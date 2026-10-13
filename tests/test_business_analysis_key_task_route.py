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
        with patch.object(app_module, "_get_business_analysis_scope", return_value=self.scope), patch.object(
            app_module, "_is_business_analysis_api_reachable", return_value=False
        ), patch.object(
            app_module, "_ensure_business_analysis_api_started", return_value=False
        ), patch.object(
            app_module.time, "sleep", return_value=None
        ):
            response = self.client.get("/api/ai/business-analysis/dashboard?period=2026-09")

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


if __name__ == "__main__":
    unittest.main()
