from __future__ import annotations

import csv
import io
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

import requests
from flask import Blueprint, Response, jsonify, redirect, request, send_from_directory, session, url_for
from openpyxl import load_workbook

from secret_settings import env


ROOT = Path(__file__).resolve().parent
CODE_DIR = ROOT / "code"
DATA_DIR = ROOT / "data"
LOCAL_SETTINGS_PATH = CODE_DIR / ".env.local"
DEFAULT_RANKING_FILE = DATA_DIR / "aba-ranking-export.json"
DEFAULT_RANKING_DASHBOARD_FILE = DATA_DIR / "ABA四核心词综合排名看板_2026-06-28~2026-07-04.html"
ACTIVE_RANKING_FILE = DATA_DIR / "active-aba-ranking.json"

DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_SILICONFLOW_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
DEFAULT_SELLFOX_DASHBOARD_URL = "http://127.0.0.1:8765"
MAX_BODY_BYTES = 26 * 1024 * 1024
MAX_RANKING_IMPORT_FILES = 4
DEFAULT_RANKING_CORE_ORDER = ("lash", "lashes", "eyelash", "eyelashes")
VISION_MODEL_FALLBACKS = (
    DEFAULT_SILICONFLOW_MODEL,
    "Qwen/Qwen3-VL-32B-Instruct",
    "Qwen/Qwen3-VL-30B-A3B-Instruct",
    "zai-org/GLM-4.5V",
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

LISTING_SYSTEM_PROMPT = """You are an Amazon listing copywriter for beauty products. Write compliant, specific English listing copy from confirmed product facts only. Never invent materials, certifications, safety claims, wear time, waterproof performance, reusable count, package contents, or medical claims. Never use any forbidden term supplied by the user. Respect title, bullet, description and backend-search-term limits. Return strict JSON only, with this shape:
{
  "variants": [
    {
      "id": "balanced | style | search",
      "title": "string",
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
_settings_lock = RLock()
_http = requests.Session()
_http.trust_env = False


def _load_local_settings() -> dict[str, str]:
    if not LOCAL_SETTINGS_PATH.exists():
        return {}
    result: dict[str, str] = {}
    try:
        lines = LOCAL_SETTINGS_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            result[key] = value
    return result


_local_settings = _load_local_settings()
_runtime_settings = {
    "api_key": env("SILICONFLOW_API_KEY") or _local_settings.get("SILICONFLOW_API_KEY", ""),
    "model": env("SILICONFLOW_MODEL") or _local_settings.get("SILICONFLOW_MODEL", "") or DEFAULT_SILICONFLOW_MODEL,
    "text_model": env("SILICONFLOW_TEXT_MODEL") or _local_settings.get("SILICONFLOW_TEXT_MODEL", ""),
}


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
    if source_path != DEFAULT_RANKING_FILE:
        try:
            template = DEFAULT_RANKING_DASHBOARD_FILE.read_text(encoding="utf-8-sig")
            dashboard_data = _load_ranking_data(source_path)
            default_meta = _load_ranking_data(DEFAULT_RANKING_FILE).get("meta", {})
            meta = {
                **(default_meta if isinstance(default_meta, dict) else {}),
                **(dashboard_data.get("meta") if isinstance(dashboard_data.get("meta"), dict) else {}),
            }
            payload = {
                "meta": meta,
                "rows": [
                    _ranking_row_to_dashboard_array(row)
                    for row in dashboard_data.get("rows", [])
                    if isinstance(row, dict)
                ],
            }
            original_json = _extract_dashboard_json(template)
            serialized_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            serialized_payload = (
                serialized_payload.replace("&", "\\u0026")
                .replace("<", "\\u003c")
                .replace(">", "\\u003e")
            )
            template = template.replace(original_json, serialized_payload, 1)
            response = Response(template, mimetype="text/html")
            response.headers["Cache-Control"] = "no-store"
            return response
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    response = send_from_directory(
        DEFAULT_RANKING_DASHBOARD_FILE.parent,
        DEFAULT_RANKING_DASHBOARD_FILE.name,
        max_age=0,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _send_code_file(filename: str):
    response = send_from_directory(CODE_DIR, filename, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    return response


@listing_agent_bp.route("/api/health", methods=["GET", "HEAD"])
def api_health():
    return jsonify(
        {
            "ok": True,
            "model": _get_model(),
            "hasApiKey": bool(_get_api_key()),
        }
    )


@listing_agent_bp.route("/api/settings", methods=["GET", "HEAD", "POST"])
def api_settings():
    if request.method in {"GET", "HEAD"}:
        return jsonify(_public_settings())

    payload = _json_body()
    if payload is None:
        return jsonify({"error": "Invalid JSON request body."}), 400
    api_key = _clean(payload.get("apiKey"))
    model = _clean(payload.get("model")) or DEFAULT_SILICONFLOW_MODEL
    text_model = _clean(payload.get("textModel"))
    with _settings_lock:
        if api_key:
            _runtime_settings["api_key"] = api_key
        _runtime_settings["model"] = model
        _runtime_settings["text_model"] = text_model
        if not _runtime_settings["api_key"]:
            return jsonify({"error": "SILICONFLOW_API_KEY is required before image extraction can run."}), 400
        try:
            _save_local_settings()
        except OSError as exc:
            return jsonify({"error": f"配置保存失败：{_safe_detail(exc)}"}), 500
    return jsonify(_public_settings())


@listing_agent_bp.post("/api/extract-image")
def api_extract_image():
    api_key = _get_api_key()
    if not api_key:
        return jsonify({"error": "SILICONFLOW_API_KEY is not set. Configure it before image extraction."}), 500

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
                    "model": result.get("model") or _get_model(),
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
                "needsConfirmation": ["视觉模型已返回内容，但无法解析为 JSON。请手动填写图片可见事实。"],
                "doNotInfer": DO_NOT_INFER,
                "source": f"SiliconFlow {result.get('model')} returned unparsed text.",
            }
        )

    return jsonify(
        {
            "facts": _normalize_facts(parsed.get("facts")),
            "needsConfirmation": _normalize_strings(parsed.get("needsConfirmation") or parsed.get("needs")),
            "doNotInfer": _unique_strings(
                _normalize_strings(parsed.get("doNotInfer") or parsed.get("blocked")) + DO_NOT_INFER
            ),
            "source": f"SiliconFlow {result.get('model')}",
        }
    )


@listing_agent_bp.post("/api/generate-listings")
def api_generate_listings():
    api_key = _get_api_key()
    if not api_key:
        return jsonify({"error": "SILICONFLOW_API_KEY is not set. Configure it before generating AI listings."}), 500
    payload = _json_body()
    if payload is None:
        return jsonify({"error": "Invalid JSON request body."}), 400
    prompt_payload = _normalize_listing_generation_input(payload)
    if not prompt_payload["product"]["type"]:
        return jsonify({"error": "Confirmed product facts are required before generating listings."}), 400

    model_payload = {
        "model": _get_text_model(),
        "temperature": 0.65,
        "max_tokens": 6200,
        "messages": [
            {"role": "system", "content": LISTING_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
        ],
    }
    result = _call_siliconflow(api_key, model_payload)
    if not result.get("ok"):
        reason = result.get("error") if isinstance(result.get("error"), dict) else {}
        return (
            jsonify(
                {
                    "error": "SiliconFlow text generation failed",
                    "siliconFlowStatus": result.get("status", 0),
                    "siliconFlowCode": reason.get("code", ""),
                    "siliconFlowMessage": reason.get("message") or _safe_detail(result.get("text")),
                    "model": result.get("model"),
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
                    "model": result.get("model"),
                    "detail": _safe_detail(_completion_content(completion)),
                }
            ),
            502,
        )
    return jsonify({"ok": True, "model": result.get("model"), "variants": variants})


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
                    "message": "无法读取已绑定的赛虎 ABA 看板文件。",
                    "detail": _safe_detail(exc),
                }
            ),
            500,
        )


@listing_agent_bp.post("/api/sellfox/import-ranking")
def api_sellfox_import_ranking():
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
        ACTIVE_RANKING_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = ACTIVE_RANKING_FILE.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(dashboard_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(ACTIVE_RANKING_FILE)
        meta = dashboard_data.get("meta", {})
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
                    "message": f"无法连接赛虎广告看板（{base_url}）。请先启动它的本地服务。",
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


def _call_siliconflow(api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{(env('SILICONFLOW_BASE_URL') or DEFAULT_SILICONFLOW_BASE_URL).rstrip('/')}/chat/completions"
    try:
        response = _http.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=(10, 180),
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
    return code == 30003 or "model disabled" in message or "model not" in message


def _normalize_listing_generation_input(data: dict[str, Any]) -> dict[str, Any]:
    product = data.get("product") if isinstance(data.get("product"), dict) else {}
    keywords = data.get("keywords") if isinstance(data.get("keywords"), dict) else {}
    compliance = data.get("compliance") if isinstance(data.get("compliance"), dict) else {}
    skill = data.get("skill") if isinstance(data.get("skill"), dict) else {}
    limits = data.get("limits") if isinstance(data.get("limits"), dict) else {}

    def terms(items: Any) -> list[dict[str, Any]]:
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
        return normalized

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
            "growthPriority": terms(keywords.get("growthPriority")),
            "conversionPriority": terms(keywords.get("conversionPriority")),
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
            "title": _clamp(limits.get("title"), 75, 30, 200),
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
        variant = {
            "id": variant_id,
            "title": _clean(value.get("title")),
            "highlights": _string_list(value.get("highlights"), 3),
            "bullets": _string_list(value.get("bullets"), 5),
            "description": _clean(value.get("description")),
            "searchTerms": _clean(value.get("searchTerms")),
            "reasons": _string_list(value.get("reasons"), 4),
        }
        if (
            variant["title"]
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
    configured = env("SELLFOX_RANKING_FILE")
    return Path(configured) if configured else DEFAULT_RANKING_FILE


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


def _public_settings() -> dict[str, Any]:
    return {
        "hasApiKey": bool(_get_api_key()),
        "model": _get_model(),
        "textModel": _get_text_model(),
    }


def _get_api_key() -> str:
    with _settings_lock:
        return _runtime_settings["api_key"]


def _get_model() -> str:
    with _settings_lock:
        return _runtime_settings["model"] or DEFAULT_SILICONFLOW_MODEL


def _get_text_model() -> str:
    with _settings_lock:
        return _runtime_settings["text_model"] or _runtime_settings["model"] or DEFAULT_SILICONFLOW_MODEL


def _save_local_settings() -> None:
    lines = [
        f"SILICONFLOW_API_KEY={_env_value(_runtime_settings['api_key'])}",
        f"SILICONFLOW_MODEL={_env_value(_runtime_settings['model'])}",
        f"SILICONFLOW_TEXT_MODEL={_env_value(_runtime_settings['text_model'])}",
    ]
    LOCAL_SETTINGS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _env_value(value: Any) -> str:
    return str(value or "").replace("\r", "").replace("\n", "").strip()


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


def _safe_detail(value: Any) -> str:
    return str(value or "")[:800]
