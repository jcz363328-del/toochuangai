"""Build main dashboard pages and their store tier summaries."""

from __future__ import annotations


def _build_dashboard_store_tier_index(
    snapshot,
    *,
    normalize_person_name,
):
    """Build a small latest-day lookup for the dashboard header."""
    if not isinstance(snapshot, dict):
        return '', {}

    rows = snapshot.get('rows')
    if not isinstance(rows, list):
        return '', {}

    data_date = str(snapshot.get('maxDate') or '').strip()
    if not data_date:
        data_date = max(
            (str(row.get('date') or '').strip() for row in rows if isinstance(row, dict)),
            default='',
        )

    by_operator = {}
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or str(row.get('date') or '').strip() != data_date:
            continue
        operator = normalize_person_name(row.get('operator'))
        store = str(row.get('store') or '').strip()
        tier = str(row.get('tier') or '').strip()
        if not operator or not store or not tier:
            continue
        unique_key = (operator, store)
        if unique_key in seen:
            continue
        seen.add(unique_key)
        by_operator.setdefault(operator, []).append({'store': store, 'tier': tier})

    def store_sort_key(item):
        store = item.get('store', '')
        return (0, int(store)) if store.isdigit() else (1, store)

    for items in by_operator.values():
        items.sort(key=store_sort_key)
    return data_date, by_operator


def _get_dashboard_store_tiers(
    user_name,
    *,
    _BUSINESS_ANALYSIS_TIER_HISTORY_SNAPSHOT_PATH,
    _build_dashboard_store_tier_index,
    _dashboard_store_tier_cache,
    _dashboard_store_tier_cache_lock,
    _safe_debug_print,
    json,
    normalize_person_name,
    os,
):
    """Return only the signed-in operator's latest store tiers, cached by snapshot mtime."""
    operator = normalize_person_name(user_name)
    if not operator:
        return '', []
    try:
        mtime_ns = os.stat(_BUSINESS_ANALYSIS_TIER_HISTORY_SNAPSHOT_PATH).st_mtime_ns
        with _dashboard_store_tier_cache_lock:
            if _dashboard_store_tier_cache['mtime_ns'] != mtime_ns:
                with open(_BUSINESS_ANALYSIS_TIER_HISTORY_SNAPSHOT_PATH, 'r', encoding='utf-8') as handle:
                    snapshot = json.load(handle)
                data_date, by_operator = _build_dashboard_store_tier_index(snapshot)
                _dashboard_store_tier_cache.update({
                    'mtime_ns': mtime_ns,
                    'data_date': data_date,
                    'by_operator': by_operator,
                })
            return (
                _dashboard_store_tier_cache['data_date'],
                list(_dashboard_store_tier_cache['by_operator'].get(operator, [])),
            )
    except (OSError, ValueError, TypeError) as exc:
        _safe_debug_print(f"Dashboard store tier snapshot unavailable: {exc}")
        return '', []


