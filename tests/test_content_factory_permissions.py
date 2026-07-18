import unittest
from pathlib import Path

from flask import Flask, session
from jinja2 import Environment, FileSystemLoader

from department_permissions import (
    DEPARTMENT_ID_MAPPING,
    DEPARTMENT_TREE_INHERIT_ROOTS,
    PERMISSION_CONFIG,
    FeishuPermissionManager,
)


class ContentFactoryPermissionTests(unittest.TestCase):
    def setUp(self):
        self.manager = FeishuPermissionManager()
        self.manager.is_developer = lambda user_id=None, email=None: False
        self.manager._get_extra_allowed_functions = lambda user_id: []
        self.manager._resolve_effective_departments = (
            lambda departments, function_name: (departments, False)
        )

    def test_department_mapping_and_function_name_use_content_factory(self):
        root_id = "od-c560effca33bf715c15f79a0670fe6ba"
        self.assertEqual(DEPARTMENT_ID_MAPPING[root_id], "内容生产工厂")
        self.assertIn("内容生产工厂", DEPARTMENT_TREE_INHERIT_ROOTS)
        self.assertNotIn("内容生成工厂", DEPARTMENT_TREE_INHERIT_ROOTS)
        self.assertNotIn("TK项目", DEPARTMENT_TREE_INHERIT_ROOTS)
        self.assertEqual(PERMISSION_CONFIG["tk_project_group"]["name"], "内容生产工厂")

    def test_user_department_lookup_requests_open_department_ids(self):
        root_id = "od-c560effca33bf715c15f79a0670fe6ba"
        captured = {}

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "code": 0,
                    "data": {
                        "user": {
                            "name": "内容子部门用户",
                            "department_ids": [root_id],
                        }
                    },
                }

        def fake_request(method, url, **kwargs):
            captured.update(kwargs.get("params") or {})
            return FakeResponse()

        self.manager.get_access_token = lambda: "test-token"
        self.manager._feishu_request = fake_request

        departments = self.manager.get_user_departments("ou_content_user")

        self.assertEqual(captured["user_id_type"], "open_id")
        self.assertEqual(captured["department_id_type"], "open_department_id")
        self.assertEqual(departments[0]["department_id"], root_id)
        self.assertEqual(departments[0]["name"], "内容生产工厂")

    def test_unmapped_api_department_is_normalized_and_inherits_card(self):
        root_id = "od-c560effca33bf715c15f79a0670fe6ba"
        child_id = "od-884d568d0952416a876a77c087a1d15a"

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "code": 0,
                    "data": {
                        "user": {
                            "name": "BD一组用户",
                            "department_ids": [child_id],
                        }
                    },
                }

        self.manager.get_access_token = lambda: "test-token"
        self.manager._feishu_request = lambda method, url, **kwargs: FakeResponse()
        self.manager.get_department_info = lambda department_id: {
            "department_id": "489e41c8f73499db",
            "open_department_id": child_id,
            "name": "BD一组",
            "parent_department_id": root_id,
            "status": {"is_deleted": False},
        }

        departments = self.manager.get_user_departments("ou_bd_group_user")
        allowed, reason = self.manager.check_user_permission(
            "ou_bd_group_user",
            "tk_project_group",
        )

        self.assertEqual(departments[0]["department_id"], child_id)
        self.assertEqual(departments[0]["open_department_id"], child_id)
        self.assertTrue(allowed, reason)
        self.assertIn("内容生产工厂(子部门继承)", reason)

    def test_content_factory_root_has_renamed_tk_permissions(self):
        self.manager.get_user_departments = lambda user_id: [
            {
                "department_id": "od-c560effca33bf715c15f79a0670fe6ba",
                "name": "内容生产工厂",
                "status": "active",
            }
        ]

        for function_name in [
            "tk_project_group",
            "tk_email_register",
            "tk_video_realtime",
            "tk_dashboard",
            "tk_total_dashboard",
        ]:
            with self.subTest(function_name=function_name):
                allowed_departments = PERMISSION_CONFIG[function_name]["allowed_departments"]
                self.assertIn("内容生产工厂", allowed_departments)
                self.assertNotIn("内容生成工厂", allowed_departments)
                self.assertNotIn("TK项目", allowed_departments)
                allowed, reason = self.manager.check_user_permission(
                    "content-factory-user",
                    function_name,
                )
                self.assertTrue(allowed, reason)

    def test_unmapped_nested_department_inherits_content_factory_card(self):
        root_id = "od-c560effca33bf715c15f79a0670fe6ba"
        parent_chain = {
            "od-content-team-level-3": {
                "parent_department_id": "od-content-team-level-2",
            },
            "od-content-team-level-2": {
                "parent_department_id": "od-content-team-level-1",
            },
            "od-content-team-level-1": {
                "parent_department_id": root_id,
            },
        }
        self.manager.get_user_departments = lambda user_id: [
            {
                "department_id": "od-content-team-level-3",
                "name": "新增内容子组",
                "status": "unmapped",
            }
        ]
        self.manager.get_department_info = (
            lambda department_id: parent_chain.get(department_id, {})
        )

        allowed, reason = self.manager.check_user_permission(
            "nested-content-factory-user",
            "tk_project_group",
        )

        self.assertTrue(allowed, reason)
        self.assertIn("内容生产工厂(子部门继承)", reason)

    def test_debug_user_department_tree_is_used_for_dashboard_and_card_check(self):
        root_id = "od-c560effca33bf715c15f79a0670fe6ba"
        bd_department_id = "od-content-factory-bd"
        bd_group_id = "od-content-factory-bd-group-1"
        manager = FeishuPermissionManager()
        manager.is_developer = lambda user_id=None, email=None: False
        manager._get_extra_allowed_functions = lambda user_id: []

        def fake_user_departments(user_id):
            if user_id == "ou_debug_zhangrui":
                return [{
                    "department_id": bd_group_id,
                    "open_department_id": bd_group_id,
                    "name": "BD一组",
                    "status": "unmapped",
                }]
            return [{
                "department_id": "od-ai-department",
                "open_department_id": "od-ai-department",
                "name": "AI部",
                "status": "active",
            }]

        department_parents = {
            bd_group_id: {"parent_department_id": bd_department_id},
            bd_department_id: {"parent_department_id": root_id},
        }
        manager.get_user_departments = fake_user_departments
        manager.get_department_info = (
            lambda department_id: department_parents.get(department_id, {})
        )

        app = Flask(__name__)
        app.secret_key = "content-factory-permission-test"
        with app.test_request_context("/"):
            session["permission_debug_departments"] = ["BD一组"]
            session["permission_debug_user_name"] = "张睿"
            session["permission_debug_user_open_id"] = "ou_debug_zhangrui"

            functions = manager.get_user_accessible_functions("ou_ai_operator")
            function_names = {row["function_name"] for row in functions}
            allowed, reason = manager.check_user_permission(
                "ou_ai_operator",
                "tk_project_group",
            )

            template_dir = Path(__file__).resolve().parents[1] / "templates"
            environment = Environment(loader=FileSystemLoader(template_dir))
            environment.globals["url_for"] = (
                lambda endpoint, **values: "/tk_project" if endpoint == "tk_project" else f"/{endpoint}"
            )
            environment.globals["get_flashed_messages"] = lambda **kwargs: []
            dashboard_html = environment.get_template("dashboard.html").render(
                user_id="ou_ai_operator",
                user_name="AI调试账号",
                accessible_functions=functions,
                permission_debug_departments=["BD一组"],
                permission_debug_user_name="张睿",
            )

        self.assertIn("tk_project_group", function_names)
        self.assertTrue(allowed, reason)
        self.assertIn("内容生产工厂(子部门继承)", reason)
        self.assertIn('<span class="nav-name">内容生产工厂</span>', dashboard_html)
        self.assertIn('data-href="/tk_project"', dashboard_html)

    def test_content_factory_page_uses_new_visible_name(self):
        template_dir = Path(__file__).resolve().parents[1] / "templates"
        environment = Environment(loader=FileSystemLoader(template_dir))
        environment.globals["url_for"] = lambda endpoint, **values: f"/{endpoint}"
        template = environment.get_template("tk_project.html")

        html = template.render(accessible_functions=[])

        self.assertIn("内容生产工厂", html)
        self.assertNotIn("内容生成工厂", html)
        self.assertNotIn("TK项目组功能", html)


if __name__ == "__main__":
    unittest.main()
