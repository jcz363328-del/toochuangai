"""Run the main-image A+ generation, editing and mobile adaptation jobs."""

from __future__ import annotations

from typing import Any


def run_main_image_a_plus_manual_element_job(
    template_input,
    point,
    existing_elements,
    job_id,
    *,
    admitted_job,
    analyze_main_image_a_plus_element_at_point,
    set_task_progress,
) -> dict[str, Any]:
    with admitted_job(existing=True):
        set_task_progress(job_id, 15, "正在读取点击位置")
        set_task_progress(job_id, 35, "正在识别点击位置的完整元素")
        new_element = analyze_main_image_a_plus_element_at_point(
            template_input,
            point,
            existing_elements,
        )
        set_task_progress(job_id, 100, "补漏识别完成")
        return new_element


def run_main_image_a_plus_text_edit_job(
    job_context,
    *,
    AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
    Image,
    ImageOps,
    MAIN_IMAGE_A_PLUS_MODE_TEXT_EDIT,
    NANO_BANANA_MODEL,
    build_main_image_a_plus_text_edit_prompt,
    call_openrouter_images_api,
    cover_image_to_exact_size,
    io,
    load_image_bytes_from_url,
    select_main_image_a_plus_safe_aspect_ratio,
    set_task_progress,
) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    source_image = str(job_context.get("main_image_a_plus_text_edit_source") or "").strip()
    replacement_text = str(job_context.get("main_image_a_plus_text_edit_content") or "").strip()
    font_name = str(job_context.get("main_image_a_plus_text_edit_font") or "").strip()
    raw_point = job_context.get("main_image_a_plus_text_edit_point")
    if not source_image:
        raise RuntimeError("没有可用于文字编辑的 A+ 成品图。")
    if not replacement_text:
        raise RuntimeError("请输入修改后的文字内容。")
    if not isinstance(raw_point, (list, tuple)) or len(raw_point) < 2:
        raise RuntimeError("请先在成品图上点击需要修改的文字。")
    point = (
        max(0, min(1000, int(raw_point[0]))),
        max(0, min(1000, int(raw_point[1]))),
    )
    if job_id:
        set_task_progress(job_id, 10, "正在读取 A+ 成品与目标文字位置")
    source_bytes, source_mime_type = load_image_bytes_from_url(source_image)
    source_reference = {
        "data": source_bytes,
        "name": "a_plus_text_edit_source.png",
        "type": source_mime_type or "image/png",
    }
    try:
        with Image.open(io.BytesIO(source_bytes)) as image:
            source = ImageOps.exif_transpose(image)
            target_width, target_height = source.size
    except Exception as exc:
        raise RuntimeError(f"A+ 成品图读取失败：{exc}") from exc
    if target_width < 1 or target_height < 1:
        raise RuntimeError("A+ 成品图尺寸无效。")
    request_aspect_ratio = select_main_image_a_plus_safe_aspect_ratio(
        (target_width, target_height)
    )
    edit_prompt = build_main_image_a_plus_text_edit_prompt(
        point,
        replacement_text,
        font_name,
    )
    if job_id:
        set_task_progress(job_id, 24, "正在锁定点击位置对应的完整文字块")
    edit_result = call_openrouter_images_api(
        model=str(job_context.get("model") or NANO_BANANA_MODEL),
        prompt=edit_prompt,
        uploaded_files=[source_reference],
        aspect_ratio=request_aspect_ratio,
        resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        max_attempts=1,
    )
    generated_images = list(edit_result.get("images") or [])
    if not generated_images:
        raise RuntimeError("文字编辑没有返回成品图，请重新提交。")
    if job_id:
        set_task_progress(job_id, 78, "文字已替换，正在恢复原图尺寸")
    final_image_url = cover_image_to_exact_size(
        str(generated_images[0]),
        target_width,
        target_height,
    )
    return {
        "images": [final_image_url],
        "text": (
            f"已将点击位置附近的目标文字替换为“{replacement_text}”，字体设置为“{font_name or '保持原字体风格'}”。"
            "编辑结果保持原图尺寸，并要求锁定目标文字块以外的全部内容。"
        ),
        "channel": "Images API 原生 4K · A+ 文字局部编辑",
        "target_size": (target_width, target_height),
        "requested_aspect_ratios": (request_aspect_ratio,),
        "section_count": 1,
        "section_heights": (target_height,),
        "section_height": target_height,
        "main_image_a_plus_mode": MAIN_IMAGE_A_PLUS_MODE_TEXT_EDIT,
        "main_image_a_plus_text_edit_source": source_image,
        "main_image_a_plus_text_edit_point": point,
        "main_image_a_plus_text_edit_content": replacement_text,
        "main_image_a_plus_text_edit_font": font_name or "保持原字体风格",
    }


