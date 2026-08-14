from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from xiaotu_report_memory import (
    ReportMemoryError,
    build_report_memory_path,
    render_report_memory_context,
    sanitize_report_memory_filename,
    update_report_memory_file,
)
from backfill_xiaotu_report_memory_local import build_local_snapshot


class XiaotuReportMemoryTests(unittest.TestCase):
    def test_filename_uses_feishu_user_name_and_removes_windows_invalid_chars(self) -> None:
        self.assertEqual(sanitize_report_memory_filename(" 张三 "), "张三")
        self.assertEqual(sanitize_report_memory_filename('张/三:*?"<>|'), "张_三_______")

    def test_update_writes_utf8_json_to_user_named_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            calls = []

            def fake_ai_generate(**kwargs):
                calls.append(kwargs)
                return """```json
                {
                  "overview": "持续推进项目A",
                  "current_focus": [{"thread_id": "project-a", "title": "项目A"}],
                  "key_insights": [{"date": "2026-07-28", "text": "先验证再扩大"}],
                  "open_followups": [{"id": "f1", "item": "确认数据", "status": "open"}],
                  "recent_timeline": [{
                    "date": "2026-07-28",
                    "report_id": "report-1",
                    "important_events": ["完成首轮验证"],
                    "changes": ["进入数据确认阶段"]
                  }],
                  "archives": []
                }
                ```"""

            file_path, snapshot = update_report_memory_file(
                storage_root=temp_dir,
                user_name="张三",
                user_open_id="ou_123",
                report_id="report-1",
                report_date="2026-07-28",
                report_material="完成项目A首轮验证。",
                is_edit=False,
                ai_generate=fake_ai_generate,
            )

            expected_path = Path(temp_dir) / "日报整合" / "张三.json"
            self.assertEqual(Path(file_path), expected_path.resolve())
            self.assertTrue(expected_path.is_file())
            saved = json.loads(expected_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["user_name"], "张三")
            self.assertEqual(saved["user_open_id"], "ou_123")
            self.assertEqual(saved["last_report_id"], "report-1")
            self.assertEqual(saved["updated_through"], "2026-07-28")
            self.assertEqual(saved["snapshot_version"], 1)
            self.assertEqual(snapshot, saved)
            self.assertIn("旧的长期记忆JSON", calls[0]["doc_text"])
            self.assertIn("完成项目A首轮验证", calls[0]["doc_text"])

    def test_edit_keeps_only_latest_timeline_entry_for_same_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            def fake_ai_generate(**_kwargs):
                return json.dumps(
                    {
                        "overview": "项目A已修订",
                        "current_focus": [],
                        "key_insights": [],
                        "open_followups": [],
                        "recent_timeline": [
                            {
                                "date": "2026-07-27",
                                "report_id": "report-1",
                                "important_events": ["旧内容"],
                            },
                            {
                                "date": "2026-07-28",
                                "report_id": "report-1",
                                "important_events": ["修订内容"],
                            },
                        ],
                        "archives": [],
                    },
                    ensure_ascii=False,
                )

            _, snapshot = update_report_memory_file(
                storage_root=temp_dir,
                user_name="张三",
                user_open_id="ou_123",
                report_id="report-1",
                report_date="2026-07-28",
                report_material="修订后的日报。",
                is_edit=True,
                ai_generate=fake_ai_generate,
            )

            entries = [
                item
                for item in snapshot["recent_timeline"]
                if item.get("report_id") == "report-1"
            ]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["important_events"], ["修订内容"])
            self.assertEqual(entries[0]["date"], "2026-07-28")

    def test_invalid_ai_json_does_not_overwrite_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(build_report_memory_path(temp_dir, "张三"))
            file_path.parent.mkdir(parents=True, exist_ok=True)
            original = {"overview": "原有长期记忆", "snapshot_version": 7}
            original_text = json.dumps(original, ensure_ascii=False, indent=2)
            file_path.write_text(original_text, encoding="utf-8")

            with self.assertRaises(ReportMemoryError):
                update_report_memory_file(
                    storage_root=temp_dir,
                    user_name="张三",
                    user_open_id="ou_123",
                    report_id="report-2",
                    report_date="2026-07-28",
                    report_material="当前日报",
                    is_edit=False,
                    ai_generate=lambda **_kwargs: "这不是JSON",
                )

            self.assertEqual(file_path.read_text(encoding="utf-8"), original_text)

    def test_missing_ai_sections_preserve_previous_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(build_report_memory_path(temp_dir, "王五"))
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(
                json.dumps(
                    {
                        "snapshot_version": 3,
                        "overview": "原概览",
                        "current_focus": [{"thread_id": "keep-me"}],
                        "key_insights": [{"text": "保留心得"}],
                        "open_followups": [{"id": "keep-followup"}],
                        "recent_timeline": [],
                        "archives": [{"period": "2026-06", "summary": "历史归档"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            _, snapshot = update_report_memory_file(
                storage_root=temp_dir,
                user_name="王五",
                user_open_id="ou_456",
                report_id="report-3",
                report_date="2026-07-28",
                report_material="当前日报",
                is_edit=False,
                ai_generate=lambda **_kwargs: '{"overview":"新概览"}',
            )

            self.assertEqual(snapshot["overview"], "新概览")
            self.assertEqual(snapshot["current_focus"], [{"thread_id": "keep-me"}])
            self.assertEqual(snapshot["key_insights"], [{"text": "保留心得"}])
            self.assertEqual(snapshot["open_followups"], [{"id": "keep-followup"}])
            self.assertEqual(snapshot["archives"][0]["period"], "2026-06")
            self.assertEqual(snapshot["snapshot_version"], 4)

    def test_render_context_reads_saved_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(build_report_memory_path(temp_dir, "李四"))
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(
                json.dumps(
                    {
                        "overview": "负责项目B",
                        "current_focus": [{"title": "项目B"}],
                        "recent_timeline": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            context = render_report_memory_context(temp_dir, "李四")

            self.assertIn("负责项目B", context)
            self.assertIn("项目B", context)

    def test_report_submit_starts_independent_memory_worker(self) -> None:
        app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        self.assertIn("def _xiaotu_report_memory_background_worker(payload):", app_source)
        self.assertIn("_xiaotu_update_report_memory(", app_source)
        self.assertIn("dbo.baogao_zhenghe", app_source)
        self.assertIn('"report_date_text": report_date_text', app_source)

    def test_local_backfill_extracts_history_without_ai(self) -> None:
        snapshot = build_local_snapshot(
            "赵六",
            [
                {
                    "report_id": "r1",
                    "report_date": "2026-07-27",
                    "title": "赵六日报",
                    "body": "完成商品页面第一轮优化。复盘发现素材命名不统一会增加查找时间。明日继续验证新版页面。",
                    "image_ocr": "",
                },
                {
                    "report_id": "r2",
                    "report_date": "2026-07-28",
                    "title": "赵六日报",
                    "body": "新版页面数据提升10%。后续需要跟进转化率变化。",
                    "image_ocr": "",
                },
            ],
        )

        self.assertEqual(snapshot["history_report_count"], 2)
        self.assertEqual(snapshot["history_backfill_method"], "local_extractive_v1")
        self.assertEqual(snapshot["last_report_id"], "r2")
        self.assertTrue(snapshot["current_focus"])
        self.assertTrue(snapshot["key_insights"])
        self.assertTrue(snapshot["open_followups"])
        self.assertEqual(len(snapshot["recent_timeline"]), 2)


if __name__ == "__main__":
    unittest.main()
