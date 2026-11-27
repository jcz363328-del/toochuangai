"""Execute Xiaoha image batches and infinite canvas jobs."""

from __future__ import annotations

from typing import Any


def process_batch_group(
    job_context,
    uploaded_group,
    group_index,
    *,
    Any,
    DEFAULT_ASPECT_RATIO,
    JIMENG_HD_FEATURE_KEY,
    OUTPAINT_RESULTS_PER_SOURCE,
    REMOVE_EYELASHES_IMAGE_RESOLUTION,
    _OPENROUTER_REMOVE_EYELASHES_LOCK,
    build_outpaint_seam_repair_prompt,
    build_outpaint_seam_repair_reference,
    build_outpaint_source_canvas,
    build_outpaint_source_framing_instruction,
    call_ark_seedream_images_api,
    call_jimeng_hd_upscale,
    call_jimeng_v40,
    call_openrouter,
    call_openrouter_images_api,
    call_portrait_hd_upscale,
    clamp_outpaint_extensions,
    crop_outpaint_result_to_selected_region,
    get_feature_min_output_edge,
    get_outpaint_target_aspect_ratio,
    get_outpaint_target_canvas_size,
    get_uploaded_input_closest_aspect_ratio,
    get_uploaded_input_dimensions,
    get_uploaded_input_name,
    has_outpaint_rectangular_join,
    is_ark_seedream_model,
    is_jimeng_model,
    is_omnia_image_outcome_unknown,
    is_outpaint_result_effectively_unchanged,
    measure_outpaint_boundary_seams,
    resize_image_to_exact_size,
    run_hd_batch_generate_with_retry,
    should_enhance_output_detail,
    upscale_image_to_min_edge,
) -> dict[str, Any]:
    source_name = get_uploaded_input_name(uploaded_group[0]) if uploaded_group else ""
    feature_key = str((job_context.get("feature") or {}).get("key") or "")
    min_output_edge = get_feature_min_output_edge(feature_key)
    request_aspect_ratio = str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO)
    request_prompt = str(job_context["prompt"])
    request_uploaded_group = list(uploaded_group)
    outpaint_alignment: dict[str, int] = {}
    if feature_key == "outpaint" and uploaded_group:
        outpaint_settings = dict(job_context.get("outpaint_settings") or {})
        top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
            uploaded_group[0],
            int(outpaint_settings.get("top", 0) or 0),
            int(outpaint_settings.get("bottom", 0) or 0),
            int(outpaint_settings.get("left", 0) or 0),
            int(outpaint_settings.get("right", 0) or 0),
        )
        target_width, target_height = get_outpaint_target_canvas_size(
            uploaded_group[0],
            top_px,
            bottom_px,
            left_px,
            right_px,
        )
        source_width, source_height = get_uploaded_input_dimensions(uploaded_group[0])
        locked_source_width = int(outpaint_settings.get("source_width", 0) or 0)
        locked_source_height = int(outpaint_settings.get("source_height", 0) or 0)
        if (
            locked_source_width == source_width
            and locked_source_height == source_height
        ):
            locked_target_width = int(outpaint_settings.get("target_width", 0) or 0)
            locked_target_height = int(outpaint_settings.get("target_height", 0) or 0)
            if (
                locked_target_width > 0
                and locked_target_height > 0
                and (target_width, target_height)
                != (locked_target_width, locked_target_height)
            ):
                raise RuntimeError(
                    "扩图提交尺寸校验失败：界面锁定尺寸与后台计算尺寸不一致，请刷新页面后重新提交。"
                )
        outpaint_alignment = {
            "source_width": source_width,
            "source_height": source_height,
            "target_width": target_width,
            "target_height": target_height,
            "top": top_px,
            "bottom": bottom_px,
            "left": left_px,
            "right": right_px,
        }
        transition_canvas = build_outpaint_source_canvas(
            uploaded_group[0],
            top_px,
            bottom_px,
            left_px,
            right_px,
        )
        request_uploaded_group = [transition_canvas]
        request_aspect_ratio = get_outpaint_target_aspect_ratio(
            uploaded_group[0],
            top_px,
            bottom_px,
            left_px,
            right_px,
            fallback=request_aspect_ratio,
        )
        request_prompt += (
            "\n\nCurrent source-specific expansion: "
            f"top {top_px}px, bottom {bottom_px}px, left {left_px}px, right {right_px}px. "
            f"The intended expanded canvas is {target_width}×{target_height} before mapping to the nearest supported model aspect ratio."
            "\n\n"
            + build_outpaint_source_framing_instruction(
                uploaded_group[0],
                top_px,
                bottom_px,
                left_px,
                right_px,
            )
            + "\n\nThere is exactly one input image: the authoritative outpaint working canvas at the requested final aspect ratio. The visible photograph is already placed at the exact X/Y position selected by the user. The soft edge-color fields outside it are disposable generation scaffolding, not real scene content, and every requested outer area must be replaced with a natural continuation of the photograph. "
            + "The interior away from the former boundary is the visual authority. Do not move, recenter, enlarge, shrink, crop, or duplicate it, but seamless full-frame continuity has higher priority than exact pixel locking near an old edge. The softly blended former-edge corridor is a mandatory reconstruction area; regenerate it together with the outer scaffold so it never becomes a frame, inset, rectangle, tonal band, blur band, stretched edge, or pasted-photo boundary. "
            + "Generate the complete final photograph directly in one model pass. Around every former source edge that touches an expanded side, reconstruct the blended transition corridor together with the disposable outer scaffold, so geometry, long lines, texture, depth, illumination, color, sharpness, grain, and noise continue naturally across the former boundary. "
            + "Globally harmonize exposure, white balance, contrast, saturation, focus falloff, texture scale, and image grain across the full final frame. There must be no sudden tonal step or detail-frequency change at any old edge. Preserve the interior away from each transition corridor as closely as possible, but never at the cost of exposing the old rectangular source boundary. "
            + "Never recenter, zoom, rescale, or redistribute the source field. A side with zero requested expansion must remain exactly on the final image edge. "
            + "If the person or any limb, garment, hair, furniture, or object crosses a former edge, continue exactly that same structure through the corridor with coherent anatomy, perspective, texture, light, and scale. Do not cut it at the former boundary, do not create a horizontal or vertical join, and do not restart a different body or object in the new area. "
            + "Keep the single person and all important anatomy naturally framed inside the final outer canvas; avoid final-edge cuts through the head, face, hands, elbows, knees, or other joints."
        )

    def generate_once(
        prompt_text: str,
        uploaded_files_override: list[Any] | None = None,
    ) -> dict[str, Any]:
        active_uploaded_group = (
            list(request_uploaded_group)
            if uploaded_files_override is None
            else list(uploaded_files_override)
        )
        if feature_key == "hd_batch":
            return call_portrait_hd_upscale(list(active_uploaded_group[:1]), prompt=prompt_text)
        if feature_key == JIMENG_HD_FEATURE_KEY:
            return call_jimeng_hd_upscale(uploaded_files=list(active_uploaded_group[:1]))
        if is_ark_seedream_model(str(job_context.get("model") or "")):
            from .generation_settings import current_resolution
            return call_ark_seedream_images_api(
                prompt=prompt_text + (f"\n输出图片宽高比：{request_aspect_ratio}。" if request_aspect_ratio != DEFAULT_ASPECT_RATIO else ""),
                uploaded_files=list(active_uploaded_group),
                size=current_resolution(),
            )
        if is_jimeng_model(str(job_context.get("model") or "")):
            return call_jimeng_v40(
                prompt=prompt_text,
                aspect_ratio=request_aspect_ratio,
                uploaded_files=list(active_uploaded_group),
                feature_key=feature_key,
            )
        if feature_key == "remove_eyelashes":
            source_aspect_ratio = request_aspect_ratio
            if active_uploaded_group:
                source_aspect_ratio = get_uploaded_input_closest_aspect_ratio(
                    active_uploaded_group[0],
                    fallback=request_aspect_ratio,
                )
            with _OPENROUTER_REMOVE_EYELASHES_LOCK:
                return call_openrouter_images_api(
                    model=str(job_context["model"]),
                    prompt=prompt_text,
                    uploaded_files=list(active_uploaded_group[:1]),
                    aspect_ratio=source_aspect_ratio,
                    resolution=REMOVE_EYELASHES_IMAGE_RESOLUTION,
                )
        return call_openrouter(
            model=str(job_context["model"]),
            prompt=prompt_text,
            uploaded_files=list(active_uploaded_group),
            output_mode=str(job_context["output_mode"]),
            aspect_ratio=request_aspect_ratio,
        )

    if feature_key == "outpaint" and str(job_context.get("output_mode") or "") == "image":
        variant_count = max(int(job_context.get("max_output_images") or OUTPAINT_RESULTS_PER_SOURCE), 1)
        variant_images: list[str] = []
        variant_texts: list[str] = []
        for variant_index in range(variant_count):
            variant_prompt = (
                request_prompt
                + "\n\n"
                + f"Generate candidate {variant_index + 1} of {variant_count}. Return exactly one finished image in this call. "
                + "Keep the source identity and requested framing fixed, while giving the newly extended environment a natural independent variation."
            )
            variant_result = generate_once(variant_prompt)
            first_variant_image = next(
                iter(list(variant_result.get("images") or [])[:1]),
                "",
            )
            if (
                first_variant_image
                and (top_px + bottom_px + left_px + right_px) > 0
                and is_outpaint_result_effectively_unchanged(
                    str(first_variant_image),
                    uploaded_group[0],
                )
            ):
                variant_result = generate_once(
                    variant_prompt
                    + "\n\nThe previous attempt failed because it returned the original crop with no visible expansion. "
                    + "This retry must replace every disposable outer scaffold region of the working canvas with real scene content and visibly show the requested new surroundings. "
                    + "Returning the old framing again is invalid."
                )
            variant_images.extend(list(variant_result.get("images") or [])[:1])
            variant_text = str(variant_result.get("text") or "").strip()
            if variant_text:
                variant_texts.append(variant_text)
        batch_result = {
            "images": variant_images,
            "text": "\n\n".join(variant_texts),
        }
    else:
        try:
            if feature_key == "hd_batch" and str(job_context.get("output_mode") or "") == "image":
                batch_result = run_hd_batch_generate_with_retry(
                    generate_once,
                    request_prompt,
                    retry_offset_seconds=(max(group_index, 1) - 1) * 4,
                )
            else:
                batch_result = generate_once(request_prompt)
        except Exception as exc:
            if feature_key == "remove_eyelashes":
                source_label = f"第 {group_index} 张"
                if source_name:
                    source_label += f"（{source_name}）"
                raise RuntimeError(f"{source_label}处理失败：{exc}") from exc
            raise
    if job_context["output_mode"] == "image":
        target_size = job_context.get("target_size")
        if target_size:
            batch_result["images"] = [
                resize_image_to_exact_size(image_url, int(target_size[0]), int(target_size[1]))
                for image_url in (batch_result.get("images") or [])
            ]
        elif feature_key == "outpaint" and outpaint_alignment:
            corrected_images: list[str] = []
            rejected_join_count = 0

            def normalize_and_measure_outpaint(candidate_url: str) -> tuple[str, list[dict[str, Any]]]:
                normalized_candidate = crop_outpaint_result_to_selected_region(
                    str(candidate_url),
                    uploaded_group[0],
                    int(outpaint_alignment["top"]),
                    int(outpaint_alignment["bottom"]),
                    int(outpaint_alignment["left"]),
                    int(outpaint_alignment["right"]),
                )
                candidate_measurements = measure_outpaint_boundary_seams(
                    normalized_candidate,
                    uploaded_group[0],
                    int(outpaint_alignment["top"]),
                    int(outpaint_alignment["bottom"]),
                    int(outpaint_alignment["left"]),
                    int(outpaint_alignment["right"]),
                )
                return normalized_candidate, candidate_measurements

            for image_url in (batch_result.get("images") or []):
                corrected_image, seam_measurements = normalize_and_measure_outpaint(
                    str(image_url)
                )
                if has_outpaint_rectangular_join(seam_measurements):
                    repair_result: dict[str, Any] = {}
                    try:
                        repair_reference = build_outpaint_seam_repair_reference(corrected_image)
                        repair_result = generate_once(
                            build_outpaint_seam_repair_prompt(
                                uploaded_group[0],
                                int(outpaint_alignment["top"]),
                                int(outpaint_alignment["bottom"]),
                                int(outpaint_alignment["left"]),
                                int(outpaint_alignment["right"]),
                                seam_measurements,
                            ),
                            [repair_reference],
                        )
                    except Exception as exc:
                        if is_omnia_image_outcome_unknown(exc):
                            raise
                        repair_result = {}
                    repaired_image = next(
                        iter(list(repair_result.get("images") or [])[:1]),
                        "",
                    )
                    if repaired_image:
                        normalized_repaired_image, repaired_measurements = (
                            normalize_and_measure_outpaint(str(repaired_image))
                        )
                        if not has_outpaint_rectangular_join(repaired_measurements):
                            corrected_image = normalized_repaired_image
                            seam_measurements = repaired_measurements
                    if has_outpaint_rectangular_join(seam_measurements):
                        retry_result: dict[str, Any] = {}
                        try:
                            retry_result = generate_once(
                                request_prompt
                                + "\n\nMANDATORY CLEAN REGENERATION AFTER RECTANGULAR-JOIN REJECTION. "
                                + "A previous candidate was rejected because it rendered the old source as a visible inset rectangle and duplicated the person outside it. "
                                + "Start again from the supplied edge-color working scaffold. Render exactly one continuous camera exposure with exactly one person. "
                                + "Replace all outer scaffold bands with real scene content and remove all four conceptual source boundaries. "
                                + "Do not paste the source back, do not draw an inner rectangle, and do not duplicate the head, face, torso, arms, hands, hair, or clothing."
                            )
                        except Exception as exc:
                            if is_omnia_image_outcome_unknown(exc):
                                raise
                            retry_result = {}
                        retry_image = next(
                            iter(list(retry_result.get("images") or [])[:1]),
                            "",
                        )
                        if retry_image:
                            normalized_retry_image, retry_measurements = (
                                normalize_and_measure_outpaint(str(retry_image))
                            )
                            if not has_outpaint_rectangular_join(retry_measurements):
                                corrected_image = normalized_retry_image
                                seam_measurements = retry_measurements
                if has_outpaint_rectangular_join(seam_measurements):
                    rejected_join_count += 1
                    continue
                corrected_images.append(corrected_image)
            batch_result["images"] = corrected_images
            if rejected_join_count:
                rejection_notice = (
                    f"已自动拦截 {rejected_join_count} 张仍存在矩形拼接或重复人物的扩图候选，"
                    "这些坏图不会进入结果和下载。"
                )
                batch_result["text"] = "\n\n".join(
                    part
                    for part in (
                        str(batch_result.get("text") or "").strip(),
                        rejection_notice,
                    )
                    if part
                )
        elif feature_key not in {"hd_batch", JIMENG_HD_FEATURE_KEY, "background_cutout", "outpaint"}:
            batch_result["images"] = [
                upscale_image_to_min_edge(
                    image_url,
                    min_output_edge,
                    enhance_detail=should_enhance_output_detail(feature_key),
                )
                for image_url in (batch_result.get("images") or [])
            ]
    max_output_images = int(job_context.get("max_output_images") or 0)
    if max_output_images > 0:
        batch_result["images"] = (batch_result.get("images") or [])[:max_output_images]
    return {
        "group_index": group_index,
        "source_name": source_name,
        "images": list(batch_result.get("images") or []),
        "text": str(batch_result.get("text") or "").strip(),
        "outpaint_alignment": outpaint_alignment,
    }


