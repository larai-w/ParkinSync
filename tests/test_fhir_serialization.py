import copy
import json
import re
import unittest
from datetime import datetime
from pathlib import Path

from fhir_serialization import STRATEGIES, check_lossless, serialize_facts


ROOT = Path(__file__).resolve().parents[1]
FACT_BUNDLE_PATH = ROOT / "fhir" / "summary" / "generated" / "fact-bundle.json"


class FhirSerializationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads(FACT_BUNDLE_PATH.read_text(encoding="utf-8"))

    def test_every_strategy_keeps_all_ids_and_numbers(self):
        self.assertTrue(self.bundle["facts"])
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                text = serialize_facts(self.bundle, strategy)
                self.assertEqual(
                    check_lossless(self.bundle, text),
                    {"missing_ids": [], "missing_values": []},
                )

    def test_rendering_is_deterministic(self):
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                self.assertEqual(
                    serialize_facts(self.bundle, strategy),
                    serialize_facts(copy.deepcopy(self.bundle), strategy),
                )

    def test_timeline_is_in_time_order(self):
        lines = serialize_facts(self.bundle, "timeline").splitlines()
        times = [datetime.fromisoformat(line.split(" ", 2)[1]) for line in lines]
        self.assertEqual(times, sorted(times))

    def test_timeline_orders_by_instant_not_by_text(self):
        """+09:00 07:00 is 22:00 UTC the day before, so it comes first."""
        bundle = copy.deepcopy(self.bundle)
        bundle["facts"] = bundle["facts"][:2]
        bundle["facts"][0]["effective_time"] = "2035-01-01T02:00:00+00:00"
        bundle["facts"][1]["effective_time"] = "2035-01-01T07:00:00+09:00"
        lines = serialize_facts(bundle, "timeline").splitlines()
        self.assertIn(bundle["facts"][1]["id"], lines[0])
        self.assertIn(bundle["facts"][0]["id"], lines[1])

    def test_timeline_rejects_a_time_without_an_offset(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["facts"][0]["effective_time"] = "2035-01-01T07:00:00"
        with self.assertRaises(ValueError):
            serialize_facts(bundle, "timeline")

    def test_check_reports_a_dropped_fact(self):
        text = serialize_facts(self.bundle, "markdown_table")
        dropped = self.bundle["facts"][0]["id"]
        report = check_lossless(self.bundle, text.replace(dropped, "REMOVED"))
        self.assertEqual(report["missing_ids"], [dropped])

    def test_check_reports_a_dropped_number(self):
        fact = next(f for f in self.bundle["facts"] if f["kind"] == "medication")
        altered = copy.deepcopy(self.bundle)
        for value in altered["facts"][self.bundle["facts"].index(fact)]["source"]["values"]:
            if value["name"] == "dose_value":
                value["value"] = 987654
        text = serialize_facts(self.bundle, "timeline")
        self.assertIn(f"{fact['id']}=987654", check_lossless(altered, text)["missing_values"])

    def _shared_number_fact(self):
        """A fact whose number also appears in another fact (both doses are 100)."""
        for fact in self.bundle["facts"]:
            mine = check_lossless({"facts": [fact]}, "")["missing_values"]
            for entry in mine:
                value = entry.split("=", 1)[1]
                others = [
                    f for f in self.bundle["facts"]
                    if f is not fact and f"{f['id']}={value}"
                    in check_lossless({"facts": [f]}, "")["missing_values"]
                ]
                if others:
                    return fact, value
        self.fail("fixture no longer has two facts sharing a number")

    def test_check_reports_a_number_dropped_from_one_row_of_a_table(self):
        """Another fact carrying the same number must not hide the loss."""
        fact, value = self._shared_number_fact()
        lines = serialize_facts(self.bundle, "markdown_table").splitlines()
        altered = [
            re.sub(rf"(?<![\w.-]){re.escape(value)}(?![\w.-])", "", line)
            if fact["id"] in line else line
            for line in lines
        ]
        report = check_lossless(self.bundle, "\n".join(altered))
        self.assertIn(f"{fact['id']}={value}", report["missing_values"])

    def test_check_reports_a_number_dropped_from_one_json_record(self):
        fact, value = self._shared_number_fact()
        records = json.loads(serialize_facts(self.bundle, "json"))
        for record in records:
            if record["id"] == fact["id"]:
                text = json.dumps(record)
                text = re.sub(rf"(?<![\w.-]){re.escape(value)}(?![\w.-])", '"x"', text)
                records[records.index(record)] = json.loads(text)
        report = check_lossless(self.bundle, json.dumps(records))
        self.assertIn(f"{fact['id']}={value}", report["missing_values"])

    def test_unknown_strategy_is_rejected(self):
        with self.assertRaises(ValueError):
            serialize_facts(self.bundle, "yaml")


if __name__ == "__main__":
    unittest.main()
