"""Dependency-free binary metrics; pr_auc is threshold-grouped average precision."""
from __future__ import annotations
import math


def validate(labels, probabilities):
    if len(labels) != len(probabilities):
        raise ValueError('labels and probabilities must have equal lengths')
    if any(type(y) is not int or y not in (0, 1) for y in labels):
        raise ValueError('labels must be binary integers')
    if any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities):
        raise ValueError('probabilities must be finite and between zero and one')


def auroc(labels: list[int], probabilities: list[float]) -> float | None:
    validate(labels, probabilities)
    positives, negatives = sum(labels), len(labels) - sum(labels)
    if not positives or not negatives:
        return None
    # Pairwise definition gives a tied positive/negative pair half credit.
    wins = sum((p > n) + 0.5 * (p == n)
               for y, p in zip(labels, probabilities) if y == 1
               for other, n in zip(labels, probabilities) if other == 0)
    return round(wins / (positives * negatives), 4)


def pr_auc(labels: list[int], probabilities: list[float]) -> float | None:
    """Average precision, not trapezoidal PR area; include equal scores together."""
    validate(labels, probabilities)
    positives = sum(labels)
    if not positives:
        return None
    tp = fp = 0
    area = 0.0
    for score in sorted(set(probabilities), reverse=True):
        group = [y for y, p in zip(labels, probabilities) if p == score]
        added = sum(group)
        tp += added
        fp += len(group) - added
        area += (added / positives) * tp / (tp + fp)
    return round(area, 4)


def expected_calibration_error(labels: list[int], probabilities: list[float], bins: int = 5) -> float:
    validate(labels, probabilities)
    if type(bins) is not int or bins < 1:
        raise ValueError('bins must be a positive integer')
    if not labels:
        return 0.0  # Legacy empty-fixture convention; not evidence of calibration.
    error = 0.0
    for bucket in range(bins):
        low, high = bucket / bins, (bucket + 1) / bins
        indices = [i for i, probability in enumerate(probabilities) if low <= probability < high or (bucket == bins - 1 and probability == high)]
        if indices:
            confidence = sum(probabilities[i] for i in indices) / len(indices)
            accuracy = sum(labels[i] for i in indices) / len(indices)
            error += len(indices) / len(labels) * abs(confidence - accuracy)
    return round(error, 4)
