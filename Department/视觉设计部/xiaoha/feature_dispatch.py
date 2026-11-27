"""Dispatch image feature jobs, admit queued work and persist results."""

from __future__ import annotations

from typing import Any


def finalize_feature_job_result(
    job_context,
    result,
    job_id,
    *,
    Path,
    build_local_history_records,
    ensure_feature_output_dir,
    save_generated_images_and_record_db,
    set_task_progress,
    sys,
) -> dict[str, Any]:
    if bool(job_context.get("_defer_feature_finalize")):
        return result
    if job_id:
        set_task_progress(job_id, 88, "正在整理结果并返回页面")
    account_name = str(job_context.get("account_name") or "admin")
    fallback_history_records = build_local_history_records(
        feature=dict(job_context["feature"]),
        model=str(job_context.get("model") or ""),
        prompt=str(job_context.get("prompt") or ""),
        result=result,
        account_name=account_name,
    )
    result_text_parts = [str(result.get("text") or "").strip()]
    history_records = fallback_history_records
    psd_bytes = result.get("psd_bytes")
    if isinstance(psd_bytes, (bytes, bytearray)) and psd_bytes:
        try:
            artifact_dir = ensure_feature_output_dir(
                str((job_context.get("feature") or {}).get("key") or "amazon_a_plus")
            )
            psd_file_name = Path(str(result.get("psd_file_name") or "amazon_a_plus.psd")).name
            if not psd_file_name.lower().endswith(".psd"):
                psd_file_name += ".psd"
            psd_path = artifact_dir / psd_file_name
            psd_path.write_bytes(bytes(psd_bytes))
            result["psd_path"] = str(psd_path)
            result.pop("psd_storage_error", None)
            result_text_parts.append("分层 PSD 已保存到服务器。")
        except Exception as exc:
            psd_storage_error = f"分层 PSD 保存到服务器失败：{exc}"
            result["psd_storage_error"] = psd_storage_error
            print(f"[psd-save] {psd_storage_error}", file=sys.stderr)
            result_text_parts.append("分层 PSD 已生成并可下载，但保存到服务器失败。")
    if result.get("images"):
        try:
            history_records = save_generated_images_and_record_db(
                feature=dict(job_context["feature"]),
                model=str(job_context.get("model") or ""),
                prompt=str(job_context.get("prompt") or ""),
                result=result,
                account_name=account_name,
            )
            result_text_parts.append("结果已保存到服务器和数据库。")
            result["storage_pending"] = False
            result.pop("storage_error", None)
        except Exception as exc:
            storage_error = f"保存生成结果失败：{exc}"
            print(f"[history-save] {storage_error}", file=sys.stderr)
            result["storage_pending"] = False
            result["storage_error"] = storage_error
            result_text_parts.append("结果已返回页面，但保存到服务器和数据库失败。")
    result["text"] = "\n\n".join(part for part in result_text_parts if part).strip()
    result["history_records"] = history_records
    result["history_account_name"] = account_name
    if job_id:
        set_task_progress(job_id, 100, "处理完成")
    return result


