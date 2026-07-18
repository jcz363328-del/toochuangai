import unittest
from unittest.mock import patch

from 图片 import openrouter_image_site as site


class ResultDownloadConsistencyTests(unittest.TestCase):
    def test_result_download_prefers_the_persisted_history_original(self) -> None:
        records = [
            {
                "images": ["history-thumbnail"],
                "original_images": [r"D:\history\saved-original.png"],
            }
        ]

        with patch.object(
            site,
            "build_history_download_public_url",
            side_effect=lambda source: f"history-public://{source}",
        ) as build_public_url:
            sources = site.build_result_download_sources(["temporary-result"], records)

        self.assertEqual(sources, [r"history-public://D:\history\saved-original.png"])
        build_public_url.assert_called_once_with(r"D:\history\saved-original.png")

    def test_result_preview_uses_history_download_source_as_full_image(self) -> None:
        with patch.object(site, "render_zoomable_image_gallery") as render_gallery:
            site.render_result_preview(
                ["temporary-preview"],
                show_title=False,
                download_images=["history-public-original"],
            )

        kwargs = render_gallery.call_args.kwargs
        self.assertEqual(kwargs["full_images"], ["history-public-original"])
        self.assertTrue(kwargs["include_full_src"])
        self.assertFalse(kwargs["embed_full_src"])

    def test_compare_download_uses_the_same_history_original_name(self) -> None:
        with patch.object(
            site,
            "build_gallery_item",
            side_effect=lambda source, **_kwargs: {"src": source, "full_src": source},
        ), patch.object(
            site,
            "build_history_download_public_url",
            side_effect=lambda source: source,
        ), patch.object(site.components, "html") as render_html:
            site.render_before_after_compare_gallery(
                ["source-image"],
                ["temporary-result"],
                ["效果图"],
                "outpaint",
                download_images=["http://example.com/history/20260718_001.webp"],
            )

        rendered_html = render_html.call_args.args[0]
        self.assertIn('"view": "http://example.com/history/20260718_001.webp"', rendered_html)
        self.assertIn('"download_name": "20260718_001.webp"', rendered_html)


if __name__ == "__main__":
    unittest.main()
