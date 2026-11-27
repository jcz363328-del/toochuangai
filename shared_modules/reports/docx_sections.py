"""Locate selected daily report sections and images in Feishu documents."""

from __future__ import annotations


def _xiaotu_find_preferred_daily_date_start(
    text,
    now_dt,
    *,
    _xiaotu_build_date_search_keys,
    _xiaotu_build_today_daily_search_keys,
    _xiaotu_find_daily_date_matches,
    _xiaotu_is_daily_date_heading,
):
    raw = str(text or "")
    if not raw:
        return -1, "", ""
    matches = _xiaotu_find_daily_date_matches(raw)
    today_keys = _xiaotu_build_today_daily_search_keys(now_dt)
    if matches:
        if today_keys:
            for one in matches:
                one_text = str(one.get("text") or "").strip()
                one_keys = _xiaotu_build_date_search_keys(one_text)
                if any(key and key in one_keys for key in today_keys):
                    return int(one.get("start") or -1), one_text, "today"
        last = matches[-1]
        return int(last.get("start") or -1), str(last.get("text") or "").strip(), "last"

    offset = 0
    last_pos = -1
    last_line = ""
    today_pos = -1
    today_line = ""
    for one in raw.splitlines(True):
        plain = str(one or "").rstrip("\r\n")
        if _xiaotu_is_daily_date_heading(plain):
            line_keys = _xiaotu_build_date_search_keys(plain)
            if today_keys and any(key and key in line_keys for key in today_keys) and today_pos < 0:
                today_pos = offset
                today_line = plain.strip()
            last_pos = offset
            last_line = plain.strip()
        offset += len(one)
    if today_pos >= 0:
        return today_pos, today_line, "today"
    return last_pos, last_line, ("last" if last_pos >= 0 else "")


def _xiaotu_extract_image_tokens_from_block(
    block_obj,
    *,
    _xiaotu_extract_feishu_file_token_from_fragment,
    json,
    re,
):
    direct_token_keys = {"file_token", "image_token", "media_token", "resource_token", "object_token", "filetoken"}
    token_parent_hints = {
        "image", "media", "file", "attachment", "thumbnail", "cover", "origin_image",
        "gallery", "figure", "img", "picture", "embed", "docsimage", "inline_image"
    }
    found = []
    seen = set()

    def add_token(v):
        s = str(v or "").strip()
        if not s or len(s) < 10 or s in seen:
            return
        seen.add(s)
        found.append(s)

    def walk(obj, parent_key=""):
        if obj is None:
            return
        if isinstance(obj, dict):
            key_set = {str(k).lower() for k in obj.keys()}
            for k, v in obj.items():
                lk = str(k or "").strip().lower()
                if lk in direct_token_keys:
                    add_token(v)
                elif lk == "token" and (str(parent_key or "").lower() in token_parent_hints or (key_set & token_parent_hints)):
                    add_token(v)
                elif lk in {"filetoken", "mediatoken", "imagetoken", "resourcetoken", "objecttoken"}:
                    add_token(v)
                elif lk in {"src", "source"} and isinstance(v, dict):
                    add_token(v.get("token") or v.get("file_token") or v.get("image_token") or v.get("media_token"))
                walk(v, lk)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, parent_key)

    walk(block_obj)
    if not found:
        try:
            raw = json.dumps(block_obj, ensure_ascii=False)
        except Exception:
            raw = str(block_obj or "")
        raw = str(raw or "")
        token = _xiaotu_extract_feishu_file_token_from_fragment(raw)
        if token:
            add_token(token)
        if (not found) and re.search(r"(image|media|gallery|figure|picture|attachment|drivetoken)", raw, flags=re.I):
            patterns = [
                r'"fileToken"\s*:\s*"([A-Za-z0-9_-]{10,})"',
                r'"(?:file_token|image_token|media_token|resource_token|object_token)"\s*:\s*"([A-Za-z0-9_-]{10,})"',
                r'drivetoken://([A-Za-z0-9_-]{10,})',
                r'"token"\s*:\s*"([A-Za-z0-9_-]{10,})"'
            ]
            for pat in patterns:
                for m in re.finditer(pat, raw, flags=re.I):
                    add_token(m.group(1))
    return found


def _xiaotu_find_last_daily_block_index(
    blocks,
    matched_line,
    *,
    _xiaotu_build_date_search_keys,
    _xiaotu_extract_block_plain_text,
    _xiaotu_is_daily_date_heading,
    json,
    re,
):
    rows = list(blocks or [])
    if not rows:
        return -1
    last_idx = -1
    for idx, block in enumerate(rows):
        block_text = _xiaotu_extract_block_plain_text(block)
        if _xiaotu_is_daily_date_heading(block_text):
            last_idx = idx
    if last_idx >= 0:
        return last_idx

    search_keys = _xiaotu_build_date_search_keys(matched_line)
    if not search_keys:
        return -1

    for idx, block in enumerate(rows):
        try:
            raw = json.dumps(block, ensure_ascii=False)
        except Exception:
            raw = str(block or "")
        normalized = re.sub(r"\D+", "", raw or "")
        if not normalized:
            continue
        if any(key and key in normalized for key in search_keys):
            last_idx = idx
    return last_idx


