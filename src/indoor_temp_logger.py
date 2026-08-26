import base64
import datetime
import hashlib
import hmac
import json
import math
import os
import time
import uuid

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


# 何日ぶんさかのぼって埋め直すか。
# マスターの行は**紙の介護記録をスキャンしたとき**にできる。紙は月単位で
# まとまるので、行ができるのは計測から数週間〜数か月あと。
# 既定を短くすると、結局ほとんど埋まらない。
BACKFILL_DAYS = int(os.environ.get("BACKFILL_DAYS", "120"))


def _has_aggregate(agg_rows, row_number, start_row=2):
    """マスターの U:X に既に値が入っているか。

    **空のときだけ書く**ための判定。既にある値を上書きすると、
    手で直した内容を壊す。
    """
    idx = row_number - start_row
    if idx < 0 or idx >= len(agg_rows):
        return False
    return any(str(c).strip() for c in agg_rows[idx])


def backfill_missing_aggregates(service, spreadsheet_id, telemetry_rows, today,
                                days=None):
    """行ができたあとの日付について、日次集計を埋め直す。

    **なぜ要るか**（2026-08-26・CSI-021）

    `sync_daily_aggregate` は**今日の日付でしか呼ばれない**。だが
    マスターの行ができるのは、紙の介護記録がスキャンされたとき——
    普通は計測より**ずっとあと**。

    その結果、行ができたときには**埋めにいく実行が二度と来ない。**
    計測値は `TempHistory` に残っているのに、**集計だけが永久に書かれない。**
    実際、45日間55回すべてが `master-date-missing` だった。

    **一度きりの機会を逃すと取り返せない処理は、必ず取りこぼす。**

    **時間予算**（CSI-018 の教訓）

    日数ぶんループしても API 呼び出しは増やさない。
    **読み2回・書き1回に固定する**:

      1. `B2:B`（日付列）を1回読む
      2. `U2:X`（集計列）を1回読む
      3. 埋める行をまとめて `batchUpdate` で1回書く

    **空のときだけ書く。** 上書きはしない。
    """
    days = BACKFILL_DAYS if days is None else days
    values_api = service.spreadsheets().values()

    date_rows = values_api.get(
        spreadsheetId=spreadsheet_id,
        range=f"{_sheet_ref(MASTER_SHEET)}!B2:B",
        valueRenderOption="FORMATTED_VALUE",
        fields="values",
    ).execute().get("values", [])

    agg_rows = values_api.get(
        spreadsheetId=spreadsheet_id,
        range=f"{_sheet_ref(MASTER_SHEET)}!U2:X",
        valueRenderOption="FORMATTED_VALUE",
        fields="values",
    ).execute().get("values", [])

    updates = []
    filled_dates = []
    for back in range(1, days + 1):
        day = today - datetime.timedelta(days=back)
        aggregate = aggregate_telemetry_rows(telemetry_rows, day)
        if aggregate is None:
            continue                      # その日の計測値が無い
        matches = _master_row_numbers(date_rows, day)
        if len(matches) != 1:
            continue                      # 行が無い / 重複している日は触らない
        row_number = matches[0]
        if _has_aggregate(agg_rows, row_number):
            continue                      # 既に入っている。**上書きしない**
        updates.append({
            "range": f"{_sheet_ref(MASTER_SHEET)}!U{row_number}:X{row_number}",
            "values": [[
                _format_summary(aggregate),
                aggregate["avg"], aggregate["min"], aggregate["max"],
            ]],
        })
        filled_dates.append(str(day))

    if not updates:
        return {"filled": 0, "dates": []}

    values_api.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": updates},
    ).execute()
    return {"filled": len(updates), "dates": filled_dates}


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


def _signed_headers(token, secret):
    """Build SwitchBot v1.1 auth headers with a fresh timestamp and unique nonce.

    A unique per-request nonce is required: reusing a constant nonce trips
    SwitchBot's replay protection and returns intermittent HTTP 401.
    """
    request_time = str(int(time.time() * 1000))
    nonce = uuid.uuid4().hex
    string_to_sign = f"{token}{request_time}{nonce}".encode("utf-8")
    sign = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            msg=string_to_sign,
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    return {
        "Authorization": token,
        "sign": sign,
        "t": request_time,
        "nonce": nonce,
        "Content-Type": "application/json; charset=utf8",
    }


