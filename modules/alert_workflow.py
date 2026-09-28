from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Iterable, Any

WORKFLOW_DB = Path("data/legaltech_workflow.sqlite3")

AI_PENDING = "pending"
AI_RUNNING = "running"
AI_DONE = "done"
AI_FAILED = "failed"

VALID_AI_STATUSES = {AI_PENDING, AI_RUNNING, AI_DONE, AI_FAILED}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    WORKFLOW_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(WORKFLOW_DB)
    connection.row_factory = sqlite3.Row
    return connection


def initialize() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS alert_workflow (
                alert_key TEXT PRIMARY KEY,
                is_read INTEGER NOT NULL DEFAULT 0,
                read_at TEXT,
                ai_status TEXT NOT NULL DEFAULT 'pending',
                ai_started_at TEXT,
                ai_completed_at TEXT,
                last_error TEXT,
                is_new_since_last_sync INTEGER NOT NULL DEFAULT 0,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                treated_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workflow_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_key TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_at TEXT NOT NULL,
                details TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_workflow_read
                ON alert_workflow(is_read);

            CREATE INDEX IF NOT EXISTS idx_workflow_ai
                ON alert_workflow(ai_status);

            CREATE INDEX IF NOT EXISTS idx_workflow_new
                ON alert_workflow(is_new_since_last_sync);

            CREATE INDEX IF NOT EXISTS idx_events_alert
                ON workflow_events(alert_key, event_at DESC);
            """
        )


def record_event(
    alert_key: str,
    event_type: str,
    details: str | None = None,
) -> None:
    initialize()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO workflow_events(alert_key, event_type, event_at, details)
            VALUES (?, ?, ?, ?)
            """,
            (str(alert_key), str(event_type), _now(), details),
        )


def ensure_alerts(alert_keys: Iterable[str]) -> None:
    """Create missing workflow rows without rewriting every existing row.

    V31 deliberately avoids updating last_seen_at during normal UI renders.
    This removes hundreds of unnecessary SQLite writes per click.
    """
    initialize()
    keys = list(dict.fromkeys(str(key) for key in alert_keys if str(key)))
    if not keys:
        return
    now = _now()
    connection = _connect()
    try:
        connection.executemany(
            """
            INSERT OR IGNORE INTO alert_workflow(
                alert_key, first_seen_at, last_seen_at, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            [(key, now, now, now) for key in keys],
        )
        connection.commit()
    finally:
        connection.close()



def get_state(alert_key: str) -> dict[str, Any]:
    initialize()
    key = str(alert_key)

    ensure_alerts([key])

    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM alert_workflow WHERE alert_key = ?",
            (key,),
        ).fetchone()

    return dict(row) if row else {
        "alert_key": key,
        "is_read": 0,
        "ai_status": AI_PENDING,
        "is_new_since_last_sync": 0,
        "treated_at": None,
    }


def get_states(alert_keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    initialize()
    keys = [str(key) for key in alert_keys if str(key)]
    if not keys:
        return {}

    ensure_alerts(keys)

    placeholders = ",".join("?" for _ in keys)
    with _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM alert_workflow
            WHERE alert_key IN ({placeholders})
            """,
            keys,
        ).fetchall()

    return {str(row["alert_key"]): dict(row) for row in rows}


def is_treated_state(state: dict[str, Any]) -> bool:
    return bool(state.get("is_read")) and state.get("ai_status") == AI_DONE


def mark_read(alert_key: str) -> bool:
    """Return True only when this action moves the alert to Traitées."""
    initialize()
    key = str(alert_key)
    state = get_state(key)

    already_read = bool(state.get("is_read"))
    was_treated = is_treated_state(state)
    now = _now()

    treated_at = state.get("treated_at")
    if state.get("ai_status") == AI_DONE and not treated_at:
        treated_at = now

    with _connect() as connection:
        connection.execute(
            """
            UPDATE alert_workflow
            SET
                is_read = 1,
                read_at = COALESCE(read_at, ?),
                is_new_since_last_sync = 0,
                treated_at = ?,
                updated_at = ?
            WHERE alert_key = ?
            """,
            (now, treated_at, now, key),
        )

    if not already_read:
        record_event(key, "ALERT_OPENED", "Notification ouverte et marquée comme lue.")

    after = get_state(key)
    moved = (not was_treated) and is_treated_state(after)

    if moved:
        record_event(
            key,
            "MOVED_TO_TREATED",
            "Notification lue et analyse IA terminée.",
        )

    return moved


