from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from listing_agent import listing_agent_bp
from listing_agent import blueprint as listing_module


class ListingAgentBlueprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        self.app.secret_key = "listing-agent-test"
        self.app.register_blueprint(listing_agent_bp)
        self.client = self.app.test_client()
        with listing_module._settings_lock:
            self.original_settings = dict(listing_module._runtime_settings)
            listing_module._runtime_settings.update(
                {
                    "api_key": "test-key",
                    "model": listing_module.DEFAULT_SILICONFLOW_MODEL,
                    "text_model": "",
                }
            )

    def tearDown(self) -> None:
        with listing_module._settings_lock:
            listing_module._runtime_settings.clear()
            listing_module._runtime_settings.update(self.original_settings)

    def login(self) -> None:
        with self.client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "test-user"

    def test_api_requires_login(self) -> None:
        response = self.client.get("/listing-agent/api/health")

        self.assertEqual(response.status_code, 401)
        self.assertIn("请先登录", response.get_json()["error"])

    def test_page_assets_and_aba_data_are_served_under_prefix(self) -> None:
        self.login()

        page = self.client.get("/listing-agent/")
        script = self.client.get("/listing-agent/app.js")
        dashboard = self.client.get("/listing-agent/aba-ranking/")
        ranking = self.client.get("/listing-agent/api/sellfox/ranking-file")
        self.addCleanup(page.close)
        self.addCleanup(script.close)
        self.addCleanup(dashboard.close)
        self.addCleanup(ranking.close)

        self.assertEqual(page.status_code, 200)
        page_text = page.get_data(as_text=True)
        self.assertIn("Listing Agent Studio", page_text)
        self.assertIn("导入 ABA 看板", page_text)
        self.assertLess(page_text.index('id="abaRankingImport"'), page_text.index('class="panel input-panel"'))
        self.assertEqual(script.status_code, 200)
        self.assertIn("/listing-agent/api", script.get_data(as_text=True))
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("ABA 四核心词综合排名", dashboard.get_data(as_text=True))
        self.assertIn("const DATA =", dashboard.get_data(as_text=True))
        self.assertEqual(ranking.status_code, 200)
        payload = ranking.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["rows"]), 4571)
        self.assertEqual(payload["meta"]["uniqueTermCount"], 4571)

    def test_image_extraction_normalizes_model_response(self) -> None:
        self.login()
        model_content = {
            "facts": [
                {
                    "key": "lengths",
                    "label": "长度",
                    "value": "10-14mm",
                    "source": "包装文字",
                    "confidence": "high",
                }
            ],
            "needsConfirmation": ["根数需要确认"],
            "doNotInfer": ["不要推断材质"],
        }
        completion = {"choices": [{"message": {"content": json.dumps(model_content, ensure_ascii=False)}}]}
        fake_result = {
            "ok": True,
            "status": 200,
            "text": json.dumps(completion, ensure_ascii=False),
            "model": listing_module.DEFAULT_SILICONFLOW_MODEL,
        }

        with patch.object(listing_module, "_call_siliconflow_with_fallbacks", return_value=fake_result):
            response = self.client.post(
                "/listing-agent/api/extract-image",
                json={
                    "marketplace": "US",
                    "category": "lash clusters",
                    "images": [
                        {
                            "name": "product.png",
                            "type": "image/png",
                            "dataUrl": "data:image/png;base64,AA==",
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["facts"][0]["key"], "lengths")
        self.assertEqual(payload["facts"][0]["confidence"], "high")
        self.assertIn("不要推断材质", payload["doNotInfer"])
        self.assertGreater(len(payload["doNotInfer"]), 1)

    def test_imported_aba_file_becomes_ranking_detail_source(self) -> None:
        self.login()
        imported = {
            "meta": {"dateRange": "2026-08-01 至 2026-08-07"},
            "rows": [
                {
                    "marketplace": "美国",
                    "searchTerm": "custom lash keyword",
                    "searchFrequencyRank": "1,200",
                    "rankMoM": "25%",
                    "rankYoY": "10%",
                    "top3AsinClickShare": "32%",
                    "top3AsinConversionShare": "28%",
                    "top3AsinList": ["B000000001"],
                    "topBrands": ["Example Brand"],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            active_file = Path(temporary_directory) / "active-aba-ranking.json"
            with patch.object(listing_module, "ACTIVE_RANKING_FILE", active_file):
                imported_response = self.client.post(
                    "/listing-agent/api/sellfox/import-ranking",
                    data={
                        "file": (
                            io.BytesIO(json.dumps(imported, ensure_ascii=False).encode("utf-8")),
                            "my-aba-dashboard.json",
                        )
                    },
                    content_type="multipart/form-data",
                )
                ranking_response = self.client.get("/listing-agent/api/sellfox/ranking-file")
                dashboard_response = self.client.get("/listing-agent/aba-ranking/")

                self.addCleanup(imported_response.close)
                self.addCleanup(ranking_response.close)
                self.addCleanup(dashboard_response.close)
                self.assertTrue(active_file.exists())

        self.assertEqual(imported_response.status_code, 200)
        self.assertEqual(imported_response.get_json()["summary"]["uniqueTerms"], 1)
        self.assertEqual(ranking_response.status_code, 200)
        ranking_payload = ranking_response.get_json()
        self.assertEqual(ranking_payload["source"], "my-aba-dashboard.json")
        self.assertEqual(ranking_payload["rows"][0]["searchTerm"], "custom lash keyword")
        self.assertEqual(ranking_payload["rows"][0]["previousSearchFrequencyRank"], 1600)
        self.assertAlmostEqual(ranking_payload["rows"][0]["top3AsinClickShare"], 0.32)
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("custom lash keyword", dashboard_response.get_data(as_text=True))

    def test_csv_aba_import_maps_chinese_columns_and_percentages(self) -> None:
        csv_source = (
            "站点名称,搜索词,搜索词频率排名,排名环比,排名同比,前3ASIN点击量占比,前3ASIN转化占比\n"
            '美国,lash csv keyword,"2,345",20%,10%,35%,28%\n'
        ).encode("utf-8")

        parsed = listing_module._parse_uploaded_ranking_data(
            csv_source,
            ".csv",
            "aba-export.csv",
        )

        self.assertEqual(parsed["meta"]["uniqueTermCount"], 1)
        self.assertEqual(parsed["meta"]["importedSource"], "aba-export.csv")
        self.assertEqual(parsed["rows"][0]["searchFrequencyRank"], 2345)
        self.assertEqual(parsed["rows"][0]["previousSearchFrequencyRank"], 2931)
        self.assertAlmostEqual(parsed["rows"][0]["top3AsinConversionShare"], 0.28)

    def test_listing_generation_returns_exactly_three_variants(self) -> None:
        self.login()
        variants = []
        for variant_id in ("balanced", "style", "search"):
            variants.append(
                {
                    "id": variant_id,
                    "title": f"{variant_id} title",
                    "highlights": ["One", "Two", "Three"],
                    "bullets": ["One", "Two", "Three", "Four", "Five"],
                    "description": "Description",
                    "searchTerms": "lash clusters wispy",
                    "reasons": ["测试理由"],
                }
            )
        completion = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"variants": variants}, ensure_ascii=False),
                    }
                }
            ]
        }
        fake_result = {
            "ok": True,
            "status": 200,
            "text": json.dumps(completion, ensure_ascii=False),
            "model": listing_module.DEFAULT_SILICONFLOW_MODEL,
        }

        with patch.object(listing_module, "_call_siliconflow", return_value=fake_result) as mocked_call:
            response = self.client.post(
                "/listing-agent/api/generate-listings",
                json={
                    "marketplace": "US",
                    "product": {"type": "lash clusters", "brand": "ALICE"},
                    "keywords": {},
                    "compliance": {},
                    "skill": {},
                    "limits": {},
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual([item["id"] for item in payload["variants"]], ["balanced", "style", "search"])
        request_payload = mocked_call.call_args.args[1]
        self.assertEqual(request_payload["messages"][0]["role"], "system")
        self.assertIn("lash clusters", request_payload["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
