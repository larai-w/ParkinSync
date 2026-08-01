import datetime
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


if __name__ == "__main__":
    unittest.main()
