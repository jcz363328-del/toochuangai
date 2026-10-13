from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from flask import Blueprint, Response, jsonify, redirect, request, send_from_directory, session, url_for
from openpyxl import load_workbook

from bjc import dui_db
from department_permissions import permission_manager
from secret_settings import ai_runtime_config, env


ROOT = Path(__file__).resolve().parent
CODE_DIR = ROOT / "code"
DATA_DIR = ROOT / "data"
DEFAULT_RANKING_FILE = DATA_DIR / "aba-ranking-export.json"
DEFAULT_RANKING_DASHBOARD_FILE = DATA_DIR / "ABA四核心词综合排名看板_2026-06-28~2026-07-04.html"
LEGACY_ACTIVE_RANKING_FILE = DATA_DIR / "active-aba-ranking.json"
LISTING_STORAGE_ROOT = Path(env("LISTING_STORAGE_ROOT") or r"D:\tuchuangai\Listing生成")
ABA_RANKING_STORAGE_DIR = Path(
    env("LISTING_ABA_RANKING_DIR") or LISTING_STORAGE_ROOT / "ABA排名"
)
SKILL_STORAGE_DIR = Path(env("LISTING_SKILL_STORAGE_DIR") or LISTING_STORAGE_ROOT / "Skills")
LISTING_ARCHIVE_DIR = Path(
    env("LISTING_ARCHIVE_DIR") or LISTING_STORAGE_ROOT / "lisitng"
)
ACTIVE_RANKING_FILE = ABA_RANKING_STORAGE_DIR / "active-aba-ranking.json"
LISTING_RECORD_TABLE = "dbo.Listing_ShengCheng"
LISTING_DATABASE_TEXT_LIMIT = 60_000
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_SILICONFLOW_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
DEFAULT_SILICONFLOW_TEXT_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"
DEFAULT_SELLFOX_DASHBOARD_URL = "http://127.0.0.1:8765"
MAX_BODY_BYTES = 26 * 1024 * 1024
MAX_RANKING_IMPORT_FILES = 4
DEFAULT_RANKING_CORE_ORDER = ("lash", "lashes", "eyelash", "eyelashes")
ABA_IMPORT_PERMISSION = "listing_agent_aba_import"
ABA_ECHARTS_ASSET_PATH = "/listing-agent/aba-ranking/echarts.min.js"
ABA_DASHBOARD_CACHE_LIMIT = 4
VISION_MODEL_FALLBACKS = (
    DEFAULT_SILICONFLOW_MODEL,
    "Qwen/Qwen3-VL-32B-Instruct",
    "Qwen/Qwen3-VL-30B-A3B-Instruct",
    "zai-org/GLM-4.5V",
)
TEXT_MODEL_FALLBACKS = (
    DEFAULT_SILICONFLOW_TEXT_MODEL,
    "Qwen/Qwen3-32B",
    "deepseek-ai/DeepSeek-V3.2",
)

DO_NOT_INFER = [
    "不要仅凭图片推断材质、成分、低敏、无乳胶、防水、佩戴时长、可复用次数、无刺激、无残留或敏感眼可用等声明。",
    "胶水、封层、卸除液、镊子/夹子等侧边道具，不能默认视为包含物；必须由包装、SKU 数据或用户确认。",
    "包装印刷文字和托盘标签的证据等级高于视觉风格猜测。",
]

EXTRACTION_PROMPT = """你是 Amazon 假睫毛产品图片事实提取助手。

请只提取图片中可见的事实，并按以下证据等级判断：
1. 包装印刷文字和托盘标签。
2. 清楚可见的产品内容物。
3. 只能对风格词做视觉推断，例如 wispy、natural、spiky、manga、bunny eye、cat eye、doll eye、soft glam。

只返回严格 JSON，不要输出 Markdown 或解释。JSON 字段名保持英文，字段值尽量使用中文：
{
  "facts": [
    {
      "key": "brandName | productType | lengths | curl | pieceCount | bandType | styleAngle | contents | packageText | rowCount | clustersPerRow | lengthBreakdown",
      "label": "简短中文标签",
      "value": "图片中可见的值",
      "source": "包装文字 | 托盘标签 | 可见内容物 | 视觉推断",
      "confidence": "high | medium | low"
    }
  ],
  "needsConfirmation": ["需要人工确认的中文短句"],
  "doNotInfer": ["禁止仅凭图片推断的中文短句"]
}

规则：
- 如果根数只是根据可见行数估算，value 必须写“图片可见估算”，confidence 用 medium 或 low。
- 如果长度或卷度看不清，不要猜，放入 needsConfirmation。
- 如果品牌、包装完整文字或包含工具不清楚，放入 needsConfirmation。
- 每个可见内容物单独输出一个 fact，key 使用 "contents"。
- 不要输出代码块、Markdown 或 JSON 之外的内容。"""

LISTING_SYSTEM_PROMPT = """You are an Amazon listing copywriter for beauty products. Write compliant, specific English listing copy from confirmed product facts only. Never invent materials, certifications, safety claims, wear time, waterproof performance, reusable count, package contents, or medical claims. Never use any forbidden term supplied by the user.

Keyword placement is mandatory, not optional:
1. Treat a smaller ABA rank number as higher priority. Use rankingPriority in ascending rank order.
2. Put the highest-ranked relevant exact keyword phrase near the beginning of the title. Fit the next distinct high-ranked phrase naturally when space permits.
3. Distribute remaining rankingPriority, conversionPriority and growthPriority phrases across different bullet points. Preserve exact phrase wording when grammatical.
4. Put relevant backendPriority phrases not already used in customer-facing copy into Search Terms. Do not repeat phrases already present in the title, Item Highlights, bullets or description.
5. Do not repeat the same product fact, benefit, specification or keyword phrase across multiple bullets. Each bullet must have a distinct job: primary benefit, specifications, design/use, scenario/audience, and package/decision information.

Use the available character space efficiently. The title must be exactly 70 characters and the Item Highlight must be exactly 125 characters, counting spaces and punctuation. Reach those targets with distinct relevant ranked keywords and confirmed product facts; never use filler, broken phrases, invented claims or repetition. Write substantial bullets of roughly 180-350 characters each when enough confirmed information is available. Start Item Highlights, every internal highlight, and every bullet with an uppercase English letter. Follow Amazon's requirements effective July 27, 2026 and its title quality rules: do not use !, $, ?, _, {, }, ^, ¬, or ¦ unless part of the brand name, and do not repeat the same substantive word more than twice. Item Highlights is a separate searchable customer-facing field for confirmed materials, specifications, or recommended use cases; it is not a bullet point. Respect bullet, description and backend-search-term limits. Return strict JSON only, with this shape:
{
  "variants": [
    {
      "id": "balanced | style | search",
      "title": "string",
      "itemHighlight": "string",
      "highlights": ["string", "string", "string"],
      "bullets": ["string", "string", "string", "string", "string"],
      "description": "string",
      "searchTerms": "string",
      "reasons": ["short Chinese explanation", "short Chinese explanation"]
    }
  ]
}
Return exactly three variants: balanced, style, search. The copy fields must be English. Reasons must be Chinese. Do not use markdown."""


listing_agent_bp = Blueprint("listing_agent", __name__, url_prefix="/listing-agent")
_http = requests.Session()
_http.trust_env = False
_aba_dashboard_cache_lock = threading.RLock()
_aba_dashboard_template_cache: dict[str, Any] = {}
_aba_dashboard_render_cache: dict[tuple[Any, ...], dict[str, Any]] = {}


@listing_agent_bp.before_request
def _require_login():
    if session.get("feishu_user_id"):
        if request.content_length and request.content_length > MAX_BODY_BYTES:
            return jsonify({"ok": False, "error": "Request body is too large."}), 413
        return None
    if request.path.startswith("/listing-agent/api/"):
        return jsonify({"ok": False, "error": "请先登录后再使用 Listing 生成智能体。"}), 401
    next_path = request.full_path.rstrip("?")
    session["post_auth_redirect"] = next_path
    return redirect(url_for("feishu_auth", next=next_path))


