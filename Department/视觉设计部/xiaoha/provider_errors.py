"""Normalize provider results and user-facing errors."""

from __future__ import annotations

from typing import Any


def extract_response_payload(data) -> dict[str, Any]:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter 响应解析失败：返回内容里没有 choices。")

    message = choices[0].get("message") or {}
    images: list[str] = []
    texts: list[str] = []

    for image in message.get("images") or []:
        image_url = ((image or {}).get("image_url") or {}).get("url")
        if image_url:
            images.append(image_url)

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        texts.append(content.strip())
    elif isinstance(content, list):
        for item in content:
            item_type = item.get("type")
            if item_type in {"text", "output_text"} and item.get("text"):
                texts.append(item["text"].strip())
            if item_type == "image_url":
                image_url = (item.get("image_url") or {}).get("url")
                if image_url:
                    images.append(image_url)

    unique_images = []
    seen = set()
    for image_url in images:
        if image_url not in seen:
            seen.add(image_url)
            unique_images.append(image_url)

    return {"images": unique_images, "text": "\n\n".join(texts).strip(), "raw": data}


def format_openrouter_error_message(
    error_message,
    *,
    re,
) -> str:
    raw_message = str(error_message or "").strip()
    if not raw_message:
        return "OpenRouter 请求失败：服务返回了空错误信息。"
    cleaned_message = re.sub(r"https?://\S+", "", raw_message).strip()
    normalized_message = cleaned_message.lower()
    source_match = re.search(
        r"(第\s*\d+\s*张(?:（[^）\r\n]{1,100}）)?)",
        cleaned_message,
    )
    source_prefix = f"{source_match.group(1)}：" if source_match else ""

    def with_source(message: str) -> str:
        return f"{source_prefix}{message}" if source_prefix else message

    if "downloaded image content cannot exceed 30mb" in normalized_message or "cannot exceed 30mb" in normalized_message:
        return with_source("OpenRouter 输入图片超过 30MB，系统已加入自动压缩处理，请重新提交任务。")
    if "key limit exceeded" in normalized_message or "daily limit" in normalized_message:
        return with_source("OpenRouter 今日额度已用完，请更换可用的 API Key，或等待每日额度重置后再试。")
    if (
        "insufficient credits" in normalized_message
        or "payment required" in normalized_message
        or "http 402" in normalized_message
    ):
        return with_source("OpenRouter 账户余额不足（HTTP 402），请充值或更换可用的 API Key 后重试。")
    if "rate limit" in normalized_message or "http 429" in normalized_message:
        return with_source("OpenRouter 当前请求过于频繁（HTTP 429），系统已自动重试，请稍等一会儿再提交。")
    if "image_safety" in normalized_message or "blocked the request" in normalized_message:
        return with_source("图片或文字要求触发了模型安全审核，本次请求未生成图片。请更换合规图片或调整要求后重试。")
    if "timeout" in normalized_message or "timed out" in normalized_message or "无法连接" in cleaned_message:
        return with_source("OpenRouter 连接超时，系统已自动重试，请稍后再提交。")
    if "unauthorized" in normalized_message or "invalid api key" in normalized_message or "http 401" in normalized_message:
        return with_source("OpenRouter 身份验证失败（HTTP 401），请联系管理员检查 API Key。")
    if "未返回图片" in cleaned_message or "no image" in normalized_message:
        return with_source("OpenRouter 未返回可用图片，请重新提交任务。")
    http_status = re.search(r"\bHTTP\s+(\d{3})\b", cleaned_message, flags=re.IGNORECASE)
    if http_status:
        status_code = int(http_status.group(1))
        if status_code in {408, 425, 500, 502, 503, 504}:
            return with_source(
                f"OpenRouter 上游服务暂时不可用（HTTP {status_code}），系统已自动重试，请稍后再提交。"
            )
        return with_source(f"OpenRouter 请求失败（HTTP {status_code}），详细信息已记录在服务器。")
    return with_source("OpenRouter 请求失败，详细信息已记录在服务器，请稍后重试或联系管理员。")


