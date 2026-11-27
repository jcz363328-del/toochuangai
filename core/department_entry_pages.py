"""Portal department entry pages and navigation state."""

from __future__ import annotations


def api_menu_click(
    *,
    dui_db,
    jsonify,
    request,
    session,
):
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


def api_dashboard_favorites_context(
    *,
    _permission_debug_effective_state,
    jsonify,
    session,
):
    """Return the same identity key used by the dashboard's local favorites."""
    debug_state = _permission_debug_effective_state()
    user_key = (
        str(debug_state.get('user_name') or '').strip()
        or str(session.get('feishu_user_id') or '').strip()
        or str(session.get('feishu_user_name') or '').strip()
        or 'guest'
    )
    return jsonify({'success': True, 'user_key': user_key})
