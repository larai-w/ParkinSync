#!/usr/bin/env python3
"""Run a deterministic shuffled-label negative control for P4 logistic baseline."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from p4_logistic_baseline import evaluate, fit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260827)
    args = parser.parse_args()
    rows = json.loads(args.labels.read_text(encoding="utf-8"))["rows"]
    first, second = max(1, int(len(rows) * 0.6)), max(2, int(len(rows) * 0.8))
    labels = [int(row["label_high_support_next_day"]) for row in rows]
    random.Random(args.seed).shuffle(labels)
    shuffled = [dict(row, label_high_support_next_day=label) for row, label in zip(rows, labels)]
    train, validation, test = shuffled[:first], shuffled[first:second], shuffled[second:]
    params, _ = fit(train)
    result = {
        "protocol": "P4-negative-control-v1",
        "control": "fixed-seed label shuffle",
        "seed": args.seed,
        "split": {"train": len(train), "validation": len(validation), "test": len(test)},
        "metrics": {"validation": evaluate(validation, params), "test": evaluate(test, params)},
        "syntheticOnly": True,
        "note": "Negative-control smoke test; no pass/fail performance threshold is asserted here.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
