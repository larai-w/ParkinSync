#!/usr/bin/env python3
"""Run and compare the three transparent P4 baseline evaluators."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from p4_logistic_baseline import evaluate as evaluate_logistic
from p4_logistic_baseline import fit as fit_logistic
from p4_majority_baseline import metrics as majority_metrics
from p4_tree_baseline import evaluate as evaluate_tree
from p4_tree_baseline import fit as fit_tree


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.labels.read_text(encoding="utf-8"))["rows"]
    first, second = max(1, int(len(rows) * 0.6)), max(2, int(len(rows) * 0.8))
    train, validation, test = rows[:first], rows[first:second], rows[second:]
    majority_count = sum(int(row["label_high_support_next_day"]) for row in train)
    majority_class = int(majority_count >= len(train) - majority_count)
    majority_probability = majority_count / len(train)
    logistic_params, _ = fit_logistic(train)
    tree_model = fit_tree(train)
    majority_validation = majority_metrics([int(row["label_high_support_next_day"]) for row in validation], majority_class, majority_probability)
    majority_test = majority_metrics([int(row["label_high_support_next_day"]) for row in test], majority_class, majority_probability)
    result = {
        "protocol": "P4-baseline-comparison-v1",
        "split": {"train": len(train), "validation": len(validation), "test": len(test)},
        "baselines": {
            "majority": {"validation": majority_validation, "test": majority_test},
            "logistic": {"validation": evaluate_logistic(validation, logistic_params), "test": evaluate_logistic(test, logistic_params)},
            "treeStump": {"validation": evaluate_tree(validation, tree_model), "test": evaluate_tree(test, tree_model)},
        },
        "syntheticOnly": True,
        "note": "Comparison manifest for contract smoke tests; not a clinical or deployment performance claim.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["baselines"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
