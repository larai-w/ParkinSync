#!/usr/bin/env python3
"""Generate or verify ParkinSync's deterministic synthetic FHIR R4 artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fhir_export import load_record, render_outputs  # noqa: E402


INPUT_PATH = ROOT / "fhir" / "synthetic_normalized_record.json"
OUTPUT_DIR = ROOT / "fhir" / "generated"


def check_outputs(expected: dict[str, str]) -> bool:
    actual_names = sorted(path.name for path in OUTPUT_DIR.glob("*.json"))
    expected_names = sorted(expected)
    if actual_names != expected_names:
        print("FHIR output file set is stale or incomplete", file=sys.stderr)
        return False
    stale = [name for name, content in expected.items() if (OUTPUT_DIR / name).read_text() != content]
    if stale:
        for name in stale:
            print(f"stale FHIR artifact: fhir/generated/{name}", file=sys.stderr)
        return False
    print(f"Synthetic FHIR R4 artifacts are reproducible ({len(expected) - 1} artifacts).")
    return True


def write_outputs(outputs: dict[str, str]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for old_path in OUTPUT_DIR.glob("*.json"):
        if old_path.name not in outputs:
            old_path.unlink()
    for name, content in outputs.items():
        (OUTPUT_DIR / name).write_text(content, encoding="utf-8")
    print(f"Wrote {len(outputs) - 1} synthetic FHIR R4 artifacts to fhir/generated/.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify tracked output without writing")
    args = parser.parse_args()
    try:
        outputs = render_outputs(load_record(INPUT_PATH))
        if args.check:
            return 0 if check_outputs(outputs) else 1
        write_outputs(outputs)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"FHIR export failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
