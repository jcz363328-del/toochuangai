"""Xiaoha history loading and rendering."""


def load_db_history_records(
    feature_key,
    account_name,
    limit,
    A_PLUS_REFERENCE_LAB_FEATURE_KEY,
    Any,
    DB_HISTORY_TABLE,
    Path,
    _db_history_can_view_all,
    build_history_thumbnail_source,
    convert_history_path_to_public_url,
    ensure_history_thumbnail,
    execute_db_query,
    format_history_datetime,
    get_feature_name_by_key,
    resolve_db_history_image_path,
):
    safe_limit = max(int(limit), 1)
    normalized_account = str(account_name or "admin").strip() or "admin"
    feature_name = get_feature_name_by_key(feature_key)
    feature_names = [feature_name]
    if feature_key == A_PLUS_REFERENCE_LAB_FEATURE_KEY:
        feature_names.append("A+测试")
    feature_names = list(dict.fromkeys(name for name in feature_names if name))
    feature_placeholders = ", ".join("%s" for _ in feature_names)
    if _db_history_can_view_all(normalized_account):
        query = (
            f"SELECT TOP {safe_limit} ZhangHao, GongNeng, MoXing, TuPian, RiQi "
            f"FROM {DB_HISTORY_TABLE} "
            f"WHERE GongNeng IN ({feature_placeholders}) "
            f"ORDER BY RiQi DESC, ID DESC"
        )
        rows = execute_db_query(query, tuple(feature_names))
    else:
        query = (
            f"SELECT TOP {safe_limit} ZhangHao, GongNeng, MoXing, TuPian, RiQi "
            f"FROM {DB_HISTORY_TABLE} "
            f"WHERE ZhangHao = %s AND GongNeng IN ({feature_placeholders}) "
            f"ORDER BY RiQi DESC, ID DESC"
        )
        rows = execute_db_query(query, (normalized_account, *feature_names))
    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        account_value = str(row[0] if len(row) > 0 else "").strip()
        feature_name_value = str(row[1] if len(row) > 1 else "").strip()
        model_value = str(row[2] if len(row) > 2 else "").strip()
        created_at = format_history_datetime(row[4] if len(row) > 4 else "")
        image_path = resolve_db_history_image_path(
            str(row[3] if len(row) > 3 else "").strip(),
            account_name=account_value,
            feature_name=feature_name_value,
            created_at_text=created_at,
        )
        if not image_path:
            continue
        thumbnail_path = ensure_history_thumbnail(image_path)
        thumbnail_source = convert_history_path_to_public_url(thumbnail_path or image_path)
        original_source = convert_history_path_to_public_url(image_path)
        local_thumbnail_source = ""
        try:
            thumbnail_candidate = Path(str(thumbnail_path or "").strip())
            image_candidate = Path(str(image_path or "").strip())
            if thumbnail_candidate.exists() and thumbnail_candidate.is_file() and thumbnail_candidate != image_candidate:
                local_thumbnail_source = str(thumbnail_candidate)
            else:
                local_thumbnail_source = build_history_thumbnail_source(str(image_path))
        except Exception:
            local_thumbnail_source = str(thumbnail_path or image_path)
        records.append(
            {
                "account_name": account_value,
                "feature_key": feature_key,
                "feature_name": feature_name_value,
                "model": model_value,
                "images": [thumbnail_source or original_source],
                "original_images": [original_source],
                "thumbnail_images": [thumbnail_source or original_source],
                "local_images": [local_thumbnail_source],
                "local_original_images": [str(image_path)],
                "created_at": created_at,
                "image_index": index,
            }
        )
    return records


