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
LAT = os.environ.get("WEATHER_LAT", "35.38")
LON = os.environ.get("WEATHER_LON", "134.67")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1aHdVYePaTQQ59feBWtPXBYPpsaMBO2KMcuXhwV3AFBE")
SECRET_ID = os.environ.get("SECRET_ID", "ParkinSync/Production/GoogleCredentials")
# SNS_TOPIC_ARN and LOG_MONTH are intentionally NOT cached at module level
# so that tests can override them via patch.dict('os.environ', ...).

JST = datetime.timezone(datetime.timedelta(hours=9))

MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "sept": "09", "oct": "10",
    "nov": "11", "dec": "12",
}

# S3 object tag used to prevent reprocessing the same file
_PROCESSED_TAG = "ParkinSync-Status"
_PROCESSED_VALUE = "processed"
_REVIEW_PREFIX = "review/"


def _log_year():
    """Year used when the OCR date has no year. Overridable via LOG_YEAR env var."""
    return os.environ.get("LOG_YEAR", str(datetime.datetime.now(JST).year))


def _infer_month_from_key(document_key):
    """
    Try to extract a month string ('YYYY-MM') from the S3 object key (filename).
    Supports patterns like: '2026-04_log.jpg', 'log_april_2026.pdf', 'log_2026_04.jpg'
    Returns 'YYYY-MM' string or None.
    """
    log_month = os.environ.get("LOG_MONTH", "")
    if log_month:
        m = re.match(r'(\d{4})-(\d{2})', log_month)
        if m:
            return log_month[:7]

    # Numeric: 2026-04 or 2026_04
    m = re.search(r'(\d{4})[-_](\d{2})', document_key)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # English month name in filename
    m = re.search(r'([A-Za-z]+)', document_key)
    if m:
        month_num = MONTH_MAP.get(m.group(1).lower())
        if month_num:
            year_m = re.search(r'(\d{4})', document_key)
            year = year_m.group(1) if year_m else _log_year()
            return f"{year}-{month_num}"

    return None


def parse_log_date(date_str, fallback_month=None):
    """
    Parses an OCR date string into 'YYYY-MM-DD', or returns None if unparseable.
    Supported formats:
      - 'April 20', 'Apr 20th'   (English month, optional ordinal)
      - '4月20日'                 (Japanese)
      - '4/20', '04-20'          (numeric month/day)
      - '2026-04-20', '2026/4/20' (full ISO-like)
      - '20th', '3rd'            (day-only — requires fallback_month='YYYY-MM')
    """
    if not date_str:
        return None
    text = str(date_str).strip()

    # Full ISO date: year present
    m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

    # Japanese: 4月20日
    m = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日?', text)
    if m:
        return f"{_log_year()}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"

    # English month + day: "April 20", "Apr 3rd"
    m = re.search(r'([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower())
        if month:
            return f"{_log_year()}-{month}-{m.group(2).zfill(2)}"

    # Numeric month/day: 4/20 or 04-20
    m = re.search(r'(\d{1,2})[-/](\d{1,2})', text)
    if m:
        return f"{_log_year()}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"

    # Day-only ordinal: "20th", "3rd" — needs fallback_month='YYYY-MM'
    if fallback_month:
        m = re.search(r'^(\d{1,2})(?:st|nd|rd|th)?$', text)
        if m:
            return f"{fallback_month}-{m.group(1).zfill(2)}"

    return None


def get_historical_weather(date_str, api_key, fallback_month=None):
    """Fetches historical weather from Visual Crossing for the given OCR date."""
    try:
        formatted_date = parse_log_date(date_str, fallback_month=fallback_month)
        if formatted_date:
            url = (
                f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
                f"{LAT},{LON}/{formatted_date}"
                f"?key={api_key}&unitGroup=metric&include=days"
            )
            response = requests.get(url)
            data = response.json()
            day_info = data['days'][0]
            return f"{day_info['temp']}C, {day_info['conditions']} (Hist)"
    except Exception as e:
        print(f"Weather Fetch Error: {e}")
    return "Weather N/A"


# --- Task 6: OCR failure recovery helpers ---

def _quarantine_and_notify(s3, bucket, document, reason):
    """
    Copies the failed image to review/ prefix and sends an SNS notification.
    Non-fatal: errors here are logged but never re-raised.
    """
    try:
        dest_key = f"{_REVIEW_PREFIX}{document}"
        s3.copy_object(
            Bucket=bucket,
            CopySource={'Bucket': bucket, 'Key': document},
            Key=dest_key,
        )
        print(f"[QUARANTINE] Copied {document} -> {dest_key} | Reason: {reason}")
    except Exception as e:
        print(f"[QUARANTINE] Failed to copy to review/: {e}")

    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    if sns_topic_arn:
        try:
            sns = boto3.client('sns')
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject=f"[ParkinSync] 手動確認が必要なファイル",
                Message=(
                    f"ファイル: s3://{bucket}/{document}\n"
                    f"理由: {reason}\n"
                    f"コピー先: s3://{bucket}/{_REVIEW_PREFIX}{document}"
                ),
            )
        except Exception as e:
            print(f"[SNS] Publish failed: {e}")


