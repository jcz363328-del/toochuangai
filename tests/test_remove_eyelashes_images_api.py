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
        created = Mock(status_code=202)
        created.json.return_value = {"id": "task_test_429", "status": "queued"}
        completed = Mock(status_code=200)
        completed.json.return_value = {
            "id": "task_test_429",
            "status": "succeeded",
            "assets": [{"kind": "image", "url": "https://example.invalid/result.jpg"}],
        }
        downloaded = Mock(status_code=200, content=b"image")
        downloaded.headers = {"Content-Type": "image/png"}

        with (
            patch.object(site, "load_omnia_api_key", return_value="test-key"),
            patch.object(site.requests, "post", side_effect=[throttled, created]) as request_post,
            patch.object(site.requests, "get", side_effect=[completed, downloaded]),
            patch.object(site.time, "sleep") as retry_sleep,
        ):
            result = site.call_openrouter_images_api(
                model="bytedance-seed/seedream-4.5",
                prompt="remove eyelashes",
            )

        self.assertEqual(request_post.call_count, 2)
        retry_sleep.assert_any_call(site.OMNIAKEY_MEDIA_RETRY_DELAYS[0])
        self.assertEqual(result["channel"], "Seedream 5.0 Pro · OmniaKey")
        self.assertTrue(result["images"][0].startswith("data:image/png;base64,"))

    def test_images_api_failure_keeps_http_status_and_error_code(self) -> None:
        failed_one = Mock(status_code=503)
        failed_one.json.return_value = {
            "error": {"message": "Provider unavailable", "code": "provider_error"}
        }
        failed_two = Mock(status_code=503)
        failed_two.json.return_value = failed_one.json.return_value

        with (
            patch.object(site, "load_omnia_api_key", return_value="test-key"),
            patch.object(site.requests, "post", side_effect=[failed_one, failed_two]),
            patch.object(site.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, r"HTTP 503.*provider_error"):
                site.call_openrouter_images_api(
                    model="bytedance-seed/seedream-4.5",
                    prompt="remove eyelashes",
                )

    def test_nano_banana_generate_routes_to_omnia_media_tasks(self) -> None:
        created = Mock(status_code=202)
        created.json.return_value = {"id": "task_test_1", "status": "queued"}
        succeeded = Mock(status_code=200)
        succeeded.json.return_value = {
            "id": "task_test_1",
            "status": "succeeded",
            "assets": [
                {
                    "kind": "image",
                    "mime_type": "image/jpeg",
                    "url": "https://example.invalid/result.jpg",
                }
            ],
        }
        downloaded = Mock(status_code=200, content=b"fake-image-bytes")
        downloaded.headers = {"Content-Type": "image/jpeg"}

        with (
            patch.object(site, "load_omnia_api_key", return_value="test-omnia-key"),
            patch.object(site.requests, "post", return_value=created) as request_post,
            patch.object(site.requests, "get", side_effect=[succeeded, downloaded]),
            patch.object(site.time, "sleep"),
        ):
            result = site.call_openrouter_images_api(
                model="google/gemini-nano-banana-2.1",
                prompt="remove eyelashes",
            )

        self.assertTrue(result["images"][0].startswith("data:image/jpeg;base64,"))
        self.assertEqual(result["channel"], "Nano Banana 2.1 · OmniaKey")
        self.assertEqual(request_post.call_args.args[0], site.OMNIAKEY_MEDIA_TASKS_URL)
        payload = request_post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], site.NANO_BANANA_MODEL)
        self.assertEqual(payload["operation"], "generate")

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
