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
from datetime import datetime
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


def _instant(text: str) -> datetime:
    """Parse an effective time as an absolute instant.

    Sorting the strings would put ``02:00+00:00`` before ``07:00+09:00`` although
    the second is nine hours earlier. A time without an offset cannot be placed
    on that line at all, so it is rejected rather than guessed.
    """
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError(f"effective_time has no UTC offset: {text}")
    return moment


def _to_timeline(facts: list[dict[str, Any]]) -> str:
    rows = sorted((_row(f) for f in facts), key=lambda r: (_instant(r["time"]), r["id"]))
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


def _records(text: str, fact_ids: list[str]) -> dict[str, str]:
    """Split a rendering into the part that belongs to each fact ID.

    A JSON rendering is split by its objects; the table and the timeline put one
    fact on one line. A number only counts for a fact when it is in that fact's
    own record, so another fact carrying the same number cannot hide a loss.
    """
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    records: dict[str, list[str]] = {}
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                records.setdefault(item["id"], []).append(json.dumps(item))
        return {key: "\n".join(parts) for key, parts in records.items()}
    for line in text.splitlines():
        for fact_id in fact_ids:
            if fact_id in line:
                records.setdefault(fact_id, []).append(line)
    return {key: "\n".join(parts) for key, parts in records.items()}


def check_lossless(fact_bundle: dict[str, Any], text: str) -> dict[str, list[str]]:
    """Report fact IDs and numeric source values that a rendering dropped.

    Each fact's numbers must appear in that fact's own record (its JSON object,
    or the lines that carry its ID). Checking against every number anywhere in
    the text would let two facts with the same dose cover for each other.
    """
    facts = list(fact_bundle.get("facts", []))
    records = _records(text, [fact["id"] for fact in facts])
    missing_ids: list[str] = []
    missing_values: list[str] = []
    for fact in facts:
        if fact["id"] not in text:
            missing_ids.append(fact["id"])
        record = records.get(fact["id"], "")
        numbers = {Decimal(match) for match in NUMBER_PATTERN.findall(record)}
        for value in sorted(_numeric_values(fact) - numbers):
            missing_values.append(f"{fact['id']}={value}")
    return {"missing_ids": missing_ids, "missing_values": missing_values}
