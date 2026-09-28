"""Persistent document-library service for the LegalTech Streamlit app.

The service indexes active and archived PDFs, enriches them with metadata from
``data/legaltech_registry.sqlite3``, records consultation activity, and safely
archives/restores documents without exposing LegalTech secrets.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Iterable, Iterator

from pypdf import PdfReader


PDF_LIBRARY_SERVICE_VERSION = "pdf_library_service_v1"

DEFAULT_LIBRARY_DB = Path("data/pdf_library.sqlite3")
DEFAULT_LEGALTECH_DB = Path("data/legaltech_registry.sqlite3")
DEFAULT_ACTIVE_DIR = Path("data/pdf_raw")
DEFAULT_ARCHIVE_DIR = Path("data/pdf_archive")


@dataclass(frozen=True)
class PDFRecord:
    filename: str
    path: str
    location: str
    size_bytes: int
    size_label: str
    modified_at: str
    page_count: int | None
    sha256: str
    source_type: str
    source_name: str
    reference: str
    title: str
    language: str
    published_at: str
    collected_at: str
    processing_status: str
    viewed: bool
    first_viewed_at: str
    last_viewed_at: str
    view_count: int
    archived_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LibrarySummary:
    total_active: int
    viewed: int
    unviewed: int
    legaltech: int
    manual: int
    archived: int


class PDFLibraryError(RuntimeError):
    pass


class PDFLibraryService:
    def __init__(
        self,
        database_path: str | Path = DEFAULT_LIBRARY_DB,
        legaltech_database_path: str | Path = DEFAULT_LEGALTECH_DB,
        active_dir: str | Path = DEFAULT_ACTIVE_DIR,
        archive_dir: str | Path = DEFAULT_ARCHIVE_DIR,
    ) -> None:
        self.database_path = Path(database_path)
        self.legaltech_database_path = Path(legaltech_database_path)
        self.active_dir = Path(active_dir)
        self.archive_dir = Path(archive_dir)

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
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

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS pdf_activity (
                    filename TEXT PRIMARY KEY,
                    first_seen_at TEXT NOT NULL,
                    first_viewed_at TEXT,
                    last_viewed_at TEXT,
                    view_count INTEGER NOT NULL DEFAULT 0,
                    archived_at TEXT,
                    last_known_path TEXT NOT NULL,
                    last_known_location TEXT NOT NULL DEFAULT 'active',
                    cached_size_bytes INTEGER,
                    cached_mtime_ns INTEGER,
                    cached_page_count INTEGER,
                    cached_sha256 TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_pdf_activity_last_viewed
                    ON pdf_activity(last_viewed_at);
                """
            )

            existing_columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(pdf_activity)"
                ).fetchall()
            }
            migrations = {
                "cached_size_bytes": "INTEGER",
                "cached_mtime_ns": "INTEGER",
                "cached_page_count": "INTEGER",
                "cached_sha256": "TEXT",
            }
            for column, sql_type in migrations.items():
                if column not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE pdf_activity ADD COLUMN {column} {sql_type}"
                    )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        value = float(max(0, size_bytes))
        units = ["o", "Ko", "Mo", "Go"]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "o":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{size_bytes} o"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _page_count(path: Path) -> int | None:
        try:
            return len(PdfReader(str(path), strict=False).pages)
        except Exception:
            return None

    def _ensure_activity(self, path: Path, location: str) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pdf_activity (
                    filename,
                    first_seen_at,
                    last_known_path,
                    last_known_location
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(filename) DO UPDATE SET
                    last_known_path = excluded.last_known_path,
                    last_known_location = excluded.last_known_location,
                    archived_at = CASE
                        WHEN excluded.last_known_location = 'active' THEN NULL
                        ELSE pdf_activity.archived_at
                    END
                """,
                (path.name, now, str(path), location),
            )

    def _activity_map(self) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM pdf_activity").fetchall()
        return {str(row["filename"]): dict(row) for row in rows}

    def _legaltech_map(self) -> dict[str, dict[str, Any]]:
        if not self.legaltech_database_path.exists():
            return {}

        try:
            connection = sqlite3.connect(self.legaltech_database_path)
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT filename, reference, sha256, published_at,
                       collected_at, processing_status, metadata_json,
                       source_id, local_path
                FROM documents
                ORDER BY collected_at DESC
                """
            ).fetchall()
            connection.close()
        except sqlite3.Error:
            return {}

        mapping: dict[str, dict[str, Any]] = {}
        for row in rows:
            record = dict(row)
            try:
                record["metadata"] = json.loads(
                    record.get("metadata_json") or "{}"
                )
            except json.JSONDecodeError:
                record["metadata"] = {}
            mapping.setdefault(str(record.get("filename") or ""), record)
        return mapping

    def synchronize_index(self) -> None:
        for path in sorted(self.active_dir.glob("*.pdf")):
            if path.is_file():
                self._ensure_activity(path, "active")
        for path in sorted(self.archive_dir.glob("*.pdf")):
            if path.is_file():
                self._ensure_activity(path, "archived")

    def _technical_metadata(
        self,
        path: Path,
        activity: dict[str, Any],
    ) -> tuple[int | None, str]:
        stat = path.stat()
        same_version = (
            int(activity.get("cached_size_bytes") or -1) == stat.st_size
            and int(activity.get("cached_mtime_ns") or -1) == stat.st_mtime_ns
        )
        cached_sha = str(activity.get("cached_sha256") or "")
        cached_pages = activity.get("cached_page_count")

        if same_version and cached_sha:
            page_count = (
                int(cached_pages) if cached_pages is not None else None
            )
            return page_count, cached_sha

        page_count = self._page_count(path)
        digest = self._sha256(path)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE pdf_activity
                SET cached_size_bytes = ?,
                    cached_mtime_ns = ?,
                    cached_page_count = ?,
                    cached_sha256 = ?
                WHERE filename = ?
                """,
                (
                    stat.st_size,
                    stat.st_mtime_ns,
                    page_count,
                    digest,
                    path.name,
                ),
            )
        return page_count, digest

    def _record_for(
        self,
        path: Path,
        location: str,
        activity: dict[str, Any],
        legaltech: dict[str, Any] | None,
    ) -> PDFRecord:
        stat = path.stat()
        legaltech = legaltech or {}
        metadata = legaltech.get("metadata") or {}

        source_type = "LegalTech" if legaltech else "Import manuel"
        source_name = str(metadata.get("source") or source_type)
        cached_pages, cached_sha = self._technical_metadata(path, activity)
        sha = str(legaltech.get("sha256") or cached_sha)

        return PDFRecord(
            filename=path.name,
            path=str(path),
            location=location,
            size_bytes=stat.st_size,
            size_label=self._human_size(stat.st_size),
            modified_at=datetime.fromtimestamp(
                stat.st_mtime,
                tz=timezone.utc,
            ).isoformat(),
            page_count=cached_pages,
            sha256=sha,
            source_type=source_type,
            source_name=source_name,
            reference=str(legaltech.get("reference") or ""),
            title=str(metadata.get("title") or path.stem),
            language=str(metadata.get("language") or ""),
            published_at=str(legaltech.get("published_at") or ""),
            collected_at=str(legaltech.get("collected_at") or ""),
            processing_status=str(
                legaltech.get("processing_status") or "AVAILABLE"
            ),
            viewed=int(activity.get("view_count") or 0) > 0,
            first_viewed_at=str(activity.get("first_viewed_at") or ""),
            last_viewed_at=str(activity.get("last_viewed_at") or ""),
            view_count=int(activity.get("view_count") or 0),
            archived_at=str(activity.get("archived_at") or ""),
            metadata=metadata,
        )

    def list_records(self, location: str = "active") -> list[PDFRecord]:
        if location not in {"active", "archived", "all"}:
            raise ValueError("location doit être active, archived ou all")

        self.synchronize_index()
        activity = self._activity_map()
        legaltech = self._legaltech_map()

        paths: list[tuple[Path, str]] = []
        if location in {"active", "all"}:
            paths.extend((path, "active") for path in self.active_dir.glob("*.pdf"))
        if location in {"archived", "all"}:
            paths.extend((path, "archived") for path in self.archive_dir.glob("*.pdf"))

        records = [
            self._record_for(
                path,
                item_location,
                activity.get(path.name, {}),
                legaltech.get(path.name),
            )
            for path, item_location in paths
            if path.is_file()
        ]
        return sorted(records, key=lambda item: item.modified_at, reverse=True)

    def get(self, filename: str, location: str = "active") -> PDFRecord | None:
        for record in self.list_records(location=location):
            if record.filename == filename:
                return record
        return None

    def mark_viewed(self, filename: str) -> None:
        path = self._safe_existing_path(filename, allow_archived=True)
        location = "archived" if path.parent.resolve() == self.archive_dir.resolve() else "active"
        self._ensure_activity(path, location)
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE pdf_activity
                SET first_viewed_at = COALESCE(first_viewed_at, ?),
                    last_viewed_at = ?,
                    view_count = view_count + 1
                WHERE filename = ?
                """,
                (now, now, filename),
            )

    def mark_unviewed(self, filename: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE pdf_activity
                SET first_viewed_at = NULL,
                    last_viewed_at = NULL,
                    view_count = 0
                WHERE filename = ?
                """,
                (filename,),
            )

    def _safe_existing_path(
        self,
        filename: str,
        *,
        allow_archived: bool = False,
    ) -> Path:
        if Path(filename).name != filename:
            raise PDFLibraryError("Nom de fichier non autorisé.")

        candidates = [self.active_dir / filename]
        if allow_archived:
            candidates.append(self.archive_dir / filename)

        roots = [self.active_dir.resolve(), self.archive_dir.resolve()]
        for candidate in candidates:
            resolved = candidate.resolve()
            if any(root == resolved.parent for root in roots) and resolved.exists():
                return resolved
        raise FileNotFoundError(filename)

    def archive(self, filename: str) -> Path:
        source = self._safe_existing_path(filename)
        destination = self.archive_dir / filename
        if destination.exists():
            raise PDFLibraryError(
                "Un document portant le même nom existe déjà dans les archives."
            )
        shutil.move(str(source), str(destination))
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE pdf_activity
                SET archived_at = ?,
                    last_known_path = ?,
                    last_known_location = 'archived'
                WHERE filename = ?
                """,
                (now, str(destination), filename),
            )
        return destination

    def restore(self, filename: str) -> Path:
        source = self._safe_existing_path(filename, allow_archived=True)
        if source.parent.resolve() != self.archive_dir.resolve():
            raise PDFLibraryError("Le document n'est pas archivé.")
        destination = self.active_dir / filename
        if destination.exists():
            raise PDFLibraryError(
                "Un document portant le même nom existe déjà dans la bibliothèque."
            )
        shutil.move(str(source), str(destination))
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE pdf_activity
                SET archived_at = NULL,
                    last_known_path = ?,
                    last_known_location = 'active'
                WHERE filename = ?
                """,
                (str(destination), filename),
            )
        return destination

    def delete_archived(self, filename: str) -> None:
        path = self._safe_existing_path(filename, allow_archived=True)
        if path.parent.resolve() != self.archive_dir.resolve():
            raise PDFLibraryError(
                "Seuls les documents archivés peuvent être supprimés définitivement."
            )
        path.unlink()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM pdf_activity WHERE filename = ?",
                (filename,),
            )

    def summary(self) -> LibrarySummary:
        active = self.list_records("active")
        archived = self.list_records("archived")
        viewed = sum(item.viewed for item in active)
        legaltech = sum(item.source_type == "LegalTech" for item in active)
        return LibrarySummary(
            total_active=len(active),
            viewed=viewed,
            unviewed=len(active) - viewed,
            legaltech=legaltech,
            manual=len(active) - legaltech,
            archived=len(archived),
        )


def filter_and_sort_records(
    records: Iterable[PDFRecord],
    *,
    search: str = "",
    status: str = "Tous",
    source: str = "Toutes",
    sort_by: str = "Plus récents",
) -> list[PDFRecord]:
    result = list(records)
    needle = search.strip().casefold()

    if needle:
        result = [
            item
            for item in result
            if needle
            in " ".join(
                [
                    item.filename,
                    item.reference,
                    item.title,
                    item.source_name,
                    item.language,
                ]
            ).casefold()
        ]

    if status == "Consultés":
        result = [item for item in result if item.viewed]
    elif status == "Non consultés":
        result = [item for item in result if not item.viewed]

    if source == "LegalTech":
        result = [item for item in result if item.source_type == "LegalTech"]
    elif source == "Import manuel":
        result = [item for item in result if item.source_type == "Import manuel"]

    sorters = {
        "Plus récents": (lambda item: item.modified_at, True),
        "Plus anciens": (lambda item: item.modified_at, False),
        "Nom A–Z": (lambda item: item.filename.casefold(), False),
        "Nom Z–A": (lambda item: item.filename.casefold(), True),
        "Plus volumineux": (lambda item: item.size_bytes, True),
        "Plus consultés": (lambda item: item.view_count, True),
    }
    key, reverse = sorters.get(sort_by, sorters["Plus récents"])
    return sorted(result, key=key, reverse=reverse)
