from __future__ import annotations

import base64
import inspect
import io
import json
import threading
import time
import unittest
import zipfile
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


def passed_quality_review(score: float = 9.0) -> dict[str, object]:
    return {
        "reviewed": True,
        "passed": True,
        "quality_score": score,
        "critical_issue_count": 0,
        "layout_issues": [],
    }


class MainImageAPlusTests(unittest.TestCase):
    def test_main_image_uploads_support_drag_priority_reordering(self) -> None:
        page_source = inspect.getsource(site.render_openrouter_feature)
        uploader_source = inspect.getsource(site.render_multi_image_uploader)
        sorter_source = inspect.getsource(site.inject_upload_reorder_support)

        self.assertIn("allow_reorder=True", page_source)
        self.assertIn("按住图片左上角", uploader_source)
        self.assertIn('addEventListener("dragstart"', sorter_source)
        self.assertIn('addEventListener("drop"', sorter_source)
        self.assertIn("UPLOAD_REORDER_QUERY_KEY", sorter_source)

    def test_upload_priority_token_round_trips_and_cache_order_is_persisted(self) -> None:
        widget_key = "main_image_a_plus_uploader_main_image_a_plus"
        token = site.build_upload_reorder_token(widget_key, 0, 2)
        self.assertEqual(site.parse_upload_reorder_token(token), (widget_key, 0, 2))

        first = {"name": "first.png"}
        second = {"name": "second.png"}
        third = {"name": "third.png"}
        reordered = [second, third, first]
        with patch.object(site, "get_current_account_name", return_value="tester"), patch.object(
            site,
            "load_upload_cache",
            return_value=[first, second, third],
        ), patch.object(site, "replace_upload_cache", return_value=reordered) as replace_cache:
            result = site.reorder_upload_cache_item(widget_key, 0, 2)

        self.assertEqual(result, reordered)
        replace_cache.assert_called_once_with(widget_key, reordered, account_name="tester")

    def test_mobile_and_desktop_crop_archives_contain_four_ordered_png_segments(self) -> None:
        mobile_source = Image.new("RGB", (60, 180), "white")
        mobile_draw = ImageDraw.Draw(mobile_source)
        colors = ("red", "green", "blue", "yellow")
        for index, color in enumerate(colors):
            mobile_draw.rectangle((0, index * 45, 59, (index + 1) * 45 - 1), fill=color)
        mobile_bytes = io.BytesIO()
        mobile_source.save(mobile_bytes, format="PNG")

        mobile_archive = site.build_main_image_a_plus_crop_archive(
            mobile_bytes.getvalue(),
            "mobile",
            "sample.png",
        )
        self.assertEqual(mobile_archive["source_size"], (60, 180))
        self.assertEqual(mobile_archive["normalized_size"], (600, 1800))
        self.assertEqual(mobile_archive["segment_sizes"], [(600, 450)] * 4)
        self.assertTrue(mobile_archive["file_name"].endswith("_mobile_4_segments.zip"))
        with zipfile.ZipFile(io.BytesIO(mobile_archive["data"])) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 4)
            self.assertEqual(names[0], "sample_mobile_01.png")
            for index, name in enumerate(names):
                with Image.open(io.BytesIO(archive.read(name))) as segment:
                    self.assertEqual(segment.size, (600, 450))
                    expected = Image.new("RGB", (1, 1), colors[index]).getpixel((0, 0))
                    actual = segment.convert("RGB").getpixel((300, 225))
                    self.assertEqual(actual, expected)

        desktop_source = Image.new("RGB", (80, 2400), "white")
        desktop_bytes = io.BytesIO()
        desktop_source.save(desktop_bytes, format="PNG")
        desktop_archive = site.build_main_image_a_plus_crop_archive(
            desktop_bytes.getvalue(),
            "desktop",
            "desktop-result.jpg",
        )
        self.assertEqual(desktop_archive["normalized_size"], (80, 2400))
        self.assertEqual(desktop_archive["segment_sizes"], [(80, 600)] * 4)
        with zipfile.ZipFile(io.BytesIO(desktop_archive["data"])) as archive:
            self.assertEqual(len(archive.namelist()), 4)
            with Image.open(io.BytesIO(archive.read(archive.namelist()[-1]))) as segment:
                self.assertEqual(segment.size, (80, 600))

    def test_mobile_and_desktop_crop_archives_preserve_five_screen_examples(self) -> None:
        for preset_key, size, expected_segment_size in (
            ("mobile", (600, 2250), (600, 450)),
            ("desktop", (1464, 3000), (1464, 600)),
        ):
            source = Image.new("RGB", size, "white")
            source_bytes = io.BytesIO()
            source.save(source_bytes, format="PNG")

            archive = site.build_main_image_a_plus_crop_archive(
                source_bytes.getvalue(),
                preset_key,
                f"five-screen-{preset_key}.png",
            )

            self.assertEqual(archive["segment_count"], 5)
            self.assertEqual(archive["normalized_size"], size)
            self.assertEqual(archive["segment_sizes"], [expected_segment_size] * 5)
            self.assertTrue(archive["file_name"].endswith(f"_{preset_key}_5_segments.zip"))
            with zipfile.ZipFile(io.BytesIO(archive["data"])) as zipped:
                self.assertEqual(len(zipped.namelist()), 5)

    def test_mobile_layout_screen_count_tracks_desktop_story_length(self) -> None:
        four_screen = site.get_main_image_a_plus_mobile_layout_for_source((1464, 2400))
        five_screen = site.get_main_image_a_plus_mobile_layout_for_source((1464, 3000))

        self.assertEqual(four_screen["target_size"], (600, 1800))
        self.assertEqual(four_screen["mobile_screen_count"], 4)
        self.assertEqual(five_screen["target_size"], (600, 2250))
        self.assertEqual(five_screen["mobile_screen_count"], 5)
        self.assertEqual(five_screen["section_heights"], (450,) * 5)

    def test_a_plus_crop_options_are_hidden_until_opened_and_enabled_for_history(self) -> None:
        crop_source = inspect.getsource(site.render_main_image_a_plus_crop_downloads)
        history_source = inspect.getsource(site.render_history_gallery)
        page_source = inspect.getsource(site.render_openrouter_feature)

        self.assertIn("options_visible", crop_source)
        self.assertIn("if not is_visible", crop_source)
        self.assertIn("手机端裁切", str(site.MAIN_IMAGE_A_PLUS_CROP_PRESETS))
        self.assertIn("电脑端裁切", str(site.MAIN_IMAGE_A_PLUS_CROP_PRESETS))
        self.assertIn("st.download_button", crop_source)
        self.assertIn("enable_a_plus_crop_downloads", history_source)
        self.assertIn("render_main_image_a_plus_crop_downloads", page_source)
        self.assertIn("生成手机端适配版", page_source)
        self.assertIn("submit_main_image_a_plus_mobile_adaptation", page_source)
        self.assertIn("生成手机端适配版", history_source)
        self.assertIn("is_main_image_a_plus_mobile_canvas", history_source)
        self.assertIn("submit_main_image_a_plus_mobile_adaptation", history_source)
        self.assertIn("保留问题最少的可编辑预览", page_source)
        self.assertIn("人物或商品严重截断的结果仍会阻断", page_source)

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
        self.assertEqual(
            site.MAIN_IMAGE_A_PLUS_MODE_LABELS[site.MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN],
            "首屏设计感",
        )
        self.assertEqual(
            site.MAIN_IMAGE_A_PLUS_FREE_MODES,
            {site.MAIN_IMAGE_A_PLUS_MODE_FREE, site.MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN},
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

    def test_commercial_a_plus_and_free_psd_entries_are_visible(self) -> None:
        visible_keys = {feature["key"] for feature in site.get_visible_features()}

        self.assertIn(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY, visible_keys)
        self.assertIn(site.AMAZON_A_PLUS_FEATURE_KEY, visible_keys)
        self.assertIn("套版替换", site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)["summary"])
        self.assertEqual(site.get_feature_by_key(site.AMAZON_A_PLUS_FEATURE_KEY)["name"], "自由创作 PSD")

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
        self.assertIn("充分向画布内侧收拢", prompt)
        self.assertIn("明显且一致的呼吸空间", prompt)
        self.assertIn("不得显示辅助线、坐标、距离、像素文字、标尺或箭头", prompt)
        self.assertNotIn("距左右边缘至少 54px", prompt)
        self.assertNotIn("距上下边缘至少 90px", prompt)
        self.assertIn("首屏必须是完整的商业主视觉", prompt)
        self.assertIn("参考图只是可选择的素材池，不要求全部出现在首屏", prompt)
        self.assertIn("严禁在首屏中直接堆叠多个产品抠图", prompt)
        self.assertIn("整体采用黑金风格", prompt)
        self.assertIn("最终连续长图只锁定成品宽度 600px", prompt)
        self.assertIn("1800px 只是构图节奏参考", prompt)
        self.assertIn("实际高度按 API 返回图比例等比自适应", prompt)

    def test_generation_canvas_safety_does_not_expose_measurements_to_image_model(self) -> None:
        instruction = site.build_main_image_a_plus_canvas_safety_instruction(
            site.get_main_image_a_plus_layout("desktop_equal"),
            "3:4",
        )

        self.assertNotIn("px", instruction)
        self.assertNotIn("%", instruction)
        self.assertNotIn("0–1000", instruction)
        self.assertNotIn("[", instruction)
        self.assertIn("标尺、辅助线、箭头", instruction)
        self.assertIn("文字排版必须先确定文本框宽度", instruction)
        self.assertIn("较长标题必须降低一个或多个字号层级", instruction)
        self.assertIn("右对齐文字只能对齐到画面内部的统一文字栏", instruction)

    def test_all_generation_prompts_include_the_global_geometry_lock(self) -> None:
        feature = site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        assert feature is not None

        prompt = site.build_prompt(feature, "", site.DEFAULT_ASPECT_RATIO, "")
        jimeng_payload = site.build_jimeng_request_payload("Create a commercial image", "1:1")

        self.assertIn("GLOBAL GEOMETRY LOCK", prompt)
        self.assertIn("Only uniform scaling up or down is allowed", prompt)
        self.assertIn("GLOBAL GEOMETRY LOCK", jimeng_payload["prompt"])
        self.assertIn("aspect ratio", jimeng_payload["prompt"])

    def test_all_a_plus_modes_apply_the_absolute_product_lock(self) -> None:
        layout = site.get_main_image_a_plus_layout("desktop_equal")
        replacements = [
            {
                "id": 1,
                "name": "核心产品",
                "type": "product",
                "regions": [[100, 100, 500, 500]],
            }
        ]
        prompts = [
            site.build_main_image_a_plus_free_prompt("生成 A+", layout),
            site.build_main_image_a_plus_hero_design_prompt("生成 A+", layout),
            site.build_main_image_a_plus_section_prompt("生成 A+", layout, 0),
            site.build_main_image_a_plus_single_test_prompt("生成 A+", layout),
            site.build_main_image_a_plus_template_section_prompt("生成 A+", layout, 0),
            site.build_main_image_a_plus_element_replacement_prompt("生成 A+", layout, replacements),
        ]

        for prompt in prompts:
            self.assertIn("产品绝对锁定规则", prompt)
            self.assertIn("严禁对用户产品进行重绘、改写、再设计", prompt)
            self.assertIn("品牌名、Logo、包装结构、包装图案", prompt)
            self.assertIn("产品只允许作为一个完整、不可编辑的整体", prompt)
            self.assertIn("绝不能调整产品本身", prompt)

        main_feature = site.get_feature_by_key(site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        psd_feature = site.get_feature_by_key(site.AMAZON_A_PLUS_FEATURE_KEY)
        self.assertIn("产品绝对锁定规则", str(main_feature["default_prompt"]))
        self.assertIn("产品绝对锁定规则", str(psd_feature["default_prompt"]))

    def test_free_prompt_hides_desktop_hero_section_distances(self) -> None:
        notes = site.build_main_image_a_plus_layout_notes("desktop_hero", 2)

        self.assertIn("1464×2400px", notes)
        self.assertNotIn("y=0–800px", notes)
        self.assertNotIn("高 800px", notes)
        self.assertNotIn("533px", notes)
        self.assertIn("不按固定像素、固定距离或等高方框划分", notes)
        self.assertIn("禁止内部拆段、逐段生成、后期拼接", notes)

    def test_free_prompt_requires_one_commercial_canvas_without_stitching(self) -> None:
        layout = site.get_main_image_a_plus_layout("mobile_equal")
        prompt = site.build_main_image_a_plus_free_prompt(
            site.build_main_image_a_plus_layout_notes("mobile_equal", 3),
            layout,
        )

        self.assertIn("一次模型生成中直接输出 1 张以 600×1800px 为构图节奏参考", prompt)
        self.assertIn("禁止把画布拆成四段", prompt)
        self.assertIn("禁止调用多次生成后拼接", prompt)
        self.assertIn("统一场景", prompt)
        self.assertIn("主体跨区", prompt)
        self.assertIn("四个内容阶段只负责阅读节奏", prompt)
        self.assertIn("完整返回图按宽度等比缩放", prompt)
        self.assertIn("禁止裁切或拉伸人物、商品、包装、文字、Logo", prompt)
        self.assertIn("禁止增加白边、米色边、黑边", prompt)
        self.assertIn("原图内容层不裁掉任何一个像素", prompt)
        self.assertIn("比例不一致时不生成任何补边区域", prompt)
        self.assertIn("高度不强制改成 1800px", prompt)
        self.assertIn("只挑选一位最清晰、最适合商业展示的模特", prompt)
        self.assertIn("禁止出现第二位模特", prompt)
        self.assertIn("禁止半个字、缺字、断行裁切", prompt)
        self.assertIn("禁止整张缩小搬运", prompt)
        self.assertIn("最多 3 个支撑证据模块", prompt)
        self.assertIn("主文字组总数不得超过 5 个", prompt)
        self.assertIn("后端适配只锁定最终宽度", prompt)
        self.assertIn("最终高度由原生图比例自动决定", prompt)
        self.assertIn("较长标题必须降低一个或多个字号层级", prompt)

    def test_hero_design_prompt_keeps_free_creation_flow_and_strengthens_first_screen(self) -> None:
        layout = site.get_main_image_a_plus_layout("desktop_equal")
        prompt = site.build_main_image_a_plus_hero_design_prompt(
            "突出自然轻盈感",
            layout,
        )

        self.assertIn("自由创作整图直出执行指令", prompt)
        self.assertIn("首屏设计感模式最高优先级执行规则", prompt)
        self.assertIn("只有一个明确视觉中心和一条清晰阅读动线", prompt)
        self.assertIn("高级杂志式的不对称平衡构图", prompt)
        self.assertIn("首屏最多只能出现 3 个独立文字区", prompt)
        self.assertIn("副标题与卖点标签二选一", prompt)
        self.assertIn("主标题最多 2 行", prompt)
        self.assertIn("禁止长段落、三行以上标题、卖点列表", prompt)
        self.assertIn("至少保留 45% 的无文字视觉区域", prompt)
        self.assertIn("不得占据首屏面积的 20% 以上", prompt)
        self.assertIn("其余经核实的卖点放到后续内容阶段或直接省略", prompt)
        self.assertIn("首屏不能成为独立硬边界模块", prompt)
        self.assertIn("不得在画面中显示网格、比例、层级说明", prompt)
        self.assertIn("突出自然轻盈感", prompt)

    def test_mobile_adaptation_prompt_locks_content_and_allows_only_responsive_reflow(self) -> None:
        prompt = site.build_main_image_a_plus_mobile_adaptation_prompt()

        self.assertIn("600×1800px、共 4 个约 600×450 阅读屏的手机端 A+ 长图", prompt)
        self.assertIn("不得新增、删除、替换、改写", prompt)
        self.assertIn("这不是内容重绘，但必须是一次真正的移动端版式重构", prompt)
        self.assertIn("禁止把电脑端整图直接缩窄、压扁、中心裁切", prompt)
        self.assertIn("所有可读文字必须逐字保持原文", prompt)
        self.assertIn("不得根据语义重新撰写相似文案", prompt)
        self.assertIn("桌面横向双栏或多栏模块按语义拆成一个或两个纵向阅读屏", prompt)
        self.assertIn("Before/After、双眼型、步骤图等天然成组内容", prompt)
        self.assertIn("商品盘、长度表、卖点图和教程模块要放大到手机可读尺寸", prompt)
        self.assertIn("左右交替、上下错位和穿插纯背景留白", prompt)
        self.assertIn("摄影窗口可按 photo_recrop_allowed 为手机比例重新取景", prompt)
        self.assertIn("纯背景可以裁，人物、商品、文字、Logo、步骤图和效果图不能裁", prompt)
        self.assertIn("不得相互覆盖有效内容", prompt)
        self.assertIn("不得把所有内容统一缩小来换取完整", prompt)
        self.assertIn("full-bleed background + all foreground elements fully visible", prompt)
        self.assertIn("不能出现白边、黑边、透明条、纯色留白条", prompt)
        self.assertNotIn("[222,20,778,980]", prompt)
        self.assertNotIn("[258,50,742,950]", prompt)
        self.assertNotIn("18–30px", prompt)
        self.assertIn("明显而均衡的内侧呼吸空间", prompt)
        self.assertIn("不得出现安全框、坐标、距离、像素、百分比、标尺、辅助线、箭头", prompt)
        self.assertIn("安全区是硬边界", prompt)
        self.assertIn("禁止拉长边缘像素、镜像复制、拖影或条纹化补边", prompt)
        self.assertIn("禁止对整张图或任何人物、商品、Logo、文字、图片窗口进行非等比压缩、拉伸", prompt)
        self.assertIn("把同一套设计系统翻译成更适合手机浏览的构图", prompt)
        self.assertIn("唯一成品层", prompt)
        self.assertIn("不会二次扩图、生成背景副本、叠加回贴", prompt)

    def test_mobile_adaptation_uses_desktop_as_only_content_source_and_layout_pairs(self) -> None:
        desktop_source = image_data_url(Image.new("RGB", (1464, 2400), "navy"))
        generated = image_data_url(Image.new("RGB", (100, 400), "green"))
        job_context = {
            "model": site.NANO_BANANA_MODEL,
            "main_image_a_plus_desktop_source": desktop_source,
        }

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={"images": [generated], "text": ""},
            ) as request_images,
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                return_value=passed_quality_review(),
            ) as review_candidate,
            patch.object(
                site,
                "analyze_main_image_a_plus_mobile_element_inventory",
                return_value=[
                    {
                        "name": "品牌 Logo",
                        "description": "中心 Logo",
                        "count": 1,
                        "regions": [[220, 120, 780, 260]],
                    },
                ],
            ),
        ):
            result = site.run_main_image_a_plus_mobile_adaptation_job(job_context)

        request_images.assert_called_once()
        call_kwargs = request_images.call_args.kwargs
        self.assertEqual(len(call_kwargs["uploaded_files"]), 7)
        self.assertTrue(
            str(call_kwargs["uploaded_files"][0]["name"]).startswith(
                "desktop_a_plus_reference"
            )
        )
        self.assertTrue(
            all(
                str(item["name"]).startswith("layout_example_")
                for item in call_kwargs["uploaded_files"][1:]
            )
        )
        self.assertEqual(call_kwargs["aspect_ratio"], "1:4")
        self.assertEqual(call_kwargs["resolution"], "4K")
        self.assertEqual(call_kwargs["max_attempts"], 1)
        self.assertIn("不得新增、删除、替换、改写", call_kwargs["prompt"])
        self.assertIn("电脑端元素清单", call_kwargs["prompt"])
        self.assertIn("品牌 Logo", call_kwargs["prompt"])
        self.assertIn("手机端安全边距硬规则", call_kwargs["prompt"])
        self.assertIn("动态规划安全边距", call_kwargs["prompt"])
        self.assertIn("第 1 张是本次待适配的电脑版 A+", call_kwargs["prompt"])
        self.assertIn("只用于学习如何拆解横向模块", call_kwargs["prompt"])
        self.assertIn("不会二次扩图、生成背景副本、叠加回贴", call_kwargs["prompt"])
        self.assertIn("不会二次扩图", call_kwargs["prompt"])
        self.assertNotIn("[60,40,940,960]", call_kwargs["prompt"])
        self.assertEqual(result["mobile_adaptation_source"], desktop_source)
        self.assertEqual(result["main_image_a_plus_mode"], site.MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT)
        self.assertEqual(result["target_size"], (600, 1800))
        self.assertEqual(result["mobile_generation_attempts"], 1)
        self.assertEqual(result["mobile_screen_count"], 4)
        self.assertEqual(result["mobile_reference_pair_count"], 3)
        self.assertEqual(result["prepared_reference_count"], 7)
        self.assertEqual(result["mobile_element_inventory_count"], 1)
        self.assertEqual(result["section_count"], 1)
        self.assertEqual(result["section_heights"], (1800,))
        self.assertEqual(result["requested_aspect_ratios"], ("1:4",))
        self.assertEqual(result["mobile_foreground_fit"], "single_layer_exact_size")
        self.assertEqual(result["mobile_background_fill"], "none")
        self.assertEqual(result["mobile_outpaint_section_count"], 0)
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (600, 1800))

    def test_mobile_adaptation_repairs_first_candidate_and_blocks_failed_result(self) -> None:
        desktop_source = image_data_url(Image.new("RGB", (1464, 2400), "navy"))
        first_candidate = image_data_url(Image.new("RGB", (600, 1800), "red"))
        repaired_candidate = image_data_url(Image.new("RGB", (600, 1800), "green"))
        first_review = {
            "reviewed": True,
            "passed": False,
            "quality_score": 9.0,
            "critical_issue_count": 2,
            "cropped_or_edge_touching_text": [],
            "clipped_foreground": [],
            "missing_elements": ["底部 Logo 缺失"],
            "duplicated_elements": [],
            "text_mismatches": ["主标题拼写不一致"],
            "layout_issues": [],
            "retry_instruction": "恢复 Logo 并纠正标题",
        }
        repaired_review = {
            "reviewed": True,
            "passed": False,
            "quality_score": 7.0,
            "critical_issue_count": 1,
            "cropped_or_edge_touching_text": ["底部参数行仍略贴边"],
            "clipped_foreground": [],
            "missing_elements": [],
            "duplicated_elements": [],
            "text_mismatches": [],
            "layout_issues": [],
            "retry_instruction": "底部参数行继续上移",
        }

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                side_effect=[
                    {"images": [first_candidate], "text": ""},
                    {"images": [repaired_candidate], "text": ""},
                ],
            ) as request_images,
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                side_effect=[first_review, repaired_review],
            ),
            patch.object(
                site,
                "analyze_main_image_a_plus_mobile_element_inventory",
                return_value=[
                    {
                        "name": "品牌 Logo",
                        "description": "底部 Logo",
                        "count": 1,
                        "regions": [[220, 820, 780, 940]],
                    },
                ],
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "本次结果已拦截"):
                site.run_main_image_a_plus_mobile_adaptation_job(
                    {
                        "model": site.NANO_BANANA_MODEL,
                        "main_image_a_plus_desktop_source": desktop_source,
                    }
                )

        self.assertEqual(request_images.call_count, 2)
        first_call = request_images.call_args_list[0].kwargs
        repair_call = request_images.call_args_list[1].kwargs
        self.assertEqual(len(first_call["uploaded_files"]), 7)
        self.assertEqual(len(repair_call["uploaded_files"]), 2)
        self.assertIn("第 1 张是电脑版原稿", repair_call["prompt"])
        self.assertIn("第 2 张是上一轮生成的手机版候选", repair_call["prompt"])
        self.assertIn("恢复 Logo 并纠正标题", repair_call["prompt"])
        self.assertTrue(
            str(repair_call["uploaded_files"][1]["name"]).startswith(
                "mobile_candidate_attempt_1"
            )
        )
    def test_mobile_inventory_is_built_before_generation_and_keeps_small_elements(self) -> None:
        source = image_uploaded_input(Image.new("RGB", (1464, 2400), "white"))
        inventory_json = json.dumps(
            {
                "elements": [
                    {
                        "name": "Adapt to Your Skin Tone 卖点",
                        "type": "text",
                        "count": 1,
                        "description": "完整英文卖点",
                        "verbatim_text": "Adapt to Your Skin Tone",
                        "reading_order": 1,
                        "regions": [[80, 120, 420, 190]],
                    },
                    {
                        "name": "模特手腕上的手链",
                        "type": "accessory",
                        "count": 1,
                        "description": "人物配件",
                        "reading_order": 2,
                        "regions": [[610, 280, 720, 360]],
                    },
                    {
                        "name": "右下角干花束",
                        "type": "decoration",
                        "count": 1,
                        "description": "背景小装饰",
                        "reading_order": 3,
                        "regions": [[760, 760, 940, 930]],
                    },
                ]
            },
            ensure_ascii=False,
        )

        with patch.object(
            site,
            "call_openrouter",
            return_value={"text": inventory_json},
        ) as analyze:
            elements = site.analyze_main_image_a_plus_mobile_element_inventory(source)

        self.assertEqual(len(elements), 3)
        self.assertEqual(elements[0]["name"], "Adapt to Your Skin Tone 卖点")
        self.assertEqual(elements[1]["name"], "模特手腕上的手链")
        self.assertEqual(elements[2]["name"], "右下角干花束")
        self.assertEqual(elements[0]["regions"], [[80, 120, 420, 190]])
        self.assertEqual(elements[0]["verbatim_text"], "Adapt to Your Skin Tone")
        self.assertEqual(elements[0]["reading_order"], 1)
        formatted_inventory = site.format_main_image_a_plus_mobile_element_inventory(elements)
        self.assertIn("阅读顺序 1", formatted_inventory)
        self.assertIn('逐字锁定原文="Adapt to Your Skin Tone"', formatted_inventory)
        analysis_prompt = analyze.call_args.kwargs["prompt"]
        self.assertIn("不得忽略画布四角、边缘、底部或背景中的小元素", analysis_prompt)
        self.assertIn("完整外接框 regions", analysis_prompt)
        self.assertIn("verbatim_text 中逐字转录原文", analysis_prompt)
        self.assertIn("reading_order", analysis_prompt)

    def test_feature_job_routes_mobile_adaptation_before_upload_validation(self) -> None:
        job_context = {
            "feature": {"key": site.MAIN_IMAGE_A_PLUS_FEATURE_KEY, "name": "主图生A+"},
            "model": site.NANO_BANANA_MODEL,
            "prompt": "",
            "uploaded_files": [],
            "main_image_a_plus_adapt_mobile": True,
            "main_image_a_plus_desktop_source": "data:image/png;base64,source",
            "account_name": "tester",
        }
        mobile_result = {"images": ["data:image/png;base64,result"]}

        with (
            patch.object(
                site,
                "run_main_image_a_plus_mobile_adaptation_job",
                return_value=mobile_result,
            ) as run_mobile,
            patch.object(
                site,
                "finalize_feature_job_result",
                side_effect=lambda _context, result, _job_id: result,
            ),
        ):
            result = site.run_feature_job(job_context)

        run_mobile.assert_called_once_with(job_context)
        self.assertEqual(result, mobile_result)

    def test_mobile_canvas_detection_skips_existing_mobile_history_results(self) -> None:
        mobile = image_data_url(Image.new("RGB", (600, 1800), "green"))
        five_screen_mobile = image_data_url(Image.new("RGB", (600, 2250), "green"))
        mobile_thumbnail = image_data_url(Image.new("RGB", (120, 360), "green"))
        five_screen_thumbnail = image_data_url(Image.new("RGB", (120, 450), "green"))
        desktop = image_data_url(Image.new("RGB", (1464, 2400), "green"))

        self.assertTrue(site.is_main_image_a_plus_mobile_canvas(mobile))
        self.assertTrue(site.is_main_image_a_plus_mobile_canvas(five_screen_mobile))
        self.assertTrue(site.is_main_image_a_plus_mobile_canvas(mobile_thumbnail))
        self.assertTrue(site.is_main_image_a_plus_mobile_canvas(five_screen_thumbnail))
        self.assertFalse(site.is_main_image_a_plus_mobile_canvas(desktop))

    def test_mobile_adaptation_submitter_accepts_a_history_image_source(self) -> None:
        source = r"D:\history\desktop-a-plus.png"
        queued = {"job_id": "mobile-job", "status": "queued"}

        with (
            patch.object(site, "st") as streamlit,
            patch.object(site, "submit_feature_job", return_value=queued) as submit_job,
        ):
            streamlit.session_state.get.return_value = "history-user"
            result = site.submit_main_image_a_plus_mobile_adaptation(source)

        self.assertEqual(result, queued)
        submit_job.assert_called_once()
        feature_arg, context_arg = submit_job.call_args.args
        self.assertEqual(feature_arg["key"], site.MAIN_IMAGE_A_PLUS_FEATURE_KEY)
        self.assertTrue(context_arg["main_image_a_plus_adapt_mobile"])
        self.assertEqual(context_arg["main_image_a_plus_desktop_source"], source)
        self.assertEqual(context_arg["account_name"], "history-user")

    def test_hero_design_job_reuses_single_pass_free_creation_pipeline(self) -> None:
        source = Image.new("RGB", (200, 300), "white")
        layout = site.get_main_image_a_plus_layout("mobile_equal")
        with patch.object(
            site,
            "call_openrouter_images_api",
            return_value={"images": [image_data_url(source)], "text": ""},
        ) as request_images, patch.object(
            site,
            "review_main_image_a_plus_candidate",
            return_value=passed_quality_review(),
        ):
            result = site.run_main_image_a_plus_job(
                {
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "生成更有设计感的首屏",
                    "uploaded_files": [{"name": "main.png", "data": b"image"}],
                    "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN,
                    "main_image_a_plus_layout": layout,
                }
            )

        request_images.assert_called_once()
        call_kwargs = request_images.call_args.kwargs
        self.assertEqual(call_kwargs["aspect_ratio"], "1:4")
        self.assertEqual(call_kwargs["resolution"], "4K")
        self.assertEqual(call_kwargs["max_attempts"], 1)
        self.assertIn("首屏设计感模式最高优先级执行规则", call_kwargs["prompt"])
        self.assertIn("禁止机械左右对半", call_kwargs["prompt"])
        self.assertEqual(result["main_image_a_plus_mode"], site.MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN)
        self.assertEqual(result["section_count"], 1)
        self.assertIn("首屏设计感整图直出", result["channel"])
        self.assertIn("没有执行图片拼接", result["text"])
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (600, 900))
        self.assertEqual(result["requested_target_size"], (600, 1800))
        self.assertEqual(result["target_size"], (600, 900))

    def test_free_aspect_ratio_preserves_complete_horizontal_canvas(self) -> None:
        self.assertEqual(
            site.select_main_image_a_plus_safe_aspect_ratio((600, 1800)),
            "1:4",
        )
        self.assertEqual(
            site.select_main_image_a_plus_safe_aspect_ratio((1464, 2400)),
            "9:16",
        )
        self.assertEqual(
            site.select_main_image_a_plus_vertical_preserving_aspect_ratio((600, 1800)),
            "1:4",
        )
        self.assertEqual(
            site.select_main_image_a_plus_vertical_preserving_aspect_ratio((600, 2250)),
            "1:4",
        )
        self.assertEqual(
            site.select_main_image_a_plus_vertical_preserving_aspect_ratio((600, 2700)),
            "1:8",
        )

    def test_native_safe_zones_disable_crop_and_use_stricter_text_box(self) -> None:
        mobile_layout = site.get_main_image_a_plus_layout("mobile_equal")
        mobile_zones = site.get_main_image_a_plus_native_safe_zones(mobile_layout, "1:4")

        self.assertEqual(mobile_zones["crop_x_percent"], 0.0)
        self.assertEqual(mobile_zones["crop_y_percent"], 0.0)
        self.assertEqual(mobile_zones["extension_x_percent"], 0.0)
        self.assertEqual(mobile_zones["extension_y_percent"], 0.0)
        self.assertEqual(mobile_zones["final_text_margin_x"], 54)
        self.assertEqual(mobile_zones["final_text_margin_y"], 90)
        self.assertGreater(mobile_zones["text_box"][0], mobile_zones["foreground_box"][0])
        self.assertGreater(mobile_zones["text_box"][1], mobile_zones["foreground_box"][1])
        self.assertLess(mobile_zones["text_box"][2], mobile_zones["foreground_box"][2])
        self.assertLess(mobile_zones["text_box"][3], mobile_zones["foreground_box"][3])

        desktop_layout = site.get_main_image_a_plus_layout("desktop_equal")
        desktop_zones = site.get_main_image_a_plus_native_safe_zones(desktop_layout, "9:16")
        self.assertEqual(desktop_zones["crop_x_percent"], 0.0)
        self.assertEqual(desktop_zones["crop_y_percent"], 0.0)
        self.assertEqual(desktop_zones["extension_x_percent"], 0.0)
        self.assertEqual(desktop_zones["extension_y_percent"], 0.0)
        self.assertGreater(desktop_zones["text_box"][0], desktop_zones["foreground_box"][0])
        self.assertGreater(desktop_zones["text_box"][1], desktop_zones["foreground_box"][1])
        self.assertLess(desktop_zones["text_box"][2], desktop_zones["foreground_box"][2])
        self.assertLess(desktop_zones["text_box"][3], desktop_zones["foreground_box"][3])

        adaptation_layout = site.get_main_image_a_plus_mobile_layout_for_source((1464, 2400))
        adaptation_zones = site.get_main_image_a_plus_native_safe_zones(
            adaptation_layout,
            "1:4",
        )
        self.assertEqual(adaptation_zones["crop_x_percent"], 0.0)
        self.assertEqual(adaptation_zones["crop_y_percent"], 0.0)
        self.assertEqual(adaptation_zones["extension_x_percent"], 0.0)
        self.assertEqual(adaptation_zones["extension_y_percent"], 0.0)
        self.assertGreater(adaptation_zones["text_box"][0], adaptation_zones["foreground_box"][0])
        self.assertGreater(adaptation_zones["text_box"][1], adaptation_zones["foreground_box"][1])
        self.assertLess(adaptation_zones["text_box"][2], adaptation_zones["foreground_box"][2])
        self.assertLess(adaptation_zones["text_box"][3], adaptation_zones["foreground_box"][3])

    def test_free_generation_retries_after_quality_gate_rejects_edge_clipping(self) -> None:
        first_candidate = image_data_url(Image.new("RGB", (200, 300), "red"))
        second_candidate = image_data_url(Image.new("RGB", (200, 300), "green"))
        rejected_review = {
            "reviewed": True,
            "passed": False,
            "quality_score": 5.0,
            "critical_issue_count": 1,
            "cropped_or_edge_touching_text": ["右侧标题末字贴边并被截断"],
            "clipped_foreground": [],
            "missing_elements": [],
            "duplicated_elements": [],
            "text_mismatches": [],
            "layout_issues": ["层级偏弱"],
            "retry_instruction": "把标题向内移动并加强主次层级",
        }
        layout = site.get_main_image_a_plus_layout("desktop_equal")

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                side_effect=[
                    {"images": [first_candidate], "text": ""},
                    {"images": [second_candidate], "text": ""},
                ],
            ) as request_images,
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                side_effect=[rejected_review, passed_quality_review()],
            ) as review_candidate,
        ):
            result = site.run_main_image_a_plus_job(
                {
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "生成高设计感 A+",
                    "uploaded_files": [{"name": "main.png", "data": b"image"}],
                    "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                    "main_image_a_plus_layout": layout,
                }
            )

        self.assertEqual(request_images.call_count, 2)
        self.assertEqual(review_candidate.call_count, 2)
        self.assertIn("上一候选已被成品质检拦截", request_images.call_args_list[1].kwargs["prompt"])
        self.assertIn("右侧标题末字贴边并被截断", request_images.call_args_list[1].kwargs["prompt"])
        self.assertIn("定向修复任务", request_images.call_args_list[1].kwargs["prompt"])
        self.assertIn("商业设计感和内容丰富度不足", request_images.call_args_list[1].kwargs["prompt"])
        self.assertIn("半透明材质面、投影、高光反射", request_images.call_args_list[1].kwargs["prompt"])
        repair_inputs = request_images.call_args_list[1].kwargs["uploaded_files"]
        self.assertEqual(len(repair_inputs), 2)
        self.assertIn("a_plus_failed_candidate", str(repair_inputs[0]["name"]))
        self.assertEqual(result["generation_attempts"], 2)
        self.assertEqual(result["quality_repair_attempts"], 1)
        self.assertTrue(result["quality_review_passed"])
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.getpixel((output.width // 2, output.height // 2)), (0, 128, 0))

    def test_free_generation_can_apply_two_targeted_repairs_to_the_best_candidate(self) -> None:
        first_candidate = image_data_url(Image.new("RGB", (200, 300), "red"))
        second_candidate = image_data_url(Image.new("RGB", (200, 300), "yellow"))
        third_candidate = image_data_url(Image.new("RGB", (200, 300), "green"))
        first_review = {
            "reviewed": True,
            "passed": False,
            "quality_score": 5.0,
            "critical_issue_count": 1,
            "cropped_or_edge_touching_text": [],
            "clipped_foreground": ["模特头顶被截切"],
            "missing_elements": [],
            "duplicated_elements": [],
            "text_mismatches": [],
            "layout_issues": ["主焦点分散"],
            "retry_instruction": "缩小模特并向内移动",
        }
        second_review = {
            "reviewed": True,
            "passed": False,
            "quality_score": 6.5,
            "critical_issue_count": 0,
            "cropped_or_edge_touching_text": [],
            "clipped_foreground": [],
            "missing_elements": [],
            "duplicated_elements": [],
            "text_mismatches": [],
            "layout_issues": ["网格系统不清晰"],
            "retry_instruction": "统一对齐线和模块间距",
        }

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                side_effect=[
                    {"images": [first_candidate], "text": ""},
                    {"images": [second_candidate], "text": ""},
                    {"images": [third_candidate], "text": ""},
                ],
            ) as request_images,
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                side_effect=[first_review, second_review, passed_quality_review()],
            ),
        ):
            result = site.run_main_image_a_plus_job(
                {
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "生成高设计感 A+",
                    "uploaded_files": [{"name": "main.png", "data": b"image"}],
                    "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                    "main_image_a_plus_layout": site.get_main_image_a_plus_layout(
                        "desktop_equal"
                    ),
                }
            )

        self.assertEqual(request_images.call_count, 3)
        self.assertIn("模特头顶被截切", request_images.call_args_list[1].kwargs["prompt"])
        self.assertIn("网格系统不清晰", request_images.call_args_list[2].kwargs["prompt"])
        self.assertTrue(
            all(
                "a_plus_failed_candidate"
                in str(request_images.call_args_list[index].kwargs["uploaded_files"][0]["name"])
                for index in (1, 2)
            )
        )
        self.assertEqual(result["generation_attempts"], 3)
        self.assertEqual(result["quality_repair_attempts"], 2)
        self.assertTrue(result["quality_review_passed"])
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.getpixel((output.width // 2, output.height // 2)), (0, 128, 0))

    def test_free_generation_returns_editable_preview_for_text_only_quality_issues(self) -> None:
        candidate = image_data_url(Image.new("RGB", (200, 300), "orange"))
        text_only_review = {
            "reviewed": True,
            "passed": False,
            "quality_score": 6.8,
            "critical_issue_count": 1,
            "cropped_or_edge_touching_text": ["底部收尾文案边距不足"],
            "clipped_foreground": [],
            "missing_elements": [],
            "duplicated_elements": [],
            "text_mismatches": [],
            "layout_issues": ["底部信息略显拥挤"],
            "retry_instruction": "删除虚构收尾文案并增加底部留白",
        }

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={"images": [candidate], "text": ""},
            ) as request_images,
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                return_value=text_only_review,
            ),
        ):
            result = site.run_main_image_a_plus_job(
                {
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "生成高设计感 A+",
                    "uploaded_files": [{"name": "main.png", "data": b"image"}],
                    "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                    "main_image_a_plus_layout": site.get_main_image_a_plus_layout(
                        "desktop_equal"
                    ),
                }
            )

        self.assertEqual(request_images.call_count, 4)
        self.assertEqual(result["generation_attempts"], 4)
        self.assertEqual(result["quality_repair_attempts"], 3)
        self.assertFalse(result["quality_review_passed"])
        self.assertEqual(result["quality_delivery_status"], "needs_review")
        self.assertEqual(result["quality_critical_issue_count"], 1)
        self.assertIn("底部收尾文案边距不足", result["quality_review_issues"])
        self.assertIn("可编辑预览", result["text"])
        self.assertIn(
            "禁止新增 Thank you",
            request_images.call_args_list[-1].kwargs["prompt"],
        )

    def test_quality_review_forces_failure_when_candidate_has_clipped_text(self) -> None:
        candidate = image_data_url(Image.new("RGB", (600, 1800), "white"))
        review_json = json.dumps(
            {
                "composition_score": 8,
                "mobile_layout_score": 8,
                "cropped_or_edge_touching_text": ["底部参数行被画布截断"],
                "clipped_foreground": [],
                "missing_elements": [],
                "duplicated_elements": [],
                "text_mismatches": [],
                "layout_issues": [],
                "passed": "true",
                "retry_instruction": "将底部参数组整体上移",
            },
            ensure_ascii=False,
        )

        with patch.object(site, "call_openrouter", return_value={"text": review_json}) as review_api:
            review = site.review_main_image_a_plus_candidate(
                candidate,
                site.get_main_image_a_plus_layout("mobile_equal"),
                site.MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT,
                source_inputs=[image_uploaded_input(Image.new("RGB", (1464, 2400), "gray"))],
                expected_element_inventory="1. 底部参数行",
            )

        self.assertTrue(review["reviewed"])
        self.assertFalse(review["passed"])
        self.assertEqual(review["critical_issue_count"], 1)
        self.assertEqual(len(review_api.call_args.kwargs["uploaded_files"]), 2)
        self.assertIn("距最终画布左右至少 54px、上下至少 90px", review_api.call_args.kwargs["prompt"])
        self.assertIn("电脑端最低元素清单", review_api.call_args.kwargs["prompt"])
        self.assertIn("必须区分‘专业摄影出血’与‘意外截断’", review_api.call_args.kwargs["prompt"])
        self.assertIn("发梢、肩臂或躯干出画", review_api.call_args.kwargs["prompt"])
        self.assertIn("诸如 96px、132px 的制作标注", review_api.call_args.kwargs["prompt"])

    def test_outer_blank_border_detector_flags_white_frame(self) -> None:
        framed = Image.new("RGB", (600, 900), "white")
        ImageDraw.Draw(framed).rectangle((18, 18, 581, 881), fill=(214, 174, 126))
        output = io.BytesIO()
        framed.save(output, format="PNG")

        issues = site.detect_main_image_a_plus_outer_blank_borders(output.getvalue())

        self.assertTrue(any("左侧" in issue for issue in issues))
        self.assertTrue(any("右侧" in issue for issue in issues))
        self.assertTrue(any("顶部" in issue for issue in issues))
        self.assertTrue(any("底部" in issue for issue in issues))

    def test_outer_blank_border_detector_allows_full_bleed_light_background(self) -> None:
        full_bleed = Image.new("RGB", (600, 900), (250, 247, 240))
        output = io.BytesIO()
        full_bleed.save(output, format="PNG")

        self.assertEqual(
            site.detect_main_image_a_plus_outer_blank_borders(output.getvalue()),
            [],
        )

    def test_strict_quality_rejects_flat_layout_and_production_marks(self) -> None:
        candidate = image_data_url(Image.new("RGB", (600, 900), "beige"))
        review_json = json.dumps(
            {
                "composition_score": 8.8,
                "depth_score": 5.5,
                "content_richness_score": 7.5,
                "commercial_design_score": 4.8,
                "mobile_layout_score": 8.8,
                "cropped_or_edge_touching_text": [],
                "clipped_foreground": [],
                "missing_elements": [],
                "duplicated_elements": [],
                "text_mismatches": [],
                "technical_artifacts": ["顶部出现尺寸箭头"],
                "outer_border_issues": [],
                "layout_issues": ["同尺寸浅色圆角卡片机械堆叠"],
                "passed": True,
                "retry_instruction": "删除标注并重建前中后景",
            },
            ensure_ascii=False,
        )

        with patch.object(site, "call_openrouter", return_value={"text": review_json}):
            review = site.review_main_image_a_plus_candidate(
                candidate,
                site.get_main_image_a_plus_layout("desktop_equal"),
                site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                strict_visual_quality=True,
            )

        self.assertFalse(review["passed"])
        self.assertEqual(review["quality_score"], 4.8)
        self.assertEqual(review["commercial_design_score"], 4.8)
        self.assertEqual(review["critical_issue_count"], 2)

    def test_strict_quality_checks_all_sources_and_rejects_invented_elements(self) -> None:
        candidate = image_data_url(Image.new("RGB", (600, 900), "beige"))
        sources = [
            image_uploaded_input(Image.new("RGB", (300, 300), (index * 30, 80, 120)))
            for index in range(1, 6)
        ]
        review_json = json.dumps(
            {
                "composition_score": 9,
                "depth_score": 9,
                "mobile_layout_score": 9,
                "cropped_or_edge_touching_text": [],
                "clipped_foreground": [],
                "missing_elements": [],
                "duplicated_elements": [],
                "invented_elements": ["右下角新增了源图不存在的胶水瓶"],
                "text_mismatches": [],
                "technical_artifacts": [],
                "outer_border_issues": [],
                "layout_issues": [],
                "passed": True,
                "retry_instruction": "删除新增胶水瓶",
            },
            ensure_ascii=False,
        )

        with patch.object(
            site,
            "call_openrouter",
            return_value={"text": review_json},
        ) as review_api:
            review = site.review_main_image_a_plus_candidate(
                candidate,
                site.get_main_image_a_plus_layout("desktop_equal"),
                site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                source_inputs=sources,
                strict_visual_quality=True,
            )

        self.assertEqual(len(review_api.call_args.kwargs["uploaded_files"]), 6)
        self.assertIn("任何源图中不存在", review_api.call_args.kwargs["prompt"])
        self.assertIn("commercial_design_score", review_api.call_args.kwargs["prompt"])
        self.assertIn("至少四组真实证据", review_api.call_args.kwargs["prompt"])
        self.assertEqual(review["invented_elements"], ["右下角新增了源图不存在的胶水瓶"])
        self.assertFalse(review["passed"])
        self.assertEqual(review["critical_issue_count"], 1)

    def test_plain_title_is_not_misreported_as_severe_subject_clipping(self) -> None:
        review = {
            "clipped_foreground": [
                "Newcally Lash: Your Ultimate Lash Collection",
                "模特头顶被截断",
            ]
        }

        self.assertEqual(
            site.collect_main_image_a_plus_severe_subject_clips(review),
            ["模特头顶被截断"],
        )

    def test_quality_review_ignores_hair_only_photographic_bleed(self) -> None:
        candidate = image_data_url(Image.new("RGB", (600, 900), "beige"))
        review_json = json.dumps(
            {
                "composition_score": 9,
                "depth_score": 9,
                "mobile_layout_score": 9,
                "cropped_or_edge_touching_text": [],
                "clipped_foreground": ["左侧模特头发自然出画"],
                "missing_elements": [],
                "duplicated_elements": [],
                "text_mismatches": [],
                "technical_artifacts": [],
                "outer_border_issues": [],
                "layout_issues": [],
                "passed": False,
                "retry_instruction": "缩小模特",
            },
            ensure_ascii=False,
        )

        with patch.object(site, "call_openrouter", return_value={"text": review_json}):
            review = site.review_main_image_a_plus_candidate(
                candidate,
                site.get_main_image_a_plus_layout("desktop_equal"),
                site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                strict_visual_quality=True,
            )

        self.assertEqual(review["clipped_foreground"], [])
        self.assertTrue(review["passed"])

    def test_strict_last_attempt_restores_best_candidate_after_safe_rebuild(self) -> None:
        candidate = image_data_url(Image.new("RGB", (200, 300), "orange"))
        rejected_review = {
            "reviewed": True,
            "passed": False,
            "quality_score": 6.0,
            "critical_issue_count": 1,
            "cropped_or_edge_touching_text": [],
            "clipped_foreground": ["右侧产品包装的右边部分被画布切断"],
            "missing_elements": [],
            "duplicated_elements": [],
            "text_mismatches": [],
            "technical_artifacts": [],
            "outer_border_issues": [],
            "layout_issues": [],
            "retry_instruction": "缩小并内移右侧商品组",
        }
        source = {"name": "main.png", "data": b"image", "type": "image/png"}
        reports = [
            {
                "image_index": 1,
                "status": "complete",
                "asset_role": "raw_asset",
                "confidence": 0.99,
            }
        ]

        with (
            patch.object(
                site,
                "prepare_main_image_a_plus_sources_with_repair",
                return_value=([source], reports, 0, []),
            ),
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={"images": [candidate], "text": ""},
            ) as request_images,
            patch.object(
                site,
                "cover_image_to_exact_size",
                return_value=candidate,
            ),
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                return_value=rejected_review,
            ),
        ):
            result = site.run_main_image_a_plus_job(
                {
                    "feature": {"key": site.A_PLUS_REFERENCE_LAB_FEATURE_KEY},
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "生成 A+测试图",
                    "uploaded_files": [source],
                    "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                    "main_image_a_plus_layout": site.get_main_image_a_plus_layout(
                        "desktop_equal"
                    ),
                }
            )

        self.assertEqual(request_images.call_count, 4)
        self.assertIn(
            "最后一轮安全构图重建",
            request_images.call_args_list[-1].kwargs["prompt"],
        )
        self.assertEqual(
            request_images.call_args_list[-1].kwargs["uploaded_files"][0]["name"],
            "main.png",
        )
        self.assertNotIn(
            "a_plus_failed_candidate",
            str(request_images.call_args_list[-1].kwargs["uploaded_files"][0]["name"]),
        )
        self.assertEqual(result["quality_delivery_status"], "needs_review")
        self.assertTrue(result["quality_result_restored"])
        self.assertEqual(
            result["quality_severe_subject_risks"],
            ["右侧产品包装的右边部分被画布切断"],
        )

    def test_lab_restores_generated_candidate_when_quality_review_is_unavailable(self) -> None:
        candidate = image_data_url(Image.new("RGB", (200, 300), "orange"))
        source = {"name": "main.png", "data": b"image", "type": "image/png"}
        reports = [
            {
                "image_index": 1,
                "status": "complete",
                "asset_role": "raw_asset",
                "confidence": 0.99,
            }
        ]
        unavailable_review = {
            "reviewed": False,
            "passed": False,
            "quality_score": 0.0,
            "critical_issue_count": 1,
            "layout_issues": ["成品质检未完成"],
            "retry_instruction": "",
        }

        with (
            patch.object(
                site,
                "prepare_main_image_a_plus_sources_with_repair",
                return_value=([source], reports, 0, []),
            ),
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={"images": [candidate], "text": ""},
            ) as request_images,
            patch.object(site, "cover_image_to_exact_size", return_value=candidate),
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                return_value=unavailable_review,
            ),
        ):
            result = site.run_main_image_a_plus_job(
                {
                    "feature": {"key": site.A_PLUS_REFERENCE_LAB_FEATURE_KEY},
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "生成 A+测试图",
                    "uploaded_files": [source],
                    "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                    "main_image_a_plus_layout": site.get_main_image_a_plus_layout(
                        "desktop_equal"
                    ),
                }
            )

        self.assertEqual(request_images.call_count, 1)
        self.assertFalse(result["quality_reviewed"])
        self.assertEqual(result["quality_delivery_status"], "needs_review")
        self.assertTrue(result["quality_result_restored"])
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (1464, 2196))
            self.assertEqual(output.getpixel((732, 1098)), (255, 165, 0))

    def test_designed_module_review_treats_invented_copy_as_critical(self) -> None:
        candidate = image_data_url(Image.new("RGB", (1464, 2400), "white"))
        review_json = json.dumps(
            {
                "composition_score": 8,
                "mobile_layout_score": 8,
                "cropped_or_edge_touching_text": [],
                "clipped_foreground": [],
                "missing_elements": [],
                "duplicated_elements": [],
                "text_mismatches": [
                    "新增了源图不存在的品牌口号",
                    "mismatched_text_in_section_6",
                ],
                "layout_issues": [],
                "passed": True,
                "retry_instruction": "删除新增口号",
            },
            ensure_ascii=False,
        )

        with patch.object(site, "call_openrouter", return_value={"text": review_json}) as review_api:
            review = site.review_main_image_a_plus_candidate(
                candidate,
                site.get_main_image_a_plus_layout("desktop_equal"),
                site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                source_inputs=[image_uploaded_input(Image.new("RGB", (300, 300), "gray"))],
                designed_module_pipeline=True,
                expected_section_count=3,
            )

        self.assertFalse(review["passed"])
        self.assertEqual(review["critical_issue_count"], 1)
        self.assertEqual(review["text_mismatches"], ["新增了源图不存在的品牌口号"])
        self.assertIn("一对一分区重构", review_api.call_args.kwargs["prompt"])
        self.assertIn("不要仅因存在分区就判为拼贴", review_api.call_args.kwargs["prompt"])

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

    def test_exact_resize_keeps_content_proportions_without_stretching(self) -> None:
        source = Image.new("RGB", (300, 100), "black")
        draw = ImageDraw.Draw(source)
        draw.rectangle((130, 30, 169, 69), fill="red")

        result_url = site.resize_image_to_exact_size(image_data_url(source), 100, 100)

        with open_data_url(result_url) as result:
            self.assertEqual(result.size, (100, 100))
            red_pixels = [
                (x, y)
                for y in range(result.height)
                for x in range(result.width)
                if result.getpixel((x, y))[0] > 150
                and result.getpixel((x, y))[1] < 80
                and result.getpixel((x, y))[2] < 80
            ]
            self.assertTrue(red_pixels)
            red_width = max(x for x, _y in red_pixels) - min(x for x, _y in red_pixels) + 1
            red_height = max(y for _x, y in red_pixels) - min(y for _x, y in red_pixels) + 1
            self.assertLessEqual(abs(red_width - red_height), 1)

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

    def test_job_uses_ten_references_native_4k_and_width_locked_output(self) -> None:
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
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                return_value=passed_quality_review(),
            ),
            patch.object(site, "stitch_main_image_a_plus_sections") as stitch_sections,
            patch.object(site, "finalize_feature_job_result", side_effect=lambda _context, result, _job_id: result),
        ):
            result = site.run_feature_job(job_context)

        request_images.assert_called_once()
        stitch_sections.assert_not_called()
        call_kwargs = request_images.call_args.kwargs
        self.assertEqual(len(call_kwargs["uploaded_files"]), 10)
        self.assertEqual(call_kwargs["aspect_ratio"], "9:16")
        self.assertEqual(call_kwargs["resolution"], "4K")
        self.assertEqual(call_kwargs["max_attempts"], 1)
        self.assertIn("自由创作整图直出执行指令", call_kwargs["prompt"])
        self.assertIn("禁止把画布拆成四段", call_kwargs["prompt"])
        self.assertIn("只挑选一位最清晰、最适合商业展示的模特", call_kwargs["prompt"])
        self.assertIn("禁止出现第二位模特", call_kwargs["prompt"])
        self.assertIn("不能遮挡模特", call_kwargs["prompt"])
        self.assertIn("完整返回图按宽度等比缩放", call_kwargs["prompt"])
        self.assertIn("比例不一致时不生成任何补边区域", call_kwargs["prompt"])
        self.assertIn("禁止裁切或拉伸人物、商品、包装、文字、Logo", call_kwargs["prompt"])
        self.assertIn("禁止增加白边、米色边、黑边", call_kwargs["prompt"])
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (1464, 2196))
        self.assertEqual(result["section_count"], 1)
        self.assertEqual(result["target_size"], (1464, 2196))
        self.assertEqual(result["requested_target_size"], (1464, 2400))
        self.assertEqual(result["section_height"], 2196)
        self.assertEqual(result["section_heights"], (2196,))
        self.assertTrue(result["width_only_proportional_fit"])
        self.assertEqual(result["main_image_a_plus_layout_key"], "desktop_equal")
        self.assertIn("整图直出", result["channel"])
        self.assertIn("没有执行图片拼接", result["text"])
        self.assertNotIn("safe_margin", result)

    def test_job_applies_mobile_layout_size_and_sections(self) -> None:
        source = Image.new("RGB", (200, 800), "white")
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
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                return_value=passed_quality_review(),
            ) as review_candidate,
            patch.object(site, "build_main_image_a_plus_continuity_reference") as continuity_reference,
            patch.object(site, "stitch_main_image_a_plus_sections") as stitch_sections,
            patch.object(site, "finalize_feature_job_result", side_effect=lambda _context, result, _job_id: result),
        ):
            result = site.run_feature_job(job_context)

        request_images.assert_called_once()
        continuity_reference.assert_not_called()
        stitch_sections.assert_not_called()
        self.assertEqual(len(request_images.call_args.kwargs["uploaded_files"]), 1)
        self.assertEqual(request_images.call_args.kwargs["aspect_ratio"], "1:4")
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (600, 2400))
        self.assertEqual(result["requested_aspect_ratios"], ("1:4",))
        self.assertEqual(result["section_count"], 1)
        self.assertEqual(result["target_size"], (600, 2400))
        self.assertEqual(result["requested_target_size"], (600, 1800))
        self.assertEqual(result["section_heights"], (2400,))
        self.assertEqual(result["section_height"], 2400)
        self.assertEqual(result["main_image_a_plus_layout_key"], "mobile_equal")
        self.assertEqual(review_candidate.call_args.args[1]["target_size"], (600, 2400))

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

    def test_free_canvas_size_adapter_preserves_complete_wide_image(self) -> None:
        source = Image.new("RGB", (300, 100), "green")
        source.paste("red", (0, 0, 100, 100))
        source.paste("blue", (200, 0, 300, 100))

        fitted_url = site.cover_image_to_exact_size(image_data_url(source), 100, 100)

        with open_data_url(fitted_url) as fitted:
            self.assertEqual(fitted.size, (100, 100))
            self.assertEqual(fitted.getpixel((0, 50)), (255, 0, 0))
            self.assertEqual(fitted.getpixel((99, 50)), (0, 0, 255))

    def test_width_only_adapter_preserves_ratio_without_crop_or_background_fill(self) -> None:
        source = Image.new("RGB", (100, 300), "green")
        source.paste("red", (0, 0, 100, 40))
        source.paste("blue", (0, 260, 100, 300))

        fitted_url, fitted_size = site.resize_image_to_target_width(
            image_data_url(source),
            200,
        )

        self.assertEqual(fitted_size, (200, 600))
        with open_data_url(fitted_url) as fitted:
            self.assertEqual(fitted.size, (200, 600))
            self.assertEqual(fitted.getpixel((100, 0)), (255, 0, 0))
            self.assertEqual(fitted.getpixel((100, 599)), (0, 0, 255))

    def test_width_only_adapter_keeps_wide_result_short_instead_of_padding_height(self) -> None:
        source = Image.new("RGB", (300, 100), "green")
        source.paste("red", (0, 0, 100, 100))
        source.paste("blue", (200, 0, 300, 100))

        fitted_url, fitted_size = site.resize_image_to_target_width(
            image_data_url(source),
            150,
        )

        self.assertEqual(fitted_size, (150, 50))
        with open_data_url(fitted_url) as fitted:
            self.assertEqual(fitted.size, (150, 50))
            self.assertEqual(fitted.getpixel((0, 25)), (255, 0, 0))
            self.assertEqual(fitted.getpixel((149, 25)), (0, 0, 255))

    def test_free_canvas_size_adapter_ignores_crop_anchors_and_preserves_both_edges(self) -> None:
        source = Image.new("RGB", (300, 100), "green")
        source.paste("red", (0, 0, 100, 100))
        source.paste("blue", (200, 0, 300, 100))

        right_anchored_url = site.cover_image_to_exact_size(
            image_data_url(source),
            100,
            100,
            horizontal_anchor="right",
        )
        left_anchored_url = site.cover_image_to_exact_size(
            image_data_url(source),
            100,
            100,
            horizontal_anchor="left",
        )

        with open_data_url(right_anchored_url) as right_anchored:
            self.assertEqual(right_anchored.getpixel((0, 50)), (255, 0, 0))
            self.assertEqual(right_anchored.getpixel((99, 50)), (0, 0, 255))
        with open_data_url(left_anchored_url) as left_anchored:
            self.assertEqual(left_anchored.getpixel((0, 50)), (255, 0, 0))
            self.assertEqual(left_anchored.getpixel((99, 50)), (0, 0, 255))

    def test_crop_anchor_follows_quality_review_edge_direction(self) -> None:
        review = {
            "cropped_or_edge_touching_text": [
                "‘NEWCALLY’ 的字母 Y 在右侧被切断",
                "Logo 在右侧被切断",
            ],
            "clipped_foreground": [],
            "layout_issues": [],
        }

        self.assertEqual(
            site.select_main_image_a_plus_crop_anchors(review),
            ("right", "center"),
        )

    def test_mobile_single_layer_normalization_uses_only_the_generated_candidate(self) -> None:
        candidate = Image.new("RGB", (270, 480), "green")
        candidate.paste("red", (0, 0, 270, 24))
        candidate.paste("blue", (0, 456, 270, 480))
        candidate_url = image_data_url(candidate)
        result_url = site.resize_main_image_a_plus_mobile_single_layer(
            candidate_url,
            600,
            1800,
        )

        with open_data_url(result_url) as result:
            self.assertEqual(result.size, (600, 1800))
            self.assertEqual(result.getpixel((300, 0)), (255, 0, 0))
            self.assertEqual(result.getpixel((300, 1799)), (0, 0, 255))
            self.assertEqual(result.getpixel((0, 900)), (0, 128, 0))
            self.assertEqual(result.getpixel((599, 900)), (0, 128, 0))
        run_source = inspect.getsource(site.run_main_image_a_plus_mobile_adaptation_job)
        self.assertIn("resize_main_image_a_plus_mobile_single_layer", run_source)
        self.assertNotIn("expand_main_image_a_plus_mobile_whole_canvas", run_source)
        self.assertNotIn("expand_main_image_a_plus_mobile_candidate_sections", run_source)
        self.assertNotIn("stitch_main_image_a_plus_sections", run_source)

    def test_layout_skeleton_has_an_explicit_non_content_role(self) -> None:
        prompt = site.build_main_image_a_plus_free_prompt(
            "生成商业 A+",
            site.get_main_image_a_plus_layout("desktop_equal"),
            has_layout_skeleton=True,
        )

        self.assertIn("最后一张是抽象版式骨架", prompt)
        self.assertIn("不是商品或品牌素材", prompt)
        self.assertIn("其余输入图才是本次真实商品与品牌素材", prompt)

    def test_free_job_records_source_repair_and_tells_generation_model(self) -> None:
        source = image_uploaded_input(Image.new("RGB", (200, 300), "white"), "source.png")
        prepared_source = site.prepare_main_image_a_plus_reference_input(source)
        repaired_report = {
            "image_index": 1,
            "status": "cropped",
            "cropped_sides": ["top"],
            "content_types": ["hair"],
            "repairability": "safe_auto",
            "confidence": 0.95,
            "reason": "头发顶部被截断",
            "repair_status": "repaired",
        }
        generated = image_data_url(Image.new("RGB", (200, 300), "green"))

        with (
            patch.object(
                site,
                "prepare_main_image_a_plus_sources_with_repair",
                return_value=([prepared_source], [repaired_report], 1, []),
            ),
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={"images": [generated], "text": ""},
            ) as generate_request,
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                return_value=passed_quality_review(),
            ),
        ):
            result = site.run_main_image_a_plus_job(
                {
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "生成 A+",
                    "uploaded_files": [source],
                    "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                    "main_image_a_plus_layout": site.get_main_image_a_plus_layout("desktop_equal"),
                }
            )

        self.assertIn("源图完整性预处理", generate_request.call_args.kwargs["prompt"])
        self.assertIn("第 1 张已补齐 top 边缘", generate_request.call_args.kwargs["prompt"])
        self.assertEqual(result["source_repair_count"], 1)
        self.assertTrue(result["source_integrity_checked"])

    def test_source_integrity_analysis_normalizes_detected_crop(self) -> None:
        source = image_uploaded_input(Image.new("RGB", (200, 300), "white"), "source.png")
        response_text = json.dumps(
            {
                "images": [
                    {
                        "image_index": 1,
                        "asset_role": "designed_module",
                        "status": "cropped",
                        "intentional_crop": False,
                        "cropped_sides": ["top", "invalid"],
                        "content_types": ["hair", "invalid"],
                        "repairability": "safe_auto",
                        "reference_image_indices": [2, 1, 99],
                        "confidence": 0.94,
                        "reason": "头发顶部被截断",
                    }
                ]
            },
            ensure_ascii=False,
        )

        with patch.object(site, "call_openrouter", return_value={"text": response_text}):
            reports = site.analyze_main_image_a_plus_source_integrity([source])

        self.assertEqual(reports[0]["status"], "cropped")
        self.assertEqual(reports[0]["asset_role"], "designed_module")
        self.assertEqual(reports[0]["cropped_sides"], ["top"])
        self.assertEqual(reports[0]["content_types"], ["hair"])
        self.assertEqual(reports[0]["repairability"], "safe_auto")
        self.assertEqual(reports[0]["reference_image_indices"], [])
        self.assertAlmostEqual(reports[0]["confidence"], 0.94)

    def test_designed_module_with_unsafe_text_crop_is_preserved_as_reference(self) -> None:
        source = image_uploaded_input(Image.new("RGB", (300, 300), "white"), "module.png")
        report = {
            "image_index": 1,
            "asset_role": "designed_module",
            "status": "cropped",
            "intentional_crop": False,
            "cropped_sides": ["bottom"],
            "content_types": ["text", "parameter"],
            "repairability": "reference_required",
            "reference_image_indices": [],
            "confidence": 0.95,
            "reason": "底部 Before 模块和参数被切断",
        }

        with (
            patch.object(
                site,
                "analyze_main_image_a_plus_source_integrity",
                return_value=[report],
            ),
            patch.object(site, "repair_main_image_a_plus_source_crop") as repair_source,
        ):
            prepared, reports, repair_count, warnings = (
                site.prepare_main_image_a_plus_sources_with_repair(
                    [source],
                    model=site.NANO_BANANA_MODEL,
                )
            )

        repair_source.assert_not_called()
        self.assertEqual(len(prepared), 1)
        self.assertEqual(repair_count, 0)
        self.assertEqual(reports[0]["repair_status"], "preserved_unrepaired")
        self.assertIn("已保留原图", warnings[0])
        instruction = site.build_main_image_a_plus_source_integrity_instruction(reports)
        self.assertIn("已排版的广告/A+ 模块", instruction)
        self.assertIn("只能采用其完整可见", instruction)
        self.assertIn("内容预算是硬上限", instruction)
        self.assertIn("支撑证据组总数不得超过 3 个", instruction)

    def test_completed_designed_modules_are_rebuilt_one_source_per_section(self) -> None:
        colors = {
            "hero.png": "red",
            "detail.png": "green",
            "proof.png": "blue",
        }
        sources = [
            image_uploaded_input(Image.new("RGB", (300, 300), color), name)
            for name, color in colors.items()
        ]
        reports = [
            {
                "image_index": index,
                "asset_role": "designed_module",
                "status": "complete",
                "intentional_crop": index == 2,
                "cropped_sides": [],
                "content_types": [],
                "repairability": "unknown",
                "reference_image_indices": [],
                "confidence": 0.99,
                "reason": "完成广告模块",
            }
            for index in range(1, 4)
        ]

        def generate_section(**kwargs):
            source_name = kwargs["uploaded_files"][0]["name"]
            source_color = next(
                color
                for original_name, color in colors.items()
                if source_name.startswith(original_name.rsplit(".", 1)[0])
            )
            return {
                "images": [
                    image_data_url(Image.new("RGB", (160, 100), source_color))
                ],
                "text": "",
            }

        with (
            patch.object(
                site,
                "analyze_main_image_a_plus_source_integrity",
                return_value=reports,
            ),
            patch.object(
                site,
                "call_openrouter_images_api",
                side_effect=generate_section,
            ) as request_images,
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                return_value=passed_quality_review(),
            ),
        ):
            result = site.run_main_image_a_plus_job(
                {
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "生成 A+",
                    "uploaded_files": sources,
                    "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                    "main_image_a_plus_layout": site.get_main_image_a_plus_layout(
                        "desktop_equal"
                    ),
                }
            )

        self.assertEqual(request_images.call_count, 3)
        for call in request_images.call_args_list:
            self.assertEqual(len(call.kwargs["uploaded_files"]), 1)
            self.assertIn("严禁把源图整个方形/矩形画布缩小后贴入", call.kwargs["prompt"])
            self.assertIn("安全区只是内部构图约束", call.kwargs["prompt"])
            self.assertNotIn("132px", call.kwargs["prompt"])
        self.assertTrue(result["designed_module_pipeline"])
        self.assertEqual(result["section_count"], 3)
        self.assertEqual(result["section_heights"], (800, 800, 800))
        self.assertEqual(result["quality_delivery_status"], "passed")
        self.assertIn("已设计素材分区重构", result["channel"])
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (1464, 2400))
            self.assertEqual(output.getpixel((700, 400)), (255, 0, 0))
            self.assertEqual(output.getpixel((700, 1200)), (0, 128, 0))
            self.assertEqual(output.getpixel((700, 2000)), (0, 0, 255))

    def test_designed_module_section_prompt_discards_unrecoverable_edge_groups(self) -> None:
        prompt = site.build_main_image_a_plus_designed_module_section_prompt(
            "生成专业睫毛 A+",
            site.get_main_image_a_plus_layout("mobile_equal"),
            2,
            3,
            600,
            {
                "status": "cropped",
                "cropped_sides": ["right", "bottom"],
                "intentional_crop": False,
            },
        )

        self.assertIn("第 3/3 个横向连续区段", prompt)
        self.assertIn("任何半截文字、半张卡片、残缺参数", prompt)
        self.assertIn("不得编造 Thank you", prompt)
        self.assertIn("严禁把纵向长度阶梯、完整参数表", prompt)
        self.assertIn("只能选择一个代表性参数", prompt)
        self.assertIn("只含连续背景、渐变、纹理或光影的过渡带", prompt)
        self.assertIn("绝不能把安全区边界、边距数值、像素单位", prompt)
        self.assertNotIn("54px", prompt)

    def test_designed_module_retry_only_regenerates_reviewed_problem_section(self) -> None:
        sources = [
            image_uploaded_input(Image.new("RGB", (200, 200), color), name)
            for name, color in (
                ("hero.png", "red"),
                ("detail.png", "green"),
                ("proof.png", "blue"),
            )
        ]
        reports = [
            {
                "image_index": index,
                "asset_role": "designed_module",
                "status": "complete",
                "intentional_crop": False,
            }
            for index in range(1, 4)
        ]
        first_review = {
            "reviewed": True,
            "passed": False,
            "quality_score": 6.5,
            "critical_issue_count": 0,
            "cropped_or_edge_touching_text": [],
            "clipped_foreground": [],
            "missing_elements": [],
            "duplicated_elements": [],
            "text_mismatches": [],
            "layout_issues": ["第 3 段参数过多"],
            "affected_section_indices": [3],
            "retry_instruction": "第 3 段只保留一个参数",
        }

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={
                    "images": [image_data_url(Image.new("RGB", (160, 100), "orange"))],
                    "text": "",
                },
            ) as request_images,
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                side_effect=[first_review, passed_quality_review()],
            ),
        ):
            result = site.run_main_image_a_plus_designed_module_job(
                job_context={
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "生成 A+",
                },
                generation_mode=site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                layout=site.get_main_image_a_plus_layout("desktop_equal"),
                uploaded_files=sources,
                source_integrity_reports=reports,
                source_repair_count=0,
                source_integrity_warnings=[],
            )

        self.assertEqual(request_images.call_count, 4)
        self.assertTrue(
            str(request_images.call_args_list[-1].kwargs["uploaded_files"][0]["name"])
            .startswith("proof")
        )
        self.assertIn("第 3 段只保留一个参数", request_images.call_args_list[-1].kwargs["prompt"])
        self.assertEqual(result["repaired_section_indices"], (3,))
        self.assertTrue(result["quality_review_passed"])

    def test_lab_designed_module_packaging_crop_returns_preview_instead_of_task_failure(self) -> None:
        sources = [
            image_uploaded_input(Image.new("RGB", (200, 200), "gray"), f"module-{index}.png")
            for index in range(1, 4)
        ]
        reports = [
            {
                "image_index": index,
                "asset_role": "designed_module",
                "status": "complete",
                "intentional_crop": False,
            }
            for index in range(1, 4)
        ]
        badge_review = {
            "reviewed": True,
            "passed": False,
            "quality_score": 7.0,
            "critical_issue_count": 1,
            "cropped_or_edge_touching_text": [],
            "clipped_foreground": ["产品包装左侧的 NEWCALLY 被画布左侧切断"],
            "missing_elements": [],
            "duplicated_elements": [],
            "text_mismatches": [],
            "layout_issues": [],
            "affected_section_indices": [3],
            "retry_instruction": "缩小并内移产品包装",
        }

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={
                    "images": [image_data_url(Image.new("RGB", (160, 100), "orange"))],
                    "text": "",
                },
            ) as request_images,
            patch.object(
                site,
                "review_main_image_a_plus_candidate",
                side_effect=[badge_review, badge_review, badge_review],
            ),
        ):
            result = site.run_main_image_a_plus_designed_module_job(
                job_context={
                    "feature": {"key": site.A_PLUS_REFERENCE_LAB_FEATURE_KEY},
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "生成 A+",
                },
                generation_mode=site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                layout=site.get_main_image_a_plus_layout("desktop_equal"),
                uploaded_files=sources,
                source_integrity_reports=reports,
                source_repair_count=0,
                source_integrity_warnings=[],
            )

        self.assertEqual(request_images.call_count, 5)
        self.assertFalse(result["quality_review_passed"])
        self.assertEqual(result["quality_delivery_status"], "needs_review")
        self.assertTrue(result["quality_result_restored"])
        self.assertTrue(
            any("产品包装" in issue for issue in result["quality_review_issues"])
        )
        self.assertIn("必须把该次要内容整组删除", request_images.call_args_list[-1].kwargs["prompt"])

    def test_source_repair_uses_only_explicit_same_identity_references(self) -> None:
        cropped = image_uploaded_input(Image.new("RGB", (200, 300), "white"), "cropped.png")
        matching = image_uploaded_input(Image.new("RGB", (200, 300), "gray"), "matching.png")
        unrelated = image_uploaded_input(Image.new("RGB", (200, 300), "black"), "unrelated.png")
        reports = [
            {
                "image_index": 1,
                "asset_role": "raw_asset",
                "status": "cropped",
                "intentional_crop": False,
                "cropped_sides": ["right"],
                "content_types": ["product"],
                "repairability": "reference_required",
                "reference_image_indices": [2],
                "confidence": 0.96,
                "reason": "商品右侧缺失",
            },
            {
                "image_index": 2,
                "asset_role": "raw_asset",
                "status": "complete",
                "cropped_sides": [],
                "content_types": [],
                "repairability": "unknown",
                "reference_image_indices": [],
                "confidence": 0.9,
                "reason": "",
            },
            {
                "image_index": 3,
                "asset_role": "raw_asset",
                "status": "complete",
                "cropped_sides": [],
                "content_types": [],
                "repairability": "unknown",
                "reference_image_indices": [],
                "confidence": 0.9,
                "reason": "",
            },
        ]

        with (
            patch.object(
                site,
                "analyze_main_image_a_plus_source_integrity",
                return_value=reports,
            ),
            patch.object(
                site,
                "repair_main_image_a_plus_source_crop",
                return_value=cropped,
            ) as repair_source,
        ):
            prepared, _reports, repair_count, _warnings = (
                site.prepare_main_image_a_plus_sources_with_repair(
                    [cropped, matching, unrelated],
                    model=site.NANO_BANANA_MODEL,
                )
            )

        self.assertEqual(len(prepared), 3)
        self.assertEqual(repair_count, 1)
        supporting = repair_source.call_args.kwargs["supporting_references"]
        self.assertEqual(len(supporting), 1)
        self.assertEqual(supporting[0]["name"], "matching.png")

    def test_source_repair_outpaints_only_confirmed_edges(self) -> None:
        source = image_uploaded_input(Image.new("RGB", (100, 100), "red"), "cropped.png")
        generated = image_data_url(Image.new("RGB", (100, 124), "green"))
        report = {
            "status": "cropped",
            "cropped_sides": ["top"],
            "content_types": ["hair"],
            "repairability": "safe_auto",
            "confidence": 0.95,
        }

        with patch.object(
            site,
            "call_openrouter_images_api",
            return_value={"images": [generated], "text": ""},
        ) as repair_request:
            repaired = site.repair_main_image_a_plus_source_crop(
                source,
                report,
                model=site.NANO_BANANA_MODEL,
            )

        self.assertTrue(str(repaired["name"]).endswith("_a_plus_completed.png"))
        with Image.open(io.BytesIO(bytes(repaired["data"]))) as image:
            self.assertEqual(image.size, (100, 124))
        call_kwargs = repair_request.call_args.kwargs
        self.assertEqual(len(call_kwargs["uploaded_files"]), 1)
        self.assertEqual(call_kwargs["uploaded_files"][0]["name"], "outpaint_transition_canvas.png")
        self.assertIn("只补齐这些缺失方向", call_kwargs["prompt"])

    def test_unrecoverable_core_source_crop_requires_another_reference(self) -> None:
        source = image_uploaded_input(Image.new("RGB", (200, 300), "white"), "product.png")
        report = {
            "image_index": 1,
            "status": "cropped",
            "cropped_sides": ["right"],
            "content_types": ["product", "logo"],
            "repairability": "unrecoverable",
            "confidence": 0.96,
            "reason": "商品和 Logo 右侧缺失",
        }

        with patch.object(
            site,
            "analyze_main_image_a_plus_source_integrity",
            return_value=[report],
        ):
            with self.assertRaisesRegex(RuntimeError, "不会猜造商品结构"):
                site.prepare_main_image_a_plus_sources_with_repair(
                    [source],
                    model=site.NANO_BANANA_MODEL,
                )

    def test_quality_review_failure_is_not_treated_as_passed(self) -> None:
        candidate = image_data_url(Image.new("RGB", (600, 1800), "white"))
        with patch.object(site, "call_openrouter", side_effect=RuntimeError("review offline")):
            review = site.review_main_image_a_plus_candidate(
                candidate,
                site.get_main_image_a_plus_layout("mobile_equal"),
                site.MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT,
            )

        self.assertFalse(review["reviewed"])
        self.assertFalse(review["passed"])
        self.assertEqual(review["critical_issue_count"], 1)

    def test_free_canvas_size_adapter_preserves_top_and_bottom_content(self) -> None:
        source = Image.new("RGB", (100, 300), "green")
        source.paste("red", (0, 0, 100, 40))
        source.paste("blue", (0, 260, 100, 300))

        fitted_url = site.cover_image_to_exact_size(image_data_url(source), 100, 200)

        with open_data_url(fitted_url) as fitted:
            self.assertEqual(fitted.size, (100, 200))
            self.assertEqual(fitted.getpixel((50, 0)), (255, 0, 0))
            self.assertEqual(fitted.getpixel((50, 199)), (0, 0, 255))

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
        created_response = Mock(status_code=202)
        created_response.json.return_value = {"id": "task_timeout", "status": "queued"}
        completed_response = Mock(status_code=200)
        completed_response.json.return_value = {
            "id": "task_timeout",
            "status": "succeeded",
            "assets": [{"kind": "image", "url": "https://example.invalid/result.jpg"}],
        }
        downloaded_response = Mock(status_code=200, content=b"image")
        downloaded_response.headers = {"Content-Type": "image/png"}

        with (
            patch.object(site, "load_omnia_api_key", return_value="test-key"),
            patch.object(
                site.requests,
                "post",
                side_effect=[site.requests.ReadTimeout("temporary timeout"), created_response],
            ) as request_post,
            patch.object(site.requests, "get", side_effect=[completed_response, downloaded_response]),
            patch.object(site.time, "sleep") as retry_sleep,
        ):
            result = site.call_openrouter_images_api(
                model="bytedance-seed/seedream-4.5",
                prompt="生成测试图片",
            )

        self.assertEqual(request_post.call_count, 2)
        retry_sleep.assert_any_call(site.OMNIAKEY_MEDIA_RETRY_DELAYS[0])
        self.assertEqual(
            request_post.call_args_list[0].kwargs["timeout"],
            (
                site.OMNIAKEY_CONNECT_TIMEOUT_SECONDS,
                site.OMNIAKEY_READ_TIMEOUT_SECONDS,
            ),
        )
        self.assertIn(
            "GLOBAL GEOMETRY LOCK",
            request_post.call_args_list[0].kwargs["json"]["input"]["prompt"],
        )
        self.assertTrue(result["images"][0].startswith("data:image/png;base64,"))

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