@listing_agent_bp.after_request
def _disable_api_cache(response):
    if request.path.startswith("/listing-agent/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@listing_agent_bp.get("")
def index_redirect():
    return redirect(url_for("listing_agent.index"), code=308)


@listing_agent_bp.get("/")
def index():
    return _send_code_file("index.html")


@listing_agent_bp.get("/app.js")
def app_js():
    return _send_code_file("app.js")


@listing_agent_bp.get("/styles.css")
def styles_css():
    return _send_code_file("styles.css")


@listing_agent_bp.get("/aba-ranking")
def aba_ranking_redirect():
    return redirect(url_for("listing_agent.aba_ranking_dashboard"), code=308)


@listing_agent_bp.get("/aba-ranking/")
def aba_ranking_dashboard():
    source_path = _get_active_ranking_file()
    try:
        can_import, _ = _aba_import_permission()
        rendered = _get_cached_aba_dashboard(source_path, can_import=can_import)
        return _cached_content_response(
            raw_content=rendered["raw"],
            gzip_content=rendered["gzip"],
            raw_etag=rendered["raw_etag"],
            gzip_etag=rendered["gzip_etag"],
            content_type="text/html; charset=utf-8",
            cache_control="private, no-cache",
        )
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    response = send_from_directory(
        DEFAULT_RANKING_DASHBOARD_FILE.parent,
        DEFAULT_RANKING_DASHBOARD_FILE.name,
        max_age=0,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@listing_agent_bp.get("/aba-ranking/echarts.min.js")
def aba_ranking_echarts():
    bundle = _load_aba_dashboard_template_bundle()
    return _cached_content_response(
        raw_content=bundle["echarts_raw"],
        gzip_content=bundle["echarts_gzip"],
        raw_etag=bundle["echarts_raw_etag"],
        gzip_etag=bundle["echarts_gzip_etag"],
        content_type="application/javascript; charset=utf-8",
        cache_control="public, max-age=31536000, immutable",
    )


def _send_code_file(filename: str):
    response = send_from_directory(CODE_DIR, filename, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    return response


def _aba_import_permission() -> tuple[bool, str]:
    user_id = str(session.get("feishu_user_id") or "").strip()
    if not user_id:
        return False, "未登录"
    try:
        return permission_manager.check_user_permission(user_id, ABA_IMPORT_PERMISSION)
    except Exception as exc:
        return False, f"权限校验失败：{_safe_detail(exc)}"


def _aba_ranking_import_controls(can_import: bool | None = None) -> str:
    """只为有权限的 AI 部用户把导入入口渲染到 ABA 排名看板。"""
    if can_import is None:
        can_import, _ = _aba_import_permission()
    if not can_import:
        return ""
    import_url = url_for("listing_agent.api_sellfox_import_ranking")
    return f"""
<style>
  .tc-aba-import-panel {{
    position: relative; z-index: 1000; display: flex; align-items: center;
    justify-content: space-between; gap: 18px; padding: 14px 22px;
    margin: 0; color: #eef6ff; background: linear-gradient(135deg, #123a69, #225f9e);
    border-bottom: 1px solid rgba(255,255,255,.2); box-shadow: 0 10px 24px rgba(8,33,64,.2);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  }}
  .tc-aba-import-copy strong {{ display: block; margin-bottom: 4px; font-size: 16px; }}
  .tc-aba-import-copy span {{ color: #cfe5ff; font-size: 13px; }}
  .tc-aba-import-actions {{ display: flex; align-items: center; gap: 10px; flex: 0 0 auto; }}
  .tc-aba-import-button {{
    border: 0; border-radius: 999px; padding: 10px 20px; cursor: pointer;
    color: #153a64; background: #fff; font-weight: 800; white-space: nowrap;
  }}
  .tc-aba-import-button:disabled {{ cursor: wait; opacity: .7; }}
  .tc-aba-import-status {{ min-width: 120px; font-size: 13px; color: #dcecff; }}
  @media (max-width: 760px) {{
    .tc-aba-import-panel {{ align-items: flex-start; flex-direction: column; padding: 14px 16px; }}
    .tc-aba-import-actions {{ width: 100%; flex-wrap: wrap; }}
  }}
</style>
<section class="tc-aba-import-panel" id="tcAbaImportPanel" aria-label="ABA 排名导入">
  <div class="tc-aba-import-copy">
    <strong>导入 ABA 排名</strong>
    <span>仅 AI 部可见；支持一次选择 1–4 份 HTML、JSON、CSV 或 XLSX 文件，合计不超过 26 MB。</span>
  </div>
  <div class="tc-aba-import-actions">
    <input id="tcAbaImportFiles" type="file" multiple hidden
           accept=".html,.htm,.json,.csv,.xlsx,text/html,application/json,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet">
    <button class="tc-aba-import-button" id="tcAbaImportButton" type="button">选择文件并导入</button>
    <span class="tc-aba-import-status" id="tcAbaImportStatus" aria-live="polite"></span>
  </div>
</section>
<script>
(() => {{
  const input = document.getElementById('tcAbaImportFiles');
  const button = document.getElementById('tcAbaImportButton');
  const status = document.getElementById('tcAbaImportStatus');
  if (!input || !button || !status) return;
  button.addEventListener('click', () => input.click());
  input.addEventListener('change', async () => {{
    const files = Array.from(input.files || []);
    input.value = '';
    if (!files.length) return;
    if (files.length > 4) {{ status.textContent = '一次最多选择 4 份文件'; return; }}
    const body = new FormData();
    body.append('file', files[0], files[0].name);
    files.slice(1).forEach((file) => body.append('files', file, file.name));
    button.disabled = true;
    button.textContent = '正在解析并生成看板…';
    status.textContent = '';
    try {{
      const response = await fetch({json.dumps(import_url)}, {{ method: 'POST', body }});
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.message || `导入失败（${{response.status}}）`);
      const count = Number(payload.summary?.uniqueTerms || 0).toLocaleString('zh-CN');
      status.textContent = `导入成功，共 ${{count}} 个搜索词，正在刷新…`;
      window.setTimeout(() => window.location.reload(), 700);
    }} catch (error) {{
      status.textContent = error?.message || '导入失败';
      button.disabled = false;
      button.textContent = '选择文件并导入';
    }}
  }});
}})();
</script>
"""


def _file_signature(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size)


def _content_etag(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _load_aba_dashboard_template_bundle() -> dict[str, Any]:
    """读取一次看板模板，并把 ECharts 拆成可长期缓存的静态资源。"""
    signature = _file_signature(DEFAULT_RANKING_DASHBOARD_FILE)
    with _aba_dashboard_cache_lock:
        if _aba_dashboard_template_cache.get("signature") == signature:
            return _aba_dashboard_template_cache

        template = DEFAULT_RANKING_DASHBOARD_FILE.read_text(encoding="utf-8-sig")
        license_index = template.find("Licensed to the Apache Software Foundation")
        if license_index < 0:
            raise ValueError("ABA 看板模板中未找到 ECharts 资源。")
        script_start = template.rfind("<script", 0, license_index)
        script_open_end = template.find(">", script_start)
        script_end = template.find("</script>", license_index)
        if min(script_start, script_open_end, script_end) < 0:
            raise ValueError("ABA 看板模板中的 ECharts 脚本不完整。")

        echarts_source = template[script_open_end + 1 : script_end]
        if len(echarts_source) < 500_000 or "echarts" not in echarts_source:
            raise ValueError("ABA 看板模板中的 ECharts 资源无法识别。")
        echarts_raw = echarts_source.encode("utf-8")
        echarts_gzip = gzip.compress(echarts_raw, compresslevel=6, mtime=0)
        echarts_raw_etag = _content_etag(echarts_raw)
        echarts_gzip_etag = _content_etag(echarts_gzip)
        asset_tag = (
            f'<script src="{ABA_ECHARTS_ASSET_PATH}?v={echarts_raw_etag[:16]}"></script>'
        )
        template = template[:script_start] + asset_tag + template[script_end + len("</script>") :]

        original_json = _extract_dashboard_json(template)
        default_payload = json.loads(original_json)
        default_meta = (
            dict(default_payload.get("meta") or {})
            if isinstance(default_payload, dict)
            else {}
        )
        _aba_dashboard_template_cache.clear()
        _aba_dashboard_template_cache.update(
            {
                "signature": signature,
                "template": template,
                "original_json": original_json,
                "default_meta": default_meta,
                "echarts_raw": echarts_raw,
                "echarts_gzip": echarts_gzip,
                "echarts_raw_etag": echarts_raw_etag,
                "echarts_gzip_etag": echarts_gzip_etag,
            }
        )
        _aba_dashboard_render_cache.clear()
        return _aba_dashboard_template_cache


def _render_aba_dashboard(source_path: Path, *, can_import: bool) -> dict[str, Any]:
    bundle = _load_aba_dashboard_template_bundle()
    template = bundle["template"]
    if source_path != DEFAULT_RANKING_FILE:
        dashboard_data = _load_ranking_data(source_path)
        dashboard_meta = (
            dashboard_data.get("meta")
            if isinstance(dashboard_data.get("meta"), dict)
            else {}
        )
        payload = {
            "meta": {**bundle["default_meta"], **dashboard_meta},
            "rows": [
                _ranking_row_to_dashboard_array(row)
                for row in dashboard_data.get("rows", [])
                if isinstance(row, dict)
            ],
        }
        serialized_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        serialized_payload = (
            serialized_payload.replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
        )
        template = template.replace(bundle["original_json"], serialized_payload, 1)

    import_controls = _aba_ranking_import_controls(can_import=can_import)
    if import_controls:
        template = template.replace("<body>", f"<body>{import_controls}", 1)
    raw_content = template.encode("utf-8")
    gzip_content = gzip.compress(raw_content, compresslevel=6, mtime=0)
    return {
        "raw": raw_content,
        "gzip": gzip_content,
        "raw_etag": _content_etag(raw_content),
        "gzip_etag": _content_etag(gzip_content),
    }


def _get_cached_aba_dashboard(source_path: Path, *, can_import: bool) -> dict[str, Any]:
    bundle = _load_aba_dashboard_template_bundle()
    cache_key = (
        bundle["signature"],
        _file_signature(source_path),
        bool(can_import),
    )
    with _aba_dashboard_cache_lock:
        cached = _aba_dashboard_render_cache.get(cache_key)
        if cached is not None:
            return cached
        rendered = _render_aba_dashboard(source_path, can_import=can_import)
        while len(_aba_dashboard_render_cache) >= ABA_DASHBOARD_CACHE_LIMIT:
            oldest_key = next(iter(_aba_dashboard_render_cache))
            _aba_dashboard_render_cache.pop(oldest_key, None)
        _aba_dashboard_render_cache[cache_key] = rendered
        return rendered


def _clear_aba_dashboard_render_cache() -> None:
    with _aba_dashboard_cache_lock:
        _aba_dashboard_render_cache.clear()


def _cached_content_response(
    *,
    raw_content: bytes,
    gzip_content: bytes,
    raw_etag: str,
    gzip_etag: str,
    content_type: str,
    cache_control: str,
) -> Response:
    use_gzip = request.accept_encodings["gzip"] > 0
    response = Response(
        gzip_content if use_gzip else raw_content,
        content_type=content_type,
    )
    if use_gzip:
        response.headers["Content-Encoding"] = "gzip"
    response.headers["Cache-Control"] = cache_control
    response.vary.add("Accept-Encoding")
    response.vary.add("Cookie")
    response.set_etag(gzip_etag if use_gzip else raw_etag)
    response.make_conditional(request)
    return response


@listing_agent_bp.route("/api/health", methods=["GET", "HEAD"])
def api_health():
    return jsonify(
        {
            "ok": True,
            "aiConfigured": bool(_get_api_key()),
        }
    )


@listing_agent_bp.route("/api/settings", methods=["GET", "HEAD"])
def api_settings():
    can_import_aba, _ = _aba_import_permission()
    return jsonify(
        {
            "managed": True,
            "aiConfigured": bool(_get_api_key()),
            "canImportAba": can_import_aba,
        }
    )


@listing_agent_bp.route("/api/user-state", methods=["GET", "HEAD", "POST"])
def api_user_state():
    user_name = _current_listing_user_name()
    skill_path = _skill_file_path(user_name)
    if request.method in {"GET", "HEAD"}:
        if not skill_path.exists():
            return jsonify(
                {
                    "ok": True,
                    "skills": [],
                    "preferences": {},
                    "riskLibrary": [],
                    "skillPath": str(skill_path),
                }
            )
        try:
            saved = json.loads(skill_path.read_text(encoding="utf-8"))
            return jsonify(
                {
                    "ok": True,
                    "skills": saved.get("skills") if isinstance(saved.get("skills"), list) else [],
                    "preferences": (
                        saved.get("preferences")
                        if isinstance(saved.get("preferences"), dict)
                        else {}
                    ),
                    "riskLibrary": (
                        saved.get("riskLibrary")
                        if isinstance(saved.get("riskLibrary"), list)
                        else []
                    ),
                    "skillPath": str(skill_path),
                    "updatedAt": _clean(saved.get("updatedAt")),
                }
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": f"偏好 Skill 读取失败：{_safe_detail(exc)}",
                    }
                ),
                500,
            )

    payload = _json_body()
    if payload is None:
        return jsonify({"ok": False, "message": "Invalid JSON request body."}), 400
    skills = payload.get("skills") if isinstance(payload.get("skills"), list) else []
    preferences = payload.get("preferences") if isinstance(payload.get("preferences"), dict) else {}
    risk_library = []
    seen_risk_terms: set[str] = set()
    for item in _object_list(payload.get("riskLibrary"), 200):
        term = _clean(item.get("term")).lower()
        if not term or term in seen_risk_terms:
            continue
        seen_risk_terms.add(term)
        risk_library.append(
            {
                "term": term,
                "level": "medium" if _clean(item.get("level")).lower() == "medium" else "high",
            }
        )
    if len(skills) > 100:
        return jsonify({"ok": False, "message": "最多保存 100 个 Listing Skill。"}), 400
    try:
        saved_at = _now_shanghai()
        _atomic_write_json(
            skill_path,
            {
                "version": 1,
                "userName": user_name,
                "updatedAt": saved_at.isoformat(),
                "skills": skills,
                "preferences": preferences,
                "riskLibrary": risk_library,
            },
        )
        _upsert_listing_record(
            user_name=user_name,
            saved_at=saved_at,
            skill_path=skill_path,
        )
        return jsonify(
            {
                "ok": True,
                "skillPath": str(skill_path),
                "updatedAt": saved_at.isoformat(),
            }
        )
    except OSError as exc:
        return jsonify({"ok": False, "message": f"偏好 Skill 保存失败：{_safe_detail(exc)}"}), 500
    except Exception as exc:
        return jsonify({"ok": False, "message": f"偏好 Skill 记录失败：{_safe_detail(exc)}"}), 500


@listing_agent_bp.post("/api/extract-image")
def api_extract_image():
    api_key = _get_api_key()
    if not api_key:
        return jsonify({"error": "服务端日报 AI 配置不可用，请联系管理员。"}), 500

    payload = _json_body()
    if payload is None:
        return jsonify({"error": "Invalid JSON request body."}), 400
    images = payload.get("images") if isinstance(payload.get("images"), list) else []
    valid_images = []
    for image in images[:4]:
        if not isinstance(image, dict):
            continue
        data_url = _clean(image.get("dataUrl"))
        if not data_url.startswith("data:image/"):
            continue
        valid_images.append(
            {
                "name": _clean(image.get("name")) or "uploaded-image",
                "type": _clean(image.get("type")),
                "dataUrl": data_url,
            }
        )
    if not valid_images:
        return jsonify({"error": "No valid image dataUrl values were provided."}), 400

    text = "\n".join(
        [
            EXTRACTION_PROMPT,
            "",
            f"Marketplace: {_clean(payload.get('marketplace')) or 'US'}",
            f"Selected category: {_clean(payload.get('category')) or 'false eyelashes'}",
            f"Image filenames: {', '.join(item['name'] for item in valid_images)}",
        ]
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    content.extend(
        {"type": "image_url", "image_url": {"url": image["dataUrl"]}}
        for image in valid_images
    )
    result = _call_siliconflow_with_fallbacks(
        api_key,
        {
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.1,
            "max_tokens": 1400,
        },
    )
    if not result.get("ok"):
        reason = result.get("error") if isinstance(result.get("error"), dict) else {}
        return (
            jsonify(
                {
                    "error": "SiliconFlow request failed",
                    "siliconFlowStatus": result.get("status", 0),
                    "siliconFlowCode": reason.get("code", ""),
                    "siliconFlowMessage": reason.get("message") or _safe_detail(result.get("text")),
                }
            ),
            502,
        )

    completion = _parse_json_from_text(result.get("text")) or {}
    content_value = _completion_content(completion)
    parsed = _parse_json_from_text(content_value)
    if not isinstance(parsed, dict):
        return jsonify(
            {
                "facts": [],
                "needsConfirmation": ["图片识别服务已返回内容，但无法解析为 JSON。请手动填写图片可见事实。"],
                "doNotInfer": DO_NOT_INFER,
                "source": "服务端图片识别返回了无法解析的内容。",
            }
        )

    return jsonify(
        {
            "facts": _normalize_facts(parsed.get("facts")),
            "needsConfirmation": _normalize_strings(parsed.get("needsConfirmation") or parsed.get("needs")),
            "doNotInfer": _unique_strings(
                _normalize_strings(parsed.get("doNotInfer") or parsed.get("blocked")) + DO_NOT_INFER
            ),
            "source": "服务端图片识别",
        }
    )


@listing_agent_bp.post("/api/generate-listings")
def api_generate_listings():
    api_key = _get_api_key()
    if not api_key:
        return jsonify({"error": "服务端日报 AI 配置不可用，请联系管理员。"}), 500
    payload = _json_body()
    if payload is None:
        return jsonify({"error": "Invalid JSON request body."}), 400
    prompt_payload = _normalize_listing_generation_input(payload)
    if not prompt_payload["product"]["type"]:
        return jsonify({"error": "Confirmed product facts are required before generating listings."}), 400

    model_payload = {
        "model": _get_text_model(),
        "temperature": 0.65,
        # Listing generation is a structured copywriting task. Qwen3 models may
        # otherwise spend a large part of the request budget on hidden reasoning.
        "enable_thinking": False,
        "max_tokens": 4000,
        "messages": [
            {"role": "system", "content": LISTING_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
        ],
    }
    result = _call_siliconflow_with_text_fallbacks(api_key, model_payload)
    if not result.get("ok"):
        reason = result.get("error") if isinstance(result.get("error"), dict) else {}
        return (
            jsonify(
                {
                    "error": "SiliconFlow text generation failed",
                    "siliconFlowStatus": result.get("status", 0),
                    "siliconFlowCode": reason.get("code", ""),
                    "siliconFlowMessage": reason.get("message") or _safe_detail(result.get("text")),
                }
            ),
            502,
        )

    completion = _parse_json_from_text(result.get("text")) or {}
    parsed = _parse_json_from_text(_completion_content(completion)) or {}
    variants = _normalize_generated_listing_variants(parsed.get("variants") if isinstance(parsed, dict) else None)
    if len(variants) != 3:
        return (
            jsonify(
                {
                    "error": "SiliconFlow returned an incomplete listing payload.",
                    "detail": _safe_detail(_completion_content(completion)),
                }
            ),
            502,
        )
    try:
        storage = _persist_generated_listing(
            source_payload=payload,
            prompt_payload=prompt_payload,
            variants=variants,
        )
    except Exception as exc:
        detail = _safe_detail(exc)
        return jsonify(
            {
                "ok": True,
                "variants": variants,
                "warning": "Listing generated but persistence failed",
                "storage": {
                    "storedAs": "unsaved",
                    "persistenceFailed": True,
                    "message": detail,
                },
            }
        )
    return jsonify({"ok": True, "variants": variants, "storage": storage})


@listing_agent_bp.route("/api/sellfox/ranking-file", methods=["GET", "HEAD"])
def api_sellfox_ranking_file():
    try:
        source_path = _get_active_ranking_file()
        dashboard_data = _load_ranking_data(source_path)
        rows = dashboard_data.get("rows") if isinstance(dashboard_data.get("rows"), list) else []
        meta = dashboard_data.get("meta") if isinstance(dashboard_data.get("meta"), dict) else {}
        return jsonify(
            {
                "ok": True,
                "source": meta.get("importedSource") or source_path.name,
                "updatedAt": datetime.fromtimestamp(
                    source_path.stat().st_mtime,
                    tz=timezone.utc,
                ).isoformat(),
                "meta": meta,
                "summary": {
                    "rawRows": meta.get("rawRowCount") or len(rows),
                    "uniqueTerms": meta.get("uniqueTermCount") or len(rows),
                    "top30000Count": meta.get("top30000Count") or 0,
                },
                "rows": rows,
            }
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "message": "无法读取已绑定的赛狐 ABA 看板文件。",
                    "detail": _safe_detail(exc),
                }
            ),
            500,
        )


@listing_agent_bp.post("/api/sellfox/import-ranking")
def api_sellfox_import_ranking():
    can_import_aba, permission_reason = _aba_import_permission()
    if not can_import_aba:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "权限不足",
                    "message": "当前账号没有 ABA 看板导入权限。",
                    "detail": permission_reason,
                    "requiredFunction": ABA_IMPORT_PERMISSION,
                }
            ),
            403,
        )
    # 同时接收旧前端的 file 和新前端的 files，避免服务/静态资源
    # 热更新先后不一致时出现“请选择文件”的误报。
    uploads = request.files.getlist("file") + request.files.getlist("files")
    uploads = [upload for upload in uploads if upload and Path(upload.filename or "").name]
    if not uploads:
        return jsonify({"ok": False, "message": "请选择要导入的 ABA 看板文件。"}), 400
    if len(uploads) > MAX_RANKING_IMPORT_FILES:
        return jsonify({"ok": False, "message": "一次最多导入 4 个 ABA 看板文件。"}), 400

    upload_sources: list[tuple[str, str, bytes]] = []
    total_bytes = 0
    for upload in uploads:
        filename = Path(upload.filename or "").name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".html", ".htm", ".json", ".csv", ".xlsx"}:
            return jsonify({"ok": False, "message": f"{filename} 格式不支持，仅支持 HTML、JSON、CSV 或 XLSX。"}), 400
        content = upload.stream.read(MAX_BODY_BYTES + 1)
        if not content:
            return jsonify({"ok": False, "message": f"{filename} 是空文件。"}), 400
        total_bytes += len(content)
        if total_bytes > MAX_BODY_BYTES:
            return jsonify({"ok": False, "message": "ABA 看板文件合计不能超过 26 MB。"}), 413
        upload_sources.append((filename, suffix, content))

    try:
        parsed_sources = []
        for filename, suffix, content in upload_sources:
            parsed = _parse_uploaded_ranking_data(content, suffix, filename)
            if not parsed.get("rows"):
                raise ValueError(f"{filename} 中未找到可用的 ABA 搜索词排名记录。")
            parsed_sources.append((filename, parsed))
        dashboard_data = (
            _merge_uploaded_ranking_datasets(parsed_sources)
            if len(parsed_sources) > 1 or upload_sources[0][1] in {".csv", ".xlsx"}
            else parsed_sources[0][1]
        )
        rows = dashboard_data.get("rows") if isinstance(dashboard_data.get("rows"), list) else []
        if not rows:
            raise ValueError("未找到可用的 ABA 搜索词排名记录。")
        stored_files = _store_aba_uploads(upload_sources)
        meta = dashboard_data.setdefault("meta", {})
        meta["importedBy"] = _current_listing_user_name()
        meta["storedFiles"] = [str(path) for path in stored_files]
        ACTIVE_RANKING_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = ACTIVE_RANKING_FILE.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(dashboard_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(ACTIVE_RANKING_FILE)
        _clear_aba_dashboard_render_cache()
        return jsonify(
            {
                "ok": True,
                "source": meta.get("importedSource") or upload_sources[0][0],
                "importedAt": meta.get("importedAt"),
                "summary": {
                    "rawRows": meta.get("rawRowCount") or len(rows),
                    "uniqueTerms": meta.get("uniqueTermCount") or len(rows),
                    "top30000Count": meta.get("top30000Count") or 0,
                },
                "storedFiles": [str(path) for path in stored_files],
            }
        )
    except (UnicodeError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        return jsonify({"ok": False, "message": f"ABA 看板解析失败：{_safe_detail(exc)}"}), 400
    except OSError as exc:
        return jsonify({"ok": False, "message": f"ABA 看板保存失败：{_safe_detail(exc)}"}), 500


@listing_agent_bp.route(
    "/api/sellfox/<path:resource>",
    methods=["GET", "HEAD", "POST"],
)
def api_sellfox_proxy(resource: str):
    dashboard_path = _sellfox_dashboard_path(resource)
    if not dashboard_path:
        return jsonify({"error": "Unknown Sellfox integration endpoint."}), 404
    base_url = (env("SELLFOX_DASHBOARD_URL") or DEFAULT_SELLFOX_DASHBOARD_URL).rstrip("/")
    target_url = f"{base_url}{dashboard_path}"
    try:
        response = _http.request(
            request.method,
            target_url,
            params=request.args,
            json=request.get_json(silent=True) if request.method == "POST" else None,
            timeout=30,
        )
        parsed = _parse_json_from_text(response.text)
        payload = parsed if isinstance(parsed, dict) else {"ok": False, "message": _safe_detail(response.text)}
        return jsonify(payload), response.status_code
    except requests.RequestException as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "message": f"无法连接赛狐广告看板（{base_url}）。请先启动它的本地服务。",
                    "detail": _safe_detail(exc),
                }
            ),
            502,
        )


