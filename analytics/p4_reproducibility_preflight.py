#!/usr/bin/env python3
"""Fail-closed preflight for the P4 synthetic baseline pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .p4_leakage_guard import check
    from .p4_synthetic_labels import build_label_rows
    from .run_30_day_synthetic_readiness import build_events
except ImportError:  # pragma: no cover - direct file execution
    from p4_leakage_guard import check
    from p4_synthetic_labels import build_label_rows
    from run_30_day_synthetic_readiness import build_events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = build_label_rows(build_events())
    payload = {"featureColumns": ["weatherAvg", "indoorTemperatureAvg", "previousConditionNum"], "rows": rows}
    errors = check(payload)
    if len(rows) != 29:
        errors.append(f"row-count:{len(rows)}")
    result = {"protocol": "P4-reproducibility-preflight-v1", "status": "FAIL" if errors else "PASS", "rowCount": len(rows), "errors": sorted(set(errors)), "syntheticOnly": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
