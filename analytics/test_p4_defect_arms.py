from __future__ import annotations

import unittest

from p4_duplicate_inflation import inflate as duplicate_inflate
from p4_label_imbalance import rebalance
from p4_provenance_removal import remove as provenance_remove
from p4_schema_drift import drift
from run_30_day_synthetic_readiness import build_events, build_report


class DefectArmTest(unittest.TestCase):
    def test_duplicate_arm_increases_duplicate_detection(self) -> None:
        events, added = duplicate_inflate(build_events(), "2035-01-11", "2035-01-17", 3)
        self.assertEqual(added, 12)
        self.assertEqual(build_report(events)["duplicateEventCount"], 13)

    def test_integrity_arms_fail_closed(self) -> None:
        events, changed = provenance_remove(build_events(), "2035-01-11", "2035-01-17", 4)
        self.assertEqual(changed, build_report(events)["invalidEventCount"])
        events, changed = drift(build_events(), "2035-01-11", "2035-01-17", 5)
        self.assertEqual(changed, build_report(events)["invalidEventCount"])

    def test_label_imbalance_preserves_schema_validity(self) -> None:
        events, changed = rebalance(build_events(), "2035-01-01", "2035-01-30", 4)
        report = build_report(events)
        self.assertEqual(changed, 31)
        self.assertEqual(report["invalidEventCount"], 0)
        self.assertEqual(report["eventTypeCounts"]["medication_taken"], 90)


if __name__ == "__main__":
    unittest.main()
