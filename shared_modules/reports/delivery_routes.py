"""Daily report delivery state and feedback entry points."""

from __future__ import annotations


def _xiaotu_collect_report_delivery_targets(
    wendangid,
    report_row,
    *,
    _xiaotu_get_report_card_receive_ids,
    _xiaotu_get_report_owner_open_id_resolved,
    _xiaotu_get_report_row,
    _xiaotu_guess_report_default_notify_open_ids,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_query_user_names_by_open_ids,
    _xiaotu_split_cache_multi_value,
):
    wid = str(wendangid or "").strip()
    row = report_row if isinstance(report_row, dict) else _xiaotu_get_report_row(wid)
    owner_open_id = _xiaotu_get_report_owner_open_id_resolved(wid, row)
    owner_name = str((row or {}).get("xingming") or "").strip()
    targets = []
    seen_open_ids = set()
    unresolved_names = []
    seen_names = set()

    def _append_target(open_id="", name="", source=""):
        oid = str(open_id or "").strip()
        nm = str(name or "").strip()
        src = str(source or "").strip()
        if oid:
            if oid == owner_open_id or oid in seen_open_ids:
                return
            seen_open_ids.add(oid)
            targets.append({
                "open_id": oid,
                "name": nm,
                "source": src,
            })
            return
        if nm and nm != owner_name and nm not in seen_names:
            seen_names.add(nm)
            unresolved_names.append(nm)

    for receive_id in _xiaotu_get_report_card_receive_ids(wid):
        _append_target(receive_id, source="message_store")

    for notify_name in _xiaotu_split_cache_multi_value((row or {}).get("jieshouren") or ""):
        resolved_open_id = str(_xiaotu_lookup_open_id_by_name(notify_name) or "").strip()
        _append_target(resolved_open_id, notify_name, source="report_row")

    if not targets and not unresolved_names:
        for open_id in _xiaotu_guess_report_default_notify_open_ids(owner_open_id, owner_name):
            _append_target(open_id, source="default_policy")

    missing_name_open_ids = [str(item.get("open_id") or "").strip() for item in targets if str(item.get("open_id") or "").strip() and not str(item.get("name") or "").strip()]
    if missing_name_open_ids:
        name_map = _xiaotu_query_user_names_by_open_ids(missing_name_open_ids) or {}
        for item in targets:
            oid = str(item.get("open_id") or "").strip()
            if oid and not str(item.get("name") or "").strip():
                item["name"] = str(name_map.get(oid) or "").strip()

    return {
        "owner_open_id": owner_open_id,
        "targets": targets,
        "unresolved_names": unresolved_names,
    }