def get_feature_history_records(
    feature_key,
    account_name,
    limit,
    _db_history_can_view_all,
    load_db_history_records,
    st,
):
    normalized_account = str(account_name or "admin").strip() or "admin"
    normalized_feature = str(feature_key or "").strip()
    try:
        db_records = load_db_history_records(normalized_feature, normalized_account, limit=limit)
    except Exception:
        db_records = []
    if db_records:
        return db_records[: max(int(limit), 1)]
    if _db_history_can_view_all(normalized_account):
        merged_records = []
        for user_store in (st.session_state.local_history_records or {}).values():
            merged_records.extend(list(dict(user_store or {}).get(normalized_feature) or []))
    else:
        user_store = dict((st.session_state.local_history_records or {}).get(normalized_account) or {})
        merged_records = list(user_store.get(normalized_feature) or [])
    merged_records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return merged_records[: max(int(limit), 1)]


def render_history_gallery(
    items,
    key_prefix,
    columns_per_row,
    thumb_height,
    enable_a_plus_crop_downloads,
    MAIN_IMAGE_A_PLUS_FEATURE_KEY,
    build_history_download_archive_bytes,
    build_history_download_public_url,
    datetime,
    get_history_columns_per_row,
    get_history_item_selection_key,
    html,
    is_main_image_a_plus_mobile_canvas,
    partial,
    render_main_image_a_plus_crop_downloads,
    render_main_image_a_plus_text_editor,
    render_zoomable_image_gallery,
    st,
    submit_main_image_a_plus_mobile_adaptation,
):
    if not items:
        return
    selection_keys = [
        get_history_item_selection_key(key_prefix, item, item_index)
        for item_index, item in enumerate(items)
    ]
    toolbar_columns = st.columns([1, 1, 2], gap="small")
    with toolbar_columns[0]:
        if st.button(
            "全选当前图片",
            key=f"{key_prefix}_select_all",
            use_container_width=True,
            icon=":material/select_all:",
        ):
            for selection_key in selection_keys:
                st.session_state[selection_key] = True
    with toolbar_columns[1]:
        if st.button(
            "取消全选",
            key=f"{key_prefix}_clear_selection",
            use_container_width=True,
            icon=":material/deselect:",
        ):
            for selection_key in selection_keys:
                st.session_state[selection_key] = False
    selected_count = sum(bool(st.session_state.get(selection_key, False)) for selection_key in selection_keys)
    with toolbar_columns[2]:
        st.caption(f"已选择 {selected_count} / {len(items)} 张；勾选后可下载一个 ZIP 压缩包。")

    normalized_columns_per_row = max(int(columns_per_row or get_history_columns_per_row(len(items))), 1)
    for row_start in range(0, len(items), normalized_columns_per_row):
        row_items = items[row_start : row_start + normalized_columns_per_row]
        columns = st.columns(normalized_columns_per_row, gap="medium")
        for column_index, column in enumerate(columns):
            if column_index >= len(row_items):
                continue
            item = row_items[column_index]
            with column:
                created_at = str(item.get("created_at") or "")
                model_name = str(item.get("model") or "")
                feature_name = str(item.get("feature_name") or "")
                download_source = str(item.get("download_source") or "").strip()
                item_index = row_start + column_index
                st.checkbox(
                    "选择此图",
                    key=selection_keys[item_index],
                )
                fullscreen_href = ""
                if download_source:
                    try:
                        fullscreen_href = build_history_download_public_url(download_source)
                    except Exception:
                        fullscreen_href = str(item.get("original_image") or "").strip()
                if not fullscreen_href:
                    fullscreen_href = str(item.get("original_image") or "").strip()
                meta_parts: list[str] = ['<div class="history-card-meta">']
                if created_at:
                    meta_parts.append(f'<div class="history-card-time">{html.escape(created_at)}</div>')
                if feature_name:
                    meta_parts.append(f'<div class="history-card-model">{html.escape(feature_name)}</div>')
                if model_name:
                    meta_parts.append(f'<div class="history-card-model">{html.escape(model_name)}</div>')
                meta_parts.append("</div>")
                st.markdown("".join(meta_parts), unsafe_allow_html=True)
                render_zoomable_image_gallery(
                    [str(item.get("display_image") or "")],
                    columns=1,
                    thumb_height=thumb_height,
                    component_key=f"{key_prefix}_{row_start}_{column_index}",
                    fit_mode="cover",
                    max_width_percent=100,
                    compress_preview=True,
                    include_full_src=True,
                    full_images=[fullscreen_href or str(item.get("display_image") or "")],
                    download_names=[str(item.get("download_name") or "")],
                    embed_full_src=False,
                    native_fullscreen_context_menu=True,
                )
                if enable_a_plus_crop_downloads and download_source:
                    render_main_image_a_plus_crop_downloads(
                        [download_source],
                        key_prefix=f"{key_prefix}_crop_{row_start + column_index}",
                        base_names=[str(item.get("download_name") or "")],
                    )
                    render_main_image_a_plus_text_editor(
                        download_source,
                        key_prefix=f"{key_prefix}_text_edit_{row_start + column_index}",
                    )
                    dimension_source = str(item.get("display_image") or download_source).strip()
                    if not is_main_image_a_plus_mobile_canvas(dimension_source):
                        mobile_adaptation_active = str(
                            (st.session_state.background_jobs.get(MAIN_IMAGE_A_PLUS_FEATURE_KEY) or {}).get("status")
                            or ""
                        ).strip().lower() in {"queued", "running"}
                        if st.button(
                            "生成手机端适配版",
                            key=f"{key_prefix}_mobile_{row_start + column_index}",
                            type="primary",
                            use_container_width=True,
                            disabled=mobile_adaptation_active,
                        ):
                            submit_main_image_a_plus_mobile_adaptation(download_source)
                            st.rerun()

    selected_items = [
        item
        for item, selection_key in zip(items, selection_keys)
        if bool(st.session_state.get(selection_key, False))
    ]
    selected_count = len(selected_items)
    archive_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        f"批量下载已选图片（{selected_count} 张）",
        data=partial(build_history_download_archive_bytes, selected_items),
        file_name=f"history_images_{archive_timestamp}_{selected_count}.zip",
        mime="application/zip",
        key=f"{key_prefix}_batch_download",
        type="primary",
        icon=":material/folder_zip:",
        disabled=selected_count == 0,
        use_container_width=True,
        on_click="ignore",
    )


