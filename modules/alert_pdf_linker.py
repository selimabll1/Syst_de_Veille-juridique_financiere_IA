from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
from typing import Any

from modules.alert_identity import stable_alert_uid

PDF_LINKER_VERSION = "alert_pdf_linker_v30_1_windows_sqlite_close"
LINK_DB = Path("data/legaltech_alert_links.sqlite3")
PDF_DIRS = [
    Path("data/pdf_raw"),
    Path("data/pdf_archive"),
    Path("data/pdfs"),
    Path("data/pdf"),
    Path("pdfs"),
]
LEGALTECH_REGISTRY = Path("data/legaltech_registry.sqlite3")
_CACHE_TTL = 45.0
_CATALOG_CACHE_AT = 0.0
_CATALOG_CACHE: list[dict[str, Any]] = []
_REGISTRY_CACHE_AT = 0.0
_REGISTRY_CACHE: list[dict[str, Any]] = []


@contextmanager
def _connect():
    """Open a SQLite connection and ALWAYS close it.

    sqlite3.Connection used as a context manager commits/rolls back but does
    not close the connection. On Windows that kept links.sqlite3 locked and
    broke the V30 verifier / temporary database cleanup.
    """
    LINK_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(LINK_DB)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def initialize() -> None:
    with _connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS alert_documents (
                 alert_uid TEXT PRIMARY KEY,
                 path TEXT NOT NULL,
                 method TEXT NOT NULL,
                 linked_at TEXT NOT NULL
               )"""
        )


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def invalidate_pdf_cache() -> None:
    global _CATALOG_CACHE_AT, _CATALOG_CACHE, _REGISTRY_CACHE_AT, _REGISTRY_CACHE
    _CATALOG_CACHE_AT = 0.0
    _CATALOG_CACHE = []
    _REGISTRY_CACHE_AT = 0.0
    _REGISTRY_CACHE = []


def _existing_saved(uid: str) -> Path | None:
    initialize()
    with _connect() as con:
        row = con.execute(
            "SELECT path FROM alert_documents WHERE alert_uid=?", (uid,)
        ).fetchone()
    if not row:
        return None
    path = Path(str(row["path"] or ""))
    return path if path.exists() and path.is_file() else None


def _save(uid: str, path: Path, method: str) -> Path:
    path = path.resolve()
    initialize()
    with _connect() as con:
        con.execute(
            """INSERT INTO alert_documents(alert_uid,path,method,linked_at)
               VALUES (?,?,?,?)
               ON CONFLICT(alert_uid) DO UPDATE SET
                 path=excluded.path, method=excluded.method,
                 linked_at=excluded.linked_at""",
            (uid, str(path), method, _now()),
        )
    return path


def _direct_path(alert: dict[str, Any]) -> Path | None:
    fields = alert.get("source_fields") or {}
    if not isinstance(fields, dict):
        fields = {}
    for raw in (
        alert.get("download_path"), alert.get("pdf_path"), alert.get("local_path"),
        fields.get("download_path"), fields.get("pdf_path"), fields.get("local_path"),
    ):
        text = str(raw or "").strip()
        if not text:
            continue
        path = Path(text)
        if path.exists() and path.is_file() and path.suffix.casefold() == ".pdf":
            return path.resolve()
    return None


def _registry_rows() -> list[dict[str, Any]]:
    global _REGISTRY_CACHE_AT, _REGISTRY_CACHE
    now = time.monotonic()
    if _REGISTRY_CACHE and now - _REGISTRY_CACHE_AT < _CACHE_TTL:
        return list(_REGISTRY_CACHE)
    if not LEGALTECH_REGISTRY.exists():
        _REGISTRY_CACHE, _REGISTRY_CACHE_AT = [], now
        return []
    try:
        con = sqlite3.connect(LEGALTECH_REGISTRY)
        con.row_factory = sqlite3.Row
        rows = [dict(row) for row in con.execute(
            "SELECT * FROM documents ORDER BY collected_at DESC"
        ).fetchall()]
        con.close()
    except sqlite3.Error:
        rows = []
    _REGISTRY_CACHE, _REGISTRY_CACHE_AT = rows, now
    return list(rows)


def _catalog() -> list[dict[str, Any]]:
    global _CATALOG_CACHE_AT, _CATALOG_CACHE
    now = time.monotonic()
    if _CATALOG_CACHE and now - _CATALOG_CACHE_AT < _CACHE_TTL:
        return list(_CATALOG_CACHE)

    mapping: dict[str, dict[str, Any]] = {}
    for directory in PDF_DIRS:
        if not directory.exists():
            continue
        try:
            paths = directory.glob("*.pdf")
        except Exception:
            continue
        for path in paths:
            try:
                if not path.is_file():
                    continue
                resolved = path.resolve()
                mapping[str(resolved)] = {
                    "path": resolved,
                    "filename": resolved.name,
                    "search": _norm(resolved.name),
                    "mtime": resolved.stat().st_mtime,
                    "size_bytes": resolved.stat().st_size,
                }
            except Exception:
                continue

    # Registry can point at PDFs even when the filename itself is opaque.
    for row in _registry_rows():
        raw_path = str(row.get("local_path") or "").strip()
        path = Path(raw_path) if raw_path else None
        if path is None or not path.exists():
            filename = str(row.get("filename") or "").strip()
            path = next(
                (directory / filename for directory in PDF_DIRS
                 if filename and (directory / filename).exists()),
                None,
            )
        if path is None or not path.exists() or not path.is_file():
            continue
        path = path.resolve()
        corpus = " ".join(str(row.get(key) or "") for key in (
            "filename", "reference", "source_id", "local_path", "metadata_json"
        ))
        existing = mapping.get(str(path), {})
        mapping[str(path)] = {
            "path": path,
            "filename": path.name,
            "search": _norm((existing.get("filename") or path.name) + " " + corpus),
            "mtime": existing.get("mtime", path.stat().st_mtime),
            "size_bytes": existing.get("size_bytes", path.stat().st_size),
        }

    result = sorted(mapping.values(), key=lambda item: item["mtime"], reverse=True)
    _CATALOG_CACHE, _CATALOG_CACHE_AT = result, now
    return list(result)


def list_pdf_paths() -> list[Path]:
    return [Path(item["path"]) for item in _catalog()]


def _identity_tokens(alert: dict[str, Any]) -> list[tuple[str, int]]:
    fields = alert.get("source_fields") or {}
    if not isinstance(fields, dict):
        fields = {}
    strong = [
        alert.get("article_id"), alert.get("doc_id"),
        fields.get("reference"), fields.get("numero_publication"),
        fields.get("identifiant_unique"), fields.get("numero"), fields.get("id"),
    ]
    medium = [alert.get("card_title"), alert.get("detail_title")]
    out: list[tuple[str, int]] = []
    seen: set[str] = set()
    for value in strong:
        token = _norm(value)
        if len(token) >= 6 and token not in seen:
            seen.add(token); out.append((token, 100))
    for value in medium:
        token = _norm(value)
        if len(token) >= 10 and token not in seen:
            seen.add(token); out.append((token, 65))
    return out


def _score(alert: dict[str, Any], item: dict[str, Any]) -> int:
    haystack = str(item.get("search") or "")
    score = 0
    for token, weight in _identity_tokens(alert):
        if token and token in haystack:
            score = max(score, weight)
    return score


def find_pdf_for_alert(alert: dict[str, Any]) -> Path | None:
    uid = stable_alert_uid(alert)
    saved = _existing_saved(uid)
    if saved:
        return saved

    direct = _direct_path(alert)
    if direct:
        return _save(uid, direct, "notification_direct_path")

    best: tuple[int, Path] | None = None
    for item in _catalog():
        score = _score(alert, item)
        path = Path(item["path"])
        if score >= 60 and (best is None or score > best[0]):
            best = (score, path)
    if best:
        return _save(uid, best[1], "canonical_identifier_match")
    return None
