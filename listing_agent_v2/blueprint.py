from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, jsonify, redirect, request, send_from_directory, session, url_for

from listing_agent import blueprint as listing_service


DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist" / "client"
MAX_BODY_BYTES = 2 * 1024 * 1024

listing_agent_v2_bp = Blueprint(
    "listing_agent_v2",
    __name__,
    url_prefix="/listing-agent-v2",
)


@listing_agent_v2_bp.before_request
def _require_login():
    if session.get("feishu_user_id"):
        if request.content_length and request.content_length > MAX_BODY_BYTES:
            return jsonify({"ok": False, "error": "Request body is too large."}), 413
        return None
    if request.path.startswith("/listing-agent-v2/api/"):
        return jsonify({"ok": False, "error": "请先登录后再使用 Listing Studio V2。"}), 401
    next_path = request.full_path.rstrip("?")
    session["post_auth_redirect"] = next_path
    return redirect(url_for("feishu_auth", next=next_path))


@listing_agent_v2_bp.after_request
def _response_headers(response):
    if request.path.startswith("/listing-agent-v2/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@listing_agent_v2_bp.get("")
def index_redirect():
    return redirect(url_for("listing_agent_v2.index"), code=308)


@listing_agent_v2_bp.get("/")
def index():
    if not (DIST_DIR / "index.html").exists():
        return (
            "Listing Studio V2 尚未构建，请先生成前端资源。",
            503,
            {"Content-Type": "text/plain; charset=utf-8"},
        )
    response = send_from_directory(DIST_DIR, "index.html", max_age=0)
    response.headers["Cache-Control"] = "no-store"
    return response


@listing_agent_v2_bp.get("/api/health")
def api_health():
    return jsonify(
        {
            "ok": True,
            "version": "listing-studio-v2",
            "generationApi": "/listing-agent/api/generate-listings",
        }
    )


@listing_agent_v2_bp.post("/api/refine")
def api_refine():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON request body."}), 400

    action = _clean(payload.get("action")).lower()
    field = _clean(payload.get("field")) or "Listing content"
    content = _clean(payload.get("content"))
    instruction = _clean(payload.get("instruction"))
    keywords = [_clean(item) for item in payload.get("keywords", []) if _clean(item)][:12]
    limit = _safe_int(payload.get("limit"), 2000, 40, 4000)
    if action not in {"translate", "optimize"} or not content:
        return jsonify({"ok": False, "error": "Missing refine action or content."}), 400

    api_key = listing_service._get_api_key()
    if not api_key:
        return jsonify({"ok": False, "error": "服务端 AI 配置不可用，请联系管理员。"}), 500

    if action == "translate":
        task = (
            "Translate the Amazon listing field into concise, natural Simplified Chinese for internal review. "
            "Keep product facts and measurements exact. Return only the translation."
        )
    else:
        task = (
            "Rewrite this Amazon listing field in compliant, natural English. Preserve confirmed facts, "
            "avoid unsupported claims, and return only the revised field."
        )
    prompt = "\n".join(
        [
            task,
            f"Field: {field}",
            f"Maximum characters: {limit}",
            f"Priority keywords: {', '.join(keywords) or 'none supplied'}",
            f"User instruction: {instruction or 'Improve clarity and conversion without keyword stuffing.'}",
            "Content:",
            content,
        ]
    )
    result = listing_service._call_siliconflow_with_text_fallbacks(
        api_key,
        {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise Amazon listing editor. Output plain text only.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.25,
            "max_tokens": 900,
        },
    )
    if not result.get("ok"):
        reason = result.get("error") if isinstance(result.get("error"), dict) else {}
        return (
            jsonify(
                {
                    "ok": False,
                    "error": reason.get("message") or listing_service._safe_detail(result.get("text")),
                }
            ),
            502,
        )

    completion = listing_service._parse_json_from_text(result.get("text")) or {}
    refined = _clean(listing_service._completion_content(completion))
    if not refined:
        return jsonify({"ok": False, "error": "AI 未返回可用内容。"}), 502
    refined = _strip_wrapping_quotes(refined)
    if action == "optimize":
        refined = listing_service._fit_copy_limit(refined, limit)
    return jsonify({"ok": True, "content": refined})


@listing_agent_v2_bp.get("/<path:asset_path>")
def asset(asset_path: str):
    if asset_path.startswith("api/"):
        abort(404)
    target = DIST_DIR / asset_path
    if not target.is_file():
        abort(404)
    response = send_from_directory(DIST_DIR, asset_path, max_age=31536000)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return " ".join(str(value).strip().split())


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _strip_wrapping_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1].strip()
    return text
