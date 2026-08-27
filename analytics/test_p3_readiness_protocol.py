#!/usr/bin/env python3
"""Executable contract tests for the P3 readiness protocol."""

from __future__ import annotations

from copy import deepcopy

from p3_readiness_protocol import (
    build_protocol_fixture,
    build_report,
    compute_metrics,
    validate,
)


def _assert_check(report: dict, name: str, status: str) -> None:
    matches = [item for item in report["gates"]["checks"] if item["check"] == name]
    assert len(matches) == 1, matches
    assert matches[0]["status"] == status, matches[0]


def test_clean_fixture() -> None:
    report = build_report(build_protocol_fixture(), "synthetic", False)
    metrics = report["metrics"]

    assert metrics["inputEventCount"] == 271
    assert metrics["uniqueValidEventCount"] == 270
    assert metrics["invalidEventCount"] == 0
    assert metrics["duplicateEventCount"] == 1
    assert metrics["adherenceLabel"] == {
        "taken": 90,
        "missed": 30,
        "usableLabelCount": 120,
        "minorityClassShare": 0.25,
    }
    assert metrics["notRecordedShare"] == 0.2
    assert metrics["labelAvailability"] == 0.8
    assert report["gates"]["dataQualityGate"] == "ANALYZE_OK"
    assert report["gates"]["researchReleaseGate"] == "NOT_YET"
    assert {item["status"] for item in report["gates"]["checks"]} == {"PASS"}


def test_missingness_is_not_an_adherence_outcome() -> None:
    events = build_protocol_fixture()
    metrics = compute_metrics(events)
    not_recorded_medication = [
        item
        for item in events
        if item["eventType"] in ("medication_taken", "medication_missed")
        and item["missingness"] == "not_recorded"
    ]
    observed_missed = [
        item
        for item in events
        if item["eventType"] == "medication_missed" and item["missingness"] == "observed"
    ]

    assert len(not_recorded_medication) == 30
    assert len(observed_missed) == 30
    assert len({item["localDate"] for item in observed_missed}) == 30
    assert {item["payload"]["timing"] for item in observed_missed} == {"夜8時"}
    assert metrics["adherenceLabel"]["usableLabelCount"] == 120
    assert metrics["adherenceLabel"]["taken"] + metrics["adherenceLabel"]["missed"] == 120


def test_canonical_schema_rejects_constraints_old_check_missed() -> None:
    event = deepcopy(build_protocol_fixture()[0])
    event["unexpected"] = True
    event["occurredAt"] = "not-a-date-time"
    event["provenance"]["unexpected"] = True

    errors = validate(event)
    assert any("Additional properties" in item and "unexpected" in item for item in errors), errors
    assert any(item.startswith("occurredAt:") and "date-time" in item for item in errors), errors
    assert any(item.startswith("provenance:") and "Additional properties" in item for item in errors), errors
    assert validate("not-an-object") == ["$: 'not-an-object' is not of type 'object'"]

    report = build_report([*build_protocol_fixture(), "not-an-object"], "synthetic", False)
    assert report["metrics"]["invalidEventCount"] == 1
    _assert_check(report, "schema_validity", "FAIL")


def test_schema_failure_dominates_other_checks() -> None:
    events = build_protocol_fixture()
    events[0]["payload"] = "not-an-object"
    report = build_report(events, "synthetic", False)

    assert report["metrics"]["invalidEventCount"] == 1
    _assert_check(report, "schema_validity", "FAIL")
    assert report["gates"]["dataQualityGate"] == "NOT_READY"
    assert report["gates"]["researchReleaseGate"] == "NOT_YET"


def test_governance_flag_is_only_effective_for_real_label() -> None:
    events = build_protocol_fixture()
    synthetic = build_report(events, "synthetic", True)
    real_without_attestation = build_report(events, "real", False)
    real_with_attestation = build_report(events, "real", True)

    assert synthetic["gates"]["researchReleaseGate"] == "NOT_YET"
    assert real_without_attestation["gates"]["researchReleaseGate"] == "NOT_YET"
    assert real_with_attestation["gates"]["researchReleaseGate"] == "READY"


def main() -> int:
    tests = [
        test_clean_fixture,
        test_missingness_is_not_an_adherence_outcome,
        test_canonical_schema_rejects_constraints_old_check_missed,
        test_schema_failure_dominates_other_checks,
        test_governance_flag_is_only_effective_for_real_label,
    ]
    for test in tests:
        test()
    print(f"p3 readiness protocol tests: GREEN ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
