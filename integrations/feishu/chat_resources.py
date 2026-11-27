"""Manage Feishu conversation history, referenced content and attachments."""

from __future__ import annotations

from .attachment_text import extract_attachment_text


def _feishu_append_chat_history(
    chat_id,
    role,
    content,
    *,
    _feishu_chat_memory,
    _feishu_chat_memory_lock,
    _feishu_chat_memory_max_messages,
    _feishu_extract_resources_from_text,
    _feishu_memory_prune_locked,
    datetime,
):
    cid = str(chat_id or "").strip()
    if not cid:
        return
    r = str(role or "").strip()
    c = (content or "").strip()
    if not r or not c:
        return
    resources = _feishu_extract_resources_from_text(c)
    if len(c) > 1200:
        c = c[:1200].strip()
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid)
        if not isinstance(item, dict):
            item = {"ts": now_ts, "messages": [], "resources": []}
        msgs = item.get("messages")
        if not isinstance(msgs, list):
            msgs = []
        msgs.append({"role": r, "content": c})
        if len(msgs) > _feishu_chat_memory_max_messages:
            msgs = msgs[-_feishu_chat_memory_max_messages:]
        if resources:
            lst = item.get("resources")
            if not isinstance(lst, list):
                lst = []
            seen = {str((x or {}).get("url") or "").strip() for x in lst if isinstance(x, dict)}
            for rr in resources:
                u = str((rr or {}).get("url") or "").strip()
                if not u or u in seen:
                    continue
                seen.add(u)
                lst.append({"type": rr.get("type"), "url": u, "ts": now_ts})
            if len(lst) > 20:
                lst = lst[-20:]
            item["resources"] = lst
        if r == "assistant":
            item["last_bot_ts"] = now_ts
        item["ts"] = now_ts
        item["messages"] = msgs
        _feishu_chat_memory[cid] = item


def _feishu_remember_resources(
    chat_id,
    text,
    *,
    _feishu_chat_memory,
    _feishu_chat_memory_lock,
    _feishu_extract_resources_from_text,
    _feishu_memory_prune_locked,
    datetime,
):
    cid = str(chat_id or "").strip()
    if not cid:
        return
    resources = _feishu_extract_resources_from_text(text)
    if not resources:
        return
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid)
        if not isinstance(item, dict):
            item = {"ts": now_ts, "messages": [], "resources": []}
        lst = item.get("resources")
        if not isinstance(lst, list):
            lst = []
        seen = {str((r or {}).get("url") or "").strip() for r in lst if isinstance(r, dict)}
        for r in resources:
            u = str((r or {}).get("url") or "").strip()
            if not u or u in seen:
                continue
            seen.add(u)
            lst.append({"type": r.get("type"), "url": u, "ts": now_ts})
        if len(lst) > 20:
            lst = lst[-20:]
        item["resources"] = lst
        item["ts"] = now_ts
        _feishu_chat_memory[cid] = item


def _feishu_remember_image_resource(
    chat_id,
    key,
    message_id,
    resource_type,
    file_name,
    *,
    _feishu_chat_memory,
    _feishu_chat_memory_lock,
    _feishu_memory_prune_locked,
    datetime,
):
    cid = str(chat_id or "").strip()
    k = str(key or "").strip()
    if not cid or not k:
        return
    rt = str(resource_type or "").strip().lower() or "image"
    mid = str(message_id or "").strip()
    fn = str(file_name or "").strip()
    now_ts = datetime.now().timestamp()
    with _feishu_chat_memory_lock:
        _feishu_memory_prune_locked(now_ts)
        item = _feishu_chat_memory.get(cid)
        if not isinstance(item, dict):
            item = {"ts": now_ts, "messages": [], "resources": []}
        lst = item.get("resources")
        if not isinstance(lst, list):
            lst = []
        seen = {str((r or {}).get("url") or "").strip() for r in lst if isinstance(r, dict)}
        if k not in seen:
            lst.append({"type": "image", "url": k, "ts": now_ts, "message_id": mid, "resource_type": rt, "file_name": fn})
        if len(lst) > 20:
            lst = lst[-20:]
        item["resources"] = lst
        item["ts"] = now_ts
        _feishu_chat_memory[cid] = item


def _feishu_extract_reference_message_ids(
    message_obj,
    content_obj,
    *,
    _feishu_is_message_id,
):
    msg = message_obj if isinstance(message_obj, dict) else {}
    cont = content_obj if isinstance(content_obj, dict) else {}
    keys = {
        "parent_id", "parent_message_id", "root_id", "root_message_id",
        "quote_message_id", "quoted_message_id", "reference_message_id", "referenced_message_id"
    }
    out = []
    seen = set()

    def add(v):
        s = str(v or "").strip()
        if not s or not _feishu_is_message_id(s):
            return
        if s in seen:
            return
        seen.add(s)
        out.append(s)

    for k in keys:
        add(msg.get(k))
        add(cont.get(k))

    def walk(x):
        if x is None:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                lk = str(k or "").strip().lower()
                if lk in keys:
                    add(v)
                walk(v)
            return
        if isinstance(x, list):
            for it in x:
                walk(it)
            return

    walk(msg)
    walk(cont)
    return out


