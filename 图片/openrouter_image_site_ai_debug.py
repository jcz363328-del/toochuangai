from __future__ import annotations

import base64
import html
import hashlib
import hmac
import io
import json
import math
import mimetypes
import os
import re
import sys
import time
import urllib.parse
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

import requests
import streamlit as st
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from secret_settings import sql_server_config

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.1-flash-image-preview"
NANO_BANANA_MODEL = "google/gemini-3.1-flash-image-preview"
DEFAULT_ASPECT_RATIO = "自动"
REFERENCE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MIN_OUTPUT_EDGE = 2000
HD_MIN_OUTPUT_EDGE = 4096
HD_MODEL_REFERENCE_FILE = APP_DIR / "__pycache__" / "model_reference" / "模特参考图.png"
OUTPUTS_HD_REFERENCE_DIR = APP_DIR / "outputs" / "reference"
OUTPUTS_HD_DEFAULT_REFERENCE_FILE = OUTPUTS_HD_REFERENCE_DIR / "参考1.png"
SKIN_TEXTURE_REFERENCE_DIR = Path(r"D:\肌肤质感参考")
PORTRAIT_HD_DEFAULT_IMAGE_SIZE = "4K"
PROXY_URL = "socks5h://127.0.0.1:10808"
REQUEST_PROXIES = {
    "http": PROXY_URL,
    "https": PROXY_URL,
}
HISTORY_DIR = APP_DIR / "history"
HISTORY_IMAGES_DIR = HISTORY_DIR / "images"
HISTORY_FILE = HISTORY_DIR / "records.json"
MAX_HISTORY_RECORDS = 120
HISTORY_PAGE_SIZE = 20
DB_HISTORY_TABLE = "AI_TuPian"
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
JIMENG_HD_API_RESOLUTION = "8k"
JIMENG_HD_API_SCALE = 30
DB_IMAGE_DIR = Path(r"D:\视觉图片")
DB_HISTORY_LIMIT = MAX_HISTORY_RECORDS
DB_HISTORY_THUMB_DIR_NAME = "_thumbs"
DB_HISTORY_THUMB_MAX_EDGE = 640
DB_HISTORY_THUMB_TARGET_BYTES = 140 * 1024
DB_HISTORY_PATH_MAX_LENGTH = 50
GALLERY_PREVIEW_MAX_EDGE = 1600
GALLERY_PREVIEW_TARGET_BYTES = 220 * 1024
UPLOAD_CACHE_DIR = Path(r"D:\图片上传缓存")
AUTH_QUERY_USER_KEY = "auth_user"
AUTH_QUERY_TOKEN_KEY = "auth_token"
UPLOAD_DELETE_QUERY_KEY = "delete_upload"
AUTH_TOKEN_SALT = "lashforge-auth-v1"
DB_CONFIG = sql_server_config()
DEFAULT_SERVER_ADDRESS = "0.0.0.0"
DEFAULT_SERVER_PORT = 8501
DEFAULT_JIMENG_STATIC_PORT = 8502
DEFAULT_PUBLIC_APP_URL = "http://www.toochuangai.com:8501/lashforge"
DEFAULT_LOGIN_ACCOUNTS = {}
MODEL_OPTIONS = [
    JIMENG_MODEL_NAME,
    "google/gemini-2.5-flash-image",
    "google/gemini-3.1-flash-image-preview",
    "google/gemini-3-pro-image-preview",
    "openai/gpt-5.4-image-2",
    "openai/gpt-5-image-mini",
    "openai/gpt-5-image",
    "bytedance-seed/seedream-4.5",
    "x-ai/grok-imagine-image-quality",
    "recraft/recraft-v4.1-utility-pro",
]
IMAGE_ONLY_OUTPUT_MODEL_PREFIXES = (
    "bytedance-seed/",
    "x-ai/grok-imagine-image",
    "recraft/",
)
GEMINI_IMAGE_ASPECT_RATIOS = {
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
}
GEMINI_IMAGE_SIZES = {"1K", "2K", "4K"}
BATCH_MULTI_IMAGE_FEATURE_KEYS = {"hd_batch", "remove_eyelashes", "outpaint", "single_to_double"}
BATCH_MULTI_IMAGE_MAX_FILES = 20
MAX_BATCH_API_CONCURRENCY = 4
DEFAULT_BATCH_API_CONCURRENCY = 4
JIMENG_MAX_API_CONCURRENCY = 1
JIMENG_CONCURRENT_LIMIT_RETRY_COUNT = 3
JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS = (3, 6, 10)

class TaskRuntime:
    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.futures: dict[str, Future] = {}
        self.progress: dict[str, dict[str, Any]] = {}
        self.lock = Lock()


@st.cache_resource
def get_task_runtime() -> TaskRuntime:
    return TaskRuntime()


class JimengStaticRequestHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        directory: str | None = None,
        upload_directory: str | None = None,
        history_directory: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.upload_directory = str(upload_directory or directory or ".")
        self.history_directory = str(history_directory or DB_IMAGE_DIR)
        super().__init__(*args, directory=self.upload_directory, **kwargs)

    def translate_path(self, path: str) -> str:
        request_path = urllib.parse.unquote(urllib.parse.urlsplit(path).path or "/")
        target_directory = ""
        relative_path_text = ""
        upload_prefix = JIMENG_UPLOAD_ROUTE_PREFIX.rstrip("/")
        history_prefix = HISTORY_STATIC_ROUTE_PREFIX.rstrip("/")
        if request_path == upload_prefix:
            request_path = f"{upload_prefix}/"
        if request_path == history_prefix:
            request_path = f"{history_prefix}/"
        if request_path.startswith(f"{upload_prefix}/"):
            target_directory = self.upload_directory
            relative_path_text = request_path[len(f"{upload_prefix}/") :]
        elif request_path.startswith(f"{history_prefix}/"):
            target_directory = self.history_directory
            relative_path_text = request_path[len(f"{history_prefix}/") :]
        else:
            return str(Path(self.directory or ".") / "__not_found__")
        relative_path = Path(relative_path_text)
        safe_parts = [part for part in relative_path.parts if part not in ("", ".", "..")]
        return str(Path(target_directory).joinpath(*safe_parts))

    def log_message(self, format: str, *args: Any) -> None:
        return


def build_jimeng_static_base_url(public_app_url: str, static_port: int) -> str:
    raw_url = str(public_app_url or "").strip() or DEFAULT_PUBLIC_APP_URL
    parsed = urllib.parse.urlsplit(raw_url)
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname or "www.toochuangai.com"
    netloc = hostname
    default_port = 443 if scheme == "https" else 80
    if static_port and static_port != default_port:
        netloc = f"{hostname}:{static_port}"
    return urllib.parse.urlunsplit((scheme, netloc, JIMENG_UPLOAD_ROUTE_PREFIX, "", ""))


def build_history_static_base_url(public_app_url: str, static_port: int) -> str:
    raw_url = str(public_app_url or "").strip() or DEFAULT_PUBLIC_APP_URL
    parsed = urllib.parse.urlsplit(raw_url)
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname or "www.toochuangai.com"
    netloc = hostname
    default_port = 443 if scheme == "https" else 80
    if static_port and static_port != default_port:
        netloc = f"{hostname}:{static_port}"
    return urllib.parse.urlunsplit((scheme, netloc, HISTORY_STATIC_ROUTE_PREFIX, "", ""))


@st.cache_resource
def ensure_jimeng_static_server() -> dict[str, Any]:
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
        }
    except OSError as exc:
        return {
            "started": False,
            "bind_address": bind_address,
            "port": static_port,
            "base_url": str(runtime_settings.get("jimeng_public_upload_base_url") or "").strip(),
            "error": f"端口 {static_port} 启动失败：{exc}",
        }


