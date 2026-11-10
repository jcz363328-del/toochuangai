from __future__ import annotations

import gzip
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
        listing_module._clear_aba_dashboard_render_cache()
        self.app = Flask(__name__)
        self.app.secret_key = "listing-agent-test"
        self.app.register_blueprint(listing_agent_bp)
        self.client = self.app.test_client()
        self.ai_config_patcher = patch.object(
            listing_module,
            "ai_runtime_config",
            return_value={
                "provider": "siliconflow",
                "api_key": "daily-report-test-key",
                "base_url": "https://daily-report-ai.example/v1",
                "text_model": "daily-report-text-model",
                "vision_model": "daily-report-vision-model",
            },
        )
        self.ai_config_patcher.start()
        self.permission_patcher = patch.object(
            listing_module.permission_manager,
            "check_user_permission",
            return_value=(True, "test permission"),
        )
        self.permission_patcher.start()
        self.storage_directory = tempfile.TemporaryDirectory()
        storage_root = Path(self.storage_directory.name)
        self.aba_storage_dir = storage_root / "ABA排名"
        self.skill_storage_dir = storage_root / "Skills"
        self.listing_storage_dir = storage_root / "lisitng"
        self.storage_patchers = [
            patch.object(listing_module, "ABA_RANKING_STORAGE_DIR", self.aba_storage_dir),
            patch.object(listing_module, "SKILL_STORAGE_DIR", self.skill_storage_dir),
            patch.object(listing_module, "LISTING_ARCHIVE_DIR", self.listing_storage_dir),
            patch.object(listing_module, "ACTIVE_RANKING_FILE", self.aba_storage_dir / "active-aba-ranking.json"),
        ]
        for storage_patcher in self.storage_patchers:
            storage_patcher.start()
        self.db_write_patcher = patch.object(listing_module, "dui_db", return_value=None)
        self.mock_dui_db = self.db_write_patcher.start()

    def tearDown(self) -> None:
        listing_module._clear_aba_dashboard_render_cache()
        self.db_write_patcher.stop()
        for storage_patcher in reversed(self.storage_patchers):
            storage_patcher.stop()
        self.storage_directory.cleanup()
        self.permission_patcher.stop()
        self.ai_config_patcher.stop()

    def login(self) -> None:
        with self.client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "test-user"
            flask_session["feishu_user_name"] = "测试用户"

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
        self.assertIn("当前 ABA 排名数据（只读）", page_text)
        self.assertNotIn("导入 ABA 看板", page_text)
        self.assertNotIn("siliconFlowApiKey", page_text)
        self.assertNotIn("siliconFlowModel", page_text)
        self.assertNotIn("siliconFlowTextModel", page_text)
        self.assertNotIn("硅基流动配置", page_text)
        self.assertLess(page_text.index('id="abaRankingContext"'), page_text.index('class="panel input-panel"'))
        self.assertEqual(script.status_code, 200)
        script_text = script.get_data(as_text=True)
        self.assertIn("/listing-agent/api", script_text)
        self.assertNotIn("saveApiConfig", script_text)
        self.assertNotIn("aiResponse.model", script_text)
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("ABA 四核心词综合排名", dashboard.get_data(as_text=True))
        self.assertIn("const DATA =", dashboard.get_data(as_text=True))
        self.assertIn('id="tcAbaImportPanel"', dashboard.get_data(as_text=True))
        self.assertIn('id="excludeInput"', dashboard.get_data(as_text=True))
        self.assertIn('data-exclude-mode="all"', dashboard.get_data(as_text=True))
        self.assertIn('data-exclude-mode="excluded"', dashboard.get_data(as_text=True))
        self.assertIn("matchesExclusion(row)", dashboard.get_data(as_text=True))
        self.assertEqual(ranking.status_code, 200)
        payload = ranking.get_json()
        self.assertTrue(payload["ok"])
        self.assertGreater(len(payload["rows"]), 0)
        self.assertEqual(payload["meta"]["uniqueTermCount"], len(payload["rows"]))

    def test_aba_dashboard_is_gzipped_revalidated_and_splits_echarts_asset(self) -> None:
        self.login()

        dashboard = self.client.get(
            "/listing-agent/aba-ranking/",
            headers={"Accept-Encoding": "gzip"},
        )
        self.addCleanup(dashboard.close)
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.headers.get("Content-Encoding"), "gzip")
        self.assertIn("private", dashboard.headers.get("Cache-Control", ""))
        self.assertIn("no-cache", dashboard.headers.get("Cache-Control", ""))
        self.assertIn("Accept-Encoding", dashboard.headers.get("Vary", ""))
        html = gzip.decompress(dashboard.get_data()).decode("utf-8")
        self.assertIn("/listing-agent/aba-ranking/echarts.min.js?v=", html)
        self.assertNotIn("Licensed to the Apache Software Foundation", html)

        revalidated = self.client.get(
            "/listing-agent/aba-ranking/",
            headers={
                "Accept-Encoding": "gzip",
                "If-None-Match": dashboard.headers["ETag"],
            },
        )
        self.addCleanup(revalidated.close)
        self.assertEqual(revalidated.status_code, 304)

        echarts = self.client.get(
            "/listing-agent/aba-ranking/echarts.min.js",
            headers={"Accept-Encoding": "gzip"},
        )
        self.addCleanup(echarts.close)
        self.assertEqual(echarts.status_code, 200)
        self.assertEqual(echarts.headers.get("Content-Encoding"), "gzip")
        self.assertIn("immutable", echarts.headers.get("Cache-Control", ""))
        self.assertIn(
            "Licensed to the Apache Software Foundation",
            gzip.decompress(echarts.get_data()).decode("utf-8"),
        )

    def test_aba_dashboard_reuses_render_until_active_file_changes(self) -> None:
        self.login()
        first_payload = {
            "meta": {"dateRange": "2026-08-01 至 2026-08-07"},
            "rows": [
                {
                    "marketplace": "美国",
                    "searchTerm": "cached keyword",
                    "searchFrequencyRank": 1200,
                }
            ],
        }
        second_payload = {
            "meta": {"dateRange": "2026-08-08 至 2026-08-14"},
            "rows": [
                {
                    "marketplace": "美国",
                    "searchTerm": "changed cached keyword",
                    "searchFrequencyRank": 900,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            active_file = Path(temporary_directory) / "active-aba-ranking.json"
            active_file.write_text(json.dumps(first_payload, ensure_ascii=False), encoding="utf-8")
            with (
                patch.object(listing_module, "ACTIVE_RANKING_FILE", active_file),
                patch.object(
                    listing_module,
                    "_load_ranking_data",
                    wraps=listing_module._load_ranking_data,
                ) as load_ranking_data,
            ):
                first = self.client.get("/listing-agent/aba-ranking/")
                second = self.client.get("/listing-agent/aba-ranking/")
                active_file.write_text(json.dumps(second_payload, ensure_ascii=False), encoding="utf-8")
                third = self.client.get("/listing-agent/aba-ranking/")
                self.addCleanup(first.close)
                self.addCleanup(second.close)
                self.addCleanup(third.close)

        self.assertEqual(load_ranking_data.call_count, 2)
        self.assertIn("cached keyword", first.get_data(as_text=True))
        self.assertIn("cached keyword", second.get_data(as_text=True))
        self.assertIn("changed cached keyword", third.get_data(as_text=True))

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
        self.assertEqual(payload["source"], "服务端图片识别")
        self.assertIn("不要推断材质", payload["doNotInfer"])
        self.assertGreater(len(payload["doNotInfer"]), 1)

    def test_image_extraction_falls_back_when_configured_model_no_longer_exists(self) -> None:
        unavailable = {
            "ok": False,
            "status": 400,
            "error": {"code": 20012, "message": "Model does not exist. Please check it carefully."},
        }
        available = {"ok": True, "status": 200, "text": "{}"}
        with (
            patch.object(listing_module, "_get_model", return_value="retired/vision-model"),
            patch.object(
                listing_module,
                "_call_siliconflow",
                side_effect=[unavailable, available],
            ) as call_siliconflow,
        ):
            result = listing_module._call_siliconflow_with_fallbacks(
                "test-key",
                {"messages": []},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(call_siliconflow.call_count, 2)
        self.assertEqual(
            call_siliconflow.call_args_list[1].args[1]["model"],
            listing_module.DEFAULT_SILICONFLOW_MODEL,
        )
        self.assertTrue(listing_module._model_unavailable(unavailable))

    def test_ai_configuration_is_server_managed_and_hides_models(self) -> None:
        self.login()

        settings = self.client.get("/listing-agent/api/settings")
        health = self.client.get("/listing-agent/api/health")
        update = self.client.post(
            "/listing-agent/api/settings",
            json={"apiKey": "browser-key", "model": "browser-model"},
        )

        self.assertEqual(settings.status_code, 200)
        self.assertEqual(
            settings.get_json(),
            {"managed": True, "aiConfigured": True, "canImportAba": True},
        )
        self.assertEqual(health.get_json(), {"ok": True, "aiConfigured": True})
        self.assertEqual(update.status_code, 405)
        self.assertEqual(listing_module._get_api_key(), "daily-report-test-key")
        self.assertEqual(listing_module._get_ai_base_url(), "https://daily-report-ai.example/v1")
        self.assertNotIn("model", settings.get_json())
        self.assertNotIn("model", health.get_json())

    def test_aba_import_requires_dedicated_permission(self) -> None:
        self.login()
        with patch.object(
            listing_module.permission_manager,
            "check_user_permission",
            return_value=(False, "个人权限未命中"),
        ):
            settings = self.client.get("/listing-agent/api/settings")
            response = self.client.post(
                "/listing-agent/api/sellfox/import-ranking",
                data={"file": (io.BytesIO(b"{}"), "blocked.json")},
                content_type="multipart/form-data",
            )
            dashboard = self.client.get("/listing-agent/aba-ranking/")

        self.assertEqual(settings.status_code, 200)
        self.assertFalse(settings.get_json()["canImportAba"])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["requiredFunction"], "listing_agent_aba_import")
        self.assertNotIn("tcAbaImportPanel", dashboard.get_data(as_text=True))

    def test_aba_import_button_is_permission_driven(self) -> None:
        root = Path(__file__).resolve().parents[1]
        page = (root / "listing_agent" / "code" / "index.html").read_text(encoding="utf-8")
        script = (root / "listing_agent" / "code" / "app.js").read_text(encoding="utf-8")
        seed_data = (root / "permission_seed_data.py").read_text(encoding="utf-8")
        self.assertNotIn('id="importAbaRankingBtn"', page)
        self.assertNotIn('id="abaRankingFileInput"', page)
        self.assertNotIn("importAbaRankingFiles", script)
        self.assertIn('"gongneng": "listing_agent_aba_import"', seed_data)
        self.assertIn('"yonghu": ""', seed_data)
        self.assertIn('"bumen": "AI部"', seed_data)

    def test_image_recognition_supplement_remains_optional_when_no_facts_are_returned(self) -> None:
        root = Path(__file__).resolve().parents[1]
        page = (root / "listing_agent" / "code" / "index.html").read_text(encoding="utf-8")
        script = (root / "listing_agent" / "code" / "app.js").read_text(encoding="utf-8")

        self.assertIn("识别补充（可选）", page)
        self.assertNotIn('id="imageFacts" required', page)
        self.assertIn("识别补充为可选项，可留空并确认继续", script)
        self.assertIn("已确认暂无可用图片事实", script)
        self.assertIn('const canConfirmEmptyResult = imageExtraction.status === "extracted"', script)
        self.assertNotIn("图片识别失败，请补充图片文字后重新提取", script)

    def test_user_skill_preferences_are_saved_to_file_and_database_record(self) -> None:
        self.login()
        response = self.client.post(
            "/listing-agent/api/user-state",
            json={
                "skills": [{"id": "skill-1", "name": "我的 Skill", "tone": "beauty factual"}],
                "preferences": {"selectedSkillId": "skill-1", "lastVariantId": "balanced"},
                "riskLibrary": [
                    {"term": "Waterproof", "level": "high"},
                    {"term": "Vegan", "level": "medium"},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        skill_path = Path(payload["skillPath"])
        self.assertEqual(skill_path.parent, self.skill_storage_dir)
        self.assertTrue(skill_path.exists())
        saved = json.loads(skill_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["userName"], "测试用户")
        self.assertEqual(saved["skills"][0]["id"], "skill-1")
        self.assertEqual(saved["preferences"]["selectedSkillId"], "skill-1")
        self.assertEqual(
            saved["riskLibrary"],
            [
                {"term": "waterproof", "level": "high"},
                {"term": "vegan", "level": "medium"},
            ],
        )
        sql = self.mock_dui_db.call_args.args[0]
        self.assertIn("dbo.Listing_ShengCheng", sql)
        params = self.mock_dui_db.call_args.kwargs["params"]
        self.assertEqual(params[0], "测试用户")
        self.assertEqual(params[3], str(skill_path))

        loaded = self.client.get("/listing-agent/api/user-state")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.get_json()["skills"][0]["name"], "我的 Skill")
        self.assertEqual(loaded.get_json()["riskLibrary"][1]["term"], "vegan")

    def test_text_generation_retries_a_fast_fallback_after_timeout(self) -> None:
        timed_out = {
            "ok": False,
            "status": 0,
            "text": "Read timed out. (read timeout=60)",
            "error": {"message": "Read timed out. (read timeout=60)"},
        }
        available = {"ok": True, "status": 200, "text": "{}"}
        with (
            patch.object(listing_module, "_get_text_model", return_value="slow/text-model"),
            patch.object(
                listing_module,
                "_call_siliconflow",
                side_effect=[timed_out, available],
            ) as call_siliconflow,
        ):
            result = listing_module._call_siliconflow_with_text_fallbacks(
                "test-key",
                {"messages": []},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(call_siliconflow.call_count, 2)
        self.assertEqual(
            call_siliconflow.call_args_list[1].args[1]["model"],
            listing_module.DEFAULT_SILICONFLOW_TEXT_MODEL,
        )
        self.assertEqual(call_siliconflow.call_args_list[0].kwargs["read_timeout"], 60)

    def test_text_model_defaults_to_dedicated_text_model(self) -> None:
        with (
            patch.object(listing_module, "ai_runtime_config", return_value={}),
            patch.object(listing_module, "env", return_value=""),
            patch.object(listing_module, "_get_model", return_value="slow/vision-model"),
        ):
            self.assertEqual(
                listing_module._get_text_model(),
                listing_module.DEFAULT_SILICONFLOW_TEXT_MODEL,
            )

    def test_listing_page_has_selectable_builtin_skills_and_user_scoped_risk_state(self) -> None:
        root = Path(__file__).resolve().parents[1]
        page = (root / "listing_agent" / "code" / "index.html").read_text(encoding="utf-8")
        script = (root / "listing_agent" / "code" / "app.js").read_text(encoding="utf-8")

        self.assertIn("可先选择 Skill 和管理违禁词库", page)
        self.assertIn('id: "builtin-ranking-first"', script)
        self.assertIn('id: "builtin-natural-premium"', script)
        self.assertIn("JSON.stringify({ skills: userSkills, preferences, riskLibrary })", script)
        self.assertIn("strategyPanel.inert = false", script)

    def test_listing_page_uses_a_single_primary_guided_workflow(self) -> None:
        root = Path(__file__).resolve().parents[1]
        page = (root / "listing_agent" / "code" / "index.html").read_text(encoding="utf-8")
        script = (root / "listing_agent" / "code" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="workflowRoot"', page)
        self.assertIn('class="workflow-sidebar"', page)
        self.assertIn('id="workflowStageBody"', page)
        self.assertIn('id="workflowPrimaryBtn"', page)
        self.assertEqual(page.count('id="workflowPrimaryBtn"'), 1)
        self.assertIn("function organizeWorkflowLayout()", script)
        self.assertIn("function setActiveWorkflowStep", script)
        self.assertIn("document.body.dataset.flowState = state", script)
        self.assertIn('confirmed: 2', script)
        self.assertIn('done: 4', script)

    def test_listing_page_exposes_current_title_and_item_highlight_limits(self) -> None:
        root = Path(__file__).resolve().parents[1]
        page = (root / "listing_agent" / "code" / "index.html").read_text(encoding="utf-8")
        script = (root / "listing_agent" / "code" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="titleScore">0/75', page)
        self.assertIn('id="itemHighlightScore">0/125', page)
        self.assertIn('titleLimit: 70', script)
        self.assertIn('itemHighlightLimit: 125', script)
        self.assertIn('Item Highlights（商品亮点，常称副标题）', script)
        self.assertIn('${escapeHtml(variant.itemHighlight)}', script)

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
        imported_payload = imported_response.get_json()
        self.assertEqual(imported_payload["summary"]["uniqueTerms"], 1)
        self.assertEqual(len(imported_payload["storedFiles"]), 1)
        stored_upload = Path(imported_payload["storedFiles"][0])
        self.assertEqual(stored_upload.parent, self.aba_storage_dir)
        self.assertTrue(stored_upload.exists())
        self.assertEqual(
            json.loads(stored_upload.read_text(encoding="utf-8"))["rows"][0]["searchTerm"],
            "custom lash keyword",
        )
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
                    "itemHighlight": f"{variant_id} item highlight",
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
        self.assertNotIn("model", payload)
        self.assertEqual(payload["storage"]["storedAs"], "database")
        self.assertEqual(Path(payload["storage"]["skillPath"]).parent, self.skill_storage_dir)
        self.assertEqual([item["id"] for item in payload["variants"]], ["balanced", "style", "search"])
        self.assertEqual(payload["variants"][0]["itemHighlight"], "Balanced item highlight")
        request_payload = mocked_call.call_args.args[1]
        self.assertFalse(request_payload["enable_thinking"])
        self.assertEqual(request_payload["max_tokens"], 4000)
        self.assertEqual(request_payload["messages"][0]["role"], "system")
        self.assertIn("July 27, 2026", request_payload["messages"][0]["content"])
        self.assertIn("Item Highlights", request_payload["messages"][0]["content"])
        self.assertIn("lash clusters", request_payload["messages"][1]["content"])
        sql = self.mock_dui_db.call_args.args[0]
        params = self.mock_dui_db.call_args.kwargs["params"]
        self.assertEqual(params[0], "测试用户")
        self.assertIn("balanced title", params[2])

    def test_generated_title_and_item_highlight_use_current_amazon_limits(self) -> None:
        variants = [
            {
                "id": variant_id,
                "title": "Title " + ("x" * 100),
                "itemHighlight": "Item highlight " + ("y" * 180),
                "highlights": ["One", "Two", "Three"],
                "bullets": ["One", "Two", "Three", "Four", "Five"],
                "description": "Description",
                "searchTerms": "lash clusters wispy",
                "reasons": ["测试理由"],
            }
            for variant_id in ("balanced", "style", "search")
        ]

        normalized = listing_module._normalize_generated_listing_variants(variants)

        self.assertEqual(len(normalized), 3)
        self.assertTrue(all(len(item["title"]) <= 70 for item in normalized))
        self.assertTrue(all(len(item["itemHighlight"]) <= 125 for item in normalized))

    def test_generated_highlights_and_bullets_start_with_uppercase_letters(self) -> None:
        variants = [
            {
                "id": variant_id,
                "title": "Lash Clusters Kit",
                "itemHighlight": "soft wispy definition",
                "highlights": ["mixed lengths", "clear band", "d curl"],
                "bullets": ["first benefit", "second spec", "third design", "fourth scene", "fifth package"],
                "description": "Description",
                "searchTerms": "lash clusters wispy",
                "reasons": ["测试理由"],
            }
            for variant_id in ("balanced", "style", "search")
        ]

        normalized = listing_module._normalize_generated_listing_variants(variants)

        self.assertEqual(normalized[0]["itemHighlight"], "Soft wispy definition")
        self.assertEqual(normalized[0]["highlights"], ["Mixed lengths", "Clear band", "D curl"])
        self.assertEqual(normalized[0]["bullets"][0], "First benefit")

    def test_keyword_priorities_are_sorted_by_aba_signals(self) -> None:
        payload = listing_module._normalize_listing_generation_input(
            {
                "product": {"type": "lash clusters"},
                "keywords": {
                    "rankingPriority": [
                        {"term": "lower priority", "rank": 900},
                        {"term": "highest priority", "rank": 12},
                        {"term": "unknown rank"},
                    ],
                    "growthPriority": [
                        {"term": "slow growth", "growth": 20},
                        {"term": "fast growth", "growth": 500},
                    ],
                    "conversionPriority": [
                        {"term": "low conversion", "conversionShare": 0.1},
                        {"term": "high conversion", "conversionShare": 0.4},
                    ],
                },
            }
        )

        self.assertEqual(
            [item["term"] for item in payload["keywords"]["rankingPriority"]],
            ["highest priority", "lower priority", "unknown rank"],
        )
        self.assertEqual(payload["keywords"]["growthPriority"][0]["term"], "fast growth")
        self.assertEqual(payload["keywords"]["conversionPriority"][0]["term"], "high conversion")

    def test_long_listing_is_archived_to_configured_listing_folder(self) -> None:
        self.login()
        variants = [
            {
                "id": variant_id,
                "title": f"{variant_id} title",
                "highlights": ["One", "Two", "Three"],
                "bullets": ["One", "Two", "Three", "Four", "Five"],
                "description": "Long description " * 20,
                "searchTerms": "lash clusters wispy",
                "reasons": ["测试理由"],
            }
            for variant_id in ("balanced", "style", "search")
        ]
        completion = {"choices": [{"message": {"content": json.dumps({"variants": variants}, ensure_ascii=False)}}]}
        fake_result = {
            "ok": True,
            "status": 200,
            "text": json.dumps(completion, ensure_ascii=False),
            "model": listing_module.DEFAULT_SILICONFLOW_MODEL,
        }

        with (
            patch.object(listing_module, "_call_siliconflow", return_value=fake_result),
            patch.object(listing_module, "LISTING_DATABASE_TEXT_LIMIT", 10),
        ):
            response = self.client.post(
                "/listing-agent/api/generate-listings",
                json={
                    "marketplace": "US",
                    "product": {"type": "lash clusters", "brand": "ALICE"},
                    "keywords": {},
                    "compliance": {},
                    "skill": {"id": "skill-long", "name": "长文案 Skill"},
                    "limits": {},
                },
            )

        self.assertEqual(response.status_code, 200)
        storage = response.get_json()["storage"]
        self.assertEqual(storage["storedAs"], "file")
        listing_path = Path(storage["listingPath"])
        self.assertEqual(listing_path.parent, self.listing_storage_dir)
        self.assertTrue(listing_path.exists())
        archived = json.loads(listing_path.read_text(encoding="utf-8"))
        self.assertEqual(archived["userName"], "测试用户")
        self.assertEqual(len(archived["variants"]), 3)
        self.assertEqual(
            self.mock_dui_db.call_args.kwargs["params"][2],
            str(listing_path),
        )

    def test_generated_variants_are_returned_when_persistence_fails(self) -> None:
        self.login()
        variants = [
            {
                "id": variant_id,
                "title": f"{variant_id} title",
                "highlights": ["One", "Two", "Three"],
                "bullets": ["One", "Two", "Three", "Four", "Five"],
                "description": "Description",
                "searchTerms": "lash clusters wispy",
                "reasons": ["测试理由"],
            }
            for variant_id in ("balanced", "style", "search")
        ]
        completion = {
            "choices": [{"message": {"content": json.dumps({"variants": variants}, ensure_ascii=False)}}]
        }
        fake_result = {
            "ok": True,
            "status": 200,
            "text": json.dumps(completion, ensure_ascii=False),
            "model": listing_module.DEFAULT_SILICONFLOW_MODEL,
        }

        with (
            patch.object(listing_module, "_call_siliconflow", return_value=fake_result),
            patch.object(
                listing_module,
                "_persist_generated_listing",
                side_effect=RuntimeError("database temporarily unavailable"),
            ),
        ):
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
        self.assertEqual(len(payload["variants"]), 3)
        self.assertTrue(payload["storage"]["persistenceFailed"])
        self.assertEqual(payload["storage"]["storedAs"], "unsaved")

    def test_listing_with_percentages_is_passed_as_a_database_parameter(self) -> None:
        listing_value = json.dumps(
            {"ranking": "点击 18% / 转化 8.8%", "title": "Kid's Lashes"},
            ensure_ascii=False,
        )
        saved_at = listing_module._now_shanghai()

        listing_module._upsert_listing_record(
            user_name="百分号测试用户",
            saved_at=saved_at,
            skill_path=self.skill_storage_dir / "percent-skill.json",
            listing_value=listing_value,
        )

        sql = self.mock_dui_db.call_args.args[0]
        params = self.mock_dui_db.call_args.kwargs["params"]
        self.assertNotIn("18%", sql)
        self.assertNotIn("Kid's Lashes", sql)
        self.assertEqual(params[2], listing_value)
        self.assertEqual(params[4], 1)


if __name__ == "__main__":
    unittest.main()
