#!/usr/bin/env python3
"""Create a deterministic schema-version drift fixture for P4."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import date
from pathlib import Path

try:
    from .run_30_day_synthetic_readiness import build_events, build_report
except ImportError:  # pragma: no cover
    from run_30_day_synthetic_readiness import build_events, build_report


def drift(events: list[dict], start: str, end: str, every: int = 5) -> tuple[list[dict], int]:
    start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
    if every < 1 or end_day < start_day:
        raise ValueError("invalid interval or cadence")
    output, eligible, changed = [], 0, 0
    for item in events:
        copy_item = copy.deepcopy(item)
        item_day = date.fromisoformat(item["localDate"])
        if item["source"] == "medication-promise" and start_day <= item_day <= end_day:
            if eligible % every == 0:
                copy_item["schemaVersion"] = "care-event/v2-drift"
                changed += 1
            eligible += 1
        output.append(copy_item)
    return output, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", default="2035-01-11")
    parser.add_argument("--end", default="2035-01-17")
    parser.add_argument("--every", type=int, default=5)
    args = parser.parse_args()
    events, changed = drift(build_events(), args.start, args.end, args.every)
    report = build_report(events)
    result = {"protocol": "P4-schema-drift-v1", "start": args.start, "end": args.end, "cadence": args.every, "inputEventCount": 271, "outputEventCount": len(events), "driftedEventCount": changed, "invalidEventCount": report["invalidEventCount"], "events": events, "syntheticOnly": True, "note": "Schema-version integrity perturbation; not a clinical result."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("driftedEventCount", "invalidEventCount")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
