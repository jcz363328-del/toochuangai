from __future__ import annotations

import unittest
from unittest.mock import patch

from 图片 import openrouter_image_site as site


class HdBatchRetryTests(unittest.TestCase):
    def test_transient_omnia_errors_are_retryable(self) -> None:
        for message in (
            "OmniaKey 创建图片任务失败（HTTP 503）：no_available_channel",
            "OmniaKey 创建图片任务失败（HTTP 503）：system_cpu_overloaded",
            "OmniaKey 图片任务失败：provider_submit_rejected：The generation service is busy",
            "OmniaKey 连接失败：Read timed out",
        ):
            with self.subTest(message=message):
                self.assertTrue(site.is_hd_batch_transient_error(message))

    def test_invalid_input_is_not_retried(self) -> None:
        self.assertFalse(
            site.is_hd_batch_transient_error(
                "provider_submit_rejected：content not allowed：invalid_input"
            )
        )

    def test_retry_helper_retries_transient_failure_then_succeeds(self) -> None:
        calls = []

        def generate_once(prompt: str) -> dict[str, object]:
            calls.append(prompt)
            if len(calls) < 3:
                raise RuntimeError("OmniaKey 创建图片任务失败（HTTP 503）：system_cpu_overloaded")
            return {"images": ["ok"]}

        with patch.object(site.time, "sleep") as sleep:
            result = site.run_hd_batch_generate_with_retry(generate_once, "enhance")

        self.assertEqual(result["images"], ["ok"])
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep.call_count, 2)

    def test_retry_helper_does_not_retry_non_transient_failure(self) -> None:
        calls = []

        def generate_once(prompt: str) -> dict[str, object]:
            calls.append(prompt)
            raise RuntimeError("provider_submit_rejected：content not allowed")

        with self.assertRaises(RuntimeError):
            site.run_hd_batch_generate_with_retry(generate_once, "enhance")
        self.assertEqual(len(calls), 1)

    def test_hd_batch_concurrency_is_capped_below_previous_three_way_load(self) -> None:
        self.assertEqual(site.HD_BATCH_MAX_API_CONCURRENCY, 2)

    def test_cpu_overload_message_is_not_reported_as_missing_channel(self) -> None:
        message = site.format_omnia_error_message(
            "OmniaKey 创建图片任务失败（HTTP 503）：system_cpu_overloaded："
            "system cpu overloaded (current: 98.3%, threshold: 90%)"
        )
        self.assertIn("负载过高", message)
        self.assertNotIn("没有可用渠道", message)


if __name__ == "__main__":
    unittest.main()