def mark_ai_running(alert_key: str) -> None:
    initialize()
    key = str(alert_key)
    state = get_state(key)
    now = _now()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE alert_workflow
            SET
                ai_status = ?,
                ai_started_at = ?,
                ai_completed_at = NULL,
                last_error = NULL,
                treated_at = NULL,
                updated_at = ?
            WHERE alert_key = ?
            """,
            (AI_RUNNING, now, now, key),
        )

    if state.get("ai_status") != AI_RUNNING:
        record_event(key, "AI_STARTED", "Analyse IA lancée.")


def mark_ai_done(alert_key: str) -> bool:
    """Return True only when completion moves the alert to Traitées."""
    initialize()
    key = str(alert_key)
    state = get_state(key)
    was_treated = is_treated_state(state)
    now = _now()

    treated_at = now if bool(state.get("is_read")) else None

    with _connect() as connection:
        connection.execute(
            """
            UPDATE alert_workflow
            SET
                ai_status = ?,
                ai_completed_at = ?,
                last_error = NULL,
                treated_at = ?,
                updated_at = ?
            WHERE alert_key = ?
            """,
            (AI_DONE, now, treated_at, now, key),
        )

    if state.get("ai_status") != AI_DONE:
        record_event(key, "AI_COMPLETED", "Analyse IA terminée avec succès.")

    after = get_state(key)
    moved = (not was_treated) and is_treated_state(after)

    if moved:
        record_event(
            key,
            "MOVED_TO_TREATED",
            "Notification lue et analyse IA terminée.",
        )

    return moved


def mark_ai_failed(alert_key: str, error: str | None = None) -> None:
    initialize()
    key = str(alert_key)
    state = get_state(key)
    now = _now()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE alert_workflow
            SET
                ai_status = ?,
                ai_completed_at = ?,
                last_error = ?,
                treated_at = NULL,
                updated_at = ?
            WHERE alert_key = ?
            """,
            (AI_FAILED, now, str(error or "Analyse IA non exploitable."), now, key),
        )

    if state.get("ai_status") != AI_FAILED or state.get("last_error") != error:
        record_event(
            key,
            "AI_FAILED",
            str(error or "Analyse IA non exploitable."),
        )


def reconcile_ai_status(alert_key: str, desired_status: str) -> None:
    """Synchronize legacy cached analyses into workflow state without fake re-runs."""
    if desired_status not in {AI_DONE, AI_FAILED}:
        return

    key = str(alert_key)
    state = get_state(key)

    # Do not overwrite an analysis currently being launched by the user.
    if state.get("ai_status") == AI_RUNNING:
        return

    if state.get("ai_status") == desired_status:
        return

    now = _now()
    treated_at = (
        now
        if desired_status == AI_DONE and bool(state.get("is_read"))
        else None
    )

    with _connect() as connection:
        connection.execute(
            """
            UPDATE alert_workflow
            SET
                ai_status = ?,
                ai_completed_at = ?,
                treated_at = ?,
                updated_at = ?
            WHERE alert_key = ?
            """,
            (desired_status, now, treated_at, now, key),
        )


