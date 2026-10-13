import unittest
from unittest.mock import patch

import app as app_module


class BusinessAnalysisPermissionCacheTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "ou-cache-test"
            flask_session["feishu_user_name"] = "测试用户"
            flask_session["feishu_user_access_token"] = "test-user-token"

    def test_access_check_is_reused_for_page_assets_and_api_requests(self):
        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(True, "test"),
        ) as checker, patch.object(
            app_module,
            "_get_business_analysis_scope",
            return_value={"role": "ratio_viewer", "canViewAmounts": False},
        ), patch.object(
            app_module,
            "load_fiscal_overview",
            return_value={"ok": True},
        ):
            first = self.client.get("/api/ai/business-analysis/fiscal-overview")
            second = self.client.get("/api/ai/business-analysis/fiscal-overview")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        checker.assert_called_once_with("ou-cache-test", "business_analysis")

    def test_access_cache_is_isolated_by_debug_identity(self):
        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(True, "test"),
        ) as checker, patch.object(
            app_module,
            "_get_business_analysis_scope",
            return_value={"role": "ratio_viewer", "canViewAmounts": False},
        ), patch.object(
            app_module,
            "load_fiscal_overview",
            return_value={"ok": True},
        ):
            self.client.get("/api/ai/business-analysis/fiscal-overview")
            with self.client.session_transaction() as flask_session:
                flask_session["permission_debug_user_open_id"] = "ou-debug-user"
                flask_session["permission_debug_updated_at"] = "2026-09-03T10:00:00"
            self.client.get("/api/ai/business-analysis/fiscal-overview")

        self.assertEqual(checker.call_count, 2)

    def test_scope_endpoint_does_not_wait_for_dashboard_service(self):
        expected_scope = {
            "role": "member",
            "department": "运营一部",
            "operator": "测试用户",
            "userName": "测试用户",
            "canViewAmounts": False,
            "categoryRatioVisible": True,
        }
        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(True, "test"),
        ), patch.object(
            app_module,
            "_get_business_analysis_scope",
            return_value=expected_scope,
        ), patch.object(
            app_module,
            "_is_business_analysis_api_reachable",
        ) as service_check:
            response = self.client.get("/api/ai/business-analysis/scope")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"scope": expected_scope})
        service_check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
