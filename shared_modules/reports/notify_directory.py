"""Select and resolve Feishu recipients for daily report notifications."""

from __future__ import annotations


def _xiaotu_list_notify_departments(
    *,
    _XIAOTU_NOTIFY_ID_TABLE_FALLBACK,
    _XIAOTU_NOTIFY_ID_TABLE_PRIMARY,
    sf_db,
):
    rows = sf_db(
        f"""
        IF OBJECT_ID(N'{_XIAOTU_NOTIFY_ID_TABLE_PRIMARY}', N'U') IS NOT NULL
            SELECT DISTINCT YONGHU, FeiShu_ID FROM {_XIAOTU_NOTIFY_ID_TABLE_PRIMARY}
            WHERE (FeiShu_ID LIKE 'od[_]%%' OR FeiShu_ID LIKE 'od-%%')
            ORDER BY YONGHU
        ELSE
            SELECT DISTINCT YONGHU, FeiShu_ID FROM {_XIAOTU_NOTIFY_ID_TABLE_FALLBACK}
            WHERE (FeiShu_ID LIKE 'od[_]%%' OR FeiShu_ID LIKE 'od-%%')
            ORDER BY YONGHU
        """
    ) or []
    out = []
    seen = set()
    if not isinstance(rows, list):
        rows = [rows]
    for row in rows:
        if isinstance(row, dict):
            dept_name = str(row.get("YONGHU") or "").strip()
            dept_id = str(row.get("FeiShu_ID") or "").strip()
        elif isinstance(row, (list, tuple)):
            dept_name = str(row[0] if len(row) > 0 else "").strip()
            dept_id = str(row[1] if len(row) > 1 else "").strip()
        else:
            dept_name = str(row or "").strip()
            dept_id = ""
        if not dept_id.startswith("od_") and not dept_id.startswith("od-"):
            continue
        key = f"{dept_id}|{dept_name}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"department_id": dept_id, "department_name": dept_name})
    return out


def _xiaotu_list_department_children_current_app(
    department_id,
    *,
    _feishu_http,
    permission_manager,
):
    dep_id = str(department_id or "").strip()
    if not dep_id:
        return []
    token = permission_manager.get_access_token()
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    page_token = ""
    out = []
    seen = set()
    for _ in range(50):
        try:
            url = f"https://open.feishu.cn/open-apis/contact/v3/departments/{dep_id}/children"
            params = {"department_id_type": "open_department_id", "page_size": 100, "fetch_child": False}
            if page_token:
                params["page_token"] = page_token
            resp = _feishu_http.get(url, headers=headers, params=params, timeout=15)
            data = resp.json() if resp is not None else {}
            if not resp or resp.status_code != 200 or not isinstance(data, dict) or int(data.get("code") or 0) != 0:
                break
            items = ((data.get("data") or {}).get("items") or [])
            for item in items:
                one_id = str(
                    (item or {}).get("open_department_id")
                    or (item or {}).get("department_id")
                    or (item or {}).get("id")
                    or ""
                ).strip()
                if one_id and one_id not in seen:
                    seen.add(one_id)
                    out.append(one_id)
            page_token = str(((data.get("data") or {}).get("page_token") or "")).strip()
            if not page_token:
                break
        except Exception:
            break
    return out


def _xiaotu_list_notify_users_current_app(
    department_id,
    *,
    _feishu_http,
    _xiaotu_expand_department_tree_current_app,
    permission_manager,
):
    dep_ids = _xiaotu_expand_department_tree_current_app(department_id)
    if not dep_ids:
        return []
    token = permission_manager.get_access_token()
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    payload = []
    seen = set()
    for dep_id in dep_ids:
        page_token = ""
        for _ in range(50):
            try:
                url = "https://open.feishu.cn/open-apis/contact/v3/users"
                params = {
                    "department_id_type": "open_department_id",
                    "department_id": dep_id,
                    "user_id_type": "open_id",
                    "page_size": 100
                }
                if page_token:
                    params["page_token"] = page_token
                resp = _feishu_http.get(url, headers=headers, params=params, timeout=15)
                data = resp.json() if resp is not None else {}
                if not resp or resp.status_code != 200 or not isinstance(data, dict) or int(data.get("code") or 0) != 0:
                    break
                items = ((data.get("data") or {}).get("items") or [])
                for item in items:
                    oid = str((item or {}).get("open_id") or "").strip()
                    if not oid or oid in seen:
                        continue
                    seen.add(oid)
                    payload.append({
                        "open_id": oid,
                        "name": str((item or {}).get("name") or "").strip(),
                        "display_name": str((item or {}).get("name") or oid).strip()
                    })
                page_token = str(((data.get("data") or {}).get("page_token") or "")).strip()
                if not page_token:
                    break
            except Exception:
                break
    payload.sort(key=lambda x: str(x.get("display_name") or ""))
    return payload