def format_omnia_error_message(
    error_message,
    *,
    re,
) -> str:
    raw_message = str(error_message or "").strip()
    normalized_message = raw_message.lower()
    if any(marker in normalized_message for marker in ("image_recitation", "copyright", "protected content")):
        task = re.search(r"task[_-][A-Za-z0-9_-]+", raw_message)
        suffix = f"（任务 {task.group(0)}）" if task else ""
        return (
            "OmniaKey 模型认为生成结果可能复现受保护内容，已停止生成，未返回图片。"
            "这可能是误判；如使用自有或已授权素材，请联系服务商复核。本次未自动重试。" + suffix
        )
    if "同步生图" in raw_message and "未自动重新提交" in raw_message:
        return raw_message
    if "图片任务等待超时" in raw_message or "查询图片任务失败" in raw_message:
        return raw_message
    if "provider_submit_uncertain" in normalized_message:
        task = re.search(r"task_[A-Za-z0-9]+", raw_message)
        suffix = f"（任务 {task.group(0)}）" if task else ""
        return ("OmniaKey 上游提交超时，服务商已将任务标记为失败，未返回图片。"
                "可稍后重试，或选择其他模型重新生成。" + suffix)
    if "omniakey_api_key" in normalized_message or "未配置" in raw_message:
        return "OmniaKey 未配置 OMNIAKEY_API_KEY，请联系管理员完成配置。"
    if "http 401" in normalized_message or "unauthorized" in normalized_message or "invalid api key" in normalized_message:
        return "OmniaKey 鉴权失败（HTTP 401），请联系管理员检查 OMNIAKEY_API_KEY。"
    if "http 402" in normalized_message or "insufficient" in normalized_message or "余额" in raw_message:
        return "OmniaKey 账户余额不足（HTTP 402），请充值后重试。"
    if "http 429" in normalized_message or "rate limit" in normalized_message or "限流" in raw_message:
        return "OmniaKey 当前请求过于频繁（HTTP 429），请稍等一会儿再提交。"
    if "system_cpu_overloaded" in normalized_message or "cpu overloaded" in normalized_message:
        return "OmniaKey 上游负载过高（CPU 过载），批量高清已自动降低并发并重试；请稍后重新提交。"
    if "generation service is busy" in normalized_message or "service is busy" in normalized_message:
        return "OmniaKey 上游生成服务繁忙，系统已自动重试；请稍后重新提交。"
    if "http 503" in normalized_message or "no_available_channel" in normalized_message or "no available channel" in normalized_message:
        return "OmniaKey 当前没有可用渠道服务该模型，系统已自动降低并发并重试；请稍后重新提交。"
    if "http 413" in normalized_message or "request body too large" in normalized_message or "1mb" in normalized_message:
        return "OmniaKey 请求体超过 1MB 上限，请降低输入图片尺寸后重试。"
    if any(marker in normalized_message for marker in ("content_filter", "content filter", "safety", "blocked")) or "审核" in raw_message:
        return "OmniaKey 返回内容审核拦截，未提供图片结果；这不一定表示输入违规。请检查图片和提示词，正常内容仍被拒绝时请联系服务商排查。"
    if "timeout" in normalized_message or "timed out" in normalized_message or "超时" in raw_message:
        return "OmniaKey 任务等待超时，请稍后重新提交。"
    cleaned_message = re.sub(r"https?://\S+", "", raw_message).strip()
    if len(cleaned_message) > 600:
        return "OmniaKey 任务未成功，详细信息已记录在服务器，请稍后重试或联系管理员。"
    return cleaned_message or "OmniaKey 任务失败，请稍后重试。"


