import copy
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from openpyxl import Workbook, load_workbook
import daily_replenishment_operation as op


class SharedRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.app.config['DAILY_REPLENISHMENT_OPERATION_OUTPUT_DIR'] = self.temp.name
        self.payload = {'sheets': {op.base.SHEET_NAME: {'columns': ['运营', '店铺', '分类', 'SKU'], 'rows': [['高冉', '1', 'A', 'SKU1'], ['其他运营', '2', 'B', 'SKU2']]}}, 'generation': {}}
        op._refresh_jobs.clear()

    def tearDown(self):
        self.temp.cleanup()

    def access(self, store):
        return {'read_stores': {store}, 'write_stores': {store}, 'visible_skus': {'SKU' + store}, 'can_write': True}

    def test_first_operator_refreshes_all_and_each_response_is_scoped(self):
        def save(dataset, path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'snapshot')
            return path
        with self.app.test_request_context('/'), patch.object(op, '_current_user_name', return_value='高冉'), patch.object(op, 'scoped_query_executor', return_value=(lambda sql: [], self.access('1'))), patch.object(op.base, 'resolve_source_path', return_value=None), patch.object(op, 'generate_operation_dataset', return_value={}) as generate, patch.object(op, 'save_operation_workbook', side_effect=save) as saved, patch.object(op, '_sheet_payload', return_value=copy.deepcopy(self.payload)), patch.object(op._refresh_executor, 'submit', side_effect=lambda f: f()):
            response, status = op.refresh.__wrapped__()
            self.assertEqual(status, 202)
            self.assertIs(generate.call_args.kwargs['query_executor'], op.base.sf_db)
            self.assertEqual(saved.call_args.args[1].parent, op.get_shared_snapshot_path().parent)
            full = op.load_snapshot_cached(op.get_shared_today_snapshot())
            self.assertEqual(len(full['sheets'][op.base.SHEET_NAME]['rows']), 2)
            job_id = response.get_json()['jobId']
            result = op.refresh_status.__wrapped__(job_id).get_json()
            self.assertEqual([r[1] for r in result['sheets'][op.base.SHEET_NAME]['rows']], ['1'])
        with self.app.test_request_context('/'), patch.object(op, '_current_user_name', return_value='其他运营'), patch.object(op, 'scoped_query_executor', return_value=(lambda sql: [], self.access('2'))):
            result = op.data.__wrapped__().get_json()
            self.assertEqual([r[1] for r in result['sheets'][op.base.SHEET_NAME]['rows']], ['2'])
            exported = op.download.__wrapped__()
            exported.direct_passthrough = False
            book = load_workbook(BytesIO(exported.get_data()), read_only=True)
            self.assertEqual(list(book[op.base.SHEET_NAME].values)[1:], [('其他运营', '2', 'B', 'SKU2')])
            book.close()

    def test_personal_snapshot_is_never_shared(self):
        with self.app.app_context():
            own = op.get_snapshot_path(user_name='高冉')
            own.parent.mkdir(parents=True, exist_ok=True)
            own.write_bytes(b'large but scoped snapshot' * 100)
            self.assertIsNone(op.get_shared_today_snapshot())
            self.assertEqual(op._resolve_snapshot_for_user('高冉'), (None, True))
