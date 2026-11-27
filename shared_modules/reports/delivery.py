"""Feishu delivery for reports and report feedback."""


def _xiaotu_send_report_notification(
    receive_id,
    receive_id_type,
    title_text,
    person_type,
    pingjia_text,
    doc_url,
    source_text,
    image_key,
    image_paths_text,
    wendangid,
    comment_url,
    report_url,
    org_impact_text,
    _feishu_send_message_detail,
    _feishu_send_text,
    _xiaotu_build_report_notify_card,
    _xiaotu_extract_plain_preview_text,
    _xiaotu_remember_report_card_message,
):
    card = _xiaotu_build_report_notify_card(
        title_text,
        person_type,
        pingjia_text,
        doc_url=doc_url,
        source_text=source_text,
        image_key=image_key,
        image_paths_text=image_paths_text,
        wendangid=wendangid,
        comment_url=comment_url,
        report_url=report_url,
        org_impact_text=org_impact_text
    )
    ok, resp = _feishu_send_message_detail(receive_id, receive_id_type, "interactive", card)
    if ok:
        if str(receive_id_type or "").strip() == "open_id":
            message_id = str(((resp or {}).get("data") or {}).get("message_id") or "").strip()
            _xiaotu_remember_report_card_message(wendangid, receive_id, message_id)
        return True
    push_lines = [
        "小图问答已完成入库",
        f"文档标题：{title_text}",
        f"人员类型：{person_type}",
    ]
    if doc_url:
        push_lines.append(f"文档链接：{doc_url}")
    if report_url:
        push_lines.append(f"查看日报：{report_url}")
    source_preview = _xiaotu_extract_plain_preview_text(source_text, limit=600)
    if source_preview:
        push_lines.extend([
            "",
            f"原文内容：\n{source_preview}"
        ])
    push_lines.extend([
        "",
        f"评价结果：\n{str(pingjia_text or '').strip()[:2500]}"
    ])
    org_impact_preview = str(org_impact_text or "").strip()
    if org_impact_preview:
        push_lines.extend([
            "",
            f"对组织绩效影响：\n{org_impact_preview[:1000]}"
        ])
    return _feishu_send_text(receive_id, receive_id_type, "\n".join(push_lines))


def _xiaotu_notify_report_owner_feedback(
    wendangid,
    action_name,
    actor_name,
    comment_text,
    target_name,
    _feishu_send_message_detail,
    _feishu_send_text,
    _xiaotu_build_feedback_notice_markdown,
    _xiaotu_build_report_history_url,
    _xiaotu_build_report_notify_card,
    _xiaotu_get_report_card_context,
    _xiaotu_get_report_feedback,
    _xiaotu_get_report_owner_open_id,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_remember_report_card_message,
):
    wid = str(wendangid or "").strip()
    if not wid:
        return False, "缺少文档ID"
    ctx = _xiaotu_get_report_card_context(wid)
    owner_name = str((ctx or {}).get("owner_name") or "").strip()
    title_text = str((ctx or {}).get("title_text") or "未命名标题").strip() or "未命名标题"
    if not owner_name:
        return False, "未找到报告发起人"
    owner_open_id = _xiaotu_get_report_owner_open_id(wid) or _xiaotu_lookup_open_id_by_name(owner_name)
    if not owner_open_id:
        return False, "未找到发起人飞书ID"
    actor = str(actor_name or "").strip() or "匿名用户"
    if owner_name == actor:
        return True, "发起人本人操作，跳过同步通知"
    report_url = _xiaotu_build_report_history_url(wid)
    notice_markdown = _xiaotu_build_feedback_notice_markdown(
        action_name, actor, comment_text, target_name
    )
    header_title = "报告互动通知"
    header_template = "wathet"
    if action_name == "like_report":
        header_title = "你的报告收到新的点赞"
        header_template = "turquoise"
    elif action_name == "reply_report":
        header_title = "你的报告收到新的回复"
        header_template = "orange"
    else:
        header_title = "你的报告收到新的评论"
        header_template = "blue"
    feedback = _xiaotu_get_report_feedback(wid, owner_name=owner_name)
    card = _xiaotu_build_report_notify_card(
        title_text,
        str((ctx or {}).get("person_type") or "").strip(),
        str((ctx or {}).get("pingjia_text") or "").strip(),
        source_text=str((ctx or {}).get("source_text") or "").strip(),
        image_paths_text=str((ctx or {}).get("image_paths_text") or "").strip(),
        wendangid=wid,
        report_url=report_url,
        feedback_override=feedback,
        header_title=header_title,
        header_template=header_template,
        notice_markdown=notice_markdown
    )
    ok, resp = _feishu_send_message_detail(owner_open_id, "open_id", "interactive", card)
    if ok:
        message_id = str(((resp or {}).get("data") or {}).get("message_id") or "").strip()
        if message_id:
            _xiaotu_remember_report_card_message(wid, owner_open_id, message_id)
        return True, ""
    msg_lines = [
        header_title,
        f"文档标题：{title_text}",
        notice_markdown.replace("**", "")
    ]
    text_ok = _feishu_send_text(owner_open_id, "open_id", "\n".join([x for x in msg_lines if str(x).strip()]))
    return (True, "") if text_ok else (False, "飞书通知发送失败")