def _xiaotu_list_notify_users_current_app_cached(
    department_id,
    *,
    _xiaotu_list_notify_users_current_app,
    _xiaotu_notify_department_users_cache,
    _xiaotu_notify_department_users_cache_lock,
    _xiaotu_notify_department_users_cache_ttl_seconds,
    time,
):
    dep_id = str(department_id or "").strip()
    if not dep_id:
        return []
    now_ts = time.time()
    with _xiaotu_notify_department_users_cache_lock:
        cached = _xiaotu_notify_department_users_cache.get(dep_id)
        if isinstance(cached, dict) and (now_ts - float(cached.get("ts") or 0)) < _xiaotu_notify_department_users_cache_ttl_seconds:
            users = cached.get("users") or []
            return [dict(one) for one in users if isinstance(one, dict)]
    users = _xiaotu_list_notify_users_current_app(dep_id)
    normalized = [dict(one) for one in (users or []) if isinstance(one, dict)]
    with _xiaotu_notify_department_users_cache_lock:
        _xiaotu_notify_department_users_cache[dep_id] = {"ts": now_ts, "users": normalized}
    return [dict(one) for one in normalized]


def _xiaotu_get_history_analysis_visible_user_names(
    user_id,
    user_name,
    *,
    _XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES,
    _current_user_has_permission,
    _xiaotu_collect_notify_user_names_by_department_names,
    _xiaotu_get_department_leader_user_id,
    _xiaotu_list_notify_departments,
    _xiaotu_list_notify_users_current_app_cached,
    permission_manager,
):
    uid = str(user_id or "").strip()
    current_name = str(user_name or "").strip()
    visible_names = []
    seen_names = set()
    leader_department_ids = []
    leader_department_names = []
    scoped_department_ids = []
    scoped_department_names = []
    if _current_user_has_permission('xiaotu_report_history_operation_3_scope', uid):
        scoped_department_names = ["运营三部"]
    elif _current_user_has_permission('xiaotu_report_history_operation_scope', uid):
        scoped_department_names = list(_XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES)
    leader_scope_allowed = _current_user_has_permission(
        'xiaotu_report_history_department_leader',
        uid,
    )

    def add_name(raw_name):
        name = str(raw_name or "").strip()
        if not name or name in seen_names:
            return
        seen_names.add(name)
        visible_names.append(name)

    if scoped_department_names:
        for one in (_xiaotu_list_notify_departments() or []):
            if not isinstance(one, dict):
                continue
            dept_name = str(one.get("department_name") or one.get("name") or "").strip()
            dept_id = str(one.get("department_id") or "").strip()
            if dept_name in scoped_department_names and dept_id:
                scoped_department_ids.append(dept_id)
        for scoped_name in _xiaotu_collect_notify_user_names_by_department_names(scoped_department_names):
            add_name(scoped_name)

    if uid and leader_scope_allowed:
        try:
            departments = permission_manager.get_user_departments(uid) or []
        except Exception:
            departments = []
        for row in departments:
            if not isinstance(row, dict):
                continue
            if str(row.get("status") or "").strip().lower() in {"invalid", "unmapped"}:
                continue
            dept_id = str(row.get("department_id") or "").strip()
            if not dept_id:
                continue
            leader_user_id = _xiaotu_get_department_leader_user_id(dept_id)
            if leader_user_id and leader_user_id == uid:
                leader_department_ids.append(dept_id)
                leader_department_names.append(str(row.get("name") or "").strip())

    if leader_department_ids:
        for dept_id in leader_department_ids:
            for one in (_xiaotu_list_notify_users_current_app_cached(dept_id) or []):
                if isinstance(one, dict):
                    add_name(one.get("name"))
    add_name(current_name)
    department_ids = []
    for dep_id in list(leader_department_ids) + list(scoped_department_ids):
        if dep_id and dep_id not in department_ids:
            department_ids.append(dep_id)
    department_names = []
    for dep_name in list(leader_department_names) + list(scoped_department_names):
        if dep_name and dep_name not in department_names:
            department_names.append(dep_name)
    return {
        "is_department_leader": bool(department_ids),
        "department_ids": department_ids,
        "department_names": department_names,
        "user_names": visible_names,
    }


