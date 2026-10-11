"""Synthetic ambiguous year cells; Sheets access is mocked."""
import datetime
import unittest
from unittest.mock import MagicMock

import indoor_temp_logger as logger


class TestAmbiguousYear(unittest.TestCase):
    def test_distinct_years_are_not_a_year_source(self):
        for text in ('2025 / 2026', '2026年から2025年', '2025-12-31 / 2026-01-01'):
            with self.subTest(text=text):
                self.assertIsNone(logger._year_from_cell(text))

    def test_single_year_and_timestamp_remain_supported(self):
        for text in ('2026', '2026年', '2026-04-20 09:00:00', '2026 / 2026'):
            with self.subTest(text=text):
                self.assertEqual(logger._year_from_cell(text), 2026)

    def test_ambiguous_year_is_not_indexed(self):
        result = logger.index_master_dates([['2025 / 2026', 'April 20']])
        self.assertEqual(result['by_date'], {})
        self.assertEqual(result['unparsed'], 1)

    def test_explicit_date_does_not_need_year_source(self):
        result = logger.index_master_dates([['2025 / 2026', '2026-04-20']])
        self.assertEqual(result['by_date'], {datetime.date(2026, 4, 20): [2]})

    def test_diagnosis_agrees_with_unparsed_index(self):
        result = logger.diagnose_year_source([['2025 / 2026', 'April 20']])
        self.assertEqual(result['parsed_years'], {})
        self.assertEqual(result['unparsed_rows'], 1)

    def test_ambiguous_year_does_not_receive_daily_write(self):
        service = MagicMock()
        values = service.spreadsheets.return_value.values.return_value
        values.get.return_value.execute.return_value = {'values': [['2025 / 2026', 'April 20']]}
        result = logger.sync_daily_aggregate(service, 'synthetic-sheet',
            [['2025-04-20 09:00', 20.0]], '2025-04-20')
        self.assertEqual(result['status'], 'master-date-missing')
        values.update.assert_not_called()

    def test_ambiguous_year_does_not_receive_backfill_write(self):
        service = MagicMock()
        values = service.spreadsheets.return_value.values.return_value
        values.get.return_value.execute.side_effect = [
            {'values': [['2025 / 2026', 'April 20']]}, {'values': []}]
        result = logger.backfill_missing_aggregates(service, 'synthetic-sheet',
            [['2025-04-20 09:00', 20.0]], datetime.date(2025, 4, 21), days=1)
        self.assertEqual(result['filled'], 0)
        self.assertEqual(result['unparsed_dates'], 1)
        values.batchUpdate.assert_not_called()
