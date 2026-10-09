import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "dependency_snapshot", Path(__file__).resolve().parents[1] / "scripts/check_dependency_snapshot.py"
)
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class DependencySnapshotTests(unittest.TestCase):
    def test_equivalent_package_names_and_tooling_do_not_report_drift(self):
        self.assertEqual(snapshot.differences({"google-auth": "2.60.0"},
                                             {"Google_Auth": "2.60.0", "pip": "26.2.1"}), [])

    def test_changed_missing_and_new_transitive_packages_are_all_rejected(self):
        errors = snapshot.differences({"requests": "2.34.2", "google-auth": "2.60.0"},
                                     {"requests": "999.0", "new-dependency": "1.0"})
        self.assertEqual(len(errors), 3)
        self.assertIn("missing: google-auth==2.60.0", errors)
        self.assertIn("changed: requests: expected 2.34.2, installed 999.0", errors)
        self.assertIn("unconstrained: new-dependency==1.0", errors)

    def test_incomplete_or_ambiguous_snapshots_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "constraints.txt"
            for content in ("", "# empty\n", "requests>=2\n", "x==1\nx==2\n", "X_y==1\nx-y==1\n", "pip==26.2.1\n"):
                with self.subTest(content=content):
                    path.write_text(content)
                    with self.assertRaises(ValueError):
                        snapshot.read_snapshot(path)

    def test_snapshot_preserves_exact_versions_and_normalizes_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "constraints.txt"
            path.write_text("# snapshot\nPython_Dateutil==2.9.0.post0\n")
            self.assertEqual(snapshot.read_snapshot(path), {"python-dateutil": "2.9.0.post0"})
