import os
import json
import re
import urllib.parse
import datetime
import boto3
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration for AWS and localized weather enrichment.
# Overridable via Lambda environment variables; defaults keep local/dev behavior.
SECRET_ID = os.environ.get("SECRET_ID", "ParkinSync/Production/GoogleCredentials")
REGION_NAME = os.environ.get("SECRETS_REGION", "us-east-1")
LAT = os.environ.get("WEATHER_LAT", "35.38")
LON = os.environ.get("WEATHER_LON", "134.67")

JST = datetime.timezone(datetime.timedelta(hours=9))

# Month-name lookup for filename inference and OCR date parsing.
MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "sept": "09", "oct": "10",
    "nov": "11", "dec": "12",
}

# S3 object tag used to make processing idempotent, and the quarantine prefix.
_PROCESSED_TAG = "ParkinSync-Status"
_PROCESSED_VALUE = "processed"
_REVIEW_PREFIX = "review/"


def get_weather_emoji(condition_text):
    """Map weather conditions to specific emojis for dashboard clarity."""
    cond = condition_text.lower()
    if "rain" in cond: return "☔"
    if "cloud" in cond: return "☁️"
    if "clear" in cond or "sun" in cond: return "☀️"
    if "snow" in cond: return "❄️"
    if "partly" in cond: return "⛅"
    return "🌡️"


def _log_year():
    """Year used when the OCR date has no year. Overridable via LOG_YEAR env var."""
    return os.environ.get("LOG_YEAR", str(datetime.datetime.now(JST).year))


def _infer_month_from_key(document_key):
    """
    Extract a 'YYYY-MM' month hint from the S3 object key (filename), used to
    resolve day-only OCR cells such as '20th'. Supports patterns like
    '2026-04_log.jpg', 'log_2026_04.pdf', 'april_2026_log.jpg'. Returns None when
    nothing usable is found. `LOG_MONTH` env var takes precedence when set.
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

    # English month name in the filename
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
    Parse an OCR date string into 'YYYY-MM-DD', or return None if unparseable.
    Supported formats:
      - '2026-04-20', '2026/4/20'  (full ISO-like, keeps its own year)
      - '4月20日'                   (Japanese)
      - 'April 20', 'Apr 3rd'      (English month, optional ordinal)
      - '4/20', '04-20'            (numeric month/day, uses LOG_YEAR)
      - '20th', '3rd'              (day-only — requires fallback_month='YYYY-MM')
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
    """
    Fetch historical weather for the specific date listed on the paper.
    Returns a (summary_string, raw_day_dict) tuple, or ("Weather N/A", None) when
    the date is unparseable or the API call fails (never raises).
    """
    try:
        formatted_date = parse_log_date(date_str, fallback_month=fallback_month)
        if not formatted_date:
            return "Weather N/A", None

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


# もう一度やっても結果が変わらない失敗。**リトライに意味が無い。**
# Textract の同期 API（`analyze_document`）は複数ページ PDF を受け付けず、
# `UnsupportedDocumentException` を返す。**ファイルが変わらない限り毎回失敗する。**
_PERMANENT_FAILURES = frozenset({
    "UnsupportedDocumentException",     # 形式が対象外（複数ページPDF・破損など）
    "DocumentTooLargeException",        # 大きすぎる
    "BadDocumentException",             # 読めない
    "InvalidParameterException",        # 呼び出し方が間違っている
    "UnsupportedActionException",
})


def _failure_reason(exc):
    """隔離の理由を、**受け取った人が次にできること**まで書く。

    2026-08-21 に3件の介護記録が隔離されたが、通知に書かれていたのは
    `処理中のエラー: An error occurred (UnsupportedDocumentException) ...` だけで、
    **何をすれば取り込めるのかが書いていなかった。** 結果、3件は隔離されたまま。

    隔離された3件を数えたところ、**すべて2ページ**だった。
    処理できたものは**すべて1ページ**。
    Textract の同期 API（`analyze_document`）は**1ページの PDF しか受け付けない。**

    **1ページずつに分けて `incoming/` へ入れ直せば、いまのコードで取り込める。**
    （このハンドラは表を1つしか読まない実装なので、
      1ページ1表になる分割のほうが、非同期 API 化より確実。）
    """
    name = type(exc).__name__
    code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
    if "UnsupportedDocument" in name or "UnsupportedDocument" in code:
        return (
            "複数ページの PDF は取り込めません"
            "（Textract の同期 API は1ページのみ対応）。\n"
            "**1ページずつに分けて incoming/ へ入れ直してください。**\n"
            f"元のエラー: {exc}"
        )
    return f"処理中のエラー: {exc}"


def _is_permanent_failure(exc):
    """リトライしても結果が変わらない失敗か。

    **判定は例外の名前で行う。** botocore の例外クラスはサービスの
    エラーコードから動的に作られるので、`isinstance` では捕まえにくい。
    """
    name = type(exc).__name__
    if name in _PERMANENT_FAILURES:
        return True
    # botocore の ClientError は、中のエラーコードを見る
    code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
    return code in _PERMANENT_FAILURES


def _quarantine_and_notify(s3, bucket, document, reason):
    """
    Copy a failed image to the review/ prefix and send an SNS notification so a
    human can inspect it. Non-fatal: errors here are logged but never re-raised.
    SNS is only attempted when SNS_TOPIC_ARN is configured.
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
                Subject="[ParkinSync] 手動確認が必要なファイル",
                Message=(
                    f"ファイル: s3://{bucket}/{document}\n"
                    f"理由: {reason}\n"
                    f"コピー先: s3://{bucket}/{_REVIEW_PREFIX}{document}"
                ),
            )
        except Exception as e:
            print(f"[SNS] Publish failed: {e}")


