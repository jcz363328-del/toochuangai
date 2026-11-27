"""Dedicated Xiaoha pages for specialized workbenches."""

from __future__ import annotations


def render_background_cutout_feature(
    feature,
    *,
    DEFAULT_ASPECT_RATIO,
    FEATURE_OUTPUT_COUNT_MAX,
    FEATURE_OUTPUT_COUNT_MIN,
    NANO_BANANA_MODEL,
    format_user_facing_error_message,
    prepare_uploaded_input,
    re,
    render_image_workbench_header,
    render_result_loading,
    render_result_preview,
    render_running_job_status,
    render_single_image_uploader,
    render_zoomable_image_gallery,
    st,
    submit_feature_job,
    uploaded_input_to_data_url,
) -> None:
    feature_key = str(feature.get("key") or "background_cutout")
    result = st.session_state.feature_results.get(feature_key) or {}
    job_info = st.session_state.background_jobs.get(feature_key) or {}

    st.markdown('<div class="workspace-panel">', unsafe_allow_html=True)
    render_image_workbench_header(feature, "AI 抠图转透明")
    action_dock = st.container(key="workbench_action_dock", border=True)
    left_col, right_col = st.columns([0.86, 1.14], gap="medium")
    uploaded_file = None
    with left_col:
        st.markdown('<div class="result-block-title">上传图片</div>', unsafe_allow_html=True)
        uploaded_file = render_single_image_uploader(
            "上传需要抠图的图片",
            key=f"uploader_{feature_key}",
            help_text="请上传包含睫毛托盘/包装的商品图。AI 会先抠出完整带睫毛的托盘并清理杂质背景。",
        )
        cutout_prompt = str(feature.get("default_prompt") or "").strip()
        st.caption("流程：AI 先输出只有睫毛托盘的纯绿背景图，再由代码把绿幕背景转成透明 PNG。")
        cutout_output_count = int(
            st.select_slider(
                "生成结果张数",
                options=list(range(FEATURE_OUTPUT_COUNT_MIN, FEATURE_OUTPUT_COUNT_MAX + 1)),
                value=1,
                key=f"output_count_{feature_key}",
            )
        )
        cutout_action_label = "只抠睫毛商品区域"
        if str(job_info.get("status") or "").strip().lower() in {"queued", "running"}:
            cutout_action_label += "（加入队列）"
        with action_dock:
            submitted = st.button(cutout_action_label, key=f"process_{feature_key}", type="primary", use_container_width=True)
        if submitted:
            if uploaded_file is None:
                st.warning("请先上传 1 张需要抠图的图片。")
            else:
                st.session_state.feature_results.pop(feature_key, None)
                submit_feature_job(
                    feature,
                    {
                        "feature": dict(feature),
                        "model": NANO_BANANA_MODEL,
                        "prompt": str(cutout_prompt).strip(),
                        "uploaded_files": [prepare_uploaded_input(uploaded_file)],
                        "batch_groups": [],
                        "output_mode": "image",
                        "max_output_images": cutout_output_count,
                        "account_name": str(st.session_state.get("auth_username") or "admin"),
                        "aspect_ratio": DEFAULT_ASPECT_RATIO,
                    },
                )
                st.info("已提交 AI 抠图任务，完成后会在右侧显示透明 PNG。")
                st.rerun()

    result = st.session_state.feature_results.get(feature_key) or {}
    with right_col:
        st.markdown('<div class="result-block-title">结果图预览</div>', unsafe_allow_html=True)
        if uploaded_file is not None:
            st.markdown('<div class="panel-subtitle">原图</div>', unsafe_allow_html=True)
            try:
                render_zoomable_image_gallery(
                    [uploaded_input_to_data_url(uploaded_file)],
                    columns=1,
                    thumb_height=180,
                    component_key=f"cutout_source_{feature_key}",
                    fit_mode="contain",
                    max_width_percent=62,
                    compress_preview=True,
                    include_full_src=True,
                )
            except Exception:
                st.caption("原图预览暂时无法显示。")
        if render_result_loading(feature_key):
            pass
        elif result.get("images"):
            st.markdown('<div class="panel-subtitle">AI 抠图透明 PNG 结果</div>', unsafe_allow_html=True)
            result_id = re.sub(r"[^a-zA-Z0-9_]", "_", str(result.get("result_id") or "latest"))
            render_zoomable_image_gallery(
                list(result.get("images") or []),
                columns=1,
                thumb_height=None,
                component_key=f"cutout_result_{result_id}",
                fit_mode="contain",
                max_width_percent=62,
                compress_preview=False,
                include_full_src=True,
            )
        else:
            render_result_preview([], show_title=False)
        if str(job_info.get("status") or "").strip().lower() in {"queued", "running"}:
            render_running_job_status(feature_key)
        elif job_info.get("status") == "error":
            st.error(f"后台任务失败：{format_user_facing_error_message(job_info.get('error'))}")
        elif job_info.get("status") == "completed":
            st.success("睫毛商品区域抠图任务已完成。")

    st.markdown("</div>", unsafe_allow_html=True)


