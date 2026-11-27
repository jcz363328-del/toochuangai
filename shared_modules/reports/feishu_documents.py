"""Discover Feishu documents and people used by daily reports."""

from __future__ import annotations


def _xiaotu_get_user_saved_docs(
    user_id,
    *,
    session,
):
    all_docs = session.get("xiaotu_saved_docs") or {}
    if not isinstance(all_docs, dict):
        return []
    rows = all_docs.get(str(user_id or "").strip()) or []
    if not isinstance(rows, list):
        return []
    out = []
    for one in rows:
        if not isinstance(one, dict):
            continue
        url = str(one.get("url") or "").strip()
        name = str(one.get("name") or "").strip()
        doc_id = str(one.get("id") or "").strip()
        if not url or not doc_id:
            continue
        out.append({
            "id": doc_id,
            "name": name or "未命名云文档",
            "url": url,
            "source": "personal",
            "created_at": str(one.get("created_at") or "")
        })
    return out


def _xiaotu_list_feishu_docs_for_user(
    user_id,
    force_refresh,
    user_access_token,
    *,
    _feishu_build_cloud_doc_url,
    _feishu_http,
    _xiaotu_doc_list_cache,
    _xiaotu_doc_list_cache_lock,
    _xiaotu_doc_list_cache_ttl_seconds,
    _xiaotu_extract_doc_token,
    datetime,
):
    uid = str(user_id or "").strip()
    if not uid:
        return [], "未登录"
    token = str(user_access_token or "").strip()
    token_cache_key = f"{uid}|{token[:20]}"
    now_ts = datetime.now().timestamp()
    with _xiaotu_doc_list_cache_lock:
        cached = _xiaotu_doc_list_cache.get(token_cache_key)
        if (not force_refresh) and isinstance(cached, dict):
            ts = float(cached.get("ts") or 0)
            if (now_ts - ts) <= _xiaotu_doc_list_cache_ttl_seconds:
                data = cached.get("data") or []
                return data if isinstance(data, list) else [], str(cached.get("err") or "")
    use_user_token = True
    if not token:
        return [], "未获取到用户飞书登录凭证，请重新登录后再刷新可见文档"
    headers = {"Authorization": f"Bearer {token}"}
    page_token = ""
    pages = 0
    max_pages = 400
    max_items = 20000
    out = []
    seen = set()
    err_text = ""
    while pages < max_pages:
        pages += 1
        param_variants = [
            {"page_size": 200, "order_by": "EditedTime", "direction": "DESC"},
            {"page_size": 200},
            {"page_size": 100}
        ]
        resp = None
        resp_data = None
        status_code = 0
        for base_params in param_variants:
            params = dict(base_params)
            if page_token:
                params["page_token"] = page_token
            try:
                one_resp = _feishu_http.get("https://open.feishu.cn/open-apis/drive/v1/files", headers=headers, params=params, timeout=15)
            except Exception as e:
                err_text = str(e)
                one_resp = None
            if one_resp is None:
                continue
            one_status = int(one_resp.status_code or 0)
            one_data = one_resp.json() if one_resp.content else {}
            if one_status == 200 and int((one_data or {}).get("code") or 0) == 0:
                resp = one_resp
                resp_data = one_data
                status_code = one_status
                break
            if one_status == 400:
                resp = one_resp
                resp_data = one_data
                status_code = one_status
                continue
            resp = one_resp
            resp_data = one_data
            status_code = one_status
            break
        if resp is None:
            if not err_text:
                err_text = "飞书接口请求失败"
            break
        if status_code != 200:
            api_msg = str((resp_data or {}).get("msg") or "").strip()
            if api_msg:
                err_text = f"飞书接口返回状态码 {status_code}：{api_msg}"
            else:
                err_text = f"飞书接口返回状态码 {status_code}"
            low_msg = api_msg.lower()
            if status_code == 401 or "token expired" in low_msg or "authentication token expired" in low_msg:
                err_text = "飞书登录已过期，请重新登录后再刷新可见文档"
            if status_code == 400:
                err_text = f"{err_text}（已自动兼容不同分页参数）"
            break
        data = resp_data if isinstance(resp_data, dict) else (resp.json() if resp.content else {})
        if int((data or {}).get("code") or 0) != 0:
            err_text = str((data or {}).get("msg") or "飞书接口调用失败")
            if use_user_token and ("access token" in err_text.lower() or "invalid" in err_text.lower() or "expired" in err_text.lower()):
                err_text = "飞书登录已过期，请重新登录后再刷新可见文档"
            break
        body = (data or {}).get("data") or {}
        files = body.get("files") or body.get("items") or body.get("list") or []
        for one in files:
            if not isinstance(one, dict):
                continue
            typ_raw = str(
                one.get("type")
                or one.get("obj_type")
                or one.get("file_type")
                or one.get("doc_type")
                or one.get("mime_type")
                or one.get("file_extension")
                or one.get("sub_type")
                or ""
            ).strip().lower()
            token_one = str(
                one.get("token")
                or one.get("file_token")
                or one.get("obj_token")
                or one.get("node_token")
                or one.get("wiki_token")
                or ""
            ).strip()
            name = str(one.get("name") or one.get("title") or "").strip()
            url = str(one.get("url") or "").strip()
            if not token_one and url:
                token_one = _xiaotu_extract_doc_token(url)
            typ = ""
            # 放宽类型：收集用户可访问的主要云文档对象（文档/表格/wiki/多维表格/思维笔记/幻灯片）
            if "docx" in typ_raw:
                typ = "docx"
            elif typ_raw in {"docs", "doc", "wiki", "sheet", "sheets", "bitable", "base", "mindnote", "slides"}:
                typ = typ_raw
            elif "wiki" in typ_raw:
                typ = "wiki"
            elif "doc" in typ_raw:
                typ = "doc"
            elif "sheet" in typ_raw:
                typ = "sheet"
            elif "bitable" in typ_raw or "base" in typ_raw:
                typ = "bitable"
            elif "mindnote" in typ_raw:
                typ = "mindnote"
            elif "slide" in typ_raw:
                typ = "slides"

            if not typ:
                if token_one.startswith("doxcn"):
                    typ = "docx"
                elif token_one.startswith("doccn"):
                    typ = "doc"
                elif token_one.startswith("wiki"):
                    typ = "wiki"

            if not typ and url:
                u = url.lower()
                if "/docx/" in u:
                    typ = "docx"
                elif "/docs/" in u:
                    typ = "docs"
                elif "/doc/" in u:
                    typ = "doc"
                elif "/wiki/" in u:
                    typ = "wiki"
                elif "/sheets/" in u:
                    typ = "sheets"
                elif "/base/" in u or "/bitable/" in u:
                    typ = "bitable"
                elif "/mindnote/" in u:
                    typ = "mindnote"
                elif "/slides/" in u:
                    typ = "slides"

            # 没有URL时，尽量构造可访问链接；构不出就跳过
            if not url:
                url = _feishu_build_cloud_doc_url(typ, token_one)
            if not url:
                continue
            stable_key = token_one or url
            key = f"{typ}:{stable_key}"
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "id": f"auto_{token_one}",
                "name": name or f"云文档-{token_one[:8]}",
                "url": url,
                "source": "auto",
                "created_at": ""
            })
            if len(out) >= max_items:
                break
        if len(out) >= max_items:
            break
        page_token = str(
            body.get("next_page_token")
            or body.get("page_token")
            or body.get("next_cursor")
            or body.get("cursor")
            or ""
        ).strip()
        has_more_raw = body.get("has_more")
        if has_more_raw is None:
            has_more_raw = body.get("more")
        if isinstance(has_more_raw, bool):
            has_more = has_more_raw
        elif isinstance(has_more_raw, (int, float)):
            has_more = int(has_more_raw) != 0
        else:
            has_more = str(has_more_raw or "").strip().lower() in {"1", "true", "yes", "y"}

        if page_token:
            continue
        if not has_more:
            break
        # 避免has_more是脏值但没有分页游标时死循环导致只拿到首页数据
        break
    with _xiaotu_doc_list_cache_lock:
        _xiaotu_doc_list_cache[token_cache_key] = {"ts": now_ts, "data": out, "err": err_text}
    if use_user_token and not out and not err_text:
        err_text = "未拉取到可见云文档：请确认飞书应用已开通云文档读取权限，并重新登录后再刷新"
    return out, err_text


