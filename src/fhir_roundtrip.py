"""Post a synthetic FHIR transaction and verify every stored resource by read-back."""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


ROUNDTRIP_SCHEMA_VERSION = "parkinsync-fhir-roundtrip-result-v1"
FHIR_JSON = "application/fhir+json"
SERVER_MANAGED_META_FIELDS = {"lastUpdated", "source", "versionId"}


class RoundTripError(RuntimeError):
    """Raised when server capability, transaction, or read-back evidence fails."""


def _require_loopback(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        raise RoundTripError("FHIR round-trip server must use a loopback URL")


def _request_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any]]:
    base = base_url.rstrip("/") + "/"
    url = urljoin(base, path.lstrip("/")) if path else base_url.rstrip("/")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Accept": FHIR_JSON, "Content-Type": FHIR_JSON},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RoundTripError(f"{method} {path or '/'} returned HTTP {error.code}") from error
    except URLError as error:
        raise RoundTripError(f"{method} {path or '/'} could not reach the FHIR server") from error
    except OSError as error:
        raise RoundTripError(f"{method} {path or '/'} lost the FHIR server connection") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RoundTripError(f"{method} {path or '/'} returned non-JSON content") from error
    if not isinstance(data, dict):
        raise RoundTripError(f"{method} {path or '/'} returned a non-object JSON body")
    return status, data


def fetch_capability(base_url: str, timeout: float = 30.0) -> dict[str, Any]:
    _require_loopback(base_url)
    status, capability = _request_json(base_url, "GET", "metadata", timeout=timeout)
    if status != 200 or capability.get("resourceType") != "CapabilityStatement":
        raise RoundTripError("FHIR metadata endpoint did not return a CapabilityStatement")
    if capability.get("fhirVersion") != "4.0.1":
        raise RoundTripError(
            f"FHIR server must declare R4 4.0.1, found {capability.get('fhirVersion')!r}"
        )
    rest_modes = {
        rest.get("mode") for rest in capability.get("rest", []) if isinstance(rest, dict)
    }
    if "server" not in rest_modes:
        raise RoundTripError("CapabilityStatement does not declare a server REST endpoint")
    return capability


def _resource_identity(resource: dict[str, Any]) -> str:
    resource_type = resource.get("resourceType")
    resource_id = resource.get("id")
    if not isinstance(resource_type, str) or not isinstance(resource_id, str):
        raise RoundTripError("FHIR resource is missing resourceType or id")
    return f"{resource_type}/{resource_id}"


def _location_identity(location: str, known_identities: set[str]) -> str | None:
    clean = location.split("?", 1)[0].rstrip("/")
    if "/_history/" in clean:
        clean = clean.split("/_history/", 1)[0]
    for identity in sorted(known_identities):
        if clean == identity or clean.endswith("/" + identity):
            return identity
    return None


def _normalize_reference(
    reference: str,
    full_url_identities: dict[str, str],
    known_identities: set[str],
) -> str:
    if reference in full_url_identities:
        return full_url_identities[reference]
    resolved = _location_identity(reference, known_identities)
    return resolved or reference


def _normalize_value(
    value: Any,
    full_url_identities: dict[str, str],
    known_identities: set[str],
) -> Any:
    if isinstance(value, list):
        return [
            _normalize_value(item, full_url_identities, known_identities)
            for item in value
        ]
    if not isinstance(value, dict):
        return value
    normalized = {}
    for key, item in value.items():
        if key == "meta" and isinstance(item, dict):
            meta = {
                meta_key: _normalize_value(
                    meta_value, full_url_identities, known_identities
                )
                for meta_key, meta_value in item.items()
                if meta_key not in SERVER_MANAGED_META_FIELDS
            }
            if meta:
                normalized[key] = meta
        elif key == "reference" and isinstance(item, str):
            normalized[key] = _normalize_reference(
                item, full_url_identities, known_identities
            )
        else:
            normalized[key] = _normalize_value(
                item, full_url_identities, known_identities
            )
    return normalized


def normalize_resource(
    resource: dict[str, Any],
    full_url_identities: dict[str, str],
    known_identities: set[str],
) -> dict[str, Any]:
    """Normalize only server-owned metadata and resolved transaction references."""
    return _normalize_value(deepcopy(resource), full_url_identities, known_identities)


def _diff_paths(expected: Any, actual: Any, path: str = "$") -> list[str]:
    if type(expected) is not type(actual):
        return [path]
    if isinstance(expected, dict):
        paths = []
        for key in sorted(set(expected) | set(actual)):
            child = f"{path}.{key}"
            if key not in expected or key not in actual:
                paths.append(child)
            else:
                paths.extend(_diff_paths(expected[key], actual[key], child))
        return paths
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [path + ".length"]
        return [
            changed
            for index, (expected_item, actual_item) in enumerate(zip(expected, actual))
            for changed in _diff_paths(expected_item, actual_item, f"{path}[{index}]")
        ]
    return [] if expected == actual else [path]


def _has_synthetic_tag(resource: dict[str, Any]) -> bool:
    return any(
        tag.get("system") == "https://veai.jp/fhir/CodeSystem/data-classification"
        and tag.get("code") == "synthetic"
        for tag in resource.get("meta", {}).get("tag", [])
        if isinstance(tag, dict)
    )


