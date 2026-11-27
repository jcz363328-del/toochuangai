import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote, unquote

from Department.视觉设计部.xiaoha.image_downloads import build_image_attachment_header, resolve_local_static_image_source


class ImageDownloadHeaderTests(unittest.TestCase):
    def header(self, target, **kwargs):
        return build_image_attachment_header(
            target,
            status_code=kwargs.get("status_code", 200),
            content_type=kwargs.get("content_type", "image/png"),
            method=kwargs.get("method", "GET"),
        )

    def test_chinese_requested_name_survives_as_utf8(self):
        result = self.header("/history_images/record/image.png?download=1&filename=" + quote("问答生图 原图.png"))
        self.assertEqual(unquote(result.split("filename*=UTF-8''", 1)[1]), "问答生图 原图.png")
        self.assertIn('filename="image.png"', result)

    def test_missing_or_empty_name_defaults_to_original_basename(self):
        for suffix in ("", "&filename=", "&filename=..."):
            with self.subTest(suffix=suffix):
                result = self.header("/jimeng_uploads/history_downloads/original.png?download=1" + suffix)
                self.assertIn('filename="original.png"', result)
                self.assertTrue(result.endswith("original.png"))

    def test_filename_cannot_inject_headers_or_use_directories(self):
        requested = "C:\\private\\nested/原图\r\nX-Evil: yes.png"
        result = self.header("/history_images/original.png?download=1&filename=" + quote(requested))
        self.assertNotIn("\r", result)
        self.assertNotIn("\n", result)
        self.assertNotIn("private", result)
        self.assertEqual(unquote(result.split("filename*=UTF-8''", 1)[1]), "原图X-Evil_ yes.png")

    def test_header_quoted_name_cannot_be_escaped(self):
        result = self.header("/history_images/original.png?download=1&filename=" + quote('a"; filename="evil.png'))
        self.assertEqual(result.count('filename="'), 1)
        self.assertNotIn('filename="evil.png', result)

    def test_failed_or_nonimage_responses_never_download_error_documents(self):
        for status in (301, 304, 400, 403, 404, 429, 500):
            with self.subTest(status=status):
                self.assertIsNone(self.header("/history_images/missing.png?download=1", status_code=status))
        for content_type in ("text/html", "application/json", "application/octet-stream", ""):
            with self.subTest(content_type=content_type):
                self.assertIsNone(self.header("/history_images/original.png?download=1", content_type=content_type))

    def test_only_explicit_static_image_gets_are_attachments(self):
        for target in (
            "/infinite-canvas/api/omnia-asset?download=1",
            "/history_images_extra/original.png?download=1",
            "/history_images/original.png",
            "/history_images/original.png?download=0",
        ):
            with self.subTest(target=target):
                self.assertIsNone(self.header(target))
        self.assertIsNone(self.header("/history_images/original.png?download=1", method="HEAD"))
        self.assertIsNotNone(self.header("/history_images/original.png?download=1", status_code=206))

    def test_long_name_preserves_extension(self):
        result = self.header("/history_images/original.png?download=1&filename=" + quote("原" * 250 + ".png"))
        filename = unquote(result.split("filename*=UTF-8''", 1)[1])
        self.assertLessEqual(len(filename), 180)
        self.assertTrue(filename.endswith(".png"))


class LocalStaticImageSourceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.history = self.root / "history"
        self.uploads = self.root / "uploads"
        self.history.mkdir()
        self.uploads.mkdir()

    def resolve(self, source):
        return resolve_local_static_image_source(
            source,
            history_directory=self.history,
            upload_directory=self.uploads,
            public_base_urls=["http://configured.example:8000/history_images", "https://uploads.example/jimeng_uploads"],
        )

    def test_firstparty_urls_preserve_nested_unicode_names_and_ignore_query(self):
        path = self.history / "account" / "历史 原图.png"
        path.parent.mkdir()
        path.write_bytes(b"original")
        result = self.resolve("https://configured.example/history_images/account/" + quote(path.name) + "?download=1&v=123")
        self.assertEqual(result, path.resolve())
        self.assertEqual(result.read_bytes(), b"original")

    def test_upload_and_history_routes_keep_distinct_roots(self):
        (self.history / "same.png").write_bytes(b"history")
        upload = self.uploads / "same.png"
        upload.write_bytes(b"upload")
        self.assertEqual(self.resolve("/jimeng_uploads/same.png"), upload.resolve())
        self.assertEqual(self.resolve("https://uploads.example/jimeng_uploads/same.png").read_bytes(), b"upload")

    def test_external_host_cannot_resolve_to_an_unrelated_local_image(self):
        (self.history / "original.png").write_bytes(b"original")
        for source in (
            "https://external.example/history_images/original.png",
            "https://configured.example.evil/history_images/original.png",
            "file:///history_images/original.png",
            "https:///history_images/original.png",
        ):
            with self.subTest(source=source):
                self.assertIsNone(self.resolve(source))

    def test_traversal_encoded_separators_and_wrong_routes_are_rejected(self):
        (self.root / "outside.png").write_bytes(b"outside")
        for source in (
            "/history_images/../outside.png",
            "/history_images/%2e%2e/outside.png",
            "/history_images/%2Foutside.png",
            "/history_images/%5c..%5coutside.png",
            "/history_images/original%00.png",
            "/history_images_extra/outside.png",
            "/infinite-canvas/outside.png",
        ):
            with self.subTest(source=source):
                self.assertIsNone(self.resolve(source))

    def test_missing_files_and_directories_are_not_resolved(self):
        (self.history / "directory.png").mkdir()
        self.assertIsNone(self.resolve("/history_images/missing.png"))
        self.assertIsNone(self.resolve("/history_images/directory.png"))

    def test_symlink_cannot_escape_storage_root(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "image.png").write_bytes(b"outside")
        link = self.history / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            if os.name != "nt":
                self.skipTest("Creating symlinks is unavailable on this host")
            # Directory junctions exercise the same containment check without
            # requiring Windows Developer Mode or symlink privileges.
            subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
                check=True,
                capture_output=True,
            )
        self.assertEqual((link / "image.png").read_bytes(), b"outside")
        self.assertIsNone(self.resolve("/history_images/linked/image.png"))


if __name__ == "__main__":
    unittest.main()
