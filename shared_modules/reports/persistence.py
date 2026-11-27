def _xiaotu_read_report_memory_context(
    user_name,
    TUCHUANGAI_STORAGE_ROOT,
    render_report_memory_context,
):
    return render_report_memory_context(
        storage_root=TUCHUANGAI_STORAGE_ROOT,
        user_name=user_name,
        max_chars=16000,
    )



def _xiaotu_upsert_report_memory_path(
    user_name,
    file_path,
    _xiaotu_sql_escape,
    dui_db,
):
    name = str(user_name or "").strip()
    path = str(file_path or "").strip()
    if not name or not path:
        raise ValueError("日报整合用户名或文件路径为空")
    name_esc = _xiaotu_sql_escape(name)
    path_esc = _xiaotu_sql_escape(path)
    dui_db(f"""
        IF OBJECT_ID(N'dbo.baogao_zhenghe', N'U') IS NULL
            THROW 50001, N'缺少数据表 dbo.baogao_zhenghe', 1;

        IF EXISTS (
            SELECT 1
            FROM dbo.baogao_zhenghe WITH (UPDLOCK, HOLDLOCK)
            WHERE yonghu = N'{name_esc}'
        )
        BEGIN
            UPDATE dbo.baogao_zhenghe
            SET zhenghe = N'{path_esc}'
            WHERE yonghu = N'{name_esc}';
        END
        ELSE
        BEGIN
            INSERT INTO dbo.baogao_zhenghe (yonghu, zhenghe)
            VALUES (N'{name_esc}', N'{path_esc}');
        END
    """)



def _xiaotu_update_report_memory(
    user_name,
    user_open_id,
    report_id,
    report_date,
    report_material,
    is_edit,
    TUCHUANGAI_STORAGE_ROOT,
    _xiaotu_generate_report_memory_json,
    _xiaotu_upsert_report_memory_path,
    update_report_memory_file,
):
    file_path, snapshot = update_report_memory_file(
        storage_root=TUCHUANGAI_STORAGE_ROOT,
        user_name=user_name,
        user_open_id=user_open_id,
        report_id=report_id,
        report_date=report_date,
        report_material=report_material,
        is_edit=bool(is_edit),
        ai_generate=_xiaotu_generate_report_memory_json,
    )
    _xiaotu_upsert_report_memory_path(user_name, file_path)
    return file_path, snapshot



def _xiaotu_remove_report_feedback_entry(
    wendangid,
    user_name,
    entry_type,
    entry_index,
    _xiaotu_feedback_entries_to_text,
    _xiaotu_parse_feedback_entries,
    _xiaotu_sql_escape,
    dui_db,
    sf_db,
):
    wid = str(wendangid or "").strip()
    actor = str(user_name or "").strip()
    kind = str(entry_type or "").strip().lower()
    if not wid:
        return False, "缺少日报ID"
    if not actor:
        return False, "未获取到当前用户"
    if kind not in {"comment", "reply"}:
        return False, "不支持的撤销类型"
    try:
        idx = int(entry_index)
    except Exception:
        return False, "缺少要撤销的记录"
    if idx < 0:
        return False, "撤销记录无效"
    esc_wid = _xiaotu_sql_escape(wid)
    field_name = "PingJia" if kind == "comment" else "HuiFu"
    rows = sf_db(f"SELECT TOP 1 {field_name} FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}'") or []
    row = rows[0] if isinstance(rows, list) and rows else rows
    if isinstance(row, dict):
        raw_text = str(row.get(field_name) or row.get(field_name.lower()) or "").strip()
    elif isinstance(row, (list, tuple)):
        raw_text = str(row[0] if len(row) > 0 else "").strip()
    else:
        raw_text = ""
    items = _xiaotu_parse_feedback_entries(raw_text, kind)
    if idx >= len(items):
        return False, "未找到要撤销的记录"
    target_item = items[idx] if isinstance(items[idx], dict) else {}
    item_actor = str(target_item.get("actor") or "").strip()
    if item_actor != actor:
        return False, "只能撤销自己提交的内容"
    new_items = [item for pos, item in enumerate(items) if pos != idx]
    new_text = _xiaotu_feedback_entries_to_text(new_items, kind)
    esc_new_text = _xiaotu_sql_escape(new_text)
    sql = f"""
        UPDATE BaoGao_dianzan
        SET {field_name}=N'{esc_new_text}'
        WHERE WenDangID='{esc_wid}'
    """
    try:
        dui_db(sql)
        return True, ""
    except Exception as e:
        return False, str(e)



def _xiaotu_get_report_feedback(
    wendangid,
    owner_name,
    _xiaotu_enrich_feedback_data,
    _xiaotu_sql_escape,
    sf_db,
):
    wid = str(wendangid or "").strip()
    if not wid:
        return _xiaotu_enrich_feedback_data({"dianzan": "", "pinglun": "", "huifu": "", "yonghu": ""}, owner_name=owner_name)
    esc_wid = _xiaotu_sql_escape(wid)
    sql = f"SELECT TOP 1 DianZan, PingJia, HuiFu, YongHu FROM BaoGao_dianzan WHERE WenDangID='{esc_wid}'"
    row = sf_db(sql) or []
    if isinstance(row, list) and row and isinstance(row[0], dict):
        row = row[0]
    if isinstance(row, list) and row and isinstance(row[0], (list, tuple)):
        row = row[0]
    if isinstance(row, dict):
        return _xiaotu_enrich_feedback_data({
            "dianzan": str(row.get("dianzan") or row.get("DianZan") or "").strip(),
            "pinglun": str(row.get("pinglun") or row.get("PingLun") or row.get("PingJia") or "").strip(),
            "huifu": str(row.get("huifu") or row.get("HuiFu") or "").strip(),
            "yonghu": str(row.get("yonghu") or row.get("YongHu") or "").strip(),
        }, owner_name=owner_name)
    if isinstance(row, (list, tuple)):
        return _xiaotu_enrich_feedback_data({
            "dianzan": str(row[0] if len(row) > 0 else "").strip(),
            "pinglun": str(row[1] if len(row) > 1 else "").strip(),
            "huifu": str(row[2] if len(row) > 2 else "").strip(),
            "yonghu": str(row[3] if len(row) > 3 else "").strip(),
        }, owner_name=owner_name)
    return _xiaotu_enrich_feedback_data({"dianzan": "", "pinglun": "", "huifu": "", "yonghu": ""}, owner_name=owner_name)



def _xiaotu_report_history_is_visible_to_user(
    wendangid,
    user_name,
    _xiaotu_build_report_history_export_context,
    _xiaotu_sql_escape,
    sf_db,
):
    """Return whether the report is present in either history list for this user."""
    wid = str(wendangid or "").strip()
    name = str(user_name or "").strip()
    if not wid or not name:
        return False
    ctx = _xiaotu_build_report_history_export_context({}, name)
    esc_wid = _xiaotu_sql_escape(wid)
    rows = sf_db(f"""
        SELECT TOP 1 b.WenDangID
        FROM baogao b
        WHERE b.WenDangID = '{esc_wid}'
          AND (
            ({ctx['uploaded_where_sql']})
            OR
            ({ctx['received_where_sql']})
          )
    """) or []
    return bool(rows)

