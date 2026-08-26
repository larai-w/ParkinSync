import contextlib
import datetime
import io
import time

import requests
import json
import unittest
from unittest.mock import MagicMock, patch

import indoor_temp_logger as logger


class TestTelemetryAggregation(unittest.TestCase):

    def test_aggregates_only_valid_rows_for_target_date(self):
        rows = [
            ["Timestamp", "Temperature"],
            ["2026-04-20 00:00", 20.0],
            ["2026/04/20 03:00", "22.5"],
            ["2026-04-20 06:00", "invalid"],
            ["2026-04-21 00:00", 99.0],
            ["2026-04-20 09:00", float("nan")],
        ]

        result = logger.aggregate_telemetry_rows(rows, "2026-04-20")

        self.assertEqual(result, {"count": 2, "avg": 21.25, "min": 20.0, "max": 22.5})

    def test_returns_none_when_date_has_no_valid_samples(self):
        rows = [["2026-04-20 00:00", "invalid"]]
        self.assertIsNone(logger.aggregate_telemetry_rows(rows, "2026-04-20"))

    def test_measurement_time_is_converted_to_jst(self):
        now = datetime.datetime(2026, 4, 20, 18, 30, tzinfo=datetime.timezone.utc)
        result = logger.current_sample_time(now)
        self.assertEqual(result.isoformat(), "2026-04-21T03:30:00+09:00")

    def test_retry_event_id_is_detected_as_duplicate(self):
        sample_time = datetime.datetime(2026, 4, 20, 9, 0, tzinfo=logger.JST)
        rows = [["2026/04/20 09:00", 20.0, "event-123"]]
        self.assertTrue(logger.sample_already_logged(rows, "event-123", sample_time))

    def test_manual_call_uses_minute_as_duplicate_fallback(self):
        sample_time = datetime.datetime(2026, 4, 20, 9, 1, tzinfo=logger.JST)
        rows = [["2026-04-20 09:01", 20.0]]
        self.assertTrue(logger.sample_already_logged(rows, "", sample_time))


class TestMasterSynchronization(unittest.TestCase):

    def _service(self, date_rows):
        service = MagicMock()
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.get.return_value.execute.return_value = {"values": date_rows}
        values_api.update.return_value.execute.return_value = {}
        return service, values_api

    def test_updates_only_switchbot_columns_for_one_matching_date(self):
        service, values_api = self._service([["2026/04/19"], ["2026/04/20"]])
        telemetry = [
            ["2026-04-20 00:00", 20.0],
            ["2026-04-20 03:00", 22.0],
        ]

        result = logger.sync_daily_aggregate(
            service, "sheet-id", telemetry, datetime.date(2026, 4, 20)
        )

        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["sample_count"], 2)
        values_api.update.assert_called_once_with(
            spreadsheetId="sheet-id",
            range="'Sheet1'!U3:X3",
            valueInputOption="RAW",
            body={"values": [["Avg:21.00/Min:20.00/Max:22.00", 21.0, 20.0, 22.0]]},
        )

    def test_missing_master_date_does_not_write(self):
        service, values_api = self._service([["2026/04/19"]])
        telemetry = [["2026-04-20 00:00", 20.0]]

        result = logger.sync_daily_aggregate(
            service, "sheet-id", telemetry, "2026-04-20"
        )

        self.assertEqual(result["status"], "master-date-missing")
        values_api.update.assert_not_called()

    def test_duplicate_master_date_does_not_write(self):
        service, values_api = self._service([["2026-04-20"], ["2026/04/20"]])
        telemetry = [["2026-04-20 00:00", 20.0]]

        result = logger.sync_daily_aggregate(
            service, "sheet-id", telemetry, "2026-04-20"
        )

        self.assertEqual(result["status"], "duplicate-master-date")
        values_api.update.assert_not_called()


