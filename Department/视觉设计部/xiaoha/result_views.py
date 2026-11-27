"""Render Xiaoha results and the shared workbench header."""

from __future__ import annotations


def render_result_preview(
    images,
    show_title,
    download_images,
    max_width_percent,
    feature_key,
    *,
    build_result_download_sources,
    render_result_loading,
    render_zoomable_image_gallery,
    st,
) -> None:
    if show_title:
        st.markdown('<div class="result-block-title">结果图预览</div>', unsafe_allow_html=True)
    if render_result_loading(feature_key):
        return
    if not images:
        st.markdown(
            """
            <div class="result-empty">
                <div class="empty-icon">+</div>
                <div class="empty-title">处理完成后在这里查看结果图</div>
                <div class="empty-subtitle">支持多张结果图展示</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        normalized_download_images = list(download_images or build_result_download_sources(images))
        render_zoomable_image_gallery(
            images,
            columns=1,
            thumb_height=None,
            component_key="result_viewer",
            fit_mode="contain",
            max_width_percent=max_width_percent,
            compress_preview=True,
            include_full_src=True,
            full_images=normalized_download_images,
            embed_full_src=False,
        )


def render_result_preview_with_captions(
    images,
    captions,
    feature_key,
    download_images,
    *,
    build_result_download_sources,
    render_result_preview,
    render_zoomable_image_gallery,
    st,
) -> None:
    if not images:
        render_result_preview(images, show_title=False, download_images=download_images)
        return
    if len(captions) != len(images):
        render_result_preview(images, show_title=False, download_images=download_images)
        return
    normalized_download_images = list(download_images or build_result_download_sources(images))
    columns_per_row = min(4, max(len(images), 1))
    for row_start in range(0, len(images), columns_per_row):
        row_images = images[row_start : row_start + columns_per_row]
        row_captions = captions[row_start : row_start + columns_per_row]
        columns = st.columns(columns_per_row)
        for column_index, column in enumerate(columns):
            if column_index >= len(row_images):
                continue
            with column:
                caption = str(row_captions[column_index] or "").strip()
                if caption:
                    st.caption(caption)
                render_zoomable_image_gallery(
                    [row_images[column_index]],
                    columns=1,
                    thumb_height=220,
                    component_key=f"result_viewer_{feature_key}_{row_start + column_index}",
                    fit_mode="contain",
                    max_width_percent=100,
                    compress_preview=True,
                    include_full_src=True,
                    full_images=(
                        [normalized_download_images[row_start + column_index]]
                        if row_start + column_index < len(normalized_download_images)
                        else []
                    ),
                    embed_full_src=False,
                )


def render_image_workbench_header(
    feature,
    badge,
    *,
    html,
    render_fusion_history_dialog,
    st,
) -> None:
    """Shared image-tool header; history always stays within reach."""
    st.markdown("""<style>
    .workbench-page-marker {display:none;}
    body:has(.workbench-page-marker) textarea {min-height:clamp(180px,22vh,340px)!important;resize:vertical;background:#091325!important;color:#edf0ff!important;}
    body:has(.workbench-page-marker) textarea::placeholder {color:#8996b3!important;opacity:1;}
    body:has(.workbench-page-marker) [data-baseweb="textarea"] {border:1px solid #303958!important;border-radius:10px;background:#091325!important;}
    body:has(.workbench-page-marker) [data-testid="stPopoverButton"] {background:#101b31!important;color:#dce2f8!important;border:1px solid #303958!important;border-radius:9px!important;}
    .st-key-workbench_settings {background:#0c1529;border-color:#303958!important;}
    .st-key-workbench_action_dock {position:fixed;bottom:0;left:0;right:0;z-index:1000;background:rgba(12,20,40,.98);border-radius:0!important;padding:12px 28px!important;border-top:1px solid #3c4169!important;}
    body:has(.workbench-page-marker) section[data-testid="stMain"] .block-container {padding-bottom:130px!important;}
    body:has(.workbench-page-marker) div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .feature-workbench-left-marker) {padding-bottom:130px!important;scroll-padding-bottom:130px;}
    div[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .workbench-right-marker) {height:100%;min-height:0;}
    [data-testid="stLayoutWrapper"]:has(> .st-key-workbench_results), .st-key-workbench_results {flex:1!important;min-height:420px;}
    .st-key-workbench_results > [data-testid="stElementContainer"]:has(.result-empty) {flex:1!important;height:100%;}
    .st-key-workbench_results :is([data-testid="stMarkdown"],[data-testid="stMarkdownContainer"]):has(.result-empty),
    .st-key-workbench_results [data-testid="stMarkdown"]:has(.result-empty) > div {height:100%;}
    .st-key-workbench_results .result-empty {height:100%;min-height:420px;box-sizing:border-box;margin:0;}
    @media(max-width:900px){.st-key-workbench_action_dock{padding:8px 12px!important;}}
    </style><div class="workbench-page-marker"></div>""", unsafe_allow_html=True)
    title_col, history_col = st.columns([5, 1], vertical_alignment="center")
    with title_col:
        st.markdown(f'<div class="feature-title">{html.escape(str(feature["name"]))}<span class="feature-badge">{html.escape(badge)}</span></div>', unsafe_allow_html=True)
    with history_col:
        if st.button("历史记录", icon=":material/history:", key=f"workbench_history_{feature['key']}", use_container_width=True):
            render_fusion_history_dialog(feature)
