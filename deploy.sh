#!/usr/bin/env bash
set -euo pipefail

# HEALTH-SAFETY GUARDRAIL (Issue #26) - do not remove without reading the doc.
# The current source has been behaviorally reconciled and verified by tests, but
# the owner should explicitly approve guardrail removal after reviewing the
# evidence. Details + rollback evidence:
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
VENDOR_DEPS="${VENDOR_DEPS:-0}"
DRY_RUN="${DRY_RUN:-0}"
LAMBDA_ALIAS="${LAMBDA_ALIAS:-prod}"
RELEASE_DESCRIPTION="${RELEASE_DESCRIPTION:-ParkinSync release via deploy.sh}"

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

  # Production functions use compatible Lambda Layers, so source-only is the
  # default. Opt-in vendoring still targets Linux and fails closed if a binary
  # wheel is unavailable; it must not compile host-specific extensions.
  if [ "$VENDOR_DEPS" = "1" ]; then
    "$PYTHON_BIN" -m pip install \
      --platform "$LAMBDA_PLATFORM" \
      --implementation cp \
      --python-version "$LAMBDA_PYTHON_VERSION" \
      --only-binary=:all: \
      --target "$build_dir" \
      "${LAMBDA_DEPS[@]}"
  fi
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
    echo "DRY_RUN: would publish $function_name and move alias $LAMBDA_ALIAS ($(du -h "$zip_path" | cut -f1), vendor_deps=$VENDOR_DEPS)"
    return
  fi

  local version
  version="$(aws lambda update-function-code \
    --region "$AWS_REGION" \
    --function-name "$function_name" \
    --zip-file "fileb://$zip_path" \
    --publish \
    --description "$RELEASE_DESCRIPTION" \
    --query 'Version' \
    --output text)"

  if [ -z "$version" ] || [ "$version" = "None" ] || [ "$version" = "\$LATEST" ]; then
    echo "Failed to obtain an immutable published version for $function_name" >&2
    exit 1
  fi

  if aws lambda get-alias \
    --region "$AWS_REGION" \
    --function-name "$function_name" \
    --name "$LAMBDA_ALIAS" \
    >/dev/null 2>&1; then
    aws lambda update-alias \
      --region "$AWS_REGION" \
      --function-name "$function_name" \
      --name "$LAMBDA_ALIAS" \
      --function-version "$version" \
      --description "$RELEASE_DESCRIPTION" \
      >/dev/null
  else
    aws lambda create-alias \
      --region "$AWS_REGION" \
      --function-name "$function_name" \
      --name "$LAMBDA_ALIAS" \
      --function-version "$version" \
      --description "$RELEASE_DESCRIPTION" \
      >/dev/null
  fi

  echo "Published $function_name version $version and moved alias $LAMBDA_ALIAS"
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
