from __future__ import annotations

import base64
import colorsys
import html
import hashlib
import hmac
import io
import json
import math
import mimetypes
import os
import re
import shutil
import sys
import time
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import date, datetime, timedelta, timezone
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageStat


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from Department.视觉设计部.xiaoha.generation_settings import apply_image_settings, with_job_image_settings, current_resolution

import Department.视觉设计部.xiaoha.page as _xiaoha_page
import Department.视觉设计部.xiaoha.history as _xiaoha_history
import Department.视觉设计部.xiaoha.features.hero_style_reverse as _hero_style_reverse
import Department.视觉设计部.xiaoha.features.image_smart_analysis as _image_smart_analysis
import Department.视觉设计部.xiaoha.features.background_cutout as _background_cutout
import Department.视觉设计部.xiaoha.workbench_pages as _workbench_pages
import Department.视觉设计部.xiaoha.features.main_image_a_plus_jobs as _main_image_a_plus_jobs
import Department.视觉设计部.xiaoha.feature_workbench as _feature_workbench
import Department.视觉设计部.xiaoha.gallery_views as _gallery_views
import Department.视觉设计部.xiaoha.batch_jobs as _batch_jobs
import Department.视觉设计部.xiaoha.usage_views as _usage_views
import Department.视觉设计部.xiaoha.features.main_image_a_plus_quality as _main_image_a_plus_quality
import Department.视觉设计部.xiaoha.feature_dispatch as _feature_dispatch
import Department.视觉设计部.xiaoha.provider_clients as _provider_clients
import Department.视觉设计部.xiaoha.features.main_image_a_plus_sources as _main_image_a_plus_sources
import Department.视觉设计部.xiaoha.features.main_image_a_plus_editor as _main_image_a_plus_editor
import Department.视觉设计部.xiaoha.job_status_views as _job_status_views
import Department.视觉设计部.xiaoha.workbench_assets as _workbench_assets
import Department.视觉设计部.xiaoha.features.main_image_a_plus_prompts as _main_image_a_plus_prompts
import Department.视觉设计部.xiaoha.usage_data as _usage_data
import Department.视觉设计部.xiaoha.gallery_data as _gallery_data
import Department.视觉设计部.xiaoha.features.layout_skills as _layout_skills
import Department.视觉设计部.xiaoha.features.main_image_a_plus_elements as _main_image_a_plus_elements
import Department.视觉设计部.xiaoha.result_storage as _result_storage
import Department.视觉设计部.xiaoha.feature_prompts as _feature_prompts
import Department.视觉设计部.xiaoha.features.first_screen_selling_points as _first_screen_selling_points
import Department.视觉设计部.xiaoha.image_geometry as _image_geometry
import Department.视觉设计部.xiaoha.upload_views as _upload_views
import Department.视觉设计部.xiaoha.jimeng_client as _jimeng_client
import Department.视觉设计部.xiaoha.image_inputs as _image_inputs
import Department.视觉设计部.xiaoha.provider_errors as _provider_errors
import Department.视觉设计部.xiaoha.result_views as _result_views
import Department.视觉设计部.xiaoha.features.main_image_a_plus_image_tools as _main_image_a_plus_image_tools
import Department.视觉设计部.xiaoha.feature_helpers as _feature_helpers
import Department.视觉设计部.xiaoha.workbench_state as _workbench_state
import Department.视觉设计部.xiaoha.usage_queries as _usage_queries
import Department.视觉设计部.xiaoha.jimeng_uploads as _jimeng_uploads
import Department.视觉设计部.xiaoha.job_progress_views as _job_progress_views
import Department.视觉设计部.xiaoha.portrait_results as _portrait_results
import Department.视觉设计部.xiaoha.history_repository as _history_repository
import Department.视觉设计部.xiaoha.features.a_plus_layout_rules as _a_plus_layout_rules
import Department.视觉设计部.xiaoha.upload_actions as _upload_actions
import Department.视觉设计部.xiaoha.model_choices as _model_choices
import Department.视觉设计部.xiaoha.history_paths as _history_paths
import Department.视觉设计部.xiaoha.download_views as _download_views
import Department.视觉设计部.xiaoha.output_processing as _output_processing
import Department.视觉设计部.xiaoha.upload_state as _upload_state
import Department.视觉设计部.xiaoha.image_primitives as _image_primitives
import Department.视觉设计部.xiaoha.job_presentation as _job_presentation
import Department.视觉设计部.xiaoha.features.layout_selection as _layout_selection
import Department.视觉设计部.xiaoha.login_state as _login_state
import Department.视觉设计部.xiaoha.provider_inputs as _provider_inputs
import Department.视觉设计部.xiaoha.runtime_config as _runtime_config
import Department.视觉设计部.xiaoha.runtime_paths as _runtime_paths
from Department.视觉设计部.xiaoha.features import image_matting as _image_matting
from Department.视觉设计部.xiaoha.static_request_handler import create_static_request_handler
from Department.视觉设计部.xiaoha.task_runtime import JIMENG_HD_GLOBAL_QUEUE_KEY, TaskRuntime
from Department.视觉设计部.xiaoha.features import outpaint as _outpaint
from Department.视觉设计部.xiaoha.features.background_texture import BACKGROUND_TEXTURE_PRESETS, build_background_texture_instruction
from Department.视觉设计部.xiaoha.features.prompt_builders import (
    build_ai_lash_tray_cutout_prompt,
    build_hero_style_reverse_analysis_prompt,
)
import Department.视觉设计部.xiaoha.history_storage as _xiaoha_history_storage
import Department.视觉设计部.xiaoha.history_downloads as _xiaoha_history_downloads
from secret_settings import image_site_config_namespace, relocate_storage_path, sql_server_config
import prepress_check_service
from Department.视觉设计部.xiaoha.request_limits import admitted_job, get_request_limiter, limited_request, request_wait_callback
from Department.视觉设计部.xiaoha.omnia_key_pool import current_omnia_credential
from Department.视觉设计部.xiaoha.omnia_service import (
    managed_omnia_call, record_omnia_task, record_omnia_provider_status,
    current_omnia_call_metadata, record_omnia_model,
)
from Department.视觉设计部.xiaoha.image_downloads import build_image_attachment_header, is_managed_static_image_url, resolve_local_static_image_source
from Department.视觉设计部.xiaoha.multi_reference_composer import MULTI_REFERENCE_COMPOSER_FEATURE_KEY
from Department.视觉设计部.xiaoha.a_plus_reference_lab import (
    A_PLUS_REFERENCE_LAB_FEATURE_KEY,
    A_PLUS_REFERENCE_LAB_MAX_PRODUCT_IMAGES,
    build_a_plus_reference_lab_instruction,
    get_a_plus_reference_style_description,
    get_a_plus_reference_style_label,
    get_a_plus_reference_style_options,
    prepare_a_plus_reference_style_input,
    resolve_a_plus_reference_style,
)
from Department.视觉设计部.xiaoha.amazon_a_plus_psd import (
    build_commercial_a_plus_background,
    build_layered_a_plus,
    fit_green_screen_to_canvas,
    select_closest_aspect_ratio,
)

ARK_IMAGES_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
ARK_SEEDREAM_5_PRO_MODEL = "doubao-seedream-5-0-pro-260628"
ARK_SEEDREAM_5_PRO_SIZE = "2K"
_OMNIAKEY_API_BASE_RAW = str(os.getenv("OMNIAKEY_BASE_URL") or "https://api.omniakey.com").strip().rstrip("/")
OMNIAKEY_API_BASE = (
    _OMNIAKEY_API_BASE_RAW[:-3]
    if _OMNIAKEY_API_BASE_RAW.lower().endswith("/v1")
    else _OMNIAKEY_API_BASE_RAW
)
OMNIAKEY_MEDIA_TASKS_URL = f"{OMNIAKEY_API_BASE}/v1/media/tasks"
OMNIAKEY_CHAT_COMPLETIONS_URL = f"{OMNIAKEY_API_BASE}/v1/chat/completions"
NANO_BANANA_MODEL = "gemini-nano-banana-2.1"
DEFAULT_MODEL = NANO_BANANA_MODEL
# 历史遗留的 Nano Banana 变体统一收敛到 NANO_BANANA_MODEL，使用 OmniaKey 异步任务 API。
NANO_BANANA_MODEL_ALIASES = (
    "gemini-nano-banana",
    "google/gemini-nano-banana",
    "google/gemini-2.5-flash-image",
    "google/gemini-3-pro-image-preview",
)
# 除 Seedream 外，所有可选生图模型都由 OmniaKey 提供。
OMNIA_IMAGE_MODEL_LABELS = {
    NANO_BANANA_MODEL: "Nano Banana 2.1",
    "gpt-image-2.6-sunburst": "GPT Image 2.6 Sunburst",
    "gpt-image-2.6-flare": "GPT Image 2.6 Flare",
    "gpt-image-2.5-flare": "GPT Image 2.5 Flare",
    "gpt-image-2": "GPT Image 2",
    "grok-imagine-image-quality": "Grok Imagine Image Quality",
}
OMNIA_IMAGE_MODELS = tuple(OMNIA_IMAGE_MODEL_LABELS)
OMNIA_IMAGE_MODEL_ALIASES = {
    "openai/gpt-5.4-image-2": "gpt-image-2.6-flare",
    "openai/gpt-5-image-mini": "gpt-image-2.5-flare",
    "openai/gpt-5-image": "gpt-image-2",
    "x-ai/grok-imagine-image-quality": "grok-imagine-image-quality",
    "recraft/recraft-v4.1-utility-pro": "gpt-image-2.6-flare",
}
DEFAULT_ASPECT_RATIO = "自动"
REFERENCE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MIN_OUTPUT_EDGE = 2000
HD_MIN_OUTPUT_EDGE = 4096
HD_MODEL_REFERENCE_FILE = APP_DIR / "__pycache__" / "model_reference" / "模特参考图.png"
OUTPUTS_HD_REFERENCE_DIR = APP_DIR / "outputs" / "reference"
OUTPUTS_HD_DEFAULT_REFERENCE_FILE = OUTPUTS_HD_REFERENCE_DIR / "参考1.png"
SKIN_TEXTURE_REFERENCE_DIR = Path(relocate_storage_path(r"D:\tuchuangai\肌肤质感参考"))
PORTRAIT_HD_DEFAULT_IMAGE_SIZE = "2K"
PORTRAIT_HD_SKIN_LOCK_RULES = (
    "肤色与肤质锁定是本次高清处理的最高优先级。"
    "必须严格保持第1张原图皮肤的明暗、冷暖、色相、白平衡、通透度、红润度、肤色不均和局部色差完全一致，禁止提亮、压暗、增白、变黄、变红或统一肤色。"
    "必须严格保持第1张原图已有的毛孔、皮肤颗粒、油脂光泽、干燥感、斑点、雀斑、痣、痘印、细纹、皱纹和眼周纹理，禁止磨皮、美颜、祛斑、去痣、去痘印、去细纹或重塑皮肤。"
    "如果存在第2张肤质参考图，只能参考其清晰度、分辨率和细节解析水平，严禁迁移第2张图的肤色、肤质、毛孔形态、皮肤状态、光泽、颗粒、妆容或任何人物特征。"
    "任何基础提示词、参考图或用户补充要求与此规则冲突时，都必须优先保持第1张原图的肤色和肤质不变。"
)
PORTRAIT_HD_COLOR_LOCK_RULES = (
    "整张画面的色温与色调锁定也是本次高清处理的最高优先级。"
    "必须严格保持第1张原图的整体与局部色温、冷暖关系、综合色调、色相、白平衡、色偏、饱和度、自然度、曝光、亮度、对比度、高光、阴影、黑白场和伽马完全一致。"
    "人物皮肤、头发、眼睛、服装、商品、背景、灯光及画面内所有区域的原有颜色关系都不得改变。"
    "禁止自动白平衡、自动校色、调色、重新定色、改变冷暖、消除或增加色偏、套用滤镜或 LUT、电影感调色、增加通透感、提亮暗部、压低高光、增强饱和度或改变对比度。"
    "如果存在第2张高清参考图，严禁迁移其色温、色调、白平衡、曝光、对比度、光线颜色或任何色彩风格。"
    "只允许提升原图已有细节的清晰度；任何基础提示词、参考图或用户补充要求与此规则冲突时，都必须优先保持第1张原图的色温和色调不变。"
)
GLOBAL_NO_DISTORTION_RULES = (
    "GLOBAL GEOMETRY LOCK (highest priority): Preserve the natural aspect ratio and proportions of "
    "every visible element, including people, faces, body parts, products, packages, logos, words, "
    "and graphics. Only uniform scaling up or down is allowed. Never squeeze, widen, stretch, warp, "
    "or scale horizontal and vertical axes independently. Fit a different canvas by recomposition "
    "and background extension, never by forcing the artwork to the target width or height."
)
PROXY_URL = "socks5h://127.0.0.1:10808"
REQUEST_PROXIES = {
    "http": PROXY_URL,
    "https": PROXY_URL,
}
HISTORY_DIR = APP_DIR / "history"
HISTORY_IMAGES_DIR = HISTORY_DIR / "images"
HISTORY_FILE = HISTORY_DIR / "records.json"
OPENROUTER_ERROR_LOG_FILE = PROJECT_ROOT / "logs" / "openrouter_errors.jsonl"
OMNIAKEY_TASK_RECEIPTS_FILE = PROJECT_ROOT / "logs" / "omnia_image_tasks.jsonl"
MAX_HISTORY_RECORDS = 120
HISTORY_PAGE_SIZE = 20
DB_HISTORY_TABLE = "AI_TuPian"
XIAOHA_DASHBOARD_KEY = "__usage_dashboard__"
XIAOHA_BALANCE_KEY = "__balance__"
XIAOHA_DEFAULT_FEATURE_KEY = "hd_batch"
XIAOHA_DASHBOARD_HISTORY_DAYS = 7
XIAOHA_DASHBOARD_CACHE_SECONDS = 60
XIAOHA_DASHBOARD_MAX_FEATURE_LINES = 6
JIMENG_API_HOST = "visual.volcengineapi.com"
JIMENG_API_ENDPOINT = f"https://{JIMENG_API_HOST}/"
JIMENG_API_REGION = "cn-north-1"
JIMENG_API_SERVICE = "cv"
JIMENG_API_VERSION = "2022-08-31"
JIMENG_SUBMIT_ACTION = "CVSync2AsyncSubmitTask"
JIMENG_GET_RESULT_ACTION = "CVSync2AsyncGetResult"
JIMENG_REQ_KEY = "jimeng_seedream46_cvtob"
JIMENG_MODEL_NAME = "jimeng_seedream46_cvtob"
JIMENG_HD_UPSCALE_REQ_KEY = "jimeng_i2i_seed3_tilesr_cvtob"
JIMENG_HD_MODEL_NAME = JIMENG_HD_UPSCALE_REQ_KEY
JIMENG_HD_FEATURE_KEY = "jimeng_hd_upscale"
JIMENG_RESULT_POLL_INTERVAL_SECONDS = 2
JIMENG_RESULT_TIMEOUT_SECONDS = 180
JIMENG_UPLOAD_SUBDIR = "jimeng_uploads"
JIMENG_UPLOAD_ROUTE_PREFIX = f"/{JIMENG_UPLOAD_SUBDIR}"
HISTORY_STATIC_SUBDIR = "history_images"
HISTORY_STATIC_ROUTE_PREFIX = f"/{HISTORY_STATIC_SUBDIR}"
JIMENG_MAX_INPUT_IMAGES = 14
JIMENG_IMAGE_EDIT_SCALE = 50
JIMENG_HD_IMAGE_EDIT_SCALE = 1
JIMENG_PROMPT_MAX_CHARS = 780
JIMENG_HD_OUTPUT_AREA = 2048 * 2048
JIMENG_HD_API_MAX_BYTES = 4_700_000
JIMENG_HD_API_MAX_EDGE = 4096
JIMENG_I2I_MAX_BYTES = 4_700_000
JIMENG_I2I_MAX_EDGE = 4096
# OpenRouter 的 30 MB 限制按请求中的 data URL 体积计算；base64 会比原图
# 增加约 1/3，故原始图片必须控制在约 20 MB 内，不能按 29 MiB 判断。
OPENROUTER_MAX_INPUT_IMAGE_BYTES = 21 * 1024 * 1024
OPENROUTER_SAFE_INPUT_TARGET_BYTES = 20 * 1024 * 1024
# 部分上游（Google AI Studio）只接受 20000000 字节以内的请求体，而多张图会一起塞进
# 同一个 JSON。这里按“原始图片总预算”分摊，给 base64 膨胀（约 4/3）和提示词留余量。
OPENROUTER_REQUEST_IMAGE_BUDGET_BYTES = 13 * 1024 * 1024
OPENROUTER_INPUT_MIN_BUDGET_BYTES = 3 * 1024 * 1024
OPENROUTER_MAX_INPUT_IMAGE_EDGE = 4096
OPENROUTER_IMAGES_CONNECT_TIMEOUT_SECONDS = 30
OPENROUTER_IMAGES_READ_TIMEOUT_SECONDS = 360
OPENROUTER_IMAGES_MAX_ATTEMPTS = 2
OPENROUTER_IMAGES_RETRY_DELAYS = (4,)
OPENROUTER_IMAGES_TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
# OmniaKey 媒体任务接口要求整个请求（含 Base64）不超过 1 MiB，原始图片需要先压到预算内。
OMNIAKEY_CONNECT_TIMEOUT_SECONDS = 30
OMNIAKEY_READ_TIMEOUT_SECONDS = 120
OMNIAKEY_SYNC_IMAGE_TIMEOUT_SECONDS = 300
OMNIAKEY_TASK_TIMEOUT_SECONDS = 600
OMNIAKEY_TASK_POLL_INTERVAL_SECONDS = 3
OMNIAKEY_MEDIA_MAX_ATTEMPTS = 2
OMNIAKEY_MEDIA_RETRY_DELAYS = (4,)
OMNIAKEY_MEDIA_TRANSIENT_STATUS_CODES = {408, 425, 429, *range(500, 600)}
OMNIAKEY_INPUT_TOTAL_BUDGET_BYTES = 620_000
OMNIAKEY_INPUT_MIN_BUDGET_BYTES = 48_000
OMNIAKEY_MAX_INPUT_IMAGE_EDGE = 4096
REMOVE_EYELASHES_IMAGE_RESOLUTION = "2K"
REMOVE_EYELASHES_MAX_API_CONCURRENCY = 5
# 批量高清与即梦超清共用专用接口，按服务商单并发串行处理。
HD_BATCH_MAX_API_CONCURRENCY = 5
HD_BATCH_TRANSIENT_MAX_ATTEMPTS = 3
HD_BATCH_TRANSIENT_RETRY_DELAYS = (8, 20)
REMOVE_EYELASHES_REMOVE_ALL_PROMPT = (
    "You are performing a local image edit only. The existing image is locked. "
    "Every pixel outside the eyelashes is read-only and must remain pixel-identical. "
    "Only remove all eyelashes, including both natural eyelashes and false eyelashes. "
    "Do not modify the eyelids, eyes, irises, pupils, eyebrows, eye shape, or any surrounding skin. "
    "Do not redraw, enhance, beautify, retouch, resize, reposition, crop, rotate, or reinterpret any existing content. "
    "Maintain exactly the same person, facial identity, face shape, facial features, eye position, skin texture, skin tone, makeup, hairstyle, clothing, accessories, pose, expression, lighting, shadows, colors, sharpness, composition, background, and image resolution. "
    "Do not add, remove, or modify any detail other than the eyelashes. "
    "The final result must look like the exact same photograph with only the eyelashes removed. "
    "Output exactly one realistic image."
)
REMOVE_EYELASHES_PRESERVE_BASIC_PROMPT = (
    "You are performing a tightly localized eyelash edit only. The existing image is locked. "
    "Remove false eyelashes, extensions, excessive length, excessive curl, and unnatural density, but preserve a subtle layer of short, fine, natural base eyelashes growing from the original upper and lower lash lines. "
    "The eyes must not look completely lashless or unnaturally bare. Keep the retained natural lashes sparse, soft, individually defined, and consistent with the person's real hair color. "
    "Do not create decorative, dramatic, thick, long, clustered, or obviously artificial lashes. "
    "Every pixel outside the eyelashes is read-only. Do not modify the eyelids, lash lines, eyes, irises, pupils, eyebrows, eye shape, makeup, or surrounding skin. "
    "Do not redraw, beautify, retouch, resize, reposition, crop, rotate, or reinterpret any other content. "
    "Maintain exactly the same person, facial identity, face shape, skin texture, skin tone, hairstyle, clothing, accessories, pose, expression, lighting, shadows, colors, sharpness, composition, background, and image resolution. "
    "Output exactly one realistic image with only the excessive or artificial eyelashes removed and the basic natural eyelashes preserved."
)
ARK_IMAGES_CONNECT_TIMEOUT_SECONDS = 30
ARK_IMAGES_READ_TIMEOUT_SECONDS = 360
ARK_IMAGES_MAX_ATTEMPTS = 2
ARK_IMAGES_RETRY_DELAYS = (4,)
ARK_IMAGES_TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
ARK_MAX_INPUT_IMAGE_BYTES = 29 * 1024 * 1024
ARK_MAX_INPUT_IMAGE_EDGE = 6000
ARK_MAX_INPUT_IMAGE_PIXELS = 36_000_000
JIMENG_HD_API_RESOLUTION = "8k"
JIMENG_HD_API_SCALE = 50
DB_IMAGE_DIR = Path(relocate_storage_path(r"D:\tuchuangai\视觉图片"))
CUTOUT_OUTPUT_DIR = Path(relocate_storage_path(r"D:\tuchuangai\视觉图片"))
DB_HISTORY_LIMIT = MAX_HISTORY_RECORDS
DB_HISTORY_THUMB_DIR_NAME = "_thumbs"
DB_HISTORY_THUMB_MAX_EDGE = 640
DB_HISTORY_THUMB_TARGET_BYTES = 140 * 1024
DB_HISTORY_PATH_MAX_LENGTH = 50
GALLERY_PREVIEW_MAX_EDGE = 640
GALLERY_PREVIEW_TARGET_BYTES = 80 * 1024
UPLOAD_CACHE_DIR = Path(relocate_storage_path(r"D:\tuchuangai\图片上传缓存"))
AUTH_QUERY_USER_KEY = "auth_user"
AUTH_QUERY_TOKEN_KEY = "auth_token"
FEATURE_QUERY_KEY = "feature"
MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY = "a_plus_manual_point"
MAIN_IMAGE_A_PLUS_TEXT_POINT_QUERY_KEY = "a_plus_text_point"
UPLOAD_DELETE_QUERY_KEY = "delete_upload"
UPLOAD_REPLACE_WIDGET_QUERY_KEY = "replace_upload_widget"
UPLOAD_REPLACE_INDEX_QUERY_KEY = "replace_upload_index"
UPLOAD_REORDER_QUERY_KEY = "reorder_upload"
OUTPAINT_DRAG_QUERY_KEY = "outpaint_drag"
AUTH_TOKEN_SALT = "lashforge-auth-v1"
DB_CONFIG = sql_server_config()
DEFAULT_SERVER_ADDRESS = "0.0.0.0"
DEFAULT_SERVER_PORT = 8501
DEFAULT_JIMENG_STATIC_PORT = 8502
DEFAULT_PUBLIC_APP_URL = "http://www.toochuangai.com:8501/lashforge"
INFINITE_CANVAS_STATIC_ROUTE_PREFIX = "/infinite-canvas"
INFINITE_CANVAS_MODEL_HD_MAX_REQUEST_BYTES = 80 * 1024 * 1024
INFINITE_CANVAS_MODEL_HD_METHOD_NANO = "nano-banana-2"
INFINITE_CANVAS_MODEL_HD_METHOD_SEEDREAM = "seedream-5-pro"
INFINITE_CANVAS_MODEL_HD_METHODS = {
    INFINITE_CANVAS_MODEL_HD_METHOD_NANO,
    INFINITE_CANVAS_MODEL_HD_METHOD_SEEDREAM,
}
INFINITE_CANVAS_IMAGE_FEATURE_MAX_REQUEST_BYTES = 80 * 1024 * 1024
from Department.视觉设计部.xiaoha.canvas_a_plus import FEATURE_KEYS as CANVAS_A_PLUS_FEATURE_KEYS

INFINITE_CANVAS_IMAGE_FEATURE_KEYS = {
    *CANVAS_A_PLUS_FEATURE_KEYS,
    "product_retouch",
    "product_retouch_local",
    "background_cutout",
    JIMENG_HD_FEATURE_KEY,
    "remove_eyelashes",
    "pose_change",
    "scene_change",
    "outpaint",
    "single_to_double",
    "skin_tone",
    "pupil_color_change",
    "eye_shape_change",
    "three_view",
    "ai_qa_image",
}
INFINITE_CANVAS_IMAGE_FEATURE_REFERENCE_KEYS = {
    "product_retouch",
    "pose_change",
    "scene_change",
    "skin_tone",
    "pupil_color_change",
    "eye_shape_change",
    "three_view",
}
INFINITE_CANVAS_IMAGE_FEATURE_SINGLE_INPUT_KEYS = {
    "product_retouch_local",
    "background_cutout",
    JIMENG_HD_FEATURE_KEY,
    "remove_eyelashes",
    "outpaint",
    "single_to_double",
}
INFINITE_CANVAS_USAGE_ACTION_LABELS = {
    "image_generation": "图片生成",
    "image_edit": "图片编辑",
    "image_generation_retry": "图片生成重试",
    "image_edit_retry": "图片编辑重试",
}
INFINITE_CANVAS_BUILD_DIR = Path(
    os.getenv(
        "INFINITE_CANVAS_BUILD_DIR",
        r"D:\toochuangai\_non_code_files\infinite-canvas\build",
    )
)
DEFAULT_LOGIN_ACCOUNTS = {}
MODEL_OPTIONS = [
    JIMENG_MODEL_NAME,
    ARK_SEEDREAM_5_PRO_MODEL,
    *OMNIA_IMAGE_MODELS,
]
OUTPAINT_MODEL_OPTIONS = [
    NANO_BANANA_MODEL,
    ARK_SEEDREAM_5_PRO_MODEL,
]
INFINITE_CANVAS_IMAGE_MODELS = tuple(
    model for model in MODEL_OPTIONS if model != JIMENG_MODEL_NAME
)
OMNIAKEY_VISION_TEXT_MODEL = "claude-haiku-4-5"
OMNIAKEY_VISION_TEXT_FALLBACK_MODELS = ("gemini-3.7-flash",)
INFINITE_CANVAS_TEXT_MODELS = (OMNIAKEY_VISION_TEXT_MODEL,)
GEMINI_IMAGE_ASPECT_RATIOS = {
    "1:1",
    "1:4",
    "1:8",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:1",
    "4:5",
    "5:4",
    "8:1",
    "9:16",
    "16:9",
    "21:9",
}
GEMINI_IMAGE_SIZES = {"1K", "2K", "4K"}
BATCH_MULTI_IMAGE_FEATURE_KEYS = {
    "hd_batch",
    JIMENG_HD_FEATURE_KEY,
    "remove_eyelashes",
    "outpaint",
    "single_to_double",
}
BATCH_MULTI_IMAGE_MAX_FILES = 20
INFINITE_CANVAS_STEP_FEATURE_KEYS = (
    "hd_batch",
    JIMENG_HD_FEATURE_KEY,
    "remove_eyelashes",
    "outpaint",
    "single_to_double",
)
INFINITE_CANVAS_MAX_INPUT_IMAGES = 6
INFINITE_CANVAS_MAX_STEPS = 4
OUTPAINT_FALLBACK_MAX_EXTENSION_PX = 300
OUTPAINT_DEFAULT_EXTENSION_PX = 100
OUTPAINT_MAX_CANVAS_MULTIPLIER = 3
OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX = 30_000
OUTPAINT_RESULTS_PER_SOURCE = 3
FEATURE_OUTPUT_COUNT_MIN = 1
FEATURE_OUTPUT_COUNT_MAX = 4
OUTPAINT_GUIDE_MAX_EDGE = 2048
OUTPAINT_DRAG_STEP_PX = 1
OUTPAINT_TRANSITION_CLEAR_RATIO = 0.06
OUTPAINT_TRANSITION_FEATHER_RATIO = 0.12
OUTPAINT_SCAFFOLD_BLUR_RATIO = 0.025
OUTPAINT_SEAM_STRENGTH_THRESHOLD = 2.2
OUTPAINT_SEAM_RATIO_THRESHOLD = 2.2
OUTPAINT_MULTISCALE_SEAM_STRENGTH_THRESHOLD = 8.0
OUTPAINT_MULTISCALE_SEAM_RATIO_THRESHOLD = 1.65
MAX_BATCH_API_CONCURRENCY = 5
DEFAULT_BATCH_API_CONCURRENCY = 5
JIMENG_MAX_API_CONCURRENCY = 1
JIMENG_CONCURRENT_LIMIT_RETRY_COUNT = 6
JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS = (5, 10, 20, 30, 45, 60)
JIMENG_RESULT_RETRY_DELAY_SECONDS = 5
AMAZON_A_PLUS_MAX_EDGE = 10_000
AMAZON_A_PLUS_MAX_PIXELS = 40_000_000
AMAZON_A_PLUS_NATIVE_IMAGE_SIZE = "2K"
AMAZON_A_PLUS_FEATURE_KEY = "amazon_a_plus"
AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY = "amazon_to_walmart_a_plus"
AMAZON_TO_WALMART_PAGE_COUNT = 4
AMAZON_TO_WALMART_PAGE_SIZE = (1920, 1080)
MAIN_IMAGE_A_PLUS_FEATURE_KEY = "main_image_a_plus"
A_PLUS_STYLE_MODEL_REPLACE_FEATURE_KEY = "a_plus_style_model_replace"
A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY = "a_plus_first_screen_selling_points"
A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY = "a_plus_hero_style_reverse"
MAIN_IMAGE_A_PLUS_FEATURE_KEYS = {
    MAIN_IMAGE_A_PLUS_FEATURE_KEY,
    A_PLUS_REFERENCE_LAB_FEATURE_KEY,
}
A_PLUS_IMAGES_API_FEATURE_KEYS = {
    AMAZON_A_PLUS_FEATURE_KEY,
    AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY,
    A_PLUS_STYLE_MODEL_REPLACE_FEATURE_KEY,
    A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY,
    *MAIN_IMAGE_A_PLUS_FEATURE_KEYS,
}
MAIN_IMAGE_A_PLUS_MAX_FILES = 10
MAIN_IMAGE_A_PLUS_SECTION_COUNT = 4
MAIN_IMAGE_A_PLUS_DESKTOP_SCREEN_HEIGHT = 600
MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT = 450
MAIN_IMAGE_A_PLUS_MIN_MOBILE_SCREENS = 4
MAIN_IMAGE_A_PLUS_MAX_MOBILE_SCREENS = 10
# Standard output canvases shown to users.  Desktop and mobile sizes are kept
# separate so the selected device width is never inferred from the other one.
MAIN_IMAGE_A_PLUS_SIZE_OPTIONS = tuple(
    [("desktop", (1464, height)) for height in range(600, 4201, 600)]
    + [("mobile", (600, height)) for height in range(450, 3151, 450)]
)
A_PLUS_SKILL_ROOT = Path(os.getenv("A_PLUS_SKILL_ROOT", r"D:\tuchuangai\A+skills"))
A_PLUS_SHOP_STYLE_SKILL_CATALOG = APP_DIR / "a_plus_shop_style_skills.json"
A_PLUS_SKILL_DB_TYPE = "A+生成"
A_PLUS_SKILL_MAX_CASES = 8
A_PLUS_SKILL_SCHEMA_VERSION = 1
MAIN_IMAGE_A_PLUS_CROP_PRESETS: dict[str, dict[str, Any]] = {
    "mobile": {
        "label": "手机端裁切",
        "segment_height": 450,
        "segment_count": MAIN_IMAGE_A_PLUS_SECTION_COUNT,
        "suffix": "mobile",
    },
    "desktop": {
        "label": "电脑端裁切",
        "segment_height": 600,
        "segment_count": MAIN_IMAGE_A_PLUS_SECTION_COUNT,
        "suffix": "desktop",
    },
}
MAIN_IMAGE_A_PLUS_MAX_SECTION_CONCURRENCY = 4
MAIN_IMAGE_A_PLUS_REFERENCE_MAX_EDGE = 2048
MAIN_IMAGE_A_PLUS_REFERENCE_TARGET_BYTES = 3 * 1024 * 1024
MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL = OMNIAKEY_VISION_TEXT_MODEL
MAIN_IMAGE_A_PLUS_QUALITY_REVIEW_MODEL = OMNIAKEY_VISION_TEXT_MODEL
MAIN_IMAGE_A_PLUS_MAX_QUALITY_ATTEMPTS = 2
MAIN_IMAGE_A_PLUS_MAX_FREE_QUALITY_ATTEMPTS = 4
MAIN_IMAGE_A_PLUS_SOURCE_INTEGRITY_MODEL = OMNIAKEY_VISION_TEXT_MODEL
MAIN_IMAGE_A_PLUS_SOURCE_REPAIR_MIN_CONFIDENCE = 0.78
MAIN_IMAGE_A_PLUS_SOURCE_REPAIR_EDGE_RATIO = 0.12
MAIN_IMAGE_A_PLUS_MAX_SOURCE_REPAIRS = 3
MAIN_IMAGE_A_PLUS_MOBILE_REFERENCE_ROOT = APP_DIR / "a_plus_mobile_reference_pairs"
MAIN_IMAGE_A_PLUS_MOBILE_REFERENCE_PAIRS = (
    ("23-84F-desktop.jpg", "23-84F-mobile.jpg"),
    ("22-56G-desktop.jpg", "22-56G-mobile.jpg"),
    ("36-71G-desktop.jpg", "36-71G-mobile.jpg"),
)
IMAGE_SMART_ANALYSIS_FEATURE_KEY = "image_smart_analysis"
IMAGE_SMART_ANALYSIS_MODEL = OMNIAKEY_VISION_TEXT_MODEL
PUBLIC_FIGURE_DETECTION_MODELS = (IMAGE_SMART_ANALYSIS_MODEL,)
# 无限画布在生成前调用本服务做公众人物风险检测，走服务器代理以避开浏览器直连的地区限制。
PUBLIC_FIGURE_DETECTION_PROMPT = (
    "检查所有参考图片中是否出现真实存在的知名公众人物，例如明星、网红、政治人物、企业家。\n"
    "普通真人、模特、普通顾客或无法确认身份的写实人像都不算公众人物，必须返回 detected=false。\n"
    "能认出具体身份时把姓名放进 names；强烈怀疑是公众人物但说不准名字时返回 detected=true、names 留空。\n"
    '只输出一行 JSON，不要输出 Markdown：{"detected":true|false,"names":[]}。'
)
BACKGROUND_TEXTURE_FEATURE_KEY = "background_texture"
MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS = 20
MAIN_IMAGE_A_PLUS_MODE_FREE = "free_create"
MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN = "hero_design"
MAIN_IMAGE_A_PLUS_MODE_TEMPLATE = "template_replace"
MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST = "single_test"
MAIN_IMAGE_A_PLUS_MODE_ELEMENT = "element_replace"
MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT = "mobile_adapt"
MAIN_IMAGE_A_PLUS_MODE_TEXT_EDIT = "text_edit"
MAIN_IMAGE_A_PLUS_TEXT_FONT_OPTIONS = (
    "保持原字体风格",
    "思源黑体 / Noto Sans CJK",
    "思源宋体 / Noto Serif CJK",
    "Montserrat",
    "Arial / Helvetica",
    "Times New Roman",
    "Didot / Bodoni 高级衬线",
    "圆润无衬线",
    "粗体展示字",
    "手写签名字体",
    "自定义字体",
)
MAIN_IMAGE_A_PLUS_MODE_LABELS = {
    MAIN_IMAGE_A_PLUS_MODE_FREE: "自由创作",
    MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN: "首屏设计感",
    MAIN_IMAGE_A_PLUS_MODE_TEMPLATE: "套版替换",
    MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST: "一张测试",
    MAIN_IMAGE_A_PLUS_MODE_ELEMENT: "指定元素替换",
}
MAIN_IMAGE_A_PLUS_FREE_MODES = {
    MAIN_IMAGE_A_PLUS_MODE_FREE,
    MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN,
}
MAIN_IMAGE_A_PLUS_TEMPLATE_MODES = {
    MAIN_IMAGE_A_PLUS_MODE_TEMPLATE,
    MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST,
    MAIN_IMAGE_A_PLUS_MODE_ELEMENT,
}
MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY = "desktop_equal"
MAIN_IMAGE_A_PLUS_LAYOUTS: dict[str, dict[str, Any]] = {
    "mobile_equal": {
        "label": "手机端｜600×1800｜自然流动",
        "target_size": (600, 1800),
        "section_heights": (450, 450, 450, 450),
        "text_margin_x": 54,
        "text_margin_y": 90,
    },
    "desktop_equal": {
        "label": "电脑端｜1464×2400｜自然均衡",
        "target_size": (1464, 2400),
        "section_heights": (600, 600, 600, 600),
        "text_margin_x": 132,
        "text_margin_y": 96,
    },
    "desktop_hero": {
        "label": "电脑端｜1464×2400｜首屏突出",
        "target_size": (1464, 2400),
        "section_heights": (800, 533, 533, 534),
        "text_margin_x": 132,
        "text_margin_y": 96,
    },
}
MAIN_IMAGE_A_PLUS_SECTION_PURPOSES = (
    "模特与品牌主视觉",
    "核心卖点与关键细节",
    "使用场景、功能表现或工艺展示",
    "套装规格、包装信息与品牌收尾",
)
A_PLUS_PRODUCT_LOCK_RULES = (
    "产品绝对锁定规则（整个 A+ 生成过程中的最高优先级硬约束）：内容参考图中的第 1 张核心产品，以及其余参考图中属于同一产品的真实角度和细节，都是不可编辑的原始产品资产。"
    "模板中原有的旧产品不属于用户产品，必须按模式要求清除或替换；一旦使用用户上传的产品，就必须保持与对应参考图完全一致。"
    "严禁对用户产品进行重绘、改写、再设计、风格化、理想化、美化、修复、纠错、增强、简化、补全、变形、换款、换色、重新打光、重新渲染或材质重塑。"
    "必须逐项锁定产品的 SKU 与款式、数量与套装组成、外轮廓、长宽比例、厚度、结构、部件数量、部件位置、排列顺序、开合状态、拍摄角度、透视、颜色、色温、材质、纹理、透明度、光泽、反射、阴影关系、边缘形态、瑕疵和全部细节。"
    "品牌名、Logo、包装结构、包装图案、标签、参数、条码和产品或包装上的所有可读文字必须逐字逐图保持原样；禁止纠错、翻译、改字、替字、重新排版或生成近似 Logo。"
    "禁止增加、删除、复制、合并、拆分或移动产品本体的任何零件、配件、包装内容和装饰；禁止把不同参考图的局部拼成一个不存在的新产品，禁止用模板产品或模型臆造内容替换用户产品细节。"
    "产品只允许作为一个完整、不可编辑的整体，在保持原始比例的前提下等比缩放和移动；禁止非等比拉伸、镜像、旋转、改变透视、裁切产品、遮挡产品关键信息或让产品超出画布。"
    "可以重新设计背景、场景、模特、装饰和文案排版，但这些元素不得覆盖、污染、染色或改变产品；如果产品与版式冲突，必须调整版式、背景和其他元素，绝不能调整产品本身。"
)
A_PLUS_UPLOAD_POOL_LOCK_RULES = (
    "上传素材池绝对锁定规则（A+测试最高优先级）：全部输入图只是同一个可选内容池，没有任何一张必须整图使用，也不以第 1 张强制指定主图。"
    "只能选择输入图中清楚、完整、真实可见的人物、商品、包装、Logo、文字、配件、步骤与效果元素；允许等比缩放、重新取景、移动、叠层和重排，允许直接舍弃不适合当前构图的元素。"
    "凡被采用的人物和物品必须保持真实身份、款式、结构、数量、比例、颜色、材质、图案和文字，禁止重绘、换款、修复、补全、融合或用近似内容替代。"
    "严禁生成素材池中不存在的新人物、五官、商品、包装、配件、工具、花朵、徽章、图标、认证、参数、Logo 或文案；只允许新建不承载商品语义的纯背景、抽象形状、渐变、纹理、光影和投影。"
    "源图已经截断、遮挡或无法确认的对象，如果其他输入图没有同一对象的完整真实依据，就必须舍弃，不能猜测缺失部分。"
)
MAIN_IMAGE_A_PLUS_MOBILE_SOURCE_LOCK_RULES = (
    "手机端适配素材角色锁定规则（最高优先级）：输入图片第 1 张是本次唯一内容源，最终成品中的人物、商品、包装、Logo、文字、参数、步骤图、效果图和品牌视觉只能来自第 1 张。"
    "第 2 张起若存在图片，它们只构成经过批准的 PC→手机版式参考对：每对按‘电脑版、对应手机版’连续排列，只用于学习如何拆解横向模块、调整主次、重新换行和组织纵向节奏。"
    "严禁从版式参考对复制或混入任何人物、脸、眼睛、睫毛、商品、包装、Logo、品牌名、文字、数字、颜色、背景照片、装饰或像素；参考对中的所有商业内容都属于其他商品。"
    "第 1 张中的真实商品与人物必须保持身份、数量、外观、结构、角度、颜色、材质、比例和细节不变；只能对完整语义元素等比缩放、移动和重排，禁止重绘、换款、变形、镜像或臆造。"
)
MAIN_IMAGE_A_PLUS_TEMPLATE_DEFAULT_PROMPT = (
    "请执行电商 A+ 成品套版替换。版式模板只用于锁定构图和设计结构，内容参考图用于提供新的品牌、文案、模特、商品、包装和细节素材。"
    "第一张模板图是唯一版式标准：最终宽高必须与第一张模板图完全一致，不能改尺寸、比例、裁切范围或画布方向。"
    "必须严格保持模板中的分区数量与边界、每个元素槽位的坐标、宽高、相对占比、图片窗口形状、裁切方式、叠放关系、对齐方式、视觉层级、留白、背景、边框、色块、装饰线条、字体风格和阅读顺序不变。"
    "只允许替换内容层：原品牌名、原 Logo、原文案、原模特、原商品、原包装、原产品效果、原产品特写、原参数和原标签；模板中的背景、色块、边框、分隔、装饰和结构元素不是替换对象，必须保留原有位置与数量。"
    "自动识别内容参考图中各素材的角色，并将模特替换到模板模特位、商品与包装替换到商品位、局部特写替换到细节位、文案与品牌信息替换到对应文字位。"
    "不得保留模板中的旧品牌、旧模特、旧产品、旧文案或旧参数；不得把模板原内容与新内容混合。"
    "严格执行一对一槽位替换：模板有几个内容槽位，结果就保留几个对应槽位；禁止新增、删除、合并、拆分或移动槽位。"
    "禁止自行增加模板中没有的人物、产品、配件、图标、徽章、花朵、光效、标签、边框、装饰、文字块或卖点模块；禁止重复人物、重复产品、重复 Logo 和堆叠无关元素。"
    "元素必须疏密有序，不得变成拼贴、九宫格或杂乱堆放；每个替换内容只能进入语义对应的原槽位，不能跨区、遮挡文字或挤占留白。"
    "只能使用内容参考图中清楚可见或用户补充要求中明确提供的信息，不得编造品牌、卖点、参数、认证、功效、价格或承诺。"
    "如果内容参考图没有提供某个旧内容的替代素材，应清除该槽位的旧内容并自然延续该槽位原有背景，不得保留旧内容、编造新内容或添加额外装饰。"
    "所有新文案必须清楚、完整、可读，不能出现乱码、错别字、缺字或被边缘截断；商品、模特和 Logo 必须保持真实身份与外观。"
    "最终结果应像在同一份专业设计源文件中完成的内容替换，而不是重新设计、拼贴或在旧内容上覆盖贴纸。"
    + A_PLUS_PRODUCT_LOCK_RULES
)
MAIN_IMAGE_A_PLUS_SINGLE_TEST_DEFAULT_PROMPT = (
    "请执行电商 A+ 成品整图套版重绘。输入图片中的第 1 张是完整成品 A+ 版式模板，后续图片全部是用于替换内容的新素材参考图。"
    "必须把第 1 张模板作为一张不可拆分的完整画布来理解和重绘，一次直接生成一张完整结果图；禁止把模板拆成四段、禁止逐段生成、禁止拼接、禁止输出多张局部图。"
    "唯一允许保留的内容只有两类：不携带旧商品或旧品牌信息的纯背景，以及模板的版式结构。版式结构包括宽高比例、画布方向、整体构图、分区数量、区域面积、元素槽位坐标、相对大小、裁切窗口、叠放关系、对齐方式、底层色块、结构边框、留白和阅读顺序。"
    "除纯背景和版式结构之外，模板画面中的所有前景内容都必须替换或删除，绝对不能只替换一部分。"
    "必须先完整盘点模板中的每一处旧产品、产品局部、包装、品牌名、Logo、水印、文案、参数、标签、图标、徽章、模特、人物脸部、头发、眼睛、手部、身体、服装、使用效果图、场景人物和带有旧商品语义的装饰元素，再逐项检查并全部替换。"
    "同一个旧产品、旧品牌或旧模特即使在模板中出现多次，每一次出现都必须替换，不能遗漏任何角落、缩略图、局部特写、半透明叠图或背景中的旧内容。"
    "后续内容参考图才是新内容的唯一来源：将新模特替换全部旧人物位置，将新产品与包装替换全部旧产品位置，将新细节替换全部旧细节位置，将新品牌、Logo、文案和参数替换全部对应文字位置。"
    "严格执行一对一内容替换，不新增、不删除、不移动、不合并、不拆分模板中的内容槽位；不得重新设计版式，不得增加模板中没有的人物、产品、图标、徽章、标签、花朵、光效、边框、装饰或文字模块。"
    "如果参考图没有提供某个旧内容的替代素材，必须清除该旧内容并自然补全该处原有背景；没有新模特时清除旧模特，没有新文案时清除旧文案，任何情况下都不得保留模板旧内容、编造新信息或添加无关元素。"
    "只使用参考图中真实可见或用户明确填写的信息，不得编造品牌、参数、功效、认证、价格或承诺。"
    "所有新文字与可读 Logo 必须完整、清楚、无乱码、无错字且不被画布边缘截断；人物和商品必须保持参考图中的真实身份、外观、颜色、材质、结构与比例。"
    "输出前必须再次检查整张图，确认模板中的旧产品、旧品牌、旧 Logo、旧文案和旧模特残留数量为零。"
    "输出必须是一张连贯、完整、商业级的 A+ 成品长图，不能出现接缝、断层、重复区域、四张图拼接感、贴纸覆盖感或新旧内容混合。"
    + A_PLUS_PRODUCT_LOCK_RULES
)
MAIN_IMAGE_A_PLUS_ELEMENT_DEFAULT_PROMPT = (
    "请执行电商 A+ 成品指定元素替换。输入图片中的第 1 张是完整成品 A+ 模板，后续每张图片都只对应一个用户指定的替换元素。"
    "必须把模板作为一张不可拆分的完整画布一次生成最终成品，禁止拆段、拼接、分屏或输出多张结果。"
    "模板的画布尺寸、背景、版式、分区、槽位坐标、元素大小、裁切窗口、叠放层级、对齐、留白、阅读顺序和所有未被指定的内容必须保持不变。"
    "只允许修改元素映射清单中明确列出的编号与区域；每张替换参考图只能用于它对应的编号，禁止把一个编号的素材误用到其他元素。"
    "同一编号包含多个出现区域时，必须把这些区域中的旧元素全部替换为该编号的新素材，不能遗漏角落、缩略图、局部特写或半透明重复元素。"
    "没有上传替换图的元素必须完整保留，不能顺带改写品牌、模特、产品、文案、参数、背景或装饰。"
    "替换内容必须自然融入原槽位，严格继承模板该位置的大小、角度、透视、裁切、光影与叠放关系，不能出现贴纸感、白边、旧内容残影或重复主体。"
    "只使用对应替换图中真实可见的信息，不得编造品牌、Logo、文案、参数、功效、认证、价格或承诺。"
    "最终只输出一张完整、清晰、商业级的 A+ 成品长图。"
    + A_PLUS_PRODUCT_LOCK_RULES
)
# Backward-compatible aliases for older sessions and callers that expect the original default layout.
MAIN_IMAGE_A_PLUS_TARGET_SIZE = tuple(
    MAIN_IMAGE_A_PLUS_LAYOUTS[MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY]["target_size"]
)
MAIN_IMAGE_A_PLUS_SECTION_HEIGHT = int(
    MAIN_IMAGE_A_PLUS_LAYOUTS[MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY]["section_heights"][0]
)

