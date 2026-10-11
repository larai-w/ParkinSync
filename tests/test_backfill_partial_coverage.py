"""Backfill diagnostics distinguish occupied partial rows without overwriting."""
import copy
import datetime
import unittest
from unittest.mock import MagicMock

import indoor_temp_logger as logger


class BackfillPartialCoverageTests(unittest.TestCase):
    def run_backfill(self, aggregate_rows):
        original = copy.deepcopy(aggregate_rows)
        service = MagicMock()
        api = service.spreadsheets.return_value.values.return_value
        dates = [f'2026-04-{19 - i:02d}' for i in range(len(aggregate_rows))]
        api.get.return_value.execute.side_effect = [
            {'values': [['', day] for day in dates]},
            {'values': aggregate_rows},
        ]
        telemetry = [[f'{day} 09:00', 20.0, f'synthetic-{i}']
                     for i, day in enumerate(dates)]
        result = logger.backfill_missing_aggregates(
            service, 'synthetic-sheet', telemetry, datetime.date(2026, 4, 20), days=5)
        self.assertEqual(aggregate_rows, original)
        self.assertEqual(api.get.call_count, 2)
        return result, api

    def test_partial_rows_are_not_counted_as_fully_populated(self):
        for row in (['manual note'], ['', 20], ['summary', 20, '', 22],
                    ['summary', 20, 18, '  '], ['summary', 20, None, 22]):
            with self.subTest(row=row):
                result, api = self.run_backfill([row])
                self.assertEqual(result['coverage']['already_filled'], 0)
                self.assertEqual(result['coverage']['partially_filled'], 1)
                self.assertEqual(result['filled'], 0)
                api.batchUpdate.assert_not_called()

    def test_four_populated_cells_include_numeric_zero(self):
        result, api = self.run_backfill([['summary', 0, 0, 0]])
        self.assertEqual(result['coverage']['already_filled'], 1)
        self.assertEqual(result['coverage']['partially_filled'], 0)
        api.batchUpdate.assert_not_called()

    def test_empty_row_can_still_be_backfilled(self):
        result, api = self.run_backfill([['', '', '', '']])
        self.assertEqual(result['filled'], 1)
        self.assertEqual(result['coverage']['already_filled'], 0)
        self.assertEqual(result['coverage']['partially_filled'], 0)
        api.batchUpdate.assert_called_once()

    def test_mixed_rows_keep_counts_and_only_write_empty_row(self):
        result, api = self.run_backfill([
            ['summary', 20, 18, 22], ['manual note'], []])
        self.assertEqual(result['coverage']['row_found'], 3)
        self.assertEqual(result['coverage']['already_filled'], 1)
        self.assertEqual(result['coverage']['partially_filled'], 1)
        self.assertEqual(result['filled'], 1)
        updates = api.batchUpdate.call_args.kwargs['body']['data']
        self.assertEqual([update['range'] for update in updates], ["'Sheet1'!U4:X4"])


if __name__ == '__main__':
    unittest.main()
