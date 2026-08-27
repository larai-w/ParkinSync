#!/usr/bin/env python3
"""Synthetic deletion (consent-withdrawal) rehearsal.

Rehearses "withdrawal == deletion" on synthetic data BEFORE any real data is
touched. Design mirrors BEN-001: consent withdrawal removes all of a person's
care-event records AND their pseudonym-mapping entry, and deletion is verified
fail-closed by re-scanning and asserting absence. Over-deletion (touching other
subjects) is also asserted against.

No participant, household, or production data. Synthetic pseudonymous fixtures
only. This is a control rehearsal, not a real deletion.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path


def _event(subject: str, event_id: str, event_type: str, source: str, day: str) -> dict:
    occurred = f"{day}T08:00:00+09:00"
    return {
        "schemaVersion": "care-event/v1",
        "eventId": event_id,
        "eventType": event_type,
        "source": source,
        "patientId": subject,
        "careTeamId": "synthetic-team-001",
        "occurredAt": occurred,
        "recordedAt": occurred,
        "localDate": day,
        "payload": {},
        "missingness": "observed",
        "provenance": {
            "source": source,
            "sourceRecordId": f"{source}:{event_id}",
            "recordedAt": occurred,
            "exportedAt": "2035-02-01T00:00:00+09:00",
            "transformVersion": "synthetic-transform/1",
        },
        "consentScope": "research_aggregate",
        "exportVersion": "synthetic-export/2035-02",
    }


def build_store() -> tuple[list[dict], dict[str, str]]:
    """A synthetic 'store' of two pseudonymous subjects + a separated mapping table."""
    subjects = ("synthetic-person-001", "synthetic-person-002")
    events: list[dict] = []
    start = date(2035, 1, 1)
    for subject in subjects:
        for offset in range(5):
            day = (start + timedelta(days=offset)).isoformat()
            events.append(_event(subject, f"{subject}-med-{offset}", "medication_taken", "medication-promise", day))
            events.append(_event(subject, f"{subject}-bowel-{offset}", "bowel_movement", "gutpacer", day))
    # mapping table is kept physically separate from the export in real life
    mapping = {
        "synthetic-person-001": "SYNTHETIC-NAME-PLACEHOLDER-001",
        "synthetic-person-002": "SYNTHETIC-NAME-PLACEHOLDER-002",
    }
    return events, mapping


def withdraw(events: list[dict], mapping: dict[str, str], subject: str) -> tuple[list[dict], dict[str, str], int]:
    """Delete all of `subject`'s events and their mapping entry."""
    before = len(events)
    remaining = [e for e in events if e["patientId"] != subject]
    removed = before - len(remaining)
    new_mapping = {k: v for k, v in mapping.items() if k != subject}
    return remaining, new_mapping, removed


def verify_absence(events: list[dict], mapping: dict[str, str], subject: str) -> list[str]:
    """Fail-closed check: subject must be fully gone from events AND mapping."""
    problems: list[str] = []
    leftover = [e["eventId"] for e in events if e["patientId"] == subject]
    if leftover:
        problems.append(f"residual_events:{len(leftover)}")
    if subject in mapping:
        problems.append("residual_mapping_entry")
    return problems


def rehearse(withdraw_subject: str = "synthetic-person-001") -> dict:
    events, mapping = build_store()
    others = sorted({e["patientId"] for e in events if e["patientId"] != withdraw_subject})
    others_before = {s: sum(1 for e in events if e["patientId"] == s) for s in others}

    remaining, new_mapping, removed = withdraw(events, mapping, withdraw_subject)
    problems = verify_absence(remaining, new_mapping, withdraw_subject)

    # over-deletion guard: everyone else must be untouched
    others_after = {s: sum(1 for e in remaining if e["patientId"] == s) for s in others}
    over_deletion = {s: [others_before[s], others_after[s]] for s in others if others_before[s] != others_after[s]}
    if over_deletion:
        problems.append(f"over_deletion:{over_deletion}")

    passed = not problems
    return {
        "control": "synthetic-deletion-rehearsal/v1",
        "withdrawSubject": withdraw_subject,
        "removedEventCount": removed,
        "residualProblems": problems,
        "otherSubjectsIntact": not over_deletion,
        "storeEventsBefore": len(events),
        "storeEventsAfter": len(remaining),
        "mappingEntriesAfter": len(new_mapping),
        "result": "GREEN" if passed else "RED",
        "privacy": "Synthetic pseudonymous rehearsal; no real participant data.",
    }


def self_test() -> int:
    report = rehearse()
    assert report["result"] == "GREEN", report
    assert report["removedEventCount"] == 10, report  # 5 days x 2 events
    assert report["otherSubjectsIntact"], report
    assert report["mappingEntriesAfter"] == 1, report

    # negative: a broken deletion (leftover) must be detected as RED
    events, mapping = build_store()
    remaining = [e for e in events if not (e["patientId"] == "synthetic-person-001" and e["eventType"] == "bowel_movement")]
    # only some records removed -> residual medication events remain
    problems = verify_absence(remaining, {k: v for k, v in mapping.items() if k != "synthetic-person-001"}, "synthetic-person-001")
    assert problems and any(p.startswith("residual_events") for p in problems), problems

    # negative: residual mapping entry must be detected
    events2, mapping2 = build_store()
    remaining2, _, _ = withdraw(events2, mapping2, "synthetic-person-001")
    problems2 = verify_absence(remaining2, mapping2, "synthetic-person-001")  # note: original mapping still has entry
    assert "residual_mapping_entry" in problems2, problems2

    print("deletion-rehearsal self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic consent-withdrawal deletion rehearsal")
    parser.add_argument("--subject", default="synthetic-person-001")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/synthetic-deletion-rehearsal"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    report = rehearse(args.subject)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "deletion-rehearsal.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["result"] == "GREEN" else 3  # fail-closed


if __name__ == "__main__":
    raise SystemExit(main())
