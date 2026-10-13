import unittest
from unittest.mock import patch

import app as app_module
from department_permissions import PERMISSION_CONFIG
from permission_seed_data import EXTRA_PERMISSION_ROWS, build_permission_seed_rows


class AiModuleScopedPermissionTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def _open_ai_modules(self, allowed_functions):
        with self.client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "dev_scoped_ai_user"
            flask_session["feishu_user_name"] = "孙洁"

        def check_permission(_user_id, function_name):
            allowed = function_name in allowed_functions
            return allowed, "test permission"

        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            side_effect=check_permission,
        ):
            return self.client.get("/ai_modules")

    def test_scoped_user_only_sees_business_analysis_and_magic_ad(self):
        response = self._open_ai_modules(
            {
                "ai_dept",
                "daily_replenishment",
                "business_analysis",
                "business_analysis_all",
                "ads_monitor",
            }
        )

        self.assertEqual(200, response.status_code)
        page = response.get_data(as_text=True)
        self.assertIn("<h3>日常补货</h3>", page)
        self.assertIn("<h3>经营分析</h3>", page)
        self.assertIn("<h3>MAGIC AD 广告监控</h3>", page)
        self.assertNotIn("<h3>更新</h3>", page)
        self.assertNotIn("<h3>性能监控</h3>", page)
        self.assertNotIn("<h3>管理员功能</h3>", page)
        self.assertNotIn("<h3>权限身份切换（测试）</h3>", page)

    def test_ai_department_full_user_still_sees_all_cards(self):
        response = self._open_ai_modules(
            {
                "ai_dept",
                "daily_replenishment",
                "admin_functions",
                "business_analysis",
                "ads_monitor",
            }
        )

        self.assertEqual(200, response.status_code)
        page = response.get_data(as_text=True)
        self.assertIn("<h3>经营分析</h3>", page)
        self.assertIn("<h3>MAGIC AD 广告监控</h3>", page)
        self.assertIn("<h3>更新</h3>", page)
        self.assertIn("<h3>性能监控</h3>", page)
        self.assertIn("<h3>管理员功能</h3>", page)

    def test_daily_replenishment_card_is_hidden_without_scoped_permission(self):
        response = self._open_ai_modules({"ai_dept", "admin_functions"})

        self.assertEqual(200, response.status_code)
        self.assertNotIn("<h3>日常补货</h3>", response.get_data(as_text=True))

    def test_daily_replenishment_permission_is_seeded_for_ai_department_only(self):
        rows = {
            row["gongneng"]: row
            for row in build_permission_seed_rows(PERMISSION_CONFIG)
        }
        permission = rows["daily_replenishment"]

        self.assertEqual("AI部", permission["bumen"])
        self.assertEqual("", permission["yonghu"])
        self.assertEqual("ai_dept", permission["fujigongneng"])

    def test_daily_replenishment_operation_is_a_separate_card_and_permission(self):
        response = self._open_ai_modules({"ai_dept", "daily_replenishment_operation"})
        page = response.get_data(as_text=True)
        self.assertEqual(200, response.status_code)
        self.assertIn("<h3>日常补货运营</h3>", page)
        self.assertNotIn("<h3>日常补货</h3>", page)

        rows = {row["gongneng"]: row for row in build_permission_seed_rows(PERMISSION_CONFIG)}
        permission = rows["daily_replenishment_operation"]
        self.assertEqual("运营部；AI部；总经办", permission["bumen"])
        self.assertEqual("", permission["fujigongneng"])

    def test_operation_permission_adds_ai_modules_dashboard_entry(self):
        functions = app_module._normalize_dashboard_functions([
            {"function_name": "daily_replenishment_operation", "name": "日常补货运营"}
        ])

        self.assertIn("ai_dept", {item["function_name"] for item in functions})

    def test_magic_ad_permission_is_seeded_for_requested_users(self):
        rows = {row["gongneng"]: row for row in EXTRA_PERMISSION_ROWS}
        magic_ad = rows["ads_monitor"]
        self.assertEqual("孙洁；侯梁；刘蓉蓉", magic_ad["yonghu"])
        self.assertEqual("ai_dept", magic_ad["fujigongneng"])


if __name__ == "__main__":
    unittest.main()
