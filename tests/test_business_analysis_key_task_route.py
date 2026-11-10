import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module
from business_analysis_key_tasks import KeyTaskStore


class BusinessAnalysisKeyTaskRouteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = KeyTaskStore(Path(self.temporary.name) / "key-tasks.json")
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
            flask_session["feishu_open_id"] = "ou-zhou-juncheng"
            flask_session["feishu_user_name"] = "周俊成"
            flask_session["feishu_user_access_token"] = "test-user-token"

    def tearDown(self):
        self.temporary.cleanup()

    def test_route_works_without_business_analysis_node_service(self):
        payload = {
            "department": "运营一部",
            "project": "product-pilot",
            "task": "路由冒烟任务",
            "owner": "周俊成",
            "output": "",
            "nextCheckpoint": "",
            "risk": "",
            "status": "started",
        }
        with patch.object(app_module, "_get_business_analysis_scope", return_value=self.scope), patch.object(
            app_module, "_business_analysis_key_task_store", self.store
        ), patch.object(
            app_module,
            "_is_business_analysis_api_reachable",
            side_effect=AssertionError("关键任务路由不应再调用 Node 健康检查"),
        ):
            initial = self.client.get("/api/ai/business-analysis/key-tasks")
            self.assertEqual(initial.status_code, 200)
            self.assertEqual(initial.get_json()["meta"]["scope"]["role"], "business_owner")

            created = self.client.post("/api/ai/business-analysis/key-tasks", json=payload)
            self.assertEqual(created.status_code, 200)
            task_id = created.get_json()["created"][0]["id"]

            listed = self.client.get("/api/ai/business-analysis/key-tasks")
            self.assertEqual([item["id"] for item in listed.get_json()["tasks"]], [task_id])

            removed = self.client.delete(f"/api/ai/business-analysis/key-tasks/{task_id}")
            self.assertEqual(removed.status_code, 200)

    def test_dashboard_returns_permission_scoped_daily_snapshot_without_node(self):
        with open(app_module._BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH, encoding="utf-8") as handle:
            snapshot_period = json.load(handle)["period"]
        with patch.object(app_module, "_get_business_analysis_scope", return_value=self.scope), patch.object(
            app_module, "_is_business_analysis_api_reachable", return_value=False
        ), patch.object(
            app_module, "_ensure_business_analysis_api_started", return_value=False
        ), patch.object(
            app_module.time, "sleep", return_value=None
        ):
            response = self.client.get(
                f"/api/ai/business-analysis/dashboard?period={snapshot_period}"
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Business-Analysis-Source"], "daily-snapshot")
        self.assertEqual(payload["source"]["mode"], "daily-snapshot")
        self.assertEqual(payload["data"]["meta"]["accessScope"]["role"], "business_owner")
        self.assertTrue(payload["data"]["meta"]["accessScope"]["canViewAmounts"])
        self.assertGreater(len(payload["data"]["performance"]["stores"]), 0)
        self.assertNotIn("categorySegmentsByPeriod", payload["data"])
        paired = payload["data"]["categorySegments"]["categories"][0]
        self.assertGreater(paired["company"]["yearAgo"]["sales"], 0)
        self.assertIsNotNone(paired["ratios"]["company"]["dailyYoy"])

    def test_previous_month_also_returns_daily_snapshot_without_node(self):
        with open(app_module._BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH, encoding="utf-8") as handle:
            snapshot = json.load(handle)
        cached_periods = list(snapshot.get("periods") or {})
        self.assertGreaterEqual(len(cached_periods), 2)
        previous_period = cached_periods[1]

        with patch.object(app_module, "_get_business_analysis_scope", return_value=self.scope), patch.object(
            app_module,
            "_is_business_analysis_api_reachable",
            side_effect=AssertionError("cached previous month must not call the Node service"),
        ):
            response = self.client.get(
                f"/api/ai/business-analysis/dashboard?period={previous_period}"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Business-Analysis-Source"], "daily-snapshot")
        self.assertEqual(response.headers["X-Business-Analysis-Period"], previous_period)
        current = next(
            row for row in response.get_json()["data"]["performance"]["periods"]
            if row["key"] == "current"
        )
        self.assertEqual(current["label"], previous_period)

    def test_historical_period_is_forwarded_instead_of_returning_current_snapshot(self):
        with open(app_module._BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH, encoding="utf-8") as handle:
            snapshot_period = json.load(handle)["period"]
        year, month = map(int, snapshot_period.split("-"))
        month -= 2
        if month <= 0:
            year -= 1
            month += 12
        historical_period = f"{year:04d}-{month:02d}"
        upstream_payload = {
            "data": {
                "meta": {},
                "performance": {"periods": [], "departments": [], "stores": [], "periodRows": []},
                "slowMoving": [],
                "shipping": [],
            },
            "formulas": [],
            "source": {"mode": "database", "stale": False},
        }

        class UpstreamResponse:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            content = b""

            @staticmethod
            def json():
                return upstream_payload

        with patch.object(app_module, "_get_business_analysis_scope", return_value=self.scope), patch.object(
            app_module, "_is_business_analysis_api_reachable", return_value=True
        ), patch.object(app_module.requests, "get", return_value=UpstreamResponse()) as upstream_get:
            response = self.client.get(
                f"/api/ai/business-analysis/dashboard?period={historical_period}"
            )

        self.assertEqual(response.status_code, 200)
        forwarded_params = dict(upstream_get.call_args.kwargs["params"])
        self.assertEqual(forwarded_params["period"], historical_period)
        self.assertEqual(response.get_json()["source"]["mode"], "database")


if __name__ == "__main__":
    unittest.main()
