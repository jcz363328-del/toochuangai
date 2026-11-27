"""Department portal entry pages."""


def tk_project(
    *,
    _safe_debug_print,
    get_joint_dashboard_allowed_shops,
    permission_manager,
    render_template,
    session,
):
    """内容生产工厂功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')

    # 获取用户可访问的功能
    accessible_functions = []
    if user_id:
        try:
            accessible_functions = permission_manager.get_user_accessible_functions(user_id)
        except Exception as e:
            _safe_debug_print(f"❌ 获取用户权限失败: {e}")

    return render_template('内容生产工厂/tk_project.html',
                           user_name=user_name,
                           user_id=user_id,
                           accessible_functions=accessible_functions,
                           can_view_joint_dashboard=bool(get_joint_dashboard_allowed_shops()))


def tk_seedance(
    *,
    _current_user_has_permission,
    redirect,
    url_for,
):
    if not _current_user_has_permission('tk_project_seedance'):
        return redirect(url_for('tk_project'))
    return redirect(url_for('seedance_web.seedance_web_index'))
