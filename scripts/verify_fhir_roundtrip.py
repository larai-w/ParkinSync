#!/usr/bin/env python3
"""Verify the tracked synthetic weekly Bundle against an ephemeral FHIR server."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fhir_roundtrip import RoundTripError, fetch_capability, verify_roundtrip  # noqa: E402


DEFAULT_BUNDLE = (
    ROOT
    / "fhir"
    / "weekly"
    / "generated"
    / "bundle-synthetic-weekly-transaction-bundle.json"
)


def wait_for_server(base_url: str, wait_seconds: int) -> None:
    deadline = time.monotonic() + wait_seconds
    last_error = "server not ready"
    while time.monotonic() < deadline:
        try:
            fetch_capability(base_url, timeout=5.0)
            return
        except RoundTripError as error:
            last_error = str(error)
            time.sleep(2)
    raise RoundTripError(f"FHIR server did not become ready: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="ephemeral FHIR R4 base URL")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=300)
    args = parser.parse_args()
    try:
        wait_for_server(args.base_url, args.wait_seconds)
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        report = verify_roundtrip(args.base_url, bundle, timeout=60.0)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(
            f"FHIR round trip passed: {report['checks']['semantic_matches']} "
            f"semantic matches on {report['server']['product']} {report['server']['version']}"
        )
        return 0
    except (OSError, json.JSONDecodeError, RoundTripError) as error:
        print(f"FHIR round trip failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
