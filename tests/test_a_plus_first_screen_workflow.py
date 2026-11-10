from __future__ import annotations

import inspect
import unittest

from 图片 import openrouter_image_site as site


class APlusFirstScreenWorkflowTests(unittest.TestCase):
    def test_ui_exposes_combined_and_staged_generation(self) -> None:
        source = inspect.getsource(site.render_openrouter_feature)

        self.assertIn('options=("combined", "staged")', source)
        self.assertIn('"第 1 步 · 生成首屏"', source)
        self.assertIn('"第 2 步 · 续写下方卖点"', source)
        self.assertIn('max_files=1', source)
        self.assertIn('max_files=9', source)

    def test_selling_point_step_reuses_the_locked_hero(self) -> None:
        source = inspect.getsource(site.render_openrouter_feature)

        self.assertIn('load_image_bytes_from_url(str(hero_images[0]))', source)
        self.assertIn('"name": f"locked_first_screen{hero_extension}"', source)
        self.assertIn('files.insert(', source)
        self.assertIn('相同商品视角、元素、文案和卖点在整张图中只能出现一次', source)

    def test_completed_hero_is_saved_separately_from_latest_result(self) -> None:
        source = inspect.getsource(site.store_completed_background_job_result)

        self.assertIn('a_plus_first_screen_workflow_stage', source)
        self.assertIn('a_plus_first_screen_hero_results', source)

    def test_user_prompt_overrides_reference_text_preservation(self) -> None:
        feature = site.get_feature_by_key(site.A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY)
        self.assertIsNotNone(feature)

        prompt = site.build_prompt(feature, "去掉参考图上的所有文字", "自动", "")

        self.assertTrue(prompt.startswith("【用户编辑目标｜最高优先级】"))
        self.assertIn("必须删除用户所指参考图中的全部目标文字", prompt)
        self.assertIn("不得照抄、重绘、近似复刻", prompt)
        self.assertGreaterEqual(prompt.count("【用户编辑目标｜最高优先级】"), 2)

    def test_non_removal_user_prompt_is_still_marked_highest_priority(self) -> None:
        override = site.build_a_plus_first_screen_user_override("整体改成蓝色科技风")

        self.assertIn("最高优先级", override)
        self.assertIn("整体改成蓝色科技风", override)
        self.assertNotIn("已识别为去文字任务", override)


if __name__ == "__main__":
    unittest.main()
