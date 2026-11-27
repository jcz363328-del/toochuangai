"""Authenticated canvas access to the same provider queues as the Xiaoha UI."""
from __future__ import annotations

import base64
import hmac
import json
import math
import os
import re
import time
from contextlib import contextmanager
from email import policy
from email.parser import BytesParser
from threading import BoundedSemaphore
from urllib.parse import parse_qs

import requests


MAX_BODY_BYTES = 50 * 1024 * 1024
MAX_IMAGES = 15
IMAGE_PATHS = {"/images/generations", "/images/edits"}
TEXT_PATHS = {"/responses", "/chat/completions"}

try:
    CANVAS_MAX_REQUESTS = max(1, min(32, int(os.getenv("XIAOHA_CANVAS_MAX_REQUESTS", "8"))))
except ValueError:
    CANVAS_MAX_REQUESTS = 8
# Bound uploaded bodies and streaming handlers before reading their potentially
# large payloads; full queues reject immediately instead of creating waiters.
_request_slots = BoundedSemaphore(CANVAS_MAX_REQUESTS)


class CanvasRequestError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


@contextmanager
def canvas_request():
    """Admit one complete canvas operation before allocating its upload body."""
    from Department.视觉设计部.xiaoha.request_limits import admitted_job

    if not _request_slots.acquire(blocking=False):
        raise CanvasRequestError("画布请求队列已满，本次请求尚未提交，请稍后再试", 429)
    try:
        with admitted_job():
            yield
    finally:
        _request_slots.release()


def serve_legacy_canvas_request(handler, site, query_text, callback):
    """Share the upload bound with existing HD, feature and detection routes."""
    from Department.视觉设计部.xiaoha.request_limits import RequestQueueFull

    try:
        query = parse_qs(query_text)
        username = str((query.get(site.AUTH_QUERY_USER_KEY) or [""])[0]).strip()
        signature = str((query.get(site.AUTH_QUERY_TOKEN_KEY) or [""])[0]).strip()
        if not username or not signature or not hmac.compare_digest(signature, site.build_auth_token(username)):
            raise CanvasRequestError("无效的画布访问凭证", 403)
        with canvas_request():
            callback(query_text)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        return
    except Exception as exc:
        status = exc.status if isinstance(exc, CanvasRequestError) else 429 if isinstance(exc, RequestQueueFull) else 502
        try:
            handler.send_json({"success": False, "message": site.format_user_facing_error_message(exc)}, status=status)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def build_canvas_token(username, signature):
    # Reuse the existing signed app session, never the upstream provider key.
    raw = json.dumps([username, signature], ensure_ascii=False, separators=(",", ":")).encode()
    return "xh1." + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def authenticate_canvas_token(authorization, build_auth_token):
    prefix = "Bearer xh1."
    if not str(authorization or "").startswith(prefix) or len(authorization) > 4096:
        raise CanvasRequestError("无效的画布访问凭证，请从小哈重新打开画布", 403)
    try:
        encoded = authorization[len(prefix):]
        username, signature = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if not isinstance(username, str) or not isinstance(signature, str) or not username:
            raise ValueError()
        if not hmac.compare_digest(signature.encode(), build_auth_token(username).encode()):
            raise ValueError()
    except (ValueError, TypeError, UnicodeError) as exc:
        raise CanvasRequestError("无效的画布访问凭证，请从小哈重新打开画布", 403) from exc
    return username


def read_canvas_payload(handler):
    try:
        size = int(handler.headers.get("Content-Length") or 0)
    except (TypeError, ValueError) as exc:
        raise CanvasRequestError("请求长度无效") from exc
    if size <= 0 or size > MAX_BODY_BYTES:
        raise CanvasRequestError("请求为空或超过 50MB", 413)
    body = handler.rfile.read(size)
    if len(body) != size:
        raise CanvasRequestError("请求内容未传输完整")
    content_type = str(handler.headers.get("Content-Type") or "")
    files = []
    if content_type.lower().startswith("multipart/form-data"):
        message = BytesParser(policy=policy.default).parsebytes(
            ("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + body
        )
        if not message.is_multipart():
            raise CanvasRequestError("图片上传格式无效")
        payload = {}
        parts = list(message.iter_parts())
        if len(parts) > 32:
            raise CanvasRequestError("上传字段过多")
        for part in parts:
            name = part.get_param("name", header="content-disposition")
            data = part.get_payload(decode=True) or b""
            if name == "mask":
                raise CanvasRequestError("OmniaKey 图片编辑暂不支持蒙版")
            if name in {"image", "image[]"}:
                if not data or not part.get_content_type().startswith("image/"):
                    raise CanvasRequestError("上传内容不是有效图片")
                files.append({"name": part.get_filename() or "reference.png", "type": part.get_content_type(), "data": data})
            elif part.get_filename():
                raise CanvasRequestError("不支持的上传字段")
            elif name:
                payload[name] = data.decode("utf-8")
        if len(files) > MAX_IMAGES:
            raise CanvasRequestError("最多上传 15 张参考图")
    elif content_type.lower().startswith("application/json"):
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError) as exc:
            raise CanvasRequestError("请求 JSON 格式无效") from exc
        if not isinstance(payload, dict):
            raise CanvasRequestError("请求必须为 JSON 对象")
    else:
        raise CanvasRequestError("不支持的请求格式", 415)
    return payload, files


