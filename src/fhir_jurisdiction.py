"""Shared contracts for bounded jurisdiction-specific FHIR profile overlays."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from fhir.resources.bundle import Bundle

from fhir_export import validate_transaction_bundle


CLASSIFICATION_SYSTEM = "https://veai.jp/fhir/CodeSystem/data-classification"
EXPECTED_RESOURCE_COUNTS = {
    "CarePlan": 1,
    "MedicationStatement": 14,
    "Observation": 14,
    "Patient": 1,
}
SOURCE_BUNDLE_ID = "synthetic-weekly-transaction-bundle"


@dataclass(frozen=True)
class JurisdictionProfileSpec:
    label: str
    bundle_id: str
    profile_by_resource_type: Mapping[str, str]
    resource_overlay: Callable[[dict[str, Any]], None] | None = None


def _apply_resource_overlay(
    resource: dict[str, Any], spec: JurisdictionProfileSpec
) -> None:
    profile = spec.profile_by_resource_type.get(resource["resourceType"])
    if profile:
        resource.setdefault("meta", {})["profile"] = [profile]
    if spec.resource_overlay is not None:
        spec.resource_overlay(resource)


def has_synthetic_tag(resource: dict[str, Any]) -> bool:
    return any(
        tag.get("system") == CLASSIFICATION_SYSTEM and tag.get("code") == "synthetic"
        for tag in resource.get("meta", {}).get("tag", [])
        if isinstance(tag, dict)
    )


def entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    result = bundle.get("entry")
    if not isinstance(result, list) or not result:
        raise ValueError("FHIR transaction Bundle must contain entries")
    if any(not isinstance(entry, dict) for entry in result):
        raise ValueError("FHIR transaction Bundle entries must be objects")
    return result


def validate_reviewed_source(bundle: dict[str, Any], label: str) -> None:
    if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "transaction":
        raise ValueError(f"{label} source must be a transaction Bundle")
    if bundle.get("id") != SOURCE_BUNDLE_ID:
        raise ValueError(f"{label} source Bundle id is not the reviewed weekly id")
    if not has_synthetic_tag(bundle):
        raise ValueError(f"{label} source Bundle must be classified as synthetic")

    counts: Counter[str] = Counter()
    for entry in entries(bundle):
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            raise ValueError(f"{label} source entry must contain a resource")
        resource_type = resource.get("resourceType")
        counts[resource_type] += 1
        if not has_synthetic_tag(resource):
            raise ValueError(
                f"{label} source resource is not classified as synthetic: {resource_type}"
            )
        if resource.get("meta", {}).get("profile"):
            raise ValueError(f"{label} source resources must not predeclare profiles")
    if dict(counts) != EXPECTED_RESOURCE_COUNTS:
        raise ValueError(f"{label} source resource counts do not match the reviewed contract")
    validate_transaction_bundle(Bundle.parse_obj(bundle))


def build_profile_overlay(
    source_bundle: dict[str, Any], spec: JurisdictionProfileSpec
) -> dict[str, Any]:
    """Add profile declarations while preserving every source semantic value."""
    validate_reviewed_source(source_bundle, spec.label)
    bundle = deepcopy(source_bundle)
    bundle["id"] = spec.bundle_id
    for entry in bundle["entry"]:
        _apply_resource_overlay(entry["resource"], spec)
    validate_profile_overlay(source_bundle, bundle, spec)
    return bundle


def validate_profile_overlay(
    source_bundle: dict[str, Any],
    bundle: dict[str, Any],
    spec: JurisdictionProfileSpec,
) -> Counter[str]:
    if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "transaction":
        raise ValueError(f"{spec.label} derivative must be a transaction Bundle")
    if bundle.get("id") != spec.bundle_id:
        raise ValueError(f"{spec.label} derivative Bundle id is not reviewed")
    if not has_synthetic_tag(bundle):
        raise ValueError(f"{spec.label} derivative Bundle must be classified as synthetic")

    counts: Counter[str] = Counter()
    profile_counts: Counter[str] = Counter()
    for entry in entries(bundle):
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            raise ValueError(f"{spec.label} derivative entry must contain a resource")
        resource_type = resource.get("resourceType")
        counts[resource_type] += 1
        if not has_synthetic_tag(resource):
            raise ValueError(f"{spec.label} derivative lost synthetic tag: {resource_type}")

        expected_profile = spec.profile_by_resource_type.get(resource_type)
        profiles = resource.get("meta", {}).get("profile", [])
        if expected_profile:
            if profiles != [expected_profile]:
                raise ValueError(
                    f"{spec.label} profile declaration is invalid: {resource_type}"
                )
            profile_counts[expected_profile] += 1
        elif profiles:
            raise ValueError(
                f"{spec.label} has no reviewed profile for {resource_type}"
            )

    if dict(counts) != EXPECTED_RESOURCE_COUNTS:
        raise ValueError(
            f"{spec.label} derivative resource counts do not match the reviewed contract"
        )

    expected = deepcopy(source_bundle)
    expected["id"] = spec.bundle_id
    for entry in expected["entry"]:
        _apply_resource_overlay(entry["resource"], spec)
    if bundle != expected:
        raise ValueError(
            f"{spec.label} derivative changed data beyond the reviewed overlay"
        )
    validate_transaction_bundle(Bundle.parse_obj(bundle))
    return profile_counts
