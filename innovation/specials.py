"""创新专项页面和 API。"""

from __future__ import annotations

from datetime import datetime
import logging
import math
import os
import uuid

from flask import jsonify, render_template, request, session, url_for

from bjc import dui_db, sf_db
from innovation.special_support import (
    ensure_special_storage,
    sql_int,
    sql_text,
    user_in_receiver_department,
)
from innovation.config import DEPARTMENTS
from innovation.web_app import (
    _get_current_feishu_user_name,
    _innovation_has_permission,
    get_message_service,
    APP_CONFIG,
)


logger = logging.getLogger(__name__)


SPECIAL_MANAGE_PERMISSION = 'innovation_special_manage'
SPECIAL_STATUS_LABELS = {
    'caogao': '草稿',
    'yifabu': '进行中',
    'zanting': '已暂停',
    'yijieshu': '已结束',
}
IDEA_STATUS_LABELS = {
    'daipinggu': '待评估',
    'yicainei': '已采纳',
    'yijujue': '已驳回',
}


def _save_special_media():
    groups = [('images', {'.jpg', '.jpeg', '.png', '.gif', '.webp'}),
              ('videos', {'.mp4', '.webm', '.mov', '.m4v'})]
    pending = []
    for key, allowed in groups:
        for file in request.files.getlist(key):
            if not file.filename:
                continue
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in allowed:
                from werkzeug.exceptions import BadRequest
                raise BadRequest('不支持的附件格式')
            pending.append((key, file, ext))
    result = {'images': [], 'videos': []}
    os.makedirs(APP_CONFIG['upload_folder'], exist_ok=True)
    for key, file, ext in pending:
        name = 'special_' + uuid.uuid4().hex + ext
        file.save(os.path.join(APP_CONFIG['upload_folder'], name))
        result[key].append('uploads/' + name)
    return ';'.join(result['images']), ';'.join(result['videos'])


