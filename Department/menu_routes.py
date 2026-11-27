"""只含公共目录展示的部门入口，业务数据和权限仍由各模块维护。"""
from flask import render_template, session

MENUS = (
    ('tech_dept', '技术部'),
    ('photography_dept', '摄影部'),
    ('visual_design_dept', '视觉设计部'),
    ('procurement_dept', '采购部'),
)


def register_department_menu_routes(app, require_permission):
    def make_view(key, label):
        def view():
            return render_template('主站/operation_dept.html',
                user_name=session.get('feishu_user_name', '用户'),
                user_id=session.get('feishu_user_id'), dept_name=label, dept_id=key)
        view.__name__ = key
        return require_permission(key)(view)
    for key, label in MENUS:
        app.add_url_rule('/' + key, endpoint=key, view_func=make_view(key, label))

    @app.route('/finance_modules')
    @require_permission('finance_dept')
    def finance_modules():
        return render_template('财务部/finance_modules.html')
