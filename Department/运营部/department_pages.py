"""Render operation department pages and FBA shipment tools."""

from __future__ import annotations


def _operation_dept_has_access(*, _current_user_has_permission):
    return _current_user_has_permission('operation_fba_shipping')


def api_operation_fba_shipping_methods(
    *,
    _operation_dept_has_access,
    app,
    jsonify,
    request,
    sf_db,
):
    if not _operation_dept_has_access():
        return jsonify({'success': False, 'message': '无权限访问运营部门数据'}), 403
    try:
        from Department.运营部.fba_shipping_service import load_snapshot, payload
        return jsonify({'success': True, 'data': payload(load_snapshot(sf_db, force=request.args.get('refresh') == '1'), request.args)})
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': '分页参数无效'}), 400
    except Exception:
        app.logger.exception('FBA shipping query failed')
        return jsonify({'success': False, 'message': '货件数据读取失败，请稍后重试'}), 503


def api_operation_fba_shipping_method_shops(
    *,
    _operation_dept_has_access,
    app,
    jsonify,
    sf_db,
):
    if not _operation_dept_has_access():
        return jsonify({'success': False, 'message': '无权限访问运营部门数据'}), 403
    try:
        from Department.运营部.fba_shipping_service import load_snapshot
        snapshot = load_snapshot(sf_db)
        return jsonify({'success': True, 'data': {'shops': snapshot['shops'],
                       'shipping_methods': snapshot['shipping_methods']}})
    except Exception:
        app.logger.exception('FBA shipping options failed')
        return jsonify({'success': False, 'message': '筛选选项读取失败，请稍后重试'}), 503


def export_operation_fba_shipping_methods(
    *,
    _operation_dept_has_access,
    app,
    jsonify,
    request,
    sf_db,
):
    if not _operation_dept_has_access():
        return jsonify({'success': False, 'message': '无权限访问运营部门数据'}), 403
    try:
        from flask import Response
        from Department.运营部.fba_shipping_service import load_snapshot, csv_rows
        snapshot = load_snapshot(sf_db)
        response = Response(csv_rows(snapshot, dict(request.args)), content_type='text/csv; charset=utf-8')
        response.headers['Content-Disposition'] = 'attachment; filename="fba_shipping.csv"'
        response.headers['Cache-Control'] = 'no-store'
        return response
    except Exception:
        app.logger.exception('FBA shipping export failed')
        return jsonify({'success': False, 'message': '导出失败，请稍后重试'}), 503


def operation_fba_shipping_methods_page(
    *,
    _FBA_SHIPPING_ACCESS_FUNCTIONS,
    _operation_dept_has_access,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
):
    if not _operation_dept_has_access():
        flash('无权限访问FBA货件运输方式')
        return redirect(url_for('dashboard'))
    source = str(request.args.get('source') or '').strip()
    dept_names = {
        'operation_dept_1': '运营一部',
        'operation_dept_2': '运营二部',
        'operation_dept_3': '运营三部',
        'operation_dept_6': '运营六部',
        'operation_dept_7': '运营七部',
        'newcomer_group': '新人组',
    }
    back_url = url_for(source) if source in _FBA_SHIPPING_ACCESS_FUNCTIONS else url_for('dashboard')
    return render_template(
        '运营部/operation_fba_shipping_methods.html',
        user_name=session.get('feishu_user_name', '用户'),
        source=source,
        source_name=dept_names.get(source, '运营部门'),
        back_url=back_url,
    )


def operation_dept_1(
    *,
    _current_user_has_permission,
    _operation_page_permission_flags,
    render_template,
    session,
):
    """运营一部功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    permission_flags = _operation_page_permission_flags(user_id)
    return render_template('主站/operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='运营一部',
                           dept_id='operation_dept_1',
                           can_view_tk_90=_current_user_has_permission('tk_dashboard_90', user_id),
                           **permission_flags)


def operation_dept_2(
    *,
    _operation_page_permission_flags,
    render_template,
    session,
):
    """运营二部功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    permission_flags = _operation_page_permission_flags(user_id)
    return render_template('主站/operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='运营二部',
                           dept_id='operation_dept_2',
                           **permission_flags)


def operation_dept_3(
    *,
    _operation_page_permission_flags,
    render_template,
    session,
):
    """运营三部功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    permission_flags = _operation_page_permission_flags(user_id)
    return render_template('主站/operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='运营三部',
                           dept_id='operation_dept_3',
                           **permission_flags)


def operation_dept_6(
    *,
    _current_user_has_permission,
    _operation_page_permission_flags,
    render_template,
    session,
):
    """运营六部功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    permission_flags = _operation_page_permission_flags(user_id)
    return render_template('主站/operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='运营六部',
                           dept_id='operation_dept_6',
                           can_view_tk_82=_current_user_has_permission('tk_dashboard_82', user_id),
                           can_view_tk_88=_current_user_has_permission('tk_dashboard_88', user_id),
                           **permission_flags)


def operation_dept_7(
    *,
    _operation_page_permission_flags,
    render_template,
    session,
):
    """运营七部功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    permission_flags = _operation_page_permission_flags(user_id)
    return render_template('主站/operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='运营七部',
                           dept_id='operation_dept_7',
                           **permission_flags)


def shenzhen_dept(
    *,
    _current_user_has_permission,
    render_template,
    session,
):
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('主站/operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='深圳团队',
                           dept_id='shenzhen_dept',
                           can_sz_dashboard=_current_user_has_permission('tk_total_dashboard', user_id))


def newcomer_group(
    *,
    _current_user_has_permission,
    _operation_page_permission_flags,
    render_template,
    session,
):
    """新人组功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    permission_flags = _operation_page_permission_flags(user_id)
    return render_template('主站/operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='新人组',
                           dept_id='newcomer_group',
                           can_view_tk_88=_current_user_has_permission('tk_dashboard_88', user_id),
                           **permission_flags)