# Kept only for loading older sessions that still reference the retired local matting helpers.
IMAGE_MATTING_DEFAULT_MODEL_PATH = APP_DIR / "image_matting" / "briaai" / "RMBG-1.4" / "model.onnx"
IMAGE_MATTING_INPUT_SIZE = (1024, 1024)
_IMAGE_MATTING_LOCK = Lock()
_IMAGE_MATTING_SEGMENTER: Any | None = None
_IMAGE_MATTING_SEGMENTER_PATH = ""
# 火山引擎的“并发 1”是账号级限制，不是单个批次内部的线程数。
# 不同用户的后台队列可能同时运行，因此必须在整个进程内串行提交并轮询即梦任务。
_JIMENG_TASK_LOCK = Lock()
# OpenRouter 的图片编辑上游也会按账号限流。去睫毛是逐张编辑任务，跨会话串行可避免
# 多个用户同时提交时把短时并发放大成 429/5xx。
_OPENROUTER_REMOVE_EYELASHES_LOCK = Lock()
_OPENROUTER_ERROR_LOG_LOCK = Lock()



@st.cache_resource
def get_task_runtime() -> TaskRuntime:
    return TaskRuntime()


JimengStaticRequestHandler = create_static_request_handler(lambda: globals())


def build_jimeng_static_base_url(public_app_url: str, static_port: int) -> str:
    return _history_paths.build_jimeng_static_base_url(
        public_app_url,
        static_port,
        DEFAULT_PUBLIC_APP_URL=DEFAULT_PUBLIC_APP_URL,
        JIMENG_UPLOAD_ROUTE_PREFIX=JIMENG_UPLOAD_ROUTE_PREFIX,
        os=os,
        urllib=urllib,
    )


def build_history_static_base_url(public_app_url: str, static_port: int) -> str:
    return _history_paths.build_history_static_base_url(
        public_app_url,
        static_port,
        DEFAULT_PUBLIC_APP_URL=DEFAULT_PUBLIC_APP_URL,
        HISTORY_STATIC_ROUTE_PREFIX=HISTORY_STATIC_ROUTE_PREFIX,
        os=os,
        urllib=urllib,
    )


def build_infinite_canvas_url(public_app_url: str, static_port: int, username: str, workspace: str='') -> str:
    return _runtime_config.build_infinite_canvas_url(
        public_app_url,
        static_port,
        username,
        workspace,
        AUTH_QUERY_TOKEN_KEY=AUTH_QUERY_TOKEN_KEY,
        AUTH_QUERY_USER_KEY=AUTH_QUERY_USER_KEY,
        DEFAULT_PUBLIC_APP_URL=DEFAULT_PUBLIC_APP_URL,
        INFINITE_CANVAS_BUILD_DIR=INFINITE_CANVAS_BUILD_DIR,
        INFINITE_CANVAS_STATIC_ROUTE_PREFIX=INFINITE_CANVAS_STATIC_ROUTE_PREFIX,
        build_auth_token=build_auth_token,
        os=os,
        urllib=urllib,
    )


def ensure_jimeng_static_server(*, owner: bool = False) -> dict[str, Any]:
    if os.getenv("TC_SINGLE_PORT") != "1" or owner:
        return start_jimeng_static_server()
    runtime_settings = load_runtime_settings()
    static_port = int(runtime_settings.get("jimeng_static_port") or DEFAULT_JIMENG_STATIC_PORT)
    status = {
        "started": False,
        "bind_address": "127.0.0.1",
        "port": static_port,
        "base_url": str(runtime_settings.get("jimeng_public_upload_base_url") or "").strip(),
        "canvas_ready": False,
    }
    try:
        response = requests.get(f"http://127.0.0.1:{static_port}/_xiaoha_static_health", timeout=2)
        response.raise_for_status()
        payload = response.json()
        if payload.get("service") != "xiaoha-static":
            raise ValueError("端口上的服务不是小哈素材服务")
        status.update(started=True, canvas_ready=bool(payload.get("canvas_ready")))
    except (requests.RequestException, ValueError) as exc:
        status["error"] = f"素材服务暂不可用：{exc}"
    return status


@st.cache_resource
def start_jimeng_static_server() -> dict[str, Any]:
    runtime_settings = load_runtime_settings()
    upload_dir = ensure_jimeng_upload_dir()
    history_dir = ensure_db_image_dir()
    try:
        static_port = int(runtime_settings.get("jimeng_static_port") or DEFAULT_JIMENG_STATIC_PORT)
    except Exception:
        static_port = DEFAULT_JIMENG_STATIC_PORT
    bind_address = str(runtime_settings.get("server_address") or DEFAULT_SERVER_ADDRESS).strip() or DEFAULT_SERVER_ADDRESS
    try:
        handler = partial(
            JimengStaticRequestHandler,
            directory=str(upload_dir),
            upload_directory=str(upload_dir),
            history_directory=str(history_dir),
            canvas_directory=str(INFINITE_CANVAS_BUILD_DIR),
        )
        server = ThreadingHTTPServer((bind_address, static_port), handler)
        server.daemon_threads = True
        thread = Thread(target=server.serve_forever, name="jimeng-static-server", daemon=True)
        thread.start()
        return {
            "started": True,
            "bind_address": bind_address,
            "port": static_port,
            "base_url": str(runtime_settings.get("jimeng_public_upload_base_url") or "").strip(),
            "canvas_ready": (INFINITE_CANVAS_BUILD_DIR / "index.html").exists(),
        }
    except OSError as exc:
        return {
            "started": False,
            "bind_address": bind_address,
            "port": static_port,
            "base_url": str(runtime_settings.get("jimeng_public_upload_base_url") or "").strip(),
            "canvas_ready": False,
            "error": f"端口 {static_port} 启动失败：{exc}",
        }


from Department.视觉设计部.xiaoha.features.seedream_tools import feature_definitions as seedream_feature_definitions

FEATURES = [
    {
        "key": "prepress_check",
        "name": "印前检查",
        "summary": "上传 AI、PDF、截图或 ZIP，自动生成 19 项印前合规报告",
        "mode": "prepress_check",
        "output_mode": "report",
        "min_images": 0,
        "max_output_images": 0,
        "description": "检查 CMYK、2mm 出血、300dpi、字体转曲、文件名、页面尺寸及包装视觉规范。",
        "default_prompt": "按设计部印前检查流程生成逐项合规报告。",
    },
    {
        "key": "a_plus_canvas",
        "name": "A+画布",
        "summary": "在画布中整理A+素材，集中使用A+创作工具",
        "mode": "canvas",
        "output_mode": "image",
        "min_images": 0,
        "max_output_images": 0,
        "description": "集中使用画布和A+相关创作功能。",
        "default_prompt": "",
    },
    {
        "key": "infinite_canvas",
        "name": "无限画布",
        "summary": "上传图片后自由组合已有功能",
        "mode": "canvas",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 0,
        "description": "把已经写好的单图处理功能按顺序组合起来，前一步结果会自动作为下一步输入。",
        "default_prompt": (
            "请把上传图片作为唯一主体，按用户选择的功能顺序逐步处理。"
            "每一步都必须尽量保持人物身份、五官结构、构图关系、光影和真实质感稳定。"
            "最终只输出每张输入图对应的一张完成图。"
        ),
    },
    {
        "key": "product_retouch",
        "name": "产品图精修",
        "summary": "保留产品真实细节，完成商业产品图级别的清晰度与瑕疵整理",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "只精修产品本身，不改变包装文字、Logo、颜色、比例、结构和画布构图。",
        "default_prompt": (
            "The final image MUST have a uniform pure white background (#FFFFFF), with no texture, gradient, color cast, or original background elements; preserve only a subtle natural contact shadow beneath the product. "
            "Use Nano Banana 2 image editing only. Preserve the exact original pixel dimensions, aspect ratio, framing, composition, product scale, and visible sharpness; do not downsample, blur, soften, compress, or reduce fine detail. "
            "Make the result visibly clearer and more premium than the input: enhance true edge definition, micro-contrast, material texture, fine surface detail, label legibility, clean highlights, controlled reflections, and realistic depth without inventing or redesigning any product detail. "
            "When a second reference image is provided, treat image 1 as the only product source and image 2 only as a reference for lighting, material finish, contrast, and premium presentation; never copy the second image's product, layout, props, or text. "
            "请对输入的产品图进行商业产品摄影级精修。产品主体、包装结构、Logo、所有文字、标签、规格、颜色、材质纹理、比例、透视、构图和画布尺寸必须保持不变；"
            "只清理灰尘、污渍、划痕、轻微折痕、压缩噪点和不自然的小瑕疵，均匀并真实地整理光影、边缘和清晰度，提升产品质感与可读性。"
            "禁止重新设计、改写文字、补画细节、改变颜色、增加装饰、裁剪、扩图、换背景或生成新产品。输出一张自然、真实、可用于电商主图的精修结果。"
        ),
    },
    {
        "key": "product_retouch_local",
        "name": "局部瑕疵修复",
        "summary": "只修复指定黑线、划痕、污渍等局部问题",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "请在提示词中描述要修复的区域和瑕疵，AI 只修改指定区域。",
        "promptRequired": True,
        "default_prompt": (
            "Use Nano Banana 2 only. Perform a tightly localized product-photo repair. "
            "Modify only the defect explicitly described by the user; preserve all product geometry, packaging, logos, text, colors, material, reflections, sharpness, resolution, framing, and proportions. "
            "Remove the unwanted black line or other described defect by reconstructing the surrounding continuous material naturally. Do not remove intentional printed text or legitimate structural details. "
            "Keep a clean pure white background (#FFFFFF), with no other changes. Output one realistic, sharper, premium product image."
        ),
    },
    {
        "key": "background_cutout",
        "name": "智能抠图",
        "summary": "只保留有睫毛的商品区域",
        "mode": "ai_cutout",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "先由 AI 把带睫毛的托盘完整抠出来并清理杂质背景，再由代码转成透明 PNG。",
        "default_prompt": (
            "请严格基于上传图片做商品抠图预处理：只保留包含多排黑色假睫毛的长方形商品托盘/包装主体，"
            "完整保留白色卡纸、透明塑料托盘边框、品牌文字、尺寸文字、花纹、底部说明文字和全部睫毛排布。"
            "必须去除桌面、左侧透明盒盖、后方支架、阴影、反光、杂物和所有无关背景。"
            "必须保持原图商品颜色、亮度、色温、饱和度、主体高度、宽高比例和透视角度一致。"
            "不要调色、不要美化、不要锐化、不要拉伸压缩、不要重绘或改写包装文字，不要增删睫毛，不要裁掉托盘边缘。"
            "输出时把商品主体放在纯 #00FF00 绿幕背景上；背景必须完全纯色、无渐变、无阴影、无纹理、无白边、无水印。"
        ),
    },
    {
        "key": "hd_batch",
        "name": "模特图批量高清",
        "summary": "Nano Banana 2.1 高清增强，保留生成原始分辨率",
        "mode": "portrait_hd",
        "model": NANO_BANANA_MODEL,
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "fixed_output_count": 1,
        "description": "使用 Nano Banana 2.1 增强原图清晰度，保留人物、商品和背景内容；每张原图输出一张结果，保留模型生成结果的原始像素宽高。",
        "default_prompt": (
            "仅使用每张原图进行高清增强，保留原图内容、比例与边界。"
            "使用 Nano Banana 2.1，不使用其他人物参考图；每张输出一张结果，保留模型生成结果的原始像素宽高。"
        )
    },
    {
        "key": JIMENG_HD_FEATURE_KEY,
        "name": "即梦超清",
        "summary": "火山引擎即梦智能超清，直接输出 8K 高清结果",
        "mode": "jimeng_upscale",
        "model": JIMENG_HD_MODEL_NAME,
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "调用即梦智能超清专用接口，将原图增强到 8K；保持原图内容、构图、比例与色彩，不重新生成或改写人物和商品。",
        "default_prompt": (
            "使用火山引擎即梦智能超清专用接口处理输入原图，固定 resolution=8k、scale=50。"
            "这是超分辨率增强，不是图片生成或重绘任务；不得改变、替换、增删或改写原图中的人物、商品、文字、Logo、背景和任何内容。"
            "保持原图宽高比、构图、取景、颜色、光影及边界内容，只提升分辨率、清晰度和原有细节的可见度。"
        )
    },
    {
        "key": "image_resize",
        "name": "图片尺寸放大",
        "summary": "按指定像素放大图片",
        "mode": "local_resize",
        "model": "本机高质量处理",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "输入目标宽高后在本机完成高质量尺寸调整，不调用生图接口。",
        "default_prompt": "按用户指定的目标像素尺寸进行本机高质量图片缩放。",
    },
    {
        "key": "remove_eyelashes",
        "name": "批量去掉睫毛",
        "summary": "自然去睫毛，保留眼部细节",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "去掉所有睫毛，包括真睫毛和假睫毛；除睫毛外，其他所有内容必须完全不变。",
        "default_prompt": REMOVE_EYELASHES_PRESERVE_BASIC_PROMPT,
    },
    {
        "key": "pose_change",
        "name": "模特换姿势",
        "summary": "只换姿势，场景人物不变",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "1 张主模特图，姿势参考最多 5 张；只输出 1 张结果图，姿势必须与参考图完全一致，场景和人物严格保持不变。",
        "default_prompt": (
            "请严格基于主模特图进行姿势变化，目标姿势必须与姿势参考图完全一致。"
            "包括头部朝向、肩颈角度、手臂位置、手势、身体转向、躯干弯曲、腿部动作、站姿或坐姿、重心方向、镜头朝向和整体动作细节都要严格对齐参考图。"
            "只允许参考姿势参考图中的姿势信息，不允许参考其人物身份、脸部特征、发型、妆容、服饰、体型、肤色、场景、背景、道具、光线、色彩、构图、机位和整体风格。"
            "最终结果必须完全保留主模特图中的人物身份、脸部特征、发型、妆容、服饰、场景、背景、光线、构图、机位和整体风格，只改变姿势。"
            "仅输出 1 张结果图。"
        ),
    },
    {
        "key": "scene_change",
        "name": "模特换场景",
        "summary": "只换场景，人物姿势不变",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "1 张主模特图，场景参考最多 5 张；只输出 1 张结果图，只改变场景，人物和姿势严格保持不变。",
        "default_prompt": (
            "请严格基于主模特图进行场景变化，只允许改变背景、空间氛围和环境。"
            "人物身份、脸部特征、发型、妆容、服饰、姿势、肢体动作、构图、机位、光线关系和整体风格都必须严格保持不变。"
            "仅输出 1 张结果图。"
        ),
    },
    {
        "key": BACKGROUND_TEXTURE_FEATURE_KEY,
        "name": "场景背景质感",
        "summary": "只改变背景表面质感，人物、商品与构图不变",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "上传 1 张原图，选择预设质感或直接用提示词描述；只重塑场景背景的材质与纹理，不替换人物、商品和空间结构。",
        "default_prompt": (
            "请严格基于第 1 张原图执行局部背景材质编辑，只允许改变场景背景表面的材质、纹理、粗糙度、反射特性和与材质直接相关的细微光影。"
            "必须保留原场景的空间结构、墙面与地面边界、家具和道具的位置、透视、景深、机位、画幅、构图、光线方向与整体色彩关系。"
            "人物、脸部、五官、皮肤、头发、妆容、服饰、姿势、肢体、商品、包装、Logo、文字和前景物体全部锁定，禁止重绘、替换、移动、增删、变形、调色或覆盖。"
            "背景新质感必须沿原有表面透视与几何结构自然贴合，纹理尺度真实，遮挡关系、接触阴影、反射和景深符合原照片，不得像平铺贴图、滤镜、蒙版或独立色块。"
            "不得更换场景类型，不得生成新人物、新商品、新文字、新道具或无关装饰。"
            "最终仅输出 1 张与原图构图和宽高比一致的真实商业摄影结果。"
        ),
    },
    {
        "key": "outpaint",
        "name": "模特扩图",
        "summary": "扩展画面，优化构图",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": OUTPAINT_RESULTS_PER_SOURCE,
        "description": "适合半身补全、边缘扩展、补足背景和人物缺失区域，但原图已有细节必须完全保持不变。",
        "default_prompt": (
            "Perform one-pass direct outpainting from the uploaded original photograph. "
        "The four numeric directional expansion amounts are field-of-view constraints: extend only the requested sides and make the generated image itself the final outer canvas. "
        "Generate new content only on the sides included by that selection, plus a transition corridor spanning both sides of each former source edge that touches an expanded side; never add space on an unselected side, recenter the source, or redistribute expansion between sides. "
        "Generate the entire larger-frame photograph as one continuous image in a single model pass. "
            "Do not paste, composite, embed, overlay, or preserve the source as a rectangular block inside the result. Seamless full-frame continuity has higher priority than exact source-pixel preservation near every former boundary. "
            "There must be no visible original-image rectangle, inset photo, border, frame, hard edge, color block, tonal step, or rectangular seam anywhere in the final image. "
            "Extend the camera field of view beyond the requested original borders while keeping the same person, identity, face, expression, pose, hairstyle, clothing, camera viewpoint, perspective, lighting, colors, focus, and photographic style as stable as possible. "
            "Do not preserve the original crop or the subject's old frame occupancy: the subject and original field of view must become proportionally smaller inside the final frame whenever expansion is requested. "
        "Continue the environment, background, clothing, and any anatomically necessary body area naturally through the former image boundaries. If a person, arm, hand, torso, garment, hair, furniture, or other structure crosses a former boundary, regenerate the narrow transition corridor and the new outer area together so the structure remains continuous; never terminate it at the old edge and restart a different version below or beside it. "
            "The transition across every former image edge must be structurally and photographically continuous, with coherent geometry, texture, light, depth, and detail rather than blur or smudging. "
            "Do not create a collage, split frame, picture-in-picture result, duplicated subject, mirrored content, stretched pixels, tiled texture, repeated background, or newly composed portrait. "
            "The final result must look like one photograph captured with a wider canvas, never like an original photo placed on top of generated surroundings."
        ),
    },
    {
        "key": "single_to_double",
        "name": "单眼变双眼",
        "summary": "单眼图像智能补全",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "description": "针对人物单眼状态进行双眼重建，尽量保留自然神态。",
        "default_prompt": (
            "将这张单眼局部照片自然扩展为完整双眼正面图，保持原有眼睛的眼型、瞳孔颜色、睫毛浓密度、眼妆风格、肤色和光影质感一致。生成另一只对称自然的眼睛，五官比例真实，眼距合理，皮肤纹理细腻，睫毛根根分明，妆容干净高级，整体像真实美妆摄影照片。不要改变原眼睛特征，不要夸张变形，不要卡通感，不要过度磨皮，背景简洁，高级商业修图质感。"
        ),
    },
    {
        "key": "skin_tone",
        "name": "模特换肤色",
        "summary": "自然替换肤色，真实细腻",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "上传 1 张主体图和 1 张肤色参考图；只参考参考图中的肤色，主体只改变肤色，其他内容严格保持不变。",
        "default_prompt": (
            "请严格基于主体图进行肤色替换，只允许改变主体人物的肤色。"
            "肤色必须参考肤色参考图中的肤色表现，但只允许参考其肤色信息，不允许参考其人物身份、脸部特征、发型、妆容、服饰、体型、姿势、背景、场景、道具、光线、色彩、构图和整体风格。"
            "最终结果必须严格保留主体图中的人物身份、脸部特征、五官、发型、妆容、服饰、肤质、毛孔、皮肤纹理、姿势、构图、机位、光线、背景和整体风格，只改变肤色。"
            "仅输出 1 张结果图。"
        ),
    },
    {
        "key": "pupil_color_change",
        "name": "换瞳孔颜色",
        "summary": "只换瞳孔颜色",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "上传 1 张主体图和 1 张瞳孔颜色参考图；只参考参考图中的瞳孔颜色，主体只改变瞳孔颜色，其他内容严格保持不变。",
        "default_prompt": (
            "请严格基于主体图进行瞳孔颜色替换，只允许改变主体人物的瞳孔颜色。"
            "瞳孔颜色必须参考瞳孔颜色参考图中的瞳孔颜色表现，但只允许参考其瞳孔颜色信息，不允许参考其人物身份、脸部特征、发型、妆容、眼型、睫毛、服饰、体型、姿势、背景、场景、道具、光线、色彩、构图和整体风格。"
            "最终结果必须严格保留主体图中的人物身份、脸部特征、眼型、眼神、睫毛、妆容、肤质、皮肤纹理、发型、服饰、姿势、构图、机位、光线、背景和整体风格，只改变瞳孔颜色。"
            "仅输出 1 张结果图。"
        ),
    },
    {
        "key": "eye_shape_change",
        "name": "换眼型",
        "summary": "只换眼型",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "上传 1 张主体图和 1 张眼型参考图；只参考参考图中的眼型，主体只改变眼型，其他内容严格保持不变。",
        "default_prompt": (
            "请严格基于主体图进行眼型调整，只允许改变主体人物的眼型结构与眼部轮廓。"
            "眼型必须参考眼型参考图中的眼型表现，但只允许参考其眼型信息，不允许参考其人物身份、脸部特征、发型、妆容、瞳孔颜色、睫毛、服饰、体型、姿势、背景、场景、道具、光线、色彩、构图和整体风格。"
            "最终结果必须严格保留主体图中的人物身份、脸部特征、瞳孔颜色、眼神、睫毛、妆容、肤质、皮肤纹理、发型、服饰、姿势、构图、机位、光线、背景和整体风格，只改变眼型。"
            "仅输出 1 张结果图。"
        ),
    },
    {
        "key": "three_view",
        "name": "模特侧面图生成",
        "summary": "生成单张侧面图",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "上传 1 张主体图和 1 张角度参考图；只参考参考图中的角度，主体人物和其他内容严格保持不变。",
        "default_prompt": (
            "请严格基于主体图生成 1 张模特侧面图。"
            "角度必须参考角度参考图中的拍摄角度与人脸朝向，但只允许参考其角度信息，不允许参考其人物身份、脸部特征、发型、妆容、服饰、肤质、背景、场景、道具、光线、色彩、构图和整体风格。"
            "最终结果必须严格保留主体图中的人物身份、脸部特征、发型、妆容、服饰、肤质、光线风格、背景和整体画面质感，只改变人物角度为参考图对应的侧面角度。"
            "仅输出 1 张结果图。"
        ),
    },
    {
        "key": "ai_qa_image",
        "name": "AI问答生图",
        "summary": "通过对话生成图片，支持参考图与连续修改",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 0,
        "max_output_images": 1,
        "description": "输入文字或附加参考图生成图片，支持保存对话并基于上一轮结果继续修改。",
        "default_prompt": (
            "请根据我的文字要求生成 1 张高质量结果图；如有参考图，请结合参考图进行多模态理解。"
            "要优先理解用户上传图片中的主体、场景、构图、细节和视觉关系，再严格按照文字要求执行生成。"
            "仅输出 1 张结果图。"
        ),
    },
    {
        "key": IMAGE_SMART_ANALYSIS_FEATURE_KEY,
        "name": "图片智能分析",
        "summary": "拖入一张主图，全面分析配色、装饰元素、构图与内容风格",
        "mode": "openrouter",
        "model": IMAGE_SMART_ANALYSIS_MODEL,
        "output_mode": "text",
        "min_images": 1,
        "max_input_images": 1,
        "max_output_images": 0,
        "description": "只分析图片，不修改图片；输出带区域标注、真实色卡、HEX 色号和简短说明的可视化拆解图。",
        "default_prompt": (
            "你是一名资深商业视觉设计师、摄影美术指导和电商图片分析师。"
            "请只分析用户上传的第1张主图，不要生成、修改或重绘图片，也不要把任务理解成生图。"
            "先观察全图，再把画面归纳为3至6个有明确意义的主要视觉区域，分析要简短、具体、便于制作视觉拆解图。"
            "只陈述图片中确实可见的事实；推断内容必须明确标记为“推测”；看不清的文字、Logo、材质、商品型号或细节必须写“无法确认”，禁止臆造。"
            "系统会在提示词末尾提供从原图像素直接提取的真实色号；你只能为这些色号填写用途和简短描述，禁止新增、修改或猜测色号。"
            "最终只返回一个有效 JSON 对象，不要 Markdown、代码围栏或额外说明。JSON 格式必须为："
            '{"summary":"全图视觉概述，60字以内",'
            '"composition":"构图和视觉动线，50字以内",'
            '"lighting":"光影与材质，40字以内",'
            '"typography":"文字与字体，无文字则写未发现清晰文字，40字以内",'
            '"decorations":["装饰元素及作用，最多5项"],'
            '"style_tags":["风格标签，最多8项"],'
            '"color_notes":[{"hex":"系统提供的色号","role":"主色/辅色/强调色/中性色","description":"颜色在画面中的位置与作用，25字以内"}],'
            '"regions":[{"id":1,"name":"区域名称，10字以内","bbox":[左,上,右,下],'
            '"content":"区域可见内容，35字以内","style":"区域的色彩、装饰或视觉作用，35字以内"}]}。'
            "bbox 使用0至1000的归一化坐标，必须覆盖对应内容，左<右、上<下；区域不要重叠过多，也不要把无关内容合并。"
        ),
    },
    {
        "key": AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY,
        "name": "亚马逊A+改沃尔玛A+",
        "summary": "把一张亚马逊 A+ 长图重构为 4 张独立且连续的沃尔玛 16:9 A+ 页面",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_input_images": 1,
        "max_output_images": AMAZON_TO_WALMART_PAGE_COUNT,
        "fixed_output_count": AMAZON_TO_WALMART_PAGE_COUNT,
        "target_size": AMAZON_TO_WALMART_PAGE_SIZE,
        "target_size_text": "1920*1080",
        "description": "上传 1 张由 4 个 1464×600 内容段组成的亚马逊 A+；系统按顺序重构为 4 张 1920×1080 沃尔玛 A+，单张成立，纵向拼接仍保持统一连贯。",
        "default_prompt": (
            "请把上传的亚马逊 A+ 长图转换为沃尔玛 A+ 内容组。"
            "完整保留原图中真实存在的商品、人物、包装、品牌、Logo、可读文案、参数、卖点和阅读顺序，不得编造或替换商品事实。"
            "输出固定为 4 张独立的 1920×1080 横版页面；每页必须拥有明确主题、完整主体、完整文案和独立可用的商业构图。"
            "必须对四页文案做全局去重：同一标题、宣传句、卖点、参数说明、功能说明和行动语在整组四页中只能出现一次，不得原句重复，也不得改写成近义句后重复表达。"
            "按照原图从上到下把文案分配给第 1 至第 4 页；当前页只使用属于当前内容段且尚未在前页出现的文案。若原稿自身存在重复文案，只保留第一次出现，后续页面删除重复项并用商品细节、场景或自然留白重新平衡版式，绝对不能编造替代文案。"
            "品牌 Logo 可以为品牌识别而保留，但品牌口号、宣传标题和卖点仍然不得跨页重复。"
            "四页必须共享同一套品牌色、字体气质、光影、背景材质、装饰语言、留白规则和视觉层级。"
            "按第 1 至第 4 页顺序纵向排列时，背景、色块、纹理、光线或装饰动线应自然延续，不能出现突兀换色、风格跳变、重复内容、硬接缝或四张无关海报的拼凑感。"
            "适配 16:9 时必须重新排版和扩展场景，不得拉伸、压扁、简单裁切或用模糊边框补齐；商品、人物、Logo 和文字均不得被画布边缘截断。"
        ),
    },
    {
        "key": A_PLUS_STYLE_MODEL_REPLACE_FEATURE_KEY,
        "name": "A+首屏风格复刻—替换模特",
        "summary": "参考首屏风格调性，把其中所有模特替换为指定模特",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 2,
        "max_input_images": 2,
        "max_output_images": 1,
        "target_size": (1464, 1000),
        "target_size_text": "1464*1000",
        "description": "第 1 张上传 A+ 首屏风格参考图，第 2 张上传唯一一张目标模特图。优先保留目标模特原始姿势，自然融合画面并自动补全缺失局部，输出固定 1464×1000。",
        "default_prompt": (
            "请执行电商 A+ 首屏的风格复刻与指定模特替换。输入图片中的第 1 张是 A+ 首屏参考图，只提供风格与整体调性；第 2 张提供目标模特的身份与原始姿态。"
            "请参考第 1 张图的整体视觉风格，包括配色倾向、光影氛围、质感与材质表现、字体气质、装饰语言和版面节奏，输出一张风格接近的 A+ 首屏。"
            "不需要逐像素复刻原版式：允许在保证商业设计合理、信息层级清晰的前提下重新组织版面，调整元素的位置、大小和疏密关系，让画面更自然协调。"
            "把参考图中出现的所有模特统一替换为第 2 张提供的目标模特。必须稳定保持目标模特的身份、脸型、五官、肤色、发型和辨识度，不得混入原模特的面部特征，不得出现多个不同身份的人物。"
            "目标模特必须自然融入新画面：光线方向、色温、反差、景深、透视比例、服装质感和背景氛围要与画面一致，边缘过渡自然，不得出现抠图感、拼贴感、生硬贴脸或悬浮的边缘。"
            "优先保留目标模特参考图本身的原始姿势、肢体动作、身体朝向和头部朝向，让她以原有姿态自然融入画面；不必模仿首屏风格参考图中原模特的姿势，也不要为了复刻风格而刻意改动作、扭转身体或强行摆成相同姿势。"
            "可根据目标模特原有姿态调整人物位置、等比大小、构图留白、背景和周边元素，使光影、透视、接触阴影与遮挡关系自然协调。仅使用第 2 张目标模特图作为身份和姿态依据，不得拼凑其他人物的肢体动作。"
            "若目标模特素材因裁切或遮挡缺少头发、肩颈、手臂、手部、身体或服装边缘，应沿现有姿态、人体结构、透视和服装走向自动自然补全融入画面所需的缺失局部；已完整可见的部位保持一致，延续同一人物的肤色、服饰和质感，衔接无断层，不得改变身份、五官或额外增加肢体。"
            "参考图中的商品、Logo、可读文案、排版位置和品牌视觉，如未被用户明确要求替换，必须完整保留；不得改写文字、编造卖点、参数、认证或品牌信息。"
            "最终只输出一张完整成品图，精确尺寸为 1464×1000 像素。画面必须覆盖四边，无白边、黑边、截图界面、对话框、水印、拼贴接缝或候选方案。"
            "使用高清商业修图质量，人物面部、发丝、商品、文字和细节清晰锐利，禁止模糊、畸形、重复肢体、乱码、低分辨率和过度磨皮。"
        ),
    },
    {
        "key": A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY,
        "name": "A+首屏卖点融合",
        "summary": "底稿元素原样保留，只在空白区自然加入完整卖点",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 2,
        "max_input_images": 10,
        "max_output_images": 1,
        "target_size": (1464, 2400),
        "target_size_text": "",
        "description": "第一张底稿的所有已有元素保持不变且不受遮挡；只在安全空白区域加入完整、合适的卖点素材，放不下则省略，不裁切、不强行填满。尺寸和比例跟随底稿。",
        "default_prompt": (
            "第1张图是不可修改的完整A+底稿，所有人物、商品、文字、Logo、背景装饰、侧边和页脚均原样保留，不得重绘、移动、调色、删改、裁切、重排或遮挡任何已有元素。"
            "只在第1张图真实空白且能完整容纳元素的区域，选择性加入后续卖点素材，不要求用完全部素材。"
            "被采用的元素和必要信息必须完整，不裁切、不截断、不遮挡、不拉伸；只能合理等比缩小，若太大、比例不适合或缩小后难以辨认，则整体省略。"
            "新增元素与底稿统一色彩、光影、字体气质及视觉层级，保持适当间距和自然留白，不强行填满、不做机械拼贴、不与原有设计冲突。"
            "只使用真实可见的卖点和文案，不编造信息、不重复已有内容。补充要求仅适用于新增素材，不能改变底稿保护规则。"
            "最终画布沿用第1张图的原始像素尺寸和宽高比例，不扩图、不裁图，输出一张自然协调的完整A+。"
        ),
    },
    {
        "key": A_PLUS_REFERENCE_LAB_FEATURE_KEY,
        "name": "A+3.0",
        "summary": "上传素材，生成统一、真实的商业 A+ 图片",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_input_images": A_PLUS_REFERENCE_LAB_MAX_PRODUCT_IMAGES,
        "max_output_images": FEATURE_OUTPUT_COUNT_MAX,
        "target_size": MAIN_IMAGE_A_PLUS_TARGET_SIZE,
        "description": "上传图片是唯一内容来源；从中选择真实人物、商品、包装、文字和细节，自由重组为商业 A+。",
        "default_prompt": (
            "只使用用户上传图片中真实存在的内容，生成一张高完成度电商 A+ 长图。"
            "上传图中的所有人物、商品、包装、Logo、文字、配件、效果图和步骤图都是可选内容；允许主动取舍和重新组合，不要求全部采用，也不要求整张照搬任何一张源图。"
            "除纯背景、抽象色块、无语义纹理、光影和投影外，不得创造上传图中不存在的人物、商品、包装、配件、标识、图标、认证、参数或文案。"
            "先建立统一品牌视觉系统，再组织主视觉、核心卖点、细节证据、使用说明和品牌收尾；结果必须具有清晰焦点、尺度对比、前中后景和商业设计层级。"
            "严格保持被采用元素的身份、外观、品牌、包装、颜色、比例和结构，不能融合不同对象或猜测补全缺失部分。"
            + A_PLUS_PRODUCT_LOCK_RULES
        ),
    },
    {
        "key": A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY,
        "name": "A+首屏风格逆向",
        "summary": "上传参考图，逆向拆解风格并批量生成同风格创意图",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_input_images": 1,
        "max_output_images": 4,
        "target_size": (1464, 1098),
        "description": (
            "上传 1 张首屏风格参考图，AI 从主体内容、构图布局、色彩搭配、光影效果、设计风格、细节元素六个维度拆解，"
            "反写中文生图提示词；提示词可直接修改，再批量生成同风格创意图，最后筛选最优方案做二次优化。"
        ),
        "default_prompt": (
            "请基于参考图的视觉风格，生成一张同风格的电商 A+ 首屏创意图片。"
            "只借鉴参考图的构图节奏、色调关系、光影氛围、材质质感与设计语言，不照搬其中的品牌、文字和商品。"
        ),
    },
    {
        "key": "poster_fusion",
        "name": "海报融合",
        "summary": "以第1张海报为主体，融合1～3张参考图的风格与元素",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 2,
        "max_input_images": 4,
        "max_output_images": 1,
        "fixed_output_count": 1,
        "description": "1张主体海报与1～3张风格参考，自然融合光影、材质和装饰，生成一张丰富且连贯的海报。",
        "default_prompt": "以第1张海报为主体，融合1～3张参考图的风格和辅助元素，统一光影与透视，禁止简单拼贴。",
    },
    {
        "key": MULTI_REFERENCE_COMPOSER_FEATURE_KEY,
        "name": "多图参考创作",
        "hidden": True,
        "summary": "逐图反推，挑选六类参考内容，组合提示词生成底图",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 0,
        "max_input_images": 10,
        "max_output_images": 4,
        "description": "分别反推多张参考图，自选背景、主体、辅助元素、装饰、字体和质感，组合成新提示词后生成底图。",
        "default_prompt": "",
    },
    {
        "key": MAIN_IMAGE_A_PLUS_FEATURE_KEY,
        "name": "主图生A+",
        "summary": "支持自由创作、首屏设计感、成品套版替换、整图测试与指定元素替换",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_input_images": MAIN_IMAGE_A_PLUS_MAX_FILES,
        "max_output_images": 1,
        "target_size": MAIN_IMAGE_A_PLUS_TARGET_SIZE,
        "description": "支持自由创作整图直出、首屏商业主视觉强化、成品套版、整图全量替换，以及识别模板元素后按编号上传素材进行指定替换。",
        "default_prompt": (
            "请严格基于上传的主图设计一张完整的电商 A+ 宣传长图。"
            "第 1 张图是核心主图，决定商品身份、品牌、包装、颜色、材质和外观；其余图片只用于补充角度、细节、套装内容、使用方式与视觉素材。"
            "必须在一次生成中直接输出一张完整长图，禁止拆成多个片段分别生成，禁止纵向或横向拼接，禁止把任何原图作为矩形图层原样贴回画面。"
            "自由创作时，整张长图只需从上到下大体形成四个内容阶段，不按固定距离划分，也不显示分段高度、坐标、间距或辅助线。"
            "第一阶段建立具有商业审美的品牌与商品主视觉：形成单一明确焦点，通过专业网格、主次比例、留白、光影、景深和色彩关系形成高级海报感；如果上传素材中包含多个模特，只挑选一位最清晰、最适合商业展示的模特，放在整张长图最上方的首屏并置于最上层，禁止再出现第二位模特或重复同一模特；如果没有模特则以核心商品为主视觉且不得凭空添加人物；不得把上传素材直接平铺、堆叠或全部塞入首屏。"
            "随后自然过渡到核心卖点与关键细节、使用场景或工艺表现，最后以套装规格、包装信息或品牌形象收尾。"
            "四个阶段只是同一张画布中的阅读节奏，不是四个独立方框；不得出现明显分割线、硬边界、卡片式分栏、接缝、重复背景或四块等高拼接感。"
            "人物、产品、场景、光影、色块、纹理、装饰和大图形可以在相邻阶段之间自然跨越、遮挡和延伸，使整张长图像一次完成的连续商业设计。"
            "保持统一的品牌色、字体风格、光影和商业质感；不要做成杂乱拼图，不要出现重复商品、无关商品或空白断层。"
            "画面背景、场景、色块、纹理和装饰必须满版延伸到画布四边，不能出现外边框、白边、黑边、模糊边带或留白。"
            "文字排版必须在画布上、下、左、右四条外边缘保留自然可读空间；不要显示安全距离或测量标记。完整文案、参数和可读 Logo 不能被任何一侧画布边缘截断。"
            "必须准确保持商品主体、品牌标识、包装结构、颜色、比例和关键细节，不得擅自换款、变形或虚构不存在的配件。"
            "只能使用上传图片中明确可见或用户补充说明中明确提供的卖点、规格和宣传信息；不得编造参数、认证、功效、折扣或承诺。"
            "所有商品纹理、边缘、Logo、包装文字和宣传文字必须清楚锐利、易读，禁止乱码、错别字、模糊、虚焦、涂抹、像素化、压缩痕迹和过度柔化。"
            "所有可读文字必须保留充足安全区，不要贴近上、下、左、右任何一侧边缘；非文字背景仍需满版铺满。"
            "画布四边必须完整保留，禁止从上下左右任何一侧裁切；任何标题、正文、参数、品牌名、商品主体和可读 Logo 都不能越过或贴住画布边缘，必须完整呈现，必要时缩小字号、换行、缩小主体或向画面内部移动。"
            "使用原生 4K 高清细节生成；最终必须呈现为一张从顶部到底部统一构图、统一场景、统一光影的一体化 A+ 宣传成品，不要输出绿幕、透明图、线框、草图或候选版式。"
            + A_PLUS_PRODUCT_LOCK_RULES
        ),
    },
    {
        "key": "amazon_a_plus",
        "name": "自由创作 PSD",
        "summary": "自由生成商业 A+，导出 Photoshop 可编辑分层文件",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_input_images": MAIN_IMAGE_A_PLUS_MAX_FILES,
        "max_output_images": 1,
        "description": "可上传最多 10 张参考图，自由创作完整 A+，并自动拆分背景、商品、模特、文案和装饰元素后导出 PSD。",
        "default_prompt": (
            "请严格基于上传原图自由创作一张适用于电商 A+ 宣传的可分层元素底稿。"
            "第1张图片是核心商品与品牌依据，其余图片只补充商品角度、细节、包装、模特、文案和使用场景；不得替换商品、品牌或人物身份。"
            "整体从上到下形成自然连续的四阶段商业阅读节奏：品牌主视觉、核心卖点与细节、使用场景或工艺、包装规格与品牌收尾；不要绘制四块硬边界。"
            "如果素材中有多个模特，只选择一位最适合商业展示的模特放在最上方首屏，保持人物身份、脸部、发型和服饰一致，不得重复人物。"
            "画布背景必须是完全均匀的纯色 #00FF00 绿幕，无渐变、纹理、阴影、地面、反光、边框和水印。"
            "商品主体、标题文字、卖点文字、图标、徽章和装饰素材都必须作为彼此独立的视觉元素放在画布中，"
            "按照最终 A+ 成品中的准确视觉位置进行排版，但任何两个可编辑元素都不能接触、重叠或被阴影连接，元素之间至少保留 32px 纯绿间距。"
            "同一段文字可以作为一个完整元素，但不同文字块必须分开；不要生成跨越多个元素的底板、分栏线或大面积装饰背景。"
            "只使用上传图片中真实存在的商品、人物、品牌、参数和卖点，不要加入无关商品，不得编造文案、功效、认证或规格。"
            "所有文字、Logo、人物、商品和装饰必须完整位于画布内，上下左右均不得被截断。"
            "必须以原生 4K 高清质量绘制，商品纹理、睫毛丝、人物五官和所有文字边缘都要清晰锐利；"
            "禁止模糊、虚焦、低分辨率、涂抹感、过度降噪、像素化、压缩痕迹和不可辨认的小字。"
            "所有元素边缘必须清晰，不得带绿色描边或绿色光晕。最终只输出 1 张绿幕元素底稿，系统会自动加入独立商业背景层并导出可编辑 PSD。"
            + A_PLUS_PRODUCT_LOCK_RULES
        ),
    },
]

