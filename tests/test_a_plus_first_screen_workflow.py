from __future__ import annotations

import inspect
import re
import unittest
from unittest.mock import patch

from Department.视觉设计部.xiaoha import openrouter_image_site as site


class APlusFirstScreenWorkflowTests(unittest.TestCase):
    def test_unified_workflow_always_uses_pixel_protected_composition(self) -> None:
        feature = site.get_feature_by_key(site.A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY)
        for stage in (None, 'combined', 'selling_points', 'hero'):
            with self.subTest(stage=stage):
                context = {'feature': feature, 'uploaded_files': [{'name': 'hero'}, {'name': 'selling'}],
                           'output_mode': 'image', 'model': site.NANO_BANANA_MODEL,
                           'a_plus_first_screen_workflow_stage': stage}
                protected = {'images': ['pixel-protected-result']}
                with patch.object(site, 'run_first_screen_selling_points_job', return_value=protected) as compose, \
                        patch.object(site, 'call_openrouter_images_api') as provider, \
                        patch.object(site, 'finalize_feature_job_result', side_effect=lambda c, r, j: r):
                    self.assertEqual(site.run_feature_job(context), protected)
                compose.assert_called_once_with(context)
                provider.assert_not_called()

    def test_feature_requires_base_and_optional_material_selection_without_crop(self) -> None:
        feature = site.get_feature_by_key(site.A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY)
        self.assertEqual(feature['min_images'], 2)
        self.assertEqual(feature['max_input_images'], 10)
        prompt = re.sub(r'\s+', '', feature['default_prompt'])
        self.assertIn('第1张', prompt)
        self.assertRegex(prompt, r'整张|所有|全部')
        self.assertIn('留白', prompt)
        self.assertRegex(prompt, r'不裁切|不得裁切|禁止裁切')
        self.assertRegex(prompt, r'放不下|无法完整|空间不足|不够|元素太大|比例不适合')
        self.assertRegex(prompt, r'省略|舍弃|不用|不采用')
        self.assertNotIn('元素时除外', prompt)

    def test_completed_hero_is_saved_separately_from_latest_result(self) -> None:
        source = inspect.getsource(site._feature_helpers.store_completed_background_job_result)
        self.assertIn('a_plus_first_screen_workflow_stage', source)
        self.assertIn('a_plus_first_screen_hero_results', source)

    def test_remove_text_request_cannot_override_original_image_protection(self) -> None:
        feature = site.get_feature_by_key(site.A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY)
        prompt = site.build_prompt(feature, '去掉参考图上的所有文字', '自动', '')
        normalized = re.sub(r'\s+', '', prompt)
        self.assertIn('去掉参考图上的所有文字', prompt)
        self.assertIn('新增', prompt)
        self.assertIn('第1张', normalized)
        self.assertRegex(prompt, r'不能|不得|不允许')
        self.assertNotIn('最高优先级', prompt)
        self.assertNotIn('必须删除用户所指参考图中的全部目标文字', prompt)
        self.assertNotIn('元素时除外', prompt)

    def test_design_request_is_scoped_to_new_material_only(self) -> None:
        override = site.build_a_plus_first_screen_user_override('整体改成蓝色科技风')
        self.assertIn('整体改成蓝色科技风', override)
        self.assertIn('新增', override)
        self.assertIn('第1张', re.sub(r'\s+', '', override))
        self.assertRegex(override, r'不能|不得|不允许')
        self.assertNotIn('最高优先级', override)
        self.assertEqual(site.build_a_plus_first_screen_user_override('  '), '')


if __name__ == '__main__':
    unittest.main()