def _xiaotu_search_notify_users(
    keyword,
    limit,
    *,
    _XIAOTU_NOTIFY_ID_TABLE_FALLBACK,
    _XIAOTU_NOTIFY_ID_TABLE_PRIMARY,
    _normalize_feishu_user_name,
    _xiaotu_sql_escape,
    sf_db,
):
    query = str(keyword or "").strip()
    if not query:
        return []
    safe_limit = max(1, min(int(limit or 50), 200))
    esc_kw = _xiaotu_sql_escape(query)
    rows = sf_db(
        f"""
        IF OBJECT_ID(N'{_XIAOTU_NOTIFY_ID_TABLE_PRIMARY}', N'U') IS NOT NULL
            SELECT TOP {safe_limit} YONGHU, FeiShu_ID FROM {_XIAOTU_NOTIFY_ID_TABLE_PRIMARY}
            WHERE (FeiShu_ID LIKE 'ou[_]%%' OR FeiShu_ID LIKE 'ou-%%')
              AND (YONGHU LIKE N'%%{esc_kw}%%' OR FeiShu_ID LIKE '%%{esc_kw}%%')
            ORDER BY YONGHU ASC, FeiShu_ID ASC
        ELSE
            SELECT TOP {safe_limit} YONGHU, FeiShu_ID FROM {_XIAOTU_NOTIFY_ID_TABLE_FALLBACK}
            WHERE (FeiShu_ID LIKE 'ou[_]%%' OR FeiShu_ID LIKE 'ou-%%')
              AND (YONGHU LIKE N'%%{esc_kw}%%' OR FeiShu_ID LIKE '%%{esc_kw}%%')
            ORDER BY YONGHU ASC, FeiShu_ID ASC
        """
    ) or []
    if not isinstance(rows, list):
        rows = [rows]
    out = []
    seen = set()
    for row in rows:
        if isinstance(row, dict):
            name = _normalize_feishu_user_name(row.get("YONGHU"), fallback="")
            open_id = str(row.get("FeiShu_ID") or "").strip()
        elif isinstance(row, (list, tuple)):
            name = _normalize_feishu_user_name(row[0] if len(row) > 0 else "", fallback="")
            open_id = str(row[1] if len(row) > 1 else "").strip()
        else:
            continue
        if not open_id.startswith("ou_") and not open_id.startswith("ou-"):
            continue
        display_name = str(name or open_id).strip()
        key = open_id or display_name
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({
            "open_id": open_id,
            "name": name,
            "display_name": display_name,
            "search_scope": "all_departments",
        })
    return out