def verify_roundtrip(
    base_url: str, bundle: dict[str, Any], timeout: float = 30.0
) -> dict[str, Any]:
    """Verify R4 capability, transaction response, and semantic read-back equality."""
    if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "transaction":
        raise RoundTripError("input must be a FHIR transaction Bundle")
    _require_loopback(base_url)
    if not _has_synthetic_tag(bundle):
        raise RoundTripError("transaction Bundle must carry the synthetic classification")
    entries = bundle.get("entry")
    if not isinstance(entries, list) or not entries:
        raise RoundTripError("transaction Bundle must contain entries")

    expected_by_identity: dict[str, dict[str, Any]] = {}
    full_url_identities: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RoundTripError("transaction Bundle entries must be objects")
        resource = entry.get("resource", {})
        identity = _resource_identity(resource)
        if not _has_synthetic_tag(resource):
            raise RoundTripError(
                f"transaction resource lacks synthetic classification: {identity}"
            )
        request = entry.get("request", {})
        if request.get("method") != "PUT" or request.get("url") != identity:
            raise RoundTripError(f"transaction request does not match {identity}")
        if identity in expected_by_identity:
            raise RoundTripError(f"duplicate transaction identity: {identity}")
        expected_by_identity[identity] = resource
        full_url = entry.get("fullUrl")
        if not isinstance(full_url, str) or not full_url.startswith("urn:uuid:"):
            raise RoundTripError(f"transaction fullUrl is not a urn:uuid for {identity}")
        if full_url in full_url_identities:
            raise RoundTripError(f"duplicate transaction fullUrl: {full_url}")
        full_url_identities[full_url] = identity
    known_identities = set(expected_by_identity)
    capability = fetch_capability(base_url, timeout=timeout)

    status, response_bundle = _request_json(
        base_url, "POST", "", payload=bundle, timeout=timeout
    )
    if status not in {200, 201}:
        raise RoundTripError(f"transaction POST returned HTTP {status}")
    if (
        response_bundle.get("resourceType") != "Bundle"
        or response_bundle.get("type") != "transaction-response"
    ):
        raise RoundTripError("transaction POST did not return a transaction-response Bundle")
    response_entries = response_bundle.get("entry")
    if not isinstance(response_entries, list) or len(response_entries) != len(entries):
        raise RoundTripError("transaction-response entry count does not match the request")

    outcome_counts: Counter[str] = Counter()
    for index, (request_entry, response_entry) in enumerate(zip(entries, response_entries)):
        expected_identity = request_entry["request"]["url"]
        response = response_entry.get("response", {})
        response_status = str(response.get("status", ""))
        status_code = response_status.split(" ", 1)[0]
        if status_code not in {"200", "201"}:
            raise RoundTripError(
                f"transaction-response entry {index} failed with status {response_status!r}"
            )
        outcome_counts[status_code] += 1
        location = response.get("location")
        if not isinstance(location, str) or not location:
            raise RoundTripError(
                f"transaction-response entry {index} has no resource location"
            )
        location_identity = _location_identity(location, known_identities)
        if location_identity != expected_identity:
            raise RoundTripError(
                f"transaction-response entry {index} location does not match the request"
            )

    read_count = 0
    synthetic_tag_count = 0
    subject_reference_count = 0
    for identity, expected_resource in expected_by_identity.items():
        read_status, actual_resource = _request_json(
            base_url, "GET", identity, timeout=timeout
        )
        if read_status != 200:
            raise RoundTripError(f"read-back for {identity} returned HTTP {read_status}")
        if _resource_identity(actual_resource) != identity:
            raise RoundTripError(f"read-back identity does not match {identity}")
        if not _has_synthetic_tag(actual_resource):
            raise RoundTripError(f"read-back resource lost synthetic classification: {identity}")
        synthetic_tag_count += 1

        expected = normalize_resource(
            expected_resource, full_url_identities, known_identities
        )
        actual = normalize_resource(actual_resource, full_url_identities, known_identities)
        changed_paths = _diff_paths(expected, actual)
        if changed_paths:
            preview = ", ".join(changed_paths[:8])
            raise RoundTripError(
                f"read-back semantic mismatch for {identity} at {preview}"
            )
        if "subject" in expected_resource:
            subject_reference_count += 1
        read_count += 1

    software = capability.get("software", {})
    type_counts = Counter(identity.split("/", 1)[0] for identity in known_identities)
    return {
        "schema_version": ROUNDTRIP_SCHEMA_VERSION,
        "classification": "synthetic",
        "status": "passed",
        "source_bundle_id": bundle.get("id"),
        "server": {
            "product": software.get("name", "unspecified"),
            "version": software.get("version", "unspecified"),
            "fhir_version": capability.get("fhirVersion"),
        },
        "transport": "FHIR REST transaction POST followed by read by logical id",
        "resource_count": len(entries),
        "resource_type_counts": dict(sorted(type_counts.items())),
        "transaction_outcomes": dict(sorted(outcome_counts.items())),
        "checks": {
            "capability_r4": True,
            "transaction_response_entries": len(response_entries),
            "resources_read": read_count,
            "semantic_matches": read_count,
            "synthetic_tags": synthetic_tag_count,
            "subject_references_resolved": subject_reference_count,
        },
        "normalization": {
            "server_managed_meta_fields": sorted(SERVER_MANAGED_META_FIELDS),
            "transaction_full_urls": "resolved to ResourceType/id",
        },
    }
