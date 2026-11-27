"""Feishu assistant answers, document analysis and OCR."""

from __future__ import annotations


def _generate_ai_answer_with_doc(
    prompt_text,
    doc_text,
    doc_name,
    chat_id,
    *,
    _OPENAI_TEXT_MODEL_CANDIDATES,
    _ai_chat_complete,
    _feishu_get_chat_history,
    _safe_debug_print,
):
    q = (prompt_text or "").strip()
    if not q:
        q = f"请阅读文档《{doc_name}》并提炼关键信息，给出结构化总结。".strip("《》")
    content = (doc_text or "").strip()
    if not content:
        return "我没有解析出文档内容。请换成可复制文字的文档（txt/docx/xlsx），或把关键内容粘贴到消息里。"

    clipped = content[:60000]
    user_content = f"用户问题：{q}\n\n文档《{doc_name or '未知文件'}》内容如下（可能已截断）：\n{clipped}"
    system_content = "你是图创AI，是公司内部的飞书智能助手。请用中文回答，严格基于用户提供的文档内容作答，不要编造文档里不存在的信息。若文档内容不足以支撑结论，先说明缺少的信息。"
    history = _feishu_get_chat_history(chat_id) if chat_id else []

    try:
        messages = [{"role": "system", "content": system_content}, *history, {"role": "user", "content": user_content}]
        return _ai_chat_complete(messages, max_tokens=900, temperature=0.2, model_candidates=_OPENAI_TEXT_MODEL_CANDIDATES)
    except Exception as e:
        _safe_debug_print(f"AI回复生成失败(文档模式): {e}")
        return "我这边文档识别后的回答生成失败了，请稍后再试。"


def _generate_ai_answer_with_image(
    prompt_text,
    image_bytes,
    image_mime,
    chat_id,
    *,
    _OPENAI_VISION_MODEL_CANDIDATES,
    _ai_chat_complete,
    _feishu_get_chat_history,
    _safe_debug_print,
    base64,
):
    q = (prompt_text or "").strip()
    if not q:
        q = "请识别图片里的文字/表格/关键信息，并用中文结构化输出。"
    if not image_bytes:
        return "我没有拿到图片数据。"

    mime = (image_mime or "").split(";", 1)[0].strip().lower()
    if not mime.startswith("image/"):
        mime = "image/png"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    system_content = "你是图创AI，是公司内部的飞书智能助手。请用中文回答。先识别图片内容，再根据用户问题给出结论与可执行建议。不要臆测看不清的内容。"
    history = _feishu_get_chat_history(chat_id) if chat_id else []
    messages = [{"role": "system", "content": system_content}] + history + [{
        "role": "user",
        "content": [
            {"type": "text", "text": q},
            {"type": "image_url", "image_url": {"url": data_url}}
        ]
    }]

    last_err = None
    try:
        return _ai_chat_complete(messages, max_tokens=900, temperature=0.2, model_candidates=_OPENAI_VISION_MODEL_CANDIDATES)
    except Exception as e:
        last_err = e

    _safe_debug_print(f"AI回复生成失败(图片模式): {last_err}")
    return "我这边暂时无法识别图片（当前模型/接口可能不支持多模态）。你可以把图片里的关键文字粘贴出来，我再继续处理。"


