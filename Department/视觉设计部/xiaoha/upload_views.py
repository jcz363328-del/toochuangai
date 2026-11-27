"""Render Xiaoha upload previews and image selection controls."""

from __future__ import annotations

from typing import Any


def render_uploaded_preview_card(
    uploaded_input,
    widget_key,
    item_index,
    component_key,
    preview_renderer,
    allow_reorder,
    item_count,
    *,
    get_replace_uploader_widget_key,
    remove_upload_cache_item,
    render_frame_uploader,
    reorder_upload_cache_item,
    replace_upload_cache_item,
    reset_upload_widget,
    st,
) -> None:
    replacement_upload = render_frame_uploader(
        f"第 {item_index + 1} 张图片", type=["png", "jpg", "jpeg", "webp"],
        key=get_replace_uploader_widget_key(widget_key, item_index),
        preview_files=[uploaded_input], frame_height=300,
        remove_button_key=f"delete_upload_{component_key}_{item_index}",
        label_visibility="collapsed",
    )
    if replacement_upload is not None:
        replace_upload_cache_item(widget_key, item_index, replacement_upload)
        reset_upload_widget(widget_key)
        st.rerun()
    if preview_renderer is not None:
        preview_renderer(uploaded_input, item_index, component_key)
    controls = st.columns(3 if allow_reorder and item_count > 1 else 1)
    with controls[0]:
        if st.button("移除", key=f"delete_upload_{component_key}_{item_index}", help="移除这张图片"):
            remove_upload_cache_item(widget_key, item_index)
            reset_upload_widget(widget_key)
            st.rerun()
    if allow_reorder and item_count > 1:
        for column, label, target in zip(controls[1:], ("← 前移", "后移 →"), (item_index - 1, item_index + 1)):
            with column:
                if st.button(label, key=f"reorder_{component_key}_{target}", disabled=not 0 <= target < item_count):
                    reorder_upload_cache_item(widget_key, item_index, target)
                    reset_upload_widget(widget_key)
                    st.rerun()


def render_uploaded_gallery(
    files,
    empty_text,
    widget_key,
    slot_count,
    preview_renderer,
    allow_reorder,
    *,
    render_uploaded_preview_card,
    st,
) -> None:
    if not files:
        st.markdown(f'<div class="slot-helper">{empty_text}</div>', unsafe_allow_html=True)
        return
    columns_per_row = min(max(slot_count, 1), len(files), 3)
    for row_start in range(0, len(files), columns_per_row):
        columns = st.columns(columns_per_row)
        for column_index, column in enumerate(columns):
            item_index = row_start + column_index
            with column:
                if item_index < len(files):
                    render_uploaded_preview_card(
                        files[item_index],
                        widget_key=widget_key,
                        item_index=item_index,
                        component_key=f"upload_preview_{widget_key}_{item_index}",
                        preview_renderer=preview_renderer,
                        allow_reorder=allow_reorder,
                        item_count=len(files),
                    )
    if empty_text:
        st.markdown(f'<div class="slot-helper">{empty_text}</div>', unsafe_allow_html=True)


def render_single_image_uploader(
    label,
    key,
    help_text,
    *,
    clear_upload_cache,
    consume_pending_upload_replacement,
    get_uploader_widget_key,
    load_upload_cache,
    render_frame_uploader,
    reset_upload_widget,
    save_upload_cache,
    st,
) -> Any | None:
    cached_files = load_upload_cache(key, max_files=1)
    active_uploaded = cached_files[0] if cached_files else None

    uploaded = render_frame_uploader(
        label, type=["png", "jpg", "jpeg", "webp"],
        key=get_uploader_widget_key(key), preview_files=cached_files, frame_height=350,
        remove_button_key=f"clear_upload_{key}",
        help=help_text or None, label_visibility="collapsed",
    )
    if uploaded is not None:
        consume_pending_upload_replacement(key)
        save_upload_cache(key, [uploaded])
        reset_upload_widget(key)
        st.rerun()
    if st.button("清空上传", key=f"clear_upload_{key}", type="secondary"):
        clear_upload_cache(key)
        reset_upload_widget(key)
        st.rerun()

    st.caption("支持 Ctrl+V 直接粘贴图片到当前上传区域")
    return active_uploaded


