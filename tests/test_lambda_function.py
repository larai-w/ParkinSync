import unittest
from unittest.mock import patch, MagicMock

# The production handler lives in src/ParkinSync_OCR_Handler.py.
# CI adds `src` to PYTHONPATH so this import resolves.
import ParkinSync_OCR_Handler as handler


class TestHistoricalWeather(unittest.TestCase):

    def test_returns_summary_and_raw_on_success(self):
        """get_historical_weather returns a (summary, raw_data) tuple."""
        with patch('requests.get') as mocked_get:
            mocked_get.return_value.raise_for_status.return_value = None
            mocked_get.return_value.json.return_value = {
                'days': [{
                    'temp': 20.5, 'tempmin': 15.0, 'tempmax': 25.0,
                    'conditions': 'Clear'
                }]
            }

            summary, raw = handler.get_historical_weather("2026-04-20", "fake_key")

            # Summary is a formatted string; raw is the underlying day dict
            self.assertIn("20.5", summary)
            self.assertIn("Clear", summary)
            self.assertEqual(raw['tempmax'], 25.0)

    def test_degrades_gracefully_on_api_error(self):
        """On any API/network failure it returns the sentinel tuple."""
        with patch('requests.get', side_effect=Exception("network down")):
            summary, raw = handler.get_historical_weather("2026-04-20", "fake_key")
            self.assertEqual(summary, "Weather N/A")
            self.assertIsNone(raw)

    def test_unparseable_date_returns_sentinel_without_api_call(self):
        """An unparseable OCR date never hits the weather API."""
        with patch('requests.get') as mocked_get:
            summary, raw = handler.get_historical_weather("N/A", "fake_key")
            self.assertEqual(summary, "Weather N/A")
            self.assertIsNone(raw)
            mocked_get.assert_not_called()

    def test_day_only_date_uses_fallback_month_in_url(self):
        """A day-only cell ('20th') is resolved via fallback_month for the API call."""
        with patch('requests.get') as mocked_get:
            mocked_get.return_value.raise_for_status.return_value = None
            mocked_get.return_value.json.return_value = {
                'days': [{
                    'temp': 15.0, 'tempmin': 10.0, 'tempmax': 18.0,
                    'conditions': 'Overcast'
                }]
            }
            summary, raw = handler.get_historical_weather(
                "20th", "fake_key", fallback_month="2026-04"
            )
            self.assertIn("15.0", summary)
            called_url = mocked_get.call_args[0][0]
            self.assertIn("2026-04-20", called_url)


class TestWeatherEmoji(unittest.TestCase):

    def test_maps_conditions_to_emoji(self):
        self.assertEqual(handler.get_weather_emoji("Rain, Overcast"), "☔")
        self.assertEqual(handler.get_weather_emoji("Clear"), "☀️")
        self.assertEqual(handler.get_weather_emoji("Snow"), "❄️")

    def test_unknown_condition_falls_back(self):
        self.assertEqual(handler.get_weather_emoji("Freezing Fog"), "🌡️")


class TestDateParsing(unittest.TestCase):

    def test_english_full_month(self):
        self.assertEqual(handler.parse_log_date("April 20"), f"{handler._log_year()}-04-20")

    def test_english_abbreviated_month_with_ordinal(self):
        self.assertEqual(handler.parse_log_date("Apr 3rd"), f"{handler._log_year()}-04-03")
        self.assertEqual(handler.parse_log_date("Sept. 21st"), f"{handler._log_year()}-09-21")

    def test_japanese_date(self):
        self.assertEqual(handler.parse_log_date("4月20日"), f"{handler._log_year()}-04-20")
        self.assertEqual(handler.parse_log_date("12月3日"), f"{handler._log_year()}-12-03")

    def test_numeric_date(self):
        self.assertEqual(handler.parse_log_date("4/20"), f"{handler._log_year()}-04-20")

    def test_full_iso_date_keeps_own_year(self):
        self.assertEqual(handler.parse_log_date("2025-04-20"), "2025-04-20")
        self.assertEqual(handler.parse_log_date("2025/4/2"), "2025-04-02")

    def test_unparseable_returns_none(self):
        self.assertIsNone(handler.parse_log_date("N/A"))
        self.assertIsNone(handler.parse_log_date(""))
        self.assertIsNone(handler.parse_log_date(None))

    def test_log_year_env_override(self):
        with patch.dict('os.environ', {'LOG_YEAR': '2027'}):
            self.assertEqual(handler.parse_log_date("May 1"), "2027-05-01")

    def test_day_only_ordinal_with_fallback_month(self):
        self.assertEqual(handler.parse_log_date("20th", fallback_month="2026-04"), "2026-04-20")
        self.assertEqual(handler.parse_log_date("1st", fallback_month="2026-01"), "2026-01-01")

    def test_day_only_without_fallback_returns_none(self):
        self.assertIsNone(handler.parse_log_date("20th"))

    def test_infer_month_from_numeric_key(self):
        self.assertEqual(handler._infer_month_from_key("2026-04_log.jpg"), "2026-04")
        self.assertEqual(handler._infer_month_from_key("log_2026_05.pdf"), "2026-05")

    def test_infer_month_from_english_key(self):
        self.assertEqual(handler._infer_month_from_key("april_2026_log.jpg"), "2026-04")

    def test_infer_month_from_log_month_env(self):
        with patch.dict('os.environ', {'LOG_MONTH': '2026-04'}):
            self.assertEqual(handler._infer_month_from_key("any_file.jpg"), "2026-04")


