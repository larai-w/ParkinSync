import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


class ReadmeLinkTests(unittest.TestCase):
    def test_repository_relative_links_resolve(self):
        targets = MARKDOWN_LINK.findall(README_PATH.read_text(encoding="utf-8"))
        local_targets = [
            target.split("#", 1)[0]
            for target in targets
            if target
            and not target.startswith(("https://", "http://", "mailto:", "#"))
        ]

        missing = sorted(
            target for target in local_targets if not (ROOT / target).exists()
        )
        self.assertEqual(missing, [], f"README contains missing local links: {missing}")

    def test_five_minute_review_links_to_executable_evidence(self):
        readme = README_PATH.read_text(encoding="utf-8")
        required_targets = {
            "src/fhir_export.py",
            "src/fhir_summary.py",
            "tests/test_fhir_export.py",
            "tests/test_fhir_summary.py",
            "fhir/generated/bundle-synthetic-transaction-bundle.json",
            "fhir/summary/generated/fact-bundle.json",
            "fhir/summary/generated/offline-summary.json",
            "src/fhir_weekly.py",
            "fhir/weekly/generated/bundle-synthetic-weekly-transaction-bundle.json",
            "fhir/weekly/generated/weekly-summary.json",
            "src/fhir_roundtrip.py",
            "fhir/server/roundtrip-contract.json",
            ".github/workflows/fhir-roundtrip.yml",
            "src/fhir_nzbase.py",
            "fhir/nzbase/generated/bundle-synthetic-weekly-nzbase-transaction-bundle.json",
            "fhir/nzbase/generated/manifest.json",
            ".github/workflows/ci.yml",
        }

        linked_targets = set(MARKDOWN_LINK.findall(readme))
        self.assertTrue(required_targets.issubset(linked_targets))


if __name__ == "__main__":
    unittest.main()
