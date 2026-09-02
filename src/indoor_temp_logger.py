import base64
import datetime
import hashlib
import hmac
import json
import math
import os
import re
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


def _parse_date(value, year=None):
    """Parse a Master Sheet date without relying on the spreadsheet locale.

    `year` を渡すと、年の無い `April 20` 形式も読む（CSI-014）。
    **渡さなければ読まない。**
    """
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

    # 年の無い `April 20` 形式は、**年を渡されたときだけ**読む（CSI-014）。
    # 2026-09-02 の実測で B列の143行がこの形だった。A列に年があることは
    # 診断で確かめてある（`year_in_column={"A":143}` / `years_by_column={"A":[2026]}`）。
    # **年が無ければ読まない。** 推測して埋めると別の年の行に集計を書き込み、
    # 空欄で残すより悪くなる。
    if year is not None:
        parsed = _parse_month_day(text)
        if parsed is not None:
            month, day = parsed
            try:
                return datetime.date(year, month, day)
            except ValueError:
                return None
    return None


# 月名は**表で持つ**。`strptime("%B")` はロケール依存で、Lambda と手元で
# 挙動が変わりうる。この関数の元の docstring も
# 「スプレッドシートのロケールに依存しない」ことを目的に書かれている。
_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("january", "jan"), ("february", "feb"), ("march", "mar"),
            ("april", "apr"), ("may",), ("june", "jun"),
            ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"),
            ("october", "oct"), ("november", "nov"), ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}

_MONTH_DAY_RE = re.compile(r"^([A-Za-z]+)\.?\s+(\d{1,2})$")


def _parse_month_day(text):
    """`April 20` `Apr. 5` から (月, 日) を取り出す。読めなければ None。"""
    match = _MONTH_DAY_RE.match(text.strip())
    if not match:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    return month, int(match.group(2))


def _year_from_cell(value):
    """A列の値から年を取り出す。4桁の年に見えなければ None（＝推測しない）。"""
    match = _YEAR_RE.search(str(value or ""))
    return int(match.group()) if match else None


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


def _summarize(temperatures):
    """気温のリストから、日次の件数・平均・最低・最高を作る。"""
    if not temperatures:
        return None

    return {
        "count": len(temperatures),
        "avg": round(sum(temperatures) / len(temperatures), 2),
        "min": round(min(temperatures), 2),
        "max": round(max(temperatures), 2),
    }


def group_telemetry_by_date(rows):
    """TempHistory を**1回だけ**走査して、日付→気温リスト にまとめる。

    **なぜ要るか**（2026-08-31）

    埋め直しは 120 日ぶんループする。日ごとに全行を舐め直すと
    120×全行になり、実行時間が 3秒→36秒へ伸びて、120秒の上限に
    ときどき届いていた（`ParkinSync_IndoorTemp_Logger-Errors` が
    8/25・8/27・8/28・8/31 に発報）。**日数を増やしても走査は1回。**
    """
    by_date = {}
    for row in rows:
        if len(row) < 2:
            continue
        timestamp = _parse_timestamp(row[0])
        temperature = _temperature(row[1])
        if timestamp and temperature is not None:
            by_date.setdefault(timestamp.date(), []).append(temperature)
    return by_date


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

    return _summarize(temperatures)


def _master_row_numbers(date_rows, target_date, start_row=2):
    """Find all Master Sheet row numbers matching the requested date.

    `date_rows` は **A:B**（A=年・B=日付）。年の無い `April 20` 形式のために
    A列を渡す（CSI-014）。
    """
    target = _parse_date(target_date)
    if target is None:
        raise ValueError("target_date must be a supported calendar date")

    return [
        index
        for index, row in enumerate(date_rows, start=start_row)
        if len(row) > 1
        and _parse_date(row[1], year=_year_from_cell(row[0])) == target
    ]