def _xiaotu_query_user_names_by_open_ids(
    open_ids,
    *,
    _XIAOTU_NOTIFY_ID_TABLE_FALLBACK,
    _XIAOTU_NOTIFY_ID_TABLE_PRIMARY,
    _feishu_http,
    _normalize_feishu_user_name,
    _resolve_feishu_user_name,
    _xiaotu_sql_escape,
    permission_manager,
    sf_db,
):
    ids = []
    seen = set()
    for raw in (open_ids or []):
        oid = str(raw or "").strip()
        if not oid.startswith("ou_") or oid in seen:
            continue
        seen.add(oid)
        ids.append(oid)
    if not ids:
        return {}
    mapping = {}
    token = permission_manager.get_access_token() if hasattr(permission_manager, "get_access_token") else ""
    if token:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        for oid in ids:
            try:
                resp = _feishu_http.get(
                    f"https://open.feishu.cn/open-apis/contact/v3/users/{oid}",
                    headers=headers,
                    params={"user_id_type": "open_id"},
                    timeout=10
                )
                data = resp.json() if resp is not None else {}
                if resp and resp.status_code == 200 and isinstance(data, dict) and int(data.get("code") or 0) == 0:
                    user_obj = (data.get("data") or {}).get("user") or {}
                    name = _resolve_feishu_user_name(user_obj, fallback="")
                    if name:
                        mapping[oid] = name
            except Exception:
                continue
    missing_ids = [oid for oid in ids if oid not in mapping]
    if missing_ids:
        cond = " OR ".join([f"FeiShu_ID='{_xiaotu_sql_escape(oid)}'" for oid in missing_ids])
        rows = sf_db(
            f"""
            IF OBJECT_ID(N'{_XIAOTU_NOTIFY_ID_TABLE_PRIMARY}', N'U') IS NOT NULL
                SELECT FeiShu_ID, YONGHU FROM {_XIAOTU_NOTIFY_ID_TABLE_PRIMARY} WHERE {cond}
            ELSE
                SELECT FeiShu_ID, YONGHU FROM {_XIAOTU_NOTIFY_ID_TABLE_FALLBACK} WHERE {cond}
            """
        ) or []
        if not isinstance(rows, list):
            rows = [rows]
        for row in rows:
            if isinstance(row, dict):
                oid = str(row.get("FeiShu_ID") or "").strip()
                name = _normalize_feishu_user_name(row.get("YONGHU"), fallback="")
            elif isinstance(row, (list, tuple)):
                oid = str(row[0] if len(row) > 0 else "").strip()
                name = _normalize_feishu_user_name(row[1] if len(row) > 1 else "", fallback="")
            else:
                continue
            if oid.startswith("ou_") and name:
                mapping[oid] = name
    return mapping


def _xiaotu_query_user_name_by_any_id(
    open_id,
    user_id,
    union_id,
    *,
    _feishu_http,
    _normalize_feishu_user_name,
    _resolve_feishu_user_name,
    _xiaotu_query_user_names_by_open_ids,
    permission_manager,
):
    oid = str(open_id or "").strip()
    uid = str(user_id or "").strip()
    union = str(union_id or "").strip()
    token = permission_manager.get_access_token() if hasattr(permission_manager, "get_access_token") else ""
    targets = []
    if oid.startswith("ou_"):
        targets.append((oid, "open_id"))
    if uid:
        targets.append((uid, "user_id"))
    if union:
        targets.append((union, "union_id"))
    if token:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        for raw_id, id_type in targets:
            try:
                resp = _feishu_http.get(
                    f"https://open.feishu.cn/open-apis/contact/v3/users/{raw_id}",
                    headers=headers,
                    params={"user_id_type": id_type},
                    timeout=10
                )
                data = resp.json() if resp is not None else {}
                if resp and resp.status_code == 200 and isinstance(data, dict) and int(data.get("code") or 0) == 0:
                    user_obj = (data.get("data") or {}).get("user") or {}
                    name = _resolve_feishu_user_name(user_obj, fallback="")
                    if name:
                        return name
            except Exception:
                continue
    if oid.startswith("ou_"):
        try:
            mapping = _xiaotu_query_user_names_by_open_ids([oid]) or {}
            name = _normalize_feishu_user_name(mapping.get(oid), fallback="")
            if name:
                return name
        except Exception:
            pass
    return ""


def _xiaotu_parse_notify_open_ids(
    data_dict,
    *,
    json,
    request,
):
    candidates = []
    if isinstance(data_dict, dict):
        one = data_dict.get("notify_open_ids")
        if isinstance(one, list):
            candidates.extend(one)
        else:
            candidates.append(one)
    try:
        candidates.extend(request.form.getlist("notify_open_ids"))
    except Exception:
        pass

    out = []
    seen = set()
    for raw in candidates:
        if raw is None:
            continue
        if isinstance(raw, list):
            parts = raw
        else:
            txt = str(raw or "").strip()
            if not txt:
                continue
            parts = []
            if txt.startswith("[") and txt.endswith("]"):
                try:
                    parsed = json.loads(txt)
                    if isinstance(parsed, list):
                        parts = parsed
                except Exception:
                    parts = []
            if not parts:
                if "," in txt:
                    parts = [x.strip() for x in txt.split(",") if str(x).strip()]
                else:
                    parts = [txt]
        for item in parts:
            oid = str(item or "").strip()
            if not oid.startswith("ou_") or oid in seen:
                continue
            seen.add(oid)
            out.append(oid)
    return out


