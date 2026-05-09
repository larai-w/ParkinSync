import boto3
import json
import requests
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURATION ---
LAT = "35.38"
LON = "134.67"
SPREADSHEET_ID = "1aHdVYePaTQQ59feBWtPXBYPpsaMBO2KMcuXhwV3AFBE"
SECRET_ID = "ParkinSync/Production/GoogleCredentials"

# Initialize AWS clients
textract = boto3.client('textract')
secrets_client = boto3.client('secretsmanager')

def get_historical_weather(date_str, api_key):
    """
    Parses OCR date (e.g., 'April 20') and fetches weather from Visual Crossing.
    """
    try:
        month_map = {"April": "04", "May": "05"}
        parts = date_str.split()
        if len(parts) >= 2:
            month = month_map.get(parts[0], "04")
            day = parts[1].zfill(2)
            # Hardcoded year 2026 for clinical test context
            formatted_date = f"2026-{month}-{day}"
            
            url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LAT},{LON}/{formatted_date}?key={api_key}&unitGroup=metric&include=days"
            response = requests.get(url)
            data = response.json()
            
            day_data = data['days'][0]
            return f"{day_data['temp']}C, {day_data['conditions']} (Hist)"
    except Exception as e:
        print(f"Weather Fetch Error: {e}")
    return "Weather N/A"

def lambda_handler(event, context):
    try:
        # 1. Capture S3 Event Data
        bucket = event['Records'][0]['s3']['bucket']['name']
        document = event['Records'][0]['s3']['object']['key']

        # 2. Retrieve Secrets from AWS Secrets Manager
        secret_response = secrets_client.get_secret_value(SecretId=SECRET_ID)
        secrets = json.loads(secret_response['SecretString'])
        google_creds_info = secrets
        vc_api_key = secrets.get('VISUAL_CROSSING_KEY')

        # 3. Execute Textract Tables Analysis
        response = textract.analyze_document(
            Document={'S3Object': {'Bucket': bucket, 'Name': document}},
            FeatureTypes=["TABLES"]
        )

        blocks = response['Blocks']
        tables = [block for block in blocks if block['BlockType'] == 'TABLE']
        if not tables:
            return {'statusCode': 404, 'body': 'No table found'}

        # Map table cells into a dictionary rows[row_index][column_index]
        rows = {}
        for relationship in tables[0].get('Relationships', []):
            if relationship['Type'] == 'CHILD':
                for child_id in relationship['Ids']:
                    cell = next(b for b in blocks if b['Id'] == child_id)
                    if cell['BlockType'] == 'CELL':
                        r, c = cell['RowIndex'], cell['ColumnIndex']
                        if r not in rows: rows[r] = {}
                        txt = ""
                        if 'Relationships' in cell:
                            for child_rel in cell['Relationships']:
                                if child_rel['Type'] == 'CHILD':
                                    for w_id in child_rel['Ids']:
                                        w = next(b for b in blocks if b['Id'] == w_id)
                                        if w['BlockType'] == 'WORD': txt += w['Text'] + " "
                        rows[r][c] = txt.strip()

        # 4. Prepare Timezone and Row Data (JST UTC+9)
        jst = datetime.timezone(datetime.timedelta(hours=9))
        now_ts = datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M")
        
        final_rows = []
        for r_idx in sorted(rows.keys()):
            if r_idx == 1: continue # Skip Header
            
            row = rows[r_idx]
            date_val = row.get(1, "N/A")
            weather_for_date = get_historical_weather(date_val, vc_api_key)
            
            # Map all 13 columns (A to M)
            final_rows.append([
                now_ts,                     # Col A: Processed At
                date_val,                   # Col B: Date
                row.get(2, "N/A"),          # Col C: Day
                row.get(3, "N/A"),          # Col D: Morning
                row.get(4, "N/A"),          # Col E: Lunch
                row.get(5, "N/A"),          # Col F: Evening
                row.get(6, "N/A"),          # Col G: Bedtime
                row.get(7, "N/A"),          # Col H: Bowel/Movi
                row.get(8, "N/A"),          # Col I: Condition C
                row.get(9, "N/A"),          # Col J: Emerg. Call
                row.get(10, "N/A"),         # Col K: Daily Notes
                weather_for_date,           # Col L: Historical Weather
                document                    # Col M: File Name
            ])

        # 5. Batch Update Google Sheets
        service = build('sheets', 'v4', credentials=service_account.Credentials.from_service_account_info(google_creds_info, scopes=['https://www.googleapis.com/auth/spreadsheets']))
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range='Sheet1!A2',
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': final_rows}
        ).execute()

        return {'statusCode': 200, 'body': f'Synced {len(final_rows)} rows successfully.'}

    except Exception as e:
        print(f"Critical Error: {str(e)}")
        raise e
