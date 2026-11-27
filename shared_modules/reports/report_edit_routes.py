"""Prepare report edits and scope report history exports."""

from __future__ import annotations


def api_xiaotu_report_prepare_edit(
    *,
    _feishu_recall_message,
    _is_mobile_request,
    _xiaotu_collect_report_card_message_entries,
    _xiaotu_forget_report_card_messages,
    _xiaotu_get_report_delivery_status,
    _xiaotu_get_report_row,
    _xiaotu_set_report_edit_ready_session,
    jsonify,
    request,
    session,
    url_for,
):
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


def api_xiaotu_report_edit_payload(
    *,
    _feishu_build_cloud_doc_url,
    _xiaotu_extract_source_doc_token,
    _xiaotu_get_report_edit_ready_session,
    _xiaotu_get_report_row,
    _xiaotu_person_type_to_value,
    _xiaotu_report_type_from_kind,
    _xiaotu_split_cache_multi_value,
    jsonify,
    re,
    request,
    session,
):
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


def _xiaotu_build_report_history_export_context(
    args,
    session_user_name,
    *,
    _current_user_has_permission,
    _xiaotu_build_name_match_clause,
    _xiaotu_collect_notify_user_names_by_department_names,
    _xiaotu_get_report_history_scope,
    _xiaotu_list_notify_departments,
    _xiaotu_list_notify_users_current_app_cached,
    _xiaotu_sql_escape,
    datetime,
):
    request_debug_mode = str(args.get('debug_scope_mode') or '').strip().lower()
    history_debug_enabled = _current_user_has_permission('xiaotu_report_history_debug')
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
    for date_value in (date_start, date_end):
        if date_value:
            try:
                datetime.strptime(date_value, "%Y-%m-%d")
            except ValueError:
                raise ValueError("日期格式无效，请重新选择")
    if date_start and date_end and date_end < date_start:
        raise ValueError("结束日期不能早于开始日期")
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
