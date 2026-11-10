import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import developer_product_sales as module
from app import app
from pathlib import Path


class DeveloperProductSalesTests(unittest.TestCase):
    def test_parse_range_validation(self):
        self.assertEqual(module._parse_range("2026-10-01", "2026-10-02"), (date(2026, 10, 1), date(2026, 10, 2)))
        with self.assertRaises(ValueError):
            module._parse_range("2026-10-03", "2026-10-02")

    def test_store_must_be_a_positive_integer(self):
        self.assertEqual(module._parse_store("37"), 37)
        for value in ("", "abc", "0", "-1", "1.5"):
            with self.assertRaises(ValueError):
                module._parse_store(value)

    def test_page_has_no_default_store(self):
        source = (Path(__file__).resolve().parents[1] / "templates" / "developer_product_sales.html").read_text(encoding="utf-8")
        self.assertIn('placeholder="请输入店铺号"', source)
        self.assertNotIn('value="{{ default_store }}"', source)
        self.assertNotIn(";load();", source)

    @patch.object(module.pytds, "connect")
    def test_query_uses_parameterized_current_developer(self, connect):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(1200, 240, 0.2), (650000,)]
        cursor.fetchall.return_value = [(date(2026, 10, 1), 1200, 240, 0.2)]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connect.return_value.__enter__.return_value = connection

        result = module._query_sales("陈梓琪", 82, date(2026, 10, 1), date(2026, 10, 2))

        self.assertEqual(result["developer"], "陈梓琪")
        self.assertEqual(result["store"], 82)
        self.assertEqual(result["progress"], 1.3)
        self.assertEqual(cursor.execute.call_count, 3)
        for call in cursor.execute.call_args_list:
            sql, params = call.args
            self.assertIn("%(developer)s", sql)
            self.assertNotIn("陈梓琪", sql)
            self.assertEqual(params["developer"], "陈梓琪")
            self.assertEqual(params["store"], 82)

    def test_page_reads_current_feishu_user_name(self):
        app.config.update(TESTING=True, SECRET_KEY="developer-sales-test")
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "ou_test"
            flask_session["feishu_user_name"] = "当前用户"
        with patch.object(module, "require_permission"):
            pass
        with app.test_request_context():
            session = __import__("flask").session
            session["feishu_user_name"] = "当前用户"
            self.assertEqual(module._developer_name(), "当前用户")

    def test_switched_identity_takes_priority(self):
        with app.test_request_context():
            session = __import__("flask").session
            flask_g = __import__("flask").g
            session["feishu_user_name"] = "真实用户"
            session["permission_debug_user_name"] = "会话切换用户"
            self.assertEqual(module._developer_name(), "会话切换用户")

            flask_g.permission_debug_state = {"user_name": "Cookie切换用户"}
            self.assertEqual(module._developer_name(), "Cookie切换用户")


if __name__ == "__main__":
    unittest.main()