def _xiaotu_parse_notify_targets(
    data_dict,
    *,
    json,
    request,
):
    candidates = []
    if isinstance(data_dict, dict):
        one = data_dict.get("notify_targets")
        if isinstance(one, list):
            candidates.extend(one)
        elif isinstance(one, str) and one.strip():
            try:
                parsed = json.loads(one)
                if isinstance(parsed, list):
                    candidates.extend(parsed)
            except Exception:
                pass
    try:
        candidates.extend(request.form.getlist("notify_targets"))
    except Exception:
        pass

    out = []
    seen = set()
    for raw in candidates:
        parts = []
        if isinstance(raw, list):
            parts = raw
        elif isinstance(raw, dict):
            parts = [raw]
        else:
            txt = str(raw or "").strip()
            if not txt:
                continue
            if txt.startswith("[") and txt.endswith("]"):
                try:
                    parsed = json.loads(txt)
                    if isinstance(parsed, list):
                        parts = parsed
                except Exception:
                    parts = []
        for item in parts:
            if not isinstance(item, dict):
                continue
            oid = str(item.get("open_id") or "").strip()
            name = str(item.get("name") or "").strip()
            key = f"{oid}|{name}"
            if (not oid and not name) or key in seen:
                continue
            seen.add(key)
            out.append({"open_id": oid, "name": name})
    return out


