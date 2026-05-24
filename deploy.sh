# 1. Install dependencies into a local package directory
pip install --target ./package pandas requests google-api-python-client

# 2. Bundle core dependencies into a reusable staging ZIP archive
cd package
zip -r ../deployment_package.zip .
cd ..

# 3. Deploy and update the Clinical Data Handler Function
zip -g deployment_package.zip src/lambda_function.py
aws lambda update-function-code \
  --function-name ParkinSync_OCR_Handler \
  --zip-file fileb://deployment_package.zip
# 4. Deploy and update the Scheduled IoT Telemetry Logger Function
zip -d deployment_package.zip src/lambda_function.py # Remove previous handler
zip -g deployment_package.zip src/indoor_temp_logger.py
aws lambda update-function-code \
  --function-name ParkinSync_IndoorTemp_Logger \
  --zip-file fileb://deployment_package.zip
