"""Persist report drafts and notification settings."""

from __future__ import annotations


def _xiaotu_build_notify_cache_text(
    open_ids,
    notify_targets,
    *,
    _XIAOTU_NOTIFY_CACHE_PREFIX,
    _xiaotu_query_user_names_by_open_ids,
    json,
):
    resolved_open_ids = []
    seen_open_ids = set()
    for raw in (open_ids or []):
        oid = str(raw or "").strip()
        if not oid.startswith("ou_") or oid in seen_open_ids:
            continue
        seen_open_ids.add(oid)
        resolved_open_ids.append(oid)
    fallback_name_map = {}
    for item in (notify_targets or []):
        if not isinstance(item, dict):
            continue
        oid = str(item.get("open_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if oid.startswith("ou_") and name and oid not in fallback_name_map:
            fallback_name_map[oid] = name
    resolved_name_map = _xiaotu_query_user_names_by_open_ids(resolved_open_ids)
    normalized_targets = []
    for oid in resolved_open_ids:
        normalized_targets.append({
            "open_id": oid,
            "name": str(resolved_name_map.get(oid) or fallback_name_map.get(oid) or "").strip(),
        })
    payload = {
        "version": 2,
        "notify_open_ids": resolved_open_ids,
        "notify_targets": normalized_targets,
    }
    return _XIAOTU_NOTIFY_CACHE_PREFIX + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _xiaotu_parse_notify_cache_text(
    raw_text,
    *,
    _XIAOTU_NOTIFY_CACHE_PREFIX,
    _xiaotu_query_user_names_by_open_ids,
    _xiaotu_resolve_notify_open_ids,
    json,
):
    text = str(raw_text or "").strip()
    if not text.startswith(_XIAOTU_NOTIFY_CACHE_PREFIX):
        return None
    payload_text = text[len(_XIAOTU_NOTIFY_CACHE_PREFIX):].strip()
    if not payload_text:
        return {
            "notify_names": [],
            "notify_targets": [],
            "notify_open_ids": [],
        }
    try:
        payload = json.loads(payload_text)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    raw_targets = payload.get("notify_targets")
    notify_targets = raw_targets if isinstance(raw_targets, list) else []
    notify_open_ids = _xiaotu_resolve_notify_open_ids(payload.get("notify_open_ids"), notify_targets)
    if not notify_open_ids:
        return {
            "notify_names": [],
            "notify_targets": [],
            "notify_open_ids": [],
        }
    resolved_name_map = _xiaotu_query_user_names_by_open_ids(notify_open_ids)
    fallback_name_map = {}
    for item in notify_targets:
        if not isinstance(item, dict):
            continue
        oid = str(item.get("open_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if oid.startswith("ou_") and name and oid not in fallback_name_map:
            fallback_name_map[oid] = name
    normalized_targets = []
    notify_names = []
    seen_names = set()
    for oid in notify_open_ids:
        name = str(resolved_name_map.get(oid) or fallback_name_map.get(oid) or "").strip()
        normalized_targets.append({
            "name": name,
            "open_id": oid,
        })
        if name and name not in seen_names:
            seen_names.add(name)
            notify_names.append(name)
    return {
        "notify_names": notify_names,
        "notify_targets": normalized_targets,
        "notify_open_ids": notify_open_ids,
    }


def _xiaotu_get_report_cache(
    user_name,
    *,
    _XIAOTU_REPORT_CACHE_TABLE_FALLBACK,
    _XIAOTU_REPORT_CACHE_TABLE_PRIMARY,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_normalize_notify_time,
    _xiaotu_parse_notify_cache_text,
    _xiaotu_resolve_notify_names,
    _xiaotu_split_cache_multi_value,
    _xiaotu_sql_escape,
    sf_db,
):
    name = str(user_name or "").strip()
    if not name:
        return {
            "user_name": "",
            "notify_names": [],
            "notify_targets": [],
            "notify_open_ids": [],
            "notify_time": "",
            "draft_html": "",
            "image_paths": []
        }
    esc_name = _xiaotu_sql_escape(name)
    sql = f"""
        IF OBJECT_ID(N'{_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}', N'U') IS NOT NULL
            SELECT TOP 1 ID, YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin, TongZhiShiJian
            FROM {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}
            WHERE YongHu = N'{esc_name}'
            ORDER BY ID DESC
        ELSE
            SELECT TOP 1 ID, YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin, CAST(N'' AS NVARCHAR(20)) AS TongZhiShiJian
            FROM {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK}
            WHERE YongHu = N'{esc_name}'
            ORDER BY ID DESC
    """
    rows = sf_db(sql) or []
    row = rows[0] if rows else {}
    if isinstance(row, (list, tuple)):
        row = {
            "ID": row[0] if len(row) > 0 else None,
            "YongHu": row[1] if len(row) > 1 else "",
            "TiJiaoRen": row[2] if len(row) > 2 else "",
            "HuanCunWenBen": row[3] if len(row) > 3 else "",
            "TuPianLuJin": row[4] if len(row) > 4 else "",
            "TongZhiShiJian": row[5] if len(row) > 5 else "",
        }
    elif not isinstance(row, dict):
        row = {}
    notify_raw = row.get("TiJiaoRen") or row.get("tijiaoren") or ""
    parsed_notify_cache = _xiaotu_parse_notify_cache_text(notify_raw)
    if parsed_notify_cache is not None:
        notify_names = parsed_notify_cache.get("notify_names") or []
        notify_targets = parsed_notify_cache.get("notify_targets") or []
        notify_open_ids = parsed_notify_cache.get("notify_open_ids") or []
    else:
        notify_names = _xiaotu_split_cache_multi_value(notify_raw)
        notify_targets = []
        notify_open_ids = []
        seen_open_ids = set()
        for nm in notify_names:
            oid = str(_xiaotu_lookup_open_id_by_name(nm) or "").strip()
            if not oid.startswith("ou_") or oid in seen_open_ids:
                continue
            seen_open_ids.add(oid)
            notify_open_ids.append(oid)
            notify_targets.append({"name": nm, "open_id": oid})
        notify_names = _xiaotu_resolve_notify_names(notify_open_ids, notify_targets)
    return {
        "user_name": name,
        "notify_names": notify_names,
        "notify_targets": notify_targets,
        "notify_open_ids": notify_open_ids,
        "notify_time": _xiaotu_normalize_notify_time(
            row.get("TongZhiShiJian") or row.get("tongzhishijian") or row.get("通知时间") or ""
        ),
        "draft_html": str(row.get("HuanCunWenBen") or row.get("huancunwenben") or "").strip(),
        "image_paths": _xiaotu_split_cache_multi_value(row.get("TuPianLuJin") or row.get("tupianlujin") or "")
    }


def _xiaotu_upsert_report_cache_notify(
    user_name,
    notify_open_ids,
    notify_targets,
    notify_time,
    *,
    _XIAOTU_REPORT_CACHE_TABLE_FALLBACK,
    _XIAOTU_REPORT_CACHE_TABLE_PRIMARY,
    _xiaotu_build_notify_cache_text,
    _xiaotu_normalize_notify_time,
    _xiaotu_sql_escape,
    dui_db,
):
    name = str(user_name or "").strip()
    if not name:
        return
    name_esc = _xiaotu_sql_escape(name)
    notify_text = _xiaotu_build_notify_cache_text(notify_open_ids, notify_targets)
    notify_esc = _xiaotu_sql_escape(notify_text)
    notify_time_esc = _xiaotu_sql_escape(_xiaotu_normalize_notify_time(notify_time))
    sql = f"""
        IF OBJECT_ID(N'{_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}', N'U') IS NOT NULL
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}
                SET TiJiaoRen = N'{notify_esc}',
                    TongZhiShiJian = N'{notify_time_esc}'
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin, TongZhiShiJian)
                VALUES (N'{name_esc}', N'{notify_esc}', N'', N'', N'{notify_time_esc}')
        END
        ELSE
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK}
                SET TiJiaoRen = N'{notify_esc}'
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin)
                VALUES (N'{name_esc}', N'{notify_esc}', N'', N'')
        END
    """
    dui_db(sql)


def _xiaotu_upsert_report_cache_draft(
    user_name,
    draft_html,
    image_paths,
    *,
    _XIAOTU_REPORT_CACHE_TABLE_FALLBACK,
    _XIAOTU_REPORT_CACHE_TABLE_PRIMARY,
    _xiaotu_split_cache_multi_value,
    _xiaotu_sql_escape,
    dui_db,
):
    name = str(user_name or "").strip()
    if not name:
        return
    name_esc = _xiaotu_sql_escape(name)
    html_esc = _xiaotu_sql_escape(draft_html)
    image_text = "|".join(_xiaotu_split_cache_multi_value("|".join(image_paths or [])))
    image_esc = _xiaotu_sql_escape(image_text)
    sql = f"""
        IF OBJECT_ID(N'{_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}', N'U') IS NOT NULL
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}
                SET HuanCunWenBen = N'{html_esc}',
                    TuPianLuJin = N'{image_esc}'
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin, TongZhiShiJian)
                VALUES (N'{name_esc}', N'', N'{html_esc}', N'{image_esc}', N'')
        END
        ELSE
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK}
                SET HuanCunWenBen = N'{html_esc}',
                    TuPianLuJin = N'{image_esc}'
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin)
                VALUES (N'{name_esc}', N'', N'{html_esc}', N'{image_esc}')
        END
    """
    dui_db(sql)


def _xiaotu_clear_report_cache_draft(
    user_name,
    *,
    _XIAOTU_REPORT_CACHE_TABLE_FALLBACK,
    _XIAOTU_REPORT_CACHE_TABLE_PRIMARY,
    _xiaotu_sql_escape,
    dui_db,
):
    name = str(user_name or "").strip()
    if not name:
        return
    name_esc = _xiaotu_sql_escape(name)
    sql = f"""
        IF OBJECT_ID(N'{_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}', N'U') IS NOT NULL
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY}
                SET HuanCunWenBen = N'',
                    TuPianLuJin = N''
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_PRIMARY} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin, TongZhiShiJian)
                VALUES (N'{name_esc}', N'', N'', N'', N'')
        END
        ELSE
        BEGIN
            IF EXISTS (SELECT 1 FROM {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} WHERE YongHu = N'{name_esc}')
                UPDATE {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK}
                SET HuanCunWenBen = N'',
                    TuPianLuJin = N''
                WHERE YongHu = N'{name_esc}'
            ELSE
                INSERT INTO {_XIAOTU_REPORT_CACHE_TABLE_FALLBACK} (YongHu, TiJiaoRen, HuanCunWenBen, TuPianLuJin)
                VALUES (N'{name_esc}', N'', N'', N'')
        END
    """
    dui_db(sql)
