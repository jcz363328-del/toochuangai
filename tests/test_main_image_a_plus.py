from __future__ import annotations

import base64
import inspect
import io
import threading
import time
import unittest
from unittest.mock import Mock, patch

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
    def test_layout_keeps_primary_and_dynamic_actions_in_reserved_slots(self) -> None:
        render_source = inspect.getsource(site.render_openrouter_feature)
        style_source = inspect.getsource(site.inject_app_styles)

        self.assertIn("primary_action_slot = st.empty()", render_source)
        self.assertIn("main-action-dock-marker", render_source)
        self.assertIn("a-plus-analysis-card-marker", render_source)
        self.assertIn("a-plus-auto-fill-card-marker", render_source)
        self.assertIn("disabled=True", render_source)
        self.assertIn("position: sticky", style_source)
        self.assertIn("a-plus-template-card-marker", style_source)

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
        self.assertEqual(
            site.MAIN_IMAGE_A_PLUS_MODE_LABELS[site.MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST],
            "一张测试",
        )
        self.assertEqual(
            site.MAIN_IMAGE_A_PLUS_MODE_LABELS[site.MAIN_IMAGE_A_PLUS_MODE_ELEMENT],
            "指定元素替换",
        )

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
        self.assertNotIn("y=0–450px", prompt)
        self.assertNotIn("每段 450px", prompt)
        self.assertIn("四个阶段只代表信息节奏", prompt)
        self.assertIn("不按固定像素、固定距离或等高方框划分", prompt)
        self.assertIn("允许跨越相邻阶段", prompt)
        self.assertIn("不要绘制分割线、边框、卡片底板", prompt)
        self.assertIn("原生 4K", prompt)
        self.assertIn("满版延伸到画布四边", prompt)
        self.assertNotIn("左右至少内缩 48px", prompt)
        self.assertIn("不显示任何安全距离", prompt)
        self.assertIn("首屏必须是完整的商业主视觉", prompt)
        self.assertIn("参考图只是可选择的素材池，不要求全部出现在首屏", prompt)
        self.assertIn("严禁在首屏中直接堆叠多个产品抠图", prompt)
        self.assertIn("整体采用黑金风格", prompt)
        self.assertIn("最终连续长图成品尺寸必须严格等于 600*1800px", prompt)

    def test_free_prompt_hides_desktop_hero_section_distances(self) -> None:
        notes = site.build_main_image_a_plus_layout_notes("desktop_hero", 2)

        self.assertIn("1464×2400px", notes)
        self.assertNotIn("y=0–800px", notes)
        self.assertNotIn("高 800px", notes)
        self.assertNotIn("533px", notes)
        self.assertIn("不按固定像素、固定距离或等高方框划分", notes)
        self.assertIn("不能暴露内部拼接位置", notes)

    def test_template_prompt_requires_layout_lock_and_full_content_replacement(self) -> None:
        notes = site.build_main_image_a_plus_template_notes("desktop_equal", 5)
        section_prompt = site.build_main_image_a_plus_template_section_prompt(
            site.MAIN_IMAGE_A_PLUS_TEMPLATE_DEFAULT_PROMPT,
            site.get_main_image_a_plus_layout("desktop_equal"),
            0,
        )

        self.assertIn("模板图不提供可复用的品牌、人物、产品或文案", notes)
        self.assertIn("每一处原模特、原产品、原包装、原 Logo", notes)
        self.assertIn("第一张模板图决定最终原始宽高", notes)
        self.assertIn("不得移动、增删、合并或拆分槽位", notes)
        self.assertIn("禁止新增模板中不存在的人物、产品、配件", notes)
        self.assertIn("第 1 张是当前分段的版式模板", section_prompt)
        self.assertIn("像素级锁定模板中每个槽位的坐标、宽高、占比", section_prompt)
        self.assertIn("只替换文案、人物、产品、包装、Logo", section_prompt)
        self.assertIn("严格一对一替换且保持模板原有元素数量", section_prompt)
        self.assertIn("禁止重复人物、重复商品、重复 Logo", section_prompt)
        self.assertIn("绝对不能出现在结果中", section_prompt)

    def test_single_test_prompt_requires_one_complete_generation_without_stitching(self) -> None:
        layout = site.get_main_image_a_plus_layout("desktop_equal")
        notes = site.build_main_image_a_plus_single_test_notes(layout, 5)
        prompt = site.build_main_image_a_plus_single_test_prompt(
            site.MAIN_IMAGE_A_PLUS_SINGLE_TEST_DEFAULT_PROMPT + notes,
            layout,
        )

        self.assertIn("第 1 张是完整成品 A+ 版式模板", prompt)
        self.assertIn("一次直接生成 1 张完整的 1464×2400px", prompt)
        self.assertIn("禁止拆成四段", prompt)
        self.assertIn("禁止拼接", prompt)
        self.assertIn("唯一允许保留的内容只有两类", prompt)
        self.assertIn("除纯背景和版式结构之外", prompt)
        self.assertIn("绝对不能只替换一部分", prompt)
        self.assertIn("每一处旧产品、产品局部、包装、品牌名、Logo", prompt)
        self.assertIn("将新模特替换全部旧人物位置", prompt)
        self.assertIn("没有新模特时清除旧模特", prompt)
        self.assertIn("残留数量为零", prompt)
        self.assertIn("不要只替换首屏或明显主体", prompt)
        self.assertIn("只输出这一张完整成品", prompt)

    def test_element_analysis_parses_grouped_regions_and_builds_numbered_preview(self) -> None:
        analysis_text = """```json
        {"elements":[
          {"name":"品牌 Logo","type":"brand_logo","description":"重复品牌标识","replacement_hint":"上传新 Logo", "regions":[[100,80,300,180],[700,820,900,920]]},
          {"name":"主模特","type":"model","regions":[[0.35,0.12,0.85,0.58]]}
        ]}
        ```"""
        elements = site.parse_main_image_a_plus_element_analysis(analysis_text, (200, 400))

        self.assertEqual(len(elements), 2)
        self.assertEqual(elements[0]["id"], 1)
        self.assertEqual(elements[0]["name"], "品牌 Logo")
        self.assertEqual(len(elements[0]["regions"]), 2)
        self.assertEqual(elements[1]["regions"], [[350, 120, 850, 580]])

        template = Image.new("RGB", (200, 400), "white")
        preview_url = site.build_main_image_a_plus_element_preview(
            image_uploaded_input(template, "template.png"),
            elements,
        )
        with open_data_url(preview_url) as preview:
            self.assertEqual(preview.size, (200, 400))
            self.assertNotEqual(preview.getpixel((20, 32)), (255, 255, 255))

    def test_element_analysis_uses_vision_model_and_strict_json_prompt(self) -> None:
        template = image_uploaded_input(Image.new("RGB", (200, 400), "white"), "template.png")
        response_text = '{"elements":[{"name":"产品","type":"product","regions":[[100,100,800,500]]}]}'

        with patch.object(site, "call_openrouter", return_value={"text": response_text}) as analyze_request:
            elements = site.analyze_main_image_a_plus_elements(template)

        self.assertEqual(elements[0]["name"], "产品")
        call_kwargs = analyze_request.call_args.kwargs
        self.assertEqual(call_kwargs["model"], site.MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL)
        self.assertEqual(call_kwargs["output_mode"], "text")
        self.assertEqual(call_kwargs["uploaded_files"], [template])
        self.assertIn("只返回严格 JSON", call_kwargs["prompt"])
        self.assertIn("不要只分析首屏", call_kwargs["prompt"])

    def test_replacement_material_analysis_matches_and_deduplicates_slots(self) -> None:
        elements = [
            {"id": 1, "name": "主模特", "type": "model", "regions": [[100, 100, 500, 700]]},
            {"id": 2, "name": "产品包装", "type": "package", "regions": [[550, 200, 900, 600]]},
        ]
        response_text = """```json
        {"matches":[
          {"element_id":1,"image_index":2,"confidence":65,"detected_content":"人物","crop_box":[80,40,930,980]},
          {"element_id":1,"image_index":1,"confidence":0.94,"detected_content":"新模特","crop_box":[120,60,850,960]},
          {"element_id":2,"image_index":2,"confidence":0.88,"reason":"包装对应","crop_box":[220,260,780,740]},
          {"element_id":9,"image_index":1,"confidence":1},
          {"element_id":2,"image_index":8,"confidence":1}
        ]}
        ```"""

        matches = site.parse_main_image_a_plus_replacement_matches(response_text, elements, 2)

        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]["element_id"], 1)
        self.assertEqual(matches[0]["image_index"], 1)
        self.assertAlmostEqual(matches[0]["confidence"], 0.94)
        self.assertEqual(matches[0]["crop_box"], [120, 60, 850, 960])
        self.assertEqual(matches[1]["image_index"], 2)
        self.assertEqual(matches[1]["crop_box"], [220, 260, 780, 740])

    def test_replacement_material_analysis_uses_template_and_all_materials(self) -> None:
        template = image_uploaded_input(Image.new("RGB", (300, 600), "white"), "template.png")
        materials = [
            image_uploaded_input(Image.new("RGB", (200, 200), "red"), "model.png"),
            image_uploaded_input(Image.new("RGB", (200, 200), "blue"), "product.png"),
        ]
        elements = [
            {"id": 1, "name": "模特", "type": "model", "regions": [[100, 100, 600, 700]]},
        ]
        response_text = (
            '{"matches":[{"element_id":1,"image_index":1,"confidence":0.9,'
            '"crop_box":[150,40,850,980]}]}'
        )

        with patch.object(site, "call_openrouter", return_value={"text": response_text}) as request:
            matches = site.analyze_main_image_a_plus_replacement_matches(
                template,
                elements,
                materials,
            )

        self.assertEqual(matches[0]["element_id"], 1)
        call_kwargs = request.call_args.kwargs
        self.assertEqual(call_kwargs["uploaded_files"], [template, *materials])
        self.assertEqual(call_kwargs["output_mode"], "text")
        self.assertIn("image_index=1 对应输入图片第 2 张", call_kwargs["prompt"])
        self.assertIn("一张素材同时包含多类有效内容时可以匹配多个编号", call_kwargs["prompt"])
        self.assertIn("每条匹配必须同时返回 crop_box", call_kwargs["prompt"])
        self.assertIn("禁止用整张图片范围代替", call_kwargs["prompt"])

    def test_recommended_replacement_is_cropped_to_element_only(self) -> None:
        source = Image.new("RGB", (300, 200), "navy")
        draw = ImageDraw.Draw(source)
        draw.rectangle((60, 40, 180, 160), fill="red")

        cropped_input = site.crop_main_image_a_plus_replacement_input(
            image_uploaded_input(source, "full-poster.png"),
            [200, 200, 600, 800],
            3,
            "产品包装",
        )

        self.assertIsNotNone(cropped_input)
        assert cropped_input is not None
        self.assertEqual(cropped_input["type"], "image/png")
        self.assertIn("recommended_3_", cropped_input["name"])
        with Image.open(io.BytesIO(cropped_input["data"])) as cropped:
            self.assertLess(cropped.width, source.width)
            self.assertLess(cropped.height, source.height)
            self.assertEqual(cropped.getpixel((cropped.width // 2, cropped.height // 2)), (255, 0, 0))

        self.assertIsNone(
            site.crop_main_image_a_plus_replacement_input(
                image_uploaded_input(source, "full-poster.png"),
                [0, 0, 1000, 1000],
                3,
                "产品包装",
            )
        )

    def test_manual_point_finds_existing_smallest_region_or_adds_new_element(self) -> None:
        existing = [
            {"id": 1, "name": "大区域", "regions": [[0, 0, 900, 900]]},
            {"id": 2, "name": "产品", "regions": [[200, 200, 400, 400]]},
        ]
        matched = site.find_main_image_a_plus_element_at_point(existing, (300, 300))
        self.assertEqual(matched["id"], 2)
        self.assertIsNone(site.find_main_image_a_plus_element_at_point(existing, (950, 950)))

        template = image_uploaded_input(Image.new("RGB", (300, 600), "white"), "template.png")
        response_text = (
            '{"elements":[{"name":"遗漏 Logo","type":"brand_logo",'
            '"regions":[[700,700,900,820]]}]}'
        )
        with patch.object(site, "call_openrouter", return_value={"text": response_text}) as request:
            new_element = site.analyze_main_image_a_plus_element_at_point(
                template,
                (800, 760),
                existing,
            )

        self.assertEqual(new_element["id"], 3)
        self.assertEqual(new_element["name"], "遗漏 Logo")
        self.assertIn("位置为 (800, 760)", request.call_args.kwargs["prompt"])
        self.assertIn("避免重复返回已经识别的元素", request.call_args.kwargs["prompt"])

    def test_element_replacement_prompt_maps_each_reference_to_numbered_regions(self) -> None:
        layout = site.get_main_image_a_plus_layout("desktop_equal")
        replacements = [
            {"id": 2, "name": "主模特", "type": "model", "regions": [[100, 50, 800, 700]]},
            {"id": 5, "name": "产品包装", "type": "package", "regions": [[650, 720, 950, 980]]},
        ]
        prompt = site.build_main_image_a_plus_element_replacement_prompt(
            site.MAIN_IMAGE_A_PLUS_ELEMENT_DEFAULT_PROMPT,
            layout,
            replacements,
        )

        self.assertIn("输入图片第 2 张 → 编号 #2“主模特”", prompt)
        self.assertIn("输入图片第 3 张 → 编号 #5“产品包装”", prompt)
        self.assertIn("只替换归一化区域 [100,50,800,700]", prompt)
        self.assertIn("未列出的产品、品牌、Logo、模特、文字", prompt)
        self.assertIn("选中元素全部替换、未选元素完全未改", prompt)

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
        for index, request_call in enumerate(request_images.call_args_list):
            call_kwargs = request_call.kwargs
            self.assertEqual(len(call_kwargs["uploaded_files"]), 10)
            self.assertEqual(call_kwargs["aspect_ratio"], "21:9")
            self.assertEqual(call_kwargs["resolution"], "4K")
        first_section_prompt = request_images.call_args_list[0].kwargs["prompt"]
        second_section_prompt = request_images.call_args_list[1].kwargs["prompt"]
        self.assertIn("首屏商业主视觉专项规则", first_section_prompt)
        self.assertIn("一位模特为唯一视觉主体", first_section_prompt)
        self.assertIn("模特必须位于最上层、最前景", first_section_prompt)
        self.assertIn("不能反向遮挡模特", first_section_prompt)
        self.assertIn("禁止把多个商品抠图", first_section_prompt)
        self.assertNotIn("首屏商业主视觉专项规则", second_section_prompt)
        self.assertIn("都可以延伸到片段顶部或底部", second_section_prompt)
        self.assertNotIn("最后一张是紧邻当前画面上方的已生成连续片段", second_section_prompt)
        self.assertFalse(
            any(
                str(uploaded.get("name") or "").startswith("a_plus_continuity_")
                for uploaded in request_images.call_args_list[1].kwargs["uploaded_files"]
            )
        )
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
        self.assertEqual(len(request_images.call_args_list[0].kwargs["uploaded_files"]), 1)
        self.assertEqual(len(request_images.call_args_list[1].kwargs["uploaded_files"]), 2)
        self.assertEqual(
            request_images.call_args_list[1].kwargs["uploaded_files"][-1]["name"],
            "a_plus_continuity_section_1.jpg",
        )
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (600, 1800))
        self.assertEqual(result["requested_aspect_ratios"], ("4:3", "4:3", "4:3", "4:3"))
        self.assertEqual(result["section_heights"], (450, 450, 450, 450))
        self.assertEqual(result["section_height"], 450)
        self.assertEqual(result["main_image_a_plus_layout_key"], "mobile_equal")

    def test_continuity_reference_is_resized_and_compressed(self) -> None:
        source = Image.new("RGB", (1200, 900), "purple")

        reference = site.build_main_image_a_plus_continuity_reference(
            image_data_url(source),
            600,
            450,
            "previous-section.png",
        )

        self.assertEqual(reference["name"], "previous-section.jpg")
        self.assertEqual(reference["type"], "image/jpeg")
        with Image.open(io.BytesIO(reference["data"])) as compressed:
            self.assertEqual(compressed.size, (600, 450))

    def test_uploaded_references_are_prepared_once_for_fast_reuse(self) -> None:
        source = Image.new("RGB", (3200, 2400), "purple")

        reference = site.prepare_main_image_a_plus_reference_input(
            image_uploaded_input(source, "large-reference.png")
        )

        self.assertEqual(reference["name"], "large-reference_a_plus_ref.jpg")
        self.assertEqual(reference["type"], "image/jpeg")
        self.assertLessEqual(len(reference["data"]), site.MAIN_IMAGE_A_PLUS_REFERENCE_TARGET_BYTES)
        with Image.open(io.BytesIO(reference["data"])) as compressed:
            self.assertLessEqual(max(compressed.size), site.MAIN_IMAGE_A_PLUS_REFERENCE_MAX_EDGE)

    def test_template_sections_are_generated_in_parallel_and_kept_in_order(self) -> None:
        generated = image_data_url(Image.new("RGB", (146, 60), "white"))
        template = Image.new("RGB", (146, 240), "pink")
        active_count = 0
        max_active_count = 0
        lock = threading.Lock()

        def slow_request(**_kwargs: object) -> dict[str, object]:
            nonlocal active_count, max_active_count
            with lock:
                active_count += 1
                max_active_count = max(max_active_count, active_count)
            time.sleep(0.04)
            with lock:
                active_count -= 1
            return {"images": [generated], "text": ""}

        with patch.object(site, "call_openrouter_images_api", side_effect=slow_request):
            result = site.run_main_image_a_plus_job(
                {
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "并行套版",
                    "uploaded_files": [{"name": "new-product.png", "data": b"content"}],
                    "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_TEMPLATE,
                    "main_image_a_plus_layout": {
                        "key": "test-template",
                        "label": "测试模板",
                        "target_size": (146, 240),
                        "section_heights": (60, 60, 60, 60),
                        "text_margin_x": 12,
                        "text_margin_y": 8,
                    },
                    "main_image_a_plus_template": image_uploaded_input(template, "template.png"),
                }
            )

        self.assertGreaterEqual(max_active_count, 2)
        self.assertEqual(result["generation_waves"], 1)
        self.assertEqual(result["max_parallel_sections"], 4)
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (146, 240))

    def test_images_api_retries_transient_read_timeout(self) -> None:
        success_response = Mock(status_code=200)
        success_response.json.return_value = {
            "data": [{"b64_json": "aW1hZ2U=", "media_type": "image/png"}]
        }

        with (
            patch.object(site, "load_api_key", return_value="test-key"),
            patch.object(
                site.requests,
                "post",
                side_effect=[site.requests.ReadTimeout("temporary timeout"), success_response],
            ) as request_post,
            patch.object(site.time, "sleep") as retry_sleep,
        ):
            result = site.call_openrouter_images_api(
                model=site.NANO_BANANA_MODEL,
                prompt="生成测试图片",
            )

        self.assertEqual(request_post.call_count, 2)
        self.assertEqual(retry_sleep.call_count, 1)
        self.assertEqual(
            request_post.call_args_list[0].kwargs["timeout"],
            (
                site.OPENROUTER_IMAGES_CONNECT_TIMEOUT_SECONDS,
                site.OPENROUTER_IMAGES_READ_TIMEOUT_SECONDS,
            ),
        )
        self.assertEqual(result["images"], ["data:image/png;base64,aW1hZ2U="])

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

    def test_single_test_mode_generates_complete_template_once_without_split_or_stitch(self) -> None:
        generated = Image.new("RGB", (200, 300), "white")
        template = Image.new("RGB", (146, 240), "pink")
        feature = site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        assert feature is not None
        job_context = {
            "feature": dict(feature),
            "model": site.NANO_BANANA_MODEL,
            "prompt": "使用完整模板一次替换全部内容",
            "uploaded_files": [{"name": "new-product.png", "type": "image/png", "data": b"content"}],
            "batch_groups": [],
            "output_mode": "image",
            "max_output_images": 1,
            "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST,
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
            patch.object(site, "split_main_image_a_plus_template") as split_template,
            patch.object(site, "stitch_main_image_a_plus_sections") as stitch_sections,
            patch.object(site, "finalize_feature_job_result", side_effect=lambda _context, result, _job_id: result),
        ):
            result = site.run_feature_job(job_context)

        request_images.assert_called_once()
        split_template.assert_not_called()
        stitch_sections.assert_not_called()
        call_kwargs = request_images.call_args.kwargs
        self.assertEqual(len(call_kwargs["uploaded_files"]), 2)
        self.assertEqual(call_kwargs["uploaded_files"][0]["name"], "finished-a-plus.png")
        self.assertEqual(call_kwargs["uploaded_files"][1]["name"], "new-product.png")
        self.assertEqual(call_kwargs["resolution"], "4K")
        self.assertIn("禁止拆成四段", call_kwargs["prompt"])
        self.assertIn("禁止拼接", call_kwargs["prompt"])
        self.assertEqual(result["main_image_a_plus_mode"], site.MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST)
        self.assertEqual(result["section_count"], 1)
        self.assertEqual(result["section_heights"], (240,))
        self.assertIn("整图套版重绘", result["channel"])
        self.assertIn("未拆分模板", result["text"])
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (146, 240))

    def test_element_mode_replaces_only_mapped_elements_in_one_complete_generation(self) -> None:
        generated = Image.new("RGB", (200, 300), "white")
        template = Image.new("RGB", (146, 240), "pink")
        feature = site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        assert feature is not None
        replacements = [
            {"id": 2, "name": "主模特", "type": "model", "regions": [[100, 50, 800, 700]]},
            {"id": 5, "name": "产品包装", "type": "package", "regions": [[650, 720, 950, 980]]},
        ]
        job_context = {
            "feature": dict(feature),
            "model": site.NANO_BANANA_MODEL,
            "prompt": "只替换指定编号",
            "uploaded_files": [
                {"name": "new-model.png", "type": "image/png", "data": b"model"},
                {"name": "new-package.png", "type": "image/png", "data": b"package"},
            ],
            "batch_groups": [],
            "output_mode": "image",
            "max_output_images": 1,
            "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_ELEMENT,
            "main_image_a_plus_template": image_uploaded_input(template, "finished-a-plus.png"),
            "main_image_a_plus_element_replacements": replacements,
            "account_name": "tester",
            "aspect_ratio": site.DEFAULT_ASPECT_RATIO,
        }

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={"images": [image_data_url(generated)], "text": ""},
            ) as request_images,
            patch.object(site, "split_main_image_a_plus_template") as split_template,
            patch.object(site, "stitch_main_image_a_plus_sections") as stitch_sections,
            patch.object(site, "finalize_feature_job_result", side_effect=lambda _context, result, _job_id: result),
        ):
            result = site.run_feature_job(job_context)

        request_images.assert_called_once()
        split_template.assert_not_called()
        stitch_sections.assert_not_called()
        call_kwargs = request_images.call_args.kwargs
        self.assertEqual(
            [item["name"] for item in call_kwargs["uploaded_files"]],
            ["finished-a-plus.png", "new-model.png", "new-package.png"],
        )
        self.assertIn("输入图片第 2 张 → 编号 #2“主模特”", call_kwargs["prompt"])
        self.assertIn("输入图片第 3 张 → 编号 #5“产品包装”", call_kwargs["prompt"])
        self.assertEqual(result["main_image_a_plus_mode"], site.MAIN_IMAGE_A_PLUS_MODE_ELEMENT)
        self.assertEqual(result["replaced_element_count"], 2)
        self.assertEqual(result["replaced_element_ids"], (2, 5))
        self.assertIn("指定元素整图替换", result["channel"])
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
