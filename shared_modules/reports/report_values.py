"""Normalize report types, dates and source references."""

from __future__ import annotations


def _xiaotu_report_history_can_view_all_uploads(
    user_name,
    *,
    _current_user_has_permission,
):
    return _current_user_has_permission('xiaotu_report_history_all')


def _xiaotu_get_report_history_debug_options(
    user_name,
    *,
    _current_user_has_permission,
):
    if not _current_user_has_permission('xiaotu_report_history_debug'):
        return []
    return [
        {"value": "current", "label": "当前真实权限"},
        {"value": "self_only", "label": "普通用户视角"},
        {"value": "all_uploads", "label": "全量查看视角"},
        {"value": "operation_only", "label": "运营部门受限视角"},
    ]


def _xiaotu_match_doc_permission(doc_item, user_depts):
    allowed = doc_item.get("allowed_departments")
    if allowed == "all":
        return True
    if not isinstance(allowed, list):
        return False
    my_set = {str(x or "").strip() for x in (user_depts or []) if str(x or "").strip()}
    allow_set = {str(x or "").strip() for x in (allowed or []) if str(x or "").strip()}
    return bool(my_set & allow_set)


def _xiaotu_build_report_instance_id(
    doc_token,
    *,
    datetime,
):
    token = str(doc_token or "").strip()
    ts_part = datetime.now().strftime("%Y%m%d%H%M%S%f")
    if token:
        return f"{token}__{ts_part}"[:120]
    return f"manual__{ts_part}"[:120]


def _xiaotu_build_report_title(
    user_name,
    report_kind,
    date_text,
    *,
    datetime,
):
    date_part = str(date_text or datetime.now().strftime('%Y-%m-%d')).strip() or datetime.now().strftime('%Y-%m-%d')
    name_part = str(user_name or '').strip() or '未知用户'
    kind_part = str(report_kind or '').strip() or '周报'
    return f"{date_part} {name_part} {kind_part}"[:200]


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


def _xiaotu_build_today_daily_search_keys(
    now_dt,
    *,
    _xiaotu_build_date_search_keys,
    datetime,
):
    now = now_dt if isinstance(now_dt, datetime) else datetime.now()
    return _xiaotu_build_date_search_keys(
        f"{now.year}-{now.month:02d}-{now.day:02d}"
    )


def _xiaotu_count_daily_date_headings(
    text,
    *,
    _xiaotu_find_daily_date_matches,
    _xiaotu_is_daily_date_heading,
):
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


def _xiaotu_get_period_range(
    report_type,
    *,
    datetime,
    timedelta,
):
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


def _xiaotu_parse_date_value(
    value,
    fallback,
    *,
    datetime,
):
    raw = str(value or "").strip()
    if not raw:
        return fallback
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    return fallback


def _xiaotu_report_image_url(
    path_value,
    *,
    quote,
    relocate_storage_path,
    url_for,
):
    raw = relocate_storage_path(path_value)
    if not raw:
        return ""
    if raw.startswith("/api/xiaotu/report_image"):
        return raw
    try:
        return url_for("api_xiaotu_report_image", path=raw)
    except Exception:
        return "/api/xiaotu/report_image?path=" + quote(raw)


def _xiaotu_save_history_analysis_file(
    user_name,
    start_date,
    end_date,
    html_text,
    *,
    _XIAOTU_REPORT_HISTORY_ANALYSIS_DIR,
    datetime,
    os,
    re,
):
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


def _xiaotu_resolve_redirect_url(
    endpoint_name,
    fallback,
    *,
    url_for,
):
    target = str(endpoint_name or "").strip()
    if not target:
        target = fallback
    try:
        return url_for(target)
    except Exception:
        return url_for(fallback)


def _xiaotu_extract_url_from_text(
    text,
    *,
    re,
):
    s = str(text or "").replace("`", "").strip()
    m = re.search(r"https?://[^\s\u3002\uff0c,]+", s)
    if not m:
        return ""
    return str(m.group(0) or "").strip().rstrip(")")


def _xiaotu_parse_image_path_list(
    raw_paths,
    *,
    relocate_storage_path,
):
    return [relocate_storage_path(x) for x in str(raw_paths or "").split("|") if str(x or "").strip()]


def _xiaotu_image_file_name(raw_path):
    txt = str(raw_path or "").strip().replace("\\", "/")
    if not txt:
        return ""
    return str(txt.split("/")[-1] or "").strip()


def dashboard_xiaotu(
    *,
    _get_feishu_user_access_token,
    redirect,
    render_template,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu')
        return redirect(url_for('feishu_auth'))
    user_access_token = _get_feishu_user_access_token()
    if not user_access_token:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu')
        return redirect(url_for('feishu_auth'))
    user_name = session.get('feishu_user_name', '用户')
    return render_template('日报与报告/xiaotu_dashboard.html', user_name=user_name)


def api_xiaotu_delete_doc(
    doc_id,
    *,
    _xiaotu_get_user_saved_docs,
    _xiaotu_set_user_saved_docs,
    jsonify,
    session,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    target = str(doc_id or '').strip()
    rows = _xiaotu_get_user_saved_docs(user_id)
    next_rows = [x for x in rows if str((x or {}).get('id') or '').strip() != target]
    _xiaotu_set_user_saved_docs(user_id, next_rows)
    return jsonify({'success': True})
