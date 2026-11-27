def _handle_feishu_cloud_doc_mention_event(
    data,
    _extract_all_text,
    _extract_first_feishu_user_id,
    _feishu_build_cloud_doc_url,
    _feishu_extract_cloud_doc_url_from_event,
    _feishu_find_bitable_url,
    _feishu_find_cloud_doc_url_any,
    _feishu_is_event_processed,
    _feishu_mark_event_processed,
    _feishu_send_text,
    _generate_ai_answer_with_bitable_url,
    _generate_ai_answer_with_cloud_doc_url,
    _generate_cloud_doc_analysis,
    _get_cloud_documents_agent,
    _split_text,
    executor,
    jsonify,
    re,
):
    event = (data or {}).get("event") or {}
    event_id = (
        ((data or {}).get("header") or {}).get("event_id")
        or ((data or {}).get("event") or {}).get("event_id")
        or (event.get("event_id") if isinstance(event, dict) else "")
    )
    if _feishu_is_event_processed(event_id):
        return jsonify({"msg": "ok"}), 200
    _feishu_mark_event_processed(event_id)
    user_id = _extract_first_feishu_user_id(event)
    prompt_text = _extract_all_text(event, max_chars=20000)
    agent = _get_cloud_documents_agent()
    doc_url = _feishu_find_cloud_doc_url_any(prompt_text)
    bitable_url = _feishu_find_bitable_url(prompt_text)
    if not doc_url:
        doc_url = _feishu_extract_cloud_doc_url_from_event(event)
    if not doc_url and agent is not None:
        m = re.search(r"(doxcn[a-zA-Z0-9]+|doccn[a-zA-Z0-9]+)", prompt_text)
        if m:
            token = (m.group(1) or "").strip()
            if token:
                doc_url = _feishu_build_cloud_doc_url("", token)

    if not doc_url and not bitable_url:
        if user_id:
            _feishu_send_text(user_id, "open_id", "我收到了@，但没有找到云文档/多维表格链接。请在评论里贴上飞书云文档链接（/docx/xxxx）或多维表格链接（/base/xxxx）。")
        return jsonify({"msg": "ok"}), 200

    if user_id:
        _feishu_send_text(user_id, "open_id", "收到，我在读取链接内容并生成回答，完成后会发给你。")

    def run():
        if bitable_url and not doc_url:
            content = _generate_ai_answer_with_bitable_url(prompt_text, bitable_url, chat_id=None)
            if user_id and content:
                for chunk in _split_text(content, max_len=1500):
                    _feishu_send_text(user_id, "open_id", chunk)
            return

        kw = (prompt_text or "").strip()
        if (not kw) or any(k in kw for k in ["周报", "月报", "评分", "打分", "评估", "点评", "改进", "复盘"]):
            content = _generate_cloud_doc_analysis(prompt_text, doc_url, chat_id=None)
        else:
            content = _generate_ai_answer_with_cloud_doc_url(prompt_text, doc_url, chat_id=None)

        if user_id and content:
            for chunk in _split_text(content, max_len=1500):
                _feishu_send_text(user_id, "open_id", chunk)

    executor.submit(run)
    return jsonify({"msg": "ok"}), 200