class TestIdempotency(unittest.TestCase):

    def _make_s3(self, tag_value=None):
        s3 = MagicMock()
        if tag_value:
            s3.get_object_tagging.return_value = {
                'TagSet': [{'Key': 'ParkinSync-Status', 'Value': tag_value}]
            }
        else:
            s3.get_object_tagging.return_value = {'TagSet': []}
        return s3

    def test_already_processed_returns_true(self):
        s3 = self._make_s3(tag_value='processed')
        self.assertTrue(handler._is_already_processed(s3, 'bucket', 'key.jpg'))

    def test_unprocessed_returns_false(self):
        s3 = self._make_s3()
        self.assertFalse(handler._is_already_processed(s3, 'bucket', 'key.jpg'))

    def test_tag_check_error_returns_false(self):
        s3 = MagicMock()
        s3.get_object_tagging.side_effect = Exception("AccessDenied")
        self.assertFalse(handler._is_already_processed(s3, 'bucket', 'key.jpg'))

    def test_mark_as_processed_sets_tag(self):
        s3 = self._make_s3()
        handler._mark_as_processed(s3, 'bucket', 'key.jpg')
        s3.put_object_tagging.assert_called_once()
        tag_set = s3.put_object_tagging.call_args[1]['Tagging']['TagSet']
        self.assertIn({'Key': 'ParkinSync-Status', 'Value': 'processed'}, tag_set)

    def test_mark_preserves_existing_tags(self):
        s3 = MagicMock()
        s3.get_object_tagging.return_value = {
            'TagSet': [{'Key': 'UploadedBy', 'Value': 'LINE'}]
        }
        handler._mark_as_processed(s3, 'bucket', 'key.jpg')
        tag_set = s3.put_object_tagging.call_args[1]['Tagging']['TagSet']
        keys = [t['Key'] for t in tag_set]
        self.assertIn('UploadedBy', keys)
        self.assertIn('ParkinSync-Status', keys)

    def test_mark_as_processed_returns_true_on_success(self):
        s3 = self._make_s3()
        self.assertTrue(handler._mark_as_processed(s3, 'bucket', 'key.jpg'))

    def test_tagging_failure_is_reported_not_swallowed(self):
        """A tagging failure used to be printed and forgotten.

        The object then looked unprocessed forever and nobody found out.
        It must not raise (the rows are already written, and a retry would
        duplicate them), but it must be visible: False to the caller, and a
        greppable marker in the log.
        """
        s3 = MagicMock()
        s3.get_object_tagging.return_value = {'TagSet': []}
        s3.put_object_tagging.side_effect = Exception('AccessDenied')

        with patch('builtins.print') as fake_print:
            result = handler._mark_as_processed(s3, 'bucket', 'key.jpg')

        self.assertFalse(result, 'a failed tagging must report False')
        printed = ' '.join(str(c) for c in fake_print.call_args_list)
        self.assertIn('[TAGGING FAILED]', printed,
                      'the failure must be greppable in the log')

    def test_tagging_failure_does_not_raise(self):
        """Raising here would let the Lambda retry and duplicate spreadsheet rows."""
        s3 = MagicMock()
        s3.get_object_tagging.side_effect = Exception('boom')
        try:
            handler._mark_as_processed(s3, 'bucket', 'key.jpg')
        except Exception as exc:  # pragma: no cover
            self.fail(f'_mark_as_processed must not raise, but raised {exc}')


class TestQuarantine(unittest.TestCase):

    def test_quarantine_copies_to_review_prefix(self):
        s3 = MagicMock()
        handler._quarantine_and_notify(s3, 'bucket', 'log.jpg', 'test reason')
        s3.copy_object.assert_called_once_with(
            Bucket='bucket',
            CopySource={'Bucket': 'bucket', 'Key': 'log.jpg'},
            Key='review/log.jpg',
        )

    def test_quarantine_publishes_to_sns_when_topic_set(self):
        s3 = MagicMock()
        with patch.dict('os.environ', {'SNS_TOPIC_ARN': 'arn:aws:sns:us-east-1:123:test'}):
            with patch('boto3.client') as mock_boto:
                mock_sns = MagicMock()
                mock_boto.return_value = mock_sns
                handler._quarantine_and_notify(s3, 'bucket', 'log.jpg', 'test')
                mock_sns.publish.assert_called_once()

    def test_quarantine_skips_sns_when_no_topic(self):
        s3 = MagicMock()
        with patch.dict('os.environ', {'SNS_TOPIC_ARN': ''}):
            with patch('boto3.client') as mock_boto:
                handler._quarantine_and_notify(s3, 'bucket', 'log.jpg', 'test')
                mock_boto.assert_not_called()


