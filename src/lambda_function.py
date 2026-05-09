import boto3
import json
import requests
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURATION ---
# Target coordinates for weather data (Hyogo, Japan)
LAT = "35.38"
LON = "134.67"
# Google Spreadsheet ID for data logging
SPREADSHEET_ID = "1aHdVYePaTQQ59feBWtPXBYPpsaMBO2KMcuXhwV3AFBE"
# AWS Secrets Manager ID for storing API keys and credentials
SECRET_ID = "ParkinSync/Production/GoogleCredentials"

def get_historical_weather(date_str, api_key):
    """
    Parses OCR date (e.g., 'April 20') and fetches historical weather from Visual Crossing.
    Returns a string containing temperature and weather conditions.
    """
    try:
        month_map = {"April": "04", "May": "05"}
        parts = date_str.split()
        if len(parts) >= 2:
            month = month_map.get(parts[0], "04")
            day = parts[1].zfill(2)
            # Use 2026 as the standard year for the clinical trial context
            formatted_date = f"2026-{month}-{day}"
            
            url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LAT},{LON}/{formatted_date}?key={api_key}&unitGroup=metric&include=days"
            response = requests.get(url)
            data = response.json()
            
            day_info = data['days'][0]
            return f"{day_info['temp']}C, {day_info['conditions']} (Hist)"
    except Exception as e:
        print(f"Weather Fetch Error: {e}")
    return "Weather N/A"

def lambda_handler(event, context):
    """
    Main entry point for AWS Lambda.
    Triggered by S3 upload, processes OCR via Textract, and saves to Google Sheets.
    """
    # CRITICAL: Initialize AWS clients INSIDE the handler for successful unit testing (Mocking).
    # This prevents the code from attempting to connect to real AWS services during import.
    textract = boto3.client('textract')
    secrets_client = boto3.client('secretsmanager')
    
    try:
        # 1. Capture S3 Event Details
        bucket = event['Records'][0]['s3']['bucket']['name']
        document = event['Records'][0]['s3']['object']['key']

        # 2. Retrieve Credentials from AWS Secrets Manager
        secret_response = secrets_client.get_secret_value(SecretId=SECRET_ID)
        secrets = json.loads(secret_response['SecretString'])
        google_creds = secrets
        vc_key = secrets.get('VISUAL_CROSSING_KEY')

        # 3. Analyze Document with Amazon Textract (TABLES feature)
        response = textract.analyze_document(
            Document={'S3Object': {'Bucket': bucket, 'Name': document}},
            FeatureTypes=["TABLES"]
        )

        blocks = response['Blocks']
        tables = [b for b in blocks if b['BlockType'] == 'TABLE']
        if not tables:
            return {'statusCode': 404, 'body': 'No table detected in document'}

        # Map Textract cells into a row/column dictionary
        rows = {}
        for rel in tables[0].get('Relationships', []):
            if rel['Type'] == 'CHILD':
                for c_id in rel['Ids']:
                    cell = next(b for b in blocks if b['Id'] == c_id)
                    if cell['BlockType'] == 'CELL':
                        r, c = cell['RowIndex'], cell['ColumnIndex']
                        if r not in rows: rows[r] = {}
                        
                        # Extract text from cell
                        txt = ""
                        if 'Relationships' in cell:
                            for cr in cell['Relationships']:
                                if cr['Type'] == 'CHILD':
                                    for w_id in cr['Ids']:
                                        w = next(b for b in blocks if b['Id'] == w_id)
                                        txt += w['Text'] + " "
                        rows[r][c] = txt.strip()

        # 4. Data Processing and Localization (JST UTC+9)
        jst = datetime.timezone(datetime.timedelta(hours=9))
        now_ts = datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M")
        
        final_data = []
        for r_idx in sorted(rows.keys()):
            if r_idx == 1: continue # Skip Header Row
            
            row = rows[r_idx]
            dt_val = row.get(1, "N/A")
            weather = get_historical_weather(dt_val, vc_key)
            
            # Map 13 columns (A to M) for the Google Sheet
            final_data.append([
                now_ts, dt_val, row.get(2, "N/A"), row.get(3, "N/A"), 
                row.get(4, "N/A"), row.get(5, "N/A"), row.get(6, "N/A"), 
                row.get(7, "N/A"), row.get(8, "N/A"), row.get(9, "N/A"), 
                row.get(10, "N/A"), weather, document
            ])

        # 5. Export Data to Google Sheets API
        creds = service_account.Credentials.from_service_account_info(google_creds, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        service = build('sheets', 'v4', credentials=creds)
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range='Sheet1!A2',
            valueInputOption='USER_ENTERED', insertDataOption='INSERT_ROWS',
            body={'values': final_data}
        ).execute()

        return {'statusCode': 200, 'body': f'Successfully synced {len(final_data)} rows.'}

    except Exception as e:
        print(f"Critical Error: {str(e)}")
        # Re-raise to ensure the error is visible in CloudWatch
        raise e
