#!/usr/bin/env python3
"""Create a deterministic P4 block-missingness perturbation fixture.

The source fixture is synthetic only.  A contiguous date block is removed for
one source to model a pipeline outage; this script does not claim clinical or
product-performance validity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

try:  # Support both direct script execution and package-style imports.
    from .run_30_day_synthetic_readiness import build_events
except ImportError:  # pragma: no cover - exercised when invoked by file path.
    from run_30_day_synthetic_readiness import build_events


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def perturb(events: list[dict], source: str, start: str, end: str) -> tuple[list[dict], int]:
    start_day = date.fromisoformat(start)
    end_day = date.fromisoformat(end)
    if end_day < start_day:
        raise ValueError("end must be on or after start")
    kept: list[dict] = []
    removed = 0
    for item in events:
        item_day = date.fromisoformat(item["localDate"])
        if item["source"] == source and start_day <= item_day <= end_day:
            removed += 1
        else:
            kept.append(item)
    return kept, removed


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in events), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/parkinsync-p4-missingness"))
    parser.add_argument("--source", default="medication-promise")
    parser.add_argument("--start", default="2035-01-11")
    parser.add_argument("--end", default="2035-01-12")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    clean_path = args.output_dir / "clean-events.jsonl"
    perturbed_path = args.output_dir / "block-missingness-events.jsonl"
    clean = build_events()
    perturbed, removed = perturb(clean, args.source, args.start, args.end)
    write_jsonl(clean_path, clean)
    write_jsonl(perturbed_path, perturbed)
    manifest = {
        "protocol": "P4-block-missingness-v1",
        "defectType": "contiguous_source_date_block_removed",
        "source": args.source,
        "start": args.start,
        "end": args.end,
        "inputEventCount": len(clean),
        "outputEventCount": len(perturbed),
        "removedEventCount": removed,
        "inputSha256": _sha256(clean_path),
        "outputSha256": _sha256(perturbed_path),
        "syntheticOnly": True,
        "note": "Fixture for pipeline/ML robustness rehearsal; not a clinical result.",
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
