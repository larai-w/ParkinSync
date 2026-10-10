import unittest
from unittest.mock import MagicMock, patch

import ParkinSync_OCR_Handler as handler


class QuarantineCopyOutcomeTests(unittest.TestCase):
    def test_copy_success_returns_true(self):
        with patch.dict('os.environ', {'SNS_TOPIC_ARN': ''}):
            self.assertIs(handler._quarantine_and_notify(MagicMock(), 'synthetic-bucket', 'synthetic-scan.pdf', 'synthetic failure'), True)

    def test_copy_failure_notifies_without_claiming_copy_destination(self):
        s3, sns = MagicMock(), MagicMock()
        s3.copy_object.side_effect = RuntimeError('synthetic copy failure')
        with patch.dict('os.environ', {'SNS_TOPIC_ARN': 'synthetic-topic'}), patch.object(handler.boto3, 'client', return_value=sns):
            copied = handler._quarantine_and_notify(s3, 'synthetic-bucket', 'synthetic-scan.pdf', 'synthetic failure')
        self.assertIs(copied, False)
        sns.publish.assert_called_once()
        message = sns.publish.call_args.kwargs['Message']
        self.assertNotIn('コピー先:', message)
        self.assertIn('コピー失敗', message)
        self.assertIn('原本', message)

    def test_sns_failure_does_not_turn_successful_copy_into_failure(self):
        sns = MagicMock(); sns.publish.side_effect = RuntimeError('synthetic SNS failure')
        with patch.dict('os.environ', {'SNS_TOPIC_ARN': 'synthetic-topic'}), patch.object(handler.boto3, 'client', return_value=sns):
            self.assertIs(handler._quarantine_and_notify(MagicMock(), 'synthetic-bucket', 'synthetic-scan.pdf', 'synthetic failure'), True)

    def test_copy_failure_without_topic_returns_false_and_skips_sns(self):
        s3 = MagicMock(); s3.copy_object.side_effect = RuntimeError('synthetic copy failure')
        with patch.dict('os.environ', {'SNS_TOPIC_ARN': ''}), patch.object(handler.boto3, 'client') as clients:
            self.assertIs(handler._quarantine_and_notify(s3, 'synthetic-bucket', 'synthetic-scan.pdf', 'synthetic failure'), False)
        clients.assert_not_called()

    def call_handler(self, copy_fails=False, textract_error=None):
        clients = {name: MagicMock() for name in ('s3', 'textract', 'secretsmanager')}
        clients['s3'].get_object_tagging.return_value = {'TagSet': []}
        if copy_fails: clients['s3'].copy_object.side_effect = RuntimeError('synthetic copy failure')
        clients['textract'].analyze_document.return_value = {'Blocks': []}
        if textract_error is not None: clients['textract'].analyze_document.side_effect = textract_error
        clients['secretsmanager'].get_secret_value.return_value = {'SecretString': '{"VISUAL_CROSSING_KEY":"synthetic","GOOGLE_SHEET_ID":"synthetic"}'}
        event = {'Records': [{'s3': {'bucket': {'name': 'synthetic-bucket'}, 'object': {'key': 'synthetic-scan.pdf'}}}]}
        with patch.dict('os.environ', {'SNS_TOPIC_ARN': ''}), patch.object(handler.boto3, 'client', side_effect=lambda name, **kwargs: clients[name]):
            return handler.lambda_handler(event, None)

    def test_no_table_copy_failure_has_false_flag_and_original_upload_action(self):
        result = self.call_handler(copy_fails=True)
        self.assertEqual(result['statusCode'], 404)
        self.assertEqual(result['status'], 'quarantined')
        self.assertIs(result.get('quarantined'), False)
        self.assertIn('original upload', result['next_action'])

    def test_no_table_copy_success_has_true_flag(self):
        result = self.call_handler()
        self.assertEqual(result['statusCode'], 404)
        self.assertIs(result.get('quarantined'), True)

    def test_permanent_failure_copy_failure_is_not_marked_quarantined(self):
        class UnsupportedDocumentException(Exception): pass
        result = self.call_handler(copy_fails=True, textract_error=UnsupportedDocumentException('synthetic unsupported format'))
        self.assertEqual(result['statusCode'], 422)
        self.assertEqual(result['status'], 'quarantined_permanent_failure')
        self.assertIs(result['quarantined'], False)
        self.assertIn('original upload', result['next_action'])

    def test_transient_error_identity_is_preserved_after_copy_failure(self):
        original = RuntimeError('synthetic transient failure')
        with self.assertRaises(RuntimeError) as caught:
            self.call_handler(copy_fails=True, textract_error=original)
        self.assertIs(caught.exception, original)


if __name__ == '__main__': unittest.main()
