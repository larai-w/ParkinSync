#!/usr/bin/env python3
"""P3 analysis protocol as code — frozen ML-readiness / data-quality gate.

This is the *pre-specified and version-frozen* protocol for the P3 applied paper. The
metric definitions and decision thresholds below are FROZEN before real data is
seen, so that running on real data later is an input swap, not a code change and
not a threshold tweak (guards against p-hacking / post-hoc gate loosening).

Two independent axes, both fail-closed:
  1. data_quality_gate   -> ANALYZE_OK / HUMAN_REVIEW_REQUIRED / NOT_READY
                            (computed purely from the records)
  2. research_release_gate -> READY / NOT_YET
                            (requires an explicit operator attestation of external
                             governance clearance; synthetic input can NEVER reach
                             READY — pipeline PASS is not research readiness)

Input is care-event/v1 records. Default input is the synthetic 30-day fixture
reused from run_30_day_synthetic_readiness.py. When the governance gate passes,
point --input at an approved restricted-environment export instead; the protocol
is unchanged.

No participant, household, or production data. Synthetic only unless an operator
supplies real input after completing the external governance process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ModuleNotFoundError as exc:  # pragma: no cover - exercised by environment setup
    raise SystemExit(
        "P3 requires jsonschema. Install with: "
        "python3 -m pip install -r analytics/requirements-p3.txt"
    ) from exc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_30_day_synthetic_readiness import (  # noqa: E402
    build_events,
)

# --- FROZEN protocol (v1). Do not tune to fit a dataset. -------------------
PROTOCOL_VERSION = "p3-readiness-protocol/v1"
WINDOW_DAYS = 30
MEDICATION_SLOTS_PER_DAY = 5
SOURCES = ("medication-promise", "gutpacer", "parkinsync")
# Canonical public schema is owned by the GutPacer/ParkinSync contract fixture.
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "poc" / "gutpacer-parkinsync" / "schema" / "care-event-v1.schema.json"
EXPECTED_SCHEMA_SEMANTIC_SHA256 = "ca5844dba90e247015d3c8ad8bd1ffc6986c7b598e96ab67452d6a8d2817da7e"

_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
_SCHEMA_SEMANTIC_SHA256 = hashlib.sha256(
    json.dumps(_SCHEMA, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
if _SCHEMA_SEMANTIC_SHA256 != EXPECTED_SCHEMA_SEMANTIC_SHA256:
    raise RuntimeError(
        "care-event/v1 schema drifted from the P3 v1 evidence lock: "
        f"expected {EXPECTED_SCHEMA_SEMANTIC_SHA256}, got {_SCHEMA_SEMANTIC_SHA256}"
    )
Draft202012Validator.check_schema(_SCHEMA)
_SCHEMA_VALIDATOR = Draft202012Validator(_SCHEMA, format_checker=FormatChecker())

# Thresholds are pre-specified and frozen. FAIL dominates REVIEW dominates PASS.
THRESHOLDS = {
    "invalid_count_max": 0,            # any schema-invalid record -> FAIL
    "duplicate_rate_review": 0.05,     # > -> REVIEW
    "day_coverage_review": 0.90,       # distinct days / window < -> REVIEW
    "day_coverage_fail": 0.50,         # < -> FAIL (too sparse to analyze)
    "source_day_coverage_review": 0.80,  # per-source day coverage < -> REVIEW
    "max_gap_days_review": 2,          # longest run of fully-missing days > -> REVIEW
    "not_recorded_share_review": 0.20,  # not_recorded / med slots > -> REVIEW
    "class_balance_review": 0.10,      # minority adherence class share < -> REVIEW
    "label_availability_review": 0.80,  # usable labels / expected slots < -> REVIEW
}
# --------------------------------------------------------------------------


def build_protocol_fixture() -> list[dict]:
    """Derive the P3 fixture while keeping outcome labels separate from missingness.

    The shared 30-day fixture contains 120 observed medication events and 30
    not-recorded slots. The same observed slot on each day (20:00) is
    deterministically relabelled as a missed dose, yielding 90 taken and 30
    missed usable labels. Not-recorded slots remain unavailable labels and never
    count as missed doses.
    """
    events = build_events()
    relabelled = 0
    for item in events:
        if (
            item.get("eventType") == "medication_taken"
            and item.get("missingness") == "observed"
            and item.get("payload", {}).get("timing") == "夜8時"
        ):
            item["eventType"] = "medication_missed"
            relabelled += 1
    if relabelled != 30:
        raise RuntimeError(f"P3 fixture expected 30 observed missed labels; got {relabelled}")
    return events


def validate(item: object) -> list[str]:
    """Validate one event against the canonical care-event/v1 JSON Schema."""
    errors = sorted(_SCHEMA_VALIDATOR.iter_errors(item), key=lambda err: list(err.absolute_path))
    rendered: list[str] = []
    for error in errors:
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        rendered.append(f"{path}: {error.message}")
    return rendered


def _dedupe(events: list[object]) -> tuple[list[dict], int, list[dict]]:
    invalid: list[dict] = []
    seen: set[str] = set()
    unique: list[dict] = []
    duplicates = 0
    for index, item in enumerate(events):
        errs = validate(item)
        if errs:
            event_id = item.get("eventId") if isinstance(item, dict) else None
            invalid.append({"index": index, "eventId": event_id, "errors": errs})
            continue
        assert isinstance(item, dict)  # guaranteed by the schema validator
        if item["eventId"] in seen:
            duplicates += 1
            continue
        seen.add(item["eventId"])
        unique.append(item)
    return unique, duplicates, invalid


def _window_days(unique: list[dict]) -> list[str]:
    dates = sorted({item["localDate"] for item in unique})
    if not dates:
        return []
    start = date.fromisoformat(dates[0])
    span = (date.fromisoformat(dates[-1]) - start).days + 1
    span = max(span, WINDOW_DAYS)
    return [(start + timedelta(days=i)).isoformat() for i in range(span)]


def _max_missing_gap(unique: list[dict], window: list[str]) -> int:
    observed_days = {
        item["localDate"] for item in unique if item["missingness"] == "observed"
    }
    longest = current = 0
    for day in window:
        if day in observed_days:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def compute_metrics(events: list[object]) -> dict:
    unique, duplicates, invalid = _dedupe(events)
    window = _window_days(unique)
    window_len = len(window) or WINDOW_DAYS

    by_day: defaultdict[str, list[dict]] = defaultdict(list)
    for item in unique:
        by_day[item["localDate"]].append(item)

    source_day_coverage = {
        s: len({i["localDate"] for i in unique if i["source"] == s}) for s in SOURCES
    }

    med = [i for i in unique if i["eventType"] in ("medication_taken", "medication_missed")]
    usable_labels = [i for i in med if i["missingness"] == "observed"]
    taken = sum(1 for i in usable_labels if i["eventType"] == "medication_taken")
    missed = sum(1 for i in usable_labels if i["eventType"] == "medication_missed")
    med_total = taken + missed
    minority_share = (min(taken, missed) / med_total) if med_total else 0.0

    not_recorded = sum(1 for i in med if i["missingness"] == "not_recorded")
    expected_slots = window_len * MEDICATION_SLOTS_PER_DAY
    not_recorded_share = (not_recorded / expected_slots) if expected_slots else 0.0

    label_availability = (len(usable_labels) / expected_slots) if expected_slots else 0.0

    dup_rate = (duplicates / len(events)) if events else 0.0
    day_coverage = (len(by_day) / window_len) if window_len else 0.0
    max_gap = _max_missing_gap(unique, window)

    return {
        "inputEventCount": len(events),
        "uniqueValidEventCount": len(unique),
        "invalidEventCount": len(invalid),
        "duplicateEventCount": duplicates,
        "duplicateRate": round(dup_rate, 4),
        "windowDays": window_len,
        "distinctDayCount": len(by_day),
        "dayCoverage": round(day_coverage, 4),
        "sourceDayCoverage": source_day_coverage,
        "maxMissingGapDays": max_gap,
        "missingnessCounts": dict(sorted(Counter(i["missingness"] for i in unique).items())),
        "eventTypeCounts": dict(sorted(Counter(i["eventType"] for i in unique).items())),
        "adherenceLabel": {
            "taken": taken,
            "missed": missed,
            "usableLabelCount": med_total,
            "minorityClassShare": round(minority_share, 4),
        },
        "notRecordedShare": round(not_recorded_share, 4),
        "labelAvailability": round(label_availability, 4),
        "invalid": invalid,
    }


def evaluate_gates(metrics: dict, data_label: str, governance_cleared: bool) -> dict:
    checks: list[dict] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"check": name, "status": status, "detail": detail})

    t = THRESHOLDS

    add(
        "schema_validity",
        "FAIL" if metrics["invalidEventCount"] > t["invalid_count_max"] else "PASS",
        f"invalid={metrics['invalidEventCount']} (max {t['invalid_count_max']})",
    )
    dc = metrics["dayCoverage"]
    add(
        "day_coverage",
        "FAIL" if dc < t["day_coverage_fail"] else ("REVIEW" if dc < t["day_coverage_review"] else "PASS"),
        f"{dc:.2%} of {metrics['windowDays']} days",
    )
    add(
        "duplicate_rate",
        "REVIEW" if metrics["duplicateRate"] > t["duplicate_rate_review"] else "PASS",
        f"{metrics['duplicateRate']:.2%}",
    )
    worst_src = min(metrics["sourceDayCoverage"].values(), default=0) / metrics["windowDays"]
    add(
        "source_day_coverage",
        "REVIEW" if worst_src < t["source_day_coverage_review"] else "PASS",
        f"worst source {worst_src:.2%}",
    )
    add(
        "temporal_continuity",
        "REVIEW" if metrics["maxMissingGapDays"] > t["max_gap_days_review"] else "PASS",
        f"max gap {metrics['maxMissingGapDays']} days",
    )
    add(
        "not_recorded_share",
        "REVIEW" if metrics["notRecordedShare"] > t["not_recorded_share_review"] else "PASS",
        f"{metrics['notRecordedShare']:.2%}",
    )
    add(
        "class_balance",
        "REVIEW" if metrics["adherenceLabel"]["minorityClassShare"] < t["class_balance_review"] else "PASS",
        f"minority share {metrics['adherenceLabel']['minorityClassShare']:.2%}",
    )
    add(
        "label_availability",
        "REVIEW" if metrics["labelAvailability"] < t["label_availability_review"] else "PASS",
        f"{metrics['labelAvailability']:.2%}",
    )

    statuses = {c["status"] for c in checks}
    if "FAIL" in statuses:
        data_quality_gate = "NOT_READY"
    elif "REVIEW" in statuses:
        data_quality_gate = "HUMAN_REVIEW_REQUIRED"
    else:
        data_quality_gate = "ANALYZE_OK"

    # Research release is fail-closed: synthetic can never be READY, and real
    # data needs an operator attestation of external governance clearance AND a clean gate.
    if data_label == "real" and governance_cleared and data_quality_gate == "ANALYZE_OK":
        research_release_gate = "READY"
        research_reason = "real data + operator clearance attestation + data quality ANALYZE_OK"
    else:
        research_release_gate = "NOT_YET"
        if data_label != "real":
            research_reason = "synthetic input — pipeline PASS is not research readiness"
        elif not governance_cleared:
            research_reason = "operator clearance attestation not provided"
        else:
            research_reason = f"data quality gate is {data_quality_gate}, not ANALYZE_OK"

    return {
        "dataQualityGate": data_quality_gate,
        "researchReleaseGate": research_release_gate,
        "researchReason": research_reason,
        "checks": checks,
    }


def build_report(events: list[object], data_label: str, governance_cleared: bool) -> dict:
    metrics = compute_metrics(events)
    gates = evaluate_gates(metrics, data_label, governance_cleared)
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "schemaEvidenceLock": {
            "id": _SCHEMA.get("$id"),
            "draft": _SCHEMA.get("$schema"),
            "semanticSha256": _SCHEMA_SEMANTIC_SHA256,
        },
        "dataLabel": data_label,
        "governanceCleared": governance_cleared,
        "thresholds": THRESHOLDS,
        "metrics": metrics,
        "gates": gates,
        "privacy": "Synthetic pseudonymous fixture unless an operator supplied real input after external governance clearance.",
        "limitations": [
            "Pre-specified, version-frozen data-quality / ML-readiness protocol, not a preregistration, model-performance, or clinical result.",
            "On synthetic input, ANALYZE_OK reflects pipeline readiness only; research release stays NOT_YET by design.",
            "Thresholds are frozen (v1) and must not be tuned to a dataset after the fact.",
        ],
    }


def markdown(report: dict) -> str:
    m, g = report["metrics"], report["gates"]
    lines = [
        f"# P3 readiness protocol report ({report['protocolVersion']})",
        "",
        f"- data label: **{report['dataLabel']}** / governance cleared: **{report['governanceCleared']}**",
        f"- input events: **{m['inputEventCount']}** / unique valid: **{m['uniqueValidEventCount']}** / invalid: **{m['invalidEventCount']}** / duplicate: **{m['duplicateEventCount']}**",
        f"- day coverage: **{m['dayCoverage']:.0%}** of {m['windowDays']} / max missing gap: **{m['maxMissingGapDays']}d**",
        "",
        "## Gate decision",
        "",
        f"- **Data-quality gate:** {g['dataQualityGate']}",
        f"- **Research-release gate:** {g['researchReleaseGate']} — {g['researchReason']}",
        "",
        "## Checks",
        "",
        "| check | status | detail |",
        "|---|---|---|",
    ]
    for c in g["checks"]:
        lines.append(f"| {c['check']} | {c['status']} | {c['detail']} |")
    lines += [
        "",
        "## Notes",
        "",
        *[f"- {x}" for x in report["limitations"]],
    ]
    return "\n".join(lines) + "\n"


def _degrade(events: list[dict]) -> list[dict]:
    """Self-test fixture: break class balance, labels, and add an invalid record."""
    degraded = [e.copy() for e in events if e["eventType"] != "medication_taken"]
    # every medication event becomes not_recorded -> no observed labels, no balance
    for e in degraded:
        if e["eventType"] == "medication_missed":
            e["missingness"] = "not_recorded"
    bad = events[0].copy()
    bad.pop("provenance", None)  # schema-invalid
    bad["eventId"] = "bad-1"
    degraded.append(bad)
    return degraded


def self_test() -> int:
    clean = build_report(build_protocol_fixture(), "synthetic", False)
    assert clean["gates"]["dataQualityGate"] == "ANALYZE_OK", clean["gates"]
    assert clean["gates"]["researchReleaseGate"] == "NOT_YET", "synthetic must never be READY"
    assert clean["metrics"]["adherenceLabel"] == {
        "taken": 90,
        "missed": 30,
        "usableLabelCount": 120,
        "minorityClassShare": 0.25,
    }, clean["metrics"]["adherenceLabel"]
    assert clean["metrics"]["labelAvailability"] == 0.8, clean["metrics"]

    # even if someone lies about clearance on synthetic, research stays NOT_YET
    lied = build_report(build_protocol_fixture(), "synthetic", True)
    assert lied["gates"]["researchReleaseGate"] == "NOT_YET"

    degraded = build_report(_degrade(build_protocol_fixture()), "synthetic", False)
    assert degraded["gates"]["dataQualityGate"] == "NOT_READY", degraded["gates"]
    statuses = {c["status"] for c in degraded["gates"]["checks"]}
    assert "FAIL" in statuses

    # a clean real dataset with clearance would be READY (contract check, synthetic proxy)
    real_ready = build_report(build_protocol_fixture(), "real", True)
    assert real_ready["gates"]["researchReleaseGate"] == "READY", real_ready["gates"]

    print("p3 self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="P3 frozen readiness protocol")
    parser.add_argument("--input", type=Path, help="care-event/v1 JSON list (approved real export). Omit for synthetic.")
    parser.add_argument("--data-label", choices=("synthetic", "real"), default="synthetic")
    parser.add_argument(
        "--governance-cleared",
        action="store_true",
        help="operator attests external governance clearance; this flag does not verify approval",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/p3-readiness"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if args.input:
        events = json.loads(args.input.read_text(encoding="utf-8"))
        data_label = args.data_label
    else:
        events = build_protocol_fixture()
        data_label = "synthetic"  # no input => synthetic, regardless of flag

    report = build_report(events, data_label, args.governance_cleared)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "p3-readiness.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "p3-readiness.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"dataQualityGate": report["gates"]["dataQualityGate"], "researchReleaseGate": report["gates"]["researchReleaseGate"], "metrics": {k: report["metrics"][k] for k in ("inputEventCount", "uniqueValidEventCount", "invalidEventCount", "dayCoverage", "maxMissingGapDays", "labelAvailability")}}, ensure_ascii=False, sort_keys=True))
    # fail-closed exit: non-zero unless data quality is clean
    return 0 if report["gates"]["dataQualityGate"] == "ANALYZE_OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
