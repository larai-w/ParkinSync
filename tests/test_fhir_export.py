import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from fhir.resources import __fhir_version__
from fhir.resources.bundle import Bundle

from fhir_export import (
    BUNDLE_FILE,
    FHIR_VERSION,
    RESOURCE_MODELS,
    build_transaction_bundle,
    build_resources,
    load_record,
    render_outputs,
    validate_transaction_bundle,
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

    def test_builds_deterministic_transaction_bundle(self):
        resources = build_resources(self.record)
        bundle = build_transaction_bundle(resources)
        payload = json.loads(bundle.json(exclude_none=True, by_alias=True))
        repeated = json.loads(
            build_transaction_bundle(resources).json(exclude_none=True, by_alias=True)
        )

        self.assertEqual(payload, repeated)
        self.assertEqual(payload["resourceType"], "Bundle")
        self.assertEqual(payload["type"], "transaction")
        self.assertEqual(len(payload["entry"]), len(resources))
        full_urls = {entry["fullUrl"] for entry in payload["entry"]}
        self.assertEqual(len(full_urls), len(resources))
        self.assertTrue(all(full_url.startswith("urn:uuid:") for full_url in full_urls))
        for entry in payload["entry"]:
            resource = entry["resource"]
            self.assertEqual(entry["request"]["method"], "PUT")
            self.assertEqual(
                entry["request"]["url"],
                f"{resource['resourceType']}/{resource['id']}",
            )

        patient_entry = next(
            entry for entry in payload["entry"] if entry["resource"]["resourceType"] == "Patient"
        )
        self.assertTrue(
            all(
                entry["resource"].get("subject", {}).get("reference")
                == patient_entry["fullUrl"]
                for entry in payload["entry"]
                if entry["resource"]["resourceType"] != "Patient"
            )
        )

    def test_rejects_duplicate_transaction_full_url(self):
        payload = json.loads(
            build_transaction_bundle(build_resources(self.record)).json(
                exclude_none=True, by_alias=True
            )
        )
        payload["entry"][1]["fullUrl"] = payload["entry"][0]["fullUrl"]
        with self.assertRaisesRegex(ValueError, "fullUrls must be unique"):
            validate_transaction_bundle(Bundle.parse_obj(payload))

    def test_generated_artifacts_are_reproducible(self):
        expected = render_outputs(self.record)
        actual = {path.name: path.read_text() for path in OUTPUT_DIR.glob("*.json")}
        self.assertEqual(actual, expected)
        self.assertIn(BUNDLE_FILE, actual)
        result = subprocess.run(
            [sys.executable, "scripts/export_synthetic_fhir.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
