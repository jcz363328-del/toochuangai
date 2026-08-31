from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from flask import Flask

from listing_agent_v2 import listing_agent_v2_bp
from listing_agent_v2 import blueprint as listing_v2_module


class ListingAgentV2BlueprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        self.app.secret_key = "listing-v2-test"

        @self.app.get("/auth/feishu")
        def feishu_auth():
            return "login"

        self.app.register_blueprint(listing_agent_v2_bp)
        self.client = self.app.test_client()

    def login(self) -> None:
        with self.client.session_transaction() as session:
            session["feishu_user_id"] = "ou_listing_v2_test"
            session["feishu_user_name"] = "V2 测试用户"

    def test_index_serves_independent_built_application(self) -> None:
        self.login()
        response = self.client.get("/listing-agent-v2/")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Focused Split Studio", page)
        self.assertIn("/listing-agent-v2/assets/", page)

    def test_health_requires_login_and_reports_shared_generation_api(self) -> None:
        unauthenticated = self.client.get("/listing-agent-v2/api/health")
        self.addCleanup(unauthenticated.close)
        self.assertEqual(unauthenticated.status_code, 401)

        self.login()
        response = self.client.get("/listing-agent-v2/api/health")
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["generationApi"],
            "/listing-agent/api/generate-listings",
        )

    def test_refine_returns_plain_model_content(self) -> None:
        self.login()
        completion = {
            "choices": [
                {
                    "message": {
                        "content": "Natural wispy lash clusters for customizable daily looks"
                    }
                }
            ]
        }
        fake_result = {
            "ok": True,
            "status": 200,
            "text": json.dumps(completion),
        }
        with (
            patch.object(listing_v2_module.listing_service, "_get_api_key", return_value="test-key"),
            patch.object(
                listing_v2_module.listing_service,
                "_call_siliconflow_with_text_fallbacks",
                return_value=fake_result,
            ),
        ):
            response = self.client.post(
                "/listing-agent-v2/api/refine",
                json={
                    "action": "optimize",
                    "field": "Item Highlights",
                    "content": "Wispy lashes",
                    "keywords": ["lash clusters"],
                    "limit": 125,
                },
            )
            self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["content"],
            "Natural wispy lash clusters for customizable daily looks",
        )


if __name__ == "__main__":
    unittest.main()
