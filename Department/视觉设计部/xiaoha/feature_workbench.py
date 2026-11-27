"""Render the common Xiaoha feature workbench."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def render_openrouter_feature(
    runtime: SimpleNamespace,
    feature: dict[str, Any],
    model: str,
    aspect_ratio: str,
) -> None:
    """Render a workbench using the dependencies captured by the Streamlit entry point."""
    AMAZON_A_PLUS_FEATURE_KEY = runtime.AMAZON_A_PLUS_FEATURE_KEY
    AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY = runtime.AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY
    A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY = runtime.A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY
    A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY = runtime.A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY
    A_PLUS_IMAGES_API_FEATURE_KEYS = runtime.A_PLUS_IMAGES_API_FEATURE_KEYS
    A_PLUS_REFERENCE_LAB_FEATURE_KEY = runtime.A_PLUS_REFERENCE_LAB_FEATURE_KEY
    A_PLUS_REFERENCE_LAB_MAX_PRODUCT_IMAGES = runtime.A_PLUS_REFERENCE_LAB_MAX_PRODUCT_IMAGES
    A_PLUS_STYLE_MODEL_REPLACE_FEATURE_KEY = runtime.A_PLUS_STYLE_MODEL_REPLACE_FEATURE_KEY
    Any = runtime.Any
    BACKGROUND_TEXTURE_FEATURE_KEY = runtime.BACKGROUND_TEXTURE_FEATURE_KEY
    BACKGROUND_TEXTURE_PRESETS = runtime.BACKGROUND_TEXTURE_PRESETS
    BATCH_MULTI_IMAGE_FEATURE_KEYS = runtime.BATCH_MULTI_IMAGE_FEATURE_KEYS
    BATCH_MULTI_IMAGE_MAX_FILES = runtime.BATCH_MULTI_IMAGE_MAX_FILES
    DEFAULT_BATCH_API_CONCURRENCY = runtime.DEFAULT_BATCH_API_CONCURRENCY
    DEFAULT_MODEL = runtime.DEFAULT_MODEL
    FEATURE_OUTPUT_COUNT_MAX = runtime.FEATURE_OUTPUT_COUNT_MAX
    FEATURE_OUTPUT_COUNT_MIN = runtime.FEATURE_OUTPUT_COUNT_MIN
    HD_BATCH_MAX_API_CONCURRENCY = runtime.HD_BATCH_MAX_API_CONCURRENCY
    IMAGE_SMART_ANALYSIS_FEATURE_KEY = runtime.IMAGE_SMART_ANALYSIS_FEATURE_KEY
    IMAGE_SMART_ANALYSIS_MODEL = runtime.IMAGE_SMART_ANALYSIS_MODEL
    JIMENG_HD_FEATURE_KEY = runtime.JIMENG_HD_FEATURE_KEY
    JIMENG_HD_MODEL_NAME = runtime.JIMENG_HD_MODEL_NAME
    JIMENG_MAX_INPUT_IMAGES = runtime.JIMENG_MAX_INPUT_IMAGES
    MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY = runtime.MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY
    MAIN_IMAGE_A_PLUS_ELEMENT_DEFAULT_PROMPT = runtime.MAIN_IMAGE_A_PLUS_ELEMENT_DEFAULT_PROMPT
    MAIN_IMAGE_A_PLUS_FEATURE_KEY = runtime.MAIN_IMAGE_A_PLUS_FEATURE_KEY
    MAIN_IMAGE_A_PLUS_FEATURE_KEYS = runtime.MAIN_IMAGE_A_PLUS_FEATURE_KEYS
    MAIN_IMAGE_A_PLUS_FREE_MODES = runtime.MAIN_IMAGE_A_PLUS_FREE_MODES
    MAIN_IMAGE_A_PLUS_LAYOUTS = runtime.MAIN_IMAGE_A_PLUS_LAYOUTS
    MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS = runtime.MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS
    MAIN_IMAGE_A_PLUS_MAX_FILES = runtime.MAIN_IMAGE_A_PLUS_MAX_FILES
    MAIN_IMAGE_A_PLUS_MODE_ELEMENT = runtime.MAIN_IMAGE_A_PLUS_MODE_ELEMENT
    MAIN_IMAGE_A_PLUS_MODE_FREE = runtime.MAIN_IMAGE_A_PLUS_MODE_FREE
    MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN = runtime.MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN
    MAIN_IMAGE_A_PLUS_MODE_LABELS = runtime.MAIN_IMAGE_A_PLUS_MODE_LABELS
    MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT = runtime.MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT
    MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST = runtime.MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST
    MAIN_IMAGE_A_PLUS_MODE_TEMPLATE = runtime.MAIN_IMAGE_A_PLUS_MODE_TEMPLATE
    MAIN_IMAGE_A_PLUS_SINGLE_TEST_DEFAULT_PROMPT = runtime.MAIN_IMAGE_A_PLUS_SINGLE_TEST_DEFAULT_PROMPT
    MAIN_IMAGE_A_PLUS_SIZE_OPTIONS = runtime.MAIN_IMAGE_A_PLUS_SIZE_OPTIONS
    MAIN_IMAGE_A_PLUS_TEMPLATE_DEFAULT_PROMPT = runtime.MAIN_IMAGE_A_PLUS_TEMPLATE_DEFAULT_PROMPT
    MAIN_IMAGE_A_PLUS_TEMPLATE_MODES = runtime.MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
    MODEL_OPTIONS = runtime.MODEL_OPTIONS
    MULTI_REFERENCE_COMPOSER_FEATURE_KEY = runtime.MULTI_REFERENCE_COMPOSER_FEATURE_KEY
    NANO_BANANA_MODEL = runtime.NANO_BANANA_MODEL
    OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX = runtime.OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX
    OUTPAINT_DEFAULT_EXTENSION_PX = runtime.OUTPAINT_DEFAULT_EXTENSION_PX
    OUTPAINT_MAX_CANVAS_MULTIPLIER = runtime.OUTPAINT_MAX_CANVAS_MULTIPLIER
    OUTPAINT_MODEL_OPTIONS = runtime.OUTPAINT_MODEL_OPTIONS
    OUTPAINT_RESULTS_PER_SOURCE = runtime.OUTPAINT_RESULTS_PER_SOURCE
    PORTRAIT_HD_COLOR_LOCK_RULES = runtime.PORTRAIT_HD_COLOR_LOCK_RULES
    PORTRAIT_HD_SKIN_LOCK_RULES = runtime.PORTRAIT_HD_SKIN_LOCK_RULES
    REMOVE_EYELASHES_PRESERVE_BASIC_PROMPT = runtime.REMOVE_EYELASHES_PRESERVE_BASIC_PROMPT
    REMOVE_EYELASHES_REMOVE_ALL_PROMPT = runtime.REMOVE_EYELASHES_REMOVE_ALL_PROMPT
    analyze_main_image_a_plus_elements = runtime.analyze_main_image_a_plus_elements
    analyze_main_image_a_plus_replacement_matches = runtime.analyze_main_image_a_plus_replacement_matches
    build_a_plus_reference_lab_instruction = runtime.build_a_plus_reference_lab_instruction
    build_background_texture_instruction = runtime.build_background_texture_instruction
    build_jimeng_prompt = runtime.build_jimeng_prompt
    build_main_image_a_plus_element_preview = runtime.build_main_image_a_plus_element_preview
    build_main_image_a_plus_element_replacement_notes = runtime.build_main_image_a_plus_element_replacement_notes
    build_main_image_a_plus_layout_notes = runtime.build_main_image_a_plus_layout_notes
    build_main_image_a_plus_single_test_notes = runtime.build_main_image_a_plus_single_test_notes
    build_main_image_a_plus_template_notes = runtime.build_main_image_a_plus_template_notes
    build_outpaint_extra_notes = runtime.build_outpaint_extra_notes
    build_prompt = runtime.build_prompt
    build_result_download_sources = runtime.build_result_download_sources
    clamp_outpaint_extensions = runtime.clamp_outpaint_extensions
    clear_upload_cache = runtime.clear_upload_cache
    consume_main_image_a_plus_manual_point = runtime.consume_main_image_a_plus_manual_point
    crop_main_image_a_plus_replacement_input = runtime.crop_main_image_a_plus_replacement_input
    find_main_image_a_plus_element_at_point = runtime.find_main_image_a_plus_element_at_point
    format_user_facing_error_message = runtime.format_user_facing_error_message
    get_a_plus_reference_style_label = runtime.get_a_plus_reference_style_label
    get_a_plus_reference_style_options = runtime.get_a_plus_reference_style_options
    get_feature_by_key = runtime.get_feature_by_key
    get_feature_min_output_edge = runtime.get_feature_min_output_edge
    get_main_image_a_plus_layout = runtime.get_main_image_a_plus_layout
    get_main_image_a_plus_template_layout = runtime.get_main_image_a_plus_template_layout
    get_main_image_a_plus_template_signature = runtime.get_main_image_a_plus_template_signature
    get_model_display_name = runtime.get_model_display_name
    get_outpaint_default_extension = runtime.get_outpaint_default_extension
    get_outpaint_extension_limits = runtime.get_outpaint_extension_limits
    get_outpaint_target_canvas_size = runtime.get_outpaint_target_canvas_size
    get_uploaded_file_bytes = runtime.get_uploaded_file_bytes
    get_uploaded_file_name = runtime.get_uploaded_file_name
    get_uploaded_input_dimensions = runtime.get_uploaded_input_dimensions
    hashlib = runtime.hashlib
    html = runtime.html
    is_jimeng_model = runtime.is_jimeng_model
    is_main_image_a_plus_mobile_size = runtime.is_main_image_a_plus_mobile_size
    load_image_bytes_from_url = runtime.load_image_bytes_from_url
    load_upload_cache = runtime.load_upload_cache
    mimetypes = runtime.mimetypes
    normalize_feature_output_count = runtime.normalize_feature_output_count
    parse_size_text = runtime.parse_size_text
    prepare_uploaded_input = runtime.prepare_uploaded_input
    re = runtime.re
    render_a_plus_hero_style_reverse_feature = runtime.render_a_plus_hero_style_reverse_feature
    render_a_plus_layout_skill_builder = runtime.render_a_plus_layout_skill_builder
    render_a_plus_reference_lab_empty_results = runtime.render_a_plus_reference_lab_empty_results
    render_background_cutout_feature = runtime.render_background_cutout_feature
    render_before_after_compare_gallery = runtime.render_before_after_compare_gallery
    render_compact_element_image_uploader = runtime.render_compact_element_image_uploader
    render_first_screen_material_uploader = runtime.render_first_screen_material_uploader
    render_fusion_history_dialog = runtime.render_fusion_history_dialog
    render_image_smart_analysis_report = runtime.render_image_smart_analysis_report
    render_image_workbench_header = runtime.render_image_workbench_header
    render_main_image_a_plus_crop_downloads = runtime.render_main_image_a_plus_crop_downloads
    render_main_image_a_plus_manual_element_job_status = runtime.render_main_image_a_plus_manual_element_job_status
    render_main_image_a_plus_manual_element_picker = runtime.render_main_image_a_plus_manual_element_picker
    render_main_image_a_plus_text_editor = runtime.render_main_image_a_plus_text_editor
    render_multi_image_uploader = runtime.render_multi_image_uploader
    render_outpaint_extension_preview_card = runtime.render_outpaint_extension_preview_card
    render_prepress_check_feature = runtime.render_prepress_check_feature
    render_reference_slot_uploaders = runtime.render_reference_slot_uploaders
    render_replacement_infinite_canvas_feature = runtime.render_replacement_infinite_canvas_feature
    render_result_loading = runtime.render_result_loading
    render_result_preview = runtime.render_result_preview
    render_result_preview_with_captions = runtime.render_result_preview_with_captions
    render_running_job_status = runtime.render_running_job_status
    render_single_image_uploader = runtime.render_single_image_uploader
    render_zoomable_image_gallery = runtime.render_zoomable_image_gallery
    reset_upload_widget = runtime.reset_upload_widget
    resolve_a_plus_layout_skill_context_for_layout = runtime.resolve_a_plus_layout_skill_context_for_layout
    resolve_a_plus_reference_style = runtime.resolve_a_plus_reference_style
    save_upload_cache = runtime.save_upload_cache
    st = runtime.st
    submit_feature_job = runtime.submit_feature_job
    submit_main_image_a_plus_manual_element_job = runtime.submit_main_image_a_plus_manual_element_job
    submit_main_image_a_plus_mobile_adaptation = runtime.submit_main_image_a_plus_mobile_adaptation
    sync_main_image_a_plus_manual_element_job = runtime.sync_main_image_a_plus_manual_element_job
    uploaded_input_to_data_url = runtime.uploaded_input_to_data_url

    if feature.get("key") in {"a_plus_canvas", MULTI_REFERENCE_COMPOSER_FEATURE_KEY}:
        from Department.视觉设计部.xiaoha.a_plus_canvas import render
        render(runtime, get_feature_by_key("a_plus_canvas"), model, aspect_ratio)
        return
    if feature.get("key") == "poster_fusion":
        from Department.视觉设计部.xiaoha.poster_fusion import render
        render(runtime, feature)
        return
    if feature.get("key") == "ai_qa_image":
        from Department.视觉设计部.xiaoha.qa_chat import render
        render(runtime, feature, model, aspect_ratio)
        return
    if feature.get("key") == "prepress_check":
        render_prepress_check_feature(feature)
        return
    if feature.get("key") == "infinite_canvas":
        render_replacement_infinite_canvas_feature(feature)
        return
    if feature.get("key") == "background_cutout":
        render_background_cutout_feature(feature)
        return
    if feature.get("key") == A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY:
        render_a_plus_hero_style_reverse_feature(feature)
        return
    default_model_for_feature = str(feature.get("model") or model)
    feature_mode = str(feature.get("mode") or "openrouter")
    model_options_for_feature = MODEL_OPTIONS
    if feature.get("key") == "hd_batch":
        default_model_for_feature = NANO_BANANA_MODEL
        model_options_for_feature = [NANO_BANANA_MODEL]
    elif feature.get("key") == JIMENG_HD_FEATURE_KEY:
        default_model_for_feature = JIMENG_HD_MODEL_NAME
        model_options_for_feature = [JIMENG_HD_MODEL_NAME]
    elif feature.get("key") == "image_resize":
        default_model_for_feature = "本机高质量处理"
        model_options_for_feature = ["本机高质量处理"]
    elif feature.get("key") == IMAGE_SMART_ANALYSIS_FEATURE_KEY:
        default_model_for_feature = IMAGE_SMART_ANALYSIS_MODEL
        model_options_for_feature = [IMAGE_SMART_ANALYSIS_MODEL]
    elif feature.get("key") == "outpaint":
        default_model_for_feature = NANO_BANANA_MODEL
        model_options_for_feature = OUTPAINT_MODEL_OPTIONS
    elif feature.get("key") in A_PLUS_IMAGES_API_FEATURE_KEYS:
        default_model_for_feature = NANO_BANANA_MODEL
        model_options_for_feature = [NANO_BANANA_MODEL]
    if default_model_for_feature not in model_options_for_feature:
        default_model_for_feature = model_options_for_feature[0] if model_options_for_feature else DEFAULT_MODEL
    min_images = int(feature.get("min_images", 0))
    max_output_images = int(feature.get("max_output_images", 0))
    fixed_output_count = int(feature.get("fixed_output_count") or 0)
    default_output_count = (
        normalize_feature_output_count(fixed_output_count or max_output_images, default=1)
        if str(feature.get("output_mode") or "") == "image"
        else 0
    )
    selected_output_count = default_output_count
    supports_batch_multi_upload = feature["key"] in BATCH_MULTI_IMAGE_FEATURE_KEYS
    supports_remove_eyelashes = feature["key"] == "remove_eyelashes"
    supports_skin_tone_reference = feature["key"] == "skin_tone"
    supports_pupil_color_reference = feature["key"] == "pupil_color_change"
    supports_eye_shape_reference = feature["key"] == "eye_shape_change"
    supports_side_angle_reference = feature["key"] == "three_view"
    supports_ai_qa_image = feature["key"] == "ai_qa_image"
    supports_image_smart_analysis = feature["key"] == IMAGE_SMART_ANALYSIS_FEATURE_KEY
    supports_amazon_a_plus = feature["key"] == AMAZON_A_PLUS_FEATURE_KEY
    supports_amazon_to_walmart_a_plus = feature["key"] == AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY
    supports_a_plus_style_model_replace = feature["key"] == A_PLUS_STYLE_MODEL_REPLACE_FEATURE_KEY
    supports_a_plus_first_screen_selling_points = feature["key"] == A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY
    supports_main_image_a_plus = feature["key"] in MAIN_IMAGE_A_PLUS_FEATURE_KEYS
    supports_a_plus_reference_lab = feature["key"] == A_PLUS_REFERENCE_LAB_FEATURE_KEY
    supports_a_plus_images_api = (
        supports_amazon_a_plus
        or supports_amazon_to_walmart_a_plus
        or supports_main_image_a_plus
        or supports_a_plus_style_model_replace
        or supports_a_plus_first_screen_selling_points
    )
    supports_pose_references = feature["key"] == "pose_change"
    supports_scene_references = feature["key"] == "scene_change"
    supports_background_texture = feature["key"] == BACKGROUND_TEXTURE_FEATURE_KEY
    supports_outpaint = feature["key"] == "outpaint"
    supports_image_resize = feature["key"] == "image_resize"
    result = st.session_state.feature_results.get(feature["key"]) or {}
    job_info = st.session_state.background_jobs.get(feature["key"]) or {}
    help_text = "可上传 JPG / PNG / WEBP。"
    if min_images > 0:
        help_text += (
            " 请上传 1 张待转换的完整亚马逊 A+ 原图，不需要额外参考图。"
            if supports_amazon_to_walmart_a_plus
            else f" 当前功能至少需要上传 {min_images} 张参考图。"
        )
    active_model = default_model_for_feature

    st.markdown('<div class="workspace-panel">', unsafe_allow_html=True)
    if supports_a_plus_reference_lab:
        st.markdown('<div class="a-plus-lab-page-marker"></div>', unsafe_allow_html=True)
    if supports_a_plus_first_screen_selling_points:
        st.markdown("""<style>
        .st-key-fusion_hero, .st-key-fusion_materials { min-width:0; background:#0c1529; border-color:#303958!important; }
        :is(.st-key-fusion_hero,.st-key-fusion_materials) [data-testid="stPopoverButton"] {background:#101b31!important;color:#dce2f8!important;border:1px solid #303958!important;border-radius:9px!important;}
        :is(.st-key-fusion_hero,.st-key-fusion_materials) [data-testid="stPopoverButton"] p {color:#dce2f8!important;}
        .st-key-fusion_settings {border-color:#303958!important;background:#0c1529;}
        .st-key-fusion_settings textarea {min-height:clamp(220px,24vh,380px)!important;resize:vertical;background:#091325!important;color:#edf0ff!important;}
        .st-key-fusion_settings textarea::placeholder {color:#8996b3!important;opacity:1;}
        .st-key-fusion_settings [data-baseweb="textarea"] {border:1px solid #303958!important;border-radius:10px;background:#091325!important;}
        .st-key-fusion_settings [data-testid="stHorizontalBlock"] {align-items:end;}
        .st-key-fusion_settings [data-testid="stColumn"] {min-width:0!important;}
        .fusion-panel-header {display:flex;flex-direction:column;gap:6px;padding-bottom:10px;}
        .fusion-panel-heading {display:flex;justify-content:space-between;align-items:center;gap:12px;color:#f1f3ff;font-size:16px;line-height:1.5;}
        .fusion-panel-heading strong {display:block;line-height:1.5;}
        .fusion-panel-description {color:#aeb9d7;font-size:12px;line-height:1.5;white-space:normal;overflow-wrap:anywhere;}
        .fusion-panel-heading span {border:1px solid #36415d;border-radius:18px;padding:2px 12px;font-size:12px;color:#c8cde5;}
        .fusion-empty-slot {height:112px;border:1px dashed #49547c;border-radius:12px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#aeb9d7;font-size:12px;background:#10192e;}
        .fusion-empty-slot span {font-size:25px;color:#a995ff;margin-bottom:8px;}
        .fusion-empty-hero {height:470px;}
        div[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .fusion-right-marker) {height:100%;min-height:0;padding:12px;border:1px solid #303958;border-radius:14px;background:rgba(7,15,31,.32);}
        .st-key-fusion_results {flex:1!important;min-height:500px;}
        [data-testid="stLayoutWrapper"]:has(> .st-key-fusion_results) {flex:1!important;min-height:500px;}
        .st-key-fusion_results > [data-testid="stElementContainer"]:has(.fusion-result-empty) {flex:1!important;height:100%;}
        .st-key-fusion_results [data-testid="stMarkdown"]:has(.fusion-result-empty) {height:100%;}
        .st-key-fusion_results [data-testid="stMarkdownContainer"]:has(.fusion-result-empty),
        .st-key-fusion_results [data-testid="stMarkdown"]:has(.fusion-result-empty) > div {height:100%;}
        .fusion-result-empty {height:100%;min-height:500px;box-sizing:border-box;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;border:1px dashed #7165ac;border-radius:12px;background:#0d162b;}
        .fusion-result-empty>div {font-size:42px;color:#9c7aff;margin-bottom:20px;}
        .fusion-result-empty p {font-size:13px;color:#aab5d1;max-width:230px;}
        .st-key-fusion_action_dock {position:fixed;bottom:0;left:0;right:0;z-index:1000;background:rgba(12,20,40,.98);border-radius:0!important;padding:12px 28px!important;border-top:1px solid #3c4169!important;}
        .st-key-fusion_action_dock p {margin:10px 0;color:#c8d5ec;}
        section[data-testid="stMain"] .block-container {padding-bottom:110px;}
        @media(max-width:900px){.st-key-fusion_action_dock {padding:8px 12px!important;} .fusion-result-empty {height:500px;}}
        </style>""", unsafe_allow_html=True)
    page_subtitle = str(feature.get("summary") or feature.get("description") or "").strip()
    if not supports_a_plus_reference_lab and page_subtitle:
        page_subtitle = re.split(r"[。；;]", page_subtitle, maxsplit=1)[0].strip()
        if len(page_subtitle) > 42:
            page_subtitle = f"{page_subtitle[:41].rstrip()}…"
    title_html = f'<div class="feature-title">{feature["name"]}<span class="feature-badge">AI 增强</span></div>'
    if supports_a_plus_first_screen_selling_points:
        title_col, history_col = st.columns([5, 1], vertical_alignment="center")
        with title_col:
            st.markdown(title_html, unsafe_allow_html=True)
        with history_col:
            if st.button("历史记录", icon=":material/history:", key="fusion_open_history", use_container_width=True):
                render_fusion_history_dialog(feature)
    else:
        render_image_workbench_header(feature)
    if not supports_a_plus_reference_lab:
        st.markdown(f'<div class="feature-desc">{page_subtitle}</div>', unsafe_allow_html=True)
    if str(job_info.get("status") or "").strip().lower() in {"queued", "running"}:
        render_running_job_status(feature["key"])
    elif job_info.get("status") == "error":
        st.error(f"后台任务失败：{format_user_facing_error_message(job_info.get('error'))}")
    elif job_info.get("status") == "completed":
        st.success(
            "图片分析已完成，报告已更新到右侧。"
            if supports_image_smart_analysis
            else "任务已完成，结果已更新到右侧预览区。"
        )

    meta_items = ['<span class="meta-pill">JPG、PNG、WEBP · 单张≤50MB</span>']
    if supports_a_plus_reference_lab:
        meta_items.append('<span class="meta-pill">上传图片是唯一元素来源</span>')
        meta_items.append('<span class="meta-pill">5 类商业视觉方向</span>')
        meta_items.append('<span class="meta-pill">电脑 / 手机独立构图</span>')
        meta_items.append('<span class="meta-pill">真实元素分层取舍与重组</span>')
        meta_items.append('<span class="meta-pill">多视觉中心与分层构图</span>')
        meta_items.append('<span class="meta-pill">独立任务与历史记录</span>')
    elif supports_main_image_a_plus:
        meta_items.append(f'<span class="meta-pill">最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张参考图</span>')
        meta_items.append('<span class="meta-pill">4 种模式 · 支持指定元素替换</span>')
        meta_items.append('<span class="meta-pill">3 种规格 · 套版跟随模板</span>')
        meta_items.append('<span class="meta-pill">原生 4K · 文字不截断</span>')
        meta_items.append('<span class="meta-pill">成品文字可二次编辑</span>')
    elif supports_amazon_a_plus:
        meta_items.append(f'<span class="meta-pill">最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张参考图</span>')
        meta_items.append('<span class="meta-pill">3 种 A+ 规格</span>')
        meta_items.append('<span class="meta-pill">背景与视觉元素自动拆层</span>')
        meta_items.append('<span class="meta-pill">一键导出 Photoshop PSD</span>')
    elif supports_amazon_to_walmart_a_plus:
        meta_items.append('<span class="meta-pill">上传 1 张完整亚马逊 A+</span>')
        meta_items.append('<span class="meta-pill">固定输出 4 张 1920×1080</span>')
        meta_items.append('<span class="meta-pill">单页独立 · 四页连续</span>')
        meta_items.append('<span class="meta-pill">原生 4K 重构 · 非拉伸裁切</span>')
    elif supports_a_plus_first_screen_selling_points:
        meta_items.append('<span class="meta-pill">首屏 1464×600–1200 自适应</span>')
        meta_items.append('<span class="meta-pill">A+ 总高度 2400 / 3000 / 3600</span>')
        meta_items.append('<span class="meta-pill">最多 10 张 · 多主图卖点融合</span>')
        meta_items.append('<span class="meta-pill">真实元素保留 · 卖点自动去重</span>')
    elif supports_outpaint:
        meta_items.append('<span class="meta-pill">Nano Banana 2.1 / 即梦 5 Pro 可选</span>')
        meta_items.append('<span class="meta-pill">画布宽高最大可扩至原图 3 倍</span>')
        meta_items.append('<span class="meta-pill">自动匹配扩展画幅</span>')
        meta_items.append('<span class="meta-pill">整图一次生成 · 无矩形拼接</span>')
        meta_items.append('<span class="meta-pill">每张原图可选返回 1–4 张结果</span>')
    elif feature.get("key") == JIMENG_HD_FEATURE_KEY:
        meta_items.append('<span class="meta-pill">即梦智能超清 · 原生 8K · scale 50</span>')
        meta_items.append(
            '<span class="meta-pill">全局串行队列 · 所有任务依次执行</span>'
        )
    elif feature.get("key") == "hd_batch":
        meta_items.append('<span class="meta-pill">输出尺寸与原图完全一致 · 无补边 · 无拉伸</span>')
    elif supports_background_texture:
        meta_items.append(f'<span class="meta-pill">{len(BACKGROUND_TEXTURE_PRESETS)} 种预设质感 · 支持多选</span>')
        meta_items.append('<span class="meta-pill">支持直接提示词描述</span>')
        meta_items.append('<span class="meta-pill">人物、商品与场景结构锁定</span>')
    elif supports_image_smart_analysis:
        meta_items.append('<span class="meta-pill">单图深度识别 · 只分析不改图</span>')
        meta_items.append('<span class="meta-pill">分区域简析 · 原图真实取色</span>')
        meta_items.append('<span class="meta-pill">原图与纯排版同图对照</span>')
    else:
        meta_items.append(f'<span class="meta-pill">等比例放大，宽高都不小于 {get_feature_min_output_edge(feature)}px</span>')
    if supports_batch_multi_upload:
        meta_items.append(f'<span class="meta-pill">支持批量上传，最多 {BATCH_MULTI_IMAGE_MAX_FILES} 张</span>')
    if feature.get("key") == JIMENG_HD_FEATURE_KEY:
        meta_items.append('<span class="meta-pill">保持原图比例、构图与内容</span>')
    elif feature.get("key") == "hd_batch":
        meta_items.append('<span class="meta-pill">Nano Banana 2.1 · 仅使用原图 · 每张返回一张结果</span>')
    if supports_outpaint:
        meta_items.append('<span class="meta-pill">支持上下左右独立扩展</span>')
    if default_output_count > 0 and not supports_outpaint:
        meta_items.append('<span class="meta-pill">结果张数可选 1–4 张</span>')
    if not supports_a_plus_reference_lab:
        meta_items = meta_items[:3]
        st.markdown(f'<div class="meta-row">{"".join(meta_items)}</div>', unsafe_allow_html=True)

    if supports_a_plus_first_screen_selling_points:
        workflow_steps = ("上传素材", "设置要求", "生成结果")
    elif supports_a_plus_reference_lab:
        workflow_steps = ("选风格", "传素材", "定规格", "生成", "看结果")
    elif supports_main_image_a_plus or supports_amazon_a_plus:
        workflow_steps = ("选择方式", "上传素材", "设置规格与要求", "开始生成", "查看结果")
    elif supports_outpaint:
        workflow_steps = ("上传原图", "框定扩图区域", "补充要求", "开始扩图", "对比结果")
    elif feature.get("key") == JIMENG_HD_FEATURE_KEY:
        workflow_steps = ("上传原图", "提交 8K 超清", "查看结果")
    elif feature.get("key") == "hd_batch":
        workflow_steps = ("上传图片", "专用超清", "查看结果")
    elif supports_background_texture:
        workflow_steps = ("上传原图", "选择背景质感", "补充描述", "开始生成", "查看结果")
    elif supports_image_smart_analysis:
        workflow_steps = ("上传主图", "识别内容", "解析视觉", "生成报告", "查看与下载")
    else:
        workflow_steps = ("上传图片", "补充参考", "填写要求", "开始处理", "查看结果")
    workflow_html = "".join(
        f'<div class="workflow-step"><span class="workflow-step-number">{index}</span><span>{label}</span></div>'
        for index, label in enumerate(workflow_steps, start=1)
    )
    st.markdown(f'<div class="workflow-strip">{workflow_html}</div>', unsafe_allow_html=True)

    submitted = False
    active_batch_concurrency = DEFAULT_BATCH_API_CONCURRENCY if supports_batch_multi_upload else 1
    if feature.get("key") == "hd_batch":
        active_batch_concurrency = min(active_batch_concurrency, HD_BATCH_MAX_API_CONCURRENCY)

    shared_action_dock = None
    if not supports_a_plus_first_screen_selling_points:
        shared_action_dock = st.container(key="workbench_action_dock", border=True)
    column_ratio = [1.85, 1] if supports_a_plus_first_screen_selling_points else [1, 1]
    left_col, right_col = st.columns(column_ratio, gap="medium")
    with left_col:
        if supports_a_plus_reference_lab:
            st.markdown('<div class="a-plus-lab-left-marker"></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="feature-workbench-left-marker"></div>', unsafe_allow_html=True)
        if supports_batch_multi_upload:
            st.markdown('<div class="batch-left-column-marker"></div>', unsafe_allow_html=True)
        left_panel_title = (
            "创作设置"
            if supports_main_image_a_plus or supports_amazon_a_plus or supports_a_plus_style_model_replace or supports_a_plus_first_screen_selling_points
            else "上传待分析主图"
            if supports_image_smart_analysis
            else "上传与设置"
        )
        st.markdown(
            f'<div class="result-block-title">{left_panel_title}</div>',
            unsafe_allow_html=True,
        )
        primary_action_slot = None
        skin_tone_reference_file = None
        pupil_color_reference_file = None
        eye_shape_reference_file = None
        side_angle_reference_file = None
        ai_qa_source_files: list[Any] = []
        ai_qa_prompt = ""
        amazon_source_files: list[Any] = []
        amazon_size_text = "1464*600"
        amazon_a_plus_prompt = ""
        a_plus_style_model_replace_prompt = ""
        a_plus_first_screen_selling_points_prompt = ""
        a_plus_first_screen_workflow_mode = "combined"
        a_plus_first_screen_workflow_stage = "combined"
        main_image_a_plus_prompt = ""
        main_image_a_plus_mode = MAIN_IMAGE_A_PLUS_MODE_FREE
        main_image_a_plus_template_file = None
        main_image_a_plus_layout_key = MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY
        main_image_a_plus_detected_elements: list[dict[str, Any]] = []
        main_image_a_plus_element_replacements: list[dict[str, Any]] = []
        main_image_a_plus_element_preview = ""
        main_image_a_plus_element_template_signature = ""
        main_image_a_plus_element_review_confirmed = False
        a_plus_layout_skill_context: dict[str, Any] = {}
        a_plus_lab_style_key = "auto"
        a_plus_lab_resolved_style_key = "fashion_editorial"
        pose_reference_files: list[Any] = []
        scene_reference_files: list[Any] = []
        background_texture_presets: list[str] = ["高级哑光"]
        background_texture_prompt = ""
        local_retouch_prompt = ""
        batch_source_files: list[Any] = []
        outpaint_top_px = OUTPAINT_DEFAULT_EXTENSION_PX
        outpaint_bottom_px = OUTPAINT_DEFAULT_EXTENSION_PX
        outpaint_left_px = OUTPAINT_DEFAULT_EXTENSION_PX
        outpaint_right_px = OUTPAINT_DEFAULT_EXTENSION_PX
        resize_target_width = 2000
        resize_target_height = 2000
        preserve_basic_eyelashes = True

        supports_dual_reference_upload = (
            supports_skin_tone_reference
            or supports_pupil_color_reference
            or supports_eye_shape_reference
            or supports_side_angle_reference
        )

        if supports_batch_multi_upload:
            st.markdown(
                f'<div class="panel-subtitle">原图（最多 {BATCH_MULTI_IMAGE_MAX_FILES} 张）</div>',
                unsafe_allow_html=True,
            )
            outpaint_top_key = f"outpaint_top_{feature['key']}"
            outpaint_bottom_key = f"outpaint_bottom_{feature['key']}"
            outpaint_left_key = f"outpaint_left_{feature['key']}"
            outpaint_right_key = f"outpaint_right_{feature['key']}"
            outpaint_drag_mode_key = f"outpaint_drag_mode_v2_{feature['key']}"
            if supports_outpaint:
                outpaint_defaults_key = f"outpaint_defaults_{OUTPAINT_MAX_CANVAS_MULTIPLIER}x_{OUTPAINT_DEFAULT_EXTENSION_PX}_{feature['key']}"
                if not st.session_state.get(outpaint_defaults_key):
                    for state_key in (outpaint_top_key, outpaint_bottom_key, outpaint_left_key, outpaint_right_key):
                        st.session_state[state_key] = OUTPAINT_DEFAULT_EXTENSION_PX
                    st.session_state[outpaint_defaults_key] = True
                for state_key in (outpaint_top_key, outpaint_bottom_key, outpaint_left_key, outpaint_right_key):
                    if state_key not in st.session_state:
                        st.session_state[state_key] = OUTPAINT_DEFAULT_EXTENSION_PX
                    if state_key in st.session_state:
                        try:
                            current_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(st.session_state[state_key])))
                            st.session_state[state_key] = current_px
                        except Exception:
                            st.session_state[state_key] = OUTPAINT_DEFAULT_EXTENSION_PX
                outpaint_top_px = int(st.session_state.get(outpaint_top_key, OUTPAINT_DEFAULT_EXTENSION_PX))
                outpaint_bottom_px = int(st.session_state.get(outpaint_bottom_key, OUTPAINT_DEFAULT_EXTENSION_PX))
                outpaint_left_px = int(st.session_state.get(outpaint_left_key, OUTPAINT_DEFAULT_EXTENSION_PX))
                outpaint_right_px = int(st.session_state.get(outpaint_right_key, OUTPAINT_DEFAULT_EXTENSION_PX))
                if st.session_state.get(outpaint_drag_mode_key) not in {"position", "resize"}:
                    st.session_state[outpaint_drag_mode_key] = "resize"

                def outpaint_preview_renderer(uploaded_input: Any, item_index: int, component_key: str) -> None:
                    render_outpaint_extension_preview_card(
                        uploaded_input,
                        outpaint_top_px,
                        outpaint_bottom_px,
                        outpaint_left_px,
                        outpaint_right_px,
                        f"{component_key}_{item_index}",
                        max_preview_edge=760,
                        drag_state_keys={
                            "top": outpaint_top_key,
                            "bottom": outpaint_bottom_key,
                            "left": outpaint_left_key,
                            "right": outpaint_right_key,
                            "mode": outpaint_drag_mode_key,
                        },
                    )
            else:
                outpaint_preview_renderer = None
            batch_source_files = render_multi_image_uploader(
                "上传原图",
                key=f"batch_uploader_{feature['key']}",
                help_text=f"可上传 JPG / PNG / WEBP。当前功能最多使用 {BATCH_MULTI_IMAGE_MAX_FILES} 张原图，系统会逐张处理并返回对应结果。",
                max_files=BATCH_MULTI_IMAGE_MAX_FILES,
                preview_renderer=outpaint_preview_renderer,
                preview_slot_count=1 if supports_outpaint else None,
                show_clear_button=not supports_outpaint,
            )
            if supports_remove_eyelashes:
                preserve_basic_eyelashes = st.checkbox(
                    "保留基础原生睫毛",
                    value=True,
                    key=f"preserve_basic_eyelashes_{feature['key']}",
                    help="默认仅去除假睫毛、嫁接感、过长和过密部分，保留贴近睑缘的短而自然基础睫毛；取消勾选则彻底去除全部睫毛。",
                )
                st.caption(
                    "已勾选：眼睛不会被处理成完全无睫毛状态；只削弱明显的假睫毛、浓密感和夸张长度。"
                    if preserve_basic_eyelashes
                    else "未勾选：沿用原有逻辑，去除自然睫毛与假睫毛。"
                )
            if supports_outpaint:
                if batch_source_files:
                    try:
                        source_bytes = get_uploaded_file_bytes(batch_source_files[0])
                        source_signature = hashlib.sha1(source_bytes).hexdigest()[:16]
                        dynamic_defaults_key = f"outpaint_dynamic_defaults_source_{feature['key']}"
                        if st.session_state.get(dynamic_defaults_key) != source_signature:
                            direction_limits = get_outpaint_extension_limits(batch_source_files[0])
                            st.session_state[outpaint_top_key] = get_outpaint_default_extension(direction_limits["top"])
                            st.session_state[outpaint_bottom_key] = get_outpaint_default_extension(direction_limits["bottom"])
                            st.session_state[outpaint_left_key] = get_outpaint_default_extension(direction_limits["left"])
                            st.session_state[outpaint_right_key] = get_outpaint_default_extension(direction_limits["right"])
                            st.session_state[dynamic_defaults_key] = source_signature
                            st.rerun()
                        outpaint_top_px, outpaint_bottom_px, outpaint_left_px, outpaint_right_px = clamp_outpaint_extensions(
                            batch_source_files[0],
                            outpaint_top_px,
                            outpaint_bottom_px,
                            outpaint_left_px,
                            outpaint_right_px,
                        )
                        st.session_state[outpaint_top_key] = outpaint_top_px
                        st.session_state[outpaint_bottom_key] = outpaint_bottom_px
                        st.session_state[outpaint_left_key] = outpaint_left_px
                        st.session_state[outpaint_right_key] = outpaint_right_px
                    except Exception:
                        pass
        elif supports_image_smart_analysis:
            st.markdown('<div class="panel-subtitle">待分析主图（1 张）</div>', unsafe_allow_html=True)
            uploaded_file = render_single_image_uploader(
                "拖入或上传待分析主图",
                key=f"uploader_{feature['key']}",
                help_text="支持 JPG / PNG / WEBP，仅分析当前这 1 张主图，不会修改或生成图片。",
            )
            st.caption(
                "系统会生成分区域视觉拆解图；色块和 HEX 色号直接从原图像素提取，不由 AI 猜测。"
            )
        elif supports_ai_qa_image:
            st.markdown('<div class="panel-subtitle">参考图片（最多 3 张）</div>', unsafe_allow_html=True)
            ai_qa_source_files = render_multi_image_uploader(
                "上传问答参考图",
                key=f"ai_qa_uploader_{feature['key']}",
                help_text="可上传 JPG / PNG / WEBP。当前功能最多使用 3 张参考图。",
                max_files=3,
            )
            st.markdown('<div class="panel-subtitle">文字要求</div>', unsafe_allow_html=True)
            if not supports_a_plus_first_screen_selling_points and primary_action_slot is None:
                primary_action_slot = st.empty()
            ai_qa_prompt = st.text_area(
                "输入你的问答要求",
                key=f"ai_qa_prompt_{feature['key']}",
                placeholder="例如：参考这张模特图，保持人物不变，生成一张更高级的白色极简背景海报图。",
                height=120,
                label_visibility="collapsed",
            )
        elif supports_a_plus_style_model_replace:
            st.markdown('<div class="panel-subtitle">A+ 首屏风格参考图 + 一张目标模特图</div>', unsafe_allow_html=True)
            amazon_source_files = render_multi_image_uploader(
                "上传 A+ 参考图与目标模特图",
                key=f"a_plus_style_model_replace_uploader_{feature['key']}",
                help_text="第 1 张上传 A+ 首屏风格参考图；第 2 张上传一张目标模特图（正脸、半身或全身），优先保留目标模特原始姿势，缺失局部自动补全。",
                max_files=2,
                allow_reorder=True,
            )
            st.markdown(
                '<div class="slot-helper">第 1 张提供风格调性；第 2 张提供目标模特身份与原始姿态，人物自然融合即可。</div>',
                unsafe_allow_html=True,
            )
            st.info("优先保留目标模特原始姿势，自动补全缺失局部并匹配画面光影与透视；版式可灵活调整，固定输出 1464×1000 px。")
            st.markdown('<div class="panel-subtitle">补充要求（可选）</div>', unsafe_allow_html=True)
            if not supports_a_plus_first_screen_selling_points and primary_action_slot is None:
                primary_action_slot = st.empty()
            a_plus_style_model_replace_prompt = st.text_area(
                "输入 A+ 换模补充要求",
                key=f"a_plus_style_model_replace_prompt_{feature['key']}",
                placeholder="例如：保持参考图服装氛围，目标模特长发和五官必须与上传图一致；保留原文案。",
                height=110,
                label_visibility="collapsed",
            )
        elif supports_a_plus_first_screen_selling_points:
            st.caption("底稿已有元素不变、不遮挡；只在空白区域加入完整卖点，放不下的素材会省略，不强行填满。")
            hero_upload_key = f"a_plus_first_screen_hero_uploader_{feature['key']}"
            selling_points_upload_key = f"a_plus_first_screen_selling_only_uploader_{feature['key']}"
            legacy_upload_key = f"a_plus_first_screen_selling_points_uploader_{feature['key']}"
            if not load_upload_cache(hero_upload_key, max_files=1) and not load_upload_cache(selling_points_upload_key, max_files=9):
                legacy_files = load_upload_cache(legacy_upload_key, max_files=10)
                if legacy_files:
                    save_upload_cache(hero_upload_key, legacy_files[:1])
                    if len(legacy_files) > 1:
                        save_upload_cache(selling_points_upload_key, legacy_files[1:])
                    clear_upload_cache(legacy_upload_key)

            hero_col, selling_points_col = st.columns([0.85, 1.15], gap="small")
            with hero_col:
                hero_source_files = render_first_screen_material_uploader(hero_upload_key, hero=True)
            with selling_points_col:
                selling_point_files = render_first_screen_material_uploader(selling_points_upload_key)
            amazon_source_files = list(hero_source_files) + list(selling_point_files)
            with st.container(key="fusion_settings", border=True):
                st.markdown('<div class="result-block-title">生成设置</div>', unsafe_allow_html=True)
                count_col, model_col, height_col = st.columns([1, 1.6, 1.4], gap="small")
                with count_col:
                    selected_output_count = int(st.number_input(
                        "生成数量", min_value=FEATURE_OUTPUT_COUNT_MIN, max_value=FEATURE_OUTPUT_COUNT_MAX,
                        value=default_output_count, step=1, disabled=bool(fixed_output_count),
                        key=f"output_count_{feature['key']}",
                    ))
                with model_col:
                    active_model = model_options_for_feature[0]
                    st.text_input("当前模型", value=get_model_display_name(active_model), disabled=True, key="fusion_current_model")
                with height_col:
                    st.number_input(
                        "填充起始高度（px，0 为自动识别）", min_value=0, max_value=30000,
                        value=0, step=1, key=f"first_screen_keep_height_{feature['key']}",
                        help="仅允许在此高度以下的安全空白区域加入素材；原图任何已有元素仍保持不变，不会因设置高度而被覆盖。",
                    )
                if not supports_a_plus_first_screen_selling_points and primary_action_slot is None:
                    primary_action_slot = st.empty()
                a_plus_first_screen_selling_points_prompt = st.text_area(
                    "补充要求（可选）", key=f"a_plus_first_screen_selling_points_prompt_{feature['key']}",
                    placeholder="请输入本次生成的补充要求…", height=220,
                )
        elif supports_a_plus_reference_lab:
            main_image_a_plus_mode = MAIN_IMAGE_A_PLUS_MODE_FREE
            a_plus_lab_style_key = st.selectbox(
                "选择商业视觉方向",
                options=get_a_plus_reference_style_options(),
                format_func=get_a_plus_reference_style_label,
                key=f"a_plus_lab_style_{feature['key']}",
                label_visibility="collapsed",
            )

            st.markdown('<div class="panel-subtitle">商品素材（最多 8 张）</div>', unsafe_allow_html=True)
            amazon_source_files = render_multi_image_uploader(
                "上传 A+3.0 商品素材",
                key=f"main_image_a_plus_uploader_{feature['key']}",
                help_text="最多 8 张，支持拖动排序。",
                max_files=A_PLUS_REFERENCE_LAB_MAX_PRODUCT_IMAGES,
                allow_reorder=True,
            )

            layout_col, count_col, model_col = st.columns([2.8, 0.9, 1.35], gap="small")
            with layout_col:
                st.markdown('<div class="panel-subtitle">生成规格</div>', unsafe_allow_html=True)
                a_plus_size_options = [
                    (layout_key, device, size)
                    for layout_key in MAIN_IMAGE_A_PLUS_LAYOUTS
                    for device, size in MAIN_IMAGE_A_PLUS_SIZE_OPTIONS
                ]
                a_plus_default_size = (MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY, "desktop", (1464, 2400))
                a_plus_selected_option = st.selectbox(
                    "选择 A+3.0 版式与尺寸",
                    options=a_plus_size_options,
                    index=a_plus_size_options.index(a_plus_default_size),
                    format_func=lambda item: (
                        f"{'电脑端' if item[1] == 'desktop' else '手机端'}｜"
                        f"{item[2][0]}×{item[2][1]}｜"
                        f"{MAIN_IMAGE_A_PLUS_LAYOUTS[item[0]]['label'].split('｜')[-1]}"
                    ),
                    key=f"main_image_a_plus_layout_size_{feature['key']}",
                    label_visibility="collapsed",
                )
                main_image_a_plus_layout_key = a_plus_selected_option[0]
                a_plus_selected_size = a_plus_selected_option[2]
                a_plus_selected_layout = dict(get_main_image_a_plus_layout(main_image_a_plus_layout_key))
                a_plus_selected_layout["target_size"] = tuple(a_plus_selected_size)
                a_plus_selected_layout["section_heights"] = (
                    (a_plus_selected_size[1] // (a_plus_selected_size[0] == 600 and 450 or 600),)
                    * (a_plus_selected_size[1] // (a_plus_selected_size[0] == 600 and 450 or 600))
                )
                selected_a_plus_layout = a_plus_selected_layout
            with count_col:
                st.markdown('<div class="panel-subtitle">生成数量</div>', unsafe_allow_html=True)
                selected_output_count = int(
                    st.number_input(
                        "生成数量",
                        min_value=FEATURE_OUTPUT_COUNT_MIN,
                        max_value=FEATURE_OUTPUT_COUNT_MAX,
                        value=default_output_count,
                        step=1,
                        disabled=bool(fixed_output_count),
                        key=f"output_count_{feature['key']}",
                        label_visibility="collapsed",
                    )
                )
            with model_col:
                st.markdown('<div class="panel-subtitle">当前模型</div>', unsafe_allow_html=True)
                st.markdown(
                    '<div class="a-plus-inline-model-card">'
                    f'{html.escape(get_model_display_name(default_model_for_feature))}</div>',
                    unsafe_allow_html=True,
                )
            st.markdown('<div class="panel-subtitle">补充宣传要求（可选）</div>', unsafe_allow_html=True)
            if not supports_a_plus_first_screen_selling_points and primary_action_slot is None:
                primary_action_slot = st.empty()
            main_image_a_plus_prompt = st.text_area(
                "输入 A+3.0 补充要求",
                key=f"main_image_a_plus_prompt_{feature['key']}",
                placeholder="例如：突出轻盈和自然佩戴，首屏要有强主视觉，整体使用粉紫 Y2K 杂志风。只填写真实、可核实的卖点。",
                height=110,
                label_visibility="collapsed",
            )
            a_plus_lab_resolved_style_key = resolve_a_plus_reference_style(
                a_plus_lab_style_key,
                custom_prompt=main_image_a_plus_prompt,
            )
        elif supports_main_image_a_plus:
            a_plus_layout_skill_context = render_a_plus_layout_skill_builder(
                feature["key"],
                str(st.session_state.get("auth_username") or "admin"),
                get_main_image_a_plus_layout(
                    str(
                        st.session_state.get(
                            f"main_image_a_plus_layout_{feature['key']}",
                            MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY,
                        )
                    )
                ),
            )
            st.markdown(
                '<div class="a-plus-mode-selector-marker"></div>'
                '<div class="panel-subtitle">生成方式</div>',
                unsafe_allow_html=True,
            )
            main_image_a_plus_mode = st.radio(
                "选择主图生A+生成方式",
                options=list(MAIN_IMAGE_A_PLUS_MODE_LABELS),
                index=0,
                format_func=lambda value: MAIN_IMAGE_A_PLUS_MODE_LABELS[value],
                key=f"main_image_a_plus_mode_{feature['key']}",
                horizontal=True,
                label_visibility="collapsed",
            )
            if main_image_a_plus_mode not in MAIN_IMAGE_A_PLUS_FREE_MODES:
                a_plus_layout_skill_context = {}
            uses_finished_a_plus_template = (
                main_image_a_plus_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
            )
            if uses_finished_a_plus_template:
                with st.container(border=True):
                    st.markdown(
                        '<div class="a-plus-template-card-marker"></div>'
                        '<div class="panel-subtitle">成品 A+ 版式模板（1 张）</div>',
                        unsafe_allow_html=True,
                    )
                    main_image_a_plus_template_file = render_single_image_uploader(
                        "上传成品A+版式模板",
                        key=f"main_image_a_plus_template_{feature['key']}",
                        help_text=(
                            "上传完整成品 A+ 示例图。指定元素替换只修改你为编号上传了新素材的元素，"
                            "其余内容、背景和版式保持不变。"
                            if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
                            else (
                                "上传要套用版式的完整成品 A+。模板只保留布局、色彩和视觉层级，"
                                "原品牌、原文案、原模特和原产品都会被替换或删除。"
                                + (
                                    "一张测试会把完整模板作为一个整体，只保留纯背景和版式，其他内容全部替换；只生成一张成品，不拆分、不拼接。"
                                    if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST
                                    else ""
                                )
                            )
                        ),
                    )
                    st.markdown(
                        (
                            '<div class="slot-helper">上传模板后先识别元素；图中编号与下方上传框一一对应，只替换已上传的编号</div>'
                            if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
                            else (
                                '<div class="slot-helper">整张模板一次重绘：只保留背景与版式，产品、品牌、模特和其他内容全部替换；不拆四段、不拼接</div>'
                                if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST
                                else '<div class="slot-helper">套版结果自动跟随模板原图尺寸，无需另外选择规格</div>'
                            )
                        ),
                        unsafe_allow_html=True,
                    )
            if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
                if main_image_a_plus_template_file is None:
                    with st.container(border=True):
                        st.markdown(
                            '<div class="a-plus-analysis-card-marker"></div>'
                            '<div class="panel-subtitle">识别并标注可替换元素</div>',
                            unsafe_allow_html=True,
                        )
                        st.button(
                            "识别可替换元素",
                            key=f"analyze_main_image_a_plus_elements_{feature['key']}_empty",
                            use_container_width=True,
                            type="secondary",
                            disabled=True,
                        )
                        st.info("请先上传完整 A+ 示例图，上传后按钮会在原位置启用。")
                else:
                    template_signature = get_main_image_a_plus_template_signature(
                        main_image_a_plus_template_file
                    )
                    analysis_state_key = f"main_image_a_plus_element_analysis_{feature['key']}"
                    analysis_state = dict(st.session_state.get(analysis_state_key) or {})
                    analysis_matches_template = (
                        str(analysis_state.get("template_signature") or "") == template_signature
                    )
                    analyze_elements_clicked = False
                    with st.container(border=True):
                        st.markdown(
                            '<div class="a-plus-analysis-card-marker"></div>'
                            '<div class="panel-subtitle">识别并标注可替换元素</div>',
                            unsafe_allow_html=True,
                        )
                        analyze_elements_clicked = st.button(
                            "重新识别可替换元素"
                            if analysis_matches_template
                            else "识别可替换元素",
                            key=f"analyze_main_image_a_plus_elements_{feature['key']}_{template_signature}",
                            use_container_width=True,
                            type="secondary",
                        )
                        if analysis_matches_template:
                            analysis_error = str(analysis_state.get("error") or "").strip()
                            if analysis_error:
                                st.error(f"元素识别失败：{analysis_error}")
                            else:
                                detected_count = len(
                                    [
                                        item
                                        for item in list(analysis_state.get("elements") or [])
                                        if isinstance(item, dict)
                                    ]
                                )
                                st.success(f"已识别 {detected_count} 个元素组，可继续校对或重新识别。")
                        else:
                            st.info("模板已就绪，点击后会识别产品、品牌、模特、文案和细节元素。")
                    if analyze_elements_clicked:
                        with st.spinner("正在分析整张 A+ 的产品、品牌、模特、文案和细节元素…"):
                            try:
                                detected_elements = analyze_main_image_a_plus_elements(
                                    main_image_a_plus_template_file
                                )
                                st.session_state[analysis_state_key] = {
                                    "template_signature": template_signature,
                                    "elements": detected_elements,
                                    "error": "",
                                }
                            except Exception as exc:
                                st.session_state[analysis_state_key] = {
                                    "template_signature": template_signature,
                                    "elements": [],
                                    "error": format_user_facing_error_message(exc),
                                }
                        st.rerun()
                    if analysis_matches_template:
                        main_image_a_plus_detected_elements = [
                            dict(item)
                            for item in list(analysis_state.get("elements") or [])
                            if isinstance(item, dict)
                        ]
                    if main_image_a_plus_detected_elements:
                        manual_job_state_key = (
                            f"main_image_a_plus_manual_job_{feature['key']}_{template_signature}"
                        )
                        manual_job_state = sync_main_image_a_plus_manual_element_job(
                            manual_job_state_key,
                            analysis_state_key,
                            template_signature,
                        )
                        manual_job_status = str(
                            manual_job_state.get("status") or ""
                        ).lower()
                        if manual_job_status == "completed":
                            completed_element = dict(
                                manual_job_state.get("new_element") or {}
                            )
                            if completed_element:
                                refreshed_analysis_state = dict(
                                    st.session_state.get(analysis_state_key) or {}
                                )
                                main_image_a_plus_detected_elements = [
                                    dict(item)
                                    for item in list(
                                        refreshed_analysis_state.get("elements") or []
                                    )
                                    if isinstance(item, dict)
                                ]
                                st.success(
                                    f"已补充 #{int(completed_element.get('id') or 0)} "
                                    f"{str(completed_element.get('name') or '新元素')}。"
                                )
                        elif manual_job_status == "error":
                            st.error(
                                "点击补漏失败："
                                f"{str(manual_job_state.get('error') or '请重新点击元素主体。')}"
                            )
                        manual_point = consume_main_image_a_plus_manual_point(template_signature)
                        if manual_point is not None:
                            existing_element = find_main_image_a_plus_element_at_point(
                                main_image_a_plus_detected_elements,
                                manual_point,
                            )
                            if existing_element is not None:
                                st.info(
                                    f"点击位置已经属于 #{int(existing_element.get('id') or 0)} "
                                    f"{str(existing_element.get('name') or '元素')}，无需重复添加。"
                                )
                            else:
                                manual_job_state = submit_main_image_a_plus_manual_element_job(
                                    manual_job_state_key,
                                    main_image_a_plus_template_file,
                                    template_signature,
                                    manual_point,
                                    main_image_a_plus_detected_elements,
                                )
                                manual_job_status = str(
                                    manual_job_state.get("status") or ""
                                ).lower()
                                if manual_job_status == "error":
                                    st.error(str(manual_job_state.get("error") or "点击补漏提交失败"))
                        if manual_job_status in {"queued", "running"}:
                            render_main_image_a_plus_manual_element_job_status(
                                manual_job_state_key,
                                analysis_state_key,
                                template_signature,
                            )
                        main_image_a_plus_element_preview = build_main_image_a_plus_element_preview(
                            main_image_a_plus_template_file,
                            main_image_a_plus_detected_elements,
                        )
                        main_image_a_plus_element_template_signature = template_signature
                        st.caption(
                            f"已识别 {len(main_image_a_plus_detected_elements)} 个元素组。右侧可查看完整编号图，也可以切换到“手动补漏”点击漏掉的内容。"
                        )
                        auto_material_key = (
                            f"main_image_a_plus_auto_materials_{feature['key']}_{template_signature}"
                        )
                        auto_material_files = load_upload_cache(
                            auto_material_key,
                            max_files=MAIN_IMAGE_A_PLUS_MAX_FILES,
                        )
                        auto_match_state_key = (
                            f"main_image_a_plus_auto_matches_{feature['key']}_{template_signature}"
                        )
                        review_state_key = (
                            f"main_image_a_plus_element_review_{feature['key']}_{template_signature}"
                        )
                        auto_match_state = dict(st.session_state.get(auto_match_state_key) or {})
                        auto_matches_by_element: dict[int, dict[str, Any]] = {}
                        auto_match_error = ""
                        auto_match_applied_count: int | None = None
                        auto_match_skipped_count = 0
                        auto_match_uncropped_count = 0
                        if (
                            str(auto_match_state.get("template_signature") or "")
                            == template_signature
                        ):
                            auto_matches_by_element = {
                                int(item.get("element_id") or 0): dict(item)
                                for item in list(auto_match_state.get("matches") or [])
                                if isinstance(item, dict) and int(item.get("element_id") or 0) > 0
                            }
                            auto_match_error = str(auto_match_state.get("error") or "").strip()
                            if "applied_count" in auto_match_state:
                                auto_match_applied_count = int(
                                    auto_match_state.get("applied_count") or 0
                                )
                                auto_match_skipped_count = int(
                                    auto_match_state.get("skipped_count") or 0
                                )
                                auto_match_uncropped_count = int(
                                    auto_match_state.get("uncropped_count") or 0
                                )
                        auto_match_clicked = False
                        with st.container(border=True):
                            st.markdown(
                                '<div class="a-plus-auto-fill-card-marker"></div>'
                                '<div class="panel-subtitle">AI 自动识别并填充替换素材</div>',
                                unsafe_allow_html=True,
                            )
                            auto_match_clicked = st.button(
                                "AI 识别素材并自动填充",
                                key=f"auto_match_main_image_a_plus_{feature['key']}_{template_signature}",
                                use_container_width=True,
                                type="secondary",
                                disabled=not auto_material_files,
                            )
                            if auto_match_error:
                                st.error(f"自动填充失败：{auto_match_error}")
                            elif auto_match_applied_count is not None:
                                st.success(
                                    f"AI 已裁切并填充 {auto_match_applied_count} 个编号；"
                                    f"已有人工素材的 {auto_match_skipped_count} 个编号未覆盖；"
                                    f"未能准确裁出的 {auto_match_uncropped_count} 个编号未自动填充。"
                                )
                            elif auto_material_files:
                                st.caption("素材已就绪，上方按钮可开始自动匹配。")
                            else:
                                st.caption("先在下方上传素材，按钮会在原位置自动启用。")
                            auto_material_files = render_multi_image_uploader(
                                "批量上传替换素材",
                                key=auto_material_key,
                                help_text=(
                                    "可混合上传产品、包装、模特、Logo、文案和细节图。"
                                    "AI 会识别每张图里的内容，并自动放入最合适的编号卡片。"
                                ),
                                max_files=MAIN_IMAGE_A_PLUS_MAX_FILES,
                                preview_slot_count=5,
                            )
                        if auto_match_clicked:
                            with st.spinner("正在识别每张素材并匹配产品、模特、品牌、文案和细节编号…"):
                                try:
                                    auto_matches = analyze_main_image_a_plus_replacement_matches(
                                        main_image_a_plus_template_file,
                                        main_image_a_plus_detected_elements,
                                        auto_material_files,
                                    )
                                    applied_matches: list[dict[str, Any]] = []
                                    skipped_matches: list[dict[str, Any]] = []
                                    uncropped_matches: list[dict[str, Any]] = []
                                    processed_matches: list[dict[str, Any]] = []
                                    for auto_match in auto_matches:
                                        processed_match = dict(auto_match)
                                        matched_element_id = int(auto_match.get("element_id") or 0)
                                        matched_image_index = int(auto_match.get("image_index") or 0)
                                        matched_element = next(
                                            (
                                                item
                                                for item in main_image_a_plus_detected_elements
                                                if int(item.get("id") or 0) == matched_element_id
                                            ),
                                            {},
                                        )
                                        matched_upload_key = (
                                            f"main_image_a_plus_element_{feature['key']}_"
                                            f"{template_signature}_{matched_element_id}"
                                        )
                                        existing_replacement_files = load_upload_cache(
                                            matched_upload_key,
                                            max_files=1,
                                        )
                                        previous_auto_match = auto_matches_by_element.get(
                                            matched_element_id
                                        )
                                        existing_replacement_name = (
                                            get_uploaded_file_name(existing_replacement_files[0])
                                            if existing_replacement_files
                                            else ""
                                        )
                                        previous_auto_names = set()
                                        if previous_auto_match is not None:
                                            previous_cropped_name = str(
                                                previous_auto_match.get("cropped_reference_name") or ""
                                            ).strip()
                                            if previous_cropped_name:
                                                previous_auto_names.add(previous_cropped_name)
                                            previous_image_index = int(
                                                previous_auto_match.get("image_index") or 0
                                            )
                                            if 1 <= previous_image_index <= len(auto_material_files):
                                                previous_auto_names.add(
                                                    get_uploaded_file_name(
                                                        auto_material_files[previous_image_index - 1]
                                                    )
                                                )
                                        existing_is_previous_auto_fill = bool(
                                            existing_replacement_name
                                            and existing_replacement_name in previous_auto_names
                                        )
                                        if (
                                            existing_replacement_files
                                            and not existing_is_previous_auto_fill
                                        ):
                                            processed_match["crop_status"] = "manual_preserved"
                                            skipped_matches.append(processed_match)
                                            processed_matches.append(processed_match)
                                            continue
                                        if 1 <= matched_image_index <= len(auto_material_files):
                                            cropped_replacement = crop_main_image_a_plus_replacement_input(
                                                auto_material_files[matched_image_index - 1],
                                                auto_match.get("crop_box"),
                                                matched_element_id,
                                                str(
                                                    matched_element.get("name")
                                                    or auto_match.get("detected_content")
                                                    or f"元素_{matched_element_id}"
                                                ),
                                            )
                                            if cropped_replacement is None:
                                                processed_match["crop_status"] = "not_located"
                                                uncropped_matches.append(processed_match)
                                                processed_matches.append(processed_match)
                                                continue
                                            save_upload_cache(
                                                matched_upload_key,
                                                [cropped_replacement],
                                            )
                                            processed_match["crop_status"] = "applied"
                                            processed_match["cropped_reference_name"] = str(
                                                cropped_replacement.get("name") or ""
                                            )
                                            applied_matches.append(processed_match)
                                            processed_matches.append(processed_match)
                                    st.session_state[auto_match_state_key] = {
                                        "template_signature": template_signature,
                                        "matches": processed_matches,
                                        "applied_count": len(applied_matches),
                                        "skipped_count": len(skipped_matches),
                                        "uncropped_count": len(uncropped_matches),
                                        "material_count": len(auto_material_files),
                                    }
                                    st.session_state[review_state_key] = False
                                except Exception as exc:
                                    st.session_state[auto_match_state_key] = {
                                        "template_signature": template_signature,
                                        "matches": [],
                                        "error": format_user_facing_error_message(exc),
                                    }
                            st.rerun()
                        st.markdown('<div class="panel-subtitle">按编号校对替换元素</div>', unsafe_allow_html=True)
                        st.markdown(
                            '<div class="slot-helper">逐项检查 AI 填充结果；可以更换、移除或为未匹配编号手动上传，留空编号保持原样</div>',
                            unsafe_allow_html=True,
                        )
                        element_columns = st.columns(2, gap="small")
                        for element_index, element in enumerate(main_image_a_plus_detected_elements):
                            element_id = int(element.get("id") or 0)
                            element_name = str(element.get("name") or f"元素 {element_id}")
                            replacement_hint = str(
                                element.get("replacement_hint")
                                or element.get("description")
                                or "上传包含该元素的新图片"
                            )
                            region_count = len(list(element.get("regions") or []))
                            element_upload_key = (
                                f"main_image_a_plus_element_{feature['key']}_{template_signature}_{element_id}"
                            )
                            has_uploaded_replacement = bool(
                                load_upload_cache(element_upload_key, max_files=1)
                            )
                            auto_match = auto_matches_by_element.get(element_id)
                            if has_uploaded_replacement and auto_match is not None:
                                confidence_percent = round(
                                    float(auto_match.get("confidence") or 0) * 100
                                )
                                status_text = f" · AI 裁切 {confidence_percent}%"
                            elif (
                                auto_match is not None
                                and str(auto_match.get("crop_status") or "") == "not_located"
                            ):
                                status_text = " · 待手动裁切"
                            else:
                                status_text = " · 已上传" if has_uploaded_replacement else ""
                            with element_columns[element_index % 2]:
                                with st.expander(
                                    f"#{element_id} {element_name} · {region_count} 处{status_text}",
                                    expanded=has_uploaded_replacement,
                                ):
                                    st.caption(f"{replacement_hint}。留空则保持原元素不变。")
                                    if auto_match is not None:
                                        auto_reason = str(auto_match.get("reason") or "").strip()
                                        auto_content = str(
                                            auto_match.get("detected_content") or ""
                                        ).strip()
                                        if str(auto_match.get("crop_status") or "") == "not_located":
                                            st.caption("未能定位出独立元素，已阻止整图自动填充，请手动上传裁切素材。")
                                        if auto_reason or auto_content:
                                            st.caption(
                                                "AI 判断："
                                                + "；".join(
                                                    text
                                                    for text in (auto_content, auto_reason)
                                                    if text
                                                )
                                            )
                                    replacement_file = render_compact_element_image_uploader(
                                        f"上传 #{element_id} {element_name}",
                                        key=element_upload_key,
                                        help_text=f"只用于替换模板编号 #{element_id} 的“{element_name}”，不会用于其他编号。",
                                    )
                                    if replacement_file is not None:
                                        amazon_source_files.append(replacement_file)
                                        replacement_mapping = dict(element)
                                        replacement_mapping["reference_name"] = get_uploaded_file_name(
                                            replacement_file
                                        )
                                        main_image_a_plus_element_replacements.append(
                                            replacement_mapping
                                        )
                        st.info(
                            f"当前已选择 {len(main_image_a_plus_element_replacements)} / {len(main_image_a_plus_detected_elements)} 个元素进行替换。"
                        )
                        main_image_a_plus_element_review_confirmed = st.checkbox(
                            "我已逐项校对编号、替换素材和未识别元素，可以开始替换",
                            key=review_state_key,
                            help="勾选后才会启用生成按钮；AI 自动填充不会直接开始生成。",
                        )
            else:
                st.markdown(
                    (
                        f'<div class="panel-subtitle">替换内容参考图（最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张）</div>'
                        if uses_finished_a_plus_template
                        else f'<div class="panel-subtitle">商品主图（最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张）</div>'
                    ),
                    unsafe_allow_html=True,
                )
                amazon_source_files = render_multi_image_uploader(
                    (
                        "上传要替换进去的内容参考图"
                        if uses_finished_a_plus_template
                        else "上传商品主图"
                    ),
                    key=f"main_image_a_plus_uploader_{feature['key']}",
                    help_text=(
                        (
                            "可上传包含新文案、品牌、Logo、模特、产品、包装、细节和参数的 JPG / PNG / WEBP。"
                            "第 1 张作为核心商品与品牌依据，其余图片由 AI 自动匹配到模板对应位置，"
                            f"最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张。"
                        )
                        if uses_finished_a_plus_template
                        else (
                            "可上传 JPG / PNG / WEBP。第 1 张作为核心商品主图，其余图片用于补充角度、细节、"
                            f"套装内容和使用场景，最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张。"
                        )
                    ),
                    max_files=MAIN_IMAGE_A_PLUS_MAX_FILES,
                    allow_reorder=True,
                )
                st.markdown(
                    (
                        '<div class="slot-helper">请把最能代表新商品与品牌的图片放在第一张；其余文案、模特、产品细节图可继续上传</div>'
                        if uses_finished_a_plus_template
                        else '<div class="slot-helper">请把最能代表商品的图片第一个上传；图片顺序即参考优先级</div>'
                    ),
                    unsafe_allow_html=True,
                )
            if main_image_a_plus_mode in MAIN_IMAGE_A_PLUS_FREE_MODES or feature.get("key") == A_PLUS_REFERENCE_LAB_FEATURE_KEY:
                st.markdown('<div class="panel-subtitle">选择成品规格</div>', unsafe_allow_html=True)
                layout_keys = list(MAIN_IMAGE_A_PLUS_LAYOUTS)
                size_options = [
                    (device, size)
                    for device, size in MAIN_IMAGE_A_PLUS_SIZE_OPTIONS
                ]
                combined_options = [
                    (layout_key, device, size)
                    for layout_key in layout_keys
                    for device, size in size_options
                ]
                default_option = (MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY, "desktop", (1464, 2400))
                selected_option = st.selectbox(
                    "成品版式与尺寸",
                    options=combined_options,
                    index=combined_options.index(default_option),
                    format_func=lambda item: (
                        f"{'电脑端' if item[1] == 'desktop' else '手机端'}｜"
                        f"{item[2][0]}×{item[2][1]}｜"
                        f"{MAIN_IMAGE_A_PLUS_LAYOUTS[item[0]]['label'].split('｜')[-1]}"
                    ),
                    key=f"main_image_a_plus_layout_size_{feature['key']}",
                    label_visibility="collapsed",
                )
                main_image_a_plus_layout_key, _selected_device, selected_size = selected_option
                selected_a_plus_layout = get_main_image_a_plus_layout(main_image_a_plus_layout_key)
                selected_a_plus_layout = dict(selected_a_plus_layout)
                selected_a_plus_layout["target_size"] = tuple(selected_size)
                selected_a_plus_layout["section_heights"] = (
                    (selected_size[1] // (selected_size[0] == 600 and 450 or 600),)
                    * (selected_size[1] // (selected_size[0] == 600 and 450 or 600))
                )
                a_plus_layout_skill_context = resolve_a_plus_layout_skill_context_for_layout(
                    a_plus_layout_skill_context,
                    selected_a_plus_layout,
                    account_name=str(st.session_state.get("auth_username") or "admin"),
                )
                selected_width, selected_height = selected_a_plus_layout["target_size"]
                st.info(
                    (
                        f"锁定宽度 {selected_width}px，{selected_height}px 仅作构图高度参考 · 实际高度等比自适应 · 首屏商业主视觉强化 · 单一视觉中心 · "
                        "杂志式不对称构图 · 克制信息层级 · 生成后自动成品复核。"
                        if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN
                        else f"锁定宽度 {selected_width}px，{selected_height}px 仅作构图高度参考 · 实际高度等比自适应、不裁切、不补边 · 整张一次生成 · 不拆段、不拼接 · "
                        "艺术指导强化 · 文字安全区锁定 · 生成后自动检查裁切与版式。"
                    )
                )
            st.markdown('<div class="panel-subtitle">补充宣传要求（可选）</div>', unsafe_allow_html=True)
            if not supports_a_plus_first_screen_selling_points and primary_action_slot is None:
                primary_action_slot = st.empty()
            main_image_a_plus_prompt = st.text_area(
                "输入主图生A+补充要求",
                key=f"main_image_a_plus_prompt_{feature['key']}",
                placeholder="例如：突出轻盈、自然和佩戴舒适；整体使用黑金高级风格。请只填写真实、可核实的卖点。",
                height=110,
                label_visibility="collapsed",
            )
        elif supports_amazon_a_plus:
            a_plus_layout_skill_context = render_a_plus_layout_skill_builder(
                feature["key"],
                str(st.session_state.get("auth_username") or "admin"),
                get_main_image_a_plus_layout(
                    str(
                        st.session_state.get(
                            f"amazon_layout_{feature['key']}",
                            MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY,
                        )
                    )
                ),
            )
            st.markdown(
                f'<div class="panel-subtitle">A+参考图（最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张）</div>',
                unsafe_allow_html=True,
            )
            amazon_source_files = render_multi_image_uploader(
                "上传A+参考图",
                key=f"amazon_uploader_{feature['key']}",
                help_text=(
                    "可上传 JPG / PNG / WEBP。第 1 张作为核心商品和品牌依据，其余图片补充角度、细节、包装、模特、文案与使用场景。"
                    f"最多 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张。"
                ),
                max_files=MAIN_IMAGE_A_PLUS_MAX_FILES,
                allow_reorder=True,
            )
            st.markdown('<div class="slot-helper">请把最能代表商品与品牌的图片放在第一张；图片顺序即参考优先级</div>', unsafe_allow_html=True)
            st.markdown('<div class="panel-subtitle">选择成品规格</div>', unsafe_allow_html=True)
            a_plus_psd_layout_keys = list(MAIN_IMAGE_A_PLUS_LAYOUTS)
            a_plus_psd_layout_key = st.selectbox(
                "选择自由创作 PSD 规格",
                options=a_plus_psd_layout_keys,
                index=a_plus_psd_layout_keys.index(MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY),
                format_func=lambda value: str(MAIN_IMAGE_A_PLUS_LAYOUTS[value]["label"]),
                key=f"amazon_layout_{feature['key']}",
                label_visibility="collapsed",
            )
            a_plus_psd_layout = get_main_image_a_plus_layout(a_plus_psd_layout_key)
            a_plus_layout_skill_context = resolve_a_plus_layout_skill_context_for_layout(
                a_plus_layout_skill_context,
                a_plus_psd_layout,
                account_name=str(st.session_state.get("auth_username") or "admin"),
            )
            a_plus_psd_width, a_plus_psd_height = a_plus_psd_layout["target_size"]
            amazon_size_text = f"{a_plus_psd_width}*{a_plus_psd_height}"
            st.info(
                f"{a_plus_psd_width}×{a_plus_psd_height}px · 商业背景独立图层 · 商品/模特/文案/装饰自动拆层。"
            )
            st.markdown('<div class="panel-subtitle">补充宣传要求（可选）</div>', unsafe_allow_html=True)
            if not supports_a_plus_first_screen_selling_points and primary_action_slot is None:
                primary_action_slot = st.empty()
            amazon_a_plus_prompt = st.text_area(
                "输入自由创作 PSD 补充要求",
                key=f"amazon_prompt_{feature['key']}",
                placeholder="例如：整体使用黑金高级风格，突出轻盈、自然和佩戴舒适，只使用图片中真实可见的卖点。",
                height=110,
                label_visibility="collapsed",
            )
            st.caption("PSD 中的文字和视觉元素为独立像素图层，可在 Photoshop 中移动、隐藏、缩放或替换。")
        elif supports_background_texture:
            st.markdown('<div class="panel-subtitle">原图（1 张）</div>', unsafe_allow_html=True)
            uploaded_file = render_single_image_uploader(
                "上传需要调整背景质感的原图",
                key=f"uploader_{feature['key']}",
                help_text="上传 JPG / PNG / WEBP。人物、商品和构图会保持不变，只编辑场景背景表面。",
            )
            st.markdown('<div class="panel-subtitle">选择背景质感（可多选）</div>', unsafe_allow_html=True)
            background_texture_presets = st.multiselect(
                "背景质感预设",
                options=list(BACKGROUND_TEXTURE_PRESETS),
                default=["高级哑光"],
                key=f"background_texture_presets_{feature['key']}",
                placeholder="选择一种或多种质感",
                label_visibility="collapsed",
            )
            if background_texture_presets:
                selected_texture_details = "；".join(
                    f"{name}：{BACKGROUND_TEXTURE_PRESETS[name]}"
                    for name in background_texture_presets
                )
                st.caption(selected_texture_details)
            st.markdown('<div class="panel-subtitle">直接描述想要的质感（可选）</div>', unsafe_allow_html=True)
            if not supports_a_plus_first_screen_selling_points and primary_action_slot is None:
                primary_action_slot = st.empty()
            background_texture_prompt = st.text_area(
                "输入背景质感描述",
                key=f"background_texture_prompt_{feature['key']}",
                placeholder="例如：背景墙改成偏暖灰色的细腻微水泥，纹理轻一些、低反光，保留原来的光影和空间结构。",
                height=108,
                label_visibility="collapsed",
            )
            st.caption("可以只选预设、只写描述，也可以组合使用；文字描述会优先控制具体颜色与纹理强弱。")
        elif supports_pose_references or supports_scene_references or supports_dual_reference_upload:
            subject_label = "主体图（1 张）" if supports_dual_reference_upload else "主模特图（1 张）"
            st.markdown(f'<div class="panel-subtitle">{subject_label}</div>', unsafe_allow_html=True)
            uploaded_file = render_single_image_uploader(
                "上传主体图" if supports_dual_reference_upload else "上传主模特图",
                key=f"uploader_{feature['key']}",
                help_text=help_text,
            )

            if supports_skin_tone_reference:
                st.markdown('<div class="panel-subtitle">肤色参考图（1 张）</div>', unsafe_allow_html=True)
                skin_tone_reference_file = render_single_image_uploader(
                    "上传肤色参考图",
                    key=f"skin_tone_ref_{feature['key']}",
                )

            if supports_pupil_color_reference:
                st.markdown('<div class="panel-subtitle">瞳孔颜色参考图（1 张）</div>', unsafe_allow_html=True)
                pupil_color_reference_file = render_single_image_uploader(
                    "上传瞳孔颜色参考图",
                    key=f"pupil_color_ref_{feature['key']}",
                )

            if supports_eye_shape_reference:
                st.markdown('<div class="panel-subtitle">眼型参考图（1 张）</div>', unsafe_allow_html=True)
                eye_shape_reference_file = render_single_image_uploader(
                    "上传眼型参考图",
                    key=f"eye_shape_ref_{feature['key']}",
                )

            if supports_side_angle_reference:
                st.markdown('<div class="panel-subtitle">角度参考图（1 张）</div>', unsafe_allow_html=True)
                side_angle_reference_file = render_single_image_uploader(
                    "上传角度参考图",
                    key=f"side_angle_ref_{feature['key']}",
                )

            if supports_pose_references:
                st.markdown('<div class="panel-subtitle">姿势参考图（最多 5 张）</div>', unsafe_allow_html=True)
                pose_reference_files = render_reference_slot_uploaders(f"pose_refs_{feature['key']}", 5)
                st.markdown('<div class="slot-helper">直接在方框中上传姿势参考图</div>', unsafe_allow_html=True)

            if supports_scene_references:
                st.markdown('<div class="panel-subtitle">场景参考图（最多 5 张）</div>', unsafe_allow_html=True)
                scene_reference_files = render_reference_slot_uploaders(f"scene_refs_{feature['key']}", 5)
                st.markdown('<div class="slot-helper">直接在方框中上传场景参考图</div>', unsafe_allow_html=True)
        else:
            uploaded_file = render_single_image_uploader(
                "上传完整亚马逊 A+ 原图" if supports_amazon_to_walmart_a_plus else "上传参考图",
                key=f"uploader_{feature['key']}",
                help_text=help_text,
            )
            if feature.get("key") == "product_retouch_local":
                st.markdown('<div class="panel-subtitle">修复要求</div>', unsafe_allow_html=True)
                if not supports_a_plus_first_screen_selling_points and primary_action_slot is None:
                    primary_action_slot = st.empty()
                local_retouch_prompt = st.text_area(
                    "输入要修复的区域和瑕疵",
                    key=f"local_retouch_prompt_{feature['key']}",
                    placeholder="例如：清除左上角的浅黑线，保持包装文字、材质和光泽不变。",
                    height=110,
                    label_visibility="collapsed",
                )
            if supports_image_resize:
                source_width, source_height = (2000, 2000)
                if uploaded_file is not None:
                    source_width, source_height = get_uploaded_input_dimensions(uploaded_file)
                    st.caption(f"原图 {source_width} × {source_height} px")
                lock_ratio = st.checkbox(
                    "锁定原比例",
                    value=True,
                    key=f"resize_lock_ratio_{feature['key']}",
                )
                width_col, height_col = st.columns(2, gap="small")
                with width_col:
                    resize_target_width = int(
                        st.number_input(
                            "目标宽度",
                            min_value=1,
                            max_value=12000,
                            value=max(source_width, 2000),
                            step=100,
                            key=f"resize_width_{feature['key']}",
                        )
                    )
                height_key = f"resize_height_{feature['key']}"
                if lock_ratio:
                    st.session_state[height_key] = max(
                        1,
                        int(round(resize_target_width * source_height / max(source_width, 1))),
                    )
                with height_col:
                    resize_target_height = int(
                        st.number_input(
                            "目标高度",
                            min_value=1,
                            max_value=12000,
                            value=max(source_height, 2000),
                            step=100,
                            key=height_key,
                            disabled=lock_ratio,
                        )
                    )
                st.caption(f"输出 {resize_target_width} × {resize_target_height} px · PNG")

        process_button_label = (
            "开始 8K 超清"
            if feature.get("key") == JIMENG_HD_FEATURE_KEY
            else (
                "开始放大"
                if supports_image_resize
                else (
                    "开始智能分析"
                    if supports_image_smart_analysis
                    else (
                        "开始生成 A+3.0"
                        if supports_a_plus_reference_lab
                        else (
                            "开始生成 A+"
                            if supports_main_image_a_plus
                            else (
                                "开始生成 PSD"
                                if supports_amazon_a_plus
                                else (
                                    "开始更换质感"
                                    if supports_background_texture
                                    else ("开始扩图" if supports_outpaint else "开始处理")
                                )
                            )
                        )
                    )
                )
            )
        )
        if supports_a_plus_first_screen_selling_points:
            process_button_label = (
                "生成首屏"
                if a_plus_first_screen_workflow_stage == "hero"
                else "完成整张 A+"
                if a_plus_first_screen_workflow_stage == "selling_points"
                else "生成首屏＋卖点 A+"
            )
        has_active_job = str(job_info.get("status") or "").strip().lower() in {"queued", "running"}
        if has_active_job:
            process_button_label = f"{process_button_label}（加入队列）"
        is_element_review_pending = bool(
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and not main_image_a_plus_element_review_confirmed
        )
        process_button_disabled = is_element_review_pending
        if not supports_a_plus_first_screen_selling_points:
            settings_parent = primary_action_slot.container() if primary_action_slot is not None else st.container()
            with settings_parent, st.container(key="workbench_settings", border=True):
                st.markdown('<div class="result-block-title">生成设置</div>', unsafe_allow_html=True)
                count_col, model_col = st.columns([1, 2], gap="small")
                with count_col:
                    if str(feature.get("output_mode") or "") == "image" and not supports_image_resize and not supports_a_plus_reference_lab:
                        selected_output_count = int(st.number_input(
                            "生成数量", min_value=FEATURE_OUTPUT_COUNT_MIN, max_value=FEATURE_OUTPUT_COUNT_MAX,
                            value=default_output_count, step=1, disabled=bool(fixed_output_count),
                            key=f"output_count_{feature['key']}",
                        ))
                    else:
                        st.caption(f"结果数量：{selected_output_count}" if selected_output_count else "分析结果")
                with model_col:
                    if len(model_options_for_feature) == 1:
                        active_model = model_options_for_feature[0]
                        st.text_input("当前模型", value=get_model_display_name(active_model), disabled=True, key=f"workbench_model_{feature['key']}")
                    else:
                        active_model = st.selectbox(
                            "生成方式" if supports_outpaint else "当前模型", model_options_for_feature,
                            index=model_options_for_feature.index(default_model_for_feature),
                            format_func=get_model_display_name, key=f"model_select_{feature['key']}",
                        )
            with shared_action_dock:
                if supports_outpaint:
                    status_col, clear_col, action_col = st.columns([2, 0.5, 1], vertical_alignment="center")
                    with clear_col:
                        upload_key = f"batch_uploader_{feature['key']}"
                        if st.button("清空上传", key=f"clear_upload_{upload_key}", type="secondary", use_container_width=True):
                            clear_upload_cache(upload_key)
                            reset_upload_widget(upload_key)
                            st.rerun()
                else:
                    status_col, action_col = st.columns([2, 1], vertical_alignment="center")
                with status_col:
                    st.caption(f"{feature['name']} · {'任务处理中，可继续加入队列' if has_active_job else '设置完成后开始处理'}")
                with action_col:
                    submitted = st.button(
                        f"开始生成 {selected_output_count} 张" if supports_a_plus_reference_lab else process_button_label,
                        key=f"process_{feature['key']}", type="primary", use_container_width=True,
                        disabled=process_button_disabled,
                    )
    with right_col:
        if not supports_a_plus_first_screen_selling_points:
            st.markdown('<div class="workbench-right-marker" style="display:none"></div>', unsafe_allow_html=True)
        if supports_a_plus_reference_lab:
            st.markdown('<div class="a-plus-lab-right-marker"></div>', unsafe_allow_html=True)
        elif supports_a_plus_first_screen_selling_points:
            st.markdown('<div class="fusion-right-marker" style="display:none"></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="feature-workbench-right-marker"></div>', unsafe_allow_html=True)
        if supports_batch_multi_upload:
            st.markdown('<div class="batch-right-column-marker"></div>', unsafe_allow_html=True)
        shows_element_map = bool(
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and main_image_a_plus_element_preview
        )
        right_panel_title = (
            "元素标注与生成结果"
            if shows_element_map
            else ("图片分析报告" if supports_image_smart_analysis else "结果图预览")
        )
        st.markdown(
            f'<div class="result-block-title">{right_panel_title}</div>',
            unsafe_allow_html=True,
        )
        result_images = list(result.get("images") or [])
        result_download_images = build_result_download_sources(
            result_images,
            list(result.get("history_records") or []),
        )
        source_images = list(result.get("source_images") or [])
        outpaint_alignments = list(result.get("outpaint_alignments") or [])
        if not source_images and supports_batch_multi_upload and batch_source_files:
            fallback_sources = list(batch_source_files)
            if supports_outpaint:
                fallback_sources = [
                    source_file
                    for source_file in batch_source_files
                    for _ in range(OUTPAINT_RESULTS_PER_SOURCE)
                ]
            for source_file in fallback_sources[: len(result_images)]:
                try:
                    source_images.append(uploaded_input_to_data_url(source_file))
                except Exception:
                    source_images.append("")
        result_captions = list(result.get("captions") or [])
        result_view_container = (
            st.container(key="fusion_results", border=False)
            if supports_a_plus_first_screen_selling_points
            else st.container(key="workbench_results", border=False)
        )
        if shows_element_map:
            element_map_tab, manual_picker_tab, result_view_container = st.tabs(
                ["元素标注图", "手动补漏", "生成结果"]
            )
            with element_map_tab:
                render_zoomable_image_gallery(
                    [main_image_a_plus_element_preview],
                    columns=1,
                    thumb_height=760,
                    component_key=(
                        "main_image_a_plus_element_map_"
                        f"{main_image_a_plus_element_template_signature}"
                    ),
                    fit_mode="contain",
                    max_width_percent=100,
                    compress_preview=True,
                    include_full_src=True,
                )
                st.caption(
                    "点击标注图可全屏放大查看；右侧编号对应左侧同号上传卡片，同号多个区域共用一份替换素材。"
                )
            with manual_picker_tab:
                render_main_image_a_plus_manual_element_picker(
                    main_image_a_plus_element_preview,
                    main_image_a_plus_element_template_signature,
                    component_key=(
                        "main_image_a_plus_manual_picker_"
                        f"{main_image_a_plus_element_template_signature}"
                    ),
                )
        with result_view_container:
            if render_result_loading(feature["key"]):
                pass
            elif supports_image_smart_analysis:
                render_image_smart_analysis_report(
                    result,
                    str(job_info.get("status") or ""),
                    str(job_info.get("job_id") or result.get("created_at") or "latest"),
                )
            elif supports_amazon_a_plus and result_images:
                psd_bytes = result.get("psd_bytes")
                if isinstance(psd_bytes, (bytes, bytearray)) and psd_bytes:
                    layer_count = int(result.get("layer_count") or 0)
                    psd_file_name = str(result.get("psd_file_name") or "amazon_a_plus.psd")
                    if not psd_file_name.lower().endswith(".psd"):
                        psd_file_name += ".psd"
                    st.download_button(
                        "下载 PSD 源文件（Photoshop）",
                        data=bytes(psd_bytes),
                        file_name=psd_file_name,
                        mime="application/octet-stream",
                        key=f"download_amazon_psd_{psd_file_name}",
                        icon=":material/download:",
                        type="primary",
                        use_container_width=True,
                    )
                    st.caption(
                        f"主下载文件为 .psd，共 {layer_count} 个可编辑像素图层。下方图片只用于查看效果，不再提供 PNG 保存。"
                    )
                else:
                    st.warning("当前结果尚未生成 PSD 文件，请重新生成一次。")
                layered_tab, background_tab, green_tab = st.tabs(["A+ 成品预览", "独立背景层", "AI 分层底稿"])
                with layered_tab:
                    render_zoomable_image_gallery(
                        result_images,
                        columns=1,
                        thumb_height=None,
                        component_key="amazon_a_plus_result_preview_only",
                        fit_mode="contain",
                        max_width_percent=50,
                        compress_preview=True,
                        include_full_src=True,
                        full_images=result_download_images,
                        allow_native_image_download=False,
                    )
                with background_tab:
                    background_images = list(result.get("background_images") or [])
                    if background_images:
                        render_zoomable_image_gallery(
                            background_images,
                            columns=1,
                            thumb_height=None,
                            component_key="amazon_a_plus_background_viewer",
                            fit_mode="contain",
                            max_width_percent=50,
                            compress_preview=True,
                            include_full_src=True,
                            allow_native_image_download=False,
                        )
                    else:
                        st.info("当前结果没有独立背景层。")
                with green_tab:
                    green_screen_images = list(result.get("green_screen_images") or [])
                    if green_screen_images:
                        render_zoomable_image_gallery(
                            green_screen_images,
                            columns=1,
                            thumb_height=None,
                            component_key="amazon_a_plus_green_screen_viewer",
                            fit_mode="contain",
                            max_width_percent=50,
                            compress_preview=True,
                            include_full_src=True,
                            allow_native_image_download=False,
                        )
                    else:
                        st.info("当前结果没有保留绿幕底稿。")
            elif (
                supports_main_image_a_plus
                and result_images
                and str(result.get("main_image_a_plus_text_edit_source") or "").strip()
            ):
                before_tab, after_tab = st.tabs(["文字编辑前", "文字编辑后"])
                text_edit_source = str(
                    result.get("main_image_a_plus_text_edit_source") or ""
                ).strip()
                with before_tab:
                    render_zoomable_image_gallery(
                        [text_edit_source],
                        columns=1,
                        thumb_height=None,
                        component_key="main_image_a_plus_text_edit_source",
                        fit_mode="contain",
                        max_width_percent=50,
                        compress_preview=True,
                        include_full_src=True,
                        full_images=[text_edit_source],
                        embed_full_src=False,
                    )
                with after_tab:
                    render_zoomable_image_gallery(
                        result_images,
                        columns=1,
                        thumb_height=None,
                        component_key="main_image_a_plus_text_edit_result",
                        fit_mode="contain",
                        max_width_percent=50,
                        compress_preview=True,
                        include_full_src=True,
                        full_images=result_download_images,
                        embed_full_src=False,
                    )
            elif (
                supports_main_image_a_plus
                and result_images
                and str(result.get("mobile_adaptation_source") or "").strip()
            ):
                desktop_tab, mobile_tab = st.tabs(["电脑端原图", "手机端适配版"])
                desktop_source = str(result.get("mobile_adaptation_source") or "").strip()
                with desktop_tab:
                    render_zoomable_image_gallery(
                        [desktop_source],
                        columns=1,
                        thumb_height=None,
                        component_key="main_image_a_plus_mobile_source",
                        fit_mode="contain",
                        max_width_percent=50,
                        compress_preview=True,
                        include_full_src=True,
                        full_images=[desktop_source],
                        embed_full_src=False,
                    )
                with mobile_tab:
                    render_zoomable_image_gallery(
                        result_images,
                        columns=1,
                        thumb_height=None,
                        component_key="main_image_a_plus_mobile_result",
                        fit_mode="contain",
                        max_width_percent=50,
                        compress_preview=True,
                        include_full_src=True,
                        full_images=result_download_images,
                        embed_full_src=False,
                    )
            elif supports_batch_multi_upload and result_images and source_images:
                render_before_after_compare_gallery(
                    source_images,
                    result_images,
                    result_captions,
                    feature["key"],
                    outpaint_alignments=outpaint_alignments if supports_outpaint else None,
                    download_images=result_download_images,
                )
            elif supports_batch_multi_upload and result_images and result_captions:
                render_result_preview_with_captions(
                    result_images,
                    result_captions,
                    feature["key"],
                    download_images=result_download_images,
                )
            elif supports_a_plus_first_screen_selling_points:
                if not result_images:
                    st.markdown(
                        '<div class="fusion-result-empty"><div>✦</div><strong>准备生成你的 A+ 长图</strong>'
                        '<p>上传素材并填写要求后，点击下方生成</p></div>', unsafe_allow_html=True,
                    )
                else:
                    preview_index = st.selectbox(
                        "切换结果", range(len(result_images)), format_func=lambda i: f"结果 {i + 1}",
                        key=f"fusion_result_index_{feature['key']}",
                    )
                    zoom = st.select_slider("预览缩放", options=[50, 75, 100], value=100, key="fusion_result_zoom")
                    render_zoomable_image_gallery(
                        [result_images[preview_index]], columns=1, thumb_height=660,
                        component_key="fusion_result_view", fit_mode="contain", max_width_percent=zoom,
                        full_images=[result_download_images[preview_index]], include_full_src=True,
                    )
            elif supports_a_plus_reference_lab and not result_images:
                render_a_plus_reference_lab_empty_results(selected_output_count)
            else:
                render_result_preview(
                    result_images,
                    show_title=False,
                    download_images=result_download_images,
                )
            if supports_main_image_a_plus:
                if supports_a_plus_reference_lab and result_images:
                    result_style_key = str(
                        result.get("a_plus_reference_lab_style_key") or "auto"
                    )
                    st.caption(
                        f"A+ 商业方向：{get_a_plus_reference_style_label(result_style_key)}"
                        " · 内容仅来自本次上传素材 · 未加载 A++ 文件夹图片"
                    )
                if bool(result.get("designed_module_pipeline")):
                    st.caption(
                        f"已识别为完成广告模块 · 按 {int(result.get('section_count') or 0)} 个区段一对一重构 · 每张源图仅进入一个区段"
                    )
                source_repair_count = int(result.get("source_repair_count") or 0)
                if source_repair_count > 0:
                    st.caption(
                        f"源图完整性检查已完成 · 自动补齐 {source_repair_count} 张可信边缘截断素材"
                    )
                source_integrity_warnings = [
                    str(value).strip()
                    for value in list(result.get("source_integrity_warnings") or [])
                    if str(value).strip()
                ]
                if source_integrity_warnings:
                    st.warning("；".join(source_integrity_warnings[:3]))
            if supports_main_image_a_plus and (
                bool(result.get("quality_reviewed"))
                or bool(result.get("quality_result_restored"))
            ):
                quality_score = float(result.get("quality_score") or 0.0)
                if bool(result.get("quality_review_passed")):
                    st.caption(
                        f"成品复核已通过 · 设计质量 {quality_score:.1f}/10 · "
                        "文字安全区、主体完整性与版式层级已检查"
                    )
                else:
                    critical_issue_count = int(
                        result.get("quality_critical_issue_count") or 0
                    )
                    quality_repair_attempts = int(
                        result.get("quality_repair_attempts") or 0
                    )
                    issue_preview = "；".join(
                        str(issue).strip()
                        for issue in list(result.get("quality_review_issues") or [])[:3]
                        if str(issue).strip()
                    )
                    risk_summary = (
                        f"仍有 {critical_issue_count} 项完整性风险。"
                        if critical_issue_count
                        else "未发现人物或商品主体截断，但版式质检仍未完全通过。"
                    )
                    quality_message = (
                        f"已完成首版生成和 {quality_repair_attempts} 轮定向修复，并恢复问题最少的候选图到结果预览；设计质量 {quality_score:.1f}/10，"
                        if bool(result.get("quality_result_restored"))
                        else f"已完成首版生成和 {quality_repair_attempts} 轮定向修复，并保留问题最少的可编辑预览；设计质量 {quality_score:.1f}/10，"
                    )
                    quality_message += risk_summary
                    if issue_preview:
                        quality_message += f"重点检查：{issue_preview}。"
                    quality_message += (
                        "这是自动修复后的最佳候选，已保留到结果区供检查和下载，不代表质检通过。"
                        if supports_a_plus_reference_lab
                        else "可使用下方的成品文字编辑器修正文案与文字位置；人物或商品严重截断的结果仍会阻断。"
                    )
                    st.warning(quality_message)
            if supports_main_image_a_plus and result_download_images:
                crop_result_id = str(
                    result.get("result_id")
                    or job_info.get("job_id")
                    or result.get("created_at")
                    or "latest"
                )
                render_main_image_a_plus_crop_downloads(
                    result_download_images,
                    key_prefix=f"current_main_image_a_plus_{crop_result_id}",
                )
                if feature["key"] == MAIN_IMAGE_A_PLUS_FEATURE_KEY:
                    render_main_image_a_plus_text_editor(
                        str(result_download_images[0]),
                        key_prefix=f"current_main_image_a_plus_text_edit_{crop_result_id}",
                    )
                result_target_size = tuple(int(value) for value in (result.get("target_size") or ()))
                is_mobile_result = (
                    str(result.get("main_image_a_plus_mode") or "").strip()
                    == MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT
                    or is_main_image_a_plus_mobile_size(result_target_size)
                )
                mobile_adaptation_active = str(job_info.get("status") or "").strip().lower() in {
                    "queued",
                    "running",
                }
                if not is_mobile_result and feature["key"] == MAIN_IMAGE_A_PLUS_FEATURE_KEY:
                    if st.button(
                        "生成手机端适配版",
                        key=f"adapt_main_image_a_plus_mobile_{crop_result_id}",
                        type="primary",
                        use_container_width=True,
                        disabled=mobile_adaptation_active,
                    ):
                        submit_main_image_a_plus_mobile_adaptation(str(result_download_images[0]))
                        st.rerun()

    if supports_a_plus_first_screen_selling_points:
        with st.container(key="fusion_action_dock", border=True):
            status_col, submit_col = st.columns([2, 1])
            ready = bool(hero_source_files and selling_point_files)
            with status_col:
                st.markdown(f"{'✓' if ready else '○'} 底稿 {len(hero_source_files)} 张 · 卖点素材 {len(selling_point_files)} 张 · {'已就绪' if ready else '请补充素材'}")
            with submit_col:
                submitted = st.button(
                    process_button_label, key=f"process_{feature['key']}", type="primary",
                    use_container_width=True, disabled=not ready,
                )

    if job_info.get("status") == "completed":
        if feature.get("output_mode") == "image" and not (result.get("images") or []):
            st.warning("本次任务已结束，但模型没有返回图片。建议重试一次，或切换其他模型。")
        result_text = str(result.get("text") or "").strip()
        if result_text and not supports_image_smart_analysis:
            if "已自动回退为智能超清结果" in result_text:
                st.warning(result_text)
            else:
                st.info(result_text)
        storage_error = str(result.get("storage_error") or "").strip()
        if storage_error:
            st.warning(storage_error)
        psd_storage_error = str(result.get("psd_storage_error") or "").strip()
        if psd_storage_error:
            st.warning(psd_storage_error)

    if submitted:
        if supports_batch_multi_upload:
            files = list(batch_source_files)
        elif supports_ai_qa_image:
            files = list(ai_qa_source_files)
        elif supports_amazon_to_walmart_a_plus:
            files = [uploaded_file] if uploaded_file is not None else []
        elif supports_a_plus_images_api:
            files = list(amazon_source_files)
        else:
            files = [uploaded_file] if uploaded_file is not None else []
        if (
            supports_a_plus_first_screen_selling_points
            and a_plus_first_screen_workflow_stage == "selling_points"
        ):
            hero_result = dict(
                (st.session_state.get("a_plus_first_screen_hero_results") or {}).get(feature["key"])
                or {}
            )
            hero_images = list(hero_result.get("images") or [])
            if hero_images:
                try:
                    hero_bytes, hero_mime_type = load_image_bytes_from_url(str(hero_images[0]))
                    hero_extension = mimetypes.guess_extension(hero_mime_type) or ".png"
                    files.insert(
                        0,
                        {
                            "data": hero_bytes,
                            "name": f"locked_first_screen{hero_extension}",
                            "type": hero_mime_type,
                        },
                    )
                except Exception as exc:
                    a_plus_first_screen_locked_hero_ready = False
                    st.warning(f"无法读取已生成首屏，请重新生成首屏后再试：{format_user_facing_error_message(exc)}")
            else:
                a_plus_first_screen_locked_hero_ready = False
        custom_prompt = (
            ai_qa_prompt
            if supports_ai_qa_image
            else a_plus_style_model_replace_prompt
            if supports_a_plus_style_model_replace
            else a_plus_first_screen_selling_points_prompt
            if supports_a_plus_first_screen_selling_points
            else main_image_a_plus_prompt
            if supports_main_image_a_plus
            else amazon_a_plus_prompt
            if supports_amazon_a_plus
            else build_background_texture_instruction(
                background_texture_presets,
                background_texture_prompt,
            )
            if supports_background_texture
            else local_retouch_prompt
            if feature.get("key") == "product_retouch_local"
            else ""
        )
        main_image_a_plus_template_layout_error = ""
        if (
            supports_main_image_a_plus
            and main_image_a_plus_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
            and main_image_a_plus_template_file is not None
        ):
            try:
                selected_main_image_a_plus_layout = get_main_image_a_plus_template_layout(
                    main_image_a_plus_template_file
                )
            except RuntimeError as exc:
                selected_main_image_a_plus_layout = None
                main_image_a_plus_template_layout_error = str(exc)
        else:
            selected_main_image_a_plus_layout = (
                selected_a_plus_layout
                if "selected_a_plus_layout" in locals()
                else get_main_image_a_plus_layout(main_image_a_plus_layout_key)
            )
        target_size = (
            selected_main_image_a_plus_layout["target_size"]
            if supports_main_image_a_plus and selected_main_image_a_plus_layout is not None
            else tuple(feature.get("target_size") or (1464, 1000))
            if supports_a_plus_style_model_replace
            else (
                get_uploaded_input_dimensions(files[0])
                if supports_a_plus_first_screen_selling_points and files
                else tuple(feature.get("target_size") or (1464, 2400))
            )
            if supports_a_plus_first_screen_selling_points
            else parse_size_text(amazon_size_text)
            if supports_amazon_a_plus
            else (resize_target_width, resize_target_height)
            if supports_image_resize
            else None
        )
        using_jimeng_for_request = (
            feature_mode == "jimeng_upscale"
            or is_jimeng_model(active_model)
        )
        if using_jimeng_for_request and len(files) > JIMENG_MAX_INPUT_IMAGES and not supports_batch_multi_upload:
            st.warning(f"Agent 最多只能上传 {JIMENG_MAX_INPUT_IMAGES} 张图片。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and main_image_a_plus_template_file is None
        ):
            st.warning("指定元素替换需要先上传 1 张完整的成品 A+ 示例图。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and not main_image_a_plus_detected_elements
        ):
            st.warning("请先点击“识别可替换元素”，确认编号后再上传对应替换图。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and not main_image_a_plus_element_replacements
        ):
            st.warning("请至少为 1 个编号上传对应的替换元素图片。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and not main_image_a_plus_element_review_confirmed
        ):
            st.warning("请先逐项校对自动填充结果，并勾选确认后再开始替换。")
        elif (
            supports_a_plus_first_screen_selling_points
            and a_plus_first_screen_workflow_stage == "hero"
            and len(files) < 1
        ):
            st.warning("请先上传 1 张首屏参考图。")
        elif (
            supports_a_plus_first_screen_selling_points
            and a_plus_first_screen_workflow_stage == "selling_points"
            and (not a_plus_first_screen_locked_hero_ready or len(files) < 2)
        ):
            st.warning(
                "已生成首屏不可用，请先重新生成首屏。"
                if not a_plus_first_screen_locked_hero_ready
                else "请至少上传 1 张主图或卖点图；已生成首屏会自动作为第 1 张参考图。"
            )
        elif len(files) < min_images and not (
            supports_a_plus_first_screen_selling_points
            and a_plus_first_screen_workflow_stage == "hero"
        ):
            st.warning(
                "请上传 1 张待转换的完整亚马逊 A+ 原图。"
                if supports_amazon_to_walmart_a_plus
                else f"当前功能至少需要上传 {min_images} 张参考图。"
            )
        elif supports_ai_qa_image and len(files) > 3:
            st.warning("AI问答生图功能最多只能上传 3 张参考图。")
        elif supports_ai_qa_image and not ai_qa_prompt.strip():
            st.warning("请输入你的文字要求。")
        elif feature.get("key") == "product_retouch_local" and not local_retouch_prompt.strip():
            st.warning("请输入要修复的区域和瑕疵。")
        elif (
            supports_background_texture
            and not background_texture_presets
            and not background_texture_prompt.strip()
        ):
            st.warning("请至少选择一种背景质感，或直接填写质感描述。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
            and main_image_a_plus_template_file is None
        ):
            st.warning(
                "指定元素替换需要先上传 1 张完整的成品 A+ 示例图。"
                if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
                else (
                    "一张测试需要先上传 1 张完整的成品 A+ 版式模板。"
                    if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST
                    else "套版替换需要先上传 1 张完整的成品 A+ 版式模板。"
                )
            )
        elif supports_main_image_a_plus and main_image_a_plus_template_layout_error:
            st.warning(main_image_a_plus_template_layout_error)
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and len(files) > MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS
        ):
            st.warning(f"指定元素替换最多支持 {MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS} 个上传元素组。")
        elif (
            supports_main_image_a_plus
            and main_image_a_plus_mode != MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            and len(files) > MAIN_IMAGE_A_PLUS_MAX_FILES
        ):
            st.warning(f"主图生A+最多只能上传 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张主图。")
        elif supports_amazon_a_plus and len(files) > MAIN_IMAGE_A_PLUS_MAX_FILES:
            st.warning(f"自由创作 PSD 最多只能上传 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张参考图。")
        elif supports_amazon_a_plus and target_size is None:
            st.warning("请选择正确的 A+ 成品规格。")
        elif supports_outpaint and (outpaint_top_px + outpaint_bottom_px + outpaint_left_px + outpaint_right_px) <= 0:
            st.warning("请至少设置一个方向的扩图像素。")
        elif supports_skin_tone_reference and skin_tone_reference_file is None:
            st.warning("请先上传 1 张肤色参考图。")
        elif supports_pupil_color_reference and pupil_color_reference_file is None:
            st.warning("请先上传 1 张瞳孔颜色参考图。")
        elif supports_eye_shape_reference and eye_shape_reference_file is None:
            st.warning("请先上传 1 张眼型参考图。")
        elif supports_side_angle_reference and side_angle_reference_file is None:
            st.warning("请先上传 1 张角度参考图。")
        else:
            extra_notes = ""
            batch_groups: list[list[Any]] = []
            display_source_groups: list[list[Any]] = []
            st.session_state.feature_results.pop(feature["key"], None)
            if feature["key"] == JIMENG_HD_FEATURE_KEY:
                extra_notes = (
                    "使用即梦智能超清专用接口把每张原图增强为 8K，细节生成程度固定为 50。"
                    "不调用生图模型，不需要提示词或高清参考图；每张原图只返回一张对应的超清结果。"
                )
            elif feature["key"] == "hd_batch":
                extra_notes = (
                    PORTRAIT_HD_SKIN_LOCK_RULES
                    + PORTRAIT_HD_COLOR_LOCK_RULES
                    + "第1张图必须作为唯一主体，不允许改变人物身份、五官比例、脸型、表情、发型和构图。"
                    "保持当前第1张原图的完整构图与宽高比，使用原生 4K 高清输出，不要缩回上传图尺寸；禁止裁剪、扩图、补边、旋转、拉伸或重新取景，原图四边内容必须全部保留。"
                    "如果存在第2张图，第2张图仍作为高清参考图，但只用于参考清晰度、分辨率和细节解析水平。"
                    "严禁从第2张图借用或迁移肤色、肤质、毛孔状态、皮肤光泽、颗粒感、斑点、妆容、脸型、五官、眼睛、表情、发型、服饰、背景、色温、色调、白平衡、曝光、对比度、光线颜色、色彩风格或人物身份。"
                    "批量时上传几张主图，就只返回几张高清结果图；每张主图只允许对应1张结果图。"
                )
            elif supports_outpaint:
                display_source_groups = [[item] for item in files]
                extra_notes = build_outpaint_extra_notes(
                    outpaint_top_px,
                    outpaint_bottom_px,
                    outpaint_left_px,
                    outpaint_right_px,
                )
            elif supports_skin_tone_reference:
                files.append(skin_tone_reference_file)
                extra_notes = (
                    "第 1 张图是主体图，必须以这张图的人物身份和画面内容为绝对主体。"
                    "第 2 张图是肤色参考图。"
                    "只参考第 2 张图中的肤色信息，包括肤色倾向、冷暖关系、深浅程度和综合色调。"
                    "除肤色之外，一概不要参考第 2 张图中的任何其他内容，包括人物身份、五官、发型、妆容、服饰、体型、姿势、背景、场景、道具、光线、色彩、构图和风格。"
                    "第 1 张主体图中的人物身份、脸部特征、五官结构、发型、妆容、服饰、肤质、毛孔、皮肤纹理、姿势、构图、机位、光线、背景和整体风格都必须严格保持不变。"
                    "仅生成 1 张结果图，不要输出多个版本。"
                )
            elif supports_ai_qa_image:
                extra_notes = (
                    f"当前共上传 {len(files)} 张参考图。"
                    "请先充分理解这些图片中的主体、构图、场景、风格、细节和视觉关系，再严格执行用户的文字要求。"
                    "如果用户要求保留原图中的人物、商品、场景或构图，需要优先保持一致。"
                    "只输出 1 张最终结果图，不要输出多个版本。"
                )
            elif supports_background_texture:
                extra_notes = (
                    "第 1 张图是唯一待处理原图。只识别并重塑场景背景的材质表面，不改变背景空间的几何布局。"
                    "前景人物、商品和所有主体内容是不可编辑区域；主体边缘必须干净完整，不能出现材质溢出、光晕、蒙版边缘或背景纹理穿透。"
                    "最终只返回 1 张完成图，不要返回对比图、材质样板、拼图或多个版本。"
                )
            elif supports_main_image_a_plus:
                if supports_a_plus_reference_lab:
                    extra_notes = build_a_plus_reference_lab_instruction(
                        a_plus_lab_resolved_style_key,
                        main_image_a_plus_layout_key,
                        product_image_count=len(files),
                        style_reference_count=0,
                        custom_prompt=main_image_a_plus_prompt,
                        auto_repair_crops=False,
                    )
                elif main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
                    extra_notes = build_main_image_a_plus_element_replacement_notes(
                        selected_main_image_a_plus_layout,
                        len(main_image_a_plus_detected_elements),
                        main_image_a_plus_element_replacements,
                    )
                elif main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST:
                    extra_notes = build_main_image_a_plus_single_test_notes(
                        selected_main_image_a_plus_layout,
                        len(files),
                    )
                elif main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE:
                    extra_notes = build_main_image_a_plus_template_notes(
                        selected_main_image_a_plus_layout,
                        len(files),
                    )
                else:
                    extra_notes = build_main_image_a_plus_layout_notes(
                        main_image_a_plus_layout_key,
                        len(files),
                    )
            elif supports_amazon_a_plus:
                target_width, target_height = target_size
                extra_notes = (
                    f"当前共上传 {len(files)} 张参考图；第1张是核心商品和品牌依据。"
                    "请自由创作一套适合电商 A+ 宣传的独立视觉元素，并按最终成品位置完成从上到下的商业排版。"
                    "整体大体形成品牌主视觉、核心卖点与细节、使用场景或工艺、包装规格与品牌收尾四个自然阅读阶段，但不要绘制四块硬边界。"
                    "如有多位模特，只选择一位放在最上方首屏，人物、商品、Logo 和全部文字必须完整且不得被画布四边截断。"
                    "每个商品、文字块、图标、徽章和装饰元素必须完整且彼此分离，不能接触、交叠或通过阴影相连。"
                    "元素之间至少保留 32px 纯 #00FF00 间距；除独立元素外，整张画布只能出现纯 #00FF00。"
                    "不要生成底板、分栏线、大面积背景、场景地面或跨元素装饰。"
                    "元素位置要体现清晰、商业化的 A+ 信息层级，但不要替换上传主体、品牌或人物身份，也不要生成无关商品或编造卖点。"
                    "必须使用原生 4K 高清细节，商品纹理、睫毛丝、眼部细节、人物五官和文字边缘必须清晰锐利。"
                    "禁止模糊、虚焦、低分辨率、涂抹、过度柔化、像素化和压缩痕迹。"
                    f"绿幕底稿画布尺寸必须严格等于 {target_width}*{target_height}px。"
                    "仅输出 1 张绿幕元素底稿，不要输出成品背景图、透明图、草图或分步骤图。"
                )
            elif supports_pupil_color_reference:
                files.append(pupil_color_reference_file)
                extra_notes = (
                    "第 1 张图是主体图，必须以这张图的人物身份和画面内容为绝对主体。"
                    "第 2 张图是瞳孔颜色参考图。"
                    "只参考第 2 张图中的瞳孔颜色信息，包括颜色倾向、明暗表现和综合色调。"
                    "除瞳孔颜色之外，一概不要参考第 2 张图中的任何其他内容，包括人物身份、五官、眼型、发型、妆容、睫毛、服饰、体型、姿势、背景、场景、道具、光线、色彩、构图和风格。"
                    "第 1 张主体图中的人物身份、脸部特征、眼型、眼神、睫毛、妆容、肤质、皮肤纹理、发型、服饰、姿势、构图、机位、光线、背景和整体风格都必须严格保持不变。"
                    "仅生成 1 张结果图，不要输出多个版本。"
                )
            elif supports_eye_shape_reference:
                files.append(eye_shape_reference_file)
                extra_notes = (
                    "第 1 张图是主体图，必须以这张图的人物身份和画面内容为绝对主体。"
                    "第 2 张图是眼型参考图。"
                    "只参考第 2 张图中的眼型信息，包括眼裂形状、眼角走向、眼睑弧度和眼部轮廓结构。"
                    "除眼型之外，一概不要参考第 2 张图中的任何其他内容，包括人物身份、五官、瞳孔颜色、发型、妆容、睫毛、服饰、体型、姿势、背景、场景、道具、光线、色彩、构图和风格。"
                    "第 1 张主体图中的人物身份、脸部特征、瞳孔颜色、眼神、睫毛、妆容、肤质、皮肤纹理、发型、服饰、姿势、构图、机位、光线、背景和整体风格都必须严格保持不变。"
                    "仅生成 1 张结果图，不要输出多个版本。"
                )
            elif supports_side_angle_reference:
                files.append(side_angle_reference_file)
                extra_notes = (
                    "第 1 张图是主体图，必须以这张图的人物身份和画面内容为绝对主体。"
                    "第 2 张图是角度参考图。"
                    "只参考第 2 张图中的拍摄角度、头部朝向、脸部转向和侧面视角关系。"
                    "除角度之外，一概不要参考第 2 张图中的任何其他内容，包括人物身份、脸部特征、发型、妆容、服饰、肤质、背景、场景、道具、光线、色彩、构图和整体风格。"
                    "第 1 张主体图中的人物身份、脸部特征、发型、妆容、服饰、肤质、背景、场景、光线、色彩、构图和整体风格都必须严格保持不变。"
                    "仅生成 1 张结果图，不要输出多个版本。"
                )
            elif supports_pose_references:
                files.extend(pose_reference_files)
                files.extend(scene_reference_files)
                pose_count = len(pose_reference_files)
                parts = [
                    "第 1 张图是主模特图，必须以这张图的人物身份为绝对主体。",
                    f"姿势参考图共 {pose_count} 张。",
                    "只参考姿势参考图中的动作、肢体姿势、头部朝向、手势、站姿或坐姿、重心方向和镜头方向。",
                    "生成结果中的姿势必须与参考图完全一致，包括头部朝向、肩颈角度、手臂位置、手势、身体转向、躯干弯曲、腿部动作、站姿或坐姿、重心方向和动作细节。",
                    "除姿势之外，一概不要参考姿势参考图中的任何其他内容，包括人物身份、五官、发型、妆容、服饰、体型、肤色、背景、场景、道具、光线、色彩、构图和风格。",
                    "主模特图中的人物身份、脸部特征、发型、妆容、服饰、场景、背景、光线、构图和整体风格都必须严格保持不变。",
                    "不允许修改背景环境，不允许替换场景。",
                    "仅生成 1 张结果图，不要输出多个版本。",
                ]
                extra_notes = "".join(parts)
            elif supports_scene_references:
                files.extend(scene_reference_files)
                scene_count = len(scene_reference_files)
                parts = [
                    "第 1 张图是主模特图，必须以这张图的人物身份为绝对主体。",
                    f"场景参考图共 {scene_count} 张。",
                    "只参考场景参考图中的背景、空间氛围、环境风格。",
                    "主模特图中的人物身份、脸部特征、发型、妆容、服饰、姿势、肢体动作、构图、机位和光线关系都必须严格保持不变。",
                    "不允许修改人物姿势，不允许改变主体人物。",
                    "仅生成 1 张结果图，不要输出多个版本。",
                ]
                extra_notes = "".join(parts)
            active_layout_skill_prompt = str(
                a_plus_layout_skill_context.get("prompt") or ""
            ).strip()
            if active_layout_skill_prompt:
                extra_notes = "\n\n".join(
                    part for part in (extra_notes.strip(), active_layout_skill_prompt) if part
                )
            feature_for_request = dict(feature)
            if supports_a_plus_first_screen_selling_points:
                feature_for_request["default_prompt"] = feature["default_prompt"]
            if supports_remove_eyelashes:
                feature_for_request["default_prompt"] = (
                    REMOVE_EYELASHES_PRESERVE_BASIC_PROMPT
                    if preserve_basic_eyelashes
                    else REMOVE_EYELASHES_REMOVE_ALL_PROMPT
                )
            if supports_main_image_a_plus:
                feature_for_request["main_image_a_plus_mode"] = main_image_a_plus_mode
                feature_for_request["main_image_a_plus_layout_key"] = main_image_a_plus_layout_key
                feature_for_request["main_image_a_plus_layout"] = selected_main_image_a_plus_layout
                if main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
                    feature_for_request["default_prompt"] = MAIN_IMAGE_A_PLUS_ELEMENT_DEFAULT_PROMPT
                elif main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST:
                    feature_for_request["default_prompt"] = MAIN_IMAGE_A_PLUS_SINGLE_TEST_DEFAULT_PROMPT
                elif main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE:
                    feature_for_request["default_prompt"] = MAIN_IMAGE_A_PLUS_TEMPLATE_DEFAULT_PROMPT
            if target_size is not None:
                feature_for_request["target_size"] = tuple(target_size)
                feature_for_request["target_size_text"] = f"{int(target_size[0])}*{int(target_size[1])}"
            if using_jimeng_for_request:
                final_prompt = build_jimeng_prompt(feature_for_request, custom_prompt, aspect_ratio, extra_notes)
            else:
                final_prompt = build_prompt(feature_for_request, custom_prompt, aspect_ratio, extra_notes)
            if (supports_a_plus_first_screen_selling_points
                    and a_plus_first_screen_workflow_stage != "hero"):
                final_prompt += (
                    "\n\n最终硬性规则：第1张底稿的所有已有元素完全不变且不受遮挡，任何补充要求不得覆盖此规则。"
                    "只在确认安全的空白区域选择性加入完整卖点，保持整张底稿尺寸、位置和已有元素。"
                    "素材必须完整不裁切、不遮挡；太大或放不下则省略，允许少放和留白，不编造或重复信息，不改变底稿任何元素。"
                )
            if supports_batch_multi_upload and not batch_groups:
                batch_groups = [[item] for item in files]
            if using_jimeng_for_request and batch_groups and any(len(group) > JIMENG_MAX_INPUT_IMAGES for group in batch_groups):
                st.warning(f"当前这组 Agent 请求中有图片数量超过 {JIMENG_MAX_INPUT_IMAGES} 张，请减少参考图数量后再试。")
                st.markdown("</div>", unsafe_allow_html=True)
                return
            if using_jimeng_for_request and not batch_groups and len(files) > JIMENG_MAX_INPUT_IMAGES:
                st.warning(f"当前这次 Agent 请求最多只能携带 {JIMENG_MAX_INPUT_IMAGES} 张图片。")
                st.markdown("</div>", unsafe_allow_html=True)
                return
            locked_outpaint_settings: dict[str, int] = {}
            if supports_outpaint and files:
                locked_source_width, locked_source_height = get_uploaded_input_dimensions(files[0])
                locked_target_width, locked_target_height = get_outpaint_target_canvas_size(
                    files[0],
                    outpaint_top_px,
                    outpaint_bottom_px,
                    outpaint_left_px,
                    outpaint_right_px,
                )
                locked_outpaint_settings = {
                    "source_width": locked_source_width,
                    "source_height": locked_source_height,
                    "target_width": locked_target_width,
                    "target_height": locked_target_height,
                    "top": outpaint_top_px,
                    "bottom": outpaint_bottom_px,
                    "left": outpaint_left_px,
                    "right": outpaint_right_px,
                }
            submit_feature_job(
                feature,
                {
                    "feature": feature_for_request,
                    "model": active_model,
                    "prompt": final_prompt,
                    "custom_prompt": custom_prompt,
                    "uploaded_files": [prepare_uploaded_input(item) for item in files] if not supports_batch_multi_upload else [],
                    "batch_groups": (
                        [
                            [prepare_uploaded_input(group_item) for group_item in group]
                            for group in batch_groups
                        ]
                        if supports_batch_multi_upload
                        else []
                    ),
                    "display_source_groups": (
                        [
                            [prepare_uploaded_input(group_item) for group_item in group]
                            for group in display_source_groups
                        ]
                        if display_source_groups
                        else []
                    ),
                    "output_mode": feature["output_mode"],
                    "max_output_images": selected_output_count,
                    "target_size": (
                        target_size
                        if (supports_a_plus_images_api or supports_image_resize) and target_size is not None
                        else None
                    ),
                    "main_image_a_plus_layout_key": (
                        main_image_a_plus_layout_key if supports_main_image_a_plus else None
                    ),
                    "main_image_a_plus_layout": (
                        selected_main_image_a_plus_layout if supports_main_image_a_plus else None
                    ),
                    "main_image_a_plus_mode": (
                        main_image_a_plus_mode if supports_main_image_a_plus else None
                    ),
                    "a_plus_first_screen_workflow_stage": (
                        a_plus_first_screen_workflow_stage
                        if supports_a_plus_first_screen_selling_points
                        else None
                    ),
                    "a_plus_first_screen_requirements": (
                        custom_prompt if supports_a_plus_first_screen_selling_points else ""
                    ),
                    "a_plus_first_screen_keep_height": (
                        int(st.session_state.get(f"first_screen_keep_height_{feature['key']}") or 0)
                        if supports_a_plus_first_screen_selling_points else 0
                    ),
                    "main_image_a_plus_template": (
                        prepare_uploaded_input(main_image_a_plus_template_file)
                        if supports_main_image_a_plus
                        and main_image_a_plus_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
                        and main_image_a_plus_template_file is not None
                        else None
                    ),
                    "main_image_a_plus_element_replacements": (
                        [dict(item) for item in main_image_a_plus_element_replacements]
                        if supports_main_image_a_plus
                        and main_image_a_plus_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
                        else []
                    ),
                    "a_plus_layout_skill_id": str(
                        a_plus_layout_skill_context.get("skill_id") or ""
                    ),
                    "a_plus_layout_skill_skeleton": (
                        prepare_uploaded_input(a_plus_layout_skill_context["skeleton"])
                        if a_plus_layout_skill_context.get("skeleton") is not None
                        else None
                    ),
                    "a_plus_reference_lab_style_key": (
                        a_plus_lab_resolved_style_key
                        if supports_a_plus_reference_lab
                        else ""
                    ),
                    "a_plus_reference_lab_reference_paths": [],
                    "a_plus_source_repair_enabled": (
                        False
                        if supports_a_plus_reference_lab
                        else True
                    ),
                    "outpaint_settings": (
                        locked_outpaint_settings
                        if supports_outpaint
                        else {}
                    ),
                    "account_name": str(st.session_state.get("auth_username") or "admin"),
                    "batch_concurrency": active_batch_concurrency,
                    "aspect_ratio": aspect_ratio,
                },
            )
            if supports_batch_multi_upload:
                effective_submit_concurrency = min(len(batch_groups) if batch_groups else len(files), active_batch_concurrency)
                st.info(
                    f"已提交 {len(files)} 张图片到后台批量处理，最多 {active_batch_concurrency} 路并发，当前实际按 {effective_submit_concurrency} 路执行，你可以先切换到其他功能。"
                )
            else:
                st.info("任务已提交到后台处理，你可以先切换到其他功能。")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
