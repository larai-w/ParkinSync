import copy
import json
import unittest
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
        times = [line.split(" ", 2)[1] for line in lines]
        self.assertEqual(times, sorted(times))

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

    def test_unknown_strategy_is_rejected(self):
        with self.assertRaises(ValueError):
            serialize_facts(self.bundle, "yaml")


if __name__ == "__main__":
    unittest.main()