def _ocr_images_bytes_with_ai(
    images,
    *,
    _OPENAI_VISION_MODEL_CANDIDATES,
    _ai_chat_complete,
    _safe_debug_print,
    base64,
):
    if not images:
        return ""

    def _to_data_url(image_bytes, image_mime=""):
        mime = (image_mime or "").split(";", 1)[0].strip().lower()
        if not mime.startswith("image/"):
            mime = "image/png"
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mime};base64,{b64}"

    normalized = []
    if isinstance(images, (bytes, bytearray)):
        normalized = [(bytes(images), "image/png")]
    elif isinstance(images, (list, tuple)):
        for it in images:
            if isinstance(it, dict):
                b = it.get("bytes") or it.get("data") or b""
                m = it.get("mime") or it.get("content_type") or ""
                if b:
                    normalized.append((b, m))
                continue
            if isinstance(it, (list, tuple)) and it:
                b = it[0]
                m = it[1] if len(it) > 1 else ""
                if b:
                    normalized.append((b, m))

    if not normalized:
        return ""

    system_content = (
        "你是OCR引擎。你的任务是从图片中提取可读文字并原样输出。\n"
        "要求：\n"
        "1) 只输出识别到的文字内容，不要总结、不要解释、不要补充推测。\n"
        "2) 识别到表格时用Markdown表格输出；识别到标题/列表时尽量保持原结构。\n"
        "3) 对看不清/缺失的部分用“[无法识别]”标注，不要编造。\n"
        "4) 按下面固定格式输出，每张图片一段：\n"
        "【图片1】\\n...\\n\\n【图片2】\\n...（依次类推）"
    )

    model_candidates = ["Qwen/Qwen2.5-VL-7B-Instruct", "zai-org/GLM-4.5V"] + list(_OPENAI_VISION_MODEL_CANDIDATES or [])
    seen = set()
    model_candidates = [m for m in model_candidates if m and not (m in seen or seen.add(m))]
    out_parts = []
    for base_idx in range(0, len(normalized), 4):
        batch = normalized[base_idx:base_idx + 4]
        content = [{"type": "text", "text": "请分别对下面每张图片做OCR，并按指定格式输出。"}]
        for b, m in batch:
            try:
                url = _to_data_url(b, m)
            except Exception:
                continue
            content.append({"type": "image_url", "image_url": {"url": url}})
        messages = [{"role": "system", "content": system_content}, {"role": "user", "content": content}]

        try:
            t = _ai_chat_complete(messages, max_tokens=1600, temperature=0.0, model_candidates=model_candidates)
        except Exception as e:
            _safe_debug_print(f"OCR失败: {e}")
            t = ""
            fallback = []
            for i, (b, m) in enumerate(batch, start=1):
                url = _to_data_url(b, m)
                one = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": [{"type": "text", "text": f"请对这张图片做OCR，只输出识别结果。\\n【图片{i}】"}, {"type": "image_url", "image_url": {"url": url}}]},
                ]
                try:
                    one_text = _ai_chat_complete(one, max_tokens=900, temperature=0.0, model_candidates=model_candidates)
                except Exception:
                    one_text = ""
                one_text = (one_text or "").strip()
                if one_text:
                    fallback.append(one_text)
            if fallback:
                t = "\n\n".join(fallback).strip()

        t = (t or "").strip()
        if t:
            out_parts.append(t)
    return "\n\n".join(out_parts).strip()


def _merge_system_content(base_system, extra_system):
    b = str(base_system or "").strip()
    e = str(extra_system or "").strip()
    if not e:
        return b
    if not b:
        return e
    return f"{b}\n\n你还需要遵循以下技能说明：\n{e}"


