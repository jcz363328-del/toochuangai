from flask import Blueprint, render_template, request, jsonify, session, send_from_directory
from bjc import sf_db, dui_db
from department_permissions import require_permission
import os
import threading
from werkzeug.utils import secure_filename
from innovation.message_service import MessageService
from datetime import datetime
from innovation.message_service import MessageService

model_management_bp = Blueprint('model_management', __name__)

BASE_VIDEO_DIR = r"D:\\模特视频"

def get_user_name():
    return session.get('feishu_user_name', '')

@model_management_bp.route('/model/library')
@require_permission('model_library')
def library():
    return render_template('model_library.html')

@model_management_bp.route('/model/queue')
@require_permission('model_queue')
def queue():
    return render_template('model_queue.html')

@model_management_bp.route('/model/videos/<path:filename>')
def serve_video(filename):
    return send_from_directory(BASE_VIDEO_DIR, filename)

def _resolve_feishu_id(name):
    n = (name or '').strip()
    n = n.replace(' 技术代排', '')
    row = sf_db(f"SELECT FeiShu_ID FROM feishu_id WHERE YONGHU='{n.replace("'", "''")}'", single=True)
    return row or n


def _notify_new_model(user_name, code, name, status, country, level, remark):
    try:
        ms = MessageService()
        dept_names = ['运营一部', '运营二部', '运营三部', '运营六部', 'AI部']
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        message = f"""【模特库新增达人】

上传人：{user_name}
上传时间：{ts}
模特编号：{code}
模特姓名：{name}
状态：{status}
国家：{country}
等级：{level}
备注：{remark or '无'}

请相关运营关注该模特视频素材，若有需求，请务必及时排队！"""
        for dept in dept_names:
            try:
                ms.send_message_to_department_members(dept, message)
            except Exception:
                continue
    except Exception:
        pass


def _notify_new_model_async(user_name, code, name, status, country, level, remark):
    t = threading.Thread(
        target=_notify_new_model,
        args=(user_name, code, name, status, country, level, remark),
        daemon=True,
    )
    t.start()

@model_management_bp.route('/api/models', methods=['GET', 'POST'])
def models():
    if request.method == 'GET':
        user_name = get_user_name().replace("'", "''")
        name = (request.args.get('name', '') or '').strip()
        status = (request.args.get('status', '') or '').strip()
        country = (request.args.get('country', '') or '').strip()
        level = (request.args.get('level', '') or '').strip()
        queue_filter = (request.args.get('queue_filter', '') or '').strip()
        sort = (request.args.get('sort', '') or '').strip()

        name_esc = name.replace("'", "''")
        status_esc = status.replace("'", "''")
        country_esc = country.replace("'", "''")
        level_esc = level.replace("'", "''")

        where_clauses = [f"m.上传人 = '{user_name}'"]
        if name_esc:
            where_clauses.append(f"CHARINDEX('{name_esc}', ISNULL(CAST(m.模特姓名 AS NVARCHAR(200)), '')) > 0")
        if status_esc:
            where_clauses.append(f"m.状态 = '{status_esc}'")
        if country_esc:
            where_clauses.append(f"m.国家 = '{country_esc}'")
        if level_esc:
            where_clauses.append(f"m.等级 = '{level_esc}'")

        base_from = """
            FROM [模特信息] m
            LEFT JOIN (
                SELECT 模特ID, COUNT(*) AS queue_count
                FROM [模特排队]
                WHERE 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0
                GROUP BY 模特ID
            ) qc ON qc.模特ID = m.模特ID
        """

        if queue_filter == 'has':
            where_clauses.append("ISNULL(qc.queue_count, 0) > 0")
        elif queue_filter == 'none':
            where_clauses.append("ISNULL(qc.queue_count, 0) = 0")

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        order_by = "m.创建时间 DESC, m.模特ID DESC"
        if sort == 'queue_count_desc':
            order_by = "ISNULL(qc.queue_count, 0) DESC, m.创建时间 DESC, m.模特ID DESC"
        elif sort == 'queue_count_asc':
            order_by = "ISNULL(qc.queue_count, 0) ASC, m.创建时间 DESC, m.模特ID DESC"
        elif sort == 'created_desc':
            order_by = "m.创建时间 DESC, m.模特ID DESC"

        sql = f"""
            SELECT
                m.模特ID, m.模特编号, m.模特姓名, m.视频地址, m.状态, m.国家, m.等级, m.备注, m.上传人, m.创建时间, m.更新时间,
                ISNULL(qc.queue_count, 0) AS queueing_count
            {base_from}
            {where_sql}
            ORDER BY {order_by}
        """
        rows = sf_db(sql) or []
        data = []
        for r in rows:
            data.append({
                'id': r[0],
                'code': r[1],
                'name': r[2],
                'videos': r[3] or '',
                'status': r[4] or '',
                'country': r[5] or '',
                'level': r[6] or '',
                'remark': r[7] or '',
                'uploader': r[8] or '',
                'created_at': r[9],
                'updated_at': r[10],
                'queueing_count': int(r[11] or 0)
            })
        return jsonify({'success': True, 'data': data})
    else:
        try:
            user_name = get_user_name()
            code = request.form.get('code', '')
            name = request.form.get('name', '')
            status = request.form.get('status', '')
            country = request.form.get('country', '')
            level = request.form.get('level', '')
            remark = request.form.get('remark', '')
            os.makedirs(BASE_VIDEO_DIR, exist_ok=True)
            files = request.files.getlist('videos')
            saved_paths = []
            for f in files:
                if f and f.filename:
                    filename = secure_filename(f.filename)
                    fname = f"{filename}"
                    full_path = os.path.join(BASE_VIDEO_DIR, fname)
                    i = 1
                    base, ext = os.path.splitext(fname)
                    while os.path.exists(full_path):
                        fname = f"{base}_{i}{ext}"
                        full_path = os.path.join(BASE_VIDEO_DIR, fname)
                        i += 1
                    f.save(full_path)
                    saved_paths.append(fname)
            video_field = ';'.join(saved_paths)
            sql = (
                "INSERT INTO [模特信息] (模特编号, 模特姓名, 视频地址, 状态, 国家, 等级, 备注, 上传人, 创建时间, 更新时间) "
                f"VALUES ('{code.replace("'", "''")}', '{name.replace("'", "''")}', '{video_field.replace("'", "''")}', "
                f"'{status.replace("'", "''")}', '{country.replace("'", "''")}', '{level.replace("'", "''")}', "
                f"'{remark.replace("'", "''")}', '{user_name.replace("'", "''")}', GETDATE(), GETDATE())"
            )
            dui_db(sql)
            try:
                _notify_new_model_async(user_name, code, name, status, country, level, remark)
            except Exception:
                pass
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

@model_management_bp.route('/api/models_all', methods=['GET'])
def models_all():
    sql = "SELECT 模特ID, 模特编号, 模特姓名, 视频地址, 状态, 国家, 等级, 备注, 上传人, 创建时间, 更新时间 FROM [模特信息] ORDER BY 创建时间 DESC"
    rows = sf_db(sql) or []
    data = []
    for r in rows:
        data.append({
            'id': r[0],
            'code': r[1],
            'name': r[2],
            'videos': r[3] or '',
            'status': r[4] or '',
            'country': r[5] or '',
            'level': r[6] or '',
            'remark': r[7] or '',
            'uploader': r[8] or '',
            'created_at': r[9],
            'updated_at': r[10]
        })
    return jsonify({'success': True, 'data': data})

@model_management_bp.route('/api/model_queue_overview', methods=['GET'])
def model_queue_overview():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        if page < 1:
            page = 1
        if per_page < 1:
            per_page = 10
        if per_page > 100:
            per_page = 100

        sort = (request.args.get('sort', '') or '').strip()
        name = (request.args.get('name', '') or '').strip()
        responsible = (request.args.get('responsible', '') or '').strip()
        mine_only = (request.args.get('mine_only', '') or '').strip()
        status = (request.args.get('status', '') or '').strip()
        country = (request.args.get('country', '') or '').strip()
        level = (request.args.get('level', '') or '').strip()
        queue_filter = (request.args.get('queue_filter', '') or '').strip()
        order_by = "m.创建时间 DESC, m.模特ID DESC"
        if sort == 'queue_count_desc':
            order_by = "ISNULL(qc.queue_count, 0) DESC, m.创建时间 DESC, m.模特ID DESC"
        elif sort == 'queue_count_asc':
            order_by = "ISNULL(qc.queue_count, 0) ASC, m.创建时间 DESC, m.模特ID DESC"
        elif sort == 'created_desc':
            order_by = "m.创建时间 DESC, m.模特ID DESC"

        name_esc = name.replace("'", "''")
        responsible_esc = responsible.replace("'", "''")
        status_esc = status.replace("'", "''")
        country_esc = country.replace("'", "''")
        level_esc = level.replace("'", "''")

        user = get_user_name().replace("'", "''")

        where_clauses = []
        if name_esc:
            where_clauses.append(f"CHARINDEX('{name_esc}', ISNULL(CAST(m.模特姓名 AS NVARCHAR(200)), '')) > 0")
        if responsible_esc:
            where_clauses.append(f"CHARINDEX('{responsible_esc}', ISNULL(CAST(m.上传人 AS NVARCHAR(200)), '')) > 0")
        if status_esc:
            where_clauses.append(f"m.状态 = '{status_esc}'")
        if country_esc:
            where_clauses.append(f"m.国家 = '{country_esc}'")
        if level_esc:
            where_clauses.append(f"m.等级 = '{level_esc}'")
        if queue_filter == 'has':
            where_clauses.append("ISNULL(qc.queue_count, 0) > 0")
        elif queue_filter == 'none':
            where_clauses.append("ISNULL(qc.queue_count, 0) = 0")
        if mine_only.lower() in ('1', 'true', 'yes'):
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM [模特排队] qmine WHERE qmine.模特ID = m.模特ID AND qmine.创建人 = '{user}' AND qmine.排队状态 IN ('排队中','暂停') AND qmine.视频已完成 = 0)"
            )

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        base_from = """
            FROM [模特信息] m
            LEFT JOIN (
                SELECT 模特ID, COUNT(*) AS queue_count
                FROM [模特排队]
                WHERE 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0
                GROUP BY 模特ID
            ) qc ON qc.模特ID = m.模特ID
        """

        total_sql = f"SELECT COUNT(*) {base_from} {where_sql}"
        total = int(sf_db(total_sql, single=True) or 0)
        total_pages = int((total + per_page - 1) // per_page) if total > 0 else 0
        offset = (page - 1) * per_page
        sql = f"""
            SELECT
                m.模特ID, m.模特编号, m.模特姓名, m.视频地址, m.状态, m.国家, m.等级, m.备注, m.上传人, m.创建时间, m.更新时间,
                ISNULL(qc.queue_count, 0) AS queueing_count,
                CASE WHEN mine.mine_id IS NULL THEN 0 ELSE 1 END AS has_mine_pending,
                CASE
                    WHEN mine.mine_id IS NULL THEN NULL
                    ELSE (
                        SELECT COUNT(*)
                        FROM [模特排队] q2
                        WHERE q2.模特ID = m.模特ID
                          AND q2.排队状态 IN ('排队中','暂停')
                          AND q2.视频已完成 = 0
                          AND (q2.创建时间 < mine.mine_time OR (q2.创建时间 = mine.mine_time AND q2.排队ID < mine.mine_id))
                    )
                END AS position_for_current
            {base_from}
            OUTER APPLY (
                SELECT TOP 1 排队ID AS mine_id, 创建时间 AS mine_time
                FROM [模特排队] q
                WHERE q.模特ID = m.模特ID
                  AND q.创建人 = '{user}'
                  AND q.排队状态 IN ('排队中','暂停')
                  AND q.视频已完成 = 0
                ORDER BY 创建时间 ASC, 排队ID ASC
            ) mine
            {where_sql}
            ORDER BY {order_by}
            OFFSET {offset} ROWS FETCH NEXT {per_page} ROWS ONLY
        """

        rows = sf_db(sql) or []
        data = []
        for r in rows:
            data.append({
                'id': r[0],
                'code': r[1],
                'name': r[2],
                'videos': r[3] or '',
                'status': r[4] or '',
                'country': r[5] or '',
                'level': r[6] or '',
                'remark': r[7] or '',
                'uploader': r[8] or '',
                'created_at': r[9],
                'updated_at': r[10],
                'queueing_count': int(r[11] or 0),
                'has_mine_pending': bool(r[12]) if r[12] is not None else False,
                'position_for_current': int(r[13]) if r[13] is not None else None
            })

        return jsonify({
            'success': True,
            'data': data,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@model_management_bp.route('/api/models/<int:model_id>', methods=['PUT', 'DELETE'])
def update_model(model_id):
    if request.method == 'DELETE':
        try:
            vids = sf_db(f"SELECT 视频地址 FROM [模特信息] WHERE 模特ID = {model_id}", single=True) or ''
            if vids:
                for v in [x for x in vids.split(';') if x]:
                    p = os.path.join(BASE_VIDEO_DIR, v)
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass
            dui_db(f"DELETE FROM [模特排队] WHERE 模特ID = {model_id}")
            dui_db(f"DELETE FROM [模特信息] WHERE 模特ID = {model_id}")
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
    else:
        name = request.form.get('name', '')
        status = request.form.get('status', '')
        country = request.form.get('country', '')
        level = request.form.get('level', '')
        remark = request.form.get('remark', '')
        keep_videos = request.form.get('keep_videos', '')
        files = request.files.getlist('videos')
        video_field = None

        old_paths = sf_db(f"SELECT 视频地址 FROM [模特信息] WHERE 模特ID = {model_id}", single=True) or ''
        old_list = [x for x in (old_paths.split(';') if old_paths else []) if x]
        keep_list = [x for x in (keep_videos.split(';') if keep_videos else []) if x]

        if keep_list or keep_videos != "":
            to_remove = [v for v in old_list if v not in keep_list]
            for v in to_remove:
                p = os.path.join(BASE_VIDEO_DIR, v)
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
            base_list = keep_list
        else:
            base_list = old_list

        saved_paths = []
        if files:
            os.makedirs(BASE_VIDEO_DIR, exist_ok=True)
            for f in files:
                if f and f.filename:
                    filename = secure_filename(f.filename)
                    fname = f"{filename}"
                    full_path = os.path.join(BASE_VIDEO_DIR, fname)
                    i = 1
                    base, ext = os.path.splitext(fname)
                    while os.path.exists(full_path):
                        fname = f"{base}_{i}{ext}"
                        full_path = os.path.join(BASE_VIDEO_DIR, fname)
                        i += 1
                    f.save(full_path)
                    saved_paths.append(fname)

        if keep_list or saved_paths or (not old_list and not keep_list):
            video_field = ';'.join(base_list + saved_paths)
        updates = []
        if name or name == "":
            updates.append(f"模特姓名 = '{(name or '').replace("'", "''")}'")
        if status:
            updates.append(f"状态 = '{status.replace("'", "''")}'")
        if country:
            updates.append(f"国家 = '{country.replace("'", "''")}'")
        if level:
            updates.append(f"等级 = '{level.replace("'", "''")}'")
        if remark or remark == "":
            updates.append(f"备注 = '{(remark or '').replace("'", "''")}'")
        if video_field is not None:
            updates.append(f"视频地址 = '{video_field.replace("'", "''")}'")
        updates.append("更新时间 = GETDATE()")
        if not updates:
            return jsonify({'success': False, 'message': 'no changes'})
        sql = f"UPDATE [模特信息] SET {', '.join(updates)} WHERE 模特ID = {model_id}"
        dui_db(sql)
        return jsonify({'success': True})

@model_management_bp.route('/api/model_queue/<int:model_id>', methods=['GET'])
def get_model_queue(model_id):
    sql = f"SELECT 排队ID, 模特ID, 部门, 排队状态, 视频已完成, 备注, 创建时间, 创建人, 代排队 FROM [模特排队] WHERE 模特ID = {model_id} AND 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0 ORDER BY 创建时间 ASC, 排队ID ASC"
    rows = sf_db(sql) or []
    data = []
    position = 1
    for r in rows:
        data.append({
            'id': r[0],
            'model_id': r[1],
            'department': r[2] or '',
            'queue_status': r[3] or '',
            'video_done': bool(r[4]) if r[4] is not None else False,
            'remark': r[5] or '',
            'created_at': r[6],
            'creator': r[7] or '',
            'proxy_queue': r[8],
            'position': position
        })
        position += 1
    count_sql = f"SELECT COUNT(*) FROM [模特排队] WHERE 模特ID = {model_id} AND 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0"
    count_val = sf_db(count_sql, single=True) or 0
    # 计算当前用户在队列中的位置
    user = get_user_name()
    mine_row = sf_db(f"SELECT TOP 1 排队ID, 创建时间 FROM [模特排队] WHERE 模特ID = {model_id} AND 创建人 = '{user.replace("'", "''")}' AND 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0 ORDER BY 创建时间 ASC, 排队ID ASC")
    position_for_current = None
    if mine_row:
        mine_id = mine_row[0][0]
        mine_time = mine_row[0][1]
        pos_sql = f"SELECT COUNT(*) FROM [模特排队] WHERE 模特ID = {model_id} AND 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0 AND (创建时间 < '{mine_time}' OR (创建时间 = '{mine_time}' AND 排队ID < {mine_id}))"
        position_for_current = int(sf_db(pos_sql, single=True) or 0)
    has_mine_pending = (sf_db(f"SELECT COUNT(*) FROM [模特排队] WHERE 模特ID = {model_id} AND 创建人 = '{user.replace("'", "''")}' AND 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0", single=True) or 0) > 0
    return jsonify({'success': True, 'data': data, 'queueing_count': int(count_val), 'position_for_current': position_for_current, 'has_mine_pending': has_mine_pending})

@model_management_bp.route('/api/model_queue', methods=['POST'])
def create_model_queue():
    payload = request.get_json() or {}
    model_id = int(payload.get('model_id', 0))
    department = payload.get('department', '') or get_user_name()
    remark = payload.get('remark', '')
    proxy_queue = payload.get('proxy_queue', '')
    creator = get_user_name()
    # 限制：同一运营(以部门字段识别)对同一模特只有未完成的预约存在时，禁止再次预约
    exist_count = sf_db(f"SELECT COUNT(*) FROM [模特排队] WHERE 模特ID = {model_id} AND 部门 = '{department.replace("'", "''")}' AND 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0", single=True) or 0
    if exist_count > 0:
        return jsonify({'success': False, 'message': '您对该模特已存在未完成的预约，请完成后再预约'})
    sql = (
        "INSERT INTO [模特排队] (模特ID, 部门, 排队状态, 视频已完成, 备注, 创建时间, 创建人, 代排队) "
        f"VALUES ({model_id}, '{department.replace("'", "''")}', '排队中', 0, '{remark.replace("'", "''")}', GETDATE(), "
        f"'{creator.replace("'", "''")}', '{str(proxy_queue).replace("'", "''")}')"
    )
    dui_db(sql)
    try:
        uploader = sf_db(f"SELECT 上传人 FROM [模特信息] WHERE 模特ID = {model_id}", single=True) or ''
        model_name = sf_db(f"SELECT 模特姓名 FROM [模特信息] WHERE 模特ID = {model_id}", single=True) or ''
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ms = MessageService()
        ms.send_message(str(_resolve_feishu_id(uploader)), f"【排队通知】{department} 于 {ts} 为模特 {model_name} 排队")
    except Exception:
        pass
    return jsonify({'success': True})

@model_management_bp.route('/api/model_queue/proxy', methods=['POST'])
def create_proxy_queue():
    payload = request.get_json() or {}
    model_id = int(payload.get('model_id', 0))
    operator_name = (payload.get('operator_name', '') or '').strip()
    if not operator_name:
        return jsonify({'success': False, 'message': '请填写运营姓名'})
    # 以填写的名字作为部门字段，其他逻辑与自助排队一致
    department = operator_name
    creator = get_user_name()
    remark = payload.get('remark', '')
    # 限制：该运营名对该模特只能有一个未完成预约
    exist_count = sf_db(f"SELECT COUNT(*) FROM [模特排队] WHERE 模特ID = {model_id} AND 部门 = '{department.replace("'", "''")}' AND 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0", single=True) or 0
    if exist_count > 0:
        return jsonify({'success': False, 'message': '该运营已存在未完成的预约，完成后再预约'})
    sql = (
        "INSERT INTO [模特排队] (模特ID, 部门, 排队状态, 视频已完成, 备注, 创建时间, 创建人, 代排队) "
        f"VALUES ({model_id}, '{department.replace("'", "''")}', '排队中', 0, '{remark.replace("'", "''")}', GETDATE(), "
        f"'{creator.replace("'", "''")}', '')"
    )
    dui_db(sql)
    return jsonify({'success': True})

@model_management_bp.route('/api/model_queue/<int:model_id>/complete_mine', methods=['POST'])
def complete_my_queue(model_id):
    user = get_user_name()
    sql = f"UPDATE [模特排队] SET 视频已完成 = 1, 排队状态 = '已完成' WHERE 模特ID = {model_id} AND 创建人 = '{user.replace("'", "''")}' AND 排队状态 = '排队中'"
    dui_db(sql)
    return jsonify({'success': True})

@model_management_bp.route('/api/model_queue/<int:queue_id>/complete', methods=['POST'])
def complete_video(queue_id):
    sql = f"UPDATE [模特排队] SET 视频已完成 = 1, 排队状态 = '已完成' WHERE 排队ID = {queue_id}"
    dui_db(sql)
    model_id = sf_db(f"SELECT 模特ID FROM [模特排队] WHERE 排队ID = {queue_id}", single=True)
    cur_name = sf_db(f"SELECT 部门 FROM [模特排队] WHERE 排队ID = {queue_id}", single=True)
    model_name = ''
    uploader = ''
    if model_id:
        model_name = sf_db(f"SELECT 模特姓名 FROM [模特信息] WHERE 模特ID = {model_id}", single=True) or ''
        uploader = sf_db(f"SELECT 上传人 FROM [模特信息] WHERE 模特ID = {model_id}", single=True) or ''
    notified_current = False
    notified_next = False
    try:
        ms = MessageService()
        if cur_name:
            ms.send_message(str(_resolve_feishu_id(cur_name)), f"【视频完成】{model_name} 视频已完成")
            notified_current = True
        if uploader:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ms.send_message(
                str(_resolve_feishu_id(uploader)),
                f"【视频完成】{cur_name} 于 {ts} 完成模特 {model_name} 的视频"
            )
    except Exception:
        pass
    next_name = None
    if model_id:
        next_name = sf_db(
            f"SELECT TOP 1 部门 FROM [模特排队] WHERE 模特ID = {model_id} AND 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0 ORDER BY 创建时间 ASC, 排队ID ASC",
            single=True
        )
        try:
            if next_name:
                ms = MessageService()
                ms.send_message(
                    str(_resolve_feishu_id(next_name)),
                    f"【到号通知】{uploader}负责的模特{model_name} 已到号，请将想拍的产品发给技术部"
                )
                notified_next = True
        except Exception:
            pass
    return jsonify({'success': True, 'notified_current': notified_current, 'notified_next': notified_next})

@model_management_bp.route('/api/model_queue/<int:queue_id>/cancel', methods=['POST'])
def cancel_queue(queue_id):
    # 先获取排队信息用于通知
    row = sf_db(f"SELECT 模特ID, 部门 FROM [模特排队] WHERE 排队ID = {queue_id}")
    sql = f"UPDATE [模特排队] SET 排队状态 = '已取消' WHERE 排队ID = {queue_id}"
    dui_db(sql)
    try:
        if row:
            model_id = row[0][0]
            department = row[0][1] or ''
            uploader = sf_db(f"SELECT 上传人 FROM [模特信息] WHERE 模特ID = {model_id}", single=True) or ''
            model_name = sf_db(f"SELECT 模特姓名 FROM [模特信息] WHERE 模特ID = {model_id}", single=True) or ''
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ms = MessageService()
            ms.send_message(str(_resolve_feishu_id(uploader)), f"【取消排队】{department} 于 {ts} 取消模特 {model_name} 的排队")
    except Exception:
        pass
    return jsonify({'success': True})

@model_management_bp.route('/api/model_queue/<int:model_id>/cancel_mine', methods=['POST'])
def cancel_my_queue(model_id):
    user = get_user_name()
    # 获取当前用户的排队信息用于通知
    info = sf_db(f"SELECT TOP 1 排队ID, 部门 FROM [模特排队] WHERE 模特ID = {model_id} AND 创建人 = '{user.replace("'", "''")}' AND 排队状态 = '排队中' ORDER BY 创建时间 DESC, 排队ID DESC")
    sql = f"UPDATE [模特排队] SET 排队状态 = '已取消' WHERE 模特ID = {model_id} AND 创建人 = '{user.replace("'", "''")}' AND 排队状态 = '排队中'"
    dui_db(sql)
    try:
        uploader = sf_db(f"SELECT 上传人 FROM [模特信息] WHERE 模特ID = {model_id}", single=True) or ''
        model_name = sf_db(f"SELECT 模特姓名 FROM [模特信息] WHERE 模特ID = {model_id}", single=True) or ''
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        department = None
        if info:
            department = info[0][1] or user
        else:
            department = user
        ms = MessageService()
        ms.send_message(str(_resolve_feishu_id(uploader)), f"【取消排队】{department} 于 {ts} 取消模特 {model_name} 的排队")
    except Exception:
        pass
    return jsonify({'success': True})

@model_management_bp.route('/api/models/<int:model_id>/pause', methods=['POST'])
def pause_queue(model_id):
    user = get_user_name()
    paused = sf_db(f"SELECT COUNT(*) FROM [模特排队] WHERE 模特ID = {model_id} AND 创建人 = '{user.replace("'", "''")}' AND 排队状态 = '暂停' AND 视频已完成 = 0", single=True) or 0
    if paused > 0:
        sql = f"UPDATE [模特排队] SET 排队状态 = '排队中' WHERE 模特ID = {model_id} AND 创建人 = '{user.replace("'", "''")}' AND 排队状态 = '暂停' AND 视频已完成 = 0"
        new_status = '排队中'
    else:
        sql = f"UPDATE [模特排队] SET 排队状态 = '暂停' WHERE 模特ID = {model_id} AND 创建人 = '{user.replace("'", "''")}' AND 排队状态 = '排队中' AND 视频已完成 = 0"
        new_status = '暂停'
    dui_db(sql)
    try:
        if new_status == '暂停':
            dui_db(f"UPDATE [模特信息] SET 状态 = '暂停拍摄' WHERE 模特ID = {model_id}")
        else:
            dui_db(f"UPDATE [模特信息] SET 状态 = '合作中' WHERE 模特ID = {model_id} AND 状态 = '暂停拍摄'")
    except Exception:
        pass
    if new_status == '暂停':
        try:
            model_name = sf_db(f"SELECT 模特姓名 FROM [模特信息] WHERE 模特ID = {model_id}", single=True) or ''
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            recipients = sf_db(
                f"SELECT DISTINCT 部门 FROM [模特排队] WHERE 模特ID = {model_id} AND 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0"
            ) or []
            names = []
            for r in recipients:
                if isinstance(r, (list, tuple)) and len(r) > 0:
                    name = (r[0] or '').strip()
                elif isinstance(r, dict):
                    name = (r.get('部门') or r.get('department') or '').strip()
                else:
                    name = (str(r) or '').strip()
                if name:
                    names.append(name)
            if names:
                ms = MessageService()
                msg = f"【暂停通知】模特 {model_name} 已暂停排队（暂停人：{user}，时间：{ts}）"
                for name in sorted(set(names)):
                    try:
                        ms.send_message(str(_resolve_feishu_id(name)), msg)
                    except Exception:
                        continue
        except Exception:
            pass
    return jsonify({'success': True, 'new_status': new_status})

@model_management_bp.route('/api/models/<int:model_id>/proxy', methods=['POST'])
def set_proxy_queue(model_id):
    payload = request.get_json() or {}
    name = (payload.get('value', '') or '').strip()
    if name:
        value = f"{name} 技术代排"
    else:
        value = "技术代排"
    sql = f"UPDATE [模特排队] SET 代排队 = '{str(value).replace("'", "''")}' WHERE 模特ID = {model_id} AND 排队状态 IN ('排队中','暂停') AND 视频已完成 = 0"
    dui_db(sql)
    return jsonify({'success': True})
