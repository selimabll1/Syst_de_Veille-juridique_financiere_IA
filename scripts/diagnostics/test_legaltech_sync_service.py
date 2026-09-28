"""Tests hors ligne de l'intégration Streamlit / LegalTech."""

from __future__ import annotations

from pathlib import Path
import tempfile

from modules.legaltech_api_client_v2 import LegalTechArticle
from modules.legaltech_registry import LegalTechRegistry
from modules.legaltech_sync_service import (
    LEGALTECH_SYNC_SERVICE_VERSION,
    _collection_filename,
)


def main() -> None:
    article_a = LegalTechArticle(
        source_id="source-id-a",
        doc_id="doc-a",
        reference="REF/001",
        title="Annonce A",
        language="fr",
        article_text="Texte",
        published_at="2026-07-21T00:00:00Z",
        source="JORT",
        file="a.pdf",
        page=1,
        raw_hit={},
    )
    article_b = LegalTechArticle(
        source_id="source-id-b",
        doc_id="doc-b",
        reference="REF/001",
        title="Annonce B",
        language="ar",
        article_text="Texte",
        published_at="2026-07-21T00:00:01Z",
        source="JORT",
        file="b.pdf",
        page=2,
        raw_hit={},
    )

    filename_a = _collection_filename(article_a)
    filename_b = _collection_filename(article_b)

    assert filename_a.endswith(".pdf")
    assert filename_b.endswith(".pdf")
    assert filename_a != filename_b
    assert "/" not in filename_a
    assert "\\" not in filename_a

    with tempfile.TemporaryDirectory() as directory:
        registry = LegalTechRegistry(Path(directory) / "registry.sqlite3")
        inserted = registry.register(
            source_id="source-id-a",
            reference="REF-001",
            source_url=None,
            download_url="https://example.invalid/pdf",
            filename=filename_a,
            local_path=Path(directory) / filename_a,
            sha256="a" * 64,
            size_bytes=100,
            published_at="2026-07-21T00:00:00Z",
            metadata={"test": True},
        )
        assert inserted is True
        assert registry.has_source_id("source-id-a") is True
        assert registry.has_sha256("a" * 64) is True

    print("LEGALTECH SYNC SERVICE — TEST HORS LIGNE OK")
    print("Service :", LEGALTECH_SYNC_SERVICE_VERSION)
    print("Noms de fichiers sans collision : OK")
    print("Registre et déduplication : OK")


if __name__ == "__main__":
    main()
