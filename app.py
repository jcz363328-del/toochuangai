from shared_modules.reports import export_html
from shared_modules.reports.export_media import _xiaotu_history_export_image_data_uri
from shared_modules.reports.formatting import (
    _xiaotu_clip_card_text,
    _xiaotu_extract_plain_preview_text,
    _xiaotu_format_message_time,
    _xiaotu_html_to_plain_text_preserve_blocks,
    _xiaotu_normalize_compare_path,
    _xiaotu_normalize_notify_time,
    _xiaotu_sql_escape,
)
# 飞书原生视频消息接口超过约 30MB 会被拒绝。
FEISHU_NATIVE_VIDEO_MAX_BYTES = 30 * 1024 * 1024
import concurrent.futures
import time
from core.permissions.business_analysis_guard import require_business_analysis_access
from core.service_processes import start_background_process, start_powershell_service
from threading import Lock, Thread
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_from_directory, send_file, g, stream_with_context, abort
from openai import OpenAI
from datetime import datetime, timedelta, date
import os
import sys
import json
import re
import base64
import hashlib
import secrets
import mimetypes
import requests
import importlib.util
from integrations.feishu import video_messages as _feishu_video_messages
from functools import partial
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from shared_modules.reports.document_text import (
    _xiaotu_extract_doc_token,
    _xiaotu_extract_source_doc_token,
    _xiaotu_guess_title,
    _xiaotu_detect_report_kind,
    _xiaotu_is_daily_date_heading,
    _xiaotu_find_daily_date_matches,
    _xiaotu_extract_block_plain_text,
    _xiaotu_order_doc_blocks,
    _xiaotu_is_image_like_block,
    _xiaotu_build_date_search_keys,
    _xiaotu_markdownish_to_html,
    _xiaotu_compact_report_body_for_storage,
)
from shared_modules.reports.feedback_text import (
    _xiaotu_feedback_entry_line,
    _xiaotu_parse_feedback_entries,
    _xiaotu_parse_like_user_names,
    _xiaotu_build_like_user_text,
    _xiaotu_feedback_entries_to_text,
)
from Department.运营部.export_address import (
    _tk_country_to_iso2,
    _tk_split_street_city,
    _tk_extract_zip_and_country,
    _tk_extract_us_state_with_span,
    _tk_guess_city_from_tail,
    _tk_guess_city_from_street_tail,
    _tk_parse_structured_export_address,
    _tk_normalize_export_phone,
    _tk_refine_export_address_city,
    _tk_guess_city_from_export_text,
)
import integrations.feishu.callback_routes as _feishu_callback_routes
import core.permissions.admin_routes as _permission_admin_routes
import shared_modules.reports.submission as _report_submission
import shared_modules.reports.delivery as _report_delivery
import shared_modules.reports.persistence as _report_persistence
import integrations.feishu.events as _feishu_events
from core.permissions import identity_routes as _identity_routes
import integrations.feishu.bitable as _feishu_bitable
import shared_modules.reports.reminders as _report_reminders
import integrations.feishu.message_content as _feishu_message_content
import shared_modules.reports.media_ingestion as _report_media_ingestion
import Department.总经办.business_analysis_routes as _business_analysis_routes
import Department.内容生产工厂.tk_video_realtime_routes as _tk_video_realtime_routes
import shared_modules.reports.history_routes as _report_history_routes
import shared_modules.reports.im_submission_routes as _report_im_submission
import Department.内容生产工厂.tk_monthly_target_routes as _tk_monthly_target_routes
import integrations.feishu.answers as _feishu_answers
import core.dashboard_routes as _dashboard_routes
import Department.内容生产工厂.tk_invite_monitor_routes as _tk_invite_monitor_routes
import Department.内容生产工厂.tk_dashboard_routes as _tk_dashboard_routes
import Department.内容生产工厂.tk_customer_service_routes as _tk_customer_service_routes
import shared_modules.reports.report_analysis_routes as _report_analysis_routes
import integrations.feishu.session_identity as _feishu_session_identity
import shared_modules.reports.feishu_documents as _report_feishu_documents
import shared_modules.reports.delivery_routes as _report_delivery_routes
import core.workspace_routes as _workspace_routes
import shared_modules.reports.report_edit_routes as _report_edit_routes
import integrations.feishu.message_test_routes as _feishu_message_test_routes
import shared_modules.reports.editor_routes as _report_editor_routes
import integrations.feishu.version_notice_routes as _version_notice_routes
import shared_modules.reports.draft_cache as _report_draft_cache
import shared_modules.reports.export_views as _report_export_views
import shared_modules.reports.notify_directory as _report_notify_directory
import core.dashboard_access as _dashboard_access
import Department.流程与AI部.content_generation_routes as _content_generation_routes
import shared_modules.reports.comment_pages as _report_comment_pages
import integrations.feishu.message_delivery as _feishu_message_delivery
from shared_modules.reports.card_message_store import ReportCardMessageStore
import Department.视觉设计部.canvas_routes as _canvas_routes
import shared_modules.reports.docx_sections as _report_docx_sections
import shared_modules.reports.scope as _report_scope
import shared_modules.training_media as _training_media
import integrations.feishu.chat_resources as _feishu_chat_resources
import shared_modules.reports.document_pages as _report_document_pages
import Department.流程与AI部.proxy_routes as _ai_proxy_routes
import Department.流程与AI部.catalog_pages as _ai_catalog_pages
import Department.运营部.amazon_reply_routes as _amazon_reply_routes
import Department.运营部.fba_shipping_columns as _fba_shipping_columns
import shared_modules.reports.card_support as _report_card_support
import integrations.feishu.department_forwarding as _department_forwarding
import Department.人力资源与行政部.lunch_push_routes as _lunch_push_routes
import shared_modules.reports.editor_context as _report_editor_context
import shared_modules.reports.card_context as _report_card_context
import Department.运营部.department_pages as _operation_department_pages
import shared_modules.reports.notification_pages as _report_notification_pages
import Department.流程与AI部.innovation_admin_routes as _innovation_admin_routes
import shared_modules.reports.report_values as _report_values
import integrations.feishu.chat_flow as _feishu_chat_flow
import core.department_entry_pages as _department_entry_pages
import Department.内容生产工厂.entry_pages as _content_factory_entry_pages
import Department.总经办.entry_pages as _general_office_entry_pages
import Department.研发部.entry_pages as _research_entry_pages
import Department.流程与AI部.tool_entry_pages as _tool_entry_pages
import shared_modules.reports.media_safe as _report_media_safe
import core.permissions.identity_state as _identity_state
import core.portal_session_pages as _portal_session_pages
import shared_modules.reports.reminder_state as _report_reminder_state
import Department.视觉设计部.portal_links as _design_portal_links
from shared_modules.reports.card_source_parser import CardSourceParser
import shared_modules.reports.cards as _report_cards
import shared_modules.reports.feedback as _report_feedback
from secret_settings import TUCHUANGAI_STORAGE_ROOT, ai_runtime_config, env, env_int, relocate_storage_path, sql_server_config
from tools import ai_chat_complete, is_mobile_user_agent, safe_print as _safe_debug_print
from shared_modules.reports.xiaotu_report_memory import render_report_memory_context, update_report_memory_file
from html import escape as html_escape, unescape as html_unescape
from urllib.parse import urlparse, parse_qs, unquote, quote
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from Department.技术部.review_analysis import review_analysis_bp
from Department.内容生产工厂.influencer_management import influencer_management_bp
from Department.内容生产工厂.model_management import model_management_bp
from innovation.innovation_proposals import innovation_proposals_bp
from innovation.innovation_blueprint import innovation_bp
from innovation.home_snapshots import start_home_snapshot_worker
from innovation.config import APP_CONFIG as INNOVATION_APP_CONFIG
from Department.内容生产工厂.tk_total_dashboard import tk_dashboard_bp, get_joint_dashboard_allowed_shops
from Department.内容生产工厂.tk_bd_metrics import bd_metrics_bp
from department_permissions import permission_manager, require_permission, get_feishu_auth_url, FEISHU_CONFIG, \
    handle_feishu_event
from department_permissions import is_local_superadmin
from bjc import sf_db, dui_db
from innovation.message_service import MessageService
from innovation.pending_reminder import innovation_pending_reminder
from Department.内容生产工厂.tk_customer_service_reminder import tk_customer_service_tracking_reminder
from Department.人力资源与行政部.lunch_push import lunch_push
from integrations.feishu.skill_catalog import FeishuSkillCatalog
import prepress_check_service
from Department.内容生产工厂.seedance_web import seedance_web_bp
from Department.采购部.yangban_inventory import yangban_inventory_bp
from Department.内容生产工厂.tk_gmv_authorization import tk_gmv_authorization_bp
from Department.流程与AI部.listing_agent import listing_agent_bp
from Department.流程与AI部.listing_agent_v2 import listing_agent_v2_bp
from Department.流程与AI部.daily_replenishment import daily_replenishment_bp
from Department.运营部.daily_replenishment_operation import daily_replenishment_operation_bp
from Department.内容生产工厂.daily_replenishment_tiktok import daily_replenishment_tiktok_bp
from Department.流程与AI部.ai_group_performance import ai_group_performance_bp
from Department.运营部.historical_sales import historical_sales_bp
from Department.流程与AI部.developer_product_sales import developer_product_sales_bp
from Department.人力资源与行政部.value_evaluation import value_evaluation_bp
from Department.总经办.business_analysis_access import (
    BUSINESS_ANALYSIS_DEPARTMENT_LEADERS,
    force_business_analysis_query_params,
    merge_business_analysis_store_tier_snapshot,
    normalize_person_name,
    prepare_business_analysis_payload,
    resolve_business_analysis_scope,
)
from Department.总经办.business_analysis_company_market import (
    CompanyMarketError,
    get_company_market_overview,
    get_market_overview_rows,
    upsert_company_market_month,
)
from Department.总经办.business_analysis_key_tasks import KeyTaskStore, KeyTaskStoreError
from Department.总经办.business_analysis_fiscal_overview import load_fiscal_overview, validate_fiscal_year
from Department.总经办.business_analysis_store_tier_promotion import detect_promotions
from Department.总经办.business_analysis_usage import record_business_analysis_usage

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.secret_key = env("FLASK_SECRET_KEY", "change-this-secret-key")  # 用于session加密
app.config['JSON_AS_ASCII'] = False  # 支持中文JSON响应
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024
app.config.setdefault('MAX_FORM_MEMORY_SIZE', 256 * 1024 * 1024)
app.config.setdefault('MAX_FORM_PARTS', 5000)
FEISHU_NATIVE_VIDEO_MAX_BYTES = 30_000_000


@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(error):
    if request.path.startswith('/api/'):
        return jsonify({
            'success': False,
            'message': '上传内容超过服务器允许的大小，请压缩视频后重试',
        }), 413
    return error

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
_STRATEGY_TRAINING_VIDEO_DIR = relocate_storage_path(r"D:\tuchuangai\3.17-战略分解培训")
_ROCOCO_TRAINING_VIDEO_DIR = relocate_storage_path(r"D:\tuchuangai\洛可可培训")
_CHUANSHI_TRAINING_ROOT_DIR = relocate_storage_path(r"D:\tuchuangai\2026-7-9传世启动仪式")
_CHUANSHI_TRAINING_IMAGE_DIR = os.path.join(_CHUANSHI_TRAINING_ROOT_DIR, "图片")
_CHUANSHI_TRAINING_VIDEO_DIR = os.path.join(_CHUANSHI_TRAINING_ROOT_DIR, "视频")
_ANNUAL_MOMENTS_IMAGE_DIR = relocate_storage_path(r"D:\tuchuangai\2026-06-18年会图片")
_ANNUAL_MOMENTS_VIDEO_DIR = relocate_storage_path(r"D:\tuchuangai\2026-06-18年会视频")
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".heic", ".heif"}
_PUBLIC_DOWNLOAD_APR16_VIDEO = relocate_storage_path(r"D:\tuchuangai\4月16日.mp4")
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
_XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES = (
    "运营一部",
    "运营二部",
    "运营三部",
    "运营六部",
    "运营七部",
)
_xiaotu_notify_department_users_cache = {}
_xiaotu_notify_department_users_cache_ttl_seconds = 300
_xiaotu_notify_department_users_cache_lock = Lock()
_XIAOTU_REPORT_REMINDER_ENABLED = False  # temporary disabled for entry timeout debugging
_xiaotu_report_reminder_thread_started = False
_xiaotu_report_reminder_lock = Lock()
_xiaotu_report_reminder_sent_marks = {}
_xiaotu_user_open_id_cache = {}
_feishu_user_token_cache = {}
_feishu_user_token_cache_lock = Lock()
_FEISHU_USER_TOKEN_DEFAULT_TTL_SECONDS = 2 * 60 * 60
_LASHFORGE_PUBLIC_URL = (os.environ.get("LASHFORGE_PUBLIC_URL") or "http://www.toochuangai.com:8501/lashforge").strip().rstrip("/")
_LASHFORGE_HEALTH_URL = (os.environ.get("LASHFORGE_HEALTH_URL") or "http://127.0.0.1:8501/lashforge/").strip()
_LASHFORGE_AUTH_TOKEN_SALT = "lashforge-auth-v1"
_lashforge_watchdog_lock = Lock()
_lashforge_watchdog_last_attempt = 0.0
_PORTAL_ROOT = os.path.dirname(__file__)
_BUSINESS_ANALYSIS_SOURCE_ROOT = (
    _PORTAL_ROOT if env("TC_CONTAINER_MODE") == "1"
    else os.path.join(_PORTAL_ROOT, "Department", "总经办")
)
_ADS_MONITOR_SOURCE_ROOT = (
    _PORTAL_ROOT if env("TC_CONTAINER_MODE") == "1"
    else os.path.join(_PORTAL_ROOT, "Department", "流程与AI部")
)
_BUSINESS_ANALYSIS_ROOT = os.path.join(_BUSINESS_ANALYSIS_SOURCE_ROOT, "business_analysis")
_BUSINESS_ANALYSIS_DATA_ROOT = os.path.join(os.path.dirname(__file__), "business_analysis", "data")
_BUSINESS_ANALYSIS_DIST_DIR = os.path.join(_BUSINESS_ANALYSIS_ROOT, "dist-flask")
_BUSINESS_ANALYSIS_SNAPSHOT_PATH = os.path.join(
    _BUSINESS_ANALYSIS_ROOT,
    "app",
    "data",
    "workbook-data.json",
)
_BUSINESS_ANALYSIS_TIER_SNAPSHOT_PATH = os.path.join(
    _BUSINESS_ANALYSIS_ROOT,
    "app",
    "data",
    "store-tiers.json",
)
_BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH = os.path.join(
    _BUSINESS_ANALYSIS_DATA_ROOT,
    "dashboard-snapshot.json",
)
_BUSINESS_ANALYSIS_TIER_HISTORY_SNAPSHOT_PATH = os.path.join(
    _BUSINESS_ANALYSIS_DATA_ROOT,
    "store-tier-history-snapshot.json",
)
_business_analysis_tier_history_cache = {
    'mtime_ns': None,
    'snapshot': None,
    'promotion_events': None,
}
_business_analysis_tier_history_cache_lock = Lock()
_dashboard_store_tier_cache = {
    'mtime_ns': None,
    'data_date': '',
    'by_operator': {},
}
_dashboard_store_tier_cache_lock = Lock()
_BUSINESS_ANALYSIS_API_PORT = env_int("SALES_API_PORT", 4311)
_BUSINESS_ANALYSIS_HEALTH_URL = f"http://127.0.0.1:{_BUSINESS_ANALYSIS_API_PORT}/api/health"
_business_analysis_start_lock = Lock()
_business_analysis_last_start_attempt = 0.0
_business_analysis_key_task_store = KeyTaskStore(
    os.environ.get("SALES_KEY_TASKS_FILE")
    or os.path.join(_BUSINESS_ANALYSIS_DATA_ROOT, "key-tasks.json")
)
_ADS_MONITOR_ROOT = os.path.join(
    _ADS_MONITOR_SOURCE_ROOT,
    "ads_monitor_web",
    "ads-monitor-web-full-source",
)
_ADS_MONITOR_WEB_ROOT = os.path.join(_ADS_MONITOR_ROOT, "ads-monitor-web")
_ADS_MONITOR_DIST_DIR = os.path.join(_ADS_MONITOR_WEB_ROOT, "dist-flask")
_ADS_MONITOR_PYTHON_DEPS_DIR = os.path.join(_ADS_MONITOR_ROOT, ".python_deps")
_ADS_MONITOR_API_PORT = 4174
_ADS_MONITOR_HEALTH_URL = f"http://127.0.0.1:{_ADS_MONITOR_API_PORT}/api/diagnostic/health"
_ads_monitor_start_lock = Lock()
_ads_monitor_last_start_attempt = 0.0
_VIDEOCLAW_URL = os.environ.get('VIDEOCLAW_URL', '').strip()
_VIDEOCLAW_ROOT = os.path.join(os.path.dirname(__file__), 'Department', '流程与AI部', 'VideoClaw', 'video-claw', 'video-claw')
_VIDEOCLAW_FRONTEND_ROOT = os.path.join(_VIDEOCLAW_ROOT, 'frontend')
_VIDEOCLAW_BACKEND_ROOT = os.path.join(_VIDEOCLAW_ROOT, 'backend')
_VIDEOCLAW_FRONTEND_PORT = env_int('VIDEOCLAW_FRONTEND_PORT', 3000)
_VIDEOCLAW_BACKEND_PORT = env_int('VIDEOCLAW_BACKEND_PORT', 18000)
_VIDEOCLAW_FRONTEND_URL = f'http://127.0.0.1:{_VIDEOCLAW_FRONTEND_PORT}'
_VIDEOCLAW_BACKEND_URL = f'http://127.0.0.1:{_VIDEOCLAW_BACKEND_PORT}'
_videoclaw_start_lock = Lock()
_videoclaw_last_start_attempt = 0.0
_INFINITE_CANVAS_OMNIAKEY_MODEL = "gemini-nano-banana-2.1"
_INFINITE_CANVAS_OMNIAKEY_IMAGE_MODELS = (
    "gemini-nano-banana-2.1",
    "gpt-image-2.6-flare",
    "gpt-image-2.5-flare",
    "gpt-image-2",
    "grok-imagine-image-quality",
)
_INFINITE_CANVAS_OPENROUTER_IMAGE_MODELS = (
    "bytedance-seed/seedream-4.5",
)
_INFINITE_CANVAS_LEGACY_IMAGE_MODELS = (
    "openai/gpt-5.4-image-2",
    "openai/gpt-5-image-mini",
    "openai/gpt-5-image",
    "x-ai/grok-imagine-image-quality",
    "recraft/recraft-v4.1-utility-pro",
    "bytedance-seed/seedream-4.5",
)
_INFINITE_CANVAS_OPENROUTER_TEXT_MODELS = (
    "google/gemini-2.5-flash",
)


def _get_cloud_documents_agent():
    global _cloud_documents_agent
    if _cloud_documents_agent is not None:
        return _cloud_documents_agent
    file_path = os.path.join(os.path.dirname(__file__), "cloud_documents.py")
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
    return _portal_session_pages._is_mobile_request(is_mobile_user_agent=is_mobile_user_agent, request=request)


def _is_feishu_request():
    return _portal_session_pages._is_feishu_request(request=request)


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
    return _report_reminder_state._xiaotu_remember_user_open_id(
        user_name,
        open_id,
        _xiaotu_user_open_id_cache=_xiaotu_user_open_id_cache,
        re=re,
    )


def _xiaotu_get_cached_open_id_by_name(user_name):
    return _report_reminder_state._xiaotu_get_cached_open_id_by_name(
        user_name,
        _xiaotu_user_open_id_cache=_xiaotu_user_open_id_cache,
        re=re,
    )


def _current_user_has_permission(function_name, user_id=None):
    uid = str(user_id or session.get('feishu_user_id') or '').strip()
    if not uid:
        return False
    try:
        return bool(permission_manager.check_user_permission(uid, function_name)[0])
    except Exception as exc:
        _safe_debug_print(f"权限表校验失败: {function_name} -> {exc}")
        return False


def _can_access_ai_workspace():
    return _dashboard_access._can_access_ai_workspace(
        app=app,
        g=g,
        is_local_superadmin=is_local_superadmin,
        permission_manager=permission_manager,
        session=session,
    )


def _xiaotu_report_history_can_view_all_uploads(user_name=None):
    return _report_values._xiaotu_report_history_can_view_all_uploads(user_name, _current_user_has_permission=_current_user_has_permission)


def _xiaotu_get_report_history_scope(user_name, debug_mode=None):
    return _report_scope._xiaotu_get_report_history_scope(
        user_name,
        debug_mode,
        _XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES=_XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES,
        _current_user_has_permission=_current_user_has_permission,
        _xiaotu_report_history_can_view_all_uploads=_xiaotu_report_history_can_view_all_uploads,
    )


def _xiaotu_get_report_history_debug_options(user_name):
    return _report_values._xiaotu_get_report_history_debug_options(user_name, _current_user_has_permission=_current_user_has_permission)


def _xiaotu_build_name_match_clause(column_name, names):
    return _report_scope._xiaotu_build_name_match_clause(
        column_name,
        names,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        re=re,
    )


def _xiaotu_build_name_scope_clause(column_name, names):
    return _report_editor_context._xiaotu_build_name_scope_clause(
        column_name,
        names,
        _xiaotu_build_name_match_clause=_xiaotu_build_name_match_clause,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        re=re,
    )


def _xiaotu_collect_notify_user_names_by_department_names(department_names):
    return _report_scope._xiaotu_collect_notify_user_names_by_department_names(
        department_names,
        _xiaotu_list_notify_departments=_xiaotu_list_notify_departments,
        _xiaotu_list_notify_users_current_app_cached=_xiaotu_list_notify_users_current_app_cached,
    )


def _get_func_field(func, key):
    if isinstance(func, dict):
        return func.get(key)
    return getattr(func, key, None)


def _build_mobile_function_cards(accessible_functions):
    return _workspace_routes._build_mobile_function_cards(
        accessible_functions,
        _can_access_ai_workspace=_can_access_ai_workspace,
        _current_user_has_permission=_current_user_has_permission,
        _get_func_field=_get_func_field,
        url_for=url_for,
    )


def _build_lashforge_auth_token(user_name):
    return _design_portal_links._build_lashforge_auth_token(
        user_name,
        _LASHFORGE_AUTH_TOKEN_SALT=_LASHFORGE_AUTH_TOKEN_SALT,
        hashlib=hashlib,
    )


def _get_lashforge_public_base_url():
    return _design_portal_links._get_lashforge_public_base_url(
        _LASHFORGE_PUBLIC_URL=_LASHFORGE_PUBLIC_URL,
        env=env,
        os=os,
        request=request,
        urlparse=urlparse,
    )


def _build_lashforge_entry_url(user_name=''):
    return _design_portal_links._build_lashforge_entry_url(
        user_name,
        _build_lashforge_auth_token=_build_lashforge_auth_token,
        _get_lashforge_public_base_url=_get_lashforge_public_base_url,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        quote=quote,
    )


def _is_lashforge_reachable(timeout=1.5):
    try:
        response = requests.get(_LASHFORGE_HEALTH_URL, timeout=timeout)
        return 200 <= response.status_code < 400
    except Exception:
        return False


def _ensure_lashforge_watchdog_started():
    global _lashforge_watchdog_last_attempt
    if env("TC_CONTAINER_MODE") == "1":
        return _is_lashforge_reachable()
    if _is_lashforge_reachable():
        return True

    with _lashforge_watchdog_lock:
        now = time.time()
        if now - _lashforge_watchdog_last_attempt < 30:
            return False
        _lashforge_watchdog_last_attempt = now

        script_dir = os.path.join(os.path.dirname(__file__), "Department", "视觉设计部", "xiaoha")
        script_path = os.path.join(script_dir, "xiaoha_watchdog.ps1")
        if not os.path.exists(script_path):
            app.logger.warning("XiaoHa watchdog script not found: %s", script_path)
            return False

        try:
            start_powershell_service(script_path, cwd=script_dir)
            return True
        except Exception as exc:
            app.logger.warning("Failed to start XiaoHa watchdog: %s", exc)
            return False


def _is_business_analysis_api_reachable(timeout=2.0):
    try:
        response = requests.get(_BUSINESS_ANALYSIS_HEALTH_URL, timeout=timeout)
        return 200 <= response.status_code < 400
    except Exception:
        return False


def _ensure_business_analysis_api_started():
    """Start the localhost-only dashboard API when the AI page first needs it."""
    global _business_analysis_last_start_attempt
    if env("TC_CONTAINER_MODE") == "1":
        return _is_business_analysis_api_reachable(timeout=0.8)
    if _is_business_analysis_api_reachable(timeout=0.8):
        return True

    with _business_analysis_start_lock:
        now = time.time()
        if now - _business_analysis_last_start_attempt < 30:
            return False
        _business_analysis_last_start_attempt = now

        script_path = os.path.join(_BUSINESS_ANALYSIS_ROOT, "scripts", "start-api.ps1")
        if not os.path.exists(script_path):
            app.logger.warning("Business analysis API launcher not found: %s", script_path)
            return False

        try:
            start_powershell_service(
                script_path,
                cwd=_BUSINESS_ANALYSIS_ROOT,
                script_args=('-ApiPort', str(_BUSINESS_ANALYSIS_API_PORT)),
            )
            return True
        except Exception as exc:
            app.logger.warning("Failed to start business analysis API: %s", exc)
            return False


def _is_ads_monitor_api_reachable(timeout=2.0):
    try:
        response = requests.get(_ADS_MONITOR_HEALTH_URL, timeout=timeout)
        return 200 <= response.status_code < 400
    except requests.RequestException:
        return False


def _ensure_ads_monitor_api_started():
    if env("TC_CONTAINER_MODE") == "1":
        return _is_ads_monitor_api_reachable(timeout=0.8)
    """Start the localhost-only Sellfox diagnostic API on first use."""
    global _ads_monitor_last_start_attempt
    if _is_ads_monitor_api_reachable(timeout=0.8):
        return True

    with _ads_monitor_start_lock:
        now = time.time()
        if now - _ads_monitor_last_start_attempt < 30:
            return False
        _ads_monitor_last_start_attempt = now

        script_path = os.path.join(_ADS_MONITOR_ROOT, "sellfox_ad_diagnostic_server.py")
        if not os.path.isfile(script_path):
            app.logger.warning("Ads monitor API entry not found: %s", script_path)
            return False

        child_env = os.environ.copy()
        if os.path.isdir(_ADS_MONITOR_PYTHON_DEPS_DIR):
            existing_python_path = str(child_env.get("PYTHONPATH") or "").strip()
            child_env["PYTHONPATH"] = os.pathsep.join(
                part
                for part in (_ADS_MONITOR_PYTHON_DEPS_DIR, existing_python_path)
                if part
            )

        try:
            start_background_process([sys.executable, script_path], cwd=_ADS_MONITOR_ROOT, env=child_env)
            return True
        except Exception as exc:
            app.logger.warning("Failed to start ads monitor API: %s", exc)
            return False