FEATURES = [
    {
        "key": "hd_batch",
        "name": "模特图批量高清",
        "summary": "提升分辨率，优化细节",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "高清增强，清晰优先，按原比例放大且宽高都不小于 3200px。",
        "default_prompt": (
            "请基于输入图片进行高清修复和细节增强，4k清晰度，不要改变人物身份、五官比例、脸型、表情、发型和构图，去掉斑点和细纹，高清透亮。眼部和睫毛是最重要的区域这个位置一定要清晰"
            "增强目标："
            "1. 去掉脸上的斑点，细纹，稍微美颜，皮肤纹理清晰可见，不要模糊，人像整体提升到高清、干净、自然的感觉，。"
            "2. 重点增强眼部区域：睫毛根根分明、自然纤细、不要变成假睫毛或夸张妆感。"
            "3. 提升眉毛、眼线边缘、虹膜高光、眼周皮肤纹理的清晰度。"
            "4. 如果提供肤质参考图，皮肤状态必须严格参考第2张参考图。"
            "5. 发丝、唇部边缘、鼻翼、面部轮廓保持自然锐利。"
            "6. 不添加文字、水印、滤镜边框，不改变背景主体关系。"
            "输出一张自然、真实、商业修图级的人像高清图。"
        )
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
        "default_prompt": (
            "请严格基于参考图进行局部精修：只去掉所有睫毛，包括真睫毛和假睫毛，仅输出 1 张结果图。"
            "除睫毛被去除之外，其他所有内容必须完全不变，包括但不限于人物身份、脸型、五官位置、眼型、瞳孔、眉毛、"
            "皮肤、妆容、发型、服饰、姿势、构图、光影、清晰度、背景、色彩、尺寸都必须与原图保持一致。"
            "禁止新增、删减或修改任何其他细节，只允许执行“去除睫毛”这一项改动。"
        ),
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
        "key": "outpaint",
        "name": "模特扩图",
        "summary": "扩展画面，优化构图",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "description": "适合半身补全、边缘扩展、补足背景和人物缺失区域，但原图已有细节必须完全保持不变。",
        "default_prompt": (
            "Please perform a natural outpainting and 4K-quality enhancement strictly based on the original image. "
            "The transparent blank margins in the input are the only areas that need new content; treat transparent pixels as missing canvas, not as black or solid background. "
            "Only complete the missing canvas area and edge regions, and do not modify any detail that already exists in the original image. "
            "Any person, facial features, face shape, skin tone, skin texture, pores, skin detail, makeup, hair, clothing, material, "
            "pose, lighting, shadows, color, sharpness, background elements, and composition relationships that already appear in the image must remain completely unchanged. "
            "The output must be a single coherent, continuous photograph. Do not create a collage, split-frame, multi-panel layout, or duplicated scenes. "
            "In particular, the subject's skin texture must not be altered. Preserve the original realistic skin texture, pore detail, tonal depth, and natural surface quality. "
            "The outpainted area must blend seamlessly with the original image and should only extend the scene naturally. Do not redraw the existing subject and do not add details that conflict with the original style. "
            "Never stretch, smear, mirror, tile, clone, or repeat the border pixels of the original image. "
            "Background areas, limbs, clothing edges, and missing regions should be completed in a realistic and natural way suitable for e-commerce visuals."
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
        "summary": "上传图片问答生成图片",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "支持上传参考图并输入文字要求，像网页版 AI 问答一样理解图片内容后生成 1 张结果图。",
        "default_prompt": (
            "请结合我上传的图片和我的文字要求进行多模态理解，并生成 1 张高质量结果图。"
            "要优先理解用户上传图片中的主体、场景、构图、细节和视觉关系，再严格按照文字要求执行生成。"
            "仅输出 1 张结果图。"
        ),
    },
    {
        "key": "amazon_a_plus",
        "name": "亚马逊A+生成",
        "summary": "多图排版生成A+图",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "可上传最多 3 张原图，自动排版生成 1 张指定规格的亚马逊 A+ 图片，支持输入如 1464*600 的尺寸参数。",
        "default_prompt": (
            "请严格基于上传的原图生成一张适用于亚马逊 A+ 模块展示的排版图片。"
            "需要对原图进行电商感排版，画面整洁、高级、适合商品详情页展示。"
            "只使用上传图片中的产品/主体内容进行重组与排版，不要凭空替换主体，不要加入与原图无关的额外商品。"
            "最终只输出 1 张完整排版图。"
        ),
    },
    {
        "key": "jimeng_v40",
        "name": "Agent文生图",
        "summary": "输入文字直接生成高质量图片",
        "mode": "jimeng",
        "model": JIMENG_MODEL_NAME,
        "output_mode": "image",
        "min_images": 0,
        "max_output_images": 1,
        "description": "基于 Agent 4.6 图片生成能力的文生图功能，支持单张高质量出图。",
        "default_prompt": (
                "请根据文字要求生成 1 张高质量图片。"
            "画面需要细节丰富、构图完整、质感自然，适合商业展示。"
            "除非用户明确要求，否则不要输出多张，不要拼图，不要多联画。"
        ),
    },
]


def load_config_namespace() -> dict[str, Any]:
    config_path = APP_DIR / "config.py"
    if not config_path.exists():
        return {}

    namespace: dict[str, Any] = {}
    try:
        exec(config_path.read_text(encoding="utf-8"), namespace)
    except Exception:
        return {}
    return namespace


def load_api_key() -> str:
    env_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key

    namespace = load_config_namespace()
    if not namespace:
        return ""

    for key_name in ("open_routher_api_key", "openrouter_api_key", "OPENROUTER_API_KEY"):
        value = str(namespace.get(key_name, "")).strip()
        if value:
            return value

    return ""


def load_jimeng_credentials() -> tuple[str, str]:
    env_access_key = (
        os.getenv("VOLCENGINE_ACCESS_KEY_ID", "").strip()
        or os.getenv("JIMENG_ACCESS_KEY_ID", "").strip()
        or os.getenv("JIMENG_ACCESS_KEY", "").strip()
    )
    env_secret_key = (
        os.getenv("VOLCENGINE_SECRET_ACCESS_KEY", "").strip()
        or os.getenv("JIMENG_SECRET_ACCESS_KEY", "").strip()
        or os.getenv("JIMENG_SECRET_KEY", "").strip()
    )
    if env_access_key and env_secret_key:
        return env_access_key, env_secret_key

    namespace = load_config_namespace()
    if not namespace:
        return "", ""

    access_key = ""
    secret_key = ""
    for key_name in (
        "jimeng_access_key_id",
        "jimeng_access_key",
        "JIMENG_ACCESS_KEY_ID",
        "VOLCENGINE_ACCESS_KEY_ID",
    ):
        value = str(namespace.get(key_name, "")).strip()
        if value:
            access_key = value
            break
    for key_name in (
        "jimeng_secret_access_key",
        "jimeng_secret_key",
        "JIMENG_SECRET_ACCESS_KEY",
        "VOLCENGINE_SECRET_ACCESS_KEY",
    ):
        value = str(namespace.get(key_name, "")).strip()
        if value:
            secret_key = value
            break
    return access_key, secret_key


def _jimeng_sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _jimeng_hmac_bytes(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _jimeng_normalize_query(params: dict[str, Any]) -> str:
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


def build_jimeng_auth_headers(action: str, body_text: str) -> dict[str, str]:
    access_key, secret_key = load_jimeng_credentials()
    single_api_key = str(load_config_namespace().get("jimeng_jimeng_api_key", "")).strip()
    if not access_key or not secret_key:
        if single_api_key:
            raise RuntimeError(
                "Agent 需要火山引擎 AK/SK 签名鉴权，当前 config.py 里只有 `jimeng_jimeng_api_key` 单个值，"
                "还需要补充 `jimeng_access_key_id` 和 `jimeng_secret_access_key`。"
            )
        raise RuntimeError(
            "未找到 Agent 的火山引擎 AK/SK。请在 config.py 或环境变量中配置 "
            "`jimeng_access_key_id` 和 `jimeng_secret_access_key`。"
        )

    now_utc = datetime.now(timezone.utc)
    request_date = now_utc.strftime("%Y%m%dT%H%M%SZ")
    short_date = now_utc.strftime("%Y%m%d")
    canonical_query = _jimeng_normalize_query(
        {
            "Action": action,
            "Version": JIMENG_API_VERSION,
        }
    )
    payload_hash = _jimeng_sha256_hex(body_text)
    signed_headers = "content-type;host;x-content-sha256;x-date"
    canonical_headers = (
        "content-type:application/json\n"
        f"host:{JIMENG_API_HOST}\n"
        f"x-content-sha256:{payload_hash}\n"
        f"x-date:{request_date}\n"
    )
    canonical_request = "\n".join(
        [
            "POST",
            "/",
            canonical_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{short_date}/{JIMENG_API_REGION}/{JIMENG_API_SERVICE}/request"
    string_to_sign = "\n".join(
        [
            "HMAC-SHA256",
            request_date,
            credential_scope,
            _jimeng_sha256_hex(canonical_request),
        ]
    )
    k_date = _jimeng_hmac_bytes(secret_key.encode("utf-8"), short_date)
    k_region = _jimeng_hmac_bytes(k_date, JIMENG_API_REGION)
    k_service = _jimeng_hmac_bytes(k_region, JIMENG_API_SERVICE)
    k_signing = _jimeng_hmac_bytes(k_service, "request")
    signature = _jimeng_hmac_bytes(k_signing, string_to_sign).hex()
    authorization = (
        f"HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Content-Type": "application/json",
        "Host": JIMENG_API_HOST,
        "X-Date": request_date,
        "X-Content-Sha256": payload_hash,
        "Authorization": authorization,
    }


def load_login_accounts() -> dict[str, str]:
    namespace = load_config_namespace()
    configured_accounts = namespace.get("login_accounts")
    if isinstance(configured_accounts, dict):
        accounts = {
            str(username).strip(): str(password)
            for username, password in configured_accounts.items()
            if str(username).strip()
        }
        if accounts:
            return accounts
    return dict(DEFAULT_LOGIN_ACCOUNTS)


def load_runtime_settings() -> dict[str, Any]:
    namespace = load_config_namespace()
    server_address = str(namespace.get("server_address") or DEFAULT_SERVER_ADDRESS).strip() or DEFAULT_SERVER_ADDRESS
    try:
        server_port = int(namespace.get("server_port") or DEFAULT_SERVER_PORT)
    except Exception:
        server_port = DEFAULT_SERVER_PORT
    try:
        jimeng_static_port = int(namespace.get("jimeng_static_port") or DEFAULT_JIMENG_STATIC_PORT)
    except Exception:
        jimeng_static_port = DEFAULT_JIMENG_STATIC_PORT
    public_app_url = str(namespace.get("public_app_url") or "").strip().rstrip("/")
    if not public_app_url:
        public_app_url = f"http://www.toochuangai.com:{server_port}/lashforge"
    jimeng_public_upload_base_url = str(namespace.get("jimeng_public_upload_base_url") or "").strip().rstrip("/")
    if not jimeng_public_upload_base_url:
        jimeng_public_upload_base_url = build_jimeng_static_base_url(public_app_url, jimeng_static_port)
    return {
        "server_address": server_address,
        "server_port": server_port,
        "jimeng_static_port": jimeng_static_port,
        "public_app_url": public_app_url,
        "jimeng_public_upload_base_url": jimeng_public_upload_base_url,
    }


def build_auth_token(username: str) -> str:
    normalized_username = str(username or "").strip().lower()
    raw = f"{AUTH_TOKEN_SALT}:{normalized_username}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def persist_auth_session(username: str) -> None:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        return
    st.query_params[AUTH_QUERY_USER_KEY] = normalized_username
    st.query_params[AUTH_QUERY_TOKEN_KEY] = build_auth_token(normalized_username)


def clear_persisted_auth_session() -> None:
    try:
        del st.query_params[AUTH_QUERY_USER_KEY]
    except Exception:
        pass
    try:
        del st.query_params[AUTH_QUERY_TOKEN_KEY]
    except Exception:
        pass


def clear_query_param(param_key: str) -> None:
    try:
        del st.query_params[param_key]
    except Exception:
        pass


def get_requested_auth_username() -> str:
    candidate_keys = (
        AUTH_QUERY_USER_KEY,
        "feishu_user_name",
        "user_name",
        "name",
    )
    for key in candidate_keys:
        value = str(st.query_params.get(key, "")).strip()
        if value:
            return value
    return ""


def authenticate_requested_user() -> None:
    requested_username = get_requested_auth_username()
    if requested_username:
        normalized_username = requested_username
        query_token = str(st.query_params.get(AUTH_QUERY_TOKEN_KEY, "")).strip()
        if query_token and query_token != build_auth_token(normalized_username):
            clear_query_param(AUTH_QUERY_TOKEN_KEY)
        st.session_state.is_authenticated = True
        st.session_state.auth_username = normalized_username
        st.session_state.login_username = normalized_username
        st.session_state.login_error = ""
        persist_auth_session(normalized_username)
        return
    st.session_state.is_authenticated = True
    st.session_state.auth_username = "访客"
    st.session_state.login_username = "访客"
    st.session_state.login_error = ""


def restore_auth_session() -> None:
    if st.session_state.get("is_authenticated"):
        return
    authenticate_requested_user()


def build_upload_delete_token(widget_key: str, item_index: int) -> str:
    payload = json.dumps(
        {
            "widget_key": str(widget_key or "").strip(),
            "item_index": int(item_index),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def parse_upload_delete_token(raw_token: str) -> tuple[str, int] | None:
    normalized = str(raw_token or "").strip()
    if not normalized:
        return None
    padding = "=" * (-len(normalized) % 4)
    try:
        payload = base64.urlsafe_b64decode((normalized + padding).encode("ascii")).decode("utf-8")
        parsed = json.loads(payload)
    except Exception:
        return None
    widget_key = str(parsed.get("widget_key") or "").strip()
    if not widget_key:
        return None
    try:
        item_index = int(parsed.get("item_index"))
    except Exception:
        return None
    if item_index < 0:
        return None
    return widget_key, item_index


def consume_pending_upload_delete() -> bool:
    delete_token = str(st.query_params.get(UPLOAD_DELETE_QUERY_KEY, "")).strip()
    if not delete_token:
        return False
    clear_query_param(UPLOAD_DELETE_QUERY_KEY)
    parsed = parse_upload_delete_token(delete_token)
    if parsed is None:
        return False
    widget_key, item_index = parsed
    remove_upload_cache_item(widget_key, item_index)
    reset_upload_widget(widget_key)
    return True


def get_uploader_nonce_state_key(widget_key: str) -> str:
    return f"uploader_nonce_{widget_key}"


def get_uploader_widget_key(widget_key: str) -> str:
    nonce_key = get_uploader_nonce_state_key(widget_key)
    nonce_value = int(st.session_state.get(nonce_key, 0) or 0)
    return f"{widget_key}__uploader__{nonce_value}"


def reset_upload_widget(widget_key: str) -> None:
    current_widget_key = get_uploader_widget_key(widget_key)
    st.session_state.pop(widget_key, None)
    st.session_state.pop(current_widget_key, None)
    nonce_key = get_uploader_nonce_state_key(widget_key)
    st.session_state[nonce_key] = int(st.session_state.get(nonce_key, 0) or 0) + 1


def file_to_data_url(uploaded_file: Any) -> str:
    if isinstance(uploaded_file, Path):
        raw = uploaded_file.read_bytes()
        file_name = uploaded_file.name
        mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    elif isinstance(uploaded_file, dict):
        raw = bytes(uploaded_file.get("data") or b"")
        file_name = str(uploaded_file.get("name") or "")
        mime_type = str(uploaded_file.get("type") or "") or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    else:
        raw = uploaded_file.getvalue()
        file_name = getattr(uploaded_file, "name", "")
        mime_type = getattr(uploaded_file, "type", "") or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    encoded = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def get_model_reference_files() -> list[Path]:
    if OUTPUTS_HD_DEFAULT_REFERENCE_FILE.exists() and OUTPUTS_HD_DEFAULT_REFERENCE_FILE.is_file():
        return [OUTPUTS_HD_DEFAULT_REFERENCE_FILE]
    if HD_MODEL_REFERENCE_FILE.exists() and HD_MODEL_REFERENCE_FILE.is_file():
        return [HD_MODEL_REFERENCE_FILE]
    candidate_dirs = [
        OUTPUTS_HD_REFERENCE_DIR,
        APP_DIR / "model_reference",
        APP_DIR / "__pycache__" / "model_reference",
    ]
    results: list[Path] = []
    seen: set[Path] = set()
    for folder in candidate_dirs:
        if not folder.exists() or not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in REFERENCE_IMAGE_EXTENSIONS:
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    results.append(path)
    return results


def get_skin_texture_reference_files() -> list[Path]:
    if not SKIN_TEXTURE_REFERENCE_DIR.exists() or not SKIN_TEXTURE_REFERENCE_DIR.is_dir():
        return []
    results: list[Path] = []
    for path in sorted(SKIN_TEXTURE_REFERENCE_DIR.iterdir()):
        if path.is_file() and path.suffix.lower() in REFERENCE_IMAGE_EXTENSIONS:
            results.append(path)
    return results


def ensure_state() -> None:
    if "feature_results" not in st.session_state:
        st.session_state.feature_results = {}
    if "selected_feature_key" not in st.session_state:
        st.session_state.selected_feature_key = FEATURES[0]["key"]
    if "is_authenticated" not in st.session_state:
        st.session_state.is_authenticated = False
    if "auth_username" not in st.session_state:
        st.session_state.auth_username = ""
    if "history_panel_expanded" not in st.session_state:
        st.session_state.history_panel_expanded = {}
    if "history_records_cache" not in st.session_state:
        st.session_state.history_records_cache = {}
    if "history_visible_counts" not in st.session_state:
        st.session_state.history_visible_counts = {}
    if "local_history_records" not in st.session_state:
        st.session_state.local_history_records = {}
    if "background_jobs" not in st.session_state:
        st.session_state.background_jobs = {}


def ensure_history_storage() -> None:
    UPLOAD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DB_IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def get_current_account_name() -> str:
    return str(st.session_state.get("auth_username") or "admin").strip() or "admin"


def build_upload_cache_token(account_name: str, widget_key: str) -> str:
    raw = f"{account_name}:{widget_key}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def sanitize_file_name(file_name: str) -> str:
    original_name = str(file_name or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", original_name).strip("._")
    if cleaned:
        return cleaned[:96]
    if original_name:
        return f"file_{hashlib.sha1(original_name.encode('utf-8')).hexdigest()[:12]}"
    return "upload.bin"


def get_upload_cache_dir(account_name: str, widget_key: str) -> Path:
    ensure_history_storage()
    safe_account = sanitize_file_name(account_name)
    cache_token = build_upload_cache_token(account_name, widget_key)
    return UPLOAD_CACHE_DIR / safe_account / cache_token


def ensure_jimeng_upload_dir() -> Path:
    ensure_history_storage()
    upload_dir = DB_IMAGE_DIR / JIMENG_UPLOAD_SUBDIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_jimeng_public_upload_base_url() -> str:
    runtime_settings = load_runtime_settings()
    return str(runtime_settings.get("jimeng_public_upload_base_url") or "").strip().rstrip("/")


def get_history_public_base_url() -> str:
    runtime_settings = load_runtime_settings()
    public_app_url = str(runtime_settings.get("public_app_url") or DEFAULT_PUBLIC_APP_URL).strip() or DEFAULT_PUBLIC_APP_URL
    try:
        static_port = int(runtime_settings.get("jimeng_static_port") or DEFAULT_JIMENG_STATIC_PORT)
    except Exception:
        static_port = DEFAULT_JIMENG_STATIC_PORT
    return build_history_static_base_url(public_app_url, static_port).rstrip("/")


def convert_history_path_to_public_url(image_path_text: str) -> str:
    normalized = str(image_path_text or "").strip()
    if not normalized:
        return ""
    if normalized.startswith(("http://", "https://", "data:", "file://")):
        return normalized
    candidate = Path(normalized)
    if not candidate.exists() or not candidate.is_file():
        return normalized
    try:
        relative_path = candidate.resolve().relative_to(ensure_db_image_dir().resolve())
    except Exception:
        return normalized
    encoded_relative_path = "/".join(urllib.parse.quote(part) for part in relative_path.parts)
    return f"{get_history_public_base_url()}/{encoded_relative_path}"


def save_uploaded_inputs_for_jimeng(uploaded_files: list[Any]) -> list[str]:
    if not uploaded_files:
        return []
    base_url = get_jimeng_public_upload_base_url()
    if not base_url:
        raise RuntimeError("未配置 Agent 上传公网地址。请先在 config.py 中配置 `jimeng_public_upload_base_url`。")
    upload_dir = ensure_jimeng_upload_dir()
    public_urls: list[str] = []
    for index, uploaded_file in enumerate(uploaded_files, start=1):
        normalized = prepare_jimeng_i2i_uploaded_input(uploaded_file)
        image_bytes = bytes(normalized.get("data") or b"")
        if not image_bytes:
            continue
        original_name = sanitize_file_name(str(normalized.get("name") or f"jimeng_input_{index}.png"))
        extension = Path(original_name).suffix.lower()
        if extension not in REFERENCE_IMAGE_EXTENSIONS:
            extension = get_image_extension_from_mime(str(normalized.get("type") or "image/png"))
        image_bytes, extension = normalize_image_bytes_for_jimeng(image_bytes, extension)
        file_name = (
            f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{index:02d}_{uuid4().hex[:10]}{extension}"
        )
        saved_path = upload_dir / file_name
        saved_path.write_bytes(image_bytes)
        public_urls.append(f"{base_url}/{urllib.parse.quote(file_name)}")
    return public_urls


def build_history_download_public_url(image_source: str) -> str:
    normalized_source = str(image_source or "").strip()
    if not normalized_source:
        return ""
    if normalized_source.startswith(("http://", "https://")):
        return normalized_source
    upload_base_url = get_jimeng_public_upload_base_url()
    if not upload_base_url:
        return normalized_source
    upload_dir = ensure_jimeng_upload_dir() / "history_downloads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(normalized_source)
    if source_path.exists() and source_path.is_file():
        target_name = source_path.name
        target_path = upload_dir / target_name
        try:
            if not target_path.exists() or target_path.stat().st_size != source_path.stat().st_size:
                target_path.write_bytes(source_path.read_bytes())
        except Exception:
            return normalized_source
        encoded_parts = "/".join(urllib.parse.quote(part) for part in ("history_downloads", target_name))
        return f"{upload_base_url}/{encoded_parts}"
    decoded = decode_data_url(normalized_source)
    if decoded is None:
        return normalized_source
    image_bytes, mime_type = decoded
    extension = get_image_extension_from_mime(mime_type or "image/png")
    file_name = f"history_download_{hashlib.sha1(image_bytes).hexdigest()[:16]}{extension}"
    target_path = upload_dir / file_name
    try:
        if not target_path.exists():
            target_path.write_bytes(image_bytes)
    except Exception:
        return normalized_source
    encoded_parts = "/".join(urllib.parse.quote(part) for part in ("history_downloads", file_name))
    return f"{upload_base_url}/{encoded_parts}"


def get_uploaded_file_bytes(uploaded_file: Any) -> bytes:
    if isinstance(uploaded_file, Path):
        return uploaded_file.read_bytes()
    if isinstance(uploaded_file, dict):
        return bytes(uploaded_file.get("data") or b"")
    return uploaded_file.getvalue()


def get_uploaded_file_name(uploaded_file: Any) -> str:
    if isinstance(uploaded_file, Path):
        return uploaded_file.name
    if isinstance(uploaded_file, dict):
        return str(uploaded_file.get("name") or "").strip()
    return str(getattr(uploaded_file, "name", "") or "").strip()


def get_uploaded_file_type(uploaded_file: Any) -> str:
    if isinstance(uploaded_file, Path):
        return mimetypes.guess_type(uploaded_file.name)[0] or "application/octet-stream"
    if isinstance(uploaded_file, dict):
        return str(uploaded_file.get("type") or "").strip() or "application/octet-stream"
    return str(getattr(uploaded_file, "type", "") or "").strip() or "application/octet-stream"


def normalize_uploaded_input(uploaded_file: Any) -> dict[str, Any]:
    return {
        "data": get_uploaded_file_bytes(uploaded_file),
        "name": get_uploaded_file_name(uploaded_file),
        "type": get_uploaded_file_type(uploaded_file),
    }


def prepare_outpaint_uploaded_input(
    uploaded_file: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    feather_strength: int,
    error_prefix: str = "模特扩图失败",
) -> dict[str, Any]:
    normalized = normalize_uploaded_input(uploaded_file)
    image_bytes = bytes(normalized.get("data") or b"")
    if not image_bytes:
        raise RuntimeError(f"{error_prefix}：没有可用的原图数据。")

    top_px = max(int(top_px), 0)
    bottom_px = max(int(bottom_px), 0)
    left_px = max(int(left_px), 0)
    right_px = max(int(right_px), 0)
    feather_strength = max(int(feather_strength), 0)

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            source = ImageOps.exif_transpose(image).convert("RGBA")
            source_w, source_h = source.size
            canvas_width = source_w + left_px + right_px
            canvas_height = source_h + top_px + bottom_px
            canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
            canvas.alpha_composite(source, (left_px, top_px))

            output = io.BytesIO()
            canvas.save(output, format="PNG")
            stem = Path(str(normalized.get("name") or "outpaint_input")).stem or "outpaint_input"
            return {
                "data": output.getvalue(),
                "name": f"{sanitize_file_name(stem)}_outpaint.png",
                "type": "image/png",
            }
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"{error_prefix}：扩图预处理失败。{exc}") from exc


def clear_upload_cache(widget_key: str, account_name: str | None = None) -> None:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    cache_dir = get_upload_cache_dir(normalized_account, widget_key)
    if cache_dir.exists():
        for child in cache_dir.glob("*"):
            try:
                if child.is_file():
                    child.unlink()
            except Exception:
                pass
        try:
            cache_dir.rmdir()
        except Exception:
            pass


def save_upload_cache(widget_key: str, uploaded_files: list[Any], account_name: str | None = None) -> list[dict[str, Any]]:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    cache_dir = get_upload_cache_dir(normalized_account, widget_key)
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cache_dir / "manifest.json"
    entries: list[dict[str, Any]] = []
    for child in cache_dir.glob("*"):
        if child.name != "manifest.json" and child.is_file():
            try:
                child.unlink()
            except Exception:
                pass
    for index, uploaded_file in enumerate(uploaded_files, start=1):
        normalized = normalize_uploaded_input(uploaded_file)
        file_name = normalized["name"] or f"upload_{index}.bin"
        extension = Path(file_name).suffix or mimetypes.guess_extension(normalized["type"]) or ".bin"
        cached_name = f"{index:02d}_{sanitize_file_name(Path(file_name).stem)}{extension}"
        cached_path = cache_dir / cached_name
        cached_path.write_bytes(bytes(normalized["data"]))
        entries.append(
            {
                "file_name": file_name,
                "mime_type": normalized["type"],
                "cached_name": cached_name,
            }
        )
    manifest_path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return load_upload_cache(widget_key, account_name=normalized_account)


def replace_upload_cache(widget_key: str, uploaded_files: list[Any], account_name: str | None = None) -> list[dict[str, Any]]:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    if not uploaded_files:
        clear_upload_cache(widget_key, account_name=normalized_account)
        return []
    return save_upload_cache(widget_key, uploaded_files, account_name=normalized_account)


def load_upload_cache(
    widget_key: str,
    account_name: str | None = None,
    max_files: int | None = None,
) -> list[dict[str, Any]]:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    cache_dir = get_upload_cache_dir(normalized_account, widget_key)
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    results: list[dict[str, Any]] = []
    for entry in list(entries or []):
        cached_name = str(entry.get("cached_name") or "").strip()
        if not cached_name:
            continue
        cached_path = cache_dir / cached_name
        if not cached_path.exists() or not cached_path.is_file():
            continue
        results.append(
            {
                "data": cached_path.read_bytes(),
                "name": str(entry.get("file_name") or cached_path.name),
                "type": str(entry.get("mime_type") or mimetypes.guess_type(cached_path.name)[0] or "application/octet-stream"),
            }
        )
        if max_files is not None and len(results) >= max_files:
            break
    return results


def remove_upload_cache_item(widget_key: str, item_index: int, account_name: str | None = None) -> list[dict[str, Any]]:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    current_files = load_upload_cache(widget_key, account_name=normalized_account, max_files=None)
    remaining_files = [item for index, item in enumerate(current_files) if index != item_index]
    return replace_upload_cache(widget_key, remaining_files, account_name=normalized_account)


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


@st.fragment(run_every="3s")
def render_running_job_status(feature_key: str) -> None:
    sync_background_jobs()
    current_job = st.session_state.background_jobs.get(feature_key) or {}
    status = str(current_job.get("status") or "").strip().lower()
    if status == "running":
        progress_value = max(1, min(int(current_job.get("progress") or 1), 99))
        progress_stage = str(current_job.get("stage") or "正在处理中").strip() or "正在处理中"
        st.progress(progress_value, text=f"{progress_stage}（{progress_value}%）")
        st.info("当前任务正在后台处理中，你可以切换到其他功能继续操作，结果完成后会保留。")
        st.caption("任务状态会自动刷新，运行期间也可以展开历史记录。")
        return
    st.rerun()


def get_external_request_kwargs(timeout: int, use_proxy: bool = True) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"timeout": timeout}
    if use_proxy:
        kwargs["proxies"] = REQUEST_PROXIES
    return kwargs


def escape_sql_text(value: Any) -> str:
    return str(value or "").replace("'", "''")


def get_db_connection() -> Any:
    import pytds as sql

    return sql.connect(**DB_CONFIG)


def execute_db_query(query: str) -> list[tuple[Any, ...]]:
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        return list(rows or [])
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def execute_db_non_query(query: str, params: tuple[Any, ...] | None = None) -> None:
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if params is None:
            cursor.execute(query)
        else:
            cursor.execute(query, params)
        if not conn.autocommit:
            conn.commit()
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def format_history_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "").strip()


def get_feature_name_by_key(feature_key: str) -> str:
    normalized_key = str(feature_key or "").strip()
    for feature in FEATURES:
        if str(feature.get("key") or "").strip() == normalized_key:
            return str(feature.get("name") or normalized_key)
    return normalized_key


def ensure_db_image_dir() -> Path:
    DB_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    return DB_IMAGE_DIR


def get_image_extension_from_mime(mime_type: str) -> str:
    normalized_mime = str(mime_type or "").strip().lower()
    extension = mimetypes.guess_extension(normalized_mime) or ".png"
    if extension == ".jpe":
        return ".jpg"
    return extension


def normalize_image_bytes_for_jimeng(image_bytes: bytes, extension: str) -> tuple[bytes, str]:
    normalized_extension = str(extension or "").strip().lower()
    if normalized_extension in {".png", ".jpg", ".jpeg"}:
        return image_bytes, ".jpg" if normalized_extension == ".jpeg" else normalized_extension
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")
            output = io.BytesIO()
            if "A" in converted.getbands():
                converted.save(output, format="PNG")
                return output.getvalue(), ".png"
            converted.save(output, format="JPEG", quality=95, subsampling=0)
            return output.getvalue(), ".jpg"
    except Exception:
        return image_bytes, ".png"


def prepare_jimeng_hd_input_base64(uploaded_file: Any) -> str:
    normalized = normalize_uploaded_input(uploaded_file)
    image_bytes = bytes(normalized.get("data") or b"")
    if not image_bytes:
        raise RuntimeError("Agent 高清失败：没有可用的原图数据。")
    original_name = sanitize_file_name(str(normalized.get("name") or "hd_input.jpg"))
    extension = Path(original_name).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg"}:
        extension = get_image_extension_from_mime(str(normalized.get("type") or "image/jpeg"))
    image_bytes, _extension = normalize_image_bytes_for_jimeng(image_bytes, extension)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")
            if max(working.size) > JIMENG_HD_API_MAX_EDGE:
                ratio = JIMENG_HD_API_MAX_EDGE / float(max(working.size))
                resized_size = (
                    max(1, int(round(working.size[0] * ratio))),
                    max(1, int(round(working.size[1] * ratio))),
                )
                working = working.resize(resized_size, Image.Resampling.LANCZOS)
            if "A" in working.getbands():
                background = Image.new("RGB", working.size, (255, 255, 255))
                background.paste(working, mask=working.getchannel("A"))
                working = background
            else:
                working = working.convert("RGB")
            quality_candidates = (95, 90, 86, 82, 78, 74, 70, 66)
            output_bytes = b""
            for quality in quality_candidates:
                output = io.BytesIO()
                working.save(output, format="JPEG", quality=quality, optimize=True)
                output_bytes = output.getvalue()
                if len(output_bytes) <= JIMENG_HD_API_MAX_BYTES:
                    break
            if len(output_bytes) > JIMENG_HD_API_MAX_BYTES:
                raise RuntimeError("Agent 高清失败：原图压缩后仍超过火山智能超清接口 4.7MB 限制。")
            return base64.b64encode(output_bytes).decode("utf-8")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Agent 高清失败：原图预处理失败。{exc}") from exc


def prepare_jimeng_i2i_uploaded_input(
    uploaded_file: Any,
    error_prefix: str = "Agent 参考图失败",
) -> dict[str, Any]:
    normalized = normalize_uploaded_input(uploaded_file)
    image_bytes = bytes(normalized.get("data") or b"")
    if not image_bytes:
        raise RuntimeError(f"{error_prefix}：没有可用的图片数据。")
    original_name = sanitize_file_name(str(normalized.get("name") or "jimeng_i2i_input.jpg"))
    extension = Path(original_name).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg"}:
        extension = get_image_extension_from_mime(str(normalized.get("type") or "image/jpeg"))
    image_bytes, extension = normalize_image_bytes_for_jimeng(image_bytes, extension)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")
            if max(working.size) > JIMENG_I2I_MAX_EDGE:
                ratio = JIMENG_I2I_MAX_EDGE / float(max(working.size))
                resized_size = (
                    max(1, int(round(working.size[0] * ratio))),
                    max(1, int(round(working.size[1] * ratio))),
                )
                working = working.resize(resized_size, Image.Resampling.LANCZOS)
            if "A" in working.getbands():
                background = Image.new("RGB", working.size, (255, 255, 255))
                background.paste(working, mask=working.getchannel("A"))
                working = background
            else:
                working = working.convert("RGB")
            quality_candidates = (92, 88, 84, 80, 76, 72, 68, 64)
            output_bytes = b""
            for quality in quality_candidates:
                output = io.BytesIO()
                working.save(output, format="JPEG", quality=quality, optimize=True)
                output_bytes = output.getvalue()
                if len(output_bytes) <= JIMENG_I2I_MAX_BYTES:
                    break
            if len(output_bytes) > JIMENG_I2I_MAX_BYTES:
                raise RuntimeError(
                    f"{error_prefix}：图片压缩后仍超过 Agent 4.6 图生图输入限制。"
                )
            return {
                "data": output_bytes,
                "name": f"{Path(original_name).stem}.jpg",
                "type": "image/jpeg",
            }
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"{error_prefix}：图片预处理失败。{exc}") from exc


def build_uploaded_input_from_image_url_raw(image_url: str, base_name: str = "hd_input.jpg") -> dict[str, Any]:
    image_bytes, mime_type = load_image_bytes_from_url(image_url)
    return {
        "data": image_bytes,
        "name": sanitize_file_name(base_name),
        "type": mime_type or "image/png",
    }


def build_portrait_hd_prompt(prompt: str) -> str:
    base_prompt = str(prompt or "").strip()
    rules = (
        "图片使用规则：\n"
        "- 第一张图片是需要高清增强的主图，必须以第一张图片的人物身份、五官、脸型、表情、发型、构图和背景为准。\n"
        "- 如果提供了第二张图片，第二张图片只作为肤质参考：皮肤状态必须严格参考第二张图片，仅参考皮肤纹理、毛孔细节、真实光泽、清透度、皮肤颗粒感、细腻程度和整体肤感。\n"
        "- 不允许弱参考，不允许忽略第二张图的皮肤状态；最终皮肤观感必须尽量向第二张图贴近。\n"
        "- 严禁从第二张图片借用或迁移脸型、五官、眼睛形状、鼻子、嘴唇、眉形、妆容、肤色、表情、发型、服饰、背景或人物身份。\n"
        "- 最终结果必须仍然是第一张图片中的同一个人。"
    )
    if base_prompt:
        return f"{base_prompt}\n\n{rules}"
    return rules


def get_portrait_hd_inputs(uploaded_files: list[Any] | None = None) -> list[Any]:
    normalized_files = list(uploaded_files or [])
    if not normalized_files:
        raise RuntimeError("高清失败：请先上传 1 张主图。")
    portrait_inputs = [normalized_files[0]]
    if len(normalized_files) >= 2:
        portrait_inputs.append(normalized_files[1])
        return portrait_inputs
    reference_files = get_model_reference_files()
    if reference_files:
        portrait_inputs.append(reference_files[0])
    return portrait_inputs


def build_history_thumbnail_path(image_path: Path) -> Path:
    return image_path.parent / DB_HISTORY_THUMB_DIR_NAME / f"{image_path.stem}_thumb.jpg"


def save_history_thumbnail(image_bytes: bytes, original_path: Path) -> str:
    thumbnail_path = build_history_thumbnail_path(original_path)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = image.convert("RGB")
            converted.thumbnail((DB_HISTORY_THUMB_MAX_EDGE, DB_HISTORY_THUMB_MAX_EDGE), Image.Resampling.LANCZOS)
            quality_candidates = (82, 76, 70, 64, 58, 52)
            output_bytes = b""
            for quality in quality_candidates:
                output = io.BytesIO()
                converted.save(output, format="JPEG", quality=quality, optimize=True)
                output_bytes = output.getvalue()
                if len(output_bytes) <= DB_HISTORY_THUMB_TARGET_BYTES or quality == quality_candidates[-1]:
                    break
    except Exception:
        return str(original_path)
    thumbnail_path.write_bytes(output_bytes)
    return str(thumbnail_path)


def ensure_history_thumbnail(image_path_text: str) -> str:
    image_path = Path(str(image_path_text or "").strip())
    if not image_path.exists() or not image_path.is_file():
        return str(image_path_text or "")
    thumbnail_path = build_history_thumbnail_path(image_path)
    if thumbnail_path.exists() and thumbnail_path.is_file():
        return str(thumbnail_path)
    try:
        return save_history_thumbnail(image_path.read_bytes(), image_path)
    except Exception:
        return str(image_path)


def build_db_history_image_value(image_path: Path) -> str:
    full_path_text = str(image_path)
    if len(full_path_text) <= DB_HISTORY_PATH_MAX_LENGTH:
        return full_path_text
    file_name = image_path.name
    if len(file_name) <= DB_HISTORY_PATH_MAX_LENGTH:
        return file_name
    suffix = image_path.suffix or ".png"
    stem_limit = max(DB_HISTORY_PATH_MAX_LENGTH - len(suffix), 1)
    return f"{image_path.stem[:stem_limit]}{suffix}"


def build_saved_history_file_name(created_at: datetime, index: int, extension: str) -> str:
    return f"{created_at.strftime('%Y%m%d_%H%M%S_%f')}_{index:02d}{extension}"


def try_find_history_image_by_metadata(
    account_name: str,
    feature_name: str,
    created_at_text: str,
) -> str:
    normalized_created_at = str(created_at_text or "").strip()
    if not normalized_created_at:
        return ""
    try:
        created_at = datetime.strptime(normalized_created_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""
    prefix = created_at.strftime("%Y%m%d_%H%M%S")
    storage_dir = ensure_db_image_dir()
    candidates = sorted(storage_dir.glob(f"{prefix}_*"), key=lambda path: path.name)
    if not candidates:
        return ""
    safe_account = sanitize_file_name(account_name or "")
    narrowed_candidates = [
        path
        for path in candidates
        if safe_account and safe_account.lower() in path.name.lower()
    ]
    if narrowed_candidates:
        return str(narrowed_candidates[0])
    return str(candidates[0])


def resolve_db_history_image_path(
    image_path_text: str,
    account_name: str = "",
    feature_name: str = "",
    created_at_text: str = "",
) -> str:
    normalized = str(image_path_text or "").strip()
    if not normalized:
        return try_find_history_image_by_metadata(account_name, feature_name, created_at_text)
    candidate = Path(normalized)
    if candidate.is_absolute():
        return str(candidate)
    resolved_path = ensure_db_image_dir() / candidate.name
    if resolved_path.exists() and resolved_path.is_file():
        return str(resolved_path)
    same_prefix_candidates = sorted(
        ensure_db_image_dir().glob(f"{candidate.stem}*{candidate.suffix}"),
        key=lambda path: path.name,
    )
    if same_prefix_candidates:
        return str(same_prefix_candidates[0])
    return try_find_history_image_by_metadata(account_name, feature_name, created_at_text)


def insert_history_db_record(
    account_name: str,
    feature_name: str,
    model: str,
    image_path: str,
    created_at_text: str,
    image_count: int,
) -> None:
    insert_query = (
        f"INSERT INTO {DB_HISTORY_TABLE} (ZhangHao, GongNeng, MoXing, TuPian, RiQi, ZhangShu) "
        f"VALUES (%s, %s, %s, %s, %s, %s)"
    )
    execute_db_non_query(
        insert_query,
        (
            str(account_name or ""),
            str(feature_name or ""),
            str(model or ""),
            str(image_path or ""),
            str(created_at_text or ""),
            max(int(image_count), 0),
        ),
    )


def save_generated_images_and_record_db(
    feature: dict[str, Any],
    model: str,
    prompt: str,
    result: dict[str, Any],
    account_name: str,
) -> list[dict[str, Any]]:
    normalized_account = str(account_name or "admin").strip() or "admin"
    feature_key = str(feature.get("key") or "").strip()
    feature_name = str(feature.get("name") or feature_key).strip()
    created_at = datetime.now()
    created_at_text = created_at.strftime("%Y-%m-%d %H:%M:%S")
    records: list[dict[str, Any]] = []
    image_sources = list(result.get("images") or [])
    image_count = len(image_sources)
    if not image_sources:
        insert_history_db_record(
            account_name=normalized_account,
            feature_name=feature_name,
            model=str(model or ""),
            image_path="",
            created_at_text=created_at_text,
            image_count=image_count,
        )
        records.append(
            {
                "account_name": normalized_account,
                "feature_key": feature_key,
                "feature_name": feature_name,
                "model": str(model or ""),
                "prompt": str(prompt or ""),
                "images": [],
                "created_at": created_at_text,
                "image_index": 1,
            }
        )
        return records
    storage_dir = ensure_db_image_dir()
    for index, image_source in enumerate(image_sources, start=1):
        image_bytes, mime_type = load_image_bytes_from_url(str(image_source))
        extension = get_image_extension_from_mime(mime_type)
        file_name = build_saved_history_file_name(created_at, index, extension)
        saved_path = storage_dir / file_name
        saved_path.write_bytes(image_bytes)
        image_path_text = str(saved_path)
        db_image_path_text = build_db_history_image_value(saved_path)
        thumbnail_path_text = ensure_history_thumbnail(image_path_text)
        insert_history_db_record(
            account_name=normalized_account,
            feature_name=feature_name,
            model=str(model or ""),
            image_path=db_image_path_text,
            created_at_text=created_at_text,
            image_count=image_count,
        )
        records.append(
            {
                "account_name": normalized_account,
                "feature_key": feature_key,
                "feature_name": feature_name,
                "model": str(model or ""),
                "prompt": str(prompt or ""),
                "images": [thumbnail_path_text],
                "original_images": [image_path_text],
                "thumbnail_images": [thumbnail_path_text],
                "created_at": created_at_text,
                "image_index": index,
            }
        )
    return records


def persist_generated_images_in_background(
    feature: dict[str, Any],
    model: str,
    prompt: str,
    result: dict[str, Any],
    account_name: str,
) -> None:
    safe_feature = dict(feature)
    safe_result = {"images": list(result.get("images") or [])}
    safe_model = str(model or "")
    safe_prompt = str(prompt or "")
    safe_account_name = str(account_name or "admin")

    def worker() -> None:
        try:
            save_generated_images_and_record_db(
                feature=safe_feature,
                model=safe_model,
                prompt=safe_prompt,
                result=safe_result,
                account_name=safe_account_name,
            )
        except Exception as exc:
            print(f"[history-save] 后台保存失败：{exc}", file=sys.stderr)

    Thread(target=worker, daemon=True).start()


def load_db_history_records(
    feature_key: str,
    account_name: str,
    limit: int = DB_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    safe_limit = max(int(limit), 1)
    query = (
        f"SELECT TOP {safe_limit} ZhangHao, GongNeng, MoXing, TuPian, RiQi "
        f"FROM {DB_HISTORY_TABLE} "
        f"ORDER BY RiQi DESC, ID DESC"
    )
    rows = execute_db_query(query)
    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        account_value = str(row[0] if len(row) > 0 else "").strip()
        feature_name_value = str(row[1] if len(row) > 1 else "").strip()
        model_value = str(row[2] if len(row) > 2 else "").strip()
        created_at = format_history_datetime(row[4] if len(row) > 4 else "")
        image_path = resolve_db_history_image_path(
            str(row[3] if len(row) > 3 else "").strip(),
            account_name=account_value,
            feature_name=feature_name_value,
            created_at_text=created_at,
        )
        if not image_path:
            continue
        thumbnail_path = ensure_history_thumbnail(image_path)
        thumbnail_source = convert_history_path_to_public_url(thumbnail_path or image_path)
        original_source = convert_history_path_to_public_url(image_path)
        local_thumbnail_source = ""
        try:
            thumbnail_candidate = Path(str(thumbnail_path or "").strip())
            image_candidate = Path(str(image_path or "").strip())
            if thumbnail_candidate.exists() and thumbnail_candidate.is_file() and thumbnail_candidate != image_candidate:
                local_thumbnail_source = str(thumbnail_candidate)
            else:
                local_thumbnail_source = build_history_thumbnail_source(str(image_path))
        except Exception:
            local_thumbnail_source = str(thumbnail_path or image_path)
        records.append(
            {
                "account_name": account_value,
                "feature_key": feature_key,
                "feature_name": feature_name_value,
                "model": model_value,
                "prompt": "",
                "images": [thumbnail_source or original_source],
                "original_images": [original_source],
                "thumbnail_images": [thumbnail_source or original_source],
                "local_images": [local_thumbnail_source],
                "local_original_images": [str(image_path)],
                "created_at": created_at,
                "image_index": index,
            }
        )
    return records


def get_history_cache_key(account_name: str, feature_key: str) -> str:
    return "global:all_history"


def get_history_visible_limit(cache_key: str) -> int:
    current = st.session_state.history_visible_counts.get(cache_key, HISTORY_PAGE_SIZE)
    return max(int(current), HISTORY_PAGE_SIZE)


def set_history_visible_limit(cache_key: str, limit: int) -> None:
    st.session_state.history_visible_counts[cache_key] = max(int(limit), HISTORY_PAGE_SIZE)


def ensure_history_records_loaded(feature_key: str, account_name: str, cache_key: str, limit: int) -> list[dict[str, Any]]:
    safe_limit = max(int(limit), HISTORY_PAGE_SIZE)
    cached_records = st.session_state.history_records_cache.get(cache_key)
    if cached_records is not None and len(cached_records) >= safe_limit:
        return list(cached_records)
    records = get_feature_history_records(feature_key, account_name, limit=safe_limit)
    st.session_state.history_records_cache[cache_key] = records
    return records


def normalize_history_image_source(image_source: str) -> str:
    image_bytes, mime_type = load_image_bytes_from_url(image_source)
    return image_bytes_to_data_url(image_bytes, mime_type or "image/png")


def build_history_thumbnail_source(image_source: str) -> str:
    image_bytes, mime_type = load_image_bytes_from_url(image_source)
    preview_item = build_gallery_preview_data_url(image_bytes, mime_type or "image/png")
    if preview_item is not None:
        return preview_item[0]
    return image_bytes_to_data_url(image_bytes, mime_type or "image/png")


def build_local_history_records(
    feature: dict[str, Any],
    model: str,
    prompt: str,
    result: dict[str, Any],
    account_name: str,
) -> list[dict[str, Any]]:
    normalized_account = str(account_name or "admin").strip() or "admin"
    created_at = datetime.now()
    created_at_text = created_at.strftime("%Y-%m-%d %H:%M:%S")
    records: list[dict[str, Any]] = []
    for index, image_source in enumerate(result.get("images") or [], start=1):
        try:
            local_image_source = normalize_history_image_source(image_source)
            local_thumbnail_source = build_history_thumbnail_source(image_source)
        except Exception:
            continue
        records.append(
            {
                "account_name": normalized_account,
                "feature_key": str(feature.get("key") or ""),
                "feature_name": str(feature.get("name") or ""),
                "model": str(model or ""),
                "prompt": str(prompt or ""),
                "images": [local_thumbnail_source],
                "original_images": [local_image_source],
                "thumbnail_images": [local_thumbnail_source],
                "local_images": [local_thumbnail_source],
                "local_original_images": [local_image_source],
                "created_at": created_at_text,
                "image_index": index,
            }
        )
    return records


def store_local_history_records(account_name: str, feature_key: str, records: list[dict[str, Any]]) -> None:
    normalized_account = str(account_name or "admin").strip() or "admin"
    user_store = dict(st.session_state.local_history_records.get(normalized_account) or {})
    existing_records = list(user_store.get(feature_key) or [])
    merged_records = list(records) + existing_records
    user_store[feature_key] = merged_records[:MAX_HISTORY_RECORDS]
    st.session_state.local_history_records[normalized_account] = user_store


def get_feature_history_records(
    feature_key: str,
    account_name: str,
    limit: int = DB_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    try:
        db_records = load_db_history_records(feature_key, account_name, limit=limit)
    except Exception:
        db_records = []
    if db_records:
        return db_records[: max(int(limit), 1)]
    merged_records: list[dict[str, Any]] = []
    for user_store in (st.session_state.local_history_records or {}).values():
        for record_list in dict(user_store or {}).values():
            merged_records.extend(list(record_list or []))
    merged_records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return merged_records[: max(int(limit), 1)]


def get_latest_feature_result(feature_key: str) -> dict[str, Any] | None:
    return None


def prepare_uploaded_input(uploaded_file: Any) -> Any:
    if isinstance(uploaded_file, Path):
        return uploaded_file
    if isinstance(uploaded_file, dict):
        return normalize_uploaded_input(uploaded_file)
    return normalize_uploaded_input(uploaded_file)


def get_uploaded_input_name(uploaded_input: Any) -> str:
    if isinstance(uploaded_input, Path):
        return uploaded_input.name
    if isinstance(uploaded_input, dict):
        return str(uploaded_input.get("name") or "").strip()
    return str(getattr(uploaded_input, "name", "") or "").strip()


def get_feature_min_output_edge(feature_or_key: dict[str, Any] | str | None) -> int:
    if isinstance(feature_or_key, dict):
        feature_key = str(feature_or_key.get("key") or "").strip()
    else:
        feature_key = str(feature_or_key or "").strip()
    return HD_MIN_OUTPUT_EDGE if feature_key == "hd_batch" else MIN_OUTPUT_EDGE


def is_jimeng_model(model_name: str) -> bool:
    return str(model_name or "").strip() == JIMENG_MODEL_NAME


def get_model_display_name(model_name: str) -> str:
    normalized_name = str(model_name or "").strip()
    if is_jimeng_model(normalized_name):
        return "即梦 Seedream 4.6"
    if normalized_name == NANO_BANANA_MODEL:
        return "Nano Banana"
    return normalized_name


def is_jimeng_concurrent_limit_error(message: str) -> bool:
    normalized_message = str(message or "").strip().lower()
    if not normalized_message:
        return False
    return (
        "request has reached api concurrent limit" in normalized_message
        or "concurrent limit" in normalized_message
        or "exceededconcurrentquota" in normalized_message
    )


def process_batch_group(job_context: dict[str, Any], uploaded_group: list[Any], group_index: int) -> dict[str, Any]:
    source_name = get_uploaded_input_name(uploaded_group[0]) if uploaded_group else ""
    feature_key = str((job_context.get("feature") or {}).get("key") or "")
    min_output_edge = get_feature_min_output_edge(feature_key)
    if is_jimeng_model(str(job_context.get("model") or "")):
        if feature_key == "hd_batch":
            batch_result = call_jimeng_portrait_hd(
                prompt=str(job_context["prompt"]),
                aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
                uploaded_files=list(uploaded_group),
                feature_key=feature_key,
            )
        else:
            batch_result = call_jimeng_v40(
                prompt=str(job_context["prompt"]),
                aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
                uploaded_files=list(uploaded_group),
                feature_key=feature_key,
            )
    else:
        if feature_key == "hd_batch" and str(job_context.get("output_mode") or "") == "image":
            batch_result = call_openrouter_portrait_hd(
                model=str(job_context["model"]),
                prompt=str(job_context["prompt"]),
                aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
                uploaded_files=list(uploaded_group),
            )
        else:
            batch_result = call_openrouter(
                model=str(job_context["model"]),
                prompt=str(job_context["prompt"]),
                uploaded_files=list(uploaded_group),
                output_mode=str(job_context["output_mode"]),
                aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
            )
    if job_context["output_mode"] == "image":
        target_size = job_context.get("target_size")
        if target_size:
            batch_result["images"] = [
                resize_image_to_exact_size(image_url, int(target_size[0]), int(target_size[1]))
                for image_url in (batch_result.get("images") or [])
            ]
        elif feature_key != "hd_batch":
            batch_result["images"] = [
                upscale_image_to_min_edge(
                    image_url,
                    min_output_edge,
                    enhance_detail=(feature_key == "hd_batch"),
                )
                for image_url in (batch_result.get("images") or [])
            ]
    max_output_images = int(job_context.get("max_output_images") or 0)
    if max_output_images > 0:
        batch_result["images"] = (batch_result.get("images") or [])[:max_output_images]
    return {
        "group_index": group_index,
        "source_name": source_name,
        "images": list(batch_result.get("images") or []),
        "text": str(batch_result.get("text") or "").strip(),
    }


def run_feature_job(job_context: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    if job_id:
        set_task_progress(job_id, 5, "准备上传图片")
    batch_groups = list(job_context.get("batch_groups") or [])
    if batch_groups:
        merged_images: list[str] = []
        merged_texts: list[str] = []
        merged_captions: list[str] = []
        total_groups = max(len(batch_groups), 1)
        requested_batch_concurrency = max(
            1,
            min(int(job_context.get("batch_concurrency") or DEFAULT_BATCH_API_CONCURRENCY), MAX_BATCH_API_CONCURRENCY),
        )
        if is_jimeng_model(str(job_context.get("model") or "")):
            requested_batch_concurrency = min(requested_batch_concurrency, JIMENG_MAX_API_CONCURRENCY)
        effective_batch_concurrency = min(requested_batch_concurrency, total_groups)
        completed_results: dict[int, dict[str, Any]] = {}
        if effective_batch_concurrency <= 1 or total_groups <= 1:
            for group_index, uploaded_group in enumerate(batch_groups, start=1):
                if job_id:
                    progress_start = 8 + math.floor(((group_index - 1) / total_groups) * 58)
                    set_task_progress(
                        job_id,
                        progress_start,
                        f"正在生成第 {group_index}/{total_groups} 张，实际并发 {effective_batch_concurrency} 路",
                    )
                completed_results[group_index] = process_batch_group(job_context, uploaded_group, group_index)
                if job_id:
                    progress_post = 18 + math.floor((group_index / total_groups) * 60)
                    set_task_progress(job_id, progress_post, f"正在整理第 {group_index}/{total_groups} 张结果")
        else:
            if job_id:
                set_task_progress(
                    job_id,
                    8,
                    f"正在并发生成，共 {total_groups} 张，实际并发 {effective_batch_concurrency} 路",
                )
            completed_count = 0
            with ThreadPoolExecutor(max_workers=effective_batch_concurrency) as batch_executor:
                future_map = {
                    batch_executor.submit(process_batch_group, job_context, uploaded_group, group_index): group_index
                    for group_index, uploaded_group in enumerate(batch_groups, start=1)
                }
                for future in as_completed(future_map):
                    group_index = future_map[future]
                    completed_results[group_index] = future.result()
                    completed_count += 1
                    if job_id:
                        progress_post = 18 + math.floor((completed_count / total_groups) * 60)
                        set_task_progress(
                            job_id,
                            progress_post,
                            f"已完成 {completed_count}/{total_groups} 张，实际并发 {effective_batch_concurrency} 路",
                        )
        for group_index in range(1, total_groups + 1):
            group_result = completed_results[group_index]
            batch_images = list(group_result.get("images") or [])
            merged_images.extend(batch_images)
            if batch_images:
                base_caption = str(group_result.get("source_name") or "").strip() or f"原图 {group_index}"
                if len(batch_images) == 1:
                    merged_captions.append(base_caption)
                else:
                    merged_captions.extend([f"{base_caption} - 结果 {index + 1}" for index in range(len(batch_images))])
            batch_text = str(group_result.get("text") or "").strip()
            if batch_text:
                merged_texts.append(batch_text)
        if not merged_images and job_context["output_mode"] == "image":
            backend_name = "Agent" if is_jimeng_model(str(job_context.get("model") or "")) else "OpenRouter"
            raise RuntimeError(f"{backend_name} 未返回图片：请求已提交，但响应中没有可用的结果图片。")
        result = {
            "images": merged_images,
            "text": "\n\n".join(merged_texts).strip(),
            "captions": merged_captions,
        }
    else:
        if job_id:
            set_task_progress(job_id, 18, "正在请求模型生成结果")
        feature_mode = str((job_context.get("feature") or {}).get("mode") or "openrouter")
        feature_key = str((job_context.get("feature") or {}).get("key") or "")
        if feature_mode == "jimeng" or is_jimeng_model(str(job_context.get("model") or "")):
            if feature_key == "hd_batch":
                result = call_jimeng_portrait_hd(
                    prompt=str(job_context["prompt"]),
                    aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
                    uploaded_files=list(job_context.get("uploaded_files") or []),
                    feature_key=feature_key,
                )
            else:
                result = call_jimeng_v40(
                    prompt=str(job_context["prompt"]),
                    aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
                    uploaded_files=list(job_context.get("uploaded_files") or []),
                    feature_key=feature_key,
                )
        else:
            if feature_key == "hd_batch" and str(job_context.get("output_mode") or "") == "image":
                result = call_openrouter_portrait_hd(
                    model=str(job_context["model"]),
                    prompt=str(job_context["prompt"]),
                    aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
                    uploaded_files=list(job_context["uploaded_files"]),
                )
            else:
                result = call_openrouter(
                    model=str(job_context["model"]),
                    prompt=str(job_context["prompt"]),
                    uploaded_files=list(job_context["uploaded_files"]),
                    output_mode=str(job_context["output_mode"]),
                    aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
                )
        if job_id:
            set_task_progress(job_id, 72, "正在整理返回图片")
        if job_context["output_mode"] == "image":
            target_size = job_context.get("target_size")
            min_output_edge = get_feature_min_output_edge(feature_key)
            if target_size:
                result["images"] = [
                    resize_image_to_exact_size(image_url, int(target_size[0]), int(target_size[1]))
                    for image_url in (result.get("images") or [])
                ]
            elif feature_key != "hd_batch":
                result["images"] = [
                    upscale_image_to_min_edge(
                        image_url,
                        min_output_edge,
                        enhance_detail=(feature_key == "hd_batch"),
                    )
                    for image_url in (result.get("images") or [])
                ]
        max_output_images = int(job_context.get("max_output_images") or 0)
        if max_output_images > 0:
            result["images"] = (result.get("images") or [])[:max_output_images]
        if job_context["output_mode"] == "image" and not (result.get("images") or []):
            backend_name = "Agent" if is_jimeng_model(str(job_context.get("model") or "")) else "OpenRouter"
            raise RuntimeError(f"{backend_name} 未返回图片：请求已提交，但响应中没有可用的结果图片。")
    if job_id:
        set_task_progress(job_id, 88, "正在整理结果并返回页面")
    account_name = str(job_context.get("account_name") or "admin")
    fallback_history_records = build_local_history_records(
        feature=dict(job_context["feature"]),
        model=str(job_context["model"]),
        prompt=str(job_context["prompt"]),
        result=result,
        account_name=account_name,
    )
    result_text_parts = [str(result.get("text") or "").strip()]
    history_records = fallback_history_records
    if result.get("images"):
        try:
            history_records = save_generated_images_and_record_db(
                feature=dict(job_context["feature"]),
                model=str(job_context["model"]),
                prompt=str(job_context["prompt"]),
                result=result,
                account_name=account_name,
            )
            result_text_parts.append("结果已保存到服务器和数据库。")
            result["storage_pending"] = False
            result.pop("storage_error", None)
        except Exception as exc:
            storage_error = f"保存生成结果失败：{exc}"
            print(f"[history-save] {storage_error}", file=sys.stderr)
            result["storage_pending"] = False
            result["storage_error"] = storage_error
            result_text_parts.append("结果已返回页面，但保存到服务器和数据库失败。")
    result["text"] = "\n\n".join(part for part in result_text_parts if part).strip()
    result["history_records"] = history_records
    result["history_account_name"] = account_name
    if job_id:
        set_task_progress(job_id, 100, "处理完成")
    return result


def submit_feature_job(feature: dict[str, Any], job_context: dict[str, Any]) -> None:
    runtime = get_task_runtime()
    job_id = f"{feature['key']}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    job_context = dict(job_context)
    job_context["job_id"] = job_id
    set_task_progress(job_id, 1, "任务已提交，等待开始")
    future = runtime.executor.submit(run_feature_job, job_context)
    with runtime.lock:
        runtime.futures[job_id] = future
    st.session_state.background_jobs[feature["key"]] = {
        "job_id": job_id,
        "status": "running",
        "feature_name": feature["name"],
        "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": "",
        "progress": 1,
        "stage": "任务已提交，等待开始",
    }


def sync_background_jobs() -> None:
    runtime = get_task_runtime()
    jobs = st.session_state.get("background_jobs") or {}
    for feature_key, job_info in list(jobs.items()):
        if job_info.get("status") != "running":
            continue
        job_id = str(job_info.get("job_id") or "")
        if not job_id:
            continue
        with runtime.lock:
            future = runtime.futures.get(job_id)
        if future is None:
            progress_info = get_task_progress(job_id)
            if progress_info:
                job_info["progress"] = int(progress_info.get("percent") or job_info.get("progress") or 1)
                job_info["stage"] = str(progress_info.get("stage") or job_info.get("stage") or "")
            else:
                job_info["status"] = "error"
                job_info["error"] = "后台任务状态已丢失，请重新提交任务。"
                job_info["progress"] = 0
                job_info["stage"] = "任务状态丢失"
            continue
        if not future.done():
            progress_info = get_task_progress(job_id)
            if progress_info:
                job_info["progress"] = int(progress_info.get("percent") or job_info.get("progress") or 1)
                job_info["stage"] = str(progress_info.get("stage") or job_info.get("stage") or "")
            continue
        try:
            result = future.result()
        except Exception as exc:
            job_info["status"] = "error"
            job_info["error"] = str(exc)
            job_info["progress"] = 0
            job_info["stage"] = "任务执行失败"
        else:
            job_info["status"] = "completed"
            job_info["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            job_info["progress"] = 100
            job_info["stage"] = "处理完成"
            st.session_state.feature_results[feature_key] = result
            account_name = str(result.get("history_account_name") or st.session_state.get("auth_username") or "admin")
            history_records = list(result.get("history_records") or [])
            if history_records:
                store_local_history_records(account_name, feature_key, history_records)
            cache_key = get_history_cache_key(account_name, feature_key)
            st.session_state.history_records_cache.pop(cache_key, None)
            set_history_visible_limit(cache_key, HISTORY_PAGE_SIZE)
        with runtime.lock:
            runtime.futures.pop(job_id, None)
        clear_task_progress(job_id)


def inject_app_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            background:
                radial-gradient(circle at top right, rgba(88, 64, 255, 0.20), transparent 28%),
                radial-gradient(circle at bottom right, rgba(88, 64, 255, 0.14), transparent 18%),
                linear-gradient(90deg, #030816 0%, #071329 45%, #08152d 100%);
            color: #f5f7ff;
        }
        [data-testid="stHeader"] {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
        }
        .stAppHeader {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            background: transparent;
        }
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu,
        button[title="View fullscreen"],
        button[title="Deploy"],
        div:has(> button[title="Deploy"]) {
            display: none !important;
            visibility: hidden !important;
        }
        [data-testid="collapsedControl"] {
            display: none !important;
            visibility: hidden !important;
        }
        [data-testid="stAppViewContainer"] {
            padding-top: 0 !important;
        }
        [data-testid="stAppViewContainer"] > .main {
            padding-top: 0 !important;
            margin-top: 0 !important;
        }
        .main .block-container {
            max-width: 1540px;
            padding-top: 0 !important;
            margin-top: 0 !important;
            padding-bottom: 2rem;
        }
        [data-testid="stMainBlockContainer"] {
            padding-top: 0 !important;
            margin-top: 0 !important;
        }
        [data-testid="stSidebar"] {
            display: none !important;
            visibility: hidden !important;
        }
        [data-testid="stSidebarContent"] {
            padding: 0.75rem 0.8rem 0.7rem;
        }
        [data-testid="stSidebar"] .stButton {
            margin-bottom: 0;
        }
        [data-testid="stSidebar"] .stButton > button {
            width: 100%;
            min-height: 46px;
            justify-content: center;
            align-items: center;
            padding: 0.38rem 0.65rem;
            border-radius: 0;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-bottom: none;
            background: rgba(6, 14, 30, 0.72);
            box-shadow: none;
            transition: all 0.18s ease;
        }
        [data-testid="stSidebar"] .stButton:first-of-type > button {
            border-top-left-radius: 14px;
            border-top-right-radius: 14px;
        }
        [data-testid="stSidebar"] .stButton:last-of-type > button {
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            border-bottom-left-radius: 14px;
            border-bottom-right-radius: 14px;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background: rgba(21, 32, 58, 0.9);
            border-color: rgba(146, 166, 255, 0.18);
            transform: none;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, rgba(118, 87, 255, 0.96), rgba(85, 62, 230, 0.94));
            border-color: rgba(169, 149, 255, 0.58);
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
        }
        [data-testid="stSidebar"] .stButton > button p {
            white-space: pre-line;
            text-align: center;
            font-size: 1rem;
            line-height: 1.2;
            font-weight: 700;
            color: rgba(255, 255, 255, 0.92);
            margin: 0;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] p {
            color: #ffffff;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, rgba(118, 87, 255, 0.96), rgba(85, 62, 230, 0.94));
            border-color: rgba(169, 149, 255, 0.58);
        }
        .brand-wrap {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            margin-bottom: 0.45rem;
        }
        .sidebar-card {
            display: block;
            text-decoration: none;
            padding: 0.9rem 1rem 0.82rem;
            margin-bottom: 0.85rem;
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            background: rgba(8, 15, 31, 0.88);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.22);
            transition: all 0.18s ease;
        }
        .sidebar-card:hover {
            border-color: rgba(144, 122, 255, 0.42);
            transform: translateY(-1px);
        }
        .sidebar-card.active {
            background: linear-gradient(135deg, rgba(106, 76, 255, 0.95), rgba(92, 65, 239, 0.92));
            border-color: rgba(144, 122, 255, 0.7);
            box-shadow: 0 14px 34px rgba(93, 68, 246, 0.28);
        }
        .sidebar-card-title {
            color: #ffffff;
            font-size: 1.02rem;
            font-weight: 700;
            line-height: 1.35;
            margin-bottom: 0.28rem;
        }
        .sidebar-card-sub {
            color: rgba(222, 226, 255, 0.78);
            font-size: 0.79rem;
            line-height: 1.45;
        }
        .brand-logo {
            width: 28px;
            height: 28px;
            border-radius: 7px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 0.85rem;
            color: #ffffff;
            background: linear-gradient(135deg, #8c7bff, #5f4bff);
            box-shadow: 0 10px 24px rgba(95, 75, 255, 0.35);
        }
        .brand-title {
            color: #ffffff;
            font-size: 1.06rem;
            font-weight: 700;
            margin: 0;
            line-height: 1.15;
        }
        .brand-subtitle {
            color: rgba(214, 219, 255, 0.72);
            font-size: 0.66rem;
            margin-top: 0.08rem;
        }
        .side-menu-shell {
            background:
                radial-gradient(circle at top right, rgba(88, 64, 255, 0.10), transparent 28%),
                linear-gradient(135deg, rgba(9, 17, 35, 0.88), rgba(7, 15, 31, 0.88));
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
            box-shadow: 0 16px 34px rgba(0, 0, 0, 0.20);
            padding: 0.46rem 0.44rem 0.42rem;
            margin-bottom: 0.24rem;
        }
        .side-menu-note {
            color: rgba(214, 219, 255, 0.7);
            font-size: 0.64rem;
            margin: 0.1rem 0 0;
        }
        div[data-testid="column"]:has(.side-menu-shell) .stButton > button {
            min-height: 31px !important;
            padding: 0.12rem 0.36rem !important;
            border-radius: 10px !important;
        }
        div[data-testid="column"]:has(.side-menu-shell) .stButton > button p {
            font-size: 0.72rem !important;
            line-height: 1.08 !important;
            font-weight: 700 !important;
        }
        div[data-testid="column"]:has(.side-menu-shell) .side-history-shell {
            margin-top: 0.45rem;
            padding-top: 0.45rem;
        }
        .side-history-shell {
            margin-top: 0.7rem;
            padding-top: 0.65rem;
            border-top: 1px solid rgba(255, 255, 255, 0.07);
        }
        .side-history-title {
            color: #f5f7ff;
            font-size: 0.9rem;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }
        .side-history-caption {
            color: rgba(214, 219, 255, 0.66);
            font-size: 0.7rem;
            margin: 0.2rem 0 0.32rem;
        }
        .history-card-time {
            color: #f5f7ff;
            font-size: 0.78rem;
            font-weight: 700;
            line-height: 1.25;
            margin-bottom: 0.12rem;
        }
        .history-card-model {
            color: rgba(214, 219, 255, 0.72);
            font-size: 0.68rem;
            line-height: 1.28;
            margin-bottom: 0.12rem;
            word-break: break-word;
        }
        .history-card-meta {
            min-height: 54px;
            margin-bottom: 0.34rem;
        }
        a[data-download-href] {
            display: none !important;
        }
        .workspace-panel {
            background:
                radial-gradient(circle at top right, rgba(88, 64, 255, 0.12), transparent 26%),
                linear-gradient(135deg, rgba(9, 17, 35, 0.92), rgba(7, 15, 31, 0.92));
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 22px;
            box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
            padding: 0.85rem 0.95rem 0.9rem;
            margin-top: 0;
        }
        .login-shell {
            min-height: calc(100vh - 2rem);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-card {
            width: min(430px, 100%);
            background:
                radial-gradient(circle at top right, rgba(88, 64, 255, 0.16), transparent 30%),
                linear-gradient(135deg, rgba(9, 17, 35, 0.96), rgba(7, 15, 31, 0.96));
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 22px;
            box-shadow: 0 28px 70px rgba(0, 0, 0, 0.34);
            padding: 1.5rem 1.35rem 1.2rem;
        }
        .login-brand {
            color: #ffffff;
            font-size: 1.8rem;
            font-weight: 800;
            margin-bottom: 0.3rem;
            text-align: center;
        }
        .login-subtitle {
            color: rgba(214, 219, 255, 0.76);
            font-size: 0.95rem;
            text-align: center;
            margin-bottom: 1.2rem;
        }
        .login-tips {
            color: rgba(214, 219, 255, 0.7);
            font-size: 0.82rem;
            text-align: center;
            margin-top: 0.7rem;
        }
        .feature-head-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 0.55rem;
        }
        .feature-left-box {
            flex: 1;
        }
        .feature-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.22rem 0.52rem;
            margin-left: 0.55rem;
            border-radius: 999px;
            font-size: 0.74rem;
            color: #dcd5ff;
            background: rgba(120, 92, 255, 0.14);
            border: 1px solid rgba(130, 103, 255, 0.28);
            vertical-align: middle;
        }
        .feature-title {
            color: #ffffff;
            font-size: 1.9rem;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }
        .feature-desc {
            color: rgba(214, 219, 255, 0.78);
            font-size: 0.98rem;
            margin-bottom: 0.85rem;
            max-width: 780px;
        }
        .meta-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.6rem;
            margin-bottom: 1rem;
        }
        .meta-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.42rem 0.75rem;
            border-radius: 999px;
            font-size: 0.84rem;
            color: #dbe0ff;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.06);
        }
        .guide-wrap {
            min-width: 140px;
        }
        .section-kicker {
            color: rgba(214, 219, 255, 0.72);
            font-size: 0.78rem;
            margin: 0.15rem 0 0.45rem;
        }
        .panel-subtitle {
            color: rgba(214, 219, 255, 0.82);
            font-size: 0.82rem;
            font-weight: 600;
            margin: 0.35rem 0 0.45rem;
        }
        .upload-main-empty, .result-empty {
            min-height: 210px;
            border-radius: 18px;
            border: 1px dashed rgba(132, 111, 255, 0.58);
            background: rgba(7, 15, 31, 0.52);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            gap: 0.55rem;
            text-align: center;
            color: rgba(214, 219, 255, 0.72);
            margin-bottom: 0.35rem;
        }
        .empty-icon {
            font-size: 1.9rem;
            color: #8b75ff;
            line-height: 1;
        }
        .empty-title {
            color: #eef1ff;
            font-size: 0.95rem;
            font-weight: 600;
        }
        .empty-subtitle {
            color: rgba(214, 219, 255, 0.62);
            font-size: 0.78rem;
        }
        .slot-empty {
            height: 88px;
            border-radius: 14px;
            border: 1px dashed rgba(132, 111, 255, 0.54);
            background: rgba(7, 15, 31, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #8b75ff;
            font-size: 1.6rem;
            margin-bottom: 0.35rem;
        }
        .slot-helper {
            color: rgba(214, 219, 255, 0.55);
            font-size: 0.72rem;
            text-align: center;
            margin: 0.15rem 0 0.4rem;
        }
        .compact-thumb img {
            border-radius: 12px !important;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .clickable-image-grid {
            display: grid;
            gap: 0.75rem;
            margin-bottom: 0.75rem;
        }
        .clickable-image-card {
            display: block;
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.08);
            background: rgba(7, 15, 31, 0.52);
            text-decoration: none;
            transition: transform 0.16s ease, border-color 0.16s ease;
        }
        .clickable-image-card:hover {
            transform: translateY(-1px);
            border-color: rgba(140, 124, 255, 0.55);
        }
        .clickable-image-card img {
            width: 100%;
            display: block;
        }
        .clickable-image-tip {
            color: rgba(214, 219, 255, 0.62);
            font-size: 0.76rem;
            margin: -0.15rem 0 0.65rem;
        }
        [data-testid="stFileUploader"] {
            margin: 0 !important;
            padding: 0 !important;
        }
        [data-testid="stFileUploader"] > section {
            margin: 0 !important;
            padding: 0 !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            background: rgba(10, 19, 38, 0.92) !important;
            color: rgba(243, 246, 255, 0.92) !important;
            border: 1px solid rgba(255, 255, 255, 0.10) !important;
            border-radius: 12px !important;
            min-height: 34px !important;
            height: 34px !important;
            padding: 0 !important;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            width: 100% !important;
            position: relative !important;
        }
        [data-testid="stFileUploaderDropzone"]:hover {
            background: rgba(18, 30, 56, 0.96) !important;
            border-color: rgba(138, 158, 255, 0.24) !important;
            color: #ffffff !important;
        }
        [data-testid="stFileUploaderDropzoneInstructions"] {
            display: none !important;
        }
        [data-testid="stFileUploaderDropzone"]::after {
            content: "选择图片";
            font-size: 0.76rem;
            font-weight: 600;
            color: inherit;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 100%;
            position: absolute;
            left: 0;
            top: 0;
        }
        div[data-testid="stFileUploader"]:has(input[aria-label="继续上传"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "继续上传";
        }
        div[data-testid="stFileUploader"]:has(input[aria-label="重新上传"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "重新上传";
        }
        div[data-testid="stFileUploader"]:has(input[aria-label="上传图片"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "上传图片";
        }
        div[data-testid="stFileUploader"]:has(input[aria-label="上传参考图"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "上传参考图";
        }
        [data-testid="stFileUploaderFile"] {
            display: none !important;
        }
        [data-testid="stFileUploaderDropzone"] button {
            display: none !important;
        }
        .image-placeholder {
            color: rgba(214, 219, 255, 0.68);
            font-size: 0.9rem;
            line-height: 1.8;
            text-align: center;
            padding: 4.5rem 1rem;
        }
        .stTextArea textarea, .stTextInput input {
            background: rgba(7, 15, 31, 0.92) !important;
            color: #f4f6ff !important;
            border-radius: 14px !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
        }
        div[data-baseweb="select"] > div {
            background: rgba(7, 15, 31, 0.92) !important;
            color: #f4f6ff !important;
            border-radius: 14px !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
        }
        .stForm {
            border: none !important;
            background: transparent !important;
            padding: 0 !important;
        }
        .stButton {
            margin: 0 !important;
            padding: 0 !important;
        }
        .stButton > button[kind="primary"], .stFormSubmitButton > button {
            background: linear-gradient(135deg, #7a5cff, #5d44f6);
            color: #ffffff;
            border: none;
            border-radius: 12px;
            box-shadow: 0 12px 30px rgba(93, 68, 246, 0.25);
        }
        .stButton > button[kind="secondary"] {
            background: rgba(10, 19, 38, 0.92) !important;
            color: rgba(243, 246, 255, 0.92) !important;
            border: 1px solid rgba(255, 255, 255, 0.10) !important;
            border-radius: 12px;
            box-shadow: none;
            min-height: 34px;
            padding: 0.18rem 0.55rem;
        }
        .stButton > button[kind="secondary"]:hover {
            background: rgba(18, 30, 56, 0.96) !important;
            border-color: rgba(138, 158, 255, 0.24) !important;
            color: #ffffff !important;
        }
        .stButton > button[kind="secondary"] p {
            color: rgba(243, 246, 255, 0.92) !important;
            font-size: 0.76rem !important;
            font-weight: 600 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root) {
            position: relative;
            margin-bottom: 0.35rem;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root) > div[data-testid="element-container"]:has(.delete-marker) {
            display: none !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root) > div[data-testid="element-container"]:has(.delete-marker) + div[data-testid="element-container"] {
            position: relative;
            z-index: 20;
            width: 100% !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
            display: flex;
            justify-content: flex-end;
            top: 6px;
            padding-right: 6px !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root) > div[data-testid="element-container"]:has(.delete-marker) + div[data-testid="element-container"] .stButton > button {
            min-height: 24px !important;
            height: 24px !important;
            width: 24px !important;
            padding: 0 !important;
            border-radius: 50% !important;
            background: rgba(255, 77, 90, 0.96) !important;
            border: 1px solid rgba(255, 255, 255, 0.92) !important;
            color: #ffffff !important;
            display: flex;
            align-items: center;
            justify-content: center;
            line-height: 1;
            box-shadow: 0 6px 14px rgba(0, 0, 0, 0.34) !important;
            opacity: 1 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root) > div[data-testid="element-container"]:has(.delete-marker) + div[data-testid="element-container"] .stButton > button:hover {
            background: rgba(255, 36, 74, 1) !important;
            border-color: rgba(255, 255, 255, 1) !important;
            color: #ffffff !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root) > div[data-testid="element-container"]:has(.delete-marker) + div[data-testid="element-container"] .stButton p {
            color: inherit !important;
            font-size: 15px !important;
            font-weight: 800 !important;
            line-height: 1 !important;
            margin: 0 !important;
            padding: 0 !important;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .stButton > button[kind="secondary"].small-icon-button,
        .stButton > button[kind="secondary"]:has(p:only-child) {
            box-shadow: none;
        }
        [data-testid="stPopoverButton"] > button {
            background: rgba(255, 255, 255, 0.06);
            color: #f8f9ff;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(8, 15, 31, 0.55);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 18px;
        }
        .result-block-title {
            color: #ffffff;
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 0.8rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_prompt(feature: dict[str, Any], custom_prompt: str, aspect_ratio: str, extra_notes: str) -> str:
    sections = [
        f"当前执行功能：{feature['name']}",
        feature.get("default_prompt", ""),
    ]
    if feature.get("key") == "amazon_a_plus":
        size_text = str(feature.get("target_size_text", "")).strip()
        if size_text:
            sections.append(f"最终输出尺寸必须严格等于 {size_text}px。")
    elif feature.get("output_mode") == "image":
        sections.append(
            f"最终输出必须保持原始比例不变，并且宽度和高度都不小于 {get_feature_min_output_edge(feature)}px。"
        )
    positive_prompt = str(feature.get("positive_prompt", "")).strip()
    negative_prompt = str(feature.get("negative_prompt", "")).strip()
    if positive_prompt:
        sections.append(f"正面提示词：{positive_prompt}")
    if negative_prompt:
        sections.append(f"负面提示词：{negative_prompt}")
    if aspect_ratio != "自动":
        sections.append(f"目标画幅比例：{aspect_ratio}")
    if custom_prompt.strip():
        sections.append(f"补充要求：{custom_prompt.strip()}")
    if extra_notes.strip():
        sections.append(f"附加说明：{extra_notes.strip()}")
    sections.append("请输出适合商业修图/电商展示的高质量结果。")
    return "\n\n".join(part for part in sections if part)


def _compact_prompt_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def build_outpaint_extra_notes(
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    feather_strength: int,
) -> str:
    active_directions = [
        f"expand upward by {top_px}px" if top_px > 0 else "",
        f"expand downward by {bottom_px}px" if bottom_px > 0 else "",
        f"expand left by {left_px}px" if left_px > 0 else "",
        f"expand right by {right_px}px" if right_px > 0 else "",
    ]
    active_directions = [item for item in active_directions if item]
    direction_text = ", ".join(active_directions)
    return (
        "This is a directional outpainting task. "
        f"Follow these canvas expansion instructions exactly: {direction_text}. "
        "The input image contains transparent blank margins created for the requested expansion; these transparent margins are missing canvas that must be newly painted. "
        "Do not interpret transparent margins as black, gray, or colored background. "
        "Do not generate content on any side where no expansion value is specified. "
        "The output must be a single coherent, continuous image. Do not create a collage, split-frame, multi-panel layout, or duplicated scenes. "
        "If the expanded area involves the head, face, chin, forehead, hairline, ears, neck, or facial contour, the completion must remain a realistic natural human face and anatomically correct human structure. "
        "It is strictly forbidden to turn the face into a non-human face, mask-like face, cartoon face, fake face, distorted facial features, misaligned features, duplicated features, blurred face, or abstract texture. "
        "The completed face must remain the same person as in the original image, with continuous consistency in facial proportions, face shape, skin texture, skin tone, makeup, hairstyle, expression, apparent age, and real photographic quality. "
        "All existing subject content, details, composition, and sharpness in the original image must remain completely unchanged, and only the newly expanded canvas area may be completed. "
        "The transition must be natural through coherent content matching, not through blurring or smudging. "
        "Never stretch, smear, mirror, tile, clone, or repeat the border pixels of the original image. "
        "The outpainted result must connect naturally and avoid seams, breaks, repeated textures, stretched deformation, or obvious AI-generated artifacts."
    )


def build_jimeng_feature_prompt(
    feature: dict[str, Any],
    custom_prompt: str,
    aspect_ratio: str,
    extra_notes: str,
    base_instruction: str = "",
) -> str:
    parts: list[str] = [
        _compact_prompt_text(base_instruction),
        _compact_prompt_text(feature.get("default_prompt", "")),
        f"正面提示词：{_compact_prompt_text(feature.get('positive_prompt', ''))}"
        if str(feature.get("positive_prompt", "")).strip()
        else "",
        f"负面提示词：{_compact_prompt_text(feature.get('negative_prompt', ''))}"
        if str(feature.get("negative_prompt", "")).strip()
        else "",
        f"目标画幅比例：{aspect_ratio}" if aspect_ratio != "自动" else "",
        f"补充要求：{_compact_prompt_text(custom_prompt)}" if str(custom_prompt or "").strip() else "",
        f"附加说明：{_compact_prompt_text(extra_notes)}" if str(extra_notes or "").strip() else "",
        "请输出适合商业修图或电商展示的高质量结果，仅输出最终图片。",
    ]
    prompt = "；".join(part for part in parts if part)
    prompt = _compact_prompt_text(prompt)
    if len(prompt) <= JIMENG_PROMPT_MAX_CHARS:
        return prompt
    return prompt[:JIMENG_PROMPT_MAX_CHARS].rstrip("；,，。 ") + "。"


def build_jimeng_prompt(feature: dict[str, Any], custom_prompt: str, aspect_ratio: str, extra_notes: str) -> str:
    feature_key = str(feature.get("key") or "").strip()
    if feature_key == "hd_batch":
        return build_jimeng_feature_prompt(
            feature,
            custom_prompt,
            aspect_ratio,
            extra_notes,
            base_instruction="",
        )
    return build_jimeng_feature_prompt(feature, custom_prompt, aspect_ratio, extra_notes)


def build_jimeng_request_payload(
    prompt: str,
    aspect_ratio: str,
    image_urls: list[str] | None = None,
    feature_key: str = "",
) -> dict[str, Any]:
    normalized_feature_key = str(feature_key or "").strip()
    payload: dict[str, Any] = {
        "req_key": JIMENG_REQ_KEY,
        "prompt": str(prompt or "").strip(),
        "force_single": True,
        "size": JIMENG_HD_OUTPUT_AREA if normalized_feature_key == "hd_batch" else 2048 * 2048,
    }
    size_map = (
        {
            "1:1": (2048, 2048),
            "4:3": (2304, 1728),
            "3:2": (2496, 1664),
            "16:9": (2560, 1440),
            "21:9": (3024, 1296),
            "9:16": (1440, 2560),
        }
        if normalized_feature_key == "hd_batch"
        else {
            "1:1": (2048, 2048),
            "4:3": (2304, 1728),
            "3:2": (2496, 1664),
            "16:9": (2560, 1440),
            "21:9": (3024, 1296),
            "9:16": (1440, 2560),
        }
    )
    selected_size = size_map.get(str(aspect_ratio or "").strip())
    if selected_size:
        payload["width"], payload["height"] = selected_size
    cleaned_image_urls = [str(item).strip() for item in (image_urls or []) if str(item).strip()]
    if cleaned_image_urls:
        payload["image_urls"] = cleaned_image_urls[:JIMENG_MAX_INPUT_IMAGES]
        payload["scale"] = (
            JIMENG_HD_IMAGE_EDIT_SCALE if normalized_feature_key == "hd_batch" else JIMENG_IMAGE_EDIT_SCALE
        )
    return payload


def jimeng_signed_post(action: str, body: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    body_text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    last_error: RuntimeError | None = None
    for attempt in range(JIMENG_CONCURRENT_LIMIT_RETRY_COUNT + 1):
        headers = build_jimeng_auth_headers(action, body_text)
        try:
            response = requests.post(
                JIMENG_API_ENDPOINT,
                params={"Action": action, "Version": JIMENG_API_VERSION},
                data=body_text.encode("utf-8"),
                headers=headers,
                **get_external_request_kwargs(timeout=timeout, use_proxy=False),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Agent 请求失败：无法连接到火山引擎视觉服务。{exc}") from exc
        try:
            data = response.json()
        except Exception as exc:
            raise RuntimeError(f"Agent 响应解析失败：{response.text[:300]}") from exc
        if response.status_code < 400:
            return data
        error_message = str(data.get("message") or response.text).strip()
        if (
            response.status_code in {400, 403, 429}
            and is_jimeng_concurrent_limit_error(error_message)
            and attempt < JIMENG_CONCURRENT_LIMIT_RETRY_COUNT
        ):
            retry_delay = JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS[
                min(attempt, len(JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS) - 1)
            ]
            time.sleep(retry_delay)
            continue
        last_error = RuntimeError(f"Agent 请求失败：{error_message}")
        break
    if last_error is not None:
        raise last_error
    raise RuntimeError("Agent 请求失败：请求未成功，请稍后重试。")


def extract_jimeng_result_images(payload: dict[str, Any]) -> dict[str, Any]:
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


def poll_jimeng_task_result(req_key: str, task_id: str, timeout: int = 120) -> dict[str, Any]:
    deadline = time.time() + JIMENG_RESULT_TIMEOUT_SECONDS
    last_status = "in_queue"
    while time.time() < deadline:
        result_body = {
            "req_key": req_key,
            "task_id": task_id,
            "req_json": json.dumps({"return_url": True}, ensure_ascii=False, separators=(",", ":")),
        }
        result_data = jimeng_signed_post(JIMENG_GET_RESULT_ACTION, result_body, timeout=timeout)
        code = int(result_data.get("code") or 0)
        if code == 50500:
            last_status = "transient_internal_error"
            time.sleep(JIMENG_RESULT_POLL_INTERVAL_SECONDS)
            continue
        if code != 10000:
            raise RuntimeError(f"Agent 查询结果失败：{result_data.get('message') or result_data}")
        payload = result_data.get("data") or {}
        status = str(payload.get("status") or "").strip()
        last_status = status or last_status
        if status == "done":
            return extract_jimeng_result_images(payload)
        if status in {"not_found", "expired"}:
            raise RuntimeError(f"Agent 查询结果失败：任务状态为 {status}。")
        time.sleep(JIMENG_RESULT_POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"Agent 处理超时：任务长时间处于 {last_status} 状态。")


def call_jimeng_hd_upscale(uploaded_files: list[Any] | None = None) -> dict[str, Any]:
    normalized_files = list(uploaded_files or [])
    if not normalized_files:
        raise RuntimeError("Agent 高清失败：请先上传 1 张原图。")
    submit_body = {
        "req_key": JIMENG_HD_UPSCALE_REQ_KEY,
        "binary_data_base64": [prepare_jimeng_hd_input_base64(normalized_files[0])],
        "resolution": JIMENG_HD_API_RESOLUTION,
        "scale": JIMENG_HD_API_SCALE,
    }
    submit_data = jimeng_signed_post(JIMENG_SUBMIT_ACTION, submit_body, timeout=120)
    if int(submit_data.get("code") or 0) != 10000:
        raise RuntimeError(f"Agent 高清提交失败：{submit_data.get('message') or submit_data}")
    task_id = str(((submit_data.get("data") or {}).get("task_id")) or "").strip()
    if not task_id:
        raise RuntimeError("Agent 高清提交失败：返回结果里没有 task_id。")
    return poll_jimeng_task_result(JIMENG_HD_UPSCALE_REQ_KEY, task_id, timeout=120)


def call_openrouter_hd_then_upscale(
    model: str,
    prompt: str,
    aspect_ratio: str,
    uploaded_files: list[Any] | None = None,
) -> dict[str, Any]:
    portrait_inputs = get_portrait_hd_inputs(uploaded_files)
    base_result = call_openrouter(
        model=model,
        prompt=build_portrait_hd_prompt(prompt),
        uploaded_files=portrait_inputs,
        output_mode="image",
        aspect_ratio=aspect_ratio,
        image_size=PORTRAIT_HD_DEFAULT_IMAGE_SIZE,
    )
    original_images = list(base_result.get("images") or [])
    if not original_images:
        return base_result
    upscaled_images: list[str] = []
    fallback_messages: list[str] = []
    for index, image_url in enumerate(original_images, start=1):
        try:
            hd_input = build_uploaded_input_from_image_url_raw(image_url, base_name=f"openrouter_hd_stage_{index}.png")
            hd_result = call_jimeng_hd_upscale(uploaded_files=[hd_input])
            hd_images = list(hd_result.get("images") or [])
            if not hd_images:
                raise RuntimeError("智能超清阶段没有返回可用图片。")
            upscaled_images.append(str(hd_images[0]))
        except Exception as exc:
            upscaled_images.append(str(image_url))
            fallback_messages.append(f"第 {index} 张高清增强失败，已保留模型原图。原因：{exc}")
    result_text_parts = [str(base_result.get("text") or "").strip(), *fallback_messages]
    return {
        "images": upscaled_images,
        "text": "\n\n".join(part for part in result_text_parts if part).strip(),
        "raw": base_result.get("raw"),
        "intermediate_hd_images": original_images,
    }


def call_openrouter_portrait_hd(
    model: str,
    prompt: str,
    aspect_ratio: str,
    uploaded_files: list[Any] | None = None,
) -> dict[str, Any]:
    portrait_inputs = get_portrait_hd_inputs(uploaded_files)
    return call_openrouter(
        model=model,
        prompt=build_portrait_hd_prompt(prompt),
        uploaded_files=portrait_inputs,
        output_mode="image",
        aspect_ratio=aspect_ratio,
        image_size=PORTRAIT_HD_DEFAULT_IMAGE_SIZE,
    )


def call_jimeng_portrait_hd(
    prompt: str,
    aspect_ratio: str,
    uploaded_files: list[Any] | None = None,
    feature_key: str = "hd_batch",
) -> dict[str, Any]:
    portrait_inputs = get_portrait_hd_inputs(uploaded_files)
    return call_jimeng_v40(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        uploaded_files=portrait_inputs,
        feature_key=feature_key,
    )


def call_jimeng_v40(
    prompt: str,
    aspect_ratio: str,
    uploaded_files: list[Any] | None = None,
    feature_key: str = "",
) -> dict[str, Any]:
    image_urls = save_uploaded_inputs_for_jimeng(list(uploaded_files or []))
    submit_body = build_jimeng_request_payload(
        prompt,
        aspect_ratio,
        image_urls=image_urls,
        feature_key=feature_key,
    )
    submit_data = jimeng_signed_post(JIMENG_SUBMIT_ACTION, submit_body, timeout=120)
    if int(submit_data.get("code") or 0) != 10000:
        raise RuntimeError(f"Agent 提交任务失败：{submit_data.get('message') or submit_data}")
    task_id = str(((submit_data.get("data") or {}).get("task_id")) or "").strip()
    if not task_id:
        raise RuntimeError("Agent 提交任务失败：返回结果里没有 task_id。")
    return poll_jimeng_task_result(JIMENG_REQ_KEY, task_id, timeout=120)


def extract_response_payload(data: dict[str, Any]) -> dict[str, Any]:
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


def call_openrouter(
    model: str,
    prompt: str,
    uploaded_files: list[Any],
    output_mode: str,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    image_size: str = "",
) -> dict[str, Any]:
    api_key = load_api_key()
    if not api_key:
        raise RuntimeError("未找到 OPENROUTER_API_KEY，请先在环境变量或 config.py 中配置。")

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for uploaded_file in uploaded_files:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": file_to_data_url(uploaded_file)},
            }
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://127.0.0.1:10808",
        "X-Title": "OpenRouter Image Workspace",
    }

    if output_mode == "text":
        modality_candidates = [["text"]]
    elif model.startswith(IMAGE_ONLY_OUTPUT_MODEL_PREFIXES):
        modality_candidates = [["image"], ["image", "text"]]
    else:
        modality_candidates = [["image", "text"], ["image"]]

    normalized_model = str(model or "").strip().lower()
    normalized_aspect_ratio = str(aspect_ratio or "").strip()
    normalized_image_size = str(image_size or "").strip().upper()
    supports_gemini_image_config = normalized_model.startswith("google/gemini-") and "image" in normalized_model
    last_error: Exception | None = None
    for modalities in modality_candidates:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "modalities": modalities,
            "stream": False,
        }
        if output_mode == "image" and supports_gemini_image_config:
            image_config: dict[str, Any] = {}
            if normalized_aspect_ratio in GEMINI_IMAGE_ASPECT_RATIOS:
                image_config["aspect_ratio"] = normalized_aspect_ratio
            if normalized_image_size in GEMINI_IMAGE_SIZES:
                image_config["image_size"] = normalized_image_size
            if image_config:
                payload["image_config"] = image_config
                payload["provider"] = {"require_parameters": True}
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                **get_external_request_kwargs(timeout=240),
            )
        except requests.RequestException as exc:
            last_error = RuntimeError(f"OpenRouter 请求失败：无法连接到 OpenRouter 或请求超时。{exc}")
            continue
        try:
            data = response.json()
        except Exception:
            if response.status_code >= 400:
                last_error = RuntimeError("OpenRouter 响应解析失败：返回了无法解析的内容。")
                continue
            response.raise_for_status()
            raise RuntimeError("OpenRouter 响应解析失败：返回了无法解析的内容。")

        if response.status_code >= 400:
            error_message = (data.get("error") or {}).get("message") or response.text
            last_error = RuntimeError(f"OpenRouter 请求失败：{error_message}")
            continue

        parsed = extract_response_payload(data)
        if output_mode == "image" and not (parsed.get("images") or []):
            last_error = RuntimeError(
                f"OpenRouter 未返回图片：当前模型 `{model}` 没有返回图片结果，已自动尝试兼容方式。"
            )
            continue
        return parsed

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"OpenRouter 请求失败：当前模型 `{model}` 调用失败。")


def decode_data_url(data_url: str) -> tuple[bytes, str] | None:
    if not data_url.startswith("data:"):
        return None
    try:
        meta, encoded = data_url.split(",", 1)
    except ValueError:
        return None
    mime_type = meta.split(":", 1)[1].split(";", 1)[0] or "image/png"
    try:
        if ";base64" in meta:
            return base64.b64decode(encoded), mime_type
        return urllib.parse.unquote_to_bytes(encoded), mime_type
    except Exception:
        return None


def image_bytes_to_data_url(image_bytes: bytes, mime_type: str = "image/png") -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def load_image_bytes_from_url(image_url: str) -> tuple[bytes, str]:
    decoded = decode_data_url(image_url)
    if decoded:
        return decoded
    local_path = Path(image_url)
    if not image_url.startswith(("http://", "https://")) and local_path.exists() and local_path.is_file():
        mime_type = mimetypes.guess_type(local_path.name)[0] or "image/png"
        return local_path.read_bytes(), mime_type
    try:
        normalized_url = str(image_url or "").strip().lower()
        use_proxy = not (
            "volcengine" in normalized_url
            or "tos-cn-" in normalized_url
            or "imagex" in normalized_url
            or ":8502/" in normalized_url
            or "toochuangai.com/jimeng_uploads" in normalized_url
        )
        response = requests.get(image_url, **get_external_request_kwargs(timeout=120, use_proxy=use_proxy))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"图片下载失败：无法下载模型返回的图片地址。{exc}") from exc
    mime_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip() or "image/png"
    return response.content, mime_type


def upscale_image_to_min_edge(image_url: str, min_edge: int, enhance_detail: bool = False) -> str:
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = image.convert("RGB")
            width, height = converted.size
            if width <= 0 or height <= 0:
                raise RuntimeError("返回的图片尺寸无效。")
            adaptive_min_edge = max(int(min_edge or 0), MIN_OUTPUT_EDGE)
            scale = max(adaptive_min_edge / width, adaptive_min_edge / height, 1.0)
            if scale > 1.001:
                target_width = max(math.ceil(width * scale), adaptive_min_edge)
                target_height = max(math.ceil(height * scale), adaptive_min_edge)
                resized = converted.copy()
                current_width, current_height = width, height
                while current_width < target_width or current_height < target_height:
                    next_width = min(target_width, max(math.ceil(current_width * 1.35), current_width + 1))
                    next_height = min(target_height, max(math.ceil(current_height * 1.35), current_height + 1))
                    resized = resized.resize((next_width, next_height), Image.Resampling.LANCZOS)
                    current_width, current_height = next_width, next_height
                    if enhance_detail and (current_width < target_width or current_height < target_height):
                        resized = resized.filter(ImageFilter.UnsharpMask(radius=0.7, percent=78, threshold=2))
            else:
                resized = converted.copy()
            if enhance_detail:
                # Preserve zoomed detail while keeping skin texture natural and less harsh.
                resized = resized.filter(ImageFilter.DETAIL)
                resized = ImageEnhance.Contrast(resized).enhance(1.05)
                resized = resized.filter(ImageFilter.UnsharpMask(radius=1.2, percent=172, threshold=3))
                resized = resized.filter(ImageFilter.UnsharpMask(radius=0.55, percent=96, threshold=2))
                resized = ImageEnhance.Sharpness(resized).enhance(1.22)
            output = io.BytesIO()
            resized.save(output, format="PNG")
        return image_bytes_to_data_url(output.getvalue(), "image/png")
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc).startswith("图片下载失败："):
            raise
        raise RuntimeError(f"本地处理失败：返回图片已收到，但在本地放大处理时出错。{exc}") from exc


def resize_image_to_exact_size(image_url: str, target_width: int, target_height: int) -> str:
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = image.convert("RGB")
            resized = converted.resize((target_width, target_height), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            resized.save(output, format="PNG")
        return image_bytes_to_data_url(output.getvalue(), "image/png")
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc).startswith("图片下载失败："):
            raise
        raise RuntimeError(f"本地处理失败：返回图片已收到，但在尺寸处理时出错。{exc}") from exc


def parse_size_text(size_text: str) -> tuple[int, int] | None:
    normalized = size_text.strip().lower().replace("x", "*").replace("×", "*")
    match = re.fullmatch(r"(\d{2,5})\*(\d{2,5})", normalized)
    if not match:
        return None
    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        return None
    return width, height


def uploaded_input_to_data_url(uploaded_input: Any) -> str:
    image_bytes = get_uploaded_file_bytes(uploaded_input)
    mime_type = ""
    if isinstance(uploaded_input, Path):
        file_name = uploaded_input.name
        mime_type = mimetypes.guess_type(file_name)[0] or ""
    elif isinstance(uploaded_input, dict):
        mime_type = str(uploaded_input.get("type") or "").strip()
        file_name = str(uploaded_input.get("name") or "").strip()
    else:
        mime_type = str(getattr(uploaded_input, "type", "") or "").strip()
        file_name = str(getattr(uploaded_input, "name", "") or "").strip()
    if not mime_type:
        mime_type = mimetypes.guess_type(file_name)[0] or "image/png"
    preview_item = build_gallery_preview_data_url(image_bytes, mime_type)
    if preview_item is not None:
        return preview_item[0]
    return image_bytes_to_data_url(image_bytes, mime_type)


def render_upload_delete_button(widget_key: str, item_index: int, button_key: str) -> None:
    st.markdown('<div class="delete-marker" style="display:none;"></div>', unsafe_allow_html=True)
    if st.button("×", key=button_key, help="删除当前图片", use_container_width=False, type="secondary"):
        remove_upload_cache_item(widget_key, item_index)
        reset_upload_widget(widget_key)
        st.rerun()


def render_uploaded_preview_card(uploaded_input: Any, widget_key: str, item_index: int, component_key: str) -> None:
    preview_container = st.container()
    with preview_container:
        st.markdown('<div class="upload-preview-root" style="display:none;"></div>', unsafe_allow_html=True)
        render_upload_delete_button(widget_key, item_index, f"delete_upload_native_{widget_key}_{item_index}")
        render_zoomable_image_gallery(
            [uploaded_input_to_data_url(uploaded_input)],
            columns=1,
            thumb_height=150,
            component_key=component_key,
            fit_mode="contain",
            max_width_percent=100,
        )


def render_uploaded_previews(uploaded_file: Any | None, widget_key: str) -> None:
    if uploaded_file is not None:
        preview_col, _ = st.columns([1, 3])
        with preview_col:
            render_uploaded_preview_card(
                uploaded_file,
                widget_key=widget_key,
                item_index=0,
                component_key=f"upload_preview_{widget_key}_0",
            )


def render_uploaded_gallery(files: list[Any], empty_text: str, widget_key: str, slot_count: int = 5) -> None:
    columns_per_row = min(max(slot_count, 1), 5)
    if not files:
        st.markdown(f'<div class="slot-helper">{empty_text}</div>', unsafe_allow_html=True)
        return
    for row_start in range(0, len(files), columns_per_row):
        columns = st.columns(columns_per_row)
        for column_index, column in enumerate(columns):
            item_index = row_start + column_index
            with column:
                if item_index < len(files):
                    render_uploaded_preview_card(
                        files[item_index],
                        widget_key=widget_key,
                        item_index=item_index,
                        component_key=f"upload_preview_{widget_key}_{item_index}",
                    )
    st.markdown(f'<div class="slot-helper">{empty_text}</div>', unsafe_allow_html=True)


def image_source_to_data_url(image_source: str) -> str | None:
    if image_source.startswith("data:"):
        return image_source
    try:
        image_bytes, mime_type = load_image_bytes_from_url(image_source)
    except Exception:
        return None
    return image_bytes_to_data_url(image_bytes, mime_type or "image/png")


def build_gallery_preview_data_url(image_bytes: bytes, mime_type: str) -> tuple[str, int, int] | None:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = image.convert("RGB")
            width, height = converted.size
            preview = converted.copy()
            preview.thumbnail((GALLERY_PREVIEW_MAX_EDGE, GALLERY_PREVIEW_MAX_EDGE), Image.Resampling.LANCZOS)
            quality_candidates = (85, 78, 72, 66, 60, 54)
            output_bytes = b""
            for quality in quality_candidates:
                output = io.BytesIO()
                preview.save(output, format="JPEG", quality=quality, optimize=True)
                output_bytes = output.getvalue()
                if len(output_bytes) <= GALLERY_PREVIEW_TARGET_BYTES or quality == quality_candidates[-1]:
                    break
    except Exception:
        return None
    return image_bytes_to_data_url(output_bytes, "image/jpeg"), width, height


def build_gallery_item(
    image_source: str,
    compress_preview: bool = True,
    include_full_src: bool = False,
    full_image_source: str = "",
    direct_src: bool = False,
    embed_full_src: bool = False,
) -> dict[str, Any] | None:
    normalized_image_source = str(image_source or "").strip()
    normalized_full_src = str(full_image_source or "").strip()
    if direct_src:
        if not normalized_image_source:
            return None
        item: dict[str, Any] = {
            "src": normalized_image_source,
            "width": 1,
            "height": 1,
        }
        if include_full_src:
            item["full_src"] = normalized_full_src or normalized_image_source
        return item
    original_full_src = ""
    decoded_data_url = decode_data_url(normalized_image_source)
    if decoded_data_url is not None:
        image_bytes, mime_type = decoded_data_url
    else:
        original_full_src = normalized_image_source
        try:
            image_bytes, mime_type = load_image_bytes_from_url(normalized_image_source)
        except Exception:
            fallback_item: dict[str, Any] = {
                "src": normalized_image_source,
                "width": 1,
                "height": 1,
            }
            if include_full_src and (normalized_full_src or original_full_src):
                fallback_item["full_src"] = normalized_full_src
                if not fallback_item["full_src"]:
                    fallback_item["full_src"] = original_full_src
            return fallback_item
    if compress_preview:
        preview_item = build_gallery_preview_data_url(image_bytes, mime_type or "image/png")
        if preview_item is None:
            return None
        preview_src, width, height = preview_item
    else:
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                width, height = image.size
        except Exception:
            width, height = 0, 0
        preview_src = image_bytes_to_data_url(image_bytes, mime_type or "image/png")
    item = {
        "src": preview_src,
        "width": width,
        "height": height,
    }
    if include_full_src:
        normalized_full_src = str(full_image_source or "").strip()
        if normalized_full_src:
            if embed_full_src and not normalized_full_src.startswith("data:"):
                try:
                    full_image_bytes, full_mime_type = load_image_bytes_from_url(normalized_full_src)
                    item["full_src"] = image_bytes_to_data_url(full_image_bytes, full_mime_type or "image/png")
                except Exception:
                    item["full_src"] = normalized_full_src
            else:
                item["full_src"] = normalized_full_src
        elif original_full_src:
            item["full_src"] = original_full_src
        elif not compress_preview:
            item["full_src"] = preview_src
    return item


def render_zoomable_image_gallery(
    images: list[str],
    columns: int,
    thumb_height: int | None,
    component_key: str,
    fit_mode: str = "contain",
    max_width_percent: int = 100,
    context_delete_token: str | None = None,
    compress_preview: bool = True,
    include_full_src: bool = False,
    full_images: list[str] | None = None,
    direct_src: bool = False,
    embed_full_src: bool = False,
) -> None:
    items: list[dict[str, Any]] = []
    normalized_full_images = list(full_images or [])
    for index, image_source in enumerate(images):
        item = build_gallery_item(
            image_source,
            compress_preview=compress_preview,
            include_full_src=include_full_src,
            full_image_source=(
                normalized_full_images[index]
                if index < len(normalized_full_images)
                else ""
            ),
            direct_src=direct_src,
            embed_full_src=embed_full_src,
        )
        if item:
            items.append(item)
    if not items:
        return
    gap = 12
    row_count = max(math.ceil(len(items) / max(columns, 1)), 1)
    estimated_thumb_height = thumb_height or 120
    base_height = row_count * estimated_thumb_height + max(row_count - 1, 0) * gap
    if thumb_height is None and columns == 1:
        assumed_column_width = max(math.ceil(520 * max_width_percent / 100), 80)
        natural_heights = [
            math.ceil(assumed_column_width * item["height"] / item["width"])
            for item in items
            if item.get("width", 0) > 0 and item.get("height", 0) > 0
        ]
        if natural_heights:
            base_height = max(base_height, min(max(natural_heights) + 24, 1200))
    thumb_style = f"height: {thumb_height}px;" if thumb_height else "height: auto;"
    payload = json.dumps(items, ensure_ascii=False)
    delete_token = json.dumps(str(context_delete_token or ""))
    html_content = f"""
    <div id="{component_key}" class="zoom-gallery-root" style="max-width: {max_width_percent}%; margin: 0 auto;">
      <div class="zoom-gallery-grid" style="grid-template-columns: repeat({columns}, minmax(0, 1fr)); gap: {gap}px;">
      </div>
    </div>
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        background: transparent;
      }}
      .zoom-gallery-grid {{
        display: grid;
      }}
      .zoom-thumb-wrap {{
        position: relative;
        width: 100%;
      }}
      .zoom-thumb {{
        width: 100%;
        {thumb_style}
        object-fit: {fit_mode};
        display: block;
        cursor: zoom-in;
        background: transparent;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.10);
        box-sizing: border-box;
      }}
      .zoom-thumb-delete {{
        appearance: none;
        position: absolute;
        top: 6px;
        right: 6px;
        z-index: 3;
        width: 24px;
        height: 24px;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.92);
        background: rgba(255, 77, 90, 0.96);
        color: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 15px;
        font-weight: 800;
        line-height: 1;
        cursor: pointer;
        user-select: none;
        backdrop-filter: blur(3px);
        box-shadow: 0 6px 14px rgba(0, 0, 0, 0.34);
        opacity: 1;
      }}
      .zoom-thumb-delete:hover {{
        background: rgba(255, 36, 74, 1);
        border-color: rgba(255, 255, 255, 1);
        color: #ffffff;
      }}
    </style>
    <script>
      const images_{component_key} = {payload};
      const grid_{component_key} = document.querySelector("#{component_key} .zoom-gallery-grid");
      const hostWindow_{component_key} = (() => {{
        try {{
          return window.parent;
        }} catch (e) {{
          return window;
        }}
      }})();
      const hostDoc_{component_key} = (() => {{
        try {{
          return window.parent.document;
        }} catch (e) {{
          return document;
        }}
      }})();

      function setFrameHeight_{component_key}(value) {{
        try {{
          if (window.frameElement) {{
            window.frameElement.style.height = value + "px";
          }}
        }} catch (e) {{}}
      }}

      function updateFrameHeight_{component_key}() {{
        const root = document.getElementById("{component_key}");
        if (!root) return;
        const nextHeight = Math.max(root.scrollHeight + 12, {base_height});
        setFrameHeight_{component_key}(nextHeight);
      }}

      function normalizeViewerSrc_{component_key}(src) {{
        const raw = String(src || "").trim();
        if (!raw || raw.startsWith("data:")) {{
          return raw;
        }}
        try {{
          const parsed = new URL(raw, hostWindow_{component_key}.location.href);
          const isStaticImageRoute =
            parsed.pathname.startsWith("{HISTORY_STATIC_ROUTE_PREFIX}/") ||
            parsed.pathname.startsWith("{JIMENG_UPLOAD_ROUTE_PREFIX}/");
          if (!isStaticImageRoute) {{
            return parsed.toString();
          }}
          const currentProtocol = hostWindow_{component_key}.location.protocol || parsed.protocol;
          const currentHostname = hostWindow_{component_key}.location.hostname || parsed.hostname;
          const currentPort = parsed.port ? ":" + parsed.port : "";
          return `${{currentProtocol}}//${{currentHostname}}${{currentPort}}${{parsed.pathname}}${{parsed.search}}${{parsed.hash}}`;
        }} catch (e) {{
          return raw;
        }}
      }}

      function ensureOverlay_{component_key}() {{
        if (!hostDoc_{component_key}.getElementById("lashforge-fullscreen-style")) {{
          const style = hostDoc_{component_key}.createElement("style");
          style.id = "lashforge-fullscreen-style";
          style.textContent = `
            #lashforge-fullscreen-viewer {{
              position: fixed;
              inset: 0;
              z-index: 999999;
              background: rgba(3, 8, 22, 0.96);
              display: none;
              align-items: center;
              justify-content: center;
              overflow: hidden;
            }}
            #lashforge-fullscreen-viewer.active {{
              display: flex;
            }}
            #lashforge-fullscreen-viewer img {{
              max-width: 96vw;
              max-height: 96vh;
              object-fit: contain;
              transform-origin: center center;
              transition: transform 0.08s linear;
              user-select: none;
              -webkit-user-drag: none;
              cursor: grab;
            }}
            #lashforge-fullscreen-viewer img.dragging {{
              cursor: grabbing;
            }}
          `;
          hostDoc_{component_key}.head.appendChild(style);
        }}
        if (!hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer")) {{
          const overlay = hostDoc_{component_key}.createElement("div");
          overlay.id = "lashforge-fullscreen-viewer";
          overlay.innerHTML = '<img id="lashforge-fullscreen-image" src="" alt="preview" />';
          hostDoc_{component_key}.body.appendChild(overlay);

          const state = {{
            scale: 1,
            offsetX: 0,
            offsetY: 0,
            dragging: false,
            dragStartX: 0,
            dragStartY: 0,
            dragOriginX: 0,
            dragOriginY: 0,
          }};
          hostWindow_{component_key}.__lashforgeFullscreenState = state;

          const image = overlay.querySelector("img");
          const applyTransform = () => {{
            image.style.transform =
              "translate(" + state.offsetX + "px, " + state.offsetY + "px) scale(" + state.scale + ")";
          }};
          const resetTransform = () => {{
            state.scale = 1;
            state.offsetX = 0;
            state.offsetY = 0;
            state.dragging = false;
            image.classList.remove("dragging");
            applyTransform();
          }};

          overlay.addEventListener("click", (event) => {{
            if (event.target === overlay) {{
              overlay.classList.remove("active");
              resetTransform();
            }}
          }});

          overlay.addEventListener("wheel", (event) => {{
            if (!overlay.classList.contains("active")) return;
            event.preventDefault();
            if (event.deltaY < 0) {{
              state.scale = Math.min(state.scale + 0.16, 6);
            }} else {{
              state.scale = Math.max(state.scale - 0.16, 0.35);
            }}
            applyTransform();
          }}, {{ passive: false }});

          image.addEventListener("pointerdown", (event) => {{
            if (!overlay.classList.contains("active")) return;
            event.preventDefault();
            state.dragging = true;
            state.dragStartX = event.clientX;
            state.dragStartY = event.clientY;
            state.dragOriginX = state.offsetX;
            state.dragOriginY = state.offsetY;
            image.classList.add("dragging");
            if (image.setPointerCapture) {{
              image.setPointerCapture(event.pointerId);
            }}
          }});

          image.addEventListener("pointermove", (event) => {{
            if (!state.dragging) return;
            event.preventDefault();
            state.offsetX = state.dragOriginX + (event.clientX - state.dragStartX);
            state.offsetY = state.dragOriginY + (event.clientY - state.dragStartY);
            applyTransform();
          }});

          const stopDragging = (event) => {{
            if (!state.dragging) return;
            state.dragging = false;
            image.classList.remove("dragging");
            if (event && image.releasePointerCapture) {{
              try {{
                image.releasePointerCapture(event.pointerId);
              }} catch (e) {{}}
            }}
          }};

          image.addEventListener("pointerup", stopDragging);
          image.addEventListener("pointercancel", stopDragging);
          image.addEventListener("lostpointercapture", () => {{
            state.dragging = false;
            image.classList.remove("dragging");
          }});

          hostDoc_{component_key}.addEventListener("keydown", (event) => {{
            if (event.key === "Escape") {{
              overlay.classList.remove("active");
              resetTransform();
            }}
          }});
        }}
      }}

      function openFullscreen_{component_key}(src) {{
        ensureOverlay_{component_key}();
        const overlay = hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer");
        const image = hostDoc_{component_key}.getElementById("lashforge-fullscreen-image");
        const state = hostWindow_{component_key}.__lashforgeFullscreenState;
        image.src = normalizeViewerSrc_{component_key}(src);
        state.scale = 1;
        state.offsetX = 0;
        state.offsetY = 0;
        state.dragging = false;
        image.classList.remove("dragging");
        image.style.transform = "translate(0px, 0px) scale(1)";
        overlay.classList.add("active");
      }}

      function buildDeleteUrl_{component_key}() {{
        const deleteToken = {delete_token};
        if (!deleteToken) return "";
        const currentUrl = new URL(hostWindow_{component_key}.location.href);
        currentUrl.searchParams.set("{UPLOAD_DELETE_QUERY_KEY}", deleteToken);
        return currentUrl.toString();
      }}

      images_{component_key}.forEach((item, index) => {{
        const wrap = document.createElement("div");
        wrap.className = "zoom-thumb-wrap";

        const img = document.createElement("img");
        img.src = item.src;
        img.className = "zoom-thumb";
        img.onload = () => updateFrameHeight_{component_key}();
        img.onclick = () => openFullscreen_{component_key}(item.full_src || item.src);
        wrap.appendChild(img);

        if ({delete_token}) {{
          const deleteForm = document.createElement("form");
          deleteForm.method = "GET";
          deleteForm.action = buildDeleteUrl_{component_key}();
          deleteForm.target = "_top";
          deleteForm.style.margin = "0";
          deleteForm.style.position = "absolute";
          deleteForm.style.top = "0";
          deleteForm.style.right = "0";
          deleteForm.style.zIndex = "4";

          const deleteButton = document.createElement("button");
          deleteButton.type = "submit";
          deleteButton.className = "zoom-thumb-delete";
          deleteButton.title = "删除当前图片";
          deleteButton.textContent = "×";
          deleteButton.addEventListener("pointerdown", (event) => {{
            event.stopPropagation();
          }});
          deleteButton.addEventListener("click", (event) => {{
            event.stopPropagation();
          }});
          deleteForm.appendChild(deleteButton);
          wrap.appendChild(deleteForm);
        }}

        grid_{component_key}.appendChild(wrap);
      }});

      setTimeout(updateFrameHeight_{component_key}, 0);
    </script>
    """
    st.iframe(
        html_content,
        height=base_height,
        width="stretch",
    )


def render_single_image_uploader(
    label: str,
    key: str,
    help_text: str = "",
) -> Any | None:
    cached_files = load_upload_cache(key, max_files=1)
    active_uploaded = cached_files[0] if cached_files else None

    if active_uploaded is not None:
        render_uploaded_previews(active_uploaded, key)

    action_left, action_right, _ = st.columns([1, 1, 4.4], gap="small")
    with action_left:
        uploaded = st.file_uploader(
            "重新上传" if active_uploaded is not None else "上传图片",
            type=["png", "jpg", "jpeg", "webp"],
            key=get_uploader_widget_key(key),
            help=help_text or None,
            label_visibility="collapsed",
        )
        if uploaded is not None:
            save_upload_cache(key, [uploaded])
            reset_upload_widget(key)
            st.rerun()

    with action_right:
        if st.button("清空上传", key=f"clear_upload_{key}", use_container_width=True, type="secondary"):
            clear_upload_cache(key)
            reset_upload_widget(key)
            st.rerun()

    return active_uploaded


def render_multi_image_uploader(
    label: str,
    key: str,
    help_text: str = "",
    max_files: int = 3,
) -> list[Any]:
    cached_files = load_upload_cache(key, max_files=max_files)
    active_uploaded_files = cached_files

    if active_uploaded_files:
        render_uploaded_gallery(
            active_uploaded_files,
            f"已上传 {len(active_uploaded_files)} / {max_files} 张原图",
            widget_key=key,
            slot_count=max_files,
        )

    action_left, action_right, _ = st.columns([1, 1, 4.4], gap="small")
    with action_left:
        uploaded_files = st.file_uploader(
            "继续上传" if active_uploaded_files else "上传图片",
            type=["png", "jpg", "jpeg", "webp"],
            key=get_uploader_widget_key(key),
            help=help_text or None,
            label_visibility="collapsed",
            accept_multiple_files=True,
        ) or []
        
        if uploaded_files:
            current_cache = load_upload_cache(key, max_files=max_files)
            combined = current_cache + list(uploaded_files)
            combined = combined[:max_files]
            save_upload_cache(key, combined)
            reset_upload_widget(key)
            st.rerun()

    with action_right:
        if st.button("清空上传", key=f"clear_upload_{key}", use_container_width=True, type="secondary"):
            clear_upload_cache(key)
            reset_upload_widget(key)
            st.rerun()

    return active_uploaded_files


def render_reference_slot_uploaders(slot_prefix: str, slot_count: int = 5) -> list[Any]:
    uploaded_files: list[Any] = []
    columns = st.columns(slot_count)
    for index in range(slot_count):
        with columns[index]:
            slot_key = f"{slot_prefix}_{index}"
            cached_files = load_upload_cache(slot_key, max_files=1)
            active_uploaded = cached_files[0] if cached_files else None
            
            if active_uploaded is not None:
                render_uploaded_preview_card(
                    active_uploaded,
                    widget_key=slot_key,
                    item_index=0,
                    component_key=f"upload_preview_{slot_key}_0",
                )
                uploaded_files.append(active_uploaded)
            
            uploaded = st.file_uploader(
                "重新上传" if active_uploaded else "上传参考图",
                type=["png", "jpg", "jpeg", "webp"],
                key=get_uploader_widget_key(slot_key),
                label_visibility="collapsed",
            )
            if uploaded is not None:
                save_upload_cache(slot_key, [uploaded])
                reset_upload_widget(slot_key)
                st.rerun()
                
    return uploaded_files


def render_result_preview(images: list[str], show_title: bool = True) -> None:
    if show_title:
        st.markdown('<div class="result-block-title">结果图预览</div>', unsafe_allow_html=True)
    if not images:
        st.markdown(
            """
            <div class="result-empty">
                <div class="empty-icon">+</div>
                <div class="empty-title">处理完成后在这里查看结果图</div>
                <div class="empty-subtitle">支持多张结果图展示</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        render_zoomable_image_gallery(
            images,
            columns=1,
            thumb_height=None,
            component_key="result_viewer",
            fit_mode="contain",
            max_width_percent=25,
            compress_preview=True,
            include_full_src=True,
        )


def render_result_preview_with_captions(images: list[str], captions: list[str], feature_key: str) -> None:
    if not images:
        render_result_preview(images, show_title=False)
        return
    if len(captions) != len(images):
        render_result_preview(images, show_title=False)
        return
    columns_per_row = min(4, max(len(images), 1))
    for row_start in range(0, len(images), columns_per_row):
        row_images = images[row_start : row_start + columns_per_row]
        row_captions = captions[row_start : row_start + columns_per_row]
        columns = st.columns(columns_per_row)
        for column_index, column in enumerate(columns):
            if column_index >= len(row_images):
                continue
            with column:
                caption = str(row_captions[column_index] or "").strip()
                if caption:
                    st.caption(caption)
                render_zoomable_image_gallery(
                    [row_images[column_index]],
                    columns=1,
                    thumb_height=220,
                    component_key=f"result_viewer_{feature_key}_{row_start + column_index}",
                    fit_mode="contain",
                    max_width_percent=100,
                    compress_preview=True,
                    include_full_src=True,
                )


def flatten_history_items(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record_index, record in enumerate(records):
        display_images = list(record.get("images") or [])
        original_images = list(record.get("original_images") or display_images)
        local_display_images = list(record.get("local_images") or display_images)
        local_original_images = list(record.get("local_original_images") or original_images)
        created_at = str(record.get("created_at") or "").strip()
        model_name = str(record.get("model") or "").strip()
        feature_name = str(record.get("feature_name") or "").strip()
        for image_index, display_image in enumerate(display_images):
            original_image = original_images[image_index] if image_index < len(original_images) else display_image
            render_display_image = (
                local_display_images[image_index] if image_index < len(local_display_images) else display_image
            )
            download_source = (
                local_original_images[image_index] if image_index < len(local_original_images) else original_image
            )
            items.append(
                {
                    "display_image": render_display_image,
                    "original_image": original_image,
                    "download_source": download_source,
                    "created_at": created_at,
                    "model": model_name,
                    "feature_name": feature_name,
                    "download_name": Path(str(download_source or original_image or render_display_image or display_image)).name
                    or f"history_{record_index + 1}_{image_index + 1}.png",
                }
            )
    return items


def get_history_columns_per_row(item_count: int) -> int:
    if item_count <= 2:
        return max(item_count, 1)
    if item_count <= 6:
        return 3
    return 4


def render_history_gallery(
    items: list[dict[str, Any]],
    key_prefix: str,
    columns_per_row: int | None = None,
    thumb_height: int = 230,
) -> None:
    if not items:
        return
    normalized_columns_per_row = max(int(columns_per_row or get_history_columns_per_row(len(items))), 1)
    for row_start in range(0, len(items), normalized_columns_per_row):
        row_items = items[row_start : row_start + normalized_columns_per_row]
        columns = st.columns(normalized_columns_per_row, gap="medium")
        for column_index, column in enumerate(columns):
            if column_index >= len(row_items):
                continue
            item = row_items[column_index]
            with column:
                created_at = str(item.get("created_at") or "")
                model_name = str(item.get("model") or "")
                feature_name = str(item.get("feature_name") or "")
                download_source = str(item.get("download_source") or "").strip()
                fullscreen_href = ""
                if download_source:
                    try:
                        fullscreen_href = build_history_download_public_url(download_source)
                    except Exception:
                        fullscreen_href = str(item.get("original_image") or "").strip()
                if not fullscreen_href:
                    fullscreen_href = str(item.get("original_image") or "").strip()
                meta_parts: list[str] = ['<div class="history-card-meta">']
                if created_at:
                    meta_parts.append(f'<div class="history-card-time">{html.escape(created_at)}</div>')
                if feature_name:
                    meta_parts.append(f'<div class="history-card-model">{html.escape(feature_name)}</div>')
                if model_name:
                    meta_parts.append(f'<div class="history-card-model">{html.escape(model_name)}</div>')
                meta_parts.append("</div>")
                st.markdown("".join(meta_parts), unsafe_allow_html=True)
                render_zoomable_image_gallery(
                    [str(item.get("display_image") or "")],
                    columns=1,
                    thumb_height=thumb_height,
                    component_key=f"{key_prefix}_{row_start}_{column_index}",
                    fit_mode="cover",
                    max_width_percent=100,
                    compress_preview=True,
                    include_full_src=True,
                    full_images=[fullscreen_href or str(item.get("display_image") or "")],
                    embed_full_src=False,
                )
                download_href = ""
                if download_source:
                    try:
                        download_href = build_history_download_public_url(download_source)
                    except Exception:
                        download_href = download_source
                if not download_href:
                    download_href = str(item.get("original_image") or "").strip()
                if download_href:
                    safe_href = html.escape(download_href, quote=True)
                    safe_name = html.escape(str(item.get("download_name") or "history_original.png"), quote=True)
                    st.markdown(
                        (
                            '<a href="{href}" download="{name}" target="_blank" rel="noopener noreferrer" '
                            'data-download-href="{href}" '
                            'onclick="try{{const raw=this.dataset.downloadHref||this.href;'
                            'const parsed=new URL(raw, window.top.location.href);'
                            'const isStatic=parsed.pathname.startsWith(\'{history_prefix}/\')||parsed.pathname.startsWith(\'{upload_prefix}/\');'
                            'if(isStatic){{const hostWindow=window.top||window;'
                            'const currentProtocol=hostWindow.location.protocol||parsed.protocol;'
                            'const currentHostname=hostWindow.location.hostname||parsed.hostname;'
                            'const currentPort=parsed.port?(\':\'+parsed.port):\'\';'
                            'this.href=`${{currentProtocol}}//${{currentHostname}}${{currentPort}}${{parsed.pathname}}${{parsed.search}}${{parsed.hash}}`;}}'
                            'else{{this.href=parsed.toString();}}}}catch(e){{}}" '
                            'style="display:block;width:100%;text-align:center;padding:0.5rem 0.75rem;'
                            'border-radius:999px;background:rgba(5,24,56,0.78);border:1px solid rgba(126,166,255,0.28);'
                            'color:#eef4ff;text-decoration:none;font-size:0.95rem;font-weight:600;">下载原图</a>'
                        ).format(
                            href=safe_href,
                            name=safe_name,
                            history_prefix=HISTORY_STATIC_ROUTE_PREFIX,
                            upload_prefix=JIMENG_UPLOAD_ROUTE_PREFIX,
                        ),
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("点击查看缩略图")
                st.markdown("</div>", unsafe_allow_html=True)


def render_history_toggle(feature: dict[str, Any]) -> None:
    account_name = str(st.session_state.get("auth_username") or "admin")
    cache_key = get_history_cache_key(account_name, feature["key"])
    is_expanded = bool(st.session_state.history_panel_expanded.get(cache_key, False))
    button_label = "展开历史图片" if not is_expanded else "收起历史图片"
    if st.button(button_label, key=f"toggle_history_{feature['key']}"):
        next_state = not is_expanded
        st.session_state.history_panel_expanded[cache_key] = next_state
        if next_state:
            set_history_visible_limit(cache_key, HISTORY_PAGE_SIZE)
            ensure_history_records_loaded(feature["key"], account_name, cache_key, HISTORY_PAGE_SIZE)
        st.rerun()


def render_history_records(feature: dict[str, Any]) -> None:
    account_name = str(st.session_state.get("auth_username") or "admin")
    cache_key = get_history_cache_key(account_name, feature["key"])
    if cache_key not in st.session_state.history_visible_counts:
        set_history_visible_limit(cache_key, HISTORY_PAGE_SIZE)
    visible_limit = get_history_visible_limit(cache_key)
    records = ensure_history_records_loaded(feature["key"], account_name, cache_key, visible_limit)
    st.markdown('<div class="result-block-title">全部历史图片</div>', unsafe_allow_html=True)
    if not records:
        st.caption("暂无历史图片")
        return
    history_items = flatten_history_items(records[:visible_limit])
    st.caption(f"当前先显示前 {len(history_items)} 张，点击放大后可右击或拖动保存原图")
    if history_items:
        render_history_gallery(history_items, key_prefix=f"history_{feature['key']}")
    if len(records) >= visible_limit:
        if st.button("继续加载 20 条", key=f"history_more_{feature['key']}"):
            next_limit = visible_limit + HISTORY_PAGE_SIZE
            set_history_visible_limit(cache_key, next_limit)
            ensure_history_records_loaded(feature["key"], account_name, cache_key, next_limit)
            st.rerun()


def render_side_history_panel(feature: dict[str, Any]) -> None:
    account_name = str(st.session_state.get("auth_username") or "admin")
    cache_key = get_history_cache_key(account_name, feature["key"])
    is_expanded = bool(st.session_state.history_panel_expanded.get(cache_key, False))
    button_label = "展开历史图片" if not is_expanded else "收起历史图片"
    st.markdown('<div class="side-history-shell">', unsafe_allow_html=True)
    st.markdown('<div class="side-history-title">全部历史图片</div>', unsafe_allow_html=True)
    if st.button(button_label, key=f"side_toggle_history_{feature['key']}", use_container_width=True, type="secondary"):
        next_state = not is_expanded
        st.session_state.history_panel_expanded[cache_key] = next_state
        if next_state:
            set_history_visible_limit(cache_key, HISTORY_PAGE_SIZE)
            ensure_history_records_loaded(feature["key"], account_name, cache_key, HISTORY_PAGE_SIZE)
        st.rerun()
    if not st.session_state.history_panel_expanded.get(cache_key, False):
        st.markdown("</div>", unsafe_allow_html=True)
        return
    visible_limit = get_history_visible_limit(cache_key)
    records = ensure_history_records_loaded(feature["key"], account_name, cache_key, visible_limit)
    if not records:
        st.caption("暂无历史图片")
        st.markdown("</div>", unsafe_allow_html=True)
        return
    history_items = flatten_history_items(records[:visible_limit])
    st.caption(f"当前先显示前 {len(history_items)} 张，下面可继续加载更多，点击放大后可右击或拖动保存原图")
    if history_items:
        render_history_gallery(
            history_items,
            key_prefix=f"side_history_{feature['key']}",
            columns_per_row=1,
            thumb_height=220,
        )
    if len(records) >= visible_limit:
        if st.button("继续加载 20 条", key=f"side_history_more_{feature['key']}", use_container_width=True, type="secondary"):
            next_limit = visible_limit + HISTORY_PAGE_SIZE
            set_history_visible_limit(cache_key, next_limit)
            ensure_history_records_loaded(feature["key"], account_name, cache_key, next_limit)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

def render_openrouter_feature(feature: dict[str, Any], model: str, aspect_ratio: str) -> None:
    default_model_for_feature = str(feature.get("model") or model)
    feature_mode = str(feature.get("mode") or "openrouter")
    supports_jimeng_generation = feature_mode == "jimeng"
    model_options_for_feature = MODEL_OPTIONS
    if feature.get("key") == "hd_batch":
        default_model_for_feature = NANO_BANANA_MODEL
        model_options_for_feature = [NANO_BANANA_MODEL]
    if not supports_jimeng_generation and default_model_for_feature not in model_options_for_feature:
        default_model_for_feature = model_options_for_feature[0] if model_options_for_feature else DEFAULT_MODEL
    min_images = int(feature.get("min_images", 0))
    max_output_images = int(feature.get("max_output_images", 0))
    supports_batch_multi_upload = feature["key"] in BATCH_MULTI_IMAGE_FEATURE_KEYS
    supports_skin_reference = feature["key"] == "hd_batch"
    supports_skin_tone_reference = feature["key"] == "skin_tone"
    supports_pupil_color_reference = feature["key"] == "pupil_color_change"
    supports_eye_shape_reference = feature["key"] == "eye_shape_change"
    supports_side_angle_reference = feature["key"] == "three_view"
    supports_ai_qa_image = feature["key"] == "ai_qa_image"
    supports_amazon_a_plus = feature["key"] == "amazon_a_plus"
    supports_pose_references = feature["key"] == "pose_change"
    supports_scene_references = feature["key"] == "scene_change"
    supports_outpaint = feature["key"] == "outpaint"
    model_reference_files = get_model_reference_files() if supports_skin_reference else []
    skin_texture_reference_files = get_skin_texture_reference_files() if supports_skin_reference else []
    result = st.session_state.feature_results.get(feature["key"]) or {}
    job_info = st.session_state.background_jobs.get(feature["key"]) or {}
    help_text = "可上传 JPG / PNG / WEBP。"
    if min_images > 0:
        help_text += f" 当前功能至少需要上传 {min_images} 张参考图。"
    active_model = default_model_for_feature

    st.markdown('<div class="workspace-panel">', unsafe_allow_html=True)
    page_subtitle = str(feature.get("summary") or feature.get("description") or "").strip()
    title_html = f'<div class="feature-title">{feature["name"]}<span class="feature-badge">AI 增强</span></div>'
    st.markdown(title_html, unsafe_allow_html=True)
    st.markdown(f'<div class="feature-desc">{page_subtitle}</div>', unsafe_allow_html=True)
    meta_items = [
        '<span class="meta-pill">支持 JPG、PNG、WEBP 格式</span>',
        '<span class="meta-pill">单张最大 50MB</span>',
        f'<span class="meta-pill">等比例放大，宽高都不小于 {get_feature_min_output_edge(feature)}px</span>',
    ]
    if supports_batch_multi_upload:
        meta_items.append(f'<span class="meta-pill">支持批量上传，最多 {BATCH_MULTI_IMAGE_MAX_FILES} 张</span>')
    if supports_outpaint:
        meta_items.append('<span class="meta-pill">支持上下左右扩展像素与羽化参数</span>')
    if max_output_images == 1:
        meta_items.append('<span class="meta-pill">默认输出 1 张结果图</span>')
    st.markdown(f'<div class="meta-row">{"".join(meta_items)}</div>', unsafe_allow_html=True)

    left_col, right_col = st.columns(2)
    with left_col:
        st.markdown(
            '<div class="result-block-title">文字要求</div>' if supports_jimeng_generation else '<div class="result-block-title">上传图片</div>',
            unsafe_allow_html=True,
        )
        skin_tone_reference_file = None
        pupil_color_reference_file = None
        eye_shape_reference_file = None
        side_angle_reference_file = None
        ai_qa_source_files: list[Any] = []
        ai_qa_prompt = ""
        jimeng_source_files: list[Any] = []
        jimeng_prompt = ""
        amazon_source_files: list[Any] = []
        amazon_size_text = "1464*600"
        pose_reference_files: list[Any] = []
        scene_reference_files: list[Any] = []
        batch_source_files: list[Any] = []
        hd_skin_reference_file = None
        hd_skin_texture_reference_file: Path | None = None
        outpaint_top_px = 0
        outpaint_bottom_px = 0
        outpaint_left_px = 0
        outpaint_right_px = 0
        outpaint_feather_strength = 20

        supports_dual_reference_upload = (
            supports_skin_tone_reference
            or supports_pupil_color_reference
            or supports_eye_shape_reference
            or supports_side_angle_reference
        )

        if supports_jimeng_generation:
            st.markdown(f'<div class="panel-subtitle">参考图片（最多 {JIMENG_MAX_INPUT_IMAGES} 张，可不传）</div>', unsafe_allow_html=True)
            jimeng_source_files = render_multi_image_uploader(
                "上传 Agent 参考图",
                key=f"jimeng_uploader_{feature['key']}",
                help_text=f"会先保存到服务器，再按 {get_jimeng_public_upload_base_url() or '/jimeng_uploads'} 生成公网地址后传给 Agent。最多 {JIMENG_MAX_INPUT_IMAGES} 张。",
                max_files=JIMENG_MAX_INPUT_IMAGES,
            )
            st.markdown('<div class="panel-subtitle">生成要求</div>', unsafe_allow_html=True)
            jimeng_prompt = st.text_area(
                "输入 Agent 的生图要求",
                key=f"jimeng_prompt_{feature['key']}",
                placeholder="例如：生成一张高级商业人像海报，肤质细腻，白色极简背景，灯光柔和，整体质感高级。",
                height=180,
                label_visibility="collapsed",
            )
            st.caption("支持纯文字生成，也支持先上传图片，再由服务器生成 `jimeng_uploads` 公网地址后传给 Agent。")
        elif supports_batch_multi_upload:
            st.markdown(
                f'<div class="panel-subtitle">原图（最多 {BATCH_MULTI_IMAGE_MAX_FILES} 张）</div>',
                unsafe_allow_html=True,
            )
            batch_source_files = render_multi_image_uploader(
                "上传原图",
                key=f"batch_uploader_{feature['key']}",
                help_text=f"可上传 JPG / PNG / WEBP。当前功能最多使用 {BATCH_MULTI_IMAGE_MAX_FILES} 张原图，系统会逐张处理并返回对应结果。",
                max_files=BATCH_MULTI_IMAGE_MAX_FILES,
            )
            if supports_outpaint:
                st.markdown('<div class="panel-subtitle">扩图参数</div>', unsafe_allow_html=True)
                top_col, bottom_col = st.columns(2)
                with top_col:
                    outpaint_top_px = int(
                        st.number_input(
                            "上方扩展像素",
                            min_value=0,
                            max_value=4000,
                            value=0,
                            step=10,
                            key=f"outpaint_top_{feature['key']}",
                        )
                    )
                    outpaint_left_px = int(
                        st.number_input(
                            "左侧扩展像素",
                            min_value=0,
                            max_value=4000,
                            value=0,
                            step=10,
                            key=f"outpaint_left_{feature['key']}",
                        )
                    )
                with bottom_col:
                    outpaint_bottom_px = int(
                        st.number_input(
                            "下方扩展像素",
                            min_value=0,
                            max_value=4000,
                            value=0,
                            step=10,
                            key=f"outpaint_bottom_{feature['key']}",
                        )
                    )
                    outpaint_right_px = int(
                        st.number_input(
                            "右侧扩展像素",
                            min_value=0,
                            max_value=4000,
                            value=0,
                            step=10,
                            key=f"outpaint_right_{feature['key']}",
                        )
                    )
                outpaint_feather_strength = int(
                    st.slider(
                        "边缘羽化程度",
                        min_value=0,
                        max_value=100,
                        value=20,
                        step=1,
                        key=f"outpaint_feather_{feature['key']}",
                    )
                )
                st.caption("像素值越大，画布在对应方向扩得越多；羽化值越大，原图与新增区域的过渡越柔和。")
            if supports_skin_reference:
                st.markdown('<div class="panel-subtitle">肤质参考图（可选，1 张）</div>', unsafe_allow_html=True)
                hd_skin_reference_file = render_single_image_uploader(
                    "上传肤质参考图",
                    key=f"hd_skin_reference_{feature['key']}",
                    help_text="不上传时默认使用 outputs/reference/参考1.png；上传后所有主图都会使用这张新参考图。",
                )
                if skin_texture_reference_files:
                    st.markdown('<div class="panel-subtitle">肌肤质感参考图库（单选）</div>', unsafe_allow_html=True)
                    selected_skin_texture_name = st.radio(
                        "选择肌肤质感参考图",
                        options=["不使用图库选项", *[path.name for path in skin_texture_reference_files]],
                        index=0,
                        key=f"hd_skin_texture_gallery_{feature['key']}",
                        horizontal=False,
                        label_visibility="collapsed",
                    )
                    if selected_skin_texture_name != "不使用图库选项":
                        hd_skin_texture_reference_file = next(
                            (path for path in skin_texture_reference_files if path.name == selected_skin_texture_name),
                            None,
                        )
                        if hd_skin_texture_reference_file is not None:
                            st.caption(f"当前图库参考图：{hd_skin_texture_reference_file.name}。优先级高于上方手动上传的肤质参考图。")
                            preview_col, _ = st.columns([1, 3])
                            with preview_col:
                                render_zoomable_image_gallery(
                                    [uploaded_input_to_data_url(hd_skin_texture_reference_file)],
                                    columns=1,
                                    thumb_height=150,
                                    component_key=f"hd_skin_texture_gallery_preview_{feature['key']}",
                                    fit_mode="contain",
                                    max_width_percent=100,
                                )
                else:
                    st.caption("未找到 `肌肤质感参考` 文件夹中的可用图片，将继续使用上传参考图或默认参考图。")
        elif supports_ai_qa_image:
            st.markdown('<div class="panel-subtitle">参考图片（最多 3 张）</div>', unsafe_allow_html=True)
            ai_qa_source_files = render_multi_image_uploader(
                "上传问答参考图",
                key=f"ai_qa_uploader_{feature['key']}",
                help_text="可上传 JPG / PNG / WEBP。当前功能最多使用 3 张参考图。",
                max_files=3,
            )
            st.markdown('<div class="panel-subtitle">文字要求</div>', unsafe_allow_html=True)
            ai_qa_prompt = st.text_area(
                "输入你的问答要求",
                key=f"ai_qa_prompt_{feature['key']}",
                placeholder="例如：参考这张模特图，保持人物不变，生成一张更高级的白色极简背景海报图。",
                height=120,
                label_visibility="collapsed",
            )
        elif supports_amazon_a_plus:
            st.markdown('<div class="panel-subtitle">A+原图（最多 3 张）</div>', unsafe_allow_html=True)
            amazon_source_files = render_multi_image_uploader(
                "上传A+原图",
                key=f"amazon_uploader_{feature['key']}",
                help_text="可上传 JPG / PNG / WEBP。当前功能最多使用 3 张原图。",
                max_files=3,
            )
            st.markdown('<div class="slot-helper">图片预览显示在上方，上传框保留在下方</div>', unsafe_allow_html=True)
            st.markdown('<div class="panel-subtitle">A+规格参数</div>', unsafe_allow_html=True)
            amazon_size_text = st.text_input(
                "输入规格参数",
                value="1464*600",
                key=f"amazon_size_{feature['key']}",
                placeholder="例如 1464*600",
                label_visibility="collapsed",
            )
        elif supports_pose_references or supports_scene_references or supports_dual_reference_upload:
            subject_label = "主体图（1 张）" if supports_dual_reference_upload else "主模特图（1 张）"
            st.markdown(f'<div class="panel-subtitle">{subject_label}</div>', unsafe_allow_html=True)
            uploaded_file = render_single_image_uploader(
                "上传主体图" if supports_dual_reference_upload else "上传主模特图",
                key=f"uploader_{feature['key']}",
                help_text=help_text,
            )

            if supports_skin_tone_reference:
                st.markdown('<div class="panel-subtitle">肤色参考图（1 张）</div>', unsafe_allow_html=True)
                skin_tone_reference_file = render_single_image_uploader(
                    "上传肤色参考图",
                    key=f"skin_tone_ref_{feature['key']}",
                )

            if supports_pupil_color_reference:
                st.markdown('<div class="panel-subtitle">瞳孔颜色参考图（1 张）</div>', unsafe_allow_html=True)
                pupil_color_reference_file = render_single_image_uploader(
                    "上传瞳孔颜色参考图",
                    key=f"pupil_color_ref_{feature['key']}",
                )

            if supports_eye_shape_reference:
                st.markdown('<div class="panel-subtitle">眼型参考图（1 张）</div>', unsafe_allow_html=True)
                eye_shape_reference_file = render_single_image_uploader(
                    "上传眼型参考图",
                    key=f"eye_shape_ref_{feature['key']}",
                )

            if supports_side_angle_reference:
                st.markdown('<div class="panel-subtitle">角度参考图（1 张）</div>', unsafe_allow_html=True)
                side_angle_reference_file = render_single_image_uploader(
                    "上传角度参考图",
                    key=f"side_angle_ref_{feature['key']}",
                )

            if supports_pose_references:
                st.markdown('<div class="panel-subtitle">姿势参考图（最多 5 张）</div>', unsafe_allow_html=True)
                pose_reference_files = render_reference_slot_uploaders(f"pose_refs_{feature['key']}", 5)
                st.markdown('<div class="slot-helper">直接在方框中上传姿势参考图</div>', unsafe_allow_html=True)

            if supports_scene_references:
                st.markdown('<div class="panel-subtitle">场景参考图（最多 5 张）</div>', unsafe_allow_html=True)
                scene_reference_files = render_reference_slot_uploaders(f"scene_refs_{feature['key']}", 5)
                st.markdown('<div class="slot-helper">直接在方框中上传场景参考图</div>', unsafe_allow_html=True)
        else:
            uploaded_file = render_single_image_uploader(
                "上传参考图",
                key=f"uploader_{feature['key']}",
                help_text=help_text,
            )
    with right_col:
        st.markdown('<div class="result-block-title">结果图预览</div>', unsafe_allow_html=True)
        result_images = list(result.get("images") or [])
        result_captions = list(result.get("captions") or [])
        if supports_batch_multi_upload and result_images and result_captions:
            render_result_preview_with_captions(result_images, result_captions, feature["key"])
        else:
            render_result_preview(result_images, show_title=False)

    if job_info.get("status") == "running":
        render_running_job_status(feature["key"])
    elif job_info.get("status") == "error":
        st.error(f"后台任务失败：{job_info.get('error')}")
    elif job_info.get("status") == "completed":
        st.success("后台任务已完成，可继续查看或处理其他功能。")
        if feature.get("output_mode") == "image" and not (result.get("images") or []):
            st.warning("本次任务已结束，但模型没有返回图片。建议重试一次，或切换其他模型。")
        result_text = str(result.get("text") or "").strip()
        if result_text:
            if "已自动回退为智能超清结果" in result_text:
                st.warning(result_text)
            else:
                st.info(result_text)
        storage_error = str(result.get("storage_error") or "").strip()
        if storage_error:
            st.warning(storage_error)

    if supports_jimeng_generation:
        st.caption("当前模型：Agent")
    else:
        selector_col, _ = st.columns([1.35, 4.65], gap="small")
        with selector_col:
            active_model = st.selectbox(
                "模型切换",
                model_options_for_feature,
                index=model_options_for_feature.index(default_model_for_feature),
                format_func=get_model_display_name,
                key=f"model_select_{feature['key']}",
            )
        if feature.get("key") == "hd_batch":
            st.caption("即梦 4.6 高清已暂时关闭，当前仅保留 Nano Banana。")
    active_batch_concurrency = DEFAULT_BATCH_API_CONCURRENCY if supports_batch_multi_upload else 1
    process_col, _, _ = st.columns([1, 1, 4.6], gap="small")
    with process_col:
        submitted = st.button("开始处理", key=f"process_{feature['key']}", type="secondary", use_container_width=True)

    if submitted:
        if job_info.get("status") == "running":
            st.warning("当前功能已有任务在后台处理中，请等待完成后再发起新的任务。")
            st.markdown("</div>", unsafe_allow_html=True)
            return
        if supports_batch_multi_upload:
            files = list(batch_source_files)
        elif supports_ai_qa_image:
            files = list(ai_qa_source_files)
        elif supports_amazon_a_plus:
            files = list(amazon_source_files)
        elif supports_jimeng_generation:
            files = list(jimeng_source_files)
        else:
            files = [uploaded_file] if uploaded_file is not None else []
        custom_prompt = jimeng_prompt if supports_jimeng_generation else (ai_qa_prompt if supports_ai_qa_image else "")
        target_size = parse_size_text(amazon_size_text) if supports_amazon_a_plus else None
        using_jimeng_for_request = supports_jimeng_generation or is_jimeng_model(active_model)
        if supports_jimeng_generation and not jimeng_prompt.strip():
            st.warning("请输入 Agent 的生图要求。")
        elif feature["key"] == "hd_batch" and is_jimeng_model(active_model):
            st.warning("即梦 4.6 高清已暂时关闭，请先使用 Nano Banana。")
        elif using_jimeng_for_request and len(files) > JIMENG_MAX_INPUT_IMAGES and not supports_batch_multi_upload:
            st.warning(f"Agent 最多只能上传 {JIMENG_MAX_INPUT_IMAGES} 张图片。")
        elif len(files) < min_images:
            st.warning(f"当前功能至少需要上传 {min_images} 张参考图。")
        elif supports_ai_qa_image and len(files) > 3:
            st.warning("AI问答生图功能最多只能上传 3 张参考图。")
        elif supports_ai_qa_image and not ai_qa_prompt.strip():
            st.warning("请输入你的文字要求。")
        elif supports_amazon_a_plus and len(files) > 3:
            st.warning("亚马逊A+功能最多只能上传 3 张原图。")
        elif supports_amazon_a_plus and target_size is None:
            st.warning("请输入正确的规格参数，例如 1464*600。")
        elif supports_outpaint and (outpaint_top_px + outpaint_bottom_px + outpaint_left_px + outpaint_right_px) <= 0:
            st.warning("请至少设置一个方向的扩图像素。")
        elif supports_skin_tone_reference and skin_tone_reference_file is None:
            st.warning("请先上传 1 张肤色参考图。")
        elif supports_pupil_color_reference and pupil_color_reference_file is None:
            st.warning("请先上传 1 张瞳孔颜色参考图。")
        elif supports_eye_shape_reference and eye_shape_reference_file is None:
            st.warning("请先上传 1 张眼型参考图。")
        elif supports_side_angle_reference and side_angle_reference_file is None:
            st.warning("请先上传 1 张角度参考图。")
        else:
            extra_notes = ""
            batch_groups: list[list[Any]] = []
            st.session_state.feature_results.pop(feature["key"], None)
            if feature["key"] == "hd_batch":
                extra_notes = (
                    "第1张图必须作为唯一主体，不允许改变人物身份、五官比例、脸型、表情、发型和构图。"
                    "如果存在第2张图，第2张图只作为肤质参考，但皮肤状态必须严格参考第2张图。"
                    "必须重点贴近第2张图的肤理、毛孔、皮肤颗粒感、光泽方式、细腻程度、粗糙程度、通透感和整体肤感，不允许只做轻微参考。"
                    "严禁从第2张图借用或迁移脸型、五官、眼睛形状、鼻子、嘴唇、眉形、妆容、肤色、表情、发型、服饰、背景或人物身份。"
                    "批量时上传几张主图，就只返回几张高清结果图；每张主图只允许对应1张结果图。"
                )
            elif supports_outpaint:
                files = [
                    prepare_outpaint_uploaded_input(
                        item,
                        outpaint_top_px,
                        outpaint_bottom_px,
                        outpaint_left_px,
                        outpaint_right_px,
                        outpaint_feather_strength,
                    )
                    for item in files
                ]
                extra_notes = build_outpaint_extra_notes(
                    outpaint_top_px,
                    outpaint_bottom_px,
                    outpaint_left_px,
                    outpaint_right_px,
                    outpaint_feather_strength,
                )
            elif supports_skin_tone_reference:
                files.append(skin_tone_reference_file)
                extra_notes = (
                    "第 1 张图是主体图，必须以这张图的人物身份和画面内容为绝对主体。"
                    "第 2 张图是肤色参考图。"
                    "只参考第 2 张图中的肤色信息，包括肤色倾向、冷暖关系、深浅程度和综合色调。"
                    "除肤色之外，一概不要参考第 2 张图中的任何其他内容，包括人物身份、五官、发型、妆容、服饰、体型、姿势、背景、场景、道具、光线、色彩、构图和风格。"
                    "第 1 张主体图中的人物身份、脸部特征、五官结构、发型、妆容、服饰、肤质、毛孔、皮肤纹理、姿势、构图、机位、光线、背景和整体风格都必须严格保持不变。"
                    "仅生成 1 张结果图，不要输出多个版本。"
                )
            elif supports_ai_qa_image:
                extra_notes = (
                    f"当前共上传 {len(files)} 张参考图。"
                    "请先充分理解这些图片中的主体、构图、场景、风格、细节和视觉关系，再严格执行用户的文字要求。"
                    "如果用户要求保留原图中的人物、商品、场景或构图，需要优先保持一致。"
                    "只输出 1 张最终结果图，不要输出多个版本。"
                )
            elif supports_amazon_a_plus:
                target_width, target_height = target_size
                feature["target_size_text"] = f"{target_width}*{target_height}"
                extra_notes = (
                    f"当前共上传 {len(files)} 张原图。"
                    "请将这些原图中的主体内容进行整合排版，生成适合亚马逊 A+ 模块展示的电商视觉成品。"
                    "可以对原图进行裁切、缩放、组合、留白、分栏和版式设计，但不要替换上传的主体内容，不要生成无关商品。"
                    "版面需要整洁、商业化、信息展示清晰、视觉重点明确。"
                    f"最终成品画布尺寸必须严格等于 {target_width}*{target_height}px。"
                    "仅生成 1 张完整成品图，不要输出多张，不要输出草图或分步骤图。"
                )
            elif supports_pupil_color_reference:
                files.append(pupil_color_reference_file)
                extra_notes = (
                    "第 1 张图是主体图，必须以这张图的人物身份和画面内容为绝对主体。"
                    "第 2 张图是瞳孔颜色参考图。"
                    "只参考第 2 张图中的瞳孔颜色信息，包括颜色倾向、明暗表现和综合色调。"
                    "除瞳孔颜色之外，一概不要参考第 2 张图中的任何其他内容，包括人物身份、五官、眼型、发型、妆容、睫毛、服饰、体型、姿势、背景、场景、道具、光线、色彩、构图和风格。"
                    "第 1 张主体图中的人物身份、脸部特征、眼型、眼神、睫毛、妆容、肤质、皮肤纹理、发型、服饰、姿势、构图、机位、光线、背景和整体风格都必须严格保持不变。"
                    "仅生成 1 张结果图，不要输出多个版本。"
                )
            elif supports_eye_shape_reference:
                files.append(eye_shape_reference_file)
                extra_notes = (
                    "第 1 张图是主体图，必须以这张图的人物身份和画面内容为绝对主体。"
                    "第 2 张图是眼型参考图。"
                    "只参考第 2 张图中的眼型信息，包括眼裂形状、眼角走向、眼睑弧度和眼部轮廓结构。"
                    "除眼型之外，一概不要参考第 2 张图中的任何其他内容，包括人物身份、五官、瞳孔颜色、发型、妆容、睫毛、服饰、体型、姿势、背景、场景、道具、光线、色彩、构图和风格。"
                    "第 1 张主体图中的人物身份、脸部特征、瞳孔颜色、眼神、睫毛、妆容、肤质、皮肤纹理、发型、服饰、姿势、构图、机位、光线、背景和整体风格都必须严格保持不变。"
                    "仅生成 1 张结果图，不要输出多个版本。"
                )
            elif supports_side_angle_reference:
                files.append(side_angle_reference_file)
                extra_notes = (
                    "第 1 张图是主体图，必须以这张图的人物身份和画面内容为绝对主体。"
                    "第 2 张图是角度参考图。"
                    "只参考第 2 张图中的拍摄角度、头部朝向、脸部转向和侧面视角关系。"
                    "除角度之外，一概不要参考第 2 张图中的任何其他内容，包括人物身份、脸部特征、发型、妆容、服饰、肤质、背景、场景、道具、光线、色彩、构图和整体风格。"
                    "第 1 张主体图中的人物身份、脸部特征、发型、妆容、服饰、肤质、背景、场景、光线、色彩、构图和整体风格都必须严格保持不变。"
                    "仅生成 1 张结果图，不要输出多个版本。"
                )
            elif supports_pose_references:
                files.extend(pose_reference_files)
                files.extend(scene_reference_files)
                pose_count = len(pose_reference_files)
                parts = [
                    "第 1 张图是主模特图，必须以这张图的人物身份为绝对主体。",
                    f"姿势参考图共 {pose_count} 张。",
                    "只参考姿势参考图中的动作、肢体姿势、头部朝向、手势、站姿或坐姿、重心方向和镜头方向。",
                    "生成结果中的姿势必须与参考图完全一致，包括头部朝向、肩颈角度、手臂位置、手势、身体转向、躯干弯曲、腿部动作、站姿或坐姿、重心方向和动作细节。",
                    "除姿势之外，一概不要参考姿势参考图中的任何其他内容，包括人物身份、五官、发型、妆容、服饰、体型、肤色、背景、场景、道具、光线、色彩、构图和风格。",
                    "主模特图中的人物身份、脸部特征、发型、妆容、服饰、场景、背景、光线、构图和整体风格都必须严格保持不变。",
                    "不允许修改背景环境，不允许替换场景。",
                    "仅生成 1 张结果图，不要输出多个版本。",
                ]
                extra_notes = "".join(parts)
            elif supports_scene_references:
                files.extend(scene_reference_files)
                scene_count = len(scene_reference_files)
                parts = [
                    "第 1 张图是主模特图，必须以这张图的人物身份为绝对主体。",
                    f"场景参考图共 {scene_count} 张。",
                    "只参考场景参考图中的背景、空间氛围、环境风格。",
                    "主模特图中的人物身份、脸部特征、发型、妆容、服饰、姿势、肢体动作、构图、机位和光线关系都必须严格保持不变。",
                    "不允许修改人物姿势，不允许改变主体人物。",
                    "仅生成 1 张结果图，不要输出多个版本。",
                ]
                extra_notes = "".join(parts)
            if using_jimeng_for_request:
                final_prompt = build_jimeng_prompt(feature, custom_prompt, aspect_ratio, extra_notes)
            else:
                final_prompt = build_prompt(feature, custom_prompt, aspect_ratio, extra_notes)
            selected_hd_reference_input = hd_skin_texture_reference_file or hd_skin_reference_file
            if feature["key"] == "hd_batch" and selected_hd_reference_input is not None:
                batch_groups = [[item, selected_hd_reference_input] for item in files]
            elif supports_batch_multi_upload and not batch_groups:
                batch_groups = [[item] for item in files]
            if using_jimeng_for_request and batch_groups and any(len(group) > JIMENG_MAX_INPUT_IMAGES for group in batch_groups):
                st.warning(f"当前这组 Agent 请求中有图片数量超过 {JIMENG_MAX_INPUT_IMAGES} 张，请减少参考图数量后再试。")
                st.markdown("</div>", unsafe_allow_html=True)
                return
            if using_jimeng_for_request and not batch_groups and len(files) > JIMENG_MAX_INPUT_IMAGES:
                st.warning(f"当前这次 Agent 请求最多只能携带 {JIMENG_MAX_INPUT_IMAGES} 张图片。")
                st.markdown("</div>", unsafe_allow_html=True)
                return
            submit_feature_job(
                feature,
                {
                    "feature": dict(feature),
                    "model": active_model,
                    "prompt": final_prompt,
                    "uploaded_files": [prepare_uploaded_input(item) for item in files] if not supports_batch_multi_upload else [],
                    "batch_groups": (
                        [
                            [prepare_uploaded_input(group_item) for group_item in group]
                            for group in batch_groups
                        ]
                        if supports_batch_multi_upload
                        else []
                    ),
                    "output_mode": feature["output_mode"],
                    "max_output_images": max_output_images,
                    "target_size": target_size if supports_amazon_a_plus and target_size is not None else None,
                    "account_name": str(st.session_state.get("auth_username") or "admin"),
                    "batch_concurrency": active_batch_concurrency,
                    "aspect_ratio": aspect_ratio,
                },
            )
            if supports_batch_multi_upload:
                effective_submit_concurrency = min(len(batch_groups) if batch_groups else len(files), active_batch_concurrency)
                st.info(
                    f"已提交 {len(files)} 张图片到后台批量处理，最多 4 路并发，当前实际按 {effective_submit_concurrency} 路执行，你可以先切换到其他功能。"
                )
            else:
                st.info("任务已提交到后台处理，你可以先切换到其他功能。")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    render_history_records(feature)


def render_login_page() -> None:
    authenticate_requested_user()
    st.rerun()


def render_side_menu(current_feature: dict[str, Any]) -> None:
    st.markdown(
        """
        <div class="side-menu-shell">
            <div class="brand-wrap">
                <div class="brand-logo">AI</div>
                <div>
                    <div class="brand-title">小哈</div>
                    <div class="brand-subtitle">专业的 AI 图像处理工具</div>
                </div>
            </div>
            <div class="side-menu-note">功能菜单</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for feature in FEATURES:
        is_active = st.session_state.selected_feature_key == feature["key"]
        if st.button(
            feature["name"],
            key=f"side_menu_feature_{feature['key']}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            if st.session_state.selected_feature_key != feature["key"]:
                st.session_state.selected_feature_key = feature["key"]
                st.rerun()


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
        ],
    )


def main() -> None:
    st.set_page_config(page_title="小哈", layout="wide", initial_sidebar_state="expanded")
    ensure_state()
    restore_auth_session()
    sync_background_jobs()
    ensure_history_storage()
    jimeng_static_server = ensure_jimeng_static_server()
    if consume_pending_upload_delete():
        st.rerun()
    inject_app_styles()
    if not st.session_state.is_authenticated:
        authenticate_requested_user()
    feature_keys = {feature["key"] for feature in FEATURES}
    if st.session_state.selected_feature_key not in feature_keys:
        st.session_state.selected_feature_key = FEATURES[0]["key"]

    current_feature = next(
        feature for feature in FEATURES if feature["key"] == st.session_state.selected_feature_key
    )
    if not bool(jimeng_static_server.get("started")):
        st.warning(
            "Agent 参考图静态服务启动失败，当前图片上传到 Agent 可能无法使用。"
            f"{str(jimeng_static_server.get('error') or '').strip()}"
        )
    menu_col, content_col = st.columns([0.46, 4.54], gap="medium")
    with menu_col:
        render_side_menu(current_feature)
    with content_col:
        render_openrouter_feature(current_feature, model=DEFAULT_MODEL, aspect_ratio=DEFAULT_ASPECT_RATIO)


if __name__ == "__main__":
    if is_running_in_streamlit():
        main()
    else:
        relaunch_with_streamlit()
