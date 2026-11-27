"""Build permission simulation state and signed identity selections."""

from __future__ import annotations


def _permission_debug_available_departments(*, permission_manager):
    names = set(permission_manager.get_available_permission_departments())
    for mapped in getattr(permission_manager, 'get_department_mapping_stats', lambda: {})().get('department_list', []) or []:
        name = str(mapped or '').strip()
        if name:
            names.add(name)
    return sorted(list(names), key=lambda x: x)


def _can_dashboard_switch_identity(
    *,
    _DASHBOARD_IDENTITY_SWITCH_USER_NAMES,
    _normalize_feishu_user_name,
    is_local_superadmin,
    session,
):
    """Only explicitly approved real Feishu users may impersonate another member."""
    if is_local_superadmin() and session.get('feishu_user_id'):
        return True
    if not str(session.get('feishu_user_id') or '').strip():
        return False
    real_user_name = _normalize_feishu_user_name(
        session.get('feishu_user_name'),
        fallback='',
    ).strip()
    return real_user_name in _DASHBOARD_IDENTITY_SWITCH_USER_NAMES


def _dashboard_identity_switch_forbidden_response(*, jsonify):
    return jsonify({
        'success': False,
        'message': '当前账号无权切换成员身份',
    }), 403


def _dashboard_identity_switch_serializer(
    *,
    URLSafeTimedSerializer,
    app,
):
    return URLSafeTimedSerializer(
        app.secret_key,
        salt='dashboard-identity-switch-member-v1',
    )


def _dashboard_identity_switch_state_serializer(
    *,
    URLSafeTimedSerializer,
    app,
):
    return URLSafeTimedSerializer(
        app.secret_key,
        salt='dashboard-identity-switch-state-v1',
    )


def _dashboard_identity_switch_operator_open_id(*, session):
    return str(
        session.get('feishu_open_id') or session.get('feishu_user_id') or ''
    ).strip()


def _dashboard_identity_switch_state_token(
    open_id,
    user_name,
    departments,
    updated_at,
    *,
    _dashboard_identity_switch_operator_open_id,
    _dashboard_identity_switch_state_serializer,
    _normalize_feishu_user_name,
):
    return _dashboard_identity_switch_state_serializer().dumps({
        'o': _dashboard_identity_switch_operator_open_id(),
        'u': str(open_id or '').strip(),
        'n': _normalize_feishu_user_name(user_name, fallback='').strip(),
        'd': [str(name).strip() for name in departments or [] if str(name).strip()],
        't': str(updated_at or '').strip(),
    })


def _load_dashboard_identity_switch_request_state(
    *,
    _dashboard_identity_switch_state_from_request,
    g,
):
    state = _dashboard_identity_switch_state_from_request()
    if state:
        g.permission_debug_state = state
    return state


def _permission_debug_effective_state(
    *,
    g,
    session,
):
    request_state = getattr(g, 'permission_debug_state', None)
    if isinstance(request_state, dict):
        return request_state
    return {
        'departments': session.get('permission_debug_departments') or [],
        'user_name': str(session.get('permission_debug_user_name') or '').strip(),
        'user_open_id': str(session.get('permission_debug_user_open_id') or '').strip(),
        'updated_at': str(session.get('permission_debug_updated_at') or '').strip(),
    }


def _permission_debug_identity_cache_key(*, _permission_debug_effective_state):
    state = _permission_debug_effective_state()
    return '|'.join((
        str(state.get('user_open_id') or '').strip(),
        str(state.get('updated_at') or '').strip(),
    ))


def _dashboard_identity_switch_selection_token(
    open_id,
    user_name,
    *,
    _dashboard_identity_switch_serializer,
    _normalize_feishu_user_name,
):
    return _dashboard_identity_switch_serializer().dumps({
        'open_id': str(open_id or '').strip(),
        'name': _normalize_feishu_user_name(user_name, fallback='').strip(),
    })


def _permission_debug_session_state(*, _permission_debug_effective_state):
    effective_state = _permission_debug_effective_state()
    current = effective_state.get('departments') or []
    if isinstance(current, str):
        current = [current]
    current = [str(x).strip() for x in current if str(x).strip()]
    debug_user_name = str(effective_state.get('user_name') or '').strip()
    debug_user_open_id = str(effective_state.get('user_open_id') or '').strip()
    mode = 'user' if debug_user_name else ('department' if current else '')
    return {
        'enabled': bool(mode),
        'mode': mode,
        'current_departments': current,
        'current_user_name': debug_user_name,
        'current_user_open_id': debug_user_open_id,
    }
