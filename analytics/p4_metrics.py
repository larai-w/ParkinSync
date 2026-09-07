"""Dependency-free binary ranking metrics for P4 smoke tests."""

from __future__ import annotations


def auroc(labels: list[int], probabilities: list[float]) -> float | None:
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    order = sorted(range(len(labels)), key=lambda index: probabilities[index])
    rank_sum = sum(rank + 1 for rank, index in enumerate(order) if labels[index] == 1)
    return round((rank_sum - positives * (positives + 1) / 2) / (positives * negatives), 4)


def pr_auc(labels: list[int], probabilities: list[float]) -> float | None:
    positives = sum(labels)
    if not positives:
        return None
    order = sorted(range(len(labels)), key=lambda index: probabilities[index], reverse=True)
    true_positive = false_positive = 0
    points = [(0.0, 1.0)]
    for index in order:
        if labels[index]:
            true_positive += 1
        else:
            false_positive += 1
        points.append((true_positive / positives, true_positive / (true_positive + false_positive)))
    area = sum((recall - previous_recall) * precision for (recall, precision), (previous_recall, _) in zip(points[1:], points))
    return round(area, 4)


def expected_calibration_error(labels: list[int], probabilities: list[float], bins: int = 5) -> float:
    if not labels:
        return 0.0
    error = 0.0
    for bucket in range(bins):
        low, high = bucket / bins, (bucket + 1) / bins
        indices = [i for i, probability in enumerate(probabilities) if low <= probability < high or (bucket == bins - 1 and probability == high)]
        if indices:
            confidence = sum(probabilities[i] for i in indices) / len(indices)
            accuracy = sum(labels[i] for i in indices) / len(indices)
            error += len(indices) / len(labels) * abs(confidence - accuracy)
    return round(error, 4)
