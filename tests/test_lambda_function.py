import unittest
from unittest.mock import patch, MagicMock
import lambda_function

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
        self.assertIn('No table found', response['body'])

if __name__ == '__main__':
    unittest.main()
