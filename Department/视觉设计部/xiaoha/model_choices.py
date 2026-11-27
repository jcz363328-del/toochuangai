"""Resolve feature availability, model selection and output limits."""

from __future__ import annotations

from typing import Any


def get_feature_by_key(
    feature_key,
    *,
    FEATURES,
) -> dict[str, Any] | None:
    normalized_key = str(feature_key or "").strip()
    for feature in FEATURES:
        if str(feature.get("key") or "").strip() == normalized_key:
            return feature
    return None


def get_visible_features(*, FEATURES) -> list[dict[str, Any]]:
    return [feature for feature in FEATURES if not bool(feature.get("hidden"))]


def get_infinite_canvas_step_features(
    *,
    INFINITE_CANVAS_STEP_FEATURE_KEYS,
    get_feature_by_key,
) -> list[dict[str, Any]]:
    return [
        feature
        for feature_key in INFINITE_CANVAS_STEP_FEATURE_KEYS
        for feature in [get_feature_by_key(feature_key)]
        if feature is not None
    ]


def get_feature_name_by_key(
    feature_key,
    *,
    FEATURES,
) -> str:
    normalized_key = str(feature_key or "").strip()
    for feature in FEATURES:
        if str(feature.get("key") or "").strip() == normalized_key:
            return str(feature.get("name") or normalized_key)
    return normalized_key


def get_feature_min_output_edge(
    feature_or_key,
    *,
    HD_MIN_OUTPUT_EDGE,
    MIN_OUTPUT_EDGE,
) -> int:
    if isinstance(feature_or_key, dict):
        feature_key = str(feature_or_key.get("key") or "").strip()
    else:
        feature_key = str(feature_or_key or "").strip()
    return HD_MIN_OUTPUT_EDGE if feature_key == "hd_batch" else MIN_OUTPUT_EDGE


def normalize_feature_output_count(
    value,
    default,
    *,
    FEATURE_OUTPUT_COUNT_MAX,
    FEATURE_OUTPUT_COUNT_MIN,
) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = int(default)
    return max(FEATURE_OUTPUT_COUNT_MIN, min(normalized, FEATURE_OUTPUT_COUNT_MAX))


def should_enhance_output_detail(feature_key) -> bool:
    return str(feature_key or "").strip() == "hd_batch"


def is_jimeng_model(
    model_name,
    *,
    JIMENG_HD_MODEL_NAME,
    JIMENG_MODEL_NAME,
) -> bool:
    return str(model_name or "").strip() in {JIMENG_MODEL_NAME, JIMENG_HD_MODEL_NAME}


def is_ark_seedream_model(
    model_name,
    *,
    ARK_SEEDREAM_5_PRO_MODEL,
) -> bool:
    return str(model_name or "").strip() == ARK_SEEDREAM_5_PRO_MODEL


def is_nano_banana_model(
    model_name,
    *,
    NANO_BANANA_MODEL_ALIASES,
) -> bool:
    normalized = str(model_name or "").strip().lower()
    return normalized.startswith(NANO_BANANA_MODEL_ALIASES)


def resolve_nano_banana_model(
    model_name,
    *,
    NANO_BANANA_MODEL,
    is_nano_banana_model,
) -> str:
    """Nano Banana 的任意变体都映射到唯一的 NANO_BANANA_MODEL。"""
    if is_nano_banana_model(model_name):
        return NANO_BANANA_MODEL
    return str(model_name or "").strip()


def resolve_omnia_image_model(
    model_name,
    *,
    NANO_BANANA_MODEL,
    OMNIA_IMAGE_MODELS,
    OMNIA_IMAGE_MODEL_ALIASES,
    is_nano_banana_model,
) -> str:
    """把旧模型名和 OmniaKey 模型名统一收敛到 OmniaKey 的生图模型。"""
    normalized = str(model_name or "").strip()
    if normalized in OMNIA_IMAGE_MODELS:
        return normalized
    if normalized in OMNIA_IMAGE_MODEL_ALIASES:
        return OMNIA_IMAGE_MODEL_ALIASES[normalized]
    if is_nano_banana_model(normalized):
        return NANO_BANANA_MODEL
    return ""


def get_model_display_name(
    model_name,
    *,
    IMAGE_SMART_ANALYSIS_MODEL,
    JIMENG_HD_MODEL_NAME,
    OMNIA_IMAGE_MODEL_LABELS,
    is_ark_seedream_model,
    is_jimeng_model,
) -> str:
    normalized_name = str(model_name or "").strip()
    if is_ark_seedream_model(normalized_name):
        return "即梦 5 Pro（火山方舟）"
    if normalized_name == JIMENG_HD_MODEL_NAME:
        return "即梦智能超清 8K"
    if is_jimeng_model(normalized_name):
        return "即梦 Seedream 4.6"
    if normalized_name == IMAGE_SMART_ANALYSIS_MODEL:
        return "Gemini 2.5 Flash 视觉分析"
    if normalized_name in OMNIA_IMAGE_MODEL_LABELS:
        return OMNIA_IMAGE_MODEL_LABELS[normalized_name]
    return normalized_name


def is_jimeng_concurrent_limit_error(message) -> bool:
    normalized_message = str(message or "").strip().lower()
    if not normalized_message:
        return False
    return (
        "request has reached api concurrent limit" in normalized_message
        or "concurrent limit" in normalized_message
        or "exceededconcurrentquota" in normalized_message
    )


def is_omnia_image_outcome_unknown(
    error,
    *,
    ImageOutcomeUnknown,
) -> bool:
    """Keep accepted or uncertain image work from being submitted a second time."""
    pending = [error]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, ImageOutcomeUnknown):
            return True
        normalized = str(current or "").strip().lower()
        if any(marker in normalized for marker in (
            "未自动重新提交", "provider_submit_uncertain", "查询图片任务失败", "图片任务等待超时",
        )):
            return True
        if isinstance(current, BaseException):
            pending.extend(cause for cause in (current.__cause__, current.__context__) if cause is not None)
    return False
