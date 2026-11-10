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
        ), patch.object(app_module.permission_manager, "get_user_departments", return_value=[{"name": "AI部"}]):
            return self.client.get("/ai_modules")

    def test_scoped_user_sees_all_cards_with_unavailable_cards_locked(self):
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
        self.assertNotIn("<h3>经营分析</h3>", page)
        self.assertIn("<h3>MAGIC AD 广告监控</h3>", page)
        self.assertIn("<h3>更新</h3>", page)
        self.assertIn("<h3>性能监控</h3>", page)
        self.assertIn("<h3>管理员功能</h3>", page)
        self.assertIn('data-allowed="false"', page)
        self.assertIn("暂无该功能权限", page)

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
        self.assertNotIn("<h3>经营分析</h3>", page)
        self.assertIn("<h3>MAGIC AD 广告监控</h3>", page)
        self.assertIn("<h3>更新</h3>", page)
        self.assertIn("<h3>性能监控</h3>", page)
        self.assertIn("<h3>管理员功能</h3>", page)

    def test_daily_replenishment_card_is_visible_but_locked_without_permission(self):
        response = self._open_ai_modules({"ai_dept", "admin_functions"})

        self.assertEqual(200, response.status_code)
        page = response.get_data(as_text=True)
        self.assertIn("<h3>日常补货</h3>", page)
        self.assertIn('data-allowed="false"', page)

    def test_value_evaluation_cards_are_hidden_without_table_permissions(self):
        response = self._open_ai_modules({"ai_dept"})
        page = response.get_data(as_text=True)

        self.assertNotIn("<h3>360价值评价</h3>", page)
        self.assertNotIn("<h3>360价值评价管理</h3>", page)

    def test_only_value_evaluation_admin_card_remains_in_ai_modules(self):
        response = self._open_ai_modules({
            "ai_dept", "value_evaluation", "value_evaluation_admin"
        })
        page = response.get_data(as_text=True)

        self.assertNotIn("<h3>360价值评价</h3>", page)
        self.assertIn("<h3>360价值评价管理</h3>", page)

    def test_value_evaluation_permissions_match_current_audience(self):
        rows = {
            row["gongneng"]: row
            for row in build_permission_seed_rows(PERMISSION_CONFIG)
        }

        evaluation = rows["value_evaluation"]
        self.assertEqual("all", evaluation["bumen"])
        self.assertEqual("", evaluation["yonghu"])

        admin = rows["value_evaluation_admin"]
        self.assertEqual("AI部", admin["bumen"])
        self.assertEqual("韩雅俊；蔡晶", admin["yonghu"])

    def test_daily_replenishment_permission_is_seeded_for_ai_department_only(self):
        rows = {
            row["gongneng"]: row
            for row in build_permission_seed_rows(PERMISSION_CONFIG)
        }
        permission = rows["daily_replenishment"]

        self.assertEqual("AI部", permission["bumen"])
        self.assertEqual("", permission["yonghu"])
        self.assertEqual("ai_dept", permission["fujigongneng"])

    def test_operation_replenishment_keeps_its_separate_permission(self):
        rows = {row["gongneng"]: row for row in build_permission_seed_rows(PERMISSION_CONFIG)}
        permission = rows["daily_replenishment_operation"]
        self.assertEqual("运营部；AI部；总经办", permission["bumen"])
        self.assertEqual("", permission["fujigongneng"])

    def test_moved_operations_cards_are_absent_from_ai_page_even_with_permissions(self):
        response = self._open_ai_modules({
            "ai_dept", "historical_sales", "daily_replenishment_operation", "daily_replenishment"
        })

        self.assertEqual(200, response.status_code)
        page = response.get_data(as_text=True)
        for title in ("我开发的产品销售", "智能补货中心-运营"):
            with self.subTest(title=title):
                self.assertNotIn("<h3>" + title + "</h3>", page)
        self.assertIn("<h3>日常补货</h3>", page)
        self.assertIn("<h3>历史销售数据曲线</h3>", page)

    def test_historical_sales_card_is_hidden_without_its_permission(self):
        response = self._open_ai_modules({"ai_dept"})

        self.assertEqual(200, response.status_code)
        self.assertNotIn("<h3>历史销售数据曲线</h3>", response.get_data(as_text=True))

    def test_dashboard_catalog_keeps_unavailable_functions_visible(self):
        functions = app_module._normalize_dashboard_functions([
            {"function_name": "innovation_proposals", "name": "创新提案管理"}
        ])
        functions_by_name = {item["function_name"]: item for item in functions}

        self.assertIn("operation_dept_2", functions_by_name)
        self.assertIn("finance_dept", functions_by_name)
        self.assertFalse(functions_by_name["operation_dept_2"]["is_allowed"])
        self.assertFalse(functions_by_name["finance_dept"]["is_allowed"])
        self.assertTrue(functions_by_name["innovation_proposals"]["is_allowed"])

    def test_dashboard_catalog_exposes_fba_shipping_as_direct_entry(self):
        functions = app_module._normalize_dashboard_functions([
            {"function_name": "operation_fba_shipping", "name": "FBA货件运输方式"}
        ])
        functions_by_name = {item["function_name"]: item for item in functions}

        self.assertIn("operation_fba_shipping", functions_by_name)
        self.assertTrue(functions_by_name["operation_fba_shipping"]["is_allowed"])

    def test_magic_ad_permission_is_seeded_for_requested_users(self):
        rows = {row["gongneng"]: row for row in EXTRA_PERMISSION_ROWS}
        magic_ad = rows["ads_monitor"]
        self.assertEqual("孙洁；侯梁；刘蓉蓉", magic_ad["yonghu"])
        self.assertEqual("ai_dept", magic_ad["fujigongneng"])


if __name__ == "__main__":
    unittest.main()
