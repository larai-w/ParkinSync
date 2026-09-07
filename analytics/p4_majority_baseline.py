#!/usr/bin/env python3
"""Evaluate a transparent majority-class baseline on the frozen P4 labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def metrics(y_true: list[int], prediction: int, probability: float) -> dict[str, float]:
    accuracy = sum(actual == prediction for actual in y_true) / len(y_true) if y_true else 0.0
    positives = [actual for actual in y_true if actual == 1]
    negatives = [actual for actual in y_true if actual == 0]
    recalls = []
    if positives:
        recalls.append(sum(prediction == 1 for _ in positives) / len(positives))
    if negatives:
        recalls.append(sum(prediction == 0 for _ in negatives) / len(negatives))
    brier = sum((probability - actual) ** 2 for actual in y_true) / len(y_true) if y_true else 0.0
    return {"accuracy": round(accuracy, 4), "balancedAccuracy": round(sum(recalls) / len(recalls), 4) if recalls else 0.0, "brier": round(brier, 4)}


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload["rows"]
    if len(rows) < 5:
        raise ValueError("at least five rows are required for chronological split")
    first = max(1, int(len(rows) * 0.6))
    second = max(first + 1, int(len(rows) * 0.8))
    splits = {"train": rows[:first], "validation": rows[first:second], "test": rows[second:]}
    train_labels = [int(row["label_high_support_next_day"]) for row in splits["train"]]
    count_one = sum(train_labels)
    prediction = int(count_one >= len(train_labels) - count_one)
    probability = count_one / len(train_labels)
    return {
        "protocol": "P4-majority-baseline-v1",
        "labelProtocol": payload.get("protocol"),
        "split": {name: len(items) for name, items in splits.items()},
        "trainClassCounts": {"0": len(train_labels) - count_one, "1": count_one},
        "predictedClass": prediction,
        "predictedProbability": round(probability, 4),
        "metrics": {name: metrics([int(row["label_high_support_next_day"]) for row in items], prediction, probability) for name, items in splits.items() if name != "train"},
        "syntheticOnly": True,
        "note": "Transparent contract smoke test; not a clinical or deployment performance claim.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(json.loads(args.labels.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
