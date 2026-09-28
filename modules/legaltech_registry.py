"""Registre SQLite pour les annonces et documents collectés depuis LegalTech.

Version v4 :
- conserve la table historique ``documents`` utilisée par la bibliothèque PDF ;
- stocke les annonces structurées dans ``announcements`` ;
- déduplique les annonces par identifiant LegalTech ;
- distingue une vraie mise à jour métier d'un simple changement cosmétique de métadonnées ;
- conserve la compatibilité avec les données enregistrées par les versions précédentes.
"""

from __future__ import annotations

import ast
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator


LEGALTECH_REGISTRY_VERSION = "legaltech_registry_v5"


def _normalize_datetime_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    candidate = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(microsecond=0).isoformat()
    except ValueError:
        return text


def _flatten_serialized_text(value: Any) -> str:
    """Normalize legacy strings such as ``['texte']`` without executing code."""
    text = str(value or "").strip()
    if not text:
        return ""

    if text[:1] in {"[", "("} and text[-1:] in {"]", ")"}:
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            parsed = None

        if isinstance(parsed, (list, tuple)):
            parts = [
                _flatten_serialized_text(item)
                for item in parsed
                if item is not None
            ]
            return "\n".join(part for part in parts if part).strip()

    return text


def _normalize_compare_text(value: Any) -> str:
    text = _flatten_serialized_text(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_scalar(value: Any, *, casefold: bool = False) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text.casefold() if casefold else text


class LegalTechRegistry:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL DEFAULT 'legaltech',
                    source_id TEXT,
                    reference TEXT,
                    source_url TEXT,
                    download_url TEXT,
                    filename TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    published_at TEXT,
                    collected_at TEXT NOT NULL,
                    processing_status TEXT NOT NULL DEFAULT 'COLLECTED',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_sha256
                    ON documents(sha256);

                CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_source_id
                    ON documents(source, source_id)
                    WHERE source_id IS NOT NULL AND source_id <> '';

                CREATE INDEX IF NOT EXISTS idx_documents_reference
                    ON documents(reference);

                CREATE INDEX IF NOT EXISTS idx_documents_status
                    ON documents(processing_status);

                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL DEFAULT 'legaltech',
                    source_id TEXT NOT NULL,
                    doc_id TEXT,
                    reference TEXT,
                    title TEXT,
                    source_name TEXT,
                    language TEXT,
                    published_at TEXT,
                    page INTEGER,
                    file_ref TEXT,
                    categories_json TEXT NOT NULL DEFAULT '[]',
                    article_text_raw TEXT NOT NULL DEFAULT '',
                    article_text_clean TEXT NOT NULL DEFAULT '',
                    content_sha256 TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    processing_status TEXT NOT NULL DEFAULT 'COLLECTED',
                    pdf_status TEXT NOT NULL DEFAULT 'NOT_REQUESTED',
                    pdf_filename TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE UNIQUE INDEX IF NOT EXISTS uq_announcements_source_id
                    ON announcements(source, source_id);

                CREATE INDEX IF NOT EXISTS idx_announcements_reference
                    ON announcements(reference);

                CREATE INDEX IF NOT EXISTS idx_announcements_published
                    ON announcements(published_at);

                CREATE INDEX IF NOT EXISTS idx_announcements_source_name
                    ON announcements(source_name);
                """
            )

            existing_columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(announcements)"
                ).fetchall()
            }
            detail_migrations = {
                "detail_status": "TEXT NOT NULL DEFAULT 'NOT_FETCHED'",
                "detail_fetched_at": "TEXT",
                "detail_error": "TEXT",
                "detail_reference": "TEXT",
                "detail_title": "TEXT",
                "detail_language": "TEXT",
                "detail_published_at": "TEXT",
                "detail_page": "INTEGER",
                "detail_file_ref": "TEXT",
                "detail_categories_json": "TEXT NOT NULL DEFAULT '[]'",
                "detail_article_text_raw": "TEXT NOT NULL DEFAULT ''",
                "detail_article_text_clean": "TEXT NOT NULL DEFAULT ''",
                "detail_extras_json": "TEXT NOT NULL DEFAULT '{}'",
                "detail_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
            }
            for column, sql_type in detail_migrations.items():
                if column not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE announcements "
                        f"ADD COLUMN {column} {sql_type}"
                    )

    # -----------------------------------------------------------------
    # Structured announcements
    # -----------------------------------------------------------------

    def has_announcement_source_id(self, source_id: str | None) -> bool:
        if not source_id:
            return False

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM announcements
                WHERE source = 'legaltech'
                  AND source_id = ?
                LIMIT 1
                """,
                (source_id,),
            ).fetchone()

        return row is not None

    @staticmethod
    def _semantic_same(
        existing: sqlite3.Row,
        *,
        reference: str | None,
        source_name: str | None,
        published_at: str | None,
        page: int | None,
        article_text_clean: str,
    ) -> bool:
        """Compare only fields that materially identify the legal content.

        Cosmetic changes to title, categories, language labels, ``file`` or other
        metadata do not turn an existing announcement into UPDATED.

        The comparison also understands the legacy bad-clean value ``['texte']``,
        so installing v4 does not create a fake update just because the wrapper
        has now been cleaned.
        """
        return all(
            (
                _normalize_scalar(existing["reference"])
                == _normalize_scalar(reference),
                _normalize_scalar(existing["source_name"], casefold=True)
                == _normalize_scalar(source_name, casefold=True),
                _normalize_datetime_text(existing["published_at"])
                == _normalize_datetime_text(published_at),
                (existing["page"] if existing["page"] is not None else None)
                == (page if page is not None else None),
                _normalize_compare_text(existing["article_text_clean"])
                == _normalize_compare_text(article_text_clean),
            )
        )

    def upsert_announcement(
        self,
        *,
        source_id: str,
        doc_id: str | None,
        reference: str | None,
        title: str | None,
        source_name: str | None,
        language: str | None,
        published_at: str | None,
        page: int | None,
        file_ref: str | None,
        categories: list[str] | tuple[str, ...] | None,
        article_text_raw: str,
        article_text_clean: str,
        content_sha256: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Insert/update an announcement and return NEW, UPDATED or KNOWN."""
        if not source_id:
            raise ValueError("source_id est obligatoire pour une annonce LegalTech.")

        now = self._now()
        categories_json = json.dumps(
            list(categories or []),
            ensure_ascii=False,
            sort_keys=True,
        )
        metadata_json = json.dumps(
            metadata or {},
            ensure_ascii=False,
            sort_keys=True,
        )

        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT *
                FROM announcements
                WHERE source = 'legaltech'
                  AND source_id = ?
                LIMIT 1
                """,
                (source_id,),
            ).fetchone()

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO announcements (
                        source,
                        source_id,
                        doc_id,
                        reference,
                        title,
                        source_name,
                        language,
                        published_at,
                        page,
                        file_ref,
                        categories_json,
                        article_text_raw,
                        article_text_clean,
                        content_sha256,
                        first_seen_at,
                        last_seen_at,
                        processing_status,
                        pdf_status,
                        metadata_json
                    )
                    VALUES (
                        'legaltech', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, 'COLLECTED', 'NOT_REQUESTED', ?
                    )
                    """,
                    (
                        source_id,
                        doc_id,
                        reference,
                        title,
                        source_name,
                        language,
                        published_at,
                        page,
                        file_ref,
                        categories_json,
                        article_text_raw,
                        article_text_clean,
                        content_sha256,
                        now,
                        now,
                        metadata_json,
                    ),
                )
                return "NEW"

            semantic_same = self._semantic_same(
                existing,
                reference=reference,
                source_name=source_name,
                published_at=published_at,
                page=page,
                article_text_clean=article_text_clean,
            )
            status = "KNOWN" if semantic_same else "UPDATED"

            # Do not erase useful text if LegalTech temporarily returns an empty
            # value. A new non-empty value, however, is accepted.
            incoming_raw = str(article_text_raw or "")
            incoming_clean = str(article_text_clean or "")
            stored_raw = str(existing["article_text_raw"] or "")
            stored_clean = str(existing["article_text_clean"] or "")

            final_raw = incoming_raw if incoming_raw.strip() else stored_raw
            final_clean = incoming_clean if incoming_clean.strip() else stored_clean

            existing_processing_status = str(
                existing["processing_status"] or "COLLECTED"
            )
            final_processing_status = (
                existing_processing_status if status == "KNOWN" else "UPDATED"
            )

            connection.execute(
                """
                UPDATE announcements
                SET doc_id = ?,
                    reference = ?,
                    title = ?,
                    source_name = ?,
                    language = ?,
                    published_at = ?,
                    page = ?,
                    file_ref = ?,
                    categories_json = ?,
                    article_text_raw = ?,
                    article_text_clean = ?,
                    content_sha256 = ?,
                    last_seen_at = ?,
                    processing_status = ?,
                    metadata_json = ?
                WHERE source = 'legaltech'
                  AND source_id = ?
                """,
                (
                    doc_id or existing["doc_id"],
                    reference or existing["reference"],
                    title or existing["title"],
                    source_name or existing["source_name"],
                    language or existing["language"],
                    published_at or existing["published_at"],
                    page if page is not None else existing["page"],
                    file_ref or existing["file_ref"],
                    categories_json,
                    final_raw,
                    final_clean,
                    content_sha256,
                    now,
                    final_processing_status,
                    metadata_json,
                    source_id,
                ),
            )
            return status

    def save_announcement_detail(
        self,
        *,
        source_id: str,
        reference: str | None,
        title: str | None,
        language: str | None,
        published_at: str | None,
        page: int | None,
        file_ref: str | None,
        categories: list[str] | tuple[str, ...] | None,
        article_text_raw: str,
        article_text_clean: str,
        extras: dict[str, Any] | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist enriched detail without marking the announcement as UPDATED."""
        categories_json = json.dumps(
            list(categories or []),
            ensure_ascii=False,
            sort_keys=True,
        )
        extras_json = json.dumps(
            extras or {},
            ensure_ascii=False,
            sort_keys=True,
        )
        metadata_json = json.dumps(
            metadata or {},
            ensure_ascii=False,
            sort_keys=True,
        )

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE announcements
                SET detail_status = 'ENRICHED',
                    detail_fetched_at = ?,
                    detail_error = NULL,
                    detail_reference = ?,
                    detail_title = ?,
                    detail_language = ?,
                    detail_published_at = ?,
                    detail_page = ?,
                    detail_file_ref = ?,
                    detail_categories_json = ?,
                    detail_article_text_raw = ?,
                    detail_article_text_clean = ?,
                    detail_extras_json = ?,
                    detail_metadata_json = ?
                WHERE source = 'legaltech'
                  AND source_id = ?
                """,
                (
                    self._now(),
                    reference,
                    title,
                    language,
                    published_at,
                    page,
                    file_ref,
                    categories_json,
                    article_text_raw,
                    article_text_clean,
                    extras_json,
                    metadata_json,
                    source_id,
                ),
            )

    def mark_announcement_detail_status(
        self,
        source_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        allowed = {"NOT_FETCHED", "ENRICHED", "SKIPPED", "FAILED"}
        normalized = status.upper().strip()
        if normalized not in allowed:
            raise ValueError(f"Statut détail invalide : {status}")

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE announcements
                SET detail_status = ?,
                    detail_fetched_at = ?,
                    detail_error = ?
                WHERE source = 'legaltech'
                  AND source_id = ?
                """,
                (
                    normalized,
                    self._now(),
                    str(error or "")[:2000] or None,
                    source_id,
                ),
            )

    def update_announcement_pdf_status(
        self,
        source_id: str,
        status: str,
        filename: str | None = None,
    ) -> None:
        allowed = {
            "NOT_REQUESTED",
            "COLLECTED",
            "DUPLICATE",
            "TOKEN_EXPIRED",
            "UNAVAILABLE",
            "FAILED",
        }
        normalized = status.upper().strip()

        if normalized not in allowed:
            raise ValueError(f"Statut PDF invalide : {status}")

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE announcements
                SET pdf_status = ?,
                    pdf_filename = COALESCE(?, pdf_filename)
                WHERE source = 'legaltech'
                  AND source_id = ?
                """,
                (normalized, filename, source_id),
            )

    def recent_announcements(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM announcements
                ORDER BY
                    CASE
                        WHEN published_at IS NULL OR published_at = '' THEN 1
                        ELSE 0
                    END,
                    published_at DESC,
                    last_seen_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for source_key, target_key, fallback in (
                ("categories_json", "categories", []),
                ("metadata_json", "metadata", {}),
                ("detail_categories_json", "detail_categories", []),
                ("detail_extras_json", "detail_extras", {}),
                ("detail_metadata_json", "detail_metadata", {}),
            ):
                try:
                    item[target_key] = json.loads(item.get(source_key) or "")
                except (TypeError, json.JSONDecodeError):
                    item[target_key] = fallback
            result.append(item)

        return result

    # -----------------------------------------------------------------
    # Existing PDF registry — preserved for pdf_library_service.py
    # -----------------------------------------------------------------

    def has_source_id(self, source_id: str | None) -> bool:
        if not source_id:
            return False

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM documents
                WHERE source = 'legaltech'
                  AND source_id = ?
                LIMIT 1
                """,
                (source_id,),
            ).fetchone()

        return row is not None

    def has_sha256(self, digest: str | None) -> bool:
        if not digest:
            return False

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM documents
                WHERE sha256 = ?
                LIMIT 1
                """,
                (digest,),
            ).fetchone()

        return row is not None

    def register(
        self,
        *,
        source_id: str | None,
        reference: str | None,
        source_url: str | None,
        download_url: str | None,
        filename: str,
        local_path: str | Path,
        sha256: str,
        size_bytes: int,
        published_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO documents (
                        source,
                        source_id,
                        reference,
                        source_url,
                        download_url,
                        filename,
                        local_path,
                        sha256,
                        size_bytes,
                        published_at,
                        collected_at,
                        processing_status,
                        metadata_json
                    )
                    VALUES (
                        'legaltech',
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        'COLLECTED',
                        ?
                    )
                    """,
                    (
                        source_id,
                        reference,
                        source_url,
                        download_url,
                        filename,
                        str(Path(local_path)),
                        sha256,
                        int(size_bytes),
                        published_at,
                        self._now(),
                        json.dumps(
                            metadata or {},
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def update_status(self, sha256: str, status: str) -> None:
        allowed_statuses = {
            "COLLECTED",
            "PROCESSING",
            "ANALYZED",
            "FAILED",
            "ARCHIVED",
        }
        normalized = status.upper().strip()

        if normalized not in allowed_statuses:
            raise ValueError(f"Statut invalide : {status}")

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET processing_status = ?
                WHERE sha256 = ?
                """,
                (normalized, sha256),
            )

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM documents
                ORDER BY collected_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()

        return [dict(row) for row in rows]