def run_main_image_a_plus_mobile_adaptation_job(
    job_context,
    *,
    AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
    Any,
    MAIN_IMAGE_A_PLUS_MAX_QUALITY_ATTEMPTS,
    MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT,
    NANO_BANANA_MODEL,
    analyze_main_image_a_plus_mobile_element_inventory,
    build_main_image_a_plus_mobile_adaptation_prompt,
    build_main_image_a_plus_mobile_repair_prompt,
    build_main_image_a_plus_mobile_safe_margin_instruction,
    build_main_image_a_plus_quality_retry_instruction,
    call_openrouter_images_api,
    collect_main_image_a_plus_quality_issues,
    format_main_image_a_plus_mobile_element_inventory,
    get_main_image_a_plus_mobile_layout_for_source,
    get_main_image_a_plus_mobile_reference_inputs,
    get_uploaded_input_dimensions,
    load_image_bytes_from_url,
    prepare_main_image_a_plus_reference_input,
    rank_main_image_a_plus_quality_review,
    resize_main_image_a_plus_mobile_single_layer,
    review_main_image_a_plus_candidate,
    select_main_image_a_plus_safe_aspect_ratio,
    set_task_progress,
) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    source_image = str(job_context.get("main_image_a_plus_desktop_source") or "").strip()
    if not source_image:
        raise RuntimeError("请先生成一张电脑端 A+ 成品，再进行手机端适配。")

    if job_id:
        set_task_progress(job_id, 12, "正在读取电脑端 A+ 成品")
    source_bytes, source_mime_type = load_image_bytes_from_url(source_image)
    source_input = {
        "data": source_bytes,
        "name": "desktop_a_plus_reference.png",
        "type": source_mime_type,
    }
    source_size = get_uploaded_input_dimensions(source_input)
    target_layout = get_main_image_a_plus_mobile_layout_for_source(source_size)
    target_width, target_height = target_layout["target_size"]
    request_aspect_ratio = select_main_image_a_plus_safe_aspect_ratio((target_width, target_height))
    source_reference = prepare_main_image_a_plus_reference_input(
        source_input
    )
    mobile_layout_references = get_main_image_a_plus_mobile_reference_inputs()
    reference_pair_count = len(mobile_layout_references) // 2
    generation_inputs = [source_reference, *mobile_layout_references]
    if job_id:
        set_task_progress(job_id, 20, "正在建立电脑端元素清单")
    source_elements = analyze_main_image_a_plus_mobile_element_inventory(source_reference)
    element_inventory = format_main_image_a_plus_mobile_element_inventory(source_elements)
    safe_margin_instruction = build_main_image_a_plus_mobile_safe_margin_instruction(
        source_elements,
        target_layout,
    )
    if job_id:
        set_task_progress(
            job_id,
            36,
            f"正在参考 {reference_pair_count} 组样本重排为 {target_layout['mobile_screen_count']} 屏手机版",
        )
    base_generation_prompt = build_main_image_a_plus_mobile_adaptation_prompt(
        element_inventory,
        safe_margin_instruction,
        target_layout,
        reference_pair_count,
    )
    quality_reviews: list[dict[str, Any]] = []
    best_image_url = ""
    best_review: dict[str, Any] = {}
    best_rank: tuple[int, int, float] | None = None
    generation_attempts = 0
    retry_instruction = ""
    repair_candidate_reference: Any | None = None
    repair_review: dict[str, Any] = {}
    for attempt_index in range(MAIN_IMAGE_A_PLUS_MAX_QUALITY_ATTEMPTS):
        generation_attempts = attempt_index + 1
        attempt_inputs = generation_inputs
        if repair_candidate_reference is not None and repair_review:
            attempt_prompt = build_main_image_a_plus_mobile_repair_prompt(
                target_layout,
                element_inventory,
                safe_margin_instruction,
                repair_review,
            )
            attempt_inputs = [source_reference, repair_candidate_reference]
            if job_id:
                set_task_progress(job_id, 62, "首版未通过完整性检查，正在定向修复")
        else:
            attempt_prompt = base_generation_prompt
        if retry_instruction and repair_candidate_reference is None:
            attempt_prompt += f"\n\n{retry_instruction}"
            if job_id:
                set_task_progress(job_id, 62, "首版未通过完整性检查，正在自动重排修复")
        mobile_result = call_openrouter_images_api(
            model=str(job_context.get("model") or NANO_BANANA_MODEL),
            prompt=attempt_prompt,
            uploaded_files=attempt_inputs,
            aspect_ratio=request_aspect_ratio,
            resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
            max_attempts=1,
        )
        generated_images = list(mobile_result.get("images") or [])
        if not generated_images:
            if attempt_index + 1 >= MAIN_IMAGE_A_PLUS_MAX_QUALITY_ATTEMPTS:
                break
            retry_instruction = "上一候选没有返回成品图，请重新生成一张完整手机端 A+。"
            continue
        if job_id:
            set_task_progress(job_id, 68, "正在将单张手机版成品归一为规定尺寸")
        candidate_image_url = resize_main_image_a_plus_mobile_single_layer(
            str(generated_images[0]),
            target_width,
            target_height,
        )
        if job_id:
            set_task_progress(job_id, 72, "正在检查元素、文字安全区和移动端设计质量")
        quality_review = review_main_image_a_plus_candidate(
            candidate_image_url,
            target_layout,
            MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT,
            source_inputs=[source_reference],
            expected_element_inventory=element_inventory,
        )
        quality_reviews.append(quality_review)
        candidate_rank = rank_main_image_a_plus_quality_review(quality_review)
        if best_rank is None or candidate_rank > best_rank:
            best_rank = candidate_rank
            best_image_url = candidate_image_url
            best_review = quality_review
        if bool(quality_review.get("passed")):
            break
        retry_instruction = build_main_image_a_plus_quality_retry_instruction(quality_review)
        repair_review = quality_review
        try:
            candidate_bytes, candidate_mime_type = load_image_bytes_from_url(candidate_image_url)
            repair_candidate_reference = prepare_main_image_a_plus_reference_input(
                {
                    "data": candidate_bytes,
                    "name": f"mobile_candidate_attempt_{generation_attempts}.png",
                    "type": candidate_mime_type,
                }
            )
        except Exception:
            repair_candidate_reference = None
    if not best_image_url:
        raise RuntimeError("手机端适配没有返回成品图，请重试。")
    final_image_url = best_image_url
    quality_issues = collect_main_image_a_plus_quality_issues(best_review)
    critical_issue_count = int(best_review.get("critical_issue_count") or 0)
    quality_passed = bool(best_review.get("passed"))
    if not bool(best_review.get("reviewed")):
        raise RuntimeError(
            "手机端 A+ 成品质检暂时不可用；为避免交付未检查的截断或变形图片，本次结果已拦截，请稍后重试。"
        )
    if not quality_passed:
        issue_summary = "；".join(quality_issues[:6])
        raise RuntimeError(
            "手机端 A+ 已自动重排和修复，但仍未通过元素完整性与移动端设计检查；"
            + (f"主要问题：{issue_summary}。" if issue_summary else "")
            + "本次结果已拦截，请重新生成。"
        )
    if job_id:
        set_task_progress(
            job_id,
            84,
            "手机端成品质检通过，正在保存结果"
            if quality_passed
            else "已保留问题最少的版本，正在保存质检标记",
        )
    return {
        "images": [final_image_url],
        "text": (
            ""
        ),
        "channel": "Images API 原生 4K · 手机端排版适配",
        "mobile_adaptation_source": source_image,
        "requested_aspect_ratios": (request_aspect_ratio,),
        "target_size": (target_width, target_height),
        "section_count": 1,
        "section_heights": (target_height,),
        "section_height": target_height,
        "main_image_a_plus_layout_key": target_layout["key"],
        "main_image_a_plus_layout_label": target_layout["label"],
        "main_image_a_plus_mode": MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT,
        "generation_waves": 2,
        "max_parallel_sections": 1,
        "mobile_generation_attempts": generation_attempts,
        "mobile_screen_count": int(target_layout.get("mobile_screen_count") or 1),
        "mobile_element_inventory_count": len(source_elements),
        "mobile_reference_pair_count": reference_pair_count,
        "prepared_reference_count": len(generation_inputs),
        "mobile_foreground_fit": "single_layer_exact_size",
        "mobile_background_fill": "none",
        "mobile_outpaint_section_count": 0,
        "quality_reviewed": bool(best_review.get("reviewed")),
        "quality_review_passed": quality_passed,
        "quality_score": float(best_review.get("quality_score") or 0.0),
        "quality_review_attempts": len(quality_reviews),
        "quality_critical_issue_count": critical_issue_count,
        "quality_review_issues": quality_issues,
        "quality_delivery_status": "passed",
        "mobile_repair_attempted": generation_attempts > 1,
    }


