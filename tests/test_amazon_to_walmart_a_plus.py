from __future__ import annotations

import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image

from 图片 import openrouter_image_site as site


def image_input(width: int, height: int, name: str = "amazon-a-plus.png") -> dict[str, object]:
    output = io.BytesIO()
    image = Image.new("RGB", (width, height), "white")
    for index, color in enumerate(("#1f2937", "#7c3aed", "#f59e0b", "#0f766e")):
        top = round(height * index / 4)
        bottom = round(height * (index + 1) / 4)
        section = Image.new("RGB", (width, bottom - top), color)
        image.paste(section, (0, top))
    image.save(output, format="PNG")
    return {"name": name, "type": "image/png", "data": output.getvalue()}


def image_data_url(width: int = 1920, height: int = 1080, color: str = "#334155") -> str:
    output = io.BytesIO()
    Image.new("RGB", (width, height), color).save(output, format="PNG")
    payload = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{payload}"


class AmazonToWalmartAPlusTests(unittest.TestCase):
    def test_feature_is_visible_and_has_fixed_four_page_output(self) -> None:
        feature = site.get_feature_by_key(site.AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY)
        assert feature is not None
        self.assertEqual(feature["name"], "亚马逊A+改沃尔玛A+")
        self.assertEqual(feature["max_input_images"], 1)
        self.assertEqual(feature["fixed_output_count"], 4)
        self.assertEqual(feature["target_size"], (1920, 1080))
        a_plus_group = next(keys for name, keys in site.SIDE_MENU_FEATURE_GROUPS if name == "A+ 电商设计")
        self.assertIn(site.AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY, a_plus_group)

    def test_long_amazon_canvas_is_split_into_four_ordered_sections(self) -> None:
        sections, was_split = site.split_amazon_a_plus_source(image_input(1464, 2400))
        self.assertTrue(was_split)
        self.assertEqual(len(sections), 4)
        self.assertEqual([site.get_uploaded_input_dimensions(item) for item in sections], [(1464, 600)] * 4)

    @patch.object(site, "call_openrouter_images_api")
    def test_job_generates_four_exact_pages_and_carries_previous_page_forward(self, generate) -> None:
        generate.side_effect = [
            {"images": [image_data_url(color=color)]}
            for color in ("#111827", "#4c1d95", "#b45309", "#115e59")
        ]
        result = site.run_amazon_to_walmart_a_plus_job(
            {
                "feature": site.get_feature_by_key(site.AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY),
                "model": site.NANO_BANANA_MODEL,
                "prompt": "保持品牌一致并转换沃尔玛版式。",
                "uploaded_files": [image_input(1464, 2400)],
            }
        )

        self.assertEqual(len(result["images"]), 4)
        self.assertEqual(len(result["captions"]), 4)
        self.assertEqual(generate.call_count, 4)
        self.assertEqual(len(generate.call_args_list[0].kwargs["uploaded_files"]), 2)
        self.assertEqual(len(generate.call_args_list[1].kwargs["uploaded_files"]), 3)
        second_page_prompt = generate.call_args_list[1].kwargs["prompt"]
        self.assertIn("文案去重依据", second_page_prompt)
        self.assertIn("跨页重复文案数量为零", second_page_prompt)
        self.assertIn("不能编造新句子填补", second_page_prompt)
        sizes = []
        for url in result["images"]:
            image_bytes, _mime_type = site.load_image_bytes_from_url(url)
            with Image.open(io.BytesIO(image_bytes)) as opened:
                sizes.append(opened.size)
        self.assertEqual(sizes, [(1920, 1080)] * 4)


if __name__ == "__main__":
    unittest.main()