def render_compact_element_image_uploader(
    label,
    key,
    help_text,
    *,
    clear_upload_cache,
    get_uploader_widget_key,
    load_upload_cache,
    render_frame_uploader,
    reset_upload_widget,
    save_upload_cache,
    st,
) -> Any | None:
    cached_files = load_upload_cache(key, max_files=1)
    active_uploaded = cached_files[0] if cached_files else None

    uploaded = render_frame_uploader(
        "更换素材" if active_uploaded is not None else label,
        type=["png", "jpg", "jpeg", "webp"],
        key=get_uploader_widget_key(key), preview_files=cached_files, frame_height=220,
        help=help_text or None,
        label_visibility="collapsed",
    )
    if uploaded is not None:
        save_upload_cache(key, [uploaded])
        reset_upload_widget(key)
        st.rerun()

    if active_uploaded is not None and st.button(
        "移除当前素材",
        key=f"clear_compact_element_upload_{key}",
        use_container_width=True,
        type="secondary",
    ):
        clear_upload_cache(key)
        reset_upload_widget(key)
        st.rerun()

    return active_uploaded


def render_multi_image_uploader(
    label,
    key,
    help_text,
    max_files,
    preview_renderer,
    preview_slot_count,
    allow_reorder,
    preview_area_height,
    show_clear_button,
    *,
    clear_upload_cache,
    consume_pending_upload_replacement,
    get_uploader_widget_key,
    load_upload_cache,
    render_frame_uploader,
    render_uploaded_gallery,
    reset_upload_widget,
    save_upload_cache,
    st,
) -> list[Any]:
    cached_files = load_upload_cache(key, max_files=max_files)
    active_uploaded_files = cached_files

    if active_uploaded_files:
        with st.container():
            render_uploaded_gallery(active_uploaded_files, "", key, preview_renderer=preview_renderer,
                                    slot_count=preview_slot_count or min(max_files, 5), allow_reorder=allow_reorder)
    uploaded_files = render_frame_uploader(
        label, type=["png", "jpg", "jpeg", "webp"], key=get_uploader_widget_key(key),
        help=help_text or None, label_visibility="collapsed", accept_multiple_files=True,
        frame_height=200 if active_uploaded_files else 350,
    ) or []
    if uploaded_files:
        current_cache = load_upload_cache(key, max_files=max_files)
        replacement_index = consume_pending_upload_replacement(key)
        if replacement_index is not None and uploaded_files:
            combined = list(current_cache)
            if replacement_index < len(combined):
                combined[replacement_index] = list(uploaded_files)[0]
            else:
                combined.append(list(uploaded_files)[0])
        else:
            combined = current_cache + list(uploaded_files)
        combined = combined[:max_files]
        save_upload_cache(key, combined)
        reset_upload_widget(key)
        st.rerun()

    if show_clear_button and st.button("清空上传", key=f"clear_upload_{key}", type="secondary"):
        clear_upload_cache(key)
        reset_upload_widget(key)
        st.rerun()

    st.caption("支持 Ctrl+V 直接粘贴图片到当前上传区域")
    return active_uploaded_files


def render_reference_slot_uploaders(
    slot_prefix,
    slot_count,
    *,
    Any,
    consume_pending_upload_replacement,
    get_uploader_widget_key,
    load_upload_cache,
    render_frame_uploader,
    reset_upload_widget,
    save_upload_cache,
    st,
) -> list[Any]:
    uploaded_files: list[Any] = []
    columns = st.columns(slot_count)
    for index in range(slot_count):
        with columns[index]:
            slot_key = f"{slot_prefix}_{index}"
            cached_files = load_upload_cache(slot_key, max_files=1)
            active_uploaded = cached_files[0] if cached_files else None

            if active_uploaded is not None:
                uploaded_files.append(active_uploaded)

            uploaded = render_frame_uploader(
                "重新上传" if active_uploaded else "上传参考图",
                type=["png", "jpg", "jpeg", "webp"],
                key=get_uploader_widget_key(slot_key), preview_files=cached_files, frame_height=220,
                label_visibility="collapsed",
            )
            if uploaded is not None:
                consume_pending_upload_replacement(slot_key)
                save_upload_cache(slot_key, [uploaded])
                reset_upload_widget(slot_key)
                st.rerun()

    return uploaded_files
