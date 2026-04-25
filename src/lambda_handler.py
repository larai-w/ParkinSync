import boto3
import json

def lambda_handler(event, context):
    textract = boto3.client('textract')
    
    # Get file info from S3 event
    bucket = event['Records'][0]['s3']['bucket']['name']
    document = event['Records'][0]['s3']['object']['key']
    
    response = textract.analyze_document(
        Document={'S3Object': {
            'Bucket': bucket,
            'Name': document
        }},
        FeatureTypes=["FORMS"]
    )
    
    blocks = response['Blocks']
    
    return {
        'statusCode': 200,
        'body': json.dumps('Textract processing complete')
    }
