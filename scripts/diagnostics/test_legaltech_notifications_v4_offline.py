
from modules.legaltech_notifications_collector import (
    LegalTechNotificationsCollector,
)

def main():
    obj = object.__new__(LegalTechNotificationsCollector)

    notif = obj._parse_notification(
        "2 résultat(s) trouvé(s) pour VILAVI 25-07-2026",
        1,
    )
    assert notif.company_or_query == "VILAVI"
    assert notif.notification_date == "25-07-2026"
    assert notif.announced_result_count == 2

    card = obj._parse_card(
        """Journal Chourouk
Dimanche 26-07-2026
jrchourouk-fr-2026-07-26-IP2266435
S.D.B-Wc- Hall au 2ème étage avec un gd. balcon interphone
Télécharger
Voir plus""",
        "VILAVI",
        "JrChourouk",
    )
    assert card["card_date"] == "26-07-2026"
    assert card["card_title"] == "jrchourouk-fr-2026-07-26-IP2266435"
    assert "S.D.B-Wc" in card["card_summary"]

    print("V4 OFFLINE TEST OK")
    print(notif)
    print(card)

if __name__ == "__main__":
    main()
