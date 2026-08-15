from __future__ import annotations

import io
import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from openpyxl import Workbook

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

    def test_xlsx_aba_import_supports_title_row_and_chinese_columns(self) -> None:
        self.login()
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "ABA 数据"
        worksheet.append(["ABA 搜索词排名导出"])
        worksheet.append(
            [
                "站点名称",
                "搜索词",
                "搜索词频率排名",
                "排名环比",
                "排名同比",
                "前3ASIN点击量占比",
                "前3ASIN转化占比",
            ]
        )
        worksheet.append(["美国", "lash xlsx keyword", "2,345", 0.2, 0.1, 0.35, 0.28])
        xlsx_file = io.BytesIO()
        workbook.save(xlsx_file)
        workbook.close()
        xlsx_file.seek(0)
        malformed_dimension_file = io.BytesIO()
        with zipfile.ZipFile(xlsx_file, "r") as source_zip, zipfile.ZipFile(
            malformed_dimension_file, "w"
        ) as target_zip:
            for item in source_zip.infolist():
                content = source_zip.read(item.filename)
                if item.filename == "xl/worksheets/sheet1.xml":
                    content = re.sub(
                        br'<dimension ref="[^"]+"\s*/>',
                        b'<dimension ref="A1"/>',
                        content,
                        count=1,
                    )
                target_zip.writestr(item, content)
        malformed_dimension_file.seek(0)

        with tempfile.TemporaryDirectory() as temporary_directory:
            active_file = Path(temporary_directory) / "active-aba-ranking.json"
            with patch.object(listing_module, "ACTIVE_RANKING_FILE", active_file):
                response = self.client.post(
                    "/listing-agent/api/sellfox/import-ranking",
                    data={"file": (malformed_dimension_file, "aba-export.xlsx")},
                    content_type="multipart/form-data",
                )
                self.addCleanup(response.close)
                saved = json.loads(active_file.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["summary"]["uniqueTerms"], 1)
        self.assertEqual(saved["meta"]["importedSource"], "aba-export.xlsx")
        self.assertEqual(saved["rows"][0]["searchTerm"], "lash xlsx keyword")
        self.assertEqual(saved["rows"][0]["searchFrequencyRank"], 2345)
        self.assertEqual(saved["rows"][0]["previousSearchFrequencyRank"], 2931)
        self.assertAlmostEqual(saved["rows"][0]["top3AsinConversionShare"], 0.28)

    def test_four_xlsx_files_merge_into_one_dashboard_with_source_masks(self) -> None:
        self.login()

        def build_xlsx(core_term: str, rank: int) -> io.BytesIO:
            headers = [
                "站点名称", "搜索词", "搜索词频率排名", "排名环比", "排名同比",
                "前3ASIN点击量占比", "前3ASIN转化占比",
                "#1已点击的ASIN", "#1商品名称", "#1点击份额", "#1转化份额",
                "#1品牌", "#1品类", "#1月销量",
                "#2已点击的ASIN", "#2商品名称", "#2点击份额", "#2转化份额",
                "#2品牌", "#2品类", "#2月销量",
                "#3已点击的ASIN", "#3商品名称", "#3点击份额", "#3转化份额",
                "#3品牌", "#3品类", "#3月销量", "商品数",
            ]

            def ranking_row(term: str, current_rank: int) -> list[object]:
                values: list[object] = [None] * 29
                values[:7] = ["美国", term, current_rank, 0.2, 0.1, 0.35, 0.28]
                values[7:14] = [
                    f"ASIN-{core_term}", f"{core_term} product", 0.2, 0.15,
                    f"{core_term} brand", "Beauty & Personal Care", 1000,
                ]
                values[28] = 500
                return values

            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(headers)
            worksheet.append(ranking_row(core_term, rank))
            worksheet.append(ranking_row("shared keyword", 100))
            stream = io.BytesIO()
            workbook.save(stream)
            workbook.close()
            stream.seek(0)
            return stream

        uploads = [
            (
                build_xlsx(core_term, 1000 + index),
                f"search_terms_analysis_2026-08-02~2026-08-08-{index}.xlsx",
            )
            for index, core_term in enumerate(("lash", "lashes", "eyelash", "eyelashes"), 1)
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            active_file = Path(temporary_directory) / "active-aba-ranking.json"
            with patch.object(listing_module, "ACTIVE_RANKING_FILE", active_file):
                response = self.client.post(
                    "/listing-agent/api/sellfox/import-ranking",
                    data={"file": uploads[0], "files": uploads[1:]},
                    content_type="multipart/form-data",
                )
                dashboard_response = self.client.get("/listing-agent/aba-ranking/")
                self.addCleanup(response.close)
                self.addCleanup(dashboard_response.close)
                saved = json.loads(active_file.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["summary"]["rawRows"], 8)
        self.assertEqual(response.get_json()["summary"]["uniqueTerms"], 5)
        self.assertEqual(saved["meta"]["dateRange"], "2026-08-02 至 2026-08-08")
        self.assertEqual(len(saved["meta"]["sourceSummary"]), 4)
        rows = {row["searchTerm"]: row for row in saved["rows"]}
        self.assertEqual(rows["shared keyword"]["sourceMask"], 15)
        self.assertEqual(rows["shared keyword"]["sourceCount"], 4)
        self.assertEqual(rows["lash"]["sourceMask"], 1)
        self.assertEqual(rows["lashes"]["sourceMask"], 2)
        self.assertEqual(rows["eyelash"]["sourceMask"], 4)
        self.assertEqual(rows["eyelashes"]["sourceMask"], 8)
        self.assertEqual(rows["lash"]["top3ProductNames"][0], "lash product")
        self.assertIn("lash product", dashboard_response.get_data(as_text=True))

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
