"""A transient Sheets read timeout must not lose the sample; writes stay single-shot.

2026-10-22 and 2026-11-16 (JST 08:14): the TempHistory read timed out once
(`TimeoutError: The read operation timed out`), the whole run raised, and the
LoggingFailed alarm fired. Lambda's async retry recorded the sample a minute
later, so the alarm was noise for a one-off network stall.

These tests drive the real googleapiclient request/retry code through a fake
HTTP transport, so they check what the library actually does with the
arguments the logger passes - not what a MagicMock would accept.
"""
import contextlib
import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

import httplib2

import indoor_temp_logger as logger


class FakeSheetsHttp:
    """Minimal httplib2-compatible transport; synthetic data only."""

    def __init__(self, fail_first_get=0, fail_append=False):
        self.fail_first_get = fail_first_get
        self.fail_append = fail_append
        self.calls = []

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        self.calls.append((method, uri))
        if method == "GET" and "TempHistory" in uri:
            if self.fail_first_get > 0:
                self.fail_first_get -= 1
                raise TimeoutError("The read operation timed out")
            return httplib2.Response({"status": "200"}), b'{"values": []}'
        if method == "POST" and ":append" in uri:
            if self.fail_append:
                raise TimeoutError("The read operation timed out")
            return httplib2.Response({"status": "200"}), b"{}"
        raise AssertionError(f"unexpected request {method} {uri}")

    def count(self, method, fragment):
        return sum(1 for m, u in self.calls if m == method and fragment in u)


class SheetsReadRetryTests(unittest.TestCase):
    def run_logger(self, fake_http):
        secrets_client = MagicMock()
        secrets_client.get_secret_value.return_value = {
            "SecretString": json.dumps({
                "SWITCHBOT_TOKEN": "token",
                "SWITCHBOT_SECRET": "secret",
                "SWITCHBOT_DEVICE_ID": "device",
                "GOOGLE_SHEET_ID": "sheet-id",
            })
        }
        switchbot_response = MagicMock()
        switchbot_response.json.return_value = {"body": {"temperature": 20.5}}
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(logger.boto3, "client", return_value=secrets_client))
            stack.enter_context(patch.object(logger, "_switchbot_status", return_value=switchbot_response))
            stack.enter_context(patch.object(
                logger, "current_sample_time",
                return_value=datetime.datetime(2026, 11, 16, 8, 14, tzinfo=logger.JST),
            ))
            stack.enter_context(patch.object(
                logger.service_account.Credentials, "from_service_account_info",
                return_value=MagicMock(),
            ))
            stack.enter_context(patch.object(
                logger.google_auth_httplib2, "AuthorizedHttp", return_value=fake_http,
            ))
            stack.enter_context(patch.object(
                logger, "sync_daily_aggregate", return_value={"status": "updated"},
            ))
            stack.enter_context(patch.object(
                logger, "backfill_missing_aggregates", return_value={"filled": 0, "dates": []},
            ))
            # googleapiclient backs off with time.sleep between retries.
            stack.enter_context(patch("time.sleep"))
            stack.enter_context(contextlib.redirect_stdout(open("/dev/null", "w")))
            return logger.lambda_handler(
                {"id": "5bf9cb57-f02a-2fff-de7e-b143a63d4541"}, None
            )

    def test_one_read_timeout_is_retried_and_the_sample_is_logged(self):
        fake = FakeSheetsHttp(fail_first_get=1)

        result = self.run_logger(fake)

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(json.loads(result["body"])["sample"], "logged")
        self.assertEqual(fake.count("GET", "TempHistory"), 2)
        self.assertEqual(fake.count("POST", ":append"), 1)

    def test_persistent_read_timeout_still_raises(self):
        fake = FakeSheetsHttp(fail_first_get=99)

        with self.assertRaises(TimeoutError):
            self.run_logger(fake)

        self.assertEqual(
            fake.count("GET", "TempHistory"), logger.SHEETS_READ_RETRIES + 1,
            "retries are bounded so a Sheets outage cannot eat the Lambda timeout",
        )
        self.assertEqual(fake.count("POST", ":append"), 0)

    def test_append_timeout_is_not_retried(self):
        # A timed-out append may still have been applied server-side.
        # Retrying it inside the run could write the sample twice; the
        # Lambda-level retry re-reads TempHistory and de-duplicates instead.
        fake = FakeSheetsHttp(fail_append=True)

        with self.assertRaises(TimeoutError):
            self.run_logger(fake)

        self.assertEqual(fake.count("POST", ":append"), 1)


if __name__ == "__main__":
    unittest.main()
