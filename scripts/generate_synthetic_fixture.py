#!/usr/bin/env python3
"""Generate ParkinSync's deterministic, schema-only public analytics fixture."""

from __future__ import annotations

import argparse
import csv
import io
import json
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "design" / "master_schema_template.csv"
FIXTURE_PATH = ROOT / "analytics" / "synthetic_sample_data_v1.3.csv"
MANIFEST_PATH = ROOT / "analytics" / "synthetic_fixture_manifest.json"
ROW_COUNT = 21
START_DATE = date(2035, 1, 1)


def read_schema() -> list[str]:
    with SCHEMA_PATH.open(newline="", encoding="utf-8") as source:
        return next(csv.reader(source))


def build_rows() -> list[dict[str, object]]:
    conditions = ("A", "B", "C", "B")
    weather_conditions = ("synthetic-clear", "synthetic-cloudy", "synthetic-rain")
    rows: list[dict[str, object]] = []

    for index in range(ROW_COUNT):
        day = START_DATE + timedelta(days=index)
        weather_avg = 7.5 + ((index * 7) % 13) * 0.5
        indoor_avg = 19.0 + ((index * 5 + 2) % 9) * 0.4
        scenario = index + 1
        rows.append(
            {
                "Processed": "TRUE",
                "Date": day.strftime("%Y/%m/%d"),
                "Day": day.strftime("%a"),
                "Morning": f"07:{(index * 5) % 30:02d}",
                "Lunch": f"12:{(index * 3) % 20:02d}",
                "Evening": f"18:{(index * 4) % 24:02d}",
                "Bedtime": f"21:{(index * 2) % 20:02d}",
                "Bedtime_2": "",
                "Bowel": 0 if index % 4 == 1 else 1,
                "Movi": 1 if index % 7 == 2 else 0,
                "Emerg_Call": 0,
                "Ryusei_Eme": 0,
                "Condition_C": conditions[index % len(conditions)],
                "Condition_Num": 1 + ((index * 2 + 1) % 5),
                "Daily_Notes": f"SYNTHETIC_SCENARIO_{scenario:03d}",
                "Weather_Summary": f"SYNTHETIC_WEATHER_{scenario:03d}",
                "Weather_Avg": f"{weather_avg:.1f}",
                "Weather_Min": f"{weather_avg - 2.5:.1f}",
                "Weather_Max": f"{weather_avg + 3.0:.1f}",
                "Weather_Condition": weather_conditions[index % len(weather_conditions)],
                "Switchbot_Summary": f"SYNTHETIC_INDOOR_{scenario:03d}",
                "Switchbot_Avg": f"{indoor_avg:.1f}",
                "Switchbot_Min": f"{indoor_avg - 0.8:.1f}",
                "Switchbot_Max": f"{indoor_avg + 0.9:.1f}",
                "File_Name": f"synthetic/scenario_{scenario:03d}.pdf",
            }
        )

    return rows


def render_fixture() -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=read_schema(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(build_rows())
    return output.getvalue()


def render_manifest() -> str:
    end_date = START_DATE + timedelta(days=ROW_COUNT - 1)
    manifest = {
        "classification": "synthetic",
        "date_range": {
            "end": end_date.isoformat(),
            "start": START_DATE.isoformat(),
        },
        "fixture": FIXTURE_PATH.name,
        "generator": "scripts/generate_synthetic_fixture.py",
        "intended_use": [
            "schema validation",
            "software tests",
            "exploratory-analysis demonstration",
        ],
        "prohibited_use": [
            "clinical inference",
            "performance claims",
            "treatment or diagnostic decisions",
        ],
        "provenance": (
            "Generated solely from the public schema and invented scenarios; "
            "no participant, household, or care-setting records were used."
        ),
        "record_count": ROW_COUNT,
    }
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def check_current() -> bool:
    expected = {
        FIXTURE_PATH: render_fixture(),
        MANIFEST_PATH: render_manifest(),
    }
    stale = [path for path, content in expected.items() if not path.exists() or path.read_text() != content]
    if stale:
        for path in stale:
            print(f"stale or missing generated artifact: {path.relative_to(ROOT)}")
        return False
    print("Synthetic fixture and manifest are reproducible.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify tracked output without writing")
    args = parser.parse_args()

    if args.check:
        return 0 if check_current() else 1

    FIXTURE_PATH.write_text(render_fixture(), encoding="utf-8")
    MANIFEST_PATH.write_text(render_manifest(), encoding="utf-8")
    print(f"Wrote {ROW_COUNT} synthetic rows to {FIXTURE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
