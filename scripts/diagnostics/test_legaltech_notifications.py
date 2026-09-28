
from modules.legaltech_browser_collector import LegalTechBrowserCollector
from modules.legaltech_notifications_collector import LegalTechNotificationsCollector

def main():
    with LegalTechBrowserCollector(headless=False, slow_mo_ms=180) as browser:
        collector = LegalTechNotificationsCollector(browser)
        notifications, alerts, pages = collector.collect_dashboard(
            max_notification_pages=1,
            max_alert_pages=5,
        )
        print("NOTIFICATIONS PAGE : OK")
        print("Pages notifications :", pages)
        print("Notifications détectées :", len(notifications))
        print("Alertes détectées :", len(alerts))
        for i, n in enumerate(notifications, 1):
            count = sum(1 for a in alerts if a.notification_key == n.notification_key)
            print(
                f"{i}. {n.company_or_query} | date={n.notification_date or '-'} "
                f"| annoncé={n.announced_result_count} | collecté={count}"
            )
        input("\nAppuyez sur Entrée pour fermer le navigateur...")

if __name__ == "__main__":
    main()
