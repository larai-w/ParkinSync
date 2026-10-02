#!/usr/bin/env python3
"""Print the synthetic summary-gate audit to stdout; never write source artifacts."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fhir_summary_evaluation import evaluate_summary_gate


def main():
    bundle = json.loads((ROOT / "fhir/generated/bundle-synthetic-transaction-bundle.json").read_text())
    report = evaluate_summary_gate(bundle)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return int(any(row["outcome"] in {"missed", "control_rejected", "source_not_blocked"} for row in report["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
