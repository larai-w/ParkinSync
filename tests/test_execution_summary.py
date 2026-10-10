"""Bounded OCR invocation summaries must not alter processing or copy payloads."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ParkinSync_OCR_Handler as handler


REQUEST = '12345678-1234-1234-1234-123456789abc'
PREFIX = '[EXECUTION_SUMMARY] '


class ExecutionSummaryTests(unittest.TestCase):
    def invoke(self, result, context=None):
        with patch.object(handler, '_process_event', return_value=result) as process:
            with patch('builtins.print') as output:
                event = {'private': 'DO_NOT_COPY_EVENT'}
                returned = handler.lambda_handler(event, context)
        self.assertIs(returned, result)
        process.assert_called_once_with(event, context)
        output.assert_called_once()
        line = output.call_args.args[0]
        self.assertTrue(line.startswith(PREFIX))
        return line, json.loads(line[len(PREFIX):])

    def test_summary_copies_only_allowlisted_fields(self):
        result = {'status':'processed', 'rows_processed':2,
                  'body':'DO_NOT_COPY_BODY', 'key':'DO_NOT_COPY_KEY',
                  'secret':'DO_NOT_COPY_SECRET', 'health':'DO_NOT_COPY_HEALTH'}
        line, summary = self.invoke(result, SimpleNamespace(aws_request_id=REQUEST))
        self.assertNotIn('DO_NOT_COPY', line)
        self.assertEqual(summary, {
            'schema_version':1, 'handler':'ocr', 'request_id':REQUEST,
            'event_id':None, 'execution_outcome':'returned',
            'processing_status':'processed', 'rows_processed':2,
            'source_freshness':'UNMEASURED', 'human_review':'UNVERIFIED',
        })

    def test_zero_rows_is_preserved_without_marking_reviewed(self):
        _, summary = self.invoke({'status':'processed', 'rows_processed':0})
        self.assertEqual(summary['rows_processed'], 0)
        self.assertEqual(summary['human_review'], 'UNVERIFIED')

    def test_known_outcomes_are_distinct(self):
        for status in ('processed_tagging_warning','already_processed','quarantined',
                       'quarantined_permanent_failure','skipped'):
            with self.subTest(status=status):
                _, summary = self.invoke({'status':status})
                self.assertEqual(summary['processing_status'], status)
                self.assertEqual(summary['execution_outcome'], 'returned')
                self.assertIsNone(summary['rows_processed'])

    def test_missing_or_invalid_request_id_is_unknown(self):
        for context in (None, SimpleNamespace(aws_request_id='DO_NOT_COPY_NAME'),
                        SimpleNamespace(aws_request_id=REQUEST+'\n'),
                        SimpleNamespace(aws_request_id=123)):
            with self.subTest(context=context):
                line, summary = self.invoke({'status':'skipped'}, context)
                self.assertIsNone(summary['request_id'])
                self.assertNotIn('DO_NOT_COPY', line)

    def test_unknown_result_is_not_success(self):
        for result in (None, 'DO_NOT_COPY_BODY', {'status':'DO_NOT_COPY_STATUS'},
                       {'status':['DO_NOT_COPY_STATUS']}):
            with self.subTest(result=result):
                line, summary = self.invoke(result)
                self.assertEqual(summary['processing_status'], 'unknown')
                self.assertIsNone(summary['rows_processed'])
                self.assertNotIn('DO_NOT_COPY', line)

    def test_non_integer_or_unbounded_rows_are_unknown(self):
        for rows in (True, -1, 1.5, float('nan'), float('inf'), '2', 2**53):
            with self.subTest(rows=rows):
                _, summary = self.invoke({'status':'processed', 'rows_processed':rows})
                self.assertIsNone(summary['rows_processed'])

    def test_original_exception_is_re_raised_without_text(self):
        original = RuntimeError('DO_NOT_COPY_EXCEPTION')
        with patch.object(handler, '_process_event', side_effect=original):
            with patch('builtins.print') as output:
                with self.assertRaises(RuntimeError) as caught:
                    handler.lambda_handler({}, SimpleNamespace(aws_request_id=REQUEST))
        self.assertIs(caught.exception, original)
        line = output.call_args.args[0]
        self.assertNotIn('DO_NOT_COPY', line)
        summary = json.loads(line[len(PREFIX):])
        self.assertEqual(summary['execution_outcome'], 'raised')
        self.assertEqual(summary['processing_status'], 'unknown')

    def test_log_failure_does_not_mask_return(self):
        result = {'status':'processed'}
        with patch.object(handler, '_process_event', return_value=result):
            with patch('builtins.print', side_effect=OSError('output unavailable')):
                self.assertIs(handler.lambda_handler({}, None), result)

    def test_log_failure_does_not_mask_exception(self):
        original = RuntimeError('DO_NOT_COPY_EXCEPTION')
        with patch.object(handler, '_process_event', side_effect=original):
            with patch('builtins.print', side_effect=OSError('output unavailable')):
                with self.assertRaises(RuntimeError) as caught:
                    handler.lambda_handler({}, None)
        self.assertIs(caught.exception, original)

    def test_unreadable_context_does_not_mask_return(self):
        class Context:
            @property
            def aws_request_id(self):
                raise RuntimeError('DO_NOT_COPY_CONTEXT')
        result = {'status':'processed'}
        with patch.object(handler, '_process_event', return_value=result):
            with patch('builtins.print') as output:
                self.assertIs(handler.lambda_handler({}, Context()), result)
        output.assert_not_called()


if __name__ == '__main__':
    unittest.main()
