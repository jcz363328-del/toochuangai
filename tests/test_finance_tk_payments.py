import unittest
from datetime import date
from io import BytesIO
from unittest.mock import Mock

from flask import Flask
from PIL import Image

from finance_tk_payments import payment_query, register_tk_payments
from finance_tk_expenses import EXPENSE_QUERY


class PaymentTests(unittest.TestCase):
    def setUp(self):
        self.conn = Mock()
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.permissions = []
        def guard(name):
            self.permissions.append(name)
            return lambda fn: fn
        register_tk_payments(self.app, guard, connect=lambda: self.conn)
        self.client = self.app.test_client()

    def test_dates_and_filters_are_parameterized(self):
        sql, params = payment_query(dict(start_date='2026-09-01', end_date='2026-09-30', unpaid='1', mine='1'), "O'Brien")
        self.assertEqual(params, (date(2026, 9, 1), date(2026, 10, 1), '青岛', "O'Brien"))
        self.assertNotIn("O'Brien", sql)
        self.assertIn('FuKuanRen IS NULL', sql)
        self.assertIn('ShenQingShiJian < %s', sql)
        self.assertIn('ORDER BY ID DESC', sql)

    def test_invalid_dates_and_unknown_actor_do_not_query(self):
        response = self.client.get('/api/finance/tk_payments?start_date=2026-11-30&end_date=2026-11-01')
        self.assertEqual(response.status_code, 400)
        response = self.client.get('/api/finance/tk_payments?start_date=2026-11-01&end_date=2026-11-30&mine=1')
        self.assertEqual(response.status_code, 400)
        self.conn.cursor.assert_not_called()

    def test_empty_screenshot_is_404_and_scoped(self):
        self.conn.cursor.return_value.fetchone.return_value = None
        response = self.client.get('/api/finance/tk_payments/1/screenshot')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.conn.cursor.return_value.execute.call_args.args[1], (1, '青岛'))
        self.conn.close.assert_called_once()
        self.assertEqual(self.permissions, ['finance_dept'] * 3)

    def test_screenshot_response_is_image_and_not_cached(self):
        buf = BytesIO()
        Image.new('RGB', (2, 2)).save(buf, 'PNG')
        self.conn.cursor.return_value.fetchone.return_value = (buf.getvalue(),)
        response = self.client.get('/api/finance/tk_payments/1/screenshot')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/png')
        self.assertIn('no-store', response.headers['Cache-Control'])
        response.close()

    def test_query_failure_closes_connection(self):
        self.conn.cursor.return_value.execute.side_effect = RuntimeError('database offline')
        response = self.client.get('/api/finance/tk_payments?start_date=2026-11-01&end_date=2026-11-30')
        self.assertEqual(response.status_code, 500)
        self.conn.close.assert_called_once()

    def test_query_preserves_large_payment_number_as_text(self):
        from decimal import Decimal
        self.conn.cursor.return_value.fetchall.return_value = [
            (1, 2, '申请人', None, '达人', 'account', Decimal('49.50'), 92, '', 3,
             '10011826585723612995584', '付款人', None, '', 1)
        ]
        response = self.client.get('/api/finance/tk_payments?start_date=2026-09-01&end_date=2026-09-30')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['data'][0][10], '10011826585723612995584')
        self.assertEqual(response.json['data'][0][6], '49.50')

    def test_new_workbook_fee_query_sources(self):
        self.assertEqual(EXPENSE_QUERY.count('%s'), 6)
        self.assertIn('DaoRuRen,DaoRuShiJian', EXPENSE_QUERY)
        self.assertIn('ROUND(dd.ChanPinJinE*0.08,4)', EXPENSE_QUERY)
        self.assertEqual(EXPENSE_QUERY.count('NOT EXISTS'), 2)


if __name__ == '__main__':
    unittest.main()