# --- Task 7: Idempotency helpers ---

def _is_already_processed(s3, bucket, document):
    """Returns True if the S3 object has already been processed (tagged)."""
    try:
        resp = s3.get_object_tagging(Bucket=bucket, Key=document)
        for tag in resp.get('TagSet', []):
            if tag['Key'] == _PROCESSED_TAG and tag['Value'] == _PROCESSED_VALUE:
                return True
    except Exception as e:
        print(f"[IDEMPOTENCY] Tag check failed (treating as unprocessed): {e}")
    return False


def _mark_as_processed(s3, bucket, document):
    """Tags the S3 object as processed to prevent reprocessing."""
    try:
        # Preserve existing tags and add/overwrite ours
        resp = s3.get_object_tagging(Bucket=bucket, Key=document)
        existing = [t for t in resp.get('TagSet', []) if t['Key'] != _PROCESSED_TAG]
        existing.append({'Key': _PROCESSED_TAG, 'Value': _PROCESSED_VALUE})
        s3.put_object_tagging(Bucket=bucket, Key=document, Tagging={'TagSet': existing})
    except Exception as e:
        print(f"[IDEMPOTENCY] Failed to tag object: {e}")


def lambda_handler(event, context):
    """
    Main entry point for AWS Lambda.
    Triggered by S3 upload, processes OCR via Textract, and saves to Google Sheets.
    """
    bucket = event['Records'][0]['s3']['bucket']['name']
    document = event['Records'][0]['s3']['object']['key']

    # Skip files already sitting in the review/ quarantine folder (no clients needed)
    if document.startswith(_REVIEW_PREFIX):
        return {'statusCode': 200, 'body': 'Skipped review/ prefix file.'}

    # Initialize AWS clients inside the handler for clean unit-test mocking.
    s3 = boto3.client('s3')
    textract = boto3.client('textract')
    secrets_client = boto3.client('secretsmanager')

    # --- Task 7: Idempotency check ---
    if _is_already_processed(s3, bucket, document):
        print(f"[IDEMPOTENCY] Already processed: {document}")
        return {'statusCode': 200, 'body': f'Already processed: {document}'}

    # --- Task 9: Infer month from filename for day-only date cells ---
    fallback_month = _infer_month_from_key(document)

    try:
        # 1. Retrieve credentials from AWS Secrets Manager
        secret_response = secrets_client.get_secret_value(SecretId=SECRET_ID)
        secrets = json.loads(secret_response['SecretString'])
        google_creds = secrets
        vc_key = secrets.get('VISUAL_CROSSING_KEY')

        # 2. Analyze document with Amazon Textract (TABLES feature)
        response = textract.analyze_document(
            Document={'S3Object': {'Bucket': bucket, 'Name': document}},
            FeatureTypes=["TABLES"]
        )

        blocks = response['Blocks']
        tables = [b for b in blocks if b['BlockType'] == 'TABLE']
        if not tables:
            _quarantine_and_notify(s3, bucket, document, "Textract: テーブルが検出されませんでした")
            return {'statusCode': 404, 'body': 'No table detected in document'}

        # Map Textract cells into a row/column dictionary
        rows = {}
        for rel in tables[0].get('Relationships', []):
            if rel['Type'] == 'CHILD':
                for c_id in rel['Ids']:
                    cell = next(b for b in blocks if b['Id'] == c_id)
                    if cell['BlockType'] == 'CELL':
                        r, c = cell['RowIndex'], cell['ColumnIndex']
                        if r not in rows:
                            rows[r] = {}
                        txt = ""
                        if 'Relationships' in cell:
                            for cr in cell['Relationships']:
                                if cr['Type'] == 'CHILD':
                                    for w_id in cr['Ids']:
                                        w = next(b for b in blocks if b['Id'] == w_id)
                                        txt += w['Text'] + " "
                        rows[r][c] = txt.strip()

        # 3. Data processing and localization (JST UTC+9)
        now_ts = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M")

        final_data = []
        for r_idx in sorted(rows.keys()):
            if r_idx == 1:
                continue  # Skip header row
            row = rows[r_idx]
            dt_val = row.get(1, "N/A")
            weather = get_historical_weather(dt_val, vc_key, fallback_month=fallback_month)

            # 13 columns (A–M)
            final_data.append([
                now_ts, dt_val, row.get(2, "N/A"), row.get(3, "N/A"),
                row.get(4, "N/A"), row.get(5, "N/A"), row.get(6, "N/A"),
                row.get(7, "N/A"), row.get(8, "N/A"), row.get(9, "N/A"),
                row.get(10, "N/A"), weather, document
            ])

        # 4. Export to Google Sheets
        creds = service_account.Credentials.from_service_account_info(
            google_creds, scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=creds)
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range='Sheet1!A2',
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': final_data}
        ).execute()

        # 5. Mark as processed to prevent re-ingestion
        _mark_as_processed(s3, bucket, document)

        return {'statusCode': 200, 'body': f'Successfully synced {len(final_data)} rows.'}

    except Exception as e:
        print(f"Critical Error: {str(e)}")
        _quarantine_and_notify(s3, bucket, document, f"処理中のエラー: {str(e)}")
        raise e
