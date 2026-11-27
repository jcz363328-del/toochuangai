"""Resolve workspace function visibility and business analysis access scopes."""

from __future__ import annotations


def _can_access_ai_workspace(
    *,
    app,
    g,
    is_local_superadmin,
    permission_manager,
    session,
):
    if is_local_superadmin() and session.get('feishu_user_id') and not getattr(g, 'permission_debug_state', None) and not session.get('permission_debug_user_open_id'):
        g.can_access_ai_workspace = True
        return True
    cached = getattr(g, 'can_access_ai_workspace', None)
    if cached is not None:
        return cached
    user_id = str(session.get('feishu_user_id') or '').strip()
    allowed = False
    if user_id:
        try:
            rows = permission_manager.get_user_departments(user_id) or []
            names = [str(row.get('name') or '').strip() for row in rows if isinstance(row, dict)]
            signed_state = getattr(g, 'permission_debug_state', None)
            if isinstance(signed_state, dict):
                names = signed_state.get('departments') or []
            else:
                names, _ = permission_manager._resolve_effective_departments(names, 'ai_dept')
            # 飞书中的同一部门已更名为“流程与AI部”，兼容历史会话的旧名称。
            allowed = bool({'AI部', '流程与AI部'}.intersection(names))
        except Exception:
            app.logger.exception('Failed to resolve AI workspace membership')
    g.can_access_ai_workspace = allowed
    return allowed


def _get_business_analysis_scope(
    resolve_leader,
    *,
    _normalize_feishu_user_name,
    _permission_debug_effective_state,
    _permission_debug_identity_cache_key,
    _xiaotu_get_department_leader_user_id,
    g,
    permission_manager,
    resolve_business_analysis_scope,
    session,
    time,
):
    cache_key = "business_analysis_scope_with_leader" if resolve_leader else "business_analysis_scope"
    cached = getattr(g, cache_key, None)
    if isinstance(cached, dict):
        return cached

    user_id = str(session.get('feishu_user_id') or '').strip()
    user_name = _normalize_feishu_user_name(session.get('feishu_user_name'), fallback='')
    effective_identity = _permission_debug_effective_state()
    effective_user_id = str(effective_identity.get('user_open_id') or '').strip()
    effective_user_name = _normalize_feishu_user_name(
        effective_identity.get('user_name'),
        fallback='',
    ).strip()
    if effective_user_id and effective_user_name:
        user_id = effective_user_id
        user_name = effective_user_name
    identity_key = '|'.join((
        'effective-identity-v4-permission-grants',
        user_id,
        user_name,
        _permission_debug_identity_cache_key(),
    ))
    session_cache_key = f'_{cache_key}'
    session_cached = session.get(session_cache_key)
    if isinstance(session_cached, dict):
        cached_at = float(session_cached.get('cached_at') or 0)
        cached_scope = session_cached.get('scope')
        if (
            session_cached.get('identity') == identity_key
            and time.time() - cached_at < 300
            and isinstance(cached_scope, dict)
        ):
            setattr(g, cache_key, cached_scope)
            return cached_scope
    try:
        full_access, _ = permission_manager.check_user_permission(
            user_id,
            'business_analysis_all',
        )
    except Exception:
        full_access = False
    try:
        department_rows = permission_manager.get_user_departments(user_id) or []
    except Exception:
        department_rows = []
    fallback_department = str(session.get('user_department') or '').strip()
    if fallback_department and not any(
        str(row.get('name') or '').strip() == fallback_department
        for row in department_rows
        if isinstance(row, dict)
    ):
        department_rows = list(department_rows) + [{
            'department_id': f'local:{fallback_department}',
            'name': fallback_department,
            'status': 'active',
        }]

    leader_getter = (
        lambda department_id: ""
        if str(department_id or '').startswith('local:')
        else _xiaotu_get_department_leader_user_id(department_id)
    ) if resolve_leader else None
    scope = resolve_business_analysis_scope(
        user_id,
        user_name,
        department_rows,
        leader_id_getter=leader_getter,
        full_access=full_access,
    )
    if isinstance(scope, dict):
        setattr(g, cache_key, scope)
        session[session_cache_key] = {
            'identity': identity_key,
            'cached_at': time.time(),
            'scope': scope,
        }
    return scope


