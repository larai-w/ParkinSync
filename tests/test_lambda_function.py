import unittest
from unittest.mock import patch, MagicMock, call
import lambda_function


class TestDateParsing(unittest.TestCase):

    def setUp(self):
        self.env_patcher = patch.dict('os.environ', {'LOG_YEAR': '2026'})
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def test_english_full_month(self):
        self.assertEqual(lambda_function.parse_log_date("April 20"), "2026-04-20")
        self.assertEqual(lambda_function.parse_log_date("December 5"), "2026-12-05")

    def test_english_abbreviated_month_with_ordinal(self):
        self.assertEqual(lambda_function.parse_log_date("Apr 3rd"), "2026-04-03")
        self.assertEqual(lambda_function.parse_log_date("Sept. 21st"), "2026-09-21")

    def test_japanese_date(self):
        self.assertEqual(lambda_function.parse_log_date("4月20日"), "2026-04-20")
        self.assertEqual(lambda_function.parse_log_date("12月3日"), "2026-12-03")

    def test_numeric_date(self):
        self.assertEqual(lambda_function.parse_log_date("4/20"), "2026-04-20")

    def test_full_iso_date_keeps_own_year(self):
        self.assertEqual(lambda_function.parse_log_date("2025-04-20"), "2025-04-20")
        self.assertEqual(lambda_function.parse_log_date("2025/4/2"), "2025-04-02")

    def test_unparseable_returns_none(self):
        self.assertIsNone(lambda_function.parse_log_date("N/A"))
        self.assertIsNone(lambda_function.parse_log_date(""))
        self.assertIsNone(lambda_function.parse_log_date(None))

    def test_log_year_env_override(self):
        with patch.dict('os.environ', {'LOG_YEAR': '2027'}):
            self.assertEqual(lambda_function.parse_log_date("May 1"), "2027-05-01")

    def test_unparseable_date_returns_weather_na_without_api_call(self):
        with patch('requests.get') as mocked_get:
            result = lambda_function.get_historical_weather("???", "fake_key")
            self.assertEqual(result, "Weather N/A")
            mocked_get.assert_not_called()

    # --- Task 9: day-only ordinal with fallback_month ---

    def test_day_only_ordinal_with_fallback_month(self):
        self.assertEqual(lambda_function.parse_log_date("20th", fallback_month="2026-04"), "2026-04-20")
        self.assertEqual(lambda_function.parse_log_date("3rd", fallback_month="2026-12"), "2026-12-03")
        self.assertEqual(lambda_function.parse_log_date("1st", fallback_month="2026-01"), "2026-01-01")

    def test_day_only_without_fallback_returns_none(self):
        self.assertIsNone(lambda_function.parse_log_date("20th"))
        self.assertIsNone(lambda_function.parse_log_date("3rd"))

    def test_infer_month_from_numeric_key(self):
        self.assertEqual(lambda_function._infer_month_from_key("2026-04_log.jpg"), "2026-04")
        self.assertEqual(lambda_function._infer_month_from_key("log_2026_05.pdf"), "2026-05")

    def test_infer_month_from_english_key(self):
        result = lambda_function._infer_month_from_key("april_2026_log.jpg")
        self.assertIsNotNone(result)
        self.assertIn("-04", result)

    def test_infer_month_from_log_month_env(self):
        with patch.dict('os.environ', {'LOG_MONTH': '2026-04'}):
            self.assertEqual(lambda_function._infer_month_from_key("any_file.jpg"), "2026-04")


