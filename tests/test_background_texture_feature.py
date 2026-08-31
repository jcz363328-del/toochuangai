from __future__ import annotations

import inspect
import unittest

from 图片 import openrouter_image_site as site


class BackgroundTextureFeatureTests(unittest.TestCase):
    def test_feature_is_visible_with_texture_presets_and_custom_prompt_controls(self) -> None:
        feature = site.get_feature_by_key(site.BACKGROUND_TEXTURE_FEATURE_KEY)
        self.assertIsNotNone(feature)
        assert feature is not None
        self.assertEqual(feature["name"], "场景背景质感")
        self.assertEqual(feature["max_output_images"], 1)
        self.assertIn(site.BACKGROUND_TEXTURE_FEATURE_KEY, {
            item["key"] for item in site.get_visible_features()
        })
        self.assertGreaterEqual(len(site.BACKGROUND_TEXTURE_PRESETS), 10)

        render_source = inspect.getsource(site.render_openrouter_feature)
        self.assertIn("st.multiselect", render_source)
        self.assertIn("background_texture_prompt", render_source)
        self.assertIn("开始更换质感", render_source)

    def test_selected_presets_and_direct_description_are_combined(self) -> None:
        instruction = site.build_background_texture_instruction(
            ["微水泥", "拉丝金属"],
            "暖灰色，纹理轻一些",
        )

        self.assertIn("微水泥", instruction)
        self.assertIn("拉丝金属", instruction)
        self.assertIn("暖灰色，纹理轻一些", instruction)
        self.assertIn("用户描述优先", instruction)
        self.assertIn("人物、商品", instruction)

    def test_generation_prompt_locks_subject_and_keeps_original_aspect_ratio(self) -> None:
        feature = site.get_feature_by_key(site.BACKGROUND_TEXTURE_FEATURE_KEY)
        assert feature is not None
        custom_prompt = site.build_background_texture_instruction(["柔雾磨砂"], "低反光")

        prompt = site.build_prompt(feature, custom_prompt, "16:9", "只返回一张完成图")

        self.assertIn("只允许改变场景背景表面", prompt)
        self.assertIn("人物、脸部、五官", prompt)
        self.assertIn("柔雾磨砂", prompt)
        self.assertIn("低反光", prompt)
        self.assertNotIn("目标画幅比例：16:9", prompt)
        self.assertIn("原始比例不变", prompt)


if __name__ == "__main__":
    unittest.main()