def _is_videoclaw_frontend_reachable(timeout=1.0):
    try:
        response = requests.get(_VIDEOCLAW_FRONTEND_URL, timeout=timeout)
        return 200 <= response.status_code < 500
    except requests.RequestException:
        return False


def _ensure_videoclaw_started():
    """Start VideoClaw's local API and Next frontend on first AI-page visit."""
    global _videoclaw_last_start_attempt
    if env("TC_CONTAINER_MODE") == "1":
        return _is_videoclaw_frontend_reachable(timeout=0.4)
    if _is_videoclaw_frontend_reachable(timeout=0.4):
        return True
    with _videoclaw_start_lock:
        now = time.time()
        if now - _videoclaw_last_start_attempt < 30:
            return False
        _videoclaw_last_start_attempt = now
        if not os.path.isdir(_VIDEOCLAW_FRONTEND_ROOT):
            app.logger.warning('VideoClaw frontend not found: %s', _VIDEOCLAW_FRONTEND_ROOT)
            return False
        try:
            child_env = os.environ.copy()
            ffmpeg_dir = os.path.join(os.path.dirname(__file__), 'Department', '流程与AI部', 'VideoClaw', 'ffmpeg')
            if os.path.isdir(ffmpeg_dir):
                child_env['PATH'] = ffmpeg_dir + os.pathsep + child_env.get('PATH', '')
            # The backend is intentionally localhost-only; Flask remains the auth boundary.
            backend_python = os.path.join(_VIDEOCLAW_BACKEND_ROOT, 'venv', 'Scripts', 'python.exe')
            if os.name != 'nt' or not os.path.isfile(backend_python):
                backend_python = sys.executable
            backend_env = dict(child_env)
            backend_env['VIDEOCLAW_BACKEND_PORT'] = str(_VIDEOCLAW_BACKEND_PORT)
            config_path = os.path.join(_VIDEOCLAW_BACKEND_ROOT, 'config.yaml')
            if os.path.isfile(config_path):
                start_background_process([backend_python, 'api_server.py'], cwd=_VIDEOCLAW_BACKEND_ROOT, env=backend_env)
            start_background_process(['npm.cmd' if os.name == 'nt' else 'npm', 'start'], cwd=_VIDEOCLAW_FRONTEND_ROOT, env=child_env)
            return True
        except Exception as exc:
            app.logger.warning('Failed to start VideoClaw: %s', exc)
            return False


def _get_business_analysis_scope(resolve_leader=False):
    return _dashboard_access._get_business_analysis_scope(
        resolve_leader,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        _permission_debug_effective_state=_permission_debug_effective_state,
        _permission_debug_identity_cache_key=_permission_debug_identity_cache_key,
        _xiaotu_get_department_leader_user_id=_xiaotu_get_department_leader_user_id,
        g=g,
        permission_manager=permission_manager,
        resolve_business_analysis_scope=resolve_business_analysis_scope,
        session=session,
        time=time,
    )


def _require_business_analysis_access(view):
    return require_business_analysis_access(
        view,
        identity_cache_key=lambda: _permission_debug_identity_cache_key(),
        check_user_permission=lambda user_id, permission: permission_manager.check_user_permission(
            user_id, permission,
        ),
    )


def _normalize_dashboard_functions(accessible_functions):
    return _dashboard_access._normalize_dashboard_functions(accessible_functions)


def _normalize_feishu_user_name(raw_name, fallback='用户'):
    return _portal_session_pages._normalize_feishu_user_name(
        raw_name,
        fallback,
        re=re,
    )


def _xiaotu_is_invalid_feishu_name(raw_name):
    return _portal_session_pages._xiaotu_is_invalid_feishu_name(raw_name, re=re)


def _resolve_feishu_user_name(user_info, fallback='用户'):
    return _feishu_session_identity._resolve_feishu_user_name(
        user_info,
        fallback,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
    )


def _clear_feishu_user_access_token():
    return _feishu_session_identity._clear_feishu_user_access_token(
        _feishu_user_token_cache=_feishu_user_token_cache,
        _feishu_user_token_cache_lock=_feishu_user_token_cache_lock,
        session=session,
    )


def _set_feishu_user_access_token(token, expires_in=0):
    return _feishu_session_identity._set_feishu_user_access_token(
        token,
        expires_in,
        _FEISHU_USER_TOKEN_DEFAULT_TTL_SECONDS=_FEISHU_USER_TOKEN_DEFAULT_TTL_SECONDS,
        _clear_feishu_user_access_token=_clear_feishu_user_access_token,
        _feishu_user_token_cache=_feishu_user_token_cache,
        _feishu_user_token_cache_lock=_feishu_user_token_cache_lock,
        secrets=secrets,
        session=session,
        time=time,
    )


def _get_feishu_user_access_token():
    return _feishu_session_identity._get_feishu_user_access_token(
        _feishu_user_token_cache=_feishu_user_token_cache,
        _feishu_user_token_cache_lock=_feishu_user_token_cache_lock,
        _set_feishu_user_access_token=_set_feishu_user_access_token,
        session=session,
        time=time,
    )


def _clear_feishu_identity_session():
    return _feishu_session_identity._clear_feishu_identity_session(_clear_feishu_user_access_token=_clear_feishu_user_access_token, session=session)


def _bind_feishu_session(user_info, user_access_token=''):
    return _feishu_session_identity._bind_feishu_session(
        user_info,
        user_access_token,
        FEISHU_CONFIG=FEISHU_CONFIG,
        _resolve_feishu_user_name=_resolve_feishu_user_name,
        _set_feishu_user_access_token=_set_feishu_user_access_token,
        _xiaotu_remember_user_open_id=_xiaotu_remember_user_open_id,
        app=app,
        datetime=datetime,
        permission_manager=permission_manager,
        session=session,
        timedelta=timedelta,
    )


def _sync_feishu_identity_via_current_app(force_refresh=False):
    return _feishu_session_identity._sync_feishu_identity_via_current_app(
        force_refresh,
        FEISHU_CONFIG=FEISHU_CONFIG,
        _bind_feishu_session=_bind_feishu_session,
        _clear_feishu_identity_session=_clear_feishu_identity_session,
        _debug_log_elapsed=_debug_log_elapsed,
        _get_feishu_user_access_token=_get_feishu_user_access_token,
        _safe_debug_print=_safe_debug_print,
        permission_manager=permission_manager,
        request=request,
        session=session,
        time=time,
    )


def _handle_feishu_identity_mismatch(is_api_request=False):
    return _feishu_session_identity._handle_feishu_identity_mismatch(
        is_api_request,
        jsonify=jsonify,
        redirect=redirect,
        request=request,
        session=session,
        url_for=url_for,
    )


def _xiaotu_get_user_departments(user_id):
    return _report_editor_context._xiaotu_get_user_departments(user_id, permission_manager=permission_manager)


def _xiaotu_match_doc_permission(doc_item, user_depts):
    return _report_values._xiaotu_match_doc_permission(doc_item, user_depts)


def _xiaotu_get_user_saved_docs(user_id):
    return _report_feishu_documents._xiaotu_get_user_saved_docs(user_id, session=session)


def _xiaotu_list_feishu_docs_for_user(user_id, force_refresh=False, user_access_token=''):
    return _report_feishu_documents._xiaotu_list_feishu_docs_for_user(
        user_id,
        force_refresh,
        user_access_token,
        _feishu_build_cloud_doc_url=_feishu_build_cloud_doc_url,
        _feishu_http=_feishu_http,
        _xiaotu_doc_list_cache=_xiaotu_doc_list_cache,
        _xiaotu_doc_list_cache_lock=_xiaotu_doc_list_cache_lock,
        _xiaotu_doc_list_cache_ttl_seconds=_xiaotu_doc_list_cache_ttl_seconds,
        _xiaotu_extract_doc_token=_xiaotu_extract_doc_token,
        datetime=datetime,
    )


def _xiaotu_need_reauth(err_text):
    return _report_editor_context._xiaotu_need_reauth(err_text)


def _xiaotu_set_user_saved_docs(user_id, rows):
    return _report_feishu_documents._xiaotu_set_user_saved_docs(
        user_id,
        rows,
        session=session,
    )




def _xiaotu_build_report_instance_id(doc_token=''):
    return _report_values._xiaotu_build_report_instance_id(doc_token, datetime=datetime)






def _xiaotu_lookup_org_perf_context(user_name):
    return _report_document_pages._xiaotu_lookup_org_perf_context(
        user_name,
        _safe_debug_print=_safe_debug_print,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        re=re,
        sf_db=sf_db,
    )


def _xiaotu_generate_org_perf_contribution(user_name, report_kind, report_material, org_perf_context, chat_id=""):
    return _report_submission._xiaotu_generate_org_perf_contribution(
        user_name,
        report_kind,
        report_material,
        org_perf_context,
        chat_id,
        _generate_ai_answer_with_doc=_generate_ai_answer_with_doc,
        _safe_debug_print=_safe_debug_print,
    )



def _xiaotu_read_report_memory_context(user_name):
    return _report_persistence._xiaotu_read_report_memory_context(
        user_name,
        TUCHUANGAI_STORAGE_ROOT=TUCHUANGAI_STORAGE_ROOT,
        render_report_memory_context=render_report_memory_context,
    )


def _xiaotu_generate_report_memory_json(prompt_text, doc_text, doc_name="", chat_id=None):
    return _report_submission._xiaotu_generate_report_memory_json(
        prompt_text,
        doc_text,
        doc_name,
        chat_id,
        _OPENAI_TEXT_MODEL_CANDIDATES=_OPENAI_TEXT_MODEL_CANDIDATES,
        _ai_chat_complete=_ai_chat_complete,
    )



def _xiaotu_upsert_report_memory_path(user_name, file_path):
    return _report_persistence._xiaotu_upsert_report_memory_path(
        user_name,
        file_path,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        dui_db=dui_db,
    )


def _xiaotu_update_report_memory(
    user_name,
    user_open_id,
    report_id,
    report_date,
    report_material,
    is_edit=False,
):
    return _report_persistence._xiaotu_update_report_memory(
        user_name,
        user_open_id,
        report_id,
        report_date,
        report_material,
        is_edit,
        TUCHUANGAI_STORAGE_ROOT=TUCHUANGAI_STORAGE_ROOT,
        _xiaotu_generate_report_memory_json=_xiaotu_generate_report_memory_json,
        _xiaotu_upsert_report_memory_path=_xiaotu_upsert_report_memory_path,
        update_report_memory_file=update_report_memory_file,
    )




def _xiaotu_build_report_title(user_name, report_kind, date_text=None):
    return _report_values._xiaotu_build_report_title(
        user_name,
        report_kind,
        date_text,
        datetime=datetime,
    )




def _xiaotu_report_kind_from_type(report_type):
    return _report_values._xiaotu_report_kind_from_type(report_type)


def _xiaotu_report_type_from_kind(report_kind):
    return _report_values._xiaotu_report_type_from_kind(report_kind)






def _xiaotu_find_last_daily_date_start(text):
    return _report_editor_context._xiaotu_find_last_daily_date_start(
        text,
        _xiaotu_find_daily_date_matches=_xiaotu_find_daily_date_matches,
        _xiaotu_is_daily_date_heading=_xiaotu_is_daily_date_heading,
    )


def _xiaotu_build_today_daily_search_keys(now_dt=None):
    return _report_values._xiaotu_build_today_daily_search_keys(
        now_dt,
        _xiaotu_build_date_search_keys=_xiaotu_build_date_search_keys,
        datetime=datetime,
    )


def _xiaotu_find_preferred_daily_date_start(text, now_dt=None):
    return _report_docx_sections._xiaotu_find_preferred_daily_date_start(
        text,
        now_dt,
        _xiaotu_build_date_search_keys=_xiaotu_build_date_search_keys,
        _xiaotu_build_today_daily_search_keys=_xiaotu_build_today_daily_search_keys,
        _xiaotu_find_daily_date_matches=_xiaotu_find_daily_date_matches,
        _xiaotu_is_daily_date_heading=_xiaotu_is_daily_date_heading,
    )


def _xiaotu_count_daily_date_headings(text):
    return _report_values._xiaotu_count_daily_date_headings(
        text,
        _xiaotu_find_daily_date_matches=_xiaotu_find_daily_date_matches,
        _xiaotu_is_daily_date_heading=_xiaotu_is_daily_date_heading,
    )




def _xiaotu_extract_image_tokens_from_block(block_obj):
    return _report_docx_sections._xiaotu_extract_image_tokens_from_block(
        block_obj,
        _xiaotu_extract_feishu_file_token_from_fragment=_xiaotu_extract_feishu_file_token_from_fragment,
        json=json,
        re=re,
    )






def _xiaotu_build_block_debug_sample(block_obj):
    return _report_editor_context._xiaotu_build_block_debug_sample(
        block_obj,
        _xiaotu_extract_block_plain_text=_xiaotu_extract_block_plain_text,
        _xiaotu_extract_image_tokens_from_block=_xiaotu_extract_image_tokens_from_block,
        _xiaotu_is_image_like_block=_xiaotu_is_image_like_block,
    )




def _xiaotu_find_last_daily_block_index(blocks, matched_line=''):
    return _report_docx_sections._xiaotu_find_last_daily_block_index(
        blocks,
        matched_line,
        _xiaotu_build_date_search_keys=_xiaotu_build_date_search_keys,
        _xiaotu_extract_block_plain_text=_xiaotu_extract_block_plain_text,
        _xiaotu_is_daily_date_heading=_xiaotu_is_daily_date_heading,
        json=json,
        re=re,
    )


def _xiaotu_find_preferred_daily_block_index(blocks, matched_line='', now_dt=None):
    return _report_docx_sections._xiaotu_find_preferred_daily_block_index(
        blocks,
        matched_line,
        now_dt,
        _xiaotu_build_date_search_keys=_xiaotu_build_date_search_keys,
        _xiaotu_build_today_daily_search_keys=_xiaotu_build_today_daily_search_keys,
        _xiaotu_extract_block_plain_text=_xiaotu_extract_block_plain_text,
        _xiaotu_is_daily_date_heading=_xiaotu_is_daily_date_heading,
        json=json,
        re=re,
    )


def _xiaotu_fetch_docx_blocks(agent, doc_token):
    return _report_docx_sections._xiaotu_fetch_docx_blocks(
        agent,
        doc_token,
        _feishu_http=_feishu_http,
        permission_manager=permission_manager,
    )


def _xiaotu_slice_daily_doc_content(agent, doc_url, doc_text):
    return _report_analysis_routes._xiaotu_slice_daily_doc_content(
        agent,
        doc_url,
        doc_text,
        _xiaotu_build_block_debug_sample=_xiaotu_build_block_debug_sample,
        _xiaotu_extract_block_plain_text=_xiaotu_extract_block_plain_text,
        _xiaotu_extract_image_tokens_from_block=_xiaotu_extract_image_tokens_from_block,
        _xiaotu_fetch_docx_blocks=_xiaotu_fetch_docx_blocks,
        _xiaotu_find_preferred_daily_block_index=_xiaotu_find_preferred_daily_block_index,
        _xiaotu_find_preferred_daily_date_start=_xiaotu_find_preferred_daily_date_start,
        _xiaotu_is_image_like_block=_xiaotu_is_image_like_block,
        _xiaotu_order_doc_blocks=_xiaotu_order_doc_blocks,
    )


def _xiaotu_person_type_from_value(value):
    return _report_values._xiaotu_person_type_from_value(value)


def _xiaotu_person_type_to_value(value):
    return _report_values._xiaotu_person_type_to_value(value)


def _xiaotu_person_focus_text(person_type):
    return _report_document_pages._xiaotu_person_focus_text(person_type)


def _xiaotu_lookup_open_id_by_name(user_name):
    return _report_feishu_documents._xiaotu_lookup_open_id_by_name(
        user_name,
        _XIAOTU_NOTIFY_ID_TABLE_FALLBACK=_XIAOTU_NOTIFY_ID_TABLE_FALLBACK,
        _XIAOTU_NOTIFY_ID_TABLE_PRIMARY=_XIAOTU_NOTIFY_ID_TABLE_PRIMARY,
        _safe_debug_print=_safe_debug_print,
        _xiaotu_get_cached_open_id_by_name=_xiaotu_get_cached_open_id_by_name,
        _xiaotu_list_notify_departments=_xiaotu_list_notify_departments,
        _xiaotu_list_notify_users_current_app_cached=_xiaotu_list_notify_users_current_app_cached,
        _xiaotu_remember_user_open_id=_xiaotu_remember_user_open_id,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        re=re,
        sf_db=sf_db,
    )


_XIAOTU_REPORT_ESCALATION_USER = "陶晓飞"


def _xiaotu_pick_primary_department(user_id):
    return _report_editor_context._xiaotu_pick_primary_department(
        user_id,
        permission_manager=permission_manager,
        session=session,
    )


def _xiaotu_get_department_leader_user_id(department_id):
    return _report_scope._xiaotu_get_department_leader_user_id(
        department_id,
        _feishu_http=_feishu_http,
        _safe_debug_print=_safe_debug_print,
        permission_manager=permission_manager,
    )


def _xiaotu_list_notify_departments():
    return _report_notify_directory._xiaotu_list_notify_departments(
        _XIAOTU_NOTIFY_ID_TABLE_FALLBACK=_XIAOTU_NOTIFY_ID_TABLE_FALLBACK,
        _XIAOTU_NOTIFY_ID_TABLE_PRIMARY=_XIAOTU_NOTIFY_ID_TABLE_PRIMARY,
        sf_db=sf_db,
    )


def _xiaotu_list_department_children_current_app(department_id):
    return _report_notify_directory._xiaotu_list_department_children_current_app(
        department_id,
        _feishu_http=_feishu_http,
        permission_manager=permission_manager,
    )


def _xiaotu_expand_department_tree_current_app(department_id):
    return _report_editor_context._xiaotu_expand_department_tree_current_app(department_id, _xiaotu_list_department_children_current_app=_xiaotu_list_department_children_current_app)


def _xiaotu_list_notify_users_current_app(department_id):
    return _report_notify_directory._xiaotu_list_notify_users_current_app(
        department_id,
        _feishu_http=_feishu_http,
        _xiaotu_expand_department_tree_current_app=_xiaotu_expand_department_tree_current_app,
        permission_manager=permission_manager,
    )


def _xiaotu_list_notify_users_current_app_cached(department_id):
    return _report_notify_directory._xiaotu_list_notify_users_current_app_cached(
        department_id,
        _xiaotu_list_notify_users_current_app=_xiaotu_list_notify_users_current_app,
        _xiaotu_notify_department_users_cache=_xiaotu_notify_department_users_cache,
        _xiaotu_notify_department_users_cache_lock=_xiaotu_notify_department_users_cache_lock,
        _xiaotu_notify_department_users_cache_ttl_seconds=_xiaotu_notify_department_users_cache_ttl_seconds,
        time=time,
    )


def _xiaotu_get_history_analysis_visible_user_names(user_id, user_name):
    return _report_notify_directory._xiaotu_get_history_analysis_visible_user_names(
        user_id,
        user_name,
        _XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES=_XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES,
        _current_user_has_permission=_current_user_has_permission,
        _xiaotu_collect_notify_user_names_by_department_names=_xiaotu_collect_notify_user_names_by_department_names,
        _xiaotu_get_department_leader_user_id=_xiaotu_get_department_leader_user_id,
        _xiaotu_list_notify_departments=_xiaotu_list_notify_departments,
        _xiaotu_list_notify_users_current_app_cached=_xiaotu_list_notify_users_current_app_cached,
        permission_manager=permission_manager,
    )


def _xiaotu_search_notify_users(keyword, limit=50):
    return _report_notify_directory._xiaotu_search_notify_users(
        keyword,
        limit,
        _XIAOTU_NOTIFY_ID_TABLE_FALLBACK=_XIAOTU_NOTIFY_ID_TABLE_FALLBACK,
        _XIAOTU_NOTIFY_ID_TABLE_PRIMARY=_XIAOTU_NOTIFY_ID_TABLE_PRIMARY,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        sf_db=sf_db,
    )


def _xiaotu_query_user_names_by_open_ids(open_ids):
    return _report_notify_directory._xiaotu_query_user_names_by_open_ids(
        open_ids,
        _XIAOTU_NOTIFY_ID_TABLE_FALLBACK=_XIAOTU_NOTIFY_ID_TABLE_FALLBACK,
        _XIAOTU_NOTIFY_ID_TABLE_PRIMARY=_XIAOTU_NOTIFY_ID_TABLE_PRIMARY,
        _feishu_http=_feishu_http,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        _resolve_feishu_user_name=_resolve_feishu_user_name,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        permission_manager=permission_manager,
        sf_db=sf_db,
    )


def _xiaotu_query_user_name_by_any_id(open_id='', user_id='', union_id=''):
    return _report_notify_directory._xiaotu_query_user_name_by_any_id(
        open_id,
        user_id,
        union_id,
        _feishu_http=_feishu_http,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        _resolve_feishu_user_name=_resolve_feishu_user_name,
        _xiaotu_query_user_names_by_open_ids=_xiaotu_query_user_names_by_open_ids,
        permission_manager=permission_manager,
    )


def _xiaotu_resolve_card_actor_name(payload):
    return _report_card_support._xiaotu_resolve_card_actor_name(
        payload,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        _xiaotu_is_invalid_feishu_name=_xiaotu_is_invalid_feishu_name,
        _xiaotu_query_user_name_by_any_id=_xiaotu_query_user_name_by_any_id,
    )


def _xiaotu_parse_notify_open_ids(data_dict):
    return _report_notify_directory._xiaotu_parse_notify_open_ids(
        data_dict,
        json=json,
        request=request,
    )


def _xiaotu_parse_notify_targets(data_dict):
    return _report_notify_directory._xiaotu_parse_notify_targets(
        data_dict,
        json=json,
        request=request,
    )


def _xiaotu_resolve_notify_names(open_ids, notify_targets=None):
    return _report_notify_directory._xiaotu_resolve_notify_names(
        open_ids,
        notify_targets,
        _xiaotu_query_user_names_by_open_ids=_xiaotu_query_user_names_by_open_ids,
    )


def _xiaotu_resolve_notify_open_ids(open_ids, notify_targets=None):
    return _report_notify_directory._xiaotu_resolve_notify_open_ids(
        open_ids,
        notify_targets,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
    )


def _xiaotu_extract_report_image_paths_from_html(html_text):
    return _report_docx_sections._xiaotu_extract_report_image_paths_from_html(
        html_text,
        os=os,
        parse_qs=parse_qs,
        re=re,
        relocate_storage_path=relocate_storage_path,
        unquote=unquote,
        urlparse=urlparse,
    )


def _xiaotu_split_cache_multi_value(raw_text):
    return _report_editor_context._xiaotu_split_cache_multi_value(
        raw_text,
        re=re,
        relocate_storage_path=relocate_storage_path,
    )


def _xiaotu_build_notify_cache_text(open_ids, notify_targets=None):
    return _report_draft_cache._xiaotu_build_notify_cache_text(
        open_ids,
        notify_targets,
        _XIAOTU_NOTIFY_CACHE_PREFIX=_XIAOTU_NOTIFY_CACHE_PREFIX,
        _xiaotu_query_user_names_by_open_ids=_xiaotu_query_user_names_by_open_ids,
        json=json,
    )


def _xiaotu_parse_notify_cache_text(raw_text):
    return _report_draft_cache._xiaotu_parse_notify_cache_text(
        raw_text,
        _XIAOTU_NOTIFY_CACHE_PREFIX=_XIAOTU_NOTIFY_CACHE_PREFIX,
        _xiaotu_query_user_names_by_open_ids=_xiaotu_query_user_names_by_open_ids,
        _xiaotu_resolve_notify_open_ids=_xiaotu_resolve_notify_open_ids,
        json=json,
    )




def _xiaotu_get_report_cache(user_name):
    return _report_draft_cache._xiaotu_get_report_cache(
        user_name,
        _XIAOTU_REPORT_CACHE_TABLE_FALLBACK=_XIAOTU_REPORT_CACHE_TABLE_FALLBACK,
        _XIAOTU_REPORT_CACHE_TABLE_PRIMARY=_XIAOTU_REPORT_CACHE_TABLE_PRIMARY,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_normalize_notify_time=_xiaotu_normalize_notify_time,
        _xiaotu_parse_notify_cache_text=_xiaotu_parse_notify_cache_text,
        _xiaotu_resolve_notify_names=_xiaotu_resolve_notify_names,
        _xiaotu_split_cache_multi_value=_xiaotu_split_cache_multi_value,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        sf_db=sf_db,
    )


def _xiaotu_upsert_report_cache_notify(user_name, notify_open_ids, notify_targets=None, notify_time=''):
    return _report_draft_cache._xiaotu_upsert_report_cache_notify(
        user_name,
        notify_open_ids,
        notify_targets,
        notify_time,
        _XIAOTU_REPORT_CACHE_TABLE_FALLBACK=_XIAOTU_REPORT_CACHE_TABLE_FALLBACK,
        _XIAOTU_REPORT_CACHE_TABLE_PRIMARY=_XIAOTU_REPORT_CACHE_TABLE_PRIMARY,
        _xiaotu_build_notify_cache_text=_xiaotu_build_notify_cache_text,
        _xiaotu_normalize_notify_time=_xiaotu_normalize_notify_time,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        dui_db=dui_db,
    )


def _xiaotu_upsert_report_cache_draft(user_name, draft_html, image_paths):
    return _report_draft_cache._xiaotu_upsert_report_cache_draft(
        user_name,
        draft_html,
        image_paths,
        _XIAOTU_REPORT_CACHE_TABLE_FALLBACK=_XIAOTU_REPORT_CACHE_TABLE_FALLBACK,
        _XIAOTU_REPORT_CACHE_TABLE_PRIMARY=_XIAOTU_REPORT_CACHE_TABLE_PRIMARY,
        _xiaotu_split_cache_multi_value=_xiaotu_split_cache_multi_value,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        dui_db=dui_db,
    )


def _xiaotu_clear_report_cache_draft(user_name):
    return _report_draft_cache._xiaotu_clear_report_cache_draft(
        user_name,
        _XIAOTU_REPORT_CACHE_TABLE_FALLBACK=_XIAOTU_REPORT_CACHE_TABLE_FALLBACK,
        _XIAOTU_REPORT_CACHE_TABLE_PRIMARY=_XIAOTU_REPORT_CACHE_TABLE_PRIMARY,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        dui_db=dui_db,
    )


