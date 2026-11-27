"""Feishu Bitable routing, fetching and answer context."""

from __future__ import annotations


def _feishu_find_bitable_url(
    text,
    *,
    _feishu_extract_urls_basic,
):
    urls = _feishu_extract_urls_basic(text or "")
    for u in urls:
        lu = u.lower()
        if ("feishu" in lu or "larksuite" in lu) and ("/base/" in lu or "bitable" in lu or "bascn" in lu):
            return u
    for u in urls:
        lu = u.lower()
        if "/base/" in lu or "bitable" in lu or "bascn" in lu:
            return u
    return ""


def _parse_bitable_url(
    url,
    *,
    parse_qs,
    re,
    urlparse,
):
    u = str(url or "").strip()
    if not u:
        return "", "", "", "链接为空"
    app_token = ""
    table_id = ""
    view_id = ""

    m = re.search(r"/base/([a-zA-Z0-9]+)", u)
    if m:
        app_token = (m.group(1) or "").strip()
    if not app_token:
        m = re.search(r"(bascn[a-zA-Z0-9]+)", u)
        if m:
            app_token = (m.group(1) or "").strip()

    try:
        parsed = urlparse(u)
        qs = parse_qs(parsed.query or "")
        table_id = str((qs.get("table") or qs.get("table_id") or [""])[0] or "").strip()
        view_id = str((qs.get("view") or qs.get("view_id") or [""])[0] or "").strip()
    except Exception:
        pass

    if not table_id:
        m = re.search(r"(tbl[a-zA-Z0-9]+)", u)
        if m:
            table_id = (m.group(1) or "").strip()

    if not app_token:
        return "", "", "", "未能从链接中解析出多维表格 app_token"
    return app_token, table_id, view_id, ""


def _feishu_bitable_request(
    method,
    path,
    params,
    *,
    _feishu_http,
    permission_manager,
):
    access_token = permission_manager.get_access_token() if hasattr(permission_manager, "get_access_token") else ""
    access_token = str(access_token or "").strip()
    if not access_token:
        return None, "当前无法获取飞书 tenant_access_token，无法拉取多维表格内容。"
    url = f"https://open.feishu.cn/open-apis{path}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        if str(method).upper() == "POST":
            resp = _feishu_http.post(url, headers=headers, json=(params or {}), timeout=20)
        else:
            resp = _feishu_http.get(url, headers=headers, params=(params or {}), timeout=20)
    except Exception as e:
        return None, str(e)
    if resp is None:
        return None, "请求失败"
    if resp.status_code != 200:
        return None, f"{resp.status_code} {str(resp.text or '')[:300]}"
    try:
        data = resp.json()
    except Exception:
        data = None
    if not isinstance(data, dict):
        return None, "接口返回非JSON"
    if int(data.get("code") or 0) != 0:
        return None, f"{data.get('code')} {data.get('msg')}"
    return data.get("data"), ""


def _feishu_bitable_list_tables(
    app_token,
    *,
    _feishu_bitable_request,
):
    data, err = _feishu_bitable_request("GET", f"/bitable/v1/apps/{app_token}/tables", params={"page_size": 100})
    if err:
        return [], err
    items = (data or {}).get("items") or []
    return items if isinstance(items, list) else [], ""


