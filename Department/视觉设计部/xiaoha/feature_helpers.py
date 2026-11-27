"""Support reusable model jobs, layout analysis and result processing."""

from __future__ import annotations

from typing import Any


def _normalize_layout_skill_sections(
    value,
    *,
    Any,
    _layout_skill_bbox,
    _layout_skill_ratio,
    _layout_skill_text,
    _normalize_layout_skill_elements,
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for raw_section in list(value or []) if isinstance(value, (list, tuple)) else []:
        if not isinstance(raw_section, dict):
            continue
        sections.append(
            {
                "type": _layout_skill_text(raw_section.get("type") or "content", 48),
                "height_ratio": _layout_skill_ratio(raw_section.get("height_ratio")),
                "bbox": _layout_skill_bbox(raw_section.get("bbox")),
                "alignment": _layout_skill_text(raw_section.get("alignment"), 64),
                "whitespace_ratio": _layout_skill_ratio(raw_section.get("whitespace_ratio")),
                "elements": _normalize_layout_skill_elements(raw_section.get("elements")),
            }
        )
        if len(sections) >= 12:
            break
    if not sections:
        sections = [
            {
                "type": section_type,
                "height_ratio": 0.25,
                "bbox": [0, index * 250, 1000, (index + 1) * 250],
                "alignment": "",
                "whitespace_ratio": 0.0,
                "elements": [],
            }
            for index, section_type in enumerate(
                ("hero", "selling_points", "details", "package")
            )
        ]
    ratio_total = sum(float(section.get("height_ratio") or 0) for section in sections)
    if ratio_total > 0:
        for section in sections:
            section["height_ratio"] = round(
                float(section.get("height_ratio") or 0) / ratio_total,
                4,
            )
    return sections


def _normalize_layout_skill_common(
    value,
    *,
    _layout_skill_int,
    _layout_skill_string_list,
    _layout_skill_text,
    _normalize_layout_skill_hero,
    _normalize_layout_skill_sections,
    re,
) -> dict[str, Any]:
    raw_common = dict(value or {}) if isinstance(value, dict) else {}
    raw_typography = dict(raw_common.get("typography") or {})
    raw_background = dict(raw_common.get("background") or {})
    palette = [
        color.upper()
        for color in _layout_skill_string_list(raw_background.get("palette"), 8)
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", color)
    ]
    return {
        "style": _layout_skill_text(raw_common.get("style"), 120),
        "design_strengths": _layout_skill_string_list(raw_common.get("design_strengths")),
        "hero": _normalize_layout_skill_hero(raw_common.get("hero")),
        "sections": _normalize_layout_skill_sections(raw_common.get("sections")),
        "typography": {
            "hierarchy": _layout_skill_string_list(raw_typography.get("hierarchy"), 8),
            "text_blocks": _layout_skill_int(raw_typography.get("text_blocks"), maximum=40),
            "density": _layout_skill_text(raw_typography.get("density"), 48),
            "alignment": _layout_skill_text(raw_typography.get("alignment"), 64),
            "max_title_lines": _layout_skill_int(raw_typography.get("max_title_lines"), maximum=6),
        },
        "background": {
            "palette": palette,
            "lighting": _layout_skill_text(raw_background.get("lighting"), 120),
            "decorative_language": _layout_skill_text(
                raw_background.get("decorative_language"),
                160,
            ),
            "depth": _layout_skill_text(raw_background.get("depth"), 120),
            "continuity": _layout_skill_text(raw_background.get("continuity"), 160),
        },
        "reading_flow": _layout_skill_string_list(raw_common.get("reading_flow")),
        "cross_section_rules": _layout_skill_string_list(raw_common.get("cross_section_rules")),
        "product_placement_rules": _layout_skill_string_list(
            raw_common.get("product_placement_rules")
        ),
        "anti_patterns": _layout_skill_string_list(raw_common.get("anti_patterns")),
    }


def build_a_plus_layout_analysis_prompt(
    case_inputs,
    previous_common,
    *,
    get_uploaded_input_dimensions,
    json,
) -> str:
    dimensions = [get_uploaded_input_dimensions(item) for item in case_inputs]
    dimension_text = "；".join(
        f"案例 {index + 1}={width}×{height}px"
        for index, (width, height) in enumerate(dimensions)
    )
    previous_text = json.dumps(previous_common or {}, ensure_ascii=False, separators=(",", ":"))
    if len(previous_text) > 12000:
        previous_text = previous_text[:12000]
    return (
        "你是电商 A+ 版式结构分析器。输入图片按顺序是用户认可的优秀 A+ 完整案例。"
        "只学习设计结构，不学习、复述、复制或记录案例中的具体产品、人物身份、品牌、Logo、文案、参数、价格和图片内容。"
        "逐张分析画布、首屏、视觉中心、模特/产品/Logo/标题/卖点的抽象位置，各内容区比例、留白、对齐、字体层级、文字数量与密度、背景配色、光影、装饰语言、阅读动线、跨区元素、商品区域坐标和遮挡关系。"
        "所有 bbox 使用 0 到 1000 的全画布归一化坐标 [left,top,right,bottom]；元素 type 只能使用 model、product、logo、title、selling_point、detail、package、decoration、other 等通用类型，不能输出具体内容名称。"
        "cases 必须与输入图片一一对应。common 只保留多个案例共同出现、可复用且确实优秀的设计原则；不同案例互相冲突的特点不要强行合并。"
        "如果提供了 previous_common，它是过去已沉淀的通用原则；请用本批新案例作为新证据进行增量合并，保留仍成立的原则，删除被反复证明不通用的规则，实现持续进化。"
        "严禁在 JSON 中输出 OCR 原文、品牌名、商品名、人物描述或案例内容摘要。只返回严格 JSON，不要 Markdown，不要解释。"
        f"实际图片尺寸：{dimension_text}。"
        f"previous_common={previous_text}。"
        "JSON schema："
        '{"cases":[{"case_index":1,"style":"通用风格描述","design_strengths":["结构优点"],'
        '"hero":{"height_ratio":0.32,"visual_center":[500,220],"product_position":"右下",'
        '"model_position":"左侧","text_blocks":2,"text_area_ratio":0.15,'
        '"elements":[{"type":"product","bbox":[560,80,960,390],"alignment":"右对齐","overlap":"前景"}]},'
        '"sections":[{"type":"hero","height_ratio":0.32,"bbox":[0,0,1000,320],'
        '"alignment":"不对称","whitespace_ratio":0.35,"elements":[]}],'
        '"typography":{"hierarchy":["品牌","主标题","辅助文案"],"text_blocks":6,"density":"低",'
        '"alignment":"左对齐","max_title_lines":2},'
        '"background":{"palette":["#111111","#C9A45C"],"lighting":"侧逆光",'
        '"decorative_language":"克制线条","depth":"前中后景","continuity":"背景跨区连续"},'
        '"reading_flow":["左上到右下"],"cross_section_elements":[],'
        '"product_regions":[{"type":"product","bbox":[560,80,960,390],"alignment":"右下",'
        '"overlap":"不遮挡 Logo"}]}],'
        '"common":{"style":"共同风格","design_strengths":["共同优点"],'
        '"hero":{"height_ratio":0.32,"visual_center":[500,220],"product_position":"右下",'
        '"model_position":"左侧","text_blocks":2,"text_area_ratio":0.15,"elements":[]},'
        '"sections":[{"type":"hero","height_ratio":0.32,"bbox":[0,0,1000,320],'
        '"alignment":"不对称","whitespace_ratio":0.35,"elements":[]}],'
        '"typography":{"hierarchy":["品牌","主标题","辅助文案"],"text_blocks":6,'
        '"density":"低","alignment":"左对齐","max_title_lines":2},'
        '"background":{"palette":["#111111","#C9A45C"],"lighting":"侧逆光",'
        '"decorative_language":"克制线条","depth":"前中后景","continuity":"背景跨区连续"},'
        '"reading_flow":["首屏焦点到卖点再到细节"],"cross_section_rules":["主体跨区但不形成硬分割"],'
        '"product_placement_rules":["产品完整且不被文字遮挡"],"anti_patterns":["素材堆叠"]}}'
    )


def is_hd_batch_transient_error(
    error,
    *,
    is_omnia_image_outcome_unknown,
) -> bool:
    if is_omnia_image_outcome_unknown(error):
        return False
    normalized = str(error or "").strip().lower()
    if not normalized:
        return False
    if any(
        marker in normalized
        for marker in ("invalid_input", "content not allowed", "not supported",
                       "content_filter", "image_recitation", "copyright", "protected content",
                       "provider_submit_uncertain", "查询图片任务失败", "图片任务等待超时")
    ):
        return False
    return any(
        marker in normalized
        for marker in (
            "no available channel",
            "no_available_channel",
            "system_cpu_overloaded",
            "cpu overloaded",
            "generation service is busy",
            "service is busy",
            "provider_submit_rejected",
            "http 502",
            "http 503",
            "http 504",
            "http 429",
            "timed out",
            "timeout",
            "连接失败",
        )
    )


def run_hd_batch_generate_with_retry(
    generate_once,
    prompt_text,
    retry_offset_seconds,
    *,
    HD_BATCH_TRANSIENT_MAX_ATTEMPTS,
    HD_BATCH_TRANSIENT_RETRY_DELAYS,
    is_hd_batch_transient_error,
    sys,
    time,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt_index in range(HD_BATCH_TRANSIENT_MAX_ATTEMPTS):
        try:
            return generate_once(prompt_text)
        except Exception as exc:
            last_error = exc
            if (
                attempt_index + 1 >= HD_BATCH_TRANSIENT_MAX_ATTEMPTS
                or not is_hd_batch_transient_error(exc)
            ):
                raise
            delay = (
                HD_BATCH_TRANSIENT_RETRY_DELAYS[
                    min(attempt_index, len(HD_BATCH_TRANSIENT_RETRY_DELAYS) - 1)
                ]
                + max(int(retry_offset_seconds or 0), 0)
            )
            print(
                f"⚠️ 批量高清第 {attempt_index + 1} 次生成遇到临时故障，"
                f"{delay} 秒后自动重试：{exc}",
                file=sys.stderr,
            )
            time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("批量高清生成失败，请稍后重试。")


def finalize_canvas_job_result(
    job_context,
    result,
    job_id,
    *,
    build_local_history_records,
    save_generated_images_and_record_db,
    set_task_progress,
    sys,
) -> dict[str, Any]:
    if bool(job_context.get("_defer_feature_finalize")):
        return result
    if job_id:
        set_task_progress(job_id, 88, "正在整理结果并保存历史")
    account_name = str(job_context.get("account_name") or "admin")
    fallback_history_records = build_local_history_records(
        feature=dict(job_context["feature"]),
        model=str(job_context["model"]),
        prompt=str(job_context["prompt"]),
        result=result,
        account_name=account_name,
    )
    result_text_parts = [str(result.get("text") or "").strip()]
    history_records = fallback_history_records
    if result.get("images"):
        try:
            history_records = save_generated_images_and_record_db(
                feature=dict(job_context["feature"]),
                model=str(job_context["model"]),
                prompt=str(job_context["prompt"]),
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


def merge_feature_variant_results(
    variant_results,
    variant_errors,
    requested_output_count,
) -> dict[str, Any]:
    if not variant_results:
        if variant_errors:
            raise variant_errors[0][1]
        raise RuntimeError("任务未返回任何候选结果。")

    merged = dict(variant_results[0])
    for field_name in ("images", "source_images", "captions", "outpaint_alignments"):
        merged[field_name] = [
            item
            for result in variant_results
            for item in list(result.get(field_name) or [])
        ]

    text_parts: list[str] = []
    for variant_index, result in enumerate(variant_results, start=1):
        result_text = str(result.get("text") or "").strip()
        if not result_text:
            continue
        if requested_output_count > 1:
            text_parts.append(f"候选 {variant_index}：\n{result_text}")
        else:
            text_parts.append(result_text)
    if variant_errors:
        failed_labels = "、".join(str(index) for index, _exc in variant_errors)
        text_parts.append(
            f"候选 {failed_labels} 生成失败；已保留成功返回的 {len(variant_results)} 个候选。"
        )
    merged["text"] = "\n\n".join(text_parts).strip()
    merged["requested_output_count"] = requested_output_count
    merged["completed_variant_count"] = len(variant_results)
    merged["failed_variant_count"] = len(variant_errors)
    return merged


def submit_main_image_a_plus_text_edit(
    source_image,
    point,
    replacement_text,
    font_name,
    *,
    MAIN_IMAGE_A_PLUS_FEATURE_KEY,
    NANO_BANANA_MODEL,
    build_main_image_a_plus_text_edit_prompt,
    get_feature_by_key,
    st,
    submit_feature_job,
) -> dict[str, Any]:
    normalized_source = str(source_image or "").strip()
    normalized_text = str(replacement_text or "").strip()
    normalized_font = str(font_name or "").strip() or "保持原字体风格"
    if not normalized_source:
        raise RuntimeError("没有可用于文字编辑的 A+ 成品图。")
    if not normalized_text:
        raise RuntimeError("请输入修改后的文字内容。")
    feature = get_feature_by_key(MAIN_IMAGE_A_PLUS_FEATURE_KEY)
    if feature is None:
        raise RuntimeError("主图生A+功能不存在。")
    return submit_feature_job(
        feature,
        {
            "feature": dict(feature),
            "model": NANO_BANANA_MODEL,
            "prompt": build_main_image_a_plus_text_edit_prompt(
                point,
                normalized_text,
                normalized_font,
            ),
            "uploaded_files": [],
            "output_mode": "image",
            "main_image_a_plus_text_edit": True,
            "main_image_a_plus_text_edit_source": normalized_source,
            "main_image_a_plus_text_edit_point": tuple(int(value) for value in point[:2]),
            "main_image_a_plus_text_edit_content": normalized_text,
            "main_image_a_plus_text_edit_font": normalized_font,
            "account_name": str(st.session_state.get("auth_username") or "admin"),
        },
    )


def store_completed_background_job_result(
    feature_key,
    job_info,
    result,
    *,
    A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY,
    A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY,
    HISTORY_PAGE_SIZE,
    MULTI_REFERENCE_COMPOSER_FEATURE_KEY,
    datetime,
    get_history_cache_key,
    prepare_result_for_frontend,
    set_history_visible_limit,
    st,
    store_local_history_records,
) -> None:
    job_info["status"] = "completed"
    job_info["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    job_info["progress"] = 100
    job_info["stage"] = "处理完成"
    job_info.pop("completion_pending", None)
    job_info.pop("completion_started_at", None)
    job_info.pop("completion_start_progress", None)
    if feature_key == MULTI_REFERENCE_COMPOSER_FEATURE_KEY and "multi_reference_analysis" in result:
        from Department.视觉设计部.xiaoha.multi_reference_composer import accept_analysis_result
        accept_analysis_result(st.session_state, result)
        return
    frontend_result = prepare_result_for_frontend(result)
    st.session_state.feature_results[feature_key] = frontend_result
    if feature_key == A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY and result.get("hero_reverse_batch"):
        state = st.session_state.setdefault("hero_style_reverse_state", {})
        batches = state.setdefault("batches", [])
        if not any(batch.get("job_id") == job_info.get("job_id") for batch in batches):
            batch = dict(result["hero_reverse_batch"])
            batch.update(images=list(frontend_result.get("images") or []),
                         job_id=job_info.get("job_id"),
                         label=f"第 {len(batches) + 1} 批 · {datetime.now().strftime('%m-%d %H:%M')}")
            batches.append(batch)
            state["pending_batch_reset"] = True
    if (
        feature_key == A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY
        and str(job_info.get("a_plus_first_screen_workflow_stage") or "") == "hero"
        and list(frontend_result.get("images") or [])
    ):
        hero_results = dict(st.session_state.get("a_plus_first_screen_hero_results") or {})
        hero_results[feature_key] = frontend_result
        st.session_state.a_plus_first_screen_hero_results = hero_results
    account_name = str(frontend_result.get("history_account_name") or st.session_state.get("auth_username") or "admin")
    history_records = list(frontend_result.get("history_records") or [])
    if history_records:
        store_local_history_records(account_name, feature_key, history_records)
    cache_key = get_history_cache_key(account_name, feature_key)
    st.session_state.history_records_cache.pop(cache_key, None)
    set_history_visible_limit(cache_key, HISTORY_PAGE_SIZE)


def build_infinite_canvas_image_feature_notes(
    feature_key,
    input_count,
    outpaint_settings,
    *,
    build_outpaint_extra_notes,
) -> str:
    reference_count = max(0, int(input_count) - 1)
    if feature_key == "outpaint":
        return build_outpaint_extra_notes(
            int(outpaint_settings.get("top", 0) or 0),
            int(outpaint_settings.get("bottom", 0) or 0),
            int(outpaint_settings.get("left", 0) or 0),
            int(outpaint_settings.get("right", 0) or 0),
        )
    if feature_key == "pose_change":
        return (
            "第 1 张图是当前图片节点中的主模特图，必须保持人物身份、场景、服装和画面风格。"
            f"后续 {reference_count} 张连接图片只作为姿势参考，只提取肢体动作、头部朝向、手势和重心，不得迁移参考图中的人物或背景。"
        )
    if feature_key == "scene_change":
        return (
            "第 1 张图是当前图片节点中的主模特图，必须保持人物身份、五官、服装、姿势和动作。"
            f"后续 {reference_count} 张连接图片只作为场景参考，只提取环境、空间和氛围，不得迁移参考图中的人物。"
        )
    if feature_key == "skin_tone":
        return "第 1 张图是主体图，第 2 张连接图片只作为肤色参考；只迁移肤色，其他内容全部以第 1 张图为准。"
    if feature_key == "pupil_color_change":
        return "第 1 张图是主体图，第 2 张连接图片只作为瞳孔颜色参考；只改变瞳孔颜色，眼型、眼神和其他内容保持不变。"
    if feature_key == "eye_shape_change":
        return "第 1 张图是主体图，第 2 张连接图片只作为眼型参考；只改变眼型结构，瞳孔颜色、人物身份和其他内容保持不变。"
    if feature_key == "three_view":
        return "第 1 张图是主体图，第 2 张连接图片只作为侧面角度参考；只改变拍摄角度和脸部朝向，人物身份及画面风格保持不变。"
    if feature_key == "ai_qa_image":
        return (
            f"第 1 张图是当前图片节点中的主图，另有 {reference_count} 张连接参考图。"
            "先理解图片内容和关系，再严格执行用户的文字要求，只返回 1 张最终结果图。"
        )
    return "第 1 张图是当前图片节点中的唯一待处理原图，只执行所选功能，不改变无关内容。"


def build_outpaint_extra_notes(
    top_px,
    bottom_px,
    left_px,
    right_px,
) -> str:
    active_directions = [
        f"expand upward by {top_px}px" if top_px > 0 else "",
        f"expand downward by {bottom_px}px" if bottom_px > 0 else "",
        f"expand left by {left_px}px" if left_px > 0 else "",
        f"expand right by {right_px}px" if right_px > 0 else "",
    ]
    active_directions = [item for item in active_directions if item]
    direction_text = ", ".join(active_directions)
    return (
        "This is direct, one-pass directional outpainting from the uploaded working canvas. "
        f"Extend the apparent camera canvas according to these framing instructions: {direction_text}. "
        "The four numeric directional expansion amounts define the final outer field of view: every requested side and every zero-expansion side must be followed literally, without automatic centering, balanced margins, or expansion redistribution. "
        "The pixel amounts describe how much additional visual space is needed on each side; they must never appear as blank bands, frames, overlays, or separate image regions. "
        "The uploaded working canvas already places the source photograph at the selected target coordinates. Use its clear interior as the visual authority, fully regenerate the softly blended former-edge corridors, and replace every blurred or stretched edge-color scaffold pixel with coherent new scene content in one generation. "
        "The outer scaffold is only a temporary geometry cue and must not remain in the result. Do not return transparency, empty padding, blurred padding, stretched-edge bands, or blank bands, do not paste the original back afterward, and do not reproduce the source as a visible smaller rectangle inside the generated image. "
        "The working canvas is a geometry constraint, never a collage or inset-photo design. "
        "Do not create any visible rectangle around the former image bounds, including hard seams, straight tonal changes, borders, frames, inset-photo edges, picture-in-picture layouts, or abrupt texture boundaries. "
        "Keep the original subject at the proportional position implied by the requested directional expansion, while reducing its occupancy of the final frame enough to reveal the requested new surroundings. "
        "Do not add visual space on a side where no expansion value is specified. "
        "The output must be one coherent, continuous photograph, not a collage, split-frame, multi-panel layout, or duplicated scene. "
        "If the expanded area involves the head, face, chin, forehead, hairline, ears, neck, or facial contour, the completion must remain a realistic natural human face and anatomically correct human structure. "
        "It is strictly forbidden to turn the face into a non-human face, mask-like face, cartoon face, fake face, distorted facial features, misaligned features, duplicated features, blurred face, or abstract texture. "
        "The completed face must remain the same person as in the original image, with continuous consistency in facial proportions, face shape, skin texture, skin tone, makeup, hairstyle, expression, apparent age, and real photographic quality. "
        "Preserve the original subject identity, facial features, pose, clothing, details, composition, and sharpness as closely as possible while generating the larger continuous frame. "
        "The newly expanded area must remain sharp, high-definition, and detailed, matching the focus and texture clarity of the original photo. "
        "Do not apply blur, haze, soft-focus, low-resolution texture, smeared details, over-smoothing, or feathered softness to either the original image or the new expanded area. "
        "Every former image boundary must disappear through coherent scene generation, not through copy-paste, rectangular compositing, blurring, or smudging. "
        "Reconstruct both sides of every former boundary together and globally harmonize exposure, white balance, contrast, saturation, sharpness, texture scale, focus falloff, grain, and noise across the whole frame; there must be no detail-frequency or color step at the old edge. "
        "A broad transition corridor immediately inside every expanded former edge must be regenerated together with the new outer area; this is required whenever a person, limb, garment, hair, furniture, or object crosses the former edge. The interior away from that corridor remains the visual authority, but exact pixel locking must never create a visible rectangle. "
        "Never end an arm, hand, torso, garment, hair mass, furniture edge, or other continuous structure at the former boundary and restart a different version in the expanded area. There must be no straight horizontal or vertical join through the person or scene. "
        "Never stretch, smear, mirror, tile, clone, or repeat the border pixels of the original image. "
        "For left or right expansion on portrait/selfie/model photos, the newly expanded side margins should primarily be natural background continuation: room wall, furniture, shadows, lighting, depth, and environmental texture. "
        "Do not place any extra hands, arms, sleeves, shoulders, chest, torso fragments, skin patches, hair fragments, duplicate face, duplicate person, duplicate clothing, or cropped body parts in the new side margins. "
        "If the original image already contains a hand, arm, sleeve, or clothing edge near a border, do not mirror, clone, stretch, or continue it into the expanded blank margin; keep the original body part only inside the original image area and complete the new margin as background unless a single anatomically correct continuation is unavoidable. "
        "The result must contain exactly one main person, with no repeated limbs and no duplicated subject fragments. "
        "The outpainted result must be visually seamless and avoid rectangular joins, breaks, repeated textures, stretched deformation, blur, softness, or obvious AI-generated artifacts."
    )
