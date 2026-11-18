import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock

from flask import Flask
from openpyxl import load_workbook

import daily_replenishment_operation as operation
from tests.test_daily_replenishment import build_sample_dataset


class ReplenishmentTrendSnapshotTests(unittest.TestCase):
    def test_fifteen_days_end_at_snapshot_cutoff_and_missing_days_are_zero(self):
        query = Mock(return_value=[
            ('SKU-A', date(2026, 11, 2), 4),
            ('SKU-A', date(2026, 11, 16), 7),
            ('SKU-A', date(2026, 11, 16), 2),
            ('SKU-A', date(2026, 11, 17), 100),
            ('OTHER', date(2026, 11, 16), 99),
        ])
        sheet = operation._sales_trend_snapshot_sheet(
            {'sales_end': date(2026, 11, 16), 'sales_source': '下单'},
            {'SKU-A', 'SKU-B'}, query_executor=query,
        )
        query.assert_called_once()
        self.assertIn('FROM GuangGao', query.call_args.args[0])
        self.assertEqual(sheet['columns'][1:], [f'2026-11-{day:02d}' for day in range(2, 17)])
        self.assertEqual(sheet['rows'][0], ['SKU-A', 4, *([0] * 13), 9])
        self.assertEqual(sheet['rows'][1], ['SKU-B', *([0] * 15)])

    def test_roundtrip_preserves_main_columns_and_scopes_trend_skus(self):
        app = Flask(__name__)
        with tempfile.TemporaryDirectory() as temp, app.app_context():
            path = Path(temp) / 'snapshot.xlsx'
            main = build_sample_dataset()
            trend = operation._sales_trend_snapshot_sheet(
                {'sales_end': '2026-11-16', 'sales_source': '付款'},
                {'SKU-A', 'SKU-B'}, query_executor=lambda sql: [],
            )
            operation.save_operation_workbook({'main': main, 'sheets': {operation.SALES_TREND_SHEET: trend}}, path)
            payload = operation.load_snapshot(path)
            self.assertEqual(payload['sheets'][operation.base.SHEET_NAME]['columns'], list(main['columns']))
            scoped = operation._scope_snapshot_payload(payload, {'visible_skus': {'SKU-A'}, 'read_stores': {'1'}})
            self.assertEqual(len(scoped['sheets'][operation.SALES_TREND_SHEET]['rows']), 1)
            self.assertEqual(scoped['sheets'][operation.SALES_TREND_SHEET]['rows'][0][0], 'SKU-A')
            book = load_workbook(path)
            try:
                self.assertEqual(book[operation.SALES_TREND_SHEET].sheet_state, 'hidden')
            finally:
                book.close()


if __name__ == '__main__':
    unittest.main()