def format_user_facing_error_message(
    error_message,
    *,
    GLOBAL_NO_DISTORTION_RULES,
    format_omnia_error_message,
    format_openrouter_error_message,
    re,
    redact_background_error_text,
) -> str:
    raw_message = str(error_message or "").strip()
    if not raw_message:
        return "任务失败，请稍后重试。"
    if "未自动重新提交" in raw_message:
        return redact_background_error_text(raw_message)[:600]
    normalized_message = raw_message.lower()
    is_ark_seedream_error = "即梦 5 pro" in normalized_message or "火山方舟" in raw_message
    if is_ark_seedream_error:
        if "ark_api_key" in normalized_message or "api key" in normalized_message and "未配置" in raw_message:
            return "即梦 5 Pro 未配置 ARK_API_KEY，请联系管理员完成配置。"
        if "http 401" in normalized_message or "unauthorized" in normalized_message or "invalid api key" in normalized_message:
            return "即梦 5 Pro 鉴权失败，请联系管理员检查 ARK_API_KEY 和模型开通状态。"
        if "http 429" in normalized_message or "rate limit" in normalized_message or "并发" in raw_message:
            return "即梦 5 Pro 当前请求较多或额度已满，请稍后重试。"
        if "timeout" in normalized_message or "timed out" in normalized_message or "超时" in raw_message:
            return "即梦 5 Pro 连接超时，请稍后重试。"
        if "safety" in normalized_message or "审核" in raw_message or "blocked" in normalized_message:
            return "图片或文字要求触发了即梦 5 Pro 安全审核，请更换合规图片或调整要求后重试。"
        return "即梦 5 Pro 请求失败，详细信息已记录在服务器，请稍后重试或联系管理员。"
    is_jimeng_error = (
        "agent 请求失败" in normalized_message
        or "即梦" in raw_message
        or "火山引擎" in raw_message
    )
    if is_jimeng_error and (
        "错误码 50430" in raw_message
        or "code 50430" in normalized_message
        or "concurrent limit" in normalized_message
    ):
        return (
            "即梦服务当前并发额度已占满（HTTP 429，错误码 50430）。"
            "系统已按账号级并发 1 串行排队并自动退避重试；请不要重复点击提交。"
            "如果等待约 3 分钟后仍失败，请在火山引擎控制台提升智能超清并发额度或确认没有其他程序占用该账号。"
        )
    if is_jimeng_error and (
        "http 401" in normalized_message
        or "错误码 50400" in raw_message
        or "code 50400" in normalized_message
    ):
        return (
            "火山引擎鉴权失败（HTTP 401，错误码 50400）：当前 AK/SK 未通过校验。"
            "请确认 AK 与 SK 来自同一组有效的 AccessKey、未被停用，且该 AccessKey 所属账号已开通“即梦AI-智能超清”；"
            "方舟模型 API Key 不能替代这里的 AK/SK。"
        )
    if "access denied" in normalized_message and (
        is_jimeng_error
    ):
        return (
            "火山引擎鉴权或授权失败：请确认 AK/SK 是同一组有效的 AccessKey，"
            "并确认其所属账号已开通“即梦AI-智能超清”；方舟模型 API Key 不能替代这里的 AK/SK。"
        )
    if "omnia" in normalized_message:
        return format_omnia_error_message(raw_message)
    if "openrouter" in normalized_message or "key limit exceeded" in normalized_message or "daily limit" in normalized_message:
        if "key limit exceeded" in normalized_message or "daily limit" in normalized_message:
            return "OpenRouter 今日额度已用完，请更换可用的 API Key，或等待每日额度重置后再试。"
        return format_openrouter_error_message(raw_message.replace("OpenRouter 请求失败：", "", 1))
    cleaned_message = re.sub(r"https?://\S+", "", raw_message).strip()
    contains_request_payload = bool(
        re.search(r"(?i)[\"'](?:prompt|messages|request_prompt|system_prompt)[\"']\s*:", cleaned_message)
        or "当前执行功能：" in cleaned_message
        or GLOBAL_NO_DISTORTION_RULES in cleaned_message
    )
    if contains_request_payload or len(cleaned_message) > 600:
        return "任务请求未成功，详细信息已记录在服务器，请稍后重试或联系管理员。"
    return cleaned_message
