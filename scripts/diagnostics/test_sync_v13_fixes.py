"""Offline smoke tests for LegalTech sync v13 fixes."""

from __future__ import annotations

from pathlib import Path
import tempfile

from modules.legaltech_registry import LegalTechRegistry
from modules.legaltech_sync_service import clean_article_text


def main() -> None:
    assert clean_article_text("<mark>JORT</mark>") == "JORT"
    assert (
        clean_article_text("[' cette annonce au <mark>JORT</mark>.']")
        == "cette annonce au JORT."
    )
    assert clean_article_text('["Texte 1", "Texte 2"]') == "Texte 1\nTexte 2"

    with tempfile.TemporaryDirectory() as tmp:
        registry = LegalTechRegistry(Path(tmp) / "registry.sqlite3")

        first = registry.upsert_announcement(
            source_id="demo-1",
            doc_id="doc-1",
            reference="REF-1",
            title="Titre initial",
            source_name="jort",
            language="fr",
            published_at="2026-07-24T23:33:04+00:00",
            page=13,
            file_ref="file-1",
            categories=[],
            article_text_raw="[' texte']",
            article_text_clean="[' texte']",
            content_sha256="old-hash",
            metadata={},
        )
        assert first == "NEW"

        cosmetic = registry.upsert_announcement(
            source_id="demo-1",
            doc_id="doc-1",
            reference="REF-1",
            title="Titre reformatté",
            source_name="JORT",
            language="fr",
            published_at="2026-07-24T23:33:04Z",
            page=13,
            file_ref="other-label",
            categories=["Catégorie ajoutée"],
            article_text_raw='[" texte"]',
            article_text_clean="texte",
            content_sha256="new-hash",
            metadata={"cosmetic": True},
        )
        assert cosmetic == "KNOWN"

        real_change = registry.upsert_announcement(
            source_id="demo-1",
            doc_id="doc-1",
            reference="REF-1",
            title="Titre reformatté",
            source_name="JORT",
            language="fr",
            published_at="2026-07-24T23:33:04Z",
            page=13,
            file_ref="other-label",
            categories=["Catégorie ajoutée"],
            article_text_raw="texte juridiquement modifié",
            article_text_clean="texte juridiquement modifié",
            content_sha256="third-hash",
            metadata={},
        )
        assert real_change == "UPDATED"

    print("LEGALTECH SYNC v13 FIXES — TEST HORS LIGNE OK")
    print("Nettoyage Résumé : OK")
    print("Déduplication sémantique : OK")
    print("Vraie mise à jour : OK")


if __name__ == "__main__":
    main()
