"""Department portal entry pages."""


def general_office(
    *,
    _current_user_has_permission,
    render_template,
    session,
):
    """总经办功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('主站/operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='总经办',
                           dept_id='general_office',
                           can_business_analysis=_current_user_has_permission('business_analysis', user_id))
