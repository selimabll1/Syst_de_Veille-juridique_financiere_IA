from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import json
import sqlite3
import time
from typing import Any, Iterable

from modules.alert_identity import stable_alert_uid

BUSINESS_DB = Path("data/legaltech_business_workflow.sqlite3")

from modules.service_model import SERVICES

SOURCES = {
    "legaltech": {
        "label": "LegalTech",
        "status": "active",
        "services": ["commercial", "portfolio"],
        "note": "Source actuellement connectée.",
    },
    "social": {
        "label": "Réseaux sociaux",
        "status": "planned",
        "services": ["commercial"],
        "note": "Collecteur à connecter dans la phase suivante.",
    },
    "finance_ministry": {
        "label": "Ministère des Finances",
        "status": "planned",
        "services": ["compliance"],
        "note": "Collecteur à connecter dans la phase suivante.",
    },
    "cmf": {
        "label": "Conseil du Marché Financier",
        "status": "planned",
        "services": ["compliance"],
        "note": "Collecteur à connecter dans la phase suivante.",
    },
}

_INITIALIZED = False
_CACHE_AT = 0.0
_CACHE_TTL = 10.0
_ROUTE_CACHE: dict[str, list[str]] = {}
_TAG_CACHE: dict[str, list[str]] = {}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@contextmanager
def _connect():
    """Open a SQLite connection and ALWAYS close it.

    sqlite3.Connection used directly as a context manager commits/rolls back,
    but does not close the connection. On Windows that leaves temporary
    databases locked and caused the V32 verifier WinError 32.
    """
    BUSINESS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(BUSINESS_DB)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _invalidate_cache() -> None:
    global _CACHE_AT, _ROUTE_CACHE, _TAG_CACHE
    _CACHE_AT = 0.0
    _ROUTE_CACHE = {}
    _TAG_CACHE = {}


