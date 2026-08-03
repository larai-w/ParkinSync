"""Build and verify grounded summaries from synthetic FHIR R4 resources."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fhir.resources.bundle import Bundle

from fhir_export import (
    CLASSIFICATION_SYSTEM,
    FHIR_VERSION,
    RESOURCE_MODELS,
    UCUM_SYSTEM,
)


FACT_BUNDLE_SCHEMA_VERSION = "parkinsync-fhir-facts-v1"
SUMMARY_SCHEMA_VERSION = "parkinsync-grounded-summary-v1"
OFFLINE_GENERATOR = "deterministic-template-v1"

EXPECTED_OBSERVATION_UNITS = {
    "8310-5": (UCUM_SYSTEM, "Cel"),
    "8867-4": (UCUM_SYSTEM, "/min"),
}

PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"(?:system|developer|assistant)\s*prompt", re.IGNORECASE),
    re.compile(r"\b(?:system|developer|assistant)\s*:", re.IGNORECASE),
)
CAUSAL_CLAIM_PATTERNS = (
    re.compile(r"\bbecause\b", re.IGNORECASE),
    re.compile(r"\bcaused?\b", re.IGNORECASE),
    re.compile(r"\bdue to\b", re.IGNORECASE),
    re.compile(r"\bresult(?:ed|ing)? from\b", re.IGNORECASE),
    re.compile(r"原因"),
    re.compile(r"ために改善"),
)
CLINICAL_CLAIM_PATTERNS = (
    re.compile(r"\bdiagnos(?:e|ed|is|tic)\b", re.IGNORECASE),
    re.compile(r"\b(?:recommend|prescribe|treat(?:ment|ed|ing)?)\b", re.IGNORECASE),
    re.compile(r"\bshould\s+(?:take|stop|start|increase|decrease)\b", re.IGNORECASE),
    re.compile(r"(?:診断|治療|服薬|投薬).*(?:すべき|勧め|変更|中止|増や|減ら)"),
)
NUMBER_PATTERN = re.compile(r"(?<![\w.-])-?\d+(?:\.\d+)?(?![\w.-])")

QUALITY_LIST_FIELDS = (
    "missing_values",
    "duplicates",
    "unit_mismatches",
    "unresolved_references",
    "contradictory_statuses",
    "conflicting_timestamps",
    "invalid_resources",
    "prompt_injection_signals",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _stable_fact_id(resource_type: str, resource_id: str) -> str:
    identity = f"https://veai.jp/fhir/fact/{resource_type}/{resource_id}"
    return f"fact-{uuid5(NAMESPACE_URL, identity)}"


def _has_synthetic_tag(resource: dict[str, Any]) -> bool:
    return any(
        tag.get("system") == CLASSIFICATION_SYSTEM and tag.get("code") == "synthetic"
        for tag in resource.get("meta", {}).get("tag", [])
        if isinstance(tag, dict)
    )


def _source_value(name: str, value: Any, path: str) -> dict[str, Any]:
    return {"name": name, "value": value, "fhir_path": path}


def _issue(resource_type: str, resource_id: str, path: str) -> dict[str, str]:
    return {
        "resource": f"{resource_type}/{resource_id}",
        "fhir_path": path,
    }


def _required(
    value: Any,
    resource_type: str,
    resource_id: str,
    path: str,
    missing_values: list[dict[str, str]],
) -> Any:
    if value is None or value == "" or value == []:
        missing_values.append(_issue(resource_type, resource_id, path))
        return None
    return value


def _first_coding(resource: dict[str, Any]) -> dict[str, Any]:
    codings = resource.get("code", {}).get("coding", [])
    return codings[0] if isinstance(codings, list) and codings else {}


def _first_dose(resource: dict[str, Any]) -> dict[str, Any]:
    dosage = resource.get("dosage", [])
    if not isinstance(dosage, list) or not dosage:
        return {}
    dose_and_rate = dosage[0].get("doseAndRate", [])
    if not isinstance(dose_and_rate, list) or not dose_and_rate:
        return {}
    return dose_and_rate[0].get("doseQuantity", {})


def _bundle_resources(bundle_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    try:
        bundle = Bundle.parse_obj(bundle_payload)
    except ValueError as error:
        raise ValueError("input must be a valid FHIR R4 Bundle") from error
    payload = json.loads(bundle.json(exclude_none=True, by_alias=True))
    entries = payload.get("entry", [])
    resources = [entry.get("resource", {}) for entry in entries]
    targets = {
        target
        for entry in entries
        for target in (
            entry.get("fullUrl"),
            f"{entry.get('resource', {}).get('resourceType')}/{entry.get('resource', {}).get('id')}",
        )
        if isinstance(target, str)
    }
    return resources, targets


def _injection_paths(resource: dict[str, Any]) -> list[str]:
    candidates: list[tuple[str, Any]] = []
    resource_type = resource.get("resourceType")
    if resource_type == "Observation":
        candidates.extend(
            (
                ("Observation.code.text", resource.get("code", {}).get("text")),
                (
                    "Observation.code.coding[0].display",
                    _first_coding(resource).get("display"),
                ),
            )
        )
    elif resource_type == "MedicationStatement":
        candidates.append(
            (
                "MedicationStatement.medicationCodeableConcept.text",
                resource.get("medicationCodeableConcept", {}).get("text"),
            )
        )
    return [
        path
        for path, value in candidates
        if isinstance(value, str)
        and any(pattern.search(value) for pattern in PROMPT_INJECTION_PATTERNS)
    ]


def _observation_fact(
    resource: dict[str, Any], quality: dict[str, Any]
) -> dict[str, Any] | None:
    resource_type = "Observation"
    resource_id = str(resource.get("id", "unknown"))
    coding = _first_coding(resource)
    quantity = resource.get("valueQuantity", {})
    required = {
        "label": _required(
            resource.get("code", {}).get("text") or coding.get("display"),
            resource_type,
            resource_id,
            "Observation.code.text",
            quality["missing_values"],
        ),
        "code": _required(
            coding.get("code"),
            resource_type,
            resource_id,
            "Observation.code.coding[0].code",
            quality["missing_values"],
        ),
        "status": _required(
            resource.get("status"),
            resource_type,
            resource_id,
            "Observation.status",
            quality["missing_values"],
        ),
        "effective_time": _required(
            resource.get("effectiveDateTime"),
            resource_type,
            resource_id,
            "Observation.effectiveDateTime",
            quality["missing_values"],
        ),
        "value": _required(
            quantity.get("value"),
            resource_type,
            resource_id,
            "Observation.valueQuantity.value",
            quality["missing_values"],
        ),
        "unit_system": _required(
            quantity.get("system"),
            resource_type,
            resource_id,
            "Observation.valueQuantity.system",
            quality["missing_values"],
        ),
        "unit": _required(
            quantity.get("code"),
            resource_type,
            resource_id,
            "Observation.valueQuantity.code",
            quality["missing_values"],
        ),
        "subject_reference": _required(
            resource.get("subject", {}).get("reference"),
            resource_type,
            resource_id,
            "Observation.subject.reference",
            quality["missing_values"],
        ),
    }
    if any(value is None for value in required.values()):
        return None

    expected_unit = EXPECTED_OBSERVATION_UNITS.get(required["code"])
    actual_unit = (required["unit_system"], required["unit"])
    if expected_unit and actual_unit != expected_unit:
        quality["unit_mismatches"].append(
            {
                **_issue(
                    resource_type,
                    resource_id,
                    "Observation.valueQuantity.system|code",
                ),
                "expected": "|".join(expected_unit),
                "actual": "|".join(actual_unit),
            }
        )

    return {
        "id": _stable_fact_id(resource_type, resource_id),
        "kind": "observation",
        "label": required["label"],
        "code": required["code"],
        "status": required["status"],
        "effective_time": required["effective_time"],
        "value": required["value"],
        "unit": required["unit"],
        "subject_reference": required["subject_reference"],
        "source": {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "values": [
                _source_value("label", required["label"], "Observation.code.text"),
                _source_value("code", required["code"], "Observation.code.coding[0].code"),
                _source_value("status", required["status"], "Observation.status"),
                _source_value(
                    "effective_time",
                    required["effective_time"],
                    "Observation.effectiveDateTime",
                ),
                _source_value(
                    "value", required["value"], "Observation.valueQuantity.value"
                ),
                _source_value(
                    "unit_system",
                    required["unit_system"],
                    "Observation.valueQuantity.system",
                ),
                _source_value(
                    "unit", required["unit"], "Observation.valueQuantity.code"
                ),
                _source_value(
                    "subject_reference",
                    required["subject_reference"],
                    "Observation.subject.reference",
                ),
            ],
        },
    }


def _medication_fact(
    resource: dict[str, Any], quality: dict[str, Any]
) -> dict[str, Any] | None:
    resource_type = "MedicationStatement"
    resource_id = str(resource.get("id", "unknown"))
    dose = _first_dose(resource)
    required = {
        "medication": _required(
            resource.get("medicationCodeableConcept", {}).get("text"),
            resource_type,
            resource_id,
            "MedicationStatement.medicationCodeableConcept.text",
            quality["missing_values"],
        ),
        "status": _required(
            resource.get("status"),
            resource_type,
            resource_id,
            "MedicationStatement.status",
            quality["missing_values"],
        ),
        "effective_time": _required(
            resource.get("effectiveDateTime"),
            resource_type,
            resource_id,
            "MedicationStatement.effectiveDateTime",
            quality["missing_values"],
        ),
        "dose_value": _required(
            dose.get("value"),
            resource_type,
            resource_id,
            "MedicationStatement.dosage[0].doseAndRate[0].doseQuantity.value",
            quality["missing_values"],
        ),
        "unit_system": _required(
            dose.get("system"),
            resource_type,
            resource_id,
            "MedicationStatement.dosage[0].doseAndRate[0].doseQuantity.system",
            quality["missing_values"],
        ),
        "unit": _required(
            dose.get("code"),
            resource_type,
            resource_id,
            "MedicationStatement.dosage[0].doseAndRate[0].doseQuantity.code",
            quality["missing_values"],
        ),
        "subject_reference": _required(
            resource.get("subject", {}).get("reference"),
            resource_type,
            resource_id,
            "MedicationStatement.subject.reference",
            quality["missing_values"],
        ),
    }
    if any(value is None for value in required.values()):
        return None

    timestamp_paths = {
        "MedicationStatement.dateAsserted": resource.get("dateAsserted"),
    }
    dosage = resource.get("dosage", [])
    if isinstance(dosage, list) and dosage:
        events = dosage[0].get("timing", {}).get("event", [])
        if isinstance(events, list) and events:
            timestamp_paths["MedicationStatement.dosage[0].timing.event[0]"] = events[0]
    for path, timestamp in timestamp_paths.items():
        if timestamp and timestamp != required["effective_time"]:
            quality["conflicting_timestamps"].append(
                {
                    **_issue(resource_type, resource_id, path),
                    "expected_path": "MedicationStatement.effectiveDateTime",
                }
            )

    if required["unit_system"] != UCUM_SYSTEM:
        quality["unit_mismatches"].append(
            {
                **_issue(
                    resource_type,
                    resource_id,
                    "MedicationStatement.dosage[0].doseAndRate[0].doseQuantity.system",
                ),
                "expected": UCUM_SYSTEM,
                "actual": str(required["unit_system"]),
            }
        )

    return {
        "id": _stable_fact_id(resource_type, resource_id),
        "kind": "medication",
        "medication": required["medication"],
        "status": required["status"],
        "effective_time": required["effective_time"],
        "dose_value": required["dose_value"],
        "unit": required["unit"],
        "subject_reference": required["subject_reference"],
        "source": {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "values": [
                _source_value(
                    "medication",
                    required["medication"],
                    "MedicationStatement.medicationCodeableConcept.text",
                ),
                _source_value("status", required["status"], "MedicationStatement.status"),
                _source_value(
                    "effective_time",
                    required["effective_time"],
                    "MedicationStatement.effectiveDateTime",
                ),
                _source_value(
                    "dose_value",
                    required["dose_value"],
                    "MedicationStatement.dosage[0].doseAndRate[0].doseQuantity.value",
                ),
                _source_value(
                    "unit_system",
                    required["unit_system"],
                    "MedicationStatement.dosage[0].doseAndRate[0].doseQuantity.system",
                ),
                _source_value(
                    "unit",
                    required["unit"],
                    "MedicationStatement.dosage[0].doseAndRate[0].doseQuantity.code",
                ),
                _source_value(
                    "subject_reference",
                    required["subject_reference"],
                    "MedicationStatement.subject.reference",
                ),
            ],
        },
    }


def build_fact_bundle(bundle_payload: dict[str, Any]) -> dict[str, Any]:
    """Extract deterministic facts and non-LLM data-quality findings."""
    resources, reference_targets = _bundle_resources(bundle_payload)
    quality: dict[str, Any] = {field: [] for field in QUALITY_LIST_FIELDS}
    quality["coverage"] = {}
    identities: set[str] = set()
    event_keys: dict[tuple[Any, ...], str] = {}
    medication_statuses: dict[tuple[str, str], dict[str, list[str]]] = {}
    facts: list[dict[str, Any]] = []
    eligible_resource_count = 0
    required_value_count = 0

    for resource in resources:
        resource_type = str(resource.get("resourceType", "unknown"))
        resource_id = str(resource.get("id", "unknown"))
        identity = f"{resource_type}/{resource_id}"
        if identity in identities:
            quality["duplicates"].append(
                {"kind": "resource-identity", "resource": identity}
            )
        identities.add(identity)

        model = RESOURCE_MODELS.get(resource_type)
        if model is None:
            quality["invalid_resources"].append(
                {"resource": identity, "reason": "unsupported-resource-type"}
            )
            continue
        try:
            model.parse_obj(resource)
        except ValueError:
            quality["invalid_resources"].append(
                {"resource": identity, "reason": "fhir-model-validation-failed"}
            )
            continue
        if not _has_synthetic_tag(resource):
            quality["invalid_resources"].append(
                {"resource": identity, "reason": "synthetic-classification-required"}
            )
            continue
        if resource_type not in {"Observation", "MedicationStatement"}:
            continue

        eligible_resource_count += 1
        allowed_statuses = (
            {"final"}
            if resource_type == "Observation"
            else {"completed", "not-taken"}
        )
        if resource.get("status") not in allowed_statuses:
            quality["invalid_resources"].append(
                {"resource": identity, "reason": "unreviewed-resource-status"}
            )
            continue
        subject_reference = resource.get("subject", {}).get("reference")
        if subject_reference and subject_reference not in reference_targets:
            quality["unresolved_references"].append(
                {
                    **_issue(resource_type, resource_id, f"{resource_type}.subject.reference"),
                    "reference": subject_reference,
                }
            )
        injection_paths = _injection_paths(resource)
        for path in injection_paths:
            quality["prompt_injection_signals"].append(
                _issue(resource_type, resource_id, path)
            )
        if injection_paths:
            continue

        if resource_type == "Observation":
            required_value_count += 8
            fact = _observation_fact(resource, quality)
            if fact:
                event_key = (
                    "Observation",
                    fact["code"],
                    fact["effective_time"],
                    fact["subject_reference"],
                )
        else:
            required_value_count += 7
            fact = _medication_fact(resource, quality)
            if fact:
                event_key = (
                    "MedicationStatement",
                    fact["medication"],
                    fact["effective_time"],
                    fact["subject_reference"],
                )
                status_key = (fact["medication"], fact["effective_time"])
                statuses = medication_statuses.setdefault(status_key, {})
                statuses.setdefault(fact["status"], []).append(identity)
        if not fact:
            continue
        if event_key in event_keys:
            quality["duplicates"].append(
                {
                    "kind": "semantic-event",
                    "resource": identity,
                    "matches": event_keys[event_key],
                }
            )
        else:
            event_keys[event_key] = identity
        facts.append(fact)

    for (medication, effective_time), statuses in medication_statuses.items():
        if len(statuses) > 1:
            quality["contradictory_statuses"].append(
                {
                    "medication_key": sha256(medication.encode("utf-8")).hexdigest()[:12],
                    "effective_time": effective_time,
                    "resources": sorted(
                        resource for group in statuses.values() for resource in group
                    ),
                    "statuses": sorted(statuses),
                }
            )

    facts.sort(key=lambda fact: fact["id"])
    present_types = sorted({fact["kind"] for fact in facts})
    present_value_count = sum(len(fact["source"]["values"]) for fact in facts)
    missing_types = sorted({"medication", "observation"} - set(present_types))
    quality["coverage"] = {
        "eligible_resource_count": eligible_resource_count,
        "fact_count": len(facts),
        "required_value_count": required_value_count,
        "present_value_count": present_value_count,
        "ratio": (
            round(present_value_count / required_value_count, 6)
            if required_value_count
            else 0.0
        ),
        "present_fact_types": present_types,
        "missing_fact_types": missing_types,
    }
    for field in QUALITY_LIST_FIELDS:
        quality[field] = sorted(quality[field], key=_canonical_json)

    blocking_findings = missing_types or any(quality[field] for field in QUALITY_LIST_FIELDS)
    status = "ready" if facts and not blocking_findings else "insufficient_data"
    return {
        "schema_version": FACT_BUNDLE_SCHEMA_VERSION,
        "classification": "synthetic",
        "fhir_release": FHIR_VERSION,
        "source_bundle_id": bundle_payload.get("id"),
        "status": status,
        "facts": facts,
        "quality": quality,
    }


def _numeric_values(fact: dict[str, Any]) -> set[Decimal]:
    values: set[Decimal] = set()
    for source_value in fact.get("source", {}).get("values", []):
        value = source_value.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        values.add(Decimal(str(value)))
    return values


def _numbers_in_text(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for match in NUMBER_PATTERN.findall(text):
        try:
            values.add(Decimal(match))
        except InvalidOperation:
            continue
    return values


def validate_summary_candidate(
    candidate: dict[str, Any], fact_bundle: dict[str, Any]
) -> dict[str, Any]:
    """Reject unsupported, uncited, incomplete, or numerically changed statements."""
    errors: list[dict[str, Any]] = []
    facts = {fact["id"]: fact for fact in fact_bundle.get("facts", [])}
    statements = candidate.get("statements")
    cited_ids: set[str] = set()

    if fact_bundle.get("status") != "ready":
        errors.append({"code": "source-insufficient-data"})
    if not isinstance(statements, list) or not statements:
        errors.append({"code": "no-statements"})
        statements = []

    for index, statement in enumerate(statements):
        if not isinstance(statement, dict):
            errors.append({"code": "invalid-statement", "statement_index": index})
            continue
        text = statement.get("text")
        fact_ids = statement.get("fact_ids")
        if not isinstance(text, str) or not text.strip():
            errors.append({"code": "empty-statement", "statement_index": index})
            continue
        if not isinstance(fact_ids, list) or not fact_ids:
            errors.append({"code": "uncited-statement", "statement_index": index})
            continue
        unknown_ids = sorted(
            fact_id for fact_id in fact_ids if not isinstance(fact_id, str) or fact_id not in facts
        )
        if unknown_ids:
            errors.append(
                {
                    "code": "unknown-fact-citation",
                    "statement_index": index,
                    "fact_ids": unknown_ids,
                }
            )
            continue
        cited_ids.update(fact_ids)
        if any(pattern.search(text) for pattern in PROMPT_INJECTION_PATTERNS):
            errors.append({"code": "instruction-like-output", "statement_index": index})
        if any(pattern.search(text) for pattern in CAUSAL_CLAIM_PATTERNS):
            errors.append({"code": "unsupported-causal-claim", "statement_index": index})
        if any(pattern.search(text) for pattern in CLINICAL_CLAIM_PATTERNS):
            errors.append({"code": "unsupported-clinical-claim", "statement_index": index})
        allowed_numbers = {
            value for fact_id in fact_ids for value in _numeric_values(facts[fact_id])
        }
        unsupported_numbers = sorted(_numbers_in_text(text) - allowed_numbers)
        if unsupported_numbers:
            errors.append(
                {
                    "code": "numerical-inconsistency",
                    "statement_index": index,
                    "values": [str(value) for value in unsupported_numbers],
                }
            )

    missed_dose_ids = {
        fact_id
        for fact_id, fact in facts.items()
        if fact.get("kind") == "medication" and fact.get("status") == "not-taken"
    }
    if omitted := sorted(missed_dose_ids - cited_ids):
        errors.append({"code": "omitted-not-taken-medication", "fact_ids": omitted})

    errors.sort(key=_canonical_json)
    accepted = not errors
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "classification": "synthetic",
        "status": "ready_for_human_review" if accepted else "rejected",
        "requires_human_review": True,
        "sharing_permitted": False,
        "generator": candidate.get("generator", "external-candidate"),
        "statements": statements,
        "validation": {"accepted": accepted, "errors": errors},
    }


def build_offline_summary(fact_bundle: dict[str, Any]) -> dict[str, Any]:
    """Create a reproducible no-model fallback and run it through the same gate."""
    if fact_bundle.get("status") != "ready":
        reason_codes = [
            field
            for field in QUALITY_LIST_FIELDS
            if fact_bundle.get("quality", {}).get(field)
        ]
        if fact_bundle.get("quality", {}).get("coverage", {}).get("missing_fact_types"):
            reason_codes.append("missing_fact_types")
        return {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "classification": "synthetic",
            "status": "insufficient_data",
            "requires_human_review": True,
            "sharing_permitted": False,
            "generator": OFFLINE_GENERATOR,
            "reason_codes": sorted(reason_codes) or ["no-eligible-facts"],
            "statements": [],
            "validation": {"accepted": False, "errors": [{"code": "source-insufficient-data"}]},
        }

    statements = []
    for fact in fact_bundle["facts"]:
        if fact["kind"] == "observation":
            text = f"{fact['label']} was recorded as {fact['value']:g} {fact['unit']}."
        else:
            text = (
                f"{fact['medication']} was recorded as {fact['status']} "
                f"with a dose of {fact['dose_value']:g} {fact['unit']}."
            )
        statements.append({"text": text, "fact_ids": [fact["id"]]})
    return validate_summary_candidate(
        {"generator": OFFLINE_GENERATOR, "statements": statements}, fact_bundle
    )


def render_summary_outputs(bundle_payload: dict[str, Any]) -> dict[str, str]:
    fact_bundle = build_fact_bundle(bundle_payload)
    summary = build_offline_summary(fact_bundle)
    outputs = {
        "fact-bundle.json": json.dumps(fact_bundle, indent=2, sort_keys=True) + "\n",
        "offline-summary.json": json.dumps(summary, indent=2, sort_keys=True) + "\n",
    }
    manifest = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "classification": "synthetic",
        "source_bundle_id": bundle_payload.get("id"),
        "fact_count": len(fact_bundle["facts"]),
        "fact_bundle_status": fact_bundle["status"],
        "summary_status": summary["status"],
        "generator": OFFLINE_GENERATOR,
        "files": sorted(outputs),
        "sha256": {
            name: sha256(content.encode("utf-8")).hexdigest()
            for name, content in sorted(outputs.items())
        },
    }
    outputs["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    return outputs