def dashboard(
    *,
    _can_access_ai_workspace,
    _can_dashboard_switch_identity,
    _current_user_has_permission,
    _debug_log_elapsed,
    _get_dashboard_store_tiers,
    _is_mobile_request,
    _normalize_dashboard_functions,
    _permission_debug_session_state,
    _resolve_feishu_user_name,
    _safe_debug_print,
    _sync_feishu_identity_via_current_app,
    dashboard_workspace_catalog,
    datetime,
    permission_manager,
    redirect,
    render_template,
    request,
    session,
    time,
    url_for,
):
    """主控制台"""
    dashboard_started_at = time.perf_counter()
    force_desktop = str(request.args.get('desktop') or '').strip() in {'1', 'true', 'yes'}
    if (not force_desktop) and _is_mobile_request():
        _debug_log_elapsed("dashboard_redirect_mobile", dashboard_started_at, path=request.path)
        return redirect(url_for('dashboard_mobile'))
    _safe_debug_print(f"\n=== Dashboard路由处理 ===")

    # 首先尝试从飞书上下文获取用户信息（免登录）
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    user_department = session.get('user_department')
    login_time = session.get('login_time')

    _safe_debug_print(f"👤 用户ID: {user_id}")
    _safe_debug_print(f"📛 用户名: {user_name}")
    _safe_debug_print(f"🏢 用户部门: {user_department}")
    _safe_debug_print(f"⏰ 登录时间: {login_time}")
    _safe_debug_print(f"🔑 Session Keys: {list(session.keys())}")

    # 如果session中没有用户信息，尝试从飞书上下文获取
    if not user_id:
        _safe_debug_print(f"🔍 Session中无用户信息，开始获取...")
        # 检查是否为本地开发环境
        is_local_dev = request.host.startswith('127.0.0.1') or request.host.startswith('localhost')

        if is_local_dev:
            _safe_debug_print(f"🔧 本地开发环境，跳转到开发者登录")
            # 本地开发环境，跳转到开发者登录
            return redirect(url_for('dev_login', user_type='bd'))

        # 统一通过当前应用获取用户信息
        dashboard_identity_started_at = time.perf_counter()
        user_info = _sync_feishu_identity_via_current_app(force_refresh=True)
        _debug_log_elapsed(
            "dashboard_identity_sync",
            dashboard_identity_started_at,
            ok=bool(user_info),
            path=request.path
        )

        if user_info:
            user_id = str(session.get('feishu_user_id') or user_info.get('user_id') or '').strip()
            user_name = str(session.get('feishu_user_name') or _resolve_feishu_user_name(user_info, fallback='飞书用户')).strip()
            _safe_debug_print(f"✅ Dashboard飞书识别成功 - 用户: {user_id}")

    _safe_debug_print(f"🔍 Dashboard访问 - 用户ID: {user_id}, 用户名: {user_name}")

    # 如果用户已登录，获取其可访问的功能
    accessible_functions = []
    if user_id:
        # 检查是否有预加载的数据
        preloaded_functions = session.get('preloaded_functions')
        preload_time_str = session.get('preload_time')

        # 检查预加载数据是否有效（5分钟内）
        use_preloaded = False
        if preloaded_functions and preload_time_str:
            try:
                preload_time = datetime.fromisoformat(preload_time_str)
                time_diff = (datetime.now() - preload_time).total_seconds()
                if time_diff < 300:  # 5分钟内有效
                    use_preloaded = True
                    _safe_debug_print(f"🚀 使用预加载数据，预加载时间: {time_diff:.1f}秒前")
            except Exception as e:
                _safe_debug_print(f"⚠️ 预加载时间解析失败: {e}")

        if use_preloaded:
            accessible_functions = preloaded_functions
            _safe_debug_print(f"✅ 使用预加载权限数据，可访问功能数量: {len(accessible_functions)}")
            if len(accessible_functions) <= 1:
                _safe_debug_print("🔄 预加载功能数量过少，尝试重新获取用户可访问功能...")
                try:
                    permissions_started_at = time.perf_counter()
                    accessible_functions = permission_manager.get_user_accessible_functions(user_id)
                    _debug_log_elapsed(
                        "dashboard_permissions_reload",
                        permissions_started_at,
                        user_id=user_id,
                        function_count=len(accessible_functions or [])
                    )
                    _safe_debug_print(f"✅ 重新获取用户权限成功，可访问功能数量: {len(accessible_functions)}")
                    session.pop('preloaded_functions', None)
                    session.pop('preload_time', None)
                except Exception as e:
                    _debug_log_elapsed("dashboard_permissions_reload_failed", permissions_started_at, user_id=user_id, error=str(e))
                    _safe_debug_print(f"❌ 重新获取用户权限失败: {e}")
        else:
            _safe_debug_print(f"🔍 预加载数据无效或过期，重新获取用户可访问功能...")
            try:
                permissions_started_at = time.perf_counter()
                accessible_functions = permission_manager.get_user_accessible_functions(user_id)
                _debug_log_elapsed(
                    "dashboard_permissions_load",
                    permissions_started_at,
                    user_id=user_id,
                    function_count=len(accessible_functions or [])
                )
                _safe_debug_print(f"✅ 成功获取用户权限，可访问功能数量: {len(accessible_functions)}")
                # 更新预加载数据
                session.pop('preloaded_functions', None)
                session.pop('preload_time', None)
                for func in accessible_functions:
                    _safe_debug_print(f"   - {func.get('function_name')}: {func.get('name')} ({func.get('reason')})")
            except Exception as e:
                _debug_log_elapsed("dashboard_permissions_load_failed", permissions_started_at, user_id=user_id, error=str(e))
                _safe_debug_print(f"❌ 获取用户权限失败: {e}")
                import traceback
                traceback.print_exc()
    else:
        # 如果仍然无法获取用户信息，跳转到飞书授权
        _safe_debug_print("🔄 Dashboard未检测到用户信息，跳转到授权页面")
        return redirect(url_for('feishu_auth'))

    # 权限表或飞书部门接口短暂异常时，空结果会让整个控制台看起来没有权限。
    # 清理一次当前用户缓存并重算，最终仍以权限表结果为准。
    if not accessible_functions:
        try:
            permission_manager.clear_cache(user_id)
            accessible_functions = permission_manager.get_user_accessible_functions(user_id)
            _safe_debug_print(f"🔄 空权限结果已重算，可访问功能数量: {len(accessible_functions or [])}")
        except Exception as e:
            _safe_debug_print(f"⚠️ 空权限结果重算失败: {e}")

    _safe_debug_print(f"🎨 渲染dashboard模板...")
    _debug_log_elapsed(
        "dashboard_ready_to_render",
        dashboard_started_at,
        user_id=str(user_id or '').strip(),
        function_count=len(accessible_functions or []),
        used_preloaded=bool(use_preloaded) if user_id else False
    )
    _safe_debug_print("========================\n")

    # Keep the raw permission names as well as the normalized dashboard
    # catalog.  The catalog intentionally omits feature-hub children (for
    # example ``daily_replenishment_operation``), but those names still need to
    # be available when validating a favorite created on a hub page.
    raw_accessible_function_names = {
        str(item.get('function_name') or '').strip()
        for item in (accessible_functions or [])
        if isinstance(item, dict) and str(item.get('function_name') or '').strip()
    }
    workspace_accessible_functions = list(accessible_functions or [])
    accessible_functions = _normalize_dashboard_functions(accessible_functions)
    can_access_ai_workspace = _can_access_ai_workspace()
    if not can_access_ai_workspace:
        accessible_functions = [item for item in accessible_functions if item.get('function_name') != 'ai_dept']
    dashboard_allowed_functions = sorted(
        raw_accessible_function_names
        | {
            str(item.get('function_name') or '').strip()
            for item in accessible_functions
            if item.get('is_allowed') and str(item.get('function_name') or '').strip()
        }
    )
    permission_debug_state = _permission_debug_session_state()
    can_video_claw = _current_user_has_permission('video_claw', user_id)
    can_business_analysis = _current_user_has_permission('business_analysis', user_id)
    can_value_evaluation = _current_user_has_permission('value_evaluation', user_id)
    tier_identity_name = permission_debug_state['current_user_name'] or user_name
    dashboard_store_tier_date, dashboard_store_tiers = _get_dashboard_store_tiers(tier_identity_name)

    return render_template('主站/dashboard.html',
                           can_access_ai_workspace=can_access_ai_workspace,
                           workspace_catalog=dashboard_workspace_catalog(workspace_accessible_functions).get_json() if user_id else {},
                           user_name=user_name,
                           user_id=user_id,
                           user_department=user_department,
                           accessible_functions=accessible_functions,
                           can_video_claw=can_video_claw,
                           can_business_analysis=can_business_analysis,
                           can_value_evaluation=can_value_evaluation,
                           can_switch_identity=_can_dashboard_switch_identity(),
                           dashboard_allowed_functions=dashboard_allowed_functions,
                           dashboard_store_tier_date=dashboard_store_tier_date,
                           dashboard_store_tiers=dashboard_store_tiers,
                           permission_debug_departments=permission_debug_state['current_departments'],
                           permission_debug_user_name=permission_debug_state['current_user_name'])