FEATURES.extend(seedream_feature_definitions(ARK_SEEDREAM_5_PRO_MODEL))

FEATURE_NAME_OVERRIDES = {
    "hd_batch": "批量高清",
}
for _feature in FEATURES:
    _feature_key = str(_feature.get("key") or "").strip()
    if _feature_key in FEATURE_NAME_OVERRIDES:
        _feature["name"] = FEATURE_NAME_OVERRIDES[_feature_key]


FEATURE_DISPLAY_ORDER = {
    "hd_batch": 0,
    JIMENG_HD_FEATURE_KEY: 1,
    "image_resize": 1,
    A_PLUS_STYLE_MODEL_REPLACE_FEATURE_KEY: 1,
    "infinite_canvas": 2,
    "product_retouch": 3,
    "product_retouch_local": 4,
    "background_cutout": 3,
}
FEATURES.sort(
    key=lambda feature: FEATURE_DISPLAY_ORDER.get(
        str(feature.get("key") or "").strip(),
        1,
    )
)


def get_feature_by_key(feature_key: str) -> dict[str, Any] | None:
    return _model_choices.get_feature_by_key(feature_key, FEATURES=FEATURES)


def get_visible_features() -> list[dict[str, Any]]:
    return _model_choices.get_visible_features(FEATURES=FEATURES)




def get_main_image_a_plus_layout(layout_key: str | None=None) -> dict[str, Any]:
    return _layout_selection.get_main_image_a_plus_layout(
        layout_key,
        MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY=MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY,
        MAIN_IMAGE_A_PLUS_LAYOUTS=MAIN_IMAGE_A_PLUS_LAYOUTS,
    )


def infer_main_image_a_plus_screen_count(canvas_size: tuple[int, int]) -> int:
    return _a_plus_layout_rules.infer_main_image_a_plus_screen_count(
        canvas_size,
        MAIN_IMAGE_A_PLUS_DESKTOP_SCREEN_HEIGHT=MAIN_IMAGE_A_PLUS_DESKTOP_SCREEN_HEIGHT,
        MAIN_IMAGE_A_PLUS_MAX_MOBILE_SCREENS=MAIN_IMAGE_A_PLUS_MAX_MOBILE_SCREENS,
        MAIN_IMAGE_A_PLUS_MIN_MOBILE_SCREENS=MAIN_IMAGE_A_PLUS_MIN_MOBILE_SCREENS,
        math=math,
    )


def get_main_image_a_plus_mobile_layout_for_source(source_size: tuple[int, int]) -> dict[str, Any]:
    return _a_plus_layout_rules.get_main_image_a_plus_mobile_layout_for_source(
        source_size,
        MAIN_IMAGE_A_PLUS_LAYOUTS=MAIN_IMAGE_A_PLUS_LAYOUTS,
        MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT=MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT,
        get_main_image_a_plus_layout=get_main_image_a_plus_layout,
        infer_main_image_a_plus_screen_count=infer_main_image_a_plus_screen_count,
    )


def is_main_image_a_plus_mobile_size(canvas_size: tuple[int, int]) -> bool:
    return _layout_selection.is_main_image_a_plus_mobile_size(canvas_size, infer_main_image_a_plus_screen_count=infer_main_image_a_plus_screen_count)


def select_main_image_a_plus_safe_aspect_ratio(canvas_size: tuple[int, int]) -> str:
    return _a_plus_layout_rules.select_main_image_a_plus_safe_aspect_ratio(
        canvas_size,
        GEMINI_IMAGE_ASPECT_RATIOS=GEMINI_IMAGE_ASPECT_RATIOS,
        re=re,
    )


def select_main_image_a_plus_vertical_preserving_aspect_ratio(canvas_size: tuple[int, int]) -> str:
    return _layout_selection.select_main_image_a_plus_vertical_preserving_aspect_ratio(canvas_size, select_main_image_a_plus_safe_aspect_ratio=select_main_image_a_plus_safe_aspect_ratio)


def get_main_image_a_plus_native_safe_zones(layout: dict[str, Any], request_aspect_ratio: str | None=None) -> dict[str, Any]:
    return _main_image_a_plus_image_tools.get_main_image_a_plus_native_safe_zones(
        layout,
        request_aspect_ratio,
        math=math,
        re=re,
        select_main_image_a_plus_safe_aspect_ratio=select_main_image_a_plus_safe_aspect_ratio,
    )


def build_main_image_a_plus_canvas_safety_instruction(layout: dict[str, Any], request_aspect_ratio: str | None=None) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_canvas_safety_instruction(
        layout,
        request_aspect_ratio,
        get_main_image_a_plus_native_safe_zones=get_main_image_a_plus_native_safe_zones,
    )


def get_main_image_a_plus_template_layout(template_input: Any) -> dict[str, Any]:
    return _main_image_a_plus_image_tools.get_main_image_a_plus_template_layout(
        template_input,
        AMAZON_A_PLUS_MAX_EDGE=AMAZON_A_PLUS_MAX_EDGE,
        AMAZON_A_PLUS_MAX_PIXELS=AMAZON_A_PLUS_MAX_PIXELS,
        Image=Image,
        ImageOps=ImageOps,
        MAIN_IMAGE_A_PLUS_SECTION_COUNT=MAIN_IMAGE_A_PLUS_SECTION_COUNT,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        io=io,
    )


def normalize_main_image_a_plus_mode(mode: str | None=None) -> str:
    return _layout_selection.normalize_main_image_a_plus_mode(
        mode,
        MAIN_IMAGE_A_PLUS_MODE_FREE=MAIN_IMAGE_A_PLUS_MODE_FREE,
        MAIN_IMAGE_A_PLUS_MODE_LABELS=MAIN_IMAGE_A_PLUS_MODE_LABELS,
    )


def get_main_image_a_plus_template_signature(template_input: Any) -> str:
    return _layout_selection.get_main_image_a_plus_template_signature(
        template_input,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        hashlib=hashlib,
    )


def normalize_main_image_a_plus_element_bbox(raw_bbox: Any, image_size: tuple[int, int]) -> list[int] | None:
    return _main_image_a_plus_image_tools.normalize_main_image_a_plus_element_bbox(raw_bbox, image_size)


def parse_main_image_a_plus_element_analysis(response_text: str, image_size: tuple[int, int]) -> list[dict[str, Any]]:
    return _main_image_a_plus_elements.parse_main_image_a_plus_element_analysis(
        response_text,
        image_size,
        Any=Any,
        MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS=MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS,
        json=json,
        normalize_main_image_a_plus_element_bbox=normalize_main_image_a_plus_element_bbox,
        re=re,
    )


def analyze_main_image_a_plus_elements(template_input: Any) -> list[dict[str, Any]]:
    return _main_image_a_plus_image_tools.analyze_main_image_a_plus_elements(
        template_input,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS=MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS,
        call_openrouter=call_openrouter,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        parse_main_image_a_plus_element_analysis=parse_main_image_a_plus_element_analysis,
    )


def parse_main_image_a_plus_replacement_matches(response_text: str, elements: list[dict[str, Any]], replacement_count: int, replacement_sizes: list[tuple[int, int]] | None=None) -> list[dict[str, Any]]:
    return _main_image_a_plus_elements.parse_main_image_a_plus_replacement_matches(
        response_text,
        elements,
        replacement_count,
        replacement_sizes,
        Any=Any,
        json=json,
        normalize_main_image_a_plus_element_bbox=normalize_main_image_a_plus_element_bbox,
        re=re,
    )


def analyze_main_image_a_plus_replacement_matches(template_input: Any, elements: list[dict[str, Any]], replacement_inputs: list[Any]) -> list[dict[str, Any]]:
    return _main_image_a_plus_elements.analyze_main_image_a_plus_replacement_matches(
        template_input,
        elements,
        replacement_inputs,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        call_openrouter=call_openrouter,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        parse_main_image_a_plus_replacement_matches=parse_main_image_a_plus_replacement_matches,
    )


def crop_main_image_a_plus_replacement_input(replacement_input: Any, crop_box: Any, element_id: int, element_name: str) -> dict[str, Any] | None:
    return _main_image_a_plus_image_tools.crop_main_image_a_plus_replacement_input(
        replacement_input,
        crop_box,
        element_id,
        element_name,
        Image=Image,
        ImageOps=ImageOps,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        io=io,
        math=math,
        normalize_main_image_a_plus_element_bbox=normalize_main_image_a_plus_element_bbox,
        sanitize_file_name=sanitize_file_name,
    )


def find_main_image_a_plus_element_at_point(elements: list[dict[str, Any]], point: tuple[int, int]) -> dict[str, Any] | None:
    return _a_plus_layout_rules.find_main_image_a_plus_element_at_point(
        elements,
        point,
        Any=Any,
    )


def analyze_main_image_a_plus_element_at_point(template_input: Any, point: tuple[int, int], existing_elements: list[dict[str, Any]]) -> dict[str, Any]:
    return _main_image_a_plus_image_tools.analyze_main_image_a_plus_element_at_point(
        template_input,
        point,
        existing_elements,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS=MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS,
        call_openrouter=call_openrouter,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        parse_main_image_a_plus_element_analysis=parse_main_image_a_plus_element_analysis,
    )


def consume_main_image_a_plus_manual_point(template_signature: str) -> tuple[int, int] | None:
    return _a_plus_layout_rules.consume_main_image_a_plus_manual_point(
        template_signature,
        MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY=MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY,
        clear_query_param=clear_query_param,
        json=json,
        st=st,
    )


def build_main_image_a_plus_element_preview(template_input: Any, elements: list[dict[str, Any]]) -> str:
    return _main_image_a_plus_editor.build_main_image_a_plus_element_preview(
        template_input,
        elements,
        Image=Image,
        ImageDraw=ImageDraw,
        ImageFont=ImageFont,
        ImageOps=ImageOps,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
    )


def render_main_image_a_plus_manual_element_picker(annotated_preview: str, template_signature: str, component_key: str) -> None:
    return _main_image_a_plus_image_tools.render_main_image_a_plus_manual_element_picker(
        annotated_preview,
        template_signature,
        component_key,
        MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY=MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY,
        json=json,
        re=re,
        st=st,
    )


def get_main_image_a_plus_text_edit_signature(source_image: str) -> str:
    return _layout_selection.get_main_image_a_plus_text_edit_signature(source_image, hashlib=hashlib)


def consume_main_image_a_plus_text_edit_point(source_signature: str) -> tuple[int, int] | None:
    return _a_plus_layout_rules.consume_main_image_a_plus_text_edit_point(
        source_signature,
        MAIN_IMAGE_A_PLUS_TEXT_POINT_QUERY_KEY=MAIN_IMAGE_A_PLUS_TEXT_POINT_QUERY_KEY,
        clear_query_param=clear_query_param,
        json=json,
        st=st,
    )


def render_main_image_a_plus_text_edit_picker(source_image: str, source_signature: str, selected_point: tuple[int, int] | None, component_key: str) -> None:
    return _main_image_a_plus_elements.render_main_image_a_plus_text_edit_picker(
        source_image,
        source_signature,
        selected_point,
        component_key,
        MAIN_IMAGE_A_PLUS_TEXT_POINT_QUERY_KEY=MAIN_IMAGE_A_PLUS_TEXT_POINT_QUERY_KEY,
        json=json,
        re=re,
        st=st,
    )


def build_main_image_a_plus_text_edit_prompt(point: tuple[int, int], replacement_text: str, font_name: str) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_text_edit_prompt(
        point,
        replacement_text,
        font_name,
        json=json,
    )


def build_main_image_a_plus_element_replacement_notes(layout: dict[str, Any], detected_element_count: int, replacements: list[dict[str, Any]]) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_element_replacement_notes(
        layout,
        detected_element_count,
        replacements,
        A_PLUS_PRODUCT_LOCK_RULES=A_PLUS_PRODUCT_LOCK_RULES,
    )


def build_main_image_a_plus_element_replacement_prompt(full_prompt: str, layout: dict[str, Any], replacements: list[dict[str, Any]]) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_element_replacement_prompt(
        full_prompt,
        layout,
        replacements,
        A_PLUS_PRODUCT_LOCK_RULES=A_PLUS_PRODUCT_LOCK_RULES,
    )


def build_main_image_a_plus_layout_notes(layout_key: str, image_count: int) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_layout_notes(
        layout_key,
        image_count,
        A_PLUS_PRODUCT_LOCK_RULES=A_PLUS_PRODUCT_LOCK_RULES,
        get_main_image_a_plus_layout=get_main_image_a_plus_layout,
    )


def build_main_image_a_plus_free_prompt(full_prompt: str, layout: dict[str, Any], has_layout_skeleton: bool=False, style_reference_count: int=0, source_pool_only: bool=False) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_free_prompt(
        full_prompt,
        layout,
        has_layout_skeleton,
        style_reference_count,
        source_pool_only,
        A_PLUS_PRODUCT_LOCK_RULES=A_PLUS_PRODUCT_LOCK_RULES,
        A_PLUS_UPLOAD_POOL_LOCK_RULES=A_PLUS_UPLOAD_POOL_LOCK_RULES,
        build_main_image_a_plus_canvas_safety_instruction=build_main_image_a_plus_canvas_safety_instruction,
        select_main_image_a_plus_safe_aspect_ratio=select_main_image_a_plus_safe_aspect_ratio,
    )


def build_main_image_a_plus_hero_design_prompt(full_prompt: str, layout: dict[str, Any], has_layout_skeleton: bool=False, style_reference_count: int=0) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_hero_design_prompt(
        full_prompt,
        layout,
        has_layout_skeleton,
        style_reference_count,
        build_main_image_a_plus_free_prompt=build_main_image_a_plus_free_prompt,
    )


def analyze_main_image_a_plus_mobile_element_inventory(source_input: Any) -> list[dict[str, Any]]:
    return _main_image_a_plus_sources.analyze_main_image_a_plus_mobile_element_inventory(
        source_input,
        Any=Any,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        _extract_strict_json_object=_extract_strict_json_object,
        call_openrouter=call_openrouter,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        normalize_main_image_a_plus_element_bbox=normalize_main_image_a_plus_element_bbox,
    )


def format_main_image_a_plus_mobile_element_inventory(elements: list[dict[str, Any]]) -> str:
    return _main_image_a_plus_sources.format_main_image_a_plus_mobile_element_inventory(elements, json=json)


def build_main_image_a_plus_mobile_safe_margin_instruction(elements: list[dict[str, Any]], mobile_layout: dict[str, Any] | None=None) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_mobile_safe_margin_instruction(elements, mobile_layout)


def build_main_image_a_plus_mobile_adaptation_prompt(element_inventory: str='', safe_margin_instruction: str='', mobile_layout: dict[str, Any] | None=None, reference_pair_count: int=0) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_mobile_adaptation_prompt(
        element_inventory,
        safe_margin_instruction,
        mobile_layout,
        reference_pair_count,
        MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT=MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT,
        MAIN_IMAGE_A_PLUS_MOBILE_SOURCE_LOCK_RULES=MAIN_IMAGE_A_PLUS_MOBILE_SOURCE_LOCK_RULES,
        get_main_image_a_plus_layout=get_main_image_a_plus_layout,
    )


def detect_main_image_a_plus_outer_blank_borders(candidate_bytes: bytes) -> list[str]:
    return _main_image_a_plus_elements.detect_main_image_a_plus_outer_blank_borders(
        candidate_bytes,
        Image=Image,
        ImageOps=ImageOps,
        ImageStat=ImageStat,
        io=io,
    )


def is_main_image_a_plus_permitted_photographic_bleed_issue(issue: Any) -> bool:
    return _main_image_a_plus_image_tools.is_main_image_a_plus_permitted_photographic_bleed_issue(issue)


def review_main_image_a_plus_candidate(candidate_image: str, layout: dict[str, Any], mode: str, source_inputs: list[Any] | None=None, expected_element_inventory: str='', designed_module_pipeline: bool=False, expected_section_count: int=0, strict_visual_quality: bool=False, multi_visual_centers: bool=False) -> dict[str, Any]:
    return _main_image_a_plus_quality.review_main_image_a_plus_candidate(
        candidate_image,
        layout,
        mode,
        source_inputs,
        expected_element_inventory,
        designed_module_pipeline,
        expected_section_count,
        strict_visual_quality,
        multi_visual_centers,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        MAIN_IMAGE_A_PLUS_MAX_FILES=MAIN_IMAGE_A_PLUS_MAX_FILES,
        MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT=MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT,
        MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT=MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT,
        MAIN_IMAGE_A_PLUS_QUALITY_REVIEW_MODEL=MAIN_IMAGE_A_PLUS_QUALITY_REVIEW_MODEL,
        _extract_strict_json_object=_extract_strict_json_object,
        call_openrouter=call_openrouter,
        detect_main_image_a_plus_outer_blank_borders=detect_main_image_a_plus_outer_blank_borders,
        is_main_image_a_plus_permitted_photographic_bleed_issue=is_main_image_a_plus_permitted_photographic_bleed_issue,
        load_image_bytes_from_url=load_image_bytes_from_url,
        prepare_main_image_a_plus_reference_input=prepare_main_image_a_plus_reference_input,
        re=re,
    )


def build_main_image_a_plus_quality_retry_instruction(review: dict[str, Any], multi_visual_centers: bool=False) -> str:
    return _main_image_a_plus_quality.build_main_image_a_plus_quality_retry_instruction(review, multi_visual_centers)


def build_main_image_a_plus_free_quality_repair_prompt(full_prompt: str, layout: dict[str, Any], review: dict[str, Any], source_reference_count: int, source_pool_only: bool=False) -> str:
    return _main_image_a_plus_quality.build_main_image_a_plus_free_quality_repair_prompt(
        full_prompt,
        layout,
        review,
        source_reference_count,
        source_pool_only,
        A_PLUS_PRODUCT_LOCK_RULES=A_PLUS_PRODUCT_LOCK_RULES,
        A_PLUS_UPLOAD_POOL_LOCK_RULES=A_PLUS_UPLOAD_POOL_LOCK_RULES,
        build_main_image_a_plus_canvas_safety_instruction=build_main_image_a_plus_canvas_safety_instruction,
        build_main_image_a_plus_quality_retry_instruction=build_main_image_a_plus_quality_retry_instruction,
        select_main_image_a_plus_safe_aspect_ratio=select_main_image_a_plus_safe_aspect_ratio,
    )


def build_main_image_a_plus_quality_recovery_advice(review: dict[str, Any]) -> str:
    return _main_image_a_plus_quality.build_main_image_a_plus_quality_recovery_advice(review)


def collect_main_image_a_plus_quality_issues(review: dict[str, Any]) -> list[str]:
    return _main_image_a_plus_quality.collect_main_image_a_plus_quality_issues(review)


def select_main_image_a_plus_crop_anchors(review: dict[str, Any] | None) -> tuple[str, str]:
    return _main_image_a_plus_quality.select_main_image_a_plus_crop_anchors(review, collect_main_image_a_plus_quality_issues=collect_main_image_a_plus_quality_issues)


def collect_main_image_a_plus_severe_subject_clips(review: dict[str, Any]) -> list[str]:
    return _main_image_a_plus_quality.collect_main_image_a_plus_severe_subject_clips(review, is_main_image_a_plus_permitted_photographic_bleed_issue=is_main_image_a_plus_permitted_photographic_bleed_issue)


def build_main_image_a_plus_mobile_repair_prompt(layout: dict[str, Any], element_inventory: str, safe_margin_instruction: str, review: dict[str, Any]) -> str:
    return _main_image_a_plus_quality.build_main_image_a_plus_mobile_repair_prompt(
        layout,
        element_inventory,
        safe_margin_instruction,
        review,
        MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT=MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT,
        build_main_image_a_plus_quality_retry_instruction=build_main_image_a_plus_quality_retry_instruction,
    )


def rank_main_image_a_plus_quality_review(review: dict[str, Any]) -> tuple[int, int, float]:
    return _main_image_a_plus_quality.rank_main_image_a_plus_quality_review(review)


def build_main_image_a_plus_section_prompt(full_prompt: str, layout: dict[str, Any], section_index: int, has_previous_section_reference: bool=False, continuity_reference_role: str='') -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_section_prompt(
        full_prompt,
        layout,
        section_index,
        has_previous_section_reference,
        continuity_reference_role,
        A_PLUS_PRODUCT_LOCK_RULES=A_PLUS_PRODUCT_LOCK_RULES,
        MAIN_IMAGE_A_PLUS_SECTION_PURPOSES=MAIN_IMAGE_A_PLUS_SECTION_PURPOSES,
    )


def build_main_image_a_plus_template_notes(layout_or_key: dict[str, Any] | str, image_count: int) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_template_notes(
        layout_or_key,
        image_count,
        A_PLUS_PRODUCT_LOCK_RULES=A_PLUS_PRODUCT_LOCK_RULES,
        get_main_image_a_plus_layout=get_main_image_a_plus_layout,
    )


def build_main_image_a_plus_single_test_notes(layout_or_key: dict[str, Any] | str, image_count: int) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_single_test_notes(
        layout_or_key,
        image_count,
        A_PLUS_PRODUCT_LOCK_RULES=A_PLUS_PRODUCT_LOCK_RULES,
        get_main_image_a_plus_layout=get_main_image_a_plus_layout,
    )


def build_main_image_a_plus_single_test_prompt(full_prompt: str, layout: dict[str, Any]) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_single_test_prompt(
        full_prompt,
        layout,
        A_PLUS_PRODUCT_LOCK_RULES=A_PLUS_PRODUCT_LOCK_RULES,
    )


def build_main_image_a_plus_template_section_prompt(full_prompt: str, layout: dict[str, Any], section_index: int) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_template_section_prompt(
        full_prompt,
        layout,
        section_index,
        A_PLUS_PRODUCT_LOCK_RULES=A_PLUS_PRODUCT_LOCK_RULES,
        MAIN_IMAGE_A_PLUS_SECTION_COUNT=MAIN_IMAGE_A_PLUS_SECTION_COUNT,
    )


def _extract_strict_json_object(response_text: str, empty_message: str) -> dict[str, Any]:
    return _a_plus_layout_rules._extract_strict_json_object(
        response_text,
        empty_message,
        json=json,
        re=re,
    )


def _layout_skill_text(value: Any, max_length: int=240) -> str:
    return _layout_selection._layout_skill_text(
        value,
        max_length,
        re=re,
    )


def _layout_skill_string_list(value: Any, max_items: int=12) -> list[str]:
    return _a_plus_layout_rules._layout_skill_string_list(
        value,
        max_items,
        _layout_skill_text=_layout_skill_text,
        re=re,
    )


def _layout_skill_ratio(value: Any, default: float=0.0) -> float:
    return _layout_selection._layout_skill_ratio(value, default)


def _layout_skill_int(value: Any, default: int=0, minimum: int=0, maximum: int=100) -> int:
    return _layout_selection._layout_skill_int(
        value,
        default,
        minimum,
        maximum,
    )


def _layout_skill_bbox(value: Any) -> list[int]:
    return _layout_selection._layout_skill_bbox(value, normalize_main_image_a_plus_element_bbox=normalize_main_image_a_plus_element_bbox)


