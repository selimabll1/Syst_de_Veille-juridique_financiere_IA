from modules.legaltech_notifications_network_collector import (
    NetworkFirstNotificationsCollector,
)
from modules.legaltech_notifications_collector import NotificationItem

def main():
    payload = {
        "hits": {
            "total": {"value": 2},
            "hits": [
                {
                    "_id": "jrletemps-fr-2026-07-23-PM260851",
                    "_source": {
                        "source": "JrLeTemps",
                        "article_id": "jrletemps-fr-2026-07-23-PM260851",
                        "doc_id": "23/07/2026",
                        "title": "SOCIETE GAMMARTH LOISIRS",
                        "publishedAt": "2026-07-23T09:24:13+00:00",
                        "articleText": "Résumé A",
                    },
                },
                {
                    "_id": "jort-2026-88-fr-2026X01057VEPA1",
                    "_source": {
                        "source": "jort",
                        "article_id": "jort-2026-88-fr-2026X01057VEPA1",
                        "doc_id": "jort-2026-88-fr",
                        "title": "Vente immobilière",
                        "publishedAt": "2026-07-22T23:31:29+00:00",
                        "articleText": "Résumé B",
                    },
                },
            ],
        }
    }

    walked = list(
        NetworkFirstNotificationsCollector._walk_article_dicts(payload)
    )
    assert walked, "walk returned no objects"

    # Create an object without __init__ because this test only exercises pure
    # normalization logic; no browser or database is needed.
    collector = object.__new__(NetworkFirstNotificationsCollector)
    collector.browser = type(
        "B",
        (),
        {"base_url": "https://annonces.legaltech.tn"},
    )()

    notif = NotificationItem(
        notification_key="test-notif",
        company_or_query="CENTRAL",
        notification_date="27-07-2026",
        announced_result_count=1,
        notification_page=1,
        raw_text="",
        notification_index=0,
    )

    alerts = collector._alerts_from_payloads(notif, [payload])
    assert len(alerts) == 2, f"expected 2 unique alerts, got {len(alerts)}"

    print("V5.3 OFFLINE PARSER TEST OK")
    print("walked_objects:", len(walked))
    print("unique_alerts:", len(alerts))
    for alert in alerts:
        print("-", alert.source, "|", alert.card_title)

if __name__ == "__main__":
    main()
