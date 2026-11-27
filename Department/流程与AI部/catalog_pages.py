"""Render process and AI tools and their release notes."""

from __future__ import annotations


def ai_modules(
    *,
    _can_access_ai_workspace,
    _safe_debug_print,
    permission_manager,
    render_template,
    session,
):
    """AI模块页面"""
    if not _can_access_ai_workspace():
        return '仅AI部成员可访问AI部功能。', 403
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')

    def has_permission(function_name):
        try:
            return bool(permission_manager.check_user_permission(user_id, function_name)[0])
        except Exception as exc:
            _safe_debug_print(f"AI模块内部权限检查失败: {function_name} -> {exc}")
            return False

    return render_template(
        '流程与AI部/ai_modules.html',
        user_id=user_id,
        user_name=user_name,
        can_ai_full=has_permission('admin_functions'),
        can_daily_replenishment=has_permission('daily_replenishment'),
        can_replenishment_vben=has_permission('replenishment_vben'),
        can_group_performance=has_permission('ai_group_performance'),
        can_business_analysis=has_permission('business_analysis'),
        can_ads_monitor=has_permission('ads_monitor'),
        can_video_claw=has_permission('video_claw'),
        can_value_evaluation=has_permission('value_evaluation'),
        can_value_evaluation_admin=has_permission('value_evaluation_admin'),
        can_historical_sales=has_permission('historical_sales'),
        can_model_library=has_permission('model_library'),
        can_model_queue=has_permission('model_queue'),
    )


def _format_ai_update_cell(
    value,
    *,
    date,
    datetime,
):
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def ai_update(
    *,
    _AI_UPDATE_QUERY,
    _format_ai_update_cell,
    app,
    datetime,
    render_template,
    sf_db,
):
    """Show today's rows from the gengxin table for AI department users."""
    try:
        raw_columns = sf_db(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = 'gengxin' ORDER BY ORDINAL_POSITION"
        ) or []
        columns = [
            str(column[0] if isinstance(column, (list, tuple)) else column)
            for column in raw_columns
        ]

        raw_rows = sf_db(_AI_UPDATE_QUERY) or []
        normalized_rows = []
        for raw_row in raw_rows:
            values = list(raw_row) if isinstance(raw_row, (list, tuple)) else [raw_row]
            normalized_rows.append([_format_ai_update_cell(value) for value in values])

        widest_row = max((len(row) for row in normalized_rows), default=0)
        if widest_row > len(columns):
            columns.extend(
                f"列{index}"
                for index in range(len(columns) + 1, widest_row + 1)
            )
        for row in normalized_rows:
            row.extend("—" for _ in range(len(columns) - len(row)))

        return render_template(
            '流程与AI部/ai_update.html',
            columns=columns,
            rows=normalized_rows,
            loaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            error=None,
        )
    except Exception:
        app.logger.exception("Failed to query today's gengxin rows")
        return render_template(
            '流程与AI部/ai_update.html',
            columns=[],
            rows=[],
            loaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            error='查询失败，请稍后重试或联系管理员。',
        ), 503


def performance_monitor(
    *,
    app,
    get_feishu_auth_url,
    redirect,
    render_template,
    session,
):
    """性能监控页面"""
    user_id = session.get('feishu_user_id')

    # 本地开发模式，跳过飞书认证
    if app.config.get('LOCAL_DEV_MODE', False):
        user_id = 'local_dev_user'
        session['feishu_user_id'] = user_id
        session['feishu_user_name'] = '本地开发用户'

    if not user_id:
        return redirect(get_feishu_auth_url())

    return render_template('流程与AI部/performance.html')


def admin_dashboard(*, render_template):
    """管理员仪表板"""
    return render_template('流程与AI部/admin_dashboard.html')
