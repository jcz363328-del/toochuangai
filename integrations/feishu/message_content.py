"""Message content and attachment handling for Feishu events."""

from __future__ import annotations


def _feishu_parse_message_content(
    content,
    *,
    json,
):
    if content is None:
        return {}
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            obj = json.loads(content)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _feishu_extract_image_keys(obj, limit):
    keys = []
    seen = set()

    def walk(x):
        if x is None or len(keys) >= int(limit or 0):
            return
        if isinstance(x, dict):
            for k, v in x.items():
                if len(keys) >= int(limit or 0):
                    return
                lk = str(k or "").strip().lower()
                if lk in {"image_key", "imagekey"} and isinstance(v, str):
                    s = v.strip()
                    if s and s not in seen:
                        seen.add(s)
                        keys.append(s)
                        if len(keys) >= int(limit or 0):
                            return
                walk(v)
            return
        if isinstance(x, list):
            for it in x:
                walk(it)
                if len(keys) >= int(limit or 0):
                    return
            return

    walk(obj)
    return keys


def _feishu_download_resource(
    message_id,
    file_key,
    resource_type,
    *,
    permission_manager,
):
    file_key = (file_key or "").strip()
    resource_type = (resource_type or "").strip()
    if not file_key:
        return None, ""

    token = permission_manager.get_access_token()
    if not token:
        return None, ""

    import requests
    headers = {"Authorization": f"Bearer {token}"}
    urls = []
    if message_id and resource_type:
        urls.append(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}?type={resource_type}"
        )
    if resource_type == "image":
        urls.append(f"https://open.feishu.cn/open-apis/im/v1/images/{file_key}?type=message")
        urls.append(f"https://open.feishu.cn/open-apis/im/v1/images/{file_key}?image_type=message")

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200 and resp.content:
                return resp.content, str(resp.headers.get("Content-Type") or "")
        except Exception:
            continue
    return None, ""


def _feishu_find_cloud_doc_url(
    text,
    *,
    _get_cloud_documents_agent,
):
    agent = _get_cloud_documents_agent()
    if agent is None:
        return ""
    urls = agent.extract_urls(text or "")
    for u in urls:
        lu = u.lower()
        if ("feishu" in lu or "larksuite" in lu) and ("/docx/" in lu or "/docs/" in lu or "/wiki/" in lu or "doxcn" in lu):
            return u
    return ""


def _feishu_find_cloud_doc_url_any(
    text,
    *,
    _get_cloud_documents_agent,
):
    agent = _get_cloud_documents_agent()
    if agent is None:
        return ""
    urls = agent.extract_urls(text or "")
    for u in urls:
        lu = u.lower()
        if ("/docx/" in lu or "/docs/" in lu or "/wiki/" in lu or "doxcn" in lu):
            return u
    return ""


def _feishu_extract_urls_basic(
    text,
    *,
    re,
):
    t = str(text or "")
    urls = re.findall(r"https?://[^\s<>()\"']+", t)
    cleaned = []
    seen = set()
    for u in urls:
        u = u.strip().rstrip(".,;:!?)，。；：！】》）")
        if not u:
            continue
        if u in seen:
            continue
        seen.add(u)
        cleaned.append(u)
    return cleaned


def _feishu_build_cloud_doc_url(
    doc_type,
    token,
    *,
    re,
):
    t = str(token or "").strip()
    if not t:
        return ""
    typ = str(doc_type or "").strip().lower()
    if typ in {"docx", "docs", "doc", "wiki"}:
        return f"https://www.feishu.cn/{typ}/{t}"
    if typ in {"sheet", "sheets"}:
        return f"https://www.feishu.cn/sheets/{t}"
    if typ in {"bitable", "base"}:
        return f"https://www.feishu.cn/base/{t}"
    if typ in {"mindnote", "mindnotes"}:
        return f"https://www.feishu.cn/mindnotes/{t}"
    if typ in {"slide", "slides"}:
        return f"https://www.feishu.cn/slides/{t}"
    if re.match(r"^doxcn[a-zA-Z0-9]+$", t):
        return f"https://www.feishu.cn/docx/{t}"
    if re.match(r"^doccn[a-zA-Z0-9]+$", t):
        return f"https://www.feishu.cn/doc/{t}"
    if re.match(r"^shtcn[a-zA-Z0-9]+$", t):
        return f"https://www.feishu.cn/sheets/{t}"
    if re.match(r"^(bascn|app)[a-zA-Z0-9]+$", t):
        return f"https://www.feishu.cn/base/{t}"
    if re.match(r"^wiki[a-zA-Z0-9_-]+$", t):
        return f"https://www.feishu.cn/wiki/{t}"
    # 兜底：部分类型token无法识别时，走file路由让飞书侧重定向
    return f"https://www.feishu.cn/file/{t}"


