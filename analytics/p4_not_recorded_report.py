#!/usr/bin/env python3
"""Summarize the not_recorded-inflation arm with the shared readiness report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .run_30_day_synthetic_readiness import build_events, build_report
except ImportError:  # pragma: no cover
    from run_30_day_synthetic_readiness import build_events, build_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.fixture.read_text(encoding="utf-8"))
    clean, arm = build_report(build_events()), build_report(payload["events"])
    result = {
        "protocol": "P4-not-recorded-inflation-v1",
        "changedEventCount": payload["changedEventCount"],
        "cleanMedicationCoverage": clean["medicationSlotCoverage"],
        "armMedicationCoverage": arm["medicationSlotCoverage"],
        "missingnessCounts": arm["missingnessCounts"],
        "invalidEventCount": arm["invalidEventCount"],
        "syntheticOnly": True,
        "note": "Synthetic missingness semantics check; not a clinical result.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
