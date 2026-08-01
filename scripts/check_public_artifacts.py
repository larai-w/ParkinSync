#!/usr/bin/env python3
"""Guard against accidentally publishing sensitive capstone artifacts."""

from __future__ import annotations

import csv
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

    if failures:
        print("Public artifact check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Public artifact check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
