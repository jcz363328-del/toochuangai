from __future__ import annotations

import io
import inspect
import unittest
from unittest.mock import patch

from PIL import Image

from 图片 import openrouter_image_site as site


class PortraitHdSkinLockTests(unittest.TestCase):
    @staticmethod
    def make_image_input(size: tuple[int, int], name: str = "source.png") -> dict[str, object]:
        image = Image.new("RGB", size, (80, 120, 160))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return {"data": output.getvalue(), "name": name, "type": "image/png"}

    @staticmethod
    def read_result_size(image_url: str) -> tuple[int, int]:
        image_bytes, _mime_type = site.load_image_bytes_from_url(image_url)
        with Image.open(io.BytesIO(image_bytes)) as image:
            return image.size

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
            "整张画面的色温与色调锁定也是本次高清处理的最高优先级",
            "整体与局部色温、冷暖关系、综合色调、色相、白平衡",
            "禁止自动白平衡、自动校色、调色、重新定色",
        ):
            self.assertIn(rule, prompt)
        self.assertNotIn("去掉脸上的斑点", prompt)

    def test_hd_prompt_overrides_requests_to_change_temperature_or_tone(self) -> None:
        prompt = site.build_portrait_hd_prompt("把画面调暖一点，增加电影色调和饱和度")

        self.assertIn("色温与色调锁定也是本次高清处理的最高优先级", prompt)
        self.assertIn("色温、色调、白平衡和全部颜色关系必须逐项保持第1张原图状态", prompt)
        self.assertIn("禁止任何自动校色或风格化调色", prompt)
        self.assertIn("严禁迁移其色温、色调、白平衡、曝光、对比度", prompt)
        self.assertGreater(
            prompt.index("最高优先级硬性规则"),
            prompt.index("把画面调暖一点"),
        )

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
        self.assertIn("PORTRAIT_HD_COLOR_LOCK_RULES", render_source)
        self.assertIn("参考图仅用于清晰度", render_source)
        self.assertIn("色温、色调、白平衡及原有颜色关系", render_source)

    def test_hd_prompt_locks_canvas_to_source_dimensions_without_cropping(self) -> None:
        source = self.make_image_input((137, 91))

        instruction = site.build_portrait_hd_size_instruction(source)
        prompt = site.build_portrait_hd_prompt("只做高清")

        self.assertIn("137×91px", instruction)
        self.assertIn("禁止裁剪、扩图、补边", instruction)
        self.assertIn("像素宽度和像素高度必须分别与第1张原图完全一致", prompt)
        self.assertIn("完整保留原图上下左右四边", prompt)

    def test_hd_result_is_restored_to_source_size_without_edge_crop(self) -> None:
        source = self.make_image_input((10, 10))
        generated = Image.new("RGB", (30, 10), (20, 180, 20))
        for y in range(generated.height):
            for x in range(0, 8):
                generated.putpixel((x, y), (240, 10, 10))
            for x in range(22, 30):
                generated.putpixel((x, y), (10, 10, 240))
        generated_output = io.BytesIO()
        generated.save(generated_output, format="PNG")
        generated_url = site.image_bytes_to_data_url(generated_output.getvalue(), "image/png")

        restored_url = site.restore_portrait_hd_source_size(generated_url, source)
        restored_bytes, _mime_type = site.load_image_bytes_from_url(restored_url)
        with Image.open(io.BytesIO(restored_bytes)) as restored:
            self.assertEqual(restored.size, (10, 10))
            self.assertGreater(restored.getpixel((0, 5))[0], restored.getpixel((0, 5))[2])
            self.assertGreater(restored.getpixel((9, 5))[2], restored.getpixel((9, 5))[0])

    def test_openrouter_hd_uses_source_ratio_and_returns_exact_source_size(self) -> None:
        source = self.make_image_input((137, 91))
        reference = self.make_image_input((64, 64), name="reference.png")
        generated = self.make_image_input((2048, 2048), name="generated.png")
        generated_url = site.image_bytes_to_data_url(bytes(generated["data"]), "image/png")

        with patch.object(
            site,
            "call_openrouter_images_api",
            return_value={"images": [generated_url], "text": ""},
        ) as mocked_call:
            result = site.call_openrouter_portrait_hd(
                model="test-model",
                prompt="只做高清",
                aspect_ratio="1:1",
                uploaded_files=[source, reference],
            )

        self.assertEqual(self.read_result_size(result["images"][0]), (137, 91))
        self.assertEqual(result["target_size"], (137, 91))
        self.assertEqual(
            mocked_call.call_args.kwargs["aspect_ratio"],
            site.select_closest_aspect_ratio((137, 91)),
        )
        self.assertIn("最终结果必须严格为 137×91px", mocked_call.call_args.kwargs["prompt"])


if __name__ == "__main__":
    unittest.main()
