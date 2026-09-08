#!/usr/bin/env python3
"""Report pre-specified synthetic subgroup error rates for logistic baseline."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

try:
    from .p4_logistic_baseline import fit, sigmoid, FEATURES
except ImportError:  # pragma: no cover
    from p4_logistic_baseline import fit, sigmoid, FEATURES


def predict(rows: list[dict], params: list[float]) -> list[int]:
    weights, bias, means, scales = params[:3], params[3], params[4:7], params[7:10]
    output = []
    for row in rows:
        x = [(float(row[name] or 0.0) - means[i]) / scales[i] for i, name in enumerate(FEATURES)]
        output.append(int(sigmoid(bias + sum(w * value for w, value in zip(weights, x))) >= 0.5))
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.labels.read_text(encoding="utf-8"))["rows"]
    first, second = max(1, int(len(rows) * 0.6)), max(2, int(len(rows) * 0.8))
    train, test = rows[:first], rows[second:]
    predictions = predict(test, fit(train)[0])
    groups = {"weekday": [], "weekend": [], "early_window": [], "late_window": []}
    for row, prediction in zip(test, predictions):
        day = date.fromisoformat(row["localDate"])
        groups["weekend" if day.weekday() >= 5 else "weekday"].append((row, prediction))
        groups["late_window" if int(row["localDate"][-2:]) >= 15 else "early_window"].append((row, prediction))
    results = {}
    for name, members in groups.items():
        results[name] = {"count": len(members), "accuracy": round(sum(prediction == int(row["label_high_support_next_day"]) for row, prediction in members) / len(members), 4) if len(members) >= 2 else None}
    result = {"protocol": "P4-subgroup-metrics-v1", "split": {"train": len(train), "test": len(test)}, "groups": results, "minimumGroupCount": 2, "syntheticOnly": True, "note": "Fixture partitions only; not a demographic or clinical fairness analysis."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["groups"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
