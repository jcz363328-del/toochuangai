"""Feishu identity sessions, token lifecycle and authentication guards."""

from __future__ import annotations


def _resolve_feishu_user_name(
    user_info,
    fallback,
    *,
    _normalize_feishu_user_name,
):
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


def _clear_feishu_user_access_token(
    *,
    _feishu_user_token_cache,
    _feishu_user_token_cache_lock,
    session,
):
    """Remove the user token without putting the large JWT in the browser cookie."""
    token_ref = str(session.pop('feishu_user_token_ref', '') or '').strip()
    session.pop('feishu_user_access_token', None)
    if token_ref:
        with _feishu_user_token_cache_lock:
            _feishu_user_token_cache.pop(token_ref, None)


def _set_feishu_user_access_token(
    token,
    expires_in,
    *,
    _FEISHU_USER_TOKEN_DEFAULT_TTL_SECONDS,
    _clear_feishu_user_access_token,
    _feishu_user_token_cache,
    _feishu_user_token_cache_lock,
    secrets,
    session,
    time,
):
    """Keep Feishu's large user token server-side and store only an opaque reference."""
    _clear_feishu_user_access_token()
    clean_token = str(token or '').strip()
    if not clean_token:
        return ''

    try:
        ttl_seconds = int(expires_in or 0)
    except (TypeError, ValueError):
        ttl_seconds = 0
    if ttl_seconds <= 0:
        ttl_seconds = _FEISHU_USER_TOKEN_DEFAULT_TTL_SECONDS

    token_ref = secrets.token_urlsafe(24)
    expires_at = time.time() + ttl_seconds
    with _feishu_user_token_cache_lock:
        now = time.time()
        expired_refs = [
            ref for ref, item in _feishu_user_token_cache.items()
            if float(item.get('expires_at') or 0) <= now
        ]
        for ref in expired_refs:
            _feishu_user_token_cache.pop(ref, None)
        _feishu_user_token_cache[token_ref] = {
            'token': clean_token,
            'expires_at': expires_at,
        }
    session['feishu_user_token_ref'] = token_ref
    return clean_token


def _get_feishu_user_access_token(
    *,
    _feishu_user_token_cache,
    _feishu_user_token_cache_lock,
    _set_feishu_user_access_token,
    session,
    time,
):
    """Resolve the current user's token from the server-side token cache."""
    # Migrate cookies issued by older versions without keeping the JWT client-side.
    legacy_token = str(session.get('feishu_user_access_token') or '').strip()
    if legacy_token:
        return _set_feishu_user_access_token(legacy_token)

    token_ref = str(session.get('feishu_user_token_ref') or '').strip()
    if not token_ref:
        return ''
    with _feishu_user_token_cache_lock:
        item = _feishu_user_token_cache.get(token_ref)
        if not item or float(item.get('expires_at') or 0) <= time.time():
            _feishu_user_token_cache.pop(token_ref, None)
            item = None
    if not item:
        session.pop('feishu_user_token_ref', None)
        return ''
    return str(item.get('token') or '').strip()


def _clear_feishu_identity_session(
    *,
    _clear_feishu_user_access_token,
    session,
):
    _clear_feishu_user_access_token()
    for k in [
        'feishu_user_id', 'feishu_open_id', 'feishu_tenant_user_id',
        'feishu_user_name', 'feishu_user_email', 'feishu_email',
        'feishu_avatar', 'feishu_user_access_token', 'feishu_user_token_ref', 'feishu_user_refresh_token',
        'feishu_user_access_token_expire_at', 'preloaded_departments', 'preloaded_functions',
        'preload_time', 'user_department', 'login_time',
        '_business_analysis_access', '_business_analysis_scope',
        '_business_analysis_scope_with_leader',
        'permission_debug_departments', 'permission_debug_user_name',
        'permission_debug_user_open_id', 'permission_debug_updated_at'
    ]:
        session.pop(k, None)