def run_feature_job(
    job_context,
    *,
    AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY,
    Any,
    _run_feature_job_once,
    finalize_canvas_job_result,
    finalize_feature_job_result,
    math,
    merge_feature_variant_results,
    normalize_feature_output_count,
    record_background_job_error,
    set_task_progress,
) -> dict[str, Any]:
    feature = dict(job_context.get("feature") or {})
    feature_key = str(feature.get("key") or "")
    output_mode = str(job_context.get("output_mode") or feature.get("output_mode") or "")
    requested_output_count = normalize_feature_output_count(
        job_context.get("max_output_images"),
        default=int(feature.get("max_output_images") or 1),
    )
    is_internal_a_plus_action = bool(
        job_context.get("main_image_a_plus_text_edit")
        or job_context.get("main_image_a_plus_adapt_mobile")
    )
    if (
        output_mode != "image"
        or requested_output_count <= 1
        or is_internal_a_plus_action
        or feature_key == AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY
    ):
        return _run_feature_job_once(job_context)

    job_id = str(job_context.get("job_id") or "")
    variant_results: list[dict[str, Any]] = []
    variant_errors: list[tuple[int, Exception]] = []
    original_prompt = str(job_context.get("prompt") or "")
    for variant_index in range(1, requested_output_count + 1):
        if job_id:
            progress = 5 + math.floor(((variant_index - 1) / requested_output_count) * 80)
            set_task_progress(
                job_id,
                progress,
                f"正在生成候选 {variant_index}/{requested_output_count}",
            )
        variant_context = dict(job_context)
        variant_context["max_output_images"] = 1
        variant_context["_defer_feature_finalize"] = True
        variant_context["prompt"] = (
            original_prompt
            + "\n\n"
            + f"本次只生成第 {variant_index}/{requested_output_count} 个独立候选。"
            + "只返回 1 张完整成品；保持全部硬性约束不变，并让本候选在允许变化的构图、细节或视觉表达上具有独立性。"
            + "候选编号只用于后台调度，禁止把编号、候选字样或任何调度说明画进成品。"
        )
        try:
            variant_results.append(_run_feature_job_once(variant_context))
        except Exception as exc:
            variant_errors.append((variant_index, exc))
            record_background_job_error(
                job_id,
                feature_key,
                f"候选 {variant_index}/{requested_output_count} 生成失败",
                exc,
            )

    merged_result = merge_feature_variant_results(
        variant_results,
        variant_errors,
        requested_output_count,
    )
    if feature_key == "infinite_canvas":
        return finalize_canvas_job_result(job_context, merged_result, job_id)
    return finalize_feature_job_result(job_context, merged_result, job_id)