def _xiaotu_get_period_range(report_type):
    return _report_values._xiaotu_get_period_range(
        report_type,
        datetime=datetime,
        timedelta=timedelta,
    )


def _xiaotu_get_sender_open_id_from_message(message_row):
    return _report_values._xiaotu_get_sender_open_id_from_message(message_row)


def _xiaotu_get_message_text_for_daily_ref(message_row):
    return _report_editor_context._xiaotu_get_message_text_for_daily_ref(message_row, _feishu_extract_text_from_content=_feishu_extract_text_from_content)




def _xiaotu_render_period_source_text(rows):
    return _report_editor_context._xiaotu_render_period_source_text(rows)


_XIAOTU_REPORT_HISTORY_ANALYSIS_DIR = relocate_storage_path(r"D:\tuchuangai\日报历史分析")


def _xiaotu_parse_date_value(value, fallback=None):
    return _report_values._xiaotu_parse_date_value(
        value,
        fallback,
        datetime=datetime,
    )


def _xiaotu_report_image_url(path_value):
    return _report_values._xiaotu_report_image_url(
        path_value,
        quote=quote,
        relocate_storage_path=relocate_storage_path,
        url_for=url_for,
    )


def _xiaotu_normalize_report_html_body(raw_html, image_paths_text=''):
    return _report_export_views._xiaotu_normalize_report_html_body(
        raw_html,
        image_paths_text,
        _xiaotu_report_image_url=_xiaotu_report_image_url,
        html_escape=html_escape,
        html_unescape=html_unescape,
        os=os,
        re=re,
    )




def _xiaotu_build_history_analysis_html(user_name, start_date, end_date, analysis_text, rows):
    return _report_export_views._xiaotu_build_history_analysis_html(
        user_name,
        start_date,
        end_date,
        analysis_text,
        rows,
        _xiaotu_markdownish_to_html=_xiaotu_markdownish_to_html,
        _xiaotu_normalize_report_html_body=_xiaotu_normalize_report_html_body,
        datetime=datetime,
        html_escape=html_escape,
    )


def _xiaotu_save_history_analysis_file(user_name, start_date, end_date, html_text):
    return _report_values._xiaotu_save_history_analysis_file(
        user_name,
        start_date,
        end_date,
        html_text,
        _XIAOTU_REPORT_HISTORY_ANALYSIS_DIR=_XIAOTU_REPORT_HISTORY_ANALYSIS_DIR,
        datetime=datetime,
        os=os,
        re=re,
    )


def _xiaotu_extract_knowledge_terms(question):
    return _report_document_pages._xiaotu_extract_knowledge_terms(question, re=re)


def _xiaotu_render_knowledge_source_text(rows):
    return _report_editor_context._xiaotu_render_knowledge_source_text(rows)


def _xiaotu_resolve_redirect_url(endpoint_name, fallback='dashboard_xiaotu'):
    return _report_values._xiaotu_resolve_redirect_url(
        endpoint_name,
        fallback,
        url_for=url_for,
    )


def _xiaotu_classify_image_debug(err_text, image_block_count, saved_count):
    return _report_media_ingestion._xiaotu_classify_image_debug(
        err_text,
        image_block_count,
        saved_count,
    )


def _xiaotu_pick_doc_for_request(user_id, user_access_token, doc_id='', manual_url='', question=''):
    return _report_docx_sections._xiaotu_pick_doc_for_request(
        user_id,
        user_access_token,
        doc_id,
        manual_url,
        question,
        _feishu_build_cloud_doc_url=_feishu_build_cloud_doc_url,
        _feishu_find_cloud_doc_url_any=_feishu_find_cloud_doc_url_any,
        _xiaotu_extract_doc_token=_xiaotu_extract_doc_token,
        _xiaotu_get_doc_candidates_for_user=_xiaotu_get_doc_candidates_for_user,
    )


def _xiaotu_save_doc_images_and_ocr(agent, doc_token, doc_url='', specific_tokens=None):
    return _report_media_ingestion._xiaotu_save_doc_images_and_ocr(
        agent,
        doc_token,
        doc_url,
        specific_tokens,
        _ocr_images_bytes_with_ai=_ocr_images_bytes_with_ai,
        _xiaotu_classify_image_debug=_xiaotu_classify_image_debug,
        os=os,
        relocate_storage_path=relocate_storage_path,
    )


def _xiaotu_save_uploaded_images_and_ocr(files, report_token='', root_base_dir=relocate_storage_path('D:\\tuchuangai\\报告图片')):
    return _report_media_ingestion._xiaotu_save_uploaded_images_and_ocr(
        files,
        report_token,
        root_base_dir,
        _ocr_images_bytes_with_ai=_ocr_images_bytes_with_ai,
        datetime=datetime,
        os=os,
        relocate_storage_path=relocate_storage_path,
        secure_filename=secure_filename,
    )


def _xiaotu_save_inline_html_images_and_ocr(html_text, report_token='', root_base_dir=relocate_storage_path('D:\\tuchuangai\\报告图片')):
    return _report_media_ingestion._xiaotu_save_inline_html_images_and_ocr(
        html_text,
        report_token,
        root_base_dir,
        _ocr_images_bytes_with_ai=_ocr_images_bytes_with_ai,
        base64=base64,
        datetime=datetime,
        os=os,
        re=re,
        relocate_storage_path=relocate_storage_path,
    )


def _xiaotu_extract_feishu_file_token_from_fragment(fragment_text):
    return _report_media_ingestion._xiaotu_extract_feishu_file_token_from_fragment(
        fragment_text,
        base64=base64,
        html_unescape=html_unescape,
        json=json,
        re=re,
    )


def _xiaotu_save_remote_html_images_and_ocr(html_text, report_token='', agent=None, root_base_dir=relocate_storage_path('D:\\tuchuangai\\报告图片')):
    return _report_media_ingestion._xiaotu_save_remote_html_images_and_ocr(
        html_text,
        report_token,
        agent,
        root_base_dir,
        _ocr_images_bytes_with_ai=_ocr_images_bytes_with_ai,
        _xiaotu_extract_feishu_file_token_from_fragment=_xiaotu_extract_feishu_file_token_from_fragment,
        datetime=datetime,
        html_unescape=html_unescape,
        mimetypes=mimetypes,
        os=os,
        re=re,
        relocate_storage_path=relocate_storage_path,
        requests=requests,
        unquote=unquote,
        urlparse=urlparse,
    )


def _xiaotu_replace_html_img_src_with_paths(html_text, image_paths):
    return _report_media_ingestion._xiaotu_replace_html_img_src_with_paths(
        html_text,
        image_paths,
        re=re,
    )




def _xiaotu_image_debug(reason_code, reason_text, saved_count=0):
    return _report_media_ingestion._xiaotu_image_debug(
        reason_code,
        reason_text,
        saved_count,
    )


def _xiaotu_save_uploaded_images_and_ocr_safe(files, report_token='', root_base_dir=relocate_storage_path('D:\\tuchuangai\\报告图片')):
    return _report_media_safe._xiaotu_save_uploaded_images_and_ocr_safe(
        files,
        report_token,
        root_base_dir,
        _xiaotu_image_debug=_xiaotu_image_debug,
        _xiaotu_save_uploaded_images_and_ocr=_xiaotu_save_uploaded_images_and_ocr,
    )


def _xiaotu_save_inline_html_images_and_ocr_safe(html_text, report_token='', root_base_dir=relocate_storage_path('D:\\tuchuangai\\报告图片')):
    return _report_media_safe._xiaotu_save_inline_html_images_and_ocr_safe(
        html_text,
        report_token,
        root_base_dir,
        _xiaotu_compact_report_body_for_storage=_xiaotu_compact_report_body_for_storage,
        _xiaotu_image_debug=_xiaotu_image_debug,
        _xiaotu_save_inline_html_images_and_ocr=_xiaotu_save_inline_html_images_and_ocr,
    )


def _xiaotu_save_remote_html_images_and_ocr_safe(html_text, report_token='', agent=None, root_base_dir=relocate_storage_path('D:\\tuchuangai\\报告图片')):
    return _report_media_safe._xiaotu_save_remote_html_images_and_ocr_safe(
        html_text,
        report_token,
        agent,
        root_base_dir,
        _xiaotu_compact_report_body_for_storage=_xiaotu_compact_report_body_for_storage,
        _xiaotu_image_debug=_xiaotu_image_debug,
        _xiaotu_save_remote_html_images_and_ocr=_xiaotu_save_remote_html_images_and_ocr,
    )


def _xiaotu_save_doc_images_and_ocr_safe(agent, doc_token, doc_url='', specific_tokens=None):
    return _report_media_safe._xiaotu_save_doc_images_and_ocr_safe(
        agent,
        doc_token,
        doc_url,
        specific_tokens,
        _xiaotu_image_debug=_xiaotu_image_debug,
        _xiaotu_save_doc_images_and_ocr=_xiaotu_save_doc_images_and_ocr,
    )


def _feishu_upload_image_by_path_safe(image_path):
    return _report_media_safe._feishu_upload_image_by_path_safe(image_path, _feishu_upload_image_by_path=_feishu_upload_image_by_path)


def _xiaotu_extract_url_from_text(text):
    return _report_values._xiaotu_extract_url_from_text(text, re=re)


def _xiaotu_get_doc_candidates_for_user(user_id, force_refresh=False, user_access_token=''):
    return _report_feishu_documents._xiaotu_get_doc_candidates_for_user(
        user_id,
        force_refresh,
        user_access_token,
        _XIAOTU_SHARED_DOCS=_XIAOTU_SHARED_DOCS,
        _xiaotu_get_user_departments=_xiaotu_get_user_departments,
        _xiaotu_get_user_saved_docs=_xiaotu_get_user_saved_docs,
        _xiaotu_list_feishu_docs_for_user=_xiaotu_list_feishu_docs_for_user,
        _xiaotu_match_doc_permission=_xiaotu_match_doc_permission,
    )

# 注册蓝图
app.register_blueprint(review_analysis_bp)
app.register_blueprint(influencer_management_bp)
app.register_blueprint(model_management_bp)
app.register_blueprint(innovation_proposals_bp)
app.register_blueprint(innovation_bp)
app.register_blueprint(tk_dashboard_bp)
app.register_blueprint(listing_agent_bp)
app.register_blueprint(listing_agent_v2_bp)
app.register_blueprint(daily_replenishment_bp)
app.register_blueprint(daily_replenishment_operation_bp)
app.register_blueprint(daily_replenishment_tiktok_bp)
app.register_blueprint(ai_group_performance_bp)
app.register_blueprint(historical_sales_bp)
app.register_blueprint(developer_product_sales_bp)
app.register_blueprint(value_evaluation_bp)
app.register_blueprint(bd_metrics_bp)
app.register_blueprint(seedance_web_bp, url_prefix="/seedance-web")
app.register_blueprint(yangban_inventory_bp)
app.register_blueprint(tk_gmv_authorization_bp)


def get_message_service():
    company_key = request.args.get('company', 'company1')
    return MessageService(company_key)


@app.route('/api/ai/version_update_notice', methods=['POST'])
@require_permission('admin_functions')
def api_ai_version_update_notice():
    return _version_notice_routes.api_ai_version_update_notice(
        datetime=datetime,
        get_message_service=get_message_service,
        jsonify=jsonify,
        request=request,
        sf_db=sf_db,
    )


@app.route('/api/ai/version_update_departments')
@require_permission('admin_functions')
def api_ai_version_update_departments():
    return _version_notice_routes.api_ai_version_update_departments(jsonify=jsonify, sf_db=sf_db)


@app.route('/api/ai/delete_innovation_project', methods=['POST'])
@require_permission('admin_functions')
def api_ai_delete_innovation_project():
    return _innovation_admin_routes.api_ai_delete_innovation_project(
        dui_db=dui_db,
        jsonify=jsonify,
        request=request,
    )


@app.route('/api/ai/innovation_project_preview', methods=['GET'])
@require_permission('admin_functions')
def api_ai_innovation_project_preview():
    return _innovation_admin_routes.api_ai_innovation_project_preview(
        jsonify=jsonify,
        request=request,
        sf_db=sf_db,
    )


@app.route('/api/ai/innovation_pending_reminder/test-send', methods=['POST'])
@require_permission('admin_functions')
def api_ai_innovation_pending_reminder_test_send():
    return _innovation_admin_routes.api_ai_innovation_pending_reminder_test_send(
        datetime=datetime,
        innovation_pending_reminder=innovation_pending_reminder,
        jsonify=jsonify,
        sf_db=sf_db,
    )


@app.route('/dev_login')
def dev_login():
    return _feishu_session_identity.dev_login(
        _safe_debug_print=_safe_debug_print,
        _set_feishu_user_access_token=_set_feishu_user_access_token,
        _xiaotu_remember_user_open_id=_xiaotu_remember_user_open_id,
        app=app,
        datetime=datetime,
        is_local_superadmin=is_local_superadmin,
        redirect=redirect,
        request=request,
        session=session,
        timedelta=timedelta,
        url_for=url_for,
    )


@app.before_request
def check_feishu_user():
    return _feishu_session_identity.check_feishu_user(
        _clear_feishu_identity_session=_clear_feishu_identity_session,
        _debug_log_elapsed=_debug_log_elapsed,
        _get_feishu_user_access_token=_get_feishu_user_access_token,
        _handle_feishu_identity_mismatch=_handle_feishu_identity_mismatch,
        _load_dashboard_identity_switch_request_state=_load_dashboard_identity_switch_request_state,
        _safe_debug_print=_safe_debug_print,
        _seedance_access_allowed=_seedance_access_allowed,
        _start_xiaotu_report_reminder_thread_once=_start_xiaotu_report_reminder_thread_once,
        _sync_feishu_identity_via_current_app=_sync_feishu_identity_via_current_app,
        _xiaotu_remember_user_open_id=_xiaotu_remember_user_open_id,
        app=app,
        env=env,
        innovation_pending_reminder=innovation_pending_reminder,
        is_local_superadmin=is_local_superadmin,
        jsonify=jsonify,
        lunch_push=lunch_push,
        redirect=redirect,
        request=request,
        session=session,
        time=time,
        tk_customer_service_tracking_reminder=tk_customer_service_tracking_reminder,
        url_for=url_for,
    )


def _seedance_access_allowed():
    return _tool_entry_pages._seedance_access_allowed(_current_user_has_permission=_current_user_has_permission)


# AI的API密钥和配置
_AI_CONFIG_PATH = os.path.join(
    str(TUCHUANGAI_STORAGE_ROOT) if env("TC_CONTAINER_MODE") == "1" else os.path.dirname(__file__),
    "ai_runtime_config.json",
)
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
_report_card_messages = ReportCardMessageStore(os.path.join(
    str(TUCHUANGAI_STORAGE_ROOT) if env("TC_CONTAINER_MODE") == "1" else os.path.dirname(__file__),
    "xiaotu_report_card_messages.json",
))
_xiaotu_report_owner_open_id_map = {}
_feishu_message_text_cache = {}
_feishu_message_text_cache_ttl_seconds = 600
_feishu_message_text_cache_lock = Lock()
_feishu_skills = FeishuSkillCatalog(os.path.dirname(__file__))


def _feishu_parse_skill_frontmatter(md_text):
    return _feishu_skills.parse_frontmatter(md_text)


def _feishu_load_skills(force_refresh=False):
    return _feishu_skills.load(force_refresh)


def _feishu_get_skill(skill_name):
    return _feishu_skills.get(skill_name)


def _feishu_render_skill_list():
    return _feishu_skills.render_list()


def _feishu_parse_skill_invocation(text):
    return _feishu_skills.parse_invocation(text)


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
    return _feishu_chat_flow._feishu_is_message_processed(
        message_id,
        _feishu_processed_message_cache=_feishu_processed_message_cache,
        _feishu_processed_message_ttl_seconds=_feishu_processed_message_ttl_seconds,
        datetime=datetime,
    )


def _feishu_mark_message_processed(message_id):
    return _feishu_chat_flow._feishu_mark_message_processed(
        message_id,
        _feishu_processed_message_cache=_feishu_processed_message_cache,
        datetime=datetime,
    )


def _feishu_is_event_processed(event_id):
    return _feishu_chat_flow._feishu_is_event_processed(
        event_id,
        _feishu_processed_event_cache=_feishu_processed_event_cache,
        _feishu_processed_event_ttl_seconds=_feishu_processed_event_ttl_seconds,
        datetime=datetime,
    )


def _feishu_mark_event_processed(event_id):
    return _feishu_chat_flow._feishu_mark_event_processed(
        event_id,
        _feishu_processed_event_cache=_feishu_processed_event_cache,
        datetime=datetime,
    )


def _feishu_memory_prune_locked(now_ts):
    return _feishu_chat_flow._feishu_memory_prune_locked(
        now_ts,
        _feishu_chat_memory=_feishu_chat_memory,
        _feishu_chat_memory_ttl_seconds=_feishu_chat_memory_ttl_seconds,
    )


def _feishu_get_chat_history(chat_id):
    return _feishu_chat_flow._feishu_get_chat_history(
        chat_id,
        _feishu_chat_memory=_feishu_chat_memory,
        _feishu_chat_memory_lock=_feishu_chat_memory_lock,
        _feishu_memory_prune_locked=_feishu_memory_prune_locked,
        datetime=datetime,
    )


def _feishu_append_chat_history(chat_id, role, content):
    return _feishu_chat_resources._feishu_append_chat_history(
        chat_id,
        role,
        content,
        _feishu_chat_memory=_feishu_chat_memory,
        _feishu_chat_memory_lock=_feishu_chat_memory_lock,
        _feishu_chat_memory_max_messages=_feishu_chat_memory_max_messages,
        _feishu_extract_resources_from_text=_feishu_extract_resources_from_text,
        _feishu_memory_prune_locked=_feishu_memory_prune_locked,
        datetime=datetime,
    )


def _feishu_clear_chat_history(chat_id):
    return _feishu_chat_flow._feishu_clear_chat_history(
        chat_id,
        _feishu_chat_memory=_feishu_chat_memory,
        _feishu_chat_memory_lock=_feishu_chat_memory_lock,
    )


def _feishu_extract_resources_from_text(text):
    return _feishu_chat_flow._feishu_extract_resources_from_text(
        text,
        _feishu_find_bitable_url=_feishu_find_bitable_url,
        _feishu_find_cloud_doc_url_any=_feishu_find_cloud_doc_url_any,
    )


def _feishu_remember_resources(chat_id, text):
    return _feishu_chat_resources._feishu_remember_resources(
        chat_id,
        text,
        _feishu_chat_memory=_feishu_chat_memory,
        _feishu_chat_memory_lock=_feishu_chat_memory_lock,
        _feishu_extract_resources_from_text=_feishu_extract_resources_from_text,
        _feishu_memory_prune_locked=_feishu_memory_prune_locked,
        datetime=datetime,
    )


def _feishu_remember_image_resource(chat_id, key, message_id='', resource_type='image', file_name=''):
    return _feishu_chat_resources._feishu_remember_image_resource(
        chat_id,
        key,
        message_id,
        resource_type,
        file_name,
        _feishu_chat_memory=_feishu_chat_memory,
        _feishu_chat_memory_lock=_feishu_chat_memory_lock,
        _feishu_memory_prune_locked=_feishu_memory_prune_locked,
        datetime=datetime,
    )


def _feishu_get_last_bot_ts(chat_id):
    return _feishu_chat_flow._feishu_get_last_bot_ts(
        chat_id,
        _feishu_chat_memory=_feishu_chat_memory,
        _feishu_chat_memory_lock=_feishu_chat_memory_lock,
        _feishu_memory_prune_locked=_feishu_memory_prune_locked,
        datetime=datetime,
    )


def _feishu_get_last_resource(chat_id, prefer_type=''):
    return _feishu_chat_flow._feishu_get_last_resource(
        chat_id,
        prefer_type,
        _feishu_chat_memory=_feishu_chat_memory,
        _feishu_chat_memory_lock=_feishu_chat_memory_lock,
        _feishu_memory_prune_locked=_feishu_memory_prune_locked,
        datetime=datetime,
    )


def _feishu_is_message_id(value):
    return _feishu_chat_flow._feishu_is_message_id(value)


def _feishu_extract_reference_message_ids(message_obj, content_obj=None):
    return _feishu_chat_resources._feishu_extract_reference_message_ids(
        message_obj,
        content_obj,
        _feishu_is_message_id=_feishu_is_message_id,
    )


def _feishu_get_message_text(message_id):
    return _feishu_chat_resources._feishu_get_message_text(
        message_id,
        _feishu_extract_text_from_content=_feishu_extract_text_from_content,
        _feishu_http=_feishu_http,
        _feishu_message_text_cache=_feishu_message_text_cache,
        _feishu_message_text_cache_lock=_feishu_message_text_cache_lock,
        _feishu_message_text_cache_ttl_seconds=_feishu_message_text_cache_ttl_seconds,
        datetime=datetime,
        permission_manager=permission_manager,
    )


def _feishu_extract_text_from_content(content):
    return _feishu_chat_resources._feishu_extract_text_from_content(
        content,
        _feishu_extract_text_from_content=_feishu_extract_text_from_content,
        json=json,
    )


def _feishu_is_group_message(chat_type):
    return _feishu_chat_flow._feishu_is_group_message(chat_type)


def _feishu_is_p2p_message(chat_type):
    return _feishu_chat_flow._feishu_is_p2p_message(chat_type)


def _feishu_is_bot_mentioned(text, mentions):
    return _feishu_chat_flow._feishu_is_bot_mentioned(
        text,
        mentions,
        FEISHU_BOT_NAME=FEISHU_BOT_NAME,
    )


def _feishu_clean_question(text):
    return _feishu_chat_flow._feishu_clean_question(
        text,
        FEISHU_BOT_NAME=FEISHU_BOT_NAME,
        re=re,
    )


def _feishu_send_text_to_chat(chat_id, message_text):
    return _feishu_chat_flow._feishu_send_text_to_chat(
        chat_id,
        message_text,
        _feishu_recent_events=_feishu_recent_events,
        _feishu_recent_events_limit=_feishu_recent_events_limit,
        _safe_debug_print=_safe_debug_print,
        datetime=datetime,
        json=json,
        permission_manager=permission_manager,
    )


def _xiaotu_remember_report_card_message(wendangid, receive_id, message_id):
    return _report_card_messages.remember(wendangid, receive_id, message_id)


def _xiaotu_ensure_report_card_message_store_loaded():
    return _report_card_messages._ensure_loaded()


def _xiaotu_save_report_card_message_store_locked():
    return _report_card_messages._save_locked()


def _xiaotu_get_report_card_message_ids(wendangid, receive_id=''):
    return _report_card_messages.message_ids(wendangid, receive_id)


def _xiaotu_get_report_card_message_id(wendangid, receive_id=''):
    return _report_card_messages.message_id(wendangid, receive_id)


def _xiaotu_get_report_card_receive_ids(wendangid):
    return _report_card_messages.receive_ids(wendangid)


def _xiaotu_forget_report_card_messages(wendangid):
    return _report_card_messages.forget(wendangid)


def _xiaotu_collect_report_card_message_entries(wendangid, latest_only=False):
    return _report_card_messages.entries(wendangid, latest_only)


def _xiaotu_get_report_row(wendangid):
    return _report_comment_pages._xiaotu_get_report_row(
        wendangid,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        sf_db=sf_db,
    )


def _xiaotu_get_report_owner_open_id_resolved(wendangid, report_row=None):
    return _report_card_context._xiaotu_get_report_owner_open_id_resolved(
        wendangid,
        report_row,
        _xiaotu_get_report_owner_open_id=_xiaotu_get_report_owner_open_id,
        _xiaotu_get_report_row=_xiaotu_get_report_row,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_remember_report_owner_open_id=_xiaotu_remember_report_owner_open_id,
    )


def _feishu_get_message_read_users(message_id, user_id_type='open_id', page_size=100):
    return _feishu_message_delivery._feishu_get_message_read_users(
        message_id,
        user_id_type,
        page_size,
        _feishu_http=_feishu_http,
        permission_manager=permission_manager,
    )


def _feishu_recall_message(message_id):
    return _feishu_message_delivery._feishu_recall_message(
        message_id,
        _feishu_http=_feishu_http,
        permission_manager=permission_manager,
    )


def _xiaotu_guess_report_default_notify_open_ids(owner_open_id, owner_name=''):
    return _report_card_support._xiaotu_guess_report_default_notify_open_ids(
        owner_open_id,
        owner_name,
        _XIAOTU_REPORT_ESCALATION_USER=_XIAOTU_REPORT_ESCALATION_USER,
        _xiaotu_get_department_leader_user_id=_xiaotu_get_department_leader_user_id,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_pick_primary_department=_xiaotu_pick_primary_department,
    )


def _xiaotu_collect_report_delivery_targets(wendangid, report_row=None):
    return _report_delivery_routes._xiaotu_collect_report_delivery_targets(
        wendangid,
        report_row,
        _xiaotu_get_report_card_receive_ids=_xiaotu_get_report_card_receive_ids,
        _xiaotu_get_report_owner_open_id_resolved=_xiaotu_get_report_owner_open_id_resolved,
        _xiaotu_get_report_row=_xiaotu_get_report_row,
        _xiaotu_guess_report_default_notify_open_ids=_xiaotu_guess_report_default_notify_open_ids,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_query_user_names_by_open_ids=_xiaotu_query_user_names_by_open_ids,
        _xiaotu_split_cache_multi_value=_xiaotu_split_cache_multi_value,
    )


def _xiaotu_get_report_delivery_status(wendangid, report_row=None):
    return _report_delivery_routes._xiaotu_get_report_delivery_status(
        wendangid,
        report_row,
        _feishu_get_message_read_users=_feishu_get_message_read_users,
        _xiaotu_collect_report_delivery_targets=_xiaotu_collect_report_delivery_targets,
        _xiaotu_get_report_card_message_id=_xiaotu_get_report_card_message_id,
        _xiaotu_get_report_row=_xiaotu_get_report_row,
    )


def _xiaotu_set_report_edit_ready_session(wendangid, notify_open_ids, notify_targets):
    return _report_card_context._xiaotu_set_report_edit_ready_session(
        wendangid,
        notify_open_ids,
        notify_targets,
        _XIAOTU_REPORT_EDIT_READY_SESSION_KEY=_XIAOTU_REPORT_EDIT_READY_SESSION_KEY,
        datetime=datetime,
        session=session,
    )


def _xiaotu_clear_report_edit_ready_session(wendangid=''):
    return _report_card_context._xiaotu_clear_report_edit_ready_session(
        wendangid,
        _XIAOTU_REPORT_EDIT_READY_SESSION_KEY=_XIAOTU_REPORT_EDIT_READY_SESSION_KEY,
        session=session,
    )


