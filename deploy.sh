#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

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

  "$PYTHON_BIN" -m pip install --target "$build_dir" "${LAMBDA_DEPS[@]}"
  (
    cd "$build_dir"
    zip -qr "$output_zip" .
  )
}

# OCR Lambda: production handler is configured as lambda_function.lambda_handler,
# so the source file is copied to that module name at the ZIP root.
OCR_BUILD="$BUILD_ROOT/ocr"
OCR_ZIP="$BUILD_ROOT/parkinsync-ocr-handler.zip"
mkdir -p "$OCR_BUILD"
cp "$ROOT_DIR/src/ParkinSync_OCR_Handler.py" "$OCR_BUILD/lambda_function.py"
build_zip "$OCR_BUILD" "$OCR_ZIP"

aws lambda update-function-code \
  --region "$AWS_REGION" \
  --function-name ParkinSync_OCR_Handler \
  --zip-file "fileb://$OCR_ZIP"

# Indoor telemetry Lambda also uses lambda_function.lambda_handler in AWS.
IOT_BUILD="$BUILD_ROOT/iot"
IOT_ZIP="$BUILD_ROOT/parkinsync-indoor-temp-logger.zip"
mkdir -p "$IOT_BUILD"
cp "$ROOT_DIR/src/indoor_temp_logger.py" "$IOT_BUILD/lambda_function.py"
build_zip "$IOT_BUILD" "$IOT_ZIP"

aws lambda update-function-code \
  --region "$AWS_REGION" \
  --function-name ParkinSync_IndoorTemp_Logger \
  --zip-file "fileb://$IOT_ZIP"
