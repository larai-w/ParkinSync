import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("synthetic_analysis", ROOT / "analytics/pd_correlation_analysis.py")
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class AnalysisCoverageTests(unittest.TestCase):
    def run_rows(self, changes=None):
        columns, original = analysis.load_fixture()
        rows = [dict(row) for row in original]
        if changes:
            changes(rows)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(analysis, "load_fixture", return_value=(columns, rows)):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = analysis.verify_and_analyze_pipeline()
        return status, stdout.getvalue(), stderr.getvalue()

    def test_default_output_has_coverage_missingness_and_limits(self):
        status, output, errors = self.run_rows()
        self.assertEqual(status, 0, errors)
        self.assertIn("[MISSINGNESS] Switchbot_Avg: observed=21 missing=0 invalid=0", output)
        self.assertIn("[COVERAGE] Correlation pairs: 21/21 input rows", output)
        self.assertIn("[LIMITATIONS]", output)
        self.assertIn("no confidence intervals", output)
        self.assertIn("multiple testing", output)

    def test_blank_values_are_missing_and_zero_is_observed(self):
        def change(rows):
            rows[0]["Switchbot_Avg"] = ""
            rows[1]["Condition_Num"] = "  "
            rows[2]["Bowel"] = ""
            rows[3]["Bowel"] = "0"
        status, output, errors = self.run_rows(change)
        self.assertEqual(status, 0, errors)
        self.assertIn("Switchbot_Avg: observed=20 missing=1 invalid=0", output)
        self.assertIn("Bowel: observed=20 missing=1 invalid=0", output)
        self.assertIn("Correlation pairs: 19/21 input rows", output)

    def test_nonfinite_input_is_counted_and_rejected(self):
        for token in ("nan", "inf", "-inf", "bad-number"):
            with self.subTest(token=token):
                status, output, errors = self.run_rows(lambda rows: rows[0].update(Switchbot_Avg=token))
                self.assertEqual(status, 1)
                self.assertIn("Switchbot_Avg: observed=20 missing=0 invalid=1", output)
                self.assertNotIn("[CORR]", output)

    def test_constant_correlation_is_undefined(self):
        status, output, errors = self.run_rows(lambda rows: [r.update(Condition_Num="2") for r in rows])
        self.assertEqual(status, 0, errors)
        self.assertIn("undefined", output)
        self.assertNotIn(": nan", output)

    def test_all_missing_fields_do_not_become_zero(self):
        def change(rows):
            for row in rows:
                for field in ("Switchbot_Avg", "Weather_Avg", "Condition_Num", "Bowel"):
                    row[field] = ""
        status, output, errors = self.run_rows(change)
        self.assertEqual(status, 0, errors)
        self.assertIn("Correlation pairs: 0/21 input rows", output)
        self.assertIn("Mean indoor field: undefined", output)
        self.assertIn("observed subtotal: undefined", output)

    def test_unpaired_correlation_is_rejected(self):
        with self.assertRaises(ValueError):
            analysis.correlation([1., 2.], [3.])

    def test_fewer_than_two_pairs_is_undefined(self):
        self.assertIsNone(analysis.correlation([1.], [2.]))


if __name__ == "__main__":
    unittest.main()