def _run_feature_job_once(
    job_context,
    *,
    AMAZON_A_PLUS_FEATURE_KEY,
    AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
    AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY,
    A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY,
    A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY,
    A_PLUS_IMAGES_API_FEATURE_KEYS,
    Any,
    DEFAULT_ASPECT_RATIO,
    DEFAULT_BATCH_API_CONCURRENCY,
    HD_BATCH_MAX_API_CONCURRENCY,
    IMAGE_SMART_ANALYSIS_FEATURE_KEY,
    JIMENG_HD_API_RESOLUTION,
    JIMENG_HD_FEATURE_KEY,
    JIMENG_HD_UPSCALE_REQ_KEY,
    JIMENG_MAX_API_CONCURRENCY,
    MAIN_IMAGE_A_PLUS_FEATURE_KEYS,
    MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS,
    MAIN_IMAGE_A_PLUS_MAX_FILES,
    MAIN_IMAGE_A_PLUS_MODE_ELEMENT,
    MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST,
    MAIN_IMAGE_A_PLUS_TEMPLATE_MODES,
    MAX_BATCH_API_CONCURRENCY,
    MULTI_REFERENCE_COMPOSER_FEATURE_KEY,
    REMOVE_EYELASHES_MAX_API_CONCURRENCY,
    ThreadPoolExecutor,
    as_completed,
    build_amazon_a_plus_layered_result,
    build_image_smart_analysis_model_prompt,
    build_image_smart_analysis_result,
    call_jimeng_hd_upscale,
    call_jimeng_v40,
    call_openrouter,
    call_openrouter_images_api,
    call_portrait_hd_upscale,
    capture_runtime,
    copy_context,
    extract_image_smart_palette,
    finalize_canvas_job_result,
    finalize_feature_job_result,
    get_feature_min_output_edge,
    get_main_image_a_plus_layout,
    get_main_image_a_plus_template_layout,
    is_jimeng_model,
    math,
    normalize_main_image_a_plus_mode,
    prepare_uploaded_input,
    preserve_first_screen_pixels,
    process_batch_group,
    resize_image_to_exact_size,
    resize_uploaded_image_locally,
    run_ai_background_cutout_job,
    run_amazon_to_walmart_a_plus_job,
    run_first_screen_selling_points_job,
    run_hero_reverse_job,
    run_infinite_canvas_job,
    run_main_image_a_plus_job,
    run_main_image_a_plus_mobile_adaptation_job,
    run_main_image_a_plus_text_edit_job,
    select_closest_aspect_ratio,
    set_task_progress,
    should_enhance_output_detail,
    uploaded_input_to_data_url,
    upscale_image_to_min_edge,
) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    if job_id:
        set_task_progress(job_id, 5, "准备上传图片")
    feature_key = str((job_context.get("feature") or {}).get("key") or "")
    if feature_key == "poster_fusion":
        from Department.视觉设计部.xiaoha.poster_fusion import run_job
        return finalize_feature_job_result(job_context, run_job(capture_runtime(), job_context), job_id)
    if feature_key == MULTI_REFERENCE_COMPOSER_FEATURE_KEY:
        from Department.视觉设计部.xiaoha.multi_reference_composer import run_job
        result = run_job(capture_runtime(), job_context)
        if job_context.get("composer_action") == "analyze":
            return result
        return finalize_feature_job_result(job_context, result, job_id)
    if feature_key == A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY:
        return finalize_feature_job_result(job_context, run_hero_reverse_job(job_context), job_id)
    if feature_key == A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY:
        result = run_first_screen_selling_points_job(job_context)
        return finalize_feature_job_result(job_context, result, job_id)
    if feature_key == AMAZON_TO_WALMART_A_PLUS_FEATURE_KEY:
        result = run_amazon_to_walmart_a_plus_job(job_context)
        return finalize_feature_job_result(job_context, result, job_id)
    if feature_key == "image_resize":
        uploaded_files = list(job_context.get("uploaded_files") or [])
        target_size = tuple(job_context.get("target_size") or ())
        if not uploaded_files:
            raise RuntimeError("请先上传 1 张图片。")
        if len(target_size) != 2:
            raise RuntimeError("请填写有效的目标宽度和高度。")
        if job_id:
            set_task_progress(job_id, 45, "正在调整图片尺寸")
        image_url = resize_uploaded_image_locally(
            uploaded_files[0],
            int(target_size[0]),
            int(target_size[1]),
        )
        result = {
            "images": [image_url],
            "source_images": [uploaded_input_to_data_url(uploaded_files[0])],
            "target_size": [int(target_size[0]), int(target_size[1])],
            "text": f"已输出 {int(target_size[0])} × {int(target_size[1])} px PNG。",
            "channel": "本机高质量缩放",
        }
        return finalize_feature_job_result(job_context, result, job_id)
    if feature_key in MAIN_IMAGE_A_PLUS_FEATURE_KEYS:
        if bool(job_context.get("main_image_a_plus_text_edit")):
            result = run_main_image_a_plus_text_edit_job(job_context)
            return finalize_feature_job_result(job_context, result, job_id)
        if bool(job_context.get("main_image_a_plus_adapt_mobile")):
            result = run_main_image_a_plus_mobile_adaptation_job(job_context)
            return finalize_feature_job_result(job_context, result, job_id)
        uploaded_files = list(job_context.get("uploaded_files") or [])
        feature = dict(job_context.get("feature") or {})
        generation_mode = normalize_main_image_a_plus_mode(
            str(
                job_context.get("main_image_a_plus_mode")
                or feature.get("main_image_a_plus_mode")
                or ""
            )
        )
        if not uploaded_files:
            raise RuntimeError(f"{str(feature.get('name') or 'A+生成')}至少需要上传 1 张内容参考图。")
        reference_limit = (
            MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT
            else max(int(feature.get("max_input_images") or MAIN_IMAGE_A_PLUS_MAX_FILES), 1)
        )
        if len(uploaded_files) > reference_limit:
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
                raise RuntimeError(f"指定元素替换最多支持 {reference_limit} 个上传元素组。")
            raise RuntimeError(f"{str(feature.get('name') or 'A+生成')}最多只能上传 {reference_limit} 张主图。")
        if (
            generation_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
            and job_context.get("main_image_a_plus_template") is None
        ):
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
                raise RuntimeError("指定元素替换需要先上传并识别 1 张完整的成品 A+ 示例图。")
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST:
                raise RuntimeError("一张测试需要先上传 1 张完整的成品 A+ 版式模板。")
            raise RuntimeError("套版替换需要先上传 1 张成品 A+ 模板。")
        layout = (
            get_main_image_a_plus_template_layout(job_context.get("main_image_a_plus_template"))
            if generation_mode in MAIN_IMAGE_A_PLUS_TEMPLATE_MODES
            else get_main_image_a_plus_layout(
                str(
                    job_context.get("main_image_a_plus_layout_key")
                    or feature.get("main_image_a_plus_layout_key")
                    or ""
                )
            )
        )
        job_context = dict(job_context)
        job_context["main_image_a_plus_mode"] = generation_mode
        job_context["main_image_a_plus_layout"] = layout
        job_context["main_image_a_plus_layout_key"] = layout["key"]
        job_context["target_size"] = layout["target_size"]
        job_context["section_heights"] = layout["section_heights"]
        result = run_main_image_a_plus_job(job_context)
        return finalize_feature_job_result(job_context, result, job_id)
    if feature_key == "infinite_canvas":
        result = run_infinite_canvas_job(job_context)
        return finalize_canvas_job_result(job_context, result, job_id)
    if feature_key == AMAZON_A_PLUS_FEATURE_KEY:
        uploaded_files = list(job_context.get("uploaded_files") or [])
        if not uploaded_files:
            raise RuntimeError("自由创作 PSD 至少需要上传 1 张参考图。")
        if len(uploaded_files) > MAIN_IMAGE_A_PLUS_MAX_FILES:
            raise RuntimeError(f"自由创作 PSD 最多只能上传 {MAIN_IMAGE_A_PLUS_MAX_FILES} 张参考图。")
        if job_context.get("target_size") is None:
            raise RuntimeError("自由创作 PSD 需要选择有效的 A+ 成品规格。")
    feature_mode = str((job_context.get("feature") or {}).get("mode") or "openrouter")
    if feature_mode == "ai_cutout":
        result = run_ai_background_cutout_job(job_context)
        return finalize_feature_job_result(job_context, result, job_id)
    batch_groups = list(job_context.get("batch_groups") or [])
    if batch_groups:
        display_source_groups = list(job_context.get("display_source_groups") or [])
        merged_images: list[str] = []
        merged_source_images: list[str] = []
        merged_texts: list[str] = []
        merged_captions: list[str] = []
        merged_outpaint_alignments: list[dict[str, int]] = []
        total_groups = max(len(batch_groups), 1)
        requested_batch_concurrency = max(
            1,
            min(int(job_context.get("batch_concurrency") or DEFAULT_BATCH_API_CONCURRENCY), MAX_BATCH_API_CONCURRENCY),
        )
        if is_jimeng_model(str(job_context.get("model") or "")):
            requested_batch_concurrency = min(requested_batch_concurrency, JIMENG_MAX_API_CONCURRENCY)
        if feature_key == "remove_eyelashes":
            requested_batch_concurrency = min(
                requested_batch_concurrency,
                REMOVE_EYELASHES_MAX_API_CONCURRENCY,
            )
        if feature_key == "hd_batch":
            requested_batch_concurrency = min(
                requested_batch_concurrency,
                HD_BATCH_MAX_API_CONCURRENCY,
            )
        effective_batch_concurrency = min(requested_batch_concurrency, total_groups)
        completed_results: dict[int, dict[str, Any]] = {}
        if effective_batch_concurrency <= 1 or total_groups <= 1:
            for group_index, uploaded_group in enumerate(batch_groups, start=1):
                if job_id:
                    progress_start = 8 + math.floor(((group_index - 1) / total_groups) * 58)
                    set_task_progress(
                        job_id,
                        progress_start,
                        f"正在生成第 {group_index}/{total_groups} 张，实际并发 {effective_batch_concurrency} 路",
                    )
                completed_results[group_index] = process_batch_group(job_context, uploaded_group, group_index)
                if job_id:
                    progress_post = 18 + math.floor((group_index / total_groups) * 60)
                    set_task_progress(job_id, progress_post, f"正在整理第 {group_index}/{total_groups} 张结果")
        else:
            if job_id:
                set_task_progress(
                    job_id,
                    8,
                    f"正在并发生成，共 {total_groups} 张，实际并发 {effective_batch_concurrency} 路",
                )
            completed_count = 0
            with ThreadPoolExecutor(max_workers=effective_batch_concurrency) as batch_executor:
                future_map = {
                    batch_executor.submit(copy_context().run, process_batch_group, job_context, uploaded_group, group_index): group_index
                    for group_index, uploaded_group in enumerate(batch_groups, start=1)
                }
                for future in as_completed(future_map):
                    group_index = future_map[future]
                    completed_results[group_index] = future.result()
                    completed_count += 1
                    if job_id:
                        progress_post = 18 + math.floor((completed_count / total_groups) * 60)
                        set_task_progress(
                            job_id,
                            progress_post,
                            f"已完成 {completed_count}/{total_groups} 张，实际并发 {effective_batch_concurrency} 路",
                        )
        for group_index in range(1, total_groups + 1):
            group_result = completed_results[group_index]
            batch_images = list(group_result.get("images") or [])
            merged_images.extend(batch_images)
            group_alignment = dict(group_result.get("outpaint_alignment") or {})
            merged_outpaint_alignments.extend([group_alignment] * len(batch_images))
            if batch_images:
                uploaded_group = (
                    display_source_groups[group_index - 1]
                    if group_index - 1 < len(display_source_groups)
                    else batch_groups[group_index - 1] if group_index - 1 < len(batch_groups) else []
                )
                source_image = ""
                if uploaded_group:
                    try:
                        source_image = uploaded_input_to_data_url(uploaded_group[0])
                    except Exception:
                        source_image = ""
                merged_source_images.extend([source_image] * len(batch_images))
                base_caption = str(group_result.get("source_name") or "").strip() or f"原图 {group_index}"
                if len(batch_images) == 1:
                    merged_captions.append(base_caption)
                else:
                    merged_captions.extend([f"{base_caption} - 结果 {index + 1}" for index in range(len(batch_images))])
            batch_text = str(group_result.get("text") or "").strip()
            if batch_text:
                merged_texts.append(batch_text)
        if not merged_images and job_context["output_mode"] == "image":
            backend_name = "Agent" if is_jimeng_model(str(job_context.get("model") or "")) else "OpenRouter"
            raise RuntimeError(f"{backend_name} 未返回图片：请求已提交，但响应中没有可用的结果图片。")
        result = {
            "images": merged_images,
            "source_images": merged_source_images,
            "text": "\n\n".join(merged_texts).strip(),
            "captions": merged_captions,
            "outpaint_alignments": merged_outpaint_alignments,
        }
        if str((job_context.get("feature") or {}).get("key") or "") == JIMENG_HD_FEATURE_KEY:
            result["channel"] = "即梦智能超清 · 原生 8K"
            result["resolution"] = JIMENG_HD_API_RESOLUTION
            result["req_key"] = JIMENG_HD_UPSCALE_REQ_KEY
    else:
        if job_id:
            set_task_progress(job_id, 18, "正在请求模型生成结果")
        feature_key = str((job_context.get("feature") or {}).get("key") or "")
        if feature_key == "hd_batch":
            result = call_portrait_hd_upscale(list(job_context.get("uploaded_files") or [])[:1], prompt=str(job_context.get("prompt") or ""))
        elif feature_key == JIMENG_HD_FEATURE_KEY or feature_mode == "jimeng_upscale":
            result = call_jimeng_hd_upscale(
                uploaded_files=list(job_context.get("uploaded_files") or [])[:1],
            )
        elif feature_mode == "jimeng" or is_jimeng_model(str(job_context.get("model") or "")):
            result = call_jimeng_v40(
                prompt=str(job_context["prompt"]),
                aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
                uploaded_files=list(job_context.get("uploaded_files") or []),
                feature_key=feature_key,
            )
        else:
            analysis_palette: list[dict[str, Any]] = []
            request_prompt = str(job_context["prompt"])
            if feature_key == IMAGE_SMART_ANALYSIS_FEATURE_KEY:
                analysis_inputs = list(job_context.get("uploaded_files") or [])
                if not analysis_inputs:
                    raise RuntimeError("图片智能分析需要先上传 1 张主图。")
                analysis_palette = extract_image_smart_palette(analysis_inputs[0])
                request_prompt = build_image_smart_analysis_model_prompt(
                    request_prompt,
                    analysis_palette,
                )
            if feature_key in A_PLUS_IMAGES_API_FEATURE_KEYS and str(job_context.get("output_mode") or "") == "image":
                target_size = job_context.get("target_size")
                request_aspect_ratio = (
                    select_closest_aspect_ratio((int(target_size[0]), int(target_size[1])))
                    if target_size
                    else str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO)
                )
                request_uploaded_files = list(job_context["uploaded_files"])
                skill_skeleton = job_context.get("a_plus_layout_skill_skeleton")
                skill_skeleton_used = False
                if (
                    feature_key == AMAZON_A_PLUS_FEATURE_KEY
                    and skill_skeleton is not None
                    and len(request_uploaded_files) < MAIN_IMAGE_A_PLUS_MAX_FILES
                ):
                    request_uploaded_files.append(prepare_uploaded_input(skill_skeleton))
                    skill_skeleton_used = True
                result = call_openrouter_images_api(
                    model=str(job_context["model"]),
                    prompt=str(job_context["prompt"]),
                    uploaded_files=request_uploaded_files,
                    aspect_ratio=request_aspect_ratio,
                    resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
                )
                result["channel"] = "Images API 原生 4K"
                result["requested_aspect_ratio"] = request_aspect_ratio
                result["layout_skill_id"] = str(job_context.get("a_plus_layout_skill_id") or "")
                result["layout_skill_skeleton_used"] = skill_skeleton_used
            else:
                result = call_openrouter(
                    model=str(job_context["model"]),
                    prompt=request_prompt,
                    uploaded_files=list(job_context["uploaded_files"]),
                    output_mode=str(job_context["output_mode"]),
                    aspect_ratio=str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
                )
            if feature_key == IMAGE_SMART_ANALYSIS_FEATURE_KEY:
                if job_id:
                    set_task_progress(job_id, 80, "正在生成分区域视觉拆解图")
                result = build_image_smart_analysis_result(
                    result,
                    list(job_context.get("uploaded_files") or [])[0],
                    palette=analysis_palette,
                )
        if job_id:
            set_task_progress(
                job_id,
                72,
                (
                    "正在整理分析报告"
                    if str(job_context.get("output_mode") or "") == "text"
                    else "正在整理返回图片"
                ),
            )
        if job_context["output_mode"] == "image":
            target_size = job_context.get("target_size")
            min_output_edge = get_feature_min_output_edge(feature_key)
            if target_size and feature_key != AMAZON_A_PLUS_FEATURE_KEY:
                result["images"] = [
                    resize_image_to_exact_size(image_url, int(target_size[0]), int(target_size[1]))
                    for image_url in (result.get("images") or [])
                ]
            elif feature_key not in {"hd_batch", JIMENG_HD_FEATURE_KEY, "background_cutout", "outpaint"}:
                result["images"] = [
                    upscale_image_to_min_edge(
                        image_url,
                        min_output_edge,
                        enhance_detail=should_enhance_output_detail(feature_key),
                    )
                    for image_url in (result.get("images") or [])
                ]
            if feature_key == AMAZON_A_PLUS_FEATURE_KEY and (result.get("images") or []):
                if job_id:
                    set_task_progress(job_id, 80, "正在识别绿幕元素并生成分层 PSD")
                result = build_amazon_a_plus_layered_result(result, target_size)
            if (feature_key == A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY
                    and job_context.get("a_plus_first_screen_workflow_stage") != "hero"):
                original = list(job_context.get("uploaded_files") or [])[0]
                result["images"] = [preserve_first_screen_pixels(url, original)
                                    for url in result.get("images") or []]
        max_output_images = int(job_context.get("max_output_images") or 0)
        if max_output_images > 0:
            result["images"] = (result.get("images") or [])[:max_output_images]
        if job_context["output_mode"] == "image" and not (result.get("images") or []):
            backend_name = "Agent" if is_jimeng_model(str(job_context.get("model") or "")) else "OpenRouter"
            raise RuntimeError(f"{backend_name} 未返回图片：请求已提交，但响应中没有可用的结果图片。")
    return finalize_feature_job_result(job_context, result, job_id)