def _xiaotu_notify_feedback_reply_target(
    wendangid,
    actor_name,
    target_name,
    reply_text,
    _feishu_send_message_detail,
    _feishu_send_text,
    _xiaotu_build_feedback_notice_markdown,
    _xiaotu_build_report_history_url,
    _xiaotu_build_report_notify_card,
    _xiaotu_get_report_card_context,
    _xiaotu_get_report_feedback,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_remember_report_card_message,
):
    wid = str(wendangid or "").strip()
    target = str(target_name or "").strip()
    actor = str(actor_name or "").strip() or "匿名用户"
    if not wid or not target or target == actor:
        return True, "无需通知回复对象"
    ctx = _xiaotu_get_report_card_context(wid)
    title_text = str((ctx or {}).get("title_text") or "未命名标题").strip() or "未命名标题"
    target_open_id = _xiaotu_lookup_open_id_by_name(target)
    if not target_open_id:
        return False, "未找到回复对象飞书ID"
    report_url = _xiaotu_build_report_history_url(wid)
    notice_markdown = _xiaotu_build_feedback_notice_markdown(
        "reply_report", actor, reply_text, target
    )
    feedback = _xiaotu_get_report_feedback(wid, owner_name=str((ctx or {}).get("owner_name") or "").strip())
    card = _xiaotu_build_report_notify_card(
        title_text,
        str((ctx or {}).get("person_type") or "").strip(),
        str((ctx or {}).get("pingjia_text") or "").strip(),
        source_text=str((ctx or {}).get("source_text") or "").strip(),
        image_paths_text=str((ctx or {}).get("image_paths_text") or "").strip(),
        wendangid=wid,
        report_url=report_url,
        feedback_override=feedback,
        header_title="你收到一条新的评价回复",
        header_template="orange",
        notice_markdown=notice_markdown
    )
    ok, resp = _feishu_send_message_detail(target_open_id, "open_id", "interactive", card)
    if ok:
        message_id = str(((resp or {}).get("data") or {}).get("message_id") or "").strip()
        if message_id:
            _xiaotu_remember_report_card_message(wid, target_open_id, message_id)
        return True, ""
    msg = "\n".join([
        "你收到一条新的评价回复",
        f"文档标题：{title_text}",
        f"回复人：{actor}",
        f"回复给：{target}",
        f"回复内容：{str(reply_text or '').strip() or '（空）'}",
    ])
    text_ok = _feishu_send_text(target_open_id, "open_id", msg)
    return (True, "") if text_ok else (False, "回复对象通知发送失败")


def _xiaotu_notify_feedback_open_ids(
    wendangid,
    action_name,
    actor_name,
    comment_text,
    target_name,
    open_ids,
    skip_open_ids,
    _feishu_send_message_detail,
    _xiaotu_build_feedback_notice_markdown,
    _xiaotu_build_report_history_url,
    _xiaotu_build_report_notify_card,
    _xiaotu_get_report_card_context,
    _xiaotu_get_report_feedback,
    _xiaotu_remember_report_card_message,
):
    wid = str(wendangid or "").strip()
    if not wid:
        return []
    ctx = _xiaotu_get_report_card_context(wid)
    title_text = str((ctx or {}).get("title_text") or "未命名标题").strip() or "未命名标题"
    owner_name = str((ctx or {}).get("owner_name") or "").strip()
    report_url = _xiaotu_build_report_history_url(wid)
    feedback = _xiaotu_get_report_feedback(wid, owner_name=owner_name)
    actor = str(actor_name or "").strip() or "匿名用户"
    notice_markdown = _xiaotu_build_feedback_notice_markdown(
        action_name, actor, comment_text, target_name
    )
    header_title = "你收到一条新的评价互动"
    header_template = "wathet"
    if action_name == "like_report":
        header_title = "你收到一条新的评价点赞"
        header_template = "turquoise"
    elif action_name == "reply_report":
        header_title = "你收到一条新的评价回复"
        header_template = "orange"
    else:
        header_title = "你收到一条新的评价评论"
        header_template = "blue"
    card = _xiaotu_build_report_notify_card(
        title_text,
        str((ctx or {}).get("person_type") or "").strip(),
        str((ctx or {}).get("pingjia_text") or "").strip(),
        source_text=str((ctx or {}).get("source_text") or "").strip(),
        image_paths_text=str((ctx or {}).get("image_paths_text") or "").strip(),
        wendangid=wid,
        report_url=report_url,
        feedback_override=feedback,
        header_title=header_title,
        header_template=header_template,
        notice_markdown=notice_markdown
    )
    skip_ids = {
        str(x or "").strip()
        for x in (skip_open_ids or [])
        if str(x or "").strip()
    }
    results = []
    seen = set()
    for raw in (open_ids or []):
        oid = str(raw or "").strip()
        if not oid or oid in seen or oid in skip_ids:
            continue
        seen.add(oid)
        ok, resp = _feishu_send_message_detail(oid, "open_id", "interactive", card)
        message_id = str(((resp or {}).get("data") or {}).get("message_id") or "").strip() if ok else ""
        if message_id:
            _xiaotu_remember_report_card_message(wid, oid, message_id)
        results.append({
            "open_id": oid,
            "ok": bool(ok),
            "message_id": message_id,
            "error": "" if ok else "飞书通知发送失败"
        })
    return results
