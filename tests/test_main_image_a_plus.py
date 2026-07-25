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


class MainImageAPlusTests(unittest.TestCase):
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
        self.assertIn("不显示任何安全距离", prompt)
        self.assertIn("首屏必须是完整的商业主视觉", prompt)
        self.assertIn("参考图只是可选择的素材池，不要求全部出现在首屏", prompt)
        self.assertIn("严禁在首屏中直接堆叠多个产品抠图", prompt)
        self.assertIn("整体采用黑金风格", prompt)
        self.assertIn("最终连续长图成品尺寸必须严格等于 600*1800px", prompt)

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

        self.assertIn("一次模型生成中直接输出 1 张完整的 600×1800px", prompt)
        self.assertIn("禁止把画布拆成四段", prompt)
        self.assertIn("禁止调用多次生成后拼接", prompt)
        self.assertIn("统一场景", prompt)
        self.assertIn("主体跨区", prompt)
        self.assertIn("四个内容阶段只负责阅读节奏", prompt)
        self.assertIn("保持比例、满版覆盖", prompt)
        self.assertIn("禁止给画面增加白边、米色边、黑边", prompt)
        self.assertIn("最外围的纯背景或连续场景做最少量居中裁切", prompt)
        self.assertIn("只挑选一位最清晰、最适合商业展示的模特", prompt)
        self.assertIn("禁止出现第二位模特", prompt)
        self.assertIn("禁止半个字、缺字、断行裁切", prompt)

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

        self.assertIn("600×1800px 手机端 A+ 长图", prompt)
        self.assertIn("不得新增、删除、替换、改写", prompt)
        self.assertIn("这不是一次新设计或内容重绘，而是对同一张电脑端成品做响应式重排", prompt)
        self.assertIn("所有可读文字必须逐字保持原文", prompt)
        self.assertIn("不得根据语义重新撰写相似文案", prompt)
        self.assertIn("现有元素可以等比缩放、移动、调整间距", prompt)
        self.assertIn("必须主动对原有完整元素做穿插式重排", prompt)
        self.assertIn("左右交替与上下错位", prompt)
        self.assertIn("将小型完整元素放入另一元素周围的纯背景留白", prompt)
        self.assertIn("允许不同完整元素的矩形外接框在空间上穿插", prompt)
        self.assertIn("不允许任何有效像素被另一元素覆盖", prompt)
        self.assertIn("元素总数、元素种类、出现次数和内容一一对应", prompt)
        self.assertIn("每一个元素都必须被视为不可拆分的完整整体", prompt)
        self.assertIn("禁止把一个元素切成多块、只保留局部、裁掉边缘", prompt)
        self.assertIn("禁止为了做穿插而给任何元素添加裁切窗口、蒙版、遮罩", prompt)
        self.assertIn("每一个可见像素都必须保留", prompt)
        self.assertIn("空间不足时必须缩小整个元素并另找位置", prompt)
        self.assertIn("禁止对任何前景执行 cover 裁切、中心裁切", prompt)
        self.assertIn("full-bleed background + all foreground elements fully visible", prompt)
        self.assertIn("不能出现白边、黑边、透明条、纯色留白条", prompt)
        self.assertIn("中间 75% 高度范围内", prompt)
        self.assertIn("上方 12.5% 和下方 12.5%", prompt)
        self.assertIn("[30,150,970,850]", prompt)
        self.assertIn("安全区是前景元素外接框的硬边界", prompt)
        self.assertIn("这两段上下背景是最终尺寸适配时唯一允许移除的区域", prompt)
        self.assertIn("禁止把边缘像素、家具线条、人物轮廓", prompt)
        self.assertIn("禁止任何拖影、条纹化延展或镜像复制痕迹", prompt)
        self.assertIn("禁止对整张图或任何人物、商品、Logo、文字、图片窗口进行非等比压缩、拉伸", prompt)
        self.assertIn("不重新设计", prompt)
        self.assertIn("必须整体位于中间内容区内", prompt)

    def test_mobile_adaptation_uses_desktop_result_as_sole_reference_and_returns_exact_size(self) -> None:
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
        self.assertEqual(len(call_kwargs["uploaded_files"]), 1)
        self.assertEqual(call_kwargs["aspect_ratio"], "1:4")
        self.assertEqual(call_kwargs["resolution"], "4K")
        self.assertEqual(call_kwargs["max_attempts"], 1)
        self.assertIn("不得新增、删除、替换、改写", call_kwargs["prompt"])
        self.assertIn("电脑端元素清单", call_kwargs["prompt"])
        self.assertIn("品牌 Logo", call_kwargs["prompt"])
        self.assertIn("手机端安全边距硬规则", call_kwargs["prompt"])
        self.assertIn("动态规划安全边距", call_kwargs["prompt"])
        self.assertNotIn("[60,40,940,960]", call_kwargs["prompt"])
        self.assertEqual(result["mobile_adaptation_source"], desktop_source)
        self.assertEqual(result["main_image_a_plus_mode"], site.MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT)
        self.assertEqual(result["target_size"], (600, 1800))
        self.assertEqual(result["mobile_generation_attempts"], 1)
        self.assertEqual(result["mobile_element_inventory_count"], 1)
        self.assertEqual(result["mobile_foreground_fit"], "reserved_background_trim")
        self.assertEqual(result["mobile_background_fill"], "native_full_bleed")
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (600, 1800))

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
        mobile_thumbnail = image_data_url(Image.new("RGB", (120, 360), "green"))
        desktop = image_data_url(Image.new("RGB", (1464, 2400), "green"))

        self.assertTrue(site.is_main_image_a_plus_mobile_canvas(mobile))
        self.assertTrue(site.is_main_image_a_plus_mobile_canvas(mobile_thumbnail))
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
        ) as request_images:
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
            self.assertEqual(output.size, (600, 1800))

    def test_free_aspect_ratio_uses_closest_native_ratio_for_crop_free_fitting(self) -> None:
        self.assertEqual(
            site.select_main_image_a_plus_safe_aspect_ratio((600, 1800)),
            "1:4",
        )
        self.assertEqual(
            site.select_main_image_a_plus_safe_aspect_ratio((1464, 2400)),
            "9:16",
        )

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
        self.assertIn("保持比例、满版覆盖", call_kwargs["prompt"])
        self.assertIn("禁止给画面增加白边、米色边、黑边", call_kwargs["prompt"])
        with open_data_url(result["images"][0]) as output:
            self.assertEqual(output.size, (1464, 2400))
        self.assertEqual(result["section_count"], 1)
        self.assertEqual(result["section_height"], 2400)
        self.assertEqual(result["section_heights"], (2400,))
        self.assertEqual(result["main_image_a_plus_layout_key"], "desktop_equal")
        self.assertIn("整图直出", result["channel"])
        self.assertIn("没有执行图片拼接", result["text"])
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
            self.assertEqual(output.size, (600, 1800))
        self.assertEqual(result["requested_aspect_ratios"], ("1:4",))
        self.assertEqual(result["section_count"], 1)
        self.assertEqual(result["section_heights"], (1800,))
        self.assertEqual(result["section_height"], 1800)
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

    def test_free_canvas_size_adapter_fills_left_and_right_without_borders(self) -> None:
        source = Image.new("RGB", (300, 100), "green")
        source.paste("red", (0, 0, 100, 100))
        source.paste("blue", (200, 0, 300, 100))

        fitted_url = site.cover_image_to_exact_size(image_data_url(source), 100, 100)

        with open_data_url(fitted_url) as fitted:
            self.assertEqual(fitted.size, (100, 100))
            self.assertEqual(fitted.getpixel((0, 50)), (0, 128, 0))
            self.assertEqual(fitted.getpixel((99, 50)), (0, 128, 0))

    def test_mobile_reserved_background_trim_preserves_elements_without_edge_stretching(self) -> None:
        source = Image.new("RGB", (120, 480), (20, 20, 20))
        draw = ImageDraw.Draw(source)
        for y in range(0, source.height, 4):
            for x in range(0, source.width, 4):
                shade = 18 + ((x // 4 + y // 4) % 7) * 4
                draw.rectangle((x, y, x + 3, y + 3), fill=(shade, shade + 5, shade + 10))
        draw.rectangle((4, 65, 24, 85), fill=(255, 0, 0))
        draw.rectangle((95, 65, 115, 85), fill=(0, 255, 0))
        draw.rectangle((4, 395, 24, 415), fill=(0, 0, 255))
        draw.rectangle((95, 395, 115, 415), fill=(255, 255, 0))
        draw.rectangle((50, 230, 69, 249), fill=(255, 0, 255))

        result_url = site.fit_image_to_exact_size_by_trimming_reserved_background(
            image_data_url(source),
            600,
            1800,
        )

        with open_data_url(result_url) as result:
            self.assertEqual(result.size, (600, 1800))
            color_checks = {
                "red": lambda pixel: pixel[0] > 180 and pixel[1] < 80 and pixel[2] < 80,
                "green": lambda pixel: pixel[0] < 80 and pixel[1] > 180 and pixel[2] < 80,
                "blue": lambda pixel: pixel[0] < 80 and pixel[1] < 80 and pixel[2] > 180,
                "yellow": lambda pixel: pixel[0] > 180 and pixel[1] > 180 and pixel[2] < 80,
                "magenta": lambda pixel: pixel[0] > 180 and pixel[1] < 80 and pixel[2] > 180,
            }
            detected_boxes: dict[str, tuple[int, int, int, int]] = {}
            for name, matcher in color_checks.items():
                pixels = [
                    (x, y)
                    for y in range(result.height)
                    for x in range(result.width)
                    if matcher(result.getpixel((x, y)))
                ]
                self.assertTrue(pixels, f"missing contained element: {name}")
                detected_boxes[name] = (
                    min(x for x, _y in pixels),
                    min(y for _x, y in pixels),
                    max(x for x, _y in pixels),
                    max(y for _x, y in pixels),
                )
            for left, top, right, bottom in detected_boxes.values():
                self.assertGreater(left, 0)
                self.assertGreater(top, 0)
                self.assertLess(right, result.width - 1)
                self.assertLess(bottom, result.height - 1)
            magenta = detected_boxes["magenta"]
            self.assertLessEqual(abs((magenta[2] - magenta[0]) - (magenta[3] - magenta[1])), 2)

            self.assertEqual(result.mode, "RGB")
            borders = (
                [result.getpixel((x, 0)) for x in range(result.width)],
                [result.getpixel((x, result.height - 1)) for x in range(result.width)],
                [result.getpixel((0, y)) for y in range(result.height)],
                [result.getpixel((result.width - 1, y)) for y in range(result.height)],
            )
            for border in borders:
                self.assertGreater(len(set(border)), 1)
                self.assertFalse(all(pixel in {(0, 0, 0), (255, 255, 255)} for pixel in border))

        run_source = inspect.getsource(site.run_main_image_a_plus_mobile_adaptation_job)
        self.assertIn("fit_image_to_exact_size_by_trimming_reserved_background", run_source)
        self.assertNotIn("cover_image_to_exact_size", run_source)
        adapter_source = inspect.getsource(site.fit_image_to_exact_size_by_trimming_reserved_background)
        self.assertNotIn("FLIP_LEFT_RIGHT", adapter_source)
        self.assertNotIn("FLIP_TOP_BOTTOM", adapter_source)

    def test_free_canvas_size_adapter_fills_top_and_bottom_without_borders(self) -> None:
        source = Image.new("RGB", (100, 300), "green")
        source.paste("red", (0, 0, 100, 40))
        source.paste("blue", (0, 260, 100, 300))

        fitted_url = site.cover_image_to_exact_size(image_data_url(source), 100, 200)

        with open_data_url(fitted_url) as fitted:
            self.assertEqual(fitted.size, (100, 200))
            self.assertEqual(fitted.getpixel((50, 0)), (0, 128, 0))
            self.assertEqual(fitted.getpixel((50, 199)), (0, 128, 0))

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
        self.assertIn(
            "GLOBAL GEOMETRY LOCK",
            request_post.call_args_list[0].kwargs["json"]["prompt"],
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