def _xiaotu_get_report_edit_ready_session(wendangid=''):
    return _report_card_context._xiaotu_get_report_edit_ready_session(
        wendangid,
        _XIAOTU_REPORT_EDIT_READY_SESSION_KEY=_XIAOTU_REPORT_EDIT_READY_SESSION_KEY,
        _XIAOTU_REPORT_EDIT_READY_TTL_SECONDS=_XIAOTU_REPORT_EDIT_READY_TTL_SECONDS,
        _xiaotu_clear_report_edit_ready_session=_xiaotu_clear_report_edit_ready_session,
        datetime=datetime,
        session=session,
    )


def _xiaotu_patch_related_report_cards(wendangid, open_ids, card_obj, skip_message_ids=None):
    return _report_card_support._xiaotu_patch_related_report_cards(
        wendangid,
        open_ids,
        card_obj,
        skip_message_ids,
        _feishu_update_message_card=_feishu_update_message_card,
        _xiaotu_get_report_card_message_ids=_xiaotu_get_report_card_message_ids,
    )


def _xiaotu_remember_report_owner_open_id(wendangid, open_id):
    return _report_notification_pages._xiaotu_remember_report_owner_open_id(
        wendangid,
        open_id,
        _xiaotu_report_owner_open_id_map=_xiaotu_report_owner_open_id_map,
    )


def _xiaotu_get_report_owner_open_id(wendangid):
    return _report_notification_pages._xiaotu_get_report_owner_open_id(wendangid, _xiaotu_report_owner_open_id_map=_xiaotu_report_owner_open_id_map)


def _feishu_send_message_detail(receive_id, receive_id_type, msg_type, content_obj):
    return _feishu_message_delivery._feishu_send_message_detail(
        receive_id,
        receive_id_type,
        msg_type,
        content_obj,
        json=json,
        permission_manager=permission_manager,
    )


def _feishu_send_message(receive_id, receive_id_type, msg_type, content_obj):
    return _feishu_message_delivery._feishu_send_message(
        receive_id,
        receive_id_type,
        msg_type,
        content_obj,
        _feishu_send_message_detail=_feishu_send_message_detail,
    )


def _feishu_update_message_card(message_id, card_obj):
    return _feishu_message_delivery._feishu_update_message_card(
        message_id,
        card_obj,
        _feishu_recent_events=_feishu_recent_events,
        _feishu_recent_events_limit=_feishu_recent_events_limit,
        datetime=datetime,
        json=json,
        permission_manager=permission_manager,
    )


def _feishu_send_text(receive_id, receive_id_type, message_text):
    return _feishu_send_message(receive_id, receive_id_type, "text", {"text": message_text})


def _xiaotu_has_report_submitted_today(user_name, now_dt=None):
    return _report_reminders._xiaotu_has_report_submitted_today(
        user_name,
        now_dt,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        datetime=datetime,
        sf_db=sf_db,
        timedelta=timedelta,
    )


def _xiaotu_list_due_report_reminders(target_hhmm):
    return _report_reminders._xiaotu_list_due_report_reminders(
        target_hhmm,
        _XIAOTU_REPORT_CACHE_TABLE_PRIMARY=_XIAOTU_REPORT_CACHE_TABLE_PRIMARY,
        _xiaotu_normalize_notify_time=_xiaotu_normalize_notify_time,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        sf_db=sf_db,
    )


def _xiaotu_build_report_reminder_text(user_name, notify_time):
    return _report_reminders._xiaotu_build_report_reminder_text(
        user_name,
        notify_time,
        _xiaotu_build_report_center_url=_xiaotu_build_report_center_url,
        _xiaotu_normalize_notify_time=_xiaotu_normalize_notify_time,
        datetime=datetime,
    )


def _xiaotu_append_report_reminder_log(stage, **kwargs):
    return _report_reminder_state._xiaotu_append_report_reminder_log(
        stage,
        kwargs,
        _safe_debug_print=_safe_debug_print,
        _xiaotu_report_reminder_lock=_xiaotu_report_reminder_lock,
        _xiaotu_report_reminder_logs=_xiaotu_report_reminder_logs,
        _xiaotu_report_reminder_logs_limit=_xiaotu_report_reminder_logs_limit,
        datetime=datetime,
        json=json,
    )


def _xiaotu_build_report_center_url():
    return _report_reminders._xiaotu_build_report_center_url(
        _XIAOTU_REPORT_CENTER_PUBLIC_URL=_XIAOTU_REPORT_CENTER_PUBLIC_URL,
        request=request,
        url_for=url_for,
        urlparse=urlparse,
    )


def _xiaotu_build_missing_report_reminder_card(user_name, notify_time):
    return _report_cards._xiaotu_build_missing_report_reminder_card(
        user_name,
        notify_time,
        _xiaotu_build_report_center_url=_xiaotu_build_report_center_url,
        _xiaotu_normalize_notify_time=_xiaotu_normalize_notify_time,
        datetime=datetime,
    )


def _xiaotu_send_missing_report_reminder(receive_id, receive_id_type, user_name, notify_time):
    return _report_reminders._xiaotu_send_missing_report_reminder(
        receive_id,
        receive_id_type,
        user_name,
        notify_time,
        _feishu_send_message_detail=_feishu_send_message_detail,
        _feishu_send_text=_feishu_send_text,
        _xiaotu_build_missing_report_reminder_card=_xiaotu_build_missing_report_reminder_card,
        _xiaotu_build_report_reminder_text=_xiaotu_build_report_reminder_text,
    )


def _xiaotu_run_report_reminder_once(now_dt=None):
    return _report_reminders._xiaotu_run_report_reminder_once(
        now_dt,
        _safe_debug_print=_safe_debug_print,
        _xiaotu_append_report_reminder_log=_xiaotu_append_report_reminder_log,
        _xiaotu_get_cached_open_id_by_name=_xiaotu_get_cached_open_id_by_name,
        _xiaotu_has_report_submitted_today=_xiaotu_has_report_submitted_today,
        _xiaotu_list_due_report_reminders=_xiaotu_list_due_report_reminders,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_normalize_notify_time=_xiaotu_normalize_notify_time,
        _xiaotu_report_reminder_lock=_xiaotu_report_reminder_lock,
        _xiaotu_report_reminder_sent_marks=_xiaotu_report_reminder_sent_marks,
        _xiaotu_report_reminder_thread_started=_xiaotu_report_reminder_thread_started,
        _xiaotu_send_missing_report_reminder=_xiaotu_send_missing_report_reminder,
        datetime=datetime,
    )


def _xiaotu_report_reminder_loop():
    return _report_reminders._xiaotu_report_reminder_loop(
        _safe_debug_print=_safe_debug_print,
        _xiaotu_append_report_reminder_log=_xiaotu_append_report_reminder_log,
        _xiaotu_run_report_reminder_once=_xiaotu_run_report_reminder_once,
        app=app,
        time=time,
    )


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








def _xiaotu_parse_image_path_list(raw_paths):
    return _report_values._xiaotu_parse_image_path_list(raw_paths, relocate_storage_path=relocate_storage_path)


def _xiaotu_image_file_name(raw_path):
    return _report_values._xiaotu_image_file_name(raw_path)




def _xiaotu_clean_card_text_block(raw_text):
    return _report_card_support._xiaotu_clean_card_text_block(
        raw_text,
        html_unescape=html_unescape,
        re=re,
    )


def _XiaoTuCardSourceParser(image_paths):
    return CardSourceParser(
        image_paths,
        clean_text=_xiaotu_clean_card_text_block,
        normalize_path=_xiaotu_normalize_compare_path,
        image_name=_xiaotu_image_file_name,
    )


def _xiaotu_build_card_source_elements(source_text, image_paths_text="", fallback_image_key="", max_blocks=16, full_content_url=""):
    return _report_cards._xiaotu_build_card_source_elements(
        source_text,
        image_paths_text,
        fallback_image_key,
        max_blocks,
        full_content_url,
        _XiaoTuCardSourceParser=_XiaoTuCardSourceParser,
        _feishu_upload_image_by_path=_feishu_upload_image_by_path,
        _xiaotu_clean_card_text_block=_xiaotu_clean_card_text_block,
        _xiaotu_clip_card_text=_xiaotu_clip_card_text,
        _xiaotu_extract_plain_preview_text=_xiaotu_extract_plain_preview_text,
        _xiaotu_parse_image_path_list=_xiaotu_parse_image_path_list,
        re=re,
    )


def _feishu_upload_image_by_path(image_path):
    return _feishu_message_delivery._feishu_upload_image_by_path(
        image_path,
        mimetypes=mimetypes,
        os=os,
        permission_manager=permission_manager,
        relocate_storage_path=relocate_storage_path,
        requests=requests,
    )






def _xiaotu_enrich_feedback_data(feedback, owner_name=''):
    return _report_scope._xiaotu_enrich_feedback_data(
        feedback,
        owner_name,
        _xiaotu_parse_feedback_entries=_xiaotu_parse_feedback_entries,
        _xiaotu_parse_like_user_names=_xiaotu_parse_like_user_names,
    )


def _xiaotu_card_feedback_text(feedback, expanded=False, preview_count=3):
    return _report_cards._xiaotu_card_feedback_text(
        feedback,
        expanded,
        preview_count,
        _xiaotu_clip_card_text=_xiaotu_clip_card_text,
        _xiaotu_enrich_feedback_data=_xiaotu_enrich_feedback_data,
    )


def _xiaotu_build_reply_target_options(feedback, owner_name=''):
    return _report_card_context._xiaotu_build_reply_target_options(
        feedback,
        owner_name,
        _xiaotu_enrich_feedback_data=_xiaotu_enrich_feedback_data,
    )


def _xiaotu_build_feedback_notice_markdown(action_name, actor_name, comment_text='', target_name=''):
    return _report_card_support._xiaotu_build_feedback_notice_markdown(
        action_name,
        actor_name,
        comment_text,
        target_name,
        _xiaotu_clip_card_text=_xiaotu_clip_card_text,
    )


def _xiaotu_get_report_card_context(wendangid):
    return _report_scope._xiaotu_get_report_card_context(
        wendangid,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        sf_db=sf_db,
    )


def _xiaotu_build_report_history_url(wendangid=''):
    return _report_card_context._xiaotu_build_report_history_url(
        wendangid,
        _XIAOTU_REPORT_CENTER_PUBLIC_URL=_XIAOTU_REPORT_CENTER_PUBLIC_URL,
        quote=quote,
        re=re,
        url_for=url_for,
        urlparse=urlparse,
    )


def _xiaotu_split_org_perf_from_pingjia(pingjia_text):
    return _report_card_context._xiaotu_split_org_perf_from_pingjia(pingjia_text, re=re)


def _xiaotu_build_report_notify_card(title_text, person_type, pingjia_text, doc_url="", source_text="", image_key="", image_paths_text="", wendangid="", comment_url="", report_url="", feedback_override=None, header_title="", header_template="blue", notice_markdown="", feedback_expanded=False, org_impact_text=""):
    return _report_cards._xiaotu_build_report_notify_card(
        title_text,
        person_type,
        pingjia_text,
        doc_url,
        source_text,
        image_key,
        image_paths_text,
        wendangid,
        comment_url,
        report_url,
        feedback_override,
        header_title,
        header_template,
        notice_markdown,
        feedback_expanded,
        org_impact_text,
        _xiaotu_build_card_source_elements=_xiaotu_build_card_source_elements,
        _xiaotu_build_reply_target_options=_xiaotu_build_reply_target_options,
        _xiaotu_build_report_history_url=_xiaotu_build_report_history_url,
        _xiaotu_card_feedback_text=_xiaotu_card_feedback_text,
        _xiaotu_clip_card_text=_xiaotu_clip_card_text,
        _xiaotu_enrich_feedback_data=_xiaotu_enrich_feedback_data,
        _xiaotu_get_report_card_context=_xiaotu_get_report_card_context,
        _xiaotu_get_report_feedback=_xiaotu_get_report_feedback,
        _xiaotu_split_org_perf_from_pingjia=_xiaotu_split_org_perf_from_pingjia,
        re=re,
    )


def _xiaotu_send_report_notification(receive_id, receive_id_type, title_text, person_type, pingjia_text, doc_url="", source_text="", image_key="", image_paths_text="", wendangid="", comment_url="", report_url="", org_impact_text=""):
    return _report_delivery._xiaotu_send_report_notification(
        receive_id,
        receive_id_type,
        title_text,
        person_type,
        pingjia_text,
        doc_url,
        source_text,
        image_key,
        image_paths_text,
        wendangid,
        comment_url,
        report_url,
        org_impact_text,
        _feishu_send_message_detail=_feishu_send_message_detail,
        _feishu_send_text=_feishu_send_text,
        _xiaotu_build_report_notify_card=_xiaotu_build_report_notify_card,
        _xiaotu_extract_plain_preview_text=_xiaotu_extract_plain_preview_text,
        _xiaotu_remember_report_card_message=_xiaotu_remember_report_card_message,
    )



def _xiaotu_find_first_key(obj, target_keys):
    return _report_card_context._xiaotu_find_first_key(
        obj,
        target_keys,
        _xiaotu_find_first_key=_xiaotu_find_first_key,
    )


def _xiaotu_get_card_action_payload(data):
    return _report_cards._xiaotu_get_card_action_payload(
        data,
        _xiaotu_find_first_key=_xiaotu_find_first_key,
    )








def _xiaotu_upsert_report_like(wendangid, user_name=''):
    return _report_feedback._xiaotu_upsert_report_like(
        wendangid,
        user_name,
        _xiaotu_build_like_user_text=_xiaotu_build_like_user_text,
        _xiaotu_parse_like_user_names=_xiaotu_parse_like_user_names,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        dui_db=dui_db,
        sf_db=sf_db,
    )


def _xiaotu_toggle_report_like(wendangid, user_name=''):
    return _report_feedback._xiaotu_toggle_report_like(
        wendangid,
        user_name,
        _xiaotu_build_like_user_text=_xiaotu_build_like_user_text,
        _xiaotu_parse_like_user_names=_xiaotu_parse_like_user_names,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        dui_db=dui_db,
        sf_db=sf_db,
    )


def _xiaotu_append_report_comment(wendangid, user_name, comment_text):
    return _report_feedback._xiaotu_append_report_comment(
        wendangid,
        user_name,
        comment_text,
        _xiaotu_feedback_entry_line=_xiaotu_feedback_entry_line,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        dui_db=dui_db,
    )


def _xiaotu_append_report_reply(wendangid, user_name, reply_text, target_name=''):
    return _report_feedback._xiaotu_append_report_reply(
        wendangid,
        user_name,
        reply_text,
        target_name,
        _xiaotu_feedback_entry_line=_xiaotu_feedback_entry_line,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        dui_db=dui_db,
    )


def _xiaotu_remove_report_feedback_entry(wendangid, user_name, entry_type, entry_index):
    return _report_feedback._xiaotu_remove_report_feedback_entry(
        wendangid,
        user_name,
        entry_type,
        entry_index,
        _report_persistence=_report_persistence,
        _xiaotu_feedback_entries_to_text=_xiaotu_feedback_entries_to_text,
        _xiaotu_parse_feedback_entries=_xiaotu_parse_feedback_entries,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        dui_db=dui_db,
        sf_db=sf_db,
    )


def _xiaotu_get_report_feedback(wendangid, owner_name=''):
    return _report_feedback._xiaotu_get_report_feedback(
        wendangid,
        owner_name,
        _report_persistence=_report_persistence,
        _xiaotu_enrich_feedback_data=_xiaotu_enrich_feedback_data,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        sf_db=sf_db,
    )


def _xiaotu_extract_comment_text(form_value):
    return _report_feedback._xiaotu_extract_comment_text(
        form_value,
        _xiaotu_extract_comment_text=_xiaotu_extract_comment_text,
    )


def _xiaotu_extract_reply_target_name(form_value):
    return _report_feedback._xiaotu_extract_reply_target_name(
        form_value,
        _xiaotu_extract_reply_target_name=_xiaotu_extract_reply_target_name,
    )


def _xiaotu_build_card_callback_response(card, toast_type, toast_content):
    return _report_feedback._xiaotu_build_card_callback_response(
        card,
        toast_type,
        toast_content,
        jsonify=jsonify,
    )


def _xiaotu_notify_report_owner_feedback(wendangid, action_name, actor_name, comment_text="", target_name=""):
    return _report_delivery._xiaotu_notify_report_owner_feedback(
        wendangid,
        action_name,
        actor_name,
        comment_text,
        target_name,
        _feishu_send_message_detail=_feishu_send_message_detail,
        _feishu_send_text=_feishu_send_text,
        _xiaotu_build_feedback_notice_markdown=_xiaotu_build_feedback_notice_markdown,
        _xiaotu_build_report_history_url=_xiaotu_build_report_history_url,
        _xiaotu_build_report_notify_card=_xiaotu_build_report_notify_card,
        _xiaotu_get_report_card_context=_xiaotu_get_report_card_context,
        _xiaotu_get_report_feedback=_xiaotu_get_report_feedback,
        _xiaotu_get_report_owner_open_id=_xiaotu_get_report_owner_open_id,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_remember_report_card_message=_xiaotu_remember_report_card_message,
    )



def _xiaotu_notify_feedback_reply_target(wendangid, actor_name, target_name, reply_text=""):
    return _report_delivery._xiaotu_notify_feedback_reply_target(
        wendangid,
        actor_name,
        target_name,
        reply_text,
        _feishu_send_message_detail=_feishu_send_message_detail,
        _feishu_send_text=_feishu_send_text,
        _xiaotu_build_feedback_notice_markdown=_xiaotu_build_feedback_notice_markdown,
        _xiaotu_build_report_history_url=_xiaotu_build_report_history_url,
        _xiaotu_build_report_notify_card=_xiaotu_build_report_notify_card,
        _xiaotu_get_report_card_context=_xiaotu_get_report_card_context,
        _xiaotu_get_report_feedback=_xiaotu_get_report_feedback,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_remember_report_card_message=_xiaotu_remember_report_card_message,
    )



def _xiaotu_notify_feedback_open_ids(wendangid, action_name, actor_name, comment_text="", target_name="", open_ids=None, skip_open_ids=None):
    return _report_delivery._xiaotu_notify_feedback_open_ids(
        wendangid,
        action_name,
        actor_name,
        comment_text,
        target_name,
        open_ids,
        skip_open_ids,
        _feishu_send_message_detail=_feishu_send_message_detail,
        _xiaotu_build_feedback_notice_markdown=_xiaotu_build_feedback_notice_markdown,
        _xiaotu_build_report_history_url=_xiaotu_build_report_history_url,
        _xiaotu_build_report_notify_card=_xiaotu_build_report_notify_card,
        _xiaotu_get_report_card_context=_xiaotu_get_report_card_context,
        _xiaotu_get_report_feedback=_xiaotu_get_report_feedback,
        _xiaotu_remember_report_card_message=_xiaotu_remember_report_card_message,
    )



def _xiaotu_finalize_report_card_feedback_async(wendangid, action_name, actor_name, target_message_id='', open_message_id='', operator_open_id='', reply_target_name='', comment_text='', feedback_expanded=False, doc_url='', image_key=''):
    return _report_delivery_routes._xiaotu_finalize_report_card_feedback_async(
        wendangid,
        action_name,
        actor_name,
        target_message_id,
        open_message_id,
        operator_open_id,
        reply_target_name,
        comment_text,
        feedback_expanded,
        doc_url,
        image_key,
        _feishu_recent_events=_feishu_recent_events,
        _feishu_recent_events_limit=_feishu_recent_events_limit,
        _feishu_update_message_card=_feishu_update_message_card,
        _xiaotu_build_report_history_url=_xiaotu_build_report_history_url,
        _xiaotu_build_report_notify_card=_xiaotu_build_report_notify_card,
        _xiaotu_get_report_card_context=_xiaotu_get_report_card_context,
        _xiaotu_get_report_card_message_ids=_xiaotu_get_report_card_message_ids,
        _xiaotu_get_report_card_receive_ids=_xiaotu_get_report_card_receive_ids,
        _xiaotu_get_report_feedback=_xiaotu_get_report_feedback,
        _xiaotu_get_report_owner_open_id=_xiaotu_get_report_owner_open_id,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_notify_feedback_open_ids=_xiaotu_notify_feedback_open_ids,
        _xiaotu_notify_feedback_reply_target=_xiaotu_notify_feedback_reply_target,
        _xiaotu_notify_report_owner_feedback=_xiaotu_notify_report_owner_feedback,
        _xiaotu_patch_related_report_cards=_xiaotu_patch_related_report_cards,
        datetime=datetime,
    )


def _xiaotu_handle_report_card_action(data):
    return _report_cards._xiaotu_handle_report_card_action(
        data,
        _feishu_recent_events=_feishu_recent_events,
        _feishu_recent_events_limit=_feishu_recent_events_limit,
        _feishu_submit_task=_feishu_submit_task,
        _feishu_update_message_card=_feishu_update_message_card,
        _xiaotu_append_report_comment=_xiaotu_append_report_comment,
        _xiaotu_append_report_reply=_xiaotu_append_report_reply,
        _xiaotu_build_card_callback_response=_xiaotu_build_card_callback_response,
        _xiaotu_build_report_history_url=_xiaotu_build_report_history_url,
        _xiaotu_build_report_notify_card=_xiaotu_build_report_notify_card,
        _xiaotu_extract_comment_text=_xiaotu_extract_comment_text,
        _xiaotu_extract_reply_target_name=_xiaotu_extract_reply_target_name,
        _xiaotu_finalize_report_card_feedback_async=_xiaotu_finalize_report_card_feedback_async,
        _xiaotu_get_card_action_payload=_xiaotu_get_card_action_payload,
        _xiaotu_get_report_card_context=_xiaotu_get_report_card_context,
        _xiaotu_get_report_card_message_id=_xiaotu_get_report_card_message_id,
        _xiaotu_get_report_feedback=_xiaotu_get_report_feedback,
        _xiaotu_resolve_card_actor_name=_xiaotu_resolve_card_actor_name,
        _xiaotu_upsert_report_like=_xiaotu_upsert_report_like,
        datetime=datetime,
    )


def _split_text(text, max_len=1500):
    return _feishu_chat_resources._split_text(text, max_len)


def _parse_forward_departments(prompt_text):
    return _department_forwarding._parse_forward_departments(prompt_text)


def _forward_text_to_departments(department_names, text):
    return _department_forwarding._forward_text_to_departments(
        department_names,
        text,
        MessageService=MessageService,
        _split_text=_split_text,
    )


def _feishu_parse_message_content(content):
    return _feishu_message_content._feishu_parse_message_content(content, json=json)


def _feishu_extract_image_keys(obj, limit=4):
    return _feishu_message_content._feishu_extract_image_keys(obj, limit)


def _feishu_download_resource(message_id, file_key, resource_type):
    return _feishu_message_content._feishu_download_resource(
        message_id,
        file_key,
        resource_type,
        permission_manager=permission_manager,
    )


def _generate_ai_answer_with_doc(prompt_text, doc_text, doc_name='', chat_id=None):
    return _feishu_answers._generate_ai_answer_with_doc(
        prompt_text,
        doc_text,
        doc_name,
        chat_id,
        _OPENAI_TEXT_MODEL_CANDIDATES=_OPENAI_TEXT_MODEL_CANDIDATES,
        _ai_chat_complete=_ai_chat_complete,
        _feishu_get_chat_history=_feishu_get_chat_history,
        _safe_debug_print=_safe_debug_print,
    )


def _generate_ai_answer_with_image(prompt_text, image_bytes, image_mime='', chat_id=None):
    return _feishu_answers._generate_ai_answer_with_image(
        prompt_text,
        image_bytes,
        image_mime,
        chat_id,
        _OPENAI_VISION_MODEL_CANDIDATES=_OPENAI_VISION_MODEL_CANDIDATES,
        _ai_chat_complete=_ai_chat_complete,
        _feishu_get_chat_history=_feishu_get_chat_history,
        _safe_debug_print=_safe_debug_print,
        base64=base64,
    )


def _ocr_images_bytes_with_ai(images):
    return _feishu_answers._ocr_images_bytes_with_ai(
        images,
        _OPENAI_VISION_MODEL_CANDIDATES=_OPENAI_VISION_MODEL_CANDIDATES,
        _ai_chat_complete=_ai_chat_complete,
        _safe_debug_print=_safe_debug_print,
        base64=base64,
    )

def _merge_system_content(base_system, extra_system):
    return _feishu_answers._merge_system_content(base_system, extra_system)


def _generate_ai_answer(question_text, chat_id=None, extra_system_content=''):
    return _feishu_answers._generate_ai_answer(
        question_text,
        chat_id,
        extra_system_content,
        _GOOGLE_CSE_API_KEY=_GOOGLE_CSE_API_KEY,
        _GOOGLE_CSE_CX=_GOOGLE_CSE_CX,
        _OPENAI_TEXT_MODEL_CANDIDATES=_OPENAI_TEXT_MODEL_CANDIDATES,
        _TAVILY_API_KEY=_TAVILY_API_KEY,
        _ai_chat_complete=_ai_chat_complete,
        _feishu_get_chat_history=_feishu_get_chat_history,
        _merge_system_content=_merge_system_content,
        _safe_debug_print=_safe_debug_print,
        os=os,
        requests=requests,
    )


def _async_generate_and_reply(chat_id, question_text):
    return _feishu_chat_flow._async_generate_and_reply(
        chat_id,
        question_text,
        _feishu_append_chat_history=_feishu_append_chat_history,
        _feishu_send_text_to_chat=_feishu_send_text_to_chat,
        _generate_ai_answer=_generate_ai_answer,
        _safe_debug_print=_safe_debug_print,
    )


def _async_generate_and_reply_with_skill(chat_id, question_text, skill_name, skill_detail):
    return _feishu_chat_flow._async_generate_and_reply_with_skill(
        chat_id,
        question_text,
        skill_name,
        skill_detail,
        _feishu_append_chat_history=_feishu_append_chat_history,
        _feishu_send_text_to_chat=_feishu_send_text_to_chat,
        _generate_ai_answer=_generate_ai_answer,
        _safe_debug_print=_safe_debug_print,
    )


def _prepress_visual_review(render_path, chat_id):
    return _feishu_chat_flow._prepress_visual_review(
        render_path,
        chat_id,
        _generate_ai_answer_with_image=_generate_ai_answer_with_image,
    )


def _feishu_send_prepress_report(chat_id, report):
    return _department_forwarding._feishu_send_prepress_report(
        chat_id,
        report,
        _feishu_send_text_to_chat=_feishu_send_text_to_chat,
    )


