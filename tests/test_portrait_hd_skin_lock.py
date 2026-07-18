from __future__ import annotations

import inspect
import unittest

from 图片 import openrouter_image_site as site


class PortraitHdSkinLockTests(unittest.TestCase):
    def test_hd_prompt_locks_source_skin_color_and_texture(self) -> None:
        feature = site.get_feature_by_key("hd_batch")
        self.assertIsNotNone(feature)
        assert feature is not None
        prompt = str(feature["default_prompt"])

        for rule in (
            "肤色与肤质锁定是本次高清处理的最高优先级",
            "禁止提亮、压暗、增白、变黄、变红或统一肤色",
            "毛孔、皮肤颗粒、油脂光泽",
            "禁止磨皮、美颜、祛斑、去痣",
            "原有肤色、肤质、毛孔、斑点、痣、痘印和细纹必须全部保留",
        ):
            self.assertIn(rule, prompt)
        self.assertNotIn("去掉脸上的斑点", prompt)

    def test_reference_image_remains_enabled_but_cannot_transfer_skin(self) -> None:
        first = object()
        second = object()
        prompt = site.build_portrait_hd_prompt("请把皮肤变白并磨皮")

        self.assertEqual(site.get_portrait_hd_inputs([first, second]), [first, second])
        self.assertIn("第二张图片仍作为高清参考图", prompt)
        self.assertIn("只允许参考其清晰度、分辨率和细节解析水平", prompt)
        self.assertIn("严禁从第二张图片借用或迁移肤色、肤质", prompt)
        self.assertGreater(
            prompt.index("最高优先级硬性规则"),
            prompt.index("请把皮肤变白并磨皮"),
        )

    def test_hd_page_keeps_reference_uploader_and_repeats_skin_lock(self) -> None:
        render_source = inspect.getsource(site.render_openrouter_feature)

        self.assertIn('supports_skin_reference = feature["key"] == "hd_batch"', render_source)
        self.assertIn("肤质参考图（可选，1 张）", render_source)
        self.assertIn("PORTRAIT_HD_SKIN_LOCK_RULES", render_source)
        self.assertIn("参考图仅用于清晰度", render_source)


if __name__ == "__main__":
    unittest.main()