def _feishu_bitable_list_fields(
    app_token,
    table_id,
    *,
    _feishu_bitable_request,
):
    data, err = _feishu_bitable_request("GET", f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields", params={"page_size": 200})
    if err:
        return [], err
    items = (data or {}).get("items") or []
    return items if isinstance(items, list) else [], ""


def _feishu_bitable_list_records(
    app_token,
    table_id,
    view_id,
    max_records,
    *,
    _feishu_bitable_request,
):
    items = []
    page_token = ""
    for _ in range(30):
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        if view_id:
            params["view_id"] = view_id
        data, err = _feishu_bitable_request("GET", f"/bitable/v1/apps/{app_token}/tables/{table_id}/records", params=params)
        if err:
            return [], err
        got = (data or {}).get("items") or []
        if isinstance(got, list):
            items.extend(got)
        if max_records and len(items) >= int(max_records):
            items = items[:int(max_records)]
            break
        page_token = str((data or {}).get("page_token") or "").strip()
        if not page_token:
            break
    return items, ""


def _bitable_value_to_text(
    v,
    *,
    json,
):
    if v is None:
        return ""
    if isinstance(v, (str, int, float, bool)):
        return str(v)
    if isinstance(v, list):
        parts = []
        for it in v[:12]:
            if isinstance(it, (str, int, float, bool)):
                parts.append(str(it))
            elif isinstance(it, dict):
                name = str(it.get("name") or it.get("text") or it.get("title") or "").strip()
                url = str(it.get("url") or it.get("link") or "").strip()
                if name and url:
                    parts.append(f"{name}({url})")
                elif name:
                    parts.append(name)
                elif url:
                    parts.append(url)
                else:
                    parts.append(json.dumps(it, ensure_ascii=False))
            else:
                parts.append(str(it))
        return "; ".join([p for p in parts if p])
    if isinstance(v, dict):
        if "text" in v and isinstance(v.get("text"), str):
            return str(v.get("text") or "")
        if "title" in v and isinstance(v.get("title"), str):
            return str(v.get("title") or "")
        if "name" in v and isinstance(v.get("name"), str):
            return str(v.get("name") or "")
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _tokenize_loose(
    text,
    *,
    re,
):
    s = str(text or "").lower()
    s = re.sub(r"\s+", " ", s).strip()
    tokens = []
    for w in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", s):
        w = (w or "").strip()
        if not w:
            continue
        if len(w) == 1 and not w.isdigit():
            continue
        tokens.append(w)
    return tokens


def _build_bitable_context(
    question,
    url,
    app_token,
    table_id,
    table_name,
    view_id,
    fields,
    records,
    *,
    _bitable_value_to_text,
    _tokenize_loose,
    json,
):
    q_tokens = set(_tokenize_loose(question))
    field_names = []
    field_types = {}
    for f in (fields or []):
        name = str(f.get("field_name") or f.get("name") or "").strip()
        if not name:
            continue
        field_names.append(name)
        if "type" in f:
            try:
                field_types[name] = int(f.get("type"))
            except Exception:
                pass

    rows = []
    for r in (records or []):
        rid = str(r.get("record_id") or r.get("recordId") or "").strip()
        fd = r.get("fields") or {}
        if not isinstance(fd, dict):
            fd = {}
        flat = {}
        row_text_parts = []
        for k in field_names:
            v = _bitable_value_to_text(fd.get(k))
            if v:
                flat[k] = v
                row_text_parts.append(v)
        row_text = " ".join(row_text_parts).lower()
        if q_tokens:
            r_tokens = set(_tokenize_loose(row_text))
            overlap = len(q_tokens & r_tokens)
        else:
            overlap = 0
        rows.append((overlap, rid, flat))

    rows.sort(key=lambda x: x[0], reverse=True)
    top_rows = []
    for overlap, rid, flat in rows:
        if not flat:
            continue
        top_rows.append((overlap, rid, flat))
        if len(top_rows) >= 80:
            break

    header = [
        f"【多维表格链接】{url}",
        f"【App】{app_token}",
        f"【表】{table_name or table_id}",
    ]
    if view_id:
        header.append(f"【视图】{view_id}")
    if field_names:
        header.append("【字段】" + "、".join(field_names[:80]))
    if field_types:
        header.append("【字段类型】" + json.dumps(field_types, ensure_ascii=False))

    body = []
    body.append("【候选记录（按与问题相关性排序）】")
    for i, (overlap, rid, flat) in enumerate(top_rows, start=1):
        body.append(f"{i}. record_id={rid} overlap={overlap}")
        body.append(json.dumps(flat, ensure_ascii=False))

    if not top_rows and records:
        body.append("【候选记录】未筛出高相关记录，但表内有数据。你可以给出更具体的筛选条件（字段名/关键词/日期范围/负责人等）。")
    if not records:
        body.append("【候选记录】表内暂无记录或当前应用无权读取记录。")

    merged = "\n".join(header + [""] + body).strip()
    if len(merged) > 90000:
        merged = merged[:90000].strip()
    return merged


def _generate_ai_answer_with_bitable_url(
    question_text,
    bitable_url,
    chat_id,
    *,
    _bitable_cache,
    _bitable_cache_lock,
    _bitable_cache_ttl_seconds,
    _build_bitable_context,
    _feishu_bitable_list_fields,
    _feishu_bitable_list_records,
    _feishu_bitable_list_tables,
    _generate_ai_answer_with_doc,
    _parse_bitable_url,
    datetime,
):
    q = (question_text or "").strip()
    if not q:
        q = "请阅读该多维表格并回答我的问题。"
    app_token, table_id, view_id, err = _parse_bitable_url(bitable_url)
    if err:
        return err

    cache_key = f"{bitable_url.strip()}|{q}"
    now_ts = datetime.now().timestamp()
    with _bitable_cache_lock:
        expired = [k for k, v in _bitable_cache.items() if not isinstance(v, dict) or (now_ts - float(v.get('ts') or 0)) > _bitable_cache_ttl_seconds]
        for k in expired:
            _bitable_cache.pop(k, None)
        cached = _bitable_cache.get(cache_key)
        if isinstance(cached, dict) and cached.get("text"):
            return str(cached.get("text") or "")

    tables, terr = _feishu_bitable_list_tables(app_token)
    if terr:
        return f"拉取多维表格失败：{terr}"
    table_name = ""
    if not table_id:
        if tables:
            table_id = str((tables[0] or {}).get("table_id") or "").strip()
            table_name = str((tables[0] or {}).get("name") or "").strip()
    else:
        for t in tables:
            if str((t or {}).get("table_id") or "").strip() == table_id:
                table_name = str((t or {}).get("name") or "").strip()
                break

    if not table_id:
        return "未能解析出表格 table_id，且应用下未列出可用数据表。"

    fields, ferr = _feishu_bitable_list_fields(app_token, table_id)
    if ferr:
        return f"拉取多维表格字段失败：{ferr}"
    records, rerr = _feishu_bitable_list_records(app_token, table_id, view_id=view_id, max_records=1200)
    if rerr:
        return f"拉取多维表格记录失败：{rerr}"

    ctx = _build_bitable_context(q, bitable_url, app_token, table_id, table_name, view_id, fields, records)
    answer = _generate_ai_answer_with_doc(q, ctx, doc_name=f"多维表格:{table_name or table_id}", chat_id=chat_id)
    if answer:
        with _bitable_cache_lock:
            _bitable_cache[cache_key] = {"ts": now_ts, "text": answer}
    return answer
