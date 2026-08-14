from __future__ import annotations

import base64
import inspect
import io
import unittest
from unittest.mock import patch

from PIL import Image

from 图片 import openrouter_image_site as site


def image_data_url(width: int = 120, height: int = 240) -> str:
    image = Image.new("RGB", (width, height), "white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


class APlusTextEditTests(unittest.TestCase):
    def test_prompt_locks_everything_except_clicked_text_block(self) -> None:
        prompt = site.build_main_image_a_plus_text_edit_prompt(
            (325, 640),
            "NEW PRODUCT TITLE",
            "Montserrat",
        )

        self.assertIn("(325, 640)", prompt)
        self.assertIn("NEW PRODUCT TITLE", prompt)
        self.assertIn("Montserrat", prompt)
        self.assertIn("只允许编辑这一处文字块", prompt)
        self.assertIn("必须清除旧文字的全部笔画和残影", prompt)
        self.assertIn("新文案必须逐字准确", prompt)
        self.assertIn("绝对锁定目标文字块以外的全部画面", prompt)
        self.assertIn("禁止顺带润色", prompt)
        self.assertIn("不得裁切、溢出、贴边", prompt)

    def test_text_edit_job_uses_source_dimensions_and_single_reference(self) -> None:
        source = image_data_url()
        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={"images": ["data:image/png;base64,generated"], "text": ""},
            ) as mocked_call,
            patch.object(
                site,
                "cover_image_to_exact_size",
                return_value="data:image/png;base64,final",
            ) as mocked_fit,
        ):
            result = site.run_main_image_a_plus_text_edit_job(
                {
                    "model": site.NANO_BANANA_MODEL,
                    "main_image_a_plus_text_edit_source": source,
                    "main_image_a_plus_text_edit_point": (250, 500),
                    "main_image_a_plus_text_edit_content": "Natural Volume",
                    "main_image_a_plus_text_edit_font": "Didot / Bodoni 高级衬线",
                }
            )

        self.assertEqual(result["images"], ["data:image/png;base64,final"])
        self.assertEqual(result["target_size"], (120, 240))
        self.assertEqual(
            result["main_image_a_plus_mode"],
            site.MAIN_IMAGE_A_PLUS_MODE_TEXT_EDIT,
        )
        self.assertEqual(result["main_image_a_plus_text_edit_source"], source)
        self.assertEqual(result["main_image_a_plus_text_edit_point"], (250, 500))
        call_kwargs = mocked_call.call_args.kwargs
        self.assertEqual(len(call_kwargs["uploaded_files"]), 1)
        self.assertEqual(call_kwargs["resolution"], site.AMAZON_A_PLUS_NATIVE_IMAGE_SIZE)
        self.assertIn("Natural Volume", call_kwargs["prompt"])
        self.assertIn("Didot / Bodoni 高级衬线", call_kwargs["prompt"])
        mocked_fit.assert_called_once_with(
            "data:image/png;base64,generated",
            120,
            240,
        )

    def test_dispatch_allows_text_edit_without_new_uploads(self) -> None:
        expected = {"images": ["edited"]}
        with (
            patch.object(
                site,
                "run_main_image_a_plus_text_edit_job",
                return_value=expected,
            ) as mocked_run,
            patch.object(
                site,
                "finalize_feature_job_result",
                return_value=expected,
            ) as mocked_finalize,
        ):
            result = site.run_feature_job(
                {
                    "feature": {"key": site.MAIN_IMAGE_A_PLUS_FEATURE_KEY},
                    "main_image_a_plus_text_edit": True,
                    "uploaded_files": [],
                }
            )

        self.assertEqual(result, expected)
        mocked_run.assert_called_once()
        mocked_finalize.assert_called_once()

    def test_current_result_and_history_expose_text_editor(self) -> None:
        editor_source = inspect.getsource(site.render_main_image_a_plus_text_editor)
        page_source = inspect.getsource(site.render_openrouter_feature)
        history_source = inspect.getsource(site.render_history_gallery)

        self.assertIn("编辑文字内容与字体", editor_source)
        self.assertIn("修改后的文字内容", editor_source)
        self.assertIn("MAIN_IMAGE_A_PLUS_TEXT_FONT_OPTIONS", editor_source)
        self.assertIn("点击成品图中的目标文字", editor_source)
        self.assertIn("submit_main_image_a_plus_text_edit", editor_source)
        self.assertIn("render_main_image_a_plus_text_editor", page_source)
        self.assertIn("文字编辑前", page_source)
        self.assertIn("文字编辑后", page_source)
        self.assertIn("render_main_image_a_plus_text_editor", history_source)


if __name__ == "__main__":
    unittest.main()
