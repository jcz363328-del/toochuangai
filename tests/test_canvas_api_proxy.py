import base64
import io
import importlib
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager, nullcontext
from threading import BoundedSemaphore
from types import SimpleNamespace
from unittest.mock import Mock, patch

from Department.视觉设计部.xiaoha import canvas_api_proxy as proxy


class QueueFull(RuntimeError):
    pass


class FakeHandler:
    def __init__(self, payload=None, body=None, content_type="application/json", token=None):
        raw = json.dumps(payload or {}).encode() if body is None else body
        self.headers = {"Authorization": token or "Bearer " + proxy.build_canvas_token("test", "sig:test"),
                        "Content-Type": content_type, "Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.sent_headers = {}
        self.status = None
        self.json = None
        self.close_connection = False

    def send_json(self, payload, status=200):
        self.json, self.status = payload, status

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers[name] = value

    def end_headers(self):
        pass


def fake_site():
    return SimpleNamespace(
        build_auth_token=lambda user: "sig:" + user,
        format_user_facing_error_message=str,
        INFINITE_CANVAS_IMAGE_MODELS=("nano", "other"),
        INFINITE_CANVAS_TEXT_MODELS=("text",),
        GEMINI_IMAGE_ASPECT_RATIOS=("1:1", "3:2", "2:3"),
        DEFAULT_ASPECT_RATIO="自动", NANO_BANANA_MODEL="nano",
        resolve_omnia_image_model=lambda value: value,
        call_omnia_sync_image_api=Mock(return_value={"images": ["data:image/png;base64,aW1hZ2U="]}),
        call_omnia_image_api=Mock(return_value={"images": ["https://assets.omniakey.com/image.png"]}),
        load_image_bytes_from_url=Mock(return_value=(b"provider-image", "image/png")),
        load_omnia_api_key=lambda: "server-only-secret", OMNIAKEY_API_BASE="https://api.omniakey.com",
        get_external_request_kwargs=lambda **kwargs: {"timeout": kwargs["timeout"]},
    )


class CanvasApiProxyTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.provider_statuses = []

        @contextmanager
        def slot(group):
            self.events.append("enter:" + group)
            try:
                yield
            finally:
                self.events.append("exit:" + group)

        self.limits = SimpleNamespace(RequestQueueFull=QueueFull, get_request_limiter=lambda: SimpleNamespace(slot=slot), admitted_job=nullcontext)
        service = SimpleNamespace(managed_omnia_context=lambda **kwargs: nullcontext(),
                                  record_omnia_provider_status=self.provider_statuses.append)
        self.module_patch = patch.dict(sys.modules, {"Department.视觉设计部.xiaoha.request_limits": self.limits,
                                                    "Department.视觉设计部.xiaoha.omnia_service": service})
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)

    def test_pooled_credential_and_accounting_cover_complete_stream_even_after_disconnect(self):
        for disconnect in (False, True):
            with self.subTest(disconnect=disconnect):
                self.events.clear()
                self.provider_statuses.clear()
                active = {"key": "server-only-secret"}
                site = fake_site()
                site.load_omnia_api_key = lambda: active["key"]

                @contextmanager
                def managed(**kwargs):
                    self.assertEqual(kwargs["primary_key"], "server-only-secret")
                    self.assertEqual(kwargs["model"], "text")
                    self.assertEqual(kwargs["api_base"], "https://api.omniakey.com")
                    self.events.append("enter:managed")
                    active["key"] = "pooled-server-secret"
                    try:
                        yield
                        self.events.append("settle:success")
                    finally:
                        active["key"] = "server-only-secret"
                        self.events.append("exit:managed")

                handler = FakeHandler({"model": "text", "stream": True})
                if disconnect:
                    handler.wfile = Mock()
                    handler.wfile.write.side_effect = BrokenPipeError()
                upstream = Mock(status_code=200, headers={"Content-Type": "text/event-stream"})
                upstream.__enter__ = Mock(return_value=upstream)
                upstream.__exit__ = Mock(side_effect=lambda *args: self.events.append("close-upstream"))

                def chunks(**kwargs):
                    self.assertEqual(active["key"], "pooled-server-secret")
                    yield b"data: first\n\n"
                    self.assertEqual(active["key"], "pooled-server-secret")
                    self.events.append("drained")
                    yield b"data: [DONE]\n\n"

                upstream.iter_content.side_effect = chunks
                with patch.dict(sys.modules, {"Department.视觉设计部.xiaoha.omnia_service": SimpleNamespace(
                        managed_omnia_context=managed, record_omnia_provider_status=self.provider_statuses.append)}), \
                     patch.object(proxy.requests, "post", return_value=upstream) as post:
                    proxy.serve_canvas_api(handler, site, "/responses")
                self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer pooled-server-secret")
                self.assertEqual(self.events, ["enter:omnia_text", "enter:managed", "drained",
                                              "close-upstream", "settle:success", "exit:managed", "exit:omnia_text"])
                self.assertNotIn("pooled-server-secret", str(handler.sent_headers))
                self.assertEqual(self.provider_statuses, ["uncertain", "success"])

    def test_upstream_4xx_body_is_preserved_but_accounting_records_failure(self):
        captured = []

        @contextmanager
        def managed(**kwargs):
            try:
                yield
                captured.append("success")
            except BaseException as exc:
                captured.append(exc)
                raise

        handler = FakeHandler({"model": "text", "stream": False})
        upstream = Mock(status_code=403, headers={"Content-Type": "application/json"})
        upstream.__enter__ = Mock(return_value=upstream)
        upstream.__exit__ = Mock(return_value=False)
        body = b'{"error":{"message":"model not allowed"}}'
        upstream.iter_content.return_value = iter([body])
        with patch.dict(sys.modules, {"Department.视觉设计部.xiaoha.omnia_service": SimpleNamespace(
                managed_omnia_context=managed, record_omnia_provider_status=self.provider_statuses.append)}), \
             patch.object(proxy.requests, "post", return_value=upstream) as post:
            proxy.serve_canvas_api(handler, fake_site(), "/responses")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(handler.status, 403)
        self.assertEqual(handler.wfile.getvalue(), body)
        self.assertIsNone(handler.json)
        self.assertEqual(len(captured), 1)
        self.assertIsInstance(captured[0], proxy.CanvasRequestError)
        self.assertEqual(captured[0].status, 403)
        self.assertEqual(self.provider_statuses, ["uncertain", "rejected"])

    def test_stream_interruption_exits_accounting_as_unknown_without_resubmit(self):
        captured = []

        @contextmanager
        def managed(**kwargs):
            try:
                yield
                captured.append("success")
            except BaseException as exc:
                captured.append(exc)
                raise

        handler = FakeHandler({"model": "text", "stream": True})
        upstream = Mock(status_code=200, headers={"Content-Type": "text/event-stream"})
        upstream.__enter__ = Mock(return_value=upstream)
        upstream.__exit__ = Mock(return_value=False)

        def chunks(**kwargs):
            yield b"data: partial\n\n"
            raise proxy.requests.ConnectionError("interrupted")

        upstream.iter_content.side_effect = chunks
        with patch.dict(sys.modules, {"Department.视觉设计部.xiaoha.omnia_service": SimpleNamespace(
                managed_omnia_context=managed, record_omnia_provider_status=self.provider_statuses.append)}), \
             patch.object(proxy.requests, "post", return_value=upstream) as post:
            proxy.serve_canvas_api(handler, fake_site(), "/responses")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(len(captured), 1)
        self.assertIn("未自动重新提交", str(captured[0]))
        self.assertIsNone(handler.json)
        self.assertEqual(self.provider_statuses, ["uncertain"])

    def test_app_token_authentication_never_requires_provider_key(self):
        token = proxy.build_canvas_token("测试用户", "sig:测试用户")
        self.assertNotIn("server-only-secret", token)
        self.assertEqual(proxy.authenticate_canvas_token("Bearer " + token, lambda user: "sig:" + user), "测试用户")
        for bad in ("", "Bearer server-only-secret", "Bearer xh1.invalid", "Bearer " + proxy.build_canvas_token("test", "wrong")):
            with self.subTest(bad=bad), self.assertRaises(proxy.CanvasRequestError):
                proxy.authenticate_canvas_token(bad, lambda user: "sig:" + user)

    def test_block_invalid_auth_route_model_and_oversize_before_upstream(self):
        cases = [
            (FakeHandler({"model": "nano", "prompt": "draw"}, token="Bearer wrong"), "/images/generations", 403),
            (FakeHandler({}), "/media/tasks", 404),
            (FakeHandler({"model": "unapproved", "prompt": "draw"}), "/images/generations", 400),
        ]
        huge = FakeHandler({})
        huge.headers["Content-Length"] = str(proxy.MAX_BODY_BYTES + 1)
        cases.append((huge, "/images/generations", 413))
        for handler, endpoint, status in cases:
            with self.subTest(endpoint=endpoint, status=status):
                site = fake_site()
                proxy.serve_canvas_api(handler, site, endpoint)
                self.assertEqual(handler.status, status)
                site.call_omnia_sync_image_api.assert_not_called()
                site.call_omnia_image_api.assert_not_called()

    def test_generation_uses_existing_limited_adapter_and_preserves_exact_size(self):
        site = fake_site()
        handler = FakeHandler({"model": "nano", "prompt": "draw", "n": 3, "size": "1536x1024"})
        proxy.serve_canvas_api(handler, site, "/images/generations")
        self.assertEqual(handler.status, 200)
        self.assertEqual(len(handler.json["data"]), 3)
        self.assertEqual(site.call_omnia_sync_image_api.call_count, 3)
        self.assertEqual(site.call_omnia_sync_image_api.call_args.kwargs["size"], "1536x1024")
        self.assertEqual(handler.json["data"][0]["b64_json"], "aW1hZ2U=")

    def test_multipart_edit_keeps_all_reference_files(self):
        fields = [("model", "nano"), ("prompt", "combine"), ("n", "1"), ("size", "1024x1024")]
        body = b""
        for key, value in fields:
            body += f'--test\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        for filename, value in (("a.png", b"first"), ("b.png", b"second")):
            body += f'--test\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode() + value + b"\r\n"
        body += b"--test--\r\n"
        handler = FakeHandler(body=body, content_type="multipart/form-data; boundary=test")
        site = fake_site()
        proxy.serve_canvas_api(handler, site, "/images/edits")
        self.assertEqual(handler.status, 200)
        files = site.call_omnia_sync_image_api.call_args.args[2]
        self.assertEqual([item["data"] for item in files], [b"first", b"second"])
        self.assertEqual([item["name"] for item in files], ["a.png", "b.png"])

    def test_invalid_count_and_missing_references_cannot_submit(self):
        for payload, path in (({"n": 16}, "/images/generations"), ({"n": 0}, "/images/generations"), ({}, "/images/edits"), ({"mask": "data:mask"}, "/images/generations")):
            site = fake_site()
            handler = FakeHandler({"model": "nano", "prompt": "draw", **payload})
            proxy.serve_canvas_api(handler, site, path)
            self.assertEqual(handler.status, 400)
            site.call_omnia_sync_image_api.assert_not_called()

    def test_later_failure_keeps_successful_paid_outputs_without_retry(self):
        site = fake_site()
        site.call_omnia_sync_image_api.side_effect = [{"images": ["data:image/png;base64,aW1hZ2U="]}, RuntimeError("remote outcome unknown")]
        handler = FakeHandler({"model": "nano", "prompt": "draw", "n": 3})
        proxy.serve_canvas_api(handler, site, "/images/generations")
        self.assertEqual(site.call_omnia_sync_image_api.call_count, 2)
        self.assertEqual(len(handler.json["data"]), 1)
        self.assertIn("unknown", handler.json["warning"])

    def test_non_nano_uses_shared_media_adapter(self):
        site = fake_site()
        handler = FakeHandler({"model": "other", "prompt": "draw"})
        proxy.serve_canvas_api(handler, site, "/images/generations")
        site.call_omnia_image_api.assert_called_once()
        site.call_omnia_sync_image_api.assert_not_called()
        site.load_image_bytes_from_url.assert_called_once_with("https://assets.omniakey.com/image.png")
        self.assertEqual(base64.b64decode(handler.json["data"][0]["b64_json"]), b"provider-image")

    def test_text_slot_covers_stream_and_preserves_history_and_tools(self):
        for endpoint in ("/responses", "/chat/completions"):
            with self.subTest(endpoint=endpoint):
                self.events.clear()
                payload = {"model": "text", "stream": True, "input": [{"role": "user", "content": "hello"}], "tools": [{"type": "function", "name": "canvas"}]}
                handler = FakeHandler(payload)
                upstream = Mock(status_code=200, headers={"Content-Type": "text/event-stream"})
                upstream.__enter__ = Mock(return_value=upstream)
                upstream.__exit__ = Mock(side_effect=lambda *args: self.events.append("close-upstream"))

                def chunks(**kwargs):
                    self.assertEqual(self.events, ["enter:omnia_text"])
                    self.events.append("stream")
                    yield b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n'
                    yield b"data: [DONE]\n\n"

                upstream.iter_content.side_effect = chunks
                with patch.object(proxy.requests, "post", return_value=upstream) as post:
                    proxy.serve_canvas_api(handler, fake_site(), endpoint)
                self.assertEqual(self.events, ["enter:omnia_text", "stream", "close-upstream", "exit:omnia_text"])
                self.assertEqual(post.call_args.kwargs["json"], payload)
                self.assertEqual(post.call_args.args[0], "https://api.omniakey.com/v1" + endpoint)
                self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer server-only-secret")
                self.assertIn(b"[DONE]", handler.wfile.getvalue())
                self.assertNotIn("server-only-secret", str(handler.sent_headers))

    def test_disconnected_stream_is_drained_before_slot_release(self):
        handler = FakeHandler({"model": "text", "stream": True})
        handler.wfile = Mock()
        handler.wfile.write.side_effect = BrokenPipeError()
        upstream = Mock(status_code=200, headers={"Content-Type": "text/event-stream"})
        upstream.__enter__ = Mock(return_value=upstream)
        upstream.__exit__ = Mock()

        def chunks(**kwargs):
            yield b"first"
            self.events.append("drained")
            yield b"second"

        upstream.iter_content.side_effect = chunks
        with patch.object(proxy.requests, "post", return_value=upstream) as post:
            proxy.serve_canvas_api(handler, fake_site(), "/responses")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.events, ["enter:omnia_text", "drained", "exit:omnia_text"])
        upstream.__exit__.assert_called_once()

    def test_queue_full_is_backpressure_not_a_new_upstream_request(self):
        site = fake_site()
        site.call_omnia_sync_image_api.side_effect = QueueFull("queue full")
        handler = FakeHandler({"model": "nano", "prompt": "draw"})
        proxy.serve_canvas_api(handler, site, "/images/generations")
        self.assertEqual(handler.status, 429)
        self.assertEqual(site.call_omnia_sync_image_api.call_count, 1)

    def test_text_rate_limit_exits_slot_with_429_without_resubmitting(self):
        handler = FakeHandler({"model": "text", "stream": True})
        upstream = Mock(status_code=429)
        upstream.__enter__ = Mock(return_value=upstream)
        upstream.__exit__ = Mock(return_value=False)
        with patch.object(proxy.requests, "post", return_value=upstream) as post:
            proxy.serve_canvas_api(handler, fake_site(), "/responses")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(handler.status, 429)
        self.assertIn("429", handler.json["error"]["message"])
        self.assertEqual(self.events, ["enter:omnia_text", "exit:omnia_text"])
        upstream.iter_content.assert_not_called()
        self.assertEqual(self.provider_statuses, ["uncertain", "rejected"])

    def test_text_post_timeout_is_unknown_outcome_and_not_retried(self):
        for failure in (proxy.requests.Timeout(), proxy.requests.RequestException("transport failed")):
            handler = FakeHandler({"model": "text", "stream": True})
            with patch.object(proxy.requests, "post", side_effect=failure) as post:
                proxy.serve_canvas_api(handler, fake_site(), "/responses")
            self.assertEqual(post.call_count, 1)
            self.assertEqual(handler.status, 502)
            self.assertIn("未自动重新提交", handler.json["error"]["message"])

    def test_text_server_error_is_unknown_outcome_before_stream_headers(self):
        for status in (408, 500, 502, 504):
            self.provider_statuses.clear()
            handler = FakeHandler({"model": "text", "stream": True})
            upstream = Mock(status_code=status)
            upstream.__enter__ = Mock(return_value=upstream)
            upstream.__exit__ = Mock(return_value=False)
            with patch.object(proxy.requests, "post", return_value=upstream) as post:
                proxy.serve_canvas_api(handler, fake_site(), "/responses")
            self.assertEqual(post.call_count, 1)
            self.assertEqual(handler.status, status)
            self.assertFalse(handler._canvas_response_started)
            self.assertIn("未自动重新提交", str(upstream.__exit__.call_args.args[1]))
            self.assertEqual(self.provider_statuses, ["uncertain"])

    def test_stream_failure_leaves_unknown_outcome_without_second_response(self):
        handler = FakeHandler({"model": "text", "stream": True})
        upstream = Mock(status_code=200, headers={"Content-Type": "text/event-stream"})
        upstream.__enter__ = Mock(return_value=upstream)
        upstream.__exit__ = Mock(return_value=False)

        def chunks(**kwargs):
            yield b"data: partial\n\n"
            raise proxy.requests.ConnectionError("stream failed")

        upstream.iter_content.side_effect = chunks
        with patch.object(proxy.requests, "post", return_value=upstream) as post:
            proxy.serve_canvas_api(handler, fake_site(), "/responses")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(handler.status, 200)
        self.assertIsNone(handler.json)
        self.assertTrue(handler._canvas_response_started)
        self.assertIn("未自动重新提交", str(upstream.__exit__.call_args.args[1]))
        self.assertEqual(self.events, ["enter:omnia_text", "exit:omnia_text"])

    def test_models_are_authenticated_allowlist_without_upstream_request(self):
        handler = FakeHandler()
        proxy.serve_canvas_api(handler, fake_site(), "/models", "GET")
        self.assertEqual(handler.status, 200)
        self.assertEqual([model["id"] for model in handler.json["data"]], ["nano", "other", "text"])

    def test_canvas_capacity_rejects_before_reading_body_or_submitting(self):
        slots = BoundedSemaphore(1)
        slots.acquire()
        handler = FakeHandler({"model": "nano", "prompt": "draw"})
        site = fake_site()
        with patch.object(proxy, "_request_slots", slots):
            proxy.serve_canvas_api(handler, site, "/images/generations")
            self.assertEqual(handler.status, 429)
            self.assertEqual(handler.rfile.tell(), 0)
            site.call_omnia_sync_image_api.assert_not_called()
            slots.release()
            proxy.serve_canvas_api(handler, site, "/images/generations")
            self.assertEqual(handler.status, 200)
            site.call_omnia_sync_image_api.assert_called_once()

    def test_canvas_capacity_is_released_after_failure(self):
        slots = BoundedSemaphore(1)
        site = fake_site()
        site.call_omnia_sync_image_api.side_effect = [RuntimeError("failed"), {"images": ["data:image/png;base64,aW1hZ2U="]}]
        with patch.object(proxy, "_request_slots", slots):
            for status in (502, 200):
                handler = FakeHandler({"model": "nano", "prompt": "draw"})
                proxy.serve_canvas_api(handler, site, "/images/generations")
                self.assertEqual(handler.status, status)
        self.assertTrue(slots.acquire(blocking=False))
        slots.release()

    def test_canvas_capacity_is_held_until_stream_finishes(self):
        slots = BoundedSemaphore(1)
        handler = FakeHandler({"model": "text", "stream": True})
        upstream = Mock(status_code=200, headers={"Content-Type": "text/event-stream"})
        upstream.__enter__ = Mock(return_value=upstream)
        upstream.__exit__ = Mock()

        def chunks(**kwargs):
            competing = FakeHandler({"model": "nano", "prompt": "draw"})
            proxy.serve_canvas_api(competing, fake_site(), "/images/generations")
            self.assertEqual(competing.status, 429)
            self.assertEqual(competing.rfile.tell(), 0)
            yield b"data: [DONE]\n\n"

        upstream.iter_content.side_effect = chunks
        with patch.object(proxy, "_request_slots", slots), patch.object(proxy.requests, "post", return_value=upstream):
            proxy.serve_canvas_api(handler, fake_site(), "/responses")
        self.assertEqual(handler.status, 200)
        self.assertTrue(slots.acquire(blocking=False))
        slots.release()

    def test_legacy_routes_share_capacity_before_reading_uploads(self):
        site = fake_site()
        site.AUTH_QUERY_USER_KEY, site.AUTH_QUERY_TOKEN_KEY = "auth_user", "auth_token"
        handler = FakeHandler()
        callback = Mock()
        slots = BoundedSemaphore(1)
        slots.acquire()
        with patch.object(proxy, "_request_slots", slots):
            proxy.serve_legacy_canvas_request(handler, site, "auth_user=test&auth_token=sig:test", callback)
            self.assertEqual(handler.status, 429)
            self.assertEqual(handler.rfile.tell(), 0)
            callback.assert_not_called()
            slots.release()
            proxy.serve_legacy_canvas_request(handler, site, "auth_user=test&auth_token=sig:test", callback)
            callback.assert_called_once()


