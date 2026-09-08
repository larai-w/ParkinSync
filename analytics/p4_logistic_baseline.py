#!/usr/bin/env python3
"""Small, dependency-free logistic baseline for the frozen P4 labels."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from .p4_metrics import auroc, expected_calibration_error, pr_auc
except ImportError:  # pragma: no cover
    from p4_metrics import auroc, expected_calibration_error, pr_auc


FEATURES = ["weatherAvg", "indoorTemperatureAvg", "previousConditionNum"]


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, value))))


def fit(rows: list[dict[str, Any]], steps: int = 2000, learning_rate: float = 0.05) -> tuple[list[float], float]:
    means = [sum(float(row[name] or 0.0) for row in rows) / len(rows) for name in FEATURES]
    scales = [max(1.0, math.sqrt(sum((float(row[name] or 0.0) - means[i]) ** 2 for row in rows) / len(rows))) for i, name in enumerate(FEATURES)]
    weights = [0.0] * len(FEATURES)
    bias = 0.0
    for _ in range(steps):
        grad_w = [0.0] * len(FEATURES)
        grad_b = 0.0
        for row in rows:
            x = [(float(row[name] or 0.0) - means[i]) / scales[i] for i, name in enumerate(FEATURES)]
            y = int(row["label_high_support_next_day"])
            error = sigmoid(bias + sum(w * value for w, value in zip(weights, x))) - y
            grad_b += error
            for i, value in enumerate(x):
                grad_w[i] += error * value
        bias -= learning_rate * grad_b / len(rows)
        weights = [w - learning_rate * g / len(rows) for w, g in zip(weights, grad_w)]
    return [*weights, bias, *means, *scales], bias


def evaluate(rows: list[dict[str, Any]], params: list[float]) -> dict[str, float]:
    weights, bias = params[:3], params[3]
    means, scales = params[4:7], params[7:10]
    probabilities = []
    labels = []
    for row in rows:
        x = [(float(row[name] or 0.0) - means[i]) / scales[i] for i, name in enumerate(FEATURES)]
        probabilities.append(sigmoid(bias + sum(w * value for w, value in zip(weights, x))))
        labels.append(int(row["label_high_support_next_day"]))
    predictions = [int(probability >= 0.5) for probability in probabilities]
    return {
        "accuracy": round(sum(prediction == label for prediction, label in zip(predictions, labels)) / len(labels), 4),
        "brier": round(sum((probability - label) ** 2 for probability, label in zip(probabilities, labels)) / len(labels), 4),
        "auroc": auroc(labels, probabilities),
        "prAuc": pr_auc(labels, probabilities),
        "ece": expected_calibration_error(labels, probabilities),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.labels.read_text(encoding="utf-8"))["rows"]
    first, second = max(1, int(len(rows) * 0.6)), max(2, int(len(rows) * 0.8))
    train, validation, test = rows[:first], rows[first:second], rows[second:]
    params, _ = fit(train)
    result = {"protocol": "P4-logistic-baseline-v1", "features": FEATURES, "split": {"train": len(train), "validation": len(validation), "test": len(test)}, "metrics": {"validation": evaluate(validation, params), "test": evaluate(test, params)}, "syntheticOnly": True, "note": "Dependency-free smoke test; not a clinical or deployment performance claim."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