def _bind_feishu_session(
    user_info,
    user_access_token,
    *,
    FEISHU_CONFIG,
    _resolve_feishu_user_name,
    _set_feishu_user_access_token,
    _xiaotu_remember_user_open_id,
    app,
    datetime,
    permission_manager,
    session,
    timedelta,
):
    info = dict(user_info or {})
    token = str(user_access_token or info.get('user_access_token') or '').strip()
    open_id = str(info.get('open_id') or info.get('user_id') or '').strip()
    # 身份重新绑定后，部门与权限结果必须从当前账号重新读取，不能复用旧会话缓存。
    if open_id:
        try:
            permission_manager.clear_cache(open_id)
        except Exception:
            pass
    tenant_user_id = str(info.get('user_id') or '').strip()
    # `feishu_user_id` is the canonical permission subject and historically stores
    # open_id. Keep Feishu's tenant-scoped user_id separately so request headers are
    # only compared within the same identifier namespace.
    session['feishu_user_id'] = open_id
    session['feishu_open_id'] = open_id
    if tenant_user_id:
        session['feishu_tenant_user_id'] = tenant_user_id
    else:
        session.pop('feishu_tenant_user_id', None)
    session['feishu_user_name'] = _resolve_feishu_user_name(info, fallback='用户')
    session['feishu_user_email'] = info.get('email', '') or info.get('enterprise_email', '')
    session['feishu_email'] = info.get('email', '') or info.get('enterprise_email', '')
    session['feishu_avatar'] = info.get('avatar_url', '') or info.get('avatar', '')

    # Preserve a department hint returned by the identity provider.  It lets
    # permission checks survive a short contact API/token outage while the
    # canonical department lookup retries.  Never persist opaque Feishu IDs as
    # names because they cannot match the department names in dbo.quanxian.
    def _department_name_hint(value):
        if isinstance(value, dict):
            for key in ('name', 'department_name', 'departmentName', 'display_name'):
                hinted = _department_name_hint(value.get(key))
                if hinted:
                    return hinted
            return ''
        if isinstance(value, (list, tuple)):
            for item in value:
                hinted = _department_name_hint(item)
                if hinted:
                    return hinted
            return ''
        text = str(value or '').strip()
        if not text or text.startswith(('od-', 'ou_', 'ou-')):
            return ''
        return text

    session.pop('user_department', None)
    department_hint = ''
    for key in ('department', 'department_name', 'departmentName', 'departments'):
        department_hint = _department_name_hint(info.get(key))
        if department_hint:
            break
    if department_hint:
        session['user_department'] = department_hint

    token_expires_in = int(info.get('user_token_expires_in') or 0)
    _set_feishu_user_access_token(token, token_expires_in)
    # Refresh tokens are not used by this app and can also be too large for a
    # client-side Flask session, so never place them in the browser cookie.
    session.pop('feishu_user_refresh_token', None)
    if token_expires_in > 0:
        session['feishu_user_access_token_expire_at'] = (datetime.now() + timedelta(seconds=token_expires_in)).isoformat()
    session['login_time'] = datetime.now()
    session['feishu_identity_app_id'] = str(FEISHU_CONFIG.get('app_id') or '')
    session.permanent = True
    app.permanent_session_lifetime = timedelta(hours=24)
    _xiaotu_remember_user_open_id(session.get('feishu_user_name'), session.get('feishu_open_id'))


def _sync_feishu_identity_via_current_app(
    force_refresh,
    *,
    FEISHU_CONFIG,
    _bind_feishu_session,
    _clear_feishu_identity_session,
    _debug_log_elapsed,
    _get_feishu_user_access_token,
    _safe_debug_print,
    permission_manager,
    request,
    session,
    time,
):
    """统一通过当前飞书应用的 user_access_token 获取真实用户信息。"""
    sync_started_at = time.perf_counter()
    request_token = str(request.headers.get('X-Lark-User-Access-Token') or '').strip()
    auth_header = str(request.headers.get('Authorization') or '').strip()
    if (not request_token) and auth_header.lower().startswith('bearer '):
        request_token = auth_header[7:].strip()
    session_token = _get_feishu_user_access_token()
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


def _handle_feishu_identity_mismatch(
    is_api_request,
    *,
    jsonify,
    redirect,
    request,
    session,
    url_for,
):
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


def dev_login(
    *,
    _safe_debug_print,
    _set_feishu_user_access_token,
    _xiaotu_remember_user_open_id,
    app,
    datetime,
    is_local_superadmin,
    redirect,
    request,
    session,
    timedelta,
    url_for,
):
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
        'business_owner': {
            'user_id': 'dev_business_owner_001',
            'name': '周俊成',
            'email': 'business_owner_test@company.com',
            'department': 'AI部'
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
        },
        'operation7': {
            'user_id': 'dev_operation7_user_001',
            'name': '运营七部测试用户',
            'email': 'operation7_test@company.com',
            'department': '运营七部'
        }
    }

    user_type_was_explicit = bool(str(request.args.get('user_type') or '').strip())
    user_info = mock_users.get(user_type, mock_users['bd'])
    if is_local_superadmin() and not user_type_was_explicit:
        user_info = dict(mock_users['admin'], name='本地开发管理员')
    _safe_debug_print(f"📝 选择的用户信息: {user_info}")

    raw_name = user_info['name']
    name_parts = str(raw_name).split('（', 1)
    feishu_name = name_parts[0].strip() if name_parts else str(raw_name).strip()

    session['feishu_user_id'] = user_info['user_id']
    session['feishu_user_name'] = feishu_name or raw_name
    session['feishu_user_email'] = user_info['email']
    _set_feishu_user_access_token('dev_local_access_token')
    session['user_department'] = user_info['department']
    session['local_dev_identity_override'] = user_type_was_explicit
    session['login_time'] = datetime.now()
    session.permanent = True
    app.permanent_session_lifetime = timedelta(hours=24)
    _xiaotu_remember_user_open_id(session.get('feishu_user_name'), session.get('feishu_user_id'))

    _safe_debug_print(f"✅ 开发者模式登录成功 - {user_info['name']} ({user_info['department']})")
    _safe_debug_print(f"📝 Session信息已设置")
    _safe_debug_print(f"🔄 重定向到dashboard")
    _safe_debug_print("========================\n")

    return redirect(url_for('dashboard'))