def run_main_image_a_plus_designed_module_job(
    job_context,
    generation_mode,
    layout,
    uploaded_files,
    source_integrity_reports,
    source_repair_count,
    source_integrity_warnings,
    style_reference_inputs,
    style_reference_paths,
    *,
    AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
    A_PLUS_REFERENCE_LAB_FEATURE_KEY,
    Any,
    MAIN_IMAGE_A_PLUS_MAX_FILES,
    MAIN_IMAGE_A_PLUS_MAX_SECTION_CONCURRENCY,
    ThreadPoolExecutor,
    as_completed,
    build_main_image_a_plus_designed_module_section_heights,
    build_main_image_a_plus_designed_module_section_prompt,
    build_main_image_a_plus_quality_recovery_advice,
    build_main_image_a_plus_quality_retry_instruction,
    call_openrouter_images_api,
    collect_main_image_a_plus_quality_issues,
    collect_main_image_a_plus_severe_subject_clips,
    copy_context,
    math,
    rank_main_image_a_plus_quality_review,
    review_main_image_a_plus_candidate,
    select_closest_aspect_ratio,
    set_task_progress,
    stitch_main_image_a_plus_sections,
) -> dict[str, Any]:
    """Rebuild completed ad modules one-to-one so the model cannot collage them together."""
    job_id = str(job_context.get("job_id") or "")
    feature_context = job_context.get("feature")
    strict_visual_quality = bool(
        isinstance(feature_context, dict)
        and str(feature_context.get("key") or "") == A_PLUS_REFERENCE_LAB_FEATURE_KEY
    ) or bool(job_context.get("a_plus_reference_lab_reference_paths"))
    target_width, target_height = (int(value) for value in layout["target_size"])
    section_count = len(uploaded_files)
    prepared_style_references = list(style_reference_inputs or [])[
        : max(MAIN_IMAGE_A_PLUS_MAX_FILES - 1, 0)
    ]
    prepared_style_paths = list(style_reference_paths or [])
    section_heights = build_main_image_a_plus_designed_module_section_heights(
        target_height,
        section_count,
    )
    quality_reviews: list[dict[str, Any]] = []
    best_image_url = ""
    best_review: dict[str, Any] = {}
    best_model_text = ""
    best_rank: tuple[int, int, float] | None = None
    requested_aspect_ratios: tuple[str, ...] = ()
    generation_attempts = 0
    retry_instruction = ""
    current_section_results: dict[int, dict[str, Any]] = {}
    repaired_section_indices: tuple[int, ...] = ()

    for quality_attempt in range(3):
        generation_attempts = quality_attempt + 1
        if quality_attempt == 0:
            active_section_indices = list(range(section_count))
        else:
            affected_section_indices = [
                int(value) - 1
                for value in list(quality_reviews[-1].get("affected_section_indices") or [])
                if 1 <= int(value) <= section_count
            ]
            active_section_indices = affected_section_indices or list(range(section_count))
            repaired_section_indices = tuple(index + 1 for index in active_section_indices)
        if job_id:
            set_task_progress(
                job_id,
                14 if quality_attempt == 0 else 58,
                (
                    f"正在按 {section_count} 张已设计素材逐区重构，避免整块拼贴"
                    if quality_attempt == 0
                    else f"首版未通过，正在只重做 {len(active_section_indices)} 个问题区段"
                ),
            )

        def generate_designed_section(section_index: int) -> dict[str, Any]:
            section_height = int(section_heights[section_index])
            request_aspect_ratio = select_closest_aspect_ratio(
                (target_width, section_height)
            )
            section_result = call_openrouter_images_api(
                model=str(job_context["model"]),
                prompt=build_main_image_a_plus_designed_module_section_prompt(
                    str(job_context.get("prompt") or ""),
                    layout,
                    section_index,
                    section_count,
                    section_height,
                    source_integrity_reports[section_index],
                    retry_instruction=retry_instruction,
                    style_reference_count=len(prepared_style_references),
                ),
                uploaded_files=[
                    uploaded_files[section_index],
                    *prepared_style_references,
                ],
                aspect_ratio=request_aspect_ratio,
                resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
                max_attempts=1,
            )
            generated_images = list(section_result.get("images") or [])
            if not generated_images:
                raise RuntimeError(
                    f"A+ 第 {section_index + 1} 个素材区段没有返回图片，请重试。"
                )
            return {
                "index": section_index,
                "image": str(generated_images[0]),
                "text": str(section_result.get("text") or "").strip(),
                "aspect_ratio": request_aspect_ratio,
            }

        worker_count = min(
            MAIN_IMAGE_A_PLUS_MAX_SECTION_CONCURRENCY,
            len(active_section_indices),
        )
        with ThreadPoolExecutor(max_workers=worker_count) as section_executor:
            future_map = {
                section_executor.submit(copy_context().run, generate_designed_section, section_index): section_index
                for section_index in active_section_indices
            }
            completed_count = 0
            for future in as_completed(future_map):
                section_result = future.result()
                current_section_results[int(section_result["index"])] = section_result
                completed_count += 1
                if job_id:
                    set_task_progress(
                        job_id,
                        (18 if quality_attempt == 0 else 60)
                        + math.floor((completed_count / len(active_section_indices)) * 24),
                        f"已完成本轮区段 {completed_count}/{len(active_section_indices)}",
                    )
        ordered_results = [
            current_section_results[index]
            for index in range(section_count)
        ]
        candidate_image_url = stitch_main_image_a_plus_sections(
            [str(item["image"]) for item in ordered_results],
            target_width,
            section_heights,
        )
        requested_aspect_ratios = tuple(
            str(item["aspect_ratio"]) for item in ordered_results
        )
        candidate_review = review_main_image_a_plus_candidate(
            candidate_image_url,
            layout,
            generation_mode,
            source_inputs=uploaded_files[:3],
            designed_module_pipeline=True,
            expected_section_count=section_count,
            strict_visual_quality=strict_visual_quality,
        )
        quality_reviews.append(candidate_review)
        candidate_rank = rank_main_image_a_plus_quality_review(candidate_review)
        if best_rank is None or candidate_rank > best_rank:
            best_rank = candidate_rank
            best_image_url = candidate_image_url
            best_review = candidate_review
            best_model_text = "\n".join(
                str(item.get("text") or "").strip()
                for item in ordered_results
                if str(item.get("text") or "").strip()
            )
        if bool(candidate_review.get("passed")) or not bool(candidate_review.get("reviewed")):
            break
        retry_instruction = build_main_image_a_plus_quality_retry_instruction(
            candidate_review
        )

    if not best_image_url:
        raise RuntimeError("分区重构没有返回完整 A+ 成品，请重新提交。")
    restore_lab_candidate = bool(
        isinstance(feature_context, dict)
        and str(feature_context.get("key") or "") == A_PLUS_REFERENCE_LAB_FEATURE_KEY
    )
    if not bool(best_review.get("reviewed")) and not restore_lab_candidate:
        raise RuntimeError(
            "A+ 成品质检暂时不可用；为避免交付未检查的截断图片，本次结果已拦截，请稍后重试。"
        )
    quality_passed = bool(best_review.get("passed"))
    quality_issues = collect_main_image_a_plus_quality_issues(best_review)
    quality_recovery_advice = (
        "" if quality_passed else build_main_image_a_plus_quality_recovery_advice(best_review)
    )
    severe_foreground_issues = collect_main_image_a_plus_severe_subject_clips(
        best_review
    )
    if not quality_passed and severe_foreground_issues and not restore_lab_candidate:
        issue_summary = "；".join(quality_issues[:4])
        raise RuntimeError(
            f"A+ 已逐区重构并复检 {generation_attempts} 轮，但人物或商品主体仍存在严重截断；"
            + (f"主要问题：{issue_summary}。" if issue_summary else "")
            + f"为避免交付残缺图片，本次结果已拦截。{quality_recovery_advice}"
        )
    if job_id:
        set_task_progress(
            job_id,
            84,
            "分区重构已通过检查，正在保存精确尺寸成品"
            if quality_passed
            else "已保留文字或版式问题最少的分区成品，正在准备可编辑预览",
        )
    summary = (
        f"已将 {section_count} 张完成广告模块分别重构为独立内容区，并精确合成为 "
        f"{target_width}×{target_height}px A+。每张源图只进入一个区段，避免整块搬运、重复模块和多海报拼贴。"
        + (
            f"当前是可编辑预览，仍需检查文字与版式；{quality_recovery_advice}"
            if not quality_passed
            else ""
        )
    )
    return {
        "images": [best_image_url],
        "text": "\n\n".join(part for part in (best_model_text, summary) if part),
        "channel": "Images API 原生 4K · 已设计素材分区重构",
        "requested_aspect_ratios": requested_aspect_ratios,
        "target_size": (target_width, target_height),
        "section_count": section_count,
        "section_heights": section_heights,
        "section_height": section_heights[0] if len(set(section_heights)) == 1 else None,
        "main_image_a_plus_layout_key": layout["key"],
        "main_image_a_plus_layout_label": layout["label"],
        "main_image_a_plus_mode": generation_mode,
        "generation_waves": generation_attempts,
        "max_parallel_sections": section_count,
        "generation_attempts": generation_attempts,
        "quality_repair_attempts": max(generation_attempts - 1, 0),
        "repaired_section_indices": repaired_section_indices,
        "prepared_reference_count": len(uploaded_files) + len(prepared_style_references),
        "source_integrity_checked": True,
        "source_repair_count": source_repair_count,
        "source_integrity_warnings": source_integrity_warnings,
        "a_plus_reference_lab_style_key": str(
            job_context.get("a_plus_reference_lab_style_key") or ""
        ),
        "a_plus_reference_lab_reference_names": [
            path.name for path in prepared_style_paths if path.is_file()
        ],
        "a_plus_reference_lab_reference_count": len(prepared_style_references),
        "layout_skill_id": "",
        "layout_skill_skeleton_used": False,
        "quality_reviewed": bool(best_review.get("reviewed")),
        "quality_review_passed": quality_passed,
        "quality_score": float(best_review.get("quality_score") or 0.0),
        "quality_review_attempts": len(quality_reviews),
        "quality_critical_issue_count": int(best_review.get("critical_issue_count") or 0),
        "quality_review_issues": quality_issues,
        "quality_delivery_status": "passed" if quality_passed else "needs_review",
        "quality_recovery_advice": quality_recovery_advice,
        "quality_result_restored": bool(strict_visual_quality and not quality_passed),
        "quality_severe_subject_risks": severe_foreground_issues,
        "designed_module_pipeline": True,
    }


