from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from 图片 import openrouter_image_site as site


def image_input(width: int, height: int, name: str, color: str = "white") -> dict[str, object]:
    output = io.BytesIO()
    Image.new("RGB", (width, height), color).save(output, format="PNG")
    return {"name": name, "type": "image/png", "data": output.getvalue()}


def image_data_url(width: int = 200, height: int = 300) -> str:
    image_bytes = image_input(width, height, "result.png")["data"]
    return f"data:image/png;base64,{base64.b64encode(bytes(image_bytes)).decode('ascii')}"


def analysis_payload(case_count: int = 2) -> dict[str, object]:
    case = {
        "style": "高端黑金",
        "design_strengths": ["视觉中心清晰", "留白克制"],
        "hero": {
            "height_ratio": 32,
            "visual_center": [520, 220],
            "product_position": "右下",
            "model_position": "左侧",
            "text_blocks": "两块",
            "text_area_ratio": 0.15,
            "elements": [
                {"type": "product", "bbox": [580, 60, 960, 330], "overlap": "前景"},
                {"type": "title", "bbox": [80, 90, 420, 190], "alignment": "左对齐"},
            ],
        },
        "sections": [
            {"type": "hero", "height_ratio": 0.32, "bbox": [0, 0, 1000, 320]},
            {"type": "selling_points", "height_ratio": 0.23, "bbox": [0, 320, 1000, 550]},
            {"type": "details", "height_ratio": 0.25, "bbox": [0, 550, 1000, 800]},
            {"type": "package", "height_ratio": 0.20, "bbox": [0, 800, 1000, 1000]},
        ],
        "typography": {
            "hierarchy": ["品牌", "主标题", "辅助文案"],
            "text_blocks": "6",
            "density": "低",
            "alignment": "左对齐",
            "max_title_lines": "2.0",
        },
        "background": {
            "palette": ["#111111", "#C9A45C", "not-a-color"],
            "lighting": "侧逆光",
            "decorative_language": "克制线条",
            "depth": "前中后景",
            "continuity": "背景跨区连续",
        },
        "reading_flow": ["首屏主视觉", "卖点", "细节", "包装"],
        "cross_section_elements": [],
        "product_regions": [
            {"type": "product", "bbox": [580, 60, 960, 330], "overlap": "不遮挡标题"}
        ],
    }
    return {
        "cases": [dict(case) for _ in range(case_count)],
        "common": {
            **case,
            "reading_flow": ["首屏主视觉", "卖点", "细节", "包装"],
            "cross_section_rules": ["背景自然跨区"],
            "product_placement_rules": ["产品完整且不被文字遮挡"],
            "anti_patterns": ["素材堆叠", "硬分割"],
        },
    }