def run_infinite_canvas_job(
    job_context,
    *,
    DEFAULT_ASPECT_RATIO,
    JIMENG_HD_FEATURE_KEY,
    NANO_BANANA_MODEL,
    OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
    OUTPAINT_DEFAULT_EXTENSION_PX,
    build_outpaint_extra_notes,
    build_prompt,
    build_uploaded_input_from_image_url_raw,
    call_jimeng_hd_upscale,
    call_jimeng_portrait_hd,
    call_jimeng_v40,
    call_openrouter,
    call_openrouter_portrait_hd,
    clamp_outpaint_extensions,
    get_feature_by_key,
    get_feature_min_output_edge,
    get_outpaint_target_aspect_ratio,
    is_jimeng_model,
    math,
    prepare_uploaded_input,
    set_task_progress,
    should_enhance_output_detail,
    uploaded_input_to_data_url,
    upscale_image_to_min_edge,
) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    uploaded_files = [prepare_uploaded_input(item) for item in list(job_context.get("uploaded_files") or [])]
    step_keys = [
        str(step_key or "").strip()
        for step_key in list(job_context.get("canvas_steps") or [])
        if get_feature_by_key(str(step_key or "").strip()) is not None
    ]
    if not uploaded_files:
        raise RuntimeError("无限画布需要先上传至少 1 张图片。")
    if not step_keys:
        raise RuntimeError("请至少选择 1 个要组合的处理步骤。")

    model = str(job_context.get("model") or NANO_BANANA_MODEL)
    aspect_ratio = str(job_context.get("aspect_ratio") or DEFAULT_ASPECT_RATIO)
    custom_prompt = str(job_context.get("custom_prompt") or "")
    canvas_step_settings = list(job_context.get("canvas_step_settings") or [])
    canvas_outpaint = dict(job_context.get("canvas_outpaint") or {})
    outpaint_top_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(canvas_outpaint.get("top", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
    outpaint_bottom_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(canvas_outpaint.get("bottom", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
    outpaint_left_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(canvas_outpaint.get("left", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
    outpaint_right_px = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, int(canvas_outpaint.get("right", OUTPAINT_DEFAULT_EXTENSION_PX) or 0)))
    canvas_hd_reference = job_context.get("canvas_hd_reference")
    if canvas_hd_reference is not None:
        canvas_hd_reference = prepare_uploaded_input(canvas_hd_reference)

    result_images: list[str] = []
    source_images: list[str] = []
    captions: list[str] = []
    text_parts: list[str] = []
    total_operations = max(len(uploaded_files) * len(step_keys), 1)
    completed_operations = 0

    if job_id:
        set_task_progress(job_id, 8, "正在执行无限画布组合流程")

    for image_index, original_input in enumerate(uploaded_files, start=1):
        current_input = prepare_uploaded_input(original_input)
        final_image_url = ""
        try:
            source_images.append(uploaded_input_to_data_url(original_input))
        except Exception:
            source_images.append("")
        step_names: list[str] = []

        for step_index, step_key in enumerate(step_keys, start=1):
            step_feature = get_feature_by_key(step_key)
            if step_feature is None:
                continue
            step_settings = (
                dict(canvas_step_settings[step_index - 1])
                if step_index - 1 < len(canvas_step_settings) and isinstance(canvas_step_settings[step_index - 1], dict)
                else {}
            )
            step_names.append(str(step_feature.get("name") or step_key))
            extra_notes = (
                f"这是无限画布组合流程的第 {step_index}/{len(step_keys)} 步。"
                "当前输入可能是上一步已经处理过的结果，请把它作为唯一主体继续处理，"
                "不要重置画面、不要生成多版本、不要改变已经稳定的主体身份。"
            )
            step_aspect_ratio = aspect_ratio
            step_uploaded_files = [current_input]
            step_hd_reference = step_settings.get("hd_reference") or canvas_hd_reference
            if step_hd_reference is not None:
                step_hd_reference = prepare_uploaded_input(step_hd_reference)
            if step_key == "hd_batch" and step_hd_reference is not None:
                step_uploaded_files = [current_input, step_hd_reference]
            if step_key == "outpaint":
                step_outpaint = dict(step_settings.get("outpaint") or {})
                current_top_px, current_bottom_px, current_left_px, current_right_px = clamp_outpaint_extensions(
                    current_input,
                    int(step_outpaint.get("top", outpaint_top_px) or 0),
                    int(step_outpaint.get("bottom", outpaint_bottom_px) or 0),
                    int(step_outpaint.get("left", outpaint_left_px) or 0),
                    int(step_outpaint.get("right", outpaint_right_px) or 0),
                )
                if current_top_px + current_bottom_px + current_left_px + current_right_px <= 0:
                    raise RuntimeError("无限画布里的扩图步骤至少需要一个方向大于 0。")
                step_uploaded_files = [current_input]
                step_aspect_ratio = get_outpaint_target_aspect_ratio(
                    current_input,
                    current_top_px,
                    current_bottom_px,
                    current_left_px,
                    current_right_px,
                    fallback=aspect_ratio,
                )
                extra_notes = (
                    build_outpaint_extra_notes(
                        current_top_px,
                        current_bottom_px,
                        current_left_px,
                        current_right_px,
                    )
                    + "\n"
                    + extra_notes
                )
            step_prompt = build_prompt(
                dict(step_feature),
                custom_prompt,
                step_aspect_ratio,
                extra_notes,
            )
            if step_key == JIMENG_HD_FEATURE_KEY:
                step_result = call_jimeng_hd_upscale(
                    uploaded_files=step_uploaded_files[:1],
                )
            elif is_jimeng_model(model):
                if step_key == "hd_batch":
                    step_result = call_jimeng_portrait_hd(
                        prompt=step_prompt,
                        aspect_ratio=step_aspect_ratio,
                        uploaded_files=step_uploaded_files,
                        feature_key=step_key,
                    )
                else:
                    step_result = call_jimeng_v40(
                        prompt=step_prompt,
                        aspect_ratio=step_aspect_ratio,
                        uploaded_files=step_uploaded_files,
                        feature_key=step_key,
                    )
            elif step_key == "hd_batch":
                step_result = call_openrouter_portrait_hd(
                    model=model,
                    prompt=step_prompt,
                    aspect_ratio=step_aspect_ratio,
                    uploaded_files=step_uploaded_files,
                )
            else:
                step_result = call_openrouter(
                    model=model,
                    prompt=step_prompt,
                    uploaded_files=step_uploaded_files,
                    output_mode="image",
                    aspect_ratio=step_aspect_ratio,
                )

            step_images = list(step_result.get("images") or [])
            if not step_images:
                raise RuntimeError(f"无限画布第 {step_index} 步「{step_feature.get('name') or step_key}」没有返回图片。")
            image_url = str(step_images[0])
            if step_key not in {"hd_batch", JIMENG_HD_FEATURE_KEY, "outpaint"}:
                image_url = upscale_image_to_min_edge(
                    image_url,
                    get_feature_min_output_edge(step_key),
                    enhance_detail=should_enhance_output_detail(step_key),
                )
            step_text = str(step_result.get("text") or "").strip()
            if step_text:
                text_parts.append(f"图 {image_index} / {step_feature.get('name') or step_key}：{step_text}")
            current_input = build_uploaded_input_from_image_url_raw(
                image_url,
                base_name=f"infinite_canvas_{image_index}_{step_index}.png",
            )
            final_image_url = image_url
            completed_operations += 1
            if job_id:
                progress_value = 12 + math.floor((completed_operations / total_operations) * 66)
                set_task_progress(
                    job_id,
                    min(progress_value, 82),
                    f"正在处理第 {image_index}/{len(uploaded_files)} 张，第 {step_index}/{len(step_keys)} 步",
                )

        result_images.append(final_image_url or uploaded_input_to_data_url(current_input))
        captions.append(f"画布图 {image_index} · {' → '.join(step_names)}")

    if not result_images:
        raise RuntimeError("无限画布没有生成可用结果，请调整组合步骤后重试。")
    return {
        "images": result_images,
        "source_images": source_images[: len(result_images)],
        "captions": captions,
        "text": "\n\n".join(text_parts).strip(),
    }