class TestLambdaHandler(unittest.TestCase):

    def _event(self, key='2026-04_log.jpg'):
        return {'Records': [{'s3': {'bucket': {'name': 'test-bucket'}, 'object': {'key': key}}}]}

    def _mock_boto(self, mock_boto, tag_set=None, textract_blocks=None):
        mock_s3 = MagicMock()
        mock_s3.get_object_tagging.return_value = {'TagSet': tag_set or []}
        mock_textract = MagicMock()
        mock_textract.analyze_document.return_value = {'Blocks': textract_blocks or []}
        mock_secrets = MagicMock()
        mock_secrets.get_secret_value.return_value = {
            'SecretString': '{"VISUAL_CROSSING_KEY":"k","GOOGLE_SHEET_ID":"s"}'
        }

        def client_factory(service, *args, **kwargs):
            return {'s3': mock_s3, 'textract': mock_textract,
                    'secretsmanager': mock_secrets}.get(service, MagicMock())

        mock_boto.side_effect = client_factory
        return mock_s3, mock_textract, mock_secrets

    def test_skips_review_prefix_files(self):
        # review/ files short-circuit before any AWS client is created.
        response = handler.lambda_handler(self._event(key='review/log.jpg'), None)
        self.assertEqual(response['statusCode'], 200)
        self.assertIn('Skipped', response['body'])

    @patch('boto3.client')
    def test_already_processed_returns_200_without_textract(self, mock_boto):
        _, mock_textract, _ = self._mock_boto(
            mock_boto, tag_set=[{'Key': 'ParkinSync-Status', 'Value': 'processed'}]
        )
        response = handler.lambda_handler(self._event(), None)
        self.assertEqual(response['statusCode'], 200)
        self.assertIn('Already processed', response['body'])
        mock_textract.analyze_document.assert_not_called()

    @patch('boto3.client')
    def test_no_table_quarantines_and_returns_404(self, mock_boto):
        mock_s3, _, _ = self._mock_boto(mock_boto, textract_blocks=[])
        response = handler.lambda_handler(self._event(), None)
        self.assertEqual(response['statusCode'], 404)
        self.assertIn('No table detected', response['body'])
        mock_s3.copy_object.assert_called_once()  # quarantine triggered

    @patch('boto3.client')
    def test_permanent_textract_failure_is_not_retried(self, mock_boto):
        """もう一度やっても直らない失敗を投げ直さない。

        2026-08-21 に3件の PDF が `UnsupportedDocumentException` で失敗した。
        Textract の同期 API は複数ページ PDF を受け付けない。
        **ファイルが変わらない限り、次も必ず同じ失敗になる。**

        隔離も通知も正しく動いていたのに、そのあと投げ直していたため
        Lambda が自動リトライし、**隔離コピーと通知メールが増え、
        エラー率が膨らんで本当に直せる一時的な失敗が埋もれていた。**

        この関数は既にこの区別を持っている（「テーブル未検出」は
        隔離して 404 を返し、投げ直さない）。同じ扱いに揃える。
        """
        mock_s3, mock_textract, _ = self._mock_boto(mock_boto)

        class UnsupportedDocumentException(Exception):
            pass

        mock_textract.analyze_document.side_effect = UnsupportedDocumentException(
            "Request has unsupported document format"
        )

        response = handler.lambda_handler(self._event(), None)

        self.assertEqual(response['statusCode'], 422)
        self.assertTrue(response.get('quarantined'), "隔離した印が返っていない")
        mock_s3.copy_object.assert_called_once()   # 隔離はする

    @patch('boto3.client')
    def test_transient_failure_is_still_raised(self, mock_boto):
        """一時的かもしれない失敗は投げ直す。

        **投げ直さなくした結果、何も鳴らなくなっては意味がない。**
        Lambda のリトライに意味がある失敗は、これまでどおり投げる。
        """
        mock_s3, mock_textract, _ = self._mock_boto(mock_boto)

        class ThrottlingException(Exception):
            pass

        mock_textract.analyze_document.side_effect = ThrottlingException("slow down")

        with self.assertRaises(ThrottlingException):
            handler.lambda_handler(self._event(), None)

        mock_s3.copy_object.assert_called_once()   # 隔離はする

    def test_permanent_failure_detected_from_client_error_code(self):
        """botocore の ClientError は、中のエラーコードで判定する。

        例外クラスはサービスのエラーコードから動的に作られるので、
        **クラス名だけを見ていると取りこぼす。**
        """
        class ClientError(Exception):
            def __init__(self, code):
                super().__init__(code)
                self.response = {'Error': {'Code': code}}

        self.assertTrue(handler._is_permanent_failure(ClientError('UnsupportedDocumentException')))
        self.assertFalse(handler._is_permanent_failure(ClientError('ThrottlingException')))
        self.assertFalse(handler._is_permanent_failure(RuntimeError('boom')))


if __name__ == '__main__':
    unittest.main()