def render_history_toggle(
    feature,
    HISTORY_PAGE_SIZE,
    ensure_history_records_loaded,
    get_history_cache_key,
    set_history_visible_limit,
    st,
):
    account_name = str(st.session_state.get("auth_username") or "admin")
    cache_key = get_history_cache_key(account_name, feature["key"])
    is_expanded = bool(st.session_state.history_panel_expanded.get(cache_key, False))
    button_label = "展开历史图片" if not is_expanded else "收起历史图片"
    if st.button(button_label, key=f"toggle_history_{feature['key']}"):
        next_state = not is_expanded
        st.session_state.history_panel_expanded[cache_key] = next_state
        if next_state:
            set_history_visible_limit(cache_key, HISTORY_PAGE_SIZE)
            ensure_history_records_loaded(feature["key"], account_name, cache_key, HISTORY_PAGE_SIZE)
        st.rerun()


def render_history_records(
    feature,
    show_toggle,
    HISTORY_PAGE_SIZE,
    MAIN_IMAGE_A_PLUS_FEATURE_KEY,
    ensure_history_records_loaded,
    flatten_history_items,
    get_history_cache_key,
    get_history_visible_limit,
    render_history_gallery,
    set_history_visible_limit,
    st,
):
    account_name = str(st.session_state.get("auth_username") or "admin")
    cache_key = get_history_cache_key(account_name, feature["key"])
    is_expanded = bool(st.session_state.history_panel_expanded.get(cache_key, False))
    button_label = "加载历史记录" if not is_expanded else "收起历史记录"
    button_icon = ":material/history:" if not is_expanded else ":material/expand_less:"
    if not show_toggle:
        is_expanded = True
    else:
        if st.button(
            button_label,
            key=f"lazy_history_{feature['key']}",
            use_container_width=True,
            type="secondary",
            icon=button_icon,
        ):
            next_state = not is_expanded
            st.session_state.history_panel_expanded[cache_key] = next_state
            if next_state:
                set_history_visible_limit(cache_key, HISTORY_PAGE_SIZE)
            st.rerun()
    if not is_expanded:
        return

    if cache_key not in st.session_state.history_visible_counts:
        set_history_visible_limit(cache_key, HISTORY_PAGE_SIZE)
    visible_limit = get_history_visible_limit(cache_key)
    records = ensure_history_records_loaded(feature["key"], account_name, cache_key, visible_limit)
    st.markdown('<div class="result-block-title">全部历史图片</div>', unsafe_allow_html=True)
    if not records:
        st.caption("暂无历史图片")
        return
    history_items = flatten_history_items(records[:visible_limit])
    st.caption(f"当前先显示前 {len(history_items)} 张，点击放大后可右击或拖动保存原图")
    if history_items:
        render_history_gallery(
            history_items,
            key_prefix=f"history_{feature['key']}",
            enable_a_plus_crop_downloads=(feature["key"] == MAIN_IMAGE_A_PLUS_FEATURE_KEY),
        )
    if len(records) >= visible_limit:
        if st.button("继续加载 20 条", key=f"history_more_{feature['key']}"):
            next_limit = visible_limit + HISTORY_PAGE_SIZE
            set_history_visible_limit(cache_key, next_limit)
            ensure_history_records_loaded(feature["key"], account_name, cache_key, next_limit)
            st.rerun()


