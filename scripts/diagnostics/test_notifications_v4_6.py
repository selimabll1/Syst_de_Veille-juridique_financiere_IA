"""Functional v4.6 test for first 3 notifications.

This performs normal LegalTech clicks. The tested notifications may therefore
be marked read, exactly as with manual clicks.

No Voir-plus details and no PDFs are opened in this diagnostic.
"""

from modules.legaltech_browser_collector import LegalTechBrowserCollector
from modules.legaltech_notifications_collector import (
    DEFAULT_NOTIFICATIONS_URL,
    LegalTechNotificationsCollector,
)

def main():
    with LegalTechBrowserCollector(
        headless=False,
        slow_mo_ms=120,
    ) as browser:
        browser.ensure_authenticated(DEFAULT_NOTIFICATIONS_URL)
        collector = LegalTechNotificationsCollector(browser)

        rows = collector._notification_candidates()[:3]
        items = [
            collector._parse_notification(
                row["text"],
                1,
                notification_index=index,
            )
            for index, row in enumerate(rows)
        ]

        for notif in items:
            print(
                f"\n=== {notif.company_or_query} "
                f"· {notif.notification_date} ==="
            )

            changed, panel = collector._activate_notification(
                notif,
                retries=2,
            )

            print("panel_changed:", changed)
            print(
                "voir_plus_count:",
                collector._visible_see_more_count(),
            )
            print("panel_total:", collector._panel_total())

            cards = collector._current_alerts(
                notif,
                1,
            )
            print("cards:", len(cards))

            for index, card in enumerate(cards, 1):
                print(
                    f"\nCARD {index}"
                    f"\nsource={card.source_label or card.source}"
                    f"\ndate={card.card_date or '-'}"
                    f"\ntitle={card.card_title or '-'}"
                    f"\nsummary={(card.card_summary or '-')[:300]}"
                )

            if changed and not cards:
                collector._save_panel_debug(
                    notif.company_or_query
                )
                print(
                    "DEBUG SAVED:",
                    f"data/legaltech_debug/{notif.company_or_query}_panel.*",
                )

        input("\nAppuyez sur Entrée pour fermer le navigateur...")

if __name__ == "__main__":
    main()
