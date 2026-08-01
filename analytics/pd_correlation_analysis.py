"""Audit ParkinSync's schema and demonstrate EDA with deterministic synthetic data."""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "analytics" / "synthetic_sample_data_v1.3.csv"
SCHEMA_PATH = ROOT / "design" / "master_schema_template.csv"


def expected_columns() -> list[str]:
    with SCHEMA_PATH.open(newline="", encoding="utf-8") as source:
        return next(csv.reader(source))


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


def correlation(left: list[float], right: list[float]) -> float:
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else float("nan")


def verify_and_analyze_pipeline() -> int:
    try:
        columns, rows = load_fixture()
        verify_synthetic_boundary(columns, rows)
        indoor = [float(row["Switchbot_Avg"]) for row in rows]
        outdoor = [float(row["Weather_Avg"]) for row in rows]
        condition = [float(row["Condition_Num"]) for row in rows]
        bowel = [float(row["Bowel"]) for row in rows]
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

    weekend_count = sum(row["Day"] in {"Sat", "Sun"} for row in rows)

    print("\nSynthetic EDA demonstration")
    print(f"[THERMAL] Mean indoor field: {mean(indoor):.2f} C")
    print(f"[THERMAL] Mean outdoor field: {mean(outdoor):.2f} C")
    print(f"[COVERAGE] Weekday rows: {len(rows) - weekend_count}")
    print(f"[COVERAGE] Weekend rows: {weekend_count}")
    print(f"[CORR] Invented condition score vs. indoor field: {correlation(condition, indoor):.4f}")
    print(f"[COUNT] Invented bowel-event field total: {int(sum(bowel))}")
    print("[BOUNDARY] These values demonstrate code paths only; do not infer health relationships.")
    return 0


if __name__ == "__main__":
    raise SystemExit(verify_and_analyze_pipeline())
