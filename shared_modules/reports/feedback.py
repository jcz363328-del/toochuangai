"""Read and write daily report reactions, comments and replies."""


def _xiaotu_upsert_report_like(
    wendangid,
    user_name,
    *,
    _xiaotu_build_like_user_text,
    _xiaotu_parse_like_user_names,
    _xiaotu_sql_escape,
    dui_db,
    sf_db,
):
    wid = str(wendangid or "").strip()
    if not wid:
        return False, "缺少文档ID"
    esc_wid = _xiaotu_sql_escape(wid)
    actor = str(user_name or "").strip()
    esc_actor = _xiaotu_sql_escape(actor)
    existing_like_users = []
    try:
        existing_row = sf_db(f"SELECT TOP 1 DianZan, YongHu FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}'") or []
        if isinstance(existing_row, list) and existing_row and isinstance(existing_row[0], dict):
            existing_row = existing_row[0]
        if isinstance(existing_row, list) and existing_row and isinstance(existing_row[0], (list, tuple)):
            existing_row = existing_row[0]
        if isinstance(existing_row, dict):
            if str(existing_row.get("DianZan") or existing_row.get("dianzan") or "").strip().upper() == "Y":
                existing_like_users = _xiaotu_parse_like_user_names(existing_row.get("YongHu") or existing_row.get("yonghu") or "")
        elif isinstance(existing_row, (list, tuple)):
            if str(existing_row[0] if len(existing_row) > 0 else "").strip().upper() == "Y":
                existing_like_users = _xiaotu_parse_like_user_names(existing_row[1] if len(existing_row) > 1 else "")
    except Exception:
        existing_like_users = []
    merged_like_users = list(existing_like_users or [])
    if actor and actor not in merged_like_users:
        merged_like_users.append(actor)
    like_users_text = _xiaotu_build_like_user_text(merged_like_users)
    esc_like_users = _xiaotu_sql_escape(like_users_text)
    sql = f"""
        IF EXISTS (SELECT 1 FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}')
            UPDATE BaoGao_dianzan
            SET DianZan='Y', YongHu=N'{esc_like_users}'
            WHERE WenDangID='{esc_wid}'
        ELSE
            INSERT INTO BaoGao_dianzan (WenDangID, DianZan, PingJia, HuiFu, YongHu)
            VALUES ('{esc_wid}', 'Y', N'', N'', N'{esc_like_users}')
    """
    try:
        dui_db(sql)
        return True, ""
    except Exception as e:
        return False, str(e)


def _xiaotu_toggle_report_like(
    wendangid,
    user_name,
    *,
    _xiaotu_build_like_user_text,
    _xiaotu_parse_like_user_names,
    _xiaotu_sql_escape,
    dui_db,
    sf_db,
):
    wid = str(wendangid or "").strip()
    actor = str(user_name or "").strip()
    if not wid:
        return False, "缺少日报ID", False
    if not actor:
        return False, "未获取到当前用户", False
    esc_wid = _xiaotu_sql_escape(wid)
    existing_like_users = []
    try:
        existing_row = sf_db(f"SELECT TOP 1 DianZan, YongHu FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}'") or []
        if isinstance(existing_row, list) and existing_row and isinstance(existing_row[0], dict):
            existing_row = existing_row[0]
        if isinstance(existing_row, list) and existing_row and isinstance(existing_row[0], (list, tuple)):
            existing_row = existing_row[0]
        if isinstance(existing_row, dict):
            if str(existing_row.get("DianZan") or existing_row.get("dianzan") or "").strip().upper() == "Y":
                existing_like_users = _xiaotu_parse_like_user_names(existing_row.get("YongHu") or existing_row.get("yonghu") or "")
        elif isinstance(existing_row, (list, tuple)):
            if str(existing_row[0] if len(existing_row) > 0 else "").strip().upper() == "Y":
                existing_like_users = _xiaotu_parse_like_user_names(existing_row[1] if len(existing_row) > 1 else "")
    except Exception:
        existing_like_users = []
    liked_now = actor not in existing_like_users
    if liked_now:
        existing_like_users.append(actor)
    else:
        existing_like_users = [name for name in existing_like_users if name != actor]
    like_users_text = _xiaotu_build_like_user_text(existing_like_users)
    esc_like_users = _xiaotu_sql_escape(like_users_text)
    dianzan_value = "Y" if like_users_text else ""
    sql = f"""
        IF EXISTS (SELECT 1 FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}')
            UPDATE BaoGao_dianzan
            SET DianZan='{dianzan_value}', YongHu=N'{esc_like_users}'
            WHERE WenDangID='{esc_wid}'
        ELSE
            INSERT INTO BaoGao_dianzan (WenDangID, DianZan, PingJia, HuiFu, YongHu)
            VALUES ('{esc_wid}', '{dianzan_value}', N'', N'', N'{esc_like_users}')
    """
    try:
        dui_db(sql)
        return True, "", liked_now
    except Exception as e:
        return False, str(e), False


