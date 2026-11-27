import contextlib
import inspect
import unittest
from unittest.mock import patch

from Department.视觉设计部.xiaoha import openrouter_image_site as site


class UploadPreviewDeleteTests(unittest.TestCase):
    def test_delete_button_css_overlays_current_streamlit_element_container(self) -> None:
        source = inspect.getsource(site._workbench_assets.inject_app_styles)

        self.assertIn('[data-testid="stElementContainer"]', source)
        self.assertIn("position: absolute !important", source)
        self.assertIn("top: 6px !important", source)
        self.assertIn("right: 6px !important", source)
        self.assertIn("button:hover", source)

    def test_default_preview_uses_streamlit_delete_button(self) -> None:
        with patch.object(site.st, "columns", return_value=[contextlib.nullcontext()]), patch.object(
            site, "render_frame_uploader", return_value=None
        ) as frame, patch.object(site.st, "button", return_value=True) as button, patch.object(
            site, "remove_upload_cache_item"
        ) as remove_item, patch.object(site, "reset_upload_widget") as reset, patch.object(site.st, "rerun") as rerun:
            site.render_uploaded_preview_card(
                {"data": b"image", "name": "source.png", "type": "image/png"},
                widget_key="uploader_remove_eyelashes",
                item_index=0,
                component_key="upload_preview_uploader_remove_eyelashes_0",
            )

        button_key = "delete_upload_upload_preview_uploader_remove_eyelashes_0_0"
        self.assertEqual(frame.call_args.kwargs["remove_button_key"], button_key)
        self.assertEqual(button.call_args.kwargs["key"], button_key)
        remove_item.assert_called_once_with("uploader_remove_eyelashes", 0)
        reset.assert_called_once_with("uploader_remove_eyelashes")
        rerun.assert_called_once_with()

    def test_delete_button_removes_cache_and_refreshes(self) -> None:
        with patch.object(site.st, "markdown"), patch.object(
            site.st, "button", return_value=True
        ), patch.object(site, "remove_upload_cache_item") as remove_item, patch.object(
            site, "reset_upload_widget"
        ) as reset_widget, patch.object(site.st, "rerun") as rerun:
            site.render_upload_delete_button("uploader_remove_eyelashes", 0, "delete_button")

        remove_item.assert_called_once_with("uploader_remove_eyelashes", 0)
        reset_widget.assert_called_once_with("uploader_remove_eyelashes")
        rerun.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
