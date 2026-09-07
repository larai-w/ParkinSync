#!/usr/bin/env python3
"""Compare clean and block-missingness synthetic fixtures with P3 checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .run_30_day_synthetic_readiness import build_report
except ImportError:  # pragma: no cover - direct file execution
    from run_30_day_synthetic_readiness import build_report


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def compare(clean: dict[str, Any], perturbed: dict[str, Any]) -> dict[str, Any]:
    def delta(path: tuple[str, ...]) -> int | float:
        left: Any = clean
        right: Any = perturbed
        for key in path:
            left, right = left[key], right[key]
        return right - left

    return {
        "protocol": "P4-block-missingness-v1",
        "clean": clean,
        "perturbed": perturbed,
        "delta": {
            "inputEventCount": delta(("inputEventCount",)),
            "uniqueValidEventCount": delta(("uniqueValidEventCount",)),
            "distinctDayCount": delta(("distinctDayCount",)),
            "medicationObservedSlots": delta(("medicationSlotCoverage", "observedSlots")),
            "medicationCoverageRate": delta(("medicationSlotCoverage", "rate")),
            "medicationSourceDayCoverage": delta(("sourceDayCoverage", "medication-promise")),
        },
        "interpretation": "Synthetic robustness comparison only; not a clinical or product-performance result.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--perturbed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(build_report(load_jsonl(args.clean)), build_report(load_jsonl(args.perturbed)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["delta"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