def _media_urls(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode('utf-8', errors='replace')
    return ['/innovation/uploads/' + os.path.basename(v.replace('\\', '/'))
            for v in str(value or '').split(';') if v.strip()]


def _current_user() -> dict[str, str]:
    raw_department = session.get('user_department')
    if isinstance(raw_department, (list, tuple, set)):
        department = ', '.join(str(item or '').strip() for item in raw_department if str(item or '').strip())
    else:
        department = str(raw_department or '').strip()
    return {
        'user_id': str(session.get('feishu_user_id') or '').strip(),
        'user_name': _get_current_feishu_user_name(),
        'department': department,
        'avatar': str(session.get('feishu_avatar') or '').strip(),
    }


def _is_manager() -> bool:
    return _innovation_has_permission(SPECIAL_MANAGE_PERMISSION)


def _format_datetime(value):
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return str(value)


def _special_from_row(row):
    media = sf_db(f"SELECT tupian_lujing, shipin_lujing FROM dbo.chuangxin_zhuanxiang WHERE zhuanxiang_id = {int(row[0])}") or []
    return {
        'images': _media_urls(media[0][0]) if media else [],
        'videos': _media_urls(media[0][1]) if media else [],
        'zhuanxiang_id': int(row[0]),
        'zhuanxiang_bianhao': str(row[1] or ''),
        'biaoti': str(row[2] or ''),
        'nanti_miaoshu': str(row[3] or ''),
        'fabu_user_id': str(row[4] or ''),
        'fabu_user_name': str(row[5] or ''),
        'fabu_bumen': str(row[6] or ''),
        'chengjie_bumen': str(row[7] or ''),
        'zhuangtai': str(row[8] or ''),
        'zhuangtai_label': SPECIAL_STATUS_LABELS.get(str(row[8] or ''), str(row[8] or '')),
        'jiangli_jifen': int(row[9] or 0),
        'jiangli_mingxi': str(row[10] or ''),
        'chuangjian_shijian': _format_datetime(row[11]),
        'gengxin_shijian': _format_datetime(row[12]),
        'idea_count': int(row[13] or 0) if len(row) > 13 else 0,
    }


def _idea_from_row(row):
    return {
        'images': _media_urls(row[14]) if len(row) > 14 else [],
        'videos': _media_urls(row[15]) if len(row) > 15 else [],
        'id': int(row[0]),
        'title': str(row[1] or ''),
        'content': str(row[2] or ''),
        'submitter': str(row[3] or ''),
        'submitter_user_id': str(row[4] or ''),
        'submitted_at': _format_datetime(row[5]),
        'status': str(row[6] or 'daipinggu'),
        'status_label': IDEA_STATUS_LABELS.get(str(row[6] or 'daipinggu'), str(row[6] or 'daipinggu')),
        'score': float(row[7]) if row[7] is not None else None,
        'comment': str(row[8] or ''),
        'adopter_user_id': str(row[9] or ''),
        'adopted_at': _format_datetime(row[10]),
        'awarded_points': int(row[11] or 0),
        'points_awarded': bool(row[12]),
        'submitter_avatar': str(row[13] or '') if len(row) > 13 else '',
    }


def _load_special(special_id: int):
    rows = sf_db(f"""
        SELECT TOP 1
            zhuanxiang_id, zhuanxiang_bianhao, biaoti, nanti_miaoshu,
            fabu_user_id, fabu_user_name, fabu_bumen, chengjie_bumen, zhuangtai,
            jiangli_jifen, jiangli_mingxi,
            chuangjian_shijian, gengxin_shijian,
            (SELECT COUNT(1) FROM dbo.chuangxin_tibao1 t WHERE t.zhuanxiang_id = z.zhuanxiang_id) AS idea_count
        FROM dbo.chuangxin_zhuanxiang z
        WHERE zhuanxiang_id = {int(special_id)}
    """) or []
    return _special_from_row(rows[0]) if rows else None


def _load_ideas(special_id: int):
    rows = sf_db(f"""
        SELECT
            编号, 标题, 内容, 发起人, tijiao_user_id, 发起时间,
            xiangfa_zhuangtai, zhuanxiang_pingfen, zhuanxiang_pingyu,
            caina_user_id, caina_shijian, zhuanxiang_fafang_jifen,
            zhuanxiang_fafang_biaoshi, tijiao_user_avatar, 图片详情, 视频详情
        FROM dbo.chuangxin_tibao1
        WHERE zhuanxiang_id = {int(special_id)}
        ORDER BY 发起时间 DESC, 编号 DESC
    """) or []
    return [_idea_from_row(row) for row in rows]


def _fill_current_user_avatar(ideas: list[dict], user: dict[str, str] | None = None) -> list[dict]:
    """为历史专项想法补上当前飞书会话中的头像，避免旧数据只有用户 ID。"""
    current_user = user or _current_user()
    avatar = str(current_user.get('avatar') or '').strip()
    user_id = str(current_user.get('user_id') or '').strip()
    if not avatar or not user_id:
        return ideas
    for idea in ideas:
        if not idea.get('submitter_avatar') and idea.get('submitter_user_id') == user_id:
            idea['submitter_avatar'] = avatar
    return ideas


def _can_operate_special(special: dict) -> bool:
    user = _current_user()
    return _is_manager() or (
        bool(user['user_id']) and user['user_id'] == special['fabu_user_id']
    ) or (
        not special['fabu_user_id'] and user['user_name'] == special['fabu_user_name']
    )


def _can_review_special(special: dict) -> bool:
    user = _current_user()
    return user_in_receiver_department(special.get('chengjie_bumen'), user['user_id'])


def _append_special_flow(idea_id: int, special_id: int, status: str, remark: str, user: dict):
    current_count = sf_db(
        f"SELECT COALESCE(MAX(流转次数), 0) FROM dbo.chuangxin_liuzhuan1 WHERE 项目编号 = {int(idea_id)}",
        single=True,
    ) or 0
    special = _load_special(special_id) or {}
    dui_db(f"""
        INSERT INTO dbo.chuangxin_liuzhuan1
            (项目编号, 发起人, 承接人, 流转次数, 流转时间, 状态, 流转备注,
             zhuanxiang_id, liuzhuan_leixing, caozuo_user_id)
        SELECT
            {int(idea_id)},
            ISNULL(发起人, {sql_text(user['user_name'])}),
            {sql_text(special.get('fabu_user_name') or user['user_name'])},
            {int(current_count) + 1},
            SYSDATETIME(),
            {sql_text(status)},
            {sql_text(remark)},
            {int(special_id)},
            'zhuanxiang',
            {sql_text(user['user_id'])}
        FROM dbo.chuangxin_tibao1
        WHERE 编号 = {int(idea_id)}
    """)


def _notify_user(recipient: str, message: str) -> bool:
    if not recipient:
        return False
    try:
        return bool(get_message_service().send_message(recipient, message))
    except Exception:
        return False


def specials_page():
    ensure_special_storage()
    user = _current_user()
    return render_template(
        'specials.html',
        feishu_user_name=user['user_name'],
        is_special_manager=_is_manager(),
        departments=DEPARTMENTS,
    )


def special_detail_page(special_id: int):
    ensure_special_storage()
    user = _current_user()
    special = _load_special(special_id)
    if not special:
        return render_template('special_detail.html', special=None, ideas=[], feishu_user_name=user['user_name']), 404
    if special['zhuangtai'] == 'caogao' and not _can_operate_special(special):
        return render_template('special_detail.html', special=None, ideas=[], feishu_user_name=user['user_name']), 403
    return render_template(
        'special_detail.html',
        special=special,
        ideas=_fill_current_user_avatar(_load_ideas(special_id), user),
        feishu_user_name=user['user_name'],
        can_operate=_can_review_special(special),
        can_manage=_can_operate_special(special),
        departments=DEPARTMENTS,
    )


def get_specials():
    ensure_special_storage()
    manager = _is_manager()
    user = _current_user()
    where_clause = '' if manager else "WHERE zhuangtai = 'yifabu'"
    rows = sf_db(f"""
        SELECT
            zhuanxiang_id, zhuanxiang_bianhao, biaoti, nanti_miaoshu,
            fabu_user_id, fabu_user_name, fabu_bumen, chengjie_bumen, zhuangtai,
            jiangli_jifen, jiangli_mingxi,
            chuangjian_shijian, gengxin_shijian,
            (SELECT COUNT(1) FROM dbo.chuangxin_tibao1 t WHERE t.zhuanxiang_id = z.zhuanxiang_id) AS idea_count
        FROM dbo.chuangxin_zhuanxiang z
        {where_clause}
        ORDER BY CASE WHEN zhuangtai = 'yifabu' THEN 0 ELSE 1 END,
                 zhuanxiang_id DESC
    """) or []
    data = []
    for row in rows:
        special = _special_from_row(row)
        special['ideas'] = _fill_current_user_avatar(_load_ideas(special['zhuanxiang_id']), user)
        data.append(special)
    return jsonify({'success': True, 'data': data})


def get_special_detail(special_id: int):
    ensure_special_storage()
    user = _current_user()
    special = _load_special(special_id)
    if not special:
        return jsonify({'success': False, 'message': '专项不存在'}), 404
    if special['zhuangtai'] == 'caogao' and not _can_operate_special(special):
        return jsonify({'success': False, 'message': '专项尚未发布'}), 403
    return jsonify({'success': True, 'data': {'special': special, 'ideas': _fill_current_user_avatar(_load_ideas(special_id), user)}})


def create_special():
    ensure_special_storage()
    if not _is_manager():
        return jsonify({'success': False, 'message': '没有专项管理权限'}), 403
    user = _current_user()
    if not user['user_id'] or not user['user_name']:
        return jsonify({'success': False, 'message': '请先完成飞书身份绑定'}), 401
    data = request.get_json(silent=True) or request.form.to_dict()
    title = str(data.get('biaoti') or '').strip()
    problem = str(data.get('nanti_miaoshu') or '').strip()
    receiver_department = str(data.get('chengjie_bumen') or '').strip()
    if not title or not problem or not receiver_department:
        return jsonify({'success': False, 'message': '专项标题、难题描述和承接部门不能为空'}), 400
    points = sql_int(data.get('jiangli_jifen'), 0)
    if points < 0:
        return jsonify({'success': False, 'message': '奖励积分不能为负数'}), 400
    image_paths, video_paths = _save_special_media()
    current_max = sf_db(
        "SELECT MAX(CASE WHEN zhuanxiang_bianhao NOT LIKE N'%[^0-9]%' "
        "THEN CONVERT(INT, zhuanxiang_bianhao) END) FROM dbo.chuangxin_zhuanxiang",
        single=True,
    )
    special_no = f"{sql_int(current_max, 0) + 1:03d}"
    dui_db(f"""
        INSERT INTO dbo.chuangxin_zhuanxiang
            (zhuanxiang_bianhao, biaoti, nanti_miaoshu,
             fabu_user_id, fabu_user_name, fabu_bumen, chengjie_bumen, zhuangtai,
             jiangli_jifen, jiangli_mingxi, tupian_lujing, shipin_lujing)
        VALUES (
            {sql_text(special_no)}, {sql_text(title)}, {sql_text(problem)},
            {sql_text(user['user_id'])}, {sql_text(user['user_name'])},
            {sql_text(user['department'])}, {sql_text(receiver_department)}, 'caogao',
            {points}, {sql_text(str(data.get('jiangli_mingxi') or '').strip())}, {sql_text(image_paths)}, {sql_text(video_paths)}
        )
    """)
    row = sf_db(
        f"SELECT TOP 1 zhuanxiang_id FROM dbo.chuangxin_zhuanxiang WHERE zhuanxiang_bianhao = {sql_text(special_no)}",
        single=True,
    )
    return jsonify({'success': True, 'data': {'zhuanxiang_id': int(row)}}), 201


def update_special(special_id: int):
    ensure_special_storage()
    special = _load_special(special_id)
    if not special:
        return jsonify({'success': False, 'message': '专项不存在'}), 404
    if not _can_operate_special(special):
        return jsonify({'success': False, 'message': '没有专项操作权限'}), 403
    data = request.get_json(silent=True) or request.form.to_dict()
    fields = {
        'biaoti': str(data.get('biaoti') or '').strip(),
        'nanti_miaoshu': str(data.get('nanti_miaoshu') or '').strip(),
        'chengjie_bumen': str(data.get('chengjie_bumen') or special.get('chengjie_bumen') or '').strip(),
        'jiangli_jifen': sql_int(data.get('jiangli_jifen'), special['jiangli_jifen']),
        'jiangli_mingxi': str(data.get('jiangli_mingxi', special.get('jiangli_mingxi')) or '').strip(),
    }
    if not fields['biaoti'] or not fields['nanti_miaoshu'] or not fields['chengjie_bumen']:
        return jsonify({'success': False, 'message': '专项标题、难题描述和承接部门不能为空'}), 400
    dui_db(f"""
        UPDATE dbo.chuangxin_zhuanxiang
        SET biaoti = {sql_text(fields['biaoti'])},
            nanti_miaoshu = {sql_text(fields['nanti_miaoshu'])},
            chengjie_bumen = {sql_text(fields['chengjie_bumen'])},
            jiangli_jifen = {max(fields['jiangli_jifen'], 0)},
            jiangli_mingxi = {sql_text(fields['jiangli_mingxi'])},
            gengxin_shijian = SYSDATETIME()
        WHERE zhuanxiang_id = {int(special_id)}
    """)
    return jsonify({'success': True})


def publish_special(special_id: int):
    ensure_special_storage()
    special = _load_special(special_id)
    if not special:
        return jsonify({'success': False, 'message': '专项不存在'}), 404
    if not _can_operate_special(special):
        return jsonify({'success': False, 'message': '没有专项发布权限'}), 403
    if not special['biaoti'] or not special['nanti_miaoshu'] or not special['chengjie_bumen']:
        return jsonify({'success': False, 'message': '专项标题、难题描述和承接部门不能为空'}), 400
    dui_db(f"""
        UPDATE dbo.chuangxin_zhuanxiang
        SET zhuangtai = 'yifabu', fabu_shijian = SYSDATETIME(), gengxin_shijian = SYSDATETIME()
        WHERE zhuanxiang_id = {int(special_id)} AND zhuangtai = 'caogao'
    """)
    return jsonify({'success': True})


def close_special(special_id: int):
    ensure_special_storage()
    special = _load_special(special_id)
    if not special:
        return jsonify({'success': False, 'message': '专项不存在'}), 404
    if not _can_operate_special(special):
        return jsonify({'success': False, 'message': '没有专项关闭权限'}), 403
    dui_db(f"""
        UPDATE dbo.chuangxin_zhuanxiang
        SET zhuangtai = 'yijieshu', gengxin_shijian = SYSDATETIME()
        WHERE zhuanxiang_id = {int(special_id)} AND zhuangtai = 'yifabu'
    """)
    return jsonify({'success': True})


def submit_special_idea(special_id: int):
    ensure_special_storage()
    special = _load_special(special_id)
    user = _current_user()
    if not special:
        return jsonify({'success': False, 'message': '专项不存在'}), 404
    if special['zhuangtai'] != 'yifabu':
        return jsonify({'success': False, 'message': '专项当前不可提交想法'}), 400
    if not special.get('chengjie_bumen'):
        return jsonify({'success': False, 'message': '专项尚未设置承接部门，请联系管理员'}), 400
    if not user['user_id'] or not user['user_name']:
        return jsonify({'success': False, 'message': '请先完成飞书身份绑定'}), 401
    data = request.get_json(silent=True) or request.form.to_dict()
    content = str(data.get('content') or '').strip()
    if not content:
        return jsonify({'success': False, 'message': '想法内容不能为空'}), 400
    image_paths, video_paths = _save_special_media()
    title = f"专项想法-{user['user_name']}-{datetime.now():%Y%m%d%H%M%S%f}"
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        dui_db(f"""
            INSERT INTO dbo.chuangxin_tibao1
                (标题, 内容, 发起人, 发起时间, 得分, 状态, 创新类别,
                 解决方案, zhuanxiang_id, tijiao_user_id, xiangfa_zhuangtai,
                 tijiao_user_avatar, zhuanxiang_fafang_biaoshi, 图片详情, 视频详情)
            VALUES (
                {sql_text(title)}, {sql_text(content)}, {sql_text(user['user_name'])},
                {sql_text(now)}, 0,
                '待评估', '专项想法', N'', {int(special_id)},
                {sql_text(user['user_id'])}, {sql_text(user['avatar'])}, 'daipinggu', 0, CONVERT(VARCHAR(MAX), {sql_text(image_paths)}), CONVERT(VARCHAR(MAX), {sql_text(video_paths)})
            )
        """)
        idea_id = sf_db(f"""
            SELECT TOP 1 编号 FROM dbo.chuangxin_tibao1
            WHERE zhuanxiang_id = {int(special_id)}
              AND tijiao_user_id = {sql_text(user['user_id'])}
              AND 标题 = {sql_text(title)}
            ORDER BY 编号 DESC
        """, single=True)
    except Exception:
        logger.exception('提交创新专项想法失败，special_id=%s, user_id=%s', special_id, user['user_id'])
        return jsonify({'success': False, 'message': '想法提交失败，请稍后重试或联系管理员'}), 500
    if not idea_id:
        return jsonify({'success': False, 'message': '想法提交失败，未能获取想法编号'}), 500
    idea_id = int(idea_id)
    _append_special_flow(idea_id, special_id, 'daipinggu', '提交专项想法', user)
    dui_db(f"""
        UPDATE dbo.chuangxin_zhuanxiang
        SET gengxin_shijian = SYSDATETIME()
        WHERE zhuanxiang_id = {int(special_id)}
    """)
    message = (
        '💡 你的创新专项收到了新的想法\n\n'
        f"专项标题：{special['biaoti']}\n"
        f"提交人：{user['user_name']}\n\n"
        f"请前往专项详情查看：{url_for('innovation.innovation_special_detail', special_id=special_id, _external=True)}"
    )
    recipient = special['fabu_user_id'] or special['fabu_user_name']
    sent = _notify_user(recipient, message)
    dui_db(f"""
        UPDATE dbo.chuangxin_tibao1
        SET zhuanxiang_tongzhi_zhuangtai = {sql_text('yifasong' if sent else 'shibai')},
            zhuanxiang_tongzhi_shijian = SYSDATETIME()
        WHERE 编号 = {idea_id}
    """)
    return jsonify({'success': True, 'data': {'idea_id': idea_id, 'notification_sent': sent}}), 201


def review_special_idea(special_id: int, idea_id: int):
    ensure_special_storage()
    special = _load_special(special_id)
    if not special or not _can_review_special(special):
        return jsonify({'success': False, 'message': '没有专项评价权限'}), 403
    if special['zhuangtai'] != 'yifabu':
        return jsonify({'success': False, 'message': '专项已结束，不能继续评价想法'}), 400
    data = request.get_json(silent=True) or request.form.to_dict()
    score = data.get('score')
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '评分必须是数字'}), 400
    if not math.isfinite(score_value) or score_value < 0 or score_value > 10:
        return jsonify({'success': False, 'message': '评分范围为0到10分'}), 400
    comment = str(data.get('comment') or '').strip()
    idea_exists = sf_db(
        f"SELECT COUNT(*) FROM dbo.chuangxin_tibao1 WHERE 编号 = {int(idea_id)} AND zhuanxiang_id = {int(special_id)}",
        single=True,
    ) or 0
    if not idea_exists:
        return jsonify({'success': False, 'message': '专项想法不存在'}), 404
    user = _current_user()
    dui_db(f"""
        UPDATE dbo.chuangxin_tibao1
        SET zhuanxiang_pingfen = {score_value},
            zhuanxiang_pingyu = {sql_text(comment)},
            xiangfa_zhuangtai = 'daipinggu'
        WHERE 编号 = {int(idea_id)} AND zhuanxiang_id = {int(special_id)}
    """)
    _append_special_flow(idea_id, special_id, 'daipinggu', comment or f'评分 {score_value}', user)
    return jsonify({'success': True})


