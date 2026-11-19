import csv
import ast
import io
import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from pathlib import Path
from flask import Flask, jsonify, request

import fba_shipping_service as service


class FbaShippingServiceTests(unittest.TestCase):
    def row(self, **kwargs):
        values = dict(ID=1, Dian='US', DanHao='FBA0001', YunShuFangShi='海运',
                      HuoJianDanHao='TRACK1; TRACK2', ZhuiZongMaGeShu=2,
                      ShiFouTianXie='Y  ', JianChaRiQi=datetime(2026, 11, 19),
                      DaoRuShiJian=datetime(2026, 11, 18))
        values.update(kwargs)
        return service.prepare(values)

    def snapshot(self, records):
        return dict(records=records, loaded_at='2026-11-19 10:00:00', columns=[],
                    available_fields=['date','id','shop'])

    def test_trims_status_and_keeps_record_count_separate_from_parsed(self):
        row = self.row(HuoJianDanHao='A;; B， C\nD\tE', ZhuiZongMaGeShu=8)
        self.assertTrue(row['filled'])
        self.assertEqual(row['n'], 8)
        self.assertEqual(row['parsed_count'], 5)
        self.assertEqual(row['issues'], ['数量待核对'])
        null = self.row(ShiFouTianXie=None, ZhuiZongMaGeShu=None)
        self.assertEqual(null['status'], '')
        self.assertFalse(null['filled'])
        self.assertIsNone(null['n'])
        self.assertFalse(null['issues'])

    def test_missing_and_scientific_are_detected_in_individual_tokens(self):
        self.assertIn('海运追踪码缺失', self.row(HuoJianDanHao=None)['issues'])
        self.assertIn('追踪码格式异常', self.row(HuoJianDanHao='NORMAL; 8.4E+12')['issues'])
        self.assertFalse(self.row(HuoJianDanHao='AMZ-E+123', ZhuiZongMaGeShu=1)['issues'])

    def test_stats_cover_filtered_dataset_not_only_page_or_tab(self):
        records = [self.row(ID=i, DanHao=f'FBA{i}', ShiFouTianXie='Y' if i < 25 else None,
                            HuoJianDanHao='' if i >= 30 else 'A;B') for i in range(45)]
        snapshot = self.snapshot(records)
        result = service.payload(snapshot, {'tab': 'issue', 'page_size': '10', 'page': '2'})
        self.assertEqual(result['stats']['total'], 45)
        self.assertEqual(result['stats']['filled'], 25)
        self.assertEqual(result['total'], 15)
        self.assertEqual(len(result['records']), 5)
        self.assertEqual(result['page'], 2)
        self.assertEqual(service.payload(snapshot, {'page': '999'})['page'], 3)

    def test_searches_ien_tracking_and_applies_multiple_filters(self):
        a = self.row(Ien='GB1234', ID=1)
        b = self.row(Dian='UK', ID=2, HuoJianDanHao='TRACK3', ZhuiZongMaGeShu=1)
        snapshot = self.snapshot([a, b])
        self.assertEqual(service.payload(snapshot, {'q': 'gb1234'})['total'], 1)
        self.assertEqual(service.payload(snapshot, {'q': 'track3', 'dian': 'UK'})['total'], 1)
        self.assertEqual(service.payload(snapshot, {'q': 'track3', 'dian': 'US'})['total'], 0)
        self.assertEqual(service.payload(snapshot, {'q': "' OR 1=1--"})['total'], 0)

    def test_export_obeys_filters_selection_and_protects_formulas(self):
        a = self.row(ID=1, Dian='=danger', Ien='+formula')
        b = self.row(ID=2, Dian='UK')
        snapshot = self.snapshot([a, b])
        output = ''.join(service.csv_rows(snapshot, {'selected': '1'})).lstrip('\ufeff')
        rows = list(csv.reader(io.StringIO(output)))
        self.assertEqual(len(rows), 2)
        self.assertIn("'=danger", rows[1])
        self.assertIn("'+formula", rows[1])
        self.assertEqual(len(list(service.csv_rows(snapshot, {'dian': 'UK', 'selected': '1'}))), 1)

    def test_snapshot_cache_excludes_internal_shipments_and_keeps_nulls(self):
        columns = list(service.FIELDS)
        data = []
        for index, cargo in enumerate(['FBA1', 'IBR2', 'OWS3']):
            values = {'ID': index, 'DanHao': cargo}
            data.append(tuple(values.get(k) for k in columns))
        query = Mock(side_effect=[columns, data])
        with patch.object(service, '_snapshot', None), patch.object(service, '_expires', 0):
            snapshot = service.load_snapshot(query)
            self.assertEqual(len(snapshot['records']), 1)
            self.assertIs(service.load_snapshot(query), snapshot)
            self.assertEqual(query.call_count, 2)


class FbaShippingApiTests(unittest.TestCase):
    def setUp(self):
        source = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8-sig')
        names = ['api_operation_fba_shipping_methods', 'api_operation_fba_shipping_method_shops',
                 'export_operation_fba_shipping_methods']
        functions = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
        for function in functions:
            self.assertTrue(any(isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                                and d.func.id == 'require_permission' for d in function.decorator_list))
            function.decorator_list = []
        self.app = Flask(__name__)
        self.allowed = False
        scope = dict(app=self.app, jsonify=jsonify, request=request, sf_db=Mock(),
                     _operation_dept_has_access=lambda: self.allowed)
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<fba-api>', 'exec'), scope)
        for name, path in zip(names, ['/data', '/shops', '/export']):
            self.app.add_url_rule(path, view_func=scope[name])
        self.client = self.app.test_client()
        self.snapshot = dict(records=[], columns=[], available_fields=[], loaded_at='now', shops=[], shipping_methods=[])

    def test_all_read_endpoints_require_permission_before_database_access(self):
        with patch.object(service, 'load_snapshot') as load:
            for path in ['/data', '/shops', '/export']:
                self.assertEqual(self.client.get(path).status_code, 403)
            load.assert_not_called()

    def test_pagination_validation_and_export_headers(self):
        self.allowed = True
        with patch.object(service, 'load_snapshot', return_value=self.snapshot):
            self.assertEqual(self.client.get('/data?page=invalid').status_code, 400)
            response = self.client.get('/data')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['data']['stats']['total'], 0)
            response = self.client.get('/export')
            self.assertEqual(response.status_code, 200)
            self.assertIn('text/csv', response.content_type)
            self.assertIn('attachment', response.headers['Content-Disposition'])


if __name__ == '__main__':
    unittest.main()
