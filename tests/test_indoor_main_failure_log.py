"""Synthetic main failures retain their identity without copying error bodies."""
import contextlib
import io
import json
import unittest
from unittest.mock import MagicMock, patch

import indoor_temp_logger as logger


class UnprintableError(Exception):
    def __str__(self):
        raise RuntimeError('synthetic formatting failure')


class MainFailureLogTests(unittest.TestCase):
    def invoke_failure(self, error, broken_output=False):
        client = MagicMock()
        client.get_secret_value.side_effect = error
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(logger.boto3, 'client', return_value=client))
            switchbot = stack.enter_context(patch.object(logger, '_switchbot_status'))
            sheets = stack.enter_context(patch.object(logger, 'build'))
            stack.enter_context(contextlib.redirect_stdout(output))
            if broken_output:
                stack.enter_context(patch('builtins.print', side_effect=OSError('synthetic output failure')))
            caught = None
            try:
                logger.lambda_handler({}, None)
            except Exception as raised:
                caught = raised
            self.assertIs(caught, error)
            client.get_secret_value.assert_called_once()
            switchbot.assert_not_called()
            sheets.assert_not_called()
        return output.getvalue()

    def test_error_body_is_not_copied_into_application_logs(self):
        marker = 'SYNTHETIC_PRIVATE_RESPONSE_MARKER'
        logs = self.invoke_failure(RuntimeError(marker))
        self.assertNotIn(marker, logs)
        self.assertIn('Telemetry logging failed: processing error', logs)
        summaries = [json.loads(line.split(' ', 1)[1]) for line in logs.splitlines()
                     if line.startswith('[EXECUTION_SUMMARY] ')]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]['execution_outcome'], 'raised')
        self.assertEqual(summaries[0]['processing_status'], 'unknown')

    def test_unprintable_error_keeps_the_original_exception(self):
        self.invoke_failure(UnprintableError())

    def test_output_failure_keeps_the_original_exception(self):
        self.invoke_failure(RuntimeError('synthetic original'), broken_output=True)


if __name__ == '__main__':
    unittest.main()