def _async_stage_prepress_resource(chat_id, message_id, resource_key, resource_type, file_name, run_after=False):
    return _feishu_chat_flow._async_stage_prepress_resource(
        chat_id,
        message_id,
        resource_key,
        resource_type,
        file_name,
        run_after,
        _async_run_prepress_check=_async_run_prepress_check,
        _feishu_download_resource=_feishu_download_resource,
        _feishu_send_text_to_chat=_feishu_send_text_to_chat,
        _safe_debug_print=_safe_debug_print,
        prepress_check_service=prepress_check_service,
    )


def _async_run_prepress_check(chat_id):
    return _feishu_chat_flow._async_run_prepress_check(
        chat_id,
        _feishu_append_chat_history=_feishu_append_chat_history,
        _feishu_send_prepress_report=_feishu_send_prepress_report,
        _feishu_send_text_to_chat=_feishu_send_text_to_chat,
        _prepress_visual_review=_prepress_visual_review,
        _safe_debug_print=_safe_debug_print,
        prepress_check_service=prepress_check_service,
    )


def _async_generate_and_reply_image(chat_id, question_text, message_id, image_key):
    return _feishu_chat_flow._async_generate_and_reply_image(
        chat_id,
        question_text,
        message_id,
        image_key,
        _feishu_append_chat_history=_feishu_append_chat_history,
        _feishu_download_resource=_feishu_download_resource,
        _feishu_send_text_to_chat=_feishu_send_text_to_chat,
        _generate_ai_answer_with_image=_generate_ai_answer_with_image,
    )


def _async_generate_and_reply_file(chat_id, question_text, message_id, file_key, file_name):
    return _feishu_chat_resources._async_generate_and_reply_file(
        chat_id,
        question_text,
        message_id,
        file_key,
        file_name,
        _feishu_append_chat_history=_feishu_append_chat_history,
        _feishu_download_resource=_feishu_download_resource,
        _feishu_send_text_to_chat=_feishu_send_text_to_chat,
        _generate_ai_answer_with_doc=_generate_ai_answer_with_doc,
        _generate_ai_answer_with_image=_generate_ai_answer_with_image,
    )


def _async_generate_and_reply_cloud_doc_qa(chat_id, question_text, doc_url):
    return _feishu_chat_flow._async_generate_and_reply_cloud_doc_qa(
        chat_id,
        question_text,
        doc_url,
        _feishu_append_chat_history=_feishu_append_chat_history,
        _feishu_send_text_to_chat=_feishu_send_text_to_chat,
        _generate_ai_answer_with_cloud_doc_url=_generate_ai_answer_with_cloud_doc_url,
    )


def _async_generate_and_reply_bitable(chat_id, question_text, bitable_url):
    return _feishu_chat_flow._async_generate_and_reply_bitable(
        chat_id,
        question_text,
        bitable_url,
        _feishu_append_chat_history=_feishu_append_chat_history,
        _feishu_send_text_to_chat=_feishu_send_text_to_chat,
        _generate_ai_answer_with_bitable_url=_generate_ai_answer_with_bitable_url,
    )


def _feishu_find_cloud_doc_url(text):
    return _feishu_message_content._feishu_find_cloud_doc_url(text, _get_cloud_documents_agent=_get_cloud_documents_agent)


def _feishu_find_cloud_doc_url_any(text):
    return _feishu_message_content._feishu_find_cloud_doc_url_any(text, _get_cloud_documents_agent=_get_cloud_documents_agent)


def _feishu_extract_urls_basic(text):
    return _feishu_message_content._feishu_extract_urls_basic(text, re=re)


def _feishu_find_bitable_url(text):
    return _feishu_bitable._feishu_find_bitable_url(text, _feishu_extract_urls_basic=_feishu_extract_urls_basic)


def _parse_bitable_url(url):
    return _feishu_bitable._parse_bitable_url(
        url,
        parse_qs=parse_qs,
        re=re,
        urlparse=urlparse,
    )


def _feishu_bitable_request(method, path, params=None):
    return _feishu_bitable._feishu_bitable_request(
        method,
        path,
        params,
        _feishu_http=_feishu_http,
        permission_manager=permission_manager,
    )


def _feishu_bitable_list_tables(app_token):
    return _feishu_bitable._feishu_bitable_list_tables(app_token, _feishu_bitable_request=_feishu_bitable_request)


def _feishu_bitable_list_fields(app_token, table_id):
    return _feishu_bitable._feishu_bitable_list_fields(
        app_token,
        table_id,
        _feishu_bitable_request=_feishu_bitable_request,
    )


def _feishu_bitable_list_records(app_token, table_id, view_id='', max_records=1200):
    return _feishu_bitable._feishu_bitable_list_records(
        app_token,
        table_id,
        view_id,
        max_records,
        _feishu_bitable_request=_feishu_bitable_request,
    )


def _bitable_value_to_text(v):
    return _feishu_bitable._bitable_value_to_text(v, json=json)


def _tokenize_loose(text):
    return _feishu_bitable._tokenize_loose(text, re=re)


def _build_bitable_context(question, url, app_token, table_id, table_name, view_id, fields, records):
    return _feishu_bitable._build_bitable_context(
        question,
        url,
        app_token,
        table_id,
        table_name,
        view_id,
        fields,
        records,
        _bitable_value_to_text=_bitable_value_to_text,
        _tokenize_loose=_tokenize_loose,
        json=json,
    )


def _generate_ai_answer_with_cloud_doc_url(question_text, doc_url, chat_id=None):
    return _feishu_answers._generate_ai_answer_with_cloud_doc_url(
        question_text,
        doc_url,
        chat_id,
        _generate_ai_answer_with_doc=_generate_ai_answer_with_doc,
        _get_cloud_documents_agent=_get_cloud_documents_agent,
    )


def _generate_ai_answer_with_bitable_url(question_text, bitable_url, chat_id=None):
    return _feishu_bitable._generate_ai_answer_with_bitable_url(
        question_text,
        bitable_url,
        chat_id,
        _bitable_cache=_bitable_cache,
        _bitable_cache_lock=_bitable_cache_lock,
        _bitable_cache_ttl_seconds=_bitable_cache_ttl_seconds,
        _build_bitable_context=_build_bitable_context,
        _feishu_bitable_list_fields=_feishu_bitable_list_fields,
        _feishu_bitable_list_records=_feishu_bitable_list_records,
        _feishu_bitable_list_tables=_feishu_bitable_list_tables,
        _generate_ai_answer_with_doc=_generate_ai_answer_with_doc,
        _parse_bitable_url=_parse_bitable_url,
        datetime=datetime,
    )


def _feishu_build_cloud_doc_url(doc_type, token):
    return _feishu_message_content._feishu_build_cloud_doc_url(
        doc_type,
        token,
        re=re,
    )


def _feishu_extract_cloud_doc_url_from_event(event_obj):
    return _feishu_message_content._feishu_extract_cloud_doc_url_from_event(
        event_obj,
        _feishu_build_cloud_doc_url=_feishu_build_cloud_doc_url,
        re=re,
    )


def _generate_cloud_doc_scoring(prompt_text, doc_url):
    return _feishu_answers._generate_cloud_doc_scoring(
        prompt_text,
        doc_url,
        _OPENAI_TEXT_MODEL_CANDIDATES=_OPENAI_TEXT_MODEL_CANDIDATES,
        _ai_chat_complete=_ai_chat_complete,
        _cloud_doc_scoring_cache=_cloud_doc_scoring_cache,
        _cloud_doc_scoring_cache_lock=_cloud_doc_scoring_cache_lock,
        _cloud_doc_scoring_cache_ttl_seconds=_cloud_doc_scoring_cache_ttl_seconds,
        _get_cloud_documents_agent=_get_cloud_documents_agent,
        datetime=datetime,
    )


def _feishu_plain_textify(text):
    return _feishu_message_content._feishu_plain_textify(text, re=re)


def _generate_cloud_doc_analysis(prompt_text, doc_url, chat_id=None):
    return _feishu_answers._generate_cloud_doc_analysis(
        prompt_text,
        doc_url,
        chat_id,
        _generate_ai_answer_with_cloud_doc_url=_generate_ai_answer_with_cloud_doc_url,
    )


def _async_generate_and_reply_cloud_doc(chat_id, prompt_text, doc_url):
    return _feishu_chat_flow._async_generate_and_reply_cloud_doc(
        chat_id,
        prompt_text,
        doc_url,
        _feishu_append_chat_history=_feishu_append_chat_history,
        _feishu_plain_textify=_feishu_plain_textify,
        _feishu_send_text_to_chat=_feishu_send_text_to_chat,
        _forward_text_to_departments=_forward_text_to_departments,
        _generate_cloud_doc_analysis=_generate_cloud_doc_analysis,
        _parse_forward_departments=_parse_forward_departments,
    )


def _extract_first_feishu_user_id(obj):
    return _feishu_message_content._extract_first_feishu_user_id(obj, _extract_first_feishu_user_id=_extract_first_feishu_user_id)


def _extract_all_text(obj, max_chars=20000):
    return _feishu_message_content._extract_all_text(obj, max_chars)


def _event_mentions_bot(event_obj):
    return _feishu_message_content._event_mentions_bot(
        event_obj,
        FEISHU_BOT_NAME=FEISHU_BOT_NAME,
        _extract_all_text=_extract_all_text,
    )


def _handle_feishu_cloud_doc_mention_event(data):
    return _feishu_events._handle_feishu_cloud_doc_mention_event(
        data,
        _extract_all_text=_extract_all_text,
        _extract_first_feishu_user_id=_extract_first_feishu_user_id,
        _feishu_build_cloud_doc_url=_feishu_build_cloud_doc_url,
        _feishu_extract_cloud_doc_url_from_event=_feishu_extract_cloud_doc_url_from_event,
        _feishu_find_bitable_url=_feishu_find_bitable_url,
        _feishu_find_cloud_doc_url_any=_feishu_find_cloud_doc_url_any,
        _feishu_is_event_processed=_feishu_is_event_processed,
        _feishu_mark_event_processed=_feishu_mark_event_processed,
        _feishu_send_text=_feishu_send_text,
        _generate_ai_answer_with_bitable_url=_generate_ai_answer_with_bitable_url,
        _generate_ai_answer_with_cloud_doc_url=_generate_ai_answer_with_cloud_doc_url,
        _generate_cloud_doc_analysis=_generate_cloud_doc_analysis,
        _get_cloud_documents_agent=_get_cloud_documents_agent,
        _split_text=_split_text,
        executor=executor,
        jsonify=jsonify,
        re=re,
    )


def handle_feishu_message_event(data):
    return _feishu_events.handle_feishu_message_event(
        data,
        _async_generate_and_reply=_async_generate_and_reply,
        _async_generate_and_reply_bitable=_async_generate_and_reply_bitable,
        _async_generate_and_reply_cloud_doc=_async_generate_and_reply_cloud_doc,
        _async_generate_and_reply_cloud_doc_qa=_async_generate_and_reply_cloud_doc_qa,
        _async_generate_and_reply_file=_async_generate_and_reply_file,
        _async_generate_and_reply_image=_async_generate_and_reply_image,
        _async_generate_and_reply_with_skill=_async_generate_and_reply_with_skill,
        _async_run_prepress_check=_async_run_prepress_check,
        _async_stage_prepress_resource=_async_stage_prepress_resource,
        _feishu_append_chat_history=_feishu_append_chat_history,
        _feishu_clean_question=_feishu_clean_question,
        _feishu_clear_chat_history=_feishu_clear_chat_history,
        _feishu_extract_image_keys=_feishu_extract_image_keys,
        _feishu_extract_reference_message_ids=_feishu_extract_reference_message_ids,
        _feishu_extract_text_from_content=_feishu_extract_text_from_content,
        _feishu_find_bitable_url=_feishu_find_bitable_url,
        _feishu_find_cloud_doc_url=_feishu_find_cloud_doc_url,
        _feishu_get_last_bot_ts=_feishu_get_last_bot_ts,
        _feishu_get_last_resource=_feishu_get_last_resource,
        _feishu_get_message_text=_feishu_get_message_text,
        _feishu_get_skill=_feishu_get_skill,
        _feishu_is_bot_mentioned=_feishu_is_bot_mentioned,
        _feishu_is_group_message=_feishu_is_group_message,
        _feishu_is_message_processed=_feishu_is_message_processed,
        _feishu_is_p2p_message=_feishu_is_p2p_message,
        _feishu_mark_message_processed=_feishu_mark_message_processed,
        _feishu_parse_message_content=_feishu_parse_message_content,
        _feishu_parse_skill_invocation=_feishu_parse_skill_invocation,
        _feishu_recent_events=_feishu_recent_events,
        _feishu_recent_events_limit=_feishu_recent_events_limit,
        _feishu_remember_image_resource=_feishu_remember_image_resource,
        _feishu_remember_resources=_feishu_remember_resources,
        _feishu_render_skill_list=_feishu_render_skill_list,
        _feishu_send_text_to_chat=_feishu_send_text_to_chat,
        _feishu_submit_task=_feishu_submit_task,
        datetime=datetime,
        jsonify=jsonify,
        os=os,
        prepress_check_service=prepress_check_service,
        secrets=secrets,
    )


def _feishu_try_decrypt_callback_data(data):
    return _feishu_events._feishu_try_decrypt_callback_data(
        data,
        _safe_debug_print=_safe_debug_print,
        json=json,
        permission_manager=permission_manager,
    )


@app.route('/')
def index():
    """主页 - 默认跳转到主控制台"""
    force_desktop = str(request.args.get('desktop') or '').strip() in {'1', 'true', 'yes'}
    if (not force_desktop) and _is_mobile_request():
        return redirect(url_for('dashboard_mobile'))
    return redirect(url_for('dashboard'))


def _build_dashboard_store_tier_index(snapshot):
    return _dashboard_routes._build_dashboard_store_tier_index(snapshot, normalize_person_name=normalize_person_name)


def _get_dashboard_store_tiers(user_name):
    return _dashboard_routes._get_dashboard_store_tiers(
        user_name,
        _BUSINESS_ANALYSIS_TIER_HISTORY_SNAPSHOT_PATH=_BUSINESS_ANALYSIS_TIER_HISTORY_SNAPSHOT_PATH,
        _build_dashboard_store_tier_index=_build_dashboard_store_tier_index,
        _dashboard_store_tier_cache=_dashboard_store_tier_cache,
        _dashboard_store_tier_cache_lock=_dashboard_store_tier_cache_lock,
        _safe_debug_print=_safe_debug_print,
        json=json,
        normalize_person_name=normalize_person_name,
        os=os,
    )


@app.route('/dashboard')
def dashboard():
    return _dashboard_routes.dashboard(
        _can_access_ai_workspace=_can_access_ai_workspace,
        _can_dashboard_switch_identity=_can_dashboard_switch_identity,
        _current_user_has_permission=_current_user_has_permission,
        _debug_log_elapsed=_debug_log_elapsed,
        _get_dashboard_store_tiers=_get_dashboard_store_tiers,
        _is_mobile_request=_is_mobile_request,
        _normalize_dashboard_functions=_normalize_dashboard_functions,
        _permission_debug_session_state=_permission_debug_session_state,
        _resolve_feishu_user_name=_resolve_feishu_user_name,
        _safe_debug_print=_safe_debug_print,
        _sync_feishu_identity_via_current_app=_sync_feishu_identity_via_current_app,
        dashboard_workspace_catalog=dashboard_workspace_catalog,
        datetime=datetime,
        permission_manager=permission_manager,
        redirect=redirect,
        render_template=render_template,
        request=request,
        session=session,
        time=time,
        url_for=url_for,
    )


@app.route('/dashboard/mobile')
def dashboard_mobile():
    return _dashboard_routes.dashboard_mobile(
        _build_mobile_function_cards=_build_mobile_function_cards,
        _debug_log_elapsed=_debug_log_elapsed,
        _permission_debug_session_state=_permission_debug_session_state,
        _resolve_feishu_user_name=_resolve_feishu_user_name,
        _sync_feishu_identity_via_current_app=_sync_feishu_identity_via_current_app,
        permission_manager=permission_manager,
        redirect=redirect,
        render_template=render_template,
        request=request,
        session=session,
        time=time,
        url_for=url_for,
    )


@app.route('/dashboard/xiaotu')
@require_permission('xiaotu_qa')
def dashboard_xiaotu():
    return _report_values.dashboard_xiaotu(
        _get_feishu_user_access_token=_get_feishu_user_access_token,
        redirect=redirect,
        render_template=render_template,
        session=session,
        url_for=url_for,
    )


@app.route('/dashboard/xiaotu-report-center')
@require_permission('xiaotu_qa')
def dashboard_xiaotu_report_center():
    return _report_editor_context.dashboard_xiaotu_report_center(
        _get_feishu_user_access_token=_get_feishu_user_access_token,
        _is_mobile_request=_is_mobile_request,
        redirect=redirect,
        render_template=render_template,
        request=request,
        session=session,
        url_for=url_for,
    )


@app.route('/dashboard/xiaotu-report-center-mobile')
@require_permission('xiaotu_qa')
def dashboard_xiaotu_report_center_mobile():
    return _report_editor_context.dashboard_xiaotu_report_center_mobile(
        _get_feishu_user_access_token=_get_feishu_user_access_token,
        redirect=redirect,
        render_template=render_template,
        request=request,
        session=session,
        url_for=url_for,
    )


@app.route('/dashboard/xiaotu-report-history')
@require_permission('xiaotu_qa')
def dashboard_xiaotu_report_history():
    return _report_document_pages.dashboard_xiaotu_report_history(
        _get_feishu_user_access_token=_get_feishu_user_access_token,
        _xiaotu_get_history_analysis_visible_user_names=_xiaotu_get_history_analysis_visible_user_names,
        _xiaotu_get_report_history_debug_options=_xiaotu_get_report_history_debug_options,
        _xiaotu_get_report_history_scope=_xiaotu_get_report_history_scope,
        redirect=redirect,
        render_template=render_template,
        request=request,
        session=session,
        url_for=url_for,
    )


@app.route('/xiaotu/report_comment', methods=['GET', 'POST'])
@require_permission('xiaotu_qa')
def xiaotu_report_comment_page():
    return _report_comment_pages.xiaotu_report_comment_page(
        _xiaotu_append_report_comment=_xiaotu_append_report_comment,
        _xiaotu_append_report_reply=_xiaotu_append_report_reply,
        _xiaotu_get_report_feedback=_xiaotu_get_report_feedback,
        _xiaotu_report_history_is_visible_to_user=_xiaotu_report_history_is_visible_to_user,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        redirect=redirect,
        render_template=render_template,
        request=request,
        session=session,
        sf_db=sf_db,
        url_for=url_for,
    )