def adopt_special_idea(special_id: int, idea_id: int):
    ensure_special_storage()
    special = _load_special(special_id)
    if not special or not _can_review_special(special):
        return jsonify({'success': False, 'message': '没有专项采纳权限'}), 403
    if special['zhuangtai'] != 'yifabu':
        return jsonify({'success': False, 'message': '专项已结束，不能继续采纳想法'}), 400
    idea_rows = sf_db(f"""
        SELECT TOP 1 发起人, tijiao_user_id, xiangfa_zhuangtai, zhuanxiang_fafang_biaoshi
        FROM dbo.chuangxin_tibao1
        WHERE 编号 = {int(idea_id)} AND zhuanxiang_id = {int(special_id)}
    """) or []
    if not idea_rows:
        return jsonify({'success': False, 'message': '专项想法不存在'}), 404
    if str(idea_rows[0][2] or '') == 'yicainei' or bool(idea_rows[0][3]):
        return jsonify({'success': False, 'message': '该想法已经采纳'}), 409
    user = _current_user()
    dui_db(f"""
        UPDATE dbo.chuangxin_tibao1
        SET xiangfa_zhuangtai = 'yicainei',
            caina_user_id = {sql_text(user['user_id'])},
            caina_shijian = SYSDATETIME(),
            zhuanxiang_fafang_jifen = {int(special['jiangli_jifen'])},
            zhuanxiang_fafang_biaoshi = 1
        WHERE 编号 = {int(idea_id)}
          AND zhuanxiang_id = {int(special_id)}
          AND ISNULL(zhuanxiang_fafang_biaoshi, 0) = 0
    """)
    adopted_rows = sf_db(f"""
        SELECT TOP 1 caina_user_id, zhuanxiang_fafang_biaoshi
        FROM dbo.chuangxin_tibao1
        WHERE 编号 = {int(idea_id)} AND zhuanxiang_id = {int(special_id)}
    """) or []
    if not adopted_rows or not bool(adopted_rows[0][1]) or str(adopted_rows[0][0] or '') != user['user_id']:
        return jsonify({'success': False, 'message': '该想法已经被其他操作处理'}), 409
    _append_special_flow(idea_id, special_id, 'yicainei', '专项想法已采纳', user)
    has_bonus_package = bool(str(special.get('jiangli_mingxi') or '').strip())
    if has_bonus_package:
        dui_db(f"""
            UPDATE dbo.chuangxin_zhuanxiang
            SET zhuangtai = 'yijieshu', gengxin_shijian = SYSDATETIME()
            WHERE zhuanxiang_id = {int(special_id)} AND zhuangtai = 'yifabu'
        """)
    recipient = str(idea_rows[0][1] or idea_rows[0][0] or '').strip()
    message = (
        '🎉 你的创新专项想法已被采纳\n\n'
        f"专项标题：{special['biaoti']}\n"
        f"奖励积分：{special['jiangli_jifen']}\n"
        f"奖励明细：{special['jiangli_mingxi'] or '创新积分'}"
    )
    sent = _notify_user(recipient, message)
    return jsonify({'success': True, 'data': {
        'awarded_points': special['jiangli_jifen'],
        'notification_sent': sent,
        'special_closed': has_bonus_package,
    }})


def reject_special_idea(special_id: int, idea_id: int):
    ensure_special_storage()
    special = _load_special(special_id)
    if not special or not _can_review_special(special):
        return jsonify({'success': False, 'message': '没有专项处理权限'}), 403
    if special['zhuangtai'] != 'yifabu':
        return jsonify({'success': False, 'message': '专项已结束，不能继续处理想法'}), 400
    data = request.get_json(silent=True) or request.form.to_dict()
    comment = str(data.get('comment') or '').strip()
    user = _current_user()
    dui_db(f"""
        UPDATE dbo.chuangxin_tibao1
        SET xiangfa_zhuangtai = 'yijujue', zhuanxiang_pingyu = {sql_text(comment)}
        WHERE 编号 = {int(idea_id)} AND zhuanxiang_id = {int(special_id)}
    """)
    _append_special_flow(idea_id, special_id, 'yijujue', comment or '专项想法未采纳', user)
    return jsonify({'success': True})

