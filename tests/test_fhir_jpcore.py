import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from fhir_jpcore import (
    JP_CORE_BUNDLE_FILE,
    JP_CORE_BUNDLE_ID,
    JP_CORE_PACKAGE,
    JP_PATIENT_PROFILE,
    JP_VITAL_SIGNS_PROFILE,
    build_jpcore_bundle,
    render_jpcore_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = (
    ROOT
    / "fhir"
    / "weekly"
    / "generated"
    / "bundle-synthetic-weekly-transaction-bundle.json"
)
OUTPUT_DIR = ROOT / "fhir" / "jpcore" / "generated"


class JpCoreFhirTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))

    def test_builds_deterministic_thirty_resource_derivative(self):
        bundle = build_jpcore_bundle(self.source)
        repeated = build_jpcore_bundle(copy.deepcopy(self.source))

        self.assertEqual(bundle, repeated)
        self.assertEqual(bundle["id"], JP_CORE_BUNDLE_ID)
        self.assertEqual(len(bundle["entry"]), 30)

    def test_profiles_patient_and_vital_sign_observations(self):
        bundle = build_jpcore_bundle(self.source)
        profiles_by_type = {}
        for entry in bundle["entry"]:
            resource = entry["resource"]
            profiles_by_type.setdefault(resource["resourceType"], []).append(
                resource.get("meta", {}).get("profile", [])
            )

        self.assertEqual(profiles_by_type["Patient"], [[JP_PATIENT_PROFILE]])
        self.assertEqual(
            profiles_by_type["Observation"], [[JP_VITAL_SIGNS_PROFILE]] * 14
        )
        self.assertEqual(profiles_by_type["MedicationStatement"], [[]] * 14)
        self.assertEqual(profiles_by_type["CarePlan"], [[]])

    def test_retains_temporary_synthetic_patient_identifier(self):
        bundle = build_jpcore_bundle(self.source)
        patient = next(
            entry["resource"]
            for entry in bundle["entry"]
            if entry["resource"]["resourceType"] == "Patient"
        )

        self.assertEqual(
            patient["identifier"],
            [
                {
                    "system": "https://veai.jp/fhir/synthetic-patient",
                    "use": "temp",
                    "value": "SYNTHETIC-WEEKLY-001",
                }
            ],
        )
        self.assertNotIn("extension", patient)

    def test_does_not_profile_or_code_medication_statements(self):
        bundle = build_jpcore_bundle(self.source)
        medications = [
            entry["resource"]
            for entry in bundle["entry"]
            if entry["resource"]["resourceType"] == "MedicationStatement"
        ]

        self.assertEqual(len(medications), 14)
        for medication in medications:
            self.assertNotIn("profile", medication["meta"])
            self.assertNotIn("coding", medication["medicationCodeableConcept"])

    def test_semantics_differ_only_by_bundle_id_and_profiles(self):
        expected = copy.deepcopy(self.source)
        expected["id"] = JP_CORE_BUNDLE_ID
        actual = build_jpcore_bundle(self.source)
        for entry in actual["entry"]:
            entry["resource"].get("meta", {}).pop("profile", None)

        self.assertEqual(actual, expected)

    def test_rejects_non_synthetic_source(self):
        source = copy.deepcopy(self.source)
        source["entry"][0]["resource"]["meta"]["tag"] = []

        with self.assertRaisesRegex(ValueError, "not classified as synthetic"):
            build_jpcore_bundle(source)

    def test_rejects_source_with_predeclared_profile(self):
        source = copy.deepcopy(self.source)
        source["entry"][0]["resource"]["meta"]["profile"] = [JP_PATIENT_PROFILE]

        with self.assertRaisesRegex(ValueError, "must not predeclare profiles"):
            build_jpcore_bundle(source)

    def test_manifest_pins_package_and_scope(self):
        manifest = json.loads(render_jpcore_outputs(self.source)["manifest.json"])

        self.assertEqual(manifest["jp_core_package"], JP_CORE_PACKAGE)
        self.assertEqual(manifest["profiled_resource_count"], 15)
        self.assertEqual(
            manifest["base_only_resource_type_counts"],
            {"CarePlan": 1, "MedicationStatement": 14},
        )
        self.assertIn("Japanese patient identifier", manifest["excluded_inferences"])

    def test_generated_jpcore_artifacts_are_reproducible(self):
        expected = render_jpcore_outputs(self.source)
        actual = {path.name: path.read_text() for path in OUTPUT_DIR.glob("*.json")}

        self.assertEqual(actual, expected)
        self.assertIn(JP_CORE_BUNDLE_FILE, actual)
        result = subprocess.run(
            [sys.executable, "scripts/generate_jpcore_fhir.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
