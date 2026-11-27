import unittest
from datetime import datetime, timedelta
from functools import partial
from io import BytesIO
from flask import Flask, request, jsonify, send_file
from openpyxl import load_workbook
from Department.内容生产工厂 import tk_customer_service_routes as routes


class McfExportTests(unittest.TestCase):
    def setUp(self):
        self.items = [{'SKU': "SKU-A", 'dian': 'SHOP', 'FaYangDingDanHao': '001234567890123456789'}]
        self.base = {'*订单号': self.items[0]['FaYangDingDanHao'], '*收件人': 'John',
                     '电话': '+11234567890', '*邮编': '00123', '*国家二字码': 'US',
                     '州/省': 'TX', '区/县': '', '*城市': 'Austin', '*地址1': '12 Main St', '地址2': ''}

    def database(self, sql):
        if 'KuCun3' in sql:
            return [('SKU-A', 'SHOP', '2159386248354310'), ('SKU-A', 'OTHER', 'OTHER-ID')]
        return [('SHOP', 'shop@example.com')]

    def builder(self, items):
        return [dict(self.base) for _ in items], []

    def test_resolves_shop_inventory_and_email(self):
        rows, errors = routes._tk_customer_service_build_mcf_rows(
            self.items, build_export_rows=self.builder, sf_db=self.database)
        self.assertEqual(list(rows[0]), routes.MCF_HEADERS)
        self.assertEqual(rows[0]['* Goods ID'], '2159386248354310')
        self.assertEqual(rows[0]['* E-mail'], 'shop@example.com')
        self.assertEqual(errors, [])

    def test_missing_mapping_keeps_order_and_reports_errors(self):
        rows, errors = routes._tk_customer_service_build_mcf_rows(
            self.items, build_export_rows=self.builder, sf_db=lambda sql: [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['* Goods ID'], '')
        self.assertIn('绑定邮箱', errors[0]['错误原因'])

    def test_endpoint_exports_text_ids_and_forwards_filters(self):
        app = Flask(__name__)
        calls = []
        def query(*args):
            calls.append(args)
            return self.items
        with app.test_request_context('/?format=mcf&start_date=2026-11-01&end_date=2026-11-27'):
            response = routes.api_tk_customer_service_export(
                _tk_customer_service_build_export_rows=self.builder,
                _tk_customer_service_query_rows=query,
                _tk_parse_importers_from_request=lambda: ['Alice'],
                _tk_parse_order_nos_from_request=lambda: ['ORDER'],
                _tk_parse_shop_names_from_request=lambda: ['SHOP'],
                datetime=datetime, jsonify=jsonify, request=request,
                send_file=send_file, timedelta=timedelta, sf_db=self.database)
            response.direct_passthrough = False
            workbook = load_workbook(BytesIO(response.get_data()))
        sheet = workbook['全部数据']
        self.assertEqual([c.value for c in sheet[1]], routes.MCF_HEADERS)
        self.assertEqual(sheet['A2'].value, '001234567890123456789')
        self.assertEqual(sheet['L2'].data_type, 's')
        self.assertEqual(sheet['E2'].value, '00123')
        self.assertEqual(sheet['M2'].value, 1)
        self.assertEqual(calls[0][2:], (['SHOP'], ['Alice'], ['ORDER']))


if __name__ == '__main__':
    unittest.main()
