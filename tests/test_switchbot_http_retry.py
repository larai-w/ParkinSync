import unittest
from unittest.mock import MagicMock, patch
import requests
import indoor_temp_logger as logger


class TestSwitchBotHttpRetry(unittest.TestCase):
    def response(self, code, retry_after=None):
        response = requests.Response()
        response.status_code = code
        response.url = 'https://example.invalid/status'
        if retry_after is not None:
            response.headers['Retry-After'] = retry_after
        return response

    def recover(self, code, header=None, wait=1):
        bad = self.response(code, header); good = self.response(200)
        with patch.object(logger.requests, 'get', side_effect=[bad, good]) as get:
            with patch.object(logger.time, 'sleep') as sleep:
                with patch.object(logger, '_signed_headers', side_effect=[{'nonce': 'one'}, {'nonce': 'two'}]):
                    self.assertIs(logger._switchbot_status('https://example.invalid/status', 't', 's'), good)
        self.assertEqual(get.call_count, 2)
        self.assertEqual([call.kwargs['timeout'] for call in get.call_args_list], [15, 15])
        self.assertNotEqual(get.call_args_list[0].kwargs['headers'], get.call_args_list[1].kwargs['headers'])
        sleep.assert_called_once_with(wait)

    def test_rate_limit_recovers(self): self.recover(429)
    def test_server_error_recovers(self): self.recover(503)
    def test_other_transient_server_errors_recover(self):
        for code in (500, 502, 504):
            with self.subTest(code=code): self.recover(code)
    def test_retry_after_seconds_is_respected(self): self.recover(429, '4', 4)
    def test_retry_after_zero_keeps_minimum_backoff(self): self.recover(503, '0', 1)
    def test_retry_after_upper_boundary(self): self.recover(429, '5', 5)

    def test_repeated_errors_stop_after_three_attempts(self):
        responses = [self.response(503) for _ in range(3)]
        with patch.object(logger.requests, 'get', side_effect=responses) as get:
            with patch.object(logger.time, 'sleep') as sleep:
                with self.assertRaises(requests.HTTPError) as caught:
                    logger._switchbot_status('u', 't', 's')
        self.assertIs(caught.exception.response, responses[-1])
        self.assertEqual(get.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    def test_long_or_unparseable_retry_after_is_not_shortened(self):
        for header in ('6', '3600', '-1', '1.5', 'NaN', '', 'Wed, 21 Oct 2015 07:28:00 GMT'):
            with self.subTest(header=header):
                bad = self.response(429, header)
                with patch.object(logger.requests, 'get', return_value=bad) as get:
                    with patch.object(logger.time, 'sleep') as sleep:
                        with self.assertRaises(requests.HTTPError): logger._switchbot_status('u', 't', 's')
                self.assertEqual(get.call_count, 1); sleep.assert_not_called()

    def test_auth_and_other_statuses_are_not_retried(self):
        for code in (400, 401, 403, 404, 501, 505):
            with self.subTest(code=code):
                with patch.object(logger.requests, 'get', return_value=self.response(code)) as get:
                    with patch.object(logger.time, 'sleep') as sleep:
                        with self.assertRaises(requests.HTTPError): logger._switchbot_status('u', 't', 's')
                self.assertEqual(get.call_count, 1); sleep.assert_not_called()

    def test_retry_wait_and_next_request_must_fit_deadline(self):
        # Initial 15s request fits; a 4s wait plus another 15s request does not.
        with patch.object(logger.time, 'monotonic', return_value=100):
            with patch.object(logger.requests, 'get', return_value=self.response(429, '4')) as get:
                with patch.object(logger.time, 'sleep') as sleep:
                    with self.assertRaises(requests.HTTPError): logger._switchbot_status('u', 't', 's', deadline=118)
        self.assertEqual(get.call_count, 1); sleep.assert_not_called()

    def test_retry_fits_exact_deadline(self):
        with patch.object(logger.time, 'monotonic', return_value=100):
            bad = self.response(503); good = self.response(200)
            with patch.object(logger.requests, 'get', side_effect=[bad, good]) as get:
                with patch.object(logger.time, 'sleep') as sleep:
                    self.assertIs(logger._switchbot_status('u', 't', 's', deadline=116), good)
        self.assertEqual(get.call_count, 2); sleep.assert_called_once_with(1)

    def test_missing_http_response_is_not_retried(self):
        with patch.object(logger.requests, 'get', side_effect=requests.HTTPError('synthetic')) as get:
            with patch.object(logger.time, 'sleep') as sleep:
                with self.assertRaises(requests.HTTPError): logger._switchbot_status('u', 't', 's')
        self.assertEqual(get.call_count, 1); sleep.assert_not_called()


if __name__ == '__main__': unittest.main()
