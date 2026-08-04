"""Create a bounded NZ Base derivative of the synthetic weekly FHIR Bundle."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fhir_jurisdiction import (
    EXPECTED_RESOURCE_COUNTS,
    JurisdictionProfileSpec,
    build_profile_overlay,
    entries,
    validate_profile_overlay,
    validate_reviewed_source,
)


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
NZ_BASE_BUNDLE_ID = "synthetic-weekly-nzbase-transaction-bundle"
NZ_BASE_BUNDLE_FILE = f"bundle-{NZ_BASE_BUNDLE_ID}.json"

PROFILE_BY_RESOURCE_TYPE = {
    "Patient": NZ_PATIENT_PROFILE,
    "MedicationStatement": NZ_MEDICATION_STATEMENT_PROFILE,
}
NZ_BASE_SPEC = JurisdictionProfileSpec(
    label="NZ Base",
    bundle_id=NZ_BASE_BUNDLE_ID,
    profile_by_resource_type=PROFILE_BY_RESOURCE_TYPE,
)


def _serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def validate_source_bundle(bundle: dict[str, Any]) -> None:
    """Require the reviewed weekly synthetic transaction before applying profiles."""
    validate_reviewed_source(bundle, "NZ Base")


def build_nzbase_bundle(source_bundle: dict[str, Any]) -> dict[str, Any]:
    """Add only the two NZ Base profiles available for ParkinSync resource types."""
    bundle = build_profile_overlay(source_bundle, NZ_BASE_SPEC)
    validate_nzbase_bundle(bundle, source_bundle)
    return bundle


def validate_nzbase_bundle(
    bundle: dict[str, Any], source_bundle: dict[str, Any]
) -> None:
    """Enforce the exact profile, identity, and no-inference boundary."""
    profile_counts = validate_profile_overlay(source_bundle, bundle, NZ_BASE_SPEC)
    for entry in entries(bundle):
        resource = entry.get("resource")
        resource_type = resource.get("resourceType")
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

    expected_profile_counts = {
        NZ_MEDICATION_STATEMENT_PROFILE: 14,
        NZ_PATIENT_PROFILE: 1,
    }
    if dict(profile_counts) != expected_profile_counts:
        raise ValueError("NZ Base derivative profile counts do not match the reviewed contract")


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
