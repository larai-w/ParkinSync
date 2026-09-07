#!/usr/bin/env python3
"""Evaluate a deterministic one-split tree baseline for P4."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FEATURES = ["weatherAvg", "indoorTemperatureAvg", "previousConditionNum"]


def fit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    best: tuple[float, int, str, float, int, int] | None = None
    for feature_index, feature in enumerate(FEATURES):
        values = sorted({float(row[feature] or 0.0) for row in rows})
        thresholds = [(a + b) / 2 for a, b in zip(values, values[1:])]
        for threshold in thresholds:
            for left_class in (0, 1):
                right_class = 1 - left_class
                correct = sum((left_class if float(row[feature] or 0.0) <= threshold else right_class) == int(row["label_high_support_next_day"]) for row in rows)
                candidate = (correct / len(rows), -feature_index, feature, -threshold, left_class, right_class)
                if best is None or candidate > best:
                    best = candidate
    if best is None:
        raise ValueError("at least two distinct feature values are required")
    score, _, feature, neg_threshold, left_class, right_class = best
    return {"feature": feature, "threshold": -neg_threshold, "leftClass": left_class, "rightClass": right_class, "trainAccuracy": round(score, 4)}


def evaluate(rows: list[dict[str, Any]], model: dict[str, Any]) -> dict[str, float]:
    predictions = [model["leftClass"] if float(row[model["feature"]] or 0.0) <= model["threshold"] else model["rightClass"] for row in rows]
    labels = [int(row["label_high_support_next_day"]) for row in rows]
    return {"accuracy": round(sum(prediction == label for prediction, label in zip(predictions, labels)) / len(labels), 4)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.labels.read_text(encoding="utf-8"))["rows"]
    first, second = max(1, int(len(rows) * 0.6)), max(2, int(len(rows) * 0.8))
    train, validation, test = rows[:first], rows[first:second], rows[second:]
    model = fit(train)
    result = {"protocol": "P4-tree-stump-baseline-v1", "features": FEATURES, "split": {"train": len(train), "validation": len(validation), "test": len(test)}, "model": model, "metrics": {"validation": evaluate(validation, model), "test": evaluate(test, model)}, "syntheticOnly": True, "note": "One-split transparent smoke test; not a clinical or deployment performance claim."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
