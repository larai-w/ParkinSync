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


class TestWeatherEmoji(unittest.TestCase):

    def test_maps_conditions_to_emoji(self):
        self.assertEqual(handler.get_weather_emoji("Rain, Overcast"), "☔")
        self.assertEqual(handler.get_weather_emoji("Clear"), "☀️")
        self.assertEqual(handler.get_weather_emoji("Snow"), "❄️")

    def test_unknown_condition_falls_back(self):
        self.assertEqual(handler.get_weather_emoji("Freezing Fog"), "🌡️")


class TestLambdaHandler(unittest.TestCase):

    @patch('boto3.client')
    def test_returns_404_when_no_table_detected(self, mock_boto):
        """Handler returns 404 when Textract finds no tables in the document."""
        mock_textract = MagicMock()
        mock_textract.analyze_document.return_value = {'Blocks': []}

        mock_secrets = MagicMock()
        mock_secrets.get_secret_value.return_value = {
            'SecretString': '{"VISUAL_CROSSING_KEY":"k","GOOGLE_SHEET_ID":"s"}'
        }

        # Real code calls boto3.client('secretsmanager', region_name=...),
        # so the factory must accept extra args/kwargs.
        def client_factory(service, *args, **kwargs):
            return mock_textract if service == 'textract' else mock_secrets
        mock_boto.side_effect = client_factory

        event = {
            'Records': [{
                's3': {'bucket': {'name': 'test-bucket'}, 'object': {'key': 'test.pdf'}}
            }]
        }

        response = handler.lambda_handler(event, None)
        self.assertEqual(response['statusCode'], 404)
        self.assertIn('No table detected', response['body'])


if __name__ == '__main__':
    unittest.main()
