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
    if not isinstance(payload, dict):
        return ['invalid-payload']
    columns = payload.get('featureColumns')
    rows = payload.get('rows')
    if not isinstance(columns, list) or not columns or any(not isinstance(x, str) for x in columns):
        return ['invalid-feature-columns']
    errors = []
    features = set(columns)
    if len(features) != len(columns):
        errors.append('duplicate-feature-columns')
    errors.extend(f"forbidden-feature:{name}" for name in sorted(features & FORBIDDEN_FEATURES))
    errors.extend(f"unknown-feature:{name}" for name in sorted(features - ALLOWED_FEATURES))
    if not isinstance(rows, list) or not rows:
        return sorted(set(errors + ['empty-or-invalid-rows']))
    previous = None
    for index, row in enumerate(rows):
        try:
            if not isinstance(row, dict):
                raise ValueError()
            local = date.fromisoformat(row['localDate'])
            forecast = date.fromisoformat(row['forecastDate'])
        except (KeyError, TypeError, ValueError):
            errors.append(f'invalid-row-dates:{index}')
            continue
        if (forecast - local).days != 1:
            errors.append(f'non-next-day-horizon:{index}')
        if previous is not None and local <= previous:
            errors.append(f'non-increasing-date:{index}')
        previous = local
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
