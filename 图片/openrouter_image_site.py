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
from datetime import date, datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageStat


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from secret_settings import relocate_storage_path, sql_server_config
from 图片.amazon_a_plus_psd import (
    build_layered_a_plus,
    fit_green_screen_to_canvas,
    select_closest_aspect_ratio,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_IMAGES_URL = "https://openrouter.ai/api/v1/images"
DEFAULT_MODEL = "google/gemini-3.1-flash-image"
NANO_BANANA_MODEL = "google/gemini-3.1-flash-image"
DEFAULT_ASPECT_RATIO = "自动"
REFERENCE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MIN_OUTPUT_EDGE = 2000
HD_MIN_OUTPUT_EDGE = 4096
HD_MODEL_REFERENCE_FILE = APP_DIR / "__pycache__" / "model_reference" / "模特参考图.png"
OUTPUTS_HD_REFERENCE_DIR = APP_DIR / "outputs" / "reference"
OUTPUTS_HD_DEFAULT_REFERENCE_FILE = OUTPUTS_HD_REFERENCE_DIR / "参考1.png"
SKIN_TEXTURE_REFERENCE_DIR = Path(r"D:\tuchuangai\肌肤质感参考")
PORTRAIT_HD_DEFAULT_IMAGE_SIZE = "4K"
PORTRAIT_HD_SKIN_LOCK_RULES = (
    "肤色与肤质锁定是本次高清处理的最高优先级。"
    "必须严格保持第1张原图皮肤的明暗、冷暖、色相、白平衡、通透度、红润度、肤色不均和局部色差完全一致，禁止提亮、压暗、增白、变黄、变红或统一肤色。"
    "必须严格保持第1张原图已有的毛孔、皮肤颗粒、油脂光泽、干燥感、斑点、雀斑、痣、痘印、细纹、皱纹和眼周纹理，禁止磨皮、美颜、祛斑、去痣、去痘印、去细纹或重塑皮肤。"
    "如果存在第2张肤质参考图，只能参考其清晰度、分辨率和细节解析水平，严禁迁移第2张图的肤色、肤质、毛孔形态、皮肤状态、光泽、颗粒、妆容或任何人物特征。"
    "任何基础提示词、参考图或用户补充要求与此规则冲突时，都必须优先保持第1张原图的肤色和肤质不变。"
)
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
XIAOHA_DASHBOARD_KEY = "__usage_dashboard__"
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
OPENROUTER_MAX_INPUT_IMAGE_BYTES = 29 * 1024 * 1024
OPENROUTER_SAFE_INPUT_TARGET_BYTES = 24 * 1024 * 1024
OPENROUTER_MAX_INPUT_IMAGE_EDGE = 4096
OPENROUTER_IMAGES_CONNECT_TIMEOUT_SECONDS = 30
OPENROUTER_IMAGES_READ_TIMEOUT_SECONDS = 360
OPENROUTER_IMAGES_MAX_ATTEMPTS = 2
OPENROUTER_IMAGES_RETRY_DELAYS = (4,)
OPENROUTER_IMAGES_TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
JIMENG_HD_API_RESOLUTION = "8k"
JIMENG_HD_API_SCALE = 30
DB_IMAGE_DIR = Path(r"D:\tuchuangai\视觉图片")
CUTOUT_OUTPUT_DIR = Path(r"D:\tuchuangai\视觉图片")
DB_HISTORY_LIMIT = MAX_HISTORY_RECORDS
DB_HISTORY_THUMB_DIR_NAME = "_thumbs"
DB_HISTORY_THUMB_MAX_EDGE = 640
DB_HISTORY_THUMB_TARGET_BYTES = 140 * 1024
DB_HISTORY_PATH_MAX_LENGTH = 50
DB_HISTORY_ALL_ACCESS_USERS = {"周俊成"}
GALLERY_PREVIEW_MAX_EDGE = 1600
GALLERY_PREVIEW_TARGET_BYTES = 220 * 1024
UPLOAD_CACHE_DIR = Path(r"D:\tuchuangai\图片上传缓存")
AUTH_QUERY_USER_KEY = "auth_user"
AUTH_QUERY_TOKEN_KEY = "auth_token"
FEATURE_QUERY_KEY = "feature"
MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY = "a_plus_manual_point"
UPLOAD_DELETE_QUERY_KEY = "delete_upload"
UPLOAD_REPLACE_WIDGET_QUERY_KEY = "replace_upload_widget"
UPLOAD_REPLACE_INDEX_QUERY_KEY = "replace_upload_index"
OUTPAINT_DRAG_QUERY_KEY = "outpaint_drag"
AUTH_TOKEN_SALT = "lashforge-auth-v1"
DB_CONFIG = sql_server_config()
DEFAULT_SERVER_ADDRESS = "0.0.0.0"
DEFAULT_SERVER_PORT = 8501
DEFAULT_JIMENG_STATIC_PORT = 8502
DEFAULT_PUBLIC_APP_URL = "http://www.toochuangai.com:8501/lashforge"
INFINITE_CANVAS_STATIC_ROUTE_PREFIX = "/infinite-canvas"
INFINITE_CANVAS_BUILD_DIR = Path(
    os.getenv(
        "INFINITE_CANVAS_BUILD_DIR",
        r"D:\toochuangai\_non_code_files\infinite-canvas\build",
    )
)
DEFAULT_LOGIN_ACCOUNTS = {}
MODEL_OPTIONS = [
    JIMENG_MODEL_NAME,
    "google/gemini-2.5-flash-image",
    "google/gemini-3.1-flash-image",
    "google/gemini-3-pro-image-preview",
    "openai/gpt-5.4-image-2",
    "openai/gpt-5-image-mini",
    "openai/gpt-5-image",
    "bytedance-seed/seedream-4.5",
    "x-ai/grok-imagine-image-quality",
    "recraft/recraft-v4.1-utility-pro",
]
INFINITE_CANVAS_IMAGE_MODELS = tuple(
    model for model in MODEL_OPTIONS if model != JIMENG_MODEL_NAME
)
INFINITE_CANVAS_TEXT_MODELS = ("google/gemini-2.5-flash",)
IMAGE_ONLY_OUTPUT_MODEL_PREFIXES = (
    "bytedance-seed/",
    "x-ai/grok-imagine-image",
    "recraft/",
)
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
BATCH_MULTI_IMAGE_FEATURE_KEYS = {"hd_batch", "remove_eyelashes", "outpaint", "single_to_double"}
BATCH_MULTI_IMAGE_MAX_FILES = 20
INFINITE_CANVAS_STEP_FEATURE_KEYS = ("hd_batch", "remove_eyelashes", "outpaint", "single_to_double")
INFINITE_CANVAS_MAX_INPUT_IMAGES = 6
INFINITE_CANVAS_MAX_STEPS = 4
OUTPAINT_FALLBACK_MAX_EXTENSION_PX = 300
OUTPAINT_DEFAULT_EXTENSION_PX = 100
OUTPAINT_MAX_CANVAS_MULTIPLIER = 3
OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX = 30_000
OUTPAINT_RESULTS_PER_SOURCE = 1
OUTPAINT_GUIDE_MAX_EDGE = 1024
MAX_BATCH_API_CONCURRENCY = 4
DEFAULT_BATCH_API_CONCURRENCY = 4
JIMENG_MAX_API_CONCURRENCY = 1
JIMENG_CONCURRENT_LIMIT_RETRY_COUNT = 3
JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS = (3, 6, 10)
AMAZON_A_PLUS_MAX_EDGE = 10_000
AMAZON_A_PLUS_MAX_PIXELS = 40_000_000
AMAZON_A_PLUS_NATIVE_IMAGE_SIZE = "4K"
AMAZON_A_PLUS_FEATURE_KEY = "amazon_a_plus"
MAIN_IMAGE_A_PLUS_FEATURE_KEY = "main_image_a_plus"
A_PLUS_IMAGES_API_FEATURE_KEYS = {
    AMAZON_A_PLUS_FEATURE_KEY,
    MAIN_IMAGE_A_PLUS_FEATURE_KEY,
}
MAIN_IMAGE_A_PLUS_MAX_FILES = 10
MAIN_IMAGE_A_PLUS_SECTION_COUNT = 4
MAIN_IMAGE_A_PLUS_MAX_SECTION_CONCURRENCY = 4
MAIN_IMAGE_A_PLUS_REFERENCE_MAX_EDGE = 2048
MAIN_IMAGE_A_PLUS_REFERENCE_TARGET_BYTES = 3 * 1024 * 1024
MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL = "google/gemini-2.5-flash"
MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS = 20
MAIN_IMAGE_A_PLUS_MODE_FREE = "free_create"
MAIN_IMAGE_A_PLUS_MODE_TEMPLATE = "template_replace"
MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST = "single_test"
MAIN_IMAGE_A_PLUS_MODE_ELEMENT = "element_replace"
MAIN_IMAGE_A_PLUS_MODE_LABELS = {
    MAIN_IMAGE_A_PLUS_MODE_FREE: "自由创作",
    MAIN_IMAGE_A_PLUS_MODE_TEMPLATE: "套版替换",
    MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST: "一张测试",
    MAIN_IMAGE_A_PLUS_MODE_ELEMENT: "指定元素替换",
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
        "text_margin_x": 48,
        "text_margin_y": 32,
    },
    "desktop_equal": {
        "label": "电脑端｜1464×2400｜自然均衡",
        "target_size": (1464, 2400),
        "section_heights": (600, 600, 600, 600),
        "text_margin_x": 120,
        "text_margin_y": 72,
    },
    "desktop_hero": {
        "label": "电脑端｜1464×2400｜首屏突出",
        "target_size": (1464, 2400),
        "section_heights": (800, 533, 533, 534),
        "text_margin_x": 120,
        "text_margin_y": 64,
    },
}
MAIN_IMAGE_A_PLUS_SECTION_PURPOSES = (
    "模特与品牌主视觉",
    "核心卖点与关键细节",
    "使用场景、功能表现或工艺展示",
    "套装规格、包装信息与品牌收尾",
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
        canvas_directory: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.upload_directory = str(upload_directory or directory or ".")
        self.history_directory = str(history_directory or DB_IMAGE_DIR)
        self.canvas_directory = str(canvas_directory or INFINITE_CANVAS_BUILD_DIR)
        super().__init__(*args, directory=self.upload_directory, **kwargs)

    def do_GET(self) -> None:
        request_url = urllib.parse.urlsplit(self.path)
        request_path = urllib.parse.unquote(request_url.path or "/").rstrip("/")
        bootstrap_path = f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/api/bootstrap-config"
        if request_path == bootstrap_path:
            self.serve_infinite_canvas_bootstrap(request_url.query)
            return
        super().do_GET()

    def end_headers(self) -> None:
        request_url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(request_url.query)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "Content-Disposition, Content-Type")
        if str((query.get("download") or [""])[0]).strip() == "1":
            file_name = Path(urllib.parse.unquote(request_url.path or "")).name or "image.png"
            encoded_name = urllib.parse.quote(file_name)
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded_name}")
        super().end_headers()

    def serve_infinite_canvas_bootstrap(self, query_text: str) -> None:
        query = urllib.parse.parse_qs(query_text)
        username = str((query.get(AUTH_QUERY_USER_KEY) or [""])[0]).strip()
        auth_token = str((query.get(AUTH_QUERY_TOKEN_KEY) or [""])[0]).strip()
        expected_token = build_auth_token(username) if username else ""
        if not username or not auth_token or not hmac.compare_digest(auth_token, expected_token):
            self.send_json({"success": False, "message": "无效的画布访问凭证"}, status=403)
            return

        api_key = load_api_key()
        if not api_key:
            self.send_json({"success": False, "message": "OPENROUTER_API_KEY 未配置"}, status=503)
            return

        image_models = list(INFINITE_CANVAS_IMAGE_MODELS)
        text_models = list(INFINITE_CANVAS_TEXT_MODELS)
        self.send_json(
            {
                "success": True,
                "config": {
                    "channel": {
                        "id": "xiaoha-openrouter",
                        "name": "小哈 OpenRouter",
                        "baseUrl": "https://openrouter.ai/api/v1",
                        "apiKey": api_key,
                        "apiFormat": "openai",
                        "models": image_models + text_models,
                    },
                    "imageModel": "google/gemini-3.1-flash-image",
                    "textModel": text_models[0],
                    "videoModel": "",
                    "audioModel": "",
                    "imageModels": image_models,
                    "textModels": text_models,
                    "videoModels": [],
                    "audioModels": [],
                },
            }
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


def build_infinite_canvas_url(public_app_url: str, static_port: int, username: str) -> str:
    raw_url = str(public_app_url or "").strip() or DEFAULT_PUBLIC_APP_URL
    parsed = urllib.parse.urlsplit(raw_url)
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname or "www.toochuangai.com"
    netloc = hostname
    default_port = 443 if scheme == "https" else 80
    if static_port and static_port != default_port:
        netloc = f"{hostname}:{static_port}"
    normalized_username = str(username or "访客").strip() or "访客"
    query = urllib.parse.urlencode(
        {
            AUTH_QUERY_USER_KEY: normalized_username,
            AUTH_QUERY_TOKEN_KEY: build_auth_token(normalized_username),
            "embed": "true",
        }
    )
    return urllib.parse.urlunsplit(
        (scheme, netloc, f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/canvas", query, "")
    )


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


FEATURES = [
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
        "summary": "提升分辨率，优化细节",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "高清增强，清晰优先，按原比例放大且宽高都不小于 3200px。",
        "default_prompt": (
            "请基于输入图片进行高清修复和细节增强，4K 清晰度，不要改变人物身份、五官比例、脸型、表情、发型和构图。"
            + PORTRAIT_HD_SKIN_LOCK_RULES
            + "眼部和睫毛是最重要的区域，只提升清晰度，不改变眼睛大小、眼型、眼神或睫毛形态。"
            "增强目标："
            "1. 皮肤只提升原有细节的可见清晰度，原有肤色、肤质、毛孔、斑点、痣、痘印和细纹必须全部保留，不得美颜或修饰。"
            "2. 重点增强眼部区域：睫毛根根分明、自然纤细、不要变成假睫毛或夸张妆感。"
            "3. 提升眉毛、眼线边缘、虹膜高光、眼周皮肤纹理的清晰度。"
            "4. 如果提供肤质参考图，只参考清晰度与细节解析水平，不能参考或迁移其肤色和肤质。"
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
            "You are performing a local image edit only. "
            "The existing image is locked. "
            "Every pixel outside the eyelashes is read-only and must remain pixel-identical. "
            "Only remove all eyelashes, including both natural eyelashes and false eyelashes. "
            "Do not modify the eyelids, eyes, irises, pupils, eyebrows, eye shape, or any surrounding skin. "
            "Do not redraw, enhance, beautify, retouch, resize, reposition, crop, rotate, or reinterpret any existing content. "
            "Maintain exactly the same person, facial identity, face shape, facial features, eye position, skin texture, skin tone, makeup, hairstyle, clothing, accessories, pose, expression, lighting, shadows, colors, sharpness, composition, background, and image resolution. "
            "Do not add, remove, or modify any detail other than the eyelashes. "
            "The final result must look like the exact same photograph with only the eyelashes removed. "
            "Output exactly one realistic image."
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
        "max_output_images": OUTPAINT_RESULTS_PER_SOURCE,
        "description": "适合半身补全、边缘扩展、补足背景和人物缺失区域，但原图已有细节必须完全保持不变。",
        "default_prompt": (
            "Perform one-pass direct outpainting from the uploaded original photograph. "
            "Generate the entire larger-frame photograph as one continuous image in a single model pass. "
            "Do not paste, composite, embed, overlay, or preserve the source as a rectangular block inside the result. "
            "There must be no visible original-image rectangle, inset photo, border, frame, hard edge, color block, tonal step, or rectangular seam anywhere in the final image. "
            "Extend the camera field of view beyond the requested original borders while keeping the same person, identity, face, expression, pose, hairstyle, clothing, camera viewpoint, perspective, lighting, colors, focus, and photographic style as stable as possible. "
            "Do not preserve the original crop or the subject's old frame occupancy: the subject and original field of view must become proportionally smaller inside the final frame whenever expansion is requested. "
            "Continue the environment, background, clothing, and any anatomically necessary body area naturally through the former image boundaries. "
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
        "key": MAIN_IMAGE_A_PLUS_FEATURE_KEY,
        "name": "主图生A+",
        "summary": "支持自由创作、成品套版替换、整图测试与指定元素替换",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_input_images": MAIN_IMAGE_A_PLUS_MAX_FILES,
        "max_output_images": 1,
        "target_size": MAIN_IMAGE_A_PLUS_TARGET_SIZE,
        "description": "支持自由创作整图直出、成品套版、整图全量替换，以及识别模板元素后按编号上传素材进行指定替换。",
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
        ),
    },
    {
        "key": "amazon_a_plus",
        "name": "亚马逊A+生成",
        "hidden": True,
        "summary": "绿幕生成独立元素并导出分层PSD",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 1,
        "max_output_images": 1,
        "description": "可上传最多 3 张原图，AI 先生成绿幕 A+ 元素底稿，再由代码自动裁切并输出分层 PSD。",
        "default_prompt": (
            "请严格基于上传原图生成一张适用于亚马逊 A+ 模块的可分层元素底稿。"
            "画布背景必须是完全均匀的纯色 #00FF00 绿幕，无渐变、纹理、阴影、地面、反光、边框和水印。"
            "商品主体、标题文字、卖点文字、图标、徽章和装饰素材都必须作为彼此独立的视觉元素放在画布中，"
            "保持最终 A+ 版式所需的大致坐标，但任何两个元素都不能接触、重叠或被阴影连接，元素之间至少保留 32px 纯绿间距。"
            "同一段文字可以作为一个完整元素，但不同文字块必须分开；不要生成跨越多个元素的底板、分栏线或大面积装饰背景。"
            "只使用上传图片中的产品或主体内容，不要替换主体，不要加入无关商品。"
            "必须以原生 4K 高清质量绘制，商品纹理、睫毛丝、人物五官和所有文字边缘都要清晰锐利；"
            "禁止模糊、虚焦、低分辨率、涂抹感、过度降噪、像素化、压缩痕迹和不可辨认的小字。"
            "所有元素边缘必须清晰，不得带绿色描边或绿色光晕。最终只输出 1 张绿幕元素底稿。"
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

FEATURE_DISPLAY_ORDER = {
    "hd_batch": 0,
    "infinite_canvas": 2,
    "background_cutout": 3,
}
FEATURES.sort(
    key=lambda feature: FEATURE_DISPLAY_ORDER.get(
        str(feature.get("key") or "").strip(),
        1,
    )
)


def get_feature_by_key(feature_key: str) -> dict[str, Any] | None:
    normalized_key = str(feature_key or "").strip()
    for feature in FEATURES:
        if str(feature.get("key") or "").strip() == normalized_key:
            return feature
    return None


def get_visible_features() -> list[dict[str, Any]]:
    return [feature for feature in FEATURES if not bool(feature.get("hidden"))]


def get_main_image_a_plus_layout(layout_key: str | None = None) -> dict[str, Any]:
    normalized_key = str(layout_key or "").strip()
    if normalized_key not in MAIN_IMAGE_A_PLUS_LAYOUTS:
        normalized_key = MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY
    layout = dict(MAIN_IMAGE_A_PLUS_LAYOUTS[normalized_key])
    layout["key"] = normalized_key
    layout["target_size"] = tuple(int(value) for value in layout["target_size"])
    layout["section_heights"] = tuple(int(value) for value in layout["section_heights"])
    return layout


def select_main_image_a_plus_safe_aspect_ratio(canvas_size: tuple[int, int]) -> str:
    """Choose the closest native ratio so four-sided crop-free fitting stays minimal."""
    width, height = (int(value) for value in canvas_size)
    if width <= 0 or height <= 0:
        raise ValueError("A+ canvas dimensions must be positive.")
    return select_closest_aspect_ratio((width, height))


def get_main_image_a_plus_template_layout(template_input: Any) -> dict[str, Any]:
    if template_input is None:
        raise RuntimeError("套版替换需要先上传 1 张成品 A+ 模板。")
    template_bytes = get_uploaded_file_bytes(template_input)
    try:
        with Image.open(io.BytesIO(template_bytes)) as image:
            normalized = ImageOps.exif_transpose(image)
            target_width, target_height = normalized.size
    except Exception as exc:
        raise RuntimeError(f"无法读取成品 A+ 模板尺寸：{exc}") from exc
    if (
        target_width <= 0
        or target_height < MAIN_IMAGE_A_PLUS_SECTION_COUNT
        or target_width > AMAZON_A_PLUS_MAX_EDGE
        or target_height > AMAZON_A_PLUS_MAX_EDGE
        or target_width * target_height > AMAZON_A_PLUS_MAX_PIXELS
    ):
        raise RuntimeError(
            "成品 A+ 模板尺寸不受支持：最长边不能超过 10000px，画布不能超过 4000 万像素。"
        )
    base_section_height, remainder = divmod(target_height, MAIN_IMAGE_A_PLUS_SECTION_COUNT)
    section_heights = [base_section_height] * MAIN_IMAGE_A_PLUS_SECTION_COUNT
    section_heights[-1] += remainder
    return {
        "key": "template_original_size",
        "label": f"跟随模板原尺寸｜{target_width}×{target_height}",
        "target_size": (target_width, target_height),
        "section_heights": tuple(section_heights),
        "text_margin_x": max(24, round(target_width * 0.08)),
        "text_margin_y": max(20, round(min(section_heights) * 0.1)),
    }


def normalize_main_image_a_plus_mode(mode: str | None = None) -> str:
    normalized_mode = str(mode or "").strip()
    if normalized_mode not in MAIN_IMAGE_A_PLUS_MODE_LABELS:
        return MAIN_IMAGE_A_PLUS_MODE_FREE
    return normalized_mode


def get_main_image_a_plus_template_signature(template_input: Any) -> str:
    template_bytes = get_uploaded_file_bytes(template_input)
    return hashlib.sha1(template_bytes).hexdigest()[:16] if template_bytes else ""


def normalize_main_image_a_plus_element_bbox(
    raw_bbox: Any,
    image_size: tuple[int, int],
) -> list[int] | None:
    if isinstance(raw_bbox, dict):
        left = raw_bbox.get("left", raw_bbox.get("x", 0))
        top = raw_bbox.get("top", raw_bbox.get("y", 0))
        if "right" in raw_bbox or "bottom" in raw_bbox:
            right = raw_bbox.get("right", left)
            bottom = raw_bbox.get("bottom", top)
        else:
            right = float(left or 0) + float(raw_bbox.get("width", raw_bbox.get("w", 0)) or 0)
            bottom = float(top or 0) + float(raw_bbox.get("height", raw_bbox.get("h", 0)) or 0)
        values = [left, top, right, bottom]
    elif isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
        values = list(raw_bbox[:4])
    else:
        return None
    try:
        left, top, right, bottom = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    max_value = max(abs(left), abs(top), abs(right), abs(bottom))
    if max_value <= 1.01:
        left, top, right, bottom = [value * 1000 for value in (left, top, right, bottom)]
    elif max_value > 1000:
        image_width, image_height = image_size
        if image_width <= 0 or image_height <= 0:
            return None
        left = left / image_width * 1000
        right = right / image_width * 1000
        top = top / image_height * 1000
        bottom = bottom / image_height * 1000
    left, right = sorted((max(0, min(1000, left)), max(0, min(1000, right))))
    top, bottom = sorted((max(0, min(1000, top)), max(0, min(1000, bottom))))
    if right - left < 5 or bottom - top < 5:
        return None
    return [round(left), round(top), round(right), round(bottom)]


def parse_main_image_a_plus_element_analysis(
    response_text: str,
    image_size: tuple[int, int],
) -> list[dict[str, Any]]:
    raw_text = str(response_text or "").strip()
    if not raw_text:
        raise RuntimeError("元素识别没有返回结果，请重试。")
    candidates = [raw_text]
    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text, re.IGNORECASE)
    if fenced_match:
        candidates.insert(0, fenced_match.group(1).strip())
    object_start, object_end = raw_text.find("{"), raw_text.rfind("}")
    if object_start >= 0 and object_end > object_start:
        candidates.append(raw_text[object_start : object_end + 1])
    list_start, list_end = raw_text.find("["), raw_text.rfind("]")
    if list_start >= 0 and list_end > list_start:
        candidates.append(raw_text[list_start : list_end + 1])
    payload: Any = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            break
        except Exception:
            continue
    if payload is None:
        raise RuntimeError("元素识别结果格式不完整，请重新识别。")
    raw_elements = payload.get("elements") if isinstance(payload, dict) else payload
    if not isinstance(raw_elements, list):
        raise RuntimeError("元素识别结果中没有可用的元素列表，请重新识别。")
    elements: list[dict[str, Any]] = []
    for raw_element in raw_elements:
        if not isinstance(raw_element, dict):
            continue
        raw_regions = (
            raw_element.get("regions")
            or raw_element.get("boxes")
            or raw_element.get("bboxes")
            or raw_element.get("bbox")
            or []
        )
        if isinstance(raw_regions, dict) or (
            isinstance(raw_regions, (list, tuple))
            and len(raw_regions) >= 4
            and not isinstance(raw_regions[0], (list, tuple, dict))
        ):
            raw_regions = [raw_regions]
        regions = [
            bbox
            for bbox in (
                normalize_main_image_a_plus_element_bbox(raw_bbox, image_size)
                for raw_bbox in list(raw_regions or [])
            )
            if bbox is not None
        ]
        if not regions:
            continue
        element_name = str(
            raw_element.get("name")
            or raw_element.get("label")
            or raw_element.get("type")
            or "可替换元素"
        ).strip()[:48]
        element_type = str(raw_element.get("type") or "other").strip().lower()[:32]
        description = str(raw_element.get("description") or "").strip()[:240]
        replacement_hint = str(
            raw_element.get("replacement_hint")
            or raw_element.get("hint")
            or description
        ).strip()[:240]
        elements.append(
            {
                "id": len(elements) + 1,
                "name": element_name or f"可替换元素 {len(elements) + 1}",
                "type": element_type or "other",
                "description": description,
                "replacement_hint": replacement_hint,
                "regions": regions,
            }
        )
        if len(elements) >= MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS:
            break
    if not elements:
        raise RuntimeError("没有识别到可替换元素，请确认上传的是完整 A+ 成品图后重试。")
    return elements


def analyze_main_image_a_plus_elements(template_input: Any) -> list[dict[str, Any]]:
    if template_input is None:
        raise RuntimeError("请先上传 1 张完整的成品 A+ 示例图。")
    image_size = get_uploaded_input_dimensions(template_input)
    analysis_prompt = (
        "你是电商 A+ 视觉模板元素分析器。请完整识别这张成品 A+ 长图中所有可以用另一张图片替换的前景内容，"
        "包括模特或人物、商品、包装、Logo/品牌、独立文案块、参数标签、徽章图标、使用效果、局部特写和带有商品语义的装饰。"
        "不要把纯背景、底层色块、结构边框、留白、分区和整体版式列为可替换元素。"
        "语义相同且应该使用同一份替换素材的重复内容合并成一个元素组，并在 regions 中列出它的全部出现位置；"
        "语义不同的产品、人物、文字块或细节必须拆成不同元素组。请覆盖整张长图，不要只分析首屏。"
        f"最多输出 {MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS} 个最完整的元素组。所有坐标都使用 0 到 1000 的归一化整数，"
        "格式为 [left, top, right, bottom]。只返回严格 JSON，不要 Markdown，不要解释。"
        "JSON 格式：{\"elements\":[{\"name\":\"主模特\",\"type\":\"model\","
        "\"description\":\"模板中人物主体\",\"replacement_hint\":\"上传要替换进去的新模特图\","
        "\"regions\":[[100,50,700,420]]}]}"
    )
    response = call_openrouter(
        model=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        prompt=analysis_prompt,
        uploaded_files=[template_input],
        output_mode="text",
        aspect_ratio=DEFAULT_ASPECT_RATIO,
    )
    return parse_main_image_a_plus_element_analysis(
        str(response.get("text") or ""),
        image_size,
    )


def parse_main_image_a_plus_replacement_matches(
    response_text: str,
    elements: list[dict[str, Any]],
    replacement_count: int,
    replacement_sizes: list[tuple[int, int]] | None = None,
) -> list[dict[str, Any]]:
    raw_text = str(response_text or "").strip()
    if not raw_text:
        raise RuntimeError("替换素材识别没有返回结果，请重试。")
    candidates = [raw_text]
    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text, re.IGNORECASE)
    if fenced_match:
        candidates.insert(0, fenced_match.group(1).strip())
    object_start, object_end = raw_text.find("{"), raw_text.rfind("}")
    if object_start >= 0 and object_end > object_start:
        candidates.append(raw_text[object_start : object_end + 1])
    payload: Any = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            break
        except Exception:
            continue
    if payload is None:
        raise RuntimeError("替换素材识别结果格式不完整，请重新识别。")
    raw_matches = payload.get("matches") if isinstance(payload, dict) else payload
    if not isinstance(raw_matches, list):
        raise RuntimeError("替换素材识别结果中没有匹配清单，请重新识别。")
    valid_element_ids = {
        int(element.get("id") or index + 1)
        for index, element in enumerate(elements)
    }
    best_matches: dict[int, dict[str, Any]] = {}
    for raw_match in raw_matches:
        if not isinstance(raw_match, dict):
            continue
        try:
            element_id = int(raw_match.get("element_id") or raw_match.get("id") or 0)
            image_index = int(raw_match.get("image_index") or raw_match.get("reference_index") or 0)
        except (TypeError, ValueError):
            continue
        if element_id not in valid_element_ids or image_index < 1 or image_index > replacement_count:
            continue
        try:
            confidence = float(raw_match.get("confidence") or 0.5)
        except (TypeError, ValueError):
            confidence = 0.5
        if confidence > 1.0:
            confidence = confidence / 100.0
        confidence = max(0.0, min(1.0, confidence))
        replacement_size = (
            replacement_sizes[image_index - 1]
            if replacement_sizes and image_index <= len(replacement_sizes)
            else (1000, 1000)
        )
        raw_crop_box = (
            raw_match.get("crop_box")
            or raw_match.get("source_region")
            or raw_match.get("bbox")
            or raw_match.get("region")
        )
        crop_box = normalize_main_image_a_plus_element_bbox(
            raw_crop_box,
            replacement_size,
        )
        normalized_match = {
            "element_id": element_id,
            "image_index": image_index,
            "confidence": confidence,
            "crop_box": crop_box or [],
            "reason": str(raw_match.get("reason") or "").strip()[:240],
            "detected_content": str(
                raw_match.get("detected_content") or raw_match.get("content") or ""
            ).strip()[:160],
        }
        current_match = best_matches.get(element_id)
        if current_match is None or confidence > float(current_match.get("confidence") or 0):
            best_matches[element_id] = normalized_match
    return [best_matches[element_id] for element_id in sorted(best_matches)]


def analyze_main_image_a_plus_replacement_matches(
    template_input: Any,
    elements: list[dict[str, Any]],
    replacement_inputs: list[Any],
) -> list[dict[str, Any]]:
    if template_input is None or not elements:
        raise RuntimeError("请先上传 A+ 模板并完成元素识别。")
    if not replacement_inputs:
        raise RuntimeError("请先上传至少 1 张用于替换的新素材图。")
    element_summary = "\n".join(
        (
            f"#{int(element.get('id') or index + 1)}｜名称：{str(element.get('name') or '元素')}｜"
            f"类型：{str(element.get('type') or 'other')}｜说明："
            f"{str(element.get('description') or element.get('replacement_hint') or '')}"
        )
        for index, element in enumerate(elements)
    )
    prompt = (
        "你是电商 A+ 替换素材匹配器。输入图片第 1 张是带有待替换元素的完整 A+ 模板，"
        "从输入图片第 2 张开始依次是用户上传的新素材图；返回 JSON 中的 image_index 从 1 开始，"
        "其中 image_index=1 对应输入图片第 2 张。请识别每张新素材里真实存在的人物、产品、包装、"
        "品牌 Logo、文字、参数、效果图和细节，并把它匹配到下面最合适的模板编号。"
        "一张素材同时包含多类有效内容时可以匹配多个编号；一个编号只能选择最合适的一张素材。"
        "每条匹配必须同时返回 crop_box，表示该替换元素在对应新素材图中的紧致范围，坐标使用 0 到 1000 的"
        "归一化整数 [left,top,right,bottom]；crop_box 只能框住真正要替换的产品、人物、Logo、文字或细节，"
        "尽量排除无关背景、其他商品、其他人物和整张海报。若一张素材匹配多个编号，必须为每个编号分别给出"
        "各自的 crop_box。无法准确定位替换部分时不要返回该匹配，禁止用整张图片范围代替。"
        "不要因为颜色相似就误配，不能识别清楚的编号不要返回。只返回严格 JSON，不要 Markdown。\n\n"
        f"模板元素清单：\n{element_summary}\n\n"
        "JSON 格式：{\"matches\":[{\"element_id\":1,\"image_index\":2,"
        "\"confidence\":0.92,\"detected_content\":\"白色假睫毛包装盒\","
        "\"crop_box\":[120,180,860,790],"
        "\"reason\":\"素材中的包装对应模板产品包装槽位\"}]}"
    )
    response = call_openrouter(
        model=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        prompt=prompt,
        uploaded_files=[template_input, *replacement_inputs],
        output_mode="text",
        aspect_ratio=DEFAULT_ASPECT_RATIO,
    )
    return parse_main_image_a_plus_replacement_matches(
        str(response.get("text") or ""),
        elements,
        len(replacement_inputs),
        [get_uploaded_input_dimensions(item) for item in replacement_inputs],
    )


def crop_main_image_a_plus_replacement_input(
    replacement_input: Any,
    crop_box: Any,
    element_id: int,
    element_name: str,
) -> dict[str, Any] | None:
    """Return only the matched replacement element, never the full source artwork."""
    try:
        source_bytes = get_uploaded_file_bytes(replacement_input)
        with Image.open(io.BytesIO(source_bytes)) as source_image:
            source_image = ImageOps.exif_transpose(source_image)
            source_width, source_height = source_image.size
            normalized_box = normalize_main_image_a_plus_element_bbox(
                crop_box,
                (source_width, source_height),
            )
            if normalized_box is None:
                return None
            left_n, top_n, right_n, bottom_n = normalized_box
            left = math.floor(left_n / 1000 * source_width)
            top = math.floor(top_n / 1000 * source_height)
            right = math.ceil(right_n / 1000 * source_width)
            bottom = math.ceil(bottom_n / 1000 * source_height)
            crop_width = max(right - left, 1)
            crop_height = max(bottom - top, 1)
            padding = max(2, round(max(crop_width, crop_height) * 0.035))
            left = max(0, left - padding)
            top = max(0, top - padding)
            right = min(source_width, right + padding)
            bottom = min(source_height, bottom + padding)
            if right - left < 4 or bottom - top < 4:
                return None
            cropped = source_image.crop((left, top, right, bottom))
            if cropped.size == source_image.size:
                return None
            if cropped.mode not in {"RGB", "RGBA"}:
                cropped = cropped.convert("RGBA" if "A" in cropped.getbands() else "RGB")
            output = io.BytesIO()
            cropped.save(output, format="PNG", optimize=True)
    except Exception:
        return None
    safe_name = sanitize_file_name(str(element_name or f"element_{element_id}"))
    return {
        "data": output.getvalue(),
        "name": f"recommended_{int(element_id)}_{safe_name}_crop.png",
        "type": "image/png",
    }


def find_main_image_a_plus_element_at_point(
    elements: list[dict[str, Any]],
    point: tuple[int, int],
) -> dict[str, Any] | None:
    point_x, point_y = point
    candidates: list[tuple[float, dict[str, Any]]] = []
    for element in elements:
        for region in list(element.get("regions") or []):
            if not isinstance(region, (list, tuple)) or len(region) < 4:
                continue
            left, top, right, bottom = [float(value) for value in region[:4]]
            if left <= point_x <= right and top <= point_y <= bottom:
                candidates.append((max(1.0, (right - left) * (bottom - top)), element))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def analyze_main_image_a_plus_element_at_point(
    template_input: Any,
    point: tuple[int, int],
    existing_elements: list[dict[str, Any]],
) -> dict[str, Any]:
    if template_input is None:
        raise RuntimeError("请先上传完整 A+ 模板。")
    if len(existing_elements) >= MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS:
        raise RuntimeError(f"当前最多支持 {MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS} 个元素组。")
    point_x, point_y = point
    existing_summary = "；".join(
        f"#{int(element.get('id') or index + 1)} {str(element.get('name') or '元素')}"
        for index, element in enumerate(existing_elements)
    )
    prompt = (
        "你是电商 A+ 模板补漏识别器。用户点击了完整模板中的一个漏识别元素，点击坐标使用 0 到 1000 "
        f"归一化坐标，位置为 ({point_x}, {point_y})。请识别点击位置正下方或距离最近的完整前景元素，"
        "判断它是人物、产品、包装、品牌 Logo、独立文字块、参数、徽章、效果图还是细节特写，"
        "并返回该语义元素的完整边界；如果同一元素在模板中重复出现，请在 regions 中返回全部出现位置。"
        "不要把背景、底层色块、结构边框或整个分区识别成元素。只返回 1 个元素的严格 JSON，不要 Markdown。"
        f"已经识别的元素为：{existing_summary or '无'}。避免重复返回已经识别的元素。"
        "JSON 格式：{\"elements\":[{\"name\":\"产品包装\",\"type\":\"package\","
        "\"description\":\"点击位置的商品包装\",\"replacement_hint\":\"上传新产品包装图\","
        "\"regions\":[[100,100,450,380]]}]}"
    )
    response = call_openrouter(
        model=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        prompt=prompt,
        uploaded_files=[template_input],
        output_mode="text",
        aspect_ratio=DEFAULT_ASPECT_RATIO,
    )
    detected = parse_main_image_a_plus_element_analysis(
        str(response.get("text") or ""),
        get_uploaded_input_dimensions(template_input),
    )
    if not detected:
        raise RuntimeError("点击位置没有识别到可替换元素，请点击元素主体后重试。")
    new_element = dict(detected[0])
    new_element["id"] = max(
        [int(element.get("id") or 0) for element in existing_elements] or [0]
    ) + 1
    return new_element


def consume_main_image_a_plus_manual_point(
    template_signature: str,
) -> tuple[int, int] | None:
    raw_payload = str(
        st.query_params.get(MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY, "")
    ).strip()
    if not raw_payload:
        return None
    clear_query_param(MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY)
    try:
        payload = json.loads(raw_payload)
        if str(payload.get("template_signature") or "") != str(template_signature or ""):
            return None
        point_x = max(0, min(1000, int(round(float(payload.get("x") or 0)))))
        point_y = max(0, min(1000, int(round(float(payload.get("y") or 0)))))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return point_x, point_y


def build_main_image_a_plus_element_preview(
    template_input: Any,
    elements: list[dict[str, Any]],
) -> str:
    template_bytes = get_uploaded_file_bytes(template_input)
    try:
        with Image.open(io.BytesIO(template_bytes)) as image:
            preview = ImageOps.exif_transpose(image).convert("RGBA")
            preview.thumbnail((1600, 2400), Image.Resampling.LANCZOS)
    except Exception as exc:
        raise RuntimeError(f"无法生成元素编号预览：{exc}") from exc
    overlay = Image.new("RGBA", preview.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    palette = (
        (126, 96, 255, 255),
        (0, 190, 170, 255),
        (255, 146, 43, 255),
        (232, 73, 135, 255),
        (55, 145, 255, 255),
        (158, 197, 61, 255),
    )
    line_width = max(2, round(min(preview.size) * 0.004))
    badge_padding = max(6, line_width * 2)
    badge_font_size = max(20, min(58, round(min(preview.size) * 0.035)))
    badge_font = None
    for font_path in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/msyhbd.ttc",
        "DejaVuSans-Bold.ttf",
    ):
        try:
            badge_font = ImageFont.truetype(font_path, badge_font_size)
            break
        except (OSError, ValueError):
            continue
    if badge_font is None:
        badge_font = ImageFont.load_default()
    for element_index, element in enumerate(elements):
        color = palette[element_index % len(palette)]
        element_id = int(element.get("id") or element_index + 1)
        for region_index, region in enumerate(list(element.get("regions") or [])):
            if not isinstance(region, (list, tuple)) or len(region) < 4:
                continue
            left = round(float(region[0]) / 1000 * preview.width)
            top = round(float(region[1]) / 1000 * preview.height)
            right = round(float(region[2]) / 1000 * preview.width)
            bottom = round(float(region[3]) / 1000 * preview.height)
            region_fill = (color[0], color[1], color[2], 30)
            draw.rectangle(
                (left, top, right, bottom),
                fill=region_fill,
                outline=color,
                width=line_width,
            )
            label = f"#{element_id}"
            text_box = draw.textbbox((0, 0), label, font=badge_font)
            text_width = text_box[2] - text_box[0]
            text_height = text_box[3] - text_box[1]
            badge_width = text_width + badge_padding * 2
            badge_height = text_height + badge_padding * 2
            badge_left = max(0, min(preview.width - badge_width, left))
            badge_top = max(0, top - badge_height - line_width)
            if badge_top == 0 and top < badge_height + line_width:
                badge_top = min(preview.height - badge_height, top + line_width)
            draw.rounded_rectangle(
                (badge_left, badge_top, badge_left + badge_width, badge_top + badge_height),
                radius=max(4, badge_padding),
                fill=color,
            )
            draw.text(
                (badge_left + badge_padding, badge_top + badge_padding - text_box[1]),
                label,
                fill=(255, 255, 255, 255),
                font=badge_font,
            )
            if region_index == 0:
                draw.line(
                    (
                        badge_left + badge_width / 2,
                        badge_top + badge_height,
                        (left + right) / 2,
                        (top + bottom) / 2,
                    ),
                    fill=color,
                    width=max(1, line_width // 2),
                )
    annotated = Image.alpha_composite(preview, overlay).convert("RGB")
    output = io.BytesIO()
    annotated.save(output, format="JPEG", quality=90, optimize=True)
    return image_bytes_to_data_url(output.getvalue(), "image/jpeg")


def render_main_image_a_plus_manual_element_picker(
    annotated_preview: str,
    template_signature: str,
    component_key: str,
) -> None:
    safe_component_key = re.sub(r"[^A-Za-z0-9_-]+", "_", str(component_key or "picker"))
    preview_json = json.dumps(str(annotated_preview or ""), ensure_ascii=False)
    signature_json = json.dumps(str(template_signature or ""), ensure_ascii=False)
    query_key_json = json.dumps(MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY)
    html_content = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        html, body {{ margin: 0; padding: 0; background: transparent; color: #eef3ff; font-family: Arial, sans-serif; }}
        .picker-shell {{ position: relative; height: 720px; overflow: auto; border-radius: 14px; border: 1px solid rgba(139, 156, 255, .26); background: rgba(5, 12, 27, .72); }}
        .picker-tip {{ position: sticky; top: 0; z-index: 3; padding: 10px 12px; background: rgba(9, 18, 39, .94); color: #dfe6ff; font-size: 13px; line-height: 1.5; border-bottom: 1px solid rgba(139, 156, 255, .18); }}
        .picker-image-wrap {{ display: flex; justify-content: center; padding: 12px; }}
        .picker-image {{ display: block; width: min(100%, 760px); height: auto; cursor: crosshair; border-radius: 8px; user-select: none; -webkit-user-drag: none; }}
        .picker-image:hover {{ box-shadow: 0 0 0 2px rgba(126, 96, 255, .85); }}
        .picker-loading {{ position: fixed; inset: 0; display: none; align-items: center; justify-content: center; background: rgba(3, 8, 22, .72); z-index: 5; font-weight: 700; }}
      </style>
    </head>
    <body>
      <div class="picker-shell" id="picker-shell-{safe_component_key}">
        <div class="picker-tip" id="picker-tip-{safe_component_key}">点击机器漏掉的元素主体，系统会按点击位置补充识别并生成一个新编号。已带彩色编号的区域无需重复点击。</div>
        <div class="picker-image-wrap"><img class="picker-image" id="picker-image-{safe_component_key}" alt="点击补漏" /></div>
      </div>
      <div class="picker-loading" id="picker-loading-{safe_component_key}">正在定位元素，请稍候…</div>
      <script>
        (() => {{
          const image = document.getElementById("picker-image-{safe_component_key}");
          const loading = document.getElementById("picker-loading-{safe_component_key}");
          const tip = document.getElementById("picker-tip-{safe_component_key}");
          const hostWindow = window.parent;
          image.src = {preview_json};
          image.addEventListener("click", (event) => {{
            const rect = image.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            const x = Math.max(0, Math.min(1000, Math.round((event.clientX - rect.left) / rect.width * 1000)));
            const y = Math.max(0, Math.min(1000, Math.round((event.clientY - rect.top) / rect.height * 1000)));
            const payload = JSON.stringify({{
              template_signature: {signature_json},
              x,
              y
            }});
            const nextUrl = new URL(hostWindow.location.href);
            nextUrl.searchParams.set({query_key_json}, payload);
            loading.style.display = "flex";
            hostWindow.location.replace(nextUrl.toString());
            window.setTimeout(() => {{
              loading.style.display = "none";
              if (tip) tip.textContent = "点击已提交；如果页面没有更新，请再点击一次元素主体。";
            }}, 6000);
          }});
        }})();
      </script>
    </body>
    </html>
    """
    st.iframe(html_content, height=740, width="stretch")


def build_main_image_a_plus_element_replacement_notes(
    layout: dict[str, Any],
    detected_element_count: int,
    replacements: list[dict[str, Any]],
) -> str:
    target_width, target_height = layout["target_size"]
    selected_names = "、".join(
        f"#{int(item.get('id') or index + 1)} {str(item.get('name') or '元素')}"
        for index, item in enumerate(replacements)
    )
    return (
        f"系统共识别 {detected_element_count} 个可替换元素组，本次已指定 {len(replacements)} 个：{selected_names}。"
        f"最终只生成一张 {target_width}×{target_height}px 完整 A+ 长图，尺寸和版式严格跟随模板。"
        "只替换已上传对应图片的编号；没有上传图片的编号及所有未编号内容必须保持模板原样。"
        "每个编号的替换图只能进入该编号的全部标注区域，不能用于其他编号，不能改变背景、版式或未选元素。"
        "禁止拆段、拼接、多图输出、顺带重绘、扩大修改范围、遗漏同编号的重复出现位置或保留旧元素残影。"
    )


def build_main_image_a_plus_element_replacement_prompt(
    full_prompt: str,
    layout: dict[str, Any],
    replacements: list[dict[str, Any]],
) -> str:
    target_width, target_height = layout["target_size"]
    mapping_lines: list[str] = []
    for reference_index, replacement in enumerate(replacements, start=2):
        element_id = int(replacement.get("id") or reference_index - 1)
        name = str(replacement.get("name") or f"元素 {element_id}").strip()
        element_type = str(replacement.get("type") or "other").strip()
        regions = list(replacement.get("regions") or [])
        region_text = "、".join(
            f"[{int(box[0])},{int(box[1])},{int(box[2])},{int(box[3])}]"
            for box in regions
            if isinstance(box, (list, tuple)) and len(box) >= 4
        )
        mapping_lines.append(
            f"输入图片第 {reference_index} 张 → 编号 #{element_id}“{name}”（{element_type}），"
            f"只替换归一化区域 {region_text or '按模板识别位置'}。"
        )
    return (
        f"{str(full_prompt or '').strip()}\n\n"
        "指定元素映射执行指令：输入图片第 1 张是未标注的完整 A+ 模板；后续图片与编号严格一一对应。\n"
        + "\n".join(mapping_lines)
        + f"\n一次生成 1 张完整的 {target_width}×{target_height}px 成品。"
        "坐标采用模板宽高各自 0 到 1000 的归一化范围。只修改上述编号区域，同编号有多个区域时全部替换。"
        "模板中未列出的产品、品牌、Logo、模特、文字、参数、图标、背景、装饰和版式必须保持不变。"
        "禁止把第 2 张之后的素材混用、错位、跨编号扩散或添加到未指定区域。"
        "输出前逐项核对映射，确保选中元素全部替换、未选元素完全未改。只输出这一张完整成品。"
    )


def build_main_image_a_plus_layout_notes(layout_key: str, image_count: int) -> str:
    layout = get_main_image_a_plus_layout(layout_key)
    target_width, target_height = layout["target_size"]
    return (
        f"当前共上传 {image_count} 张商品主图，图片顺序即参考优先级。"
        "第 1 张必须作为核心主图，严格锁定商品身份、品牌、包装、颜色、材质、结构和比例；"
        "第 2 张至最后一张只用于补充商品角度、局部细节、套装内容、使用方式和可用场景。"
        f"当前选择的版式为“{layout['label']}”。"
        f"最终成品必须是一张 {target_width}×{target_height}px 的完整竖版 A+ 宣传长图；"
        "画布尺寸只用于控制最终输出，画面中绝不能出现尺寸数字、坐标、距离、辅助线或分段说明。"
        "整张长图从上到下大体形成四个阅读阶段：模特与品牌主视觉、核心卖点与关键细节、"
        "使用场景或工艺表现、套装包装与品牌收尾。"
        "四个阶段只代表信息节奏，不按固定像素、固定距离或等高方框划分，也不要求内容严格待在各自范围内。"
        "首屏必须是完整的商业主视觉，而不是素材陈列区：如果上传参考图中包含多个模特，只挑选一位最清晰、最适合商业展示的模特作为唯一主视觉核心；如果没有模特，则以核心商品为唯一主视觉且不得虚构人物。"
        "选中的唯一模特必须放在整张长图最上方的首屏区域，并处于画面最上层和视觉最前景；保持身份、脸部、发型、姿态与服饰真实一致，禁止再出现第二位模特或在下方重复该模特；商品、文字、Logo、色块、光效和装饰均不得遮挡模特的脸、眼睛、头发轮廓、身体主体或关键服饰。"
        "参考图只是可选择的素材池，不要求全部出现在首屏；必须主动取舍素材，使用专业网格、大小对比、前中后景、光影、留白和品牌文字层级完成高级海报式构图。"
        "严禁在首屏中直接堆叠多个产品抠图、重复人物、重复包装、大量小图、标签和文字块；严禁做成拼贴、产品清单、九宫格或把所有参考图平铺进去。"
        "不要绘制分割线、边框、卡片底板、硬切色块或明显的四块拼接结构；四个阶段之间必须使用构图、景深、光影、色彩和视觉动线自然衔接。"
        "人物、商品、包装、场景、光影、色块、纹理、装饰、大标题图形和其他非正文视觉元素允许跨越相邻阶段，"
        "可以自然遮挡、叠压和延伸，形成一个连续整体，但不能变成凌乱的九宫格或多图拼贴。"
        "只允许展示上传图片中真实存在的商品、配件、包装和信息，不得增加无关商品，不得改变品牌与商品外观。"
        "不得编造参数、认证、功效、促销价格或承诺；补充宣传要求与图片冲突时，以主图中的真实商品信息为准。"
        "背景、场景、色块、纹理和装饰必须满版延伸到画布四边，不得生成边框、白边、黑边、模糊边带或可见留白。"
        "标题、卖点、参数、说明文字和可读 Logo 必须在上、下、左、右四条画布外边缘保留自然可读空间，不显示任何安全距离。"
        "文字可以跟随整体构图跨越概念阶段，但每一段完整文字都不能被画布边缘切断，不能出现半个字、缺字或被截断的行。"
        "禁止在画布顶部、底部、左侧或右侧放置贴边文字；每个标题、正文、参数、品牌名和可读 Logo 必须完整保留字高、行高与四周呼吸空间，必要时缩小字号、自动换行或向画面内部移动。"
        "最终规格适配必须完整保留原生画面的上下左右四边，不允许从任何一侧裁切人物、商品、文字、Logo、背景或装饰。"
        "必须使用原生 4K 高清细节，商品纹理、边缘、Logo、包装字和宣传字必须清晰锐利、可辨认。"
        "严禁乱码、错别字、模糊、虚焦、涂抹、过度柔化、像素化、压缩痕迹、重复主体和明显 AI 伪影。"
        "必须只调用一次整图生成并直接得到一张连续长图，禁止内部拆段、逐段生成、后期拼接或覆盖原图；不要输出绿幕、透明图、草图、线框或多张候选版式。"
    )


def build_main_image_a_plus_free_prompt(
    full_prompt: str,
    layout: dict[str, Any],
) -> str:
    target_width, target_height = (int(value) for value in layout["target_size"])
    request_aspect_ratio = select_main_image_a_plus_safe_aspect_ratio((target_width, target_height))
    no_crop_note = (
        f"原生生成使用最接近成品的 {request_aspect_ratio} 画幅，最终适配不会从上、下、左、右任何一侧裁切；"
        "原生画面的全部像素都会保留并完整映射到成品，因此四边都不是可牺牲区域。"
        "所有人物、商品、Logo、完整文字和关键装饰必须完整位于画布内部，背景与场景自然满版延续到四边。"
    )
    return (
        f"{str(full_prompt or '').strip()}\n\n"
        "自由创作整图直出执行指令：必须把全部参考图理解为同一商品与品牌的素材库，"
        f"在一次模型生成中直接输出 1 张完整的 {target_width}×{target_height}px A+ 宣传长图。"
        "禁止把画布拆成四段或多个模块分别生成，禁止调用多次生成后拼接，禁止复制粘贴原图矩形，"
        "禁止出现接缝、断层、重复背景、突然换场、卡片边界、等高分块或四张图上下排列的视觉痕迹。"
        "从顶部到底部必须共享同一套品牌色、统一场景空间、材质、透视、光源、景深、纹理和设计语言，"
        "通过主体跨区、背景连续延伸、光影渐变、前后景叠压和视觉动线，让卖点内容自然融合为一个整体。"
        "四个内容阶段只负责阅读节奏，任何人物、商品、场景、色块和装饰都可以跨越阶段，不能绘制阶段边框或分割线。"
        "首屏必须有商业广告主视觉和清晰焦点，不能把上传图片缩小后平铺、堆叠或做成素材清单。"
        "如果上传素材中有多张模特图，只挑选一位最清晰、最适合商业展示的模特，放在整张图最上方的首屏并置于最上层；"
        "禁止出现第二位模特，禁止在中段或底部再次重复同一模特，任何元素都不能遮挡模特，商品、文字和装饰尤其不能遮挡选中的模特；"
        "如果所有上传素材都没有模特，则以核心商品为首屏主视觉，不得凭空生成陌生人物。"
        "所有标题、正文、参数、品牌名和可读 Logo 必须逐字完整、清晰可读，上下左右四边都要保留完整字高、行高和自然呼吸空间；"
        "禁止半个字、缺字、断行裁切、文字或主体超出画布、紧贴任何一侧边缘，空间不足时必须缩小字号、换行、缩小主体或向内移动。"
        f"{no_crop_note}"
        "最终只返回这一张融合完成的商业级 A+ 成品，不返回局部图、过程图、拼接图或候选版本。"
    )


def build_main_image_a_plus_section_prompt(
    full_prompt: str,
    layout: dict[str, Any],
    section_index: int,
    has_previous_section_reference: bool = False,
    continuity_reference_role: str = "",
) -> str:
    target_width, target_height = layout["target_size"]
    section_heights = layout["section_heights"]
    section_height = int(section_heights[section_index])
    purpose = MAIN_IMAGE_A_PLUS_SECTION_PURPOSES[section_index]
    hero_design_rules = (
        "首屏商业主视觉专项规则：本段必须以上传参考图中的一位模特为唯一视觉主体，模特占据首屏最主要面积与最高视觉权重；商品、品牌和场景只作为辅助信息。"
        "模特必须位于最上层、最前景，不能被任何商品、包装、文字、Logo、标签、色块、光效、纹理或装饰覆盖；脸部、眼睛、头发轮廓、身体主体和关键服饰必须完整清晰。"
        "如果需要产生遮挡关系，只能由模特遮挡后方的商品、文字或装饰，不能反向遮挡模特。"
        "必须主动筛选参考素材，不要求全部使用；通过专业网格、非对称平衡、主次比例、前中后景、自然遮挡、留白、光影和品牌色建立高级广告海报感。"
        "商品、人物、标题和卖点必须形成清楚的视觉层级，不能彼此争抢焦点。"
        "禁止把多个商品抠图、人物、包装、小图、图标、标签和文字块直接向画面中堆叠；禁止重复主体、素材平铺、拼贴、九宫格、产品清单和拥挤排版。"
        if section_index == 0
        else ""
    )
    if has_previous_section_reference and continuity_reference_role == "style_anchor":
        continuation_rules = (
            "输入图片中的最后一张是已生成的首屏风格锚点，不是当前片段的内容素材。"
            "必须锁定其中的品牌色、字体气质、商品表现、场景材质、光影方向、景深、纹理、装饰语言和整体商业质感，"
            "让当前片段看起来属于同一张连续长图；不要复制首屏构图，不要重复首屏主体，也不要把锚点当成新商品参考。"
            "当前片段顶部和底部都要使用可自然延续的背景、色彩、光影和视觉动线，避免独立卡片感。"
        )
    elif has_previous_section_reference:
        continuation_rules = (
            "输入图片中的最后一张是紧邻当前画面上方的已生成连续片段，只用于衔接参考；其余输入图片仍是商品内容参考图。"
            "必须观察上一片段底部的背景、主体边缘、场景透视、色彩、光影、纹理、装饰和视觉动线，"
            "从当前片段顶部无痕延续下来；如果上一片段有商品、人物、光影、色块或装饰伸向底边，应在当前片段中自然接续，不能突然切断或重新开始。"
            "不要复刻整张上一片段，也不要把上一片段当成新的商品参考。"
        )
    else:
        continuation_rules = (
            "这是整张长图的起始片段，需要为后续内容保留自然向下延伸的场景、光影、色彩和视觉动线。"
            if section_index == 0
            else "当前没有额外连续片段参考，必须严格依照总提示中的品牌色、商品身份、字体气质、光影方向和场景语言完成本段，并让上下边缘保持可自然延续。"
        )
    return (
        f"{str(full_prompt or '').strip()}\n\n"
        "连续长图生成执行指令：系统会依次制作连续画面片段并组合为一张长图，片段不是独立卡片或独立版块。"
        f"本次制作第 {section_index + 1} 个连续画面片段，当前信息重点大体为“{purpose}”，但相邻阶段的内容可以进入本片段。"
        f"内部输出尺寸必须为 {target_width}×{section_height}px，并将组成 {target_width}×{target_height}px 的成品；"
        "这些尺寸仅用于系统输出控制，绝不能作为文字、标尺、坐标或说明出现在画面里。"
        f"{hero_design_rules}"
        f"{continuation_rules}"
        "不要绘制上下分界线、边框、独立卡片、硬切背景或明显的模块边界。"
        "人物、商品、场景、光影、色块、纹理、装饰和大图形都可以延伸到片段顶部或底部，以便跨片段形成连续视觉。"
        "画面、背景、色块和场景必须铺满四边，不要白边、黑边或透明边缘。"
        "完整文案、参数与可读 Logo 不要压在实际上下拼接边缘，避免在合成时被切断；画布左右边缘只需保留自然可读空间，不显示距离标记。"
        "保持整张长图统一的商品身份、品牌色、字体风格、光影方向、透视关系和商业质感。"
        "只输出当前连续画面片段，不要输出辅助线、版式说明或候选方案。"
    )


def build_main_image_a_plus_template_notes(layout_or_key: dict[str, Any] | str, image_count: int) -> str:
    layout = (
        dict(layout_or_key)
        if isinstance(layout_or_key, dict)
        else get_main_image_a_plus_layout(layout_or_key)
    )
    target_width, target_height = layout["target_size"]
    section_heights = layout["section_heights"]
    text_margin_x = int(layout.get("text_margin_x") or 0)
    text_margin_y = int(layout.get("text_margin_y") or 0)
    return (
        f"当前套版任务包含 1 张完整成品 A+ 模板和 {image_count} 张内容参考图。"
        "模板图不提供可复用的品牌、人物、产品或文案，只提供版式与设计结构；内容参考图才是新内容的唯一来源。"
        f"当前选择的成品规格为“{layout['label']}”，最终合成长图必须严格为 {target_width}×{target_height}px。"
        f"四段高度依次为 {'、'.join(str(value) + 'px' for value in section_heights)}。"
        "系统会先按这四段高度拆分模板，再逐段执行同位置、同层级、同视觉比例的内容替换。"
        "第一张模板图决定最终原始宽高、每个内容槽位的大小与位置，禁止改尺寸、改比例、改裁切、改分栏或重新排版。"
        "每一处原模特、原产品、原包装、原 Logo、原品牌名、原宣传语、原参数、原标签和原细节照片都必须被替换或删除，不能残留。"
        "内容参考图中的第一张作为核心商品与品牌识别依据，其余图片用于匹配模特、不同角度、细节、效果、包装、文案和规格。"
        "替换后的内容必须一对一完整落在模板原有槽位中，不得移动、增删、合并或拆分槽位，不得改变分栏比例或打乱阅读顺序。"
        "除文案、人物、产品、包装、Logo 与对应产品细节外，模板背景、色块、边框、装饰线和结构元素保持不变。"
        "禁止新增模板中不存在的人物、产品、配件、图标、徽章、标签、光效、装饰或文字模块，禁止重复主体与杂乱堆叠。"
        f"所有可读文字左右至少内缩 {text_margin_x}px，并与所在分段上下边界至少保持 {text_margin_y}px 距离。"
        "背景与装饰仍须满版到边，文字、Logo 和商品关键信息不得被画布边缘或分区边界截断。"
    )


def build_main_image_a_plus_single_test_notes(
    layout_or_key: dict[str, Any] | str,
    image_count: int,
) -> str:
    layout = (
        dict(layout_or_key)
        if isinstance(layout_or_key, dict)
        else get_main_image_a_plus_layout(layout_or_key)
    )
    target_width, target_height = layout["target_size"]
    return (
        f"当前一张测试任务包含 1 张完整成品 A+ 版式模板和 {image_count} 张内容替换参考图。"
        "第 1 张模板只负责锁定整张长图的版式、构图、背景与设计语言，后续参考图负责提供全部新内容。"
        f"最终只生成 1 张完整的 {target_width}×{target_height}px A+ 长图，并严格跟随模板原始宽高比例与画布方向。"
        "必须把模板作为一个不可拆分的整体进行理解和重绘；禁止拆成四段，禁止生成四张局部图，禁止任何上下拼接、图块拼接或后期合成。"
        "整张图只能调用一次生成流程，并在这一次生成中完成所有人物、产品、产品局部、包装、品牌、Logo、文案、参数、标签、图标和细节照片的全量替换。"
        "只保留不带旧商品语义的纯背景，以及模板的整体构图、分区、槽位位置与大小、裁切窗口、叠放层级、对齐、底层色块、结构边框、留白和阅读顺序。"
        "除背景和版式之外的全部内容都必须替换或删除，不能只替换明显的大产品而遗漏小产品、特写、旧品牌、旧模特、角落文字、半透明元素或背景中的旧内容。"
        "模板旧内容必须全部替换或删除；内容参考图中的第一张作为核心商品和品牌依据，其余图片用于匹配模特、角度、细节、效果、包装、文案与规格。"
        "只能替换内容，不能重新设计版式；不得新增、删除、移动、合并或拆分槽位，不得重复人物、商品、Logo 或添加无关装饰。"
        "如果没有对应替换素材，清除模板旧内容并自然补全原背景，不得保留旧产品、旧品牌、旧文案或旧模特，不得编造信息。"
        "输出前逐项复查所有槽位，确保模板旧产品、旧品牌、旧 Logo、旧文案和旧模特残留为零。"
        "最终画面必须完整连贯、清晰锐利，没有接缝、断层、重复区域、贴纸覆盖感、四块拼接感或新旧内容混合。"
        "所有文字与可读 Logo 必须完整清楚并避免被画布边缘截断。"
    )


def build_main_image_a_plus_single_test_prompt(
    full_prompt: str,
    layout: dict[str, Any],
) -> str:
    target_width, target_height = layout["target_size"]
    return (
        f"{str(full_prompt or '').strip()}\n\n"
        "一张测试整图执行指令：输入图片中的第 1 张是完整成品 A+ 版式模板，后续图片全部是新内容参考图。"
        f"一次直接生成 1 张完整的 {target_width}×{target_height}px 商业级 A+ 成品长图。"
        "必须以第 1 张模板的整张画布为统一构图基准，在同一张结果图中完成全部内容替换。"
        "禁止拆成四段或任何数量的局部区域分别生成；禁止拼接、分步合成、分屏、九宫格、多张候选图、接缝、断层和重复画面。"
        "输出宽高比例、画布方向、分区位置、元素槽位、纯背景与视觉层级必须与模板一致。"
        "除纯背景和版式结构外，模板中的文案、人物、产品、产品局部、包装、品牌、Logo、参数、标签、图标、效果图与带有旧商品语义的装饰必须全部替换或删除，一个都不能遗漏。"
        "每一处重复出现的旧产品、旧品牌和旧模特都要分别替换；不要只替换首屏或明显主体。"
        "不要保留任何模板旧内容，不要增加模板没有的元素；新内容必须自然融入原槽位，像在同一份专业设计源文件中一次完成。"
        "生成完成前执行全图复查，旧产品、旧品牌、旧 Logo、旧文案、旧参数和旧模特的残留必须为零。"
        "只输出这一张完整成品，不要输出局部图、过程图、辅助线或版式说明。"
    )


def build_main_image_a_plus_template_section_prompt(
    full_prompt: str,
    layout: dict[str, Any],
    section_index: int,
) -> str:
    target_width, target_height = layout["target_size"]
    section_heights = layout["section_heights"]
    section_height = int(section_heights[section_index])
    text_margin_x = int(layout.get("text_margin_x") or 0)
    text_margin_y = int(layout.get("text_margin_y") or 0)
    return (
        f"{str(full_prompt or '').strip()}\n\n"
        "套版分段执行指令：输入图片中的第 1 张是当前分段的版式模板，后续图片全部是要替换进去的新内容参考图。"
        f"本次只处理第 {section_index + 1}/{MAIN_IMAGE_A_PLUS_SECTION_COUNT} 段，"
        f"输出必须严格为 {target_width}×{section_height}px，最终将合成 {target_width}×{target_height}px 长图。"
        "第 1 张模板分段决定本次输出的精确宽高、构图边界和全部元素槽位，输出不得改变画布比例或裁切范围。"
        "先识别模板中所有人物位、产品位、包装位、Logo 位、标题位、正文位、参数位、标签位和细节图位，"
        "再从后续内容参考图中找到语义对应的新内容逐一替换。"
        "必须像素级锁定模板中每个槽位的坐标、宽高、占比、裁切形状、叠放关系、对齐、背景、色彩、边框、装饰、留白和阅读顺序；不要重新设计版式。"
        "只替换文案、人物、产品、包装、Logo 与对应产品细节；背景、色块、边框、分隔线和结构装饰保持原位。"
        "模板原有的品牌、Logo、文案、模特、产品、包装、局部特写、参数和标签都属于待删除内容，绝对不能出现在结果中。"
        "如果后续参考图没有提供某个槽位的替代内容，删除旧内容并延续相邻背景或装饰，不得保留旧内容或编造新信息。"
        "严格一对一替换且保持模板原有元素数量；禁止添加任何模板没有的人物、产品、配件、图标、徽章、标签、花纹、光效、装饰或文字块。"
        "禁止重复人物、重复商品、重复 Logo、跨槽位放大、元素堆叠和杂乱拼贴；替换内容必须自然融入原槽位，不要出现贴纸感、硬边、遮挡残留、双重文字或新旧内容混合。"
        f"所有文字左右至少内缩 {text_margin_x}px，上下至少内缩 {text_margin_y}px，必须完整可读且不能被截断。"
        "只输出这一段完成套版替换后的商业级成品图。"
    )


def get_infinite_canvas_step_features() -> list[dict[str, Any]]:
    return [
        feature
        for feature_key in INFINITE_CANVAS_STEP_FEATURE_KEYS
        for feature in [get_feature_by_key(feature_key)]
        if feature is not None
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


def get_requested_feature_key() -> str:
    return str(st.query_params.get(FEATURE_QUERY_KEY, "")).strip()


def select_feature(feature_key: str) -> None:
    normalized_key = str(feature_key or "").strip()
    if not normalized_key:
        return
    st.session_state.selected_feature_key = normalized_key
    if get_requested_feature_key() != normalized_key:
        st.query_params[FEATURE_QUERY_KEY] = normalized_key


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


def consume_pending_upload_replacement(widget_key: str) -> int | None:
    replace_widget = str(st.query_params.get(UPLOAD_REPLACE_WIDGET_QUERY_KEY, "")).strip()
    if replace_widget != str(widget_key or "").strip():
        return None
    raw_index = str(st.query_params.get(UPLOAD_REPLACE_INDEX_QUERY_KEY, "")).strip()
    clear_query_param(UPLOAD_REPLACE_WIDGET_QUERY_KEY)
    clear_query_param(UPLOAD_REPLACE_INDEX_QUERY_KEY)
    try:
        return max(int(raw_index), 0)
    except Exception:
        return 0


def consume_pending_outpaint_drag() -> bool:
    raw_payload = str(st.query_params.get(OUTPAINT_DRAG_QUERY_KEY, "")).strip()
    if not raw_payload:
        return False
    clear_query_param(OUTPAINT_DRAG_QUERY_KEY)
    try:
        payload = json.loads(raw_payload)
    except Exception:
        return False
    keys = dict(payload.get("keys") or {})
    limits = dict(payload.get("limits") or {})
    changed = False
    for direction in ("top", "bottom", "left", "right"):
        state_key = str(keys.get(direction) or "").strip()
        if not state_key.startswith(("outpaint_", "infinite_canvas_")):
            continue
        try:
            value = int(payload.get(direction) or 0)
        except Exception:
            value = 0
        try:
            direction_limit = int(limits.get(direction) or OUTPAINT_FALLBACK_MAX_EXTENSION_PX)
        except Exception:
            direction_limit = OUTPAINT_FALLBACK_MAX_EXTENSION_PX
        direction_limit = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, direction_limit))
        if direction_limit > 0 and value >= direction_limit - 25:
            value = direction_limit
        else:
            value = max(0, min(direction_limit, int(round(value / 50) * 50)))
        st.session_state[state_key] = value
        changed = True
    return changed


def get_uploader_nonce_state_key(widget_key: str) -> str:
    return f"uploader_nonce_{widget_key}"


def get_uploader_widget_key(widget_key: str) -> str:
    nonce_key = get_uploader_nonce_state_key(widget_key)
    nonce_value = int(st.session_state.get(nonce_key, 0) or 0)
    return f"{widget_key}__uploader__{nonce_value}"


def get_replace_uploader_widget_key(widget_key: str, item_index: int) -> str:
    nonce_key = get_uploader_nonce_state_key(widget_key)
    nonce_value = int(st.session_state.get(nonce_key, 0) or 0)
    return f"{widget_key}__replace__{item_index}__{nonce_value}"


def get_replace_payload_widget_key(widget_key: str, item_index: int) -> str:
    nonce_key = get_uploader_nonce_state_key(widget_key)
    nonce_value = int(st.session_state.get(nonce_key, 0) or 0)
    return f"{widget_key}__replace_payload__{item_index}__{nonce_value}"


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
        st.session_state.selected_feature_key = (
            get_requested_feature_key() or XIAOHA_DEFAULT_FEATURE_KEY
        )
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
    normalized = relocate_storage_path(image_path_text)
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


def build_direct_image_download_url(image_source: str) -> str:
    download_source = build_history_download_public_url(image_source)
    if not download_source.startswith(("http://", "https://")):
        return download_source
    parsed = urllib.parse.urlsplit(download_source)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["download"] = ["1"]
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(query, doseq=True),
            parsed.fragment,
        )
    )


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


def prepare_openrouter_uploaded_input(uploaded_file: Any) -> dict[str, Any]:
    normalized = normalize_uploaded_input(uploaded_file)
    image_bytes = bytes(normalized.get("data") or b"")
    if not image_bytes or len(image_bytes) <= OPENROUTER_MAX_INPUT_IMAGE_BYTES:
        return normalized

    original_name = sanitize_file_name(str(normalized.get("name") or "openrouter_input.png"))
    stem = Path(original_name).stem or "openrouter_input"
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = ImageOps.exif_transpose(image)
            has_alpha = working.mode in {"RGBA", "LA"} or "transparency" in working.info
            working = working.convert("RGBA") if has_alpha else working.convert("RGB")
            if max(working.size) > OPENROUTER_MAX_INPUT_IMAGE_EDGE:
                ratio = OPENROUTER_MAX_INPUT_IMAGE_EDGE / float(max(working.size))
                resized_size = (
                    max(1, int(round(working.size[0] * ratio))),
                    max(1, int(round(working.size[1] * ratio))),
                )
                working = working.resize(resized_size, Image.Resampling.LANCZOS)
            if has_alpha:
                background = Image.new("RGB", working.size, (255, 255, 255))
                background.paste(working, mask=working.getchannel("A"))
                working = background
            else:
                working = working.convert("RGB")

            quality_candidates = (94, 92, 90, 88, 86, 84, 82, 80, 76, 72, 68, 64, 60, 56, 52)
            output_bytes = b""
            for _attempt in range(8):
                for quality in quality_candidates:
                    output = io.BytesIO()
                    working.save(output, format="JPEG", quality=quality, optimize=True)
                    output_bytes = output.getvalue()
                    if len(output_bytes) <= OPENROUTER_SAFE_INPUT_TARGET_BYTES:
                        return {
                            "data": output_bytes,
                            "name": f"{sanitize_file_name(stem)}_openrouter.jpg",
                            "type": "image/jpeg",
                        }
                if len(output_bytes) <= OPENROUTER_MAX_INPUT_IMAGE_BYTES:
                    return {
                        "data": output_bytes,
                        "name": f"{sanitize_file_name(stem)}_openrouter.jpg",
                        "type": "image/jpeg",
                    }
                next_size = (
                    max(1, int(round(working.size[0] * 0.86))),
                    max(1, int(round(working.size[1] * 0.86))),
                )
                if next_size == working.size:
                    break
                working = working.resize(next_size, Image.Resampling.LANCZOS)
    except Exception as exc:
        raise RuntimeError(
            "OpenRouter 输入图片超过 30MB，自动压缩失败，请换一张更小的图片或降低上一步输出尺寸。"
        ) from exc

    raise RuntimeError("OpenRouter 输入图片超过 30MB，自动压缩后仍然太大，请降低图片尺寸后重试。")


def get_uploaded_input_closest_aspect_ratio(
    uploaded_input: Any,
    fallback: str = DEFAULT_ASPECT_RATIO,
) -> str:
    try:
        image_bytes = get_uploaded_file_bytes(uploaded_input)
        with Image.open(io.BytesIO(image_bytes)) as image:
            normalized = ImageOps.exif_transpose(image)
            if normalized.width > 0 and normalized.height > 0:
                return select_closest_aspect_ratio((normalized.width, normalized.height))
    except Exception:
        pass
    return str(fallback or DEFAULT_ASPECT_RATIO)


def get_uploaded_input_dimensions(uploaded_input: Any) -> tuple[int, int]:
    image_bytes = get_uploaded_file_bytes(uploaded_input)
    if not image_bytes:
        raise RuntimeError("上传图片为空，请重新上传。")
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            source = ImageOps.exif_transpose(image)
            return max(int(source.width), 1), max(int(source.height), 1)
    except Exception as exc:
        raise RuntimeError(f"无法读取上传图片尺寸：{exc}") from exc


def get_outpaint_extension_limits(original_input: Any) -> dict[str, int]:
    source_w, source_h = get_uploaded_input_dimensions(original_input)
    per_side_factor = max((float(OUTPAINT_MAX_CANVAS_MULTIPLIER) - 1.0) / 2.0, 0.0)
    horizontal_limit = min(
        OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
        max(int(round(source_w * per_side_factor)), 0),
    )
    vertical_limit = min(
        OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
        max(int(round(source_h * per_side_factor)), 0),
    )
    return {
        "top": vertical_limit,
        "bottom": vertical_limit,
        "left": horizontal_limit,
        "right": horizontal_limit,
    }


def clamp_outpaint_extensions(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
) -> tuple[int, int, int, int]:
    limits = get_outpaint_extension_limits(original_input)
    return (
        max(0, min(limits["top"], int(top_px))),
        max(0, min(limits["bottom"], int(bottom_px))),
        max(0, min(limits["left"], int(left_px))),
        max(0, min(limits["right"], int(right_px))),
    )


def get_outpaint_default_extension(direction_limit: int) -> int:
    limit = max(int(direction_limit), 0)
    if limit <= 0:
        return 0
    target = limit * 0.5
    if limit < 50:
        return max(1, int(round(target)))
    return max(50, min(limit, int(round(target / 50.0) * 50)))


def get_outpaint_target_canvas_size(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
) -> tuple[int, int]:
    try:
        source_w, source_h = get_uploaded_input_dimensions(original_input)
        top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
            original_input,
            top_px,
            bottom_px,
            left_px,
            right_px,
        )
        return (
            max(1, source_w + left_px + right_px),
            max(1, source_h + top_px + bottom_px),
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"模特扩图失败：无法读取原图尺寸。{exc}") from exc


def get_outpaint_target_aspect_ratio(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    fallback: str = DEFAULT_ASPECT_RATIO,
) -> str:
    try:
        return select_closest_aspect_ratio(
            get_outpaint_target_canvas_size(
                original_input,
                top_px,
                bottom_px,
                left_px,
                right_px,
            )
        )
    except Exception:
        return str(fallback or DEFAULT_ASPECT_RATIO)


def build_outpaint_source_framing_instruction(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
) -> str:
    source_w, source_h = get_uploaded_input_dimensions(original_input)
    top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    target_w = source_w + left_px + right_px
    target_h = source_h + top_px + bottom_px
    width_share = (source_w / target_w) * 100.0
    height_share = (source_h / target_h) * 100.0
    left_share = (left_px / target_w) * 100.0
    right_share = (right_px / target_w) * 100.0
    top_share = (top_px / target_h) * 100.0
    bottom_share = (bottom_px / target_h) * 100.0
    source_area_share = ((source_w * source_h) / float(target_w * target_h)) * 100.0
    new_area_share = max(0.0, 100.0 - source_area_share)
    return (
        "MANDATORY OUTPAINT FRAMING GEOMETRY — this overrides any instruction to keep the old crop or old subject size. "
        f"The uploaded source field of view must occupy only about {width_share:.1f}% of the final frame width and {height_share:.1f}% of the final frame height. "
        f"Place that conceptual source field with about {left_share:.1f}% new visual space on the left, {right_share:.1f}% on the right, {top_share:.1f}% above, and {bottom_share:.1f}% below. "
        f"Approximately {new_area_share:.1f}% of the final frame area must show genuinely new, naturally continued scene content that was outside the uploaded crop. "
        "These percentages describe field-of-view geometry only; do not draw a box, border, inset, or pasted source rectangle. "
        "The final result must show an unmistakably wider/taller camera view and visibly more surroundings. "
        "Returning the same crop, the same subject frame occupancy, a merely retouched copy, or an image with no clearly visible new outer scene is a failed result."
    )


def build_outpaint_region_guide(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
) -> dict[str, Any]:
    source_w, source_h = get_uploaded_input_dimensions(original_input)
    top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    target_w = source_w + left_px + right_px
    target_h = source_h + top_px + bottom_px
    scale = min(OUTPAINT_GUIDE_MAX_EDGE / float(max(target_w, target_h)), 1.0)
    guide_w = max(32, int(round(target_w * scale)))
    guide_h = max(32, int(round(target_h * scale)))
    guide = Image.new("RGB", (guide_w, guide_h), (0, 0, 0))
    draw = ImageDraw.Draw(guide)
    source_box = (
        int(round(left_px / target_w * guide_w)),
        int(round(top_px / target_h * guide_h)),
        int(round((left_px + source_w) / target_w * guide_w)) - 1,
        int(round((top_px + source_h) / target_h * guide_h)) - 1,
    )
    draw.rectangle(source_box, fill=(255, 255, 255))
    output = io.BytesIO()
    guide.save(output, format="PNG", optimize=True)
    return {
        "data": output.getvalue(),
        "name": "outpaint_region_layout_mask.png",
        "type": "image/png",
    }


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


def replace_upload_cache_item(
    widget_key: str,
    item_index: int,
    uploaded_file: Any,
    account_name: str | None = None,
) -> list[dict[str, Any]]:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    current_files = load_upload_cache(widget_key, account_name=normalized_account, max_files=None)
    if item_index < 0:
        return current_files
    if item_index < len(current_files):
        current_files[item_index] = uploaded_file
    else:
        current_files.append(uploaded_file)
    return replace_upload_cache(widget_key, current_files, account_name=normalized_account)


def build_uploaded_input_from_replace_payload(payload_text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(str(payload_text or ""))
    except Exception:
        return None
    data_url = str(payload.get("data_url") or "").strip()
    decoded = decode_data_url(data_url)
    if decoded is None:
        return None
    image_bytes, mime_type = decoded
    file_name = str(payload.get("name") or "").strip() or f"replacement{mimetypes.guess_extension(mime_type) or '.png'}"
    return {
        "data": image_bytes,
        "name": file_name,
        "type": str(payload.get("type") or mime_type or "image/png"),
    }


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


def calculate_smooth_running_progress(
    current_percent: int,
    reported_percent: int,
) -> int:
    """Advance visible progress in small steps while a background task is running."""
    current = max(1, min(int(current_percent or 1), 99))
    reported = max(1, min(int(reported_percent or 1), 100))
    reported_target = min(reported, 97)
    if reported_target > current:
        return min(reported_target, current + 2)

    if reported <= 5:
        waiting_cap = 10
    elif reported < 72:
        waiting_cap = 70
    elif reported < 88:
        waiting_cap = 86
    else:
        waiting_cap = 97
    return min(waiting_cap, current + 1)


def calculate_finishing_progress(
    start_percent: int,
    elapsed_seconds: float,
    duration_seconds: float = 8.0,
) -> int:
    """Animate a completed backend task to 100 instead of jumping instantly."""
    start = max(1, min(int(start_percent or 1), 99))
    duration = max(float(duration_seconds), 0.1)
    fraction = max(0.0, min(float(elapsed_seconds) / duration, 1.0))
    return min(100, max(start, int(math.floor(start + ((100 - start) * fraction)))))


def run_main_image_a_plus_manual_element_job(
    template_input: Any,
    point: tuple[int, int],
    existing_elements: list[dict[str, Any]],
    job_id: str,
) -> dict[str, Any]:
    set_task_progress(job_id, 15, "正在读取点击位置")
    set_task_progress(job_id, 35, "正在识别点击位置的完整元素")
    new_element = analyze_main_image_a_plus_element_at_point(
        template_input,
        point,
        existing_elements,
    )
    set_task_progress(job_id, 100, "补漏识别完成")
    return new_element


def submit_main_image_a_plus_manual_element_job(
    job_state_key: str,
    template_input: Any,
    template_signature: str,
    point: tuple[int, int],
    existing_elements: list[dict[str, Any]],
) -> dict[str, Any]:
    current_state = dict(st.session_state.get(job_state_key) or {})
    if str(current_state.get("status") or "").lower() == "running":
        return current_state
    runtime = get_task_runtime()
    job_id = f"a_plus_manual_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    set_task_progress(job_id, 5, "点击位置已提交")
    future = runtime.executor.submit(
        run_main_image_a_plus_manual_element_job,
        prepare_uploaded_input(template_input),
        tuple(point),
        [dict(element) for element in existing_elements],
        job_id,
    )
    with runtime.lock:
        runtime.futures[job_id] = future
    job_state = {
        "job_id": job_id,
        "status": "running",
        "template_signature": str(template_signature or ""),
        "point": tuple(point),
        "progress": 5,
        "stage": "点击位置已提交",
        "error": "",
    }
    st.session_state[job_state_key] = job_state
    return job_state


def sync_main_image_a_plus_manual_element_job(
    job_state_key: str,
    analysis_state_key: str,
    template_signature: str,
) -> dict[str, Any]:
    job_state = dict(st.session_state.get(job_state_key) or {})
    if str(job_state.get("status") or "").lower() != "running":
        return job_state
    job_id = str(job_state.get("job_id") or "")
    runtime = get_task_runtime()
    with runtime.lock:
        future = runtime.futures.get(job_id)
    progress_info = get_task_progress(job_id)
    if progress_info:
        job_state["progress"] = calculate_smooth_running_progress(
            int(job_state.get("progress") or 5),
            int(progress_info.get("percent") or 5),
        )
        job_state["stage"] = str(progress_info.get("stage") or job_state.get("stage") or "正在识别")
    if future is None:
        job_state.update(
            {
                "status": "error",
                "error": "补漏识别任务状态已丢失，请重新点击元素。",
                "progress": 0,
            }
        )
    elif future.done():
        try:
            new_element = dict(future.result())
            analysis_state = dict(st.session_state.get(analysis_state_key) or {})
            if str(analysis_state.get("template_signature") or "") != str(template_signature or ""):
                raise RuntimeError("模板已经变化，请在当前模板上重新点击。")
            current_elements = [
                dict(item)
                for item in list(analysis_state.get("elements") or [])
                if isinstance(item, dict)
            ]
            if len(current_elements) >= MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS:
                raise RuntimeError(f"当前最多支持 {MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS} 个元素组。")
            new_element["id"] = max(
                [int(element.get("id") or 0) for element in current_elements] or [0]
            ) + 1
            current_elements.append(new_element)
            st.session_state[analysis_state_key] = {
                "template_signature": template_signature,
                "elements": current_elements,
                "error": "",
            }
            job_state.update(
                {
                    "status": "completed",
                    "progress": 100,
                    "stage": "补漏识别完成",
                    "new_element": new_element,
                    "error": "",
                }
            )
        except Exception as exc:
            job_state.update(
                {
                    "status": "error",
                    "progress": 0,
                    "error": format_user_facing_error_message(exc),
                }
            )
        with runtime.lock:
            runtime.futures.pop(job_id, None)
        clear_task_progress(job_id)
    st.session_state[job_state_key] = job_state
    return job_state


@st.fragment(run_every="1s")
def render_main_image_a_plus_manual_element_job_status(
    job_state_key: str,
    analysis_state_key: str,
    template_signature: str,
) -> None:
    job_state = sync_main_image_a_plus_manual_element_job(
        job_state_key,
        analysis_state_key,
        template_signature,
    )
    if str(job_state.get("status") or "").lower() == "running":
        st.markdown(
            build_running_job_spinner_html(
                int(job_state.get("progress") or 5),
                str(job_state.get("stage") or "正在识别点击位置"),
            ),
            unsafe_allow_html=True,
        )
        return
    st.rerun()


def build_running_job_spinner_html(progress_value: int, progress_stage: str) -> str:
    normalized_progress = max(1, min(int(progress_value), 99))
    safe_stage = html.escape(str(progress_stage or "正在处理中").strip() or "正在处理中")
    return f"""
    <style>
      .xiaoha-task-spinner-card {{
        display: flex;
        align-items: center;
        gap: 14px;
        width: 100%;
        box-sizing: border-box;
        padding: 14px 16px;
        margin: 4px 0 10px;
        border: 1px solid rgba(126, 96, 255, 0.22);
        border-radius: 14px;
        background: linear-gradient(135deg, rgba(126, 96, 255, 0.10), rgba(18, 31, 55, 0.44));
      }}
      .xiaoha-task-spinner-circle {{
        position: relative;
        width: 48px;
        height: 48px;
        flex: 0 0 48px;
        display: grid;
        place-items: center;
      }}
      .xiaoha-task-spinner-orbit {{
        position: absolute;
        inset: 0;
        box-sizing: border-box;
        border: 4px solid rgba(126, 96, 255, 0.18);
        border-top-color: #8d78ff;
        border-right-color: #39d7c5;
        border-radius: 50%;
        animation: xiaoha-task-spinner-rotate 0.9s linear infinite;
      }}
      .xiaoha-task-spinner-value {{
        color: #f5f7ff;
        font-size: 11px;
        line-height: 1;
        font-weight: 800;
        letter-spacing: -0.2px;
      }}
      .xiaoha-task-spinner-stage {{
        color: #f5f7ff;
        font-size: 14px;
        line-height: 1.45;
        font-weight: 750;
      }}
      .xiaoha-task-spinner-subtitle {{
        margin-top: 3px;
        color: rgba(214, 219, 255, 0.68);
        font-size: 12px;
        line-height: 1.35;
      }}
      @keyframes xiaoha-task-spinner-rotate {{
        to {{ transform: rotate(360deg); }}
      }}
      @media (prefers-reduced-motion: reduce) {{
        .xiaoha-task-spinner-orbit {{ animation-duration: 1.8s; }}
      }}
    </style>
    <div class="xiaoha-task-spinner-card" role="status" aria-live="polite">
      <div class="xiaoha-task-spinner-circle" aria-hidden="true">
        <div class="xiaoha-task-spinner-orbit"></div>
        <span class="xiaoha-task-spinner-value">{normalized_progress}%</span>
      </div>
      <div>
        <div class="xiaoha-task-spinner-stage">{safe_stage}</div>
        <div class="xiaoha-task-spinner-subtitle">任务在后台运行，状态会自动更新</div>
      </div>
    </div>
    """


@st.fragment(run_every="1s")
def render_running_job_status(feature_key: str) -> None:
    sync_background_jobs()
    current_job = st.session_state.background_jobs.get(feature_key) or {}
    status = str(current_job.get("status") or "").strip().lower()
    if status == "running":
        progress_value = max(1, min(int(current_job.get("progress") or 1), 99))
        progress_stage = str(current_job.get("stage") or "正在处理中").strip() or "正在处理中"
        st.markdown(
            build_running_job_spinner_html(progress_value, progress_stage),
            unsafe_allow_html=True,
        )
        return
    st.rerun()


def get_external_request_kwargs(
    timeout: int | tuple[int, int],
    use_proxy: bool = True,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"timeout": timeout}
    if use_proxy:
        kwargs["proxies"] = REQUEST_PROXIES
    return kwargs


def escape_sql_text(value: Any) -> str:
    return str(value or "").replace("'", "''")


def get_db_connection() -> Any:
    import pytds as sql

    return sql.connect(**DB_CONFIG)


def execute_db_query(query: str, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if params is None:
            cursor.execute(query)
        else:
            cursor.execute(query, params)
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


def normalize_dashboard_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text_value = str(value or "").strip()
    if not text_value:
        return None
    try:
        return date.fromisoformat(text_value[:10])
    except ValueError:
        return None


def build_xiaoha_usage_dashboard_data(
    rows: list[tuple[Any, ...]],
    reference_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    today = normalize_dashboard_date(reference_date) or datetime.now().date()
    yesterday = today - timedelta(days=1)
    first_day = today - timedelta(days=XIAOHA_DASHBOARD_HISTORY_DAYS - 1)
    usage_counts: dict[tuple[date, int, str], int] = {}
    today_active_accounts = 0

    for row in rows:
        if len(row) > 4:
            try:
                today_active_accounts = max(today_active_accounts, int(row[4] or 0))
            except (TypeError, ValueError):
                pass
        usage_day = normalize_dashboard_date(row[0] if len(row) > 0 else None)
        if usage_day is None or usage_day < first_day or usage_day > today:
            continue
        try:
            usage_hour = int(row[1] if len(row) > 1 else 0)
        except (TypeError, ValueError):
            usage_hour = 0
        usage_hour = max(0, min(usage_hour, 23))
        feature_name = str(row[2] if len(row) > 2 else "").strip() or "未分类功能"
        try:
            usage_count = max(int(row[3] if len(row) > 3 else 0), 0)
        except (TypeError, ValueError):
            usage_count = 0
        key = (usage_day, usage_hour, feature_name)
        usage_counts[key] = usage_counts.get(key, 0) + usage_count

    day_sequence = [first_day + timedelta(days=offset) for offset in range(XIAOHA_DASHBOARD_HISTORY_DAYS)]
    hour_labels = [f"{hour:02d}:00" for hour in range(24)]
    today_feature_totals: dict[str, int] = {}
    recent_feature_totals: dict[str, int] = {}
    today_hour_totals = [0] * 24
    yesterday_hour_totals = [0] * 24
    daily_totals = {usage_day: 0 for usage_day in day_sequence}

    for (usage_day, usage_hour, feature_name), usage_count in usage_counts.items():
        recent_feature_totals[feature_name] = recent_feature_totals.get(feature_name, 0) + usage_count
        daily_totals[usage_day] = daily_totals.get(usage_day, 0) + usage_count
        if usage_day == today:
            today_feature_totals[feature_name] = today_feature_totals.get(feature_name, 0) + usage_count
            today_hour_totals[usage_hour] += usage_count
        elif usage_day == yesterday:
            yesterday_hour_totals[usage_hour] += usage_count

    sorted_today_features = sorted(
        today_feature_totals.items(),
        key=lambda item: (-item[1], item[0]),
    )
    line_feature_source = sorted_today_features or sorted(
        recent_feature_totals.items(),
        key=lambda item: (-item[1], item[0]),
    )
    line_feature_names = [
        feature_name
        for feature_name, _count in line_feature_source[:XIAOHA_DASHBOARD_MAX_FEATURE_LINES]
    ]
    feature_hour_series = []
    for feature_name in line_feature_names:
        feature_hour_series.append(
            {
                "name": feature_name,
                "data": [
                    usage_counts.get((today, hour, feature_name), 0)
                    for hour in range(24)
                ],
            }
        )

    today_total = sum(today_hour_totals)
    yesterday_total = sum(yesterday_hour_totals)
    delta_count = today_total - yesterday_total
    if yesterday_total > 0:
        delta_percent = round((delta_count / yesterday_total) * 100, 1)
        delta_label = f"{delta_percent:+g}% 较昨日"
    elif today_total > 0:
        delta_label = "今日新增记录"
    else:
        delta_label = "今日暂无记录"

    peak_count = max(today_hour_totals) if today_hour_totals else 0
    peak_hour = today_hour_totals.index(peak_count) if peak_count > 0 else None
    top_feature_name = sorted_today_features[0][0] if sorted_today_features else "暂无"
    top_feature_count = sorted_today_features[0][1] if sorted_today_features else 0

    return {
        "date": today.isoformat(),
        "date_label": today.strftime("%Y年%m月%d日"),
        "updated_at": datetime.now().strftime("%H:%M:%S"),
        "today_total": today_total,
        "yesterday_total": yesterday_total,
        "delta_count": delta_count,
        "delta_label": delta_label,
        "active_accounts": today_active_accounts,
        "active_features": len([count for count in today_feature_totals.values() if count > 0]),
        "peak_hour": f"{peak_hour:02d}:00" if peak_hour is not None else "—",
        "peak_count": peak_count,
        "top_feature_name": top_feature_name,
        "top_feature_count": top_feature_count,
        "feature_names": [feature_name for feature_name, _count in sorted_today_features],
        "feature_counts": [count for _feature_name, count in sorted_today_features],
        "hour_labels": hour_labels,
        "today_hour_totals": today_hour_totals,
        "yesterday_hour_totals": yesterday_hour_totals,
        "day_labels": [usage_day.strftime("%m-%d") for usage_day in day_sequence],
        "day_totals": [daily_totals.get(usage_day, 0) for usage_day in day_sequence],
        "feature_hour_series": feature_hour_series,
        "has_today_data": today_total > 0,
    }


@st.cache_data(ttl=XIAOHA_DASHBOARD_CACHE_SECONDS, show_spinner=False)
def load_xiaoha_usage_dashboard_rows(reference_date_text: str) -> list[tuple[Any, ...]]:
    today = normalize_dashboard_date(reference_date_text) or datetime.now().date()
    range_start = datetime.combine(
        today - timedelta(days=XIAOHA_DASHBOARD_HISTORY_DAYS - 1),
        datetime.min.time(),
    )
    today_start = datetime.combine(today, datetime.min.time())
    range_end = today_start + timedelta(days=1)
    query = f"""
        WITH UsageByHour AS (
            SELECT
                CAST(RiQi AS date) AS UsageDate,
                DATEPART(hour, RiQi) AS UsageHour,
                CASE
                    WHEN NULLIF(LTRIM(RTRIM(GongNeng)), '') IS NULL THEN N'未分类功能'
                    ELSE LTRIM(RTRIM(GongNeng))
                END AS FeatureName,
                COUNT_BIG(*) AS UsageCount
            FROM {DB_HISTORY_TABLE}
            WHERE RiQi >= %s AND RiQi < %s
            GROUP BY
                CAST(RiQi AS date),
                DATEPART(hour, RiQi),
                CASE
                    WHEN NULLIF(LTRIM(RTRIM(GongNeng)), '') IS NULL THEN N'未分类功能'
                    ELSE LTRIM(RTRIM(GongNeng))
                END
        ),
        TodayAccounts AS (
            SELECT COUNT(DISTINCT NULLIF(LTRIM(RTRIM(ZhangHao)), '')) AS ActiveAccounts
            FROM {DB_HISTORY_TABLE}
            WHERE RiQi >= %s AND RiQi < %s
        )
        SELECT
            UsageByHour.UsageDate,
            UsageByHour.UsageHour,
            UsageByHour.FeatureName,
            UsageByHour.UsageCount,
            TodayAccounts.ActiveAccounts
        FROM TodayAccounts
        LEFT JOIN UsageByHour ON 1 = 1
        ORDER BY UsageByHour.UsageDate, UsageByHour.UsageHour, UsageByHour.UsageCount DESC
    """
    return execute_db_query(
        query,
        (range_start, range_end, today_start, range_end),
    )


def build_xiaoha_usage_dashboard_html(dashboard_data: dict[str, Any]) -> str:
    serialized_data = (
        json.dumps(dashboard_data, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    empty_note = "" if bool(dashboard_data.get("has_today_data")) else (
        '<div class="empty-note">今天暂时没有使用记录，图表将在产生新记录后自动更新。</div>'
    )
    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"
                onerror="this.onerror=null;this.src='https://unpkg.com/echarts@5.5.1/dist/echarts.min.js';"></script>
        <style>
            * {{ box-sizing: border-box; }}
            html, body {{
                margin: 0;
                padding: 0;
                background: transparent;
                color: #f6f7ff;
                font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
            }}
            .dashboard {{ padding: 4px 2px 18px; }}
            .hero {{
                position: relative;
                overflow: hidden;
                padding: 24px 26px;
                border: 1px solid rgba(255,255,255,.09);
                border-radius: 22px;
                background:
                    radial-gradient(circle at 82% 18%, rgba(126,100,255,.28), transparent 32%),
                    linear-gradient(135deg, rgba(15,27,54,.98), rgba(10,18,39,.96));
                box-shadow: 0 20px 55px rgba(0,0,0,.24);
            }}
            .hero::after {{
                content: "";
                position: absolute;
                width: 240px;
                height: 240px;
                right: -80px;
                top: -125px;
                border: 42px solid rgba(102,231,255,.08);
                border-radius: 50%;
            }}
            .eyebrow {{
                display: inline-flex;
                align-items: center;
                gap: 7px;
                padding: 6px 10px;
                border-radius: 999px;
                background: rgba(116,91,255,.18);
                color: #b9adff;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: .08em;
            }}
            .eyebrow::before {{
                content: "";
                width: 7px;
                height: 7px;
                border-radius: 50%;
                background: #6ce5ff;
                box-shadow: 0 0 14px rgba(108,229,255,.9);
            }}
            h1 {{ margin: 12px 0 5px; font-size: 27px; line-height: 1.15; }}
            .subtitle {{ color: rgba(220,226,255,.68); font-size: 13px; }}
            .metrics {{
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 12px;
                margin-top: 18px;
            }}
            .metric {{
                min-height: 100px;
                padding: 15px 16px;
                border: 1px solid rgba(255,255,255,.075);
                border-radius: 16px;
                background: linear-gradient(150deg, rgba(255,255,255,.055), rgba(255,255,255,.018));
            }}
            .metric-label {{ color: rgba(221,226,255,.65); font-size: 12px; }}
            .metric-value {{ margin-top: 6px; font-size: 27px; line-height: 1.05; font-weight: 800; }}
            .metric-sub {{
                margin-top: 8px;
                color: #8fddff;
                font-size: 11px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}
            .empty-note {{
                margin-top: 12px;
                padding: 10px 13px;
                border: 1px solid rgba(247,197,92,.18);
                border-radius: 12px;
                background: rgba(247,197,92,.07);
                color: #f5d990;
                font-size: 12px;
            }}
            .chart-grid {{
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
                gap: 14px;
                margin-top: 14px;
            }}
            .chart-card {{
                min-width: 0;
                padding: 15px 15px 8px;
                border: 1px solid rgba(255,255,255,.075);
                border-radius: 18px;
                background: linear-gradient(145deg, rgba(12,24,49,.94), rgba(8,17,36,.94));
                box-shadow: 0 14px 38px rgba(0,0,0,.18);
            }}
            .chart-card.wide {{ grid-column: 1 / -1; }}
            .chart-title {{ margin: 0 0 1px 4px; font-size: 14px; font-weight: 750; }}
            .chart-caption {{ margin: 3px 0 0 4px; color: rgba(216,223,255,.52); font-size: 11px; }}
            .chart {{ width: 100%; height: 300px; }}
            .chart-card.wide .chart {{ height: 330px; }}
            .load-error {{
                display: none;
                margin-top: 14px;
                padding: 14px;
                border-radius: 14px;
                background: rgba(255,103,133,.10);
                color: #ffb2c0;
                font-size: 13px;
            }}
            @media (max-width: 850px) {{
                .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
                .chart-grid {{ grid-template-columns: 1fr; }}
                .chart-card.wide {{ grid-column: auto; }}
            }}
        </style>
    </head>
    <body>
        <main class="dashboard">
            <section class="hero">
                <div class="eyebrow">TODAY · {html.escape(str(dashboard_data.get('date') or ''))}</div>
                <h1>功能使用仪表盘</h1>
                <div class="subtitle">数据来自 AI_TuPian · 按 GongNeng 统计 · 每 {XIAOHA_DASHBOARD_CACHE_SECONDS} 秒自动更新</div>
                <div class="metrics">
                    <div class="metric">
                        <div class="metric-label">今日使用记录</div>
                        <div class="metric-value">{int(dashboard_data.get('today_total') or 0):,}</div>
                        <div class="metric-sub">{html.escape(str(dashboard_data.get('delta_label') or ''))}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">今日活跃账号</div>
                        <div class="metric-value">{int(dashboard_data.get('active_accounts') or 0):,}</div>
                        <div class="metric-sub">产生过使用记录的账号</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">今日使用功能</div>
                        <div class="metric-value">{int(dashboard_data.get('active_features') or 0):,}</div>
                        <div class="metric-sub">最高：{html.escape(str(dashboard_data.get('top_feature_name') or '暂无'))} · {int(dashboard_data.get('top_feature_count') or 0):,} 次</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">今日高峰时段</div>
                        <div class="metric-value">{html.escape(str(dashboard_data.get('peak_hour') or '—'))}</div>
                        <div class="metric-sub">该小时共 {int(dashboard_data.get('peak_count') or 0):,} 条记录</div>
                    </div>
                </div>
                {empty_note}
            </section>
            <section class="chart-grid">
                <article class="chart-card">
                    <div class="chart-title">今日各功能使用排行</div>
                    <div class="chart-caption">展示当天 AI_TuPian 中全部 GongNeng 记录</div>
                    <div id="featureRanking" class="chart"></div>
                </article>
                <article class="chart-card">
                    <div class="chart-title">最近 7 天使用趋势</div>
                    <div class="chart-caption">按天汇总全部功能，观察整体使用变化</div>
                    <div id="dailyTrend" class="chart"></div>
                </article>
                <article class="chart-card wide">
                    <div class="chart-title">每小时使用对比</div>
                    <div class="chart-caption">今日各功能走势，并以虚线对比昨日总量</div>
                    <div id="hourlyTrend" class="chart"></div>
                </article>
            </section>
            <div id="loadError" class="load-error">图表组件暂时未加载成功，请刷新页面后重试。</div>
        </main>
        <script>
            const dashboardData = {serialized_data};
            const palette = ['#8b78ff', '#55d7ff', '#ff7fa7', '#5ce0a0', '#f6c95c', '#ff9b69'];
            const axisColor = 'rgba(215,223,255,.48)';
            const gridLine = 'rgba(205,216,255,.075)';
            const charts = [];

            function baseTooltip() {{
                return {{
                    trigger: 'axis',
                    backgroundColor: 'rgba(7,14,30,.96)',
                    borderColor: 'rgba(139,120,255,.35)',
                    textStyle: {{ color: '#f5f7ff', fontSize: 12 }},
                    axisPointer: {{ type: 'line', lineStyle: {{ color: 'rgba(108,229,255,.3)' }} }}
                }};
            }}

            function initDashboard() {{
                if (!window.echarts) {{
                    document.getElementById('loadError').style.display = 'block';
                    return;
                }}

                const ranking = echarts.init(document.getElementById('featureRanking'));
                const rankingNames = [...dashboardData.feature_names].reverse();
                const rankingCounts = [...dashboardData.feature_counts].reverse();
                ranking.setOption({{
                    animationDuration: 650,
                    color: [palette[0]],
                    tooltip: baseTooltip(),
                    grid: {{ left: 108, right: 38, top: 18, bottom: 25 }},
                    xAxis: {{
                        type: 'value',
                        minInterval: 1,
                        axisLabel: {{ color: axisColor, fontSize: 10 }},
                        splitLine: {{ lineStyle: {{ color: gridLine }} }}
                    }},
                    yAxis: {{
                        type: 'category',
                        data: rankingNames,
                        axisTick: {{ show: false }},
                        axisLine: {{ show: false }},
                        axisLabel: {{
                            color: '#dfe4ff',
                            fontSize: 11,
                            width: 92,
                            overflow: 'truncate'
                        }}
                    }},
                    series: [{{
                        name: '使用记录',
                        type: 'bar',
                        data: rankingCounts,
                        barMaxWidth: 15,
                        showBackground: true,
                        backgroundStyle: {{ color: 'rgba(255,255,255,.035)', borderRadius: 8 }},
                        itemStyle: {{
                            borderRadius: [0, 8, 8, 0],
                            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                                {{ offset: 0, color: '#715bff' }},
                                {{ offset: 1, color: '#58d8ff' }}
                            ])
                        }},
                        label: {{ show: true, position: 'right', color: '#f5f7ff', fontSize: 10 }}
                    }}]
                }});
                charts.push(ranking);

                const daily = echarts.init(document.getElementById('dailyTrend'));
                daily.setOption({{
                    animationDuration: 650,
                    color: [palette[1]],
                    tooltip: baseTooltip(),
                    grid: {{ left: 44, right: 22, top: 25, bottom: 34 }},
                    xAxis: {{
                        type: 'category',
                        boundaryGap: false,
                        data: dashboardData.day_labels,
                        axisTick: {{ show: false }},
                        axisLine: {{ lineStyle: {{ color: gridLine }} }},
                        axisLabel: {{ color: axisColor, fontSize: 10 }}
                    }},
                    yAxis: {{
                        type: 'value',
                        minInterval: 1,
                        axisLine: {{ show: false }},
                        axisLabel: {{ color: axisColor, fontSize: 10 }},
                        splitLine: {{ lineStyle: {{ color: gridLine }} }}
                    }},
                    series: [{{
                        name: '使用记录',
                        type: 'line',
                        smooth: .28,
                        symbol: 'circle',
                        symbolSize: 7,
                        lineStyle: {{ width: 3 }},
                        areaStyle: {{
                            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                {{ offset: 0, color: 'rgba(85,215,255,.36)' }},
                                {{ offset: 1, color: 'rgba(85,215,255,.015)' }}
                            ])
                        }},
                        data: dashboardData.day_totals
                    }}]
                }});
                charts.push(daily);

                const hourly = echarts.init(document.getElementById('hourlyTrend'));
                const featureSeries = dashboardData.feature_hour_series.map((item, index) => ({{
                    name: item.name,
                    type: 'line',
                    smooth: .32,
                    showSymbol: false,
                    emphasis: {{ focus: 'series' }},
                    lineStyle: {{ width: 2 }},
                    data: item.data,
                    color: palette[index % palette.length]
                }}));
                featureSeries.push({{
                    name: '昨日总量',
                    type: 'line',
                    smooth: .25,
                    showSymbol: false,
                    data: dashboardData.yesterday_hour_totals,
                    color: 'rgba(225,231,255,.46)',
                    lineStyle: {{ width: 1.5, type: 'dashed' }}
                }});
                hourly.setOption({{
                    animationDuration: 650,
                    tooltip: baseTooltip(),
                    legend: {{
                        type: 'scroll',
                        top: 5,
                        left: 45,
                        right: 20,
                        textStyle: {{ color: 'rgba(226,231,255,.72)', fontSize: 10 }},
                        pageTextStyle: {{ color: axisColor }}
                    }},
                    grid: {{ left: 46, right: 22, top: 48, bottom: 35 }},
                    xAxis: {{
                        type: 'category',
                        boundaryGap: false,
                        data: dashboardData.hour_labels,
                        axisTick: {{ show: false }},
                        axisLine: {{ lineStyle: {{ color: gridLine }} }},
                        axisLabel: {{ color: axisColor, fontSize: 9, interval: 2 }}
                    }},
                    yAxis: {{
                        type: 'value',
                        minInterval: 1,
                        axisLine: {{ show: false }},
                        axisLabel: {{ color: axisColor, fontSize: 10 }},
                        splitLine: {{ lineStyle: {{ color: gridLine }} }}
                    }},
                    series: featureSeries
                }});
                charts.push(hourly);
                window.addEventListener('resize', () => charts.forEach(chart => chart.resize()));
            }}

            if (document.readyState === 'complete') {{
                initDashboard();
            }} else {{
                window.addEventListener('load', initDashboard, {{ once: true }});
            }}
        </script>
    </body>
    </html>
    """


def render_xiaoha_usage_dashboard() -> None:
    title_col, refresh_col = st.columns([5.6, 0.8], vertical_alignment="bottom")
    with title_col:
        st.markdown("## 今日数据看板")
        st.caption("查看当天各功能使用情况，以及最近 7 天与昨日的时间线对比。")
    with refresh_col:
        if st.button("刷新数据", key="refresh_xiaoha_usage_dashboard", use_container_width=True):
            load_xiaoha_usage_dashboard_rows.clear()
            st.rerun()

    today = datetime.now().date()
    try:
        rows = load_xiaoha_usage_dashboard_rows(today.isoformat())
    except Exception as exc:
        st.error("数据看板暂时无法连接统计数据库，请稍后刷新。")
        st.caption(f"统计查询错误：{format_user_facing_error_message(exc)}")
        return
    dashboard_data = build_xiaoha_usage_dashboard_data(rows, today)
    components.html(
        build_xiaoha_usage_dashboard_html(dashboard_data),
        height=1050,
        scrolling=False,
    )


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


def ensure_feature_output_dir(feature_key: str) -> Path:
    output_dir = CUTOUT_OUTPUT_DIR if str(feature_key or "").strip() == "background_cutout" else DB_IMAGE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


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


def prepare_main_image_a_plus_reference_input(uploaded_input: Any) -> dict[str, Any]:
    normalized = normalize_uploaded_input(uploaded_input)
    image_bytes = bytes(normalized.get("data") or b"")
    if not image_bytes:
        return normalized
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = ImageOps.exif_transpose(image).convert("RGB")
            if max(working.size) > MAIN_IMAGE_A_PLUS_REFERENCE_MAX_EDGE:
                scale = MAIN_IMAGE_A_PLUS_REFERENCE_MAX_EDGE / float(max(working.size))
                working = working.resize(
                    (
                        max(1, int(round(working.width * scale))),
                        max(1, int(round(working.height * scale))),
                    ),
                    Image.Resampling.LANCZOS,
                )
            output_bytes = b""
            for quality in (92, 88, 84, 80, 76, 72):
                output = io.BytesIO()
                working.save(output, format="JPEG", quality=quality, optimize=True)
                output_bytes = output.getvalue()
                if len(output_bytes) <= MAIN_IMAGE_A_PLUS_REFERENCE_TARGET_BYTES:
                    break
            stem = Path(str(normalized.get("name") or "a_plus_reference")).stem or "a_plus_reference"
            return {
                "data": output_bytes,
                "name": f"{sanitize_file_name(stem)}_a_plus_ref.jpg",
                "type": "image/jpeg",
            }
    except Exception:
        return normalized


def build_main_image_a_plus_continuity_reference(
    image_url: str,
    target_width: int,
    target_height: int,
    base_name: str,
) -> dict[str, Any]:
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = ImageOps.exif_transpose(image).convert("RGB")
            expected_size = (max(int(target_width), 1), max(int(target_height), 1))
            if working.size != expected_size:
                working = working.resize(expected_size, Image.Resampling.LANCZOS)
            output = io.BytesIO()
            working.save(output, format="JPEG", quality=88, optimize=True, subsampling=0)
    except Exception as exc:
        raise RuntimeError(f"A+ 连续片段参考图压缩失败：{exc}") from exc
    safe_stem = Path(sanitize_file_name(base_name or "a_plus_continuity")).stem
    return {
        "data": output.getvalue(),
        "name": f"{safe_stem}.jpg",
        "type": "image/jpeg",
    }


def build_portrait_hd_prompt(prompt: str) -> str:
    base_prompt = str(prompt or "").strip()
    rules = (
        f"最高优先级硬性规则：{PORTRAIT_HD_SKIN_LOCK_RULES}\n"
        "图片使用规则：\n"
        "- 第一张图片是需要高清增强的主图，必须以第一张图片的人物身份、五官、脸型、表情、发型、构图和背景为准。\n"
        "- 如果提供了第二张图片，第二张图片仍作为高清参考图，但只允许参考其清晰度、分辨率和细节解析水平。\n"
        "- 严禁从第二张图片借用或迁移肤色、肤质、毛孔状态、皮肤光泽、颗粒感、斑点、妆容、脸型、五官、眼睛、表情、发型、服饰、背景或人物身份。\n"
        "- 最终皮肤必须逐项保持第1张原图状态，不得磨皮、祛斑、去痣、去痘印、去细纹、提亮或调色。\n"
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
    image_path = Path(relocate_storage_path(image_path_text))
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
    normalized = relocate_storage_path(image_path_text)
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
    storage_dir = ensure_feature_output_dir(feature_key)
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
    normalized_account = str(account_name or "admin").strip() or "admin"
    feature_name = get_feature_name_by_key(feature_key)
    if normalized_account in DB_HISTORY_ALL_ACCESS_USERS:
        query = (
            f"SELECT TOP {safe_limit} ZhangHao, GongNeng, MoXing, TuPian, RiQi "
            f"FROM {DB_HISTORY_TABLE} "
            f"WHERE GongNeng = %s "
            f"ORDER BY RiQi DESC, ID DESC"
        )
        rows = execute_db_query(query, (feature_name,))
    else:
        query = (
            f"SELECT TOP {safe_limit} ZhangHao, GongNeng, MoXing, TuPian, RiQi "
            f"FROM {DB_HISTORY_TABLE} "
            f"WHERE ZhangHao = %s AND GongNeng = %s "
            f"ORDER BY RiQi DESC, ID DESC"
        )
        rows = execute_db_query(query, (normalized_account, feature_name))
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
    normalized_account = str(account_name or "admin").strip() or "admin"
    normalized_feature = str(feature_key or "").strip() or "all"
    return f"history:{normalized_account}:{normalized_feature}"


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
    normalized_account = str(account_name or "admin").strip() or "admin"
    normalized_feature = str(feature_key or "").strip()
    try:
        db_records = load_db_history_records(normalized_feature, normalized_account, limit=limit)
    except Exception:
        db_records = []
    if db_records:
        return db_records[: max(int(limit), 1)]
    if normalized_account in DB_HISTORY_ALL_ACCESS_USERS:
        merged_records = []
        for user_store in (st.session_state.local_history_records or {}).values():
            merged_records.extend(list(dict(user_store or {}).get(normalized_feature) or []))
    else:
        user_store = dict((st.session_state.local_history_records or {}).get(normalized_account) or {})
        merged_records = list(user_store.get(normalized_feature) or [])
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


def should_enhance_output_detail(feature_key: str) -> bool:
    return str(feature_key or "").strip() == "hd_batch"


def is_jimeng_model(model_name: str) -> bool:
    return str(model_name or "").strip() == JIMENG_MODEL_NAME


def get_model_display_name(model_name: str) -> str:
    normalized_name = str(model_name or "").strip()
    if is_jimeng_model(normalized_name):
        return "即梦 Seedream 4.6"
    if normalized_name == NANO_BANANA_MODEL:
        return "Nano Banana 2 生图"
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
    request_aspect_ratio = str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO)
    request_prompt = str(job_context["prompt"])
    request_uploaded_group = list(uploaded_group)
    outpaint_alignment: dict[str, int] = {}
    if feature_key == "outpaint" and uploaded_group:
        outpaint_settings = dict(job_context.get("outpaint_settings") or {})
        top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
            uploaded_group[0],
            int(outpaint_settings.get("top", 0) or 0),
            int(outpaint_settings.get("bottom", 0) or 0),
            int(outpaint_settings.get("left", 0) or 0),
            int(outpaint_settings.get("right", 0) or 0),
        )
        target_width, target_height = get_outpaint_target_canvas_size(
            uploaded_group[0],
            top_px,
            bottom_px,
            left_px,
            right_px,
        )
        source_width, source_height = get_uploaded_input_dimensions(uploaded_group[0])
        outpaint_alignment = {
            "source_width": source_width,
            "source_height": source_height,
            "target_width": target_width,
            "target_height": target_height,
            "top": top_px,
            "bottom": bottom_px,
            "left": left_px,
            "right": right_px,
        }
        region_guide = build_outpaint_region_guide(
            uploaded_group[0],
            top_px,
            bottom_px,
            left_px,
            right_px,
        )
        request_uploaded_group = [uploaded_group[0], region_guide]
        request_aspect_ratio = get_outpaint_target_aspect_ratio(
            uploaded_group[0],
            top_px,
            bottom_px,
            left_px,
            right_px,
            fallback=request_aspect_ratio,
        )
        request_prompt += (
            "\n\nCurrent source-specific expansion: "
            f"top {top_px}px, bottom {bottom_px}px, left {left_px}px, right {right_px}px. "
            f"The intended expanded canvas is {target_width}×{target_height} before mapping to the nearest supported model aspect ratio."
            "\n\n"
            + build_outpaint_source_framing_instruction(
                uploaded_group[0],
                top_px,
                bottom_px,
                left_px,
                right_px,
            )
            + "\n\nThe first input image is the source photograph. The second input image is a strict black-and-white layout mask: "
            + "the white rectangle is the exact final-frame location and size of the uploaded source field, and every black area is the direction and amount that must be newly generated. "
            + "Use this mask only as geometry. Do not copy black, white, borders, rectangles, mask texture, or diagram styling into the photograph. "
            + "The generated photograph must visibly follow the mask proportions and offset; changing the requested rectangle position or expansion direction is a failed result."
        )

    def generate_once(prompt_text: str) -> dict[str, Any]:
        if is_jimeng_model(str(job_context.get("model") or "")):
            if feature_key == "hd_batch":
                return call_jimeng_portrait_hd(
                    prompt=prompt_text,
                    aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
                    uploaded_files=list(request_uploaded_group),
                    feature_key=feature_key,
                )
            return call_jimeng_v40(
                prompt=prompt_text,
                aspect_ratio=request_aspect_ratio,
                uploaded_files=list(request_uploaded_group),
                feature_key=feature_key,
            )
        if feature_key == "hd_batch" and str(job_context.get("output_mode") or "") == "image":
            return call_openrouter_portrait_hd(
                model=str(job_context["model"]),
                prompt=prompt_text,
                aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
                uploaded_files=list(request_uploaded_group),
            )
        return call_openrouter(
            model=str(job_context["model"]),
            prompt=prompt_text,
            uploaded_files=list(request_uploaded_group),
            output_mode=str(job_context["output_mode"]),
            aspect_ratio=request_aspect_ratio,
        )

    if feature_key == "outpaint" and str(job_context.get("output_mode") or "") == "image":
        variant_count = max(int(job_context.get("max_output_images") or OUTPAINT_RESULTS_PER_SOURCE), 1)
        variant_images: list[str] = []
        variant_texts: list[str] = []
        for variant_index in range(variant_count):
            variant_result = generate_once(
                request_prompt
                + "\n\n"
                + f"Generate candidate {variant_index + 1} of {variant_count}. Return exactly one finished image in this call. "
                + "Keep the source identity and requested framing fixed, while giving the newly extended environment a natural independent variation."
            )
            variant_images.extend(list(variant_result.get("images") or [])[:1])
            variant_text = str(variant_result.get("text") or "").strip()
            if variant_text:
                variant_texts.append(variant_text)
        batch_result = {
            "images": variant_images,
            "text": "\n\n".join(variant_texts),
        }
    else:
        batch_result = generate_once(request_prompt)
    if job_context["output_mode"] == "image":
        target_size = job_context.get("target_size")
        if target_size:
            batch_result["images"] = [
                resize_image_to_exact_size(image_url, int(target_size[0]), int(target_size[1]))
                for image_url in (batch_result.get("images") or [])
            ]
        elif feature_key not in {"hd_batch", "background_cutout", "outpaint"}:
            batch_result["images"] = [
                upscale_image_to_min_edge(
                    image_url,
                    min_output_edge,
                    enhance_detail=should_enhance_output_detail(feature_key),
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
        "outpaint_alignment": outpaint_alignment,
    }


def finalize_canvas_job_result(job_context: dict[str, Any], result: dict[str, Any], job_id: str) -> dict[str, Any]:
    if job_id:
        set_task_progress(job_id, 88, "正在整理结果并保存历史")
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


def finalize_feature_job_result(job_context: dict[str, Any], result: dict[str, Any], job_id: str) -> dict[str, Any]:
    if job_id:
        set_task_progress(job_id, 88, "正在整理结果并返回页面")
    account_name = str(job_context.get("account_name") or "admin")
    fallback_history_records = build_local_history_records(
        feature=dict(job_context["feature"]),
        model=str(job_context.get("model") or ""),
        prompt=str(job_context.get("prompt") or ""),
        result=result,
        account_name=account_name,
    )
    result_text_parts = [str(result.get("text") or "").strip()]
    history_records = fallback_history_records
    psd_bytes = result.get("psd_bytes")
    if isinstance(psd_bytes, (bytes, bytearray)) and psd_bytes:
        try:
            artifact_dir = ensure_feature_output_dir(
                str((job_context.get("feature") or {}).get("key") or "amazon_a_plus")
            )
            psd_file_name = Path(str(result.get("psd_file_name") or "amazon_a_plus.psd")).name
            if not psd_file_name.lower().endswith(".psd"):
                psd_file_name += ".psd"
            psd_path = artifact_dir / psd_file_name
            psd_path.write_bytes(bytes(psd_bytes))
            result["psd_path"] = str(psd_path)
            result.pop("psd_storage_error", None)
            result_text_parts.append("分层 PSD 已保存到服务器。")
        except Exception as exc:
            psd_storage_error = f"分层 PSD 保存到服务器失败：{exc}"
            result["psd_storage_error"] = psd_storage_error
            print(f"[psd-save] {psd_storage_error}", file=sys.stderr)
            result_text_parts.append("分层 PSD 已生成并可下载，但保存到服务器失败。")
    if result.get("images"):
        try:
            history_records = save_generated_images_and_record_db(
                feature=dict(job_context["feature"]),
                model=str(job_context.get("model") or ""),
                prompt=str(job_context.get("prompt") or ""),
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


def run_infinite_canvas_job(job_context: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    uploaded_files = [prepare_uploaded_input(item) for item in list(job_context.get("uploaded_files") or [])]
    step_keys = [
        str(step_key or "").strip()
        for step_key in list(job_context.get("canvas_steps") or [])
        if get_feature_by_key(str(step_key or "").strip()) is not None
    ]
    if not uploaded_files:
        raise RuntimeError("无限画布需要先上传至少 1 张图片。")
    if not step_keys:
        raise RuntimeError("请至少选择 1 个要组合的处理步骤。")

    model = str(job_context.get("model") or NANO_BANANA_MODEL)
    aspect_ratio = str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO)
    custom_prompt = str(job_context.get("custom_prompt") or "")
    canvas_step_settings = list(job_context.get("canvas_step_settings") or [])
    canvas_outpaint = dict(job_context.get("canvas_outpaint") or {})
    outpaint_top_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(canvas_outpaint.get("top", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
    outpaint_bottom_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(canvas_outpaint.get("bottom", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
    outpaint_left_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(canvas_outpaint.get("left", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
    outpaint_right_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(canvas_outpaint.get("right", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
    canvas_hd_reference = job_context.get("canvas_hd_reference")
    if canvas_hd_reference is not None:
        canvas_hd_reference = prepare_uploaded_input(canvas_hd_reference)

    result_images: list[str] = []
    source_images: list[str] = []
    captions: list[str] = []
    text_parts: list[str] = []
    total_operations = max(len(uploaded_files) * len(step_keys), 1)
    completed_operations = 0

    if job_id:
        set_task_progress(job_id, 8, "正在执行无限画布组合流程")

    for image_index, original_input in enumerate(uploaded_files, start=1):
        current_input = prepare_uploaded_input(original_input)
        final_image_url = ""
        try:
            source_images.append(uploaded_input_to_data_url(original_input))
        except Exception:
            source_images.append("")
        step_names: list[str] = []

        for step_index, step_key in enumerate(step_keys, start=1):
            step_feature = get_feature_by_key(step_key)
            if step_feature is None:
                continue
            step_settings = (
                dict(canvas_step_settings[step_index - 1])
                if step_index - 1 < len(canvas_step_settings) and isinstance(canvas_step_settings[step_index - 1], dict)
                else {}
            )
            step_names.append(str(step_feature.get("name") or step_key))
            extra_notes = (
                f"这是无限画布组合流程的第 {step_index}/{len(step_keys)} 步。"
                "当前输入可能是上一步已经处理过的结果，请把它作为唯一主体继续处理，"
                "不要重置画面、不要生成多版本、不要改变已经稳定的主体身份。"
            )
            step_aspect_ratio = aspect_ratio
            step_uploaded_files = [current_input]
            step_hd_reference = step_settings.get("hd_reference") or canvas_hd_reference
            if step_hd_reference is not None:
                step_hd_reference = prepare_uploaded_input(step_hd_reference)
            if step_key == "hd_batch" and step_hd_reference is not None:
                step_uploaded_files = [current_input, step_hd_reference]
            if step_key == "outpaint":
                step_outpaint = dict(step_settings.get("outpaint") or {})
                current_top_px, current_bottom_px, current_left_px, current_right_px = clamp_outpaint_extensions(
                    current_input,
                    int(step_outpaint.get("top", outpaint_top_px) or 0),
                    int(step_outpaint.get("bottom", outpaint_bottom_px) or 0),
                    int(step_outpaint.get("left", outpaint_left_px) or 0),
                    int(step_outpaint.get("right", outpaint_right_px) or 0),
                )
                if current_top_px + current_bottom_px + current_left_px + current_right_px <= 0:
                    raise RuntimeError("无限画布里的扩图步骤至少需要一个方向大于 0。")
                step_uploaded_files = [current_input]
                step_aspect_ratio = get_outpaint_target_aspect_ratio(
                    current_input,
                    current_top_px,
                    current_bottom_px,
                    current_left_px,
                    current_right_px,
                    fallback=aspect_ratio,
                )
                extra_notes = (
                    build_outpaint_extra_notes(
                        current_top_px,
                        current_bottom_px,
                        current_left_px,
                        current_right_px,
                    )
                    + "\n"
                    + extra_notes
                )
            step_prompt = build_prompt(
                dict(step_feature),
                custom_prompt,
                step_aspect_ratio,
                extra_notes,
            )
            if is_jimeng_model(model):
                if step_key == "hd_batch":
                    step_result = call_jimeng_portrait_hd(
                        prompt=step_prompt,
                        aspect_ratio=step_aspect_ratio,
                        uploaded_files=step_uploaded_files,
                        feature_key=step_key,
                    )
                else:
                    step_result = call_jimeng_v40(
                        prompt=step_prompt,
                        aspect_ratio=step_aspect_ratio,
                        uploaded_files=step_uploaded_files,
                        feature_key=step_key,
                    )
            elif step_key == "hd_batch":
                step_result = call_openrouter_portrait_hd(
                    model=model,
                    prompt=step_prompt,
                    aspect_ratio=step_aspect_ratio,
                    uploaded_files=step_uploaded_files,
                )
            else:
                step_result = call_openrouter(
                    model=model,
                    prompt=step_prompt,
                    uploaded_files=step_uploaded_files,
                    output_mode="image",
                    aspect_ratio=step_aspect_ratio,
                )

            step_images = list(step_result.get("images") or [])
            if not step_images:
                raise RuntimeError(f"无限画布第 {step_index} 步「{step_feature.get('name') or step_key}」没有返回图片。")
            image_url = str(step_images[0])
            if step_key not in {"hd_batch", "outpaint"}:
                image_url = upscale_image_to_min_edge(
                    image_url,
                    get_feature_min_output_edge(step_key),
                    enhance_detail=should_enhance_output_detail(step_key),
                )
            step_text = str(step_result.get("text") or "").strip()
            if step_text:
                text_parts.append(f"图 {image_index} / {step_feature.get('name') or step_key}：{step_text}")
            current_input = build_uploaded_input_from_image_url_raw(
                image_url,
                base_name=f"infinite_canvas_{image_index}_{step_index}.png",
            )
            final_image_url = image_url
            completed_operations += 1
            if job_id:
                progress_value = 12 + math.floor((completed_operations / total_operations) * 66)
                set_task_progress(
                    job_id,
                    min(progress_value, 82),
                    f"正在处理第 {image_index}/{len(uploaded_files)} 张，第 {step_index}/{len(step_keys)} 步",
                )

        result_images.append(final_image_url or uploaded_input_to_data_url(current_input))
        captions.append(f"画布图 {image_index} · {' → '.join(step_names)}")

    if not result_images:
        raise RuntimeError("无限画布没有生成可用结果，请调整组合步骤后重试。")
    return {
        "images": result_images,
        "source_images": source_images[: len(result_images)],
        "captions": captions,
        "text": "\n\n".join(text_parts).strip(),
    }


def split_main_image_a_plus_template(
    template_input: Any,
    target_width: int,
    section_heights: tuple[int, ...],
) -> list[dict[str, Any]]:
    if template_input is None:
        raise RuntimeError("套版替换需要先上传 1 张成品 A+ 模板。")
    template_bytes = get_uploaded_file_bytes(template_input)
    try:
        with Image.open(io.BytesIO(template_bytes)) as image:
            template = ImageOps.exif_transpose(image).convert("RGB")
            target_height = sum(section_heights)
            if template.size != (target_width, target_height):
                template = template.resize((target_width, target_height), Image.Resampling.LANCZOS)
            sections: list[dict[str, Any]] = []
            start_y = 0
            for index, section_height in enumerate(section_heights, start=1):
                section = template.crop((0, start_y, target_width, start_y + section_height))
                output = io.BytesIO()
                section.save(output, format="PNG")
                sections.append(
                    {
                        "data": output.getvalue(),
                        "name": f"a_plus_layout_template_section_{index}.png",
                        "type": "image/png",
                    }
                )
                start_y += section_height
            return sections
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"成品 A+ 模板读取或拆分失败：{exc}") from exc


def stitch_main_image_a_plus_sections(
    section_image_urls: list[str],
    target_width: int,
    section_heights: tuple[int, ...],
) -> str:
    if len(section_image_urls) != len(section_heights):
        raise RuntimeError("主图生A+分段数量不完整，无法合成长图。")
    target_height = sum(section_heights)
    canvas = Image.new("RGB", (target_width, target_height), "white")
    current_y = 0
    for section_image_url, section_height in zip(section_image_urls, section_heights):
        image_bytes, _mime_type = load_image_bytes_from_url(section_image_url)
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                section = ImageOps.exif_transpose(image).convert("RGB")
                if section.size != (target_width, section_height):
                    section = section.resize((target_width, section_height), Image.Resampling.LANCZOS)
                canvas.paste(section, (0, current_y))
        except Exception as exc:
            raise RuntimeError(f"主图生A+分段图片读取失败：{exc}") from exc
        current_y += section_height
    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return image_bytes_to_data_url(output.getvalue(), "image/png")


def run_main_image_a_plus_job(job_context: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    generation_mode = normalize_main_image_a_plus_mode(
        str(job_context.get("main_image_a_plus_mode") or "")
    )
    layout = (
        dict(job_context["main_image_a_plus_layout"])
        if isinstance(job_context.get("main_image_a_plus_layout"), dict)
        else get_main_image_a_plus_layout(
            str(job_context.get("main_image_a_plus_layout_key") or "")
        )
    )
    target_width, target_height = layout["target_size"]
    section_heights = layout["section_heights"]
    uploaded_files = [
        prepare_main_image_a_plus_reference_input(item)
        for item in list(job_context.get("uploaded_files") or [])
    ]
    if generation_mode == MAIN_IMAGE_A_PLUS_MODE_FREE:
        request_aspect_ratio = select_main_image_a_plus_safe_aspect_ratio((target_width, target_height))
        if job_id:
            set_task_progress(job_id, 12, "正在一次生成完整 A+ 商业长图")
        free_result = call_openrouter_images_api(
            model=str(job_context["model"]),
            prompt=build_main_image_a_plus_free_prompt(
                str(job_context.get("prompt") or ""),
                layout,
            ),
            uploaded_files=uploaded_files,
            aspect_ratio=request_aspect_ratio,
            resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
            max_attempts=1,
        )
        generated_images = list(free_result.get("images") or [])
        if not generated_images:
            raise RuntimeError("自由创作没有返回完整 A+ 成品图，请重新提交。")
        if job_id:
            set_task_progress(job_id, 76, "整张 A+ 已生成，正在适配所选规格")
        final_image_url = cover_image_to_exact_size(
            str(generated_images[0]),
            target_width,
            target_height,
        )
        model_text = str(free_result.get("text") or "").strip()
        summary = (
            f"已按“{layout['label']}”一次生成并适配为 {target_width}×{target_height}px 商业 A+ 长图。"
            "本次只调用一次整图生成，没有拆分模块、没有生成四张局部图，也没有执行图片拼接。"
        )
        return {
            "images": [final_image_url],
            "text": "\n\n".join(part for part in (model_text, summary) if part),
            "channel": "Images API 原生 4K · A+ 整图直出",
            "requested_aspect_ratios": (request_aspect_ratio,),
            "target_size": (target_width, target_height),
            "section_count": 1,
            "section_heights": (target_height,),
            "section_height": target_height,
            "main_image_a_plus_layout_key": layout["key"],
            "main_image_a_plus_layout_label": layout["label"],
            "main_image_a_plus_mode": generation_mode,
            "generation_waves": 1,
            "max_parallel_sections": 1,
            "prepared_reference_count": len(uploaded_files),
        }
    if generation_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
        template_input = job_context.get("main_image_a_plus_template")
        if template_input is None:
            raise RuntimeError("指定元素替换需要先上传并识别 1 张完整的成品 A+ 示例图。")
        replacements = [
            dict(item)
            for item in list(job_context.get("main_image_a_plus_element_replacements") or [])
            if isinstance(item, dict)
        ]
        if not replacements or len(replacements) != len(uploaded_files):
            raise RuntimeError("指定元素与替换图片的映射不完整，请重新识别并为至少一个编号上传替换图。")
        template_reference = normalize_uploaded_input(template_input)
        request_aspect_ratio = select_closest_aspect_ratio((target_width, target_height))
        if job_id:
            set_task_progress(job_id, 12, f"正在按 {len(replacements)} 个编号执行指定元素替换")
        element_result = call_openrouter_images_api(
            model=str(job_context["model"]),
            prompt=build_main_image_a_plus_element_replacement_prompt(
                str(job_context.get("prompt") or ""),
                layout,
                replacements,
            ),
            uploaded_files=[template_reference, *uploaded_files],
            aspect_ratio=request_aspect_ratio,
            resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        )
        generated_images = list(element_result.get("images") or [])
        if not generated_images:
            raise RuntimeError("指定元素替换没有返回完整 A+ 成品图，请重试。")
        if job_id:
            set_task_progress(job_id, 76, "指定元素替换完成，正在适配模板原尺寸")
        final_image_url = resize_image_to_exact_size(
            str(generated_images[0]),
            target_width,
            target_height,
        )
        replaced_labels = "、".join(
            f"#{int(item.get('id') or index + 1)} {str(item.get('name') or '元素')}"
            for index, item in enumerate(replacements)
        )
        summary = (
            f"已按模板原尺寸一次生成 {target_width}×{target_height}px 成品，并完成指定元素替换：{replaced_labels}。"
            "未选择的元素、背景和版式均要求保持不变；本模式未拆分模板或拼接图片。"
        )
        return {
            "images": [final_image_url],
            "text": summary,
            "channel": "Images API 原生 4K · 指定元素整图替换",
            "requested_aspect_ratios": (request_aspect_ratio,),
            "target_size": (target_width, target_height),
            "section_count": 1,
            "section_heights": (target_height,),
            "section_height": target_height,
            "main_image_a_plus_layout_key": layout["key"],
            "main_image_a_plus_layout_label": layout["label"],
            "main_image_a_plus_mode": generation_mode,
            "generation_waves": 1,
            "max_parallel_sections": 1,
            "prepared_reference_count": len(uploaded_files),
            "replaced_element_count": len(replacements),
            "replaced_element_ids": tuple(int(item.get("id") or 0) for item in replacements),
        }
    if generation_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST:
        template_input = job_context.get("main_image_a_plus_template")
        if template_input is None:
            raise RuntimeError("一张测试需要先上传 1 张完整的成品 A+ 版式模板。")
        template_reference = normalize_uploaded_input(template_input)
        request_aspect_ratio = select_closest_aspect_ratio((target_width, target_height))
        if job_id:
            set_task_progress(job_id, 12, "正在识别完整 A+ 版式并进行整图内容替换")
        single_result = call_openrouter_images_api(
            model=str(job_context["model"]),
            prompt=build_main_image_a_plus_single_test_prompt(
                str(job_context.get("prompt") or ""),
                layout,
            ),
            uploaded_files=[template_reference, *uploaded_files],
            aspect_ratio=request_aspect_ratio,
            resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        )
        generated_images = list(single_result.get("images") or [])
        if not generated_images:
            raise RuntimeError("一张测试没有返回完整 A+ 成品图，请重试。")
        if job_id:
            set_task_progress(job_id, 76, "整图生成完成，正在适配模板原尺寸")
        final_image_url = resize_image_to_exact_size(
            str(generated_images[0]),
            target_width,
            target_height,
        )
        model_text = str(single_result.get("text") or "").strip()
        summary = (
            f"已将完整模板作为统一版式参考，一次生成 1 张 {target_width}×{target_height}px A+ 成品长图。"
            "本模式未拆分模板、未生成四张局部图，也未执行任何图片拼接。"
        )
        return {
            "images": [final_image_url],
            "text": "\n\n".join(part for part in (model_text, summary) if part),
            "channel": "Images API 原生 4K · 整图套版重绘",
            "requested_aspect_ratios": (request_aspect_ratio,),
            "target_size": (target_width, target_height),
            "section_count": 1,
            "section_heights": (target_height,),
            "section_height": target_height,
            "main_image_a_plus_layout_key": layout["key"],
            "main_image_a_plus_layout_label": layout["label"],
            "main_image_a_plus_mode": generation_mode,
            "generation_waves": 1,
            "max_parallel_sections": 1,
            "prepared_reference_count": len(uploaded_files),
        }
    template_sections = (
        split_main_image_a_plus_template(
            job_context.get("main_image_a_plus_template"),
            target_width,
            section_heights,
        )
        if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE
        else []
    )

    def generate_section(
        section_index: int,
        continuity_reference: dict[str, Any] | None = None,
        continuity_reference_role: str = "",
    ) -> dict[str, Any]:
        section_height = int(section_heights[section_index])
        request_aspect_ratio = select_closest_aspect_ratio((target_width, section_height))
        section_prompt = (
            build_main_image_a_plus_template_section_prompt(
                str(job_context.get("prompt") or ""),
                layout,
                section_index,
            )
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE
            else build_main_image_a_plus_section_prompt(
                str(job_context.get("prompt") or ""),
                layout,
                section_index,
                has_previous_section_reference=continuity_reference is not None,
                continuity_reference_role=continuity_reference_role,
            )
        )
        section_uploaded_files = (
            [template_sections[section_index], *uploaded_files]
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE
            else [
                *uploaded_files,
                *([continuity_reference] if continuity_reference is not None else []),
            ]
        )
        section_result = call_openrouter_images_api(
            model=str(job_context["model"]),
            prompt=section_prompt,
            uploaded_files=section_uploaded_files,
            aspect_ratio=request_aspect_ratio,
            resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        )
        generated_images = list(section_result.get("images") or [])
        if not generated_images:
            raise RuntimeError(
                f"主图生A+第 {section_index + 1} 个模块没有返回图片，请重试。"
            )
        return {
            "index": section_index,
            "image": str(generated_images[0]),
            "text": str(section_result.get("text") or "").strip(),
            "aspect_ratio": request_aspect_ratio,
        }

    section_results: dict[int, dict[str, Any]] = {}

    def generate_sections_in_parallel(
        section_specs: list[tuple[int, dict[str, Any] | None, str]],
        progress_label: str,
        progress_start: int,
        progress_span: int,
    ) -> None:
        if not section_specs:
            return
        worker_count = min(MAIN_IMAGE_A_PLUS_MAX_SECTION_CONCURRENCY, len(section_specs))
        completed_count = 0
        with ThreadPoolExecutor(max_workers=worker_count) as section_executor:
            future_map = {
                section_executor.submit(generate_section, section_index, reference, role): section_index
                for section_index, reference, role in section_specs
            }
            for future in as_completed(future_map):
                section_result = future.result()
                section_results[int(section_result["index"])] = section_result
                completed_count += 1
                if job_id:
                    set_task_progress(
                        job_id,
                        progress_start + math.floor((completed_count / len(section_specs)) * progress_span),
                        f"{progress_label} {completed_count}/{len(section_specs)}",
                    )

    if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE:
        generation_waves = 1
        max_parallel_sections = MAIN_IMAGE_A_PLUS_SECTION_COUNT
        if job_id:
            set_task_progress(job_id, 12, "正在并行替换 4 个 A+ 模板片段")
        generate_sections_in_parallel(
            [(index, None, "") for index in range(MAIN_IMAGE_A_PLUS_SECTION_COUNT)],
            "已完成套版片段",
            12,
            60,
        )
    elif len(uploaded_files) >= MAIN_IMAGE_A_PLUS_MAX_FILES:
        generation_waves = 1
        max_parallel_sections = MAIN_IMAGE_A_PLUS_SECTION_COUNT
        if job_id:
            set_task_progress(job_id, 12, "正在并行生成 4 个 A+ 连续画面片段")
        generate_sections_in_parallel(
            [(index, None, "") for index in range(MAIN_IMAGE_A_PLUS_SECTION_COUNT)],
            "已完成画面片段",
            12,
            60,
        )
    else:
        generation_waves = 2
        max_parallel_sections = MAIN_IMAGE_A_PLUS_SECTION_COUNT - 1
        if job_id:
            set_task_progress(job_id, 12, "正在生成 A+ 首屏风格锚点")
        first_section_result = generate_section(0)
        section_results[0] = first_section_result
        continuity_reference = None
        try:
            continuity_reference = build_main_image_a_plus_continuity_reference(
                str(first_section_result["image"]),
                target_width,
                int(section_heights[0]),
                base_name="a_plus_continuity_section_1.png",
            )
        except Exception:
            continuity_reference = None
        if job_id:
            set_task_progress(job_id, 32, "首屏完成，正在并行生成剩余 3 个片段")
        generate_sections_in_parallel(
            [
                (
                    index,
                    continuity_reference,
                    "previous" if index == 1 else "style_anchor",
                )
                for index in range(1, MAIN_IMAGE_A_PLUS_SECTION_COUNT)
            ],
            "已完成剩余片段",
            32,
            40,
        )

    ordered_section_results = [
        section_results[index]
        for index in range(MAIN_IMAGE_A_PLUS_SECTION_COUNT)
    ]
    section_image_urls = [str(item["image"]) for item in ordered_section_results]
    requested_aspect_ratios = [str(item["aspect_ratio"]) for item in ordered_section_results]
    section_texts = [
        f"第 {index + 1} 段：{str(item['text']).strip()}"
        for index, item in enumerate(ordered_section_results)
        if str(item.get("text") or "").strip()
    ]

    if job_id:
        set_task_progress(job_id, 76, "正在合成连续 A+ 长图")
    final_image_url = stitch_main_image_a_plus_sections(
        section_image_urls,
        target_width,
        section_heights,
    )
    if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE:
        summary = (
            "已按模板原图尺寸拆分成品模板，并行替换各片段后按原顺序无缝合成套版成品。"
            "模板仅保留版式与设计结构，原品牌、原模特、原产品和原文案均要求替换或删除。"
        )
    else:
        summary = (
            f"已按“{layout['label']}”使用原生 4K 生成连续画面，并合成为 "
            f"{target_width}×{target_height}px 成品。"
            "四个内容阶段自然衔接且不显示硬边界，视觉元素可跨阶段延伸；画面满版铺满，完整文字不会被截断。"
        )
    return {
        "images": [final_image_url],
        "text": "\n\n".join([*section_texts, summary]).strip(),
        "channel": (
            "Images API 原生 4K · 并行套版替换"
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE
            else "Images API 原生 4K · 快速连续长图生成"
        ),
        "requested_aspect_ratios": tuple(requested_aspect_ratios),
        "target_size": (target_width, target_height),
        "section_count": MAIN_IMAGE_A_PLUS_SECTION_COUNT,
        "section_heights": section_heights,
        "section_height": section_heights[0] if len(set(section_heights)) == 1 else None,
        "main_image_a_plus_layout_key": layout["key"],
        "main_image_a_plus_layout_label": layout["label"],
        "main_image_a_plus_mode": generation_mode,
        "generation_waves": generation_waves,
        "max_parallel_sections": max_parallel_sections,
        "prepared_reference_count": len(uploaded_files),
    }


def run_feature_job(job_context: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    if job_id:
        set_task_progress(job_id, 5, "准备上传图片")
    feature_key = str((job_context.get("feature") or {}).get("key") or "")
    if feature_key == MAIN_IMAGE_A_PLUS_FEATURE_KEY:
        uploaded_files = list(job_context.get("uploaded_files") or [])
        feature = dict(job_context.get("feature") or {})
        generation_mode = normalize_main_image_a_plus_mode(
            str(
                job_context.get("main_image_a_plus_mode")
                or feature.get("main_image_a_plus_mode")
                or ""
            )
        )
        if not uploaded_files:
            raise RuntimeError("主图生A+至少需要上传 1 张内容参考图。")
        reference_limit = (
            MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            else MAIN_IMAGE_A_PLUS_MAX_FILES
        )
        if len(uploaded_files) > reference_limit:
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
                raise RuntimeError(f"指定元素替换最多支持 {reference_limit} 个上传元素组。")
            raise RuntimeError(f"主图生A+最多只能上传 {reference_limit} 张主图。")
        if (
            generation_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
            and job_context.get("main_image_a_plus_template") is None
        ):
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
                raise RuntimeError("指定元素替换需要先上传并识别 1 张完整的成品 A+ 示例图。")
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST:
                raise RuntimeError("一张测试需要先上传 1 张完整的成品 A+ 版式模板。")
            raise RuntimeError("套版替换需要先上传 1 张成品 A+ 模板。")
        layout = (
            get_main_image_a_plus_template_layout(job_context.get("main_image_a_plus_template"))
            if generation_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
            else get_main_image_a_plus_layout(
                str(
                    job_context.get("main_image_a_plus_layout_key")
                    or feature.get("main_image_a_plus_layout_key")
                    or ""
                )
            )
        )
        job_context = dict(job_context)
        job_context["main_image_a_plus_mode"] = generation_mode
        job_context["main_image_a_plus_layout"] = layout
        job_context["main_image_a_plus_layout_key"] = layout["key"]
        job_context["target_size"] = layout["target_size"]
        job_context["section_heights"] = layout["section_heights"]
        result = run_main_image_a_plus_job(job_context)
        return finalize_feature_job_result(job_context, result, job_id)
    if feature_key == "infinite_canvas":
        result = run_infinite_canvas_job(job_context)
        return finalize_canvas_job_result(job_context, result, job_id)
    feature_mode = str((job_context.get("feature") or {}).get("mode") or "openrouter")
    if feature_mode == "ai_cutout":
        result = run_ai_background_cutout_job(job_context)
        return finalize_feature_job_result(job_context, result, job_id)
    batch_groups = list(job_context.get("batch_groups") or [])
    if batch_groups:
        display_source_groups = list(job_context.get("display_source_groups") or [])
        merged_images: list[str] = []
        merged_source_images: list[str] = []
        merged_texts: list[str] = []
        merged_captions: list[str] = []
        merged_outpaint_alignments: list[dict[str, int]] = []
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
            group_alignment = dict(group_result.get("outpaint_alignment") or {})
            merged_outpaint_alignments.extend([group_alignment] * len(batch_images))
            if batch_images:
                uploaded_group = (
                    display_source_groups[group_index - 1]
                    if group_index - 1 < len(display_source_groups)
                    else batch_groups[group_index - 1] if group_index - 1 < len(batch_groups) else []
                )
                source_image = ""
                if uploaded_group:
                    try:
                        source_image = uploaded_input_to_data_url(uploaded_group[0])
                    except Exception:
                        source_image = ""
                merged_source_images.extend([source_image] * len(batch_images))
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
            "source_images": merged_source_images,
            "text": "\n\n".join(merged_texts).strip(),
            "captions": merged_captions,
            "outpaint_alignments": merged_outpaint_alignments,
        }
    else:
        if job_id:
            set_task_progress(job_id, 18, "正在请求模型生成结果")
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
            if feature_key in A_PLUS_IMAGES_API_FEATURE_KEYS and str(job_context.get("output_mode") or "") == "image":
                target_size = job_context.get("target_size")
                request_aspect_ratio = (
                    select_closest_aspect_ratio((int(target_size[0]), int(target_size[1])))
                    if target_size
                    else str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO)
                )
                result = call_openrouter_images_api(
                    model=str(job_context["model"]),
                    prompt=str(job_context["prompt"]),
                    uploaded_files=list(job_context["uploaded_files"]),
                    aspect_ratio=request_aspect_ratio,
                    resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
                )
                result["channel"] = "Images API 原生 4K"
                result["requested_aspect_ratio"] = request_aspect_ratio
            elif feature_key == "hd_batch" and str(job_context.get("output_mode") or "") == "image":
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
            if target_size and feature_key != AMAZON_A_PLUS_FEATURE_KEY:
                result["images"] = [
                    resize_image_to_exact_size(image_url, int(target_size[0]), int(target_size[1]))
                    for image_url in (result.get("images") or [])
                ]
            elif feature_key not in {"hd_batch", "background_cutout", "outpaint"}:
                result["images"] = [
                    upscale_image_to_min_edge(
                        image_url,
                        min_output_edge,
                        enhance_detail=should_enhance_output_detail(feature_key),
                    )
                    for image_url in (result.get("images") or [])
                ]
            if feature_key == AMAZON_A_PLUS_FEATURE_KEY and (result.get("images") or []):
                if job_id:
                    set_task_progress(job_id, 80, "正在识别绿幕元素并生成分层 PSD")
                result = build_amazon_a_plus_layered_result(result, target_size)
        max_output_images = int(job_context.get("max_output_images") or 0)
        if max_output_images > 0:
            result["images"] = (result.get("images") or [])[:max_output_images]
        if job_context["output_mode"] == "image" and not (result.get("images") or []):
            backend_name = "Agent" if is_jimeng_model(str(job_context.get("model") or "")) else "OpenRouter"
            raise RuntimeError(f"{backend_name} 未返回图片：请求已提交，但响应中没有可用的结果图片。")
    return finalize_feature_job_result(job_context, result, job_id)


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


def store_completed_background_job_result(
    feature_key: str,
    job_info: dict[str, Any],
    result: dict[str, Any],
) -> None:
    job_info["status"] = "completed"
    job_info["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    job_info["progress"] = 100
    job_info["stage"] = "处理完成"
    job_info.pop("completion_pending", None)
    job_info.pop("completion_started_at", None)
    job_info.pop("completion_start_progress", None)
    st.session_state.feature_results[feature_key] = result
    account_name = str(result.get("history_account_name") or st.session_state.get("auth_username") or "admin")
    history_records = list(result.get("history_records") or [])
    if history_records:
        store_local_history_records(account_name, feature_key, history_records)
    cache_key = get_history_cache_key(account_name, feature_key)
    st.session_state.history_records_cache.pop(cache_key, None)
    set_history_visible_limit(cache_key, HISTORY_PAGE_SIZE)


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
                job_info["progress"] = calculate_smooth_running_progress(
                    int(job_info.get("progress") or 1),
                    int(progress_info.get("percent") or 1),
                )
                job_info["stage"] = str(progress_info.get("stage") or job_info.get("stage") or "")
            else:
                job_info["status"] = "error"
                job_info["error"] = "后台任务状态已丢失，请重新提交任务。"
                job_info["progress"] = 0
                job_info["stage"] = "任务状态丢失"
            continue
        if bool(job_info.get("completion_pending")):
            completion_started_at = float(job_info.get("completion_started_at") or time.time())
            completion_start_progress = int(
                job_info.get("completion_start_progress")
                or job_info.get("progress")
                or 1
            )
            animated_progress = calculate_finishing_progress(
                completion_start_progress,
                time.time() - completion_started_at,
            )
            job_info["progress"] = animated_progress
            job_info["stage"] = "结果已生成，正在完成最后处理"
            if animated_progress < 100:
                continue
            try:
                result = future.result()
            except Exception as exc:
                progress_info = get_task_progress(job_id) or {}
                failed_stage = str(progress_info.get("stage") or "任务执行失败").strip()
                user_error = format_user_facing_error_message(exc)
                job_info["status"] = "error"
                job_info["error"] = (
                    f"{failed_stage}：{user_error}"
                    if failed_stage and failed_stage != "任务执行失败"
                    else user_error
                )
                job_info["progress"] = 0
                job_info["stage"] = failed_stage or "任务执行失败"
            else:
                store_completed_background_job_result(feature_key, job_info, result)
            with runtime.lock:
                runtime.futures.pop(job_id, None)
            clear_task_progress(job_id)
            continue
        if not future.done():
            progress_info = get_task_progress(job_id)
            if progress_info:
                job_info["progress"] = calculate_smooth_running_progress(
                    int(job_info.get("progress") or 1),
                    int(progress_info.get("percent") or 1),
                )
                job_info["stage"] = str(progress_info.get("stage") or job_info.get("stage") or "")
            continue
        try:
            result = future.result()
        except Exception as exc:
            progress_info = get_task_progress(job_id) or {}
            failed_stage = str(progress_info.get("stage") or "任务执行失败").strip()
            user_error = format_user_facing_error_message(exc)
            job_info["status"] = "error"
            job_info["error"] = (
                f"{failed_stage}：{user_error}"
                if failed_stage and failed_stage != "任务执行失败"
                else user_error
            )
            job_info["progress"] = 0
            job_info["stage"] = failed_stage or "任务执行失败"
            print(
                f"[background-job] job_id={job_id} feature={feature_key} stage={failed_stage} "
                f"error={type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            with runtime.lock:
                runtime.futures.pop(job_id, None)
            clear_task_progress(job_id)
        else:
            completion_start_progress = calculate_smooth_running_progress(
                int(job_info.get("progress") or 1),
                100,
            )
            job_info["progress"] = completion_start_progress
            job_info["stage"] = "结果已生成，正在完成最后处理"
            job_info["completion_pending"] = True
            job_info["completion_started_at"] = time.time()
            job_info["completion_start_progress"] = completion_start_progress


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
            padding-top: 0.72rem !important;
            margin-top: 0 !important;
            padding-left: 1rem;
            padding-right: 1rem;
            padding-bottom: 1.35rem;
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
        .workspace-panel {
            background:
                radial-gradient(circle at top right, rgba(88, 64, 255, 0.12), transparent 26%),
                linear-gradient(135deg, rgba(9, 17, 35, 0.92), rgba(7, 15, 31, 0.92));
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
            box-shadow: 0 18px 44px rgba(0, 0, 0, 0.24);
            padding: 0.86rem 0.94rem 0.92rem;
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
            font-size: 1.55rem;
            font-weight: 700;
            margin-bottom: 0.24rem;
        }
        .feature-desc {
            color: rgba(214, 219, 255, 0.78);
            font-size: 0.88rem;
            margin-bottom: 0.55rem;
            max-width: 780px;
        }
        .meta-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.38rem;
            margin-bottom: 0.65rem;
        }
        .meta-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.28rem 0.56rem;
            border-radius: 999px;
            font-size: 0.74rem;
            color: #dbe0ff;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.06);
        }
        .workflow-strip {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.38rem;
            margin: 0.1rem 0 0.78rem;
            padding: 0.48rem;
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 13px;
            background: rgba(5, 12, 27, 0.42);
        }
        .workflow-step {
            display: flex;
            align-items: center;
            min-width: 0;
            gap: 0.42rem;
            color: rgba(230, 233, 255, 0.78);
            font-size: 0.74rem;
            line-height: 1.25;
            white-space: nowrap;
            position: relative;
        }
        .workflow-step:not(:last-child)::after {
            content: "";
            height: 1px;
            flex: 1 1 auto;
            min-width: 12px;
            margin-left: 0.18rem;
            background: linear-gradient(90deg, rgba(139, 117, 255, 0.46), rgba(139, 117, 255, 0.08));
        }
        .workflow-step-number {
            display: grid;
            place-items: center;
            width: 22px;
            height: 22px;
            flex: 0 0 22px;
            border-radius: 50%;
            color: #f7f6ff;
            font-size: 0.68rem;
            font-weight: 800;
            background: rgba(126, 96, 255, 0.2);
            border: 1px solid rgba(145, 122, 255, 0.34);
        }
        .fixed-model-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.7rem;
            margin: 0.08rem 0 0.42rem;
            padding: 0.58rem 0.72rem;
            border-radius: 11px;
            border: 1px solid rgba(255, 255, 255, 0.07);
            background: rgba(255, 255, 255, 0.035);
            color: rgba(214, 219, 255, 0.68);
            font-size: 0.74rem;
        }
        .fixed-model-card strong {
            color: #f3f5ff;
            font-size: 0.82rem;
            font-weight: 750;
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
            margin: 0.2rem 0 0.26rem;
        }
        .upload-main-empty, .result-empty {
            min-height: 188px;
            border-radius: 14px;
            border: 1px dashed rgba(132, 111, 255, 0.58);
            background: rgba(7, 15, 31, 0.52);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            gap: 0.55rem;
            text-align: center;
            color: rgba(214, 219, 255, 0.72);
            margin-bottom: 0.24rem;
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
            text-align: left;
            margin: 0.12rem 0 0.32rem;
        }
        .inline-action-row {
            margin-top: 0.42rem;
            padding-top: 0.48rem;
            border-top: 1px solid rgba(255, 255, 255, 0.07);
        }
        .main-action-dock-marker,
        .a-plus-mode-selector-marker,
        .a-plus-template-card-marker,
        .a-plus-analysis-card-marker,
        .a-plus-auto-fill-card-marker,
        .batch-left-column-marker,
        .batch-right-column-marker,
        .upload-add-marker,
        .upload-more-marker {
            display: none !important;
        }
        div[data-testid="column"]:has(.batch-left-column-marker),
        div[data-testid="column"]:has(.batch-right-column-marker) {
            align-self: stretch !important;
            min-width: 0 !important;
            padding: 0.78rem 0.82rem 0.82rem !important;
            border: 1px solid rgba(255, 255, 255, 0.075);
            border-radius: 15px;
            background:
                radial-gradient(circle at top right, rgba(132, 111, 255, 0.075), transparent 31%),
                rgba(5, 13, 29, 0.58);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
        }
        div[data-testid="column"]:has(.batch-right-column-marker) .result-empty {
            min-height: 390px;
            margin-bottom: 0;
        }
        div[data-testid="column"]:has(.batch-left-column-marker) .result-block-title,
        div[data-testid="column"]:has(.batch-right-column-marker) .result-block-title {
            margin-bottom: 0.62rem;
        }
        .upload-summary-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            min-height: 34px;
            margin: 0 0 0.5rem;
            padding: 0.42rem 0.58rem;
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.035);
            color: rgba(214, 219, 255, 0.72);
            font-size: 0.74rem;
        }
        .upload-summary-row strong {
            color: #f3f5ff;
            font-size: 0.78rem;
            font-weight: 750;
        }
        .upload-summary-row span:last-child {
            color: rgba(214, 219, 255, 0.56);
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.main-action-dock-marker),
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] .main-action-dock-marker) {
            position: sticky;
            top: 0.55rem;
            z-index: 42;
            margin: 0 0 0.72rem !important;
            padding: 0.58rem 0.62rem 0.48rem !important;
            border: 1px solid rgba(132, 111, 255, 0.34) !important;
            border-radius: 14px !important;
            border-color: rgba(132, 111, 255, 0.34) !important;
            background:
                linear-gradient(180deg, rgba(13, 23, 48, 0.98), rgba(8, 16, 34, 0.96)) !important;
            box-shadow:
                0 14px 32px rgba(0, 0, 0, 0.3),
                inset 0 1px 0 rgba(255, 255, 255, 0.055);
            backdrop-filter: blur(16px);
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.main-action-dock-marker) .fixed-model-card,
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] .main-action-dock-marker) .fixed-model-card {
            margin-top: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.main-action-dock-marker) .inline-action-row,
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] .main-action-dock-marker) .inline-action-row {
            display: none !important;
        }
        div[data-testid="stVerticalBlock"]:has(.a-plus-mode-selector-marker) > .stElementContainer:has(.stRadio) {
            width: 100% !important;
        }
        div[data-testid="stVerticalBlock"]:has(.a-plus-mode-selector-marker) .stRadio {
            width: 100% !important;
        }
        div[data-testid="stVerticalBlock"]:has(.a-plus-mode-selector-marker) .stRadio [role="radiogroup"] {
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.34rem !important;
            width: 100% !important;
        }
        div[data-testid="stVerticalBlock"]:has(.a-plus-mode-selector-marker) .stRadio [role="radiogroup"] label {
            min-width: 0 !important;
            min-height: 34px !important;
            padding: 0.18rem 0.36rem !important;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            background: rgba(8, 16, 34, 0.72);
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.a-plus-template-card-marker),
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] .a-plus-template-card-marker) {
            min-height: 272px;
            padding: 0.62rem 0.68rem 0.52rem !important;
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            border-radius: 14px !important;
            background: rgba(7, 15, 31, 0.52) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.a-plus-analysis-card-marker),
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] .a-plus-analysis-card-marker) {
            min-height: 178px;
            padding: 0.62rem 0.68rem 0.52rem !important;
            border: 1px solid rgba(132, 111, 255, 0.18) !important;
            border-radius: 14px !important;
            border-color: rgba(132, 111, 255, 0.18) !important;
            background: rgba(10, 18, 38, 0.68) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.a-plus-auto-fill-card-marker),
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] .a-plus-auto-fill-card-marker) {
            min-height: 210px;
            padding: 0.62rem 0.68rem 0.52rem !important;
            border: 1px solid rgba(132, 111, 255, 0.18) !important;
            border-radius: 14px !important;
            border-color: rgba(132, 111, 255, 0.18) !important;
            background: rgba(10, 18, 38, 0.68) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.a-plus-analysis-card-marker) .stButton,
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] .a-plus-analysis-card-marker) .stButton,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.a-plus-auto-fill-card-marker) .stButton,
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] .a-plus-auto-fill-card-marker) .stButton {
            min-height: 34px;
        }
        div[data-testid="stVerticalBlock"]:has(.skin-reference-grid-marker):has(.skin-reference-grid-end)
            div[data-testid="stHorizontalBlock"]:has(.panel-subtitle) {
            align-items: start !important;
        }
        div[data-testid="stVerticalBlock"]:has(.skin-reference-grid-marker):has(.skin-reference-grid-end)
            > div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            min-width: 0 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.skin-reference-grid-marker):has(.skin-reference-grid-end)
            div[data-testid="column"]:has(.upload-preview-root) {
            min-height: 206px !important;
        }
        div[data-testid="stVerticalBlock"]:has(.skin-reference-grid-marker):has(.skin-reference-grid-end)
            div[data-testid="column"]:has(.upload-preview-root) div[data-testid="stVerticalBlock"]:has(.upload-preview-root) {
            width: min(158px, 100%) !important;
        }
        div[data-testid="stVerticalBlock"]:has(.skin-reference-grid-marker):has(.skin-reference-grid-end)
            div[data-testid="column"]:has(.upload-preview-root) iframe {
            max-height: 150px !important;
        }
        div[data-testid="stVerticalBlock"]:has(.skin-reference-grid-marker):has(.skin-reference-grid-end)
            .stRadio [role="radiogroup"] {
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.18rem 0.55rem !important;
        }
        div[data-testid="stVerticalBlock"]:has(.inline-action-row) > div[data-testid="stHorizontalBlock"]:has(.stSelectbox):has(.stButton) {
            align-items: end !important;
            display: grid !important;
            grid-template-columns: minmax(220px, 1fr) minmax(160px, 0.72fr) !important;
        }
        div[data-testid="stVerticalBlock"]:has(.inline-action-row) > div[data-testid="stHorizontalBlock"]:has(.stSelectbox):has(.stButton)
            > div[data-testid="column"] {
            width: 100% !important;
            min-width: 0 !important;
        }
        .stRadio [role="radiogroup"] {
            gap: 0.18rem !important;
        }
        .stRadio [role="radiogroup"] label {
            min-height: 28px !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        .compact-thumb img {
            border-radius: 12px !important;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .clickable-image-grid {
            display: grid;
            gap: 0.5rem;
            margin-bottom: 0.5rem;
        }
        .clickable-image-card {
            display: block;
            border-radius: 12px;
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
        div[data-testid="stFileUploader"]:has([aria-label="继续上传"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "继续上传";
        }
        div[data-testid="stFileUploader"]:has([aria-label="重新上传"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "重新上传";
        }
        div[data-testid="stFileUploader"]:has([aria-label="上传图片"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "上传图片";
        }
        div[data-testid="stFileUploader"]:has([aria-label="上传参考图"]) [data-testid="stFileUploaderDropzone"]::after {
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
            padding: 2.75rem 0.8rem;
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
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }
        .stButton > button,
        [data-testid="stFileUploaderDropzone"] {
            min-width: 0 !important;
        }
        [data-testid="stFileUploaderDropzone"]::after {
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            padding: 0 0.35rem;
            box-sizing: border-box;
        }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stFileUploader"]):has(.stButton) > div[data-testid="column"] {
            width: 100% !important;
            min-width: 0 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root) {
            position: relative;
            margin-bottom: 0.35rem;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root) .upload-preview-root {
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
        }
        div[data-testid="element-container"]:has(.upload-replace-uploader-marker) {
            display: none !important;
        }
        div[data-testid="element-container"]:has(.upload-replace-uploader-marker) + div[data-testid="element-container"] {
            position: static !important;
            display: block !important;
            width: 100% !important;
            height: auto !important;
            margin: 0.34rem 0 0 !important;
            padding: 0 !important;
            opacity: 1 !important;
            pointer-events: auto !important;
        }
        div[data-testid="element-container"]:has(.upload-replace-uploader-marker) + div[data-testid="element-container"] [data-testid="stFileUploaderDropzone"] {
            min-height: 30px !important;
            height: 30px !important;
            border-radius: 10px !important;
            background: rgba(10, 19, 38, 0.9) !important;
        }
        div[data-testid="element-container"]:has(.upload-replace-uploader-marker) + div[data-testid="element-container"] [data-testid="stFileUploaderDropzone"]::after {
            content: "替换图片" !important;
        }
        div[data-testid="element-container"]:has(.upload-add-marker) + div[data-testid="element-container"] [data-testid="stFileUploaderDropzone"]::after {
            content: "添加图片" !important;
        }
        div[data-testid="element-container"]:has(.upload-more-marker) + div[data-testid="element-container"] [data-testid="stFileUploaderDropzone"]::after {
            content: "继续添加" !important;
        }
        div[data-testid="stFileUploader"]:has([aria-label="替换图片"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "替换图片";
        }
        .upload-replace-hotspot {
            position: fixed !important;
            z-index: 999998 !important;
            margin: 0 !important;
            padding: 0 !important;
            opacity: 0;
            pointer-events: none;
            display: block !important;
            transition: opacity 0.14s ease;
        }
        body.upload-file-dragging .upload-replace-hotspot {
            opacity: 1;
            pointer-events: auto;
        }
        .upload-replace-hotspot {
            border: 2px solid rgba(126, 96, 255, 0.94) !important;
            border-radius: 14px !important;
            background: rgba(8, 15, 31, 0.72) !important;
            box-shadow: 0 0 0 9999px rgba(3, 8, 22, 0.14);
            backdrop-filter: blur(2px);
        }
        .upload-replace-hotspot::after {
            content: "松开替换图片" !important;
            color: #ffffff;
            font-size: 0.82rem;
            font-weight: 700;
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        div[data-testid="element-container"].upload-replace-overlay {
            position: fixed !important;
            z-index: 999999 !important;
            display: block !important;
            margin: 0 !important;
            padding: 0 !important;
            opacity: 0.01;
            pointer-events: none;
        }
        body.upload-file-dragging div[data-testid="element-container"].upload-replace-overlay {
            pointer-events: auto;
        }
        div[data-testid="element-container"].upload-replace-overlay [data-testid="stFileUploader"],
        div[data-testid="element-container"].upload-replace-overlay [data-testid="stFileUploader"] > section,
        div[data-testid="element-container"].upload-replace-overlay [data-testid="stFileUploaderDropzone"] {
            width: 100% !important;
            height: 100% !important;
            min-height: 100% !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker) {
            display: none !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) {
            position: absolute !important;
            z-index: 20;
            top: 6px !important;
            right: 6px !important;
            width: 28px !important;
            height: 28px !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
            display: block !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) [data-testid="stButton"],
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) [data-testid="stTooltipIcon"],
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) [data-testid="stTooltipHoverTarget"] {
            width: 28px !important;
            height: 28px !important;
            min-width: 28px !important;
            min-height: 28px !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) button {
            min-height: 28px !important;
            height: 28px !important;
            min-width: 28px !important;
            width: 28px !important;
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
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) button:hover {
            background: rgba(255, 36, 74, 1) !important;
            border-color: rgba(255, 255, 255, 1) !important;
            color: #ffffff !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) button p {
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
            font-size: 0.92rem;
            font-weight: 700;
            margin-bottom: 0.48rem;
        }
        .canvas-flow-summary {
            display: flex;
            flex-wrap: wrap;
            gap: 0.36rem;
            margin: 0 0 0.58rem;
        }
        .canvas-flow-chip {
            display: inline-flex;
            align-items: center;
            padding: 0.22rem 0.52rem;
            border-radius: 999px;
            color: #e8eaff;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.08);
            font-size: 0.72rem;
            line-height: 1.3;
        }
        div[data-testid="column"]:has(.canvas-right-column-marker) {
            align-self: flex-start !important;
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            background:
                radial-gradient(circle at top right, rgba(132, 111, 255, 0.12), transparent 30%),
                rgba(6, 14, 29, 0.72);
            padding: 0.72rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
        }
        div[data-testid="stVerticalBlock"] {
            gap: 0.42rem !important;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.62rem !important;
        }
        div[data-testid="element-container"] {
            margin-bottom: 0.18rem !important;
        }
        .stSlider {
            padding-top: 0 !important;
            padding-bottom: 0.12rem !important;
        }
        .stSlider label p,
        .stTextArea label p,
        .stSelectbox label p,
        .stRadio label p {
            color: rgba(225, 229, 255, 0.82) !important;
            font-size: 0.76rem !important;
            font-weight: 600 !important;
        }
        .stSlider [data-baseweb="slider"] {
            padding-top: 0.15rem !important;
            padding-bottom: 0.15rem !important;
        }
        [data-testid="stCaptionContainer"] {
            font-size: 0.72rem !important;
            line-height: 1.35 !important;
        }
        @media (max-width: 900px) {
            .main .block-container {
                padding-left: 0.55rem;
                padding-right: 0.55rem;
            }
            .feature-title {
                font-size: 1.28rem;
            }
            .workspace-panel {
                padding: 0.62rem;
            }
            .workflow-strip {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .workflow-step:last-child {
                grid-column: span 2;
            }
            .workflow-step::after {
                display: none !important;
            }
            div[data-testid="column"]:has(.batch-right-column-marker) .result-empty {
                min-height: 250px;
            }
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.main-action-dock-marker),
            div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] .main-action-dock-marker) {
                position: relative;
                top: auto;
            }
            div[data-testid="stVerticalBlock"]:has(.a-plus-mode-selector-marker) .stRadio [role="radiogroup"] {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.a-plus-template-card-marker),
            div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] .a-plus-template-card-marker) {
                min-height: 224px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_clipboard_paste_support() -> None:
    components.html(
        """
        <script>
        (function () {
          const hostWindow = window.parent;
          const hostDocument = hostWindow && hostWindow.document;
          if (!hostWindow || !hostDocument || hostWindow.__lashforgePasteSupportInstalled) {
            return;
          }
          hostWindow.__lashforgePasteSupportInstalled = true;
          hostWindow.__lashforgeLastUploaderInput = null;

          function isVisible(element) {
            if (!element || !(element instanceof hostWindow.HTMLElement)) {
              return false;
            }
            const style = hostWindow.getComputedStyle(element);
            if (!style || style.display === "none" || style.visibility === "hidden") {
              return false;
            }
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          }

          function findUploaderInputFromNode(node) {
            let current = node;
            while (current && current !== hostDocument.body) {
              if (typeof current.querySelector === "function") {
                const input = current.querySelector('input[type="file"]');
                if (input && isVisible(input) && !input.disabled) {
                  return input;
                }
              }
              current = current.parentElement;
            }
            return null;
          }

          function getVisibleFileInputs() {
            return Array.from(hostDocument.querySelectorAll('input[type="file"]')).filter(function (input) {
              return isVisible(input) && !input.disabled;
            });
          }

          function resolveTargetInput() {
            const active = hostDocument.activeElement;
            if (active && active.tagName === "INPUT" && active.type === "file" && isVisible(active) && !active.disabled) {
              return active;
            }
            const remembered = hostWindow.__lashforgeLastUploaderInput;
            if (remembered && isVisible(remembered) && !remembered.disabled) {
              return remembered;
            }
            const visibleInputs = getVisibleFileInputs();
            return visibleInputs.length ? visibleInputs[0] : null;
          }

          function showToast(message) {
            let toast = hostDocument.getElementById("lashforge-paste-toast");
            if (!toast) {
              toast = hostDocument.createElement("div");
              toast.id = "lashforge-paste-toast";
              toast.style.cssText = [
                "position:fixed",
                "right:18px",
                "bottom:18px",
                "z-index:999999",
                "padding:10px 14px",
                "border-radius:12px",
                "background:rgba(10,18,36,0.92)",
                "border:1px solid rgba(126,166,255,0.28)",
                "color:#eef4ff",
                "font-size:12px",
                "box-shadow:0 12px 34px rgba(0,0,0,0.28)",
                "opacity:0",
                "transition:opacity .18s ease"
              ].join(";");
              hostDocument.body.appendChild(toast);
            }
            toast.textContent = message;
            toast.style.opacity = "1";
            hostWindow.clearTimeout(hostWindow.__lashforgePasteToastTimer);
            hostWindow.__lashforgePasteToastTimer = hostWindow.setTimeout(function () {
              toast.style.opacity = "0";
            }, 1800);
          }

          hostDocument.addEventListener("pointerdown", function (event) {
            const input = findUploaderInputFromNode(event.target);
            if (input) {
              hostWindow.__lashforgeLastUploaderInput = input;
            }
          }, true);

          hostDocument.addEventListener("mouseover", function (event) {
            const input = findUploaderInputFromNode(event.target);
            if (input) {
              hostWindow.__lashforgeLastUploaderInput = input;
            }
          }, true);

          hostDocument.addEventListener("paste", async function (event) {
            const clipboard = event.clipboardData;
            if (!clipboard || !clipboard.items || !clipboard.items.length) {
              return;
            }
            const imageFiles = Array.from(clipboard.items)
              .filter(function (item) { return item.kind === "file" && /^image\\//i.test(item.type || ""); })
              .map(function (item) { return item.getAsFile(); })
              .filter(Boolean);
            if (!imageFiles.length) {
              return;
            }
            const targetInput = resolveTargetInput();
            if (!targetInput) {
              showToast("未找到可粘贴的图片上传区域");
              return;
            }
            try {
              const transfer = new hostWindow.DataTransfer();
              imageFiles.forEach(function (file) {
                transfer.items.add(file);
              });
              targetInput.files = transfer.files;
              targetInput.dispatchEvent(new hostWindow.Event("change", { bubbles: true }));
              targetInput.dispatchEvent(new hostWindow.Event("input", { bubbles: true }));
              event.preventDefault();
              showToast(imageFiles.length > 1 ? "已粘贴图片到上传区域" : "已粘贴图片到当前上传区域");
            } catch (error) {
              showToast("粘贴图片失败，请改用上传按钮");
            }
          }, true);
        })();
        </script>
        """,
        height=0,
    )


def inject_upload_drag_replace_support() -> None:
    components.html(
        """
        <script>
        (function () {
          const hostWindow = window.parent;
          const hostDocument = hostWindow && hostWindow.document;
          const installVersion = "native-overlay-uploader-v5";
          if (!hostWindow || !hostDocument || hostWindow.__lashforgeUploadReplaceInstalled === installVersion) {
            return;
          }
          hostWindow.__lashforgeUploadReplaceInstalled = installVersion;

          function hasImageFile(event) {
            const items = Array.from((event.dataTransfer && event.dataTransfer.items) || []);
            if (items.some((item) => item.kind === "file" && /^image\\//i.test(item.type || ""))) {
              return true;
            }
            return Array.from((event.dataTransfer && event.dataTransfer.files) || [])
              .some((file) => /^image\\//i.test(file.type || ""));
          }

          function getElementContainer(node) {
            return node && node.closest('div[data-testid="element-container"]');
          }

          function getPreviewContainer(marker) {
            let current = getElementContainer(marker);
            while (current && current.nextElementSibling) {
              current = current.nextElementSibling;
              if (current.querySelector && current.querySelector(".upload-replace-uploader-marker")) {
                return null;
              }
              const rect = current.getBoundingClientRect();
              if (rect.width > 24 && rect.height > 24) {
                return current;
              }
            }
            return null;
          }

          function getReplacementUploaderContainer(marker) {
            let current = getElementContainer(marker);
            while (current && current.nextElementSibling) {
              current = current.nextElementSibling;
              if (current.querySelector && current.querySelector(".upload-replace-uploader-marker")) {
                return current.nextElementSibling || null;
              }
            }
            return null;
          }

          function clearHotspots() {
            hostDocument.querySelectorAll(".upload-replace-hotspot").forEach((node) => node.remove());
            hostDocument.querySelectorAll(".upload-replace-overlay").forEach((node) => {
              node.classList.remove("upload-replace-overlay");
              node.style.left = "";
              node.style.top = "";
              node.style.width = "";
              node.style.height = "";
            });
          }

          function createReplaceHotspots() {
            clearHotspots();
            hostDocument.querySelectorAll(".upload-preview-root").forEach((marker) => {
              const preview = getPreviewContainer(marker);
              const uploader = getReplacementUploaderContainer(marker);
              if (!preview || !uploader) return;
              const rect = preview.getBoundingClientRect();
              if (rect.width < 24 || rect.height < 24) return;
              uploader.classList.add("upload-replace-overlay");
              uploader.style.left = `${rect.left}px`;
              uploader.style.top = `${rect.top}px`;
              uploader.style.width = `${rect.width}px`;
              uploader.style.height = `${rect.height}px`;
              const hotspot = hostDocument.createElement("div");
              hotspot.className = "upload-replace-hotspot";
              hotspot.style.left = `${rect.left}px`;
              hotspot.style.top = `${rect.top}px`;
              hotspot.style.width = `${rect.width}px`;
              hotspot.style.height = `${rect.height}px`;
              hostDocument.body.appendChild(hotspot);
            });
          }

          function enableReplaceLayer(event) {
            if (!hasImageFile(event)) return;
            createReplaceHotspots();
            hostDocument.body.classList.add("upload-file-dragging");
          }

          function disableReplaceLayer() {
            hostWindow.setTimeout(function () {
              hostDocument.body.classList.remove("upload-file-dragging");
              clearHotspots();
            }, 180);
          }

          hostDocument.addEventListener("dragenter", enableReplaceLayer, true);
          hostDocument.addEventListener("dragover", enableReplaceLayer, true);
          hostDocument.addEventListener("drop", disableReplaceLayer, true);
          hostDocument.addEventListener("dragend", disableReplaceLayer, true);
          hostDocument.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
              hostDocument.body.classList.remove("upload-file-dragging");
            }
          }, true);
          hostWindow.addEventListener("scroll", disableReplaceLayer, true);
          hostWindow.addEventListener("resize", disableReplaceLayer, true);
        })();
        </script>
        """,
        height=0,
    )


def build_prompt(feature: dict[str, Any], custom_prompt: str, aspect_ratio: str, extra_notes: str) -> str:
    sections = [
        f"当前执行功能：{feature['name']}",
        feature.get("default_prompt", ""),
    ]
    if feature.get("key") in A_PLUS_IMAGES_API_FEATURE_KEYS:
        size_text = str(feature.get("target_size_text", "")).strip()
        if not size_text:
            target_size = feature.get("target_size")
            if isinstance(target_size, (tuple, list)) and len(target_size) == 2:
                size_text = f"{int(target_size[0])}*{int(target_size[1])}"
        if size_text:
            if feature.get("key") == MAIN_IMAGE_A_PLUS_FEATURE_KEY:
                sections.append(f"最终连续长图成品尺寸必须严格等于 {size_text}px，尺寸信息不得出现在画面中。")
            else:
                sections.append(f"最终输出尺寸必须严格等于 {size_text}px。")
    elif feature.get("key") == "outpaint":
        sections.append(
            "最终输出必须采用扩展后的目标画幅，并由模型一次生成完整连续画面；禁止把原图作为矩形图层覆盖或拼接回结果。"
        )
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
        "This is direct, one-pass directional outpainting from the uploaded original image. "
        f"Extend the apparent camera canvas according to these framing instructions: {direction_text}. "
        "The pixel amounts describe how much additional visual space is needed on each side; they must never appear as blank bands, frames, overlays, or separate image regions. "
        "Use the uploaded image directly as the source photograph and synthesize the entire final frame coherently in one generation. "
        "Do not make a transparent padded canvas, do not paste the original back afterward, and do not reproduce the source as a smaller rectangle inside a larger generated image. "
        "Do not create any visible rectangle around the former image bounds, including hard seams, straight tonal changes, borders, frames, inset-photo edges, picture-in-picture layouts, or abrupt texture boundaries. "
        "Keep the original subject at the proportional position implied by the requested directional expansion, while reducing its occupancy of the final frame enough to reveal the requested new surroundings. "
        "Do not add visual space on a side where no expansion value is specified. "
        "The output must be one coherent, continuous photograph, not a collage, split-frame, multi-panel layout, or duplicated scene. "
        "If the expanded area involves the head, face, chin, forehead, hairline, ears, neck, or facial contour, the completion must remain a realistic natural human face and anatomically correct human structure. "
        "It is strictly forbidden to turn the face into a non-human face, mask-like face, cartoon face, fake face, distorted facial features, misaligned features, duplicated features, blurred face, or abstract texture. "
        "The completed face must remain the same person as in the original image, with continuous consistency in facial proportions, face shape, skin texture, skin tone, makeup, hairstyle, expression, apparent age, and real photographic quality. "
        "Preserve the original subject identity, facial features, pose, clothing, details, composition, and sharpness as closely as possible while generating the larger continuous frame. "
        "The newly expanded area must remain sharp, high-definition, and detailed, matching the focus and texture clarity of the original photo. "
        "Do not apply blur, haze, soft-focus, low-resolution texture, smeared details, over-smoothing, or feathered softness to either the original image or the new expanded area. "
        "Every former image boundary must disappear through coherent scene generation, not through copy-paste, rectangular compositing, blurring, or smudging. "
        "Never stretch, smear, mirror, tile, clone, or repeat the border pixels of the original image. "
        "For left or right expansion on portrait/selfie/model photos, the newly expanded side margins should primarily be natural background continuation: room wall, furniture, shadows, lighting, depth, and environmental texture. "
        "Do not place any extra hands, arms, sleeves, shoulders, chest, torso fragments, skin patches, hair fragments, duplicate face, duplicate person, duplicate clothing, or cropped body parts in the new side margins. "
        "If the original image already contains a hand, arm, sleeve, or clothing edge near a border, do not mirror, clone, stretch, or continue it into the expanded blank margin; keep the original body part only inside the original image area and complete the new margin as background unless a single anatomically correct continuation is unavoidable. "
        "The result must contain exactly one main person, with no repeated limbs and no duplicated subject fragments. "
        "The outpainted result must be visually seamless and avoid rectangular joins, breaks, repeated textures, stretched deformation, blur, softness, or obvious AI-generated artifacts."
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
    hd_prompt = build_portrait_hd_prompt(prompt)
    try:
        result = call_openrouter_images_api(
            model=model,
            prompt=hd_prompt,
            aspect_ratio=aspect_ratio,
            uploaded_files=portrait_inputs,
            resolution=PORTRAIT_HD_DEFAULT_IMAGE_SIZE,
        )
        result["channel"] = "Images API 原生 4K"
        return result
    except Exception as exc:
        raise RuntimeError(
            "OpenRouter Images API 原生 4K 调用失败。为避免画质降级，本次未使用聊天兼容通道或本地放大。"
            f"原因：{exc}"
        ) from exc


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


def format_openrouter_error_message(error_message: Any) -> str:
    raw_message = str(error_message or "").strip()
    if not raw_message:
        return "OpenRouter 请求失败：服务返回了空错误信息。"
    cleaned_message = re.sub(r"https?://\S+", "", raw_message).strip()
    normalized_message = cleaned_message.lower()
    if "downloaded image content cannot exceed 30mb" in normalized_message or "cannot exceed 30mb" in normalized_message:
        return "OpenRouter 输入图片超过 30MB，系统已加入自动压缩处理，请重新提交任务。"
    if "key limit exceeded" in normalized_message or "daily limit" in normalized_message:
        return "OpenRouter 今日额度已用完，请更换可用的 API Key，或等待每日额度重置后再试。"
    if "rate limit" in normalized_message:
        return "OpenRouter 当前请求过于频繁，请稍等一会儿再试。"
    return f"OpenRouter 请求失败：{cleaned_message}"


def format_user_facing_error_message(error_message: Any) -> str:
    raw_message = str(error_message or "").strip()
    if not raw_message:
        return "任务失败，请稍后重试。"
    normalized_message = raw_message.lower()
    if "openrouter" in normalized_message or "key limit exceeded" in normalized_message or "daily limit" in normalized_message:
        if "key limit exceeded" in normalized_message or "daily limit" in normalized_message:
            return "OpenRouter 今日额度已用完，请更换可用的 API Key，或等待每日额度重置后再试。"
        return format_openrouter_error_message(raw_message.replace("OpenRouter 请求失败：", "", 1))
    return re.sub(r"https?://\S+", "", raw_message).strip()


def call_openrouter_images_api(
    model: str,
    prompt: str,
    uploaded_files: list[Any] | None = None,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    resolution: str = "",
    max_attempts: int | None = None,
) -> dict[str, Any]:
    """Call OpenRouter's dedicated Images API with correctly shaped references."""
    api_key = load_api_key()
    if not api_key:
        raise RuntimeError("未找到 OPENROUTER_API_KEY，请先完成配置。")

    input_references: list[dict[str, Any]] = []
    for uploaded_file in list(uploaded_files or []):
        safe_uploaded_file = prepare_openrouter_uploaded_input(uploaded_file)
        input_references.append(
            {
                "type": "image_url",
                "image_url": {"url": file_to_data_url(safe_uploaded_file)},
            }
        )

    payload: dict[str, Any] = {
        "model": str(model or "").strip(),
        "prompt": str(prompt or "").strip(),
    }
    if input_references:
        payload["input_references"] = input_references
    normalized_resolution = str(resolution or "").strip().upper()
    if normalized_resolution in GEMINI_IMAGE_SIZES or normalized_resolution == "512":
        payload["resolution"] = normalized_resolution
    normalized_aspect_ratio = str(aspect_ratio or "").strip()
    if normalized_aspect_ratio in GEMINI_IMAGE_ASPECT_RATIOS:
        payload["aspect_ratio"] = normalized_aspect_ratio

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://127.0.0.1:10808",
        "X-Title": "OpenRouter Image Workspace",
    }
    response = None
    last_request_error: requests.RequestException | None = None
    normalized_max_attempts = max(int(max_attempts or OPENROUTER_IMAGES_MAX_ATTEMPTS), 1)
    for attempt_index in range(normalized_max_attempts):
        try:
            response = requests.post(
                OPENROUTER_IMAGES_URL,
                headers=headers,
                json=payload,
                **get_external_request_kwargs(
                    timeout=(
                        OPENROUTER_IMAGES_CONNECT_TIMEOUT_SECONDS,
                        OPENROUTER_IMAGES_READ_TIMEOUT_SECONDS,
                    )
                ),
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_request_error = exc
            if attempt_index + 1 >= normalized_max_attempts:
                raise RuntimeError(
                    f"OpenRouter Images API 连接失败，已自动尝试 {normalized_max_attempts} 次：{exc}"
                ) from exc
            retry_delay = OPENROUTER_IMAGES_RETRY_DELAYS[
                min(attempt_index, len(OPENROUTER_IMAGES_RETRY_DELAYS) - 1)
            ]
            time.sleep(retry_delay)
            continue
        except requests.RequestException as exc:
            raise RuntimeError(f"OpenRouter Images API 连接失败：{exc}") from exc
        if (
            response.status_code in OPENROUTER_IMAGES_TRANSIENT_STATUS_CODES
            and attempt_index + 1 < normalized_max_attempts
        ):
            retry_delay = OPENROUTER_IMAGES_RETRY_DELAYS[
                min(attempt_index, len(OPENROUTER_IMAGES_RETRY_DELAYS) - 1)
            ]
            time.sleep(retry_delay)
            continue
        break
    if response is None:
        raise RuntimeError(f"OpenRouter Images API 连接失败：{last_request_error or '未收到响应'}")

    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"OpenRouter Images API 返回了无法解析的内容（HTTP {response.status_code}）。") from exc
    if response.status_code >= 400:
        error_payload = data.get("error") if isinstance(data, dict) else data
        if isinstance(error_payload, dict):
            error_message = error_payload.get("message") or error_payload
        else:
            error_message = error_payload
        raise RuntimeError(f"OpenRouter Images API 请求失败：{error_message}")

    images: list[str] = []
    for item in list(data.get("data") or []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        encoded_image = str(item.get("b64_json") or "").strip()
        if encoded_image:
            media_type = str(item.get("media_type") or "image/png").strip() or "image/png"
            images.append(f"data:{media_type};base64,{encoded_image}")
            continue
        image_url = str(item.get("url") or "").strip()
        if image_url:
            images.append(image_url)
    if not images:
        raise RuntimeError("OpenRouter Images API 没有返回可用图片。")
    return {
        "images": images,
        "text": "",
        "raw": data,
        "requested_resolution": normalized_resolution,
    }


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
        safe_uploaded_file = prepare_openrouter_uploaded_input(uploaded_file)
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": file_to_data_url(safe_uploaded_file)},
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


def cover_image_to_exact_size(image_url: str, target_width: int, target_height: int) -> str:
    """Fit A+ output to the exact size without cropping any generated edge."""
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = ImageOps.exif_transpose(image).convert("RGB")
            safe_target_width = max(int(target_width), 1)
            safe_target_height = max(int(target_height), 1)
            # The closest supported native ratio may still differ slightly from the
            # requested A+ canvas. Resize the complete frame instead of sacrificing
            # text, logos, products, or background from any of the four edges.
            fitted = converted.resize(
                (safe_target_width, safe_target_height),
                Image.Resampling.LANCZOS,
            )
            output = io.BytesIO()
            fitted.save(output, format="PNG")
        return image_bytes_to_data_url(output.getvalue(), "image/png")
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc).startswith("图片下载失败："):
            raise
        raise RuntimeError(f"本地处理失败：完整 A+ 已返回，但在保留四边画面的规格适配时出错。{exc}") from exc


def parse_size_text(size_text: str) -> tuple[int, int] | None:
    normalized = size_text.strip().lower().replace("x", "*").replace("×", "*")
    match = re.fullmatch(r"(\d{2,5})\*(\d{2,5})", normalized)
    if not match:
        return None
    width = int(match.group(1))
    height = int(match.group(2))
    if (
        width <= 0
        or height <= 0
        or width > AMAZON_A_PLUS_MAX_EDGE
        or height > AMAZON_A_PLUS_MAX_EDGE
        or width * height > AMAZON_A_PLUS_MAX_PIXELS
    ):
        return None
    return width, height


def build_amazon_a_plus_layered_result(
    result: dict[str, Any],
    target_size: tuple[int, int] | None,
) -> dict[str, Any]:
    image_sources = list(result.get("images") or [])
    if not image_sources:
        raise RuntimeError("模型没有返回可用于分层的绿幕 A+ 底稿。")

    image_bytes, _mime_type = load_image_bytes_from_url(str(image_sources[0]))
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            green_screen = ImageOps.exif_transpose(image).convert("RGBA")
    except Exception as exc:
        raise RuntimeError(f"无法读取模型返回的绿幕 A+ 底稿：{exc}") from exc

    source_generation_size = green_screen.size
    if target_size:
        green_screen = fit_green_screen_to_canvas(
            green_screen,
            (int(target_size[0]), int(target_size[1])),
        ).convert("RGBA")

    try:
        layered = build_layered_a_plus(green_screen)
    except Exception as exc:
        raise RuntimeError(f"绿幕元素自动裁切失败：{exc}") from exc

    green_buffer = io.BytesIO()
    green_screen.save(green_buffer, format="PNG")
    layer_count = int(layered.get("layer_count") or 0)
    psd_file_name = f"amazon_a_plus_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.psd"
    processed_result = dict(result)
    processed_result["images"] = [
        image_bytes_to_data_url(bytes(layered["composite_png"]), "image/png")
    ]
    processed_result["green_screen_images"] = [
        image_bytes_to_data_url(green_buffer.getvalue(), "image/png")
    ]
    processed_result["layer_count"] = layer_count
    processed_result["layer_manifest"] = list(layered.get("layer_manifest") or [])
    processed_result["source_generation_size"] = source_generation_size
    processed_result["psd_bytes"] = bytes(layered["psd_bytes"])
    processed_result["psd_file_name"] = psd_file_name
    original_text = str(result.get("text") or "").strip()
    processed_result["text"] = "\n\n".join(
        part
        for part in (
            original_text,
            f"高清底稿尺寸为 {source_generation_size[0]}*{source_generation_size[1]}px，已按比例适配到目标画布。",
            f"已从绿幕底稿中识别并生成 {layer_count} 个独立可编辑图层。",
        )
        if part
    )
    return processed_result


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


def render_outpaint_extension_preview_card(
    uploaded_file: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    component_key: str,
    max_preview_edge: int = 760,
    drag_state_keys: dict[str, str] | None = None,
) -> None:
    try:
        image_bytes = get_uploaded_file_bytes(uploaded_file)
        with Image.open(io.BytesIO(image_bytes)) as image:
            source = ImageOps.exif_transpose(image).convert("RGBA")
            source_w, source_h = source.size
    except Exception:
        st.caption("扩图预览暂时无法显示，可继续调整参数后处理。")
        return

    limits = get_outpaint_extension_limits(uploaded_file)
    top_px = max(0, min(limits["top"], int(top_px)))
    bottom_px = max(0, min(limits["bottom"], int(bottom_px)))
    left_px = max(0, min(limits["left"], int(left_px)))
    right_px = max(0, min(limits["right"], int(right_px)))
    max_preview_edge = max(260, int(max_preview_edge))
    is_draggable = bool(drag_state_keys)
    top_band = float(limits["top"] if is_draggable else top_px)
    bottom_band = float(limits["bottom"] if is_draggable else bottom_px)
    left_band = float(limits["left"] if is_draggable else left_px)
    right_band = float(limits["right"] if is_draggable else right_px)
    canvas_w = max(source_w + left_band + right_band, 1)
    canvas_h = max(source_h + top_band + bottom_band, 1)
    scale = min(max_preview_edge / canvas_w, max_preview_edge / canvas_h)
    display_w = max(1, int(round(canvas_w * scale)))
    display_h = max(1, int(round(canvas_h * scale)))
    source_x = round(left_band * scale, 2)
    source_y = round(top_band * scale, 2)
    display_source_w = max(1, int(round(source_w * scale)))
    display_source_h = max(1, int(round(source_h * scale)))
    has_extension = (top_px + bottom_px + left_px + right_px) > 0
    current_left = int(round((left_band - left_px) * scale)) if is_draggable else 1
    current_top = int(round((top_band - top_px) * scale)) if is_draggable else 1
    current_right = int(round((left_band + source_w + right_px) * scale)) if is_draggable else max(display_w - 2, 1)
    current_bottom = int(round((top_band + source_h + bottom_px) * scale)) if is_draggable else max(display_h - 2, 1)

    preview_canvas = Image.new("RGBA", (display_w, display_h), (0, 0, 0, 0))
    resized_source = source.resize((display_source_w, display_source_h), Image.Resampling.LANCZOS)
    preview_canvas.alpha_composite(resized_source, (int(round(source_x)), int(round(source_y))))
    draw = ImageDraw.Draw(preview_canvas)

    def draw_dashed_rectangle(box: tuple[int, int, int, int], color: tuple[int, int, int, int]) -> None:
        left, top, right, bottom = box
        dash = 10
        gap = 7
        width = 2
        for x in range(left, right, dash + gap):
            draw.line((x, top, min(x + dash, right), top), fill=color, width=width)
            draw.line((x, bottom, min(x + dash, right), bottom), fill=color, width=width)
        for y in range(top, bottom, dash + gap):
            draw.line((left, y, left, min(y + dash, bottom)), fill=color, width=width)
            draw.line((right, y, right, min(y + dash, bottom)), fill=color, width=width)

    if has_extension and not is_draggable:
        draw_dashed_rectangle((1, 1, max(display_w - 2, 1), max(display_h - 2, 1)), (139, 117, 255, 245))
    source_left = int(round(source_x)) + 1
    source_top = int(round(source_y)) + 1
    draw_dashed_rectangle(
        (
            source_left,
            source_top,
            max(source_left + display_source_w - 2, source_left + 1),
            max(source_top + display_source_h - 2, source_top + 1),
        ),
        (255, 255, 255, 235),
    )
    output = io.BytesIO()
    preview_canvas.save(output, format="PNG")
    preview_src = image_bytes_to_data_url(output.getvalue(), "image/png")
    if not is_draggable:
        st.image(output.getvalue(), width=display_w)
        return

    drag_payload = {
        "keys": dict(drag_state_keys or {}),
        "top": top_px,
        "bottom": bottom_px,
        "left": left_px,
        "right": right_px,
        "limits": limits,
        "step": 50,
        "source_width": source_w,
        "source_height": source_h,
        "scale": scale,
        "display_width": display_w,
        "display_height": display_h,
        "current_left": current_left,
        "current_top": current_top,
        "current_right": current_right,
        "current_bottom": current_bottom,
        "query_key": OUTPAINT_DRAG_QUERY_KEY,
    }
    drag_json = json.dumps(drag_payload, ensure_ascii=False)
    html_content = f"""
    <div id="{component_key}" class="outpaint-drag-root">
      <div class="outpaint-drag-stage">
        <img class="outpaint-drag-img" src="{preview_src}" alt="扩图范围预览">
        <div class="outpaint-current-box">
          <div class="drag-edge drag-top" data-edge="top"></div>
          <div class="drag-edge drag-bottom" data-edge="bottom"></div>
          <div class="drag-edge drag-left" data-edge="left"></div>
          <div class="drag-edge drag-right" data-edge="right"></div>
          <div class="drag-corner drag-top-left" data-edge="top-left"></div>
          <div class="drag-corner drag-top-right" data-edge="top-right"></div>
          <div class="drag-corner drag-bottom-left" data-edge="bottom-left"></div>
          <div class="drag-corner drag-bottom-right" data-edge="bottom-right"></div>
        </div>
      </div>
      <div class="outpaint-drag-values">
        <span>上 <b data-value="top"></b></span>
        <span>下 <b data-value="bottom"></b></span>
        <span>左 <b data-value="left"></b></span>
        <span>右 <b data-value="right"></b></span>
      </div>
    </div>
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        background: transparent;
        color: rgba(245, 247, 255, 0.92);
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      #{component_key} {{
        width: {display_w}px;
        max-width: 100%;
        margin: 0 auto;
      }}
      #{component_key} .outpaint-drag-stage {{
        position: relative;
        width: min({display_w}px, 100%);
        aspect-ratio: {display_w} / {display_h};
        height: auto;
        max-width: 100%;
        background: rgba(4, 10, 24, 0.56);
        border-radius: 12px;
        overflow: hidden;
        touch-action: none;
      }}
      #{component_key} .outpaint-drag-img {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: contain;
        user-select: none;
        -webkit-user-drag: none;
        pointer-events: none;
      }}
      #{component_key} .outpaint-current-box {{
        position: absolute;
        box-sizing: border-box;
        border: 2px dashed rgba(139, 117, 255, 0.98);
        box-shadow: 0 0 0 1px rgba(139, 117, 255, 0.35), 0 0 18px rgba(139, 117, 255, 0.35);
        overflow: visible;
      }}
      #{component_key} .drag-edge {{
        position: absolute;
        background: rgba(139, 117, 255, 0.18);
      }}
      #{component_key} .drag-corner {{
        position: absolute;
        width: 18px;
        height: 18px;
        border-radius: 999px;
        background: rgba(139, 117, 255, 0.98);
        border: 2px solid rgba(255, 255, 255, 0.95);
        box-shadow: 0 0 16px rgba(139, 117, 255, 0.55);
        z-index: 3;
      }}
      #{component_key} .drag-edge:hover,
      #{component_key} .drag-corner:hover {{
        background: rgba(160, 139, 255, 1);
      }}
      #{component_key} .drag-top, #{component_key} .drag-bottom {{
        left: -8px;
        right: -8px;
        height: 16px;
        cursor: ns-resize;
      }}
      #{component_key} .drag-top {{ top: -9px; }}
      #{component_key} .drag-bottom {{ bottom: -9px; }}
      #{component_key} .drag-left, #{component_key} .drag-right {{
        top: -8px;
        bottom: -8px;
        width: 16px;
        cursor: ew-resize;
      }}
      #{component_key} .drag-left {{ left: -9px; }}
      #{component_key} .drag-right {{ right: -9px; }}
      #{component_key} .drag-top-left {{
        left: -10px;
        top: -10px;
        cursor: nwse-resize;
      }}
      #{component_key} .drag-top-right {{
        right: -10px;
        top: -10px;
        cursor: nesw-resize;
      }}
      #{component_key} .drag-bottom-left {{
        left: -10px;
        bottom: -10px;
        cursor: nesw-resize;
      }}
      #{component_key} .drag-bottom-right {{
        right: -10px;
        bottom: -10px;
        cursor: nwse-resize;
      }}
      #{component_key} .outpaint-drag-values {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 6px;
        margin-top: 8px;
        font-size: 11px;
        color: rgba(214, 219, 255, 0.78);
      }}
      #{component_key} .outpaint-drag-values span {{
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
        padding: 5px 6px;
        background: rgba(7, 15, 31, 0.56);
        text-align: center;
      }}
      #{component_key} .outpaint-drag-values b {{
        color: #ffffff;
      }}
    </style>
    <script>
      const config_{component_key} = {drag_json};
      const root_{component_key} = document.getElementById("{component_key}");
      const stage_{component_key} = root_{component_key}.querySelector(".outpaint-drag-stage");
      const box_{component_key} = root_{component_key}.querySelector(".outpaint-current-box");
      const valueNodes_{component_key} = {{
        top: root_{component_key}.querySelector('[data-value="top"]'),
        bottom: root_{component_key}.querySelector('[data-value="bottom"]'),
        left: root_{component_key}.querySelector('[data-value="left"]'),
        right: root_{component_key}.querySelector('[data-value="right"]'),
      }};
      let values_{component_key} = {{
        top: Number(config_{component_key}.top || 0),
        bottom: Number(config_{component_key}.bottom || 0),
        left: Number(config_{component_key}.left || 0),
        right: Number(config_{component_key}.right || 0),
      }};
      const directionLimit_{component_key} = (direction) => {{
        return Number((config_{component_key}.limits || {{}})[direction] || 0);
      }};
      const roundValue_{component_key} = (value, direction) => {{
        const max = directionLimit_{component_key}(direction);
        const step = Number(config_{component_key}.step || 50);
        const numericValue = Math.max(0, Number(value || 0));
        if (max > 0 && numericValue >= max - step / 2) return max;
        return Math.max(0, Math.min(max, Math.round(numericValue / step) * step));
      }};
      const renderScale_{component_key} = () => {{
        const rect = stage_{component_key}.getBoundingClientRect();
        return {{
          x: Math.max(rect.width, 1) / Math.max(Number(config_{component_key}.display_width || 1), 1),
          y: Math.max(rect.height, 1) / Math.max(Number(config_{component_key}.display_height || 1), 1),
        }};
      }};
      const applyBox_{component_key} = () => {{
        const baseScale = Number(config_{component_key}.scale || 1);
        const stageScale = renderScale_{component_key}();
        const scaleX = baseScale * stageScale.x;
        const scaleY = baseScale * stageScale.y;
        const maxX = directionLimit_{component_key}("left");
        const maxY = directionLimit_{component_key}("top");
        const sourceWidth = Number(config_{component_key}.source_width || 1);
        const sourceHeight = Number(config_{component_key}.source_height || 1);
        const left = (maxX - values_{component_key}.left) * scaleX;
        const top = (maxY - values_{component_key}.top) * scaleY;
        const right = (maxX + sourceWidth + values_{component_key}.right) * scaleX;
        const bottom = (maxY + sourceHeight + values_{component_key}.bottom) * scaleY;
        box_{component_key}.style.left = `${{left}}px`;
        box_{component_key}.style.top = `${{top}}px`;
        box_{component_key}.style.width = `${{Math.max(right - left, 1)}}px`;
        box_{component_key}.style.height = `${{Math.max(bottom - top, 1)}}px`;
        Object.entries(valueNodes_{component_key}).forEach(([key, node]) => {{
          if (node) node.textContent = `${{values_{component_key}[key]}}px`;
        }});
      }};
      const updateFromPointer_{component_key} = (edge, event) => {{
        const rect = stage_{component_key}.getBoundingClientRect();
        const baseScale = Number(config_{component_key}.scale || 1);
        const stageScale = renderScale_{component_key}();
        const scaleX = baseScale * stageScale.x;
        const scaleY = baseScale * stageScale.y;
        const maxX = directionLimit_{component_key}("left");
        const maxY = directionLimit_{component_key}("top");
        const sourceWidth = Number(config_{component_key}.source_width || 1);
        const sourceHeight = Number(config_{component_key}.source_height || 1);
        const x = (event.clientX - rect.left) / scaleX;
        const y = (event.clientY - rect.top) / scaleY;
        if (edge.includes("left")) values_{component_key}.left = roundValue_{component_key}(maxX - x, "left");
        if (edge.includes("top")) values_{component_key}.top = roundValue_{component_key}(maxY - y, "top");
        if (edge.includes("right")) values_{component_key}.right = roundValue_{component_key}(x - maxX - sourceWidth, "right");
        if (edge.includes("bottom")) values_{component_key}.bottom = roundValue_{component_key}(y - maxY - sourceHeight, "bottom");
        applyBox_{component_key}();
      }};
      const commit_{component_key} = () => {{
        try {{
          const parentWindow = window.parent || window;
          const next = new URL(parentWindow.location.href);
          next.searchParams.set(config_{component_key}.query_key, JSON.stringify({{
            keys: config_{component_key}.keys || {{}},
            top: values_{component_key}.top,
            bottom: values_{component_key}.bottom,
            left: values_{component_key}.left,
            right: values_{component_key}.right,
            limits: config_{component_key}.limits || {{}},
          }}));
          parentWindow.location.href = next.toString();
        }} catch (error) {{}}
      }};
      root_{component_key}.querySelectorAll(".drag-edge, .drag-corner").forEach((handle) => {{
        let dragging = false;
        const edge = handle.dataset.edge;
        handle.addEventListener("pointerdown", (event) => {{
          dragging = true;
          handle.setPointerCapture && handle.setPointerCapture(event.pointerId);
          updateFromPointer_{component_key}(edge, event);
          event.preventDefault();
        }});
        handle.addEventListener("pointermove", (event) => {{
          if (!dragging) return;
          updateFromPointer_{component_key}(edge, event);
          event.preventDefault();
        }});
        const stop = () => {{
          if (!dragging) return;
          dragging = false;
          commit_{component_key}();
        }};
        handle.addEventListener("pointerup", stop);
        handle.addEventListener("pointercancel", stop);
        handle.addEventListener("lostpointercapture", stop);
      }});
      window.addEventListener("resize", applyBox_{component_key});
      applyBox_{component_key}();
    </script>
    """
    components.html(html_content, height=max(display_h + 92, 360), scrolling=False)


def render_outpaint_extension_preview(
    uploaded_files: list[Any],
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
) -> None:
    if not uploaded_files:
        return
    st.caption("虚线外框是扩展后的画布，虚线内框是原图边界。")
    render_outpaint_extension_preview_card(
        uploaded_files[0],
        top_px,
        bottom_px,
        left_px,
        right_px,
        "outpaint_inline_preview",
    )


def render_upload_delete_button(widget_key: str, item_index: int, button_key: str) -> None:
    st.markdown('<div class="delete-marker" style="display:none;"></div>', unsafe_allow_html=True)
    if st.button("×", key=button_key, help="删除当前图片", use_container_width=False, type="secondary"):
        remove_upload_cache_item(widget_key, item_index)
        reset_upload_widget(widget_key)
        st.rerun()


def render_uploaded_preview_card(
    uploaded_input: Any,
    widget_key: str,
    item_index: int,
    component_key: str,
    preview_renderer: Any | None = None,
) -> None:
    preview_container = st.container()
    with preview_container:
        st.markdown(
            f"""
            <div
                class="upload-preview-root"
                data-upload-widget="{html.escape(widget_key, quote=True)}"
                data-upload-index="{item_index}"
            ></div>
            """,
            unsafe_allow_html=True,
        )
        render_upload_delete_button(
            widget_key,
            item_index,
            button_key=f"delete_upload_{component_key}_{item_index}",
        )
        if preview_renderer is not None:
            preview_renderer(uploaded_input, item_index, component_key)
        else:
            render_zoomable_image_gallery(
                [uploaded_input_to_data_url(uploaded_input)],
                columns=1,
                thumb_height=150,
                component_key=component_key,
                fit_mode="contain",
                max_width_percent=100,
            )
        st.markdown('<div class="upload-replace-uploader-marker" style="display:none;"></div>', unsafe_allow_html=True)
        replacement_upload = st.file_uploader(
            "替换图片",
            type=["png", "jpg", "jpeg", "webp"],
            key=get_replace_uploader_widget_key(widget_key, item_index),
            label_visibility="collapsed",
        )
        if replacement_upload is not None:
            replace_upload_cache_item(widget_key, item_index, replacement_upload)
            reset_upload_widget(widget_key)
            st.rerun()


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


def render_uploaded_gallery(
    files: list[Any],
    empty_text: str,
    widget_key: str,
    slot_count: int = 5,
    preview_renderer: Any | None = None,
) -> None:
    if not files:
        st.markdown(f'<div class="slot-helper">{empty_text}</div>', unsafe_allow_html=True)
        return
    columns_per_row = min(max(slot_count, 1), 5)
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
                        preview_renderer=preview_renderer,
                    )
    if empty_text:
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
        original_full_src = normalized_image_source
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

      function deriveEagleFileName_{component_key}(src, index) {{
        const fallbackName = "{component_key}_" + String(index + 1) + ".png";
        const raw = String(src || "").trim();
        if (!raw) return fallbackName;
        if (raw.startsWith("data:")) return fallbackName;
        try {{
          const parsed = new URL(raw, hostWindow_{component_key}.location.href);
          const baseName = decodeURIComponent((parsed.pathname || "").split("/").pop() || "").trim();
          return baseName || fallbackName;
        }} catch (e) {{
          return fallbackName;
        }}
      }}

      function ensureEagleUi_{component_key}() {{
        if (!hostDoc_{component_key}.getElementById("lashforge-eagle-style")) {{
          const style = hostDoc_{component_key}.createElement("style");
          style.id = "lashforge-eagle-style";
          style.textContent = `
            #lashforge-eagle-menu {{
              position: fixed;
              min-width: 168px;
              padding: 6px;
              border-radius: 12px;
              background: rgba(9, 17, 35, 0.96);
              border: 1px solid rgba(126, 166, 255, 0.22);
              box-shadow: 0 18px 40px rgba(0, 0, 0, 0.34);
              z-index: 1000001;
              display: none;
            }}
            #lashforge-eagle-menu button {{
              width: 100%;
              border: 0;
              border-radius: 9px;
              background: transparent;
              color: #eef4ff;
              padding: 9px 10px;
              text-align: left;
              font-size: 13px;
              cursor: pointer;
            }}
            #lashforge-eagle-menu button:hover {{
              background: rgba(126, 166, 255, 0.16);
            }}
            #lashforge-eagle-toast {{
              position: fixed;
              right: 18px;
              bottom: 18px;
              z-index: 1000002;
              padding: 10px 14px;
              border-radius: 12px;
              background: rgba(9, 17, 35, 0.94);
              border: 1px solid rgba(126, 166, 255, 0.22);
              color: #eef4ff;
              font-size: 12px;
              box-shadow: 0 14px 34px rgba(0, 0, 0, 0.28);
              opacity: 0;
              pointer-events: none;
              transition: opacity .16s ease;
            }}
          `;
          hostDoc_{component_key}.head.appendChild(style);
        }}
        if (!hostDoc_{component_key}.getElementById("lashforge-eagle-menu")) {{
          const menu = hostDoc_{component_key}.createElement("div");
          menu.id = "lashforge-eagle-menu";
          menu.innerHTML = ''
            + '<button type="button" id="lashforge-download-image">下载图片</button>'
            + '<button type="button" id="lashforge-save-as-image">另存为...</button>'
            + '<button type="button" id="lashforge-save-to-eagle">保存到 Eagle</button>';
          hostDoc_{component_key}.body.appendChild(menu);
          hostWindow_{component_key}.__lashforgeEagleMenuState = {{}};
          const hideMenu = () => {{
            menu.style.display = "none";
          }};
          hostDoc_{component_key}.addEventListener("click", hideMenu, true);
          hostDoc_{component_key}.addEventListener("scroll", hideMenu, true);
          hostWindow_{component_key}.addEventListener("blur", hideMenu);
          hostDoc_{component_key}.addEventListener("keydown", (event) => {{
            if (event.key === "Escape") hideMenu();
          }}, true);
          menu.querySelector("#lashforge-download-image").addEventListener("click", () => {{
            const state = hostWindow_{component_key}.__lashforgeEagleMenuState || {{}};
            hideMenu();
            if (!state.src) {{
              return;
            }}
            try {{
              const link = hostDoc_{component_key}.createElement("a");
              link.href = state.src;
              link.download = state.name || "{component_key}.png";
              link.target = "_blank";
              link.rel = "noopener noreferrer";
              hostDoc_{component_key}.body.appendChild(link);
              link.click();
              link.remove();
            }} catch (error) {{
              showEagleToast_{component_key}("下载触发失败，请重试");
            }}
          }});
          menu.querySelector("#lashforge-save-as-image").addEventListener("click", async () => {{
            const state = hostWindow_{component_key}.__lashforgeEagleMenuState || {{}};
            hideMenu();
            if (!state.src) {{
              return;
            }}
            try {{
              const response = await hostWindow_{component_key}.fetch(state.src);
              if (!response.ok) {{
                throw new Error("fetch failed");
              }}
              const blob = await response.blob();
              const suggestedName = state.name || "{component_key}.png";
              const mimeType = blob.type || "image/png";
              if (typeof hostWindow_{component_key}.showSaveFilePicker === "function") {{
                const extension = suggestedName.includes(".") ? suggestedName.split(".").pop() : "png";
                const handle = await hostWindow_{component_key}.showSaveFilePicker({{
                  suggestedName,
                  types: [{{
                    description: "Image File",
                    accept: {{
                      [mimeType]: ["." + extension]
                    }}
                  }}]
                }});
                const writable = await handle.createWritable();
                await writable.write(blob);
                await writable.close();
                showEagleToast_{component_key}("已另存为图片");
                return;
              }}
              const blobUrl = hostWindow_{component_key}.URL.createObjectURL(blob);
              const link = hostDoc_{component_key}.createElement("a");
              link.href = blobUrl;
              link.download = suggestedName;
              hostDoc_{component_key}.body.appendChild(link);
              link.click();
              link.remove();
              hostWindow_{component_key}.setTimeout(() => {{
                hostWindow_{component_key}.URL.revokeObjectURL(blobUrl);
              }}, 1200);
              showEagleToast_{component_key}("当前环境不支持另存为弹窗，已改为下载");
            }} catch (error) {{
              showEagleToast_{component_key}("另存为失败，请重试");
            }}
          }});
          menu.querySelector("#lashforge-save-to-eagle").addEventListener("click", async () => {{
            const state = hostWindow_{component_key}.__lashforgeEagleMenuState || {{}};
            hideMenu();
            if (!state.src) {{
              return;
            }}
            const eagleTraceId = "eagle-" + Date.now() + "-" + Math.random().toString(16).slice(2, 8);
            const requestBody = {{
              url: state.src,
              name: state.name || "{component_key}.png",
              website: hostWindow_{component_key}.location.href,
              modificationTime: Date.now()
            }};
            try {{
              // #region debug-point B:eagle-save-start
              reportEagleDebug_{component_key}("B", "[DEBUG] Eagle save started", {{
                pageUrl: hostWindow_{component_key}.location.href,
                imageUrl: state.src,
                imageName: requestBody.name,
                hasAltKey: !!(hostWindow_{component_key}.event && hostWindow_{component_key}.event.altKey),
                userAgent: hostWindow_{component_key}.navigator.userAgent
              }}, eagleTraceId);
              // #endregion
              const response = await hostWindow_{component_key}.fetch("http://localhost:41595/api/item/addFromURL", {{
                method: "POST",
                headers: {{
                  "Content-Type": "application/json"
                }},
                body: JSON.stringify(requestBody)
              }});
              const result = await response.json().catch(() => ({{}}));
              // #region debug-point C:eagle-save-response
              reportEagleDebug_{component_key}("C", "[DEBUG] Eagle save response", {{
                ok: response.ok,
                statusCode: response.status,
                statusText: response.statusText,
                resultStatus: result && result.status ? result.status : "",
                resultMessage: result && result.message ? result.message : ""
              }}, eagleTraceId);
              // #endregion
              if (!response.ok || (result && result.status && result.status !== "success")) {{
                throw new Error((result && (result.message || result.status)) || "保存失败");
              }}
              showEagleToast_{component_key}("已保存到 Eagle");
            }} catch (error) {{
              // #region debug-point D:eagle-save-error
              reportEagleDebug_{component_key}("D", "[DEBUG] Eagle save failed", {{
                errorName: error && error.name ? error.name : "",
                errorMessage: error && error.message ? error.message : String(error || ""),
                imageUrl: state.src,
                pageUrl: hostWindow_{component_key}.location.href
              }}, eagleTraceId);
              // #endregion
              showEagleToast_{component_key}("保存到 Eagle 失败，请确认 Eagle 正在运行");
            }}
          }});
        }}
        if (!hostDoc_{component_key}.getElementById("lashforge-eagle-toast")) {{
          const toast = hostDoc_{component_key}.createElement("div");
          toast.id = "lashforge-eagle-toast";
          hostDoc_{component_key}.body.appendChild(toast);
        }}
      }}

      function showEagleToast_{component_key}(message) {{
        ensureEagleUi_{component_key}();
        const toast = hostDoc_{component_key}.getElementById("lashforge-eagle-toast");
        if (!toast) return;
        toast.textContent = String(message || "");
        toast.style.opacity = "1";
        hostWindow_{component_key}.clearTimeout(hostWindow_{component_key}.__lashforgeEagleToastTimer);
        hostWindow_{component_key}.__lashforgeEagleToastTimer = hostWindow_{component_key}.setTimeout(() => {{
          toast.style.opacity = "0";
        }}, 1800);
      }}

      function reportEagleDebug_{component_key}(hypothesisId, msg, data, traceId) {{
        // #region debug-point A:eagle-save-report
        hostWindow_{component_key}.fetch("http://127.0.0.1:7777/event", {{
          method: "POST",
          headers: {{
            "Content-Type": "application/json"
          }},
          body: JSON.stringify({{
            sessionId: "eagle-save-feishu",
            runId: "pre-fix",
            hypothesisId,
            location: "openrouter_image_site.py:eagle-menu",
            msg,
            data: data || {{}},
            traceId: traceId || "",
            ts: Date.now()
          }})
        }}).catch(() => {{}});
        // #endregion
      }}

      function openEagleMenu_{component_key}(event, src, index) {{
        ensureEagleUi_{component_key}();
        const menu = hostDoc_{component_key}.getElementById("lashforge-eagle-menu");
        if (!menu) return;
        const normalizedSrc = normalizeViewerSrc_{component_key}(src);
        hostWindow_{component_key}.__lashforgeEagleMenuState = {{
          src: normalizedSrc,
          name: deriveEagleFileName_{component_key}(normalizedSrc, index)
        }};
        const menuWidth = 168;
        const menuHeight = 126;
        const maxLeft = Math.max((hostWindow_{component_key}.innerWidth || 0) - menuWidth - 12, 12);
        const maxTop = Math.max((hostWindow_{component_key}.innerHeight || 0) - menuHeight - 12, 12);
        menu.style.left = Math.min(Math.max(event.clientX, 12), maxLeft) + "px";
        menu.style.top = Math.min(Math.max(event.clientY, 12), maxTop) + "px";
        menu.style.display = "block";
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
            #lashforge-fullscreen-close {{
              position: fixed;
              top: 18px;
              right: 18px;
              z-index: 1000000;
              width: 42px;
              height: 42px;
              border-radius: 999px;
              border: 1px solid rgba(255, 255, 255, 0.7);
              background: rgba(15, 23, 42, 0.86);
              color: #ffffff;
              font-size: 28px;
              line-height: 38px;
              text-align: center;
              cursor: pointer;
              box-shadow: 0 10px 28px rgba(0, 0, 0, 0.34);
            }}
            #lashforge-fullscreen-close:hover {{
              background: rgba(239, 68, 68, 0.92);
            }}
          `;
          hostDoc_{component_key}.head.appendChild(style);
        }}
        if (!hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer")) {{
          const overlay = hostDoc_{component_key}.createElement("div");
          overlay.id = "lashforge-fullscreen-viewer";
          overlay.innerHTML = '<button id="lashforge-fullscreen-close" type="button" aria-label="关闭预览" title="关闭">×</button><img id="lashforge-fullscreen-image" src="" alt="preview" />';
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
          const closeOverlay = () => {{
            overlay.classList.remove("active");
            resetTransform();
          }};
          const closeButton = overlay.querySelector("#lashforge-fullscreen-close");
          if (closeButton) {{
            closeButton.addEventListener("click", (event) => {{
              event.preventDefault();
              event.stopPropagation();
              closeOverlay();
            }});
          }}

          overlay.addEventListener("click", (event) => {{
            if (event.target === overlay) {{
              closeOverlay();
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
            if (event.button !== 0) return;
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
          image.addEventListener("contextmenu", (event) => {{
            if (!overlay.classList.contains("active")) return;
            if (!event.altKey) return;
            event.preventDefault();
            openEagleMenu_{component_key}(event, image.src, 0);
          }});

          hostDoc_{component_key}.addEventListener("keydown", (event) => {{
            if (event.key === "Escape") {{
              closeOverlay();
            }}
          }});
        }}
        const activeOverlay = hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer");
        const activeImage = hostDoc_{component_key}.getElementById("lashforge-fullscreen-image");
        if (activeOverlay && activeImage) {{
          if (!hostWindow_{component_key}.__lashforgeFullscreenState) {{
            hostWindow_{component_key}.__lashforgeFullscreenState = {{
              scale: 1,
              offsetX: 0,
              offsetY: 0,
              dragging: false,
              dragStartX: 0,
              dragStartY: 0,
              dragOriginX: 0,
              dragOriginY: 0,
            }};
          }}
          const resetActiveFullscreen = () => {{
            const state = hostWindow_{component_key}.__lashforgeFullscreenState || {{}};
            state.scale = 1;
            state.offsetX = 0;
            state.offsetY = 0;
            state.dragging = false;
            activeImage.classList.remove("dragging");
            activeImage.style.transform = "translate(0px, 0px) scale(1)";
          }};
          const closeActiveFullscreen = () => {{
            activeOverlay.classList.remove("active");
            resetActiveFullscreen();
          }};
          hostWindow_{component_key}.__lashforgeCloseFullscreen = closeActiveFullscreen;
          const activeCloseButton = activeOverlay.querySelector("#lashforge-fullscreen-close");
          if (activeCloseButton) {{
            activeCloseButton.onclick = (event) => {{
              event.preventDefault();
              event.stopPropagation();
              closeActiveFullscreen();
            }};
          }}
          activeOverlay.onclick = (event) => {{
            if (event.target === activeOverlay) {{
              closeActiveFullscreen();
            }}
          }};
          if (hostWindow_{component_key}.__lashforgeFullscreenKeyHandler) {{
            try {{
              hostDoc_{component_key}.removeEventListener("keydown", hostWindow_{component_key}.__lashforgeFullscreenKeyHandler, true);
            }} catch (e) {{}}
          }}
          hostWindow_{component_key}.__lashforgeFullscreenKeyHandler = (event) => {{
            if (event.key === "Escape") {{
              closeActiveFullscreen();
            }}
          }};
          hostDoc_{component_key}.addEventListener("keydown", hostWindow_{component_key}.__lashforgeFullscreenKeyHandler, true);
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
        img.oncontextmenu = (event) => {{
          if (!event.altKey) return;
          event.preventDefault();
          openEagleMenu_{component_key}(event, item.full_src || item.src, index);
        }};
        wrap.appendChild(img);

        if ({delete_token}) {{
          const deleteButton = document.createElement("button");
          deleteButton.type = "button";
          deleteButton.className = "zoom-thumb-delete";
          deleteButton.title = "删除当前图片";
          deleteButton.textContent = "×";
          deleteButton.addEventListener("pointerdown", (event) => {{
            event.stopPropagation();
          }});
          deleteButton.addEventListener("click", (event) => {{
            event.preventDefault();
            event.stopPropagation();
            const deleteUrl = buildDeleteUrl_{component_key}();
            if (deleteUrl) {{
              hostWindow_{component_key}.location.href = deleteUrl;
            }}
          }});
          wrap.appendChild(deleteButton);
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

    action_left, action_right = st.columns([1, 1], gap="small")
    with action_left:
        uploaded = st.file_uploader(
            "重新上传" if active_uploaded is not None else "上传图片",
            type=["png", "jpg", "jpeg", "webp"],
            key=get_uploader_widget_key(key),
            help=help_text or None,
            label_visibility="collapsed",
        )
        if uploaded is not None:
            replacement_index = consume_pending_upload_replacement(key)
            if replacement_index is not None and active_uploaded is not None:
                replace_upload_cache_item(key, replacement_index, uploaded)
            else:
                save_upload_cache(key, [uploaded])
            reset_upload_widget(key)
            st.rerun()

    with action_right:
        if st.button("清空上传", key=f"clear_upload_{key}", use_container_width=True, type="secondary"):
            clear_upload_cache(key)
            reset_upload_widget(key)
            st.rerun()

    st.caption("支持 Ctrl+V 直接粘贴图片到当前上传区域")
    return active_uploaded


def render_compact_element_image_uploader(
    label: str,
    key: str,
    help_text: str = "",
) -> Any | None:
    cached_files = load_upload_cache(key, max_files=1)
    active_uploaded = cached_files[0] if cached_files else None

    if active_uploaded is not None:
        render_zoomable_image_gallery(
            [uploaded_input_to_data_url(active_uploaded)],
            columns=1,
            thumb_height=112,
            component_key=f"compact_element_preview_{key}",
            fit_mode="contain",
            max_width_percent=100,
        )
        st.caption(f"已选：{get_uploaded_file_name(active_uploaded)}")

    uploaded = st.file_uploader(
        "更换素材" if active_uploaded is not None else label,
        type=["png", "jpg", "jpeg", "webp"],
        key=get_uploader_widget_key(key),
        help=help_text or None,
        label_visibility="collapsed",
    )
    if uploaded is not None:
        save_upload_cache(key, [uploaded])
        reset_upload_widget(key)
        st.rerun()

    if active_uploaded is not None and st.button(
        "移除当前素材",
        key=f"clear_compact_element_upload_{key}",
        use_container_width=True,
        type="secondary",
    ):
        clear_upload_cache(key)
        reset_upload_widget(key)
        st.rerun()

    return active_uploaded


def render_multi_image_uploader(
    label: str,
    key: str,
    help_text: str = "",
    max_files: int = 3,
    preview_renderer: Any | None = None,
    preview_slot_count: int | None = None,
) -> list[Any]:
    cached_files = load_upload_cache(key, max_files=max_files)
    active_uploaded_files = cached_files

    if active_uploaded_files:
        st.markdown(
            '<div class="upload-summary-row">'
            '<strong>已上传图片</strong>'
            f'<span>{len(active_uploaded_files)} / {max_files} 张</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        render_uploaded_gallery(
            active_uploaded_files,
            "",
            widget_key=key,
            slot_count=preview_slot_count or max_files,
            preview_renderer=preview_renderer,
        )
    else:
        st.markdown(
            '<div class="upload-main-empty">'
            '<div class="empty-icon">＋</div>'
            '<div class="empty-title">添加需要处理的图片</div>'
            f'<div class="empty-subtitle">支持批量上传，最多 {max_files} 张</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    action_left, action_right = st.columns([1.4, 0.6], gap="small")
    with action_left:
        st.markdown(
            '<div class="upload-more-marker"></div>'
            if active_uploaded_files
            else '<div class="upload-add-marker"></div>',
            unsafe_allow_html=True,
        )
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
            replacement_index = consume_pending_upload_replacement(key)
            if replacement_index is not None and uploaded_files:
                combined = list(current_cache)
                if replacement_index < len(combined):
                    combined[replacement_index] = list(uploaded_files)[0]
                else:
                    combined.append(list(uploaded_files)[0])
            else:
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

    st.caption("支持 Ctrl+V 直接粘贴图片到当前上传区域")
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
                consume_pending_upload_replacement(slot_key)
                save_upload_cache(slot_key, [uploaded])
                reset_upload_widget(slot_key)
                st.rerun()
                
    return uploaded_files


def build_result_download_sources(
    images: list[str],
    history_records: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Use the same persisted original-image URLs as the history gallery."""
    history_items = flatten_history_items(list(history_records or []))
    download_sources: list[str] = []
    for index, image_source in enumerate(images):
        history_source = ""
        if index < len(history_items):
            history_item = history_items[index]
            history_source = str(
                history_item.get("download_source")
                or history_item.get("original_image")
                or ""
            ).strip()
        preferred_source = history_source or str(image_source or "").strip()
        try:
            public_source = build_history_download_public_url(preferred_source)
        except Exception:
            public_source = preferred_source
        download_sources.append(public_source or str(image_source or "").strip())
    return download_sources


def render_result_preview(
    images: list[str],
    show_title: bool = True,
    download_images: list[str] | None = None,
) -> None:
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
        normalized_download_images = list(download_images or build_result_download_sources(images))
        render_zoomable_image_gallery(
            images,
            columns=1,
            thumb_height=None,
            component_key="result_viewer",
            fit_mode="contain",
            max_width_percent=25,
            compress_preview=True,
            include_full_src=True,
            full_images=normalized_download_images,
            embed_full_src=False,
        )


def render_result_preview_with_captions(
    images: list[str],
    captions: list[str],
    feature_key: str,
    download_images: list[str] | None = None,
) -> None:
    if not images:
        render_result_preview(images, show_title=False, download_images=download_images)
        return
    if len(captions) != len(images):
        render_result_preview(images, show_title=False, download_images=download_images)
        return
    normalized_download_images = list(download_images or build_result_download_sources(images))
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
                    full_images=(
                        [normalized_download_images[row_start + column_index]]
                        if row_start + column_index < len(normalized_download_images)
                        else []
                    ),
                    embed_full_src=False,
                )


def render_before_after_compare_gallery(
    source_images: list[str],
    result_images: list[str],
    captions: list[str],
    feature_key: str,
    outpaint_alignments: list[dict[str, Any]] | None = None,
    download_images: list[str] | None = None,
) -> None:
    normalized_download_images = list(download_images or build_result_download_sources(result_images))
    pairs: list[dict[str, Any]] = []
    for index, result_image in enumerate(result_images):
        source_image = source_images[index] if index < len(source_images) else ""
        if not source_image or not result_image:
            continue
        source_item = build_gallery_item(source_image, compress_preview=True, include_full_src=True)
        result_item = build_gallery_item(str(result_image), compress_preview=True, include_full_src=True)
        if not source_item or not result_item:
            continue
        result_full_source = (
            normalized_download_images[index]
            if index < len(normalized_download_images)
            else str(result_item.get("full_src") or result_image)
        )
        view_source = build_history_download_public_url(result_full_source)
        download_source = build_direct_image_download_url(view_source)
        download_path = Path(urllib.parse.unquote(urllib.parse.urlsplit(view_source).path or ""))
        download_extension = download_path.suffix if download_path.suffix.lower() in REFERENCE_IMAGE_EXTENSIONS else ".png"
        download_name = download_path.name or f"扩图效果图_{index + 1}{download_extension}"
        pairs.append(
            {
                "source": source_item["src"],
                "result": result_item["src"],
                "view": view_source,
                "download": download_source,
                "download_name": download_name,
                "caption": str(captions[index] if index < len(captions) else f"结果 {index + 1}").strip(),
                "alignment": (
                    dict(outpaint_alignments[index] or {})
                    if outpaint_alignments and index < len(outpaint_alignments)
                    else {}
                ),
            }
        )
    if not pairs:
        render_result_preview_with_captions(
            result_images,
            captions,
            feature_key,
            download_images=normalized_download_images,
        )
        return
    component_key = re.sub(r"[^a-zA-Z0-9_]", "_", f"compare_{feature_key}_{len(pairs)}")
    payload = json.dumps(pairs, ensure_ascii=False)
    row_height = 672
    html_content = f"""
    <div id="{component_key}" class="compare-gallery-root"></div>
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        background: transparent;
        color: #f5f7ff;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      .compare-gallery-root {{
        display: grid;
        gap: 16px;
        width: 100%;
        box-sizing: border-box;
      }}
      .compare-title {{
        color: rgba(214, 219, 255, 0.76);
        font-size: 12px;
        font-weight: 700;
        margin: 0 0 7px;
      }}
      .compare-pair {{
        display: block;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        overflow: hidden;
        background: rgba(7, 15, 31, 0.52);
        width: 100%;
        box-sizing: border-box;
      }}
      .compare-pane {{
        position: relative;
        height: 620px;
        background: rgba(4, 10, 24, 0.72);
        overflow: hidden;
        touch-action: none;
        box-sizing: border-box;
      }}
      .compare-stage {{
        cursor: ew-resize;
      }}
      .compare-canvas {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        display: block;
        z-index: 1;
      }}
      .compare-line {{
        position: absolute;
        top: 0;
        height: 100%;
        left: 50%;
        width: 2px;
        transform: translateX(-1px);
        background: #ffffff;
        box-shadow: 0 0 0 1px rgba(126, 96, 255, 0.78), 0 0 18px rgba(126, 96, 255, 0.72);
        pointer-events: none;
        z-index: 4;
      }}
      .compare-knob {{
        position: absolute;
        left: 50%;
        top: 50%;
        width: 30px;
        height: 30px;
        transform: translate(-50%, -50%);
        border-radius: 999px;
        background: rgba(126, 96, 255, 0.95);
        border: 2px solid rgba(255,255,255,0.9);
        pointer-events: none;
        z-index: 4;
      }}
      .compare-knob::before {{
        content: "↔";
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #ffffff;
        font-size: 16px;
        font-weight: 800;
      }}
      .compare-slider {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        opacity: 0;
        cursor: ew-resize;
        pointer-events: none;
        z-index: 6;
      }}
      .compare-native-result {{
        position: absolute;
        display: block;
        margin: 0;
        opacity: 1;
        object-fit: fill;
        cursor: zoom-in;
        user-select: none;
        -webkit-user-drag: none;
        z-index: 3;
      }}
      .compare-label {{
        position: absolute;
        top: 8px;
        padding: 4px 8px;
        border-radius: 999px;
        background: rgba(3, 8, 22, 0.7);
        color: rgba(245, 247, 255, 0.92);
        font-size: 11px;
        font-weight: 700;
        pointer-events: none;
        z-index: 5;
      }}
      .compare-label.left {{ left: 8px; }}
      .compare-label.right {{ right: 8px; }}
      .compare-download-hint {{
        position: absolute;
        right: 10px;
        bottom: 10px;
        padding: 5px 9px;
        border-radius: 999px;
        background: rgba(3, 8, 22, 0.72);
        color: rgba(245, 247, 255, 0.82);
        font-size: 11px;
        font-weight: 650;
        pointer-events: none;
        z-index: 5;
      }}
      @media (max-width: 720px) {{
        .compare-pane {{ height: 520px; }}
      }}
    </style>
    <script>
      const pairs_{component_key} = {payload};
      const root_{component_key} = document.getElementById("{component_key}");
      const hostWindow_{component_key} = (() => {{
        try {{
          return window.parent;
        }} catch (error) {{
          return window;
        }}
      }})();
      const hostDoc_{component_key} = (() => {{
        try {{
          return window.parent.document;
        }} catch (error) {{
          return document;
        }}
      }})();
      const normalizeNativeResultSrc_{component_key} = (src) => {{
        const raw = String(src || "").trim();
        if (!raw || raw.startsWith("data:")) return raw;
        try {{
          const parsed = new URL(raw, hostWindow_{component_key}.location.href);
          const isStaticImageRoute =
            parsed.pathname.startsWith("{HISTORY_STATIC_ROUTE_PREFIX}/") ||
            parsed.pathname.startsWith("{JIMENG_UPLOAD_ROUTE_PREFIX}/");
          if (!isStaticImageRoute) return parsed.toString();
          const currentProtocol = hostWindow_{component_key}.location.protocol || parsed.protocol;
          const currentHostname = hostWindow_{component_key}.location.hostname || parsed.hostname;
          const currentPort = parsed.port ? ":" + parsed.port : "";
          return `${{currentProtocol}}//${{currentHostname}}${{currentPort}}${{parsed.pathname}}${{parsed.search}}${{parsed.hash}}`;
        }} catch (error) {{
          return raw;
        }}
      }};
      const ensureCompareFullscreen_{component_key} = () => {{
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
            #lashforge-fullscreen-viewer.active {{ display: flex; }}
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
            #lashforge-fullscreen-viewer img.dragging {{ cursor: grabbing; }}
            #lashforge-fullscreen-close {{
              position: fixed;
              top: 18px;
              right: 18px;
              z-index: 1000000;
              width: 42px;
              height: 42px;
              border-radius: 999px;
              border: 1px solid rgba(255, 255, 255, 0.7);
              background: rgba(15, 23, 42, 0.86);
              color: #ffffff;
              font-size: 28px;
              line-height: 38px;
              text-align: center;
              cursor: pointer;
              box-shadow: 0 10px 28px rgba(0, 0, 0, 0.34);
            }}
            #lashforge-fullscreen-close:hover {{ background: rgba(239, 68, 68, 0.92); }}
          `;
          hostDoc_{component_key}.head.appendChild(style);
        }}
        let overlay = hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer");
        if (overlay) return overlay;
        overlay = hostDoc_{component_key}.createElement("div");
        overlay.id = "lashforge-fullscreen-viewer";
        overlay.innerHTML = '<button id="lashforge-fullscreen-close" type="button" aria-label="关闭预览" title="关闭">×</button><img id="lashforge-fullscreen-image" src="" alt="preview" />';
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
        const closeOverlay = () => {{
          overlay.classList.remove("active");
          resetTransform();
        }};
        hostWindow_{component_key}.__lashforgeCloseFullscreen = closeOverlay;
        overlay.querySelector("#lashforge-fullscreen-close").addEventListener("click", (event) => {{
          event.preventDefault();
          event.stopPropagation();
          closeOverlay();
        }});
        overlay.addEventListener("click", (event) => {{
          if (event.target === overlay) closeOverlay();
        }});
        overlay.addEventListener("wheel", (event) => {{
          if (!overlay.classList.contains("active")) return;
          event.preventDefault();
          state.scale = event.deltaY < 0
            ? Math.min(state.scale + 0.16, 6)
            : Math.max(state.scale - 0.16, 0.35);
          applyTransform();
        }}, {{ passive: false }});
        image.addEventListener("pointerdown", (event) => {{
          if (!overlay.classList.contains("active") || event.button !== 0) return;
          event.preventDefault();
          state.dragging = true;
          state.dragStartX = event.clientX;
          state.dragStartY = event.clientY;
          state.dragOriginX = state.offsetX;
          state.dragOriginY = state.offsetY;
          image.classList.add("dragging");
          image.setPointerCapture && image.setPointerCapture(event.pointerId);
        }});
        image.addEventListener("pointermove", (event) => {{
          if (!state.dragging) return;
          event.preventDefault();
          state.offsetX = state.dragOriginX + (event.clientX - state.dragStartX);
          state.offsetY = state.dragOriginY + (event.clientY - state.dragStartY);
          applyTransform();
        }});
        const stopImageDrag = () => {{
          state.dragging = false;
          image.classList.remove("dragging");
        }};
        image.addEventListener("pointerup", stopImageDrag);
        image.addEventListener("pointercancel", stopImageDrag);
        image.addEventListener("lostpointercapture", stopImageDrag);
        if (hostWindow_{component_key}.__lashforgeFullscreenKeyHandler) {{
          try {{
            hostDoc_{component_key}.removeEventListener(
              "keydown",
              hostWindow_{component_key}.__lashforgeFullscreenKeyHandler,
              true
            );
          }} catch (error) {{}}
        }}
        hostWindow_{component_key}.__lashforgeFullscreenKeyHandler = (event) => {{
          if (event.key === "Escape") closeOverlay();
        }};
        hostDoc_{component_key}.addEventListener(
          "keydown",
          hostWindow_{component_key}.__lashforgeFullscreenKeyHandler,
          true
        );
        return overlay;
      }};
      const openCompareFullscreen_{component_key} = (src) => {{
        const overlay = ensureCompareFullscreen_{component_key}();
        const image = hostDoc_{component_key}.getElementById("lashforge-fullscreen-image");
        const state = hostWindow_{component_key}.__lashforgeFullscreenState || {{}};
        state.scale = 1;
        state.offsetX = 0;
        state.offsetY = 0;
        state.dragging = false;
        hostWindow_{component_key}.__lashforgeFullscreenState = state;
        image.src = normalizeNativeResultSrc_{component_key}(src);
        image.classList.remove("dragging");
        image.style.transform = "translate(0px, 0px) scale(1)";
        overlay.classList.add("active");
      }};
      pairs_{component_key}.forEach((pair, index) => {{
        const wrap = document.createElement("div");
        const title = document.createElement("div");
        title.className = "compare-title";
        title.textContent = pair.caption || `结果 ${{index + 1}}`;
        const grid = document.createElement("div");
        grid.className = "compare-pair";
        grid.innerHTML = `
          <div class="compare-pane compare-control compare-stage">
            <canvas class="compare-canvas"></canvas>
            <span class="compare-label left">原图</span>
            <span class="compare-label right">效果图</span>
            <span class="compare-download-hint">左键查看大图 · 右键使用 Chrome 原生菜单</span>
            <div class="compare-line"></div>
            <div class="compare-knob"></div>
            <input class="compare-slider" type="range" min="0" max="100" value="50" aria-label="对比滑块">
            <img class="compare-native-result" alt="效果图原图" draggable="false">
          </div>`;
        wrap.appendChild(title);
        wrap.appendChild(grid);
        root_{component_key}.appendChild(wrap);
        const control = grid.querySelector(".compare-control");
        const canvas = control.querySelector(".compare-canvas");
        const ctx = canvas.getContext("2d");
        const slider = control.querySelector(".compare-slider");
        const line = control.querySelector(".compare-line");
        const knob = control.querySelector(".compare-knob");
        const nativeResultImage = control.querySelector(".compare-native-result");
        const sourceImage = new Image();
        const resultImage = new Image();
        let currentValue = 50;
        let drawBox = {{ x: 0, y: 0, width: 1, height: 1 }};
        const getContainBox = (image, stageWidth, stageHeight) => {{
          const naturalWidth = Math.max(image.naturalWidth || 1, 1);
          const naturalHeight = Math.max(image.naturalHeight || 1, 1);
          const imageRatio = naturalWidth / naturalHeight;
          let width = stageWidth;
          let height = width / imageRatio;
          if (height > stageHeight) {{
            height = stageHeight;
            width = height * imageRatio;
          }}
          return {{
            x: (stageWidth - width) / 2,
            y: (stageHeight - height) / 2,
            width,
            height,
          }};
        }};
        const drawImageContain = (image, box) => {{
          ctx.drawImage(image, box.x, box.y, box.width, box.height);
        }};
        const renderCanvas = () => {{
          const stageWidth = Math.max(control.clientWidth, 1);
          const stageHeight = Math.max(control.clientHeight, 1);
          const dpr = Math.max(window.devicePixelRatio || 1, 1);
          const pixelWidth = Math.round(stageWidth * dpr);
          const pixelHeight = Math.round(stageHeight * dpr);
          if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {{
            canvas.width = pixelWidth;
            canvas.height = pixelHeight;
          }}
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          ctx.clearRect(0, 0, stageWidth, stageHeight);
          const sourceReady = sourceImage.complete && sourceImage.naturalWidth > 0;
          const resultReady = resultImage.complete && resultImage.naturalWidth > 0;
          if (!sourceReady || !resultReady) {{
            return;
          }}
          drawBox = getContainBox(resultImage, stageWidth, stageHeight);
          drawImageContain(resultImage, drawBox);
          const revealWidth = drawBox.width * currentValue / 100;
          const alignment = pair.alignment || {{}};
          const targetWidth = Number(alignment.target_width || 0);
          const targetHeight = Number(alignment.target_height || 0);
          const sourceWidth = Number(alignment.source_width || 0);
          const sourceHeight = Number(alignment.source_height || 0);
          const hasAlignment = targetWidth > 0 && targetHeight > 0 && sourceWidth > 0 && sourceHeight > 0;
          ctx.save();
          ctx.beginPath();
          ctx.rect(drawBox.x, drawBox.y, revealWidth, drawBox.height);
          ctx.clip();
          if (hasAlignment) {{
            ctx.fillStyle = "rgba(4, 10, 24, 0.98)";
            ctx.fillRect(drawBox.x, drawBox.y, drawBox.width, drawBox.height);
            const sourceBox = {{
              x: drawBox.x + (Number(alignment.left || 0) / targetWidth) * drawBox.width,
              y: drawBox.y + (Number(alignment.top || 0) / targetHeight) * drawBox.height,
              width: (sourceWidth / targetWidth) * drawBox.width,
              height: (sourceHeight / targetHeight) * drawBox.height,
            }};
            drawImageContain(sourceImage, sourceBox);
          }} else {{
            drawImageContain(sourceImage, drawBox);
          }}
          ctx.restore();
          const lineLeft = drawBox.x + drawBox.width * currentValue / 100;
          line.style.left = `${{lineLeft}}px`;
          line.style.top = `${{drawBox.y}}px`;
          line.style.height = `${{drawBox.height}}px`;
          knob.style.left = `${{lineLeft}}px`;
          knob.style.top = `${{drawBox.y + drawBox.height / 2}}px`;
          nativeResultImage.style.left = `${{drawBox.x}}px`;
          nativeResultImage.style.top = `${{drawBox.y}}px`;
          nativeResultImage.style.width = `${{drawBox.width}}px`;
          nativeResultImage.style.height = `${{drawBox.height}}px`;
          nativeResultImage.style.clipPath = `inset(0 0 0 ${{currentValue}}%)`;
        }};
        const update = (nextValue) => {{
          const value = Math.max(0, Math.min(100, Number(nextValue ?? slider.value ?? 50)));
          currentValue = value;
          slider.value = String(value);
          renderCanvas();
        }};
        const updateFromPointer = (event) => {{
          const rect = control.getBoundingClientRect();
          const clientX = event.touches && event.touches.length ? event.touches[0].clientX : event.clientX;
          const localX = clientX - rect.left;
          const boxStart = drawBox.x;
          const boxWidth = Math.max(drawBox.width, 1);
          update(((localX - boxStart) / boxWidth) * 100);
        }};
        let dragging = false;
        let dragMoved = false;
        let dragStartX = 0;
        let dragStartY = 0;
        let pointerDownOnEffect = false;
        control.addEventListener("pointerdown", (event) => {{
          if (event.button !== 0) return;
          dragging = true;
          dragMoved = false;
          dragStartX = event.clientX;
          dragStartY = event.clientY;
          pointerDownOnEffect = event.target === nativeResultImage;
          control.setPointerCapture && control.setPointerCapture(event.pointerId);
          if (!pointerDownOnEffect) updateFromPointer(event);
        }});
        control.addEventListener("pointermove", (event) => {{
          if (!dragging) return;
          if (Math.hypot(event.clientX - dragStartX, event.clientY - dragStartY) > 5) {{
            dragMoved = true;
          }}
          if (!dragMoved && pointerDownOnEffect) return;
          updateFromPointer(event);
        }});
        const stopDrag = () => {{ dragging = false; }};
        control.addEventListener("pointerup", stopDrag);
        control.addEventListener("pointercancel", () => {{
          dragging = false;
          pointerDownOnEffect = false;
          dragMoved = false;
        }});
        control.addEventListener("lostpointercapture", stopDrag);
        control.addEventListener("click", (event) => {{
          const shouldOpen = pointerDownOnEffect && !dragMoved;
          pointerDownOnEffect = false;
          dragMoved = false;
          if (!shouldOpen) return;
          event.preventDefault();
          event.stopPropagation();
          openCompareFullscreen_{component_key}(pair.view || pair.result);
        }});
        slider.addEventListener("input", () => update(slider.value));
        window.addEventListener("resize", () => update(slider.value));
        sourceImage.addEventListener("load", () => update(currentValue));
        resultImage.addEventListener("load", () => update(currentValue));
        nativeResultImage.addEventListener("dragstart", (event) => event.preventDefault());
        sourceImage.src = pair.source;
        resultImage.src = pair.result;
        nativeResultImage.src = normalizeNativeResultSrc_{component_key}(pair.view || pair.result);
        update(50);
      }});
    </script>
    """
    components.html(html_content, height=max(len(pairs), 1) * row_height, scrolling=False)


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
    is_expanded = bool(st.session_state.history_panel_expanded.get(cache_key, False))
    button_label = "加载历史记录" if not is_expanded else "收起历史记录"
    button_icon = ":material/history:" if not is_expanded else ":material/expand_less:"
    if st.button(
        button_label,
        key=f"lazy_history_{feature['key']}",
        use_container_width=True,
        type="secondary",
        icon=button_icon,
    ):
        next_state = not is_expanded
        st.session_state.history_panel_expanded[cache_key] = next_state
        if next_state:
            set_history_visible_limit(cache_key, HISTORY_PAGE_SIZE)
        st.rerun()
    if not is_expanded:
        return

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


def parse_hex_rgb(hex_color: str) -> tuple[int, int, int]:
    normalized = str(hex_color or "").strip().lstrip("#")
    if len(normalized) == 3:
        normalized = "".join(part * 2 for part in normalized)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", normalized):
        return (255, 255, 255)
    return (
        int(normalized[0:2], 16),
        int(normalized[2:4], 16),
        int(normalized[4:6], 16),
    )


def estimate_cutout_background_color(image: Image.Image, sample_mode: str) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    if width <= 0 or height <= 0:
        return (255, 255, 255)
    sample_mode = str(sample_mode or "").strip()
    if sample_mode == "自动边缘取样":
        band = max(2, min(width, height, 80) // 10)
        band = min(band, width, height)
        boxes = [
            (0, 0, width, band),
            (0, height - band, width, height),
            (0, 0, band, height),
            (width - band, 0, width, height),
        ]
    else:
        corner = max(2, min(width, height, 96) // 4)
        corner = min(corner, width, height)
        boxes = [
            (0, 0, corner, corner),
            (width - corner, 0, width, corner),
            (0, height - corner, corner, height),
            (width - corner, height - corner, width, height),
        ]

    totals = [0.0, 0.0, 0.0]
    total_weight = 0
    for box in boxes:
        left, top, right, bottom = box
        crop_width = max(right - left, 1)
        crop_height = max(bottom - top, 1)
        weight = crop_width * crop_height
        stat = ImageStat.Stat(rgb.crop(box))
        for channel_index, mean_value in enumerate(stat.mean[:3]):
            totals[channel_index] += float(mean_value) * weight
        total_weight += weight
    if total_weight <= 0:
        return (255, 255, 255)
    return tuple(max(0, min(255, int(round(value / total_weight)))) for value in totals)


def extract_edge_connected_mask(candidate_mask: Image.Image) -> Image.Image:
    try:
        import numpy as np
        from scipy import ndimage

        mask = np.asarray(candidate_mask.convert("L")) >= 128
        if mask.size == 0:
            return candidate_mask.convert("L")
        seeds = np.zeros_like(mask, dtype=bool)
        seeds[0, :] = mask[0, :]
        seeds[-1, :] = mask[-1, :]
        seeds[:, 0] = mask[:, 0]
        seeds[:, -1] = mask[:, -1]
        connected = ndimage.binary_propagation(seeds, mask=mask)
        connected_image = (connected.astype(np.uint8) * 255)
        return Image.fromarray(connected_image, mode="L")
    except Exception:
        pass

    working = candidate_mask.convert("L").point(lambda value: 255 if value >= 128 else 0)
    width, height = working.size
    if width <= 0 or height <= 0:
        return working
    pixels = working.load()
    for x in range(width):
        if pixels[x, 0] == 255:
            ImageDraw.floodfill(working, (x, 0), 128, thresh=0)
        if pixels[x, height - 1] == 255:
            ImageDraw.floodfill(working, (x, height - 1), 128, thresh=0)
    for y in range(height):
        if pixels[0, y] == 255:
            ImageDraw.floodfill(working, (0, y), 128, thresh=0)
        if pixels[width - 1, y] == 255:
            ImageDraw.floodfill(working, (width - 1, y), 128, thresh=0)
    return working.point(lambda value: 255 if value == 128 else 0)


def build_subject_protection_mask(distance: Image.Image, threshold: int) -> Image.Image:
    try:
        import numpy as np

        arr = np.asarray(distance.convert("L")) > max(0, min(255, int(threshold)))
        if arr.size == 0:
            return Image.new("L", distance.size, 0)
        height, width = arr.shape
        row_threshold = max(12, int(round(width * 0.008)))
        col_threshold = max(12, int(round(height * 0.008)))
        rows = np.where(arr.sum(axis=1) >= row_threshold)[0]
        cols = np.where(arr.sum(axis=0) >= col_threshold)[0]
        if rows.size == 0 or cols.size == 0:
            return Image.new("L", distance.size, 0)

        left = int(cols[0])
        right = int(cols[-1])
        top = int(rows[0])
        bottom = int(rows[-1])
        pad_x = max(8, int(round(width * 0.018)))
        pad_y = max(8, int(round(height * 0.018)))
        left = max(0, left - pad_x)
        right = min(width - 1, right + pad_x)
        top = max(0, top - pad_y)
        bottom = min(height - 1, bottom + pad_y)

        area_ratio = ((right - left + 1) * (bottom - top + 1)) / float(max(width * height, 1))
        if area_ratio <= 0 or area_ratio >= 0.92:
            return Image.new("L", distance.size, 0)

        mask = Image.new("L", distance.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((left, top, right, bottom), fill=255)
        return mask
    except Exception:
        return Image.new("L", distance.size, 0)


def build_lash_rectangle_protection_mask(image: Image.Image) -> Image.Image:
    try:
        import numpy as np

        rgb = np.asarray(image.convert("RGB"))
        if rgb.size == 0:
            return Image.new("L", image.size, 0)
        height, width = rgb.shape[:2]
        luminance = (
            0.299 * rgb[:, :, 0].astype("float32")
            + 0.587 * rgb[:, :, 1].astype("float32")
            + 0.114 * rgb[:, :, 2].astype("float32")
        )
        dark_mask = luminance < 95
        if not bool(dark_mask.any()):
            return Image.new("L", image.size, 0)

        min_col_count = max(10, int(round(height * 0.006)))
        min_row_count = max(10, int(round(width * 0.006)))
        cols = np.where(dark_mask.sum(axis=0) >= min_col_count)[0]
        rows = np.where(dark_mask.sum(axis=1) >= min_row_count)[0]
        if cols.size == 0 or rows.size == 0:
            return Image.new("L", image.size, 0)

        lash_left = int(cols[0])
        lash_right = int(cols[-1])
        lash_top = int(rows[0])
        lash_bottom = int(rows[-1])

        dense_mask = dark_mask.copy()
        dense_mask[:, :lash_left] = False
        dense_mask[:, lash_right + 1 :] = False
        dense_mask[:lash_top, :] = False
        dense_mask[lash_bottom + 1 :, :] = False
        ys, xs = np.where(dense_mask)
        if xs.size < 200:
            return Image.new("L", image.size, 0)

        points = np.column_stack((xs.astype("float32"), ys.astype("float32")))
        center = points.mean(axis=0)
        centered = points - center
        covariance = np.cov(centered, rowvar=False)
        values, vectors = np.linalg.eigh(covariance)
        ordered = vectors[:, np.argsort(values)[::-1]]
        axis_a = ordered[:, 0]
        axis_b = ordered[:, 1]
        if abs(axis_a[0]) >= abs(axis_b[0]):
            x_axis = axis_a
            y_axis = axis_b
        else:
            x_axis = axis_b
            y_axis = axis_a
        if x_axis[0] < 0:
            x_axis = -x_axis
        if y_axis[1] < 0:
            y_axis = -y_axis

        projected_x = points @ x_axis
        projected_y = points @ y_axis
        left = float(projected_x.min())
        right = float(projected_x.max())
        top = float(projected_y.min())
        bottom = float(projected_y.max())
        lash_width = max(right - left, 1.0)
        lash_height = max(bottom - top, 1.0)

        left -= lash_width * 0.12
        right += lash_width * 0.04
        top -= lash_height * 0.30
        bottom += lash_height * 0.16

        corners = [
            x_axis * left + y_axis * top,
            x_axis * right + y_axis * top,
            x_axis * right + y_axis * bottom,
            x_axis * left + y_axis * bottom,
        ]
        polygon = [(float(point[0]), float(point[1])) for point in corners]
        min_x = max(0.0, min(point[0] for point in polygon))
        max_x = min(float(width - 1), max(point[0] for point in polygon))
        min_y = max(0.0, min(point[1] for point in polygon))
        max_y = min(float(height - 1), max(point[1] for point in polygon))
        area_ratio = ((max_x - min_x + 1) * (max_y - min_y + 1)) / float(max(width * height, 1))
        if area_ratio <= 0.04 or area_ratio >= 0.88:
            return Image.new("L", image.size, 0)

        mask = Image.new("L", image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.polygon(polygon, fill=255)
        return mask
    except Exception:
        return Image.new("L", image.size, 0)


def remove_background_by_color(
    image: Image.Image,
    background_color: tuple[int, int, int],
    tolerance: int,
    softness: int,
    edge_blur: float,
    invert_mask: bool,
    connected_only: bool = True,
    protect_subject_region: bool = True,
    subject_region_mode: str = "lash_rectangle",
) -> Image.Image:
    source = ImageOps.exif_transpose(image).convert("RGBA")
    tolerance = max(0, min(255, int(tolerance)))
    softness = max(0, min(255, int(softness)))
    edge_blur = max(0.0, min(8.0, float(edge_blur)))
    background = Image.new("RGB", source.size, background_color)
    diff = ImageChops.difference(source.convert("RGB"), background)
    red, green, blue = diff.split()
    distance = ImageChops.lighter(ImageChops.lighter(red, green), blue)

    high = tolerance if softness <= 0 else max(tolerance + 1, min(255, tolerance + softness))
    if softness <= 0:
        background_strength = distance.point(lambda value: 255 if value <= tolerance else 0)
    else:

        def background_from_distance(value: int) -> int:
            if value <= tolerance:
                return 255
            if value >= high:
                return 0
            return int(round((high - value) * 255 / (high - tolerance)))

        background_strength = distance.point(background_from_distance)

    protection_mask = None
    if connected_only:
        candidate_mask = distance.point(lambda value: 255 if value <= high else 0)
        connected_mask = extract_edge_connected_mask(candidate_mask)
        background_strength = ImageChops.multiply(background_strength, connected_mask)
    if protect_subject_region:
        if str(subject_region_mode or "").strip() == "lash_rectangle":
            candidate_protection_mask = build_lash_rectangle_protection_mask(source)
        else:
            candidate_protection_mask = build_subject_protection_mask(distance, high)
        if candidate_protection_mask.getbbox() is not None:
            protection_mask = candidate_protection_mask
            background_strength = ImageChops.multiply(background_strength, ImageOps.invert(protection_mask))

    alpha = ImageOps.invert(background_strength)
    if protection_mask is not None:
        alpha = ImageChops.multiply(alpha, protection_mask)
    if invert_mask:
        alpha = ImageOps.invert(alpha)
    alpha = ImageChops.multiply(alpha, source.getchannel("A"))
    if edge_blur > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(edge_blur))

    result = source.copy()
    result.putalpha(alpha)
    return result


def image_to_png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def crop_to_visible_alpha(image: Image.Image, padding: int = 2) -> Image.Image:
    source = ImageOps.exif_transpose(image).convert("RGBA")
    alpha_bbox = source.getchannel("A").getbbox()
    if not alpha_bbox:
        return source
    left, top, right, bottom = alpha_bbox
    safe_padding = max(0, int(padding))
    left = max(0, left - safe_padding)
    top = max(0, top - safe_padding)
    right = min(source.width, right + safe_padding)
    bottom = min(source.height, bottom + safe_padding)
    if left <= 0 and top <= 0 and right >= source.width and bottom >= source.height:
        return source
    return source.crop((left, top, right, bottom))


def regularize_lash_tray_alpha(alpha_image: Image.Image) -> tuple[Image.Image, bool]:
    """Fit a clean perspective quadrilateral to the rectangular lash tray mask."""
    alpha = alpha_image.convert("L")
    try:
        import cv2
        import numpy as np

        alpha_array = np.asarray(alpha, dtype=np.uint8)
        height, width = alpha_array.shape[:2]
        if width < 64 or height < 64:
            return alpha, False

        binary = (alpha_array >= 96).astype(np.uint8) * 255
        contours, _hierarchy = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return alpha, False
        contour = max(contours, key=cv2.contourArea)
        contour_area = float(cv2.contourArea(contour))
        canvas_area = float(max(width * height, 1))
        if contour_area / canvas_area < 0.06:
            return alpha, False

        hull = cv2.convexHull(contour)
        perimeter = float(cv2.arcLength(hull, True))
        if perimeter <= 0:
            return alpha, False

        quadrilateral = None
        for epsilon_ratio in (0.003, 0.004, 0.005, 0.006, 0.008, 0.01, 0.012, 0.015, 0.02):
            candidate = cv2.approxPolyDP(hull, epsilon_ratio * perimeter, True)
            if len(candidate) == 4 and cv2.isContourConvex(candidate):
                candidate_area = float(cv2.contourArea(candidate))
                area_ratio = candidate_area / max(contour_area, 1.0)
                if 0.96 <= area_ratio <= 1.10:
                    quadrilateral = candidate
                    break
        if quadrilateral is None:
            return alpha, False

        points = quadrilateral.reshape(4, 2).astype(np.int32)
        edge_lengths = [
            float(np.linalg.norm(points[(index + 1) % 4] - points[index]))
            for index in range(4)
        ]
        if min(edge_lengths) < min(width, height) * 0.10:
            return alpha, False

        smooth_alpha = np.zeros((height, width), dtype=np.uint8)
        cv2.fillConvexPoly(smooth_alpha, points, 255, lineType=cv2.LINE_AA)
        return Image.fromarray(smooth_alpha, mode="L"), True
    except Exception:
        return alpha, False


def regularize_lash_tray_cutout(image: Image.Image) -> tuple[Image.Image, bool]:
    """Straighten the tray outline and extend nearby edge pixels into tiny mask gaps."""
    source = ImageOps.exif_transpose(image).convert("RGBA")
    smooth_alpha, regularized = regularize_lash_tray_alpha(source.getchannel("A"))
    if not regularized:
        return source, False
    try:
        import cv2
        import numpy as np

        array = np.array(source)
        original_alpha = array[:, :, 3]
        smooth_alpha_array = np.asarray(smooth_alpha, dtype=np.uint8)
        reliable_subject = original_alpha >= 96
        added_area = (smooth_alpha_array > 2) & ~reliable_subject
        added_ratio = float(added_area.mean())
        if added_ratio > 0.035 or not reliable_subject.any():
            return source, False

        if added_area.any():
            distance_source = (~reliable_subject).astype(np.uint8)
            _distance, labels = cv2.distanceTransformWithLabels(
                distance_source,
                cv2.DIST_L2,
                5,
                labelType=cv2.DIST_LABEL_PIXEL,
            )
            subject_coordinates = np.argwhere(distance_source == 0)
            added_y, added_x = np.where(added_area)
            nearest_indexes = labels[added_y, added_x].astype(np.int64) - 1
            valid = (nearest_indexes >= 0) & (nearest_indexes < len(subject_coordinates))
            if valid.any():
                nearest_y = subject_coordinates[nearest_indexes[valid], 0]
                nearest_x = subject_coordinates[nearest_indexes[valid], 1]
                array[added_y[valid], added_x[valid], :3] = array[nearest_y, nearest_x, :3]

        array[:, :, 3] = smooth_alpha_array
        return Image.fromarray(array, mode="RGBA"), True
    except Exception:
        return source, False


def finalize_lash_tray_cutout_edges(image: Image.Image) -> Image.Image:
    regularized_image, has_regularized_edge = regularize_lash_tray_cutout(image)
    return crop_to_visible_alpha(
        clean_cutout_edge_fringe(
            regularized_image,
            contract_edge=False,
            preserve_alpha_edge=has_regularized_edge,
        ),
        padding=1,
    )


def preserve_source_pixels_with_ai_alpha(source_image: Image.Image, ai_cutout_image: Image.Image) -> Image.Image:
    """Use AI as the cutout mask while keeping original product color and scale."""
    source = ImageOps.exif_transpose(source_image).convert("RGBA")
    ai_cutout = ImageOps.exif_transpose(ai_cutout_image).convert("RGBA")
    if source.width <= 0 or source.height <= 0 or ai_cutout.width <= 0 or ai_cutout.height <= 0:
        return finalize_lash_tray_cutout_edges(ai_cutout)

    source_ratio = source.width / float(source.height)
    cutout_ratio = ai_cutout.width / float(ai_cutout.height)
    if abs(source_ratio - cutout_ratio) / max(source_ratio, 0.01) > 0.045:
        return finalize_lash_tray_cutout_edges(ai_cutout)

    alpha = ai_cutout.getchannel("A")
    if alpha.size != source.size:
        alpha = alpha.resize(source.size, Image.Resampling.LANCZOS)
    visible_bbox = alpha.getbbox()
    if not visible_bbox:
        return finalize_lash_tray_cutout_edges(ai_cutout)
    visible_area = (visible_bbox[2] - visible_bbox[0]) * (visible_bbox[3] - visible_bbox[1])
    canvas_area = max(source.width * source.height, 1)
    if visible_area / canvas_area < 0.04:
        return finalize_lash_tray_cutout_edges(ai_cutout)

    result = source.copy()
    result.putalpha(alpha)
    return finalize_lash_tray_cutout_edges(result)


def build_ai_lash_tray_cutout_prompt(base_prompt: str = "", source_size: tuple[int, int] | None = None) -> str:
    source_note = ""
    if source_size:
        source_width, source_height = source_size
        source_note = (
            f"\n原图尺寸为 {source_width}x{source_height}px。输出必须保持原图画幅比例、商品所在位置、"
            "主体高度、宽高比例、倾斜角度和透视关系一致；只把不需要的背景区域替换为纯 #00FF00，"
            "不要移动、放大、缩小、拉伸、压缩或旋转商品主体。"
        )
    rules = (
        "请严格基于上传图片执行商品抠图预处理。\n"
        "目标：只保留包含多排黑色假睫毛的长方形商品托盘/包装主体。\n"
        "必须完整保留：白色卡纸、透明塑料托盘边框、品牌文字、尺寸文字、花纹、底部说明文字、全部睫毛排布和商品透视角度。\n"
        "必须去除：桌面、左侧透明盒盖、后方支架、阴影、反光、灰尘、杂物和所有无关背景。\n"
        "颜色和高度必须严格保持：不要改变商品原有颜色、亮度、色温、饱和度、对比度和材质透明感；"
        "不要美化、不要调色、不要锐化、不要磨皮、不要重绘。\n"
        "不要改变包装文字，不要重绘文字，不要改变睫毛数量和排列，不要裁掉托盘边缘，不要添加任何新物体。\n"
        "输出要求：把完整商品主体放在纯 #00FF00 绿幕背景上。背景必须是完全纯色 #00FF00，"
        "无渐变、无纹理、无阴影、无地面、无反光、无白边、无描边、无水印。"
        "商品主体边缘必须干净平整，不要出现绿色描边、绿色光晕、绿色毛刺、绿色锯齿或绿色半透明边。"
        f"{source_note}"
    )
    base_prompt = str(base_prompt or "").strip()
    return f"{base_prompt}\n\n{rules}" if base_prompt else rules


def remove_simple_green_screen_background(image: Image.Image) -> Image.Image:
    try:
        import numpy as np

        source = ImageOps.exif_transpose(image).convert("RGBA")
        array = np.array(source)
        rgb = array[:, :, :3].astype(np.int32)
        red = rgb[:, :, 0]
        green = rgb[:, :, 1]
        blue = rgb[:, :, 2]
        green_mask = (green > 120) & (green - red > 45) & (green - blue > 45)
        array[:, :, 3] = np.where(green_mask, 0, array[:, :, 3]).astype(np.uint8)
        return Image.fromarray(array, mode="RGBA")
    except Exception:
        return image.convert("RGBA")


def clean_cutout_edge_fringe(
    image: Image.Image,
    contract_edge: bool = True,
    preserve_alpha_edge: bool = False,
) -> Image.Image:
    """Create a narrow, smooth inner antialias and remove green-screen spill."""
    source = ImageOps.exif_transpose(image).convert("RGBA")
    try:
        import cv2
        import numpy as np

        array = np.array(source)
        alpha = array[:, :, 3].astype(np.uint8)
        if alpha.size == 0 or int(alpha.max()) == 0:
            return source
        if float((alpha == 0).mean()) < 0.01:
            return source

        rgb = array[:, :, :3].astype(np.int32)
        red = rgb[:, :, 0]
        green = rgb[:, :, 1]
        blue = rgb[:, :, 2]

        if preserve_alpha_edge:
            alpha = np.where(alpha <= 2, 0, alpha).astype(np.uint8)
        else:
            # Low-alpha pixels are the wide halo seen after zooming. Build a fresh
            # contour from the reliable part of the mask, then antialias inward only.
            reliable_mask = (alpha >= 96).astype(np.uint8)
            if int(reliable_mask.sum()) <= 0:
                return source

            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            contracted_mask = (
                cv2.erode(reliable_mask, kernel, iterations=1)
                if contract_edge
                else reliable_mask
            )
            reliable_area = int(reliable_mask.sum())
            contracted_area = int(contracted_mask.sum())
            if contracted_area <= 0 or contracted_area < reliable_area * 0.86:
                contracted_mask = reliable_mask

            # The distance ramp is fully inside the contour: no outward blur or halo.
            distance = cv2.distanceTransform(contracted_mask, cv2.DIST_L2, 5)
            alpha = np.clip((distance - 0.22) * (255.0 / 0.92), 0, 255).astype(np.uint8)
            alpha[contracted_mask == 0] = 0

        partial_edge = (alpha > 0) & (alpha < 255)
        green_dominant = (green > 82) & (green > red + 12) & (green > blue + 12)
        fringe_mask = partial_edge & green_dominant
        if fringe_mask.any():
            neutral_green = np.maximum(red, blue)
            array[:, :, 1] = np.where(
                fringe_mask,
                np.minimum(green, neutral_green),
                array[:, :, 1],
            ).astype(np.uint8)

        transparent_mask = alpha <= 2
        if transparent_mask.any():
            array[:, :, :3] = np.where(transparent_mask[:, :, None], 0, array[:, :, :3]).astype(np.uint8)
        array[:, :, 3] = alpha
        return Image.fromarray(array, mode="RGBA")
    except Exception:
        return source


def remove_ai_green_screen_background(image: Image.Image) -> Image.Image:
    """Remove the AI-generated outer background while preserving inner product details."""
    source = ImageOps.exif_transpose(image).convert("RGBA")
    try:
        import cv2
        import numpy as np

        array = np.array(source)
        height, width = array.shape[:2]
        if width <= 0 or height <= 0:
            return source

        rgb = array[:, :, :3].astype(np.int32)
        alpha = array[:, :, 3]
        red = rgb[:, :, 0]
        green = rgb[:, :, 1]
        blue = rgb[:, :, 2]

        if float((alpha == 0).mean()) > 0.08 and float((alpha[0, :] == 0).mean()) > 0.45:
            return clean_cutout_edge_fringe(source)

        border_mask = np.zeros((height, width), dtype=bool)
        border_mask[0, :] = True
        border_mask[-1, :] = True
        border_mask[:, 0] = True
        border_mask[:, -1] = True
        ring = max(2, min(36, int(round(min(width, height) * 0.025))))
        edge_ring_mask = np.zeros((height, width), dtype=bool)
        edge_ring_mask[:ring, :] = True
        edge_ring_mask[-ring:, :] = True
        edge_ring_mask[:, :ring] = True
        edge_ring_mask[:, -ring:] = True

        border_pixels = rgb[edge_ring_mask & (alpha > 0)]
        if border_pixels.size:
            border_key = np.median(border_pixels, axis=0).astype(np.int32)
        else:
            border_key = np.array([0, 255, 0], dtype=np.int32)

        green_key = np.array([0, 255, 0], dtype=np.int32)
        green_distance = np.sqrt(((rgb - green_key) ** 2).sum(axis=2))
        border_distance = np.sqrt(((rgb - border_key) ** 2).sum(axis=2))
        edge_distances = border_distance[edge_ring_mask & (alpha > 0)]
        if edge_distances.size:
            adaptive_border_threshold = int(round(float(np.percentile(edge_distances, 92)) + 38))
            adaptive_border_threshold = max(52, min(145, adaptive_border_threshold))
        else:
            adaptive_border_threshold = 72
        brightness = (red + green + blue) / 3.0
        max_channel = np.maximum(np.maximum(red, green), blue)
        min_channel = np.minimum(np.minimum(red, green), blue)
        low_saturation = (max_channel - min_channel) <= 42
        edge_brightness_values = brightness[edge_ring_mask & (alpha > 0)]
        edge_is_light = bool(edge_brightness_values.size and float(np.median(edge_brightness_values)) >= 170)
        light_background_like = edge_is_light & low_saturation & (brightness >= 145) & (border_distance <= max(72, adaptive_border_threshold + 22))
        green_like = (green > 115) & (green - red > 35) & (green - blue > 35)
        candidate_mask = (
            ((green_distance <= 175) & (green > 85))
            | green_like
            | (border_distance <= adaptive_border_threshold)
            | light_background_like
        )
        candidate_mask &= alpha > 0
        if float(candidate_mask[border_mask].mean()) < 0.15:
            candidate_mask |= ((green_distance <= 215) & (green > 70) & (green > red + 18) & (green > blue + 18))
            candidate_mask |= (border_distance <= max(adaptive_border_threshold, 110))
            candidate_mask &= alpha > 0

        component_count, labels = cv2.connectedComponents(candidate_mask.astype(np.uint8), 8)
        if component_count <= 1:
            return clean_cutout_edge_fringe(remove_background_by_color(
                source,
                tuple(int(value) for value in border_key[:3]),
                tolerance=max(adaptive_border_threshold, 90),
                softness=48,
                edge_blur=0.45,
                invert_mask=False,
                connected_only=True,
                protect_subject_region=True,
                subject_region_mode="lash_rectangle",
            ))

        edge_labels = np.unique(labels[border_mask & candidate_mask])
        edge_labels = edge_labels[edge_labels > 0]
        if edge_labels.size == 0:
            return clean_cutout_edge_fringe(remove_background_by_color(
                source,
                tuple(int(value) for value in border_key[:3]),
                tolerance=max(adaptive_border_threshold, 90),
                softness=48,
                edge_blur=0.45,
                invert_mask=False,
                connected_only=True,
                protect_subject_region=True,
                subject_region_mode="lash_rectangle",
            ))

        background_mask = np.isin(labels, edge_labels)
        protection_mask_image = build_lash_rectangle_protection_mask(source)
        protection_mask = np.asarray(protection_mask_image.convert("L")) >= 128
        if protection_mask.any():
            background_mask &= ~protection_mask
        removed_ratio = float(background_mask.mean())
        if removed_ratio < 0.015:
            return clean_cutout_edge_fringe(remove_background_by_color(
                source,
                tuple(int(value) for value in border_key[:3]),
                tolerance=max(adaptive_border_threshold, 100),
                softness=56,
                edge_blur=0.45,
                invert_mask=False,
                connected_only=True,
                protect_subject_region=True,
                subject_region_mode="lash_rectangle",
            ))
        subject_alpha = np.where(background_mask, 0, 255).astype(np.uint8)
        subject_alpha_image = Image.fromarray(subject_alpha, mode="L").filter(ImageFilter.GaussianBlur(0.55))
        final_alpha = np.minimum(np.array(subject_alpha_image), alpha).astype(np.uint8)

        edge_mask = (final_alpha > 0) & (final_alpha < 252) & (green > red + 25) & (green > blue + 25)
        if edge_mask.any():
            neutral_green = np.maximum(red, blue) + 8
            array[:, :, 1] = np.where(edge_mask, np.minimum(green, neutral_green), array[:, :, 1]).astype(np.uint8)

        array[:, :, 3] = final_alpha
        return clean_cutout_edge_fringe(Image.fromarray(array, mode="RGBA"))
    except Exception:
        return clean_cutout_edge_fringe(remove_simple_green_screen_background(source))


def call_ai_lash_tray_cutout(uploaded_input: Any, prompt: str) -> dict[str, Any]:
    source_size: tuple[int, int] | None = None
    try:
        source_size = uploaded_input_to_pil_image(uploaded_input).size
    except Exception:
        source_size = None
    ai_prompt = build_ai_lash_tray_cutout_prompt(prompt, source_size=source_size)
    try:
        result = call_openrouter_images_api(
            model=NANO_BANANA_MODEL,
            prompt=ai_prompt,
            aspect_ratio=DEFAULT_ASPECT_RATIO,
            uploaded_files=[uploaded_input],
            resolution="4K",
        )
        result["channel"] = "Images API 原生 4K"
        return result
    except Exception as exc:
        raise RuntimeError(
            "OpenRouter Images API 原生 4K 调用失败。为避免画质降级，本次未使用聊天兼容通道。"
            f"原因：{exc}"
        ) from exc


def get_image_matting_model_path() -> Path:
    configured_path = str(os.environ.get("IMAGE_MATTING_MODEL_PATH") or "").strip()
    if not configured_path:
        try:
            configured_path = str(load_runtime_settings().get("image_matting_model_path") or "").strip()
        except Exception:
            configured_path = ""
    if configured_path:
        return Path(configured_path).expanduser()
    return IMAGE_MATTING_DEFAULT_MODEL_PATH


def trim_transparent_image(image: Image.Image, padding: int = 4, alpha_threshold: int = 4) -> Image.Image:
    source = image.convert("RGBA")
    alpha = source.getchannel("A").point(lambda value: 255 if value > alpha_threshold else 0)
    bbox = alpha.getbbox()
    if bbox is None:
        return source
    left, top, right, bottom = bbox
    padding = max(0, int(padding))
    crop_box = (
        max(0, left - padding),
        max(0, top - padding),
        min(source.size[0], right + padding),
        min(source.size[1], bottom + padding),
    )
    return source.crop(crop_box)


def find_lash_product_region_polygon(image: Image.Image) -> list[tuple[float, float]] | None:
    try:
        import cv2
        import numpy as np

        source = ImageOps.exif_transpose(image).convert("RGB")
        width, height = source.size
        if width <= 0 or height <= 0:
            return None

        max_detection_edge = 1400
        scale = min(max_detection_edge / float(max(width, height)), 1.0)
        small_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        small = source.resize(small_size, Image.Resampling.LANCZOS) if scale < 1.0 else source
        rgb = np.asarray(small)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        dark_mask = (gray < 95).astype(np.uint8) * 255
        if int(dark_mask.sum()) <= 0:
            return None

        close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 5))
        grouped = cv2.morphologyEx(dark_mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
        grouped = cv2.dilate(grouped, cv2.getStructuringElement(cv2.MORPH_RECT, (17, 9)), iterations=2)
        component_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(grouped, 8)
        components: list[dict[str, Any]] = []
        image_area = max(small_size[0] * small_size[1], 1)
        for component_index in range(1, component_count):
            x, y, w, h, area = [int(value) for value in stats[component_index]]
            if area < max(250, int(round(image_area * 0.0012))):
                continue
            aspect = w / float(max(h, 1))
            if area < image_area * 0.006 and aspect < 1.8:
                continue
            components.append(
                {
                    "index": component_index,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "area": area,
                    "right": x + w,
                    "bottom": y + h,
                }
            )
        if not components:
            return None

        primary = max(components, key=lambda item: int(item["area"]))
        primary_left = int(primary["x"])
        primary_right = int(primary["right"])
        primary_width = max(primary_right - primary_left, 1)
        selected_indexes: set[int] = {int(primary["index"])}
        for component in components:
            overlap_left = max(primary_left, int(component["x"]))
            overlap_right = min(primary_right, int(component["right"]))
            overlap_ratio = max(overlap_right - overlap_left, 0) / float(max(min(primary_width, int(component["w"])), 1))
            close_enough = abs((int(component["x"]) + int(component["right"])) / 2 - (primary_left + primary_right) / 2) <= primary_width * 0.34
            if overlap_ratio >= 0.45 or close_enough:
                selected_indexes.add(int(component["index"]))

        selected_mask = np.isin(labels, list(selected_indexes))
        ys, xs = np.where(selected_mask)
        if xs.size < 200:
            return None

        points = np.column_stack((xs.astype("float32"), ys.astype("float32")))
        center = points.mean(axis=0)
        centered = points - center
        covariance = np.cov(centered, rowvar=False)
        values, vectors = np.linalg.eigh(covariance)
        ordered = vectors[:, np.argsort(values)[::-1]]
        axis_a = ordered[:, 0]
        axis_b = ordered[:, 1]
        if abs(axis_a[0]) >= abs(axis_b[0]):
            x_axis = axis_a
            y_axis = axis_b
        else:
            x_axis = axis_b
            y_axis = axis_a
        if x_axis[0] < 0:
            x_axis = -x_axis
        if y_axis[1] < 0:
            y_axis = -y_axis

        projected_x = points @ x_axis
        projected_y = points @ y_axis
        left = float(projected_x.min())
        right = float(projected_x.max())
        top = float(projected_y.min())
        bottom = float(projected_y.max())
        region_width = max(right - left, 1.0)
        region_height = max(bottom - top, 1.0)

        left -= region_width * 0.08
        right += region_width * 0.035
        top -= region_height * 0.28
        bottom += region_height * 0.075

        small_corners = [
            x_axis * left + y_axis * top,
            x_axis * right + y_axis * top,
            x_axis * right + y_axis * bottom,
            x_axis * left + y_axis * bottom,
        ]
        inverse_scale = 1.0 / max(scale, 1e-6)
        polygon = [
            (
                max(0.0, min(float(width - 1), float(point[0]) * inverse_scale)),
                max(0.0, min(float(height - 1), float(point[1]) * inverse_scale)),
            )
            for point in small_corners
        ]
        min_x = min(point[0] for point in polygon)
        max_x = max(point[0] for point in polygon)
        min_y = min(point[1] for point in polygon)
        max_y = max(point[1] for point in polygon)
        area_ratio = ((max_x - min_x + 1) * (max_y - min_y + 1)) / float(max(width * height, 1))
        if area_ratio <= 0.08 or area_ratio >= 0.78:
            return None
        return polygon
    except Exception:
        return None


def cut_to_lash_product_region(original_image: Image.Image, fallback_image: Image.Image) -> Image.Image:
    source = ImageOps.exif_transpose(original_image).convert("RGBA")
    polygon = find_lash_product_region_polygon(source)
    if not polygon:
        return trim_transparent_image(fallback_image)
    mask = Image.new("L", source.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon(polygon, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.35))
    result = source.copy()
    result.putalpha(ImageChops.multiply(mask, source.getchannel("A")))
    return trim_transparent_image(result, padding=2, alpha_threshold=2)


class ImageMattingSegmenter:
    """Local ONNX matting backend adapted from pangxiaobin/image-matting."""

    def __init__(self, model_path: Path, model_input_size: tuple[int, int] = IMAGE_MATTING_INPUT_SIZE) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("缺少 onnxruntime，请先安装依赖：pip install onnxruntime opencv-python") from exc

        resolved_model_path = Path(model_path).expanduser()
        if not resolved_model_path.exists() or not resolved_model_path.is_file():
            raise RuntimeError(
                "未找到 image-matting 的 RMBG-1.4 ONNX 模型文件。"
                f"请把 model.onnx 放到：{IMAGE_MATTING_DEFAULT_MODEL_PATH}，"
                "或通过环境变量 IMAGE_MATTING_MODEL_PATH 指定模型路径。"
            )

        self.model_path = resolved_model_path
        self.model_input_size = (int(model_input_size[0]), int(model_input_size[1]))
        providers = self.get_available_providers(ort)
        try:
            if "DmlExecutionProvider" in providers:
                session_options = ort.SessionOptions()
                session_options.enable_mem_pattern = False
                session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                self.ort_session = ort.InferenceSession(
                    str(self.model_path),
                    providers=providers,
                    sess_options=session_options,
                )
            else:
                self.ort_session = ort.InferenceSession(str(self.model_path), providers=providers)
        except Exception as exc:
            raise RuntimeError(f"image-matting 模型加载失败：{exc}") from exc

    @staticmethod
    def get_available_providers(ort: Any) -> list[str]:
        available_providers = list(ort.get_available_providers())
        if "CUDAExecutionProvider" in available_providers:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if "DmlExecutionProvider" in available_providers:
            return ["DmlExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def preprocess_image(self, image_array: Any) -> Any:
        import numpy as np

        if len(image_array.shape) < 3:
            image_array = image_array[:, :, np.newaxis]
        resized = np.array(Image.fromarray(image_array).resize(self.model_input_size, Image.Resampling.BILINEAR))
        normalized = resized.astype(np.float32) / 255.0
        mean = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        normalized = (normalized - mean) / np.array([1.0, 1.0, 1.0], dtype=np.float32)
        normalized = normalized.transpose(2, 0, 1)
        return np.expand_dims(normalized, axis=0)

    @staticmethod
    def postprocess_mask(result: Any, image_size: tuple[int, int]) -> Image.Image:
        import numpy as np

        mask_array = np.squeeze(result).astype(np.float32)
        mask = Image.fromarray(mask_array).resize(image_size, Image.Resampling.BILINEAR)
        resized = np.asarray(mask).astype(np.float32)
        max_value = float(resized.max()) if resized.size else 0.0
        min_value = float(resized.min()) if resized.size else 0.0
        if max_value - min_value <= 1e-6:
            alpha = np.zeros_like(resized, dtype=np.uint8)
        else:
            alpha = ((resized - min_value) / (max_value - min_value) * 255.0).clip(0, 255).astype(np.uint8)
        return Image.fromarray(alpha, mode="L")

    def segment_image(self, image: Image.Image, trim_result: bool = True) -> Image.Image:
        import numpy as np

        original = ImageOps.exif_transpose(image).convert("RGBA")
        input_image = original.convert("RGB")
        image_array = np.array(input_image)
        preprocessed = self.preprocess_image(image_array)
        ort_inputs = {self.ort_session.get_inputs()[0].name: preprocessed}
        try:
            ort_outputs = self.ort_session.run(None, ort_inputs)
        except Exception as exc:
            raise RuntimeError(f"image-matting ONNX 推理失败：{exc}") from exc

        alpha = self.postprocess_mask(ort_outputs[0][0][0], input_image.size)
        alpha = alpha.filter(ImageFilter.GaussianBlur(0.35))
        alpha = ImageEnhance.Contrast(alpha).enhance(1.08)
        alpha = ImageChops.multiply(alpha, original.getchannel("A"))
        result = original.copy()
        result.putalpha(alpha)
        if trim_result:
            return trim_transparent_image(result)
        return result


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
    image_bytes = get_uploaded_file_bytes(uploaded_input)
    if not image_bytes:
        raise RuntimeError("上传图片为空，请重新上传。")
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return ImageOps.exif_transpose(image).convert("RGBA")
    except Exception as exc:
        raise RuntimeError(f"无法读取上传图片：{exc}") from exc


def run_ai_background_cutout_job(job_context: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    uploaded_files = [prepare_uploaded_input(item) for item in list(job_context.get("uploaded_files") or [])]
    if not uploaded_files:
        raise RuntimeError("请先上传 1 张需要抠图的图片。")
    max_output_images = int(job_context.get("max_output_images") or 0)
    if max_output_images > 0:
        uploaded_files = uploaded_files[:max_output_images]

    result_images: list[str] = []
    source_images: list[str] = []
    captions: list[str] = []
    text_parts: list[str] = []
    total_files = max(len(uploaded_files), 1)
    base_prompt = str(job_context.get("prompt") or "")

    for image_index, uploaded_input in enumerate(uploaded_files, start=1):
        if job_id:
            progress = 12 + math.floor(((image_index - 1) / total_files) * 58)
            set_task_progress(job_id, progress, f"正在调用 AI 抠出睫毛托盘 {image_index}/{total_files}")
        source_name = get_uploaded_input_name(uploaded_input) or f"原图 {image_index}"
        source_images.append(uploaded_input_to_data_url(uploaded_input))
        source_image = uploaded_input_to_pil_image(uploaded_input)

        ai_result = call_ai_lash_tray_cutout(uploaded_input, base_prompt)
        ai_images = list(ai_result.get("images") or [])
        if not ai_images:
            raise RuntimeError("AI 没有返回可用的抠图预处理图片，请重试。")

        if job_id:
            progress = 68 + math.floor((image_index / total_files) * 12)
            set_task_progress(job_id, min(progress, 82), f"正在把 AI 绿幕图转成透明 PNG {image_index}/{total_files}")
        ai_image_bytes, _mime_type = load_image_bytes_from_url(str(ai_images[0]))
        try:
            with Image.open(io.BytesIO(ai_image_bytes)) as ai_image:
                ai_transparent_image = remove_ai_green_screen_background(ai_image)
                transparent_image = preserve_source_pixels_with_ai_alpha(source_image, ai_transparent_image)
        except Exception as exc:
            raise RuntimeError(f"AI 抠图结果转透明 PNG 失败：{exc}") from exc

        result_images.append(image_bytes_to_data_url(image_to_png_bytes(transparent_image), "image/png"))
        captions.append(f"{source_name} - AI 抠图后透明 PNG")
        ai_text = str(ai_result.get("text") or "").strip()
        if ai_text:
            text_parts.append(ai_text)

    if job_id:
        set_task_progress(job_id, 84, "正在生成透明 PNG 预览")
    return {
        "images": result_images,
        "source_images": source_images[: len(result_images)],
        "captions": captions,
        "text": "\n\n".join(
            part
            for part in [
                "已由 AI 先定位带睫毛的托盘区域并去除杂质背景，再由代码优先使用原图像素生成透明 PNG，保持商品颜色和主体高度一致。",
                *text_parts,
            ]
            if str(part or "").strip()
        ).strip(),
    }


def build_checkerboard_preview(image: Image.Image, max_edge: int = 1600) -> Image.Image:
    preview = image.convert("RGBA")
    max_edge = max(320, int(max_edge))
    if max(preview.size) > max_edge:
        ratio = max_edge / float(max(preview.size))
        next_size = (
            max(1, int(round(preview.size[0] * ratio))),
            max(1, int(round(preview.size[1] * ratio))),
        )
        preview = preview.resize(next_size, Image.Resampling.LANCZOS)

    block = max(10, min(preview.size) // 24)
    checker = Image.new("RGBA", preview.size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(checker)
    for y in range(0, preview.size[1], block):
        for x in range(0, preview.size[0], block):
            if ((x // block) + (y // block)) % 2:
                draw.rectangle(
                    (x, y, min(x + block, preview.size[0]), min(y + block, preview.size[1])),
                    fill=(230, 236, 245, 255),
                )
    checker.alpha_composite(preview)
    return checker


def render_background_cutout_feature(feature: dict[str, Any]) -> None:
    feature_key = str(feature.get("key") or "background_cutout")
    result = st.session_state.feature_results.get(feature_key) or {}
    job_info = st.session_state.background_jobs.get(feature_key) or {}

    st.markdown('<div class="workspace-panel">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="feature-title">{feature["name"]}<span class="feature-badge">AI 抠图转透明</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="feature-desc">上传图片后先由 AI 抠出完整睫毛托盘并清理杂质背景，再由代码把纯色背景转为透明 PNG。</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="meta-row">'
        '<span class="meta-pill">AI 先抠托盘</span>'
        '<span class="meta-pill">去除杂质背景</span>'
        '<span class="meta-pill">绿幕转透明</span>'
        '<span class="meta-pill">保留完整睫毛托</span>'
        '<span class="meta-pill">Nano Banana 2 生图</span>'
        '<span class="meta-pill">导出透明 PNG</span>'
        '<span class="meta-pill">支持 JPG、PNG、WEBP</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    left_col, right_col = st.columns([0.86, 1.14], gap="medium")
    uploaded_file = None
    with left_col:
        st.markdown('<div class="result-block-title">上传图片</div>', unsafe_allow_html=True)
        uploaded_file = render_single_image_uploader(
            "上传需要抠图的图片",
            key=f"uploader_{feature_key}",
            help_text="请上传包含睫毛托盘/包装的商品图。AI 会先抠出完整带睫毛的托盘并清理杂质背景。",
        )
        cutout_prompt = str(feature.get("default_prompt") or "").strip()
        st.caption("流程：AI 先输出只有睫毛托盘的纯绿背景图，再由代码把绿幕背景转成透明 PNG。")
        submitted = st.button("只抠睫毛商品区域", key=f"process_{feature_key}", type="secondary", use_container_width=True)
        if submitted:
            if job_info.get("status") == "running":
                st.warning("当前抠图任务正在处理中，请等待完成后再提交。")
            elif uploaded_file is None:
                st.warning("请先上传 1 张需要抠图的图片。")
            else:
                st.session_state.feature_results.pop(feature_key, None)
                submit_feature_job(
                    feature,
                    {
                        "feature": dict(feature),
                        "model": NANO_BANANA_MODEL,
                        "prompt": str(cutout_prompt).strip(),
                        "uploaded_files": [prepare_uploaded_input(uploaded_file)],
                        "batch_groups": [],
                        "output_mode": "image",
                        "max_output_images": 1,
                        "account_name": str(st.session_state.get("auth_username") or "admin"),
                        "aspect_ratio": DEFAULT_ASPECT_RATIO,
                    },
                )
                st.info("已提交 AI 抠图任务，完成后会在右侧显示透明 PNG。")
                st.rerun()

    result = st.session_state.feature_results.get(feature_key) or {}
    with right_col:
        st.markdown('<div class="result-block-title">结果图预览</div>', unsafe_allow_html=True)
        if uploaded_file is not None:
            st.markdown('<div class="panel-subtitle">原图</div>', unsafe_allow_html=True)
            try:
                render_zoomable_image_gallery(
                    [uploaded_input_to_data_url(uploaded_file)],
                    columns=1,
                    thumb_height=180,
                    component_key=f"cutout_source_{feature_key}",
                    fit_mode="contain",
                    max_width_percent=62,
                    compress_preview=True,
                    include_full_src=True,
                )
            except Exception:
                st.caption("原图预览暂时无法显示。")
        if result.get("images"):
            st.markdown('<div class="panel-subtitle">AI 抠图透明 PNG 结果</div>', unsafe_allow_html=True)
            result_id = re.sub(r"[^a-zA-Z0-9_]", "_", str(result.get("result_id") or "latest"))
            render_zoomable_image_gallery(
                list(result.get("images") or []),
                columns=1,
                thumb_height=None,
                component_key=f"cutout_result_{result_id}",
                fit_mode="contain",
                max_width_percent=62,
                compress_preview=False,
                include_full_src=True,
            )
        else:
            render_result_preview([], show_title=False)
        if job_info.get("status") == "running":
            render_running_job_status(feature_key)
        elif job_info.get("status") == "error":
            st.error(f"后台任务失败：{format_user_facing_error_message(job_info.get('error'))}")
        elif job_info.get("status") == "completed":
            st.success("睫毛商品区域抠图任务已完成。")

    st.markdown("</div>", unsafe_allow_html=True)
    render_history_records(feature)


def render_replacement_infinite_canvas_feature(feature: dict[str, Any]) -> None:
    runtime_settings = load_runtime_settings()
    try:
        static_port = int(runtime_settings.get("jimeng_static_port") or DEFAULT_JIMENG_STATIC_PORT)
    except Exception:
        static_port = DEFAULT_JIMENG_STATIC_PORT
    canvas_url = build_infinite_canvas_url(
        str(runtime_settings.get("public_app_url") or DEFAULT_PUBLIC_APP_URL),
        static_port,
        str(st.session_state.get("auth_username") or "访客"),
    )

    st.markdown('<div class="workspace-panel">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="feature-title">{html.escape(str(feature.get("name") or "无限画布"))}'
        '<span class="feature-badge">新版</span></div>',
        unsafe_allow_html=True,
    )
    if not (INFINITE_CANVAS_BUILD_DIR / "index.html").exists():
        st.error("新版无限画布尚未构建，请先运行小哈启动脚本完成初始化。")
    else:
        st.iframe(canvas_url, width="stretch", height=920)
    st.markdown("</div>", unsafe_allow_html=True)


def render_infinite_canvas_feature(feature: dict[str, Any], model: str, aspect_ratio: str) -> None:
    result = st.session_state.feature_results.get(feature["key"]) or {}
    job_info = st.session_state.background_jobs.get(feature["key"]) or {}
    step_features = get_infinite_canvas_step_features()
    step_options = [str(item.get("key") or "") for item in step_features if item.get("key")]
    step_name_map = {str(item.get("key") or ""): str(item.get("name") or item.get("key") or "") for item in step_features}

    st.markdown('<div class="workspace-panel">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="feature-title">{feature["name"]}<span class="feature-badge">自由组合</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="feature-desc">上传图片后，把已有功能按顺序串起来处理；前一步的结果会自动进入下一步。</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="meta-row">'
        '<span class="meta-pill">最多上传 6 张</span>'
        '<span class="meta-pill">最多组合 4 步</span>'
        '<span class="meta-pill">支持高清、去睫毛、扩图、单眼变双眼</span>'
        '<span class="meta-pill">每张图输出 1 张最终结果</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    submitted = False
    left_col, right_col = st.columns([0.78, 1.22], gap="medium")
    with left_col:
        preview_step_count = int(st.session_state.get("infinite_canvas_step_count", min(2, INFINITE_CANVAS_MAX_STEPS)) or 1)
        preview_step_count = max(1, min(INFINITE_CANVAS_MAX_STEPS, preview_step_count))
        selected_steps_for_preview: list[str] = []
        if step_options:
            for preview_index in range(preview_step_count):
                preview_state_key = f"infinite_canvas_step_{preview_index}"
                default_preview_step = step_options[min(preview_index, len(step_options) - 1)]
                selected_steps_for_preview.append(str(st.session_state.get(preview_state_key) or default_preview_step))
        preview_outpaint_index = next(
            (index for index, step_key in enumerate(selected_steps_for_preview) if step_key == "outpaint"),
            None,
        )
        preview_outpaint_prefix = (
            f"infinite_canvas_step_{preview_outpaint_index}_outpaint"
            if preview_outpaint_index is not None
            else "infinite_canvas_outpaint"
        )
        outpaint_top_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(st.session_state.get(f"{preview_outpaint_prefix}_top", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
        outpaint_bottom_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(st.session_state.get(f"{preview_outpaint_prefix}_bottom", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
        outpaint_left_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(st.session_state.get(f"{preview_outpaint_prefix}_left", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
        outpaint_right_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(st.session_state.get(f"{preview_outpaint_prefix}_right", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
        canvas_outpaint_preview_renderer = None
        if "outpaint" in selected_steps_for_preview:
            def canvas_outpaint_preview_renderer(uploaded_input: Any, item_index: int, component_key: str) -> None:
                render_outpaint_extension_preview_card(
                    uploaded_input,
                    outpaint_top_px,
                    outpaint_bottom_px,
                    outpaint_left_px,
                    outpaint_right_px,
                    f"{component_key}_canvas_outpaint_{item_index}",
                    max_preview_edge=760,
                    drag_state_keys={
                        "top": f"{preview_outpaint_prefix}_top",
                        "bottom": f"{preview_outpaint_prefix}_bottom",
                        "left": f"{preview_outpaint_prefix}_left",
                        "right": f"{preview_outpaint_prefix}_right",
                    },
                )
        st.markdown('<div class="result-block-title">上传图片</div>', unsafe_allow_html=True)
        canvas_source_files = render_multi_image_uploader(
            "上传无限画布图片",
            key="infinite_canvas_uploader",
            help_text=f"可上传 JPG / PNG / WEBP。无限画布最多使用 {INFINITE_CANVAS_MAX_INPUT_IMAGES} 张图片。",
            max_files=INFINITE_CANVAS_MAX_INPUT_IMAGES,
            preview_renderer=canvas_outpaint_preview_renderer,
            preview_slot_count=1 if canvas_outpaint_preview_renderer is not None else INFINITE_CANVAS_MAX_INPUT_IMAGES,
        )
        canvas_outpaint_limits = {
            "top": OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
            "bottom": OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
            "left": OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
            "right": OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
        }
        if canvas_source_files:
            try:
                canvas_outpaint_limits = get_outpaint_extension_limits(canvas_source_files[0])
            except Exception:
                pass
        if "outpaint" in selected_steps_for_preview:
            st.caption("紫色虚线是预计扩图后的范围，白色虚线是原图位置；四边拉满时画布宽高最大为原图的 3 倍。")

        st.markdown('<div class="panel-subtitle">组合步骤</div>', unsafe_allow_html=True)
        canvas_step_settings: list[dict[str, Any]] = []
        if not step_options:
            st.warning("还没有可组合的功能。")
            selected_steps: list[str] = []
        else:
            step_count = int(
                st.slider(
                    "步骤数量",
                    min_value=1,
                    max_value=INFINITE_CANVAS_MAX_STEPS,
                    value=min(2, INFINITE_CANVAS_MAX_STEPS),
                    step=1,
                    key="infinite_canvas_step_count",
                )
            )
            selected_steps = []
            for step_index in range(step_count):
                state_key = f"infinite_canvas_step_{step_index}"
                if state_key not in st.session_state:
                    st.session_state[state_key] = step_options[min(step_index, len(step_options) - 1)]
                selected_key = st.selectbox(
                    f"第 {step_index + 1} 步",
                    step_options,
                    key=state_key,
                    format_func=lambda value: step_name_map.get(str(value), str(value)),
                )
                selected_steps.append(str(selected_key))
                step_setting: dict[str, Any] = {}
                if selected_key == "outpaint":
                    st.markdown(f'<div class="panel-subtitle">第 {step_index + 1} 步设置：扩图参数</div>', unsafe_allow_html=True)
                    vertical_limit = max(int(canvas_outpaint_limits["top"]), 1)
                    horizontal_limit = max(int(canvas_outpaint_limits["left"]), 1)
                    top_state_key = f"infinite_canvas_step_{step_index}_outpaint_top"
                    bottom_state_key = f"infinite_canvas_step_{step_index}_outpaint_bottom"
                    left_state_key = f"infinite_canvas_step_{step_index}_outpaint_left"
                    right_state_key = f"infinite_canvas_step_{step_index}_outpaint_right"
                    for state_key, direction_limit in (
                        (top_state_key, vertical_limit),
                        (bottom_state_key, vertical_limit),
                        (left_state_key, horizontal_limit),
                        (right_state_key, horizontal_limit),
                    ):
                        if state_key in st.session_state:
                            st.session_state[state_key] = max(
                                0,
                                min(direction_limit, int(st.session_state[state_key] or 0)),
                            )
                    step_top_col, step_bottom_col = st.columns(2, gap="small")
                    with step_top_col:
                        step_top_px = int(
                            st.slider(
                                "上方扩展像素",
                                0,
                                vertical_limit,
                                get_outpaint_default_extension(vertical_limit),
                                50 if vertical_limit >= 50 else 1,
                                key=top_state_key,
                            )
                        )
                    with step_bottom_col:
                        step_bottom_px = int(
                            st.slider(
                                "下方扩展像素",
                                0,
                                vertical_limit,
                                get_outpaint_default_extension(vertical_limit),
                                50 if vertical_limit >= 50 else 1,
                                key=bottom_state_key,
                            )
                        )
                    step_left_col, step_right_col = st.columns(2, gap="small")
                    with step_left_col:
                        step_left_px = int(
                            st.slider(
                                "左侧扩展像素",
                                0,
                                horizontal_limit,
                                get_outpaint_default_extension(horizontal_limit),
                                50 if horizontal_limit >= 50 else 1,
                                key=left_state_key,
                            )
                        )
                    with step_right_col:
                        step_right_px = int(
                            st.slider(
                                "右侧扩展像素",
                                0,
                                horizontal_limit,
                                get_outpaint_default_extension(horizontal_limit),
                                50 if horizontal_limit >= 50 else 1,
                                key=right_state_key,
                            )
                        )
                    step_setting["outpaint"] = {
                        "top": step_top_px,
                        "bottom": step_bottom_px,
                        "left": step_left_px,
                        "right": step_right_px,
                    }
                if selected_key == "hd_batch":
                    st.markdown(f'<div class="panel-subtitle">第 {step_index + 1} 步设置：高清参考图（可选）</div>', unsafe_allow_html=True)
                    step_ref_upload_col, step_ref_gallery_col = st.columns([1, 1], gap="small")
                    with step_ref_upload_col:
                        step_hd_reference_upload = render_single_image_uploader(
                            "上传高清参考图",
                            key=f"infinite_canvas_step_{step_index}_hd_reference",
                            help_text="用于当前高清步骤的皮肤质感或细节参考；不选择时使用默认参考。",
                        )
                    step_hd_reference_file = step_hd_reference_upload
                    with step_ref_gallery_col:
                        step_skin_reference_files = get_skin_texture_reference_files()
                        if step_skin_reference_files:
                            step_reference_name = st.radio(
                                "选择高清参考图库",
                                options=["不使用图库参考图", *[path.name for path in step_skin_reference_files]],
                                index=0,
                                key=f"infinite_canvas_step_{step_index}_hd_reference_gallery",
                                label_visibility="collapsed",
                            )
                            if step_reference_name != "不使用图库参考图":
                                step_hd_reference_file = next(
                                    (path for path in step_skin_reference_files if path.name == step_reference_name),
                                    step_hd_reference_file,
                                )
                                st.caption(f"当前使用图库参考图：{step_reference_name}")
                        else:
                            st.caption("暂无可选参考图库，可直接上传参考图。")
                    if step_hd_reference_file is not None:
                        step_setting["hd_reference"] = prepare_uploaded_input(step_hd_reference_file)
                canvas_step_settings.append(step_setting)

        first_outpaint_settings = next(
            (dict(step_setting.get("outpaint") or {}) for step_setting in canvas_step_settings if step_setting.get("outpaint")),
            {},
        )
        outpaint_top_px = int(first_outpaint_settings.get("top", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)
        outpaint_bottom_px = int(first_outpaint_settings.get("bottom", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)
        outpaint_left_px = int(first_outpaint_settings.get("left", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)
        outpaint_right_px = int(first_outpaint_settings.get("right", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)
        if False and "outpaint" in selected_steps:
            st.markdown('<div class="panel-subtitle">扩图参数</div>', unsafe_allow_html=True)
            top_col, bottom_col = st.columns(2, gap="small")
            with top_col:
                outpaint_top_px = int(
                    st.slider("上方扩展像素", 0, OUTPAINT_FALLBACK_MAX_EXTENSION_PX, OUTPAINT_DEFAULT_EXTENSION_PX, 50, key="infinite_canvas_outpaint_top")
                )
            with bottom_col:
                outpaint_bottom_px = int(
                    st.slider("下方扩展像素", 0, OUTPAINT_FALLBACK_MAX_EXTENSION_PX, OUTPAINT_DEFAULT_EXTENSION_PX, 50, key="infinite_canvas_outpaint_bottom")
                )
            left_px_col, right_px_col = st.columns(2, gap="small")
            with left_px_col:
                outpaint_left_px = int(
                    st.slider("左侧扩展像素", 0, OUTPAINT_FALLBACK_MAX_EXTENSION_PX, OUTPAINT_DEFAULT_EXTENSION_PX, 50, key="infinite_canvas_outpaint_left")
                )
            with right_px_col:
                outpaint_right_px = int(
                    st.slider("右侧扩展像素", 0, OUTPAINT_FALLBACK_MAX_EXTENSION_PX, OUTPAINT_DEFAULT_EXTENSION_PX, 50, key="infinite_canvas_outpaint_right")
                )

        hd_reference_file = None
        if False and "hd_batch" in selected_steps:
            st.markdown('<div class="panel-subtitle">高清参考图（可选）</div>', unsafe_allow_html=True)
            ref_upload_col, ref_gallery_col = st.columns([1, 1], gap="small")
            with ref_upload_col:
                hd_reference_upload = render_single_image_uploader(
                    "上传高清参考图",
                    key="infinite_canvas_hd_reference",
                    help_text="用于高清步骤的皮肤质感或细节参考；不选择时使用默认参考。",
                )
            hd_reference_file = hd_reference_upload
            with ref_gallery_col:
                skin_texture_reference_files = get_skin_texture_reference_files()
                if skin_texture_reference_files:
                    selected_reference_name = st.radio(
                        "选择高清参考图库",
                        options=["不使用图库参考图", *[path.name for path in skin_texture_reference_files]],
                        index=0,
                        key="infinite_canvas_hd_reference_gallery",
                        label_visibility="collapsed",
                    )
                    if selected_reference_name != "不使用图库参考图":
                        hd_reference_file = next(
                            (path for path in skin_texture_reference_files if path.name == selected_reference_name),
                            hd_reference_file,
                        )
                        st.caption(f"当前使用图库参考图：{selected_reference_name}")
                else:
                    st.caption("暂无可选参考图库，可直接上传参考图。")

        st.markdown('<div class="panel-subtitle">补充要求</div>', unsafe_allow_html=True)
        custom_prompt = st.text_area(
            "无限画布补充要求",
            key="infinite_canvas_prompt",
            placeholder="例如：整体保持真实商业修图质感，人物身份和五官不要变化。",
            height=96,
            label_visibility="collapsed",
        )

        selector_col, process_col = st.columns([1.15, 0.95], gap="small")
        with selector_col:
            active_model = st.selectbox(
                "模型切换",
                [NANO_BANANA_MODEL],
                index=0,
                format_func=get_model_display_name,
                key="model_select_infinite_canvas",
            )
        with process_col:
            st.markdown('<div class="panel-subtitle">&nbsp;</div>', unsafe_allow_html=True)
            submitted = st.button(
                "开始组合处理",
                key="process_infinite_canvas",
                type="secondary",
                use_container_width=True,
            )

    with right_col:
        st.markdown('<div class="canvas-right-column-marker"></div>', unsafe_allow_html=True)
        st.markdown('<div class="result-block-title">右侧预览</div>', unsafe_allow_html=True)
        if selected_steps:
            flow_chips = "".join(
                f'<span class="canvas-flow-chip">{html.escape(step_name_map.get(step_key, step_key))}</span>'
                for step_key in selected_steps
            )
            st.markdown(f'<div class="canvas-flow-summary">{flow_chips}</div>', unsafe_allow_html=True)
        result_images = list(result.get("images") or [])
        result_captions = list(result.get("captions") or [])
        result_download_images = build_result_download_sources(
            result_images,
            list(result.get("history_records") or []),
        )
        if result_images and result_captions:
            render_result_preview_with_captions(
                result_images,
                result_captions,
                feature["key"],
                download_images=result_download_images,
            )
        elif result_images:
            render_result_preview(
                result_images,
                show_title=False,
                download_images=result_download_images,
            )
        elif canvas_source_files:
            st.markdown('<div class="panel-subtitle">输入图预览</div>', unsafe_allow_html=True)
            preview_file = canvas_source_files[0]
            if "outpaint" in selected_steps:
                render_outpaint_extension_preview_card(
                    preview_file,
                    outpaint_top_px,
                    outpaint_bottom_px,
                    outpaint_left_px,
                    outpaint_right_px,
                    "infinite_canvas_right_preview",
                    max_preview_edge=520,
                )
                st.caption("紫色虚线是预计扩图后的范围，白色虚线是原图位置。")
            else:
                render_zoomable_image_gallery(
                    [uploaded_input_to_data_url(preview_file)],
                    columns=1,
                    thumb_height=520,
                    component_key="infinite_canvas_right_input_preview",
                    fit_mode="contain",
                    max_width_percent=88,
                    compress_preview=True,
                    include_full_src=True,
                )
            st.caption("处理完成后，这里会自动切换成最终结果图。")
        else:
            render_result_preview(result_images, show_title=False)

    if job_info.get("status") == "running":
        render_running_job_status(feature["key"])
    elif job_info.get("status") == "error":
        st.error(f"后台任务失败：{format_user_facing_error_message(job_info.get('error'))}")
    elif job_info.get("status") == "completed":
        st.success("无限画布处理完成，可以继续换组合或查看历史。")
        result_text = str(result.get("text") or "").strip()
        if result_text:
            st.info(result_text)
        storage_error = str(result.get("storage_error") or "").strip()
        if storage_error:
            st.warning(storage_error)

    if submitted:
        if job_info.get("status") == "running":
            st.warning("当前无限画布已有任务在后台处理，请等完成后再发起新的组合。")
            st.markdown("</div>", unsafe_allow_html=True)
            return
        if not canvas_source_files:
            st.warning("请先上传至少 1 张图片。")
        elif not selected_steps:
            st.warning("请至少选择 1 个组合步骤。")
        elif "outpaint" in selected_steps and (outpaint_top_px + outpaint_bottom_px + outpaint_left_px + outpaint_right_px) <= 0:
            st.warning("扩图步骤至少需要一个方向大于 0。")
        else:
            st.session_state.feature_results.pop(feature["key"], None)
            step_names = [step_name_map.get(step_key, step_key) for step_key in selected_steps]
            flow_text = " → ".join(step_names)
            final_prompt = f"无限画布组合流程：{flow_text}"
            if custom_prompt.strip():
                final_prompt += f"\n\n补充要求：{custom_prompt.strip()}"
            submit_feature_job(
                feature,
                {
                    "feature": dict(feature),
                    "model": active_model,
                    "prompt": final_prompt,
                    "custom_prompt": custom_prompt,
                    "uploaded_files": [prepare_uploaded_input(item) for item in canvas_source_files],
                    "canvas_steps": selected_steps,
                    "canvas_step_settings": canvas_step_settings,
                    "canvas_outpaint": {
                        "top": outpaint_top_px,
                        "bottom": outpaint_bottom_px,
                        "left": outpaint_left_px,
                        "right": outpaint_right_px,
                    },
                    "canvas_hd_reference": prepare_uploaded_input(hd_reference_file) if hd_reference_file is not None else None,
                    "batch_groups": [],
                    "output_mode": feature["output_mode"],
                    "max_output_images": 0,
                    "account_name": str(st.session_state.get("auth_username") or "admin"),
                    "aspect_ratio": aspect_ratio,
                },
            )
            st.info("无限画布任务已提交到后台，完成后会自动显示在右侧。")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    render_history_records(feature)


def render_openrouter_feature(feature: dict[str, Any], model: str, aspect_ratio: str) -> None:
    if feature.get("key") == "infinite_canvas":
        render_replacement_infinite_canvas_feature(feature)
        return
    if feature.get("key") == "background_cutout":
        render_background_cutout_feature(feature)
        return
    default_model_for_feature = str(feature.get("model") or model)
    feature_mode = str(feature.get("mode") or "openrouter")
    supports_jimeng_generation = feature_mode == "jimeng"
    model_options_for_feature = MODEL_OPTIONS
    if feature.get("key") == "hd_batch":
        default_model_for_feature = NANO_BANANA_MODEL
        model_options_for_feature = [NANO_BANANA_MODEL]
    elif feature.get("key") in A_PLUS_IMAGES_API_FEATURE_KEYS:
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
    supports_amazon_a_plus = feature["key"] == AMAZON_A_PLUS_FEATURE_KEY
    supports_main_image_a_plus = feature["key"] == MAIN_IMAGE_A_PLUS_FEATURE_KEY
    supports_a_plus_images_api = supports_amazon_a_plus or supports_main_image_a_plus
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
    if job_info.get("status") == "running":
        render_running_job_status(feature["key"])
    elif job_info.get("status") == "error":
        st.error(f"后台任务失败：{format_user_facing_error_message(job_info.get('error'))}")
    elif job_info.get("status") == "completed":
        st.success("任务已完成，结果已更新到右侧预览区。")

    meta_items = ['<span class="meta-pill">JPG、PNG、WEBP · 单张≤50MB</span>']
    if supports_main_image_a_plus:
        meta_items.append(f'<span class="meta-pill">最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张参考图</span>')
        meta_items.append('<span class="meta-pill">4 种模式 · 支持指定元素替换</span>')
        meta_items.append('<span class="meta-pill">3 种规格 · 套版跟随模板</span>')
        meta_items.append('<span class="meta-pill">原生 4K · 文字不截断</span>')
    elif supports_amazon_a_plus:
        meta_items.append('<span class="meta-pill">原生 4K 高清底稿</span>')
        meta_items.append('<span class="meta-pill">纯绿幕独立元素底稿</span>')
        meta_items.append('<span class="meta-pill">自动裁切并导出分层 PSD</span>')
    elif supports_outpaint:
        meta_items.append('<span class="meta-pill">画布宽高最大可扩至原图 3 倍</span>')
        meta_items.append('<span class="meta-pill">自动匹配扩展画幅</span>')
        meta_items.append('<span class="meta-pill">整图一次生成 · 无矩形拼接</span>')
        meta_items.append('<span class="meta-pill">每张原图返回 1 张结果</span>')
    else:
        meta_items.append(f'<span class="meta-pill">等比例放大，宽高都不小于 {get_feature_min_output_edge(feature)}px</span>')
    if supports_batch_multi_upload:
        meta_items.append(f'<span class="meta-pill">支持批量上传，最多 {BATCH_MULTI_IMAGE_MAX_FILES} 张</span>')
    if feature.get("key") == "hd_batch":
        meta_items.append('<span class="meta-pill">肤色肤质锁定 · 参考图仅用于清晰度</span>')
    if supports_outpaint:
        meta_items.append('<span class="meta-pill">支持上下左右独立扩展</span>')
    if max_output_images > 0 and not supports_outpaint:
        meta_items.append(f'<span class="meta-pill">默认输出 {max_output_images} 张结果图</span>')
    st.markdown(f'<div class="meta-row">{"".join(meta_items)}</div>', unsafe_allow_html=True)

    if supports_main_image_a_plus:
        workflow_steps = ("选择方式", "上传素材", "设置规格与要求", "开始生成", "查看结果")
    elif supports_outpaint:
        workflow_steps = ("上传原图", "框定扩图区域", "补充要求", "开始扩图", "对比结果")
    else:
        workflow_steps = ("上传图片", "补充参考", "填写要求", "开始处理", "查看结果")
    workflow_html = "".join(
        f'<div class="workflow-step"><span class="workflow-step-number">{index}</span><span>{label}</span></div>'
        for index, label in enumerate(workflow_steps, start=1)
    )
    st.markdown(f'<div class="workflow-strip">{workflow_html}</div>', unsafe_allow_html=True)

    submitted = False
    active_batch_concurrency = DEFAULT_BATCH_API_CONCURRENCY if supports_batch_multi_upload else 1

    left_col, right_col = st.columns([0.88, 1.12], gap="medium")
    with left_col:
        if supports_batch_multi_upload:
            st.markdown('<div class="batch-left-column-marker"></div>', unsafe_allow_html=True)
        left_panel_title = (
            "创作设置"
            if supports_main_image_a_plus
            else ("文字要求" if supports_jimeng_generation else "上传与设置")
        )
        st.markdown(
            f'<div class="result-block-title">{left_panel_title}</div>',
            unsafe_allow_html=True,
        )
        primary_action_slot = None
        if not supports_batch_multi_upload:
            primary_action_slot = st.empty()
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
        main_image_a_plus_prompt = ""
        main_image_a_plus_mode = MAIN_IMAGE_A_PLUS_MODE_FREE
        main_image_a_plus_template_file = None
        main_image_a_plus_layout_key = MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY
        main_image_a_plus_detected_elements: list[dict[str, Any]] = []
        main_image_a_plus_element_replacements: list[dict[str, Any]] = []
        main_image_a_plus_element_preview = ""
        main_image_a_plus_element_template_signature = ""
        main_image_a_plus_element_review_confirmed = False
        pose_reference_files: list[Any] = []
        scene_reference_files: list[Any] = []
        batch_source_files: list[Any] = []
        hd_skin_reference_file = None
        hd_skin_texture_reference_file: Path | None = None
        outpaint_top_px = OUTPAINT_DEFAULT_EXTENSION_PX
        outpaint_bottom_px = OUTPAINT_DEFAULT_EXTENSION_PX
        outpaint_left_px = OUTPAINT_DEFAULT_EXTENSION_PX
        outpaint_right_px = OUTPAINT_DEFAULT_EXTENSION_PX

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
            outpaint_top_key = f"outpaint_top_{feature['key']}"
            outpaint_bottom_key = f"outpaint_bottom_{feature['key']}"
            outpaint_left_key = f"outpaint_left_{feature['key']}"
            outpaint_right_key = f"outpaint_right_{feature['key']}"
            if supports_outpaint:
                outpaint_defaults_key = f"outpaint_defaults_{OUTPAINT_MAX_CANVAS_MULTIPLIER}x_{OUTPAINT_DEFAULT_EXTENSION_PX}_{feature['key']}"
                if not st.session_state.get(outpaint_defaults_key):
                    for state_key in (outpaint_top_key, outpaint_bottom_key, outpaint_left_key, outpaint_right_key):
                        st.session_state[state_key] = OUTPAINT_DEFAULT_EXTENSION_PX
                    st.session_state[outpaint_defaults_key] = True
                for state_key in (outpaint_top_key, outpaint_bottom_key, outpaint_left_key, outpaint_right_key):
                    if state_key not in st.session_state:
                        st.session_state[state_key] = OUTPAINT_DEFAULT_EXTENSION_PX
                    if state_key in st.session_state:
                        try:
                            current_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(st.session_state[state_key])))
                            st.session_state[state_key] = current_px
                        except Exception:
                            st.session_state[state_key] = OUTPAINT_DEFAULT_EXTENSION_PX
                outpaint_top_px = int(st.session_state.get(outpaint_top_key, OUTPAINT_DEFAULT_EXTENSION_PX))
                outpaint_bottom_px = int(st.session_state.get(outpaint_bottom_key, OUTPAINT_DEFAULT_EXTENSION_PX))
                outpaint_left_px = int(st.session_state.get(outpaint_left_key, OUTPAINT_DEFAULT_EXTENSION_PX))
                outpaint_right_px = int(st.session_state.get(outpaint_right_key, OUTPAINT_DEFAULT_EXTENSION_PX))

                def outpaint_preview_renderer(uploaded_input: Any, item_index: int, component_key: str) -> None:
                    render_outpaint_extension_preview_card(
                        uploaded_input,
                        outpaint_top_px,
                        outpaint_bottom_px,
                        outpaint_left_px,
                        outpaint_right_px,
                        f"{component_key}_{item_index}",
                        max_preview_edge=760,
                        drag_state_keys={
                            "top": outpaint_top_key,
                            "bottom": outpaint_bottom_key,
                            "left": outpaint_left_key,
                            "right": outpaint_right_key,
                        },
                    )
            else:
                outpaint_preview_renderer = None
            batch_source_files = render_multi_image_uploader(
                "上传原图",
                key=f"batch_uploader_{feature['key']}",
                help_text=f"可上传 JPG / PNG / WEBP。当前功能最多使用 {BATCH_MULTI_IMAGE_MAX_FILES} 张原图，系统会逐张处理并返回对应结果。",
                max_files=BATCH_MULTI_IMAGE_MAX_FILES,
                preview_renderer=outpaint_preview_renderer,
                preview_slot_count=1 if supports_outpaint else None,
            )
            if supports_outpaint:
                if batch_source_files:
                    try:
                        source_bytes = get_uploaded_file_bytes(batch_source_files[0])
                        source_signature = hashlib.sha1(source_bytes).hexdigest()[:16]
                        dynamic_defaults_key = f"outpaint_dynamic_defaults_source_{feature['key']}"
                        if st.session_state.get(dynamic_defaults_key) != source_signature:
                            direction_limits = get_outpaint_extension_limits(batch_source_files[0])
                            st.session_state[outpaint_top_key] = get_outpaint_default_extension(direction_limits["top"])
                            st.session_state[outpaint_bottom_key] = get_outpaint_default_extension(direction_limits["bottom"])
                            st.session_state[outpaint_left_key] = get_outpaint_default_extension(direction_limits["left"])
                            st.session_state[outpaint_right_key] = get_outpaint_default_extension(direction_limits["right"])
                            st.session_state[dynamic_defaults_key] = source_signature
                            st.rerun()
                        outpaint_top_px, outpaint_bottom_px, outpaint_left_px, outpaint_right_px = clamp_outpaint_extensions(
                            batch_source_files[0],
                            outpaint_top_px,
                            outpaint_bottom_px,
                            outpaint_left_px,
                            outpaint_right_px,
                        )
                        st.session_state[outpaint_top_key] = outpaint_top_px
                        st.session_state[outpaint_bottom_key] = outpaint_bottom_px
                        st.session_state[outpaint_left_key] = outpaint_left_px
                        st.session_state[outpaint_right_key] = outpaint_right_px
                    except Exception:
                        pass
                st.caption("上传后默认生成约 2 倍画布，四边拉满时最大为原图的 3 倍；每张原图返回 1 张整图结果，不进行矩形拼接。")
            if supports_skin_reference:
                st.markdown('<div class="skin-reference-grid-marker"></div>', unsafe_allow_html=True)
                skin_upload_col, skin_gallery_col = st.columns([1, 1], gap="small")
                with skin_upload_col:
                    st.markdown('<div class="panel-subtitle">肤质参考图（可选，1 张）</div>', unsafe_allow_html=True)
                    hd_skin_reference_file = render_single_image_uploader(
                        "上传肤质参考图",
                        key=f"hd_skin_reference_{feature['key']}",
                        help_text="不上传时默认使用 outputs/reference/参考1.png；上传后所有主图都会使用这张新参考图。",
                    )
                with skin_gallery_col:
                    st.markdown('<div class="panel-subtitle">肌肤质感参考图库（单选）</div>', unsafe_allow_html=True)
                    if skin_texture_reference_files:
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
                                st.caption(f"当前图库参考图：{hd_skin_texture_reference_file.name}。优先级高于手动上传。")
                                render_zoomable_image_gallery(
                                    [uploaded_input_to_data_url(hd_skin_texture_reference_file)],
                                    columns=1,
                                    thumb_height=120,
                                    component_key=f"hd_skin_texture_gallery_preview_{feature['key']}",
                                    fit_mode="cover",
                                    max_width_percent=58,
                                )
                    else:
                        st.caption("未找到 `肌肤质感参考` 文件夹中的可用图片，将继续使用上传参考图或默认参考图。")
                st.markdown('<div class="skin-reference-grid-end"></div>', unsafe_allow_html=True)
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
        elif supports_main_image_a_plus:
            st.markdown(
                '<div class="a-plus-mode-selector-marker"></div>'
                '<div class="panel-subtitle">生成方式</div>',
                unsafe_allow_html=True,
            )
            main_image_a_plus_mode = st.radio(
                "选择主图生A+生成方式",
                options=list(MAIN_IMAGE_A_PLUS_MODE_LABELS),
                index=0,
                format_func=lambda value: MAIN_IMAGE_A_PLUS_MODE_LABELS[value],
                key=f"main_image_a_plus_mode_{feature['key']}",
                horizontal=True,
                label_visibility="collapsed",
            )
            uses_finished_a_plus_template = (
                main_image_a_plus_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
            )
            if uses_finished_a_plus_template:
                with st.container(border=True):
                    st.markdown(
                        '<div class="a-plus-template-card-marker"></div>'
                        '<div class="panel-subtitle">成品 A+ 版式模板（1 张）</div>',
                        unsafe_allow_html=True,
                    )
                    main_image_a_plus_template_file = render_single_image_uploader(
                        "上传成品A+版式模板",
                        key=f"main_image_a_plus_template_{feature['key']}",
                        help_text=(
                            "上传完整成品 A+ 示例图。指定元素替换只修改你为编号上传了新素材的元素，"
                            "其余内容、背景和版式保持不变。"
                            if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
                            else (
                                "上传要套用版式的完整成品 A+。模板只保留布局、色彩和视觉层级，"
                                "原品牌、原文案、原模特和原产品都会被替换或删除。"
                                + (
                                    "一张测试会把完整模板作为一个整体，只保留纯背景和版式，其他内容全部替换；只生成一张成品，不拆分、不拼接。"
                                    if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST
                                    else ""
                                )
                            )
                        ),
                    )
                    st.markdown(
                        (
                            '<div class="slot-helper">上传模板后先识别元素；图中编号与下方上传框一一对应，只替换已上传的编号</div>'
                            if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
                            else (
                                '<div class="slot-helper">整张模板一次重绘：只保留背景与版式，产品、品牌、模特和其他内容全部替换；不拆四段、不拼接</div>'
                                if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST
                                else '<div class="slot-helper">套版结果自动跟随模板原图尺寸，无需另外选择规格</div>'
                            )
                        ),
                        unsafe_allow_html=True,
                    )
            if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
                if main_image_a_plus_template_file is None:
                    with st.container(border=True):
                        st.markdown(
                            '<div class="a-plus-analysis-card-marker"></div>'
                            '<div class="panel-subtitle">识别并标注可替换元素</div>',
                            unsafe_allow_html=True,
                        )
                        st.button(
                            "识别可替换元素",
                            key=f"analyze_main_image_a_plus_elements_{feature['key']}_empty",
                            use_container_width=True,
                            type="secondary",
                            disabled=True,
                        )
                        st.info("请先上传完整 A+ 示例图，上传后按钮会在原位置启用。")
                else:
                    template_signature = get_main_image_a_plus_template_signature(
                        main_image_a_plus_template_file
                    )
                    analysis_state_key = f"main_image_a_plus_element_analysis_{feature['key']}"
                    analysis_state = dict(st.session_state.get(analysis_state_key) or {})
                    analysis_matches_template = (
                        str(analysis_state.get("template_signature") or "") == template_signature
                    )
                    analyze_elements_clicked = False
                    with st.container(border=True):
                        st.markdown(
                            '<div class="a-plus-analysis-card-marker"></div>'
                            '<div class="panel-subtitle">识别并标注可替换元素</div>',
                            unsafe_allow_html=True,
                        )
                        analyze_elements_clicked = st.button(
                            "重新识别可替换元素"
                            if analysis_matches_template
                            else "识别可替换元素",
                            key=f"analyze_main_image_a_plus_elements_{feature['key']}_{template_signature}",
                            use_container_width=True,
                            type="secondary",
                        )
                        if analysis_matches_template:
                            analysis_error = str(analysis_state.get("error") or "").strip()
                            if analysis_error:
                                st.error(f"元素识别失败：{analysis_error}")
                            else:
                                detected_count = len(
                                    [
                                        item
                                        for item in list(analysis_state.get("elements") or [])
                                        if isinstance(item, dict)
                                    ]
                                )
                                st.success(f"已识别 {detected_count} 个元素组，可继续校对或重新识别。")
                        else:
                            st.info("模板已就绪，点击后会识别产品、品牌、模特、文案和细节元素。")
                    if analyze_elements_clicked:
                        with st.spinner("正在分析整张 A+ 的产品、品牌、模特、文案和细节元素…"):
                            try:
                                detected_elements = analyze_main_image_a_plus_elements(
                                    main_image_a_plus_template_file
                                )
                                st.session_state[analysis_state_key] = {
                                    "template_signature": template_signature,
                                    "elements": detected_elements,
                                    "error": "",
                                }
                            except Exception as exc:
                                st.session_state[analysis_state_key] = {
                                    "template_signature": template_signature,
                                    "elements": [],
                                    "error": format_user_facing_error_message(exc),
                                }
                        st.rerun()
                    if analysis_matches_template:
                        main_image_a_plus_detected_elements = [
                            dict(item)
                            for item in list(analysis_state.get("elements") or [])
                            if isinstance(item, dict)
                        ]
                    if main_image_a_plus_detected_elements:
                        manual_job_state_key = (
                            f"main_image_a_plus_manual_job_{feature['key']}_{template_signature}"
                        )
                        manual_job_state = sync_main_image_a_plus_manual_element_job(
                            manual_job_state_key,
                            analysis_state_key,
                            template_signature,
                        )
                        manual_job_status = str(
                            manual_job_state.get("status") or ""
                        ).lower()
                        if manual_job_status == "completed":
                            completed_element = dict(
                                manual_job_state.get("new_element") or {}
                            )
                            if completed_element:
                                refreshed_analysis_state = dict(
                                    st.session_state.get(analysis_state_key) or {}
                                )
                                main_image_a_plus_detected_elements = [
                                    dict(item)
                                    for item in list(
                                        refreshed_analysis_state.get("elements") or []
                                    )
                                    if isinstance(item, dict)
                                ]
                                st.success(
                                    f"已补充 #{int(completed_element.get('id') or 0)} "
                                    f"{str(completed_element.get('name') or '新元素')}。"
                                )
                        elif manual_job_status == "error":
                            st.error(
                                "点击补漏失败："
                                f"{str(manual_job_state.get('error') or '请重新点击元素主体。')}"
                            )
                        manual_point = consume_main_image_a_plus_manual_point(template_signature)
                        if manual_point is not None:
                            existing_element = find_main_image_a_plus_element_at_point(
                                main_image_a_plus_detected_elements,
                                manual_point,
                            )
                            if existing_element is not None:
                                st.info(
                                    f"点击位置已经属于 #{int(existing_element.get('id') or 0)} "
                                    f"{str(existing_element.get('name') or '元素')}，无需重复添加。"
                                )
                            else:
                                manual_job_state = submit_main_image_a_plus_manual_element_job(
                                    manual_job_state_key,
                                    main_image_a_plus_template_file,
                                    template_signature,
                                    manual_point,
                                    main_image_a_plus_detected_elements,
                                )
                                manual_job_status = str(
                                    manual_job_state.get("status") or ""
                                ).lower()
                        if manual_job_status == "running":
                            render_main_image_a_plus_manual_element_job_status(
                                manual_job_state_key,
                                analysis_state_key,
                                template_signature,
                            )
                        main_image_a_plus_element_preview = build_main_image_a_plus_element_preview(
                            main_image_a_plus_template_file,
                            main_image_a_plus_detected_elements,
                        )
                        main_image_a_plus_element_template_signature = template_signature
                        st.caption(
                            f"已识别 {len(main_image_a_plus_detected_elements)} 个元素组。右侧可查看完整编号图，也可以切换到“手动补漏”点击漏掉的内容。"
                        )
                        auto_material_key = (
                            f"main_image_a_plus_auto_materials_{feature['key']}_{template_signature}"
                        )
                        auto_material_files = load_upload_cache(
                            auto_material_key,
                            max_files=MAIN_IMAGE_A_PLUS_MAX_FILES,
                        )
                        auto_match_state_key = (
                            f"main_image_a_plus_auto_matches_{feature['key']}_{template_signature}"
                        )
                        review_state_key = (
                            f"main_image_a_plus_element_review_{feature['key']}_{template_signature}"
                        )
                        auto_match_state = dict(st.session_state.get(auto_match_state_key) or {})
                        auto_matches_by_element: dict[int, dict[str, Any]] = {}
                        auto_match_error = ""
                        auto_match_applied_count: int | None = None
                        auto_match_skipped_count = 0
                        auto_match_uncropped_count = 0
                        if (
                            str(auto_match_state.get("template_signature") or "")
                            == template_signature
                        ):
                            auto_matches_by_element = {
                                int(item.get("element_id") or 0): dict(item)
                                for item in list(auto_match_state.get("matches") or [])
                                if isinstance(item, dict) and int(item.get("element_id") or 0) > 0
                            }
                            auto_match_error = str(auto_match_state.get("error") or "").strip()
                            if "applied_count" in auto_match_state:
                                auto_match_applied_count = int(
                                    auto_match_state.get("applied_count") or 0
                                )
                                auto_match_skipped_count = int(
                                    auto_match_state.get("skipped_count") or 0
                                )
                                auto_match_uncropped_count = int(
                                    auto_match_state.get("uncropped_count") or 0
                                )
                        auto_match_clicked = False
                        with st.container(border=True):
                            st.markdown(
                                '<div class="a-plus-auto-fill-card-marker"></div>'
                                '<div class="panel-subtitle">AI 自动识别并填充替换素材</div>',
                                unsafe_allow_html=True,
                            )
                            auto_match_clicked = st.button(
                                "AI 识别素材并自动填充",
                                key=f"auto_match_main_image_a_plus_{feature['key']}_{template_signature}",
                                use_container_width=True,
                                type="secondary",
                                disabled=not auto_material_files,
                            )
                            if auto_match_error:
                                st.error(f"自动填充失败：{auto_match_error}")
                            elif auto_match_applied_count is not None:
                                st.success(
                                    f"AI 已裁切并填充 {auto_match_applied_count} 个编号；"
                                    f"已有人工素材的 {auto_match_skipped_count} 个编号未覆盖；"
                                    f"未能准确裁出的 {auto_match_uncropped_count} 个编号未自动填充。"
                                )
                            elif auto_material_files:
                                st.caption("素材已就绪，上方按钮可开始自动匹配。")
                            else:
                                st.caption("先在下方上传素材，按钮会在原位置自动启用。")
                            auto_material_files = render_multi_image_uploader(
                                "批量上传替换素材",
                                key=auto_material_key,
                                help_text=(
                                    "可混合上传产品、包装、模特、Logo、文案和细节图。"
                                    "AI 会识别每张图里的内容，并自动放入最合适的编号卡片。"
                                ),
                                max_files=MAIN_IMAGE_A_PLUS_MAX_FILES,
                                preview_slot_count=5,
                            )
                        if auto_match_clicked:
                            with st.spinner("正在识别每张素材并匹配产品、模特、品牌、文案和细节编号…"):
                                try:
                                    auto_matches = analyze_main_image_a_plus_replacement_matches(
                                        main_image_a_plus_template_file,
                                        main_image_a_plus_detected_elements,
                                        auto_material_files,
                                    )
                                    applied_matches: list[dict[str, Any]] = []
                                    skipped_matches: list[dict[str, Any]] = []
                                    uncropped_matches: list[dict[str, Any]] = []
                                    processed_matches: list[dict[str, Any]] = []
                                    for auto_match in auto_matches:
                                        processed_match = dict(auto_match)
                                        matched_element_id = int(auto_match.get("element_id") or 0)
                                        matched_image_index = int(auto_match.get("image_index") or 0)
                                        matched_element = next(
                                            (
                                                item
                                                for item in main_image_a_plus_detected_elements
                                                if int(item.get("id") or 0) == matched_element_id
                                            ),
                                            {},
                                        )
                                        matched_upload_key = (
                                            f"main_image_a_plus_element_{feature['key']}_"
                                            f"{template_signature}_{matched_element_id}"
                                        )
                                        existing_replacement_files = load_upload_cache(
                                            matched_upload_key,
                                            max_files=1,
                                        )
                                        previous_auto_match = auto_matches_by_element.get(
                                            matched_element_id
                                        )
                                        existing_replacement_name = (
                                            get_uploaded_file_name(existing_replacement_files[0])
                                            if existing_replacement_files
                                            else ""
                                        )
                                        previous_auto_names = set()
                                        if previous_auto_match is not None:
                                            previous_cropped_name = str(
                                                previous_auto_match.get("cropped_reference_name") or ""
                                            ).strip()
                                            if previous_cropped_name:
                                                previous_auto_names.add(previous_cropped_name)
                                            previous_image_index = int(
                                                previous_auto_match.get("image_index") or 0
                                            )
                                            if 1 <= previous_image_index <= len(auto_material_files):
                                                previous_auto_names.add(
                                                    get_uploaded_file_name(
                                                        auto_material_files[previous_image_index - 1]
                                                    )
                                                )
                                        existing_is_previous_auto_fill = bool(
                                            existing_replacement_name
                                            and existing_replacement_name in previous_auto_names
                                        )
                                        if (
                                            existing_replacement_files
                                            and not existing_is_previous_auto_fill
                                        ):
                                            processed_match["crop_status"] = "manual_preserved"
                                            skipped_matches.append(processed_match)
                                            processed_matches.append(processed_match)
                                            continue
                                        if 1 <= matched_image_index <= len(auto_material_files):
                                            cropped_replacement = crop_main_image_a_plus_replacement_input(
                                                auto_material_files[matched_image_index - 1],
                                                auto_match.get("crop_box"),
                                                matched_element_id,
                                                str(
                                                    matched_element.get("name")
                                                    or auto_match.get("detected_content")
                                                    or f"元素_{matched_element_id}"
                                                ),
                                            )
                                            if cropped_replacement is None:
                                                processed_match["crop_status"] = "not_located"
                                                uncropped_matches.append(processed_match)
                                                processed_matches.append(processed_match)
                                                continue
                                            save_upload_cache(
                                                matched_upload_key,
                                                [cropped_replacement],
                                            )
                                            processed_match["crop_status"] = "applied"
                                            processed_match["cropped_reference_name"] = str(
                                                cropped_replacement.get("name") or ""
                                            )
                                            applied_matches.append(processed_match)
                                            processed_matches.append(processed_match)
                                    st.session_state[auto_match_state_key] = {
                                        "template_signature": template_signature,
                                        "matches": processed_matches,
                                        "applied_count": len(applied_matches),
                                        "skipped_count": len(skipped_matches),
                                        "uncropped_count": len(uncropped_matches),
                                        "material_count": len(auto_material_files),
                                    }
                                    st.session_state[review_state_key] = False
                                except Exception as exc:
                                    st.session_state[auto_match_state_key] = {
                                        "template_signature": template_signature,
                                        "matches": [],
                                        "error": format_user_facing_error_message(exc),
                                    }
                            st.rerun()
                        st.markdown('<div class="panel-subtitle">按编号校对替换元素</div>', unsafe_allow_html=True)
                        st.markdown(
                            '<div class="slot-helper">逐项检查 AI 填充结果；可以更换、移除或为未匹配编号手动上传，留空编号保持原样</div>',
                            unsafe_allow_html=True,
                        )
                        element_columns = st.columns(2, gap="small")
                        for element_index, element in enumerate(main_image_a_plus_detected_elements):
                            element_id = int(element.get("id") or 0)
                            element_name = str(element.get("name") or f"元素 {element_id}")
                            replacement_hint = str(
                                element.get("replacement_hint")
                                or element.get("description")
                                or "上传包含该元素的新图片"
                            )
                            region_count = len(list(element.get("regions") or []))
                            element_upload_key = (
                                f"main_image_a_plus_element_{feature['key']}_{template_signature}_{element_id}"
                            )
                            has_uploaded_replacement = bool(
                                load_upload_cache(element_upload_key, max_files=1)
                            )
                            auto_match = auto_matches_by_element.get(element_id)
                            if has_uploaded_replacement and auto_match is not None:
                                confidence_percent = round(
                                    float(auto_match.get("confidence") or 0) * 100
                                )
                                status_text = f" · AI 裁切 {confidence_percent}%"
                            elif (
                                auto_match is not None
                                and str(auto_match.get("crop_status") or "") == "not_located"
                            ):
                                status_text = " · 待手动裁切"
                            else:
                                status_text = " · 已上传" if has_uploaded_replacement else ""
                            with element_columns[element_index % 2]:
                                with st.expander(
                                    f"#{element_id} {element_name} · {region_count} 处{status_text}",
                                    expanded=has_uploaded_replacement,
                                ):
                                    st.caption(f"{replacement_hint}。留空则保持原元素不变。")
                                    if auto_match is not None:
                                        auto_reason = str(auto_match.get("reason") or "").strip()
                                        auto_content = str(
                                            auto_match.get("detected_content") or ""
                                        ).strip()
                                        if str(auto_match.get("crop_status") or "") == "not_located":
                                            st.caption("未能定位出独立元素，已阻止整图自动填充，请手动上传裁切素材。")
                                        if auto_reason or auto_content:
                                            st.caption(
                                                "AI 判断："
                                                + "；".join(
                                                    text
                                                    for text in (auto_content, auto_reason)
                                                    if text
                                                )
                                            )
                                    replacement_file = render_compact_element_image_uploader(
                                        f"上传 #{element_id} {element_name}",
                                        key=element_upload_key,
                                        help_text=f"只用于替换模板编号 #{element_id} 的“{element_name}”，不会用于其他编号。",
                                    )
                                    if replacement_file is not None:
                                        amazon_source_files.append(replacement_file)
                                        replacement_mapping = dict(element)
                                        replacement_mapping["reference_name"] = get_uploaded_file_name(
                                            replacement_file
                                        )
                                        main_image_a_plus_element_replacements.append(
                                            replacement_mapping
                                        )
                        st.info(
                            f"当前已选择 {len(main_image_a_plus_element_replacements)} / {len(main_image_a_plus_detected_elements)} 个元素进行替换。"
                        )
                        main_image_a_plus_element_review_confirmed = st.checkbox(
                            "我已逐项校对编号、替换素材和未识别元素，可以开始替换",
                            key=review_state_key,
                            help="勾选后才会启用生成按钮；AI 自动填充不会直接开始生成。",
                        )
            else:
                st.markdown(
                    (
                        f'<div class="panel-subtitle">替换内容参考图（最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张）</div>'
                        if uses_finished_a_plus_template
                        else f'<div class="panel-subtitle">商品主图（最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张）</div>'
                    ),
                    unsafe_allow_html=True,
                )
                amazon_source_files = render_multi_image_uploader(
                    (
                        "上传要替换进去的内容参考图"
                        if uses_finished_a_plus_template
                        else "上传商品主图"
                    ),
                    key=f"main_image_a_plus_uploader_{feature['key']}",
                    help_text=(
                        (
                            "可上传包含新文案、品牌、Logo、模特、产品、包装、细节和参数的 JPG / PNG / WEBP。"
                            "第 1 张作为核心商品与品牌依据，其余图片由 AI 自动匹配到模板对应位置，"
                            f"最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张。"
                        )
                        if uses_finished_a_plus_template
                        else (
                            "可上传 JPG / PNG / WEBP。第 1 张作为核心商品主图，其余图片用于补充角度、细节、"
                            f"套装内容和使用场景，最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张。"
                        )
                    ),
                    max_files=MAIN_IMAGE_A_PLUS_MAX_FILES,
                )
                st.markdown(
                    (
                        '<div class="slot-helper">请把最能代表新商品与品牌的图片放在第一张；其余文案、模特、产品细节图可继续上传</div>'
                        if uses_finished_a_plus_template
                        else '<div class="slot-helper">请把最能代表商品的图片第一个上传；图片顺序即参考优先级</div>'
                    ),
                    unsafe_allow_html=True,
                )
            if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_FREE:
                st.markdown('<div class="panel-subtitle">选择成品规格</div>', unsafe_allow_html=True)
                layout_keys = list(MAIN_IMAGE_A_PLUS_LAYOUTS)
                main_image_a_plus_layout_key = st.selectbox(
                    "选择主图生A+规格",
                    options=layout_keys,
                    index=layout_keys.index(MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY),
                    format_func=lambda value: str(MAIN_IMAGE_A_PLUS_LAYOUTS[value]["label"]),
                    key=f"main_image_a_plus_layout_{feature['key']}",
                    label_visibility="collapsed",
                )
                selected_a_plus_layout = get_main_image_a_plus_layout(main_image_a_plus_layout_key)
                selected_width, selected_height = selected_a_plus_layout["target_size"]
                st.info(
                    f"{selected_width}×{selected_height}px · 整张一次生成 · 不拆段、不拼接 · "
                    "上下左右四边完整保留 · 单一模特置于首屏最上方 · 完整文字与可读 Logo 不截断。"
                )
            st.markdown('<div class="panel-subtitle">补充宣传要求（可选）</div>', unsafe_allow_html=True)
            main_image_a_plus_prompt = st.text_area(
                "输入主图生A+补充要求",
                key=f"main_image_a_plus_prompt_{feature['key']}",
                placeholder="例如：突出轻盈、自然和佩戴舒适；整体使用黑金高级风格。请只填写真实、可核实的卖点。",
                height=110,
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

        process_button_label = (
            "开始生成 A+"
            if supports_main_image_a_plus
            else ("开始扩图" if supports_outpaint else "开始处理")
        )
        is_job_running = str(job_info.get("status") or "").strip().lower() == "running"
        is_element_review_pending = bool(
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and not main_image_a_plus_element_review_confirmed
        )
        process_button_disabled = is_job_running or is_element_review_pending
        if primary_action_slot is None:
            action_container = st.container(border=True)
        else:
            with primary_action_slot:
                action_container = st.container(border=True)
        with action_container:
            st.markdown(
                '<div class="main-action-dock-marker"></div>'
                '<div class="inline-action-row"></div>',
                unsafe_allow_html=True,
            )
            if supports_jimeng_generation:
                st.caption("当前模型：Agent")
                submitted = st.button(
                    process_button_label,
                    key=f"process_{feature['key']}",
                    type="primary",
                    use_container_width=True,
                    disabled=process_button_disabled,
                )
            elif len(model_options_for_feature) == 1:
                active_model = model_options_for_feature[0]
                st.markdown(
                    '<div class="fixed-model-card"><span>当前模型</span>'
                    f'<strong>{html.escape(get_model_display_name(active_model))}</strong></div>',
                    unsafe_allow_html=True,
                )
                submitted = st.button(
                    process_button_label,
                    key=f"process_{feature['key']}",
                    type="primary",
                    use_container_width=True,
                    disabled=process_button_disabled,
                )
            else:
                selector_col, process_col = st.columns([1.35, 0.95], gap="small")
                with selector_col:
                    active_model = st.selectbox(
                        "模型切换",
                        model_options_for_feature,
                        index=model_options_for_feature.index(default_model_for_feature),
                        format_func=get_model_display_name,
                        key=f"model_select_{feature['key']}",
                    )
                with process_col:
                    st.markdown('<div class="panel-subtitle">&nbsp;</div>', unsafe_allow_html=True)
                    submitted = st.button(
                        process_button_label,
                        key=f"process_{feature['key']}",
                        type="primary",
                        use_container_width=True,
                        disabled=process_button_disabled,
                    )
            if feature.get("key") == "hd_batch":
                st.caption("当前使用 Nano Banana 2 原生 4K；保留肤质参考图，但只参考清晰度，肤色和肤质以原图为准且不得修改。")
            elif supports_main_image_a_plus:
                st.caption("主图生A+使用 Nano Banana 2 原生 4K Images API；画面满版，文字使用安全区避免被截断。")
            elif supports_amazon_a_plus:
                st.caption("A+ 使用原生 4K Images API 生成高清绿幕底稿。")
    with right_col:
        if supports_batch_multi_upload:
            st.markdown('<div class="batch-right-column-marker"></div>', unsafe_allow_html=True)
        shows_element_map = bool(
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and main_image_a_plus_element_preview
        )
        right_panel_title = "元素标注与生成结果" if shows_element_map else "结果图预览"
        st.markdown(
            f'<div class="result-block-title">{right_panel_title}</div>',
            unsafe_allow_html=True,
        )
        result_images = list(result.get("images") or [])
        result_download_images = build_result_download_sources(
            result_images,
            list(result.get("history_records") or []),
        )
        source_images = list(result.get("source_images") or [])
        outpaint_alignments = list(result.get("outpaint_alignments") or [])
        if not source_images and supports_batch_multi_upload and batch_source_files:
            fallback_sources = list(batch_source_files)
            if supports_outpaint:
                fallback_sources = [
                    source_file
                    for source_file in batch_source_files
                    for _ in range(OUTPAINT_RESULTS_PER_SOURCE)
                ]
            for source_file in fallback_sources[: len(result_images)]:
                try:
                    source_images.append(uploaded_input_to_data_url(source_file))
                except Exception:
                    source_images.append("")
        result_captions = list(result.get("captions") or [])
        result_view_container = st.container()
        if shows_element_map:
            element_map_tab, manual_picker_tab, result_view_container = st.tabs(
                ["元素标注图", "手动补漏", "生成结果"]
            )
            with element_map_tab:
                render_zoomable_image_gallery(
                    [main_image_a_plus_element_preview],
                    columns=1,
                    thumb_height=760,
                    component_key=(
                        "main_image_a_plus_element_map_"
                        f"{main_image_a_plus_element_template_signature}"
                    ),
                    fit_mode="contain",
                    max_width_percent=100,
                    compress_preview=True,
                    include_full_src=True,
                )
                st.caption(
                    "点击标注图可全屏放大查看；右侧编号对应左侧同号上传卡片，同号多个区域共用一份替换素材。"
                )
            with manual_picker_tab:
                render_main_image_a_plus_manual_element_picker(
                    main_image_a_plus_element_preview,
                    main_image_a_plus_element_template_signature,
                    component_key=(
                        "main_image_a_plus_manual_picker_"
                        f"{main_image_a_plus_element_template_signature}"
                    ),
                )
        with result_view_container:
            if supports_amazon_a_plus and result_images:
                layered_tab, green_tab = st.tabs(["分层结果", "AI 绿幕底稿"])
                with layered_tab:
                    render_result_preview(
                        result_images,
                        show_title=False,
                        download_images=result_download_images,
                    )
                with green_tab:
                    green_screen_images = list(result.get("green_screen_images") or [])
                    if green_screen_images:
                        render_zoomable_image_gallery(
                            green_screen_images,
                            columns=1,
                            thumb_height=None,
                            component_key="amazon_a_plus_green_screen_viewer",
                            fit_mode="contain",
                            max_width_percent=50,
                            compress_preview=True,
                            include_full_src=True,
                        )
                    else:
                        st.info("当前结果没有保留绿幕底稿。")
                psd_bytes = result.get("psd_bytes")
                if isinstance(psd_bytes, (bytes, bytearray)) and psd_bytes:
                    layer_count = int(result.get("layer_count") or 0)
                    st.caption(f"已生成 {layer_count} 个可编辑图层，画布与输入规格一致。")
                    st.download_button(
                        "下载分层 PSD",
                        data=bytes(psd_bytes),
                        file_name=str(result.get("psd_file_name") or "amazon_a_plus.psd"),
                        mime="image/vnd.adobe.photoshop",
                        key=f"download_amazon_psd_{result.get('psd_file_name') or 'latest'}",
                        icon=":material/download:",
                        use_container_width=True,
                    )
            elif supports_batch_multi_upload and result_images and source_images:
                render_before_after_compare_gallery(
                    source_images,
                    result_images,
                    result_captions,
                    feature["key"],
                    outpaint_alignments=outpaint_alignments if supports_outpaint else None,
                    download_images=result_download_images,
                )
            elif supports_batch_multi_upload and result_images and result_captions:
                render_result_preview_with_captions(
                    result_images,
                    result_captions,
                    feature["key"],
                    download_images=result_download_images,
                )
            else:
                render_result_preview(
                    result_images,
                    show_title=False,
                    download_images=result_download_images,
                )

    if job_info.get("status") == "completed":
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
        psd_storage_error = str(result.get("psd_storage_error") or "").strip()
        if psd_storage_error:
            st.warning(psd_storage_error)

    if submitted:
        if job_info.get("status") == "running":
            st.warning("当前功能已有任务在后台处理中，请等待完成后再发起新的任务。")
            st.markdown("</div>", unsafe_allow_html=True)
            return
        if supports_batch_multi_upload:
            files = list(batch_source_files)
        elif supports_ai_qa_image:
            files = list(ai_qa_source_files)
        elif supports_a_plus_images_api:
            files = list(amazon_source_files)
        elif supports_jimeng_generation:
            files = list(jimeng_source_files)
        else:
            files = [uploaded_file] if uploaded_file is not None else []
        custom_prompt = (
            jimeng_prompt
            if supports_jimeng_generation
            else ai_qa_prompt
            if supports_ai_qa_image
            else main_image_a_plus_prompt
            if supports_main_image_a_plus
            else ""
        )
        main_image_a_plus_template_layout_error = ""
        if (
            supports_main_image_a_plus
            and main_image_a_plus_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
            and main_image_a_plus_template_file is not None
        ):
            try:
                selected_main_image_a_plus_layout = get_main_image_a_plus_template_layout(
                    main_image_a_plus_template_file
                )
            except RuntimeError as exc:
                selected_main_image_a_plus_layout = None
                main_image_a_plus_template_layout_error = str(exc)
        else:
            selected_main_image_a_plus_layout = get_main_image_a_plus_layout(main_image_a_plus_layout_key)
        target_size = (
            selected_main_image_a_plus_layout["target_size"]
            if supports_main_image_a_plus and selected_main_image_a_plus_layout is not None
            else parse_size_text(amazon_size_text)
            if supports_amazon_a_plus
            else None
        )
        using_jimeng_for_request = supports_jimeng_generation or is_jimeng_model(active_model)
        if supports_jimeng_generation and not jimeng_prompt.strip():
            st.warning("请输入 Agent 的生图要求。")
        elif feature["key"] == "hd_batch" and is_jimeng_model(active_model):
            st.warning("即梦 4.6 高清已暂时关闭，请先使用 Nano Banana 2 生图。")
        elif using_jimeng_for_request and len(files) > JIMENG_MAX_INPUT_IMAGES and not supports_batch_multi_upload:
            st.warning(f"Agent 最多只能上传 {JIMENG_MAX_INPUT_IMAGES} 张图片。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and main_image_a_plus_template_file is None
        ):
            st.warning("指定元素替换需要先上传 1 张完整的成品 A+ 示例图。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and not main_image_a_plus_detected_elements
        ):
            st.warning("请先点击“识别可替换元素”，确认编号后再上传对应替换图。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and not main_image_a_plus_element_replacements
        ):
            st.warning("请至少为 1 个编号上传对应的替换元素图片。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and not main_image_a_plus_element_review_confirmed
        ):
            st.warning("请先逐项校对自动填充结果，并勾选确认后再开始替换。")
        elif len(files) < min_images:
            st.warning(f"当前功能至少需要上传 {min_images} 张参考图。")
        elif supports_ai_qa_image and len(files) > 3:
            st.warning("AI问答生图功能最多只能上传 3 张参考图。")
        elif supports_ai_qa_image and not ai_qa_prompt.strip():
            st.warning("请输入你的文字要求。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
            and main_image_a_plus_template_file is None
        ):
            st.warning(
                "指定元素替换需要先上传 1 张完整的成品 A+ 示例图。"
                if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
                else (
                    "一张测试需要先上传 1 张完整的成品 A+ 版式模板。"
                    if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST
                    else "套版替换需要先上传 1 张完整的成品 A+ 版式模板。"
                )
            )
        elif supports_main_image_a_plus and main_image_a_plus_template_layout_error:
            st.warning(main_image_a_plus_template_layout_error)
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and len(files) > MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS
        ):
            st.warning(f"指定元素替换最多支持 {MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS} 个上传元素组。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode != MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and len(files) > MAIN_IMAGE_A_PLUS_MAX_FILES
        ):
            st.warning(f"主图生A+最多只能上传 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张主图。")
        elif supports_amazon_a_plus and len(files) > 3:
            st.warning("亚马逊A+功能最多只能上传 3 张原图。")
        elif supports_amazon_a_plus and target_size is None:
            st.warning("请输入正确的规格参数，例如 1464*600；最长边不超过 10000px，画布不超过 4000 万像素。")
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
            display_source_groups: list[list[Any]] = []
            st.session_state.feature_results.pop(feature["key"], None)
            if feature["key"] == "hd_batch":
                extra_notes = (
                    PORTRAIT_HD_SKIN_LOCK_RULES
                    + "第1张图必须作为唯一主体，不允许改变人物身份、五官比例、脸型、表情、发型和构图。"
                    "如果存在第2张图，第2张图仍作为高清参考图，但只用于参考清晰度、分辨率和细节解析水平。"
                    "严禁从第2张图借用或迁移肤色、肤质、毛孔状态、皮肤光泽、颗粒感、斑点、妆容、脸型、五官、眼睛、表情、发型、服饰、背景或人物身份。"
                    "批量时上传几张主图，就只返回几张高清结果图；每张主图只允许对应1张结果图。"
                )
            elif supports_outpaint:
                display_source_groups = [[item] for item in files]
                extra_notes = build_outpaint_extra_notes(
                    outpaint_top_px,
                    outpaint_bottom_px,
                    outpaint_left_px,
                    outpaint_right_px,
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
            elif supports_main_image_a_plus:
                if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
                    extra_notes = build_main_image_a_plus_element_replacement_notes(
                        selected_main_image_a_plus_layout,
                        len(main_image_a_plus_detected_elements),
                        main_image_a_plus_element_replacements,
                    )
                elif main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST:
                    extra_notes = build_main_image_a_plus_single_test_notes(
                        selected_main_image_a_plus_layout,
                        len(files),
                    )
                elif main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE:
                    extra_notes = build_main_image_a_plus_template_notes(
                        selected_main_image_a_plus_layout,
                        len(files),
                    )
                else:
                    extra_notes = build_main_image_a_plus_layout_notes(
                        main_image_a_plus_layout_key,
                        len(files),
                    )
            elif supports_amazon_a_plus:
                target_width, target_height = target_size
                extra_notes = (
                    f"当前共上传 {len(files)} 张原图。"
                    "请将原图中的主体内容设计成适合亚马逊 A+ 模块的独立视觉元素底稿。"
                    "每个商品、文字块、图标、徽章和装饰元素必须完整且彼此分离，不能接触、交叠或通过阴影相连。"
                    "元素之间至少保留 32px 纯 #00FF00 间距；除独立元素外，整张画布只能出现纯 #00FF00。"
                    "不要生成底板、分栏线、大面积背景、场景地面或跨元素装饰。"
                    "元素位置要体现清晰、商业化的 A+ 信息层级，但不要替换上传主体，也不要生成无关商品。"
                    "必须使用原生 4K 高清细节，商品纹理、睫毛丝、眼部细节、人物五官和文字边缘必须清晰锐利。"
                    "禁止模糊、虚焦、低分辨率、涂抹、过度柔化、像素化和压缩痕迹。"
                    f"绿幕底稿画布尺寸必须严格等于 {target_width}*{target_height}px。"
                    "仅输出 1 张绿幕元素底稿，不要输出成品背景图、透明图、草图或分步骤图。"
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
            feature_for_request = dict(feature)
            if supports_main_image_a_plus:
                feature_for_request["main_image_a_plus_mode"] = main_image_a_plus_mode
                feature_for_request["main_image_a_plus_layout_key"] = main_image_a_plus_layout_key
                feature_for_request["main_image_a_plus_layout"] = selected_main_image_a_plus_layout
                if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
                    feature_for_request["default_prompt"] = MAIN_IMAGE_A_PLUS_ELEMENT_DEFAULT_PROMPT
                elif main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST:
                    feature_for_request["default_prompt"] = MAIN_IMAGE_A_PLUS_SINGLE_TEST_DEFAULT_PROMPT
                elif main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE:
                    feature_for_request["default_prompt"] = MAIN_IMAGE_A_PLUS_TEMPLATE_DEFAULT_PROMPT
            if target_size is not None:
                feature_for_request["target_size"] = tuple(target_size)
                feature_for_request["target_size_text"] = f"{int(target_size[0])}*{int(target_size[1])}"
            if using_jimeng_for_request:
                final_prompt = build_jimeng_prompt(feature_for_request, custom_prompt, aspect_ratio, extra_notes)
            else:
                final_prompt = build_prompt(feature_for_request, custom_prompt, aspect_ratio, extra_notes)
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
                    "feature": feature_for_request,
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
                    "display_source_groups": (
                        [
                            [prepare_uploaded_input(group_item) for group_item in group]
                            for group in display_source_groups
                        ]
                        if display_source_groups
                        else []
                    ),
                    "output_mode": feature["output_mode"],
                    "max_output_images": max_output_images,
                    "target_size": target_size if supports_a_plus_images_api and target_size is not None else None,
                    "main_image_a_plus_layout_key": (
                        main_image_a_plus_layout_key if supports_main_image_a_plus else None
                    ),
                    "main_image_a_plus_layout": (
                        selected_main_image_a_plus_layout if supports_main_image_a_plus else None
                    ),
                    "main_image_a_plus_mode": (
                        main_image_a_plus_mode if supports_main_image_a_plus else None
                    ),
                    "main_image_a_plus_template": (
                        prepare_uploaded_input(main_image_a_plus_template_file)
                        if supports_main_image_a_plus
                        and main_image_a_plus_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
                        and main_image_a_plus_template_file is not None
                        else None
                    ),
                    "main_image_a_plus_element_replacements": (
                        [dict(item) for item in main_image_a_plus_element_replacements]
                        if supports_main_image_a_plus
                        and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
                        else []
                    ),
                    "outpaint_settings": (
                        {
                            "top": outpaint_top_px,
                            "bottom": outpaint_bottom_px,
                            "left": outpaint_left_px,
                            "right": outpaint_right_px,
                        }
                        if supports_outpaint
                        else {}
                    ),
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


def render_side_menu(current_feature: dict[str, Any] | None = None) -> None:
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
    for feature in get_visible_features():
        is_active = st.session_state.selected_feature_key == feature["key"]
        st.button(
            feature["name"],
            key=f"side_menu_feature_{feature['key']}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
            on_click=select_feature,
            args=(feature["key"],),
        )
    is_dashboard_active = st.session_state.selected_feature_key == XIAOHA_DASHBOARD_KEY
    st.button(
        "数据看板",
        key="side_menu_usage_dashboard",
        use_container_width=True,
        type="primary" if is_dashboard_active else "secondary",
        on_click=select_feature,
        args=(XIAOHA_DASHBOARD_KEY,),
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
    st.set_page_config(page_title="小哈", layout="wide", initial_sidebar_state="expanded")
    ensure_state()
    restore_auth_session()
    sync_background_jobs()
    ensure_history_storage()
    jimeng_static_server = ensure_jimeng_static_server()
    if consume_pending_upload_delete():
        st.rerun()
    if consume_pending_outpaint_drag():
        st.rerun()
    inject_app_styles()
    inject_clipboard_paste_support()
    if not st.session_state.is_authenticated:
        authenticate_requested_user()
    visible_features = get_visible_features()
    feature_keys = {feature["key"] for feature in visible_features}
    allowed_page_keys = feature_keys | {XIAOHA_DASHBOARD_KEY}
    if st.session_state.selected_feature_key not in allowed_page_keys:
        st.session_state.selected_feature_key = (
            XIAOHA_DEFAULT_FEATURE_KEY
            if XIAOHA_DEFAULT_FEATURE_KEY in feature_keys
            else (visible_features[0]["key"] if visible_features else XIAOHA_DASHBOARD_KEY)
        )
        if st.session_state.selected_feature_key:
            st.query_params[FEATURE_QUERY_KEY] = st.session_state.selected_feature_key

    current_feature = next(
        (
            feature
            for feature in visible_features
            if feature["key"] == st.session_state.selected_feature_key
        ),
        None,
    )
    if not bool(jimeng_static_server.get("started")):
        st.warning(
            "Agent 参考图静态服务启动失败，当前图片上传到 Agent 可能无法使用。"
            f"{str(jimeng_static_server.get('error') or '').strip()}"
        )
    menu_col, content_col = st.columns([0.62, 4.38], gap="small")
    with menu_col:
        render_side_menu(current_feature)
    with content_col:
        if st.session_state.selected_feature_key == XIAOHA_DASHBOARD_KEY:
            render_xiaoha_usage_dashboard()
        elif current_feature is not None:
            render_openrouter_feature(current_feature, model=DEFAULT_MODEL, aspect_ratio=DEFAULT_ASPECT_RATIO)


if __name__ == "__main__":
    if is_running_in_streamlit():
        main()
    else:
        relaunch_with_streamlit()
