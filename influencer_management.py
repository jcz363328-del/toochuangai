from flask import Blueprint, render_template, request, jsonify, session
import bjc
from datetime import datetime
from department_permissions import require_permission
import pandas as pd
import os
import re
import smtplib
from werkzeug.utils import secure_filename
from secret_settings import sql_server_config
from tools import escape_sql_literal as _escape_sql_literal_for_pytds


# 添加检查申请人是否存在的函数
def check_applicant_exists(applicant_name):
    """检查申请人是否存在于ComputerName表的uname字段中"""
    try:
        # 打印调试信息
        print(f"检查申请人是否存在: {applicant_name}")
        # 使用uname字段查询，sf_db不支持params参数，使用字符串拼接
        sql = f"SELECT COUNT(*) FROM ComputerName WHERE uname = '{applicant_name}'"
        count = bjc.sf_db(sql, single=True)
        print(f"查询结果: {count}")
        return count > 0
    except Exception as e:
        print(f"检查申请人时出错: {str(e)}")
        return False


# 添加从session获取当前用户名的辅助函数
def get_current_user_name():
    """从session中获取当前用户名"""
    # 尝试从session中获取用户名
    user_name = session.get('feishu_user_name', '')
    return user_name


def _normalize_sender_group_value(value):
    text = str(value or '').strip()
    if not text:
        return ''
    match = re.search(r'([1-4])', text)
    if match:
        return f"{match.group(1)}组"
    return text


def _detect_sender_group_fields(col_names):
    group_field = None
    leader_field = None
    for col_name in col_names or []:
        text = str(col_name or '').strip()
        if not text:
            continue
        if ('组长' in text) and not leader_field:
            leader_field = text
            continue
        if text == '姓名':
            continue
        if any(keyword in text for keyword in ['分组', '小组', '组别', '组']):
            if '组长' in text:
                continue
            if not group_field:
                group_field = text
    return group_field, leader_field


def _build_sender_group_meta(sender_table, col_names):
    group_field, leader_field = _detect_sender_group_fields(col_names)
    group_options = list(_TIMED_MAIL_FIXED_GROUP_LEADER_MAP.keys()) if group_field else []
    leader_map = dict(_TIMED_MAIL_FIXED_GROUP_LEADER_MAP) if group_field and leader_field else {}
    return {
        'group_field': group_field,
        'leader_field': leader_field,
        'group_options': group_options,
        'leader_map': leader_map
    }


def _apply_sender_group_leader(email_data, sender_table, col_names):
    if not isinstance(email_data, dict):
        return email_data
    payload = dict(email_data)
    meta = _build_sender_group_meta(sender_table, col_names)
    group_field = meta.get('group_field')
    leader_field = meta.get('leader_field')
    leader_map = meta.get('leader_map') or {}
    if not group_field or not leader_field:
        return payload
    group_value = _normalize_sender_group_value(payload.get(group_field, ''))
    if group_value:
        payload[group_field] = group_value
        leader_value = str(leader_map.get(group_value) or '').strip()
        if leader_value:
            payload[leader_field] = leader_value
    return payload


def _is_sender_email_col(col_name):
    s = str(col_name or '').strip()
    sl = s.lower()
    if s == '姓名':
        return False
    if ('是否' in s) or ('y或n' in sl) or ('y/n' in sl):
        return False
    return ('youxiang' in sl) or ('email' in sl) or ('e-mail' in sl) or ('mail' in sl) or ('邮箱' in s) or ('邮件地址' in s) or ('发件' in s)


def _detect_sender_auth_fields(col_names):
    email_field = None
    auth_field = None
    password_field = None
    for col_name in col_names or []:
        text = str(col_name or '').strip()
        lower_text = text.lower()
        if not email_field and _is_sender_email_col(text):
            email_field = text
            continue
        if not auth_field and ('授权码' in text or 'app密码' in text or '客户端密码' in text or 'smtp密码' in lower_text):
            auth_field = text
            continue
        if not password_field and (
            text == '密码'
            or '登录密码' in text
            or '邮箱密码' in text
            or 'password' in lower_text
            or lower_text.endswith('pwd')
            or 'mima' in lower_text
        ) and '授权' not in text:
            password_field = text
    return {
        'email_field': email_field,
        'auth_field': auth_field,
        'password_field': password_field
    }


def _should_validate_sender_credentials(changed_data, col_names):
    if not isinstance(changed_data, dict) or not changed_data:
        return False
    auth_meta = _detect_sender_auth_fields(col_names)
    watched_fields = {
        auth_meta.get('email_field'),
        auth_meta.get('auth_field'),
        auth_meta.get('password_field')
    }
    watched_fields = {field for field in watched_fields if field}
    return any(key in watched_fields for key in changed_data.keys())


def _guess_sender_smtp_config(email_address):
    domain = str(email_address or '').split('@')[-1].strip().lower()
    mapping = {
        'qq.com': {'host': 'smtp.qq.com', 'port': 465, 'use_ssl': True},
        'foxmail.com': {'host': 'smtp.qq.com', 'port': 465, 'use_ssl': True},
        'exmail.qq.com': {'host': 'smtp.exmail.qq.com', 'port': 465, 'use_ssl': True},
        '163.com': {'host': 'smtp.163.com', 'port': 465, 'use_ssl': True},
        '126.com': {'host': 'smtp.126.com', 'port': 465, 'use_ssl': True},
        'yeah.net': {'host': 'smtp.yeah.net', 'port': 465, 'use_ssl': True},
        'vip.163.com': {'host': 'smtp.vip.163.com', 'port': 465, 'use_ssl': True},
        'gmail.com': {'host': 'smtp.gmail.com', 'port': 465, 'use_ssl': True},
        'outlook.com': {'host': 'smtp.office365.com', 'port': 587, 'use_ssl': False},
        'hotmail.com': {'host': 'smtp.office365.com', 'port': 587, 'use_ssl': False},
        'live.com': {'host': 'smtp.office365.com', 'port': 587, 'use_ssl': False},
        'msn.com': {'host': 'smtp.office365.com', 'port': 587, 'use_ssl': False},
    }
    return mapping.get(domain, {'host': f'smtp.{domain}', 'port': 465, 'use_ssl': True})


def _validate_sender_account_credentials(account_data, col_names):
    if not isinstance(account_data, dict):
        return True, ''
    auth_meta = _detect_sender_auth_fields(col_names)
    email_field = auth_meta.get('email_field')
    auth_field = auth_meta.get('auth_field')
    password_field = auth_meta.get('password_field')
    email_address = str(account_data.get(email_field) or '').strip() if email_field else ''
    auth_code = str(account_data.get(auth_field) or '').strip() if auth_field else ''
    password_value = str(account_data.get(password_field) or '').strip() if password_field else ''

    if not email_address or '@' not in email_address:
        return False, '请先填写有效的发件邮箱地址后再保存'

    login_secret = auth_code or password_value
    if not login_secret:
        return False, '请先填写授权码或密码，并验证通过后再保存'

    smtp_config = _guess_sender_smtp_config(email_address)
    server = None
    try:
        if smtp_config.get('use_ssl'):
            server = smtplib.SMTP_SSL(smtp_config['host'], smtp_config['port'], timeout=12)
        else:
            server = smtplib.SMTP(smtp_config['host'], smtp_config['port'], timeout=12)
            server.ehlo()
            server.starttls()
            server.ehlo()
        server.login(email_address, login_secret)
        return True, ''
    except smtplib.SMTPAuthenticationError:
        return False, '授权码或密码校验失败，请检查后再保存'
    except Exception as e:
        return False, f"邮箱校验失败: {str(e)}"
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


def _row_to_sender_account_dict(col_names, row):
    data = {}
    if not isinstance(row, (list, tuple)):
        return data
    for index, col_name in enumerate(col_names or []):
        value = row[index] if index < len(row) else None
        data[str(col_name)] = '' if value is None else str(value)
    return data


# 性能优化建议:
# 1. 在常用筛选字段上创建索引: BianHao, WangHongMing, Guo, FuZeRen
# 2. 在排序字段上创建索引: DaoRuShiJian
# 3. 使用复合索引优化多字段筛选查询

influencer_management_bp = Blueprint('influencer_management', __name__)

_TIMED_MAIL_FIXED_GROUP_LEADER_MAP = {
    '1组': '张睿',
    '2组': '李炜翀',
    '3组': '贾雪月',
    '4组': '李雪涛',
}


@influencer_management_bp.route('/influencer_management')
@require_permission('influencer_management')
def influencer_management():
    """达人管理主页面"""
    return render_template('influencer_management.html')


