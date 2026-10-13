import unittest
from unittest.mock import patch

import app as app_module


class BusinessAnalysisFiscalOverviewRouteTests(unittest.TestCase):
    def setUp(self):
        self.scope = {
            "role": "business_owner",
            "department": None,
            "operator": None,
            "userName": "周俊成",
            "canViewAmounts": True,
        }
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "ou-zhou-juncheng"
            flask_session["feishu_user_name"] = "周俊成"
            flask_session["feishu_user_access_token"] = "test-user-token"

    def test_route_passes_validated_fiscal_year_scope_and_force(self):
        expected = {"fiscalYear": "2026-2027", "overall": {"achievementRate": 0.9}}
        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(True, "test"),
        ), patch.object(
            app_module,
            "_get_business_analysis_scope",
            return_value=self.scope,
        ), patch.object(
            app_module,
            "load_fiscal_overview",
            return_value=expected,
        ) as loader:
            response = self.client.get(
                "/api/ai/business-analysis/fiscal-overview?fiscal_year=2026-2027&force=1"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), expected)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        loader.assert_called_once_with(
            "2026-2027",
            self.scope,
            force=True,
            filters={"department": None, "periodType": "annual", "period": None},
        )

    def test_route_forwards_department_and_period_filters(self):
        expected = {"fiscalYear": "2026-2027", "overall": {"achievementRate": 1}}
        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(True, "test"),
        ), patch.object(
            app_module,
            "_get_business_analysis_scope",
            return_value=self.scope,
        ), patch.object(
            app_module,
            "load_fiscal_overview",
            return_value=expected,
        ) as loader:
            response = self.client.get(
                "/api/ai/business-analysis/fiscal-overview?department=运营一部&period_type=month&period=2026-07"
            )

        self.assertEqual(response.status_code, 200)
        loader.assert_called_once_with(
            "2026-2027",
            self.scope,
            force=False,
            filters={"department": "运营一部", "periodType": "month", "period": "2026-07"},
        )

    def test_route_rejects_invalid_fiscal_year_without_querying_database(self):
        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(True, "test"),
        ), patch.object(
            app_module,
            "_get_business_analysis_scope",
            return_value=self.scope,
        ), patch.object(app_module, "load_fiscal_overview") as loader:
            response = self.client.get(
                "/api/ai/business-analysis/fiscal-overview?fiscal_year=2026-2028"
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "INVALID_FISCAL_OVERVIEW_QUERY")
        loader.assert_not_called()

    def test_route_converts_database_failure_to_service_unavailable(self):
        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(True, "test"),
        ), patch.object(
            app_module,
            "_get_business_analysis_scope",
            return_value=self.scope,
        ), patch.object(
            app_module,
            "load_fiscal_overview",
            side_effect=RuntimeError("database unavailable"),
        ):
            response = self.client.get("/api/ai/business-analysis/fiscal-overview")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"]["code"], "FISCAL_OVERVIEW_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