def _generate_ai_answer(
    question_text,
    chat_id,
    extra_system_content,
    *,
    _GOOGLE_CSE_API_KEY,
    _GOOGLE_CSE_CX,
    _OPENAI_TEXT_MODEL_CANDIDATES,
    _TAVILY_API_KEY,
    _ai_chat_complete,
    _feishu_get_chat_history,
    _merge_system_content,
    _safe_debug_print,
    os,
    requests,
):
    def _normalize_web_search_trigger(text):
        t = (text or "").strip()
        lowered = t.lower()
        triggers = ["联网:", "联网：", "实时搜索:", "实时搜索：", "实时检索:", "实时检索：", "web:", "search:"]
        for p in triggers:
            if lowered.startswith(p):
                return t[len(p):].strip(), True
        if "联网搜索" in t or "实时搜索" in t or "联网查" in t:
            return t.replace("联网搜索", "").replace("实时搜索", "").replace("联网查", "").strip(), True
        return t, False

    def _should_web_search_by_keywords(text):
        t = (text or "").strip().lower()
        if not t:
            return False
        keywords = [
            "最新", "今天", "现在", "本周", "本月", "今年", "昨日", "近期",
            "新闻", "公告", "发布", "更新", "版本",
            "官网", "下载", "价格", "对比", "政策", "法规", "通知",
            "天气", "气温", "温度", "预报", "台风", "降雨", "雨量", "风力", "湿度", "空气质量", "pm2.5",
        ]
        return any(k in t for k in keywords)

    def _google_cse_search(query, max_results=5):
        api_key = (os.environ.get("GOOGLE_CSE_API_KEY") or _GOOGLE_CSE_API_KEY or "").strip()
        cx = (os.environ.get("GOOGLE_CSE_CX") or _GOOGLE_CSE_CX or "").strip()
        if not api_key or not cx:
            return [], "未配置GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX"
        q2 = (query or "").strip()
        if not q2:
            return [], "查询为空"
        try:
            num = int(max_results or 5)
            num = max(1, min(num, 10))
        except Exception:
            num = 5
        try:
            resp = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": api_key,
                    "cx": cx,
                    "q": q2[:400],
                    "num": num,
                    "safe": "active",
                },
                timeout=20,
            )
            if resp.status_code != 200:
                try:
                    detail = (resp.text or "").strip()
                except Exception:
                    detail = ""
                detail = detail[:300].strip() if detail else ""
                return [], f"Google CSE返回状态码{resp.status_code}{('，响应：' + detail) if detail else ''}"
            payload = resp.json() if resp.content else {}
            items = payload.get("items") or []
            if not isinstance(items, list):
                return [], "Google CSE响应格式异常(items不是list)"
            normalized = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                url = str(it.get("link") or "").strip()
                title = str(it.get("title") or "").strip()
                content = str(it.get("snippet") or "").strip()
                if not url and not content:
                    continue
                normalized.append({"url": url, "title": title, "content": content})
            if not normalized:
                return [], "Google CSE未返回有效结果"
            return normalized, ""
        except Exception as e:
            return [], f"Google CSE请求失败: {type(e).__name__}: {str(e)[:200]}"

    def _tavily_search(query, max_results=5, search_depth="basic"):
        api_key = (os.environ.get("TAVILY_API_KEY") or _TAVILY_API_KEY or "").strip()
        if not api_key:
            return [], "未配置TAVILY_API_KEY"
        q2 = (query or "").strip()
        if not q2:
            return [], "查询为空"
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": q2[:400],
                    "search_depth": search_depth,
                    "max_results": int(max_results or 5),
                    "include_answer": False,
                    "include_raw_content": False,
                    "include_images": False,
                },
                timeout=20,
            )
            if resp.status_code != 200:
                try:
                    detail = (resp.text or "").strip()
                except Exception:
                    detail = ""
                detail = detail[:300].strip() if detail else ""
                return [], f"Tavily返回状态码{resp.status_code}{('，响应：' + detail) if detail else ''}"
            payload = resp.json() if resp.content else {}
            results = payload.get("results") or []
            if not isinstance(results, list):
                return [], "Tavily响应格式异常(results不是list)"
            normalized = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                url = str(r.get("url") or "").strip()
                title = str(r.get("title") or "").strip()
                content = str(r.get("content") or "").strip()
                if not url and not content:
                    continue
                normalized.append({"url": url, "title": title, "content": content})
            if not normalized:
                return [], "Tavily未返回有效结果"
            return normalized, ""
        except Exception as e:
            return [], f"Tavily请求失败: {type(e).__name__}: {str(e)[:200]}"

    def _format_web_results(results, limit_chars=8000):
        parts = []
        for i, r in enumerate(results or [], start=1):
            if not isinstance(r, dict):
                continue
            title = (r.get("title") or "").strip()
            url = (r.get("url") or "").strip()
            content = (r.get("content") or "").strip()
            block = f"【联网结果{i}】\n标题：{title or '（无标题）'}\n链接：{url or '（无链接）'}\n摘要：{content}"
            parts.append(block)
            if sum(len(x) for x in parts) >= int(limit_chars or 0):
                break
        out = "\n\n".join(parts).strip()
        return out[: int(limit_chars or 0)].strip() if limit_chars else out

    q_raw = (question_text or "").strip()
    q, force_web_search = _normalize_web_search_trigger(q_raw)
    if not q:
        return f"我在。请直接描述你的问题，我会尽量给出可执行的答案。"

    history = _feishu_get_chat_history(chat_id) if chat_id else []

    web_results = []
    web_error = ""
    need_web_by_keyword = _should_web_search_by_keywords(q)
    _safe_debug_print(
        f"联网检索触发 chat_id={chat_id or ''} force={force_web_search} keyword={need_web_by_keyword} "
        f"google_key={bool((os.environ.get('GOOGLE_CSE_API_KEY') or _GOOGLE_CSE_API_KEY).strip())} "
        f"google_cx={bool((os.environ.get('GOOGLE_CSE_CX') or _GOOGLE_CSE_CX).strip())} "
        f"tavily_key={bool((os.environ.get('TAVILY_API_KEY') or _TAVILY_API_KEY).strip())}"
    )
    web_results, google_error = _google_cse_search(q, max_results=5)
    web_error = google_error or ""
    if web_error:
        _safe_debug_print(f"Google检索失败: {web_error}")
    if not web_results:
        web_results, tavily_error = _tavily_search(q, max_results=5, search_depth="basic")
        tavily_error = tavily_error or ""
        if tavily_error:
            _safe_debug_print(f"Tavily检索失败: {tavily_error}")
        if (not web_results) and (web_error and tavily_error):
            web_error = f"{web_error}；备选Tavily：{tavily_error}"
        elif not web_results:
            web_error = tavily_error or web_error
    else:
        _safe_debug_print(f"Google检索成功: results={len(web_results)}")
    web_context = _format_web_results(web_results, limit_chars=8000) if web_results else ""
    if force_web_search and (not web_context):
        return (
            f"我这边没有联网检索到结果。原因：{web_error or '未知错误'}。"
            f"请检查服务进程是否已设置环境变量 GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX（优先），或 TAVILY_API_KEY（备选），"
            f"并确认服务器可访问 Google Custom Search API / https://api.tavily.com 。"
            f"（PowerShell 里要用：$env:GOOGLE_CSE_API_KEY='...' / $env:GOOGLE_CSE_CX='...'，不要用 set）"
        )
    if need_web_by_keyword and (not web_context):
        return (
            f"这个问题看起来需要实时信息，但我这边联网检索失败了。原因：{web_error or '未知错误'}。"
            f"请确认服务进程已注入环境变量 GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX（优先），或 TAVILY_API_KEY（备选），"
            f"并确认服务器出网可访问对应接口。"
            f"（PowerShell 里要用：$env:GOOGLE_CSE_API_KEY='...' / $env:GOOGLE_CSE_CX='...'，不要用 set）"
        )

    try:
        system_content = "你是图创AI，是公司内部的飞书智能助手。请用中文回答，给出清晰可执行的步骤或结论。"
        user_content = q
        if web_context:
            system_content = (
                "你是图创AI，是公司内部的飞书智能助手。请用中文回答。\n"
                "你可以使用下面提供的联网检索结果，但必须严格基于来源内容作答，不要编造。\n"
                "在使用某条联网信息时，请在该句末尾用“(来源: URL)”标注链接。"
            )
            user_content = f"问题：{q}\n\n联网检索结果如下：\n{web_context}"
        system_content = _merge_system_content(system_content, extra_system_content)
        messages = [{"role": "system", "content": system_content}, *history, {"role": "user", "content": user_content}]
        content = _ai_chat_complete(messages, max_tokens=800, temperature=0.4, model_candidates=_OPENAI_TEXT_MODEL_CANDIDATES)
        return content or "我暂时没生成出有效答案，请换一种问法再试一次。"
    except Exception as e:
        _safe_debug_print(f"AI回复生成失败: {e}")
        return "我这边生成回复失败了，请稍后再试。"


