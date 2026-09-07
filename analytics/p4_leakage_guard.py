#!/usr/bin/env python3
"""Fail-closed checks for future-information leakage in the P4 label fixture."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path


ALLOWED_FEATURES = {"weatherAvg", "indoorTemperatureAvg", "previousConditionNum"}
FORBIDDEN_FEATURES = {"forecastDate", "label_high_support_next_day", "conditionNum"}


def check(payload: dict) -> list[str]:
    errors = []
    features = set(payload.get("featureColumns", []))
    errors.extend(f"forbidden-feature:{name}" for name in sorted(features & FORBIDDEN_FEATURES))
    errors.extend(f"unknown-feature:{name}" for name in sorted(features - ALLOWED_FEATURES))
    for index, row in enumerate(payload.get("rows", [])):
        if date.fromisoformat(row["forecastDate"]) <= date.fromisoformat(row["localDate"]):
            errors.append(f"non-future-horizon:{index}")
        if any(name in row for name in FORBIDDEN_FEATURES - {"label_high_support_next_day"}):
            # forecastDate is metadata, but must never be passed as a feature.
            if "forecastDate" in payload.get("featureColumns", []):
                errors.append(f"future-feature:{index}")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    errors = check(json.loads(args.labels.read_text(encoding="utf-8")))
    result = {"protocol": "P4-leakage-guard-v1", "status": "FAIL" if errors else "PASS", "errors": errors, "syntheticOnly": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