def _xiaotu_get_report_delivery_status(
    wendangid,
    report_row,
    *,
    _feishu_get_message_read_users,
    _xiaotu_collect_report_delivery_targets,
    _xiaotu_get_report_card_message_id,
    _xiaotu_get_report_row,
):
    wid = str(wendangid or "").strip()
    row = report_row if isinstance(report_row, dict) else _xiaotu_get_report_row(wid)
    delivery_targets_info = _xiaotu_collect_report_delivery_targets(wid, row)
    owner_open_id = str((delivery_targets_info or {}).get("owner_open_id") or "").strip()
    notify_targets = list((delivery_targets_info or {}).get("targets") or [])
    unresolved_names = list((delivery_targets_info or {}).get("unresolved_names") or [])
    total_targets = len(notify_targets) + len(unresolved_names)
    read_count = 0
    unread_count = 0
    unknown_count = 0
    items = []
    notify_open_ids = []
    for notify_target in notify_targets:
        oid = str((notify_target or {}).get("open_id") or "").strip()
        if not oid:
            continue
        notify_open_ids.append(oid)
        message_id = _xiaotu_get_report_card_message_id(wid, oid)
        read_users = []
        err = ""
        if message_id:
            read_users, err = _feishu_get_message_read_users(message_id, user_id_type="open_id")
        else:
            err = "未找到消息ID"
        is_read = None
        if err:
            unknown_count += 1
        else:
            is_read = bool(oid in set(read_users))
            if is_read:
                read_count += 1
            else:
                unread_count += 1
        items.append({
            "open_id": oid,
            "name": str((notify_target or {}).get("name") or "").strip(),
            "message_id": message_id,
            "is_read": is_read,
            "error": str(err or "").strip(),
            "source": str((notify_target or {}).get("source") or "").strip(),
        })
    for notify_name in unresolved_names:
        unknown_count += 1
        items.append({
            "open_id": "",
            "name": str(notify_name or "").strip(),
            "message_id": "",
            "is_read": None,
            "error": "未找到接收人飞书ID",
            "source": "report_row_name",
        })
    if total_targets <= 0:
        status_code = "no_external_targets"
        status_text = "未检测到其他通知对象"
        can_recall_edit = True
    elif unknown_count > 0:
        status_code = "unknown"
        if read_count > 0 and unread_count > 0:
            status_text = "部分读取状态获取失败"
        elif read_count > 0:
            status_text = "已读状态部分获取失败"
        elif unread_count > 0:
            status_text = "未读状态部分获取失败"
        else:
            status_text = "读取状态获取失败"
        can_recall_edit = read_count == 0
    elif read_count == 0:
        status_code = "all_unread"
        status_text = f"全部未读（{unread_count}人）"
        can_recall_edit = True
    elif unread_count == 0:
        status_code = "all_read"
        status_text = f"已全部阅读（{read_count}人）"
        can_recall_edit = False
    else:
        status_code = "partial_read"
        status_text = f"部分已读（已读{read_count}人，未读{unread_count}人）"
        can_recall_edit = False
    return {
        "status_code": status_code,
        "status_text": status_text,
        "can_recall_edit": bool(can_recall_edit),
        "total_targets": total_targets,
        "read_count": read_count,
        "unread_count": unread_count,
        "unknown_count": unknown_count,
        "owner_open_id": owner_open_id,
        "notify_open_ids": notify_open_ids,
        "notify_targets": [
            {
                "open_id": str(item.get("open_id") or "").strip(),
                "name": str(item.get("name") or "").strip(),
            }
            for item in items
        ],
        "items": items,
    }


