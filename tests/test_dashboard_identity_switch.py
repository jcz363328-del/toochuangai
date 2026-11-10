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

    def _login(self, user_name="周俊成", base_url=None):
        session_options = {"base_url": base_url} if base_url else {}
        with self.client.session_transaction(**session_options) as flask_session:
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

    def test_default_favorites_can_be_removed_and_restored(self):
        source = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8-sig")

        self.assertIn("dashboard_hidden_default_favorites:${userKey}", source)
        self.assertIn("card.classList.toggle('favorite-hidden'", source)
        self.assertIn("hiddenDefaults = Array.from(new Set", source)
        self.assertIn("if (defaultMenus.has(menu))", source)
        self.assertNotIn("if (!menu || defaultMenus.has(menu)) return;", source)

    def test_secondary_favorites_are_rendered_on_dashboard(self):
        source = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8-sig")

        self.assertIn("dashboard_favorite_items:${userKey}", source)
        self.assertIn("secondaryItems.forEach(source =>", source)
        self.assertIn("source.iconClass || 'fa-solid fa-star'", source)

    def test_secondary_favorite_component_is_loaded_by_function_hubs(self):
        for template_name in (
            "ai_modules.html",
            "operation_dept.html",
            "tk_project.html",
            "finance_modules.html",
            "hr_admin_modules.html",
        ):
            source = (ROOT / "templates" / template_name).read_text(encoding="utf-8-sig")
            self.assertIn("dashboard_secondary_favorites.css", source, template_name)
            self.assertIn("dashboard_secondary_favorites.js", source, template_name)

    def test_secondary_favorites_carry_and_validate_permission_keys(self):
        dashboard = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8-sig")
        secondary = (ROOT / "static" / "js" / "dashboard_secondary_favorites.js").read_text(encoding="utf-8-sig")
        ai_modules = (ROOT / "templates" / "ai_modules.html").read_text(encoding="utf-8-sig")

        self.assertIn("dashboard_allowed_functions", dashboard)
        self.assertIn("permissionByMenu", dashboard)
        self.assertIn("source.permission || permissionByMenu[source.menu]", dashboard)
        self.assertIn("!currentSource || !currentSource.allowed", dashboard)
        self.assertIn("dataset.permission", secondary)
        self.assertIn('data-permission="daily_replenishment_operation"', ai_modules)

    def test_favorite_context_uses_current_identity(self):
        self._login("测试用户")

        response = self.client.get("/api/dashboard/favorites/context")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user_key"], "ou_real_operator")

    def test_every_default_favorite_has_a_full_feature_entry(self):
        environment = Environment(loader=FileSystemLoader(ROOT / "templates"))
        environment.globals["url_for"] = lambda endpoint, **values: f"/{endpoint}"
        environment.globals["get_flashed_messages"] = lambda **kwargs: []
        template = environment.get_template("dashboard.html")
        html = template.render(
            user_id="ou_test",
            user_name="测试用户",
            accessible_functions=[
                {
                    "function_name": "innovation_proposals",
                    "name": "创新提案管理",
                    "description": "",
                    "is_allowed": True,
                },
                {
                    "function_name": "xiaotu_qa",
                    "name": "报告智能体",
                    "description": "",
                    "is_allowed": True,
                },
                {
                    "function_name": "business_analysis",
                    "name": "经营分析",
                    "description": "",
                    "is_allowed": True,
                },
            ],
            can_value_evaluation=True,
            can_business_analysis=True,
            can_video_claw=False,
            can_switch_identity=False,
            permission_debug_departments=[],
            permission_debug_user_name="",
        )

        default_menus = (
            "创新提案管理",
            "报告智能体",
            "360价值评价",
            "经营分析",
            "Seedance 视频生成",
            "Listing 生成智能体",
            "ABA 排名看板",
            "年会精彩瞬间",
            "培训视频",
            "模特排队",
        )
        for menu in default_menus:
            self.assertGreaterEqual(
                html.count(f'data-menu="{menu}"'),
                2,
                f"{menu} 取消收藏后在全功能区找不到恢复入口",
            )

    def test_member_search_is_forbidden_for_other_users(self):
        self._login("其他成员")

        response = self.client.get("/api/dashboard/identity-switch/members?q=张三")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.get_json()["success"])

    @patch.object(app_module, "_xiaotu_search_notify_users")
    def test_cai_jing_can_switch_identity_like_zhou_juncheng(self, search_members):
        self._login("蔡晶")
        search_members.return_value = [
            {"open_id": "ou_target", "name": "张三", "display_name": "张三"},
        ]

        response = self.client.get("/api/dashboard/identity-switch/members?q=张三")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

    @patch.object(app_module, "_xiaotu_search_notify_users")
    def test_tenant_user_id_header_is_not_compared_with_session_open_id(self, search_members):
        self._login(base_url="http://app.example")
        search_members.return_value = [
            {"open_id": "ou_target", "name": "张三", "display_name": "张三"},
        ]

        response = self.client.get(
            "/api/dashboard/identity-switch/members?q=张三",
            base_url="http://app.example",
            headers={"X-Lark-User-Id": "tenant_user_123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

    @patch.object(app_module, "_xiaotu_search_notify_users")
    def test_matching_tenant_user_id_header_is_accepted(self, search_members):
        self._login(base_url="http://app.example")
        search_members.return_value = [
            {"open_id": "ou_target", "name": "张三", "display_name": "张三"},
        ]
        with self.client.session_transaction(base_url="http://app.example") as flask_session:
            flask_session["feishu_tenant_user_id"] = "tenant_user_123"

        response = self.client.get(
            "/api/dashboard/identity-switch/members?q=张三",
            base_url="http://app.example",
            headers={"X-Lark-User-Id": "tenant_user_123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

    def test_mismatching_tenant_user_id_header_requires_reauthorization(self):
        self._login(base_url="http://app.example")
        with self.client.session_transaction(base_url="http://app.example") as flask_session:
            flask_session["feishu_tenant_user_id"] = "tenant_user_123"

        response = self.client.get(
            "/api/dashboard/identity-switch/members?q=张三",
            base_url="http://app.example",
            headers={"X-Lark-User-Id": "tenant_user_456"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "身份已切换")

    def test_binding_keeps_open_id_and_tenant_user_id_separate(self):
        with app_module.app.test_request_context("/"):
            app_module._bind_feishu_session({
                "open_id": "ou_real_operator",
                "user_id": "tenant_user_123",
                "name": "周俊成",
            })

            self.assertEqual(app_module.session["feishu_user_id"], "ou_real_operator")
            self.assertEqual(app_module.session["feishu_open_id"], "ou_real_operator")
            self.assertEqual(app_module.session["feishu_tenant_user_id"], "tenant_user_123")

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
    def test_switch_uses_a_small_separate_signed_cookie(self, resolve_names, resolve_departments):
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
        identity_cookie = self.client.get_cookie(
            app_module._DASHBOARD_IDENTITY_SWITCH_COOKIE
        )
        self.assertIsNotNone(identity_cookie)
        self.assertLess(len(identity_cookie.value), 4093)
        cookie_payload = app_module._dashboard_identity_switch_state_serializer().loads(
            identity_cookie.value,
            max_age=app_module._DASHBOARD_IDENTITY_SWITCH_MAX_AGE_SECONDS,
        )
        self.assertEqual(cookie_payload["o"], "ou_real_operator")
        self.assertEqual(cookie_payload["u"], "ou_target")
        self.assertEqual(cookie_payload["n"], "张三")
        self.assertEqual(cookie_payload["d"], ["运营三部"])
        with self.client.session_transaction() as flask_session:
            self.assertEqual(flask_session["feishu_user_name"], "周俊成")
            self.assertNotIn("permission_debug_user_name", flask_session)
            self.assertNotIn("permission_debug_user_open_id", flask_session)
            self.assertNotIn("permission_debug_departments", flask_session)
            self.assertNotIn("preloaded_functions", flask_session)

    def test_signed_switch_cookie_is_loaded_for_permission_checks(self):
        updated_at = "2026-09-03T20:00:00"
        with app_module.app.test_request_context("/"):
            app_module.session["feishu_user_id"] = "ou_real_operator"
            app_module.session["feishu_open_id"] = "ou_real_operator"
            app_module.session["feishu_user_name"] = "周俊成"
            identity_token = app_module._dashboard_identity_switch_state_token(
                "ou_target",
                "张三",
                ["运营三部"],
                updated_at,
            )

        with app_module.app.test_request_context(
            "/",
            headers={
                "Cookie": (
                    f"{app_module._DASHBOARD_IDENTITY_SWITCH_COOKIE}={identity_token}"
                )
            },
        ):
            app_module.session["feishu_user_id"] = "ou_real_operator"
            app_module.session["feishu_open_id"] = "ou_real_operator"
            app_module.session["feishu_user_name"] = "周俊成"

            loaded = app_module._load_dashboard_identity_switch_request_state()
            state = app_module._permission_debug_session_state()
            manager = FeishuPermissionManager()

            self.assertEqual(loaded["user_open_id"], "ou_target")
            self.assertEqual(state["current_user_name"], "张三")
            self.assertEqual(state["current_departments"], ["运营三部"])
            self.assertEqual(
                manager._get_debug_user_from_session(),
                {"name": "张三", "open_id": "ou_target"},
            )
            self.assertEqual(
                manager._get_debug_departments_from_session(),
                ["运营三部"],
            )

    def test_simulated_liu_only_gets_the_business_analysis_ai_card(self):
        manager = FeishuPermissionManager()
        records = {
            "ai_dept": {
                "function_name": "ai_dept",
                "name": "AI部功能",
                "description": "",
                "bumen": "AI部；总经办",
                "yonghu": "",
                "fujigongneng": "",
            },
            "admin_functions": {
                "function_name": "admin_functions",
                "name": "管理员功能",
                "description": "",
                "bumen": "AI部；总经办",
                "yonghu": "",
                "fujigongneng": "",
            },
            "business_analysis": {
                "function_name": "business_analysis",
                "name": "经营分析",
                "description": "",
                "bumen": "运营三部；AI部；总经办",
                "yonghu": "",
                "fujigongneng": "ai_dept",
            },
            "business_analysis_all": {
                "function_name": "business_analysis_all",
                "name": "经营分析（全量权限）",
                "description": "",
                "bumen": "AI部；总经办",
                "yonghu": "刘蓉蓉",
                "fujigongneng": "business_analysis",
            },
            "ads_monitor": {
                "function_name": "ads_monitor",
                "name": "MAGIC AD 广告监控",
                "description": "",
                "bumen": "AI部；总经办",
                "yonghu": "孙洁；侯梁",
                "fujigongneng": "ai_dept",
            },
        }
        manager.get_permission_records = lambda force_refresh=False: records
        manager.get_user_permission_overrides = lambda user_id: {}

        def user_departments(user_id):
            department_name = "运营三部" if user_id == "ou_liu" else "AI部"
            return [{
                "department_id": f"test:{department_name}",
                "name": department_name,
                "status": "active",
            }]

        manager.get_user_departments = user_departments

        with app_module.app.test_request_context("/"):
            app_module.g.permission_debug_state = {
                "departments": ["运营三部"],
                "user_name": "刘蓉蓉",
                "user_open_id": "ou_liu",
                "updated_at": "2026-09-04T10:00:00",
            }
            visible = {
                item["function_name"]
                for item in manager.get_user_accessible_functions("ou_real_operator")
            }
            ai_allowed = manager.check_user_permission(
                "ou_real_operator", "ai_dept"
            )[0]
            admin_allowed = manager.check_user_permission(
                "ou_real_operator", "admin_functions"
            )[0]
            ads_allowed = manager.check_user_permission(
                "ou_real_operator", "ads_monitor"
            )[0]

        self.assertEqual(
            {"ai_dept", "business_analysis", "business_analysis_all"},
            visible,
        )
        self.assertTrue(ai_allowed)
        self.assertFalse(admin_allowed)
        self.assertFalse(ads_allowed)

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

    def test_business_analysis_scope_uses_switched_member_identity_for_department_leader(self):
        original_check = app_module.permission_manager.check_user_permission
        original_departments = app_module.permission_manager.get_user_departments
        original_leader = app_module._xiaotu_get_department_leader_user_id
        try:
            app_module.permission_manager.check_user_permission = lambda user_id, function_name: (False, "")
            app_module.permission_manager.get_user_departments = lambda user_id: [{
                "department_id": "od_operation_6",
                "name": "运营六部",
                "status": "active",
            }]
            app_module._xiaotu_get_department_leader_user_id = lambda department_id: "ou_operation_6_leader"

            with app_module.app.test_request_context("/"):
                app_module.session["feishu_user_id"] = "ou_real_admin"
                app_module.session["feishu_user_name"] = "管理员"
                app_module.g.permission_debug_state = {
                    "departments": ["运营六部"],
                    "user_name": "郭鑫",
                    "user_open_id": "ou_operation_6_leader",
                    "updated_at": "2026-09-07T16:00:00",
                }

                scope = app_module._get_business_analysis_scope(resolve_leader=True)

            self.assertEqual(scope["role"], "department_leader")
            self.assertEqual(scope["department"], "运营六部")
            self.assertIsNone(scope["operator"])
            self.assertTrue(scope["canViewAmounts"])
        finally:
            app_module.permission_manager.check_user_permission = original_check
            app_module.permission_manager.get_user_departments = original_departments
            app_module._xiaotu_get_department_leader_user_id = original_leader


if __name__ == "__main__":
    unittest.main()
