from __future__ import annotations

import unittest
from unittest.mock import patch

from 图片 import openrouter_image_site as site


class PromptFrontendPrivacyTests(unittest.TestCase):
    def test_frontend_result_drops_internal_prompt_and_provider_payload(self) -> None:
        source = {
            "images": ["data:image/png;base64,abc"],
            "prompt": "内部提示词",
            "request_prompt": "内部请求提示词",
            "raw": {"request": {"prompt": "供应商原始提示词"}},
            "history_records": [
                {
                    "feature_name": "模特图批量高清",
                    "prompt": "历史内部提示词",
                    "images": ["thumb.png"],
                }
            ],
        }

        frontend_result = site.prepare_result_for_frontend(source)

        self.assertNotIn("prompt", frontend_result)
        self.assertNotIn("request_prompt", frontend_result)
        self.assertNotIn("raw", frontend_result)
        self.assertNotIn("prompt", frontend_result["history_records"][0])
        self.assertEqual(source["prompt"], "内部提示词")

    def test_local_history_records_never_retain_prompt(self) -> None:
        with (
            patch.object(site, "normalize_history_image_source", return_value="image-data"),
            patch.object(site, "build_history_thumbnail_source", return_value="thumb-data"),
        ):
            records = site.build_local_history_records(
                feature={"key": "hd_batch", "name": "模特图批量高清"},
                model="test-model",
                prompt="绝密提示词",
                result={"images": ["source-image"]},
                account_name="tester",
            )

        self.assertEqual(len(records), 1)
        self.assertNotIn("prompt", records[0])

    def test_unknown_openrouter_error_does_not_echo_request_payload(self) -> None:
        message = site.format_user_facing_error_message(
            'OpenRouter 请求失败：{"prompt":"绝密提示词","error":"provider rejected"}'
        )

        self.assertNotIn("绝密提示词", message)
        self.assertNotIn("prompt", message.lower())

    def test_image_safety_error_keeps_safe_user_guidance(self) -> None:
        message = site.format_user_facing_error_message(
            "OpenRouter Images API 请求失败：Gemini blocked the request (IMAGE_SAFETY)"
        )

        self.assertIn("安全审核", message)
        self.assertNotIn("IMAGE_SAFETY", message)


if __name__ == "__main__":
    unittest.main()