def render_side_history_panel(
    feature,
    HISTORY_PAGE_SIZE,
    MAIN_IMAGE_A_PLUS_FEATURE_KEY,
    ensure_history_records_loaded,
    flatten_history_items,
    get_history_cache_key,
    get_history_visible_limit,
    render_history_gallery,
    set_history_visible_limit,
    st,
):
    account_name = str(st.session_state.get("auth_username") or "admin")
    cache_key = get_history_cache_key(account_name, feature["key"])
    is_expanded = bool(st.session_state.history_panel_expanded.get(cache_key, False))
    button_label = "展开历史图片" if not is_expanded else "收起历史图片"
    st.markdown('<div class="side-history-shell">', unsafe_allow_html=True)
    st.markdown('<div class="side-history-title">全部历史图片</div>', unsafe_allow_html=True)
    if st.button(button_label, key=f"side_toggle_history_{feature['key']}", use_container_width=True, type="secondary"):
        next_state = not is_expanded
        st.session_state.history_panel_expanded[cache_key] = next_state
        if next_state:
            set_history_visible_limit(cache_key, HISTORY_PAGE_SIZE)
            ensure_history_records_loaded(feature["key"], account_name, cache_key, HISTORY_PAGE_SIZE)
        st.rerun()
    if not st.session_state.history_panel_expanded.get(cache_key, False):
        st.markdown("</div>", unsafe_allow_html=True)
        return
    visible_limit = get_history_visible_limit(cache_key)
    records = ensure_history_records_loaded(feature["key"], account_name, cache_key, visible_limit)
    if not records:
        st.caption("暂无历史图片")
        st.markdown("</div>", unsafe_allow_html=True)
        return
    history_items = flatten_history_items(records[:visible_limit])
    st.caption(f"当前先显示前 {len(history_items)} 张，下面可继续加载更多，点击放大后可右击或拖动保存原图")
    if history_items:
        render_history_gallery(
            history_items,
            key_prefix=f"side_history_{feature['key']}",
            columns_per_row=1,
            thumb_height=220,
            enable_a_plus_crop_downloads=(feature["key"] == MAIN_IMAGE_A_PLUS_FEATURE_KEY),
        )
    if len(records) >= visible_limit:
        if st.button("继续加载 20 条", key=f"side_history_more_{feature['key']}", use_container_width=True, type="secondary"):
            next_limit = visible_limit + HISTORY_PAGE_SIZE
            set_history_visible_limit(cache_key, next_limit)
            ensure_history_records_loaded(feature["key"], account_name, cache_key, next_limit)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
