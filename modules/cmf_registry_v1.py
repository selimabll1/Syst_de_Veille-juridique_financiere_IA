from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator


CMF_REGISTRY_VERSION = "cmf_registry_v1_2"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "cmf_compliance_v1.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect(database_path: str | Path = DEFAULT_DB) -> Iterator[sqlite3.Connection]:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize(database_path: str | Path = DEFAULT_DB) -> None:
    """Create/migrate the CMF-only registry without touching LegalTech databases."""
    with _connect(database_path) as connection:
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS cmf_items (
                uid TEXT PRIMARY KEY,
                section TEXT NOT NULL,
                title TEXT NOT NULL,
                published_at TEXT,
                detail_url TEXT,
                pdf_url TEXT,
                language TEXT,
                category TEXT,
                priority TEXT,
                service TEXT NOT NULL DEFAULT 'compliance',
                raw_excerpt TEXT,
                source_mode TEXT NOT NULL DEFAULT 'live',
                is_new INTEGER NOT NULL DEFAULT 0,
                is_read INTEGER NOT NULL DEFAULT 0,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                content_sha256 TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cmf_sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                mode TEXT NOT NULL DEFAULT 'live',
                item_count INTEGER NOT NULL DEFAULT 0,
                avis_count INTEGER NOT NULL DEFAULT 0,
                bulletin_count INTEGER NOT NULL DEFAULT 0,
                inserted_count INTEGER NOT NULL DEFAULT 0,
                updated_count INTEGER NOT NULL DEFAULT 0,
                new_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                errors_json TEXT NOT NULL DEFAULT '[]'
            );

            CREATE INDEX IF NOT EXISTS idx_cmf_items_pub
                ON cmf_items(published_at DESC);
            CREATE INDEX IF NOT EXISTS idx_cmf_items_section
                ON cmf_items(section);
            CREATE INDEX IF NOT EXISTS idx_cmf_items_read
                ON cmf_items(is_read, is_new);
            """
        )

        existing_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(cmf_items)").fetchall()
        }
        migrations = {
            "detail_url": "TEXT",
            "pdf_url": "TEXT",
            "language": "TEXT",
            "category": "TEXT",
            "priority": "TEXT",
            "service": "TEXT NOT NULL DEFAULT 'compliance'",
            "raw_excerpt": "TEXT",
            "source_mode": "TEXT NOT NULL DEFAULT 'live'",
            "is_new": "INTEGER NOT NULL DEFAULT 0",
            "is_read": "INTEGER NOT NULL DEFAULT 0",
            "first_seen_at": "TEXT",
            "last_seen_at": "TEXT",
            "content_sha256": "TEXT",
            "updated_at": "TEXT",
        }
        for column, sql_type in migrations.items():
            if column not in existing_columns:
                connection.execute(
                    f"ALTER TABLE cmf_items ADD COLUMN {column} {sql_type}"
                )

        # Remove only prototype/demo rows. Real live data is preserved.
        connection.execute("DELETE FROM cmf_items WHERE source_mode = 'demo'")


def purge_demo_items(database_path: str | Path = DEFAULT_DB) -> int:
    initialize(database_path)
    with _connect(database_path) as connection:
        cursor = connection.execute("DELETE FROM cmf_items WHERE source_mode = 'demo'")
        return int(cursor.rowcount or 0)


def _canonical_item(item: dict[str, Any]) -> dict[str, Any]:
    result = {
        "uid": str(item.get("uid") or "").strip(),
        "section": str(item.get("section") or "").strip(),
        "title": " ".join(str(item.get("title") or "").split()).strip(),
        "published_at": str(item.get("published_at") or "").strip(),
        "detail_url": str(item.get("detail_url") or "").strip(),
        "pdf_url": str(item.get("pdf_url") or "").strip(),
        "language": str(item.get("language") or "fr").strip() or "fr",
        "category": str(item.get("category") or "Publication CMF").strip(),
        "priority": str(item.get("priority") or "Non classée").strip(),
        "service": "compliance",
        "raw_excerpt": str(item.get("raw_excerpt") or "").strip(),
    }
    if not result["uid"]:
        identity = "|".join(
            [
                result["section"],
                result["title"].casefold(),
                result["published_at"],
                result["detail_url"],
            ]
        )
        result["uid"] = sha256(identity.encode("utf-8")).hexdigest()
    return result


def _digest(item: dict[str, Any]) -> str:
    payload = json.dumps(
        {
            key: item.get(key, "")
            for key in (
                "section",
                "title",
                "published_at",
                "detail_url",
                "pdf_url",
                "language",
                "category",
                "priority",
                "service",
                "raw_excerpt",
            )
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def upsert_items(
    items: list[dict[str, Any]],
    *,
    source_mode: str = "live",
    first_live_sync_as_baseline: bool = True,
    database_path: str | Path = DEFAULT_DB,
) -> dict[str, int]:
    initialize(database_path)
    now = _now()
    source_mode = "live" if source_mode != "demo" else "demo"

    with _connect(database_path) as connection:
        live_exists = bool(
            connection.execute(
                "SELECT 1 FROM cmf_items WHERE source_mode = 'live' LIMIT 1"
            ).fetchone()
        )
        baseline = (
            source_mode == "live"
            and first_live_sync_as_baseline
            and not live_exists
        )

        stats = {"inserted": 0, "updated": 0, "unchanged": 0, "new": 0}

        for raw in items:
            item = _canonical_item(raw)
            if not item["title"] or item["section"] not in {"avis", "bulletin"}:
                continue

            digest = _digest(item)
            existing = connection.execute(
                "SELECT * FROM cmf_items WHERE uid = ?", (item["uid"],)
            ).fetchone()

            # Compatibility with an earlier prototype that may have used a
            # different UID formula: reconcile on natural publication identity
            # before inserting, so a live re-sync cannot duplicate existing rows.
            if existing is None:
                existing = connection.execute(
                    """
                    SELECT * FROM cmf_items
                    WHERE source_mode != 'demo'
                      AND section = ?
                      AND title = ?
                      AND COALESCE(published_at, '') = ?
                    ORDER BY first_seen_at ASC
                    LIMIT 1
                    """,
                    (item["section"], item["title"], item["published_at"]),
                ).fetchone()
                if existing is not None:
                    item["uid"] = str(existing["uid"])

            if existing is None:
                is_new = 0 if baseline else 1
                connection.execute(
                    """
                    INSERT INTO cmf_items (
                        uid, section, title, published_at, detail_url, pdf_url,
                        language, category, priority, service, raw_excerpt,
                        source_mode, is_new, is_read, first_seen_at, last_seen_at,
                        content_sha256, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'compliance', ?, ?, ?, 0, ?, ?, ?, ?)
                    """,
                    (
                        item["uid"],
                        item["section"],
                        item["title"],
                        item["published_at"],
                        item["detail_url"],
                        item["pdf_url"],
                        item["language"],
                        item["category"],
                        item["priority"],
                        item["raw_excerpt"],
                        source_mode,
                        is_new,
                        now,
                        now,
                        digest,
                        now,
                    ),
                )
                stats["inserted"] += 1
                stats["new"] += is_new
                continue

            changed = str(existing["content_sha256"] or "") != digest
            if changed:
                # An updated official publication is actionable again after baseline.
                next_new = 0 if baseline else 1
                connection.execute(
                    """
                    UPDATE cmf_items
                    SET section = ?, title = ?, published_at = ?, detail_url = ?,
                        pdf_url = COALESCE(NULLIF(?, ''),pdf_url), language = ?, category = ?, priority = ?,
                        service = 'compliance', raw_excerpt = COALESCE(NULLIF(?, ''),raw_excerpt), source_mode = ?,
                        is_new = CASE WHEN ? = 1 THEN 1 ELSE is_new END,
                        last_seen_at = ?, content_sha256 = ?, updated_at = ?
                    WHERE uid = ?
                    """,
                    (
                        item["section"],
                        item["title"],
                        item["published_at"],
                        item["detail_url"],
                        item["pdf_url"],
                        item["language"],
                        item["category"],
                        item["priority"],
                        item["raw_excerpt"],
                        source_mode,
                        next_new,
                        now,
                        digest,
                        now,
                        item["uid"],
                    ),
                )
                stats["updated"] += 1
                stats["new"] += next_new
            else:
                connection.execute(
                    "UPDATE cmf_items SET last_seen_at = ?, source_mode = ? WHERE uid = ?",
                    (now, source_mode, item["uid"]),
                )
                stats["unchanged"] += 1

        return stats


def counts(database_path: str | Path = DEFAULT_DB) -> dict[str, int]:
    initialize(database_path)
    with _connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN is_new = 1 AND is_read = 0 THEN 1 ELSE 0 END) AS new_count,
                SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) AS unread,
                SUM(CASE WHEN is_read = 1 THEN 1 ELSE 0 END) AS read_count,
                SUM(CASE WHEN section = 'avis' THEN 1 ELSE 0 END) AS avis,
                SUM(CASE WHEN section = 'bulletin' THEN 1 ELSE 0 END) AS bulletins,
                SUM(CASE WHEN priority IN ('Haute', 'Critique') THEN 1 ELSE 0 END) AS high
            FROM cmf_items
            WHERE source_mode != 'demo'
            """
        ).fetchone()
    return {key: int(row[key] or 0) for key in row.keys()}