def _normalize_layout_skill_elements(value: Any, max_items: int=24) -> list[dict[str, Any]]:
    return _a_plus_layout_rules._normalize_layout_skill_elements(
        value,
        max_items,
        Any=Any,
        _layout_skill_bbox=_layout_skill_bbox,
        _layout_skill_text=_layout_skill_text,
    )


def _normalize_layout_skill_sections(value: Any) -> list[dict[str, Any]]:
    return _feature_helpers._normalize_layout_skill_sections(
        value,
        Any=Any,
        _layout_skill_bbox=_layout_skill_bbox,
        _layout_skill_ratio=_layout_skill_ratio,
        _layout_skill_text=_layout_skill_text,
        _normalize_layout_skill_elements=_normalize_layout_skill_elements,
    )


def _normalize_layout_skill_hero(value: Any) -> dict[str, Any]:
    return _a_plus_layout_rules._normalize_layout_skill_hero(
        value,
        _layout_skill_int=_layout_skill_int,
        _layout_skill_ratio=_layout_skill_ratio,
        _layout_skill_text=_layout_skill_text,
        _normalize_layout_skill_elements=_normalize_layout_skill_elements,
    )


def _normalize_layout_skill_common(value: Any) -> dict[str, Any]:
    return _feature_helpers._normalize_layout_skill_common(
        value,
        _layout_skill_int=_layout_skill_int,
        _layout_skill_string_list=_layout_skill_string_list,
        _layout_skill_text=_layout_skill_text,
        _normalize_layout_skill_hero=_normalize_layout_skill_hero,
        _normalize_layout_skill_sections=_normalize_layout_skill_sections,
        re=re,
    )


def normalize_a_plus_layout_skill_analysis(payload: dict[str, Any], case_inputs: list[Any]) -> dict[str, Any]:
    return _layout_skills.normalize_a_plus_layout_skill_analysis(
        payload,
        case_inputs,
        A_PLUS_SKILL_SCHEMA_VERSION=A_PLUS_SKILL_SCHEMA_VERSION,
        Any=Any,
        _layout_skill_string_list=_layout_skill_string_list,
        _layout_skill_text=_layout_skill_text,
        _normalize_layout_skill_common=_normalize_layout_skill_common,
        _normalize_layout_skill_elements=_normalize_layout_skill_elements,
        _normalize_layout_skill_hero=_normalize_layout_skill_hero,
        _normalize_layout_skill_sections=_normalize_layout_skill_sections,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
    )


def build_a_plus_layout_analysis_prompt(case_inputs: list[Any], previous_common: dict[str, Any] | None=None) -> str:
    return _feature_helpers.build_a_plus_layout_analysis_prompt(
        case_inputs,
        previous_common,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        json=json,
    )


def analyze_a_plus_layout_cases(case_inputs: list[Any], previous_common: dict[str, Any] | None=None) -> dict[str, Any]:
    return _a_plus_layout_rules.analyze_a_plus_layout_cases(
        case_inputs,
        previous_common,
        A_PLUS_SKILL_MAX_CASES=A_PLUS_SKILL_MAX_CASES,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        _extract_strict_json_object=_extract_strict_json_object,
        build_a_plus_layout_analysis_prompt=build_a_plus_layout_analysis_prompt,
        call_openrouter=call_openrouter,
        normalize_a_plus_layout_skill_analysis=normalize_a_plus_layout_skill_analysis,
    )


def build_a_plus_layout_skill_prompt(analysis: dict[str, Any]) -> str:
    return _layout_skills.build_a_plus_layout_skill_prompt(
        analysis,
        A_PLUS_PRODUCT_LOCK_RULES=A_PLUS_PRODUCT_LOCK_RULES,
        _layout_skill_string_list=_layout_skill_string_list,
    )


def build_a_plus_layout_skeleton_image(analysis: dict[str, Any]) -> bytes:
    return _layout_skills.build_a_plus_layout_skeleton_image(
        analysis,
        Image=Image,
        ImageDraw=ImageDraw,
        _layout_skill_bbox=_layout_skill_bbox,
        io=io,
    )


def normalize_a_plus_layout_skill_account(account_name: str) -> str:
    return _layout_skills.normalize_a_plus_layout_skill_account(account_name)


def list_builtin_a_plus_layout_skills() -> list[dict[str, Any]]:
    return _layout_skills.list_builtin_a_plus_layout_skills(
        A_PLUS_SHOP_STYLE_SKILL_CATALOG=A_PLUS_SHOP_STYLE_SKILL_CATALOG,
        A_PLUS_SKILL_DB_TYPE=A_PLUS_SKILL_DB_TYPE,
        A_PLUS_SKILL_MAX_CASES=A_PLUS_SKILL_MAX_CASES,
        A_PLUS_SKILL_SCHEMA_VERSION=A_PLUS_SKILL_SCHEMA_VERSION,
        Any=Any,
        _layout_skill_string_list=_layout_skill_string_list,
        _layout_skill_text=_layout_skill_text,
        build_a_plus_layout_skill_prompt=build_a_plus_layout_skill_prompt,
        json=json,
    )


def get_a_plus_layout_skill_user_pointer_path(account_name: str) -> Path:
    return _layout_skills.get_a_plus_layout_skill_user_pointer_path(
        account_name,
        A_PLUS_SKILL_ROOT=A_PLUS_SKILL_ROOT,
        hashlib=hashlib,
        normalize_a_plus_layout_skill_account=normalize_a_plus_layout_skill_account,
    )


def register_a_plus_layout_skill_in_db(created_at: datetime, account_name: str) -> None:
    return _layout_skills.register_a_plus_layout_skill_in_db(
        created_at,
        account_name,
        A_PLUS_SKILL_DB_TYPE=A_PLUS_SKILL_DB_TYPE,
        A_PLUS_SKILL_ROOT=A_PLUS_SKILL_ROOT,
        execute_db_non_query=execute_db_non_query,
        normalize_a_plus_layout_skill_account=normalize_a_plus_layout_skill_account,
    )


def list_a_plus_layout_skills(account_name: str) -> list[dict[str, Any]]:
    return _layout_skills.list_a_plus_layout_skills(
        account_name,
        A_PLUS_SKILL_DB_TYPE=A_PLUS_SKILL_DB_TYPE,
        A_PLUS_SKILL_ROOT=A_PLUS_SKILL_ROOT,
        Any=Any,
        json=json,
        normalize_a_plus_layout_skill_account=normalize_a_plus_layout_skill_account,
    )


def list_available_a_plus_layout_skills(account_name: str) -> list[dict[str, Any]]:
    return _layout_skills.list_available_a_plus_layout_skills(
        account_name,
        list_a_plus_layout_skills=list_a_plus_layout_skills,
        list_builtin_a_plus_layout_skills=list_builtin_a_plus_layout_skills,
    )


def load_latest_a_plus_layout_skill(account_name: str='admin') -> dict[str, Any]:
    return _layout_skills.load_latest_a_plus_layout_skill(account_name, list_a_plus_layout_skills=list_a_plus_layout_skills)


def load_a_plus_layout_skill(account_name: str, skill_id: str) -> dict[str, Any]:
    return _layout_skills.load_a_plus_layout_skill(
        account_name,
        skill_id,
        list_a_plus_layout_skills=list_a_plus_layout_skills,
        list_builtin_a_plus_layout_skills=list_builtin_a_plus_layout_skills,
    )


def parse_a_plus_layout_skill_created_date(manifest: dict[str, Any]) -> date:
    return _layout_skills.parse_a_plus_layout_skill_created_date(
        manifest,
        Path=Path,
        datetime=datetime,
    )


def update_a_plus_layout_skill_user_pointer(account_name: str) -> None:
    return _layout_skills.update_a_plus_layout_skill_user_pointer(
        account_name,
        datetime=datetime,
        get_a_plus_layout_skill_user_pointer_path=get_a_plus_layout_skill_user_pointer_path,
        json=json,
        load_latest_a_plus_layout_skill=load_latest_a_plus_layout_skill,
        normalize_a_plus_layout_skill_account=normalize_a_plus_layout_skill_account,
    )


def delete_a_plus_layout_skill(account_name: str, skill_id: str) -> dict[str, Any]:
    return _layout_skills.delete_a_plus_layout_skill(
        account_name,
        skill_id,
        A_PLUS_SKILL_DB_TYPE=A_PLUS_SKILL_DB_TYPE,
        A_PLUS_SKILL_ROOT=A_PLUS_SKILL_ROOT,
        Path=Path,
        execute_db_non_query=execute_db_non_query,
        load_a_plus_layout_skill=load_a_plus_layout_skill,
        normalize_a_plus_layout_skill_account=normalize_a_plus_layout_skill_account,
        parse_a_plus_layout_skill_created_date=parse_a_plus_layout_skill_created_date,
        shutil=shutil,
        update_a_plus_layout_skill_user_pointer=update_a_plus_layout_skill_user_pointer,
        uuid4=uuid4,
    )


def save_a_plus_layout_skill(case_inputs: list[Any], analysis: dict[str, Any], title: str='', account_name: str='admin') -> dict[str, Any]:
    return _layout_skills.save_a_plus_layout_skill(
        case_inputs,
        analysis,
        title,
        account_name,
        A_PLUS_SKILL_DB_TYPE=A_PLUS_SKILL_DB_TYPE,
        A_PLUS_SKILL_MAX_CASES=A_PLUS_SKILL_MAX_CASES,
        A_PLUS_SKILL_ROOT=A_PLUS_SKILL_ROOT,
        A_PLUS_SKILL_SCHEMA_VERSION=A_PLUS_SKILL_SCHEMA_VERSION,
        Any=Any,
        Path=Path,
        _layout_skill_text=_layout_skill_text,
        build_a_plus_layout_skeleton_image=build_a_plus_layout_skeleton_image,
        build_a_plus_layout_skill_prompt=build_a_plus_layout_skill_prompt,
        datetime=datetime,
        get_a_plus_layout_skill_user_pointer_path=get_a_plus_layout_skill_user_pointer_path,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        get_uploaded_file_name=get_uploaded_file_name,
        hashlib=hashlib,
        json=json,
        load_latest_a_plus_layout_skill=load_latest_a_plus_layout_skill,
        normalize_a_plus_layout_skill_account=normalize_a_plus_layout_skill_account,
        register_a_plus_layout_skill_in_db=register_a_plus_layout_skill_in_db,
        sanitize_file_name=sanitize_file_name,
    )


def create_a_plus_layout_skill(case_inputs: list[Any], title: str='', account_name: str='admin') -> dict[str, Any]:
    return _layout_skills.create_a_plus_layout_skill(
        case_inputs,
        title,
        account_name,
        analyze_a_plus_layout_cases=analyze_a_plus_layout_cases,
        load_latest_a_plus_layout_skill=load_latest_a_plus_layout_skill,
        normalize_a_plus_layout_skill_account=normalize_a_plus_layout_skill_account,
        save_a_plus_layout_skill=save_a_plus_layout_skill,
    )


def get_active_a_plus_layout_skill_context(account_name: str='admin', selected_skill_id: str | None=None) -> dict[str, Any]:
    return _layout_skills.get_active_a_plus_layout_skill_context(
        account_name,
        selected_skill_id,
        Any=Any,
        Path=Path,
        build_a_plus_layout_skeleton_image=build_a_plus_layout_skeleton_image,
        load_a_plus_layout_skill=load_a_plus_layout_skill,
        load_latest_a_plus_layout_skill=load_latest_a_plus_layout_skill,
    )


def get_main_image_a_plus_layout_device(layout: dict[str, Any] | str | None) -> str:
    return _a_plus_layout_rules.get_main_image_a_plus_layout_device(layout)


def resolve_a_plus_layout_skill_context_for_layout(context: dict[str, Any] | None, layout: dict[str, Any] | str | None, *, account_name: str='admin') -> dict[str, Any]:
    return _layout_skills.resolve_a_plus_layout_skill_context_for_layout(
        context,
        layout,
        account_name=account_name,
        get_active_a_plus_layout_skill_context=get_active_a_plus_layout_skill_context,
        get_main_image_a_plus_layout_device=get_main_image_a_plus_layout_device,
        list_builtin_a_plus_layout_skills=list_builtin_a_plus_layout_skills,
    )


def render_a_plus_layout_skill_builder(feature_key: str, account_name: str, target_layout: dict[str, Any] | str | None=None) -> dict[str, Any]:
    return _main_image_a_plus_editor.render_a_plus_layout_skill_builder(
        feature_key,
        account_name,
        target_layout,
        Path=Path,
        delete_a_plus_layout_skill=delete_a_plus_layout_skill,
        format_user_facing_error_message=format_user_facing_error_message,
        get_active_a_plus_layout_skill_context=get_active_a_plus_layout_skill_context,
        get_main_image_a_plus_layout_device=get_main_image_a_plus_layout_device,
        hashlib=hashlib,
        html=html,
        list_available_a_plus_layout_skills=list_available_a_plus_layout_skills,
        normalize_a_plus_layout_skill_account=normalize_a_plus_layout_skill_account,
        st=st,
    )


def get_infinite_canvas_step_features() -> list[dict[str, Any]]:
    return _model_choices.get_infinite_canvas_step_features(INFINITE_CANVAS_STEP_FEATURE_KEYS=INFINITE_CANVAS_STEP_FEATURE_KEYS, get_feature_by_key=get_feature_by_key)


def load_config_namespace() -> dict[str, Any]:
    return _runtime_config.load_config_namespace(
        APP_DIR=APP_DIR,
        Any=Any,
        image_site_config_namespace=image_site_config_namespace,
        os=os,
    )


def load_api_key() -> str:
    return _runtime_config.load_api_key(load_config_namespace=load_config_namespace, os=os)


def load_omnia_api_key() -> str:
    return _runtime_config.load_omnia_api_key(
        current_omnia_credential=current_omnia_credential,
        load_config_namespace=load_config_namespace,
        os=os,
    )


def load_ark_api_key() -> str:
    return _runtime_config.load_ark_api_key(load_config_namespace=load_config_namespace, os=os)


def load_jimeng_credentials() -> tuple[str, str]:
    return _jimeng_client.load_jimeng_credentials(load_config_namespace=load_config_namespace, os=os)


def _jimeng_sha256_hex(value: str) -> str:
    return _provider_inputs._jimeng_sha256_hex(value, hashlib=hashlib)


def _jimeng_hmac_bytes(key: bytes, message: str) -> bytes:
    return _provider_inputs._jimeng_hmac_bytes(
        key,
        message,
        hashlib=hashlib,
        hmac=hmac,
    )


def _jimeng_normalize_query(params: dict[str, Any]) -> str:
    return _provider_inputs._jimeng_normalize_query(params, urllib=urllib)


def build_jimeng_auth_headers(action: str, body_text: str) -> dict[str, str]:
    return _jimeng_client.build_jimeng_auth_headers(
        action,
        body_text,
        JIMENG_API_HOST=JIMENG_API_HOST,
        JIMENG_API_REGION=JIMENG_API_REGION,
        JIMENG_API_SERVICE=JIMENG_API_SERVICE,
        JIMENG_API_VERSION=JIMENG_API_VERSION,
        _jimeng_hmac_bytes=_jimeng_hmac_bytes,
        _jimeng_normalize_query=_jimeng_normalize_query,
        _jimeng_sha256_hex=_jimeng_sha256_hex,
        datetime=datetime,
        load_config_namespace=load_config_namespace,
        load_jimeng_credentials=load_jimeng_credentials,
        timezone=timezone,
    )


def load_login_accounts() -> dict[str, str]:
    return _login_state.load_login_accounts(DEFAULT_LOGIN_ACCOUNTS=DEFAULT_LOGIN_ACCOUNTS, load_config_namespace=load_config_namespace)


def load_runtime_settings() -> dict[str, Any]:
    return _runtime_config.load_runtime_settings(
        DEFAULT_JIMENG_STATIC_PORT=DEFAULT_JIMENG_STATIC_PORT,
        DEFAULT_SERVER_ADDRESS=DEFAULT_SERVER_ADDRESS,
        DEFAULT_SERVER_PORT=DEFAULT_SERVER_PORT,
        build_jimeng_static_base_url=build_jimeng_static_base_url,
        load_config_namespace=load_config_namespace,
    )


def build_auth_token(username: str) -> str:
    return _login_state.build_auth_token(
        username,
        AUTH_TOKEN_SALT=AUTH_TOKEN_SALT,
        hashlib=hashlib,
    )


def persist_auth_session(username: str) -> None:
    return _login_state.persist_auth_session(
        username,
        AUTH_QUERY_TOKEN_KEY=AUTH_QUERY_TOKEN_KEY,
        AUTH_QUERY_USER_KEY=AUTH_QUERY_USER_KEY,
        build_auth_token=build_auth_token,
        st=st,
    )


def clear_persisted_auth_session() -> None:
    return _login_state.clear_persisted_auth_session(
        AUTH_QUERY_TOKEN_KEY=AUTH_QUERY_TOKEN_KEY,
        AUTH_QUERY_USER_KEY=AUTH_QUERY_USER_KEY,
        st=st,
    )


def get_requested_feature_key() -> str:
    return _login_state.get_requested_feature_key(FEATURE_QUERY_KEY=FEATURE_QUERY_KEY, st=st)


def select_feature(feature_key: str) -> None:
    return _login_state.select_feature(
        feature_key,
        FEATURE_QUERY_KEY=FEATURE_QUERY_KEY,
        get_requested_feature_key=get_requested_feature_key,
        st=st,
    )


def set_side_menu_visible(visible: bool) -> None:
    return _login_state.set_side_menu_visible(visible, st=st)


def clear_query_param(param_key: str) -> None:
    return _login_state.clear_query_param(param_key, st=st)


def get_requested_auth_username() -> str:
    return _login_state.get_requested_auth_username(AUTH_QUERY_USER_KEY=AUTH_QUERY_USER_KEY, st=st)


def authenticate_requested_user() -> None:
    return _login_state.authenticate_requested_user(
        AUTH_QUERY_TOKEN_KEY=AUTH_QUERY_TOKEN_KEY,
        build_auth_token=build_auth_token,
        clear_query_param=clear_query_param,
        get_requested_auth_username=get_requested_auth_username,
        persist_auth_session=persist_auth_session,
        st=st,
    )


def restore_auth_session() -> None:
    return _login_state.restore_auth_session(authenticate_requested_user=authenticate_requested_user, st=st)


def build_upload_delete_token(widget_key: str, item_index: int) -> str:
    return _upload_state.build_upload_delete_token(
        widget_key,
        item_index,
        base64=base64,
        json=json,
    )


def parse_upload_delete_token(raw_token: str) -> tuple[str, int] | None:
    return _upload_actions.parse_upload_delete_token(
        raw_token,
        base64=base64,
        json=json,
    )


def consume_pending_upload_delete() -> bool:
    return _upload_state.consume_pending_upload_delete(
        UPLOAD_DELETE_QUERY_KEY=UPLOAD_DELETE_QUERY_KEY,
        clear_query_param=clear_query_param,
        parse_upload_delete_token=parse_upload_delete_token,
        remove_upload_cache_item=remove_upload_cache_item,
        reset_upload_widget=reset_upload_widget,
        st=st,
    )


def build_upload_reorder_token(widget_key: str, source_index: int, target_index: int) -> str:
    return _upload_state.build_upload_reorder_token(
        widget_key,
        source_index,
        target_index,
        base64=base64,
        json=json,
    )


def parse_upload_reorder_token(raw_token: str) -> tuple[str, int, int] | None:
    return _upload_actions.parse_upload_reorder_token(
        raw_token,
        base64=base64,
        json=json,
    )


def consume_pending_upload_reorder() -> bool:
    return _upload_state.consume_pending_upload_reorder(
        UPLOAD_REORDER_QUERY_KEY=UPLOAD_REORDER_QUERY_KEY,
        clear_query_param=clear_query_param,
        parse_upload_reorder_token=parse_upload_reorder_token,
        reorder_upload_cache_item=reorder_upload_cache_item,
        reset_upload_widget=reset_upload_widget,
        st=st,
    )


def consume_pending_upload_replacement(widget_key: str) -> int | None:
    return _upload_state.consume_pending_upload_replacement(
        widget_key,
        UPLOAD_REPLACE_INDEX_QUERY_KEY=UPLOAD_REPLACE_INDEX_QUERY_KEY,
        UPLOAD_REPLACE_WIDGET_QUERY_KEY=UPLOAD_REPLACE_WIDGET_QUERY_KEY,
        clear_query_param=clear_query_param,
        st=st,
    )


def consume_pending_outpaint_drag() -> bool:
    return _workbench_state.consume_pending_outpaint_drag(
        OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX=OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
        OUTPAINT_DRAG_QUERY_KEY=OUTPAINT_DRAG_QUERY_KEY,
        OUTPAINT_DRAG_STEP_PX=OUTPAINT_DRAG_STEP_PX,
        OUTPAINT_FALLBACK_MAX_EXTENSION_PX=OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
        clear_query_param=clear_query_param,
        json=json,
        st=st,
    )


def get_uploader_nonce_state_key(widget_key: str) -> str:
    return _upload_state.get_uploader_nonce_state_key(widget_key)


def get_uploader_widget_key(widget_key: str) -> str:
    return _upload_state.get_uploader_widget_key(
        widget_key,
        get_uploader_nonce_state_key=get_uploader_nonce_state_key,
        st=st,
    )


def get_replace_uploader_widget_key(widget_key: str, item_index: int) -> str:
    return _upload_state.get_replace_uploader_widget_key(
        widget_key,
        item_index,
        get_uploader_nonce_state_key=get_uploader_nonce_state_key,
        st=st,
    )


def get_replace_payload_widget_key(widget_key: str, item_index: int) -> str:
    return _upload_state.get_replace_payload_widget_key(
        widget_key,
        item_index,
        get_uploader_nonce_state_key=get_uploader_nonce_state_key,
        st=st,
    )


def reset_upload_widget(widget_key: str) -> None:
    return _upload_state.reset_upload_widget(
        widget_key,
        get_uploader_nonce_state_key=get_uploader_nonce_state_key,
        get_uploader_widget_key=get_uploader_widget_key,
        st=st,
    )


def file_to_data_url(uploaded_file: Any) -> str:
    return _upload_actions.file_to_data_url(
        uploaded_file,
        Path=Path,
        base64=base64,
        mimetypes=mimetypes,
    )


def get_model_reference_files() -> list[Path]:
    return _upload_actions.get_model_reference_files(
        APP_DIR=APP_DIR,
        HD_MODEL_REFERENCE_FILE=HD_MODEL_REFERENCE_FILE,
        OUTPUTS_HD_DEFAULT_REFERENCE_FILE=OUTPUTS_HD_DEFAULT_REFERENCE_FILE,
        OUTPUTS_HD_REFERENCE_DIR=OUTPUTS_HD_REFERENCE_DIR,
        Path=Path,
        REFERENCE_IMAGE_EXTENSIONS=REFERENCE_IMAGE_EXTENSIONS,
    )


def get_skin_texture_reference_files() -> list[Path]:
    return _upload_state.get_skin_texture_reference_files(
        Path=Path,
        REFERENCE_IMAGE_EXTENSIONS=REFERENCE_IMAGE_EXTENSIONS,
        SKIN_TEXTURE_REFERENCE_DIR=SKIN_TEXTURE_REFERENCE_DIR,
    )


def ensure_state() -> None:
    return _workbench_state.ensure_state(
        Any=Any,
        XIAOHA_DEFAULT_FEATURE_KEY=XIAOHA_DEFAULT_FEATURE_KEY,
        get_requested_feature_key=get_requested_feature_key,
        st=st,
    )


def ensure_history_storage() -> None:
    return _xiaoha_history_storage.ensure_history_storage(
        DB_IMAGE_DIR=DB_IMAGE_DIR,
        UPLOAD_CACHE_DIR=UPLOAD_CACHE_DIR,
    )


def get_current_account_name() -> str:
    return _login_state.get_current_account_name(st=st)


def build_upload_cache_token(account_name: str, widget_key: str) -> str:
    return _upload_state.build_upload_cache_token(
        account_name,
        widget_key,
        hashlib=hashlib,
    )


def sanitize_file_name(file_name: str) -> str:
    return _image_primitives.sanitize_file_name(
        file_name,
        hashlib=hashlib,
        re=re,
    )


def get_upload_cache_dir(account_name: str, widget_key: str) -> Path:
    return _upload_state.get_upload_cache_dir(
        account_name,
        widget_key,
        UPLOAD_CACHE_DIR=UPLOAD_CACHE_DIR,
        build_upload_cache_token=build_upload_cache_token,
        ensure_history_storage=ensure_history_storage,
        sanitize_file_name=sanitize_file_name,
    )


def ensure_jimeng_upload_dir() -> Path:
    return _runtime_paths.ensure_jimeng_upload_dir(
        DB_IMAGE_DIR=DB_IMAGE_DIR,
        JIMENG_UPLOAD_SUBDIR=JIMENG_UPLOAD_SUBDIR,
        ensure_history_storage=ensure_history_storage,
    )


def get_jimeng_public_upload_base_url() -> str:
    return _history_paths.get_jimeng_public_upload_base_url(load_runtime_settings=load_runtime_settings)


def get_history_public_base_url() -> str:
    return _history_paths.get_history_public_base_url(
        DEFAULT_JIMENG_STATIC_PORT=DEFAULT_JIMENG_STATIC_PORT,
        DEFAULT_PUBLIC_APP_URL=DEFAULT_PUBLIC_APP_URL,
        build_history_static_base_url=build_history_static_base_url,
        load_runtime_settings=load_runtime_settings,
    )


def convert_history_path_to_public_url(image_path_text: str) -> str:
    return _xiaoha_history_storage.convert_history_path_to_public_url(
        image_path_text,
        Path=Path,
        ensure_db_image_dir=ensure_db_image_dir,
        get_history_public_base_url=get_history_public_base_url,
        relocate_storage_path=relocate_storage_path,
        urllib=urllib,
    )


def save_uploaded_inputs_for_jimeng(uploaded_files: list[Any]) -> list[str]:
    return _jimeng_uploads.save_uploaded_inputs_for_jimeng(
        uploaded_files,
        Path=Path,
        REFERENCE_IMAGE_EXTENSIONS=REFERENCE_IMAGE_EXTENSIONS,
        datetime=datetime,
        ensure_jimeng_upload_dir=ensure_jimeng_upload_dir,
        get_image_extension_from_mime=get_image_extension_from_mime,
        get_jimeng_public_upload_base_url=get_jimeng_public_upload_base_url,
        normalize_image_bytes_for_jimeng=normalize_image_bytes_for_jimeng,
        prepare_jimeng_i2i_uploaded_input=prepare_jimeng_i2i_uploaded_input,
        sanitize_file_name=sanitize_file_name,
        urllib=urllib,
        uuid4=uuid4,
    )


def build_history_download_public_url(image_source: str) -> str:
    return _xiaoha_history_storage.build_history_download_public_url(
        image_source,
        DB_IMAGE_DIR=DB_IMAGE_DIR,
        Image=Image,
        Path=Path,
        convert_history_path_to_public_url=convert_history_path_to_public_url,
        decode_data_url=decode_data_url,
        ensure_jimeng_upload_dir=ensure_jimeng_upload_dir,
        get_history_public_base_url=get_history_public_base_url,
        get_image_extension_from_mime=get_image_extension_from_mime,
        get_jimeng_public_upload_base_url=get_jimeng_public_upload_base_url,
        hashlib=hashlib,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        is_managed_static_image_url=is_managed_static_image_url,
        load_image_bytes_from_url=load_image_bytes_from_url,
        urllib=urllib,
        uuid4=uuid4,
    )


def build_direct_image_download_url(image_source: str) -> str:
    return _history_paths.build_direct_image_download_url(
        image_source,
        build_history_download_public_url=build_history_download_public_url,
        urllib=urllib,
    )


def get_uploaded_file_bytes(uploaded_file: Any) -> bytes:
    return _image_primitives.get_uploaded_file_bytes(uploaded_file, Path=Path)


def get_uploaded_file_name(uploaded_file: Any) -> str:
    return _image_primitives.get_uploaded_file_name(uploaded_file, Path=Path)


def get_uploaded_file_type(uploaded_file: Any) -> str:
    return _image_primitives.get_uploaded_file_type(
        uploaded_file,
        Path=Path,
        mimetypes=mimetypes,
    )


def normalize_uploaded_input(uploaded_file: Any) -> dict[str, Any]:
    return _image_primitives.normalize_uploaded_input(
        uploaded_file,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        get_uploaded_file_name=get_uploaded_file_name,
        get_uploaded_file_type=get_uploaded_file_type,
    )


def prepare_openrouter_uploaded_input(uploaded_file: Any, max_bytes: int=OPENROUTER_SAFE_INPUT_TARGET_BYTES) -> dict[str, Any]:
    return _image_inputs.prepare_openrouter_uploaded_input(
        uploaded_file,
        max_bytes,
        Image=Image,
        ImageOps=ImageOps,
        OPENROUTER_INPUT_MIN_BUDGET_BYTES=OPENROUTER_INPUT_MIN_BUDGET_BYTES,
        OPENROUTER_MAX_INPUT_IMAGE_EDGE=OPENROUTER_MAX_INPUT_IMAGE_EDGE,
        Path=Path,
        io=io,
        normalize_uploaded_input=normalize_uploaded_input,
        sanitize_file_name=sanitize_file_name,
    )


def prepare_openrouter_request_inputs(uploaded_files: list[Any]) -> list[dict[str, Any]]:
    return _image_primitives.prepare_openrouter_request_inputs(
        uploaded_files,
        OPENROUTER_INPUT_MIN_BUDGET_BYTES=OPENROUTER_INPUT_MIN_BUDGET_BYTES,
        OPENROUTER_REQUEST_IMAGE_BUDGET_BYTES=OPENROUTER_REQUEST_IMAGE_BUDGET_BYTES,
        prepare_openrouter_uploaded_input=prepare_openrouter_uploaded_input,
    )


def prepare_ark_seedream_uploaded_input(uploaded_file: Any) -> dict[str, Any]:
    return _image_inputs.prepare_ark_seedream_uploaded_input(
        uploaded_file,
        ARK_MAX_INPUT_IMAGE_BYTES=ARK_MAX_INPUT_IMAGE_BYTES,
        ARK_MAX_INPUT_IMAGE_EDGE=ARK_MAX_INPUT_IMAGE_EDGE,
        ARK_MAX_INPUT_IMAGE_PIXELS=ARK_MAX_INPUT_IMAGE_PIXELS,
        Image=Image,
        ImageOps=ImageOps,
        Path=Path,
        io=io,
        math=math,
        normalize_uploaded_input=normalize_uploaded_input,
        sanitize_file_name=sanitize_file_name,
    )


def get_uploaded_input_closest_aspect_ratio(uploaded_input: Any, fallback: str=DEFAULT_ASPECT_RATIO) -> str:
    return _image_primitives.get_uploaded_input_closest_aspect_ratio(
        uploaded_input,
        fallback,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        Image=Image,
        ImageOps=ImageOps,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        io=io,
        select_closest_aspect_ratio=select_closest_aspect_ratio,
    )


def get_uploaded_input_dimensions(uploaded_input: Any) -> tuple[int, int]:
    return _image_primitives.get_uploaded_input_dimensions(
        uploaded_input,
        Image=Image,
        ImageOps=ImageOps,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        io=io,
    )


def get_outpaint_extension_limits(original_input: Any) -> dict[str, int]:
    return _outpaint.get_outpaint_extension_limits(
        original_input,
        OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX=OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
        OUTPAINT_MAX_CANVAS_MULTIPLIER=OUTPAINT_MAX_CANVAS_MULTIPLIER,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
    )


def clamp_outpaint_extensions(original_input: Any, top_px: int, bottom_px: int, left_px: int, right_px: int) -> tuple[int, int, int, int]:
    return _outpaint.clamp_outpaint_extensions(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
        get_outpaint_extension_limits=get_outpaint_extension_limits,
    )


def get_outpaint_default_extension(direction_limit: int) -> int:
    return _outpaint.get_outpaint_default_extension(direction_limit)


def get_outpaint_target_canvas_size(original_input: Any, top_px: int, bottom_px: int, left_px: int, right_px: int) -> tuple[int, int]:
    return _outpaint.get_outpaint_target_canvas_size(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
        clamp_outpaint_extensions=clamp_outpaint_extensions,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
    )


def get_outpaint_target_aspect_ratio(original_input: Any, top_px: int, bottom_px: int, left_px: int, right_px: int, fallback: str=DEFAULT_ASPECT_RATIO) -> str:
    return _outpaint.get_outpaint_target_aspect_ratio(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
        fallback,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        get_outpaint_target_canvas_size=get_outpaint_target_canvas_size,
        select_closest_aspect_ratio=select_closest_aspect_ratio,
    )


def build_outpaint_source_framing_instruction(original_input: Any, top_px: int, bottom_px: int, left_px: int, right_px: int) -> str:
    return _outpaint.build_outpaint_source_framing_instruction(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
        clamp_outpaint_extensions=clamp_outpaint_extensions,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
    )


def build_outpaint_region_guide(original_input: Any, top_px: int, bottom_px: int, left_px: int, right_px: int) -> dict[str, Any]:
    return _outpaint.build_outpaint_region_guide(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
        OUTPAINT_GUIDE_MAX_EDGE=OUTPAINT_GUIDE_MAX_EDGE,
        clamp_outpaint_extensions=clamp_outpaint_extensions,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
    )


def build_outpaint_source_canvas(original_input: Any, top_px: int, bottom_px: int, left_px: int, right_px: int) -> dict[str, Any]:
    return _outpaint.build_outpaint_source_canvas(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
        OUTPAINT_GUIDE_MAX_EDGE=OUTPAINT_GUIDE_MAX_EDGE,
        OUTPAINT_SCAFFOLD_BLUR_RATIO=OUTPAINT_SCAFFOLD_BLUR_RATIO,
        OUTPAINT_TRANSITION_CLEAR_RATIO=OUTPAINT_TRANSITION_CLEAR_RATIO,
        OUTPAINT_TRANSITION_FEATHER_RATIO=OUTPAINT_TRANSITION_FEATHER_RATIO,
        clamp_outpaint_extensions=clamp_outpaint_extensions,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
    )


