"""Start and expose supported AI tool pages."""

from __future__ import annotations


def _seedance_access_allowed(*, _current_user_has_permission):
    return _current_user_has_permission('seedance_video')


def replenishment_vben_page(
    *,
    _can_access_ai_workspace,
    app,
    os,
    send_file,
):
    if not _can_access_ai_workspace():
        return '仅AI部成员可访问AI部功能。', 403
    response = send_file(os.path.join(app.static_folder, 'replenishment-vben', 'index.html'), max_age=0)
    response.headers['Cache-Control'] = 'no-store'
    return response


def replenishment_vben_config(
    *,
    _can_access_ai_workspace,
    jsonify,
    session,
    url_for,
):
    if not _can_access_ai_workspace():
        return jsonify(success=False, message='仅AI部成员可访问AI部功能。'), 403
    import daily_replenishment_operation as operation
    _, access = operation.scoped_query_executor(operation._current_user_name())
    response = jsonify(success=True, can_write=bool(access.get('can_write')),
        write_stores=sorted(access.get('write_stores') or []),
        user_name=session.get('feishu_user_name', ''),
        data_url=url_for('daily_replenishment_operation.data'),
        quantity_url=url_for('daily_replenishment_operation.update_order_quantities'),
        refresh_url=url_for('daily_replenishment_operation.refresh'),
        purchase_url=url_for('daily_replenishment_operation.purchase_plan'),
        trend_url=url_for('daily_replenishment_operation.sales_trend'),
        sea_url=url_for('daily_replenishment_operation.sea_shipping_recommendations'))
    response.headers['Cache-Control'] = 'no-store'
    return response


def ads_monitor(
    *,
    _ADS_MONITOR_DIST_DIR,
    _ensure_ads_monitor_api_started,
    os,
    render_template,
    send_from_directory,
):
    """AI 部 MAGIC AD 广告监控工作台。"""
    index_path = os.path.join(_ADS_MONITOR_DIST_DIR, 'index.html')
    if not os.path.isfile(index_path):
        return render_template(
            '流程与AI部/ads_monitor_unavailable.html',
            reason='广告监控前端资源尚未构建，请联系管理员执行构建。',
        ), 503
    _ensure_ads_monitor_api_started()
    response = send_from_directory(_ADS_MONITOR_DIST_DIR, 'index.html')
    response.headers['Cache-Control'] = 'no-store'
    return response


def ads_monitor_asset(
    filename,
    *,
    _ADS_MONITOR_DIST_DIR,
    send_from_directory,
):
    response = send_from_directory(_ADS_MONITOR_DIST_DIR, filename)
    if filename.startswith('assets/'):
        response.headers['Cache-Control'] = 'private, max-age=31536000, immutable'
    else:
        response.headers['Cache-Control'] = 'no-store'
    return response
