"""Load and authorize the daily report comment view."""

from __future__ import annotations


def _xiaotu_get_report_row(
    wendangid,
    *,
    _xiaotu_sql_escape,
    sf_db,
):
    wid = str(wendangid or "").strip()
    if not wid:
        return {}
    esc_wid = _xiaotu_sql_escape(wid)
    sql = f"""
        SELECT TOP 1
            WenDangID,
            BiaoTi,
            ZhengWen,
            TuPianLujin,
            XingMing,
            RiQi,
            PingJia,
            TuPianNeiRong,
            LeiXing,
            RenYuanLeiXing,
            JieShouRen
        FROM baogao
        WHERE WenDangID = '{esc_wid}'
        ORDER BY RiQi DESC
    """
    rows = sf_db(sql) or []
    row = rows[0] if isinstance(rows, list) and rows else rows
    if isinstance(row, dict):
        return {
            "wendangid": str(row.get("WenDangID") or wid).strip(),
            "biaoti": str(row.get("BiaoTi") or "").strip(),
            "zhengwen": str(row.get("ZhengWen") or "").strip(),
            "tupianlujin": str(row.get("TuPianLujin") or "").strip(),
            "xingming": str(row.get("XingMing") or "").strip(),
            "riqi": str(row.get("RiQi") or "").strip(),
            "pingjia": str(row.get("PingJia") or "").strip(),
            "tupianneirong": str(row.get("TuPianNeiRong") or "").strip(),
            "leixing": str(row.get("LeiXing") or "").strip(),
            "renyuanleixing": str(row.get("RenYuanLeiXing") or "").strip(),
            "jieshouren": str(row.get("JieShouRen") or "").strip(),
        }
    if isinstance(row, (list, tuple)):
        values = list(row)
        return {
            "wendangid": str(values[0] if len(values) > 0 else wid).strip(),
            "biaoti": str(values[1] if len(values) > 1 else "").strip(),
            "zhengwen": str(values[2] if len(values) > 2 else "").strip(),
            "tupianlujin": str(values[3] if len(values) > 3 else "").strip(),
            "xingming": str(values[4] if len(values) > 4 else "").strip(),
            "riqi": str(values[5] if len(values) > 5 else "").strip(),
            "pingjia": str(values[6] if len(values) > 6 else "").strip(),
            "tupianneirong": str(values[7] if len(values) > 7 else "").strip(),
            "leixing": str(values[8] if len(values) > 8 else "").strip(),
            "renyuanleixing": str(values[9] if len(values) > 9 else "").strip(),
            "jieshouren": str(values[10] if len(values) > 10 else "").strip(),
        }
    return {}


def xiaotu_report_comment_page(
    *,
    _xiaotu_append_report_comment,
    _xiaotu_append_report_reply,
    _xiaotu_get_report_feedback,
    _xiaotu_report_history_is_visible_to_user,
    _xiaotu_sql_escape,
    redirect,
    render_template,
    request,
    session,
    sf_db,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth', next=request.full_path))
    wendangid = str(request.values.get('wendangid') or '').strip()
    if not wendangid:
        return "缺少文档ID", 400
    actor_name = str(session.get('feishu_user_name') or '').strip()
    if not actor_name:
        return "未获取到当前用户名", 403
    if not _xiaotu_report_history_is_visible_to_user(wendangid, actor_name):
        return "无权查看或评论该日报", 403
    esc_wid = _xiaotu_sql_escape(wendangid)
    row = sf_db(f"SELECT TOP 1 WenDangID, BiaoTi, XingMing, RiQi FROM baogao WHERE WenDangID='{esc_wid}'") or []
    if isinstance(row, list) and row:
        row = row[0]
    report = {
        'wendangid': wendangid,
        'biaoti': '',
        'xingming': '',
        'riqi': ''
    }
    if isinstance(row, dict):
        report.update({
            'wendangid': str(row.get('WenDangID') or wendangid).strip(),
            'biaoti': str(row.get('BiaoTi') or '').strip(),
            'xingming': str(row.get('XingMing') or '').strip(),
            'riqi': str(row.get('RiQi') or '').strip(),
        })
    elif isinstance(row, (list, tuple)):
        report.update({
            'wendangid': str(row[0] if len(row) > 0 else wendangid).strip(),
            'biaoti': str(row[1] if len(row) > 1 else '').strip(),
            'xingming': str(row[2] if len(row) > 2 else '').strip(),
            'riqi': str(row[3] if len(row) > 3 else '').strip(),
        })
    error = ""
    success = bool(str(request.args.get('ok') or '').strip())
    if request.method == 'POST':
        action_name = str(request.form.get('action') or 'comment').strip().lower()
        if action_name == 'reply':
            reply_text = str(request.form.get('reply') or '').strip()
            reply_target = str(request.form.get('reply_target') or '').strip()
            ok, err = _xiaotu_append_report_reply(
                report.get('wendangid'),
                actor_name,
                reply_text,
                reply_target
            )
        else:
            comment_text = str(request.form.get('comment') or '').strip()
            ok, err = _xiaotu_append_report_comment(
                report.get('wendangid'),
                actor_name,
                comment_text
            )
        if ok:
            return redirect(url_for('xiaotu_report_comment_page', wendangid=report.get('wendangid'), ok=action_name))
        error = err or ('回复保存失败' if action_name == 'reply' else '评论保存失败')
        success = False
    success_text = ''
    if success:
        ok_type = str(request.args.get('ok') or '').strip().lower()
        success_text = '回复已提交成功。' if ok_type == 'reply' else '评论已提交成功。'
    return render_template(
        '日报与报告/xiaotu_report_comment.html',
        report=report,
        feedback=_xiaotu_get_report_feedback(report.get('wendangid'), owner_name=report.get('xingming')),
        error=error,
        success=success,
        success_text=success_text
    )
