"""Daily report reminder scheduling and dispatch."""

from __future__ import annotations


def _xiaotu_has_report_submitted_today(
    user_name,
    now_dt,
    *,
    _xiaotu_sql_escape,
    datetime,
    sf_db,
    timedelta,
):
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


def _xiaotu_list_due_report_reminders(
    target_hhmm,
    *,
    _XIAOTU_REPORT_CACHE_TABLE_PRIMARY,
    _xiaotu_normalize_notify_time,
    _xiaotu_sql_escape,
    sf_db,
):
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


def _xiaotu_build_report_reminder_text(
    user_name,
    notify_time,
    *,
    _xiaotu_build_report_center_url,
    _xiaotu_normalize_notify_time,
    datetime,
):
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


def _xiaotu_build_report_center_url(
    *,
    _XIAOTU_REPORT_CENTER_PUBLIC_URL,
    request,
    url_for,
    urlparse,
):
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


def _xiaotu_send_missing_report_reminder(
    receive_id,
    receive_id_type,
    user_name,
    notify_time,
    *,
    _feishu_send_message_detail,
    _feishu_send_text,
    _xiaotu_build_missing_report_reminder_card,
    _xiaotu_build_report_reminder_text,
):
    card = _xiaotu_build_missing_report_reminder_card(user_name, notify_time)
    ok, _ = _feishu_send_message_detail(receive_id, receive_id_type, "interactive", card)
    if ok:
        return True
    return _feishu_send_text(receive_id, receive_id_type, _xiaotu_build_report_reminder_text(user_name, notify_time))


def _xiaotu_run_report_reminder_once(
    now_dt,
    *,
    _safe_debug_print,
    _xiaotu_append_report_reminder_log,
    _xiaotu_get_cached_open_id_by_name,
    _xiaotu_has_report_submitted_today,
    _xiaotu_list_due_report_reminders,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_normalize_notify_time,
    _xiaotu_report_reminder_lock,
    _xiaotu_report_reminder_sent_marks,
    _xiaotu_report_reminder_thread_started,
    _xiaotu_send_missing_report_reminder,
    datetime,
):
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


def _xiaotu_report_reminder_loop(
    *,
    _safe_debug_print,
    _xiaotu_append_report_reminder_log,
    _xiaotu_run_report_reminder_once,
    app,
    time,
):
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
