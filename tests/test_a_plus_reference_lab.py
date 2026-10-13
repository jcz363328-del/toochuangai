from __future__ import annotations

import io
import inspect
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from 图片 import a_plus_reference_lab as lab
from 图片 import openrouter_image_site as site


class APlusReferenceLabTests(unittest.TestCase):
    def test_lab_feature_is_registered_as_an_independent_module(self) -> None:
        feature = site.get_feature_by_key(lab.A_PLUS_REFERENCE_LAB_FEATURE_KEY)

        self.assertIsNotNone(feature)
        self.assertEqual(feature["name"], "A+3.0")
        self.assertEqual(feature["max_input_images"], lab.A_PLUS_REFERENCE_LAB_MAX_PRODUCT_IMAGES)
        self.assertEqual(feature["max_output_images"], site.FEATURE_OUTPUT_COUNT_MAX)
        self.assertIn(lab.A_PLUS_REFERENCE_LAB_FEATURE_KEY, site.MAIN_IMAGE_A_PLUS_FEATURE_KEYS)

    def test_lab_ui_uses_stable_four_slot_workbench(self) -> None:
        source = inspect.getsource(site.render_openrouter_feature)

        self.assertIn("a-plus-lab-left-marker", source)
        self.assertIn("a-plus-lab-right-marker", source)
        self.assertIn("render_a_plus_reference_lab_empty_results(selected_output_count)", source)
        self.assertIn('st.number_input(', source)
        self.assertIn('f"开始生成 {selected_output_count} 张"', source)

    def test_lab_history_reads_new_and_legacy_feature_names(self) -> None:
        with (
            patch.object(site, "_db_history_can_view_all", return_value=False),
            patch.object(site, "execute_db_query", return_value=[]) as execute_query,
        ):
            site.load_db_history_records(
                lab.A_PLUS_REFERENCE_LAB_FEATURE_KEY,
                "tester",
                limit=20,
            )

        query, params = execute_query.call_args.args
        self.assertIn("GongNeng IN (%s, %s)", query)
        self.assertEqual(params, ("tester", "A+3.0", "A+测试"))

    def test_reference_library_scan_counts_supported_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            Image.new("RGB", (600, 1800), "white").save(root / "mobile.jpg")
            Image.new("RGB", (1464, 2400), "black").save(root / "desktop.png")
            Image.new("RGB", (2300, 2400), "gray").save(root / "pair.jpg")
            (root / "notes.txt").write_text("ignore", encoding="utf-8")

            summary = lab.scan_a_plus_reference_library(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["file_count"], 4)
        self.assertEqual(summary["image_count"], 3)
        self.assertEqual(summary["mobile_count"], 1)
        self.assertEqual(summary["desktop_count"], 1)
        self.assertEqual(summary["possible_composite_count"], 1)

    def test_auto_style_and_curated_reference_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("2.jpg", "20.jpg", "25.jpg"):
                Image.new("RGB", (600, 1800), "pink").save(root / name)

            resolved_style, references = lab.select_a_plus_reference_paths(
                "auto",
                "desktop_equal",
                custom_prompt="希望是粉紫 Y2K 甜酷风格",
                root=root,
            )

        self.assertEqual(resolved_style, "pink_y2k")
        self.assertEqual([path.name for path in references], ["2.jpg", "20.jpg"])

    def test_lab_instruction_uses_uploads_as_the_only_optional_content_pool(self) -> None:
        instruction = lab.build_a_plus_reference_lab_instruction(
            "clean_blue",
            "mobile_equal",
            product_image_count=4,
            style_reference_count=2,
            auto_repair_crops=True,
        )
        prompt = site.build_main_image_a_plus_free_prompt(
            instruction,
            site.get_main_image_a_plus_layout("mobile_equal"),
            source_pool_only=True,
        )

        self.assertIn("本次只有 4 张用户上传图片", instruction)
        self.assertIn("没有任何图片参考、模板参考或外部元素来源", instruction)
        self.assertIn("所有元素都是可选项", instruction)
        self.assertIn("不得猜测补画", instruction)
        self.assertIn("不加载任何 A++ 文件夹图片", instruction)
        self.assertIn("禁止把电脑版直接缩小或居中裁切", instruction)
        self.assertIn("背景氛围层、中景信息与图形层、前景商品或人物层", instruction)
        self.assertIn("同尺寸、同底色、同圆角卡片机械堆叠", instruction)
        self.assertIn("满版或半满版摄影、超大商品前景、局部特写窗口", instruction)
        self.assertIn("连续品牌色背景、大面积渐变、抽象几何或有机色块", instruction)
        self.assertIn("一个超大主中心、两到四个大中型次中心", instruction)
        self.assertIn("至少要使用 4 组来自不同源图或不同语义组的真实证据", instruction)
        self.assertIn("约 4 个可独立停留的视觉中心", instruction)
        self.assertIn("约 5 个有明显主次变化的内容场景", instruction)
        self.assertIn("不得把全部高价值素材集中在顶部", instruction)
        self.assertIn("选择三至五种并贯穿全图", instruction)
        self.assertIn("一处满版或半满版首屏强视觉", instruction)
        self.assertIn("两处位于不同纵向区域的大中型次视觉锚点", instruction)
        self.assertIn("一组与主体有层叠关系的特写窗口", instruction)
        self.assertIn("相邻两个支撑场景不得连续使用相同的白色底", instruction)
        self.assertIn("禁止新增箭头、编号、图标、徽章", instruction)
        self.assertIn("成品不得出现页边距、相框、白边、黑边", instruction)
        self.assertIn("标尺、箭头和制作批注", instruction)
        self.assertIn("全部输入图都是本次上传素材池", prompt)
        self.assertIn("上传顺序不代表必须使用", prompt)
        self.assertIn("严禁生成素材池中不存在", prompt)
        self.assertIn("2 至 4 个分布在中段和下段且可独立停留的次视觉中心", prompt)
        self.assertIn("一个超大主中心、两到四个大中型次中心", prompt)
        self.assertIn("同一张完整真实素材最多出现两次", prompt)
        self.assertIn("绝不能复制、补画或虚构对象凑数", prompt)
        self.assertNotIn("A++ 风格参考", prompt)

    def test_lab_quality_repair_preserves_multiple_visual_centers(self) -> None:
        review = {
            "composition_score": 6.0,
            "content_richness_score": 5.0,
            "commercial_design_score": 5.5,
            "layout_issues": ["中下段视觉重量不足"],
            "retry_instruction": "增强中段和下段层级",
        }

        retry_instruction = site.build_main_image_a_plus_quality_retry_instruction(
            review,
            multi_visual_centers=True,
        )
        repair_prompt = site.build_main_image_a_plus_free_quality_repair_prompt(
            "只使用上传素材",
            site.get_main_image_a_plus_layout("desktop_equal"),
            review,
            source_reference_count=5,
            source_pool_only=True,
        )

        self.assertIn("中段、下段的两到四个大中型次视觉中心", retry_instruction)
        self.assertIn("保住中段和下段的次视觉中心", repair_prompt)
        self.assertIn("2 至 4 个中下段次视觉中心", repair_prompt)
        self.assertNotIn("第二，只保留一个最强主焦点", repair_prompt)

    def test_composite_reference_is_split_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "paired.jpg"
            composite = Image.new("RGB", (1240, 1800), "white")
            composite.paste(Image.new("RGB", (600, 1800), "red"), (0, 0))
            composite.paste(Image.new("RGB", (600, 1800), "blue"), (640, 0))
            composite.save(reference_path, quality=95)

            prepared = lab.prepare_a_plus_reference_style_input(
                reference_path,
                "mobile_equal",
            )
            with Image.open(io.BytesIO(prepared["data"])) as result_image:
                result_size = result_image.size

        self.assertTrue(prepared["split_applied"])
        self.assertGreaterEqual(result_size[0], 595)
        self.assertLessEqual(result_size[0], 605)
        self.assertEqual(result_size[1], 1800)

    def test_lab_generation_ignores_stale_style_reference_paths(self) -> None:
        product = io.BytesIO()
        Image.new("RGB", (800, 1000), "white").save(product, format="PNG")
        product_input = {
            "data": product.getvalue(),
            "name": "product.png",
            "type": "image/png",
        }
        generated_url = site.image_bytes_to_data_url(product.getvalue(), "image/png")
        reports = [
            {
                "image_index": 1,
                "status": "complete",
                "asset_role": "raw_asset",
                "confidence": 0.99,
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            style_path = Path(temp_dir) / "style.jpg"
            Image.new("RGB", (1464, 2400), "pink").save(style_path, quality=90)
            with (
                patch.object(
                    site,
                    "prepare_main_image_a_plus_sources_with_repair",
                    return_value=([product_input], reports, 0, []),
                ),
                patch.object(
                    site,
                    "call_openrouter_images_api",
                    return_value={"images": [generated_url], "text": ""},
                ) as generate,
                patch.object(
                    site,
                    "review_main_image_a_plus_candidate",
                    return_value={
                        "reviewed": True,
                        "passed": True,
                        "quality_score": 9.2,
                        "critical_issue_count": 0,
                        "cropped_or_edge_touching_text": [],
                        "clipped_foreground": [],
                        "missing_elements": [],
                        "duplicated_elements": [],
                        "text_mismatches": [],
                        "layout_issues": [],
                    },
                ),
            ):
                result = site.run_main_image_a_plus_job(
                    {
                        "model": site.NANO_BANANA_MODEL,
                        "feature": {"key": site.A_PLUS_REFERENCE_LAB_FEATURE_KEY},
                        "prompt": "生成 A+ 测试图",
                        "uploaded_files": [product_input],
                        "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                        "main_image_a_plus_layout_key": "desktop_equal",
                        "a_plus_reference_lab_style_key": "pink_y2k",
                        "a_plus_reference_lab_reference_paths": [str(style_path)],
                    }
                )

        call_kwargs = generate.call_args.kwargs
        self.assertEqual(len(call_kwargs["uploaded_files"]), 1)
        self.assertIn("全部输入图都是本次上传素材池", call_kwargs["prompt"])
        self.assertIn("严禁生成素材池中不存在", call_kwargs["prompt"])
        self.assertNotIn("A++ 风格参考", call_kwargs["prompt"])
        self.assertEqual(result["a_plus_reference_lab_reference_count"], 0)
        self.assertEqual(result["a_plus_reference_lab_reference_names"], [])

    def test_five_lab_uploads_are_combined_in_one_whole_canvas_generation(self) -> None:
        products = []
        for index in range(5):
            product = io.BytesIO()
            Image.new("RGB", (800, 1000), (40 * index, 80, 120)).save(
                product,
                format="PNG",
            )
            products.append(
                {
                    "data": product.getvalue(),
                    "name": f"ad-{index + 1}.png",
                    "type": "image/png",
                }
            )
        section = io.BytesIO()
        Image.new("RGB", (1600, 640), "beige").save(section, format="PNG")
        section_url = site.image_bytes_to_data_url(section.getvalue(), "image/png")
        passed_review = {
            "reviewed": True,
            "passed": True,
            "quality_score": 9.2,
            "critical_issue_count": 0,
            "cropped_or_edge_touching_text": [],
            "clipped_foreground": [],
            "missing_elements": [],
            "duplicated_elements": [],
            "text_mismatches": [],
            "technical_artifacts": [],
            "outer_border_issues": [],
            "layout_issues": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            style_path = Path(temp_dir) / "style.jpg"
            Image.new("RGB", (1464, 2400), "pink").save(style_path, quality=90)
            with (
                patch.object(
                    site,
                    "prepare_main_image_a_plus_sources_with_repair",
                ) as source_repair,
                patch.object(
                    site,
                    "call_openrouter_images_api",
                    return_value={"images": [section_url], "text": ""},
                ) as generate,
                patch.object(
                    site,
                    "review_main_image_a_plus_candidate",
                    return_value=passed_review,
                ) as review_candidate,
            ):
                result = site.run_main_image_a_plus_job(
                    {
                        "feature": {"key": site.A_PLUS_REFERENCE_LAB_FEATURE_KEY},
                        "model": site.NANO_BANANA_MODEL,
                        "prompt": "生成 A+测试图",
                        "uploaded_files": products,
                        "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                        "main_image_a_plus_layout_key": "desktop_equal",
                        "a_plus_reference_lab_style_key": "pink_y2k",
                        "a_plus_reference_lab_reference_paths": [str(style_path)],
                    }
                )

        source_repair.assert_not_called()
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(len(generate.call_args.kwargs["uploaded_files"]), 5)
        self.assertIn("全部输入图都是本次上传素材池", generate.call_args.kwargs["prompt"])
        self.assertIn("每张图、每个元素都可以使用或舍弃", generate.call_args.kwargs["prompt"])
        self.assertIn("分布在中段和下段且可独立停留的次视觉中心", generate.call_args.kwargs["prompt"])
        self.assertNotIn("第 1 张是当前区段唯一", generate.call_args.kwargs["prompt"])
        self.assertTrue(review_candidate.call_args.kwargs["multi_visual_centers"])
        self.assertEqual(review_candidate.call_args.args[1]["target_size"], (1464, 586))
        self.assertFalse(result.get("designed_module_pipeline", False))
        self.assertEqual(result["section_count"], 1)
        self.assertEqual(result["target_size"], (1464, 586))
        self.assertEqual(result["requested_target_size"], (1464, 2400))
        self.assertEqual(result["section_heights"], (586,))
        self.assertTrue(result["width_only_proportional_fit"])
        self.assertEqual(result["a_plus_reference_lab_reference_count"], 0)
        self.assertEqual(result["a_plus_reference_lab_reference_names"], [])


if __name__ == "__main__":
    unittest.main()
