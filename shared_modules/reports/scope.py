"""Resolve report visibility, recipient scopes and card context."""

from __future__ import annotations


def _xiaotu_get_report_history_scope(
    user_name,
    debug_mode,
    *,
    _XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES,
    _current_user_has_permission,
    _xiaotu_report_history_can_view_all_uploads,
):
    allowed_department_names = []
    normalized_debug_mode = str(debug_mode or "").strip().lower()
    if normalized_debug_mode == "all_uploads":
        return {
            "can_view_all_uploads": True,
            "restricted_to_allowed_departments": False,
            "allowed_department_names": [],
            "debug_mode": "all_uploads",
        }
    if normalized_debug_mode == "operation_only":
        return {
            "can_view_all_uploads": False,
            "restricted_to_allowed_departments": True,
            "allowed_department_names": list(_XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES),
            "debug_mode": "operation_only",
        }
    if normalized_debug_mode == "self_only":
        return {
            "can_view_all_uploads": False,
            "restricted_to_allowed_departments": False,
            "allowed_department_names": [],
            "debug_mode": "self_only",
        }
    if _current_user_has_permission('xiaotu_report_history_operation_3_scope'):
        allowed_department_names = ["运营三部"]
    elif _current_user_has_permission('xiaotu_report_history_operation_scope'):
        allowed_department_names = list(_XIAOTU_REPORT_HISTORY_OPERATION_DEPARTMENT_NAMES)
    return {
        "can_view_all_uploads": _xiaotu_report_history_can_view_all_uploads(),
        "restricted_to_allowed_departments": bool(allowed_department_names),
        "allowed_department_names": allowed_department_names,
        "debug_mode": "current",
    }


def _xiaotu_build_name_match_clause(
    column_name,
    names,
    *,
    _xiaotu_sql_escape,
    re,
):
    exact_names = []
    compact_names = []
    seen_exact = set()
    seen_compact = set()
    for raw_name in (names or []):
        name = str(raw_name or "").strip()
        if not name:
            continue
        if name not in seen_exact:
            seen_exact.add(name)
            exact_names.append(name)
        compact_name = re.sub(r"\s+", "", name)
        if compact_name and compact_name not in seen_compact:
            seen_compact.add(compact_name)
            compact_names.append(compact_name)
    clauses = []
    if exact_names:
        exact_sql = ", ".join([f"N'{_xiaotu_sql_escape(name)}'" for name in exact_names])
        clauses.append(f"{column_name} IN ({exact_sql})")
    if compact_names:
        compact_sql = ", ".join([f"N'{_xiaotu_sql_escape(name)}'" for name in compact_names])
        clauses.append(f"REPLACE(REPLACE({column_name}, N' ', N''), CHAR(9), N'') IN ({compact_sql})")
    if not clauses:
        return ""
    return "(" + " OR ".join(clauses) + ")"


