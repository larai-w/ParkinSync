from __future__ import annotations

import unittest

try:
    from .p4_leakage_guard import check
except ImportError:  # pragma: no cover - direct unittest invocation
    from p4_leakage_guard import check


class LeakageGuardTest(unittest.TestCase):
    def test_clean_contract_passes(self) -> None:
        payload = {
            "featureColumns": ["weatherAvg", "indoorTemperatureAvg", "previousConditionNum"],
            "rows": [{"localDate": "2035-01-01", "forecastDate": "2035-01-02"}],
        }
        self.assertEqual(check(payload), [])

    def test_label_feature_is_rejected(self) -> None:
        payload = {
            "featureColumns": ["weatherAvg", "label_high_support_next_day"],
            "rows": [{"localDate": "2035-01-01", "forecastDate": "2035-01-02"}],
        }
        self.assertIn("forbidden-feature:label_high_support_next_day", check(payload))


if __name__ == "__main__":
    unittest.main()
