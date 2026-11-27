def _xiaotu_build_missing_report_reminder_card(
    user_name,
    notify_time,
    _xiaotu_build_report_center_url,
    _xiaotu_normalize_notify_time,
    datetime,
):
    name = str(user_name or "").strip() or "同事"
    time_text = _xiaotu_normalize_notify_time(notify_time)
    now_text = datetime.now().strftime('%Y-%m-%d')
    report_center_url = _xiaotu_build_report_center_url()
    elements = [
        {
            "tag": "markdown",
            "content": f"**{name}，你今天的报告还没有提交。**"
        },
        {
            "tag": "markdown",
            "content": f"**提醒时间：** {time_text or '未设置'}\n**日期：** {now_text}"
        },
        {
            "tag": "markdown",
            "content": "请点击此提醒，直接进入报告智能体填写今日报告。"
        }
    ]
    if report_center_url:
        elements.append({
            "tag": "markdown",
            "content": f"[打开报告中心]({report_center_url})"
        })
    if report_center_url:
        elements.extend([
            {"tag": "hr"},
            {
                "tag": "column_set",
                "columns": [
                    {
                        "tag": "column",
                        "width": "auto",
                        "elements": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "立即填写报告"
                                },
                                "type": "primary",
                                "size": "small",
                                "behaviors": [
                                    {
                                        "type": "open_url",
                                        "default_url": report_center_url
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "horizontal_spacing": "8px"
            }
        ])
    card = {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "width_mode": "fill"
        },
        "header": {
            "template": "orange",
            "title": {
                "tag": "plain_text",
                "content": "报告未提交提醒"
            }
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 12px 12px",
            "elements": elements
        }
    }
    return card



def _xiaotu_build_card_source_elements(
    source_text,
    image_paths_text,
    fallback_image_key,
    max_blocks,
    full_content_url,
    _XiaoTuCardSourceParser,
    _feishu_upload_image_by_path,
    _xiaotu_clean_card_text_block,
    _xiaotu_clip_card_text,
    _xiaotu_extract_plain_preview_text,
    _xiaotu_parse_image_path_list,
    re,
):
    raw_text = str(source_text or "").strip()
    image_paths = _xiaotu_parse_image_path_list(image_paths_text)
    elements = [{
        "tag": "markdown",
        "content": "**原文内容**"
    }]
    if not raw_text and fallback_image_key:
        elements.append({
            "tag": "img",
            "img_key": str(fallback_image_key).strip(),
            "alt": {"tag": "plain_text", "content": "报告图片"}
        })
        return elements
    segments = []
    if re.search(r"<[^>]+>", raw_text):
        parser = _XiaoTuCardSourceParser(image_paths)
        try:
            parser.feed(raw_text)
            parser.close()
            segments = list(parser.segments or [])
        except Exception:
            segments = []
    if not segments:
        plain = _xiaotu_clean_card_text_block(raw_text)
        if plain:
            segments.append({"type": "text", "content": plain})
        for path in image_paths:
            segments.append({"type": "image", "path": path})
    upload_cache = {}
    used_blocks = 0
    long_content = False
    preview_limit = 1000
    max_blocks_safe = max(1, int(max_blocks))
    for seg in segments:
        if used_blocks >= max_blocks_safe:
            long_content = True
            break
        if str(seg.get("type") or "") == "text":
            full_content = _xiaotu_clean_card_text_block(seg.get("content") or "")
            if len(full_content) > preview_limit:
                long_content = True
            content = _xiaotu_clip_card_text(full_content, limit=preview_limit)
            if not content:
                continue
            elements.append({
                "tag": "markdown",
                "content": content
            })
            used_blocks += 1
            continue
        if str(seg.get("type") or "") == "image":
            img_path = str(seg.get("path") or "").strip()
            if not img_path:
                continue
            if img_path not in upload_cache:
                upload_cache[img_path] = _feishu_upload_image_by_path(img_path)
            img_key = str(upload_cache.get(img_path) or "").strip()
            if not img_key:
                continue
            elements.append({
                "tag": "img",
                "img_key": img_key,
                "alt": {"tag": "plain_text", "content": "报告图片"}
            })
            used_blocks += 1
    if len(elements) == 1:
        fallback_text = _xiaotu_extract_plain_preview_text(raw_text, limit=520) or "（无原文内容）"
        if raw_text and len(_xiaotu_clean_card_text_block(raw_text)) > 520:
            long_content = True
        elements.append({
            "tag": "markdown",
            "content": fallback_text
        })
        if fallback_image_key:
            elements.append({
                "tag": "img",
                "img_key": str(fallback_image_key).strip(),
                "alt": {"tag": "plain_text", "content": "报告图片"}
            })
    if long_content:
        full_url = str(full_content_url or "").strip()
        notice_text = "内容较长，卡片已折叠展示，请点击下方「查看日报」查看完整内容。"
        if full_url:
            notice_text = f"内容较长，卡片已折叠展示。[查看完整日报]({full_url})"
        elements.append({
            "tag": "markdown",
            "content": notice_text
        })
    return elements



def _xiaotu_card_feedback_text(
    feedback,
    expanded,
    preview_count,
    _xiaotu_clip_card_text,
    _xiaotu_enrich_feedback_data,
):
    fb = _xiaotu_enrich_feedback_data(feedback or {})
    comments = list(fb.get("comment_items") or [])
    replies = list(fb.get("reply_items") or [])
    preview = max(1, int(preview_count or 3))
    shown_comments = comments if expanded else comments[-preview:]
    shown_replies = replies if expanded else replies[-preview:]
    lines = []
    if shown_comments:
        lines.append("**评论记录**")
        for item in shown_comments:
            ts = str(item.get("ts") or "").strip()
            actor = str(item.get("actor") or "匿名用户").strip() or "匿名用户"
            content = _xiaotu_clip_card_text(item.get("content") or "", limit=120)
            prefix = f"`{ts}` " if ts else ""
            lines.append(f"- {prefix}{actor}：{content}")
    if shown_replies:
        if lines:
            lines.append("")
        lines.append("**回复记录**")
        for item in shown_replies:
            ts = str(item.get("ts") or "").strip()
            actor = str(item.get("actor") or "匿名用户").strip() or "匿名用户"
            target = str(item.get("target") or "").strip()
            content = _xiaotu_clip_card_text(item.get("content") or "", limit=120)
            prefix = f"`{ts}` " if ts else ""
            reply_to = f" 回复 {target}" if target else " 回复"
            lines.append(f"- {prefix}{actor}{reply_to}：{content}")
    return "\n".join([x for x in lines if str(x).strip()]).strip()



def _xiaotu_build_report_notify_card(
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
    feedback_override,
    header_title,
    header_template,
    notice_markdown,
    feedback_expanded,
    org_impact_text,
    _xiaotu_build_card_source_elements,
    _xiaotu_build_reply_target_options,
    _xiaotu_build_report_history_url,
    _xiaotu_card_feedback_text,
    _xiaotu_clip_card_text,
    _xiaotu_enrich_feedback_data,
    _xiaotu_get_report_card_context,
    _xiaotu_get_report_feedback,
    _xiaotu_split_org_perf_from_pingjia,
    re,
):
    title_val = str(title_text or "未命名标题").strip() or "未命名标题"
    person_val = str(person_type or "未设置").strip() or "未设置"
    summary_text, parsed_org_impact_text = _xiaotu_split_org_perf_from_pingjia(pingjia_text)
    summary_val = _xiaotu_clip_card_text(summary_text, limit=900) or "暂无评价结果"
    org_impact_text = str(org_impact_text or "").strip() or parsed_org_impact_text
    org_impact_text = re.sub(r"^\s*组织绩效贡献\s*[:：]\s*", "", org_impact_text).strip()
    org_impact_text = re.sub(r"^\s*对组织绩效影响\s*[:：]\s*", "", org_impact_text).strip()
    org_impact_val = _xiaotu_clip_card_text(org_impact_text, limit=500)
    ctx = _xiaotu_get_report_card_context(wendangid) if str(wendangid or "").strip() else {}
    owner_name = str((ctx or {}).get("owner_name") or "").strip()
    feedback = feedback_override if isinstance(feedback_override, dict) else _xiaotu_get_report_feedback(wendangid, owner_name=owner_name)
    feedback = _xiaotu_enrich_feedback_data(feedback, owner_name=owner_name)
    liked = str(feedback.get("dianzan") or "").strip().upper() == "Y"
    wid = str(wendangid or "").strip()
    report_url = str(report_url or _xiaotu_build_report_history_url(wid)).strip()
    suffix = re.sub(r"[^A-Za-z0-9_]", "_", wid or "manual")[-18:] or "manual"
    reply_target_options = _xiaotu_build_reply_target_options(feedback, owner_name=owner_name)
    feedback_expanded = bool(feedback_expanded)
    preview_count = 3
    total_feedback_count = len(list(feedback.get("comment_items") or [])) + len(list(feedback.get("reply_items") or []))
    like_button = {
        "tag": "button",
        "name": f"like_btn_{suffix}",
        "text": {
            "tag": "plain_text",
            "content": "已点赞" if liked else "点赞"
        },
        "type": "danger_filled" if liked else "primary",
        "size": "small",
        "behaviors": [
            {
                "type": "callback",
                "value": {
                    "action": "like_report",
                    "wendangid": wid,
                    "doc_url": str(doc_url or "").strip(),
                    "image_key": str(image_key or "").strip(),
                    "feedback_expanded": "1" if feedback_expanded else "0"
                }
            }
        ]
    }
    action_column = {
        "tag": "column",
        "width": "auto",
        "elements": [like_button]
    }
    columns = [action_column]
    if report_url:
        columns.append({
            "tag": "column",
            "width": "auto",
            "elements": [
                {
                    "tag": "button",
                    "name": f"report_btn_{suffix}",
                    "text": {
                        "tag": "plain_text",
                        "content": "查看日报"
                    },
                    "type": "default",
                    "size": "small",
                    "behaviors": [
                        {
                            "type": "open_url",
                            "default_url": report_url
                        }
                    ]
                }
            ]
        })
    if doc_url:
        columns.append({
            "tag": "column",
            "width": "auto",
            "elements": [
                {
                    "tag": "button",
                    "name": f"doc_btn_{suffix}",
                    "text": {
                        "tag": "plain_text",
                        "content": "打开云文档"
                    },
                    "type": "default",
                    "size": "small",
                    "behaviors": [
                        {
                            "type": "open_url",
                            "default_url": str(doc_url).strip()
                        }
                    ]
                }
            ]
        })
    card_elements = _xiaotu_build_card_source_elements(
        source_text=source_text,
        image_paths_text=image_paths_text,
        fallback_image_key=image_key,
        max_blocks=16,
        full_content_url=report_url
    )
    if not card_elements:
        card_elements = [{
            "tag": "markdown",
            "content": "**原文内容**\n（无原文内容）"
        }]
    notice_val = str(notice_markdown or "").strip()
    if notice_val:
        card_elements = [{
            "tag": "markdown",
            "content": notice_val
        }, {
            "tag": "hr"
        }] + card_elements
    card_elements.extend([
        {
            "tag": "markdown",
            "content": f"**文档标题：** {title_val}\n**人员类型：** {person_val}"
        },
        {
            "tag": "hr"
        },
        ({
            "tag": "column_set",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [{
                        "tag": "markdown",
                        "content": f"**评价结果**\n{summary_val}"
                    }]
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [{
                        "tag": "markdown",
                        "content": f"**对组织绩效影响**\n{org_impact_val}"
                    }]
                }
            ],
            "horizontal_spacing": "12px"
        } if org_impact_val else {
            "tag": "markdown",
            "content": f"**评价结果**\n{summary_val}"
        }),
        {
            "tag": "hr"
        },
        {
            "tag": "column_set",
            "columns": columns,
            "horizontal_spacing": "8px"
        },
        {
            "tag": "form",
            "name": f"report_feedback_form_{suffix}",
            "elements": [
                *([
                    {
                        "tag": "select_static",
                        "name": "reply_target",
                        "placeholder": {
                            "tag": "plain_text",
                            "content": "可选：选择要回复的人"
                        },
                        "options": reply_target_options
                    }
                ] if reply_target_options else []),
                {
                    "tag": "input",
                    "name": "feedback_text",
                    "input_type": "multiline_text",
                    "rows": 2,
                    "max_rows": 5,
                    "max_length": 1000,
                    "required": False,
                    "width": "fill",
                    "placeholder": {
                        "tag": "plain_text",
                        "content": "输入评论或回复内容"
                    }
                },
                {
                    "tag": "column_set",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "auto",
                            "elements": [
                                {
                                    "tag": "button",
                                    "name": f"feedback_submit_{suffix}",
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "提交互动"
                                    },
                                    "type": "primary_filled",
                                    "size": "small",
                                    "form_action_type": "submit",
                                    "behaviors": [
                                        {
                                            "type": "callback",
                                            "value": {
                                                "action": "submit_feedback_report",
                                                "wendangid": wid,
                                                "doc_url": str(doc_url or "").strip(),
                                                "image_key": str(image_key or "").strip(),
                                                "feedback_expanded": "1" if feedback_expanded else "0"
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ])
    feedback_text = _xiaotu_card_feedback_text(feedback, expanded=feedback_expanded, preview_count=preview_count)
    if feedback_text:
        card_elements.insert(-2, {
            "tag": "markdown",
            "content": feedback_text
        })
        if total_feedback_count > preview_count:
            card_elements.insert(-2, {
                "tag": "button",
                "name": f"feedback_toggle_{suffix}",
                "text": {
                    "tag": "plain_text",
                    "content": "收起记录" if feedback_expanded else "展开记录"
                },
                "type": "default",
                "size": "small",
                "behaviors": [
                    {
                        "type": "callback",
                        "value": {
                            "action": "toggle_feedback_records",
                            "wendangid": wid,
                            "doc_url": str(doc_url or "").strip(),
                            "image_key": str(image_key or "").strip(),
                            "feedback_expanded": "0" if feedback_expanded else "1"
                        }
                    }
                ]
            })
    return {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "width_mode": "fill"
        },
        "header": {
            "template": str(header_template or "blue").strip() or "blue",
            "title": {
                "tag": "plain_text",
                "content": str(header_title or title_val).strip() or title_val
            }
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 12px 12px",
            "elements": card_elements
        }
    }



def _xiaotu_get_card_action_payload(
    data,
    _xiaotu_find_first_key,
):
    event = (data or {}).get("event") or {}
    action = event.get("action") or (data or {}).get("action") or {}
    if not isinstance(action, dict):
        action = {}
    value = action.get("value")
    if not isinstance(value, dict):
        value = _xiaotu_find_first_key(data, {"value"})
    if not isinstance(value, dict):
        value = {}
    form_value = action.get("form_value")
    if not isinstance(form_value, dict):
        form_value = _xiaotu_find_first_key(data, {"form_value", "form", "form_values"})
    if not isinstance(form_value, dict):
        form_value = {}
    operator = event.get("operator") or (data or {}).get("operator") or {}
    identity_candidates = []
    for candidate in (
        operator,
        (operator.get("operator_id") if isinstance(operator, dict) else None),
        (event.get("user") if isinstance(event, dict) else None),
        (event.get("sender") if isinstance(event, dict) else None),
        ((data or {}).get("operator") if isinstance(data, dict) else None),
        ((data or {}).get("user") if isinstance(data, dict) else None),
        ((data or {}).get("sender") if isinstance(data, dict) else None),
    ):
        if isinstance(candidate, dict):
            identity_candidates.append(candidate)
    open_id = ""
    user_id = ""
    union_id = ""
    operator_name = ""
    for one in identity_candidates:
        if not open_id:
            open_id = str(
                one.get("open_id")
                or ((one.get("operator_id") or {}).get("open_id") if isinstance(one.get("operator_id"), dict) else "")
                or ""
            ).strip()
        if not user_id:
            user_id = str(
                one.get("user_id")
                or ((one.get("operator_id") or {}).get("user_id") if isinstance(one.get("operator_id"), dict) else "")
                or ""
            ).strip()
        if not union_id:
            union_id = str(
                one.get("union_id")
                or ((one.get("operator_id") or {}).get("union_id") if isinstance(one.get("operator_id"), dict) else "")
                or ""
            ).strip()
        if not operator_name:
            operator_name = str(
                one.get("name")
                or one.get("user_name")
                or one.get("display_name")
                or one.get("nick_name")
                or ""
            ).strip()
    open_message_id = (
        (event.get("open_message_id") if isinstance(event, dict) else None)
        or (event.get("message_id") if isinstance(event, dict) else None)
        or _xiaotu_find_first_key(data, {"open_message_id", "message_id"})
        or ""
    )
    return {
        "event": event if isinstance(event, dict) else {},
        "action": action,
        "value": value,
        "form_value": form_value,
        "open_id": str(open_id or "").strip(),
        "user_id": str(user_id or "").strip(),
        "union_id": str(union_id or "").strip(),
        "operator_name": operator_name,
        "open_message_id": str(open_message_id or "").strip(),
    }



def _xiaotu_handle_report_card_action(
    data,
    _feishu_recent_events,
    _feishu_recent_events_limit,
    _feishu_submit_task,
    _feishu_update_message_card,
    _xiaotu_append_report_comment,
    _xiaotu_append_report_reply,
    _xiaotu_build_card_callback_response,
    _xiaotu_build_report_history_url,
    _xiaotu_build_report_notify_card,
    _xiaotu_extract_comment_text,
    _xiaotu_extract_reply_target_name,
    _xiaotu_finalize_report_card_feedback_async,
    _xiaotu_get_card_action_payload,
    _xiaotu_get_report_card_context,
    _xiaotu_get_report_card_message_id,
    _xiaotu_get_report_feedback,
    _xiaotu_resolve_card_actor_name,
    _xiaotu_upsert_report_like,
    datetime,
):
    payload = _xiaotu_get_card_action_payload(data)
    value = payload.get("value") or {}
    action_name = str(value.get("action") or "").strip()
    wendangid = str(value.get("wendangid") or "").strip()
    doc_url = str(value.get("doc_url") or "").strip()
    image_key = str(value.get("image_key") or "").strip()
    feedback_expanded = str(value.get("feedback_expanded") or "").strip() in {"1", "true", "True", "yes", "on"}
    open_message_id = str(payload.get("open_message_id") or "").strip()
    operator_open_id = str(payload.get("open_id") or "").strip()
    remembered_message_id = _xiaotu_get_report_card_message_id(wendangid, operator_open_id)
    target_message_id = open_message_id or remembered_message_id
    ctx = _xiaotu_get_report_card_context(wendangid)
    title_text = str(ctx.get("title_text") or "未命名标题").strip()
    person_type = str(ctx.get("person_type") or "未设置").strip()
    pingjia_text = str(ctx.get("pingjia_text") or "").strip()
    source_text = str(ctx.get("source_text") or "").strip()
    image_paths_text = str(ctx.get("image_paths_text") or "").strip()
    try:
        _feishu_recent_events.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "stage": "report_card_action_enter",
            "action": action_name,
            "wendangid": wendangid,
            "open_id": str(payload.get("open_id") or "").strip(),
            "user_id": str(payload.get("user_id") or "").strip(),
            "union_id": str(payload.get("union_id") or "").strip(),
            "operator_name": str(payload.get("operator_name") or "").strip(),
            "open_message_id": open_message_id,
            "remembered_message_id": remembered_message_id,
            "has_form_value": bool(payload.get("form_value")),
        })
        if len(_feishu_recent_events) > _feishu_recent_events_limit:
            del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
    except Exception:
        pass
    if action_name == "toggle_feedback_records":
        updated_feedback = _xiaotu_get_report_feedback(wendangid, owner_name=str(ctx.get("owner_name") or "").strip())
        card = _xiaotu_build_report_notify_card(
            title_text,
            person_type,
            pingjia_text,
            doc_url=doc_url,
            source_text=source_text,
            image_key=image_key,
            image_paths_text=image_paths_text,
            wendangid=wendangid,
            report_url=_xiaotu_build_report_history_url(wendangid),
            feedback_override=updated_feedback,
            feedback_expanded=feedback_expanded
        )
        patch_ok = True
        patch_err = ""
        if target_message_id:
            patch_ok, patch_err = _feishu_update_message_card(target_message_id, card)
        toast_text = "已展开记录" if feedback_expanded else "已收起记录"
        if target_message_id and not patch_ok:
            return _xiaotu_build_card_callback_response(None, "warning", f"{toast_text}，但卡片刷新失败：{patch_err or '未知错误'}")
        return _xiaotu_build_card_callback_response(card, "success", toast_text)
    if action_name == "like_report":
        actor_name = _xiaotu_resolve_card_actor_name(payload)
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "report_card_actor_resolved",
                "action": action_name,
                "wendangid": wendangid,
                "open_id": str(payload.get("open_id") or "").strip(),
                "user_id": str(payload.get("user_id") or "").strip(),
                "union_id": str(payload.get("union_id") or "").strip(),
                "operator_name": str(payload.get("operator_name") or "").strip(),
                "actor_name": str(actor_name or "").strip(),
            })
        except Exception:
            pass
        ok, err = _xiaotu_upsert_report_like(wendangid, actor_name)
        if not ok:
            try:
                _feishu_recent_events.append({
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "stage": "report_card_action_error",
                    "action": action_name,
                    "wendangid": wendangid,
                    "error": str(err or "未知错误")
                })
            except Exception:
                pass
            return _xiaotu_build_card_callback_response(None, "error", f"点赞失败：{err or '未知错误'}")
        _feishu_submit_task(
            _xiaotu_finalize_report_card_feedback_async,
            wendangid,
            action_name,
            actor_name,
            target_message_id,
            open_message_id,
            operator_open_id,
            "",
            "",
            feedback_expanded,
            doc_url,
            image_key,
        )
        return _xiaotu_build_card_callback_response(None, "success", "已点赞")
    if action_name in {"comment_report", "reply_report", "submit_feedback_report"}:
        form_value = payload.get("form_value") or {}
        comment_text = _xiaotu_extract_comment_text(form_value)
        reply_target_name = _xiaotu_extract_reply_target_name(form_value)
        actor_name = _xiaotu_resolve_card_actor_name(payload)
        effective_action = action_name
        if action_name == "submit_feedback_report":
            effective_action = "reply_report" if reply_target_name else "comment_report"
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "report_card_actor_resolved",
                "action": effective_action,
                "wendangid": wendangid,
                "open_id": str(payload.get("open_id") or "").strip(),
                "user_id": str(payload.get("user_id") or "").strip(),
                "union_id": str(payload.get("union_id") or "").strip(),
                "operator_name": str(payload.get("operator_name") or "").strip(),
                "actor_name": str(actor_name or "").strip(),
                "reply_target_name": str(reply_target_name or "").strip(),
            })
        except Exception:
            pass
        if not comment_text:
            return _xiaotu_build_card_callback_response(None, "warning", "请先输入互动内容")
        if effective_action == "reply_report":
            if not reply_target_name:
                return _xiaotu_build_card_callback_response(None, "warning", "请先选择回复对象")
            ok, err = _xiaotu_append_report_reply(wendangid, actor_name, comment_text, reply_target_name)
            if not ok:
                try:
                    _feishu_recent_events.append({
                        "ts": datetime.now().isoformat(timespec="seconds"),
                        "stage": "report_card_action_error",
                        "action": effective_action,
                        "wendangid": wendangid,
                        "error": str(err or "未知错误"),
                        "comment_preview": str(comment_text or "")[:80],
                        "reply_target_name": str(reply_target_name or "").strip()
                    })
                except Exception:
                    pass
                return _xiaotu_build_card_callback_response(None, "error", err or "回复提交失败")
        else:
            ok, err = _xiaotu_append_report_comment(wendangid, actor_name, comment_text)
            if not ok:
                try:
                    _feishu_recent_events.append({
                        "ts": datetime.now().isoformat(timespec="seconds"),
                        "stage": "report_card_action_error",
                        "action": effective_action,
                        "wendangid": wendangid,
                        "error": str(err or "未知错误"),
                        "comment_preview": str(comment_text or "")[:80]
                    })
                except Exception:
                    pass
                return _xiaotu_build_card_callback_response(None, "error", err or "评论提交失败")
        _feishu_submit_task(
            _xiaotu_finalize_report_card_feedback_async,
            wendangid,
            effective_action,
            actor_name,
            target_message_id,
            open_message_id,
            operator_open_id,
            reply_target_name,
            comment_text,
            feedback_expanded,
            doc_url,
            image_key,
        )
        success_label = "回复已提交并通知对方" if effective_action == "reply_report" else "评论已提交"
        return _xiaotu_build_card_callback_response(None, "success", success_label)
    return _xiaotu_build_card_callback_response(None, "info", "未识别的卡片操作")