class TestTelemetryHandler(unittest.TestCase):

    @patch("indoor_temp_logger.boto3.client")
    def test_dependency_failure_is_reraised(self, mock_boto):
        mock_boto.side_effect = RuntimeError("dependency unavailable")

        with self.assertRaisesRegex(RuntimeError, "dependency unavailable"):
            logger.lambda_handler({"id": "event-123"}, None)

    @patch("indoor_temp_logger.build")
    @patch("indoor_temp_logger.service_account.Credentials.from_service_account_info")
    @patch("indoor_temp_logger.requests.get")
    @patch("indoor_temp_logger.boto3.client")
    @patch("indoor_temp_logger.current_sample_time")
    def test_logs_sample_and_updates_daily_master_aggregate(
        self, mock_sample_time, mock_boto, mock_get, mock_credentials, mock_build
    ):
        mock_sample_time.return_value = datetime.datetime(
            2026, 4, 20, 9, 0, tzinfo=logger.JST
        )
        secrets_client = MagicMock()
        secrets_client.get_secret_value.return_value = {
            "SecretString": (
                '{"SWITCHBOT_TOKEN":"token","SWITCHBOT_SECRET":"secret",'
                '"SWITCHBOT_DEVICE_ID":"device","GOOGLE_SHEET_ID":"sheet-id"}'
            )
        }
        mock_boto.return_value = secrets_client

        switchbot_response = MagicMock()
        switchbot_response.json.return_value = {"body": {"temperature": 20.5}}
        mock_get.return_value = switchbot_response

        service = MagicMock()
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.get.return_value.execute.side_effect = [
            {"values": []},
            {"values": [["2026-04-20"]]},
        ]
        values_api.append.return_value.execute.return_value = {}
        values_api.update.return_value.execute.return_value = {}
        mock_build.return_value = service
        mock_credentials.return_value = MagicMock()

        result = logger.lambda_handler({"id": "event-123"}, None)

        # build() は googleapiclient の実物ではなくモック。**モックは何でも
        # 受け取るので、引数が不正でも通ってしまう。** 実際 2026-08-14 以降、
        # 本番では毎回 ValueError で落ちていたのにここは緑だった。
        # 呼び出し引数そのものを検査する。
        build_kwargs = mock_build.call_args.kwargs
        self.assertNotIn(
            "credentials", build_kwargs,
            "build() に credentials と http を両方渡すと googleapiclient が "
            "ValueError を投げる（http と credentials は排他）。"
            "AuthorizedHttp が既に creds を持っている",
        )
        self.assertIn("http", build_kwargs, "タイムアウト付きの http を渡すこと")

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(json.loads(result["body"])["aggregate"], "updated")
        values_api.append.assert_called_once_with(
            spreadsheetId="sheet-id",
            range="'TempHistory'!A:C",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [["2026-04-20 09:00", 20.5, "event-123"]]},
        )
        values_api.update.assert_called_once_with(
            spreadsheetId="sheet-id",
            range="'Sheet1'!U2:X2",
            valueInputOption="RAW",
            body={"values": [["Avg:20.50/Min:20.50/Max:20.50", 20.5, 20.5, 20.5]]},
        )

    @patch("indoor_temp_logger.build")
    @patch("indoor_temp_logger.service_account.Credentials.from_service_account_info")
    @patch("indoor_temp_logger.requests.get")
    @patch("indoor_temp_logger.boto3.client")
    @patch("indoor_temp_logger.current_sample_time")
    def test_retry_skips_append_and_refreshes_aggregate(
        self, mock_sample_time, mock_boto, mock_get, mock_credentials, mock_build
    ):
        mock_sample_time.return_value = datetime.datetime(
            2026, 4, 20, 9, 0, tzinfo=logger.JST
        )
        secrets_client = MagicMock()
        secrets_client.get_secret_value.return_value = {
            "SecretString": (
                '{"SWITCHBOT_TOKEN":"token","SWITCHBOT_SECRET":"secret",'
                '"SWITCHBOT_DEVICE_ID":"device","GOOGLE_SHEET_ID":"sheet-id"}'
            )
        }
        mock_boto.return_value = secrets_client

        switchbot_response = MagicMock()
        switchbot_response.json.return_value = {"body": {"temperature": 20.5}}
        mock_get.return_value = switchbot_response

        service = MagicMock()
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.get.return_value.execute.side_effect = [
            {"values": [["2026-04-20 09:00", 20.5, "event-123"]]},
            {"values": [["2026-04-20"]]},
        ]
        values_api.update.return_value.execute.return_value = {}
        mock_build.return_value = service
        mock_credentials.return_value = MagicMock()

        result = logger.lambda_handler({"id": "event-123"}, None)

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(json.loads(result["body"])["sample"], "duplicate")
        values_api.append.assert_not_called()
        values_api.update.assert_called_once()

    @patch("indoor_temp_logger.build")
    @patch("indoor_temp_logger.service_account.Credentials.from_service_account_info")
    @patch("indoor_temp_logger.requests.get")
    @patch("indoor_temp_logger.boto3.client")
    @patch("indoor_temp_logger.current_sample_time")
    def test_missing_master_row_is_not_logged_as_success(
        self, mock_sample_time, mock_boto, mock_get, mock_credentials, mock_build
    ):
        """集計が書けなかった実行を「成功」と書かない。

        Master シートに対象日の行が無いと `sync_daily_aggregate` は
        `master-date-missing` を返し、**日次の平均・最低・最高は書かれない。**
        docs/USER_GUIDE.md に対処が書いてある想定内の状態だが、
        **依頼された仕事は行われていない。**

        2026-08-26 に CloudWatch を数えたところ、45日間の55回すべてが
        これで、`updated` は0回だった。**それでも行の頭が
        `Telemetry success` だったので、誰も気づかなかった。**

        ログを読む人と grep の両方が気づけるように、語を分けたことを固定する。
        """
        mock_sample_time.return_value = datetime.datetime(
            2026, 4, 20, 9, 0, tzinfo=logger.JST
        )
        secrets_client = MagicMock()
        secrets_client.get_secret_value.return_value = {
            "SecretString": (
                '{"SWITCHBOT_TOKEN":"token","SWITCHBOT_SECRET":"secret",'
                '"SWITCHBOT_DEVICE_ID":"device","GOOGLE_SHEET_ID":"sheet-id"}'
            )
        }
        mock_boto.return_value = secrets_client

        switchbot_response = MagicMock()
        switchbot_response.json.return_value = {"body": {"temperature": 20.5}}
        mock_get.return_value = switchbot_response

        service = MagicMock()
        values_api = service.spreadsheets.return_value.values.return_value
        # 2本目の get が Master シートの日付列。**対象日の行が無い。**
        values_api.get.return_value.execute.side_effect = [
            {"values": []},
            {"values": [["2026-04-19"]]},
        ]
        values_api.append.return_value.execute.return_value = {}
        mock_build.return_value = service
        mock_credentials.return_value = MagicMock()

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            result = logger.lambda_handler({"id": "event-123"}, None)
        printed = captured.getvalue()

        # 集計は書かれていない
        self.assertEqual(json.loads(result["body"])["aggregate"], "master-date-missing")
        values_api.update.assert_not_called()

        # **ここが本題。** 成功と書かない
        self.assertNotIn(
            "Telemetry success",
            printed,
            "集計が書けていないのに success と記録している（45日間これを見逃した）",
        )
        self.assertIn("Telemetry incomplete", printed, printed)
        self.assertIn("aggregate=master-date-missing", printed, printed)

    @patch("indoor_temp_logger.build")
    @patch("indoor_temp_logger.service_account.Credentials.from_service_account_info")
    @patch("indoor_temp_logger.requests.get")
    @patch("indoor_temp_logger.boto3.client")
    @patch("indoor_temp_logger.current_sample_time")
    def test_completed_run_still_says_success(
        self, mock_sample_time, mock_boto, mock_get, mock_credentials, mock_build
    ):
        """語を分けた結果、正常な実行まで incomplete にしていないか。

        **片方だけ確かめても意味がない。** 成功側も固定する。
        """
        mock_sample_time.return_value = datetime.datetime(
            2026, 4, 20, 9, 0, tzinfo=logger.JST
        )
        secrets_client = MagicMock()
        secrets_client.get_secret_value.return_value = {
            "SecretString": (
                '{"SWITCHBOT_TOKEN":"token","SWITCHBOT_SECRET":"secret",'
                '"SWITCHBOT_DEVICE_ID":"device","GOOGLE_SHEET_ID":"sheet-id"}'
            )
        }
        mock_boto.return_value = secrets_client

        switchbot_response = MagicMock()
        switchbot_response.json.return_value = {"body": {"temperature": 20.5}}
        mock_get.return_value = switchbot_response

        service = MagicMock()
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.get.return_value.execute.side_effect = [
            {"values": []},
            {"values": [["2026-04-20"]]},
        ]
        values_api.append.return_value.execute.return_value = {}
        values_api.update.return_value.execute.return_value = {}
        mock_build.return_value = service
        mock_credentials.return_value = MagicMock()

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            logger.lambda_handler({"id": "event-123"}, None)
        printed = captured.getvalue()

        self.assertIn("Telemetry success", printed, printed)
        self.assertNotIn("Telemetry incomplete", printed, printed)


