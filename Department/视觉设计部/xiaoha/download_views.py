"""Render preview and upload components used by image features."""

from __future__ import annotations

from typing import Any


def render_outpaint_extension_preview(
    uploaded_files,
    top_px,
    bottom_px,
    left_px,
    right_px,
    *,
    render_outpaint_extension_preview_card,
    st,
) -> None:
    if not uploaded_files:
        return
    st.caption("虚线外框是扩展后的画布，虚线内框是原图边界。")
    render_outpaint_extension_preview_card(
        uploaded_files[0],
        top_px,
        bottom_px,
        left_px,
        right_px,
        "outpaint_inline_preview",
    )


def render_upload_delete_button(
    widget_key,
    item_index,
    button_key,
    *,
    remove_upload_cache_item,
    reset_upload_widget,
    st,
) -> None:
    st.markdown('<div class="delete-marker" style="display:none;"></div>', unsafe_allow_html=True)
    if st.button("×", key=button_key, help="删除当前图片", use_container_width=False, type="secondary"):
        remove_upload_cache_item(widget_key, item_index)
        reset_upload_widget(widget_key)
        st.rerun()


def render_uploaded_previews(
    uploaded_file,
    widget_key,
    *,
    render_uploaded_preview_card,
    st,
) -> None:
    if uploaded_file is not None:
        preview_col, _ = st.columns([1, 3])
        with preview_col:
            render_uploaded_preview_card(
                uploaded_file,
                widget_key=widget_key,
                item_index=0,
                component_key=f"upload_preview_{widget_key}_0",
            )


def image_source_to_data_url(
    image_source,
    *,
    image_bytes_to_data_url,
    load_image_bytes_from_url,
) -> str | None:
    if image_source.startswith("data:"):
        return image_source
    try:
        image_bytes, mime_type = load_image_bytes_from_url(image_source)
    except Exception:
        return None
    return image_bytes_to_data_url(image_bytes, mime_type or "image/png")


def build_gallery_preview_data_url(
    image_bytes,
    mime_type,
    *,
    GALLERY_PREVIEW_MAX_EDGE,
    GALLERY_PREVIEW_TARGET_BYTES,
    Image,
    image_bytes_to_data_url,
    io,
) -> tuple[str, int, int] | None:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = image.convert("RGB")
            width, height = converted.size
            preview = converted.copy()
            preview.thumbnail((GALLERY_PREVIEW_MAX_EDGE, GALLERY_PREVIEW_MAX_EDGE), Image.Resampling.LANCZOS)
            quality_candidates = (85, 78, 72, 66, 60, 54)
            output_bytes = b""
            for quality in quality_candidates:
                output = io.BytesIO()
                preview.save(output, format="JPEG", quality=quality, optimize=True)
                output_bytes = output.getvalue()
                if len(output_bytes) <= GALLERY_PREVIEW_TARGET_BYTES or quality == quality_candidates[-1]:
                    break
    except Exception:
        return None
    return image_bytes_to_data_url(output_bytes, "image/jpeg"), width, height


def render_first_screen_material_uploader(
    key,
    *,
    hero,
    render_multi_image_uploader,
    render_single_image_uploader,
    st,
) -> list[Any]:
    """The A+ material area shares the same paste/drop frames as other features."""
    with st.container(border=True, key="fusion_hero" if hero else "fusion_materials"):
        st.markdown("**首屏底稿**" if hero else "**卖点素材 · 最多9张**")
        if hero:
            uploaded = render_single_image_uploader("首屏底稿", key)
            return [uploaded] if uploaded is not None else []
        return render_multi_image_uploader(
            "卖点素材", key, max_files=9, preview_slot_count=3,
            allow_reorder=True, preview_area_height=440,
            help_text="拖入或粘贴图片，按优先级调整素材顺序。",
        )


def render_a_plus_reference_lab_empty_results(
    slot_count,
    *,
    st,
) -> None:
    slots = "".join(
        '<div class="a-plus-lab-empty-item">'
        f'<div class="a-plus-lab-empty-index">方案 {index}</div>'
        '<div class="a-plus-lab-empty-copy">'
        '<div class="a-plus-lab-empty-title">尚未生成</div>'
        f'<div class="a-plus-lab-empty-subtitle">点击左侧“开始生成”，获取第 {index} 张方案</div>'
        '</div></div>'
        for index in range(1, max(1, int(slot_count)) + 1)
    )
    st.markdown(f'<div class="a-plus-lab-empty-grid">{slots}</div>', unsafe_allow_html=True)
