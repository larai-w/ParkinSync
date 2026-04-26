import boto3
import json

# Initialize Textract client
textract = boto3.client('textract')

def lambda_handler(event, context):
    """
    Main function to process PDF logs from S3 using Amazon Textract.
    Triggered automatically when a file is uploaded to 'incoming/' folder.
    """
    try:
        # Get the bucket and file name from the S3 event
        bucket = event['Records'][0]['s3']['bucket']['name']
        document = event['Records'][0]['s3']['object']['key']
        
        print(f"Detecting text in: {document}")

        # Call Amazon Textract to analyze the document
        response = textract.analyze_document(
            Document={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': document
                }
            },
            FeatureTypes=["FORMS"] # Important for structured logs
        )

# Add this line to see the actual extracted data in the logs
        print("Raw Data:", json.dumps(response, indent=2))
        
        print("Textract Analysis Successful.")
        
        return {
            'statusCode': 200,
            'body': json.dumps(f"Processed: {document}")
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        raise e