def _normalize_dashboard_functions(accessible_functions):
    dashboard_catalog = [
        ('innovation_proposals', '创新提案管理', '创新提案的提交、评审和管理系统'),
        ('xiaotu_qa', '报告智能体', '日报、周报和月报提交与生成'),
        ('business_analysis', '经营分析', '销售、利润、库存、履约与财年目标综合分析'),
        ('tk_customer_service', '客服', '客服跟单信息与备注管理'),
        ('tk_project_group', '内容生产工厂', '内容生产工厂专属功能模块'),
        ('operation_dept_1', '运营一部功能', '运营一部专属功能模块'),
        ('operation_dept_2', '运营二部功能', '运营二部专属功能模块'),
        ('operation_dept_3', '运营三部功能', '运营三部专属功能模块'),
        ('operation_dept_6', '运营六部功能', '运营六部专属功能模块'),
        ('operation_dept_7', '运营七部功能', '运营七部专属功能模块'),
        ('operation_fba_shipping', 'FBA追踪码/IEN查询', '查询FBA追踪码、IEN、物流单号和异常信息'),
        ('amazon_reply_agent', '亚马逊站内信回复智能体', '亚马逊站内信回复工具'),
        ('tech_dept', '技术部功能', '技术部专属功能模块'),
        ('visual_design_dept', '视觉设计部功能', '视觉设计部功能模块'),
        ('photography_dept', '摄影部功能', '摄影部专属功能模块'),
        ('ai_dept', 'AI部功能', 'AI部功能入口'),
        ('warehouse_group', '仓储部组功能', '仓储部组专属功能模块'),
        ('procurement_dept', '采购部功能', '采购部专属功能模块'),
        ('general_office', '总经办功能', '总经办专属功能模块'),
        ('rd_dept', '研发部功能', '研发部专属功能模块'),
        ('finance_dept', '财务部功能', '财务部专属功能模块'),
        ('hr_admin_dept', '人力行政部功能', '人力行政部专属功能模块'),
        ('newcomer_group', '新人组功能', '新人组专属功能模块'),
        ('shenzhen_dept', '深圳团队功能', '深圳团队专属功能模块'),
    ]
    allowed_by_name = {}
    normalized = []
    for idx, func in enumerate(accessible_functions or []):
        if isinstance(func, dict):
            one = dict(func)
        else:
            one = {
                'function_name': str(getattr(func, 'function_name', '') or '').strip(),
                'name': str(getattr(func, 'name', '') or '').strip(),
                'description': str(getattr(func, 'description', '') or '').strip()
            }
        fname = str(one.get('function_name') or '').strip()
        if fname == 'xiaotu_qa':
            one['name'] = '报告智能体'
            desc = str(one.get('description') or '').strip()
            if not desc:
                one['description'] = '周报/月报提交与生成'
        one['_order_index'] = idx
        one['is_allowed'] = True
        allowed_by_name[fname] = one

    # 首页始终展示完整功能目录，权限只控制入口是否可以点击。
    for idx, (fname, name, description) in enumerate(dashboard_catalog):
        one = dict(allowed_by_name.get(fname) or {})
        one.update({
            'function_name': fname,
            'name': one.get('name') or name,
            'description': one.get('description') or description,
            # AI 部页面本身是完整目录页，所有登录用户都可进入；页面内功能继续逐项鉴权。
            'is_allowed': fname == 'ai_dept' or fname in allowed_by_name,
            '_order_index': idx,
        })
        normalized.append(one)

    normalized.sort(key=lambda x: int(x.get('_order_index', 0)))
    for one in normalized:
        one.pop('_order_index', None)
    return normalized


def _operation_page_permission_flags(
    user_id,
    *,
    _safe_debug_print,
    permission_manager,
):
    flags = {
        'can_view_review_analysis': False,
        'can_view_amazon_reply': False,
        'can_business_analysis': False,
    }
    if not user_id:
        return flags
    for function_name, flag_name in (
        ('review_analysis', 'can_view_review_analysis'),
        ('amazon_reply_agent', 'can_view_amazon_reply'),
        ('business_analysis', 'can_business_analysis'),
    ):
        try:
            allowed, _ = permission_manager.check_user_permission(
                user_id,
                function_name,
            )
            flags[flag_name] = bool(allowed)
        except Exception as e:
            _safe_debug_print(f"运营板块内部权限检查失败: {function_name} -> {e}")
    return flags