def is_outpaint_result_effectively_unchanged(image_url: str, original_input: Any) -> bool:
    return _outpaint.is_outpaint_result_effectively_unchanged(
        image_url,
        original_input,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def crop_outpaint_result_to_selected_region(image_url: str, original_input: Any, top_px: int, bottom_px: int, left_px: int, right_px: int) -> str:
    return _outpaint.crop_outpaint_result_to_selected_region(
        image_url,
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
        clamp_outpaint_extensions=clamp_outpaint_extensions,
        get_outpaint_target_canvas_size=get_outpaint_target_canvas_size,
        image_bytes_to_data_url=image_bytes_to_data_url,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def measure_outpaint_boundary_seams(image_url: str, original_input: Any, top_px: int, bottom_px: int, left_px: int, right_px: int) -> list[dict[str, Any]]:
    return _outpaint.measure_outpaint_boundary_seams(
        image_url,
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
        OUTPAINT_MULTISCALE_SEAM_RATIO_THRESHOLD=OUTPAINT_MULTISCALE_SEAM_RATIO_THRESHOLD,
        OUTPAINT_MULTISCALE_SEAM_STRENGTH_THRESHOLD=OUTPAINT_MULTISCALE_SEAM_STRENGTH_THRESHOLD,
        OUTPAINT_SEAM_RATIO_THRESHOLD=OUTPAINT_SEAM_RATIO_THRESHOLD,
        OUTPAINT_SEAM_STRENGTH_THRESHOLD=OUTPAINT_SEAM_STRENGTH_THRESHOLD,
        clamp_outpaint_extensions=clamp_outpaint_extensions,
        get_outpaint_target_canvas_size=get_outpaint_target_canvas_size,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def has_outpaint_rectangular_join(measurements: list[dict[str, Any]]) -> bool:
    return _outpaint.has_outpaint_rectangular_join(measurements)


def build_outpaint_seam_repair_reference(image_url: str) -> dict[str, Any]:
    return _outpaint.build_outpaint_seam_repair_reference(
        image_url,
        OUTPAINT_GUIDE_MAX_EDGE=OUTPAINT_GUIDE_MAX_EDGE,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def build_outpaint_seam_repair_prompt(original_input: Any, top_px: int, bottom_px: int, left_px: int, right_px: int, measurements: list[dict[str, Any]]) -> str:
    return _outpaint.build_outpaint_seam_repair_prompt(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
        measurements,
        clamp_outpaint_extensions=clamp_outpaint_extensions,
        get_outpaint_target_canvas_size=get_outpaint_target_canvas_size,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
    )


def clear_upload_cache(widget_key: str, account_name: str | None=None) -> None:
    return _upload_actions.clear_upload_cache(
        widget_key,
        account_name,
        get_current_account_name=get_current_account_name,
        get_upload_cache_dir=get_upload_cache_dir,
    )


def save_upload_cache(widget_key: str, uploaded_files: list[Any], account_name: str | None=None) -> list[dict[str, Any]]:
    return _image_inputs.save_upload_cache(
        widget_key,
        uploaded_files,
        account_name,
        Any=Any,
        Path=Path,
        get_current_account_name=get_current_account_name,
        get_upload_cache_dir=get_upload_cache_dir,
        json=json,
        load_upload_cache=load_upload_cache,
        mimetypes=mimetypes,
        normalize_uploaded_input=normalize_uploaded_input,
        sanitize_file_name=sanitize_file_name,
    )


def replace_upload_cache(widget_key: str, uploaded_files: list[Any], account_name: str | None=None) -> list[dict[str, Any]]:
    return _upload_state.replace_upload_cache(
        widget_key,
        uploaded_files,
        account_name,
        clear_upload_cache=clear_upload_cache,
        get_current_account_name=get_current_account_name,
        save_upload_cache=save_upload_cache,
    )


def load_upload_cache(widget_key: str, account_name: str | None=None, max_files: int | None=None) -> list[dict[str, Any]]:
    return _image_inputs.load_upload_cache(
        widget_key,
        account_name,
        max_files,
        Any=Any,
        get_current_account_name=get_current_account_name,
        get_upload_cache_dir=get_upload_cache_dir,
        json=json,
        mimetypes=mimetypes,
    )


def remove_upload_cache_item(widget_key: str, item_index: int, account_name: str | None=None) -> list[dict[str, Any]]:
    return _upload_state.remove_upload_cache_item(
        widget_key,
        item_index,
        account_name,
        get_current_account_name=get_current_account_name,
        load_upload_cache=load_upload_cache,
        replace_upload_cache=replace_upload_cache,
    )


def reorder_upload_cache_item(widget_key: str, source_index: int, target_index: int, account_name: str | None=None) -> list[dict[str, Any]]:
    return _upload_actions.reorder_upload_cache_item(
        widget_key,
        source_index,
        target_index,
        account_name,
        get_current_account_name=get_current_account_name,
        load_upload_cache=load_upload_cache,
        replace_upload_cache=replace_upload_cache,
    )


def replace_upload_cache_item(widget_key: str, item_index: int, uploaded_file: Any, account_name: str | None=None) -> list[dict[str, Any]]:
    return _upload_actions.replace_upload_cache_item(
        widget_key,
        item_index,
        uploaded_file,
        account_name,
        get_current_account_name=get_current_account_name,
        load_upload_cache=load_upload_cache,
        replace_upload_cache=replace_upload_cache,
    )


def build_uploaded_input_from_replace_payload(payload_text: str) -> dict[str, Any] | None:
    return _upload_actions.build_uploaded_input_from_replace_payload(
        payload_text,
        decode_data_url=decode_data_url,
        json=json,
        mimetypes=mimetypes,
    )


def set_task_progress(job_id: str, percent: int, stage: str) -> None:
    normalized_percent = max(0, min(int(percent), 100))
    runtime = get_task_runtime()
    with runtime.lock:
        runtime.progress[job_id] = {
            "percent": normalized_percent,
            "stage": str(stage or "").strip(),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


def get_task_progress(job_id: str) -> dict[str, Any]:
    runtime = get_task_runtime()
    with runtime.lock:
        return dict(runtime.progress.get(job_id) or {})


def clear_task_progress(job_id: str) -> None:
    runtime = get_task_runtime()
    with runtime.lock:
        runtime.progress.pop(job_id, None)


def calculate_smooth_running_progress(current_percent: int, reported_percent: int, *, waiting: bool=False) -> int:
    return _job_progress_views.calculate_smooth_running_progress(
        current_percent,
        reported_percent,
        waiting=waiting,
    )


def calculate_finishing_progress(start_percent: int, elapsed_seconds: float, duration_seconds: float=8.0) -> int:
    return _job_presentation.calculate_finishing_progress(
        start_percent,
        elapsed_seconds,
        duration_seconds,
        math=math,
    )


def run_main_image_a_plus_manual_element_job(template_input: Any, point: tuple[int, int], existing_elements: list[dict[str, Any]], job_id: str) -> dict[str, Any]:
    return _main_image_a_plus_jobs.run_main_image_a_plus_manual_element_job(
        template_input,
        point,
        existing_elements,
        job_id,
        admitted_job=admitted_job,
        analyze_main_image_a_plus_element_at_point=analyze_main_image_a_plus_element_at_point,
        set_task_progress=set_task_progress,
    )


def submit_main_image_a_plus_manual_element_job(job_state_key: str, template_input: Any, template_signature: str, point: tuple[int, int], existing_elements: list[dict[str, Any]]) -> dict[str, Any]:
    return _main_image_a_plus_elements.submit_main_image_a_plus_manual_element_job(
        job_state_key,
        template_input,
        template_signature,
        point,
        existing_elements,
        clear_task_progress=clear_task_progress,
        datetime=datetime,
        format_user_facing_error_message=format_user_facing_error_message,
        get_request_limiter=get_request_limiter,
        get_task_runtime=get_task_runtime,
        prepare_uploaded_input=prepare_uploaded_input,
        run_main_image_a_plus_manual_element_job=run_main_image_a_plus_manual_element_job,
        set_task_progress=set_task_progress,
        st=st,
    )


def sync_main_image_a_plus_manual_element_job(job_state_key: str, analysis_state_key: str, template_signature: str) -> dict[str, Any]:
    return _main_image_a_plus_elements.sync_main_image_a_plus_manual_element_job(
        job_state_key,
        analysis_state_key,
        template_signature,
        MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS=MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS,
        calculate_smooth_running_progress=calculate_smooth_running_progress,
        clear_task_progress=clear_task_progress,
        format_user_facing_error_message=format_user_facing_error_message,
        get_task_progress=get_task_progress,
        get_task_runtime=get_task_runtime,
        st=st,
    )


@st.fragment(run_every="1s")
def render_main_image_a_plus_manual_element_job_status(job_state_key: str, analysis_state_key: str, template_signature: str) -> None:
    return _main_image_a_plus_elements.render_main_image_a_plus_manual_element_job_status(
        job_state_key,
        analysis_state_key,
        template_signature,
        build_running_job_spinner_html=build_running_job_spinner_html,
        st=st,
        sync_main_image_a_plus_manual_element_job=sync_main_image_a_plus_manual_element_job,
    )


def build_running_job_spinner_html(progress_value: int, progress_stage: str) -> str:
    return _job_progress_views.build_running_job_spinner_html(
        progress_value,
        progress_stage,
        html=html,
    )


def build_queued_job_card_html(job_info: dict[str, Any]) -> str:
    return _job_progress_views.build_queued_job_card_html(job_info, html=html)


def build_job_queue_overview_html(active_jobs: list[dict[str, Any]], current_job_id: str='') -> str:
    return _job_progress_views.build_job_queue_overview_html(
        active_jobs,
        current_job_id,
        html=html,
    )


@st.fragment(run_every="1s")
def render_running_job_status(feature_key: str, in_result: bool=False) -> None:
    return _job_presentation.render_running_job_status(
        feature_key,
        in_result,
        build_running_job_spinner_html=build_running_job_spinner_html,
        st=st,
        sync_background_jobs=sync_background_jobs,
    )


def render_result_loading(feature_key: str='') -> bool:
    return _job_presentation.render_result_loading(
        feature_key,
        render_running_job_status=render_running_job_status,
        st=st,
    )


def get_external_request_kwargs(timeout: int | tuple[int, int], use_proxy: bool=True) -> dict[str, Any]:
    return _runtime_config.get_external_request_kwargs(
        timeout,
        use_proxy,
        Any=Any,
        REQUEST_PROXIES=REQUEST_PROXIES,
    )


def escape_sql_text(value: Any) -> str:
    return _runtime_paths.escape_sql_text(value)


def get_db_connection() -> Any:
    return _history_repository.get_db_connection(DB_CONFIG=DB_CONFIG)


def execute_db_query(query: str, params: tuple[Any, ...] | None=None) -> list[tuple[Any, ...]]:
    return _history_repository.execute_db_query(
        query,
        params,
        get_db_connection=get_db_connection,
    )


def normalize_dashboard_date(value: Any) -> date | None:
    return _job_presentation.normalize_dashboard_date(
        value,
        date=date,
        datetime=datetime,
    )


def build_xiaoha_usage_dashboard_data(rows: list[tuple[Any, ...]], reference_date: date | datetime | str | None=None) -> dict[str, Any]:
    return _usage_data.build_xiaoha_usage_dashboard_data(
        rows,
        reference_date,
        XIAOHA_DASHBOARD_HISTORY_DAYS=XIAOHA_DASHBOARD_HISTORY_DAYS,
        XIAOHA_DASHBOARD_MAX_FEATURE_LINES=XIAOHA_DASHBOARD_MAX_FEATURE_LINES,
        date=date,
        datetime=datetime,
        normalize_dashboard_date=normalize_dashboard_date,
        timedelta=timedelta,
    )


@st.cache_data(ttl=XIAOHA_DASHBOARD_CACHE_SECONDS, show_spinner=False)
def load_xiaoha_usage_dashboard_rows(reference_date_text: str) -> list[tuple[Any, ...]]:
    return _usage_queries.load_xiaoha_usage_dashboard_rows(
        reference_date_text,
        DB_HISTORY_TABLE=DB_HISTORY_TABLE,
        XIAOHA_DASHBOARD_HISTORY_DAYS=XIAOHA_DASHBOARD_HISTORY_DAYS,
        datetime=datetime,
        execute_db_query=execute_db_query,
        normalize_dashboard_date=normalize_dashboard_date,
        timedelta=timedelta,
    )


def build_xiaoha_usage_dashboard_html(dashboard_data: dict[str, Any]) -> str:
    return _usage_views.build_xiaoha_usage_dashboard_html(
        dashboard_data,
        XIAOHA_DASHBOARD_CACHE_SECONDS=XIAOHA_DASHBOARD_CACHE_SECONDS,
        html=html,
        json=json,
    )


def render_xiaoha_balance_management() -> None:
    return _job_presentation.render_xiaoha_balance_management(
        SimpleNamespace=SimpleNamespace,
        load_omnia_api_key=load_omnia_api_key,
        st=st,
    )


def render_xiaoha_usage_dashboard() -> None:
    return _job_progress_views.render_xiaoha_usage_dashboard(
        build_xiaoha_usage_dashboard_data=build_xiaoha_usage_dashboard_data,
        build_xiaoha_usage_dashboard_html=build_xiaoha_usage_dashboard_html,
        components=components,
        datetime=datetime,
        format_user_facing_error_message=format_user_facing_error_message,
        load_xiaoha_usage_dashboard_rows=load_xiaoha_usage_dashboard_rows,
        st=st,
    )


def execute_db_non_query(query: str, params: tuple[Any, ...] | None=None) -> None:
    return _history_repository.execute_db_non_query(
        query,
        params,
        get_db_connection=get_db_connection,
    )


def format_history_datetime(value: Any) -> str:
    return _job_presentation.format_history_datetime(value, datetime=datetime)


def get_feature_name_by_key(feature_key: str) -> str:
    return _model_choices.get_feature_name_by_key(feature_key, FEATURES=FEATURES)


def ensure_db_image_dir() -> Path:
    return _runtime_paths.ensure_db_image_dir(DB_IMAGE_DIR=DB_IMAGE_DIR)


def ensure_feature_output_dir(feature_key: str) -> Path:
    return _runtime_paths.ensure_feature_output_dir(
        feature_key,
        CUTOUT_OUTPUT_DIR=CUTOUT_OUTPUT_DIR,
        DB_IMAGE_DIR=DB_IMAGE_DIR,
    )


def get_image_extension_from_mime(mime_type: str) -> str:
    return _image_primitives.get_image_extension_from_mime(mime_type, mimetypes=mimetypes)


def normalize_image_bytes_for_jimeng(image_bytes: bytes, extension: str) -> tuple[bytes, str]:
    return _upload_actions.normalize_image_bytes_for_jimeng(
        image_bytes,
        extension,
        Image=Image,
        io=io,
    )


def prepare_jimeng_hd_input_base64(uploaded_file: Any) -> str:
    return _jimeng_client.prepare_jimeng_hd_input_base64(
        uploaded_file,
        Image=Image,
        JIMENG_HD_API_MAX_BYTES=JIMENG_HD_API_MAX_BYTES,
        JIMENG_HD_API_MAX_EDGE=JIMENG_HD_API_MAX_EDGE,
        Path=Path,
        base64=base64,
        get_image_extension_from_mime=get_image_extension_from_mime,
        io=io,
        normalize_image_bytes_for_jimeng=normalize_image_bytes_for_jimeng,
        normalize_uploaded_input=normalize_uploaded_input,
        sanitize_file_name=sanitize_file_name,
    )


def prepare_jimeng_i2i_uploaded_input(uploaded_file: Any, error_prefix: str='Agent 参考图失败') -> dict[str, Any]:
    return _jimeng_client.prepare_jimeng_i2i_uploaded_input(
        uploaded_file,
        error_prefix,
        Image=Image,
        JIMENG_I2I_MAX_BYTES=JIMENG_I2I_MAX_BYTES,
        JIMENG_I2I_MAX_EDGE=JIMENG_I2I_MAX_EDGE,
        Path=Path,
        get_image_extension_from_mime=get_image_extension_from_mime,
        io=io,
        normalize_image_bytes_for_jimeng=normalize_image_bytes_for_jimeng,
        normalize_uploaded_input=normalize_uploaded_input,
        sanitize_file_name=sanitize_file_name,
    )


def build_uploaded_input_from_image_url_raw(image_url: str, base_name: str='hd_input.jpg') -> dict[str, Any]:
    return _output_processing.build_uploaded_input_from_image_url_raw(
        image_url,
        base_name,
        load_image_bytes_from_url=load_image_bytes_from_url,
        sanitize_file_name=sanitize_file_name,
    )


def prepare_main_image_a_plus_reference_input(uploaded_input: Any) -> dict[str, Any]:
    return _image_inputs.prepare_main_image_a_plus_reference_input(
        uploaded_input,
        Image=Image,
        ImageOps=ImageOps,
        MAIN_IMAGE_A_PLUS_REFERENCE_MAX_EDGE=MAIN_IMAGE_A_PLUS_REFERENCE_MAX_EDGE,
        MAIN_IMAGE_A_PLUS_REFERENCE_TARGET_BYTES=MAIN_IMAGE_A_PLUS_REFERENCE_TARGET_BYTES,
        Path=Path,
        io=io,
        normalize_uploaded_input=normalize_uploaded_input,
        sanitize_file_name=sanitize_file_name,
    )


def analyze_main_image_a_plus_source_integrity(source_inputs: list[Any]) -> list[dict[str, Any]]:
    return _main_image_a_plus_sources.analyze_main_image_a_plus_source_integrity(
        source_inputs,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        MAIN_IMAGE_A_PLUS_MAX_FILES=MAIN_IMAGE_A_PLUS_MAX_FILES,
        MAIN_IMAGE_A_PLUS_SOURCE_INTEGRITY_MODEL=MAIN_IMAGE_A_PLUS_SOURCE_INTEGRITY_MODEL,
        _extract_strict_json_object=_extract_strict_json_object,
        call_openrouter=call_openrouter,
    )


def repair_main_image_a_plus_source_crop(source_input: Any, report: dict[str, Any], *, model: str, supporting_references: list[Any] | None=None) -> dict[str, Any]:
    return _main_image_a_plus_sources.repair_main_image_a_plus_source_crop(
        source_input,
        report,
        model=model,
        supporting_references=supporting_references,
        AMAZON_A_PLUS_NATIVE_IMAGE_SIZE=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        MAIN_IMAGE_A_PLUS_SOURCE_REPAIR_EDGE_RATIO=MAIN_IMAGE_A_PLUS_SOURCE_REPAIR_EDGE_RATIO,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        Path=Path,
        build_outpaint_source_canvas=build_outpaint_source_canvas,
        build_outpaint_source_framing_instruction=build_outpaint_source_framing_instruction,
        call_openrouter_images_api=call_openrouter_images_api,
        crop_outpaint_result_to_selected_region=crop_outpaint_result_to_selected_region,
        get_outpaint_target_aspect_ratio=get_outpaint_target_aspect_ratio,
        get_outpaint_target_canvas_size=get_outpaint_target_canvas_size,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        get_uploaded_input_name=get_uploaded_input_name,
        load_image_bytes_from_url=load_image_bytes_from_url,
        normalize_uploaded_input=normalize_uploaded_input,
        prepare_main_image_a_plus_reference_input=prepare_main_image_a_plus_reference_input,
        sanitize_file_name=sanitize_file_name,
    )


def prepare_main_image_a_plus_sources_with_repair(source_inputs: list[Any], *, model: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, list[str]]:
    return _main_image_a_plus_sources.prepare_main_image_a_plus_sources_with_repair(
        source_inputs,
        model=model,
        Any=Any,
        MAIN_IMAGE_A_PLUS_MAX_FILES=MAIN_IMAGE_A_PLUS_MAX_FILES,
        MAIN_IMAGE_A_PLUS_MAX_SOURCE_REPAIRS=MAIN_IMAGE_A_PLUS_MAX_SOURCE_REPAIRS,
        MAIN_IMAGE_A_PLUS_SOURCE_REPAIR_MIN_CONFIDENCE=MAIN_IMAGE_A_PLUS_SOURCE_REPAIR_MIN_CONFIDENCE,
        analyze_main_image_a_plus_source_integrity=analyze_main_image_a_plus_source_integrity,
        prepare_main_image_a_plus_reference_input=prepare_main_image_a_plus_reference_input,
        repair_main_image_a_plus_source_crop=repair_main_image_a_plus_source_crop,
    )


def build_main_image_a_plus_source_integrity_instruction(reports: list[dict[str, Any]]) -> str:
    return _main_image_a_plus_sources.build_main_image_a_plus_source_integrity_instruction(reports)


@st.cache_data(show_spinner=False, ttl=3600, max_entries=2)
def get_main_image_a_plus_mobile_reference_inputs() -> list[dict[str, Any]]:
    return _main_image_a_plus_image_tools.get_main_image_a_plus_mobile_reference_inputs(
        Any=Any,
        MAIN_IMAGE_A_PLUS_MOBILE_REFERENCE_PAIRS=MAIN_IMAGE_A_PLUS_MOBILE_REFERENCE_PAIRS,
        MAIN_IMAGE_A_PLUS_MOBILE_REFERENCE_ROOT=MAIN_IMAGE_A_PLUS_MOBILE_REFERENCE_ROOT,
        prepare_main_image_a_plus_reference_input=prepare_main_image_a_plus_reference_input,
    )


def build_main_image_a_plus_continuity_reference(image_url: str, target_width: int, target_height: int, base_name: str) -> dict[str, Any]:
    return _a_plus_layout_rules.build_main_image_a_plus_continuity_reference(
        image_url,
        target_width,
        target_height,
        base_name,
        Image=Image,
        ImageOps=ImageOps,
        Path=Path,
        cover_image_to_canvas_without_distortion=cover_image_to_canvas_without_distortion,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
        sanitize_file_name=sanitize_file_name,
    )


def build_portrait_hd_prompt(prompt: str) -> str:
    return _output_processing.build_portrait_hd_prompt(
        prompt,
        PORTRAIT_HD_COLOR_LOCK_RULES=PORTRAIT_HD_COLOR_LOCK_RULES,
        PORTRAIT_HD_SKIN_LOCK_RULES=PORTRAIT_HD_SKIN_LOCK_RULES,
    )


def build_portrait_hd_size_instruction(source_input: Any) -> str:
    return _output_processing.build_portrait_hd_size_instruction(source_input, get_uploaded_input_dimensions=get_uploaded_input_dimensions)


def restore_portrait_hd_source_size(image_url: str, source_input: Any) -> str:
    return _portrait_results.restore_portrait_hd_source_size(
        image_url,
        source_input,
        Image=Image,
        ImageOps=ImageOps,
        cover_image_to_canvas_without_distortion=cover_image_to_canvas_without_distortion,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def finalize_portrait_hd_result(result: dict[str, Any], source_input: Any) -> dict[str, Any]:
    return _output_processing.finalize_portrait_hd_result(
        result,
        source_input,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        restore_portrait_hd_source_size=restore_portrait_hd_source_size,
    )


def get_portrait_hd_inputs(uploaded_files: list[Any] | None=None) -> list[Any]:
    return _output_processing.get_portrait_hd_inputs(uploaded_files, get_model_reference_files=get_model_reference_files)


def build_history_thumbnail_path(image_path: Path) -> Path:
    return _history_paths.build_history_thumbnail_path(image_path, DB_HISTORY_THUMB_DIR_NAME=DB_HISTORY_THUMB_DIR_NAME)


def save_history_thumbnail(image_bytes: bytes, original_path: Path) -> str:
    return _xiaoha_history_storage.save_history_thumbnail(
        image_bytes,
        original_path,
        DB_HISTORY_THUMB_MAX_EDGE=DB_HISTORY_THUMB_MAX_EDGE,
        DB_HISTORY_THUMB_TARGET_BYTES=DB_HISTORY_THUMB_TARGET_BYTES,
        Image=Image,
        build_history_thumbnail_path=build_history_thumbnail_path,
        io=io,
    )


def ensure_history_thumbnail(image_path_text: str) -> str:
    return _xiaoha_history_storage.ensure_history_thumbnail(
        image_path_text,
        Path=Path,
        build_history_thumbnail_path=build_history_thumbnail_path,
        relocate_storage_path=relocate_storage_path,
        save_history_thumbnail=save_history_thumbnail,
    )


def build_db_history_image_value(image_path: Path) -> str:
    return _history_paths.build_db_history_image_value(image_path, DB_HISTORY_PATH_MAX_LENGTH=DB_HISTORY_PATH_MAX_LENGTH)


def build_saved_history_file_name(created_at: datetime, index: int, extension: str) -> str:
    return _history_paths.build_saved_history_file_name(
        created_at,
        index,
        extension,
    )


def try_find_history_image_by_metadata(
    account_name: str,
    feature_name: str,
    created_at_text: str,
) -> str:
    return _xiaoha_history_storage.try_find_history_image_by_metadata(
        account_name,
        feature_name,
        created_at_text,
        datetime=datetime,
        ensure_db_image_dir=ensure_db_image_dir,
        sanitize_file_name=sanitize_file_name,
    )


def resolve_db_history_image_path(image_path_text: str, account_name: str='', feature_name: str='', created_at_text: str='') -> str:
    return _history_paths.resolve_db_history_image_path(
        image_path_text,
        account_name,
        feature_name,
        created_at_text,
        Path=Path,
        _xiaoha_history_storage=_xiaoha_history_storage,
        ensure_db_image_dir=ensure_db_image_dir,
        relocate_storage_path=relocate_storage_path,
        try_find_history_image_by_metadata=try_find_history_image_by_metadata,
    )


def insert_history_db_record(account_name: str, feature_name: str, model: str, image_path: str, created_at_text: str, image_count: int) -> None:
    return _history_repository.insert_history_db_record(
        account_name,
        feature_name,
        model,
        image_path,
        created_at_text,
        image_count,
        DB_HISTORY_TABLE=DB_HISTORY_TABLE,
        _xiaoha_history_storage=_xiaoha_history_storage,
        execute_db_non_query=execute_db_non_query,
    )


def record_infinite_canvas_usage(account_name: str, feature_name: str, model: str, image_count: int=1) -> bool:
    return _history_repository.record_infinite_canvas_usage(
        account_name,
        feature_name,
        model,
        image_count,
        DB_HISTORY_TABLE=DB_HISTORY_TABLE,
        datetime=datetime,
        insert_history_db_record=insert_history_db_record,
        sys=sys,
    )


def save_generated_images_and_record_db(feature: dict[str, Any], model: str, prompt: str, result: dict[str, Any], account_name: str) -> list[dict[str, Any]]:
    return _result_storage.save_generated_images_and_record_db(
        feature,
        model,
        prompt,
        result,
        account_name,
        Any=Any,
        build_db_history_image_value=build_db_history_image_value,
        build_saved_history_file_name=build_saved_history_file_name,
        datetime=datetime,
        ensure_feature_output_dir=ensure_feature_output_dir,
        ensure_history_thumbnail=ensure_history_thumbnail,
        get_image_extension_from_mime=get_image_extension_from_mime,
        insert_history_db_record=insert_history_db_record,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def persist_generated_images_in_background(feature: dict[str, Any], model: str, prompt: str, result: dict[str, Any], account_name: str) -> None:
    return _result_storage.persist_generated_images_in_background(
        feature,
        model,
        prompt,
        result,
        account_name,
        Thread=Thread,
        save_generated_images_and_record_db=save_generated_images_and_record_db,
        sys=sys,
    )


def _db_history_can_view_all(account_name: str) -> bool:
    return _history_repository._db_history_can_view_all(
        account_name,
        execute_db_query=execute_db_query,
        re=re,
    )


def load_db_history_records(feature_key: str, account_name: str, limit: int=DB_HISTORY_LIMIT) -> list[dict[str, Any]]:
    return _history_repository.load_db_history_records(
        feature_key,
        account_name,
        limit,
        A_PLUS_REFERENCE_LAB_FEATURE_KEY=A_PLUS_REFERENCE_LAB_FEATURE_KEY,
        Any=Any,
        DB_HISTORY_TABLE=DB_HISTORY_TABLE,
        Path=Path,
        _db_history_can_view_all=_db_history_can_view_all,
        _xiaoha_history=_xiaoha_history,
        build_history_thumbnail_source=build_history_thumbnail_source,
        convert_history_path_to_public_url=convert_history_path_to_public_url,
        ensure_history_thumbnail=ensure_history_thumbnail,
        execute_db_query=execute_db_query,
        format_history_datetime=format_history_datetime,
        get_feature_name_by_key=get_feature_name_by_key,
        resolve_db_history_image_path=resolve_db_history_image_path,
    )



def get_history_cache_key(account_name: str, feature_key: str) -> str:
    return _job_presentation.get_history_cache_key(account_name, feature_key)


def get_history_visible_limit(cache_key: str) -> int:
    return _job_presentation.get_history_visible_limit(
        cache_key,
        HISTORY_PAGE_SIZE=HISTORY_PAGE_SIZE,
        st=st,
    )


def set_history_visible_limit(cache_key: str, limit: int) -> None:
    return _job_presentation.set_history_visible_limit(
        cache_key,
        limit,
        HISTORY_PAGE_SIZE=HISTORY_PAGE_SIZE,
        st=st,
    )


def ensure_history_records_loaded(feature_key: str, account_name: str, cache_key: str, limit: int) -> list[dict[str, Any]]:
    return _job_presentation.ensure_history_records_loaded(
        feature_key,
        account_name,
        cache_key,
        limit,
        HISTORY_PAGE_SIZE=HISTORY_PAGE_SIZE,
        get_feature_history_records=get_feature_history_records,
        st=st,
    )


def normalize_history_image_source(image_source: str) -> str:
    return _history_paths.normalize_history_image_source(
        image_source,
        image_bytes_to_data_url=image_bytes_to_data_url,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def build_history_thumbnail_source(image_source: str) -> str:
    return _history_paths.build_history_thumbnail_source(
        image_source,
        build_gallery_preview_data_url=build_gallery_preview_data_url,
        image_bytes_to_data_url=image_bytes_to_data_url,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def build_local_history_records(
    feature: dict[str, Any],
    model: str,
    prompt: str,
    result: dict[str, Any],
    account_name: str,
) -> list[dict[str, Any]]:
    return _xiaoha_history_storage.build_local_history_records(
        feature,
        model,
        prompt,
        result,
        account_name,
        Any=Any,
        build_history_thumbnail_source=build_history_thumbnail_source,
        datetime=datetime,
        normalize_history_image_source=normalize_history_image_source,
    )


def store_local_history_records(account_name: str, feature_key: str, records: list[dict[str, Any]]) -> None:
    return _xiaoha_history_storage.store_local_history_records(
        account_name,
        feature_key,
        records,
        MAX_HISTORY_RECORDS=MAX_HISTORY_RECORDS,
        st=st,
    )


FRONTEND_PRIVATE_RESULT_FIELDS = {
    "prompt",
    "system_prompt",
    "request_prompt",
    "raw_prompt",
    "request_payload",
    "raw",
}


def prepare_result_for_frontend(result: dict[str, Any]) -> dict[str, Any]:
    return _history_paths.prepare_result_for_frontend(
        result,
        Any=Any,
        FRONTEND_PRIVATE_RESULT_FIELDS=FRONTEND_PRIVATE_RESULT_FIELDS,
    )


def get_feature_history_records(
    feature_key: str,
    account_name: str,
    limit: int = DB_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    return _xiaoha_history.get_feature_history_records(
        feature_key,
        account_name,
        limit,
        _db_history_can_view_all=_db_history_can_view_all,
        load_db_history_records=load_db_history_records,
        st=st,
    )



def get_latest_feature_result(feature_key: str) -> dict[str, Any] | None:
    return _output_processing.get_latest_feature_result(feature_key)


def prepare_uploaded_input(uploaded_file: Any) -> Any:
    return _output_processing.prepare_uploaded_input(
        uploaded_file,
        Path=Path,
        normalize_uploaded_input=normalize_uploaded_input,
    )


def get_uploaded_input_name(uploaded_input: Any) -> str:
    return _output_processing.get_uploaded_input_name(uploaded_input, Path=Path)


def get_feature_min_output_edge(feature_or_key: dict[str, Any] | str | None) -> int:
    return _model_choices.get_feature_min_output_edge(
        feature_or_key,
        HD_MIN_OUTPUT_EDGE=HD_MIN_OUTPUT_EDGE,
        MIN_OUTPUT_EDGE=MIN_OUTPUT_EDGE,
    )


def normalize_feature_output_count(value: Any, default: int=1) -> int:
    return _model_choices.normalize_feature_output_count(
        value,
        default,
        FEATURE_OUTPUT_COUNT_MAX=FEATURE_OUTPUT_COUNT_MAX,
        FEATURE_OUTPUT_COUNT_MIN=FEATURE_OUTPUT_COUNT_MIN,
    )


def should_enhance_output_detail(feature_key: str) -> bool:
    return _model_choices.should_enhance_output_detail(feature_key)


def is_jimeng_model(model_name: str) -> bool:
    return _model_choices.is_jimeng_model(
        model_name,
        JIMENG_HD_MODEL_NAME=JIMENG_HD_MODEL_NAME,
        JIMENG_MODEL_NAME=JIMENG_MODEL_NAME,
    )


def is_ark_seedream_model(model_name: str) -> bool:
    return _model_choices.is_ark_seedream_model(model_name, ARK_SEEDREAM_5_PRO_MODEL=ARK_SEEDREAM_5_PRO_MODEL)


def is_nano_banana_model(model_name: str) -> bool:
    return _model_choices.is_nano_banana_model(model_name, NANO_BANANA_MODEL_ALIASES=NANO_BANANA_MODEL_ALIASES)


def resolve_nano_banana_model(model_name: str) -> str:
    return _model_choices.resolve_nano_banana_model(
        model_name,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        is_nano_banana_model=is_nano_banana_model,
    )


def resolve_omnia_image_model(model_name: str) -> str:
    return _model_choices.resolve_omnia_image_model(
        model_name,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        OMNIA_IMAGE_MODELS=OMNIA_IMAGE_MODELS,
        OMNIA_IMAGE_MODEL_ALIASES=OMNIA_IMAGE_MODEL_ALIASES,
        is_nano_banana_model=is_nano_banana_model,
    )


def get_model_display_name(model_name: str) -> str:
    return _model_choices.get_model_display_name(
        model_name,
        IMAGE_SMART_ANALYSIS_MODEL=IMAGE_SMART_ANALYSIS_MODEL,
        JIMENG_HD_MODEL_NAME=JIMENG_HD_MODEL_NAME,
        OMNIA_IMAGE_MODEL_LABELS=OMNIA_IMAGE_MODEL_LABELS,
        is_ark_seedream_model=is_ark_seedream_model,
        is_jimeng_model=is_jimeng_model,
    )


def is_jimeng_concurrent_limit_error(message: str) -> bool:
    return _model_choices.is_jimeng_concurrent_limit_error(message)


def is_omnia_image_outcome_unknown(error: Any) -> bool:
    return _model_choices.is_omnia_image_outcome_unknown(error, ImageOutcomeUnknown=ImageOutcomeUnknown)


def is_hd_batch_transient_error(error: Any) -> bool:
    return _feature_helpers.is_hd_batch_transient_error(error, is_omnia_image_outcome_unknown=is_omnia_image_outcome_unknown)


def run_hd_batch_generate_with_retry(generate_once, prompt_text: str, retry_offset_seconds: int=0) -> dict[str, Any]:
    return _feature_helpers.run_hd_batch_generate_with_retry(
        generate_once,
        prompt_text,
        retry_offset_seconds,
        HD_BATCH_TRANSIENT_MAX_ATTEMPTS=HD_BATCH_TRANSIENT_MAX_ATTEMPTS,
        HD_BATCH_TRANSIENT_RETRY_DELAYS=HD_BATCH_TRANSIENT_RETRY_DELAYS,
        is_hd_batch_transient_error=is_hd_batch_transient_error,
        sys=sys,
        time=time,
    )


def process_batch_group(job_context: dict[str, Any], uploaded_group: list[Any], group_index: int) -> dict[str, Any]:
    return _batch_jobs.process_batch_group(
        job_context,
        uploaded_group,
        group_index,
        Any=Any,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        JIMENG_HD_FEATURE_KEY=JIMENG_HD_FEATURE_KEY,
        OUTPAINT_RESULTS_PER_SOURCE=OUTPAINT_RESULTS_PER_SOURCE,
        REMOVE_EYELASHES_IMAGE_RESOLUTION=REMOVE_EYELASHES_IMAGE_RESOLUTION,
        _OPENROUTER_REMOVE_EYELASHES_LOCK=_OPENROUTER_REMOVE_EYELASHES_LOCK,
        build_outpaint_seam_repair_prompt=build_outpaint_seam_repair_prompt,
        build_outpaint_seam_repair_reference=build_outpaint_seam_repair_reference,
        build_outpaint_source_canvas=build_outpaint_source_canvas,
        build_outpaint_source_framing_instruction=build_outpaint_source_framing_instruction,
        call_ark_seedream_images_api=call_ark_seedream_images_api,
        call_jimeng_hd_upscale=call_jimeng_hd_upscale,
        call_jimeng_v40=call_jimeng_v40,
        call_openrouter=call_openrouter,
        call_openrouter_images_api=call_openrouter_images_api,
        call_portrait_hd_upscale=call_portrait_hd_upscale,
        clamp_outpaint_extensions=clamp_outpaint_extensions,
        crop_outpaint_result_to_selected_region=crop_outpaint_result_to_selected_region,
        get_feature_min_output_edge=get_feature_min_output_edge,
        get_outpaint_target_aspect_ratio=get_outpaint_target_aspect_ratio,
        get_outpaint_target_canvas_size=get_outpaint_target_canvas_size,
        get_uploaded_input_closest_aspect_ratio=get_uploaded_input_closest_aspect_ratio,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        get_uploaded_input_name=get_uploaded_input_name,
        has_outpaint_rectangular_join=has_outpaint_rectangular_join,
        is_ark_seedream_model=is_ark_seedream_model,
        is_jimeng_model=is_jimeng_model,
        is_omnia_image_outcome_unknown=is_omnia_image_outcome_unknown,
        is_outpaint_result_effectively_unchanged=is_outpaint_result_effectively_unchanged,
        measure_outpaint_boundary_seams=measure_outpaint_boundary_seams,
        resize_image_to_exact_size=resize_image_to_exact_size,
        run_hd_batch_generate_with_retry=run_hd_batch_generate_with_retry,
        should_enhance_output_detail=should_enhance_output_detail,
        upscale_image_to_min_edge=upscale_image_to_min_edge,
    )


def finalize_canvas_job_result(job_context: dict[str, Any], result: dict[str, Any], job_id: str) -> dict[str, Any]:
    return _feature_helpers.finalize_canvas_job_result(
        job_context,
        result,
        job_id,
        build_local_history_records=build_local_history_records,
        save_generated_images_and_record_db=save_generated_images_and_record_db,
        set_task_progress=set_task_progress,
        sys=sys,
    )


def finalize_feature_job_result(job_context: dict[str, Any], result: dict[str, Any], job_id: str) -> dict[str, Any]:
    return _feature_dispatch.finalize_feature_job_result(
        job_context,
        result,
        job_id,
        Path=Path,
        build_local_history_records=build_local_history_records,
        ensure_feature_output_dir=ensure_feature_output_dir,
        save_generated_images_and_record_db=save_generated_images_and_record_db,
        set_task_progress=set_task_progress,
        sys=sys,
    )


def run_infinite_canvas_job(job_context: dict[str, Any]) -> dict[str, Any]:
    return _batch_jobs.run_infinite_canvas_job(
        job_context,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        JIMENG_HD_FEATURE_KEY=JIMENG_HD_FEATURE_KEY,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX=OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
        OUTPAINT_DEFAULT_EXTENSION_PX=OUTPAINT_DEFAULT_EXTENSION_PX,
        build_outpaint_extra_notes=build_outpaint_extra_notes,
        build_prompt=build_prompt,
        build_uploaded_input_from_image_url_raw=build_uploaded_input_from_image_url_raw,
        call_jimeng_hd_upscale=call_jimeng_hd_upscale,
        call_jimeng_portrait_hd=call_jimeng_portrait_hd,
        call_jimeng_v40=call_jimeng_v40,
        call_openrouter=call_openrouter,
        call_openrouter_portrait_hd=call_openrouter_portrait_hd,
        clamp_outpaint_extensions=clamp_outpaint_extensions,
        get_feature_by_key=get_feature_by_key,
        get_feature_min_output_edge=get_feature_min_output_edge,
        get_outpaint_target_aspect_ratio=get_outpaint_target_aspect_ratio,
        is_jimeng_model=is_jimeng_model,
        math=math,
        prepare_uploaded_input=prepare_uploaded_input,
        set_task_progress=set_task_progress,
        should_enhance_output_detail=should_enhance_output_detail,
        uploaded_input_to_data_url=uploaded_input_to_data_url,
        upscale_image_to_min_edge=upscale_image_to_min_edge,
    )


def split_main_image_a_plus_template(template_input: Any, target_width: int, section_heights: tuple[int, ...]) -> list[dict[str, Any]]:
    return _image_geometry.split_main_image_a_plus_template(
        template_input,
        target_width,
        section_heights,
        Any=Any,
        Image=Image,
        ImageOps=ImageOps,
        fit_image_to_canvas_without_distortion=fit_image_to_canvas_without_distortion,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        io=io,
    )


def stitch_main_image_a_plus_sections(section_image_urls: list[str], target_width: int, section_heights: tuple[int, ...]) -> str:
    return _image_geometry.stitch_main_image_a_plus_sections(
        section_image_urls,
        target_width,
        section_heights,
        Image=Image,
        ImageOps=ImageOps,
        cover_image_to_canvas_without_distortion=cover_image_to_canvas_without_distortion,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def resize_main_image_a_plus_mobile_single_layer(candidate_image_url: str, target_width: int, target_height: int) -> str:
    return _image_geometry.resize_main_image_a_plus_mobile_single_layer(
        candidate_image_url,
        target_width,
        target_height,
        Image=Image,
        ImageOps=ImageOps,
        cover_image_to_canvas_without_distortion=cover_image_to_canvas_without_distortion,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def run_main_image_a_plus_text_edit_job(job_context: dict[str, Any]) -> dict[str, Any]:
    return _main_image_a_plus_jobs.run_main_image_a_plus_text_edit_job(
        job_context,
        AMAZON_A_PLUS_NATIVE_IMAGE_SIZE=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        Image=Image,
        ImageOps=ImageOps,
        MAIN_IMAGE_A_PLUS_MODE_TEXT_EDIT=MAIN_IMAGE_A_PLUS_MODE_TEXT_EDIT,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        build_main_image_a_plus_text_edit_prompt=build_main_image_a_plus_text_edit_prompt,
        call_openrouter_images_api=call_openrouter_images_api,
        cover_image_to_exact_size=cover_image_to_exact_size,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
        select_main_image_a_plus_safe_aspect_ratio=select_main_image_a_plus_safe_aspect_ratio,
        set_task_progress=set_task_progress,
    )


def run_main_image_a_plus_mobile_adaptation_job(job_context: dict[str, Any]) -> dict[str, Any]:
    return _main_image_a_plus_jobs.run_main_image_a_plus_mobile_adaptation_job(
        job_context,
        AMAZON_A_PLUS_NATIVE_IMAGE_SIZE=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        Any=Any,
        MAIN_IMAGE_A_PLUS_MAX_QUALITY_ATTEMPTS=MAIN_IMAGE_A_PLUS_MAX_QUALITY_ATTEMPTS,
        MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT=MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        analyze_main_image_a_plus_mobile_element_inventory=analyze_main_image_a_plus_mobile_element_inventory,
        build_main_image_a_plus_mobile_adaptation_prompt=build_main_image_a_plus_mobile_adaptation_prompt,
        build_main_image_a_plus_mobile_repair_prompt=build_main_image_a_plus_mobile_repair_prompt,
        build_main_image_a_plus_mobile_safe_margin_instruction=build_main_image_a_plus_mobile_safe_margin_instruction,
        build_main_image_a_plus_quality_retry_instruction=build_main_image_a_plus_quality_retry_instruction,
        call_openrouter_images_api=call_openrouter_images_api,
        collect_main_image_a_plus_quality_issues=collect_main_image_a_plus_quality_issues,
        format_main_image_a_plus_mobile_element_inventory=format_main_image_a_plus_mobile_element_inventory,
        get_main_image_a_plus_mobile_layout_for_source=get_main_image_a_plus_mobile_layout_for_source,
        get_main_image_a_plus_mobile_reference_inputs=get_main_image_a_plus_mobile_reference_inputs,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        load_image_bytes_from_url=load_image_bytes_from_url,
        prepare_main_image_a_plus_reference_input=prepare_main_image_a_plus_reference_input,
        rank_main_image_a_plus_quality_review=rank_main_image_a_plus_quality_review,
        resize_main_image_a_plus_mobile_single_layer=resize_main_image_a_plus_mobile_single_layer,
        review_main_image_a_plus_candidate=review_main_image_a_plus_candidate,
        select_main_image_a_plus_safe_aspect_ratio=select_main_image_a_plus_safe_aspect_ratio,
        set_task_progress=set_task_progress,
    )


def build_main_image_a_plus_designed_module_section_heights(target_height: int, section_count: int) -> tuple[int, ...]:
    return _layout_selection.build_main_image_a_plus_designed_module_section_heights(target_height, section_count)


def build_main_image_a_plus_designed_module_section_prompt(user_prompt: str, layout: dict[str, Any], section_index: int, section_count: int, section_height: int, source_report: dict[str, Any], retry_instruction: str='', style_reference_count: int=0) -> str:
    return _main_image_a_plus_prompts.build_main_image_a_plus_designed_module_section_prompt(
        user_prompt,
        layout,
        section_index,
        section_count,
        section_height,
        source_report,
        retry_instruction,
        style_reference_count,
    )


def run_main_image_a_plus_designed_module_job(job_context: dict[str, Any], generation_mode: str, layout: dict[str, Any], uploaded_files: list[Any], source_integrity_reports: list[dict[str, Any]], source_repair_count: int, source_integrity_warnings: list[str], style_reference_inputs: list[Any] | None=None, style_reference_paths: list[Path] | None=None) -> dict[str, Any]:
    return _main_image_a_plus_jobs.run_main_image_a_plus_designed_module_job(
        job_context,
        generation_mode,
        layout,
        uploaded_files,
        source_integrity_reports,
        source_repair_count,
        source_integrity_warnings,
        style_reference_inputs,
        style_reference_paths,
        AMAZON_A_PLUS_NATIVE_IMAGE_SIZE=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        A_PLUS_REFERENCE_LAB_FEATURE_KEY=A_PLUS_REFERENCE_LAB_FEATURE_KEY,
        Any=Any,
        MAIN_IMAGE_A_PLUS_MAX_FILES=MAIN_IMAGE_A_PLUS_MAX_FILES,
        MAIN_IMAGE_A_PLUS_MAX_SECTION_CONCURRENCY=MAIN_IMAGE_A_PLUS_MAX_SECTION_CONCURRENCY,
        ThreadPoolExecutor=ThreadPoolExecutor,
        as_completed=as_completed,
        build_main_image_a_plus_designed_module_section_heights=build_main_image_a_plus_designed_module_section_heights,
        build_main_image_a_plus_designed_module_section_prompt=build_main_image_a_plus_designed_module_section_prompt,
        build_main_image_a_plus_quality_recovery_advice=build_main_image_a_plus_quality_recovery_advice,
        build_main_image_a_plus_quality_retry_instruction=build_main_image_a_plus_quality_retry_instruction,
        call_openrouter_images_api=call_openrouter_images_api,
        collect_main_image_a_plus_quality_issues=collect_main_image_a_plus_quality_issues,
        collect_main_image_a_plus_severe_subject_clips=collect_main_image_a_plus_severe_subject_clips,
        copy_context=copy_context,
        math=math,
        rank_main_image_a_plus_quality_review=rank_main_image_a_plus_quality_review,
        review_main_image_a_plus_candidate=review_main_image_a_plus_candidate,
        select_closest_aspect_ratio=select_closest_aspect_ratio,
        set_task_progress=set_task_progress,
        stitch_main_image_a_plus_sections=stitch_main_image_a_plus_sections,
    )


def run_main_image_a_plus_job(job_context: dict[str, Any]) -> dict[str, Any]:
    return _main_image_a_plus_jobs.run_main_image_a_plus_job(
        job_context,
        AMAZON_A_PLUS_NATIVE_IMAGE_SIZE=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        A_PLUS_REFERENCE_LAB_FEATURE_KEY=A_PLUS_REFERENCE_LAB_FEATURE_KEY,
        A_PLUS_REFERENCE_LAB_MAX_PRODUCT_IMAGES=A_PLUS_REFERENCE_LAB_MAX_PRODUCT_IMAGES,
        Any=Any,
        MAIN_IMAGE_A_PLUS_FREE_MODES=MAIN_IMAGE_A_PLUS_FREE_MODES,
        MAIN_IMAGE_A_PLUS_MAX_FILES=MAIN_IMAGE_A_PLUS_MAX_FILES,
        MAIN_IMAGE_A_PLUS_MAX_FREE_QUALITY_ATTEMPTS=MAIN_IMAGE_A_PLUS_MAX_FREE_QUALITY_ATTEMPTS,
        MAIN_IMAGE_A_PLUS_MAX_SECTION_CONCURRENCY=MAIN_IMAGE_A_PLUS_MAX_SECTION_CONCURRENCY,
        MAIN_IMAGE_A_PLUS_MODE_ELEMENT=MAIN_IMAGE_A_PLUS_MODE_ELEMENT,
        MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN=MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN,
        MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST=MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST,
        MAIN_IMAGE_A_PLUS_MODE_TEMPLATE=MAIN_IMAGE_A_PLUS_MODE_TEMPLATE,
        MAIN_IMAGE_A_PLUS_SECTION_COUNT=MAIN_IMAGE_A_PLUS_SECTION_COUNT,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        Path=Path,
        ThreadPoolExecutor=ThreadPoolExecutor,
        as_completed=as_completed,
        build_main_image_a_plus_continuity_reference=build_main_image_a_plus_continuity_reference,
        build_main_image_a_plus_element_replacement_prompt=build_main_image_a_plus_element_replacement_prompt,
        build_main_image_a_plus_free_prompt=build_main_image_a_plus_free_prompt,
        build_main_image_a_plus_free_quality_repair_prompt=build_main_image_a_plus_free_quality_repair_prompt,
        build_main_image_a_plus_hero_design_prompt=build_main_image_a_plus_hero_design_prompt,
        build_main_image_a_plus_quality_recovery_advice=build_main_image_a_plus_quality_recovery_advice,
        build_main_image_a_plus_quality_retry_instruction=build_main_image_a_plus_quality_retry_instruction,
        build_main_image_a_plus_section_prompt=build_main_image_a_plus_section_prompt,
        build_main_image_a_plus_single_test_prompt=build_main_image_a_plus_single_test_prompt,
        build_main_image_a_plus_source_integrity_instruction=build_main_image_a_plus_source_integrity_instruction,
        build_main_image_a_plus_template_section_prompt=build_main_image_a_plus_template_section_prompt,
        build_uploaded_input_from_image_url_raw=build_uploaded_input_from_image_url_raw,
        call_openrouter_images_api=call_openrouter_images_api,
        collect_main_image_a_plus_quality_issues=collect_main_image_a_plus_quality_issues,
        collect_main_image_a_plus_severe_subject_clips=collect_main_image_a_plus_severe_subject_clips,
        copy_context=copy_context,
        cover_image_to_exact_size=cover_image_to_exact_size,
        get_main_image_a_plus_layout=get_main_image_a_plus_layout,
        is_omnia_image_outcome_unknown=is_omnia_image_outcome_unknown,
        math=math,
        normalize_main_image_a_plus_mode=normalize_main_image_a_plus_mode,
        normalize_uploaded_input=normalize_uploaded_input,
        prepare_a_plus_reference_style_input=prepare_a_plus_reference_style_input,
        prepare_main_image_a_plus_reference_input=prepare_main_image_a_plus_reference_input,
        prepare_main_image_a_plus_sources_with_repair=prepare_main_image_a_plus_sources_with_repair,
        rank_main_image_a_plus_quality_review=rank_main_image_a_plus_quality_review,
        resize_image_to_target_width=resize_image_to_target_width,
        review_main_image_a_plus_candidate=review_main_image_a_plus_candidate,
        run_main_image_a_plus_designed_module_job=run_main_image_a_plus_designed_module_job,
        select_closest_aspect_ratio=select_closest_aspect_ratio,
        select_main_image_a_plus_safe_aspect_ratio=select_main_image_a_plus_safe_aspect_ratio,
        set_task_progress=set_task_progress,
        split_main_image_a_plus_template=split_main_image_a_plus_template,
        stitch_main_image_a_plus_sections=stitch_main_image_a_plus_sections,
    )


def merge_feature_variant_results(variant_results: list[dict[str, Any]], variant_errors: list[tuple[int, Exception]], requested_output_count: int) -> dict[str, Any]:
    return _feature_helpers.merge_feature_variant_results(
        variant_results,
        variant_errors,
        requested_output_count,
    )


@with_job_image_settings
def run_feature_job(job_context: dict[str, Any]) -> dict[str, Any]:
    return _feature_dispatch.run_feature_job(
        job_context,
        AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY=AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY,
        Any=Any,
        _run_feature_job_once=_run_feature_job_once,
        finalize_canvas_job_result=finalize_canvas_job_result,
        finalize_feature_job_result=finalize_feature_job_result,
        math=math,
        merge_feature_variant_results=merge_feature_variant_results,
        normalize_feature_output_count=normalize_feature_output_count,
        record_background_job_error=record_background_job_error,
        set_task_progress=set_task_progress,
    )


def _detect_solid_first_screen_fill_start(source: Image.Image) -> int:
    return _output_processing._detect_solid_first_screen_fill_start(source, ImageStat=ImageStat)


def detect_first_screen_fill_bounds(source: Image.Image) -> tuple[int, int]:
    return _first_screen_selling_points.detect_first_screen_fill_bounds(
        source,
        ImageStat=ImageStat,
        _detect_solid_first_screen_fill_start=_detect_solid_first_screen_fill_start,
    )


def detect_first_screen_fill_start(source: Image.Image) -> int:
    return _output_processing.detect_first_screen_fill_start(source, detect_first_screen_fill_bounds=detect_first_screen_fill_bounds)


def build_first_screen_fill_mask(source: Image.Image, manual_start: int=0) -> Image.Image:
    return _first_screen_selling_points.build_first_screen_fill_mask(
        source,
        manual_start,
        Image=Image,
        ImageChops=ImageChops,
        ImageDraw=ImageDraw,
        ImageFilter=ImageFilter,
        ImageStat=ImageStat,
        detect_first_screen_fill_bounds=detect_first_screen_fill_bounds,
    )



def find_first_screen_safe_region(mask: Image.Image) -> tuple[int, int, int, int]:
    return _first_screen_selling_points.find_first_screen_safe_region(mask)


def fit_selling_points_region(image: Image.Image, size: tuple[int, int], background) -> Image.Image:
    return _output_processing.fit_selling_points_region(
        image,
        size,
        background,
        Image=Image,
        ImageOps=ImageOps,
    )


def preserve_first_screen_pixels(image_url: str, uploaded_input: Any) -> str:
    return _output_processing.preserve_first_screen_pixels(
        image_url,
        uploaded_input,
        Image=Image,
        ImageOps=ImageOps,
        build_first_screen_fill_mask=build_first_screen_fill_mask,
        find_first_screen_safe_region=find_first_screen_safe_region,
        fit_selling_points_region=fit_selling_points_region,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def selling_points_bottom_blank_fraction(image: Image.Image) -> float:
    return _output_processing.selling_points_bottom_blank_fraction(image, ImageStat=ImageStat)


def request_selling_points_layout(model, prompt, inputs, size, background):
    return _output_processing.request_selling_points_layout(
        model,
        prompt,
        inputs,
        size,
        background,
        AMAZON_A_PLUS_NATIVE_IMAGE_SIZE=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        call_openrouter_images_api=call_openrouter_images_api,
        select_closest_aspect_ratio=select_closest_aspect_ratio,
    )


def run_first_screen_selling_points_job(job_context: dict[str, Any]) -> dict[str, Any]:
    return _first_screen_selling_points.run_first_screen_selling_points_job(
        job_context,
        Image=Image,
        ImageOps=ImageOps,
        build_a_plus_first_screen_user_override=build_a_plus_first_screen_user_override,
        build_first_screen_fill_mask=build_first_screen_fill_mask,
        find_first_screen_safe_region=find_first_screen_safe_region,
        fit_selling_points_region=fit_selling_points_region,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
        request_selling_points_layout=request_selling_points_layout,
    )


def _amazon_a_plus_row_profile(source: Image.Image) -> tuple[list[float], list[float], int]:
    return _output_processing._amazon_a_plus_row_profile(
        source,
        Image=Image,
        math=math,
    )


def detect_amazon_a_plus_section_boundaries(source: Image.Image) -> list[int]:
    return _image_geometry.detect_amazon_a_plus_section_boundaries(
        source,
        AMAZON_TO_WALMART_PAGE_COUNT=AMAZON_TO_WALMART_PAGE_COUNT,
        _amazon_a_plus_row_profile=_amazon_a_plus_row_profile,
    )


def split_amazon_a_plus_source(uploaded_input: Any) -> tuple[list[dict[str, Any]], bool]:
    return _image_geometry.split_amazon_a_plus_source(
        uploaded_input,
        AMAZON_TO_WALMART_PAGE_COUNT=AMAZON_TO_WALMART_PAGE_COUNT,
        Any=Any,
        Image=Image,
        ImageOps=ImageOps,
        detect_amazon_a_plus_section_boundaries=detect_amazon_a_plus_section_boundaries,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        io=io,
        prepare_openrouter_uploaded_input=prepare_openrouter_uploaded_input,
    )


def image_url_as_uploaded_input(image_url: str, name: str) -> dict[str, Any]:
    return _output_processing.image_url_as_uploaded_input(
        image_url,
        name,
        load_image_bytes_from_url=load_image_bytes_from_url,
        prepare_openrouter_uploaded_input=prepare_openrouter_uploaded_input,
    )


AMAZON_TO_WALMART_PAGE_PROMPT = (
    "请把上传的亚马逊 A+ 长图重构为沃尔玛 A+ 内容组中的一页。"
    "完整保留本页内容来源区域中真实存在的商品、人物、包装、品牌、Logo、可读文案、参数、卖点和阅读顺序，不得编造或替换商品事实。"
    "输出单张 1920×1080 横版页面；本页必须拥有明确主题、完整主体、完整文案和独立可用的商业构图。"
    "四页共享同一套品牌色、字体气质、光影、背景材质、装饰语言、留白规则和视觉层级。"
    "本页顶部应自然承接上一页、底部为下一页预留视觉延续，不出现突兀换色、风格跳变或硬接缝。"
    "适配 16:9 时必须重新排版和扩展场景，不得拉伸、压扁、简单裁切或用模糊边框补齐；商品、人物、Logo 和文字均不得被画布边缘截断。"
)


def run_amazon_to_walmart_a_plus_job(job_context: dict[str, Any]) -> dict[str, Any]:
    from Department.视觉设计部.xiaoha.features.amazon_to_walmart_a_plus import (
        run_amazon_to_walmart_a_plus_job as run_job,
    )

    return run_job(
        job_context,
        prepare_openrouter_uploaded_input=prepare_openrouter_uploaded_input,
        split_amazon_a_plus_source=split_amazon_a_plus_source,
        set_task_progress=set_task_progress,
        AMAZON_TO_WALMART_PAGE_COUNT=AMAZON_TO_WALMART_PAGE_COUNT,
        AMAZON_TO_WALMART_PAGE_PROMPT=AMAZON_TO_WALMART_PAGE_PROMPT,
        call_openrouter_images_api=call_openrouter_images_api,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        AMAZON_A_PLUS_NATIVE_IMAGE_SIZE=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        resize_image_to_exact_size=resize_image_to_exact_size,
        AMAZON_TO_WALMART_PAGE_SIZE=AMAZON_TO_WALMART_PAGE_SIZE,
        image_url_as_uploaded_input=image_url_as_uploaded_input,
        uploaded_input_to_data_url=uploaded_input_to_data_url,
    )


def _run_feature_job_once(job_context: dict[str, Any]) -> dict[str, Any]:
    return _feature_dispatch._run_feature_job_once(
        job_context,
        AMAZON_A_PLUS_FEATURE_KEY=AMAZON_A_PLUS_FEATURE_KEY,
        AMAZON_A_PLUS_NATIVE_IMAGE_SIZE=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY=AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY,
        A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY=A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY,
        A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY=A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY,
        A_PLUS_IMAGES_API_FEATURE_KEYS=A_PLUS_IMAGES_API_FEATURE_KEYS,
        Any=Any,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        DEFAULT_BATCH_API_CONCURRENCY=DEFAULT_BATCH_API_CONCURRENCY,
        HD_BATCH_MAX_API_CONCURRENCY=HD_BATCH_MAX_API_CONCURRENCY,
        IMAGE_SMART_ANALYSIS_FEATURE_KEY=IMAGE_SMART_ANALYSIS_FEATURE_KEY,
        JIMENG_HD_API_RESOLUTION=JIMENG_HD_API_RESOLUTION,
        JIMENG_HD_FEATURE_KEY=JIMENG_HD_FEATURE_KEY,
        JIMENG_HD_UPSCALE_REQ_KEY=JIMENG_HD_UPSCALE_REQ_KEY,
        JIMENG_MAX_API_CONCURRENCY=JIMENG_MAX_API_CONCURRENCY,
        MAIN_IMAGE_A_PLUS_FEATURE_KEYS=MAIN_IMAGE_A_PLUS_FEATURE_KEYS,
        MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS=MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS,
        MAIN_IMAGE_A_PLUS_MAX_FILES=MAIN_IMAGE_A_PLUS_MAX_FILES,
        MAIN_IMAGE_A_PLUS_MODE_ELEMENT=MAIN_IMAGE_A_PLUS_MODE_ELEMENT,
        MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST=MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST,
        MAIN_IMAGE_A_PLUS_TEMPLATE_MODES=MAIN_IMAGE_A_PLUS_TEMPLATE_MODES,
        MAX_BATCH_API_CONCURRENCY=MAX_BATCH_API_CONCURRENCY,
        MULTI_REFERENCE_COMPOSER_FEATURE_KEY=MULTI_REFERENCE_COMPOSER_FEATURE_KEY,
        REMOVE_EYELASHES_MAX_API_CONCURRENCY=REMOVE_EYELASHES_MAX_API_CONCURRENCY,
        ThreadPoolExecutor=ThreadPoolExecutor,
        as_completed=as_completed,
        build_amazon_a_plus_layered_result=build_amazon_a_plus_layered_result,
        build_image_smart_analysis_model_prompt=build_image_smart_analysis_model_prompt,
        build_image_smart_analysis_result=build_image_smart_analysis_result,
        call_jimeng_hd_upscale=call_jimeng_hd_upscale,
        call_jimeng_v40=call_jimeng_v40,
        call_openrouter=call_openrouter,
        call_openrouter_images_api=call_openrouter_images_api,
        call_portrait_hd_upscale=call_portrait_hd_upscale,
        capture_runtime=lambda: SimpleNamespace(**globals()),
        copy_context=copy_context,
        extract_image_smart_palette=extract_image_smart_palette,
        finalize_canvas_job_result=finalize_canvas_job_result,
        finalize_feature_job_result=finalize_feature_job_result,
        get_feature_min_output_edge=get_feature_min_output_edge,
        get_main_image_a_plus_layout=get_main_image_a_plus_layout,
        get_main_image_a_plus_template_layout=get_main_image_a_plus_template_layout,
        is_jimeng_model=is_jimeng_model,
        math=math,
        normalize_main_image_a_plus_mode=normalize_main_image_a_plus_mode,
        prepare_uploaded_input=prepare_uploaded_input,
        preserve_first_screen_pixels=preserve_first_screen_pixels,
        process_batch_group=process_batch_group,
        resize_image_to_exact_size=resize_image_to_exact_size,
        resize_uploaded_image_locally=resize_uploaded_image_locally,
        run_ai_background_cutout_job=run_ai_background_cutout_job,
        run_amazon_to_walmart_a_plus_job=run_amazon_to_walmart_a_plus_job,
        run_first_screen_selling_points_job=run_first_screen_selling_points_job,
        run_hero_reverse_job=run_hero_reverse_job,
        run_infinite_canvas_job=run_infinite_canvas_job,
        run_main_image_a_plus_job=run_main_image_a_plus_job,
        run_main_image_a_plus_mobile_adaptation_job=run_main_image_a_plus_mobile_adaptation_job,
        run_main_image_a_plus_text_edit_job=run_main_image_a_plus_text_edit_job,
        select_closest_aspect_ratio=select_closest_aspect_ratio,
        set_task_progress=set_task_progress,
        should_enhance_output_detail=should_enhance_output_detail,
        uploaded_input_to_data_url=uploaded_input_to_data_url,
        upscale_image_to_min_edge=upscale_image_to_min_edge,
    )


def _submit_feature_job_legacy(feature: dict[str, Any], job_context: dict[str, Any]) -> None:
    return _feature_dispatch._submit_feature_job_legacy(
        feature,
        job_context,
        datetime=datetime,
        get_task_runtime=get_task_runtime,
        run_feature_job=run_feature_job,
        set_task_progress=set_task_progress,
        st=st,
    )


def run_queued_feature_job(job_context: dict[str, Any]) -> dict[str, Any]:
    return _feature_dispatch.run_queued_feature_job(
        job_context,
        admitted_job=admitted_job,
        capture_runtime=lambda: SimpleNamespace(**globals()),
        datetime=datetime,
        get_task_runtime=get_task_runtime,
        request_wait_callback=request_wait_callback,
        run_feature_job=run_feature_job,
        set_task_progress=set_task_progress,
    )


def submit_feature_job(feature: dict[str, Any], job_context: dict[str, Any]) -> dict[str, Any]:
    return _feature_dispatch.submit_feature_job(
        feature,
        job_context,
        JIMENG_HD_FEATURE_KEY=JIMENG_HD_FEATURE_KEY,
        JIMENG_HD_GLOBAL_QUEUE_KEY=JIMENG_HD_GLOBAL_QUEUE_KEY,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        clear_task_progress=clear_task_progress,
        datetime=datetime,
        get_request_limiter=get_request_limiter,
        get_task_runtime=get_task_runtime,
        run_queued_feature_job=run_queued_feature_job,
        set_task_progress=set_task_progress,
        st=st,
    )


def submit_main_image_a_plus_mobile_adaptation(source_image: str) -> dict[str, Any]:
    return _output_processing.submit_main_image_a_plus_mobile_adaptation(
        source_image,
        MAIN_IMAGE_A_PLUS_FEATURE_KEY=MAIN_IMAGE_A_PLUS_FEATURE_KEY,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        get_feature_by_key=get_feature_by_key,
        st=st,
        submit_feature_job=submit_feature_job,
    )


def submit_main_image_a_plus_text_edit(source_image: str, point: tuple[int, int], replacement_text: str, font_name: str) -> dict[str, Any]:
    return _feature_helpers.submit_main_image_a_plus_text_edit(
        source_image,
        point,
        replacement_text,
        font_name,
        MAIN_IMAGE_A_PLUS_FEATURE_KEY=MAIN_IMAGE_A_PLUS_FEATURE_KEY,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        build_main_image_a_plus_text_edit_prompt=build_main_image_a_plus_text_edit_prompt,
        get_feature_by_key=get_feature_by_key,
        st=st,
        submit_feature_job=submit_feature_job,
    )


def store_completed_background_job_result(feature_key: str, job_info: dict[str, Any], result: dict[str, Any]) -> None:
    return _feature_helpers.store_completed_background_job_result(
        feature_key,
        job_info,
        result,
        A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY=A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY,
        A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY=A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY,
        HISTORY_PAGE_SIZE=HISTORY_PAGE_SIZE,
        MULTI_REFERENCE_COMPOSER_FEATURE_KEY=MULTI_REFERENCE_COMPOSER_FEATURE_KEY,
        datetime=datetime,
        get_history_cache_key=get_history_cache_key,
        prepare_result_for_frontend=prepare_result_for_frontend,
        set_history_visible_limit=set_history_visible_limit,
        st=st,
        store_local_history_records=store_local_history_records,
    )


def _sync_background_jobs_legacy() -> None:
    return _job_status_views._sync_background_jobs_legacy(
        calculate_finishing_progress=calculate_finishing_progress,
        calculate_smooth_running_progress=calculate_smooth_running_progress,
        clear_task_progress=clear_task_progress,
        format_user_facing_error_message=format_user_facing_error_message,
        get_task_progress=get_task_progress,
        get_task_runtime=get_task_runtime,
        record_background_job_error=record_background_job_error,
        st=st,
        store_completed_background_job_result=store_completed_background_job_result,
        sys=sys,
        time=time,
    )


def redact_background_error_text(value: Any) -> str:
    return _output_processing.redact_background_error_text(value, re=re)


def record_background_job_error(job_id: str, feature_key: str, stage: str, exc: Exception) -> None:
    return _job_status_views.record_background_job_error(
        job_id,
        feature_key,
        stage,
        exc,
        OPENROUTER_ERROR_LOG_FILE=OPENROUTER_ERROR_LOG_FILE,
        _OPENROUTER_ERROR_LOG_LOCK=_OPENROUTER_ERROR_LOG_LOCK,
        datetime=datetime,
        json=json,
        redact_background_error_text=redact_background_error_text,
        sys=sys,
        timezone=timezone,
    )


def get_session_background_job_records() -> list[dict[str, Any]]:
    return _job_status_views.get_session_background_job_records(st=st)


def get_active_session_background_jobs() -> list[dict[str, Any]]:
    return _job_status_views.get_active_session_background_jobs(get_session_background_job_records=get_session_background_job_records)


def _mark_background_job_failed(runtime: TaskRuntime, job_info: dict[str, Any], feature_key: str, job_id: str, exc: Exception) -> None:
    return _job_status_views._mark_background_job_failed(
        runtime,
        job_info,
        feature_key,
        job_id,
        exc,
        clear_task_progress=clear_task_progress,
        format_user_facing_error_message=format_user_facing_error_message,
        get_task_progress=get_task_progress,
        record_background_job_error=record_background_job_error,
        sys=sys,
    )


def sync_background_jobs() -> None:
    return _job_status_views.sync_background_jobs(
        Any=Any,
        _mark_background_job_failed=_mark_background_job_failed,
        calculate_finishing_progress=calculate_finishing_progress,
        calculate_smooth_running_progress=calculate_smooth_running_progress,
        clear_task_progress=clear_task_progress,
        get_session_background_job_records=get_session_background_job_records,
        get_task_progress=get_task_progress,
        get_task_runtime=get_task_runtime,
        st=st,
        store_completed_background_job_result=store_completed_background_job_result,
        time=time,
    )


def inject_processing_transition() -> None:
    return _workbench_assets.inject_processing_transition(
        APP_DIR=APP_DIR,
        build_running_job_spinner_html=build_running_job_spinner_html,
        components=components,
        json=json,
    )


def inject_app_styles() -> None:
    return _workbench_assets.inject_app_styles(inject_processing_transition=inject_processing_transition, st=st)


def inject_clipboard_paste_support() -> None:
    return _workbench_assets.inject_clipboard_paste_support(components=components)


def inject_upload_drag_replace_support() -> None:
    return _workbench_assets.inject_upload_drag_replace_support(components=components)


def inject_upload_reorder_support() -> None:
    return _workbench_assets.inject_upload_reorder_support(
        APP_DIR=APP_DIR,
        UPLOAD_REORDER_QUERY_KEY=UPLOAD_REORDER_QUERY_KEY,
        components=components,
    )



def build_a_plus_first_screen_user_override(custom_prompt: str) -> str:
    return _output_processing.build_a_plus_first_screen_user_override(custom_prompt)


def build_prompt(feature: dict[str, Any], custom_prompt: str, aspect_ratio: str, extra_notes: str) -> str:
    return _feature_prompts.build_prompt(
        feature,
        custom_prompt,
        aspect_ratio,
        extra_notes,
        A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY=A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY,
        A_PLUS_IMAGES_API_FEATURE_KEYS=A_PLUS_IMAGES_API_FEATURE_KEYS,
        BACKGROUND_TEXTURE_FEATURE_KEY=BACKGROUND_TEXTURE_FEATURE_KEY,
        GLOBAL_NO_DISTORTION_RULES=GLOBAL_NO_DISTORTION_RULES,
        IMAGE_SMART_ANALYSIS_FEATURE_KEY=IMAGE_SMART_ANALYSIS_FEATURE_KEY,
        JIMENG_HD_FEATURE_KEY=JIMENG_HD_FEATURE_KEY,
        MAIN_IMAGE_A_PLUS_FEATURE_KEYS=MAIN_IMAGE_A_PLUS_FEATURE_KEYS,
        build_a_plus_first_screen_user_override=build_a_plus_first_screen_user_override,
        get_feature_min_output_edge=get_feature_min_output_edge,
        parse_size_text=parse_size_text,
    )


def _compact_prompt_text(value: str) -> str:
    return _output_processing._compact_prompt_text(value, re=re)


def enforce_global_no_distortion_rules(prompt: str, *, prepend: bool=False) -> str:
    return _output_processing.enforce_global_no_distortion_rules(
        prompt,
        prepend=prepend,
        GLOBAL_NO_DISTORTION_RULES=GLOBAL_NO_DISTORTION_RULES,
    )


def build_infinite_canvas_image_feature_notes(feature_key: str, input_count: int, outpaint_settings: dict[str, int]) -> str:
    return _feature_helpers.build_infinite_canvas_image_feature_notes(
        feature_key,
        input_count,
        outpaint_settings,
        build_outpaint_extra_notes=build_outpaint_extra_notes,
    )


def build_outpaint_extra_notes(top_px: int, bottom_px: int, left_px: int, right_px: int) -> str:
    return _feature_helpers.build_outpaint_extra_notes(
        top_px,
        bottom_px,
        left_px,
        right_px,
    )


def build_jimeng_feature_prompt(feature: dict[str, Any], custom_prompt: str, aspect_ratio: str, extra_notes: str, base_instruction: str='') -> str:
    return _jimeng_client.build_jimeng_feature_prompt(
        feature,
        custom_prompt,
        aspect_ratio,
        extra_notes,
        base_instruction,
        GLOBAL_NO_DISTORTION_RULES=GLOBAL_NO_DISTORTION_RULES,
        JIMENG_PROMPT_MAX_CHARS=JIMENG_PROMPT_MAX_CHARS,
        _compact_prompt_text=_compact_prompt_text,
    )


def build_jimeng_prompt(feature: dict[str, Any], custom_prompt: str, aspect_ratio: str, extra_notes: str) -> str:
    return _provider_inputs.build_jimeng_prompt(
        feature,
        custom_prompt,
        aspect_ratio,
        extra_notes,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        build_jimeng_feature_prompt=build_jimeng_feature_prompt,
    )


def build_jimeng_request_payload(prompt: str, aspect_ratio: str, image_urls: list[str] | None=None, feature_key: str='') -> dict[str, Any]:
    return _jimeng_client.build_jimeng_request_payload(
        prompt,
        aspect_ratio,
        image_urls,
        feature_key,
        Any=Any,
        JIMENG_HD_IMAGE_EDIT_SCALE=JIMENG_HD_IMAGE_EDIT_SCALE,
        JIMENG_HD_OUTPUT_AREA=JIMENG_HD_OUTPUT_AREA,
        JIMENG_IMAGE_EDIT_SCALE=JIMENG_IMAGE_EDIT_SCALE,
        JIMENG_MAX_INPUT_IMAGES=JIMENG_MAX_INPUT_IMAGES,
        JIMENG_PROMPT_MAX_CHARS=JIMENG_PROMPT_MAX_CHARS,
        JIMENG_REQ_KEY=JIMENG_REQ_KEY,
        enforce_global_no_distortion_rules=enforce_global_no_distortion_rules,
    )


def jimeng_signed_post(action: str, body: dict[str, Any], timeout: int=180) -> dict[str, Any]:
    return _jimeng_client.jimeng_signed_post(
        action,
        body,
        timeout,
        ImageOutcomeUnknown=ImageOutcomeUnknown,
        JIMENG_API_ENDPOINT=JIMENG_API_ENDPOINT,
        JIMENG_API_VERSION=JIMENG_API_VERSION,
        JIMENG_CONCURRENT_LIMIT_RETRY_COUNT=JIMENG_CONCURRENT_LIMIT_RETRY_COUNT,
        JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS=JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS,
        JIMENG_SUBMIT_ACTION=JIMENG_SUBMIT_ACTION,
        build_jimeng_auth_headers=build_jimeng_auth_headers,
        get_external_request_kwargs=get_external_request_kwargs,
        get_request_limiter=get_request_limiter,
        is_jimeng_concurrent_limit_error=is_jimeng_concurrent_limit_error,
        json=json,
        requests=requests,
        time=time,
    )


def extract_jimeng_result_images(payload: dict[str, Any]) -> dict[str, Any]:
    return _provider_inputs.extract_jimeng_result_images(
        payload,
        base64=base64,
        image_bytes_to_data_url=image_bytes_to_data_url,
    )


def poll_jimeng_task_result(req_key: str, task_id: str, timeout: int=120) -> dict[str, Any]:
    return _jimeng_client.poll_jimeng_task_result(
        req_key,
        task_id,
        timeout,
        ImageOutcomeUnknown=ImageOutcomeUnknown,
        JIMENG_GET_RESULT_ACTION=JIMENG_GET_RESULT_ACTION,
        JIMENG_RESULT_POLL_INTERVAL_SECONDS=JIMENG_RESULT_POLL_INTERVAL_SECONDS,
        JIMENG_RESULT_RETRY_DELAY_SECONDS=JIMENG_RESULT_RETRY_DELAY_SECONDS,
        extract_jimeng_result_images=extract_jimeng_result_images,
        jimeng_signed_post=jimeng_signed_post,
        json=json,
        time=time,
    )


@limited_request("jimeng")
def call_jimeng_hd_upscale(uploaded_files: list[Any] | None=None) -> dict[str, Any]:
    return _jimeng_client.call_jimeng_hd_upscale(
        uploaded_files,
        JIMENG_HD_API_RESOLUTION=JIMENG_HD_API_RESOLUTION,
        JIMENG_HD_API_SCALE=JIMENG_HD_API_SCALE,
        JIMENG_HD_UPSCALE_REQ_KEY=JIMENG_HD_UPSCALE_REQ_KEY,
        JIMENG_SUBMIT_ACTION=JIMENG_SUBMIT_ACTION,
        _JIMENG_TASK_LOCK=_JIMENG_TASK_LOCK,
        get_jimeng_public_upload_base_url=get_jimeng_public_upload_base_url,
        jimeng_signed_post=jimeng_signed_post,
        poll_jimeng_task_result=poll_jimeng_task_result,
        prepare_jimeng_hd_input_base64=prepare_jimeng_hd_input_base64,
        save_uploaded_inputs_for_jimeng=save_uploaded_inputs_for_jimeng,
    )


def call_portrait_hd_upscale(uploaded_files: list[Any], *, prompt: str='') -> dict[str, Any]:
    return _provider_inputs.call_portrait_hd_upscale(
        uploaded_files,
        prompt=prompt,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        call_openrouter_portrait_hd=call_openrouter_portrait_hd,
    )


def finalize_portrait_upscale_result(result: dict[str, Any], target_size: tuple[int, int]) -> dict[str, Any]:
    return _portrait_results.finalize_portrait_upscale_result(
        result,
        target_size,
        Image=Image,
        ImageOps=ImageOps,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def call_openrouter_hd_then_upscale(model: str, prompt: str, aspect_ratio: str, uploaded_files: list[Any] | None=None) -> dict[str, Any]:
    return _jimeng_client.call_openrouter_hd_then_upscale(
        model,
        prompt,
        aspect_ratio,
        uploaded_files,
        PORTRAIT_HD_DEFAULT_IMAGE_SIZE=PORTRAIT_HD_DEFAULT_IMAGE_SIZE,
        build_portrait_hd_prompt=build_portrait_hd_prompt,
        build_uploaded_input_from_image_url_raw=build_uploaded_input_from_image_url_raw,
        call_jimeng_hd_upscale=call_jimeng_hd_upscale,
        call_openrouter=call_openrouter,
        get_portrait_hd_inputs=get_portrait_hd_inputs,
    )


def call_openrouter_portrait_hd(model: str, prompt: str, aspect_ratio: str, uploaded_files: list[Any] | None=None, source_only: bool=False, preserve_native_resolution: bool=False) -> dict[str, Any]:
    return _jimeng_client.call_openrouter_portrait_hd(
        model,
        prompt,
        aspect_ratio,
        uploaded_files,
        source_only,
        preserve_native_resolution,
        PORTRAIT_HD_DEFAULT_IMAGE_SIZE=current_resolution(),
        build_portrait_hd_prompt=build_portrait_hd_prompt,
        build_portrait_hd_size_instruction=build_portrait_hd_size_instruction,
        call_openrouter_images_api=call_openrouter_images_api,
        finalize_portrait_hd_result=finalize_portrait_hd_result,
        get_portrait_hd_inputs=get_portrait_hd_inputs,
        get_uploaded_input_closest_aspect_ratio=get_uploaded_input_closest_aspect_ratio,
        is_omnia_image_outcome_unknown=is_omnia_image_outcome_unknown,
    )


def call_jimeng_portrait_hd(prompt: str, aspect_ratio: str, uploaded_files: list[Any] | None=None, feature_key: str='hd_batch') -> dict[str, Any]:
    return _portrait_results.call_jimeng_portrait_hd(
        prompt,
        aspect_ratio,
        uploaded_files,
        feature_key,
        build_portrait_hd_prompt=build_portrait_hd_prompt,
        build_portrait_hd_size_instruction=build_portrait_hd_size_instruction,
        call_jimeng_v40=call_jimeng_v40,
        finalize_portrait_hd_result=finalize_portrait_hd_result,
        get_portrait_hd_inputs=get_portrait_hd_inputs,
        get_uploaded_input_closest_aspect_ratio=get_uploaded_input_closest_aspect_ratio,
    )


@limited_request("jimeng")
def call_jimeng_v40(prompt: str, aspect_ratio: str, uploaded_files: list[Any] | None=None, feature_key: str='') -> dict[str, Any]:
    return _portrait_results.call_jimeng_v40(
        prompt,
        aspect_ratio,
        uploaded_files,
        feature_key,
        JIMENG_REQ_KEY=JIMENG_REQ_KEY,
        JIMENG_SUBMIT_ACTION=JIMENG_SUBMIT_ACTION,
        _JIMENG_TASK_LOCK=_JIMENG_TASK_LOCK,
        build_jimeng_request_payload=build_jimeng_request_payload,
        jimeng_signed_post=jimeng_signed_post,
        poll_jimeng_task_result=poll_jimeng_task_result,
        save_uploaded_inputs_for_jimeng=save_uploaded_inputs_for_jimeng,
    )


def extract_response_payload(data: dict[str, Any]) -> dict[str, Any]:
    return _provider_errors.extract_response_payload(data)


def format_openrouter_error_message(error_message: Any) -> str:
    return _provider_errors.format_openrouter_error_message(error_message, re=re)


def format_omnia_error_message(error_message: Any) -> str:
    return _provider_errors.format_omnia_error_message(error_message, re=re)


def format_user_facing_error_message(error_message: Any) -> str:
    return _provider_errors.format_user_facing_error_message(
        error_message,
        GLOBAL_NO_DISTORTION_RULES=GLOBAL_NO_DISTORTION_RULES,
        format_omnia_error_message=format_omnia_error_message,
        format_openrouter_error_message=format_openrouter_error_message,
        re=re,
        redact_background_error_text=redact_background_error_text,
    )


def prepare_omnia_media_uploaded_input(uploaded_file: Any, max_bytes: int=OMNIAKEY_INPUT_TOTAL_BUDGET_BYTES) -> dict[str, Any]:
    return _image_inputs.prepare_omnia_media_uploaded_input(
        uploaded_file,
        max_bytes,
        Image=Image,
        ImageOps=ImageOps,
        OMNIAKEY_INPUT_MIN_BUDGET_BYTES=OMNIAKEY_INPUT_MIN_BUDGET_BYTES,
        OMNIAKEY_MAX_INPUT_IMAGE_EDGE=OMNIAKEY_MAX_INPUT_IMAGE_EDGE,
        Path=Path,
        io=io,
        normalize_uploaded_input=normalize_uploaded_input,
        sanitize_file_name=sanitize_file_name,
    )


def prepare_omnia_media_request_inputs(uploaded_files: list[Any]) -> list[dict[str, Any]]:
    return _provider_inputs.prepare_omnia_media_request_inputs(
        uploaded_files,
        OMNIAKEY_INPUT_MIN_BUDGET_BYTES=OMNIAKEY_INPUT_MIN_BUDGET_BYTES,
        OMNIAKEY_INPUT_TOTAL_BUDGET_BYTES=OMNIAKEY_INPUT_TOTAL_BUDGET_BYTES,
        prepare_omnia_media_uploaded_input=prepare_omnia_media_uploaded_input,
    )


def build_omnia_task_error_message(payload: dict[str, Any]) -> str:
    return _provider_inputs.build_omnia_task_error_message(payload)


class ImageOutcomeUnknown(RuntimeError):
    """A paid request may have been accepted; never submit a replacement automatically."""


class OmniaImageOutcomeUnknown(ImageOutcomeUnknown):
    """The synchronous provider may still be generating; never resubmit automatically."""


@apply_image_settings
def call_omnia_sync_image_api(model: str, prompt: str, uploaded_files: list[Any] | None=None, aspect_ratio: str=DEFAULT_ASPECT_RATIO, resolution: str='', *, size: str='') -> dict[str, Any]:
    if is_ark_seedream_model(model):
        return call_seedream_official_image_api(prompt, uploaded_files, aspect_ratio, resolution, size=size)
    return _call_omnia_sync_image_api(model, prompt, uploaded_files, aspect_ratio, resolution, size=size)


@limited_request("omnia_image")
@managed_omnia_call(kind="image", resume=False)
def _call_omnia_sync_image_api(model: str, prompt: str, uploaded_files: list[Any] | None=None, aspect_ratio: str=DEFAULT_ASPECT_RATIO, resolution: str='', *, size: str='') -> dict[str, Any]:
    return _provider_clients.call_omnia_sync_image_api(
        model,
        prompt,
        uploaded_files,
        aspect_ratio,
        resolution,
        size=size,
        Any=Any,
        GEMINI_IMAGE_ASPECT_RATIOS=GEMINI_IMAGE_ASPECT_RATIOS,
        Image=Image,
        OMNIAKEY_API_BASE=OMNIAKEY_API_BASE,
        OMNIAKEY_CONNECT_TIMEOUT_SECONDS=OMNIAKEY_CONNECT_TIMEOUT_SECONDS,
        OMNIAKEY_SYNC_IMAGE_TIMEOUT_SECONDS=OMNIAKEY_SYNC_IMAGE_TIMEOUT_SECONDS,
        OMNIA_IMAGE_MODEL_LABELS=OMNIA_IMAGE_MODEL_LABELS,
        OmniaImageOutcomeUnknown=OmniaImageOutcomeUnknown,
        base64=base64,
        build_omnia_task_error_message=build_omnia_task_error_message,
        enforce_global_no_distortion_rules=enforce_global_no_distortion_rules,
        get_external_request_kwargs=get_external_request_kwargs,
        get_uploaded_input_closest_aspect_ratio=get_uploaded_input_closest_aspect_ratio,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_omnia_api_key=load_omnia_api_key,
        math=math,
        prepare_omnia_media_request_inputs=prepare_omnia_media_request_inputs,
        re=re,
        record_omnia_provider_status=record_omnia_provider_status,
        redact_background_error_text=redact_background_error_text,
        requests=requests,
    )


@apply_image_settings
def call_omnia_image_api(model: str, prompt: str, uploaded_files: list[Any] | None=None, aspect_ratio: str=DEFAULT_ASPECT_RATIO, resolution: str='', max_attempts: int | None=None) -> dict[str, Any]:
    if is_ark_seedream_model(model):
        return call_seedream_official_image_api(prompt, uploaded_files, aspect_ratio, resolution)
    return _provider_clients.call_omnia_image_api(
        model,
        prompt,
        uploaded_files,
        aspect_ratio,
        resolution,
        max_attempts,
        call_omnia_media_image_api=call_omnia_media_image_api,
        resolve_omnia_image_model=resolve_omnia_image_model,
    )


@apply_image_settings
def call_omnia_media_image_api(model: str, prompt: str, uploaded_files: list[Any] | None=None, aspect_ratio: str=DEFAULT_ASPECT_RATIO, resolution: str='', max_attempts: int | None=None) -> dict[str, Any]:
    if is_ark_seedream_model(model):
        return call_seedream_official_image_api(prompt, uploaded_files, aspect_ratio, resolution)
    return _call_omnia_media_image_api(model, prompt, uploaded_files, aspect_ratio, resolution, max_attempts)


@limited_request("omnia_image")
@managed_omnia_call(kind="image", resume=False)
def _call_omnia_media_image_api(model: str, prompt: str, uploaded_files: list[Any] | None=None, aspect_ratio: str=DEFAULT_ASPECT_RATIO, resolution: str='', max_attempts: int | None=None) -> dict[str, Any]:
    return _provider_clients.call_omnia_media_image_api(
        model,
        prompt,
        uploaded_files,
        aspect_ratio,
        resolution,
        max_attempts,
        Any=Any,
        GEMINI_IMAGE_ASPECT_RATIOS=GEMINI_IMAGE_ASPECT_RATIOS,
        GEMINI_IMAGE_SIZES=GEMINI_IMAGE_SIZES,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        OMNIAKEY_CONNECT_TIMEOUT_SECONDS=OMNIAKEY_CONNECT_TIMEOUT_SECONDS,
        OMNIAKEY_MEDIA_MAX_ATTEMPTS=OMNIAKEY_MEDIA_MAX_ATTEMPTS,
        OMNIAKEY_MEDIA_RETRY_DELAYS=OMNIAKEY_MEDIA_RETRY_DELAYS,
        OMNIAKEY_MEDIA_TASKS_URL=OMNIAKEY_MEDIA_TASKS_URL,
        OMNIAKEY_MEDIA_TRANSIENT_STATUS_CODES=OMNIAKEY_MEDIA_TRANSIENT_STATUS_CODES,
        OMNIAKEY_READ_TIMEOUT_SECONDS=OMNIAKEY_READ_TIMEOUT_SECONDS,
        OMNIAKEY_TASK_RECEIPTS_FILE=OMNIAKEY_TASK_RECEIPTS_FILE,
        OmniaImageOutcomeUnknown=OmniaImageOutcomeUnknown,
        _OPENROUTER_ERROR_LOG_LOCK=_OPENROUTER_ERROR_LOG_LOCK,
        base64=base64,
        build_omnia_task_error_message=build_omnia_task_error_message,
        collect_omnia_image_task=collect_omnia_image_task,
        current_omnia_call_metadata=current_omnia_call_metadata,
        datetime=datetime,
        enforce_global_no_distortion_rules=enforce_global_no_distortion_rules,
        get_external_request_kwargs=get_external_request_kwargs,
        get_request_limiter=get_request_limiter,
        get_uploaded_input_closest_aspect_ratio=get_uploaded_input_closest_aspect_ratio,
        json=json,
        load_omnia_api_key=load_omnia_api_key,
        prepare_omnia_media_request_inputs=prepare_omnia_media_request_inputs,
        record_omnia_provider_status=record_omnia_provider_status,
        record_omnia_task=record_omnia_task,
        requests=requests,
        resolve_omnia_image_model=resolve_omnia_image_model,
        time=time,
        timezone=timezone,
        uuid4=uuid4,
    )


@limited_request("omnia_image")
@managed_omnia_call(kind="image", resume=True)
def resume_omnia_image_task(task_id: str, model: str=NANO_BANANA_MODEL, resolution: str='') -> dict[str, Any]:
    return _provider_clients.resume_omnia_image_task(
        task_id,
        model,
        resolution,
        collect_omnia_image_task=collect_omnia_image_task,
        load_omnia_api_key=load_omnia_api_key,
        re=re,
        resolve_omnia_image_model=resolve_omnia_image_model,
    )


def collect_omnia_image_task(task_id: str, create_data: dict[str, Any], api_key: str, omnia_model: str, normalized_resolution: str) -> dict[str, Any]:
    return _provider_clients.collect_omnia_image_task(
        task_id,
        create_data,
        api_key,
        omnia_model,
        normalized_resolution,
        Any=Any,
        OMNIAKEY_CONNECT_TIMEOUT_SECONDS=OMNIAKEY_CONNECT_TIMEOUT_SECONDS,
        OMNIAKEY_MEDIA_TASKS_URL=OMNIAKEY_MEDIA_TASKS_URL,
        OMNIAKEY_MEDIA_TRANSIENT_STATUS_CODES=OMNIAKEY_MEDIA_TRANSIENT_STATUS_CODES,
        OMNIAKEY_READ_TIMEOUT_SECONDS=OMNIAKEY_READ_TIMEOUT_SECONDS,
        OMNIAKEY_TASK_POLL_INTERVAL_SECONDS=OMNIAKEY_TASK_POLL_INTERVAL_SECONDS,
        OMNIAKEY_TASK_TIMEOUT_SECONDS=OMNIAKEY_TASK_TIMEOUT_SECONDS,
        OMNIA_IMAGE_MODEL_LABELS=OMNIA_IMAGE_MODEL_LABELS,
        OmniaImageOutcomeUnknown=OmniaImageOutcomeUnknown,
        build_omnia_task_error_message=build_omnia_task_error_message,
        get_external_request_kwargs=get_external_request_kwargs,
        get_request_limiter=get_request_limiter,
        image_bytes_to_data_url=image_bytes_to_data_url,
        record_background_job_error=record_background_job_error,
        record_omnia_provider_status=record_omnia_provider_status,
        requests=requests,
        time=time,
        urllib=urllib,
    )


@apply_image_settings
def call_openrouter_images_api(model: str, prompt: str, uploaded_files: list[Any] | None=None, aspect_ratio: str=DEFAULT_ASPECT_RATIO, resolution: str='', max_attempts: int | None=None) -> dict[str, Any]:
    if is_ark_seedream_model(model):
        return call_seedream_official_image_api(prompt, uploaded_files, aspect_ratio, resolution)
    return _provider_clients.call_openrouter_images_api(
        model,
        prompt,
        uploaded_files,
        aspect_ratio,
        resolution,
        max_attempts,
        call_omnia_image_api=call_omnia_image_api,
        resolve_omnia_image_model=resolve_omnia_image_model,
    )


def call_seedream_official_image_api(prompt: str, uploaded_files: list[Any] | None=None, aspect_ratio: str=DEFAULT_ASPECT_RATIO, resolution: str='', *, size: str='') -> dict[str, Any]:
    requested_size = size or resolution or current_resolution()
    if aspect_ratio and aspect_ratio != DEFAULT_ASPECT_RATIO:
        prompt = str(prompt) + f"\n输出图片宽高比：{aspect_ratio}。"
    return call_ark_seedream_images_api(prompt, uploaded_files, size=requested_size)


@limited_request("ark")
def call_ark_seedream_images_api(prompt: str, uploaded_files: list[Any] | None=None, size: str=ARK_SEEDREAM_5_PRO_SIZE, *, layer_decomposition: bool=False, output_format: str | None=None, response_format: str="url", watermark: bool=True, optimize_prompt_mode: str | None=None, background: str | None=None, interactive_edit: bool=False) -> dict[str, Any]:
    return _provider_clients.call_ark_seedream_images_api(
        prompt,
        uploaded_files,
        size,
        layer_decomposition=layer_decomposition,
        output_format=output_format,
        response_format=response_format,
        watermark=watermark,
        optimize_prompt_mode=optimize_prompt_mode,
        background=background,
        interactive_edit=interactive_edit,
        ARK_IMAGES_CONNECT_TIMEOUT_SECONDS=ARK_IMAGES_CONNECT_TIMEOUT_SECONDS,
        ARK_IMAGES_MAX_ATTEMPTS=ARK_IMAGES_MAX_ATTEMPTS,
        ARK_IMAGES_READ_TIMEOUT_SECONDS=ARK_IMAGES_READ_TIMEOUT_SECONDS,
        ARK_IMAGES_RETRY_DELAYS=ARK_IMAGES_RETRY_DELAYS,
        ARK_IMAGES_URL=ARK_IMAGES_URL,
        ARK_SEEDREAM_5_PRO_MODEL=ARK_SEEDREAM_5_PRO_MODEL,
        ARK_SEEDREAM_5_PRO_SIZE=ARK_SEEDREAM_5_PRO_SIZE,
        Any=Any,
        ImageOutcomeUnknown=ImageOutcomeUnknown,
        enforce_global_no_distortion_rules=enforce_global_no_distortion_rules,
        file_to_data_url=file_to_data_url,
        get_external_request_kwargs=get_external_request_kwargs,
        get_request_limiter=get_request_limiter,
        load_ark_api_key=load_ark_api_key,
        prepare_ark_seedream_uploaded_input=prepare_ark_seedream_uploaded_input,
        requests=requests,
        time=time,
    )


@limited_request("omnia_text")
@managed_omnia_call(kind="text", resume=False)
def call_omnia_chat_api(model: str, prompt: str, uploaded_files: list[Any]) -> dict[str, Any]:
    return _provider_clients.call_omnia_chat_api(
        model,
        prompt,
        uploaded_files,
        Any=Any,
        ImageOutcomeUnknown=ImageOutcomeUnknown,
        OMNIAKEY_CHAT_COMPLETIONS_URL=OMNIAKEY_CHAT_COMPLETIONS_URL,
        OMNIAKEY_MEDIA_RETRY_DELAYS=OMNIAKEY_MEDIA_RETRY_DELAYS,
        OMNIAKEY_VISION_TEXT_FALLBACK_MODELS=OMNIAKEY_VISION_TEXT_FALLBACK_MODELS,
        OMNIAKEY_VISION_TEXT_MODEL=OMNIAKEY_VISION_TEXT_MODEL,
        extract_response_payload=extract_response_payload,
        file_to_data_url=file_to_data_url,
        get_external_request_kwargs=get_external_request_kwargs,
        get_request_limiter=get_request_limiter,
        load_omnia_api_key=load_omnia_api_key,
        prepare_openrouter_request_inputs=prepare_openrouter_request_inputs,
        record_omnia_model=record_omnia_model,
        record_omnia_provider_status=record_omnia_provider_status,
        redact_background_error_text=redact_background_error_text,
        requests=requests,
        time=time,
    )


def call_openrouter(model: str, prompt: str, uploaded_files: list[Any], output_mode: str, aspect_ratio: str=DEFAULT_ASPECT_RATIO, image_size: str='') -> dict[str, Any]:
    return _provider_clients.call_openrouter(
        model,
        prompt,
        uploaded_files,
        output_mode,
        aspect_ratio,
        image_size,
        call_omnia_chat_api=call_omnia_chat_api,
        call_openrouter_images_api=call_openrouter_images_api,
        enforce_global_no_distortion_rules=enforce_global_no_distortion_rules,
    )


def decode_data_url(data_url: str) -> tuple[bytes, str] | None:
    return _image_primitives.decode_data_url(
        data_url,
        base64=base64,
        urllib=urllib,
    )


def image_bytes_to_data_url(image_bytes: bytes, mime_type: str='image/png') -> str:
    return _image_primitives.image_bytes_to_data_url(
        image_bytes,
        mime_type,
        Image=Image,
        base64=base64,
        io=io,
    )


def load_image_bytes_from_url(image_url: str) -> tuple[bytes, str]:
    return _image_inputs.load_image_bytes_from_url(
        image_url,
        DB_IMAGE_DIR=DB_IMAGE_DIR,
        HISTORY_STATIC_ROUTE_PREFIX=HISTORY_STATIC_ROUTE_PREFIX,
        JIMENG_UPLOAD_ROUTE_PREFIX=JIMENG_UPLOAD_ROUTE_PREFIX,
        Path=Path,
        REQUEST_PROXIES=REQUEST_PROXIES,
        decode_data_url=decode_data_url,
        ensure_jimeng_upload_dir=ensure_jimeng_upload_dir,
        get_external_request_kwargs=get_external_request_kwargs,
        get_history_public_base_url=get_history_public_base_url,
        get_jimeng_public_upload_base_url=get_jimeng_public_upload_base_url,
        get_request_limiter=get_request_limiter,
        mimetypes=mimetypes,
        requests=requests,
        resolve_local_static_image_source=resolve_local_static_image_source,
        urllib=urllib,
    )


def is_main_image_a_plus_mobile_canvas(image_source: str) -> bool:
    return _layout_selection.is_main_image_a_plus_mobile_canvas(
        image_source,
        Image=Image,
        ImageOps=ImageOps,
        io=io,
        is_main_image_a_plus_mobile_size=is_main_image_a_plus_mobile_size,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def build_main_image_a_plus_crop_archive(image_bytes: bytes, preset_key: str, base_name: str='a_plus_result') -> dict[str, Any]:
    return _gallery_data.build_main_image_a_plus_crop_archive(
        image_bytes,
        preset_key,
        base_name,
        AMAZON_A_PLUS_MAX_PIXELS=AMAZON_A_PLUS_MAX_PIXELS,
        Image=Image,
        ImageOps=ImageOps,
        MAIN_IMAGE_A_PLUS_CROP_PRESETS=MAIN_IMAGE_A_PLUS_CROP_PRESETS,
        MAIN_IMAGE_A_PLUS_MAX_MOBILE_SCREENS=MAIN_IMAGE_A_PLUS_MAX_MOBILE_SCREENS,
        MAIN_IMAGE_A_PLUS_MIN_MOBILE_SCREENS=MAIN_IMAGE_A_PLUS_MIN_MOBILE_SCREENS,
        Path=Path,
        infer_main_image_a_plus_screen_count=infer_main_image_a_plus_screen_count,
        io=io,
        sanitize_file_name=sanitize_file_name,
        zipfile=zipfile,
    )


@st.cache_data(show_spinner=False, ttl=900, max_entries=32)
def build_main_image_a_plus_crop_archive_from_source(image_source: str, preset_key: str, base_name: str) -> dict[str, Any]:
    return _gallery_data.build_main_image_a_plus_crop_archive_from_source(
        image_source,
        preset_key,
        base_name,
        build_main_image_a_plus_crop_archive=build_main_image_a_plus_crop_archive,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def infer_main_image_a_plus_crop_base_name(image_source: str, index: int) -> str:
    return _output_processing.infer_main_image_a_plus_crop_base_name(
        image_source,
        index,
        Path=Path,
        urllib=urllib,
    )


def render_main_image_a_plus_crop_downloads(image_sources: list[str], key_prefix: str, base_names: list[str] | None=None) -> None:
    return _main_image_a_plus_image_tools.render_main_image_a_plus_crop_downloads(
        image_sources,
        key_prefix,
        base_names,
        MAIN_IMAGE_A_PLUS_CROP_PRESETS=MAIN_IMAGE_A_PLUS_CROP_PRESETS,
        build_main_image_a_plus_crop_archive_from_source=build_main_image_a_plus_crop_archive_from_source,
        infer_main_image_a_plus_crop_base_name=infer_main_image_a_plus_crop_base_name,
        sanitize_file_name=sanitize_file_name,
        st=st,
    )


def render_main_image_a_plus_text_editor(source_image: str, key_prefix: str) -> None:
    return _main_image_a_plus_editor.render_main_image_a_plus_text_editor(
        source_image,
        key_prefix,
        MAIN_IMAGE_A_PLUS_TEXT_FONT_OPTIONS=MAIN_IMAGE_A_PLUS_TEXT_FONT_OPTIONS,
        consume_main_image_a_plus_text_edit_point=consume_main_image_a_plus_text_edit_point,
        format_user_facing_error_message=format_user_facing_error_message,
        get_main_image_a_plus_text_edit_signature=get_main_image_a_plus_text_edit_signature,
        render_main_image_a_plus_text_edit_picker=render_main_image_a_plus_text_edit_picker,
        sanitize_file_name=sanitize_file_name,
        st=st,
        submit_main_image_a_plus_text_edit=submit_main_image_a_plus_text_edit,
    )


def upscale_image_to_min_edge(image_url: str, min_edge: int, enhance_detail: bool=False) -> str:
    return _image_geometry.upscale_image_to_min_edge(
        image_url,
        min_edge,
        enhance_detail,
        Image=Image,
        ImageEnhance=ImageEnhance,
        ImageFilter=ImageFilter,
        MIN_OUTPUT_EDGE=MIN_OUTPUT_EDGE,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
        math=math,
    )


def fit_image_to_canvas_without_distortion(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    return _image_geometry.fit_image_to_canvas_without_distortion(
        image,
        target_width,
        target_height,
        Image=Image,
        ImageOps=ImageOps,
        ImageStat=ImageStat,
    )


def cover_image_to_canvas_without_distortion(image: Image.Image, target_width: int, target_height: int, horizontal_anchor: str='center', vertical_anchor: str='center') -> Image.Image:
    return _image_geometry.cover_image_to_canvas_without_distortion(
        image,
        target_width,
        target_height,
        horizontal_anchor,
        vertical_anchor,
        Image=Image,
        ImageOps=ImageOps,
        math=math,
    )


def fit_image_to_canvas_with_continuous_background(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    return _image_geometry.fit_image_to_canvas_with_continuous_background(
        image,
        target_width,
        target_height,
        Image=Image,
        ImageEnhance=ImageEnhance,
        ImageFilter=ImageFilter,
        ImageOps=ImageOps,
        cover_image_to_canvas_without_distortion=cover_image_to_canvas_without_distortion,
    )


def resize_image_to_target_width(image_url: str, target_width: int) -> tuple[str, tuple[int, int]]:
    return _image_geometry.resize_image_to_target_width(
        image_url,
        target_width,
        Image=Image,
        ImageOps=ImageOps,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def resize_image_to_exact_size(image_url: str, target_width: int, target_height: int) -> str:
    return _output_processing.resize_image_to_exact_size(
        image_url,
        target_width,
        target_height,
        Image=Image,
        fit_image_to_canvas_without_distortion=fit_image_to_canvas_without_distortion,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def resize_uploaded_image_locally(uploaded_input: Any, target_width: int, target_height: int) -> str:
    return _portrait_results.resize_uploaded_image_locally(
        uploaded_input,
        target_width,
        target_height,
        Image=Image,
        ImageOps=ImageOps,
        fit_image_to_canvas_without_distortion=fit_image_to_canvas_without_distortion,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
    )


def cover_image_to_exact_size(image_url: str, target_width: int, target_height: int, horizontal_anchor: str='center', vertical_anchor: str='center') -> str:
    return _image_geometry.cover_image_to_exact_size(
        image_url,
        target_width,
        target_height,
        horizontal_anchor,
        vertical_anchor,
        Image=Image,
        fit_image_to_canvas_with_continuous_background=fit_image_to_canvas_with_continuous_background,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def parse_size_text(size_text: str) -> tuple[int, int] | None:
    return _output_processing.parse_size_text(
        size_text,
        AMAZON_A_PLUS_MAX_EDGE=AMAZON_A_PLUS_MAX_EDGE,
        AMAZON_A_PLUS_MAX_PIXELS=AMAZON_A_PLUS_MAX_PIXELS,
        re=re,
    )


def build_amazon_a_plus_layered_result(result: dict[str, Any], target_size: tuple[int, int] | None) -> dict[str, Any]:
    return _main_image_a_plus_image_tools.build_amazon_a_plus_layered_result(
        result,
        target_size,
        Image=Image,
        ImageOps=ImageOps,
        build_commercial_a_plus_background=build_commercial_a_plus_background,
        build_layered_a_plus=build_layered_a_plus,
        datetime=datetime,
        fit_green_screen_to_canvas=fit_green_screen_to_canvas,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
        uuid4=uuid4,
    )


def uploaded_input_to_data_url(uploaded_input: Any) -> str:
    return _upload_actions.uploaded_input_to_data_url(
        uploaded_input,
        Path=Path,
        build_gallery_preview_data_url=build_gallery_preview_data_url,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        image_bytes_to_data_url=image_bytes_to_data_url,
        mimetypes=mimetypes,
    )


def render_outpaint_extension_preview_card(uploaded_file: Any, top_px: int, bottom_px: int, left_px: int, right_px: int, component_key: str, max_preview_edge: int=760, drag_state_keys: dict[str, str] | None=None) -> None:
    return _gallery_views.render_outpaint_extension_preview_card(
        uploaded_file,
        top_px,
        bottom_px,
        left_px,
        right_px,
        component_key,
        max_preview_edge,
        drag_state_keys,
        Image=Image,
        ImageDraw=ImageDraw,
        ImageOps=ImageOps,
        OUTPAINT_DRAG_QUERY_KEY=OUTPAINT_DRAG_QUERY_KEY,
        OUTPAINT_DRAG_STEP_PX=OUTPAINT_DRAG_STEP_PX,
        components=components,
        get_outpaint_extension_limits=get_outpaint_extension_limits,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        json=json,
        st=st,
    )


def render_outpaint_extension_preview(uploaded_files: list[Any], top_px: int, bottom_px: int, left_px: int, right_px: int) -> None:
    return _download_views.render_outpaint_extension_preview(
        uploaded_files,
        top_px,
        bottom_px,
        left_px,
        right_px,
        render_outpaint_extension_preview_card=render_outpaint_extension_preview_card,
        st=st,
    )


def render_upload_delete_button(widget_key: str, item_index: int, button_key: str) -> None:
    return _download_views.render_upload_delete_button(
        widget_key,
        item_index,
        button_key,
        remove_upload_cache_item=remove_upload_cache_item,
        reset_upload_widget=reset_upload_widget,
        st=st,
    )


def render_uploaded_preview_card(uploaded_input: Any, widget_key: str, item_index: int, component_key: str, preview_renderer: Any | None=None, allow_reorder: bool=False, item_count: int=1) -> None:
    return _upload_views.render_uploaded_preview_card(
        uploaded_input,
        widget_key,
        item_index,
        component_key,
        preview_renderer,
        allow_reorder,
        item_count,
        get_replace_uploader_widget_key=get_replace_uploader_widget_key,
        remove_upload_cache_item=remove_upload_cache_item,
        render_frame_uploader=render_frame_uploader,
        reorder_upload_cache_item=reorder_upload_cache_item,
        replace_upload_cache_item=replace_upload_cache_item,
        reset_upload_widget=reset_upload_widget,
        st=st,
    )


def render_uploaded_previews(uploaded_file: Any | None, widget_key: str) -> None:
    return _download_views.render_uploaded_previews(
        uploaded_file,
        widget_key,
        render_uploaded_preview_card=render_uploaded_preview_card,
        st=st,
    )


def render_uploaded_gallery(files: list[Any], empty_text: str, widget_key: str, slot_count: int=5, preview_renderer: Any | None=None, allow_reorder: bool=False) -> None:
    return _upload_views.render_uploaded_gallery(
        files,
        empty_text,
        widget_key,
        slot_count,
        preview_renderer,
        allow_reorder,
        render_uploaded_preview_card=render_uploaded_preview_card,
        st=st,
    )


def image_source_to_data_url(image_source: str) -> str | None:
    return _download_views.image_source_to_data_url(
        image_source,
        image_bytes_to_data_url=image_bytes_to_data_url,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


@st.cache_data(show_spinner=False, max_entries=256)
def build_gallery_preview_data_url(image_bytes: bytes, mime_type: str) -> tuple[str, int, int] | None:
    return _download_views.build_gallery_preview_data_url(
        image_bytes,
        mime_type,
        GALLERY_PREVIEW_MAX_EDGE=GALLERY_PREVIEW_MAX_EDGE,
        GALLERY_PREVIEW_TARGET_BYTES=GALLERY_PREVIEW_TARGET_BYTES,
        Image=Image,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
    )


def build_gallery_item(image_source: str, compress_preview: bool=True, include_full_src: bool=True, full_image_source: str='', direct_src: bool=False, embed_full_src: bool=False) -> dict[str, Any] | None:
    return _gallery_data.build_gallery_item(
        image_source,
        compress_preview,
        include_full_src,
        full_image_source,
        direct_src,
        embed_full_src,
        Any=Any,
        Image=Image,
        build_gallery_preview_data_url=build_gallery_preview_data_url,
        decode_data_url=decode_data_url,
        get_history_public_base_url=get_history_public_base_url,
        get_jimeng_public_upload_base_url=get_jimeng_public_upload_base_url,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        is_managed_static_image_url=is_managed_static_image_url,
        load_image_bytes_from_url=load_image_bytes_from_url,
        urllib=urllib,
        build_history_download_public_url=build_history_download_public_url,
    )


def render_zoomable_image_gallery(images: list[str], columns: int, thumb_height: int | None, component_key: str, fit_mode: str='contain', max_width_percent: int=100, context_delete_token: str | None=None, compress_preview: bool=True, include_full_src: bool=True, full_images: list[str] | None=None, download_names: list[str] | None=None, direct_src: bool=False, embed_full_src: bool=False, allow_native_image_download: bool=True, native_fullscreen_context_menu: bool=False) -> None:
    return _gallery_views.render_zoomable_image_gallery(
        images,
        columns,
        thumb_height,
        component_key,
        fit_mode,
        max_width_percent,
        context_delete_token,
        compress_preview,
        include_full_src,
        full_images,
        download_names,
        direct_src,
        embed_full_src,
        allow_native_image_download,
        native_fullscreen_context_menu,
        Any=Any,
        HISTORY_STATIC_ROUTE_PREFIX=HISTORY_STATIC_ROUTE_PREFIX,
        JIMENG_UPLOAD_ROUTE_PREFIX=JIMENG_UPLOAD_ROUTE_PREFIX,
        UPLOAD_DELETE_QUERY_KEY=UPLOAD_DELETE_QUERY_KEY,
        build_gallery_item=build_gallery_item,
        get_history_public_base_url=get_history_public_base_url,
        get_image_extension_from_mime=get_image_extension_from_mime,
        get_jimeng_public_upload_base_url=get_jimeng_public_upload_base_url,
        json=json,
        os=os,
        st=st,
        urllib=urllib,
    )


def render_frame_uploader(label: str, **kwargs):
    from Department.视觉设计部.xiaoha.upload_frames import render_file_frame
    return render_file_frame(SimpleNamespace(**globals()), label, **kwargs)


def render_single_image_uploader(label: str, key: str, help_text: str='') -> Any | None:
    return _upload_views.render_single_image_uploader(
        label,
        key,
        help_text,
        clear_upload_cache=clear_upload_cache,
        consume_pending_upload_replacement=consume_pending_upload_replacement,
        get_uploader_widget_key=get_uploader_widget_key,
        load_upload_cache=load_upload_cache,
        render_frame_uploader=render_frame_uploader,
        reset_upload_widget=reset_upload_widget,
        save_upload_cache=save_upload_cache,
        st=st,
    )


def render_compact_element_image_uploader(label: str, key: str, help_text: str='') -> Any | None:
    return _upload_views.render_compact_element_image_uploader(
        label,
        key,
        help_text,
        clear_upload_cache=clear_upload_cache,
        get_uploader_widget_key=get_uploader_widget_key,
        load_upload_cache=load_upload_cache,
        render_frame_uploader=render_frame_uploader,
        reset_upload_widget=reset_upload_widget,
        save_upload_cache=save_upload_cache,
        st=st,
    )


def render_first_screen_material_uploader(key: str, *, hero: bool=False) -> list[Any]:
    return _download_views.render_first_screen_material_uploader(
        key,
        hero=hero,
        render_multi_image_uploader=render_multi_image_uploader,
        render_single_image_uploader=render_single_image_uploader,
        st=st,
    )


def render_multi_image_uploader(label: str, key: str, help_text: str='', max_files: int=3, preview_renderer: Any | None=None, preview_slot_count: int | None=None, allow_reorder: bool=False, preview_area_height: int | None=None, show_clear_button: bool=True) -> list[Any]:
    return _upload_views.render_multi_image_uploader(
        label,
        key,
        help_text,
        max_files,
        preview_renderer,
        preview_slot_count,
        allow_reorder,
        preview_area_height,
        show_clear_button,
        clear_upload_cache=clear_upload_cache,
        consume_pending_upload_replacement=consume_pending_upload_replacement,
        get_uploader_widget_key=get_uploader_widget_key,
        load_upload_cache=load_upload_cache,
        render_frame_uploader=render_frame_uploader,
        render_uploaded_gallery=render_uploaded_gallery,
        reset_upload_widget=reset_upload_widget,
        save_upload_cache=save_upload_cache,
        st=st,
    )


def render_reference_slot_uploaders(slot_prefix: str, slot_count: int=5) -> list[Any]:
    return _upload_views.render_reference_slot_uploaders(
        slot_prefix,
        slot_count,
        Any=Any,
        consume_pending_upload_replacement=consume_pending_upload_replacement,
        get_uploader_widget_key=get_uploader_widget_key,
        load_upload_cache=load_upload_cache,
        render_frame_uploader=render_frame_uploader,
        reset_upload_widget=reset_upload_widget,
        save_upload_cache=save_upload_cache,
        st=st,
    )


def build_result_download_sources(images: list[str], history_records: list[dict[str, Any]] | None=None) -> list[str]:
    return _portrait_results.build_result_download_sources(
        images,
        history_records,
        build_history_download_public_url=build_history_download_public_url,
        flatten_history_items=flatten_history_items,
    )


def render_result_preview(images: list[str], show_title: bool=True, download_images: list[str] | None=None, max_width_percent: int=25, feature_key: str='') -> None:
    return _result_views.render_result_preview(
        images,
        show_title,
        download_images,
        max_width_percent,
        feature_key,
        build_result_download_sources=build_result_download_sources,
        render_result_loading=render_result_loading,
        render_zoomable_image_gallery=render_zoomable_image_gallery,
        st=st,
    )


def render_result_preview_with_captions(images: list[str], captions: list[str], feature_key: str, download_images: list[str] | None=None) -> None:
    return _result_views.render_result_preview_with_captions(
        images,
        captions,
        feature_key,
        download_images,
        build_result_download_sources=build_result_download_sources,
        render_result_preview=render_result_preview,
        render_zoomable_image_gallery=render_zoomable_image_gallery,
        st=st,
    )


def render_before_after_compare_gallery(source_images: list[str], result_images: list[str], captions: list[str], feature_key: str, outpaint_alignments: list[dict[str, Any]] | None=None, download_images: list[str] | None=None) -> None:
    return _gallery_views.render_before_after_compare_gallery(
        source_images,
        result_images,
        captions,
        feature_key,
        outpaint_alignments,
        download_images,
        Any=Any,
        HISTORY_STATIC_ROUTE_PREFIX=HISTORY_STATIC_ROUTE_PREFIX,
        JIMENG_UPLOAD_ROUTE_PREFIX=JIMENG_UPLOAD_ROUTE_PREFIX,
        Path=Path,
        REFERENCE_IMAGE_EXTENSIONS=REFERENCE_IMAGE_EXTENSIONS,
        build_direct_image_download_url=build_direct_image_download_url,
        build_gallery_item=build_gallery_item,
        build_history_download_public_url=build_history_download_public_url,
        build_result_download_sources=build_result_download_sources,
        components=components,
        get_history_public_base_url=get_history_public_base_url,
        get_jimeng_public_upload_base_url=get_jimeng_public_upload_base_url,
        json=json,
        os=os,
        re=re,
        render_result_preview_with_captions=render_result_preview_with_captions,
        urllib=urllib,
    )


def sanitize_history_download_name_part(value: Any, fallback: str) -> str:
    return _xiaoha_history_downloads.sanitize_history_download_name_part(
        value,
        fallback,
        re=re,
    )


def format_history_download_timestamp(created_at: Any) -> str:
    return _xiaoha_history_downloads.format_history_download_timestamp(
        created_at,
        datetime=datetime,
        re=re,
    )


def build_history_download_file_name(
    feature_name: str,
    created_at: str,
    image_index: int,
    image_source: str,
    original_name: str = "",
    uniqueness_seed: str = "",
) -> str:
    return _xiaoha_history_downloads.build_history_download_file_name(
        feature_name,
        created_at,
        image_index,
        image_source,
        original_name,
        uniqueness_seed,
        Path=Path,
        format_history_download_timestamp=format_history_download_timestamp,
        hashlib=hashlib,
        infer_history_download_extension=infer_history_download_extension,
        sanitize_history_download_name_part=sanitize_history_download_name_part,
        urllib=urllib,
    )


def flatten_history_items(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _xiaoha_history_downloads.flatten_history_items(
        records,
        Any=Any,
        Path=Path,
        build_history_download_file_name=build_history_download_file_name,
        hashlib=hashlib,
        urllib=urllib,
    )


def get_history_item_selection_key(
    key_prefix: str,
    item: dict[str, Any],
    item_index: int,
) -> str:
    return _xiaoha_history_downloads.get_history_item_selection_key(
        key_prefix,
        item,
        item_index,
        hashlib=hashlib,
    )


def infer_history_download_extension(
    file_name: str,
    image_source: str,
    mime_type: str,
) -> str:
    return _xiaoha_history_downloads.infer_history_download_extension(
        file_name,
        image_source,
        mime_type,
        Path=Path,
        urllib=urllib,
    )


def build_history_download_archive_bytes(items: list[dict[str, Any]]) -> bytes:
    return _xiaoha_history_downloads.build_history_download_archive_bytes(
        items,
        Path=Path,
        infer_history_download_extension=infer_history_download_extension,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
        sanitize_history_download_name_part=sanitize_history_download_name_part,
        zipfile=zipfile,
    )


def get_history_columns_per_row(item_count: int) -> int:
    return _job_presentation.get_history_columns_per_row(item_count)


def render_history_gallery(
    items: list[dict[str, Any]],
    key_prefix: str,
    columns_per_row: int | None = None,
    thumb_height: int = 230,
    enable_a_plus_crop_downloads: bool = False,
) -> None:
    return _xiaoha_history.render_history_gallery(
        items,
        key_prefix,
        columns_per_row,
        thumb_height,
        enable_a_plus_crop_downloads,
        MAIN_IMAGE_A_PLUS_FEATURE_KEY=MAIN_IMAGE_A_PLUS_FEATURE_KEY,
        build_history_download_archive_bytes=build_history_download_archive_bytes,
        build_history_download_public_url=build_history_download_public_url,
        datetime=datetime,
        get_history_columns_per_row=get_history_columns_per_row,
        get_history_item_selection_key=get_history_item_selection_key,
        html=html,
        is_main_image_a_plus_mobile_canvas=is_main_image_a_plus_mobile_canvas,
        partial=partial,
        render_main_image_a_plus_crop_downloads=render_main_image_a_plus_crop_downloads,
        render_main_image_a_plus_text_editor=render_main_image_a_plus_text_editor,
        render_zoomable_image_gallery=render_zoomable_image_gallery,
        st=st,
        submit_main_image_a_plus_mobile_adaptation=submit_main_image_a_plus_mobile_adaptation,
    )



def render_history_toggle(feature: dict[str, Any]) -> None:
    return _xiaoha_history.render_history_toggle(
        feature,
        HISTORY_PAGE_SIZE=HISTORY_PAGE_SIZE,
        ensure_history_records_loaded=ensure_history_records_loaded,
        get_history_cache_key=get_history_cache_key,
        set_history_visible_limit=set_history_visible_limit,
        st=st,
    )



def render_history_records(feature: dict[str, Any], *, show_toggle: bool = True) -> None:
    return _xiaoha_history.render_history_records(
        feature,
        show_toggle,
        HISTORY_PAGE_SIZE=HISTORY_PAGE_SIZE,
        MAIN_IMAGE_A_PLUS_FEATURE_KEY=MAIN_IMAGE_A_PLUS_FEATURE_KEY,
        ensure_history_records_loaded=ensure_history_records_loaded,
        flatten_history_items=flatten_history_items,
        get_history_cache_key=get_history_cache_key,
        get_history_visible_limit=get_history_visible_limit,
        render_history_gallery=render_history_gallery,
        set_history_visible_limit=set_history_visible_limit,
        st=st,
    )



def render_image_workbench_header(feature: dict[str, Any], badge: str='AI 增强') -> None:
    return _result_views.render_image_workbench_header(
        feature,
        badge,
        html=html,
        render_fusion_history_dialog=render_fusion_history_dialog,
        st=st,
    )


@st.dialog("历史记录", width="large")
def render_fusion_history_dialog(feature: dict[str, Any]) -> None:
    render_history_records(feature, show_toggle=False)


def render_side_history_panel(feature: dict[str, Any]) -> None:
    return _xiaoha_history.render_side_history_panel(
        feature,
        HISTORY_PAGE_SIZE=HISTORY_PAGE_SIZE,
        MAIN_IMAGE_A_PLUS_FEATURE_KEY=MAIN_IMAGE_A_PLUS_FEATURE_KEY,
        ensure_history_records_loaded=ensure_history_records_loaded,
        flatten_history_items=flatten_history_items,
        get_history_cache_key=get_history_cache_key,
        get_history_visible_limit=get_history_visible_limit,
        render_history_gallery=render_history_gallery,
        set_history_visible_limit=set_history_visible_limit,
        st=st,
    )



def parse_hex_rgb(hex_color: str) -> tuple[int, int, int]:
    return _background_cutout.parse_hex_rgb(hex_color, re=re)


def estimate_cutout_background_color(image: Image.Image, sample_mode: str) -> tuple[int, int, int]:
    return _background_cutout.estimate_cutout_background_color(
        image,
        sample_mode,
        ImageStat=ImageStat,
    )


def extract_edge_connected_mask(candidate_mask: Image.Image) -> Image.Image:
    return _background_cutout.extract_edge_connected_mask(
        candidate_mask,
        Image=Image,
        ImageDraw=ImageDraw,
    )


def build_subject_protection_mask(distance: Image.Image, threshold: int) -> Image.Image:
    return _background_cutout.build_subject_protection_mask(
        distance,
        threshold,
        Image=Image,
        ImageDraw=ImageDraw,
    )


def build_lash_rectangle_protection_mask(image: Image.Image) -> Image.Image:
    return _background_cutout.build_lash_rectangle_protection_mask(
        image,
        Image=Image,
        ImageDraw=ImageDraw,
    )


def remove_background_by_color(image: Image.Image, background_color: tuple[int, int, int], tolerance: int, softness: int, edge_blur: float, invert_mask: bool, connected_only: bool=True, protect_subject_region: bool=True, subject_region_mode: str='lash_rectangle') -> Image.Image:
    return _background_cutout.remove_background_by_color(
        image,
        background_color,
        tolerance,
        softness,
        edge_blur,
        invert_mask,
        connected_only,
        protect_subject_region,
        subject_region_mode,
        Image=Image,
        ImageChops=ImageChops,
        ImageFilter=ImageFilter,
        ImageOps=ImageOps,
        build_lash_rectangle_protection_mask=build_lash_rectangle_protection_mask,
        build_subject_protection_mask=build_subject_protection_mask,
        extract_edge_connected_mask=extract_edge_connected_mask,
    )


def image_to_png_bytes(image: Image.Image) -> bytes:
    return _background_cutout.image_to_png_bytes(image, io=io)


def crop_to_visible_alpha(image: Image.Image, padding: int=2) -> Image.Image:
    return _background_cutout.crop_to_visible_alpha(
        image,
        padding,
        ImageOps=ImageOps,
    )


def regularize_lash_tray_alpha(alpha_image: Image.Image) -> tuple[Image.Image, bool]:
    return _background_cutout.regularize_lash_tray_alpha(alpha_image, Image=Image)


def regularize_lash_tray_cutout(image: Image.Image) -> tuple[Image.Image, bool]:
    return _background_cutout.regularize_lash_tray_cutout(
        image,
        Image=Image,
        ImageOps=ImageOps,
        regularize_lash_tray_alpha=regularize_lash_tray_alpha,
    )


def finalize_lash_tray_cutout_edges(image: Image.Image) -> Image.Image:
    return _background_cutout.finalize_lash_tray_cutout_edges(
        image,
        clean_cutout_edge_fringe=clean_cutout_edge_fringe,
        crop_to_visible_alpha=crop_to_visible_alpha,
        regularize_lash_tray_cutout=regularize_lash_tray_cutout,
    )


def preserve_source_pixels_with_ai_alpha(source_image: Image.Image, ai_cutout_image: Image.Image) -> Image.Image:
    return _background_cutout.preserve_source_pixels_with_ai_alpha(
        source_image,
        ai_cutout_image,
        Image=Image,
        ImageOps=ImageOps,
        finalize_lash_tray_cutout_edges=finalize_lash_tray_cutout_edges,
    )




def remove_simple_green_screen_background(image: Image.Image) -> Image.Image:
    return _background_cutout.remove_simple_green_screen_background(
        image,
        Image=Image,
        ImageOps=ImageOps,
    )


def clean_cutout_edge_fringe(image: Image.Image, contract_edge: bool=True, preserve_alpha_edge: bool=False) -> Image.Image:
    return _background_cutout.clean_cutout_edge_fringe(
        image,
        contract_edge,
        preserve_alpha_edge,
        Image=Image,
        ImageOps=ImageOps,
    )


def remove_ai_green_screen_background(image: Image.Image) -> Image.Image:
    return _background_cutout.remove_ai_green_screen_background(
        image,
        Image=Image,
        ImageFilter=ImageFilter,
        ImageOps=ImageOps,
        build_lash_rectangle_protection_mask=build_lash_rectangle_protection_mask,
        clean_cutout_edge_fringe=clean_cutout_edge_fringe,
        remove_background_by_color=remove_background_by_color,
        remove_simple_green_screen_background=remove_simple_green_screen_background,
    )


def call_ai_lash_tray_cutout(uploaded_input: Any, prompt: str) -> dict[str, Any]:
    return _background_cutout.call_ai_lash_tray_cutout(
        uploaded_input,
        prompt,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        build_ai_lash_tray_cutout_prompt=build_ai_lash_tray_cutout_prompt,
        call_openrouter_images_api=call_openrouter_images_api,
        uploaded_input_to_pil_image=uploaded_input_to_pil_image,
    )


def get_image_matting_model_path() -> Path:
    return _runtime_config.get_image_matting_model_path(
        IMAGE_MATTING_DEFAULT_MODEL_PATH=IMAGE_MATTING_DEFAULT_MODEL_PATH,
        Path=Path,
        load_runtime_settings=load_runtime_settings,
        os=os,
    )


def trim_transparent_image(image: Image.Image, padding: int=4, alpha_threshold: int=4) -> Image.Image:
    return _background_cutout.trim_transparent_image(
        image,
        padding,
        alpha_threshold,
    )


def find_lash_product_region_polygon(image: Image.Image) -> list[tuple[float, float]] | None:
    return _background_cutout.find_lash_product_region_polygon(
        image,
        Any=Any,
        Image=Image,
        ImageOps=ImageOps,
    )


def cut_to_lash_product_region(original_image: Image.Image, fallback_image: Image.Image) -> Image.Image:
    return _background_cutout.cut_to_lash_product_region(
        original_image,
        fallback_image,
        Image=Image,
        ImageChops=ImageChops,
        ImageDraw=ImageDraw,
        ImageFilter=ImageFilter,
        ImageOps=ImageOps,
        find_lash_product_region_polygon=find_lash_product_region_polygon,
        trim_transparent_image=trim_transparent_image,
    )


class ImageMattingSegmenter(_image_matting.ImageMattingSegmenter):
    def __init__(self, model_path: Path, model_input_size: tuple[int, int] = IMAGE_MATTING_INPUT_SIZE) -> None:
        super().__init__(
            model_path,
            model_input_size,
            default_model_path=IMAGE_MATTING_DEFAULT_MODEL_PATH,
            trim_image=lambda image: trim_transparent_image(image),
        )


def get_image_matting_segmenter() -> ImageMattingSegmenter:
    global _IMAGE_MATTING_SEGMENTER, _IMAGE_MATTING_SEGMENTER_PATH
    model_path = get_image_matting_model_path()
    normalized_path = str(model_path)
    with _IMAGE_MATTING_LOCK:
        if _IMAGE_MATTING_SEGMENTER is None or _IMAGE_MATTING_SEGMENTER_PATH != normalized_path:
            _IMAGE_MATTING_SEGMENTER = ImageMattingSegmenter(model_path)
            _IMAGE_MATTING_SEGMENTER_PATH = normalized_path
        return _IMAGE_MATTING_SEGMENTER


def uploaded_input_to_pil_image(uploaded_input: Any) -> Image.Image:
    return _background_cutout.uploaded_input_to_pil_image(
        uploaded_input,
        Image=Image,
        ImageOps=ImageOps,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        io=io,
    )


def run_ai_background_cutout_job(job_context: dict[str, Any]) -> dict[str, Any]:
    return _background_cutout.run_ai_background_cutout_job(
        job_context,
        Image=Image,
        call_ai_lash_tray_cutout=call_ai_lash_tray_cutout,
        get_uploaded_input_name=get_uploaded_input_name,
        image_bytes_to_data_url=image_bytes_to_data_url,
        image_to_png_bytes=image_to_png_bytes,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
        math=math,
        prepare_uploaded_input=prepare_uploaded_input,
        preserve_source_pixels_with_ai_alpha=preserve_source_pixels_with_ai_alpha,
        remove_ai_green_screen_background=remove_ai_green_screen_background,
        set_task_progress=set_task_progress,
        uploaded_input_to_data_url=uploaded_input_to_data_url,
        uploaded_input_to_pil_image=uploaded_input_to_pil_image,
    )


def build_checkerboard_preview(image: Image.Image, max_edge: int=1600) -> Image.Image:
    return _background_cutout.build_checkerboard_preview(
        image,
        max_edge,
        Image=Image,
        ImageDraw=ImageDraw,
    )


def render_background_cutout_feature(feature: dict[str, Any]) -> None:
    return _workbench_pages.render_background_cutout_feature(
        feature,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        FEATURE_OUTPUT_COUNT_MAX=FEATURE_OUTPUT_COUNT_MAX,
        FEATURE_OUTPUT_COUNT_MIN=FEATURE_OUTPUT_COUNT_MIN,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        format_user_facing_error_message=format_user_facing_error_message,
        prepare_uploaded_input=prepare_uploaded_input,
        re=re,
        render_image_workbench_header=render_image_workbench_header,
        render_result_loading=render_result_loading,
        render_result_preview=render_result_preview,
        render_running_job_status=render_running_job_status,
        render_single_image_uploader=render_single_image_uploader,
        render_zoomable_image_gallery=render_zoomable_image_gallery,
        st=st,
        submit_feature_job=submit_feature_job,
        uploaded_input_to_data_url=uploaded_input_to_data_url,
    )




# ---- A+ 首屏风格逆向 ----
HERO_STYLE_REVERSE_FIELD_LABELS: tuple[tuple[str, str], ...] = (
    ("subject", "主体内容"),
    ("composition", "构图布局"),
    ("color", "色彩搭配"),
    ("lighting", "光影效果"),
    ("style", "设计风格"),
    ("details", "细节元素"),
)

HERO_STYLE_REVERSE_ASPECT_OPTIONS: tuple[tuple[str, str], ...] = (
    ("A+ 首屏 4:3", "4:3"),
    ("A+ 首屏 16:9", "16:9"),
    ("方图 1:1", "1:1"),
    ("竖版 4:5", "4:5"),
    ("竖版 9:16", "9:16"),
)

HERO_STYLE_REVERSE_MAX_COUNT = 4




def parse_hero_style_reverse_analysis(response_text: str) -> dict[str, str]:
    return _hero_style_reverse.parse_hero_style_reverse_analysis(
        response_text,
        Any=Any,
        HERO_STYLE_REVERSE_FIELD_LABELS=HERO_STYLE_REVERSE_FIELD_LABELS,
        json=json,
        re=re,
    )


def analyze_hero_style_reverse_reference(uploaded_input: Any, extra_requirements: str='') -> dict[str, str]:
    return _hero_style_reverse.analyze_hero_style_reverse_reference(
        uploaded_input,
        extra_requirements,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        IMAGE_SMART_ANALYSIS_MODEL=IMAGE_SMART_ANALYSIS_MODEL,
        build_hero_style_reverse_analysis_prompt=build_hero_style_reverse_analysis_prompt,
        call_openrouter=call_openrouter,
        parse_hero_style_reverse_analysis=parse_hero_style_reverse_analysis,
    )


def optimize_hero_style_reverse_prompt(prompt_text: str, analysis: dict[str, str] | None=None, extra_requirements: str='') -> str:
    return _hero_style_reverse.optimize_hero_style_reverse_prompt(
        prompt_text,
        analysis,
        extra_requirements,
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        HERO_STYLE_REVERSE_FIELD_LABELS=HERO_STYLE_REVERSE_FIELD_LABELS,
        IMAGE_SMART_ANALYSIS_MODEL=IMAGE_SMART_ANALYSIS_MODEL,
        call_openrouter=call_openrouter,
        re=re,
    )


def build_hero_style_reverse_image_input(image_source: str) -> dict[str, Any] | None:
    return _hero_style_reverse.build_hero_style_reverse_image_input(
        image_source,
        get_external_request_kwargs=get_external_request_kwargs,
        get_request_limiter=get_request_limiter,
        requests=requests,
    )


def generate_hero_style_reverse_images(prompt_text: str, reference_files: list[Any] | None=None, count: int=2, aspect_ratio: str='4:3', progress_callback: Any=None) -> list[str]:
    return _hero_style_reverse.generate_hero_style_reverse_images(
        prompt_text,
        reference_files,
        count,
        aspect_ratio,
        progress_callback,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        call_openrouter_images_api=call_openrouter_images_api,
    )


def hero_style_reverse_nearest_aspect_ratio(width: int, height: int) -> str:
    return _hero_style_reverse.hero_style_reverse_nearest_aspect_ratio(
        width,
        height,
        HERO_STYLE_REVERSE_ASPECT_OPTIONS=HERO_STYLE_REVERSE_ASPECT_OPTIONS,
    )


def resize_hero_style_reverse_output(image_source: str, target_width: int, target_height: int | None=None) -> str:
    return _hero_style_reverse.resize_hero_style_reverse_output(
        image_source,
        target_width,
        target_height,
        Image=Image,
        ImageOps=ImageOps,
        fit_image_to_canvas_without_distortion=fit_image_to_canvas_without_distortion,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        load_image_bytes_from_url=load_image_bytes_from_url,
    )


def persist_hero_style_reverse_history(feature: dict[str, Any], images: list[str], prompt: str, model: str=NANO_BANANA_MODEL) -> list[dict[str, Any]]:
    return _hero_style_reverse.persist_hero_style_reverse_history(
        feature,
        images,
        prompt,
        model,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        build_local_history_records=build_local_history_records,
        get_history_cache_key=get_history_cache_key,
        save_generated_images_and_record_db=save_generated_images_and_record_db,
        st=st,
        store_local_history_records=store_local_history_records,
        sys=sys,
    )


def save_hero_reverse_draft(field: str, widget_key: str) -> None:
    return _hero_style_reverse.save_hero_reverse_draft(
        field,
        widget_key,
        st=st,
    )


def submit_hero_reverse_job(feature, prompt, references, count, ratio, width, height, parent='', parent_index=None):
    return _hero_style_reverse.submit_hero_reverse_job(
        feature,
        prompt,
        references,
        count,
        ratio,
        width,
        height,
        parent,
        parent_index,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        normalize_uploaded_input=normalize_uploaded_input,
        st=st,
        submit_feature_job=submit_feature_job,
    )


def run_hero_reverse_job(context):
    return _hero_style_reverse.run_hero_reverse_job(
        context,
        datetime=datetime,
        generate_hero_style_reverse_images=generate_hero_style_reverse_images,
        resize_hero_style_reverse_output=resize_hero_style_reverse_output,
        set_task_progress=set_task_progress,
    )


def render_a_plus_hero_style_reverse_feature(feature: dict[str, Any]) -> None:
    return _workbench_pages.render_a_plus_hero_style_reverse_feature(
        feature,
        A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY=A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY,
        HERO_STYLE_REVERSE_FIELD_LABELS=HERO_STYLE_REVERSE_FIELD_LABELS,
        HERO_STYLE_REVERSE_MAX_COUNT=HERO_STYLE_REVERSE_MAX_COUNT,
        analyze_hero_style_reverse_reference=analyze_hero_style_reverse_reference,
        build_hero_style_reverse_image_input=build_hero_style_reverse_image_input,
        format_user_facing_error_message=format_user_facing_error_message,
        get_uploaded_input_name=get_uploaded_input_name,
        hero_style_reverse_nearest_aspect_ratio=hero_style_reverse_nearest_aspect_ratio,
        optimize_hero_style_reverse_prompt=optimize_hero_style_reverse_prompt,
        render_image_workbench_header=render_image_workbench_header,
        render_result_loading=render_result_loading,
        render_result_preview=render_result_preview,
        render_running_job_status=render_running_job_status,
        render_single_image_uploader=render_single_image_uploader,
        render_zoomable_image_gallery=render_zoomable_image_gallery,
        save_hero_reverse_draft=save_hero_reverse_draft,
        st=st,
        submit_hero_reverse_job=submit_hero_reverse_job,
    )


def render_replacement_infinite_canvas_feature(feature: dict[str, Any]) -> None:
    return _workbench_pages.render_replacement_infinite_canvas_feature(
        feature,
        DEFAULT_JIMENG_STATIC_PORT=DEFAULT_JIMENG_STATIC_PORT,
        DEFAULT_PUBLIC_APP_URL=DEFAULT_PUBLIC_APP_URL,
        INFINITE_CANVAS_BUILD_DIR=INFINITE_CANVAS_BUILD_DIR,
        build_infinite_canvas_url=build_infinite_canvas_url,
        html=html,
        load_runtime_settings=load_runtime_settings,
        st=st,
    )


def render_infinite_canvas_feature(feature: dict[str, Any], model: str, aspect_ratio: str) -> None:
    return _workbench_pages.render_infinite_canvas_feature(
        feature,
        model,
        aspect_ratio,
        Any=Any,
        INFINITE_CANVAS_MAX_INPUT_IMAGES=INFINITE_CANVAS_MAX_INPUT_IMAGES,
        INFINITE_CANVAS_MAX_STEPS=INFINITE_CANVAS_MAX_STEPS,
        NANO_BANANA_MODEL=NANO_BANANA_MODEL,
        OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX=OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
        OUTPAINT_DEFAULT_EXTENSION_PX=OUTPAINT_DEFAULT_EXTENSION_PX,
        OUTPAINT_FALLBACK_MAX_EXTENSION_PX=OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
        build_result_download_sources=build_result_download_sources,
        format_user_facing_error_message=format_user_facing_error_message,
        get_infinite_canvas_step_features=get_infinite_canvas_step_features,
        get_model_display_name=get_model_display_name,
        get_outpaint_default_extension=get_outpaint_default_extension,
        get_outpaint_extension_limits=get_outpaint_extension_limits,
        get_skin_texture_reference_files=get_skin_texture_reference_files,
        html=html,
        prepare_uploaded_input=prepare_uploaded_input,
        render_history_records=render_history_records,
        render_multi_image_uploader=render_multi_image_uploader,
        render_outpaint_extension_preview_card=render_outpaint_extension_preview_card,
        render_result_loading=render_result_loading,
        render_result_preview=render_result_preview,
        render_result_preview_with_captions=render_result_preview_with_captions,
        render_running_job_status=render_running_job_status,
        render_single_image_uploader=render_single_image_uploader,
        render_zoomable_image_gallery=render_zoomable_image_gallery,
        st=st,
        submit_feature_job=submit_feature_job,
        uploaded_input_to_data_url=uploaded_input_to_data_url,
    )


def _image_smart_text(value: Any, max_length: int=180) -> str:
    return _image_smart_analysis._image_smart_text(
        value,
        max_length,
        re=re,
    )


def _image_smart_string_list(value: Any, max_items: int=8, max_length: int=48) -> list[str]:
    return _image_smart_analysis._image_smart_string_list(
        value,
        max_items,
        max_length,
        _image_smart_text=_image_smart_text,
        re=re,
    )


def describe_image_smart_color(rgb: tuple[int, int, int]) -> str:
    return _image_smart_analysis.describe_image_smart_color(rgb, colorsys=colorsys)


def _extract_image_smart_palette_from_image(source_image: Image.Image, max_colors: int=6) -> list[dict[str, Any]]:
    return _image_smart_analysis._extract_image_smart_palette_from_image(
        source_image,
        max_colors,
        Any=Any,
        Image=Image,
        describe_image_smart_color=describe_image_smart_color,
        math=math,
    )


def extract_image_smart_palette(uploaded_input: Any, max_colors: int=6) -> list[dict[str, Any]]:
    return _image_smart_analysis.extract_image_smart_palette(
        uploaded_input,
        max_colors,
        Image=Image,
        ImageOps=ImageOps,
        _extract_image_smart_palette_from_image=_extract_image_smart_palette_from_image,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        io=io,
    )


def build_image_smart_analysis_model_prompt(base_prompt: str, palette: list[dict[str, Any]]) -> str:
    return _image_smart_analysis.build_image_smart_analysis_model_prompt(base_prompt, palette)


def parse_image_smart_analysis_payload(response_text: str, image_size: tuple[int, int], palette: list[dict[str, Any]]) -> dict[str, Any]:
    return _image_smart_analysis.parse_image_smart_analysis_payload(
        response_text,
        image_size,
        palette,
        Any=Any,
        _image_smart_string_list=_image_smart_string_list,
        _image_smart_text=_image_smart_text,
        json=json,
        normalize_main_image_a_plus_element_bbox=normalize_main_image_a_plus_element_bbox,
        re=re,
    )


def _load_image_smart_font(size: int, bold: bool=False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return _image_smart_analysis._load_image_smart_font(
        size,
        bold,
        ImageFont=ImageFont,
    )


def _wrap_image_smart_text(draw: ImageDraw.ImageDraw, value: Any, font: ImageFont.ImageFont, max_width: int, max_lines: int) -> list[str]:
    return _image_smart_analysis._wrap_image_smart_text(
        draw,
        value,
        font,
        max_width,
        max_lines,
        _image_smart_text=_image_smart_text,
    )


def _draw_image_smart_text_block(draw: ImageDraw.ImageDraw, value: Any, position: tuple[int, int], font: ImageFont.ImageFont, fill: tuple[int, int, int], max_width: int, max_lines: int, line_gap: int=8) -> int:
    return _image_smart_analysis._draw_image_smart_text_block(
        draw,
        value,
        position,
        font,
        fill,
        max_width,
        max_lines,
        line_gap,
        _wrap_image_smart_text=_wrap_image_smart_text,
    )


def build_image_smart_analysis_board(uploaded_input: Any, analysis: dict[str, Any]) -> bytes:
    return _image_smart_analysis.build_image_smart_analysis_board(
        uploaded_input,
        analysis,
        Image=Image,
        ImageDraw=ImageDraw,
        ImageOps=ImageOps,
        _draw_image_smart_text_block=_draw_image_smart_text_block,
        _load_image_smart_font=_load_image_smart_font,
        build_image_smart_layout_comparison=build_image_smart_layout_comparison,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        io=io,
        math=math,
    )


def build_image_smart_layout_comparison(uploaded_input: Any, analysis: dict[str, Any]) -> Image.Image:
    return _image_smart_analysis.build_image_smart_layout_comparison(
        uploaded_input,
        analysis,
        Any=Any,
        Image=Image,
        ImageDraw=ImageDraw,
        ImageOps=ImageOps,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        io=io,
    )


def build_image_smart_analysis_result(model_result: dict[str, Any], uploaded_input: Any, palette: list[dict[str, Any]] | None=None) -> dict[str, Any]:
    return _image_smart_analysis.build_image_smart_analysis_result(
        model_result,
        uploaded_input,
        palette,
        Image=Image,
        ImageOps=ImageOps,
        Path=Path,
        _extract_image_smart_palette_from_image=_extract_image_smart_palette_from_image,
        build_image_smart_analysis_board=build_image_smart_analysis_board,
        extract_image_smart_palette=extract_image_smart_palette,
        get_uploaded_file_bytes=get_uploaded_file_bytes,
        get_uploaded_input_dimensions=get_uploaded_input_dimensions,
        get_uploaded_input_name=get_uploaded_input_name,
        image_bytes_to_data_url=image_bytes_to_data_url,
        io=io,
        parse_image_smart_analysis_payload=parse_image_smart_analysis_payload,
        sanitize_file_name=sanitize_file_name,
    )


def render_image_smart_analysis_report(result: dict[str, Any], job_status: str='', result_key: str='latest') -> None:
    return _image_smart_analysis.render_image_smart_analysis_report(
        result,
        job_status,
        result_key,
        datetime=datetime,
        decode_data_url=decode_data_url,
        html=html,
        re=re,
        render_zoomable_image_gallery=render_zoomable_image_gallery,
        st=st,
    )


def render_a_plus_reference_lab_empty_results(slot_count: int=FEATURE_OUTPUT_COUNT_MAX) -> None:
    return _download_views.render_a_plus_reference_lab_empty_results(slot_count, st=st)


def render_prepress_check_feature(feature: dict[str, Any]) -> None:
    return _workbench_pages.render_prepress_check_feature(
        feature,
        datetime=datetime,
        prepress_check_service=prepress_check_service,
        render_frame_uploader=render_frame_uploader,
        st=st,
        uuid4=uuid4,
    )


def render_openrouter_feature(feature: dict[str, Any], model: str, aspect_ratio: str) -> None:
    if feature.get("mode") == "seedream_tools":
        from Department.视觉设计部.xiaoha.features.seedream_tools import render
        return render(SimpleNamespace(**globals()), feature)
    _feature_workbench.render_openrouter_feature(
        SimpleNamespace(**globals()), feature, model, aspect_ratio,
    )


def render_login_page() -> None:
    return _xiaoha_page.render_login_page(
        authenticate_requested_user=authenticate_requested_user,
        st=st,
    )



SIDE_MENU_FEATURE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("设计检查", ("prepress_check",)),
    (
        "图片处理",
        (
            "seedream_layers",
            "seedream_coordinate_edit",
            "seedream_mark_edit",
            "hd_batch",
            JIMENG_HD_FEATURE_KEY,
            "image_resize",
            "product_retouch",
            "product_retouch_local",
            "background_cutout",
            BACKGROUND_TEXTURE_FEATURE_KEY,
            "outpaint",
        ),
    ),
    (
        "模特编辑",
        (
            "remove_eyelashes",
            "pose_change",
            "scene_change",
            "single_to_double",
            "skin_tone",
            "pupil_color_change",
            "eye_shape_change",
            "three_view",
        ),
    ),
    (
        "A+",
        (
            "a_plus_canvas",
            "poster_fusion",
            A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY,
            AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY,
            A_PLUS_STYLE_MODEL_REPLACE_FEATURE_KEY,
            A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY,
            A_PLUS_REFERENCE_LAB_FEATURE_KEY,
            MAIN_IMAGE_A_PLUS_FEATURE_KEY,
            AMAZON_A_PLUS_FEATURE_KEY,
        ),
    ),
    (
        "智能创作",
        (
            "ai_qa_image",
            IMAGE_SMART_ANALYSIS_FEATURE_KEY,
        ),
    ),
    ("工作台", ("infinite_canvas",)),
)


def render_side_menu(current_feature: dict[str, Any] | None = None) -> None:
    return _xiaoha_page.render_side_menu(
        current_feature,
        SIDE_MENU_FEATURE_GROUPS=SIDE_MENU_FEATURE_GROUPS,
        XIAOHA_BALANCE_KEY=XIAOHA_BALANCE_KEY,
        XIAOHA_DASHBOARD_KEY=XIAOHA_DASHBOARD_KEY,
        get_visible_features=get_visible_features,
        select_feature=select_feature,
        st=st,
    )



def is_running_in_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def relaunch_with_streamlit() -> None:
    runtime_settings = load_runtime_settings()
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(Path(__file__).resolve()),
            "--server.address",
            str(runtime_settings["server_address"]),
            "--server.port",
            str(runtime_settings["server_port"]),
            "--server.baseUrlPath",
            "lashforge",
            "--server.headless",
            "true",
            "--server.websocketPingInterval",
            "20",
            "--server.disconnectedSessionTTL",
            "86400",
            "--server.fileWatcherType",
            "none",
        ],
    )


def main() -> None:
    return _xiaoha_page.main(
        DEFAULT_ASPECT_RATIO=DEFAULT_ASPECT_RATIO,
        DEFAULT_MODEL=DEFAULT_MODEL,
        FEATURE_QUERY_KEY=FEATURE_QUERY_KEY,
        XIAOHA_BALANCE_KEY=XIAOHA_BALANCE_KEY,
        XIAOHA_DASHBOARD_KEY=XIAOHA_DASHBOARD_KEY,
        XIAOHA_DEFAULT_FEATURE_KEY=XIAOHA_DEFAULT_FEATURE_KEY,
        authenticate_requested_user=authenticate_requested_user,
        consume_pending_outpaint_drag=consume_pending_outpaint_drag,
        consume_pending_upload_delete=consume_pending_upload_delete,
        consume_pending_upload_reorder=consume_pending_upload_reorder,
        ensure_history_storage=ensure_history_storage,
        ensure_jimeng_static_server=ensure_jimeng_static_server,
        ensure_state=ensure_state,
        get_visible_features=get_visible_features,
        inject_app_styles=inject_app_styles,
        inject_clipboard_paste_support=inject_clipboard_paste_support,
        inject_upload_reorder_support=inject_upload_reorder_support,
        render_openrouter_feature=render_openrouter_feature,
        render_side_menu=render_side_menu,
        render_xiaoha_balance_management=render_xiaoha_balance_management,
        render_xiaoha_usage_dashboard=render_xiaoha_usage_dashboard,
        restore_auth_session=restore_auth_session,
        st=st,
        sync_background_jobs=sync_background_jobs,
    )



if __name__ == "__main__":
    if is_running_in_streamlit():
        main()
    else:
        relaunch_with_streamlit()
