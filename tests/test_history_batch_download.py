from __future__ import annotations

import base64
import io
import unittest
import zipfile
from unittest.mock import patch

from PIL import Image

from 图片 import openrouter_image_site as site


def make_data_url(color: tuple[int, int, int], image_format: str = "PNG") -> tuple[str, bytes]:
    output = io.BytesIO()
    Image.new("RGB", (12, 8), color).save(output, format=image_format)
    image_bytes = output.getvalue()
    mime_type = "image/jpeg" if image_format == "JPEG" else "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}", image_bytes


class HistoryBatchDownloadTests(unittest.TestCase):
    def test_flattened_history_items_have_unique_stable_selection_ids(self) -> None:
        records = [
            {
                "images": ["https://example.com/result.png", "https://example.com/result.png"],
                "original_images": ["https://example.com/original.png"] * 2,
                "created_at": "2026-07-24 12:00:00",
                "model": "test-model",
                "feature_name": "test-feature",
            }
        ]

        first_items = site.flatten_history_items(records)
        second_items = site.flatten_history_items(records)

        self.assertEqual(len(first_items), 2)
        self.assertEqual(
            [item["selection_id"] for item in first_items],
            [item["selection_id"] for item in second_items],
        )
        self.assertEqual(len({item["selection_id"] for item in first_items}), 2)
        first_names = [item["download_name"] for item in first_items]
        second_names = [item["download_name"] for item in second_items]
        self.assertEqual(first_names, second_names)
        self.assertEqual(len(set(first_names)), 2)
        self.assertRegex(
            first_names[0],
            r"^test-feature_20260724_120000_01_[0-9a-f]{8}\.png$",
        )
        self.assertRegex(
            first_names[1],
            r"^test-feature_20260724_120000_02_[0-9a-f]{8}\.png$",
        )

    def test_batch_archive_contains_each_selected_original_image(self) -> None:
        first_url, first_bytes = make_data_url((255, 0, 0))
        second_url, second_bytes = make_data_url((0, 0, 255), image_format="JPEG")
        items = [
            {
                "download_source": first_url,
                "download_name": "result.png",
            },
            {
                "download_source": second_url,
                "download_name": "result.png",
            },
        ]

        archive_bytes = site.build_history_download_archive_bytes(items)

        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            names = archive.namelist()
            self.assertEqual(names, ["result.png", "result_2.png"])
            self.assertEqual(archive.read(names[0]), first_bytes)
            self.assertEqual(archive.read(names[1]), second_bytes)

    def test_batch_archive_requires_a_selection(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "至少选择 1 张"):
            site.build_history_download_archive_bytes([])

    def test_history_selection_key_is_scoped_to_gallery(self) -> None:
        item = {"selection_id": "a" * 40}

        main_key = site.get_history_item_selection_key("history_feature", item, 0)
        side_key = site.get_history_item_selection_key("side_history_feature", item, 0)

        self.assertNotEqual(main_key, side_key)
        self.assertTrue(main_key.startswith("history_feature_select_"))

    def test_gallery_uses_configured_unique_download_name(self) -> None:
        image_url, _image_bytes = make_data_url((20, 40, 60))
        download_name = "主图生成A+_20260725_091530_01_a1b2c3d4.png"

        with patch.object(site.st, "iframe") as render_html:
            site.render_zoomable_image_gallery(
                [image_url],
                columns=1,
                thumb_height=120,
                component_key="history_unique_name_test",
                compress_preview=False,
                include_full_src=True,
                download_names=[download_name],
            )

        rendered_html = render_html.call_args.args[0]
        self.assertIn(f'"download_name": "{download_name}"', rendered_html)
        self.assertIn("if (configuredName) return configuredName;", rendered_html)


if __name__ == "__main__":
    unittest.main()
