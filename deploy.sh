#!/usr/bin/env bash
set -euo pipefail

# HEALTH-SAFETY GUARDRAIL (Issue #26) - do not remove without reading the doc.
# As of 2026-07-28, the deployed OCR Lambda is NOT repository `main`: it is
# byte-identical to `feature/fable5-mvp-hardening` and has hardening (idempotent S3
# processing, OCR failure quarantine/notification, filename date recovery, broader
# date parsing) that `main` lacks. Running this script from `main` as-is would
# OVERWRITE the hardened production code with the simpler `main` code — a regression.
# Reconcile `main` with production first (port the hardened capabilities via PRs),
# then remove this guardrail. Details + rollback evidence:
#   docs/PRODUCTION_LAMBDA_RECONCILIATION.md
DEPLOY_TARGET="${DEPLOY_TARGET:-all}"
case "$DEPLOY_TARGET" in
  all|ocr|iot) ;;
  *)
    echo "DEPLOY_TARGET must be one of: all, ocr, iot" >&2
    exit 2
    ;;
esac

# An IoT-only release cannot overwrite the OCR Lambda, so it is safe to pass this
# guard. OCR and all-component releases remain blocked until the production source
# of truth is explicitly reconciled.
if [ "$DEPLOY_TARGET" != "iot" ] && [ "${ALLOW_UNRECONCILED_DEPLOY:-}" != "1" ]; then
  echo "Refusing to deploy: main is not reconciled with production (Issue #26)." >&2
  echo "See docs/PRODUCTION_LAMBDA_RECONCILIATION.md. Override with ALLOW_UNRECONCILED_DEPLOY=1." >&2
  echo "For the indoor telemetry Lambda only, use DEPLOY_TARGET=iot." >&2
  exit 1
fi

AWS_REGION="${AWS_REGION:-us-east-1}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LAMBDA_PLATFORM="${LAMBDA_PLATFORM:-manylinux2014_x86_64}"
LAMBDA_PYTHON_VERSION="${LAMBDA_PYTHON_VERSION:-3.12}"
DRY_RUN="${DRY_RUN:-0}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_ROOT="$(mktemp -d)"
trap 'rm -rf "$BUILD_ROOT"' EXIT

LAMBDA_DEPS=(
  requests
  google-api-python-client
  google-auth
)

build_zip() {
  local build_dir="$1"
  local output_zip="$2"

  # Build for the Lambda Linux runtime even when this script runs on macOS.
  # Binary-only mode fails closed instead of compiling host-specific extensions.
  "$PYTHON_BIN" -m pip install \
    --platform "$LAMBDA_PLATFORM" \
    --implementation cp \
    --python-version "$LAMBDA_PYTHON_VERSION" \
    --only-binary=:all: \
    --target "$build_dir" \
    "${LAMBDA_DEPS[@]}"
  (
    cd "$build_dir"
    zip -qr "$output_zip" .
  )
  zip -T "$output_zip" >/dev/null
}

deploy_function_code() {
  local function_name="$1"
  local zip_path="$2"

  if [ "$DRY_RUN" = "1" ]; then
    echo "DRY_RUN: built Linux package for $function_name ($(du -h "$zip_path" | cut -f1))"
    return
  fi

  aws lambda update-function-code \
    --region "$AWS_REGION" \
    --function-name "$function_name" \
    --zip-file "fileb://$zip_path"
}

if [ "$DEPLOY_TARGET" = "all" ] || [ "$DEPLOY_TARGET" = "ocr" ]; then
  # OCR Lambda: production handler is configured as lambda_function.lambda_handler,
  # so the source file is copied to that module name at the ZIP root.
  OCR_BUILD="$BUILD_ROOT/ocr"
  OCR_ZIP="$BUILD_ROOT/parkinsync-ocr-handler.zip"
  mkdir -p "$OCR_BUILD"
  cp "$ROOT_DIR/src/ParkinSync_OCR_Handler.py" "$OCR_BUILD/lambda_function.py"
  build_zip "$OCR_BUILD" "$OCR_ZIP"

  deploy_function_code "ParkinSync_OCR_Handler" "$OCR_ZIP"
fi

if [ "$DEPLOY_TARGET" = "all" ] || [ "$DEPLOY_TARGET" = "iot" ]; then
  # Indoor telemetry Lambda also uses lambda_function.lambda_handler in AWS.
  IOT_BUILD="$BUILD_ROOT/iot"
  IOT_ZIP="$BUILD_ROOT/parkinsync-indoor-temp-logger.zip"
  mkdir -p "$IOT_BUILD"
  cp "$ROOT_DIR/src/indoor_temp_logger.py" "$IOT_BUILD/lambda_function.py"
  build_zip "$IOT_BUILD" "$IOT_ZIP"

  deploy_function_code "ParkinSync_IndoorTemp_Logger" "$IOT_ZIP"
fi
