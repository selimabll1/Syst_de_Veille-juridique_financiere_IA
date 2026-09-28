"""Small read-only browser test on one LegalTech alert.

Example:
    python -m scripts.test_legaltech_browser \
        --alert-url "https://annonces.legaltech.tn/alert/<ID>"
"""

from __future__ import annotations

import argparse

from modules.legaltech_browser_collector import (
    AuthenticationRequired,
    LegalTechBrowserCollector,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alert-url", required=True)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--details", type=int, default=1)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Utiliser uniquement après avoir créé le profil connecté.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        with LegalTechBrowserCollector(
            headless=args.headless,
            slow_mo_ms=150 if not args.headless else 0,
        ) as collector:
            collector.ensure_authenticated(args.alert_url)

            results, pages = collector.collect_alert_results(
                args.alert_url,
                max_pages=args.max_pages,
            )

            print("BROWSER SESSION : OK")
            print("Pages parcourues :", pages)
            print("Résultats détectés :", len(results))

            for index, result in enumerate(results[:10], start=1):
                print(
                    f"{index}. source={result.source} "
                    f"article_id={result.article_id} "
                    f"doc_id={'oui' if result.doc_id else 'non'}"
                )

            for result in results[: max(0, args.details)]:
                print("\nDETAIL :", result.source, result.article_id)
                detail = collector.collect_detail(result)
                print("Titre :", detail.title[:180] or "-")
                print("Caractères visibles :", len(detail.visible_text))
                print(
                    "Champs structurés :",
                    ", ".join(sorted(detail.source_fields.keys())) or "-",
                )
            input("\nBrowser kept open. Press Enter to close...")

    except AuthenticationRequired as exc:
        print("AUTH_REQUIRED")
        print(exc)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
