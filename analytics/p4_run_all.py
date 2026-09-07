#!/usr/bin/env python3
"""Run the complete synthetic P4 benchmark suite and emit one manifest.

Public release. Everything here runs on a deterministic synthetic fixture that
the code generates; no participant, household, or production record is read.
Only the Python standard library is required.

    python3 analytics/p4_run_all.py --output-dir <dir>

The manuscript-linting steps used while writing the paper are intentionally not
part of this release: they read a manuscript file that is not published, so they
would fail for anyone else. The benchmark itself is complete without them.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(command: list[str], cwd: Path) -> dict[str, object]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return {"command": command, "returnCode": completed.returncode, "stdout": completed.stdout.strip(), "stderr": completed.stderr.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    labels = args.output_dir / "labels.json"
    results: list[dict[str, object]] = []
    commands = [
        [sys.executable, "analytics/p4_reproducibility_preflight.py", "--output", str(args.output_dir / "preflight.json")],
        [sys.executable, "analytics/p4_synthetic_labels.py", "--output", str(labels)],
        [sys.executable, "analytics/p4_missingness_sweep.py", "--output", str(args.output_dir / "missingness-sweep.json")],
        [sys.executable, "analytics/p4_baseline_compare.py", "--labels", str(labels), "--output", str(args.output_dir / "baselines.json")],
        [sys.executable, "analytics/p4_negative_control.py", "--labels", str(labels), "--output", str(args.output_dir / "negative.json")],
        [sys.executable, "analytics/p4_source_conflation.py", "--output", str(args.output_dir / "source-conflation.json")],
        [sys.executable, "analytics/p4_subgroup_metrics.py", "--labels", str(labels), "--output", str(args.output_dir / "subgroups.json")],
        [sys.executable, "-m", "unittest", "discover", "-s", "analytics", "-p", "test_p4_*.py"],
    ]
    for command in commands:
        result = run(command, root)
        results.append(result)
        if result["returnCode"] != 0:
            manifest = {"protocol": "P4-full-suite-v1", "status": "FAIL", "steps": results, "syntheticOnly": True}
            (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(manifest, ensure_ascii=False))
            return 1
    manifest = {"protocol": "P4-full-suite-v1", "status": "PASS", "steps": results, "artifacts": sorted(path.name for path in args.output_dir.iterdir()), "syntheticOnly": True, "note": "End-to-end synthetic suite; not a clinical or deployment-performance claim."}
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"protocol": manifest["protocol"], "status": manifest["status"], "stepCount": len(results)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
