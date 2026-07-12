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

MODE="${1:-zip}"
# Production function name in us-east-1 (dependencies provided via Lambda Layers)
FUNCTION_NAME="${FUNCTION_NAME:-ParkinSync_OCR_Handler}"
AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${STACK_NAME:-parkinsync}"

case "$MODE" in
  sam)
    command -v sam >/dev/null || { echo "AWS SAM CLI not found. Install: brew install aws-sam-cli"; exit 1; }
    sam build
    sam deploy --stack-name "$STACK_NAME" --capabilities CAPABILITY_IAM --resolve-s3 --no-confirm-changeset
    ;;
  zip)
    # Dependencies are provided by Lambda Layers — zip only the function code.
    ZIP_FILE=/tmp/parkinsync_lambda.zip
    rm -f "$ZIP_FILE"
    (cd src && zip "$ZIP_FILE" lambda_function.py)
    aws lambda update-function-code \
      --function-name "$FUNCTION_NAME" \
      --zip-file "fileb://$ZIP_FILE" \
      --region "$AWS_REGION"
    aws lambda wait function-updated \
      --function-name "$FUNCTION_NAME" \
      --region "$AWS_REGION"
    echo "[SUCCESS] Deployed $FUNCTION_NAME to $AWS_REGION"
    ;;
  *)
    echo "Usage: ./deploy.sh [sam|zip]"; exit 1
    ;;
esac
