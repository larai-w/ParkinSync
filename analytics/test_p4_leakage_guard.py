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

    def test_empty_and_malformed_input_is_not_a_pass(self):
        for payload in ({}, None, [], {'featureColumns': [], 'rows': []},
                        {'featureColumns': ['weatherAvg'], 'rows': []},
                        {'featureColumns': ['weatherAvg'], 'rows': [None]},
                        {'featureColumns': ['weatherAvg'], 'rows': [{'localDate': 'bad'}]}):
            self.assertTrue(check(payload))

    def test_horizon_and_order_are_checked(self):
        columns = ['weatherAvg']
        row = {'localDate': '2035-01-02', 'forecastDate': '2035-01-04'}
        self.assertTrue(check({'featureColumns': columns, 'rows': [row]}))
        row['forecastDate'] = '2035-01-03'
        self.assertTrue(check({'featureColumns': columns, 'rows': [row, row]}))


if __name__ == "__main__":
    unittest.main()
