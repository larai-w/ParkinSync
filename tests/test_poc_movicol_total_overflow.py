"""Synthetic daily-total overflow checks; no record store or API access."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'poc_dose_overflow', ROOT / 'poc/gutpacer-parkinsync/parkinsync_import.py')
CONSUMER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONSUMER)


def event(dose):
    return {'localDate': '2035-01-15', 'eventType': 'movicol_taken',
            'missingness': 'observed', 'payload': {'doseSachets': dose}}


class MovicolTotalOverflowTests(unittest.TestCase):
    def total(self, doses):
        return CONSUMER.import_to_daily([event(d) for d in doses])['2035-01-15']['Movi']

    def test_finite_doses_with_infinite_total_remain_unknown(self):
        self.assertIsNone(self.total([1e308, 1e308]))

    def test_mixed_numeric_overflow_remains_unknown(self):
        self.assertIsNone(self.total([10**400, 0.5]))

    def test_invalid_total_preserves_other_observations(self):
        events = [event(1e308), event(1e308),
                  {'localDate': '2035-01-15', 'eventType': 'bowel_movement',
                   'missingness': 'confirmed_none', 'payload': {}},
                  {'localDate': '2035-01-15', 'eventType': 'medication_taken',
                   'missingness': 'observed', 'payload': {}}]
        row = CONSUMER.import_to_daily(events)['2035-01-15']
        self.assertIsNone(row['Movi'])
        self.assertEqual(row['Bowel'], 0)
        self.assertEqual(row['Med'], 1)


if __name__ == '__main__':
    unittest.main()
