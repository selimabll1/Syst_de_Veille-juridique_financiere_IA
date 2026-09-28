"""Click first 3 notifications and inspect visible alert cards.

Normal LegalTech clicks are used. They may mark the tested notifications as
read, just like manual clicks in the website.

No Voir plus details and no PDFs in this diagnostic.
"""

from modules.legaltech_browser_collector import LegalTechBrowserCollector
from modules.legaltech_notifications_collector import (
    DEFAULT_NOTIFICATIONS_URL,
    LegalTechNotificationsCollector,
)

def main():
    with LegalTechBrowserCollector(
        headless=False,
        slow_mo_ms=150,
    ) as browser:
        browser.ensure_authenticated(DEFAULT_NOTIFICATIONS_URL)
        collector = LegalTechNotificationsCollector(browser)

        candidates = collector._notification_candidates()[:3]
        items = [
            collector._parse_notification(
                row["text"],
                1,
                notification_index=index,
            )
            for index, row in enumerate(candidates)
        ]

        for notif in items:
            print(
                f"\nNOTIFICATION: {notif.company_or_query} "
                f"· {notif.notification_date}"
            )

            changed, _ = collector._activate_notification(
                notif,
                retries=2,
            )
            print("panel_changed:", changed)
            print(
                "voir_plus_count:",
                collector._visible_see_more_count(),
            )

            cards = collector._current_alerts(notif, 1)
            print("cards:", len(cards))
            print("panel_total:", collector._panel_total())

            for card in cards[:10]:
                print(
                    " -",
                    card.source_label or card.source,
                    "|",
                    card.card_date or "-",
                    "|",
                    card.card_title or "-",
                    "|",
                    (card.card_summary or "")[:120],
                )

            if changed and not cards:
                collector._save_panel_debug(
                    notif.company_or_query
                )

        input("\nAppuyez sur Entrée pour fermer le navigateur...")

if __name__ == "__main__":
    main()
