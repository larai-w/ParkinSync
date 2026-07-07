# Environment variables for local unit testing
export AWS_ACCESS_KEY_ID=testing
export AWS_SECRET_ACCESS_KEY=testing
export AWS_SECURITY_TOKEN=testing
export AWS_SESSION_TOKEN=testing
export AWS_DEFAULT_REGION=us-east-1
export PYTHONPATH=src

# Run the unit tests
python3 -m unittest tests.test_lambda_function