def _xiaotu_append_report_comment(
    wendangid,
    user_name,
    comment_text,
    *,
    _xiaotu_feedback_entry_line,
    _xiaotu_sql_escape,
    dui_db,
):
    wid = str(wendangid or "").strip()
    comment = str(comment_text or "").strip()
    if not wid:
        return False, "缺少文档ID"
    if not comment:
        return False, "评论不能为空"
    actor = str(user_name or "匿名用户").strip() or "匿名用户"
    entry = _xiaotu_feedback_entry_line("comment", actor, comment)
    esc_wid = _xiaotu_sql_escape(wid)
    esc_entry = _xiaotu_sql_escape(entry)
    sql = f"""
        IF EXISTS (SELECT 1 FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}')
            UPDATE BaoGao_dianzan
            SET PingJia = CASE
                WHEN ISNULL(PingJia, '') = '' THEN N'{esc_entry}'
                ELSE CONVERT(NVARCHAR(MAX), PingJia) + CHAR(10) + N'{esc_entry}'
            END
            WHERE WenDangID='{esc_wid}'
        ELSE
            INSERT INTO BaoGao_dianzan (WenDangID, DianZan, PingJia, HuiFu, YongHu)
            VALUES ('{esc_wid}', '', N'{esc_entry}', N'', N'')
    """
    try:
        dui_db(sql)
        return True, ""
    except Exception as e:
        return False, str(e)


def _xiaotu_append_report_reply(
    wendangid,
    user_name,
    reply_text,
    target_name,
    *,
    _xiaotu_feedback_entry_line,
    _xiaotu_sql_escape,
    dui_db,
):
    wid = str(wendangid or "").strip()
    reply = str(reply_text or "").strip()
    if not wid:
        return False, "缺少文档ID"
    if not reply:
        return False, "回复内容不能为空"
    actor = str(user_name or "匿名用户").strip() or "匿名用户"
    target = str(target_name or "").strip()
    entry = _xiaotu_feedback_entry_line("reply", actor, reply, target)
    esc_wid = _xiaotu_sql_escape(wid)
    esc_entry = _xiaotu_sql_escape(entry)
    sql = f"""
        IF EXISTS (SELECT 1 FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}')
            UPDATE BaoGao_dianzan
            SET HuiFu = CASE
                WHEN ISNULL(HuiFu, '') = '' THEN N'{esc_entry}'
                ELSE CONVERT(NVARCHAR(MAX), HuiFu) + CHAR(10) + N'{esc_entry}'
            END
            WHERE WenDangID='{esc_wid}'
        ELSE
            INSERT INTO BaoGao_dianzan (WenDangID, DianZan, PingJia, HuiFu, YongHu)
            VALUES ('{esc_wid}', '', N'', N'{esc_entry}', N'')
    """
    try:
        dui_db(sql)
        return True, ""
    except Exception as e:
        return False, str(e)


def _xiaotu_remove_report_feedback_entry(
    wendangid,
    user_name,
    entry_type,
    entry_index,
    *,
    _report_persistence,
    _xiaotu_feedback_entries_to_text,
    _xiaotu_parse_feedback_entries,
    _xiaotu_sql_escape,
    dui_db,
    sf_db,
):
    return _report_persistence._xiaotu_remove_report_feedback_entry(
        wendangid,
        user_name,
        entry_type,
        entry_index,
        _xiaotu_feedback_entries_to_text=_xiaotu_feedback_entries_to_text,
        _xiaotu_parse_feedback_entries=_xiaotu_parse_feedback_entries,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        dui_db=dui_db,
        sf_db=sf_db,
    )


def _xiaotu_get_report_feedback(
    wendangid,
    owner_name,
    *,
    _report_persistence,
    _xiaotu_enrich_feedback_data,
    _xiaotu_sql_escape,
    sf_db,
):
    return _report_persistence._xiaotu_get_report_feedback(
        wendangid,
        owner_name,
        _xiaotu_enrich_feedback_data=_xiaotu_enrich_feedback_data,
        _xiaotu_sql_escape=_xiaotu_sql_escape,
        sf_db=sf_db,
    )


def _xiaotu_extract_comment_text(
    form_value,
    *,
    _xiaotu_extract_comment_text,
):
    if isinstance(form_value, dict):
        direct = str(
            form_value.get("feedback_text")
            or form_value.get("comment_text")
            or form_value.get("comment")
            or form_value.get("reply_text")
            or form_value.get("reply")
            or form_value.get("pinglun")
            or form_value.get("PingJia")
            or form_value.get("huifu")
            or form_value.get("HuiFu")
            or ""
        ).strip()
        if direct:
            return direct
        for v in form_value.values():
            nested = _xiaotu_extract_comment_text(v)
            if nested:
                return nested
    elif isinstance(form_value, list):
        for item in form_value:
            nested = _xiaotu_extract_comment_text(item)
            if nested:
                return nested
    elif isinstance(form_value, str):
        txt = str(form_value or "").strip()
        if txt:
            return txt
    return ""


def _xiaotu_extract_reply_target_name(
    form_value,
    *,
    _xiaotu_extract_reply_target_name,
):
    if isinstance(form_value, dict):
        direct = form_value.get("reply_target") or form_value.get("target_name") or form_value.get("reply_to")
        if isinstance(direct, dict):
            val = str(direct.get("value") or direct.get("content") or direct.get("text") or "").strip()
            if val:
                return val
        if isinstance(direct, (list, tuple)):
            for item in direct:
                nested = _xiaotu_extract_reply_target_name(item)
                if nested:
                    return nested
        text_val = str(direct or "").strip()
        if text_val:
            return text_val
        for v in form_value.values():
            nested = _xiaotu_extract_reply_target_name(v)
            if nested:
                return nested
    elif isinstance(form_value, list):
        for item in form_value:
            nested = _xiaotu_extract_reply_target_name(item)
            if nested:
                return nested
    return ""


def _xiaotu_build_card_callback_response(
    card,
    toast_type,
    toast_content,
    *,
    jsonify,
):
    payload = {
        "toast": {
            "type": str(toast_type or "info"),
            "content": str(toast_content or "").strip() or "操作完成"
        }
    }
    return jsonify(payload), 200
