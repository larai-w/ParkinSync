#!/bin/bash
# ParkinSync deployment script.
#
# Preferred path (Infrastructure as Code):
#   sam build && sam deploy --guided     # first time
#   ./deploy.sh sam                      # subsequent deploys
#
# Fallback path (code-only update of an existing Lambda function):
#   ./deploy.sh zip
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-sam}"
FUNCTION_NAME="${FUNCTION_NAME:-ParkinSyncProcessor}"
STACK_NAME="${STACK_NAME:-parkinsync}"

case "$MODE" in
  sam)
    command -v sam >/dev/null || { echo "AWS SAM CLI not found. Install: brew install aws-sam-cli"; exit 1; }
    sam build
    sam deploy --stack-name "$STACK_NAME" --capabilities CAPABILITY_IAM --resolve-s3 --no-confirm-changeset
    ;;
  zip)
    BUILD_DIR=build
    ZIP_FILE=parkinsync_lambda.zip
    rm -rf "$BUILD_DIR" "$ZIP_FILE"
    mkdir -p "$BUILD_DIR"
    pip install --quiet --target "$BUILD_DIR" -r src/requirements.txt
    cp src/lambda_function.py "$BUILD_DIR/"
    (cd "$BUILD_DIR" && zip -qr "../$ZIP_FILE" .)
    aws lambda update-function-code --function-name "$FUNCTION_NAME" --zip-file "fileb://$ZIP_FILE"
    echo "[SUCCESS] Updated function code: $FUNCTION_NAME"
    ;;
  *)
    echo "Usage: ./deploy.sh [sam|zip]"; exit 1
    ;;
esac
