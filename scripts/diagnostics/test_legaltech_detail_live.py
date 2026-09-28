"""Read-only live test for the LegalTech article-detail endpoint.

The script prints only business fields/lengths. It does not print cookies,
tokens or complete raw responses.
"""

from __future__ import annotations

from modules.legaltech_api_client_v2 import LegalTechAPIClient


def main() -> None:
    client = LegalTechAPIClient.from_files(
        "config/legaltech_collection.local.json",
        "secrets/legaltech_session.local.json",
    )
    articles, _ = client.fetch_articles(limit=5)

    print("Articles reçus :", len(articles))
    successes = 0
    failures = 0

    for index, article in enumerate(articles, start=1):
        print("\\n--- Article", index, "---")
        print("source :", article.source or "-")
        print("source_id présent :", bool(article.source_id))
        print("doc_id présent :", bool(article.doc_id))

        try:
            detail, _ = client.fetch_article_detail(article)
            successes += 1
            print("DETAIL OK")
            print("référence :", detail.reference or "-")
            print("titre :", detail.title or "-")
            print("caractères :", len(detail.article_text or ""))
            print("extras :", ", ".join(sorted(detail.extras.keys())) or "-")
        except Exception as exc:
            failures += 1
            print("DETAIL INDISPONIBLE :", exc)

    print("\\nRésumé :")
    print("détails OK :", successes)
    print("détails indisponibles :", failures)


if __name__ == "__main__":
    main()
