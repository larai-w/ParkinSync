"""Synthetic checks for daily dose totals; no API or record store access."""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "poc_movicol_consumer", ROOT / "poc/gutpacer-parkinsync/parkinsync_import.py"
)
CONSUMER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONSUMER)


def event(payload, missingness="observed"):
    return {"localDate": "2035-01-15", "eventType": "movicol_taken",
            "missingness": missingness, "payload": payload}


class MovicolDoseMissingnessTests(unittest.TestCase):
    def total(self, events):
        return CONSUMER.import_to_daily(events)["2035-01-15"]["Movi"]

    def test_runtime_taken_slots_without_doses_remain_unknown(self):
        events = [event({"slot": slot, "medicationRef": "med-movicol",
                         "timePrecision": "day"})
                  for slot in ("morning", "evening")]
        self.assertIsNone(self.total(events))

    def test_known_and_unknown_doses_do_not_report_partial_total(self):
        self.assertIsNone(self.total([event({"doseSachets": 2}), event({"slot": "evening"})]))

    def test_explicit_null_dose_remains_unknown(self):
        self.assertIsNone(self.total([event({"doseSachets": None})]))

    def test_known_doses_are_summed(self):
        self.assertEqual(self.total([event({"doseSachets": 1}), event({"doseSachets": 2})]), 3)

    def test_fractional_doses_are_not_truncated(self):
        self.assertEqual(self.total([event({"doseSachets": 0.5}), event({"doseSachets": 1})]), 1.5)

    def test_explicit_zero_is_preserved(self):
        self.assertEqual(self.total([event({"doseSachets": 0})]), 0)

    def test_invalid_doses_remain_unknown(self):
        for dose in (True, False, -1, float("inf"), float("nan"), "unknown", "2"):
            with self.subTest(dose=dose):
                self.assertIsNone(self.total([event({"doseSachets": dose})]))

    def test_unobserved_dose_does_not_contaminate_known_total(self):
        self.assertEqual(self.total([event({"doseSachets": 2}), event({}, "not_recorded")]), 2)

    def test_unknown_dose_preserves_other_observations(self):
        events = [event({"slot": "morning"}),
                  {"localDate": "2035-01-15", "eventType": "bowel_movement",
                   "missingness": "confirmed_none", "payload": {}},
                  {"localDate": "2035-01-15", "eventType": "medication_taken",
                   "missingness": "observed", "payload": {}}]
        row = CONSUMER.import_to_daily(events)["2035-01-15"]
        self.assertIsNone(row["Movi"])
        self.assertEqual(row["Bowel"], 0)
        self.assertEqual(row["Med"], 1)


if __name__ == "__main__":
    unittest.main()