def _submit_feature_job_legacy(
    feature,
    job_context,
    *,
    datetime,
    get_task_runtime,
    run_feature_job,
    set_task_progress,
    st,
) -> None:
    runtime = get_task_runtime()
    job_id = f"{feature['key']}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    job_context = dict(job_context)
    job_context["job_id"] = job_id
    set_task_progress(job_id, 1, "任务已提交，等待开始")
    future = runtime.executor.submit(run_feature_job, job_context)
    with runtime.lock:
        runtime.futures[job_id] = future
    st.session_state.background_jobs[feature["key"]] = {
        "job_id": job_id,
        "status": "running",
        "feature_name": feature["name"],
        "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": "",
        "progress": 1,
        "stage": "任务已提交，等待开始",
    }


def run_queued_feature_job(
    job_context,
    *,
    admitted_job,
    capture_runtime,
    datetime,
    get_task_runtime,
    request_wait_callback,
    run_feature_job,
    set_task_progress,
) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    if job_id:
        set_task_progress(job_id, 3, "排队结束，正在启动任务")

    def report_request_wait(group: str, position: int) -> None:
        if not job_id or group == "download":
            return
        labels = {"omnia_image": "OmniaKey 生图", "omnia_text": "OmniaKey 分析", "ark": "即梦生图", "jimeng": "即梦超清"}
        label = labels.get(group, "模型")
        if group == "omnia_image" and str((job_context.get("feature") or {}).get("key") or "") == "hd_batch":
            label = "Nano Banana 2.1"
        runtime = get_task_runtime()
        with runtime.lock:
            progress = runtime.progress.setdefault(job_id, {"percent": 3})
            progress.update(
                stage=f"等待{label}空闲，当前排队第 {position} 位" if position else f"正在请求{label}",
                request_waiting=bool(position),
                updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

    with admitted_job(existing=True), request_wait_callback(report_request_wait):
        if job_context.get("qa_turn_id"):
            from Department.视觉设计部.xiaoha.qa_chat import run_chat_job
            return run_chat_job(capture_runtime(), job_context, run_feature_job)
        return run_feature_job(job_context)


def submit_feature_job(
    feature,
    job_context,
    *,
    JIMENG_HD_FEATURE_KEY,
    JIMENG_HD_GLOBAL_QUEUE_KEY,
    NANO_BANANA_MODEL,
    clear_task_progress,
    datetime,
    get_request_limiter,
    get_task_runtime,
    run_queued_feature_job,
    set_task_progress,
    st,
) -> dict[str, Any]:
    get_request_limiter().ensure_accepting()
    runtime = get_task_runtime()
    job_id = str(job_context.get("job_id") or f"{feature['key']}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    job_context = dict(job_context)
    job_context["job_id"] = job_id
    feature_key = str(feature.get("key") or "").strip()
    if feature_key == "hd_batch":
        job_context["model"] = NANO_BANANA_MODEL
    is_jimeng_hd_job = feature_key == JIMENG_HD_FEATURE_KEY
    queue_key = (
        JIMENG_HD_GLOBAL_QUEUE_KEY
        if is_jimeng_hd_job
        else (str(job_context.get("account_name") or "admin").strip() or "admin")
    )
    set_task_progress(job_id, 1, "任务已提交，正在排队")
    try:
        runtime.submit_generation_job(
            queue_key,
            job_id,
            run_queued_feature_job,
            job_context,
            # 即梦超清跨用户 FIFO，服务商容量另由跨进程限流器统一控制。
            max_outstanding_jobs=None,
        )
    except Exception:
        clear_task_progress(job_id)
        raise
    queue_state = runtime.get_generation_queue_state(job_id)
    is_running = queue_state.get("state") == "running"
    ahead_count = max(int(queue_state.get("ahead_count") or 0), 0)
    job_info = {
        "job_id": job_id,
        "status": "running" if is_running else "queued",
        "feature_key": feature_key,
        "feature_name": str(feature.get("name") or feature.get("key") or "任务"),
        "queue_key": queue_key,
        "queue_ahead": ahead_count,
        "queue_position": max(int(queue_state.get("queue_position") or 0), 0),
        "queue_capacity": runtime.max_outstanding_jobs if is_jimeng_hd_job else runtime.max_account_jobs,
        "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": "",
        "progress": 1,
        "stage": (
            "任务已开始执行"
            if is_running
            else (f"排队中，前面还有 {ahead_count} 个任务" if ahead_count else "排队中，等待执行")
        ),
    }
    workflow_stage = str(job_context.get("a_plus_first_screen_workflow_stage") or "").strip()
    if workflow_stage:
        job_info["a_plus_first_screen_workflow_stage"] = workflow_stage
    queue_records = list(st.session_state.get("background_job_queue") or [])
    queue_records.append(job_info)
    st.session_state.background_job_queue = queue_records
    st.session_state.background_jobs[feature["key"]] = job_info
    return job_info
