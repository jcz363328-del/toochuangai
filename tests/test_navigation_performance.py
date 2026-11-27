import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from Department.视觉设计部.xiaoha import upload_frames, job_presentation


class NavigationPerformanceTests(unittest.TestCase):
    def test_upload_assets_are_cached_and_original_is_byte_exact(self):
        with TemporaryDirectory() as directory:
            buf = io.BytesIO()
            Image.new("RGB", (1600, 1200), "red").save(buf, format="JPEG")
            raw = buf.getvalue()
            api = SimpleNamespace(
                st=SimpleNamespace(session_state={}),
                normalize_uploaded_input=lambda item: item,
                get_jimeng_public_upload_base_url=lambda: "https://assets.test/uploads",
                ensure_jimeng_upload_dir=lambda: Path(directory),
            )
            item = {"data": raw, "type": "image/jpeg", "name": "original.jpg"}
            preview, original, name = upload_frames._frame_sources(api, item)
            self.assertTrue(preview.startswith("https://assets.test/uploads/"))
            self.assertTrue(original.endswith(".jpg"))
            self.assertEqual((Path(directory) / "frame_previews" / original.rsplit("/", 1)[1]).read_bytes(), raw)
            with Image.open(Path(directory) / "frame_previews" / preview.rsplit("/", 1)[1]) as image:
                self.assertEqual(image.size, (900, 675))
            with patch.object(upload_frames.Image, "open", side_effect=AssertionError("decoded again")):
                self.assertEqual(upload_frames._frame_sources(api, item), (preview, original, name))
                renamed = dict(item, name="renamed.jpg")
                self.assertEqual(upload_frames._frame_sources(api, renamed)[2], "renamed.jpg")
            changed = dict(item, data=raw + b"changed")
            self.assertNotEqual(upload_frames._frame_sources(api, changed)[1], original)

    def test_old_page_poller_never_reruns_new_page(self):
        st = SimpleNamespace(session_state={"selected_feature_key": "new-page"}, rerun=Mock())
        sync = Mock()
        job_presentation.render_running_job_status(
            "old-page", True, build_running_job_spinner_html=Mock(), st=st,
            sync_background_jobs=sync)
        sync.assert_not_called()
        st.rerun.assert_not_called()

    def test_current_page_completion_still_refreshes_results(self):
        st = SimpleNamespace(session_state={"selected_feature_key": "page", "background_jobs": {}}, rerun=Mock())
        sync = Mock()
        job_presentation.render_running_job_status(
            "page", True, build_running_job_spinner_html=Mock(), st=st,
            sync_background_jobs=sync)
        sync.assert_called_once()
        st.rerun.assert_called_once()


if __name__ == "__main__":
    unittest.main()
