import contextlib
import inspect
import unittest
from unittest.mock import patch

from 图片 import openrouter_image_site as site


class UploadPreviewDeleteTests(unittest.TestCase):
    def test_delete_button_css_overlays_current_streamlit_element_container(self) -> None:
        source = inspect.getsource(site.inject_app_styles)

        self.assertIn('[data-testid="stElementContainer"]', source)
        self.assertIn("position: absolute !important", source)
        self.assertIn("top: 6px !important", source)
        self.assertIn("right: 6px !important", source)
        self.assertIn("button:hover", source)

    def test_default_preview_uses_streamlit_delete_button(self) -> None:
        with patch.object(site.st, "container", return_value=contextlib.nullcontext()), patch.object(
            site.st, "markdown"
        ), patch.object(site.st, "file_uploader", return_value=None), patch.object(
            site, "render_upload_delete_button"
        ) as render_delete, patch.object(
            site, "uploaded_input_to_data_url", return_value="data:image/png;base64,AAAA"
        ), patch.object(site, "render_zoomable_image_gallery") as render_gallery:
            site.render_uploaded_preview_card(
                {"data": b"image", "name": "source.png", "type": "image/png"},
                widget_key="uploader_remove_eyelashes",
                item_index=0,
                component_key="upload_preview_uploader_remove_eyelashes_0",
            )

        render_delete.assert_called_once_with(
            "uploader_remove_eyelashes",
            0,
            button_key="delete_upload_upload_preview_uploader_remove_eyelashes_0_0",
        )
        self.assertNotIn("context_delete_token", render_gallery.call_args.kwargs)

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
