import unittest
from unittest.mock import patch, MagicMock
import lambda_function

class TestDateParsing(unittest.TestCase):

    def setUp(self):
        # Pin the fallback year so tests are stable regardless of when they run
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


class TestParkinSyncLambda(unittest.TestCase):

    def test_date_parsing_logic(self):
        """Test if the weather date parsing logic works correctly"""
        # Testing the helper function directly
        # Note: We mock the requests.get to avoid actual API calls during testing
        with patch('requests.get') as mocked_get:
            mocked_get.return_value.json.return_value = {
                'days': [{'temp': 20.5, 'conditions': 'Clear'}]
            }
            
            result = lambda_function.get_historical_weather("April 20", "fake_key")
            self.assertIn("20.5C", result)
            self.assertIn("Clear", result)

    @patch('boto3.client')
    def test_lambda_handler_no_table_error(self, mock_boto):
        """Test if the handler correctly identifies when no table is found in Textract"""
        # Mocking Textract response with no tables
        mock_textract = MagicMock()
        mock_textract.analyze_document.return_value = {'Blocks': []}
        
        # Mocking Secrets Manager
        mock_secrets = MagicMock()
        mock_secrets.get_secret_value.return_value = {'SecretString': '{"key":"val"}'}
        
        mock_boto.side_effect = lambda service: mock_textract if service == 'textract' else mock_secrets

        event = {
            'Records': [{
                's3': {'bucket': {'name': 'test-bucket'}, 'object': {'key': 'test.pdf'}}
            }]
        }
        
        response = lambda_function.lambda_handler(event, None)
        self.assertEqual(response['statusCode'], 404)
        self.assertIn('No table detected', response['body'])
if __name__ == '__main__':
    unittest.main()