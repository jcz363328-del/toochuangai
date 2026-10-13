from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from 图片 import openrouter_image_site as site


class RemoveEyelashesImagesApiTests(unittest.TestCase):
    @staticmethod
    def make_image_input(
        size: tuple[int, int] = (600, 900),
        name: str = "source.png",
    ) -> dict[str, object]:
        image = Image.new("RGB", size, (120, 90, 70))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return {"data": output.getvalue(), "name": name, "type": "image/png"}

    def test_remove_eyelashes_uses_dedicated_images_api_and_source_ratio(self) -> None:
        source = self.make_image_input()
        feature = site.get_feature_by_key("remove_eyelashes")
        assert feature is not None
        generated_url = "data:image/png;base64,aW1hZ2U="
        expected_ratio = site.get_uploaded_input_closest_aspect_ratio(source, fallback="自动")
        job_context = {
            "feature": feature,
            "model": site.NANO_BANANA_MODEL,
            "prompt": str(feature["default_prompt"]),
            "output_mode": "image",
            "aspect_ratio": "自动",
            "max_output_images": 1,
        }

        with (
            patch.object(
                site,
                "call_openrouter_images_api",
                return_value={"images": [generated_url], "text": ""},
            ) as images_api,
            patch.object(
                site,
                "call_openrouter",
                side_effect=AssertionError("legacy chat image endpoint must not be used"),
            ),
            patch.object(site, "upscale_image_to_min_edge", side_effect=lambda image_url, *_args, **_kwargs: image_url),
        ):
            result = site.process_batch_group(job_context, [source], 1)

        self.assertEqual(result["images"], [generated_url])
        self.assertEqual(images_api.call_count, 1)
        request = images_api.call_args.kwargs
        self.assertEqual(request["model"], site.NANO_BANANA_MODEL)
        self.assertEqual(request["uploaded_files"], [source])
        self.assertEqual(request["aspect_ratio"], expected_ratio)
        self.assertEqual(request["resolution"], site.REMOVE_EYELASHES_IMAGE_RESOLUTION)

    def test_images_api_retries_http_429_then_succeeds(self) -> None:
        throttled = Mock(status_code=429)
        throttled.json.return_value = {"error": {"message": "Rate limit exceeded", "code": 429}}
        success = Mock(status_code=200)
        success.json.return_value = {
            "data": [{"b64_json": "aW1hZ2U=", "media_type": "image/png"}]
        }

        with (
            patch.object(site, "load_api_key", return_value="test-key"),
            patch.object(site.requests, "post", side_effect=[throttled, success]) as request_post,
            patch.object(site.time, "sleep") as retry_sleep,
        ):
            result = site.call_openrouter_images_api(
                model=site.NANO_BANANA_MODEL,
                prompt="remove eyelashes",
            )

        self.assertEqual(request_post.call_count, 2)
        retry_sleep.assert_called_once()
        self.assertEqual(result["images"], ["data:image/png;base64,aW1hZ2U="])

    def test_images_api_failure_keeps_http_status_and_error_code(self) -> None:
        failed_one = Mock(status_code=503)
        failed_one.json.return_value = {
            "error": {"message": "Provider unavailable", "code": "provider_error"}
        }
        failed_two = Mock(status_code=503)
        failed_two.json.return_value = failed_one.json.return_value

        with (
            patch.object(site, "load_api_key", return_value="test-key"),
            patch.object(site.requests, "post", side_effect=[failed_one, failed_two]),
            patch.object(site.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, r"HTTP 503.*provider_error"):
                site.call_openrouter_images_api(
                    model=site.NANO_BANANA_MODEL,
                    prompt="remove eyelashes",
                )

    def test_user_error_identifies_source_and_http_reason(self) -> None:
        error = RuntimeError(
            "第 3 张（sample.jpg）处理失败：OpenRouter Images API 请求失败（HTTP 429，错误码 429）：Rate limit exceeded"
        )

        message = site.format_user_facing_error_message(error)

        self.assertIn("第 3 张（sample.jpg）", message)
        self.assertIn("HTTP 429", message)
        self.assertIn("请求过于频繁", message)

    def test_background_error_log_redacts_key_and_embedded_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "openrouter_errors.jsonl"
            error = RuntimeError(
                "HTTP 503 key=sk-or-v1-abcdefghijklmnop data:image/png;base64,QUJDRA=="
            )
            with patch.object(site, "OPENROUTER_ERROR_LOG_FILE", log_path):
                site.record_background_job_error(
                    "job-test",
                    "remove_eyelashes",
                    "正在处理第 2 张",
                    error,
                )

            record = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(record["job_id"], "job-test")
            self.assertEqual(record["feature_key"], "remove_eyelashes")
            self.assertNotIn("abcdefghijklmnop", record["error"])
            self.assertNotIn("QUJDRA==", record["error"])
            self.assertIn("HTTP 503", record["error"])


if __name__ == "__main__":
    unittest.main()