def _feishu_get_message_text(
    message_id,
    *,
    _feishu_extract_text_from_content,
    _feishu_http,
    _feishu_message_text_cache,
    _feishu_message_text_cache_lock,
    _feishu_message_text_cache_ttl_seconds,
    datetime,
    permission_manager,
):
    mid = str(message_id or "").strip()
    if not mid:
        return ""
    now_ts = datetime.now().timestamp()
    with _feishu_message_text_cache_lock:
        expired = [k for k, v in (_feishu_message_text_cache or {}).items() if not isinstance(v, dict) or (now_ts - float(v.get("ts") or 0)) > _feishu_message_text_cache_ttl_seconds]
        for k in expired:
            _feishu_message_text_cache.pop(k, None)
        cached = _feishu_message_text_cache.get(mid)
        if isinstance(cached, dict) and cached.get("text"):
            return str(cached.get("text") or "")

    token = permission_manager.get_access_token() if hasattr(permission_manager, "get_access_token") else ""
    token = str(token or "").strip()
    if not token:
        return ""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}"
    try:
        resp = _feishu_http.get(url, headers=headers, timeout=12)
        data = resp.json() if resp is not None else None
    except Exception:
        data = None
    if not isinstance(data, dict) or int(data.get("code") or 0) != 0:
        return ""
    d = data.get("data") or {}
    msg = (d.get("message") if isinstance(d, dict) else None) or (d.get("items") or [None])[0]
    body = (msg or {}).get("body") if isinstance(msg, dict) else None
    content = ""
    if isinstance(body, dict) and body.get("content") is not None:
        content = body.get("content")
    elif isinstance(msg, dict) and msg.get("content") is not None:
        content = msg.get("content")
    elif isinstance(msg, dict) and msg.get("body") is not None:
        try:
            content = (msg.get("body") or {}).get("content")
        except Exception:
            content = ""
    text = _feishu_extract_text_from_content(content)
    text = str(text or "").strip()
    if text:
        with _feishu_message_text_cache_lock:
            _feishu_message_text_cache[mid] = {"ts": now_ts, "text": text}
    return text


def _feishu_extract_text_from_content(
    content,
    *,
    _feishu_extract_text_from_content,
    json,
):
    if not content:
        return ""
    if isinstance(content, dict):
        if "text" in content:
            return str(content.get("text") or "").strip()
        if "zh_cn" in content:
            try:
                blocks = content.get("zh_cn", {}).get("content") or []
                parts = []
                for block in blocks:
                    if not isinstance(block, list):
                        continue
                    for el in block:
                        if not isinstance(el, dict):
                            continue
                        if el.get("tag") == "text" and el.get("text"):
                            parts.append(str(el.get("text")))
                        elif el.get("tag") == "at" and el.get("user_name"):
                            parts.append(f"@{el.get('user_name')}")
                return " ".join([p for p in parts if str(p).strip()]).strip()
            except Exception:
                return ""
        return ""
    if isinstance(content, str):
        try:
            payload = json.loads(content)
            if isinstance(payload, dict):
                if "text" in payload:
                    return str(payload.get("text") or "").strip()
                if "zh_cn" in payload:
                    return _feishu_extract_text_from_content(payload)
        except Exception:
            return str(content).strip()
    return str(content).strip()


def _split_text(text, max_len):
    t = str(text or "")
    if not t:
        return []
    if len(t) <= max_len:
        return [t]
    parts = []
    buf = []
    buf_len = 0
    for line in t.splitlines(True):
        if not line:
            continue
        if len(line) > max_len:
            if buf:
                parts.append("".join(buf).strip())
                buf = []
                buf_len = 0
            for i in range(0, len(line), max_len):
                chunk = line[i:i + max_len].strip()
                if chunk:
                    parts.append(chunk)
            continue
        if buf_len + len(line) > max_len and buf:
            parts.append("".join(buf).strip())
            buf = [line]
            buf_len = len(line)
        else:
            buf.append(line)
            buf_len += len(line)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _async_generate_and_reply_file(
    chat_id,
    question_text,
    message_id,
    file_key,
    file_name,
    *,
    _feishu_append_chat_history,
    _feishu_download_resource,
    _feishu_send_text_to_chat,
    _generate_ai_answer_with_doc,
    _generate_ai_answer_with_image,
):
    prompt = (question_text or "").strip()
    if not prompt:
        prompt = f"请阅读文档《{file_name or '文件'}》并提炼关键信息，给出结构化总结。"
    blob, mime = _feishu_download_resource(message_id, file_key, "file")
    if not blob:
        _feishu_send_text_to_chat(chat_id, "我这边没能下载到文档内容，可能是权限或接口限制导致。")
        return
    mime_norm = (mime or "").split(";", 1)[0].strip().lower()
    fname = (file_name or "").strip().lower()
    is_image_file = mime_norm.startswith("image/") or any(fname.endswith(s) for s in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"])
    if is_image_file:
        if (question_text or "").strip() == "":
            prompt = "请识别图片里的文字/表格/关键信息，并用中文结构化输出。"
        answer = _generate_ai_answer_with_image(prompt, blob, mime_norm or "image/png", chat_id=chat_id)
        _feishu_append_chat_history(chat_id, "user", prompt)
        _feishu_append_chat_history(chat_id, "assistant", answer or "")
        _feishu_send_text_to_chat(chat_id, answer)
        return
    extracted = extract_attachment_text(blob, file_name or "")
    if not extracted:
        _feishu_send_text_to_chat(chat_id, "我拿到了文档，但暂时无法解析内容。当前支持 txt/docx/xlsx（pdf需要额外解析能力）。")
        return
    answer = _generate_ai_answer_with_doc(prompt, extracted, doc_name=file_name or "", chat_id=chat_id)
    _feishu_append_chat_history(chat_id, "user", prompt)
    _feishu_append_chat_history(chat_id, "assistant", answer or "")
    _feishu_send_text_to_chat(chat_id, answer)
