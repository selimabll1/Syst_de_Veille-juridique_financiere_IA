"""Functional test: click first 3 notifications normally and inspect panels.

WARNING:
This uses LegalTech's normal click behavior. If LegalTech marks notifications
as read on click, the first 3 notifications may be marked read.

No detail pages and no downloads are opened in this diagnostic.
"""

from modules.legaltech_browser_collector import LegalTechBrowserCollector
from modules.legaltech_notifications_collector import (
    DEFAULT_NOTIFICATIONS_URL,
    LegalTechNotificationsCollector,
)

def main():
    with LegalTechBrowserCollector(headless=False, slow_mo_ms=160) as browser:
        browser.ensure_authenticated(DEFAULT_NOTIFICATIONS_URL)
        collector = LegalTechNotificationsCollector(browser)

        rows = collector._notification_candidates()[:3]
        print("Notifications testées :", len(rows))

        for index, row in enumerate(rows):
            notif = collector._parse_notification(row["text"], 1)
            print(
                f"\n[{index+1}/3] {notif.company_or_query} "
                f"· {notif.notification_date}"
            )

            before = collector._right_state_fingerprint()
            collector._click_notification(index)
            changed, _ = collector._wait_panel_change(before)

            links = collector._right_article_links()
            cards = collector._current_alerts(notif, 1)

            print("panel_changed :", changed)
            print("article_links :", len(links))
            print("cards :", len(cards))
            print("panel_total :", collector._panel_total())

            for card in cards[:5]:
                print(
                    " -",
                    card.source_label or card.source,
                    "|",
                    card.card_date or "-",
                    "|",
                    card.card_title or card.article_id,
                )

            if not cards:
                collector._save_panel_debug(notif.company_or_query)

        input("\nAppuyez sur Entrée pour fermer le navigateur...")

if __name__ == "__main__":
    main()