def render_a_plus_hero_style_reverse_feature(
    feature,
    *,
    A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY,
    HERO_STYLE_REVERSE_FIELD_LABELS,
    HERO_STYLE_REVERSE_MAX_COUNT,
    analyze_hero_style_reverse_reference,
    build_hero_style_reverse_image_input,
    format_user_facing_error_message,
    get_uploaded_input_name,
    hero_style_reverse_nearest_aspect_ratio,
    optimize_hero_style_reverse_prompt,
    render_image_workbench_header,
    render_result_loading,
    render_result_preview,
    render_running_job_status,
    render_single_image_uploader,
    render_zoomable_image_gallery,
    save_hero_reverse_draft,
    st,
    submit_hero_reverse_job,
) -> None:
    feature_key = str(feature.get("key") or A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY)
    if "hero_style_reverse_state" not in st.session_state:
        st.session_state.hero_style_reverse_state = {}
    state = st.session_state.hero_style_reverse_state
    prompt_key = f"hero_style_reverse_prompt_{feature_key}"
    extra_key = f"hero_style_reverse_extra_{feature_key}"
    refine_key = f"hero_style_reverse_refine_{feature_key}"
    count_key = f"hero_style_reverse_count_{feature_key}"
    width_key = f"hero_style_reverse_width_{feature_key}"
    height_key = f"hero_style_reverse_height_{feature_key}"
    use_ref_key = f"hero_style_reverse_use_ref_{feature_key}"
    batch_key = f"batch_select_{feature_key}"

    draft = state.setdefault("draft", {})
    for field, widget_key in (("extra", extra_key), ("refine", refine_key),
                              ("count", count_key), ("width", width_key),
                              ("height", height_key), ("use_ref", use_ref_key)):
        if widget_key not in st.session_state and field in draft:
            st.session_state[widget_key] = draft[field]

    if prompt_key not in st.session_state:
        st.session_state[prompt_key] = str(state.get("prompt") or "")
    pending_prompt = state.pop("pending_prompt", None)
    if pending_prompt is not None:
        st.session_state[prompt_key] = str(pending_prompt)
    if state.pop("pending_refine_clear", False):
        st.session_state.pop(refine_key, None)
    if state.pop("pending_batch_reset", False):
        st.session_state.pop(batch_key, None)

    job_info = st.session_state.get("background_jobs", {}).get(feature_key) or {}
    if job_info.get("status") in {"queued", "running"}:
        render_running_job_status(feature_key)
    elif job_info.get("status") == "error":
        st.error(str(job_info.get("error") or "生成失败，请重试。"))

    st.markdown('<div class="workspace-panel">', unsafe_allow_html=True)
    render_image_workbench_header(feature, "参考图 → 风格拆解 → 提示词 → 批量创作")
    st.caption(
        "上传一张首屏风格参考图，AI 先拆解主体、构图、色彩、光影、风格与细节，反写中文生图提示词；"
        "提示词可直接修改，再批量生成同风格创意图，最后挑出最优方案做二次优化。"
    )

    action_dock = st.container(key="workbench_action_dock", border=True)
    left_col, right_col = st.columns([0.92, 1.08], gap="medium")

    with left_col:
        st.markdown('<div class="result-block-title">① 上传参考图</div>', unsafe_allow_html=True)
        reference_file = render_single_image_uploader(
            "上传首屏风格参考图",
            key=f"uploader_{feature_key}",
            help_text="支持 A+ 首屏截图、竞品海报或任意风格参考图；建议主体清晰、最长边不小于 800px。",
        )
        st.text_area(
            "补充要求（可选）",
            key=extra_key,
            on_change=save_hero_reverse_draft, args=("extra", extra_key),
            height=86,
            placeholder="例如：保留人物姿势只换背景；希望更高级、更冷色调；必须出现大理石台面。",
        )
        with action_dock:
            analyze_clicked = st.button(
                "① 逆向分析参考图",
                key=f"analyze_{feature_key}",
                type="primary",
                use_container_width=True,
            )
        if analyze_clicked:
            if reference_file is None:
                st.warning("请先上传 1 张参考图。")
            else:
                with st.spinner("AI 正在识别主体、构图、色彩、光影、风格与细节…"):
                    try:
                        analysis_result = analyze_hero_style_reverse_reference(
                            reference_file,
                            str(st.session_state.get(extra_key) or ""),
                        )
                    except Exception as exc:
                        st.error(f"参考图分析失败：{format_user_facing_error_message(exc)}")
                    else:
                        state["analysis"] = analysis_result
                        state["prompt"] = str(analysis_result.get("prompt") or "")
                        state["pending_prompt"] = state["prompt"]
                        state["source_name"] = get_uploaded_input_name(reference_file)
                        state["pending_refine_clear"] = True
                        st.rerun()

        analysis = dict(state.get("analysis") or {})
        if analysis:
            st.markdown('<div class="result-block-title">② 风格拆解</div>', unsafe_allow_html=True)
            breakdown_lines = [
                f"- **{label}**：{str(analysis.get(field_key) or '—')}"
                for field_key, label in HERO_STYLE_REVERSE_FIELD_LABELS
            ]
            st.markdown("\n".join(breakdown_lines))
        else:
            st.caption("分析完成后，这里会显示六个维度的风格拆解。")

        st.markdown('<div class="result-block-title">③ 生图提示词</div>', unsafe_allow_html=True)
        st.text_area(
            "生图提示词（可编辑）",
            key=prompt_key,
            on_change=save_hero_reverse_draft, args=("prompt", prompt_key),
            height=230,
            placeholder="分析完成后自动填入，也可以手动编写或调整。",
        )
        with action_dock:
            optimize_clicked = st.button(
                "智能优化与补充提示词",
                key=f"optimize_{feature_key}",
                use_container_width=True,
            )
        if optimize_clicked:
            current_prompt = str(st.session_state.get(prompt_key) or "").strip()
            if not current_prompt:
                st.warning("请先完成参考图分析或手动填写提示词。")
            else:
                with st.spinner("正在优化提示词…"):
                    try:
                        optimized_prompt = optimize_hero_style_reverse_prompt(
                            current_prompt,
                            analysis,
                            str(st.session_state.get(extra_key) or ""),
                        )
                    except Exception as exc:
                        st.error(f"提示词优化失败：{format_user_facing_error_message(exc)}")
                    else:
                        state["prompt"] = optimized_prompt
                        state["pending_prompt"] = optimized_prompt
                        st.rerun()

        st.markdown('<div class="result-block-title">④ 批量生成</div>', unsafe_allow_html=True)
        count_col, size_col_width, size_col_height = st.columns([1, 1, 1], gap="small")
        with count_col:
            output_count = int(
                st.select_slider(
                    "生成张数",
                    options=list(range(1, HERO_STYLE_REVERSE_MAX_COUNT + 1)),
                    value=2,
                    key=count_key,
                    on_change=save_hero_reverse_draft, args=("count", count_key),
                )
            )
        aspect_ratio = "4:3"
        with size_col_width:
            target_width = st.number_input(
                "输出宽度（px）",
                min_value=100,
                max_value=8000,
                value=1464,
                step=1,
                key=width_key,
                on_change=save_hero_reverse_draft, args=("width", width_key),
            )
        with size_col_height:
            target_height = st.number_input(
                "输出高度（px，可留空）",
                min_value=0,
                max_value=9000,
                value=None,
                step=1,
                key=height_key,
                on_change=save_hero_reverse_draft, args=("height", height_key),
                placeholder="留空则自动计算",
            )
        if target_width and target_height:
            aspect_ratio = hero_style_reverse_nearest_aspect_ratio(
                int(target_width),
                int(target_height),
            )
            st.caption(
                f"已按目标尺寸 {int(target_width)}×{int(target_height)} 自动匹配画面比例 {aspect_ratio}。"
            )
        use_reference = st.checkbox(
            "把参考图作为风格参考一起提交（更贴近原图的质感与色调）",
            value=True,
            key=use_ref_key,
            on_change=save_hero_reverse_draft, args=("use_ref", use_ref_key),
        )
        with action_dock:
            generate_clicked = st.button(
                f"② 批量生成 {output_count} 张",
                key=f"generate_{feature_key}",
                type="primary",
                use_container_width=True,
            )
        if generate_clicked:
            prompt_to_use = str(st.session_state.get(prompt_key) or "").strip()
            if not prompt_to_use:
                st.warning("请先完成参考图分析或手动填写提示词。")
            elif reference_file is None and use_reference:
                st.warning("参考图已被清空，请重新上传，或取消“把参考图作为风格参考”后再生成。")
            else:
                reference_files = [reference_file] if (use_reference and reference_file is not None) else []
                submit_hero_reverse_job(
                    feature, prompt_to_use, reference_files, output_count,
                    aspect_ratio, int(target_width or 0), int(target_height or 0),
                )
                st.rerun()

    with right_col:
        st.markdown('<div class="result-block-title">⑤ 生成结果</div>', unsafe_allow_html=True)
        batches = list(state.get("batches") or [])
        if render_result_loading(feature_key):
            pass
        elif not batches:
            render_result_preview([], show_title=False)
            st.caption("完成分析与批量生成后，这里会出现同风格结果图，可按批次回看与筛选。")
        else:
            batch_labels = [
                str(batch.get("label") or f"第 {index + 1} 批")
                for index, batch in enumerate(batches)
            ]
            batch_label = str(
                st.selectbox(
                    "查看批次",
                    batch_labels,
                    index=len(batch_labels) - 1,
                    key=batch_key,
                )
            )
            batch_index = batch_labels.index(batch_label)
            current_batch = batches[batch_index]
            batch_images = [
                str(image_url).strip()
                for image_url in (current_batch.get("images") or [])
                if str(image_url).strip()
            ]
            if batch_images:
                render_zoomable_image_gallery(
                    batch_images,
                    columns=2,
                    thumb_height=240,
                    component_key=f"hero_style_reverse_gallery_{feature_key}_{batch_index}_{len(batch_images)}",
                    fit_mode="cover",
                    include_full_src=True,
                    compress_preview=False,
                )
            else:
                render_result_preview([], show_title=False)

            st.markdown('<div class="result-block-title">⑥ 效果筛选与二次优化</div>', unsafe_allow_html=True)
            parent_label = str(current_batch.get("parent") or "").strip()
            if parent_label:
                st.caption(f"本批次基于「{parent_label}」二次优化生成。")
            if len(batch_images) > 1:
                option_labels = [f"方案 {index + 1}" for index in range(len(batch_images))]
                selected_label = str(
                    st.radio(
                        "选为最优方案",
                        option_labels,
                        horizontal=True,
                        key=f"hero_style_reverse_pick_{feature_key}_{batch_index}_{len(batch_images)}",
                    )
                )
                selected_index = option_labels.index(selected_label)
            else:
                selected_index = 0
                st.caption("本批次只有 1 张结果，已自动作为最优方案。")
            st.text_area(
                "二次优化要求",
                key=refine_key,
                on_change=save_hero_reverse_draft, args=("refine", refine_key),
                height=96,
                placeholder="例如：光影更通透、色温偏冷、背景换成大理石台面、人物表情更自然。",
            )
            with action_dock:
                refine_clicked = st.button(
                    "③ 以选中方案为基础二次优化生成",
                    key=f"refine_{feature_key}",
                    use_container_width=True,
                )
            if refine_clicked:
                refine_requirement = str(st.session_state.get(refine_key) or "").strip()
                if not refine_requirement:
                    st.warning("请先填写二次优化要求。")
                else:
                    base_prompt = str(
                        current_batch.get("prompt") or st.session_state.get(prompt_key) or ""
                    ).strip()
                    parent_image_source = batch_images[selected_index] if batch_images else ""
                    refine_reference = build_hero_style_reverse_image_input(parent_image_source)
                    if refine_reference is None:
                        refine_reference = reference_file
                    refined_prompt = (
                        f"{base_prompt}\n\n二次优化要求：{refine_requirement}\n"
                        "请以参考图中的上一版结果作为风格基底，保持主体身份、构图骨架、色调关系与整体质感一致，"
                        "只针对二次优化要求做定向调整，输出一张更成熟的同风格新方案。"
                    )
                    refine_count = int(st.session_state.get(count_key) or 2)
                    refine_ratio = str(current_batch.get("aspect_ratio") or aspect_ratio or "4:3")
                    refine_target_size = list(current_batch.get("target_size") or [target_width or 0, target_height or 0])
                    refine_target_width = int(refine_target_size[0] or 0)
                    refine_target_height = int(refine_target_size[1] or 0) if len(refine_target_size) > 1 else 0
                    submit_hero_reverse_job(
                        feature, refined_prompt,
                        [refine_reference] if refine_reference is not None else [],
                        refine_count, refine_ratio, refine_target_width, refine_target_height,
                        parent=current_batch.get("label") or "", parent_index=selected_index,
                    )
                    st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


