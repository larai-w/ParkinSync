"""Audit ParkinSync's schema and demonstrate EDA with deterministic synthetic data."""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from master_ledger_contract import validate_columns

CSV_PATH = ROOT / "analytics" / "synthetic_sample_data_v1.3.csv"
SCHEMA_PATH = ROOT / "design" / "master_schema_template.csv"


def expected_columns() -> list[str]:
    with SCHEMA_PATH.open(newline="", encoding="utf-8") as source:
        columns = next(csv.reader(source))
    validate_columns(columns)
    return columns


def load_fixture() -> tuple[list[str], list[dict[str, str]]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        return reader.fieldnames or [], list(reader)


def verify_synthetic_boundary(columns: list[str], rows: list[dict[str, str]]) -> None:
    if columns != expected_columns():
        raise ValueError("fixture columns do not exactly match the public master schema")
    if not rows:
        raise ValueError("fixture has no rows")

    required_markers = {
        "Daily_Notes": "SYNTHETIC_SCENARIO_",
        "Weather_Summary": "SYNTHETIC_WEATHER_",
        "Switchbot_Summary": "SYNTHETIC_INDOOR_",
        "File_Name": "synthetic/",
    }
    for column, prefix in required_markers.items():
        if not all(row[column].startswith(prefix) for row in rows):
            raise ValueError(f"{column} contains a row without the required {prefix!r} marker")


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right):
        raise ValueError("correlation requires paired values")
    if len(left) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else None


def numeric_field(rows: list[dict[str, str]], field: str) -> tuple[list[float | None], dict[str, int]]:
    values: list[float | None] = []
    counts = {"observed": 0, "missing": 0, "invalid": 0}
    for row in rows:
        raw = row.get(field)
        if raw is None or not raw.strip():
            values.append(None)
            counts["missing"] += 1
            continue
        try:
            value = float(raw)
            if not math.isfinite(value):
                raise ValueError("nonfinite")
        except ValueError:
            values.append(None)
            counts["invalid"] += 1
        else:
            values.append(value)
            counts["observed"] += 1
    return values, counts


def mean_display(values: list[float | None]) -> str:
    observed = [value for value in values if value is not None]
    return f"{mean(observed):.2f} C" if observed else "undefined (no observed values)"


def verify_and_analyze_pipeline() -> int:
    try:
        columns, rows = load_fixture()
        verify_synthetic_boundary(columns, rows)
    except (csv.Error, KeyError, OSError, ValueError) as error:
        print(f"[ERROR] Synthetic fixture audit failed: {error}", file=sys.stderr)
        return 1

    print("==================================================")
    print(" ParkinSync Synthetic Fixture & Schema Audit")
    print("==================================================")
    print(f"[INFO] Data source: {CSV_PATH.relative_to(ROOT)}")
    print("[INFO] Classification: SYNTHETIC; not participant data or clinical evidence")
    print(f"[INFO] Rows: {len(rows)}")
    print(f"[STATUS] Schema audit: PASS ({len(columns)} exact columns)")

    fields = {}
    invalid = 0
    for field in ("Switchbot_Avg", "Weather_Avg", "Condition_Num", "Bowel"):
        values, counts = numeric_field(rows, field)
        fields[field] = values
        invalid += counts["invalid"]
        print(f"[MISSINGNESS] {field}: observed={counts['observed']} "
              f"missing={counts['missing']} invalid={counts['invalid']}")
        print(f"[COVERAGE] {field}: {counts['observed']}/{len(rows)} input rows")

    print("[LIMITATIONS] Invented, non-independent synthetic rows; descriptive code demonstration only; "
          "no confidence intervals or inferential p-values; no multiple testing correction. "
          "Coverage denominators are input rows, not expected calendar days or participants.")
    print("[BOUNDARY] These values demonstrate code paths only; do not infer health relationships.")
    if invalid:
        print("[ERROR] Numeric audit failed: invalid/nonfinite values; statistics not computed.", file=sys.stderr)
        return 1

    weekend_count = sum(row["Day"] in {"Sat", "Sun"} for row in rows)
    print("\nSynthetic EDA demonstration")
    print(f"[THERMAL] Mean indoor field: {mean_display(fields['Switchbot_Avg'])}")
    print(f"[THERMAL] Mean outdoor field: {mean_display(fields['Weather_Avg'])}")
    print(f"[COVERAGE] Weekday rows: {len(rows) - weekend_count}")
    print(f"[COVERAGE] Weekend rows: {weekend_count}")
    pairs = [(condition, indoor) for condition, indoor in zip(fields['Condition_Num'], fields['Switchbot_Avg'])
             if condition is not None and indoor is not None]
    print(f"[COVERAGE] Correlation pairs: {len(pairs)}/{len(rows)} input rows")
    result = correlation([pair[0] for pair in pairs], [pair[1] for pair in pairs])
    coefficient = f"{result:.4f}" if result is not None else "undefined (fewer than two pairs or constant field)"
    print(f"[CORR] Invented condition score vs. indoor field: {coefficient}")
    bowel = [value for value in fields['Bowel'] if value is not None]
    total = f"{sum(bowel):g}" if bowel else "undefined (no observed values)"
    print(f"[COUNT] Invented bowel-event field observed subtotal: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(verify_and_analyze_pipeline())
