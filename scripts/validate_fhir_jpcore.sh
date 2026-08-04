#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VALIDATOR_JAR=${FHIR_VALIDATOR_JAR:-}
JP_CORE_PACKAGE=${JP_CORE_PACKAGE:-jpfhir.jp.core#1.2.0}
JP_CORE_PACKAGE_TGZ=${JP_CORE_PACKAGE_TGZ:-}
JP_TERMINOLOGY_PACKAGE_TGZ=${JP_TERMINOLOGY_PACKAGE_TGZ:-}

if [ -z "$VALIDATOR_JAR" ] || [ ! -f "$VALIDATOR_JAR" ]; then
  echo "FHIR_VALIDATOR_JAR must point to validator_cli.jar" >&2
  exit 2
fi
if ! command -v java >/dev/null 2>&1; then
  echo "Java 17 or newer is required to run HL7 Validator CLI" >&2
  exit 2
fi

BUNDLE="$ROOT/fhir/jpcore/generated/bundle-synthetic-weekly-jpcore-transaction-bundle.json"
IG_SOURCE=$JP_CORE_PACKAGE
if [ -n "$JP_CORE_PACKAGE_TGZ" ]; then
  if [ ! -f "$JP_CORE_PACKAGE_TGZ" ]; then
    echo "JP_CORE_PACKAGE_TGZ does not exist: $JP_CORE_PACKAGE_TGZ" >&2
    exit 2
  fi
  IG_SOURCE=$JP_CORE_PACKAGE_TGZ
  if [ -z "$JP_TERMINOLOGY_PACKAGE_TGZ" ] || [ ! -f "$JP_TERMINOLOGY_PACKAGE_TGZ" ]; then
    echo "JP_TERMINOLOGY_PACKAGE_TGZ must point to the verified dependency package" >&2
    exit 2
  fi
  set -- -ig "$JP_TERMINOLOGY_PACKAGE_TGZ" -ig "$IG_SOURCE"
else
  set -- -ig "$IG_SOURCE"
fi

# Package and FHIR release are pinned; terminology calls are disabled for deterministic CI.
java -jar "$FHIR_VALIDATOR_JAR" "$BUNDLE" \
  -version 4.0.1 \
  "$@" \
  -tx n/a
