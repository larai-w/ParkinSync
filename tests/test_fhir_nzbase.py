import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from fhir_nzbase import (
    NHI_SYSTEM,
    NZ_BASE_BUNDLE_FILE,
    NZ_BASE_BUNDLE_ID,
    NZ_BASE_PACKAGE,
    NZ_MEDICATION_STATEMENT_PROFILE,
    NZ_PATIENT_PROFILE,
    build_nzbase_bundle,
    render_nzbase_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = (
    ROOT
    / "fhir"
    / "weekly"
    / "generated"
    / "bundle-synthetic-weekly-transaction-bundle.json"
)
OUTPUT_DIR = ROOT / "fhir" / "nzbase" / "generated"


class NzBaseFhirTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))

    def test_builds_deterministic_thirty_resource_derivative(self):
        bundle = build_nzbase_bundle(self.source)
        repeated = build_nzbase_bundle(copy.deepcopy(self.source))

        self.assertEqual(bundle, repeated)
        self.assertEqual(bundle["id"], NZ_BASE_BUNDLE_ID)
        self.assertEqual(len(bundle["entry"]), 30)

    def test_profiles_only_patient_and_medication_statements(self):
        bundle = build_nzbase_bundle(self.source)
        profiles_by_type = {}
        for entry in bundle["entry"]:
            resource = entry["resource"]
            profiles_by_type.setdefault(resource["resourceType"], []).append(
                resource.get("meta", {}).get("profile", [])
            )

        self.assertEqual(profiles_by_type["Patient"], [[NZ_PATIENT_PROFILE]])
        self.assertEqual(
            profiles_by_type["MedicationStatement"],
            [[NZ_MEDICATION_STATEMENT_PROFILE]] * 14,
        )
        self.assertEqual(profiles_by_type["Observation"], [[]] * 14)
        self.assertEqual(profiles_by_type["CarePlan"], [[]])

    def test_retains_synthetic_identifier_without_inventing_nhi(self):
        bundle = build_nzbase_bundle(self.source)
        patient = next(
            entry["resource"]
            for entry in bundle["entry"]
            if entry["resource"]["resourceType"] == "Patient"
        )

        self.assertEqual(patient["identifier"][0]["use"], "temp")
        self.assertNotEqual(patient["identifier"][0]["system"], NHI_SYSTEM)
        self.assertNotIn("extension", patient)

    def test_does_not_invent_nzmt_medication_codes(self):
        bundle = build_nzbase_bundle(self.source)
        medications = [
            entry["resource"]
            for entry in bundle["entry"]
            if entry["resource"]["resourceType"] == "MedicationStatement"
        ]

        self.assertEqual(len(medications), 14)
        for medication in medications:
            self.assertNotIn("coding", medication["medicationCodeableConcept"])
            self.assertTrue(medication["medicationCodeableConcept"]["text"])

    def test_semantics_differ_only_by_bundle_id_and_profile_declarations(self):
        expected = copy.deepcopy(self.source)
        expected["id"] = NZ_BASE_BUNDLE_ID
        actual = build_nzbase_bundle(self.source)
        for entry in actual["entry"]:
            entry["resource"].get("meta", {}).pop("profile", None)

        self.assertEqual(actual, expected)

    def test_rejects_non_synthetic_source_before_derivation(self):
        source = copy.deepcopy(self.source)
        source["entry"][0]["resource"]["meta"]["tag"] = []

        with self.assertRaisesRegex(ValueError, "not classified as synthetic"):
            build_nzbase_bundle(source)

    def test_rejects_source_with_predeclared_profile(self):
        source = copy.deepcopy(self.source)
        source["entry"][0]["resource"]["meta"]["profile"] = [NZ_PATIENT_PROFILE]

        with self.assertRaisesRegex(ValueError, "must not predeclare profiles"):
            build_nzbase_bundle(source)

    def test_manifest_pins_published_package_and_scope(self):
        outputs = render_nzbase_outputs(self.source)
        manifest = json.loads(outputs["manifest.json"])

        self.assertEqual(manifest["nz_base_package"], NZ_BASE_PACKAGE)
        self.assertEqual(manifest["profiled_resource_count"], 15)
        self.assertEqual(
            manifest["base_only_resource_type_counts"],
            {"CarePlan": 1, "Observation": 14},
        )
        self.assertIn("NHI", manifest["excluded_inferences"])

    def test_generated_nzbase_artifacts_are_reproducible(self):
        expected = render_nzbase_outputs(self.source)
        actual = {path.name: path.read_text() for path in OUTPUT_DIR.glob("*.json")}

        self.assertEqual(actual, expected)
        self.assertIn(NZ_BASE_BUNDLE_FILE, actual)
        result = subprocess.run(
            [sys.executable, "scripts/generate_nzbase_fhir.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
