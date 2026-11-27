"""Handlers for dashboard identity selection and permission simulation."""


def _dashboard_identity_switch_state_from_request(
    BadSignature,
    SignatureExpired,
    _DASHBOARD_IDENTITY_SWITCH_COOKIE,
    _DASHBOARD_IDENTITY_SWITCH_MAX_AGE_SECONDS,
    _can_dashboard_switch_identity,
    _dashboard_identity_switch_operator_open_id,
    _dashboard_identity_switch_state_serializer,
    _normalize_feishu_user_name,
    request,
):
    token = str(request.cookies.get(_DASHBOARD_IDENTITY_SWITCH_COOKIE) or '').strip()
    if not token or not _can_dashboard_switch_identity():
        return None
    try:
        payload = _dashboard_identity_switch_state_serializer().loads(
            token,
            max_age=_DASHBOARD_IDENTITY_SWITCH_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    operator_open_id = str(payload.get('o') or '').strip()
    user_open_id = str(payload.get('u') or '').strip()
    user_name = _normalize_feishu_user_name(payload.get('n'), fallback='').strip()
    departments = payload.get('d') or []
    if isinstance(departments, str):
        departments = [departments]
    if (
        operator_open_id != _dashboard_identity_switch_operator_open_id()
        or not user_open_id.startswith(('ou_', 'ou-'))
        or not user_name
        or not isinstance(departments, list)
    ):
        return None
    return {
        'departments': [
            str(name).strip() for name in departments if str(name).strip()
        ],
        'user_name': user_name,
        'user_open_id': user_open_id,
        'updated_at': str(payload.get('t') or '').strip(),
    }



def _dashboard_identity_switch_selected_member(
    selection_token,
    BadSignature,
    SignatureExpired,
    _dashboard_identity_switch_serializer,
    _normalize_feishu_user_name,
):
    token = str(selection_token or '').strip()
    if not token:
        return None
    try:
        member = _dashboard_identity_switch_serializer().loads(token, max_age=600)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(member, dict):
        return None
    open_id = str(member.get('open_id') or '').strip()
    name = _normalize_feishu_user_name(member.get('name'), fallback='').strip()
    if not open_id.startswith(('ou_', 'ou-')) or not name:
        return None
    return {'open_id': open_id, 'name': name}



def _dashboard_identity_switch_departments(
    open_id,
    permission_manager,
):
    rows = permission_manager.get_user_departments(open_id) or []
    departments = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get('status') or '').strip().lower() == 'invalid':
            continue
        name = str(row.get('name') or '').strip()
        if not name or name in seen:
            continue
        seen.add(name)
        departments.append(name)
    return departments



def api_dashboard_identity_switch_members(
    _can_dashboard_switch_identity,
    _dashboard_identity_switch_forbidden_response,
    _dashboard_identity_switch_selection_token,
    _normalize_feishu_user_name,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_query_user_names_by_open_ids,
    _xiaotu_search_notify_users,
    app,
    jsonify,
    request,
):
    if not _can_dashboard_switch_identity():
        return _dashboard_identity_switch_forbidden_response()
    keyword = _normalize_feishu_user_name(
        request.args.get('q') or request.args.get('keyword') or '',
        fallback='',
    ).strip()
    if not keyword:
        return jsonify({'success': True, 'data': [], 'keyword': ''})
    try:
        members = _xiaotu_search_notify_users(keyword, limit=30)
        if not members:
            exact_open_id = str(_xiaotu_lookup_open_id_by_name(keyword) or '').strip()
            if exact_open_id.startswith(('ou_', 'ou-')):
                resolved_names = _xiaotu_query_user_names_by_open_ids([exact_open_id]) or {}
                resolved_name = _normalize_feishu_user_name(
                    resolved_names.get(exact_open_id) or keyword,
                    fallback=keyword,
                ).strip()
                members = [{
                    'open_id': exact_open_id,
                    'name': resolved_name,
                    'display_name': resolved_name,
                }]
        payload = []
        seen = set()
        for member in members or []:
            if not isinstance(member, dict):
                continue
            open_id = str(member.get('open_id') or '').strip()
            name = _normalize_feishu_user_name(
                member.get('name') or member.get('display_name') or '',
                fallback='',
            ).strip()
            if not open_id.startswith(('ou_', 'ou-')) or not name or open_id in seen:
                continue
            seen.add(open_id)
            payload.append({
                'open_id': open_id,
                'name': name,
                'selection_token': _dashboard_identity_switch_selection_token(open_id, name),
            })
        return jsonify({'success': True, 'data': payload, 'keyword': keyword})
    except Exception as exc:
        app.logger.exception('Failed to search dashboard identity-switch members')
        return jsonify({
            'success': False,
            'message': f'成员搜索失败：{exc}',
            'data': [],
        }), 500



