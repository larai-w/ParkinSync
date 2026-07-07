import boto3
import json
import os
import re
import requests
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURATION ---
# All values can be overridden via Lambda environment variables.
# Defaults preserve the original production values.
# Target coordinates for weather data (Hyogo, Japan)
LAT = os.environ.get("WEATHER_LAT", "35.38")
LON = os.environ.get("WEATHER_LON", "134.67")
# Google Spreadsheet ID for data logging
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1aHdVYePaTQQ59feBWtPXBYPpsaMBO2KMcuXhwV3AFBE")
# AWS Secrets Manager ID for storing API keys and credentials
SECRET_ID = os.environ.get("SECRET_ID", "ParkinSync/Production/GoogleCredentials")

JST = datetime.timezone(datetime.timedelta(hours=9))

MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "sept": "09", "oct": "10",
    "nov": "11", "dec": "12",
}

def _log_year():
    """Year used when the OCR date has no year. Overridable for trial contexts."""
    return os.environ.get("LOG_YEAR", str(datetime.datetime.now(JST).year))

def parse_log_date(date_str):
    """
    Parses an OCR date string into 'YYYY-MM-DD', or returns None if unparseable.
    Supported formats:
      - 'April 20', 'Apr 20th' (English month, optional ordinal suffix)
      - '4月20日' (Japanese)
      - '4/20', '04-20' (numeric month/day)
      - '2026-04-20', '2026/4/20' (full ISO-like date)
    """
    if not date_str:
        return None
    text = str(date_str).strip()

    m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

    m = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日?', text)
    if m:
        return f"{_log_year()}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"

    m = re.search(r'([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower())
        if month:
            return f"{_log_year()}-{month}-{m.group(2).zfill(2)}"

    m = re.search(r'(\d{1,2})[-/](\d{1,2})', text)
    if m:
        return f"{_log_year()}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"

    return None

def get_historical_weather(date_str, api_key):
    """
    Parses an OCR date and fetches historical weather from Visual Crossing.
    Returns a string containing temperature and weather conditions.
    """
    try:
        formatted_date = parse_log_date(date_str)
        if formatted_date:
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
        now_ts = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M")
        
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