def _is_already_processed(s3, bucket, document):
    """Return True if the S3 object has already been tagged as processed."""
    try:
        resp = s3.get_object_tagging(Bucket=bucket, Key=document)
        for tag in resp.get('TagSet', []):
            if tag['Key'] == _PROCESSED_TAG and tag['Value'] == _PROCESSED_VALUE:
                return True
    except Exception as e:
        print(f"[IDEMPOTENCY] Tag check failed (treating as unprocessed): {e}")
    return False


def _mark_as_processed(s3, bucket, document):
    """Tag the S3 object as processed to prevent reprocessing, preserving other tags.

    Returns True if the tag was written, False otherwise.

    We do NOT raise on failure. This runs *after* the rows have been appended to
    the spreadsheet, so raising would let the Lambda retry and duplicate them.
    But a silent failure is worse in a different way: the object stays untagged,
    looks unprocessed forever, and nobody finds out. So the failure is made loud
    in the log and returned to the caller.
    """
    try:
        resp = s3.get_object_tagging(Bucket=bucket, Key=document)
        existing = [t for t in resp.get('TagSet', []) if t['Key'] != _PROCESSED_TAG]
        existing.append({'Key': _PROCESSED_TAG, 'Value': _PROCESSED_VALUE})
        s3.put_object_tagging(Bucket=bucket, Key=document, Tagging={'TagSet': existing})
        return True
    except Exception as e:
        # [TAGGING FAILED] is the string to alarm on. Rows were already written,
        # so the data is not lost -- but the object will be reprocessed if the
        # same S3 event fires again.
        print(f"[TAGGING FAILED] {document}: {e}")
        return False


