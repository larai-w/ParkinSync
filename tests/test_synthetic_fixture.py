import csv
import json
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "analytics" / "synthetic_sample_data_v1.3.csv"
MANIFEST_PATH = ROOT / "analytics" / "synthetic_fixture_manifest.json"
SCHEMA_PATH = ROOT / "design" / "master_schema_template.csv"


class TestSyntheticFixture(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with FIXTURE_PATH.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            cls.headers = reader.fieldnames
            cls.rows = list(reader)

    def test_matches_public_master_schema(self):
        with SCHEMA_PATH.open(newline="", encoding="utf-8") as source:
            expected_headers = next(csv.reader(source))
        self.assertEqual(self.headers, expected_headers)

    def test_every_row_is_explicitly_synthetic(self):
        self.assertEqual(len(self.rows), 21)
        for row in self.rows:
            self.assertTrue(row["Daily_Notes"].startswith("SYNTHETIC_SCENARIO_"))
            self.assertTrue(row["Weather_Summary"].startswith("SYNTHETIC_WEATHER_"))
            self.assertTrue(row["Switchbot_Summary"].startswith("SYNTHETIC_INDOOR_"))
            self.assertTrue(row["File_Name"].startswith("synthetic/"))
            self.assertEqual(datetime.strptime(row["Date"], "%Y/%m/%d").year, 2035)

    def test_manifest_declares_synthetic_provenance(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["classification"], "synthetic")
        self.assertEqual(manifest["record_count"], len(self.rows))
        self.assertEqual(manifest["fixture"], FIXTURE_PATH.name)

    def test_tracked_outputs_match_generator(self):
        result = subprocess.run(
            [sys.executable, "scripts/generate_synthetic_fixture.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_analysis_accepts_only_the_synthetic_fixture(self):
        result = subprocess.run(
            [sys.executable, "analytics/pd_correlation_analysis.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Classification: SYNTHETIC", result.stdout)
        self.assertIn("do not infer health relationships", result.stdout)


if __name__ == "__main__":
    unittest.main()
