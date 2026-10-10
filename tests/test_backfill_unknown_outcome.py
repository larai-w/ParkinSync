"""Synthetic backfill failures must not masquerade as known zero writes."""
import contextlib
import datetime
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import indoor_temp_logger as logger


class BackfillOutcomeTests(unittest.TestCase):
    def invoke(self, backfill, aggregate='updated', duplicate=False, main_error=None):
        service = MagicMock()
        values = service.spreadsheets.return_value.values.return_value
        values.get.return_value.execute.return_value = {'values': []}
        secret = MagicMock()
        secret.get_secret_value.return_value = {'SecretString': json.dumps({
            'SWITCHBOT_TOKEN': 'synthetic', 'SWITCHBOT_SECRET': 'synthetic',
            'SWITCHBOT_DEVICE_ID': 'synthetic', 'GOOGLE_SHEET_ID': 'synthetic'})}
        capture = io.StringIO()
        response = MagicMock()
        response.json.return_value = {'body': {'temperature': 20.5}}
        with contextlib.ExitStack() as stack:
            replacements = {
                'boto3.client': secret, 'build': service,
                'service_account.Credentials.from_service_account_info': MagicMock(),
                'google_auth_httplib2.AuthorizedHttp': MagicMock(),
                'current_sample_time': datetime.datetime(2026, 4, 20, 9, tzinfo=logger.JST),
                '_switchbot_status': response, 'sample_already_logged': duplicate,
            }
            for name, value in replacements.items():
                stack.enter_context(patch('indoor_temp_logger.' + name, return_value=value))
            sync = stack.enter_context(patch.object(logger, 'sync_daily_aggregate',
                                                   return_value={'status': aggregate}))
            if main_error is not None: sync.side_effect = main_error
            repair = stack.enter_context(patch.object(logger, 'backfill_missing_aggregates'))
            if isinstance(backfill, Exception): repair.side_effect = backfill
            elif callable(backfill): repair.side_effect = lambda *a, **k: backfill(values)
            else: repair.return_value = backfill
            stack.enter_context(contextlib.redirect_stdout(capture))
            if main_error is not None:
                with self.assertRaises(type(main_error)) as raised:
                    logger.lambda_handler({}, None)
                self.assertIs(raised.exception, main_error)
                repair.assert_not_called()
                return
            result = logger.lambda_handler({}, SimpleNamespace(aws_request_id=None))
        summaries = [json.loads(line[len('[EXECUTION_SUMMARY] '):])
                     for line in capture.getvalue().splitlines() if line.startswith('[EXECUTION_SUMMARY] ')]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(summaries[0]['execution_outcome'], 'returned')
        self.assertEqual(summaries[0]['backfill_completion'], 'UNVERIFIED')
        repair.assert_called_once()
        self.assertEqual(values.append.call_count, 0 if duplicate else 1)
        return json.loads(result['body']), summaries[0], capture.getvalue(), values

    def test_failure_after_daily_update_returns_unknown_count(self):
        body, summary, logs, _ = self.invoke(RuntimeError('synthetic unavailable'))
        self.assertEqual(body['aggregate'], 'updated')
        self.assertIsNone(body['backfilled'])
        self.assertIsNone(summary['backfilled_count'])
        self.assertIn('backfilled=unknown', logs)

    def test_failure_after_missing_date_does_not_claim_empty_backfill(self):
        body, summary, logs, values = self.invoke(RuntimeError('synthetic unavailable'), 'master-date-missing')
        self.assertIsNone(body['backfilled'])
        self.assertIsNone(summary['backfilled_count'])
        self.assertNotIn('Backfill filled nothing:', logs)
        self.assertEqual(values.get.call_count, 1)

    def test_partial_write_then_failure_is_unknown_without_retry(self):
        def partial(values):
            values.update(range='synthetic').execute()
            raise RuntimeError('synthetic response lost')
        body, summary, _, values = self.invoke(partial)
        self.assertIsNone(body['backfilled'])
        self.assertIsNone(summary['backfilled_count'])
        self.assertEqual(values.update.call_count, 1)

    def test_duplicate_sample_with_backfill_failure_stays_unknown(self):
        body, summary, _, _ = self.invoke(RuntimeError('synthetic unavailable'), duplicate=True)
        self.assertEqual(body['sample'], 'duplicate')
        self.assertIsNone(summary['backfilled_count'])

    def test_completed_zero_backfill_remains_known_zero(self):
        body, summary, _, _ = self.invoke({'filled': 0, 'dates': []})
        self.assertEqual(body['backfilled'], 0)
        self.assertEqual(summary['backfilled_count'], 0)

    def test_known_zero_with_missing_date_keeps_diagnosis(self):
        body, summary, logs, _ = self.invoke({'filled': 0, 'dates': []}, 'master-date-missing')
        self.assertEqual(body['backfilled'], 0)
        self.assertEqual(summary['backfilled_count'], 0)
        self.assertIn('Backfill filled nothing:', logs)

    def test_positive_backfill_keeps_reported_count(self):
        body, summary, logs, _ = self.invoke({'filled': 2, 'dates': ['synthetic-a', 'synthetic-b']})
        self.assertEqual(body['backfilled'], 2)
        self.assertEqual(summary['backfilled_count'], 2)
        self.assertIn('backfilled=2', logs)

    def test_main_failure_still_raises_without_starting_backfill(self):
        self.invoke({'filled': 0, 'dates': []}, main_error=RuntimeError('synthetic main failure'))


if __name__ == '__main__': unittest.main()
