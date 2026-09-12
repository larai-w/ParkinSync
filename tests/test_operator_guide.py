"""Keep the public operator guide aligned with OCR outcome states.

These states change what an operator should do after an upload.  A generic
"success" instruction would hide duplicate-ingestion and quarantine risks.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "USER_GUIDE.md"


class OperatorGuideTests(unittest.TestCase):
    def test_ingestion_states_have_distinct_operator_guidance(self):
        guide = GUIDE.read_text(encoding="utf-8")

        for state in (
            "`processed`",
            "`processed_tagging_warning`",
            "`already_processed`",
            "`quarantined`",
            "`quarantined_permanent_failure`",
        ):
            self.assertIn(state, guide)

        self.assertIn("Do **not** upload the same file again.", guide)
        self.assertIn("Do not manually re-upload while the retry outcome is unknown.", guide)
        self.assertIn("one-page", guide)


if __name__ == "__main__":
    unittest.main()
