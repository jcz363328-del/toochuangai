from __future__ import annotations

import inspect
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from 图片 import openrouter_image_site as site


class APlusShopStyleSkillTests(unittest.TestCase):
    def test_all_accounts_receive_the_six_store_presets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.object(site, "A_PLUS_SKILL_ROOT", Path(temporary_directory)):
                presets = site.list_builtin_a_plus_layout_skills()
                self.assertEqual(
                    [str(skill.get("skill_id") or "") for skill in presets],
                    [
                        "builtin-shop-3-desktop",
                        "builtin-shop-3-mobile",
                        "builtin-shop-15-desktop",
                        "builtin-shop-15-mobile",
                        "builtin-shop-28-desktop",
                        "builtin-shop-28-mobile",
                    ],
                )
                self.assertEqual(
                    [str(skill.get("device") or "") for skill in presets],
                    ["desktop", "mobile", "desktop", "mobile", "desktop", "mobile"],
                )
                self.assertTrue(all(skill.get("is_builtin") for skill in presets))
                self.assertTrue(all(skill.get("created_by") == "system" for skill in presets))
                self.assertEqual(site.list_a_plus_layout_skills("alice"), [])
                self.assertEqual(
                    [skill["skill_id"] for skill in site.list_available_a_plus_layout_skills("alice")],
                    [skill["skill_id"] for skill in presets],
                )

    def test_builtin_context_contains_private_prompt_and_generated_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.object(site, "A_PLUS_SKILL_ROOT", Path(temporary_directory)):
                context = site.get_active_a_plus_layout_skill_context(
                    "alice",
                    "builtin-shop-3-mobile",
                )

        self.assertTrue(context["is_builtin"])
        self.assertEqual(context["store_key"], "3")
        self.assertEqual(context["device"], "mobile")
        self.assertEqual(context["target_size"], (600, 1800))
        self.assertIn("端型适配规则", context["prompt"])
        self.assertIn("模块编排规则", context["prompt"])
        for source_identity in ("ALICROWN", "EYDEVRO", "wiwoseo"):
            self.assertNotIn(source_identity, context["prompt"])

        skeleton = context["skeleton"]
        self.assertIsInstance(skeleton, dict)
        self.assertEqual(skeleton["type"], "image/png")
        with Image.open(io.BytesIO(bytes(skeleton["data"]))) as image:
            self.assertGreaterEqual(image.width, 320)
            self.assertGreaterEqual(image.height, 640)
            self.assertGreater(image.height, image.width)
            self.assertAlmostEqual(image.width / image.height, 1 / 3, places=2)

    def test_builtin_skill_cannot_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.object(site, "A_PLUS_SKILL_ROOT", Path(temporary_directory)):
                with self.assertRaisesRegex(RuntimeError, "预置"):
                    site.delete_a_plus_layout_skill("alice", "builtin-shop-15-desktop")

    def test_learning_uploader_is_removed_from_the_rendered_builder(self) -> None:
        source = inspect.getsource(site.render_a_plus_layout_skill_builder)
        style_source = inspect.getsource(site.inject_app_styles)

        self.assertNotIn("优秀 A+ 案例学习", source)
        self.assertNotIn("a_plus_layout_skill_cases_", source)
        self.assertIn("本次使用的 A+ 版式 Skill", source)
        self.assertIn("a-plus-skill-summary", source)
        self.assertIn('st.expander("查看版式结构（可选）", expanded=False)', source)
        self.assertIn('width=128 if device == "mobile" else 180', source)
        self.assertIn("a-plus-skill-summary", style_source)


if __name__ == "__main__":
    unittest.main()
