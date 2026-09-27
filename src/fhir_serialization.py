"""Deterministic serialisations of a ParkinSync fact bundle.

The same facts can be handed to a language model in different shapes. Recent
work (arXiv 2604.21076) reports that the shape alone changes how well models
reconcile FHIR medication data, and arXiv 2609.13062 keeps a stable identifier
on every clinical event so each claim can be traced back to its source.

This module renders one fact bundle as canonical JSON, a Markdown table and a
chronological timeline. Every rendering keeps each fact's stable ID and every
numeric source value, and ``check_lossless`` verifies that. No model is called
here: the module only prepares inputs that a later, separately reviewed
experiment could compare.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Callable

from fhir_summary import NUMBER_PATTERN

STRATEGIES = ("json", "markdown_table", "timeline")


def _numeric_values(fact: dict[str, Any]) -> set[Decimal]:
    values: set[Decimal] = set()
    for source_value in fact.get("source", {}).get("values", []):
        value = source_value.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        values.add(Decimal(str(value)))
    return values


def _row(fact: dict[str, Any]) -> dict[str, str]:
    if fact["kind"] == "observation":
        what = f"{fact['label']} ({fact['code']})"
        amount = f"{fact['value']} {fact['unit']}"
    else:
        what = fact["medication"]
        amount = f"{fact['dose_value']} {fact['unit']}"
    return {
        "id": fact["id"],
        "kind": fact["kind"],
        "time": fact["effective_time"],
        "what": what,
        "status": fact["status"],
        "amount": amount,
        "source": f"{fact['source']['resource_type']}/{fact['source']['resource_id']}",
    }


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _to_json(facts: list[dict[str, Any]]) -> str:
    return json.dumps(facts, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _to_markdown_table(facts: list[dict[str, Any]]) -> str:
    columns = ("id", "kind", "time", "what", "status", "amount", "source")
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for fact in facts:
        row = _row(fact)
        lines.append("| " + " | ".join(_cell(row[c]) for c in columns) + " |")
    return "\n".join(lines) + "\n"


def _to_timeline(facts: list[dict[str, Any]]) -> str:
    rows = sorted((_row(f) for f in facts), key=lambda r: (r["time"], r["id"]))
    return "".join(
        f"- {r['time']} [{r['id']}] {r['kind']}: {r['what']}, "
        f"{r['status']}, {r['amount']} (source {r['source']})\n"
        for r in rows
    )


_RENDERERS: dict[str, Callable[[list[dict[str, Any]]], str]] = {
    "json": _to_json,
    "markdown_table": _to_markdown_table,
    "timeline": _to_timeline,
}


def serialize_facts(fact_bundle: dict[str, Any], strategy: str) -> str:
    """Render the bundle's facts in one of ``STRATEGIES``."""
    if strategy not in _RENDERERS:
        raise ValueError(f"unknown serialisation strategy: {strategy}")
    return _RENDERERS[strategy](list(fact_bundle.get("facts", [])))


def check_lossless(fact_bundle: dict[str, Any], text: str) -> dict[str, list[str]]:
    """Report fact IDs and numeric source values that a rendering dropped.

    Numeric values are checked per fact against the numbers present anywhere in
    the text, matching how summaries are checked in ``fhir_summary``.
    """
    numbers: set[Decimal] = set()
    for match in NUMBER_PATTERN.findall(text):
        numbers.add(Decimal(match))
    missing_ids: list[str] = []
    missing_values: list[str] = []
    for fact in fact_bundle.get("facts", []):
        if fact["id"] not in text:
            missing_ids.append(fact["id"])
        for value in sorted(_numeric_values(fact) - numbers):
            missing_values.append(f"{fact['id']}={value}")
    return {"missing_ids": missing_ids, "missing_values": missing_values}
