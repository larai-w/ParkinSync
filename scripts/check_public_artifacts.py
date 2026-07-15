#!/usr/bin/env python3
"""Guard against accidentally publishing sensitive capstone artifacts."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


FORBIDDEN_PATHS = {
    "docs/v1.3.0_Final_Report.pdf",
    "docs/v1.3.0_Presentation_Slides.pdf",
}

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


def main() -> int:
    failures: list[str] = []

    for path in candidate_files():
        normalized = path.as_posix()
        suffix = path.suffix.lower()

        if normalized in FORBIDDEN_PATHS:
            failures.append(f"forbidden artifact is tracked: {normalized}")

        if suffix in REVIEW_REQUIRED_SUFFIXES:
            failures.append(
                f"manual review required before tracking source document: {normalized}"
            )

        if is_text_candidate(path) and path.exists():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    failures.append(
                        f"possible secret pattern {pattern.pattern!r} found in {normalized}"
                    )

    if failures:
        print("Public artifact check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Public artifact check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