def _call_siliconflow_with_fallbacks(api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    last_result: dict[str, Any] = {}
    for model in _unique_strings([_get_model(), *VISION_MODEL_FALLBACKS]):
        result = _call_siliconflow(api_key, {**payload, "model": model})
        last_result = result
        if result.get("ok") or not _model_unavailable(result):
            return result
    return last_result


def _call_siliconflow_with_text_fallbacks(api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    last_result: dict[str, Any] = {}
    for model in _unique_strings([_get_text_model(), *TEXT_MODEL_FALLBACKS]):
        result = _call_siliconflow(
            api_key,
            {**payload, "model": model},
            read_timeout=60,
        )
        last_result = result
        if result.get("ok") or not _text_model_retryable(result):
            return result
    return last_result


def _call_siliconflow(
    api_key: str,
    payload: dict[str, Any],
    *,
    read_timeout: int = 180,
) -> dict[str, Any]:
    url = f"{_get_ai_base_url().rstrip('/')}/chat/completions"
    try:
        response = _http.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=(10, read_timeout),
        )
        text = response.text
        parsed = _parse_json_from_text(text)
        error = parsed.get("error", parsed) if isinstance(parsed, dict) else {}
        return {
            "ok": response.ok,
            "status": response.status_code,
            "text": text,
            "model": payload.get("model"),
            "error": error if isinstance(error, dict) else {},
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "status": 0,
            "text": str(exc),
            "model": payload.get("model"),
            "error": {"message": str(exc)},
        }


def _model_unavailable(result: dict[str, Any]) -> bool:
    error = result.get("error") if isinstance(result.get("error"), dict) else {}
    code = _finite_number(error.get("code"))
    message = _clean(error.get("message")).lower()
    unavailable_messages = (
        "model disabled",
        "model does not exist",
        "model not found",
        "model is unavailable",
        "unknown model",
    )
    return code in {20012, 30003} or any(text in message for text in unavailable_messages)


def _text_model_retryable(result: dict[str, Any]) -> bool:
    if _model_unavailable(result):
        return True
    status = int(_finite_number(result.get("status")) or 0)
    error = result.get("error") if isinstance(result.get("error"), dict) else {}
    message = f"{_clean(error.get('message'))} {_clean(result.get('text'))}".lower()
    return status == 0 or status in {408, 409, 425, 429} or status >= 500 or "timed out" in message


def _normalize_listing_generation_input(data: dict[str, Any]) -> dict[str, Any]:
    product = data.get("product") if isinstance(data.get("product"), dict) else {}
    keywords = data.get("keywords") if isinstance(data.get("keywords"), dict) else {}
    compliance = data.get("compliance") if isinstance(data.get("compliance"), dict) else {}
    skill = data.get("skill") if isinstance(data.get("skill"), dict) else {}
    limits = data.get("limits") if isinstance(data.get("limits"), dict) else {}

    def terms(items: Any, *, priority: str = "rank") -> list[dict[str, Any]]:
        normalized = []
        for item in _object_list(items, 10):
            term = _clean(item.get("term"))
            if not term:
                continue
            normalized.append(
                {
                    "term": term,
                    "rank": _finite_number(item.get("rank")),
                    "growth": _finite_number(item.get("growth")),
                    "clickShare": _finite_number(item.get("clickShare")),
                    "conversionShare": _finite_number(item.get("conversionShare")),
                }
            )
        if priority == "growth":
            return sorted(normalized, key=lambda item: (-(item["growth"] or 0), item["rank"] or math.inf))
        if priority == "conversion":
            return sorted(
                normalized,
                key=lambda item: (-(item["conversionShare"] or 0), item["rank"] or math.inf),
            )
        return sorted(normalized, key=lambda item: (item["rank"] is None, item["rank"] or math.inf))

    return {
        "marketplace": _clean(data.get("marketplace")) or "US",
        "product": {
            "brand": _clean(product.get("brand")),
            "type": _clean(product.get("type")),
            "style": _clean(product.get("style")),
            "lengths": _clean(product.get("lengths")),
            "curl": _clean(product.get("curl")),
            "bandType": _clean(product.get("bandType")),
            "pieceCount": _clean(product.get("pieceCount")),
            "contents": _string_list(product.get("contents"), 8),
            "verifiedClaims": _string_list(product.get("verifiedClaims"), 8),
            "imageFacts": _clean(product.get("imageFacts"))[:2400],
            "needsConfirmation": _string_list(product.get("needsConfirmation"), 8),
        },
        "keywords": {
            "t1": _string_list(keywords.get("t1"), 10),
            "t2": _string_list(keywords.get("t2"), 10),
            "t3": _string_list(keywords.get("t3"), 10),
            "rankingPriority": terms(keywords.get("rankingPriority")),
            "growthPriority": terms(keywords.get("growthPriority"), priority="growth"),
            "conversionPriority": terms(keywords.get("conversionPriority"), priority="conversion"),
            "backendPriority": terms(keywords.get("backendPriority")),
        },
        "compliance": {
            "forbiddenTerms": _string_list(compliance.get("forbiddenTerms"), 80),
            "customRules": _clean(compliance.get("customRules"))[:3000],
        },
        "skill": {
            "name": _clean(skill.get("name")),
            "titleStrategy": _clean(skill.get("titleStrategy")),
            "tone": _clean(skill.get("tone")),
            "bulletPattern": _clean(skill.get("bulletPattern")),
            "learnedRules": _string_list(skill.get("learnedRules"), 12),
            "historicalReference": _clean(skill.get("historicalReference"))[:5000],
        },
        "limits": {
            "title": 70,
            "itemHighlight": _clamp(limits.get("itemHighlight"), 125, 40, 125),
            "bullet": _clamp(limits.get("bullet"), 500, 100, 1000),
            "description": _clamp(limits.get("description"), 2000, 300, 4000),
            "searchTermsBytes": _clamp(limits.get("searchTermsBytes"), 249, 80, 500),
        },
        "variants": [
            {
                "id": _clean(item.get("id")),
                "name": _clean(item.get("name")),
                "direction": _clean(item.get("direction")),
            }
            for item in _object_list(data.get("variants"), 3)
            if _clean(item.get("id"))
        ],
    }


def _normalize_generated_listing_variants(variants: Any) -> list[dict[str, Any]]:
    expected_ids = ("balanced", "style", "search")
    normalized: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(_object_list(variants, 3)):
        candidate_id = _clean(value.get("id"))
        variant_id = candidate_id if candidate_id in expected_ids else expected_ids[index]
        highlights = [
            _uppercase_first_letter(_fit_copy_limit(item, 125))
            for item in _string_list(value.get("highlights"), 3)
        ]
        item_highlight = _uppercase_first_letter(_fit_copy_limit(
            value.get("itemHighlight") or value.get("itemHighlights") or value.get("subtitle"),
            125,
        ))
        if not item_highlight and highlights:
            item_highlight = highlights[0]
        variant = {
            "id": variant_id,
            "title": _fit_copy_limit(value.get("title"), 70),
            "itemHighlight": item_highlight,
            "highlights": highlights,
            "bullets": [
                _uppercase_first_letter(_fit_copy_limit(item, 500))
                for item in _string_list(value.get("bullets"), 5)
            ],
            "description": _clean(value.get("description")),
            "searchTerms": _clean(value.get("searchTerms")),
            "reasons": _string_list(value.get("reasons"), 4),
        }
        if (
            variant["title"]
            and variant["itemHighlight"]
            and variant["highlights"]
            and variant["bullets"]
            and variant["description"]
            and variant["searchTerms"]
        ):
            normalized[variant_id] = variant
    return [normalized[variant_id] for variant_id in expected_ids if variant_id in normalized]


def _get_active_ranking_file() -> Path:
    if ACTIVE_RANKING_FILE.exists():
        return ACTIVE_RANKING_FILE
    if LEGACY_ACTIVE_RANKING_FILE.exists():
        return LEGACY_ACTIVE_RANKING_FILE
    configured = env("SELLFOX_RANKING_FILE")
    return Path(configured) if configured else DEFAULT_RANKING_FILE


def _now_shanghai() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def _current_listing_user_name() -> str:
    return (
        _clean(session.get("feishu_user_name"))
        or _clean(session.get("feishu_user_id"))
        or "未知用户"
    )


def _safe_file_component(value: Any, fallback: str = "file") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")
    return (cleaned or fallback)[:160]


def _skill_file_path(user_name: str) -> Path:
    return SKILL_STORAGE_DIR / f"{_safe_file_component(user_name, '用户')}_偏好Skill.json"


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = _now_shanghai().strftime("%Y%m%d%H%M%S%f")
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.{stamp}.tmp")
    temporary_path.write_bytes(content)
    temporary_path.replace(path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_bytes(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
    )


def _store_aba_uploads(upload_sources: list[tuple[str, str, bytes]]) -> list[Path]:
    saved_at = _now_shanghai()
    stamp = saved_at.strftime("%Y%m%d_%H%M%S_%f")
    user_name = _safe_file_component(_current_listing_user_name(), "用户")
    stored_paths: list[Path] = []
    for index, (filename, suffix, content) in enumerate(upload_sources, start=1):
        original_stem = _safe_file_component(Path(filename).stem, "ABA排名")
        target_path = ABA_RANKING_STORAGE_DIR / (
            f"{stamp}_{user_name}_{index:02d}_{original_stem}{suffix}"
        )
        _atomic_write_bytes(target_path, content)
        stored_paths.append(target_path)
    return stored_paths


def _sql_escape(value: Any) -> str:
    return str(value or "").replace("'", "''")


def _upsert_listing_record(
    *,
    user_name: str,
    saved_at: datetime,
    skill_path: Path,
    listing_value: str | None = None,
) -> None:
    normalized_user = str(user_name or "")[:50]
    saved_at_value = saved_at.strftime("%Y-%m-%d %H:%M:%S")
    skill_path_value = str(skill_path)
    dui_db(
        f"""
        DECLARE @YongHu NVARCHAR(50) = %s;
        DECLARE @RiQi DATETIME2 = %s;
        DECLARE @Listing NVARCHAR(MAX) = %s;
        DECLARE @WeiZhi NVARCHAR(MAX) = %s;
        DECLARE @HasListing BIT = %s;
        DECLARE @LatestID INT = (
            SELECT TOP 1 ID
            FROM {LISTING_RECORD_TABLE}
            WHERE YongHu = @YongHu
            ORDER BY ID DESC
        );
        IF @LatestID IS NULL
        BEGIN
            INSERT INTO {LISTING_RECORD_TABLE} (YongHu, RiQi, [Listing], WeiZhi)
            VALUES (@YongHu, @RiQi, @Listing, @WeiZhi);
        END
        ELSE
        BEGIN
            UPDATE {LISTING_RECORD_TABLE}
            SET RiQi = @RiQi,
                WeiZhi = @WeiZhi,
                [Listing] = CASE WHEN @HasListing = 1 THEN @Listing ELSE [Listing] END
            WHERE ID = @LatestID;
        END
        """,
        params=(
            normalized_user,
            saved_at_value,
            listing_value,
            skill_path_value,
            1 if listing_value is not None else 0,
        ),
    )


def _ensure_skill_file(source_payload: dict[str, Any], user_name: str, saved_at: datetime) -> Path:
    skill_path = _skill_file_path(user_name)
    if skill_path.exists():
        return skill_path
    raw_skill = source_payload.get("skill") if isinstance(source_payload.get("skill"), dict) else {}
    _atomic_write_json(
        skill_path,
        {
            "version": 1,
            "userName": user_name,
            "updatedAt": saved_at.isoformat(),
            "skills": [raw_skill] if raw_skill else [],
            "preferences": {},
        },
    )
    return skill_path


def _persist_generated_listing(
    *,
    source_payload: dict[str, Any],
    prompt_payload: dict[str, Any],
    variants: list[dict[str, Any]],
) -> dict[str, Any]:
    saved_at = _now_shanghai()
    user_name = _current_listing_user_name()
    skill_path = _ensure_skill_file(source_payload, user_name, saved_at)
    archive_payload = {
        "version": 1,
        "userName": user_name,
        "generatedAt": saved_at.isoformat(),
        "input": prompt_payload,
        "variants": variants,
    }
    serialized = json.dumps(archive_payload, ensure_ascii=False, indent=2)
    listing_value = serialized
    archive_path: Path | None = None
    if len(serialized) > LISTING_DATABASE_TEXT_LIMIT:
        stamp = saved_at.strftime("%Y%m%d_%H%M%S_%f")
        archive_path = LISTING_ARCHIVE_DIR / (
            f"{stamp}_{_safe_file_component(user_name, '用户')}_Listing.json"
        )
        _atomic_write_json(archive_path, archive_payload)
        listing_value = str(archive_path)
    _upsert_listing_record(
        user_name=user_name,
        saved_at=saved_at,
        skill_path=skill_path,
        listing_value=listing_value,
    )
    return {
        "storedAs": "file" if archive_path else "database",
        "listingPath": str(archive_path) if archive_path else "",
        "skillPath": str(skill_path),
        "savedAt": saved_at.isoformat(),
    }


def _load_ranking_data(source_path: Path) -> dict[str, Any]:
    source = source_path.read_text(encoding="utf-8-sig")
    if source_path.suffix.lower() == ".json":
        parsed = json.loads(source)
        return _normalize_ranking_dataset(parsed, source_path.name, imported=False)
    raw_data = json.loads(_extract_dashboard_json(source))
    return _normalize_ranking_dataset(raw_data, source_path.name, imported=False)


def _parse_uploaded_ranking_data(content: bytes, suffix: str, filename: str) -> dict[str, Any]:
    if suffix == ".xlsx":
        parsed: Any = {"rows": _parse_xlsx_ranking_rows(content)}
        return _normalize_ranking_dataset(parsed, filename, imported=True)

    try:
        source = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        source = content.decode("gb18030")

    if suffix == ".json":
        parsed: Any = json.loads(source)
    elif suffix in {".html", ".htm"}:
        parsed = json.loads(_extract_dashboard_json(source))
    else:
        parsed = {"rows": list(csv.DictReader(io.StringIO(source)))}
    return _normalize_ranking_dataset(parsed, filename, imported=True)


def _parse_xlsx_ranking_rows(content: bytes) -> list[dict[str, Any]]:
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"无法读取 XLSX 文件：{_safe_detail(exc)}") from exc

    term_headers = {"searchterm", "搜索词", "关键词", "keyword"}
    rank_headers = {
        "searchfrequencyrank",
        "搜索词频率排名",
        "aba排名",
        "排名",
    }
    try:
        for worksheet in workbook.worksheets:
            # 部分 ABA 导出文件的 XML 明明包含完整数据，却把 dimension 错写为 A1。
            # read_only 模式会相信这个范围，因此必须重置后再逐行扫描。
            worksheet.reset_dimensions()
            worksheet_rows = worksheet.iter_rows(values_only=True)
            for candidate in worksheet_rows:
                headers = [_clean(value) for value in candidate]
                normalized_headers = {
                    re.sub(r"[\s_\-]+", "", header).casefold()
                    for header in headers
                    if header
                }
                if not (normalized_headers & term_headers and normalized_headers & rank_headers):
                    continue

                rows = []
                for values in worksheet_rows:
                    if not any(value not in (None, "") for value in values):
                        continue
                    rows.append(
                        {
                            header: values[index] if index < len(values) else None
                            for index, header in enumerate(headers)
                            if header
                        }
                    )
                if rows:
                    return rows
    finally:
        workbook.close()

    raise ValueError("XLSX 中未找到包含“搜索词”和“搜索词频率排名”的数据表。")


def _merge_uploaded_ranking_datasets(
    sources: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    core_order = list(DEFAULT_RANKING_CORE_ORDER)
    assigned_cores = _assign_uploaded_core_terms(sources, core_order)
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    source_keys: list[set[tuple[str, str]]] = []
    conflicting_keys: set[tuple[str, str]] = set()

    for source_index, (_filename, dataset) in enumerate(sources):
        source_bit = 1 << core_order.index(assigned_cores[source_index])
        keys: set[tuple[str, str]] = set()
        for raw_row in dataset.get("rows", []):
            if not isinstance(raw_row, dict):
                continue
            row = dict(raw_row)
            key = (
                _clean(row.get("marketplace")).casefold(),
                _clean(row.get("searchTerm")).casefold(),
            )
            if not key[1]:
                continue
            keys.add(key)
            current = merged.get(key)
            if current is None:
                row["sourceMask"] = source_bit
                merged[key] = row
                continue
            if row.get("searchFrequencyRank") != current.get("searchFrequencyRank"):
                conflicting_keys.add(key)
            current_mask = int(current.get("sourceMask") or 0)
            if row["searchFrequencyRank"] < current["searchFrequencyRank"]:
                row["sourceMask"] = current_mask | source_bit
                merged[key] = row
            else:
                current["sourceMask"] = current_mask | source_bit
        source_keys.append(keys)

    rows = sorted(merged.values(), key=lambda item: item["searchFrequencyRank"])
    for row in rows:
        row["sourceCount"] = int(row.get("sourceMask") or 0).bit_count()

    source_summary = []
    for source_index, (filename, _dataset) in enumerate(sources):
        core_term = assigned_cores[source_index]
        source_bit = 1 << core_order.index(core_term)
        keys = source_keys[source_index]
        source_rows = [merged[key] for key in keys]
        exact = next(
            (
                row
                for row in source_rows
                if _clean(row.get("searchTerm")).casefold() == core_term.casefold()
            ),
            None,
        )
        best = min(source_rows, key=lambda row: row["searchFrequencyRank"], default=None)
        source_summary.append(
            {
                "coreTerm": core_term,
                "sourceBit": source_bit,
                "sourceFile": filename,
                "rowCount": len(source_rows),
                "exclusiveCount": sum(1 for row in source_rows if row["sourceCount"] == 1),
                "overlapCount": sum(1 for row in source_rows if row["sourceCount"] > 1),
                "top30000Count": sum(
                    1 for row in source_rows if row["searchFrequencyRank"] <= 30000
                ),
                "exactRank": exact.get("searchFrequencyRank") if exact else None,
                "bestRank": best.get("searchFrequencyRank") if best else None,
                "bestTerm": best.get("searchTerm") if best else "",
            }
        )
    source_summary.sort(key=lambda item: core_order.index(item["coreTerm"]))

    imported_at = datetime.now(timezone.utc)
    raw_row_count = sum(
        int(dataset.get("meta", {}).get("rawRowCount") or len(dataset.get("rows", [])))
        for _filename, dataset in sources
    )
    marketplaces = _unique_strings([row.get("marketplace") for row in rows])
    source_names = [filename for filename, _dataset in sources]
    return {
        "meta": {
            "title": "ABA 四核心词综合排名",
            "marketplace": " / ".join(marketplaces),
            "dateRange": _ranking_import_date_range(source_names, imported_at),
            "generatedAt": imported_at.isoformat(),
            "importedAt": imported_at.isoformat(),
            "importedSource": source_names[0] if len(sources) == 1 else f"{len(sources)}份文件合并",
            "rawRowCount": raw_row_count,
            "uniqueTermCount": len(rows),
            "duplicateTermCount": sum(1 for row in rows if row["sourceCount"] > 1),
            "duplicateRowsRemoved": max(0, raw_row_count - len(rows)),
            "conflictingRankCount": len(conflicting_keys),
            "top30000Count": sum(1 for row in rows if row["searchFrequencyRank"] <= 30000),
            "coreOrder": core_order,
            "sourceSummary": source_summary,
        },
        "rows": rows,
    }


def _assign_uploaded_core_terms(
    sources: list[tuple[str, dict[str, Any]]],
    core_order: list[str],
) -> list[str]:
    candidate_sets = []
    for _filename, dataset in sources:
        terms = {
            _clean(row.get("searchTerm")).casefold()
            for row in dataset.get("rows", [])
            if isinstance(row, dict)
        }
        candidate_sets.append({term for term in core_order if term.casefold() in terms})

    assignments: dict[int, str] = {}
    used: set[str] = set()
    for core_term in core_order:
        matching_sources = [
            index
            for index, candidates in enumerate(candidate_sets)
            if index not in assignments and core_term in candidates
        ]
        if len(matching_sources) == 1:
            assignments[matching_sources[0]] = core_term
            used.add(core_term)

    for index, candidates in enumerate(candidate_sets):
        if index in assignments:
            continue
        available = [term for term in core_order if term in candidates and term not in used]
        if len(available) == 1:
            assignments[index] = available[0]
            used.add(available[0])

    remaining = [term for term in core_order if term not in used]
    for index in range(len(sources)):
        if index not in assignments:
            assignments[index] = remaining.pop(0)
    return [assignments[index] for index in range(len(sources))]


def _ranking_import_date_range(source_names: list[str], imported_at: datetime) -> str:
    ranges = []
    for source_name in source_names:
        match = re.search(r"(\d{4}-\d{2}-\d{2})\s*[~至]\s*(\d{4}-\d{2}-\d{2})", source_name)
        if match:
            ranges.append((match.group(1), match.group(2)))
    if ranges and len(set(ranges)) == 1:
        return f"{ranges[0][0]} 至 {ranges[0][1]}"
    return f"导入于 {imported_at.date().isoformat()}"


def _extract_dashboard_json(source: str) -> str:
    marker = re.search(r"\bconst\s+DATA\s*=", source)
    if not marker:
        raise ValueError("看板中未找到 DATA 数据集。")
    start = source.find("{", marker.end())
    if start < 0:
        raise ValueError("看板 DATA 数据格式不完整。")
    return _extract_balanced_json(source, start)


def _normalize_ranking_dataset(data: Any, source_name: str, *, imported: bool) -> dict[str, Any]:
    if isinstance(data, list):
        raw_rows = data
        raw_meta: dict[str, Any] = {}
    elif isinstance(data, dict):
        raw_rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        raw_meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    else:
        raise ValueError("排名数据顶层必须为对象或数组。")

    normalized: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_row in raw_rows:
        row = _map_dashboard_row(raw_row) if isinstance(raw_row, list) else _normalize_ranking_row(raw_row)
        if not row:
            continue
        key = (_clean(row.get("marketplace")).casefold(), _clean(row.get("searchTerm")).casefold())
        current = normalized.get(key)
        if current is None or row["searchFrequencyRank"] < current["searchFrequencyRank"]:
            normalized[key] = row

    rows = sorted(normalized.values(), key=lambda item: item["searchFrequencyRank"])
    meta = dict(raw_meta)
    meta.update(
        {
            "title": _clean(meta.get("title")) or "ABA 搜索词排名详情",
            "rawRowCount": len(raw_rows),
            "uniqueTermCount": len(rows),
            "duplicateRowsRemoved": max(0, len(raw_rows) - len(rows)),
            "top30000Count": sum(1 for row in rows if row["searchFrequencyRank"] <= 30000),
        }
    )
    if imported:
        imported_at = datetime.now(timezone.utc)
        meta["importedSource"] = source_name
        meta["importedAt"] = imported_at.isoformat()
        meta["dateRange"] = _clean(meta.get("dateRange")) or f"导入于 {imported_at.date().isoformat()}"
        meta["marketplace"] = _clean(meta.get("marketplace")) or (
            _clean(rows[0].get("marketplace")) if rows else ""
        )
        core_order = meta.get("coreOrder") if isinstance(meta.get("coreOrder"), list) else []
        meta["coreOrder"] = core_order or list(DEFAULT_RANKING_CORE_ORDER)
        meta["sourceSummary"] = _build_imported_source_summary(rows, meta["coreOrder"], source_name)
    return {"meta": meta, "rows": rows}


def _build_imported_source_summary(
    rows: list[dict[str, Any]],
    core_order: list[Any],
    source_name: str,
) -> list[dict[str, Any]]:
    summary = []
    for index, raw_core in enumerate(core_order):
        core = _clean(raw_core).casefold()
        if not core:
            continue
        matching = [row for row in rows if core in _clean(row.get("searchTerm")).casefold()]
        exact = next(
            (row for row in matching if _clean(row.get("searchTerm")).casefold() == core),
            None,
        )
        best = min(matching, key=lambda row: row["searchFrequencyRank"], default=None)
        summary.append(
            {
                "coreTerm": core,
                "sourceBit": 1 << index,
                "sourceFile": source_name,
                "rowCount": len(matching),
                "exclusiveCount": len(matching),
                "overlapCount": 0,
                "top30000Count": sum(1 for row in matching if row["searchFrequencyRank"] <= 30000),
                "exactRank": exact.get("searchFrequencyRank") if exact else None,
                "bestRank": best.get("searchFrequencyRank") if best else None,
                "bestTerm": best.get("searchTerm") if best else "",
            }
        )
    return summary


def _normalize_ranking_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    term = _ranking_value(row, "searchTerm", "search_term", "搜索词", "关键词", "keyword")
    rank = _ranking_number(
        _ranking_value(row, "searchFrequencyRank", "search_frequency_rank", "搜索词频率排名", "ABA排名", "排名")
    )
    if not _clean(term) or rank is None or rank <= 0:
        return None

    mom = _ranking_number(_ranking_value(row, "rankMoM", "rank_mom", "排名环比", "环比"), percent=True)
    previous_rank = _ranking_number(
        _ranking_value(row, "previousSearchFrequencyRank", "previous_rank", "上期搜索词频率排名", "上期排名")
    )
    if previous_rank is None and mom is not None and mom < 1:
        previous_rank = max(1, round(rank / (1 - mom)))
    asin_list = _ranking_position_values(
        row,
        ("top3AsinList", "top3_asin_list", "前三ASIN"),
        (
            ("#1已点击的ASIN", "asin1", "top1Asin"),
            ("#2已点击的ASIN", "asin2", "top2Asin"),
            ("#3已点击的ASIN", "asin3", "top3Asin"),
        ),
    )
    brand_list = _ranking_position_values(
        row,
        ("topBrands", "top_brands", "前三品牌"),
        (("#1品牌", "brand1", "top1Brand"), ("#2品牌", "brand2", "top2Brand"), ("#3品牌", "brand3", "top3Brand")),
    )
    product_names = _ranking_position_values(
        row,
        ("top3ProductNames", "top3_product_names"),
        (("#1商品名称", "product1"), ("#2商品名称", "product2"), ("#3商品名称", "product3")),
    )
    click_shares = _ranking_position_values(
        row,
        ("top3ClickShares", "top3_click_shares"),
        (("#1点击份额", "clickShare1"), ("#2点击份额", "clickShare2"), ("#3点击份额", "clickShare3")),
        percent=True,
    )
    conversion_shares = _ranking_position_values(
        row,
        ("top3ConversionShares", "top3_conversion_shares"),
        (("#1转化份额", "conversionShare1"), ("#2转化份额", "conversionShare2"), ("#3转化份额", "conversionShare3")),
        percent=True,
    )
    categories = _ranking_position_values(
        row,
        ("top3Categories", "top3_categories"),
        (("#1品类", "category1"), ("#2品类", "category2"), ("#3品类", "category3")),
    )
    monthly_sales = _ranking_position_values(
        row,
        ("top3MonthlySales", "top3_monthly_sales"),
        (("#1月销量", "monthlySales1"), ("#2月销量", "monthlySales2"), ("#3月销量", "monthlySales3")),
        numeric=True,
    )
    return {
        "marketplace": _clean(_ranking_value(row, "marketplace", "站点名称", "站点")) or "美国",
        "searchTerm": _clean(term),
        "searchFrequencyRank": rank,
        "previousSearchFrequencyRank": previous_rank,
        "rankMoM": mom,
        "rankYoY": _ranking_number(_ranking_value(row, "rankYoY", "rank_yoy", "排名同比", "同比"), percent=True),
        "top3AsinClickShare": _ranking_number(
            _ranking_value(row, "top3AsinClickShare", "top3_asin_click_share", "前3ASIN点击量占比", "前三ASIN点击份额"),
            percent=True,
        ) or 0,
        "top3AsinConversionShare": _ranking_number(
            _ranking_value(row, "top3AsinConversionShare", "top3_asin_conversion_share", "前3ASIN转化占比", "前三ASIN转化份额"),
            percent=True,
        ) or 0,
        "top3AsinList": asin_list[:3],
        "topBrands": brand_list[:3],
        "top3ProductNames": product_names,
        "top3ClickShares": click_shares,
        "top3ConversionShares": conversion_shares,
        "top3Categories": categories,
        "top3MonthlySales": monthly_sales,
        "productCount": _ranking_number(_ranking_value(row, "productCount", "product_count", "商品数")),
        "sourceMask": _ranking_number(_ranking_value(row, "sourceMask", "source_mask")) or 0,
        "sourceCount": _ranking_number(_ranking_value(row, "sourceCount", "source_count")) or 0,
    }


def _ranking_position_values(
    row: dict[str, Any],
    collection_aliases: tuple[str, ...],
    position_aliases: tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
    *,
    percent: bool = False,
    numeric: bool = False,
) -> list[Any]:
    collection = _ranking_value(row, *collection_aliases)
    if isinstance(collection, list):
        raw_values = list(collection[:3])
    elif collection not in (None, ""):
        raw_values = _ranking_list(collection)[:3]
    else:
        raw_values = [_ranking_value(row, *aliases) for aliases in position_aliases]
    raw_values.extend([None] * (3 - len(raw_values)))
    if percent:
        return [_ranking_number(value, percent=True) for value in raw_values[:3]]
    if numeric:
        return [_ranking_number(value) for value in raw_values[:3]]
    return [_clean(value) for value in raw_values[:3]]


def _ranking_value(row: dict[str, Any], *aliases: str) -> Any:
    for alias in aliases:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    normalized = {re.sub(r"[\s_\-]+", "", str(key)).casefold(): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(re.sub(r"[\s_\-]+", "", alias).casefold())
        if value not in (None, ""):
            return value
    return None


def _ranking_number(value: Any, *, percent: bool = False) -> float | int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    text = str(value).strip().replace(",", "").replace("#", "")
    is_percentage = text.endswith("%")
    if is_percentage:
        text = text[:-1].strip()
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if percent and is_percentage:
        number /= 100
    return int(number) if number.is_integer() else number


def _ranking_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return _unique_strings(value)
    text = _clean(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return _unique_strings(parsed)
        except json.JSONDecodeError:
            pass
    return _unique_strings(re.split(r"[|;；、]", text))


def _ranking_row_to_dashboard_array(row: dict[str, Any]) -> list[Any]:
    values: list[Any] = [None] * 31
    values[0] = row.get("marketplace")
    values[1] = row.get("searchTerm")
    values[2] = row.get("searchFrequencyRank")
    values[3] = row.get("rankMoM")
    values[4] = row.get("rankYoY")
    values[5] = row.get("top3AsinClickShare")
    values[6] = row.get("top3AsinConversionShare")
    asins = list(row.get("top3AsinList") or [])
    product_names = list(row.get("top3ProductNames") or [])
    click_shares = list(row.get("top3ClickShares") or [])
    conversion_shares = list(row.get("top3ConversionShares") or [])
    brands = list(row.get("topBrands") or [])
    categories = list(row.get("top3Categories") or [])
    monthly_sales = list(row.get("top3MonthlySales") or [])
    for position, index in enumerate((7, 14, 21)):
        values[index] = asins[position] if position < len(asins) else None
        values[index + 1] = product_names[position] if position < len(product_names) else None
        values[index + 2] = click_shares[position] if position < len(click_shares) else None
        values[index + 3] = conversion_shares[position] if position < len(conversion_shares) else None
        values[index + 4] = brands[position] if position < len(brands) else None
        values[index + 5] = categories[position] if position < len(categories) else None
        values[index + 6] = monthly_sales[position] if position < len(monthly_sales) else None
    values[28] = row.get("productCount")
    values[29] = row.get("sourceMask") or 0
    values[30] = row.get("sourceCount") or 0
    return values


def _extract_balanced_json(source: str, start: int) -> str:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise ValueError("看板 DATA 数据未完整闭合。")


def _map_dashboard_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, list) or len(row) < 31 or not row[1]:
        return None
    rank = _finite_number(row[2])
    if rank is None:
        return None
    mom = _finite_number(row[3])
    previous_rank = max(1, round(rank / (1 - mom))) if mom is not None and mom < 1 else None
    return {
        "marketplace": _clean(row[0]),
        "searchTerm": _clean(row[1]),
        "searchFrequencyRank": rank,
        "previousSearchFrequencyRank": previous_rank,
        "rankMoM": mom,
        "rankYoY": _finite_number(row[4]),
        "top3AsinClickShare": _finite_number(row[5]) or 0,
        "top3AsinConversionShare": _finite_number(row[6]) or 0,
        "top3AsinList": [_clean(row[index]) for index in (7, 14, 21)],
        "topBrands": [_clean(row[index]) for index in (11, 18, 25)],
        "top3ProductNames": [_clean(row[index]) for index in (8, 15, 22)],
        "top3ClickShares": [_finite_number(row[index]) for index in (9, 16, 23)],
        "top3ConversionShares": [_finite_number(row[index]) for index in (10, 17, 24)],
        "top3Categories": [_clean(row[index]) for index in (12, 19, 26)],
        "top3MonthlySales": [_finite_number(row[index]) for index in (13, 20, 27)],
        "productCount": _finite_number(row[28]),
        "sourceMask": _finite_number(row[29]) or 0,
        "sourceCount": _finite_number(row[30]) or 0,
    }


def _sellfox_dashboard_path(resource: str) -> str:
    if resource == "status":
        return "/api/connectivity"
    if resource == "marketplaces":
        return "/api/marketplaces"
    if resource == "aba/jobs":
        return "/api/aba/top-keywords/jobs"
    if re.fullmatch(r"aba/jobs/[a-z0-9]+(?:/cancel)?", resource, flags=re.IGNORECASE):
        return "/api/aba/top-keywords/jobs/" + resource.removeprefix("aba/jobs/")
    return ""


def _completion_content(completion: Any) -> str:
    if not isinstance(completion, dict):
        return ""
    choices = completion.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            _clean(item.get("text"))
            for item in content
            if isinstance(item, dict) and _clean(item.get("text"))
        )
    return ""


def _normalize_facts(facts: Any) -> list[dict[str, str]]:
    result = []
    for fact in _object_list(facts, 100):
        value = fact.get("value")
        if isinstance(value, list):
            value = ", ".join(_normalize_strings(value))
        normalized = {
            "key": _clean(fact.get("key")),
            "label": _clean(fact.get("label") or fact.get("key")),
            "value": _clean(value),
            "source": _clean(fact.get("source")) or "vision model",
            "confidence": _normalize_confidence(fact.get("confidence")),
        }
        if normalized["key"] and normalized["value"]:
            result.append(normalized)
    return result


def _parse_json_from_text(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None


def _json_body() -> dict[str, Any] | None:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


def _get_api_key() -> str:
    return _clean(ai_runtime_config().get("api_key"))


def _get_ai_base_url() -> str:
    return (
        _clean(ai_runtime_config().get("base_url"))
        or env("SILICONFLOW_BASE_URL")
        or DEFAULT_SILICONFLOW_BASE_URL
    )


def _get_model() -> str:
    return (
        _clean(ai_runtime_config().get("vision_model"))
        or env("SILICONFLOW_MODEL")
        or DEFAULT_SILICONFLOW_MODEL
    )


def _get_text_model() -> str:
    return (
        _clean(ai_runtime_config().get("text_model"))
        or env("SILICONFLOW_TEXT_MODEL")
        # Do not silently run long-form copy generation on the vision model.
        or DEFAULT_SILICONFLOW_TEXT_MODEL
    )


def _normalize_confidence(value: Any) -> str:
    normalized = _clean(value).lower()
    return normalized if normalized in {"high", "medium", "low"} else "medium"


def _normalize_strings(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [_clean(item) for item in items if _clean(item)]


def _unique_strings(items: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(_clean(item) for item in items if _clean(item)))


def _string_list(items: Any, maximum: int) -> list[str]:
    return _normalize_strings(items)[:maximum]


def _object_list(items: Any, maximum: int) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)][:maximum]


def _finite_number(value: Any) -> int | float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _clamp(value: Any, default: int, minimum: int, maximum: int) -> int:
    number = _finite_number(value)
    return min(max(int(number if number is not None else default), minimum), maximum)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _fit_copy_limit(value: Any, limit: int) -> str:
    cleaned = _clean(value)
    if len(cleaned) <= limit:
        return cleaned
    clipped = cleaned[:limit].rstrip()
    word_break = clipped.rfind(" ")
    if word_break >= int(limit * 0.6):
        clipped = clipped[:word_break]
    return clipped.rstrip(" ,.;:-")


def _uppercase_first_letter(value: Any) -> str:
    text = _clean(value)
    for index, char in enumerate(text):
        if char.isascii() and char.isalpha():
            return f"{text[:index]}{char.upper()}{text[index + 1:]}"
    return text


def _safe_detail(value: Any) -> str:
    return str(value or "")[:800]