class CanvasAdmissionIntegrationTests(unittest.TestCase):
    def test_entire_canvas_batch_survives_drain_but_new_requests_do_not(self):
        limits = importlib.import_module("Department.视觉设计部.xiaoha.request_limits")
        with tempfile.TemporaryDirectory() as temp:
            limiter = limits.RequestLimiter(temp + "/limits.sqlite3", uncertain_cooldown=0)
            site = fake_site()
            count = 0

            def image(*args, **kwargs):
                nonlocal count
                with limiter.slot("omnia_image"):
                    count += 1
                    if count == 1:
                        limiter.drain(True)
                    return {"images": ["data:image/png;base64,aW1hZ2U="]}

            site.call_omnia_sync_image_api.side_effect = image
            with patch.object(limits, "get_request_limiter", return_value=limiter):
                handler = FakeHandler({"model": "nano", "prompt": "draw", "n": 3})
                proxy.serve_canvas_api(handler, site, "/images/generations")
                self.assertEqual(handler.status, 200)
                self.assertEqual(len(handler.json["data"]), 3)
                second = FakeHandler({"model": "nano", "prompt": "draw"})
                proxy.serve_canvas_api(second, site, "/images/generations")
                self.assertEqual(second.status, 429)
                self.assertEqual(second.rfile.tell(), 0)
                self.assertEqual(count, 3)
                slots = BoundedSemaphore(1)
                slots.acquire()
                with patch.object(proxy, "_request_slots", slots):
                    models = FakeHandler()
                    proxy.serve_canvas_api(models, site, "/models", "GET")
                self.assertEqual(models.status, 200)

    def test_legacy_canvas_multistage_job_retains_admission_during_drain(self):
        limits = importlib.import_module("Department.视觉设计部.xiaoha.request_limits")
        with tempfile.TemporaryDirectory() as temp:
            limiter = limits.RequestLimiter(temp + "/limits.sqlite3", uncertain_cooldown=0)
            site = fake_site()
            site.AUTH_QUERY_USER_KEY, site.AUTH_QUERY_TOKEN_KEY = "auth_user", "auth_token"
            completed = []
            handler = FakeHandler()

            def callback(query):
                with limiter.slot("omnia_image"):
                    completed.append("image")
                    limiter.drain(True)
                with limiter.slot("omnia_text"):
                    completed.append("review")
                handler.send_json({"success": True})

            with patch.object(limits, "get_request_limiter", return_value=limiter):
                proxy.serve_legacy_canvas_request(handler, site, "auth_user=test&auth_token=sig:test", callback)
                self.assertEqual(handler.status, 200)
                self.assertEqual(completed, ["image", "review"])
                proxy.serve_legacy_canvas_request(handler, site, "auth_user=test&auth_token=sig:test", callback)
                self.assertEqual(handler.status, 429)
                self.assertEqual(completed, ["image", "review"])