def dashboard_mobile(
    *,
    _build_mobile_function_cards,
    _debug_log_elapsed,
    _permission_debug_session_state,
    _resolve_feishu_user_name,
    _sync_feishu_identity_via_current_app,
    permission_manager,
    redirect,
    render_template,
    request,
    session,
    time,
    url_for,
):
    """主控制台移动端页面"""
    dashboard_mobile_started_at = time.perf_counter()
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    user_department = session.get('user_department')

    if not user_id:
        is_local_dev = request.host.startswith('127.0.0.1') or request.host.startswith('localhost')
        if is_local_dev:
            _debug_log_elapsed("dashboard_mobile_redirect_dev_login", dashboard_mobile_started_at, path=request.path)
            return redirect(url_for('dev_login', user_type='bd'))
        dashboard_mobile_identity_started_at = time.perf_counter()
        user_info = _sync_feishu_identity_via_current_app(force_refresh=True)
        _debug_log_elapsed(
            "dashboard_mobile_identity_sync",
            dashboard_mobile_identity_started_at,
            ok=bool(user_info),
            path=request.path
        )
        if user_info:
            user_id = str(session.get('feishu_user_id') or user_info.get('user_id') or '').strip()
            user_name = str(session.get('feishu_user_name') or _resolve_feishu_user_name(user_info, fallback='飞书用户')).strip()

    if not user_id:
        _debug_log_elapsed("dashboard_mobile_redirect_auth", dashboard_mobile_started_at, path=request.path)
        return redirect(url_for('feishu_auth'))

    try:
        dashboard_mobile_permissions_started_at = time.perf_counter()
        accessible_functions = permission_manager.get_user_accessible_functions(user_id)
        _debug_log_elapsed(
            "dashboard_mobile_permissions_load",
            dashboard_mobile_permissions_started_at,
            user_id=str(user_id or '').strip(),
            function_count=len(accessible_functions or [])
        )
    except Exception:
        _debug_log_elapsed(
            "dashboard_mobile_permissions_load_failed",
            dashboard_mobile_permissions_started_at,
            user_id=str(user_id or '').strip()
        )
        accessible_functions = []

    cards = _build_mobile_function_cards(accessible_functions)
    permission_debug_state = _permission_debug_session_state()
    _debug_log_elapsed(
        "dashboard_mobile_ready_to_render",
        dashboard_mobile_started_at,
        user_id=str(user_id or '').strip(),
        function_count=len(accessible_functions or []),
        card_count=len(cards or [])
    )
    return render_template(
        '主站/dashboard_mobile.html',
        user_name=user_name,
        user_id=user_id,
        user_department=user_department,
        mobile_cards=cards,
        permission_debug_departments=permission_debug_state['current_departments'],
        permission_debug_user_name=permission_debug_state['current_user_name']
    )