def run_main_image_a_plus_job(
    job_context,
    *,
    AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
    A_PLUS_REFERENCE_LAB_FEATURE_KEY,
    A_PLUS_REFERENCE_LAB_MAX_PRODUCT_IMAGES,
    Any,
    MAIN_IMAGE_A_PLUS_FREE_MODES,
    MAIN_IMAGE_A_PLUS_MAX_FILES,
    MAIN_IMAGE_A_PLUS_MAX_FREE_QUALITY_ATTEMPTS,
    MAIN_IMAGE_A_PLUS_MAX_SECTION_CONCURRENCY,
    MAIN_IMAGE_A_PLUS_MODE_ELEMENT,
    MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN,
    MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST,
    MAIN_IMAGE_A_PLUS_MODE_TEMPLATE,
    MAIN_IMAGE_A_PLUS_SECTION_COUNT,
    NANO_BANANA_MODEL,
    Path,
    ThreadPoolExecutor,
    as_completed,
    build_main_image_a_plus_continuity_reference,
    build_main_image_a_plus_element_replacement_prompt,
    build_main_image_a_plus_free_prompt,
    build_main_image_a_plus_free_quality_repair_prompt,
    build_main_image_a_plus_hero_design_prompt,
    build_main_image_a_plus_quality_recovery_advice,
    build_main_image_a_plus_quality_retry_instruction,
    build_main_image_a_plus_section_prompt,
    build_main_image_a_plus_single_test_prompt,
    build_main_image_a_plus_source_integrity_instruction,
    build_main_image_a_plus_template_section_prompt,
    build_uploaded_input_from_image_url_raw,
    call_openrouter_images_api,
    collect_main_image_a_plus_quality_issues,
    collect_main_image_a_plus_severe_subject_clips,
    copy_context,
    cover_image_to_exact_size,
    get_main_image_a_plus_layout,
    is_omnia_image_outcome_unknown,
    math,
    normalize_main_image_a_plus_mode,
    normalize_uploaded_input,
    prepare_a_plus_reference_style_input,
    prepare_main_image_a_plus_reference_input,
    prepare_main_image_a_plus_sources_with_repair,
    rank_main_image_a_plus_quality_review,
    resize_image_to_target_width,
    review_main_image_a_plus_candidate,
    run_main_image_a_plus_designed_module_job,
    select_closest_aspect_ratio,
    select_main_image_a_plus_safe_aspect_ratio,
    set_task_progress,
    split_main_image_a_plus_template,
    stitch_main_image_a_plus_sections,
) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    feature_context = job_context.get("feature")
    is_reference_lab_job = bool(
        isinstance(feature_context, dict)
        and str(feature_context.get("key") or "") == A_PLUS_REFERENCE_LAB_FEATURE_KEY
    )
    strict_visual_quality = is_reference_lab_job or bool(
        job_context.get("a_plus_reference_lab_reference_paths")
    )
    generation_mode = normalize_main_image_a_plus_mode(
        str(job_context.get("main_image_a_plus_mode") or "")
    )
    layout = (
        dict(job_context["main_image_a_plus_layout"])
        if isinstance(job_context.get("main_image_a_plus_layout"), dict)
        else get_main_image_a_plus_layout(
            str(job_context.get("main_image_a_plus_layout_key") or "")
        )
    )
    target_width, target_height = layout["target_size"]
    section_heights = layout["section_heights"]
    raw_uploaded_files = list(job_context.get("uploaded_files") or [])
    source_integrity_reports: list[dict[str, Any]] = []
    source_repair_count = 0
    source_integrity_warnings: list[str] = []
    source_repair_enabled = (
        False
        if is_reference_lab_job
        else bool(job_context.get("a_plus_source_repair_enabled", True))
    )
    if generation_mode in MAIN_IMAGE_A_PLUS_FREE_MODES and source_repair_enabled:
        (
            uploaded_files,
            source_integrity_reports,
            source_repair_count,
            source_integrity_warnings,
        ) = prepare_main_image_a_plus_sources_with_repair(
            raw_uploaded_files,
            model=str(job_context.get("model") or NANO_BANANA_MODEL),
        )
    else:
        uploaded_files = [
            prepare_main_image_a_plus_reference_input(item)
            for item in raw_uploaded_files
        ]
    if generation_mode in MAIN_IMAGE_A_PLUS_FREE_MODES:
        style_reference_inputs: list[Any] = []
        style_reference_paths = [] if is_reference_lab_job else [
            Path(str(value))
            for value in list(job_context.get("a_plus_reference_lab_reference_paths") or [])
            if str(value).strip()
        ]
        available_style_slots = max(MAIN_IMAGE_A_PLUS_MAX_FILES - len(uploaded_files), 0)
        for reference_path in style_reference_paths[:available_style_slots]:
            if not reference_path.is_file():
                continue
            style_reference_inputs.append(
                prepare_main_image_a_plus_reference_input(
                    prepare_a_plus_reference_style_input(reference_path, str(layout["key"]))
                )
            )
        use_designed_module_pipeline = (
            not is_reference_lab_job
            and job_context.get("a_plus_layout_skill_skeleton") is None
            and 2 <= len(uploaded_files) <= A_PLUS_REFERENCE_LAB_MAX_PRODUCT_IMAGES
            and len(source_integrity_reports) == len(uploaded_files)
            and all(
                str(report.get("asset_role") or "") == "designed_module"
                for report in source_integrity_reports
            )
        )
        if use_designed_module_pipeline:
            return run_main_image_a_plus_designed_module_job(
                job_context=job_context,
                generation_mode=generation_mode,
                layout=layout,
                uploaded_files=uploaded_files,
                source_integrity_reports=source_integrity_reports,
                source_repair_count=source_repair_count,
                source_integrity_warnings=source_integrity_warnings,
                style_reference_inputs=style_reference_inputs,
                style_reference_paths=style_reference_paths,
            )
        generation_references = [*uploaded_files, *style_reference_inputs]
        skill_skeleton = job_context.get("a_plus_layout_skill_skeleton")
        skill_skeleton_used = False
        if (
            not is_reference_lab_job
            and skill_skeleton is not None
            and len(generation_references) < MAIN_IMAGE_A_PLUS_MAX_FILES
        ):
            generation_references.append(
                prepare_main_image_a_plus_reference_input(skill_skeleton)
            )
            skill_skeleton_used = True
        request_aspect_ratio = select_main_image_a_plus_safe_aspect_ratio((target_width, target_height))
        is_hero_design_mode = generation_mode == MAIN_IMAGE_A_PLUS_MODE_HERO_DESIGN
        if job_id:
            set_task_progress(
                job_id,
                12,
                "正在设计高商业感首屏并一次生成完整 A+ 长图"
                if is_hero_design_mode
                else "正在一次生成完整 A+ 商业长图",
            )
        source_integrity_instruction = build_main_image_a_plus_source_integrity_instruction(
            source_integrity_reports
        )
        prompt_with_source_integrity = "\n\n".join(
            part
            for part in (
                str(job_context.get("prompt") or "").strip(),
                source_integrity_instruction,
            )
            if part
        )
        generation_prompt = (
            build_main_image_a_plus_hero_design_prompt(
                prompt_with_source_integrity,
                layout,
                has_layout_skeleton=skill_skeleton_used,
                style_reference_count=len(style_reference_inputs),
            )
            if is_hero_design_mode
            else build_main_image_a_plus_free_prompt(
                prompt_with_source_integrity,
                layout,
                has_layout_skeleton=skill_skeleton_used,
                style_reference_count=len(style_reference_inputs),
                source_pool_only=is_reference_lab_job,
            )
        )
        quality_reviews: list[dict[str, Any]] = []
        best_image_url = ""
        best_model_text = ""
        best_review: dict[str, Any] = {}
        best_rank: tuple[int, int, float] | None = None
        best_output_size = (target_width, target_height)
        generation_attempts = 0
        targeted_repair_attempts = 0
        retry_instruction = ""
        for attempt_index in range(MAIN_IMAGE_A_PLUS_MAX_FREE_QUALITY_ATTEMPTS):
            generation_attempts = attempt_index + 1
            attempt_prompt = generation_prompt
            attempt_uploaded_files = generation_references
            force_strict_safe_rebuild = (
                strict_visual_quality
                and attempt_index == MAIN_IMAGE_A_PLUS_MAX_FREE_QUALITY_ATTEMPTS - 1
            )
            should_edit_previous_candidate = (
                attempt_index > 0
                and best_image_url
                and best_review
                and not force_strict_safe_rebuild
                and (not strict_visual_quality or attempt_index % 2 == 1)
            )
            if should_edit_previous_candidate:
                try:
                    candidate_repair_reference = prepare_main_image_a_plus_reference_input(
                        build_uploaded_input_from_image_url_raw(
                            best_image_url,
                            "a_plus_failed_candidate.png",
                        )
                    )
                    repair_source_references = list(uploaded_files)[
                        : MAIN_IMAGE_A_PLUS_MAX_FILES - 1
                    ]
                    attempt_uploaded_files = [
                        candidate_repair_reference,
                        *repair_source_references,
                    ]
                    attempt_prompt = build_main_image_a_plus_free_quality_repair_prompt(
                        prompt_with_source_integrity,
                        layout,
                        best_review,
                        len(repair_source_references),
                        source_pool_only=is_reference_lab_job,
                    )
                    targeted_repair_attempts += 1
                except Exception:
                    attempt_uploaded_files = generation_references
                    attempt_prompt = generation_prompt
                    if retry_instruction:
                        attempt_prompt += f"\n\n{retry_instruction}"
            elif retry_instruction:
                attempt_prompt += f"\n\n{retry_instruction}"
            if force_strict_safe_rebuild:
                attempt_uploaded_files = generation_references
                attempt_prompt += (
                    "\n\n这是 A+测试 的最后一轮安全构图重建。彻底放弃之前候选的贴边坐标和危险取景，"
                    + (
                        "只从当前用户上传素材池重新设计，不读取、不引用任何 A++ 文件夹图片或外部图片。"
                        if is_reference_lab_job
                        else "只从当前真实商品素材与风格参考重新设计。"
                    )
                    + "先建立一个远离四边的完整主视觉组：人物的脸部、头部轮廓与关键动作必须完整；所有被采用的商品、包装、胶水瓶、镜子和其他配件必须完整露出，不得有任何一部分出画。"
                    + (
                        "在保住首屏主中心的同时，把真实的商品、包装、细节效果或步骤素材分配为中段和下段的两到四个次视觉中心；每个次中心必须有独立面积、明暗反差和不同构图动作，不能全部缩成卡片。"
                        if is_reference_lab_job
                        else ""
                    )
                    + "如果同一侧曾有多个元素被切，必须降低该侧整个视觉组的尺度并整体向内移动，不能逐件补边，也不能把问题转移到另一条边。"
                    "非核心或重复的辅助素材可以不采用；凡是采用的元素就必须保持完整、清晰且与其他元素分离。上传源图本身已经缺失商品结构时，改用其他完整角度，不得展示残缺商品或凭空臆造缺失结构。"
                    "允许人物发梢、肩臂或连续环境形成专业摄影出血，但不得损伤脸部、主要头部轮廓、人物身份或动作语义。"
                    "连续背景、场景、光影、色块和纹理必须自然铺满画布四边；成品不得出现白边、黑边、标尺、箭头、安全框、尺寸文字或制作批注。"
                    "所有品牌字标、Logo 和标题必须作为完整组放在画面内侧，周围保留至少一个大写字母宽度的低干扰背景；禁止尾字或 Logo 端点进入外围裁切区域。"
                    "重新检查所有长标题和步骤正文的文本框：先降低字号再按语义换行，右对齐文字统一对齐内部栏线；任何文本框都不得延伸到画布外，禁止用超大单行标题碰撞左右边缘。"
                    "输出前按左、右、上、下四边逐项检查一遍，只返回单张完整成品。"
                )
            if job_id and attempt_index > 0:
                retry_action = (
                    "正在执行最终安全构图重建"
                    if force_strict_safe_rebuild
                    else (
                        "正在对上一候选图做定向修复"
                        if should_edit_previous_candidate
                        else "正在放弃失败版式并换构图重新生成"
                    )
                )
                set_task_progress(
                    job_id,
                    min(58 + attempt_index * 6, 70),
                    f"第 {attempt_index} 轮成品未通过，{retry_action}",
                )
            try:
                free_result = call_openrouter_images_api(
                    model=str(job_context["model"]),
                    prompt=attempt_prompt,
                    uploaded_files=attempt_uploaded_files,
                    aspect_ratio=request_aspect_ratio,
                    resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
                    max_attempts=1,
                )
            except Exception as exc:
                if is_omnia_image_outcome_unknown(exc):
                    raise
                if best_image_url:
                    break
                if attempt_index + 1 >= MAIN_IMAGE_A_PLUS_MAX_FREE_QUALITY_ATTEMPTS:
                    raise
                retry_instruction = "本轮生成接口没有返回可用成品，请保持相同素材事实约束并重新生成。"
                continue
            generated_images = list(free_result.get("images") or [])
            if not generated_images:
                if attempt_index + 1 >= MAIN_IMAGE_A_PLUS_MAX_FREE_QUALITY_ATTEMPTS:
                    break
                retry_instruction = "上一候选没有返回成品图，请重新生成一张完整的商业 A+ 长图。"
                continue
            if job_id:
                set_task_progress(job_id, 72, "正在检查设计层级、完整文字和四边安全区")
            candidate_image_url, candidate_output_size = resize_image_to_target_width(
                str(generated_images[0]),
                target_width,
            )
            candidate_layout = dict(layout)
            candidate_layout["target_size"] = candidate_output_size
            candidate_layout["section_heights"] = (candidate_output_size[1],)
            quality_review = review_main_image_a_plus_candidate(
                candidate_image_url,
                candidate_layout,
                generation_mode,
                source_inputs=uploaded_files,
                strict_visual_quality=strict_visual_quality,
                multi_visual_centers=is_reference_lab_job,
            )
            quality_reviews.append(quality_review)
            candidate_rank = rank_main_image_a_plus_quality_review(quality_review)
            if best_rank is None or candidate_rank > best_rank:
                best_rank = candidate_rank
                best_image_url = candidate_image_url
                best_model_text = str(free_result.get("text") or "").strip()
                best_review = quality_review
                best_output_size = candidate_output_size
            if bool(quality_review.get("passed")):
                break
            if not bool(quality_review.get("reviewed")):
                break
            retry_instruction = build_main_image_a_plus_quality_retry_instruction(
                quality_review,
                multi_visual_centers=is_reference_lab_job,
            )
        if not best_image_url:
            raise RuntimeError(
                "首屏设计感模式没有返回完整 A+ 成品图，请重新提交。"
                if is_hero_design_mode
                else "自由创作没有返回完整 A+ 成品图，请重新提交。"
            )
        if not bool(best_review.get("reviewed")) and not is_reference_lab_job:
            raise RuntimeError(
                "A+ 成品质检暂时不可用；为避免交付未检查的截断或低质量图片，本次结果已拦截，请稍后重试。"
            )
        quality_passed = bool(best_review.get("passed"))
        quality_issues = collect_main_image_a_plus_quality_issues(best_review)
        quality_recovery_advice = (
            "" if quality_passed else build_main_image_a_plus_quality_recovery_advice(best_review)
        )
        severe_foreground_issues = collect_main_image_a_plus_severe_subject_clips(
            best_review
        )
        if not quality_passed and severe_foreground_issues and not is_reference_lab_job:
            issue_summary = "；".join(quality_issues[:4])
            raise RuntimeError(
                f"A+ 已完成首版生成并自动定向修复 {targeted_repair_attempts} 次，"
                "但人物或商品主体仍存在严重截断；"
                + (f"主要问题：{issue_summary}。" if issue_summary else "")
                + f"为避免交付残缺图片，本次结果已拦截。{quality_recovery_advice}"
            )
        if job_id:
            set_task_progress(
                job_id,
                84,
                "整张 A+ 已通过检查，正在保存所选规格"
                if quality_passed
                else "已保留文字或版式问题最少的候选，正在准备可编辑预览",
            )
        final_image_url = best_image_url
        output_width, output_height = best_output_size
        model_text = best_model_text
        summary = (
            (
                f"已按“{layout['label']}”完成首屏商业主视觉强化，并按宽度等比适配为 {output_width}×{output_height}px A+ 长图。"
                if is_hero_design_mode
                else f"已按“{layout['label']}”一次生成，并按宽度等比适配为 {output_width}×{output_height}px 商业 A+ 长图。"
            )
            + (
                f"成品经过 {targeted_repair_attempts} 轮定向质检修复；"
                if targeted_repair_attempts
                else ""
            )
            + "全程使用整图生成与局部修复，没有拆分模块、没有生成四张局部图，也没有执行图片拼接。"
            + (
                f"当前是可编辑预览，仍需检查文字与版式；{quality_recovery_advice}"
                if not quality_passed
                else ""
            )
        )
        return {
            "images": [final_image_url],
            "text": "\n\n".join(part for part in (model_text, summary) if part),
            "channel": (
                "Images API 原生 4K · A+ 首屏设计感整图直出"
                if is_hero_design_mode
                else "Images API 原生 4K · A+ 整图直出"
            ),
            "requested_aspect_ratios": (request_aspect_ratio,),
            "target_size": best_output_size,
            "requested_target_size": (target_width, target_height),
            "section_count": 1,
            "section_heights": (output_height,),
            "section_height": output_height,
            "width_only_proportional_fit": True,
            "main_image_a_plus_layout_key": layout["key"],
            "main_image_a_plus_layout_label": layout["label"],
            "main_image_a_plus_mode": generation_mode,
            "generation_waves": 1,
            "max_parallel_sections": 1,
            "generation_attempts": generation_attempts,
            "quality_repair_attempts": targeted_repair_attempts,
            "prepared_reference_count": len(generation_references),
            "source_integrity_checked": any(
                str(report.get("status") or "") != "unknown"
                for report in source_integrity_reports
            ),
            "source_repair_count": source_repair_count,
            "source_integrity_warnings": source_integrity_warnings,
            "a_plus_reference_lab_style_key": str(
                job_context.get("a_plus_reference_lab_style_key") or ""
            ),
            "a_plus_reference_lab_reference_names": [
                path.name for path in style_reference_paths if path.is_file()
            ],
            "a_plus_reference_lab_reference_count": len(style_reference_inputs),
            "layout_skill_id": str(job_context.get("a_plus_layout_skill_id") or ""),
            "layout_skill_skeleton_used": skill_skeleton_used,
            "quality_reviewed": bool(best_review.get("reviewed")),
            "quality_review_passed": quality_passed,
            "quality_score": float(best_review.get("quality_score") or 0.0),
            "quality_review_attempts": len(quality_reviews),
            "quality_critical_issue_count": int(best_review.get("critical_issue_count") or 0),
            "quality_review_issues": quality_issues,
            "quality_delivery_status": "passed" if quality_passed else "needs_review",
            "quality_recovery_advice": quality_recovery_advice,
            "quality_result_restored": bool(strict_visual_quality and not quality_passed),
            "quality_severe_subject_risks": severe_foreground_issues,
        }
    if generation_mode == MAIN_IMAGE_A_PLUS_MODE_ELEMENT:
        template_input = job_context.get("main_image_a_plus_template")
        if template_input is None:
            raise RuntimeError("指定元素替换需要先上传并识别 1 张完整的成品 A+ 示例图。")
        replacements = [
            dict(item)
            for item in list(job_context.get("main_image_a_plus_element_replacements") or [])
            if isinstance(item, dict)
        ]
        if not replacements or len(replacements) != len(uploaded_files):
            raise RuntimeError("指定元素与替换图片的映射不完整，请重新识别并为至少一个编号上传替换图。")
        template_reference = normalize_uploaded_input(template_input)
        request_aspect_ratio = select_main_image_a_plus_safe_aspect_ratio(
            (target_width, target_height)
        )
        if job_id:
            set_task_progress(job_id, 12, f"正在按 {len(replacements)} 个编号执行指定元素替换")
        element_result = call_openrouter_images_api(
            model=str(job_context["model"]),
            prompt=build_main_image_a_plus_element_replacement_prompt(
                str(job_context.get("prompt") or ""),
                layout,
                replacements,
            ),
            uploaded_files=[template_reference, *uploaded_files],
            aspect_ratio=request_aspect_ratio,
            resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        )
        generated_images = list(element_result.get("images") or [])
        if not generated_images:
            raise RuntimeError("指定元素替换没有返回完整 A+ 成品图，请重试。")
        if job_id:
            set_task_progress(job_id, 76, "指定元素替换完成，正在适配模板原尺寸")
        final_image_url = cover_image_to_exact_size(
            str(generated_images[0]),
            target_width,
            target_height,
        )
        replaced_labels = "、".join(
            f"#{int(item.get('id') or index + 1)} {str(item.get('name') or '元素')}"
            for index, item in enumerate(replacements)
        )
        summary = (
            f"已按模板原尺寸一次生成 {target_width}×{target_height}px 成品，并完成指定元素替换：{replaced_labels}。"
            "未选择的元素、背景和版式均要求保持不变；本模式未拆分模板或拼接图片。"
        )
        return {
            "images": [final_image_url],
            "text": summary,
            "channel": "Images API 原生 4K · 指定元素整图替换",
            "requested_aspect_ratios": (request_aspect_ratio,),
            "target_size": (target_width, target_height),
            "section_count": 1,
            "section_heights": (target_height,),
            "section_height": target_height,
            "main_image_a_plus_layout_key": layout["key"],
            "main_image_a_plus_layout_label": layout["label"],
            "main_image_a_plus_mode": generation_mode,
            "generation_waves": 1,
            "max_parallel_sections": 1,
            "prepared_reference_count": len(uploaded_files),
            "replaced_element_count": len(replacements),
            "replaced_element_ids": tuple(int(item.get("id") or 0) for item in replacements),
        }
    if generation_mode == MAIN_IMAGE_A_PLUS_MODE_SINGLE_TEST:
        template_input = job_context.get("main_image_a_plus_template")
        if template_input is None:
            raise RuntimeError("一张测试需要先上传 1 张完整的成品 A+ 版式模板。")
        template_reference = normalize_uploaded_input(template_input)
        request_aspect_ratio = select_main_image_a_plus_safe_aspect_ratio(
            (target_width, target_height)
        )
        if job_id:
            set_task_progress(job_id, 12, "正在识别完整 A+ 版式并进行整图内容替换")
        single_result = call_openrouter_images_api(
            model=str(job_context["model"]),
            prompt=build_main_image_a_plus_single_test_prompt(
                str(job_context.get("prompt") or ""),
                layout,
            ),
            uploaded_files=[template_reference, *uploaded_files],
            aspect_ratio=request_aspect_ratio,
            resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        )
        generated_images = list(single_result.get("images") or [])
        if not generated_images:
            raise RuntimeError("一张测试没有返回完整 A+ 成品图，请重试。")
        if job_id:
            set_task_progress(job_id, 76, "整图生成完成，正在适配模板原尺寸")
        final_image_url = cover_image_to_exact_size(
            str(generated_images[0]),
            target_width,
            target_height,
        )
        model_text = str(single_result.get("text") or "").strip()
        summary = (
            f"已将完整模板作为统一版式参考，一次生成 1 张 {target_width}×{target_height}px A+ 成品长图。"
            "本模式未拆分模板、未生成四张局部图，也未执行任何图片拼接。"
        )
        return {
            "images": [final_image_url],
            "text": "\n\n".join(part for part in (model_text, summary) if part),
            "channel": "Images API 原生 4K · 整图套版重绘",
            "requested_aspect_ratios": (request_aspect_ratio,),
            "target_size": (target_width, target_height),
            "section_count": 1,
            "section_heights": (target_height,),
            "section_height": target_height,
            "main_image_a_plus_layout_key": layout["key"],
            "main_image_a_plus_layout_label": layout["label"],
            "main_image_a_plus_mode": generation_mode,
            "generation_waves": 1,
            "max_parallel_sections": 1,
            "prepared_reference_count": len(uploaded_files),
        }
    template_sections = (
        split_main_image_a_plus_template(
            job_context.get("main_image_a_plus_template"),
            target_width,
            section_heights,
        )
        if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE
        else []
    )

    def generate_section(
        section_index: int,
        continuity_reference: dict[str, Any] | None = None,
        continuity_reference_role: str = "",
    ) -> dict[str, Any]:
        section_height = int(section_heights[section_index])
        request_aspect_ratio = select_closest_aspect_ratio((target_width, section_height))
        section_prompt = (
            build_main_image_a_plus_template_section_prompt(
                str(job_context.get("prompt") or ""),
                layout,
                section_index,
            )
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE
            else build_main_image_a_plus_section_prompt(
                str(job_context.get("prompt") or ""),
                layout,
                section_index,
                has_previous_section_reference=continuity_reference is not None,
                continuity_reference_role=continuity_reference_role,
            )
        )
        section_uploaded_files = (
            [template_sections[section_index], *uploaded_files]
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE
            else [
                *uploaded_files,
                *([continuity_reference] if continuity_reference is not None else []),
            ]
        )
        section_result = call_openrouter_images_api(
            model=str(job_context["model"]),
            prompt=section_prompt,
            uploaded_files=section_uploaded_files,
            aspect_ratio=request_aspect_ratio,
            resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        )
        generated_images = list(section_result.get("images") or [])
        if not generated_images:
            raise RuntimeError(
                f"主图生A+第 {section_index + 1} 个模块没有返回图片，请重试。"
            )
        return {
            "index": section_index,
            "image": str(generated_images[0]),
            "text": str(section_result.get("text") or "").strip(),
            "aspect_ratio": request_aspect_ratio,
        }

    section_results: dict[int, dict[str, Any]] = {}

    def generate_sections_in_parallel(
        section_specs: list[tuple[int, dict[str, Any] | None, str]],
        progress_label: str,
        progress_start: int,
        progress_span: int,
    ) -> None:
        if not section_specs:
            return
        worker_count = min(MAIN_IMAGE_A_PLUS_MAX_SECTION_CONCURRENCY, len(section_specs))
        completed_count = 0
        with ThreadPoolExecutor(max_workers=worker_count) as section_executor:
            future_map = {
                section_executor.submit(copy_context().run, generate_section, section_index, reference, role): section_index
                for section_index, reference, role in section_specs
            }
            for future in as_completed(future_map):
                section_result = future.result()
                section_results[int(section_result["index"])] = section_result
                completed_count += 1
                if job_id:
                    set_task_progress(
                        job_id,
                        progress_start + math.floor((completed_count / len(section_specs)) * progress_span),
                        f"{progress_label} {completed_count}/{len(section_specs)}",
                    )

    if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE:
        generation_waves = 1
        max_parallel_sections = MAIN_IMAGE_A_PLUS_SECTION_COUNT
        if job_id:
            set_task_progress(job_id, 12, "正在并行替换 4 个 A+ 模板片段")
        generate_sections_in_parallel(
            [(index, None, "") for index in range(MAIN_IMAGE_A_PLUS_SECTION_COUNT)],
            "已完成套版片段",
            12,
            60,
        )
    elif len(uploaded_files) >= MAIN_IMAGE_A_PLUS_MAX_FILES:
        generation_waves = 1
        max_parallel_sections = MAIN_IMAGE_A_PLUS_SECTION_COUNT
        if job_id:
            set_task_progress(job_id, 12, "正在并行生成 4 个 A+ 连续画面片段")
        generate_sections_in_parallel(
            [(index, None, "") for index in range(MAIN_IMAGE_A_PLUS_SECTION_COUNT)],
            "已完成画面片段",
            12,
            60,
        )
    else:
        generation_waves = 2
        max_parallel_sections = MAIN_IMAGE_A_PLUS_SECTION_COUNT - 1
        if job_id:
            set_task_progress(job_id, 12, "正在生成 A+ 首屏风格锚点")
        first_section_result = generate_section(0)
        section_results[0] = first_section_result
        continuity_reference = None
        try:
            continuity_reference = build_main_image_a_plus_continuity_reference(
                str(first_section_result["image"]),
                target_width,
                int(section_heights[0]),
                base_name="a_plus_continuity_section_1.png",
            )
        except Exception:
            continuity_reference = None
        if job_id:
            set_task_progress(job_id, 32, "首屏完成，正在并行生成剩余 3 个片段")
        generate_sections_in_parallel(
            [
                (
                    index,
                    continuity_reference,
                    "previous" if index == 1 else "style_anchor",
                )
                for index in range(1, MAIN_IMAGE_A_PLUS_SECTION_COUNT)
            ],
            "已完成剩余片段",
            32,
            40,
        )

    ordered_section_results = [
        section_results[index]
        for index in range(MAIN_IMAGE_A_PLUS_SECTION_COUNT)
    ]
    section_image_urls = [str(item["image"]) for item in ordered_section_results]
    requested_aspect_ratios = [str(item["aspect_ratio"]) for item in ordered_section_results]
    section_texts = [
        f"第 {index + 1} 段：{str(item['text']).strip()}"
        for index, item in enumerate(ordered_section_results)
        if str(item.get("text") or "").strip()
    ]

    if job_id:
        set_task_progress(job_id, 76, "正在合成连续 A+ 长图")
    final_image_url = stitch_main_image_a_plus_sections(
        section_image_urls,
        target_width,
        section_heights,
    )
    if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE:
        summary = (
            "已按模板原图尺寸拆分成品模板，并行替换各片段后按原顺序无缝合成套版成品。"
            "模板仅保留版式与设计结构，原品牌、原模特、原产品和原文案均要求替换或删除。"
        )
    else:
        summary = (
            f"已按“{layout['label']}”使用原生 4K 生成连续画面，并合成为 "
            f"{target_width}×{target_height}px 成品。"
            "四个内容阶段自然衔接且不显示硬边界，视觉元素可跨阶段延伸；画面满版铺满，完整文字不会被截断。"
        )
    return {
        "images": [final_image_url],
        "text": "\n\n".join([*section_texts, summary]).strip(),
        "channel": (
            "Images API 原生 4K · 并行套版替换"
            if generation_mode == MAIN_IMAGE_A_PLUS_MODE_TEMPLATE
            else "Images API 原生 4K · 快速连续长图生成"
        ),
        "requested_aspect_ratios": tuple(requested_aspect_ratios),
        "target_size": (target_width, target_height),
        "section_count": MAIN_IMAGE_A_PLUS_SECTION_COUNT,
        "section_heights": section_heights,
        "section_height": section_heights[0] if len(set(section_heights)) == 1 else None,
        "main_image_a_plus_layout_key": layout["key"],
        "main_image_a_plus_layout_label": layout["label"],
        "main_image_a_plus_mode": generation_mode,
        "generation_waves": generation_waves,
        "max_parallel_sections": max_parallel_sections,
        "prepared_reference_count": len(uploaded_files),
    }