def _xiaotu_finalize_report_card_feedback_async(
    wendangid,
    action_name,
    actor_name,
    target_message_id,
    open_message_id,
    operator_open_id,
    reply_target_name,
    comment_text,
    feedback_expanded,
    doc_url,
    image_key,
    *,
    _feishu_recent_events,
    _feishu_recent_events_limit,
    _feishu_update_message_card,
    _xiaotu_build_report_history_url,
    _xiaotu_build_report_notify_card,
    _xiaotu_get_report_card_context,
    _xiaotu_get_report_card_message_ids,
    _xiaotu_get_report_card_receive_ids,
    _xiaotu_get_report_feedback,
    _xiaotu_get_report_owner_open_id,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_notify_feedback_open_ids,
    _xiaotu_notify_feedback_reply_target,
    _xiaotu_notify_report_owner_feedback,
    _xiaotu_patch_related_report_cards,
    datetime,
):
    wid = str(wendangid or "").strip()
    effective_action = str(action_name or "").strip()
    if not wid or not effective_action:
        return
    try:
        ctx = _xiaotu_get_report_card_context(wid)
        title_text = str((ctx or {}).get("title_text") or "未命名标题").strip()
        person_type = str((ctx or {}).get("person_type") or "未设置").strip()
        pingjia_text = str((ctx or {}).get("pingjia_text") or "").strip()
        source_text = str((ctx or {}).get("source_text") or "").strip()
        image_paths_text = str((ctx or {}).get("image_paths_text") or "").strip()
        owner_name = str((ctx or {}).get("owner_name") or "").strip()
        report_url = _xiaotu_build_report_history_url(wid)
        updated_feedback = _xiaotu_get_report_feedback(wid, owner_name=owner_name)
        card = _xiaotu_build_report_notify_card(
            title_text,
            person_type,
            pingjia_text,
            doc_url=doc_url,
            source_text=source_text,
            image_key=image_key,
            image_paths_text=image_paths_text,
            wendangid=wid,
            report_url=report_url,
            feedback_override=updated_feedback,
            feedback_expanded=feedback_expanded
        )
        patch_ok = True
        patch_err = ""
        if str(target_message_id or "").strip():
            patch_ok, patch_err = _feishu_update_message_card(target_message_id, card)
        owner_notify_ok, owner_notify_err = _xiaotu_notify_report_owner_feedback(
            wid, effective_action, actor_name, comment_text, reply_target_name
        )
        reply_target_notify_ok = True
        reply_target_notify_err = ""
        if effective_action == "reply_report":
            reply_target_notify_ok, reply_target_notify_err = _xiaotu_notify_feedback_reply_target(
                wid, actor_name, reply_target_name, comment_text
            )
        owner_open_id = _xiaotu_get_report_owner_open_id(wid) or _xiaotu_lookup_open_id_by_name(owner_name)
        reply_target_open_id = _xiaotu_lookup_open_id_by_name(reply_target_name) if effective_action == "reply_report" else ""
        participant_notify_results = _xiaotu_notify_feedback_open_ids(
            wid,
            effective_action,
            actor_name,
            comment_text,
            reply_target_name,
            open_ids=_xiaotu_get_report_card_receive_ids(wid),
            skip_open_ids=[operator_open_id, owner_open_id, reply_target_open_id]
        )
        related_open_ids = [
            operator_open_id,
            owner_open_id,
            reply_target_open_id,
            *(_xiaotu_get_report_card_receive_ids(wid) or [])
        ]
        related_message_map = {}
        for related_open_id in related_open_ids:
            oid = str(related_open_id or "").strip()
            if not oid or oid in related_message_map:
                continue
            related_message_map[oid] = _xiaotu_get_report_card_message_ids(wid, oid)
        sync_results = _xiaotu_patch_related_report_cards(
            wid,
            related_open_ids,
            card,
            skip_message_ids=[target_message_id, open_message_id]
        )
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "report_card_async_finalize",
                "action": effective_action,
                "wendangid": wid,
                "target_message_id": str(target_message_id or "").strip(),
                "patch_ok": bool(patch_ok),
                "patch_err": str(patch_err or ""),
                "owner_open_id": owner_open_id,
                "owner_notify_ok": bool(owner_notify_ok),
                "owner_notify_err": str(owner_notify_err or ""),
                "reply_target_name": str(reply_target_name or "").strip(),
                "reply_target_notify_ok": bool(reply_target_notify_ok),
                "reply_target_notify_err": str(reply_target_notify_err or ""),
                "participant_notify_results": participant_notify_results,
                "related_message_map": related_message_map,
                "sync_results": sync_results
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
    except Exception as e:
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "report_card_async_finalize_error",
                "action": effective_action,
                "wendangid": wid,
                "error": str(e)
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass


