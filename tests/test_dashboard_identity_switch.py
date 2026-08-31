import unittest
from pathlib import Path
from unittest.mock import patch

from jinja2 import Environment, FileSystemLoader

import app as app_module
from department_permissions import FeishuPermissionManager


ROOT = Path(__file__).resolve().parents[1]


class DashboardIdentitySwitchTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, SECRET_KEY="identity-switch-test")
        self.client = app_module.app.test_client()

    def _login(self, user_name="周俊成"):
        with self.client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "ou_real_operator"
            flask_session["feishu_open_id"] = "ou_real_operator"
            flask_session["feishu_user_name"] = user_name
            flask_session["feishu_user_access_token"] = "test-user-token"

    def test_switch_button_is_only_rendered_when_explicitly_allowed(self):
        environment = Environment(loader=FileSystemLoader(ROOT / "templates"))
        environment.globals["url_for"] = lambda endpoint, **values: f"/{endpoint}"
        environment.globals["get_flashed_messages"] = lambda **kwargs: []
        template = environment.get_template("dashboard.html")
        context = {
            "user_id": "ou_real_operator",
            "user_name": "周俊成",
            "accessible_functions": [],
            "permission_debug_departments": [],
            "permission_debug_user_name": "",
        }

        allowed_html = template.render(**context, can_switch_identity=True)
        denied_html = template.render(**context, can_switch_identity=False)

        self.assertIn('id="identitySwitchTrigger"', allowed_html)
        self.assertIn('id="identitySwitchModal"', allowed_html)
        self.assertNotIn('id="identitySwitchTrigger"', denied_html)

    def test_member_search_is_forbidden_for_other_users(self):
        self._login("其他成员")

        response = self.client.get("/api/dashboard/identity-switch/members?q=张三")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.get_json()["success"])

    @patch.object(app_module, "_xiaotu_search_notify_users")
    def test_search_records_server_approved_candidates(self, search_members):
        self._login()
        search_members.return_value = [
            {"open_id": "ou_target", "name": "张三", "display_name": "张三"},
        ]

        response = self.client.get("/api/dashboard/identity-switch/members?q=张三")

        self.assertEqual(response.status_code, 200)
        member = response.get_json()["data"][0]
        self.assertEqual(member["open_id"], "ou_target")
        self.assertEqual(member["name"], "张三")
        self.assertTrue(member["selection_token"])
        self.assertEqual(
            app_module._dashboard_identity_switch_selected_member(member["selection_token"]),
            {"open_id": "ou_target", "name": "张三"},
        )

    @patch.object(app_module, "_dashboard_identity_switch_departments")
    @patch.object(app_module, "_xiaotu_query_user_names_by_open_ids")
    def test_switch_updates_only_the_permission_debug_identity(self, resolve_names, resolve_departments):
        self._login()
        resolve_names.return_value = {"ou_target": "张三"}
        resolve_departments.return_value = ["运营三部"]
        with self.client.session_transaction() as flask_session:
            flask_session["preloaded_functions"] = [{"function_name": "ai_dept"}]
        selection_token = app_module._dashboard_identity_switch_selection_token(
            "ou_target",
            "张三",
        )

        response = self.client.post(
            "/api/dashboard/identity-switch",
            json={
                "open_id": "ou_forged",
                "user_name": "伪造名称",
                "selection_token": selection_token,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["user_name"], "张三")
        with self.client.session_transaction() as flask_session:
            self.assertEqual(flask_session["feishu_user_name"], "周俊成")
            self.assertEqual(flask_session["permission_debug_user_name"], "张三")
            self.assertEqual(flask_session["permission_debug_user_open_id"], "ou_target")
            self.assertEqual(flask_session["permission_debug_departments"], ["运营三部"])
            self.assertNotIn("preloaded_functions", flask_session)

    def test_switch_rejects_an_id_that_was_not_returned_by_search(self):
        self._login()

        response = self.client.post(
            "/api/dashboard/identity-switch",
            json={"open_id": "ou_unapproved", "user_name": "张三"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])

    def test_simulated_member_drives_personal_leader_and_override_permissions(self):
        manager = FeishuPermissionManager()
        records = {
            "personal_feature": {
                "function_name": "personal_feature",
                "name": "个人功能",
                "description": "",
                "bumen": "",
                "yonghu": "张三",
                "fujigongneng": "",
            },
            "leader_feature": {
                "function_name": "leader_feature",
                "name": "负责人功能",
                "description": "",
                "bumen": "",
                "yonghu": "@department_leader",
                "fujigongneng": "",
            },
            "override_feature": {
                "function_name": "override_feature",
                "name": "单独授权功能",
                "description": "",
                "bumen": "",
                "yonghu": "",
                "fujigongneng": "",
            },
        }
        manager.get_permission_records = lambda force_refresh=False: records

        def user_departments(user_id):
            if user_id == "ou_target":
                return [{
                    "department_id": "od_operation_3",
                    "name": "运营三部",
                    "status": "active",
                    "leader_user_id": "ou_target",
                }]
            return [{
                "department_id": "od_ai",
                "name": "AI部",
                "status": "active",
            }]

        manager.get_user_departments = user_departments
        manager.get_user_permission_overrides = lambda user_id: (
            {"override_feature": {"is_allowed": True}}
            if user_id == "ou_target"
            else {"override_feature": {"is_allowed": False}}
        )

        with app_module.app.test_request_context("/"):
            app_module.session["permission_debug_departments"] = ["运营三部"]
            app_module.session["permission_debug_user_name"] = "张三"
            app_module.session["permission_debug_user_open_id"] = "ou_target"

            personal_allowed, personal_reason = manager.check_user_permission(
                "ou_real_operator",
                "personal_feature",
            )
            leader_allowed, leader_reason = manager.check_user_permission(
                "ou_real_operator",
                "leader_feature",
            )
            override_allowed, override_reason = manager.check_user_permission(
                "ou_real_operator",
                "override_feature",
            )

        self.assertTrue(personal_allowed, personal_reason)
        self.assertIn("个人权限通过", personal_reason)
        self.assertTrue(leader_allowed, leader_reason)
        self.assertIn("部门负责人", leader_reason)
        self.assertTrue(override_allowed, override_reason)
        self.assertEqual(override_reason, "用户单独授权")


if __name__ == "__main__":
    unittest.main()
