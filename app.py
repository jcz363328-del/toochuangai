import asyncio
import concurrent.futures
import time
from threading import Lock, Thread
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_from_directory, send_file
from openai import OpenAI
from datetime import datetime, timedelta, date
from collections import Counter
import sqlite3
import os
import json
import re
import base64
import hashlib
import mimetypes
import requests
import importlib.util
from functools import partial
from secret_settings import ai_runtime_config, env, relocate_storage_path, sql_server_config
from tools import ai_chat_complete, is_mobile_user_agent, safe_print as _safe_debug_print
from html import escape as html_escape, unescape as html_unescape
from html.parser import HTMLParser
from urllib.parse import urlparse, parse_qs, unquote, quote
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from review_analysis import review_analysis_bp
from eyelash_analytics import eyelash_analytics_bp
from influencer_management import influencer_management_bp
from model_management import model_management_bp
from innovation_proposals import innovation_proposals_bp
from innovation_blueprint import innovation_bp
from innovation.config import APP_CONFIG as INNOVATION_APP_CONFIG
from tk_total_dashboard import tk_dashboard_bp, dashboard_82_users, dashboard_88_users, dashboard_90_users
from TK_BD_ZhiBiao import bd_metrics_bp
from department_permissions import permission_manager, require_permission, get_feishu_auth_url, FEISHU_CONFIG, \
    handle_feishu_event, PERMISSION_CONFIG
from bjc import sf_db, dui_db
from innovation.message_service import MessageService
from shenzhen_total import compute_shenzhen_expenses
from knowledge_base_service import knowledge_base_bp, kb_service
from feishu_skill_bridge import bootstrap_lark_cli_skills_env, get_skill_root_candidates
from seedance_web import seedance_web_bp
from yangban_inventory import yangban_inventory_bp

app = Flask(__name__)
app.secret_key = env("FLASK_SECRET_KEY", "change-this-secret-key")  # 用于session加密
app.config['JSON_AS_ASCII'] = False  # 支持中文JSON响应
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024
app.config.setdefault('MAX_FORM_MEMORY_SIZE', 50 * 1024 * 1024)
app.config.setdefault('MAX_FORM_PARTS', 5000)

_cloud_documents_agent = None
_amazon_reply_service = None
_cloud_doc_scoring_cache = {}
_cloud_doc_scoring_cache_ttl_seconds = 300
_cloud_doc_scoring_cache_lock = Lock()
_bitable_cache = {}
_bitable_cache_ttl_seconds = 300
_bitable_cache_lock = Lock()
_feishu_http = requests.Session()
_feishu_http.trust_env = False
_TAVILY_API_KEY = env("TAVILY_API_KEY")
_GOOGLE_CSE_API_KEY = env("GOOGLE_CSE_API_KEY")
_GOOGLE_CSE_CX = env("GOOGLE_CSE_CX")
_STRATEGY_TRAINING_VIDEO_DIR = r"D:\tuchuangai\3.17-战略分解培训"
_ROCOCO_TRAINING_VIDEO_DIR = r"D:\tuchuangai\洛可可培训"
_CHUANSHI_TRAINING_ROOT_DIR = r"D:\tuchuangai\2026-7-9传世启动仪式"
_CHUANSHI_TRAINING_IMAGE_DIR = os.path.join(_CHUANSHI_TRAINING_ROOT_DIR, "图片")
_CHUANSHI_TRAINING_VIDEO_DIR = os.path.join(_CHUANSHI_TRAINING_ROOT_DIR, "视频")
_ANNUAL_MOMENTS_IMAGE_DIR = r"D:\tuchuangai\2026-06-18年会图片"
_ANNUAL_MOMENTS_VIDEO_DIR = r"D:\tuchuangai\2026-06-18年会视频"
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".heic", ".heif"}
_PUBLIC_DOWNLOAD_APR16_VIDEO = r"D:\tuchuangai\4月16日.mp4"
_XIAOTU_SHARED_DOCS = []
_xiaotu_doc_list_cache = {}
_xiaotu_doc_list_cache_ttl_seconds = 300
_xiaotu_doc_list_cache_lock = Lock()
_XIAOTU_REPORT_CACHE_TABLE_PRIMARY = "baogao_huancun"
_XIAOTU_REPORT_CACHE_TABLE_FALLBACK = "baogao_huancunbiao"
_XIAOTU_NOTIFY_ID_TABLE_PRIMARY = "feishu_id_tc"
_XIAOTU_NOTIFY_ID_TABLE_FALLBACK = "feishu_id"
_XIAOTU_NOTIFY_CACHE_PREFIX = "__xiaotu_notify_targets_v2__:"
_XIAOTU_REPORT_EDIT_READY_SESSION_KEY = "xiaotu_report_edit_ready"
_XIAOTU_REPORT_EDIT_READY_TTL_SECONDS = 2 * 60 * 60
_XIAOTU_REPORT_CENTER_PUBLIC_URL = (
    os.environ.get("XIAOTU_REPORT_CENTER_PUBLIC_URL")
    or "http://223.78.73.100:8000/dashboard/xiaotu-report-center"
).strip()
_XIAOTU_REPORT_HISTORY_ALL_UPLOAD_USERS = {
    "陶晓飞",
    "周俊成",
    "毕景春",
}
_XIAOTU_REPORT_HISTORY_OPERATION_ONLY_USERS = {
    "刘蓉蓉",
    "孙洁",
    "侯梁",
}
_XIAOTU_REPORT_HISTORY_USER_DEPARTMENT_SCOPE = {
    "大张雯": ("运营三部",),
}
_XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES = (
    "运营一部",
    "运营二部",
    "运营三部",
    "运营六部",
    "运营七部",
)
_XIAOTU_REPORT_HISTORY_DEBUG_USER = "周俊成"
_xiaotu_notify_department_users_cache = {}
_xiaotu_notify_department_users_cache_ttl_seconds = 300
_xiaotu_notify_department_users_cache_lock = Lock()
_XIAOTU_REPORT_REMINDER_ENABLED = False  # temporary disabled for entry timeout debugging
_xiaotu_report_reminder_thread_started = False
_xiaotu_report_reminder_lock = Lock()
_xiaotu_report_reminder_sent_marks = {}
_xiaotu_user_open_id_cache = {}
_LASHFORGE_PUBLIC_URL = (os.environ.get("LASHFORGE_PUBLIC_URL") or "http://www.toochuangai.com:8501/lashforge").strip().rstrip("/")
_LASHFORGE_HEALTH_URL = (os.environ.get("LASHFORGE_HEALTH_URL") or "http://127.0.0.1:8501/lashforge/").strip()
_LASHFORGE_AUTH_TOKEN_SALT = "lashforge-auth-v1"
_lashforge_watchdog_lock = Lock()
_lashforge_watchdog_last_attempt = 0.0


def _get_cloud_documents_agent():
    global _cloud_documents_agent
    if _cloud_documents_agent is not None:
        return _cloud_documents_agent
    file_path = os.path.join(os.path.dirname(__file__), "Cloud documents.py")
    spec = importlib.util.spec_from_file_location("cloud_documents_module", file_path)
    if spec is None or spec.loader is None:
        _cloud_documents_agent = None
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    agent_cls = getattr(module, "CloudDocumentsScoringAgent", None)
    if agent_cls is None:
        _cloud_documents_agent = None
        return None
    _cloud_documents_agent = agent_cls(
        access_token_getter=permission_manager.get_access_token,
        ocr_image_func=_ocr_images_bytes_with_ai,
        app_id=str(FEISHU_CONFIG.get("app_id") or ""),
        app_secret=str(FEISHU_CONFIG.get("app_secret") or "")
    )
    return _cloud_documents_agent


def _is_mobile_request():
    return is_mobile_user_agent(request.headers.get('User-Agent'))


def _is_feishu_request():
    ua = (request.headers.get('User-Agent') or '').lower()
    if any(k in ua for k in ('lark', 'feishu', 'larkoffice')):
        return True
    return any(
        request.headers.get(header)
        for header in (
            'X-Lark-User-Id',
            'X-Lark-Open-Id',
            'X-Lark-Union-Id',
            'X-Lark-User-Access-Token',
            'X-Plugin-Token',
            'X-User-Plugin-Token',
        )
    )


def _debug_elapsed_ms(start_ts):
    try:
        return round((time.perf_counter() - float(start_ts or 0)) * 1000, 1)
    except Exception:
        return -1


def _debug_log_elapsed(label, start_ts, **kwargs):
    fields = {"elapsed_ms": _debug_elapsed_ms(start_ts)}
    for key, value in kwargs.items():
        fields[key] = value
    try:
        _safe_debug_print(f"[perf] {label}: {json.dumps(fields, ensure_ascii=False)}")
    except Exception:
        _safe_debug_print(f"[perf] {label}: {fields}")


def _xiaotu_remember_user_open_id(user_name, open_id):
    name = str(user_name or "").strip()
    oid = str(open_id or "").strip()
    if not name or not oid.startswith("ou_"):
        return
    _xiaotu_user_open_id_cache[name] = oid
    compact_name = re.sub(r"\s+", "", name)
    if compact_name:
        _xiaotu_user_open_id_cache[compact_name] = oid


def _xiaotu_get_cached_open_id_by_name(user_name):
    name = str(user_name or "").strip()
    if not name:
        return ""
    oid = str(_xiaotu_user_open_id_cache.get(name) or "").strip()
    if oid.startswith("ou_"):
        return oid
    compact_name = re.sub(r"\s+", "", name)
    oid = str(_xiaotu_user_open_id_cache.get(compact_name) or "").strip()
    return oid if oid.startswith("ou_") else ""


def _xiaotu_report_history_can_view_all_uploads(user_name):
    return str(user_name or "").strip() in _XIAOTU_REPORT_HISTORY_ALL_UPLOAD_USERS


def _xiaotu_get_report_history_scope(user_name, debug_mode=None):
    name = str(user_name or "").strip()
    allowed_department_names = []
    normalized_debug_mode = str(debug_mode or "").strip().lower()
    if normalized_debug_mode == "all_uploads":
        return {
            "can_view_all_uploads": True,
            "restricted_to_allowed_departments": False,
            "allowed_department_names": [],
            "debug_mode": "all_uploads",
        }
    if normalized_debug_mode == "operation_only":
        return {
            "can_view_all_uploads": False,
            "restricted_to_allowed_departments": True,
            "allowed_department_names": list(_XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES),
            "debug_mode": "operation_only",
        }
    if normalized_debug_mode == "self_only":
        return {
            "can_view_all_uploads": False,
            "restricted_to_allowed_departments": False,
            "allowed_department_names": [],
            "debug_mode": "self_only",
        }
    if name in _XIAOTU_REPORT_HISTORY_USER_DEPARTMENT_SCOPE:
        allowed_department_names = list(_XIAOTU_REPORT_HISTORY_USER_DEPARTMENT_SCOPE.get(name) or [])
    elif name in _XIAOTU_REPORT_HISTORY_OPERATION_ONLY_USERS:
        allowed_department_names = list(_XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES)
    return {
        "can_view_all_uploads": bool(name in _XIAOTU_REPORT_HISTORY_ALL_UPLOAD_USERS),
        "restricted_to_allowed_departments": bool(allowed_department_names),
        "allowed_department_names": allowed_department_names,
        "debug_mode": "current",
    }


def _xiaotu_get_report_history_debug_options(user_name):
    name = str(user_name or "").strip()
    if name != _XIAOTU_REPORT_HISTORY_DEBUG_USER:
        return []
    return [
        {"value": "current", "label": "当前真实权限"},
        {"value": "self_only", "label": "普通用户视角"},
        {"value": "all_uploads", "label": "全量查看视角"},
        {"value": "operation_only", "label": "运营部门受限视角"},
    ]


def _xiaotu_build_name_match_clause(column_name, names):
    exact_names = []
    compact_names = []
    seen_exact = set()
    seen_compact = set()
    for raw_name in (names or []):
        name = str(raw_name or "").strip()
        if not name:
            continue
        if name not in seen_exact:
            seen_exact.add(name)
            exact_names.append(name)
        compact_name = re.sub(r"\s+", "", name)
        if compact_name and compact_name not in seen_compact:
            seen_compact.add(compact_name)
            compact_names.append(compact_name)
    clauses = []
    if exact_names:
        exact_sql = ", ".join([f"N'{_xiaotu_sql_escape(name)}'" for name in exact_names])
        clauses.append(f"{column_name} IN ({exact_sql})")
    if compact_names:
        compact_sql = ", ".join([f"N'{_xiaotu_sql_escape(name)}'" for name in compact_names])
        clauses.append(f"REPLACE(REPLACE({column_name}, N' ', N''), CHAR(9), N'') IN ({compact_sql})")
    if not clauses:
        return ""
    return "(" + " OR ".join(clauses) + ")"


def _xiaotu_build_name_scope_clause(column_name, names):
    base_clause = _xiaotu_build_name_match_clause(column_name, names)
    loose_clauses = []
    seen = set()
    for raw_name in (names or []):
        name = str(raw_name or "").strip()
        compact_name = re.sub(r"\s+", "", name)
        for one in (name, compact_name):
            if not one or len(one) < 2 or one in seen:
                continue
            seen.add(one)
            esc_one = _xiaotu_sql_escape(one)
            loose_clauses.append(f"{column_name} LIKE N'%%{esc_one}%%'")
            loose_clauses.append(
                f"REPLACE(REPLACE({column_name}, N' ', N''), CHAR(9), N'') LIKE N'%%{esc_one}%%'"
            )
    clauses = [base_clause] if base_clause else []
    clauses.extend(loose_clauses)
    if not clauses:
        return ""
    return "(" + " OR ".join(clauses) + ")"


def _xiaotu_collect_notify_user_names_by_department_names(department_names):
    target_names = []
    target_seen = set()
    for raw_name in (department_names or []):
        dept_name = str(raw_name or "").strip()
        if not dept_name or dept_name in target_seen:
            continue
        target_seen.add(dept_name)
        target_names.append(dept_name)
    if not target_names:
        return []

    all_departments = _xiaotu_list_notify_departments()
    wanted_ids = []
    wanted_name_set = set(target_names)
    for one in (all_departments or []):
        if not isinstance(one, dict):
            continue
        dept_name = str(one.get("department_name") or "").strip()
        dept_id = str(one.get("department_id") or "").strip()
        if dept_name in wanted_name_set and dept_id and dept_id not in wanted_ids:
            wanted_ids.append(dept_id)
    if not wanted_ids:
        return []

    user_names = []
    seen_names = set()
    for dept_id in wanted_ids:
        for one in (_xiaotu_list_notify_users_current_app_cached(dept_id) or []):
            if not isinstance(one, dict):
                continue
            name = str(one.get("name") or "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            user_names.append(name)
    return user_names


def _get_func_field(func, key):
    if isinstance(func, dict):
        return func.get(key)
    return getattr(func, key, None)


def _build_mobile_function_cards(accessible_functions):
    cards = []
    seen = set()
    for func in (accessible_functions or []):
        function_name = str(_get_func_field(func, 'function_name') or '').strip()
        display_name = str(_get_func_field(func, 'name') or function_name or '功能').strip()
        if not function_name or function_name in seen:
            continue
        seen.add(function_name)

        href = ''
        icon = 'fa-solid fa-grid-2'
        if function_name == 'innovation_proposals':
            href = url_for('innovation_proposals.innovation_proposals')
            icon = 'fa-solid fa-lightbulb'
        elif function_name == 'tk_project_group':
            href = url_for('tk_project')
            icon = 'fa-solid fa-store'
        elif function_name == 'xiaotu_qa':
            href = url_for('dashboard_xiaotu_report_center_mobile')
            display_name = '报告智能体'
            icon = 'fa-solid fa-file-lines'
        elif function_name == 'general_office':
            href = url_for('general_office')
            icon = 'fa-solid fa-building'
        elif function_name == 'operation_dept_1':
            href = url_for('operation_dept_1')
            icon = 'fa-solid fa-chart-line'
        elif function_name == 'operation_dept_2':
            href = url_for('operation_dept_2')
            icon = 'fa-solid fa-chart-line'
        elif function_name == 'operation_dept_3':
            href = url_for('operation_dept_3')
            icon = 'fa-solid fa-chart-line'
        elif function_name == 'operation_dept_6':
            href = url_for('operation_dept_6')
            icon = 'fa-solid fa-chart-line'
        elif function_name == 'photography_dept':
            href = url_for('photography_dept')
            icon = 'fa-solid fa-camera'
        elif function_name == 'ai_dept':
            href = url_for('ai_modules')
            icon = 'fa-solid fa-brain'
        elif function_name == 'amazon_reply_agent':
            href = url_for('amazon_reply_agent')
            display_name = '亚马逊站内信回复智能体'
            icon = 'fa-solid fa-envelope-open-text'
        elif function_name == 'finance_dept':
            href = url_for('finance_modules')
            icon = 'fa-solid fa-coins'
        elif function_name == 'procurement_dept':
            href = url_for('procurement_dept')
            icon = 'fa-solid fa-cart-shopping'
        elif function_name == 'hr_admin_dept':
            href = url_for('hr_admin_modules')
            icon = 'fa-solid fa-users'
        elif function_name == 'tech_dept':
            href = url_for('tech_dept')
            icon = 'fa-solid fa-microchip'
        elif function_name == 'visual_design_dept':
            href = url_for('visual_design_dept')
            icon = 'fa-solid fa-palette'
        elif function_name == 'newcomer_group':
            href = url_for('newcomer_group')
            icon = 'fa-solid fa-seedling'
        elif function_name == 'shenzhen_dept':
            href = url_for('shenzhen_dept')
            icon = 'fa-solid fa-location-dot'
        elif function_name == 'model_queue':
            href = url_for('model_management.queue')
            icon = 'fa-solid fa-user-clock'

        cards.append({
            'name': display_name,
            'href': href,
            'icon': icon,
            'available': bool(href)
        })

    cards.append({
        'name': '年会精彩瞬间',
        'href': url_for('annual_moments'),
        'icon': 'fa-solid fa-images',
        'available': True
    })

    cards.append({
        'name': 'Seedance 视频生成',
        'href': url_for('seedance_web.seedance_web_index'),
        'icon': 'fa-solid fa-film',
        'available': True
    })

    cards.append({
        'name': '培训视频',
        'href': url_for('training_videos'),
        'icon': 'fa-solid fa-circle-play',
        'available': True
    })
    return cards


def _build_lashforge_auth_token(user_name):
    normalized_name = str(user_name or '').strip().lower()
    if not normalized_name:
        return ''
    raw = f"{_LASHFORGE_AUTH_TOKEN_SALT}:{normalized_name}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _get_lashforge_public_base_url():
    env_url = str(os.environ.get("LASHFORGE_PUBLIC_URL") or "").strip().rstrip('/')
    if env_url:
        return env_url

    fallback_url = (_LASHFORGE_PUBLIC_URL or "http://www.toochuangai.com:8501/lashforge").rstrip('/')
    fallback_parts = urlparse(fallback_url)
    scheme = fallback_parts.scheme or "http"
    port = fallback_parts.port or 8501
    host_text = str(
        request.headers.get('X-Forwarded-Host')
        or request.headers.get('Host')
        or request.host
        or ""
    ).split(',')[0].strip()

    if not host_text:
        return fallback_url

    parsed_host = urlparse('//' + host_text)
    hostname = parsed_host.hostname or host_text.split(':')[0].strip()
    if not hostname:
        return fallback_url
    if ':' in hostname and not hostname.startswith('['):
        hostname = f'[{hostname}]'
    return f"{scheme}://{hostname}:{port}/lashforge"


def _build_lashforge_entry_url(user_name=''):
    base_url = _get_lashforge_public_base_url().rstrip('/')
    normalized_name = _normalize_feishu_user_name(user_name, fallback='')
    if not normalized_name:
        return f"{base_url}/?embed=true"
    auth_token = _build_lashforge_auth_token(normalized_name)
    return f"{base_url}/?auth_user={quote(normalized_name)}&auth_token={auth_token}&embed=true"


def _is_lashforge_reachable(timeout=1.5):
    try:
        response = requests.get(_LASHFORGE_HEALTH_URL, timeout=timeout)
        return 200 <= response.status_code < 400
    except Exception:
        return False


def _ensure_lashforge_watchdog_started():
    global _lashforge_watchdog_last_attempt
    if _is_lashforge_reachable():
        return True

    with _lashforge_watchdog_lock:
        now = time.time()
        if now - _lashforge_watchdog_last_attempt < 30:
            return False
        _lashforge_watchdog_last_attempt = now

        script_dir = os.path.join(os.path.dirname(__file__), "图片")
        script_path = os.path.join(script_dir, "xiaoha_watchdog.ps1")
        if not os.path.exists(script_path):
            app.logger.warning("XiaoHa watchdog script not found: %s", script_path)
            return False

        try:
            import subprocess

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Hidden",
                    "-File",
                    script_path,
                ],
                cwd=script_dir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            return True
        except Exception as exc:
            app.logger.warning("Failed to start XiaoHa watchdog: %s", exc)
            return False


def _normalize_dashboard_functions(accessible_functions):
    normalized = []
    for idx, func in enumerate(accessible_functions or []):
        if isinstance(func, dict):
            one = dict(func)
        else:
            one = {
                'function_name': str(getattr(func, 'function_name', '') or '').strip(),
                'name': str(getattr(func, 'name', '') or '').strip(),
                'description': str(getattr(func, 'description', '') or '').strip()
            }
        fname = str(one.get('function_name') or '').strip()
        if fname == 'xiaotu_qa':
            one['name'] = '报告智能体'
            desc = str(one.get('description') or '').strip()
            if not desc:
                one['description'] = '周报/月报提交与生成'
        one['_order_index'] = idx
        normalized.append(one)

    order_priority = {
        'innovation_proposals': 10,
        'xiaotu_qa': 11,
    }
    normalized.sort(key=lambda x: (order_priority.get(str(x.get('function_name') or '').strip(), 100), int(x.get('_order_index', 0))))
    for one in normalized:
        one.pop('_order_index', None)
    return normalized


def _normalize_feishu_user_name(raw_name, fallback='用户'):
    name = str(raw_name or '').strip()
    if not name:
        return str(fallback or '用户')
    # 去掉“姓名（部门）/ 姓名(部门)”后缀，保留纯姓名
    name = re.sub(r'\s*[（(][^（）()]{1,40}[）)]\s*$', '', name).strip()
    if not name:
        return str(fallback or '用户')
    return name


def _xiaotu_is_invalid_feishu_name(raw_name):
    name = str(raw_name or "").strip()
    if not name:
        return True
    low = name.lower()
    if low in {"用户", "飞书用户", "lark user", "匿名用户", "unknown", "unknown user"}:
        return True
    if re.match(r"^(ou_|on_|od_|u-|union_|cli_)", name, flags=re.I):
        return True
    if re.match(r"^[a-z0-9][a-z0-9_\-]{10,}$", name, flags=re.I) and "_" in name:
        return True
    return False


def _resolve_feishu_user_name(user_info, fallback='用户'):
    info = user_info if isinstance(user_info, dict) else {}
    candidates = [
        info.get('name'),
        info.get('display_name'),
        info.get('nick_name'),
        info.get('nickname'),
        info.get('en_name'),
    ]
    for one in candidates:
        name = _normalize_feishu_user_name(one, fallback='')
        if name and name not in {'飞书用户', '用户', 'Lark User'}:
            return name
    for key in ('enterprise_email', 'email', 'user_principal_name'):
        mail = str(info.get(key) or '').strip()
        if '@' in mail:
            local = mail.split('@', 1)[0].strip()
            if local:
                return local
    return _normalize_feishu_user_name(info.get('name'), fallback=fallback)


def _clear_feishu_identity_session():
    for k in [
        'feishu_user_id', 'feishu_open_id', 'feishu_user_name', 'feishu_user_email', 'feishu_email',
        'feishu_avatar', 'feishu_user_access_token', 'feishu_user_refresh_token',
        'feishu_user_access_token_expire_at', 'preloaded_departments', 'preloaded_functions',
        'preload_time', 'user_department', 'login_time'
    ]:
        session.pop(k, None)


def _bind_feishu_session(user_info, user_access_token=''):
    info = dict(user_info or {})
    token = str(user_access_token or info.get('user_access_token') or '').strip()
    session['feishu_user_id'] = info.get('open_id') or info.get('user_id') or ''
    session['feishu_open_id'] = info.get('open_id') or info.get('user_id') or ''
    session['feishu_user_name'] = _resolve_feishu_user_name(info, fallback='用户')
    session['feishu_user_email'] = info.get('email', '') or info.get('enterprise_email', '')
    session['feishu_email'] = info.get('email', '') or info.get('enterprise_email', '')
    session['feishu_avatar'] = info.get('avatar_url', '') or info.get('avatar', '')
    session['feishu_user_access_token'] = token
    if info.get('user_refresh_token'):
        session['feishu_user_refresh_token'] = str(info.get('user_refresh_token') or '')
    token_expires_in = int(info.get('user_token_expires_in') or 0)
    if token_expires_in > 0:
        session['feishu_user_access_token_expire_at'] = (datetime.now() + timedelta(seconds=token_expires_in)).isoformat()
    session['login_time'] = datetime.now()
    session['feishu_identity_app_id'] = str(FEISHU_CONFIG.get('app_id') or '')
    session.permanent = True
    app.permanent_session_lifetime = timedelta(hours=24)
    _xiaotu_remember_user_open_id(session.get('feishu_user_name'), session.get('feishu_open_id'))


def _sync_feishu_identity_via_current_app(force_refresh=False):
    """统一通过当前飞书应用的 user_access_token 获取真实用户信息。"""
    sync_started_at = time.perf_counter()
    request_token = str(request.headers.get('X-Lark-User-Access-Token') or '').strip()
    auth_header = str(request.headers.get('Authorization') or '').strip()
    if (not request_token) and auth_header.lower().startswith('bearer '):
        request_token = auth_header[7:].strip()
    session_token = str(session.get('feishu_user_access_token') or '').strip()
    current_user_id = str(session.get('feishu_user_id') or '').strip()
    current_app_id = str(session.get('feishu_identity_app_id') or '').strip()
    expected_app_id = str(FEISHU_CONFIG.get('app_id') or '').strip()

    if request_token and session_token and request_token != session_token:
        _safe_debug_print("⚠️ 当前请求 user_access_token 与会话 token 不一致，重绑为当前请求用户")
        _clear_feishu_identity_session()
        session_token = ''
        current_user_id = ''

    token = request_token or session_token
    if not token:
        _safe_debug_print("ℹ️ 当前请求和会话中都没有 user_access_token，无法通过当前应用识别用户")
        _debug_log_elapsed(
            "sync_feishu_identity_skip_no_token",
            sync_started_at,
            force_refresh=bool(force_refresh),
            has_request_token=bool(request_token),
            has_session_token=bool(session_token)
        )
        return None

    if (not force_refresh) and current_user_id and session_token and token == session_token and current_app_id == expected_app_id:
        _debug_log_elapsed(
            "sync_feishu_identity_session_hit",
            sync_started_at,
            force_refresh=bool(force_refresh),
            user_id=current_user_id,
            app_id=current_app_id,
            has_request_token=bool(request_token)
        )
        return {
            'user_id': current_user_id,
            'open_id': str(session.get('feishu_open_id') or current_user_id),
            'name': str(session.get('feishu_user_name') or ''),
            'email': str(session.get('feishu_user_email') or session.get('feishu_email') or ''),
            'user_access_token': token
        }

    user_info_lookup_started_at = time.perf_counter()
    user_info = permission_manager.get_user_info_by_token(token)
    _debug_log_elapsed(
        "sync_feishu_identity_remote_lookup",
        user_info_lookup_started_at,
        force_refresh=bool(force_refresh),
        has_request_token=bool(request_token),
        token_source=("request_header" if request_token else "session"),
        ok=isinstance(user_info, dict)
    )
    if not isinstance(user_info, dict):
        _safe_debug_print("❌ 通过当前应用 user_access_token 获取用户信息失败")
        _debug_log_elapsed(
            "sync_feishu_identity_failed",
            sync_started_at,
            force_refresh=bool(force_refresh),
            token_source=("request_header" if request_token else "session")
        )
        return None
    user_info = dict(user_info)
    user_info['user_access_token'] = token
    _bind_feishu_session(user_info, token)
    _safe_debug_print(f"✅ 已通过当前应用 {expected_app_id} 绑定飞书用户: {session.get('feishu_user_id')}")
    _debug_log_elapsed(
        "sync_feishu_identity_done",
        sync_started_at,
        force_refresh=bool(force_refresh),
        user_id=str(session.get('feishu_user_id') or user_info.get('user_id') or '').strip(),
        token_source=("request_header" if request_token else "session")
    )
    return user_info


def _handle_feishu_identity_mismatch(is_api_request=False):
    next_path = request.full_path if request.query_string else request.path
    next_path = str(next_path or '').strip()
    if next_path.endswith('?'):
        next_path = next_path[:-1]
    session['post_auth_redirect'] = next_path or url_for('dashboard')
    if is_api_request:
        return jsonify({
            'success': False,
            'error': '身份已切换',
            'message': '检测到当前飞书身份与本地会话不一致，请重新授权',
            'auth_url': url_for('feishu_auth', next=next_path or url_for('dashboard'))
        }), 401
    return redirect(url_for('feishu_auth', next=next_path or url_for('dashboard')))


def _xiaotu_get_user_departments(user_id):
    uid = (user_id or "").strip()
    if not uid:
        return []
    try:
        rows = permission_manager.get_user_departments(uid) or []
    except Exception:
        rows = []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip().lower() in {"invalid", "unmapped"}:
            continue
        name = str(row.get("name") or "").strip()
        if name:
            out.append(name)
    return out


def _xiaotu_match_doc_permission(doc_item, user_depts):
    allowed = doc_item.get("allowed_departments")
    if allowed == "all":
        return True
    if not isinstance(allowed, list):
        return False
    my_set = {str(x or "").strip() for x in (user_depts or []) if str(x or "").strip()}
    allow_set = {str(x or "").strip() for x in (allowed or []) if str(x or "").strip()}
    return bool(my_set & allow_set)


def _xiaotu_get_user_saved_docs(user_id):
    all_docs = session.get("xiaotu_saved_docs") or {}
    if not isinstance(all_docs, dict):
        return []
    rows = all_docs.get(str(user_id or "").strip()) or []
    if not isinstance(rows, list):
        return []
    out = []
    for one in rows:
        if not isinstance(one, dict):
            continue
        url = str(one.get("url") or "").strip()
        name = str(one.get("name") or "").strip()
        doc_id = str(one.get("id") or "").strip()
        if not url or not doc_id:
            continue
        out.append({
            "id": doc_id,
            "name": name or "未命名云文档",
            "url": url,
            "source": "personal",
            "created_at": str(one.get("created_at") or "")
        })
    return out


def _xiaotu_list_feishu_docs_for_user(user_id, force_refresh=False, user_access_token=""):
    uid = str(user_id or "").strip()
    if not uid:
        return [], "未登录"
    token = str(user_access_token or "").strip()
    token_cache_key = f"{uid}|{token[:20]}"
    now_ts = datetime.now().timestamp()
    with _xiaotu_doc_list_cache_lock:
        cached = _xiaotu_doc_list_cache.get(token_cache_key)
        if (not force_refresh) and isinstance(cached, dict):
            ts = float(cached.get("ts") or 0)
            if (now_ts - ts) <= _xiaotu_doc_list_cache_ttl_seconds:
                data = cached.get("data") or []
                return data if isinstance(data, list) else [], str(cached.get("err") or "")
    use_user_token = True
    if not token:
        return [], "未获取到用户飞书登录凭证，请重新登录后再刷新可见文档"
    headers = {"Authorization": f"Bearer {token}"}
    page_token = ""
    pages = 0
    max_pages = 400
    max_items = 20000
    out = []
    seen = set()
    err_text = ""
    while pages < max_pages:
        pages += 1
        param_variants = [
            {"page_size": 200, "order_by": "EditedTime", "direction": "DESC"},
            {"page_size": 200},
            {"page_size": 100}
        ]
        resp = None
        resp_data = None
        status_code = 0
        for base_params in param_variants:
            params = dict(base_params)
            if page_token:
                params["page_token"] = page_token
            try:
                one_resp = _feishu_http.get("https://open.feishu.cn/open-apis/drive/v1/files", headers=headers, params=params, timeout=15)
            except Exception as e:
                err_text = str(e)
                one_resp = None
            if one_resp is None:
                continue
            one_status = int(one_resp.status_code or 0)
            one_data = one_resp.json() if one_resp.content else {}
            if one_status == 200 and int((one_data or {}).get("code") or 0) == 0:
                resp = one_resp
                resp_data = one_data
                status_code = one_status
                break
            if one_status == 400:
                resp = one_resp
                resp_data = one_data
                status_code = one_status
                continue
            resp = one_resp
            resp_data = one_data
            status_code = one_status
            break
        if resp is None:
            if not err_text:
                err_text = "飞书接口请求失败"
            break
        if status_code != 200:
            api_msg = str((resp_data or {}).get("msg") or "").strip()
            if api_msg:
                err_text = f"飞书接口返回状态码 {status_code}：{api_msg}"
            else:
                err_text = f"飞书接口返回状态码 {status_code}"
            low_msg = api_msg.lower()
            if status_code == 401 or "token expired" in low_msg or "authentication token expired" in low_msg:
                err_text = "飞书登录已过期，请重新登录后再刷新可见文档"
            if status_code == 400:
                err_text = f"{err_text}（已自动兼容不同分页参数）"
            break
        data = resp_data if isinstance(resp_data, dict) else (resp.json() if resp.content else {})
        if int((data or {}).get("code") or 0) != 0:
            err_text = str((data or {}).get("msg") or "飞书接口调用失败")
            if use_user_token and ("access token" in err_text.lower() or "invalid" in err_text.lower() or "expired" in err_text.lower()):
                err_text = "飞书登录已过期，请重新登录后再刷新可见文档"
            break
        body = (data or {}).get("data") or {}
        files = body.get("files") or body.get("items") or body.get("list") or []
        for one in files:
            if not isinstance(one, dict):
                continue
            typ_raw = str(
                one.get("type")
                or one.get("obj_type")
                or one.get("file_type")
                or one.get("doc_type")
                or one.get("mime_type")
                or one.get("file_extension")
                or one.get("sub_type")
                or ""
            ).strip().lower()
            token_one = str(
                one.get("token")
                or one.get("file_token")
                or one.get("obj_token")
                or one.get("node_token")
                or one.get("wiki_token")
                or ""
            ).strip()
            name = str(one.get("name") or one.get("title") or "").strip()
            url = str(one.get("url") or "").strip()
            if not token_one and url:
                token_one = _xiaotu_extract_doc_token(url)
            typ = ""
            # 放宽类型：收集用户可访问的主要云文档对象（文档/表格/wiki/多维表格/思维笔记/幻灯片）
            if "docx" in typ_raw:
                typ = "docx"
            elif typ_raw in {"docs", "doc", "wiki", "sheet", "sheets", "bitable", "base", "mindnote", "slides"}:
                typ = typ_raw
            elif "wiki" in typ_raw:
                typ = "wiki"
            elif "doc" in typ_raw:
                typ = "doc"
            elif "sheet" in typ_raw:
                typ = "sheet"
            elif "bitable" in typ_raw or "base" in typ_raw:
                typ = "bitable"
            elif "mindnote" in typ_raw:
                typ = "mindnote"
            elif "slide" in typ_raw:
                typ = "slides"

            if not typ:
                if token_one.startswith("doxcn"):
                    typ = "docx"
                elif token_one.startswith("doccn"):
                    typ = "doc"
                elif token_one.startswith("wiki"):
                    typ = "wiki"

            if not typ and url:
                u = url.lower()
                if "/docx/" in u:
                    typ = "docx"
                elif "/docs/" in u:
                    typ = "docs"
                elif "/doc/" in u:
                    typ = "doc"
                elif "/wiki/" in u:
                    typ = "wiki"
                elif "/sheets/" in u:
                    typ = "sheets"
                elif "/base/" in u or "/bitable/" in u:
                    typ = "bitable"
                elif "/mindnote/" in u:
                    typ = "mindnote"
                elif "/slides/" in u:
                    typ = "slides"

            # 没有URL时，尽量构造可访问链接；构不出就跳过
            if not url:
                url = _feishu_build_cloud_doc_url(typ, token_one)
            if not url:
                continue
            stable_key = token_one or url
            key = f"{typ}:{stable_key}"
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "id": f"auto_{token_one}",
                "name": name or f"云文档-{token_one[:8]}",
                "url": url,
                "source": "auto",
                "created_at": ""
            })
            if len(out) >= max_items:
                break
        if len(out) >= max_items:
            break
        page_token = str(
            body.get("next_page_token")
            or body.get("page_token")
            or body.get("next_cursor")
            or body.get("cursor")
            or ""
        ).strip()
        has_more_raw = body.get("has_more")
        if has_more_raw is None:
            has_more_raw = body.get("more")
        if isinstance(has_more_raw, bool):
            has_more = has_more_raw
        elif isinstance(has_more_raw, (int, float)):
            has_more = int(has_more_raw) != 0
        else:
            has_more = str(has_more_raw or "").strip().lower() in {"1", "true", "yes", "y"}

        if page_token:
            continue
        if not has_more:
            break
        # 避免has_more是脏值但没有分页游标时死循环导致只拿到首页数据
        break
    with _xiaotu_doc_list_cache_lock:
        _xiaotu_doc_list_cache[token_cache_key] = {"ts": now_ts, "data": out, "err": err_text}
    if use_user_token and not out and not err_text:
        err_text = "未拉取到可见云文档：请确认飞书应用已开通云文档读取权限，并重新登录后再刷新"
    return out, err_text


def _xiaotu_need_reauth(err_text):
    t = str(err_text or "").strip().lower()
    if not t:
        return False
    keys = [
        "飞书登录已过期",
        "authentication token expired",
        "token expired",
        "invalid access token",
        "access token expired",
        "登录状态缺少云文档访问凭证",
        "当前用户授权接口为历史版本",
        "end-user-consent",
        "please request user re-authorization",
        "unauthorized. you do not have permission",
        "应用未获取所需的用户授权"
    ]
    return any(k in t for k in keys)


def _xiaotu_set_user_saved_docs(user_id, rows):
    all_docs = session.get("xiaotu_saved_docs") or {}
    if not isinstance(all_docs, dict):
        all_docs = {}
    uid = str(user_id or "").strip()
    all_docs[uid] = rows if isinstance(rows, list) else []
    session["xiaotu_saved_docs"] = all_docs
    session.modified = True


def _xiaotu_extract_doc_token(url):
    u = str(url or "").strip()
    if not u:
        return ""
    pats = [
        r"/docx/([a-zA-Z0-9]+)",
        r"/docs/([a-zA-Z0-9]+)",
        r"/wiki/([a-zA-Z0-9]+)",
        r"/doc/([a-zA-Z0-9]+)",
        r"(doxcn[a-zA-Z0-9]+)"
    ]
    for p in pats:
        m = re.search(p, u)
        if m:
            return str(m.group(1) or "").strip()
    return ""


def _xiaotu_build_report_instance_id(doc_token=""):
    token = str(doc_token or "").strip()
    ts_part = datetime.now().strftime("%Y%m%d%H%M%S%f")
    if token:
        return f"{token}__{ts_part}"[:120]
    return f"manual__{ts_part}"[:120]


def _xiaotu_extract_source_doc_token(report_id):
    rid = str(report_id or "").strip()
    if not rid:
        return ""
    if "__" in rid:
        prefix = str(rid.split("__", 1)[0] or "").strip()
        if prefix and prefix.lower() != "manual":
            return prefix
        return ""
    if rid.lower().startswith("manual_"):
        return ""
    if re.fullmatch(r"[A-Za-z0-9]{6,120}", rid):
        return rid
    return ""


def _xiaotu_sql_escape(value):
    return str(value or "").replace("%", "%%").replace("'", "''")


def _xiaotu_lookup_org_perf_context(user_name):
    name = str(user_name or "").strip()
    if not name:
        return ""
    esc_name = _xiaotu_sql_escape(name)
    compact_name = re.sub(r"\s+", "", name)
    esc_compact_name = _xiaotu_sql_escape(compact_name)
    try:
        rows = sf_db(f"""
            IF OBJECT_ID(N'dbo.zuzhi_jixiao', N'U') IS NOT NULL
                SELECT TOP 1 ai_neirong
                FROM dbo.zuzhi_jixiao
                WHERE yonghu LIKE N'%%{esc_name}%%'
                   OR REPLACE(ISNULL(yonghu, N''), N' ', N'') LIKE N'%%{esc_compact_name}%%'
                ORDER BY yonghu
        """) or []
    except Exception as e:
        _safe_debug_print(f"查询组织绩效配置失败: {name} -> {e}")
        return ""
    if not rows:
        return ""
    first = rows[0]
    if isinstance(first, dict):
        return str(first.get("ai_neirong") or first.get("AI_NEIRONG") or "").strip()
    if isinstance(first, (list, tuple)):
        return str(first[0] if first else "").strip()
    return str(first or "").strip()


def _xiaotu_generate_org_perf_contribution(user_name, report_kind, report_material, org_perf_context, chat_id=""):
    context = str(org_perf_context or "").strip()
    material = str(report_material or "").strip()
    if not context or not material:
        return ""
    prompt = (
        "请严格对照“组织绩效配置(ai_neirong)”分析该员工今日日报对组织绩效产生了什么贡献。\n"
        "ai_neirong 是唯一评价口径，必须优先匹配其中的KPI指标、任务、定义、数据来源、达标/挑战口径；"
        "只能基于日报材料里的事实说明贡献，不要编造没有写出的结果、数据或影响。\n"
        "输出要求：\n"
        "1. 只输出一段，标题固定为“组织绩效贡献：”。\n"
        "2. 100字以内，必须点明命中的组织绩效指标/任务名称，并说明日报事实如何贡献该指标。\n"
        "3. 如果日报内容无法对应ai_neirong里的任何指标或任务，写“组织绩效贡献：当前日报信息未能对应组织绩效配置中的明确指标，暂无法判断具体贡献。”\n"
        "4. 不要打分，不要写空泛表扬，不要只写“提升效率/促进绩效”等泛化结论。"
    )
    doc_text = (
        f"提交人：{user_name}\n"
        f"报告类型：{report_kind}\n\n"
        f"组织绩效配置(ai_neirong)：\n{context}\n\n"
        f"今日日报材料：\n{material}"
    )
    try:
        text = _generate_ai_answer_with_doc(
            prompt_text=prompt,
            doc_text=doc_text,
            doc_name=f"{user_name} 组织绩效贡献分析",
            chat_id=chat_id or None
        )
        return str(text or "").strip()
    except Exception as e:
        _safe_debug_print(f"组织绩效贡献分析失败: {user_name} -> {e}")
        return ""


def _xiaotu_guess_title(doc_name, doc_text, doc_token):
    name = str(doc_name or "").strip()
    if name and not name.startswith("云文档-") and not name.startswith("临时文档-"):
        return name[:200]
    text = str(doc_text or "").strip()
    for line in text.splitlines():
        t = str(line or "").strip().lstrip("#").strip()
        if len(t) >= 2:
            return t[:200]
    if name:
        return name[:200]
    tok = str(doc_token or "").strip()
    return (f"云文档-{tok[:10]}" if tok else "未命名云文档")[:200]


def _xiaotu_build_report_title(user_name, report_kind, date_text=None):
    date_part = str(date_text or datetime.now().strftime('%Y-%m-%d')).strip() or datetime.now().strftime('%Y-%m-%d')
    name_part = str(user_name or '').strip() or '未知用户'
    kind_part = str(report_kind or '').strip() or '周报'
    return f"{date_part} {name_part} {kind_part}"[:200]


def _xiaotu_detect_report_kind(question_text, title_text, body_text):
    s = f"{str(question_text or '')}\n{str(title_text or '')}\n{str(body_text or '')}".lower()
    if "月报" in s:
        return "月报"
    if "日报" in s:
        return "日报"
    if "周报" in s:
        return "周报"
    return "周报"


def _xiaotu_report_kind_from_type(report_type):
    kind = str(report_type or "").strip().lower()
    if kind in {"day", "daily", "日报"}:
        return "日报"
    if kind in {"month", "monthly", "月报"}:
        return "月报"
    return "周报"


def _xiaotu_report_type_from_kind(report_kind):
    kind = str(report_kind or "").strip()
    if kind == "日报":
        return "day"
    if kind == "月报":
        return "month"
    return "week"


def _xiaotu_is_daily_date_heading(text_line):
    line = str(text_line or "").strip()
    if not line:
        return False
    line = re.sub(r"^[#>*\-\s]+", "", line).strip()
    if not line or len(line) > 48:
        return False
    patterns = [
        r"^(20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?)(?:\s*[（(]?[^\n（）()]{0,12}[)）]?)?(?:\s*(日报|工作日报|工作总结|总结))?$",
        r"^(\d{1,2}[月]\d{1,2}日)(?:\s*[（(]?[^\n（）()]{0,12}[)）]?)?(?:\s*(日报|工作日报|工作总结|总结))?$",
        r"^(\d{1,2}[./-]\d{1,2})(?:\s*[（(]?[^\n（）()]{0,12}[)）]?)?(?:\s*(日报|工作日报|工作总结|总结))?$",
    ]
    return any(re.match(pat, line, flags=re.I) for pat in patterns)


def _xiaotu_find_daily_date_matches(text):
    raw = str(text or "")
    if not raw:
        return []
    patterns = [
        r"(^|[\r\n])[\t >#*\-]*"
        r"(20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?(?:\s*[（(]?[^\r\n（）()]{0,12}[)）]?)?(?:\s*(?:日报|工作日报|工作总结|总结))?)"
        r"(?=\s*(?:[\r\n]|$))",
        r"(^|[\r\n])[\t >#*\-]*"
        r"(\d{1,2}月\d{1,2}日(?:\s*[（(]?[^\r\n（）()]{0,12}[)）]?)?(?:\s*(?:日报|工作日报|工作总结|总结))?)"
        r"(?=\s*(?:[\r\n]|$))",
        r"(^|[\r\n])[\t >#*\-]*"
        r"(\d{1,2}[./-]\d{1,2}(?:\s*[（(]?[^\r\n（）()]{0,12}[)）]?)?(?:\s*(?:日报|工作日报|工作总结|总结))?)"
        r"(?=\s*(?:[\r\n]|$))",
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, raw, flags=re.I):
            found.append({
                "start": int(m.start(2)),
                "text": str(m.group(2) or "").strip()
            })
    found.sort(key=lambda x: int(x.get("start") or 0))
    dedup = []
    seen = set()
    for one in found:
        key = (int(one.get("start") or 0), str(one.get("text") or ""))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(one)
    return dedup


def _xiaotu_find_last_daily_date_start(text):
    raw = str(text or "")
    if not raw:
        return -1, ""
    matches = _xiaotu_find_daily_date_matches(raw)
    if matches:
        last = matches[-1]
        return int(last.get("start") or -1), str(last.get("text") or "").strip()
    offset = 0
    last_pos = -1
    last_line = ""
    for one in raw.splitlines(True):
        plain = one.rstrip("\r\n")
        if _xiaotu_is_daily_date_heading(plain):
            last_pos = offset
            last_line = plain.strip()
        offset += len(one)
    return last_pos, last_line


def _xiaotu_build_today_daily_search_keys(now_dt=None):
    now = now_dt if isinstance(now_dt, datetime) else datetime.now()
    return _xiaotu_build_date_search_keys(
        f"{now.year}-{now.month:02d}-{now.day:02d}"
    )


def _xiaotu_find_preferred_daily_date_start(text, now_dt=None):
    raw = str(text or "")
    if not raw:
        return -1, "", ""
    matches = _xiaotu_find_daily_date_matches(raw)
    today_keys = _xiaotu_build_today_daily_search_keys(now_dt)
    if matches:
        if today_keys:
            for one in matches:
                one_text = str(one.get("text") or "").strip()
                one_keys = _xiaotu_build_date_search_keys(one_text)
                if any(key and key in one_keys for key in today_keys):
                    return int(one.get("start") or -1), one_text, "today"
        last = matches[-1]
        return int(last.get("start") or -1), str(last.get("text") or "").strip(), "last"

    offset = 0
    last_pos = -1
    last_line = ""
    today_pos = -1
    today_line = ""
    for one in raw.splitlines(True):
        plain = str(one or "").rstrip("\r\n")
        if _xiaotu_is_daily_date_heading(plain):
            line_keys = _xiaotu_build_date_search_keys(plain)
            if today_keys and any(key and key in line_keys for key in today_keys) and today_pos < 0:
                today_pos = offset
                today_line = plain.strip()
            last_pos = offset
            last_line = plain.strip()
        offset += len(one)
    if today_pos >= 0:
        return today_pos, today_line, "today"
    return last_pos, last_line, ("last" if last_pos >= 0 else "")


def _xiaotu_count_daily_date_headings(text):
    matches = _xiaotu_find_daily_date_matches(text)
    if matches:
        return len(matches)
    raw = str(text or "")
    if not raw:
        return 0
    count = 0
    for one in raw.splitlines():
        if _xiaotu_is_daily_date_heading(one):
            count += 1
    return count


def _xiaotu_extract_block_plain_text(block_obj):
    ignore_keys = {
        "token", "file_token", "image_token", "media_token", "resource_token", "object_token",
        "block_id", "id", "parent_id", "parentid", "url", "href", "block_type", "type"
    }
    table_like_keys = {
        "table", "cells", "cell", "table_cells", "table_cell", "rows", "row", "table_rows",
        "table_row", "header_row", "body_rows", "columns", "column", "grid", "matrix"
    }
    row_like_keys = {"rows", "row", "table_rows", "table_row", "header_row", "body_rows"}
    cell_like_keys = {"cells", "cell", "table_cells", "table_cell", "columns", "column"}

    def clean_fragment(raw):
        s = html_unescape(str(raw or "")).strip()
        if not s:
            return ""
        s = re.sub(r"\s+", " ", s).strip()
        # 去掉飞书 block 里常见的对象 id 前缀，避免出现在正文里。
        s = re.sub(r"^(?:[A-Za-z0-9_-]{12,}\s+)+", "", s).strip()
        if not s:
            return ""
        if re.fullmatch(r"[A-Za-z0-9_-]{12,}", s):
            return ""
        if re.fullmatch(r"\d{1,3}", s):
            return ""
        return s

    def merge_fragments(parts, separator=" "):
        rows = []
        for one in (parts or []):
            txt = str(one or "").strip()
            if not txt:
                continue
            rows.append(txt)
        if not rows:
            return ""
        text = separator.join(rows)
        text = re.sub(r"[ \t\f\v]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def walk(obj, parent_key=""):
        if obj is None:
            return ""
        if isinstance(obj, str):
            return clean_fragment(obj)
        if isinstance(obj, dict):
            grouped_parts = []
            cell_parts = []
            has_table_hint = False
            for k, v in obj.items():
                lk = str(k or "").strip().lower()
                if lk in ignore_keys:
                    continue
                if lk in table_like_keys:
                    has_table_hint = True
                child_text = walk(v, lk)
                if not child_text:
                    continue
                if lk in row_like_keys:
                    grouped_parts.append(child_text)
                elif lk in cell_like_keys:
                    cell_parts.append(child_text)
                else:
                    grouped_parts.append(child_text)
            if cell_parts:
                cell_line = merge_fragments(cell_parts, " | ")
                if cell_line:
                    grouped_parts.append(cell_line)
            if has_table_hint:
                return merge_fragments(grouped_parts, "\n")
            return merge_fragments(grouped_parts, " ")
        elif isinstance(obj, list):
            child_parts = []
            for item in obj:
                child_text = walk(item, parent_key)
                if child_text:
                    child_parts.append(child_text)
            if parent_key in row_like_keys:
                return merge_fragments(child_parts, "\n")
            if parent_key in cell_like_keys:
                return merge_fragments(child_parts, " | ")
            return merge_fragments(child_parts, "\n" if parent_key in table_like_keys else " ")
        return ""

    text = walk(block_obj)
    text = re.sub(r"[ \t\f\v]+", " ", str(text or ""))
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _xiaotu_extract_image_tokens_from_block(block_obj):
    direct_token_keys = {"file_token", "image_token", "media_token", "resource_token", "object_token", "filetoken"}
    token_parent_hints = {
        "image", "media", "file", "attachment", "thumbnail", "cover", "origin_image",
        "gallery", "figure", "img", "picture", "embed", "docsimage", "inline_image"
    }
    found = []
    seen = set()

    def add_token(v):
        s = str(v or "").strip()
        if not s or len(s) < 10 or s in seen:
            return
        seen.add(s)
        found.append(s)

    def walk(obj, parent_key=""):
        if obj is None:
            return
        if isinstance(obj, dict):
            key_set = {str(k).lower() for k in obj.keys()}
            for k, v in obj.items():
                lk = str(k or "").strip().lower()
                if lk in direct_token_keys:
                    add_token(v)
                elif lk == "token" and (str(parent_key or "").lower() in token_parent_hints or (key_set & token_parent_hints)):
                    add_token(v)
                elif lk in {"filetoken", "mediatoken", "imagetoken", "resourcetoken", "objecttoken"}:
                    add_token(v)
                elif lk in {"src", "source"} and isinstance(v, dict):
                    add_token(v.get("token") or v.get("file_token") or v.get("image_token") or v.get("media_token"))
                walk(v, lk)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, parent_key)

    walk(block_obj)
    if not found:
        try:
            raw = json.dumps(block_obj, ensure_ascii=False)
        except Exception:
            raw = str(block_obj or "")
        raw = str(raw or "")
        token = _xiaotu_extract_feishu_file_token_from_fragment(raw)
        if token:
            add_token(token)
        if (not found) and re.search(r"(image|media|gallery|figure|picture|attachment|drivetoken)", raw, flags=re.I):
            patterns = [
                r'"fileToken"\s*:\s*"([A-Za-z0-9_-]{10,})"',
                r'"(?:file_token|image_token|media_token|resource_token|object_token)"\s*:\s*"([A-Za-z0-9_-]{10,})"',
                r'drivetoken://([A-Za-z0-9_-]{10,})',
                r'"token"\s*:\s*"([A-Za-z0-9_-]{10,})"'
            ]
            for pat in patterns:
                for m in re.finditer(pat, raw, flags=re.I):
                    add_token(m.group(1))
    return found


def _xiaotu_order_doc_blocks(blocks):
    rows = [x for x in (blocks or []) if isinstance(x, dict)]
    if not rows:
        return []
    id_map = {}
    child_ids = set()
    for block in rows:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        if block_id and block_id not in id_map:
            id_map[block_id] = block
        children = block.get("children")
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    cid = str(child.get("block_id") or child.get("id") or child.get("child_id") or child.get("blockId") or "").strip()
                else:
                    cid = str(child or "").strip()
                if cid:
                    child_ids.add(cid)

    roots = []
    for block in rows:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        parent_id = str(block.get("parent_id") or block.get("parentId") or "").strip()
        if (not parent_id or parent_id not in id_map) and (not block_id or block_id not in child_ids):
            roots.append(block)
    if not roots:
        roots = rows[:]

    ordered = []
    seen = set()

    def visit(block):
        if not isinstance(block, dict):
            return
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        key = block_id or f"obj:{id(block)}"
        if key in seen:
            return
        seen.add(key)
        ordered.append(block)
        children = block.get("children")
        if not isinstance(children, list):
            return
        for child in children:
            if isinstance(child, dict):
                cid = str(child.get("block_id") or child.get("id") or child.get("child_id") or child.get("blockId") or "").strip()
            else:
                cid = str(child or "").strip()
            if cid and cid in id_map:
                visit(id_map[cid])

    for root in roots:
        visit(root)
    for block in rows:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        key = block_id or f"obj:{id(block)}"
        if key not in seen:
            seen.add(key)
            ordered.append(block)
    return ordered


def _xiaotu_is_image_like_block(block_obj):
    if not isinstance(block_obj, dict):
        return False
    block_type = str(block_obj.get("block_type") or block_obj.get("type") or "").lower()
    if any(k in block_type for k in ["image", "media", "file", "attachment", "gallery", "figure", "picture"]):
        return True
    keys = {str(k).lower() for k in block_obj.keys()}
    return bool({"image", "media", "file", "attachment", "gallery", "figure", "picture"} & keys)


def _xiaotu_build_block_debug_sample(block_obj):
    if not isinstance(block_obj, dict):
        return {}
    keys = [str(k) for k in list(block_obj.keys())[:10]]
    text_preview = str(_xiaotu_extract_block_plain_text(block_obj) or "").strip()
    if len(text_preview) > 80:
        text_preview = text_preview[:80] + "..."
    tokens = _xiaotu_extract_image_tokens_from_block(block_obj)
    return {
        "block_id": str(block_obj.get("block_id") or block_obj.get("id") or "").strip(),
        "parent_id": str(block_obj.get("parent_id") or block_obj.get("parentId") or "").strip(),
        "block_type": str(block_obj.get("block_type") or block_obj.get("type") or "").strip(),
        "image_like": _xiaotu_is_image_like_block(block_obj),
        "token_count": len(tokens or []),
        "text_preview": text_preview,
        "keys": keys
    }


def _xiaotu_build_date_search_keys(text):
    raw = str(text or "").strip()
    if not raw:
        return []
    nums = re.findall(r"\d+", raw)
    joined = "".join(nums)
    keys = []
    if len(joined) >= 8:
        keys.append(joined[:8])
        keys.append(joined[-4:])
    elif len(joined) >= 4:
        keys.append(joined[-4:])
    seen = set()
    out = []
    for one in keys:
        one = str(one or "").strip()
        if not one or one in seen:
            continue
        seen.add(one)
        out.append(one)
    return out


def _xiaotu_find_last_daily_block_index(blocks, matched_line=""):
    rows = list(blocks or [])
    if not rows:
        return -1
    last_idx = -1
    for idx, block in enumerate(rows):
        block_text = _xiaotu_extract_block_plain_text(block)
        if _xiaotu_is_daily_date_heading(block_text):
            last_idx = idx
    if last_idx >= 0:
        return last_idx

    search_keys = _xiaotu_build_date_search_keys(matched_line)
    if not search_keys:
        return -1

    for idx, block in enumerate(rows):
        try:
            raw = json.dumps(block, ensure_ascii=False)
        except Exception:
            raw = str(block or "")
        normalized = re.sub(r"\D+", "", raw or "")
        if not normalized:
            continue
        if any(key and key in normalized for key in search_keys):
            last_idx = idx
    return last_idx


def _xiaotu_find_preferred_daily_block_index(blocks, matched_line="", now_dt=None):
    rows = list(blocks or [])
    if not rows:
        return -1, ""
    today_keys = _xiaotu_build_today_daily_search_keys(now_dt)
    last_idx = -1
    for idx, block in enumerate(rows):
        block_text = _xiaotu_extract_block_plain_text(block)
        if not _xiaotu_is_daily_date_heading(block_text):
            continue
        line_keys = _xiaotu_build_date_search_keys(block_text)
        if today_keys and any(key and key in line_keys for key in today_keys):
            return idx, "today"
        last_idx = idx
    if last_idx >= 0:
        return last_idx, "last"

    search_keys = _xiaotu_build_date_search_keys(matched_line)
    if search_keys:
        for idx, block in enumerate(rows):
            try:
                raw = json.dumps(block, ensure_ascii=False)
            except Exception:
                raw = str(block or "")
            normalized = re.sub(r"\D+", "", raw or "")
            if not normalized:
                continue
            if any(key and key in normalized for key in search_keys):
                return idx, "matched_line"
    return -1, ""


def _xiaotu_fetch_docx_blocks(agent, doc_token):
    token = str(doc_token or "").strip()
    if not token:
        return [], "缺少文档token"
    access_token = permission_manager.get_access_token()
    if not access_token:
        return [], "当前无法获取飞书 tenant_access_token"
    http_client = getattr(agent, "_http", None) or _feishu_http
    headers = {"Authorization": f"Bearer {access_token}"}
    page_token = ""
    blocks = []
    for _ in range(80):
        try:
            api = f"https://open.feishu.cn/open-apis/docx/v1/documents/{token}/blocks"
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            resp = http_client.get(api, headers=headers, params=params, timeout=15)
            data = resp.json() if resp is not None else {}
            if not resp or resp.status_code != 200:
                return blocks, f"获取文档块失败 {getattr(resp, 'status_code', '')} {str(getattr(resp, 'text', '') or '')[:160]}"
            if not isinstance(data, dict) or int(data.get("code") or 0) != 0:
                return blocks, f"获取文档块失败 {data.get('code')} {data.get('msg')}"
            d = data.get("data") or {}
            items = d.get("items") or []
            if isinstance(items, list):
                blocks.extend(items)
            page_token = str(d.get("page_token") or "").strip()
            if not page_token:
                break
        except Exception as e:
            return blocks, f"获取文档块异常: {str(e)}"
    return blocks, ""


def _xiaotu_slice_daily_doc_content(agent, doc_url, doc_text):
    result = {
        "used": False,
        "matched_date": "",
        "match_mode": "",
        "text_sliced": False,
        "image_token_count": 0,
        "block_error": "",
        "text_source": "raw_content",
        "block_total": 0,
        "matched_block_index": -1,
        "trailing_block_count": 0,
        "trailing_image_like_block_count": 0,
        "trailing_block_samples": []
    }
    text_raw = str(doc_text or "").strip()
    if agent is None or not str(doc_url or "").strip() or not text_raw:
        return text_raw, [], result

    sliced_text = text_raw
    start_pos, matched_line, match_mode = _xiaotu_find_preferred_daily_date_start(text_raw)
    if start_pos >= 0:
        tail = text_raw[start_pos:].strip()
        if tail:
            sliced_text = tail
            result["used"] = True
            result["matched_date"] = matched_line
            result["match_mode"] = match_mode
            result["text_sliced"] = True

    resolver = getattr(agent, "resolve_url_to_doc", None)
    if not callable(resolver):
        return sliced_text, [], result
    try:
        resolved_token, resolved_type, resolved_err = resolver(doc_url)
    except Exception as e:
        resolved_token, resolved_type, resolved_err = "", "", str(e)
    if resolved_err or not resolved_token or str(resolved_type or "").strip().lower() not in {"docx", "docs", ""}:
        if resolved_err:
            result["block_error"] = str(resolved_err)
        return sliced_text, [], result

    blocks, block_err = _xiaotu_fetch_docx_blocks(agent, resolved_token)
    if block_err:
        result["block_error"] = block_err
        return sliced_text, [], result
    if not blocks:
        return sliced_text, [], result
    ordered_blocks = _xiaotu_order_doc_blocks(blocks)
    scan_blocks = ordered_blocks or blocks
    result["block_total"] = len(scan_blocks)

    last_date_block_idx, block_match_mode = _xiaotu_find_preferred_daily_block_index(
        scan_blocks,
        result.get("matched_date") or matched_line
    )
    if last_date_block_idx >= 0 and not result.get("matched_date"):
        result["matched_date"] = str(matched_line or "").strip()
    if block_match_mode:
        result["match_mode"] = block_match_mode
    result["matched_block_index"] = last_date_block_idx

    if last_date_block_idx < 0:
        result["trailing_block_samples"] = [
            _xiaotu_build_block_debug_sample(b)
            for b in scan_blocks[:8]
        ]
        return sliced_text, [], result

    trailing_blocks = scan_blocks[last_date_block_idx:]
    result["trailing_block_count"] = len(trailing_blocks)
    result["trailing_image_like_block_count"] = sum(1 for b in trailing_blocks if _xiaotu_is_image_like_block(b))
    result["trailing_block_samples"] = [
        _xiaotu_build_block_debug_sample(b)
        for b in trailing_blocks[:8]
    ]

    block_text_lines = []
    for block in trailing_blocks:
        one_text = _xiaotu_extract_block_plain_text(block)
        one_text = str(one_text or "").strip()
        if not one_text:
            continue
        block_text_lines.append(one_text)
    block_sliced_text = "\n".join(block_text_lines).strip()
    if block_sliced_text:
        sliced_text = block_sliced_text
        result["used"] = True
        result["text_sliced"] = True
        result["text_source"] = "doc_blocks"

    tokens = []
    seen = set()
    for block in trailing_blocks:
        for token in _xiaotu_extract_image_tokens_from_block(block):
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    result["used"] = True
    result["image_token_count"] = len(tokens)
    return sliced_text, tokens, result


def _xiaotu_person_type_from_value(value):
    t = str(value or "").strip().lower()
    if t in {"management", "manager", "管理层"}:
        return "管理层"
    if t in {"improvement_staff", "improvement", "改进人员"}:
        return "改进人员"
    if t in {"intern_trainee", "intern", "trainee", "管培生/实习", "管培生", "实习"}:
        return "管培生/实习"
    return "正式员工"


def _xiaotu_person_type_to_value(value):
    txt = str(value or "").strip()
    if txt == "管理层":
        return "management"
    if txt == "改进人员":
        return "improvement_staff"
    if txt == "管培生/实习":
        return "intern_trainee"
    return "formal_staff"


def _xiaotu_person_focus_text(person_type):
    pt = str(person_type or "").strip()
    if pt == "管理层":
        return (
            "侧重点：经营洞察、管理动作复盘、团队带教、资源配置与风险预警。"
            "请适当指出优点与不足，建议要可执行。"
        )
    if pt == "改进人员":
        return (
            "侧重点：绩效差距、改进动作闭环、指标变化、问题根因与纠偏。"
            "请适当指出优点与不足，建议要量化、可跟踪。"
        )
    if pt == "管培生/实习":
        return (
            "侧重点要求（第1点最重要，优先围绕这一点判断内容是否完整、清楚、具体）：\n"
            "1. 当日工作内容：必须重点关注今日学习内容、今日工作内容、各事项用时情况，以及学习知识点是否有梳理总结。\n"
            "2. 遇到的问题、解决方案与思路扩展：说明遇到的学习难点或不理解内容、如何解决、思考路径，以及以后应对类似问题的思路总结或扩展。\n"
            "3. 明日计划：是否写清明日需继续跟进的事项与下一步动作。\n"
            "4. 好用的工作方法与素材积累：是否沉淀了可复用的方法、资料、模板或经验。\n"
            "请在总结、优点、不足、改进建议中优先体现第1点，再依次覆盖后面几点；建议要明确、具体、易执行，适合管培生/实习生快速成长。"
        )
    return (
        "侧重点：SOP执行质量、流程优化、协作效率、结果稳定性。"
        "请适当指出优点与不足，建议要具体可落地。"
    )


def _xiaotu_lookup_open_id_by_name(user_name):
    name = str(user_name or "").strip()
    if not name:
        return ""
    if name.startswith("ou_") or name.startswith("ou-"):
        return name
    cached_id = _xiaotu_get_cached_open_id_by_name(name)
    if cached_id:
        return cached_id

    def _extract_open_id_value(result):
        if isinstance(result, str):
            return result.strip()
        if isinstance(result, dict):
            return str(
                result.get("FeiShu_ID")
                or result.get("feishu_id")
                or result.get("FEISHU_ID")
                or result.get("Feishu_ID")
                or ""
            ).strip()
        if isinstance(result, (list, tuple)):
            if not result:
                return ""
            first = result[0]
            if isinstance(first, dict):
                return str(
                    first.get("FeiShu_ID")
                    or first.get("feishu_id")
                    or first.get("FEISHU_ID")
                    or first.get("Feishu_ID")
                    or ""
                ).strip()
            if isinstance(first, (list, tuple)):
                return str(first[0] if len(first) > 0 else "").strip()
            return str(first or "").strip()
        return ""

    def _query_table(table_name, where_sql):
        table = str(table_name or "").strip()
        if not table:
            return ""
        try:
            rows = sf_db(
                f"""
                IF OBJECT_ID(N'{table}', N'U') IS NOT NULL
                    SELECT TOP 1 FeiShu_ID
                    FROM {table}
                    WHERE ({where_sql})
                      AND (FeiShu_ID LIKE 'ou[_]%%' OR FeiShu_ID LIKE 'ou-%%')
                    ORDER BY FeiShu_ID
                """
            )
        except Exception:
            rows = None
        fid = _extract_open_id_value(rows)
        return fid if (fid.startswith("ou_") or fid.startswith("ou-")) else ""

    def _query_all_tables(where_sql):
        for table in (_XIAOTU_NOTIFY_ID_TABLE_PRIMARY, _XIAOTU_NOTIFY_ID_TABLE_FALLBACK):
            fid = _query_table(table, where_sql)
            if fid:
                _xiaotu_remember_user_open_id(name, fid)
                return fid
        return ""

    esc_name = _xiaotu_sql_escape(name)
    compact_name = re.sub(r"\s+", "", name)
    esc_compact_name = _xiaotu_sql_escape(compact_name)

    fid = _query_all_tables(f"YONGHU=N'{esc_name}'")
    if fid:
        return fid

    if compact_name:
        fid = _query_all_tables(
            f"""
            REPLACE(REPLACE(ISNULL(YONGHU, N''), N' ', N''), CHAR(9), N'')=N'{esc_compact_name}'
            """
        )
        if fid:
            return fid

    fid = _query_all_tables(f"YONGHU LIKE N'%%{esc_name}%%'")
    if fid:
        return fid

    if compact_name:
        fid = _query_all_tables(
            f"""
            REPLACE(REPLACE(ISNULL(YONGHU, N''), N' ', N''), CHAR(9), N'') LIKE N'%%{esc_compact_name}%%'
            """
        )
        if fid:
            return fid
    try:
        exact_candidates = []
        fuzzy_candidates = []
        for dept in (_xiaotu_list_notify_departments() or []):
            if not isinstance(dept, dict):
                continue
            dept_id = str(dept.get("department_id") or "").strip()
            if not dept_id:
                continue
            for one in (_xiaotu_list_notify_users_current_app_cached(dept_id) or []):
                if not isinstance(one, dict):
                    continue
                oid = str(one.get("open_id") or "").strip()
                if not (oid.startswith("ou_") or oid.startswith("ou-")):
                    continue
                candidate_names = [
                    str(one.get("name") or "").strip(),
                    str(one.get("display_name") or "").strip(),
                ]
                for candidate_name in candidate_names:
                    if not candidate_name:
                        continue
                    candidate_compact = re.sub(r"\s+", "", candidate_name)
                    if candidate_name == name or (compact_name and candidate_compact == compact_name):
                        exact_candidates.append((candidate_name, oid))
                    elif name in candidate_name or (compact_name and compact_name in candidate_compact):
                        fuzzy_candidates.append((candidate_name, oid))
        for candidate_name, oid in exact_candidates or fuzzy_candidates:
            _xiaotu_remember_user_open_id(candidate_name, oid)
            _xiaotu_remember_user_open_id(name, oid)
            return oid
    except Exception as e:
        _safe_debug_print(f"permission debug contact fallback lookup failed: {name} -> {e}")
    return ""


_XIAOTU_REPORT_ESCALATION_USER = "陶晓飞"


def _xiaotu_pick_primary_department(user_id):
    uid = str(user_id or "").strip()
    if not uid:
        return "", ""
    try:
        rows = permission_manager.get_user_departments(uid) or []
    except Exception:
        rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip().lower() in {"invalid", "unmapped"}:
            continue
        dept_id = str(row.get("department_id") or "").strip()
        dept_name = str(row.get("name") or "").strip()
        if dept_id or dept_name:
            return dept_id, dept_name
    return "", str(session.get('user_department') or '').strip()


def _xiaotu_get_department_leader_user_id(department_id):
    dep_id = str(department_id or "").strip()
    if not dep_id:
        return ""
    try:
        dept_info = permission_manager.get_department_info(dep_id) or {}
    except Exception:
        dept_info = {}
    leader_id = str(
        (dept_info or {}).get("leader_user_id")
        or (dept_info or {}).get("leader_open_id")
        or (dept_info or {}).get("leader_userid")
        or ""
    ).strip()
    if leader_id.startswith("ou_") or leader_id.startswith("ou-"):
        return leader_id
    token = permission_manager.get_access_token()
    if not token:
        return ""
    try:
        resp = _feishu_http.get(
            f"https://open.feishu.cn/open-apis/contact/v3/departments/{dep_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
            params={
                "department_id_type": "open_department_id",
                "user_id_type": "open_id",
            },
            timeout=12,
        )
        data = resp.json() if resp is not None else {}
        if resp is not None and resp.status_code == 200 and isinstance(data, dict) and int(data.get("code") or 0) == 0:
            dept = ((data.get("data") or {}).get("department") or {})
            return str(
                dept.get("leader_user_id")
                or dept.get("leader_open_id")
                or dept.get("leader_userid")
                or ""
            ).strip()
    except Exception as e:
        _safe_debug_print(f"获取部门负责人失败: {dep_id} -> {e}")
    return ""


def _xiaotu_list_notify_departments():
    rows = sf_db(
        f"""
        IF OBJECT_ID(N'{_XIAOTU_NOTIFY_ID_TABLE_PRIMARY}', N'U') IS NOT NULL
            SELECT DISTINCT YONGHU, FeiShu_ID FROM {_XIAOTU_NOTIFY_ID_TABLE_PRIMARY}
            WHERE (FeiShu_ID LIKE 'od[_]%%' OR FeiShu_ID LIKE 'od-%%')
            ORDER BY YONGHU
        ELSE
            SELECT DISTINCT YONGHU, FeiShu_ID FROM {_XIAOTU_NOTIFY_ID_TABLE_FALLBACK}
            WHERE (FeiShu_ID LIKE 'od[_]%%' OR FeiShu_ID LIKE 'od-%%')
            ORDER BY YONGHU
        """
    ) or []
    out = []
    seen = set()
    if not isinstance(rows, list):
        rows = [rows]
    for row in rows:
        if isinstance(row, dict):
            dept_name = str(row.get("YONGHU") or "").strip()
            dept_id = str(row.get("FeiShu_ID") or "").strip()
        elif isinstance(row, (list, tuple)):
            dept_name = str(row[0] if len(row) > 0 else "").strip()
            dept_id = str(row[1] if len(row) > 1 else "").strip()
        else:
            dept_name = str(row or "").strip()
            dept_id = ""
        if not dept_id.startswith("od_") and not dept_id.startswith("od-"):
            continue
        key = f"{dept_id}|{dept_name}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"department_id": dept_id, "department_name": dept_name})
    return out


def _xiaotu_list_department_children_current_app(department_id):
    dep_id = str(department_id or "").strip()
    if not dep_id:
        return []
    token = permission_manager.get_access_token()
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    page_token = ""
    out = []
    seen = set()
    for _ in range(50):
        try:
            url = f"https://open.feishu.cn/open-apis/contact/v3/departments/{dep_id}/children"
            params = {"department_id_type": "open_department_id", "page_size": 100, "fetch_child": False}
            if page_token:
                params["page_token"] = page_token
            resp = _feishu_http.get(url, headers=headers, params=params, timeout=15)
            data = resp.json() if resp is not None else {}
            if not resp or resp.status_code != 200 or not isinstance(data, dict) or int(data.get("code") or 0) != 0:
                break
            items = ((data.get("data") or {}).get("items") or [])
            for item in items:
                one_id = str(
                    (item or {}).get("open_department_id")
                    or (item or {}).get("department_id")
                    or (item or {}).get("id")
                    or ""
                ).strip()
                if one_id and one_id not in seen:
                    seen.add(one_id)
                    out.append(one_id)
            page_token = str(((data.get("data") or {}).get("page_token") or "")).strip()
            if not page_token:
                break
        except Exception:
            break
    return out


def _xiaotu_expand_department_tree_current_app(department_id):
    root_id = str(department_id or "").strip()
    if not root_id:
        return []
    out = []
    seen = set()
    queue = [root_id]
    while queue:
        current = str(queue.pop(0) or "").strip()
        if not current or current in seen:
            continue
        seen.add(current)
        out.append(current)
        for child_id in _xiaotu_list_department_children_current_app(current):
            if child_id and child_id not in seen:
                queue.append(child_id)
    return out


def _xiaotu_list_notify_users_current_app(department_id):
    dep_ids = _xiaotu_expand_department_tree_current_app(department_id)
    if not dep_ids:
        return []
    token = permission_manager.get_access_token()
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    payload = []
    seen = set()
    for dep_id in dep_ids:
        page_token = ""
        for _ in range(50):
            try:
                url = "https://open.feishu.cn/open-apis/contact/v3/users"
                params = {
                    "department_id_type": "open_department_id",
                    "department_id": dep_id,
                    "user_id_type": "open_id",
                    "page_size": 100
                }
                if page_token:
                    params["page_token"] = page_token
                resp = _feishu_http.get(url, headers=headers, params=params, timeout=15)
                data = resp.json() if resp is not None else {}
                if not resp or resp.status_code != 200 or not isinstance(data, dict) or int(data.get("code") or 0) != 0:
                    break
                items = ((data.get("data") or {}).get("items") or [])
                for item in items:
                    oid = str((item or {}).get("open_id") or "").strip()
                    if not oid or oid in seen:
                        continue
                    seen.add(oid)
                    payload.append({
                        "open_id": oid,
                        "name": str((item or {}).get("name") or "").strip(),
                        "display_name": str((item or {}).get("name") or oid).strip()
                    })
                page_token = str(((data.get("data") or {}).get("page_token") or "")).strip()
                if not page_token:
                    break
            except Exception:
                break
    payload.sort(key=lambda x: str(x.get("display_name") or ""))
    return payload


def _xiaotu_list_notify_users_current_app_cached(department_id):
    dep_id = str(department_id or "").strip()
    if not dep_id:
        return []
    now_ts = time.time()
    with _xiaotu_notify_department_users_cache_lock:
        cached = _xiaotu_notify_department_users_cache.get(dep_id)
        if isinstance(cached, dict) and (now_ts - float(cached.get("ts") or 0)) < _xiaotu_notify_department_users_cache_ttl_seconds:
            users = cached.get("users") or []
            return [dict(one) for one in users if isinstance(one, dict)]
    users = _xiaotu_list_notify_users_current_app(dep_id)
    normalized = [dict(one) for one in (users or []) if isinstance(one, dict)]
    with _xiaotu_notify_department_users_cache_lock:
        _xiaotu_notify_department_users_cache[dep_id] = {"ts": now_ts, "users": normalized}
    return [dict(one) for one in normalized]


def _xiaotu_get_history_analysis_visible_user_names(user_id, user_name):
    uid = str(user_id or "").strip()
    current_name = str(user_name or "").strip()
    visible_names = []
    seen_names = set()
    leader_department_ids = []
    leader_department_names = []
    scoped_department_ids = []
    scoped_department_names = [
        str(name or "").strip()
        for name in (_XIAOTU_REPORT_HISTORY_USER_DEPARTMENT_SCOPE.get(current_name) or [])
        if str(name or "").strip()
    ]

    def add_name(raw_name):
        name = str(raw_name or "").strip()
        if not name or name in seen_names:
            return
        seen_names.add(name)
        visible_names.append(name)

    if scoped_department_names:
        for one in (_xiaotu_list_notify_departments() or []):
            if not isinstance(one, dict):
                continue
            dept_name = str(one.get("department_name") or one.get("name") or "").strip()
            dept_id = str(one.get("department_id") or "").strip()
            if dept_name in scoped_department_names and dept_id:
                scoped_department_ids.append(dept_id)
        for scoped_name in _xiaotu_collect_notify_user_names_by_department_names(scoped_department_names):
            add_name(scoped_name)

    if uid:
        try:
            departments = permission_manager.get_user_departments(uid) or []
        except Exception:
            departments = []
        for row in departments:
            if not isinstance(row, dict):
                continue
            if str(row.get("status") or "").strip().lower() in {"invalid", "unmapped"}:
                continue
            dept_id = str(row.get("department_id") or "").strip()
            if not dept_id:
                continue
            leader_user_id = _xiaotu_get_department_leader_user_id(dept_id)
            if leader_user_id and leader_user_id == uid:
                leader_department_ids.append(dept_id)
                leader_department_names.append(str(row.get("name") or "").strip())

    if leader_department_ids:
        for dept_id in leader_department_ids:
            for one in (_xiaotu_list_notify_users_current_app_cached(dept_id) or []):
                if isinstance(one, dict):
                    add_name(one.get("name"))
    add_name(current_name)
    department_ids = []
    for dep_id in list(leader_department_ids) + list(scoped_department_ids):
        if dep_id and dep_id not in department_ids:
            department_ids.append(dep_id)
    department_names = []
    for dep_name in list(leader_department_names) + list(scoped_department_names):
        if dep_name and dep_name not in department_names:
            department_names.append(dep_name)
    return {
        "is_department_leader": bool(department_ids),
        "department_ids": department_ids,
        "department_names": department_names,
        "user_names": visible_names,
    }


def _xiaotu_search_notify_users(keyword, limit=50):
    query = str(keyword or "").strip()
    if not query:
        return []
    safe_limit = max(1, min(int(limit or 50), 200))
    esc_kw = _xiaotu_sql_escape(query)
    rows = sf_db(
        f"""
        IF OBJECT_ID(N'{_XIAOTU_NOTIFY_ID_TABLE_PRIMARY}', N'U') IS NOT NULL
            SELECT TOP {safe_limit} YONGHU, FeiShu_ID FROM {_XIAOTU_NOTIFY_ID_TABLE_PRIMARY}
            WHERE (FeiShu_ID LIKE 'ou[_]%%' OR FeiShu_ID LIKE 'ou-%%')
              AND (YONGHU LIKE N'%%{esc_kw}%%' OR FeiShu_ID LIKE '%%{esc_kw}%%')
            ORDER BY YONGHU ASC, FeiShu_ID ASC
        ELSE
            SELECT TOP {safe_limit} YONGHU, FeiShu_ID FROM {_XIAOTU_NOTIFY_ID_TABLE_FALLBACK}
            WHERE (FeiShu_ID LIKE 'ou[_]%%' OR FeiShu_ID LIKE 'ou-%%')
              AND (YONGHU LIKE N'%%{esc_kw}%%' OR FeiShu_ID LIKE '%%{esc_kw}%%')
            ORDER BY YONGHU ASC, FeiShu_ID ASC
        """
    ) or []
    if not isinstance(rows, list):
        rows = [rows]
    out = []
    seen = set()
    for row in rows:
        if isinstance(row, dict):
            name = _normalize_feishu_user_name(row.get("YONGHU"), fallback="")
            open_id = str(row.get("FeiShu_ID") or "").strip()
        elif isinstance(row, (list, tuple)):
            name = _normalize_feishu_user_name(row[0] if len(row) > 0 else "", fallback="")
            open_id = str(row[1] if len(row) > 1 else "").strip()
        else:
            continue
        if not open_id.startswith("ou_") and not open_id.startswith("ou-"):
            continue
        display_name = str(name or open_id).strip()
        key = open_id or display_name
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({
            "open_id": open_id,
            "name": name,
            "display_name": display_name,
            "search_scope": "all_departments",
        })
    return out


def _xiaotu_query_user_names_by_open_ids(open_ids):
    ids = []
    seen = set()
    for raw in (open_ids or []):
        oid = str(raw or "").strip()
        if not oid.startswith("ou_") or oid in seen:
            continue
        seen.add(oid)
        ids.append(oid)
    if not ids:
        return {}
    mapping = {}
    token = permission_manager.get_access_token() if hasattr(permission_manager, "get_access_token") else ""
    if token:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        for oid in ids:
            try:
                resp = _feishu_http.get(
                    f"https://open.feishu.cn/open-apis/contact/v3/users/{oid}",
                    headers=headers,
                    params={"user_id_type": "open_id"},
                    timeout=10
                )
                data = resp.json() if resp is not None else {}
                if resp and resp.status_code == 200 and isinstance(data, dict) and int(data.get("code") or 0) == 0:
                    user_obj = (data.get("data") or {}).get("user") or {}
                    name = _resolve_feishu_user_name(user_obj, fallback="")
                    if name:
                        mapping[oid] = name
            except Exception:
                continue
    missing_ids = [oid for oid in ids if oid not in mapping]
    if missing_ids:
        cond = " OR ".join([f"FeiShu_ID='{_xiaotu_sql_escape(oid)}'" for oid in missing_ids])
        rows = sf_db(
            f"""
            IF OBJECT_ID(N'{_XIAOTU_NOTIFY_ID_TABLE_PRIMARY}', N'U') IS NOT NULL
                SELECT FeiShu_ID, YONGHU FROM {_XIAOTU_NOTIFY_ID_TABLE_PRIMARY} WHERE {cond}
            ELSE
                SELECT FeiShu_ID, YONGHU FROM {_XIAOTU_NOTIFY_ID_TABLE_FALLBACK} WHERE {cond}
            """
        ) or []
        if not isinstance(rows, list):
            rows = [rows]
        for row in rows:
            if isinstance(row, dict):
                oid = str(row.get("FeiShu_ID") or "").strip()
                name = _normalize_feishu_user_name(row.get("YONGHU"), fallback="")
            elif isinstance(row, (list, tuple)):
                oid = str(row[0] if len(row) > 0 else "").strip()
                name = _normalize_feishu_user_name(row[1] if len(row) > 1 else "", fallback="")
            else:
                continue
            if oid.startswith("ou_") and name:
                mapping[oid] = name
    return mapping


def _xiaotu_query_user_name_by_any_id(open_id="", user_id="", union_id=""):
    oid = str(open_id or "").strip()
    uid = str(user_id or "").strip()
    union = str(union_id or "").strip()
    token = permission_manager.get_access_token() if hasattr(permission_manager, "get_access_token") else ""
    targets = []
    if oid.startswith("ou_"):
        targets.append((oid, "open_id"))
    if uid:
        targets.append((uid, "user_id"))
    if union:
        targets.append((union, "union_id"))
    if token:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        for raw_id, id_type in targets:
            try:
                resp = _feishu_http.get(
                    f"https://open.feishu.cn/open-apis/contact/v3/users/{raw_id}",
                    headers=headers,
                    params={"user_id_type": id_type},
                    timeout=10
                )
                data = resp.json() if resp is not None else {}
                if resp and resp.status_code == 200 and isinstance(data, dict) and int(data.get("code") or 0) == 0:
                    user_obj = (data.get("data") or {}).get("user") or {}
                    name = _resolve_feishu_user_name(user_obj, fallback="")
                    if name:
                        return name
            except Exception:
                continue
    if oid.startswith("ou_"):
        try:
            mapping = _xiaotu_query_user_names_by_open_ids([oid]) or {}
            name = _normalize_feishu_user_name(mapping.get(oid), fallback="")
            if name:
                return name
        except Exception:
            pass
    return ""


def _xiaotu_resolve_card_actor_name(payload):
    data = payload if isinstance(payload, dict) else {}
    operator_name = _normalize_feishu_user_name(
        data.get("operator_name") or data.get("user_name") or "",
        fallback=""
    )
    if operator_name and not _xiaotu_is_invalid_feishu_name(operator_name):
        return operator_name
    open_id = str(data.get("open_id") or "").strip()
    user_id = str(data.get("user_id") or "").strip()
    union_id = str(data.get("union_id") or "").strip()
    query_name = _xiaotu_query_user_name_by_any_id(open_id=open_id, user_id=user_id, union_id=union_id)
    if query_name:
        return query_name
    if operator_name and not _xiaotu_is_invalid_feishu_name(operator_name):
        return operator_name
    for candidate in (open_id, user_id):
        txt = str(candidate or "").strip()
        if txt:
            return txt
    return "匿名用户"


def _xiaotu_parse_notify_open_ids(data_dict):
    candidates = []
    if isinstance(data_dict, dict):
        one = data_dict.get("notify_open_ids")
        if isinstance(one, list):
            candidates.extend(one)
        else:
            candidates.append(one)
    try:
        candidates.extend(request.form.getlist("notify_open_ids"))
    except Exception:
        pass

    out = []
    seen = set()
    for raw in candidates:
        if raw is None:
            continue
        if isinstance(raw, list):
            parts = raw
        else:
            txt = str(raw or "").strip()
            if not txt:
                continue
            parts = []
            if txt.startswith("[") and txt.endswith("]"):
                try:
                    parsed = json.loads(txt)
                    if isinstance(parsed, list):
                        parts = parsed
                except Exception:
                    parts = []
            if not parts:
                if "," in txt:
                    parts = [x.strip() for x in txt.split(",") if str(x).strip()]
                else:
                    parts = [txt]
        for item in parts:
            oid = str(item or "").strip()
            if not oid.startswith("ou_") or oid in seen:
                continue
            seen.add(oid)
            out.append(oid)
    return out


def _xiaotu_parse_notify_targets(data_dict):
    candidates = []
    if isinstance(data_dict, dict):
        one = data_dict.get("notify_targets")
        if isinstance(one, list):
            candidates.extend(one)
        elif isinstance(one, str) and one.strip():
            try:
                parsed = json.loads(one)
                if isinstance(parsed, list):
                    candidates.extend(parsed)
            except Exception:
                pass
    try:
        candidates.extend(request.form.getlist("notify_targets"))
    except Exception:
        pass

    out = []
    seen = set()
    for raw in candidates:
        parts = []
        if isinstance(raw, list):
            parts = raw
        elif isinstance(raw, dict):
            parts = [raw]
        else:
            txt = str(raw or "").strip()
            if not txt:
                continue
            if txt.startswith("[") and txt.endswith("]"):
                try:
                    parsed = json.loads(txt)
                    if isinstance(parsed, list):
                        parts = parsed
                except Exception:
                    parts = []
        for item in parts:
            if not isinstance(item, dict):
                continue
            oid = str(item.get("open_id") or "").strip()
            name = str(item.get("name") or "").strip()
            key = f"{oid}|{name}"
            if (not oid and not name) or key in seen:
                continue
            seen.add(key)
            out.append({"open_id": oid, "name": name})
    return out


def _xiaotu_resolve_notify_names(open_ids, notify_targets=None):
    ids = []
    seen_ids = set()
    for raw in (open_ids or []):
        oid = str(raw or "").strip()
        if oid and oid not in seen_ids:
            seen_ids.add(oid)
            ids.append(oid)
    fallback_name_map = {}
    for item in (notify_targets or []):
        if not isinstance(item, dict):
            continue
        oid = str(item.get("open_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if oid and name and oid not in fallback_name_map:
            fallback_name_map[oid] = name
    selected_notify_name_map = _xiaotu_query_user_names_by_open_ids(ids)
    out = []
    seen_names = set()
    for oid in ids:
        nm = str(selected_notify_name_map.get(oid) or fallback_name_map.get(oid) or "").strip()
        if not nm or nm in seen_names:
            continue
        seen_names.add(nm)
        out.append(nm)
    return out


def _xiaotu_resolve_notify_open_ids(open_ids, notify_targets=None):
    out = []
    seen = set()
    for raw in (open_ids or []):
        oid = str(raw or "").strip()
        if oid.startswith("ou_") and oid not in seen:
            seen.add(oid)
            out.append(oid)
    for item in (notify_targets or []):
        if not isinstance(item, dict):
            continue
        oid = str(item.get("open_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not oid and name:
            oid = str(_xiaotu_lookup_open_id_by_name(name) or "").strip()
        if oid.startswith("ou_") and oid not in seen:
            seen.add(oid)
            out.append(oid)
    return out


def _xiaotu_extract_report_image_paths_from_html(html_text):
    html = str(html_text or "").strip()
    if not html:
        return []
    out = []
    seen = set()
    for m in re.finditer(r'<img\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        src = str(m.group(1) or "").strip()
        if not src:
            continue
        normalized = unquote(src).strip().strip('"').strip("'")
        if normalized.startswith("/api/xiaotu/report_image"):
            try:
                parsed = urlparse(normalized)
                nested_path = parse_qs(parsed.query or "").get("path") or []
                normalized = str(nested_path[0] if nested_path else "").strip()
                normalized = unquote(normalized).strip().strip('"').strip("'")
            except Exception:
                normalized = ""
        if not normalized:
            continue
        normalized = relocate_storage_path(normalized).replace("/", os.sep)
        if not os.path.isabs(normalized):
            continue
        abs_path = os.path.abspath(normalized)
        if abs_path in seen:
            continue
        seen.add(abs_path)
        out.append(abs_path)
    return out


def _xiaotu_split_cache_multi_value(raw_text):
    text = str(raw_text or "").strip()
    if not text:
        return []
    parts = re.split(r"[\|\n\r,，;；]+", text)
    out = []
    seen = set()
    for raw in parts:
        one = relocate_storage_path(str(raw or "").strip())
        if not one or one in seen:
            continue
        seen.add(one)
        out.append(one)
    return out


def _xiaotu_build_notify_cache_text(open_ids, notify_targets=None):
    resolved_open_ids = []
    seen_open_ids = set()
    for raw in (open_ids or []):
        oid = str(raw or "").strip()
        if not oid.startswith("ou_") or oid in seen_open_ids:
            continue
        seen_open_ids.add(oid)
        resolved_open_ids.append(oid)
    fallback_name_map = {}
    for item in (notify_targets or []):
        if not isinstance(item, dict):
            continue
        oid = str(item.get("open_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if oid.startswith("ou_") and name and oid not in fallback_name_map:
            fallback_name_map[oid] = name
    resolved_name_map = _xiaotu_query_user_names_by_open_ids(resolved_open_ids)
    normalized_targets = []
    for oid in resolved_open_ids:
        normalized_targets.append({
            "open_id": oid,
            "name": str(resolved_name_map.get(oid) or fallback_name_map.get(oid) or "").strip(),
        })
    payload = {
        "version": 2,
        "notify_open_ids": resolved_open_ids,
        "notify_targets": normalized_targets,
    }
    return _XIAOTU_NOTIFY_CACHE_PREFIX + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _xiaotu_parse_notify_cache_text(raw_text):
    text = str(raw_text or "").strip()
    if not text.startswith(_XIAOTU_NOTIFY_CACHE_PREFIX):
        return None
    payload_text = text[len(_XIAOTU_NOTIFY_CACHE_PREFIX):].strip()
    if not payload_text:
        return {
            "notify_names": [],
            "notify_targets": [],
            "notify_open_ids": [],
        }
    try:
        payload = json.loads(payload_text)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    raw_targets = payload.get("notify_targets")
    notify_targets = raw_targets if isinstance(raw_targets, list) else []
    notify_open_ids = _xiaotu_resolve_notify_open_ids(payload.get("notify_open_ids"), notify_targets)
    if not notify_open_ids:
        return {
            "notify_names": [],
            "notify_targets": [],
            "notify_open_ids": [],
        }
    resolved_name_map = _xiaotu_query_user_names_by_open_ids(notify_open_ids)
    fallback_name_map = {}
    for item in notify_targets:
        if not isinstance(item, dict):
            continue
        oid = str(item.get("open_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if oid.startswith("ou_") and name and oid not in fallback_name_map:
            fallback_name_map[oid] = name
    normalized_targets = []
    notify_names = []
    seen_names = set()
    for oid in notify_open_ids:
        name = str(resolved_name_map.get(oid) or fallback_name_map.get(oid) or "").strip()
        normalized_targets.append({
            "name": name,
            "open_id": oid,
        })
        if name and name not in seen_names:
            seen_names.add(name)
            notify_names.append(name)
    return {
        "notify_names": notify_names,
        "notify_targets": normalized_targets,
        "notify_open_ids": notify_open_ids,
    }


def _xiaotu_normalize_notify_time(raw_text):
    txt = str(raw_text or "").strip()
    if not txt:
        return ""
    m = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?$", txt)
    if not m:
        return ""
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _xiaotu_get_report_cache(user_name):
    name = str(user_name or "").strip()
    if not name:
        return {
            "user_name": "",
            "notify_names": [],
            "notify_targets": [],
            "notify_open_ids": [],
            "notify_time": "",
            "draft_html": "",
            "image_paths": []
        }
    esc_name = _xiaotu_sql_escape(name)
    sql = f"""
        IF OBJECT_ID(N'{_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}', N'U') IS NOT NULL
            SELECT TOP 1 ID, YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin, TongZhiShiJian
            FROM {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}
            WHERE YongHu = N'{esc_name}'
            ORDER BY ID DESC
        ELSE
            SELECT TOP 1 ID, YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin, CAST(N'' AS NVARCHAR(20)) AS TongZhiShiJian
            FROM {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK}
            WHERE YongHu = N'{esc_name}'
            ORDER BY ID DESC
    """
    rows = sf_db(sql) or []
    row = rows[0] if rows else {}
    if isinstance(row, (list, tuple)):
        row = {
            "ID": row[0] if len(row) > 0 else None,
            "YongHu": row[1] if len(row) > 1 else "",
            "TiJiaoRen": row[2] if len(row) > 2 else "",
            "HuanCunWenBen": row[3] if len(row) > 3 else "",
            "TuPianLuJin": row[4] if len(row) > 4 else "",
            "TongZhiShiJian": row[5] if len(row) > 5 else "",
        }
    elif not isinstance(row, dict):
        row = {}
    notify_raw = row.get("TiJiaoRen") or row.get("tijiaoren") or ""
    parsed_notify_cache = _xiaotu_parse_notify_cache_text(notify_raw)
    if parsed_notify_cache is not None:
        notify_names = parsed_notify_cache.get("notify_names") or []
        notify_targets = parsed_notify_cache.get("notify_targets") or []
        notify_open_ids = parsed_notify_cache.get("notify_open_ids") or []
    else:
        notify_names = _xiaotu_split_cache_multi_value(notify_raw)
        notify_targets = []
        notify_open_ids = []
        seen_open_ids = set()
        for nm in notify_names:
            oid = str(_xiaotu_lookup_open_id_by_name(nm) or "").strip()
            if not oid.startswith("ou_") or oid in seen_open_ids:
                continue
            seen_open_ids.add(oid)
            notify_open_ids.append(oid)
            notify_targets.append({"name": nm, "open_id": oid})
        notify_names = _xiaotu_resolve_notify_names(notify_open_ids, notify_targets)
    return {
        "user_name": name,
        "notify_names": notify_names,
        "notify_targets": notify_targets,
        "notify_open_ids": notify_open_ids,
        "notify_time": _xiaotu_normalize_notify_time(
            row.get("TongZhiShiJian") or row.get("tongzhishijian") or row.get("通知时间") or ""
        ),
        "draft_html": str(row.get("HuanCunWenBen") or row.get("huancunwenben") or "").strip(),
        "image_paths": _xiaotu_split_cache_multi_value(row.get("TuPianLuJin") or row.get("tupianlujin") or "")
    }


def _xiaotu_upsert_report_cache_notify(user_name, notify_open_ids, notify_targets=None, notify_time=""):
    name = str(user_name or "").strip()
    if not name:
        return
    name_esc = _xiaotu_sql_escape(name)
    notify_text = _xiaotu_build_notify_cache_text(notify_open_ids, notify_targets)
    notify_esc = _xiaotu_sql_escape(notify_text)
    notify_time_esc = _xiaotu_sql_escape(_xiaotu_normalize_notify_time(notify_time))
    sql = f"""
        IF OBJECT_ID(N'{_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}', N'U') IS NOT NULL
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}
                SET TiJiaoRen = N'{notify_esc}',
                    TongZhiShiJian = N'{notify_time_esc}'
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin, TongZhiShiJian)
                VALUES (N'{name_esc}', N'{notify_esc}', N'', N'', N'{notify_time_esc}')
        END
        ELSE
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK}
                SET TiJiaoRen = N'{notify_esc}'
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin)
                VALUES (N'{name_esc}', N'{notify_esc}', N'', N'')
        END
    """
    dui_db(sql)


def _xiaotu_upsert_report_cache_draft(user_name, draft_html, image_paths):
    name = str(user_name or "").strip()
    if not name:
        return
    name_esc = _xiaotu_sql_escape(name)
    html_esc = _xiaotu_sql_escape(draft_html)
    image_text = "|".join(_xiaotu_split_cache_multi_value("|".join(image_paths or [])))
    image_esc = _xiaotu_sql_escape(image_text)
    sql = f"""
        IF OBJECT_ID(N'{_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}', N'U') IS NOT NULL
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}
                SET HuanCunWenBen = N'{html_esc}',
                    TuPianLuJin = N'{image_esc}'
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin, TongZhiShiJian)
                VALUES (N'{name_esc}', N'', N'{html_esc}', N'{image_esc}', N'')
        END
        ELSE
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK}
                SET HuanCunWenBen = N'{html_esc}',
                    TuPianLuJin = N'{image_esc}'
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin)
                VALUES (N'{name_esc}', N'', N'{html_esc}', N'{image_esc}')
        END
    """
    dui_db(sql)


def _xiaotu_clear_report_cache_draft(user_name):
    name = str(user_name or "").strip()
    if not name:
        return
    name_esc = _xiaotu_sql_escape(name)
    sql = f"""
        IF OBJECT_ID(N'{_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}', N'U') IS NOT NULL
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}
                SET HuanCunWenBen = N'',
                    TuPianLuJin = N''
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin, TongZhiShiJian)
                VALUES (N'{name_esc}', N'', N'', N'', N'')
        END
        ELSE
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK}
                SET HuanCunWenBen = N'',
                    TuPianLuJin = N''
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin)
                VALUES (N'{name_esc}', N'', N'', N'')
        END
    """
    dui_db(sql)


def _xiaotu_get_period_range(report_type):
    now = datetime.now()
    kind = str(report_type or "week").strip().lower()
    if kind == "month":
        start = datetime(now.year, now.month, 1, 0, 0, 0)
        end = now
        return start, end, "month", "月报"
    # 默认按周：本周一 00:00:00 到当前时刻
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now
    return start, end, "week", "周报"


def _xiaotu_get_sender_open_id_from_message(message_row):
    msg = message_row if isinstance(message_row, dict) else {}
    sender = msg.get("sender") if isinstance(msg.get("sender"), dict) else {}
    sender_id = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
    for key in ["open_id", "user_id", "id"]:
        val = str(sender_id.get(key) or "").strip()
        if val:
            return val
    for key in ["sender_id", "user_id", "open_id"]:
        val = str(sender.get(key) or "").strip()
        if val:
            return val
    return ""


def _xiaotu_get_message_text_for_daily_ref(message_row):
    msg = message_row if isinstance(message_row, dict) else {}
    body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
    content = body.get("content")
    if content is None:
        content = msg.get("content")
    text = _feishu_extract_text_from_content(content)
    txt = str(text or "").strip()
    if txt:
        return txt
    msg_type = str(msg.get("msg_type") or "").strip().lower()
    if msg_type in {"image"}:
        return "[图片]"
    if msg_type in {"file"}:
        return "[文件]"
    if msg_type in {"audio"}:
        return "[语音]"
    if msg_type in {"video"}:
        return "[视频]"
    if msg_type in {"sticker"}:
        return "[表情]"
    return ""


def _xiaotu_format_message_time(create_time_raw):
    raw = str(create_time_raw or "").strip()
    if not raw:
        return ""
    try:
        ts = int(float(raw))
        if ts > 10 ** 12:
            ts = int(ts / 1000)
        return datetime.fromtimestamp(ts).strftime('%H:%M')
    except Exception:
        return raw[:5]


def _xiaotu_render_period_source_text(rows):
    chunks = []
    for idx, one in enumerate(rows, start=1):
        riqi = str((one or {}).get("riqi") or "").strip()
        title = str((one or {}).get("biaoti") or "").strip()
        zhengwen = str((one or {}).get("zhengwen") or "").strip()
        tupian = str((one or {}).get("tupianneirong") or "").strip()
        if not zhengwen and not tupian:
            continue
        chunks.append(
            f"【记录{idx}】\n"
            f"时间：{riqi or '未知'}\n"
            f"标题：{title or '未命名'}\n"
            f"正文：\n{zhengwen or '（空）'}\n\n"
            f"图片内容：\n{tupian or '（空）'}"
        )
    return "\n\n".join(chunks).strip()


_XIAOTU_REPORT_HISTORY_ANALYSIS_DIR = r"D:\tuchuangai\日报历史分析"


def _xiaotu_parse_date_value(value, fallback=None):
    raw = str(value or "").strip()
    if not raw:
        return fallback
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    return fallback


def _xiaotu_report_image_url(path_value):
    raw = relocate_storage_path(path_value)
    if not raw:
        return ""
    if raw.startswith("/api/xiaotu/report_image"):
        return raw
    try:
        return url_for("api_xiaotu_report_image", path=raw)
    except Exception:
        return "/api/xiaotu/report_image?path=" + quote(raw)


def _xiaotu_normalize_report_html_body(raw_html, image_paths_text=""):
    html = str(raw_html or "").strip()
    paths = [
        str(x or "").strip()
        for x in re.split(r"[|;\n]+", str(image_paths_text or ""))
        if str(x or "").strip()
    ]
    if html:
        def repl_img_src(match):
            quote_char = match.group(1) or '"'
            src = html_unescape(str(match.group(2) or "").strip())
            if not src or src.startswith("data:") or src.startswith("http://") or src.startswith("https://") or src.startswith("/api/xiaotu/report_image"):
                return match.group(0)
            return f"src={quote_char}{html_escape(_xiaotu_report_image_url(src), quote=True)}{quote_char}"

        html = re.sub(r"src\s*=\s*([\"'])([^\"']+)\1", repl_img_src, html, flags=re.IGNORECASE)
    else:
        html = "<p>（无正文）</p>"
    existing = set()
    for m in re.finditer(r"<img\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE):
        existing.add(html_unescape(str(m.group(1) or "").strip()))
    extra_imgs = []
    for path in paths:
        img_url = _xiaotu_report_image_url(path)
        if not img_url or img_url in existing or path in existing:
            continue
        extra_imgs.append(
            f'<figure><img src="{html_escape(img_url, quote=True)}" alt="日报图片"><figcaption>{html_escape(os.path.basename(path))}</figcaption></figure>'
        )
    if extra_imgs:
        html += "\n" + "\n".join(extra_imgs)
    return html


def _xiaotu_markdownish_to_html(text):
    raw = str(text or "").strip()
    if not raw:
        return "<p>暂无分析内容。</p>"
    lines = raw.splitlines()
    parts = []
    in_ul = False
    for line in lines:
        s = str(line or "").strip()
        if not s:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", s)
        if heading:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            level = min(4, max(2, len(heading.group(1)) + 1))
            parts.append(f"<h{level}>{html_escape(heading.group(2).strip())}</h{level}>")
            continue
        if re.match(r"^[-*]\s+", s):
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{html_escape(re.sub(r'^[-*]\\s+', '', s))}</li>")
            continue
        if in_ul:
            parts.append("</ul>")
            in_ul = False
        parts.append(f"<p>{html_escape(s)}</p>")
    if in_ul:
        parts.append("</ul>")
    return "\n".join(parts)


def _xiaotu_build_history_analysis_html(user_name, start_date, end_date, analysis_text, rows):
    range_text = f"{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    analysis_html = _xiaotu_markdownish_to_html(analysis_text)
    item_html = []
    for idx, one in enumerate(rows, start=1):
        riqi = html_escape(str((one or {}).get("riqi") or "").strip())
        title = html_escape(str((one or {}).get("biaoti") or "未命名日报").strip())
        body_html = _xiaotu_normalize_report_html_body(
            (one or {}).get("zhengwen") or "",
            (one or {}).get("tupianlujin") or ""
        )
        ocr_text = str((one or {}).get("tupianneirong") or "").strip()
        ocr_html = f"<details><summary>图片识别内容</summary><pre>{html_escape(ocr_text)}</pre></details>" if ocr_text else ""
        item_html.append(f"""
        <article class="daily-item">
            <div class="daily-index">#{idx}</div>
            <h2>{title}</h2>
            <div class="daily-meta">{riqi}</div>
            <div class="daily-body">{body_html}</div>
            {ocr_html}
        </article>
        """)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_escape(user_name)} 日报历史分析 {html_escape(range_text)}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; color: #172033; background: #f6f7fb; }}
    .wrap {{ max-width: 1080px; margin: 0 auto; padding: 28px 18px 56px; }}
    .hero {{ background: #ffffff; border: 1px solid #e7eaf0; border-radius: 8px; padding: 22px; margin-bottom: 16px; }}
    h1 {{ font-size: 24px; margin: 0 0 8px; }}
    .meta {{ color: #64748b; font-size: 13px; line-height: 1.7; }}
    .analysis, .daily-item {{ background: #ffffff; border: 1px solid #e7eaf0; border-radius: 8px; padding: 20px; margin-top: 14px; }}
    .analysis h2, .daily-item h2 {{ margin: 0 0 10px; font-size: 18px; }}
    .analysis p, .analysis li {{ line-height: 1.75; }}
    .daily-index {{ display: inline-block; color: #2563eb; font-weight: 700; margin-bottom: 8px; }}
    .daily-meta {{ color: #64748b; font-size: 13px; margin-bottom: 12px; }}
    .daily-body {{ line-height: 1.75; overflow-wrap: anywhere; }}
    .daily-body img, figure img {{ max-width: 100%; height: auto; border: 1px solid #e5e7eb; border-radius: 6px; margin: 8px 0; }}
    figure {{ margin: 12px 0; }}
    figcaption {{ color: #64748b; font-size: 12px; }}
    pre {{ white-space: pre-wrap; background: #f8fafc; padding: 12px; border-radius: 6px; color: #334155; }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>{html_escape(user_name)} 日报历史分析</h1>
      <div class="meta">日期范围：{html_escape(range_text)} | 日报数量：{len(rows)} | 生成时间：{html_escape(generated_at)}</div>
    </section>
    <section class="analysis">
      <h2>整合分析</h2>
      {analysis_html}
    </section>
    {''.join(item_html)}
  </main>
</body>
</html>"""


def _xiaotu_save_history_analysis_file(user_name, start_date, end_date, html_text):
    os.makedirs(_XIAOTU_REPORT_HISTORY_ANALYSIS_DIR, exist_ok=True)
    safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", str(user_name or "用户")).strip("_") or "用户"
    file_name = f"{safe_name}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}_{int(datetime.now().timestamp())}.html"
    path = os.path.abspath(os.path.join(_XIAOTU_REPORT_HISTORY_ANALYSIS_DIR, file_name))
    base = os.path.abspath(_XIAOTU_REPORT_HISTORY_ANALYSIS_DIR)
    if os.path.commonpath([base, path]) != base:
        raise ValueError("生成文件路径非法")
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(html_text or ""))
    return path


def _xiaotu_extract_knowledge_terms(question):
    raw = str(question or "").strip().lower()
    if not raw:
        return []
    parts = re.split(r"[\s,，。；;：:、\?\!！？\(\)（）\[\]【】\"'“”‘’/\\\-\+]+", raw)
    terms = []
    seen = set()
    for part in parts:
        token = str(part or "").strip()
        if len(token) < 2:
            continue
        if token not in seen:
            seen.add(token)
            terms.append(token)
        chinese_only = re.sub(r"[^\u4e00-\u9fff]", "", token)
        if len(chinese_only) >= 4:
            for size in (2, 3):
                for i in range(0, len(chinese_only) - size + 1):
                    piece = chinese_only[i:i + size]
                    if piece not in seen:
                        seen.add(piece)
                        terms.append(piece)
                    if len(terms) >= 18:
                        return terms[:18]
    return terms[:18]


def _xiaotu_render_knowledge_source_text(rows):
    chunks = []
    for idx, one in enumerate(rows, start=1):
        riqi = str((one or {}).get("riqi") or "").strip()
        title = str((one or {}).get("biaoti") or "").strip()
        zhengwen = str((one or {}).get("zhengwen") or "").strip()
        tupian = str((one or {}).get("tupianneirong") or "").strip()
        score = int((one or {}).get("score") or 0)
        chunks.append(
            f"【命中记录{idx}】\n"
            f"时间：{riqi or '未知'}\n"
            f"标题：{title or '未命名'}\n"
            f"相关度：{score}\n"
            f"正文：\n{zhengwen or '（空）'}\n\n"
            f"图片内容：\n{tupian or '（空）'}"
        )
    return "\n\n".join(chunks).strip()


def _xiaotu_resolve_redirect_url(endpoint_name, fallback="dashboard_xiaotu"):
    target = str(endpoint_name or "").strip()
    if not target:
        target = fallback
    try:
        return url_for(target)
    except Exception:
        return url_for(fallback)


def _xiaotu_classify_image_debug(err_text, image_block_count, saved_count):
    t = str(err_text or "").strip()
    tl = t.lower()
    if int(saved_count or 0) > 0:
        return {"reason_code": "ok", "reason_text": "图片下载与落盘成功"}
    if ("可见" in t and "不可见" in t) or ("not visible" in tl) or ("invisible" in tl):
        return {"reason_code": "visibility_denied", "reason_text": t or "可见性不足：应用对文档或图片资源不可见"}
    if (
        ("权限" in t) or ("scope" in tl) or ("access denied" in tl) or ("forbidden" in tl) or
        ("401" in tl) or ("403" in tl) or ("permission" in tl)
    ):
        return {"reason_code": "permission_denied", "reason_text": t or "权限不足：应用缺少图片读取/下载权限"}
    if int(image_block_count or 0) <= 0:
        return {"reason_code": "no_image_block", "reason_text": t or "未识别到图片块：文档可能无图片或图片非可下载资源"}
    if t:
        return {"reason_code": "download_failed", "reason_text": t}
    return {"reason_code": "unknown", "reason_text": "未知原因：未获取到可落盘图片"}


def _xiaotu_pick_doc_for_request(user_id, user_access_token, doc_id="", manual_url="", question=""):
    docs, _ = _xiaotu_get_doc_candidates_for_user(
        user_id,
        force_refresh=False,
        user_access_token=user_access_token
    )
    target = str(doc_id or "").strip()
    if target:
        for one in (docs or []):
            if str((one or {}).get('id') or '').strip() == target:
                return one
    url = _feishu_find_cloud_doc_url_any(str(manual_url or '').strip()) or str(manual_url or '').strip()
    if not url:
        url = _feishu_find_cloud_doc_url_any(str(question or '').strip()) or ""
    if not url:
        token_only = _xiaotu_extract_doc_token(question)
        if token_only.startswith("doxcn"):
            url = _feishu_build_cloud_doc_url("docx", token_only)
        elif token_only.startswith("doccn"):
            url = _feishu_build_cloud_doc_url("doc", token_only)
        elif token_only.startswith("wiki"):
            url = _feishu_build_cloud_doc_url("wiki", token_only)
    if not url:
        return None
    token = _xiaotu_extract_doc_token(url)
    if not token:
        return None
    return {
        'id': f'adhoc_{token}',
        'name': f'临时文档-{token[:8]}',
        'url': url
    }


def _xiaotu_save_doc_images_and_ocr(agent, doc_token, doc_url="", specific_tokens=None):
    token = str(doc_token or "").strip()
    debug = {
        "reason_code": "unknown",
        "reason_text": "",
        "doc_token": token,
        "doc_type": "",
        "image_block_count": 0,
        "saved_image_count": 0,
        "block_total": 0,
        "image_like_block_total": 0,
        "token_candidate_total": 0
    }
    if agent is None:
        debug.update({"reason_code": "agent_missing", "reason_text": "云文档代理未初始化"})
        return [], "", debug
    doc_type = ""
    resolver = getattr(agent, "resolve_url_to_doc", None)
    if callable(resolver) and str(doc_url or "").strip():
        try:
            resolved_token, resolved_type, resolved_err = resolver(doc_url)
        except Exception:
            resolved_token, resolved_type, resolved_err = "", "", ""
        if resolved_err and not token:
            info = _xiaotu_classify_image_debug(resolved_err, 0, 0)
            debug.update(info)
            debug["doc_type"] = str(resolved_type or "").strip().lower()
            return [], f"图片读取失败：{resolved_err}", debug
        if resolved_token:
            token = str(resolved_token or "").strip()
            debug["doc_token"] = token
        doc_type = str(resolved_type or "").strip().lower()
        debug["doc_type"] = doc_type
    if not token:
        info = _xiaotu_classify_image_debug("未能解析到文档token", 0, 0)
        debug.update(info)
        return [], "图片读取失败：未能解析到文档token", debug
    if doc_type and doc_type not in {"docx", "docs", "doc", ""}:
        info = _xiaotu_classify_image_debug(f"当前文档类型 {doc_type} 暂不支持图片提取", 0, 0)
        debug.update(info)
        return [], f"图片读取失败：当前文档类型 {doc_type} 暂不支持图片提取", debug

    preferred_tokens = specific_tokens if isinstance(specific_tokens, list) else None
    if preferred_tokens is not None:
        tokens = []
        seen_tokens = set()
        for one in preferred_tokens:
            t = str(one or "").strip()
            if not t or t in seen_tokens:
                continue
            seen_tokens.add(t)
            tokens.append(t)
        err = ""
        debug["block_total"] = 0
        debug["image_like_block_total"] = len(tokens)
        debug["token_candidate_total"] = len(tokens)
        if len(tokens) <= 0:
            debug.update({
                "reason_code": "daily_slice_no_image",
                "reason_text": "日报切片后未匹配到日期后的图片"
            })
    else:
        fetch_debug = getattr(agent, "fetch_docx_image_tokens_debug", None)
        if callable(fetch_debug):
            tokens, err, token_stats = fetch_debug(token, max_tokens=80, max_pages=80)
            if isinstance(token_stats, dict):
                debug["block_total"] = int(token_stats.get("block_total") or 0)
                debug["image_like_block_total"] = int(token_stats.get("image_like_block_total") or 0)
                debug["token_candidate_total"] = int(token_stats.get("token_candidate_total") or 0)
        else:
            tokens, err = agent.fetch_docx_image_tokens(token, max_tokens=80, max_pages=80)
    debug["image_block_count"] = len(tokens or [])
    if err and not tokens:
        info = _xiaotu_classify_image_debug(err, len(tokens or []), 0)
        debug.update(info)
        return [], f"图片读取失败：{err}", debug
    if not tokens:
        msg = "未识别到可下载图片（更可能是无图片块）"
        if preferred_tokens is not None:
            msg = "日报切片后未匹配到日期后的图片"
        info = _xiaotu_classify_image_debug(msg, 0, 0)
        debug.update(info)
        return [], msg, debug
    root_dir = os.path.join(r"D:\tuchuangai\报告图片", token)
    os.makedirs(root_dir, exist_ok=True)
    image_paths = []
    ocr_inputs = []
    download_errs = []
    for idx, file_token in enumerate(tokens, start=1):
        blob, mime, dl_err = agent.download_media_bytes(file_token)
        if not blob:
            if dl_err:
                download_errs.append(str(dl_err))
            continue
        mm = str(mime or "").lower()
        ext = ".jpg"
        if "png" in mm:
            ext = ".png"
        elif "webp" in mm:
            ext = ".webp"
        elif "gif" in mm:
            ext = ".gif"
        file_path = os.path.join(root_dir, f"{idx}{ext}")
        with open(file_path, "wb") as f:
            f.write(blob)
        image_paths.append(file_path)
        ocr_inputs.append((blob, mime))
    debug["saved_image_count"] = len(image_paths)
    image_ocr_text = ""
    if ocr_inputs:
        try:
            image_ocr_text = _ocr_images_bytes_with_ai(ocr_inputs) or ""
        except Exception:
            image_ocr_text = ""
    err_for_debug = ""
    if download_errs:
        err_for_debug = "；".join(download_errs[:3])
    elif err:
        err_for_debug = str(err)
    info = _xiaotu_classify_image_debug(err_for_debug, len(tokens or []), len(image_paths))
    debug.update(info)
    if err and not image_ocr_text:
        image_ocr_text = f"图片OCR提示：{err}"
    if (not image_paths) and (not image_ocr_text) and debug.get("reason_text"):
        image_ocr_text = f"图片调试：{debug.get('reason_text')}"
    return image_paths, image_ocr_text, debug


def _xiaotu_save_uploaded_images_and_ocr(files, report_token="", root_base_dir=r"D:\tuchuangai\报告图片"):
    items = files if isinstance(files, list) else []
    if not items:
        return [], "", {"reason_code": "no_upload", "reason_text": "未上传图片", "saved_image_count": 0}
    token = str(report_token or datetime.now().strftime("%Y%m%d%H%M%S")).strip() or datetime.now().strftime("%Y%m%d%H%M%S")
    base_dir = os.path.abspath(str(root_base_dir or r"D:\tuchuangai\报告图片"))
    root_dir = os.path.join(base_dir, f"upload_{token}")
    os.makedirs(root_dir, exist_ok=True)

    image_paths = []
    ocr_inputs = []
    idx = 0
    for one in items:
        if one is None:
            continue
        raw = one.read()
        if not raw:
            continue
        idx += 1
        filename = secure_filename(str(getattr(one, "filename", "") or f"img_{idx}.jpg"))
        ext = os.path.splitext(filename)[1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
            ext = ".jpg"
        save_name = f"{idx}{ext}"
        save_path = os.path.join(root_dir, save_name)
        with open(save_path, "wb") as f:
            f.write(raw)
        image_paths.append(save_path)
        mime = str(getattr(one, "mimetype", "") or "image/jpeg")
        ocr_inputs.append((raw, mime))

    image_ocr_text = ""
    if ocr_inputs:
        try:
            image_ocr_text = _ocr_images_bytes_with_ai(ocr_inputs) or ""
        except Exception:
            image_ocr_text = ""
    debug = {
        "reason_code": "ok" if image_paths else "upload_empty",
        "reason_text": "上传图片处理完成" if image_paths else "上传图片为空",
        "saved_image_count": len(image_paths)
    }
    return image_paths, str(image_ocr_text or "").strip(), debug


def _xiaotu_save_inline_html_images_and_ocr(html_text, report_token="", root_base_dir=r"D:\tuchuangai\报告图片"):
    src = str(html_text or "")
    if not src:
        return src, [], "", {"reason_code": "no_inline_image", "reason_text": "富文本中无内嵌图片", "saved_image_count": 0}

    token = str(report_token or datetime.now().strftime("%Y%m%d%H%M%S")).strip() or datetime.now().strftime("%Y%m%d%H%M%S")
    base_dir = os.path.abspath(str(root_base_dir or r"D:\tuchuangai\报告图片"))
    root_dir = os.path.join(base_dir, f"upload_{token}_inline")
    os.makedirs(root_dir, exist_ok=True)

    image_paths = []
    ocr_inputs = []
    seen_data_urls = {}
    idx = 0

    def _ext_from_mime(mime_text):
        mt = str(mime_text or "").lower()
        if "png" in mt:
            return ".png"
        if "webp" in mt:
            return ".webp"
        if "gif" in mt:
            return ".gif"
        if "bmp" in mt:
            return ".bmp"
        return ".jpg"

    def _replace(match):
        nonlocal idx
        prefix = match.group(1)
        data_url = str(match.group(2) or "").strip()
        mime_text = str(match.group(3) or "").strip()
        payload = re.sub(r"\s+", "", str(match.group(4) or ""))
        suffix = match.group(5)
        if not data_url or not payload:
            return match.group(0)
        existing = seen_data_urls.get(data_url)
        if existing:
            return f"{prefix}{existing.replace(os.sep, '/')}{suffix}"
        try:
            image_bytes = base64.b64decode(payload, validate=False)
        except Exception:
            return match.group(0)
        if not image_bytes:
            return match.group(0)
        idx += 1
        save_path = os.path.join(root_dir, f"inline_{idx}{_ext_from_mime(mime_text)}")
        with open(save_path, "wb") as f:
            f.write(image_bytes)
        image_paths.append(save_path)
        ocr_inputs.append((image_bytes, mime_text or "image/jpeg"))
        seen_data_urls[data_url] = save_path
        return f"{prefix}{save_path.replace(os.sep, '/')}{suffix}"

    updated_html = re.sub(
        r'(<img\b[^>]*\bsrc\s*=\s*["\'])(data:(image/[^;,"\']+);base64,([^"\']+))(["\'][^>]*>)',
        _replace,
        src,
        flags=re.IGNORECASE
    )

    image_ocr_text = ""
    if ocr_inputs:
        try:
            image_ocr_text = _ocr_images_bytes_with_ai(ocr_inputs) or ""
        except Exception:
            image_ocr_text = ""
    debug = {
        "reason_code": "ok" if image_paths else "no_inline_image",
        "reason_text": "富文本内嵌图片处理完成" if image_paths else "富文本中无可保存的内嵌图片",
        "saved_image_count": len(image_paths)
    }
    return updated_html, image_paths, str(image_ocr_text or "").strip(), debug


def _xiaotu_extract_feishu_file_token_from_fragment(fragment_text):
    raw = html_unescape(str(fragment_text or ""))
    if not raw:
        return ""
    patterns = [
        r'data-lark-image-uri\s*=\s*["\']\s*drivetoken://([A-Za-z0-9_-]{10,})',
        r'file_token["\']?\s*[:=]\s*["\']?([A-Za-z0-9_-]{10,})',
        r'"file_token"\s*:\s*"([A-Za-z0-9_-]{10,})"',
        r'"token"\s*:\s*"([A-Za-z0-9_-]{10,})"',
        r'drivetoken://([A-Za-z0-9_-]{10,})'
    ]
    for pat in patterns:
        m = re.search(pat, raw, flags=re.IGNORECASE)
        if m:
            return str(m.group(1) or "").strip()
    suite_match = re.search(r'data-suite\s*=\s*["\']([^"\']+)["\']', raw, flags=re.IGNORECASE)
    if suite_match:
        encoded = html_unescape(str(suite_match.group(1) or "")).strip()
        try:
            padding = "=" * ((4 - len(encoded) % 4) % 4)
            suite_text = base64.b64decode(encoded + padding).decode("utf-8", errors="ignore")
            suite_obj = json.loads(suite_text or "{}")
            token = str(suite_obj.get("fileToken") or "").strip()
            if token:
                return token
        except Exception:
            pass
    return ""


def _xiaotu_save_remote_html_images_and_ocr(html_text, report_token="", agent=None, root_base_dir=r"D:\tuchuangai\报告图片"):
    src = str(html_text or "")
    if not src:
        return src, [], "", {"reason_code": "no_remote_image", "reason_text": "富文本中无远程图片", "saved_image_count": 0}

    token = str(report_token or datetime.now().strftime("%Y%m%d%H%M%S")).strip() or datetime.now().strftime("%Y%m%d%H%M%S")
    base_dir = os.path.abspath(str(root_base_dir or r"D:\tuchuangai\报告图片"))
    root_dir = os.path.join(base_dir, f"upload_{token}_remote")
    os.makedirs(root_dir, exist_ok=True)

    image_paths = []
    ocr_inputs = []
    download_errors = []
    seen_urls = {}
    seen_tokens = {}
    idx = 0

    def _normalize_remote_url(raw):
        u = html_unescape(str(raw or "")).strip()
        u = u.strip("`").strip().strip('"').strip("'").strip()
        if not u:
            return ""
        if u.startswith("https%3A") or u.startswith("http%3A"):
            try:
                u = unquote(u)
            except Exception:
                pass
        u = u.replace("&amp;", "&")
        u = u.strip("`").strip().strip('"').strip("'").strip()
        return u

    def _save_bytes(image_bytes, mime_text, source_key):
        nonlocal idx
        if not image_bytes:
            return ""
        idx += 1
        ext = _guess_ext(source_key, mime_text)
        save_path = os.path.join(root_dir, f"remote_{idx}{ext}")
        with open(save_path, "wb") as f:
            f.write(image_bytes)
        image_paths.append(save_path)
        ocr_inputs.append((image_bytes, mime_text or "image/jpeg"))
        return save_path

    def _guess_ext(url_text, content_type):
        ct = str(content_type or "").lower()
        if "png" in ct:
            return ".png"
        if "webp" in ct:
            return ".webp"
        if "gif" in ct:
            return ".gif"
        if "bmp" in ct:
            return ".bmp"
        if "jpeg" in ct or "jpg" in ct:
            return ".jpg"
        parsed = urlparse(str(url_text or "").strip())
        ext = os.path.splitext(parsed.path or "")[1].lower()
        if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
            return ext
        guessed = mimetypes.guess_extension(ct.split(";")[0].strip()) if ct else None
        if guessed in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
            return guessed
        return ".jpg"

    def _replace(match):
        nonlocal idx
        tag = str(match.group(0) or "")
        src_match = re.search(r'(\bsrc\s*=\s*["\'])([^"\']+)(["\'])', tag, flags=re.IGNORECASE)
        if not src_match:
            return tag
        prefix = str(src_match.group(1) or "")
        raw_url = _normalize_remote_url(src_match.group(2))
        suffix = str(src_match.group(3) or "")
        file_token = _xiaotu_extract_feishu_file_token_from_fragment(tag)
        if file_token:
            existing_by_token = seen_tokens.get(file_token)
            if existing_by_token:
                return re.sub(r'(\bsrc\s*=\s*["\'])[^"\']*(["\'])', rf'\1{existing_by_token.replace(os.sep, "/")}\2', tag, count=1, flags=re.IGNORECASE)
            if agent is not None and hasattr(agent, "download_media_bytes"):
                try:
                    blob, mime, dl_err = agent.download_media_bytes(file_token)
                except Exception as e:
                    blob, mime, dl_err = b"", "", str(e)
                if blob:
                    save_path = _save_bytes(blob, mime, f"feishu_token:{file_token}")
                    if save_path:
                        seen_tokens[file_token] = save_path
                        return re.sub(r'(\bsrc\s*=\s*["\'])[^"\']*(["\'])', rf'\1{save_path.replace(os.sep, "/")}\2', tag, count=1, flags=re.IGNORECASE)
                if dl_err:
                    download_errors.append(f"token:{file_token[:40]} -> {str(dl_err)}")
        if not raw_url:
            return tag
        lower_url = raw_url.lower()
        if (
            lower_url.startswith('/api/xiaotu/report_image')
            or lower_url.startswith('data:')
            or lower_url.startswith('blob:')
            or lower_url.startswith('file://')
        ):
            return tag
        if not re.match(r"^https?://", raw_url, flags=re.IGNORECASE):
            return tag
        existing = seen_urls.get(raw_url)
        if existing:
            return re.sub(r'(\bsrc\s*=\s*["\'])[^"\']*(["\'])', rf'\1{existing.replace(os.sep, "/")}\2', tag, count=1, flags=re.IGNORECASE)
        try:
            resp = requests.get(
                raw_url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": raw_url
                },
                timeout=20
            )
            if not resp.ok or not resp.content:
                download_errors.append(f"{raw_url[:120]} -> HTTP {getattr(resp, 'status_code', 'ERR')}")
                return tag
            content_type = str(resp.headers.get("Content-Type") or "").lower()
            if content_type and ("image/" not in content_type):
                download_errors.append(f"{raw_url[:120]} -> 非图片类型 {content_type}")
                return tag
            save_path = _save_bytes(resp.content, content_type, raw_url)
            seen_urls[raw_url] = save_path
            return re.sub(r'(\bsrc\s*=\s*["\'])[^"\']*(["\'])', rf'\1{save_path.replace(os.sep, "/")}\2', tag, count=1, flags=re.IGNORECASE)
        except Exception as e:
            download_errors.append(f"{raw_url[:120]} -> {str(e)}")
            return tag

    updated_html = re.sub(
        r'<img\b[^>]*>',
        _replace,
        src,
        flags=re.IGNORECASE
    )

    image_ocr_text = ""
    if ocr_inputs:
        try:
            image_ocr_text = _ocr_images_bytes_with_ai(ocr_inputs) or ""
        except Exception:
            image_ocr_text = ""
    debug = {
        "reason_code": "ok" if image_paths else "no_remote_image",
        "reason_text": ("富文本远程图片处理完成" if image_paths else ("富文本远程图片未下载成功" if download_errors else "富文本中无远程图片")),
        "saved_image_count": len(image_paths),
        "download_error": "；".join(download_errors[:3])
    }
    return updated_html, image_paths, str(image_ocr_text or "").strip(), debug


def _xiaotu_replace_html_img_src_with_paths(html_text, image_paths):
    src = str(html_text or "")
    paths = image_paths if isinstance(image_paths, list) else []
    if not src or not paths:
        return src
    idx = 0

    def _replace(match):
        nonlocal idx
        tag = str(match.group(0) or "")
        if 'data-local-image=' not in tag.lower():
            return tag
        if idx >= len(paths):
            return tag
        safe_path = paths[idx].replace("\\", "/")
        idx += 1
        return re.sub(r'(\bsrc\s*=\s*["\'])[^"\']*(["\'])', rf'\1{safe_path}\2', tag, count=1, flags=re.IGNORECASE)

    return re.sub(r"<img\b[^>]*>", _replace, src, flags=re.IGNORECASE)


def _xiaotu_compact_report_body_for_storage(html_text, max_chars=300000):
    text = str(html_text or "")
    if not text:
        return text

    def _replace_data_img(match):
        tag = str(match.group(0) or "")
        if re.search(r'\bsrc\s*=\s*["\']data:image/', tag, flags=re.IGNORECASE):
            return '<p>[图片已作为附件保存，正文中省略内嵌图片数据]</p>'
        if re.search(r'\bsrc\s*=\s*["\']blob:', tag, flags=re.IGNORECASE):
            return '<p>[图片已作为附件保存，正文中省略临时图片数据]</p>'
        return tag

    text = re.sub(r"<img\b[^>]*>", _replace_data_img, text, flags=re.IGNORECASE)
    text = re.sub(
        r"data:image/[^;\"'\s>]+;base64,[A-Za-z0-9+/=\r\n]+",
        "[图片数据已省略]",
        text,
        flags=re.IGNORECASE
    )
    if len(text) > max_chars:
        text = text[:max_chars] + "\n<p>[正文过长，后续内容已自动截断，原图片请查看附件]</p>"
    return text


def _xiaotu_image_debug(reason_code, reason_text, saved_count=0):
    return {
        "reason_code": str(reason_code or "failed"),
        "reason_text": str(reason_text or "").strip(),
        "saved_image_count": int(saved_count or 0),
    }


def _xiaotu_save_uploaded_images_and_ocr_safe(files, report_token="", root_base_dir=r"D:\tuchuangai\报告图片"):
    try:
        return _xiaotu_save_uploaded_images_and_ocr(files, report_token=report_token, root_base_dir=root_base_dir)
    except Exception as exc:
        return [], "", _xiaotu_image_debug("upload_image_failed", exc, 0)


def _xiaotu_save_inline_html_images_and_ocr_safe(html_text, report_token="", root_base_dir=r"D:\tuchuangai\报告图片"):
    try:
        return _xiaotu_save_inline_html_images_and_ocr(html_text, report_token=report_token, root_base_dir=root_base_dir)
    except Exception as exc:
        return _xiaotu_compact_report_body_for_storage(html_text), [], "", _xiaotu_image_debug("inline_image_failed", exc, 0)


def _xiaotu_save_remote_html_images_and_ocr_safe(html_text, report_token="", agent=None, root_base_dir=r"D:\tuchuangai\报告图片"):
    try:
        return _xiaotu_save_remote_html_images_and_ocr(html_text, report_token=report_token, agent=agent, root_base_dir=root_base_dir)
    except Exception as exc:
        return _xiaotu_compact_report_body_for_storage(html_text), [], "", _xiaotu_image_debug("remote_image_failed", exc, 0)


def _xiaotu_save_doc_images_and_ocr_safe(agent, doc_token, doc_url="", specific_tokens=None):
    try:
        return _xiaotu_save_doc_images_and_ocr(agent, doc_token, doc_url=doc_url, specific_tokens=specific_tokens)
    except Exception as exc:
        return [], "", _xiaotu_image_debug("doc_image_failed", exc, 0)


def _feishu_upload_image_by_path_safe(image_path):
    try:
        return _feishu_upload_image_by_path(image_path)
    except Exception:
        return ""


def _xiaotu_extract_url_from_text(text):
    s = str(text or "").replace("`", "").strip()
    m = re.search(r"https?://[^\s\u3002\uff0c,]+", s)
    if not m:
        return ""
    return str(m.group(0) or "").strip().rstrip(")")


def _xiaotu_get_doc_candidates_for_user(user_id, force_refresh=False, user_access_token=""):
    user_depts = _xiaotu_get_user_departments(user_id)
    out = []
    for raw in (_XIAOTU_SHARED_DOCS or []):
        if not isinstance(raw, dict):
            continue
        if not _xiaotu_match_doc_permission(raw, user_depts):
            continue
        doc_id = str(raw.get("id") or "").strip()
        url = str(raw.get("url") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not doc_id or not url:
            continue
        out.append({
            "id": doc_id,
            "name": name or "未命名云文档",
            "url": url,
            "source": "shared",
            "created_at": str(raw.get("created_at") or "")
        })
    auto_docs, auto_err = _xiaotu_list_feishu_docs_for_user(
        user_id,
        force_refresh=force_refresh,
        user_access_token=user_access_token
    )
    out.extend(auto_docs)
    out.extend(_xiaotu_get_user_saved_docs(user_id))
    uniq = []
    seen_url = set()
    for d in out:
        if not isinstance(d, dict):
            continue
        u = str(d.get("url") or "").strip()
        if not u or u in seen_url:
            continue
        seen_url.add(u)
        uniq.append(d)
    return uniq, auto_err

# 注册蓝图
app.register_blueprint(review_analysis_bp)
app.register_blueprint(eyelash_analytics_bp)
app.register_blueprint(influencer_management_bp)
app.register_blueprint(model_management_bp)
app.register_blueprint(innovation_proposals_bp)
app.register_blueprint(innovation_bp)
app.register_blueprint(tk_dashboard_bp)
app.register_blueprint(bd_metrics_bp)
app.register_blueprint(knowledge_base_bp)
app.register_blueprint(seedance_web_bp, url_prefix="/seedance-web")
app.register_blueprint(yangban_inventory_bp)


def get_message_service():
    company_key = request.args.get('company', 'company1')
    return MessageService(company_key)


@app.route('/api/ai/version_update_notice', methods=['POST'])
def api_ai_version_update_notice():
    try:
        data = request.get_json(silent=True) or {}
        template_text = (data.get('template') or '').strip()
        content = (data.get('content') or '').strip()
        departments = data.get('departments')
        if isinstance(departments, str):
            departments = [departments]
        departments = [d.strip() for d in (departments or []) if str(d).strip()]
        at_all = bool(data.get('at_all'))
        if not template_text:
            return jsonify({'success': False, 'message': '话术模板不能为空'}), 400
        full_message = template_text
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        if '[更新日期]' in full_message or '【更新日期】' in full_message:
            full_message = full_message.replace('[更新日期]', now_str).replace('【更新日期】', now_str)
        if content:
            replaced = False
            for ph in ['[简要描述]', '【简要描述】', '【在这里填写本次更新的主要内容】']:
                if ph in full_message:
                    full_message = full_message.replace(ph, content)
                    replaced = True
                    break
            if not replaced:
                if full_message.endswith('\n'):
                    full_message = full_message + content
                else:
                    full_message = full_message + '\n\n' + content
        if not departments:
            return jsonify({'success': False, 'message': '推送部门不能为空'}), 400
        message_service = get_message_service()
        # 如果选择了“全部部门”，忽略其他部门，按原有全员逻辑发送
        if '__ALL__' in departments:
            rows = sf_db("SELECT DISTINCT YONGHU FROM feishu_id WHERE FeiShu_ID LIKE 'od_%' ORDER BY YONGHU")
            names = []
            if isinstance(rows, list):
                for r in rows:
                    if isinstance(r, dict) and 'YONGHU' in r:
                        names.append(r['YONGHU'])
                    elif isinstance(r, str):
                        names.append(r)
            elif isinstance(rows, dict) and 'YONGHU' in rows:
                names.append(rows['YONGHU'])
            elif isinstance(rows, str):
                names.append(rows)
            uniq = []
            seen = set()
            for n in names:
                n = (n or '').strip()
                if n and n not in seen:
                    seen.add(n)
                    uniq.append(n)
            total_success = 0
            total_failed = 0
            total_count = 0
            for dept_name in uniq:
                try:
                    r = message_service.send_message_to_department_members(dept_name, full_message, at_all=at_all)
                    total_success += r.get('success', 0)
                    total_failed += r.get('failed', 0)
                    total_count += r.get('total', 0)
                except Exception:
                    total_failed += 1
            result = {
                'success': total_success,
                'failed': total_failed,
                'total': total_count,
                'department_count': len(uniq)
            }
        else:
            total_success = 0
            total_failed = 0
            total_count = 0
            for dept_name in departments:
                try:
                    r = message_service.send_message_to_department_members(dept_name, full_message, at_all=at_all)
                    total_success += r.get('success', 0)
                    total_failed += r.get('failed', 0)
                    total_count += r.get('total', 0)
                except Exception:
                    total_failed += 1
            result = {
                'success': total_success,
                'failed': total_failed,
                'total': total_count,
                'department_count': len(departments)
            }
        return jsonify({'success': True, 'message': '发送完成', 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/ai/version_update_departments')
def api_ai_version_update_departments():
    try:
        rows = sf_db("SELECT DISTINCT YONGHU FROM feishu_id WHERE FeiShu_ID LIKE 'od_%' ORDER BY YONGHU")
        names = []
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict) and 'YONGHU' in r:
                    names.append(r['YONGHU'])
                elif isinstance(r, str):
                    names.append(r)
        elif isinstance(rows, dict) and 'YONGHU' in rows:
            names.append(rows['YONGHU'])
        elif isinstance(rows, str):
            names.append(rows)
        uniq = []
        seen = set()
        for n in names:
            n = (n or '').strip()
            if n and n not in seen:
                seen.add(n)
                uniq.append({'name': n})
        return jsonify({'success': True, 'data': uniq})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'data': []}), 500


@app.route('/api/ai/delete_innovation_project', methods=['POST'])
@require_permission('ai_dept')
def api_ai_delete_innovation_project():
    try:
        data = request.get_json(silent=True) or {}
        project_id_raw = data.get('project_id')
        project_id = str(project_id_raw or '').strip()
        if not project_id:
            return jsonify({'success': False, 'message': '项目编号不能为空'}), 400
        if not project_id.isdigit():
            return jsonify({'success': False, 'message': '项目编号必须为数字'}), 400
        sql_flow = f"DELETE FROM chuangxin_liuzhuan1 WHERE 项目编号 = {project_id}"
        sql_main = f"DELETE FROM chuangxin_tibao1 WHERE 编号 = {project_id}"
        dui_db(sql_flow)
        dui_db(sql_main)
        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500
@app.route('/dev_login')
def dev_login():
    """开发者调试登录"""
    _safe_debug_print(f"\n=== 开发者登录处理 ===")

    # 检查是否为本地开发环境
    is_local_dev = request.host.startswith('127.0.0.1') or request.host.startswith('localhost')
    _safe_debug_print(f"🏠 本地开发环境: {is_local_dev}")

    if not is_local_dev:
        _safe_debug_print(f"❌ 非本地环境，重定向到飞书授权")
        _safe_debug_print("========================\n")
        return redirect(url_for('feishu_auth'))

    user_type = request.args.get('user_type', 'bd')
    _safe_debug_print(f"👤 用户类型: {user_type}")

    # 模拟不同部门的用户
    mock_users = {
        'bd': {
            'user_id': 'dev_bd_user_001',
            'name': 'BD部测试用户',
            'email': 'bd_test@company.com',
            'department': 'BD部'
        },
        'video': {
            'user_id': 'dev_video_user_001',
            'name': '短视频部测试用户',
            'email': 'video_test@company.com',
            'department': '短视频部'
        },
        'ai': {
            'user_id': 'dev_ai_user_001',
            'name': 'AI部测试用户',
            'email': 'ai_test@company.com',
            'department': 'AI部'
        },
        'admin': {
            'user_id': 'dev_admin_user_001',
            'name': '总经办测试用户',
            'email': 'admin_test@company.com',
            'department': '总经办'
        },
        'operation1': {
            'user_id': 'dev_operation1_user_001',
            'name': '运营一部测试用户',
            'email': 'operation1_test@company.com',
            'department': '运营一部'
        },
        'operation2': {
            'user_id': 'dev_operation2_user_001',
            'name': '运营二部测试用户',
            'email': 'operation2_test@company.com',
            'department': '运营二部'
        },
        'operation3': {
            'user_id': 'dev_operation3_user_001',
            'name': '运营三部测试用户',
            'email': 'operation3_test@company.com',
            'department': '运营三部'
        },
        'operation6': {
            'user_id': 'dev_operation6_user_001',
            'name': '运营六部测试用户',
            'email': 'operation6_test@company.com',
            'department': '运营六部'
        }
    }

    user_info = mock_users.get(user_type, mock_users['bd'])
    _safe_debug_print(f"📝 选择的用户信息: {user_info}")

    raw_name = user_info['name']
    name_parts = str(raw_name).split('（', 1)
    feishu_name = name_parts[0].strip() if name_parts else str(raw_name).strip()

    session['feishu_user_id'] = user_info['user_id']
    session['feishu_user_name'] = feishu_name or raw_name
    session['feishu_user_email'] = user_info['email']
    session['feishu_user_access_token'] = 'dev_local_access_token'
    session['user_department'] = user_info['department']
    session['login_time'] = datetime.now()
    session.permanent = True
    app.permanent_session_lifetime = timedelta(hours=24)
    _xiaotu_remember_user_open_id(session.get('feishu_user_name'), session.get('feishu_user_id'))

    _safe_debug_print(f"✅ 开发者模式登录成功 - {user_info['name']} ({user_info['department']})")
    _safe_debug_print(f"📝 Session信息已设置")
    _safe_debug_print(f"🔄 重定向到dashboard")
    _safe_debug_print("========================\n")

    return redirect(url_for('dashboard'))


@app.before_request
def check_feishu_user():
    """在每个请求前检查飞书用户身份"""
    middleware_started_at = time.perf_counter()
    try:
        _start_xiaotu_report_reminder_thread_once()
    except Exception:
        pass
    _safe_debug_print(f"\n=== 请求中间件检查 ===")
    _safe_debug_print(f"请求路径: {request.path}")
    _safe_debug_print(f"请求端点: {request.endpoint}")
    _safe_debug_print(f"请求方法: {request.method}")
    _safe_debug_print(f"请求主机: {request.host}")

    # 跳过静态文件和特定路由
    if (request.endpoint in ['static', 'feishu_auth', 'feishu_callback', 'dev_login'] or
            request.path.startswith('/static/')):
        _safe_debug_print(f"⏭️ 跳过中间件检查: {request.endpoint or request.path}")
        _debug_log_elapsed(
            "before_request_skip",
            middleware_started_at,
            path=request.path,
            endpoint=request.endpoint or ""
        )
        _safe_debug_print("========================\n")
        return

    # 检查是否为本地开发环境
    is_local_dev = request.host.startswith('127.0.0.1') or request.host.startswith('localhost')
    _safe_debug_print(f"🏠 本地开发环境: {is_local_dev}")

    # 检查当前session状态
    current_user_id = session.get('feishu_user_id')
    current_open_id = str(session.get('feishu_open_id') or current_user_id or '').strip()
    current_token = str(session.get('feishu_user_access_token') or '').strip()
    request_token = str(request.headers.get('X-Lark-User-Access-Token') or '').strip()
    header_open_id = str(request.headers.get('X-Lark-Open-Id') or '').strip()
    header_user_id = str(request.headers.get('X-Lark-User-Id') or '').strip()
    header_identity = header_open_id or header_user_id
    _safe_debug_print(f"👤 当前Session用户ID: {current_user_id}")
    _safe_debug_print(f"🔑 当前Session Token存在: {bool(current_token)} | 请求头Token存在: {bool(request_token)}")
    _xiaotu_remember_user_open_id(session.get('feishu_user_name'), current_open_id)
    if header_identity:
        _safe_debug_print(f"🪪 当前请求头身份: {header_identity}")

    # 请求头身份只用于校验当前 session 是否已经串号，不直接用来认人
    if (not is_local_dev) and current_user_id and header_identity and str(current_user_id).strip() != header_identity:
        _safe_debug_print(f"⚠️ 检测到飞书身份与会话不一致: session={current_user_id}, header={header_identity}")
        _clear_feishu_identity_session()
        _debug_log_elapsed(
            "before_request_identity_mismatch",
            middleware_started_at,
            path=request.path,
            session_user_id=str(current_user_id or "").strip(),
            header_identity=header_identity
        )
        return _handle_feishu_identity_mismatch(
            is_api_request=bool(request.path.startswith('/api/') or request.headers.get('Content-Type') == 'application/json')
        )

    local_dev_session_ok = bool(is_local_dev and str(current_user_id or "").startswith("dev_"))

    # 如果session中没有用户信息，尝试从飞书上下文获取；本地开发账号不要求飞书token
    if (not local_dev_session_ok) and ((not current_user_id) or (not current_token) or request_token):
        _safe_debug_print(f"🔍 Session中无用户信息，开始身份识别...")

        if is_local_dev:
            _safe_debug_print(f"🔧 本地开发环境，跳转到开发者登录")
            _safe_debug_print("========================\n")
            # 本地开发环境，跳转到开发者登录
            return redirect(url_for('dev_login', user_type='bd'))

        _safe_debug_print(f"🌐 尝试通过当前飞书应用获取用户信息...")
        identity_started_at = time.perf_counter()
        user_info = _sync_feishu_identity_via_current_app(force_refresh=bool(request_token))
        _debug_log_elapsed(
            "before_request_identity_sync",
            identity_started_at,
            path=request.path,
            force_refresh=bool(request_token),
            ok=bool(user_info),
            has_request_token=bool(request_token)
        )
        if user_info:
            _safe_debug_print(f"✅ 中间件成功识别飞书用户: {session.get('feishu_user_id')}")
            _safe_debug_print(f"📝 Session信息已更新")
        else:
            _safe_debug_print(f"❌ 无法通过当前飞书应用获取用户信息")
    else:
        _safe_debug_print(f"✅ Session中已有用户信息: {current_user_id}")

    # Seedance 面向所有已登录用户开放
    if request.path.startswith('/seedance-web'):
        ok = _seedance_access_allowed()
        if not ok:
            _debug_log_elapsed(
                "before_request_seedance_forbidden",
                middleware_started_at,
                path=request.path,
                user_id=str(session.get('feishu_user_id') or '').strip()
            )
            if request.path.startswith('/seedance-web/api/'):
                return jsonify({'ok': False, 'error': '无权限访问 Seedance 模块'}), 403
            return redirect(url_for('tk_project'))

    _debug_log_elapsed(
        "before_request_done",
        middleware_started_at,
        path=request.path,
        endpoint=request.endpoint or "",
        user_id=str(session.get('feishu_user_id') or '').strip(),
        has_session_token=bool(session.get('feishu_user_access_token'))
    )
    _safe_debug_print("========================\n")


def _seedance_access_allowed():
    return bool(session.get('feishu_user_id'))


# AI的API密钥和配置
_AI_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "ai_runtime_config.json")
_DEFAULT_AI_CONFIG = {
    "provider": ai_runtime_config().get("provider") or "siliconflow",
    "api_key": ai_runtime_config().get("api_key") or "",
    "base_url": ai_runtime_config().get("base_url") or "https://api.siliconflow.cn/v1",
    "text_model": ai_runtime_config().get("text_model") or "Pro/moonshotai/Kimi-K2.6",
    "vision_model": ai_runtime_config().get("vision_model") or "Qwen/Qwen2.5-VL-7B-Instruct",
}


def _load_ai_runtime_config():
    cfg = dict(_DEFAULT_AI_CONFIG)
    try:
        if os.path.exists(_AI_CONFIG_PATH):
            with open(_AI_CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for key in list(cfg.keys()):
                    if key in loaded and str(loaded.get(key) or "").strip():
                        cfg[key] = str(loaded.get(key) or "").strip()
    except Exception as e:
        _safe_debug_print(f"加载AI配置文件失败: {e}")
    return cfg


AI_RUNTIME_CONFIG = _load_ai_runtime_config()
OPENAI_API_KEY = str(os.getenv("OPENAI_API_KEY") or AI_RUNTIME_CONFIG.get("api_key") or "").strip()
API_BASE_URL = str(os.getenv("OPENAI_BASE_URL") or AI_RUNTIME_CONFIG.get("base_url") or "").strip() or "https://api.siliconflow.cn/v1"

# 创建 OpenAI 客户端
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=API_BASE_URL,
    timeout=30.0  # 设置超时时间
)

_OPENAI_TEXT_MODEL = (
    os.getenv("OPENAI_TEXT_MODEL")
    or os.getenv("OPENAI_MODEL")
    or AI_RUNTIME_CONFIG.get("text_model")
    or "Pro/moonshotai/Kimi-K2.6"
).strip()
_OPENAI_VISION_MODEL = (
    os.getenv("OPENAI_VISION_MODEL")
    or AI_RUNTIME_CONFIG.get("vision_model")
    or "Qwen/Qwen2.5-VL-7B-Instruct"
).strip()
_OPENAI_TEXT_MODEL_CANDIDATES = [
    m for m in [
        _OPENAI_TEXT_MODEL,
        "Pro/moonshotai/Kimi-K2.6",
        "Qwen/Qwen3-14B",
        "Qwen/Qwen3-32B"
    ] if m
]
_OPENAI_VISION_MODEL_CANDIDATES = [
    m for m in [
        _OPENAI_VISION_MODEL,
        "Qwen/Qwen2.5-VL-7B-Instruct",
        "zai-org/GLM-4.5V"
    ] if m
]


_ai_chat_complete = partial(ai_chat_complete, client, stream=False)

# 脚本缓存
script_cache = {}
cache_lock = Lock()

# 线程池执行器
executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
_feishu_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)

FEISHU_BOT_NAME = "图创AI"
_feishu_processed_message_cache = {}
_feishu_processed_message_ttl_seconds = 600
_feishu_processed_event_cache = {}
_feishu_processed_event_ttl_seconds = 600
_feishu_recent_events = []
_feishu_recent_events_limit = 80
_feishu_debug_instance_id = os.urandom(8).hex()
_feishu_chat_memory = {}
_feishu_chat_memory_lock = Lock()
_feishu_chat_memory_ttl_seconds = 86400
_xiaotu_report_reminder_logs = []
_xiaotu_report_reminder_logs_limit = 200
_feishu_chat_memory_max_messages = 40
_XIAOTU_REPORT_CARD_MESSAGE_STORE_PATH = os.path.join(
    os.path.dirname(__file__),
    "xiaotu_report_card_messages.json"
)
_xiaotu_report_card_message_map = {}
_xiaotu_report_card_message_lock = Lock()
_xiaotu_report_card_message_store_loaded = False
_xiaotu_report_owner_open_id_map = {}
_feishu_message_text_cache = {}
_feishu_message_text_cache_ttl_seconds = 600
_feishu_message_text_cache_lock = Lock()
_feishu_skill_cache = {}
_feishu_skill_cache_ts = 0.0
_feishu_skill_cache_ttl_seconds = 120
_feishu_skill_cache_lock = Lock()


def _feishu_parse_skill_frontmatter(md_text):
    text = str(md_text or "")
    m = re.match(r'^\s*---\s*\n([\s\S]*?)\n---\s*\n?', text)
    if not m:
        return {}, text.strip()
    header = m.group(1) or ""
    body = text[m.end():].strip()
    meta = {}
    for line in header.splitlines():
        s = str(line or "").strip()
        if not s or ":" not in s:
            continue
        k, v = s.split(":", 1)
        key = str(k or "").strip().lower()
        val = str(v or "").strip().strip('"').strip("'")
        if key:
            meta[key] = val
    return meta, body


def _feishu_load_skills(force_refresh=False):
    now_ts = datetime.now().timestamp()
    with _feishu_skill_cache_lock:
        if (not force_refresh) and _feishu_skill_cache and (now_ts - float(_feishu_skill_cache_ts or 0.0) <= _feishu_skill_cache_ttl_seconds):
            return dict(_feishu_skill_cache)
    base_dir = os.path.dirname(__file__)
    bootstrap_lark_cli_skills_env(base_dir)
    candidate_dirs = get_skill_root_candidates(base_dir)
    found = {}
    for root in candidate_dirs:
        if not root or (not os.path.isdir(root)):
            continue
        try:
            skill_dirs = [os.path.join(root, n) for n in os.listdir(root)]
        except Exception:
            skill_dirs = []
        for sd in skill_dirs:
            if not os.path.isdir(sd):
                continue
            skill_file = os.path.join(sd, "SKILL.md")
            if not os.path.isfile(skill_file):
                continue
            try:
                with open(skill_file, "r", encoding="utf-8") as f:
                    raw = f.read()
            except Exception:
                continue
            meta, body = _feishu_parse_skill_frontmatter(raw)
            name = str(meta.get("name") or os.path.basename(sd) or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in found:
                continue
            found[key] = {
                "name": name,
                "description": str(meta.get("description") or "").strip(),
                "detail": str(body or "").strip(),
                "path": skill_file
            }
    with _feishu_skill_cache_lock:
        _feishu_skill_cache.clear()
        _feishu_skill_cache.update(found)
        globals()["_feishu_skill_cache_ts"] = now_ts
        return dict(_feishu_skill_cache)


def _feishu_get_skill(skill_name):
    name = str(skill_name or "").strip()
    if not name:
        return None
    all_skills = _feishu_load_skills(force_refresh=False)
    return all_skills.get(name.lower())


def _feishu_render_skill_list():
    all_skills = _feishu_load_skills(force_refresh=True)
    if not all_skills:
        return "当前没有可用技能。请先把技能放到 .trae/skills/<skill-name>/SKILL.md，或配置环境变量 LARK_CLI_SKILLS_DIR 指向技能目录。"
    lines = ["已加载技能："]
    for k in sorted(all_skills.keys()):
        sk = all_skills.get(k) or {}
        nm = str(sk.get("name") or k)
        desc = str(sk.get("description") or "").strip()
        if desc:
            lines.append(f"- {nm}：{desc}")
        else:
            lines.append(f"- {nm}")
    lines.append("用法：/skill 技能名 你的问题")
    return "\n".join(lines)


def _feishu_parse_skill_invocation(text):
    t = str(text or "").strip()
    if not t:
        return {"mode": "", "skill": "", "question": ""}
    low = t.lower()
    if low in {"/skills", "skills", "技能列表"}:
        return {"mode": "list", "skill": "", "question": ""}
    m = re.match(r"^/(?:skill|技能)\s+([A-Za-z0-9._-]+)\s*(.*)$", t, flags=re.IGNORECASE)
    if m:
        return {"mode": "invoke", "skill": str(m.group(1) or "").strip(), "question": str(m.group(2) or "").strip()}
    m = re.match(r"^使用技能[:：\s]+([A-Za-z0-9._-]+)\s*[:：]?\s*(.*)$", t, flags=re.IGNORECASE)
    if m:
        return {"mode": "invoke", "skill": str(m.group(1) or "").strip(), "question": str(m.group(2) or "").strip()}
    return {"mode": "", "skill": "", "question": ""}


def _feishu_submit_task(task_func, *args):
    future = _feishu_executor.submit(task_func, *args)
    def _done_callback(f):
        try:
            err = f.exception()
            if err:
                _safe_debug_print(f"飞书异步任务异常: {err}")
        except Exception as e:
            _safe_debug_print(f"飞书异步任务回调异常: {e}")
    future.add_done_callback(_done_callback)
    return future


def _feishu_is_message_processed(message_id):
    if not message_id:
        return False
    now = datetime.now().timestamp()
    expired_keys = [k for k, v in _feishu_processed_message_cache.items() if (now - v) > _feishu_processed_message_ttl_seconds]
    for k in expired_keys:
        _feishu_processed_message_cache.pop(k, None)
    last = _feishu_processed_message_cache.get(message_id)
    return bool(last)


def _feishu_mark_message_processed(message_id):
    if not message_id:
        return
    _feishu_processed_message_cache[message_id] = datetime.now().timestamp()


def _feishu_is_event_processed(event_id):
    if not event_id:
        return False
    now = datetime.now().timestamp()
    expired_keys = [k for k, v in _feishu_processed_event_cache.items() if (now - v) > _feishu_processed_event_ttl_seconds]
    for k in expired_keys:
        _feishu_processed_event_cache.pop(k, None)
    last = _feishu_processed_event_cache.get(event_id)
    return bool(last)


def _feishu_mark_event_processed(event_id):
    if not event_id:
        return
    _feishu_processed_event_cache[event_id] = datetime.now().timestamp()


def _feishu_memory_prune_locked(now_ts):
    expired = []
    for cid, item in (_feishu_chat_memory or {}).items():
        if not isinstance(item, dict):
            expired.append(cid)
            continue
        ts = item.get("ts")
        if not ts or (now_ts - float(ts)) > _feishu_chat_memory_ttl_seconds:
            expired.append(cid)
    for cid in expired:
        _feishu_chat_memory.pop(cid, None)


def _feishu_get_chat_history(chat_id):
    cid = str(chat_id or "").strip()
    if not cid:
        return []
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid) or {}
        msgs = item.get("messages") or []
        if not isinstance(msgs, list):
            msgs = []
        return [{"role": m.get("role"), "content": m.get("content")} for m in msgs if isinstance(m, dict) and m.get("role") and m.get("content")]


def _feishu_append_chat_history(chat_id, role, content):
    cid = str(chat_id or "").strip()
    if not cid:
        return
    r = str(role or "").strip()
    c = (content or "").strip()
    if not r or not c:
        return
    resources = _feishu_extract_resources_from_text(c)
    if len(c) > 1200:
        c = c[:1200].strip()
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid)
        if not isinstance(item, dict):
            item = {"ts": now_ts, "messages": [], "resources": []}
        msgs = item.get("messages")
        if not isinstance(msgs, list):
            msgs = []
        msgs.append({"role": r, "content": c})
        if len(msgs) > _feishu_chat_memory_max_messages:
            msgs = msgs[-_feishu_chat_memory_max_messages:]
        if resources:
            lst = item.get("resources")
            if not isinstance(lst, list):
                lst = []
            seen = {str((x or {}).get("url") or "").strip() for x in lst if isinstance(x, dict)}
            for rr in resources:
                u = str((rr or {}).get("url") or "").strip()
                if not u or u in seen:
                    continue
                seen.add(u)
                lst.append({"type": rr.get("type"), "url": u, "ts": now_ts})
            if len(lst) > 20:
                lst = lst[-20:]
            item["resources"] = lst
        if r == "assistant":
            item["last_bot_ts"] = now_ts
        item["ts"] = now_ts
        item["messages"] = msgs
        _feishu_chat_memory[cid] = item


def _feishu_clear_chat_history(chat_id):
    cid = str(chat_id or "").strip()
    if not cid:
        return
    with _feishu_chat_memory_lock:
        _feishu_chat_memory.pop(cid, None)


def _feishu_extract_resources_from_text(text):
    t = str(text or "").strip()
    if not t:
        return []
    out = []
    try:
        bitable_url = _feishu_find_bitable_url(t)
        if bitable_url:
            out.append({"type": "bitable", "url": bitable_url})
    except Exception:
        pass
    try:
        doc_url = _feishu_find_cloud_doc_url_any(t)
        if doc_url:
            out.append({"type": "cloud_doc", "url": doc_url})
    except Exception:
        pass
    return out


def _feishu_remember_resources(chat_id, text):
    cid = str(chat_id or "").strip()
    if not cid:
        return
    resources = _feishu_extract_resources_from_text(text)
    if not resources:
        return
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid)
        if not isinstance(item, dict):
            item = {"ts": now_ts, "messages": [], "resources": []}
        lst = item.get("resources")
        if not isinstance(lst, list):
            lst = []
        seen = {str((r or {}).get("url") or "").strip() for r in lst if isinstance(r, dict)}
        for r in resources:
            u = str((r or {}).get("url") or "").strip()
            if not u or u in seen:
                continue
            seen.add(u)
            lst.append({"type": r.get("type"), "url": u, "ts": now_ts})
        if len(lst) > 20:
            lst = lst[-20:]
        item["resources"] = lst
        item["ts"] = now_ts
        _feishu_chat_memory[cid] = item


def _feishu_remember_image_resource(chat_id, key, message_id="", resource_type="image", file_name=""):
    cid = str(chat_id or "").strip()
    k = str(key or "").strip()
    if not cid or not k:
        return
    rt = str(resource_type or "").strip().lower() or "image"
    mid = str(message_id or "").strip()
    fn = str(file_name or "").strip()
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid)
        if not isinstance(item, dict):
            item = {"ts": now_ts, "messages": [], "resources": []}
        lst = item.get("resources")
        if not isinstance(lst, list):
            lst = []
        seen = {str((r or {}).get("url") or "").strip() for r in lst if isinstance(r, dict)}
        if k not in seen:
            lst.append({"type": "image", "url": k, "ts": now_ts, "message_id": mid, "resource_type": rt, "file_name": fn})
        if len(lst) > 20:
            lst = lst[-20:]
        item["resources"] = lst
        item["ts"] = now_ts
        _feishu_chat_memory[cid] = item


def _feishu_get_last_bot_ts(chat_id):
    cid = str(chat_id or "").strip()
    if not cid:
        return 0.0
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid) or {}
        try:
            return float(item.get("last_bot_ts") or 0.0)
        except Exception:
            return 0.0


def _feishu_get_last_resource(chat_id, prefer_type=""):
    cid = str(chat_id or "").strip()
    if not cid:
        return None
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid) or {}
        lst = item.get("resources") or []
        if not isinstance(lst, list) or not lst:
            return None
        if prefer_type:
            for r in reversed(lst):
                if isinstance(r, dict) and r.get("type") == prefer_type and r.get("url"):
                    return r
        for r in reversed(lst):
            if isinstance(r, dict) and r.get("url") and r.get("type"):
                return r
    return None


def _feishu_is_message_id(value):
    s = str(value or "").strip()
    if not s:
        return False
    if s.startswith("om_") or s.startswith("mid_") or s.startswith("msg_"):
        return True
    return False


def _feishu_extract_reference_message_ids(message_obj, content_obj=None):
    msg = message_obj if isinstance(message_obj, dict) else {}
    cont = content_obj if isinstance(content_obj, dict) else {}
    keys = {
        "parent_id", "parent_message_id", "root_id", "root_message_id",
        "quote_message_id", "quoted_message_id", "reference_message_id", "referenced_message_id"
    }
    out = []
    seen = set()

    def add(v):
        s = str(v or "").strip()
        if not s or not _feishu_is_message_id(s):
            return
        if s in seen:
            return
        seen.add(s)
        out.append(s)

    for k in keys:
        add(msg.get(k))
        add(cont.get(k))

    def walk(x):
        if x is None:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                lk = str(k or "").strip().lower()
                if lk in keys:
                    add(v)
                walk(v)
            return
        if isinstance(x, list):
            for it in x:
                walk(it)
            return

    walk(msg)
    walk(cont)
    return out


def _feishu_get_message_text(message_id):
    mid = str(message_id or "").strip()
    if not mid:
        return ""
    now_ts = datetime.now().timestamp()
    with _feishu_message_text_cache_lock:
        expired = [k for k, v in (_feishu_message_text_cache or {}).items() if not isinstance(v, dict) or (now_ts - float(v.get("ts") or 0)) > _feishu_message_text_cache_ttl_seconds]
        for k in expired:
            _feishu_message_text_cache.pop(k, None)
        cached = _feishu_message_text_cache.get(mid)
        if isinstance(cached, dict) and cached.get("text"):
            return str(cached.get("text") or "")

    token = permission_manager.get_access_token() if hasattr(permission_manager, "get_access_token") else ""
    token = str(token or "").strip()
    if not token:
        return ""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}"
    try:
        resp = _feishu_http.get(url, headers=headers, timeout=12)
        data = resp.json() if resp is not None else None
    except Exception:
        data = None
    if not isinstance(data, dict) or int(data.get("code") or 0) != 0:
        return ""
    d = data.get("data") or {}
    msg = (d.get("message") if isinstance(d, dict) else None) or (d.get("items") or [None])[0]
    body = (msg or {}).get("body") if isinstance(msg, dict) else None
    content = ""
    if isinstance(body, dict) and body.get("content") is not None:
        content = body.get("content")
    elif isinstance(msg, dict) and msg.get("content") is not None:
        content = msg.get("content")
    elif isinstance(msg, dict) and msg.get("body") is not None:
        try:
            content = (msg.get("body") or {}).get("content")
        except Exception:
            content = ""
    text = _feishu_extract_text_from_content(content)
    text = str(text or "").strip()
    if text:
        with _feishu_message_text_cache_lock:
            _feishu_message_text_cache[mid] = {"ts": now_ts, "text": text}
    return text


def _feishu_extract_text_from_content(content):
    if not content:
        return ""
    if isinstance(content, dict):
        if "text" in content:
            return str(content.get("text") or "").strip()
        if "zh_cn" in content:
            try:
                blocks = content.get("zh_cn", {}).get("content") or []
                parts = []
                for block in blocks:
                    if not isinstance(block, list):
                        continue
                    for el in block:
                        if not isinstance(el, dict):
                            continue
                        if el.get("tag") == "text" and el.get("text"):
                            parts.append(str(el.get("text")))
                        elif el.get("tag") == "at" and el.get("user_name"):
                            parts.append(f"@{el.get('user_name')}")
                return " ".join([p for p in parts if str(p).strip()]).strip()
            except Exception:
                return ""
        return ""
    if isinstance(content, str):
        try:
            payload = json.loads(content)
            if isinstance(payload, dict):
                if "text" in payload:
                    return str(payload.get("text") or "").strip()
                if "zh_cn" in payload:
                    return _feishu_extract_text_from_content(payload)
        except Exception:
            return str(content).strip()
    return str(content).strip()


def _feishu_is_group_message(chat_type):
    return str(chat_type or "").lower() in {"group", "chat"}


def _feishu_is_p2p_message(chat_type):
    return str(chat_type or "").lower() in {"p2p", "single"}


def _feishu_is_bot_mentioned(text, mentions):
    if isinstance(mentions, list):
        for m in mentions:
            name = str(m.get("name") or "").strip() if isinstance(m, dict) else ""
            if name and (FEISHU_BOT_NAME in name):
                return True
    return FEISHU_BOT_NAME in (text or "")


def _feishu_clean_question(text):
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace(f"@{FEISHU_BOT_NAME}", "").replace(FEISHU_BOT_NAME, "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _feishu_send_text_to_chat(chat_id, message_text):
    try:
        token = permission_manager.get_access_token()
        if not token:
            _safe_debug_print("❌ 发送飞书消息失败: access_token为空")
            return False
        import requests
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        payload = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": message_text}, ensure_ascii=False)
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=10).json()
        _safe_debug_print(f"飞书消息发送响应: {resp}")
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "send_result",
                "chat_id": chat_id,
                "ok": resp.get("code") == 0,
                "resp": resp,
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
        return resp.get("code") == 0
    except Exception as e:
        _safe_debug_print(f"❌ 发送飞书消息失败: {e}")
        return False


def _xiaotu_remember_report_card_message(wendangid, receive_id, message_id):
    _xiaotu_ensure_report_card_message_store_loaded()
    wid = str(wendangid or "").strip()
    rid = str(receive_id or "").strip()
    mid = str(message_id or "").strip()
    if not wid or not rid or not mid:
        return
    with _xiaotu_report_card_message_lock:
        bucket = _xiaotu_report_card_message_map.get(wid) or {}
        if not isinstance(bucket, dict):
            bucket = {}
        now_ts = datetime.now().timestamp()
        old_item = bucket.get(rid) or {}
        message_ids = []
        if isinstance(old_item, dict):
            old_ids = old_item.get("message_ids") or []
            if isinstance(old_ids, list):
                for old in old_ids:
                    if isinstance(old, dict):
                        old_mid = str(old.get("message_id") or "").strip()
                        if old_mid:
                            message_ids.append({
                                "message_id": old_mid,
                                "ts": float(old.get("ts") or 0) if str(old.get("ts") or "").strip() else 0
                            })
                    else:
                        old_mid = str(old or "").strip()
                        if old_mid:
                            message_ids.append({"message_id": old_mid, "ts": 0})
            old_mid = str(old_item.get("message_id") or "").strip()
            if old_mid and not any(str(x.get("message_id") or "").strip() == old_mid for x in message_ids):
                message_ids.append({
                    "message_id": old_mid,
                    "ts": float(old_item.get("ts") or 0) if str(old_item.get("ts") or "").strip() else 0
                })
        deduped = []
        seen = set()
        for item in sorted(message_ids, key=lambda x: float(x.get("ts") or 0)):
            item_mid = str(item.get("message_id") or "").strip()
            if not item_mid or item_mid in seen or item_mid == mid:
                continue
            seen.add(item_mid)
            deduped.append({
                "message_id": item_mid,
                "ts": float(item.get("ts") or 0)
            })
        deduped.append({
            "message_id": mid,
            "ts": now_ts
        })
        bucket[rid] = {
            "message_id": mid,
            "ts": now_ts,
            "message_ids": deduped[-8:]
        }
        _xiaotu_report_card_message_map[wid] = bucket
        _xiaotu_save_report_card_message_store_locked()


def _xiaotu_ensure_report_card_message_store_loaded():
    global _xiaotu_report_card_message_store_loaded
    if _xiaotu_report_card_message_store_loaded:
        return
    with _xiaotu_report_card_message_lock:
        if _xiaotu_report_card_message_store_loaded:
            return
        loaded_map = {}
        try:
            if os.path.exists(_XIAOTU_REPORT_CARD_MESSAGE_STORE_PATH):
                with open(_XIAOTU_REPORT_CARD_MESSAGE_STORE_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    for wid, bucket in raw.items():
                        wid_key = str(wid or "").strip()
                        if not wid_key or not isinstance(bucket, dict):
                            continue
                        normalized_bucket = {}
                        for rid, item in bucket.items():
                            rid_key = str(rid or "").strip()
                            if not rid_key or not isinstance(item, dict):
                                continue
                            latest_mid = str(item.get("message_id") or "").strip()
                            latest_ts = float(item.get("ts") or 0)
                            message_ids = []
                            for raw_item in (item.get("message_ids") or []):
                                if isinstance(raw_item, dict):
                                    raw_mid = str(raw_item.get("message_id") or "").strip()
                                    raw_ts = float(raw_item.get("ts") or 0)
                                else:
                                    raw_mid = str(raw_item or "").strip()
                                    raw_ts = 0
                                if raw_mid:
                                    message_ids.append({
                                        "message_id": raw_mid,
                                        "ts": raw_ts
                                    })
                            if latest_mid and not any(str(x.get("message_id") or "").strip() == latest_mid for x in message_ids):
                                message_ids.append({
                                    "message_id": latest_mid,
                                    "ts": latest_ts
                                })
                            if latest_mid or message_ids:
                                normalized_bucket[rid_key] = {
                                    "message_id": latest_mid or str((message_ids[-1] or {}).get("message_id") or "").strip(),
                                    "ts": latest_ts,
                                    "message_ids": message_ids[-8:]
                                }
                        if normalized_bucket:
                            loaded_map[wid_key] = normalized_bucket
        except Exception:
            loaded_map = {}
        _xiaotu_report_card_message_map.clear()
        _xiaotu_report_card_message_map.update(loaded_map)
        _xiaotu_report_card_message_store_loaded = True


def _xiaotu_save_report_card_message_store_locked():
    try:
        payload = {}
        for wid, bucket in (_xiaotu_report_card_message_map or {}).items():
            wid_key = str(wid or "").strip()
            if not wid_key or not isinstance(bucket, dict):
                continue
            normalized_bucket = {}
            for rid, item in bucket.items():
                rid_key = str(rid or "").strip()
                if not rid_key or not isinstance(item, dict):
                    continue
                latest_mid = str(item.get("message_id") or "").strip()
                latest_ts = float(item.get("ts") or 0)
                message_ids = []
                seen = set()
                for raw_item in (item.get("message_ids") or []):
                    if not isinstance(raw_item, dict):
                        raw_mid = str(raw_item or "").strip()
                        raw_ts = 0
                    else:
                        raw_mid = str(raw_item.get("message_id") or "").strip()
                        raw_ts = float(raw_item.get("ts") or 0)
                    if not raw_mid or raw_mid in seen:
                        continue
                    seen.add(raw_mid)
                    message_ids.append({
                        "message_id": raw_mid,
                        "ts": raw_ts
                    })
                if latest_mid and latest_mid not in seen:
                    message_ids.append({
                        "message_id": latest_mid,
                        "ts": latest_ts
                    })
                if latest_mid or message_ids:
                    normalized_bucket[rid_key] = {
                        "message_id": latest_mid or str((message_ids[-1] or {}).get("message_id") or "").strip(),
                        "ts": latest_ts,
                        "message_ids": message_ids[-8:]
                    }
            if normalized_bucket:
                payload[wid_key] = normalized_bucket
        with open(_XIAOTU_REPORT_CARD_MESSAGE_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        pass


def _xiaotu_get_report_card_message_ids(wendangid, receive_id=""):
    _xiaotu_ensure_report_card_message_store_loaded()
    wid = str(wendangid or "").strip()
    rid = str(receive_id or "").strip()
    if not wid:
        return []
    with _xiaotu_report_card_message_lock:
        bucket = _xiaotu_report_card_message_map.get(wid) or {}
        if not isinstance(bucket, dict):
            return []
        items = []
        if rid:
            items = [bucket.get(rid) or {}]
        else:
            items = list(bucket.values())
    message_ids = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        candidates = []
        raw_ids = item.get("message_ids") or []
        if isinstance(raw_ids, list):
            for raw in raw_ids:
                if isinstance(raw, dict):
                    candidate_mid = str(raw.get("message_id") or "").strip()
                else:
                    candidate_mid = str(raw or "").strip()
                if candidate_mid:
                    candidates.append(candidate_mid)
        latest_mid = str(item.get("message_id") or "").strip()
        if latest_mid:
            candidates.append(latest_mid)
        for candidate_mid in candidates:
            if candidate_mid and candidate_mid not in seen:
                seen.add(candidate_mid)
                message_ids.append(candidate_mid)
    return message_ids


def _xiaotu_get_report_card_message_id(wendangid, receive_id=""):
    message_ids = _xiaotu_get_report_card_message_ids(wendangid, receive_id)
    return message_ids[-1] if message_ids else ""


def _xiaotu_get_report_card_receive_ids(wendangid):
    _xiaotu_ensure_report_card_message_store_loaded()
    wid = str(wendangid or "").strip()
    if not wid:
        return []
    with _xiaotu_report_card_message_lock:
        bucket = _xiaotu_report_card_message_map.get(wid) or {}
        if not isinstance(bucket, dict):
            return []
        return [
            str(receive_id or "").strip()
            for receive_id in bucket.keys()
            if str(receive_id or "").strip()
        ]


def _xiaotu_forget_report_card_messages(wendangid):
    _xiaotu_ensure_report_card_message_store_loaded()
    wid = str(wendangid or "").strip()
    if not wid:
        return
    with _xiaotu_report_card_message_lock:
        if wid in _xiaotu_report_card_message_map:
            _xiaotu_report_card_message_map.pop(wid, None)
            _xiaotu_save_report_card_message_store_locked()


def _xiaotu_collect_report_card_message_entries(wendangid, latest_only=False):
    wid = str(wendangid or "").strip()
    if not wid:
        return []
    out = []
    seen = set()
    for receive_id in _xiaotu_get_report_card_receive_ids(wid):
        rid = str(receive_id or "").strip()
        message_ids = (
            [_xiaotu_get_report_card_message_id(wid, rid)]
            if latest_only else
            _xiaotu_get_report_card_message_ids(wid, rid)
        )
        for message_id in message_ids:
            mid = str(message_id or "").strip()
            if not mid or mid in seen:
                continue
            seen.add(mid)
            out.append({
                "receive_id": rid,
                "message_id": mid,
            })
    return out


def _xiaotu_get_report_row(wendangid):
    wid = str(wendangid or "").strip()
    if not wid:
        return {}
    esc_wid = _xiaotu_sql_escape(wid)
    sql = f"""
        SELECT TOP 1
            WenDangID,
            BiaoTi,
            ZhengWen,
            TuPianLujin,
            XingMing,
            RiQi,
            PingJia,
            TuPianNeiRong,
            LeiXing,
            RenYuanLeiXing,
            JieShouRen
        FROM baogao
        WHERE WenDangID = '{esc_wid}'
        ORDER BY RiQi DESC
    """
    rows = sf_db(sql) or []
    row = rows[0] if isinstance(rows, list) and rows else rows
    if isinstance(row, dict):
        return {
            "wendangid": str(row.get("WenDangID") or wid).strip(),
            "biaoti": str(row.get("BiaoTi") or "").strip(),
            "zhengwen": str(row.get("ZhengWen") or "").strip(),
            "tupianlujin": str(row.get("TuPianLujin") or "").strip(),
            "xingming": str(row.get("XingMing") or "").strip(),
            "riqi": str(row.get("RiQi") or "").strip(),
            "pingjia": str(row.get("PingJia") or "").strip(),
            "tupianneirong": str(row.get("TuPianNeiRong") or "").strip(),
            "leixing": str(row.get("LeiXing") or "").strip(),
            "renyuanleixing": str(row.get("RenYuanLeiXing") or "").strip(),
            "jieshouren": str(row.get("JieShouRen") or "").strip(),
        }
    if isinstance(row, (list, tuple)):
        values = list(row)
        return {
            "wendangid": str(values[0] if len(values) > 0 else wid).strip(),
            "biaoti": str(values[1] if len(values) > 1 else "").strip(),
            "zhengwen": str(values[2] if len(values) > 2 else "").strip(),
            "tupianlujin": str(values[3] if len(values) > 3 else "").strip(),
            "xingming": str(values[4] if len(values) > 4 else "").strip(),
            "riqi": str(values[5] if len(values) > 5 else "").strip(),
            "pingjia": str(values[6] if len(values) > 6 else "").strip(),
            "tupianneirong": str(values[7] if len(values) > 7 else "").strip(),
            "leixing": str(values[8] if len(values) > 8 else "").strip(),
            "renyuanleixing": str(values[9] if len(values) > 9 else "").strip(),
            "jieshouren": str(values[10] if len(values) > 10 else "").strip(),
        }
    return {}


def _xiaotu_get_report_owner_open_id_resolved(wendangid, report_row=None):
    wid = str(wendangid or "").strip()
    if not wid:
        return ""
    remembered = str(_xiaotu_get_report_owner_open_id(wid) or "").strip()
    if remembered.startswith("ou_"):
        return remembered
    row = report_row if isinstance(report_row, dict) else _xiaotu_get_report_row(wid)
    owner_name = str((row or {}).get("xingming") or "").strip()
    owner_open_id = str(_xiaotu_lookup_open_id_by_name(owner_name) or "").strip()
    if owner_open_id.startswith("ou_"):
        _xiaotu_remember_report_owner_open_id(wid, owner_open_id)
        return owner_open_id
    return ""


def _feishu_get_message_read_users(message_id, user_id_type="open_id", page_size=100):
    mid = str(message_id or "").strip()
    uid_type = str(user_id_type or "").strip() or "open_id"
    if not mid:
        return [], "缺少消息ID"
    try:
        token = permission_manager.get_access_token()
        if not token:
            return [], "获取飞书访问令牌失败"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        out = []
        seen = set()
        page_token = ""
        loops = 0
        while True:
            loops += 1
            params = {
                "user_id_type": uid_type,
                "page_size": max(1, min(100, int(page_size or 100))),
            }
            if page_token:
                params["page_token"] = page_token
            resp = _feishu_http.get(
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}/read_users",
                headers=headers,
                params=params,
                timeout=10
            )
            data = resp.json() if resp is not None else {}
            resp_code = int(data.get("code")) if isinstance(data, dict) and str(data.get("code")).strip() != "" else -1
            if not resp or resp.status_code != 200 or not isinstance(data, dict) or resp_code != 0:
                return out, str((data or {}).get("msg") or (data or {}).get("message") or data or f"HTTP {getattr(resp, 'status_code', 'unknown')}")
            data_obj = data.get("data") or {}
            for item in (data_obj.get("items") or []):
                if not isinstance(item, dict):
                    continue
                uid = str(item.get("user_id") or "").strip()
                if uid and uid not in seen:
                    seen.add(uid)
                    out.append(uid)
            if not data_obj.get("has_more"):
                break
            page_token = str(data_obj.get("page_token") or "").strip()
            if not page_token or loops >= 20:
                break
        return out, ""
    except Exception as e:
        return [], str(e)


def _feishu_recall_message(message_id):
    mid = str(message_id or "").strip()
    if not mid:
        return False, "缺少消息ID", {}
    try:
        token = permission_manager.get_access_token()
        if not token:
            return False, "获取飞书访问令牌失败", {}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        resp = _feishu_http.delete(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}",
            headers=headers,
            timeout=10
        )
        data = resp.json() if resp is not None else {}
        resp_code = int(data.get("code")) if isinstance(data, dict) and str(data.get("code")).strip() != "" else -1
        if resp and resp.status_code == 200 and isinstance(data, dict) and resp_code == 0:
            return True, "", data
        if isinstance(data, dict) and resp_code == 230110:
            return True, "", data
        return False, str((data or {}).get("msg") or (data or {}).get("message") or data or f"HTTP {getattr(resp, 'status_code', 'unknown')}"), data
    except Exception as e:
        return False, str(e), {}


def _xiaotu_guess_report_default_notify_open_ids(owner_open_id, owner_name=""):
    owner_oid = str(owner_open_id or "").strip()
    owner_nm = str(owner_name or "").strip()
    if not owner_oid:
        return []
    out = []
    seen = set()
    try:
        primary_dept_id, _primary_dept_name = _xiaotu_pick_primary_department(owner_oid)
        dept_leader_user_id = str(_xiaotu_get_department_leader_user_id(primary_dept_id) or "").strip()
        if dept_leader_user_id and dept_leader_user_id != owner_oid:
            seen.add(dept_leader_user_id)
            out.append(dept_leader_user_id)
        elif dept_leader_user_id and dept_leader_user_id == owner_oid:
            target_name = str(_XIAOTU_REPORT_ESCALATION_USER or "").strip()
            if target_name and target_name != owner_nm:
                escalation_open_id = str(_xiaotu_lookup_open_id_by_name(target_name) or "").strip()
                if escalation_open_id and escalation_open_id != owner_oid and escalation_open_id not in seen:
                    seen.add(escalation_open_id)
                    out.append(escalation_open_id)
    except Exception:
        return out
    return out


def _xiaotu_collect_report_delivery_targets(wendangid, report_row=None):
    wid = str(wendangid or "").strip()
    row = report_row if isinstance(report_row, dict) else _xiaotu_get_report_row(wid)
    owner_open_id = _xiaotu_get_report_owner_open_id_resolved(wid, row)
    owner_name = str((row or {}).get("xingming") or "").strip()
    targets = []
    seen_open_ids = set()
    unresolved_names = []
    seen_names = set()

    def _append_target(open_id="", name="", source=""):
        oid = str(open_id or "").strip()
        nm = str(name or "").strip()
        src = str(source or "").strip()
        if oid:
            if oid == owner_open_id or oid in seen_open_ids:
                return
            seen_open_ids.add(oid)
            targets.append({
                "open_id": oid,
                "name": nm,
                "source": src,
            })
            return
        if nm and nm != owner_name and nm not in seen_names:
            seen_names.add(nm)
            unresolved_names.append(nm)

    for receive_id in _xiaotu_get_report_card_receive_ids(wid):
        _append_target(receive_id, source="message_store")

    for notify_name in _xiaotu_split_cache_multi_value((row or {}).get("jieshouren") or ""):
        resolved_open_id = str(_xiaotu_lookup_open_id_by_name(notify_name) or "").strip()
        _append_target(resolved_open_id, notify_name, source="report_row")

    if not targets and not unresolved_names:
        for open_id in _xiaotu_guess_report_default_notify_open_ids(owner_open_id, owner_name):
            _append_target(open_id, source="default_policy")

    missing_name_open_ids = [str(item.get("open_id") or "").strip() for item in targets if str(item.get("open_id") or "").strip() and not str(item.get("name") or "").strip()]
    if missing_name_open_ids:
        name_map = _xiaotu_query_user_names_by_open_ids(missing_name_open_ids) or {}
        for item in targets:
            oid = str(item.get("open_id") or "").strip()
            if oid and not str(item.get("name") or "").strip():
                item["name"] = str(name_map.get(oid) or "").strip()

    return {
        "owner_open_id": owner_open_id,
        "targets": targets,
        "unresolved_names": unresolved_names,
    }


def _xiaotu_get_report_delivery_status(wendangid, report_row=None):
    wid = str(wendangid or "").strip()
    row = report_row if isinstance(report_row, dict) else _xiaotu_get_report_row(wid)
    delivery_targets_info = _xiaotu_collect_report_delivery_targets(wid, row)
    owner_open_id = str((delivery_targets_info or {}).get("owner_open_id") or "").strip()
    notify_targets = list((delivery_targets_info or {}).get("targets") or [])
    unresolved_names = list((delivery_targets_info or {}).get("unresolved_names") or [])
    total_targets = len(notify_targets) + len(unresolved_names)
    read_count = 0
    unread_count = 0
    unknown_count = 0
    items = []
    notify_open_ids = []
    for notify_target in notify_targets:
        oid = str((notify_target or {}).get("open_id") or "").strip()
        if not oid:
            continue
        notify_open_ids.append(oid)
        message_id = _xiaotu_get_report_card_message_id(wid, oid)
        read_users = []
        err = ""
        if message_id:
            read_users, err = _feishu_get_message_read_users(message_id, user_id_type="open_id")
        else:
            err = "未找到消息ID"
        is_read = None
        if err:
            unknown_count += 1
        else:
            is_read = bool(oid in set(read_users))
            if is_read:
                read_count += 1
            else:
                unread_count += 1
        items.append({
            "open_id": oid,
            "name": str((notify_target or {}).get("name") or "").strip(),
            "message_id": message_id,
            "is_read": is_read,
            "error": str(err or "").strip(),
            "source": str((notify_target or {}).get("source") or "").strip(),
        })
    for notify_name in unresolved_names:
        unknown_count += 1
        items.append({
            "open_id": "",
            "name": str(notify_name or "").strip(),
            "message_id": "",
            "is_read": None,
            "error": "未找到接收人飞书ID",
            "source": "report_row_name",
        })
    if total_targets <= 0:
        status_code = "no_external_targets"
        status_text = "未检测到其他通知对象"
        can_recall_edit = True
    elif unknown_count > 0:
        status_code = "unknown"
        if read_count > 0 and unread_count > 0:
            status_text = "部分读取状态获取失败"
        elif read_count > 0:
            status_text = "已读状态部分获取失败"
        elif unread_count > 0:
            status_text = "未读状态部分获取失败"
        else:
            status_text = "读取状态获取失败"
        can_recall_edit = read_count == 0
    elif read_count == 0:
        status_code = "all_unread"
        status_text = f"全部未读（{unread_count}人）"
        can_recall_edit = True
    elif unread_count == 0:
        status_code = "all_read"
        status_text = f"已全部阅读（{read_count}人）"
        can_recall_edit = False
    else:
        status_code = "partial_read"
        status_text = f"部分已读（已读{read_count}人，未读{unread_count}人）"
        can_recall_edit = False
    return {
        "status_code": status_code,
        "status_text": status_text,
        "can_recall_edit": bool(can_recall_edit),
        "total_targets": total_targets,
        "read_count": read_count,
        "unread_count": unread_count,
        "unknown_count": unknown_count,
        "owner_open_id": owner_open_id,
        "notify_open_ids": notify_open_ids,
        "notify_targets": [
            {
                "open_id": str(item.get("open_id") or "").strip(),
                "name": str(item.get("name") or "").strip(),
            }
            for item in items
        ],
        "items": items,
    }


def _xiaotu_set_report_edit_ready_session(wendangid, notify_open_ids, notify_targets):
    wid = str(wendangid or "").strip()
    if not wid:
        return
    session[_XIAOTU_REPORT_EDIT_READY_SESSION_KEY] = {
        "wendangid": wid,
        "ts": int(datetime.now().timestamp()),
        "notify_open_ids": [str(x or "").strip() for x in (notify_open_ids or []) if str(x or "").strip()],
        "notify_targets": [
            {
                "open_id": str((one or {}).get("open_id") or "").strip(),
                "name": str((one or {}).get("name") or "").strip(),
            }
            for one in (notify_targets or [])
            if isinstance(one, dict) and str((one or {}).get("open_id") or "").strip()
        ],
    }
    session.modified = True


def _xiaotu_clear_report_edit_ready_session(wendangid=""):
    wid = str(wendangid or "").strip()
    current = session.get(_XIAOTU_REPORT_EDIT_READY_SESSION_KEY)
    if wid and isinstance(current, dict) and str(current.get("wendangid") or "").strip() != wid:
        return
    if _XIAOTU_REPORT_EDIT_READY_SESSION_KEY in session:
        session.pop(_XIAOTU_REPORT_EDIT_READY_SESSION_KEY, None)
        session.modified = True


def _xiaotu_get_report_edit_ready_session(wendangid=""):
    wid = str(wendangid or "").strip()
    raw = session.get(_XIAOTU_REPORT_EDIT_READY_SESSION_KEY)
    if not isinstance(raw, dict):
        return {}
    stored_wid = str(raw.get("wendangid") or "").strip()
    ts = int(raw.get("ts") or 0)
    now_ts = int(datetime.now().timestamp())
    if (not stored_wid) or (ts <= 0) or (now_ts - ts > _XIAOTU_REPORT_EDIT_READY_TTL_SECONDS):
        _xiaotu_clear_report_edit_ready_session()
        return {}
    if wid and stored_wid != wid:
        return {}
    return raw


def _xiaotu_patch_related_report_cards(wendangid, open_ids, card_obj, skip_message_ids=None):
    wid = str(wendangid or "").strip()
    if not wid or not isinstance(card_obj, dict) or not card_obj:
        return []
    skip_ids = {str(x or "").strip() for x in (skip_message_ids or []) if str(x or "").strip()}
    patched = []
    seen = set()
    for open_id in (open_ids or []):
        oid = str(open_id or "").strip()
        if not oid or oid in seen:
            continue
        seen.add(oid)
        message_ids = _xiaotu_get_report_card_message_ids(wid, oid)
        for message_id in message_ids:
            if not message_id or message_id in skip_ids:
                continue
            ok, err = _feishu_update_message_card(message_id, card_obj)
            patched.append({
                "open_id": oid,
                "message_id": message_id,
                "ok": bool(ok),
                "error": str(err or "").strip()
            })
    return patched


def _xiaotu_remember_report_owner_open_id(wendangid, open_id):
    wid = str(wendangid or "").strip()
    oid = str(open_id or "").strip()
    if not wid or not oid.startswith("ou_"):
        return
    _xiaotu_report_owner_open_id_map[wid] = oid


def _xiaotu_get_report_owner_open_id(wendangid):
    wid = str(wendangid or "").strip()
    if not wid:
        return ""
    return str(_xiaotu_report_owner_open_id_map.get(wid) or "").strip()


def _feishu_send_message_detail(receive_id, receive_id_type, msg_type, content_obj):
    rid = str(receive_id or "").strip()
    rtype = str(receive_id_type or "").strip()
    mtype = str(msg_type or "").strip()
    if not rid or not rtype or not mtype:
        return False, {}
    try:
        token = permission_manager.get_access_token()
        if not token:
            return False, {}
        import requests
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={rtype}"
        payload = {
            "receive_id": rid,
            "msg_type": mtype,
            "content": json.dumps(content_obj or {}, ensure_ascii=False)
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=10).json()
        return resp.get("code") == 0, resp if isinstance(resp, dict) else {}
    except Exception:
        return False, {}


def _feishu_send_message(receive_id, receive_id_type, msg_type, content_obj):
    ok, _ = _feishu_send_message_detail(receive_id, receive_id_type, msg_type, content_obj)
    return ok


def _feishu_update_message_card(message_id, card_obj):
    mid = str(message_id or "").strip()
    if not mid or not isinstance(card_obj, dict) or not card_obj:
        return False, "缺少消息ID或卡片内容"
    try:
        token = permission_manager.get_access_token()
        if not token:
            return False, "获取飞书访问令牌失败"
        import requests
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        payload = {
            "msg_type": "interactive",
            "content": json.dumps(card_obj, ensure_ascii=False)
        }
        resp = {}
        ok = False
        err_msg = ""
        if mid.startswith("om_"):
            candidate_urls = [
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}?message_id_type=message_id",
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}"
            ]
        else:
            candidate_urls = [
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}?message_id_type=open_message_id",
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}?message_id_type=message_id",
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}"
            ]
        for url in candidate_urls:
            try:
                one_resp = requests.patch(url, headers=headers, json=payload, timeout=10).json()
            except Exception as inner_e:
                one_resp = {"code": -1, "msg": str(inner_e)}
            resp = one_resp
            ok = resp.get("code") == 0
            if ok:
                break
            err_msg = str(resp.get("msg") or resp.get("message") or resp)
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "report_card_patch_result",
                "message_id": mid,
                "ok": ok,
                "resp": resp,
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
        return ok, "" if ok else err_msg
    except Exception as e:
        return False, str(e)


def _feishu_send_text(receive_id, receive_id_type, message_text):
    return _feishu_send_message(receive_id, receive_id_type, "text", {"text": message_text})


def _xiaotu_has_report_submitted_today(user_name, now_dt=None):
    name = str(user_name or "").strip()
    if not name:
        return False
    now = now_dt if isinstance(now_dt, datetime) else datetime.now()
    start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(days=1)
    name_esc = _xiaotu_sql_escape(name)
    start_text = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_text = end_dt.strftime('%Y-%m-%d %H:%M:%S')
    sql = f"""
        SELECT TOP 1 WenDangID
        FROM baogao
        WHERE XingMing = N'{name_esc}'
          AND RiQi >= '{start_text}'
          AND RiQi < '{end_text}'
        ORDER BY RiQi DESC
    """
    rows = sf_db(sql) or []
    return bool(rows)


def _xiaotu_list_due_report_reminders(target_hhmm):
    notify_time = _xiaotu_normalize_notify_time(target_hhmm)
    if not notify_time:
        return []
    esc_time = _xiaotu_sql_escape(notify_time)
    sql = f"""
        IF OBJECT_ID(N'{_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}', N'U') IS NOT NULL
            SELECT YongHu, TiJiaoRen, TongZhiShiJian
            FROM {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}
            WHERE LEFT(ISNULL(TongZhiShiJian, N''), 5) <> N''
              AND LEFT(ISNULL(TongZhiShiJian, N''), 5) <= N'{esc_time}'
        ELSE
            SELECT CAST(N'' AS NVARCHAR(100)) AS YongHu, CAST(N'' AS NVARCHAR(100)) AS TiJiaoRen, CAST(N'' AS NVARCHAR(20)) AS TongZhiShiJian
            WHERE 1 = 0
    """
    rows = sf_db(sql) or []
    out = []
    for row in rows:
        if isinstance(row, dict):
            user_name = str(row.get("YongHu") or row.get("yonghu") or "").strip()
            notify_raw = row.get("TongZhiShiJian") or row.get("tongzhishijian") or ""
        elif isinstance(row, (list, tuple)):
            user_name = str(row[0] if len(row) > 0 else "").strip()
            notify_raw = row[2] if len(row) > 2 else ""
        else:
            continue
        if not user_name:
            continue
        out.append({
            "user_name": user_name,
            "notify_time": _xiaotu_normalize_notify_time(notify_raw)
        })
    return out


def _xiaotu_build_report_reminder_text(user_name, notify_time):
    name = str(user_name or "").strip() or "同事"
    time_text = _xiaotu_normalize_notify_time(notify_time)
    now_text = datetime.now().strftime('%Y-%m-%d')
    report_center_url = _xiaotu_build_report_center_url()
    lines = [
        f"{name}，你今天的报告还没有提交。",
        f"提醒时间：{time_text or '未设置'}",
        f"日期：{now_text}",
        "请尽快进入报告智能体提交今日报告。"
    ]
    if report_center_url:
        lines.append(f"填写入口：{report_center_url}")
    return "\n".join(lines)


def _xiaotu_append_report_reminder_log(stage, **kwargs):
    item = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "stage": str(stage or "").strip() or "unknown",
    }
    for key, value in (kwargs or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            item[key] = value
        else:
            try:
                item[key] = json.loads(json.dumps(value, ensure_ascii=False))
            except Exception:
                item[key] = str(value)
    with _xiaotu_report_reminder_lock:
        _xiaotu_report_reminder_logs.append(item)
        if len(_xiaotu_report_reminder_logs) > _xiaotu_report_reminder_logs_limit:
            del _xiaotu_report_reminder_logs[:len(_xiaotu_report_reminder_logs) - _xiaotu_report_reminder_logs_limit]
    try:
        _safe_debug_print(f"[xiaotu_report_reminder][{item['stage']}] {item}")
    except Exception:
        pass


def _xiaotu_build_report_center_url():
    fallback_url = str(_XIAOTU_REPORT_CENTER_PUBLIC_URL or "").strip()
    fallback_path = "/dashboard/xiaotu-report-center"
    try:
        req_base = str(request.host_url or "").strip().rstrip("/")
        if req_base and not any(x in req_base.lower() for x in ["127.0.0.1", "localhost", "0.0.0.0"]):
            return req_base + fallback_path
    except Exception:
        pass
    try:
        built_url = str(url_for('dashboard_xiaotu_report_center', _external=True) or "").strip()
        parsed = urlparse(built_url)
        host = str(parsed.hostname or "").strip().lower()
        if built_url and host and host not in {"127.0.0.1", "localhost", "0.0.0.0"}:
            return built_url
    except Exception:
        pass
    return fallback_url or ""


def _xiaotu_build_missing_report_reminder_card(user_name, notify_time):
    name = str(user_name or "").strip() or "同事"
    time_text = _xiaotu_normalize_notify_time(notify_time)
    now_text = datetime.now().strftime('%Y-%m-%d')
    report_center_url = _xiaotu_build_report_center_url()
    elements = [
        {
            "tag": "markdown",
            "content": f"**{name}，你今天的报告还没有提交。**"
        },
        {
            "tag": "markdown",
            "content": f"**提醒时间：** {time_text or '未设置'}\n**日期：** {now_text}"
        },
        {
            "tag": "markdown",
            "content": "请点击此提醒，直接进入报告智能体填写今日报告。"
        }
    ]
    if report_center_url:
        elements.append({
            "tag": "markdown",
            "content": f"[打开报告中心]({report_center_url})"
        })
    if report_center_url:
        elements.extend([
            {"tag": "hr"},
            {
                "tag": "column_set",
                "columns": [
                    {
                        "tag": "column",
                        "width": "auto",
                        "elements": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "立即填写报告"
                                },
                                "type": "primary",
                                "size": "small",
                                "behaviors": [
                                    {
                                        "type": "open_url",
                                        "default_url": report_center_url
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "horizontal_spacing": "8px"
            }
        ])
    card = {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "wide_screen_mode": True
        },
        "header": {
            "template": "orange",
            "title": {
                "tag": "plain_text",
                "content": "报告未提交提醒"
            }
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 12px 12px",
            "elements": elements
        }
    }
    return card


def _xiaotu_send_missing_report_reminder(receive_id, receive_id_type, user_name, notify_time):
    card = _xiaotu_build_missing_report_reminder_card(user_name, notify_time)
    ok, _ = _feishu_send_message_detail(receive_id, receive_id_type, "interactive", card)
    if ok:
        return True
    return _feishu_send_text(receive_id, receive_id_type, _xiaotu_build_report_reminder_text(user_name, notify_time))


def _xiaotu_run_report_reminder_once(now_dt=None):
    now = now_dt if isinstance(now_dt, datetime) else datetime.now()
    target_hhmm = now.strftime('%H:%M')
    due_rows = _xiaotu_list_due_report_reminders(target_hhmm)
    _xiaotu_append_report_reminder_log(
        "tick",
        target_hhmm=target_hhmm,
        due_count=len(due_rows or []),
        thread_started=bool(_xiaotu_report_reminder_thread_started)
    )
    if not due_rows:
        return 0
    sent_count = 0
    day_key = now.strftime('%Y-%m-%d')
    with _xiaotu_report_reminder_lock:
        stale_keys = [k for k in _xiaotu_report_reminder_sent_marks.keys() if not str(k).startswith(day_key + "|")]
        for key in stale_keys:
            _xiaotu_report_reminder_sent_marks.pop(key, None)
    for item in due_rows:
        user_name = str(item.get("user_name") or "").strip()
        notify_time = _xiaotu_normalize_notify_time(item.get("notify_time") or target_hhmm)
        if not user_name or not notify_time:
            _xiaotu_append_report_reminder_log("skip_invalid_row", raw=item)
            continue
        dedupe_key = f"{day_key}|{user_name}|{notify_time}"
        with _xiaotu_report_reminder_lock:
            if _xiaotu_report_reminder_sent_marks.get(dedupe_key):
                _xiaotu_append_report_reminder_log(
                    "skip_already_sent",
                    user_name=user_name,
                    notify_time=notify_time,
                    dedupe_key=dedupe_key
                )
                continue
        has_submitted_today = _xiaotu_has_report_submitted_today(user_name, now_dt=now)
        if has_submitted_today:
            _xiaotu_append_report_reminder_log(
                "skip_submitted",
                user_name=user_name,
                notify_time=notify_time
            )
            continue
        cached_open_id = str(_xiaotu_get_cached_open_id_by_name(user_name) or "").strip()
        looked_up_open_id = ""
        open_id_source = ""
        open_id = cached_open_id
        if open_id:
            open_id_source = "runtime_cache"
        else:
            looked_up_open_id = str(_xiaotu_lookup_open_id_by_name(user_name) or "").strip()
            open_id = looked_up_open_id
            if open_id:
                open_id_source = "database_lookup"
        if not open_id:
            _xiaotu_append_report_reminder_log(
                "skip_no_open_id",
                user_name=user_name,
                notify_time=notify_time,
                cached_open_id=cached_open_id,
                looked_up_open_id=looked_up_open_id
            )
            try:
                _safe_debug_print(f"[xiaotu_report_reminder] skip no open_id for {user_name}")
            except Exception:
                pass
            continue
        ok = _xiaotu_send_missing_report_reminder(open_id, "open_id", user_name, notify_time)
        if ok:
            with _xiaotu_report_reminder_lock:
                _xiaotu_report_reminder_sent_marks[dedupe_key] = now.strftime('%Y-%m-%d %H:%M:%S')
            sent_count += 1
            _xiaotu_append_report_reminder_log(
                "send_success",
                user_name=user_name,
                notify_time=notify_time,
                open_id=open_id,
                open_id_source=open_id_source,
                dedupe_key=dedupe_key
            )
        else:
            _xiaotu_append_report_reminder_log(
                "send_failed",
                user_name=user_name,
                notify_time=notify_time,
                open_id=open_id,
                open_id_source=open_id_source,
                dedupe_key=dedupe_key
            )
            try:
                _safe_debug_print(f"[xiaotu_report_reminder] send failed for {user_name} -> {open_id}")
            except Exception:
                pass
    return sent_count


def _xiaotu_report_reminder_loop():
    while True:
        try:
            with app.app_context():
                _xiaotu_run_report_reminder_once()
        except Exception as e:
            _xiaotu_append_report_reminder_log("loop_exception", error=str(e))
            try:
                _safe_debug_print(f"[xiaotu_report_reminder] {e}")
            except Exception:
                pass
        time.sleep(20)


def _start_xiaotu_report_reminder_thread_once():
    global _xiaotu_report_reminder_thread_started
    if not _XIAOTU_REPORT_REMINDER_ENABLED:
        _safe_debug_print("[xiaotu_report_reminder] disabled for debugging")
        return
    with _xiaotu_report_reminder_lock:
        if _xiaotu_report_reminder_thread_started:
            return
        thread = Thread(target=_xiaotu_report_reminder_loop, name="xiaotu_report_reminder", daemon=True)
        thread.start()
        _xiaotu_report_reminder_thread_started = True
    _xiaotu_append_report_reminder_log("thread_started", thread_name="xiaotu_report_reminder", pid=os.getpid())


def _xiaotu_clip_card_text(text, limit=900):
    raw = str(text or "").replace("\r\n", "\n").strip()
    if not raw:
        return ""
    if len(raw) <= limit:
        return raw
    return raw[: max(0, int(limit) - 1)].rstrip() + "…"


def _xiaotu_html_to_plain_text_preserve_blocks(raw_text):
    text = str(raw_text or "")
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)
    text = re.sub(r"<span\b[^>]*data-lark-record-data=[\s\S]*?</span\s*>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]*class=['\"][^'\"]*lark-record-clipboard[^'\"]*['\"][^>]*>[\s\S]*?</[^>]+>", " ", text, flags=re.I)
    text = re.sub(r"<(script|style|svg)[^>]*>[\s\S]*?</\1\s*>", " ", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<img\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(
        r"<li\b([^>]*)data-index=['\"]([^'\"]+)['\"]([^>]*)>",
        lambda m: "\n" + str(m.group(2) or "").strip() + " ",
        text,
        flags=re.I
    )
    text = re.sub(r"<li\b[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"</li\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</?(?:ol|ul)\b[^>]*>", "\n", text, flags=re.I)
    for lvl in range(6, 0, -1):
        text = re.sub(rf"<h{lvl}\b[^>]*>", "\n" + ("#" * lvl) + " ", text, flags=re.I)
        text = re.sub(rf"</h{lvl}\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<(?:strong|b)\b[^>]*>", "**", text, flags=re.I)
    text = re.sub(r"</(?:strong|b)\s*>", "**", text, flags=re.I)
    text = re.sub(r"<(?:em|i)\b[^>]*>", "*", text, flags=re.I)
    text = re.sub(r"</(?:em|i)\s*>", "*", text, flags=re.I)
    text = re.sub(r"</?(?:div|p|section|article|header|footer|blockquote|pre)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"</?(?:table|thead|tbody|tr)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"</?(?:td|th)\b[^>]*>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\*{3,}", "**", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    cleaned_lines = []
    for line in text.splitlines():
        one = str(line or "").strip()
        one = re.sub(r"^(?:[A-Za-z0-9_-]{12,}\s+)+", "", one).strip()
        if not one:
            continue
        if re.fullmatch(r"[A-Za-z0-9_-]{12,}", one):
            continue
        cleaned_lines.append(one)
    return "\n".join(cleaned_lines).strip()


def _xiaotu_extract_plain_preview_text(raw_text, limit=500):
    text = _xiaotu_html_to_plain_text_preserve_blocks(raw_text)
    return _xiaotu_clip_card_text(text, limit=limit)


def _xiaotu_parse_image_path_list(raw_paths):
    return [relocate_storage_path(x) for x in str(raw_paths or "").split("|") if str(x or "").strip()]


def _xiaotu_image_file_name(raw_path):
    txt = str(raw_path or "").strip().replace("\\", "/")
    if not txt:
        return ""
    return str(txt.split("/")[-1] or "").strip()


def _xiaotu_normalize_compare_path(raw_path):
    txt = str(raw_path or "").strip().replace("\\", "/")
    txt = re.sub(r"^https?://[^/]+", "", txt, flags=re.I)
    return txt


def _xiaotu_clean_card_text_block(raw_text):
    text = html_unescape(str(raw_text or "")).replace("\xa0", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    cleaned_lines = []
    last_blank = True
    for line in text.splitlines():
        one = str(line or "").rstrip()
        one = re.sub(r"^(?:[A-Za-z0-9_-]{12,}\s+)+", "", one).rstrip()
        if one and re.fullmatch(r"[A-Za-z0-9_-]{12,}", one):
            continue
        if not one.strip():
            if not last_blank:
                cleaned_lines.append("")
            last_blank = True
            continue
        cleaned_lines.append(one.strip())
        last_blank = False
    return "\n".join(cleaned_lines).strip()


class _XiaoTuCardSourceParser(HTMLParser):
    def __init__(self, image_paths):
        super().__init__(convert_charrefs=True)
        self.image_paths = list(image_paths or [])
        self.used_paths = set()
        self.image_cursor = 0
        self.skip_depth = 0
        self.segments = []
        self.text_parts = []

    def _append_text(self, text):
        if text:
            self.text_parts.append(str(text))

    def _flush_text(self):
        text = _xiaotu_clean_card_text_block("".join(self.text_parts))
        self.text_parts = []
        if text:
            self.segments.append({"type": "text", "content": text})

    def _next_fallback_image(self):
        while self.image_cursor < len(self.image_paths):
            path = str(self.image_paths[self.image_cursor] or "").strip()
            self.image_cursor += 1
            if not path or path in self.used_paths:
                continue
            self.used_paths.add(path)
            return path
        return ""

    def _resolve_image_path(self, attrs):
        attrs = attrs or {}
        candidates = [
            attrs.get("src"),
            attrs.get("data-src"),
            attrs.get("data-local-image"),
            attrs.get("data-origin-src"),
        ]
        for raw in candidates:
            txt = str(raw or "").strip().strip("`").strip("\"'")
            if not txt:
                continue
            norm = _xiaotu_normalize_compare_path(txt)
            base = _xiaotu_image_file_name(txt)
            for path in self.image_paths:
                if not path or path in self.used_paths:
                    continue
                if _xiaotu_normalize_compare_path(path) == norm or (base and _xiaotu_image_file_name(path) == base):
                    self.used_paths.add(path)
                    return path
        return self._next_fallback_image()

    def handle_starttag(self, tag, attrs):
        tag = str(tag or "").lower()
        attrs_map = {str(k or "").lower(): v for k, v in (attrs or [])}
        if tag in {"script", "style", "svg"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "br":
            self._append_text("\n")
            return
        if tag == "img":
            image_path = self._resolve_image_path(attrs_map)
            self._flush_text()
            if image_path:
                self.segments.append({"type": "image", "path": image_path})
            return
        if tag in {"div", "p", "section", "article", "header", "footer", "blockquote", "pre", "table", "thead", "tbody", "tr"}:
            self._append_text("\n")
            return
        if tag in {"td", "th"}:
            self._append_text(" ")
            return
        if tag in {"strong", "b"}:
            self._append_text("**")
            return
        if tag in {"em", "i"}:
            self._append_text("*")
            return
        if tag == "li":
            marker = str(attrs_map.get("data-index") or "").strip() or "-"
            self._append_text("\n" + marker + " ")
            return
        if re.fullmatch(r"h[1-6]", tag):
            level = int(tag[-1])
            self._append_text("\n" + ("#" * max(1, level)) + " ")

    def handle_endtag(self, tag):
        tag = str(tag or "").lower()
        if tag in {"script", "style", "svg"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in {"div", "p", "section", "article", "header", "footer", "blockquote", "pre", "table", "thead", "tbody", "tr", "li", "ol", "ul"}:
            self._append_text("\n")
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._append_text("\n")
            return
        if tag in {"strong", "b"}:
            self._append_text("**")
            return
        if tag in {"em", "i"}:
            self._append_text("*")

    def handle_data(self, data):
        if self.skip_depth:
            return
        self._append_text(data)

    def close(self):
        super().close()
        self._flush_text()


def _xiaotu_build_card_source_elements(source_text, image_paths_text="", fallback_image_key="", max_blocks=16, full_content_url=""):
    raw_text = str(source_text or "").strip()
    image_paths = _xiaotu_parse_image_path_list(image_paths_text)
    elements = [{
        "tag": "markdown",
        "content": "**原文内容**"
    }]
    if not raw_text and fallback_image_key:
        elements.append({
            "tag": "img",
            "img_key": str(fallback_image_key).strip(),
            "alt": {"tag": "plain_text", "content": "报告图片"}
        })
        return elements
    segments = []
    if re.search(r"<[^>]+>", raw_text):
        parser = _XiaoTuCardSourceParser(image_paths)
        try:
            parser.feed(raw_text)
            parser.close()
            segments = list(parser.segments or [])
        except Exception:
            segments = []
    if not segments:
        plain = _xiaotu_clean_card_text_block(raw_text)
        if plain:
            segments.append({"type": "text", "content": plain})
        for path in image_paths:
            segments.append({"type": "image", "path": path})
    upload_cache = {}
    used_blocks = 0
    long_content = False
    preview_limit = 1000
    max_blocks_safe = max(1, int(max_blocks))
    for seg in segments:
        if used_blocks >= max_blocks_safe:
            long_content = True
            break
        if str(seg.get("type") or "") == "text":
            full_content = _xiaotu_clean_card_text_block(seg.get("content") or "")
            if len(full_content) > preview_limit:
                long_content = True
            content = _xiaotu_clip_card_text(full_content, limit=preview_limit)
            if not content:
                continue
            elements.append({
                "tag": "markdown",
                "content": content
            })
            used_blocks += 1
            continue
        if str(seg.get("type") or "") == "image":
            img_path = str(seg.get("path") or "").strip()
            if not img_path:
                continue
            if img_path not in upload_cache:
                upload_cache[img_path] = _feishu_upload_image_by_path(img_path)
            img_key = str(upload_cache.get(img_path) or "").strip()
            if not img_key:
                continue
            elements.append({
                "tag": "img",
                "img_key": img_key,
                "alt": {"tag": "plain_text", "content": "报告图片"}
            })
            used_blocks += 1
    if len(elements) == 1:
        fallback_text = _xiaotu_extract_plain_preview_text(raw_text, limit=520) or "（无原文内容）"
        if raw_text and len(_xiaotu_clean_card_text_block(raw_text)) > 520:
            long_content = True
        elements.append({
            "tag": "markdown",
            "content": fallback_text
        })
        if fallback_image_key:
            elements.append({
                "tag": "img",
                "img_key": str(fallback_image_key).strip(),
                "alt": {"tag": "plain_text", "content": "报告图片"}
            })
    if long_content:
        full_url = str(full_content_url or "").strip()
        notice_text = "内容较长，卡片已折叠展示，请点击下方「查看日报」查看完整内容。"
        if full_url:
            notice_text = f"内容较长，卡片已折叠展示。[查看完整日报]({full_url})"
        elements.append({
            "tag": "markdown",
            "content": notice_text
        })
    return elements


def _feishu_upload_image_by_path(image_path):
    path = relocate_storage_path(image_path)
    if not path or (not os.path.exists(path)):
        return ""
    try:
        token = permission_manager.get_access_token()
        if not token:
            return ""
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as f:
            files = {"image": (os.path.basename(path), f, mime)}
            data = {"image_type": "message"}
            resp = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/images",
                headers={"Authorization": f"Bearer {token}"},
                files=files,
                data=data,
                timeout=20
            ).json()
        return str((resp or {}).get("data", {}).get("image_key") or "").strip()
    except Exception:
        return ""


def _xiaotu_feedback_entry_line(entry_type, actor_name, content_text, target_name=""):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    entry = {
        "type": str(entry_type or "").strip() or "comment",
        "ts": ts,
        "actor": str(actor_name or "匿名用户").strip() or "匿名用户",
        "content": str(content_text or "").strip(),
    }
    target = str(target_name or "").strip()
    if target:
        entry["target"] = target
    return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))


def _xiaotu_parse_feedback_entries(raw_text, entry_type="comment"):
    out = []
    text = str(raw_text or "").strip()
    if not text:
        return out
    for line in text.splitlines():
        line = str(line or "").strip()
        if not line:
            continue
        item = None
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    item = {
                        "type": str(obj.get("type") or entry_type or "comment").strip() or "comment",
                        "ts": str(obj.get("ts") or "").strip(),
                        "actor": str(obj.get("actor") or "").strip(),
                        "target": str(obj.get("target") or "").strip(),
                        "content": str(obj.get("content") or "").strip(),
                    }
            except Exception:
                item = None
        if not item:
            if str(entry_type or "").strip() == "reply":
                m = re.match(
                    r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+(?P<actor>.+?)\s+回复(?P<target>[^：:]*)[：:](?P<content>.+)$",
                    line
                )
                if m:
                    item = {
                        "type": "reply",
                        "ts": str(m.group("ts") or "").strip(),
                        "actor": str(m.group("actor") or "").strip(),
                        "target": str(m.group("target") or "").strip(),
                        "content": str(m.group("content") or "").strip(),
                    }
            else:
                m = re.match(
                    r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+(?P<actor>[^：:]+)[：:](?P<content>.+)$",
                    line
                )
                if m:
                    item = {
                        "type": "comment",
                        "ts": str(m.group("ts") or "").strip(),
                        "actor": str(m.group("actor") or "").strip(),
                        "target": "",
                        "content": str(m.group("content") or "").strip(),
                    }
        if not item:
            item = {
                "type": str(entry_type or "").strip() or "comment",
                "ts": "",
                "actor": "",
                "target": "",
                "content": line,
            }
        out.append(item)
    return out


def _xiaotu_enrich_feedback_data(feedback, owner_name=""):
    fb = dict(feedback or {})
    comments = _xiaotu_parse_feedback_entries(fb.get("pinglun") or "", "comment")
    replies = _xiaotu_parse_feedback_entries(fb.get("huifu") or "", "reply")
    legacy_actor = str(fb.get("yonghu") or "").strip()
    for item in comments:
        if not str((item or {}).get("actor") or "").strip() and legacy_actor:
            item["actor"] = legacy_actor
    for item in replies:
        if not str((item or {}).get("actor") or "").strip() and legacy_actor:
            item["actor"] = legacy_actor
    liked = str(fb.get("dianzan") or "").strip().upper() == "Y"
    if (not liked) and legacy_actor and not comments and not replies:
        # 兼容旧数据：历史上只有一个点赞人时，可能只在 YongHu 留了名字。
        liked = True
    like_users = _xiaotu_parse_like_user_names(legacy_actor) if liked else []
    targets = []
    seen = set()
    for name in [owner_name] + [x.get("actor") for x in comments] + [x.get("actor") for x in replies] + [x.get("target") for x in replies]:
        name = str(name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        targets.append(name)
    fb["like_users"] = like_users
    fb["like_count"] = len(like_users)
    fb["comment_items"] = comments
    fb["reply_items"] = replies
    fb["reply_targets"] = targets
    return fb


def _xiaotu_card_feedback_text(feedback, expanded=False, preview_count=3):
    fb = _xiaotu_enrich_feedback_data(feedback or {})
    comments = list(fb.get("comment_items") or [])
    replies = list(fb.get("reply_items") or [])
    preview = max(1, int(preview_count or 3))
    shown_comments = comments if expanded else comments[-preview:]
    shown_replies = replies if expanded else replies[-preview:]
    lines = []
    if shown_comments:
        lines.append("**评论记录**")
        for item in shown_comments:
            ts = str(item.get("ts") or "").strip()
            actor = str(item.get("actor") or "匿名用户").strip() or "匿名用户"
            content = _xiaotu_clip_card_text(item.get("content") or "", limit=120)
            prefix = f"`{ts}` " if ts else ""
            lines.append(f"- {prefix}{actor}：{content}")
    if shown_replies:
        if lines:
            lines.append("")
        lines.append("**回复记录**")
        for item in shown_replies:
            ts = str(item.get("ts") or "").strip()
            actor = str(item.get("actor") or "匿名用户").strip() or "匿名用户"
            target = str(item.get("target") or "").strip()
            content = _xiaotu_clip_card_text(item.get("content") or "", limit=120)
            prefix = f"`{ts}` " if ts else ""
            reply_to = f" 回复 {target}" if target else " 回复"
            lines.append(f"- {prefix}{actor}{reply_to}：{content}")
    return "\n".join([x for x in lines if str(x).strip()]).strip()


def _xiaotu_build_reply_target_options(feedback, owner_name=""):
    fb = _xiaotu_enrich_feedback_data(feedback or {}, owner_name=owner_name)
    out = []
    for name in fb.get("reply_targets") or []:
        name = str(name or "").strip()
        if not name:
            continue
        out.append({
            "text": {
                "tag": "plain_text",
                "content": name
            },
            "value": name
        })
    return out


def _xiaotu_build_feedback_notice_markdown(action_name, actor_name, comment_text="", target_name=""):
    actor = str(actor_name or "").strip() or "匿名用户"
    content = _xiaotu_clip_card_text(comment_text or "", limit=220) or "（空）"
    target = str(target_name or "").strip()
    if str(action_name or "").strip() == "like_report":
        return "\n".join([
            "**你的报告收到新的点赞**",
            f"操作人：{actor}"
        ]).strip()
    if str(action_name or "").strip() == "reply_report":
        lines = [
            "**你的报告收到新的回复**",
            f"回复人：{actor}",
        ]
        if target:
            lines.append(f"回复对象：{target}")
        lines.append(f"回复内容：{content}")
        return "\n".join(lines).strip()
    return "\n".join([
        "**你的报告收到新的评论**",
        f"评论人：{actor}",
        f"评论内容：{content}"
    ]).strip()


def _xiaotu_get_report_card_context(wendangid):
    wid = str(wendangid or "").strip()
    if not wid:
        return {}
    esc_wid = _xiaotu_sql_escape(wid)
    sql = f"""
        SELECT TOP 1 WenDangID, BiaoTi, ZhengWen, TuPianLujin, PingJia, RenYuanLeiXing, XingMing
        FROM baogao
        WHERE WenDangID='{esc_wid}'
    """
    row = sf_db(sql) or []
    if isinstance(row, list) and row:
        row = row[0]
    if isinstance(row, dict):
        return {
            "wendangid": str(row.get("WenDangID") or wid).strip(),
            "title_text": str(row.get("BiaoTi") or "").strip(),
            "source_text": str(row.get("ZhengWen") or "").strip(),
            "pingjia_text": str(row.get("PingJia") or "").strip(),
            "person_type": str(row.get("RenYuanLeiXing") or "").strip(),
            "owner_name": str(row.get("XingMing") or "").strip(),
            "image_paths_text": str(row.get("TuPianLujin") or "").strip(),
            "image_path": str(row.get("TuPianLujin") or "").split("|")[0].strip()
        }
    if isinstance(row, (list, tuple)):
        values = list(row)
        return {
            "wendangid": str(values[0] if len(values) > 0 else wid).strip(),
            "title_text": str(values[1] if len(values) > 1 else "").strip(),
            "source_text": str(values[2] if len(values) > 2 else "").strip(),
            "image_paths_text": str(values[3] if len(values) > 3 else "").strip(),
            "image_path": str(values[3] if len(values) > 3 else "").split("|")[0].strip(),
            "pingjia_text": str(values[4] if len(values) > 4 else "").strip(),
            "person_type": str(values[5] if len(values) > 5 else "").strip(),
            "owner_name": str(values[6] if len(values) > 6 else "").strip(),
        }
    return {}


def _xiaotu_build_report_history_url(wendangid=""):
    wid = str(wendangid or "").strip()
    if not wid:
        return ""
    try:
        return url_for('dashboard_xiaotu_report_history', wendangid=wid, _external=True)
    except Exception:
        base_url = str(_XIAOTU_REPORT_CENTER_PUBLIC_URL or "").strip()
        if not base_url:
            return ""
        parsed = urlparse(base_url)
        if parsed.scheme and parsed.netloc:
            base_url = f"{parsed.scheme}://{parsed.netloc}/dashboard/xiaotu-report-history"
        else:
            base_url = base_url.split("?", 1)[0].rstrip("/")
            base_url = re.sub(r"/dashboard/xiaotu-report-center/?$", "/dashboard/xiaotu-report-history", base_url)
            if not base_url.endswith("/dashboard/xiaotu-report-history"):
                base_url = base_url.rstrip("/") + "/dashboard/xiaotu-report-history"
        return f"{base_url}?wendangid={quote(wid)}"


def _xiaotu_split_org_perf_from_pingjia(pingjia_text):
    text = str(pingjia_text or "").strip()
    if not text:
        return "", ""
    marker_match = re.search(r"(?:^|\n)\s*(?:组织绩效贡献|对组织绩效影响)\s*[:：]", text)
    if not marker_match:
        return text, ""
    start = marker_match.start()
    marker_start = marker_match.start()
    if text[marker_start:marker_start + 1] == "\n":
        marker_start += 1
    summary = text[:start].strip()
    org_impact = text[marker_start:].strip()
    org_impact = re.sub(r"^\s*组织绩效贡献\s*[:：]\s*", "", org_impact).strip()
    org_impact = re.sub(r"^\s*对组织绩效影响\s*[:：]\s*", "", org_impact).strip()
    return summary, org_impact


def _xiaotu_build_report_notify_card(title_text, person_type, pingjia_text, doc_url="", source_text="", image_key="", image_paths_text="", wendangid="", comment_url="", report_url="", feedback_override=None, header_title="", header_template="blue", notice_markdown="", feedback_expanded=False, org_impact_text=""):
    title_val = str(title_text or "未命名标题").strip() or "未命名标题"
    person_val = str(person_type or "未设置").strip() or "未设置"
    summary_text, parsed_org_impact_text = _xiaotu_split_org_perf_from_pingjia(pingjia_text)
    summary_val = _xiaotu_clip_card_text(summary_text, limit=900) or "暂无评价结果"
    org_impact_text = str(org_impact_text or "").strip() or parsed_org_impact_text
    org_impact_text = re.sub(r"^\s*组织绩效贡献\s*[:：]\s*", "", org_impact_text).strip()
    org_impact_text = re.sub(r"^\s*对组织绩效影响\s*[:：]\s*", "", org_impact_text).strip()
    org_impact_val = _xiaotu_clip_card_text(org_impact_text, limit=500)
    ctx = _xiaotu_get_report_card_context(wendangid) if str(wendangid or "").strip() else {}
    owner_name = str((ctx or {}).get("owner_name") or "").strip()
    feedback = feedback_override if isinstance(feedback_override, dict) else _xiaotu_get_report_feedback(wendangid, owner_name=owner_name)
    feedback = _xiaotu_enrich_feedback_data(feedback, owner_name=owner_name)
    liked = str(feedback.get("dianzan") or "").strip().upper() == "Y"
    wid = str(wendangid or "").strip()
    report_url = str(report_url or _xiaotu_build_report_history_url(wid)).strip()
    suffix = re.sub(r"[^A-Za-z0-9_]", "_", wid or "manual")[-18:] or "manual"
    reply_target_options = _xiaotu_build_reply_target_options(feedback, owner_name=owner_name)
    feedback_expanded = bool(feedback_expanded)
    preview_count = 3
    total_feedback_count = len(list(feedback.get("comment_items") or [])) + len(list(feedback.get("reply_items") or []))
    like_button = {
        "tag": "button",
        "name": f"like_btn_{suffix}",
        "text": {
            "tag": "plain_text",
            "content": "已点赞" if liked else "点赞"
        },
        "type": "danger_filled" if liked else "primary",
        "size": "small",
        "behaviors": [
            {
                "type": "callback",
                "value": {
                    "action": "like_report",
                    "wendangid": wid,
                    "doc_url": str(doc_url or "").strip(),
                    "image_key": str(image_key or "").strip(),
                    "feedback_expanded": "1" if feedback_expanded else "0"
                }
            }
        ]
    }
    action_column = {
        "tag": "column",
        "width": "auto",
        "elements": [like_button]
    }
    columns = [action_column]
    if report_url:
        columns.append({
            "tag": "column",
            "width": "auto",
            "elements": [
                {
                    "tag": "button",
                    "name": f"report_btn_{suffix}",
                    "text": {
                        "tag": "plain_text",
                        "content": "查看日报"
                    },
                    "type": "default",
                    "size": "small",
                    "behaviors": [
                        {
                            "type": "open_url",
                            "default_url": report_url
                        }
                    ]
                }
            ]
        })
    if doc_url:
        columns.append({
            "tag": "column",
            "width": "auto",
            "elements": [
                {
                    "tag": "button",
                    "name": f"doc_btn_{suffix}",
                    "text": {
                        "tag": "plain_text",
                        "content": "打开云文档"
                    },
                    "type": "default",
                    "size": "small",
                    "behaviors": [
                        {
                            "type": "open_url",
                            "default_url": str(doc_url).strip()
                        }
                    ]
                }
            ]
        })
    card_elements = _xiaotu_build_card_source_elements(
        source_text=source_text,
        image_paths_text=image_paths_text,
        fallback_image_key=image_key,
        max_blocks=16,
        full_content_url=report_url
    )
    if not card_elements:
        card_elements = [{
            "tag": "markdown",
            "content": "**原文内容**\n（无原文内容）"
        }]
    notice_val = str(notice_markdown or "").strip()
    if notice_val:
        card_elements = [{
            "tag": "markdown",
            "content": notice_val
        }, {
            "tag": "hr"
        }] + card_elements
    card_elements.extend([
        {
            "tag": "markdown",
            "content": f"**文档标题：** {title_val}\n**人员类型：** {person_val}"
        },
        {
            "tag": "hr"
        },
        ({
            "tag": "column_set",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [{
                        "tag": "markdown",
                        "content": f"**评价结果**\n{summary_val}"
                    }]
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [{
                        "tag": "markdown",
                        "content": f"**对组织绩效影响**\n{org_impact_val}"
                    }]
                }
            ],
            "horizontal_spacing": "12px"
        } if org_impact_val else {
            "tag": "markdown",
            "content": f"**评价结果**\n{summary_val}"
        }),
        {
            "tag": "hr"
        },
        {
            "tag": "column_set",
            "columns": columns,
            "horizontal_spacing": "8px"
        },
        {
            "tag": "form",
            "name": f"report_feedback_form_{suffix}",
            "elements": [
                *([
                    {
                        "tag": "select_static",
                        "name": "reply_target",
                        "placeholder": {
                            "tag": "plain_text",
                            "content": "可选：选择要回复的人"
                        },
                        "options": reply_target_options
                    }
                ] if reply_target_options else []),
                {
                    "tag": "input",
                    "name": "feedback_text",
                    "input_type": "multiline_text",
                    "rows": 2,
                    "max_rows": 5,
                    "max_length": 1000,
                    "required": False,
                    "width": "fill",
                    "placeholder": {
                        "tag": "plain_text",
                        "content": "输入评论或回复内容"
                    }
                },
                {
                    "tag": "column_set",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "auto",
                            "elements": [
                                {
                                    "tag": "button",
                                    "name": f"feedback_submit_{suffix}",
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "提交互动"
                                    },
                                    "type": "primary_filled",
                                    "size": "small",
                                    "form_action_type": "submit",
                                    "behaviors": [
                                        {
                                            "type": "callback",
                                            "value": {
                                                "action": "submit_feedback_report",
                                                "wendangid": wid,
                                                "doc_url": str(doc_url or "").strip(),
                                                "image_key": str(image_key or "").strip(),
                                                "feedback_expanded": "1" if feedback_expanded else "0"
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ])
    feedback_text = _xiaotu_card_feedback_text(feedback, expanded=feedback_expanded, preview_count=preview_count)
    if feedback_text:
        card_elements.insert(-2, {
            "tag": "markdown",
            "content": feedback_text
        })
        if total_feedback_count > preview_count:
            card_elements.insert(-2, {
                "tag": "button",
                "name": f"feedback_toggle_{suffix}",
                "text": {
                    "tag": "plain_text",
                    "content": "收起记录" if feedback_expanded else "展开记录"
                },
                "type": "default",
                "size": "small",
                "behaviors": [
                    {
                        "type": "callback",
                        "value": {
                            "action": "toggle_feedback_records",
                            "wendangid": wid,
                            "doc_url": str(doc_url or "").strip(),
                            "image_key": str(image_key or "").strip(),
                            "feedback_expanded": "0" if feedback_expanded else "1"
                        }
                    }
                ]
            })
    return {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "wide_screen_mode": True
        },
        "header": {
            "template": str(header_template or "blue").strip() or "blue",
            "title": {
                "tag": "plain_text",
                "content": str(header_title or title_val).strip() or title_val
            }
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 12px 12px",
            "elements": card_elements
        }
    }


def _xiaotu_send_report_notification(receive_id, receive_id_type, title_text, person_type, pingjia_text, doc_url="", source_text="", image_key="", image_paths_text="", wendangid="", comment_url="", report_url="", org_impact_text=""):
    card = _xiaotu_build_report_notify_card(
        title_text,
        person_type,
        pingjia_text,
        doc_url=doc_url,
        source_text=source_text,
        image_key=image_key,
        image_paths_text=image_paths_text,
        wendangid=wendangid,
        comment_url=comment_url,
        report_url=report_url,
        org_impact_text=org_impact_text
    )
    ok, resp = _feishu_send_message_detail(receive_id, receive_id_type, "interactive", card)
    if ok:
        if str(receive_id_type or "").strip() == "open_id":
            message_id = str(((resp or {}).get("data") or {}).get("message_id") or "").strip()
            _xiaotu_remember_report_card_message(wendangid, receive_id, message_id)
        return True
    push_lines = [
        "小图问答已完成入库",
        f"文档标题：{title_text}",
        f"人员类型：{person_type}",
    ]
    if doc_url:
        push_lines.append(f"文档链接：{doc_url}")
    if report_url:
        push_lines.append(f"查看日报：{report_url}")
    source_preview = _xiaotu_extract_plain_preview_text(source_text, limit=600)
    if source_preview:
        push_lines.extend([
            "",
            f"原文内容：\n{source_preview}"
        ])
    push_lines.extend([
        "",
        f"评价结果：\n{str(pingjia_text or '').strip()[:2500]}"
    ])
    org_impact_preview = str(org_impact_text or "").strip()
    if org_impact_preview:
        push_lines.extend([
            "",
            f"对组织绩效影响：\n{org_impact_preview[:1000]}"
        ])
    return _feishu_send_text(receive_id, receive_id_type, "\n".join(push_lines))


def _xiaotu_find_first_key(obj, target_keys):
    keys = {str(k).strip().lower() for k in (target_keys or []) if str(k or "").strip()}
    if not keys:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k or "").strip().lower()
            if lk in keys:
                return v
            nested = _xiaotu_find_first_key(v, keys)
            if nested is not None:
                return nested
    elif isinstance(obj, list):
        for item in obj:
            nested = _xiaotu_find_first_key(item, keys)
            if nested is not None:
                return nested
    return None


def _xiaotu_get_card_action_payload(data):
    event = (data or {}).get("event") or {}
    action = event.get("action") or (data or {}).get("action") or {}
    if not isinstance(action, dict):
        action = {}
    value = action.get("value")
    if not isinstance(value, dict):
        value = _xiaotu_find_first_key(data, {"value"})
    if not isinstance(value, dict):
        value = {}
    form_value = action.get("form_value")
    if not isinstance(form_value, dict):
        form_value = _xiaotu_find_first_key(data, {"form_value", "form", "form_values"})
    if not isinstance(form_value, dict):
        form_value = {}
    operator = event.get("operator") or (data or {}).get("operator") or {}
    identity_candidates = []
    for candidate in (
        operator,
        (operator.get("operator_id") if isinstance(operator, dict) else None),
        (event.get("user") if isinstance(event, dict) else None),
        (event.get("sender") if isinstance(event, dict) else None),
        ((data or {}).get("operator") if isinstance(data, dict) else None),
        ((data or {}).get("user") if isinstance(data, dict) else None),
        ((data or {}).get("sender") if isinstance(data, dict) else None),
    ):
        if isinstance(candidate, dict):
            identity_candidates.append(candidate)
    open_id = ""
    user_id = ""
    union_id = ""
    operator_name = ""
    for one in identity_candidates:
        if not open_id:
            open_id = str(
                one.get("open_id")
                or ((one.get("operator_id") or {}).get("open_id") if isinstance(one.get("operator_id"), dict) else "")
                or ""
            ).strip()
        if not user_id:
            user_id = str(
                one.get("user_id")
                or ((one.get("operator_id") or {}).get("user_id") if isinstance(one.get("operator_id"), dict) else "")
                or ""
            ).strip()
        if not union_id:
            union_id = str(
                one.get("union_id")
                or ((one.get("operator_id") or {}).get("union_id") if isinstance(one.get("operator_id"), dict) else "")
                or ""
            ).strip()
        if not operator_name:
            operator_name = str(
                one.get("name")
                or one.get("user_name")
                or one.get("display_name")
                or one.get("nick_name")
                or ""
            ).strip()
    open_message_id = (
        (event.get("open_message_id") if isinstance(event, dict) else None)
        or (event.get("message_id") if isinstance(event, dict) else None)
        or _xiaotu_find_first_key(data, {"open_message_id", "message_id"})
        or ""
    )
    return {
        "event": event if isinstance(event, dict) else {},
        "action": action,
        "value": value,
        "form_value": form_value,
        "open_id": str(open_id or "").strip(),
        "user_id": str(user_id or "").strip(),
        "union_id": str(union_id or "").strip(),
        "operator_name": operator_name,
        "open_message_id": str(open_message_id or "").strip(),
    }


def _xiaotu_parse_like_user_names(raw_text):
    raw = str(raw_text or "").strip()
    if not raw:
        return []
    parts = re.split(r"[|\n,，;；]+", raw)
    out = []
    seen = set()
    for one in parts:
        name = str(one or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _xiaotu_build_like_user_text(names):
    out = []
    seen = set()
    for one in list(names or []):
        name = str(one or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return "|".join(out)


def _xiaotu_feedback_entries_to_text(items, entry_type="comment"):
    lines = []
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        entry = {
            "type": str(item.get("type") or entry_type or "comment").strip() or "comment",
            "ts": str(item.get("ts") or "").strip(),
            "actor": str(item.get("actor") or "").strip(),
            "content": content,
        }
        target = str(item.get("target") or "").strip()
        if target:
            entry["target"] = target
        lines.append(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines)


def _xiaotu_upsert_report_like(wendangid, user_name=""):
    wid = str(wendangid or "").strip()
    if not wid:
        return False, "缺少文档ID"
    esc_wid = _xiaotu_sql_escape(wid)
    actor = str(user_name or "").strip()
    esc_actor = _xiaotu_sql_escape(actor)
    existing_like_users = []
    try:
        existing_row = sf_db(f"SELECT TOP 1 DianZan, YongHu FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}'") or []
        if isinstance(existing_row, list) and existing_row and isinstance(existing_row[0], dict):
            existing_row = existing_row[0]
        if isinstance(existing_row, list) and existing_row and isinstance(existing_row[0], (list, tuple)):
            existing_row = existing_row[0]
        if isinstance(existing_row, dict):
            if str(existing_row.get("DianZan") or existing_row.get("dianzan") or "").strip().upper() == "Y":
                existing_like_users = _xiaotu_parse_like_user_names(existing_row.get("YongHu") or existing_row.get("yonghu") or "")
        elif isinstance(existing_row, (list, tuple)):
            if str(existing_row[0] if len(existing_row) > 0 else "").strip().upper() == "Y":
                existing_like_users = _xiaotu_parse_like_user_names(existing_row[1] if len(existing_row) > 1 else "")
    except Exception:
        existing_like_users = []
    merged_like_users = list(existing_like_users or [])
    if actor and actor not in merged_like_users:
        merged_like_users.append(actor)
    like_users_text = _xiaotu_build_like_user_text(merged_like_users)
    esc_like_users = _xiaotu_sql_escape(like_users_text)
    sql = f"""
        IF EXISTS (SELECT 1 FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}')
            UPDATE BaoGao_dianzan
            SET DianZan='Y', YongHu=N'{esc_like_users}'
            WHERE WenDangID='{esc_wid}'
        ELSE
            INSERT INTO BaoGao_dianzan (WenDangID, DianZan, PingJia, HuiFu, YongHu)
            VALUES ('{esc_wid}', 'Y', N'', N'', N'{esc_like_users}')
    """
    try:
        dui_db(sql)
        return True, ""
    except Exception as e:
        return False, str(e)


def _xiaotu_toggle_report_like(wendangid, user_name=""):
    wid = str(wendangid or "").strip()
    actor = str(user_name or "").strip()
    if not wid:
        return False, "缺少日报ID", False
    if not actor:
        return False, "未获取到当前用户", False
    esc_wid = _xiaotu_sql_escape(wid)
    existing_like_users = []
    try:
        existing_row = sf_db(f"SELECT TOP 1 DianZan, YongHu FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}'") or []
        if isinstance(existing_row, list) and existing_row and isinstance(existing_row[0], dict):
            existing_row = existing_row[0]
        if isinstance(existing_row, list) and existing_row and isinstance(existing_row[0], (list, tuple)):
            existing_row = existing_row[0]
        if isinstance(existing_row, dict):
            if str(existing_row.get("DianZan") or existing_row.get("dianzan") or "").strip().upper() == "Y":
                existing_like_users = _xiaotu_parse_like_user_names(existing_row.get("YongHu") or existing_row.get("yonghu") or "")
        elif isinstance(existing_row, (list, tuple)):
            if str(existing_row[0] if len(existing_row) > 0 else "").strip().upper() == "Y":
                existing_like_users = _xiaotu_parse_like_user_names(existing_row[1] if len(existing_row) > 1 else "")
    except Exception:
        existing_like_users = []
    liked_now = actor not in existing_like_users
    if liked_now:
        existing_like_users.append(actor)
    else:
        existing_like_users = [name for name in existing_like_users if name != actor]
    like_users_text = _xiaotu_build_like_user_text(existing_like_users)
    esc_like_users = _xiaotu_sql_escape(like_users_text)
    dianzan_value = "Y" if like_users_text else ""
    sql = f"""
        IF EXISTS (SELECT 1 FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}')
            UPDATE BaoGao_dianzan
            SET DianZan='{dianzan_value}', YongHu=N'{esc_like_users}'
            WHERE WenDangID='{esc_wid}'
        ELSE
            INSERT INTO BaoGao_dianzan (WenDangID, DianZan, PingJia, HuiFu, YongHu)
            VALUES ('{esc_wid}', '{dianzan_value}', N'', N'', N'{esc_like_users}')
    """
    try:
        dui_db(sql)
        return True, "", liked_now
    except Exception as e:
        return False, str(e), False


def _xiaotu_append_report_comment(wendangid, user_name, comment_text):
    wid = str(wendangid or "").strip()
    comment = str(comment_text or "").strip()
    if not wid:
        return False, "缺少文档ID"
    if not comment:
        return False, "评论不能为空"
    actor = str(user_name or "匿名用户").strip() or "匿名用户"
    entry = _xiaotu_feedback_entry_line("comment", actor, comment)
    esc_wid = _xiaotu_sql_escape(wid)
    esc_entry = _xiaotu_sql_escape(entry)
    sql = f"""
        IF EXISTS (SELECT 1 FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}')
            UPDATE BaoGao_dianzan
            SET PingJia = CASE
                WHEN ISNULL(PingJia, '') = '' THEN N'{esc_entry}'
                ELSE CONVERT(NVARCHAR(MAX), PingJia) + CHAR(10) + N'{esc_entry}'
            END
            WHERE WenDangID='{esc_wid}'
        ELSE
            INSERT INTO BaoGao_dianzan (WenDangID, DianZan, PingJia, HuiFu, YongHu)
            VALUES ('{esc_wid}', '', N'{esc_entry}', N'', N'')
    """
    try:
        dui_db(sql)
        return True, ""
    except Exception as e:
        return False, str(e)


def _xiaotu_append_report_reply(wendangid, user_name, reply_text, target_name=""):
    wid = str(wendangid or "").strip()
    reply = str(reply_text or "").strip()
    if not wid:
        return False, "缺少文档ID"
    if not reply:
        return False, "回复内容不能为空"
    actor = str(user_name or "匿名用户").strip() or "匿名用户"
    target = str(target_name or "").strip()
    entry = _xiaotu_feedback_entry_line("reply", actor, reply, target)
    esc_wid = _xiaotu_sql_escape(wid)
    esc_entry = _xiaotu_sql_escape(entry)
    sql = f"""
        IF EXISTS (SELECT 1 FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}')
            UPDATE BaoGao_dianzan
            SET HuiFu = CASE
                WHEN ISNULL(HuiFu, '') = '' THEN N'{esc_entry}'
                ELSE CONVERT(NVARCHAR(MAX), HuiFu) + CHAR(10) + N'{esc_entry}'
            END
            WHERE WenDangID='{esc_wid}'
        ELSE
            INSERT INTO BaoGao_dianzan (WenDangID, DianZan, PingJia, HuiFu, YongHu)
            VALUES ('{esc_wid}', '', N'', N'{esc_entry}', N'')
    """
    try:
        dui_db(sql)
        return True, ""
    except Exception as e:
        return False, str(e)


def _xiaotu_remove_report_feedback_entry(wendangid, user_name, entry_type, entry_index):
    wid = str(wendangid or "").strip()
    actor = str(user_name or "").strip()
    kind = str(entry_type or "").strip().lower()
    if not wid:
        return False, "缺少日报ID"
    if not actor:
        return False, "未获取到当前用户"
    if kind not in {"comment", "reply"}:
        return False, "不支持的撤销类型"
    try:
        idx = int(entry_index)
    except Exception:
        return False, "缺少要撤销的记录"
    if idx < 0:
        return False, "撤销记录无效"
    esc_wid = _xiaotu_sql_escape(wid)
    field_name = "PingJia" if kind == "comment" else "HuiFu"
    rows = sf_db(f"SELECT TOP 1 {field_name} FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}'") or []
    row = rows[0] if isinstance(rows, list) and rows else rows
    if isinstance(row, dict):
        raw_text = str(row.get(field_name) or row.get(field_name.lower()) or "").strip()
    elif isinstance(row, (list, tuple)):
        raw_text = str(row[0] if len(row) > 0 else "").strip()
    else:
        raw_text = ""
    items = _xiaotu_parse_feedback_entries(raw_text, kind)
    if idx >= len(items):
        return False, "未找到要撤销的记录"
    target_item = items[idx] if isinstance(items[idx], dict) else {}
    item_actor = str(target_item.get("actor") or "").strip()
    if item_actor != actor:
        return False, "只能撤销自己提交的内容"
    new_items = [item for pos, item in enumerate(items) if pos != idx]
    new_text = _xiaotu_feedback_entries_to_text(new_items, kind)
    esc_new_text = _xiaotu_sql_escape(new_text)
    sql = f"""
        UPDATE BaoGao_dianzan
        SET {field_name}=N'{esc_new_text}'
        WHERE WenDangID='{esc_wid}'
    """
    try:
        dui_db(sql)
        return True, ""
    except Exception as e:
        return False, str(e)


def _xiaotu_get_report_feedback(wendangid, owner_name=""):
    wid = str(wendangid or "").strip()
    if not wid:
        return _xiaotu_enrich_feedback_data({"dianzan": "", "pinglun": "", "huifu": "", "yonghu": ""}, owner_name=owner_name)
    esc_wid = _xiaotu_sql_escape(wid)
    sql = f"SELECT TOP 1 DianZan, PingJia, HuiFu, YongHu FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}'"
    row = sf_db(sql) or []
    if isinstance(row, list) and row and isinstance(row[0], dict):
        row = row[0]
    if isinstance(row, list) and row and isinstance(row[0], (list, tuple)):
        row = row[0]
    if isinstance(row, dict):
        return _xiaotu_enrich_feedback_data({
            "dianzan": str(row.get("dianzan") or row.get("DianZan") or "").strip(),
            "pinglun": str(row.get("pinglun") or row.get("PingLun") or row.get("PingJia") or "").strip(),
            "huifu": str(row.get("huifu") or row.get("HuiFu") or "").strip(),
            "yonghu": str(row.get("yonghu") or row.get("YongHu") or "").strip(),
        }, owner_name=owner_name)
    if isinstance(row, (list, tuple)):
        return _xiaotu_enrich_feedback_data({
            "dianzan": str(row[0] if len(row) > 0 else "").strip(),
            "pinglun": str(row[1] if len(row) > 1 else "").strip(),
            "huifu": str(row[2] if len(row) > 2 else "").strip(),
            "yonghu": str(row[3] if len(row) > 3 else "").strip(),
        }, owner_name=owner_name)
    return _xiaotu_enrich_feedback_data({"dianzan": "", "pinglun": "", "huifu": "", "yonghu": ""}, owner_name=owner_name)


def _xiaotu_extract_comment_text(form_value):
    if isinstance(form_value, dict):
        direct = str(
            form_value.get("feedback_text")
            or form_value.get("comment_text")
            or form_value.get("comment")
            or form_value.get("reply_text")
            or form_value.get("reply")
            or form_value.get("pinglun")
            or form_value.get("PingJia")
            or form_value.get("huifu")
            or form_value.get("HuiFu")
            or ""
        ).strip()
        if direct:
            return direct
        for v in form_value.values():
            nested = _xiaotu_extract_comment_text(v)
            if nested:
                return nested
    elif isinstance(form_value, list):
        for item in form_value:
            nested = _xiaotu_extract_comment_text(item)
            if nested:
                return nested
    elif isinstance(form_value, str):
        txt = str(form_value or "").strip()
        if txt:
            return txt
    return ""


def _xiaotu_extract_reply_target_name(form_value):
    if isinstance(form_value, dict):
        direct = form_value.get("reply_target") or form_value.get("target_name") or form_value.get("reply_to")
        if isinstance(direct, dict):
            val = str(direct.get("value") or direct.get("content") or direct.get("text") or "").strip()
            if val:
                return val
        if isinstance(direct, (list, tuple)):
            for item in direct:
                nested = _xiaotu_extract_reply_target_name(item)
                if nested:
                    return nested
        text_val = str(direct or "").strip()
        if text_val:
            return text_val
        for v in form_value.values():
            nested = _xiaotu_extract_reply_target_name(v)
            if nested:
                return nested
    elif isinstance(form_value, list):
        for item in form_value:
            nested = _xiaotu_extract_reply_target_name(item)
            if nested:
                return nested
    return ""


def _xiaotu_build_card_callback_response(card, toast_type, toast_content):
    payload = {
        "toast": {
            "type": str(toast_type or "info"),
            "content": str(toast_content or "").strip() or "操作完成"
        }
    }
    return jsonify(payload), 200


def _xiaotu_notify_report_owner_feedback(wendangid, action_name, actor_name, comment_text="", target_name=""):
    wid = str(wendangid or "").strip()
    if not wid:
        return False, "缺少文档ID"
    ctx = _xiaotu_get_report_card_context(wid)
    owner_name = str((ctx or {}).get("owner_name") or "").strip()
    title_text = str((ctx or {}).get("title_text") or "未命名标题").strip() or "未命名标题"
    if not owner_name:
        return False, "未找到报告发起人"
    owner_open_id = _xiaotu_get_report_owner_open_id(wid) or _xiaotu_lookup_open_id_by_name(owner_name)
    if not owner_open_id:
        return False, "未找到发起人飞书ID"
    actor = str(actor_name or "").strip() or "匿名用户"
    if owner_name == actor:
        return True, "发起人本人操作，跳过同步通知"
    report_url = _xiaotu_build_report_history_url(wid)
    notice_markdown = _xiaotu_build_feedback_notice_markdown(
        action_name, actor, comment_text, target_name
    )
    header_title = "报告互动通知"
    header_template = "wathet"
    if action_name == "like_report":
        header_title = "你的报告收到新的点赞"
        header_template = "turquoise"
    elif action_name == "reply_report":
        header_title = "你的报告收到新的回复"
        header_template = "orange"
    else:
        header_title = "你的报告收到新的评论"
        header_template = "blue"
    feedback = _xiaotu_get_report_feedback(wid, owner_name=owner_name)
    card = _xiaotu_build_report_notify_card(
        title_text,
        str((ctx or {}).get("person_type") or "").strip(),
        str((ctx or {}).get("pingjia_text") or "").strip(),
        source_text=str((ctx or {}).get("source_text") or "").strip(),
        image_paths_text=str((ctx or {}).get("image_paths_text") or "").strip(),
        wendangid=wid,
        report_url=report_url,
        feedback_override=feedback,
        header_title=header_title,
        header_template=header_template,
        notice_markdown=notice_markdown
    )
    ok, resp = _feishu_send_message_detail(owner_open_id, "open_id", "interactive", card)
    if ok:
        message_id = str(((resp or {}).get("data") or {}).get("message_id") or "").strip()
        if message_id:
            _xiaotu_remember_report_card_message(wid, owner_open_id, message_id)
        return True, ""
    msg_lines = [
        header_title,
        f"文档标题：{title_text}",
        notice_markdown.replace("**", "")
    ]
    text_ok = _feishu_send_text(owner_open_id, "open_id", "\n".join([x for x in msg_lines if str(x).strip()]))
    return (True, "") if text_ok else (False, "飞书通知发送失败")


def _xiaotu_notify_feedback_reply_target(wendangid, actor_name, target_name, reply_text=""):
    wid = str(wendangid or "").strip()
    target = str(target_name or "").strip()
    actor = str(actor_name or "").strip() or "匿名用户"
    if not wid or not target or target == actor:
        return True, "无需通知回复对象"
    ctx = _xiaotu_get_report_card_context(wid)
    title_text = str((ctx or {}).get("title_text") or "未命名标题").strip() or "未命名标题"
    target_open_id = _xiaotu_lookup_open_id_by_name(target)
    if not target_open_id:
        return False, "未找到回复对象飞书ID"
    report_url = _xiaotu_build_report_history_url(wid)
    notice_markdown = _xiaotu_build_feedback_notice_markdown(
        "reply_report", actor, reply_text, target
    )
    feedback = _xiaotu_get_report_feedback(wid, owner_name=str((ctx or {}).get("owner_name") or "").strip())
    card = _xiaotu_build_report_notify_card(
        title_text,
        str((ctx or {}).get("person_type") or "").strip(),
        str((ctx or {}).get("pingjia_text") or "").strip(),
        source_text=str((ctx or {}).get("source_text") or "").strip(),
        image_paths_text=str((ctx or {}).get("image_paths_text") or "").strip(),
        wendangid=wid,
        report_url=report_url,
        feedback_override=feedback,
        header_title="你收到一条新的评价回复",
        header_template="orange",
        notice_markdown=notice_markdown
    )
    ok, resp = _feishu_send_message_detail(target_open_id, "open_id", "interactive", card)
    if ok:
        message_id = str(((resp or {}).get("data") or {}).get("message_id") or "").strip()
        if message_id:
            _xiaotu_remember_report_card_message(wid, target_open_id, message_id)
        return True, ""
    msg = "\n".join([
        "你收到一条新的评价回复",
        f"文档标题：{title_text}",
        f"回复人：{actor}",
        f"回复给：{target}",
        f"回复内容：{str(reply_text or '').strip() or '（空）'}",
    ])
    text_ok = _feishu_send_text(target_open_id, "open_id", msg)
    return (True, "") if text_ok else (False, "回复对象通知发送失败")


def _xiaotu_notify_feedback_open_ids(wendangid, action_name, actor_name, comment_text="", target_name="", open_ids=None, skip_open_ids=None):
    wid = str(wendangid or "").strip()
    if not wid:
        return []
    ctx = _xiaotu_get_report_card_context(wid)
    title_text = str((ctx or {}).get("title_text") or "未命名标题").strip() or "未命名标题"
    owner_name = str((ctx or {}).get("owner_name") or "").strip()
    report_url = _xiaotu_build_report_history_url(wid)
    feedback = _xiaotu_get_report_feedback(wid, owner_name=owner_name)
    actor = str(actor_name or "").strip() or "匿名用户"
    notice_markdown = _xiaotu_build_feedback_notice_markdown(
        action_name, actor, comment_text, target_name
    )
    header_title = "你收到一条新的评价互动"
    header_template = "wathet"
    if action_name == "like_report":
        header_title = "你收到一条新的评价点赞"
        header_template = "turquoise"
    elif action_name == "reply_report":
        header_title = "你收到一条新的评价回复"
        header_template = "orange"
    else:
        header_title = "你收到一条新的评价评论"
        header_template = "blue"
    card = _xiaotu_build_report_notify_card(
        title_text,
        str((ctx or {}).get("person_type") or "").strip(),
        str((ctx or {}).get("pingjia_text") or "").strip(),
        source_text=str((ctx or {}).get("source_text") or "").strip(),
        image_paths_text=str((ctx or {}).get("image_paths_text") or "").strip(),
        wendangid=wid,
        report_url=report_url,
        feedback_override=feedback,
        header_title=header_title,
        header_template=header_template,
        notice_markdown=notice_markdown
    )
    skip_ids = {
        str(x or "").strip()
        for x in (skip_open_ids or [])
        if str(x or "").strip()
    }
    results = []
    seen = set()
    for raw in (open_ids or []):
        oid = str(raw or "").strip()
        if not oid or oid in seen or oid in skip_ids:
            continue
        seen.add(oid)
        ok, resp = _feishu_send_message_detail(oid, "open_id", "interactive", card)
        message_id = str(((resp or {}).get("data") or {}).get("message_id") or "").strip() if ok else ""
        if message_id:
            _xiaotu_remember_report_card_message(wid, oid, message_id)
        results.append({
            "open_id": oid,
            "ok": bool(ok),
            "message_id": message_id,
            "error": "" if ok else "飞书通知发送失败"
        })
    return results


def _xiaotu_finalize_report_card_feedback_async(
    wendangid,
    action_name,
    actor_name,
    target_message_id="",
    open_message_id="",
    operator_open_id="",
    reply_target_name="",
    comment_text="",
    feedback_expanded=False,
    doc_url="",
    image_key="",
):
    wid = str(wendangid or "").strip()
    effective_action = str(action_name or "").strip()
    if not wid or not effective_action:
        return
    try:
        ctx = _xiaotu_get_report_card_context(wid)
        title_text = str((ctx or {}).get("title_text") or "未命名标题").strip()
        person_type = str((ctx or {}).get("person_type") or "未设置").strip()
        pingjia_text = str((ctx or {}).get("pingjia_text") or "").strip()
        source_text = str((ctx or {}).get("source_text") or "").strip()
        image_paths_text = str((ctx or {}).get("image_paths_text") or "").strip()
        owner_name = str((ctx or {}).get("owner_name") or "").strip()
        report_url = _xiaotu_build_report_history_url(wid)
        updated_feedback = _xiaotu_get_report_feedback(wid, owner_name=owner_name)
        card = _xiaotu_build_report_notify_card(
            title_text,
            person_type,
            pingjia_text,
            doc_url=doc_url,
            source_text=source_text,
            image_key=image_key,
            image_paths_text=image_paths_text,
            wendangid=wid,
            report_url=report_url,
            feedback_override=updated_feedback,
            feedback_expanded=feedback_expanded
        )
        patch_ok = True
        patch_err = ""
        if str(target_message_id or "").strip():
            patch_ok, patch_err = _feishu_update_message_card(target_message_id, card)
        owner_notify_ok, owner_notify_err = _xiaotu_notify_report_owner_feedback(
            wid, effective_action, actor_name, comment_text, reply_target_name
        )
        reply_target_notify_ok = True
        reply_target_notify_err = ""
        if effective_action == "reply_report":
            reply_target_notify_ok, reply_target_notify_err = _xiaotu_notify_feedback_reply_target(
                wid, actor_name, reply_target_name, comment_text
            )
        owner_open_id = _xiaotu_get_report_owner_open_id(wid) or _xiaotu_lookup_open_id_by_name(owner_name)
        reply_target_open_id = _xiaotu_lookup_open_id_by_name(reply_target_name) if effective_action == "reply_report" else ""
        participant_notify_results = _xiaotu_notify_feedback_open_ids(
            wid,
            effective_action,
            actor_name,
            comment_text,
            reply_target_name,
            open_ids=_xiaotu_get_report_card_receive_ids(wid),
            skip_open_ids=[operator_open_id, owner_open_id, reply_target_open_id]
        )
        related_open_ids = [
            operator_open_id,
            owner_open_id,
            reply_target_open_id,
            *(_xiaotu_get_report_card_receive_ids(wid) or [])
        ]
        related_message_map = {}
        for related_open_id in related_open_ids:
            oid = str(related_open_id or "").strip()
            if not oid or oid in related_message_map:
                continue
            related_message_map[oid] = _xiaotu_get_report_card_message_ids(wid, oid)
        sync_results = _xiaotu_patch_related_report_cards(
            wid,
            related_open_ids,
            card,
            skip_message_ids=[target_message_id, open_message_id]
        )
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "report_card_async_finalize",
                "action": effective_action,
                "wendangid": wid,
                "target_message_id": str(target_message_id or "").strip(),
                "patch_ok": bool(patch_ok),
                "patch_err": str(patch_err or ""),
                "owner_open_id": owner_open_id,
                "owner_notify_ok": bool(owner_notify_ok),
                "owner_notify_err": str(owner_notify_err or ""),
                "reply_target_name": str(reply_target_name or "").strip(),
                "reply_target_notify_ok": bool(reply_target_notify_ok),
                "reply_target_notify_err": str(reply_target_notify_err or ""),
                "participant_notify_results": participant_notify_results,
                "related_message_map": related_message_map,
                "sync_results": sync_results
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
    except Exception as e:
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "report_card_async_finalize_error",
                "action": effective_action,
                "wendangid": wid,
                "error": str(e)
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass


def _xiaotu_handle_report_card_action(data):
    payload = _xiaotu_get_card_action_payload(data)
    value = payload.get("value") or {}
    action_name = str(value.get("action") or "").strip()
    wendangid = str(value.get("wendangid") or "").strip()
    doc_url = str(value.get("doc_url") or "").strip()
    image_key = str(value.get("image_key") or "").strip()
    feedback_expanded = str(value.get("feedback_expanded") or "").strip() in {"1", "true", "True", "yes", "on"}
    open_message_id = str(payload.get("open_message_id") or "").strip()
    operator_open_id = str(payload.get("open_id") or "").strip()
    remembered_message_id = _xiaotu_get_report_card_message_id(wendangid, operator_open_id)
    target_message_id = open_message_id or remembered_message_id
    ctx = _xiaotu_get_report_card_context(wendangid)
    title_text = str(ctx.get("title_text") or "未命名标题").strip()
    person_type = str(ctx.get("person_type") or "未设置").strip()
    pingjia_text = str(ctx.get("pingjia_text") or "").strip()
    source_text = str(ctx.get("source_text") or "").strip()
    image_paths_text = str(ctx.get("image_paths_text") or "").strip()
    try:
        _feishu_recent_events.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "stage": "report_card_action_enter",
            "action": action_name,
            "wendangid": wendangid,
            "open_id": str(payload.get("open_id") or "").strip(),
            "user_id": str(payload.get("user_id") or "").strip(),
            "union_id": str(payload.get("union_id") or "").strip(),
            "operator_name": str(payload.get("operator_name") or "").strip(),
            "open_message_id": open_message_id,
            "remembered_message_id": remembered_message_id,
            "has_form_value": bool(payload.get("form_value")),
        })
        if len(_feishu_recent_events) > _feishu_recent_events_limit:
            del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
    except Exception:
        pass
    if action_name == "toggle_feedback_records":
        updated_feedback = _xiaotu_get_report_feedback(wendangid, owner_name=str(ctx.get("owner_name") or "").strip())
        card = _xiaotu_build_report_notify_card(
            title_text,
            person_type,
            pingjia_text,
            doc_url=doc_url,
            source_text=source_text,
            image_key=image_key,
            image_paths_text=image_paths_text,
            wendangid=wendangid,
            report_url=_xiaotu_build_report_history_url(wendangid),
            feedback_override=updated_feedback,
            feedback_expanded=feedback_expanded
        )
        patch_ok = True
        patch_err = ""
        if target_message_id:
            patch_ok, patch_err = _feishu_update_message_card(target_message_id, card)
        toast_text = "已展开记录" if feedback_expanded else "已收起记录"
        if target_message_id and not patch_ok:
            return _xiaotu_build_card_callback_response(None, "warning", f"{toast_text}，但卡片刷新失败：{patch_err or '未知错误'}")
        return _xiaotu_build_card_callback_response(card, "success", toast_text)
    if action_name == "like_report":
        actor_name = _xiaotu_resolve_card_actor_name(payload)
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "report_card_actor_resolved",
                "action": action_name,
                "wendangid": wendangid,
                "open_id": str(payload.get("open_id") or "").strip(),
                "user_id": str(payload.get("user_id") or "").strip(),
                "union_id": str(payload.get("union_id") or "").strip(),
                "operator_name": str(payload.get("operator_name") or "").strip(),
                "actor_name": str(actor_name or "").strip(),
            })
        except Exception:
            pass
        ok, err = _xiaotu_upsert_report_like(wendangid, actor_name)
        if not ok:
            try:
                _feishu_recent_events.append({
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "stage": "report_card_action_error",
                    "action": action_name,
                    "wendangid": wendangid,
                    "error": str(err or "未知错误")
                })
            except Exception:
                pass
            return _xiaotu_build_card_callback_response(None, "error", f"点赞失败：{err or '未知错误'}")
        _feishu_submit_task(
            _xiaotu_finalize_report_card_feedback_async,
            wendangid,
            action_name,
            actor_name,
            target_message_id,
            open_message_id,
            operator_open_id,
            "",
            "",
            feedback_expanded,
            doc_url,
            image_key,
        )
        return _xiaotu_build_card_callback_response(None, "success", "已点赞")
    if action_name in {"comment_report", "reply_report", "submit_feedback_report"}:
        form_value = payload.get("form_value") or {}
        comment_text = _xiaotu_extract_comment_text(form_value)
        reply_target_name = _xiaotu_extract_reply_target_name(form_value)
        actor_name = _xiaotu_resolve_card_actor_name(payload)
        effective_action = action_name
        if action_name == "submit_feedback_report":
            effective_action = "reply_report" if reply_target_name else "comment_report"
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "report_card_actor_resolved",
                "action": effective_action,
                "wendangid": wendangid,
                "open_id": str(payload.get("open_id") or "").strip(),
                "user_id": str(payload.get("user_id") or "").strip(),
                "union_id": str(payload.get("union_id") or "").strip(),
                "operator_name": str(payload.get("operator_name") or "").strip(),
                "actor_name": str(actor_name or "").strip(),
                "reply_target_name": str(reply_target_name or "").strip(),
            })
        except Exception:
            pass
        if not comment_text:
            return _xiaotu_build_card_callback_response(None, "warning", "请先输入互动内容")
        if effective_action == "reply_report":
            if not reply_target_name:
                return _xiaotu_build_card_callback_response(None, "warning", "请先选择回复对象")
            ok, err = _xiaotu_append_report_reply(wendangid, actor_name, comment_text, reply_target_name)
            if not ok:
                try:
                    _feishu_recent_events.append({
                        "ts": datetime.now().isoformat(timespec="seconds"),
                        "stage": "report_card_action_error",
                        "action": effective_action,
                        "wendangid": wendangid,
                        "error": str(err or "未知错误"),
                        "comment_preview": str(comment_text or "")[:80],
                        "reply_target_name": str(reply_target_name or "").strip()
                    })
                except Exception:
                    pass
                return _xiaotu_build_card_callback_response(None, "error", err or "回复提交失败")
        else:
            ok, err = _xiaotu_append_report_comment(wendangid, actor_name, comment_text)
            if not ok:
                try:
                    _feishu_recent_events.append({
                        "ts": datetime.now().isoformat(timespec="seconds"),
                        "stage": "report_card_action_error",
                        "action": effective_action,
                        "wendangid": wendangid,
                        "error": str(err or "未知错误"),
                        "comment_preview": str(comment_text or "")[:80]
                    })
                except Exception:
                    pass
                return _xiaotu_build_card_callback_response(None, "error", err or "评论提交失败")
        _feishu_submit_task(
            _xiaotu_finalize_report_card_feedback_async,
            wendangid,
            effective_action,
            actor_name,
            target_message_id,
            open_message_id,
            operator_open_id,
            reply_target_name,
            comment_text,
            feedback_expanded,
            doc_url,
            image_key,
        )
        success_label = "回复已提交并通知对方" if effective_action == "reply_report" else "评论已提交"
        return _xiaotu_build_card_callback_response(None, "success", success_label)
    return _xiaotu_build_card_callback_response(None, "info", "未识别的卡片操作")


def _split_text(text, max_len=1500):
    t = str(text or "")
    if not t:
        return []
    if len(t) <= max_len:
        return [t]
    parts = []
    buf = []
    buf_len = 0
    for line in t.splitlines(True):
        if not line:
            continue
        if len(line) > max_len:
            if buf:
                parts.append("".join(buf).strip())
                buf = []
                buf_len = 0
            for i in range(0, len(line), max_len):
                chunk = line[i:i + max_len].strip()
                if chunk:
                    parts.append(chunk)
            continue
        if buf_len + len(line) > max_len and buf:
            parts.append("".join(buf).strip())
            buf = [line]
            buf_len = len(line)
        else:
            buf.append(line)
            buf_len += len(line)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _parse_forward_departments(prompt_text):
    t = str(prompt_text or "").strip()
    if not t:
        return []
    if any(x in t for x in ["不发给领导", "不要发给领导", "别发给领导", "无需发给领导"]):
        return []
    targets = []
    candidates = [
        "AI部", "财务部", "人力行政部",
        "运营一部", "运营二部", "运营三部", "运营六部",
        "研发部", "技术部", "采购部", "摄影部", "视觉设计部",
        "TK项目", "TK部门", "深圳团队", "仓储部", "短视频部", "BD部", "客服", "产品&店铺运营"
    ]
    for dep in candidates:
        if (f"发给{dep}" in t) or (f"给{dep}" in t) or (f"发到{dep}" in t) or (f"同步{dep}" in t):
            targets.append(dep)
    uniq = []
    seen = set()
    for x in targets:
        x = str(x or "").strip()
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _forward_text_to_departments(department_names, text):
    deps = department_names or []
    if not deps:
        return {"success": 0, "failed": 0, "total": 0, "departments": []}
    ms = MessageService("company1")
    summary = {"success": 0, "failed": 0, "total": 0, "departments": []}
    for dep in deps:
        dep_name = str(dep or "").strip()
        if not dep_name:
            continue
        sent = {"department": dep_name, "success": 0, "failed": 0, "total": 0}
        chunks = _split_text(text, max_len=1500)
        last_stats = None
        for chunk in chunks:
            last_stats = ms.send_message_to_department_members(dep_name, chunk, at_all=False)
        if isinstance(last_stats, dict):
            sent["success"] = int(last_stats.get("success") or 0)
            sent["failed"] = int(last_stats.get("failed") or 0)
            sent["total"] = int(last_stats.get("total") or 0)
        summary["success"] += sent["success"]
        summary["failed"] += sent["failed"]
        summary["total"] += sent["total"]
        summary["departments"].append(sent)
    return summary


def _feishu_parse_message_content(content):
    if content is None:
        return {}
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            obj = json.loads(content)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _feishu_extract_image_keys(obj, limit=4):
    keys = []
    seen = set()

    def walk(x):
        if x is None or len(keys) >= int(limit or 0):
            return
        if isinstance(x, dict):
            for k, v in x.items():
                if len(keys) >= int(limit or 0):
                    return
                lk = str(k or "").strip().lower()
                if lk in {"image_key", "imagekey"} and isinstance(v, str):
                    s = v.strip()
                    if s and s not in seen:
                        seen.add(s)
                        keys.append(s)
                        if len(keys) >= int(limit or 0):
                            return
                walk(v)
            return
        if isinstance(x, list):
            for it in x:
                walk(it)
                if len(keys) >= int(limit or 0):
                    return
            return

    walk(obj)
    return keys


def _feishu_download_resource(message_id, file_key, resource_type):
    file_key = (file_key or "").strip()
    resource_type = (resource_type or "").strip()
    if not file_key:
        return None, ""

    token = permission_manager.get_access_token()
    if not token:
        return None, ""

    import requests
    headers = {"Authorization": f"Bearer {token}"}
    urls = []
    if message_id and resource_type:
        urls.append(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}?type={resource_type}"
        )
    if resource_type == "image":
        urls.append(f"https://open.feishu.cn/open-apis/im/v1/images/{file_key}?type=message")
        urls.append(f"https://open.feishu.cn/open-apis/im/v1/images/{file_key}?image_type=message")

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200 and resp.content:
                return resp.content, str(resp.headers.get("Content-Type") or "")
        except Exception:
            continue
    return None, ""


def _generate_ai_answer_with_doc(prompt_text, doc_text, doc_name="", chat_id=None):
    q = (prompt_text or "").strip()
    if not q:
        q = f"请阅读文档《{doc_name}》并提炼关键信息，给出结构化总结。".strip("《》")
    content = (doc_text or "").strip()
    if not content:
        return "我没有解析出文档内容。请换成可复制文字的文档（txt/docx/xlsx），或把关键内容粘贴到消息里。"

    clipped = content[:60000]
    user_content = f"用户问题：{q}\n\n文档《{doc_name or '未知文件'}》内容如下（可能已截断）：\n{clipped}"
    system_content = "你是图创AI，是公司内部的飞书智能助手。请用中文回答，严格基于用户提供的文档内容作答，不要编造文档里不存在的信息。若文档内容不足以支撑结论，先说明缺少的信息。"
    history = _feishu_get_chat_history(chat_id) if chat_id else []

    try:
        messages = [{"role": "system", "content": system_content}, *history, {"role": "user", "content": user_content}]
        return _ai_chat_complete(messages, max_tokens=900, temperature=0.2, model_candidates=_OPENAI_TEXT_MODEL_CANDIDATES)
    except Exception as e:
        _safe_debug_print(f"AI回复生成失败(文档模式): {e}")
        return "我这边文档识别后的回答生成失败了，请稍后再试。"


def _generate_ai_answer_with_image(prompt_text, image_bytes, image_mime="", chat_id=None):
    q = (prompt_text or "").strip()
    if not q:
        q = "请识别图片里的文字/表格/关键信息，并用中文结构化输出。"
    if not image_bytes:
        return "我没有拿到图片数据。"

    mime = (image_mime or "").split(";", 1)[0].strip().lower()
    if not mime.startswith("image/"):
        mime = "image/png"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    system_content = "你是图创AI，是公司内部的飞书智能助手。请用中文回答。先识别图片内容，再根据用户问题给出结论与可执行建议。不要臆测看不清的内容。"
    history = _feishu_get_chat_history(chat_id) if chat_id else []
    messages = [{"role": "system", "content": system_content}] + history + [{
        "role": "user",
        "content": [
            {"type": "text", "text": q},
            {"type": "image_url", "image_url": {"url": data_url}}
        ]
    }]

    last_err = None
    try:
        return _ai_chat_complete(messages, max_tokens=900, temperature=0.2, model_candidates=_OPENAI_VISION_MODEL_CANDIDATES)
    except Exception as e:
        last_err = e

    _safe_debug_print(f"AI回复生成失败(图片模式): {last_err}")
    return "我这边暂时无法识别图片（当前模型/接口可能不支持多模态）。你可以把图片里的关键文字粘贴出来，我再继续处理。"


def _ocr_images_bytes_with_ai(images):
    if not images:
        return ""

    def _to_data_url(image_bytes, image_mime=""):
        mime = (image_mime or "").split(";", 1)[0].strip().lower()
        if not mime.startswith("image/"):
            mime = "image/png"
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mime};base64,{b64}"

    normalized = []
    if isinstance(images, (bytes, bytearray)):
        normalized = [(bytes(images), "image/png")]
    elif isinstance(images, (list, tuple)):
        for it in images:
            if isinstance(it, dict):
                b = it.get("bytes") or it.get("data") or b""
                m = it.get("mime") or it.get("content_type") or ""
                if b:
                    normalized.append((b, m))
                continue
            if isinstance(it, (list, tuple)) and it:
                b = it[0]
                m = it[1] if len(it) > 1 else ""
                if b:
                    normalized.append((b, m))

    if not normalized:
        return ""

    system_content = (
        "你是OCR引擎。你的任务是从图片中提取可读文字并原样输出。\n"
        "要求：\n"
        "1) 只输出识别到的文字内容，不要总结、不要解释、不要补充推测。\n"
        "2) 识别到表格时用Markdown表格输出；识别到标题/列表时尽量保持原结构。\n"
        "3) 对看不清/缺失的部分用“[无法识别]”标注，不要编造。\n"
        "4) 按下面固定格式输出，每张图片一段：\n"
        "【图片1】\\n...\\n\\n【图片2】\\n...（依次类推）"
    )

    model_candidates = ["Qwen/Qwen2.5-VL-7B-Instruct", "zai-org/GLM-4.5V"] + list(_OPENAI_VISION_MODEL_CANDIDATES or [])
    seen = set()
    model_candidates = [m for m in model_candidates if m and not (m in seen or seen.add(m))]
    out_parts = []
    for base_idx in range(0, len(normalized), 4):
        batch = normalized[base_idx:base_idx + 4]
        content = [{"type": "text", "text": "请分别对下面每张图片做OCR，并按指定格式输出。"}]
        for b, m in batch:
            try:
                url = _to_data_url(b, m)
            except Exception:
                continue
            content.append({"type": "image_url", "image_url": {"url": url}})
        messages = [{"role": "system", "content": system_content}, {"role": "user", "content": content}]

        try:
            t = _ai_chat_complete(messages, max_tokens=1600, temperature=0.0, model_candidates=model_candidates)
        except Exception as e:
            _safe_debug_print(f"OCR失败: {e}")
            t = ""
            fallback = []
            for i, (b, m) in enumerate(batch, start=1):
                url = _to_data_url(b, m)
                one = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": [{"type": "text", "text": f"请对这张图片做OCR，只输出识别结果。\\n【图片{i}】"}, {"type": "image_url", "image_url": {"url": url}}]},
                ]
                try:
                    one_text = _ai_chat_complete(one, max_tokens=900, temperature=0.0, model_candidates=model_candidates)
                except Exception:
                    one_text = ""
                one_text = (one_text or "").strip()
                if one_text:
                    fallback.append(one_text)
            if fallback:
                t = "\n\n".join(fallback).strip()

        t = (t or "").strip()
        if t:
            out_parts.append(t)
    return "\n\n".join(out_parts).strip()

try:
    kb_service.set_ocr_image_func(_ocr_images_bytes_with_ai)
except Exception:
    pass


def _merge_system_content(base_system, extra_system):
    b = str(base_system or "").strip()
    e = str(extra_system or "").strip()
    if not e:
        return b
    if not b:
        return e
    return f"{b}\n\n你还需要遵循以下技能说明：\n{e}"


def _generate_ai_answer(question_text, chat_id=None, extra_system_content=""):
    def _normalize_web_search_trigger(text):
        t = (text or "").strip()
        lowered = t.lower()
        triggers = ["联网:", "联网：", "实时搜索:", "实时搜索：", "实时检索:", "实时检索：", "web:", "search:"]
        for p in triggers:
            if lowered.startswith(p):
                return t[len(p):].strip(), True
        if "联网搜索" in t or "实时搜索" in t or "联网查" in t:
            return t.replace("联网搜索", "").replace("实时搜索", "").replace("联网查", "").strip(), True
        return t, False

    def _should_web_search_by_keywords(text):
        t = (text or "").strip().lower()
        if not t:
            return False
        keywords = [
            "最新", "今天", "现在", "本周", "本月", "今年", "昨日", "近期",
            "新闻", "公告", "发布", "更新", "版本",
            "官网", "下载", "价格", "对比", "政策", "法规", "通知",
            "天气", "气温", "温度", "预报", "台风", "降雨", "雨量", "风力", "湿度", "空气质量", "pm2.5",
        ]
        return any(k in t for k in keywords)

    def _google_cse_search(query, max_results=5):
        api_key = (os.environ.get("GOOGLE_CSE_API_KEY") or _GOOGLE_CSE_API_KEY or "").strip()
        cx = (os.environ.get("GOOGLE_CSE_CX") or _GOOGLE_CSE_CX or "").strip()
        if not api_key or not cx:
            return [], "未配置GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX"
        q2 = (query or "").strip()
        if not q2:
            return [], "查询为空"
        try:
            num = int(max_results or 5)
            num = max(1, min(num, 10))
        except Exception:
            num = 5
        try:
            resp = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": api_key,
                    "cx": cx,
                    "q": q2[:400],
                    "num": num,
                    "safe": "active",
                },
                timeout=20,
            )
            if resp.status_code != 200:
                try:
                    detail = (resp.text or "").strip()
                except Exception:
                    detail = ""
                detail = detail[:300].strip() if detail else ""
                return [], f"Google CSE返回状态码{resp.status_code}{('，响应：' + detail) if detail else ''}"
            payload = resp.json() if resp.content else {}
            items = payload.get("items") or []
            if not isinstance(items, list):
                return [], "Google CSE响应格式异常(items不是list)"
            normalized = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                url = str(it.get("link") or "").strip()
                title = str(it.get("title") or "").strip()
                content = str(it.get("snippet") or "").strip()
                if not url and not content:
                    continue
                normalized.append({"url": url, "title": title, "content": content})
            if not normalized:
                return [], "Google CSE未返回有效结果"
            return normalized, ""
        except Exception as e:
            return [], f"Google CSE请求失败: {type(e).__name__}: {str(e)[:200]}"

    def _tavily_search(query, max_results=5, search_depth="basic"):
        api_key = (os.environ.get("TAVILY_API_KEY") or _TAVILY_API_KEY or "").strip()
        if not api_key:
            return [], "未配置TAVILY_API_KEY"
        q2 = (query or "").strip()
        if not q2:
            return [], "查询为空"
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": q2[:400],
                    "search_depth": search_depth,
                    "max_results": int(max_results or 5),
                    "include_answer": False,
                    "include_raw_content": False,
                    "include_images": False,
                },
                timeout=20,
            )
            if resp.status_code != 200:
                try:
                    detail = (resp.text or "").strip()
                except Exception:
                    detail = ""
                detail = detail[:300].strip() if detail else ""
                return [], f"Tavily返回状态码{resp.status_code}{('，响应：' + detail) if detail else ''}"
            payload = resp.json() if resp.content else {}
            results = payload.get("results") or []
            if not isinstance(results, list):
                return [], "Tavily响应格式异常(results不是list)"
            normalized = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                url = str(r.get("url") or "").strip()
                title = str(r.get("title") or "").strip()
                content = str(r.get("content") or "").strip()
                if not url and not content:
                    continue
                normalized.append({"url": url, "title": title, "content": content})
            if not normalized:
                return [], "Tavily未返回有效结果"
            return normalized, ""
        except Exception as e:
            return [], f"Tavily请求失败: {type(e).__name__}: {str(e)[:200]}"

    def _format_web_results(results, limit_chars=8000):
        parts = []
        for i, r in enumerate(results or [], start=1):
            if not isinstance(r, dict):
                continue
            title = (r.get("title") or "").strip()
            url = (r.get("url") or "").strip()
            content = (r.get("content") or "").strip()
            block = f"【联网结果{i}】\n标题：{title or '（无标题）'}\n链接：{url or '（无链接）'}\n摘要：{content}"
            parts.append(block)
            if sum(len(x) for x in parts) >= int(limit_chars or 0):
                break
        out = "\n\n".join(parts).strip()
        return out[: int(limit_chars or 0)].strip() if limit_chars else out

    q_raw = (question_text or "").strip()
    q, force_web_search = _normalize_web_search_trigger(q_raw)
    if not q:
        return f"我在。请直接描述你的问题，我会尽量给出可执行的答案。"

    history = _feishu_get_chat_history(chat_id) if chat_id else []

    kb_snippets = []
    try:
        kb_snippets = kb_service.search(q, top_snippets=5)
    except Exception as e:
        _safe_debug_print(f"知识库检索失败: {e}")
        kb_snippets = []

    kb_use = False
    if kb_snippets:
        top = kb_snippets[0] or {}
        if (top.get("overlap") or 0) >= 2 or (top.get("score") or 0) >= 0.18:
            kb_use = True

    web_results = []
    web_error = ""
    need_web_by_keyword = _should_web_search_by_keywords(q)
    if force_web_search or (not kb_use) or need_web_by_keyword:
        _safe_debug_print(
            f"联网检索触发 chat_id={chat_id or ''} force={force_web_search} kb_use={kb_use} keyword={need_web_by_keyword} "
            f"google_key={bool((os.environ.get('GOOGLE_CSE_API_KEY') or _GOOGLE_CSE_API_KEY).strip())} "
            f"google_cx={bool((os.environ.get('GOOGLE_CSE_CX') or _GOOGLE_CSE_CX).strip())} "
            f"tavily_key={bool((os.environ.get('TAVILY_API_KEY') or _TAVILY_API_KEY).strip())}"
        )
        web_results, google_error = _google_cse_search(q, max_results=5)
        web_error = google_error or ""
        if web_error:
            _safe_debug_print(f"Google检索失败: {web_error}")
        if not web_results:
            web_results, tavily_error = _tavily_search(q, max_results=5, search_depth="basic")
            tavily_error = tavily_error or ""
            if tavily_error:
                _safe_debug_print(f"Tavily检索失败: {tavily_error}")
            if (not web_results) and (web_error and tavily_error):
                web_error = f"{web_error}；备选Tavily：{tavily_error}"
            elif not web_results:
                web_error = tavily_error or web_error
        else:
            _safe_debug_print(f"Google检索成功: results={len(web_results)}")
    web_context = _format_web_results(web_results, limit_chars=8000) if web_results else ""
    if force_web_search and (not web_context):
        return (
            f"我这边没有联网检索到结果。原因：{web_error or '未知错误'}。"
            f"请检查服务进程是否已设置环境变量 GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX（优先），或 TAVILY_API_KEY（备选），"
            f"并确认服务器可访问 Google Custom Search API / https://api.tavily.com 。"
            f"（PowerShell 里要用：$env:GOOGLE_CSE_API_KEY='...' / $env:GOOGLE_CSE_CX='...'，不要用 set）"
        )
    if need_web_by_keyword and (not kb_use) and (not web_context):
        return (
            f"这个问题看起来需要实时信息，但我这边联网检索失败了。原因：{web_error or '未知错误'}。"
            f"请确认服务进程已注入环境变量 GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX（优先），或 TAVILY_API_KEY（备选），"
            f"并确认服务器出网可访问对应接口。"
            f"（PowerShell 里要用：$env:GOOGLE_CSE_API_KEY='...' / $env:GOOGLE_CSE_CX='...'，不要用 set）"
        )

    if kb_use:
        kb_blocks = []
        for i, s in enumerate(kb_snippets, start=1):
            kb_blocks.append(f"【知识库片段{i}】\n来源：{s.get('doc')}\n内容：{s.get('text')}")
        kb_context = "\n\n".join(kb_blocks).strip()
        user_content = f"问题：{q}\n\n请优先基于下列知识库片段回答；如果片段不足以支撑结论，请先说明缺口，再给出可执行建议。"
        if web_context:
            user_content += f"\n\n如果知识库不足以支撑结论，可参考联网检索结果补充，但必须标注链接来源，且不要编造未在来源中出现的信息。"
            user_content += f"\n\n{kb_context}\n\n{web_context}"
        else:
            user_content += f"\n\n{kb_context}"
        system_content = "你是图创AI，是公司内部的飞书智能助手。请用中文回答，优先使用知识库内容作答。不要编造知识库里不存在的事实。答案尽量给出可执行步骤，并在关键结论后标注引用来源（例如：来源：六部.xlsx；或 来源：https://example.com）。"
        system_content = _merge_system_content(system_content, extra_system_content)
        try:
            messages = [{"role": "system", "content": system_content}, *history, {"role": "user", "content": user_content}]
            content = _ai_chat_complete(messages, max_tokens=900, temperature=0.2, model_candidates=_OPENAI_TEXT_MODEL_CANDIDATES)
            if content:
                return content
        except Exception as e:
            _safe_debug_print(f"AI回复生成失败(知识库模式): {e}")
            parts = []
            for s in kb_snippets[:3]:
                parts.append(f"来源：{s.get('doc')}\n{s.get('text')}")
            if parts:
                return "我优先从知识库里找到了这些相关内容：\n\n" + "\n\n---\n\n".join(parts)

    try:
        system_content = "你是图创AI，是公司内部的飞书智能助手。请用中文回答，给出清晰可执行的步骤或结论。"
        user_content = q
        if web_context:
            system_content = (
                "你是图创AI，是公司内部的飞书智能助手。请用中文回答。\n"
                "你可以使用下面提供的联网检索结果，但必须严格基于来源内容作答，不要编造。\n"
                "在使用某条联网信息时，请在该句末尾用“(来源: URL)”标注链接。"
            )
            user_content = f"问题：{q}\n\n联网检索结果如下：\n{web_context}"
        system_content = _merge_system_content(system_content, extra_system_content)
        messages = [{"role": "system", "content": system_content}, *history, {"role": "user", "content": user_content}]
        content = _ai_chat_complete(messages, max_tokens=800, temperature=0.4, model_candidates=_OPENAI_TEXT_MODEL_CANDIDATES)
        return content or "我暂时没生成出有效答案，请换一种问法再试一次。"
    except Exception as e:
        _safe_debug_print(f"AI回复生成失败: {e}")
        return "我这边生成回复失败了，请稍后再试。"


def _async_generate_and_reply(chat_id, question_text):
    try:
        answer = _generate_ai_answer(question_text, chat_id=chat_id)
        _feishu_append_chat_history(chat_id, "user", question_text or "")
        _feishu_append_chat_history(chat_id, "assistant", answer or "")
        _feishu_send_text_to_chat(chat_id, answer)
    except Exception as e:
        _safe_debug_print(f"异步回复失败: {e}")
        try:
            _feishu_send_text_to_chat(chat_id, "我这边处理时发生异常，请稍后重试。")
        except Exception:
            pass


def _async_generate_and_reply_with_skill(chat_id, question_text, skill_name, skill_detail):
    try:
        skill_prompt = (
            f"技能名：{skill_name}\n"
            f"请把下列技能文档作为本轮回答规则与操作手册，优先遵循并落地执行：\n{skill_detail}"
        )
        answer = _generate_ai_answer(question_text, chat_id=chat_id, extra_system_content=skill_prompt)
        _feishu_append_chat_history(chat_id, "user", question_text or "")
        _feishu_append_chat_history(chat_id, "assistant", answer or "")
        _feishu_send_text_to_chat(chat_id, answer)
    except Exception as e:
        _safe_debug_print(f"异步技能回复失败: {e}")
        try:
            _feishu_send_text_to_chat(chat_id, "我这边处理技能指令时发生异常，请稍后重试。")
        except Exception:
            pass


def _async_generate_and_reply_image(chat_id, question_text, message_id, image_key):
    prompt = (question_text or "").strip()
    if not prompt:
        prompt = "请识别图片里的文字/表格/关键信息，并用中文结构化输出。"
    img, mime = _feishu_download_resource(message_id, image_key, "image")
    if not img:
        _feishu_send_text_to_chat(chat_id, "我这边没能下载到图片内容，可能是权限或接口限制导致。")
        return
    answer = _generate_ai_answer_with_image(prompt, img, mime, chat_id=chat_id)
    _feishu_append_chat_history(chat_id, "user", prompt)
    _feishu_append_chat_history(chat_id, "assistant", answer or "")
    _feishu_send_text_to_chat(chat_id, answer)


def _async_generate_and_reply_file(chat_id, question_text, message_id, file_key, file_name):
    prompt = (question_text or "").strip()
    if not prompt:
        prompt = f"请阅读文档《{file_name or '文件'}》并提炼关键信息，给出结构化总结。"
    blob, mime = _feishu_download_resource(message_id, file_key, "file")
    if not blob:
        _feishu_send_text_to_chat(chat_id, "我这边没能下载到文档内容，可能是权限或接口限制导致。")
        return
    mime_norm = (mime or "").split(";", 1)[0].strip().lower()
    fname = (file_name or "").strip().lower()
    is_image_file = mime_norm.startswith("image/") or any(fname.endswith(s) for s in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"])
    if is_image_file:
        if (question_text or "").strip() == "":
            prompt = "请识别图片里的文字/表格/关键信息，并用中文结构化输出。"
        answer = _generate_ai_answer_with_image(prompt, blob, mime_norm or "image/png", chat_id=chat_id)
        _feishu_append_chat_history(chat_id, "user", prompt)
        _feishu_append_chat_history(chat_id, "assistant", answer or "")
        _feishu_send_text_to_chat(chat_id, answer)
        return
    extracted = kb_service.extract_text_from_bytes(blob, file_name or "")
    if not extracted:
        _feishu_send_text_to_chat(chat_id, "我拿到了文档，但暂时无法解析内容。当前支持 txt/docx/xlsx（pdf需要额外解析能力）。")
        return
    answer = _generate_ai_answer_with_doc(prompt, extracted, doc_name=file_name or "", chat_id=chat_id)
    _feishu_append_chat_history(chat_id, "user", prompt)
    _feishu_append_chat_history(chat_id, "assistant", answer or "")
    _feishu_send_text_to_chat(chat_id, answer)


def _async_generate_and_reply_cloud_doc_qa(chat_id, question_text, doc_url):
    prompt = (question_text or "").strip()
    answer = _generate_ai_answer_with_cloud_doc_url(prompt, doc_url, chat_id=chat_id)
    _feishu_append_chat_history(chat_id, "user", (prompt or "").strip() or f"云文档问答：{doc_url}")
    _feishu_append_chat_history(chat_id, "assistant", answer or "")
    _feishu_send_text_to_chat(chat_id, answer)


def _async_generate_and_reply_bitable(chat_id, question_text, bitable_url):
    prompt = (question_text or "").strip()
    answer = _generate_ai_answer_with_bitable_url(prompt, bitable_url, chat_id=chat_id)
    _feishu_append_chat_history(chat_id, "user", (prompt or "").strip() or f"多维表格问答：{bitable_url}")
    _feishu_append_chat_history(chat_id, "assistant", answer or "")
    _feishu_send_text_to_chat(chat_id, answer)


def _feishu_find_cloud_doc_url(text):
    agent = _get_cloud_documents_agent()
    if agent is None:
        return ""
    urls = agent.extract_urls(text or "")
    for u in urls:
        lu = u.lower()
        if ("feishu" in lu or "larksuite" in lu) and ("/docx/" in lu or "/docs/" in lu or "/wiki/" in lu or "doxcn" in lu):
            return u
    return ""


def _feishu_find_cloud_doc_url_any(text):
    agent = _get_cloud_documents_agent()
    if agent is None:
        return ""
    urls = agent.extract_urls(text or "")
    for u in urls:
        lu = u.lower()
        if ("/docx/" in lu or "/docs/" in lu or "/wiki/" in lu or "doxcn" in lu):
            return u
    return ""


def _feishu_extract_urls_basic(text):
    t = str(text or "")
    urls = re.findall(r"https?://[^\s<>()\"']+", t)
    cleaned = []
    seen = set()
    for u in urls:
        u = u.strip().rstrip(".,;:!?)，。；：！】》）")
        if not u:
            continue
        if u in seen:
            continue
        seen.add(u)
        cleaned.append(u)
    return cleaned


def _feishu_find_bitable_url(text):
    urls = _feishu_extract_urls_basic(text or "")
    for u in urls:
        lu = u.lower()
        if ("feishu" in lu or "larksuite" in lu) and ("/base/" in lu or "bitable" in lu or "bascn" in lu):
            return u
    for u in urls:
        lu = u.lower()
        if "/base/" in lu or "bitable" in lu or "bascn" in lu:
            return u
    return ""


def _parse_bitable_url(url):
    u = str(url or "").strip()
    if not u:
        return "", "", "", "链接为空"
    app_token = ""
    table_id = ""
    view_id = ""

    m = re.search(r"/base/([a-zA-Z0-9]+)", u)
    if m:
        app_token = (m.group(1) or "").strip()
    if not app_token:
        m = re.search(r"(bascn[a-zA-Z0-9]+)", u)
        if m:
            app_token = (m.group(1) or "").strip()

    try:
        parsed = urlparse(u)
        qs = parse_qs(parsed.query or "")
        table_id = str((qs.get("table") or qs.get("table_id") or [""])[0] or "").strip()
        view_id = str((qs.get("view") or qs.get("view_id") or [""])[0] or "").strip()
    except Exception:
        pass

    if not table_id:
        m = re.search(r"(tbl[a-zA-Z0-9]+)", u)
        if m:
            table_id = (m.group(1) or "").strip()

    if not app_token:
        return "", "", "", "未能从链接中解析出多维表格 app_token"
    return app_token, table_id, view_id, ""


def _feishu_bitable_request(method, path, params=None):
    access_token = permission_manager.get_access_token() if hasattr(permission_manager, "get_access_token") else ""
    access_token = str(access_token or "").strip()
    if not access_token:
        return None, "当前无法获取飞书 tenant_access_token，无法拉取多维表格内容。"
    url = f"https://open.feishu.cn/open-apis{path}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        if str(method).upper() == "POST":
            resp = _feishu_http.post(url, headers=headers, json=(params or {}), timeout=20)
        else:
            resp = _feishu_http.get(url, headers=headers, params=(params or {}), timeout=20)
    except Exception as e:
        return None, str(e)
    if resp is None:
        return None, "请求失败"
    if resp.status_code != 200:
        return None, f"{resp.status_code} {str(resp.text or '')[:300]}"
    try:
        data = resp.json()
    except Exception:
        data = None
    if not isinstance(data, dict):
        return None, "接口返回非JSON"
    if int(data.get("code") or 0) != 0:
        return None, f"{data.get('code')} {data.get('msg')}"
    return data.get("data"), ""


def _feishu_bitable_list_tables(app_token):
    data, err = _feishu_bitable_request("GET", f"/bitable/v1/apps/{app_token}/tables", params={"page_size": 100})
    if err:
        return [], err
    items = (data or {}).get("items") or []
    return items if isinstance(items, list) else [], ""


def _feishu_bitable_list_fields(app_token, table_id):
    data, err = _feishu_bitable_request("GET", f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields", params={"page_size": 200})
    if err:
        return [], err
    items = (data or {}).get("items") or []
    return items if isinstance(items, list) else [], ""


def _feishu_bitable_list_records(app_token, table_id, view_id="", max_records=1200):
    items = []
    page_token = ""
    for _ in range(30):
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        if view_id:
            params["view_id"] = view_id
        data, err = _feishu_bitable_request("GET", f"/bitable/v1/apps/{app_token}/tables/{table_id}/records", params=params)
        if err:
            return [], err
        got = (data or {}).get("items") or []
        if isinstance(got, list):
            items.extend(got)
        if max_records and len(items) >= int(max_records):
            items = items[:int(max_records)]
            break
        page_token = str((data or {}).get("page_token") or "").strip()
        if not page_token:
            break
    return items, ""


def _bitable_value_to_text(v):
    if v is None:
        return ""
    if isinstance(v, (str, int, float, bool)):
        return str(v)
    if isinstance(v, list):
        parts = []
        for it in v[:12]:
            if isinstance(it, (str, int, float, bool)):
                parts.append(str(it))
            elif isinstance(it, dict):
                name = str(it.get("name") or it.get("text") or it.get("title") or "").strip()
                url = str(it.get("url") or it.get("link") or "").strip()
                if name and url:
                    parts.append(f"{name}({url})")
                elif name:
                    parts.append(name)
                elif url:
                    parts.append(url)
                else:
                    parts.append(json.dumps(it, ensure_ascii=False))
            else:
                parts.append(str(it))
        return "; ".join([p for p in parts if p])
    if isinstance(v, dict):
        if "text" in v and isinstance(v.get("text"), str):
            return str(v.get("text") or "")
        if "title" in v and isinstance(v.get("title"), str):
            return str(v.get("title") or "")
        if "name" in v and isinstance(v.get("name"), str):
            return str(v.get("name") or "")
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _tokenize_loose(text):
    s = str(text or "").lower()
    s = re.sub(r"\s+", " ", s).strip()
    tokens = []
    for w in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", s):
        w = (w or "").strip()
        if not w:
            continue
        if len(w) == 1 and not w.isdigit():
            continue
        tokens.append(w)
    return tokens


def _build_bitable_context(question, url, app_token, table_id, table_name, view_id, fields, records):
    q_tokens = set(_tokenize_loose(question))
    field_names = []
    field_types = {}
    for f in (fields or []):
        name = str(f.get("field_name") or f.get("name") or "").strip()
        if not name:
            continue
        field_names.append(name)
        if "type" in f:
            try:
                field_types[name] = int(f.get("type"))
            except Exception:
                pass

    rows = []
    for r in (records or []):
        rid = str(r.get("record_id") or r.get("recordId") or "").strip()
        fd = r.get("fields") or {}
        if not isinstance(fd, dict):
            fd = {}
        flat = {}
        row_text_parts = []
        for k in field_names:
            v = _bitable_value_to_text(fd.get(k))
            if v:
                flat[k] = v
                row_text_parts.append(v)
        row_text = " ".join(row_text_parts).lower()
        if q_tokens:
            r_tokens = set(_tokenize_loose(row_text))
            overlap = len(q_tokens & r_tokens)
        else:
            overlap = 0
        rows.append((overlap, rid, flat))

    rows.sort(key=lambda x: x[0], reverse=True)
    top_rows = []
    for overlap, rid, flat in rows:
        if not flat:
            continue
        top_rows.append((overlap, rid, flat))
        if len(top_rows) >= 80:
            break

    header = [
        f"【多维表格链接】{url}",
        f"【App】{app_token}",
        f"【表】{table_name or table_id}",
    ]
    if view_id:
        header.append(f"【视图】{view_id}")
    if field_names:
        header.append("【字段】" + "、".join(field_names[:80]))
    if field_types:
        header.append("【字段类型】" + json.dumps(field_types, ensure_ascii=False))

    body = []
    body.append("【候选记录（按与问题相关性排序）】")
    for i, (overlap, rid, flat) in enumerate(top_rows, start=1):
        body.append(f"{i}. record_id={rid} overlap={overlap}")
        body.append(json.dumps(flat, ensure_ascii=False))

    if not top_rows and records:
        body.append("【候选记录】未筛出高相关记录，但表内有数据。你可以给出更具体的筛选条件（字段名/关键词/日期范围/负责人等）。")
    if not records:
        body.append("【候选记录】表内暂无记录或当前应用无权读取记录。")

    merged = "\n".join(header + [""] + body).strip()
    if len(merged) > 90000:
        merged = merged[:90000].strip()
    return merged


def _generate_ai_answer_with_cloud_doc_url(question_text, doc_url, chat_id=None):
    agent = _get_cloud_documents_agent()
    if agent is None:
        return "云文档模块未加载成功。"
    doc_text, err = agent.fetch_document_text(doc_url, include_images_ocr=True)
    if err:
        return err
    q = (question_text or "").strip()
    if not q:
        q = "请阅读该云文档并回答我的问题。"
    return _generate_ai_answer_with_doc(q, doc_text, doc_name="飞书云文档", chat_id=chat_id)


def _generate_ai_answer_with_bitable_url(question_text, bitable_url, chat_id=None):
    q = (question_text or "").strip()
    if not q:
        q = "请阅读该多维表格并回答我的问题。"
    app_token, table_id, view_id, err = _parse_bitable_url(bitable_url)
    if err:
        return err

    cache_key = f"{bitable_url.strip()}|{q}"
    now_ts = datetime.now().timestamp()
    with _bitable_cache_lock:
        expired = [k for k, v in _bitable_cache.items() if not isinstance(v, dict) or (now_ts - float(v.get('ts') or 0)) > _bitable_cache_ttl_seconds]
        for k in expired:
            _bitable_cache.pop(k, None)
        cached = _bitable_cache.get(cache_key)
        if isinstance(cached, dict) and cached.get("text"):
            return str(cached.get("text") or "")

    tables, terr = _feishu_bitable_list_tables(app_token)
    if terr:
        return f"拉取多维表格失败：{terr}"
    table_name = ""
    if not table_id:
        if tables:
            table_id = str((tables[0] or {}).get("table_id") or "").strip()
            table_name = str((tables[0] or {}).get("name") or "").strip()
    else:
        for t in tables:
            if str((t or {}).get("table_id") or "").strip() == table_id:
                table_name = str((t or {}).get("name") or "").strip()
                break

    if not table_id:
        return "未能解析出表格 table_id，且应用下未列出可用数据表。"

    fields, ferr = _feishu_bitable_list_fields(app_token, table_id)
    if ferr:
        return f"拉取多维表格字段失败：{ferr}"
    records, rerr = _feishu_bitable_list_records(app_token, table_id, view_id=view_id, max_records=1200)
    if rerr:
        return f"拉取多维表格记录失败：{rerr}"

    ctx = _build_bitable_context(q, bitable_url, app_token, table_id, table_name, view_id, fields, records)
    answer = _generate_ai_answer_with_doc(q, ctx, doc_name=f"多维表格:{table_name or table_id}", chat_id=chat_id)
    if answer:
        with _bitable_cache_lock:
            _bitable_cache[cache_key] = {"ts": now_ts, "text": answer}
    return answer


def _feishu_build_cloud_doc_url(doc_type, token):
    t = str(token or "").strip()
    if not t:
        return ""
    typ = str(doc_type or "").strip().lower()
    if typ in {"docx", "docs", "doc", "wiki"}:
        return f"https://www.feishu.cn/{typ}/{t}"
    if typ in {"sheet", "sheets"}:
        return f"https://www.feishu.cn/sheets/{t}"
    if typ in {"bitable", "base"}:
        return f"https://www.feishu.cn/base/{t}"
    if typ in {"mindnote", "mindnotes"}:
        return f"https://www.feishu.cn/mindnotes/{t}"
    if typ in {"slide", "slides"}:
        return f"https://www.feishu.cn/slides/{t}"
    if re.match(r"^doxcn[a-zA-Z0-9]+$", t):
        return f"https://www.feishu.cn/docx/{t}"
    if re.match(r"^doccn[a-zA-Z0-9]+$", t):
        return f"https://www.feishu.cn/doc/{t}"
    if re.match(r"^shtcn[a-zA-Z0-9]+$", t):
        return f"https://www.feishu.cn/sheets/{t}"
    if re.match(r"^(bascn|app)[a-zA-Z0-9]+$", t):
        return f"https://www.feishu.cn/base/{t}"
    if re.match(r"^wiki[a-zA-Z0-9_-]+$", t):
        return f"https://www.feishu.cn/wiki/{t}"
    # 兜底：部分类型token无法识别时，走file路由让飞书侧重定向
    return f"https://www.feishu.cn/file/{t}"


def _feishu_extract_cloud_doc_url_from_event(event_obj):
    token_candidates = []
    type_candidates = []

    def walk(x):
        if x is None:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                lk = str(k or "").strip().lower()
                if lk in {"file_token", "doc_token", "document_token", "obj_token", "wiki_token", "node_token", "token"}:
                    if isinstance(v, str):
                        sv = v.strip()
                        if sv:
                            token_candidates.append(sv)
                if lk in {"file_type", "doc_type", "obj_type"}:
                    if isinstance(v, str):
                        sv = v.strip().lower()
                        if sv:
                            type_candidates.append(sv)
                walk(v)
            return
        if isinstance(x, list):
            for it in x:
                walk(it)
            return
        if isinstance(x, str):
            s = x.strip()
            if not s:
                return
            m = re.search(r"(doxcn[a-zA-Z0-9]+|doccn[a-zA-Z0-9]+)", s)
            if m:
                token_candidates.append((m.group(1) or "").strip())
            return

    walk(event_obj)

    doc_type = ""
    for t in type_candidates:
        if t in {"docx", "docs", "doc", "wiki"}:
            doc_type = t
            break

    token = ""
    for cand in token_candidates:
        if cand.startswith("doxcn"):
            token = cand
            break
    if not token:
        for cand in token_candidates:
            if cand.startswith("doccn"):
                token = cand
                break
    if not token:
        for cand in token_candidates:
            if cand and len(cand) >= 10:
                token = cand
                break

    if token and not doc_type:
        if token.startswith("doxcn"):
            doc_type = "docx"
        elif token.startswith("doccn"):
            doc_type = "doc"

    return _feishu_build_cloud_doc_url(doc_type, token)


def _generate_cloud_doc_scoring(prompt_text, doc_url):
    agent = _get_cloud_documents_agent()
    if agent is None:
        return "", "云文档评分模块未加载成功，请检查服务器文件是否存在：Cloud documents.py"
    prompt_norm = str(prompt_text or "").strip()
    cache_key = f"{str(doc_url or '').strip()}|{prompt_norm}"
    now_ts = datetime.now().timestamp()
    with _cloud_doc_scoring_cache_lock:
        expired = [k for k, v in _cloud_doc_scoring_cache.items() if not isinstance(v, dict) or (now_ts - float(v.get("ts") or 0)) > _cloud_doc_scoring_cache_ttl_seconds]
        for k in expired:
            _cloud_doc_scoring_cache.pop(k, None)
        cached = _cloud_doc_scoring_cache.get(cache_key)
        if isinstance(cached, dict) and cached.get("text"):
            return str(cached.get("text") or "").strip(), ""

    doc_text, err = agent.fetch_document_text(doc_url, include_images_ocr=True)
    if err:
        return "", err
    messages = agent.build_scoring_messages(doc_text, prompt_text or "")
    try:
        scoring_model_candidates = ["Pro/moonshotai/Kimi-K2.6", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B"] + list(_OPENAI_TEXT_MODEL_CANDIDATES or [])
        seen = set()
        scoring_model_candidates = [m for m in scoring_model_candidates if m and not (m in seen or seen.add(m))]
        content = _ai_chat_complete(
            messages,
            max_tokens=1500,
            temperature=0.2,
            model_candidates=scoring_model_candidates
        )
    except Exception:
        return "", "我这边生成评分报告失败了，请稍后再试。"
    text = (content or "").strip()
    if text:
        with _cloud_doc_scoring_cache_lock:
            _cloud_doc_scoring_cache[cache_key] = {"ts": now_ts, "text": text}
    return text, ""


def _feishu_plain_textify(text):
    t = (text or "")
    if not t:
        return ""
    t = str(t).replace("\r\n", "\n").replace("\r", "\n")
    out_lines = []
    in_code_block = False
    for raw_line in t.split("\n"):
        line = raw_line
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            line = re.sub(r"^\s*#{1,6}\s*", "", line)
            line = line.replace("**", "").replace("__", "").replace("`", "")
            line = re.sub(r"^\s*[\*\-]\s+", "• ", line)
            line = re.sub(r"^\s*\*\s*", "• ", line)
        out_lines.append(line)
    out = "\n".join(out_lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def _generate_cloud_doc_analysis(prompt_text, doc_url, chat_id=None):
    q = (prompt_text or "").strip()
    if not q:
        q = (
            "请阅读这份周报/月报，只输出“总结+建议”，不需要评分/打分/等级。\n"
            "输出要求：纯文本，不要使用Markdown格式，不要出现#或*等标记符号。\n"
            "输出结构：\n"
            "一、要点总结（目标-产出-数据-问题-计划）\n"
            "二、改进建议（给具体写法）\n"
            "三、下一步行动清单（按优先级排序）"
        )
    else:
        q = (
            "请阅读这份周报/月报，只输出“总结+建议”，不需要评分/打分/等级。\n"
            "输出要求：纯文本，不要使用Markdown格式，不要出现#或*等标记符号。\n"
            "输出结构：\n"
            "一、要点总结（目标-产出-数据-问题-计划）\n"
            "二、改进建议（给具体写法）\n"
            "三、下一步行动清单（按优先级排序）\n\n"
            f"【用户补充问题】\n{q}"
        )
    return _generate_ai_answer_with_cloud_doc_url(q, doc_url, chat_id=chat_id)


def _async_generate_and_reply_cloud_doc(chat_id, prompt_text, doc_url):
    content = _generate_cloud_doc_analysis(prompt_text, doc_url, chat_id=chat_id)
    content = _feishu_plain_textify(content)
    _feishu_append_chat_history(chat_id, "user", (prompt_text or "").strip() or f"周报/月报分析：{doc_url}")
    _feishu_append_chat_history(chat_id, "assistant", content or "")
    _feishu_send_text_to_chat(chat_id, content or "我这边没有生成出有效的分析结果，请稍后再试。")

    forward_deps = _parse_forward_departments(prompt_text)
    if forward_deps and content:
        header = f"周报/月报总结与建议（自动生成）\n来源：{doc_url}\n\n"
        msg = (header + content).strip()
        stats = _forward_text_to_departments(forward_deps, msg)
        ok_total = int(stats.get("success") or 0)
        fail_total = int(stats.get("failed") or 0)
        _feishu_send_text_to_chat(chat_id, f"已同步给：{'、'.join(forward_deps)}（成功{ok_total}，失败{fail_total}）")


def _extract_first_feishu_user_id(obj):
    if obj is None:
        return ""

    if isinstance(obj, str):
        s = obj.strip()
        return s if s.startswith("ou_") else ""

    if isinstance(obj, list):
        for it in obj:
            hit = _extract_first_feishu_user_id(it)
            if hit:
                return hit
        return ""

    if isinstance(obj, dict):
        priority_keys = [
            "operator_id", "operator", "sender", "user", "user_id", "open_id",
            "create_user", "creator", "commenter", "comment", "data"
        ]
        for k in priority_keys:
            if k in obj:
                hit = _extract_first_feishu_user_id(obj.get(k))
                if hit:
                    return hit

        for v in obj.values():
            hit = _extract_first_feishu_user_id(v)
            if hit:
                return hit
        return ""

    return ""


def _extract_all_text(obj, max_chars=20000):
    out = []
    seen = set()

    def walk(x):
        if x is None:
            return
        if isinstance(x, str):
            s = x.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
            return
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
            return
        if isinstance(x, list):
            for it in x:
                walk(it)
            return

    walk(obj)
    merged = "\n".join(out)
    if len(merged) > max_chars:
        merged = merged[:max_chars]
    return merged


def _event_mentions_bot(event_obj):
    try:
        text = _extract_all_text(event_obj, max_chars=12000)
        if (f"@{FEISHU_BOT_NAME}") in text or FEISHU_BOT_NAME in text:
            return True
    except Exception:
        return False
    return False


def _handle_feishu_cloud_doc_mention_event(data):
    event = (data or {}).get("event") or {}
    event_id = (
        ((data or {}).get("header") or {}).get("event_id")
        or ((data or {}).get("event") or {}).get("event_id")
        or (event.get("event_id") if isinstance(event, dict) else "")
    )
    if _feishu_is_event_processed(event_id):
        return jsonify({"msg": "ok"}), 200
    _feishu_mark_event_processed(event_id)
    user_id = _extract_first_feishu_user_id(event)
    prompt_text = _extract_all_text(event, max_chars=20000)
    agent = _get_cloud_documents_agent()
    doc_url = _feishu_find_cloud_doc_url_any(prompt_text)
    bitable_url = _feishu_find_bitable_url(prompt_text)
    if not doc_url:
        doc_url = _feishu_extract_cloud_doc_url_from_event(event)
    if not doc_url and agent is not None:
        m = re.search(r"(doxcn[a-zA-Z0-9]+|doccn[a-zA-Z0-9]+)", prompt_text)
        if m:
            token = (m.group(1) or "").strip()
            if token:
                doc_url = _feishu_build_cloud_doc_url("", token)

    if not doc_url and not bitable_url:
        if user_id:
            _feishu_send_text(user_id, "open_id", "我收到了@，但没有找到云文档/多维表格链接。请在评论里贴上飞书云文档链接（/docx/xxxx）或多维表格链接（/base/xxxx）。")
        return jsonify({"msg": "ok"}), 200

    if user_id:
        _feishu_send_text(user_id, "open_id", "收到，我在读取链接内容并生成回答，完成后会发给你。")

    def run():
        if bitable_url and not doc_url:
            content = _generate_ai_answer_with_bitable_url(prompt_text, bitable_url, chat_id=None)
            if user_id and content:
                for chunk in _split_text(content, max_len=1500):
                    _feishu_send_text(user_id, "open_id", chunk)
            return

        kw = (prompt_text or "").strip()
        if (not kw) or any(k in kw for k in ["周报", "月报", "评分", "打分", "评估", "点评", "改进", "复盘"]):
            content = _generate_cloud_doc_analysis(prompt_text, doc_url, chat_id=None)
        else:
            content = _generate_ai_answer_with_cloud_doc_url(prompt_text, doc_url, chat_id=None)

        if user_id and content:
            for chunk in _split_text(content, max_len=1500):
                _feishu_send_text(user_id, "open_id", chunk)

    executor.submit(run)
    return jsonify({"msg": "ok"}), 200


def handle_feishu_message_event(data):
    event = data.get("event") or {}
    if not isinstance(event, dict):
        event = {}
    message = event.get("message") or {}
    if not isinstance(message, dict):
        message = {}
    sender = event.get("sender") or {}
    if not isinstance(sender, dict):
        sender = {}
    sender_type = str(sender.get("sender_type") or "").lower()

    message_id = message.get("message_id")
    if _feishu_is_message_processed(message_id):
        return jsonify({"msg": "ok"}), 200
    _feishu_mark_message_processed(message_id)

    if sender_type and sender_type != "user":
        return jsonify({"msg": "ok"}), 200

    chat_id = message.get("chat_id")
    chat_type = message.get("chat_type")
    if not chat_id:
        return jsonify({"msg": "ok"}), 200

    msg_type = str(message.get("message_type") or message.get("msg_type") or "").lower().strip()
    content_obj = _feishu_parse_message_content(message.get("content"))
    if not msg_type:
        msg_type = str(content_obj.get("msg_type") or content_obj.get("message_type") or "").lower().strip()

    text = _feishu_extract_text_from_content(message.get("content"))
    mentions = message.get("mentions") or []

    try:
        _feishu_recent_events.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "stage": "received_message_event",
            "event_type": event.get("type"),
            "message_id": message_id,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "sender_type": sender_type,
            "msg_type": msg_type,
            "text": text,
            "mentions": mentions,
        })
        if len(_feishu_recent_events) > _feishu_recent_events_limit:
            del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
    except Exception:
        pass

    bot_mentioned = _feishu_is_bot_mentioned(text, mentions)
    if _feishu_is_group_message(chat_type):
        last_bot_ts = _feishu_get_last_bot_ts(chat_id)
        should_respond = bot_mentioned or ((datetime.now().timestamp() - float(last_bot_ts or 0.0)) <= 900)
    elif _feishu_is_p2p_message(chat_type):
        should_respond = True
    else:
        should_respond = bot_mentioned

    user_text_for_memory = str(text or "").strip()
    if msg_type == "post":
        post_image_keys = _feishu_extract_image_keys(content_obj, limit=1)
        if post_image_keys:
            _feishu_remember_image_resource(chat_id, post_image_keys[0], message_id=message_id, resource_type="image")
            if not user_text_for_memory:
                user_text_for_memory = "【图片】"
    elif msg_type == "image":
        image_key = str(content_obj.get("image_key") or content_obj.get("imageKey") or "").strip()
        if image_key:
            _feishu_remember_image_resource(chat_id, image_key, message_id=message_id, resource_type="image")
            if not user_text_for_memory:
                user_text_for_memory = "【图片】"
    elif msg_type == "file":
        file_key = str(content_obj.get("file_key") or content_obj.get("fileKey") or "").strip()
        file_name = str(content_obj.get("file_name") or content_obj.get("fileName") or "").strip()
        ln = file_name.lower().strip()
        if file_key and any(ln.endswith(s) for s in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"]):
            _feishu_remember_image_resource(chat_id, file_key, message_id=message_id, resource_type="file", file_name=file_name)
            if not user_text_for_memory:
                user_text_for_memory = f"【图片】{file_name}".strip()

    if user_text_for_memory:
        _feishu_append_chat_history(chat_id, "user", user_text_for_memory)
        _feishu_remember_resources(chat_id, user_text_for_memory)

    if not should_respond:
        return jsonify({"msg": "ok"}), 200

    question = _feishu_clean_question(user_text_for_memory)
    if question in {"清空记忆", "重置记忆", "/reset", "reset"}:
        _feishu_clear_chat_history(chat_id)
        _feishu_send_text_to_chat(chat_id, "已清空本会话的上下文记忆。")
        return jsonify({"msg": "ok"}), 200
    skill_cmd = _feishu_parse_skill_invocation(question)
    if skill_cmd.get("mode") == "list":
        _feishu_send_text_to_chat(chat_id, _feishu_render_skill_list())
        return jsonify({"msg": "ok"}), 200
    if skill_cmd.get("mode") == "invoke":
        sk_name = str(skill_cmd.get("skill") or "").strip()
        sk = _feishu_get_skill(sk_name)
        if not sk:
            _feishu_send_text_to_chat(chat_id, f"未找到技能：{sk_name}\n你可以先发送 /skills 查看可用技能。")
            return jsonify({"msg": "ok"}), 200
        skill_question = str(skill_cmd.get("question") or "").strip()
        if not skill_question:
            _feishu_send_text_to_chat(chat_id, f"技能 {sk_name} 已识别。请按格式提问：/skill {sk_name} 你的问题")
            return jsonify({"msg": "ok"}), 200
        _feishu_send_text_to_chat(chat_id, f"收到，已启用技能 {sk_name}，正在处理你的问题…")
        _feishu_submit_task(
            _async_generate_and_reply_with_skill,
            chat_id,
            skill_question,
            str(sk.get("name") or sk_name),
            str(sk.get("detail") or sk.get("description") or "")
        )
        return jsonify({"msg": "ok"}), 200

    ref_ids = _feishu_extract_reference_message_ids(message, content_obj)
    ref_texts = []
    for rid in ref_ids:
        if rid and rid != message_id:
            rt = _feishu_get_message_text(rid)
            rt = str(rt or "").strip()
            if rt:
                ref_texts.append(rt)
        if len(ref_texts) >= 3:
            break

    combined_text = "\n".join([str(user_text_for_memory or "").strip()] + ref_texts).strip()
    if combined_text:
        _feishu_remember_resources(chat_id, combined_text)

    bitable_url = _feishu_find_bitable_url(combined_text) or _feishu_find_bitable_url(question)
    if bitable_url:
        _feishu_send_text_to_chat(chat_id, "收到，我在读取多维表格并回答你的问题…")
        _feishu_submit_task(_async_generate_and_reply_bitable, chat_id, question, bitable_url)
        return jsonify({"msg": "ok"}), 200
    cloud_doc_url = _feishu_find_cloud_doc_url(combined_text) or _feishu_find_cloud_doc_url(question)
    if cloud_doc_url:
        kw = (question or "").strip()
        if (not kw) or any(k in kw for k in ["周报", "月报", "评分", "打分", "评估", "点评", "改进", "复盘"]):
            _feishu_send_text_to_chat(chat_id, "收到，我在读取云文档并总结+给建议…")
            _feishu_submit_task(_async_generate_and_reply_cloud_doc, chat_id, question, cloud_doc_url)
            return jsonify({"msg": "ok"}), 200
        _feishu_send_text_to_chat(chat_id, "收到，我在读取云文档并回答你的问题…")
        _feishu_submit_task(_async_generate_and_reply_cloud_doc_qa, chat_id, question, cloud_doc_url)
        return jsonify({"msg": "ok"}), 200

    prefer_type = ""
    kw = (question or "").strip()
    if any(k in kw for k in ["多维", "表格", "字段", "列", "行", "记录", "筛选", "视图", "base", "bitable"]):
        prefer_type = "bitable"
    elif any(k in kw for k in ["云文档", "文档", "周报", "月报", "wiki", "docx", "docs"]):
        prefer_type = "cloud_doc"
    elif any(k in kw for k in ["图片", "截图", "照片", "图里", "图中", "复述", "识别", "ocr"]):
        prefer_type = "image"

    last_resource = _feishu_get_last_resource(chat_id, prefer_type=prefer_type)
    if isinstance(last_resource, dict) and last_resource.get("url") and last_resource.get("type"):
        if last_resource.get("type") == "bitable":
            _feishu_send_text_to_chat(chat_id, "收到，我在读取你前面发过的多维表格并回答你的问题…")
            _feishu_submit_task(_async_generate_and_reply_bitable, chat_id, question, str(last_resource.get("url") or ""))
            return jsonify({"msg": "ok"}), 200
        if last_resource.get("type") == "cloud_doc":
            url = str(last_resource.get("url") or "")
            if (not kw) or any(k in kw for k in ["周报", "月报", "评分", "打分", "评估", "点评", "改进", "复盘"]):
                _feishu_send_text_to_chat(chat_id, "收到，我在读取你前面发过的云文档并总结+给建议…")
                _feishu_submit_task(_async_generate_and_reply_cloud_doc, chat_id, question, url)
                return jsonify({"msg": "ok"}), 200
            _feishu_send_text_to_chat(chat_id, "收到，我在读取你前面发过的云文档并回答你的问题…")
            _feishu_submit_task(_async_generate_and_reply_cloud_doc_qa, chat_id, question, url)
            return jsonify({"msg": "ok"}), 200
        if last_resource.get("type") == "image":
            key = str(last_resource.get("url") or "").strip()
            rt = str(last_resource.get("resource_type") or "image").strip().lower()
            mid = str(last_resource.get("message_id") or "").strip()
            fn = str(last_resource.get("file_name") or "").strip()
            if rt == "file":
                _feishu_send_text_to_chat(chat_id, "收到，我在识别你前面发过的图片…")
                _feishu_submit_task(_async_generate_and_reply_file, chat_id, question, mid, key, fn)
                return jsonify({"msg": "ok"}), 200
            _feishu_send_text_to_chat(chat_id, "收到，我在识别你前面发过的图片…")
            _feishu_submit_task(_async_generate_and_reply_image, chat_id, question, mid, key)
            return jsonify({"msg": "ok"}), 200
    if msg_type == "image":
        image_key = str(content_obj.get("image_key") or content_obj.get("imageKey") or "").strip()
        _feishu_send_text_to_chat(chat_id, "收到，我在识别图片…")
        _feishu_submit_task(_async_generate_and_reply_image, chat_id, question, message_id, image_key)
    elif msg_type == "file":
        file_key = str(content_obj.get("file_key") or content_obj.get("fileKey") or "").strip()
        file_name = str(content_obj.get("file_name") or content_obj.get("fileName") or "").strip()
        _feishu_send_text_to_chat(chat_id, "收到，我在读取文档…")
        _feishu_submit_task(_async_generate_and_reply_file, chat_id, question, message_id, file_key, file_name)
    else:
        _feishu_send_text_to_chat(chat_id, "收到，我在思考中…")
        _feishu_submit_task(_async_generate_and_reply, chat_id, question)
    return jsonify({"msg": "ok"}), 200


def _feishu_try_decrypt_callback_data(data):
    if not isinstance(data, dict):
        return data
    if data.get("event") or data.get("type"):
        return data
    encrypted = data.get("encrypt")
    if not encrypted:
        return data
    try:
        decrypted_text = permission_manager.decrypt_feishu_data(encrypted)
        if isinstance(decrypted_text, str):
            decrypted_obj = json.loads(decrypted_text)
            if isinstance(decrypted_obj, dict):
                return decrypted_obj
        return data
    except Exception as e:
        _safe_debug_print(f"❌ 飞书回调解密失败: {e}")
        return data


@app.route('/')
def index():
    """主页 - 默认跳转到主控制台"""
    force_desktop = str(request.args.get('desktop') or '').strip() in {'1', 'true', 'yes'}
    if (not force_desktop) and _is_mobile_request():
        return redirect(url_for('dashboard_mobile'))
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    """主控制台"""
    dashboard_started_at = time.perf_counter()
    force_desktop = str(request.args.get('desktop') or '').strip() in {'1', 'true', 'yes'}
    if (not force_desktop) and _is_mobile_request():
        _debug_log_elapsed("dashboard_redirect_mobile", dashboard_started_at, path=request.path)
        return redirect(url_for('dashboard_mobile'))
    _safe_debug_print(f"\n=== Dashboard路由处理 ===")

    # 首先尝试从飞书上下文获取用户信息（免登录）
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    user_department = session.get('user_department')
    login_time = session.get('login_time')

    _safe_debug_print(f"👤 用户ID: {user_id}")
    _safe_debug_print(f"📛 用户名: {user_name}")
    _safe_debug_print(f"🏢 用户部门: {user_department}")
    _safe_debug_print(f"⏰ 登录时间: {login_time}")
    _safe_debug_print(f"🔑 Session Keys: {list(session.keys())}")

    # 如果session中没有用户信息，尝试从飞书上下文获取
    if not user_id:
        _safe_debug_print(f"🔍 Session中无用户信息，开始获取...")
        # 检查是否为本地开发环境
        is_local_dev = request.host.startswith('127.0.0.1') or request.host.startswith('localhost')

        if is_local_dev:
            _safe_debug_print(f"🔧 本地开发环境，跳转到开发者登录")
            # 本地开发环境，跳转到开发者登录
            return redirect(url_for('dev_login', user_type='bd'))

        # 统一通过当前应用获取用户信息
        dashboard_identity_started_at = time.perf_counter()
        user_info = _sync_feishu_identity_via_current_app(force_refresh=True)
        _debug_log_elapsed(
            "dashboard_identity_sync",
            dashboard_identity_started_at,
            ok=bool(user_info),
            path=request.path
        )

        if user_info:
            user_id = str(session.get('feishu_user_id') or user_info.get('user_id') or '').strip()
            user_name = str(session.get('feishu_user_name') or _resolve_feishu_user_name(user_info, fallback='飞书用户')).strip()
            _safe_debug_print(f"✅ Dashboard飞书识别成功 - 用户: {user_id}")

    _safe_debug_print(f"🔍 Dashboard访问 - 用户ID: {user_id}, 用户名: {user_name}")

    # 如果用户已登录，获取其可访问的功能
    accessible_functions = []
    if user_id:
        # 检查是否有预加载的数据
        preloaded_functions = session.get('preloaded_functions')
        preload_time_str = session.get('preload_time')

        # 检查预加载数据是否有效（5分钟内）
        use_preloaded = False
        if preloaded_functions and preload_time_str:
            try:
                preload_time = datetime.fromisoformat(preload_time_str)
                time_diff = (datetime.now() - preload_time).total_seconds()
                if time_diff < 300:  # 5分钟内有效
                    use_preloaded = True
                    _safe_debug_print(f"🚀 使用预加载数据，预加载时间: {time_diff:.1f}秒前")
            except Exception as e:
                _safe_debug_print(f"⚠️ 预加载时间解析失败: {e}")

        if use_preloaded:
            accessible_functions = preloaded_functions
            _safe_debug_print(f"✅ 使用预加载权限数据，可访问功能数量: {len(accessible_functions)}")
            if len(accessible_functions) <= 1:
                _safe_debug_print("🔄 预加载功能数量过少，尝试重新获取用户可访问功能...")
                try:
                    permissions_started_at = time.perf_counter()
                    accessible_functions = permission_manager.get_user_accessible_functions(user_id)
                    _debug_log_elapsed(
                        "dashboard_permissions_reload",
                        permissions_started_at,
                        user_id=user_id,
                        function_count=len(accessible_functions or [])
                    )
                    _safe_debug_print(f"✅ 重新获取用户权限成功，可访问功能数量: {len(accessible_functions)}")
                    session.pop('preloaded_functions', None)
                    session.pop('preload_time', None)
                except Exception as e:
                    _debug_log_elapsed("dashboard_permissions_reload_failed", permissions_started_at, user_id=user_id, error=str(e))
                    _safe_debug_print(f"❌ 重新获取用户权限失败: {e}")
        else:
            _safe_debug_print(f"🔍 预加载数据无效或过期，重新获取用户可访问功能...")
            try:
                permissions_started_at = time.perf_counter()
                accessible_functions = permission_manager.get_user_accessible_functions(user_id)
                _debug_log_elapsed(
                    "dashboard_permissions_load",
                    permissions_started_at,
                    user_id=user_id,
                    function_count=len(accessible_functions or [])
                )
                _safe_debug_print(f"✅ 成功获取用户权限，可访问功能数量: {len(accessible_functions)}")
                # 更新预加载数据
                session.pop('preloaded_functions', None)
                session.pop('preload_time', None)
                for func in accessible_functions:
                    _safe_debug_print(f"   - {func.get('function_name')}: {func.get('name')} ({func.get('reason')})")
            except Exception as e:
                _debug_log_elapsed("dashboard_permissions_load_failed", permissions_started_at, user_id=user_id, error=str(e))
                _safe_debug_print(f"❌ 获取用户权限失败: {e}")
                import traceback
                traceback.print_exc()
    else:
        # 如果仍然无法获取用户信息，跳转到飞书授权
        _safe_debug_print("🔄 Dashboard未检测到用户信息，跳转到授权页面")
        return redirect(url_for('feishu_auth'))

    _safe_debug_print(f"🎨 渲染dashboard模板...")
    _debug_log_elapsed(
        "dashboard_ready_to_render",
        dashboard_started_at,
        user_id=str(user_id or '').strip(),
        function_count=len(accessible_functions or []),
        used_preloaded=bool(use_preloaded) if user_id else False
    )
    _safe_debug_print("========================\n")

    accessible_functions = _normalize_dashboard_functions(accessible_functions)

    return render_template('dashboard.html',
                           user_name=user_name,
                           user_id=user_id,
                           user_department=user_department,
                           accessible_functions=accessible_functions,
                           permission_debug_departments=session.get('permission_debug_departments') or [],
                           permission_debug_user_name=str(session.get('permission_debug_user_name') or '').strip())


@app.route('/dashboard/mobile')
def dashboard_mobile():
    """主控制台移动端页面"""
    dashboard_mobile_started_at = time.perf_counter()
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    user_department = session.get('user_department')

    if not user_id:
        is_local_dev = request.host.startswith('127.0.0.1') or request.host.startswith('localhost')
        if is_local_dev:
            _debug_log_elapsed("dashboard_mobile_redirect_dev_login", dashboard_mobile_started_at, path=request.path)
            return redirect(url_for('dev_login', user_type='bd'))
        dashboard_mobile_identity_started_at = time.perf_counter()
        user_info = _sync_feishu_identity_via_current_app(force_refresh=True)
        _debug_log_elapsed(
            "dashboard_mobile_identity_sync",
            dashboard_mobile_identity_started_at,
            ok=bool(user_info),
            path=request.path
        )
        if user_info:
            user_id = str(session.get('feishu_user_id') or user_info.get('user_id') or '').strip()
            user_name = str(session.get('feishu_user_name') or _resolve_feishu_user_name(user_info, fallback='飞书用户')).strip()

    if not user_id:
        _debug_log_elapsed("dashboard_mobile_redirect_auth", dashboard_mobile_started_at, path=request.path)
        return redirect(url_for('feishu_auth'))

    try:
        dashboard_mobile_permissions_started_at = time.perf_counter()
        accessible_functions = permission_manager.get_user_accessible_functions(user_id)
        _debug_log_elapsed(
            "dashboard_mobile_permissions_load",
            dashboard_mobile_permissions_started_at,
            user_id=str(user_id or '').strip(),
            function_count=len(accessible_functions or [])
        )
    except Exception:
        _debug_log_elapsed(
            "dashboard_mobile_permissions_load_failed",
            dashboard_mobile_permissions_started_at,
            user_id=str(user_id or '').strip()
        )
        accessible_functions = []

    cards = _build_mobile_function_cards(accessible_functions)
    _debug_log_elapsed(
        "dashboard_mobile_ready_to_render",
        dashboard_mobile_started_at,
        user_id=str(user_id or '').strip(),
        function_count=len(accessible_functions or []),
        card_count=len(cards or [])
    )
    return render_template(
        'dashboard_mobile.html',
        user_name=user_name,
        user_id=user_id,
        user_department=user_department,
        mobile_cards=cards,
        permission_debug_departments=session.get('permission_debug_departments') or [],
        permission_debug_user_name=str(session.get('permission_debug_user_name') or '').strip()
    )


@app.route('/dashboard/xiaotu')
@require_permission('xiaotu_qa')
def dashboard_xiaotu():
    user_id = session.get('feishu_user_id')
    if not user_id:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu')
        return redirect(url_for('feishu_auth'))
    user_access_token = str(session.get('feishu_user_access_token') or '').strip()
    if not user_access_token:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu')
        return redirect(url_for('feishu_auth'))
    user_name = session.get('feishu_user_name', '用户')
    return render_template('xiaotu_dashboard.html', user_name=user_name)


@app.route('/dashboard/xiaotu-report-center')
@require_permission('xiaotu_qa')
def dashboard_xiaotu_report_center():
    user_id = session.get('feishu_user_id')
    if not user_id:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center')
        return redirect(url_for('feishu_auth'))
    user_access_token = str(session.get('feishu_user_access_token') or '').strip()
    if not user_access_token:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center')
        return redirect(url_for('feishu_auth'))
    user_name = session.get('feishu_user_name', '用户')
    if _is_mobile_request() and str(request.args.get('desktop') or '').strip() != '1':
        return redirect(url_for('dashboard_xiaotu_report_center_mobile'))
    return render_template(
        'xiaotu_report_center.html',
        user_name=user_name,
        edit_wendangid=str(request.args.get('edit_wendangid') or '').strip(),
    )


@app.route('/dashboard/xiaotu-report-center-mobile')
@require_permission('xiaotu_qa')
def dashboard_xiaotu_report_center_mobile():
    user_id = session.get('feishu_user_id')
    if not user_id:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center_mobile')
        return redirect(url_for('feishu_auth'))
    user_access_token = str(session.get('feishu_user_access_token') or '').strip()
    if not user_access_token:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center_mobile')
        return redirect(url_for('feishu_auth'))
    user_name = session.get('feishu_user_name', '用户')
    return render_template(
        'xiaotu_report_center_mobile.html',
        user_name=user_name,
        edit_wendangid=str(request.args.get('edit_wendangid') or '').strip(),
    )


@app.route('/dashboard/xiaotu-report-history')
@require_permission('xiaotu_qa')
def dashboard_xiaotu_report_history():
    user_id = session.get('feishu_user_id')
    if not user_id:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_history')
        return redirect(url_for('feishu_auth'))
    user_access_token = str(session.get('feishu_user_access_token') or '').strip()
    if not user_access_token:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_history')
        return redirect(url_for('feishu_auth'))
    user_name = str(session.get('feishu_user_name') or '用户').strip()
    history_debug_options = _xiaotu_get_report_history_debug_options(user_name)
    history_scope = _xiaotu_get_report_history_scope(user_name)
    history_analysis_scope = _xiaotu_get_history_analysis_visible_user_names(user_id, user_name)
    can_view_all_uploads = bool(history_scope.get('can_view_all_uploads'))
    restricted_to_allowed_departments = bool(history_scope.get('restricted_to_allowed_departments'))
    return render_template(
        'xiaotu_report_history.html',
        user_name=user_name,
        history_filter_name=('' if (can_view_all_uploads or restricted_to_allowed_departments) else user_name),
        history_can_view_all_uploads=can_view_all_uploads,
        history_restricted_to_allowed_departments=restricted_to_allowed_departments,
        history_allowed_department_names=list(history_scope.get('allowed_department_names') or []),
        history_analysis_is_department_leader=bool(history_analysis_scope.get('is_department_leader')),
        history_analysis_department_names=list(history_analysis_scope.get('department_names') or []),
        history_debug_enabled=bool(history_debug_options),
        history_debug_options=history_debug_options,
        history_debug_default_mode='current',
    )


@app.route('/xiaotu/report_comment', methods=['GET', 'POST'])
def xiaotu_report_comment_page():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth', next=request.full_path))
    wendangid = str(request.values.get('wendangid') or '').strip()
    if not wendangid:
        return "缺少文档ID", 400
    esc_wid = _xiaotu_sql_escape(wendangid)
    row = sf_db(f"SELECT TOP 1 WenDangID, BiaoTi, XingMing, RiQi FROM baogao WHERE WenDangID='{esc_wid}'") or []
    if isinstance(row, list) and row:
        row = row[0]
    report = {
        'wendangid': wendangid,
        'biaoti': '',
        'xingming': '',
        'riqi': ''
    }
    if isinstance(row, dict):
        report.update({
            'wendangid': str(row.get('WenDangID') or wendangid).strip(),
            'biaoti': str(row.get('BiaoTi') or '').strip(),
            'xingming': str(row.get('XingMing') or '').strip(),
            'riqi': str(row.get('RiQi') or '').strip(),
        })
    elif isinstance(row, (list, tuple)):
        report.update({
            'wendangid': str(row[0] if len(row) > 0 else wendangid).strip(),
            'biaoti': str(row[1] if len(row) > 1 else '').strip(),
            'xingming': str(row[2] if len(row) > 2 else '').strip(),
            'riqi': str(row[3] if len(row) > 3 else '').strip(),
        })
    error = ""
    success = bool(str(request.args.get('ok') or '').strip())
    if request.method == 'POST':
        action_name = str(request.form.get('action') or 'comment').strip().lower()
        actor_name = str(session.get('feishu_user_name') or '匿名用户').strip()
        if action_name == 'reply':
            reply_text = str(request.form.get('reply') or '').strip()
            reply_target = str(request.form.get('reply_target') or '').strip()
            ok, err = _xiaotu_append_report_reply(
                report.get('wendangid'),
                actor_name,
                reply_text,
                reply_target
            )
        else:
            comment_text = str(request.form.get('comment') or '').strip()
            ok, err = _xiaotu_append_report_comment(
                report.get('wendangid'),
                actor_name,
                comment_text
            )
        if ok:
            return redirect(url_for('xiaotu_report_comment_page', wendangid=report.get('wendangid'), ok=action_name))
        error = err or ('回复保存失败' if action_name == 'reply' else '评论保存失败')
        success = False
    success_text = ''
    if success:
        ok_type = str(request.args.get('ok') or '').strip().lower()
        success_text = '回复已提交成功。' if ok_type == 'reply' else '评论已提交成功。'
    return render_template(
        'xiaotu_report_comment.html',
        report=report,
        feedback=_xiaotu_get_report_feedback(report.get('wendangid'), owner_name=report.get('xingming')),
        error=error,
        success=success,
        success_text=success_text
    )


@app.route('/api/xiaotu/report_delivery_status', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_delivery_status():
    try:
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        wendangid = str(request.args.get('wendangid') or '').strip()
        if not wendangid:
            return jsonify({'success': False, 'message': '缺少日报ID'}), 400
        row = _xiaotu_get_report_row(wendangid)
        if not row:
            return jsonify({'success': False, 'message': '未找到对应日报'}), 404
        session_user_name = str(session.get('feishu_user_name') or '').strip()
        status = _xiaotu_get_report_delivery_status(wendangid, row)
        return jsonify({
            'success': True,
            'data': {
                'wendangid': wendangid,
                'status': status,
                'editable_by_current_user': bool(session_user_name and session_user_name == str(row.get('xingming') or '').strip()),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取投递状态失败: {str(e)}'}), 500


@app.route('/api/xiaotu/report_prepare_edit', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_prepare_edit():
    try:
        data = request.get_json(silent=True) or {}
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        session_user_name = str(session.get('feishu_user_name') or '').strip()
        wendangid = str(data.get('wendangid') or '').strip()
        if not wendangid:
            return jsonify({'success': False, 'message': '缺少日报ID'}), 400
        row = _xiaotu_get_report_row(wendangid)
        if not row:
            return jsonify({'success': False, 'message': '未找到对应日报'}), 404
        if session_user_name != str(row.get('xingming') or '').strip():
            return jsonify({'success': False, 'message': '只能撤回并修改自己提报的日报'}), 403
        status = _xiaotu_get_report_delivery_status(wendangid, row)
        if not bool(status.get('can_recall_edit')):
            return jsonify({
                'success': False,
                'message': f"当前不满足撤回修改条件：{str(status.get('status_text') or '存在已读对象')}",
                'data': {'status': status}
            }), 400
        # Only recall the latest visible card per receiver.
        # Historical message_ids are retained for compatibility and may already be invalid.
        recall_entries = _xiaotu_collect_report_card_message_entries(wendangid, latest_only=True)
        failures = []
        for entry in recall_entries:
            ok, err, _ = _feishu_recall_message(entry.get('message_id'))
            if not ok:
                failures.append({
                    'receive_id': str(entry.get('receive_id') or '').strip(),
                    'message_id': str(entry.get('message_id') or '').strip(),
                    'error': str(err or '').strip(),
                })
        if failures:
            return jsonify({
                'success': False,
                'message': '撤回原卡片失败，请稍后重试',
                'data': {
                    'status': status,
                    'failures': failures,
                }
            }), 500
        _xiaotu_forget_report_card_messages(wendangid)
        _xiaotu_set_report_edit_ready_session(
            wendangid,
            status.get('notify_open_ids') or [],
            status.get('notify_targets') or [],
        )
        if _is_mobile_request():
            edit_redirect_url = url_for(
                'dashboard_xiaotu_report_center_mobile',
                edit_wendangid=wendangid,
            )
        else:
            edit_redirect_url = url_for(
                'dashboard_xiaotu_report_center',
                edit_wendangid=wendangid,
                desktop=1,
            )
        return jsonify({
            'success': True,
            'message': '已撤回原卡片，请开始修改',
            'data': {
                'wendangid': wendangid,
                'status': status,
                'redirect_url': edit_redirect_url,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'撤回并进入修改失败: {str(e)}'}), 500


@app.route('/api/xiaotu/report_edit_payload', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_edit_payload():
    try:
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        session_user_name = str(session.get('feishu_user_name') or '').strip()
        wendangid = str(request.args.get('wendangid') or '').strip()
        if not wendangid:
            return jsonify({'success': False, 'message': '缺少日报ID'}), 400
        edit_ready = _xiaotu_get_report_edit_ready_session(wendangid)
        if not edit_ready:
            return jsonify({'success': False, 'message': '当前日报未进入可编辑状态，请先从历史页执行“撤回并修改”'}), 400
        row = _xiaotu_get_report_row(wendangid)
        if not row:
            return jsonify({'success': False, 'message': '未找到对应日报'}), 404
        if session_user_name != str(row.get('xingming') or '').strip():
            return jsonify({'success': False, 'message': '只能修改自己提报的日报'}), 403
        source_doc_token = _xiaotu_extract_source_doc_token(wendangid)
        doc_url = _feishu_build_cloud_doc_url("", source_doc_token) if source_doc_token else ""
        body_html = str(row.get('zhengwen') or '').strip()
        has_html = bool(re.search(r"</?[A-Za-z][^>]*>", body_html))
        return jsonify({
            'success': True,
            'data': {
                'wendangid': wendangid,
                'title': str(row.get('biaoti') or '').strip(),
                'riqi': str(row.get('riqi') or '').strip(),
                'report_type': _xiaotu_report_type_from_kind(row.get('leixing')),
                'report_kind': str(row.get('leixing') or '').strip(),
                'person_type_value': _xiaotu_person_type_to_value(row.get('renyuanleixing')),
                'person_type_text': str(row.get('renyuanleixing') or '').strip(),
                'draft_html': body_html if has_html else '',
                'draft_text': '' if has_html else body_html,
                'image_paths': _xiaotu_split_cache_multi_value(row.get('tupianlujin')),
                'notify_open_ids': list(edit_ready.get('notify_open_ids') or []),
                'notify_targets': list(edit_ready.get('notify_targets') or []),
                'source_doc_token': source_doc_token,
                'doc_url': doc_url,
                'pingjia': str(row.get('pingjia') or '').strip(),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取日报编辑数据失败: {str(e)}'}), 500


@app.route('/api/xiaotu/moban', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_moban_list():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    try:
        sql_text = f"""
            SELECT XingMing, Moban, NeiRong, RiQi
            FROM baogao_moban
            ORDER BY RiQi DESC, XingMing ASC, Moban ASC
        """
        rows = sf_db(sql_text) or []
        out = []
        for row in rows:
            if isinstance(row, dict):
                one = {
                    'xingming': str(row.get('XingMing') or row.get('xingming') or '').strip(),
                    'moban': str(row.get('Moban') or row.get('moban') or '').strip(),
                    'neirong': str(row.get('NeiRong') or row.get('neirong') or '').strip(),
                    'riqi': str(row.get('RiQi') or row.get('riqi') or '').strip(),
                }
            else:
                values = list(row) if isinstance(row, (list, tuple)) else []
                one = {
                    'xingming': str(values[0] if len(values) > 0 else '').strip(),
                    'moban': str(values[1] if len(values) > 1 else '').strip(),
                    'neirong': str(values[2] if len(values) > 2 else '').strip(),
                    'riqi': str(values[3] if len(values) > 3 else '').strip(),
                }
            if one['moban']:
                one['moban_key'] = f"{one['xingming']}||{one['moban']}"
                out.append(one)
        return jsonify({'success': True, 'data': out})
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取模板失败: {str(e)}'}), 500


@app.route('/api/xiaotu/moban', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_moban_save():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    user_name = str(session.get('feishu_user_name') or '').strip()
    if not user_name:
        return jsonify({'success': False, 'message': '未获取到当前用户名'}), 400

    data = request.get_json(silent=True) or {}
    moban = str(data.get('moban') or '').strip()
    neirong = str(data.get('neirong') or '').strip()
    source_moban = str(data.get('source_moban') or moban).strip()
    if not moban:
        return jsonify({'success': False, 'message': '模板名不能为空'}), 400
    if not neirong:
        return jsonify({'success': False, 'message': '模板内容不能为空'}), 400

    riqi = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    esc_name = _xiaotu_sql_escape(user_name)
    esc_moban = _xiaotu_sql_escape(moban)
    esc_source_moban = _xiaotu_sql_escape(source_moban)
    esc_neirong = _xiaotu_sql_escape(neirong)
    try:
        sql_text = f"""
            IF EXISTS (
                SELECT 1 FROM baogao_moban
                WHERE XingMing = N'{esc_name}' AND Moban = N'{esc_source_moban}'
            )
            BEGIN
                UPDATE baogao_moban
                SET Moban = N'{esc_moban}', NeiRong = N'{esc_neirong}', RiQi = '{riqi}'
                WHERE XingMing = N'{esc_name}' AND Moban = N'{esc_source_moban}'
            END
            ELSE IF EXISTS (
                SELECT 1 FROM baogao_moban
                WHERE XingMing = N'{esc_name}' AND Moban = N'{esc_moban}'
            )
            BEGIN
                UPDATE baogao_moban
                SET NeiRong = N'{esc_neirong}', RiQi = '{riqi}'
                WHERE XingMing = N'{esc_name}' AND Moban = N'{esc_moban}'
            END
            ELSE
            BEGIN
                INSERT INTO baogao_moban (XingMing, Moban, NeiRong, RiQi)
                VALUES (N'{esc_name}', N'{esc_moban}', N'{esc_neirong}', '{riqi}')
            END
        """
        dui_db(sql_text)
        return jsonify({
            'success': True,
            'message': '模板已保存',
            'data': {
                'xingming': user_name,
                'moban': moban,
                'neirong': neirong,
                'riqi': riqi
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存模板失败: {str(e)}'}), 500


@app.route('/api/xiaotu/moban', methods=['DELETE'])
@require_permission('xiaotu_qa')
def api_xiaotu_moban_delete():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    user_name = str(session.get('feishu_user_name') or '').strip()
    if not user_name:
        return jsonify({'success': False, 'message': '未获取到当前用户名'}), 400

    moban = str(request.args.get('moban') or '').strip()
    if not moban:
        return jsonify({'success': False, 'message': '缺少模板名'}), 400
    esc_name = _xiaotu_sql_escape(user_name)
    esc_moban = _xiaotu_sql_escape(moban)
    try:
        sql_text = f"""
            DELETE FROM baogao_moban
            WHERE XingMing = N'{esc_name}' AND Moban = N'{esc_moban}'
        """
        dui_db(sql_text)
        return jsonify({'success': True, 'message': '模板已删除'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除模板失败: {str(e)}'}), 500


@app.route('/api/xiaotu/docs', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_docs():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    user_access_token = str(session.get('feishu_user_access_token') or '').strip()
    if not user_access_token:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu')
        return jsonify({
            'success': False,
            'message': '登录状态缺少云文档访问凭证，正在跳转重新登录',
            'auth_url': url_for('feishu_auth')
        }), 401
    force_refresh = str(request.args.get('refresh') or '').strip().lower() in {'1', 'true', 'yes'}
    docs, sync_err = _xiaotu_get_doc_candidates_for_user(
        user_id,
        force_refresh=force_refresh,
        user_access_token=user_access_token
    )
    if _xiaotu_need_reauth(sync_err):
        session['feishu_user_access_token'] = ''
        session['feishu_user_access_token_expire_at'] = ''
        session['post_auth_redirect'] = url_for('dashboard_xiaotu')
        return jsonify({
            'success': False,
            'message': '飞书登录已过期，正在跳转重新登录',
            'auth_url': url_for('feishu_auth')
        }), 401
    sync_apply_url = _xiaotu_extract_url_from_text(sync_err)
    return jsonify({'success': True, 'data': docs, 'sync_error': sync_err, 'sync_apply_url': sync_apply_url})


@app.route('/api/xiaotu/docs', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_add_doc():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    data = request.get_json(silent=True) or {}
    url_raw = str(data.get('url') or '').strip()
    name = str(data.get('name') or '').strip()
    url = _feishu_find_cloud_doc_url_any(url_raw) or url_raw
    if not url:
        return jsonify({'success': False, 'message': '请填写云文档链接'}), 400
    token = _xiaotu_extract_doc_token(url)
    if not token:
        return jsonify({'success': False, 'message': '链接不是可识别的飞书云文档地址'}), 400
    agent = _get_cloud_documents_agent()
    if agent is None:
        return jsonify({'success': False, 'message': '云文档模块未加载成功'}), 500
    _, err = agent.fetch_document_text(url, include_images_ocr=False)
    if err:
        return jsonify({'success': False, 'message': err}), 400
    rows = _xiaotu_get_user_saved_docs(user_id)
    for one in rows:
        if str(one.get('url') or '').strip() == url:
            return jsonify({'success': True, 'data': one})
    now_s = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    doc_id = f"p_{token}_{int(datetime.now().timestamp() * 1000)}"
    new_item = {
        'id': doc_id,
        'name': name or f'云文档-{token[:8]}',
        'url': url,
        'source': 'personal',
        'created_at': now_s
    }
    rows.insert(0, new_item)
    if len(rows) > 50:
        rows = rows[:50]
    _xiaotu_set_user_saved_docs(user_id, rows)
    return jsonify({'success': True, 'data': new_item})


@app.route('/api/xiaotu/docs/<doc_id>', methods=['DELETE'])
@require_permission('xiaotu_qa')
def api_xiaotu_delete_doc(doc_id):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    target = str(doc_id or '').strip()
    rows = _xiaotu_get_user_saved_docs(user_id)
    next_rows = [x for x in rows if str((x or {}).get('id') or '').strip() != target]
    _xiaotu_set_user_saved_docs(user_id, next_rows)
    return jsonify({'success': True})


@app.route('/api/xiaotu/chat', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_chat():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    user_access_token = str(session.get('feishu_user_access_token') or '').strip()
    if not user_access_token:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu')
        return jsonify({
            'success': False,
            'message': '登录状态缺少云文档访问凭证，正在跳转重新登录',
            'auth_url': url_for('feishu_auth')
        }), 401
    data = request.get_json(silent=True) or {}
    mode = str(data.get('mode') or 'qa').strip().lower()
    question = str(data.get('question') or '').strip()
    doc_id = str(data.get('doc_id') or '').strip()
    manual_url = str(data.get('doc_url') or '').strip()
    conv = str(data.get('conversation_id') or '').strip()
    if not conv:
        conv = f"xiaotu:{user_id}:{int(datetime.now().timestamp())}"
    docs, _ = _xiaotu_get_doc_candidates_for_user(
        user_id,
        force_refresh=False,
        user_access_token=user_access_token
    )
    selected = None
    if doc_id:
        for one in docs:
            if str(one.get('id') or '').strip() == doc_id:
                selected = one
                break
    if selected is None:
        url = _feishu_find_cloud_doc_url_any(manual_url) or manual_url
        if not url:
            url = _feishu_find_cloud_doc_url_any(question) or ""
        if not url:
            token_only = _xiaotu_extract_doc_token(question)
            if token_only.startswith("doxcn"):
                url = _feishu_build_cloud_doc_url("docx", token_only)
            elif token_only.startswith("doccn"):
                url = _feishu_build_cloud_doc_url("doc", token_only)
            elif token_only.startswith("wiki"):
                url = _feishu_build_cloud_doc_url("wiki", token_only)
        if not url:
            return jsonify({'success': False, 'message': '请通过输入框中的+号选择云文档，或直接粘贴飞书云文档链接后再发送'}), 400
        token = _xiaotu_extract_doc_token(url)
        if not token:
            return jsonify({'success': False, 'message': '链接不是可识别的飞书云文档地址'}), 400
        selected = {
            'id': f'adhoc_{token}',
            'name': f'临时文档-{token[:8]}',
            'url': url
        }
    doc_url = str(selected.get('url') or '').strip()
    if not doc_url:
        return jsonify({'success': False, 'message': '文档链接无效'}), 400
    if mode == 'analysis':
        ask = question or '请按周报/月报分析方式，输出评分、亮点、不足、原因证据和可执行改进建议。'
        answer = _generate_cloud_doc_analysis(ask, doc_url, chat_id=conv)
    else:
        ask = question or '请先总结文档核心信息，再给出关键结论。'
        answer = _generate_ai_answer_with_cloud_doc_url(ask, doc_url, chat_id=conv)
    _feishu_append_chat_history(conv, "user", ask)
    _feishu_append_chat_history(conv, "assistant", answer or "")
    return jsonify({
        'success': True,
        'data': {
            'conversation_id': conv,
            'doc': {
                'id': str(selected.get('id') or ''),
                'name': str(selected.get('name') or ''),
                'url': doc_url
            },
            'answer': answer or ''
        }
    })


@app.route('/api/xiaotu/report_cache', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_cache():
    try:
        user_name = str(session.get('feishu_user_name') or '').strip()
        if not user_name:
            return jsonify({'success': False, 'message': '未登录'}), 401
        return jsonify({
            'success': True,
            'data': _xiaotu_get_report_cache(user_name)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取缓存失败: {str(e)}'}), 500


@app.route('/api/xiaotu/report_notify_config', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_notify_config():
    try:
        data = request.get_json(silent=True) or {}
        user_name = str(session.get('feishu_user_name') or '').strip()
        if not user_name:
            return jsonify({'success': False, 'message': '未登录'}), 401
        selected_notify_targets = _xiaotu_parse_notify_targets(data)
        selected_notify_open_ids = _xiaotu_resolve_notify_open_ids(
            _xiaotu_parse_notify_open_ids(data),
            selected_notify_targets
        )
        selected_notify_names = _xiaotu_resolve_notify_names(selected_notify_open_ids, selected_notify_targets)
        notify_time = _xiaotu_normalize_notify_time(data.get('notify_time') or '')

        _xiaotu_upsert_report_cache_notify(
            user_name,
            selected_notify_open_ids,
            selected_notify_targets,
            notify_time
        )
        return jsonify({
            'success': True,
            'message': '提醒设置已保存',
            'data': _xiaotu_get_report_cache(user_name)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存提醒设置失败: {str(e)}'}), 500


@app.route('/api/xiaotu/report_test_reminder', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_test_reminder():
    try:
        data = request.get_json(silent=True) or {}
        user_name = str(session.get('feishu_user_name') or '').strip()
        session_user_id = str(session.get('feishu_user_id') or '').strip()
        if not user_name:
            return jsonify({'success': False, 'message': '未登录'}), 401
        cache_data = _xiaotu_get_report_cache(user_name)
        notify_time = _xiaotu_normalize_notify_time(
            data.get('notify_time') or (cache_data or {}).get('notify_time') or ''
        )
        open_id = session_user_id if session_user_id.startswith('ou_') else ''
        if not open_id:
            open_id = str(_xiaotu_lookup_open_id_by_name(user_name) or '').strip()
        if not open_id:
            return jsonify({
                'success': False,
                'message': '未找到当前用户对应的飞书 open_id，无法发送测试提醒',
                'data': {
                    'user_name': user_name,
                    'notify_time': notify_time,
                    'session_user_id': session_user_id,
                    'resolved_open_id': ''
                }
            }), 400
        has_submitted_today = _xiaotu_has_report_submitted_today(user_name)
        ok = _xiaotu_send_missing_report_reminder(open_id, 'open_id', user_name, notify_time)
        return jsonify({
            'success': bool(ok),
            'message': ('测试提醒已发送' if ok else '测试提醒发送失败'),
            'data': {
                'user_name': user_name,
                'notify_time': notify_time,
                'session_user_id': session_user_id,
                'resolved_open_id': open_id,
                'has_submitted_today': bool(has_submitted_today),
                'cache': cache_data
            }
        }), (200 if ok else 500)
    except Exception as e:
        return jsonify({'success': False, 'message': f'测试提醒发送失败: {str(e)}'}), 500


@app.route('/api/xiaotu/report_reminder_logs', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_reminder_logs():
    try:
        limit_raw = request.args.get('limit', 100)
        try:
            limit = max(1, min(200, int(limit_raw)))
        except Exception:
            limit = 100
        with _xiaotu_report_reminder_lock:
            logs = list(_xiaotu_report_reminder_logs[-limit:])
            sent_marks = dict(_xiaotu_report_reminder_sent_marks)
        return jsonify({
            'success': True,
            'data': {
                'thread_started': bool(_xiaotu_report_reminder_thread_started),
                'pid': os.getpid(),
                'limit': limit,
                'count': len(logs),
                'sent_marks': sent_marks,
                'runtime_open_id_cache': dict(_xiaotu_user_open_id_cache),
                'logs': logs
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取自动提醒运行日志失败: {str(e)}'}), 500


@app.route('/api/xiaotu/report_draft', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_draft():
    try:
        is_multipart = str(request.content_type or "").lower().startswith("multipart/form-data")
        if is_multipart:
            data = request.form.to_dict() if request.form else {}
        else:
            data = request.get_json(silent=True) or {}
        user_id = str(session.get('feishu_user_id') or '').strip()
        user_name = str(session.get('feishu_user_name') or '').strip()
        if not user_id or not user_name:
            return jsonify({'success': False, 'message': '未登录'}), 401

        rich_content_html = str(data.get('rich_content_html') or data.get('rich_content') or '').strip()
        selected_notify_targets = _xiaotu_parse_notify_targets(data)
        selected_notify_open_ids = _xiaotu_resolve_notify_open_ids(
            _xiaotu_parse_notify_open_ids(data),
            selected_notify_targets
        )
        notify_time = _xiaotu_normalize_notify_time(data.get('notify_time') or '')
        selected_notify_names = _xiaotu_resolve_notify_names(selected_notify_open_ids, selected_notify_targets)

        uploaded_files = request.files.getlist('images') if is_multipart else []
        draft_token = f"draft_{user_id}_{int(datetime.now().timestamp())}"
        draft_root_dir = r"D:\tuchuangai\报告缓存图片"
        draft_html = rich_content_html
        image_paths = _xiaotu_extract_report_image_paths_from_html(draft_html)
        if uploaded_files:
            saved_paths, _, _ = _xiaotu_save_uploaded_images_and_ocr_safe(
                uploaded_files,
                report_token=draft_token,
                root_base_dir=draft_root_dir
            )
            for one_path in (saved_paths or []):
                if one_path and one_path not in image_paths:
                    image_paths.append(one_path)
            draft_html = _xiaotu_replace_html_img_src_with_paths(draft_html, saved_paths or [])
        if draft_html:
            draft_html, inline_paths, _, _ = _xiaotu_save_inline_html_images_and_ocr_safe(
                draft_html,
                report_token=draft_token,
                root_base_dir=draft_root_dir
            )
            for one_path in (inline_paths or []):
                if one_path and one_path not in image_paths:
                    image_paths.append(one_path)
            draft_html, remote_paths, _, _ = _xiaotu_save_remote_html_images_and_ocr_safe(
                draft_html,
                report_token=draft_token,
                agent=_get_cloud_documents_agent(),
                root_base_dir=draft_root_dir
            )
            for one_path in (remote_paths or []):
                if one_path and one_path not in image_paths:
                    image_paths.append(one_path)

        if not draft_html and image_paths:
            draft_html = "".join(
                f'<p><img src="{str(p or "").replace("\\", "/")}" alt="draft-image"></p>'
                for p in image_paths if str(p or "").strip()
            )
        draft_html = _xiaotu_compact_report_body_for_storage(draft_html)

        _xiaotu_upsert_report_cache_notify(
            user_name,
            selected_notify_open_ids,
            selected_notify_targets,
            notify_time
        )
        _xiaotu_upsert_report_cache_draft(user_name, draft_html, image_paths)

        return jsonify({
            'success': True,
            'message': '草稿已保存',
            'data': _xiaotu_get_report_cache(user_name)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存草稿失败: {str(e)}'}), 500


@app.route('/api/xiaotu/report_submit', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_submit():
    stage = "start"
    try:
        stage = "parse_request"
        is_multipart = str(request.content_type or "").lower().startswith("multipart/form-data")
        if is_multipart:
            data = request.form.to_dict() if request.form else {}
        else:
            data = request.get_json(silent=True) or {}
        doc_id = str(data.get('doc_id') or '').strip()
        manual_url = str(data.get('doc_url') or '').strip()
        question = str(data.get('question') or '').strip()
        rich_content_html = str(data.get('rich_content_html') or data.get('rich_content') or '').strip()
        notify_time = _xiaotu_normalize_notify_time(data.get('notify_time') or '')
        report_type = str(data.get('report_type') or 'week').strip()
        person_type_raw = str(data.get('renyuanleixing') or data.get('person_type') or 'formal_staff').strip()
        notify_mode = str(data.get('notify_mode') or '').strip().lower()
        edit_wendangid = str(data.get('edit_wendangid') or '').strip()
        selected_notify_targets = _xiaotu_parse_notify_targets(data)
        selected_notify_open_ids = _xiaotu_resolve_notify_open_ids(
            _xiaotu_parse_notify_open_ids(data),
            selected_notify_targets
        )
        selected_notify_names = _xiaotu_resolve_notify_names(selected_notify_open_ids, selected_notify_targets)
        selected_notify_name_map = {}
        for item in (selected_notify_targets or []):
            if not isinstance(item, dict):
                continue
            oid = str(item.get("open_id") or "").strip()
            nm = str(item.get("name") or "").strip()
            if oid and nm and oid not in selected_notify_name_map:
                selected_notify_name_map[oid] = nm
        try:
            selected_notify_name_map.update(_xiaotu_query_user_names_by_open_ids(selected_notify_open_ids) or {})
        except Exception:
            pass
        person_type = _xiaotu_person_type_from_value(person_type_raw)
        selected_report_kind = _xiaotu_report_kind_from_type(report_type)
        redirect_endpoint = str(data.get('redirect_endpoint') or 'dashboard_xiaotu').strip()
        uploaded_files = request.files.getlist('images') if is_multipart else []

        stage = "auth"
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        user_access_token = str(session.get('feishu_user_access_token') or '').strip()
        if not user_access_token:
            session['post_auth_redirect'] = _xiaotu_resolve_redirect_url(redirect_endpoint, fallback='dashboard_xiaotu')
            return jsonify({
                'success': False,
                'message': '登录状态缺少云文档访问凭证，正在跳转重新登录',
                'auth_url': url_for('feishu_auth')
            }), 401
        uploader_name = str(session.get('feishu_user_name') or '未知用户').strip()
        existing_report_row = {}
        existing_report_time_text = ""
        existing_source_doc_token = ""
        if edit_wendangid:
            edit_ready = _xiaotu_get_report_edit_ready_session(edit_wendangid)
            if not edit_ready:
                return jsonify({'success': False, 'message': '当前日报未进入可编辑状态，请先从历史页执行“撤回并修改”'}), 400
            existing_report_row = _xiaotu_get_report_row(edit_wendangid)
            if not existing_report_row:
                return jsonify({'success': False, 'message': '未找到需要修改的原日报'}), 404
            if uploader_name != str(existing_report_row.get('xingming') or '').strip():
                return jsonify({'success': False, 'message': '只能修改自己提报的日报'}), 403
            existing_report_time_text = str(existing_report_row.get('riqi') or '').strip()
            existing_source_doc_token = _xiaotu_extract_source_doc_token(edit_wendangid)

        stage = "pick_doc"
        selected = None
        doc_url = ""
        doc_token = ""
        if manual_url or doc_id or question:
            selected = _xiaotu_pick_doc_for_request(
                user_id=user_id,
                user_access_token=user_access_token,
                doc_id=doc_id,
                manual_url=manual_url,
                question=question
            )
            if selected is not None:
                doc_url = str((selected or {}).get('url') or '').strip()
                doc_token = _xiaotu_extract_doc_token(doc_url)
        if (not doc_url) and (not rich_content_html) and (not uploaded_files):
            return jsonify({'success': False, 'message': '请先选择云文档，或填写富文本内容/上传图片后再提交'}), 400
        if doc_url and not doc_token:
            return jsonify({'success': False, 'message': '未能解析云文档ID'}), 400

        stage = "load_agent"
        agent = _get_cloud_documents_agent()
        if agent is None:
            return jsonify({'success': False, 'message': '云文档模块未加载成功'}), 500

        stage = "fetch_doc_text"
        doc_text = ""
        daily_slice_debug = {"used": False, "matched_date": "", "text_sliced": False, "image_token_count": 0, "block_error": ""}
        daily_slice_image_tokens = []
        should_slice_daily = False
        auto_daily_structured = False
        if doc_url:
            doc_text, err = agent.fetch_document_text(doc_url, include_images_ocr=False)
            if err:
                return jsonify({'success': False, 'message': err}), 400
            daily_heading_count = _xiaotu_count_daily_date_headings(doc_text)
            last_daily_pos, _ = _xiaotu_find_last_daily_date_start(doc_text)
            auto_daily_structured = last_daily_pos >= 0
            initial_report_kind = selected_report_kind or _xiaotu_detect_report_kind(
                question,
                str((selected or {}).get('name') or ''),
                doc_text
            )
            should_slice_daily = (initial_report_kind == "日报") or auto_daily_structured
            if should_slice_daily:
                doc_text, daily_slice_image_tokens, daily_slice_debug = _xiaotu_slice_daily_doc_content(agent, doc_url, doc_text)
        rich_text_plain = _xiaotu_html_to_plain_text_preserve_blocks(rich_content_html or "")
        body_text = str(doc_text or '').strip()
        if rich_content_html:
            body_text = rich_content_html.strip()
        source_doc_token = str(doc_token or "").strip()
        if not source_doc_token and edit_wendangid:
            source_doc_token = existing_source_doc_token
        report_wendangid_raw = edit_wendangid or _xiaotu_build_report_instance_id(source_doc_token)
        upload_image_paths, upload_image_ocr_text, upload_debug = _xiaotu_save_uploaded_images_and_ocr_safe(
            uploaded_files,
            report_token=report_wendangid_raw
        )
        inline_image_paths, inline_image_ocr_text, inline_image_debug = ([], "", {"reason_code": "no_inline_image", "reason_text": "未检测到富文本内嵌图片", "saved_image_count": 0})
        remote_image_paths, remote_image_ocr_text, remote_image_debug = ([], "", {"reason_code": "no_remote_image", "reason_text": "未检测到富文本远程图片", "saved_image_count": 0})
        if rich_content_html:
            body_text = _xiaotu_replace_html_img_src_with_paths(rich_content_html, upload_image_paths)
            body_text, inline_image_paths, inline_image_ocr_text, inline_image_debug = _xiaotu_save_inline_html_images_and_ocr_safe(
                body_text,
                report_token=report_wendangid_raw
            )
            body_text, remote_image_paths, remote_image_ocr_text, remote_image_debug = _xiaotu_save_remote_html_images_and_ocr_safe(
                body_text,
                report_token=report_wendangid_raw,
                agent=agent
            )
        upload_image_paths = (upload_image_paths or []) + (inline_image_paths or []) + (remote_image_paths or [])
        upload_image_ocr_text = "\n\n".join([
            x for x in [
                str(upload_image_ocr_text or "").strip(),
                str(inline_image_ocr_text or "").strip(),
                str(remote_image_ocr_text or "").strip()
            ] if x
        ]).strip()
        guessed_title_text = _xiaotu_guess_title(
            (selected or {}).get('name'),
            rich_text_plain or body_text,
            source_doc_token or report_wendangid_raw
        )
        report_kind = ("日报" if should_slice_daily else (selected_report_kind or _xiaotu_detect_report_kind(question, guessed_title_text, body_text)))
        report_date_text = datetime.now().strftime('%Y-%m-%d')
        if edit_wendangid and existing_report_time_text:
            report_date_text = str(existing_report_time_text).strip()[:10] or report_date_text
        title_text = _xiaotu_build_report_title(uploader_name, report_kind, report_date_text)
        person_focus_text = _xiaotu_person_focus_text(person_type)

        stage = "image_extract"
        doc_image_paths, doc_image_ocr_text, image_debug = ([], "", {"reason_code": "skip", "reason_text": "未使用云文档图片", "saved_image_count": 0})
        if doc_url and doc_token:
            doc_image_paths, doc_image_ocr_text, image_debug = _xiaotu_save_doc_images_and_ocr_safe(
                agent,
                doc_token,
                doc_url=doc_url,
                specific_tokens=(daily_slice_image_tokens if should_slice_daily else None)
            )
        image_paths = (doc_image_paths or []) + (upload_image_paths or [])
        image_paths_text = "|".join(image_paths)
        image_ocr_text = "\n\n".join([x for x in [str(doc_image_ocr_text or "").strip(), str(upload_image_ocr_text or "").strip()] if x]).strip()
        body_text = _xiaotu_compact_report_body_for_storage(body_text)
        # Preserve the original structured body for card rendering; plain text is only a last fallback.
        notify_source_text = str(body_text or rich_content_html or doc_text or rich_text_plain or "").strip()
        notify_image_key = _feishu_upload_image_by_path_safe(image_paths[0]) if image_paths else ""
        today_text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        stage = "build_sql_fast"
        pingjia_text = "AI分析中，完成后将自动更新评价结果并推送互动卡片。"
        org_perf_context = ""
        org_perf_contribution_text = ""
        wen_dang_id = _xiaotu_sql_escape(report_wendangid_raw)
        biao_ti = _xiaotu_sql_escape(title_text)
        zheng_wen = _xiaotu_sql_escape(body_text)
        tu_pian_lu_jin = _xiaotu_sql_escape(image_paths_text)
        xing_ming = _xiaotu_sql_escape(uploader_name)
        ping_jia = _xiaotu_sql_escape(pingjia_text)
        tu_pian_nei_rong = _xiaotu_sql_escape(image_ocr_text)
        lei_xing = _xiaotu_sql_escape(report_kind)
        renyuan_lei_xing = _xiaotu_sql_escape(person_type)
        jie_shou_ren = _xiaotu_sql_escape("|".join(selected_notify_names))
        report_time_text = existing_report_time_text or today_text
        report_time_esc = _xiaotu_sql_escape(report_time_text)

        if edit_wendangid:
            sql_insert = f"""
                UPDATE baogao
                SET BiaoTi = N'{biao_ti}',
                    ZhengWen = N'{zheng_wen}',
                    TuPianLujin = N'{tu_pian_lu_jin}',
                    XingMing = N'{xing_ming}',
                    RiQi = '{report_time_esc}',
                    PingJia = N'{ping_jia}',
                    TuPianNeiRong = N'{tu_pian_nei_rong}',
                    LeiXing = N'{lei_xing}',
                    RenYuanLeiXing = N'{renyuan_lei_xing}',
                    JieShouRen = N'{jie_shou_ren}'
                WHERE WenDangID = '{wen_dang_id}'
                  AND XingMing = N'{xing_ming}'
            """
        else:
            sql_insert = f"""
                IF EXISTS (
                    SELECT 1
                    FROM baogao WITH (UPDLOCK, HOLDLOCK)
                    WHERE WenDangID = '{wen_dang_id}'
                      AND XingMing = N'{xing_ming}'
                )
                BEGIN
                    UPDATE baogao
                    SET BiaoTi = N'{biao_ti}',
                        ZhengWen = N'{zheng_wen}',
                        TuPianLujin = N'{tu_pian_lu_jin}',
                        XingMing = N'{xing_ming}',
                        RiQi = '{report_time_esc}',
                        PingJia = N'{ping_jia}',
                        TuPianNeiRong = N'{tu_pian_nei_rong}',
                        LeiXing = N'{lei_xing}',
                        RenYuanLeiXing = N'{renyuan_lei_xing}',
                        JieShouRen = N'{jie_shou_ren}'
                    WHERE WenDangID = '{wen_dang_id}'
                      AND XingMing = N'{xing_ming}'
                END
                ELSE
                BEGIN
                    INSERT INTO baogao (WenDangID, BiaoTi, ZhengWen, TuPianLujin, XingMing, RiQi, PingJia, TuPianNeiRong, LeiXing, RenYuanLeiXing, JieShouRen)
                    VALUES (
                        '{wen_dang_id}',
                        N'{biao_ti}',
                        N'{zheng_wen}',
                        N'{tu_pian_lu_jin}',
                        N'{xing_ming}',
                        '{report_time_esc}',
                        N'{ping_jia}',
                        N'{tu_pian_nei_rong}',
                        N'{lei_xing}',
                        N'{renyuan_lei_xing}',
                        N'{jie_shou_ren}'
                    )
                END
            """

        stage = "db_insert_fast"
        try:
            dui_db(sql_insert)
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'写入baogao失败: {str(e)}',
                'stage': stage
            }), 500

        comment_url = url_for('xiaotu_report_comment_page', wendangid=report_wendangid_raw, _external=True) if report_wendangid_raw else ""
        report_url = _xiaotu_build_report_history_url(report_wendangid_raw)
        _xiaotu_remember_report_owner_open_id(report_wendangid_raw, user_id)

        bg_payload = {
            "report_wendangid_raw": report_wendangid_raw,
            "uploader_name": uploader_name,
            "user_id": user_id,
            "title_text": title_text,
            "person_type": person_type,
            "person_focus_text": person_focus_text,
            "report_kind": report_kind,
            "report_type": report_type,
            "rich_text_plain": rich_text_plain,
            "body_text": body_text,
            "image_ocr_text": image_ocr_text,
            "guessed_title_text": guessed_title_text,
            "doc_url": doc_url,
            "notify_source_text": notify_source_text,
            "notify_image_key": notify_image_key,
            "image_paths_text": image_paths_text,
            "comment_url": comment_url,
            "report_url": report_url,
            "selected_notify_open_ids": list(selected_notify_open_ids or []),
            "selected_notify_name_map": dict(selected_notify_name_map or {}),
            "notify_mode": notify_mode,
            "edit_wendangid": edit_wendangid,
        }

        def _xiaotu_report_ai_background_worker(payload):
            with app.app_context():
                try:
                    uid = str(payload.get("user_id") or "").strip()
                    wid = str(payload.get("report_wendangid_raw") or "").strip()
                    uname = str(payload.get("uploader_name") or "").strip()
                    kind = str(payload.get("report_kind") or "").strip()
                    ptype = str(payload.get("person_type") or "").strip()
                    focus = str(payload.get("person_focus_text") or "").strip()
                    rich_plain = str(payload.get("rich_text_plain") or "").strip()
                    body = str(payload.get("body_text") or "").strip()
                    img_ocr = str(payload.get("image_ocr_text") or "").strip()
                    prompt = (
                        f"请按{kind}要求对该日报进行简短评价，并结合人员类型侧重点输出。\n"
                        f"{focus}\n"
                        "请把正文和图片识别内容作为同一份材料统一分析。输出要短、准、具体，控制在120字以内。"
                    )
                    source = f"正文：\n{rich_plain or _xiaotu_html_to_plain_text_preserve_blocks(body)}\n\n图片识别内容：\n{img_ocr or '（无）'}"
                    ai_text = _generate_ai_answer_with_doc(
                        prompt_text=prompt,
                        doc_text=source,
                        doc_name=str(payload.get("guessed_title_text") or payload.get("title_text") or "日报内容"),
                        chat_id=f"xiaotu_report_bg:{uid}:{int(datetime.now().timestamp())}"
                    )
                    final_pingjia = str(ai_text or "").strip()
                    org_text = ""
                    is_daily = (str(payload.get("report_type") or "").strip().lower() in {"day", "daily"}) or ("日报" in kind)
                    if is_daily:
                        org_ctx = _xiaotu_lookup_org_perf_context(uname)
                        if org_ctx:
                            org_text = _xiaotu_generate_org_perf_contribution(
                                uname,
                                kind,
                                source,
                                org_ctx,
                                chat_id=f"xiaotu_org_perf_bg:{uid}:{int(datetime.now().timestamp())}"
                            )
                            if org_text:
                                if "组织绩效贡献" not in org_text and "对组织绩效影响" not in org_text:
                                    org_text = f"组织绩效贡献：{org_text}"
                                final_pingjia = "\n\n".join([x for x in [final_pingjia, org_text] if x]).strip()
                    if not final_pingjia:
                        final_pingjia = "AI分析暂未生成有效评价。"
                    dui_db(f"""
                        UPDATE baogao
                        SET PingJia = N'{_xiaotu_sql_escape(final_pingjia)}'
                        WHERE WenDangID = '{_xiaotu_sql_escape(wid)}'
                          AND XingMing = N'{_xiaotu_sql_escape(uname)}'
                    """)

                    targets = [uid]
                    selected_ids = [str(x or "").strip() for x in (payload.get("selected_notify_open_ids") or []) if str(x or "").strip()]
                    targets.extend([x for x in selected_ids if x != uid])
                    should_add_default_target = (not selected_ids) or (str(payload.get("notify_mode") or "").strip().lower() == "selected_plus_default")
                    if should_add_default_target:
                        try:
                            primary_dept_id, _ = _xiaotu_pick_primary_department(uid)
                            leader_id = _xiaotu_get_department_leader_user_id(primary_dept_id)
                            if leader_id and leader_id != uid:
                                targets.append(leader_id)
                        except Exception:
                            pass
                    sent = set()
                    for target in targets:
                        target = str(target or "").strip()
                        if not target or target in sent:
                            continue
                        sent.add(target)
                        _xiaotu_send_report_notification(
                            target,
                            "open_id",
                            str(payload.get("title_text") or "").strip(),
                            ptype,
                            final_pingjia,
                            doc_url=str(payload.get("doc_url") or "").strip(),
                            source_text=str(payload.get("notify_source_text") or "").strip(),
                            image_key=str(payload.get("notify_image_key") or "").strip(),
                            image_paths_text=str(payload.get("image_paths_text") or "").strip(),
                            wendangid=wid,
                            comment_url=str(payload.get("comment_url") or "").strip(),
                            report_url=str(payload.get("report_url") or "").strip(),
                            org_impact_text=org_text
                        )
                except Exception as bg_err:
                    _safe_debug_print(f"后台日报AI分析失败: {payload.get('report_wendangid_raw')} -> {bg_err}")

        Thread(target=_xiaotu_report_ai_background_worker, args=(bg_payload,), daemon=True).start()

        cache_warning = ""
        try:
            _xiaotu_upsert_report_cache_notify(
                uploader_name,
                selected_notify_open_ids,
                selected_notify_targets,
                notify_time
            )
            _xiaotu_clear_report_cache_draft(uploader_name)
            if edit_wendangid:
                _xiaotu_clear_report_edit_ready_session(edit_wendangid)
        except Exception as cache_err:
            cache_warning = str(cache_err)

        return jsonify({
            'success': True,
            'message': '提交成功，AI分析将在后台进行，完成后会自动更新评价并推送互动卡片。',
            'data': {
                'doc_id': doc_token or "",
                'report_id': report_wendangid_raw,
                'source_doc_token': source_doc_token,
                'doc_url': doc_url or "",
                'edit_wendangid': edit_wendangid,
                'title': title_text,
                'submitter_name': uploader_name,
                'report_kind': report_kind,
                'renyuanleixing': person_type,
                'image_count': len(image_paths),
                'image_paths': image_paths,
                'image_debug': image_debug,
                'daily_slice_debug': daily_slice_debug,
                'upload_image_debug': upload_debug,
                'inline_image_debug': inline_image_debug,
                'remote_image_debug': remote_image_debug,
                'pushed': False,
                'ai_background': True,
                'notify_policy': '后台AI分析完成后推送',
                'notify_time': notify_time,
                'notify_detail': {},
                'jieshouren': selected_notify_names,
                'pingjia': pingjia_text,
                'org_perf_matched': False,
                'org_perf_contribution': '',
                'cache_cleared': (cache_warning == ""),
                'cache_warning': cache_warning
            }
        })

        stage = "ai_analysis"
        eval_prompt = (
            f"请按{report_kind}要求对该文档进行总结，并结合“{person_type}”身份侧重点输出精简评价。\n"
            f"{person_focus_text}\n"
            "请把正文内容和图片识别内容视为同一份素材统一分析，不要分开写两套结论；若图片内容与正文互补，请合并后再判断。\n"
            f"{'若人员类型为管培生/实习，请按“当日工作内容 -> 遇到的问题、解决方案与思路扩展 -> 明日计划 -> 好用的工作方法与素材积累”的顺序判断，其中“当日工作内容”最重要，必须优先写清楚。\\n' if person_type == '管培生/实习' else ''}"
            "先判断素材是否足够支撑分析：如果正文和图片内容总量很少，只有几个字，或主要是“测试、试试、123、111、abc”等无实际业务信息的内容，"
            "说明信息不足，不能根据人员类型去脑补SOP执行、流程优化、协作效率、结果稳定性等表现。\n"
            "输出要短、准、易读，目标是让人一眼看懂，不要写成长篇分析。\n"
            "输出结构要求为：\n"
            "1. 重点总结：2-3句，优先写最重要进展、结果或问题，必须贴合该人员类型的侧重点。\n"
            "2. 亮点：仅在正文或图片内容里存在明确、可落地、可说明的亮点时才写1-2条；如果没有明显亮点，就不要输出“亮点”这个标题，也不要凑内容。\n"
            "3. 待改进：最多写1条；如果没有明确问题，可写“暂无明显问题”或直接不写。\n"
            "要求：\n"
            "- 如果素材明显不足，请只输出“重点总结：当前内容过少或仅为测试信息，无法据此做有效业务分析。”；不要输出亮点，不要输出待改进，不要补充推测；\n"
            "- 总体尽量控制在220字以内；\n"
            "- 不要复述过多原文，不要铺陈背景，不要写空话；\n"
            "- 不要把小问题拆成很多条，不足只保留最关键的一条或不写；\n"
            "- 只能根据素材里明确写出的事实来分析，不能把“测试”类内容扩写成真实工作表现；\n"
            "- 语言直接、具体、简短，每条尽量一句话；没有亮点时不要为了凑格式硬写亮点。"
        )
        source_for_eval = (
            f"正文：\n{rich_text_plain or body_text}\n\n"
            f"图片识别内容：\n{image_ocr_text or '（无）'}\n"
        )
        pingjia = _generate_ai_answer_with_doc(
            prompt_text=eval_prompt,
            doc_text=source_for_eval,
            doc_name=guessed_title_text or title_text or "上传内容",
            chat_id=f"xiaotu_report:{user_id}:{int(datetime.now().timestamp())}"
        )
        pingjia_text = str(pingjia or '').strip()
        org_perf_context = ""
        org_perf_contribution_text = ""
        try:
            is_daily_report = (str(report_type or "").strip().lower() in {"day", "daily"}) or ("日报" in str(report_kind or ""))
            if is_daily_report:
                org_perf_context = _xiaotu_lookup_org_perf_context(uploader_name)
                if org_perf_context:
                    org_perf_material = (
                        f"正文：\n{rich_text_plain or _xiaotu_html_to_plain_text_preserve_blocks(body_text)}\n\n"
                        f"图片识别内容：\n{image_ocr_text or '（无）'}"
                    )
                    org_perf_contribution_text = _xiaotu_generate_org_perf_contribution(
                        uploader_name,
                        report_kind,
                        org_perf_material,
                        org_perf_context,
                        chat_id=f"xiaotu_org_perf:{user_id}:{int(datetime.now().timestamp())}"
                    )
                    if org_perf_contribution_text:
                        if "组织绩效贡献" not in org_perf_contribution_text:
                            org_perf_contribution_text = f"组织绩效贡献：{org_perf_contribution_text}"
                        pingjia_text = "\n\n".join([x for x in [pingjia_text, org_perf_contribution_text] if x]).strip()
        except Exception as org_perf_err:
            _safe_debug_print(f"组织绩效贡献分析跳过: {uploader_name} -> {org_perf_err}")

        stage = "build_sql"
        wen_dang_id = _xiaotu_sql_escape(report_wendangid_raw)
        biao_ti = _xiaotu_sql_escape(title_text)
        zheng_wen = _xiaotu_sql_escape(body_text)
        tu_pian_lu_jin = _xiaotu_sql_escape(image_paths_text)
        xing_ming = _xiaotu_sql_escape(uploader_name)
        ping_jia = _xiaotu_sql_escape(pingjia_text)
        tu_pian_nei_rong = _xiaotu_sql_escape(image_ocr_text)
        lei_xing = _xiaotu_sql_escape(report_kind)
        renyuan_lei_xing = _xiaotu_sql_escape(person_type)
        jie_shou_ren = _xiaotu_sql_escape("|".join(selected_notify_names))
        report_time_text = existing_report_time_text or today_text
        report_time_esc = _xiaotu_sql_escape(report_time_text)

        if edit_wendangid:
            sql_insert = f"""
                UPDATE baogao
                SET BiaoTi = N'{biao_ti}',
                    ZhengWen = N'{zheng_wen}',
                    TuPianLujin = N'{tu_pian_lu_jin}',
                    XingMing = N'{xing_ming}',
                    RiQi = '{report_time_esc}',
                    PingJia = N'{ping_jia}',
                    TuPianNeiRong = N'{tu_pian_nei_rong}',
                    LeiXing = N'{lei_xing}',
                    RenYuanLeiXing = N'{renyuan_lei_xing}',
                    JieShouRen = N'{jie_shou_ren}'
                WHERE WenDangID = '{wen_dang_id}'
                  AND XingMing = N'{xing_ming}'
            """
        else:
            sql_insert = f"""
                IF EXISTS (
                    SELECT 1
                    FROM baogao WITH (UPDLOCK, HOLDLOCK)
                    WHERE WenDangID = '{wen_dang_id}'
                      AND XingMing = N'{xing_ming}'
                )
                BEGIN
                    UPDATE baogao
                    SET BiaoTi = N'{biao_ti}',
                        ZhengWen = N'{zheng_wen}',
                        TuPianLujin = N'{tu_pian_lu_jin}',
                        XingMing = N'{xing_ming}',
                        RiQi = '{report_time_esc}',
                        PingJia = N'{ping_jia}',
                        TuPianNeiRong = N'{tu_pian_nei_rong}',
                        LeiXing = N'{lei_xing}',
                        RenYuanLeiXing = N'{renyuan_lei_xing}',
                        JieShouRen = N'{jie_shou_ren}'
                    WHERE WenDangID = '{wen_dang_id}'
                      AND XingMing = N'{xing_ming}'
                END
                ELSE
                BEGIN
                    INSERT INTO baogao (WenDangID, BiaoTi, ZhengWen, TuPianLujin, XingMing, RiQi, PingJia, TuPianNeiRong, LeiXing, RenYuanLeiXing, JieShouRen)
                    VALUES (
                        '{wen_dang_id}',
                        N'{biao_ti}',
                        N'{zheng_wen}',
                        N'{tu_pian_lu_jin}',
                        N'{xing_ming}',
                        '{report_time_esc}',
                        N'{ping_jia}',
                        N'{tu_pian_nei_rong}',
                        N'{lei_xing}',
                        N'{renyuan_lei_xing}',
                        N'{jie_shou_ren}'
                    )
                END
            """

        stage = "db_insert"
        try:
            dui_db(sql_insert)
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'写入baogao失败: {str(e)}',
                'stage': stage
            }), 500

        comment_url = url_for('xiaotu_report_comment_page', wendangid=report_wendangid_raw, _external=True) if report_wendangid_raw else ""
        report_url = _xiaotu_build_report_history_url(report_wendangid_raw)
        _xiaotu_remember_report_owner_open_id(report_wendangid_raw, user_id)

        stage = "feishu_push"
        pushed = _xiaotu_send_report_notification(
            user_id,
            "open_id",
            title_text,
            person_type,
            pingjia_text,
            doc_url=doc_url,
            source_text=notify_source_text,
            image_key=notify_image_key,
            image_paths_text=image_paths_text,
            wendangid=report_wendangid_raw,
            comment_url=comment_url,
            report_url=report_url,
            org_impact_text=org_perf_contribution_text
        )
        notify_policy = "成员提交->部门leader_user_id+自己；负责人提交->陶晓飞+自己"
        if selected_notify_open_ids:
            notify_policy = "按指定人员通知+自己"
            if notify_mode == "selected_plus_default":
                notify_policy = "按指定人员通知+默认上级策略+自己"
        notify_detail = {
            'self_notify': bool(pushed),
            'primary_department_id': '',
            'primary_department_name': '',
            'department_leader_user_id': '',
            'is_uploader_department_leader': False,
            'selected_mode': ('selected_plus_default' if notify_mode == 'selected_plus_default' else 'selected_only'),
            'selected_targets': [],
            'extra_targets': [],
            'extra_success_count': 0,
            'extra_failed_count': 0
        }

        try:
            primary_dept_id, primary_dept_name = _xiaotu_pick_primary_department(user_id)
            dept_leader_user_id = _xiaotu_get_department_leader_user_id(primary_dept_id)
            uploader_uid = str(user_id or "").strip()
            is_uploader_leader = bool(dept_leader_user_id) and (uploader_uid == dept_leader_user_id)
            notify_detail['primary_department_id'] = primary_dept_id
            notify_detail['primary_department_name'] = primary_dept_name
            notify_detail['department_leader_user_id'] = dept_leader_user_id
            notify_detail['is_uploader_department_leader'] = is_uploader_leader

            extra_targets = []
            if selected_notify_open_ids:
                for oid in selected_notify_open_ids:
                    if oid and oid != uploader_uid:
                        extra_targets.append(oid)
                    notify_detail['selected_targets'].append({
                        'open_id': oid,
                        'name': selected_notify_name_map.get(oid, ''),
                        'is_self': bool(oid == uploader_uid)
                    })
                if notify_mode == "selected_plus_default":
                    if is_uploader_leader:
                        target_name = str(_XIAOTU_REPORT_ESCALATION_USER or '').strip()
                        if target_name and target_name != uploader_name:
                            escalation_open_id = _xiaotu_lookup_open_id_by_name(target_name)
                            if escalation_open_id:
                                extra_targets.append(escalation_open_id)
                            else:
                                notify_detail['extra_targets'].append({
                                    'name': target_name,
                                    'success': False,
                                    'message': '未找到升级通知人对应的open_id'
                                })
                                notify_detail['extra_failed_count'] += 1
                    else:
                        if dept_leader_user_id and dept_leader_user_id != uploader_uid:
                            extra_targets.append(dept_leader_user_id)
                        elif not dept_leader_user_id:
                            notify_detail['extra_targets'].append({
                                'name': 'missing_department_leader_user_id',
                                'success': False,
                                'message': '当前用户部门未获取到leader_user_id'
                            })
                            notify_detail['extra_failed_count'] += 1
            elif is_uploader_leader:
                target_name = str(_XIAOTU_REPORT_ESCALATION_USER or '').strip()
                if target_name and target_name != uploader_name:
                    escalation_open_id = _xiaotu_lookup_open_id_by_name(target_name)
                    if escalation_open_id:
                        extra_targets.append(escalation_open_id)
                    else:
                        notify_detail['extra_targets'].append({
                            'name': target_name,
                            'success': False,
                            'message': '未找到升级通知人对应的open_id'
                        })
                        notify_detail['extra_failed_count'] += 1
            else:
                if dept_leader_user_id and dept_leader_user_id != uploader_uid:
                    extra_targets.append(dept_leader_user_id)
                elif not dept_leader_user_id:
                    notify_detail['extra_targets'].append({
                        'name': 'missing_department_leader_user_id',
                        'success': False,
                        'message': '当前用户部门未获取到leader_user_id'
                    })
                    notify_detail['extra_failed_count'] += 1

            sent_seen = set()
            for target in extra_targets:
                target = str(target or "").strip()
                if not target or target in sent_seen:
                    continue
                sent_seen.add(target)
                ok = bool(_xiaotu_send_report_notification(
                    target,
                    "open_id",
                    title_text,
                    person_type,
                    pingjia_text,
                    doc_url=doc_url,
                    source_text=notify_source_text,
                    image_key=notify_image_key,
                    image_paths_text=image_paths_text,
                    wendangid=report_wendangid_raw,
                    comment_url=comment_url,
                    report_url=report_url,
                    org_impact_text=org_perf_contribution_text
                ))
                notify_detail['extra_targets'].append({'name': target, 'success': ok})
                if ok:
                    notify_detail['extra_success_count'] += 1
                else:
                    notify_detail['extra_failed_count'] += 1
        except Exception as notify_err:
            notify_detail['extra_targets'].append({'name': 'notify_error', 'success': False, 'message': str(notify_err)})
            notify_detail['extra_failed_count'] += 1

        cache_warning = ""
        try:
            _xiaotu_upsert_report_cache_notify(
                uploader_name,
                selected_notify_open_ids,
                selected_notify_targets,
                notify_time
            )
            _xiaotu_clear_report_cache_draft(uploader_name)
            if edit_wendangid:
                _xiaotu_clear_report_edit_ready_session(edit_wendangid)
        except Exception as cache_err:
            cache_warning = str(cache_err)

        return jsonify({
            'success': True,
            'message': ('已更新原日报记录并完成飞书推送' if edit_wendangid else '已提交到baogao并完成飞书推送'),
            'data': {
                'doc_id': doc_token or "",
                'report_id': report_wendangid_raw,
                'source_doc_token': source_doc_token,
                'doc_url': doc_url or "",
                'edit_wendangid': edit_wendangid,
                'title': title_text,
                'submitter_name': uploader_name,
                'report_kind': report_kind,
                'renyuanleixing': person_type,
                'image_count': len(image_paths),
                'image_paths': image_paths,
                'image_debug': image_debug,
                'daily_slice_debug': daily_slice_debug,
                'upload_image_debug': upload_debug,
                'inline_image_debug': inline_image_debug,
                'remote_image_debug': remote_image_debug,
                'pushed': bool(pushed),
                'notify_policy': notify_policy,
                'notify_time': notify_time,
                'notify_detail': notify_detail,
                'jieshouren': selected_notify_names,
                'pingjia': pingjia_text,
                'org_perf_matched': bool(org_perf_context),
                'org_perf_contribution': org_perf_contribution_text,
                'cache_cleared': (cache_warning == ""),
                'cache_warning': cache_warning
            }
        })
    except RequestEntityTooLarge:
        return jsonify({
            'success': False,
            'message': '提交内容过大，请压缩图片、减少粘贴图片数量，或分次提交后再试',
            'stage': stage
        }), 413
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'提交处理失败（阶段:{stage}）: {str(e)}',
            'stage': stage
        }), 500


@app.route('/api/xiaotu/report_history', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_history():
    try:
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401

        session_user_name = str(session.get('feishu_user_name') or '').strip()
        request_debug_mode = str(request.args.get('debug_scope_mode') or '').strip().lower()
        history_debug_enabled = bool(session_user_name == _XIAOTU_REPORT_HISTORY_DEBUG_USER)
        if request_debug_mode not in {"", "current", "self_only", "all_uploads", "operation_only"}:
            request_debug_mode = ""
        effective_debug_mode = request_debug_mode if history_debug_enabled else ""
        history_scope = _xiaotu_get_report_history_scope(session_user_name, debug_mode=effective_debug_mode)
        can_view_all_uploads = bool(history_scope.get('can_view_all_uploads'))
        restricted_to_allowed_departments = bool(history_scope.get('restricted_to_allowed_departments'))
        allowed_department_names = list(history_scope.get('allowed_department_names') or [])
        request_name = str(request.args.get('name') or '').strip()
        department_id = str(request.args.get('department_id') or '').strip()
        filter_name = str(request_name or session_user_name or '').strip()
        date_start = str(request.args.get('date_start') or '').strip()
        date_end = str(request.args.get('date_end') or '').strip()
        keyword = str(request.args.get('keyword') or '').strip()
        focus_wid = str(request.args.get('wendangid') or '').strip()
        page_size = 10
        try:
            uploaded_page = max(1, int(request.args.get('uploaded_page') or 1))
        except Exception:
            uploaded_page = 1
        try:
            received_page = max(1, int(request.args.get('received_page') or 1))
        except Exception:
            received_page = 1
        if department_id and not (department_id.startswith("od_") or department_id.startswith("od-")):
            return jsonify({'success': False, 'message': 'department_id格式无效'}), 400

        allowed_department_ids = set()
        if allowed_department_names:
            for one in (_xiaotu_list_notify_departments() or []):
                if not isinstance(one, dict):
                    continue
                dept_name = str(one.get("department_name") or "").strip()
                dept_id = str(one.get("department_id") or "").strip()
                if dept_name in allowed_department_names and dept_id:
                    allowed_department_ids.add(dept_id)
            if department_id and department_id not in allowed_department_ids:
                return jsonify({'success': True, 'data': {
                    'filters': {
                        'name': '',
                        'department_id': department_id,
                        'date_start': date_start,
                        'date_end': date_end,
                        'keyword': keyword,
                        'wendangid': focus_wid,
                    },
                    'permissions': {
                        'can_view_all_uploads': can_view_all_uploads,
                        'restricted_to_allowed_departments': restricted_to_allowed_departments,
                        'allowed_department_names': allowed_department_names,
                    },
                    'pagination': {
                        'uploaded': {'page': 1, 'page_size': page_size, 'total': 0, 'total_pages': 1},
                        'received': {'page': 1, 'page_size': page_size, 'total': 0, 'total_pages': 1},
                    },
                    'stats': {
                        'uploaded_total': 0,
                        'received_total': 0,
                        'uploaded_today': 0,
                        'received_today': 0,
                        'received_unique_senders': 0,
                    },
                    'uploaded': [],
                    'received': [],
                }})

        where_uploaded = ["1=1"]
        where_received = ["1=1"]
        uploaded_filter_name = filter_name
        if (can_view_all_uploads or restricted_to_allowed_departments) and not request_name:
            uploaded_filter_name = ''
        if uploaded_filter_name:
            esc_name = _xiaotu_sql_escape(uploaded_filter_name)
            where_uploaded.append(f"b.XingMing LIKE N'%%{esc_name}%%'")
        if filter_name:
            esc_name = _xiaotu_sql_escape(filter_name)
            where_received.append(f"b.JieShouRen LIKE N'%%{esc_name}%%'")
        if allowed_department_names:
            allowed_user_names = _xiaotu_collect_notify_user_names_by_department_names(allowed_department_names)
            own_name = str(session_user_name or "").strip()
            if own_name and own_name not in allowed_user_names:
                allowed_user_names.append(own_name)
            allowed_name_clause = _xiaotu_build_name_match_clause("b.XingMing", allowed_user_names)
            if allowed_name_clause:
                where_uploaded.append(allowed_name_clause)
                where_received.append(allowed_name_clause)
            else:
                where_uploaded.append("1=0")
                where_received.append("1=0")
        if department_id:
            department_users = _xiaotu_list_notify_users_current_app_cached(department_id)
            department_user_names = [str((one or {}).get("name") or "").strip() for one in department_users if isinstance(one, dict)]
            department_name_clause = _xiaotu_build_name_match_clause("b.XingMing", department_user_names)
            if department_name_clause:
                where_uploaded.append(department_name_clause)
                where_received.append(department_name_clause)
            else:
                where_uploaded.append("1=0")
                where_received.append("1=0")
        if focus_wid:
            esc_wid = _xiaotu_sql_escape(focus_wid)
            where_uploaded.append(f"b.WenDangID = '{esc_wid}'")
            where_received.append(f"b.WenDangID = '{esc_wid}'")
        if date_start:
            where_uploaded.append(f"b.RiQi >= '{_xiaotu_sql_escape(date_start)} 00:00:00'")
            where_received.append(f"b.RiQi >= '{_xiaotu_sql_escape(date_start)} 00:00:00'")
        if date_end:
            where_uploaded.append(f"b.RiQi <= '{_xiaotu_sql_escape(date_end)} 23:59:59'")
            where_received.append(f"b.RiQi <= '{_xiaotu_sql_escape(date_end)} 23:59:59'")
        if keyword:
            esc_kw = _xiaotu_sql_escape(keyword)
            keyword_clause = (
                "("
                f"b.BiaoTi LIKE N'%%{esc_kw}%%' OR "
                f"b.ZhengWen LIKE N'%%{esc_kw}%%' OR "
                f"b.TuPianNeiRong LIKE N'%%{esc_kw}%%' OR "
                f"b.PingJia LIKE N'%%{esc_kw}%%' OR "
                f"b.LeiXing LIKE N'%%{esc_kw}%%' OR "
                f"b.RenYuanLeiXing LIKE N'%%{esc_kw}%%'"
                ")"
            )
            where_uploaded.append(keyword_clause)
            where_received.append(keyword_clause)

        uploaded_where_sql = " AND ".join(where_uploaded)
        received_where_sql = " AND ".join(where_received)
        uploaded_offset = max(0, (uploaded_page - 1) * page_size)
        received_offset = max(0, (received_page - 1) * page_size)

        def _query_scalar_int(sql_text):
            raw = sf_db(sql_text)
            if isinstance(raw, list):
                raw = raw[0] if raw else {}
            if isinstance(raw, dict):
                for value in raw.values():
                    try:
                        return int(value or 0)
                    except Exception:
                        continue
                return 0
            if isinstance(raw, (list, tuple)):
                try:
                    return int(raw[0] if len(raw) > 0 else 0)
                except Exception:
                    return 0
            try:
                return int(raw or 0)
            except Exception:
                return 0

        uploaded_total = _query_scalar_int(
            f"SELECT COUNT(1) AS total_count FROM baogao b WHERE {uploaded_where_sql}"
        )
        received_total = _query_scalar_int(
            f"SELECT COUNT(1) AS total_count FROM baogao b WHERE {received_where_sql}"
        )
        uploaded_total_pages = max(1, (uploaded_total + page_size - 1) // page_size) if uploaded_total else 1
        received_total_pages = max(1, (received_total + page_size - 1) // page_size) if received_total else 1
        uploaded_page = min(uploaded_page, uploaded_total_pages)
        received_page = min(received_page, received_total_pages)
        uploaded_offset = max(0, (uploaded_page - 1) * page_size)
        received_offset = max(0, (received_page - 1) * page_size)

        sql_uploaded = f"""
            SELECT
                b.WenDangID,
                b.RiQi,
                b.XingMing,
                b.BiaoTi,
                b.ZhengWen,
                b.TuPianLujin,
                b.LeiXing,
                b.RenYuanLeiXing,
                b.JieShouRen,
                ISNULL(d.DianZan, '') AS DianZan,
                ISNULL(d.PingJia, '') AS PingLun,
                ISNULL(d.HuiFu, '') AS HuiFu,
                ISNULL(d.YongHu, '') AS YongHu
            FROM baogao b
            LEFT JOIN BaoGao_dianzan d ON d.WenDangID = b.WenDangID
            WHERE {uploaded_where_sql}
            ORDER BY b.RiQi DESC
            OFFSET {uploaded_offset} ROWS FETCH NEXT {page_size} ROWS ONLY
        """
        sql_received = f"""
            SELECT
                b.WenDangID,
                b.RiQi,
                b.XingMing,
                b.BiaoTi,
                b.ZhengWen,
                b.TuPianLujin,
                b.LeiXing,
                b.RenYuanLeiXing,
                b.JieShouRen,
                ISNULL(d.DianZan, '') AS DianZan,
                ISNULL(d.PingJia, '') AS PingLun,
                ISNULL(d.HuiFu, '') AS HuiFu,
                ISNULL(d.YongHu, '') AS YongHu
            FROM baogao b
            LEFT JOIN BaoGao_dianzan d ON d.WenDangID = b.WenDangID
            WHERE {received_where_sql}
            ORDER BY b.RiQi DESC
            OFFSET {received_offset} ROWS FETCH NEXT {page_size} ROWS ONLY
        """
        rows_uploaded = sf_db(sql_uploaded) or []
        rows_received = sf_db(sql_received) or []

        def _norm_rows(rows):
            out = []
            if not isinstance(rows, list):
                rows = [rows]
            for row in rows:
                if isinstance(row, dict):
                    wid = str(row.get('WenDangID') or '').strip()
                    one = {
                        'wendangid': wid,
                        'source_doc_token': _xiaotu_extract_source_doc_token(wid),
                        'riqi': str(row.get('RiQi') or '').strip(),
                        'xingming': str(row.get('XingMing') or '').strip(),
                        'biaoti': str(row.get('BiaoTi') or '').strip(),
                        'zhengwen': str(row.get('ZhengWen') or '').strip(),
                        'tupianlujin': str(row.get('TuPianLujin') or '').strip(),
                        'leixing': str(row.get('LeiXing') or '').strip(),
                        'renyuanleixing': str(row.get('RenYuanLeiXing') or '').strip(),
                        'jieshouren': str(row.get('JieShouRen') or '').strip(),
                        'dianzan': str(row.get('DianZan') or row.get('dianzan') or '').strip(),
                        'pinglun': str(row.get('PingLun') or row.get('pinglun') or '').strip(),
                        'huifu': str(row.get('HuiFu') or row.get('huifu') or '').strip(),
                        'yonghu': str(row.get('YongHu') or row.get('yonghu') or '').strip(),
                        'report_url': _xiaotu_build_report_history_url(wid),
                    }
                else:
                    values = list(row) if isinstance(row, (list, tuple)) else []
                    wid = str(values[0] if len(values) > 0 else '').strip()
                    one = {
                        'wendangid': wid,
                        'source_doc_token': _xiaotu_extract_source_doc_token(wid),
                        'riqi': str(values[1] if len(values) > 1 else '').strip(),
                        'xingming': str(values[2] if len(values) > 2 else '').strip(),
                        'biaoti': str(values[3] if len(values) > 3 else '').strip(),
                        'zhengwen': str(values[4] if len(values) > 4 else '').strip(),
                        'tupianlujin': str(values[5] if len(values) > 5 else '').strip(),
                        'leixing': str(values[6] if len(values) > 6 else '').strip(),
                        'renyuanleixing': str(values[7] if len(values) > 7 else '').strip(),
                        'jieshouren': str(values[8] if len(values) > 8 else '').strip(),
                        'dianzan': str(values[9] if len(values) > 9 else '').strip(),
                        'pinglun': str(values[10] if len(values) > 10 else '').strip(),
                        'huifu': str(values[11] if len(values) > 11 else '').strip(),
                        'yonghu': str(values[12] if len(values) > 12 else '').strip(),
                        'report_url': _xiaotu_build_report_history_url(wid),
                    }
                one.update(_xiaotu_enrich_feedback_data(one, owner_name=one.get('xingming')))
                out.append(one)
            return out

        uploaded = _norm_rows(rows_uploaded)
        received = _norm_rows(rows_received)

        today_s = datetime.now().strftime('%Y-%m-%d')
        stats = {
            'uploaded_total': uploaded_total,
            'received_total': received_total,
            'uploaded_today': _query_scalar_int(
                f"SELECT COUNT(1) AS total_count FROM baogao b WHERE {uploaded_where_sql} AND CONVERT(varchar(10), b.RiQi, 23) = '{today_s}'"
            ),
            'received_today': _query_scalar_int(
                f"SELECT COUNT(1) AS total_count FROM baogao b WHERE {received_where_sql} AND CONVERT(varchar(10), b.RiQi, 23) = '{today_s}'"
            ),
            'received_unique_senders': _query_scalar_int(
                f"SELECT COUNT(DISTINCT ISNULL(NULLIF(LTRIM(RTRIM(b.XingMing)), ''), '')) AS total_count FROM baogao b WHERE {received_where_sql}"
            ),
        }
        return jsonify({
            'success': True,
            'data': {
                'filters': {
                    'name': uploaded_filter_name if can_view_all_uploads else filter_name,
                    'department_id': department_id,
                    'date_start': date_start,
                    'date_end': date_end,
                    'keyword': keyword,
                    'wendangid': focus_wid,
                },
                'permissions': {
                    'can_view_all_uploads': can_view_all_uploads,
                    'restricted_to_allowed_departments': restricted_to_allowed_departments,
                    'allowed_department_names': allowed_department_names,
                    'debug_scope_mode': str(history_scope.get('debug_mode') or 'current'),
                    'debug_enabled': history_debug_enabled,
                },
                'pagination': {
                    'uploaded': {
                        'page': min(uploaded_page, uploaded_total_pages),
                        'page_size': page_size,
                        'total': uploaded_total,
                        'total_pages': uploaded_total_pages,
                    },
                    'received': {
                        'page': min(received_page, received_total_pages),
                        'page_size': page_size,
                        'total': received_total,
                        'total_pages': received_total_pages,
                    }
                },
                'stats': stats,
                'uploaded': uploaded,
                'received': received,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取历史失败: {str(e)}'}), 500


def _xiaotu_build_report_history_export_context(args, session_user_name):
    request_debug_mode = str(args.get('debug_scope_mode') or '').strip().lower()
    history_debug_enabled = bool(session_user_name == _XIAOTU_REPORT_HISTORY_DEBUG_USER)
    if request_debug_mode not in {"", "current", "self_only", "all_uploads", "operation_only"}:
        request_debug_mode = ""
    effective_debug_mode = request_debug_mode if history_debug_enabled else ""
    history_scope = _xiaotu_get_report_history_scope(session_user_name, debug_mode=effective_debug_mode)
    can_view_all_uploads = bool(history_scope.get('can_view_all_uploads'))
    restricted_to_allowed_departments = bool(history_scope.get('restricted_to_allowed_departments'))
    allowed_department_names = list(history_scope.get('allowed_department_names') or [])
    request_name = str(args.get('name') or '').strip()
    department_id = str(args.get('department_id') or '').strip()
    filter_name = str(request_name or session_user_name or '').strip()
    date_start = str(args.get('date_start') or '').strip()
    date_end = str(args.get('date_end') or '').strip()
    keyword = str(args.get('keyword') or '').strip()
    focus_wid = str(args.get('wendangid') or '').strip()
    if department_id and not (department_id.startswith("od_") or department_id.startswith("od-")):
        raise ValueError("department_id格式无效")

    where_uploaded = ["1=1"]
    where_received = ["1=1"]

    allowed_department_ids = set()
    if allowed_department_names:
        for one in (_xiaotu_list_notify_departments() or []):
            if not isinstance(one, dict):
                continue
            dept_name = str(one.get("department_name") or "").strip()
            dept_id = str(one.get("department_id") or "").strip()
            if dept_name in allowed_department_names and dept_id:
                allowed_department_ids.add(dept_id)
        if department_id and department_id not in allowed_department_ids:
            where_uploaded.append("1=0")
            where_received.append("1=0")

    uploaded_filter_name = filter_name
    if (can_view_all_uploads or restricted_to_allowed_departments) and not request_name:
        uploaded_filter_name = ''
    if uploaded_filter_name:
        esc_name = _xiaotu_sql_escape(uploaded_filter_name)
        where_uploaded.append(f"b.XingMing LIKE N'%%{esc_name}%%'")
    if filter_name:
        esc_name = _xiaotu_sql_escape(filter_name)
        where_received.append(f"b.JieShouRen LIKE N'%%{esc_name}%%'")

    if allowed_department_names:
        allowed_user_names = _xiaotu_collect_notify_user_names_by_department_names(allowed_department_names)
        own_name = str(session_user_name or "").strip()
        if own_name and own_name not in allowed_user_names:
            allowed_user_names.append(own_name)
        allowed_name_clause = _xiaotu_build_name_match_clause("b.XingMing", allowed_user_names)
        if allowed_name_clause:
            where_uploaded.append(allowed_name_clause)
            where_received.append(allowed_name_clause)
        else:
            where_uploaded.append("1=0")
            where_received.append("1=0")

    if department_id:
        department_users = _xiaotu_list_notify_users_current_app_cached(department_id)
        department_user_names = [
            str((one or {}).get("name") or "").strip()
            for one in department_users
            if isinstance(one, dict)
        ]
        department_name_clause = _xiaotu_build_name_match_clause("b.XingMing", department_user_names)
        if department_name_clause:
            where_uploaded.append(department_name_clause)
            where_received.append(department_name_clause)
        else:
            where_uploaded.append("1=0")
            where_received.append("1=0")

    if focus_wid:
        esc_wid = _xiaotu_sql_escape(focus_wid)
        where_uploaded.append(f"b.WenDangID = '{esc_wid}'")
        where_received.append(f"b.WenDangID = '{esc_wid}'")
    if date_start:
        where_uploaded.append(f"b.RiQi >= '{_xiaotu_sql_escape(date_start)} 00:00:00'")
        where_received.append(f"b.RiQi >= '{_xiaotu_sql_escape(date_start)} 00:00:00'")
    if date_end:
        where_uploaded.append(f"b.RiQi <= '{_xiaotu_sql_escape(date_end)} 23:59:59'")
        where_received.append(f"b.RiQi <= '{_xiaotu_sql_escape(date_end)} 23:59:59'")
    if keyword:
        esc_kw = _xiaotu_sql_escape(keyword)
        keyword_clause = (
            "("
            f"b.BiaoTi LIKE N'%%{esc_kw}%%' OR "
            f"b.ZhengWen LIKE N'%%{esc_kw}%%' OR "
            f"b.TuPianNeiRong LIKE N'%%{esc_kw}%%' OR "
            f"b.PingJia LIKE N'%%{esc_kw}%%' OR "
            f"b.LeiXing LIKE N'%%{esc_kw}%%' OR "
            f"b.RenYuanLeiXing LIKE N'%%{esc_kw}%%'"
            ")"
        )
        where_uploaded.append(keyword_clause)
        where_received.append(keyword_clause)

    return {
        "uploaded_where_sql": " AND ".join(where_uploaded),
        "received_where_sql": " AND ".join(where_received),
        "date_start": date_start,
        "date_end": date_end,
        "keyword": keyword,
        "name": uploaded_filter_name if can_view_all_uploads else filter_name,
        "department_id": department_id,
        "debug_scope_mode": str(history_scope.get('debug_mode') or 'current'),
        "can_view_all_uploads": can_view_all_uploads,
        "restricted_to_allowed_departments": restricted_to_allowed_departments,
        "allowed_department_names": allowed_department_names,
    }


def _xiaotu_history_export_value(row, key, index):
    if isinstance(row, dict):
        if key in row:
            return row.get(key)
        return row.get(key.lower())
    values = list(row) if isinstance(row, (list, tuple)) else []
    return values[index] if index < len(values) else ""


def _xiaotu_history_export_image_data_uri(source, image_cache=None):
    raw = html_unescape(str(source or "").strip()).strip().strip('"').strip("'")
    if not raw:
        return ""
    if re.match(r"^data:image/(?:png|jpe?g|gif|webp|bmp);base64,", raw, flags=re.IGNORECASE):
        return raw

    parsed = urlparse(raw)
    if parsed.path == "/api/xiaotu/report_image":
        nested_paths = parse_qs(parsed.query or "").get("path") or []
        raw = str(nested_paths[0] if nested_paths else "").strip()
    elif parsed.scheme in {"http", "https"}:
        return ""
    raw = unquote(raw).strip().strip('"').strip("'")
    if not raw:
        return ""

    allowed_base_dirs = [
        os.path.abspath(r"D:\tuchuangai\报告图片"),
        os.path.abspath(r"D:\tuchuangai\报告缓存图片"),
    ]
    normalized = str(relocate_storage_path(raw) or "").replace("/", os.sep)
    if not normalized:
        return ""
    if not os.path.isabs(normalized):
        normalized = os.path.join(allowed_base_dirs[0], normalized.lstrip("\\/"))
    abs_path = os.path.abspath(normalized)
    allowed = False
    for base_dir in allowed_base_dirs:
        try:
            if os.path.commonpath([base_dir, abs_path]) == base_dir:
                allowed = True
                break
        except Exception:
            continue
    if not allowed or not os.path.isfile(abs_path):
        return ""
    if os.path.splitext(abs_path)[1].lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return ""

    cache = image_cache if isinstance(image_cache, dict) else {}
    if abs_path in cache:
        return cache[abs_path]
    mime = mimetypes.guess_type(abs_path)[0] or ""
    if not mime.startswith("image/"):
        return ""
    with open(abs_path, "rb") as image_file:
        image_bytes = image_file.read()
    if not image_bytes:
        return ""
    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    cache[abs_path] = data_uri
    return data_uri


def _xiaotu_history_export_body_html(raw_body, image_paths_text, image_cache=None):
    body_text = str(raw_body or "").strip()
    if body_text and not re.search(r"<[A-Za-z][^>]*>", body_text):
        body_text = "<p>" + html_escape(body_text).replace("\n", "<br>") + "</p>"
    html = _xiaotu_normalize_report_html_body(body_text, image_paths_text)
    html = re.sub(
        r"<\s*(script|style|iframe|object|embed|form|meta|link|base)\b[^>]*>[\s\S]*?<\s*/\s*\1\s*>",
        "",
        html,
        flags=re.IGNORECASE,
    )
    html = re.sub(r"<\s*(?:script|style|iframe|object|embed|form|meta|link|base)\b[^>]*?/?>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\s+on[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\s+style\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\s+href\s*=\s*([\"'])\s*javascript:[^\"']*\1", "", html, flags=re.IGNORECASE)

    embedded_count = 0
    missing_count = 0

    def replace_image_tag(match):
        nonlocal embedded_count, missing_count
        tag = str(match.group(0) or "")
        src_match = re.search(r"\bsrc\s*=\s*([\"'])([^\"']+)\1", tag, flags=re.IGNORECASE)
        src = html_unescape(str(src_match.group(2) if src_match else "").strip())
        data_uri = _xiaotu_history_export_image_data_uri(src, image_cache=image_cache)
        alt_match = re.search(r"\balt\s*=\s*([\"'])([^\"']*)\1", tag, flags=re.IGNORECASE)
        alt_text = html_unescape(str(alt_match.group(2) if alt_match else "日报图片").strip()) or "日报图片"
        if not data_uri:
            missing_count += 1
            return f'<span class="image-missing">[{html_escape(alt_text)}暂不可用]</span>'
        embedded_count += 1
        return f'<img src="{html_escape(data_uri, quote=True)}" alt="{html_escape(alt_text, quote=True)}">'

    html = re.sub(r"<img\b[^>]*>", replace_image_tag, html, flags=re.IGNORECASE)
    return html, embedded_count, missing_count


def _xiaotu_history_export_optional_detail(label, value):
    text = _xiaotu_html_to_plain_text_preserve_blocks(value)
    if not text:
        return ""
    return (
        '<details class="record-detail">'
        f'<summary>{html_escape(label)}</summary>'
        f'<pre>{html_escape(text)}</pre>'
        '</details>'
    )


def _xiaotu_history_export_section_html(rows, source_label, image_cache=None):
    normalized_rows = rows if isinstance(rows, list) else [rows]
    cards = []
    embedded_total = 0
    missing_total = 0
    for index, row in enumerate(normalized_rows, start=1):
        value = lambda key, position: _xiaotu_history_export_value(row, key, position)
        body_html, embedded_count, missing_count = _xiaotu_history_export_body_html(
            value("ZhengWen", 4),
            value("TuPianLujin", 5),
            image_cache=image_cache,
        )
        embedded_total += embedded_count
        missing_total += missing_count
        title = _xiaotu_html_to_plain_text_preserve_blocks(value("BiaoTi", 3)) or "未命名日报"
        wid = str(value("WenDangID", 0) or "").strip()
        report_type = str(value("LeiXing", 7) or "-").strip() or "-"
        person_type = str(value("RenYuanLeiXing", 8) or "-").strip() or "-"
        cards.append(f"""
        <article class="report-record">
          <div class="record-topline">
            <span class="record-index">#{index}</span>
            <time>{html_escape(str(value("RiQi", 1) or "").strip())}</time>
            <span class="tag">{html_escape(report_type)}</span>
            <span class="tag">{html_escape(person_type)}</span>
          </div>
          <h2>{html_escape(title)}</h2>
          <dl class="record-meta">
            <div><dt>提报人</dt><dd>{html_escape(str(value("XingMing", 2) or "-").strip() or "-")}</dd></div>
            <div><dt>接收人</dt><dd>{html_escape(str(value("JieShouRen", 9) or "-").strip() or "-")}</dd></div>
            <div><dt>日报 ID</dt><dd>{html_escape(wid or "-")}</dd></div>
            <div><dt>点赞状态</dt><dd>{html_escape(str(value("DianZan", 11) or "未点赞").strip() or "未点赞")}</dd></div>
          </dl>
          <div class="record-body">{body_html}</div>
          <div class="record-details">
            {_xiaotu_history_export_optional_detail("图片识别内容", value("TuPianNeiRong", 6))}
            {_xiaotu_history_export_optional_detail("AI 评价", value("PingJia", 10))}
            {_xiaotu_history_export_optional_detail("评论", value("PingLun", 12))}
            {_xiaotu_history_export_optional_detail("回复", value("HuiFu", 13))}
          </div>
        </article>
        """)
    empty_html = '<div class="empty-state">暂无记录</div>'
    section_html = f"""
    <section class="report-section">
      <div class="section-heading"><h1>{html_escape(source_label)}</h1><span>{len(normalized_rows)} 条</span></div>
      {''.join(cards) if cards else empty_html}
    </section>
    """
    return section_html, embedded_total, missing_total


def _xiaotu_build_history_export_html(session_user_name, ctx, rows_uploaded, rows_received):
    image_cache = {}
    uploaded_html, uploaded_images, uploaded_missing = _xiaotu_history_export_section_html(
        rows_uploaded, "提报记录", image_cache=image_cache
    )
    received_html, received_images, received_missing = _xiaotu_history_export_section_html(
        rows_received, "收到记录", image_cache=image_cache
    )
    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    start_date = str(ctx.get("date_start") or "未限制")
    end_date = str(ctx.get("date_end") or "未限制")
    filter_name = str(ctx.get("name") or "未限制")
    keyword = str(ctx.get("keyword") or "未限制")
    embedded_total = uploaded_images + received_images
    missing_total = uploaded_missing + received_missing
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
  <title>报告历史记录 {html_escape(start_date)} 至 {html_escape(end_date)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f4f6f8; color: #172033; font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif; }}
    .page {{ width: min(1120px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 56px; }}
    .export-header {{ padding: 22px; border: 1px solid #dfe4ea; background: #fff; }}
    .export-header h1 {{ margin: 0 0 14px; font-size: 24px; }}
    .export-meta {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 18px; color: #5e6878; font-size: 13px; line-height: 1.6; }}
    .export-meta strong {{ color: #273244; }}
    .report-section {{ margin-top: 22px; }}
    .section-heading {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 10px; }}
    .section-heading h1 {{ margin: 0; font-size: 20px; }}
    .section-heading span {{ color: #687386; font-size: 13px; }}
    .report-record {{ margin-top: 10px; padding: 20px; border: 1px solid #dfe4ea; background: #fff; break-inside: avoid; }}
    .record-topline {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; color: #687386; font-size: 12px; }}
    .record-index {{ color: #2563eb; font-weight: 800; }}
    .tag {{ padding: 3px 7px; border: 1px solid #d9e0e8; background: #f7f9fb; color: #465267; }}
    .report-record h2 {{ margin: 12px 0; font-size: 19px; overflow-wrap: anywhere; }}
    .record-meta {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 0 0 16px; padding: 12px; background: #f7f9fb; }}
    .record-meta div {{ min-width: 0; }}
    .record-meta dt {{ color: #758094; font-size: 11px; }}
    .record-meta dd {{ margin: 4px 0 0; color: #303b4d; font-size: 12px; overflow-wrap: anywhere; }}
    .record-body {{ font-size: 14px; line-height: 1.8; overflow-wrap: anywhere; }}
    .record-body img {{ display: block; max-width: 100%; height: auto; margin: 14px 0; border: 1px solid #e1e6ec; }}
    .record-body figure {{ margin: 14px 0; }}
    .record-body figcaption {{ color: #758094; font-size: 12px; }}
    .image-missing {{ display: inline-block; margin: 8px 0; color: #a13d45; font-size: 12px; }}
    .record-details {{ display: grid; gap: 8px; margin-top: 14px; }}
    .record-detail {{ border-top: 1px solid #e6eaf0; padding-top: 8px; }}
    .record-detail summary {{ cursor: pointer; color: #465267; font-size: 13px; font-weight: 700; }}
    .record-detail pre {{ margin: 8px 0 0; padding: 12px; background: #f7f9fb; color: #364154; font: inherit; font-size: 12px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .empty-state {{ padding: 32px; border: 1px solid #dfe4ea; background: #fff; color: #758094; text-align: center; }}
    @media (max-width: 760px) {{ .export-meta, .record-meta {{ grid-template-columns: 1fr 1fr; }} }}
    @media print {{ body {{ background: #fff; }} .page {{ width: 100%; padding: 0; }} .report-record, .export-header {{ border-color: #bbb; }} }}
  </style>
</head>
<body>
  <main class="page">
    <header class="export-header">
      <h1>报告历史记录</h1>
      <div class="export-meta">
        <span><strong>导出人：</strong>{html_escape(session_user_name or "-")}</span>
        <span><strong>导出时间：</strong>{html_escape(generated_at)}</span>
        <span><strong>日期范围：</strong>{html_escape(start_date)} 至 {html_escape(end_date)}</span>
        <span><strong>姓名筛选：</strong>{html_escape(filter_name)}</span>
        <span><strong>关键词：</strong>{html_escape(keyword)}</span>
        <span><strong>内嵌图片：</strong>{embedded_total} 张{f'，{missing_total} 张不可用' if missing_total else ''}</span>
      </div>
    </header>
    {uploaded_html}
    {received_html}
  </main>
</body>
</html>"""


@app.route('/api/xiaotu/report_history_download', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_history_download():
    try:
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        session_user_name = str(session.get('feishu_user_name') or '').strip()
        ctx = _xiaotu_build_report_history_export_context(request.args, session_user_name)
        export_limit = 20000
        select_columns = """
            b.WenDangID,
            b.RiQi,
            b.XingMing,
            b.BiaoTi,
            b.ZhengWen,
            b.TuPianLujin,
            b.TuPianNeiRong,
            b.LeiXing,
            b.RenYuanLeiXing,
            b.JieShouRen,
            b.PingJia,
            ISNULL(d.DianZan, '') AS DianZan,
            ISNULL(d.PingJia, '') AS PingLun,
            ISNULL(d.HuiFu, '') AS HuiFu,
            ISNULL(d.YongHu, '') AS YongHu
        """
        sql_uploaded = f"""
            SELECT TOP {export_limit}
                {select_columns}
            FROM baogao b
            LEFT JOIN BaoGao_dianzan d ON d.WenDangID = b.WenDangID
            WHERE {ctx['uploaded_where_sql']}
            ORDER BY b.RiQi DESC
        """
        sql_received = f"""
            SELECT TOP {export_limit}
                {select_columns}
            FROM baogao b
            LEFT JOIN BaoGao_dianzan d ON d.WenDangID = b.WenDangID
            WHERE {ctx['received_where_sql']}
            ORDER BY b.RiQi DESC
        """
        rows_uploaded = sf_db(sql_uploaded) or []
        rows_received = sf_db(sql_received) or []
        from io import BytesIO
        html_text = _xiaotu_build_history_export_html(
            session_user_name,
            ctx,
            rows_uploaded,
            rows_received,
        )
        output = BytesIO(html_text.encode("utf-8"))
        output.seek(0)
        start_label = re.sub(r"[^0-9]", "", str(ctx.get("date_start") or "")) or "全部"
        end_label = re.sub(r"[^0-9]", "", str(ctx.get("date_end") or "")) or "全部"
        now_label = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"报告历史记录_{start_label}_to_{end_label}_{now_label}.html"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='text/html; charset=utf-8'
        )
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'下载历史记录失败: {str(e)}'}), 500


@app.route('/api/xiaotu/report_feedback', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_feedback():
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        actor_name = str(session.get('feishu_user_name') or '匿名用户').strip() or '匿名用户'
        payload = request.get_json(silent=True) if request.is_json else request.form
        payload = payload if isinstance(payload, dict) else {}
        action_name = str(payload.get('action') or '').strip().lower()
        wendangid = str(payload.get('wendangid') or '').strip()
        comment_text = str(payload.get('comment_text') or '').strip()
        target_name = str(payload.get('target_name') or '').strip()
        item_index = payload.get('item_index')
        try:
            _feishu_recent_events.append({
                'ts': datetime.now().isoformat(timespec="seconds"),
                'stage': 'report_feedback_api_enter',
                'action': action_name,
                'wendangid': wendangid,
                'actor_name': actor_name,
                'target_name': target_name,
                'text_preview': comment_text[:80]
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
        if not wendangid:
            return jsonify({'success': False, 'message': '缺少文档ID'}), 400
        if action_name == 'like':
            ok, err, liked_now = _xiaotu_toggle_report_like(wendangid, actor_name)
            if not ok:
                return jsonify({'success': False, 'message': err or '点赞失败'}), 500
            if liked_now:
                _xiaotu_notify_report_owner_feedback(wendangid, 'like_report', actor_name, '')
        elif action_name == 'comment':
            if not comment_text:
                return jsonify({'success': False, 'message': '评论不能为空'}), 400
            ok, err = _xiaotu_append_report_comment(wendangid, actor_name, comment_text)
            if not ok:
                return jsonify({'success': False, 'message': err or '评论失败'}), 500
            _xiaotu_notify_report_owner_feedback(wendangid, 'comment_report', actor_name, comment_text)
        elif action_name == 'remove_comment':
            ok, err = _xiaotu_remove_report_feedback_entry(wendangid, actor_name, "comment", item_index)
            if not ok:
                return jsonify({'success': False, 'message': err or '撤销评论失败'}), 500
        elif action_name == 'reply':
            if not comment_text:
                return jsonify({'success': False, 'message': '回复内容不能为空'}), 400
            ok, err = _xiaotu_append_report_reply(wendangid, actor_name, comment_text, target_name)
            if not ok:
                return jsonify({'success': False, 'message': err or '回复失败'}), 500
            _xiaotu_notify_report_owner_feedback(wendangid, 'reply_report', actor_name, comment_text, target_name)
            _xiaotu_notify_feedback_reply_target(wendangid, actor_name, target_name, comment_text)
        elif action_name == 'remove_reply':
            ok, err = _xiaotu_remove_report_feedback_entry(wendangid, actor_name, "reply", item_index)
            if not ok:
                return jsonify({'success': False, 'message': err or '撤销回复失败'}), 500
        else:
            return jsonify({'success': False, 'message': '不支持的操作'}), 400
        owner_name = str((_xiaotu_get_report_card_context(wendangid) or {}).get('owner_name') or '').strip()
        feedback = _xiaotu_get_report_feedback(wendangid, owner_name=owner_name)
        try:
            _feishu_recent_events.append({
                'ts': datetime.now().isoformat(timespec="seconds"),
                'stage': 'report_feedback_api_success',
                'action': action_name,
                'wendangid': wendangid
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
        return jsonify({
            'success': True,
            'message': '操作成功',
            'data': {
                'wendangid': wendangid,
                'feedback': {
                    'dianzan': str((feedback or {}).get('dianzan') or '').strip(),
                    'pinglun': str((feedback or {}).get('pinglun') or '').strip(),
                    'huifu': str((feedback or {}).get('huifu') or '').strip(),
                    'yonghu': str((feedback or {}).get('yonghu') or '').strip(),
                    'like_users': list((feedback or {}).get('like_users') or []),
                    'like_count': int((feedback or {}).get('like_count') or 0),
                    'comment_items': list((feedback or {}).get('comment_items') or []),
                    'reply_items': list((feedback or {}).get('reply_items') or []),
                    'reply_targets': list((feedback or {}).get('reply_targets') or []),
                }
            }
        })
    except Exception as e:
        try:
            _feishu_recent_events.append({
                'ts': datetime.now().isoformat(timespec="seconds"),
                'stage': 'report_feedback_api_error',
                'error': str(e)
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
        return jsonify({'success': False, 'message': f'反馈失败: {str(e)}'}), 500


@app.route('/api/xiaotu/report_image', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_image():
    try:
        raw_path = str(request.args.get('path') or '').strip()
        if not raw_path:
            return jsonify({'success': False, 'message': '缺少图片路径'}), 400
        allowed_base_dirs = [
            os.path.abspath(r"D:\tuchuangai\报告图片"),
            os.path.abspath(r"D:\tuchuangai\报告缓存图片")
        ]
        base_dir = allowed_base_dirs[0]
        normalized = unquote(raw_path).strip().strip('"').strip("'")
        if normalized.startswith('/api/xiaotu/report_image'):
            parsed = urlparse(normalized)
            nested_path = parse_qs(parsed.query).get('path') or []
            normalized = str(nested_path[0] if nested_path else '').strip()
            normalized = unquote(normalized).strip().strip('"').strip("'")
        normalized = relocate_storage_path(normalized).replace('/', os.sep)
        if normalized and not os.path.isabs(normalized):
            normalized = os.path.join(base_dir, normalized.lstrip("\\/"))
        abs_path = os.path.abspath(normalized)
        allowed = False
        for one_base in allowed_base_dirs:
            try:
                if os.path.commonpath([one_base, abs_path]) == one_base:
                    allowed = True
                    break
            except Exception:
                continue
        if not allowed:
            return jsonify({'success': False, 'message': '图片路径不在允许目录内'}), 403
        if not os.path.isfile(abs_path):
            return jsonify({'success': False, 'message': '图片文件不存在'}), 404
        ext = os.path.splitext(abs_path)[1].lower()
        if ext not in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}:
            return jsonify({'success': False, 'message': '不支持的图片类型'}), 400
        return send_file(abs_path, as_attachment=False, conditional=True)
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取图片失败: {str(e)}'}), 500


@app.route('/api/xiaotu/report_history_analysis_file', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_history_analysis_file():
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        user_name = str(session.get('feishu_user_name') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        if not user_name:
            return jsonify({'success': False, 'message': '未获取到当前飞书用户名'}), 400
        raw_path = str(request.args.get('path') or '').strip()
        if not raw_path:
            return jsonify({'success': False, 'message': '缺少文件路径'}), 400
        normalized = relocate_storage_path(unquote(raw_path).strip().strip('"').strip("'"))
        abs_path = os.path.abspath(normalized)
        base = os.path.abspath(_XIAOTU_REPORT_HISTORY_ANALYSIS_DIR)
        if os.path.commonpath([base, abs_path]) != base:
            return jsonify({'success': False, 'message': '文件路径不在允许目录内'}), 403
        if not os.path.isfile(abs_path):
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        if os.path.splitext(abs_path)[1].lower() != ".html":
            return jsonify({'success': False, 'message': '只支持HTML文件'}), 400
        visible_scope = _xiaotu_get_history_analysis_visible_user_names(user_id, user_name)
        visible_name_clause = _xiaotu_build_name_scope_clause(
            "YongHu",
            list(visible_scope.get("user_names") or [user_name])
        )
        if not visible_name_clause:
            visible_name_clause = f"YongHu = N'{_xiaotu_sql_escape(user_name)}'"
        esc_path = _xiaotu_sql_escape(abs_path)
        matched_rows = sf_db(f"""
            SELECT TOP 1 ID
            FROM baogao_lishi
            WHERE WeiZhi = N'{esc_path}'
              AND {visible_name_clause}
        """) or []
        if not matched_rows:
            return jsonify({'success': False, 'message': '无权查看该报告历史文件'}), 403
        return send_file(abs_path, as_attachment=False, conditional=True)
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取历史分析文件失败: {str(e)}'}), 500


@app.route('/api/xiaotu/report_history_analysis_list', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_history_analysis_list():
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        user_name = str(session.get('feishu_user_name') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        if not user_name:
            return jsonify({'success': False, 'message': '未获取到当前飞书用户名'}), 400
        visible_scope = _xiaotu_get_history_analysis_visible_user_names(user_id, user_name)
        visible_name_clause = _xiaotu_build_name_scope_clause(
            "YongHu",
            list(visible_scope.get("user_names") or [user_name])
        )
        if not visible_name_clause:
            visible_name_clause = f"YongHu = N'{_xiaotu_sql_escape(user_name)}'"
        rows = sf_db(f"""
            SELECT TOP 100 ID, YongHu, KaiShiRiQi, JieShuRIQi, WeiZhi
            FROM baogao_lishi
            WHERE {visible_name_clause}
            ORDER BY ID DESC
        """) or []
        items = []
        for row in rows:
            if isinstance(row, dict):
                rid = row.get("ID") or row.get("id")
                yonghu = row.get("YongHu") or row.get("yonghu")
                start_date = row.get("KaiShiRiQi") or row.get("kaishiriqi")
                end_date = row.get("JieShuRIQi") or row.get("jieshuriqi")
                path = row.get("WeiZhi") or row.get("weizhi")
            else:
                values = list(row) if isinstance(row, (list, tuple)) else []
                rid = values[0] if len(values) > 0 else ""
                yonghu = values[1] if len(values) > 1 else ""
                start_date = values[2] if len(values) > 2 else ""
                end_date = values[3] if len(values) > 3 else ""
                path = values[4] if len(values) > 4 else ""
            path_text = relocate_storage_path(path)
            exists = bool(path_text and os.path.isfile(path_text))
            items.append({
                "id": str(rid or "").strip(),
                "user_name": str(yonghu or "").strip(),
                "start_date": str(start_date or "").strip()[:10],
                "end_date": str(end_date or "").strip()[:10],
                "file_path": path_text,
                "file_url": url_for('api_xiaotu_report_history_analysis_file', path=path_text) if exists else "",
                "exists": exists,
            })
        return jsonify({
            'success': True,
            'data': {
                'user_name': user_name,
                'permissions': {
                    'is_department_leader': bool(visible_scope.get('is_department_leader')),
                    'department_names': list(visible_scope.get('department_names') or []),
                },
                'items': items,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取报告历史记录失败: {str(e)}'}), 500


@app.route('/api/xiaotu/knowledge_search', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_knowledge_search():
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        user_name = str(session.get('feishu_user_name') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        if not user_name:
            return jsonify({'success': False, 'message': '未获取到当前飞书用户名'}), 400

        data = request.get_json(silent=True) or {}
        question = str(data.get('question') or '').strip()
        if not question:
            return jsonify({'success': False, 'message': '请输入要搜索的问题'}), 400

        esc_user_name = _xiaotu_sql_escape(user_name)
        sql_text = f"""
            SELECT TOP 400 RiQi, BiaoTi, ZhengWen, TuPianNeiRong
            FROM baogao
            WHERE XingMing = N'{esc_user_name}'
            ORDER BY RiQi DESC
        """
        rows = sf_db(sql_text) or []
        if not rows:
            return jsonify({'success': False, 'message': '你还没有提交过可供搜索的日志'}), 404

        norm_rows = []
        for idx, row in enumerate(rows):
            if isinstance(row, dict):
                riqi = row.get('RiQi')
                biaoti = row.get('BiaoTi')
                zhengwen = row.get('ZhengWen')
                tupianneirong = row.get('TuPianNeiRong')
            else:
                values = list(row) if isinstance(row, (list, tuple)) else []
                riqi = values[0] if len(values) > 0 else ""
                biaoti = values[1] if len(values) > 1 else ""
                zhengwen = values[2] if len(values) > 2 else ""
                tupianneirong = values[3] if len(values) > 3 else ""
            norm_rows.append({
                'order_index': idx,
                'riqi': str(riqi or '').strip(),
                'biaoti': str(biaoti or '').strip(),
                'zhengwen': str(zhengwen or '').strip(),
                'tupianneirong': str(tupianneirong or '').strip(),
            })

        q_lower = question.lower()
        q_joined = re.sub(r"\s+", "", q_lower)
        terms = _xiaotu_extract_knowledge_terms(question)
        matched_rows = []
        for one in norm_rows:
            haystack = "\n".join([
                str(one.get('biaoti') or ''),
                str(one.get('zhengwen') or ''),
                str(one.get('tupianneirong') or '')
            ]).lower()
            haystack_joined = re.sub(r"\s+", "", haystack)
            score = 0
            if q_joined and q_joined in haystack_joined:
                score += 12
            for term in terms:
                if term and term in haystack:
                    score += min(6, max(2, len(term)))
            if score > 0:
                copied = dict(one)
                copied['score'] = score
                matched_rows.append(copied)

        matched_rows.sort(key=lambda x: (-int(x.get('score') or 0), int(x.get('order_index') or 0)))
        matched_rows = matched_rows[:30]
        if not matched_rows:
            return jsonify({
                'success': False,
                'message': '未在你已提交日志的正文和图片内容中检索到相关信息'
            }), 404

        source_text = _xiaotu_render_knowledge_source_text(matched_rows)
        prompt = (
            f"你是日志知识搜索助手。请仅基于以下“{user_name}本人已提交日志”的检索结果回答问题。\n"
            f"用户问题：{question}\n"
            "回答要求：\n"
            "1) 只能依据提供的日志正文和图片内容回答，不得补充素材之外的信息；\n"
            "2) 先给出直接答案，再概括依据；\n"
            "3) 若有多条记录，合并总结共同结论并点出关键时间或标题；\n"
            "4) 若证据不足，请明确说明“未在我已提交日志中检索到足够依据”；\n"
            "5) 输出简洁清晰，适合直接阅读。"
        )
        answer = _generate_ai_answer_with_doc(
            prompt_text=prompt,
            doc_text=source_text[:50000],
            doc_name=f"{user_name}-日志知识搜索",
            chat_id=f"xiaotu_knowledge:{user_id}:{int(datetime.now().timestamp())}"
        )

        return jsonify({
            'success': True,
            'data': {
                'user_name': user_name,
                'question': question,
                'row_count': len(matched_rows),
                'searched_total': len(norm_rows),
                'answer': str(answer or '').strip(),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'知识搜索失败: {str(e)}'}), 500


@app.route('/api/xiaotu/daily_from_im', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_daily_from_im():
    stage = "start"
    try:
        stage = "auth"
        user_id = str(session.get('feishu_user_id') or '').strip()
        user_name = str(session.get('feishu_user_name') or '用户').strip()
        user_access_token = str(session.get('feishu_user_access_token') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        if not user_access_token:
            session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center')
            return jsonify({
                'success': False,
                'message': '登录状态缺少飞书消息访问凭证，正在跳转重新登录',
                'auth_url': url_for('feishu_auth')
            }), 401

        stage = "parse_args"
        payload = request.get_json(silent=True) or {}
        max_chats = int(payload.get('max_chats') or 60)
        max_chats = max(1, min(max_chats, 120))
        max_messages_per_chat = int(payload.get('max_messages_per_chat') or 80)
        max_messages_per_chat = max(20, min(max_messages_per_chat, 200))

        now = datetime.now()
        day_start = datetime(now.year, now.month, now.day, 0, 0, 0)
        day_end = now
        # 飞书消息列表接口使用秒级时间戳，传毫秒会导致当天消息范围失真
        start_ts = str(int(day_start.timestamp()))
        end_ts = str(int(day_end.timestamp()))
        headers = {"Authorization": f"Bearer {user_access_token}"}
        debug_logs = []
        need_reauth = False

        stage = "load_chats"
        chat_items = []
        chat_page_token = ""
        skipped_group_count = 0
        while True:
            params = {"page_size": 100}
            if chat_page_token:
                params["page_token"] = chat_page_token
            try:
                resp = _feishu_http.get("https://open.feishu.cn/open-apis/im/v1/chats", headers=headers, params=params, timeout=15)
                data = resp.json() if resp is not None else {}
            except Exception as e:
                data = {}
                debug_logs.append(f"拉取群列表异常: {str(e)}")
                break
            code_num = -1
            if isinstance(data, dict):
                try:
                    code_num = int(data.get("code"))
                except Exception:
                    code_num = -1
            if not isinstance(data, dict) or code_num != 0:
                code_text = str((data or {}).get("code") if isinstance(data, dict) else "")
                msg_text = str((data or {}).get("msg") if isinstance(data, dict) else "")
                if (
                    code_text in {"99991677", "99991663", "99991679", "99991695"}
                    or "token expired" in msg_text.lower()
                    or "历史版本" in msg_text
                    or "end-user-consent" in msg_text.lower()
                    or "please request user re-authorization" in msg_text.lower()
                    or "应用未获取所需的用户授权" in msg_text
                ):
                    need_reauth = True
                debug_logs.append(
                    "拉取群列表失败: code={code}, msg={msg}, request_id={rid}".format(
                        code=str((data or {}).get("code") if isinstance(data, dict) else "unknown"),
                        msg=str((data or {}).get("msg") if isinstance(data, dict) else "invalid_response"),
                        rid=str(((data or {}).get("request_id") if isinstance(data, dict) else "") or "-")
                    )
                )
                break
            body = data.get("data") if isinstance(data.get("data"), dict) else {}
            items = body.get("items") if isinstance(body.get("items"), list) else []
            for one in items:
                if not isinstance(one, dict):
                    continue
                chat_id = str(one.get("chat_id") or "").strip()
                if not chat_id:
                    continue
                chat_mode = str(one.get("chat_mode") or one.get("chat_type") or one.get("type") or "").strip().lower()
                # 当前应用类型读取群聊消息会报 231204，这里只保留单聊（p2p）进行日报参考生成
                if chat_mode and chat_mode != "p2p":
                    skipped_group_count += 1
                    continue
                if not chat_mode:
                    continue
                chat_items.append({
                    "chat_id": chat_id,
                    "name": str(one.get("name") or "").strip() or chat_id,
                    "chat_mode": chat_mode
                })
                if len(chat_items) >= max_chats:
                    break
            if len(chat_items) >= max_chats:
                break
            chat_page_token = str(body.get("page_token") or "").strip()
            if not chat_page_token:
                break

        if not chat_items:
            if skipped_group_count:
                debug_logs.append(f"已跳过群聊 {skipped_group_count} 个，当前未识别到可读取的单聊会话")
            else:
                debug_logs.append("当前未识别到可读取的单聊会话")

        stage = "load_messages"
        all_lines = []
        used_chat_count = 0
        total_message_count = 0
        total_self_message_count = 0

        for chat in chat_items:
            if len(all_lines) >= 1800:
                break
            chat_id = str(chat.get("chat_id") or "").strip()
            chat_name = str(chat.get("name") or "").strip() or chat_id
            if not chat_id:
                continue
            page_token = ""
            chat_lines = []
            fetched_this_chat = 0
            while fetched_this_chat < max_messages_per_chat:
                params = {
                    "container_id_type": "chat",
                    "container_id": chat_id,
                    "sort_type": "ByCreateTimeAsc",
                    "start_time": start_ts,
                    "end_time": end_ts,
                    "page_size": min(50, max_messages_per_chat - fetched_this_chat)
                }
                if page_token:
                    params["page_token"] = page_token
                try:
                    resp = _feishu_http.get("https://open.feishu.cn/open-apis/im/v1/messages", headers=headers, params=params, timeout=15)
                    data = resp.json() if resp is not None else {}
                except Exception as e:
                    debug_logs.append(f"拉取单聊消息异常: chat={chat_name}({chat_id}), err={str(e)}")
                    break
                code_num = -1
                if isinstance(data, dict):
                    try:
                        code_num = int(data.get("code"))
                    except Exception:
                        code_num = -1
                if not isinstance(data, dict) or code_num != 0:
                    code_text = str((data or {}).get("code") if isinstance(data, dict) else "")
                    msg_text = str((data or {}).get("msg") if isinstance(data, dict) else "")
                    if (
                        code_text in {"99991677", "99991663", "99991679", "99991695"}
                        or "token expired" in msg_text.lower()
                        or "历史版本" in msg_text
                        or "end-user-consent" in msg_text.lower()
                        or "please request user re-authorization" in msg_text.lower()
                        or "应用未获取所需的用户授权" in msg_text
                    ):
                        need_reauth = True
                    debug_logs.append(
                        "拉取单聊消息失败: chat={chat}, code={code}, msg={msg}, request_id={rid}".format(
                            chat=f"{chat_name}({chat_id})",
                            code=str((data or {}).get("code") if isinstance(data, dict) else "unknown"),
                            msg=str((data or {}).get("msg") if isinstance(data, dict) else "invalid_response"),
                            rid=str(((data or {}).get("request_id") if isinstance(data, dict) else "") or "-")
                        )
                    )
                    break
                body = data.get("data") if isinstance(data.get("data"), dict) else {}
                items = body.get("items") if isinstance(body.get("items"), list) else []
                if not items:
                    break
                for msg in items:
                    text = _xiaotu_get_message_text_for_daily_ref(msg)
                    if not text:
                        continue
                    sender_open_id = _xiaotu_get_sender_open_id_from_message(msg)
                    is_self = bool(sender_open_id and sender_open_id == user_id)
                    tm = _xiaotu_format_message_time(msg.get("create_time"))
                    sender_show = user_name if is_self else (str(sender_open_id or "他人")[:24])
                    line = f"{tm} [{sender_show}] {text}" if tm else f"[{sender_show}] {text}"
                    chat_lines.append(line)
                    total_message_count += 1
                    if is_self:
                        total_self_message_count += 1
                    fetched_this_chat += 1
                    if fetched_this_chat >= max_messages_per_chat:
                        break
                page_token = str(body.get("page_token") or "").strip()
                if not page_token:
                    break

            if chat_lines:
                used_chat_count += 1
                all_lines.append(f"【单聊】{chat_name}")
                all_lines.extend(chat_lines[:max_messages_per_chat])
                all_lines.append("")

        source_text = "\n".join(all_lines).strip()
        if not source_text:
            if need_reauth:
                session['feishu_user_access_token'] = ''
                session['feishu_user_access_token_expire_at'] = ''
                session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center')
                return jsonify({
                    'success': False,
                    'message': '飞书用户授权缺少最新权限，正在跳转重新授权',
                    'auth_url': url_for('feishu_auth'),
                    'debug': debug_logs[:20]
                }), 401
            reason_text = "；".join(debug_logs[:6]).strip()
            full_message = '未获取到今日可用的飞书对话文本'
            if reason_text:
                full_message += f'。详细原因：{reason_text}'
            else:
                if skipped_group_count and not chat_items:
                    full_message += '。当前已按“仅单聊”模式过滤，群聊已全部跳过，请确认今天存在单聊记录。'
                else:
                    full_message += '。请确认今天有单聊消息记录且应用具备消息读取权限。'
            return jsonify({
                'success': False,
                'message': full_message,
                'debug': debug_logs[:20]
            }), 404

        stage = "generate"
        prompt = (
            f"请基于以下飞书对话记录，为“{user_name}”生成一份当日日报参考草稿。\n"
            "要求：\n"
            "1) 重点提炼“我本人”相关工作推进、沟通协作、问题与结论；\n"
            "2) 输出结构固定为：今日重点工作、沟通与协作、问题与风险、明日计划；\n"
            "3) 信息必须来自对话原文，不要臆测；\n"
            "4) 语气简洁、可直接复制到日报中。"
        )
        daily_draft = _generate_ai_answer_with_doc(
            prompt_text=prompt,
            doc_text=source_text[:50000],
            doc_name=f"{user_name}-飞书对话-日报参考-{now.strftime('%Y%m%d')}",
            chat_id=f"xiaotu_daily_im:{user_id}:{int(now.timestamp())}"
        )

        return jsonify({
            'success': True,
            'data': {
                'date': now.strftime('%Y-%m-%d'),
                'user_name': user_name,
                'chat_count': used_chat_count,
                'p2p_chat_count': len(chat_items),
                'skipped_group_count': skipped_group_count,
                'message_count': total_message_count,
                'self_message_count': total_self_message_count,
                'daily_draft': str(daily_draft or '').strip(),
                'source_preview': source_text[:4000],
                'debug': debug_logs[:20]
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'生成失败（阶段:{stage}）: {str(e)}',
            'stage': stage,
            'debug': []
        }), 500


@app.route('/api/ai/xiaotu/period_report', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_period_report():
    try:
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401

        data = request.get_json(silent=True) or {}
        session_user_name = str(session.get('feishu_user_name') or '').strip()
        user_name = str(data.get('user_name') or session.get('feishu_user_name') or '').strip()
        if not user_name:
            return jsonify({'success': False, 'message': '请提供飞书用户名'}), 400

        visible_scope = _xiaotu_get_history_analysis_visible_user_names(user_id, session_user_name)
        visible_name_clause = _xiaotu_build_name_scope_clause(
            "XingMing",
            list(visible_scope.get("user_names") or [session_user_name])
        )
        if not visible_name_clause:
            visible_name_clause = f"XingMing = N'{_xiaotu_sql_escape(session_user_name)}'"
        target_name_clause = _xiaotu_build_name_match_clause("XingMing", [user_name])
        if not target_name_clause:
            target_name_clause = f"XingMing = N'{_xiaotu_sql_escape(user_name)}'"
        auth_rows = sf_db(f"""
            SELECT TOP 1 XingMing
            FROM baogao
            WHERE ({target_name_clause})
              AND ({visible_name_clause})
        """) or []
        if not auth_rows:
            return jsonify({'success': False, 'message': '无权为该用户生成报告HTML'}), 403

        today = datetime.now()
        default_start = datetime(today.year, today.month, today.day)
        start_day = _xiaotu_parse_date_value(data.get('start_date'), fallback=None)
        end_day = _xiaotu_parse_date_value(data.get('end_date'), fallback=None)
        if start_day is None or end_day is None:
            legacy_start, legacy_end, _, _ = _xiaotu_get_period_range(data.get('report_type') or 'week')
            start_day = start_day or datetime(legacy_start.year, legacy_start.month, legacy_start.day)
            end_day = end_day or datetime(legacy_end.year, legacy_end.month, legacy_end.day)
        start_day = datetime(start_day.year, start_day.month, start_day.day)
        end_day = datetime(end_day.year, end_day.month, end_day.day)
        if end_day < start_day:
            return jsonify({'success': False, 'message': '结束日期不能早于开始日期'}), 400
        if (end_day - start_day).days > 120:
            return jsonify({'success': False, 'message': '一次最多分析120天日报'}), 400
        start_s = start_day.strftime('%Y-%m-%d 00:00:00')
        end_s = end_day.strftime('%Y-%m-%d 23:59:59')
        sql_text = f"""
            SELECT RiQi, BiaoTi, ZhengWen, TuPianLujin, TuPianNeiRong
            FROM baogao
            WHERE ({target_name_clause})
              AND RiQi >= '{start_s}'
              AND RiQi <= '{end_s}'
            ORDER BY RiQi ASC
        """
        rows = sf_db(sql_text) or []
        if not rows:
            return jsonify({
                'success': False,
                'message': f'未查询到 {user_name} 在所选日期范围内的日报数据'
            }), 404

        norm_rows = []
        for row in rows:
            if isinstance(row, dict):
                riqi = row.get('RiQi')
                biaoti = row.get('BiaoTi')
                zhengwen = row.get('ZhengWen')
                tupianlujin = row.get('TuPianLujin')
                tupianneirong = row.get('TuPianNeiRong')
            else:
                values = list(row) if isinstance(row, (list, tuple)) else []
                riqi = values[0] if len(values) > 0 else ""
                biaoti = values[1] if len(values) > 1 else ""
                zhengwen = values[2] if len(values) > 2 else ""
                tupianlujin = values[3] if len(values) > 3 else ""
                tupianneirong = values[4] if len(values) > 4 else ""
            norm_rows.append({
                'riqi': str(riqi or '').strip(),
                'biaoti': str(biaoti or '').strip(),
                'zhengwen': str(zhengwen or '').strip(),
                'tupianlujin': str(tupianlujin or '').strip(),
                'tupianneirong': str(tupianneirong or '').strip(),
            })

        source_text = _xiaotu_render_period_source_text(norm_rows)
        if not source_text:
            return jsonify({'success': False, 'message': '所选日期范围内数据为空（正文和图片内容均为空）'}), 400

        prompt = (
            f"请基于以下按日报顺序整合的素材，为飞书用户“{user_name}”生成一份阶段性日报历史分析。\n"
            f"时间范围：{start_s} ~ {end_s}。\n"
            "输出要求：\n"
            "1) 不要重排日报原文顺序；分析时基于所有日报的正文和图片识别内容统一观察；\n"
            "2) 重点总结这段时间日报里体现出的思考性内容，包括关键判断、问题意识、方法沉淀、复盘反思、跨日变化；\n"
            "3) 必须基于素材事实，不要编造素材中没有出现的工作、结果或数据；\n"
            "4) 不要写成流水账，不要简单罗列每日事项；\n"
            "5) 建议输出结构：阶段概览、关键思考、方法沉淀、问题与反思、后续关注；\n"
            "6) 语言清晰、克制，适合放入HTML报告的“整合分析”部分。"
        )
        task_id = hashlib.md5(
            f"{user_name}|{start_day.strftime('%Y-%m-%d')}|{end_day.strftime('%Y-%m-%d')}|{time.time()}".encode("utf-8")
        ).hexdigest()[:16]

        def _xiaotu_period_report_background_worker(payload):
            with app.app_context():
                try:
                    p_user_name = str(payload.get("user_name") or "").strip()
                    p_user_id = str(payload.get("user_id") or "").strip()
                    p_start_day = payload.get("start_day")
                    p_end_day = payload.get("end_day")
                    p_rows = list(payload.get("rows") or [])
                    p_source_text = str(payload.get("source_text") or "")
                    p_prompt = str(payload.get("prompt") or "")
                    p_task_id = str(payload.get("task_id") or "").strip()
                    report_text = _generate_ai_answer_with_doc(
                        prompt_text=p_prompt,
                        doc_text=p_source_text,
                        doc_name=f"{p_user_name}-日报历史分析",
                        chat_id=f"xiaotu_history_report:{p_user_id}:{p_task_id}"
                    )
                    report_text = str(report_text or '').strip()
                    html_text = _xiaotu_build_history_analysis_html(p_user_name, p_start_day, p_end_day, report_text, p_rows)
                    file_path = _xiaotu_save_history_analysis_file(p_user_name, p_start_day, p_end_day, html_text)
                    dui_db(f"""
                        INSERT INTO baogao_lishi (YongHu, KaiShiRiQi, JieShuRIQi, WeiZhi)
                        VALUES (
                            N'{_xiaotu_sql_escape(p_user_name)}',
                            '{p_start_day.strftime('%Y-%m-%d')}',
                            '{p_end_day.strftime('%Y-%m-%d')}',
                            N'{_xiaotu_sql_escape(file_path)}'
                        )
                    """)
                except Exception as bg_err:
                    _safe_debug_print(f"日报历史分析后台生成失败: {payload.get('user_name')} {payload.get('task_id')} -> {bg_err}")

        Thread(target=_xiaotu_period_report_background_worker, args=({
            "task_id": task_id,
            "user_id": str(user_id or ""),
            "user_name": user_name,
            "start_day": start_day,
            "end_day": end_day,
            "rows": norm_rows,
            "source_text": source_text,
            "prompt": prompt,
        },), daemon=True).start()

        return jsonify({
            'success': True,
            'message': '已提交后台生成任务，完成后会出现在报告历史记录中',
            'data': {
                'user_name': user_name,
                'report_kind': '报告',
                'report_type': 'custom',
                'date_range': f"{start_s} ~ {end_s}",
                'row_count': len(norm_rows),
                'task_id': task_id,
                'ai_background': True,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'生成失败: {str(e)}'}), 500


@app.route('/api/xiaotu/notify_targets_preview', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_notify_targets_preview():
    try:
        data = request.get_json(silent=True) or {}
        input_name = str(data.get('user_name') or session.get('feishu_user_name') or '').strip()
        if not input_name:
            return jsonify({'success': False, 'message': '请提供飞书用户名'}), 400

        session_user_name = str(session.get('feishu_user_name') or '').strip()
        session_user_id = str(session.get('feishu_user_id') or '').strip()
        uploader_open_id = ""
        source = ""
        if session_user_name and input_name == session_user_name and session_user_id.startswith("ou_"):
            uploader_open_id = session_user_id
            source = "session"
        if not uploader_open_id:
            uploader_open_id = _xiaotu_lookup_open_id_by_name(input_name)
            source = "feishu_id_table"
        if not uploader_open_id:
            return jsonify({'success': False, 'message': f'未找到用户“{input_name}”对应的open_id'}), 404

        primary_dept_id, primary_dept_name = _xiaotu_pick_primary_department(uploader_open_id)
        dept_leader_user_id = _xiaotu_get_department_leader_user_id(primary_dept_id)
        is_uploader_leader = bool(dept_leader_user_id) and (uploader_open_id == dept_leader_user_id)

        targets = []
        seen = set()

        def add_target(open_id, role, user_name=""):
            oid = str(open_id or "").strip()
            if not oid or oid in seen:
                return
            seen.add(oid)
            targets.append({
                'open_id': oid,
                'role': role,
                'user_name': str(user_name or "").strip()
            })

        add_target(uploader_open_id, "self", input_name)
        if is_uploader_leader:
            escalation_name = str(_XIAOTU_REPORT_ESCALATION_USER or '').strip()
            escalation_open_id = _xiaotu_lookup_open_id_by_name(escalation_name)
            if escalation_open_id:
                add_target(escalation_open_id, "escalation", escalation_name)
        elif dept_leader_user_id:
            add_target(dept_leader_user_id, "department_leader")

        return jsonify({
            'success': True,
            'message': '已计算通知目标（仅预览，不发送消息）',
            'data': {
                'input_user_name': input_name,
                'input_user_open_id': uploader_open_id,
                'open_id_source': source,
                'primary_department_id': primary_dept_id,
                'primary_department_name': primary_dept_name,
                'department_leader_open_id': dept_leader_user_id,
                'is_input_user_department_leader': is_uploader_leader,
                'notify_policy': "成员提交->部门leader_user_id+自己；负责人提交->陶晓飞+自己",
                'notify_targets': targets
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'预览失败: {str(e)}'}), 500


@app.route('/api/xiaotu/notify/departments', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_notify_departments():
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录', 'data': []}), 401
        all_departments = _xiaotu_list_notify_departments()
        user_dept_ids = set()
        try:
            user_rows = permission_manager.get_user_departments(user_id) or []
        except Exception:
            user_rows = []
        for row in user_rows:
            if not isinstance(row, dict):
                continue
            dep_id = str(row.get("department_id") or "").strip()
            if dep_id:
                user_dept_ids.add(dep_id)
        for one in all_departments:
            dep_id = str(one.get("department_id") or "").strip()
            one["is_user_department"] = bool(dep_id in user_dept_ids)
        all_departments.sort(key=lambda x: (0 if x.get("is_user_department") else 1, str(x.get("department_name") or ""), str(x.get("department_id") or "")))
        return jsonify({'success': True, 'data': all_departments})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'data': []}), 500


@app.route('/api/xiaotu/notify/users', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_notify_users():
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录', 'data': []}), 401
        department_id = str(request.args.get('department_id') or '').strip()
        if not department_id:
            return jsonify({'success': False, 'message': '请提供department_id', 'data': []}), 400
        if not (department_id.startswith("od_") or department_id.startswith("od-")):
            return jsonify({'success': False, 'message': 'department_id格式无效', 'data': []}), 400

        payload = _xiaotu_list_notify_users_current_app(department_id)
        for one in payload:
            one['is_self'] = bool(str(one.get('open_id') or '').strip() == user_id)
        return jsonify({'success': True, 'data': payload, 'department_id': department_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'data': []}), 500


@app.route('/api/xiaotu/notify/search', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_notify_search():
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录', 'data': []}), 401
        keyword = str(request.args.get('keyword') or request.args.get('q') or '').strip()
        if not keyword:
            return jsonify({'success': True, 'data': [], 'keyword': keyword})
        payload = _xiaotu_search_notify_users(keyword, limit=50)
        for one in payload:
            one['is_self'] = bool(str(one.get('open_id') or '').strip() == user_id)
        return jsonify({'success': True, 'data': payload, 'keyword': keyword})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'data': []}), 500


def _annual_moments_file_size_label(size_bytes):
    try:
        size_value = float(size_bytes or 0)
    except (TypeError, ValueError):
        size_value = 0
    if size_value >= 1024 * 1024 * 1024:
        return f"{size_value / (1024 * 1024 * 1024):.1f} GB"
    if size_value >= 1024 * 1024:
        return f"{size_value / (1024 * 1024):.1f} MB"
    if size_value >= 1024:
        return f"{size_value / 1024:.1f} KB"
    return f"{int(size_value)} B"


def _collect_annual_moment_files(folder, extensions, endpoint):
    media_files = []
    if not os.path.isdir(folder):
        return media_files

    root_abs = os.path.abspath(folder)
    for current_root, dirs, files in os.walk(root_abs):
        dirs.sort()
        for name in sorted(files):
            file_abs = os.path.abspath(os.path.join(current_root, name))
            ext = os.path.splitext(name)[1].lower()
            if ext not in extensions or not os.path.isfile(file_abs):
                continue
            try:
                stat_info = os.stat(file_abs)
            except OSError:
                continue
            relpath = os.path.relpath(file_abs, root_abs).replace('\\', '/')
            rel_dir = os.path.dirname(relpath).replace('\\', '/')
            media_files.append({
                "name": name,
                "url": url_for(endpoint, relpath=relpath),
                "relpath": relpath,
                "folder_name": rel_dir if rel_dir else "根目录",
                "size": stat_info.st_size,
                "size_label": _annual_moments_file_size_label(stat_info.st_size),
                "modified_at": datetime.fromtimestamp(stat_info.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    return media_files


def _send_annual_moment_file(root_folder, relpath, allowed_extensions):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))

    raw_rel = str(relpath or '').replace('\\', '/').strip()
    if not raw_rel:
        return "文件不存在", 404
    safe_rel = os.path.normpath(raw_rel).replace('\\', '/')
    if safe_rel in {'.', ''} or safe_rel.startswith('../') or safe_rel.startswith('/'):
        return "文件不存在", 404

    root_abs = os.path.abspath(root_folder)
    file_abs = os.path.abspath(os.path.join(root_abs, safe_rel))
    try:
        if os.path.commonpath([root_abs, file_abs]).lower() != root_abs.lower():
            return "文件不存在", 404
    except ValueError:
        return "文件不存在", 404

    safe_name = os.path.basename(file_abs)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in allowed_extensions:
        return "不支持的文件类型", 400
    if not os.path.isfile(file_abs):
        return "文件不存在", 404
    return send_from_directory(os.path.dirname(file_abs), safe_name, as_attachment=False, conditional=True)


@app.route('/annual_moments')
def annual_moments():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))

    images = _collect_annual_moment_files(
        _ANNUAL_MOMENTS_IMAGE_DIR,
        _IMAGE_EXTENSIONS,
        'annual_moment_image_file'
    )
    videos = _collect_annual_moment_files(
        _ANNUAL_MOMENTS_VIDEO_DIR,
        _VIDEO_EXTENSIONS,
        'annual_moment_video_file'
    )
    return render_template(
        'annual_moments.html',
        images=images,
        videos=videos,
        image_folder=_ANNUAL_MOMENTS_IMAGE_DIR,
        video_folder=_ANNUAL_MOMENTS_VIDEO_DIR,
        image_folder_exists=os.path.isdir(_ANNUAL_MOMENTS_IMAGE_DIR),
        video_folder_exists=os.path.isdir(_ANNUAL_MOMENTS_VIDEO_DIR),
    )


@app.route('/annual_moments/images/<path:relpath>')
def annual_moment_image_file(relpath):
    return _send_annual_moment_file(_ANNUAL_MOMENTS_IMAGE_DIR, relpath, _IMAGE_EXTENSIONS)


@app.route('/annual_moments/videos/<path:relpath>')
def annual_moment_video_file(relpath):
    return _send_annual_moment_file(_ANNUAL_MOMENTS_VIDEO_DIR, relpath, _VIDEO_EXTENSIONS)


@app.route('/training_videos')
def training_videos():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    return render_template('training_videos.html')


@app.route('/training_videos/chuanshi')
def chuanshi_training():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))

    images = _collect_annual_moment_files(
        _CHUANSHI_TRAINING_IMAGE_DIR,
        _IMAGE_EXTENSIONS,
        'chuanshi_training_image_file'
    )
    videos = _collect_annual_moment_files(
        _CHUANSHI_TRAINING_VIDEO_DIR,
        _VIDEO_EXTENSIONS,
        'chuanshi_training_video_file'
    )
    return render_template(
        'annual_moments.html',
        page_title='传世培训',
        page_icon='fa-solid fa-photo-film',
        back_url=url_for('training_videos'),
        back_label='返回培训视频',
        activity_date='2026-07-09',
        images=images,
        videos=videos,
        image_folder=_CHUANSHI_TRAINING_IMAGE_DIR,
        video_folder=_CHUANSHI_TRAINING_VIDEO_DIR,
        image_folder_exists=os.path.isdir(_CHUANSHI_TRAINING_IMAGE_DIR),
        video_folder_exists=os.path.isdir(_CHUANSHI_TRAINING_VIDEO_DIR),
    )


@app.route('/training_videos/chuanshi/images/<path:relpath>')
def chuanshi_training_image_file(relpath):
    return _send_annual_moment_file(_CHUANSHI_TRAINING_IMAGE_DIR, relpath, _IMAGE_EXTENSIONS)


@app.route('/training_videos/chuanshi/videos/<path:relpath>')
def chuanshi_training_video_file(relpath):
    return _send_annual_moment_file(_CHUANSHI_TRAINING_VIDEO_DIR, relpath, _VIDEO_EXTENSIONS)


@app.route('/training_videos/strategy')
def strategy_training_videos():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    folder = _STRATEGY_TRAINING_VIDEO_DIR
    grouped_videos = []
    if os.path.isdir(folder):
        for current_root, dirs, files in os.walk(folder):
            dirs.sort()
            rel_dir = os.path.relpath(current_root, folder)
            videos = []
            for name in sorted(files):
                file_path = os.path.join(current_root, name)
                ext = os.path.splitext(name)[1].lower()
                if not os.path.isfile(file_path) or ext not in _VIDEO_EXTENSIONS:
                    continue
                if rel_dir in {'.', ''}:
                    video_url = url_for('strategy_training_video_file', filename=name)
                    folder_name = '根目录'
                else:
                    rel_file = os.path.join(rel_dir, name).replace('\\', '/')
                    video_url = url_for('strategy_training_video_file_by_path', relpath=rel_file)
                    folder_name = rel_dir.replace('\\', '/')
                videos.append({
                    "name": name,
                    "url": video_url
                })
            if videos:
                grouped_videos.append({
                    "folder_name": folder_name,
                    "videos": videos
                })
    return render_template(
        'strategy_training_videos.html',
        grouped_videos=grouped_videos,
        folder_path=folder
    )


@app.route('/training_videos/strategy/files/<path:filename>')
def strategy_training_video_file(filename):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    safe_name = os.path.basename(str(filename or ""))
    if not safe_name:
        return "文件不存在", 404
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _VIDEO_EXTENSIONS:
        return "不支持的文件类型", 400
    file_path = os.path.join(_STRATEGY_TRAINING_VIDEO_DIR, safe_name)
    if not os.path.isfile(file_path):
        return "文件不存在", 404
    return send_from_directory(_STRATEGY_TRAINING_VIDEO_DIR, safe_name, as_attachment=False)


@app.route('/training_videos/strategy/files/<path:folder>/<path:filename>')
def strategy_training_video_file_in_folder(folder, filename):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    safe_folder = os.path.basename(str(folder or ""))
    safe_name = os.path.basename(str(filename or ""))
    if not safe_folder or not safe_name:
        return "文件不存在", 404
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _VIDEO_EXTENSIONS:
        return "不支持的文件类型", 400
    target_dir = os.path.join(_STRATEGY_TRAINING_VIDEO_DIR, safe_folder)
    file_path = os.path.join(target_dir, safe_name)
    if not os.path.isdir(target_dir) or not os.path.isfile(file_path):
        return "文件不存在", 404
    return send_from_directory(target_dir, safe_name, as_attachment=False)


@app.route('/training_videos/strategy/files/tree/<path:relpath>')
def strategy_training_video_file_by_path(relpath):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    raw_rel = str(relpath or '').replace('\\', '/').strip()
    if not raw_rel:
        return "文件不存在", 404
    safe_rel = os.path.normpath(raw_rel).replace('\\', '/')
    if safe_rel in {'.', ''} or safe_rel.startswith('../') or safe_rel.startswith('/'):
        return "文件不存在", 404
    root_abs = os.path.abspath(_STRATEGY_TRAINING_VIDEO_DIR)
    file_abs = os.path.abspath(os.path.join(root_abs, safe_rel))
    try:
        if os.path.commonpath([root_abs, file_abs]).lower() != root_abs.lower():
            return "文件不存在", 404
    except ValueError:
        return "文件不存在", 404
    safe_name = os.path.basename(file_abs)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _VIDEO_EXTENSIONS:
        return "不支持的文件类型", 400
    if not os.path.isfile(file_abs):
        return "文件不存在", 404
    return send_from_directory(os.path.dirname(file_abs), safe_name, as_attachment=False)


@app.route('/training_videos/rococo')
def rococo_training_videos():
    root_folder = _ROCOCO_TRAINING_VIDEO_DIR
    grouped_videos = []
    if os.path.isdir(root_folder):
        for folder_name in sorted(os.listdir(root_folder)):
            folder_path = os.path.join(root_folder, folder_name)
            if not os.path.isdir(folder_path):
                continue
            videos = []
            for name in sorted(os.listdir(folder_path)):
                file_path = os.path.join(folder_path, name)
                ext = os.path.splitext(name)[1].lower()
                if os.path.isfile(file_path) and ext in _VIDEO_EXTENSIONS:
                    videos.append({
                        "name": name,
                        "url": url_for('rococo_training_video_file', folder=folder_name, filename=name)
                    })
            grouped_videos.append({
                "folder_name": folder_name,
                "videos": videos
            })
    return render_template(
        'rococo_training_videos.html',
        grouped_videos=grouped_videos,
        folder_path=root_folder
    )


@app.route('/training_videos/rococo/files/<path:folder>/<path:filename>')
def rococo_training_video_file(folder, filename):
    safe_folder = os.path.basename(str(folder or ""))
    safe_name = os.path.basename(str(filename or ""))
    if not safe_folder or not safe_name:
        return "文件不存在", 404
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _VIDEO_EXTENSIONS:
        return "不支持的文件类型", 400
    target_dir = os.path.join(_ROCOCO_TRAINING_VIDEO_DIR, safe_folder)
    file_path = os.path.join(target_dir, safe_name)
    if not os.path.isdir(target_dir) or not os.path.isfile(file_path):
        return "文件不存在", 404
    return send_from_directory(target_dir, safe_name, as_attachment=False)


@app.route('/api/menu_click', methods=['POST'])
def api_menu_click():
    try:
        data = request.get_json(silent=True) or {}
        menu = str(data.get('menu') or '').strip()
        href = str(data.get('href') or '').strip()
        if not menu and href:
            menu = href
        if not menu:
            return jsonify({'success': False, 'message': 'menu不能为空'}), 400

        user_id = '007'
        user_name = str(session.get('feishu_user_name') or '').strip() or '用户'

        def esc(v):
            return '' if v is None else str(v).strip().replace("'", "''")

        menu_safe = esc(menu)[:200]
        user_name_safe = esc(user_name)[:80]
        sql = (
            "INSERT INTO CaiDanShiYongJiLu ([UserID], [UserName], [Menu], [Time]) "
            f"VALUES ('{user_id}', '{user_name_safe}', '{menu_safe}', GETDATE())"
        )
        dui_db(sql)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)[:200]}), 500


@app.route('/performance')
def performance_monitor():
    """性能监控页面"""
    user_id = session.get('feishu_user_id')

    # 本地开发模式，跳过飞书认证
    if app.config.get('LOCAL_DEV_MODE', False):
        user_id = 'local_dev_user'
        session['feishu_user_id'] = user_id
        session['feishu_user_name'] = '本地开发用户'

    if not user_id:
        return redirect(get_feishu_auth_url())

    return render_template('performance.html')


@app.route('/script_generator')
@require_permission('script_generator')
def script_generator():
    """脚本生成器页面"""
    return render_template('script_generator.html')


@app.route('/generate_script', methods=['POST'])
@require_permission('script_generator')
def generate_script():
    """生成脚本API（并发优化版）"""

    try:
        data = request.get_json()
        product_name = data.get('product_name', '').strip()
        features = data.get('features', [])
        quantity = int(data.get('quantity', 1))

        if not product_name or not features:
            return jsonify({
                'success': False,
                'message': '请提供完整的产品信息'
            })

        # 使用并发处理来加速脚本生成
        def generate_single_script(script_number):
            try:
                script = call_ai_api(product_name, features, script_number)
                return {
                    'number': script_number,
                    'content': script
                }
            except Exception as script_error:
                _safe_debug_print(f"生成第{script_number}个脚本时出错: {str(script_error)}")
                return {
                    'number': script_number,
                    'content': f"脚本生成失败: {str(script_error)}"
                }

        # 使用线程池并发生成脚本
        script_numbers = list(range(1, quantity + 1))
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, quantity)) as executor:
            future_to_script = {executor.submit(generate_single_script, num): num for num in script_numbers}
            scripts = []

            for future in concurrent.futures.as_completed(future_to_script):
                script_result = future.result()
                scripts.append(script_result)

        # 按脚本编号排序
        scripts.sort(key=lambda x: x['number'])

        return jsonify({
            'success': True,
            'scripts': scripts
        })

    except Exception as e:
        _safe_debug_print(f"生成脚本API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'生成脚本时发生错误: {str(e)}'
        })


@app.route('/admin_dashboard')
@require_permission('admin_functions')
def admin_dashboard():
    """管理员仪表板"""
    return render_template('admin_dashboard.html')


@app.route('/tk_project')
@require_permission('tk_project_group')
def tk_project():
    """TK项目组功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')

    # 获取用户可访问的功能
    accessible_functions = []
    if user_id:
        try:
            accessible_functions = permission_manager.get_user_accessible_functions(user_id)
        except Exception as e:
            _safe_debug_print(f"❌ 获取用户权限失败: {e}")

    return render_template('tk_project.html',
                           user_name=user_name,
                           user_id=user_id,
                           accessible_functions=accessible_functions)


@app.route('/tk_seedance')
def tk_seedance():
    if not _seedance_access_allowed():
        return redirect(url_for('tk_project'))
    return redirect(url_for('seedance_web.seedance_web_index'))


@app.route('/tk_customer_service')
@require_permission('tk_customer_service')
def tk_customer_service():
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    default_day = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    start_date = (request.args.get('start_date') or default_day).strip()
    end_date = (request.args.get('end_date') or default_day).strip()
    return render_template(
        'tk_customer_service.html',
        user_id=user_id,
        user_name=user_name,
        start_date=start_date,
        end_date=end_date
    )


def _tk_country_to_iso2(country_name):
    s = re.sub(r'[^a-zA-Z ]', ' ', str(country_name or '')).strip().lower()
    s = re.sub(r'\s+', ' ', s)
    if not s:
        return ''
    mapping = {
        'united states': 'US',
        'united states of america': 'US',
        'usa': 'US',
        'us': 'US',
        'china': 'CN',
        'hong kong': 'HK',
        'united kingdom': 'GB',
        'uk': 'GB',
        'great britain': 'GB',
        'canada': 'CA',
        'australia': 'AU',
        'germany': 'DE',
        'france': 'FR',
        'italy': 'IT',
        'spain': 'ES',
        'japan': 'JP',
        'korea': 'KR',
        'south korea': 'KR',
        'singapore': 'SG',
        'malaysia': 'MY',
        'thailand': 'TH',
        'vietnam': 'VN',
        'philippines': 'PH',
        'indonesia': 'ID'
    }
    if s in mapping:
        return mapping[s]
    parts = [p for p in s.split(' ') if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return parts[0][:2].upper()


def _tk_split_street_city(first_part):
    text = str(first_part or '').strip()
    if not text:
        return '', ''
    tokens = text.split()
    if len(tokens) <= 1:
        return text, ''
    suffixes = {
        'st', 'street', 'rd', 'road', 'ave', 'avenue', 'blvd', 'boulevard', 'dr', 'drive',
        'ln', 'lane', 'ct', 'court', 'cir', 'circle', 'pl', 'place', 'pkwy', 'parkway',
        'way', 'trl', 'trail', 'hwy', 'highway', 'ter', 'terrace'
    }
    unit_words = {'apt', 'apartment', 'unit', 'ste', 'suite', '#', 'fl', 'floor', 'rm', 'room', 'bldg'}
    direction_words = {'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'north', 'south', 'east', 'west'}
    split_idx = -1
    for i, tk in enumerate(tokens):
        norm = re.sub(r'[^a-zA-Z]', '', tk).lower()
        if norm in suffixes:
            split_idx = i
    if split_idx < 0 or split_idx >= len(tokens) - 1:
        return text, ''
    j = split_idx + 1
    while j < len(tokens):
        norm = re.sub(r'[^a-zA-Z#]', '', tokens[j]).lower()
        if norm in unit_words:
            j += 1
            if j < len(tokens) and re.search(r'\d', tokens[j]):
                j += 1
            continue
        break
    if j >= len(tokens):
        return text, ''
    city_tokens = tokens[j:]
    if len(city_tokens) == 1:
        norm_city = re.sub(r'[^a-zA-Z]', '', city_tokens[0]).lower()
        if norm_city in suffixes:
            return text, ''
    if len(city_tokens) >= 2:
        first_city_norm = re.sub(r'[^a-zA-Z]', '', city_tokens[0]).lower()
        if first_city_norm in direction_words:
            city = city_tokens[0] + ' ' + city_tokens[1]
            if len(city_tokens) > 2:
                city = city + ' ' + ' '.join(city_tokens[2:])
        else:
            city = ' '.join(city_tokens)
    else:
        city = city_tokens[0]
    address1 = ' '.join(tokens[:j]).strip()
    return address1, city.strip()


def _tk_extract_zip_and_country(part):
    text = str(part or '').strip()
    zip_match = re.search(r'(\d{4,10}(?:-\d{3,4})?)\s*$', text)
    if not zip_match:
        return '', text
    zipcode = zip_match.group(1)
    country_name = text[:zip_match.start()].strip(' ,')
    return zipcode, country_name


def _tk_extract_state_zip_tail(text):
    s = str(text or '').strip()
    m = re.match(r'^(.*?)[,\s]+([A-Za-z]{2})\s+(\d{4,10}(?:-\d{3,4})?)\s*$', s)
    if not m:
        return '', '', ''
    return m.group(1).strip(' ,'), m.group(2).strip(), m.group(3).strip()


def _tk_extract_us_zip_anywhere(text):
    s = str(text or '')
    matches = re.findall(r'(?<!\d)(\d{5}(?:-\d{4})?)(?!\d)', s)
    if not matches:
        return ''
    return matches[-1].strip()


def _tk_extract_us_state_with_span(text):
    s = str(text or '')
    if not s:
        return '', -1, -1
    state_codes = {
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
    }
    name_map = {
        'virginia': 'VA',
        'texas': 'TX',
        'toexas': 'TX',
        'florida': 'FL',
        'ohio': 'OH'
    }
    lower_s = s.lower()
    best_name = ''
    best_name_span = (-1, -1)
    for name, code in name_map.items():
        for m in re.finditer(r'\b' + re.escape(name) + r'\b', lower_s):
            best_name = code
            best_name_span = m.span()
    if best_name:
        return best_name, best_name_span[0], best_name_span[1]
    best_code = ''
    best_span = (-1, -1)
    for m in re.finditer(r'(?<![A-Za-z])([A-Z]{2})(?![A-Za-z])', s):
        code = m.group(1)
        if code in state_codes:
            best_code = code
            best_span = m.span(1)
    if best_code:
        return best_code, best_span[0], best_span[1]
    return '', -1, -1


def _tk_fallback_parse_us_address(raw_text, existing_phone=''):
    raw = str(raw_text or '').replace('\u00A0', ' ').replace('\u3000', ' ')
    raw = re.sub(r'\s+', ' ', raw).strip(' ,')
    phone = str(existing_phone or '').strip()
    if not raw:
        return {
            'receiver': '',
            'phone': phone,
            'address1': '',
            'city': '',
            'state': '',
            'zipcode': '',
            'country_code': ''
        }
    working = raw
    if not phone:
        phone_match = re.search(r'(\(\+?\d{1,3}\)\s*[\d\-\s]{7,}\d|\+\d[\d\-\s]{8,}\d|\b\d{3}-\d{3}-\d{4}\b|\b\d{3}-\d{4}-\d{4}\b|\b\d{10}\b)', working)
        if phone_match:
            mtext = phone_match.group(1).strip()
            digits = re.sub(r'\D', '', mtext)
            lead = '+' if '+' in mtext else ''
            extra_digits = ''
            if digits.startswith('1') and len(digits) > 11:
                extra_digits = digits[11:]
                digits = digits[:11]
            elif not digits.startswith('1') and len(digits) > 10:
                extra_digits = digits[10:]
                digits = digits[:10]
            phone = (lead + digits).strip() if digits else mtext
            before = working[:phone_match.start()].strip()
            after = working[phone_match.end():].strip()
            recovered = extra_digits.strip()
            working = ' '.join([x for x in [before, recovered, after] if x]).strip()
    normalized = working
    normalized = re.sub(r'United\s+States\s+of\s+America', ' United States ', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'I+NITED\s+States\s+of\s+America', ' United States ', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'I+NITED\s+States', ' United States ', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\bToexas\b', 'Texas', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\bdeb\.ary\b', 'debary', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\s+', ' ', normalized).strip(' ,')
    zipcode = _tk_extract_us_zip_anywhere(normalized)
    state, state_start, state_end = _tk_extract_us_state_with_span(normalized)
    country_code = 'US' if re.search(r'united\s+states|usa|\bus\b', normalized, flags=re.IGNORECASE) else ''
    work_no_country = re.sub(r'united\s+states(?:\s+of\s+america)?|usa', ' ', normalized, flags=re.IGNORECASE)
    if zipcode:
        work_no_country = re.sub(r'(?<!\d)' + re.escape(zipcode) + r'(?!\d)', ' ', work_no_country)
    cut_text = work_no_country
    if state and state_start >= 0:
        cut_text = work_no_country[:state_start]
    cut_text = re.sub(r'\s+', ' ', cut_text).strip(' ,')
    first_digit_match = re.search(r'\b\d+[A-Za-z\-]*\b', cut_text)
    receiver = ''
    first_part = cut_text
    if first_digit_match:
        receiver = cut_text[:first_digit_match.start()].strip(' ,')
        first_part = cut_text[first_digit_match.start():].strip(' ,')
    else:
        tokens = [t for t in cut_text.split() if t]
        if len(tokens) >= 2:
            receiver = ' '.join(tokens[:2]).strip(' ,')
            first_part = ' '.join(tokens[2:]).strip(' ,')
        elif tokens:
            receiver = tokens[0]
            first_part = ''
    address1 = first_part
    city = ''
    if first_part:
        addr_guess, city_guess = _tk_split_street_city(first_part)
        if addr_guess:
            address1 = addr_guess
        city = city_guess
        if not city:
            addr_tail, city_tail = _tk_guess_city_from_tail(first_part)
            if city_tail:
                city = city_tail
                if addr_tail:
                    address1 = addr_tail
    return {
        'receiver': receiver.strip(' ,'),
        'phone': phone.strip(),
        'address1': address1.strip(' ,'),
        'city': city.strip(' ,'),
        'state': state.strip(),
        'zipcode': zipcode.strip(),
        'country_code': country_code
    }


def _tk_guess_city_from_tail(prefix_text):
    text = str(prefix_text or '').strip()
    if not text:
        return '', ''
    tokens = text.split()
    if len(tokens) == 1:
        return '', tokens[0]
    direction_words = {'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'north', 'south', 'east', 'west'}
    two_word_city_tail = {'haven', 'hills', 'falls', 'springs', 'heights', 'beach', 'city', 'park', 'point', 'bay'}
    last_norm = re.sub(r'[^a-zA-Z]', '', tokens[-1]).lower()
    prev_norm = re.sub(r'[^a-zA-Z]', '', tokens[-2]).lower() if len(tokens) >= 2 else ''
    if len(tokens) >= 2 and (prev_norm in direction_words or last_norm in two_word_city_tail):
        return ' '.join(tokens[:-2]).strip(), (tokens[-2] + ' ' + tokens[-1]).strip()
    return ' '.join(tokens[:-1]).strip(), tokens[-1].strip()


def _tk_guess_city_from_street_tail(prefix_text):
    text = str(prefix_text or '').strip()
    if not text:
        return '', ''
    tokens = text.split()
    if len(tokens) < 2:
        return '', ''
    suffixes = {
        'st', 'street', 'rd', 'road', 'ave', 'avenue', 'blvd', 'boulevard', 'dr', 'drive',
        'ln', 'lane', 'ct', 'court', 'cir', 'circle', 'pl', 'place', 'pkwy', 'parkway',
        'way', 'trl', 'trail', 'hwy', 'highway', 'ter', 'terrace'
    }
    direction_words = {'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'north', 'south', 'east', 'west'}
    last_norm = re.sub(r'[^a-zA-Z]', '', tokens[-1]).lower()
    prev_norm = re.sub(r'[^a-zA-Z]', '', tokens[-2]).lower()
    if last_norm in suffixes and prev_norm in direction_words:
        addr = ' '.join(tokens[:-2]).strip()
        city = (tokens[-2] + ' ' + tokens[-1]).strip()
        return addr, city
    return '', ''


def _tk_parse_wanghong_address(raw_address):
    raw = str(raw_address or '').replace('\u00A0', ' ').replace('\u3000', ' ')
    raw = re.sub(r'\s+', ' ', raw).strip()
    receiver = ''
    phone = ''
    address1 = ''
    city = ''
    state = ''
    country_code = ''
    zipcode = ''
    house_no = ''
    if not raw:
        return {
            'receiver': receiver,
            'phone': phone,
            'address1': address1,
            'short_address': address1,
            'city': city,
            'state': state,
            'country_code': country_code,
            'zipcode': zipcode,
            'house_no': house_no
        }
    phone_match = re.search(r'(\(\+?\d{1,3}\)\s*[\d\-\s]{7,}\d|\+\d[\d\-\s]{8,}\d|\b\d{3}-\d{3}-\d{4}\b|\b\d{3}-\d{4}-\d{4}\b|\b\d{10}\b)', raw)
    location_part = raw
    if phone_match:
        receiver = raw[:phone_match.start()].strip(' ,')
        phone = phone_match.group(1).strip()
        phone_digits = re.sub(r'\D', '', phone)
        if phone_digits.startswith('1') and len(phone_digits) > 11:
            extra_digits = phone_digits[11:]
            phone_digits = phone_digits[:11]
            phone = ('+' + phone_digits) if '+' in phone else phone_digits
            location_part = (extra_digits + ' ' + raw[phone_match.end():].strip(' ,')).strip()
        elif (not phone_digits.startswith('1')) and len(phone_digits) > 10:
            extra_digits = phone_digits[10:]
            phone_digits = phone_digits[:10]
            phone = phone_digits
            location_part = (extra_digits + ' ' + raw[phone_match.end():].strip(' ,')).strip()
        else:
            location_part = raw[phone_match.end():].strip(' ,')
    location_part = re.sub(r'(?<=\))(?=[A-Za-z])', ' ', location_part)
    location_part = re.sub(r'[\[\]]', ' ', location_part)
    location_part = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', location_part)
    location_part = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', location_part)
    location_part = re.sub(r'United\s+States\s+of\s+America', 'United States', location_part, flags=re.IGNORECASE)
    location_part = re.sub(r'I+NITED\s+States\s+of\s+America', 'United States', location_part, flags=re.IGNORECASE)
    location_part = re.sub(r'I+NITED\s+States', 'United States', location_part, flags=re.IGNORECASE)
    location_part = re.sub(r'\bToexas\b', 'Texas', location_part, flags=re.IGNORECASE)
    location_part = re.sub(r'\bdeb\.ary\b', 'debary', location_part, flags=re.IGNORECASE)
    location_part = re.sub(r'\s+', ' ', location_part).strip(' ,')
    parts = [p.strip() for p in location_part.split(',') if p and str(p).strip()]
    if parts:
        first_part = parts[0]
        address1 = first_part
        parsed_from_multi_parts = False
        if len(parts) >= 4:
            zip_candidate = ''
            for seg in reversed(parts):
                z = _tk_extract_us_zip_anywhere(seg)
                if z:
                    zip_candidate = z
                    break
            state_candidate = ''
            for seg in parts[1:]:
                st, _, _ = _tk_extract_us_state_with_span(seg)
                if st:
                    state_candidate = st
            country_candidate = ''
            joined_parts_text = ' '.join(parts)
            if re.search(r'united\s+states|usa|\bus\b', joined_parts_text, flags=re.IGNORECASE):
                country_candidate = 'US'
            addr_guess, city_guess = _tk_split_street_city(first_part)
            if addr_guess:
                address1 = addr_guess
            if len(parts) >= 2 and parts[1]:
                city = parts[1].strip()
            if (not city) and city_guess:
                city = city_guess
            if state_candidate:
                state = state_candidate
            if zip_candidate:
                zipcode = zip_candidate
            if country_candidate:
                country_code = country_candidate
            if zipcode or state:
                parsed_from_multi_parts = True
        if (not parsed_from_multi_parts) and len(parts) >= 3:
            p2 = parts[1]
            p3 = parts[2]
            if re.match(r'^[A-Za-z]{2}\s+\d{4,10}(?:-\d{3,4})?$', p3.strip()):
                addr_tail, city_tail = _tk_guess_city_from_street_tail(first_part)
                city = city_tail if city_tail else p2.strip()
                if addr_tail:
                    address1 = addr_tail
                state = p3.strip().split()[0]
                zipcode = p3.strip().split()[-1]
                country_code = 'US'
            else:
                state = p2
                zipcode, country_name = _tk_extract_zip_and_country(p3)
                country_code = _tk_country_to_iso2(country_name) if country_name else ''
                addr_guess, city_guess = _tk_split_street_city(first_part)
                if addr_guess:
                    address1 = addr_guess
                city = city_guess
                if not city:
                    addr_tail, city_tail = _tk_guess_city_from_tail(first_part)
                    if city_tail:
                        city = city_tail
                        if addr_tail:
                            address1 = addr_tail
        elif len(parts) == 2:
            p2 = parts[1]
            if re.match(r'^[A-Za-z]{2}\s+\d{4,10}(?:-\d{3,4})?$', p2.strip()):
                state = p2.strip().split()[0]
                zipcode = p2.strip().split()[-1]
                country_code = 'US'
                addr_guess, city_guess = _tk_split_street_city(first_part)
                if addr_guess:
                    address1 = addr_guess
                city = city_guess
            else:
                state = p2
                addr_guess, city_guess = _tk_split_street_city(first_part)
                if addr_guess:
                    address1 = addr_guess
                city = city_guess
                if not city:
                    addr_tail, city_tail = _tk_guess_city_from_tail(first_part)
                    if city_tail:
                        city = city_tail
                        if addr_tail:
                            address1 = addr_tail
        else:
            prefix_no_tail, state_tail, zip_tail = _tk_extract_state_zip_tail(first_part)
            if state_tail and zip_tail:
                state = state_tail
                zipcode = zip_tail
                country_code = 'US'
                work_part = prefix_no_tail
            else:
                work_part = first_part
            addr_guess, city_guess = _tk_split_street_city(work_part)
            if addr_guess:
                address1 = addr_guess
            city = city_guess
            if not city:
                addr_tail, city_tail = _tk_guess_city_from_tail(work_part)
                if city_tail:
                    city = city_tail
                    if addr_tail:
                        address1 = addr_tail
    house_match = re.match(r'^(\d+[A-Za-z\-]*)\b', address1)
    if house_match:
        house_no = house_match.group(1)
    if not zipcode:
        zipcode = _tk_extract_us_zip_anywhere(location_part) or _tk_extract_us_zip_anywhere(raw)
    if (not state) and location_part:
        state_guess, _, _ = _tk_extract_us_state_with_span(location_part)
        if state_guess:
            state = state_guess
    if not country_code and (zipcode or state or re.search(r'united\s+states|usa|\bus\b', raw, flags=re.IGNORECASE)):
        country_code = 'US'
    if (not receiver) or (not address1) or (not city) or (not zipcode):
        fb = _tk_fallback_parse_us_address(raw, phone)
        if not receiver:
            receiver = fb.get('receiver', '')
        if not phone:
            phone = fb.get('phone', '')
        if not address1:
            address1 = fb.get('address1', '')
        if not city:
            city = fb.get('city', '')
        if not state:
            state = fb.get('state', '')
        if not zipcode:
            zipcode = fb.get('zipcode', '')
        if not country_code:
            country_code = fb.get('country_code', '')
        if not house_no:
            house_match_fb = re.match(r'^(\d+[A-Za-z\-]*)\b', str(address1 or ''))
            if house_match_fb:
                house_no = house_match_fb.group(1)
    state_codes = {
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
    }
    raw_state = str(state or '').strip()
    state_norm, _, _ = _tk_extract_us_state_with_span(raw_state)
    if state_norm:
        state = state_norm
    else:
        upper_state = raw_state.upper()
        m_state = re.search(r'(?<![A-Za-z])([A-Z]{2})(?![A-Za-z])', upper_state)
        if m_state and m_state.group(1) in state_codes:
            state = m_state.group(1)
    if str(state or '').strip().upper() not in state_codes:
        fb_state = _tk_fallback_parse_us_address(raw, phone).get('state', '').strip().upper()
        if fb_state in state_codes:
            state = fb_state
    return {
        'receiver': receiver,
        'phone': phone,
        'address1': address1,
        'short_address': address1,
        'city': city,
        'state': state,
        'country_code': country_code,
        'zipcode': zipcode,
        'house_no': house_no
    }


def _tk_validate_export_address(raw_address, parsed, order_no):
    errs = []
    raw = str(raw_address or '').strip()
    order_no = str(order_no or '').strip()
    if not order_no:
        errs.append('订单号为空')
    if not raw or raw in {'0', '00', '000', '-'}:
        errs.append('网红地址为空或无效')
    if not parsed.get('receiver'):
        errs.append('未识别收件人')
    if not parsed.get('address1'):
        errs.append('未识别地址1')
    if not parsed.get('city'):
        errs.append('未识别城市')
    if not parsed.get('zipcode'):
        errs.append('未识别邮编')
    return errs


def _tk_parse_structured_export_address(raw_address):
    text = str(raw_address or '').strip()
    parts = [p.strip() for p in text.replace('，', ',').split(',') if str(p).strip()]
    if len(parts) < 7:
        return {}
    return {
        'receiver': parts[0],
        'phone': parts[1],
        'address1': parts[2],
        'city': parts[3],
        'state': parts[4],
        'country': parts[5],
        'zipcode': parts[6]
    }


def _tk_normalize_export_phone(phone_text):
    digits = re.sub(r'\D', '', str(phone_text or ''))
    if not digits:
        return '0000000000'
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    elif len(digits) > 10:
        digits = digits[-10:]
    return digits or '0000000000'


def _tk_normalize_export_country(country_text):
    c = str(country_text or '').strip()
    if not c:
        return ''
    if len(c) == 2 and c.isalpha():
        return c.upper()
    return _tk_country_to_iso2(c)


def _tk_refine_export_address_city(address1, city):
    addr = str(address1 or '').strip()
    city_text = str(city or '').strip()
    if not city_text:
        return addr, city_text
    tokens = [t for t in city_text.split() if t]
    if not tokens:
        return addr, ''
    street_words = {
        'st', 'street', 'rd', 'road', 'ave', 'avenue', 'blvd', 'boulevard', 'dr', 'drive',
        'ln', 'lane', 'ct', 'court', 'cir', 'circle', 'pl', 'place', 'pkwy', 'parkway',
        'way', 'trl', 'trail', 'hwy', 'highway', 'ter', 'terrace'
    }
    direction_words = {'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'north', 'south', 'east', 'west'}
    norm_tokens = [re.sub(r'[^a-zA-Z]', '', t).lower() for t in tokens]
    should_move_to_addr = False
    if len(tokens) == 1:
        one = norm_tokens[0]
        if (not one) or one in street_words or one in direction_words or len(one) <= 1:
            should_move_to_addr = True
    elif len(tokens) == 2:
        first = norm_tokens[0]
        second = norm_tokens[1]
        if (first in direction_words and second in street_words) or (first in street_words and second in street_words):
            should_move_to_addr = True
    if should_move_to_addr:
        merged = (addr + ' ' + city_text).strip() if addr else city_text
        return re.sub(r'\s+', ' ', merged).strip(), ''
    return addr, city_text


def _tk_guess_city_from_export_text(raw_address, address1='', state='', zipcode=''):
    text = str(raw_address or '').replace('\u00A0', ' ').replace('\u3000', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ''
    state_code = str(state or '').strip().upper()
    zip_code = str(zipcode or '').strip()
    city_candidate = ''
    if state_code:
        if zip_code:
            p = re.compile(rf"([A-Za-z][A-Za-z\s\.\-']{{1,50}}?)\s*,?\s*{re.escape(state_code)}\s+{re.escape(zip_code)}", re.IGNORECASE)
            m = p.search(text)
            if m:
                city_candidate = str(m.group(1) or '').split(',')[-1].strip()
        if not city_candidate:
            p = re.compile(rf"([A-Za-z][A-Za-z\s\.\-']{{1,50}}?)\s*,?\s*{re.escape(state_code)}\s+\d{{5}}(?:-\d{{4}})?", re.IGNORECASE)
            m = p.search(text)
            if m:
                city_candidate = str(m.group(1) or '').split(',')[-1].strip()
    if (not city_candidate) and address1:
        addr = re.sub(r'\s+', ' ', str(address1)).strip()
        if addr and addr.lower() in text.lower():
            pos = text.lower().find(addr.lower())
            tail = text[pos + len(addr):].strip(' ,')
            if tail:
                seg = tail.split(',')[0].strip()
                if seg and re.search(r'[A-Za-z]', seg):
                    city_candidate = seg
    if city_candidate:
        city_candidate = re.sub(r'[^A-Za-z\s\.\-]', ' ', city_candidate)
        city_candidate = re.sub(r'\s+', ' ', city_candidate).strip(" .,-'")
    if not city_candidate or len(city_candidate) < 2:
        return ''
    street_words = {
        'st', 'street', 'rd', 'road', 'ave', 'avenue', 'blvd', 'boulevard', 'dr', 'drive',
        'ln', 'lane', 'ct', 'court', 'cir', 'circle', 'pl', 'place', 'pkwy', 'parkway',
        'way', 'trl', 'trail', 'hwy', 'highway', 'ter', 'terrace'
    }
    tokens = [re.sub(r'[^a-zA-Z]', '', t).lower() for t in city_candidate.split() if t]
    if tokens and all(t in street_words for t in tokens):
        return ''
    return city_candidate


def _tk_prepare_export_contact_fields(raw_address, parsed):
    structured = _tk_parse_structured_export_address(raw_address)
    receiver = str(parsed.get('receiver') or '').strip()
    phone = str(parsed.get('phone') or '').strip()
    address1 = str(parsed.get('address1') or '').strip()
    city = str(parsed.get('city') or '').strip()
    state = str(parsed.get('state') or '').strip()
    country = str(parsed.get('country_code') or '').strip()
    zipcode = str(parsed.get('zipcode') or '').strip()
    if structured:
        receiver = receiver or structured.get('receiver', '')
        phone = phone or structured.get('phone', '')
        address1 = address1 or structured.get('address1', '')
        city = city or structured.get('city', '')
        state = state or structured.get('state', '')
        country = country or structured.get('country', '')
        zipcode = zipcode or structured.get('zipcode', '')
    country = _tk_normalize_export_country(country)
    if not country and structured:
        country = _tk_normalize_export_country(structured.get('country', ''))
    address1, city = _tk_refine_export_address_city(address1, city)
    if not city:
        city = _tk_guess_city_from_export_text(raw_address, address1=address1, state=state, zipcode=zipcode)
    if city:
        city = re.sub(r'\s+', ' ', str(city)).strip()
    return {
        'receiver': receiver,
        'phone': _tk_normalize_export_phone(phone),
        'address1': address1,
        'city': city,
        'state': state,
        'country': country,
        'zipcode': zipcode
    }


def _tk_parse_shop_names_from_request():
    vals = request.args.getlist('shops') or []
    shop_name = (request.args.get('shop_name') or '').strip()
    if shop_name:
        vals.append(shop_name)
    result = []
    seen = set()
    for v in vals:
        if v is None:
            continue
        for p in str(v).replace('，', ',').split(','):
            s = p.strip()
            if not s or s.upper() == 'ALL':
                continue
            if s in seen:
                continue
            seen.add(s)
            result.append(s)
    return result


def _tk_parse_importers_from_request():
    vals = request.args.getlist('importers') or []
    importer_name = (request.args.get('importer_name') or '').strip()
    if importer_name:
        vals.append(importer_name)
    result = []
    seen = set()
    for v in vals:
        if v is None:
            continue
        for p in str(v).replace('，', ',').split(','):
            s = p.strip()
            if not s or s.upper() == 'ALL':
                continue
            if s in seen:
                continue
            seen.add(s)
            result.append(s)
    return result


def _tk_parse_order_nos_from_request():
    vals = request.args.getlist('order_nos') or []
    order_no = (request.args.get('order_no') or '').strip()
    if order_no:
        vals.append(order_no)
    result = []
    seen = set()
    for v in vals:
        if v is None:
            continue
        for p in str(v).replace('，', ',').split(','):
            s = p.strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            result.append(s)
    return result


def _tk_customer_service_query_rows(start_date, end_date, shop_names=None, importer_names=None, order_nos=None):
    start_safe = start_date.replace("'", "''")
    end_safe = end_date.replace("'", "''")
    shop_names = shop_names or []
    importer_names = importer_names or []
    order_nos = order_nos or []
    shop_filter = ""
    importer_filter = ""
    order_filter = ""
    if shop_names:
        safe_vals = []
        for s in shop_names:
            safe_vals.append("'" + str(s).replace("'", "''") + "'")
        shop_filter = f" AND ISNULL(CAST(zd.dian AS NVARCHAR(100)), '') IN ({', '.join(safe_vals)})"
    if importer_names:
        safe_vals = []
        for s in importer_names:
            safe_vals.append("'" + str(s).replace("'", "''") + "'")
        importer_filter = f"""
          AND (
                CASE
                    WHEN CHARINDEX('@', ISNULL(CAST(hz.DaoRuRen AS NVARCHAR(200)), '')) > 0
                        THEN LTRIM(RTRIM(RIGHT(
                            ISNULL(CAST(hz.DaoRuRen AS NVARCHAR(200)), ''),
                            CHARINDEX('@', REVERSE(ISNULL(CAST(hz.DaoRuRen AS NVARCHAR(200)), ''))) - 1
                        )))
                    ELSE LTRIM(RTRIM(ISNULL(CAST(hz.DaoRuRen AS NVARCHAR(200)), '')))
                END
              ) IN ({', '.join(safe_vals)})
        """
    if order_nos:
        conds = []
        for s in order_nos:
            s_safe = str(s).replace("'", "''")
            conds.append(
                f"CHARINDEX('{s_safe}', ISNULL(CAST(hz.FaYangDingDanHao AS NVARCHAR(100)), '')) > 0"
            )
        order_filter = " AND (" + " OR ".join(conds) + ")"
    sql = f"""
        SELECT
            hz.SKU,
            zl.wanghongdizhi,
            zd.dian,
            hz.ID,
            hz.DaoRuRen,
            hz.DaoRuShiJian,
            hz.FaYangDingDanHao,
            dd.GenZongHao,
            dd.kefubeizhu,
            dd.fahuoshijian
        FROM TK_WangHong_HeZuo hz
        LEFT JOIN TK_WangHong_ZiLiao zl
            ON hz.BianHao = zl.BianHao
        LEFT JOIN ZiDian zd
            ON hz.SKU = zd.SKU
        LEFT JOIN (
            SELECT
                UPPER(LTRIM(RTRIM(ISNULL(CAST(DanHao AS NVARCHAR(100)), '')))) AS join_danhao,
                UPPER(LTRIM(RTRIM(ISNULL(CAST(SKU AS NVARCHAR(100)), '')))) AS join_sku,
                MAX(ISNULL(GenZongHao, '')) AS GenZongHao,
                MAX(ISNULL(kefubeizhu, '')) AS kefubeizhu,
                MAX(fahuoshijian) AS fahuoshijian
            FROM TK_DingDan_shouhou
            GROUP BY
                UPPER(LTRIM(RTRIM(ISNULL(CAST(DanHao AS NVARCHAR(100)), '')))),
                UPPER(LTRIM(RTRIM(ISNULL(CAST(SKU AS NVARCHAR(100)), ''))))
        ) dd
            ON UPPER(LTRIM(RTRIM(ISNULL(CAST(hz.FaYangDingDanHao AS NVARCHAR(100)), '')))) = dd.join_danhao
           AND UPPER(LTRIM(RTRIM(ISNULL(CAST(hz.SKU AS NVARCHAR(100)), '')))) = dd.join_sku
        WHERE CAST(hz.DaoRuShiJian AS date) BETWEEN '{start_safe}' AND '{end_safe}'
          AND ISNULL(hz.FaYangDingDanHao, '') <> ''
          AND CHARINDEX('57', ISNULL(CAST(hz.FaYangDingDanHao AS NVARCHAR(100)), '')) = 0
          AND CHARINDEX('TKWS', UPPER(ISNULL(CAST(hz.SKU AS NVARCHAR(100)), ''))) = 0
          {shop_filter}
          {importer_filter}
          {order_filter}
        ORDER BY hz.ID DESC
    """
    rows = sf_db(sql) or []
    cols = ['SKU', 'wanghongdizhi', 'dian', 'ID', 'DaoRuRen', 'DaoRuShiJian', 'FaYangDingDanHao', 'GenZongHao', 'kefubeizhu', 'fahuoshijian']
    items = []
    for r in rows:
        if isinstance(r, dict):
            item = {}
            for k in cols:
                item[k] = r.get(k) if k in r else r.get(k.lower())
        elif isinstance(r, (list, tuple)):
            item = {cols[i]: (r[i] if i < len(r) else None) for i in range(len(cols))}
        else:
            item = {}
        for k in ['SKU', 'wanghongdizhi', 'dian', 'DaoRuRen', 'FaYangDingDanHao', 'GenZongHao', 'kefubeizhu']:
            v = item.get(k)
            item[k] = '' if v is None else str(v)
        import_user = item.get('DaoRuRen', '')
        if '@' in import_user:
            import_tail = import_user.split('@')[-1].strip()
            if import_tail:
                item['DaoRuRen'] = import_tail
        if not (item.get('kefubeizhu') or '').strip():
            id_text = '' if item.get('ID') is None else str(item.get('ID')).strip()
            importer_text = (item.get('DaoRuRen') or '').strip()
            fallback_parts = []
            if id_text:
                fallback_parts.append(f"ID:{id_text}")
            if importer_text:
                fallback_parts.append(f"导入人:{importer_text}")
            item['kefubeizhu'] = ' '.join(fallback_parts)
        t_import = item.get('DaoRuShiJian')
        if isinstance(t_import, datetime):
            item['DaoRuShiJian'] = t_import.strftime('%Y-%m-%d %H:%M:%S')
        else:
            item['DaoRuShiJian'] = '' if t_import is None else str(t_import)
        t_ship = item.get('fahuoshijian')
        if isinstance(t_ship, datetime):
            item['fahuoshijian'] = t_ship.strftime('%Y-%m-%d %H:%M:%S')
        else:
            item['fahuoshijian'] = '' if t_ship is None else str(t_ship)
        items.append(item)
    return items


@app.route('/api/tk_customer_service/list', methods=['GET'])
@require_permission('tk_customer_service')
def api_tk_customer_service_list():
    try:
        default_day = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (request.args.get('start_date') or default_day).strip()
        end_date = (request.args.get('end_date') or default_day).strip()
        shop_names = _tk_parse_shop_names_from_request()
        importer_names = _tk_parse_importers_from_request()
        order_nos = _tk_parse_order_nos_from_request()
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except Exception:
            return jsonify({'success': False, 'message': '日期格式错误，应为YYYY-MM-DD'}), 400
        items = _tk_customer_service_query_rows(start_date, end_date, shop_names, importer_names, order_nos)
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取TK客服数据失败: {str(e)}'}), 500


@app.route('/api/tk_customer_service/shops', methods=['GET'])
@require_permission('tk_customer_service')
def api_tk_customer_service_shops():
    try:
        default_day = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (request.args.get('start_date') or default_day).strip()
        end_date = (request.args.get('end_date') or default_day).strip()
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except Exception:
            return jsonify({'success': False, 'message': '日期格式错误，应为YYYY-MM-DD'}), 400
        rows = _tk_customer_service_query_rows(start_date, end_date, [])
        shops = []
        for r in rows:
            v = r.get('dian') if isinstance(r, dict) else ''
            s = '' if v is None else str(v).strip()
            if s:
                shops.append(s)
        shops = sorted(list(set(shops)), key=lambda x: str(x))
        return jsonify({'success': True, 'shops': shops})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取店铺列表失败: {str(e)}'}), 500


@app.route('/api/tk_customer_service/export', methods=['GET'])
@require_permission('tk_customer_service')
def api_tk_customer_service_export():
    try:
        default_day = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (request.args.get('start_date') or default_day).strip()
        end_date = (request.args.get('end_date') or default_day).strip()
        shop_names = _tk_parse_shop_names_from_request()
        importer_names = _tk_parse_importers_from_request()
        order_nos = _tk_parse_order_nos_from_request()
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except Exception:
            return jsonify({'success': False, 'message': '日期格式错误，应为YYYY-MM-DD'}), 400
        items = _tk_customer_service_query_rows(start_date, end_date, shop_names, importer_names, order_nos)
        headers = [
            '*订单号', '*店铺名称', '*sku', '*数量', '*单价', '买家运费', '币种（默认USD）', '买家指定物流', '下单时间', '发货截止时间', '发货仓库', 'IOSS税号', '买家留言',
            '*收件人', '*地址1', '地址2', '短地址', '*城市', '州/省', '区/县', '*国家二字码', '*邮编', '电话', '手机', '邮箱', '税号', '门牌号', '订单备注',
            '中文报关名', '英文报关名', '申报金额（USD）', '申报重量（g）', '材质', '用途', '海关编码', '报关属性', '业务员', '交易方式', '买方公司'
        ]
        export_rows = []
        error_rows = []
        for item in items:
            parsed = _tk_parse_wanghong_address(item.get('wanghongdizhi', ''))
            raw_address = item.get('wanghongdizhi', '')
            order_no = item.get('FaYangDingDanHao', '')
            errors = _tk_validate_export_address(raw_address, parsed, order_no)
            if errors:
                error_rows.append({
                    '订单号': order_no,
                    'SKU': item.get('SKU', ''),
                    '店铺': item.get('dian', ''),
                    '客服备注': item.get('kefubeizhu', ''),
                    '网红地址原文': raw_address,
                    '错误原因': '；'.join(errors)
                })
                continue
            shop_raw = str(item.get('dian') or '').strip()
            shop_label = f"{shop_raw}（自发货）" if shop_raw else ''
            export_contact = _tk_prepare_export_contact_fields(raw_address, parsed)
            export_rows.append({
                '*订单号': order_no,
                '*店铺名称': shop_label,
                '*sku': item.get('SKU', ''),
                '*数量': 1,
                '*单价': 0,
                '买家运费': '',
                '币种（默认USD）': 'USD',
                '买家指定物流': '',
                '下单时间': '',
                '发货截止时间': '',
                '发货仓库': '',
                'IOSS税号': '',
                '买家留言': '',
                '*收件人': export_contact.get('receiver', ''),
                '*地址1': export_contact.get('address1', ''),
                '地址2': '',
                '短地址': str(raw_address or '').strip(),
                '*城市': export_contact.get('city', ''),
                '州/省': export_contact.get('state', ''),
                '区/县': '',
                '*国家二字码': export_contact.get('country', '') or 'US',
                '*邮编': export_contact.get('zipcode', ''),
                '电话': export_contact.get('phone', ''),
                '手机': '',
                '邮箱': '',
                '税号': '',
                '门牌号': '',
                '订单备注': item.get('kefubeizhu', ''),
                '中文报关名': '',
                '英文报关名': '',
                '申报金额（USD）': '',
                '申报重量（g）': '',
                '材质': '',
                '用途': '',
                '海关编码': '',
                '报关属性': '',
                '业务员': '',
                '交易方式': '',
                '买方公司': ''
            })
        import pandas as pd
        from io import BytesIO
        df = pd.DataFrame(export_rows, columns=headers)
        output = BytesIO()
        error_headers = ['订单号', 'SKU', '店铺', '客服备注', '网红地址原文', '错误原因']
        error_df = pd.DataFrame(error_rows, columns=error_headers)
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='正确数据')
            error_df.to_excel(writer, index=False, sheet_name='导出错误列表')
        output.seek(0)
        now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"TK客服导出_{start_date}_to_{end_date}_{now_str}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'导出失败: {str(e)}'}), 500


@app.route('/api/tk_customer_service/update_note', methods=['POST'])
@require_permission('tk_customer_service')
def api_tk_customer_service_update_note():
    try:
        data = request.get_json(silent=True) or {}
        order_no = str(data.get('FaYangDingDanHao') or '').strip()
        sku = str(data.get('SKU') or '').strip()
        note = str(data.get('kefubeizhu') or '')
        if not order_no:
            return jsonify({'success': False, 'message': '发样订单号不能为空'}), 400
        if not sku:
            return jsonify({'success': False, 'message': 'SKU不能为空'}), 400
        order_no_safe = order_no.replace("'", "''")
        sku_safe = sku.replace("'", "''")
        note_safe = note.replace("'", "''")
        upsert_sql = (
            "IF EXISTS ("
            "    SELECT 1 FROM TK_DingDan_shouhou "
            f"    WHERE UPPER(LTRIM(RTRIM(ISNULL(CAST(DanHao AS NVARCHAR(100)), '')))) = UPPER(LTRIM(RTRIM('{order_no_safe}'))) "
            f"      AND UPPER(LTRIM(RTRIM(ISNULL(CAST(SKU AS NVARCHAR(100)), '')))) = UPPER(LTRIM(RTRIM('{sku_safe}')))"
            ") "
            "BEGIN "
            "    UPDATE TK_DingDan_shouhou "
            f"    SET kefubeizhu = '{note_safe}' "
            f"    WHERE UPPER(LTRIM(RTRIM(ISNULL(CAST(DanHao AS NVARCHAR(100)), '')))) = UPPER(LTRIM(RTRIM('{order_no_safe}'))) "
            f"      AND UPPER(LTRIM(RTRIM(ISNULL(CAST(SKU AS NVARCHAR(100)), '')))) = UPPER(LTRIM(RTRIM('{sku_safe}'))) "
            "END "
            "ELSE "
            "BEGIN "
            "    INSERT INTO TK_DingDan_shouhou (DanHao, SKU, kefubeizhu) "
            f"    VALUES ('{order_no_safe}', '{sku_safe}', '{note_safe}') "
            "END"
        )
        dui_db(upsert_sql)
        return jsonify({'success': True, 'message': '客服备注保存成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'更新客服备注失败: {str(e)}'}), 500


@app.route('/tk_invite_monitor')
@require_permission('tk_project_group')
def tk_invite_monitor():
    """邀请ID实时监控上传页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('tk_invite_monitor.html', user_name=user_name, user_id=user_id)


@app.route('/tk_monthly_target_import')
@require_permission('tk_project_group')
def tk_monthly_target_import():
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('tk_monthly_target_import.html', user_name=user_name, user_id=user_id)


@app.route('/tk_video_realtime')
@require_permission('tk_video_realtime')
def tk_video_realtime():
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('tk_video_realtime.html', user_name=user_name, user_id=user_id)


@app.route('/tk_video_realtime_account_links')
@require_permission('tk_video_realtime')
def tk_video_realtime_account_links():
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('tk_video_realtime_account_links.html', user_name=user_name, user_id=user_id)


def _tk_video_realtime_sql_text(value):
    return str(value or '').strip().replace("'", "''")


def _tk_video_realtime_pick(row, key):
    if isinstance(row, dict):
        return row.get(key) if key in row else row.get(key.upper())
    return None


@app.route('/api/tk_video_realtime/account_links')
@require_permission('tk_video_realtime')
def api_tk_video_realtime_account_links():
    try:
        rows = sf_db(
            "SELECT DISTINCT dian, daren, fuzeren "
            "FROM TK_ZiYouZhangHao "
            "WHERE ISNULL(LTRIM(RTRIM(daren)), '') <> '' "
            "ORDER BY dian, fuzeren, daren"
        ) or []
        items = []
        for row in rows:
            if isinstance(row, dict):
                item = {
                    'dian': str(_tk_video_realtime_pick(row, 'dian') or '').strip(),
                    'daren': str(_tk_video_realtime_pick(row, 'daren') or '').strip(),
                    'fuzeren': str(_tk_video_realtime_pick(row, 'fuzeren') or '').strip(),
                }
            elif isinstance(row, (list, tuple)):
                item = {
                    'dian': str(row[0] if len(row) > 0 and row[0] is not None else '').strip(),
                    'daren': str(row[1] if len(row) > 1 and row[1] is not None else '').strip(),
                    'fuzeren': str(row[2] if len(row) > 2 and row[2] is not None else '').strip(),
                }
            else:
                item = {'dian': '', 'daren': '', 'fuzeren': ''}
            if not item['daren']:
                continue
            items.append(item)
        return jsonify({'success': True, 'data': {'items': items}})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取店铺负责人列表失败: {str(e)}'}), 500


@app.route('/api/tk_video_realtime/account_links/save', methods=['POST'])
@require_permission('tk_video_realtime')
def api_tk_video_realtime_account_links_save():
    try:
        data = request.get_json(silent=True) or {}
        dian = str(data.get('dian') or '').strip()
        daren = str(data.get('daren') or '').strip()
        fuzeren = str(data.get('fuzeren') or '').strip()
        original_dian = str(data.get('original_dian') or '').strip()
        original_daren = str(data.get('original_daren') or '').strip()
        original_fuzeren = str(data.get('original_fuzeren') or '').strip()

        if not dian:
            return jsonify({'success': False, 'message': '店铺不能为空'}), 400
        if not daren:
            return jsonify({'success': False, 'message': '账号不能为空'}), 400
        if not fuzeren:
            return jsonify({'success': False, 'message': '负责人不能为空'}), 400

        esc_dian = _tk_video_realtime_sql_text(dian)
        esc_daren = _tk_video_realtime_sql_text(daren)
        esc_fuzeren = _tk_video_realtime_sql_text(fuzeren)
        esc_original_dian = _tk_video_realtime_sql_text(original_dian)
        esc_original_daren = _tk_video_realtime_sql_text(original_daren)
        esc_original_fuzeren = _tk_video_realtime_sql_text(original_fuzeren)

        exists_sql = (
            "SELECT COUNT(1) AS total "
            "FROM TK_ZiYouZhangHao "
            f"WHERE dian = N'{esc_dian}' AND daren = N'{esc_daren}' AND fuzeren = N'{esc_fuzeren}'"
        )
        exists_count = int(sf_db(exists_sql, single=True) or 0)

        if original_daren:
            update_sql = f"""
            UPDATE TK_ZiYouZhangHao
            SET dian = N'{esc_dian}',
                daren = N'{esc_daren}',
                fuzeren = N'{esc_fuzeren}'
            WHERE ISNULL(dian, '') = N'{esc_original_dian}'
              AND ISNULL(daren, '') = N'{esc_original_daren}'
              AND ISNULL(fuzeren, '') = N'{esc_original_fuzeren}'
            """
            dui_db(update_sql)
            action = 'updated'
        else:
            if exists_count > 0:
                return jsonify({'success': False, 'message': '相同的店铺、账号、负责人记录已存在'}), 400
            insert_sql = (
                "INSERT INTO TK_ZiYouZhangHao (dian, daren, fuzeren) "
                f"VALUES (N'{esc_dian}', N'{esc_daren}', N'{esc_fuzeren}')"
            )
            dui_db(insert_sql)
            action = 'inserted'

        return jsonify({'success': True, 'message': '保存成功', 'data': {'action': action}})
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存店铺负责人失败: {str(e)}'}), 500


@app.route('/api/tk_video_realtime/account_links/delete', methods=['POST'])
@require_permission('tk_video_realtime')
def api_tk_video_realtime_account_links_delete():
    try:
        data = request.get_json(silent=True) or {}
        dian = str(data.get('dian') or '').strip()
        daren = str(data.get('daren') or '').strip()
        fuzeren = str(data.get('fuzeren') or '').strip()
        if not daren:
            return jsonify({'success': False, 'message': '缺少账号，无法删除'}), 400
        esc_dian = _tk_video_realtime_sql_text(dian)
        esc_daren = _tk_video_realtime_sql_text(daren)
        esc_fuzeren = _tk_video_realtime_sql_text(fuzeren)
        delete_sql = f"""
        DELETE FROM TK_ZiYouZhangHao
        WHERE ISNULL(dian, '') = N'{esc_dian}'
          AND ISNULL(daren, '') = N'{esc_daren}'
          AND ISNULL(fuzeren, '') = N'{esc_fuzeren}'
        """
        dui_db(delete_sql)
        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除店铺负责人失败: {str(e)}'}), 500


@app.route('/api/tk_video_realtime/shops')
@require_permission('tk_video_realtime')
def api_tk_video_realtime_shops():
    try:
        rows = sf_db(
            "SELECT DISTINCT dian FROM TK_ZiYouZhangHao "
            "WHERE dian IS NOT NULL AND LTRIM(RTRIM(dian)) <> '' "
            "ORDER BY dian"
        ) or []
        shops = []
        for r in rows:
            if isinstance(r, dict):
                v = r.get('dian') or r.get('DIAN') or ''
            elif isinstance(r, (list, tuple)) and r:
                v = r[0]
            else:
                v = r
            v = str(v).strip()
            if v:
                shops.append(v)
        return jsonify({'success': True, 'data': {'shops': shops}})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取店铺列表失败: {str(e)}'}), 500


@app.route('/api/tk_video_realtime/daren')
@require_permission('tk_video_realtime')
def api_tk_video_realtime_daren():
    try:
        def _parse_list_param(name, max_items=200):
            vals = request.args.getlist(name) or []
            parts = []
            for v in vals:
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                for p in s.replace('，', ',').split(','):
                    p = (p or '').strip()
                    if not p or p.upper() == 'ALL':
                        continue
                    parts.append(p)
            out = []
            seen = set()
            for p in parts:
                if p in seen:
                    continue
                seen.add(p)
                out.append(p)
                if len(out) >= max_items:
                    break
            return out

        dian_list = _parse_list_param('dian')
        fuzeren_list = _parse_list_param('fuzeren')
        where = "WHERE daren IS NOT NULL AND LTRIM(RTRIM(daren)) <> ''"
        if dian_list:
            dian_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in dian_list])
            where += f" AND dian IN ({dian_in})"
        if fuzeren_list:
            fuzeren_in = ", ".join([("'" + str(x).replace("'", "''") + "'") for x in fuzeren_list])
            where += f" AND fuzeren IN ({fuzeren_in})"
        rows = sf_db(
            "SELECT DISTINCT daren FROM TK_ZiYouZhangHao "
            f"{where} "
            "ORDER BY daren"
        ) or []
        daren_list = []
        for r in rows:
            if isinstance(r, dict):
                v = r.get('daren') or r.get('DAREN') or ''
            elif isinstance(r, (list, tuple)) and r:
                v = r[0]
            else:
                v = r
            v = str(v).strip()
            if v:
                daren_list.append(v)
        return jsonify({'success': True, 'data': {'daren': daren_list}})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取达人列表失败: {str(e)}'}), 500


@app.route('/api/tk_video_realtime/fuzeren')
@require_permission('tk_video_realtime')
def api_tk_video_realtime_fuzeren():
    try:
        def _parse_list_param(name, max_items=200):
            vals = request.args.getlist(name) or []
            parts = []
            for v in vals:
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                for p in s.replace('，', ',').split(','):
                    p = (p or '').strip()
                    if not p or p.upper() == 'ALL':
                        continue
                    parts.append(p)
            out = []
            seen = set()
            for p in parts:
                if p in seen:
                    continue
                seen.add(p)
                out.append(p)
                if len(out) >= max_items:
                    break
            return out

        dian_list = _parse_list_param('dian')
        daren_list = _parse_list_param('daren')
        where = "WHERE fuzeren IS NOT NULL AND LTRIM(RTRIM(fuzeren)) <> ''"
        if dian_list:
            dian_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in dian_list])
            where += f" AND dian IN ({dian_in})"
        if daren_list:
            daren_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in daren_list])
            where += f" AND daren IN ({daren_in})"
        rows = sf_db(
            "SELECT DISTINCT fuzeren FROM TK_ZiYouZhangHao "
            f"{where} "
            "ORDER BY fuzeren"
        ) or []
        fuzeren_list = []
        for r in rows:
            if isinstance(r, dict):
                v = r.get('fuzeren') or r.get('FUZEREN') or ''
            elif isinstance(r, (list, tuple)) and r:
                v = r[0]
            else:
                v = r
            v = str(v).strip()
            if v:
                fuzeren_list.append(v)
        return jsonify({'success': True, 'data': {'fuzeren': fuzeren_list}})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取负责人列表失败: {str(e)}'}), 500


@app.route('/api/tk_video_realtime/videos')
@require_permission('tk_video_realtime')
def api_tk_video_realtime_videos():
    try:
        def _parse_list_param(name, max_items=200):
            vals = request.args.getlist(name) or []
            parts = []
            for v in vals:
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                for p in s.replace('，', ',').split(','):
                    p = (p or '').strip()
                    if not p or p.upper() == 'ALL':
                        continue
                    parts.append(p)
            out = []
            seen = set()
            for p in parts:
                if p in seen:
                    continue
                seen.add(p)
                out.append(p)
                if len(out) >= max_items:
                    break
            return out

        dian_list = _parse_list_param('dian')
        daren_list = _parse_list_param('daren')
        fuzeren_list = _parse_list_param('fuzeren')
        created_start = (request.args.get('created_start') or '').strip()
        created_end = (request.args.get('created_end') or '').strip()
        view_range = (request.args.get('view_range') or '').strip()
        if created_start and (not re.match(r'^\d{4}-\d{2}-\d{2}$', created_start)):
            return jsonify({'success': False, 'message': '创建日期开始格式无效，应为YYYY-MM-DD'}), 400
        if created_end and (not re.match(r'^\d{4}-\d{2}-\d{2}$', created_end)):
            return jsonify({'success': False, 'message': '创建日期结束格式无效，应为YYYY-MM-DD'}), 400
        if created_start and created_end and created_start > created_end:
            return jsonify({'success': False, 'message': '创建日期开始不能晚于结束日期'}), 400
        valid_view_ranges = {'0_20000', '20000_100000', '100000_1000000', '1000000_plus'}
        if view_range and view_range not in valid_view_ranges:
            return jsonify({'success': False, 'message': '播放量区间参数无效'}), 400
        page = int(request.args.get('page') or 1)
        page_size = int(request.args.get('page_size') or 50)
        page = max(1, page)
        page_size = max(1, min(200, page_size))
        offset = (page - 1) * page_size

        def _parse_int_from_rows(rows, key):
            if not rows:
                return 0
            r0 = rows[0]
            if isinstance(r0, dict):
                return int(r0.get(key) or r0.get(key.upper()) or 0)
            if isinstance(r0, (list, tuple)) and r0:
                return int(r0[0] or 0)
            return int(r0 or 0)

        where_parts = ["l.rn = 1"]
        join_account_all_sql = "LEFT JOIN (SELECT daren, MAX(dian) AS dian, MAX(fuzeren) AS fuzeren FROM TK_ZiYouZhangHao GROUP BY daren) a ON a.daren = l.daren"
        join_account_filtered_sql = join_account_all_sql
        join_account_raw_filtered_sql = ""
        account_filters = []
        if dian_list:
            dian_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in dian_list])
            account_filters.append(f"dian IN ({dian_in})")
        if fuzeren_list:
            fuzeren_in = ", ".join([("'" + str(x).replace("'", "''") + "'") for x in fuzeren_list])
            account_filters.append(f"fuzeren IN ({fuzeren_in})")
        if account_filters:
            account_where_sql = " WHERE " + " AND ".join(account_filters)
            join_account_filtered_sql = (
                "INNER JOIN ("
                "  SELECT daren, MAX(dian) AS dian, MAX(fuzeren) AS fuzeren "
                "  FROM TK_ZiYouZhangHao "
                f"  {account_where_sql} "
                "  GROUP BY daren"
                ") a ON a.daren = l.daren"
            )
            join_account_raw_filtered_sql = (
                "INNER JOIN ("
                "  SELECT daren "
                "  FROM TK_ZiYouZhangHao "
                f"  {account_where_sql} "
                "  GROUP BY daren"
                ") a ON a.daren = v.daren"
            )
        if daren_list:
            daren_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in daren_list])
            where_parts.append(f"l.daren IN ({daren_in})")
        if created_start:
            where_parts.append(
                f"ISDATE(l.chuangjianshijian) = 1 AND CONVERT(datetime, l.chuangjianshijian) >= '{created_start} 00:00:00'"
            )
        if created_end:
            where_parts.append(
                f"ISDATE(l.chuangjianshijian) = 1 AND CONVERT(datetime, l.chuangjianshijian) <= '{created_end} 23:59:59'"
            )
        if view_range:
            view_num_l = "CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.bofangshu)), ',', '')) = 1 THEN CAST(REPLACE(LTRIM(RTRIM(l.bofangshu)), ',', '') AS float) ELSE -1 END"
            if view_range == '0_20000':
                where_parts.append(f"{view_num_l} >= 0 AND {view_num_l} < 20000")
            elif view_range == '20000_100000':
                where_parts.append(f"{view_num_l} >= 20000 AND {view_num_l} < 100000")
            elif view_range == '100000_1000000':
                where_parts.append(f"{view_num_l} >= 100000 AND {view_num_l} < 1000000")
            elif view_range == '1000000_plus':
                where_parts.append(f"{view_num_l} >= 1000000")
        where_sql = " AND ".join(where_parts)

        raw_where_parts = []
        if daren_list:
            daren_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in daren_list])
            raw_where_parts.append(f"v.daren IN ({daren_in})")
        if created_start:
            raw_where_parts.append(
                f"ISDATE(v.chuangjianshijian) = 1 AND CONVERT(datetime, v.chuangjianshijian) >= '{created_start} 00:00:00'"
            )
        if created_end:
            raw_where_parts.append(
                f"ISDATE(v.chuangjianshijian) = 1 AND CONVERT(datetime, v.chuangjianshijian) <= '{created_end} 23:59:59'"
            )
        if view_range:
            view_num_v = "CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(v.bofangshu)), ',', '')) = 1 THEN CAST(REPLACE(LTRIM(RTRIM(v.bofangshu)), ',', '') AS float) ELSE -1 END"
            if view_range == '0_20000':
                raw_where_parts.append(f"{view_num_v} >= 0 AND {view_num_v} < 20000")
            elif view_range == '20000_100000':
                raw_where_parts.append(f"{view_num_v} >= 20000 AND {view_num_v} < 100000")
            elif view_range == '100000_1000000':
                raw_where_parts.append(f"{view_num_v} >= 100000 AND {view_num_v} < 1000000")
            elif view_range == '1000000_plus':
                raw_where_parts.append(f"{view_num_v} >= 1000000")
        raw_where_sql = " AND ".join(raw_where_parts) if raw_where_parts else "1=1"
        order_where_parts = []
        if created_start:
            order_where_parts.append(
                f"ISDATE(o.chuangjianshijian) = 1 AND CONVERT(datetime, o.chuangjianshijian) >= '{created_start} 00:00:00'"
            )
        if created_end:
            order_where_parts.append(
                f"ISDATE(o.chuangjianshijian) = 1 AND CONVERT(datetime, o.chuangjianshijian) <= '{created_end} 23:59:59'"
            )
        order_where_sql = " AND ".join(order_where_parts) if order_where_parts else "1=1"
        total_raw_all = _parse_int_from_rows(
            sf_db("SELECT COUNT(1) AS total_raw_all FROM TK_ZiYouZhangHao_ShiPinShuJu") or [],
            "total_raw_all"
        )
        total_raw_filtered = _parse_int_from_rows(
            sf_db(
                "SELECT COUNT(1) AS total_raw_filtered "
                "FROM TK_ZiYouZhangHao_ShiPinShuJu v "
                f"{join_account_raw_filtered_sql} "
                f"WHERE {raw_where_sql}"
            ) or [],
            "total_raw_filtered"
        )

        count_rows = sf_db(
            "WITH latest AS ("
            "  SELECT v.*, ROW_NUMBER() OVER ("
            "    PARTITION BY v.daren, v.shipinid "
            "    ORDER BY "
            "      CASE "
            "        WHEN v.xuhao IS NULL THEN 0 "
            "        WHEN PATINDEX('%%[^0-9]%%', LTRIM(RTRIM(CAST(v.xuhao AS varchar(50))))) = 0 "
            "          THEN CAST(LTRIM(RTRIM(CAST(v.xuhao AS varchar(50)))) AS bigint) "
            "        ELSE 0 "
            "      END DESC, "
            "      v.zhuaqushijian DESC"
            "  ) AS rn "
            "  FROM TK_ZiYouZhangHao_ShiPinShuJu v"
            ") "
            "SELECT COUNT(1) AS total "
            "FROM latest l "
            f"{join_account_filtered_sql} "
            f"WHERE {where_sql}"
        ) or []
        total = _parse_int_from_rows(count_rows, 'total')

        def _parse_agg_row(row):
            if not row:
                return {
                    'video_count': 0,
                    'sum_duration_seconds': 0.0,
                    'sum_likes': 0.0,
                    'sum_views': 0.0,
                    'sum_jine': 0.0,
                    'sum_purchase_count': 0,
                    'sum_comments': 0.0,
                    'sum_favorites': 0.0,
                    'sum_shares': 0.0,
                }
            if isinstance(row, dict):
                getv = lambda k: row.get(k) if k in row else row.get(k.upper())
                return {
                    'video_count': int(getv('video_count') or 0),
                    'sum_duration_seconds': float(getv('sum_duration_seconds') or 0),
                    'sum_likes': float(getv('sum_likes') or 0),
                    'sum_views': float(getv('sum_views') or 0),
                    'sum_jine': float(getv('sum_jine') or 0),
                    'sum_purchase_count': int(getv('sum_purchase_count') or 0),
                    'sum_comments': float(getv('sum_comments') or 0),
                    'sum_favorites': float(getv('sum_favorites') or 0),
                    'sum_shares': float(getv('sum_shares') or 0),
                }
            if isinstance(row, (list, tuple)):
                vals = list(row) + [0] * 9
                return {
                    'video_count': int(vals[0] or 0),
                    'sum_duration_seconds': float(vals[1] or 0),
                    'sum_likes': float(vals[2] or 0),
                    'sum_views': float(vals[3] or 0),
                    'sum_jine': float(vals[4] or 0),
                    'sum_purchase_count': int(vals[5] or 0),
                    'sum_comments': float(vals[6] or 0),
                    'sum_favorites': float(vals[7] or 0),
                    'sum_shares': float(vals[8] or 0),
                }
            return {
                'video_count': 0,
                'sum_duration_seconds': 0.0,
                'sum_likes': 0.0,
                'sum_views': 0.0,
                'sum_jine': 0.0,
                'sum_purchase_count': 0,
                'sum_comments': 0.0,
                'sum_favorites': 0.0,
                'sum_shares': 0.0,
            }

        agg_sql_base = (
            "WITH latest AS ("
            "  SELECT v.*, ROW_NUMBER() OVER ("
            "    PARTITION BY v.daren, v.shipinid "
            "    ORDER BY "
            "      CASE "
            "        WHEN v.xuhao IS NULL THEN 0 "
            "        WHEN PATINDEX('%%[^0-9]%%', LTRIM(RTRIM(CAST(v.xuhao AS varchar(50))))) = 0 "
            "          THEN CAST(LTRIM(RTRIM(CAST(v.xuhao AS varchar(50)))) AS bigint) "
            "        ELSE 0 "
            "      END DESC, "
            "      v.zhuaqushijian DESC"
            "  ) AS rn "
            "  FROM TK_ZiYouZhangHao_ShiPinShuJu v"
            "), order_sum AS ("
            "  SELECT "
            "    LTRIM(RTRIM(CAST(o.shipinid AS varchar(100)))) AS shipinid_key, "
            "    COUNT(1) AS purchase_count, "
            "    SUM(CASE "
            "      WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(CAST(o.jine AS varchar(100)))), ',', '')) = 1 "
            "        THEN CAST(REPLACE(LTRIM(RTRIM(CAST(o.jine AS varchar(100)))), ',', '') AS float) "
            "      ELSE 0 END) AS jine_sum "
            "  FROM tk_bddingdan o "
            f"  WHERE {order_where_sql} "
            "  GROUP BY LTRIM(RTRIM(CAST(o.shipinid AS varchar(100))))"
            ") "
            "SELECT "
            "  COUNT(1) AS video_count, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.shichang)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.shichang)), ',', '') AS float) ELSE 0 END) AS sum_duration_seconds, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.dianzanshu)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.dianzanshu)), ',', '') AS float) ELSE 0 END) AS sum_likes, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.bofangshu)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.bofangshu)), ',', '') AS float) ELSE 0 END) AS sum_views, "
            "  SUM(ISNULL(os.jine_sum, 0)) AS sum_jine, "
            "  SUM(ISNULL(os.purchase_count, 0)) AS sum_purchase_count, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.pinglunshu)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.pinglunshu)), ',', '') AS float) ELSE 0 END) AS sum_comments, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.shoucangshu)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.shoucangshu)), ',', '') AS float) ELSE 0 END) AS sum_favorites, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.fenxiangshu)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.fenxiangshu)), ',', '') AS float) ELSE 0 END) AS sum_shares "
            "FROM latest l "
            "LEFT JOIN order_sum os ON os.shipinid_key = LTRIM(RTRIM(CAST(l.shipinid AS varchar(100)))) "
        )
        agg_all_sql = f"{agg_sql_base} {join_account_all_sql} "
        agg_filtered_sql = f"{agg_sql_base} {join_account_filtered_sql} "

        agg_all_rows = sf_db(
            f"{agg_all_sql} WHERE l.rn = 1"
        ) or []
        agg_filtered_rows = sf_db(
            f"{agg_filtered_sql} WHERE {where_sql}"
        ) or []
        aggregate_all = _parse_agg_row(agg_all_rows[0] if agg_all_rows else None)
        aggregate_filtered = _parse_agg_row(agg_filtered_rows[0] if agg_filtered_rows else None)

        start_row = offset + 1
        end_row = offset + page_size
        list_sql = (
            "WITH latest AS ("
            "  SELECT v.*, ROW_NUMBER() OVER ("
            "    PARTITION BY v.daren, v.shipinid "
            "    ORDER BY "
            "      CASE "
            "        WHEN v.xuhao IS NULL THEN 0 "
            "        WHEN PATINDEX('%%[^0-9]%%', LTRIM(RTRIM(CAST(v.xuhao AS varchar(50))))) = 0 "
            "          THEN CAST(LTRIM(RTRIM(CAST(v.xuhao AS varchar(50)))) AS bigint) "
            "        ELSE 0 "
            "      END DESC, "
            "      v.zhuaqushijian DESC"
            "  ) AS rn "
            "  FROM TK_ZiYouZhangHao_ShiPinShuJu v"
            "), order_sum AS ("
            "  SELECT "
            "    LTRIM(RTRIM(CAST(o.shipinid AS varchar(100)))) AS shipinid_key, "
            "    COUNT(1) AS purchase_count, "
            "    SUM(CASE "
            "      WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(CAST(o.jine AS varchar(100)))), ',', '')) = 1 "
            "        THEN CAST(REPLACE(LTRIM(RTRIM(CAST(o.jine AS varchar(100)))), ',', '') AS float) "
            "      ELSE 0 END) AS jine_sum "
            "  FROM tk_bddingdan o "
            f"  WHERE {order_where_sql} "
            "  GROUP BY LTRIM(RTRIM(CAST(o.shipinid AS varchar(100))))"
            "), filtered AS ("
            "  SELECT "
            "    a.dian AS dian, l.daren AS daren, a.fuzeren AS fuzeren, l.shipinid AS shipinid, "
            "    l.chuangjianshijian AS chuangjianshijian, l.biaoti AS biaoti, l.tag AS tag, "
            "    l.shichang AS shichang, l.dianzanshu AS dianzanshu, l.bofangshu AS bofangshu, "
            "    l.pinglunshu AS pinglunshu, l.shoucangshu AS shoucangshu, l.fenxiangshu AS fenxiangshu, "
            "    ISNULL(os.jine_sum, 0) AS jine_sum, "
            "    ISNULL(os.purchase_count, 0) AS purchase_count, "
            "    l.zhuaqushijian AS zhuaqushijian, "
            "    ROW_NUMBER() OVER (ORDER BY l.zhuaqushijian DESC) AS _rownum "
            "  FROM latest l "
            f"  {join_account_filtered_sql} "
            "  LEFT JOIN order_sum os ON os.shipinid_key = LTRIM(RTRIM(CAST(l.shipinid AS varchar(100)))) "
            f"  WHERE {where_sql}"
            ") "
            "SELECT dian, daren, fuzeren, shipinid, chuangjianshijian, biaoti, tag, shichang, "
            "       dianzanshu, bofangshu, pinglunshu, shoucangshu, fenxiangshu, jine_sum, purchase_count, zhuaqushijian "
            "FROM filtered "
            f"WHERE _rownum BETWEEN {start_row} AND {end_row} "
            "ORDER BY _rownum"
        )
        rows = sf_db(
            list_sql
        ) or []

        cols = [
            'dian', 'daren', 'fuzeren', 'shipinid', 'chuangjianshijian', 'biaoti', 'tag', 'shichang',
            'dianzanshu', 'bofangshu', 'pinglunshu', 'shoucangshu', 'fenxiangshu', 'jine_sum', 'purchase_count', 'zhuaqushijian'
        ]
        items = []
        for r in rows:
            if isinstance(r, dict):
                item = {k: (r.get(k) if k in r else r.get(k.upper())) for k in cols}
            elif isinstance(r, (list, tuple)):
                item = {cols[i]: (r[i] if i < len(r) else None) for i in range(len(cols))}
            else:
                item = {}
            shipinid = (item.get('shipinid') or '').strip() if isinstance(item.get('shipinid'), str) else str(item.get('shipinid') or '').strip()
            item['video_url'] = f"https://www.tiktok.com/@lunavale0128/video/{shipinid}" if shipinid else ''
            items.append(item)

        return jsonify({
            'success': True,
            'data': {
                'items': items,
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_raw_all': total_raw_all,
                'total_raw_filtered': total_raw_filtered,
                'aggregate_all': aggregate_all,
                'aggregate_filtered': aggregate_filtered
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取视频数据失败: {str(e)}'}), 500


@app.route('/api/tk_invite_monitor/upload', methods=['POST'])
@require_permission('tk_project_group')
def upload_invite_ids():
    """上传Excel并批量写入 tk_yaoqingma(邀请码, 日期, BD, 店铺)"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未发现文件，请选择Excel文件后重试'})

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'})

        # 读取Excel（兼容xlsx/xls），优先使用pandas
        import pandas as pd
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return jsonify({'success': False, 'message': f'读取Excel失败: {str(e)}'})

        # 标准化列名：兼容“邀请id/邀请码”和“截止日期/日期/店铺”
        normalized_cols = {str(c).strip(): c for c in df.columns}
        id_col = None
        date_col = None
        store_col = None
        for cand in ['邀请id', '邀请码', '邀请ID', '邀请码ID']:
            if cand in normalized_cols:
                id_col = normalized_cols[cand]
                break
        for cand in ['截止日期', '日期', '到期日期', '截止时间']:
            if cand in normalized_cols:
                date_col = normalized_cols[cand]
                break
        for cand in ['店铺', '店铺编号', '店号']:
            if cand in normalized_cols:
                store_col = normalized_cols[cand]
                break

        if not id_col or not date_col or not store_col:
            return jsonify({'success': False, 'message': 'Excel缺少必要列：需要包含“邀请id/邀请码”、“截止日期/日期”和“店铺”列（店铺示例：80、81、82）'})

        bd_name = session.get('feishu_user_name', '')
        bd_name_safe = str(bd_name).replace("'", "''")

        store_in_db = True
        try:
            tb_cols = sf_db("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'tk_yaoqingma' ORDER BY ORDINAL_POSITION") or []
            col_names = []
            for c in tb_cols:
                if isinstance(c, (list, tuple)):
                    col_names.append(str(c[0]))
                elif isinstance(c, dict):
                    col_names.append(str(c.get('COLUMN_NAME') or c.get('column_name') or ''))
                else:
                    col_names.append(str(c))
            col_names = [name for name in col_names if name]
            store_in_db = ('店铺' in col_names)
        except Exception:
            store_in_db = True

        inserted = 0
        errors = []
        warnings = []
        warned_no_store_col = False
        for idx, row in df.iterrows():
            invite_val = row.get(id_col)
            date_val = row.get(date_col)
            store_val = row.get(store_col)
            if pd.isna(invite_val) or str(invite_val).strip() == '':
                errors.append(f'第{idx+1}行邀请码为空，跳过')
                continue

            invite_safe = str(invite_val).strip().replace("'", "''")

            try:
                if pd.isna(date_val) or str(date_val).strip() == '':
                    raise ValueError('日期为空')
                if hasattr(date_val, 'strftime'):
                    date_safe = date_val.strftime('%Y-%m-%d')
                else:
                    from datetime import datetime
                    date_safe = datetime.strptime(str(date_val).strip(), '%Y-%m-%d').strftime('%Y-%m-%d')
            except Exception:
                errors.append(f'第{idx+1}行日期格式不正确，需YYYY-MM-DD，当前值: {date_val}')
                continue

            try:
                store_code = None
                if pd.isna(store_val) or str(store_val).strip() == '':
                    raise ValueError('店铺为空')
                store_str = str(store_val).strip()
                if isinstance(store_val, (int, float)):
                    store_code = str(int(float(store_val)))
                else:
                    import re
                    if re.fullmatch(r'\d+', store_str):
                        store_code = store_str
                    else:
                        raise ValueError('店铺需为数字')
                store_safe = store_code.replace("'", "''")
            except Exception:
                errors.append(f'第{idx+1}行店铺格式错误：{store_val}（需为数字，如80、81、82）')
                continue

            if store_in_db:
                sql = f"""
                INSERT INTO tk_yaoqingma (邀请码, 日期, BD, 店铺)
                VALUES ('{invite_safe}', '{date_safe}', '{bd_name_safe}', '{store_safe}')
                """
            else:
                sql = f"""
                INSERT INTO tk_yaoqingma (邀请码, 日期, BD)
                VALUES ('{invite_safe}', '{date_safe}', '{bd_name_safe}')
                """
                if not warned_no_store_col:
                    warnings.append('数据库未检测到“店铺”列，已忽略写入该字段')
                    warned_no_store_col = True
            try:
                expire_sql = f"""
                UPDATE tk_yaoqingma
                SET 日期 = '2000-01-01'
                WHERE 邀请码 = '{invite_safe}'
                """
                dui_db(expire_sql)

                dui_db(sql)
                inserted += 1
            except Exception as e:
                errors.append(f'第{idx+1}行插入失败: {str(e)}')

        return jsonify({
            'success': True,
            'inserted': inserted,
            'errors': errors,
            'warnings': warnings,
            'message': f'上传完成，成功插入 {inserted} 条记录，{len(errors)} 条失败'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'上传处理异常: {str(e)}'})


@app.route('/api/tk_invite_monitor/wanghong_register_upload', methods=['POST'])
@require_permission('tk_project_group')
def upload_wanghong_register():
    """上传Excel并写入 TK_wanghongming_dengji(BD, WangHongMing, Dian, DaoRuShiJian)"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未发现文件，请选择Excel文件后重试'})

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'})

        import pandas as pd
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return jsonify({'success': False, 'message': f'读取Excel失败: {str(e)}'})

        normalized_cols = {str(c).strip(): c for c in df.columns}
        name_col = None
        store_col = None
        for cand in ['网红名', '红人名', '达人名', '网红', '红人', '达人', 'WangHongMing']:
            if cand in normalized_cols:
                name_col = normalized_cols[cand]
                break
        for cand in ['店', '店铺', '店铺编号', '店号', 'Dian']:
            if cand in normalized_cols:
                store_col = normalized_cols[cand]
                break

        if not name_col or not store_col:
            return jsonify({'success': False, 'message': 'Excel缺少必要列：需要包含“网红名”和“店/店铺”列'})

        bd_name = session.get('feishu_user_name', '')
        bd_name_safe = str(bd_name).replace("'", "''")

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        inserted = 0
        updated = 0
        errors = []

        for idx, row in df.iterrows():
            name_val = row.get(name_col)
            store_val = row.get(store_col)

            if pd.isna(name_val) or str(name_val).strip() == '':
                errors.append(f'第{idx+1}行网红名为空，跳过')
                continue
            if pd.isna(store_val) or str(store_val).strip() == '':
                errors.append(f'第{idx+1}行店铺为空，跳过')
                continue

            name_safe = str(name_val).strip().replace("'", "''")
            store_safe = ''
            try:
                if isinstance(store_val, (int, float)) and str(store_val).strip() != '':
                    store_safe = str(int(float(store_val))).strip()
                else:
                    store_safe = str(store_val).strip()
            except Exception:
                store_safe = str(store_val).strip()
            store_safe = store_safe.replace("'", "''")
            if store_safe == '':
                errors.append(f'第{idx+1}行店铺格式错误：{store_val}')
                continue

            try:
                exists_sql = f"SELECT COUNT(1) FROM TK_wanghongming_dengji WHERE WangHongMing = '{name_safe}' AND Dian = '{store_safe}'"
                exists = sf_db(exists_sql, single=True)
                exists = int(exists or 0)
            except Exception as e:
                errors.append(f'第{idx+1}行查询失败: {str(e)}')
                continue

            try:
                if exists > 0:
                    sql = f"""
                        UPDATE TK_wanghongming_dengji
                        SET DaoRuShiJian = '{now_str}', BD = '{bd_name_safe}', TongZhiShiJian = NULL
                        WHERE WangHongMing = '{name_safe}' AND Dian = '{store_safe}'
                    """
                    dui_db(sql)
                    updated += 1
                else:
                    sql = f"""
                        INSERT INTO TK_wanghongming_dengji (BD, WangHongMing, Dian, DaoRuShiJian)
                        VALUES ('{bd_name_safe}', '{name_safe}', '{store_safe}', '{now_str}')
                    """
                    dui_db(sql)
                    inserted += 1
            except Exception as e:
                errors.append(f'第{idx+1}行写入失败: {str(e)}')

        return jsonify({
            'success': True,
            'inserted': inserted,
            'updated': updated,
            'errors': errors,
            'message': f'导入完成：新增 {inserted} 条，更新 {updated} 条，失败 {len(errors)} 条'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'上传处理异常: {str(e)}'})


@app.route('/api/tk_invite_monitor/list', methods=['GET'])
@require_permission('tk_project_group')
def list_invite_codes():
    try:
        user_name = session.get('feishu_user_name', '')
        if not user_name:
            return jsonify({'success': False, 'message': '未登录'}), 401

        bd_name_safe = str(user_name).replace("'", "''")
        sql = f"""
            SELECT 邀请码, 日期
            FROM tk_yaoqingma
            WHERE BD = '{bd_name_safe}'
            ORDER BY 日期 DESC
        """
        rows = sf_db(sql) or []
        data = []
        from datetime import datetime, date
        for r in rows:
            invite = r[0] if len(r) > 0 else ''
            raw_date = r[1] if len(r) > 1 else ''
            formatted = ''
            try:
                if isinstance(raw_date, datetime):
                    formatted = raw_date.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                elif isinstance(raw_date, date):
                    formatted = datetime(raw_date.year, raw_date.month, raw_date.day).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                else:
                    # 尝试解析字符串
                    s = str(raw_date)
                    try:
                        # 兼容 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM:SS'
                        fmt = '%Y-%m-%d %H:%M:%S' if ' ' in s else '%Y-%m-%d'
                        dt = datetime.strptime(s[:19], fmt)
                        formatted = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    except Exception:
                        formatted = s
            except Exception:
                formatted = str(raw_date)

            data.append({
                'invite_code': invite,
                'date': formatted
            })
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'查询失败: {str(e)}'}), 500


@app.route('/api/tk_invite_monitor/unchecked_12h', methods=['GET'])
@require_permission('tk_project_group')
def list_unchecked_invite_codes_12h():
    """
    查询“12小时之内还未检查的邀请码”：
    使用提供的 SQL 条件：
        SELECT ID, 邀请码, BD, 日期
        FROM tk_yaoqingma
        WHERE 日期 >= GETDATE()
          AND 导入时间 <= DATEADD(HOUR, -12, GETDATE());
    """
    try:
        sql = """
            SELECT ID, 邀请码, BD, 日期, 店铺
            FROM tk_yaoqingma
            WHERE 日期 >= GETDATE()
              AND 导入时间 <= DATEADD(HOUR, -12, GETDATE())
            ORDER BY 日期 ASC, ID ASC
        """
        rows = sf_db(sql) or []
        from datetime import datetime, date
        data = []
        store_counts = {}
        for r in rows:
            row_id = r[0] if len(r) > 0 else None
            invite = r[1] if len(r) > 1 else ''
            bd_name = r[2] if len(r) > 2 else ''
            raw_date = r[3] if len(r) > 3 else None
            store = r[4] if len(r) > 4 else ''
            store_str = '' if store is None else str(store).strip()
            if store_str:
                store_counts[store_str] = store_counts.get(store_str, 0) + 1
            formatted_date = ''
            try:
                if isinstance(raw_date, datetime):
                    formatted_date = raw_date.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(raw_date, date):
                    formatted_date = datetime(raw_date.year, raw_date.month, raw_date.day).strftime('%Y-%m-%d')
                else:
                    formatted_date = str(raw_date) if raw_date is not None else ''
            except Exception:
                formatted_date = str(raw_date) if raw_date is not None else ''
            data.append({
                'id': row_id,
                'invite_code': invite,
                'bd': bd_name,
                'date': formatted_date,
                'store': store_str
            })
        total_count = len(data)
        store_list = [{'store': k, 'count': v} for k, v in store_counts.items()]
        store_list.sort(key=lambda x: x['store'])
        return jsonify({'success': True, 'data': data, 'total': total_count, 'store_counts': store_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'查询失败: {str(e)}'}), 500


@app.route('/api/tk_invite_monitor/wanghong_register_overview', methods=['GET'])
@require_permission('tk_project_group')
def tk_invite_monitor_wanghong_register_overview():
    """达人资料/合作记录登记展示"""
    try:
        latest_sql = """
            SELECT MAX(shijian) AS latest_time
            FROM (
                SELECT MAX(DaoRuShiJian) AS shijian
                FROM TK_WangHong_ZiLiao
                WHERE CHARINDEX(N'影刀', ISNULL(CAST(BeiZhu1 AS NVARCHAR(200)), '')) > 0
                UNION ALL
                SELECT MAX(DaoRuShiJian) AS shijian
                FROM TK_WangHong_HeZuo
                WHERE CHARINDEX(N'影刀', ISNULL(CAST(DaoRuRen AS NVARCHAR(200)), '')) > 0
            ) t
        """
        latest_raw = sf_db(latest_sql, single=True)

        count_sql = """
            SELECT COUNT(1)
            FROM TK_WangHongMing_DengJi
            WHERE TongZhiShiJian IS NULL
        """
        remaining_raw = sf_db(count_sql, single=True)
        if isinstance(remaining_raw, dict):
            remaining_count = int(
                remaining_raw.get('COUNT(1)')
                or remaining_raw.get('count')
                or remaining_raw.get('cnt')
                or 0
            )
        elif isinstance(remaining_raw, (list, tuple)):
            remaining_count = int(remaining_raw[0] if remaining_raw else 0)
        else:
            remaining_count = int(remaining_raw or 0)

        list_sql = """
            SELECT TOP 300
                ROW_NUMBER() OVER (ORDER BY DaoRuShiJian DESC) AS XH,
                BD,
                WangHongMing,
                Dian,
                DaoRuShiJian,
                TongZhiShiJian
            FROM TK_WangHongMing_DengJi
            WHERE TongZhiShiJian IS NULL
            ORDER BY DaoRuShiJian DESC
        """
        rows = sf_db(list_sql) or []

        items = []
        for r in rows:
            if isinstance(r, dict):
                row_id = (
                    r.get('XH')
                    if 'XH' in r else
                    r.get('xh')
                    if 'xh' in r else
                    r.get('ID')
                    if 'ID' in r else
                    r.get('id')
                )
                bd = r.get('BD') if 'BD' in r else r.get('bd')
                wanghongming = r.get('WangHongMing') if 'WangHongMing' in r else r.get('wanghongming')
                dian = r.get('Dian') if 'Dian' in r else r.get('dian')
                daoru = r.get('DaoRuShiJian') if 'DaoRuShiJian' in r else r.get('daorushijian')
                tongzhi = r.get('TongZhiShiJian') if 'TongZhiShiJian' in r else r.get('tongzhishijian')
            elif isinstance(r, (list, tuple)):
                row_id = r[0] if len(r) > 0 else None
                bd = r[1] if len(r) > 1 else ''
                wanghongming = r[2] if len(r) > 2 else ''
                dian = r[3] if len(r) > 3 else ''
                daoru = r[4] if len(r) > 4 else None
                tongzhi = r[5] if len(r) > 5 else None
            else:
                row_id = None
                bd = ''
                wanghongming = ''
                dian = ''
                daoru = None
                tongzhi = None
            if isinstance(daoru, datetime):
                daoru_text = daoru.strftime('%Y-%m-%d %H:%M:%S')
            else:
                daoru_text = '' if daoru is None else str(daoru)
            if isinstance(tongzhi, datetime):
                tongzhi_text = tongzhi.strftime('%Y-%m-%d %H:%M:%S')
            else:
                tongzhi_text = '' if tongzhi is None else str(tongzhi)
            items.append({
                'id': row_id,
                'bd': '' if bd is None else str(bd),
                'wanghongming': '' if wanghongming is None else str(wanghongming),
                'dian': '' if dian is None else str(dian),
                'daorushijian': daoru_text,
                'tongzhishijian': tongzhi_text
            })

        if isinstance(latest_raw, datetime):
            latest_time = latest_raw.strftime('%Y-%m-%d %H:%M:%S')
        else:
            latest_time = '' if latest_raw is None else str(latest_raw)

        return jsonify({
            'success': True,
            'data': {
                'latest_time': latest_time,
                'remaining_count': remaining_count,
                'preview_count': len(items),
                'items': items
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'查询失败: {str(e)}'}), 500


@app.route('/api/tk_monthly_target_import/upload', methods=['POST'])
@require_permission('tk_project_group')
def upload_monthly_target():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未发现文件，请选择Excel文件后重试'})

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'})

        import pandas as pd
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return jsonify({'success': False, 'message': f'读取Excel失败: {str(e)}'})

        if df is None or df.empty:
            return jsonify({'success': False, 'message': 'Excel内容为空'})

        def normalize_col(name):
            s = str(name).strip()
            s = s.replace('\u3000', '').replace(' ', '').replace('\t', '')
            s = s.replace('（', '(').replace('）', ')')
            s = s.replace('(', '').replace(')', '')
            s = s.replace('_', '').replace('-', '').replace('—', '')
            s = s.lower()
            if s in ('年份', '年度', 'year'):
                return '年'
            if s in ('月份', '月度', 'month'):
                return '月'
            if s in ('店', '店铺', '门店', '店名', '门市', 'shop', '门店号', '店号'):
                return '店'
            return s

        cols_rs = sf_db(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = 'tk_yuedumubiao' ORDER BY ORDINAL_POSITION"
        ) or []
        db_cols = []
        db_types = {}
        for r in cols_rs:
            if isinstance(r, (list, tuple)) and len(r) >= 2:
                col_name = str(r[0])
                col_type = str(r[1])
            elif isinstance(r, dict):
                col_name = str(r.get('COLUMN_NAME') or r.get('column_name') or '')
                col_type = str(r.get('DATA_TYPE') or r.get('data_type') or '')
            else:
                continue
            if col_name:
                db_cols.append(col_name)
                db_types[col_name] = col_type.lower()

        if not db_cols:
            return jsonify({'success': False, 'message': '未获取到数据库表 tk_yuedumubiao 的字段信息'})

        excel_cols = list(df.columns)
        excel_norm_map = {}
        for c in excel_cols:
            n = normalize_col(c)
            if n and n not in excel_norm_map:
                excel_norm_map[n] = c

        db_norm_map = {}
        for c in db_cols:
            n = normalize_col(c)
            if n and n not in db_norm_map:
                db_norm_map[n] = c

        year_db_col = db_norm_map.get('年')
        month_db_col = db_norm_map.get('月')
        shop_db_col = db_norm_map.get('店')
        import_time_db_col = db_norm_map.get('导入时间')
        year_excel_col = excel_norm_map.get('年')
        month_excel_col = excel_norm_map.get('月')
        shop_excel_col = excel_norm_map.get('店')
        if not (year_db_col and month_db_col and year_excel_col and month_excel_col and shop_db_col and shop_excel_col):
            return jsonify({'success': False, 'message': 'Excel必须包含“年”“月”“店”三列'})

        numeric_types = {
            'int', 'bigint', 'smallint', 'tinyint',
            'decimal', 'numeric', 'float', 'real',
            'money', 'smallmoney', 'bit'
        }

        def to_sql_identifier(name):
            return '[' + str(name).replace(']', ']]') + ']'

        def parse_numeric(v, default=0):
            try:
                if pd.isna(v) or str(v).strip() == '':
                    return default
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return int(v)
                s = str(v).strip().replace(',', '')
                return int(float(s))
            except Exception:
                return default

        def to_sql_value(db_col, v, warnings):
            norm_name = normalize_col(db_col)
            if norm_name == '店':
                if v is None or (hasattr(pd, 'isna') and pd.isna(v)) or str(v).strip() == '':
                    return 'NULL', None
                num = None
                try:
                    num = parse_numeric(v, default=None)
                except Exception:
                    num = None
                if num is not None:
                    num_int = int(num)
                    return str(num_int), num_int
                s = str(v).strip()
                s = s.replace("'", "''")
                return "'" + s + "'", s
            if norm_name in ('年', '月', '导入时间'):
                if v is None or (hasattr(pd, 'isna') and pd.isna(v)):
                    return 'NULL', None
                s = str(v)
                s = s.replace("'", "''")
                return "'" + s + "'", s
            num = None
            try:
                num = parse_numeric(v, default=None)
            except Exception:
                num = None
            if num is not None:
                num_int = int(num)
                return str(num_int), num_int
            if v is None or (hasattr(pd, 'isna') and pd.isna(v)):
                return 'NULL', None
            s = str(v)
            s = s.replace("'", "''")
            return "'" + s + "'", s

        warnings = []

        mapped = []
        for excel_norm, excel_col in excel_norm_map.items():
            db_col = db_norm_map.get(excel_norm)
            if db_col:
                mapped.append((db_col, excel_col))

        if len(mapped) == 0:
            return jsonify({'success': False, 'message': 'Excel表头与数据库字段无法匹配'})

        year_ident = to_sql_identifier(year_db_col)
        month_ident = to_sql_identifier(month_db_col)
        shop_ident = to_sql_identifier(shop_db_col)
        import_time_ident = to_sql_identifier(import_time_db_col) if import_time_db_col else None

        total_rows = len(df)
        processed_rows = 0
        inserted_rows = 0
        updated_rows = 0
        detail_msgs = []

        for idx, row in df.iterrows():
            year_val = row.get(year_excel_col)
            month_val = row.get(month_excel_col)
            shop_val = row.get(shop_excel_col)
            year_num = int(parse_numeric(year_val, default=0))
            month_num = int(parse_numeric(month_val, default=0))
            if year_num <= 0 or month_num <= 0:
                warnings.append(f'第{idx + 2}行年/月不合法：年={year_val}，月={month_val}')
                continue

            shop_sql_val, shop_raw = to_sql_value(shop_db_col, shop_val, warnings)
            shop_raw_str = str(shop_raw or '').strip()
            if not shop_raw_str:
                warnings.append(f'第{idx + 2}行“店”列为空，已跳过')
                continue

            set_parts = []
            insert_cols = []
            insert_vals = []
            for db_col, excel_col in mapped:
                norm_name = normalize_col(db_col)
                if norm_name in ('年', '月', '店'):
                    continue
                sql_val, _ = to_sql_value(db_col, row.get(excel_col), warnings)
                col_ident = to_sql_identifier(db_col)
                set_parts.append(f"{col_ident} = {sql_val}")
                insert_cols.append(col_ident)
                insert_vals.append(sql_val)

            if import_time_ident:
                set_parts.append(f"{import_time_ident} = GETDATE()")

            exist_cnt = sf_db(
                f"SELECT COUNT(*) FROM tk_yuedumubiao WHERE {year_ident} = {year_num} AND {month_ident} = {month_num} AND {shop_ident} = {shop_sql_val}",
                single=True
            )
            exist_cnt = int(exist_cnt) if exist_cnt is not None else 0

            if exist_cnt > 0 and set_parts:
                sql = (
                    f"UPDATE tk_yuedumubiao SET {', '.join(set_parts)} "
                    f"WHERE {year_ident} = {year_num} AND {month_ident} = {month_num} AND {shop_ident} = {shop_sql_val}"
                )
                dui_db(sql)
                action = '更新'
                updated_rows += 1
            else:
                if import_time_ident:
                    insert_cols_full = [year_ident, month_ident, shop_ident, import_time_ident] + insert_cols
                    insert_vals_full = [str(year_num), str(month_num), shop_sql_val, 'GETDATE()'] + insert_vals
                else:
                    insert_cols_full = [year_ident, month_ident, shop_ident] + insert_cols
                    insert_vals_full = [str(year_num), str(month_num), shop_sql_val] + insert_vals
                sql = (
                    f"INSERT INTO tk_yuedumubiao ({', '.join(insert_cols_full)}) "
                    f"VALUES ({', '.join(insert_vals_full)})"
                )
                dui_db(sql)
                action = '新增'
                inserted_rows += 1

            processed_rows += 1
            detail_msgs.append(f'{action} {year_num}年{month_num}月 店={shop_raw_str} 月度目标')
            if exist_cnt > 1:
                warnings.append(f'检测到数据库中 {year_num}年{month_num}月 店={shop_raw_str} 存在多条记录，本次将全部更新')

        if processed_rows == 0:
            return jsonify({
                'success': False,
                'message': '未找到任何有效行，导入失败',
                'warnings': warnings
            })

        msg = f'导入完成：共{total_rows}行，成功{processed_rows}行，新增{inserted_rows}行，更新{updated_rows}行'

        return jsonify({'success': True,
            'action': '批量导入',
            'total_rows': total_rows,
            'processed_rows': processed_rows,
            'inserted_rows': inserted_rows,
            'updated_rows': updated_rows,
            'warnings': warnings + detail_msgs,
            'message': msg
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'导入失败: {str(e)}'})


@app.route('/api/tk_monthly_target_import/template', methods=['GET'])
@require_permission('tk_project_group')
def download_monthly_target_template():
    try:
        import pandas as pd
        from io import BytesIO
        desired_headers = [
            '实时保本额',
            '销售量',
            '销售额',
            '净利润',
            '毛利润',
            '达人佣金',
            '达人数',
            '达人视频费',
            '视频数',
            '活动服务费',
            '广告费',
            '平台佣金',
            'VAT',
            '调整费',
            '其他',
            '经营管理费青岛',
            '经营管理费深圳',
            '产品成本',
            '头程费用',
            '尾程项目',
            '项目尾程仓储费入库费',
            '工资青岛',
            '工资深圳',
            '房租青岛',
            '房租深圳',
            '年',
            '月',
            '店',
            '创作者佣金',
            '联盟伙伴佣金',
            '广告订单佣金',
            '达人渠道号佣金',
            '刷单费',
            '售后',
            '网红坑位费',
            '给网红购买产品费',
            '达人礼品费',
            '入库费',
            '仓储费',
            '退货费'
        ]
        cols_rs = sf_db(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = 'tk_yuedumubiao'"
        ) or []
        db_cols = set()
        for r in cols_rs:
            if isinstance(r, (list, tuple)) and len(r) >= 1:
                col_name = str(r[0])
            elif isinstance(r, dict):
                col_name = str(r.get('COLUMN_NAME') or r.get('column_name') or '')
            else:
                col_name = ''
            if col_name:
                db_cols.add(col_name)
        headers = [h for h in desired_headers if (not db_cols or h in db_cols)]
        if not headers:
            headers = desired_headers
        df = pd.DataFrame(columns=headers)
        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        filename = f"tk_yuedumubiao_import_template_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'生成模板失败: {str(e)}'})

@app.route('/tk_dashboard')
@require_permission('tk_project_group')
def tk_dashboard():
    """TK项目组数据看板页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')

    return render_template('tk_dashboard.html',
                           user_name=user_name,
                           user_id=user_id)


@app.route('/api/tk_dashboard_data', methods=['GET'])
@require_permission('tk_project_group')
def get_tk_dashboard_data():
    """获取TK数据看板数据API"""
    try:
        # 获取当前用户信息
        user_name = session.get('feishu_user_name', '')
        user_id = session.get('feishu_user_id', '')

        # 定义管理单（可以查看所有组的详细信息）
        admin_users = ['周俊成', '毕景春', '陶晓飞', '李昌翰', '孙军', '李春', '宋亚倩', '王丰慧', '陈梦昭']
        is_admin = user_name in admin_users

        _safe_debug_print(f"🔍 TK数据看板访问 - 用户: {user_name}, 是否管理员: {is_admin}")

        # 获取年月参数，默认为当前年月
        year = request.args.get('year', datetime.now().year, type=int)
        month = request.args.get('month', datetime.now().month, type=int)
        location = request.args.get('location', '', type=str)  # 新增位置参数

        _safe_debug_print(f"📍 筛选条件 - 年: {year}, 月: {month}, 位置: {location}")

        # 调用存储过程获取数据
        sql = f"EXEC sp_get_TK_YiBiaoPan6 @年 = {year}, @月 = {month}"
        data = sf_db(sql)

        if not data:
            return jsonify({
                'success': False,
                'message': '暂无数据',
                'data': [],
                'user_info': {
                    'user_name': user_name,
                    'is_admin': is_admin
                }
            })

        # 获取全部86店GMV数据（按月计算）
        tk_gmv_sql = f"""
            SELECT SUM(xiaoshoue) as tk_total_gmv
            FROM v_tk_dingdan 
            where   
             dian = 86
            AND Y= {year}
            AND M= {month}
        """

        try:
            tk_gmv_result = sf_db(tk_gmv_sql)
            # sf_db函数当只有一列时返回列表，多列时返回元组列表
            if tk_gmv_result:
                if isinstance(tk_gmv_result, list) and len(tk_gmv_result) > 0:
                    # 如果是列表且有数据，取第一个元素
                    tk_project_gmv = tk_gmv_result[0] if tk_gmv_result[0] is not None else 0
                else:
                    tk_project_gmv = 0
            else:
                tk_project_gmv = 0
            _safe_debug_print(f"📊 全部86店GMV: {tk_project_gmv}")
        except Exception as e:
            _safe_debug_print(f"❌ 获取全部86店GMV失败: {e}")
            tk_project_gmv = 0

        # 计算深圳联盟总GMV（等于深圳的86店GMV）
        # 根据业务逻辑：深圳的86店总GMV等于深圳的联盟总GMV
        shenzhen_alliance_gmv = 0
        try:
            # 从存储过程数据中计算深圳的GMV总和
            for row in data:
                if row[3] == '深圳':  # 位置字段是第4个字段（索引3）
                    shenzhen_alliance_gmv += float(row[13] if row[13] is not None else 0)  # GMV字段是第14个字段（索引13）
            _safe_debug_print(f"📊 深圳联盟总GMV: {shenzhen_alliance_gmv}")
        except Exception as e:
            _safe_debug_print(f"❌ 计算深圳联盟GMV失败: {e}")
            shenzhen_alliance_gmv = 0

        # 计算青岛86店GMV = 全部86店GMV - 深圳联盟GMV
        qingdao_86_gmv = tk_project_gmv - shenzhen_alliance_gmv
        _safe_debug_print(f"📊 青岛86店GMV: {qingdao_86_gmv} (全部86店GMV: {tk_project_gmv} - 深圳联盟GMV: {shenzhen_alliance_gmv})")

        # 转换数据格式，包含所有字段
        all_data = []
        for row in data:
            row_data = {
                '年': row[0],
                '月': row[1],
                'BD': row[2],
                '位置': row[3],
                '组长': row[4],
                '达人数指标': row[6],
                '实际达人数': row[7],
                '达人数达成率': f"{row[8] * 100:.2f}%" if row[8] is not None else None,
                '视频数': row[9],
                '视频发布数': row[10],
                '视频达成率': f"{row[11] * 100:.2f}%" if row[11] is not None else None,
                'GMV指标': row[12],
                'GMV': row[13],
                'GMV达成率': f"{row[14] * 100:.2f}%" if row[14] is not None else None
            }

            all_data.append(row_data)

        # 根据位置参数过滤数据
        if location:
            all_data = [row for row in all_data if row['位置'] == location]
            _safe_debug_print(f"🎯 位置筛选后数据量: {len(all_data)}")

        # 根据用户权限过滤数据
        if is_admin:
            # 管理员可以看到所有组的详细信息
            result_data = all_data
            _safe_debug_print(f"✅ 管理员用户，返回所有 {len(result_data)} 条数据")
        else:
            # 普通用户需要根据用户名匹配对应的分组数据
            # 通过BD字段或组长字段匹配用户所属分组
            user_location = None
            for row in all_data:
                # 找到当前用户所在的位置
                if (row['BD'] == user_name or row['组长'] == user_name or
                        (row['BD'] and user_name in row['BD']) or
                        (row['组长'] and user_name in row['组长'])):
                    user_location = row['位置']
                    break
            if user_location:
                # 根据位置筛选同一地区的所有数据
                result_data = [row for row in all_data if row['位置'] == user_location]
                _safe_debug_print(f" 普通用户（{user_name}），位置：{user_location}，共返回 {len(result_data)} 条数据")
            else:
                # 如果找不到用户对应的位置，则不返回数据
                result_data = []
                _safe_debug_print(f" 未找到用户 {user_name} 对应的位置，返回空数据")

        return jsonify({
            'success': True,
            'data': result_data,
            'year': year,
            'month': month,
            'location': location,  # 返回位置信息
            'tk_project_gmv': tk_project_gmv,  # 返回全部86店GMV数据
            'shenzhen_alliance_gmv': shenzhen_alliance_gmv,  # 返回深圳联盟GMV数据
            'qingdao_86_gmv': qingdao_86_gmv,  # 返回青岛86店GMV数据
            'user_info': {
                'user_name': user_name,
                'is_admin': is_admin,
                'total_groups': len(all_data),
                'accessible_groups': len(result_data)
            }
        })

    except Exception as e:
        _safe_debug_print(f"❌ 获取TK数据看板数据失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取数据失败: {str(e)}',
            'data': [],
            'user_info': {
                'user_name': session.get('feishu_user_name', ''),
                'is_admin': False
            }
        }), 500



# 运营部门功能页面路由
@app.route('/general_office')
@require_permission('general_office')
def general_office():
    """总经办功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='总经办',
                           dept_id='general_office')


@app.route('/procurement_dept')
@require_permission('procurement_dept')
def procurement_dept():
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='采购部',
                           dept_id='procurement_dept')


_OPERATION_DEPT_FUNCTIONS = {
    'operation_dept_1',
    'operation_dept_2',
    'operation_dept_3',
    'operation_dept_6',
}
_FBA_SHIPPING_TABLE = 'FBAHuoJian_YunShuFangShi'
_FBA_SHIPPING_PAGE_SIZE = 200


def _operation_dept_has_access():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return False
    for function_name in _OPERATION_DEPT_FUNCTIONS:
        try:
            ok, _ = permission_manager.check_user_permission(user_id, function_name)
            if ok:
                return True
        except Exception as e:
            _safe_debug_print(f"运营部门权限检查失败: {function_name} -> {e}")
    return False


def _fba_shipping_sql_ident(name):
    return '[' + str(name or '').replace(']', ']]') + ']'


def _fba_shipping_sql_text(value):
    return str(value or '').replace("'", "''")


def _fba_shipping_col_norm(name):
    text = str(name or '').strip().lower()
    text = re.sub(r'[\s_\-./\\()\[\]（）【】]+', '', text)
    return text


def _fba_shipping_label(name):
    raw = str(name or '').strip()
    norm = _fba_shipping_col_norm(raw)
    labels = {
        'id': '序号',
        'xh': '序号',
        'xuhao': '序号',
        'xvhao': '序号',
        '序号': '序号',
        'dian': '店铺',
        '店': '店铺',
        '店铺': '店铺',
        'danhao': '单号',
        'yunshufangshi': '运输方式',
        '运输方式': '运输方式',
        'xiaobaoguo': '小包裹',
        'wuliudanhao': '物流单号',
        'huojiandanhao': '货件单号',
        '货件单号': '货件单号',
        'daorushijian': '导入时间',
        '导入时间': '导入时间',
        'daoruren': '导入人',
        '导入人': '导入人',
        'ien': 'IEN',
        'sku': 'SKU',
        'beizhu': '备注',
        '备注': '备注',
    }
    return labels.get(norm) or raw


def _fba_shipping_pick_col(columns, candidates):
    norm_map = {_fba_shipping_col_norm(col): col for col in (columns or [])}
    for candidate in candidates:
        col = norm_map.get(_fba_shipping_col_norm(candidate))
        if col:
            return col
    return ''


def _fba_shipping_get_columns():
    sql = f"""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = N'{_FBA_SHIPPING_TABLE}'
        ORDER BY ORDINAL_POSITION
    """
    rows = sf_db(sql) or []
    columns = []
    for row in rows:
        if isinstance(row, str):
            col = row
        elif isinstance(row, dict):
            col = row.get('COLUMN_NAME') or row.get('column_name') or row.get('Column_Name')
        elif isinstance(row, (list, tuple)) and row:
            col = row[0]
        else:
            col = ''
        col = str(col or '').strip()
        if col:
            columns.append(col)
    return columns


def _fba_shipping_row_to_item(row, columns):
    if isinstance(row, dict):
        return {col: row.get(col) if col in row else row.get(col.lower()) for col in columns}
    if isinstance(row, (list, tuple)):
        return {col: (row[idx] if idx < len(row) else None) for idx, col in enumerate(columns)}
    return {col: None for col in columns}


def _fba_shipping_format_value(value):
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    return str(value)


def _fba_shipping_is_scientific(value):
    text = str(value or '').strip()
    if not text:
        return False
    return bool(re.fullmatch(r'[+-]?\d+(?:\.\d+)?[eE][+-]?\d+', text))


def _fba_shipping_sql_empty_expr(column_name):
    return f"NULLIF(LTRIM(RTRIM(ISNULL(CAST({_fba_shipping_sql_ident(column_name)} AS NVARCHAR(200)), N''))), N'') IS NULL"


def _fba_shipping_sql_scientific_expr(column_name):
    text_expr = f"UPPER(LTRIM(RTRIM(ISNULL(CAST({_fba_shipping_sql_ident(column_name)} AS NVARCHAR(200)), N''))))"
    return (
        f"({text_expr} LIKE '[0-9]%%E[+-][0-9]%%' "
        f"OR {text_expr} LIKE '+[0-9]%%E[+-][0-9]%%' "
        f"OR {text_expr} LIKE '-[0-9]%%E[+-][0-9]%%')"
    )


def _fba_shipping_issue_clause(shipping_col, cargo_col):
    if not cargo_col:
        return ''
    clauses = []
    if shipping_col:
        clauses.append(
            f"(CHARINDEX(N'海运', ISNULL(CAST({_fba_shipping_sql_ident(shipping_col)} AS NVARCHAR(200)), N'')) > 0 "
            f"AND {_fba_shipping_sql_empty_expr(cargo_col)})"
        )
    clauses.append(_fba_shipping_sql_scientific_expr(cargo_col))
    return '(' + ' OR '.join(clauses) + ')'


def _fba_shipping_prepare_payload_item(row_item, columns, sea_col, cargo_col):
    values = {}
    for col in columns:
        values[col] = _fba_shipping_format_value(row_item.get(col))

    warning_fields = {}
    shipping_text = values.get(sea_col, '') if sea_col else ''
    cargo_text = values.get(cargo_col, '') if cargo_col else ''
    if sea_col and cargo_col and '海运' in shipping_text and not cargo_text.strip():
        warning_fields[sea_col] = '运输方式包含“海运”，但货件单号为空'
        warning_fields[cargo_col] = '海运货件单号为空'
    if cargo_col and _fba_shipping_is_scientific(cargo_text):
        warning_fields[cargo_col] = '货件单号为科学计数法'
    return {
        'values': values,
        'warning': bool(warning_fields),
        'warning_fields': warning_fields,
    }


def _fba_shipping_sort_columns(columns):
    seq_col = _fba_shipping_pick_col(columns, ['序号', 'ID', 'id', 'xh', 'xuhao'])
    import_col = _fba_shipping_pick_col(columns, ['导入时间', 'DaoRuShiJian', 'daorushijian', 'import_time', 'shijian'])
    return seq_col, import_col


@app.route('/api/operation/fba_shipping_methods')
def api_operation_fba_shipping_methods():
    if not _operation_dept_has_access():
        return jsonify({'success': False, 'message': '无权限访问运营部门数据'}), 403
    try:
        columns = _fba_shipping_get_columns()
        if not columns:
            return jsonify({'success': False, 'message': '未找到FBA货件运输方式表字段'}), 404

        page = max(int(request.args.get('page') or 1), 1)
        page_size = _FBA_SHIPPING_PAGE_SIZE
        offset = (page - 1) * page_size
        dian_filter = str(request.args.get('dian') or '').strip()
        danhao_filter = str(request.args.get('danhao') or '').strip()
        sort_key = str(request.args.get('sort') or 'seq_desc').strip()
        issue_only = str(request.args.get('issue') or '').strip().lower() in {'1', 'true', 'yes', 'on'}

        dian_col = _fba_shipping_pick_col(columns, ['dian', '店', '店铺'])
        danhao_col = _fba_shipping_pick_col(columns, ['danhao', '单号'])
        shipping_col = _fba_shipping_pick_col(columns, ['yunshufangshi', '运输方式'])
        cargo_col = _fba_shipping_pick_col(columns, ['huojiandanhao', '货件单号'])
        seq_col, import_col = _fba_shipping_sort_columns(columns)

        where_parts = []
        if dian_filter and dian_col:
            where_parts.append(
                f"ISNULL(CAST({_fba_shipping_sql_ident(dian_col)} AS NVARCHAR(200)), N'') = N'{_fba_shipping_sql_text(dian_filter)}'"
            )
        if danhao_filter and danhao_col:
            where_parts.append(
                f"CHARINDEX(N'{_fba_shipping_sql_text(danhao_filter)}', ISNULL(CAST({_fba_shipping_sql_ident(danhao_col)} AS NVARCHAR(200)), N'')) > 0"
            )
        if issue_only:
            issue_clause = _fba_shipping_issue_clause(shipping_col, cargo_col)
            if issue_clause:
                where_parts.append(issue_clause)
        where_sql = ('WHERE ' + ' AND '.join(where_parts)) if where_parts else ''

        if sort_key == 'import_asc' and import_col:
            order_col, order_dir = import_col, 'ASC'
        elif sort_key == 'import_desc' and import_col:
            order_col, order_dir = import_col, 'DESC'
        elif seq_col:
            order_col, order_dir = seq_col, 'DESC'
            sort_key = 'seq_desc'
        elif import_col:
            order_col, order_dir = import_col, 'DESC'
            sort_key = 'import_desc'
        else:
            order_col, order_dir = columns[0], 'DESC'
            sort_key = 'seq_desc'

        count_rows = sf_db(f"SELECT COUNT(1) FROM {_fba_shipping_sql_ident(_FBA_SHIPPING_TABLE)} {where_sql}") or []
        total = 0
        if isinstance(count_rows, list) and count_rows:
            first = count_rows[0]
            if isinstance(first, dict):
                total = int(next(iter(first.values()), 0) or 0)
            elif isinstance(first, (list, tuple)):
                total = int(first[0] or 0)
            else:
                total = int(first or 0)

        rows = sf_db(f"""
            SELECT *
            FROM {_fba_shipping_sql_ident(_FBA_SHIPPING_TABLE)}
            {where_sql}
            ORDER BY {_fba_shipping_sql_ident(order_col)} {order_dir}
            OFFSET {offset} ROWS FETCH NEXT {page_size} ROWS ONLY
        """) or []
        items = [
            _fba_shipping_prepare_payload_item(_fba_shipping_row_to_item(row, columns), columns, shipping_col, cargo_col)
            for row in rows
        ]
        total_pages = max((total + page_size - 1) // page_size, 1)
        return jsonify({
            'success': True,
            'data': {
                'columns': [{'key': col, 'label': _fba_shipping_label(col)} for col in columns],
                'items': items,
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': total_pages,
                'sort': sort_key,
                'dian': dian_filter,
                'danhao': danhao_filter,
                'issue_only': issue_only,
                'has_import_sort': bool(import_col),
                'has_dian_filter': bool(dian_col),
                'has_danhao_filter': bool(danhao_col),
            }
        })
    except Exception as e:
        _safe_debug_print(f"FBA货件运输方式查询失败: {e}")
        return jsonify({'success': False, 'message': f'查询失败: {str(e)}'}), 500


@app.route('/api/operation/fba_shipping_methods/shops')
def api_operation_fba_shipping_method_shops():
    if not _operation_dept_has_access():
        return jsonify({'success': False, 'message': '无权限访问运营部门数据'}), 403
    try:
        columns = _fba_shipping_get_columns()
        dian_col = _fba_shipping_pick_col(columns, ['dian', '店', '店铺'])
        if not dian_col:
            return jsonify({'success': True, 'data': {'shops': []}})
        rows = sf_db(f"""
            SELECT DISTINCT TOP 500 CAST({_fba_shipping_sql_ident(dian_col)} AS NVARCHAR(200)) AS dian
            FROM {_fba_shipping_sql_ident(_FBA_SHIPPING_TABLE)}
            WHERE ISNULL(CAST({_fba_shipping_sql_ident(dian_col)} AS NVARCHAR(200)), N'') <> N''
            ORDER BY dian
        """) or []
        shops = []
        for row in rows:
            if isinstance(row, str):
                value = row
            elif isinstance(row, dict):
                value = row.get('dian') or row.get('Dian') or row.get('DIAN')
            elif isinstance(row, (list, tuple)) and row:
                value = row[0]
            else:
                value = ''
            value = str(value or '').strip()
            if value and value not in shops:
                shops.append(value)
        return jsonify({'success': True, 'data': {'shops': shops}})
    except Exception as e:
        _safe_debug_print(f"FBA货件运输方式店铺查询失败: {e}")
        return jsonify({'success': False, 'message': f'查询失败: {str(e)}'}), 500


@app.route('/operation/fba_shipping_methods')
def operation_fba_shipping_methods_page():
    if not _operation_dept_has_access():
        flash('无权限访问FBA货件运输方式')
        return redirect(url_for('dashboard'))
    source = str(request.args.get('source') or '').strip()
    dept_names = {
        'operation_dept_1': '运营一部',
        'operation_dept_2': '运营二部',
        'operation_dept_3': '运营三部',
        'operation_dept_6': '运营六部',
    }
    back_url = url_for(source) if source in _OPERATION_DEPT_FUNCTIONS else url_for('dashboard')
    return render_template(
        'operation_fba_shipping_methods.html',
        user_name=session.get('feishu_user_name', '用户'),
        source=source,
        source_name=dept_names.get(source, '运营部门'),
        back_url=back_url,
    )


@app.route('/operation_dept_1')
@require_permission('operation_dept_1')
def operation_dept_1():
    """运营一部功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='运营一部',
                           dept_id='operation_dept_1',
                           can_view_tk_90=(user_name in (dashboard_90_users or [])))


@app.route('/operation_dept_2')
@require_permission('operation_dept_2')
def operation_dept_2():
    """运营二部功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='运营二部',
                           dept_id='operation_dept_2')


@app.route('/operation_dept_3')
@require_permission('operation_dept_3')
def operation_dept_3():
    """运营三部功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='运营三部',
                           dept_id='operation_dept_3')


@app.route('/operation_dept_6')
@require_permission('operation_dept_6')
def operation_dept_6():
    """运营六部功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='运营六部',
                           dept_id='operation_dept_6',
                           can_view_tk_82=(user_name in (dashboard_82_users or [])),
                           can_view_tk_88=(user_name in (dashboard_88_users or [])))

@app.route('/tech_dept')
@require_permission('tech_dept')
def tech_dept():
    """技术部功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='技术部',
                           dept_id='tech_dept')

@app.route('/photography_dept')
@require_permission('photography_dept')
def photography_dept():
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='摄影部',
                           dept_id='photography_dept')

@app.route('/visual_design_dept')
@require_permission('visual_design_dept')
def visual_design_dept():
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='视觉设计部',
                           dept_id='visual_design_dept')

@app.route('/visual_design_dept/image_tool')
@require_permission('visual_design_dept')
def visual_design_image_tool():
    user_name = _normalize_feishu_user_name(session.get('feishu_user_name', ''), fallback='访客')
    _ensure_lashforge_watchdog_started()
    lashforge_url = _build_lashforge_entry_url(user_name)
    if _is_feishu_request() and request.args.get('embed') != '1':
        if _is_lashforge_reachable(timeout=0.8):
            return redirect(lashforge_url)
        return render_template(
            'lashforge_launch.html',
            user_name=user_name,
            lashforge_url=lashforge_url,
        )
    return render_template(
        'lashforge_embed.html',
        user_name=user_name,
        lashforge_url=lashforge_url,
    )


@app.route('/visual_design_dept/image_tool/status')
@require_permission('visual_design_dept')
def visual_design_image_tool_status():
    ready = _is_lashforge_reachable(timeout=1)
    if not ready:
        _ensure_lashforge_watchdog_started()
    return jsonify({'ready': ready})

@app.route('/shenzhen_dept')
@require_permission('shenzhen_dept')
def shenzhen_dept():
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='深圳团队',
                           dept_id='shenzhen_dept')

@app.route('/newcomer_group')
@require_permission('newcomer_group')
def newcomer_group():
    """新人组功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='新人组',
                           dept_id='newcomer_group',
                           can_view_tk_88=(user_name in (dashboard_88_users or [])))


def generate_cache_key(product_name, features, script_number):
    """生成缓存键"""
    features_str = "|".join(sorted(features))
    return f"{product_name}_{features_str}_{script_number}"


def call_ai_api(product_name, product_features, script_number):
    """调用AI API生成脚本（带缓存）"""
    try:
        # 检查缓存
        cache_key = generate_cache_key(product_name, product_features, script_number)
        with cache_lock:
            if cache_key in script_cache:
                _safe_debug_print(f"使用缓存脚本: {cache_key}")
                return script_cache[cache_key]

        features_text = "、".join(product_features)

        style_variations = [
            "充满激情和感染力",
            "更加生动活泼",
            "富有创意和想象力",
            "更具说服力",
            "更加幽默风趣"
        ]

        current_style = style_variations[(script_number - 1) % len(style_variations)]

        prompt = f"""
你是一位专业的美国TIKTOk短视频脚本撰写专家。请为以下假睫毛产品创作一个吸引人的口播脚本：

产品名称：{product_name}
产品特征：{features_text}

要求：
1. 脚本要适合TIKTOK美国达人的风格，{current_style}要沉浸式
2. 突出产品的独特卖点和优势
3. 语言要生动有趣，能够吸引观众注意力
4. 包含产品使用效果的描述
5. 脚本长度控制在30-60秒的口播时间
6. 使用英文撰写，符合美国观众的语言习惯
7. 包含适当的情感渲染和互动元素
8. 这是第{script_number}个版本，请确保与之前的版本有所不同

请生成一个完整的口播脚本：
"""

        messages = [
            {
                "role": "system",
                "content": "You are a professional script writer for TikTok, specializing in creating engaging and passionate product presentations for eyelash products."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        script_content = _ai_chat_complete(
            messages,
            max_tokens=800,
            temperature=0.8,
            model_candidates=_OPENAI_TEXT_MODEL_CANDIDATES
        )

        # 缓存结果
        with cache_lock:
            script_cache[cache_key] = script_content
            # 限制缓存大小
            if len(script_cache) > 100:
                # 删除最旧的缓存项
                oldest_key = next(iter(script_cache))
                del script_cache[oldest_key]

        return script_content

    except Exception as e:
        _safe_debug_print(f"AI API调用错误: {str(e)}")
        # 返回一个默认的脚本模板
        return f"""
Hey TikTok fam! 🔥 Let me tell you about these AMAZING {product_name}! 

These lashes are absolutely STUNNING and will transform your entire look! ✨ 
{', '.join(product_features)} - can you believe it?!

I'm literally obsessed with how natural yet dramatic they look! 
Your eyes will POP and everyone will be asking where you got them! 💫

Trust me, once you try these, you'll never go back to your old lashes! 
Who's ready to level up your lash game? Drop a 💕 if you want the link!

#FalseLashes #BeautyTips #LashGoals #MakeupHacks
"""


@app.route('/image_generator')
def image_generator():
    """图像生成器页面"""
    return render_template('image_generator.html')


@app.route('/generate_image', methods=['POST'])
def generate_image():
    """生成图像API"""
    try:
        data = request.get_json()
        prompt = data.get('prompt', '').strip()
        size = data.get('size', '1024x1024')
        quality = data.get('quality', 'standard')

        if not prompt:
            return jsonify({
                'success': False,
                'message': '请提供图像描述'
            })

        # 调用DALL-E 3 API生成图像
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size=size,
            quality=quality
        )

        image_url = response.data[0].url

        return jsonify({
            'success': True,
            'image_url': image_url,
            'prompt': prompt,
            'size': size,
            'quality': quality
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'生成图像时发生错误: {str(e)}'
        })


@app.route('/ai_modules')
def ai_modules():
    """AI模块页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('ai_modules.html', user_id=user_id, user_name=user_name)


def _get_env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return default


def _get_env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return default


def _normalize_chat_completions_url(base_url):
    normalized = str(base_url or '').strip().rstrip('/')
    if not normalized:
        normalized = 'https://api.siliconflow.cn/v1'
    if normalized.endswith('/chat/completions'):
        return normalized
    return f'{normalized}/chat/completions'


def _get_amazon_reply_service():
    global _amazon_reply_service
    if _amazon_reply_service is not None:
        return _amazon_reply_service
    from amazon_reply_service import AmazonReplyService, SiliconFlowConfig, SqlServerConfig, normalize_model

    db_defaults = sql_server_config(include_port=True)
    db_config = SqlServerConfig(
        server=str(db_defaults.get('server') or ''),
        port=int(db_defaults.get('port') or 1433),
        database=str(db_defaults.get('database') or ''),
        user=str(db_defaults.get('user') or ''),
        password=str(db_defaults.get('password') or ''),
    )
    shared_api_key = (
        os.environ.get('SILICONFLOW_API_KEY')
        or os.environ.get('OPENAI_API_KEY')
        or OPENAI_API_KEY
        or AI_RUNTIME_CONFIG.get('api_key')
        or ''
    )
    shared_base_url = (
        os.environ.get('SILICONFLOW_BASE_URL')
        or os.environ.get('OPENAI_BASE_URL')
        or API_BASE_URL
        or AI_RUNTIME_CONFIG.get('base_url')
        or 'https://api.siliconflow.cn/v1'
    )
    ai_config = SiliconFlowConfig(
        api_key=str(shared_api_key or '').strip(),
        model=normalize_model(os.environ.get('SILICONFLOW_MODEL') or os.environ.get('OPENAI_TEXT_MODEL') or _OPENAI_TEXT_MODEL),
        base_url=_normalize_chat_completions_url(shared_base_url),
        temperature=_get_env_float('SILICONFLOW_TEMPERATURE', 0.2),
        max_tokens=_get_env_int('AMAZON_REPLY_MAX_TOKENS', _get_env_int('SILICONFLOW_MAX_TOKENS', 450)),
        timeout_seconds=_get_env_int('AMAZON_REPLY_TIMEOUT_SECONDS', _get_env_int('SILICONFLOW_TIMEOUT_SECONDS', 35)),
        retry_count=_get_env_int('AMAZON_REPLY_RETRY_COUNT', _get_env_int('SILICONFLOW_RETRY_COUNT', 0)),
    )
    _amazon_reply_service = AmazonReplyService(db_config, ai_config)
    return _amazon_reply_service


@app.route('/amazon_reply_agent')
@require_permission('amazon_reply_agent')
def amazon_reply_agent():
    user_name = session.get('feishu_user_name', '用户')
    source = str(request.args.get('source') or '').strip()
    return_url_map = {
        'operation_dept_1': url_for('operation_dept_1'),
        'operation_dept_2': url_for('operation_dept_2'),
        'operation_dept_3': url_for('operation_dept_3'),
        'operation_dept_6': url_for('operation_dept_6'),
    }
    return render_template(
        'amazon_reply_agent.html',
        user_name=user_name,
        return_url=return_url_map.get(source) or url_for('ai_modules'),
        return_label=('返回运营功能' if source in return_url_map else '返回AI功能')
    )


@app.route('/api/ai/amazon_reply/generate', methods=['POST'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_generate():
    try:
        data = request.get_json(silent=True) or {}
        buyer_question = str(data.get('buyerQuestion') or data.get('buyer_question') or '').strip()
        extra_context = str(data.get('extraContext') or data.get('extra_context') or '').strip()
        if not buyer_question:
            return jsonify({'success': False, 'message': '请先填写买家站内信内容'}), 400
        if len(buyer_question) > 5000 or len(extra_context) > 5000:
            return jsonify({'success': False, 'message': '输入内容过长，请精简后再生成'}), 400
        result = _get_amazon_reply_service().generate_reply(
            buyer_question=buyer_question,
            extra_context=extra_context,
        )
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500


def _amazon_reply_text_list(value):
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r'[\n,，;；]+', str(value or ''))
    result = []
    seen = set()
    for item in raw_items:
        text = str(item or '').strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _amazon_reply_rule_type(raw_type):
    normalized = str(raw_type or '').strip().lower()
    from amazon_reply_service import RULE_TYPE_PROHIBITED, RULE_TYPE_SENSITIVE

    if normalized in {'prohibited', 'forbidden', 'ban', '禁用词'}:
        return RULE_TYPE_PROHIBITED
    if normalized in {'sensitive', 'sensitive_phrase', '敏感词', '敏感短语'}:
        return RULE_TYPE_SENSITIVE
    raise ValueError('规则类型只能是禁用词或敏感词')


@app.route('/api/ai/amazon_reply/rules', methods=['GET'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_rules():
    try:
        data = _get_amazon_reply_service().list_management_items()
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500


@app.route('/api/ai/amazon_reply/rules', methods=['POST'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_add_rule():
    try:
        data = request.get_json(silent=True) or {}
        rule_type = _amazon_reply_rule_type(data.get('ruleType') or data.get('type'))
        content = str(data.get('content') or '').strip()
        safe_hint = str(data.get('safeHint') or data.get('safe_hint') or '').strip()
        item = _get_amazon_reply_service().add_rule(rule_type, content, safe_hint)
        return jsonify({'success': True, 'data': item})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400


@app.route('/api/ai/amazon_reply/rules/<int:rule_id>', methods=['DELETE'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_delete_rule(rule_id):
    try:
        _get_amazon_reply_service().disable_rule(rule_id)
        return jsonify({'success': True, 'message': '已删除'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500


@app.route('/api/ai/amazon_reply/scenarios', methods=['POST'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_add_scenario():
    try:
        data = request.get_json(silent=True) or {}
        item = _get_amazon_reply_service().add_scenario(
            title=str(data.get('title') or '').strip(),
            keywords=_amazon_reply_text_list(data.get('keywords')),
            buyer_examples=_amazon_reply_text_list(data.get('buyerExamples') or data.get('buyer_examples')),
            seller_reply_en=str(data.get('sellerReplyEn') or data.get('seller_reply_en') or '').strip(),
            seller_reply_zh=str(data.get('sellerReplyZh') or data.get('seller_reply_zh') or '').strip(),
            internal_notes=str(data.get('internalNotes') or data.get('internal_notes') or '').strip(),
        )
        return jsonify({'success': True, 'data': item})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400


@app.route('/api/ai/amazon_reply/scenarios/<int:scenario_id>', methods=['DELETE'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_delete_scenario(scenario_id):
    try:
        _get_amazon_reply_service().disable_scenario(scenario_id)
        return jsonify({'success': True, 'message': '已删除'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500


def _permission_debug_available_departments():
    names = set()
    for v in PERMISSION_CONFIG.values():
        if not isinstance(v, dict):
            continue
        allowed = v.get('allowed_departments')
        if allowed == 'all':
            continue
        if isinstance(allowed, list):
            for one in allowed:
                name = str(one or '').strip()
                if name:
                    names.add(name)
    for mapped in getattr(permission_manager, 'get_department_mapping_stats', lambda: {})().get('department_list', []) or []:
        name = str(mapped or '').strip()
        if name:
            names.add(name)
    return sorted(list(names), key=lambda x: x)


def _permission_debug_session_state():
    current = session.get('permission_debug_departments') or []
    if isinstance(current, str):
        current = [current]
    current = [str(x).strip() for x in current if str(x).strip()]
    debug_user_name = str(session.get('permission_debug_user_name') or '').strip()
    debug_user_open_id = str(session.get('permission_debug_user_open_id') or '').strip()
    mode = 'user' if debug_user_name else ('department' if current else '')
    return {
        'enabled': bool(mode),
        'mode': mode,
        'current_departments': current,
        'current_user_name': debug_user_name,
        'current_user_open_id': debug_user_open_id,
    }


@app.route('/api/ai/permission_debug/status', methods=['GET'])
@require_permission('ai_dept')
def api_ai_permission_debug_status():
    state = _permission_debug_session_state()
    return jsonify({
        'success': True,
        'data': {
            'enabled': bool(state.get('enabled')),
            'mode': str(state.get('mode') or ''),
            'current_departments': list(state.get('current_departments') or []),
            'current_user_name': str(state.get('current_user_name') or ''),
            'current_user_open_id': str(state.get('current_user_open_id') or ''),
            'departments': _permission_debug_available_departments()
        }
    })


@app.route('/api/ai/permission_debug/switch', methods=['POST'])
@require_permission('ai_dept')
def api_ai_permission_debug_switch():
    data = request.get_json(silent=True) or {}
    target_user_name = _normalize_feishu_user_name(data.get('user_name') or '', fallback='').strip()
    target = data.get('departments')
    if isinstance(target, str):
        target = [target]
    if not isinstance(target, list):
        return jsonify({'success': False, 'message': 'departments 参数格式错误'}), 400
    cleaned = []
    mode_text = ''
    debug_user_open_id = ''
    if target_user_name:
        debug_user_open_id = str(_xiaotu_lookup_open_id_by_name(target_user_name) or '').strip()
        if not debug_user_open_id.startswith('ou_'):
            return jsonify({'success': False, 'message': f'未找到用户：{target_user_name}'}), 400
        user_rows = permission_manager.get_user_departments(debug_user_open_id) or []
        seen = set()
        for row in user_rows:
            if not isinstance(row, dict):
                continue
            if str(row.get('status') or '').strip() in {'invalid', 'unmapped'}:
                continue
            dept_name = str(row.get('name') or '').strip()
            if not dept_name or dept_name in seen:
                continue
            seen.add(dept_name)
            cleaned.append(dept_name)
        session['permission_debug_departments'] = cleaned
        session['permission_debug_user_name'] = target_user_name
        session['permission_debug_user_open_id'] = debug_user_open_id
        session['permission_debug_updated_at'] = datetime.now().isoformat()
        mode_text = (
            f"已切换为模拟用户：{target_user_name}"
            + (f"（部门：{'、'.join(cleaned)}）" if cleaned else "（未识别到有效部门）")
        )
    else:
        available = set(_permission_debug_available_departments())
        seen = set()
        for one in target:
            name = str(one or '').strip()
            if not name or name in seen:
                continue
            if name not in available:
                return jsonify({'success': False, 'message': f'无效部门: {name}'}), 400
            seen.add(name)
            cleaned.append(name)
        if cleaned:
            session['permission_debug_departments'] = cleaned
            session['permission_debug_updated_at'] = datetime.now().isoformat()
            session.pop('permission_debug_user_name', None)
            session.pop('permission_debug_user_open_id', None)
            mode_text = f"已切换为模拟部门: {'、'.join(cleaned)}"
    if not cleaned and not target_user_name:
        session.pop('permission_debug_departments', None)
        session.pop('permission_debug_updated_at', None)
        session.pop('permission_debug_user_name', None)
        session.pop('permission_debug_user_open_id', None)
        mode_text = '已恢复真实部门权限'
    # 清理预加载缓存，确保首页权限卡片立即按新身份重算
    session.pop('preloaded_functions', None)
    session.pop('preloaded_departments', None)
    session.pop('preload_time', None)
    session.modified = True
    state = _permission_debug_session_state()
    return jsonify({
        'success': True,
        'message': mode_text,
        'data': {
            'enabled': bool(state.get('enabled')),
            'mode': str(state.get('mode') or ''),
            'current_departments': list(state.get('current_departments') or []),
            'current_user_name': str(state.get('current_user_name') or ''),
            'current_user_open_id': str(state.get('current_user_open_id') or ''),
        }
    })


@app.route('/permission_debug/clear', methods=['GET'])
def permission_debug_clear():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    session.pop('permission_debug_departments', None)
    session.pop('permission_debug_updated_at', None)
    session.pop('permission_debug_user_name', None)
    session.pop('permission_debug_user_open_id', None)
    session.pop('preloaded_functions', None)
    session.pop('preloaded_departments', None)
    session.pop('preload_time', None)
    session.modified = True
    flash('已恢复真实身份权限', 'success')
    to_mobile = str(request.args.get('mobile') or '').strip().lower() in {'1', 'true', 'yes'}
    return redirect(url_for('dashboard_mobile' if to_mobile else 'dashboard'))

@app.route('/finance_modules')
@require_permission('finance_dept')
def finance_modules():
    return render_template('finance_modules.html')


@app.route('/hr_admin_modules')
@require_permission('hr_admin_dept')
def hr_admin_modules():
    return render_template('hr_admin_modules.html')


@app.route('/hr_admin/innovation_data')
@require_permission('hr_admin_dept')
def hr_admin_innovation_data():
    return render_template('hr_innovation_data.html')


def _hr_innovation_json_value(value):
    if value is None:
        return ""
    if isinstance(value, (int, float, str, bool)):
        return value
    try:
        import decimal
        if isinstance(value, decimal.Decimal):
            return float(value)
    except Exception:
        pass
    if isinstance(value, (datetime, date)):
        return value.strftime('%Y-%m-%d')
    return str(value)


def _hr_innovation_normalize_rows(rows, columns):
    out = []
    for row in rows or []:
        if isinstance(row, dict):
            item = {}
            for col in columns:
                item[col] = _hr_innovation_json_value(row.get(col) if col in row else row.get(str(col).lower()))
            out.append(item)
            continue
        values = list(row) if isinstance(row, (list, tuple)) else []
        out.append({
            col: _hr_innovation_json_value(values[idx] if idx < len(values) else "")
            for idx, col in enumerate(columns)
        })
    return out


@app.route('/api/hr/innovation_data')
@require_permission('hr_admin_dept')
def api_hr_innovation_data():
    try:
        monthly_total = sf_db("""
            SELECT
                FORMAT(发起时间, 'yyyy-MM') AS 月份,
                COUNT(*) AS 数量
            FROM v_QuanYuanChuangXin
            GROUP BY FORMAT(发起时间, 'yyyy-MM')
            ORDER BY 月份
        """) or []
        monthly_department_total = sf_db("""
            SELECT
                FORMAT(发起时间, 'yyyy-MM') AS 月份,
                COUNT(*) AS 数量,
                CASE WHEN 部门 IN ('TK_离职','TK项目') THEN 'TK项目' ELSE 部门 END AS 部门
            FROM v_QuanYuanChuangXin
            GROUP BY FORMAT(发起时间, 'yyyy-MM'), CASE WHEN 部门 IN ('TK_离职','TK项目') THEN 'TK项目' ELSE 部门 END
            ORDER BY 月份, 部门
        """) or []
        valid_department_total = sf_db("""
            SELECT
                FORMAT(发起时间, 'yyyy-MM') AS 月份,
                COUNT(*) AS 有效提案数量,
                CASE WHEN 部门 IN ('TK_离职','TK项目') THEN 'TK项目' ELSE 部门 END AS 部门
            FROM v_QuanYuanChuangXin
            WHERE 最高分 > 0
            GROUP BY FORMAT(发起时间, 'yyyy-MM'), CASE WHEN 部门 IN ('TK_离职','TK项目') THEN 'TK项目' ELSE 部门 END
            ORDER BY 月份, 部门
        """) or []
        monthly_people = sf_db("""
            SELECT DISTINCT
                CONVERT(char(7), 发起时间, 120) AS 月份,
                发起人,
                CASE WHEN 部门 IN ('TK_离职','TK项目') THEN 'TK项目' ELSE 部门 END AS 部门
            FROM v_QuanYuanChuangXin
            ORDER BY 月份, 部门, 发起人
        """) or []
        score_distribution = sf_db("""
            SELECT
                FORMAT(发起时间, 'yyyy-MM') AS 月份,
                COUNT(*) AS 数量,
                最高分 AS 分数,
                CASE WHEN 部门 IN ('TK_离职','TK项目') THEN 'TK项目' ELSE 部门 END AS 部门
            FROM v_QuanYuanChuangXin
            GROUP BY FORMAT(发起时间, 'yyyy-MM'), CASE WHEN 部门 IN ('TK_离职','TK项目') THEN 'TK项目' ELSE 部门 END, 最高分
            ORDER BY 月份, 部门, 分数
        """) or []
        category_distribution = sf_db("""
            SELECT
                FORMAT(发起时间, 'yyyy-MM') AS 月份,
                COUNT(*) AS 数量,
                创新类别
            FROM v_QuanYuanChuangXin
            GROUP BY FORMAT(发起时间, 'yyyy-MM'), 创新类别
            ORDER BY 月份, 创新类别
        """) or []
        return jsonify({
            'success': True,
            'data': {
                'monthly_total': _hr_innovation_normalize_rows(monthly_total, ['月份', '数量']),
                'monthly_department_total': _hr_innovation_normalize_rows(monthly_department_total, ['月份', '数量', '部门']),
                'valid_department_total': _hr_innovation_normalize_rows(valid_department_total, ['月份', '有效提案数量', '部门']),
                'monthly_people': _hr_innovation_normalize_rows(monthly_people, ['月份', '发起人', '部门']),
                'score_distribution': _hr_innovation_normalize_rows(score_distribution, ['月份', '数量', '分数', '部门']),
                'category_distribution': _hr_innovation_normalize_rows(category_distribution, ['月份', '数量', '创新类别']),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取创新数据失败: {str(e)}'}), 500


@app.route('/finance_sz_dashboard')
@require_permission('tk_total_dashboard')
def finance_sz_dashboard():
    return render_template('finance_sz_dashboard.html')


@app.route('/api/finance/sz_expenses')
@require_permission('tk_total_dashboard')
def api_finance_sz_expenses():
    try:
        base_month = request.args.get('base_month', '')
        months, data = compute_shenzhen_expenses(base_month)
        return jsonify({'success': True, 'months': months, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'查询失败: {str(e)}'}), 500


def _export_approval_amounts_core(start_date, end_date, approval_code, source):
    import requests, time, json
    if source != 'feishu':
        return jsonify({'success': False, 'message': '仅支持从飞书审批中心拉取'}), 400
    token = permission_manager.get_access_token()
    if not token:
        return jsonify({'success': False, 'message': '获取飞书访问令牌失败'}), 500
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json; charset=utf-8'
    }
    def to_ts(s):
        if not s:
            return None
        try:
            from datetime import datetime
            dt = datetime.strptime(s.strip(), '%Y-%m-%d')
            return int(time.mktime(dt.timetuple()))
        except Exception:
            return None
    start_ts = to_ts(start_date)
    end_ts = to_ts(end_date)
    if not start_ts or not end_ts:
        end_ts = int(time.time())
        start_ts = end_ts - 30 * 24 * 3600
    approvals = []
    code_name_map = {}
    if approval_code:
        approvals = [approval_code]
        code_name_map[approval_code] = ''
    else:
        url_list = 'https://open.feishu.cn/open-apis/approval/v4/approvals'
        page_token = None
        while True:
            params = {'page_size': 100}
            if page_token:
                params['page_token'] = page_token
            r = requests.get(url_list, headers=headers, params=params).json()
            if r.get('code') != 0:
                break
            items = r.get('data', {}).get('items') or r.get('data', {}).get('approval_list') or []
            for it in items:
                code = it.get('approval_code') or it.get('code') or ''
                name = it.get('name') or it.get('approval_name') or ''
                if code:
                    approvals.append(code)
                    code_name_map[code] = name
            page_token = r.get('data', {}).get('page_token') or r.get('data', {}).get('next_page_token')
            if not page_token:
                break
    results = []
    url_instances = 'https://open.feishu.cn/open-apis/approval/v4/instances'
    def extract_amounts(form_obj):
        amounts = []
        fields = []
        try:
            if isinstance(form_obj, str):
                form_obj = json.loads(form_obj)
        except Exception:
            form_obj = {}
        def scan(v, kpath=''):
            try:
                if isinstance(v, dict):
                    for k, val in v.items():
                        kp = f"{kpath}.{k}" if kpath else str(k)
                        scan(val, kp)
                elif isinstance(v, list):
                    for i, val in enumerate(v):
                        scan(val, f"{kpath}[{i}]")
                else:
                    if isinstance(v, (int, float)):
                        amounts.append(float(v))
                        fields.append(f"{kpath}={v}")
                    else:
                        s = str(v)
                        if any(w in (kpath or '') for w in ['金额', '费用', '金额(元)']):
                            try:
                                num = float(s.replace(',', ''))
                                amounts.append(num)
                                fields.append(f"{kpath}={num}")
                            except Exception:
                                pass
            except Exception:
                pass
        scan(form_obj)
        total = amounts[0] if amounts else 0
        return total, ';'.join(fields[:6])
    for code in approvals:
        page_token = None
        while True:
            params = {
                'approval_code': code,
                'start_time': start_ts,
                'end_time': end_ts,
                'page_size': 100
            }
            if page_token:
                params['page_token'] = page_token
            r = requests.get(url_instances, headers=headers, params=params).json()
            if r.get('code') != 0:
                try:
                    params['start_time'] = start_ts * 1000
                    params['end_time'] = end_ts * 1000
                    r = requests.get(url_instances, headers=headers, params=params).json()
                except Exception:
                    pass
                if r.get('code') != 0:
                    break
            items = r.get('data', {}).get('items') or r.get('data', {}).get('instance_list') or []
            for it in items:
                form = it.get('form') or it.get('form_value') or it.get('form_values') or {}
                amt, detail = extract_amounts(form)
                st = it.get('start_time') or it.get('create_time') or 0
                ft = it.get('end_time') or it.get('finish_time') or 0
                def fmt(ts):
                    try:
                        from datetime import datetime
                        return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S') if ts else ''
                    except Exception:
                        return ''
                title = it.get('title') or it.get('approval_name') or ''
                status = it.get('status') or it.get('instance_status') or ''
                originator = it.get('user_id') or it.get('originator_user_id') or ''
                instance_code = it.get('instance_code') or ''
                results.append([
                    instance_code,
                    title,
                    code_name_map.get(code, ''),
                    originator,
                    '',
                    amt,
                    status,
                    fmt(st),
                    fmt(ft),
                    detail
                ])
            page_token = r.get('data', {}).get('page_token') or r.get('data', {}).get('next_page_token')
            if not page_token:
                break
    preview = request.args.get('preview')
    if not results:
        if preview:
            return jsonify({'success': True, 'message': '无记录', 'approvals': approvals, 'count': 0})
        return jsonify({'success': False, 'message': '没有数据可导出'}), 404
    import pandas as pd
    from io import BytesIO
    buf = BytesIO()
    cols = ['实例编码', '审批标题', '审批类型', '申请人', '部门', '金额', '状态', '发起时间', '完成时间', '金额字段明细']
    df = pd.DataFrame(results, columns=cols)
    df.sort_values(by=['发起时间'], inplace=True, ascending=False)
    df.to_excel(buf, index=False, engine='openpyxl')
    buf.seek(0)
    filename_suffix = f"_{start_date}_to_{end_date}" if start_date and end_date else ""
    filename = f"飞书审批金额明细{filename_suffix}.xlsx"
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=filename)

@app.route('/api/export_approval_amounts', methods=['GET'])
@require_permission('ai_dept')
def export_approval_amounts():
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        approval_code = request.args.get('approval_code')
        source = request.args.get('source', 'feishu')
        return _export_approval_amounts_core(start_date, end_date, approval_code, source)
    except Exception as e:
        return jsonify({'success': False, 'message': f'导出失败: {str(e)}'}), 500

@app.route('/api/export_approval_amounts_finance', methods=['GET'])
@require_permission('finance_dept')
def export_approval_amounts_finance():
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        approval_code = request.args.get('approval_code')
        source = request.args.get('source', 'feishu')
        return _export_approval_amounts_core(start_date, end_date, approval_code, source)
    except Exception as e:
        return jsonify({'success': False, 'message': f'导出失败: {str(e)}'}), 500

@app.route('/api/feishu/approvals', methods=['GET'])
@require_permission('ai_dept')
def list_feishu_approvals():
    try:
        token = permission_manager.get_access_token()
        if not token:
            return jsonify({'success': False, 'message': '获取飞书访问令牌失败'}), 500
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        url_list = 'https://open.feishu.cn/open-apis/approval/v4/approvals'
        page_token = None
        items_all = []
        while True:
            params = {'page_size': 100}
            if page_token:
                params['page_token'] = page_token
            r = requests.get(url_list, headers=headers, params=params).json()
            if r.get('code') != 0:
                break
            items = r.get('data', {}).get('items') or r.get('data', {}).get('approval_list') or []
            for it in items:
                items_all.append({
                    'code': it.get('approval_code') or it.get('code') or '',
                    'name': it.get('name') or it.get('approval_name') or ''
                })
            page_token = r.get('data', {}).get('page_token') or r.get('data', {}).get('next_page_token')
            if not page_token:
                break
        return jsonify({'success': True, 'data': items_all})
    except Exception as e:
        return jsonify({'success': False, 'message': f'拉取失败: {str(e)}'}), 500

@app.route('/api/feishu/approvals_finance', methods=['GET'])
@require_permission('finance_dept')
def list_feishu_approvals_finance():
    try:
        token = permission_manager.get_access_token()
        if not token:
            return jsonify({'success': False, 'message': '获取飞书访问令牌失败'}), 500
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        url_list = 'https://open.feishu.cn/open-apis/approval/v4/approvals'
        page_token = None
        items_all = []
        while True:
            params = {'page_size': 100}
            if page_token:
                params['page_token'] = page_token
            r = requests.get(url_list, headers=headers, params=params).json()
            if r.get('code') != 0:
                break
            items = r.get('data', {}).get('items') or r.get('data', {}).get('approval_list') or []
            for it in items:
                items_all.append({
                    'code': it.get('approval_code') or it.get('code') or '',
                    'name': it.get('name') or it.get('approval_name') or ''
                })
            page_token = r.get('data', {}).get('page_token') or r.get('data', {}).get('next_page_token')
            if not page_token:
                break
        return jsonify({'success': True, 'data': items_all})
    except Exception as e:
        return jsonify({'success': False, 'message': f'拉取失败: {str(e)}'}), 500

@app.route('/api/finance/import_expense_sheet', methods=['POST'])
@require_permission('finance_dept')
def import_expense_sheet():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未发现文件'}), 400
        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'}), 400
        import pandas as pd
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return jsonify({'success': False, 'message': f'读取Excel失败: {str(e)}'}), 400
        cols_map = {str(c).strip(): c for c in df.columns}
        required = ['日期','费用类别','摘要','借方','贷方','报销人','项目','银行类别','部门']
        missing = [c for c in required if c not in cols_map]
        if missing:
            return jsonify({'success': False, 'message': f'缺少列: {"、".join(missing)}'}), 400
        def esc(v):
            return '' if v is None else str(v).strip().replace("'","''")
        def parse_date(v):
            import pandas as pd
            from datetime import datetime
            if pd.isna(v):
                return None
            if hasattr(v,'strftime'):
                return v.strftime('%Y-%m-%d')
            s = str(v).strip()
            if not s:
                return None
            for fmt in ['%Y-%m-%d','%Y-%m-%d %H:%M:%S','%Y/%m/%d','%Y-%m-%dT%H:%M:%S']:
                try:
                    return datetime.strptime(s,fmt).strftime('%Y-%m-%d')
                except Exception:
                    pass
            try:
                parts = s.replace('/','-').split('-')
                if len(parts)==3:
                    y = int(parts[0]); m = int(parts[1]); d = int(parts[2])
                    return f"{y:04d}-{m:02d}-{d:02d}"
            except Exception:
                pass
            return None
        def parse_num(v):
            import pandas as pd
            if pd.isna(v):
                return None
            s = str(v).strip().replace(',','')
            if s=='':
                return None
            try:
                return round(float(s),2)
            except Exception:
                return None
        inserted = 0
        updated = 0
        errors = []
        for idx, row in df.iterrows():
            d = parse_date(row.get(cols_map['日期']))
            lei = esc(row.get(cols_map['费用类别']))
            zhai = esc(row.get(cols_map['摘要']))
            jiefang = parse_num(row.get(cols_map['借方']))
            daifang = parse_num(row.get(cols_map['贷方']))
            baoxiaoren = esc(row.get(cols_map['报销人']))
            xiangmu = esc(row.get(cols_map['项目']))
            yinhang = esc(row.get(cols_map['银行类别']))
            bumen = esc(row.get(cols_map['部门']))
            if not d:
                errors.append(f'第{idx+1}行日期无效')
                continue
            conds = [
                f"日期 = '{d}'",
                f"费用类别 = '{lei}'",
                f"摘要 = '{zhai}'",
                ("借方 IS NULL" if jiefang is None else f"借方 = {jiefang}"),
                ("贷方 IS NULL" if daifang is None else f"贷方 = {daifang}"),
                f"报销人 = '{baoxiaoren}'",
                f"项目 = '{xiangmu}'",
                f"银行类别 = '{yinhang}'",
                f"部门 = '{bumen}'"
            ]
            dup_sql = f"SELECT COUNT(*) FROM 财务_费用明细 WHERE {' AND '.join(conds)}"
            try:
                cnt = sf_db(dup_sql, single=True)
                cnt = int(cnt or 0)
            except Exception:
                cnt = 0
            if cnt > 0:
                errors.append(
                    f"重复记录，已跳过: 日期={d}, 费用类别={lei}, 摘要={zhai}, 借方={'' if jiefang is None else jiefang}, 贷方={'' if daifang is None else daifang}, 报销人={baoxiaoren}, 项目={xiangmu}, 银行类别={yinhang}, 部门={bumen}"
                )
                continue
            vals = [
                f"'{d}'",
                f"'{lei}'",
                f"'{zhai}'",
                'NULL' if jiefang is None else str(jiefang),
                'NULL' if daifang is None else str(daifang),
                f"'{baoxiaoren}'",
                f"'{xiangmu}'",
                f"'{yinhang}'",
                f"'{bumen}'"
            ]
            sql = f"INSERT INTO 财务_费用明细 (日期, 费用类别, 摘要, 借方, 贷方, 报销人, 项目, 银行类别, 部门) VALUES ({', '.join(vals)})"
            try:
                dui_db(sql)
                inserted += 1
            except Exception as e:
                errors.append(f"第{idx+1}行插入失败: {str(e)}")
        return jsonify({'success': True, 'inserted': inserted, 'errors': errors, 'message': f'成功 {inserted} 条，失败 {len(errors)} 条'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'导入失败: {str(e)}'})


@app.route('/api/finance/export_expense_sheet', methods=['GET'])
@require_permission('finance_dept')
def export_expense_sheet():
    try:
        sql = "SELECT 日期, 费用类别, 摘要, 借方, 贷方, 报销人, 项目, 银行类别, 部门 FROM 财务_费用明细 ORDER BY 日期, 费用类别, 摘要"
        rows = sf_db(sql) or []
        if not rows:
            return jsonify({'success': False, 'message': '没有数据可导出'}), 404
        import pandas as pd
        from io import BytesIO
        buf = BytesIO()
        cols = ['日期', '费用类别', '摘要', '借方', '贷方', '报销人', '项目', '银行类别', '部门']
        df = pd.DataFrame(rows, columns=cols)
        df.to_excel(buf, index=False, engine='openpyxl')
        buf.seek(0)
        filename = '费用明细.xlsx'
        return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'success': False, 'message': f'导出失败: {str(e)}'}), 500


@app.route('/api/finance/export_freight', methods=['GET'])
@require_permission('finance_dept')
def export_freight():
    try:
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()
        stores_raw = request.args.get('stores', '').strip()
        if not start_date or not end_date:
            return jsonify({'success': False, 'message': '开始日期和结束日期不能为空'}), 400
        where = [
            f"结算日期 >= '{start_date}'",
            f"结算日期 <= '{end_date}'"
        ]
        shops = []
        if stores_raw:
            parts = [p.strip() for p in stores_raw.replace('，', ',').split(',') if p.strip()]
            if parts:
                shop_list = []
                for s in parts:
                    s2 = s.replace("'", "''")
                    shop_list.append(f"'{s2}'")
                    shops.append(s2)
                where.append(f"店 IN ({', '.join(shop_list)})")
        where_sql = ' AND '.join(where)
        sql = f"""
SELECT 
  物流运费, 
  平台实际运费, 
  运费折扣, 
  退货运费, 
  单号, 
  sku, 
  结算日期,
  店
FROM v_TK_JieSuan js 
LEFT JOIN tk_dingdan dd ON dd.danhao = js.单号 
WHERE {where_sql}
ORDER BY 结算日期, 店, 单号, sku
"""
        rows = sf_db(sql) or []
        if not rows:
            return jsonify({'success': False, 'message': '没有数据可导出'}), 404
        import pandas as pd
        from io import BytesIO
        buf = BytesIO()
        cols = ['物流运费', '平台实际运费', '运费折扣', '退货运费', '单号', 'sku', '结算日期', '店']
        df = pd.DataFrame(rows, columns=cols)
        df.to_excel(buf, index=False, engine='openpyxl')
        buf.seek(0)
        if shops:
            shop_str = '_'.join(shops)
            filename = f'物流运费结算明细_{start_date}_{end_date}_{shop_str}.xlsx'
        else:
            filename = f'物流运费结算明细_{start_date}_{end_date}.xlsx'
        return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'success': False, 'message': f'导出失败: {str(e)}'}), 500

@app.route('/api/finance/import_allocation_ratio', methods=['POST'])
@require_permission('finance_dept')
def import_allocation_ratio():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未发现文件'}), 400
        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'}), 400
        import pandas as pd
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return jsonify({'success': False, 'message': f'读取Excel失败: {str(e)}'}), 400
        cols = {str(c).strip(): c for c in df.columns}
        required = ['年','月','地区','项目','店铺','比例']
        missing = [c for c in required if c not in cols]
        if missing:
            return jsonify({'success': False, 'message': f'缺少列: {"、".join(missing)}'}), 400
        def esc(v):
            return '' if v is None else str(v).strip().replace("'", "''")
        def parse_int(v):
            import pandas as pd
            if pd.isna(v):
                return None
            s = str(v).strip()
            if s == '':
                return None
            try:
                return int(float(s))
            except Exception:
                return None
        def parse_num(v):
            import pandas as pd
            if pd.isna(v):
                return None
            s = str(v).strip().replace(',', '')
            if s == '':
                return None
            try:
                return float(s)
            except Exception:
                return None
        inserted = 0
        updated = 0
        errors = []
        for idx, row in df.iterrows():
            nian = parse_int(row.get(cols['年']))
            yue = parse_int(row.get(cols['月']))
            diqu = esc(row.get(cols['地区']))
            xiangmu = esc(row.get(cols['项目']))
            dianpu = esc(row.get(cols['店铺']))
            bili = parse_num(row.get(cols['比例']))
            if nian is None:
                errors.append(f'第{idx+1}行年份无效')
                continue
            # 月份允许为空（NULL）
            if not diqu:
                errors.append(f'第{idx+1}行地区为空')
                continue
            if not xiangmu:
                errors.append(f'第{idx+1}行项目为空')
                continue
            if not dianpu:
                errors.append(f'第{idx+1}行店铺为空')
                continue
            if bili is None:
                errors.append(f'第{idx+1}行比例无效')
                continue
            yue_val = 'NULL' if yue is None else str(yue)
            conds = [
                f"年 = {nian}",
                (f"月 IS NULL" if yue is None else f"月 = {yue}"),
                f"地区 = '{diqu}'",
                f"项目 = '{xiangmu}'",
                f"店铺 = '{dianpu}'"
            ]
            where_clause = " AND ".join(conds)
            dup_sql = f"SELECT COUNT(*) FROM tk_费用分摊比例 WHERE {where_clause}"
            try:
                cnt = sf_db(dup_sql, single=True)
                cnt = int(cnt or 0)
            except Exception:
                cnt = 0
            if cnt > 0:
                sql = (
                    "UPDATE tk_费用分摊比例 "
                    f"SET 比例 = {bili} "
                    f"WHERE {where_clause}"
                )
                try:
                    dui_db(sql)
                    updated += 1
                except Exception as e:
                    errors.append(f"第{idx+1}行更新失败: {str(e)}")
                continue
            sql = (
                "INSERT INTO tk_费用分摊比例 (年, 月, 地区, 项目, 店铺, 比例) VALUES "
                f"({nian}, {yue_val}, '{diqu}', '{xiangmu}', '{dianpu}', {bili})"
            )
            try:
                dui_db(sql)
                inserted += 1
            except Exception as e:
                errors.append(f"第{idx+1}行插入失败: {str(e)}")
        return jsonify({
            'success': True,
            'inserted': inserted,
            'updated': updated,
            'errors': errors,
            'message': f'新增 {inserted} 条，更新 {updated} 条，失败 {len(errors)} 条'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'导入失败: {str(e)}'})

@app.route('/api/finance/import_wage_rent', methods=['POST'])
@require_permission('finance_dept')
def import_wage_rent():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未发现文件'}), 400
        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'}), 400
        import pandas as pd
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return jsonify({'success': False, 'message': f'读取Excel失败: {str(e)}'}), 400
        cols = {str(c).strip().lower(): c for c in df.columns}
        required = ['nian','yue','tuandui','xiangmu','feiyonge']
        missing = [c for c in required if c not in cols]
        if missing:
            return jsonify({'success': False, 'message': f'缺少列: {"、".join(missing)}'}), 400
        def esc(v):
            return '' if v is None else str(v).strip().replace("'", "''")
        def parse_int(v):
            import pandas as pd
            if pd.isna(v):
                return None
            s = str(v).strip()
            if s == '':
                return None
            try:
                return int(float(s))
            except Exception:
                return None
        def parse_num(v):
            import pandas as pd
            if pd.isna(v):
                return None
            s = str(v).strip().replace(',', '')
            if s == '':
                return None
            try:
                return float(s)
            except Exception:
                return None
        user_name = session.get('feishu_user_name', '')
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        inserted = 0
        updated = 0
        errors = []
        for idx, row in df.iterrows():
            nian = parse_int(row.get(cols['nian']))
            yue = parse_int(row.get(cols['yue']))
            tuandui = esc(row.get(cols['tuandui']))
            xiangmu = esc(row.get(cols['xiangmu']))
            feiyonge = parse_num(row.get(cols['feiyonge']))
            if nian is None:
                errors.append(f'第{idx+1}行年份无效')
                continue
            if yue is None or yue < 1 or yue > 12:
                errors.append(f'第{idx+1}行月份无效')
                continue
            if not tuandui:
                errors.append(f'第{idx+1}行团队为空')
                continue
            if not xiangmu:
                errors.append(f'第{idx+1}行项目为空')
                continue
            if feiyonge is None:
                errors.append(f'第{idx+1}行费用额无效')
                continue
            dup_sql = (
                f"SELECT COUNT(*) FROM tk_feiyong2 WHERE "
                f"Nian = {nian} AND Yue = {yue} AND TuanDui = '{tuandui}' AND XiangMu = '{xiangmu}'"
            )
            try:
                cnt = sf_db(dup_sql, single=True)
                cnt = int(cnt or 0)
            except Exception:
                cnt = 0
            if cnt > 0:
                sql = (
                    f"UPDATE tk_feiyong2 SET FeiYongE = {feiyonge}, "
                    f"DaoRuRen = '{esc(user_name)}', DaoRuShiJian = '{now_str}' "
                    f"WHERE Nian = {nian} AND Yue = {yue} AND TuanDui = '{tuandui}' AND XiangMu = '{xiangmu}'"
                )
                try:
                    dui_db(sql)
                    updated += 1
                except Exception as e:
                    errors.append(f"第{idx+1}行更新失败: {str(e)}")
            else:
                sql = (
                    "INSERT INTO tk_feiyong2 (Nian, Yue, TuanDui, XiangMu, FeiYongE, DaoRuRen, DaoRuShiJian) VALUES "
                    f"({nian}, {yue}, '{tuandui}', '{xiangmu}', {feiyonge}, '{esc(user_name)}', '{now_str}')"
                )
                try:
                    dui_db(sql)
                    inserted += 1
                except Exception as e:
                    errors.append(f"第{idx+1}行插入失败: {str(e)}")
        return jsonify({
            'success': True,
            'inserted': inserted,
            'updated': updated,
            'errors': errors,
            'message': f'新增 {inserted} 条，更新 {updated} 条，失败 {len(errors)} 条'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'导入失败: {str(e)}'})


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """提供上传文件的访问"""
    try:
        # 安全检查：防止路径遍历攻击
        if '..' in filename or filename.startswith('/'):
            return "Invalid filename", 400

        return send_from_directory(INNOVATION_APP_CONFIG['upload_folder'], filename)
    except Exception as e:
        _safe_debug_print(f"文件访问错误: {e}")
        return "File not found", 404


@app.route('/public-downloads/apr16-video')
def public_download_apr16_video():
    """固定公开下载链接：4月16日视频"""
    file_path = _PUBLIC_DOWNLOAD_APR16_VIDEO
    if not os.path.isfile(file_path):
        return "File not found", 404
    return send_file(
        file_path,
        as_attachment=True,
        download_name=os.path.basename(file_path),
        mimetype='video/mp4'
    )


@app.route('/<filename>.html')
def serve_static_html_files(filename):
    """处理根目录下的HTML文件"""
    try:
        html_filename = f"{filename}.html"
        return send_from_directory('.', html_filename)
    except Exception as e:
        _safe_debug_print(f"静态HTML文件访问错误: {e}")
        return "File not found", 404


# 飞书授权相关路由
@app.route('/login')
def login():
    """登录页面路由"""
    _safe_debug_print(f"\n=== 登录页面访问 ===")

    # 检查是否为本地开发环境
    is_local_dev = request.host.startswith('127.0.0.1') or request.host.startswith('localhost')
    _safe_debug_print(f"🏠 本地开发环境: {is_local_dev}")

    if is_local_dev:
        # 本地开发环境，重定向到开发者登录
        _safe_debug_print(f"🔧 重定向到开发者登录")
        return redirect(url_for('dev_login', user_type='bd'))
    else:
        # 生产环境，重定向到飞书授权
        _safe_debug_print(f"🚀 重定向到飞书授权")
        return redirect(url_for('feishu_auth'))


@app.route('/feishu/auth')
def feishu_auth():
    """飞书授权页面"""
    next_path = str(request.args.get('next') or '').strip()
    if next_path.startswith('/'):
        session['post_auth_redirect'] = next_path
    force_reauth = str(request.args.get('force') or '').strip().lower() in {'1', 'true', 'yes'}
    if force_reauth:
        session['force_feishu_reauth'] = '1'
    auth_url = get_feishu_auth_url()
    return redirect(auth_url)


@app.route('/feishu/callback', methods=['GET', 'POST'])
def feishu_callback():
    """飞书授权回调"""
    _safe_debug_print(f"\n=== 飞书授权回调处理 ===")
    _safe_debug_print(f"请求方法: {request.method}")
    _safe_debug_print(f"请求头: {dict(request.headers)}")

    # 如果是POST请求，可能是飞书的事件回调或URL验证
    if request.method == 'POST':
        _safe_debug_print(f"🔐 检测到POST请求，处理飞书回调...")

        try:
            data = request.get_json()
            data = _feishu_try_decrypt_callback_data(data)
            _safe_debug_print(f"收到飞书回调请求: {data}")
            try:
                event_type_preview = (
                    (data or {}).get("event", {}).get("type")
                    or (data or {}).get("header", {}).get("event_type")
                    or (data or {}).get("type")
                )
                _feishu_recent_events.append({
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "stage": "callback_received",
                    "type": event_type_preview,
                    "has_encrypt": bool((request.get_json(silent=True) or {}).get("encrypt")),
                    "schema": (data or {}).get("schema"),
                })
                if len(_feishu_recent_events) > _feishu_recent_events_limit:
                    del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
            except Exception:
                pass

            # 处理 URL 校验
            if data and data.get('type') == 'url_verification':
                challenge = data.get('challenge')
                _safe_debug_print(f"URL验证请求，返回challenge: {challenge}")
                return jsonify({"challenge": challenge})

            # 校验 token（可选）
            token = data.get('token')
            if token and token != FEISHU_CONFIG.get('verification_token'):
                _safe_debug_print(f"Token验证失败: 期望 {FEISHU_CONFIG.get('verification_token')}, 收到 {token}")
                return jsonify({"msg": "verification token mismatch"}), 403

            # 处理事件
            event = data.get('event', {})
            _safe_debug_print(f"收到事件: {event}")

            event_type = (event or {}).get('type') or (data or {}).get('header', {}).get('event_type') or (data or {}).get('type')
            if event_type in ('im.message.receive_v1', 'message_receive_v1'):
                return handle_feishu_message_event(data)
            if event_type in ('card.action.trigger', 'im.message.action_v1', 'message_action_v1'):
                return _xiaotu_handle_report_card_action(data)

            try:
                if _event_mentions_bot(event):
                    payload_text = _extract_all_text(event, max_chars=12000)
                    event_doc_url = _feishu_extract_cloud_doc_url_from_event(event)
                    maybe_doc = bool(_feishu_find_cloud_doc_url_any(payload_text) or event_doc_url) or bool(re.search(r"(doxcn[a-zA-Z0-9]+|doccn[a-zA-Z0-9]+)", payload_text))
                    if maybe_doc:
                        return _handle_feishu_cloud_doc_mention_event(data)
            except Exception:
                pass

            return handle_feishu_event(data)

        except Exception as e:
            _safe_debug_print(f"❌ 处理POST回调异常: {e}")
            import traceback
            _safe_debug_print(f"🔍 错误详情: {traceback.format_exc()}")
            return jsonify({'error': '处理回调失败'}), 500

    # GET请求处理授权回调
    code = request.args.get('code')
    state = request.args.get('state')

    _safe_debug_print(f"📝 授权码: {code}")
    _safe_debug_print(f"🔐 状态码: {state}")

    # 如果没有授权码，可能是直接访问回调地址，返回友好提示
    if not code:
        _safe_debug_print(f"❌ 未获取到授权码")
        _safe_debug_print("========================\n")
        return jsonify({
            'error': '此接口用于飞书回调，请通过飞书授权流程访问',
            'message': '如需测试，请访问 /test/challenge 页面',
            'status': 'callback_endpoint'
        }), 200  # 改为200状态码，避免飞书认为接口异常

    if not str(state or '').startswith('tuchuang_ai_system'):
        _safe_debug_print(f"❌ 状态验证失败: {state}")
        _safe_debug_print("========================\n")
        return jsonify({'error': '授权失败，状态验证失败'}), 400

    try:
        _safe_debug_print(f"🔄 使用授权码获取用户信息...")
        # 通过授权码获取用户信息
        user_info = permission_manager.get_user_info_by_code(code)

        if not user_info:
            _safe_debug_print(f"❌ 获取用户信息失败")
            _safe_debug_print("========================\n")
            return jsonify({'error': '获取用户信息失败'}), 500

        _safe_debug_print(f"✅ 成功获取用户信息: {user_info}")

        # 统一绑定为当前应用下的用户身份
        _clear_feishu_identity_session()
        _bind_feishu_session(user_info, str(user_info.get('user_access_token') or ''))

        _safe_debug_print(f"✅ 用户授权成功: {user_info.get('name')} ({user_info.get('user_id')})")
        _safe_debug_print(f"📝 用户信息已保存到Session")
        session.pop('force_feishu_reauth', None)

        # 后台预加载用户部门信息和权限数据
        user_id = user_info.get('open_id') or user_info.get('user_id')
        _safe_debug_print(f"🚀 开始后台预加载用户数据: {user_id}")
        try:
            # 预加载部门信息（这会触发缓存）
            departments = permission_manager.get_user_departments(user_id)
            _safe_debug_print(f"✅ 预加载部门信息完成，部门数量: {len(departments)}")

            # 预加载权限信息（这会触发缓存）
            accessible_functions = permission_manager.get_user_accessible_functions(user_id)
            _safe_debug_print(f"✅ 预加载权限信息完成，可访问功能数量: {len(accessible_functions)}")

            # 将预加载的数据存储到session中，进一步提升响应速度
            session.pop('preloaded_departments', None)
            session.pop('preloaded_functions', None)
            session.pop('preload_time', None)

            _safe_debug_print(f"🎯 后台预加载完成，Dashboard访问将实现秒开")
        except Exception as e:
            _safe_debug_print(f"⚠️ 后台预加载失败: {e}，但不影响正常登录")

        to_path = str(session.pop('post_auth_redirect', '') or '').strip()
        if not to_path.startswith('/'):
            to_path = url_for('dashboard')
        _safe_debug_print(f"🔄 重定向到: {to_path}")
        _safe_debug_print("========================\n")
        return redirect(to_path)

    except Exception as e:
        _safe_debug_print(f"❌ 处理飞书授权回调异常: {e}")
        import traceback
        _safe_debug_print(f"🔍 错误详情: {traceback.format_exc()}")
        _safe_debug_print("========================\n")
        return jsonify({'error': f'授权处理失败: {str(e)}'}), 500


@app.route('/api/user/permissions')
def get_user_permissions():
    """获取当前用户权限API"""
    user_id = session.get('feishu_user_id')

    if not user_id:
        return jsonify({
            'success': False,
            'message': '用户未登录',
            'auth_url': get_feishu_auth_url()
        })

    try:
        accessible_functions = permission_manager.get_user_accessible_functions(user_id)
        user_departments = permission_manager.get_user_departments(user_id)

        return jsonify({
            'success': True,
            'data': {
                'user_id': user_id,
                'user_name': session.get('feishu_user_name'),
                'departments': [dept.get('name', '') for dept in user_departments],
                'accessible_functions': accessible_functions,
                'is_developer': permission_manager.is_developer(user_id)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取用户权限失败: {str(e)}'
        })


@app.route('/api/cache/stats')
def get_cache_stats():
    """获取缓存统计信息API"""
    try:
        cache_stats = permission_manager.get_cache_stats()
        preload_info = {
            'has_preloaded_data': bool(session.get('preloaded_functions')),
            'preload_time': session.get('preload_time'),
            'preloaded_functions_count': len(session.get('preloaded_functions', [])),
            'preloaded_departments_count': len(session.get('preloaded_departments', []))
        }

        return jsonify({
            'success': True,
            'data': {
                'cache_stats': cache_stats,
                'preload_info': preload_info,
                'session_info': {
                    'user_id': session.get('feishu_user_id'),
                    'user_name': session.get('feishu_user_name'),
                    'login_time': session.get('login_time')
                }
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取缓存统计失败: {str(e)}'
        })


@app.route('/api/cache/clear')
def clear_cache():
    """清空缓存API"""
    try:
        permission_manager.clear_cache()
        # 同时清空session中的预加载数据
        session.pop('preloaded_functions', None)
        session.pop('preloaded_departments', None)
        session.pop('preload_time', None)

        return jsonify({
            'success': True,
            'message': '缓存已清空'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'清空缓存失败: {str(e)}'
        })


@app.route('/permission_management')
@require_permission('admin_functions')
def permission_management():
    return render_template('permission_management.html')


@app.route('/api/admin/search_user', methods=['POST'])
@require_permission('admin_functions')
def search_user():
    """搜索用户API"""
    try:
        data = request.get_json()
        search_value = data.get('search_value', '').strip()

        if not search_value:
            return jsonify({
                'success': False,
                'message': '请输入搜索内容'
            })

        # 获取用户信息和权限
        user_info = permission_manager.search_user_by_id_or_email(search_value)

        if not user_info:
            return jsonify({
                'success': False,
                'message': '未找到该用户，请检查用户ID或邮箱是否正确'
            })

        # 获取用户的所有权限信息
        all_permissions = permission_manager.get_all_permissions_for_user(user_info['user_id'])

        return jsonify({
            'success': True,
            'data': {
                'user_id': user_info['user_id'],
                'name': user_info['name'],
                'email': user_info['email'],
                'departments': user_info['departments'],
                'permissions': all_permissions
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'搜索用户失败: {str(e)}'
        })


@app.route('/api/admin/grant_permission', methods=['POST'])
@require_permission('admin_functions')
def grant_permission():
    """授予权限API"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        function_name = data.get('function_name')

        if not user_id or not function_name:
            return jsonify({
                'success': False,
                'message': '缺少必要参数'
            })

        # 授予权限
        result = permission_manager.grant_user_permission(user_id, function_name)

        if result['success']:
            return jsonify({
                'success': True,
                'message': f'成功授予权限',
                'function_display_name': result.get('function_display_name', function_name)
            })
        else:
            return jsonify({
                'success': False,
                'message': result['message']
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'授予权限失败: {str(e)}'
        })


@app.route('/api/admin/revoke_permission', methods=['POST'])
@require_permission('admin_functions')
def revoke_permission():
    """撤销权限API"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        function_name = data.get('function_name')

        if not user_id or not function_name:
            return jsonify({
                'success': False,
                'message': '缺少必要参数'
            })

        # 撤销权限
        result = permission_manager.revoke_user_permission(user_id, function_name)

        if result['success']:
            return jsonify({
                'success': True,
                'message': f'成功撤销权限',
                'function_display_name': result.get('function_display_name', function_name)
            })
        else:
            return jsonify({
                'success': False,
                'message': result['message']
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'撤销权限失败: {str(e)}'
        })


@app.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    return redirect(url_for('dashboard'))


@app.route('/reauth')
def reauth():
    """重新授权 - 用于解决open_id cross app错误"""
    _safe_debug_print(f"\n=== 用户重新授权处理 ===")
    _safe_debug_print(f"👤 当前用户ID: {session.get('feishu_open_id', '未知')}")
    _safe_debug_print(f"👤 当前用户名: {session.get('feishu_user_name', '未知')}")
    _safe_debug_print(f"🧹 清除session和缓存...")
    
    # 清除用户缓存
    user_id = session.get('feishu_open_id')
    if user_id:
        permission_manager.clear_cache(user_id)
        _safe_debug_print(f"✅ 已清除用户 {user_id} 的缓存")
    
    # 清除session，但保留强制重授权标记
    session.clear()
    session['force_feishu_reauth'] = '1'
    _safe_debug_print(f"✅ 已清除session")
    _safe_debug_print(f"🔄 重定向到飞书授权页面...")
    _safe_debug_print("========================\n")
    
    # 重定向到飞书授权
    return redirect(url_for('feishu_auth', force='1'))


if __name__ == '__main__':
    debug_mode = str(os.environ.get("TC_FLASK_DEBUG", "")).strip().lower() in {"1", "true", "yes", "on"}
    if (not debug_mode) or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        _start_xiaotu_report_reminder_thread_once()
    app.run(debug=debug_mode, host='0.0.0.0', port=8000, use_reloader=False)
