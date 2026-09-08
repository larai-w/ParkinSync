#!/usr/bin/env python3
"""Exercise the reviewed source-conflation policy on synthetic events."""

from __future__ import annotations

import argparse
import copy
import json
from collections import defaultdict
from pathlib import Path

try:
    from .run_30_day_synthetic_readiness import build_events
except ImportError:  # pragma: no cover
    from run_30_day_synthetic_readiness import build_events


def conflate(events: list[dict], count: int = 3) -> tuple[list[dict], int]:
    output = list(events)
    selected = [item for item in events if item["source"] == "medication-promise"][:count]
    for item in selected:
        copy_item = copy.deepcopy(item)
        copy_item["source"] = "gutpacer"
        output.append(copy_item)
    return output, len(selected)


def detect(events: list[dict]) -> list[dict]:
    sources: defaultdict[str, set[str]] = defaultdict(set)
    for item in events:
        sources[item["eventId"]].add(item["source"])
    return [{"eventId": event_id, "sources": sorted(values)} for event_id, values in sorted(sources.items()) if len(values) > 1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=3)
    args = parser.parse_args()
    events, added = conflate(build_events(), args.count)
    collisions = detect(events)
    result = {"protocol": "P4-source-conflation-v1", "collisionUnit": "eventId with multiple source values", "policy": "REVIEW", "inputEventCount": 271, "outputEventCount": len(events), "addedCollisionCount": added, "detectedCollisionCount": len(collisions), "collisions": collisions, "syntheticOnly": True, "note": "Source collision is reviewable, not automatically invalid; no authoritative source is inferred."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("policy", "addedCollisionCount", "detectedCollisionCount")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