def list_items(
    *,
    section: str = "",
    priority: str = "",
    unread_only: bool = False,
    read_only: bool = False,
    limit: int = 300,
    database_path: str | Path = DEFAULT_DB,
) -> list[dict[str, Any]]:
    initialize(database_path)
    clauses = ["source_mode != 'demo'"]
    params: list[Any] = []
    if section:
        clauses.append("section = ?")
        params.append(section)
    if priority:
        clauses.append("priority = ?")
        params.append(priority)
    if unread_only:
        clauses.append("is_read = 0")
    if read_only:
        clauses.append("is_read = 1")

    params.append(max(1, int(limit)))
    sql = f"""
        SELECT * FROM cmf_items
        WHERE {' AND '.join(clauses)}
        ORDER BY
            CASE WHEN published_at IS NULL OR published_at = '' THEN 1 ELSE 0 END,
            published_at DESC,
            first_seen_at DESC
        LIMIT ?
    """
    with _connect(database_path) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_item(uid: str, database_path: str | Path = DEFAULT_DB) -> dict[str, Any] | None:
    initialize(database_path)
    with _connect(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM cmf_items WHERE uid = ? AND source_mode != 'demo'", (uid,)
        ).fetchone()
    return dict(row) if row else None


def set_read(uid: str, is_read: bool, database_path: str | Path = DEFAULT_DB) -> None:
    initialize(database_path)
    with _connect(database_path) as connection:
        connection.execute(
            """
            UPDATE cmf_items
            SET is_read = ?,
                is_new = CASE WHEN ? = 1 THEN 0 ELSE is_new END,
                updated_at = ?
            WHERE uid = ?
            """,
            (int(bool(is_read)), int(bool(is_read)), _now(), uid),
        )


