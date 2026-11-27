"""Authorize business analysis requests for the active portal identity."""

import time
from functools import wraps

from flask import flash, jsonify, redirect, request, session, url_for


def require_business_analysis_access(view, *, identity_cache_key, check_user_permission):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = str(session.get('feishu_user_id') or '').strip()
        identity_key = '|'.join((
            'permission-grants-v2',
            user_id,
            identity_cache_key(),
        ))
        cached = session.get('_business_analysis_access')
        allowed = None
        if isinstance(cached, dict):
            cached_at = float(cached.get('cached_at') or 0)
            if cached.get('identity') == identity_key and time.time() - cached_at < 60:
                allowed = bool(cached.get('allowed'))
        if allowed is None:
            try:
                allowed, _ = check_user_permission(
                    user_id,
                    'business_analysis',
                )
            except Exception:
                allowed = False
            session['_business_analysis_access'] = {
                'identity': identity_key,
                'cached_at': time.time(),
                'allowed': bool(allowed),
            }
        if allowed:
            return view(*args, **kwargs)
        message = "当前账号未获经营分析权限，请联系管理员在权限表中开通"
        if request.path.startswith('/api/'):
            return jsonify({
                'error': {'code': 'BUSINESS_ANALYSIS_FORBIDDEN', 'message': message}
            }), 403
        flash(message, 'error')
        return redirect(url_for('dashboard'))

    return wrapped
