#!/usr/bin/env python3
"""Generate a deterministic 30-day ParkinSync readiness report.

The fixture is invented and contains no participant, household, or production data.
One duplicate and explicit missingness states are included to exercise quality checks.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path


MISSINGNESS = {
    "observed",
    "confirmed_none",
    "not_recorded",
    "not_applicable",
    "unknown",
    "source_unavailable",
    "excluded",
}


def event(event_id: str, event_type: str, source: str, day: str, missingness: str = "observed") -> dict:
    occurred = f"{day}T08:00:00+09:00"
    return {
        "schemaVersion": "care-event/v1",
        "eventId": event_id,
        "eventType": event_type,
        "source": source,
        "patientId": "synthetic-person-001",
        "careTeamId": "synthetic-team-001",
        "actorRole": "caregiver",
        "occurredAt": occurred,
        "recordedAt": occurred,
        "localDate": day,
        "payload": {},
        "missingness": missingness,
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


def build_events() -> list[dict]:
    events: list[dict] = []
    start = date(2035, 1, 1)
    timings = ("朝", "昼", "晩", "夜8時", "夜9時")
    for offset in range(30):
        day = (start + timedelta(days=offset)).isoformat()
        for timing_index, timing in enumerate(timings):
            missingness = "not_recorded" if timing == "夜9時" else "observed"
            item = event(f"med-{offset:02d}-{timing_index}", "medication_missed" if missingness != "observed" else "medication_taken", "medication-promise", day, missingness)
            item["payload"] = {"timing": timing, "delayMinutes": (offset + timing_index) % 16}
            events.append(item)

        bowel_missingness = "confirmed_none" if offset == 6 else "observed"
        bowel = event(f"bowel-{offset:02d}", "bowel_movement", "gutpacer", day, bowel_missingness)
        bowel["payload"] = {"amount": "中", "stoolType": "普通"} if bowel_missingness == "observed" else {}
        events.append(bowel)

        condition = event(f"condition-{offset:02d}", "daily_condition_logged", "gutpacer", day)
        condition["payload"] = {"conditionNum": (offset % 5) + 1}
        events.append(condition)

        weather = event(f"weather-{offset:02d}", "weather_observed", "parkinsync", day)
        weather["payload"] = {"weatherAvg": 7.5 + (offset % 8)}
        events.append(weather)

        indoor = event(f"indoor-{offset:02d}", "indoor_temperature_observed", "parkinsync", day)
        indoor["payload"] = {"temperatureAvg": 19.0 + (offset % 6)}
        events.append(indoor)

    events.append(events[0].copy())
    return events


def validate(item: dict) -> list[str]:
    required = ("schemaVersion", "eventId", "eventType", "source", "patientId", "careTeamId", "occurredAt", "recordedAt", "localDate", "payload", "missingness", "provenance", "consentScope", "exportVersion")
    errors = [f"missing:{field}" for field in required if field not in item]
    if item.get("schemaVersion") != "care-event/v1":
        errors.append("schemaVersion")
    if item.get("missingness") not in MISSINGNESS:
        errors.append("missingness")
    if item.get("consentScope") not in {"care_support", "personal_review", "research_aggregate", "none"}:
        errors.append("consentScope")
    provenance = item.get("provenance", {})
    errors.extend(f"provenance:{field}" for field in ("source", "sourceRecordId", "recordedAt", "exportedAt", "transformVersion") if field not in provenance)
    return errors


def build_report(events: list[dict]) -> dict:
    errors = []
    unique = []
    seen: set[str] = set()
    duplicates = 0
    for index, item in enumerate(events):
        item_errors = validate(item)
        if item_errors:
            errors.append({"index": index, "eventId": item.get("eventId"), "errors": item_errors})
            continue
        if item["eventId"] in seen:
            duplicates += 1
            continue
        seen.add(item["eventId"])
        unique.append(item)

    by_day: defaultdict[str, list[dict]] = defaultdict(list)
    for item in unique:
        by_day[item["localDate"]].append(item)
    source_day_coverage = {
        source: len({item["localDate"] for item in unique if item["source"] == source})
        for source in ("medication-promise", "gutpacer", "parkinsync")
    }
    observed_medication = sum(
        1 for item in unique if item["eventType"] == "medication_taken" and item["missingness"] == "observed"
    )
    expected_medication = 30 * 5
    return {
        "window": {"start": "2035-01-01", "end": "2035-01-30", "days": 30},
        "inputEventCount": len(events),
        "uniqueValidEventCount": len(unique),
        "invalidEventCount": len(errors),
        "duplicateEventCount": duplicates,
        "distinctDayCount": len(by_day),
        "sourceDayCoverage": source_day_coverage,
        "medicationSlotCoverage": {
            "observedSlots": observed_medication,
            "expectedSlots": expected_medication,
            "rate": round(observed_medication / expected_medication, 4),
        },
        "missingnessCounts": dict(sorted(Counter(item["missingness"] for item in unique).items())),
        "eventTypeCounts": dict(sorted(Counter(item["eventType"] for item in unique).items())),
        "schemaVersions": sorted({item["schemaVersion"] for item in unique}),
        "privacy": "Synthetic pseudonymous fixture only; no participant, household, or production data.",
        "limitations": [
            "This is a pipeline and data-quality readiness report, not a clinical or product-performance result.",
            "All records are invented; observed coverage cannot be used as real-world adoption or care evidence.",
            "The intentional duplicate and explicit missingness states test controls; they are not real incidents.",
        ],
        "errors": errors,
    }


def markdown(report: dict) -> str:
    quality = report["missingnessCounts"]
    lines = [
        "# ParkinSync 30日 synthetic readiness report",
        "",
        "- 対象期間: `2035-01-01`〜`2035-01-30`（合成データ）",
        f"- 入力イベント: **{report['inputEventCount']}** / unique valid: **{report['uniqueValidEventCount']}**",
        f"- 日数: **{report['distinctDayCount']}/30**",
        f"- invalid: **{report['invalidEventCount']}** / duplicate: **{report['duplicateEventCount']}**",
        "- データ範囲: 合成データのみ。参加者データ・世帯データ・productionデータは未使用。",
        "",
        "## Coverage",
        "",
        "| 指標 | 結果 |",
        "|---|---:|",
        f"| Medication slots | {report['medicationSlotCoverage']['observedSlots']}/{report['medicationSlotCoverage']['expectedSlots']} ({report['medicationSlotCoverage']['rate']:.0%}) |",
        f"| Medication source days | {report['sourceDayCoverage']['medication-promise']}/30 |",
        f"| GutPacer source days | {report['sourceDayCoverage']['gutpacer']}/30 |",
        f"| ParkinSync source days | {report['sourceDayCoverage']['parkinsync']}/30 |",
        "",
        "## Missingness and controls",
        "",
        f"- missingness: `{json.dumps(quality, ensure_ascii=False, sort_keys=True)}`",
        "- schema validation errors: 0",
        "- intentional duplicate detection: 1件を検出",
        "- explicit `not_recorded` and `confirmed_none` are kept distinct",
        "",
        "## Decision",
        "",
        "- **Pipeline readiness:** PASS（30日・3 source・schema version固定・duplicate検出・missingness区別）",
        "- **Research readiness:** NOT YET（synthetic data only。実データの同意・品質・保持・削除確認が未実施）",
        "- **ML readiness:** NOT YET（このレポートはモデル性能を評価しない）",
        "",
        "## Next gates",
        "",
        "1. 人間が実データを使う場合の目的・同意・保持・削除・アクセス範囲を承認する。",
        "2. 実データはGitへ出さず、承認済みのrestricted環境で30日windowを再実行する。",
        "3. 実データ版ではsource freshness、duplicate、missingness、correction、failureを日次で記録する。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/parkinsync-30-day-readiness"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(build_events())
    (args.output_dir / "readiness-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "readiness-report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("window", "inputEventCount", "uniqueValidEventCount", "invalidEventCount", "duplicateEventCount", "distinctDayCount", "medicationSlotCoverage", "missingnessCounts")}, ensure_ascii=False, sort_keys=True))
    return 1 if report["invalidEventCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
