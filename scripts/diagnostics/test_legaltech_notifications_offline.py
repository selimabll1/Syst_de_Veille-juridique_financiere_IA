
from pathlib import Path
import tempfile

from modules.legaltech_notifications_collector import (
    LegalTechNotificationsCollector,
    NotificationsRegistry,
)

def main():
    obj = object.__new__(LegalTechNotificationsCollector)
    item = obj._parse_notification(
        "1 résultat(s) trouvé(s) pour SUD EXTEME ANIMATION 03-07-2026",
        1,
    )
    assert item.company_or_query == "SUD EXTEME ANIMATION"
    assert item.notification_date == "03-07-2026"
    assert item.announced_result_count == 1

    with tempfile.TemporaryDirectory() as tmp:
        reg = NotificationsRegistry(Path(tmp) / "x.sqlite3")
        assert reg.upsert_notification(item) == "NEW"
        assert reg.upsert_notification(item) == "KNOWN"

    print("LEGALTECH NOTIFICATIONS COLLECTOR v2 — TEST HORS LIGNE OK")

if __name__ == "__main__":
    main()