def api_dashboard_identity_switch(
    _DASHBOARD_IDENTITY_SWITCH_COOKIE,
    _can_dashboard_switch_identity,
    _dashboard_identity_switch_departments,
    _dashboard_identity_switch_forbidden_response,
    _dashboard_identity_switch_selected_member,
    _dashboard_identity_switch_state_token,
    _normalize_feishu_user_name,
    _xiaotu_query_user_names_by_open_ids,
    app,
    datetime,
    jsonify,
    request,
    session,
):
    if not _can_dashboard_switch_identity():
        return _dashboard_identity_switch_forbidden_response()
    data = request.get_json(silent=True) or {}
    selected_member = _dashboard_identity_switch_selected_member(
        data.get('selection_token'),
    )
    if not selected_member:
        return jsonify({
            'success': False,
            'message': '请先搜索并选择有效的飞书成员',
        }), 400
    open_id = selected_member['open_id']

    try:
        resolved_names = _xiaotu_query_user_names_by_open_ids([open_id]) or {}
        resolved_name = _normalize_feishu_user_name(
            resolved_names.get(open_id) or selected_member.get('name'),
            fallback='',
        ).strip()
        if not resolved_name:
            return jsonify({'success': False, 'message': '无法确认该成员的飞书身份'}), 400
        departments = _dashboard_identity_switch_departments(open_id)
    except Exception as exc:
        app.logger.exception('Failed to resolve dashboard identity-switch member')
        return jsonify({
            'success': False,
            'message': f'读取成员身份失败：{exc}',
        }), 500

    updated_at = datetime.now().isoformat()
    for key in (
        'permission_debug_departments',
        'permission_debug_user_name',
        'permission_debug_user_open_id',
        'permission_debug_updated_at',
        '_business_analysis_access',
        '_business_analysis_scope',
        '_business_analysis_scope_with_leader',
    ):
        session.pop(key, None)
    session.pop('preloaded_functions', None)
    session.pop('preloaded_departments', None)
    session.pop('preload_time', None)
    session.modified = True
    app.logger.info(
        'Dashboard identity switched: operator=%s target=%s target_open_id=%s departments=%s',
        _normalize_feishu_user_name(session.get('feishu_user_name'), fallback=''),
        resolved_name,
        open_id,
        '、'.join(departments),
    )
    response = jsonify({
        'success': True,
        'message': f'已切换为 {resolved_name}',
        'data': {
            'user_name': resolved_name,
            'open_id': open_id,
            'departments': departments,
        },
    })
    response.set_cookie(
        _DASHBOARD_IDENTITY_SWITCH_COOKIE,
        _dashboard_identity_switch_state_token(
            open_id,
            resolved_name,
            departments,
            updated_at,
        ),
        httponly=True,
        secure=request.is_secure,
        samesite='Lax',
        path='/',
    )
    return response



def api_ai_permission_debug_status(
    _permission_debug_available_departments,
    _permission_debug_session_state,
    jsonify,
):
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



def api_ai_permission_debug_switch(
    _normalize_feishu_user_name,
    _permission_debug_available_departments,
    _permission_debug_session_state,
    _xiaotu_lookup_open_id_by_name,
    datetime,
    jsonify,
    permission_manager,
    request,
    session,
):
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



def permission_debug_clear(
    _DASHBOARD_IDENTITY_SWITCH_COOKIE,
    flash,
    redirect,
    request,
    session,
    url_for,
):
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
    response = redirect(url_for('dashboard_mobile' if to_mobile else 'dashboard'))
    response.delete_cookie(
        _DASHBOARD_IDENTITY_SWITCH_COOKIE,
        path='/',
        samesite='Lax',
    )
    return response

