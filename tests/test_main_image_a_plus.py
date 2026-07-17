from __future__ import annotations

import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from 图片 import openrouter_image_site as site


def image_data_url(image: Image.Image) -> str:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(output.getvalue()).decode('ascii')}"


def image_uploaded_input(image: Image.Image, name: str = "image.png") -> dict[str, object]:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return {"name": name, "type": "image/png", "data": output.getvalue()}


def open_data_url(data_url: str) -> Image.Image:
    encoded = data_url.split(",", 1)[1]
    image = Image.open(io.BytesIO(base64.b64decode(encoded)))
    image.load()
    return image


class MainImageAPlusTests(unittest.TestCase):
    def test_feature_has_three_layouts_and_ten_image_limit(self) -> None:
        feature = site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)

        self.assertIsNotNone(feature)
        assert feature is not None
        self.assertEqual(feature["name"], "主图生A+")
        self.assertEqual(feature["max_input_images"], 10)
        self.assertEqual(tuple(feature["target_size"]), (1464, 2400))
        self.assertEqual(site.MAIN_IMAGE_A_PLUS_SECTION_COUNT, 4)
        self.assertEqual(site.MAIN_IMAGE_A_PLUS_SECTION_HEIGHT, 600)
        self.assertEqual(set(site.MAIN_IMAGE_A_PLUS_LAYOUTS), {"mobile_equal", "desktop_equal", "desktop_hero"})

        mobile_layout = site.get_main_image_a_plus_layout("mobile_equal")
        self.assertEqual(mobile_layout["target_size"], (600, 1800))
        self.assertEqual(mobile_layout["section_heights"], (450, 450, 450, 450))

        desktop_layout = site.get_main_image_a_plus_layout("desktop_equal")
        self.assertEqual(desktop_layout["target_size"], (1464, 2400))
        self.assertEqual(desktop_layout["section_heights"], (600, 600, 600, 600))

        hero_layout = site.get_main_image_a_plus_layout("desktop_hero")
        self.assertEqual(hero_layout["target_size"], (1464, 2400))
        self.assertEqual(hero_layout["section_heights"], (800, 533, 533, 534))
        self.assertEqual(sum(hero_layout["section_heights"]), hero_layout["target_size"][1])

    def test_only_direct_commercial_a_plus_is_visible(self) -> None:
        visible_keys = {feature["key"] for feature in site.get_visible_features()}

        self.assertIn(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY, visible_keys)
        self.assertNotIn(site.AMAZON_A_PLUS_FEATURE_KEY, visible_keys)
        self.assertIn("套版替换", site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)["summary"])

    def test_prompt_uses_selected_mobile_layout(self) -> None:
        feature = site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        assert feature is not None
        layout = site.get_main_image_a_plus_layout("mobile_equal")
        feature_for_request = dict(feature)
        feature_for_request["target_size"] = layout["target_size"]
        feature_for_request["target_size_text"] = "600*1800"
        layout_notes = site.build_main_image_a_plus_layout_notes("mobile_equal", 3)

        prompt = site.build_prompt(
            feature_for_request,
            "整体采用黑金风格",
            site.DEFAULT_ASPECT_RATIO,
            layout_notes,
        )

        self.assertIn("600×1800px", prompt)
        self.assertIn("第 1 部分为 y=0–450px，高 450px", prompt)
        self.assertIn("第 4 部分为 y=1350–1800px，高 450px", prompt)
        self.assertIn("原生 4K", prompt)
        self.assertIn("满版延伸到画布四边", prompt)
        self.assertIn("左右至少内缩 48px", prompt)
        self.assertIn("整体采用黑金风格", prompt)
        self.assertIn("四个模块无缝合成后的最终成品尺寸必须严格等于 600*1800px", prompt)

    def test_prompt_uses_desktop_hero_section_heights(self) -> None:
        notes = site.build_main_image_a_plus_layout_notes("desktop_hero", 2)

        self.assertIn("1464×2400px", notes)
        self.assertIn("第 1 部分为 y=0–800px，高 800px", notes)
        self.assertIn("第 2 部分为 y=800–1333px，高 533px", notes)
        self.assertIn("第 4 部分为 y=1866–2400px，高 534px", notes)

    def test_template_prompt_requires_layout_lock_and_full_content_replacement(self) -> None:
        notes = site.build_main_image_a_plus_template_notes("desktop_equal", 5)
        section_prompt = site.build_main_image_a_plus_template_section_prompt(
            site.MAIN_IMAGE_A_PLUS_TEMPLATE_DEFAULT_PROMPT,
            site.get_main_image_a_plus_layout("desktop_equal"),
            0,
        )

        self.assertIn("模板图不提供可复用的品牌、人物、产品或文案", notes)
        self.assertIn("每一处原模特、原产品、原包装、原 Logo", notes)
        self.assertIn("第 1 张是当前分段的版式模板", section_prompt)
        self.assertIn("锁定模板中每个槽位的坐标、占比、裁切形状", section_prompt)
        self.assertIn("绝对不能出现在结果中", section_prompt)

    def test_template_layout_follows_original_image_dimensions(self) -> None:
        template = Image.new("RGB", (721, 1603), "white")

        layout = site.get_main_image_a_plus_template_layout(
            image_uploaded_input(template, "custom-size-template.png")
        )

        self.assertEqual(layout["key"], "template_original_size")
        self.assertEqual(layout["target_size"], (721, 1603))
        self.assertEqual(layout["section_heights"], (400, 400, 400, 403))
        self.assertEqual(sum(layout["section_heights"]), 1603)

    def test_exact_resize_keeps_full_bleed_edge_content(self) -> None:
        source = Image.new("RGB", (90, 160), "white")
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 0, 89, 39), fill="green")
        draw.rectangle((0, 40, 89, 79), fill="yellow")
        draw.rectangle((0, 80, 89, 119), fill="purple")
        draw.rectangle((0, 120, 89, 159), fill="orange")
        draw.rectangle((0, 0, 5, 159), fill="red")
        draw.rectangle((84, 0, 89, 159), fill="blue")

        result_url = site.resize_image_to_exact_size(image_data_url(source), 146, 240)

        with open_data_url(result_url) as result:
            self.assertEqual(result.size, (146, 240))
            # All four vertical sections remain and the design reaches both side edges.
            self.assertGreater(result.getpixel((73, 5))[1], result.getpixel((73, 5))[0])
            self.assertGreater(result.getpixel((73, 235))[0], result.getpixel((73, 235))[1])
            self.assertGreater(result.getpixel((0, 120))[0], result.getpixel((0, 120))[2])
            self.assertGreater(result.getpixel((145, 120))[2], result.getpixel((145, 120))[0])

    def test_stitches_hero_sections_in_exact_vertical_order(self) -> None:
        section_urls = [
            image_data_url(Image.new("RGB", (20, 20), color))
            for color in ("red", "green", "blue", "yellow")
        ]

        result_url = site.stitch_main_image_a_plus_sections(
            section_urls,
            146,
            (80, 53, 53, 54),
        )

        with open_data_url(result_url) as result:
            self.assertEqual(result.size, (146, 240))
            self.assertEqual(result.getpixel((70, 79)), (255, 0, 0))
            self.assertEqual(result.getpixel((70, 80)), (0, 128, 0))
            self.assertEqual(result.getpixel((70, 133)), (0, 0, 255))
            self.assertEqual(result.getpixel((70, 186)), (255, 255, 0))

    def test_splits_complete_template_into_selected_sections(self) -> None:
        template = Image.new("RGB", (146, 240), "white")
        draw = ImageDraw.Draw(template)
        draw.rectangle((0, 0, 145, 79), fill="red")
        draw.rectangle((0, 80, 145, 132), fill="green")
        draw.rectangle((0, 133, 145, 185), fill="blue")
        draw.rectangle((0, 186, 145, 239), fill="yellow")

        sections = site.split_main_image_a_plus_template(
            image_uploaded_input(template, "template.png"),
            146,
            (80, 53, 53, 54),
        )

        self.assertEqual(len(sections), 4)
        expected = [((146, 80), (255, 0, 0)), ((146, 53), (0, 128, 0)), ((146, 53), (0, 0, 255)), ((146, 54), (255, 255, 0))]
        for section_input, (expected_size, expected_color) in zip(sections, expected):
            with Image.open(io.BytesIO(section_input["data"])) as section:
                self.assertEqual(section.size, expected_size)
                self.assertEqual(section.getpixel((70, section.height // 2)), expected_color)

    def test_job_uses_ten_references_native_4k_and_fixed_output(self) -> None:
        source = Image.new("RGB", (200, 300), "white")
        references = [{"name": f"main-{index}.png", "data": b"image"} for index in range(10)]
        feature = site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        assert feature is not None
        job_context = {
            "feature": dict(feature),
            "model": site.NANO_BANANA_MODEL,
            "prompt": "生成四段式 A+ 宣传长图",
            "uploaded_files": references,
            "batch_groups": [],
            "output_mode": "image",
            "max_output_images": 1,
            "target_size": (1, 1),
            "account_name": "tester",
            "aspect_ratio": site.DEFAULT_ASPECT_RATIO,
        }

        with (
            patch.object(site, "call_openrouter_images_api", return_value={"images": [image_data_url(source)], "text": ""}) as request_images,
            patch.object(site, "finalize_feature_job_result", side_effect=lambda _context, result, _job_id: result),
        ):
            result = site.run_feature_job(job_context)

        self.assertEqual(request_images.call_count, 4)
        for request_call in request_images.call_args_list:
            call_kwargs = request_call.kwargs
            self.assertEqual(len(call_kwargs["uploaded_files"]), 10)
            self.assertEqual(call_kwargs["aspect_ratio"], "21:9")
            self.assertEqual(call_kwargs["resolution"], "4K")
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (1464, 2400))
        self.assertEqual(result["section_count"], 4)
        self.assertEqual(result["section_height"], 600)
        self.assertEqual(result["section_heights"], (600, 600, 600, 600))
        self.assertEqual(result["main_image_a_plus_layout_key"], "desktop_equal")
        self.assertNotIn("safe_margin", result)

    def test_job_applies_mobile_layout_size_and_sections(self) -> None:
        source = Image.new("RGB", (200, 300), "white")
        feature = site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        assert feature is not None
        job_context = {
            "feature": dict(feature),
            "model": site.NANO_BANANA_MODEL,
            "prompt": "生成手机端四段式 A+ 宣传长图",
            "uploaded_files": [{"name": "main.png", "data": b"image"}],
            "batch_groups": [],
            "output_mode": "image",
            "max_output_images": 1,
            "main_image_a_plus_layout_key": "mobile_equal",
            "account_name": "tester",
            "aspect_ratio": site.DEFAULT_ASPECT_RATIO,
        }

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={"images": [image_data_url(source)], "text": ""},
            ) as request_images,
            patch.object(site, "finalize_feature_job_result", side_effect=lambda _context, result, _job_id: result),
        ):
            result = site.run_feature_job(job_context)

        self.assertEqual(request_images.call_count, 4)
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (600, 1800))
        self.assertEqual(result["requested_aspect_ratios"], ("4:3", "4:3", "4:3", "4:3"))
        self.assertEqual(result["section_heights"], (450, 450, 450, 450))
        self.assertEqual(result["section_height"], 450)
        self.assertEqual(result["main_image_a_plus_layout_key"], "mobile_equal")

    def test_template_mode_sends_template_section_first_and_replaces_content(self) -> None:
        generated = Image.new("RGB", (200, 100), "white")
        template = Image.new("RGB", (146, 240), "pink")
        feature = site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        assert feature is not None
        job_context = {
            "feature": dict(feature),
            "model": site.NANO_BANANA_MODEL,
            "prompt": "锁定模板版式并替换全部内容",
            "uploaded_files": [{"name": "new-product.png", "data": b"content"}],
            "batch_groups": [],
            "output_mode": "image",
            "max_output_images": 1,
            "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_TEMPLATE,
            "main_image_a_plus_layout_key": "desktop_equal",
            "main_image_a_plus_template": image_uploaded_input(template, "finished-a-plus.png"),
            "account_name": "tester",
            "aspect_ratio": site.DEFAULT_ASPECT_RATIO,
        }

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={"images": [image_data_url(generated)], "text": ""},
            ) as request_images,
            patch.object(site, "finalize_feature_job_result", side_effect=lambda _context, result, _job_id: result),
        ):
            result = site.run_feature_job(job_context)

        self.assertEqual(request_images.call_count, 4)
        for index, request_call in enumerate(request_images.call_args_list, start=1):
            call_kwargs = request_call.kwargs
            self.assertEqual(len(call_kwargs["uploaded_files"]), 2)
            self.assertEqual(
                call_kwargs["uploaded_files"][0]["name"],
                f"a_plus_layout_template_section_{index}.png",
            )
            self.assertEqual(call_kwargs["uploaded_files"][1]["name"], "new-product.png")
            self.assertIn("第 1 张是当前分段的版式模板", call_kwargs["prompt"])
            self.assertIn("绝对不能出现在结果中", call_kwargs["prompt"])
        self.assertEqual(result["main_image_a_plus_mode"], site.MAIN_IMAGE_A_PLUS_MODE_TEMPLATE)
        self.assertIn("套版替换", result["channel"])
        self.assertEqual(result["target_size"], (146, 240))
        self.assertEqual(result["section_heights"], (60, 60, 60, 60))
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (146, 240))

    def test_template_mode_requires_finished_template(self) -> None:
        feature = site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        assert feature is not None
        job_context = {
            "feature": dict(feature),
            "uploaded_files": [{"name": "new-product.png", "data": b"content"}],
            "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_TEMPLATE,
        }

        with self.assertRaisesRegex(RuntimeError, "需要先上传 1 张成品 A\\+ 模板"):
            site.run_feature_job(job_context)

    def test_job_rejects_more_than_ten_references(self) -> None:
        feature = site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        assert feature is not None
        job_context = {
            "feature": dict(feature),
            "uploaded_files": [{"name": f"main-{index}.png"} for index in range(11)],
        }

        with self.assertRaisesRegex(RuntimeError, "最多只能上传 10 张主图"):
            site.run_feature_job(job_context)


if __name__ == "__main__":
    unittest.main()