def _xiaotu_find_preferred_daily_block_index(
    blocks,
    matched_line,
    now_dt,
    *,
    _xiaotu_build_date_search_keys,
    _xiaotu_build_today_daily_search_keys,
    _xiaotu_extract_block_plain_text,
    _xiaotu_is_daily_date_heading,
    json,
    re,
):
    rows = list(blocks or [])
    if not rows:
        return -1, ""
    today_keys = _xiaotu_build_today_daily_search_keys(now_dt)
    last_idx = -1
    for idx, block in enumerate(rows):
        block_text = _xiaotu_extract_block_plain_text(block)
        if not _xiaotu_is_daily_date_heading(block_text):
            continue
        line_keys = _xiaotu_build_date_search_keys(block_text)
        if today_keys and any(key and key in line_keys for key in today_keys):
            return idx, "today"
        last_idx = idx
    if last_idx >= 0:
        return last_idx, "last"

    search_keys = _xiaotu_build_date_search_keys(matched_line)
    if search_keys:
        for idx, block in enumerate(rows):
            try:
                raw = json.dumps(block, ensure_ascii=False)
            except Exception:
                raw = str(block or "")
            normalized = re.sub(r"\D+", "", raw or "")
            if not normalized:
                continue
            if any(key and key in normalized for key in search_keys):
                return idx, "matched_line"
    return -1, ""


def _xiaotu_fetch_docx_blocks(
    agent,
    doc_token,
    *,
    _feishu_http,
    permission_manager,
):
    token = str(doc_token or "").strip()
    if not token:
        return [], "缺少文档token"
    access_token = permission_manager.get_access_token()
    if not access_token:
        return [], "当前无法获取飞书 tenant_access_token"
    http_client = getattr(agent, "_http", None) or _feishu_http
    headers = {"Authorization": f"Bearer {access_token}"}
    page_token = ""
    blocks = []
    for _ in range(80):
        try:
            api = f"https://open.feishu.cn/open-apis/docx/v1/documents/{token}/blocks"
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            resp = http_client.get(api, headers=headers, params=params, timeout=15)
            data = resp.json() if resp is not None else {}
            if not resp or resp.status_code != 200:
                return blocks, f"获取文档块失败 {getattr(resp, 'status_code', '')} {str(getattr(resp, 'text', '') or '')[:160]}"
            if not isinstance(data, dict) or int(data.get("code") or 0) != 0:
                return blocks, f"获取文档块失败 {data.get('code')} {data.get('msg')}"
            d = data.get("data") or {}
            items = d.get("items") or []
            if isinstance(items, list):
                blocks.extend(items)
            page_token = str(d.get("page_token") or "").strip()
            if not page_token:
                break
        except Exception as e:
            return blocks, f"获取文档块异常: {str(e)}"
    return blocks, ""


def _xiaotu_extract_report_image_paths_from_html(
    html_text,
    *,
    os,
    parse_qs,
    re,
    relocate_storage_path,
    unquote,
    urlparse,
):
    html = str(html_text or "").strip()
    if not html:
        return []
    out = []
    seen = set()
    for m in re.finditer(r'<img\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        src = str(m.group(1) or "").strip()
        if not src:
            continue
        normalized = unquote(src).strip().strip('"').strip("'")
        if normalized.startswith("/api/xiaotu/report_image"):
            try:
                parsed = urlparse(normalized)
                nested_path = parse_qs(parsed.query or "").get("path") or []
                normalized = str(nested_path[0] if nested_path else "").strip()
                normalized = unquote(normalized).strip().strip('"').strip("'")
            except Exception:
                normalized = ""
        if not normalized:
            continue
        normalized = relocate_storage_path(normalized).replace("/", os.sep)
        if not os.path.isabs(normalized):
            continue
        abs_path = os.path.abspath(normalized)
        if abs_path in seen:
            continue
        seen.add(abs_path)
        out.append(abs_path)
    return out


def _xiaotu_pick_doc_for_request(
    user_id,
    user_access_token,
    doc_id,
    manual_url,
    question,
    *,
    _feishu_build_cloud_doc_url,
    _feishu_find_cloud_doc_url_any,
    _xiaotu_extract_doc_token,
    _xiaotu_get_doc_candidates_for_user,
):
    docs, _ = _xiaotu_get_doc_candidates_for_user(
        user_id,
        force_refresh=False,
        user_access_token=user_access_token
    )
    target = str(doc_id or "").strip()
    if target:
        for one in (docs or []):
            if str((one or {}).get('id') or '').strip() == target:
                return one
    url = _feishu_find_cloud_doc_url_any(str(manual_url or '').strip()) or str(manual_url or '').strip()
    if not url:
        url = _feishu_find_cloud_doc_url_any(str(question or '').strip()) or ""
    if not url:
        token_only = _xiaotu_extract_doc_token(question)
        if token_only.startswith("doxcn"):
            url = _feishu_build_cloud_doc_url("docx", token_only)
        elif token_only.startswith("doccn"):
            url = _feishu_build_cloud_doc_url("doc", token_only)
        elif token_only.startswith("wiki"):
            url = _feishu_build_cloud_doc_url("wiki", token_only)
    if not url:
        return None
    token = _xiaotu_extract_doc_token(url)
    if not token:
        return None
    return {
        'id': f'adhoc_{token}',
        'name': f'临时文档-{token[:8]}',
        'url': url
    }
