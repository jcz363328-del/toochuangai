"""Resolve the people, documents and source material used by the report editor."""

from __future__ import annotations


def _xiaotu_build_name_scope_clause(
    column_name,
    names,
    *,
    _xiaotu_build_name_match_clause,
    _xiaotu_sql_escape,
    re,
):
    base_clause = _xiaotu_build_name_match_clause(column_name, names)
    loose_clauses = []
    seen = set()
    for raw_name in (names or []):
        name = str(raw_name or "").strip()
        compact_name = re.sub(r"\s+", "", name)
        for one in (name, compact_name):
            if not one or len(one) < 2 or one in seen:
                continue
            seen.add(one)
            esc_one = _xiaotu_sql_escape(one)
            loose_clauses.append(f"{column_name} LIKE N'%%{esc_one}%%'")
            loose_clauses.append(
                f"REPLACE(REPLACE({column_name}, N' ', N''), CHAR(9), N'') LIKE N'%%{esc_one}%%'"
            )
    clauses = [base_clause] if base_clause else []
    clauses.extend(loose_clauses)
    if not clauses:
        return ""
    return "(" + " OR ".join(clauses) + ")"


def _xiaotu_get_user_departments(
    user_id,
    *,
    permission_manager,
):
    uid = (user_id or "").strip()
    if not uid:
        return []
    try:
        rows = permission_manager.get_user_departments(uid) or []
    except Exception:
        rows = []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip().lower() in {"invalid", "unmapped"}:
            continue
        name = str(row.get("name") or "").strip()
        if name:
            out.append(name)
    return out


def _xiaotu_need_reauth(err_text):
    t = str(err_text or "").strip().lower()
    if not t:
        return False
    keys = [
        "飞书登录已过期",
        "authentication token expired",
        "token expired",
        "invalid access token",
        "access token expired",
        "登录状态缺少云文档访问凭证",
        "当前用户授权接口为历史版本",
        "end-user-consent",
        "please request user re-authorization",
        "unauthorized. you do not have permission",
        "应用未获取所需的用户授权"
    ]
    return any(k in t for k in keys)


def _xiaotu_find_last_daily_date_start(
    text,
    *,
    _xiaotu_find_daily_date_matches,
    _xiaotu_is_daily_date_heading,
):
    raw = str(text or "")
    if not raw:
        return -1, ""
    matches = _xiaotu_find_daily_date_matches(raw)
    if matches:
        last = matches[-1]
        return int(last.get("start") or -1), str(last.get("text") or "").strip()
    offset = 0
    last_pos = -1
    last_line = ""
    for one in raw.splitlines(True):
        plain = one.rstrip("\r\n")
        if _xiaotu_is_daily_date_heading(plain):
            last_pos = offset
            last_line = plain.strip()
        offset += len(one)
    return last_pos, last_line


def _xiaotu_build_block_debug_sample(
    block_obj,
    *,
    _xiaotu_extract_block_plain_text,
    _xiaotu_extract_image_tokens_from_block,
    _xiaotu_is_image_like_block,
):
    if not isinstance(block_obj, dict):
        return {}
    keys = [str(k) for k in list(block_obj.keys())[:10]]
    text_preview = str(_xiaotu_extract_block_plain_text(block_obj) or "").strip()
    if len(text_preview) > 80:
        text_preview = text_preview[:80] + "..."
    tokens = _xiaotu_extract_image_tokens_from_block(block_obj)
    return {
        "block_id": str(block_obj.get("block_id") or block_obj.get("id") or "").strip(),
        "parent_id": str(block_obj.get("parent_id") or block_obj.get("parentId") or "").strip(),
        "block_type": str(block_obj.get("block_type") or block_obj.get("type") or "").strip(),
        "image_like": _xiaotu_is_image_like_block(block_obj),
        "token_count": len(tokens or []),
        "text_preview": text_preview,
        "keys": keys
    }


def _xiaotu_pick_primary_department(
    user_id,
    *,
    permission_manager,
    session,
):
    uid = str(user_id or "").strip()
    if not uid:
        return "", ""
    try:
        rows = permission_manager.get_user_departments(uid) or []
    except Exception:
        rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip().lower() in {"invalid", "unmapped"}:
            continue
        dept_id = str(row.get("department_id") or "").strip()
        dept_name = str(row.get("name") or "").strip()
        if dept_id or dept_name:
            return dept_id, dept_name
    return "", str(session.get('user_department') or '').strip()


