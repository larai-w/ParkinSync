"""Indoor summaries expose outcomes, never telemetry, dates or raw payloads."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import indoor_temp_logger as handler

REQUEST = '12345678-1234-1234-1234-123456789abc'
EVENT = 'abcdefab-1234-1234-1234-123456789abc'
PREFIX = '[EXECUTION_SUMMARY] '


class IndoorExecutionSummaryTests(unittest.TestCase):
    def invoke(self, result, event=None, context=None):
        with patch.object(handler, '_process_event', return_value=result) as process:
            with patch('builtins.print') as output:
                returned = handler.lambda_handler(event, context)
        self.assertIs(returned, result)
        process.assert_called_once_with(event, context)
        output.assert_called_once()
        line = output.call_args.args[0]
        self.assertTrue(line.startswith(PREFIX))
        return line, json.loads(line[len(PREFIX):])

    def result(self, **fields):
        return {'statusCode':200, 'body':json.dumps(fields)}

    def test_allowlist_omits_payload_temperature_dates_and_credentials(self):
        result = self.result(sample='logged', aggregate='updated', backfilled=2,
                             temperature='DO_NOT_COPY_TEMP', date='DO_NOT_COPY_DATE',
                             secret='DO_NOT_COPY_SECRET')
        line, summary = self.invoke(result, {'id':EVENT,'detail':'DO_NOT_COPY_EVENT'},
                                    SimpleNamespace(aws_request_id=REQUEST))
        self.assertNotIn('DO_NOT_COPY', line)
        self.assertEqual(summary, {
            'schema_version':1, 'handler':'indoor', 'request_id':REQUEST,
            'event_id':EVENT, 'execution_outcome':'returned',
            'processing_status':'updated', 'sample_status':'logged',
            'backfilled_count':2, 'backfill_completion':'UNVERIFIED',
            'source_freshness':'UNMEASURED','human_review':'UNVERIFIED',
        })

    def test_incomplete_aggregates_remain_distinct(self):
        for status in ('updated','master-date-missing','duplicate-master-date','no-valid-samples'):
            with self.subTest(status=status):
                _, summary = self.invoke(self.result(sample='logged',aggregate=status))
                self.assertEqual(summary['processing_status'],status)
                self.assertEqual(summary['execution_outcome'],'returned')
                self.assertEqual(summary['source_freshness'],'UNMEASURED')

    def test_duplicate_is_not_classified_as_new_sample(self):
        _, summary = self.invoke(self.result(sample='duplicate',aggregate='updated'))
        self.assertEqual(summary['sample_status'],'duplicate')

    def test_zero_backfill_is_not_completion_evidence(self):
        _, summary = self.invoke(self.result(backfilled=0))
        self.assertEqual(summary['backfilled_count'],0)
        self.assertEqual(summary['backfill_completion'],'UNVERIFIED')

    def test_invalid_backfill_count_remains_unknown(self):
        for count in (True,-1,1.2,float('nan'),float('inf'),'2',2**53):
            with self.subTest(count=count):
                _, summary = self.invoke(self.result(backfilled=count))
                self.assertIsNone(summary['backfilled_count'])

    def test_unknown_fields_are_not_copied(self):
        for value in ('DO_NOT_COPY_VALUE',['DO_NOT_COPY_VALUE'],None):
            with self.subTest(value=value):
                line, summary = self.invoke(self.result(sample=value,aggregate=value))
                self.assertNotIn('DO_NOT_COPY',line)
                self.assertEqual(summary['sample_status'],'unknown')
                self.assertEqual(summary['processing_status'],'unknown')

    def test_invalid_or_absent_body_is_not_success(self):
        for result in (None,{'statusCode':200},{'body':'DO_NOT_COPY_BODY'},
                       {'body':'[]'},{'body':'null'},{'body':{'temperature':99}}):
            with self.subTest(result=result):
                line, summary = self.invoke(result)
                self.assertNotIn('DO_NOT_COPY',line)
                self.assertEqual(summary['processing_status'],'unknown')
                self.assertIsNone(summary['backfilled_count'])

    def test_oversized_body_is_not_parsed_or_copied(self):
        result=self.result(sample='logged',aggregate='updated',extra='x'*2048)
        _, summary = self.invoke(result)
        self.assertEqual(summary['processing_status'],'unknown')

    def test_invalid_ids_are_not_copied_or_derived(self):
        for value in ('DO_NOT_COPY_NAME',REQUEST+'\n',123,None):
            with self.subTest(value=value):
                line, summary = self.invoke(self.result(),{'id':value},
                                            SimpleNamespace(aws_request_id=value))
                self.assertNotIn('DO_NOT_COPY',line)
                self.assertIsNone(summary['request_id'])
                self.assertIsNone(summary['event_id'])

    def test_manual_event_without_id_stays_unknown(self):
        for event in (None,{},'DO_NOT_COPY_EVENT'):
            with self.subTest(event=event):
                _, summary = self.invoke(self.result(),event)
                self.assertIsNone(summary['event_id'])

    def test_original_exception_is_preserved_without_text(self):
        original=RuntimeError('DO_NOT_COPY_EXCEPTION')
        with patch.object(handler,'_process_event',side_effect=original):
            with patch('builtins.print') as output:
                with self.assertRaises(RuntimeError) as caught:
                    handler.lambda_handler({'id':EVENT},SimpleNamespace(aws_request_id=REQUEST))
        self.assertIs(caught.exception,original)
        line=output.call_args.args[0]
        self.assertNotIn('DO_NOT_COPY',line)
        summary=json.loads(line[len(PREFIX):])
        self.assertEqual(summary['execution_outcome'],'raised')
        self.assertEqual(summary['processing_status'],'unknown')
        self.assertEqual(summary['event_id'],EVENT)
        self.assertIsNone(summary['backfilled_count'])

    def test_output_failure_preserves_return(self):
        result=self.result(aggregate='updated')
        with patch.object(handler,'_process_event',return_value=result):
            with patch('builtins.print',side_effect=OSError('unavailable')):
                self.assertIs(handler.lambda_handler({},None),result)

    def test_output_failure_preserves_exception(self):
        original=RuntimeError('DO_NOT_COPY_EXCEPTION')
        with patch.object(handler,'_process_event',side_effect=original):
            with patch('builtins.print',side_effect=OSError('unavailable')):
                with self.assertRaises(RuntimeError) as caught:
                    handler.lambda_handler({},None)
        self.assertIs(caught.exception,original)

    def test_context_read_failure_preserves_result(self):
        class Context:
            @property
            def aws_request_id(self):
                raise RuntimeError('DO_NOT_COPY_CONTEXT')
        result=self.result(aggregate='updated')
        with patch.object(handler,'_process_event',return_value=result):
            with patch('builtins.print') as output:
                self.assertIs(handler.lambda_handler({},Context()),result)
        output.assert_not_called()


if __name__ == '__main__': unittest.main()
