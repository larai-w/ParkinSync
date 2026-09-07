from __future__ import annotations

import unittest

from p4_metrics import auroc, expected_calibration_error, pr_auc


class MetricsTest(unittest.TestCase):
    def test_ranking_metrics_on_perfect_order(self) -> None:
        labels = [0, 0, 1, 1]
        probabilities = [0.1, 0.2, 0.8, 0.9]
        self.assertEqual(auroc(labels, probabilities), 1.0)
        self.assertEqual(pr_auc(labels, probabilities), 1.0)

    def test_undefined_auc_is_explicit(self) -> None:
        self.assertIsNone(auroc([1, 1], [0.2, 0.8]))
        self.assertIsNone(pr_auc([0, 0], [0.2, 0.8]))

    def test_empty_calibration_is_zero(self) -> None:
        self.assertEqual(expected_calibration_error([], []), 0.0)


if __name__ == "__main__":
    unittest.main()