class TestRetryTimeBudget(unittest.TestCase):
    """リトライ予算が、関数全体の時間に収まることを固定する。

    2026-08-26 に数えて分かったこと:

        試行1 15秒 + 待機1秒 + 試行2 15秒 + 待機2秒 + 試行3 15秒 + 待機4秒 = **52秒**

    Lambda のタイムアウトは **60秒**。通常の Sheets 処理だけで **13〜15秒**。
    **最悪ケースで残るのは8秒しかなく、本処理が入らない。**

    実際 7/27・7/28・7/29・7/31・8/1・8/2・8/25 に60秒でタイムアウトしていた。

    **どちらの部品も、単体では正しかった。** リトライは3回が妥当で、
    タイムアウト15秒も妥当。**足し算だけが誰も見ていなかった。**
    """

    def test_the_numbers_cannot_coexist_without_a_deadline(self):
        """締切が無いと、リトライ予算だけで Lambda の時間を食い潰す。

        この計算が変わったら（試行回数・タイムアウト・待機のどれかを触ったら）
        ここが落ちる。**落ちたら足し算をやり直すこと。**
        """
        attempts, timeout = 3, 15
        worst = sum(timeout + 2 ** a for a in range(attempts))
        lambda_timeout = 60
        typical_sheets_work = 15

        self.assertGreater(
            worst + typical_sheets_work,
            lambda_timeout,
            "前提が変わった。リトライ予算が関数の時間に収まるなら、このテストは不要",
        )
        self.assertLess(
            logger.SHEETS_TIME_RESERVE_SECONDS,
            lambda_timeout,
            "Sheets 用の確保が Lambda のタイムアウトを超えている",
        )
        self.assertGreaterEqual(
            logger.SHEETS_TIME_RESERVE_SECONDS,
            typical_sheets_work,
            "Sheets の通常処理（約15秒）より確保が少ない。足りない",
        )

    def test_retry_stops_before_eating_the_sheets_budget(self):
        """締切を渡すと、Sheets の分を残して諦める。

        **タイムアウトしたリトライは成果物を残さない。** 60秒使って何も書かず
        次の実行を待つより、**早く諦めて1回分を書く**ほうがいい。
        """
        calls = []

        def slow_get(*args, **kwargs):
            calls.append(1)
            raise requests.Timeout("simulated")

        # 残り20秒しかない状況。1回の試行(15秒)を始めたら確保分を割る
        deadline = time.monotonic() + 5
        with patch("indoor_temp_logger.requests.get", side_effect=slow_get):
            with self.assertRaises((requests.Timeout, TimeoutError)):
                logger._switchbot_status("u", "t", "s", deadline=deadline)

        self.assertEqual(
            calls, [],
            "締切を超えると分かっているのに試行を始めている",
        )

    def test_no_deadline_keeps_the_old_behaviour(self):
        """締切を渡さなければ従来どおり（テスト・手元実行のため）。"""
        calls = []

        def failing(*args, **kwargs):
            calls.append(1)
            raise requests.ConnectionError("simulated")

        with patch("indoor_temp_logger.requests.get", side_effect=failing):
            with patch("indoor_temp_logger.time.sleep"):   # 待機は飛ばす
                with self.assertRaises(requests.ConnectionError):
                    logger._switchbot_status("u", "t", "s")

        self.assertEqual(len(calls), 3, "試行回数が変わっている")

    def test_deadline_comes_from_the_lambda_context(self):
        """締切は Lambda の残り時間から計算する。決め打ちにしない。"""
        class Ctx:
            def get_remaining_time_in_millis(self):
                return 60_000

        before = time.monotonic()
        deadline = logger._switchbot_deadline(Ctx())
        self.assertIsNotNone(deadline)
        # 60秒 - 確保分 の位置にあること（実行時間ぶんの誤差を許容）
        expected = before + 60 - logger.SHEETS_TIME_RESERVE_SECONDS
        self.assertAlmostEqual(deadline, expected, delta=1.0)

        self.assertIsNone(
            logger._switchbot_deadline(None),
            "context が無いときは締切なし（従来どおり）にすること",
        )


