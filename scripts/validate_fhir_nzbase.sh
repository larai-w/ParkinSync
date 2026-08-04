#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VALIDATOR_JAR=${FHIR_VALIDATOR_JAR:-}
NZ_BASE_PACKAGE=${NZ_BASE_PACKAGE:-fhir.org.nz.ig.base#3.1.0}

if [ -z "$VALIDATOR_JAR" ] || [ ! -f "$VALIDATOR_JAR" ]; then
  echo "FHIR_VALIDATOR_JAR must point to validator_cli.jar" >&2
  exit 2
fi
if ! command -v java >/dev/null 2>&1; then
  echo "Java 17 or newer is required to run HL7 Validator CLI" >&2
  exit 2
fi

BUNDLE="$ROOT/fhir/nzbase/generated/bundle-synthetic-weekly-nzbase-transaction-bundle.json"

# The published package is pinned; terminology-server calls remain disabled for deterministic CI.
java -jar "$VALIDATOR_JAR" "$BUNDLE" \
  -version 4.0.1 \
  -ig "$NZ_BASE_PACKAGE" \
  -tx n/a
