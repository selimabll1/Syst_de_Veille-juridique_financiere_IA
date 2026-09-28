import unittest

from services.event_profiles import profile
from tests.golden_events import GOLDEN_EVENTS


class GoldenEventContractTests(unittest.TestCase):
    def test_regression_matrix_covers_requested_event_families(self):
        self.assertGreaterEqual(len(GOLDEN_EVENTS), 17)
        names = {item["name"] for item in GOLDEN_EVENTS}
        for expected in ("capital reduction", "capital increase", "liquidation", "incorporation", "litigation", "public warning", "regulatory guidance", "reporting obligation", "financial results", "governance", "composite bulletin", "long Arabic", "mixed French Arabic", "ambiguous event", "irrelevant commerce", "portfolio without referential", "multi-service notification"):
            self.assertIn(expected, names)

    def test_capital_and_warning_profiles_are_not_universal(self):
        self.assertIn("capital_before", profile("CAPITAL_REDUCTION")["required"])
        self.assertIn("warning_content", profile("PUBLIC_WARNING")["required"])
        self.assertNotIn("company", profile("PUBLIC_WARNING")["required"])


if __name__ == "__main__":
    unittest.main()
