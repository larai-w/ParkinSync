"""Synthetic date cells and mocked Sheets; no production records or writes."""
import datetime
import unittest
from unittest.mock import MagicMock

import indoor_temp_logger as logger


class TestJapaneseDateBoundaries(unittest.TestCase):
    def test_rejects_date_range(self):
        self.assertIsNone(logger._parse_date('2026年4月20日〜21日'))

    def test_rejects_second_date(self):
        self.assertIsNone(logger._parse_date('4月20日、4月21日', year=2026))

    def test_rejects_trailing_note(self):
        self.assertIsNone(logger._parse_date('4月20日 合計', year=2026))

    def test_rejects_weekday_followed_by_range(self):
        self.assertIsNone(logger._parse_date('4月20日(月)〜21日', year=2026))

    def test_preserves_supported_weekday_annotation(self):
        for text in ('4月20日(月)', '4月20日（月）', ' 4月20日 （月曜日） '):
            with self.subTest(text=text):
                self.assertEqual(logger._parse_date(text, year=2026), datetime.date(2026, 4, 20))

    def test_plain_explicit_date_remains_supported(self):
        self.assertEqual(logger._parse_date('2026年4月20日'), datetime.date(2026, 4, 20))

    def test_range_does_not_receive_daily_write(self):
        service = MagicMock()
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.get.return_value.execute.return_value = {'values': [['2026', '4月20日〜21日']]}
        result = logger.sync_daily_aggregate(service, 'synthetic-sheet',
            [['2026-04-20 09:00', 20.0]], '2026-04-20')
        self.assertEqual(result['status'], 'master-date-missing')
        values_api.update.assert_not_called()

    def test_range_does_not_receive_backfill_write(self):
        service = MagicMock()
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.get.return_value.execute.side_effect = [
            {'values': [['2026', '4月20日〜21日']]}, {'values': []}]
        result = logger.backfill_missing_aggregates(service, 'synthetic-sheet',
            [['2026-04-20 09:00', 20.0]], datetime.date(2026, 4, 21), days=1)
        self.assertEqual(result['filled'], 0)
        self.assertEqual(result['coverage']['row_missing'], 1)
        self.assertEqual(result['unparsed_dates'], 1)
        values_api.batchUpdate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
