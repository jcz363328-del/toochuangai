"""Handle the Feishu assistant conversation and its task flow."""

from __future__ import annotations


def _feishu_is_message_processed(
    message_id,
    *,
    _feishu_processed_message_cache,
    _feishu_processed_message_ttl_seconds,
    datetime,
):
    if not message_id:
        return False
    now = datetime.now().timestamp()
    expired_keys = [k for k, v in _feishu_processed_message_cache.items() if (now - v) > _feishu_processed_message_ttl_seconds]
    for k in expired_keys:
        _feishu_processed_message_cache.pop(k, None)
    last = _feishu_processed_message_cache.get(message_id)
    return bool(last)


def _feishu_mark_message_processed(
    message_id,
    *,
    _feishu_processed_message_cache,
    datetime,
):
    if not message_id:
        return
    _feishu_processed_message_cache[message_id] = datetime.now().timestamp()


def _feishu_is_event_processed(
    event_id,
    *,
    _feishu_processed_event_cache,
    _feishu_processed_event_ttl_seconds,
    datetime,
):
    if not event_id:
        return False
    now = datetime.now().timestamp()
    expired_keys = [k for k, v in _feishu_processed_event_cache.items() if (now - v) > _feishu_processed_event_ttl_seconds]
    for k in expired_keys:
        _feishu_processed_event_cache.pop(k, None)
    last = _feishu_processed_event_cache.get(event_id)
    return bool(last)


def _feishu_mark_event_processed(
    event_id,
    *,
    _feishu_processed_event_cache,
    datetime,
):
    if not event_id:
        return
    _feishu_processed_event_cache[event_id] = datetime.now().timestamp()


def _feishu_memory_prune_locked(
    now_ts,
    *,
    _feishu_chat_memory,
    _feishu_chat_memory_ttl_seconds,
):
    expired = []
    for cid, item in (_feishu_chat_memory or {}).items():
        if not isinstance(item, dict):
            expired.append(cid)
            continue
        ts = item.get("ts")
        if not ts or (now_ts - float(ts)) > _feishu_chat_memory_ttl_seconds:
            expired.append(cid)
    for cid in expired:
        _feishu_chat_memory.pop(cid, None)


def _feishu_get_chat_history(
    chat_id,
    *,
    _feishu_chat_memory,
    _feishu_chat_memory_lock,
    _feishu_memory_prune_locked,
    datetime,
):
    cid = str(chat_id or "").strip()
    if not cid:
        return []
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid) or {}
        msgs = item.get("messages") or []
        if not isinstance(msgs, list):
            msgs = []
        return [{"role": m.get("role"), "content": m.get("content")} for m in msgs if isinstance(m, dict) and m.get("role") and m.get("content")]


def _feishu_clear_chat_history(
    chat_id,
    *,
    _feishu_chat_memory,
    _feishu_chat_memory_lock,
):
    cid = str(chat_id or "").strip()
    if not cid:
        return
    with _feishu_chat_memory_lock:
        _feishu_chat_memory.pop(cid, None)


def _feishu_extract_resources_from_text(
    text,
    *,
    _feishu_find_bitable_url,
    _feishu_find_cloud_doc_url_any,
):
    t = str(text or "").strip()
    if not t:
        return []
    out = []
    try:
        bitable_url = _feishu_find_bitable_url(t)
        if bitable_url:
            out.append({"type": "bitable", "url": bitable_url})
    except Exception:
        pass
    try:
        doc_url = _feishu_find_cloud_doc_url_any(t)
        if doc_url:
            out.append({"type": "cloud_doc", "url": doc_url})
    except Exception:
        pass
    return out


def _feishu_get_last_bot_ts(
    chat_id,
    *,
    _feishu_chat_memory,
    _feishu_chat_memory_lock,
    _feishu_memory_prune_locked,
    datetime,
):
    cid = str(chat_id or "").strip()
    if not cid:
        return 0.0
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid) or {}
        try:
            return float(item.get("last_bot_ts") or 0.0)
        except Exception:
            return 0.0


def _feishu_get_last_resource(
    chat_id,
    prefer_type,
    *,
    _feishu_chat_memory,
    _feishu_chat_memory_lock,
    _feishu_memory_prune_locked,
    datetime,
):
    cid = str(chat_id or "").strip()
    if not cid:
        return None
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid) or {}
        lst = item.get("resources") or []
        if not isinstance(lst, list) or not lst:
            return None
        if prefer_type:
            for r in reversed(lst):
                if isinstance(r, dict) and r.get("type") == prefer_type and r.get("url"):
                    return r
        for r in reversed(lst):
            if isinstance(r, dict) and r.get("url") and r.get("type"):
                return r
    return None


def _feishu_is_message_id(value):
    s = str(value or "").strip()
    if not s:
        return False
    if s.startswith("om_") or s.startswith("mid_") or s.startswith("msg_"):
        return True
    return False


