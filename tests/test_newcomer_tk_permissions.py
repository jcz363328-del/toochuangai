import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from department_permissions import FeishuPermissionManager


class NewcomerTkPermissionTests(unittest.TestCase):
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
                "department_id": "od-580f76720379d11ad66be30aaf7034a4",
                "name": "新人组",
                "status": "valid",
            }
        ]

    def test_newcomer_can_access_tk_and_all_operation_sections(self):
        visible_sections = [
            "tk_project_group",
            "operation_dept_1",
            "operation_dept_2",
            "operation_dept_3",
            "operation_dept_6",
        ]

        for function_name in visible_sections:
            with self.subTest(function_name=function_name):
                allowed, reason = self.manager.check_user_permission(
                    "newcomer-user",
                    function_name,
                )
                self.assertTrue(allowed, reason)

    def test_newcomer_cannot_access_independently_scoped_tk_modules(self):
        independently_scoped_modules = [
            "amazon_reply_agent",
            "review_analysis",
            "tk_email_register",
            "tk_video_realtime",
            "tk_dashboard",
            "tk_total_dashboard",
            "script_generator",
            "influencer_management",
        ]

        for function_name in independently_scoped_modules:
            with self.subTest(function_name=function_name):
                allowed, _ = self.manager.check_user_permission(
                    "newcomer-user",
                    function_name,
                )
                self.assertFalse(allowed)

    def test_newcomer_does_not_inherit_restricted_parent_permissions(self):
        self.manager._department_matches_root_name = (
            lambda department_id, root_name: True
        )

        for function_name in ["review_analysis", "amazon_reply_agent"]:
            with self.subTest(function_name=function_name):
                allowed, _ = self.manager.check_user_permission(
                    "newcomer-user",
                    function_name,
                )
                self.assertFalse(allowed)

    def test_restricted_cards_are_hidden_inside_operation_sections(self):
        template_dir = Path(__file__).resolve().parents[1] / "templates"
        environment = Environment(loader=FileSystemLoader(template_dir))
        environment.globals["url_for"] = (
            lambda endpoint, **values: f"/{endpoint}"
        )
        template = environment.get_template("operation_dept.html")

        html = template.render(
            user_name="新人",
            user_id="newcomer-user",
            dept_name="运营一部",
            dept_id="operation_dept_1",
            can_view_tk_90=False,
            can_view_review_analysis=False,
            can_view_amazon_reply=False,
        )

        self.assertNotIn("差评分析系统", html)
        self.assertNotIn("亚马逊站内信回复智能体", html)
        self.assertNotIn("90号店看板", html)
        self.assertIn("模特排队", html)
        self.assertIn("客服", html)
        self.assertIn("FBA货件运输方式", html)

    def test_newcomer_card_includes_fba_shipping(self):
        template_dir = Path(__file__).resolve().parents[1] / "templates"
        environment = Environment(loader=FileSystemLoader(template_dir))
        environment.globals["url_for"] = (
            lambda endpoint, **values: f"/{endpoint}"
        )
        template = environment.get_template("operation_dept.html")

        html = template.render(
            user_name="新人",
            user_id="newcomer-user",
            dept_name="新人组",
            dept_id="newcomer_group",
            can_view_tk_88=False,
            can_view_review_analysis=False,
            can_view_amazon_reply=False,
        )

        self.assertIn("FBA货件运输方式", html)
        self.assertIn("/operation_fba_shipping_methods_page", html)


if __name__ == "__main__":
    unittest.main()
