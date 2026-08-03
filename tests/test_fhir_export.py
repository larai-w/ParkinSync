import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from fhir.resources import __fhir_version__

from fhir_export import (
    FHIR_VERSION,
    RESOURCE_MODELS,
    build_resources,
    load_record,
    render_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "fhir" / "synthetic_normalized_record.json"
OUTPUT_DIR = ROOT / "fhir" / "generated"


class FhirExportTests(unittest.TestCase):
    def setUp(self):
        self.record = load_record(INPUT_PATH)

    def test_builds_four_valid_r4_resource_types(self):
        self.assertEqual(__fhir_version__, FHIR_VERSION)
        resources = build_resources(self.record)
        payloads = [json.loads(resource.json(exclude_none=True, by_alias=True)) for resource in resources]

        self.assertEqual({payload["resourceType"] for payload in payloads}, set(RESOURCE_MODELS))
        self.assertEqual(len(payloads), 6)
        for payload in payloads:
            RESOURCE_MODELS[payload["resourceType"]].parse_obj(payload)
            self.assertTrue(payload["id"].startswith("synthetic-"))
            self.assertEqual(payload["meta"]["tag"][0]["code"], "synthetic")

    def test_maps_explicit_medication_status_and_reviewed_loinc_codes(self):
        payloads = [
            json.loads(resource.json(exclude_none=True, by_alias=True))
            for resource in build_resources(self.record)
        ]
        medications = {
            payload["id"]: payload
            for payload in payloads
            if payload["resourceType"] == "MedicationStatement"
        }
        observations = {
            payload["id"]: payload
            for payload in payloads
            if payload["resourceType"] == "Observation"
        }

        self.assertEqual(medications["synthetic-medication-morning"]["status"], "completed")
        self.assertEqual(medications["synthetic-medication-lunch"]["status"], "not-taken")
        self.assertEqual(
            observations["synthetic-body-temperature"]["code"]["coding"][0]["code"],
            "8310-5",
        )
        self.assertEqual(
            observations["synthetic-heart-rate"]["code"]["coding"][0]["code"],
            "8867-4",
        )

    def test_rejects_non_synthetic_input(self):
        record = copy.deepcopy(self.record)
        record["classification"] = "participant"
        with self.assertRaisesRegex(ValueError, "only records classified as synthetic"):
            build_resources(record)

    def test_rejects_unknown_input_schema_version(self):
        record = copy.deepcopy(self.record)
        record["schema_version"] = "parkinsync-fhir-demo-v2"
        with self.assertRaisesRegex(ValueError, "schema_version must be"):
            build_resources(record)

    def test_rejects_unreviewed_observation_mapping(self):
        record = copy.deepcopy(self.record)
        record["observations"][0]["kind"] = "fall-risk"
        with self.assertRaisesRegex(ValueError, "not a reviewed mapping"):
            build_resources(record)

    def test_rejects_missing_explicit_medication_adherence(self):
        record = copy.deepcopy(self.record)
        del record["medications"][0]["taken"]
        with self.assertRaisesRegex(ValueError, "taken must be a boolean"):
            build_resources(record)

    def test_all_subject_references_resolve_to_the_generated_patient(self):
        payloads = [
            json.loads(resource.json(exclude_none=True, by_alias=True))
            for resource in build_resources(self.record)
        ]
        patient = next(payload for payload in payloads if payload["resourceType"] == "Patient")
        expected = f"Patient/{patient['id']}"
        self.assertTrue(
            all(
                payload.get("subject", {}).get("reference") == expected
                for payload in payloads
                if payload["resourceType"] != "Patient"
            )
        )

    def test_generated_artifacts_are_reproducible(self):
        expected = render_outputs(self.record)
        actual = {path.name: path.read_text() for path in OUTPUT_DIR.glob("*.json")}
        self.assertEqual(actual, expected)
        result = subprocess.run(
            [sys.executable, "scripts/export_synthetic_fhir.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
