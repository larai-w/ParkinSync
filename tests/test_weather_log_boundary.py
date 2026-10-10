import contextlib
import io
import unittest
from unittest.mock import patch

import requests
import ParkinSync_OCR_Handler as handler


class WeatherLogBoundaryTests(unittest.TestCase):
    def assert_safe_failure(self, error, target='requests.get'):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch(target, side_effect=error) as call:
            result = handler.get_historical_weather('2030-01-09', 'synthetic-api-marker')
        self.assertEqual(result, ('Weather N/A', None))
        self.assertEqual(call.call_count, 1)
        self.assertEqual(output.getvalue(),
                         'Weather fetch unavailable; continuing without weather enrichment.\n')
        for marker in ('synthetic-api-marker', '2030-01-09', 'https://', 'private-response-marker'):
            self.assertNotIn(marker, output.getvalue())

    def test_timeout_does_not_log_authenticated_url(self):
        self.assert_safe_failure(requests.Timeout(
            'https://example.invalid/2030-01-09?key=synthetic-api-marker'))

    def test_http_error_does_not_log_authenticated_url(self):
        self.assert_safe_failure(requests.HTTPError(
            '401 for https://example.invalid/2030-01-09?key=synthetic-api-marker'))

    def test_response_exception_does_not_log_body(self):
        self.assert_safe_failure(ValueError('private-response-marker'))

    def test_date_exception_does_not_log_source_text(self):
        self.assert_safe_failure(ValueError('private-response-marker'),
                                 target='ParkinSync_OCR_Handler.parse_log_date')

    def test_valid_response_retains_weather_without_warning(self):
        output = io.StringIO()
        raw = {'temp': 20.5, 'tempmin': 15.0, 'tempmax': 25.0, 'conditions': 'Clear'}
        with contextlib.redirect_stdout(output), patch('requests.get') as get:
            get.return_value.json.return_value = {'days': [raw]}
            summary, actual = handler.get_historical_weather('2030-01-09', 'synthetic-api-marker')
        self.assertEqual(actual, raw)
        self.assertIn('20.5', summary)
        self.assertEqual(output.getvalue(), '')
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs, {'timeout': 10})


if __name__ == '__main__':
    unittest.main()
