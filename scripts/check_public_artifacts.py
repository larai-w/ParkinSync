#!/usr/bin/env python3
"""Guard against accidentally publishing sensitive capstone artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


FORBIDDEN_PATHS = {
    "docs/v1.3.0_Final_Report.pdf",
    "docs/v1.3.0_Presentation_Slides.pdf",
    "analytics/sample_data_v1.3.csv",
}

SYNTHETIC_FIXTURE_PATH = Path("analytics/synthetic_sample_data_v1.3.csv")
SYNTHETIC_MANIFEST_PATH = Path("analytics/synthetic_fixture_manifest.json")
SCHEMA_PATH = Path("design/master_schema_template.csv")
FHIR_INPUT_PATH = Path("fhir/synthetic_normalized_record.json")
FHIR_OUTPUT_DIR = Path("fhir/generated")
FHIR_MANIFEST_PATH = FHIR_OUTPUT_DIR / "manifest.json"
SUMMARY_DIR = Path("fhir/summary")
SUMMARY_OUTPUT_DIR = SUMMARY_DIR / "generated"
SUMMARY_MANIFEST_PATH = SUMMARY_OUTPUT_DIR / "manifest.json"
SUMMARY_EVALUATION_PATH = SUMMARY_DIR / "evaluation-cases.json"

REVIEW_REQUIRED_SUFFIXES = {
    ".pages",
    ".key",
    ".numbers",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
}

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ASIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"][^'\"]{20,}['\"]"),
    re.compile(r"(?i)private_key\s*[:=]\s*['\"]-----BEGIN"),
    re.compile(r"(?i)client_email\s*[:=]\s*['\"][^'\"]+@[^'\"]+['\"]"),
    re.compile(r"(?i)google_sheet_id\s*[:=]\s*['\"][A-Za-z0-9_-]{20,}['\"]"),
    re.compile(r"(?i)visual_crossing_key\s*[:=]\s*['\"][A-Za-z0-9_-]{20,}['\"]"),
    re.compile(r"(?i)switchbot_(?:token|secret|device_id)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
]

TEXT_SUFFIXES = {
    ".csv",
    ".env",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".svg",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def candidate_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line]


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {
        ".gitignore",
        "LICENSE",
        "README",
    }


def validate_synthetic_fixture() -> list[str]:
    failures: list[str] = []
    required = (SYNTHETIC_FIXTURE_PATH, SYNTHETIC_MANIFEST_PATH, SCHEMA_PATH)
    if missing := [path.as_posix() for path in required if not path.exists()]:
        return ["missing synthetic-fixture artifact: " + path for path in missing]

    try:
        with SCHEMA_PATH.open(newline="", encoding="utf-8") as source:
            expected_headers = next(csv.reader(source))
        with SYNTHETIC_FIXTURE_PATH.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            headers = reader.fieldnames
            rows = list(reader)
        manifest = json.loads(SYNTHETIC_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (csv.Error, json.JSONDecodeError, OSError, StopIteration) as error:
        return [f"cannot validate synthetic fixture: {error}"]

    if headers != expected_headers:
        failures.append("synthetic fixture does not exactly match the public master schema")
    if len(rows) < 14:
        failures.append("synthetic fixture must contain at least 14 rows")
    for row_number, row in enumerate(rows, start=2):
        markers = (
            row.get("Daily_Notes", "").startswith("SYNTHETIC_SCENARIO_"),
            row.get("Weather_Summary", "").startswith("SYNTHETIC_WEATHER_"),
            row.get("Switchbot_Summary", "").startswith("SYNTHETIC_INDOOR_"),
            row.get("File_Name", "").startswith("synthetic/"),
            row.get("Date", "").startswith("2035/"),
        )
        if not all(markers):
            failures.append(f"synthetic fixture row {row_number} lacks required markers")
    if manifest.get("classification") != "synthetic":
        failures.append("synthetic fixture manifest has no synthetic classification")
    if manifest.get("record_count") != len(rows):
        failures.append("synthetic fixture manifest record count does not match the CSV")
    return failures


def validate_synthetic_fhir_artifacts() -> list[str]:
    failures: list[str] = []
    try:
        source = json.loads(FHIR_INPUT_PATH.read_text(encoding="utf-8"))
        manifest = json.loads(FHIR_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        return [f"cannot validate synthetic FHIR artifacts: {error}"]

    if source.get("classification") != "synthetic":
        failures.append("FHIR source fixture must be classified as synthetic")
    if not source.get("patient", {}).get("id", "").startswith("synthetic-"):
        failures.append("FHIR source Patient id must use the synthetic prefix")
    if manifest.get("classification") != "synthetic":
        failures.append("FHIR manifest must be classified as synthetic")
    if manifest.get("fhir_release") != "4.0.1":
        failures.append("FHIR manifest must declare release 4.0.1")

    expected_names = manifest.get("files")
    if not isinstance(expected_names, list):
        failures.append("FHIR manifest files must be an array")
        expected_names = []
    actual_paths = sorted(
        path for path in FHIR_OUTPUT_DIR.glob("*.json") if path.name != "manifest.json"
    )
    if [path.name for path in actual_paths] != sorted(expected_names):
        failures.append("FHIR manifest file list does not match generated resources")
    if manifest.get("artifact_count") != len(actual_paths):
        failures.append("FHIR manifest artifact count does not match generated artifacts")

    resource_names = manifest.get("resource_files")
    if not isinstance(resource_names, list):
        failures.append("FHIR manifest resource_files must be an array")
        resource_names = []
    resource_paths = [FHIR_OUTPUT_DIR / name for name in resource_names]
    if manifest.get("resource_count") != len(resource_paths):
        failures.append("FHIR manifest resource count does not match generated resources")

    found_types: set[str] = set()
    for path in resource_paths:
        try:
            resource = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            failures.append(f"cannot parse {path.as_posix()}: {error}")
            continue
        resource_type = resource.get("resourceType")
        found_types.add(resource_type)
        if not resource.get("id", "").startswith("synthetic-"):
            failures.append(f"FHIR resource lacks synthetic id: {path.as_posix()}")
        tags = resource.get("meta", {}).get("tag", [])
        if not any(tag.get("code") == "synthetic" for tag in tags):
            failures.append(f"FHIR resource lacks synthetic classification: {path.as_posix()}")

    required_types = {"Patient", "MedicationStatement", "Observation", "CarePlan"}
    if found_types != required_types:
        failures.append("FHIR artifacts must contain exactly the four required resource types")

    bundle_name = manifest.get("bundle_file")
    if not isinstance(bundle_name, str) or not bundle_name:
        failures.append("FHIR manifest must identify one transaction Bundle")
        return failures
    try:
        bundle = json.loads((FHIR_OUTPUT_DIR / bundle_name).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        failures.append(f"cannot parse FHIR transaction Bundle: {error}")
        return failures
    if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "transaction":
        failures.append("FHIR Bundle artifact must be a transaction Bundle")
    if not bundle.get("id", "").startswith("synthetic-"):
        failures.append("FHIR Bundle must use a synthetic id")
    bundle_tags = bundle.get("meta", {}).get("tag", [])
    if not any(tag.get("code") == "synthetic" for tag in bundle_tags):
        failures.append("FHIR Bundle must carry the synthetic classification")
    entries = bundle.get("entry", [])
    if len(entries) != manifest.get("resource_count"):
        failures.append("FHIR Bundle entry count does not match resource count")
    full_urls = [entry.get("fullUrl") for entry in entries]
    if len(full_urls) != len(set(full_urls)) or any(
        not isinstance(full_url, str) or not full_url.startswith("urn:uuid:")
        for full_url in full_urls
    ):
        failures.append("FHIR Bundle fullUrls must be unique urn:uuid values")
    for entry in entries:
        resource = entry.get("resource", {})
        expected_url = f"{resource.get('resourceType')}/{resource.get('id')}"
        request = entry.get("request", {})
        if request.get("method") != "PUT" or request.get("url") != expected_url:
            failures.append(f"FHIR Bundle request does not match {expected_url}")
        reference = resource.get("subject", {}).get("reference")
        if reference and reference not in full_urls:
            failures.append(f"FHIR Bundle has an unresolved subject reference: {reference}")
    return failures


def validate_synthetic_summary_artifacts() -> list[str]:
    failures: list[str] = []
    required = (
        SUMMARY_EVALUATION_PATH,
        SUMMARY_MANIFEST_PATH,
        SUMMARY_OUTPUT_DIR / "fact-bundle.json",
        SUMMARY_OUTPUT_DIR / "offline-summary.json",
    )
    if missing := [path.as_posix() for path in required if not path.exists()]:
        return ["missing grounded-summary artifact: " + path for path in missing]
    try:
        evaluation = json.loads(SUMMARY_EVALUATION_PATH.read_text(encoding="utf-8"))
        manifest = json.loads(SUMMARY_MANIFEST_PATH.read_text(encoding="utf-8"))
        fact_bundle = json.loads(
            (SUMMARY_OUTPUT_DIR / "fact-bundle.json").read_text(encoding="utf-8")
        )
        summary = json.loads(
            (SUMMARY_OUTPUT_DIR / "offline-summary.json").read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as error:
        return [f"cannot validate grounded-summary artifacts: {error}"]

    for name, payload in (
        ("evaluation fixture", evaluation),
        ("summary manifest", manifest),
        ("fact bundle", fact_bundle),
        ("offline summary", summary),
    ):
        if payload.get("classification") != "synthetic":
            failures.append(f"{name} must be classified as synthetic")

    expected_names = manifest.get("files")
    if not isinstance(expected_names, list):
        failures.append("summary manifest files must be an array")
        expected_names = []
    actual_paths = sorted(
        path for path in SUMMARY_OUTPUT_DIR.glob("*.json") if path.name != "manifest.json"
    )
    if [path.name for path in actual_paths] != sorted(expected_names):
        failures.append("summary manifest file list does not match generated artifacts")
    hashes = manifest.get("sha256", {})
    for path in actual_paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashes.get(path.name) != digest:
            failures.append(f"summary manifest digest does not match {path.as_posix()}")

    facts = fact_bundle.get("facts")
    if fact_bundle.get("status") != "ready" or not isinstance(facts, list) or not facts:
        failures.append("tracked fact bundle must be ready and non-empty")
        facts = []
    fact_ids = [fact.get("id") for fact in facts]
    if len(fact_ids) != len(set(fact_ids)) or any(
        not isinstance(fact_id, str) or not fact_id.startswith("fact-")
        for fact_id in fact_ids
    ):
        failures.append("fact IDs must be unique and stable-looking")
    for fact in facts:
        source = fact.get("source", {})
        if not source.get("resource_id", "").startswith("synthetic-"):
            failures.append("summary fact source ID must use the synthetic prefix")
        values = source.get("values")
        if not isinstance(values, list) or not values:
            failures.append("summary fact must retain source values")
            continue
        for value in values:
            if not isinstance(value.get("fhir_path"), str) or not value.get("fhir_path"):
                failures.append("every summary fact value must retain a FHIR path")

    quality = fact_bundle.get("quality", {})
    finding_fields = (
        "missing_values",
        "duplicates",
        "unit_mismatches",
        "unresolved_references",
        "contradictory_statuses",
        "conflicting_timestamps",
        "invalid_resources",
        "prompt_injection_signals",
    )
    if any(quality.get(field) for field in finding_fields):
        failures.append("tracked fact bundle must not contain data-quality findings")
    if quality.get("coverage", {}).get("ratio") != 1.0:
        failures.append("tracked fact bundle must have complete required-value coverage")

    if summary.get("status") != "ready_for_human_review":
        failures.append("offline summary must stop at ready_for_human_review")
    if summary.get("requires_human_review") is not True:
        failures.append("offline summary must require human review")
    if summary.get("sharing_permitted") is not False:
        failures.append("offline summary must not permit sharing")
    if summary.get("validation", {}).get("accepted") is not True:
        failures.append("tracked offline summary must pass the deterministic candidate gate")
    cited_ids = {
        fact_id
        for statement in summary.get("statements", [])
        for fact_id in statement.get("fact_ids", [])
    }
    if not cited_ids.issubset(set(fact_ids)):
        failures.append("offline summary cites an unknown fact ID")
    return failures


def main() -> int:
    failures: list[str] = []
    tracked_or_untracked = set(candidate_files())

    for path in tracked_or_untracked:
        normalized = path.as_posix()
        suffix = path.suffix.lower()

        if normalized in FORBIDDEN_PATHS:
            failures.append(f"forbidden artifact is tracked: {normalized}")

        if suffix in REVIEW_REQUIRED_SUFFIXES:
            failures.append(
                f"manual review required before tracking source document: {normalized}"
            )

        if path.parts[:1] == ("analytics",) and suffix == ".png":
            failures.append(
                f"generated analytics image must be reproduced, not tracked: {normalized}"
            )

        if is_text_candidate(path) and path.exists():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    failures.append(
                        f"possible secret pattern {pattern.pattern!r} found in {normalized}"
                    )

    if SYNTHETIC_FIXTURE_PATH in tracked_or_untracked:
        failures.extend(validate_synthetic_fixture())
    if FHIR_INPUT_PATH in tracked_or_untracked:
        failures.extend(validate_synthetic_fhir_artifacts())
        failures.extend(validate_synthetic_summary_artifacts())

    if failures:
        print("Public artifact check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Public artifact check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
