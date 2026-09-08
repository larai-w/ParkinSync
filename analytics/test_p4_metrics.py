from __future__ import annotations

import unittest
from itertools import permutations

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

    def test_constant_scores_do_not_depend_on_row_order(self):
        for labels in set(permutations([0, 0, 1, 1])):
            self.assertEqual(auroc(list(labels), [0.5] * 4), 0.5)
            self.assertEqual(pr_auc(list(labels), [0.5] * 4), 0.5)

    def test_mixed_ties(self):
        self.assertEqual(auroc([0, 1, 0, 1], [0.2, 0.5, 0.5, 0.8]), 0.875)
        self.assertEqual(pr_auc([0, 1, 0, 1], [0.2, 0.5, 0.5, 0.8]), 0.8333)

    def test_invalid_inputs_fail_instead_of_scoring(self):
        for labels, scores in [([1], []), ([2], [0.5]), ([True], [0.5]), ([1], [float('nan')]), ([1], [-0.1]), ([1], [1.1])]:
            for metric in (auroc, pr_auc, expected_calibration_error):
                with self.assertRaises(ValueError):
                    metric(labels, scores)
        with self.assertRaises(ValueError):
            expected_calibration_error([1], [0.5], bins=0)

    def test_empty_calibration_is_zero(self) -> None:
        self.assertEqual(expected_calibration_error([], []), 0.0)


if __name__ == "__main__":
    unittest.main()