def _xiaotu_expand_department_tree_current_app(
    department_id,
    *,
    _xiaotu_list_department_children_current_app,
):
    root_id = str(department_id or "").strip()
    if not root_id:
        return []
    out = []
    seen = set()
    queue = [root_id]
    while queue:
        current = str(queue.pop(0) or "").strip()
        if not current or current in seen:
            continue
        seen.add(current)
        out.append(current)
        for child_id in _xiaotu_list_department_children_current_app(current):
            if child_id and child_id not in seen:
                queue.append(child_id)
    return out


def _xiaotu_split_cache_multi_value(
    raw_text,
    *,
    re,
    relocate_storage_path,
):
    text = str(raw_text or "").strip()
    if not text:
        return []
    parts = re.split(r"[\|\n\r,，;；]+", text)
    out = []
    seen = set()
    for raw in parts:
        one = relocate_storage_path(str(raw or "").strip())
        if not one or one in seen:
            continue
        seen.add(one)
        out.append(one)
    return out


def _xiaotu_get_message_text_for_daily_ref(
    message_row,
    *,
    _feishu_extract_text_from_content,
):
    msg = message_row if isinstance(message_row, dict) else {}
    body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
    content = body.get("content")
    if content is None:
        content = msg.get("content")
    text = _feishu_extract_text_from_content(content)
    txt = str(text or "").strip()
    if txt:
        return txt
    msg_type = str(msg.get("msg_type") or "").strip().lower()
    if msg_type in {"image"}:
        return "[图片]"
    if msg_type in {"file"}:
        return "[文件]"
    if msg_type in {"audio"}:
        return "[语音]"
    if msg_type in {"video"}:
        return "[视频]"
    if msg_type in {"sticker"}:
        return "[表情]"
    return ""


def _xiaotu_render_period_source_text(rows):
    chunks = []
    for idx, one in enumerate(rows, start=1):
        riqi = str((one or {}).get("riqi") or "").strip()
        title = str((one or {}).get("biaoti") or "").strip()
        zhengwen = str((one or {}).get("zhengwen") or "").strip()
        tupian = str((one or {}).get("tupianneirong") or "").strip()
        if not zhengwen and not tupian:
            continue
        chunks.append(
            f"【记录{idx}】\n"
            f"时间：{riqi or '未知'}\n"
            f"标题：{title or '未命名'}\n"
            f"正文：\n{zhengwen or '（空）'}\n\n"
            f"图片内容：\n{tupian or '（空）'}"
        )
    return "\n\n".join(chunks).strip()


def _xiaotu_render_knowledge_source_text(rows):
    chunks = []
    for idx, one in enumerate(rows, start=1):
        riqi = str((one or {}).get("riqi") or "").strip()
        title = str((one or {}).get("biaoti") or "").strip()
        zhengwen = str((one or {}).get("zhengwen") or "").strip()
        tupian = str((one or {}).get("tupianneirong") or "").strip()
        score = int((one or {}).get("score") or 0)
        chunks.append(
            f"【命中记录{idx}】\n"
            f"时间：{riqi or '未知'}\n"
            f"标题：{title or '未命名'}\n"
            f"相关度：{score}\n"
            f"正文：\n{zhengwen or '（空）'}\n\n"
            f"图片内容：\n{tupian or '（空）'}"
        )
    return "\n\n".join(chunks).strip()


def dashboard_xiaotu_report_center(
    *,
    _get_feishu_user_access_token,
    _is_mobile_request,
    redirect,
    render_template,
    request,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center')
        return redirect(url_for('feishu_auth'))
    user_access_token = _get_feishu_user_access_token()
    if not user_access_token:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center')
        return redirect(url_for('feishu_auth'))
    user_name = session.get('feishu_user_name', '用户')
    if _is_mobile_request() and str(request.args.get('desktop') or '').strip() != '1':
        return redirect(url_for('dashboard_xiaotu_report_center_mobile'))
    return render_template(
        '日报与报告/xiaotu_report_center.html',
        user_name=user_name,
        edit_wendangid=str(request.args.get('edit_wendangid') or '').strip(),
    )


def dashboard_xiaotu_report_center_mobile(
    *,
    _get_feishu_user_access_token,
    redirect,
    render_template,
    request,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center_mobile')
        return redirect(url_for('feishu_auth'))
    user_access_token = _get_feishu_user_access_token()
    if not user_access_token:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center_mobile')
        return redirect(url_for('feishu_auth'))
    user_name = session.get('feishu_user_name', '用户')
    return render_template(
        '日报与报告/xiaotu_report_center_mobile.html',
        user_name=user_name,
        edit_wendangid=str(request.args.get('edit_wendangid') or '').strip(),
    )
