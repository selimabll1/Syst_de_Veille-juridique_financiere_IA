import argparse
import json
from pathlib import Path

from modules.legaltech_browser_collector import (
    AuthenticationRequired,
    LegalTechBrowserCollector,
)
from modules.legaltech_detail_parser import backfill_database
from modules.legaltech_notifications_network_collector import (
    DEFAULT_V5_DB,
    NetworkFirstNotificationsCollector,
)
from modules.legaltech_notifications_collector import summary_to_dict
from modules.legaltech_remote_watcher import reconcile_local


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-notifications",
        type=int,
        default=0,
        help="0 = toutes les cartes de notification LegalTech",
    )
    parser.add_argument(
        "--alert-pages",
        type=int,
        default=0,
        help="0 = toutes les pages de résultats jusqu'au total API",
    )
    parser.add_argument("--download-pdf", action="store_true")
    parser.add_argument("--reset-db", action="store_true")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    if args.reset_db:
        for path in (
            DEFAULT_V5_DB,
            Path(str(DEFAULT_V5_DB) + "-wal"),
            Path(str(DEFAULT_V5_DB) + "-shm"),
        ):
            path.unlink(missing_ok=True)
        print("Base v5 réinitialisée.")

    try:
        with LegalTechBrowserCollector(
            headless=args.headless,
            slow_mo_ms=80 if not args.headless else 0,
        ) as browser:
            collector = NetworkFirstNotificationsCollector(browser)
            summary = collector.sync(
                max_notifications=args.max_notifications,
                max_alert_pages=args.alert_pages,
                download_documents=args.download_pdf,
                safe_read_state=False,
            )

            parser_summary = backfill_database(DEFAULT_V5_DB)
            cleared = reconcile_local()

            print("\nSYNC V29 ALL-PAGES TERMINÉE")
            print(json.dumps(summary_to_dict(summary), indent=2, ensure_ascii=False))
            print("Normalisation détails:", json.dumps(parser_summary, ensure_ascii=False))
            print("Notifications distantes maintenant synchronisées:", cleared)
            print("Base:", DEFAULT_V5_DB)

    except AuthenticationRequired as exc:
        print("AUTH_REQUIRED")
        print(exc)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
