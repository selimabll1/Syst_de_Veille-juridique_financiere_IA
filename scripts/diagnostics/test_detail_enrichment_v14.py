"""Offline checks for the LegalTech detail-enrichment layer."""

from __future__ import annotations

from pathlib import Path
import tempfile

from modules.legaltech_registry import LegalTechRegistry


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        registry = LegalTechRegistry(Path(tmp) / "registry.sqlite3")

        status = registry.upsert_announcement(
            source_id="rne-demo-article",
            doc_id="rne-demo",
            reference="MASKED",
            title="RNE - résultat de recherche",
            source_name="rne",
            language="fr",
            published_at="2024-07-15T00:00:00+00:00",
            page=None,
            file_ref="",
            categories=[],
            article_text_raw="résumé court",
            article_text_clean="résumé court",
            content_sha256="demo-hash",
            metadata={},
        )
        assert status == "NEW"

        registry.save_announcement_detail(
            source_id="rne-demo-article",
            reference="202478127",
            title="RNE - Publication N° 202478127",
            language="fr",
            published_at="2024-07-15T00:00:00+00:00",
            page=None,
            file_ref="output/rne/demo.pdf",
            categories=[],
            article_text_raw="texte RNE détaillé",
            article_text_clean="texte RNE détaillé",
            extras={
                "identifiantUnique": "1534107K",
                "capital": 7700000,
                "typePublication": "MODIFICATION",
            },
            metadata={"source": "rne"},
        )

        row = registry.recent_announcements(limit=1)[0]
        assert row["detail_status"] == "ENRICHED"
        assert row["detail_reference"] == "202478127"
        assert row["detail_extras"]["identifiantUnique"] == "1534107K"
        assert row["detail_extras"]["capital"] == 7700000

    print("LEGALTECH DETAIL ENRICHMENT v14 — TEST HORS LIGNE OK")
    print("Migration SQLite : OK")
    print("Persistance détail : OK")
    print("Extras RNE : OK")


if __name__ == "__main__":
    main()
