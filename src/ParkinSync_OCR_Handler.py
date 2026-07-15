import os
import json
import urllib.parse
import datetime
import boto3
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration for AWS and localized weather enrichment.
SECRET_ID = "ParkinSync/Production/GoogleCredentials"
REGION_NAME = "us-east-1"
LAT = "35.38"
LON = "134.67"

def get_weather_emoji(condition_text):
    """Map weather conditions to specific emojis for dashboard clarity."""
    cond = condition_text.lower()
    if "rain" in cond: return "☔"
    if "cloud" in cond: return "☁️"
    if "clear" in cond or "sun" in cond: return "☀️"
    if "snow" in cond: return "❄️"
    if "partly" in cond: return "⛅"
    return "🌡️"

def get_historical_weather(date_str, api_key):
    """Fetch historical weather data for the specific date listed on the paper."""
    try:
        # Normalize date format for Visual Crossing API (e.g., "2026/02/07" -> "2026-02-07")
        formatted_date = date_str.strip().replace("/", "-")
        
        url = (
            f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
            f"{LAT},{LON}/{formatted_date}?key={api_key}&unitGroup=metric&include=days"
        )
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        day_data = res.json()['days'][0]
        
        emoji = get_weather_emoji(day_data['conditions'])
        summary = f"{emoji} Avg:{day_data['temp']}/Min:{day_data['tempmin']}/Max:{day_data['tempmax']} ({day_data['conditions']})"
        return summary, day_data
    except Exception as e:
        print(f"Weather Fetch Warning for {date_str}: {e}")
        return "Weather N/A", None

def lambda_handler(event, context):
    """
    v1.3.0 - Final Production Code.
    Features: Multi-row extraction, Historical Weather Sync, 25-column mapping.
    """
    textract = boto3.client('textract')
    secrets_client = boto3.client('secretsmanager', region_name=REGION_NAME)

    try:
        # 1. Retrieve S3 Event Details
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')

        # 2. Retrieve Credentials (Zero Hardcoding Policy)
        secret_value = secrets_client.get_secret_value(SecretId=SECRET_ID)
        secrets = json.loads(secret_value['SecretString'])
        vc_key = secrets.get('VISUAL_CROSSING_KEY')
        spreadsheet_id = secrets.get('GOOGLE_SHEET_ID')

        # 3. AWS Textract Analysis (Extracting Tables)
        response = textract.analyze_document(
            Document={'S3Object': {'Bucket': bucket, 'Name': key}},
            FeatureTypes=["TABLES"]
        )

        blocks = response['Blocks']
        tables = [b for b in blocks if b['BlockType'] == 'TABLE']
        if not tables:
            return {'statusCode': 404, 'body': 'No table detected in PDF'}

        # Map Textract blocks into rows/cols dictionary
        rows = {}
        for rel in tables[0].get('Relationships', []):
            if rel['Type'] == 'CHILD':
                for c_id in rel['Ids']:
                    cell = next(b for b in blocks if b['Id'] == c_id)
                    if cell['BlockType'] == 'CELL':
                        r, c = cell['RowIndex'], cell['ColumnIndex']
                        if r not in rows: rows[r] = {}
                        
                        # Extract text from the cell
                        txt = ""
                        for cell_rel in cell.get('Relationships', []):
                            if cell_rel['Type'] == 'CHILD':
                                for w_id in cell_rel['Ids']:
                                    word_b = next(b for b in blocks if b['Id'] == w_id)
                                    if word_b['BlockType'] == 'WORD':
                                        txt += word_b['Text'] + " "
                        rows[r][c] = txt.strip()

        # 4. Processing ALL Rows & Fetching Historical Weather
        processed_ts = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
        final_data_batch = []

        for r_idx in sorted(rows.keys()):
            row = rows[r_idx]
            dt_val = row.get(1, "") # Assuming Col 1 is the Date
            
            # Filter for rows that start with a valid year (e.g., 2026)
            if not dt_val or "Date" in dt_val or r_idx == 1:
                continue
            
            # Fetch weather matching the specific date on the paper
            weather_summary, raw_weather = get_historical_weather(dt_val, vc_key)

            # Build the 25-column Master Schema (A to Y)
            aligned_row = ["" for _ in range(25)]
            aligned_row[0] = processed_ts           # A: Processed Time
            aligned_row[1] = dt_val                 # B: Date from Paper
            aligned_row[2] = row.get(2, "")         # C: Day from Paper
            aligned_row[3] = row.get(3, "")         # D: Morning
            aligned_row[4] = row.get(4, "")         # E: Lunch
            aligned_row[5] = row.get(5, "")         # F: Evening
            aligned_row[6] = row.get(6, "")         # G: Bedtime 1
            aligned_row[7] = row.get(7, "")         # H: Bedtime 2
            aligned_row[8] = row.get(8, "")         # I: Bowel
            aligned_row[9] = row.get(9, "")         # J: Movi
            aligned_row[10] = row.get(10, "")       # K: Emergency Call
            aligned_row[11] = row.get(11, "")       # L: Condition C
            aligned_row[12] = row.get(12, "")       # M: Daily Notes
            
            # Weather Mapping (P-T)
            aligned_row[15] = weather_summary       # P: Weather Summary
            if raw_weather:
                aligned_row[16] = str(raw_weather['temp'])     # Q: Avg
                aligned_row[17] = str(raw_weather['tempmin'])  # R: Min
                aligned_row[18] = str(raw_weather['tempmax'])  # S: Max
                aligned_row[19] = raw_weather['conditions']    # T: Cond
            
            aligned_row[24] = key                   # Y: File Path (incoming/...)

            final_data_batch.append(aligned_row)

        # 5. Batch Update to Google Sheets (Targeting Sheet1)
        if final_data_batch:
            creds = service_account.Credentials.from_service_account_info(
                secrets, scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            service = build('sheets', 'v4', credentials=creds)
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range='Sheet1!A1',
                valueInputOption='USER_ENTERED',
                body={'values': final_data_batch}
            ).execute()

        return {'statusCode': 200, 'body': f'Successfully processed {len(final_data_batch)} rows.'}

    except Exception as e:
        print(f"[CRITICAL ERROR] {str(e)}")
        return {'statusCode': 500, 'body': 'Internal Processing Error'}