def _image_options(site, payload):
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt or len(prompt) > 30000:
        raise CanvasRequestError("请填写图片要求，长度不能超过 30000 字")
    try:
        count = int(payload.get("n", 1))
    except (TypeError, ValueError) as exc:
        raise CanvasRequestError("生成张数无效") from exc
    if not 1 <= count <= MAX_IMAGES:
        raise CanvasRequestError("单次生成张数必须在 1 到 15 之间")
    size = str(payload.get("size") or "").strip().lower()
    ratio, resolution = site.DEFAULT_ASPECT_RATIO, ""
    if size and size != "auto":
        matched = re.fullmatch(r"(\d{1,5})x(\d{1,5})", size)
        if not matched:
            raise CanvasRequestError("图片尺寸格式无效")
        width, height = map(int, matched.groups())
        if min(width, height) < 64 or max(width, height) > 8192 or width * height > 4096 ** 2:
            raise CanvasRequestError("图片尺寸超出限制")
        ratio = min(site.GEMINI_IMAGE_ASPECT_RATIOS, key=lambda item: abs(float(item.split(":")[0]) / float(item.split(":")[1]) - width / height))
        edge = math.sqrt(width * height)
        resolution = "4K" if edge >= 3000 else "2K" if edge >= 1500 else "1K"
    else:
        size = ""
        resolution = {"high": "4K", "medium": "2K", "low": "1K", "hd": "2K", "standard": "1K"}.get(str(payload.get("quality") or "").lower(), "")
    return prompt, count, size, ratio, resolution


def generate_canvas_images(site, endpoint, payload, files):
    model = str(payload.get("model") or "")
    if model not in site.INFINITE_CANVAS_IMAGE_MODELS:
        raise CanvasRequestError("画布不支持该图片模型")
    if payload.get("mask"):
        raise CanvasRequestError("OmniaKey 图片编辑暂不支持蒙版")
    if endpoint == "/images/edits" and not files:
        raise CanvasRequestError("图片编辑需要上传参考图")
    if endpoint == "/images/generations" and files:
        raise CanvasRequestError("参考图应通过图片编辑接口提交")
    prompt, count, size, ratio, resolution = _image_options(site, payload)
    images = []
    warning = ""
    # Each image enters the shared account limit independently. A 15-image
    # canvas request must not reserve fifteen upstream slots or bypass the UI.
    for _ in range(count):
        try:
            if site.resolve_omnia_image_model(model) == site.NANO_BANANA_MODEL:
                result = site.call_omnia_sync_image_api(model, prompt, files, ratio, resolution, size=size)
            else:
                result = site.call_omnia_image_api(model, prompt, files, ratio, resolution)
            for image in result.get("images") or []:
                if str(image).startswith("data:"):
                    images.append({"b64_json": str(image).split(",", 1)[1]})
                else:
                    # The same-origin channel deliberately avoids the browser's
                    # old Omnia hostname branch, so resolve signed assets here.
                    data, _mime = site.load_image_bytes_from_url(str(image))
                    images.append({"b64_json": base64.b64encode(data).decode("ascii")})
        except Exception as exc:
            if not images:
                raise
            # Preserve already-paid successful outputs if a later item fails.
            warning = site.format_user_facing_error_message(exc)
            break
    if not images:
        raise RuntimeError("OmniaKey 未返回图片")
    response = {"created": int(time.time()), "data": images}
    if warning:
        response["warning"] = warning
        response["requested_count"] = count
    return response


