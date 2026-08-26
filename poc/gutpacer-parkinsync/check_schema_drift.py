#!/usr/bin/env python3
"""Fail when a vendored care-event/v1 schema drifts from the canonical schema."""

from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
from typing import Any


UNORDERED_ARRAY_KEYS = {"enum", "required"}


def normalize(value: Any, parent_key: str | None = None) -> Any:
    """Normalize JSON Schema formatting and order-insensitive string sets."""
    if isinstance(value, dict):
        return {key: normalize(value[key], key) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [normalize(item) for item in value]
        if parent_key in UNORDERED_ARRAY_KEYS and all(
            isinstance(item, str) for item in normalized
        ):
            return sorted(normalized)
        return normalized
    return value


def load_schema(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def normalized_text(schema: Any) -> str:
    return json.dumps(normalize(schema), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("canonical", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()

    canonical = normalized_text(load_schema(args.canonical))
    candidate = normalized_text(load_schema(args.candidate))
    if canonical == candidate:
        print("care-event/v1 schema drift check: PASS (semantic match)")
        return 0

    print("care-event/v1 schema drift check: FAIL", flush=True)
    print(
        "".join(
            difflib.unified_diff(
                canonical.splitlines(keepends=True),
                candidate.splitlines(keepends=True),
                fromfile=str(args.canonical),
                tofile=str(args.candidate),
            )
        ),
        end="",
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
