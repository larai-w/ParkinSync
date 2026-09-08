#!/usr/bin/env python3
"""Build the frozen, non-clinical daily label contract for P4 baselines."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from .run_30_day_synthetic_readiness import build_events
except ImportError:  # pragma: no cover - direct file execution
    from run_30_day_synthetic_readiness import build_events


def build_label_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in events:
        by_day[item["localDate"]].append(item)
    days = sorted(by_day)
    rows: list[dict[str, Any]] = []
    for index, day in enumerate(days[:-1]):
        next_day = days[index + 1]
        condition = next(item["payload"]["conditionNum"] for item in by_day[next_day] if item["eventType"] == "daily_condition_logged")
        weather = next(item["payload"]["weatherAvg"] for item in by_day[day] if item["eventType"] == "weather_observed")
        temperature = next(item["payload"]["temperatureAvg"] for item in by_day[day] if item["eventType"] == "indoor_temperature_observed")
        previous_condition = None
        if index:
            previous_day = days[index - 1]
            previous_condition = next(item["payload"]["conditionNum"] for item in by_day[previous_day] if item["eventType"] == "daily_condition_logged")
        rows.append(
            {
                "localDate": day,
                "forecastDate": next_day,
                "weatherAvg": weather,
                "indoorTemperatureAvg": temperature,
                "previousConditionNum": previous_condition,
                "label_high_support_next_day": int(condition >= 4),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = build_label_rows(build_events())
    result = {
        "protocol": "P4-synthetic-label-v1",
        "unit": "local day",
        "horizon": "next local day",
        "label": "conditionNum >= 4 on forecastDate",
        "featureColumns": ["weatherAvg", "indoorTemperatureAvg", "previousConditionNum"],
        "rows": rows,
        "positiveCount": sum(row["label_high_support_next_day"] for row in rows),
        "negativeCount": sum(1 - row["label_high_support_next_day"] for row in rows),
        "syntheticOnly": True,
        "note": "Contract fixture for transparent baseline tests; not a clinical outcome.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("unit", "horizon", "positiveCount", "negativeCount")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
