"""Offline tests for URL parsing, RNE extraction and SQLite dedup."""

from __future__ import annotations

from pathlib import Path
import tempfile

from modules.legaltech_browser_collector import (
    BrowserRegistry,
    BrowserResult,
    parse_article_url,
    parse_rne_visible_fields,
)


def main() -> None:
    rne = parse_article_url(
        "https://annonces.legaltech.tn/article/rne/"
        "rne-1251630-202534051?docId=rne-1251630"
    )
    assert rne.source == "rne"
    assert rne.article_id == "rne-1251630-202534051"
    assert rne.doc_id == "rne-1251630"

    jort = parse_article_url(
        "/article/jort/jort-2025-36-fr-2025r00761sodb3"
        "?docId=jort-2025-36-fr"
    )
    assert jort.source == "jort"
    assert jort.doc_id == "jort-2025-36-fr"

    fields = parse_rne_visible_fields(
        """
        Dénomination : BIOLEX SA
        Identifiant unique : 1534107K
        Capital : 7 700 000
        Type de publication : MODIFICATION
        Activité : Industrie
        Adresse : Tunis
        Responsable : Exemple Responsable
        Qualité du responsable : Gérant
        """
    )
    assert fields["denomination"] == "BIOLEX SA"
    assert fields["identifiant_unique"] == "1534107K"
    assert fields["capital"] == "7 700 000"
    assert fields["type_publication"] == "MODIFICATION"

    with tempfile.TemporaryDirectory() as tmp:
        registry = BrowserRegistry(Path(tmp) / "browser.sqlite3")
        result = BrowserResult(
            result_key=rne.result_key,
            alert_url="https://annonces.legaltech.tn/alert/demo",
            source=rne.source,
            article_id=rne.article_id,
            doc_id=rne.doc_id,
            article_url=rne.article_url,
            list_page=1,
            list_text="RNE Publication demo",
        )
        assert registry.upsert_result(result) == "NEW"
        assert registry.upsert_result(result) == "KNOWN"

    print("LEGALTECH BROWSER COLLECTOR v1 — TEST HORS LIGNE OK")
    print("Routes article : OK")
    print("Extraction RNE : OK")
    print("Déduplication SQLite : OK")


if __name__ == "__main__":
    main()
