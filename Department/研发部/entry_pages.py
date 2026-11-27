"""Department portal entry pages."""


def rd_dept(
    *,
    _operation_page_permission_flags,
    render_template,
    session,
):
    """研发部功能页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    permission_flags = _operation_page_permission_flags(user_id)
    return render_template('主站/operation_dept.html',
                           user_name=user_name,
                           user_id=user_id,
                           dept_name='研发部',
                           dept_id='rd_dept',
                           **permission_flags)