def render_replacement_infinite_canvas_feature(
    feature,
    *,
    DEFAULT_JIMENG_STATIC_PORT,
    DEFAULT_PUBLIC_APP_URL,
    INFINITE_CANVAS_BUILD_DIR,
    build_infinite_canvas_url,
    html,
    load_runtime_settings,
    st,
) -> None:
    runtime_settings = load_runtime_settings()
    try:
        static_port = int(runtime_settings.get("jimeng_static_port") or DEFAULT_JIMENG_STATIC_PORT)
    except Exception:
        static_port = DEFAULT_JIMENG_STATIC_PORT
    canvas_url = build_infinite_canvas_url(
        str(runtime_settings.get("public_app_url") or DEFAULT_PUBLIC_APP_URL),
        static_port,
        str(st.session_state.get("auth_username") or "访客"),
        workspace="a_plus" if feature.get("key") == "a_plus_canvas" else "",
    )

    st.markdown('<div class="workspace-panel">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="feature-title">{html.escape(str(feature.get("name") or "无限画布"))}'
        '<span class="feature-badge">新版</span></div>',
        unsafe_allow_html=True,
    )
    if not (INFINITE_CANVAS_BUILD_DIR / "index.html").exists():
        st.error("新版无限画布尚未构建，请先运行小哈启动脚本完成初始化。")
    else:
        st.iframe(canvas_url, width="stretch", height=920)
    st.markdown("</div>", unsafe_allow_html=True)