class CanvasBootstrapTests(unittest.TestCase):
    def test_bootstrap_replaces_browser_provider_key_with_local_authenticated_route(self):
        from Department.视觉设计部.xiaoha import openrouter_image_site as site

        handler = site.JimengStaticRequestHandler.__new__(site.JimengStaticRequestHandler)
        handler.send_json = Mock()
        with patch.object(site, "load_omnia_api_key", return_value="real-upstream-key"), patch.object(site, "build_auth_token", return_value="signed-user"):
            handler.serve_infinite_canvas_bootstrap("auth_user=test&auth_token=signed-user")
        payload = handler.send_json.call_args.args[0]
        channel = payload["config"]["channels"][0]
        self.assertEqual(channel["baseUrl"], site.INFINITE_CANVAS_STATIC_ROUTE_PREFIX + "/api/omnia/v1")
        self.assertNotIn("real-upstream-key", json.dumps(payload))
        self.assertTrue(channel["apiKey"].startswith("xh1."))
        self.assertIn("shared-queue", payload["config"]["configVersion"])

    def test_existing_static_handler_dispatches_both_api_methods(self):
        from Department.视觉设计部.xiaoha import openrouter_image_site as site

        handler = site.JimengStaticRequestHandler.__new__(site.JimengStaticRequestHandler)
        for endpoint, method in (("/images/generations", "do_POST"), ("/models", "do_GET")):
            handler.path = site.INFINITE_CANVAS_STATIC_ROUTE_PREFIX + "/api/omnia/v1" + endpoint
            with patch.object(proxy, "serve_canvas_api") as serve:
                getattr(handler, method)()
            self.assertEqual(serve.call_args.args[2], endpoint)
            self.assertIs(serve.call_args.args[0], handler)

    def test_legacy_model_routes_share_guard_without_double_wrapping_proxy(self):
        from Department.视觉设计部.xiaoha import openrouter_image_site as site

        handler = site.JimengStaticRequestHandler.__new__(site.JimengStaticRequestHandler)
        for route, callback in (("model-hd", "serve_infinite_canvas_model_hd"), ("image-feature", "serve_infinite_canvas_image_feature"), ("detect-public-figures", "serve_infinite_canvas_detect_public_figures")):
            handler.path = site.INFINITE_CANVAS_STATIC_ROUTE_PREFIX + "/api/" + route + "?auth_user=test&auth_token=sig"
            with patch.object(proxy, "serve_legacy_canvas_request") as serve:
                handler.do_POST()
            self.assertEqual(serve.call_args.args[3].__name__, callback)
        handler.path = site.INFINITE_CANVAS_STATIC_ROUTE_PREFIX + "/api/omnia/v1/images/generations"
        with patch.object(proxy, "serve_legacy_canvas_request") as legacy, patch.object(proxy, "serve_canvas_api") as modern:
            handler.do_POST()
        legacy.assert_not_called()
        modern.assert_called_once()

    def test_asset_download_uses_shared_slot_after_authentication(self):
        from Department.视觉设计部.xiaoha import openrouter_image_site as site

        events = []

        @contextmanager
        def slot(group):
            events.append("enter:" + group)
            try:
                yield
            finally:
                events.append("exit:" + group)

        def download(*args, **kwargs):
            self.assertEqual(events, ["enter:download"])
            return Mock(headers={"Content-Type": "image/png"}, content=b"image")

        handler = FakeHandler()
        with patch.object(site, "build_auth_token", return_value="signed-user"), patch.object(site, "get_request_limiter", return_value=SimpleNamespace(slot=slot)) as limiter, patch.object(site.requests, "get", side_effect=download) as get:
            site.JimengStaticRequestHandler.serve_infinite_canvas_omnia_asset(handler, "auth_user=test&auth_token=bad&url=https://assets.omniakey.com/image.png")
            self.assertEqual(handler.status, 403)
            limiter.assert_not_called()
            get.assert_not_called()
            site.JimengStaticRequestHandler.serve_infinite_canvas_omnia_asset(handler, "auth_user=test&auth_token=signed-user&url=https://assets.omniakey.com/image.png")
        self.assertEqual(handler.status, 200)
        self.assertEqual(events, ["enter:download", "exit:download"])
        self.assertEqual(handler.wfile.getvalue(), b"image")


if __name__ == "__main__":
    unittest.main()
