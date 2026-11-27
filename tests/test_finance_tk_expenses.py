import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from flask import Flask
from Department.财务部 import tk_expenses
from Department.财务部.tk_expenses import parse_rows, register_tk_expenses, save_rows


class TKExpenseTests(unittest.TestCase):
    def test_original_other_columns_and_negative_reversal(self):
        sheet = Mock(title='费用导入')
        sheet.iter_rows.return_value = iter([
            (), (), (),
            (None,) * 7 + (date(2026, 11, 1), 82, '售后', '英国', -29.94, '冲销'),
        ])
        book = Mock(sheetnames=['费用导入'])
        book.__getitem__ = Mock(return_value=sheet)
        with patch.object(tk_expenses, 'load_workbook', return_value=book):
            rows = parse_rows(None, 'other')
        self.assertEqual(rows[0], (date(2026, 11, 1), 82, '英国', '售后', Decimal('-29.94'), '冲销'))
        book.close.assert_called_once()

    def test_invalid_amount_prevents_import(self):
        sheet = Mock(title='Sheet1')
        sheet.iter_rows.return_value = iter([(), ('2026-11-01', 82, '英国', 'NaN', '')])
        book = Mock(sheetnames=[], active=sheet)
        with patch.object(tk_expenses, 'load_workbook', return_value=book):
            with self.assertRaisesRegex(ValueError, '第2行'):
                parse_rows(None, 'advertising')

    def test_duplicate_ad_rolls_back_without_insert(self):
        conn = Mock()
        cursor = conn.cursor.return_value
        cursor.fetchone.return_value = (1,)
        row = (date(2026, 11, 1), 82, '英国', '广告', Decimal('1'), '')
        with self.assertRaisesRegex(ValueError, '已经导入'):
            save_rows([row], 'advertising', '测试', lambda: conn)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        self.assertEqual(cursor.execute.call_count, 1)
        conn.close.assert_called_once()

    def test_batch_failure_rolls_back_and_parameterizes_notes(self):
        conn = Mock()
        cursor = conn.cursor.return_value
        cursor.execute.side_effect = [None, RuntimeError('db failure')]
        row = (date(2026, 11, 1), 0, '英国', '售后', Decimal('-1'), "O'Brien 100%")
        with self.assertRaises(RuntimeError):
            save_rows([row, row], 'other', '测试', lambda: conn)
        self.assertNotIn(row[-1], cursor.execute.call_args_list[0].args[0])
        self.assertEqual(cursor.execute.call_args_list[0].args[1][-2], row[-1])
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_routes_require_finance_permission_and_validate_date(self):
        app = Flask(__name__)
        permissions = []
        def guard(name):
            permissions.append(name)
            return lambda fn: fn
        register_tk_expenses(app, guard)
        response = app.test_client().get('/api/finance/tk_expenses?start_date=2026-11-23&end_date=2026-11-01')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(permissions, ['finance_dept', 'finance_dept'])


if __name__ == '__main__':
    unittest.main()