def render_infinite_canvas_feature(
    feature,
    model,
    aspect_ratio,
    *,
    Any,
    INFINITE_CANVAS_MAX_INPUT_IMAGES,
    INFINITE_CANVAS_MAX_STEPS,
    NANO_BANANA_MODEL,
    OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
    OUTPAINT_DEFAULT_EXTENSION_PX,
    OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
    build_result_download_sources,
    format_user_facing_error_message,
    get_infinite_canvas_step_features,
    get_model_display_name,
    get_outpaint_default_extension,
    get_outpaint_extension_limits,
    get_skin_texture_reference_files,
    html,
    prepare_uploaded_input,
    render_history_records,
    render_multi_image_uploader,
    render_outpaint_extension_preview_card,
    render_result_loading,
    render_result_preview,
    render_result_preview_with_captions,
    render_running_job_status,
    render_single_image_uploader,
    render_zoomable_image_gallery,
    st,
    submit_feature_job,
    uploaded_input_to_data_url,
) -> None:
    result = st.session_state.feature_results.get(feature["key"]) or {}
    job_info = st.session_state.background_jobs.get(feature["key"]) or {}
    step_features = get_infinite_canvas_step_features()
    step_options = [str(item.get("key") or "") for item in step_features if item.get("key")]
    step_name_map = {str(item.get("key") or ""): str(item.get("name") or item.get("key") or "") for item in step_features}

    st.markdown('<div class="workspace-panel">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="feature-title">{feature["name"]}<span class="feature-badge">自由组合</span></div>',
        unsafe_allow_html=True,
    )
    submitted = False
    left_col, right_col = st.columns([0.78, 1.22], gap="medium")
    with left_col:
        preview_step_count = int(st.session_state.get("infinite_canvas_step_count", min(2, INFINITE_CANVAS_MAX_STEPS)) or 1)
        preview_step_count = max(1, min(INFINITE_CANVAS_MAX_STEPS, preview_step_count))
        selected_steps_for_preview: list[str] = []
        if step_options:
            for preview_index in range(preview_step_count):
                preview_state_key = f"infinite_canvas_step_{preview_index}"
                default_preview_step = step_options[min(preview_index, len(step_options) - 1)]
                selected_steps_for_preview.append(str(st.session_state.get(preview_state_key) or default_preview_step))
        preview_outpaint_index = next(
            (index for index, step_key in enumerate(selected_steps_for_preview) if step_key == "outpaint"),
            None,
        )
        preview_outpaint_prefix = (
            f"infinite_canvas_step_{preview_outpaint_index}_outpaint"
            if preview_outpaint_index is not None
            else "infinite_canvas_outpaint"
        )
        outpaint_top_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(st.session_state.get(f"{preview_outpaint_prefix}_top", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
        outpaint_bottom_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(st.session_state.get(f"{preview_outpaint_prefix}_bottom", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
        outpaint_left_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(st.session_state.get(f"{preview_outpaint_prefix}_left", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
        outpaint_right_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(st.session_state.get(f"{preview_outpaint_prefix}_right", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
        canvas_outpaint_preview_renderer = None
        if "outpaint" in selected_steps_for_preview:
            def canvas_outpaint_preview_renderer(uploaded_input: Any, item_index: int, component_key: str) -> None:
                render_outpaint_extension_preview_card(
                    uploaded_input,
                    outpaint_top_px,
                    outpaint_bottom_px,
                    outpaint_left_px,
                    outpaint_right_px,
                    f"{component_key}_canvas_outpaint_{item_index}",
                    max_preview_edge=760,
                    drag_state_keys={
                        "top": f"{preview_outpaint_prefix}_top",
                        "bottom": f"{preview_outpaint_prefix}_bottom",
                        "left": f"{preview_outpaint_prefix}_left",
                        "right": f"{preview_outpaint_prefix}_right",
                    },
                )
        st.markdown('<div class="result-block-title">上传图片</div>', unsafe_allow_html=True)
        canvas_source_files = render_multi_image_uploader(
            "上传无限画布图片",
            key="infinite_canvas_uploader",
            help_text=f"可上传 JPG / PNG / WEBP。无限画布最多使用 {INFINITE_CANVAS_MAX_INPUT_IMAGES} 张图片。",
            max_files=INFINITE_CANVAS_MAX_INPUT_IMAGES,
            preview_renderer=canvas_outpaint_preview_renderer,
            preview_slot_count=1 if canvas_outpaint_preview_renderer is not None else INFINITE_CANVAS_MAX_INPUT_IMAGES,
        )
        canvas_outpaint_limits = {
            "top": OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
            "bottom": OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
            "left": OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
            "right": OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
        }
        if canvas_source_files:
            try:
                canvas_outpaint_limits = get_outpaint_extension_limits(canvas_source_files[0])
            except Exception:
                pass
        if "outpaint" in selected_steps_for_preview:
            st.caption("紫色虚线是预计扩图后的范围，白色虚线是原图位置；四边拉满时画布宽高最大为原图的 3 倍。")

        st.markdown('<div class="panel-subtitle">组合步骤</div>', unsafe_allow_html=True)
        canvas_step_settings: list[dict[str, Any]] = []
        if not step_options:
            st.warning("还没有可组合的功能。")
            selected_steps: list[str] = []
        else:
            step_count = int(
                st.slider(
                    "步骤数量",
                    min_value=1,
                    max_value=INFINITE_CANVAS_MAX_STEPS,
                    value=min(2, INFINITE_CANVAS_MAX_STEPS),
                    step=1,
                    key="infinite_canvas_step_count",
                )
            )
            selected_steps = []
            for step_index in range(step_count):
                state_key = f"infinite_canvas_step_{step_index}"
                if state_key not in st.session_state:
                    st.session_state[state_key] = step_options[min(step_index, len(step_options) - 1)]
                selected_key = st.selectbox(
                    f"第 {step_index + 1} 步",
                    step_options,
                    key=state_key,
                    format_func=lambda value: step_name_map.get(str(value), str(value)),
                )
                selected_steps.append(str(selected_key))
                step_setting: dict[str, Any] = {}
                if selected_key == "outpaint":
                    st.markdown(f'<div class="panel-subtitle">第 {step_index + 1} 步设置：扩图参数</div>', unsafe_allow_html=True)
                    vertical_limit = max(int(canvas_outpaint_limits["top"]), 1)
                    horizontal_limit = max(int(canvas_outpaint_limits["left"]), 1)
                    top_state_key = f"infinite_canvas_step_{step_index}_outpaint_top"
                    bottom_state_key = f"infinite_canvas_step_{step_index}_outpaint_bottom"
                    left_state_key = f"infinite_canvas_step_{step_index}_outpaint_left"
                    right_state_key = f"infinite_canvas_step_{step_index}_outpaint_right"
                    for state_key, direction_limit in (
                        (top_state_key, vertical_limit),
                        (bottom_state_key, vertical_limit),
                        (left_state_key, horizontal_limit),
                        (right_state_key, horizontal_limit),
                    ):
                        if state_key in st.session_state:
                            st.session_state[state_key] = max(
                                0,
                                min(direction_limit, int(st.session_state[state_key] or 0)),
                            )
                    step_top_col, step_bottom_col = st.columns(2, gap="small")
                    with step_top_col:
                        step_top_px = int(
                            st.slider(
                                "上方扩展像素",
                                0,
                                vertical_limit,
                                get_outpaint_default_extension(vertical_limit),
                                50 if vertical_limit >= 50 else 1,
                                key=top_state_key,
                            )
                        )
                    with step_bottom_col:
                        step_bottom_px = int(
                            st.slider(
                                "下方扩展像素",
                                0,
                                vertical_limit,
                                get_outpaint_default_extension(vertical_limit),
                                50 if vertical_limit >= 50 else 1,
                                key=bottom_state_key,
                            )
                        )
                    step_left_col, step_right_col = st.columns(2, gap="small")
                    with step_left_col:
                        step_left_px = int(
                            st.slider(
                                "左侧扩展像素",
                                0,
                                horizontal_limit,
                                get_outpaint_default_extension(horizontal_limit),
                                50 if horizontal_limit >= 50 else 1,
                                key=left_state_key,
                            )
                        )
                    with step_right_col:
                        step_right_px = int(
                            st.slider(
                                "右侧扩展像素",
                                0,
                                horizontal_limit,
                                get_outpaint_default_extension(horizontal_limit),
                                50 if horizontal_limit >= 50 else 1,
                                key=right_state_key,
                            )
                        )
                    step_setting["outpaint"] = {
                        "top": step_top_px,
                        "bottom": step_bottom_px,
                        "left": step_left_px,
                        "right": step_right_px,
                    }
                canvas_step_settings.append(step_setting)

        first_outpaint_settings = next(
            (dict(step_setting.get("outpaint") or {}) for step_setting in canvas_step_settings if step_setting.get("outpaint")),
            {},
        )
        outpaint_top_px = int(first_outpaint_settings.get("top", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)
        outpaint_bottom_px = int(first_outpaint_settings.get("bottom", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)
        outpaint_left_px = int(first_outpaint_settings.get("left", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)
        outpaint_right_px = int(first_outpaint_settings.get("right", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)
        if False and "outpaint" in selected_steps:
            st.markdown('<div class="panel-subtitle">扩图参数</div>', unsafe_allow_html=True)
            top_col, bottom_col = st.columns(2, gap="small")
            with top_col:
                outpaint_top_px = int(
                    st.slider("上方扩展像素", 0, OUTPAINT_FALLBACK_MAX_EXTENSION_PX, OUTPAINT_DEFAULT_EXTENSION_PX, 50, key="infinite_canvas_outpaint_top")
                )
            with bottom_col:
                outpaint_bottom_px = int(
                    st.slider("下方扩展像素", 0, OUTPAINT_FALLBACK_MAX_EXTENSION_PX, OUTPAINT_DEFAULT_EXTENSION_PX, 50, key="infinite_canvas_outpaint_bottom")
                )
            left_px_col, right_px_col = st.columns(2, gap="small")
            with left_px_col:
                outpaint_left_px = int(
                    st.slider("左侧扩展像素", 0, OUTPAINT_FALLBACK_MAX_EXTENSION_PX, OUTPAINT_DEFAULT_EXTENSION_PX, 50, key="infinite_canvas_outpaint_left")
                )
            with right_px_col:
                outpaint_right_px = int(
                    st.slider("右侧扩展像素", 0, OUTPAINT_FALLBACK_MAX_EXTENSION_PX, OUTPAINT_DEFAULT_EXTENSION_PX, 50, key="infinite_canvas_outpaint_right")
                )

        hd_reference_file = None
        if False and "hd_batch" in selected_steps:
            st.markdown('<div class="panel-subtitle">高清参考图（可选）</div>', unsafe_allow_html=True)
            ref_upload_col, ref_gallery_col = st.columns([1, 1], gap="small")
            with ref_upload_col:
                hd_reference_upload = render_single_image_uploader(
                    "上传高清参考图",
                    key="infinite_canvas_hd_reference",
                    help_text="用于高清步骤的皮肤质感或细节参考；不选择时使用默认参考。",
                )
            hd_reference_file = hd_reference_upload
            with ref_gallery_col:
                skin_texture_reference_files = get_skin_texture_reference_files()
                if skin_texture_reference_files:
                    selected_reference_name = st.radio(
                        "选择高清参考图库",
                        options=["不使用图库参考图", *[path.name for path in skin_texture_reference_files]],
                        index=0,
                        key="infinite_canvas_hd_reference_gallery",
                        label_visibility="collapsed",
                    )
                    if selected_reference_name != "不使用图库参考图":
                        hd_reference_file = next(
                            (path for path in skin_texture_reference_files if path.name == selected_reference_name),
                            hd_reference_file,
                        )
                        st.caption(f"当前使用图库参考图：{selected_reference_name}")
                else:
                    st.caption("暂无可选参考图库，可直接上传参考图。")

        st.markdown('<div class="panel-subtitle">补充要求</div>', unsafe_allow_html=True)
        custom_prompt = st.text_area(
            "无限画布补充要求",
            key="infinite_canvas_prompt",
            placeholder="例如：整体保持真实商业修图质感，人物身份和五官不要变化。",
            height=96,
            label_visibility="collapsed",
        )

        selector_col, process_col = st.columns([1.15, 0.95], gap="small")
        with selector_col:
            active_model = st.selectbox(
                "模型切换",
                [NANO_BANANA_MODEL],
                index=0,
                format_func=get_model_display_name,
                key="model_select_infinite_canvas",
            )
        with process_col:
            st.markdown('<div class="panel-subtitle">&nbsp;</div>', unsafe_allow_html=True)
            infinite_canvas_action_label = "开始组合处理"
            if str(job_info.get("status") or "").strip().lower() in {"queued", "running"}:
                infinite_canvas_action_label += "（加入队列）"
            submitted = st.button(
                infinite_canvas_action_label,
                key="process_infinite_canvas",
                type="secondary",
                use_container_width=True,
            )

    with right_col:
        st.markdown('<div class="canvas-right-column-marker"></div>', unsafe_allow_html=True)
        st.markdown('<div class="result-block-title">右侧预览</div>', unsafe_allow_html=True)
        if selected_steps:
            flow_chips = "".join(
                f'<span class="canvas-flow-chip">{html.escape(step_name_map.get(step_key, step_key))}</span>'
                for step_key in selected_steps
            )
            st.markdown(f'<div class="canvas-flow-summary">{flow_chips}</div>', unsafe_allow_html=True)
        result_images = list(result.get("images") or [])
        result_captions = list(result.get("captions") or [])
        result_download_images = build_result_download_sources(
            result_images,
            list(result.get("history_records") or []),
        )
        if render_result_loading(feature["key"]):
            pass
        elif result_images and result_captions:
            render_result_preview_with_captions(
                result_images,
                result_captions,
                feature["key"],
                download_images=result_download_images,
            )
        elif result_images:
            render_result_preview(
                result_images,
                show_title=False,
                download_images=result_download_images,
            )
        elif canvas_source_files:
            st.markdown('<div class="panel-subtitle">输入图预览</div>', unsafe_allow_html=True)
            preview_file = canvas_source_files[0]
            if "outpaint" in selected_steps:
                render_outpaint_extension_preview_card(
                    preview_file,
                    outpaint_top_px,
                    outpaint_bottom_px,
                    outpaint_left_px,
                    outpaint_right_px,
                    "infinite_canvas_right_preview",
                    max_preview_edge=520,
                )
                st.caption("紫色虚线是预计扩图后的范围，白色虚线是原图位置。")
            else:
                render_zoomable_image_gallery(
                    [uploaded_input_to_data_url(preview_file)],
                    columns=1,
                    thumb_height=520,
                    component_key="infinite_canvas_right_input_preview",
                    fit_mode="contain",
                    max_width_percent=88,
                    compress_preview=True,
                    include_full_src=True,
                )
            st.caption("处理完成后，这里会自动切换成最终结果图。")
        else:
            render_result_preview(result_images, show_title=False)

    if str(job_info.get("status") or "").strip().lower() in {"queued", "running"}:
        render_running_job_status(feature["key"])
    elif job_info.get("status") == "error":
        st.error(f"后台任务失败：{format_user_facing_error_message(job_info.get('error'))}")
    elif job_info.get("status") == "completed":
        st.success("无限画布处理完成，可以继续换组合或查看历史。")
        result_text = str(result.get("text") or "").strip()
        if result_text:
            st.info(result_text)
        storage_error = str(result.get("storage_error") or "").strip()
        if storage_error:
            st.warning(storage_error)

    if submitted:
        a_plus_first_screen_locked_hero_ready = True
        if not canvas_source_files:
            st.warning("请先上传至少 1 张图片。")
        elif not selected_steps:
            st.warning("请至少选择 1 个组合步骤。")
        elif "outpaint" in selected_steps and (outpaint_top_px + outpaint_bottom_px + outpaint_left_px + outpaint_right_px) <= 0:
            st.warning("扩图步骤至少需要一个方向大于 0。")
        else:
            st.session_state.feature_results.pop(feature["key"], None)
            step_names = [step_name_map.get(step_key, step_key) for step_key in selected_steps]
            flow_text = " → ".join(step_names)
            final_prompt = f"无限画布组合流程：{flow_text}"
            if custom_prompt.strip():
                final_prompt += f"\n\n补充要求：{custom_prompt.strip()}"
            submit_feature_job(
                feature,
                {
                    "feature": dict(feature),
                    "model": active_model,
                    "prompt": final_prompt,
                    "custom_prompt": custom_prompt,
                    "uploaded_files": [prepare_uploaded_input(item) for item in canvas_source_files],
                    "canvas_steps": selected_steps,
                    "canvas_step_settings": canvas_step_settings,
                    "canvas_outpaint": {
                        "top": outpaint_top_px,
                        "bottom": outpaint_bottom_px,
                        "left": outpaint_left_px,
                        "right": outpaint_right_px,
                    },
                    "canvas_hd_reference": prepare_uploaded_input(hd_reference_file) if hd_reference_file is not None else None,
                    "batch_groups": [],
                    "output_mode": feature["output_mode"],
                    "max_output_images": 0,
                    "account_name": str(st.session_state.get("auth_username") or "admin"),
                    "aspect_ratio": aspect_ratio,
                },
            )
            st.info("无限画布任务已提交到后台，完成后会自动显示在右侧。")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    render_history_records(feature)


def render_prepress_check_feature(
    feature,
    *,
    datetime,
    prepress_check_service,
    render_frame_uploader,
    st,
    uuid4,
) -> None:
    st.markdown('<div class="workspace-panel">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="feature-title">{feature["name"]}<span class="feature-badge">设计质检</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="feature-desc">{feature["summary"]}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="meta-row">'
        '<span class="meta-pill">AI / PDF / ZIP / 截图</span>'
        '<span class="meta-pill">19 项逐项检查</span>'
        '<span class="meta-pill">自动证据与修改建议</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="workflow-strip">'
        '<div class="workflow-step"><span class="workflow-step-number">1</span><span>上传文件包</span></div>'
        '<div class="workflow-step"><span class="workflow-step-number">2</span><span>自动解析</span></div>'
        '<div class="workflow-step"><span class="workflow-step-number">3</span><span>查看报告</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.info("建议一次上传完整的转曲 AI、PDF 和截图；也可以直接上传包含这些文件的 ZIP。")
    uploaded_files = render_frame_uploader(
        "上传印前源文件",
        type=["ai", "pdf", "zip", "png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"],
        accept_multiple_files=True,
        key="prepress_check_uploads",
        help="单个文件不超过 200MB；ZIP 解压后不超过 500MB。",
    )
    material_type = st.selectbox(
        "物料类型",
        options=["自动识别 / 其他", "包装盒", "底卡", "信息贴"],
        key="prepress_material_type",
    )
    with st.container(key="workbench_action_dock", border=True):
        run_clicked = st.button(
            "开始印前检查",
            type="primary",
            use_container_width=True,
            disabled=not bool(uploaded_files),
            key="run_prepress_check",
        )
    if run_clicked:
        session_key = f"web-{uuid4().hex}"
        try:
            with st.spinner("正在解析 AI/PDF 并生成逐项报告，请稍候…"):
                for uploaded in uploaded_files or []:
                    prepress_check_service.stage_file(
                        session_key,
                        uploaded.getvalue(),
                        str(uploaded.name or "upload"),
                    )
                result = prepress_check_service.run_check(session_key)
                report = str(result.get("report") or "")
                if material_type != "自动识别 / 其他":
                    report = report.replace(
                        "# 印前检查报告",
                        f"# 印前检查报告\n\n物料类型：{material_type}",
                        1,
                    )
                st.session_state.prepress_check_report = report
                st.session_state.prepress_check_summary = {
                    "sources": int(result.get("scan_count") or 0),
                    "screenshots": int(result.get("image_count") or 0),
                }
            st.success("印前检查完成。")
        except Exception as exc:
            prepress_check_service.reset_session(session_key)
            st.error(f"印前检查失败：{exc}")
    report = str(st.session_state.get("prepress_check_report") or "").strip()
    if report:
        summary = st.session_state.get("prepress_check_summary") or {}
        st.caption(
            f"已解析 {int(summary.get('sources') or 0)} 个 AI/PDF 文件，"
            f"收集 {int(summary.get('screenshots') or 0)} 张截图。"
        )
        st.markdown(report)
        st.download_button(
            "下载 Markdown 报告",
            data=report.encode("utf-8"),
            file_name=f"印前检查报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            use_container_width=True,
            key="download_prepress_report",
        )
    st.markdown("</div>", unsafe_allow_html=True)