def _feishu_is_group_message(chat_type):
    return str(chat_type or "").lower() in {"group", "chat"}


def _feishu_is_p2p_message(chat_type):
    return str(chat_type or "").lower() in {"p2p", "single"}


def _feishu_is_bot_mentioned(
    text,
    mentions,
    *,
    FEISHU_BOT_NAME,
):
    if isinstance(mentions, list):
        for m in mentions:
            name = str(m.get("name") or "").strip() if isinstance(m, dict) else ""
            if name and (FEISHU_BOT_NAME in name):
                return True
    return FEISHU_BOT_NAME in (text or "")


def _feishu_clean_question(
    text,
    *,
    FEISHU_BOT_NAME,
    re,
):
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace(f"@{FEISHU_BOT_NAME}", "").replace(FEISHU_BOT_NAME, "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _feishu_send_text_to_chat(
    chat_id,
    message_text,
    *,
    _feishu_recent_events,
    _feishu_recent_events_limit,
    _safe_debug_print,
    datetime,
    json,
    permission_manager,
):
    try:
        token = permission_manager.get_access_token()
        if not token:
            _safe_debug_print("❌ 发送飞书消息失败: access_token为空")
            return False
        import requests
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        payload = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": message_text}, ensure_ascii=False)
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=10).json()
        _safe_debug_print(f"飞书消息发送响应: {resp}")
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "send_result",
                "chat_id": chat_id,
                "ok": resp.get("code") == 0,
                "resp": resp,
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
        return resp.get("code") == 0
    except Exception as e:
        _safe_debug_print(f"❌ 发送飞书消息失败: {e}")
        return False


def _async_generate_and_reply(
    chat_id,
    question_text,
    *,
    _feishu_append_chat_history,
    _feishu_send_text_to_chat,
    _generate_ai_answer,
    _safe_debug_print,
):
    try:
        answer = _generate_ai_answer(question_text, chat_id=chat_id)
        _feishu_append_chat_history(chat_id, "user", question_text or "")
        _feishu_append_chat_history(chat_id, "assistant", answer or "")
        _feishu_send_text_to_chat(chat_id, answer)
    except Exception as e:
        _safe_debug_print(f"异步回复失败: {e}")
        try:
            _feishu_send_text_to_chat(chat_id, "我这边处理时发生异常，请稍后重试。")
        except Exception:
            pass


def _async_generate_and_reply_with_skill(
    chat_id,
    question_text,
    skill_name,
    skill_detail,
    *,
    _feishu_append_chat_history,
    _feishu_send_text_to_chat,
    _generate_ai_answer,
    _safe_debug_print,
):
    try:
        skill_prompt = (
            f"技能名：{skill_name}\n"
            f"请把下列技能文档作为本轮回答规则与操作手册，优先遵循并落地执行：\n{skill_detail}"
        )
        answer = _generate_ai_answer(question_text, chat_id=chat_id, extra_system_content=skill_prompt)
        _feishu_append_chat_history(chat_id, "user", question_text or "")
        _feishu_append_chat_history(chat_id, "assistant", answer or "")
        _feishu_send_text_to_chat(chat_id, answer)
    except Exception as e:
        _safe_debug_print(f"异步技能回复失败: {e}")
        try:
            _feishu_send_text_to_chat(chat_id, "我这边处理技能指令时发生异常，请稍后重试。")
        except Exception:
            pass


def _prepress_visual_review(
    render_path,
    chat_id,
    *,
    _generate_ai_answer_with_image,
):
    with open(render_path, "rb") as handle:
        image_bytes = handle.read()
    prompt = (
        "你是印前设计复核员。只根据这张高清渲染图观察并简洁列出："
        "文字/重要内容是否过近裁切线、烫银细线风险、包装盒开盖与封口/糊边方向、"
        "开窗安全距离、信息贴位、底卡旋转和圆角、信息贴白边。"
        "看不清或无法从平面图确定的项目必须写‘需人工确认’，禁止猜测。最多180字。"
    )
    return _generate_ai_answer_with_image(prompt, image_bytes, "image/png", chat_id=chat_id)


def _async_stage_prepress_resource(
    chat_id,
    message_id,
    resource_key,
    resource_type,
    file_name,
    run_after,
    *,
    _async_run_prepress_check,
    _feishu_download_resource,
    _feishu_send_text_to_chat,
    _safe_debug_print,
    prepress_check_service,
):
    try:
        blob, _mime = _feishu_download_resource(message_id, resource_key, resource_type)
        if not blob:
            _feishu_send_text_to_chat(chat_id, "印前文件下载失败，请重新发送后再试。")
            return
        staged = prepress_check_service.stage_file(chat_id, blob, file_name)
        if run_after:
            _async_run_prepress_check(chat_id)
            return
        _feishu_send_text_to_chat(
            chat_id,
            f"已收集印前文件：{staged['name']}（当前 {staged['count']} 个）。"
            "请继续发送 AI、PDF、截图；齐全后回复“检查印前合规”。"
        )
    except Exception as exc:
        _safe_debug_print(f"印前文件暂存失败: {exc}")
        _feishu_send_text_to_chat(chat_id, f"印前文件暂存失败：{exc}")


