from __future__ import annotations

import base64
import inspect
import io
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from 图片 import openrouter_image_site as site


class ImageSmartAnalysisTests(unittest.TestCase):
    @staticmethod
    def make_split_image_input() -> dict[str, object]:
        image = Image.new("RGB", (120, 80), "red")
        draw = ImageDraw.Draw(image)
        draw.rectangle((60, 0, 119, 79), fill="blue")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return {
            "name": "split.png",
            "type": "image/png",
            "data": output.getvalue(),
        }

    def test_feature_is_visible_and_uses_single_image_text_analysis(self) -> None:
        feature = site.get_feature_by_key(site.IMAGE_SMART_ANALYSIS_FEATURE_KEY)

        self.assertIsNotNone(feature)
        assert feature is not None
        self.assertEqual(feature["name"], "图片智能分析")
        self.assertEqual(feature["model"], site.IMAGE_SMART_ANALYSIS_MODEL)
        self.assertEqual(feature["output_mode"], "text")
        self.assertEqual(feature["min_images"], 1)
        self.assertEqual(feature["max_input_images"], 1)
        self.assertEqual(feature["max_output_images"], 0)
        self.assertIn(
            site.IMAGE_SMART_ANALYSIS_FEATURE_KEY,
            {item["key"] for item in site.get_visible_features()},
        )

    def test_analysis_prompt_requests_compact_regions_and_strict_json(self) -> None:
        feature = site.get_feature_by_key(site.IMAGE_SMART_ANALYSIS_FEATURE_KEY)
        assert feature is not None

        prompt = site.build_prompt(
            feature,
            "",
            site.DEFAULT_ASPECT_RATIO,
            "",
        )

        for json_field in (
            '"summary"',
            '"composition"',
            '"lighting"',
            '"typography"',
            '"decorations"',
            '"style_tags"',
            '"color_notes"',
            '"regions"',
            '"bbox"',
        ):
            self.assertIn(json_field, prompt)
        self.assertIn("3至6个", prompt)
        self.assertIn("0至1000", prompt)
        self.assertIn("从原图像素直接提取的真实色号", prompt)
        self.assertIn("无法确认", prompt)
        self.assertIn("禁止臆造", prompt)
        self.assertIn("不要生成、修改或重绘图片", prompt)
        self.assertIn("只输出一个有效 JSON 对象", prompt)
        self.assertNotIn("GLOBAL GEOMETRY LOCK", prompt)
        self.assertNotIn("最小输出边长", prompt)
        self.assertNotIn("适合商业修图/电商展示的高质量结果", prompt)

    def test_palette_uses_real_source_pixels_and_reports_hex_codes(self) -> None:
        uploaded_input = self.make_split_image_input()

        palette = site.extract_image_smart_palette(uploaded_input, max_colors=6)
        colors = {item["hex"] for item in palette}

        self.assertIn("#FF0000", colors)
        self.assertIn("#0000FF", colors)
        self.assertAlmostEqual(sum(float(item["ratio"]) for item in palette), 100.0, delta=1.0)

    def test_job_calls_vision_model_and_returns_visual_board(self) -> None:
        feature = site.get_feature_by_key(site.IMAGE_SMART_ANALYSIS_FEATURE_KEY)
        assert feature is not None
        uploaded_input = self.make_split_image_input()
        expected_payload = (
            '{"summary":"红蓝双色构成的测试主图",'
            '"composition":"左右分区构图",'
            '"lighting":"纯色色块，无明显光影",'
            '"typography":"未发现清晰文字",'
            '"decorations":["左右色块形成对比"],'
            '"style_tags":["极简","高对比"],'
            '"color_notes":['
            '{"hex":"#FF0000","role":"主色","description":"位于左侧，形成暖色主体"},'
            '{"hex":"#0000FF","role":"辅色","description":"位于右侧，形成冷暖对比"}],'
            '"regions":['
            '{"id":1,"name":"左侧红区","bbox":[0,0,500,1000],"content":"红色色块",'
            '"style":"高饱和暖色"},'
            '{"id":2,"name":"右侧蓝区","bbox":[500,0,1000,1000],"content":"蓝色色块",'
            '"style":"高饱和冷色"}]}'
        )
        job_context = {
            "feature": dict(feature),
            "model": site.IMAGE_SMART_ANALYSIS_MODEL,
            "prompt": site.build_prompt(feature, "", site.DEFAULT_ASPECT_RATIO, ""),
            "uploaded_files": [uploaded_input],
            "batch_groups": [],
            "output_mode": "text",
            "max_output_images": 0,
            "account_name": "tester",
            "aspect_ratio": site.DEFAULT_ASPECT_RATIO,
        }

        with patch.object(
            site,
            "call_openrouter",
            return_value={"images": [], "text": expected_payload},
        ) as mocked_call:
            result = site.run_feature_job(job_context)

        self.assertEqual(result["text"], "红蓝双色构成的测试主图")
        self.assertEqual(result["images"], [])
        visual_analysis = result["visual_analysis"]
        self.assertEqual(len(visual_analysis["regions"]), 2)
        self.assertTrue(visual_analysis["board_image"].startswith("data:image/png;base64,"))
        board_bytes = base64.b64decode(visual_analysis["board_image"].split(",", 1)[1])
        with Image.open(io.BytesIO(board_bytes)) as board:
            self.assertEqual(board.width, 1400)
            self.assertGreater(board.height, 1500)
        self.assertNotIn("layout_image", visual_analysis)
        layout_comparison = site.build_image_smart_layout_comparison(
            uploaded_input,
            visual_analysis,
        )
        self.assertEqual(layout_comparison.size, (1228, 400))
        source_panel = layout_comparison.crop((0, 0, 600, 400)).convert("RGB")
        wireframe_panel = layout_comparison.crop((628, 0, 1228, 400)).convert("RGB")
        source_colors = {color for _count, color in (source_panel.getcolors(maxcolors=100_000) or [])}
        wireframe_colors = wireframe_panel.getcolors(maxcolors=100_000) or []
        self.assertIn((255, 0, 0), source_colors)
        self.assertIn((0, 0, 255), source_colors)
        self.assertTrue(wireframe_colors)
        self.assertTrue(
            all(red == green == blue for _count, (red, green, blue) in wireframe_colors)
        )
        self.assertNotIn((255, 0, 0), {color for _count, color in wireframe_colors})
        self.assertNotIn((0, 0, 255), {color for _count, color in wireframe_colors})
        mocked_call.assert_called_once()
        call_kwargs = mocked_call.call_args.kwargs
        self.assertEqual(call_kwargs["model"], site.IMAGE_SMART_ANALYSIS_MODEL)
        self.assertEqual(call_kwargs["output_mode"], "text")
        self.assertEqual(call_kwargs["uploaded_files"], [uploaded_input])
        self.assertIn("#FF0000", call_kwargs["prompt"])
        self.assertIn("#0000FF", call_kwargs["prompt"])
        self.assertIn("真实色卡数据，不是模型估算", call_kwargs["prompt"])

    def test_page_has_dedicated_visual_board_and_png_download_ui(self) -> None:
        page_source = inspect.getsource(site.render_openrouter_feature)
        report_source = inspect.getsource(site.render_image_smart_analysis_report)
        style_source = inspect.getsource(site.inject_app_styles)

        self.assertIn("待分析主图（1 张）", page_source)
        self.assertIn("开始智能分析", page_source)
        self.assertIn("图片分析报告", page_source)
        self.assertIn("render_image_smart_analysis_report", page_source)
        self.assertIn("下载完整视觉拆解图（PNG）", report_source)
        self.assertIn("原图与灰度纯排版已按相同画幅并排合入拆解图", report_source)
        self.assertNotIn("layout_image", report_source)
        self.assertNotIn("st.tabs", report_source)
        self.assertNotIn("下载纯排版结构图（PNG）", report_source)
        self.assertIn("image/png", report_source)
        self.assertIn("render_zoomable_image_gallery", report_source)
        self.assertIn("色卡与 HEX 色号由系统直接读取原图像素生成", report_source)
        self.assertIn("image-smart-analysis-report-marker", report_source)
        self.assertIn("image-smart-analysis-report-marker", style_source)
        self.assertIn(
            'if feature.get("output_mode") == "image":\n        render_history_records(feature)',
            page_source,
        )

    def test_analysis_model_has_clear_display_name(self) -> None:
        self.assertEqual(
            site.get_model_display_name(site.IMAGE_SMART_ANALYSIS_MODEL),
            "Gemini 2.5 Flash 视觉分析",
        )


if __name__ == "__main__":
    unittest.main()