def _xiaotu_resolve_notify_names(
    open_ids,
    notify_targets,
    *,
    _xiaotu_query_user_names_by_open_ids,
):
    ids = []
    seen_ids = set()
    for raw in (open_ids or []):
        oid = str(raw or "").strip()
        if oid and oid not in seen_ids:
            seen_ids.add(oid)
            ids.append(oid)
    fallback_name_map = {}
    for item in (notify_targets or []):
        if not isinstance(item, dict):
            continue
        oid = str(item.get("open_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if oid and name and oid not in fallback_name_map:
            fallback_name_map[oid] = name
    selected_notify_name_map = _xiaotu_query_user_names_by_open_ids(ids)
    out = []
    seen_names = set()
    for oid in ids:
        nm = str(selected_notify_name_map.get(oid) or fallback_name_map.get(oid) or "").strip()
        if not nm or nm in seen_names:
            continue
        seen_names.add(nm)
        out.append(nm)
    return out


def _xiaotu_resolve_notify_open_ids(
    open_ids,
    notify_targets,
    *,
    _xiaotu_lookup_open_id_by_name,
):
    out = []
    seen = set()
    for raw in (open_ids or []):
        oid = str(raw or "").strip()
        if oid.startswith("ou_") and oid not in seen:
            seen.add(oid)
            out.append(oid)
    for item in (notify_targets or []):
        if not isinstance(item, dict):
            continue
        oid = str(item.get("open_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not oid and name:
            oid = str(_xiaotu_lookup_open_id_by_name(name) or "").strip()
        if oid.startswith("ou_") and oid not in seen:
            seen.add(oid)
            out.append(oid)
    return out


def api_xiaotu_notify_targets_preview(
    *,
    _XIAOTU_REPORT_ESCALATION_USER,
    _xiaotu_get_department_leader_user_id,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_pick_primary_department,
    jsonify,
    request,
    session,
):
    try:
        data = request.get_json(silent=True) or {}
        input_name = str(data.get('user_name') or session.get('feishu_user_name') or '').strip()
        if not input_name:
            return jsonify({'success': False, 'message': '请提供飞书用户名'}), 400

        session_user_name = str(session.get('feishu_user_name') or '').strip()
        session_user_id = str(session.get('feishu_user_id') or '').strip()
        uploader_open_id = ""
        source = ""
        if session_user_name and input_name == session_user_name and session_user_id.startswith("ou_"):
            uploader_open_id = session_user_id
            source = "session"
        if not uploader_open_id:
            uploader_open_id = _xiaotu_lookup_open_id_by_name(input_name)
            source = "feishu_id_table"
        if not uploader_open_id:
            return jsonify({'success': False, 'message': f'未找到用户“{input_name}”对应的open_id'}), 404

        primary_dept_id, primary_dept_name = _xiaotu_pick_primary_department(uploader_open_id)
        dept_leader_user_id = _xiaotu_get_department_leader_user_id(primary_dept_id)
        is_uploader_leader = bool(dept_leader_user_id) and (uploader_open_id == dept_leader_user_id)

        targets = []
        seen = set()

        def add_target(open_id, role, user_name=""):
            oid = str(open_id or "").strip()
            if not oid or oid in seen:
                return
            seen.add(oid)
            targets.append({
                'open_id': oid,
                'role': role,
                'user_name': str(user_name or "").strip()
            })

        add_target(uploader_open_id, "self", input_name)
        if is_uploader_leader:
            escalation_name = str(_XIAOTU_REPORT_ESCALATION_USER or '').strip()
            escalation_open_id = _xiaotu_lookup_open_id_by_name(escalation_name)
            if escalation_open_id:
                add_target(escalation_open_id, "escalation", escalation_name)
        elif dept_leader_user_id:
            add_target(dept_leader_user_id, "department_leader")

        return jsonify({
            'success': True,
            'message': '已计算通知目标（仅预览，不发送消息）',
            'data': {
                'input_user_name': input_name,
                'input_user_open_id': uploader_open_id,
                'open_id_source': source,
                'primary_department_id': primary_dept_id,
                'primary_department_name': primary_dept_name,
                'department_leader_open_id': dept_leader_user_id,
                'is_input_user_department_leader': is_uploader_leader,
                'notify_policy': "成员提交->部门leader_user_id+自己；负责人提交->陶晓飞+自己",
                'notify_targets': targets
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'预览失败: {str(e)}'}), 500


def api_xiaotu_notify_departments(
    *,
    _xiaotu_list_notify_departments,
    jsonify,
    permission_manager,
    session,
):
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录', 'data': []}), 401
        all_departments = _xiaotu_list_notify_departments()
        user_dept_ids = set()
        try:
            user_rows = permission_manager.get_user_departments(user_id) or []
        except Exception:
            user_rows = []
        for row in user_rows:
            if not isinstance(row, dict):
                continue
            dep_id = str(row.get("department_id") or "").strip()
            if dep_id:
                user_dept_ids.add(dep_id)
        for one in all_departments:
            dep_id = str(one.get("department_id") or "").strip()
            one["is_user_department"] = bool(dep_id in user_dept_ids)
        all_departments.sort(key=lambda x: (0 if x.get("is_user_department") else 1, str(x.get("department_name") or ""), str(x.get("department_id") or "")))
        return jsonify({'success': True, 'data': all_departments})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'data': []}), 500


def api_xiaotu_notify_users(
    *,
    _xiaotu_list_notify_users_current_app,
    jsonify,
    request,
    session,
):
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录', 'data': []}), 401
        department_id = str(request.args.get('department_id') or '').strip()
        if not department_id:
            return jsonify({'success': False, 'message': '请提供department_id', 'data': []}), 400
        if not (department_id.startswith("od_") or department_id.startswith("od-")):
            return jsonify({'success': False, 'message': 'department_id格式无效', 'data': []}), 400

        payload = _xiaotu_list_notify_users_current_app(department_id)
        for one in payload:
            one['is_self'] = bool(str(one.get('open_id') or '').strip() == user_id)
        return jsonify({'success': True, 'data': payload, 'department_id': department_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'data': []}), 500


def api_xiaotu_notify_search(
    *,
    _xiaotu_search_notify_users,
    jsonify,
    request,
    session,
):
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录', 'data': []}), 401
        keyword = str(request.args.get('keyword') or request.args.get('q') or '').strip()
        if not keyword:
            return jsonify({'success': True, 'data': [], 'keyword': keyword})
        payload = _xiaotu_search_notify_users(keyword, limit=50)
        for one in payload:
            one['is_self'] = bool(str(one.get('open_id') or '').strip() == user_id)
        return jsonify({'success': True, 'data': payload, 'keyword': keyword})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'data': []}), 500
