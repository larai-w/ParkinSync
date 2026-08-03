import base64
import datetime
import hashlib
import hmac
import json
import math
import os
import time

import boto3
import google_auth_httplib2
import httplib2
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build


SECRET_ID = os.environ.get("SECRET_ID", "ParkinSync/Production/GoogleCredentials")
REGION_NAME = os.environ.get("SECRETS_REGION", "us-east-1")
TEMP_HISTORY_SHEET = os.environ.get("TEMP_HISTORY_SHEET", "TempHistory")
MASTER_SHEET = os.environ.get("MASTER_SHEET", "Sheet1")
JST = datetime.timezone(datetime.timedelta(hours=9))
SHEETS_HTTP_TIMEOUT = int(os.environ.get("SHEETS_HTTP_TIMEOUT", "8"))


def _sheet_ref(sheet_name):
    """Quote a Google Sheets tab name for use in an A1 range."""
    return f"'{sheet_name.replace(chr(39), chr(39) * 2)}'"


def _parse_timestamp(value):
    """Parse a telemetry timestamp and normalize it to JST."""
    if isinstance(value, datetime.datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None

        parsed = None
        try:
            parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for fmt in (
                "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
            ):
                try:
                    parsed = datetime.datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue

        if parsed is None:
            return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _parse_date(value):
    """Parse a Master Sheet date without relying on the spreadsheet locale."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value

    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _temperature(value):
    """Return a finite float, or None for blank/malformed telemetry."""
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def current_sample_time(now=None):
    """Return the actual sensor-poll time in JST."""
    sample_time = now or datetime.datetime.now(JST)
    if sample_time.tzinfo is None:
        sample_time = sample_time.replace(tzinfo=JST)
    return sample_time.astimezone(JST)


def event_id_from_event(event):
    """Return the stable EventBridge ID used to recognize retries."""
    if not isinstance(event, dict):
        return ""
    return str(event.get("id") or "").strip()


def sample_already_logged(rows, event_id, sample_time):
    """Detect an EventBridge retry, with a minute fallback for manual calls."""
    expected = sample_time.astimezone(JST).replace(second=0, microsecond=0)
    for row in rows:
        if not row:
            continue
        if event_id and len(row) >= 3 and str(row[2]).strip() == event_id:
            return True
        existing = _parse_timestamp(row[0])
        if not event_id and existing and existing.replace(second=0, microsecond=0) == expected:
            return True
    return False


def aggregate_telemetry_rows(rows, target_date):
    """Calculate daily indoor temperature aggregates from synthetic or sheet rows."""
    target = _parse_date(target_date)
    if target is None:
        raise ValueError("target_date must be a supported calendar date")

    temperatures = []
    for row in rows:
        if len(row) < 2:
            continue
        timestamp = _parse_timestamp(row[0])
        temperature = _temperature(row[1])
        if timestamp and timestamp.date() == target and temperature is not None:
            temperatures.append(temperature)

    if not temperatures:
        return None

    return {
        "count": len(temperatures),
        "avg": round(sum(temperatures) / len(temperatures), 2),
        "min": round(min(temperatures), 2),
        "max": round(max(temperatures), 2),
    }


def _master_row_numbers(date_rows, target_date, start_row=2):
    """Find all Master Sheet row numbers matching the requested date."""
    target = _parse_date(target_date)
    if target is None:
        raise ValueError("target_date must be a supported calendar date")

    return [
        index
        for index, row in enumerate(date_rows, start=start_row)
        if row and _parse_date(row[0]) == target
    ]


def _format_summary(aggregate):
    return (
        f"Avg:{aggregate['avg']:.2f}/Min:{aggregate['min']:.2f}/"
        f"Max:{aggregate['max']:.2f}"
    )


def sync_daily_aggregate(service, spreadsheet_id, telemetry_rows, target_date):
    """Update U:X only when exactly one Master Sheet date row exists."""
    aggregate = aggregate_telemetry_rows(telemetry_rows, target_date)
    if aggregate is None:
        return {"status": "no-valid-samples", "target_date": str(target_date)}

    values_api = service.spreadsheets().values()
    date_response = values_api.get(
        spreadsheetId=spreadsheet_id,
        range=f"{_sheet_ref(MASTER_SHEET)}!B2:B",
        valueRenderOption="FORMATTED_VALUE",
        fields="values",
    ).execute()
    matches = _master_row_numbers(date_response.get("values", []), target_date)

    if not matches:
        return {"status": "master-date-missing", "target_date": str(target_date)}
    if len(matches) > 1:
        return {"status": "duplicate-master-date", "target_date": str(target_date)}

    row_number = matches[0]
    values_api.update(
        spreadsheetId=spreadsheet_id,
        range=f"{_sheet_ref(MASTER_SHEET)}!U{row_number}:X{row_number}",
        valueInputOption="RAW",
        body={
            "values": [[
                _format_summary(aggregate),
                aggregate["avg"],
                aggregate["min"],
                aggregate["max"],
            ]]
        },
    ).execute()
    return {
        "status": "updated",
        "target_date": str(target_date),
        "sample_count": aggregate["count"],
    }


def lambda_handler(event, context):
    """Log one indoor sample and refresh its local-day Master aggregate."""
    try:
        secrets_client = boto3.client("secretsmanager", region_name=REGION_NAME)
        secret_value = secrets_client.get_secret_value(SecretId=SECRET_ID)
        secrets = json.loads(secret_value["SecretString"])

        token = secrets["SWITCHBOT_TOKEN"]
        secret = secrets["SWITCHBOT_SECRET"]
        device_id = secrets["SWITCHBOT_DEVICE_ID"]
        spreadsheet_id = secrets["GOOGLE_SHEET_ID"]

        request_time = str(int(time.time() * 1000))
        nonce = "ParkinSyncLogger"
        string_to_sign = f"{token}{request_time}{nonce}".encode("utf-8")
        sign = base64.b64encode(
            hmac.new(
                secret.encode("utf-8"),
                msg=string_to_sign,
                digestmod=hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        headers = {
            "Authorization": token,
            "sign": sign,
            "t": request_time,
            "nonce": nonce,
            "Content-Type": "application/json; charset=utf8",
        }

        url = f"https://api.switch-bot.com/v1.1/devices/{device_id}/status"
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        indoor_temp = _temperature(response.json()["body"]["temperature"])
        if indoor_temp is None:
            raise ValueError("SwitchBot returned a non-numeric temperature")

        sample_time = current_sample_time()
        event_id = event_id_from_event(event)
        timestamp = sample_time.strftime("%Y-%m-%d %H:%M")

        creds = service_account.Credentials.from_service_account_info(
            secrets,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        sheets_http = google_auth_httplib2.AuthorizedHttp(
            creds,
            http=httplib2.Http(timeout=SHEETS_HTTP_TIMEOUT),
        )
        service = build(
            "sheets",
            "v4",
            credentials=creds,
            http=sheets_http,
            cache_discovery=False,
            num_retries=0,
        )
        values_api = service.spreadsheets().values()

        history_response = values_api.get(
            spreadsheetId=spreadsheet_id,
            range=f"{_sheet_ref(TEMP_HISTORY_SHEET)}!A:C",
            valueRenderOption="FORMATTED_VALUE",
            fields="values",
        ).execute()
        telemetry_rows = list(history_response.get("values", []))

        duplicate = sample_already_logged(telemetry_rows, event_id, sample_time)
        if not duplicate:
            values_api.append(
                spreadsheetId=spreadsheet_id,
                range=f"{_sheet_ref(TEMP_HISTORY_SHEET)}!A:C",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [[timestamp, indoor_temp, event_id]]},
            ).execute()
            telemetry_rows.append([timestamp, indoor_temp, event_id])

        aggregate_result = sync_daily_aggregate(
            service,
            spreadsheet_id,
            telemetry_rows,
            sample_time.date(),
        )

        print(
            f"Telemetry success: sample={'duplicate' if duplicate else 'logged'} "
            f"aggregate={aggregate_result['status']}"
        )
        return {
            "statusCode": 200,
            "body": json.dumps({
                "sample": "duplicate" if duplicate else "logged",
                "aggregate": aggregate_result["status"],
            }),
        }

    except Exception as error:
        print(f"Telemetry logging failed: {error}")
        return {"statusCode": 500, "body": "Telemetry logging failed"}