def _switchbot_status(url, token, secret, attempts=3, timeout=15, deadline=None):
    """GET device status, retrying transient timeouts/connection errors.

    Auth failures (401/4xx) fail fast via raise_for_status (not retried), since
    those indicate a credential/signing problem, not a transient one. Each retry
    re-signs with a fresh timestamp and nonce.

    リトライ予算は、それ単体では成立していても**関数全体の時間には収まらない**。
    2026-08-26 に数えたところ:

        試行1 15秒 + 待機1秒 + 試行2 15秒 + 待機2秒 + 試行3 15秒 + 待機4秒 = **52秒**

    Lambda のタイムアウトは **60秒**。ところが通常の Sheets 処理だけで
    **13〜15秒**かかる。**最悪ケースで残るのは8秒しかなく、本処理が入らない。**

    実際 7/27・7/28・7/29・7/31・8/1・8/2・8/25 に 60秒でタイムアウトし、
    Lambda が自動リトライしていた（重複は `sample_already_logged` が防いだ）。

    ⚠️ **タイムアウトしたリトライは、成果物を残さない。** 60秒使って何も書かず、
    次の実行を待つことになる。**待つくらいなら、早く諦めて1回分を書くほうがいい。**

    `deadline`（`time.monotonic()` 基準の秒）を渡すと、**次の試行が締切を
    超えると分かった時点でリトライをやめる。** 呼び出し側が Lambda の残り時間から
    計算する。渡さなければ従来どおり（テストと手元実行のため）。
    """
    last_exc = None
    for attempt in range(attempts):
        if deadline is not None and time.monotonic() + timeout > deadline:
            # この試行を始めても締切に間に合わない。**始めない。**
            print(
                f"SwitchBot retry budget exhausted: giving up after {attempt} attempt(s) "
                f"to leave time for the Sheets update"
            )
            break
        started = time.monotonic()
        try:
            response = requests.get(url, headers=_signed_headers(token, secret), timeout=timeout)
            response.raise_for_status()
            # **所要時間を残す。** 2026-08-26 時点で、150日のうち約3%が
            # タイムアウトしていたが、**普段どれくらいで返るかを誰も測っていなかった。**
            # タイムアウト15秒が妥当かを判断する材料が無い状態だった。
            # 数字をいじる前に、まず測る。
            print(f"SwitchBot response: {int((time.monotonic() - started) * 1000)}ms "
                  f"attempt={attempt + 1}")
            return response
        except (requests.Timeout, requests.ConnectionError) as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            print(f"SwitchBot failed: {elapsed}ms attempt={attempt + 1} "
                  f"{type(exc).__name__}")
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
    if last_exc is None:
        # 1回も試行せずに締切で抜けた場合
        raise TimeoutError("SwitchBot request skipped: not enough time left in this invocation")
    raise last_exc


# ── 時間予算 ──────────────────────────────────────────────
#
# **守るべき不変条件はひとつ:**
#
#     SHEETS_TIME_RESERVE_SECONDS >= Sheets の実処理時間
#
# SwitchBot に許す時間は「Lambda の残り − 確保分」なので、確保分が
# 実処理より小さいと**必ず溢れる。**
#
# 2026-08-26 の経緯:
#   - 当初 Sheets は13〜15秒。確保25秒で足りていた
#   - **埋め直し（PR #70）を足したら実測 35.7秒になった**（読み+2・書き+1）
#   - 確保25秒のまま → SwitchBot に35秒許して Sheets が34秒 = **69秒**。
#     Lambda のタイムアウト60秒を**9秒超える。**
#     **PR #67 で直した「足し算が合わない」を、自分で作り直していた。**
#
# 対処: 確保を45秒へ、Lambda のタイムアウトを120秒へ（deploy.sh）。
#   SwitchBot に許すのは 120-45 = 75秒。リトライ予算の最大52秒が丸ごと入る。
#   最悪ケース 75+34 = 109秒 < 120秒。
#
# **部品を足したら、足し算をやり直す。**
MEASURED_SHEETS_WORK_SECONDS = 34   # 2026-08-26 実測（埋め直し込み）
SHEETS_TIME_RESERVE_SECONDS = int(os.environ.get("SHEETS_TIME_RESERVE_SECONDS", "45"))