def update_document_content(uid: str, excerpt: str, pdf_url: str, database_path: str | Path = DEFAULT_DB) -> None:
    initialize(database_path)
    with _connect(database_path) as connection:
        connection.execute("UPDATE cmf_items SET raw_excerpt=?,pdf_url=CASE WHEN ?<>'' THEN ? ELSE pdf_url END,updated_at=? WHERE uid=?", (excerpt, pdf_url, pdf_url, _now(), uid))


def update_excerpt(uid: str, excerpt: str, database_path: str | Path = DEFAULT_DB) -> None:
    initialize(database_path)
    with _connect(database_path) as connection:
        connection.execute(
            "UPDATE cmf_items SET raw_excerpt = ?, updated_at = ? WHERE uid = ?",
            (str(excerpt or "").strip(), _now(), uid),
        )


def record_sync(
    result: dict[str, Any],
    *,
    mode: str = "live",
    stats: dict[str, int] | None = None,
    database_path: str | Path = DEFAULT_DB,
) -> None:
    initialize(database_path)
    stats = stats or {}
    errors = list(result.get("errors") or [])
    with _connect(database_path) as connection:
        columns = {r[1] for r in connection.execute("PRAGMA table_info(cmf_sync_runs)")}
        if "item_count" not in columns and "found_count" in columns:
            # Earlier installations used the compact history schema. Preserve it
            # and write its existing fields without a destructive migration.
            connection.execute("INSERT INTO cmf_sync_runs(started_at,finished_at,mode,found_count,new_count,errors_json) VALUES(?,?,?,?,?,?)", (str(result.get("started_at") or ""), str(result.get("finished_at") or _now()), mode, len(result.get("items") or []), int(stats.get("new") or result.get("new_count") or 0), json.dumps(errors, ensure_ascii=False)))
            return
        connection.execute(
            """
            INSERT INTO cmf_sync_runs (
                started_at, finished_at, mode, item_count, avis_count,
                bulletin_count, inserted_count, updated_count, new_count,
                error_count, errors_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(result.get("started_at") or ""),
                str(result.get("finished_at") or _now()),
                mode,
                len(result.get("items") or []),
                int(result.get("avis_count") or 0),
                int(result.get("bulletin_count") or 0),
                int(stats.get("inserted") or 0),
                int(stats.get("updated") or 0),
                int(stats.get("new") or result.get("new_count") or 0),
                len(errors),
                json.dumps(errors, ensure_ascii=False),
            ),
        )


def latest_sync(database_path: str | Path = DEFAULT_DB) -> dict[str, Any] | None:
    initialize(database_path)
    with _connect(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM cmf_sync_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    try:
        result["errors"] = json.loads(result.get("errors_json") or "[]")
    except Exception:
        result["errors"] = []
    return result


def seed_demo(items: list[dict[str, Any]], *args: Any, **kwargs: Any) -> dict[str, int]:
    """Compatibility no-op: integrated CMF never writes demo data."""
    del items, args, kwargs
    return {"inserted": 0, "updated": 0, "unchanged": 0, "new": 0}