def initialize() -> None:
    global _INITIALIZED
    if _INITIALIZED and BUSINESS_DB.exists():
        return

    with _connect() as con:
        con.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS alert_service_routes (
                alert_uid TEXT NOT NULL,
                service_id TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                origin TEXT NOT NULL DEFAULT 'manual',
                reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(alert_uid, service_id)
            );

            CREATE TABLE IF NOT EXISTS alert_tags (
                alert_uid TEXT NOT NULL,
                tag TEXT NOT NULL,
                origin TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                PRIMARY KEY(alert_uid, tag)
            );

            CREATE TABLE IF NOT EXISTS alert_assignments (
                alert_uid TEXT PRIMARY KEY,
                assignee TEXT,
                team TEXT,
                due_at TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alert_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_uid TEXT NOT NULL,
                author TEXT,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS digest_queue (
                alert_uid TEXT NOT NULL,
                service_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                queued_at TEXT NOT NULL,
                sent_at TEXT,
                PRIMARY KEY(alert_uid, service_id)
            );

            CREATE TABLE IF NOT EXISTS service_digest_settings (
                service_id TEXT PRIMARY KEY,
                recipients_json TEXT NOT NULL DEFAULT '[]',
                cadence TEXT NOT NULL DEFAULT 'daily',
                enabled INTEGER NOT NULL DEFAULT 0,
                critical_immediate INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_catalog (
                source_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                status TEXT NOT NULL,
                services_json TEXT NOT NULL DEFAULT '[]',
                note TEXT,
                last_check_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS watchlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                service_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS watchlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watchlist_id INTEGER NOT NULL,
                company TEXT NOT NULL DEFAULT '',
                identifier TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(watchlist_id, company, identifier)
            );

            CREATE INDEX IF NOT EXISTS idx_routes_service
              ON alert_service_routes(service_id, active);

            CREATE INDEX IF NOT EXISTS idx_notes_alert
              ON alert_notes(alert_uid, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_digest_service
              ON digest_queue(service_id, status);
            """
        )

        now = _now()
        for source_id, source in SOURCES.items():
            con.execute(
                """
                INSERT INTO source_catalog(
                    source_id, label, status, services_json, note, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    label=excluded.label,
                    services_json=excluded.services_json,
                    note=COALESCE(source_catalog.note, excluded.note)
                """,
                (
                    source_id,
                    source["label"],
                    source["status"],
                    json.dumps(source["services"], ensure_ascii=False),
                    source["note"],
                    now,
                ),
            )

        for service_id in SERVICES:
            con.execute(
                """
                INSERT OR IGNORE INTO service_digest_settings(
                    service_id, recipients_json, cadence, enabled,
                    critical_immediate, updated_at
                )
                VALUES (?, '[]', 'daily', 0, 1, ?)
                """,
                (service_id, now),
            )

    _INITIALIZED = True


def service_label(service_id: str) -> str:
    return SERVICES.get(service_id, {}).get("label", service_id)


def bootstrap_existing_legaltech(alerts: Iterable[dict[str, Any]]) -> int:
    """
    Existing LegalTech work is treated as the current Commercial scope.
    This does not duplicate alerts; it only creates a service route.
    """
    initialize()
    now = _now()
    inserted = 0
    with _connect() as con:
        for alert in alerts:
            uid = stable_alert_uid(alert)
            if not uid:
                continue
            cur = con.execute(
                """
                INSERT OR IGNORE INTO alert_service_routes(
                    alert_uid, service_id, active, origin, reason,
                    created_at, updated_at
                )
                VALUES (?, 'commercial', 1, 'legacy_legaltech',
                        'Socle LegalTech existant', ?, ?)
                """,
                (uid, now, now),
            )
            inserted += int(cur.rowcount or 0)
    if inserted:
        _invalidate_cache()
    return inserted


def set_routes(
    alert_uid: str,
    services: Iterable[str],
    *,
    origin: str = "manual",
    reason: str = "",
) -> None:
    initialize()
    uid = str(alert_uid)
    selected = {str(service) for service in services if str(service) in SERVICES}
    now = _now()

    with _connect() as con:
        for service_id in SERVICES:
            if service_id in selected:
                con.execute(
                    """
                    INSERT INTO alert_service_routes(
                        alert_uid, service_id, active, origin, reason,
                        created_at, updated_at
                    )
                    VALUES (?, ?, 1, ?, ?, ?, ?)
                    ON CONFLICT(alert_uid, service_id) DO UPDATE SET
                        active=1, origin=excluded.origin,
                        reason=excluded.reason, updated_at=excluded.updated_at
                    """,
                    (uid, service_id, origin, reason, now, now),
                )
            else:
                con.execute(
                    """
                    UPDATE alert_service_routes
                    SET active=0, updated_at=?
                    WHERE alert_uid=? AND service_id=?
                    """,
                    (now, uid, service_id),
                )
    _invalidate_cache()


def add_route(
    alert_uid: str,
    service_id: str,
    *,
    origin: str = "manual",
    reason: str = "",
) -> None:
    if service_id not in SERVICES:
        return
    current = routes_for_alert(alert_uid)
    if service_id not in current:
        current.append(service_id)
    set_routes(alert_uid, current, origin=origin, reason=reason)


def _refresh_maps() -> None:
    global _CACHE_AT, _ROUTE_CACHE, _TAG_CACHE
    initialize()
    now = time.monotonic()
    if _CACHE_AT and now - _CACHE_AT < _CACHE_TTL:
        return

    routes: dict[str, list[str]] = {}
    tags: dict[str, list[str]] = {}
    with _connect() as con:
        for row in con.execute(
            """
            SELECT alert_uid, service_id
            FROM alert_service_routes
            WHERE active=1
            ORDER BY service_id
            """
        ):
            routes.setdefault(str(row["alert_uid"]), []).append(str(row["service_id"]))

        for row in con.execute(
            """
            SELECT alert_uid, tag
            FROM alert_tags
            ORDER BY tag
            """
        ):
            tags.setdefault(str(row["alert_uid"]), []).append(str(row["tag"]))

    _ROUTE_CACHE = routes
    _TAG_CACHE = tags
    _CACHE_AT = now


def routes_for_alert(alert_uid: str) -> list[str]:
    _refresh_maps()
    return list(_ROUTE_CACHE.get(str(alert_uid), []))


def route_map(alert_uids: Iterable[str] | None = None) -> dict[str, list[str]]:
    _refresh_maps()
    if alert_uids is None:
        return {k: list(v) for k, v in _ROUTE_CACHE.items()}
    wanted = {str(uid) for uid in alert_uids}
    return {uid: list(_ROUTE_CACHE.get(uid, [])) for uid in wanted}


def alerts_for_service(
    alerts: Iterable[dict[str, Any]],
    service_id: str,
) -> list[dict[str, Any]]:
    _refresh_maps()
    result = []
    for alert in alerts:
        uid = stable_alert_uid(alert)
        if service_id in _ROUTE_CACHE.get(uid, []):
            result.append(alert)
    return result


def add_tag(alert_uid: str, tag: str, *, origin: str = "manual") -> None:
    initialize()
    clean = " ".join(str(tag or "").split()).strip()
    if not clean:
        return
    with _connect() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO alert_tags(alert_uid, tag, origin, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(alert_uid), clean, origin, _now()),
        )
    _invalidate_cache()


def remove_tag(alert_uid: str, tag: str) -> None:
    initialize()
    with _connect() as con:
        con.execute(
            "DELETE FROM alert_tags WHERE alert_uid=? AND tag=?",
            (str(alert_uid), str(tag)),
        )
    _invalidate_cache()


def tags_for_alert(alert_uid: str) -> list[str]:
    _refresh_maps()
    return list(_TAG_CACHE.get(str(alert_uid), []))


def tags_map(alert_uids: Iterable[str] | None = None) -> dict[str, list[str]]:
    _refresh_maps()
    if alert_uids is None:
        return {k: list(v) for k, v in _TAG_CACHE.items()}
    wanted = {str(uid) for uid in alert_uids}
    return {uid: list(_TAG_CACHE.get(uid, [])) for uid in wanted}


def set_assignment(
    alert_uid: str,
    *,
    assignee: str = "",
    team: str = "",
    due_at: str = "",
    status: str = "open",
) -> None:
    initialize()
    with _connect() as con:
        con.execute(
            """
            INSERT INTO alert_assignments(
                alert_uid, assignee, team, due_at, status, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(alert_uid) DO UPDATE SET
                assignee=excluded.assignee,
                team=excluded.team,
                due_at=excluded.due_at,
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            (str(alert_uid), assignee, team, due_at, status, _now()),
        )


def assignment_for_alert(alert_uid: str) -> dict[str, Any]:
    initialize()
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM alert_assignments WHERE alert_uid=?",
            (str(alert_uid),),
        ).fetchone()
    return dict(row) if row else {}


def add_note(alert_uid: str, body: str, author: str = "Utilisateur UGFS") -> None:
    initialize()
    clean = str(body or "").strip()
    if not clean:
        return
    with _connect() as con:
        con.execute(
            """
            INSERT INTO alert_notes(alert_uid, author, body, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(alert_uid), author.strip(), clean, _now()),
        )


def notes_for_alert(alert_uid: str, limit: int = 20) -> list[dict[str, Any]]:
    initialize()
    with _connect() as con:
        rows = con.execute(
            """
            SELECT *
            FROM alert_notes
            WHERE alert_uid=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (str(alert_uid), int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def queue_for_digest(alert_uid: str, service_id: str) -> None:
    initialize()
    if service_id not in SERVICES:
        return
    with _connect() as con:
        con.execute(
            """
            INSERT INTO digest_queue(alert_uid, service_id, status, queued_at)
            VALUES (?, ?, 'queued', ?)
            ON CONFLICT(alert_uid, service_id) DO UPDATE SET
                status='queued', queued_at=excluded.queued_at, sent_at=NULL
            """,
            (str(alert_uid), service_id, _now()),
        )


def pending_digest_uids(service_id: str) -> list[str]:
    initialize()
    with _connect() as con:
        rows = con.execute(
            """
            SELECT alert_uid
            FROM digest_queue
            WHERE service_id=? AND status='queued'
            ORDER BY queued_at
            """,
            (service_id,),
        ).fetchall()
    return [str(row["alert_uid"]) for row in rows]


def mark_digest_sent(service_id: str, alert_uids: Iterable[str]) -> None:
    initialize()
    now = _now()
    with _connect() as con:
        for uid in alert_uids:
            con.execute(
                """
                UPDATE digest_queue
                SET status='sent', sent_at=?
                WHERE service_id=? AND alert_uid=?
                """,
                (now, service_id, str(uid)),
            )


def save_digest_settings(
    service_id: str,
    recipients: Iterable[str],
    cadence: str,
    enabled: bool,
    critical_immediate: bool,
) -> None:
    initialize()
    recipients_clean = sorted({
        str(value).strip()
        for value in recipients
        if str(value).strip()
    })
    with _connect() as con:
        con.execute(
            """
            INSERT INTO service_digest_settings(
                service_id, recipients_json, cadence, enabled,
                critical_immediate, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(service_id) DO UPDATE SET
                recipients_json=excluded.recipients_json,
                cadence=excluded.cadence,
                enabled=excluded.enabled,
                critical_immediate=excluded.critical_immediate,
                updated_at=excluded.updated_at
            """,
            (
                service_id,
                json.dumps(recipients_clean, ensure_ascii=False),
                cadence,
                int(bool(enabled)),
                int(bool(critical_immediate)),
                _now(),
            ),
        )


def digest_settings(service_id: str) -> dict[str, Any]:
    initialize()
    with _connect() as con:
        row = con.execute(
            """
            SELECT * FROM service_digest_settings
            WHERE service_id=?
            """,
            (service_id,),
        ).fetchone()
    if not row:
        return {
            "service_id": service_id,
            "recipients": [],
            "cadence": "daily",
            "enabled": False,
            "critical_immediate": True,
        }
    item = dict(row)
    try:
        item["recipients"] = json.loads(item.get("recipients_json") or "[]")
    except Exception:
        item["recipients"] = []
    item["enabled"] = bool(item.get("enabled"))
    item["critical_immediate"] = bool(item.get("critical_immediate"))
    return item


def list_sources() -> list[dict[str, Any]]:
    initialize()
    with _connect() as con:
        rows = con.execute(
            "SELECT * FROM source_catalog ORDER BY source_id"
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["services"] = json.loads(item.get("services_json") or "[]")
        except Exception:
            item["services"] = []
        result.append(item)
    return result


def update_source_status(
    source_id: str,
    *,
    status: str | None = None,
    last_check_at: str | None = None,
    note: str | None = None,
) -> None:
    initialize()
    current = next(
        (item for item in list_sources() if item["source_id"] == source_id),
        None,
    )
    if not current:
        return
    with _connect() as con:
        con.execute(
            """
            UPDATE source_catalog
            SET status=?, last_check_at=?, note=?, updated_at=?
            WHERE source_id=?
            """,
            (
                status or current["status"],
                last_check_at if last_check_at is not None else current.get("last_check_at"),
                note if note is not None else current.get("note"),
                _now(),
                source_id,
            ),
        )


def create_watchlist(name: str, service_id: str = "portfolio") -> int:
    initialize()
    clean = " ".join(str(name or "").split()).strip()
    if not clean:
        clean = "Watchlist"
    now = _now()
    with _connect() as con:
        cur = con.execute(
            """
            INSERT INTO watchlists(name, service_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (clean, service_id, now, now),
        )
        return int(cur.lastrowid)


def list_watchlists(service_id: str | None = None) -> list[dict[str, Any]]:
    initialize()
    with _connect() as con:
        if service_id:
            rows = con.execute(
                """
                SELECT * FROM watchlists
                WHERE service_id=?
                ORDER BY id DESC
                """,
                (service_id,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM watchlists ORDER BY id DESC"
            ).fetchall()
    return [dict(row) for row in rows]


def add_watchlist_item(
    watchlist_id: int,
    company: str = "",
    identifier: str = "",
) -> None:
    initialize()
    company = " ".join(str(company or "").split()).strip()
    identifier = " ".join(str(identifier or "").split()).strip()
    if not company and not identifier:
        return
    with _connect() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO watchlist_items(
                watchlist_id, company, identifier, active, created_at
            )
            VALUES (?, ?, ?, 1, ?)
            """,
            (int(watchlist_id), company, identifier, _now()),
        )


def list_watchlist_items(watchlist_id: int) -> list[dict[str, Any]]:
    initialize()
    with _connect() as con:
        rows = con.execute(
            """
            SELECT *
            FROM watchlist_items
            WHERE watchlist_id=? AND active=1
            ORDER BY company, identifier
            """,
            (int(watchlist_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def remove_watchlist_item(item_id: int) -> None:
    initialize()
    with _connect() as con:
        con.execute(
            "UPDATE watchlist_items SET active=0 WHERE id=?",
            (int(item_id),),
        )