def api_xiaotu_report_delivery_status(
    *,
    _xiaotu_get_report_delivery_status,
    _xiaotu_get_report_row,
    jsonify,
    request,
    session,
):
    try:
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        wendangid = str(request.args.get('wendangid') or '').strip()
        if not wendangid:
            return jsonify({'success': False, 'message': '缺少日报ID'}), 400
        row = _xiaotu_get_report_row(wendangid)
        if not row:
            return jsonify({'success': False, 'message': '未找到对应日报'}), 404
        session_user_name = str(session.get('feishu_user_name') or '').strip()
        status = _xiaotu_get_report_delivery_status(wendangid, row)
        return jsonify({
            'success': True,
            'data': {
                'wendangid': wendangid,
                'status': status,
                'editable_by_current_user': bool(session_user_name and session_user_name == str(row.get('xingming') or '').strip()),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取投递状态失败: {str(e)}'}), 500


def api_xiaotu_report_feedback(
    *,
    _feishu_recent_events,
    _feishu_recent_events_limit,
    _xiaotu_append_report_comment,
    _xiaotu_append_report_reply,
    _xiaotu_get_report_card_context,
    _xiaotu_get_report_feedback,
    _xiaotu_notify_feedback_reply_target,
    _xiaotu_notify_report_owner_feedback,
    _xiaotu_remove_report_feedback_entry,
    _xiaotu_report_history_is_visible_to_user,
    _xiaotu_toggle_report_like,
    datetime,
    jsonify,
    request,
    session,
):
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        actor_name = str(session.get('feishu_user_name') or '').strip()
        if not actor_name:
            return jsonify({'success': False, 'message': '未获取到当前用户名'}), 403
        payload = request.get_json(silent=True) if request.is_json else request.form
        payload = payload if isinstance(payload, dict) else {}
        action_name = str(payload.get('action') or '').strip().lower()
        wendangid = str(payload.get('wendangid') or '').strip()
        comment_text = str(payload.get('comment_text') or '').strip()
        target_name = str(payload.get('target_name') or '').strip()
        item_index = payload.get('item_index')
        try:
            _feishu_recent_events.append({
                'ts': datetime.now().isoformat(timespec="seconds"),
                'stage': 'report_feedback_api_enter',
                'action': action_name,
                'wendangid': wendangid,
                'actor_name': actor_name,
                'target_name': target_name,
                'text_preview': comment_text[:80]
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
        if not wendangid:
            return jsonify({'success': False, 'message': '缺少文档ID'}), 400
        if not _xiaotu_report_history_is_visible_to_user(wendangid, actor_name):
            return jsonify({'success': False, 'message': '无权查看或评论该日报'}), 403
        if action_name == 'like':
            ok, err, liked_now = _xiaotu_toggle_report_like(wendangid, actor_name)
            if not ok:
                return jsonify({'success': False, 'message': err or '点赞失败'}), 500
            if liked_now:
                _xiaotu_notify_report_owner_feedback(wendangid, 'like_report', actor_name, '')
        elif action_name == 'comment':
            if not comment_text:
                return jsonify({'success': False, 'message': '评论不能为空'}), 400
            ok, err = _xiaotu_append_report_comment(wendangid, actor_name, comment_text)
            if not ok:
                return jsonify({'success': False, 'message': err or '评论失败'}), 500
            _xiaotu_notify_report_owner_feedback(wendangid, 'comment_report', actor_name, comment_text)
        elif action_name == 'remove_comment':
            ok, err = _xiaotu_remove_report_feedback_entry(wendangid, actor_name, "comment", item_index)
            if not ok:
                return jsonify({'success': False, 'message': err or '撤销评论失败'}), 500
        elif action_name == 'reply':
            if not comment_text:
                return jsonify({'success': False, 'message': '回复内容不能为空'}), 400
            ok, err = _xiaotu_append_report_reply(wendangid, actor_name, comment_text, target_name)
            if not ok:
                return jsonify({'success': False, 'message': err or '回复失败'}), 500
            _xiaotu_notify_report_owner_feedback(wendangid, 'reply_report', actor_name, comment_text, target_name)
            _xiaotu_notify_feedback_reply_target(wendangid, actor_name, target_name, comment_text)
        elif action_name == 'remove_reply':
            ok, err = _xiaotu_remove_report_feedback_entry(wendangid, actor_name, "reply", item_index)
            if not ok:
                return jsonify({'success': False, 'message': err or '撤销回复失败'}), 500
        else:
            return jsonify({'success': False, 'message': '不支持的操作'}), 400
        owner_name = str((_xiaotu_get_report_card_context(wendangid) or {}).get('owner_name') or '').strip()
        feedback = _xiaotu_get_report_feedback(wendangid, owner_name=owner_name)
        try:
            _feishu_recent_events.append({
                'ts': datetime.now().isoformat(timespec="seconds"),
                'stage': 'report_feedback_api_success',
                'action': action_name,
                'wendangid': wendangid
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
        return jsonify({
            'success': True,
            'message': '操作成功',
            'data': {
                'wendangid': wendangid,
                'feedback': {
                    'dianzan': str((feedback or {}).get('dianzan') or '').strip(),
                    'pinglun': str((feedback or {}).get('pinglun') or '').strip(),
                    'huifu': str((feedback or {}).get('huifu') or '').strip(),
                    'yonghu': str((feedback or {}).get('yonghu') or '').strip(),
                    'like_users': list((feedback or {}).get('like_users') or []),
                    'like_count': int((feedback or {}).get('like_count') or 0),
                    'comment_items': list((feedback or {}).get('comment_items') or []),
                    'reply_items': list((feedback or {}).get('reply_items') or []),
                    'reply_targets': list((feedback or {}).get('reply_targets') or []),
                }
            }
        })
    except Exception as e:
        try:
            _feishu_recent_events.append({
                'ts': datetime.now().isoformat(timespec="seconds"),
                'stage': 'report_feedback_api_error',
                'error': str(e)
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
        return jsonify({'success': False, 'message': f'反馈失败: {str(e)}'}), 500
