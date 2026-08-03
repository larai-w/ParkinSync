import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from fhir_summary import validate_summary_candidate
from fhir_weekly import (
    WEEKLY_BUNDLE_FILE,
    build_weekly_bundle,
    build_weekly_fact_bundle,
    build_weekly_resources,
    build_weekly_summary,
    load_weekly_fixture,
    render_weekly_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fhir" / "weekly" / "synthetic-weekly-records.json"
OUTPUT_DIR = ROOT / "fhir" / "weekly" / "generated"


class WeeklyFhirTests(unittest.TestCase):
    def setUp(self):
        self.fixture = load_weekly_fixture(FIXTURE_PATH)
        self.bundle = build_weekly_bundle(self.fixture)
        self.fact_bundle = build_weekly_fact_bundle(self.fixture, self.bundle)

    def test_builds_deterministic_thirty_resource_transaction(self):
        repeated = build_weekly_bundle(copy.deepcopy(self.fixture))

        self.assertEqual(self.bundle, repeated)
        self.assertEqual(self.bundle["id"], "synthetic-weekly-transaction-bundle")
        self.assertEqual(self.bundle["type"], "transaction")
        self.assertEqual(len(self.bundle["entry"]), 30)
        counts = {}
        for entry in self.bundle["entry"]:
            resource_type = entry["resource"]["resourceType"]
            counts[resource_type] = counts.get(resource_type, 0) + 1
            self.assertEqual(entry["request"]["method"], "PUT")
            self.assertEqual(
                entry["request"]["url"],
                f"{resource_type}/{entry['resource']['id']}",
            )
        self.assertEqual(
            counts,
            {"Patient": 1, "MedicationStatement": 14, "Observation": 14, "CarePlan": 1},
        )

    def test_resource_ids_and_timestamps_cover_all_seven_dates(self):
        events = [
            entry["resource"]
            for entry in self.bundle["entry"]
            if entry["resource"]["resourceType"] in {"MedicationStatement", "Observation"}
        ]
        dates = {resource["effectiveDateTime"][:10] for resource in events}

        self.assertEqual(dates, {f"2035-01-0{day}" for day in range(1, 8)})
        for resource in events:
            date_key = resource["effectiveDateTime"][:10].replace("-", "")
            self.assertIn(date_key, resource["id"])

    def test_builds_traceable_weekly_aggregate_facts(self):
        self.assertEqual(self.fact_bundle["status"], "ready")
        self.assertEqual(self.fact_bundle["analysis_window"]["days"], 7)
        self.assertEqual(
            self.fact_bundle["record_counts"],
            {"MedicationStatement": 14, "Observation": 14, "derived_aggregate": 3},
        )
        self.assertEqual(self.fact_bundle["missingness"]["missing_days"], [])
        self.assertEqual(
            self.fact_bundle["missingness"]["missing_or_extra_events"], []
        )
        self.assertEqual(self.fact_bundle["material_corrections"], [])

        event_ids = {
            fact["id"]
            for fact in self.fact_bundle["facts"]
            if fact["kind"] in {"medication", "observation"}
        }
        aggregates = [
            fact for fact in self.fact_bundle["facts"] if fact["kind"].startswith("weekly-")
        ]
        self.assertEqual(len(event_ids), 28)
        self.assertEqual(len(aggregates), 3)
        for aggregate in aggregates:
            source_ids = set(aggregate["source"]["derived_from_fact_ids"])
            self.assertTrue(source_ids)
            self.assertTrue(source_ids.issubset(event_ids))
            self.assertTrue(aggregate["source"]["method"])

    def test_summary_contains_structured_window_and_grounded_ranges(self):
        summary = build_weekly_summary(self.fact_bundle)

        self.assertEqual(summary["status"], "ready_for_human_review")
        self.assertTrue(summary["validation"]["accepted"])
        self.assertTrue(summary["requires_human_review"])
        self.assertFalse(summary["sharing_permitted"])
        self.assertEqual(summary["analysis_window"]["start"], "2035-01-01")
        self.assertEqual(summary["analysis_window"]["end"], "2035-01-07")
        self.assertEqual(summary["included_sources"], ["MedicationStatement", "Observation"])
        text = " ".join(statement["text"] for statement in summary["statements"])
        self.assertIn("14 medication records", text)
        self.assertIn("2 were recorded as not-taken", text)
        self.assertIn("36.4 to 36.8 Cel", text)
        self.assertIn("66 to 72 /min", text)

    def test_missing_day_returns_explicit_insufficient_data(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["days"] = [day for day in fixture["days"] if day["date"] != "2035-01-03"]
        bundle = build_weekly_bundle(fixture)

        facts = build_weekly_fact_bundle(fixture, bundle)
        summary = build_weekly_summary(facts)
        self.assertEqual(facts["status"], "insufficient_data")
        self.assertIn("2035-01-03", facts["missingness"]["missing_days"])
        self.assertTrue(facts["missingness"]["missing_or_extra_events"])
        self.assertEqual(summary["status"], "insufficient_data")
        self.assertEqual(summary["statements"], [])

    def test_duplicate_event_returns_insufficient_data(self):
        bundle = copy.deepcopy(self.bundle)
        duplicate = copy.deepcopy(
            next(
                entry
                for entry in bundle["entry"]
                if entry["resource"]["resourceType"] == "Observation"
            )
        )
        duplicate["fullUrl"] = "urn:uuid:00000000-0000-0000-0000-000000000099"
        bundle["entry"].append(duplicate)

        facts = build_weekly_fact_bundle(self.fixture, bundle)
        self.assertEqual(facts["status"], "insufficient_data")
        self.assertTrue(facts["quality"]["duplicates"])

    def test_rejects_changed_aggregate_number(self):
        summary = build_weekly_summary(self.fact_bundle)
        statement = next(
            item for item in summary["statements"] if "Body temperature" in item["text"]
        )
        statement["text"] = statement["text"].replace("36.4", "39.4")

        result = validate_summary_candidate(summary, self.fact_bundle)
        self.assertIn(
            "numerical-inconsistency",
            {error["code"] for error in result["validation"]["errors"]},
        )

    def test_rejects_omitted_not_taken_records(self):
        summary = build_weekly_summary(self.fact_bundle)
        summary["statements"] = [
            statement
            for statement in summary["statements"]
            if "medication records" not in statement["text"]
        ]

        result = validate_summary_candidate(summary, self.fact_bundle)
        omitted = next(
            error
            for error in result["validation"]["errors"]
            if error["code"] == "omitted-not-taken-medication"
        )
        self.assertEqual(len(omitted["fact_ids"]), 2)

    def test_rejects_missing_explicit_daily_adherence(self):
        fixture = copy.deepcopy(self.fixture)
        del fixture["days"][0]["taken"]["lunch"]

        with self.assertRaisesRegex(ValueError, "taken.lunch must be a boolean"):
            build_weekly_resources(fixture)

    def test_rejects_non_seven_day_analysis_window(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["analysis_window"]["end"] = "2035-01-08"

        with self.assertRaisesRegex(ValueError, "exactly seven consecutive dates"):
            build_weekly_resources(fixture)

    def test_generated_weekly_artifacts_are_reproducible(self):
        expected = render_weekly_outputs(self.fixture)
        actual = {path.name: path.read_text() for path in OUTPUT_DIR.glob("*.json")}
        self.assertEqual(actual, expected)
        self.assertIn(WEEKLY_BUNDLE_FILE, actual)
        result = subprocess.run(
            [sys.executable, "scripts/generate_weekly_fhir.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