class TestWeather(unittest.TestCase):

    def test_weather_fetch_success(self):
        with patch('requests.get') as mocked_get:
            mocked_get.return_value.json.return_value = {
                'days': [{'temp': 20.5, 'conditions': 'Clear'}]
            }
            result = lambda_function.get_historical_weather("April 20", "fake_key")
            self.assertIn("20.5C", result)
            self.assertIn("Clear", result)

    def test_weather_with_fallback_month(self):
        with patch('requests.get') as mocked_get:
            mocked_get.return_value.json.return_value = {
                'days': [{'temp': 15.0, 'conditions': 'Overcast'}]
            }
            result = lambda_function.get_historical_weather("20th", "fake_key", fallback_month="2026-04")
            self.assertIn("15.0C", result)
            # Confirm the constructed URL used the right date
            called_url = mocked_get.call_args[0][0]
            self.assertIn("2026-04-20", called_url)


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
        self.assertTrue(lambda_function._is_already_processed(s3, 'bucket', 'key.jpg'))

    def test_unprocessed_returns_false(self):
        s3 = self._make_s3()
        self.assertFalse(lambda_function._is_already_processed(s3, 'bucket', 'key.jpg'))

    def test_tag_check_error_returns_false(self):
        s3 = MagicMock()
        s3.get_object_tagging.side_effect = Exception("AccessDenied")
        self.assertFalse(lambda_function._is_already_processed(s3, 'bucket', 'key.jpg'))

    def test_mark_as_processed_sets_tag(self):
        s3 = self._make_s3()
        lambda_function._mark_as_processed(s3, 'bucket', 'key.jpg')
        s3.put_object_tagging.assert_called_once()
        tag_set = s3.put_object_tagging.call_args[1]['Tagging']['TagSet']
        self.assertIn({'Key': 'ParkinSync-Status', 'Value': 'processed'}, tag_set)

    def test_mark_preserves_existing_tags(self):
        s3 = MagicMock()
        s3.get_object_tagging.return_value = {
            'TagSet': [{'Key': 'UploadedBy', 'Value': 'LINE'}]
        }
        lambda_function._mark_as_processed(s3, 'bucket', 'key.jpg')
        tag_set = s3.put_object_tagging.call_args[1]['Tagging']['TagSet']
        keys = [t['Key'] for t in tag_set]
        self.assertIn('UploadedBy', keys)
        self.assertIn('ParkinSync-Status', keys)


class TestQuarantine(unittest.TestCase):

    def test_quarantine_copies_to_review_prefix(self):
        s3 = MagicMock()
        lambda_function._quarantine_and_notify(s3, 'bucket', 'log.jpg', 'test reason')
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
                lambda_function._quarantine_and_notify(s3, 'bucket', 'log.jpg', 'test')
                mock_sns.publish.assert_called_once()

    def test_quarantine_skips_sns_when_no_topic(self):
        s3 = MagicMock()
        with patch.dict('os.environ', {'SNS_TOPIC_ARN': ''}):
            with patch('boto3.client') as mock_boto:
                lambda_function._quarantine_and_notify(s3, 'bucket', 'log.jpg', 'test')
                mock_boto.assert_not_called()


class TestLambdaHandler(unittest.TestCase):

    def _base_event(self, key='2026-04_log.jpg'):
        return {'Records': [{'s3': {'bucket': {'name': 'test-bucket'}, 'object': {'key': key}}}]}

    def _setup_mock_boto(self, mock_boto, textract_blocks=None):
        mock_s3 = MagicMock()
        mock_s3.get_object_tagging.return_value = {'TagSet': []}  # not processed
        mock_textract = MagicMock()
        mock_textract.analyze_document.return_value = {'Blocks': textract_blocks or []}
        mock_secrets = MagicMock()
        mock_secrets.get_secret_value.return_value = {'SecretString': '{"VISUAL_CROSSING_KEY":"k"}'}

        def client_factory(service):
            return {'s3': mock_s3, 'textract': mock_textract, 'secretsmanager': mock_secrets}.get(service, MagicMock())

        mock_boto.side_effect = client_factory
        return mock_s3, mock_textract, mock_secrets

    @patch('boto3.client')
    def test_no_table_quarantines_and_returns_404(self, mock_boto):
        mock_s3, _, _ = self._setup_mock_boto(mock_boto, textract_blocks=[])
        response = lambda_function.lambda_handler(self._base_event(), None)
        self.assertEqual(response['statusCode'], 404)
        mock_s3.copy_object.assert_called_once()  # quarantine was triggered

    @patch('boto3.client')
    def test_already_processed_returns_200_without_textract(self, mock_boto):
        mock_s3 = MagicMock()
        mock_s3.get_object_tagging.return_value = {
            'TagSet': [{'Key': 'ParkinSync-Status', 'Value': 'processed'}]
        }
        mock_boto.return_value = mock_s3
        response = lambda_function.lambda_handler(self._base_event(), None)
        self.assertEqual(response['statusCode'], 200)
        self.assertIn('Already processed', response['body'])

    @patch('boto3.client')
    def test_review_prefix_file_is_skipped(self, mock_boto):
        response = lambda_function.lambda_handler(
            self._base_event(key='review/log.jpg'), None
        )
        self.assertEqual(response['statusCode'], 200)
        self.assertIn('Skipped', response['body'])
        mock_boto.assert_not_called()


if __name__ == '__main__':
    unittest.main()
