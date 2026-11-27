"""Build permission-scoped workspace catalogs and mobile function cards."""

from __future__ import annotations


def _build_mobile_function_cards(
    accessible_functions,
    *,
    _can_access_ai_workspace,
    _current_user_has_permission,
    _get_func_field,
    url_for,
):
    cards = []
    seen = set()
    for func in (accessible_functions or []):
        function_name = str(_get_func_field(func, 'function_name') or '').strip()
        if function_name == 'ai_dept' and not _can_access_ai_workspace():
            continue
        display_name = str(_get_func_field(func, 'name') or function_name or '功能').strip()
        if not function_name or function_name in seen:
            continue
        seen.add(function_name)

        href = ''
        icon = 'fa-solid fa-grid-2'
        if function_name == 'innovation_proposals':
            href = url_for('innovation_proposals.innovation_proposals')
            icon = 'fa-solid fa-lightbulb'
        elif function_name == 'tk_project_group':
            href = url_for('tk_project')
            icon = 'fa-solid fa-store'
        elif function_name == 'xiaotu_qa':
            href = url_for('dashboard_xiaotu_report_center_mobile')
            display_name = '报告智能体'
            icon = 'fa-solid fa-file-lines'
        elif function_name == 'general_office':
            href = url_for('general_office')
            icon = 'fa-solid fa-building'
        elif function_name == 'operation_dept_1':
            href = url_for('operation_dept_1')
            icon = 'fa-solid fa-chart-line'
        elif function_name == 'operation_dept_2':
            href = url_for('operation_dept_2')
            icon = 'fa-solid fa-chart-line'
        elif function_name == 'operation_dept_3':
            href = url_for('operation_dept_3')
            icon = 'fa-solid fa-chart-line'
        elif function_name == 'operation_dept_6':
            href = url_for('operation_dept_6')
            icon = 'fa-solid fa-chart-line'
        elif function_name == 'operation_dept_7':
            href = url_for('operation_dept_7')
            icon = 'fa-solid fa-chart-line'
        elif function_name == 'photography_dept':
            href = url_for('photography_dept')
            icon = 'fa-solid fa-camera'
        elif function_name == 'ai_dept':
            href = url_for('ai_modules')
            icon = 'fa-solid fa-brain'
        elif function_name == 'business_analysis':
            href = url_for('business_analysis')
            icon = 'fa-solid fa-chart-line'
        elif function_name == 'amazon_reply_agent':
            href = url_for('amazon_reply_agent')
            display_name = '亚马逊站内信回复智能体'
            icon = 'fa-solid fa-envelope-open-text'
        elif function_name == 'finance_dept':
            href = url_for('finance_modules')
            icon = 'fa-solid fa-coins'
        elif function_name == 'procurement_dept':
            href = url_for('procurement_dept')
            icon = 'fa-solid fa-cart-shopping'
        elif function_name == 'hr_admin_dept':
            href = url_for('hr_admin_modules')
            icon = 'fa-solid fa-users'
        elif function_name == 'tech_dept':
            href = url_for('tech_dept')
            icon = 'fa-solid fa-microchip'
        elif function_name == 'rd_dept':
            href = url_for('rd_dept')
            icon = 'fa-solid fa-flask'
        elif function_name == 'visual_design_dept':
            href = url_for('visual_design_dept')
            icon = 'fa-solid fa-palette'
        elif function_name == 'newcomer_group':
            href = url_for('newcomer_group')
            icon = 'fa-solid fa-seedling'
        elif function_name == 'shenzhen_dept':
            href = url_for('shenzhen_dept')
            icon = 'fa-solid fa-location-dot'
        elif function_name == 'model_queue':
            href = url_for('model_management.queue')
            icon = 'fa-solid fa-user-clock'

        cards.append({
            'name': display_name,
            'href': href,
            'icon': icon,
            'available': bool(href)
        })

    cards.append({
        'name': '年会精彩瞬间',
        'href': url_for('annual_moments'),
        'icon': 'fa-solid fa-images',
        'available': True
    })

    cards.append({
        'name': 'Seedance 视频生成',
        'href': url_for('seedance_web.seedance_web_index'),
        'icon': 'fa-solid fa-film',
        'available': True
    })

    cards.append({
        'name': '培训视频',
        'href': url_for('training_videos'),
        'icon': 'fa-solid fa-circle-play',
        'available': True
    })
    if _current_user_has_permission('video_claw'):
        cards.append({
            'name': 'VideoClaw AI视频创作',
            'href': url_for('video_claw'),
            'icon': 'fa-solid fa-clapperboard',
            'available': True,
        })
    return cards


