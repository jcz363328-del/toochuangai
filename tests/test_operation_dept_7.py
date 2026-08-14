import ast
import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from department_permissions import FeishuPermissionManager, PERMISSION_CONFIG


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
DASHBOARD_SOURCE = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")


class OperationDeptSevenTests(unittest.TestCase):
    def setUp(self):
        self.manager = FeishuPermissionManager()
        self.manager.is_developer = lambda user_id=None, email=None: False
        self.manager._get_extra_allowed_functions = lambda user_id: []
        self.manager._resolve_effective_departments = (
            lambda departments, function_name: (departments, False)
        )
        self.manager._department_matches_root_name = (
            lambda department_id, root_name: False
        )
        self.manager.get_user_departments = lambda user_id: [
            {
                "department_id": "od-operation-seven",
                "name": "运营七部",
                "status": "valid",
            }
        ]

    def test_operation_seven_department_has_its_own_permission(self):
        self.assertIn("operation_dept_7", PERMISSION_CONFIG)
        allowed, reason = self.manager.check_user_permission(
            "operation-seven-user",
            "operation_dept_7",
        )
        self.assertTrue(allowed, reason)

    def test_other_operation_departments_do_not_receive_seven_card(self):
        for function_name in (
            "operation_dept_1",
            "operation_dept_2",
            "operation_dept_3",
            "operation_dept_6",
        ):
            with self.subTest(function_name=function_name):
                allowed, _ = self.manager.check_user_permission(
                    "operation-seven-user",
                    function_name,
                )
                self.assertFalse(allowed)

    def test_zhao_yu_receives_seven_card_when_directory_is_not_synced(self):
        manager = FeishuPermissionManager()
        manager.is_developer = lambda user_id=None, email=None: False
        manager.get_user_info_by_user_id = lambda user_id: {"name": "赵瑜"}
        manager.get_user_departments = lambda user_id: []

        allowed, reason = manager.check_user_permission(
            "zhao-yu-user",
            "operation_dept_7",
        )

        self.assertTrue(allowed, reason)
        self.assertEqual("指定用户额外权限", reason)

    def test_desktop_mobile_and_route_are_wired(self):
        ast.parse(APP_SOURCE)
        self.assertIn("@app.route('/operation_dept_7')", APP_SOURCE)
        self.assertIn("@require_permission('operation_dept_7')", APP_SOURCE)
        self.assertIn("url_for('operation_dept_7')", APP_SOURCE)
        self.assertIn("fname == 'operation_dept_7'", DASHBOARD_SOURCE)
        self.assertIn("'operation_dept_7', 'amazon_reply_agent'", DASHBOARD_SOURCE)

    def test_operation_seven_page_reuses_common_operation_features(self):
        environment = Environment(
            loader=FileSystemLoader(ROOT / "templates")
        )
        environment.globals["url_for"] = (
            lambda endpoint, **values: f"/{endpoint}"
        )
        template = environment.get_template("operation_dept.html")
        html = template.render(
            user_name="赵瑜",
            user_id="operation-seven-user",
            dept_name="运营七部",
            dept_id="operation_dept_7",
            can_view_review_analysis=True,
            can_view_amazon_reply=True,
        )

        self.assertIn("运营七部功能中心", html)
        self.assertIn("差评分析系统", html)
        self.assertIn("模特排队", html)
        self.assertIn("客服", html)
        self.assertIn("FBA货件运输方式", html)
        self.assertIn("亚马逊站内信回复智能体", html)
        self.assertIn("/operation_fba_shipping_methods_page", html)


if __name__ == "__main__":
    unittest.main()
