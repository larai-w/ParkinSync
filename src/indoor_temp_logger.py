import json
import boto3
import time
import hmac
import hashlib
import base64
import requests
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- Configuration ---
SECRET_ID = "ParkinSync/Production/GoogleCredentials"
REGION_NAME = "us-east-1"

def lambda_handler(event, context):
    """
    Background worker: Fetches indoor temperature from SwitchBot API v1.1 
    and logs it to Google Sheets for time-series analysis in SageMaker.
    """
    try:
        # 1. Retrieve Credentials from Secrets Manager
        secrets_client = boto3.client('secretsmanager', region_name=REGION_NAME)
        secret_value = secrets_client.get_secret_value(SecretId=SECRET_ID)
        secrets = json.loads(secret_value['SecretString'])
        
        token = secrets['SWITCHBOT_TOKEN']
        secret = secrets['SWITCHBOT_SECRET']
        device_id = secrets['SWITCHBOT_DEVICE_ID']
        spreadsheet_id = secrets['GOOGLE_SHEET_ID']

        # 2. Authenticate and Request Data from SwitchBot API
        t = str(int(time.time() * 1000))
        nonce = "ParkinSyncLogger"
        
        # Create Signature for SwitchBot API v1.1
        string_to_sign = f"{token}{t}{nonce}".encode('utf-8')
        sign = base64.b64encode(
            hmac.new(secret.encode('utf-8'), msg=string_to_sign, digestmod=hashlib.sha256).digest()
        ).decode('utf-8')
        
        headers = {
            "Authorization": token,
            "sign": sign,
            "t": t,
            "nonce": nonce,
            "Content-Type": "application/json; charset=utf8"
        }
        
        # Ensure device_id is correctly formatted (no colons) in Secrets Manager
        url = f"https://api.switch-bot.com/v1.1/devices/{device_id}/status"
        
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        indoor_temp = res.json()['body']['temperature']
        
        # 3. Get Timestamp in JST (UTC+9)
        jst = datetime.timezone(datetime.timedelta(hours=9))
        timestamp = datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M")
        
        # 4. Write to Google Sheets (TempHistory Tab)
        # Using the flat 'secrets' dict as credentials info
        creds = service_account.Credentials.from_service_account_info(
            secrets, 
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=creds)
        
        # Append data to the next available row in 'TempHistory'
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range='TempHistory!A1', 
            valueInputOption='USER_ENTERED',
            body={'values': [[timestamp, indoor_temp]]}
        ).execute()
        
        print(f"Log Success: {timestamp} - {indoor_temp}C")
        return {'statusCode': 200, 'body': f'Logged {indoor_temp}'}

    except Exception as e:
        print(f"Logging Failed: {str(e)}")
        return {'statusCode': 500, 'body': str(e)}