def lambda_handler(event, context):
    """
    v1.4.0 - reconciled production handler (Issue #27).
    Keeps the 25-column master schema and historical-weather enrichment, and adds
    the hardening that had only existed in the deployed image: idempotent S3
    processing, OCR-failure quarantine + notification, and filename-assisted date
    recovery. On an unexpected error the file is quarantined and the error is
    re-raised so Lambda can retry / route to a DLQ.
    """
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')

    # Skip files already sitting in the review/ quarantine folder.
    if key.startswith(_REVIEW_PREFIX):
        return {'statusCode': 200, 'body': 'Skipped review/ prefix file.'}

    # Initialize AWS clients inside the handler for clean unit-test mocking.
    s3 = boto3.client('s3')
    textract = boto3.client('textract')
    secrets_client = boto3.client('secretsmanager', region_name=REGION_NAME)

    # Idempotency: never reprocess a file we already ingested.
    if _is_already_processed(s3, bucket, key):
        print(f"[IDEMPOTENCY] Already processed: {key}")
        return {'statusCode': 200, 'body': f'Already processed: {key}'}

    # Filename month hint, used to resolve day-only date cells (e.g. "20th").
    fallback_month = _infer_month_from_key(key)

    try:
        # 1. Retrieve credentials (Zero Hardcoding Policy).
        secret_value = secrets_client.get_secret_value(SecretId=SECRET_ID)
        secrets = json.loads(secret_value['SecretString'])
        vc_key = secrets.get('VISUAL_CROSSING_KEY')
        spreadsheet_id = secrets.get('GOOGLE_SHEET_ID')

        # 2. AWS Textract Analysis (Extracting Tables).
        response = textract.analyze_document(
            Document={'S3Object': {'Bucket': bucket, 'Name': key}},
            FeatureTypes=["TABLES"]
        )

        blocks = response['Blocks']
        tables = [b for b in blocks if b['BlockType'] == 'TABLE']
        if not tables:
            _quarantine_and_notify(s3, bucket, key, "Textract: テーブルが検出されませんでした")
            return {'statusCode': 404, 'body': 'No table detected in PDF'}

        # Map Textract blocks into rows/cols dictionary.
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

        # 3. Process ALL rows & fetch historical weather.
        processed_ts = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M")
        final_data_batch = []

        for r_idx in sorted(rows.keys()):
            row = rows[r_idx]
            dt_val = row.get(1, "")  # Assuming Col 1 is the Date

            # Skip header/non-data rows.
            if not dt_val or "Date" in dt_val or r_idx == 1:
                continue

            # Fetch weather matching the specific date on the paper.
            weather_summary, raw_weather = get_historical_weather(dt_val, vc_key, fallback_month=fallback_month)

            # Build the 25-column Master Schema (A to Y).
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

            # Weather Mapping (P-T).
            aligned_row[15] = weather_summary       # P: Weather Summary
            if raw_weather:
                aligned_row[16] = str(raw_weather['temp'])     # Q: Avg
                aligned_row[17] = str(raw_weather['tempmin'])  # R: Min
                aligned_row[18] = str(raw_weather['tempmax'])  # S: Max
                aligned_row[19] = raw_weather['conditions']    # T: Cond

            aligned_row[24] = key                   # Y: File Path (incoming/...)

            final_data_batch.append(aligned_row)

        # 4. Batch update to Google Sheets (Targeting Sheet1).
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

        # 5. Mark as processed to prevent re-ingestion on duplicate S3 events.
        tagged = _mark_as_processed(s3, bucket, key)

        # Report the tagging outcome in the response. Previously a tagging failure
        # was invisible: the rows landed, the Lambda returned 200, and the object
        # stayed untagged. Callers and logs could not tell the two cases apart.
        body = f'Successfully processed {len(final_data_batch)} rows.'
        if not tagged:
            body += ' WARNING: object could not be tagged as processed.'
        return {'statusCode': 200, 'body': body, 'tagged': tagged}

    except Exception as e:
        print(f"[CRITICAL ERROR] {str(e)}")
        _quarantine_and_notify(s3, bucket, key, _failure_reason(e))

        # **もう一度やっても結果が変わらない失敗は、投げ直さない。**
        #
        # 2026-08-21 に3件の PDF が `UnsupportedDocumentException` で失敗した。
        # 隔離も通知も正しく動いたのに、そのあと投げ直していたため:
        #
        #   - Lambda が自動リトライする。**ファイル形式は次も同じなので必ず失敗する**
        #   - リトライのたびに隔離コピーと通知メールが増える
        #   - エラー率が膨らみ、**本当に直せる一時的な失敗が埋もれる**
        #
        # この関数は既にこの区別を持っている。「テーブル未検出」は
        # 隔離して 404 を返し、投げ直していない。**同じ扱いに揃える。**
        #
        # ⚠️ **握りつぶすのとは違う。** 失敗は3つの経路で残る:
        #   1. `review/` に隔離される
        #   2. SNS でメールが飛ぶ（購読済みを 2026-08-26 に確認）
        #   3. ログに `[PERMANENT FAILURE]` が出る（メトリクスフィルタで拾える）
        if _is_permanent_failure(e):
            print(f"[PERMANENT FAILURE] {key}: {type(e).__name__} — リトライしても直らない")
            return {
                'statusCode': 422,
                'body': f'Permanently unprocessable: {type(e).__name__}',
                'quarantined': True,
            }

        # 一時的かもしれない失敗は投げ直す。**Lambda のリトライに意味がある。**
        raise
