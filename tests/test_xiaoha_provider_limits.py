import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import io
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from 图片 import openrouter_image_site as site
from 图片.request_limits import RequestLimiter


class ProviderLimitTests(unittest.TestCase):
    def setUp(self):
        self.stack = self.enterContext(ExitStack())
        folder = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.limiter = RequestLimiter(Path(folder) / 'limits.sqlite3', poll_interval=.01,
                                      queue_timeout=10, uncertain_cooldown=0)
        self.stack.enter_context(patch('图片.request_limits.get_request_limiter', return_value=self.limiter))
        self.stack.enter_context(patch.object(site, 'get_request_limiter', return_value=self.limiter))
        self.stack.enter_context(patch.object(site, 'load_omnia_api_key', return_value='test'))
        self.stack.enter_context(patch.object(site, 'load_ark_api_key', return_value='test'))
        output = io.BytesIO()
        Image.new('RGB', (16, 16), 'blue').save(output, format='PNG')
        self.image = output.getvalue()
        self.upload = {'data': self.image, 'name': 'test.png', 'type': 'image/png'}

    def image_response(self):
        result = Mock(status_code=200, headers={})
        result.json.return_value = {'data': [{'b64_json': base64.b64encode(self.image).decode()}]}
        return result

    def test_parallel_image_and_text_entrypoints_share_provider_capacity(self):
        lock = threading.Lock()
        active = {'image': 0, 'text': 0}
        peak = {'image': 0, 'text': 0, 'total': 0}
        calls = []

        def post(url, **kwargs):
            kind = 'text' if url.endswith('/chat/completions') else 'image'
            with lock:
                calls.append(url)
                active[kind] += 1
                peak[kind] = max(peak[kind], active[kind])
                peak['total'] = max(peak['total'], sum(active.values()))
            try:
                time.sleep(.04)
                if kind == 'image':
                    response = Mock(status_code=202, headers={})
                    response.json.return_value = {'id': 'existing-task', 'status': 'succeeded', 'assets': [{'url': 'https://example.test/image.png'}]}
                    return response
                response = Mock(status_code=200, headers={})
                response.json.return_value = {'choices': [{'message': {'content': 'ok'}}]}
                return response
            finally:
                with lock:
                    active[kind] -= 1

        with patch.object(site.requests, 'post', side_effect=post), \
                patch.object(site.requests, 'get', return_value=Mock(status_code=200, content=self.image, headers={'Content-Type': 'image/png'})), \
                ThreadPoolExecutor(max_workers=16) as executor:
            futures = []
            for _ in range(8):
                futures.append(executor.submit(site.call_omnia_image_api, site.NANO_BANANA_MODEL, 'draw'))
                futures.append(executor.submit(site.call_omnia_chat_api, site.OMNIAKEY_VISION_TEXT_MODEL, 'analyze', []))
            for future in futures:
                future.result(timeout=10)
        self.assertEqual(len(calls), 16)
        self.assertEqual(peak['image'], 1)
        self.assertLessEqual(peak['text'], 2)
        self.assertLessEqual(peak['total'], 2)
        self.assertEqual(self.limiter.snapshot()['active'], 0)

    def test_media_task_holds_slot_until_polling_and_download_finish(self):
        polling = threading.Event()
        release = threading.Event()
        nano_started = threading.Event()
        created = Mock(status_code=202, headers={})
        created.json.return_value = {'id': 'existing-task', 'status': 'pending'}

        def post(url, **kwargs):
            if url.endswith('/media/tasks'):
                if kwargs['json']['model'] == site.NANO_BANANA_MODEL:
                    nano_started.set()
                return created
            nano_started.set()
            return self.image_response()

        def get(url, **kwargs):
            if url.endswith('/existing-task'):
                polling.set()
                release.wait(3)
                response = Mock(status_code=200, headers={})
                response.json.return_value = {'status': 'succeeded', 'assets': [{'url': 'https://example.test/image.png'}]}
                return response
            return Mock(status_code=200, content=self.image, headers={'Content-Type': 'image/png'})

        with patch.object(site.requests, 'post', side_effect=post), patch.object(site.requests, 'get', side_effect=get), \
                patch.object(site, 'OMNIAKEY_TASK_POLL_INTERVAL_SECONDS', 0), ThreadPoolExecutor(max_workers=2) as executor:
            media = executor.submit(site.call_omnia_media_image_api, 'Dola-Seedream-5.0-pro', 'draw')
            try:
                self.assertTrue(polling.wait(2))
                nano = executor.submit(site.call_omnia_image_api, site.NANO_BANANA_MODEL, 'draw')
                self.assertFalse(nano_started.wait(.1))
            finally:
                release.set()
            self.assertTrue(media.result(timeout=3)['images'])
            self.assertTrue(nano.result(timeout=3)['images'])

    def test_ark_unknown_result_is_submitted_only_once(self):
        failures = [site.requests.Timeout(), Mock(status_code=503, headers={})]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                options = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
                with patch.object(site.requests, 'post', **options) as post:
                    with self.assertRaises(site.ImageOutcomeUnknown) as caught:
                        site.run_hd_batch_generate_with_retry(
                            lambda prompt: site.call_ark_seedream_images_api(prompt, [self.upload]), 'edit')
                    self.assertEqual(post.call_count, 1)
                    self.assertIn('未自动重新提交', site.format_user_facing_error_message(caught.exception))

    def test_media_submit_retries_keep_one_idempotency_key_and_no_outer_resubmit(self):
        with patch.object(site.requests, 'post', side_effect=site.requests.Timeout()) as post, \
                patch.object(site.time, 'sleep'):
            with self.assertRaises(site.OmniaImageOutcomeUnknown):
                site.run_hd_batch_generate_with_retry(
                    lambda prompt: site.call_omnia_media_image_api('Dola-Seedream-5.0-pro', prompt), 'draw')
        self.assertEqual(post.call_count, site.OMNIAKEY_MEDIA_MAX_ATTEMPTS)
        keys = {call.kwargs['headers']['Idempotency-Key'] for call in post.call_args_list}
        self.assertEqual(len(keys), 1)

    def test_incomplete_post_responses_never_trigger_a_second_paid_request(self):
        operations = {
            "sync": lambda prompt: site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, prompt),
            "media": lambda prompt: site.call_omnia_media_image_api("Dola-Seedream-5.0-pro", prompt),
            "ark": lambda prompt: site.call_ark_seedream_images_api(prompt, [self.upload]),
        }
        for name, operation in operations.items():
            for failure in (site.requests.exceptions.ChunkedEncodingError("incomplete response"),
                            site.requests.exceptions.ContentDecodingError("invalid response encoding")):
                with self.subTest(provider=name, failure=type(failure).__name__), \
                        patch.object(site.requests, "post", side_effect=failure) as post:
                    with self.assertRaises(site.ImageOutcomeUnknown):
                        site.run_hd_batch_generate_with_retry(operation, "draw")
                    self.assertEqual(post.call_count, 1)

    def test_sync_http_408_is_an_unknown_outcome_and_retains_capacity(self):
        self.limiter.uncertain_cooldown = 60
        with patch.object(site.requests, "post", return_value=Mock(status_code=408, headers={})) as post:
            with self.assertRaises(site.OmniaImageOutcomeUnknown):
                site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, "draw")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.limiter.snapshot()["retained"], 1)

    def test_text_unknown_outcomes_do_not_fallback_to_another_paid_model(self):
        response = Mock(status_code=503, headers={})
        response.json.return_value = {"error": {"message": "upstream timeout"}}
        invalid = Mock(status_code=200, headers={})
        invalid.json.side_effect = ValueError("truncated JSON")
        failures = [site.requests.Timeout(), site.requests.exceptions.ChunkedEncodingError(), response, invalid]
        for failure in failures:
            options = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
            with self.subTest(failure=type(failure).__name__), patch.object(site.requests, "post", **options) as post, \
                    patch.object(site, "OMNIAKEY_VISION_TEXT_FALLBACK_MODELS", ("fallback-model",)):
                with self.assertRaises(site.ImageOutcomeUnknown):
                    site.call_omnia_chat_api(site.OMNIAKEY_VISION_TEXT_MODEL, "analyze", [])
                self.assertEqual(post.call_count, 1)

    def test_text_explicit_channel_rejection_can_still_choose_a_fallback(self):
        rejected = Mock(status_code=503, headers={})
        rejected.json.return_value = {"error": {"code": "no_available_channel", "message": "no available channel"}}
        success = Mock(status_code=200, headers={})
        success.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        with patch.object(site.requests, "post", side_effect=[rejected, success]) as post, \
                patch.object(site, "OMNIAKEY_VISION_TEXT_FALLBACK_MODELS", ("fallback-model",)):
            result = site.call_omnia_chat_api(site.OMNIAKEY_VISION_TEXT_MODEL, "analyze", [])
        self.assertEqual(result["text"], "ok")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "fallback-model")

    def test_media_poll_failure_keeps_task_id_and_retains_capacity(self):
        self.limiter.uncertain_cooldown = 60
        created = Mock(status_code=202, headers={})
        created.json.return_value = {"id": "already-paid-task", "status": "pending"}
        failed = Mock(status_code=503, headers={})
        failed.json.return_value = {"error": {"message": "query unavailable"}}
        with patch.object(site.requests, "post", return_value=created) as post, \
                patch.object(site.requests, "get", return_value=failed) as get, \
                patch.object(site, "OMNIAKEY_TASK_POLL_INTERVAL_SECONDS", 0):
            with self.assertRaisesRegex(site.OmniaImageOutcomeUnknown, "already-paid-task"):
                site.call_omnia_media_image_api("Dola-Seedream-5.0-pro", "draw")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(get.call_count, 4)
        self.assertEqual(self.limiter.snapshot()["retained"], 1)

    def test_media_local_deadline_retains_capacity_without_resubmission(self):
        self.limiter.uncertain_cooldown = 60
        created = Mock(status_code=202, headers={})
        created.json.return_value = {"id": "already-paid-task", "status": "pending"}
        with patch.object(site.requests, "post", return_value=created) as post, \
                patch.object(site.requests, "get") as get, \
                patch.object(site, "OMNIAKEY_TASK_TIMEOUT_SECONDS", -1):
            with self.assertRaisesRegex(site.OmniaImageOutcomeUnknown, "already-paid-task"):
                site.call_omnia_media_image_api("Dola-Seedream-5.0-pro", "draw")
        self.assertEqual(post.call_count, 1)
        get.assert_not_called()
        self.assertEqual(self.limiter.snapshot()["retained"], 1)

    def test_reverse_reference_download_holds_the_shared_download_slot(self):
        def download(*args, **kwargs):
            self.assertEqual(self.limiter.snapshot()["groups"]["download"]["active"], 1)
            return Mock(ok=True, content=self.image)

        with patch.object(site.requests, "get", side_effect=download) as get:
            result = site.build_hero_style_reverse_image_input("https://example.test/previous.png")
        self.assertEqual(result["data"], self.image)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(self.limiter.snapshot()["active"], 0)

    def test_intermediate_provider_rejections_share_their_backoff(self):
        rejected = Mock(status_code=429, headers={})
        rejected.json.return_value = {"error": {"message": "rate limited"}}
        success = Mock(status_code=200, headers={})
        success.json.return_value = {"data": [{"url": "https://example.test/image.png"}]}
        with patch.object(site.requests, "post", side_effect=[rejected, success]) as post, \
                patch.object(site.time, "sleep") as sleep, patch.object(self.limiter, "cooldown") as cooldown:
            site.call_ark_seedream_images_api("draw", [self.upload])
        self.assertEqual(post.call_count, 2)
        cooldown.assert_called_once_with("ark", seconds=site.ARK_IMAGES_RETRY_DELAYS[0])
        sleep.assert_called_once_with(site.ARK_IMAGES_RETRY_DELAYS[0])

    def test_media_429_keeps_idempotency_key_and_publishes_cooldown(self):
        rejected = Mock(status_code=429, headers={})
        completed = Mock(status_code=202, headers={})
        completed.json.return_value = {"id": "existing-task", "status": "succeeded",
                                       "assets": [{"url": "https://example.test/image.png"}]}
        image = Mock(status_code=200, headers={"Content-Type": "image/png"}, content=self.image)
        with patch.object(site.requests, "post", side_effect=[rejected, completed]) as post, \
                patch.object(site.requests, "get", return_value=image), patch.object(site.time, "sleep"), \
                patch.object(self.limiter, "cooldown") as cooldown:
            site.call_omnia_media_image_api("Dola-Seedream-5.0-pro", "draw")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(len({call.kwargs["headers"]["Idempotency-Key"] for call in post.call_args_list}), 1)
        cooldown.assert_called_once_with("omnia_image", seconds=site.OMNIAKEY_MEDIA_RETRY_DELAYS[0])

    def test_text_429_fallback_waits_and_publishes_shared_provider_cooldown(self):
        rejected = Mock(status_code=429, headers={})
        rejected.json.return_value = {"error": {"message": "rate limited"}}
        success = Mock(status_code=200, headers={})
        success.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        with patch.object(site.requests, "post", side_effect=[rejected, success]) as post, \
                patch.object(site.time, "sleep") as sleep, patch.object(self.limiter, "cooldown") as cooldown, \
                patch.object(site, "OMNIAKEY_VISION_TEXT_FALLBACK_MODELS", ("fallback-model",)):
            result = site.call_omnia_chat_api(site.OMNIAKEY_VISION_TEXT_MODEL, "analyze", [])
        self.assertEqual(result["text"], "ok")
        self.assertEqual(post.call_count, 2)
        cooldown.assert_called_once_with("omnia_text", seconds=site.OMNIAKEY_MEDIA_RETRY_DELAYS[0])
        sleep.assert_called_once_with(site.OMNIAKEY_MEDIA_RETRY_DELAYS[0])

    def test_jimeng_concurrency_rejection_publishes_cooldown(self):
        rejected = Mock(status_code=429, headers={})
        rejected.json.return_value = {"code": 50430, "message": "Concurrent Limit"}
        success = Mock(status_code=200, headers={})
        success.json.return_value = {"code": 10000, "data": {"task_id": "existing"}}
        with patch.object(site.requests, "post", side_effect=[rejected, success]) as post, \
                patch.object(site, "build_jimeng_auth_headers", return_value={}), \
                patch.object(site.time, "sleep") as sleep, patch.object(self.limiter, "cooldown") as cooldown:
            result = site.jimeng_signed_post(site.JIMENG_SUBMIT_ACTION, {})
        self.assertEqual(result["data"]["task_id"], "existing")
        self.assertEqual(post.call_count, 2)
        cooldown.assert_called_once_with("jimeng", seconds=site.JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS[0])
        sleep.assert_called_once_with(site.JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS[0])

    def test_jimeng_success_response_parse_failure_is_not_safe_to_resubmit(self):
        response = Mock(status_code=200, headers={})
        response.json.side_effect = ValueError("truncated")
        with patch.object(site.requests, "post", return_value=response) as post, \
                patch.object(site, "build_jimeng_auth_headers", return_value={}):
            with self.assertRaises(site.ImageOutcomeUnknown):
                site.jimeng_signed_post(site.JIMENG_SUBMIT_ACTION, {})
        self.assertEqual(post.call_count, 1)

    def test_jimeng_polling_has_a_finite_deadline(self):
        with patch.object(site.time, 'monotonic', side_effect=[0, 1801]), \
                patch.object(site, 'jimeng_signed_post') as post:
            with self.assertRaisesRegex(site.ImageOutcomeUnknown, 'existing-task'):
                site.poll_jimeng_task_result('test', 'existing-task')
            post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
