"""Build deterministic seven-day synthetic FHIR and grounded-summary evidence."""

from __future__ import annotations

import json
import re
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fhir_export import (
    FHIR_VERSION,
    INPUT_SCHEMA_VERSION,
    build_resources,
    build_transaction_bundle,
    serialize_resource,
    validate_collection,
)
from fhir_summary import (
    OFFLINE_GENERATOR,
    SUMMARY_SCHEMA_VERSION,
    build_fact_bundle,
    validate_summary_candidate,
)


WEEKLY_SCHEMA_VERSION = "parkinsync-fhir-weekly-v1"
WEEKLY_FACT_SCHEMA_VERSION = "parkinsync-fhir-weekly-facts-v1"
WEEKLY_BUNDLE_ID = "synthetic-weekly-transaction-bundle"
WEEKLY_BUNDLE_FILE = f"bundle-{WEEKLY_BUNDLE_ID}.json"
WEEKLY_GENERATOR = "deterministic-weekly-template-v1"
SAFE_KEY = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_weekly_fixture(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        fixture = json.load(source)
    if not isinstance(fixture, dict):
        raise ValueError("weekly FHIR input must be a JSON object")
    if fixture.get("classification") != "synthetic":
        raise ValueError("weekly FHIR demo accepts only synthetic input")
    if fixture.get("schema_version") != WEEKLY_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {WEEKLY_SCHEMA_VERSION}")
    return fixture


def _required_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _required_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty array")
    return value


def _safe_key(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SAFE_KEY.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase kebab-case key")
    return value


def _iso_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error


def _analysis_dates(fixture: dict[str, Any]) -> list[str]:
    window = _required_mapping(fixture.get("analysis_window"), "analysis_window")
    start = _iso_date(window.get("start"), "analysis_window.start")
    end = _iso_date(window.get("end"), "analysis_window.end")
    if (end - start).days != 6:
        raise ValueError("analysis_window must cover exactly seven consecutive dates")
    return [(start + timedelta(days=offset)).isoformat() for offset in range(7)]


def _daily_record(
    fixture: dict[str, Any], day: dict[str, Any], day_index: int
) -> dict[str, Any]:
    recorded_date = _iso_date(day.get("date"), f"days[{day_index}].date").isoformat()
    date_key = recorded_date.replace("-", "")
    taken = _required_mapping(day.get("taken"), f"days[{day_index}].taken")
    observation_values = _required_mapping(
        day.get("observation_values"), f"days[{day_index}].observation_values"
    )

    medications = []
    for schedule_index, schedule in enumerate(
        _required_list(fixture.get("medication_schedule"), "medication_schedule")
    ):
        schedule = _required_mapping(
            schedule, f"medication_schedule[{schedule_index}]"
        )
        slot = _safe_key(schedule.get("slot"), f"medication_schedule[{schedule_index}].slot")
        if slot not in taken or not isinstance(taken[slot], bool):
            raise ValueError(f"days[{day_index}].taken.{slot} must be a boolean")
        medications.append(
            {
                "id": f"synthetic-{date_key}-medication-{slot}",
                "name": schedule.get("name"),
                "scheduled_time": schedule.get("scheduled_time"),
                "taken": taken[slot],
                "dose": deepcopy(schedule.get("dose")),
            }
        )

    observations = []
    for schedule_index, schedule in enumerate(
        _required_list(fixture.get("observation_schedule"), "observation_schedule")
    ):
        schedule = _required_mapping(
            schedule, f"observation_schedule[{schedule_index}]"
        )
        kind = _safe_key(
            schedule.get("kind"), f"observation_schedule[{schedule_index}].kind"
        )
        value = observation_values.get(kind)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(
                f"days[{day_index}].observation_values.{kind} must be numeric"
            )
        observations.append(
            {
                "id": f"synthetic-{date_key}-observation-{kind}",
                "kind": kind,
                "effective_time": schedule.get("effective_time"),
                "value": value,
            }
        )

    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "classification": "synthetic",
        "recorded_date": recorded_date,
        "timezone": fixture.get("timezone"),
        "patient": deepcopy(fixture.get("patient")),
        "medications": medications,
        "observations": observations,
        "care_plan": deepcopy(fixture.get("care_plan")),
    }


def build_weekly_resources(fixture: dict[str, Any]) -> list[Any]:
    """Expand explicit daily values into one seven-day FHIR resource collection."""
    if fixture.get("classification") != "synthetic":
        raise ValueError("weekly FHIR demo accepts only synthetic input")
    if fixture.get("schema_version") != WEEKLY_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {WEEKLY_SCHEMA_VERSION}")
    expected_dates = set(_analysis_dates(fixture))
    days = _required_list(fixture.get("days"), "days")
    ordered_days = sorted(days, key=lambda item: str(item.get("date", "")))
    actual_dates = [str(day.get("date")) for day in ordered_days]
    if len(actual_dates) != len(set(actual_dates)):
        raise ValueError("weekly fixture dates must be unique")
    if any(day not in expected_dates for day in actual_dates):
        raise ValueError("weekly fixture contains a date outside analysis_window")

    patient = None
    care_plan = None
    events: list[Any] = []
    for day_index, day in enumerate(ordered_days):
        resources = build_resources(_daily_record(fixture, day, day_index))
        if patient is None:
            patient = next(
                resource for resource in resources if resource.get_resource_type() == "Patient"
            )
            care_plan = next(
                resource for resource in resources if resource.get_resource_type() == "CarePlan"
            )
        events.extend(
            resource
            for resource in resources
            if resource.get_resource_type() in {"MedicationStatement", "Observation"}
        )
    if patient is None or care_plan is None:
        raise ValueError("weekly fixture contains no buildable day")
    combined = [patient, *events, care_plan]
    validate_collection(combined)
    return combined


def build_weekly_bundle(fixture: dict[str, Any]) -> dict[str, Any]:
    resources = build_weekly_resources(fixture)
    bundle = build_transaction_bundle(resources, bundle_id=WEEKLY_BUNDLE_ID)
    return json.loads(bundle.json(exclude_none=True, by_alias=True))


def _aggregate_fact_id(name: str) -> str:
    identity = f"https://veai.jp/fhir/fact/weekly/{name}"
    return f"fact-{uuid5(NAMESPACE_URL, identity)}"


def _derived_fact(
    name: str,
    kind: str,
    label: str,
    values: list[dict[str, Any]],
    source_fact_ids: list[str],
    method: str,
    fhir_path: str,
    unit: str | None = None,
) -> dict[str, Any]:
    fact = {
        "id": _aggregate_fact_id(name),
        "kind": kind,
        "label": label,
        "source": {
            "resource_type": "DerivedWeeklyAggregate",
            "resource_id": f"synthetic-weekly-{name}",
            "derived_from_fact_ids": sorted(source_fact_ids),
            "method": method,
            "values": [
                {"name": value["name"], "value": value["value"], "fhir_path": fhir_path}
                for value in values
            ],
        },
    }
    fact.update({value["name"]: value["value"] for value in values})
    if unit is not None:
        fact["unit"] = unit
        fact["source"]["values"].append(
            {"name": "unit", "value": unit, "fhir_path": fhir_path.rsplit(".", 1)[0] + ".code"}
        )
    return fact


def _event_date(fact: dict[str, Any]) -> str:
    effective_time = fact.get("effective_time")
    return effective_time[:10] if isinstance(effective_time, str) else ""


def build_weekly_fact_bundle(
    fixture: dict[str, Any], bundle_payload: dict[str, Any]
) -> dict[str, Any]:
    """Add deterministic weekly aggregates and completeness metadata to event facts."""
    event_bundle = build_fact_bundle(bundle_payload)
    event_facts = event_bundle.get("facts", [])
    expected_dates = _analysis_dates(fixture)
    expected_medications = len(
        _required_list(fixture.get("medication_schedule"), "medication_schedule")
    )
    expected_observations = len(
        _required_list(fixture.get("observation_schedule"), "observation_schedule")
    )
    counts_by_date_kind = Counter(
        (_event_date(fact), fact.get("kind")) for fact in event_facts
    )
    missing_events = []
    for day in expected_dates:
        for kind, expected in (
            ("medication", expected_medications),
            ("observation", expected_observations),
        ):
            actual = counts_by_date_kind[(day, kind)]
            if actual != expected:
                missing_events.append(
                    {"date": day, "fact_type": kind, "expected": expected, "actual": actual}
                )

    medication_facts = [fact for fact in event_facts if fact.get("kind") == "medication"]
    observation_facts = [fact for fact in event_facts if fact.get("kind") == "observation"]
    aggregates = []
    if medication_facts:
        aggregates.append(
            _derived_fact(
                "medication-records",
                "weekly-medication-aggregate",
                "Medication records",
                [
                    {"name": "record_count", "value": len(medication_facts)},
                    {
                        "name": "not_taken_count",
                        "value": sum(
                            fact.get("status") == "not-taken" for fact in medication_facts
                        ),
                    },
                ],
                [fact["id"] for fact in medication_facts],
                "count MedicationStatement facts by reviewed status",
                "MedicationStatement.status",
            )
        )
    for code in sorted({fact.get("code") for fact in observation_facts}):
        facts = [fact for fact in observation_facts if fact.get("code") == code]
        units = {fact.get("unit") for fact in facts}
        labels = {fact.get("label") for fact in facts}
        if len(units) != 1 or len(labels) != 1:
            continue
        values = [fact["value"] for fact in facts]
        aggregates.append(
            _derived_fact(
                f"observation-{code}",
                "weekly-observation-aggregate",
                next(iter(labels)),
                [
                    {"name": "record_count", "value": len(facts)},
                    {"name": "minimum", "value": min(values)},
                    {"name": "maximum", "value": max(values)},
                ],
                [fact["id"] for fact in facts],
                "count, minimum, and maximum over recorded Observation values",
                "Observation.valueQuantity.value",
                unit=next(iter(units)),
            )
        )

    corrections = fixture.get("material_corrections", [])
    if not isinstance(corrections, list) or any(
        not isinstance(correction, str) for correction in corrections
    ):
        raise ValueError("material_corrections must be an array of strings")
    missing_days = sorted(
        set(expected_dates) - {_event_date(fact) for fact in event_facts}
    )
    status = (
        "ready"
        if event_bundle.get("status") == "ready" and not missing_events and not missing_days
        else "insufficient_data"
    )
    all_facts = sorted([*event_facts, *aggregates], key=lambda fact: fact["id"])
    return {
        "schema_version": WEEKLY_FACT_SCHEMA_VERSION,
        "classification": "synthetic",
        "fhir_release": FHIR_VERSION,
        "source_bundle_id": bundle_payload.get("id"),
        "status": status,
        "analysis_window": {"start": expected_dates[0], "end": expected_dates[-1], "days": 7},
        "included_sources": ["MedicationStatement", "Observation"],
        "record_counts": {
            "MedicationStatement": len(medication_facts),
            "Observation": len(observation_facts),
            "derived_aggregate": len(aggregates),
        },
        "missingness": {
            "missing_days": missing_days,
            "missing_or_extra_events": missing_events,
            "required_value_coverage_ratio": event_bundle.get("quality", {})
            .get("coverage", {})
            .get("ratio", 0.0),
        },
        "material_corrections": corrections,
        "facts": all_facts,
        "quality": event_bundle.get("quality", {}),
    }


def build_weekly_summary(weekly_fact_bundle: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "analysis_window": weekly_fact_bundle.get("analysis_window"),
        "included_sources": weekly_fact_bundle.get("included_sources", []),
        "record_counts": weekly_fact_bundle.get("record_counts", {}),
        "missingness": weekly_fact_bundle.get("missingness", {}),
        "material_corrections": weekly_fact_bundle.get("material_corrections", []),
    }
    if weekly_fact_bundle.get("status") != "ready":
        return {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "classification": "synthetic",
            "status": "insufficient_data",
            "requires_human_review": True,
            "sharing_permitted": False,
            "generator": WEEKLY_GENERATOR,
            **metadata,
            "statements": [],
            "validation": {
                "accepted": False,
                "errors": [{"code": "source-insufficient-data"}],
            },
        }

    aggregates = {
        fact["kind"] + ":" + fact.get("label", ""): fact
        for fact in weekly_fact_bundle["facts"]
        if fact["kind"].startswith("weekly-")
    }
    medication = next(
        fact
        for fact in weekly_fact_bundle["facts"]
        if fact["kind"] == "weekly-medication-aggregate"
    )
    not_taken_ids = [
        fact["id"]
        for fact in weekly_fact_bundle["facts"]
        if fact.get("kind") == "medication" and fact.get("status") == "not-taken"
    ]
    statements = [
        {
            "text": (
                f"There were {medication['record_count']} medication records; "
                f"{medication['not_taken_count']} were recorded as not-taken."
            ),
            "fact_ids": [medication["id"], *sorted(not_taken_ids)],
        }
    ]
    observation_aggregates = sorted(
        (
            fact
            for fact in aggregates.values()
            if fact["kind"] == "weekly-observation-aggregate"
        ),
        key=lambda fact: fact["label"],
    )
    for fact in observation_aggregates:
        statements.append(
            {
                "text": (
                    f"{fact['label']} had {fact['record_count']} records ranging from "
                    f"{fact['minimum']:g} to {fact['maximum']:g} {fact['unit']}."
                ),
                "fact_ids": [fact["id"]],
            }
        )
    result = validate_summary_candidate(
        {"generator": WEEKLY_GENERATOR, "statements": statements},
        weekly_fact_bundle,
    )
    result.update(metadata)
    result["limitations"] = [
        "Recorded ranges are descriptive and do not establish a trend, cause, diagnosis, or treatment effect.",
        "Human review is required before any health-adjacent summary is shared.",
    ]
    return result


def render_weekly_outputs(fixture: dict[str, Any]) -> dict[str, str]:
    bundle = build_weekly_bundle(fixture)
    fact_bundle = build_weekly_fact_bundle(fixture, bundle)
    summary = build_weekly_summary(fact_bundle)
    outputs = {
        WEEKLY_BUNDLE_FILE: json.dumps(bundle, indent=2, sort_keys=True) + "\n",
        "fact-bundle.json": json.dumps(fact_bundle, indent=2, sort_keys=True) + "\n",
        "weekly-summary.json": json.dumps(summary, indent=2, sort_keys=True) + "\n",
    }
    type_counts = Counter(
        entry.get("resource", {}).get("resourceType") for entry in bundle.get("entry", [])
    )
    manifest = {
        "schema_version": WEEKLY_SCHEMA_VERSION,
        "classification": "synthetic",
        "fhir_release": FHIR_VERSION,
        "source_fixture": "fhir/weekly/synthetic-weekly-records.json",
        "bundle_file": WEEKLY_BUNDLE_FILE,
        "resource_count": len(bundle.get("entry", [])),
        "resource_type_counts": dict(sorted(type_counts.items())),
        "fact_count": len(fact_bundle["facts"]),
        "fact_bundle_status": fact_bundle["status"],
        "summary_status": summary["status"],
        "generator": "scripts/generate_weekly_fhir.py",
        "files": sorted(outputs),
        "sha256": {
            name: sha256(content.encode("utf-8")).hexdigest()
            for name, content in sorted(outputs.items())
        },
    }
    outputs["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    return outputs
