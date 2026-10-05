"""Do not present source-level evidence as verified cloud operation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EvidenceCopyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.readme = (ROOT / "README.md").read_text()

    def test_analytics_distinguishes_local_synthetic_eda_from_cloud_runs(self):
        self.assertFalse("Amazon SageMaker  (exploratory Pearson r and lag analyses)" in self.readme, "Unsupported cloud analytics claim")
        self.assertFalse("| Analytics | Amazon SageMaker, Python Pandas / NumPy / SciPy |" in self.readme, "Unsupported analytics stack claim")
        self.assertIn("synthetic fixtures", self.readme)
        self.assertIn("SageMaker execution and lag-analysis results are unverified", self.readme)
        self.assertTrue((ROOT / "analytics/pd_correlation_analysis.py").is_file())

    def test_secret_retrieval_is_not_an_all_deployments_guarantee(self):
        self.assertFalse("stored exclusively in AWS Secrets Manager" in self.readme, "Unverified all-credentials guarantee")
        self.assertIn("does not verify all credentials or the live configuration of every deployment", self.readme)
        for name in ("ParkinSync_OCR_Handler.py", "indoor_temp_logger.py"):
            self.assertIn("get_secret_value", (ROOT / "src" / name).read_text())

    def test_main_is_not_claimed_to_be_continuously_identical_to_live_lambdas(self):
        self.assertFalse("matches live Lambda deployments" in self.readme, "Unverified live equivalence guarantee")
        self.assertIn("verified per function and deployment version", self.readme)


if __name__ == "__main__":
    unittest.main()
