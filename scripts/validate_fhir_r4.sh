#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VALIDATOR_JAR=${FHIR_VALIDATOR_JAR:-}

if [ -z "$VALIDATOR_JAR" ] || [ ! -f "$VALIDATOR_JAR" ]; then
  echo "FHIR_VALIDATOR_JAR must point to validator_cli.jar" >&2
  exit 2
fi
if ! command -v java >/dev/null 2>&1; then
  echo "Java 17 or newer is required to run HL7 Validator CLI" >&2
  exit 2
fi

FILES=$(python3 -c '
import json
from pathlib import Path
root = Path("'"$ROOT"'")
manifest = json.loads((root / "fhir/generated/manifest.json").read_text())
names = [*manifest["resource_files"], manifest["bundle_file"]]
files = [str(root / "fhir/generated" / name) for name in names]
weekly_manifest = json.loads((root / "fhir/weekly/generated/manifest.json").read_text())
files.append(str(root / "fhir/weekly/generated" / weekly_manifest["bundle_file"]))
print(" ".join(files))
')

# Generated artifact names are controlled by the manifest and contain no whitespace.
# Terminology-server validation is intentionally disabled for deterministic CI.
# shellcheck disable=SC2086
java -jar "$VALIDATOR_JAR" $FILES -version 4.0.1 -tx n/a