def _xiaotu_set_user_saved_docs(
    user_id,
    rows,
    *,
    session,
):
    all_docs = session.get("xiaotu_saved_docs") or {}
    if not isinstance(all_docs, dict):
        all_docs = {}
    uid = str(user_id or "").strip()
    all_docs[uid] = rows if isinstance(rows, list) else []
    session["xiaotu_saved_docs"] = all_docs
    session.modified = True


def _xiaotu_lookup_open_id_by_name(
    user_name,
    *,
    _XIAOTU_NOTIFY_ID_TABLE_FALLBACK,
    _XIAOTU_NOTIFY_ID_TABLE_PRIMARY,
    _safe_debug_print,
    _xiaotu_get_cached_open_id_by_name,
    _xiaotu_list_notify_departments,
    _xiaotu_list_notify_users_current_app_cached,
    _xiaotu_remember_user_open_id,
    _xiaotu_sql_escape,
    re,
    sf_db,
):
    name = str(user_name or "").strip()
    if not name:
        return ""
    if name.startswith("ou_") or name.startswith("ou-"):
        return name
    cached_id = _xiaotu_get_cached_open_id_by_name(name)
    if cached_id:
        return cached_id

    def _extract_open_id_value(result):
        if isinstance(result, str):
            return result.strip()
        if isinstance(result, dict):
            return str(
                result.get("FeiShu_ID")
                or result.get("feishu_id")
                or result.get("FEISHU_ID")
                or result.get("Feishu_ID")
                or ""
            ).strip()
        if isinstance(result, (list, tuple)):
            if not result:
                return ""
            first = result[0]
            if isinstance(first, dict):
                return str(
                    first.get("FeiShu_ID")
                    or first.get("feishu_id")
                    or first.get("FEISHU_ID")
                    or first.get("Feishu_ID")
                    or ""
                ).strip()
            if isinstance(first, (list, tuple)):
                return str(first[0] if len(first) > 0 else "").strip()
            return str(first or "").strip()
        return ""

    def _query_table(table_name, where_sql):
        table = str(table_name or "").strip()
        if not table:
            return ""
        try:
            rows = sf_db(
                f"""
                IF OBJECT_ID(N'{table}', N'U') IS NOT NULL
                    SELECT TOP 1 FeiShu_ID
                    FROM {table}
                    WHERE ({where_sql})
                      AND (FeiShu_ID LIKE 'ou[_]%%' OR FeiShu_ID LIKE 'ou-%%')
                    ORDER BY FeiShu_ID
                """
            )
        except Exception:
            rows = None
        fid = _extract_open_id_value(rows)
        return fid if (fid.startswith("ou_") or fid.startswith("ou-")) else ""

    def _query_all_tables(where_sql):
        for table in (_XIAOTU_NOTIFY_ID_TABLE_PRIMARY, _XIAOTU_NOTIFY_ID_TABLE_FALLBACK):
            fid = _query_table(table, where_sql)
            if fid:
                _xiaotu_remember_user_open_id(name, fid)
                return fid
        return ""

    esc_name = _xiaotu_sql_escape(name)
    compact_name = re.sub(r"\s+", "", name)
    esc_compact_name = _xiaotu_sql_escape(compact_name)

    fid = _query_all_tables(f"YONGHU=N'{esc_name}'")
    if fid:
        return fid

    if compact_name:
        fid = _query_all_tables(
            f"""
            REPLACE(REPLACE(ISNULL(YONGHU, N''), N' ', N''), CHAR(9), N'')=N'{esc_compact_name}'
            """
        )
        if fid:
            return fid

    fid = _query_all_tables(f"YONGHU LIKE N'%%{esc_name}%%'")
    if fid:
        return fid

    if compact_name:
        fid = _query_all_tables(
            f"""
            REPLACE(REPLACE(ISNULL(YONGHU, N''), N' ', N''), CHAR(9), N'') LIKE N'%%{esc_compact_name}%%'
            """
        )
        if fid:
            return fid
    try:
        exact_candidates = []
        fuzzy_candidates = []
        for dept in (_xiaotu_list_notify_departments() or []):
            if not isinstance(dept, dict):
                continue
            dept_id = str(dept.get("department_id") or "").strip()
            if not dept_id:
                continue
            for one in (_xiaotu_list_notify_users_current_app_cached(dept_id) or []):
                if not isinstance(one, dict):
                    continue
                oid = str(one.get("open_id") or "").strip()
                if not (oid.startswith("ou_") or oid.startswith("ou-")):
                    continue
                candidate_names = [
                    str(one.get("name") or "").strip(),
                    str(one.get("display_name") or "").strip(),
                ]
                for candidate_name in candidate_names:
                    if not candidate_name:
                        continue
                    candidate_compact = re.sub(r"\s+", "", candidate_name)
                    if candidate_name == name or (compact_name and candidate_compact == compact_name):
                        exact_candidates.append((candidate_name, oid))
                    elif name in candidate_name or (compact_name and compact_name in candidate_compact):
                        fuzzy_candidates.append((candidate_name, oid))
        for candidate_name, oid in exact_candidates or fuzzy_candidates:
            _xiaotu_remember_user_open_id(candidate_name, oid)
            _xiaotu_remember_user_open_id(name, oid)
            return oid
    except Exception as e:
        _safe_debug_print(f"permission debug contact fallback lookup failed: {name} -> {e}")
    return ""


