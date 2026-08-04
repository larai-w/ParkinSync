"""Create a bounded JP Core derivative of the synthetic weekly FHIR Bundle."""

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
)


FHIR_VERSION = "4.0.1"
JP_CORE_PACKAGE_ID = "jpfhir.jp.core"
JP_CORE_PACKAGE_VERSION = "1.2.0"
JP_CORE_PACKAGE = f"{JP_CORE_PACKAGE_ID}#{JP_CORE_PACKAGE_VERSION}"
JP_CORE_PACKAGE_URL = "https://jpfhir.jp/fhir/core/1.2.0/package.tgz"
JP_CORE_PACKAGE_SHA256 = (
    "6094c8b9ebd975cb738c66cc999774c06a0aacf4480c068a8465e597117e52a3"
)
JP_TERMINOLOGY_PACKAGE = "jpfhir-terminology#1.4.0"
JP_TERMINOLOGY_PACKAGE_URL = (
    "https://jpfhir.jp/fhir/core/terminology/jpfhir-terminology.r4-1.4.0.tgz"
)
JP_TERMINOLOGY_PACKAGE_SHA256 = (
    "cfeb76457774d5a4bf1eb907cb60d083b0dedf04cb92405effa6b4aeaf68d21f"
)
JP_PATIENT_PROFILE = "http://jpfhir.jp/fhir/core/StructureDefinition/JP_Patient"
JP_VITAL_SIGNS_PROFILE = (
    "http://jpfhir.jp/fhir/core/StructureDefinition/JP_Observation_VitalSigns"
)
SYNTHETIC_IDENTIFIER_SYSTEM = "https://veai.jp/fhir/synthetic-patient"
JP_CORE_CANONICAL_PREFIX = "http://jpfhir.jp/fhir/core/"
JP_CORE_BUNDLE_ID = "synthetic-weekly-jpcore-transaction-bundle"
JP_CORE_BUNDLE_FILE = f"bundle-{JP_CORE_BUNDLE_ID}.json"

PROFILE_BY_RESOURCE_TYPE = {
    "Patient": JP_PATIENT_PROFILE,
    "Observation": JP_VITAL_SIGNS_PROFILE,
}
JP_CORE_SPEC = JurisdictionProfileSpec(
    label="JP Core",
    bundle_id=JP_CORE_BUNDLE_ID,
    profile_by_resource_type=PROFILE_BY_RESOURCE_TYPE,
)


def _serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def build_jpcore_bundle(source_bundle: dict[str, Any]) -> dict[str, Any]:
    bundle = build_profile_overlay(source_bundle, JP_CORE_SPEC)
    validate_jpcore_bundle(bundle, source_bundle)
    return bundle


def validate_jpcore_bundle(
    bundle: dict[str, Any], source_bundle: dict[str, Any]
) -> None:
    profile_counts = validate_profile_overlay(source_bundle, bundle, JP_CORE_SPEC)
    expected_profile_counts = {
        JP_PATIENT_PROFILE: 1,
        JP_VITAL_SIGNS_PROFILE: 14,
    }
    if dict(profile_counts) != expected_profile_counts:
        raise ValueError("JP Core derivative profile counts do not match the reviewed contract")

    for entry in entries(bundle):
        resource = entry["resource"]
        resource_type = resource["resourceType"]
        if resource_type == "Patient":
            identifiers = resource.get("identifier", [])
            if len(identifiers) != 1 or identifiers[0].get("system") != (
                SYNTHETIC_IDENTIFIER_SYSTEM
            ) or identifiers[0].get("use") != "temp":
                raise ValueError("Patient must retain the reviewed temporary synthetic identifier")
            if resource.get("extension"):
                raise ValueError("JP-specific Patient extensions must not be inferred")
        elif resource_type == "MedicationStatement":
            medication = resource.get("medicationCodeableConcept", {})
            if medication.get("coding"):
                raise ValueError("Japanese medication coding must not be inferred")

        for coding in _resource_codings(resource):
            system = coding.get("system")
            if isinstance(system, str) and system.startswith(JP_CORE_CANONICAL_PREFIX):
                raise ValueError("JP Core terminology coding must not be inferred")


def _resource_codings(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if "system" in value and ("code" in value or "display" in value):
            result.append(value)
        for child in value.values():
            result.extend(_resource_codings(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(_resource_codings(child))
    return result


def render_jpcore_outputs(source_bundle: dict[str, Any]) -> dict[str, str]:
    source_content = _serialize(source_bundle)
    bundle = build_jpcore_bundle(source_bundle)
    bundle_content = _serialize(bundle)
    manifest = {
        "artifact_count": 1,
        "base_only_resource_type_counts": {"CarePlan": 1, "MedicationStatement": 14},
        "bundle_file": JP_CORE_BUNDLE_FILE,
        "classification": "synthetic",
        "excluded_inferences": [
            "Japanese patient identifier",
            "name, address, sex, birth date, or other demographics",
            "YJ, HOT, GS1, or local medication coding",
            "JP Core terminology coding",
            "performer or institution",
            "diagnosis or treatment meaning",
        ],
        "fhir_release": FHIR_VERSION,
        "files": [JP_CORE_BUNDLE_FILE],
        "generator": "scripts/generate_jpcore_fhir.py",
        "jp_core_package": JP_CORE_PACKAGE,
        "jp_core_package_sha256": JP_CORE_PACKAGE_SHA256,
        "jp_core_package_url": JP_CORE_PACKAGE_URL,
        "jp_terminology_package": JP_TERMINOLOGY_PACKAGE,
        "jp_terminology_package_sha256": JP_TERMINOLOGY_PACKAGE_SHA256,
        "jp_terminology_package_url": JP_TERMINOLOGY_PACKAGE_URL,
        "profile_counts": {
            JP_PATIENT_PROFILE: 1,
            JP_VITAL_SIGNS_PROFILE: 14,
        },
        "profiled_resource_count": 15,
        "resource_count": 30,
        "resource_type_counts": EXPECTED_RESOURCE_COUNTS,
        "schema_version": "parkinsync-fhir-jpcore-v1",
        "sha256": {
            JP_CORE_BUNDLE_FILE: hashlib.sha256(
                bundle_content.encode("utf-8")
            ).hexdigest()
        },
        "source_bundle": (
            "fhir/weekly/generated/bundle-synthetic-weekly-transaction-bundle.json"
        ),
        "source_bundle_id": source_bundle.get("id"),
        "source_bundle_sha256": hashlib.sha256(
            source_content.encode("utf-8")
        ).hexdigest(),
        "validation_scope": (
            "instance validation for JP_Patient and JP_Observation_VitalSigns "
            "against the pinned JP Core package; MedicationStatement and CarePlan "
            "remain base FHIR R4"
        ),
    }
    return {
        JP_CORE_BUNDLE_FILE: bundle_content,
        "manifest.json": _serialize(manifest),
    }