def handle_feishu_message_event(
    data,
    _async_generate_and_reply,
    _async_generate_and_reply_bitable,
    _async_generate_and_reply_cloud_doc,
    _async_generate_and_reply_cloud_doc_qa,
    _async_generate_and_reply_file,
    _async_generate_and_reply_image,
    _async_generate_and_reply_with_skill,
    _async_run_prepress_check,
    _async_stage_prepress_resource,
    _feishu_append_chat_history,
    _feishu_clean_question,
    _feishu_clear_chat_history,
    _feishu_extract_image_keys,
    _feishu_extract_reference_message_ids,
    _feishu_extract_text_from_content,
    _feishu_find_bitable_url,
    _feishu_find_cloud_doc_url,
    _feishu_get_last_bot_ts,
    _feishu_get_last_resource,
    _feishu_get_message_text,
    _feishu_get_skill,
    _feishu_is_bot_mentioned,
    _feishu_is_group_message,
    _feishu_is_message_processed,
    _feishu_is_p2p_message,
    _feishu_mark_message_processed,
    _feishu_parse_message_content,
    _feishu_parse_skill_invocation,
    _feishu_recent_events,
    _feishu_recent_events_limit,
    _feishu_remember_image_resource,
    _feishu_remember_resources,
    _feishu_render_skill_list,
    _feishu_send_text_to_chat,
    _feishu_submit_task,
    datetime,
    jsonify,
    os,
    prepress_check_service,
    secrets,
):
    event = data.get("event") or {}
    if not isinstance(event, dict):
        event = {}
    message = event.get("message") or {}
    if not isinstance(message, dict):
        message = {}
    sender = event.get("sender") or {}
    if not isinstance(sender, dict):
        sender = {}
    sender_type = str(sender.get("sender_type") or "").lower()

    message_id = message.get("message_id")
    if _feishu_is_message_processed(message_id):
        return jsonify({"msg": "ok"}), 200
    _feishu_mark_message_processed(message_id)

    if sender_type and sender_type != "user":
        return jsonify({"msg": "ok"}), 200

    chat_id = message.get("chat_id")
    chat_type = message.get("chat_type")
    if not chat_id:
        return jsonify({"msg": "ok"}), 200

    msg_type = str(message.get("message_type") or message.get("msg_type") or "").lower().strip()
    content_obj = _feishu_parse_message_content(message.get("content"))
    if not msg_type:
        msg_type = str(content_obj.get("msg_type") or content_obj.get("message_type") or "").lower().strip()

    text = _feishu_extract_text_from_content(message.get("content"))
    mentions = message.get("mentions") or []

    try:
        _feishu_recent_events.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "stage": "received_message_event",
            "event_type": event.get("type"),
            "message_id": message_id,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "sender_type": sender_type,
            "msg_type": msg_type,
            "text": text,
            "mentions": mentions,
        })
        if len(_feishu_recent_events) > _feishu_recent_events_limit:
            del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
    except Exception:
        pass

    bot_mentioned = _feishu_is_bot_mentioned(text, mentions)
    if _feishu_is_group_message(chat_type):
        last_bot_ts = _feishu_get_last_bot_ts(chat_id)
        should_respond = bot_mentioned or ((datetime.now().timestamp() - float(last_bot_ts or 0.0)) <= 900)
    elif _feishu_is_p2p_message(chat_type):
        should_respond = True
    else:
        should_respond = bot_mentioned

    user_text_for_memory = str(text or "").strip()
    if msg_type == "post":
        post_image_keys = _feishu_extract_image_keys(content_obj, limit=1)
        if post_image_keys:
            _feishu_remember_image_resource(chat_id, post_image_keys[0], message_id=message_id, resource_type="image")
            if not user_text_for_memory:
                user_text_for_memory = "【图片】"
    elif msg_type == "image":
        image_key = str(content_obj.get("image_key") or content_obj.get("imageKey") or "").strip()
        if image_key:
            _feishu_remember_image_resource(chat_id, image_key, message_id=message_id, resource_type="image")
            if not user_text_for_memory:
                user_text_for_memory = "【图片】"
    elif msg_type == "file":
        file_key = str(content_obj.get("file_key") or content_obj.get("fileKey") or "").strip()
        file_name = str(content_obj.get("file_name") or content_obj.get("fileName") or "").strip()
        ln = file_name.lower().strip()
        if file_key and any(ln.endswith(s) for s in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"]):
            _feishu_remember_image_resource(chat_id, file_key, message_id=message_id, resource_type="file", file_name=file_name)
            if not user_text_for_memory:
                user_text_for_memory = f"【图片】{file_name}".strip()

    if user_text_for_memory:
        _feishu_append_chat_history(chat_id, "user", user_text_for_memory)
        _feishu_remember_resources(chat_id, user_text_for_memory)

    if not should_respond:
        return jsonify({"msg": "ok"}), 200

    question = _feishu_clean_question(user_text_for_memory)
    if question in {"清空记忆", "重置记忆", "/reset", "reset"}:
        _feishu_clear_chat_history(chat_id)
        prepress_check_service.reset_session(chat_id)
        _feishu_send_text_to_chat(chat_id, "已清空本会话的上下文记忆。")
        return jsonify({"msg": "ok"}), 200

    prepress_trigger = prepress_check_service.is_trigger(question)
    if msg_type == "file":
        file_key = str(content_obj.get("file_key") or content_obj.get("fileKey") or "").strip()
        file_name = str(content_obj.get("file_name") or content_obj.get("fileName") or "").strip()
        extension = os.path.splitext(file_name)[1].lower()
        should_stage = (
            extension in {".ai", ".zip"}
            or prepress_trigger
            or (prepress_check_service.has_active_session(chat_id) and prepress_check_service.accepts_filename(file_name))
        )
        if file_key and should_stage and prepress_check_service.accepts_filename(file_name):
            prepress_check_service.activate_session(chat_id)
            _feishu_send_text_to_chat(chat_id, "收到，正在收集并校验印前文件…")
            _feishu_submit_task(
                _async_stage_prepress_resource,
                chat_id,
                message_id,
                file_key,
                "file",
                file_name,
                prepress_trigger,
            )
            return jsonify({"msg": "ok"}), 200
    if msg_type == "image" and prepress_check_service.has_active_session(chat_id):
        image_key = str(content_obj.get("image_key") or content_obj.get("imageKey") or "").strip()
        if image_key:
            _feishu_send_text_to_chat(chat_id, "收到，正在把截图加入印前文件组…")
            _feishu_submit_task(
                _async_stage_prepress_resource,
                chat_id,
                message_id,
                image_key,
                "image",
                f"screenshot_{message_id or secrets.token_hex(8)}.png",
                prepress_trigger,
            )
            return jsonify({"msg": "ok"}), 200
    if prepress_trigger:
        _feishu_send_text_to_chat(chat_id, "收到，正在执行印前检查并生成逐项报告…")
        _feishu_submit_task(_async_run_prepress_check, chat_id)
        return jsonify({"msg": "ok"}), 200
    skill_cmd = _feishu_parse_skill_invocation(question)
    if skill_cmd.get("mode") == "list":
        _feishu_send_text_to_chat(chat_id, _feishu_render_skill_list())
        return jsonify({"msg": "ok"}), 200
    if skill_cmd.get("mode") == "invoke":
        sk_name = str(skill_cmd.get("skill") or "").strip()
        sk = _feishu_get_skill(sk_name)
        if not sk:
            _feishu_send_text_to_chat(chat_id, f"未找到技能：{sk_name}\n你可以先发送 /skills 查看可用技能。")
            return jsonify({"msg": "ok"}), 200
        skill_question = str(skill_cmd.get("question") or "").strip()
        if not skill_question:
            _feishu_send_text_to_chat(chat_id, f"技能 {sk_name} 已识别。请按格式提问：/skill {sk_name} 你的问题")
            return jsonify({"msg": "ok"}), 200
        _feishu_send_text_to_chat(chat_id, f"收到，已启用技能 {sk_name}，正在处理你的问题…")
        _feishu_submit_task(
            _async_generate_and_reply_with_skill,
            chat_id,
            skill_question,
            str(sk.get("name") or sk_name),
            str(sk.get("detail") or sk.get("description") or "")
        )
        return jsonify({"msg": "ok"}), 200

    ref_ids = _feishu_extract_reference_message_ids(message, content_obj)
    ref_texts = []
    for rid in ref_ids:
        if rid and rid != message_id:
            rt = _feishu_get_message_text(rid)
            rt = str(rt or "").strip()
            if rt:
                ref_texts.append(rt)
        if len(ref_texts) >= 3:
            break

    combined_text = "\n".join([str(user_text_for_memory or "").strip()] + ref_texts).strip()
    if combined_text:
        _feishu_remember_resources(chat_id, combined_text)

    bitable_url = _feishu_find_bitable_url(combined_text) or _feishu_find_bitable_url(question)
    if bitable_url:
        _feishu_send_text_to_chat(chat_id, "收到，我在读取多维表格并回答你的问题…")
        _feishu_submit_task(_async_generate_and_reply_bitable, chat_id, question, bitable_url)
        return jsonify({"msg": "ok"}), 200
    cloud_doc_url = _feishu_find_cloud_doc_url(combined_text) or _feishu_find_cloud_doc_url(question)
    if cloud_doc_url:
        kw = (question or "").strip()
        if (not kw) or any(k in kw for k in ["周报", "月报", "评分", "打分", "评估", "点评", "改进", "复盘"]):
            _feishu_send_text_to_chat(chat_id, "收到，我在读取云文档并总结+给建议…")
            _feishu_submit_task(_async_generate_and_reply_cloud_doc, chat_id, question, cloud_doc_url)
            return jsonify({"msg": "ok"}), 200
        _feishu_send_text_to_chat(chat_id, "收到，我在读取云文档并回答你的问题…")
        _feishu_submit_task(_async_generate_and_reply_cloud_doc_qa, chat_id, question, cloud_doc_url)
        return jsonify({"msg": "ok"}), 200

    prefer_type = ""
    kw = (question or "").strip()
    if any(k in kw for k in ["多维", "表格", "字段", "列", "行", "记录", "筛选", "视图", "base", "bitable"]):
        prefer_type = "bitable"
    elif any(k in kw for k in ["云文档", "文档", "周报", "月报", "wiki", "docx", "docs"]):
        prefer_type = "cloud_doc"
    elif any(k in kw for k in ["图片", "截图", "照片", "图里", "图中", "复述", "识别", "ocr"]):
        prefer_type = "image"

    last_resource = _feishu_get_last_resource(chat_id, prefer_type=prefer_type)
    if isinstance(last_resource, dict) and last_resource.get("url") and last_resource.get("type"):
        if last_resource.get("type") == "bitable":
            _feishu_send_text_to_chat(chat_id, "收到，我在读取你前面发过的多维表格并回答你的问题…")
            _feishu_submit_task(_async_generate_and_reply_bitable, chat_id, question, str(last_resource.get("url") or ""))
            return jsonify({"msg": "ok"}), 200
        if last_resource.get("type") == "cloud_doc":
            url = str(last_resource.get("url") or "")
            if (not kw) or any(k in kw for k in ["周报", "月报", "评分", "打分", "评估", "点评", "改进", "复盘"]):
                _feishu_send_text_to_chat(chat_id, "收到，我在读取你前面发过的云文档并总结+给建议…")
                _feishu_submit_task(_async_generate_and_reply_cloud_doc, chat_id, question, url)
                return jsonify({"msg": "ok"}), 200
            _feishu_send_text_to_chat(chat_id, "收到，我在读取你前面发过的云文档并回答你的问题…")
            _feishu_submit_task(_async_generate_and_reply_cloud_doc_qa, chat_id, question, url)
            return jsonify({"msg": "ok"}), 200
        if last_resource.get("type") == "image":
            key = str(last_resource.get("url") or "").strip()
            rt = str(last_resource.get("resource_type") or "image").strip().lower()
            mid = str(last_resource.get("message_id") or "").strip()
            fn = str(last_resource.get("file_name") or "").strip()
            if rt == "file":
                _feishu_send_text_to_chat(chat_id, "收到，我在识别你前面发过的图片…")
                _feishu_submit_task(_async_generate_and_reply_file, chat_id, question, mid, key, fn)
                return jsonify({"msg": "ok"}), 200
            _feishu_send_text_to_chat(chat_id, "收到，我在识别你前面发过的图片…")
            _feishu_submit_task(_async_generate_and_reply_image, chat_id, question, mid, key)
            return jsonify({"msg": "ok"}), 200
    if msg_type == "image":
        image_key = str(content_obj.get("image_key") or content_obj.get("imageKey") or "").strip()
        _feishu_send_text_to_chat(chat_id, "收到，我在识别图片…")
        _feishu_submit_task(_async_generate_and_reply_image, chat_id, question, message_id, image_key)
    elif msg_type == "file":
        file_key = str(content_obj.get("file_key") or content_obj.get("fileKey") or "").strip()
        file_name = str(content_obj.get("file_name") or content_obj.get("fileName") or "").strip()
        _feishu_send_text_to_chat(chat_id, "收到，我在读取文档…")
        _feishu_submit_task(_async_generate_and_reply_file, chat_id, question, message_id, file_key, file_name)
    else:
        _feishu_send_text_to_chat(chat_id, "收到，我在思考中…")
        _feishu_submit_task(_async_generate_and_reply, chat_id, question)
    return jsonify({"msg": "ok"}), 200



def _feishu_try_decrypt_callback_data(
    data,
    _safe_debug_print,
    json,
    permission_manager,
):
    if not isinstance(data, dict):
        return data
    if data.get("event") or data.get("type"):
        return data
    encrypted = data.get("encrypt")
    if not encrypted:
        return data
    try:
        decrypted_text = permission_manager.decrypt_feishu_data(encrypted)
        if isinstance(decrypted_text, str):
            decrypted_obj = json.loads(decrypted_text)
            if isinstance(decrypted_obj, dict):
                return decrypted_obj
        return data
    except Exception as e:
        _safe_debug_print(f"❌ 飞书回调解密失败: {e}")
        return data