def _xiaotu_get_doc_candidates_for_user(
    user_id,
    force_refresh,
    user_access_token,
    *,
    _XIAOTU_SHARED_DOCS,
    _xiaotu_get_user_departments,
    _xiaotu_get_user_saved_docs,
    _xiaotu_list_feishu_docs_for_user,
    _xiaotu_match_doc_permission,
):
    user_depts = _xiaotu_get_user_departments(user_id)
    out = []
    for raw in (_XIAOTU_SHARED_DOCS or []):
        if not isinstance(raw, dict):
            continue
        if not _xiaotu_match_doc_permission(raw, user_depts):
            continue
        doc_id = str(raw.get("id") or "").strip()
        url = str(raw.get("url") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not doc_id or not url:
            continue
        out.append({
            "id": doc_id,
            "name": name or "未命名云文档",
            "url": url,
            "source": "shared",
            "created_at": str(raw.get("created_at") or "")
        })
    auto_docs, auto_err = _xiaotu_list_feishu_docs_for_user(
        user_id,
        force_refresh=force_refresh,
        user_access_token=user_access_token
    )
    out.extend(auto_docs)
    out.extend(_xiaotu_get_user_saved_docs(user_id))
    uniq = []
    seen_url = set()
    for d in out:
        if not isinstance(d, dict):
            continue
        u = str(d.get("url") or "").strip()
        if not u or u in seen_url:
            continue
        seen_url.add(u)
        uniq.append(d)
    return uniq, auto_err
