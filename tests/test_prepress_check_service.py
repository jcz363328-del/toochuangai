import os
import tempfile
import unittest
import zipfile
import zlib

import prepress_check_service as service


class PrepressCheckServiceTests(unittest.TestCase):
    def tearDown(self):
        service.reset_session("chat-stage")

    def test_trigger_and_extensions(self):
        self.assertTrue(service.is_trigger("请检查印前合规"))
        self.assertTrue(service.accepts_filename("design.AI"))
        self.assertTrue(service.accepts_filename("package.zip"))
        self.assertFalse(service.accepts_filename("notes.docx"))

    def test_stage_and_reset(self):
        service.activate_session("chat-stage")
        self.assertTrue(service.has_active_session("chat-stage"))
        result = service.stage_file("chat-stage", b"pdf", "SKU-1_10x20mm_烫银.pdf")
        self.assertEqual(result["count"], 1)
        self.assertTrue(service.has_active_session("chat-stage"))
        service.reset_session("chat-stage")
        self.assertFalse(service.has_active_session("chat-stage"))

    def test_safe_zip_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            archive_path = os.path.join(root, "unsafe.zip")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.pdf", b"pdf")
            with self.assertRaisesRegex(ValueError, "不安全路径"):
                service._safe_extract_zip(archive_path, os.path.join(root, "out"))

    def test_safe_zip_filters_unrelated_files(self):
        with tempfile.TemporaryDirectory() as root:
            archive_path = os.path.join(root, "safe.zip")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("job/design.pdf", b"pdf")
                archive.writestr("job/readme.exe", b"bad")
            output = os.path.join(root, "out")
            os.makedirs(output)
            files = service._safe_extract_zip(archive_path, output)
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].endswith("design.pdf"))

    def test_end_to_end_pdf_report(self):
        import pymupdf as fitz

        doc = fitz.open()
        page = doc.new_page(width=100 * 72 / 25.4, height=150 * 72 / 25.4)
        page.draw_rect(page.rect, color=(0, 0, 0))
        pdf_bytes = doc.tobytes()
        doc.close()
        service.stage_file("chat-stage", pdf_bytes, "SKU01_100x150mm_烫银.pdf")
        result = service.run_check("chat-stage")
        self.assertIn("# 印前检查报告", result["report"])
        self.assertIn("19 | 页面尺寸与截图备注", result["report"])
        self.assertEqual(result["scan_count"], 1)

    def test_embedding_check_does_not_false_pass_ai_preview(self):
        status, evidence = service._embedding_check([
            {
                "path": "design.ai",
                "name": "design.ai",
                "pages": [{"images": [{"dpi": 300}]}],
            }
        ])
        self.assertIn("人工确认", status)
        self.assertIn("链接", evidence)
        self.assertNotIn("✅", status)

    def test_embedding_check_accepts_pdf_image_xobjects(self):
        status, evidence = service._embedding_check([
            {
                "path": "design.pdf",
                "name": "design.pdf",
                "pages": [{"images": [{"dpi": 300}, {"dpi": 600}]}],
            }
        ])
        self.assertIn("✅", status)
        self.assertIn("2 个", evidence)

    def test_ai_native_scan_reports_linked_files(self):
        from compression import zstd

        native = (
            "%AI5_BeginRaster\n%%BeginData: 4\nXI\n%AI5_EndRaster\n"
            "%AI5_BeginPlace\n%%FileType: 1\n%%IncludeFile:Z:\\物料\\蝴蝶.psd\n~\n%AI5_EndPlace\n"
        ).encode("gbk")
        blob = service.AI_ZSTD_HEADER + zstd.compress(native)
        links = service._scan_ai_native_lines(service._iter_ai_native_chunks(blob))
        self.assertEqual(links["linked"], ["Z:\\物料\\蝴蝶.psd"])
        self.assertEqual(links["raster_count"], 1)
        status, evidence = service._embedding_check([
            {"path": "design.ai", "name": "design.ai", "pages": [], "ai_links": {**links, "readable": True}}
        ])
        self.assertIn("❌", status)
        self.assertIn("蝴蝶.psd", evidence)

    def test_ai_native_scan_passes_embedded_only(self):
        native = b"%AI5_BeginRaster\n%%BeginData: 4\nXI\n%AI5_EndRaster\n"
        blob = service.AI_ZLIB_HEADER + zlib.compress(native)
        links = service._scan_ai_native_lines(service._iter_ai_native_chunks(blob))
        status, evidence = service._embedding_check([
            {"path": "design.ai", "name": "design.ai", "pages": [], "ai_links": {**links, "readable": True}}
        ])
        self.assertIn("✅", status)
        self.assertIn("已嵌入图像 1 个", evidence)


if __name__ == "__main__":
    unittest.main()
