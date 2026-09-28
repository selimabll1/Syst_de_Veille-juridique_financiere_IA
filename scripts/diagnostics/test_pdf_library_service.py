"""Offline validation for the professional PDF document center."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

from pypdf import PdfWriter

from modules.pdf_library_service import (
    PDF_LIBRARY_SERVICE_VERSION,
    PDFLibraryService,
    filter_and_sort_records,
)


def create_pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    with path.open("wb") as handle:
        writer.write(handle)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        active = root / "pdf_raw"
        archive = root / "pdf_archive"
        active.mkdir()
        archive.mkdir()
        database = root / "pdf_library.sqlite3"
        legaltech_database = root / "legaltech_registry.sqlite3"

        create_pdf(active / "manual.pdf", 2)
        create_pdf(active / "legaltech.pdf", 3)

        connection = sqlite3.connect(legaltech_database)
        connection.execute(
            """
            CREATE TABLE documents (
                filename TEXT,
                reference TEXT,
                sha256 TEXT,
                published_at TEXT,
                collected_at TEXT,
                processing_status TEXT,
                metadata_json TEXT,
                source_id TEXT,
                local_path TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO documents VALUES (
                'legaltech.pdf', 'REF-001', 'abc123',
                '2026-07-21T09:00:00+00:00',
                '2026-07-21T10:00:00+00:00',
                'COLLECTED',
                '{"title":"Annonce test","language":"fr","source":"JORT"}',
                'source-1', 'data/pdf_raw/legaltech.pdf'
            )
            """
        )
        connection.commit()
        connection.close()

        service = PDFLibraryService(
            database_path=database,
            legaltech_database_path=legaltech_database,
            active_dir=active,
            archive_dir=archive,
        )

        records = service.list_records("active")
        assert len(records) == 2
        legaltech_record = next(item for item in records if item.filename == "legaltech.pdf")
        manual_record = next(item for item in records if item.filename == "manual.pdf")
        assert legaltech_record.source_type == "LegalTech"
        assert legaltech_record.reference == "REF-001"
        assert legaltech_record.page_count == 3
        assert manual_record.source_type == "Import manuel"
        assert manual_record.page_count == 2
        assert len(manual_record.sha256) == 64

        service.mark_viewed("legaltech.pdf")
        viewed = service.get("legaltech.pdf")
        assert viewed is not None and viewed.viewed is True
        assert viewed.view_count == 1

        consulted = filter_and_sort_records(
            service.list_records("active"),
            status="Consultés",
        )
        assert [item.filename for item in consulted] == ["legaltech.pdf"]

        service.archive("manual.pdf")
        assert service.get("manual.pdf", "active") is None
        assert service.get("manual.pdf", "archived") is not None

        service.restore("manual.pdf")
        assert service.get("manual.pdf", "active") is not None

        service.archive("manual.pdf")
        service.delete_archived("manual.pdf")
        assert not (archive / "manual.pdf").exists()

        summary = service.summary()
        assert summary.total_active == 1
        assert summary.viewed == 1
        assert summary.legaltech == 1

    print("PDF DOCUMENT CENTER — TEST HORS LIGNE OK")
    print("Service :", PDF_LIBRARY_SERVICE_VERSION)
    print("Indexation et métadonnées : OK")
    print("Historique de consultation : OK")
    print("Archivage, restauration et suppression : OK")


if __name__ == "__main__":
    main()
