#!/usr/bin/env python3
"""Run a deterministic severity sweep for P4 block missingness."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

try:
    from .p4_missingness_perturbation import perturb
    from .run_30_day_synthetic_readiness import build_events, build_report
except ImportError:  # pragma: no cover - direct file execution
    from p4_missingness_perturbation import perturb
    from run_30_day_synthetic_readiness import build_events, build_report


def run_sweep(source: str, start: str, lengths: list[int]) -> dict[str, Any]:
    clean_report = build_report(build_events())
    rows: list[dict[str, Any]] = []
    start_day = date.fromisoformat(start)
    for length in lengths:
        end = (start_day + timedelta(days=length - 1)).isoformat()
        events, removed = perturb(build_events(), source, start, end)
        report = build_report(events)
        rows.append(
            {
                "lengthDays": length,
                "start": start,
                "end": end,
                "removedEventCount": removed,
                "medicationCoverageRate": report["medicationSlotCoverage"]["rate"],
                "medicationCoverageRateDelta": round(report["medicationSlotCoverage"]["rate"] - clean_report["medicationSlotCoverage"]["rate"], 4),
                "sourceDayCoverage": report["sourceDayCoverage"].get(source, 0),
                "sourceDayCoverageDelta": report["sourceDayCoverage"].get(source, 0) - clean_report["sourceDayCoverage"].get(source, 0),
                "invalidEventCount": report["invalidEventCount"],
            }
        )
    return {
        "protocol": "P4-block-missingness-v1",
        "source": source,
        "start": start,
        "lengthsDays": lengths,
        "clean": {
            "medicationCoverageRate": clean_report["medicationSlotCoverage"]["rate"],
            "sourceDayCoverage": clean_report["sourceDayCoverage"].get(source, 0),
        },
        "conditions": rows,
        "interpretation": "Synthetic severity sweep only; not a clinical or product-performance result.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", default="medication-promise")
    parser.add_argument("--start", default="2035-01-11")
    parser.add_argument("--lengths", nargs="+", type=int, default=[1, 2, 4, 7])
    args = parser.parse_args()
    if any(length < 1 for length in args.lengths):
        parser.error("lengths must be positive")
    result = run_sweep(args.source, args.start, args.lengths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["conditions"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
