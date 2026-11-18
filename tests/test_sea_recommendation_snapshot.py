import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
from openpyxl import load_workbook

import daily_replenishment_operation as operation
from tests.test_daily_replenishment import build_sample_dataset


class SeaRecommendationSnapshotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.app = Flask(__name__)
        self.app.config['DAILY_REPLENISHMENT_OPERATION_OUTPUT_DIR'] = temp.name
        context = self.app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.access = {'visible_skus': {'SKU-A'}, 'read_stores': {'1'}, 'can_write': True}
        self.path = Path(temp.name) / 'snapshot.xlsx'

    def save(self, recommendations=None):
        sheets = {} if recommendations is None else {
            operation.SEA_RECOMMENDATION_SHEET: {'columns': ['SKU', '日均销量'], 'rows': recommendations}
        }
        operation.save_operation_workbook({'main': build_sample_dataset(), 'sheets': sheets}, self.path)

    def get(self, query):
        with self.app.test_request_context(method='GET'), \
             patch.object(operation, '_current_user_name', return_value='test'), \
             patch.object(operation, 'scoped_query_executor', return_value=(query, self.access)), \
             patch.object(operation, '_resolve_snapshot_for_user', return_value=(self.path, True)):
            return operation.sea_shipping_recommendations.__wrapped__().get_json()

    def test_repeated_reads_use_snapshot_and_still_scope_skus(self):
        self.save([['SKU-A', 21.5], ['SKU-B', 40]])
        query = Mock(side_effect=AssertionError('recommendation reads must not query SQL'))
        for _ in range(2):
            result = self.get(query)
            self.assertEqual(result['items'], [{'sku': 'SKU-A', 'avg_daily_sales': 21.5}])
            self.assertTrue(result['snapshot_ready'])
        query.assert_not_called()
        scoped = operation._scope_snapshot_payload(operation.load_snapshot_cached(self.path), self.access)
        self.assertEqual(scoped['sheets'][operation.SEA_RECOMMENDATION_SHEET]['rows'], [['SKU-A', 21.5]])

    def test_old_snapshot_does_not_fall_back_to_database_and_migrates_once(self):
        self.save()
        query = Mock(return_value=[('SKU-A', 21.5)])
        self.assertFalse(self.get(query)['snapshot_ready'])
        query.assert_not_called()
        self.assertTrue(operation.populate_sea_recommendation_snapshot(self.path, query_executor=query))
        self.assertFalse(operation.populate_sea_recommendation_snapshot(self.path, query_executor=query))
        query.assert_called_once()
        self.assertEqual(self.get(query)['items'][0]['sku'], 'SKU-A')
        query.assert_called_once()

    def test_generation_queries_recommendations_once_and_persists_hidden_sheet(self):
        query = Mock(side_effect=lambda sql: [('SKU-A', 25)] if 'sea_shipping_recommendations' in sql else [])
        with patch.object(operation, '_settings', return_value={}), \
             patch.object(operation.base, 'generate_database_dataset', return_value=build_sample_dataset()), \
             patch.object(operation.base, 'generate_button_sheets', return_value={}):
            dataset = operation.generate_operation_dataset(query_executor=query)
        calls = [call for call in query.call_args_list if 'sea_shipping_recommendations' in call.args[0]]
        self.assertEqual(len(calls), 1)
        operation.save_operation_workbook(dataset, self.path)
        self.assertEqual(operation.load_snapshot(self.path)['sheets'][operation.SEA_RECOMMENDATION_SHEET]['rows'], [['SKU-A', 25]])
        book = load_workbook(self.path)
        self.addCleanup(book.close)
        self.assertEqual(book[operation.SEA_RECOMMENDATION_SHEET].sheet_state, 'hidden')

    def test_successful_add_removes_recommendation_from_persistent_snapshot(self):
        self.save([['SKU-A', 25], ['SKU-B', 40]])
        operation.load_snapshot_cached(self.path)
        query = Mock(return_value=[])
        with self.app.test_request_context(method='POST', json={'skus': ['SKU-A']}), \
             patch.object(operation, '_current_user_name', return_value='test'), \
             patch.object(operation, 'scoped_query_executor', return_value=(query, self.access)), \
             patch.object(operation, 'get_shared_today_snapshot', return_value=self.path), \
             patch.object(operation, 'get_today_snapshot', return_value=None), \
             patch.object(operation, 'dui_db') as write:
            result = operation.sea_shipping_recommendations.__wrapped__().get_json()
        self.assertTrue(result['success'])
        write.assert_called_once()
        self.assertEqual(operation.load_snapshot_cached(self.path)['sheets'][operation.SEA_RECOMMENDATION_SHEET]['rows'], [['SKU-B', 40]])


if __name__ == '__main__':
    unittest.main()