@app.route('/api/xiaotu/report_delivery_status', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_delivery_status():
    return _report_delivery_routes.api_xiaotu_report_delivery_status(
        _xiaotu_get_report_delivery_status=_xiaotu_get_report_delivery_status,
        _xiaotu_get_report_row=_xiaotu_get_report_row,
        jsonify=jsonify,
        request=request,
        session=session,
    )


@app.route('/api/xiaotu/report_prepare_edit', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_prepare_edit():
    return _report_edit_routes.api_xiaotu_report_prepare_edit(
        _feishu_recall_message=_feishu_recall_message,
        _is_mobile_request=_is_mobile_request,
        _xiaotu_collect_report_card_message_entries=_xiaotu_collect_report_card_message_entries,
        _xiaotu_forget_report_card_messages=_xiaotu_forget_report_card_messages,
        _xiaotu_get_report_delivery_status=_xiaotu_get_report_delivery_status,
        _xiaotu_get_report_row=_xiaotu_get_report_row,
        _xiaotu_set_report_edit_ready_session=_xiaotu_set_report_edit_ready_session,
        jsonify=jsonify,
        request=request,
        session=session,
        url_for=url_for,
    )


@app.route('/api/xiaotu/report_edit_payload', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_edit_payload():
    return _report_edit_routes.api_xiaotu_report_edit_payload(
        _feishu_build_cloud_doc_url=_feishu_build_cloud_doc_url,
        _xiaotu_extract_source_doc_token=_xiaotu_extract_source_doc_token,
        _xiaotu_get_report_edit_ready_session=_xiaotu_get_report_edit_ready_session,
        _xiaotu_get_report_row=_xiaotu_get_report_row,
        _xiaotu_person_type_to_value=_xiaotu_person_type_to_value,
        _xiaotu_report_type_from_kind=_xiaotu_report_type_from_kind,
        _xiaotu_split_cache_multi_value=_xiaotu_split_cache_multi_value,
        jsonify=jsonify,
        re=re,
        request=request,
        session=session,
    )


@app.route('/api/xiaotu/moban', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_moban_list():
    return _report_editor_routes.api_xiaotu_moban_list(
        jsonify=jsonify,
        session=session,
        sf_db=sf_db,
    )


@app.route('/api/xiaotu/moban', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_moban_save():
    return _report_editor_routes.api_xiaotu_moban_save(
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        datetime=datetime,
        dui_db=dui_db,
        jsonify=jsonify,
        request=request,
        session=session,
    )


@app.route('/api/xiaotu/moban', methods=['DELETE'])
@require_permission('xiaotu_qa')
def api_xiaotu_moban_delete():
    return _report_editor_routes.api_xiaotu_moban_delete(
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        dui_db=dui_db,
        jsonify=jsonify,
        request=request,
        session=session,
    )


@app.route('/api/xiaotu/docs', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_docs():
    return _report_document_pages.api_xiaotu_docs(
        _clear_feishu_user_access_token=_clear_feishu_user_access_token,
        _get_feishu_user_access_token=_get_feishu_user_access_token,
        _xiaotu_extract_url_from_text=_xiaotu_extract_url_from_text,
        _xiaotu_get_doc_candidates_for_user=_xiaotu_get_doc_candidates_for_user,
        _xiaotu_need_reauth=_xiaotu_need_reauth,
        jsonify=jsonify,
        request=request,
        session=session,
        url_for=url_for,
    )


@app.route('/api/xiaotu/docs', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_add_doc():
    return _report_document_pages.api_xiaotu_add_doc(
        _feishu_find_cloud_doc_url_any=_feishu_find_cloud_doc_url_any,
        _get_cloud_documents_agent=_get_cloud_documents_agent,
        _xiaotu_extract_doc_token=_xiaotu_extract_doc_token,
        _xiaotu_get_user_saved_docs=_xiaotu_get_user_saved_docs,
        _xiaotu_set_user_saved_docs=_xiaotu_set_user_saved_docs,
        datetime=datetime,
        jsonify=jsonify,
        request=request,
        session=session,
    )


@app.route('/api/xiaotu/docs/<doc_id>', methods=['DELETE'])
@require_permission('xiaotu_qa')
def api_xiaotu_delete_doc(doc_id):
    return _report_values.api_xiaotu_delete_doc(
        doc_id,
        _xiaotu_get_user_saved_docs=_xiaotu_get_user_saved_docs,
        _xiaotu_set_user_saved_docs=_xiaotu_set_user_saved_docs,
        jsonify=jsonify,
        session=session,
    )


@app.route('/api/xiaotu/chat', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_chat():
    return _report_editor_routes.api_xiaotu_chat(
        _feishu_append_chat_history=_feishu_append_chat_history,
        _feishu_build_cloud_doc_url=_feishu_build_cloud_doc_url,
        _feishu_find_cloud_doc_url_any=_feishu_find_cloud_doc_url_any,
        _generate_ai_answer_with_cloud_doc_url=_generate_ai_answer_with_cloud_doc_url,
        _generate_cloud_doc_analysis=_generate_cloud_doc_analysis,
        _get_feishu_user_access_token=_get_feishu_user_access_token,
        _xiaotu_extract_doc_token=_xiaotu_extract_doc_token,
        _xiaotu_get_doc_candidates_for_user=_xiaotu_get_doc_candidates_for_user,
        datetime=datetime,
        jsonify=jsonify,
        request=request,
        session=session,
        url_for=url_for,
    )


@app.route('/api/xiaotu/report_cache', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_cache():
    return _report_editor_routes.api_xiaotu_report_cache(
        _xiaotu_get_report_cache=_xiaotu_get_report_cache,
        jsonify=jsonify,
        session=session,
    )


@app.route('/api/xiaotu/report_notify_config', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_notify_config():
    return _report_notification_pages.api_xiaotu_report_notify_config(
        _xiaotu_get_report_cache=_xiaotu_get_report_cache,
        _xiaotu_normalize_notify_time=_xiaotu_normalize_notify_time,
        _xiaotu_parse_notify_open_ids=_xiaotu_parse_notify_open_ids,
        _xiaotu_parse_notify_targets=_xiaotu_parse_notify_targets,
        _xiaotu_resolve_notify_names=_xiaotu_resolve_notify_names,
        _xiaotu_resolve_notify_open_ids=_xiaotu_resolve_notify_open_ids,
        _xiaotu_upsert_report_cache_notify=_xiaotu_upsert_report_cache_notify,
        jsonify=jsonify,
        request=request,
        session=session,
    )


@app.route('/api/xiaotu/report_test_reminder', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_test_reminder():
    return _report_notification_pages.api_xiaotu_report_test_reminder(
        _xiaotu_get_report_cache=_xiaotu_get_report_cache,
        _xiaotu_has_report_submitted_today=_xiaotu_has_report_submitted_today,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_normalize_notify_time=_xiaotu_normalize_notify_time,
        _xiaotu_send_missing_report_reminder=_xiaotu_send_missing_report_reminder,
        jsonify=jsonify,
        request=request,
        session=session,
    )


@app.route('/api/xiaotu/report_reminder_logs', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_reminder_logs():
    return _report_notification_pages.api_xiaotu_report_reminder_logs(
        _xiaotu_report_reminder_lock=_xiaotu_report_reminder_lock,
        _xiaotu_report_reminder_logs=_xiaotu_report_reminder_logs,
        _xiaotu_report_reminder_sent_marks=_xiaotu_report_reminder_sent_marks,
        _xiaotu_report_reminder_thread_started=_xiaotu_report_reminder_thread_started,
        _xiaotu_user_open_id_cache=_xiaotu_user_open_id_cache,
        jsonify=jsonify,
        os=os,
        request=request,
    )


@app.route('/api/xiaotu/report_draft', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_draft():
    return _report_editor_routes.api_xiaotu_report_draft(
        _get_cloud_documents_agent=_get_cloud_documents_agent,
        _xiaotu_compact_report_body_for_storage=_xiaotu_compact_report_body_for_storage,
        _xiaotu_extract_report_image_paths_from_html=_xiaotu_extract_report_image_paths_from_html,
        _xiaotu_get_report_cache=_xiaotu_get_report_cache,
        _xiaotu_normalize_notify_time=_xiaotu_normalize_notify_time,
        _xiaotu_parse_notify_open_ids=_xiaotu_parse_notify_open_ids,
        _xiaotu_parse_notify_targets=_xiaotu_parse_notify_targets,
        _xiaotu_replace_html_img_src_with_paths=_xiaotu_replace_html_img_src_with_paths,
        _xiaotu_resolve_notify_names=_xiaotu_resolve_notify_names,
        _xiaotu_resolve_notify_open_ids=_xiaotu_resolve_notify_open_ids,
        _xiaotu_save_inline_html_images_and_ocr_safe=_xiaotu_save_inline_html_images_and_ocr_safe,
        _xiaotu_save_remote_html_images_and_ocr_safe=_xiaotu_save_remote_html_images_and_ocr_safe,
        _xiaotu_save_uploaded_images_and_ocr_safe=_xiaotu_save_uploaded_images_and_ocr_safe,
        _xiaotu_upsert_report_cache_draft=_xiaotu_upsert_report_cache_draft,
        _xiaotu_upsert_report_cache_notify=_xiaotu_upsert_report_cache_notify,
        datetime=datetime,
        jsonify=jsonify,
        relocate_storage_path=relocate_storage_path,
        request=request,
        session=session,
    )


@app.route('/api/xiaotu/report_submit', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_submit():
    return _report_submission.api_xiaotu_report_submit(
        RequestEntityTooLarge=RequestEntityTooLarge,
        Thread=Thread,
        _XIAOTU_REPORT_ESCALATION_USER=_XIAOTU_REPORT_ESCALATION_USER,
        _feishu_upload_image_by_path_safe=_feishu_upload_image_by_path_safe,
        _generate_ai_answer_with_doc=_generate_ai_answer_with_doc,
        _get_cloud_documents_agent=_get_cloud_documents_agent,
        _get_feishu_user_access_token=_get_feishu_user_access_token,
        _safe_debug_print=_safe_debug_print,
        _xiaotu_build_report_history_url=_xiaotu_build_report_history_url,
        _xiaotu_build_report_instance_id=_xiaotu_build_report_instance_id,
        _xiaotu_build_report_title=_xiaotu_build_report_title,
        _xiaotu_clear_report_cache_draft=_xiaotu_clear_report_cache_draft,
        _xiaotu_clear_report_edit_ready_session=_xiaotu_clear_report_edit_ready_session,
        _xiaotu_compact_report_body_for_storage=_xiaotu_compact_report_body_for_storage,
        _xiaotu_count_daily_date_headings=_xiaotu_count_daily_date_headings,
        _xiaotu_detect_report_kind=_xiaotu_detect_report_kind,
        _xiaotu_extract_doc_token=_xiaotu_extract_doc_token,
        _xiaotu_extract_source_doc_token=_xiaotu_extract_source_doc_token,
        _xiaotu_find_last_daily_date_start=_xiaotu_find_last_daily_date_start,
        _xiaotu_generate_org_perf_contribution=_xiaotu_generate_org_perf_contribution,
        _xiaotu_get_department_leader_user_id=_xiaotu_get_department_leader_user_id,
        _xiaotu_get_report_edit_ready_session=_xiaotu_get_report_edit_ready_session,
        _xiaotu_get_report_row=_xiaotu_get_report_row,
        _xiaotu_guess_title=_xiaotu_guess_title,
        _xiaotu_html_to_plain_text_preserve_blocks=_xiaotu_html_to_plain_text_preserve_blocks,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_lookup_org_perf_context=_xiaotu_lookup_org_perf_context,
        _xiaotu_normalize_notify_time=_xiaotu_normalize_notify_time,
        _xiaotu_parse_notify_open_ids=_xiaotu_parse_notify_open_ids,
        _xiaotu_parse_notify_targets=_xiaotu_parse_notify_targets,
        _xiaotu_person_focus_text=_xiaotu_person_focus_text,
        _xiaotu_person_type_from_value=_xiaotu_person_type_from_value,
        _xiaotu_pick_doc_for_request=_xiaotu_pick_doc_for_request,
        _xiaotu_pick_primary_department=_xiaotu_pick_primary_department,
        _xiaotu_query_user_names_by_open_ids=_xiaotu_query_user_names_by_open_ids,
        _xiaotu_read_report_memory_context=_xiaotu_read_report_memory_context,
        _xiaotu_remember_report_owner_open_id=_xiaotu_remember_report_owner_open_id,
        _xiaotu_replace_html_img_src_with_paths=_xiaotu_replace_html_img_src_with_paths,
        _xiaotu_report_kind_from_type=_xiaotu_report_kind_from_type,
        _xiaotu_resolve_notify_names=_xiaotu_resolve_notify_names,
        _xiaotu_resolve_notify_open_ids=_xiaotu_resolve_notify_open_ids,
        _xiaotu_resolve_redirect_url=_xiaotu_resolve_redirect_url,
        _xiaotu_save_doc_images_and_ocr_safe=_xiaotu_save_doc_images_and_ocr_safe,
        _xiaotu_save_inline_html_images_and_ocr_safe=_xiaotu_save_inline_html_images_and_ocr_safe,
        _xiaotu_save_remote_html_images_and_ocr_safe=_xiaotu_save_remote_html_images_and_ocr_safe,
        _xiaotu_save_uploaded_images_and_ocr_safe=_xiaotu_save_uploaded_images_and_ocr_safe,
        _xiaotu_send_report_notification=_xiaotu_send_report_notification,
        _xiaotu_slice_daily_doc_content=_xiaotu_slice_daily_doc_content,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        _xiaotu_update_report_memory=_xiaotu_update_report_memory,
        _xiaotu_upsert_report_cache_notify=_xiaotu_upsert_report_cache_notify,
        app=app,
        datetime=datetime,
        dui_db=dui_db,
        jsonify=jsonify,
        request=request,
        session=session,
        url_for=url_for,
    )



@app.route('/api/xiaotu/report_history', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_history():
    return _report_history_routes.api_xiaotu_report_history(
        _current_user_has_permission=_current_user_has_permission,
        _xiaotu_build_name_match_clause=_xiaotu_build_name_match_clause,
        _xiaotu_build_report_history_url=_xiaotu_build_report_history_url,
        _xiaotu_collect_notify_user_names_by_department_names=_xiaotu_collect_notify_user_names_by_department_names,
        _xiaotu_enrich_feedback_data=_xiaotu_enrich_feedback_data,
        _xiaotu_extract_source_doc_token=_xiaotu_extract_source_doc_token,
        _xiaotu_get_report_history_scope=_xiaotu_get_report_history_scope,
        _xiaotu_list_notify_departments=_xiaotu_list_notify_departments,
        _xiaotu_list_notify_users_current_app_cached=_xiaotu_list_notify_users_current_app_cached,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        datetime=datetime,
        jsonify=jsonify,
        request=request,
        session=session,
        sf_db=sf_db,
    )


def _xiaotu_build_report_history_export_context(args, session_user_name):
    return _report_edit_routes._xiaotu_build_report_history_export_context(
        args,
        session_user_name,
        _current_user_has_permission=_current_user_has_permission,
        _xiaotu_build_name_match_clause=_xiaotu_build_name_match_clause,
        _xiaotu_collect_notify_user_names_by_department_names=_xiaotu_collect_notify_user_names_by_department_names,
        _xiaotu_get_report_history_scope=_xiaotu_get_report_history_scope,
        _xiaotu_list_notify_departments=_xiaotu_list_notify_departments,
        _xiaotu_list_notify_users_current_app_cached=_xiaotu_list_notify_users_current_app_cached,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        datetime=datetime,
    )


def _xiaotu_report_history_is_visible_to_user(wendangid, user_name):
    return _report_persistence._xiaotu_report_history_is_visible_to_user(
        wendangid,
        user_name,
        _xiaotu_build_report_history_export_context=_xiaotu_build_report_history_export_context,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        sf_db=sf_db,
    )






def _xiaotu_history_export_body_html(raw_body, image_paths_text, image_cache=None):
    return _report_export_views._xiaotu_history_export_body_html(
        raw_body,
        image_paths_text,
        image_cache,
        _xiaotu_history_export_image_data_uri=_xiaotu_history_export_image_data_uri,
        _xiaotu_normalize_report_html_body=_xiaotu_normalize_report_html_body,
        html_escape=html_escape,
        html_unescape=html_unescape,
        re=re,
    )








def _xiaotu_build_history_export_html(session_user_name, ctx, rows_uploaded, rows_received):
    return _report_export_views._xiaotu_build_history_export_html(
        session_user_name,
        ctx,
        rows_uploaded,
        rows_received,
        _xiaotu_history_export_body_html=_xiaotu_history_export_body_html,
        export_html=export_html,
    )


@app.route('/api/xiaotu/report_history_download', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_history_download():
    return _report_history_routes.api_xiaotu_report_history_download(
        _xiaotu_build_history_export_html=_xiaotu_build_history_export_html,
        _xiaotu_build_report_history_export_context=_xiaotu_build_report_history_export_context,
        datetime=datetime,
        jsonify=jsonify,
        re=re,
        request=request,
        send_file=send_file,
        session=session,
        sf_db=sf_db,
    )


@app.route('/api/xiaotu/report_feedback', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_feedback():
    return _report_delivery_routes.api_xiaotu_report_feedback(
        _feishu_recent_events=_feishu_recent_events,
        _feishu_recent_events_limit=_feishu_recent_events_limit,
        _xiaotu_append_report_comment=_xiaotu_append_report_comment,
        _xiaotu_append_report_reply=_xiaotu_append_report_reply,
        _xiaotu_get_report_card_context=_xiaotu_get_report_card_context,
        _xiaotu_get_report_feedback=_xiaotu_get_report_feedback,
        _xiaotu_notify_feedback_reply_target=_xiaotu_notify_feedback_reply_target,
        _xiaotu_notify_report_owner_feedback=_xiaotu_notify_report_owner_feedback,
        _xiaotu_remove_report_feedback_entry=_xiaotu_remove_report_feedback_entry,
        _xiaotu_report_history_is_visible_to_user=_xiaotu_report_history_is_visible_to_user,
        _xiaotu_toggle_report_like=_xiaotu_toggle_report_like,
        datetime=datetime,
        jsonify=jsonify,
        request=request,
        session=session,
    )


@app.route('/api/xiaotu/report_image', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_image():
    return _report_notification_pages.api_xiaotu_report_image(
        jsonify=jsonify,
        os=os,
        parse_qs=parse_qs,
        relocate_storage_path=relocate_storage_path,
        request=request,
        send_file=send_file,
        unquote=unquote,
        urlparse=urlparse,
    )


@app.route('/api/xiaotu/report_history_analysis_file', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_history_analysis_file():
    return _report_history_routes.api_xiaotu_report_history_analysis_file(
        _XIAOTU_REPORT_HISTORY_ANALYSIS_DIR=_XIAOTU_REPORT_HISTORY_ANALYSIS_DIR,
        _xiaotu_build_name_scope_clause=_xiaotu_build_name_scope_clause,
        _xiaotu_get_history_analysis_visible_user_names=_xiaotu_get_history_analysis_visible_user_names,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        jsonify=jsonify,
        os=os,
        relocate_storage_path=relocate_storage_path,
        request=request,
        send_file=send_file,
        session=session,
        sf_db=sf_db,
        unquote=unquote,
    )


@app.route('/api/xiaotu/report_history_analysis_list', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_report_history_analysis_list():
    return _report_history_routes.api_xiaotu_report_history_analysis_list(
        _xiaotu_build_name_scope_clause=_xiaotu_build_name_scope_clause,
        _xiaotu_get_history_analysis_visible_user_names=_xiaotu_get_history_analysis_visible_user_names,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        jsonify=jsonify,
        os=os,
        relocate_storage_path=relocate_storage_path,
        session=session,
        sf_db=sf_db,
        url_for=url_for,
    )


@app.route('/api/xiaotu/knowledge_search', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_knowledge_search():
    return _report_analysis_routes.api_xiaotu_knowledge_search(
        _generate_ai_answer_with_doc=_generate_ai_answer_with_doc,
        _xiaotu_extract_knowledge_terms=_xiaotu_extract_knowledge_terms,
        _xiaotu_render_knowledge_source_text=_xiaotu_render_knowledge_source_text,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        datetime=datetime,
        jsonify=jsonify,
        re=re,
        request=request,
        session=session,
        sf_db=sf_db,
    )


@app.route('/api/xiaotu/daily_from_im', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_daily_from_im():
    return _report_im_submission.api_xiaotu_daily_from_im(
        _clear_feishu_user_access_token=_clear_feishu_user_access_token,
        _feishu_http=_feishu_http,
        _generate_ai_answer_with_doc=_generate_ai_answer_with_doc,
        _get_feishu_user_access_token=_get_feishu_user_access_token,
        _xiaotu_format_message_time=_xiaotu_format_message_time,
        _xiaotu_get_message_text_for_daily_ref=_xiaotu_get_message_text_for_daily_ref,
        _xiaotu_get_sender_open_id_from_message=_xiaotu_get_sender_open_id_from_message,
        datetime=datetime,
        jsonify=jsonify,
        request=request,
        session=session,
        url_for=url_for,
    )


@app.route('/api/ai/xiaotu/period_report', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_period_report():
    return _report_analysis_routes.api_xiaotu_period_report(
        Thread=Thread,
        _generate_ai_answer_with_doc=_generate_ai_answer_with_doc,
        _safe_debug_print=_safe_debug_print,
        _xiaotu_build_history_analysis_html=_xiaotu_build_history_analysis_html,
        _xiaotu_build_name_match_clause=_xiaotu_build_name_match_clause,
        _xiaotu_build_name_scope_clause=_xiaotu_build_name_scope_clause,
        _xiaotu_get_history_analysis_visible_user_names=_xiaotu_get_history_analysis_visible_user_names,
        _xiaotu_get_period_range=_xiaotu_get_period_range,
        _xiaotu_parse_date_value=_xiaotu_parse_date_value,
        _xiaotu_render_period_source_text=_xiaotu_render_period_source_text,
        _xiaotu_save_history_analysis_file=_xiaotu_save_history_analysis_file,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        app=app,
        datetime=datetime,
        dui_db=dui_db,
        hashlib=hashlib,
        jsonify=jsonify,
        request=request,
        session=session,
        sf_db=sf_db,
        time=time,
    )


@app.route('/api/xiaotu/notify_targets_preview', methods=['POST'])
@require_permission('xiaotu_qa')
def api_xiaotu_notify_targets_preview():
    return _report_notify_directory.api_xiaotu_notify_targets_preview(
        _XIAOTU_REPORT_ESCALATION_USER=_XIAOTU_REPORT_ESCALATION_USER,
        _xiaotu_get_department_leader_user_id=_xiaotu_get_department_leader_user_id,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_pick_primary_department=_xiaotu_pick_primary_department,
        jsonify=jsonify,
        request=request,
        session=session,
    )


@app.route('/api/xiaotu/notify/departments', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_notify_departments():
    return _report_notify_directory.api_xiaotu_notify_departments(
        _xiaotu_list_notify_departments=_xiaotu_list_notify_departments,
        jsonify=jsonify,
        permission_manager=permission_manager,
        session=session,
    )


@app.route('/api/xiaotu/notify/users', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_notify_users():
    return _report_notify_directory.api_xiaotu_notify_users(
        _xiaotu_list_notify_users_current_app=_xiaotu_list_notify_users_current_app,
        jsonify=jsonify,
        request=request,
        session=session,
    )


@app.route('/api/xiaotu/notify/search', methods=['GET'])
@require_permission('xiaotu_qa')
def api_xiaotu_notify_search():
    return _report_notify_directory.api_xiaotu_notify_search(
        _xiaotu_search_notify_users=_xiaotu_search_notify_users,
        jsonify=jsonify,
        request=request,
        session=session,
    )


def _annual_moments_file_size_label(size_bytes):
    return _training_media._annual_moments_file_size_label(size_bytes)


def _collect_annual_moment_files(folder, extensions, endpoint):
    return _training_media._collect_annual_moment_files(
        folder,
        extensions,
        endpoint,
        _annual_moments_file_size_label=_annual_moments_file_size_label,
        datetime=datetime,
        os=os,
        url_for=url_for,
    )


def _send_annual_moment_file(root_folder, relpath, allowed_extensions):
    return _training_media._send_annual_moment_file(
        root_folder,
        relpath,
        allowed_extensions,
        os=os,
        redirect=redirect,
        send_from_directory=send_from_directory,
        session=session,
        url_for=url_for,
    )


@app.route('/annual_moments')
def annual_moments():
    return _training_media.annual_moments(
        _ANNUAL_MOMENTS_IMAGE_DIR=_ANNUAL_MOMENTS_IMAGE_DIR,
        _ANNUAL_MOMENTS_VIDEO_DIR=_ANNUAL_MOMENTS_VIDEO_DIR,
        _IMAGE_EXTENSIONS=_IMAGE_EXTENSIONS,
        _VIDEO_EXTENSIONS=_VIDEO_EXTENSIONS,
        _collect_annual_moment_files=_collect_annual_moment_files,
        os=os,
        redirect=redirect,
        render_template=render_template,
        session=session,
        url_for=url_for,
    )


@app.route('/annual_moments/images/<path:relpath>')
def annual_moment_image_file(relpath):
    return _training_media.annual_moment_image_file(
        relpath,
        _ANNUAL_MOMENTS_IMAGE_DIR=_ANNUAL_MOMENTS_IMAGE_DIR,
        _IMAGE_EXTENSIONS=_IMAGE_EXTENSIONS,
        _send_annual_moment_file=_send_annual_moment_file,
    )


@app.route('/annual_moments/videos/<path:relpath>')
def annual_moment_video_file(relpath):
    return _training_media.annual_moment_video_file(
        relpath,
        _ANNUAL_MOMENTS_VIDEO_DIR=_ANNUAL_MOMENTS_VIDEO_DIR,
        _VIDEO_EXTENSIONS=_VIDEO_EXTENSIONS,
        _send_annual_moment_file=_send_annual_moment_file,
    )


@app.route('/training_videos')
def training_videos():
    return _training_media.training_videos(
        redirect=redirect,
        render_template=render_template,
        session=session,
        url_for=url_for,
    )


@app.route('/training_videos/chuanshi')
def chuanshi_training():
    return _training_media.chuanshi_training(
        _CHUANSHI_TRAINING_IMAGE_DIR=_CHUANSHI_TRAINING_IMAGE_DIR,
        _CHUANSHI_TRAINING_VIDEO_DIR=_CHUANSHI_TRAINING_VIDEO_DIR,
        _IMAGE_EXTENSIONS=_IMAGE_EXTENSIONS,
        _VIDEO_EXTENSIONS=_VIDEO_EXTENSIONS,
        _collect_annual_moment_files=_collect_annual_moment_files,
        os=os,
        redirect=redirect,
        render_template=render_template,
        session=session,
        url_for=url_for,
    )


@app.route('/training_videos/chuanshi/images/<path:relpath>')
def chuanshi_training_image_file(relpath):
    return _training_media.chuanshi_training_image_file(
        relpath,
        _CHUANSHI_TRAINING_IMAGE_DIR=_CHUANSHI_TRAINING_IMAGE_DIR,
        _IMAGE_EXTENSIONS=_IMAGE_EXTENSIONS,
        _send_annual_moment_file=_send_annual_moment_file,
    )


@app.route('/training_videos/chuanshi/videos/<path:relpath>')
def chuanshi_training_video_file(relpath):
    return _training_media.chuanshi_training_video_file(
        relpath,
        _CHUANSHI_TRAINING_VIDEO_DIR=_CHUANSHI_TRAINING_VIDEO_DIR,
        _VIDEO_EXTENSIONS=_VIDEO_EXTENSIONS,
        _send_annual_moment_file=_send_annual_moment_file,
    )


@app.route('/training_videos/strategy')
def strategy_training_videos():
    return _training_media.strategy_training_videos(
        _STRATEGY_TRAINING_VIDEO_DIR=_STRATEGY_TRAINING_VIDEO_DIR,
        _VIDEO_EXTENSIONS=_VIDEO_EXTENSIONS,
        os=os,
        redirect=redirect,
        render_template=render_template,
        session=session,
        url_for=url_for,
    )


@app.route('/training_videos/strategy/files/<path:filename>')
def strategy_training_video_file(filename):
    return _training_media.strategy_training_video_file(
        filename,
        _STRATEGY_TRAINING_VIDEO_DIR=_STRATEGY_TRAINING_VIDEO_DIR,
        _VIDEO_EXTENSIONS=_VIDEO_EXTENSIONS,
        os=os,
        redirect=redirect,
        send_from_directory=send_from_directory,
        session=session,
        url_for=url_for,
    )


@app.route('/training_videos/strategy/files/<path:folder>/<path:filename>')
def strategy_training_video_file_in_folder(folder, filename):
    return _training_media.strategy_training_video_file_in_folder(
        folder,
        filename,
        _STRATEGY_TRAINING_VIDEO_DIR=_STRATEGY_TRAINING_VIDEO_DIR,
        _VIDEO_EXTENSIONS=_VIDEO_EXTENSIONS,
        os=os,
        redirect=redirect,
        send_from_directory=send_from_directory,
        session=session,
        url_for=url_for,
    )


@app.route('/training_videos/strategy/files/tree/<path:relpath>')
def strategy_training_video_file_by_path(relpath):
    return _training_media.strategy_training_video_file_by_path(
        relpath,
        _STRATEGY_TRAINING_VIDEO_DIR=_STRATEGY_TRAINING_VIDEO_DIR,
        _VIDEO_EXTENSIONS=_VIDEO_EXTENSIONS,
        os=os,
        redirect=redirect,
        send_from_directory=send_from_directory,
        session=session,
        url_for=url_for,
    )


@app.route('/training_videos/rococo')
def rococo_training_videos():
    return _training_media.rococo_training_videos(
        _ROCOCO_TRAINING_VIDEO_DIR=_ROCOCO_TRAINING_VIDEO_DIR,
        _VIDEO_EXTENSIONS=_VIDEO_EXTENSIONS,
        os=os,
        render_template=render_template,
        url_for=url_for,
    )


@app.route('/training_videos/rococo/files/<path:folder>/<path:filename>')
def rococo_training_video_file(folder, filename):
    return _training_media.rococo_training_video_file(
        folder,
        filename,
        _ROCOCO_TRAINING_VIDEO_DIR=_ROCOCO_TRAINING_VIDEO_DIR,
        _VIDEO_EXTENSIONS=_VIDEO_EXTENSIONS,
        os=os,
        send_from_directory=send_from_directory,
    )


@app.route('/training_videos/rococo/files/tree/<path:relpath>')
def rococo_training_video_file_by_path(relpath):
    return _training_media.rococo_training_video_file_by_path(
        relpath,
        _ROCOCO_TRAINING_VIDEO_DIR=_ROCOCO_TRAINING_VIDEO_DIR,
        _VIDEO_EXTENSIONS=_VIDEO_EXTENSIONS,
        os=os,
        send_from_directory=send_from_directory,
    )


@app.route('/api/menu_click', methods=['POST'])
def api_menu_click():
    return _department_entry_pages.api_menu_click(
        dui_db=dui_db,
        jsonify=jsonify,
        request=request,
        session=session,
    )


@app.route('/api/dashboard/favorites/context', methods=['GET'])
def api_dashboard_favorites_context():
    return _department_entry_pages.api_dashboard_favorites_context(
        _permission_debug_effective_state=_permission_debug_effective_state,
        jsonify=jsonify,
        session=session,
    )


@app.route('/api/dashboard/workspace/catalog')
def dashboard_workspace_catalog(accessible=None):
    return _workspace_routes.dashboard_workspace_catalog(
        accessible,
        _OPERATION_DEPT_FUNCTIONS=_OPERATION_DEPT_FUNCTIONS,
        _can_access_ai_workspace=_can_access_ai_workspace,
        _normalize_dashboard_functions=_normalize_dashboard_functions,
        _permission_debug_effective_state=_permission_debug_effective_state,
        app=app,
        jsonify=jsonify,
        permission_manager=permission_manager,
        render_template=render_template,
        session=session,
        url_for=url_for,
    )


@app.route('/performance')
@require_permission('performance_monitor')
def performance_monitor():
    return _ai_catalog_pages.performance_monitor(
        app=app,
        get_feishu_auth_url=get_feishu_auth_url,
        redirect=redirect,
        render_template=render_template,
        session=session,
    )


@app.route('/script_generator')
@require_permission('script_generator')
def script_generator():
    return _content_generation_routes.script_generator(render_template=render_template)


@app.route('/generate_script', methods=['POST'])
@require_permission('script_generator')
def generate_script():
    return _content_generation_routes.generate_script(
        _safe_debug_print=_safe_debug_print,
        call_ai_api=call_ai_api,
        concurrent=concurrent,
        jsonify=jsonify,
        request=request,
    )


@app.route('/admin_dashboard')
@require_permission('admin_functions')
def admin_dashboard():
    return _ai_catalog_pages.admin_dashboard(render_template=render_template)


@app.route('/tk_project')
@require_permission('tk_project_group')
def tk_project():
    return _content_factory_entry_pages.tk_project(
        _safe_debug_print=_safe_debug_print,
        get_joint_dashboard_allowed_shops=get_joint_dashboard_allowed_shops,
        permission_manager=permission_manager,
        render_template=render_template,
        session=session,
    )


@app.route('/tk_seedance')
def tk_seedance():
    return _content_factory_entry_pages.tk_seedance(
        _current_user_has_permission=_current_user_has_permission,
        redirect=redirect,
        url_for=url_for,
    )


@app.route('/tk_customer_service')
@require_permission('tk_customer_service')
def tk_customer_service():
    return _tk_customer_service_routes.tk_customer_service(
        datetime=datetime,
        render_template=render_template,
        request=request,
        session=session,
        timedelta=timedelta,
    )








def _tk_extract_state_zip_tail(text):
    return _tk_customer_service_routes._tk_extract_state_zip_tail(text, re=re)


def _tk_extract_us_zip_anywhere(text):
    return _tk_customer_service_routes._tk_extract_us_zip_anywhere(text, re=re)




def _tk_fallback_parse_us_address(raw_text, existing_phone=''):
    return _tk_customer_service_routes._tk_fallback_parse_us_address(
        raw_text,
        existing_phone,
        _tk_extract_us_state_with_span=_tk_extract_us_state_with_span,
        _tk_extract_us_zip_anywhere=_tk_extract_us_zip_anywhere,
        _tk_guess_city_from_tail=_tk_guess_city_from_tail,
        _tk_split_street_city=_tk_split_street_city,
        re=re,
    )






def _tk_parse_wanghong_address(raw_address):
    return _tk_customer_service_routes._tk_parse_wanghong_address(
        raw_address,
        _tk_country_to_iso2=_tk_country_to_iso2,
        _tk_extract_state_zip_tail=_tk_extract_state_zip_tail,
        _tk_extract_us_state_with_span=_tk_extract_us_state_with_span,
        _tk_extract_us_zip_anywhere=_tk_extract_us_zip_anywhere,
        _tk_extract_zip_and_country=_tk_extract_zip_and_country,
        _tk_fallback_parse_us_address=_tk_fallback_parse_us_address,
        _tk_guess_city_from_street_tail=_tk_guess_city_from_street_tail,
        _tk_guess_city_from_tail=_tk_guess_city_from_tail,
        _tk_split_street_city=_tk_split_street_city,
        re=re,
    )


def _tk_validate_export_address(raw_address, parsed, order_no):
    return _tk_customer_service_routes._tk_validate_export_address(
        raw_address,
        parsed,
        order_no,
    )






def _tk_normalize_export_country(country_text):
    return _tk_customer_service_routes._tk_normalize_export_country(country_text, _tk_country_to_iso2=_tk_country_to_iso2)






def _tk_prepare_export_contact_fields(raw_address, parsed):
    return _tk_customer_service_routes._tk_prepare_export_contact_fields(
        raw_address,
        parsed,
        _tk_guess_city_from_export_text=_tk_guess_city_from_export_text,
        _tk_normalize_export_country=_tk_normalize_export_country,
        _tk_normalize_export_phone=_tk_normalize_export_phone,
        _tk_parse_structured_export_address=_tk_parse_structured_export_address,
        _tk_refine_export_address_city=_tk_refine_export_address_city,
        re=re,
    )


def _tk_parse_shop_names_from_request():
    return _tk_customer_service_routes._tk_parse_shop_names_from_request(request=request)


def _tk_parse_importers_from_request():
    return _tk_customer_service_routes._tk_parse_importers_from_request(request=request)


def _tk_parse_order_nos_from_request():
    return _tk_customer_service_routes._tk_parse_order_nos_from_request(request=request)


_TK_CUSTOMER_SERVICE_PAGE_SIZE = _tk_customer_service_routes.DEFAULT_PAGE_SIZE


def _tk_customer_service_join_key(value):
    return _tk_customer_service_routes._tk_customer_service_join_key(value)


def _tk_customer_service_fill_complete_tracking_numbers(items, query_fn=sf_db):
    return _tk_customer_service_routes._tk_customer_service_fill_complete_tracking_numbers(
        items,
        query_fn,
        _tk_customer_service_join_key=_tk_customer_service_join_key,
    )


def _tk_customer_service_filter_sql(start_date, end_date, shop_names=None, importer_names=None, order_nos=None):
    return _tk_customer_service_routes._tk_customer_service_filter_sql(
        start_date,
        end_date,
        shop_names,
        importer_names,
        order_nos,
    )


def _tk_customer_service_query_total(start_date, end_date, shop_names=None, importer_names=None, order_nos=None):
    return _tk_customer_service_routes._tk_customer_service_query_total(
        start_date,
        end_date,
        shop_names,
        importer_names,
        order_nos,
        _tk_customer_service_filter_sql=_tk_customer_service_filter_sql,
        sf_db=sf_db,
    )


def _tk_customer_service_query_shops(start_date, end_date):
    return _tk_customer_service_routes._tk_customer_service_query_shops(
        start_date,
        end_date,
        _tk_customer_service_filter_sql=_tk_customer_service_filter_sql,
        sf_db=sf_db,
    )


def _tk_customer_service_query_rows(start_date, end_date, shop_names=None, importer_names=None, order_nos=None, page=None, page_size=_TK_CUSTOMER_SERVICE_PAGE_SIZE):
    return _tk_customer_service_routes._tk_customer_service_query_rows(
        start_date,
        end_date,
        shop_names,
        importer_names,
        order_nos,
        page,
        page_size,
        _tk_customer_service_fill_complete_tracking_numbers=_tk_customer_service_fill_complete_tracking_numbers,
        _tk_customer_service_filter_sql=_tk_customer_service_filter_sql,
        datetime=datetime,
        sf_db=sf_db,
    )


@app.route('/api/tk_customer_service/list', methods=['GET'])
@require_permission('tk_customer_service')
def api_tk_customer_service_list():
    return _tk_customer_service_routes.api_tk_customer_service_list(
        _TK_CUSTOMER_SERVICE_PAGE_SIZE=_TK_CUSTOMER_SERVICE_PAGE_SIZE,
        _tk_customer_service_query_rows=_tk_customer_service_query_rows,
        _tk_customer_service_query_total=_tk_customer_service_query_total,
        _tk_parse_importers_from_request=_tk_parse_importers_from_request,
        _tk_parse_order_nos_from_request=_tk_parse_order_nos_from_request,
        _tk_parse_shop_names_from_request=_tk_parse_shop_names_from_request,
        datetime=datetime,
        jsonify=jsonify,
        request=request,
        timedelta=timedelta,
    )


@app.route('/api/tk_customer_service/shops', methods=['GET'])
@require_permission('tk_customer_service')
def api_tk_customer_service_shops():
    return _tk_customer_service_routes.api_tk_customer_service_shops(
        _tk_customer_service_query_shops=_tk_customer_service_query_shops,
        datetime=datetime,
        jsonify=jsonify,
        request=request,
        timedelta=timedelta,
    )


def _tk_customer_service_build_export_rows(items):
    return _tk_customer_service_routes._tk_customer_service_build_export_rows(
        items,
        _tk_parse_wanghong_address=_tk_parse_wanghong_address,
        _tk_prepare_export_contact_fields=_tk_prepare_export_contact_fields,
        _tk_validate_export_address=_tk_validate_export_address,
    )


@app.route('/api/tk_customer_service/export', methods=['GET'])
@require_permission('tk_customer_service')
def api_tk_customer_service_export():
    return _tk_customer_service_routes.api_tk_customer_service_export(
        _tk_customer_service_build_export_rows=_tk_customer_service_build_export_rows,
        _tk_customer_service_query_rows=_tk_customer_service_query_rows,
        _tk_parse_importers_from_request=_tk_parse_importers_from_request,
        _tk_parse_order_nos_from_request=_tk_parse_order_nos_from_request,
        _tk_parse_shop_names_from_request=_tk_parse_shop_names_from_request,
        datetime=datetime,
        jsonify=jsonify,
        request=request,
        send_file=send_file,
        sf_db=sf_db,
        timedelta=timedelta,
    )


@app.route('/api/tk_customer_service/update_note', methods=['POST'])
@require_permission('tk_customer_service')
def api_tk_customer_service_update_note():
    return _tk_customer_service_routes.api_tk_customer_service_update_note(
        dui_db=dui_db,
        jsonify=jsonify,
        request=request,
    )


@app.route('/tk_invite_monitor')
@require_permission('tk_invite_monitor')
def tk_invite_monitor():
    return _tk_invite_monitor_routes.tk_invite_monitor(render_template=render_template, session=session)


@app.route('/tk_monthly_target_import')
@require_permission('tk_monthly_target_import')
def tk_monthly_target_import():
    return _tk_monthly_target_routes.tk_monthly_target_import(render_template=render_template, session=session)


@app.route('/tk_video_realtime')
@require_permission('tk_video_realtime')
def tk_video_realtime():
    return _tk_video_realtime_routes.tk_video_realtime(render_template=render_template, session=session)


@app.route('/tk_video_realtime_account_links')
@require_permission('tk_video_realtime')
def tk_video_realtime_account_links():
    return _tk_video_realtime_routes.tk_video_realtime_account_links(render_template=render_template, session=session)


def _tk_video_realtime_sql_text(value):
    return _tk_video_realtime_routes._tk_video_realtime_sql_text(value)


def _tk_video_realtime_pick(row, key):
    return _tk_video_realtime_routes._tk_video_realtime_pick(row, key)


@app.route('/api/tk_video_realtime/account_links')
@require_permission('tk_video_realtime')
def api_tk_video_realtime_account_links():
    return _tk_video_realtime_routes.api_tk_video_realtime_account_links(
        _tk_video_realtime_pick=_tk_video_realtime_pick,
        jsonify=jsonify,
        sf_db=sf_db,
    )


@app.route('/api/tk_video_realtime/account_links/save', methods=['POST'])
@require_permission('tk_video_realtime')
def api_tk_video_realtime_account_links_save():
    return _tk_video_realtime_routes.api_tk_video_realtime_account_links_save(
        _tk_video_realtime_sql_text=_tk_video_realtime_sql_text,
        dui_db=dui_db,
        jsonify=jsonify,
        request=request,
        sf_db=sf_db,
    )


@app.route('/api/tk_video_realtime/account_links/delete', methods=['POST'])
@require_permission('tk_video_realtime')
def api_tk_video_realtime_account_links_delete():
    return _tk_video_realtime_routes.api_tk_video_realtime_account_links_delete(
        _tk_video_realtime_sql_text=_tk_video_realtime_sql_text,
        dui_db=dui_db,
        jsonify=jsonify,
        request=request,
    )


@app.route('/api/tk_video_realtime/shops')
@require_permission('tk_video_realtime')
def api_tk_video_realtime_shops():
    return _tk_video_realtime_routes.api_tk_video_realtime_shops(jsonify=jsonify, sf_db=sf_db)


@app.route('/api/tk_video_realtime/daren')
@require_permission('tk_video_realtime')
def api_tk_video_realtime_daren():
    return _tk_video_realtime_routes.api_tk_video_realtime_daren(
        jsonify=jsonify,
        request=request,
        sf_db=sf_db,
    )


@app.route('/api/tk_video_realtime/fuzeren')
@require_permission('tk_video_realtime')
def api_tk_video_realtime_fuzeren():
    return _tk_video_realtime_routes.api_tk_video_realtime_fuzeren(
        jsonify=jsonify,
        request=request,
        sf_db=sf_db,
    )


@app.route('/api/tk_video_realtime/videos')
@require_permission('tk_video_realtime')
def api_tk_video_realtime_videos():
    return _tk_video_realtime_routes.api_tk_video_realtime_videos(
        jsonify=jsonify,
        re=re,
        request=request,
        sf_db=sf_db,
    )


@app.route('/api/tk_invite_monitor/upload', methods=['POST'])
@require_permission('tk_invite_monitor')
def upload_invite_ids():
    return _tk_invite_monitor_routes.upload_invite_ids(
        dui_db=dui_db,
        jsonify=jsonify,
        request=request,
        session=session,
        sf_db=sf_db,
    )


@app.route('/api/tk_invite_monitor/wanghong_register_upload', methods=['POST'])
@require_permission('tk_invite_monitor')
def upload_wanghong_register():
    return _tk_invite_monitor_routes.upload_wanghong_register(
        datetime=datetime,
        dui_db=dui_db,
        jsonify=jsonify,
        request=request,
        session=session,
        sf_db=sf_db,
    )


@app.route('/api/tk_invite_monitor/list', methods=['GET'])
@require_permission('tk_invite_monitor')
def list_invite_codes():
    return _tk_invite_monitor_routes.list_invite_codes(
        jsonify=jsonify,
        session=session,
        sf_db=sf_db,
    )


@app.route('/api/tk_invite_monitor/unchecked_12h', methods=['GET'])
@require_permission('tk_invite_monitor')
def list_unchecked_invite_codes_12h():
    return _tk_invite_monitor_routes.list_unchecked_invite_codes_12h(jsonify=jsonify, sf_db=sf_db)


@app.route('/api/tk_invite_monitor/wanghong_register_overview', methods=['GET'])
@require_permission('tk_invite_monitor')
def tk_invite_monitor_wanghong_register_overview():
    return _tk_invite_monitor_routes.tk_invite_monitor_wanghong_register_overview(
        datetime=datetime,
        jsonify=jsonify,
        sf_db=sf_db,
    )


@app.route('/api/tk_monthly_target_import/upload', methods=['POST'])
@require_permission('tk_monthly_target_import')
def upload_monthly_target():
    return _tk_monthly_target_routes.upload_monthly_target(
        dui_db=dui_db,
        jsonify=jsonify,
        request=request,
        sf_db=sf_db,
    )


@app.route('/api/tk_monthly_target_import/template', methods=['GET'])
@require_permission('tk_monthly_target_import')
def download_monthly_target_template():
    return _tk_monthly_target_routes.download_monthly_target_template(
        datetime=datetime,
        jsonify=jsonify,
        send_file=send_file,
        sf_db=sf_db,
    )

@app.route('/tk_dashboard')
@require_permission('tk_dashboard_legacy')
def tk_dashboard():
    return _tk_dashboard_routes.tk_dashboard(render_template=render_template, session=session)


@app.route('/api/tk_dashboard_data', methods=['GET'])
@require_permission('tk_dashboard_legacy')
def get_tk_dashboard_data():
    return _tk_dashboard_routes.get_tk_dashboard_data(
        _current_user_has_permission=_current_user_has_permission,
        _safe_debug_print=_safe_debug_print,
        datetime=datetime,
        jsonify=jsonify,
        request=request,
        session=session,
        sf_db=sf_db,
    )



# 运营部门功能页面路由
@app.route('/general_office')
@require_permission('general_office')
def general_office():
    return _general_office_entry_pages.general_office(
        _current_user_has_permission=_current_user_has_permission,
        render_template=render_template,
        session=session,
    )




_OPERATION_DEPT_FUNCTIONS = {
    'operation_dept_1',
    'operation_dept_2',
    'operation_dept_3',
    'operation_dept_6',
    'operation_dept_7',
}
_FBA_SHIPPING_ACCESS_FUNCTIONS = _OPERATION_DEPT_FUNCTIONS | {'newcomer_group'}
_FBA_SHIPPING_TABLE = 'FBAHuoJian_YunShuFangShi'
_FBA_SHIPPING_PAGE_SIZE = 200


def _operation_dept_has_access():
    return _operation_department_pages._operation_dept_has_access(_current_user_has_permission=_current_user_has_permission)


def _operation_page_permission_flags(user_id):
    return _dashboard_access._operation_page_permission_flags(
        user_id,
        _safe_debug_print=_safe_debug_print,
        permission_manager=permission_manager,
    )


def _fba_shipping_sql_ident(name):
    return _fba_shipping_columns._fba_shipping_sql_ident(name)


def _fba_shipping_sql_text(value):
    return _fba_shipping_columns._fba_shipping_sql_text(value)


def _fba_shipping_col_norm(name):
    return _fba_shipping_columns._fba_shipping_col_norm(name, re=re)


def _fba_shipping_label(name):
    return _fba_shipping_columns._fba_shipping_label(name, _fba_shipping_col_norm=_fba_shipping_col_norm)


def _fba_shipping_pick_col(columns, candidates):
    return _fba_shipping_columns._fba_shipping_pick_col(
        columns,
        candidates,
        _fba_shipping_col_norm=_fba_shipping_col_norm,
    )


def _fba_shipping_get_columns():
    return _fba_shipping_columns._fba_shipping_get_columns(_FBA_SHIPPING_TABLE=_FBA_SHIPPING_TABLE, sf_db=sf_db)


def _fba_shipping_row_to_item(row, columns):
    return _fba_shipping_columns._fba_shipping_row_to_item(row, columns)


def _fba_shipping_format_value(value):
    return _fba_shipping_columns._fba_shipping_format_value(
        value,
        date=date,
        datetime=datetime,
    )


def _fba_shipping_is_scientific(value):
    return _fba_shipping_columns._fba_shipping_is_scientific(value, re=re)


def _fba_shipping_sql_empty_expr(column_name):
    return _fba_shipping_columns._fba_shipping_sql_empty_expr(column_name, _fba_shipping_sql_ident=_fba_shipping_sql_ident)


def _fba_shipping_sql_scientific_expr(column_name):
    return _fba_shipping_columns._fba_shipping_sql_scientific_expr(column_name, _fba_shipping_sql_ident=_fba_shipping_sql_ident)


def _fba_shipping_issue_clause(shipping_col, cargo_col):
    return _fba_shipping_columns._fba_shipping_issue_clause(
        shipping_col,
        cargo_col,
        _fba_shipping_sql_empty_expr=_fba_shipping_sql_empty_expr,
        _fba_shipping_sql_ident=_fba_shipping_sql_ident,
        _fba_shipping_sql_scientific_expr=_fba_shipping_sql_scientific_expr,
    )


def _fba_shipping_prepare_payload_item(row_item, columns, sea_col, cargo_col):
    return _fba_shipping_columns._fba_shipping_prepare_payload_item(
        row_item,
        columns,
        sea_col,
        cargo_col,
        _fba_shipping_format_value=_fba_shipping_format_value,
        _fba_shipping_is_scientific=_fba_shipping_is_scientific,
        re=re,
    )


def _fba_shipping_response_columns(columns):
    return _fba_shipping_columns._fba_shipping_response_columns(
        columns,
        _fba_shipping_label=_fba_shipping_label,
        _fba_shipping_pick_col=_fba_shipping_pick_col,
    )


def _fba_shipping_sort_columns(columns):
    return _fba_shipping_columns._fba_shipping_sort_columns(columns, _fba_shipping_pick_col=_fba_shipping_pick_col)


@app.route('/api/operation/fba_shipping_methods')
@require_permission('operation_fba_shipping')
def api_operation_fba_shipping_methods():
    return _operation_department_pages.api_operation_fba_shipping_methods(
        _operation_dept_has_access=_operation_dept_has_access,
        app=app,
        jsonify=jsonify,
        request=request,
        sf_db=sf_db,
    )


@app.route('/api/operation/fba_shipping_methods/shops')
@require_permission('operation_fba_shipping')
def api_operation_fba_shipping_method_shops():
    return _operation_department_pages.api_operation_fba_shipping_method_shops(
        _operation_dept_has_access=_operation_dept_has_access,
        app=app,
        jsonify=jsonify,
        sf_db=sf_db,
    )


@app.route('/api/operation/fba_shipping_methods/export')
@require_permission('operation_fba_shipping')
def export_operation_fba_shipping_methods():
    return _operation_department_pages.export_operation_fba_shipping_methods(
        _operation_dept_has_access=_operation_dept_has_access,
        app=app,
        jsonify=jsonify,
        request=request,
        sf_db=sf_db,
    )


@app.route('/operation/fba_shipping_methods')
@require_permission('operation_fba_shipping')
def operation_fba_shipping_methods_page():
    return _operation_department_pages.operation_fba_shipping_methods_page(
        _FBA_SHIPPING_ACCESS_FUNCTIONS=_FBA_SHIPPING_ACCESS_FUNCTIONS,
        _operation_dept_has_access=_operation_dept_has_access,
        flash=flash,
        redirect=redirect,
        render_template=render_template,
        request=request,
        session=session,
        url_for=url_for,
    )


@app.route('/operation_dept_1')
@require_permission('operation_dept_1')
def operation_dept_1():
    return _operation_department_pages.operation_dept_1(
        _current_user_has_permission=_current_user_has_permission,
        _operation_page_permission_flags=_operation_page_permission_flags,
        render_template=render_template,
        session=session,
    )


@app.route('/operation_dept_2')
@require_permission('operation_dept_2')
def operation_dept_2():
    return _operation_department_pages.operation_dept_2(
        _operation_page_permission_flags=_operation_page_permission_flags,
        render_template=render_template,
        session=session,
    )


@app.route('/operation_dept_3')
@require_permission('operation_dept_3')
def operation_dept_3():
    return _operation_department_pages.operation_dept_3(
        _operation_page_permission_flags=_operation_page_permission_flags,
        render_template=render_template,
        session=session,
    )


@app.route('/operation_dept_6')
@require_permission('operation_dept_6')
def operation_dept_6():
    return _operation_department_pages.operation_dept_6(
        _current_user_has_permission=_current_user_has_permission,
        _operation_page_permission_flags=_operation_page_permission_flags,
        render_template=render_template,
        session=session,
    )


@app.route('/operation_dept_7')
@require_permission('operation_dept_7')
def operation_dept_7():
    return _operation_department_pages.operation_dept_7(
        _operation_page_permission_flags=_operation_page_permission_flags,
        render_template=render_template,
        session=session,
    )



@app.route('/rd_dept')
@require_permission('rd_dept')
def rd_dept():
    return _research_entry_pages.rd_dept(
        _operation_page_permission_flags=_operation_page_permission_flags,
        render_template=render_template,
        session=session,
    )




@app.route('/visual_design_dept/image_tool')
@require_permission('visual_design_dept')
def visual_design_image_tool():
    return _design_portal_links.visual_design_image_tool(
        _build_lashforge_entry_url=_build_lashforge_entry_url,
        _ensure_lashforge_watchdog_started=_ensure_lashforge_watchdog_started,
        _is_feishu_request=_is_feishu_request,
        _is_lashforge_reachable=_is_lashforge_reachable,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        redirect=redirect,
        render_template=render_template,
        request=request,
        session=session,
    )


@app.route('/visual_design_dept/image_tool/status')
@require_permission('visual_design_dept')
def visual_design_image_tool_status():
    return _design_portal_links.visual_design_image_tool_status(
        _ensure_lashforge_watchdog_started=_ensure_lashforge_watchdog_started,
        _is_lashforge_reachable=_is_lashforge_reachable,
        jsonify=jsonify,
    )


@app.route('/api/infinite-canvas/bootstrap-config')
@require_permission('visual_design_dept')
def api_infinite_canvas_bootstrap_config():
    return _canvas_routes.api_infinite_canvas_bootstrap_config(
        _INFINITE_CANVAS_LEGACY_IMAGE_MODELS=_INFINITE_CANVAS_LEGACY_IMAGE_MODELS,
        _INFINITE_CANVAS_OMNIAKEY_IMAGE_MODELS=_INFINITE_CANVAS_OMNIAKEY_IMAGE_MODELS,
        _INFINITE_CANVAS_OMNIAKEY_MODEL=_INFINITE_CANVAS_OMNIAKEY_MODEL,
        _INFINITE_CANVAS_OPENROUTER_IMAGE_MODELS=_INFINITE_CANVAS_OPENROUTER_IMAGE_MODELS,
        _INFINITE_CANVAS_OPENROUTER_TEXT_MODELS=_INFINITE_CANVAS_OPENROUTER_TEXT_MODELS,
        env=env,
        jsonify=jsonify,
    )


@app.route('/shenzhen_dept')
@require_permission('shenzhen_dept')
def shenzhen_dept():
    return _operation_department_pages.shenzhen_dept(
        _current_user_has_permission=_current_user_has_permission,
        render_template=render_template,
        session=session,
    )

@app.route('/newcomer_group')
@require_permission('newcomer_group')
def newcomer_group():
    return _operation_department_pages.newcomer_group(
        _current_user_has_permission=_current_user_has_permission,
        _operation_page_permission_flags=_operation_page_permission_flags,
        render_template=render_template,
        session=session,
    )


def generate_cache_key(product_name, features, script_number):
    return _content_generation_routes.generate_cache_key(
        product_name,
        features,
        script_number,
    )


def call_ai_api(product_name, product_features, script_number):
    return _content_generation_routes.call_ai_api(
        product_name,
        product_features,
        script_number,
        _OPENAI_TEXT_MODEL_CANDIDATES=_OPENAI_TEXT_MODEL_CANDIDATES,
        _ai_chat_complete=_ai_chat_complete,
        _safe_debug_print=_safe_debug_print,
        cache_lock=cache_lock,
        generate_cache_key=generate_cache_key,
        script_cache=script_cache,
    )


@app.route('/image_generator')
def image_generator():
    return _content_generation_routes.image_generator(render_template=render_template)


@app.route('/generate_image', methods=['POST'])
def generate_image():
    return _content_generation_routes.generate_image(
        client=client,
        jsonify=jsonify,
        request=request,
    )


@app.route('/ai_modules')
def ai_modules():
    return _ai_catalog_pages.ai_modules(
        _can_access_ai_workspace=_can_access_ai_workspace,
        _safe_debug_print=_safe_debug_print,
        permission_manager=permission_manager,
        render_template=render_template,
        session=session,
    )

@app.route('/ai/lunch-push')
def lunch_push_page():
    return _lunch_push_routes.lunch_push_page(
        _can_access_ai_workspace=_can_access_ai_workspace,
        env=env,
        render_template=render_template,
    )


@app.route('/api/ai/lunch-push', methods=['GET', 'POST'])
def lunch_push_api():
    return _lunch_push_routes.lunch_push_api(
        _can_access_ai_workspace=_can_access_ai_workspace,
        app=app,
        jsonify=jsonify,
        lunch_push=lunch_push,
        request=request,
        url_for=url_for,
    )


@app.route('/api/ai/lunch-push/image/<filename>')
def lunch_push_image(filename):
    return _lunch_push_routes.lunch_push_image(
        filename,
        _can_access_ai_workspace=_can_access_ai_workspace,
        abort=abort,
        lunch_push=lunch_push,
        send_file=send_file,
    )


@app.route('/ai/replenishment-vben')
@require_permission('replenishment_vben')
def replenishment_vben_page():
    return _tool_entry_pages.replenishment_vben_page(
        _can_access_ai_workspace=_can_access_ai_workspace,
        app=app,
        os=os,
        send_file=send_file,
    )


@app.route('/api/ai/replenishment-vben/config')
@require_permission('replenishment_vben')
def replenishment_vben_config():
    return _tool_entry_pages.replenishment_vben_config(
        _can_access_ai_workspace=_can_access_ai_workspace,
        jsonify=jsonify,
        session=session,
        url_for=url_for,
    )


@app.route('/ai/video-claw', defaults={'subpath': ''}, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
@app.route('/ai/video-claw/<path:subpath>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
@require_permission('video_claw')
def video_claw(subpath=''):
    return _ai_proxy_routes.video_claw(
        subpath,
        _VIDEOCLAW_FRONTEND_URL=_VIDEOCLAW_FRONTEND_URL,
        _can_access_ai_workspace=_can_access_ai_workspace,
        _ensure_videoclaw_started=_ensure_videoclaw_started,
        app=app,
        render_template=render_template,
        request=request,
        requests=requests,
    )


@app.route('/ai/video-claw/backend/<path:subpath>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
@require_permission('video_claw')
def video_claw_backend(subpath):
    return _ai_proxy_routes.video_claw_backend(
        subpath,
        _VIDEOCLAW_BACKEND_URL=_VIDEOCLAW_BACKEND_URL,
        _can_access_ai_workspace=_can_access_ai_workspace,
        app=app,
        jsonify=jsonify,
        request=request,
        requests=requests,
        stream_with_context=stream_with_context,
    )


_AI_UPDATE_QUERY = "select * from gengxin where riqi=convert(date, getdate())"


def _format_ai_update_cell(value):
    return _ai_catalog_pages._format_ai_update_cell(
        value,
        date=date,
        datetime=datetime,
    )


@app.route('/ai/update')
@require_permission('admin_functions')
def ai_update():
    return _ai_catalog_pages.ai_update(
        _AI_UPDATE_QUERY=_AI_UPDATE_QUERY,
        _format_ai_update_cell=_format_ai_update_cell,
        app=app,
        datetime=datetime,
        render_template=render_template,
        sf_db=sf_db,
    )


@app.route('/ai/business-analysis')
@_require_business_analysis_access
def business_analysis():
    return _business_analysis_routes.business_analysis(
        _BUSINESS_ANALYSIS_DIST_DIR=_BUSINESS_ANALYSIS_DIST_DIR,
        app=app,
        os=os,
        record_business_analysis_usage=record_business_analysis_usage,
        render_template=render_template,
        request=request,
        send_from_directory=send_from_directory,
        session=session,
    )


@app.route('/ai/business-analysis/assets/<path:filename>')
@_require_business_analysis_access
def business_analysis_asset(filename):
    return _business_analysis_routes.business_analysis_asset(
        filename,
        _BUSINESS_ANALYSIS_DIST_DIR=_BUSINESS_ANALYSIS_DIST_DIR,
        os=os,
        send_from_directory=send_from_directory,
    )


@app.route('/ai/ads-monitor')
@require_permission('ads_monitor')
def ads_monitor():
    return _tool_entry_pages.ads_monitor(
        _ADS_MONITOR_DIST_DIR=_ADS_MONITOR_DIST_DIR,
        _ensure_ads_monitor_api_started=_ensure_ads_monitor_api_started,
        os=os,
        render_template=render_template,
        send_from_directory=send_from_directory,
    )


@app.route('/ai/ads-monitor/<path:filename>')
@require_permission('ads_monitor')
def ads_monitor_asset(filename):
    return _tool_entry_pages.ads_monitor_asset(
        filename,
        _ADS_MONITOR_DIST_DIR=_ADS_MONITOR_DIST_DIR,
        send_from_directory=send_from_directory,
    )


@app.route('/api/ads-monitor/diagnostic', defaults={'subpath': ''}, methods=['GET', 'POST'])
@app.route('/api/ads-monitor/diagnostic/<path:subpath>', methods=['GET', 'POST'])
@require_permission('ads_monitor')
def ads_monitor_diagnostic_api(subpath):
    return _ai_proxy_routes.ads_monitor_diagnostic_api(
        subpath,
        _ADS_MONITOR_API_PORT=_ADS_MONITOR_API_PORT,
        _ensure_ads_monitor_api_started=_ensure_ads_monitor_api_started,
        _is_ads_monitor_api_reachable=_is_ads_monitor_api_reachable,
        app=app,
        jsonify=jsonify,
        request=request,
        requests=requests,
        time=time,
    )


@app.route('/ai/business-analysis/status')
@_require_business_analysis_access
def business_analysis_status():
    return _business_analysis_routes.business_analysis_status(
        _BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH=_BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH,
        jsonify=jsonify,
        os=os,
    )


@app.route('/api/ai/business-analysis/dashboard')
@_require_business_analysis_access
def business_analysis_dashboard_api():
    return _business_analysis_routes.business_analysis_dashboard_api(
        _BUSINESS_ANALYSIS_API_PORT=_BUSINESS_ANALYSIS_API_PORT,
        _BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH=_BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH,
        _BUSINESS_ANALYSIS_SNAPSHOT_PATH=_BUSINESS_ANALYSIS_SNAPSHOT_PATH,
        _BUSINESS_ANALYSIS_TIER_SNAPSHOT_PATH=_BUSINESS_ANALYSIS_TIER_SNAPSHOT_PATH,
        _ensure_business_analysis_api_started=_ensure_business_analysis_api_started,
        _get_business_analysis_scope=_get_business_analysis_scope,
        _is_business_analysis_api_reachable=_is_business_analysis_api_reachable,
        app=app,
        datetime=datetime,
        force_business_analysis_query_params=force_business_analysis_query_params,
        json=json,
        jsonify=jsonify,
        merge_business_analysis_store_tier_snapshot=merge_business_analysis_store_tier_snapshot,
        prepare_business_analysis_payload=prepare_business_analysis_payload,
        request=request,
        requests=requests,
        time=time,
    )


@app.route('/api/ai/business-analysis/scope')
@_require_business_analysis_access
def business_analysis_scope_api():
    return _business_analysis_routes.business_analysis_scope_api(_get_business_analysis_scope=_get_business_analysis_scope, jsonify=jsonify)


def _business_analysis_store_tier_scope_condition(scope):
    return _business_analysis_routes._business_analysis_store_tier_scope_condition(scope, BUSINESS_ANALYSIS_DEPARTMENT_LEADERS=BUSINESS_ANALYSIS_DEPARTMENT_LEADERS)


def _load_business_analysis_tier_history_snapshot():
    return _business_analysis_routes._load_business_analysis_tier_history_snapshot(
        _BUSINESS_ANALYSIS_TIER_HISTORY_SNAPSHOT_PATH=_BUSINESS_ANALYSIS_TIER_HISTORY_SNAPSHOT_PATH,
        _business_analysis_tier_history_cache=_business_analysis_tier_history_cache,
        _business_analysis_tier_history_cache_lock=_business_analysis_tier_history_cache_lock,
        date=date,
        detect_promotions=detect_promotions,
        json=json,
        os=os,
    )


@app.route('/api/ai/business-analysis/store-tier-history')
@_require_business_analysis_access
def business_analysis_store_tier_history_api():
    return _business_analysis_routes.business_analysis_store_tier_history_api(
        BUSINESS_ANALYSIS_DEPARTMENT_LEADERS=BUSINESS_ANALYSIS_DEPARTMENT_LEADERS,
        _BUSINESS_ANALYSIS_ROOT=_BUSINESS_ANALYSIS_ROOT,
        _get_business_analysis_scope=_get_business_analysis_scope,
        _load_business_analysis_tier_history_snapshot=_load_business_analysis_tier_history_snapshot,
        app=app,
        date=date,
        json=json,
        jsonify=jsonify,
        os=os,
        request=request,
        timedelta=timedelta,
    )


@app.route('/api/ai/business-analysis/promotion-backfill', methods=['GET', 'POST'])
@_require_business_analysis_access
def business_analysis_promotion_backfill_api():
    return _business_analysis_routes.business_analysis_promotion_backfill_api(
        _get_business_analysis_scope=_get_business_analysis_scope,
        app=app,
        date=date,
        jsonify=jsonify,
        request=request,
        timedelta=timedelta,
    )


@app.route('/api/ai/business-analysis/fiscal-overview', methods=['GET'])
@_require_business_analysis_access
def business_analysis_fiscal_overview_api():
    return _business_analysis_routes.business_analysis_fiscal_overview_api(
        _get_business_analysis_scope=_get_business_analysis_scope,
        app=app,
        jsonify=jsonify,
        load_fiscal_overview=load_fiscal_overview,
        request=request,
        validate_fiscal_year=validate_fiscal_year,
    )


@app.route('/api/ai/business-analysis/key-tasks', defaults={'task_id': None}, methods=['GET', 'POST'])
@app.route('/api/ai/business-analysis/key-tasks/<task_id>', methods=['PUT', 'DELETE'])
@_require_business_analysis_access
def business_analysis_key_tasks_api(task_id):
    return _business_analysis_routes.business_analysis_key_tasks_api(
        task_id,
        KeyTaskStoreError=KeyTaskStoreError,
        _business_analysis_key_task_store=_business_analysis_key_task_store,
        _get_business_analysis_scope=_get_business_analysis_scope,
        app=app,
        jsonify=jsonify,
        request=request,
    )


def _company_market_full_access_guard():
    return _business_analysis_routes._company_market_full_access_guard(_get_business_analysis_scope=_get_business_analysis_scope, jsonify=jsonify)


@app.route('/api/ai/business-analysis/market-overview', methods=['GET'])
@_require_business_analysis_access
def business_analysis_market_overview_api():
    return _business_analysis_routes.business_analysis_market_overview_api(
        CompanyMarketError=CompanyMarketError,
        app=app,
        get_market_overview_rows=get_market_overview_rows,
        jsonify=jsonify,
    )


@app.route('/api/ai/business-analysis/company-market', methods=['GET'])
@_require_business_analysis_access
def business_analysis_company_market_api():
    return _business_analysis_routes.business_analysis_company_market_api(
        CompanyMarketError=CompanyMarketError,
        _company_market_full_access_guard=_company_market_full_access_guard,
        app=app,
        get_company_market_overview=get_company_market_overview,
        jsonify=jsonify,
        request=request,
    )


@app.route('/api/ai/business-analysis/company-market/entry', methods=['POST'])
@_require_business_analysis_access
def business_analysis_company_market_entry_api():
    return _business_analysis_routes.business_analysis_company_market_entry_api(
        CompanyMarketError=CompanyMarketError,
        _company_market_full_access_guard=_company_market_full_access_guard,
        app=app,
        jsonify=jsonify,
        request=request,
        upsert_company_market_month=upsert_company_market_month,
    )


@app.route('/ai/innovation_pending_reminder_test')
@require_permission('admin_functions')
def innovation_pending_reminder_test_page():
    return _innovation_admin_routes.innovation_pending_reminder_test_page(render_template=render_template)


@app.route('/ai/feishu-video-card-test')
@require_permission('hr_admin_dept')
def feishu_video_card_test_page():
    return _feishu_message_test_routes.feishu_video_card_test_page(render_template=render_template, session=session)


def _upload_feishu_message_video(upload):
    return _feishu_video_messages._upload_feishu_message_video(permission_manager.get_access_token, upload)


def _upload_feishu_video_cover(upload):
    return _feishu_video_messages._upload_feishu_video_cover(permission_manager.get_access_token, upload)


def _list_feishu_bot_chats():
    return _feishu_video_messages._list_feishu_bot_chats(permission_manager.get_access_token)


def _resolve_feishu_chat_name(chat_name):
    return _feishu_video_messages._resolve_feishu_chat_name(chat_name, _list_feishu_bot_chats)


@app.route('/api/ai/feishu-video-card-test/chats')
@require_permission('hr_admin_dept')
def feishu_video_card_test_chats():
    return _feishu_message_test_routes.feishu_video_card_test_chats(_list_feishu_bot_chats=_list_feishu_bot_chats, jsonify=jsonify)


@app.route('/api/ai/feishu-video-card-test/send', methods=['POST'])
@require_permission('hr_admin_dept')
def feishu_video_card_test_send():
    return _feishu_message_test_routes.feishu_video_card_test_send(
        FEISHU_NATIVE_VIDEO_MAX_BYTES=FEISHU_NATIVE_VIDEO_MAX_BYTES,
        _feishu_send_message_detail=_feishu_send_message_detail,
        _resolve_feishu_chat_name=_resolve_feishu_chat_name,
        _upload_feishu_message_video=_upload_feishu_message_video,
        _upload_feishu_video_cover=_upload_feishu_video_cover,
        jsonify=jsonify,
        os=os,
        request=request,
        session=session,
    )


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


def _build_amazon_reply_service():
    return _amazon_reply_routes._build_amazon_reply_service(
        AI_RUNTIME_CONFIG=AI_RUNTIME_CONFIG,
        API_BASE_URL=API_BASE_URL,
        OPENAI_API_KEY=OPENAI_API_KEY,
        _OPENAI_TEXT_MODEL=_OPENAI_TEXT_MODEL,
        _get_env_float=_get_env_float,
        _get_env_int=_get_env_int,
        _normalize_chat_completions_url=_normalize_chat_completions_url,
        os=os,
        sql_server_config=sql_server_config,
    )


def _get_amazon_reply_service():
    global _amazon_reply_service
    if _amazon_reply_service is None:
        _amazon_reply_service = _build_amazon_reply_service()
    return _amazon_reply_service


@app.route('/amazon_reply_agent')
@require_permission('amazon_reply_agent')
def amazon_reply_agent():
    return _amazon_reply_routes.amazon_reply_agent(
        render_template=render_template,
        request=request,
        session=session,
        url_for=url_for,
    )


@app.route('/api/ai/amazon_reply/generate', methods=['POST'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_generate():
    return _amazon_reply_routes.api_ai_amazon_reply_generate(
        _get_amazon_reply_service=_get_amazon_reply_service,
        jsonify=jsonify,
        request=request,
    )


def _amazon_reply_text_list(value):
    return _amazon_reply_routes._amazon_reply_text_list(value, re=re)


def _amazon_reply_rule_type(raw_type):
    return _amazon_reply_routes._amazon_reply_rule_type(raw_type)


@app.route('/api/ai/amazon_reply/rules', methods=['GET'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_rules():
    return _amazon_reply_routes.api_ai_amazon_reply_rules(_get_amazon_reply_service=_get_amazon_reply_service, jsonify=jsonify)


@app.route('/api/ai/amazon_reply/rules', methods=['POST'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_add_rule():
    return _amazon_reply_routes.api_ai_amazon_reply_add_rule(
        _amazon_reply_rule_type=_amazon_reply_rule_type,
        _get_amazon_reply_service=_get_amazon_reply_service,
        jsonify=jsonify,
        request=request,
    )


@app.route('/api/ai/amazon_reply/rules/<int:rule_id>', methods=['DELETE'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_delete_rule(rule_id):
    return _amazon_reply_routes.api_ai_amazon_reply_delete_rule(
        rule_id,
        _get_amazon_reply_service=_get_amazon_reply_service,
        jsonify=jsonify,
    )


@app.route('/api/ai/amazon_reply/scenarios', methods=['POST'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_add_scenario():
    return _amazon_reply_routes.api_ai_amazon_reply_add_scenario(
        _amazon_reply_text_list=_amazon_reply_text_list,
        _get_amazon_reply_service=_get_amazon_reply_service,
        jsonify=jsonify,
        request=request,
    )


@app.route('/api/ai/amazon_reply/scenarios/<int:scenario_id>', methods=['DELETE'])
@require_permission('amazon_reply_agent')
def api_ai_amazon_reply_delete_scenario(scenario_id):
    return _amazon_reply_routes.api_ai_amazon_reply_delete_scenario(
        scenario_id,
        _get_amazon_reply_service=_get_amazon_reply_service,
        jsonify=jsonify,
    )


def _permission_debug_available_departments():
    return _identity_state._permission_debug_available_departments(permission_manager=permission_manager)


_DASHBOARD_IDENTITY_SWITCH_USER_NAMES = {'周俊成', '蔡晶', '陈子烨'}
_DASHBOARD_IDENTITY_SWITCH_COOKIE = 'dashboard_identity_switch'
_DASHBOARD_IDENTITY_SWITCH_MAX_AGE_SECONDS = 24 * 60 * 60


def _can_dashboard_switch_identity():
    return _identity_state._can_dashboard_switch_identity(
        _DASHBOARD_IDENTITY_SWITCH_USER_NAMES=_DASHBOARD_IDENTITY_SWITCH_USER_NAMES,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        is_local_superadmin=is_local_superadmin,
        session=session,
    )


def _dashboard_identity_switch_forbidden_response():
    return _identity_state._dashboard_identity_switch_forbidden_response(jsonify=jsonify)


def _dashboard_identity_switch_serializer():
    return _identity_state._dashboard_identity_switch_serializer(URLSafeTimedSerializer=URLSafeTimedSerializer, app=app)


def _dashboard_identity_switch_state_serializer():
    return _identity_state._dashboard_identity_switch_state_serializer(URLSafeTimedSerializer=URLSafeTimedSerializer, app=app)


def _dashboard_identity_switch_operator_open_id():
    return _identity_state._dashboard_identity_switch_operator_open_id(session=session)


def _dashboard_identity_switch_state_token(open_id, user_name, departments, updated_at):
    return _identity_state._dashboard_identity_switch_state_token(
        open_id,
        user_name,
        departments,
        updated_at,
        _dashboard_identity_switch_operator_open_id=_dashboard_identity_switch_operator_open_id,
        _dashboard_identity_switch_state_serializer=_dashboard_identity_switch_state_serializer,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
    )


def _dashboard_identity_switch_state_from_request():
    return _identity_routes._dashboard_identity_switch_state_from_request(
        BadSignature=BadSignature,
        SignatureExpired=SignatureExpired,
        _DASHBOARD_IDENTITY_SWITCH_COOKIE=_DASHBOARD_IDENTITY_SWITCH_COOKIE,
        _DASHBOARD_IDENTITY_SWITCH_MAX_AGE_SECONDS=_DASHBOARD_IDENTITY_SWITCH_MAX_AGE_SECONDS,
        _can_dashboard_switch_identity=_can_dashboard_switch_identity,
        _dashboard_identity_switch_operator_open_id=_dashboard_identity_switch_operator_open_id,
        _dashboard_identity_switch_state_serializer=_dashboard_identity_switch_state_serializer,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        request=request,
    )


def _load_dashboard_identity_switch_request_state():
    return _identity_state._load_dashboard_identity_switch_request_state(_dashboard_identity_switch_state_from_request=_dashboard_identity_switch_state_from_request, g=g)


def _permission_debug_effective_state():
    return _identity_state._permission_debug_effective_state(g=g, session=session)


def _permission_debug_identity_cache_key():
    return _identity_state._permission_debug_identity_cache_key(_permission_debug_effective_state=_permission_debug_effective_state)


def _dashboard_identity_switch_selection_token(open_id, user_name):
    return _identity_state._dashboard_identity_switch_selection_token(
        open_id,
        user_name,
        _dashboard_identity_switch_serializer=_dashboard_identity_switch_serializer,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
    )


def _dashboard_identity_switch_selected_member(selection_token):
    return _identity_routes._dashboard_identity_switch_selected_member(
        selection_token,
        BadSignature=BadSignature,
        SignatureExpired=SignatureExpired,
        _dashboard_identity_switch_serializer=_dashboard_identity_switch_serializer,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
    )


def _dashboard_identity_switch_departments(open_id):
    return _identity_routes._dashboard_identity_switch_departments(
        open_id,
        permission_manager=permission_manager,
    )


@app.route('/api/dashboard/identity-switch/members', methods=['GET'])
def api_dashboard_identity_switch_members():
    return _identity_routes.api_dashboard_identity_switch_members(
        _can_dashboard_switch_identity=_can_dashboard_switch_identity,
        _dashboard_identity_switch_forbidden_response=_dashboard_identity_switch_forbidden_response,
        _dashboard_identity_switch_selection_token=_dashboard_identity_switch_selection_token,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        _xiaotu_query_user_names_by_open_ids=_xiaotu_query_user_names_by_open_ids,
        _xiaotu_search_notify_users=_xiaotu_search_notify_users,
        app=app,
        jsonify=jsonify,
        request=request,
    )


@app.route('/api/dashboard/identity-switch', methods=['POST'])
def api_dashboard_identity_switch():
    return _identity_routes.api_dashboard_identity_switch(
        _DASHBOARD_IDENTITY_SWITCH_COOKIE=_DASHBOARD_IDENTITY_SWITCH_COOKIE,
        _can_dashboard_switch_identity=_can_dashboard_switch_identity,
        _dashboard_identity_switch_departments=_dashboard_identity_switch_departments,
        _dashboard_identity_switch_forbidden_response=_dashboard_identity_switch_forbidden_response,
        _dashboard_identity_switch_selected_member=_dashboard_identity_switch_selected_member,
        _dashboard_identity_switch_state_token=_dashboard_identity_switch_state_token,
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        _xiaotu_query_user_names_by_open_ids=_xiaotu_query_user_names_by_open_ids,
        app=app,
        datetime=datetime,
        jsonify=jsonify,
        request=request,
        session=session,
    )


def _permission_debug_session_state():
    return _identity_state._permission_debug_session_state(_permission_debug_effective_state=_permission_debug_effective_state)


@app.route('/api/ai/permission_debug/status', methods=['GET'])
@require_permission('admin_functions')
def api_ai_permission_debug_status():
    return _identity_routes.api_ai_permission_debug_status(
        _permission_debug_available_departments=_permission_debug_available_departments,
        _permission_debug_session_state=_permission_debug_session_state,
        jsonify=jsonify,
    )


@app.route('/api/ai/permission_debug/switch', methods=['POST'])
@require_permission('admin_functions')
def api_ai_permission_debug_switch():
    return _identity_routes.api_ai_permission_debug_switch(
        _normalize_feishu_user_name=_normalize_feishu_user_name,
        _permission_debug_available_departments=_permission_debug_available_departments,
        _permission_debug_session_state=_permission_debug_session_state,
        _xiaotu_lookup_open_id_by_name=_xiaotu_lookup_open_id_by_name,
        datetime=datetime,
        jsonify=jsonify,
        permission_manager=permission_manager,
        request=request,
        session=session,
    )


@app.route('/permission_debug/clear', methods=['GET'])
def permission_debug_clear():
    return _identity_routes.permission_debug_clear(
        _DASHBOARD_IDENTITY_SWITCH_COOKIE=_DASHBOARD_IDENTITY_SWITCH_COOKIE,
        flash=flash,
        redirect=redirect,
        request=request,
        session=session,
        url_for=url_for,
    )

from Department.财务部.tk_expenses import register_tk_expenses
register_tk_expenses(app, require_permission)
from Department.财务部.tk_payments import register_tk_payments
register_tk_payments(app, require_permission)




from Department.人力资源与行政部.routes import register_hr_routes
register_hr_routes(app, require_permission)


from Department.menu_routes import register_department_menu_routes
register_department_menu_routes(app, require_permission)
from Department.财务部.routes import register_finance_routes
register_finance_routes(app, require_permission)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return _portal_session_pages.uploaded_file(
        filename,
        INNOVATION_APP_CONFIG=INNOVATION_APP_CONFIG,
        _safe_debug_print=_safe_debug_print,
        send_from_directory=send_from_directory,
    )


@app.route('/public-downloads/apr16-video')
def public_download_apr16_video():
    return _portal_session_pages.public_download_apr16_video(
        _PUBLIC_DOWNLOAD_APR16_VIDEO=_PUBLIC_DOWNLOAD_APR16_VIDEO,
        os=os,
        send_file=send_file,
    )


@app.route('/<filename>.html')
def serve_static_html_files(filename):
    return _portal_session_pages.serve_static_html_files(
        filename,
        _safe_debug_print=_safe_debug_print,
        send_from_directory=send_from_directory,
    )


# 飞书授权相关路由
@app.route('/login')
def login():
    return _portal_session_pages.login(
        _safe_debug_print=_safe_debug_print,
        redirect=redirect,
        request=request,
        url_for=url_for,
    )


@app.route('/feishu/auth')
def feishu_auth():
    return _feishu_callback_routes.feishu_auth(
        get_feishu_auth_url=get_feishu_auth_url,
        redirect=redirect,
        request=request,
        session=session,
    )



@app.route('/feishu/callback', methods=['GET', 'POST'])
def feishu_callback():
    return _feishu_callback_routes.feishu_callback(
        FEISHU_CONFIG=FEISHU_CONFIG,
        _bind_feishu_session=_bind_feishu_session,
        _clear_feishu_identity_session=_clear_feishu_identity_session,
        _event_mentions_bot=_event_mentions_bot,
        _extract_all_text=_extract_all_text,
        _feishu_extract_cloud_doc_url_from_event=_feishu_extract_cloud_doc_url_from_event,
        _feishu_find_cloud_doc_url_any=_feishu_find_cloud_doc_url_any,
        _feishu_recent_events=_feishu_recent_events,
        _feishu_recent_events_limit=_feishu_recent_events_limit,
        _feishu_try_decrypt_callback_data=_feishu_try_decrypt_callback_data,
        _handle_feishu_cloud_doc_mention_event=_handle_feishu_cloud_doc_mention_event,
        _safe_debug_print=_safe_debug_print,
        _xiaotu_handle_report_card_action=_xiaotu_handle_report_card_action,
        datetime=datetime,
        handle_feishu_event=handle_feishu_event,
        handle_feishu_message_event=handle_feishu_message_event,
        jsonify=jsonify,
        permission_manager=permission_manager,
        re=re,
        redirect=redirect,
        request=request,
        session=session,
        url_for=url_for,
    )



@app.route('/api/user/permissions')
def get_user_permissions():
    return _permission_admin_routes.get_user_permissions(
        get_feishu_auth_url=get_feishu_auth_url,
        jsonify=jsonify,
        permission_manager=permission_manager,
        session=session,
    )



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
    return _permission_admin_routes.permission_management(
        render_template=render_template,
        request=request,
        url_for=url_for,
    )



@app.route('/api/admin/permission_overview', methods=['GET'])
@require_permission('admin_functions')
def permission_overview():
    return _permission_admin_routes.permission_overview(
        jsonify=jsonify,
        permission_manager=permission_manager,
    )



@app.route('/api/admin/search_user', methods=['POST'])
@require_permission('admin_functions')
def search_user():
    return _permission_admin_routes.search_user(
        jsonify=jsonify,
        permission_manager=permission_manager,
        request=request,
    )



@app.route('/api/admin/grant_permission', methods=['POST'])
@require_permission('admin_functions')
def grant_permission():
    return _permission_admin_routes.grant_permission(
        jsonify=jsonify,
        permission_manager=permission_manager,
        request=request,
        session=session,
    )



@app.route('/api/admin/revoke_permission', methods=['POST'])
@require_permission('admin_functions')
def revoke_permission():
    return _permission_admin_routes.revoke_permission(
        jsonify=jsonify,
        permission_manager=permission_manager,
        request=request,
        session=session,
    )



@app.route('/api/admin/reset_permission', methods=['POST'])
@require_permission('admin_functions')
def reset_permission():
    return _permission_admin_routes.reset_permission(
        jsonify=jsonify,
        permission_manager=permission_manager,
        request=request,
    )



@app.route('/logout')
def logout():
    return _portal_session_pages.logout(
        _clear_feishu_user_access_token=_clear_feishu_user_access_token,
        redirect=redirect,
        session=session,
        url_for=url_for,
    )


@app.route('/reauth')
def reauth():
    return _portal_session_pages.reauth(
        _clear_feishu_user_access_token=_clear_feishu_user_access_token,
        _safe_debug_print=_safe_debug_print,
        permission_manager=permission_manager,
        redirect=redirect,
        session=session,
        url_for=url_for,
    )


if __name__ == '__main__':
    start_home_snapshot_worker(app)
    local_superadmin = env('TC_LOCAL_SUPERADMIN', '0') == '1'
    app.config['LOCAL_SUPERADMIN_LOOPBACK_BOUND'] = local_superadmin
    debug_mode = str(os.environ.get("TC_FLASK_DEBUG", "")).strip().lower() in {"1", "true", "yes", "on"}
    if env("TC_BACKGROUND_JOBS", "1") == "1" and ((not debug_mode) or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'):
        _start_xiaotu_report_reminder_thread_once()
        innovation_pending_reminder.start()
        tk_customer_service_tracking_reminder.start()
        lunch_push.start()
    app.run(
        debug=debug_mode,
        host=env("TC_WEB_HOST") or ('127.0.0.1' if local_superadmin else '0.0.0.0'),
        port=env_int("TC_WEB_PORT", 8000),
        use_reloader=False,
    )
# 飞书原生视频消息接口的上传限制低于大文件上传需求，超过约 30MB 会被接口拒绝。
FEISHU_NATIVE_VIDEO_MAX_BYTES = 30 * 1024 * 1024
