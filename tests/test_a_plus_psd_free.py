from __future__ import annotations

import io
import inspect
import unittest

from PIL import Image, ImageDraw

from 图片 import openrouter_image_site as site


class FreeAPlusPsdTests(unittest.TestCase):
    @staticmethod
    def build_green_screen_data_url() -> str:
        image = Image.new("RGB", (240, 320), (0, 255, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((18, 20, 104, 112), fill=(220, 42, 82))
        draw.rectangle((128, 168, 218, 292), fill=(34, 54, 94))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return site.image_bytes_to_data_url(output.getvalue(), "image/png")

    def test_free_psd_entry_is_visible_directly_after_main_a_plus(self) -> None:
        visible = site.get_visible_features()
        visible_keys = [str(feature["key"]) for feature in visible]

        main_index = visible_keys.index(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        self.assertEqual(visible_keys[main_index + 1], site.AMAZON_A_PLUS_FEATURE_KEY)
        feature = site.get_feature_by_key(site.AMAZON_A_PLUS_FEATURE_KEY)
        assert feature is not None
        self.assertEqual(feature["name"], "自由创作 PSD")
        self.assertEqual(feature["max_input_images"], site.MAIN_IMAGE_A_PLUS_MAX_FILES)
        self.assertFalse(feature.get("hidden", False))
        self.assertIn("独立商业背景层", str(feature["default_prompt"]))

    def test_layered_result_contains_background_and_downloadable_psd(self) -> None:
        result = site.build_amazon_a_plus_layered_result(
            {"images": [self.build_green_screen_data_url()], "text": ""},
            (240, 320),
        )

        self.assertTrue(bytes(result["psd_bytes"]).startswith(b"8BPS"))
        self.assertGreaterEqual(int(result["layer_count"]), 3)
        self.assertEqual(result["layer_manifest"][-1]["name"], "A+ Background")
        self.assertEqual(len(result["background_images"]), 1)
        composite_bytes, _mime_type = site.load_image_bytes_from_url(result["images"][0])
        with Image.open(io.BytesIO(composite_bytes)) as composite:
            self.assertEqual(composite.size, (240, 320))
            self.assertEqual(composite.convert("RGBA").getpixel((230, 310))[3], 255)

    def test_page_uses_presets_ten_references_and_psd_download(self) -> None:
        render_source = inspect.getsource(site.render_openrouter_feature)

        self.assertIn("选择自由创作 PSD 规格", render_source)
        self.assertIn("max_files=MAIN_IMAGE_A_PLUS_MAX_FILES", render_source)
        self.assertIn("开始生成 PSD", render_source)
        self.assertIn("下载 PSD 源文件（Photoshop）", render_source)
        self.assertIn("allow_native_image_download=False", render_source)
        self.assertIn("A+ 成品预览", render_source)

    def test_backend_rejects_more_than_ten_psd_references(self) -> None:
        feature = site.get_feature_by_key(site.AMAZON_A_PLUS_FEATURE_KEY)
        assert feature is not None
        with self.assertRaisesRegex(RuntimeError, "最多只能上传 10 张参考图"):
            site.run_feature_job(
                {
                    "feature": dict(feature),
                    "uploaded_files": [{"name": f"ref-{index}.png"} for index in range(11)],
                    "target_size": (1464, 2400),
                }
            )


if __name__ == "__main__":
    unittest.main()
