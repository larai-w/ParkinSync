#!/usr/bin/env python3
"""Generate or verify deterministic grounded-summary evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fhir_summary import render_summary_outputs  # noqa: E402


INPUT_PATH = ROOT / "fhir" / "generated" / "bundle-synthetic-transaction-bundle.json"
OUTPUT_DIR = ROOT / "fhir" / "summary" / "generated"


def check_outputs(expected: dict[str, str]) -> bool:
    actual_names = sorted(path.name for path in OUTPUT_DIR.glob("*.json"))
    if actual_names != sorted(expected):
        print("Grounded-summary output file set is stale or incomplete", file=sys.stderr)
        return False
    stale = [
        name for name, content in expected.items() if (OUTPUT_DIR / name).read_text() != content
    ]
    if stale:
        for name in stale:
            print(f"stale summary artifact: fhir/summary/generated/{name}", file=sys.stderr)
        return False
    print(f"Synthetic grounded-summary artifacts are reproducible ({len(expected)} artifacts).")
    return True


def write_outputs(outputs: dict[str, str]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for old_path in OUTPUT_DIR.glob("*.json"):
        if old_path.name not in outputs:
            old_path.unlink()
    for name, content in outputs.items():
        (OUTPUT_DIR / name).write_text(content, encoding="utf-8")
    print(f"Wrote {len(outputs)} grounded-summary artifacts to fhir/summary/generated/.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify tracked output without writing")
    args = parser.parse_args()
    try:
        bundle = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
        outputs = render_summary_outputs(bundle)
        if args.check:
            return 0 if check_outputs(outputs) else 1
        write_outputs(outputs)
        return 0
    except (json.JSONDecodeError, OSError, ValueError) as error:
        print(f"Grounded-summary generation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
