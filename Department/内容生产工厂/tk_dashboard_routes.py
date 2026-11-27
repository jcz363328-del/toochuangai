"""TikTok dashboard page and data handlers."""

from __future__ import annotations


def tk_dashboard(
    *,
    render_template,
    session,
):
    """内容生产工厂数据看板页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')

    return render_template('内容生产工厂/tk_dashboard.html',
                           user_name=user_name,
                           user_id=user_id)


def get_tk_dashboard_data(
    *,
    _current_user_has_permission,
    _safe_debug_print,
    datetime,
    jsonify,
    request,
    session,
    sf_db,
):
    """获取TK数据看板数据API"""
    try:
        # 获取当前用户信息
        user_name = session.get('feishu_user_name', '')
        user_id = session.get('feishu_user_id', '')

        is_admin = _current_user_has_permission('tk_dashboard_legacy_all', user_id)

        _safe_debug_print(f"🔍 TK数据看板访问 - 用户: {user_name}, 是否管理员: {is_admin}")

        # 获取年月参数，默认为当前年月
        year = request.args.get('year', datetime.now().year, type=int)
        month = request.args.get('month', datetime.now().month, type=int)
        location = request.args.get('location', '', type=str)  # 新增位置参数

        _safe_debug_print(f"📍 筛选条件 - 年: {year}, 月: {month}, 位置: {location}")

        # 调用存储过程获取数据
        sql = f"EXEC sp_get_TK_YiBiaoPan6 @年 = {year}, @月 = {month}"
        data = sf_db(sql)

        if not data:
            return jsonify({
                'success': False,
                'message': '暂无数据',
                'data': [],
                'user_info': {
                    'user_name': user_name,
                    'is_admin': is_admin
                }
            })

        # 获取全部86店GMV数据（按月计算）
        tk_gmv_sql = f"""
            SELECT SUM(xiaoshoue) as tk_total_gmv
            FROM v_tk_dingdan 
            where   
             dian = 86
            AND Y= {year}
            AND M= {month}
        """

        try:
            tk_gmv_result = sf_db(tk_gmv_sql)
            # sf_db函数当只有一列时返回列表，多列时返回元组列表
            if tk_gmv_result:
                if isinstance(tk_gmv_result, list) and len(tk_gmv_result) > 0:
                    # 如果是列表且有数据，取第一个元素
                    tk_project_gmv = tk_gmv_result[0] if tk_gmv_result[0] is not None else 0
                else:
                    tk_project_gmv = 0
            else:
                tk_project_gmv = 0
            _safe_debug_print(f"📊 全部86店GMV: {tk_project_gmv}")
        except Exception as e:
            _safe_debug_print(f"❌ 获取全部86店GMV失败: {e}")
            tk_project_gmv = 0

        # 计算深圳联盟总GMV（等于深圳的86店GMV）
        # 根据业务逻辑：深圳的86店总GMV等于深圳的联盟总GMV
        shenzhen_alliance_gmv = 0
        try:
            # 从存储过程数据中计算深圳的GMV总和
            for row in data:
                if row[3] == '深圳':  # 位置字段是第4个字段（索引3）
                    shenzhen_alliance_gmv += float(row[13] if row[13] is not None else 0)  # GMV字段是第14个字段（索引13）
            _safe_debug_print(f"📊 深圳联盟总GMV: {shenzhen_alliance_gmv}")
        except Exception as e:
            _safe_debug_print(f"❌ 计算深圳联盟GMV失败: {e}")
            shenzhen_alliance_gmv = 0

        # 计算青岛86店GMV = 全部86店GMV - 深圳联盟GMV
        qingdao_86_gmv = tk_project_gmv - shenzhen_alliance_gmv
        _safe_debug_print(f"📊 青岛86店GMV: {qingdao_86_gmv} (全部86店GMV: {tk_project_gmv} - 深圳联盟GMV: {shenzhen_alliance_gmv})")

        # 转换数据格式，包含所有字段
        all_data = []
        for row in data:
            row_data = {
                '年': row[0],
                '月': row[1],
                'BD': row[2],
                '位置': row[3],
                '组长': row[4],
                '达人数指标': row[6],
                '实际达人数': row[7],
                '达人数达成率': f"{row[8] * 100:.2f}%" if row[8] is not None else None,
                '视频数': row[9],
                '视频发布数': row[10],
                '视频达成率': f"{row[11] * 100:.2f}%" if row[11] is not None else None,
                'GMV指标': row[12],
                'GMV': row[13],
                'GMV达成率': f"{row[14] * 100:.2f}%" if row[14] is not None else None
            }

            all_data.append(row_data)

        # 根据位置参数过滤数据
        if location:
            all_data = [row for row in all_data if row['位置'] == location]
            _safe_debug_print(f"🎯 位置筛选后数据量: {len(all_data)}")

        # 根据用户权限过滤数据
        if is_admin:
            # 管理员可以看到所有组的详细信息
            result_data = all_data
            _safe_debug_print(f"✅ 管理员用户，返回所有 {len(result_data)} 条数据")
        else:
            # 普通用户需要根据用户名匹配对应的分组数据
            # 通过BD字段或组长字段匹配用户所属分组
            user_location = None
            for row in all_data:
                # 找到当前用户所在的位置
                if (row['BD'] == user_name or row['组长'] == user_name or
                        (row['BD'] and user_name in row['BD']) or
                        (row['组长'] and user_name in row['组长'])):
                    user_location = row['位置']
                    break
            if user_location:
                # 根据位置筛选同一地区的所有数据
                result_data = [row for row in all_data if row['位置'] == user_location]
                _safe_debug_print(f" 普通用户（{user_name}），位置：{user_location}，共返回 {len(result_data)} 条数据")
            else:
                # 如果找不到用户对应的位置，则不返回数据
                result_data = []
                _safe_debug_print(f" 未找到用户 {user_name} 对应的位置，返回空数据")

        return jsonify({
            'success': True,
            'data': result_data,
            'year': year,
            'month': month,
            'location': location,  # 返回位置信息
            'tk_project_gmv': tk_project_gmv,  # 返回全部86店GMV数据
            'shenzhen_alliance_gmv': shenzhen_alliance_gmv,  # 返回深圳联盟GMV数据
            'qingdao_86_gmv': qingdao_86_gmv,  # 返回青岛86店GMV数据
            'user_info': {
                'user_name': user_name,
                'is_admin': is_admin,
                'total_groups': len(all_data),
                'accessible_groups': len(result_data)
            }
        })

    except Exception as e:
        _safe_debug_print(f"❌ 获取TK数据看板数据失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取数据失败: {str(e)}',
            'data': [],
            'user_info': {
                'user_name': session.get('feishu_user_name', ''),
                'is_admin': False
            }
        }), 500
