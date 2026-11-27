"""Prepare provider input and response payloads for remaining Xiaoha operations."""

from __future__ import annotations

from typing import Any


def _jimeng_sha256_hex(
    value,
    *,
    hashlib,
) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _jimeng_hmac_bytes(
    key,
    message,
    *,
    hashlib,
    hmac,
) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _jimeng_normalize_query(
    params,
    *,
    urllib,
) -> str:
    query_parts: list[str] = []
    for key in sorted(params.keys()):
        value = params[key]
        if isinstance(value, list):
            for item in value:
                query_parts.append(
                    f"{urllib.parse.quote(str(key), safe='-_.~')}="
                    f"{urllib.parse.quote(str(item), safe='-_.~')}"
                )
        else:
            query_parts.append(
                f"{urllib.parse.quote(str(key), safe='-_.~')}="
                f"{urllib.parse.quote(str(value), safe='-_.~')}"
            )
    return "&".join(query_parts).replace("+", "%20")


def build_jimeng_prompt(
    feature,
    custom_prompt,
    aspect_ratio,
    extra_notes,
    *,
    DEFAULT_ASPECT_RATIO,
    build_jimeng_feature_prompt,
) -> str:
    feature_key = str(feature.get("key") or "").strip()
    if feature_key == "hd_batch":
        return build_jimeng_feature_prompt(
            feature,
            custom_prompt,
            DEFAULT_ASPECT_RATIO,
            extra_notes,
            base_instruction="",
        )
    return build_jimeng_feature_prompt(feature, custom_prompt, aspect_ratio, extra_notes)


def extract_jimeng_result_images(
    payload,
    *,
    base64,
    image_bytes_to_data_url,
) -> dict[str, Any]:
    image_urls = [str(item).strip() for item in (payload.get("image_urls") or []) if str(item).strip()]
    if image_urls:
        return {"images": image_urls, "text": ""}
    base64_images = [str(item).strip() for item in (payload.get("binary_data_base64") or []) if str(item).strip()]
    if base64_images:
        return {
            "images": [
                image_bytes_to_data_url(base64.b64decode(item), "image/png")
                for item in base64_images
            ],
            "text": "",
        }
    raise RuntimeError("Agent 已完成，但没有返回图片结果。")


def call_portrait_hd_upscale(
    uploaded_files,
    *,
    prompt,
    DEFAULT_ASPECT_RATIO,
    NANO_BANANA_MODEL,
    call_openrouter_portrait_hd,
) -> dict[str, Any]:
    """批量高清固定使用 Nano Banana 2.1，仅发送当前原图。"""
    if not uploaded_files:
        raise RuntimeError("批量高清失败：请先上传原图。")
    return call_openrouter_portrait_hd(
        model=NANO_BANANA_MODEL,
        prompt=prompt,
        aspect_ratio=DEFAULT_ASPECT_RATIO,
        uploaded_files=[uploaded_files[0]],
        source_only=True,
        preserve_native_resolution=True,
    )


def prepare_omnia_media_request_inputs(
    uploaded_files,
    *,
    OMNIAKEY_INPUT_MIN_BUDGET_BYTES,
    OMNIAKEY_INPUT_TOTAL_BUDGET_BYTES,
    prepare_omnia_media_uploaded_input,
) -> list[dict[str, Any]]:
    files = list(uploaded_files or [])
    if not files:
        return []
    per_image_budget = max(
        OMNIAKEY_INPUT_MIN_BUDGET_BYTES,
        OMNIAKEY_INPUT_TOTAL_BUDGET_BYTES // len(files),
    )
    return [
        prepare_omnia_media_uploaded_input(uploaded_file, max_bytes=per_image_budget)
        for uploaded_file in files
    ]


def build_omnia_task_error_message(payload) -> str:
    error_payload = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error_payload, dict):
        code = str(error_payload.get("code") or "").strip()
        message = str(error_payload.get("message") or error_payload.get("reason") or "").strip()
        if code and message:
            return f"{code}：{message}"
        return message or code or "未提供具体错误信息"
    return str(error_payload or "").strip() or "未提供具体错误信息"
