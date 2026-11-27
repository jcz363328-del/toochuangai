"""Portal permission administration handlers."""


def get_user_permissions(
    get_feishu_auth_url,
    jsonify,
    permission_manager,
    session,
):
    """获取当前用户权限API"""
    user_id = session.get('feishu_user_id')

    if not user_id:
        return jsonify({
            'success': False,
            'message': '用户未登录',
            'auth_url': get_feishu_auth_url()
        })

    try:
        accessible_functions = permission_manager.get_user_accessible_functions(user_id)
        user_departments = permission_manager.get_user_departments(user_id)

        return jsonify({
            'success': True,
            'data': {
                'user_id': user_id,
                'user_name': session.get('feishu_user_name'),
                'departments': [dept.get('name', '') for dept in user_departments],
                'accessible_functions': accessible_functions,
                'is_developer': permission_manager.is_developer(user_id)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取用户权限失败: {str(e)}'
        })


def permission_management(
    render_template,
    request,
    url_for,
):
    source = str(request.args.get('source') or '').strip().lower()
    if source == 'ai':
        return_url = url_for('ai_modules')
        return_label = '返回AI部功能'
    else:
        return_url = url_for('admin_dashboard')
        return_label = '返回管理员功能'
    return render_template(
        '主站/permission_management.html',
        return_url=return_url,
        return_label=return_label,
    )


def permission_overview(
    jsonify,
    permission_manager,
):
    """权限目录、用户级调整和统计概览。"""
    try:
        return jsonify({
            'success': True,
            'data': permission_manager.get_permission_management_overview(),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'加载权限概览失败: {str(e)}',
        }), 500


def search_user(
    jsonify,
    permission_manager,
    request,
):
    """搜索用户API"""
    try:
        data = request.get_json()
        search_value = data.get('search_value', '').strip()

        if not search_value:
            return jsonify({
                'success': False,
                'message': '请输入搜索内容'
            })

        # 获取用户信息和权限
        user_info = permission_manager.search_user_by_id_or_email(search_value)

        if not user_info:
            return jsonify({
                'success': False,
                'message': '未找到该用户，请检查用户ID或邮箱是否正确'
            })

        # 获取用户的所有权限信息
        all_permissions = permission_manager.get_all_permissions_for_user(user_info['user_id'])

        return jsonify({
            'success': True,
            'data': {
                'user_id': user_info['user_id'],
                'name': user_info['name'],
                'email': user_info['email'],
                'departments': user_info['departments'],
                'permissions': all_permissions
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'搜索用户失败: {str(e)}'
        })


def grant_permission(
    jsonify,
    permission_manager,
    request,
    session,
):
    """授予权限API"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        function_name = data.get('function_name')

        if not user_id or not function_name:
            return jsonify({
                'success': False,
                'message': '缺少必要参数'
            })

        # 授予权限
        result = permission_manager.grant_user_permission(
            user_id,
            function_name,
            user_name=str(data.get('user_name') or '').strip(),
            updated_by=str(session.get('feishu_user_name') or '').strip(),
        )

        if result['success']:
            return jsonify({
                'success': True,
                'message': f'成功授予权限',
                'function_display_name': result.get('function_display_name', function_name)
            })
        else:
            return jsonify({
                'success': False,
                'message': result['message']
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'授予权限失败: {str(e)}'
        })


def revoke_permission(
    jsonify,
    permission_manager,
    request,
    session,
):
    """撤销权限API"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        function_name = data.get('function_name')

        if not user_id or not function_name:
            return jsonify({
                'success': False,
                'message': '缺少必要参数'
            })

        if (
            str(user_id).strip() == str(session.get('feishu_user_id') or '').strip()
            and function_name == 'admin_functions'
        ):
            return jsonify({
                'success': False,
                'message': '不能撤销自己当前使用的权限管理后台权限',
            }), 400

        result = permission_manager.revoke_user_permission(
            user_id,
            function_name,
            user_name=str(data.get('user_name') or '').strip(),
            updated_by=str(session.get('feishu_user_name') or '').strip(),
        )

        if result['success']:
            return jsonify({
                'success': True,
                'message': f'成功撤销权限',
                'function_display_name': result.get('function_display_name', function_name)
            })
        else:
            return jsonify({
                'success': False,
                'message': result['message']
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'撤销权限失败: {str(e)}'
        })


def reset_permission(
    jsonify,
    permission_manager,
    request,
):
    """删除用户单独设置，恢复部门默认权限。"""
    try:
        data = request.get_json() or {}
        user_id = str(data.get('user_id') or '').strip()
        function_name = str(data.get('function_name') or '').strip()
        if not user_id or not function_name:
            return jsonify({'success': False, 'message': '缺少必要参数'}), 400
        result = permission_manager.reset_user_permission_override(user_id, function_name)
        return jsonify(result), (200 if result.get('success') else 400)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'恢复默认权限失败: {str(e)}',
        }), 500
