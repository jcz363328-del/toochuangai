"""Serve report notifications, reminder status and image attachments."""

from __future__ import annotations


def _xiaotu_remember_report_owner_open_id(
    wendangid,
    open_id,
    *,
    _xiaotu_report_owner_open_id_map,
):
    wid = str(wendangid or "").strip()
    oid = str(open_id or "").strip()
    if not wid or not oid.startswith("ou_"):
        return
    _xiaotu_report_owner_open_id_map[wid] = oid


def _xiaotu_get_report_owner_open_id(
    wendangid,
    *,
    _xiaotu_report_owner_open_id_map,
):
    wid = str(wendangid or "").strip()
    if not wid:
        return ""
    return str(_xiaotu_report_owner_open_id_map.get(wid) or "").strip()


def api_xiaotu_report_notify_config(
    *,
    _xiaotu_get_report_cache,
    _xiaotu_normalize_notify_time,
    _xiaotu_parse_notify_open_ids,
    _xiaotu_parse_notify_targets,
    _xiaotu_resolve_notify_names,
    _xiaotu_resolve_notify_open_ids,
    _xiaotu_upsert_report_cache_notify,
    jsonify,
    request,
    session,
):
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


def api_xiaotu_report_test_reminder(
    *,
    _xiaotu_get_report_cache,
    _xiaotu_has_report_submitted_today,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_normalize_notify_time,
    _xiaotu_send_missing_report_reminder,
    jsonify,
    request,
    session,
):
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


def api_xiaotu_report_reminder_logs(
    *,
    _xiaotu_report_reminder_lock,
    _xiaotu_report_reminder_logs,
    _xiaotu_report_reminder_sent_marks,
    _xiaotu_report_reminder_thread_started,
    _xiaotu_user_open_id_cache,
    jsonify,
    os,
    request,
):
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


def api_xiaotu_report_image(
    *,
    jsonify,
    os,
    parse_qs,
    relocate_storage_path,
    request,
    send_file,
    unquote,
    urlparse,
):
    try:
        raw_path = str(request.args.get('path') or '').strip()
        if not raw_path:
            return jsonify({'success': False, 'message': '缺少图片路径'}), 400
        allowed_base_dirs = [
            os.path.abspath(relocate_storage_path(r"D:\tuchuangai\报告图片")),
            os.path.abspath(relocate_storage_path(r"D:\tuchuangai\报告缓存图片"))
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
