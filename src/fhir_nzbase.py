"""Create a bounded NZ Base derivative of the synthetic weekly FHIR Bundle."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from typing import Any

from fhir.resources.bundle import Bundle

from fhir_export import validate_transaction_bundle


FHIR_VERSION = "4.0.1"
NZ_BASE_PACKAGE_ID = "fhir.org.nz.ig.base"
NZ_BASE_PACKAGE_VERSION = "3.1.0"
NZ_BASE_PACKAGE = f"{NZ_BASE_PACKAGE_ID}#{NZ_BASE_PACKAGE_VERSION}"
NZ_PATIENT_PROFILE = "http://hl7.org.nz/fhir/StructureDefinition/NzPatient"
NZ_MEDICATION_STATEMENT_PROFILE = (
    "http://hl7.org.nz/fhir/StructureDefinition/NzMedicationStatement"
)
NHI_SYSTEM = "https://standards.digital.health.nz/ns/nhi-id"
SYNTHETIC_IDENTIFIER_SYSTEM = "https://veai.jp/fhir/synthetic-patient"
CLASSIFICATION_SYSTEM = "https://veai.jp/fhir/CodeSystem/data-classification"
NZ_BASE_BUNDLE_ID = "synthetic-weekly-nzbase-transaction-bundle"
NZ_BASE_BUNDLE_FILE = f"bundle-{NZ_BASE_BUNDLE_ID}.json"

PROFILE_BY_RESOURCE_TYPE = {
    "Patient": NZ_PATIENT_PROFILE,
    "MedicationStatement": NZ_MEDICATION_STATEMENT_PROFILE,
}
EXPECTED_RESOURCE_COUNTS = {
    "CarePlan": 1,
    "MedicationStatement": 14,
    "Observation": 14,
    "Patient": 1,
}


def _serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _has_synthetic_tag(resource: dict[str, Any]) -> bool:
    return any(
        tag.get("system") == CLASSIFICATION_SYSTEM and tag.get("code") == "synthetic"
        for tag in resource.get("meta", {}).get("tag", [])
        if isinstance(tag, dict)
    )


def _entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    entries = bundle.get("entry")
    if not isinstance(entries, list) or not entries:
        raise ValueError("FHIR transaction Bundle must contain entries")
    if any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("FHIR transaction Bundle entries must be objects")
    return entries


def validate_source_bundle(bundle: dict[str, Any]) -> None:
    """Require the reviewed weekly synthetic transaction before applying profiles."""
    if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "transaction":
        raise ValueError("NZ Base source must be a transaction Bundle")
    if bundle.get("id") != "synthetic-weekly-transaction-bundle":
        raise ValueError("NZ Base source Bundle id is not the reviewed weekly id")
    if not _has_synthetic_tag(bundle):
        raise ValueError("NZ Base source Bundle must be classified as synthetic")

    counts: Counter[str] = Counter()
    for entry in _entries(bundle):
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            raise ValueError("NZ Base source entry must contain a resource")
        resource_type = resource.get("resourceType")
        counts[resource_type] += 1
        if not _has_synthetic_tag(resource):
            raise ValueError(
                f"NZ Base source resource is not classified as synthetic: {resource_type}"
            )
        if resource.get("meta", {}).get("profile"):
            raise ValueError("NZ Base source resources must not predeclare profiles")
    if dict(counts) != EXPECTED_RESOURCE_COUNTS:
        raise ValueError("NZ Base source resource counts do not match the reviewed contract")
    validate_transaction_bundle(Bundle.parse_obj(bundle))


def build_nzbase_bundle(source_bundle: dict[str, Any]) -> dict[str, Any]:
    """Add only the two NZ Base profiles available for ParkinSync resource types."""
    validate_source_bundle(source_bundle)
    bundle = deepcopy(source_bundle)
    bundle["id"] = NZ_BASE_BUNDLE_ID
    for entry in bundle["entry"]:
        resource = entry["resource"]
        profile = PROFILE_BY_RESOURCE_TYPE.get(resource["resourceType"])
        if profile:
            resource.setdefault("meta", {})["profile"] = [profile]
    validate_nzbase_bundle(bundle)
    return bundle


def validate_nzbase_bundle(bundle: dict[str, Any]) -> None:
    """Enforce the exact profile, identity, and no-inference boundary."""
    if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "transaction":
        raise ValueError("NZ Base derivative must be a transaction Bundle")
    if bundle.get("id") != NZ_BASE_BUNDLE_ID:
        raise ValueError("NZ Base derivative Bundle id is not reviewed")
    if not _has_synthetic_tag(bundle):
        raise ValueError("NZ Base derivative Bundle must be classified as synthetic")

    counts: Counter[str] = Counter()
    profile_counts: Counter[str] = Counter()
    for entry in _entries(bundle):
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            raise ValueError("NZ Base derivative entry must contain a resource")
        resource_type = resource.get("resourceType")
        counts[resource_type] += 1
        if not _has_synthetic_tag(resource):
            raise ValueError(f"NZ Base derivative lost synthetic tag: {resource_type}")

        expected_profile = PROFILE_BY_RESOURCE_TYPE.get(resource_type)
        profiles = resource.get("meta", {}).get("profile", [])
        if expected_profile:
            if profiles != [expected_profile]:
                raise ValueError(f"NZ Base profile declaration is invalid: {resource_type}")
            profile_counts[expected_profile] += 1
        elif profiles:
            raise ValueError(f"NZ Base has no reviewed profile for {resource_type}")

        if resource_type == "Patient":
            if resource.get("extension"):
                raise ValueError("NZ-specific Patient extensions must not be inferred")
            identifiers = resource.get("identifier", [])
            if any(identifier.get("system") == NHI_SYSTEM for identifier in identifiers):
                raise ValueError("synthetic NZ Base derivative must not contain an NHI")
            if len(identifiers) != 1 or identifiers[0].get("system") != (
                SYNTHETIC_IDENTIFIER_SYSTEM
            ) or identifiers[0].get("use") != "temp":
                raise ValueError("Patient must retain the reviewed temporary synthetic identifier")
        if resource_type == "MedicationStatement":
            medication = resource.get("medicationCodeableConcept", {})
            if medication.get("coding"):
                raise ValueError("NZMT medication coding must not be inferred")

    if dict(counts) != EXPECTED_RESOURCE_COUNTS:
        raise ValueError("NZ Base derivative resource counts do not match the reviewed contract")
    expected_profile_counts = {
        NZ_MEDICATION_STATEMENT_PROFILE: 14,
        NZ_PATIENT_PROFILE: 1,
    }
    if dict(profile_counts) != expected_profile_counts:
        raise ValueError("NZ Base derivative profile counts do not match the reviewed contract")
    validate_transaction_bundle(Bundle.parse_obj(bundle))


def render_nzbase_outputs(source_bundle: dict[str, Any]) -> dict[str, str]:
    source_content = _serialize(source_bundle)
    bundle = build_nzbase_bundle(source_bundle)
    bundle_content = _serialize(bundle)
    manifest = {
        "artifact_count": 1,
        "base_only_resource_type_counts": {"CarePlan": 1, "Observation": 14},
        "bundle_file": NZ_BASE_BUNDLE_FILE,
        "classification": "synthetic",
        "excluded_inferences": [
            "NHI",
            "NZ ethnicity or iwi",
            "citizenship or residency",
            "address or sex at birth",
            "NZMT medication coding",
            "diagnosis or treatment meaning",
        ],
        "fhir_release": FHIR_VERSION,
        "files": [NZ_BASE_BUNDLE_FILE],
        "generator": "scripts/generate_nzbase_fhir.py",
        "nz_base_package": NZ_BASE_PACKAGE,
        "profile_counts": {
            NZ_MEDICATION_STATEMENT_PROFILE: 14,
            NZ_PATIENT_PROFILE: 1,
        },
        "profiled_resource_count": 15,
        "resource_count": 30,
        "resource_type_counts": EXPECTED_RESOURCE_COUNTS,
        "schema_version": "parkinsync-fhir-nzbase-v1",
        "sha256": {
            NZ_BASE_BUNDLE_FILE: hashlib.sha256(bundle_content.encode("utf-8")).hexdigest()
        },
        "source_bundle": (
            "fhir/weekly/generated/bundle-synthetic-weekly-transaction-bundle.json"
        ),
        "source_bundle_id": source_bundle.get("id"),
        "source_bundle_sha256": hashlib.sha256(source_content.encode("utf-8")).hexdigest(),
        "validation_scope": (
            "instance validation for NzPatient and NzMedicationStatement against the pinned "
            "published NZ Base package; Observation and CarePlan remain base FHIR R4"
        ),
    }
    return {
        NZ_BASE_BUNDLE_FILE: bundle_content,
        "manifest.json": _serialize(manifest),
    }
