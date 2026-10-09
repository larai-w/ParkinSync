import csv
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MasterLedgerCompatibilityTests(unittest.TestCase):
    def test_manifest_rejects_missing_and_other_contract_versions(self):
        spec = importlib.util.spec_from_file_location(
            "ledger_contract_for_test", ROOT / "scripts/master_ledger_contract.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.validate_manifest({"master_ledger_contract": module.CONTRACT_ID})
        for version in (None, "care-event/v1", "parkinsync-master-ledger/v2"):
            with self.subTest(version=version):
                with self.assertRaisesRegex(ValueError, "master-ledger"):
                    module.validate_manifest({"master_ledger_contract": version})

    def test_coordinated_template_and_fixture_changes_are_rejected(self):
        for mutation in ("reorder", "rename", "remove", "duplicate", "extra"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for folder in ("analytics", "design", "scripts"):
                    (root / folder).mkdir()
                for name in ("analytics/pd_correlation_analysis.py",
                             "analytics/synthetic_sample_data_v1.3.csv",
                             "analytics/synthetic_fixture_manifest.json",
                             "design/master_schema_template.csv",
                             "scripts/generate_synthetic_fixture.py",
                             "scripts/master_ledger_contract.py"):
                    if (ROOT / name).exists():
                        shutil.copyfile(ROOT / name, root / name)
                schema = root / "design/master_schema_template.csv"
                columns = next(csv.reader(io.StringIO(schema.read_text())))
                if mutation == "reorder":
                    columns[16], columns[21] = columns[21], columns[16]
                elif mutation == "rename":
                    columns[16] = "Weather_Mean"
                elif mutation == "remove":
                    columns.pop(16)
                elif mutation == "duplicate":
                    columns[16] = columns[17]
                else:
                    columns.append("New_Field")
                with schema.open("w", newline="") as stream:
                    csv.writer(stream).writerow(columns)
                fixture = root / "analytics/synthetic_sample_data_v1.3.csv"
                rows = list(csv.DictReader(io.StringIO(fixture.read_text())))
                with fixture.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, columns, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(rows)
                for command in ("analytics/pd_correlation_analysis.py",
                                "scripts/generate_synthetic_fixture.py"):
                    with self.subTest(mutation=mutation, consumer=command):
                        args = [sys.executable, command]
                        if command.startswith("scripts/"):
                            args.append("--check")
                        result = subprocess.run(args, cwd=root, env=os.environ.copy(),
                                                capture_output=True, text=True)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("master-ledger", result.stderr)


if __name__ == "__main__":
    unittest.main()