def index_master_dates(date_rows, start_row=2):
    """A:B を**1回だけ**走査して、日付→行番号 の対応を作る（A=年・B=日付）。

    **読めなかったセルも数えて返す**（CSI-014）。日次集計は45日間ずっと
    `master-date-missing` で、残っていた問いが「Master に対象日の行が
    無いのはなぜか」だった。`_parse_date` が読めるのは `%Y-%m-%d`
    `%Y/%m/%d` `%m/%d/%Y` `%m/%d/%y` だけで、`2026年8月26日` は読めない。
    **行が無いのか、読めていないだけなのかは、数えれば分かる** ——
    シートを開かずに。
    """
    by_date = {}
    unparsed = 0
    samples = []
    for row_number, row in enumerate(date_rows, start=start_row):
        text = str((row[1] if len(row) > 1 else "") or "").strip()
        if not text:
            continue
        # A列の年を渡す。**年が取れなければ渡さない**＝ `April 20` は読まない。
        parsed = _parse_date(text, year=_year_from_cell(row[0] if row else ""))
        if parsed is None:
            unparsed += 1
            if len(samples) < 3:
                samples.append(text[:20])
            continue
        by_date.setdefault(parsed, []).append(row_number)
    return {"by_date": by_date, "unparsed": unparsed, "samples": samples}


# `April 20` のような**年の無い**日付から、年をどこで引けばよいかを探すための診断。
#
# なぜ要るか（CSI-014・2026-09-02）: B列の143行が `April 20` 形式で、
# `_parse_date` が読めない。年を推測して埋めると**別の年の行に集計を書き込む**ので、
# 空欄のまま残すより悪い。**まず「年がどこかに書いてあるか」を確かめる。**
#
# ⚠️ これは**一時的な診断**。年の決め方が決まったら消す。
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")

# 走査する列（A..F）。B は日付そのものなので候補から外す。
_YEAR_SCAN_RANGE = "A2:F"
_DATE_COL = 1  # A2:F の中で B 列の位置


def _shape_of(text):
    """値の**形**だけを返す。数字→9・英字→A・その他の文字→#。

    ⚠️ **中身は返さない。** 形が分かればパーサは書ける。
    2026-09-02 に `unparsed_samples` の3件（`April 20`）だけを見て
    「143行すべてが同じ形」と判断し、外した。**分布を数えないと分からない。**
    """
    out = []
    for ch in text[:24]:
        if ch.isdigit():
            out.append("9")
        elif ch.isascii() and ch.isalpha():
            out.append("A")
        elif ch.isspace():
            out.append(" ")
        elif ch.isascii():
            out.append(ch)
        else:
            out.append("#")
    return "".join(out)


def diagnose_year_source(rows, date_col=_DATE_COL, start_row=2):
    """読めない日付行の「年」が、隣の列から取れそうかを数える。

    ⚠️ **セルの値そのものは返さない。** この行には介護記録が並んでいる。
    判定に要るのは「年らしき4桁があるか」と「それが何年か」だけで、
    中身は要らない。**診断のためにケア情報をログへ出さない。**

    返すもの:
      unparsed_rows      読めなかった行数
      parsed_years       読めた日付の年ごとの件数（年は個人情報ではない）
      year_in_column     列名 -> その列に年らしき値があった「読めない行」の数
      years_by_column    列名 -> その列に見つかった年の一覧（昇順）

    ⚠️ 年は**列ごとに分ける**。まとめると、介護記録の中のたまたま4桁の数字
    （2026-09-02 の実測では C列に8件・F列に1件）が、日付列の年と混ざって
    「2000 と 2030 も見えている」ように出る。**どの列を読めばよいかが決められない。**
      unparsed_row_span  読めない行の最初と最後の行番号
      unparsed_shapes    読めない値の**形**ごとの件数（多い順・上位8件）
      unparsed_charset   読めない値に出てくる数字以外の文字（重複なし・最大40）
      unparsed_charset_size  その文字の総数（上の一覧が切れているかが分かる）
    """
    columns = "ABCDEF"
    unparsed_rows = 0
    parsed_years = {}
    year_in_column = {}
    years_by_column = {}
    shapes = {}
    charset = set()
    first_row = last_row = None

    for offset, row in enumerate(rows):
        row_number = start_row + offset
        text = str((row[date_col] if len(row) > date_col else "") or "").strip()
        if not text:
            continue
        # **backfill と同じ条件で数える**（A列の年を渡す）。揃えないと
        # 「診断では143・本処理では138」のように食い違い、どちらが本当か分からない。
        year_here = _year_from_cell(row[0] if row else "")
        parsed = _parse_date(text, year=year_here)
        if parsed is not None:
            parsed_years[parsed.year] = parsed_years.get(parsed.year, 0) + 1
            continue

        unparsed_rows += 1
        shape = _shape_of(text)
        shapes[shape] = shapes.get(shape, 0) + 1
        # 形だけでは区切り文字が特定できなかった（2026-09-02）。
        # **日付欄に出てくる数字以外の文字**を集める。区切り記号や月名の一部で、
        # ケアの記述ではない。パーサを書くにはこれが要る。
        charset.update(ch for ch in text[:24] if not ch.isdigit() and not ch.isspace())
        first_row = row_number if first_row is None else first_row
        last_row = row_number
        for index, value in enumerate(row):
            if index == date_col or index >= len(columns):
                continue
            match = _YEAR_RE.search(str(value or ""))
            if not match:
                continue
            name = columns[index]
            year_in_column[name] = year_in_column.get(name, 0) + 1
            years_by_column.setdefault(name, set()).add(int(match.group()))

    return {
        "unparsed_rows": unparsed_rows,
        "parsed_years": dict(sorted(parsed_years.items())),
        "year_in_column": dict(sorted(year_in_column.items())),
        "years_by_column": {k: sorted(v) for k, v in sorted(years_by_column.items())},
        "unparsed_row_span": [first_row, last_row] if first_row is not None else [],
        "unparsed_shapes": dict(sorted(shapes.items(), key=lambda kv: -kv[1])[:8]),
        # 上限で切れていることが分からないと、「A〜P しか無い」と誤読する。
        # **切り詰めた一覧を出すときは、必ず総数も出す。**
        "unparsed_charset": sorted(charset)[:40],
        "unparsed_charset_size": len(charset),
    }


