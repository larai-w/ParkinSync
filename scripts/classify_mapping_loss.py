#!/usr/bin/env python3
"""Validate and summarize the P1 FHIR mapping-loss inventory."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path


DEFAULT_INPUT = (
    Path(__file__).resolve().parents[1]
    / "fhir"
    / "analysis"
    / "mapping-loss-inventory-v0.1.csv"
)

LOSS_MODES = {
    "L1_identity": "Identity linkage removed",
    "L2_time_semantics": "Event time and record time differ",
    "L3_missingness": "Missingness is not fully expressible",
    "L4_resource_ambiguous": "More than one resource target is defensible",
    "L5_local_semantics": "Meaning depends on a local unvalidated scale",
    "L6_misinterpretation": "A downstream reader could infer the wrong meaning",
    "L7_policy_outside_model": "Local policy is not guaranteed downstream",
}

EXPECTED = {
    "total": 15,
    "multi_label": 9,
    "clean": 0,
    "extensions": 4,
    "counts": {
        "L1_identity": 2,
        "L2_time_semantics": 2,
        "L3_missingness": 1,
        "L4_resource_ambiguous": 11,
        "L5_local_semantics": 5,
        "L6_misinterpretation": 2,
        "L7_policy_outside_model": 1,
    },
}

REQUIRED_COLUMNS = {
    "source_field",
    "source_semantics",
    "fhir_candidate",
    "current_decision",
    "information_loss_or_risk",
    "loss_modes",
    "needs_extension",
    "next_review",
}


def load_inventory(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing columns: {', '.join(sorted(missing))}")

        rows: list[dict[str, object]] = []
        seen: set[str] = set()
        for line_number, raw in enumerate(reader, start=2):
            field = raw["source_field"].strip()
            if not field:
                raise ValueError(f"line {line_number}: source_field is empty")
            if field in seen:
                raise ValueError(f"line {line_number}: duplicate source_field {field!r}")
            seen.add(field)

            modes = tuple(
                mode.strip() for mode in raw["loss_modes"].split(";") if mode.strip()
            )
            unknown = set(modes).difference(LOSS_MODES)
            if unknown:
                raise ValueError(
                    f"line {line_number}: unknown loss modes: {', '.join(sorted(unknown))}"
                )

            extension_text = raw["needs_extension"].strip().lower()
            if extension_text not in {"true", "false"}:
                raise ValueError(
                    f"line {line_number}: needs_extension must be true or false"
                )

            rows.append(
                {
                    "field": field,
                    "modes": modes,
                    "needs_extension": extension_text == "true",
                }
            )
    return rows


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    counts: Counter[str] = Counter()
    by_mode = {mode: [] for mode in LOSS_MODES}
    multi_label: list[str] = []
    clean: list[str] = []
    extensions: list[str] = []

    for row in rows:
        field = str(row["field"])
        modes = tuple(row["modes"])
        if len(modes) >= 2:
            multi_label.append(field)
        if not modes:
            clean.append(field)
        if row["needs_extension"]:
            extensions.append(field)
        for mode in modes:
            counts[mode] += 1
            by_mode[mode].append(field)

    return {
        "total": len(rows),
        "counts": dict(counts),
        "by_mode": by_mode,
        "multi_label": multi_label,
        "clean": clean,
        "extensions": extensions,
    }


def check_expected(summary: dict[str, object]) -> list[str]:
    errors: list[str] = []
    scalar_checks = {
        "total": summary["total"],
        "multi_label": len(summary["multi_label"]),
        "clean": len(summary["clean"]),
        "extensions": len(summary["extensions"]),
    }
    for key, actual in scalar_checks.items():
        if actual != EXPECTED[key]:
            errors.append(f"{key}: expected {EXPECTED[key]}, got {actual}")

    counts = summary["counts"]
    for mode, expected in EXPECTED["counts"].items():
        actual = counts.get(mode, 0)
        if actual != expected:
            errors.append(f"{mode}: expected {expected}, got {actual}")
    return errors


def print_summary(path: Path, summary: dict[str, object]) -> None:
    total = summary["total"]
    print(f"Input: {path}")
    print(f"Source fields: {total}")
    print("\nLoss modes (multi-label):")
    for mode, description in LOSS_MODES.items():
        fields = summary["by_mode"][mode]
        print(f"  {mode:25s} {len(fields):2d}/{total}  {description}")
        if fields:
            print(f"  {'':25s}       {', '.join(fields)}")
    print(f"\nRequires an extension: {len(summary['extensions'])}/{total}")
    print(f"No assigned loss mode: {len(summary['clean'])}/{total}")
    print(f"Two or more loss modes: {len(summary['multi_label'])}/{total}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the validated inventory no longer reproduces the P1 counts",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = summarize(load_inventory(args.input))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print_summary(args.input, summary)
    if args.check:
        errors = check_expected(summary)
        if errors:
            for error in errors:
                print(f"check failed: {error}", file=sys.stderr)
            return 1
        print("\nP1 mapping-loss counts reproduced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
