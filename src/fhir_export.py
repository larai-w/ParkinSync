"""Convert an explicit synthetic ParkinSync record into HL7 FHIR R4 resources."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fhir.resources import __fhir_version__
from fhir.resources.bundle import Bundle
from fhir.resources.careplan import CarePlan
from fhir.resources.medicationstatement import MedicationStatement
from fhir.resources.observation import Observation
from fhir.resources.patient import Patient


FHIR_VERSION = "4.0.1"
INPUT_SCHEMA_VERSION = "parkinsync-fhir-demo-v1"
BUNDLE_ID = "synthetic-transaction-bundle"
BUNDLE_FILE = f"bundle-{BUNDLE_ID}.json"
CLASSIFICATION_SYSTEM = "https://veai.jp/fhir/CodeSystem/data-classification"
PATIENT_IDENTIFIER_SYSTEM = "https://veai.jp/fhir/synthetic-patient"
UCUM_SYSTEM = "http://unitsofmeasure.org"
LOINC_SYSTEM = "http://loinc.org"
OBSERVATION_CATEGORY_SYSTEM = (
    "http://terminology.hl7.org/CodeSystem/observation-category"
)

RESOURCE_MODELS = {
    "CarePlan": CarePlan,
    "MedicationStatement": MedicationStatement,
    "Observation": Observation,
    "Patient": Patient,
}

OBSERVATION_MAPPINGS = {
    "body-temperature": {
        "code": "8310-5",
        "display": "Body temperature",
        "unit": "degrees Celsius",
        "ucum_code": "Cel",
    },
    "heart-rate": {
        "code": "8867-4",
        "display": "Heart rate",
        "unit": "beats per minute",
        "ucum_code": "/min",
    },
}


def load_record(path: Path) -> dict[str, Any]:
    """Load a JSON object and reject any input not explicitly marked synthetic."""
    with path.open(encoding="utf-8") as source:
        record = json.load(source)
    if not isinstance(record, dict):
        raise ValueError("FHIR input must be a JSON object")
    if record.get("classification") != "synthetic":
        raise ValueError("FHIR demo accepts only records classified as synthetic")
    return record


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _resource_id(value: Any, field: str) -> str:
    resource_id = _required_text(value, field)
    if not resource_id.startswith("synthetic-"):
        raise ValueError(f"{field} must start with 'synthetic-'")
    return resource_id


def _timestamp(recorded_date: str, local_time: str, timezone: str) -> str:
    try:
        timestamp = datetime.fromisoformat(f"{recorded_date}T{local_time}:00{timezone}")
    except ValueError as error:
        raise ValueError(f"invalid local date/time: {recorded_date} {local_time} {timezone}") from error
    if timestamp.utcoffset() is None:
        raise ValueError("FHIR event timestamps must include a UTC offset")
    return timestamp.isoformat()


def _synthetic_meta() -> dict[str, Any]:
    return {
        "tag": [
            {
                "system": CLASSIFICATION_SYSTEM,
                "code": "synthetic",
                "display": "Synthetic data",
            }
        ]
    }


def _build_patient(record: dict[str, Any]) -> Patient:
    patient = record.get("patient")
    if not isinstance(patient, dict):
        raise ValueError("patient must be an object")
    patient_id = _resource_id(patient.get("id"), "patient.id")
    identifier = _required_text(patient.get("identifier"), "patient.identifier")
    return Patient.parse_obj(
        {
            "resourceType": "Patient",
            "id": patient_id,
            "meta": _synthetic_meta(),
            "identifier": [
                {
                    "use": "temp",
                    "system": PATIENT_IDENTIFIER_SYSTEM,
                    "value": identifier,
                }
            ],
            "active": True,
        }
    )


def _build_medication_statements(
    record: dict[str, Any], patient_reference: str, recorded_date: str, timezone: str
) -> list[MedicationStatement]:
    medications = record.get("medications")
    if not isinstance(medications, list) or not medications:
        raise ValueError("medications must be a non-empty array")

    resources: list[MedicationStatement] = []
    for index, medication in enumerate(medications):
        field = f"medications[{index}]"
        if not isinstance(medication, dict):
            raise ValueError(f"{field} must be an object")
        statement_id = _resource_id(medication.get("id"), f"{field}.id")
        name = _required_text(medication.get("name"), f"{field}.name")
        local_time = _required_text(medication.get("scheduled_time"), f"{field}.scheduled_time")
        taken = medication.get("taken")
        if not isinstance(taken, bool):
            raise ValueError(f"{field}.taken must be a boolean")

        dose = medication.get("dose")
        if not isinstance(dose, dict):
            raise ValueError(f"{field}.dose must be an object")
        value = dose.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{field}.dose.value must be a positive number")
        unit = _required_text(dose.get("unit"), f"{field}.dose.unit")
        ucum_code = _required_text(dose.get("ucum_code"), f"{field}.dose.ucum_code")
        event_time = _timestamp(recorded_date, local_time, timezone)

        resources.append(
            MedicationStatement.parse_obj(
                {
                    "resourceType": "MedicationStatement",
                    "id": statement_id,
                    "meta": _synthetic_meta(),
                    "status": "completed" if taken else "not-taken",
                    "medicationCodeableConcept": {"text": name},
                    "subject": {"reference": patient_reference},
                    "effectiveDateTime": event_time,
                    "dateAsserted": event_time,
                    "dosage": [
                        {
                            "text": f"{value:g} {unit} at {local_time}",
                            "timing": {"event": [event_time]},
                            "doseAndRate": [
                                {
                                    "doseQuantity": {
                                        "value": value,
                                        "unit": unit,
                                        "system": UCUM_SYSTEM,
                                        "code": ucum_code,
                                    }
                                }
                            ],
                        }
                    ],
                }
            )
        )
    return resources


def _build_observations(
    record: dict[str, Any], patient_reference: str, recorded_date: str, timezone: str
) -> list[Observation]:
    observations = record.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ValueError("observations must be a non-empty array")

    resources: list[Observation] = []
    for index, observation in enumerate(observations):
        field = f"observations[{index}]"
        if not isinstance(observation, dict):
            raise ValueError(f"{field} must be an object")
        observation_id = _resource_id(observation.get("id"), f"{field}.id")
        kind = _required_text(observation.get("kind"), f"{field}.kind")
        try:
            mapping = OBSERVATION_MAPPINGS[kind]
        except KeyError as error:
            raise ValueError(f"{field}.kind is not a reviewed mapping: {kind}") from error
        value = observation.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{field}.value must be numeric")
        local_time = _required_text(observation.get("effective_time"), f"{field}.effective_time")

        resources.append(
            Observation.parse_obj(
                {
                    "resourceType": "Observation",
                    "id": observation_id,
                    "meta": _synthetic_meta(),
                    "status": "final",
                    "category": [
                        {
                            "coding": [
                                {
                                    "system": OBSERVATION_CATEGORY_SYSTEM,
                                    "code": "vital-signs",
                                    "display": "Vital Signs",
                                }
                            ]
                        }
                    ],
                    "code": {
                        "coding": [
                            {
                                "system": LOINC_SYSTEM,
                                "code": mapping["code"],
                                "display": mapping["display"],
                            }
                        ],
                        "text": mapping["display"],
                    },
                    "subject": {"reference": patient_reference},
                    "effectiveDateTime": _timestamp(recorded_date, local_time, timezone),
                    "valueQuantity": {
                        "value": value,
                        "unit": mapping["unit"],
                        "system": UCUM_SYSTEM,
                        "code": mapping["ucum_code"],
                    },
                }
            )
        )
    return resources


def _build_care_plan(
    record: dict[str, Any], patient_reference: str
) -> CarePlan:
    care_plan = record.get("care_plan")
    if not isinstance(care_plan, dict):
        raise ValueError("care_plan must be an object")
    care_plan_id = _resource_id(care_plan.get("id"), "care_plan.id")
    start = _required_text(care_plan.get("start"), "care_plan.start")
    end = _required_text(care_plan.get("end"), "care_plan.end")
    try:
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise ValueError("care_plan.start must not be after care_plan.end")
    except ValueError as error:
        if str(error).startswith("care_plan"):
            raise
        raise ValueError("care_plan.start and care_plan.end must be ISO dates") from error

    return CarePlan.parse_obj(
        {
            "resourceType": "CarePlan",
            "id": care_plan_id,
            "meta": _synthetic_meta(),
            "status": _required_text(care_plan.get("status"), "care_plan.status"),
            "intent": _required_text(care_plan.get("intent"), "care_plan.intent"),
            "title": _required_text(care_plan.get("title"), "care_plan.title"),
            "description": _required_text(
                care_plan.get("description"), "care_plan.description"
            ),
            "subject": {"reference": patient_reference},
            "period": {"start": start, "end": end},
            "activity": [
                {
                    "detail": {
                        "status": "scheduled",
                        "description": _required_text(
                            care_plan.get("activity"), "care_plan.activity"
                        ),
                    }
                }
            ],
        }
    )


def build_resources(record: dict[str, Any]) -> list[Any]:
    """Build and cross-check all four required FHIR R4 resource types."""
    if __fhir_version__ != FHIR_VERSION:
        raise RuntimeError(
            f"expected FHIR {FHIR_VERSION}, but fhir.resources provides {__fhir_version__}"
        )
    if record.get("classification") != "synthetic":
        raise ValueError("FHIR demo accepts only records classified as synthetic")
    if record.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {INPUT_SCHEMA_VERSION}")

    recorded_date = _required_text(record.get("recorded_date"), "recorded_date")
    try:
        date.fromisoformat(recorded_date)
    except ValueError as error:
        raise ValueError("recorded_date must be an ISO date") from error
    timezone = _required_text(record.get("timezone"), "timezone")

    patient = _build_patient(record)
    patient_reference = f"Patient/{patient.id}"
    resources: list[Any] = [patient]
    resources.extend(
        _build_medication_statements(record, patient_reference, recorded_date, timezone)
    )
    resources.extend(_build_observations(record, patient_reference, recorded_date, timezone))
    resources.append(_build_care_plan(record, patient_reference))
    validate_collection(resources)
    return resources


def validate_collection(resources: list[Any]) -> None:
    """Validate model serialization, resource types, IDs, and local Patient references."""
    if not resources:
        raise ValueError("FHIR resource collection is empty")

    seen_ids: set[tuple[str, str]] = set()
    types: set[str] = set()
    patient_references: set[str] = set()
    subject_references: list[str] = []

    for resource in resources:
        payload = json.loads(resource.json(exclude_none=True, by_alias=True))
        resource_type = payload.get("resourceType")
        if resource_type not in RESOURCE_MODELS:
            raise ValueError(f"unsupported FHIR resource type: {resource_type}")
        RESOURCE_MODELS[resource_type].parse_obj(payload)
        resource_id = _required_text(payload.get("id"), f"{resource_type}.id")
        key = (resource_type, resource_id)
        if key in seen_ids:
            raise ValueError(f"duplicate FHIR resource identity: {resource_type}/{resource_id}")
        seen_ids.add(key)
        types.add(resource_type)
        if resource_type == "Patient":
            patient_references.add(f"Patient/{resource_id}")
        elif "subject" in payload:
            subject_references.append(payload["subject"].get("reference", ""))

    missing = set(RESOURCE_MODELS) - types
    if missing:
        raise ValueError(f"missing required FHIR resource type(s): {', '.join(sorted(missing))}")
    unresolved = sorted(set(subject_references) - patient_references)
    if unresolved:
        raise ValueError(f"unresolved Patient reference(s): {', '.join(unresolved)}")


def _entry_full_url(resource_type: str, resource_id: str) -> str:
    identity = f"https://veai.jp/fhir/{resource_type}/{resource_id}"
    return f"urn:uuid:{uuid5(NAMESPACE_URL, identity)}"


def _rewrite_local_references(value: Any, full_urls: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [_rewrite_local_references(item, full_urls) for item in value]
    if not isinstance(value, dict):
        return value
    rewritten = {
        key: _rewrite_local_references(item, full_urls) for key, item in value.items()
    }
    reference = rewritten.get("reference")
    if isinstance(reference, str) and reference in full_urls:
        rewritten["reference"] = full_urls[reference]
    return rewritten


def _collect_references(value: Any) -> list[str]:
    if isinstance(value, list):
        return [reference for item in value for reference in _collect_references(item)]
    if not isinstance(value, dict):
        return []
    references = []
    if isinstance(value.get("reference"), str):
        references.append(value["reference"])
    for item in value.values():
        references.extend(_collect_references(item))
    return references


def build_transaction_bundle(
    resources: list[Any], bundle_id: str = BUNDLE_ID
) -> Bundle:
    """Build a deterministic PUT transaction with resolvable urn:uuid references."""
    validate_collection(resources)
    bundle_id = _resource_id(bundle_id, "bundle_id")
    payloads = [
        json.loads(resource.json(exclude_none=True, by_alias=True)) for resource in resources
    ]
    full_urls = {
        f"{payload['resourceType']}/{payload['id']}": _entry_full_url(
            payload["resourceType"], payload["id"]
        )
        for payload in payloads
    }
    entries = []
    for payload in payloads:
        identity = f"{payload['resourceType']}/{payload['id']}"
        entries.append(
            {
                "fullUrl": full_urls[identity],
                "resource": _rewrite_local_references(deepcopy(payload), full_urls),
                "request": {"method": "PUT", "url": identity},
            }
        )

    bundle = Bundle.parse_obj(
        {
            "resourceType": "Bundle",
            "id": bundle_id,
            "meta": _synthetic_meta(),
            "type": "transaction",
            "entry": entries,
        }
    )
    validate_transaction_bundle(bundle)
    return bundle


def validate_transaction_bundle(bundle: Bundle) -> None:
    """Enforce transaction request, identity, and internal-reference invariants."""
    payload = json.loads(bundle.json(exclude_none=True, by_alias=True))
    if payload.get("type") != "transaction":
        raise ValueError("FHIR Bundle must have type transaction")
    entries = payload.get("entry")
    if not isinstance(entries, list) or not entries:
        raise ValueError("FHIR transaction Bundle must contain entries")

    full_urls = [entry.get("fullUrl") for entry in entries]
    if any(not isinstance(full_url, str) or not full_url.startswith("urn:uuid:") for full_url in full_urls):
        raise ValueError("every transaction entry must have a urn:uuid fullUrl")
    if len(full_urls) != len(set(full_urls)):
        raise ValueError("transaction entry fullUrls must be unique")

    for entry in entries:
        resource = entry.get("resource", {})
        identity = f"{resource.get('resourceType')}/{resource.get('id')}"
        request = entry.get("request", {})
        if request.get("method") != "PUT" or request.get("url") != identity:
            raise ValueError(f"transaction request does not match resource identity: {identity}")

    unresolved = sorted(
        {
            reference
            for entry in entries
            for reference in _collect_references(entry.get("resource", {}))
            if reference.startswith("urn:uuid:") and reference not in set(full_urls)
        }
    )
    if unresolved:
        raise ValueError(f"unresolved transaction reference(s): {', '.join(unresolved)}")


def serialize_resource(resource: Any) -> str:
    payload = json.loads(resource.json(exclude_none=True, by_alias=True))
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def output_name(resource: Any) -> str:
    resource_type = resource.get_resource_type()
    return f"{resource_type.lower()}-{resource.id}.json"


def render_outputs(record: dict[str, Any]) -> dict[str, str]:
    resources = build_resources(record)
    resource_outputs = {
        output_name(resource): serialize_resource(resource) for resource in resources
    }
    bundle = build_transaction_bundle(resources)
    outputs = dict(resource_outputs)
    outputs[BUNDLE_FILE] = serialize_resource(bundle)
    manifest = {
        "artifact_count": len(outputs),
        "bundle_file": BUNDLE_FILE,
        "classification": "synthetic",
        "fhir_release": FHIR_VERSION,
        "generator": "scripts/export_synthetic_fhir.py",
        "resource_count": len(resources),
        "resource_files": sorted(resource_outputs),
        "resource_types": sorted({resource.get_resource_type() for resource in resources}),
        "files": sorted(outputs),
        "validation_scope": (
            "fhir.resources model validation, transaction invariants, deterministic identities, "
            "and offline HL7 Validator CLI checks; not terminology-server, implementation-guide, "
            "clinical, or regulatory validation"
        ),
    }
    outputs["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    return outputs