def fetch_year_source_diagnosis(service, spreadsheet_id):
    """A..F を1回読んで診断する。**本業とは別に、失敗しても止めない。**"""
    rows = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{_sheet_ref(MASTER_SHEET)}!{_YEAR_SCAN_RANGE}",
        valueRenderOption="FORMATTED_VALUE",
        fields="values",
    ).execute().get("values", [])
    return diagnose_year_source(rows)


def _format_summary(aggregate):
    return (
        f"Avg:{aggregate['avg']:.2f}/Min:{aggregate['min']:.2f}/"
        f"Max:{aggregate['max']:.2f}"
    )


# 何日ぶんさかのぼって埋め直すか。
# マスターの行は**紙の介護記録をスキャンしたとき**にできる。紙は月単位で
# まとまるので、行ができるのは計測から数週間〜数か月あと。
# 既定を短くすると、結局ほとんど埋まらない。
#
# ⚠️ **120日では足りなかった**（2026-09-02・CSI-014）。
# CSI-020 の実測で、紙のアップロードから取り込みまで **115〜122日**かかっていた。
# 窓（120日）と遅れ（115〜122日）がほぼ同じ大きさで、**行ができた頃には
# 窓を出ている**。実際、直近120日で計測値のある98日のうち、Master に行が
# あったのは1日だけだった。
#
# 走査は日数に比例するだけ（引き当ての表はループの外で1回作る・2026-08-31）。
# API 呼び出しは日数によらず読み2回・書き1回で固定。**広げても安い。**
BACKFILL_DAYS = int(os.environ.get("BACKFILL_DAYS", "400"))


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

    **API を固定しても、走査までは固定されない**（2026-08-31）。
    初版は日ごとに全行を舐め直していたので 120×全行になり、実行時間が
    3秒→36秒へ伸びて 120秒の上限にときどき届いた。**引き当ての表は
    ループの外で1回だけ**作る。
    """
    days = BACKFILL_DAYS if days is None else days
    values_api = service.spreadsheets().values()

    date_rows = values_api.get(
        spreadsheetId=spreadsheet_id,
        range=f"{_sheet_ref(MASTER_SHEET)}!A2:B",
        valueRenderOption="FORMATTED_VALUE",
        fields="values",
    ).execute().get("values", [])

    agg_rows = values_api.get(
        spreadsheetId=spreadsheet_id,
        range=f"{_sheet_ref(MASTER_SHEET)}!U2:X",
        valueRenderOption="FORMATTED_VALUE",
        fields="values",
    ).execute().get("values", [])

    # 引き当てに使う表を**先に1回だけ**作る。
    master = index_master_dates(date_rows)
    telemetry_by_date = group_telemetry_by_date(telemetry_rows)
    diagnostics = {
        "master_dates": len(master["by_date"]),
        "unparsed_dates": master["unparsed"],
        "unparsed_samples": master["samples"],
    }

    updates = []
    filled_dates = []
    # **本当の健全性はここで数える。**（CSI-014・2026-09-02）
    # 「読めない行が何行あるか」は健全性ではない。日付でない行が混ざっていれば
    # 減らないし、減らなくても集計は埋まっている。**知りたいのは
    # 「計測値があるのに集計が書かれていない日が何日あるか」**。
    coverage = {"with_telemetry": 0, "row_found": 0, "already_filled": 0,
                "row_missing": 0, "row_duplicated": 0}

    for back in range(1, days + 1):
        day = today - datetime.timedelta(days=back)
        temperatures = telemetry_by_date.get(day)
        if not temperatures:
            continue                      # その日の計測値が無い
        coverage["with_telemetry"] += 1
        matches = master["by_date"].get(day, ())
        if len(matches) != 1:
            # 行が無い / 重複している日は触らない
            key = "row_duplicated" if len(matches) > 1 else "row_missing"
            coverage[key] += 1
            continue
        coverage["row_found"] += 1
        row_number = matches[0]
        if _has_aggregate(agg_rows, row_number):
            coverage["already_filled"] += 1
            continue                      # 既に入っている。**上書きしない**
        aggregate = _summarize(temperatures)
        updates.append({
            "range": f"{_sheet_ref(MASTER_SHEET)}!U{row_number}:X{row_number}",
            "values": [[
                _format_summary(aggregate),
                aggregate["avg"], aggregate["min"], aggregate["max"],
            ]],
        })
        filled_dates.append(str(day))

    if not updates:
        # ⚠️ **早い戻り道にも同じものを載せる。** 片方だけに診断値を載せると、
        # 「何も埋めなかったとき」＝いちばん知りたいときに限って見えなくなる。
        return {"filled": 0, "dates": [], "coverage": coverage, **diagnostics}

    values_api.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": updates},
    ).execute()
    return {"filled": len(updates), "dates": filled_dates,
            "coverage": coverage, **diagnostics}


def sync_daily_aggregate(service, spreadsheet_id, telemetry_rows, target_date):
    """Update U:X only when exactly one Master Sheet date row exists."""
    aggregate = aggregate_telemetry_rows(telemetry_rows, target_date)
    if aggregate is None:
        return {"status": "no-valid-samples", "target_date": str(target_date)}

    values_api = service.spreadsheets().values()
    date_response = values_api.get(
        spreadsheetId=spreadsheet_id,
        range=f"{_sheet_ref(MASTER_SHEET)}!A2:B",
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
        elif not aggregate_done:
            # **なぜ埋まらなかったのか**を残す（CSI-014 に残っていた問い）。
            # 行が無いのか、B列の書式が読めていないのかで、次の手が変わる。
            print(
                "Backfill filled nothing: "
                f"master_dates={backfill.get('master_dates', 0)} "
                f"unparsed_dates={backfill.get('unparsed_dates', 0)} "
                f"coverage={json.dumps(backfill.get('coverage', {}), ensure_ascii=False)}"
            )
            # 読めない行があるなら、**年がどこかに書いてあるか**まで見る。
            # `April 20` には年が無く、推測して埋めると別の年の行を壊す。
            # ⚠️ 一時的な診断。年の決め方が決まったら消す（CSI-014）。
            if backfill.get("unparsed_dates", 0) > 0:
                try:
                    diag = fetch_year_source_diagnosis(service, spreadsheet_id)
                    print(f"Year source diagnosis: {json.dumps(diag, ensure_ascii=False)}")
                except Exception as exc:      # noqa: BLE001 - 診断は本業を止めない
                    print(f"Year source diagnosis skipped: {exc}")
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