def dashboard_workspace_catalog(
    accessible,
    *,
    _OPERATION_DEPT_FUNCTIONS,
    _can_access_ai_workspace,
    _normalize_dashboard_functions,
    _permission_debug_effective_state,
    app,
    jsonify,
    permission_manager,
    render_template,
    session,
    url_for,
):
    import inspect
    from urllib.parse import urlsplit
    from core.utils.dashboard_workspace import extract_features, template_catalog_context
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False}), 401
    if accessible is None:
        accessible = permission_manager.get_user_accessible_functions(user_id)
    can_access_ai_workspace = _can_access_ai_workspace()
    permission_names = {item['function_name'] for item in accessible}
    catalog_functions = [{'function_name': key} for key in permission_manager.get_permission_records()]

    def allowed(key):
        return key in permission_names

    routes = []
    for rule in app.url_map.iter_rules():
        if 'GET' not in rule.methods or rule.arguments - set((rule.defaults or {}).keys()):
            continue
        view = app.view_functions[rule.endpoint]
        keys = []
        while view:
            closure = inspect.getclosurevars(view).nonlocals
            key = closure.get('function_name')
            if isinstance(key, str):
                keys.append(key)
            view = getattr(view, '__wrapped__', None)
        if keys:
            routes.append({'path': rule.rule, 'allowed': all(allowed(key) for key in keys), 'permissions': keys})
    route_permissions = {route['path']: route['permissions'] for route in routes}
    route_permissions[url_for('business_analysis')] = ['business_analysis']
    route_permissions[url_for('tk_seedance')] = ['tk_project_seedance']
    joint_allowed = allowed('tk_dashboard_full') or allowed('tk_joint_dashboard_all') or any(permission.startswith('tk_joint_shop_') for permission in permission_names)
    operation_ids = sorted(_OPERATION_DEPT_FUNCTIONS) + ['newcomer_group']
    groups = []
    for key, name, description in [
        ('operations', '运营部功能', ''),
        *[(item['function_name'], item['name'], '') for item in _normalize_dashboard_functions([])
          if item['function_name'] in {'tk_project_group', 'tech_dept', 'visual_design_dept', 'photography_dept', 'ai_dept', 'warehouse_group', 'procurement_dept', 'general_office', 'rd_dept', 'finance_dept', 'hr_admin_dept', 'shenzhen_dept'}],
    ]:
        if key == 'ai_dept' and not can_access_ai_workspace:
            continue
        items = []
        errors = []
        ids = operation_ids if key == 'operations' else [key]
        for dept_id in ids:
            endpoint = None
            try:
                if dept_id in operation_ids or dept_id in {'tech_dept', 'visual_design_dept', 'photography_dept', 'procurement_dept', 'general_office', 'rd_dept', 'shenzhen_dept'}:
                    html = render_template('主站/operation_dept.html', dept_id=dept_id, dept_name=name,
                        user_id=user_id, user_name=session.get('feishu_user_name', ''),
                        can_view_review_analysis=True, can_view_amazon_reply=True,
                        can_view_tk_90=True, can_view_tk_82=True, can_view_tk_88=True)
                    candidates = extract_features(html, '/' + dept_id)
                else:
                    endpoint = {'tk_project_group': 'tk_project', 'ai_dept': 'ai_modules', 'finance_dept': 'finance_modules', 'hr_admin_dept': 'hr_admin_modules'}.get(dept_id)
                    if endpoint:
                        template = {'tk_project_group': '内容生产工厂/tk_project.html', 'ai_dept': '流程与AI部/ai_modules.html', 'finance_dept': '财务部/finance_modules.html', 'hr_admin_dept': '人力资源与行政部/hr_admin_modules.html'}[dept_id]
                        context = dict(user_id=user_id, user_name=session.get('feishu_user_name', ''), accessible_functions=catalog_functions,
                            can_view_joint_dashboard=True)
                        source = app.jinja_env.loader.get_source(app.jinja_env, template)[0]
                        flags, template_permissions = template_catalog_context(source)
                        context.update(flags)
                        context['accessible_functions'] = catalog_functions + [{'function_name': permission} for permission in template_permissions]
                        candidates = extract_features(render_template(template, **context), url_for(endpoint))
                    else:
                        candidates = []
                for item in candidates:
                    path = urlsplit(item['href']).path
                    inline_action = dept_id in {'finance_dept', 'hr_admin_dept'} and '#' in item['href'] and path == url_for(endpoint)
                    required = route_permissions.get(path, [])
                    if item['permission'] and item['permission'] not in required:
                        required = required + [item['permission']]
                    inline_tool = '#' in item['href'] and dept_id not in operation_ids and endpoint and path == url_for(endpoint)
                    if not required and inline_tool and item.get('scopePermission'):
                        required = [item['scopePermission']]
                    if dept_id == 'ai_dept' and path == url_for('listing_agent.index') and urlsplit(item['href']).fragment == 'abaRankingImport':
                        required = ['listing_agent_aba_import']
                    if inline_action and not required:
                        required = [dept_id]
                    item['required_permissions'] = required
                    item['allowed'] = all(allowed(permission) for permission in required)
                    if dept_id == 'tk_project_group' and path == url_for('tk_dashboard.tk_dashboard_project_page'):
                        item['allowed'] = joint_allowed
                        item['required_permissions'] = ['tk_dashboard_full / tk_joint_dashboard_all / tk_joint_shop_*']
                    items.append(item)
            except Exception:
                app.logger.exception('Workspace catalog failed: %s', dept_id)
                errors.append(dept_id)
        groups.append({'key': key, 'name': name.replace('功能模块', '').replace('功能', '') if key != 'operations' else name, 'items': list({(item['menu'], item['href']): item for item in items}.values()), 'errors': errors,
            'unavailable_reason': '原项目尚未配置仓储部功能页面，未虚构功能入口。' if key == 'warehouse_group' else ''})
    operations = next(group for group in groups if group['key'] == 'operations')
    for menu, endpoint, permission, icon in [
        ('经营分析', 'business_analysis', 'business_analysis', 'fas fa-chart-pie'),
        ('我开发的产品销售', 'developer_product_sales.page', 'ai_dept', 'fas fa-box-open'),
        ('智能补货中心-亚马逊', 'daily_replenishment_operation.page', 'daily_replenishment_operation', 'fas fa-warehouse'),
    ]:
        href = url_for(endpoint)
        operations['items'].append({'menu': menu, 'href': href,
            'permission': permission, 'required_permissions': [permission],
            'allowed': allowed(permission), 'iconClass': icon, 'id': menu + '::' + href})
    operations['items'] = list({item['href']: item for item in operations['items']}.values())
    debug_state = _permission_debug_effective_state()
    user_key = str(debug_state.get('user_name') or user_id).strip()
    response = jsonify({'success': True, 'groups': groups, 'routes': routes, 'user_key': user_key, 'can_access_ai_workspace': can_access_ai_workspace})
    response.headers['Cache-Control'] = 'no-store'
    return response
