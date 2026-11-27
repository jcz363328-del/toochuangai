"""Resolve report card actors and synchronize feedback messages."""

from __future__ import annotations


def _xiaotu_resolve_card_actor_name(
    payload,
    *,
    _normalize_feishu_user_name,
    _xiaotu_is_invalid_feishu_name,
    _xiaotu_query_user_name_by_any_id,
):
    data = payload if isinstance(payload, dict) else {}
    operator_name = _normalize_feishu_user_name(
        data.get("operator_name") or data.get("user_name") or "",
        fallback=""
    )
    if operator_name and not _xiaotu_is_invalid_feishu_name(operator_name):
        return operator_name
    open_id = str(data.get("open_id") or "").strip()
    user_id = str(data.get("user_id") or "").strip()
    union_id = str(data.get("union_id") or "").strip()
    query_name = _xiaotu_query_user_name_by_any_id(open_id=open_id, user_id=user_id, union_id=union_id)
    if query_name:
        return query_name
    if operator_name and not _xiaotu_is_invalid_feishu_name(operator_name):
        return operator_name
    for candidate in (open_id, user_id):
        txt = str(candidate or "").strip()
        if txt:
            return txt
    return "匿名用户"


def _xiaotu_guess_report_default_notify_open_ids(
    owner_open_id,
    owner_name,
    *,
    _XIAOTU_REPORT_ESCALATION_USER,
    _xiaotu_get_department_leader_user_id,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_pick_primary_department,
):
    owner_oid = str(owner_open_id or "").strip()
    owner_nm = str(owner_name or "").strip()
    if not owner_oid:
        return []
    out = []
    seen = set()
    try:
        primary_dept_id, _primary_dept_name = _xiaotu_pick_primary_department(owner_oid)
        dept_leader_user_id = str(_xiaotu_get_department_leader_user_id(primary_dept_id) or "").strip()
        if dept_leader_user_id and dept_leader_user_id != owner_oid:
            seen.add(dept_leader_user_id)
            out.append(dept_leader_user_id)
        elif dept_leader_user_id and dept_leader_user_id == owner_oid:
            target_name = str(_XIAOTU_REPORT_ESCALATION_USER or "").strip()
            if target_name and target_name != owner_nm:
                escalation_open_id = str(_xiaotu_lookup_open_id_by_name(target_name) or "").strip()
                if escalation_open_id and escalation_open_id != owner_oid and escalation_open_id not in seen:
                    seen.add(escalation_open_id)
                    out.append(escalation_open_id)
    except Exception:
        return out
    return out


def _xiaotu_patch_related_report_cards(
    wendangid,
    open_ids,
    card_obj,
    skip_message_ids,
    *,
    _feishu_update_message_card,
    _xiaotu_get_report_card_message_ids,
):
    wid = str(wendangid or "").strip()
    if not wid or not isinstance(card_obj, dict) or not card_obj:
        return []
    skip_ids = {str(x or "").strip() for x in (skip_message_ids or []) if str(x or "").strip()}
    patched = []
    seen = set()
    for open_id in (open_ids or []):
        oid = str(open_id or "").strip()
        if not oid or oid in seen:
            continue
        seen.add(oid)
        message_ids = _xiaotu_get_report_card_message_ids(wid, oid)
        for message_id in message_ids:
            if not message_id or message_id in skip_ids:
                continue
            ok, err = _feishu_update_message_card(message_id, card_obj)
            patched.append({
                "open_id": oid,
                "message_id": message_id,
                "ok": bool(ok),
                "error": str(err or "").strip()
            })
    return patched


def _xiaotu_clean_card_text_block(
    raw_text,
    *,
    html_unescape,
    re,
):
    text = html_unescape(str(raw_text or "")).replace("\xa0", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    cleaned_lines = []
    last_blank = True
    for line in text.splitlines():
        one = str(line or "").rstrip()
        one = re.sub(r"^(?:[A-Za-z0-9_-]{12,}\s+)+", "", one).rstrip()
        if one and re.fullmatch(r"[A-Za-z0-9_-]{12,}", one):
            continue
        if not one.strip():
            if not last_blank:
                cleaned_lines.append("")
            last_blank = True
            continue
        cleaned_lines.append(one.strip())
        last_blank = False
    return "\n".join(cleaned_lines).strip()


def _xiaotu_build_feedback_notice_markdown(
    action_name,
    actor_name,
    comment_text,
    target_name,
    *,
    _xiaotu_clip_card_text,
):
    actor = str(actor_name or "").strip() or "匿名用户"
    content = _xiaotu_clip_card_text(comment_text or "", limit=220) or "（空）"
    target = str(target_name or "").strip()
    if str(action_name or "").strip() == "like_report":
        return "\n".join([
            "**你的报告收到新的点赞**",
            f"操作人：{actor}"
        ]).strip()
    if str(action_name or "").strip() == "reply_report":
        lines = [
            "**你的报告收到新的回复**",
            f"回复人：{actor}",
        ]
        if target:
            lines.append(f"回复对象：{target}")
        lines.append(f"回复内容：{content}")
        return "\n".join(lines).strip()
    return "\n".join([
        "**你的报告收到新的评论**",
        f"评论人：{actor}",
        f"评论内容：{content}"
    ]).strip()