def check_feishu_user(
    *,
    _clear_feishu_identity_session,
    _debug_log_elapsed,
    _get_feishu_user_access_token,
    _handle_feishu_identity_mismatch,
    _load_dashboard_identity_switch_request_state,
    _safe_debug_print,
    _seedance_access_allowed,
    _start_xiaotu_report_reminder_thread_once,
    _sync_feishu_identity_via_current_app,
    _xiaotu_remember_user_open_id,
    app,
    env,
    innovation_pending_reminder,
    is_local_superadmin,
    jsonify,
    lunch_push,
    redirect,
    request,
    session,
    time,
    tk_customer_service_tracking_reminder,
    url_for,
):
    """在每个请求前检查飞书用户身份"""
    current_dev_user_id = str(session.get('feishu_user_id') or '').strip()
    current_dev_department = str(session.get('user_department') or '').strip()
    has_explicit_dev_identity = bool(session.get('local_dev_identity_override')) or (
        current_dev_user_id.startswith('dev_')
        and current_dev_department
        and current_dev_department != '总经办'
    )
    if is_local_superadmin() and not has_explicit_dev_identity:
        session['feishu_user_id'] = 'dev_admin_user_001'
        session['feishu_user_name'] = '本地开发管理员'
        session['feishu_user_email'] = 'admin_test@company.com'
        session['user_department'] = '总经办'
    middleware_started_at = time.perf_counter()
    if env("TC_BACKGROUND_JOBS", "1") == "1":
        try:
            _start_xiaotu_report_reminder_thread_once()
        except Exception:
            pass
        try:
            innovation_pending_reminder.start()
        except Exception:
            pass
        try:
            tk_customer_service_tracking_reminder.start()
        except Exception:
            pass
        try:
            lunch_push.start()
        except Exception:
            app.logger.exception('订餐推送线程启动失败')
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

    # The real Feishu session can already be close to the browser's per-cookie
    # size limit because it contains access credentials. Keep impersonation in a
    # separate signed cookie and expose it to permission checks through `g`.
    _load_dashboard_identity_switch_request_state()

    # 检查是否为本地开发环境
    is_local_dev = request.host.startswith('127.0.0.1') or request.host.startswith('localhost')
    _safe_debug_print(f"🏠 本地开发环境: {is_local_dev}")

    # 检查当前session状态
    current_user_id = session.get('feishu_user_id')
    current_open_id = str(session.get('feishu_open_id') or current_user_id or '').strip()
    current_tenant_user_id = str(session.get('feishu_tenant_user_id') or '').strip()
    current_token = _get_feishu_user_access_token()
    request_token = str(request.headers.get('X-Lark-User-Access-Token') or '').strip()
    header_open_id = str(request.headers.get('X-Lark-Open-Id') or '').strip()
    header_user_id = str(request.headers.get('X-Lark-User-Id') or '').strip()
    comparable_session_identity = current_open_id if header_open_id else current_tenant_user_id
    header_identity = header_open_id or (header_user_id if current_tenant_user_id else '')
    _safe_debug_print(f"👤 当前Session用户ID: {current_user_id}")
    _safe_debug_print(f"🔑 当前Session Token存在: {bool(current_token)} | 请求头Token存在: {bool(request_token)}")
    _xiaotu_remember_user_open_id(session.get('feishu_user_name'), current_open_id)
    if header_identity:
        _safe_debug_print(f"🪪 当前请求头身份: {header_identity}")

    # 请求头身份只用于校验当前 session 是否已经串号，不直接用来认人
    if (
        (not is_local_dev)
        and current_user_id
        and header_identity
        and comparable_session_identity != header_identity
    ):
        _safe_debug_print(
            f"⚠️ 检测到飞书身份与会话不一致: "
            f"session={comparable_session_identity}, header={header_identity}"
        )
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
        has_session_token=bool(_get_feishu_user_access_token())
    )
    _safe_debug_print("========================\n")
