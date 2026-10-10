"""Synthetic handled failures must not echo request URLs or response content."""
import unittest
from unittest.mock import patch

from googleapiclient.errors import HttpError
import httplib2
import indoor_temp_logger as logger
import test_backfill_unknown_outcome as existing


class UnprintableError(Exception):
    def __str__(self):
        raise RuntimeError('synthetic exception rendering failed')


class HandledDiagnosticLogTests(unittest.TestCase):
    def error(self):
        return HttpError(httplib2.Response({'status': '403', 'reason': 'Denied'}),
                         b'{"error":{"message":"synthetic-response-marker"}}',
                         uri='https://example.invalid/synthetic-sheet?key=synthetic-api-marker')

    def invoke(self, backfill, aggregate='updated'):
        return existing.BackfillOutcomeTests(methodName='runTest').invoke(backfill, aggregate)

    def safe_logs(self, logs):
        for marker in ('synthetic-api-marker', 'synthetic-response-marker',
                       'synthetic-sheet', 'https://example.invalid'):
            self.assertNotIn(marker, logs)

    def test_backfill_http_failure_retains_unknown_without_details(self):
        body, summary, logs, _ = self.invoke(self.error())
        self.assertIsNone(body['backfilled'])
        self.assertIsNone(summary['backfilled_count'])
        self.assertEqual(body['aggregate'], 'updated')
        self.assertIn('Backfill skipped: outcome unknown', logs)
        self.safe_logs(logs)

    def diagnosis(self, failed):
        zero = {'filled': 0, 'dates': [], 'unparsed_dates': 1}
        with (patch.object(logger, 'fetch_year_source_diagnosis', return_value={}) as year,
              patch.object(logger, 'fetch_date_cell_types', return_value=[]) as cells):
            (year if failed == 'year' else cells).side_effect = self.error()
            body, summary, logs, _ = self.invoke(zero, 'master-date-missing')
        self.assertEqual(body['backfilled'], 0)
        self.assertEqual(summary['backfilled_count'], 0)
        self.assertEqual(body['aggregate'], 'master-date-missing')
        year.assert_called_once()
        cells.assert_called_once()
        self.safe_logs(logs)
        return logs

    def test_year_diagnosis_failure_does_not_echo_details(self):
        logs = self.diagnosis('year')
        self.assertIn('Year source diagnosis skipped: details unavailable', logs)

    def test_cell_diagnosis_failure_does_not_echo_details(self):
        logs = self.diagnosis('cells')
        self.assertIn('Date cell types skipped: details unavailable', logs)

    def test_unprintable_backfill_error_does_not_stop_primary_work(self):
        try:
            body, summary, logs, _ = self.invoke(UnprintableError())
        except RuntimeError:
            self.fail('Formatting a handled exception stopped primary work')
        self.assertEqual(body['aggregate'], 'updated')
        self.assertIsNone(summary['backfilled_count'])
        self.assertIn('Backfill skipped: outcome unknown', logs)

    def test_successful_diagnoses_keep_existing_outputs(self):
        zero = {'filled': 0, 'dates': [], 'unparsed_dates': 1}
        with (patch.object(logger, 'fetch_year_source_diagnosis', return_value={'synthetic_count': 1}),
              patch.object(logger, 'fetch_date_cell_types', return_value=[])):
            body, summary, logs, _ = self.invoke(zero, 'master-date-missing')
        self.assertEqual(body['backfilled'], 0)
        self.assertEqual(summary['backfilled_count'], 0)
        self.assertIn('Year source diagnosis: {"synthetic_count": 1}', logs)
        self.assertIn('Date cell types: []', logs)
        self.assertNotIn('details unavailable', logs)


if __name__ == '__main__': unittest.main()
