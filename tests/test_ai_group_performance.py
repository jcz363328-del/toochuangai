import unittest
from unittest.mock import patch

import app as app_module
import ai_group_performance as module
from department_permissions import PERMISSION_CONFIG
from permission_seed_data import build_permission_seed_rows


class AiGroupPerformanceTests(unittest.TestCase):
    def test_query_is_dynamic_and_escaped(self):
        sql = module.build_query("2026-08", "测试'组")
        self.assertIn("2026-07-01", sql)
        self.assertIn("2026-09-01", sql)
        self.assertIn("N'测试''组'", sql)
        self.assertIn("z.Nian=2026 AND z.Yue=8", sql)

    def test_permission_is_ai_only(self):
        rows = {r["gongneng"]: r for r in build_permission_seed_rows(PERMISSION_CONFIG)}
        self.assertEqual("AI部", rows["ai_group_performance"]["bumen"])
        self.assertEqual("ai_dept", rows["ai_group_performance"]["fujigongneng"])

    def test_page_and_api_use_scoped_permission(self):
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["feishu_user_id"] = "dev_ai_user"
            session["feishu_user_name"] = "AI 测试用户"
        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "ok")):
            response = client.get("/ai/group-performance")
        self.assertEqual(200, response.status_code)
        self.assertIn("组别经营数据", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