def mark_new_alerts(alert_keys: Iterable[str]) -> None:
    """
    Mark only the alerts discovered during the most recent successful sync
    as 'new since last sync'.
    """
    initialize()
    keys = [str(key) for key in alert_keys if str(key)]
    now = _now()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE alert_workflow
            SET is_new_since_last_sync = 0, updated_at = ?
            """,
            (now,),
        )

    if not keys:
        return

    ensure_alerts(keys)

    with _connect() as connection:
        for key in keys:
            connection.execute(
                """
                UPDATE alert_workflow
                SET
                    is_new_since_last_sync = 1,
                    is_read = 0,
                    read_at = NULL,
                    ai_status = 'pending',
                    ai_started_at = NULL,
                    ai_completed_at = NULL,
                    last_error = NULL,
                    treated_at = NULL,
                    updated_at = ?
                WHERE alert_key = ?
                """,
                (now, key),
            )

    for key in keys:
        record_event(
            key,
            "ALERT_COLLECTED",
            "Nouvelle alerte détectée lors de la synchronisation.",
        )


def clear_new_flag(alert_key: str) -> None:
    initialize()
    now = _now()
    with _connect() as connection:
        connection.execute(
            """
            UPDATE alert_workflow
            SET is_new_since_last_sync = 0, updated_at = ?
            WHERE alert_key = ?
            """,
            (now, str(alert_key)),
        )


def get_new_keys(alert_keys: Iterable[str] | None = None) -> list[str]:
    initialize()

    query = """
        SELECT alert_key
        FROM alert_workflow
        WHERE is_new_since_last_sync = 1
        ORDER BY first_seen_at DESC
    """
    params: list[str] = []

    if alert_keys is not None:
        keys = [str(key) for key in alert_keys if str(key)]
        if not keys:
            return []
        placeholders = ",".join("?" for _ in keys)
        query = f"""
            SELECT alert_key
            FROM alert_workflow
            WHERE is_new_since_last_sync = 1
              AND alert_key IN ({placeholders})
            ORDER BY first_seen_at DESC
        """
        params = keys

    with _connect() as connection:
        rows = connection.execute(query, params).fetchall()

    return [str(row["alert_key"]) for row in rows]


def get_counts(alert_keys: Iterable[str]) -> dict[str, int]:
    keys = [str(key) for key in alert_keys if str(key)]
    states = get_states(keys)

    counts = {
        "total": len(keys),
        "unread": 0,
        "read": 0,
        "to_process": 0,
        "treated": 0,
        "pending": 0,
        "running": 0,
        "done": 0,
        "failed": 0,
        "new": 0,
    }

    for key in keys:
        state = states.get(key, {})
        is_read = bool(state.get("is_read"))
        ai_status = str(state.get("ai_status") or AI_PENDING)

        counts["read" if is_read else "unread"] += 1

        if is_treated_state(state):
            counts["treated"] += 1
        else:
            counts["to_process"] += 1

        if ai_status in {AI_PENDING, AI_RUNNING, AI_DONE, AI_FAILED}:
            counts[ai_status] += 1

        if bool(state.get("is_new_since_last_sync")):
            counts["new"] += 1

    return counts


def get_events(alert_key: str, limit: int = 20) -> list[dict[str, Any]]:
    initialize()
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT event_type, event_at, details
            FROM workflow_events
            WHERE alert_key = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (str(alert_key), int(limit)),
        ).fetchall()

    return [dict(row) for row in rows]


def migrate_key(old_key: str, new_key: str) -> None:
    """Merge legacy workflow state into a stable alert UID.

    Safe to call on every app load. The legacy row is intentionally preserved
    for rollback/audit; all future UI actions use new_key.
    """
    initialize()
    old_key = str(old_key or "")
    new_key = str(new_key or "")
    if not old_key or not new_key or old_key == new_key:
        return

    now = _now()
    with _connect() as connection:
        old = connection.execute(
            "SELECT * FROM alert_workflow WHERE alert_key=?",
            (old_key,),
        ).fetchone()
        new = connection.execute(
            "SELECT * FROM alert_workflow WHERE alert_key=?",
            (new_key,),
        ).fetchone()

        if old is None and new is None:
            connection.execute(
                """INSERT INTO alert_workflow(alert_key,first_seen_at,last_seen_at,updated_at)
                   VALUES (?,?,?,?)""",
                (new_key, now, now, now),
            )
            return

        if old is None:
            connection.execute(
                "UPDATE alert_workflow SET last_seen_at=? WHERE alert_key=?",
                (now, new_key),
            )
            return

        old = dict(old)
        new = dict(new) if new is not None else {}
        is_read = int(bool(old.get("is_read")) or bool(new.get("is_read")))

        statuses = [str(new.get("ai_status") or ""), str(old.get("ai_status") or "")]
        if AI_DONE in statuses:
            ai_status = AI_DONE
        elif AI_RUNNING in statuses:
            ai_status = AI_RUNNING
        elif AI_FAILED in statuses:
            ai_status = AI_FAILED
        else:
            ai_status = AI_PENDING

        def first_nonempty(*values):
            for value in values:
                if value not in (None, ""):
                    return value
            return None

        first_seen = min(
            [x for x in (old.get("first_seen_at"), new.get("first_seen_at")) if x]
            or [now]
        )
        read_at = first_nonempty(new.get("read_at"), old.get("read_at"))
        ai_started_at = first_nonempty(new.get("ai_started_at"), old.get("ai_started_at"))
        ai_completed_at = first_nonempty(new.get("ai_completed_at"), old.get("ai_completed_at"))
        treated_at = first_nonempty(new.get("treated_at"), old.get("treated_at"))
        if is_read and ai_status == AI_DONE and not treated_at:
            treated_at = now

        connection.execute(
            """INSERT INTO alert_workflow(
                 alert_key,is_read,read_at,ai_status,ai_started_at,ai_completed_at,
                 last_error,is_new_since_last_sync,first_seen_at,last_seen_at,
                 treated_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(alert_key) DO UPDATE SET
                 is_read=excluded.is_read,
                 read_at=COALESCE(alert_workflow.read_at,excluded.read_at),
                 ai_status=excluded.ai_status,
                 ai_started_at=COALESCE(alert_workflow.ai_started_at,excluded.ai_started_at),
                 ai_completed_at=COALESCE(alert_workflow.ai_completed_at,excluded.ai_completed_at),
                 last_error=COALESCE(alert_workflow.last_error,excluded.last_error),
                 first_seen_at=excluded.first_seen_at,
                 last_seen_at=excluded.last_seen_at,
                 treated_at=COALESCE(alert_workflow.treated_at,excluded.treated_at),
                 updated_at=excluded.updated_at""",
            (
                new_key,is_read,read_at,ai_status,ai_started_at,ai_completed_at,
                first_nonempty(new.get("last_error"), old.get("last_error")),
                0,first_seen,now,treated_at,now,
            ),
        )

        # Copy old events once, tagged by same event time/type/details.
        old_events = connection.execute(
            "SELECT event_type,event_at,details FROM workflow_events WHERE alert_key=?",
            (old_key,),
        ).fetchall()
        for event in old_events:
            exists = connection.execute(
                """SELECT 1 FROM workflow_events
                   WHERE alert_key=? AND event_type=? AND event_at=? AND COALESCE(details,'')=COALESCE(?, '')
                   LIMIT 1""",
                (new_key, event["event_type"], event["event_at"], event["details"]),
            ).fetchone()
            if not exists:
                connection.execute(
                    "INSERT INTO workflow_events(alert_key,event_type,event_at,details) VALUES (?,?,?,?)",
                    (new_key, event["event_type"], event["event_at"], event["details"]),
                )