def _generate_ai_answer_with_cloud_doc_url(
    question_text,
    doc_url,
    chat_id,
    *,
    _generate_ai_answer_with_doc,
    _get_cloud_documents_agent,
):
    agent = _get_cloud_documents_agent()
    if agent is None:
        return "云文档模块未加载成功。"
    doc_text, err = agent.fetch_document_text(doc_url, include_images_ocr=True)
    if err:
        return err
    q = (question_text or "").strip()
    if not q:
        q = "请阅读该云文档并回答我的问题。"
    return _generate_ai_answer_with_doc(q, doc_text, doc_name="飞书云文档", chat_id=chat_id)


def _generate_cloud_doc_scoring(
    prompt_text,
    doc_url,
    *,
    _OPENAI_TEXT_MODEL_CANDIDATES,
    _ai_chat_complete,
    _cloud_doc_scoring_cache,
    _cloud_doc_scoring_cache_lock,
    _cloud_doc_scoring_cache_ttl_seconds,
    _get_cloud_documents_agent,
    datetime,
):
    agent = _get_cloud_documents_agent()
    if agent is None:
        return "", "云文档评分模块未加载成功，请检查服务器文件是否存在：cloud_documents.py"
    prompt_norm = str(prompt_text or "").strip()
    cache_key = f"{str(doc_url or '').strip()}|{prompt_norm}"
    now_ts = datetime.now().timestamp()
    with _cloud_doc_scoring_cache_lock:
        expired = [k for k, v in _cloud_doc_scoring_cache.items() if not isinstance(v, dict) or (now_ts - float(v.get("ts") or 0)) > _cloud_doc_scoring_cache_ttl_seconds]
        for k in expired:
            _cloud_doc_scoring_cache.pop(k, None)
        cached = _cloud_doc_scoring_cache.get(cache_key)
        if isinstance(cached, dict) and cached.get("text"):
            return str(cached.get("text") or "").strip(), ""

    doc_text, err = agent.fetch_document_text(doc_url, include_images_ocr=True)
    if err:
        return "", err
    messages = agent.build_scoring_messages(doc_text, prompt_text or "")
    try:
        scoring_model_candidates = ["Pro/moonshotai/Kimi-K2.6", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B"] + list(_OPENAI_TEXT_MODEL_CANDIDATES or [])
        seen = set()
        scoring_model_candidates = [m for m in scoring_model_candidates if m and not (m in seen or seen.add(m))]
        content = _ai_chat_complete(
            messages,
            max_tokens=1500,
            temperature=0.2,
            model_candidates=scoring_model_candidates
        )
    except Exception:
        return "", "我这边生成评分报告失败了，请稍后再试。"
    text = (content or "").strip()
    if text:
        with _cloud_doc_scoring_cache_lock:
            _cloud_doc_scoring_cache[cache_key] = {"ts": now_ts, "text": text}
    return text, ""


def _generate_cloud_doc_analysis(
    prompt_text,
    doc_url,
    chat_id,
    *,
    _generate_ai_answer_with_cloud_doc_url,
):
    q = (prompt_text or "").strip()
    if not q:
        q = (
            "请阅读这份周报/月报，只输出“总结+建议”，不需要评分/打分/等级。\n"
            "输出要求：纯文本，不要使用Markdown格式，不要出现#或*等标记符号。\n"
            "输出结构：\n"
            "一、要点总结（目标-产出-数据-问题-计划）\n"
            "二、改进建议（给具体写法）\n"
            "三、下一步行动清单（按优先级排序）"
        )
    else:
        q = (
            "请阅读这份周报/月报，只输出“总结+建议”，不需要评分/打分/等级。\n"
            "输出要求：纯文本，不要使用Markdown格式，不要出现#或*等标记符号。\n"
            "输出结构：\n"
            "一、要点总结（目标-产出-数据-问题-计划）\n"
            "二、改进建议（给具体写法）\n"
            "三、下一步行动清单（按优先级排序）\n\n"
            f"【用户补充问题】\n{q}"
        )
    return _generate_ai_answer_with_cloud_doc_url(q, doc_url, chat_id=chat_id)