def proxy_canvas_text(handler, site, endpoint, payload):
    from Department.视觉设计部.xiaoha.request_limits import get_request_limiter
    from Department.视觉设计部.xiaoha.omnia_service import managed_omnia_context, record_omnia_provider_status

    if str(payload.get("model") or "") not in site.INFINITE_CANVAS_TEXT_MODELS:
        raise CanvasRequestError("画布不支持该文字模型")
    if payload.get("background"):
        raise CanvasRequestError("画布暂不支持异步文字请求")
    api_key = site.load_omnia_api_key()
    if not api_key:
        raise CanvasRequestError("OmniaKey 未配置", 503)
    # Keep the original responses/chat payload, including history and tools.
    # The slot covers the entire streamed response, not only the HTTP headers.
    with get_request_limiter().slot("omnia_text"), managed_omnia_context(
        primary_key=api_key, model=str(payload.get("model") or ""),
        api_base=site.OMNIAKEY_API_BASE,
    ):
        # The managed context pins this request to one pool credential
        # until the upstream body is drained and accounting completes.
        api_key = site.load_omnia_api_key()
        record_omnia_provider_status("uncertain")
        try:
            response = requests.post(
                site.OMNIAKEY_API_BASE.rstrip("/") + "/v1" + endpoint,
                json=payload,
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                stream=True,
                **site.get_external_request_kwargs(timeout=(30, 300), use_proxy=False),
            )
        except requests.RequestException as exc:
            raise RuntimeError("OmniaKey 文字请求连接中断或等待超时，远端结果尚未确认，未自动重新提交。") from exc
        with response as upstream:
            if upstream.status_code == 429:
                record_omnia_provider_status("rejected")
                # Surface rejection to the limiter before writing any headers,
                # so its account-wide cooldown also covers canvas text traffic.
                raise CanvasRequestError("OmniaKey 请求过多（HTTP 429），请稍后重试", 429)
            if upstream.status_code >= 500 or upstream.status_code == 408:
                raise CanvasRequestError(
                    f"OmniaKey 文字请求返回 HTTP {upstream.status_code}，远端结果尚未确认，未自动重新提交。",
                    upstream.status_code,
                )
            if upstream.status_code >= 400:
                record_omnia_provider_status("rejected")
            handler.send_response(upstream.status_code)
            handler.send_header("Content-Type", upstream.headers.get("Content-Type", "application/json"))
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("X-Accel-Buffering", "no")
            handler.send_header("Connection", "close")
            handler.close_connection = True
            handler.end_headers()
            handler._canvas_response_started = True
            disconnected = False
            try:
                for chunk in upstream.iter_content(chunk_size=1024):
                    if not chunk or disconnected:
                        continue
                    try:
                        handler.wfile.write(chunk)
                        handler.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        # Finish/drain this upstream operation before freeing
                        # its slot, even if the browser has closed the page.
                        disconnected = True
            except requests.RequestException as exc:
                # Release through the limiter's uncertain-outcome cooldown.
                # The caller closes the existing response without new headers.
                raise RuntimeError("OmniaKey 流连接中断，远端结果尚未确认，未自动重新提交。") from exc
            if upstream.status_code >= 400:
                # Preserve the original error body already sent to the
                # browser while recording this call as failed.
                raise CanvasRequestError(
                    f"OmniaKey 文字请求失败（HTTP {upstream.status_code}）",
                    upstream.status_code,
                )
            record_omnia_provider_status("success")


def serve_canvas_api(handler, site, endpoint, method="POST"):
    handler._canvas_response_started = False
    try:
        authenticate_canvas_token(handler.headers.get("Authorization"), site.build_auth_token)
        if method == "GET" and endpoint == "/models":
            models = dict.fromkeys((*site.INFINITE_CANVAS_IMAGE_MODELS, *site.INFINITE_CANVAS_TEXT_MODELS))
            handler.send_json({"object": "list", "data": [{"id": name, "object": "model"} for name in models]})
            return
        if method != "POST" or endpoint not in IMAGE_PATHS | TEXT_PATHS:
            raise CanvasRequestError("接口不存在", 404)
        with canvas_request():
            payload, files = read_canvas_payload(handler)
            if endpoint in IMAGE_PATHS:
                handler.send_json(generate_canvas_images(site, endpoint, payload, files))
            else:
                if files:
                    raise CanvasRequestError("文字接口只接受 JSON 请求")
                proxy_canvas_text(handler, site, endpoint, payload)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        return
    except Exception as exc:
        if handler._canvas_response_started:
            return
        from Department.视觉设计部.xiaoha.request_limits import RequestQueueFull

        status = exc.status if isinstance(exc, CanvasRequestError) else 429 if isinstance(exc, RequestQueueFull) else 502
        message = site.format_user_facing_error_message(exc)
        try:
            handler.send_json({"error": {"message": message}}, status=status)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
