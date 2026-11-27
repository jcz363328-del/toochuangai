"""Submit a daily report from the Feishu messaging entry point."""

from __future__ import annotations


def api_xiaotu_daily_from_im(
    *,
    _clear_feishu_user_access_token,
    _feishu_http,
    _generate_ai_answer_with_doc,
    _get_feishu_user_access_token,
    _xiaotu_format_message_time,
    _xiaotu_get_message_text_for_daily_ref,
    _xiaotu_get_sender_open_id_from_message,
    datetime,
    jsonify,
    request,
    session,
    url_for,
):
    stage = "start"
    try:
        stage = "auth"
        user_id = str(session.get('feishu_user_id') or '').strip()
        user_name = str(session.get('feishu_user_name') or '用户').strip()
        user_access_token = _get_feishu_user_access_token()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        if not user_access_token:
            session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center')
            return jsonify({
                'success': False,
                'message': '登录状态缺少飞书消息访问凭证，正在跳转重新登录',
                'auth_url': url_for('feishu_auth')
            }), 401

        stage = "parse_args"
        payload = request.get_json(silent=True) or {}
        max_chats = int(payload.get('max_chats') or 60)
        max_chats = max(1, min(max_chats, 120))
        max_messages_per_chat = int(payload.get('max_messages_per_chat') or 80)
        max_messages_per_chat = max(20, min(max_messages_per_chat, 200))

        now = datetime.now()
        day_start = datetime(now.year, now.month, now.day, 0, 0, 0)
        day_end = now
        # 飞书消息列表接口使用秒级时间戳，传毫秒会导致当天消息范围失真
        start_ts = str(int(day_start.timestamp()))
        end_ts = str(int(day_end.timestamp()))
        headers = {"Authorization": f"Bearer {user_access_token}"}
        debug_logs = []
        need_reauth = False

        stage = "load_chats"
        chat_items = []
        chat_page_token = ""
        skipped_group_count = 0
        while True:
            params = {"page_size": 100}
            if chat_page_token:
                params["page_token"] = chat_page_token
            try:
                resp = _feishu_http.get("https://open.feishu.cn/open-apis/im/v1/chats", headers=headers, params=params, timeout=15)
                data = resp.json() if resp is not None else {}
            except Exception as e:
                data = {}
                debug_logs.append(f"拉取群列表异常: {str(e)}")
                break
            code_num = -1
            if isinstance(data, dict):
                try:
                    code_num = int(data.get("code"))
                except Exception:
                    code_num = -1
            if not isinstance(data, dict) or code_num != 0:
                code_text = str((data or {}).get("code") if isinstance(data, dict) else "")
                msg_text = str((data or {}).get("msg") if isinstance(data, dict) else "")
                if (
                    code_text in {"99991677", "99991663", "99991679", "99991695"}
                    or "token expired" in msg_text.lower()
                    or "历史版本" in msg_text
                    or "end-user-consent" in msg_text.lower()
                    or "please request user re-authorization" in msg_text.lower()
                    or "应用未获取所需的用户授权" in msg_text
                ):
                    need_reauth = True
                debug_logs.append(
                    "拉取群列表失败: code={code}, msg={msg}, request_id={rid}".format(
                        code=str((data or {}).get("code") if isinstance(data, dict) else "unknown"),
                        msg=str((data or {}).get("msg") if isinstance(data, dict) else "invalid_response"),
                        rid=str(((data or {}).get("request_id") if isinstance(data, dict) else "") or "-")
                    )
                )
                break
            body = data.get("data") if isinstance(data.get("data"), dict) else {}
            items = body.get("items") if isinstance(body.get("items"), list) else []
            for one in items:
                if not isinstance(one, dict):
                    continue
                chat_id = str(one.get("chat_id") or "").strip()
                if not chat_id:
                    continue
                chat_mode = str(one.get("chat_mode") or one.get("chat_type") or one.get("type") or "").strip().lower()
                # 当前应用类型读取群聊消息会报 231204，这里只保留单聊（p2p）进行日报参考生成
                if chat_mode and chat_mode != "p2p":
                    skipped_group_count += 1
                    continue
                if not chat_mode:
                    continue
                chat_items.append({
                    "chat_id": chat_id,
                    "name": str(one.get("name") or "").strip() or chat_id,
                    "chat_mode": chat_mode
                })
                if len(chat_items) >= max_chats:
                    break
            if len(chat_items) >= max_chats:
                break
            chat_page_token = str(body.get("page_token") or "").strip()
            if not chat_page_token:
                break

        if not chat_items:
            if skipped_group_count:
                debug_logs.append(f"已跳过群聊 {skipped_group_count} 个，当前未识别到可读取的单聊会话")
            else:
                debug_logs.append("当前未识别到可读取的单聊会话")

        stage = "load_messages"
        all_lines = []
        used_chat_count = 0
        total_message_count = 0
        total_self_message_count = 0

        for chat in chat_items:
            if len(all_lines) >= 1800:
                break
            chat_id = str(chat.get("chat_id") or "").strip()
            chat_name = str(chat.get("name") or "").strip() or chat_id
            if not chat_id:
                continue
            page_token = ""
            chat_lines = []
            fetched_this_chat = 0
            while fetched_this_chat < max_messages_per_chat:
                params = {
                    "container_id_type": "chat",
                    "container_id": chat_id,
                    "sort_type": "ByCreateTimeAsc",
                    "start_time": start_ts,
                    "end_time": end_ts,
                    "page_size": min(50, max_messages_per_chat - fetched_this_chat)
                }
                if page_token:
                    params["page_token"] = page_token
                try:
                    resp = _feishu_http.get("https://open.feishu.cn/open-apis/im/v1/messages", headers=headers, params=params, timeout=15)
                    data = resp.json() if resp is not None else {}
                except Exception as e:
                    debug_logs.append(f"拉取单聊消息异常: chat={chat_name}({chat_id}), err={str(e)}")
                    break
                code_num = -1
                if isinstance(data, dict):
                    try:
                        code_num = int(data.get("code"))
                    except Exception:
                        code_num = -1
                if not isinstance(data, dict) or code_num != 0:
                    code_text = str((data or {}).get("code") if isinstance(data, dict) else "")
                    msg_text = str((data or {}).get("msg") if isinstance(data, dict) else "")
                    if (
                        code_text in {"99991677", "99991663", "99991679", "99991695"}
                        or "token expired" in msg_text.lower()
                        or "历史版本" in msg_text
                        or "end-user-consent" in msg_text.lower()
                        or "please request user re-authorization" in msg_text.lower()
                        or "应用未获取所需的用户授权" in msg_text
                    ):
                        need_reauth = True
                    debug_logs.append(
                        "拉取单聊消息失败: chat={chat}, code={code}, msg={msg}, request_id={rid}".format(
                            chat=f"{chat_name}({chat_id})",
                            code=str((data or {}).get("code") if isinstance(data, dict) else "unknown"),
                            msg=str((data or {}).get("msg") if isinstance(data, dict) else "invalid_response"),
                            rid=str(((data or {}).get("request_id") if isinstance(data, dict) else "") or "-")
                        )
                    )
                    break
                body = data.get("data") if isinstance(data.get("data"), dict) else {}
                items = body.get("items") if isinstance(body.get("items"), list) else []
                if not items:
                    break
                for msg in items:
                    text = _xiaotu_get_message_text_for_daily_ref(msg)
                    if not text:
                        continue
                    sender_open_id = _xiaotu_get_sender_open_id_from_message(msg)
                    is_self = bool(sender_open_id and sender_open_id == user_id)
                    tm = _xiaotu_format_message_time(msg.get("create_time"))
                    sender_show = user_name if is_self else (str(sender_open_id or "他人")[:24])
                    line = f"{tm} [{sender_show}] {text}" if tm else f"[{sender_show}] {text}"
                    chat_lines.append(line)
                    total_message_count += 1
                    if is_self:
                        total_self_message_count += 1
                    fetched_this_chat += 1
                    if fetched_this_chat >= max_messages_per_chat:
                        break
                page_token = str(body.get("page_token") or "").strip()
                if not page_token:
                    break

            if chat_lines:
                used_chat_count += 1
                all_lines.append(f"【单聊】{chat_name}")
                all_lines.extend(chat_lines[:max_messages_per_chat])
                all_lines.append("")

        source_text = "\n".join(all_lines).strip()
        if not source_text:
            if need_reauth:
                _clear_feishu_user_access_token()
                session['feishu_user_access_token_expire_at'] = ''
                session['post_auth_redirect'] = url_for('dashboard_xiaotu_report_center')
                return jsonify({
                    'success': False,
                    'message': '飞书用户授权缺少最新权限，正在跳转重新授权',
                    'auth_url': url_for('feishu_auth'),
                    'debug': debug_logs[:20]
                }), 401
            reason_text = "；".join(debug_logs[:6]).strip()
            full_message = '未获取到今日可用的飞书对话文本'
            if reason_text:
                full_message += f'。详细原因：{reason_text}'
            else:
                if skipped_group_count and not chat_items:
                    full_message += '。当前已按“仅单聊”模式过滤，群聊已全部跳过，请确认今天存在单聊记录。'
                else:
                    full_message += '。请确认今天有单聊消息记录且应用具备消息读取权限。'
            return jsonify({
                'success': False,
                'message': full_message,
                'debug': debug_logs[:20]
            }), 404

        stage = "generate"
        prompt = (
            f"请基于以下飞书对话记录，为“{user_name}”生成一份当日日报参考草稿。\n"
            "要求：\n"
            "1) 重点提炼“我本人”相关工作推进、沟通协作、问题与结论；\n"
            "2) 输出结构固定为：今日重点工作、沟通与协作、问题与风险、明日计划；\n"
            "3) 信息必须来自对话原文，不要臆测；\n"
            "4) 语气简洁、可直接复制到日报中。"
        )
        daily_draft = _generate_ai_answer_with_doc(
            prompt_text=prompt,
            doc_text=source_text[:50000],
            doc_name=f"{user_name}-飞书对话-日报参考-{now.strftime('%Y%m%d')}",
            chat_id=f"xiaotu_daily_im:{user_id}:{int(now.timestamp())}"
        )

        return jsonify({
            'success': True,
            'data': {
                'date': now.strftime('%Y-%m-%d'),
                'user_name': user_name,
                'chat_count': used_chat_count,
                'p2p_chat_count': len(chat_items),
                'skipped_group_count': skipped_group_count,
                'message_count': total_message_count,
                'self_message_count': total_self_message_count,
                'daily_draft': str(daily_draft or '').strip(),
                'source_preview': source_text[:4000],
                'debug': debug_logs[:20]
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'生成失败（阶段:{stage}）: {str(e)}',
            'stage': stage,
            'debug': []
        }), 500
