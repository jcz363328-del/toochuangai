from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from PIL import Image

from Department.视觉设计部.xiaoha import openrouter_image_site as site


class OmniaTaskRecoveryTests(unittest.TestCase):
    TASK_ID = "task-existing-generation"
    ASSET_URL = "https://assets.example.test/completed.png"

    def setUp(self) -> None:
        limiter = self.enterContext(patch.object(site, 'get_request_limiter')).return_value
        self.enterContext(patch('Department.视觉设计部.xiaoha.request_limits.get_request_limiter', return_value=limiter))
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.receipts = Path(folder) / "receipts.jsonl"
        self.stack.enter_context(patch.object(site, "OMNIAKEY_TASK_RECEIPTS_FILE", self.receipts))
        self.stack.enter_context(patch.object(site, "load_omnia_api_key", return_value="test-key"))
        self.stack.enter_context(patch.object(site.time, "sleep"))
        self.stack.enter_context(patch.object(site, "record_background_job_error"))
        self.post = self.stack.enter_context(patch.object(site.requests, "post"))
        self.get = self.stack.enter_context(patch.object(site.requests, "get"))
        self.post.return_value = self.response(202, {"id": self.TASK_ID, "status": "pending"})
        output = io.BytesIO()
        Image.new("RGB", (8, 8), "blue").save(output, format="PNG")
        self.image_bytes = output.getvalue()
        self.asset = self.response(200, {})
        self.asset.content = self.image_bytes
        self.asset.headers = {"Content-Type": "image/png"}
        self.completed = self.response(200, {
            "id": self.TASK_ID,
            "status": "succeeded",
            "assets": [{"url": self.ASSET_URL, "mime_type": "image/png"}],
        })

    @staticmethod
    def response(status: int, body: dict) -> Mock:
        response = Mock(status_code=status, headers={}, text="temporary upstream error")
        response.json.return_value = body
        return response

    def generate(self, prompt: str = "draw a blue square") -> dict:
        return site.call_omnia_image_api(site.NANO_BANANA_MODEL, prompt)

    def test_default_nano_uses_async_task_and_persists_recovery_receipt(self) -> None:
        self.get.side_effect = [self.completed, self.asset]
        result = self.generate()
        self.assertEqual(self.post.call_args.args[0], site.OMNIAKEY_MEDIA_TASKS_URL)
        payload = self.post.call_args.kwargs["json"]
        self.assertEqual(payload["parameters"]["aspect_ratio"], "1:1")
        self.assertTrue(result["images"][0].startswith("data:image/png;base64,"))
        receipt = json.loads(self.receipts.read_text(encoding="utf-8"))
        self.assertEqual(receipt["task_id"], self.TASK_ID)
        self.assertEqual(receipt["idempotency_key"], self.post.call_args.kwargs["headers"]["Idempotency-Key"])
        self.assertNotIn("test-key", self.receipts.read_text())
        self.assertNotIn("draw a blue square", self.receipts.read_text())

    def test_reference_orientation_and_all_images_survive_async_transport(self) -> None:
        output = io.BytesIO()
        Image.new("RGB", (240, 160)).save(output, format="PNG")
        upload = {"data": output.getvalue(), "name": "landscape.png", "type": "image/png"}
        self.get.side_effect = [self.completed, self.asset]
        site.call_omnia_image_api(site.NANO_BANANA_MODEL, "edit", [upload, upload], resolution="2K")
        payload = self.post.call_args.kwargs["json"]
        self.assertEqual(payload["operation"], "edit")
        self.assertEqual(payload["parameters"], {"aspect_ratio": "3:2", "image_size": "2K"})
        self.assertEqual(len(payload["input"]["images"]), 2)

    def test_resume_existing_task_only_queries_and_downloads(self) -> None:
        self.get.side_effect = [self.completed, self.asset]
        result = site.resume_omnia_image_task(self.TASK_ID)
        self.post.assert_not_called()
        self.assertTrue(self.get.call_args_list[0].args[0].endswith("/" + self.TASK_ID))
        self.assertEqual(site.decode_data_url(result["images"][0])[0], self.image_bytes)

    def test_submit_524_retry_reuses_the_same_key_and_body(self) -> None:
        self.post.side_effect = [self.response(524, {}), self.response(202, {"id": self.TASK_ID, "status": "queued"})]
        self.get.side_effect = [self.completed, self.asset]
        self.generate()
        self.assertEqual(self.post.call_count, 2)
        first, second = self.post.call_args_list
        self.assertEqual(first.kwargs["headers"]["Idempotency-Key"], second.kwargs["headers"]["Idempotency-Key"])
        self.assertEqual(first.kwargs["json"], second.kwargs["json"])

    def test_receipt_write_failure_preserves_task_id_without_resubmitting(self) -> None:
        with patch.object(Path, "open", side_effect=OSError("disk unavailable")):
            with self.assertRaisesRegex(site.OmniaImageOutcomeUnknown, self.TASK_ID):
                site.run_hd_batch_generate_with_retry(self.generate, "draw")
        self.post.assert_called_once()
        self.get.assert_not_called()

    def assert_single_submission_and_same_task_queries(self, queries: int) -> None:
        self.post.assert_called_once()
        expected_url = site.OMNIAKEY_MEDIA_TASKS_URL + "/" + self.TASK_ID
        self.assertEqual(
            [call.args[0] for call in self.get.call_args_list[:queries]],
            [expected_url] * queries,
        )

    def test_transient_poll_errors_recover_without_submitting_again(self) -> None:
        failures = (
            self.response(503, {"error": {"message": "busy"}}),
            self.response(429, {"error": {"message": "rate limited"}}),
            self.response(524, {}),
            site.requests.ConnectionError("connection reset"),
        )
        for failure in failures:
            with self.subTest(failure=getattr(failure, "status_code", type(failure).__name__)):
                self.post.reset_mock()
                self.get.reset_mock()
                self.get.side_effect = [failure, self.completed, self.asset]
                result = self.generate()
                self.assert_single_submission_and_same_task_queries(2)
                self.assertEqual(self.get.call_count, 3)
                self.assertEqual(self.get.call_args_list[-1].args[0], self.ASSET_URL)
                self.assertEqual(site.decode_data_url(result["images"][0])[0], self.image_bytes)

    def test_four_failed_queries_preserve_task_id_and_stop(self) -> None:
        self.get.side_effect = [
            self.response(503, {"error": {"code": "upstream_unavailable", "message": "busy"}})
            for _ in range(4)
        ]
        with self.assertRaisesRegex(RuntimeError, self.TASK_ID) as caught:
            self.generate()
        self.assertIn("HTTP 503", str(caught.exception))
        self.assert_single_submission_and_same_task_queries(4)
        self.assertEqual(self.get.call_count, 4)

    def test_provider_submit_uncertain_does_not_trigger_hd_resubmission(self) -> None:
        self.get.return_value = self.response(200, {
            "id": self.TASK_ID,
            "status": "failed",
            "error": {
                "code": "provider_submit_uncertain",
                "message": "The task timed out before it completed.",
                "retryable": True,
            },
        })
        with self.assertRaisesRegex(RuntimeError, "provider_submit_uncertain") as caught:
            site.run_hd_batch_generate_with_retry(self.generate, "draw a blue square")
        self.assertIn(self.TASK_ID, str(caught.exception))
        self.assert_single_submission_and_same_task_queries(1)
        self.assertEqual(self.get.call_count, 1)

    def test_query_failure_does_not_trigger_hd_resubmission(self) -> None:
        for failure in (
            self.response(503, {"error": {"message": "service is busy"}}),
            site.requests.ConnectionError("read timed out"),
        ):
            with self.subTest(failure=getattr(failure, "status_code", type(failure).__name__)):
                self.post.reset_mock()
                self.get.reset_mock()
                self.get.side_effect = [failure] * 4
                with self.assertRaisesRegex(RuntimeError, self.TASK_ID):
                    site.run_hd_batch_generate_with_retry(self.generate, "draw a blue square")
                self.assert_single_submission_and_same_task_queries(4)
                self.assertEqual(self.get.call_count, 4)

    def test_copyright_rejection_is_explained_and_never_resubmitted(self) -> None:
        self.get.return_value = self.response(200, {
            "id": self.TASK_ID, "status": "failed",
            "error": {"code": "content_filter", "detail": "finishReason=IMAGE_RECITATION",
                      "message": "The request may involve copyrighted or otherwise protected content.",
                      "reason": "copyright", "retryable": False},
        })
        with self.assertRaises(RuntimeError) as caught:
            site.run_hd_batch_generate_with_retry(self.generate, "enhance")
        message = site.format_user_facing_error_message(
            "OmniaKey 原生 4K 调用失败。为避免画质降级，本次未使用聊天兼容通道或本地放大。原因：" + str(caught.exception)
        )
        self.assertIn("受保护内容", message)
        self.assertIn("误判", message)
        self.assertIn(self.TASK_ID, message)
        self.assertNotIn("4K 调用失败", message)
        self.assertFalse(site.is_hd_batch_transient_error(str(caught.exception) + " provider_submit_rejected"))
        self.assert_single_submission_and_same_task_queries(1)
        self.assertEqual(self.get.call_count, 1)

    def test_wrapped_uncertain_result_is_not_treated_as_retryable(self) -> None:
        original = site.OmniaImageOutcomeUnknown("HTTP 504")
        wrapped = RuntimeError("HTTP 503: rendering failed")
        wrapped.__cause__ = original
        contextual = RuntimeError("read timed out")
        contextual.__context__ = wrapped
        for error in (wrapped, contextual):
            with self.subTest(error=error):
                generate = Mock(side_effect=error)
                with self.assertRaises(RuntimeError):
                    site.run_hd_batch_generate_with_retry(generate, "test")
                generate.assert_called_once()
        wrapped.__cause__ = contextual
        self.assertFalse(site.is_omnia_image_outcome_unknown(wrapped))

    def test_serialized_uncertain_result_does_not_trigger_resubmission(self) -> None:
        for marker in (
            "未自动重新提交", "provider_submit_uncertain", "查询图片任务失败", "图片任务等待超时",
        ):
            with self.subTest(marker=marker):
                generate = Mock(side_effect=RuntimeError("HTTP 503: " + marker))
                with self.assertRaises(RuntimeError):
                    site.run_hd_batch_generate_with_retry(generate, "test")
                generate.assert_called_once()

    def test_portrait_hd_preserves_uncertain_error_and_does_not_resubmit(self) -> None:
        upload = {"data": self.image_bytes, "name": "source.png", "type": "image/png"}
        uncertain = site.OmniaImageOutcomeUnknown("HTTP 504")
        with patch.object(site, "get_portrait_hd_inputs", return_value=[upload]), \
                patch.object(site, "build_portrait_hd_size_instruction", return_value="keep dimensions"), \
                patch.object(site, "call_openrouter_images_api", side_effect=uncertain) as generate:
            with self.assertRaises(site.OmniaImageOutcomeUnknown) as caught:
                site.run_hd_batch_generate_with_retry(
                    lambda prompt: site.call_openrouter_portrait_hd(
                        site.NANO_BANANA_MODEL, prompt, "1:1", [upload],
                    ),
                    "enhance",
                )
            self.assertIs(caught.exception, uncertain)
            generate.assert_called_once()

    def test_outpaint_does_not_regenerate_after_uncertain_repair(self) -> None:
        upload = {"data": self.image_bytes, "name": "source.png", "type": "image/png"}
        candidate = site.image_bytes_to_data_url(self.image_bytes, "image/png")
        context = {
            "feature": {"key": "outpaint"}, "model": site.NANO_BANANA_MODEL,
            "prompt": "extend the image", "output_mode": "image", "max_output_images": 1,
            "outpaint_settings": {"right": 8},
        }
        for failed_attempt in (2, 3):
            with self.subTest(failed_attempt=failed_attempt), ExitStack() as stack:
                for name, value in {
                    "build_outpaint_source_canvas": upload,
                    "build_outpaint_source_framing_instruction": "preserve original",
                    "is_outpaint_result_effectively_unchanged": False,
                    "crop_outpaint_result_to_selected_region": candidate,
                    "measure_outpaint_boundary_seams": [],
                    "has_outpaint_rectangular_join": True,
                    "build_outpaint_seam_repair_reference": upload,
                    "build_outpaint_seam_repair_prompt": "repair the seam",
                }.items():
                    stack.enter_context(patch.object(site, name, return_value=value))
                uncertain = site.OmniaImageOutcomeUnknown("HTTP 504")
                generate = stack.enter_context(patch.object(
                    site, "call_openrouter",
                    side_effect=[{"images": [candidate]}] * (failed_attempt - 1) + [uncertain],
                ))
                with self.assertRaises(site.OmniaImageOutcomeUnknown) as caught:
                    site.process_batch_group(context, [upload], 1)
                self.assertIs(caught.exception, uncertain)
                self.assertEqual(generate.call_count, failed_attempt)


if __name__ == "__main__":
    unittest.main()