def _xiaotu_collect_notify_user_names_by_department_names(
    department_names,
    *,
    _xiaotu_list_notify_departments,
    _xiaotu_list_notify_users_current_app_cached,
):
    target_names = []
    target_seen = set()
    for raw_name in (department_names or []):
        dept_name = str(raw_name or "").strip()
        if not dept_name or dept_name in target_seen:
            continue
        target_seen.add(dept_name)
        target_names.append(dept_name)
    if not target_names:
        return []

    all_departments = _xiaotu_list_notify_departments()
    wanted_ids = []
    wanted_name_set = set(target_names)
    for one in (all_departments or []):
        if not isinstance(one, dict):
            continue
        dept_name = str(one.get("department_name") or "").strip()
        dept_id = str(one.get("department_id") or "").strip()
        if dept_name in wanted_name_set and dept_id and dept_id not in wanted_ids:
            wanted_ids.append(dept_id)
    if not wanted_ids:
        return []

    user_names = []
    seen_names = set()
    for dept_id in wanted_ids:
        for one in (_xiaotu_list_notify_users_current_app_cached(dept_id) or []):
            if not isinstance(one, dict):
                continue
            name = str(one.get("name") or "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            user_names.append(name)
    return user_names


def _xiaotu_get_department_leader_user_id(
    department_id,
    *,
    _feishu_http,
    _safe_debug_print,
    permission_manager,
):
    dep_id = str(department_id or "").strip()
    if not dep_id:
        return ""
    try:
        dept_info = permission_manager.get_department_info(dep_id) or {}
    except Exception:
        dept_info = {}
    leader_id = str(
        (dept_info or {}).get("leader_user_id")
        or (dept_info or {}).get("leader_open_id")
        or (dept_info or {}).get("leader_userid")
        or ""
    ).strip()
    if leader_id.startswith("ou_") or leader_id.startswith("ou-"):
        return leader_id
    token = permission_manager.get_access_token()
    if not token:
        return ""
    try:
        resp = _feishu_http.get(
            f"https://open.feishu.cn/open-apis/contact/v3/departments/{dep_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
            params={
                "department_id_type": "open_department_id",
                "user_id_type": "open_id",
            },
            timeout=12,
        )
        data = resp.json() if resp is not None else {}
        if resp is not None and resp.status_code == 200 and isinstance(data, dict) and int(data.get("code") or 0) == 0:
            dept = ((data.get("data") or {}).get("department") or {})
            return str(
                dept.get("leader_user_id")
                or dept.get("leader_open_id")
                or dept.get("leader_userid")
                or ""
            ).strip()
    except Exception as e:
        _safe_debug_print(f"获取部门负责人失败: {dep_id} -> {e}")
    return ""


def _xiaotu_enrich_feedback_data(
    feedback,
    owner_name,
    *,
    _xiaotu_parse_feedback_entries,
    _xiaotu_parse_like_user_names,
):
    fb = dict(feedback or {})
    comments = _xiaotu_parse_feedback_entries(fb.get("pinglun") or "", "comment")
    replies = _xiaotu_parse_feedback_entries(fb.get("huifu") or "", "reply")
    legacy_actor = str(fb.get("yonghu") or "").strip()
    for item in comments:
        if not str((item or {}).get("actor") or "").strip() and legacy_actor:
            item["actor"] = legacy_actor
    for item in replies:
        if not str((item or {}).get("actor") or "").strip() and legacy_actor:
            item["actor"] = legacy_actor
    liked = str(fb.get("dianzan") or "").strip().upper() == "Y"
    if (not liked) and legacy_actor and not comments and not replies:
        # 兼容旧数据：历史上只有一个点赞人时，可能只在 YongHu 留了名字。
        liked = True
    like_users = _xiaotu_parse_like_user_names(legacy_actor) if liked else []
    targets = []
    seen = set()
    for name in [owner_name] + [x.get("actor") for x in comments] + [x.get("actor") for x in replies] + [x.get("target") for x in replies]:
        name = str(name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        targets.append(name)
    fb["like_users"] = like_users
    fb["like_count"] = len(like_users)
    fb["comment_items"] = comments
    fb["reply_items"] = replies
    fb["reply_targets"] = targets
    return fb


def _xiaotu_get_report_card_context(
    wendangid,
    *,
    _xiaotu_sql_escape,
    sf_db,
):
    wid = str(wendangid or "").strip()
    if not wid:
        return {}
    esc_wid = _xiaotu_sql_escape(wid)
    sql = f"""
        SELECT TOP 1 WenDangID, BiaoTi, ZhengWen, TuPianLujin, PingJia, RenYuanLeiXing, XingMing
        FROM baogao
        WHERE WenDangID='{esc_wid}'
    """
    row = sf_db(sql) or []
    if isinstance(row, list) and row:
        row = row[0]
    if isinstance(row, dict):
        return {
            "wendangid": str(row.get("WenDangID") or wid).strip(),
            "title_text": str(row.get("BiaoTi") or "").strip(),
            "source_text": str(row.get("ZhengWen") or "").strip(),
            "pingjia_text": str(row.get("PingJia") or "").strip(),
            "person_type": str(row.get("RenYuanLeiXing") or "").strip(),
            "owner_name": str(row.get("XingMing") or "").strip(),
            "image_paths_text": str(row.get("TuPianLujin") or "").strip(),
            "image_path": str(row.get("TuPianLujin") or "").split("|")[0].strip()
        }
    if isinstance(row, (list, tuple)):
        values = list(row)
        return {
            "wendangid": str(values[0] if len(values) > 0 else wid).strip(),
            "title_text": str(values[1] if len(values) > 1 else "").strip(),
            "source_text": str(values[2] if len(values) > 2 else "").strip(),
            "image_paths_text": str(values[3] if len(values) > 3 else "").strip(),
            "image_path": str(values[3] if len(values) > 3 else "").split("|")[0].strip(),
            "pingjia_text": str(values[4] if len(values) > 4 else "").strip(),
            "person_type": str(values[5] if len(values) > 5 else "").strip(),
            "owner_name": str(values[6] if len(values) > 6 else "").strip(),
        }
    return {}