def _switchbot_deadline(context):
    """SwitchBot のリトライに使ってよい締切を、Lambda の残り時間から決める。

    `context` が無い（テスト・手元実行）ときは `None` を返し、従来どおり動く。
    """
    remaining_ms = getattr(context, "get_remaining_time_in_millis", None)
    if not callable(remaining_ms):
        return None
    return time.monotonic() + (remaining_ms() / 1000.0) - SHEETS_TIME_RESERVE_SECONDS


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

        url = f"https://api.switch-bot.com/v1.1/devices/{device_id}/status"
        # Sheets の読み書きに通常13〜15秒かかる。**その分を必ず残す。**
        # 残さないと、SwitchBot のリトライに時間を使い切って関数ごと
        # タイムアウトし、**1件も記録できずに終わる。**
        response = _switchbot_status(
            url, token, secret, deadline=_switchbot_deadline(context)
        )
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
        # AuthorizedHttp は creds を内側に持つ。build() に credentials と http を
        # 両方渡すと googleapiclient が ValueError を投げる:
        #   "Arguments http and credentials are mutually exclusive"
        # 例外は下の except で握られてログに出るだけなので Lambda の Errors は
        # 0 のまま。**毎回この行で落ちて室温が記録されていなかった**
        # （2026-08-21 に発見）。タイムアウトのための http を残し、
        # 重複している credentials を落とす。
        sheets_http = google_auth_httplib2.AuthorizedHttp(
            creds,
            http=httplib2.Http(timeout=SHEETS_HTTP_TIMEOUT),
        )
        service = build(
            "sheets",
            "v4",
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

        # 集計まで終わって初めて「成功」と書く。
        #
        # `master-date-missing` は Master シートに対象日の行が無い状態で、
        # **依頼された仕事（日次の平均・最低・最高の書き込み）が行われていない。**
        # docs/USER_GUIDE.md には対処が書いてあるので想定内の状態ではあるが、
        # 2026-08-26 に CloudWatch を数えたら **45日間・55回すべてこれで、
        # `updated` は0回**だった。それでも行の頭が `Telemetry success` なので、
        # 誰も気づかないまま日次集計が1度も書かれていなかった。
        #
        # 語尾を分けて、grep とメトリクスフィルタで拾えるようにする。
        aggregate_done = aggregate_result["status"] == "updated"
        label = "Telemetry success" if aggregate_done else "Telemetry incomplete"
        # 行があとからできた日の集計を埋め直す（CSI-021）。
        #
        # ⚠️ **本来の処理を終えてから行う。** ここで失敗しても、
        # その回のサンプル記録と当日の集計は既に済んでいる。
        # **補修が本業を巻き込まないようにする。**
        backfill = {"filled": 0, "dates": []}
        try:
            backfill = backfill_missing_aggregates(
                service, spreadsheet_id, telemetry_rows, sample_time.date()
            )
        except Exception as exc:          # noqa: BLE001 - 補修の失敗は本業を止めない
            print(f"Backfill skipped: {exc}")

        print(
            f"{label}: sample={'duplicate' if duplicate else 'logged'} "
            f"aggregate={aggregate_result['status']} "
            f"backfilled={backfill['filled']}"
        )
        if backfill["filled"]:
            print(f"Backfilled aggregates for: {', '.join(backfill['dates'])}")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "sample": "duplicate" if duplicate else "logged",
                "aggregate": aggregate_result["status"],
                "backfilled": backfill["filled"],
            }),
        }

    except Exception as error:
        print(f"Telemetry logging failed: {error}")
        raise
