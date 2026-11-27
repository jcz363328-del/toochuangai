"""Serve Xiaoha static files and authenticated canvas endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sys
import urllib.parse
from collections.abc import Callable, Mapping
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def create_static_request_handler(get_runtime: Callable[[], Mapping[str, Any]]) -> type[SimpleHTTPRequestHandler]:
    """Bind handlers to the active Streamlit runtime, including in script mode."""
    class JimengStaticRequestHandler(SimpleHTTPRequestHandler):
        def __init__(
            self,
            *args: Any,
            directory: str | None = None,
            upload_directory: str | None = None,
            history_directory: str | None = None,
            canvas_directory: str | None = None,
            **kwargs: Any,
        ) -> None:
            runtime = get_runtime()
            DB_IMAGE_DIR = runtime['DB_IMAGE_DIR']
            INFINITE_CANVAS_BUILD_DIR = runtime['INFINITE_CANVAS_BUILD_DIR']

            self.upload_directory = str(upload_directory or directory or ".")
            self.history_directory = str(history_directory or DB_IMAGE_DIR)
            self.canvas_directory = str(canvas_directory or INFINITE_CANVAS_BUILD_DIR)
            super().__init__(*args, directory=self.upload_directory, **kwargs)

        def send_response(self, code: int, message: str | None = None) -> None:
            self._response_status = int(code)
            self._response_content_type = ""
            super().send_response(code, message)

        def send_header(self, keyword: str, value: str) -> None:
            if keyword.lower() == "content-type":
                self._response_content_type = str(value)
            super().send_header(keyword, value)

        def do_GET(self) -> None:
            runtime = get_runtime()
            INFINITE_CANVAS_STATIC_ROUTE_PREFIX = runtime['INFINITE_CANVAS_STATIC_ROUTE_PREFIX']

            request_url = urllib.parse.urlsplit(self.path)
            request_path = urllib.parse.unquote(request_url.path or "/").rstrip("/")
            if request_path == "/_xiaoha_static_health":
                self.send_json({"service": "xiaoha-static", "canvas_ready": (Path(self.canvas_directory) / "index.html").exists()})
                return
            proxy_prefix = f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/omnia/v1"
            if request_path.startswith(proxy_prefix + "/"):
                from Department.视觉设计部.xiaoha.canvas_api_proxy import serve_canvas_api
                serve_canvas_api(self, SimpleNamespace(**get_runtime()), request_path[len(proxy_prefix):], "GET")
                return
            if request_path == f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/a-plus-psd":
                from Department.视觉设计部.xiaoha.canvas_a_plus import serve_psd
                serve_psd(self, SimpleNamespace(**get_runtime()), request_url.query)
                return
            bootstrap_path = f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/bootstrap-config"
            if request_path == bootstrap_path:
                self.serve_infinite_canvas_bootstrap(request_url.query)
                return
            omnia_asset_path = f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/omnia-asset"
            if request_path == omnia_asset_path:
                self.serve_infinite_canvas_omnia_asset(request_url.query)
                return
            super().do_GET()

        def do_POST(self) -> None:
            runtime = get_runtime()
            INFINITE_CANVAS_STATIC_ROUTE_PREFIX = runtime['INFINITE_CANVAS_STATIC_ROUTE_PREFIX']

            request_url = urllib.parse.urlsplit(self.path)
            request_path = urllib.parse.unquote(request_url.path or "/").rstrip("/")
            proxy_prefix = f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/omnia/v1"
            if request_path.startswith(proxy_prefix + "/"):
                from Department.视觉设计部.xiaoha.canvas_api_proxy import serve_canvas_api
                serve_canvas_api(self, SimpleNamespace(**get_runtime()), request_path[len(proxy_prefix):])
                return
            model_hd_path = f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/model-hd"
            if request_path == model_hd_path:
                from Department.视觉设计部.xiaoha.canvas_api_proxy import serve_legacy_canvas_request
                serve_legacy_canvas_request(self, SimpleNamespace(**get_runtime()), request_url.query, self.serve_infinite_canvas_model_hd)
                return
            if request_path == f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/reference-node":
                from Department.视觉设计部.xiaoha.canvas_api_proxy import serve_legacy_canvas_request
                from Department.视觉设计部.xiaoha.canvas_reference import serve
                serve_legacy_canvas_request(self, SimpleNamespace(**get_runtime()), request_url.query,
                                            lambda query: serve(self, SimpleNamespace(**get_runtime()), query))
                return
            image_feature_path = f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/image-feature"
            if request_path == image_feature_path:
                from Department.视觉设计部.xiaoha.canvas_api_proxy import serve_legacy_canvas_request
                serve_legacy_canvas_request(self, SimpleNamespace(**get_runtime()), request_url.query, self.serve_infinite_canvas_image_feature)
                return
            detect_path = f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/detect-public-figures"
            if request_path == detect_path:
                from Department.视觉设计部.xiaoha.canvas_api_proxy import serve_legacy_canvas_request
                serve_legacy_canvas_request(self, SimpleNamespace(**get_runtime()), request_url.query, self.serve_infinite_canvas_detect_public_figures)
                return
            usage_record_path = f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/usage-record"
            if request_path == usage_record_path:
                self.serve_infinite_canvas_usage_record(request_url.query)
                return
            self.send_json({"success": False, "message": "接口不存在"}, status=404)

        def do_OPTIONS(self) -> None:
            runtime = get_runtime()
            INFINITE_CANVAS_STATIC_ROUTE_PREFIX = runtime['INFINITE_CANVAS_STATIC_ROUTE_PREFIX']

            request_path = urllib.parse.urlsplit(self.path).path
            proxy_prefix = f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/omnia/v1/"
            if not request_path.startswith(proxy_prefix):
                self.send_json({"success": False, "message": "接口不存在"}, status=404)
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def end_headers(self) -> None:
            runtime = get_runtime()
            INFINITE_CANVAS_STATIC_ROUTE_PREFIX = runtime['INFINITE_CANVAS_STATIC_ROUTE_PREFIX']
            build_image_attachment_header = runtime['build_image_attachment_header']

            request_url = urllib.parse.urlsplit(str(getattr(self, "path", "/") or "/"))
            request_path = urllib.parse.unquote(request_url.path or "/")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Expose-Headers", "Content-Disposition, Content-Type")
            canvas_prefix = INFINITE_CANVAS_STATIC_ROUTE_PREFIX.rstrip("/")
            if request_path == canvas_prefix or request_path == f"{canvas_prefix}/" or (
                request_path.startswith(f"{canvas_prefix}/")
                and not Path(request_path).suffix
            ):
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            attachment = build_image_attachment_header(
                self.path,
                status_code=getattr(self, "_response_status", 0),
                content_type=getattr(self, "_response_content_type", ""),
                method=self.command,
            )
            if attachment:
                self.send_header("Content-Disposition", attachment)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
            super().end_headers()

        def serve_infinite_canvas_omnia_asset(self, query_text: str) -> None:
            runtime = get_runtime()
            AUTH_QUERY_TOKEN_KEY = runtime['AUTH_QUERY_TOKEN_KEY']
            AUTH_QUERY_USER_KEY = runtime['AUTH_QUERY_USER_KEY']
            build_auth_token = runtime['build_auth_token']
            get_external_request_kwargs = runtime['get_external_request_kwargs']
            get_request_limiter = runtime['get_request_limiter']
            requests = runtime['requests']

            query = urllib.parse.parse_qs(query_text)
            username = str((query.get(AUTH_QUERY_USER_KEY) or [""])[0]).strip()
            auth_token = str((query.get(AUTH_QUERY_TOKEN_KEY) or [""])[0]).strip()
            expected_token = build_auth_token(username) if username else ""
            if not username or not auth_token or not hmac.compare_digest(auth_token, expected_token):
                self.send_json({"success": False, "message": "无效的画布访问凭证"}, status=403)
                return

            asset_url = str((query.get("url") or [""])[0]).strip()
            parsed = urllib.parse.urlsplit(asset_url)
            host = str(parsed.hostname or "").lower()
            allowed_host = (
                host == "omniakey.com"
                or host.endswith(".omniakey.com")
                or host.endswith(".r2.cloudflarestorage.com")
                or host.endswith(".r2.dev")
            )
            if parsed.scheme != "https" or not allowed_host:
                self.send_json({"success": False, "message": "无效的图片地址"}, status=400)
                return
            from Department.视觉设计部.xiaoha.request_limits import RequestQueueFull
            try:
                with get_request_limiter().slot("download"):
                    response = requests.get(
                        asset_url,
                        allow_redirects=False,
                        proxies={"http": None, "https": None},
                        **get_external_request_kwargs(timeout=60, use_proxy=False),
                    )
                    response.raise_for_status()
                content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
                if not content_type.startswith("image/"):
                    self.send_json({"success": False, "message": "返回内容不是图片"}, status=502)
                    return
                if len(response.content) > 40 * 1024 * 1024:
                    self.send_json({"success": False, "message": "图片超过 40MB 限制"}, status=413)
                    return
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(response.content)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(response.content)
            except requests.RequestException as exc:
                self.send_json({"success": False, "message": f"图片下载失败：{exc}"}, status=502)
            except RequestQueueFull as exc:
                self.send_json({"success": False, "message": str(exc)}, status=429)

        def serve_infinite_canvas_bootstrap(self, query_text: str) -> None:
            runtime = get_runtime()
            AUTH_QUERY_TOKEN_KEY = runtime['AUTH_QUERY_TOKEN_KEY']
            AUTH_QUERY_USER_KEY = runtime['AUTH_QUERY_USER_KEY']
            INFINITE_CANVAS_IMAGE_MODELS = runtime['INFINITE_CANVAS_IMAGE_MODELS']
            INFINITE_CANVAS_STATIC_ROUTE_PREFIX = runtime['INFINITE_CANVAS_STATIC_ROUTE_PREFIX']
            INFINITE_CANVAS_TEXT_MODELS = runtime['INFINITE_CANVAS_TEXT_MODELS']
            NANO_BANANA_MODEL = runtime['NANO_BANANA_MODEL']
            build_auth_token = runtime['build_auth_token']
            load_omnia_api_key = runtime['load_omnia_api_key']

            query = urllib.parse.parse_qs(query_text)
            username = str((query.get(AUTH_QUERY_USER_KEY) or [""])[0]).strip()
            auth_token = str((query.get(AUTH_QUERY_TOKEN_KEY) or [""])[0]).strip()
            expected_token = build_auth_token(username) if username else ""
            if not username or not auth_token or not hmac.compare_digest(auth_token, expected_token):
                self.send_json({"success": False, "message": "无效的画布访问凭证"}, status=403)
                return

            omnia_api_key = load_omnia_api_key()
            if not omnia_api_key:
                self.send_json(
                    {"success": False, "message": "OMNIAKEY_API_KEY 未配置"},
                    status=503,
                )
                return

            omnia_image_models = list(INFINITE_CANVAS_IMAGE_MODELS)
            text_models = list(INFINITE_CANVAS_TEXT_MODELS)
            from Department.视觉设计部.xiaoha.canvas_api_proxy import build_canvas_token
            canvas_token = build_canvas_token(username, auth_token)
            channels = [
                {
                    "id": "xiaoha-omnia",
                    "name": "小哈 OmniaKey",
                    "baseUrl": f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/omnia/v1",
                    "apiKey": canvas_token,
                    "apiFormat": "openai",
                    "models": [*omnia_image_models, *text_models],
                },
            ]
            self.send_json(
                {
                    "success": True,
                    "config": {
                        "configVersion": "2026-11-19-shared-queue-" + hashlib.sha256(canvas_token.encode()).hexdigest()[:12],
                        "channel": channels[0],
                        "channels": channels,
                        "imageModel": NANO_BANANA_MODEL,
                        "imageModelNext": NANO_BANANA_MODEL,
                        "textModel": text_models[0],
                        "videoModel": "",
                        "audioModel": "",
                        "imageModels": omnia_image_models,
                        "imageModelsNext": omnia_image_models,
                        "textModels": text_models,
                        "videoModels": [],
                        "audioModels": [],
                    },
                }
            )

        def serve_infinite_canvas_model_hd(self, query_text: str) -> None:
            runtime = get_runtime()
            ARK_SEEDREAM_5_PRO_MODEL = runtime['ARK_SEEDREAM_5_PRO_MODEL']
            AUTH_QUERY_TOKEN_KEY = runtime['AUTH_QUERY_TOKEN_KEY']
            AUTH_QUERY_USER_KEY = runtime['AUTH_QUERY_USER_KEY']
            DEFAULT_ASPECT_RATIO = runtime['DEFAULT_ASPECT_RATIO']
            INFINITE_CANVAS_MODEL_HD_MAX_REQUEST_BYTES = runtime['INFINITE_CANVAS_MODEL_HD_MAX_REQUEST_BYTES']
            INFINITE_CANVAS_MODEL_HD_METHODS = runtime['INFINITE_CANVAS_MODEL_HD_METHODS']
            INFINITE_CANVAS_MODEL_HD_METHOD_NANO = runtime['INFINITE_CANVAS_MODEL_HD_METHOD_NANO']
            INFINITE_CANVAS_MODEL_HD_METHOD_SEEDREAM = runtime['INFINITE_CANVAS_MODEL_HD_METHOD_SEEDREAM']
            NANO_BANANA_MODEL = runtime['NANO_BANANA_MODEL']
            build_auth_token = runtime['build_auth_token']
            build_portrait_hd_prompt = runtime['build_portrait_hd_prompt']
            build_portrait_hd_size_instruction = runtime['build_portrait_hd_size_instruction']
            build_prompt = runtime['build_prompt']
            call_ark_seedream_images_api = runtime['call_ark_seedream_images_api']
            call_openrouter_portrait_hd = runtime['call_openrouter_portrait_hd']
            decode_data_url = runtime['decode_data_url']
            finalize_portrait_hd_result = runtime['finalize_portrait_hd_result']
            format_user_facing_error_message = runtime['format_user_facing_error_message']
            get_feature_by_key = runtime['get_feature_by_key']
            get_uploaded_input_dimensions = runtime['get_uploaded_input_dimensions']
            image_bytes_to_data_url = runtime['image_bytes_to_data_url']
            load_image_bytes_from_url = runtime['load_image_bytes_from_url']
            record_infinite_canvas_usage = runtime['record_infinite_canvas_usage']

            query = urllib.parse.parse_qs(query_text)
            username = str((query.get(AUTH_QUERY_USER_KEY) or [""])[0]).strip()
            auth_token = str((query.get(AUTH_QUERY_TOKEN_KEY) or [""])[0]).strip()
            expected_token = build_auth_token(username) if username else ""
            if not username or not auth_token or not hmac.compare_digest(auth_token, expected_token):
                self.send_json({"success": False, "message": "无效的画布访问凭证"}, status=403)
                return

            try:
                content_length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                content_length = 0
            if content_length <= 0 or content_length > INFINITE_CANVAS_MODEL_HD_MAX_REQUEST_BYTES:
                self.send_json({"success": False, "message": "模特高清输入图片为空或超过 50MB"}, status=413)
                return

            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                image_data_url = str(payload.get("image") or "").strip()
                decoded_image = decode_data_url(image_data_url)
                if not decoded_image:
                    raise ValueError("无法读取输入图片")
                image_bytes, mime_type = decoded_image
                if not str(mime_type or "").lower().startswith("image/"):
                    raise ValueError("输入内容不是图片")
                source_input = {
                    "data": image_bytes,
                    "name": "infinite_canvas_model_hd.png",
                    "type": mime_type,
                }
                feature = get_feature_by_key("hd_batch")
                if feature is None:
                    raise RuntimeError("模特高清功能未初始化")
                method = str(payload.get("method") or INFINITE_CANVAS_MODEL_HD_METHOD_NANO).strip()
                if method not in INFINITE_CANVAS_MODEL_HD_METHODS:
                    raise ValueError("不支持的模特高清处理方式")
                custom_prompt = str(payload.get("prompt") or "").strip()[:500]
                final_prompt = build_prompt(
                    feature,
                    custom_prompt,
                    DEFAULT_ASPECT_RATIO,
                    "本次请求来自无限画布的模特高清模块，只处理第1张连接的原图。",
                )
                if method == INFINITE_CANVAS_MODEL_HD_METHOD_SEEDREAM:
                    result = call_ark_seedream_images_api(
                        prompt=(
                            build_portrait_hd_prompt(final_prompt)
                            + "\n\n"
                            + build_portrait_hd_size_instruction(source_input)
                        ),
                        uploaded_files=[source_input],
                    )
                    result = finalize_portrait_hd_result(result, source_input)
                    result["channel"] = "即梦 5 Pro 模特高清 · 原图尺寸输出"
                else:
                    result = call_openrouter_portrait_hd(
                        model=NANO_BANANA_MODEL,
                        prompt=final_prompt,
                        aspect_ratio=DEFAULT_ASPECT_RATIO,
                        uploaded_files=[source_input],
                    )
                result_image = next(iter(list(result.get("images") or [])[:1]), "")
                if not result_image:
                    raise RuntimeError("模特高清没有返回图片")
                result_bytes, result_mime_type = load_image_bytes_from_url(str(result_image))
                width, height = get_uploaded_input_dimensions(
                    {
                        "data": result_bytes,
                        "name": "infinite_canvas_model_hd_result.png",
                        "type": result_mime_type or "image/png",
                    }
                )
                usage_model = (
                    ARK_SEEDREAM_5_PRO_MODEL
                    if method == INFINITE_CANVAS_MODEL_HD_METHOD_SEEDREAM
                    else NANO_BANANA_MODEL
                )
                record_infinite_canvas_usage(
                    account_name=username,
                    feature_name="模特高清",
                    model=usage_model,
                    image_count=1,
                )
                self.send_json(
                    {
                        "success": True,
                        "image": image_bytes_to_data_url(
                            result_bytes,
                            result_mime_type or "image/png",
                        ),
                        "width": width,
                        "height": height,
                        "channel": str(result.get("channel") or "Nano Banana 2.1 模特高清"),
                    }
                )
            except Exception as exc:
                print(f"[infinite-canvas-model-hd] {exc}", file=sys.stderr)
                self.send_json(
                    {
                        "success": False,
                        "message": format_user_facing_error_message(exc),
                    },
                    status=502,
                )

        def serve_infinite_canvas_detect_public_figures(self, query_text: str) -> None:
            runtime = get_runtime()
            AUTH_QUERY_TOKEN_KEY = runtime['AUTH_QUERY_TOKEN_KEY']
            AUTH_QUERY_USER_KEY = runtime['AUTH_QUERY_USER_KEY']
            INFINITE_CANVAS_MODEL_HD_MAX_REQUEST_BYTES = runtime['INFINITE_CANVAS_MODEL_HD_MAX_REQUEST_BYTES']
            PUBLIC_FIGURE_DETECTION_MODELS = runtime['PUBLIC_FIGURE_DETECTION_MODELS']
            PUBLIC_FIGURE_DETECTION_PROMPT = runtime['PUBLIC_FIGURE_DETECTION_PROMPT']
            build_auth_token = runtime['build_auth_token']
            call_openrouter = runtime['call_openrouter']
            decode_data_url = runtime['decode_data_url']
            format_user_facing_error_message = runtime['format_user_facing_error_message']

            query = urllib.parse.parse_qs(query_text)
            username = str((query.get(AUTH_QUERY_USER_KEY) or [""])[0]).strip()
            auth_token = str((query.get(AUTH_QUERY_TOKEN_KEY) or [""])[0]).strip()
            expected_token = build_auth_token(username) if username else ""
            if not username or not auth_token or not hmac.compare_digest(auth_token, expected_token):
                self.send_json({"success": False, "message": "无效的画布访问凭证"}, status=403)
                return

            try:
                content_length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                content_length = 0
            if content_length <= 0 or content_length > INFINITE_CANVAS_MODEL_HD_MAX_REQUEST_BYTES:
                self.send_json({"success": False, "message": "检测图片为空或超过 50MB"}, status=413)
                return

            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                raw_images = payload.get("images")
                if not isinstance(raw_images, list) or not raw_images:
                    raise ValueError("请至少提供 1 张待检测图片")
                uploaded_files: list[dict[str, Any]] = []
                for index, data_url in enumerate(list(raw_images)[:8]):
                    decoded_image = decode_data_url(str(data_url or "").strip())
                    if not decoded_image:
                        continue
                    image_bytes, mime_type = decoded_image
                    uploaded_files.append(
                        {
                            "data": image_bytes,
                            "name": f"public_figure_check_{index + 1}.png",
                            "type": mime_type or "image/png",
                        }
                    )
                if not uploaded_files:
                    raise ValueError("检测图片解析失败")
                parsed: dict[str, Any] | None = None
                for detection_model in PUBLIC_FIGURE_DETECTION_MODELS:
                    try:
                        answer = call_openrouter(
                            model=detection_model,
                            prompt=PUBLIC_FIGURE_DETECTION_PROMPT,
                            uploaded_files=uploaded_files,
                            output_mode="text",
                        )
                    except RuntimeError as exc:
                        if "上游返回空结果" not in str(exc):
                            raise
                        print(f"[infinite-canvas-detect] {detection_model}: {exc}", file=sys.stderr)
                        continue
                    text = str(answer.get("text") or "").strip()
                    matched = re.search(r"\{[\s\S]*\}", text)
                    try:
                        candidate = json.loads(matched.group(0)) if matched else None
                    except json.JSONDecodeError:
                        candidate = None
                    if isinstance(candidate, dict):
                        parsed = candidate
                        break
                    print(f"[infinite-canvas-detect] {detection_model}: 未返回有效 JSON：{text[:300]}", file=sys.stderr)
                if parsed is None:
                    # Every model refused to judge the images; fall back to the manual confirmation dialog.
                    self.send_json({"success": True, "detected": True, "names": [], "uncertain": True})
                    return
                names = [str(name).strip() for name in list(parsed.get("names") or []) if str(name).strip()]
                self.send_json(
                    {
                        "success": True,
                        "detected": bool(parsed.get("detected")),
                        "names": names[:5],
                    }
                )
            except Exception as exc:
                print(f"[infinite-canvas-detect] {exc}", file=sys.stderr)
                self.send_json(
                    {
                        "success": False,
                        "message": format_user_facing_error_message(exc),
                    },
                    status=502,
                )

        def serve_infinite_canvas_usage_record(self, query_text: str) -> None:
            runtime = get_runtime()
            AUTH_QUERY_TOKEN_KEY = runtime['AUTH_QUERY_TOKEN_KEY']
            AUTH_QUERY_USER_KEY = runtime['AUTH_QUERY_USER_KEY']
            BATCH_MULTI_IMAGE_MAX_FILES = runtime['BATCH_MULTI_IMAGE_MAX_FILES']
            INFINITE_CANVAS_USAGE_ACTION_LABELS = runtime['INFINITE_CANVAS_USAGE_ACTION_LABELS']
            build_auth_token = runtime['build_auth_token']
            format_user_facing_error_message = runtime['format_user_facing_error_message']
            record_infinite_canvas_usage = runtime['record_infinite_canvas_usage']

            query = urllib.parse.parse_qs(query_text)
            username = str((query.get(AUTH_QUERY_USER_KEY) or [""])[0]).strip()
            auth_token = str((query.get(AUTH_QUERY_TOKEN_KEY) or [""])[0]).strip()
            expected_token = build_auth_token(username) if username else ""
            if not username or not auth_token or not hmac.compare_digest(auth_token, expected_token):
                self.send_json({"success": False, "message": "无效的画布访问凭证"}, status=403)
                return

            try:
                content_length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                content_length = 0
            if content_length <= 0 or content_length > 16 * 1024:
                self.send_json({"success": False, "message": "使用记录参数无效"}, status=413)
                return

            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                action = str(payload.get("action") or "").strip()
                feature_name = INFINITE_CANVAS_USAGE_ACTION_LABELS.get(action)
                if not feature_name:
                    raise ValueError("不支持的画布使用记录类型")
                model = str(payload.get("model") or "").strip()[:200]
                image_count = max(1, min(int(payload.get("imageCount") or 1), BATCH_MULTI_IMAGE_MAX_FILES))
                if not record_infinite_canvas_usage(
                    account_name=username,
                    feature_name=feature_name,
                    model=model,
                    image_count=image_count,
                ):
                    raise RuntimeError("使用记录写入失败")
                self.send_json({"success": True})
            except Exception as exc:
                print(f"[infinite-canvas-usage] {exc}", file=sys.stderr)
                self.send_json(
                    {
                        "success": False,
                        "message": format_user_facing_error_message(exc),
                    },
                    status=502,
                )

        def serve_infinite_canvas_image_feature(self, query_text: str) -> None:
            runtime = get_runtime()
            ARK_SEEDREAM_5_PRO_MODEL = runtime['ARK_SEEDREAM_5_PRO_MODEL']
            AUTH_QUERY_TOKEN_KEY = runtime['AUTH_QUERY_TOKEN_KEY']
            AUTH_QUERY_USER_KEY = runtime['AUTH_QUERY_USER_KEY']
            CANVAS_A_PLUS_FEATURE_KEYS = runtime['CANVAS_A_PLUS_FEATURE_KEYS']
            DEFAULT_ASPECT_RATIO = runtime['DEFAULT_ASPECT_RATIO']
            INFINITE_CANVAS_IMAGE_FEATURE_KEYS = runtime['INFINITE_CANVAS_IMAGE_FEATURE_KEYS']
            INFINITE_CANVAS_IMAGE_FEATURE_MAX_REQUEST_BYTES = runtime['INFINITE_CANVAS_IMAGE_FEATURE_MAX_REQUEST_BYTES']
            INFINITE_CANVAS_IMAGE_FEATURE_REFERENCE_KEYS = runtime['INFINITE_CANVAS_IMAGE_FEATURE_REFERENCE_KEYS']
            INFINITE_CANVAS_IMAGE_FEATURE_SINGLE_INPUT_KEYS = runtime['INFINITE_CANVAS_IMAGE_FEATURE_SINGLE_INPUT_KEYS']
            INFINITE_CANVAS_MAX_INPUT_IMAGES = runtime['INFINITE_CANVAS_MAX_INPUT_IMAGES']
            INFINITE_CANVAS_MODEL_HD_METHODS = runtime['INFINITE_CANVAS_MODEL_HD_METHODS']
            INFINITE_CANVAS_MODEL_HD_METHOD_NANO = runtime['INFINITE_CANVAS_MODEL_HD_METHOD_NANO']
            INFINITE_CANVAS_MODEL_HD_METHOD_SEEDREAM = runtime['INFINITE_CANVAS_MODEL_HD_METHOD_SEEDREAM']
            JIMENG_HD_FEATURE_KEY = runtime['JIMENG_HD_FEATURE_KEY']
            JIMENG_HD_MODEL_NAME = runtime['JIMENG_HD_MODEL_NAME']
            NANO_BANANA_MODEL = runtime['NANO_BANANA_MODEL']
            OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX = runtime['OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX']
            build_auth_token = runtime['build_auth_token']
            build_infinite_canvas_image_feature_notes = runtime['build_infinite_canvas_image_feature_notes']
            build_prompt = runtime['build_prompt']
            decode_data_url = runtime['decode_data_url']
            format_user_facing_error_message = runtime['format_user_facing_error_message']
            get_feature_by_key = runtime['get_feature_by_key']
            get_model_display_name = runtime['get_model_display_name']
            get_uploaded_input_dimensions = runtime['get_uploaded_input_dimensions']
            image_bytes_to_data_url = runtime['image_bytes_to_data_url']
            load_image_bytes_from_url = runtime['load_image_bytes_from_url']
            process_batch_group = runtime['process_batch_group']
            record_infinite_canvas_usage = runtime['record_infinite_canvas_usage']
            run_ai_background_cutout_job = runtime['run_ai_background_cutout_job']

            query = urllib.parse.parse_qs(query_text)
            username = str((query.get(AUTH_QUERY_USER_KEY) or [""])[0]).strip()
            auth_token = str((query.get(AUTH_QUERY_TOKEN_KEY) or [""])[0]).strip()
            expected_token = build_auth_token(username) if username else ""
            if not username or not auth_token or not hmac.compare_digest(auth_token, expected_token):
                self.send_json({"success": False, "message": "无效的画布访问凭证"}, status=403)
                return

            try:
                content_length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                content_length = 0
            if content_length <= 0 or content_length > INFINITE_CANVAS_IMAGE_FEATURE_MAX_REQUEST_BYTES:
                self.send_json({"success": False, "message": "图片功能输入为空或请求超过 80MB"}, status=413)
                return

            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                feature_key = str(payload.get("feature") or "").strip()
                if feature_key not in INFINITE_CANVAS_IMAGE_FEATURE_KEYS:
                    raise ValueError("不支持的图片功能")
                feature = get_feature_by_key(feature_key)
                if feature is None:
                    raise RuntimeError("图片功能未初始化")

                raw_images = payload.get("images")
                if not isinstance(raw_images, list) or not raw_images:
                    raise ValueError("请先提供 1 张待处理原图")
                source_inputs: list[dict[str, Any]] = []
                if feature_key in CANVAS_A_PLUS_FEATURE_KEYS and len(raw_images) > int(feature.get("max_input_images") or 10):
                    raise ValueError("连接的A+素材图片过多，请减少连线")
                image_limit = int(feature.get("max_input_images") or 10) if feature_key in CANVAS_A_PLUS_FEATURE_KEYS else INFINITE_CANVAS_MAX_INPUT_IMAGES
                for image_index, raw_image in enumerate(raw_images[:image_limit], start=1):
                    decoded_image = decode_data_url(str(raw_image or "").strip())
                    if not decoded_image:
                        raise ValueError(f"无法读取第 {image_index} 张输入图片")
                    image_bytes, mime_type = decoded_image
                    if not str(mime_type or "").lower().startswith("image/"):
                        raise ValueError(f"第 {image_index} 个输入内容不是图片")
                    source_inputs.append(
                        {
                            "data": image_bytes,
                            "name": f"infinite_canvas_feature_{image_index}.png",
                            "type": mime_type,
                        }
                    )
                if feature_key in CANVAS_A_PLUS_FEATURE_KEYS:
                    from Department.视觉设计部.xiaoha.canvas_a_plus import run_node, prepare_psd_download
                    result = run_node(SimpleNamespace(**get_runtime()), feature, source_inputs,
                                      str(payload.get("prompt") or "").strip()[:10000], username)
                    images = []
                    for image_url in result.get("images") or []:
                        data, mime = load_image_bytes_from_url(str(image_url))
                        images.append(image_bytes_to_data_url(data, mime or "image/png"))
                    self.send_json({"success": True, "image": images[0], "images": images,
                                    "featureName": feature["name"], "text": str(result.get("text") or ""),
                                    "psdUrl": prepare_psd_download(SimpleNamespace(**get_runtime()), result, username)})
                    return
                if feature_key in INFINITE_CANVAS_IMAGE_FEATURE_REFERENCE_KEYS and len(source_inputs) < 2:
                    raise ValueError(f"{str(feature.get('name') or '当前功能')}还需要连接至少 1 张参考图")
                if feature_key in INFINITE_CANVAS_IMAGE_FEATURE_SINGLE_INPUT_KEYS:
                    source_inputs = source_inputs[:1]
                if feature_key == "ai_qa_image":
                    source_inputs = source_inputs[:3]

                custom_prompt = str(payload.get("prompt") or "").strip()[:2000]
                if feature_key == "ai_qa_image" and not custom_prompt:
                    raise ValueError("AI问答生图需要填写文字要求")
                method = str(payload.get("method") or INFINITE_CANVAS_MODEL_HD_METHOD_NANO).strip()
                if feature_key in {"product_retouch", "product_retouch_local"}:
                    method = INFINITE_CANVAS_MODEL_HD_METHOD_NANO
                if method not in INFINITE_CANVAS_MODEL_HD_METHODS:
                    raise ValueError("不支持的图片处理模型")
                model = (
                    ARK_SEEDREAM_5_PRO_MODEL
                    if method == INFINITE_CANVAS_MODEL_HD_METHOD_SEEDREAM
                    else NANO_BANANA_MODEL
                )
                raw_outpaint = payload.get("outpaint")
                outpaint_payload = raw_outpaint if isinstance(raw_outpaint, dict) else {}
                outpaint_settings = {
                    direction: max(
                        0,
                        min(
                            OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
                            int(outpaint_payload.get(direction, 0) or 0),
                        ),
                    )
                    for direction in ("top", "bottom", "left", "right")
                }
                if feature_key == "outpaint" and not sum(outpaint_settings.values()):
                    raise ValueError("模特扩图需要至少设置一个方向的扩展像素")

                extra_notes = build_infinite_canvas_image_feature_notes(
                    feature_key,
                    len(source_inputs),
                    outpaint_settings,
                )
                final_prompt = build_prompt(
                    feature,
                    custom_prompt,
                    DEFAULT_ASPECT_RATIO,
                    extra_notes,
                )
                job_context = {
                    "feature": feature,
                    "model": model,
                    "prompt": final_prompt,
                    "uploaded_files": source_inputs,
                    "output_mode": "image",
                    "max_output_images": 1,
                    "target_size": None,
                    "outpaint_settings": outpaint_settings if feature_key == "outpaint" else {},
                    "aspect_ratio": DEFAULT_ASPECT_RATIO,
                }
                if feature_key == "background_cutout":
                    result = run_ai_background_cutout_job(job_context)
                else:
                    group_result = process_batch_group(job_context, source_inputs, 1)
                    result = {
                        "images": list(group_result.get("images") or []),
                        "text": str(group_result.get("text") or "").strip(),
                    }

                result_image = next(iter(list(result.get("images") or [])[:1]), "")
                if not result_image:
                    result_detail = str(result.get("text") or "").strip()
                    result_detail = result_detail[:160].strip()
                    raise RuntimeError(
                        f"{str(feature.get('name') or '图片功能')}没有返回图片"
                        + (f"：{result_detail}" if result_detail else "，请调整参数后重试")
                    )
                result_bytes, result_mime_type = load_image_bytes_from_url(str(result_image))
                width, height = get_uploaded_input_dimensions(
                    {
                        "data": result_bytes,
                        "name": "infinite_canvas_feature_result.png",
                        "type": result_mime_type or "image/png",
                    }
                )
                usage_model = (
                    JIMENG_HD_MODEL_NAME
                    if feature_key == JIMENG_HD_FEATURE_KEY
                    else "智能抠图专用接口"
                    if feature_key == "background_cutout"
                    else model
                )
                record_infinite_canvas_usage(
                    account_name=username,
                    feature_name=str(feature.get("name") or feature_key),
                    model=usage_model,
                    image_count=1,
                )
                self.send_json(
                    {
                        "success": True,
                        "image": image_bytes_to_data_url(
                            result_bytes,
                            result_mime_type or "image/png",
                        ),
                        "width": width,
                        "height": height,
                        "feature": feature_key,
                        "featureName": str(feature.get("name") or feature_key),
                        "channel": (
                            "即梦智能超清 · 原生 8K"
                            if feature_key == JIMENG_HD_FEATURE_KEY
                            else "智能抠图"
                            if feature_key == "background_cutout"
                            else f"{get_model_display_name(model)} · {str(feature.get('name') or feature_key)}"
                        ),
                    }
                )
            except Exception as exc:
                print(f"[infinite-canvas-image-feature] {exc}", file=sys.stderr)
                self.send_json(
                    {
                        "success": False,
                        "message": format_user_facing_error_message(exc),
                    },
                    status=502,
                )

        def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def translate_path(self, path: str) -> str:
            runtime = get_runtime()
            HISTORY_STATIC_ROUTE_PREFIX = runtime['HISTORY_STATIC_ROUTE_PREFIX']
            INFINITE_CANVAS_STATIC_ROUTE_PREFIX = runtime['INFINITE_CANVAS_STATIC_ROUTE_PREFIX']
            JIMENG_UPLOAD_ROUTE_PREFIX = runtime['JIMENG_UPLOAD_ROUTE_PREFIX']

            request_path = urllib.parse.unquote(urllib.parse.urlsplit(path).path or "/")
            target_directory = ""
            relative_path_text = ""
            upload_prefix = JIMENG_UPLOAD_ROUTE_PREFIX.rstrip("/")
            history_prefix = HISTORY_STATIC_ROUTE_PREFIX.rstrip("/")
            canvas_prefix = INFINITE_CANVAS_STATIC_ROUTE_PREFIX.rstrip("/")
            if request_path == upload_prefix:
                request_path = f"{upload_prefix}/"
            if request_path == history_prefix:
                request_path = f"{history_prefix}/"
            if request_path == canvas_prefix:
                request_path = f"{canvas_prefix}/"
            if request_path.startswith(f"{upload_prefix}/"):
                target_directory = self.upload_directory
                relative_path_text = request_path[len(f"{upload_prefix}/") :]
            elif request_path.startswith(f"{history_prefix}/"):
                target_directory = self.history_directory
                relative_path_text = request_path[len(f"{history_prefix}/") :]
            elif request_path.startswith(f"{canvas_prefix}/"):
                target_directory = self.canvas_directory
                relative_path_text = request_path[len(f"{canvas_prefix}/") :]
            else:
                return str(Path(self.directory or ".") / "__not_found__")
            relative_path = Path(relative_path_text)
            safe_parts = [part for part in relative_path.parts if part not in ("", ".", "..")]
            target_path = Path(target_directory).joinpath(*safe_parts)
            if target_directory == self.canvas_directory and not target_path.exists():
                return str(Path(self.canvas_directory) / "index.html")
            return str(target_path)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return JimengStaticRequestHandler
