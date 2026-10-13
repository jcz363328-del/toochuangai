import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module


class XiaotuReportDateExportTests(unittest.TestCase):
    def test_export_context_validates_date_range(self):
        with patch.object(app_module, "_current_user_has_permission", return_value=False), patch.object(
            app_module, "_xiaotu_get_report_history_scope", return_value={}
        ):
            with self.assertRaisesRegex(ValueError, "结束日期"):
                app_module._xiaotu_build_report_history_export_context(
                    {"date_start": "2026-09-08", "date_end": "2026-09-01"}, "测试用户"
                )

    def test_export_keeps_safe_rich_text_style_and_image_layout(self):
        body = '<p style="color:red;text-align:center;position:fixed">标题</p><img src="saved.png" style="width:240px;height:auto" class="report-image">'
        with patch.object(app_module, "_xiaotu_normalize_report_html_body", return_value=body), patch.object(
            app_module, "_xiaotu_history_export_image_data_uri", return_value="data:image/png;base64,AAAA"
        ):
            html, embedded, missing = app_module._xiaotu_history_export_body_html(body, "saved.png")
        self.assertIn('style="color: red; text-align: center"', html)
        self.assertNotIn("position", html)
        self.assertIn('style="width: 240px; height: auto"', html)
        self.assertIn('class="report-image"', html)
        self.assertEqual((1, 0), (embedded, missing))

    def test_desktop_and_mobile_have_date_export_entry(self):
        desktop = Path("templates/xiaotu_report_center.html").read_text(encoding="utf-8-sig")
        mobile = Path("templates/xiaotu_report_center_mobile.html").read_text(encoding="utf-8-sig")
        self.assertIn("quickExportReportsBtn", desktop)
        self.assertIn("mobileExportReportsBtn", mobile)
        self.assertIn("report_history_download", desktop)
        self.assertIn("report_history_download", mobile)

    def test_history_page_has_obvious_date_export_button(self):
        history = Path("templates/xiaotu_report_history.html").read_text(encoding="utf-8-sig")
        self.assertIn("按日期导出日报", history)
        self.assertIn("原格式和上传图片会一并保留", history)


if __name__ == "__main__":
    unittest.main()
