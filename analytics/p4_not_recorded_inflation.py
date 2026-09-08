#!/usr/bin/env python3
"""Create a deterministic not_recorded-inflation synthetic fixture for P4."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

try:
    from .run_30_day_synthetic_readiness import build_events
except ImportError:  # pragma: no cover
    from run_30_day_synthetic_readiness import build_events


def inflate(events: list[dict[str, Any]], start: str, end: str, every: int = 2) -> tuple[list[dict[str, Any]], int]:
    start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
    if every < 1 or end_day < start_day:
        raise ValueError("invalid interval or cadence")
    changed = 0
    eligible_index = 0
    output = []
    for item in events:
        copy = dict(item)
        item_day = date.fromisoformat(item["localDate"])
        eligible = item["source"] == "medication-promise" and item["missingness"] == "observed" and start_day <= item_day <= end_day
        if eligible:
            if eligible_index % every == 0:
                copy["missingness"] = "not_recorded"
                copy["payload"] = {}
                changed += 1
            eligible_index += 1
        output.append(copy)
    return output, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", default="2035-01-11")
    parser.add_argument("--end", default="2035-01-17")
    parser.add_argument("--every", type=int, default=2)
    args = parser.parse_args()
    events, changed = inflate(build_events(), args.start, args.end, args.every)
    result = {"protocol": "P4-not-recorded-inflation-v1", "start": args.start, "end": args.end, "cadence": args.every, "inputEventCount": 271, "outputEventCount": len(events), "changedEventCount": changed, "events": events, "syntheticOnly": True, "note": "Explicit missingness perturbation; not a clinical result."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("changedEventCount", "outputEventCount")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
