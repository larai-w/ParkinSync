from __future__ import annotations

import unittest

from p4_logistic_baseline import evaluate as eval_logistic, fit as fit_logistic
from p4_majority_baseline import metrics as eval_majority
from p4_synthetic_labels import build_label_rows
from p4_tree_baseline import evaluate as eval_tree, fit as fit_tree
from run_30_day_synthetic_readiness import build_events


class BaselineDeterminismTest(unittest.TestCase):
    def test_repeated_fits_are_identical(self) -> None:
        rows = build_label_rows(build_events())
        train, test = rows[:17], rows[23:]
        logistic_a = fit_logistic(train)[0]
        logistic_b = fit_logistic(train)[0]
        self.assertEqual(logistic_a, logistic_b)
        self.assertEqual(eval_logistic(test, logistic_a), eval_logistic(test, logistic_b))
        tree_a = fit_tree(train)
        tree_b = fit_tree(train)
        self.assertEqual(tree_a, tree_b)
        self.assertEqual(eval_tree(test, tree_a), eval_tree(test, tree_b))

    def test_majority_metrics_are_stable(self) -> None:
        labels = [0, 0, 1, 0]
        self.assertEqual(eval_majority(labels, 0, 0.75), eval_majority(labels, 0, 0.75))


if __name__ == "__main__":
    unittest.main()
