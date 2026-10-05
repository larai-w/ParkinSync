"""Keep the documented OCR review boundary aligned with the current handler."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OcrCopyBoundaryTests(unittest.TestCase):
    def test_architecture_places_operator_review_after_automatic_append(self):
        readme = (ROOT / "README.md").read_text()
        architecture = readme.split("## Architecture\n", 1)[1].split("```", 2)[1]
        self.assertNotIn("append verified row", architecture)
        append = architecture.index("append extracted rows to master ledger")
        review = architecture.index("operator review after import (not enforced by handler)")
        self.assertLess(append, review)

    def test_readme_does_not_claim_a_pre_ingestion_human_gate(self):
        readme = (ROOT / "README.md").read_text()
        for claim in ("does not auto-fill fields",
                      "verifies the transcription before cloud ingestion",
                      "are manually transcribed, then ingested into AWS"):
            self.assertFalse(claim in readme, f"Unsupported OCR claim: {claim}")
        self.assertIn("automatically appends extracted rows", readme)
        self.assertIn("review the imported rows in the Master sheet", readme)
        self.assertIn("does not enforce a human approval gate before that write", readme)

    def test_product_copy_places_operator_review_after_import(self):
        product = json.loads((ROOT / "product.json").read_text())
        capability = next(c for c in product["capabilities"] if c["id"] == "human-reviewed-ocr")
        self.assertIn("post-import operator review", capability["label"]["en"])
        self.assertIn("取り込み後", capability["label"]["ja"])
        self.assertIn("post-import operator review", product["site"]["en"]["description"])
        self.assertIn("その後に人が確認", product["site"]["ja"]["description"])


if __name__ == "__main__":
    unittest.main()