@influencer_management_bp.route('/get_influencer_data')
@require_permission('influencer_management')
def get_influencer_data():
    """获取达人数据 - 支持分页，默认每页15条记录"""
    print("\n[DEBUG] ====== 开始获取达人数据 ======")
    try:
        # 获取分页参数
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 15))

        # 计算偏移量
        offset = (page - 1) * page_size
        print(f"[DEBUG] 分页参数: page={page}, page_size={page_size}, offset={offset}")

        # 获取总记录数
        count_sql = "SELECT COUNT(*) FROM TK_wanghong_ziliao"
        print("[DEBUG] 执行计数SQL:", count_sql)
        count_result = bjc.sf_db(count_sql, single=True)  # 使用single=True直接获取单个值
        print("[DEBUG] 计数结果:", count_result, "类型:", type(count_result))
        total_count = count_result if count_result is not None else 0
        print("[DEBUG] 总记录数:", total_count)

        # 分页查询 - 默认按导入时间降序排序（使用SQL Server的OFFSET-FETCH语法）
        sql = f"SELECT * FROM TK_wanghong_ziliao ORDER BY DaoRuShiJian DESC OFFSET {offset} ROWS FETCH NEXT {page_size} ROWS ONLY"
        print("[DEBUG] 执行查询SQL:", sql)
        data = bjc.sf_db(sql)
        print("[DEBUG] 查询结果类型:", type(data))

        # 确保data是列表类型
        if not isinstance(data, list):
            print("[DEBUG] 查询结果不是列表类型，转换为空列表")
            data = []
        else:
            print("[DEBUG] 查询结果行数:", len(data))

        # 转换为字典格式
        result = []
        print("[DEBUG] 开始转换数据格式")
        for i, row in enumerate(data):
            print(f"[DEBUG] 处理第{i + 1}行数据，行长度:", len(row))
            result.append({
                'BianHao': row[1],  # 网红编号显示网红用户名
                'WangHongMing': row[3],  # 网红用户名显示原编号
                'Guo': row[2],
                'shouye': row[4],  # 完整的TikTok链接
                'FuZeRen': row[5],
                'WangHongDiZhi': row[6],  # 网红地址
                'ShouFeiBiaoZhun': row[7],
                'ShouFeiZhangHao': row[8],  # 付款方式
                'BeiZhu1': row[9],  # BD备注
                'BeiZhu2': row[10],  # 运营备注
                'ZhuangTai': row[11],
                'DaoRuRen': row[12],  # 导入人
                'DaoRuShijian': row[13].strftime('%Y-%m-%d %H:%M:%S') if row[13] else '',
                'ChangYongLianXiFangshi': row[14] if len(row) > 14 else '',  # 常用联系方式
                'QiTaLianXiFangShi': row[15] if len(row) > 15 else '',  # 其他联系方式
                'BiaoQian': row[16] if len(row) > 16 else ''  # 达人标签
            })

        # 计算分页信息
        total_pages = (total_count + page_size - 1) // page_size

        return jsonify({
            'success': True,
            'data': result,
            'pagination': {
                'current_page': page,
                'page_size': page_size,
                'total': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        })
    except Exception as e:
        error_message = str(e)
        print(f"[DEBUG] 错误信息: {error_message}")
        print(f"[DEBUG] 错误类型: {type(e)}")
        import traceback
        print("[DEBUG] 错误堆栈:")
        traceback.print_exc()
        return jsonify({'success': False, 'message': error_message})


# 自定义标签相关的API
@influencer_management_bp.route('/api/save_custom_tag', methods=['POST'])
def save_custom_tag():
    try:
        data = request.get_json()
        tag = data.get('tag')

        if not tag:
            return jsonify({'success': False, 'message': '标签不能为空'})

        # 检查标签是否已存在
        check_sql = f"SELECT COUNT(*) FROM TK_wanghong_ziliao WHERE BiaoQian LIKE '%{tag}%'"
        count = bjc.sf_db(check_sql, single=True)

        if count == 0:
            # 如果标签不存在，添加到一个示例记录中
            update_sql = f"UPDATE TOP(1) TK_wanghong_ziliao SET BiaoQian = CASE WHEN BiaoQian IS NULL OR BiaoQian = '' THEN '{tag}' ELSE BiaoQian + ',' + '{tag}' END"
            bjc.dui_db(update_sql)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@influencer_management_bp.route('/api/get_custom_tags', methods=['GET'])
def get_custom_tags():
    try:
        # 从所有记录的BiaoQian字段中提取唯一标签
        sql = "SELECT DISTINCT value FROM (SELECT value FROM TK_wanghong_ziliao CROSS APPLY STRING_SPLIT(BiaoQian, ',') WHERE BiaoQian IS NOT NULL AND BiaoQian != '') AS tags"
        result = bjc.sf_db(sql)
        tags = [row[0] for row in result] if result else []

        return jsonify({'success': True, 'tags': tags})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@influencer_management_bp.route('/add_influencer', methods=['POST', 'PUT'])
def manage_influencer():
    """管理达人信息 - 添加或更新"""
    try:
        print(f"[DEBUG] 接收到请求方法: {request.method}")
        data = request.get_json()
        print(f"[DEBUG] 请求数据: {data}")

        if request.method == 'POST':
            # POST请求 - 专门处理新增达人
            # 新增时必须检查网红编号和网红用户名都不能重复

            # 检查网红编号是否已存在
            check_bianhao_sql = f"SELECT COUNT(*) FROM TK_wanghong_ziliao WHERE BianHao = '{data['BianHao']}'"
            bianhao_count = bjc.sf_db(check_bianhao_sql, single=True)
            if bianhao_count > 0:
                return jsonify({'success': False, 'message': '该网红编号已存在，无法登记'})

            # 检查网红用户名是否已存在
            check_wanghongming_sql = f"SELECT COUNT(*) FROM TK_wanghong_ziliao WHERE WangHongMing = '{data['WangHongMing']}'"
            wanghongming_count = bjc.sf_db(check_wanghongming_sql, single=True)
            if wanghongming_count > 0:
                return jsonify({'success': False, 'message': '该网红用户名已存在，无法登记'})

            # 构建INSERT SQL语句
            # 处理标签，确保使用逗号分隔
            tags = data.get('BiaoQian', [])
            if isinstance(tags, list):
                tags = ','.join(tags)

            sql = """
            INSERT INTO TK_wanghong_ziliao (
            BianHao, WangHongMing, Guo, shouye, FuZeRen, 
            WangHongDiZhi, ShouFeiBiaoZhun, ShouFeiZhangHao, 
            BeiZhu1, BeiZhu2, ChangYongLianXiFangshi, 
            QiTaLianXiFangShi, BiaoQian, DaoRuShijian
        ) VALUES (
            '{}', '{}', '{}', '{}', '{}', 
            '{}', '{}', '{}', '{}', '{}', 
            '{}', '{}', '{}', '{}'
        )""".format(
                data.get('BianHao', ''),  # 网红编号
                data.get('WangHongMing', ''),  # 网红用户名
                data.get('Guo', ''),  # 国家
                data.get('shouye', ''),  # 完整的TikTok链接
                data.get('FuZeRen', ''),  # 负责人
                data.get('WangHongDiZhi', ''),  # 网红地址
                data.get('ShouFeiBiaoZhun', ''),  # 收费标准
                data.get('ShouFeiZhangHao', ''),  # 付款方式（paypal/cashapp/其他）
                data.get('BeiZhu1', ''),  # BD备注
                data.get('BeiZhu2', ''),  # 运营备注
                data.get('ChangYongLianXiFangshi', ''),  # 常用联系方式
                data.get('QiTaLianXiFangShi', ''),  # 其他联系方式
                tags,  # 达人标签（逗号分隔）
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )

            bjc.dui_db(sql)
            return jsonify({'success': True, 'message': f"达人信息添加成功，编号：{data.get('BianHao', '')}"})

        elif request.method == 'PUT':
            # PUT请求 - 专门处理修改达人信息
            # 修改时必须验证网红编号存在
            bianhao = data.get('BianHao')

            if not bianhao:
                return jsonify({'success': False, 'message': '缺少网红编号'})

            # 验证网红编号是否存在
            check_exists_sql = f"SELECT COUNT(*) FROM TK_wanghong_ziliao WHERE BianHao = '{bianhao}'"
            exists_count = bjc.sf_db(check_exists_sql, single=True)
            if exists_count == 0:
                return jsonify({'success': False, 'message': '该网红编号不存在，无法修改'})

            # 构建UPDATE SQL语句
            # 不允许更新的字段：网红编号、网红用户名、国家
            readonly_fields = ['BianHao', 'WangHongMing', 'Guo', 'editMode']
            update_fields = []
            for key, value in data.items():
                if key not in readonly_fields:  # 排除只读字段
                    field_name = {
                        'shouye': 'shouye',  # 完整的TikTok链接
                        'FuZeRen': 'FuZeRen',  # 负责人
                        'WangHongDiZhi': 'WangHongDiZhi',  # 网红地址
                        'ShouFeiBiaoZhun': 'ShouFeiBiaoZhun',  # 收费标准
                        'ShouFeiZhangHao': 'ShouFeiZhangHao',  # 付款方式
                        'BeiZhu1': 'BeiZhu1',  # BD备注
                        'BeiZhu2': 'BeiZhu2',  # 运营备注
                        'ZhuangTai': 'ZhuangTai',  # 状态
                        'ChangYongLianXiFangshi': 'ChangYongLianXiFangshi',  # 常用联系方式
                        'QiTaLianXiFangShi': 'QiTaLianXiFangShi',  # 其他联系方式
                        'BiaoQian': 'BiaoQian'  # 达人标签
                    }.get(key)

                    if field_name and value is not None:  # 只更新非空值
                        # 对字段进行 SQL 注入防护
                        safe_value = str(value).replace("'", "''")
                        update_fields.append(f"{field_name} = '{safe_value}'")

            if not update_fields:
                return jsonify({'success': False, 'message': '没有要更新的字段'})

            sql = f"UPDATE TK_wanghong_ziliao SET {', '.join(update_fields)} WHERE BianHao = '{bianhao}'"
            bjc.dui_db(sql)

            return jsonify({'success': True, 'message': '达人信息更新成功'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@influencer_management_bp.route('/filter_influencer_data', methods=['POST'])
def filter_influencer_data():
    """根据条件筛选达人数据 - 支持分页的优化SQL查询"""
    try:
        filters = request.get_json()

        # 获取分页参数
        page = int(filters.get('page', 1))
        page_size = int(filters.get('page_size', 15))

        # 构建基础SQL查询
        base_sql = "SELECT * FROM TK_wanghong_ziliao WHERE 1=1"
        count_sql = "SELECT COUNT(*) FROM TK_wanghong_ziliao WHERE 1=1"

        # 构建WHERE条件
        where_conditions = ""

        # 使用SQL条件构建筛选逻辑
        if filters.get('bianhao'):
            # 网红编号使用精确匹配
            where_conditions += f" AND BianHao = '{filters['bianhao']}'"

        if filters.get('wanghongming'):
            where_conditions += f" AND WangHongMing LIKE '%{filters['wanghongming']}%'"

        if filters.get('guo'):
            where_conditions += f" AND Guo LIKE '%{filters['guo']}%'"

        if filters.get('fuzeren'):
            where_conditions += f" AND FuZeRen LIKE '%{filters['fuzeren']}%'"

        # 日期范围筛选 - 使用字符串格式化进行日期比较
        if filters.get('startDate'):
            start_datetime = f"{filters['startDate']} 00:00:00"
            where_conditions += f" AND DaoRuShiJian >= '{start_datetime}'"

        if filters.get('endDate'):
            end_datetime = f"{filters['endDate']} 23:59:59"
            where_conditions += f" AND DaoRuShiJian <= '{end_datetime}'"

        # 添加WHERE条件到SQL语句
        base_sql += where_conditions
        count_sql += where_conditions

        # 获取筛选后的总记录数
        count_result = bjc.sf_db(count_sql, single=True)  # 使用single=True直接获取单个值
        total_count = count_result if count_result is not None else 0

        # SQL排序逻辑 - 建议在DaoRuShiJian字段上创建索引以提高排序性能
        sort_order = filters.get('sortOrder', 'DaoRuShiJian_DESC')
        if sort_order == 'DaoRuShiJian_ASC':
            base_sql += " ORDER BY DaoRuShiJian ASC"
        else:
            base_sql += " ORDER BY DaoRuShiJian DESC"

        # 添加分页限制
        offset = (page - 1) * page_size  # 添加分页限制
        final_sql = base_sql + f" OFFSET {offset} ROWS FETCH NEXT {page_size} ROWS ONLY"

        # 执行优化的SQL查询
        data = bjc.sf_db(final_sql)

        # 确保data是列表类型
        if not isinstance(data, list):
            data = []

        # 转换为字典格式
        result = []
        for row in data:
            result.append({
                'BianHao': row[1],  # 网红编号显示网红用户名
                'WangHongMing': row[3],  # 网红用户名显示原编号
                'Guo': row[2],
                'shouye': row[4],  # 完整的TikTok链接
                'FuZeRen': row[5],
                'WangHongDiZhi': row[6],  # 网红地址
                'ShouFeiBiaoZhun': row[7],
                'ShouFeiZhangHao': row[8],  # 付款方式
                'BeiZhu1': row[9],  # BD备注
                'BeiZhu2': row[10],  # 运营备注
                'ZhuangTai': row[11],
                'DaoRuRen': row[12],  # 导入人
                'DaoRuShijian': row[13].strftime('%Y-%m-%d %H:%M:%S') if row[13] else '',
                'ChangYongLianXiFangshi': row[14] if len(row) > 14 else '',  # 常用联系方式
                'QiTaLianXiFangShi': row[15] if len(row) > 15 else '',  # 其他联系方式
                'BiaoQian': row[16] if len(row) > 16 else ''  # 达人标签
            })

        # 计算分页信息
        total_pages = (total_count + page_size - 1) // page_size

        return jsonify({
            'success': True,
            'data': result,
            'pagination': {
                'current_page': page,
                'page_size': page_size,
                'total': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@influencer_management_bp.route('/delete_influencer', methods=['POST'])
def delete_influencer():
    """删除达人信息"""
    try:
        data = request.get_json()
        bianhao = data.get('bianhao')

        if not bianhao:
            return jsonify({'success': False, 'message': '缺少网红编号'})

        sql = f"DELETE FROM TK_wanghong_ziliao WHERE BianHao = '{bianhao}'"
        bjc.dui_db(sql)

        return jsonify({'success': True, 'message': '达人信息删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@influencer_management_bp.route('/api/update_influencer', methods=['POST'])
def update_influencer():
    """更新达人信息"""
    try:
        data = request.get_json()
        bianhao = data.get('BianHao')  # 注意：前端传递的是 BianHao 而不是 bianhao

        if not bianhao:
            return jsonify({'success': False, 'message': '缺少网红编号'})

        # 构建UPDATE SQL语句
        update_fields = []
        for key, value in data.items():
            if key != 'BianHao':  # 不更新编号
                field_name = {
                    'WangHongMing': 'WangHongMing',  # 网红用户名
                    'Guo': 'Guo',  # 国家
                    'shouye': 'shouye',  # 完整的TikTok链接
                    'FuZeRen': 'FuZeRen',  # 负责人
                    'WangHongDiZhi': 'WangHongDiZhi',  # 网红地址
                    'ShouFeiBiaoZhun': 'ShouFeiBiaoZhun',  # 收费标准
                    'ShouFeiZhangHao': 'ShouFeiZhangHao',  # 付款方式
                    'BeiZhu1': 'BeiZhu1',  # BD备注
                    'BeiZhu2': 'BeiZhu2',  # 运营备注
                    'ZhuangTai': 'ZhuangTai',  # 状态
                    'ChangYongLianXiFangshi': 'ChangYongLianXiFangshi',  # 常用联系方式
                    'QiTaLianXiFangShi': 'QiTaLianXiFangShi',  # 其他联系方式
                    'BiaoQian': 'BiaoQian'  # 达人标签
                }.get(key)

                if field_name and value is not None:  # 只更新非空值
                    # 特殊处理标签字段
                    if key == 'BiaoQian':
                        # BiaoQian 已经是分号分隔的字符串，不需要额外处理
                        update_fields.append(f"{field_name} = '{value}'")
                    else:
                        # 对其他字段进行 SQL 注入防护
                        safe_value = value.replace("'", "''")
                        update_fields.append(f"{field_name} = '{safe_value}'")

        if not update_fields:
            return jsonify({'success': False, 'message': '没有要更新的字段'})

        sql = f"UPDATE TK_wanghong_ziliao SET {', '.join(update_fields)} WHERE BianHao = '{bianhao}'"
        bjc.dui_db(sql)

        return jsonify({'success': True, 'message': '达人信息更新成功'})
    except Exception as e:
        print(f"更新达人信息时出错: {str(e)}")  # 添加错误日志
        return jsonify({'success': False, 'message': str(e)})


@influencer_management_bp.route('/get_payment_options')
def get_payment_options():
    """获取付款方式选项"""
    try:
        payment_options = ['paypal', 'cashapp', '其他']
        return jsonify({
            'success': True,
            'data': payment_options
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@influencer_management_bp.route('/get_filter_options')
def get_filter_options():
    """获取筛选器选项（国家和负责人列表）"""
    try:
        # 获取所有不同的国家
        countries_sql = "SELECT DISTINCT Guo FROM TK_WangHong_ZiLiao WHERE Guo IS NOT NULL AND Guo != '' ORDER BY Guo"
        countries = bjc.sf_db(countries_sql)

        # 获取所有不同的负责人
        managers_sql = "SELECT DISTINCT FuZeRen FROM TK_WangHong_ZiLiao WHERE FuZeRen IS NOT NULL AND FuZeRen != '' ORDER BY FuZeRen"
        managers = bjc.sf_db(managers_sql)

        return jsonify({
            'success': True,
            'data': {
                'countries': countries,
                'managers': managers
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@influencer_management_bp.route('/get_influencer_detail/<bianhao>')
def get_influencer_detail(bianhao):
    """获取单个达人的详细信息"""
    try:
        sql = f"SELECT * FROM TK_WangHong_ZiLiao WHERE BianHao = '{bianhao}'"
        data = bjc.sf_db(sql)

        if not data:
            return jsonify({'success': False, 'message': '未找到该达人信息'})

        row = data[0]
        # 处理标签字段，将逗号分隔的字符串转换为数组
        tags = row[16].split(',') if row[16] and len(row) > 16 else []

        result = {
            'BianHao': row[0],  # 网红编号
            'WangHongMing': row[1],  # 网红用户名
            'Guo': row[2],  # 国家
            'shouye': row[4],  # 完整的TikTok链接
            'FuZeRen': row[5],  # 负责人
            'WangHongDiZhi': row[6],  # 网红地址
            'ShouFeiBiaoZhun': row[7],  # 收费标准
            'ShouFeiZhangHao': row[8],  # 付款方式（paypal/cashapp/其他）
            'BeiZhu1': row[9],  # BD备注
            'BeiZhu2': row[10],  # 运营备注
            'ZhuangTai': row[11],
            'DaoRuRen': row[12],  # 导入人
            'DaoRuShijian': row[13].strftime('%Y-%m-%d %H:%M:%S') if row[13] else '',
            'ChangYongLianXiFangshi': row[14] if len(row) > 14 else '',  # 常用联系方式
            'QiTaLianXiFangShi': row[15] if len(row) > 15 else '',  # 其他联系方式
            'BiaoQian': tags  # 达人标签（数组格式）
        }

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# TK邮件登记功能相关路由
@influencer_management_bp.route('/tk_email_register')
@require_permission('tk_email_register')
def tk_email_register():
    """邮件登记页面"""
    # 从session中获取当前用户信息
    user_name = session.get('feishu_user_name', '')

    # 创建一个current_user对象传递给模板
    current_user = {'username': user_name}

    return render_template('tk_email_register.html', current_user=current_user, api_prefix='')


@influencer_management_bp.route('/tk_email_register_js')
@require_permission('tk_email_register')
def tk_email_register_js():
    """邮件登记页面（技术部专用表）"""
    user_name = session.get('feishu_user_name', '')
    current_user = {'username': user_name}
    return render_template('tk_email_register.html', current_user=current_user, api_prefix='/tk_email_register_js')


@influencer_management_bp.route('/get_email_data')
@influencer_management_bp.route('/tk_email_register_js/get_email_data')
@require_permission('tk_email_register')
def get_email_data():
    """获取邮件登记数据，返回邮箱拥有者与当前用户名一致的记录，或当前用户作为申请人的记录"""
    try:
        email_table = "FaYouJian_JS" if request.path.startswith('/tk_email_register_js/') else "TK_FaYouJian"

        # 获取当前用户名
        current_user = get_current_user_name()
        if not current_user:
            return jsonify({'success': False, 'message': '无法获取当前用户信息'})

        # 转义用户名中的单引号
        safe_current_user = current_user.replace("'", "''")

        # 获取分页参数
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 10))

        # 计算偏移量
        offset = (page - 1) * page_size

        # 获取总记录数（邮箱拥有者与当前用户名一致的记录，或当前用户作为申请人的记录，且排除已回复的邮箱）
        count_sql = f"SELECT COUNT(*) FROM {email_table} WHERE (YouXiangYongYouZhe = '{safe_current_user}' OR ShenQingRen = '{safe_current_user}') AND (shifouhuifu IS NULL OR shifouhuifu != 'Y')"
        count_result = bjc.sf_db(count_sql, single=True)
        total_count = count_result if count_result is not None else 0

        # 获取分页数据（邮箱拥有者与当前用户名一致的记录，或当前用户作为申请人的记录，且排除已回复的邮箱）
        data_sql = f"SELECT * FROM {email_table} WHERE (YouXiangYongYouZhe = '{safe_current_user}' OR ShenQingRen = '{safe_current_user}') AND (shifouhuifu IS NULL OR shifouhuifu != 'Y') ORDER BY ShenQingShiJian DESC OFFSET {offset} ROWS FETCH NEXT {page_size} ROWS ONLY"
        data = bjc.sf_db(data_sql)

        # 确保data是列表类型
        if not isinstance(data, list):
            data = []

        # 转换为字典格式
        result = []
        for row in data:
            # 安全处理日期字段，支持datetime对象和字符串
            def format_datetime(dt_value):
                if not dt_value:
                    return ''
                if hasattr(dt_value, 'strftime'):
                    return dt_value.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    return str(dt_value)  # 如果是字符串，直接返回

            result.append({
                'ID': row[0],
                'YouXiang': row[1],  # 邮箱
                'XingMing': row[2],  # 网红名
                'YouXiangYongYouZhe': row[3],  # 邮箱拥有者
                'ShenQingRen': row[4],  # 申请人
                'ShenQingShiJian': format_datetime(row[5]),
                'FaSongShiJian': format_datetime(row[6]),
                'ZhiDingShiJian': format_datetime(row[7]) if len(row) > 7 else '',
                'MoBan': row[8] if len(row) > 8 else ''  # 模板内容
            })

        # 计算分页信息
        total_pages = (total_count + page_size - 1) // page_size

        return jsonify({
            'success': True,
            'data': result,
            'pagination': {
                'current_page': page,
                'page_size': page_size,
                'total': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@influencer_management_bp.route('/get_emails_by_date', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/get_emails_by_date', methods=['POST'])
@require_permission('tk_email_register')
def get_emails_by_date():
    """根据日期获取所有邮件ID，支持跨页面全选"""
    try:
        email_table = "FaYouJian_JS" if request.path.startswith('/tk_email_register_js/') else "TK_FaYouJian"

        data = request.get_json()
        selected_date = data.get('date', '')

        if not selected_date:
            return jsonify({'success': False, 'message': '未提供日期参数'})

        # 获取当前用户名
        current_user = get_current_user_name()
        if not current_user:
            return jsonify({'success': False, 'message': '无法获取当前用户信息'})

        # 转义用户名中的单引号
        safe_current_user = current_user.replace("'", "''")

        # 构建日期范围查询（选定日期的00:00:00到23:59:59）
        start_datetime = f"{selected_date} 00:00:00"
        end_datetime = f"{selected_date} 23:59:59"

        # 查询指定日期的所有邮件ID（返回当前用户有权限的记录，且排除已回复的邮箱）
        sql = f"""SELECT ID FROM {email_table} 
                  WHERE (YouXiangYongYouZhe = '{safe_current_user}' OR ShenQingRen = '{safe_current_user}')
                  AND (shifouhuifu IS NULL OR shifouhuifu != 'Y')
                  AND ShenQingShiJian >= '{start_datetime}' 
                  AND ShenQingShiJian <= '{end_datetime}'
                  ORDER BY ShenQingShiJian DESC"""

        result = bjc.sf_db(sql)

        # 提取ID列表
        email_ids = []
        if result:
            for row in result:
                if isinstance(row, (list, tuple)):
                    email_ids.append(str(row[0]))
                else:
                    email_ids.append(str(row))

        return jsonify({
            'success': True,
            'email_ids': email_ids,
            'count': len(email_ids)
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@influencer_management_bp.route('/add_email_register', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/add_email_register', methods=['POST'])
@require_permission('tk_email_register')
def add_email_register():
    """添加邮件登记信息"""
    try:
        email_table = "FaYouJian_JS" if request.path.startswith('/tk_email_register_js/') else "TK_FaYouJian"

        data = request.get_json()

        # 使用辅助函数获取当前登录用户的姓名作为申请人
        shen_qing_ren = get_current_user_name()

        # 如果session中没有用户名，则尝试从前端传来的数据获取
        if not shen_qing_ren:
            shen_qing_ren = data.get('ShenQingRen', '')
            if not shen_qing_ren:
                return jsonify({'success': False, 'message': '无法获取申请人姓名，请手动输入', 'field': 'ShenQingRen'})

        # 验证申请人是否存在于ComputerName表的cname字段中
        if not check_applicant_exists(shen_qing_ren):
            return jsonify(
                {'success': False, 'message': f'申请人 {shen_qing_ren} 不存在于系统中', 'field': 'ShenQingRen'})

        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 获取邮箱拥有者（当前用户）
        youxiang_yongyouzhe = shen_qing_ren

        # 使用参数化查询避免SQL注入和字符串截断问题
        youxiang = data.get('YouXiang', '').replace("'", "''")
        xingming = data.get('XingMing', '').replace("'", "''")
        shen_qing_ren = shen_qing_ren.replace("'", "''")
        youxiang_yongyouzhe = youxiang_yongyouzhe.replace("'", "''")

        sql = f"""INSERT INTO {email_table} (YouXiang, XingMing, YouXiangYongYouZhe, ShenQingRen, ShenQingShiJian) 
               VALUES ('{youxiang}', '{xingming}', '{youxiang_yongyouzhe}', '{shen_qing_ren}', '{current_time}')"""

        bjc.dui_db(sql)
        return jsonify({'success': True, 'message': '邮件登记信息添加成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'添加失败: {str(e)}'})


@influencer_management_bp.route('/update_email_send_time', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/update_email_send_time', methods=['POST'])
@require_permission('tk_email_register')
def update_email_send_time():
    """更新邮件发送时间"""
    try:
        email_table = "FaYouJian_JS" if request.path.startswith('/tk_email_register_js/') else "TK_FaYouJian"

        data = request.get_json()
        email_ids = data.get('ids', [])

        if not email_ids:
            return jsonify({'success': False, 'message': '未选择任何邮件记录'})

        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 将ID列表转换为逗号分隔的字符串
        id_list = ','.join(map(str, email_ids))

        # 使用字符串拼接构建SQL，不再更新ShenQingRen字段
        sql = f"UPDATE {email_table} SET FaSongShiJian = '{current_time}' WHERE ID IN ({id_list})"

        bjc.dui_db(sql)

        return jsonify({'success': True, 'message': '邮件发送时间更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'})


@influencer_management_bp.route('/update_email_specified_time', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/update_email_specified_time', methods=['POST'])
@require_permission('tk_email_register')
def update_email_specified_time():
    """更新邮件指定发送时间和模板名称"""
    try:
        email_table = "FaYouJian_JS" if request.path.startswith('/tk_email_register_js/') else "TK_FaYouJian"

        data = request.get_json()
        email_ids = data.get('ids', [])
        specified_time = data.get('specified_time', '')
        moban = data.get('moban', '')

        if not email_ids:
            return jsonify({'success': False, 'message': '未选择任何邮件记录'})

        if not specified_time:
            return jsonify({'success': False, 'message': '未指定发送时间'})

        if not moban:
            return jsonify({'success': False, 'message': '未选择邮件模板'})

        # 处理日期格式，保留完整的日期时间信息
        try:
            # 尝试解析日期时间字符串
            from datetime import datetime
            dt = datetime.fromisoformat(specified_time.replace('Z', '+00:00'))
            # 保留完整的日期时间信息
            formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            # 如果解析失败，直接使用原始值
            formatted_time = specified_time

        # 转义指定时间中的单引号（如果有）
        safe_specified_time = formatted_time.replace("'", "''")

        # 获取模板名称
        moban_name = moban
        # 如果是自定义模板内容，则提取模板名称为"自定义模板"
        if moban.startswith('custom:'):
            moban_name = '自定义模板'

        # 将ID列表转换为逗号分隔的字符串
        id_list = ','.join(map(str, email_ids))

        # 使用参数化查询来避免SQL注入
        try:
            # 对于批量更新，我们需要逐个更新以使用参数化查询
            for email_id in email_ids:
                sql = f"UPDATE {email_table} SET ZhiDingShiJian = ?, mobanming = ? WHERE ID = ?"
                bjc.dui_db_with_params(sql, (formatted_time, moban_name, email_id))
        except AttributeError:
            # 如果bjc.dui_db_with_params不存在，则使用原有方法
            safe_moban_name = moban_name.replace("'", "''")
            sql = f"UPDATE {email_table} SET ZhiDingShiJian = '{safe_specified_time}', mobanming = '{safe_moban_name}' WHERE ID IN ({id_list})"
            bjc.dui_db(sql)

        return jsonify({'success': True, 'message': '邮件指定发送时间和模板名称更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'})


@influencer_management_bp.route('/get_email_templates', methods=['GET'])
@influencer_management_bp.route('/tk_email_register_js/get_email_templates', methods=['GET'])
@require_permission('tk_email_register')
def get_email_templates():
    """获取邮件模板列表"""
    try:
        template_table = "js_youjian_moban" if request.path.startswith('/tk_email_register_js/') else "tk_youjian_moban"

        # 查询所有邮件模板，不包括图片字段以提高加载速度
        sql = f"SELECT ID, MoBanMing, MoBan, YouJianBiaoTi FROM {template_table} ORDER BY ID"
        templates = bjc.sf_db(sql)

        # 转换为字典格式
        result = []
        for template in templates:
            result.append({
                'id': int(template[0]) if template[0] is not None else 0,
                'name': str(template[1]) if template[1] is not None else '',
                'content': str(template[2]) if template[2] is not None else '',
                'youjianbiaoti': str(template[3]) if len(template) > 3 and template[3] is not None else '',
                'tupian': None  # 不再加载图片数据，提高响应速度
            })

        return jsonify({'success': True, 'templates': result})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取模板失败: {str(e)}'})


# 新增：获取当前用户在 tk_fenzu_youxiang 表中的发件邮箱列表
@influencer_management_bp.route('/get_sender_emails', methods=['GET'])
@influencer_management_bp.route('/tk_email_register_js/get_sender_emails', methods=['GET'])
@require_permission('tk_email_register')
def get_sender_emails():
    """返回当前飞书用户在 tk_fenzu_youxiang 表登记的发件邮箱列表"""
    try:
        sender_table = "FaYouJian_JS_YouXiang" if request.path.startswith('/tk_email_register_js/') else "tk_fenzu_youxiang"
        email_table = "FaYouJian_JS" if request.path.startswith('/tk_email_register_js/') else "TK_FaYouJian"

        current_user = get_current_user_name()
        if not current_user:
            return jsonify({'success': False, 'message': '无法获取当前用户信息'})
        safe_user = _escape_sql_literal_for_pytds(current_user)

        # 获取表字段，识别可能的邮箱列（先按列名匹配，失败则按数据内容回退）
        columns = bjc.sf_db(
            f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{sender_table}' ORDER BY ORDINAL_POSITION")
        if not columns:
            return jsonify({'success': False, 'message': f'未找到 {sender_table} 表结构'})
        col_names = [str(c) for c in columns]  # 修复：直接使用字符串，不需要取[0]

        def is_email_col(col_name):
            s = str(col_name)
            sl = s.lower()
            if s == '姓名':
                return False
            if ('是否' in s) or ('y或n' in sl) or ('y/n' in sl):
                return False
            return ('youxiang' in sl) or ('email' in sl) or ('e-mail' in sl) or ('mail' in sl) or ('邮箱' in s) or ('邮件地址' in s) or ('发件' in s)

        email_cols = [c for c in col_names if is_email_col(c)]

        # 若列名无法识别，按数据内容扫描推断邮箱列
        inferred_cols = []
        if not email_cols:
            sample_rows = bjc.sf_db(f"SELECT TOP 200 * FROM {sender_table}")
            if sample_rows:
                # 按字段顺序扫描，寻找包含 '@' 的文本
                col_has_email = {c: False for c in col_names}
                for row in sample_rows:
                    for i, val in enumerate(row):
                        if val is None:
                            continue
                        s = str(val).strip()
                        # 简易邮箱判断：包含 '@' 且不包含空格
                        if s and ('@' in s) and (' ' not in s):
                            col_has_email[col_names[i]] = True
                inferred_cols = [c for c, has in col_has_email.items() if has and c != '姓名']
            # 使用推断的列作为邮箱列
            email_cols = inferred_cols

        # 仍未识别到邮箱列，则从发邮件记录表回退提供邮箱集合
        if not email_cols:
            fallback = bjc.sf_db(
                f"SELECT DISTINCT youjiantou FROM {email_table} WHERE youjiantou IS NOT NULL AND youjiantou LIKE '%@%'")
            fallback_emails = [str(r[0]).strip() for r in (fallback or []) if r and r[0]]
            fallback_emails = list(dict.fromkeys([e for e in fallback_emails if e]))
            if fallback_emails:
                return jsonify({'success': True, 'emails': fallback_emails,
                                'message': '未识别到邮箱字段，已从发邮件记录中提取发件邮箱'})
            return jsonify({'success': False, 'message': '未识别到邮箱相关字段'})

        # 改为 SELECT * 并按列索引取值，避免中文列名引用问题
        if '姓名' in col_names:
            sql = f"SELECT * FROM {sender_table} WHERE 姓名 = '{safe_user}'"
            message = None
        else:
            # 无“姓名”字段，退化为返回全表的邮箱集合供选择
            sql = f"SELECT * FROM {sender_table}"
            message = "未找到‘姓名’字段，已返回全表邮箱列表供选择"
        rows = bjc.sf_db(sql)
        if not rows:
            return jsonify({'success': True, 'emails': [], 'message': message or '当前用户在邮箱分组表中没有记录'})

        # 合并所有非空邮箱
        emails = []
        idx_map = {name: i for i, name in enumerate(col_names)}
        for row in rows:
            for c in email_cols:
                i = idx_map.get(c)
                if i is None or i >= len(row):
                    continue
                val = row[i]
                if val is None:
                    continue
                v = str(val).strip()
                if v and ('@' in v) and (' ' not in v):
                    emails.append(v)
        # 去重
        emails = list(dict.fromkeys(emails))

        return jsonify({'success': True, 'emails': emails, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取发件邮箱失败: {str(e)}'})


# 邮箱账户管理：仅显示并允许当前飞书用户维护自己的 tk_fenzu_youxiang 记录
@influencer_management_bp.route('/get_my_email_accounts', methods=['GET'])
@influencer_management_bp.route('/tk_email_register_js/get_my_email_accounts', methods=['GET'])
@require_permission('tk_email_register')
def get_my_email_accounts():
    """获取当前用户在 tk_fenzu_youxiang 的多条记录（含ID）、邮箱列及首条记录字段"""
    try:
        sender_table = "FaYouJian_JS_YouXiang" if request.path.startswith('/tk_email_register_js/') else "tk_fenzu_youxiang"

        current_user = get_current_user_name()
        if not current_user:
            return jsonify({'success': False, 'message': '无法获取当前用户信息'})
        safe_user = current_user.replace("'", "''")

        columns = bjc.sf_db(
            f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{sender_table}' ORDER BY ORDINAL_POSITION")
        if not columns:
            return jsonify({'success': False, 'message': f'未找到 {sender_table} 表结构'})
        col_names = [str(c) for c in columns]

        email_cols = [c for c in col_names if _is_sender_email_col(c)]
        if not email_cols:
            sample_rows = bjc.sf_db(f"SELECT TOP 200 * FROM {sender_table}")
            if sample_rows:
                col_has_email = {c: False for c in col_names}
                for row in sample_rows:
                    for i, val in enumerate(row):
                        if val is None:
                            continue
                        s = str(val).strip()
                        if s and ('@' in s) and (' ' not in s):
                            col_has_email[col_names[i]] = True
                email_cols = [c for c, has in col_has_email.items() if has and c != '姓名']

        editable = '姓名' in col_names
        group_meta = _build_sender_group_meta(sender_table, col_names)

        # 查询当前用户的所有记录（或只读模式下的第一条）
        if editable:
            sql = f"SELECT * FROM {sender_table} WHERE 姓名 = '{safe_user}' ORDER BY ID"
        else:
            sql = f"SELECT TOP 1 * FROM {sender_table} ORDER BY ID"
        rows = bjc.sf_db(sql)

        # 组装 records
        records = []
        id_index = col_names.index('ID') if 'ID' in col_names else None
        for row in (rows or []):
            rec_fields = []
            for i, col_name in enumerate(col_names):
                val = None if i >= len(row) else row[i]
                rec_fields.append({'name': col_name, 'value': '' if val is None else str(val)})
            rec_id = None
            if id_index is not None and id_index < len(row):
                try:
                    rec_id = int(row[id_index]) if row[id_index] is not None else None
                except Exception:
                    rec_id = row[id_index]
            records.append({'id': rec_id, 'fields': rec_fields})

        # 首条记录的字段（向后兼容旧前端）
        if records:
            fields = records[0]['fields']
        else:
            fields = [{'name': c, 'value': ''} for c in col_names]

        msg = None if editable else f"{sender_table} 缺少‘姓名’字段，当前为只读展示，无法按用户维护"
        return jsonify({
            'success': True,
            'fields': fields,
            'records': records,
            'record_count': len(records),
            'email_cols': email_cols,
            'group_field': group_meta.get('group_field'),
            'leader_field': group_meta.get('leader_field'),
            'group_options': group_meta.get('group_options'),
            'leader_map': group_meta.get('leader_map'),
            'editable': editable,
            'message': msg
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取邮箱账户失败: {str(e)}'})


@influencer_management_bp.route('/update_my_email_accounts', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/update_my_email_accounts', methods=['POST'])
@require_permission('tk_email_register')
def update_my_email_accounts():
    """更新当前用户在 tk_fenzu_youxiang 的邮箱相关字段；支持按ID逐条更新"""
    try:
        sender_table = "FaYouJian_JS_YouXiang" if request.path.startswith('/tk_email_register_js/') else "tk_fenzu_youxiang"

        data = request.get_json() or {}
        updates = data.get('updates', {})
        updates_by_id = data.get('updates_by_id', [])

        current_user = get_current_user_name()
        if not current_user:
            return jsonify({'success': False, 'message': '无法获取当前用户信息'})
        safe_user = current_user.replace("'", "''")

        # 获取表结构与可更新列
        columns = bjc.sf_db(
            f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{sender_table}' ORDER BY ORDINAL_POSITION")
        if not columns:
            return jsonify({'success': False, 'message': f'未找到 {sender_table} 表结构'})
        col_names = [str(c) for c in columns]
        allowed_cols = [c for c in col_names if c not in ['ID', '姓名']]

        # 分支：按ID逐条更新
        if isinstance(updates_by_id, list) and len(updates_by_id) > 0:
            if 'ID' not in col_names:
                return jsonify({'success': False, 'message': '当前表缺少ID字段，无法按记录更新'})

            updated_count = 0
            for item in updates_by_id:
                if not isinstance(item, dict):
                    continue
                rec_id = item.get('id')
                item_updates = item.get('updates', {})
                if rec_id is None or not isinstance(item_updates, dict) or not item_updates:
                    continue
                item_updates = _apply_sender_group_leader(item_updates, sender_table, col_names)

                set_clauses = []
                for k, v in item_updates.items():
                    if k in allowed_cols:
                        safe_v = _escape_sql_literal_for_pytds(v)
                        safe_col = '[' + str(k).replace(']', ']]') + ']'
                        set_clauses.append(f"{safe_col} = '{safe_v}'")
                if not set_clauses:
                    continue

                # 构造 WHERE 条件（ID 优先按数值处理）
                try:
                    rid = int(rec_id)
                    where = f"ID = {rid}"
                except Exception:
                    safe_id = _escape_sql_literal_for_pytds(rec_id)
                    where = f"ID = '{safe_id}'"

                if _should_validate_sender_credentials(item_updates, col_names):
                    existing_rows = bjc.sf_db(f"SELECT TOP 1 * FROM {sender_table} WHERE {where}") or []
                    existing_data = _row_to_sender_account_dict(col_names, existing_rows[0]) if existing_rows else {}
                    pending_data = dict(existing_data)
                    pending_data.update(item_updates)
                    valid, validate_message = _validate_sender_account_credentials(pending_data, col_names)
                    if not valid:
                        return jsonify({'success': False, 'message': validate_message})

                sql = f"UPDATE {sender_table} SET {', '.join(set_clauses)} WHERE {where}"
                bjc.dui_db(sql)
                updated_count += 1

            if updated_count == 0:
                return jsonify({'success': False, 'message': '没有任何记录被更新'})
            return jsonify({'success': True, 'message': f'按ID更新成功，更新 {updated_count} 条记录'})

        # 分支：按当前用户（姓名）整体更新
        if not isinstance(updates, dict) or not updates:
            return jsonify({'success': False, 'message': '缺少更新内容'})
        updates = _apply_sender_group_leader(updates, sender_table, col_names)
        if _should_validate_sender_credentials(updates, col_names):
            merged_updates = dict(updates)
            valid, validate_message = _validate_sender_account_credentials(merged_updates, col_names)
            if not valid:
                return jsonify({'success': False, 'message': validate_message})

        if '姓名' not in col_names:
            return jsonify({'success': False, 'message': "当前表缺少‘姓名’字段，暂不支持个人维护，请联系管理员统一维护"})

        set_clauses = []
        for k, v in updates.items():
            if k in allowed_cols:
                safe_v = _escape_sql_literal_for_pytds(v)
                safe_col = '[' + str(k).replace(']', ']]') + ']'
                set_clauses.append(f"{safe_col} = '{safe_v}'")
        if not set_clauses:
            return jsonify({'success': False, 'message': '没有可更新的字段'})

        count = bjc.sf_db(f"SELECT COUNT(*) FROM {sender_table} WHERE 姓名 = '{safe_user}'", single=True)
        if not count or count < 1:
            return jsonify(
                {'success': False, 'message': f'你的记录不存在，请联系管理员在 {sender_table} 表添加后再修改'})

        sql = f"UPDATE {sender_table} SET {', '.join(set_clauses)} WHERE 姓名 = '{safe_user}'"
        bjc.dui_db(sql)
        return jsonify({'success': True, 'message': '邮箱账户更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'})


@influencer_management_bp.route('/add_my_email_account', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/add_my_email_account', methods=['POST'])
@require_permission('tk_email_register')
def add_my_email_account():
    """为当前用户新增邮箱账户记录到 tk_fenzu_youxiang 表"""
    try:
        sender_table = "FaYouJian_JS_YouXiang" if request.path.startswith('/tk_email_register_js/') else "tk_fenzu_youxiang"

        data = request.get_json() or {}
        email_data = data.get('email_data', {})
        if not isinstance(email_data, dict) or not email_data:
            return jsonify({'success': False, 'message': '缺少邮箱账户信息'})

        current_user = get_current_user_name()
        if not current_user:
            return jsonify({'success': False, 'message': '无法获取当前用户信息'})
        safe_user = _escape_sql_literal_for_pytds(current_user)

        # 获取表结构
        columns = bjc.sf_db(
            f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{sender_table}' ORDER BY ORDINAL_POSITION")
        if not columns:
            return jsonify({'success': False, 'message': f'未找到 {sender_table} 表结构'})
        col_names = [str(c) for c in columns]  # 修复：直接使用字符串，不需要取[0]
        email_data = _apply_sender_group_leader(email_data, sender_table, col_names)

        # 检查是否有"姓名"字段
        if '姓名' not in col_names:
            return jsonify({'success': False, 'message': "当前表缺少'姓名'字段，暂不支持新增邮箱账户，请联系管理员"})

        # 允许用户添加多个邮箱账户记录，移除重复检查限制
        # 注释：用户可以拥有多个邮箱账户记录

        email_cols = [c for c in col_names if _is_sender_email_col(c)]

        if not email_cols:
            # 尝试从数据内容推断
            sample_rows = bjc.sf_db(f"SELECT TOP 100 * FROM {sender_table}")
            if sample_rows:
                col_has_email = {c: False for c in col_names}
                for row in sample_rows:
                    for i, val in enumerate(row):
                        if val is None:
                            continue
                        s = str(val).strip()
                        if s and ('@' in s) and (' ' not in s):
                            col_has_email[col_names[i]] = True
                email_cols = [c for c, has in col_has_email.items() if has and c != '姓名']

        if not email_cols:
            return jsonify({'success': False, 'message': '未识别到邮箱字段，请联系管理员维护表结构'})

        # 验证邮箱格式（仅对邮箱字段进行验证）
        for field_name, field_value in email_data.items():
            if field_name in email_cols and field_value:
                email_val = str(field_value).strip()
                if email_val and ('@' not in email_val or ' ' in email_val):
                    return jsonify({'success': False, 'message': f'字段 {field_name} 的邮箱格式不正确'})

        if _should_validate_sender_credentials(email_data, col_names):
            valid, validate_message = _validate_sender_account_credentials(email_data, col_names)
            if not valid:
                return jsonify({'success': False, 'message': validate_message})

        # 构建插入语句
        insert_cols = ['姓名']
        insert_vals = [f"'{safe_user}'"]

        for field_name, field_value in email_data.items():
            if field_name in col_names and field_name != '姓名':  # 允许所有字段，除了姓名字段
                safe_col = '[' + str(field_name).replace(']', ']]') + ']'
                safe_val = _escape_sql_literal_for_pytds(field_value) if field_value else ''
                insert_cols.append(safe_col)
                insert_vals.append(f"'{safe_val}'")

        sql = f"INSERT INTO {sender_table} ({', '.join(insert_cols)}) VALUES ({', '.join(insert_vals)})"
        bjc.dui_db(sql)

        return jsonify({'success': True, 'message': '邮箱账户新增成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'新增失败: {str(e)}'})


@influencer_management_bp.route('/get_template_image', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/get_template_image', methods=['POST'])
@require_permission('tk_email_register')
def get_template_image():
    """按需获取指定模板的图片数据"""
    try:
        template_table = "js_youjian_moban" if request.path.startswith('/tk_email_register_js/') else "tk_youjian_moban"

        def _guess_image_mime(b):
            if not b:
                return "image/jpeg"
            if b.startswith(b"\xFF\xD8\xFF"):
                return "image/jpeg"
            if b.startswith(b"\x89PNG\r\n\x1a\n"):
                return "image/png"
            if b.startswith(b"GIF87a") or b.startswith(b"GIF89a"):
                return "image/gif"
            if len(b) >= 12 and b[0:4] == b"RIFF" and b[8:12] == b"WEBP":
                return "image/webp"
            return "image/jpeg"

        def _to_data_url_from_bytes(bb):
            import base64
            mime = _guess_image_mime(bb)
            base64_data = base64.b64encode(bb).decode('utf-8')
            image_src = f"data:{mime};base64," + base64_data
            print("图片数据转换成功，长度: " + str(len(base64_data)))
            return image_src

        def _decode_template_image_value(v):
            if v is None:
                return "", "图片数据为空"

            if isinstance(v, (bytes, bytearray, memoryview)):
                bb = bytes(v)
                if not bb:
                    return "", "图片数据为空"
                return _to_data_url_from_bytes(bb), ""

            if isinstance(v, str):
                s0 = (v or "").strip()
                if not s0:
                    return "", "图片数据为空"
                if s0.startswith("data:image/"):
                    return s0, ""

                try:
                    import ast
                    lit = ast.literal_eval(s0)
                    if isinstance(lit, (bytes, bytearray, memoryview)):
                        bb = bytes(lit)
                        if bb:
                            return _to_data_url_from_bytes(bb), ""
                except Exception:
                    pass

                s = s0
                if s.lower().startswith('0x'):
                    s = s[2:]
                s = re.sub(r"\s+", "", s)

                try:
                    if len(s) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", s):
                        bb = bytes.fromhex(s)
                        if bb:
                            return _to_data_url_from_bytes(bb), ""
                except Exception:
                    pass

                try:
                    import base64
                    padded = s + ("=" * (-len(s) % 4))
                    bb = base64.b64decode(padded, validate=True)
                    if bb:
                        return _to_data_url_from_bytes(bb), ""
                except Exception:
                    pass

                return "", "图片数据格式错误"

            if isinstance(v, int):
                return "", "图片数据异常，请重新上传图片"

            try:
                bb = bytes(v)
                if bb:
                    return _to_data_url_from_bytes(bb), ""
            except Exception:
                pass

            return "", "图片数据类型异常: " + str(type(v))

        data = request.get_json()
        template_name = data.get('templateName', '')

        print("获取模板图片请求: " + template_name)

        if not template_name:
            return jsonify({'success': False, 'message': '模板名称不能为空'})

        # 使用原生SQL连接来正确处理image数据类型
        import pytds as sql
        con = sql.connect(**sql_server_config())
        cursor = con.cursor()

        # 查询指定模板的图片数据
        sql_query = f"SELECT TuPian FROM {template_table} WHERE MoBanMing = %s"
        cursor.execute(sql_query, (template_name,))
        result = cursor.fetchone()

        print("数据库查询结果: " + str(result is not None))

        if result and result[0] is not None:
            tupian_data = result[0]
            print("图片数据类型: " + str(type(tupian_data)))

            image_src, err = _decode_template_image_value(tupian_data)
            con.close()
            if err:
                return jsonify({'success': False, 'message': err})
            return jsonify({'success': True, 'tupian': image_src})
        else:
            print("图片数据为空或模板不存在")
            con.close()
            return jsonify({'success': False, 'message': '该模板没有图片或模板不存在'})

    except Exception as e:
        print("获取图片失败: " + str(e))
        if 'con' in locals():
            con.close()
        return jsonify({'success': False, 'message': '获取图片失败: ' + str(e)})


@influencer_management_bp.route('/add_email_template', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/add_email_template', methods=['POST'])
@require_permission('tk_email_register')
def add_email_template():
    """添加邮件模板"""
    try:
        template_table = "js_youjian_moban" if request.path.startswith('/tk_email_register_js/') else "tk_youjian_moban"

        def _decode_email_image_payload(payload):
            s = (payload or "").strip()
            if not s:
                return None, "", False

            if s.startswith("data:image/"):
                try:
                    import base64
                    b64_part = s.split(",", 1)[1] if "," in s else ""
                    if not b64_part:
                        return None, "图片数据格式错误", True
                    return base64.b64decode(b64_part), "", True
                except Exception:
                    return None, "图片数据格式错误", True

            try:
                import ast
                lit = ast.literal_eval(s)
                if isinstance(lit, (bytes, bytearray, memoryview)):
                    bb = bytes(lit)
                    if bb:
                        return bb, "", True
            except Exception:
                pass

            ss = s[2:] if s.lower().startswith("0x") else s
            ss = re.sub(r"\s+", "", ss)
            try:
                if len(ss) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", ss):
                    return bytes.fromhex(ss), "", True
            except Exception:
                return None, "图片数据格式错误", True

            try:
                import base64
                padded = ss + ("=" * (-len(ss) % 4))
                bb = base64.b64decode(padded, validate=True)
                if bb:
                    return bb, "", True
            except Exception:
                pass

            return None, "图片数据格式错误", True

        data = request.get_json()
        moban_ming = data.get('mobanMing', '')
        moban = data.get('moban', '')
        youjianbiaoti = data.get('youjianbiaoti', '')  # 邮件标题
        tupian = data.get('tupian', '')  # 图片数据（支持dataURL/base64或hex）

        if not moban_ming or not moban:
            return jsonify({'success': False, 'message': '模板名称和内容不能为空'})

        # 检查模板名称是否已存在
        safe_check_name = _escape_sql_literal_for_pytds(moban_ming)
        check_sql = f"SELECT COUNT(*) FROM {template_table} WHERE MoBanMing = '{safe_check_name}'"
        count = bjc.sf_db(check_sql, single=True)
        if count and count > 0:
            return jsonify({'success': False, 'message': '模板名称已存在，请使用其他名称'})

        # 获取当前用户作为创建人
        chuang_jian_ren = get_current_user_name()
        if not chuang_jian_ren:
            chuang_jian_ren = '系统'

        # 获取当前时间
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 处理图片数据
        image_data, image_err, _ = _decode_email_image_payload(tupian)
        if image_err:
            return jsonify({'success': False, 'message': image_err})

        # 使用参数化查询来避免SQL注入并保持格式不变
        try:
            # 使用原生SQL连接来正确处理image数据类型
            import pytds as sql
            con = sql.connect(**sql_server_config())
            cursor = con.cursor()

            sql_query = f"INSERT INTO {template_table} (MoBanMing, MoBan, YouJianBiaoTi, TuPian, ChuangJianRen, ChuangJianShiJian) VALUES (%s, %s, %s, %s, %s, %s)"
            cursor.execute(sql_query, (moban_ming, moban, youjianbiaoti, image_data, chuang_jian_ren, current_time))
            con.commit()
            con.close()

        except Exception as e:
            print(f"使用原生连接失败，尝试传统方法: {e}")
            # 如果原生连接失败，使用传统方法
            # 只转义单引号，保持其他格式字符不变
            safe_moban_ming = _escape_sql_literal_for_pytds(moban_ming)
            safe_moban = _escape_sql_literal_for_pytds(moban)
            safe_youjianbiaoti = _escape_sql_literal_for_pytds(youjianbiaoti) if youjianbiaoti else ''
            safe_chuang_jian_ren = _escape_sql_literal_for_pytds(chuang_jian_ren)

            # 对于二进制数据，需要特殊处理
            if image_data:
                hex_data = '0x' + image_data.hex()
                sql = f"INSERT INTO {template_table} (MoBanMing, MoBan, YouJianBiaoTi, TuPian, ChuangJianRen, ChuangJianShiJian) VALUES ('" + safe_moban_ming + "', '" + safe_moban + "', '" + safe_youjianbiaoti + "', " + hex_data + ", '" + safe_chuang_jian_ren + "', '" + current_time + "')"
            else:
                sql = f"INSERT INTO {template_table} (MoBanMing, MoBan, YouJianBiaoTi, TuPian, ChuangJianRen, ChuangJianShiJian) VALUES ('" + safe_moban_ming + "', '" + safe_moban + "', '" + safe_youjianbiaoti + "', NULL, '" + safe_chuang_jian_ren + "', '" + current_time + "')"

            bjc.dui_db(sql)

        return jsonify({'success': True, 'message': '模板添加成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'添加模板失败: {str(e)}'})


@influencer_management_bp.route('/update_email_template', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/update_email_template', methods=['POST'])
@require_permission('tk_email_register')
def update_email_template():
    """修改邮件模板"""
    try:
        template_table = "js_youjian_moban" if request.path.startswith('/tk_email_register_js/') else "tk_youjian_moban"

        def _decode_email_image_payload(payload):
            s = (payload or "").strip()
            if not s:
                return None, "", False

            if s.startswith("data:image/"):
                try:
                    import base64
                    b64_part = s.split(",", 1)[1] if "," in s else ""
                    if not b64_part:
                        return None, "图片数据格式错误", True
                    return base64.b64decode(b64_part), "", True
                except Exception:
                    return None, "图片数据格式错误", True

            try:
                import ast
                lit = ast.literal_eval(s)
                if isinstance(lit, (bytes, bytearray, memoryview)):
                    bb = bytes(lit)
                    if bb:
                        return bb, "", True
            except Exception:
                pass

            ss = s[2:] if s.lower().startswith("0x") else s
            ss = re.sub(r"\s+", "", ss)
            try:
                if len(ss) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", ss):
                    return bytes.fromhex(ss), "", True
            except Exception:
                return None, "图片数据格式错误", True

            try:
                import base64
                padded = ss + ("=" * (-len(ss) % 4))
                bb = base64.b64decode(padded, validate=True)
                if bb:
                    return bb, "", True
            except Exception:
                pass

            return None, "图片数据格式错误", True

        data = request.get_json()
        template_id = data.get('id', '')
        moban_ming = data.get('mobanMing', '')
        moban = data.get('moban', '')
        youjianbiaoti = data.get('youjianbiaoti', '')  # 邮件标题
        tupian = data.get('tupian', '')  # 图片数据（支持dataURL/base64或hex）

        if not template_id or not moban_ming or not moban:
            return jsonify({'success': False, 'message': '模板ID、名称和内容不能为空'})

        try:
            template_id_int = int(str(template_id).strip())
        except Exception:
            return jsonify({'success': False, 'message': '模板ID格式错误'})

        # 检查模板是否存在
        check_sql = f"SELECT COUNT(*) FROM {template_table} WHERE ID = {template_id_int}"
        count = bjc.sf_db(check_sql, single=True)
        if not count or count == 0:
            return jsonify({'success': False, 'message': '模板不存在'})

        locked_name_sql = f"SELECT MoBanMing FROM {template_table} WHERE ID = {template_id_int}"
        locked_name_rows = bjc.sf_db(locked_name_sql) or []
        locked_name = str(locked_name_rows[0][0]).strip() if locked_name_rows and locked_name_rows[0] and locked_name_rows[0][0] is not None else ""
        if locked_name == '默认模板':
            return jsonify({'success': False, 'message': '默认模板不可修改'})

        # 检查模板名称是否与其他模板重复（排除当前模板）
        safe_check_name = _escape_sql_literal_for_pytds(moban_ming)
        name_check_sql = f"SELECT COUNT(*) FROM {template_table} WHERE MoBanMing = '{safe_check_name}' AND ID != {template_id_int}"
        name_count = bjc.sf_db(name_check_sql, single=True)
        if name_count and name_count > 0:
            return jsonify({'success': False, 'message': '模板名称已存在，请使用其他名称'})

        # 获取当前用户作为修改人
        xiu_gai_ren = get_current_user_name()
        if not xiu_gai_ren:
            xiu_gai_ren = '系统'

        # 获取当前时间
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 处理图片数据
        image_data, image_err, image_provided = _decode_email_image_payload(tupian)
        if image_err:
            return jsonify({'success': False, 'message': image_err})

        try:
            import pytds as sql
            con = sql.connect(**sql_server_config())
            cursor = con.cursor()
            if image_provided:
                sql_query = f"UPDATE {template_table} SET MoBanMing = %s, MoBan = %s, YouJianBiaoTi = %s, TuPian = %s, XiuGaiRen = %s, XiuGaiShiJian = %s WHERE ID = %s"
                cursor.execute(sql_query, (moban_ming, moban, youjianbiaoti, image_data, xiu_gai_ren, current_time, template_id_int))
            else:
                sql_query = f"UPDATE {template_table} SET MoBanMing = %s, MoBan = %s, YouJianBiaoTi = %s, XiuGaiRen = %s, XiuGaiShiJian = %s WHERE ID = %s"
                cursor.execute(sql_query, (moban_ming, moban, youjianbiaoti, xiu_gai_ren, current_time, template_id_int))
            con.commit()
            con.close()
        except Exception as e:
            safe_moban_ming = _escape_sql_literal_for_pytds(moban_ming)
            safe_moban = _escape_sql_literal_for_pytds(moban)
            safe_youjianbiaoti = _escape_sql_literal_for_pytds(youjianbiaoti) if youjianbiaoti else ''
            safe_xiu_gai_ren = _escape_sql_literal_for_pytds(xiu_gai_ren)

            if image_provided:
                if image_data:
                    hex_data = '0x' + image_data.hex()
                else:
                    hex_data = 'NULL'
                sql = f"UPDATE {template_table} SET MoBanMing = '" + safe_moban_ming + "', MoBan = '" + safe_moban + "', YouJianBiaoTi = '" + safe_youjianbiaoti + "', TuPian = " + hex_data + ", XiuGaiRen = '" + safe_xiu_gai_ren + "', XiuGaiShiJian = '" + current_time + "' WHERE ID = " + str(template_id_int)
            else:
                sql = f"UPDATE {template_table} SET MoBanMing = '" + safe_moban_ming + "', MoBan = '" + safe_moban + "', YouJianBiaoTi = '" + safe_youjianbiaoti + "', XiuGaiRen = '" + safe_xiu_gai_ren + "', XiuGaiShiJian = '" + current_time + "' WHERE ID = " + str(template_id_int)
            bjc.dui_db(sql)

        return jsonify({'success': True, 'message': '模板修改成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'修改模板失败: {str(e)}'})


@influencer_management_bp.route('/delete_email_template', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/delete_email_template', methods=['POST'])
@require_permission('tk_email_register')
def delete_email_template():
    """删除邮件模板"""
    try:
        template_table = "js_youjian_moban" if request.path.startswith('/tk_email_register_js/') else "tk_youjian_moban"

        data = request.get_json(silent=True) or {}
        template_id = data.get('id', '')
        if template_id is None or str(template_id).strip() == '':
            return jsonify({'success': False, 'message': '模板ID不能为空'})

        try:
            template_id_int = int(str(template_id).strip())
        except Exception:
            return jsonify({'success': False, 'message': '模板ID格式错误'})

        check_sql = f"SELECT COUNT(*) FROM {template_table} WHERE ID = {template_id_int}"
        count = bjc.sf_db(check_sql, single=True)
        if not count or int(count) == 0:
            return jsonify({'success': False, 'message': '模板不存在或已被删除'})

        locked_name_sql = f"SELECT MoBanMing FROM {template_table} WHERE ID = {template_id_int}"
        locked_name_rows = bjc.sf_db(locked_name_sql) or []
        locked_name = str(locked_name_rows[0][0]).strip() if locked_name_rows and locked_name_rows[0] and locked_name_rows[0][0] is not None else ""
        if locked_name == '默认模板':
            return jsonify({'success': False, 'message': '默认模板不可删除'})

        bjc.dui_db(f"DELETE FROM {template_table} WHERE ID = {template_id_int}")
        return jsonify({'success': True, 'message': '模板删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除模板失败: {str(e)}'})


@influencer_management_bp.route('/batch_import_emails', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/batch_import_emails', methods=['POST'])
@require_permission('tk_email_register')
def batch_import_emails():
    """批量导入邮箱信息（支持选择发件邮箱并平均分配）"""
    try:
        email_table = "FaYouJian_JS" if request.path.startswith('/tk_email_register_js/') else "TK_FaYouJian"

        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未上传文件'})

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'})

        if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls') or file.filename.endswith('.csv')):
            return jsonify({'success': False, 'message': '文件格式不支持，请上传Excel或CSV文件'})

        # 使用辅助函数获取当前登录用户的姓名作为申请人
        shen_qing_ren = get_current_user_name()

        # 如果session中没有用户名，则尝试从前端传来的数据获取
        if not shen_qing_ren:
            shen_qing_ren = request.form.get('shenQingRen', '')
            if not shen_qing_ren:
                return jsonify({'success': False, 'message': '无法获取申请人姓名，请手动输入', 'field': 'ShenQingRen'})

        # 验证申请人是否存在于ComputerName表的cname字段中
        if not check_applicant_exists(shen_qing_ren):
            return jsonify(
                {'success': False, 'message': f'申请人 {shen_qing_ren} 不存在于系统中', 'field': 'ShenQingRen'})

        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 读取Excel或CSV文件
        try:
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
        except Exception as e:
            return jsonify({'success': False, 'message': f'文件读取失败: {str(e)}'})

        # 检查必要的列是否存在
        required_columns = ['YouXiang', 'XingMing']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return jsonify({'success': False, 'message': f'文件缺少必要的列: {", ".join(missing_columns)}'})

        # 解析前端传递的默认与附加发件邮箱
        default_sender_email = (request.form.get('default_sender_email', '') or '').strip()
        extra_sender_emails = request.form.getlist('extra_sender_emails[]')
        if not extra_sender_emails:
            extras_raw = request.form.get('extra_sender_emails', '')
            if extras_raw:
                extra_sender_emails = [e.strip() for e in extras_raw.split(',') if e.strip()]
        selected_senders = []
        if default_sender_email:
            selected_senders.append(default_sender_email)
        for e in extra_sender_emails:
            if e and e not in selected_senders:
                selected_senders.append(e)
        # 必须至少选择一个发件邮箱
        if not selected_senders:
            return jsonify({'success': False, 'message': '请先选择默认发送邮箱或勾选其他属于你的邮箱'})

        # 动态检测发件邮箱列，优先使用'shenqingrenyouxiang'
        try:
            tb_cols = bjc.sf_db(
                f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{email_table}' ORDER BY ORDINAL_POSITION") or []
            # 兼容不同返回结构，正确提取列名
            col_names = []
            for c in tb_cols:
                if isinstance(c, (list, tuple)):
                    col_names.append(str(c[0]))
                elif isinstance(c, dict):
                    col_names.append(str(c.get('COLUMN_NAME') or c.get('column_name') or ''))
                else:
                    col_names.append(str(c))
            col_names = [name for name in col_names if name]
            lower_names = [name.lower() for name in col_names]
            if 'shenqingrenyouxiang' in lower_names:
                sender_col = col_names[lower_names.index('shenqingrenyouxiang')]
            elif 'youjiantou' in lower_names:
                sender_col = col_names[lower_names.index('youjiantou')]
            else:
                # 兜底：优先匹配包含 'youjian' 或 'sender' 的列
                candidates = [n for n in col_names if ('youjian' in n.lower() or 'sender' in n.lower() or 'email' in n.lower())]
                sender_col = candidates[0] if candidates else 'shenqingrenyouxiang'
            print('[batch_import_emails] 检测到发件邮箱列为:', sender_col)
        except Exception as e:
            print(f"检测发件邮箱列失败，默认使用'shenqingrenyouxiang': {str(e)}")
            sender_col = 'shenqingrenyouxiang'

        # 批量插入数据，按选择的发件邮箱平均分配
        success_count = 0
        error_count = 0
        inserted_total = 0  # 实际写入数据库的记录数
        batch_values = []
        batch_size = 100  # 每批插入100条记录
        assignment_counter = 0  # 用于轮询分配发件邮箱

        # 转义申请人名称中的单引号
        safe_shen_qing_ren = shen_qing_ren.replace("'", "''")

        for index, row in df.iterrows():
            try:
                # 处理可能的NaN值和数据类型问题
                youxiang = str(row['YouXiang']) if pd.notna(row['YouXiang']) else ''
                xingming = str(row['XingMing']) if pd.notna(row['XingMing']) else ''

                # 跳过空邮箱
                if not youxiang.strip():
                    continue

                # 至少检查邮箱包含@且不含空格
                if '@' not in youxiang or (' ' in youxiang):
                    error_count += 1
                    print(f"无效邮箱，跳过: {youxiang}")
                    continue

                # 转义单引号
                safe_youxiang = youxiang.replace("'", "''")
                safe_xingming = xingming.replace("'", "''")

                # 检查该邮箱是否已经标记为已回复（shifouhuifu = 'Y'）
                try:
                    check_replied_sql = f"SELECT COUNT(*) FROM {email_table} WHERE youxiang = '{safe_youxiang}' AND shifouhuifu = 'Y'"
                    replied_count = bjc.sf_db(check_replied_sql, single=True)

                    if replied_count and replied_count > 0:
                        print(f"邮箱 {youxiang} 已标记为已回复，跳过导入")
                        continue  # 跳过已回复的邮箱

                except Exception as check_e:
                    print(f"检查邮箱回复状态失败: {str(check_e)}")
                    # 如果检查失败，继续导入流程

                # 将邮箱拥有者设置为申请人
                safe_assigned_name = safe_shen_qing_ren

                # 轮询选择发件邮箱
                sender_email = selected_senders[assignment_counter % len(selected_senders)]
                safe_sender = sender_email.replace("'", "''")
                assignment_counter += 1

                # 构建VALUES子句，写入动态发件邮箱列
                value_clause = f"('{safe_youxiang}', '{safe_xingming}', '{safe_assigned_name}', '{safe_shen_qing_ren}', '{current_time}', '{safe_sender}')"
                batch_values.append(value_clause)
                success_count += 1

                # 当达到批量大小或处理完所有数据时，执行批量插入
                if len(batch_values) >= batch_size or index == len(df) - 1:
                    try:
                        # 构建批量插入SQL，发件邮箱列动态为 sender_col（优先 shenqingrenyouxiang）
                        insert_cols = f"(YouXiang, XingMing, YouXiangYongYouZhe, ShenQingRen, ShenQingShiJian, {sender_col})"
                        batch_sql = f"INSERT INTO {email_table} {insert_cols} VALUES {','.join(batch_values)}"
                        print('[batch_import_emails] 执行批量插入 SQL 列:', insert_cols)
                        print('[batch_import_emails] 执行批量插入 数量:', len(batch_values))
                        bjc.dui_db(batch_sql)
                        inserted_total += len(batch_values)
                        print(f"成功批量插入 {len(batch_values)} 条记录")
                        batch_values = []  # 清空批次
                    except Exception as batch_e:
                        print(f"批量插入失败，尝试逐条插入: {str(batch_e)}")
                        # 如果批量插入失败，回退到逐条插入
                        for value in batch_values:
                            try:
                                single_sql = f"INSERT INTO {email_table} {insert_cols} VALUES {value}"
                                bjc.dui_db(single_sql)
                                inserted_total += 1
                            except Exception as single_e:
                                error_count += 1
                                success_count -= 1
                                print(f"单条插入失败: {str(single_e)}")
                        batch_values = []  # 清空批次

            except Exception as e:
                error_count += 1
                success_count -= 1
                print(f"数据处理错误: {str(e)}")
                continue  # 继续处理下一行

        # 循环结束后，如仍有未提交的批次（可能因为最后几行被跳过而未触发 index==last 条件），则提交
        if batch_values:
            try:
                insert_cols = f"(YouXiang, XingMing, YouXiangYongYouZhe, ShenQingRen, ShenQingShiJian, {sender_col})"
                batch_sql = f"INSERT INTO {email_table} {insert_cols} VALUES {','.join(batch_values)}"
                print('[batch_import_emails] 尾批次提交 SQL 列:', insert_cols)
                print('[batch_import_emails] 尾批次提交 数量:', len(batch_values))
                bjc.dui_db(batch_sql)
                inserted_total += len(batch_values)
                print(f"成功尾批次插入 {len(batch_values)} 条记录")
            except Exception as tail_e:
                print(f"尾批次插入失败: {str(tail_e)}")
                for value in batch_values:
                    try:
                        single_sql = f"INSERT INTO {email_table} {insert_cols} VALUES {value}"
                        bjc.dui_db(single_sql)
                        inserted_total += 1
                    except Exception as single_e:
                        error_count += 1
                        success_count -= 1
                        print(f"尾批次单条插入失败: {str(single_e)}")
            finally:
                batch_values = []

        if inserted_total == 0:
            return jsonify({'success': False, 'message': '导入失败，没有有效数据或全部导入出错'})

        message = f'成功导入{inserted_total}条邮件记录'
        if error_count > 0:
            message += f'，{error_count}条记录导入失败'

        return jsonify({'success': True, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': f'批量导入失败: {str(e)}'})


@influencer_management_bp.route('/batch_mark_replied', methods=['POST'])
@require_permission('influencer_management')
def batch_mark_replied():
    """批量标记邮箱为已回复状态"""
    try:
        data = request.get_json()
        emails = data.get('emails', [])

        if not emails:
            return jsonify({'success': False, 'message': '请提供要标记的邮箱地址'})

        # 验证邮箱格式
        import re
        email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        invalid_emails = [email for email in emails if not re.match(email_pattern, email)]

        if invalid_emails:
            return jsonify({
                'success': False,
                'message': f'以下邮箱格式不正确: {", ".join(invalid_emails)}'
            })

        # 批量更新数据库
        updated_count = 0
        failed_emails = []

        for email in emails:
            try:
                # 使用参数化查询防止SQL注入
                safe_email = email.replace("'", "''")
                sql = f"UPDATE TK_FaYouJian SET shifouhuifu = 'Y' WHERE youxiang = '{safe_email}'"

                # 执行更新
                bjc.dui_db(sql)

                # 检查是否有记录被更新
                check_sql = f"SELECT COUNT(*) FROM TK_FaYouJian WHERE youxiang = '{safe_email}'"
                count = bjc.sf_db(check_sql, single=True)

                if count > 0:
                    updated_count += 1
                else:
                    failed_emails.append(f"{email}(未找到记录)")

            except Exception as e:
                failed_emails.append(f"{email}(更新失败: {str(e)})")
                print(f"更新邮箱 {email} 失败: {str(e)}")

        # 构建返回消息
        if updated_count > 0:
            message = f'成功标记 {updated_count} 个邮箱为已回复状态'
            if failed_emails:
                message += f'\n\n以下邮箱处理失败:\n{", ".join(failed_emails)}'

            return jsonify({
                'success': True,
                'message': message,
                'updated_count': updated_count,
                'failed_count': len(failed_emails)
            })
        else:
            return jsonify({
                'success': False,
                'message': f'没有邮箱被标记为已回复。失败原因:\n{", ".join(failed_emails)}'
            })

    except Exception as e:
        print(f"批量标记已回复邮箱失败: {str(e)}")
        return jsonify({'success': False, 'message': f'批量标记失败: {str(e)}'})


@influencer_management_bp.route('/tk_email_register_js/batch_mark_replied', methods=['POST'])
@require_permission('tk_email_register')
def batch_mark_replied_js():
    """批量标记邮箱为已回复状态（技术部专用表）"""
    try:
        email_table = "FaYouJian_JS"

        data = request.get_json()
        emails = data.get('emails', [])

        if not emails:
            return jsonify({'success': False, 'message': '请提供要标记的邮箱地址'})

        import re
        email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        invalid_emails = [email for email in emails if not re.match(email_pattern, email)]

        if invalid_emails:
            return jsonify({
                'success': False,
                'message': f'以下邮箱格式不正确: {", ".join(invalid_emails)}'
            })

        updated_count = 0
        failed_emails = []

        for email in emails:
            try:
                safe_email = email.replace("'", "''")
                sql = f"UPDATE {email_table} SET shifouhuifu = 'Y' WHERE youxiang = '{safe_email}'"
                bjc.dui_db(sql)

                check_sql = f"SELECT COUNT(*) FROM {email_table} WHERE youxiang = '{safe_email}'"
                count = bjc.sf_db(check_sql, single=True)

                if count > 0:
                    updated_count += 1
                else:
                    failed_emails.append(f"{email}(未找到记录)")

            except Exception as e:
                failed_emails.append(f"{email}(更新失败: {str(e)})")
                print(f"更新邮箱 {email} 失败: {str(e)}")

        if updated_count > 0:
            message = f'成功标记 {updated_count} 个邮箱为已回复状态'
            if failed_emails:
                message += f'\n\n以下邮箱处理失败:\n{", ".join(failed_emails)}'

            return jsonify({
                'success': True,
                'message': message,
                'updated_count': updated_count,
                'failed_count': len(failed_emails)
            })
        else:
            return jsonify({
                'success': False,
                'message': f'没有邮箱被标记为已回复。失败原因:\n{", ".join(failed_emails)}'
            })

    except Exception as e:
        print(f"批量标记已回复邮箱失败: {str(e)}")
        return jsonify({'success': False, 'message': f'批量标记失败: {str(e)}'})


@influencer_management_bp.route('/upload_email_image', methods=['POST'])
@influencer_management_bp.route('/tk_email_register_js/upload_email_image', methods=['POST'])
@require_permission('tk_email_register')
def upload_email_image():
    """上传邮件图片"""
    try:
        def _normalize_email_image(image_bytes, file_type="", filename=""):
            ft = str(file_type or "").strip().lower()
            fn = str(filename or "").strip()
            ext = ""
            if "." in fn:
                ext = fn.rsplit(".", 1)[1].strip().lower()

            if not ft:
                if ext in {"jpg", "jpeg"}:
                    ft = "image/jpeg"
                elif ext == "png":
                    ft = "image/png"
                elif ext == "gif":
                    ft = "image/gif"
                elif ext == "webp":
                    ft = "image/webp"

            target_max_bytes = 5 * 1024 * 1024
            if not image_bytes:
                return b"", "图片数据为空", "", ""

            if ft == "image/gif":
                if len(image_bytes) > target_max_bytes:
                    return b"", "图片大小不能超过5MB", "", ""
                return image_bytes, "", ft, fn

            try:
                from PIL import Image
                import io

                img = Image.open(io.BytesIO(image_bytes))
                if getattr(img, "is_animated", False):
                    if len(image_bytes) > target_max_bytes:
                        return b"", "图片大小不能超过5MB", "", ""
                    return image_bytes, "", ft or "image/gif", fn

                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")

                def encode_jpeg(quality, max_w=None, max_h=None):
                    out_img = img
                    if max_w and max_h:
                        w, h = out_img.size
                        if w > max_w or h > max_h:
                            out_img = out_img.copy()
                            out_img.thumbnail((max_w, max_h))
                    bio = io.BytesIO()
                    out_img.save(bio, format="JPEG", quality=int(quality), optimize=True, progressive=True)
                    return bio.getvalue(), out_img.size

                jpeg_bytes, _ = encode_jpeg(quality=88)
                if len(jpeg_bytes) <= target_max_bytes:
                    out_name = fn
                    if out_name and "." in out_name:
                        out_name = out_name.rsplit(".", 1)[0] + ".jpg"
                    return jpeg_bytes, "", "image/jpeg", out_name

                max_w, max_h = 1920, 1920
                for quality in [82, 76, 70, 64, 58, 52]:
                    jpeg_bytes, size = encode_jpeg(quality=quality, max_w=max_w, max_h=max_h)
                    if len(jpeg_bytes) <= target_max_bytes:
                        out_name = fn
                        if out_name and "." in out_name:
                            out_name = out_name.rsplit(".", 1)[0] + ".jpg"
                        return jpeg_bytes, "", "image/jpeg", out_name
                    if max_w > 1200:
                        max_w = int(max_w * 0.85)
                        max_h = int(max_h * 0.85)

                return b"", "图片过大，已尝试压缩仍超过5MB，请换小一点的图片", "", ""
            except Exception:
                allowed_types = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}
                if (not ft) or (ft not in allowed_types):
                    return b"", "不支持的文件类型（仅支持JPG/PNG/GIF/WEBP）", "", ""
                if len(image_bytes) > target_max_bytes:
                    return b"", "图片大小不能超过5MB", "", ""
                return image_bytes, "", ft, fn

        # 检查是否是JSON格式的Base64数据
        if request.is_json:
            data = request.get_json()
            image_data = data.get('image_data')
            filename = data.get('filename')
            file_type = data.get('file_type')

            if not image_data or not filename:
                return jsonify({'success': False, 'message': '缺少必要的图片数据'})

            # 解析Base64数据
            try:
                import base64
                # 移除data:image/xxx;base64,前缀
                if ',' in image_data:
                    image_data = image_data.split(',')[1]

                # 解码Base64数据
                image_bytes = base64.b64decode(image_data)
                normalized_bytes, err, normalized_type, normalized_name = _normalize_email_image(
                    image_bytes,
                    file_type=file_type,
                    filename=filename
                )
                if err:
                    return jsonify({'success': False, 'message': err})

                # 直接返回Base64数据用于数据库存储
                return jsonify({
                    'success': True,
                    'message': '图片处理成功',
                    'image_data': normalized_bytes.hex(),  # 转换为十六进制字符串
                    'filename': normalized_name or filename,
                    'file_type': normalized_type or file_type
                })

            except Exception as e:
                return jsonify({'success': False, 'message': f'图片处理失败: {str(e)}'})

        # 原有的文件上传处理逻辑（保持兼容性）
        else:
            if 'image' not in request.files:
                return jsonify({'success': False, 'message': '没有选择文件'})

            file = request.files['image']
            if file.filename == '':
                return jsonify({'success': False, 'message': '没有选择文件'})

            # 验证文件类型
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
            if not ('.' in file.filename and
                    file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
                return jsonify({'success': False, 'message': '只支持JPG、PNG、GIF、WEBP格式的图片'})

            # 验证文件大小（5MB）
            file.seek(0, 2)  # 移动到文件末尾
            file_size = file.tell()
            file.seek(0)  # 重置文件指针
            if file_size > 5 * 1024 * 1024:
                return jsonify({'success': False, 'message': '图片大小不能超过5MB'})

            # 读取文件内容并转换为二进制数据
            file.seek(0)
            image_bytes = file.read()
            normalized_bytes, err, normalized_type, normalized_name = _normalize_email_image(
                image_bytes,
                file_type=getattr(file, "mimetype", "") or "",
                filename=file.filename
            )
            if err:
                return jsonify({'success': False, 'message': err})

            # 直接返回二进制数据用于数据库存储
            return jsonify({
                'success': True,
                'message': '图片上传成功',
                'image_data': normalized_bytes.hex(),  # 转换为十六进制字符串
                'filename': normalized_name or file.filename,
                'file_type': normalized_type
            })

    except Exception as e:
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'})