class APlusLayoutSkillTests(unittest.TestCase):
    def test_normalization_uses_real_canvas_and_tolerates_nonnumeric_counts(self) -> None:
        cases = [
            image_input(1464, 2400, "desktop.png"),
            image_input(600, 1800, "mobile.png"),
        ]

        normalized = site.normalize_a_plus_layout_skill_analysis(analysis_payload(), cases)

        self.assertEqual(normalized["case_count"], 2)
        self.assertEqual(normalized["cases"][0]["canvas"]["width"], 1464)
        self.assertEqual(normalized["cases"][1]["canvas"]["height"], 1800)
        self.assertEqual(normalized["common"]["hero"]["height_ratio"], 0.32)
        self.assertEqual(normalized["common"]["hero"]["text_blocks"], 0)
        self.assertEqual(normalized["common"]["typography"]["max_title_lines"], 2)
        self.assertEqual(normalized["common"]["background"]["palette"], ["#111111", "#C9A45C"])
        self.assertAlmostEqual(
            sum(section["height_ratio"] for section in normalized["common"]["sections"]),
            1.0,
            places=3,
        )

    def test_analysis_prompt_is_structural_private_and_incremental(self) -> None:
        prompt = site.build_a_plus_layout_analysis_prompt(
            [image_input(1464, 2400, "case.png")],
            previous_common={"style": "过去沉淀的版式"},
        )

        self.assertIn("1464×2400px", prompt)
        self.assertIn("过去沉淀的版式", prompt)
        self.assertIn("只学习设计结构", prompt)
        self.assertIn("严禁在 JSON 中输出 OCR 原文", prompt)
        self.assertIn("增量合并", prompt)

    def test_analysis_sends_only_current_cases_to_vision_model(self) -> None:
        current_cases = [image_input(600, 1800, "new-case.png")]
        response = "```json\n" + json.dumps(analysis_payload(1), ensure_ascii=False) + "\n```"

        with patch.object(site, "call_openrouter", return_value={"text": response}) as request:
            result = site.analyze_a_plus_layout_cases(
                current_cases,
                previous_common={"style": "旧版式原则"},
            )

        self.assertEqual(result["case_count"], 1)
        self.assertEqual(request.call_args.kwargs["uploaded_files"], current_cases)
        self.assertIn("旧版式原则", request.call_args.kwargs["prompt"])

    def test_save_writes_manifest_skeleton_skill_and_database_registration(self) -> None:
        case = image_input(1464, 2400, "excellent.png", "navy")
        normalized = site.normalize_a_plus_layout_skill_analysis(analysis_payload(1), [case])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with (
                patch.object(site, "A_PLUS_SKILL_ROOT", root),
                patch.object(site, "execute_db_non_query") as db_write,
            ):
                manifest = site.save_a_plus_layout_skill(
                    [case],
                    normalized,
                    title="高端通用布局",
                    account_name="tester",
                )

                self.assertTrue(Path(manifest["manifest_path"]).is_file())
                self.assertTrue(Path(manifest["skeleton_path"]).is_file())
                self.assertTrue(Path(manifest["skill_prompt_path"]).is_file())
                self.assertTrue(site.get_a_plus_layout_skill_user_pointer_path("tester").is_file())
                self.assertTrue(Path(manifest["source_files"][0]["file"]).is_file())
                with Image.open(manifest["skeleton_path"]) as skeleton:
                    self.assertGreaterEqual(skeleton.width, 320)
                    self.assertGreaterEqual(skeleton.height, 640)

                db_write.assert_called_once()
                query, parameters = db_write.call_args.args
                self.assertIn("[AI_skills]", query)
                self.assertIn("[YongHu]", query)
                self.assertEqual(parameters[0], "A+生成")
                self.assertEqual(parameters[1], str(root))
                self.assertEqual(parameters[2], "tester")
                self.assertIsInstance(parameters[3], date)

                active = site.get_active_a_plus_layout_skill_context("tester")
                self.assertEqual(active["skill_id"], manifest["skill_id"])
                self.assertEqual(active["created_by"], "tester")
                self.assertNotIn("source_files", active)
                self.assertIn("绝对禁止", active["prompt"])

    def test_skills_are_listed_selected_and_inherited_per_user(self) -> None:
        case = image_input(600, 1800, "case.png", "purple")
        normalized = site.normalize_a_plus_layout_skill_analysis(analysis_payload(1), [case])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with (
                patch.object(site, "A_PLUS_SKILL_ROOT", root),
                patch.object(site, "execute_db_non_query"),
            ):
                alice_first = site.save_a_plus_layout_skill(
                    [case], normalized, title="Alice 第一版", account_name="alice"
                )
                bob_skill = site.save_a_plus_layout_skill(
                    [case], normalized, title="Bob 版式", account_name="bob"
                )
                alice_second = site.save_a_plus_layout_skill(
                    [case], normalized, title="Alice 第二版", account_name="alice"
                )

                alice_skills = site.list_a_plus_layout_skills("alice")
                bob_skills = site.list_a_plus_layout_skills("bob")
                self.assertEqual(len(alice_skills), 2)
                self.assertEqual(len(bob_skills), 1)
                self.assertTrue(all(skill["created_by"] == "alice" for skill in alice_skills))
                self.assertEqual(bob_skills[0]["skill_id"], bob_skill["skill_id"])
                self.assertEqual(alice_second["parent_skill_id"], alice_first["skill_id"])

                selected = site.get_active_a_plus_layout_skill_context(
                    "alice", alice_first["skill_id"]
                )
                self.assertEqual(selected["skill_id"], alice_first["skill_id"])
                self.assertEqual(
                    site.get_active_a_plus_layout_skill_context("alice", bob_skill["skill_id"]),
                    {},
                )
                self.assertEqual(site.get_active_a_plus_layout_skill_context("alice", ""), {})

    def test_main_a_plus_generation_uses_skeleton_but_not_saved_cases(self) -> None:
        layout = site.get_main_image_a_plus_layout("desktop_equal")
        user_product = image_input(240, 320, "current-product.png", "red")
        skeleton = image_input(320, 640, "layout_skeleton.png", "gray")

        with patch.object(
            site,
            "call_openrouter_images_api",
            return_value={"images": [image_data_url()], "text": ""},
        ) as request:
            result = site.run_main_image_a_plus_job(
                {
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "本次商品生成",
                    "uploaded_files": [user_product],
                    "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                    "main_image_a_plus_layout": layout,
                    "a_plus_layout_skill_id": "skill-001",
                    "a_plus_layout_skill_skeleton": skeleton,
                }
            )

        names = [str(item.get("name") or "") for item in request.call_args.kwargs["uploaded_files"]]
        self.assertEqual(len(names), 2)
        self.assertIn("current-product", names[0])
        self.assertIn("layout_skeleton", names[1])
        self.assertFalse(any("excellent" in name or "case" in name for name in names))
        self.assertEqual(result["layout_skill_id"], "skill-001")
        self.assertTrue(result["layout_skill_skeleton_used"])

    def test_skeleton_is_skipped_when_all_reference_slots_are_used(self) -> None:
        references = [image_input(80, 80, f"product-{index}.png") for index in range(10)]
        layout = site.get_main_image_a_plus_layout("mobile_equal")

        with patch.object(
            site,
            "call_openrouter_images_api",
            return_value={"images": [image_data_url()], "text": ""},
        ) as request:
            result = site.run_main_image_a_plus_job(
                {
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "满额参考图",
                    "uploaded_files": references,
                    "main_image_a_plus_mode": site.MAIN_IMAGE_A_PLUS_MODE_FREE,
                    "main_image_a_plus_layout": layout,
                    "a_plus_layout_skill_skeleton": image_input(320, 640, "layout_skeleton.png"),
                }
            )

        self.assertEqual(len(request.call_args.kwargs["uploaded_files"]), 10)
        self.assertFalse(result["layout_skill_skeleton_used"])

    def test_free_psd_generation_receives_only_current_references_and_skeleton(self) -> None:
        feature = site.get_feature_by_key(site.AMAZON_A_PLUS_FEATURE_KEY)
        assert feature is not None
        current_product = image_input(180, 260, "current-product.png", "green")
        skeleton = image_input(320, 640, "layout_skeleton.png", "gray")

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={"images": [image_data_url()], "text": ""},
            ) as request,
            patch.object(site, "build_amazon_a_plus_layered_result", side_effect=lambda result, _size: result),
            patch.object(site, "finalize_feature_job_result", side_effect=lambda _context, result, _job_id: result),
        ):
            result = site.run_feature_job(
                {
                    "feature": dict(feature),
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "自由创作 PSD",
                    "uploaded_files": [current_product],
                    "output_mode": "image",
                    "target_size": (600, 1800),
                    "aspect_ratio": site.DEFAULT_ASPECT_RATIO,
                    "max_output_images": 1,
                    "a_plus_layout_skill_id": "skill-psd",
                    "a_plus_layout_skill_skeleton": skeleton,
                }
            )

        names = [str(item.get("name") or "") for item in request.call_args.kwargs["uploaded_files"]]
        self.assertEqual(names, ["current-product.png", "layout_skeleton.png"])
        self.assertEqual(result["layout_skill_id"], "skill-psd")
        self.assertTrue(result["layout_skill_skeleton_used"])


if __name__ == "__main__":
    unittest.main()