class TestBackfillMissingAggregates(unittest.TestCase):
    """行があとからできた日の集計を埋め直す（CSI-021）。

    `sync_daily_aggregate` は**今日の日付でしか呼ばれない**。だがマスターの
    行ができるのは、紙の介護記録がスキャンされたとき——普通は計測より
    ずっとあと。その結果、行ができたときには**埋めにいく実行が二度と来ない。**

    計測値は `TempHistory` に残っているのに、**集計だけが永久に書かれない。**
    実際、45日間55回すべてが `master-date-missing` だった。
    """

    TODAY = datetime.date(2026, 4, 20)

    def _service(self, date_rows, agg_rows):
        service = MagicMock()
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.get.return_value.execute.side_effect = [
            {"values": date_rows},
            {"values": agg_rows},
        ]
        values_api.batchUpdate.return_value.execute.return_value = {}
        return service, values_api

    def _telemetry(self, *dates):
        rows = []
        for d in dates:
            rows.append([f"{d} 09:00", 20.0, f"e-{d}-1"])
            rows.append([f"{d} 12:00", 24.0, f"e-{d}-2"])
        return rows

    def test_fills_a_day_whose_row_appeared_later(self):
        """行ができた過去の日を埋める。**これができないと永久に空のまま。**"""
        service, values_api = self._service(
            date_rows=[["2026-04-18"], ["2026-04-19"]],
            agg_rows=[[], []],                      # U:X は空
        )
        result = logger.backfill_missing_aggregates(
            service, "sheet-id", self._telemetry("2026-04-19"), self.TODAY, days=5
        )
        self.assertEqual(result["filled"], 1, result)
        self.assertEqual(result["dates"], ["2026-04-19"])

        call = values_api.batchUpdate.call_args.kwargs
        data = call["body"]["data"]
        self.assertEqual(len(data), 1)
        # 2行目が 2026-04-18、3行目が 2026-04-19
        self.assertEqual(data[0]["range"], "'Sheet1'!U3:X3")
        self.assertEqual(data[0]["values"][0][1:], [22.0, 20.0, 24.0])

    def test_never_overwrites_an_existing_aggregate(self):
        """既に入っている値を上書きしない。

        **手で直した内容を壊さない。** 埋め直しは「空を埋める」だけ。
        """
        service, values_api = self._service(
            date_rows=[["2026-04-19"]],
            agg_rows=[["Avg:99.00/Min:99.00/Max:99.00", 99, 99, 99]],
        )
        result = logger.backfill_missing_aggregates(
            service, "sheet-id", self._telemetry("2026-04-19"), self.TODAY, days=5
        )
        self.assertEqual(result["filled"], 0)
        values_api.batchUpdate.assert_not_called()

    def test_skips_days_without_telemetry(self):
        """計測値が無い日は触らない。"""
        service, values_api = self._service(
            date_rows=[["2026-04-19"]], agg_rows=[[]]
        )
        result = logger.backfill_missing_aggregates(
            service, "sheet-id", [], self.TODAY, days=5
        )
        self.assertEqual(result["filled"], 0)
        values_api.batchUpdate.assert_not_called()

    def test_skips_duplicate_master_rows(self):
        """同じ日付の行が2つあるときは触らない。

        どちらに書くべきか決められない。**迷ったら書かない。**
        """
        service, values_api = self._service(
            date_rows=[["2026-04-19"], ["2026-04-19"]],
            agg_rows=[[], []],
        )
        result = logger.backfill_missing_aggregates(
            service, "sheet-id", self._telemetry("2026-04-19"), self.TODAY, days=5
        )
        self.assertEqual(result["filled"], 0)
        values_api.batchUpdate.assert_not_called()

    def test_api_calls_do_not_grow_with_the_number_of_days(self):
        """日数を増やしても API 呼び出しを増やさない。

        **CSI-018 の教訓。** リトライ予算が Lambda の時間に収まらず
        60秒でタイムアウトしていた。**足し算を先に確かめる。**

        読み2回・書き1回に固定されていること。
        """
        dates = [f"2026-03-{d:02d}" for d in range(1, 29)]
        service, values_api = self._service(
            date_rows=[[d] for d in dates],
            agg_rows=[[] for _ in dates],
        )
        logger.backfill_missing_aggregates(
            service, "sheet-id", self._telemetry(*dates), self.TODAY, days=120
        )
        self.assertEqual(values_api.get.call_count, 2,
                         "読み取りが2回を超えている。日数に比例して増やさない")
        self.assertEqual(values_api.batchUpdate.call_count, 1,
                         "書き込みが1回を超えている。まとめて書くこと")

    def test_fills_many_days_in_one_write(self):
        """複数日ぶんを1回の書き込みでまとめる。"""
        dates = ["2026-04-17", "2026-04-18", "2026-04-19"]
        service, values_api = self._service(
            date_rows=[[d] for d in dates],
            agg_rows=[[] for _ in dates],
        )
        result = logger.backfill_missing_aggregates(
            service, "sheet-id", self._telemetry(*dates), self.TODAY, days=10
        )
        self.assertEqual(result["filled"], 3)
        self.assertEqual(len(values_api.batchUpdate.call_args.kwargs["body"]["data"]), 3)

    def test_today_is_not_backfilled(self):
        """当日は `sync_daily_aggregate` の担当。**二重に書かない。**"""
        service, values_api = self._service(
            date_rows=[["2026-04-20"]], agg_rows=[[]]
        )
        result = logger.backfill_missing_aggregates(
            service, "sheet-id", self._telemetry("2026-04-20"), self.TODAY, days=5
        )
        self.assertEqual(result["filled"], 0)
        values_api.batchUpdate.assert_not_called()

    @patch("indoor_temp_logger.build")
    @patch("indoor_temp_logger.service_account.Credentials.from_service_account_info")
    @patch("indoor_temp_logger.requests.get")
    @patch("indoor_temp_logger.boto3.client")
    @patch("indoor_temp_logger.current_sample_time")
    def test_backfill_failure_does_not_break_the_main_flow(
        self, mock_sample_time, mock_boto, mock_get, mock_credentials, mock_build
    ):
        """埋め直しが失敗しても、その回の記録は成立する。

        **補修が本業を巻き込まないようにする。** サンプルの記録も当日の集計も
        既に済んでいる段階で走るので、ここで落ちて全部を無駄にする理由がない。
        """
        mock_sample_time.return_value = datetime.datetime(
            2026, 4, 20, 9, 0, tzinfo=logger.JST
        )
        secrets_client = MagicMock()
        secrets_client.get_secret_value.return_value = {
            "SecretString": (
                '{"SWITCHBOT_TOKEN":"token","SWITCHBOT_SECRET":"secret",'
                '"SWITCHBOT_DEVICE_ID":"device","GOOGLE_SHEET_ID":"sheet-id"}'
            )
        }
        mock_boto.return_value = secrets_client

        switchbot_response = MagicMock()
        switchbot_response.json.return_value = {"body": {"temperature": 20.5}}
        mock_get.return_value = switchbot_response

        service = MagicMock()
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.get.return_value.execute.side_effect = [
            {"values": []},                 # TempHistory
            {"values": [["2026-04-20"]]},   # 当日の集計用（成功）
            RuntimeError("sheets unavailable"),   # 埋め直しの読み取りで失敗
        ]
        values_api.append.return_value.execute.return_value = {}
        values_api.update.return_value.execute.return_value = {}
        mock_build.return_value = service
        mock_credentials.return_value = MagicMock()

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            result = logger.lambda_handler({"id": "event-123"}, None)
        printed = captured.getvalue()

        # 本業は成立している
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body["sample"], "logged")
        self.assertEqual(body["aggregate"], "updated")
        self.assertEqual(body["backfilled"], 0)

        # **黙らせない。** 失敗したことはログに残す
        self.assertIn("Backfill skipped", printed, printed)

    @patch("indoor_temp_logger.backfill_missing_aggregates")
    @patch("indoor_temp_logger.build")
    @patch("indoor_temp_logger.service_account.Credentials.from_service_account_info")
    @patch("indoor_temp_logger.requests.get")
    @patch("indoor_temp_logger.boto3.client")
    @patch("indoor_temp_logger.current_sample_time")
    def test_handler_actually_calls_the_backfill(
        self, mock_sample_time, mock_boto, mock_get, mock_credentials,
        mock_build, mock_backfill
    ):
        """埋め直しが**実際に呼ばれている**ことを固定する。

        ⚠️ **これが無いと、配線が外れても気づけない。**
        補修の失敗は握りつぶす設計なので、`backfill_missing_aggregates` の
        呼び出しごと消えても、他のテストは全部緑のまま通る。
        **握りつぶす処理は、呼ばれたこと自体を別に確かめる。**
        """
        mock_backfill.return_value = {"filled": 2, "dates": ["2026-04-18", "2026-04-19"]}
        mock_sample_time.return_value = datetime.datetime(
            2026, 4, 20, 9, 0, tzinfo=logger.JST
        )
        secrets_client = MagicMock()
        secrets_client.get_secret_value.return_value = {
            "SecretString": (
                '{"SWITCHBOT_TOKEN":"token","SWITCHBOT_SECRET":"secret",'
                '"SWITCHBOT_DEVICE_ID":"device","GOOGLE_SHEET_ID":"sheet-id"}'
            )
        }
        mock_boto.return_value = secrets_client
        switchbot_response = MagicMock()
        switchbot_response.json.return_value = {"body": {"temperature": 20.5}}
        mock_get.return_value = switchbot_response

        service = MagicMock()
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.get.return_value.execute.side_effect = [
            {"values": []},
            {"values": [["2026-04-20"]]},
        ]
        values_api.append.return_value.execute.return_value = {}
        values_api.update.return_value.execute.return_value = {}
        mock_build.return_value = service
        mock_credentials.return_value = MagicMock()

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            result = logger.lambda_handler({"id": "event-123"}, None)
        printed = captured.getvalue()

        mock_backfill.assert_called_once()
        # 当日の日付を渡していること（未来や別の日を渡していない）
        self.assertEqual(mock_backfill.call_args.args[3], datetime.date(2026, 4, 20))

        self.assertEqual(json.loads(result["body"])["backfilled"], 2)
        self.assertIn("backfilled=2", printed, printed)
        self.assertIn("2026-04-18", printed, "埋めた日付をログに残していない")


if __name__ == "__main__":
    unittest.main()