def _async_run_prepress_check(
    chat_id,
    *,
    _feishu_append_chat_history,
    _feishu_send_prepress_report,
    _feishu_send_text_to_chat,
    _prepress_visual_review,
    _safe_debug_print,
    prepress_check_service,
):
    try:
        result = prepress_check_service.run_check(
            chat_id,
            vision_reviewer=lambda path: _prepress_visual_review(path, chat_id),
        )
        report = str(result.get("report") or "")
        _feishu_append_chat_history(chat_id, "assistant", report[:12000])
        _feishu_send_prepress_report(chat_id, report)
    except Exception as exc:
        _safe_debug_print(f"印前检查失败: {exc}")
        _feishu_send_text_to_chat(chat_id, f"印前检查未完成：{exc}")


def _async_generate_and_reply_image(
    chat_id,
    question_text,
    message_id,
    image_key,
    *,
    _feishu_append_chat_history,
    _feishu_download_resource,
    _feishu_send_text_to_chat,
    _generate_ai_answer_with_image,
):
    prompt = (question_text or "").strip()
    if not prompt:
        prompt = "请识别图片里的文字/表格/关键信息，并用中文结构化输出。"
    img, mime = _feishu_download_resource(message_id, image_key, "image")
    if not img:
        _feishu_send_text_to_chat(chat_id, "我这边没能下载到图片内容，可能是权限或接口限制导致。")
        return
    answer = _generate_ai_answer_with_image(prompt, img, mime, chat_id=chat_id)
    _feishu_append_chat_history(chat_id, "user", prompt)
    _feishu_append_chat_history(chat_id, "assistant", answer or "")
    _feishu_send_text_to_chat(chat_id, answer)


def _async_generate_and_reply_cloud_doc_qa(
    chat_id,
    question_text,
    doc_url,
    *,
    _feishu_append_chat_history,
    _feishu_send_text_to_chat,
    _generate_ai_answer_with_cloud_doc_url,
):
    prompt = (question_text or "").strip()
    answer = _generate_ai_answer_with_cloud_doc_url(prompt, doc_url, chat_id=chat_id)
    _feishu_append_chat_history(chat_id, "user", (prompt or "").strip() or f"云文档问答：{doc_url}")
    _feishu_append_chat_history(chat_id, "assistant", answer or "")
    _feishu_send_text_to_chat(chat_id, answer)


def _async_generate_and_reply_bitable(
    chat_id,
    question_text,
    bitable_url,
    *,
    _feishu_append_chat_history,
    _feishu_send_text_to_chat,
    _generate_ai_answer_with_bitable_url,
):
    prompt = (question_text or "").strip()
    answer = _generate_ai_answer_with_bitable_url(prompt, bitable_url, chat_id=chat_id)
    _feishu_append_chat_history(chat_id, "user", (prompt or "").strip() or f"多维表格问答：{bitable_url}")
    _feishu_append_chat_history(chat_id, "assistant", answer or "")
    _feishu_send_text_to_chat(chat_id, answer)


def _async_generate_and_reply_cloud_doc(
    chat_id,
    prompt_text,
    doc_url,
    *,
    _feishu_append_chat_history,
    _feishu_plain_textify,
    _feishu_send_text_to_chat,
    _forward_text_to_departments,
    _generate_cloud_doc_analysis,
    _parse_forward_departments,
):
    content = _generate_cloud_doc_analysis(prompt_text, doc_url, chat_id=chat_id)
    content = _feishu_plain_textify(content)
    _feishu_append_chat_history(chat_id, "user", (prompt_text or "").strip() or f"周报/月报分析：{doc_url}")
    _feishu_append_chat_history(chat_id, "assistant", content or "")
    _feishu_send_text_to_chat(chat_id, content or "我这边没有生成出有效的分析结果，请稍后再试。")

    forward_deps = _parse_forward_departments(prompt_text)
    if forward_deps and content:
        header = f"周报/月报总结与建议（自动生成）\n来源：{doc_url}\n\n"
        msg = (header + content).strip()
        stats = _forward_text_to_departments(forward_deps, msg)
        ok_total = int(stats.get("success") or 0)
        fail_total = int(stats.get("failed") or 0)
        _feishu_send_text_to_chat(chat_id, f"已同步给：{'、'.join(forward_deps)}（成功{ok_total}，失败{fail_total}）")