def _feishu_extract_cloud_doc_url_from_event(
    event_obj,
    *,
    _feishu_build_cloud_doc_url,
    re,
):
    token_candidates = []
    type_candidates = []

    def walk(x):
        if x is None:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                lk = str(k or "").strip().lower()
                if lk in {"file_token", "doc_token", "document_token", "obj_token", "wiki_token", "node_token", "token"}:
                    if isinstance(v, str):
                        sv = v.strip()
                        if sv:
                            token_candidates.append(sv)
                if lk in {"file_type", "doc_type", "obj_type"}:
                    if isinstance(v, str):
                        sv = v.strip().lower()
                        if sv:
                            type_candidates.append(sv)
                walk(v)
            return
        if isinstance(x, list):
            for it in x:
                walk(it)
            return
        if isinstance(x, str):
            s = x.strip()
            if not s:
                return
            m = re.search(r"(doxcn[a-zA-Z0-9]+|doccn[a-zA-Z0-9]+)", s)
            if m:
                token_candidates.append((m.group(1) or "").strip())
            return

    walk(event_obj)

    doc_type = ""
    for t in type_candidates:
        if t in {"docx", "docs", "doc", "wiki"}:
            doc_type = t
            break

    token = ""
    for cand in token_candidates:
        if cand.startswith("doxcn"):
            token = cand
            break
    if not token:
        for cand in token_candidates:
            if cand.startswith("doccn"):
                token = cand
                break
    if not token:
        for cand in token_candidates:
            if cand and len(cand) >= 10:
                token = cand
                break

    if token and not doc_type:
        if token.startswith("doxcn"):
            doc_type = "docx"
        elif token.startswith("doccn"):
            doc_type = "doc"

    return _feishu_build_cloud_doc_url(doc_type, token)


def _feishu_plain_textify(
    text,
    *,
    re,
):
    t = (text or "")
    if not t:
        return ""
    t = str(t).replace("\r\n", "\n").replace("\r", "\n")
    out_lines = []
    in_code_block = False
    for raw_line in t.split("\n"):
        line = raw_line
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            line = re.sub(r"^\s*#{1,6}\s*", "", line)
            line = line.replace("**", "").replace("__", "").replace("`", "")
            line = re.sub(r"^\s*[\*\-]\s+", "• ", line)
            line = re.sub(r"^\s*\*\s*", "• ", line)
        out_lines.append(line)
    out = "\n".join(out_lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def _extract_first_feishu_user_id(
    obj,
    *,
    _extract_first_feishu_user_id,
):
    if obj is None:
        return ""

    if isinstance(obj, str):
        s = obj.strip()
        return s if s.startswith("ou_") else ""

    if isinstance(obj, list):
        for it in obj:
            hit = _extract_first_feishu_user_id(it)
            if hit:
                return hit
        return ""

    if isinstance(obj, dict):
        priority_keys = [
            "operator_id", "operator", "sender", "user", "user_id", "open_id",
            "create_user", "creator", "commenter", "comment", "data"
        ]
        for k in priority_keys:
            if k in obj:
                hit = _extract_first_feishu_user_id(obj.get(k))
                if hit:
                    return hit

        for v in obj.values():
            hit = _extract_first_feishu_user_id(v)
            if hit:
                return hit
        return ""

    return ""


def _extract_all_text(obj, max_chars):
    out = []
    seen = set()

    def walk(x):
        if x is None:
            return
        if isinstance(x, str):
            s = x.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
            return
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
            return
        if isinstance(x, list):
            for it in x:
                walk(it)
            return

    walk(obj)
    merged = "\n".join(out)
    if len(merged) > max_chars:
        merged = merged[:max_chars]
    return merged


def _event_mentions_bot(
    event_obj,
    *,
    FEISHU_BOT_NAME,
    _extract_all_text,
):
    try:
        text = _extract_all_text(event_obj, max_chars=12000)
        if (f"@{FEISHU_BOT_NAME}") in text or FEISHU_BOT_NAME in text:
            return True
    except Exception:
        return False
    return False
