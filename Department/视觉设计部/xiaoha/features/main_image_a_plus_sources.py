"""Analyze and repair the source images used for A+ generation."""

from __future__ import annotations

from typing import Any


def analyze_main_image_a_plus_mobile_element_inventory(
    source_input,
    *,
    Any,
    DEFAULT_ASPECT_RATIO,
    MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
    _extract_strict_json_object,
    call_openrouter,
    get_uploaded_input_dimensions,
    normalize_main_image_a_plus_element_bbox,
) -> list[dict[str, Any]]:
    source_size = get_uploaded_input_dimensions(source_input)
    response = call_openrouter(
        model=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        prompt=(
            "你是电商 A+ 手机端重排前的完整元素清点器。请从上到下盘点这张电脑端 A+ 成品中的独立语义元素，"
            "包括每一个模特及其首饰配件、商品、包装盒、瓶子、刷子、Logo、品牌名、标题、正文、卖点、参数、图标、徽章、"
            "图片窗口、局部特写、花束与其他装饰、带文字或商品语义的背景内容。相同元素重复出现时必须记录真实出现次数；"
            "不同文案块、不同产品、不同图片窗口必须分开列出。不得忽略画布四角、边缘、底部或背景中的小元素。"
            "每个元素还要返回 retention_priority：人物、商品、包装、Logo、文字、参数、步骤图、效果图、眼部特写和有品牌意义的装饰为 critical；"
            "仅用于铺满画面的纯背景、环境延伸、无文字纹理或不承载信息的小装饰为 flexible_background。"
            "同时返回 crop_policy：文字、Logo、商品和图形使用 full_element；摄影窗口允许在保留完整脸部、眼睛、商品和动作语义的前提下使用 photo_recrop_allowed；"
            "纯背景使用 background_crop_allowed。不得把人物、商品或文字误判成可裁背景。"
            "对每个标题、正文、卖点、参数、Logo、品牌名和包装上的可读文字，必须在 verbatim_text 中逐字转录原文，保留原始大小写、标点、数字、单位和行顺序，不得概括或改写。"
            "按电脑端从上到下、同一高度从左到右的阅读顺序返回元素，并在 reading_order 中返回从 1 开始的顺序号。"
            "每个元素必须返回它每一次出现的完整外接框 regions，坐标使用 0 到 1000 的归一化整数 [left,top,right,bottom]，"
            "外接框必须包含元素全部可见像素，不能只框局部。"
            "只返回严格 JSON，不要 Markdown，不要解释。JSON 格式："
            '{"elements":[{"name":"Adapt to Your Skin Tone 卖点","type":"text","count":1,'
            '"description":"完整英文卖点文字","verbatim_text":"Adapt to Your Skin Tone",'
            '"retention_priority":"critical","crop_policy":"full_element",'
            '"reading_order":1,"regions":[[80,120,420,190]]}]}'
        ),
        uploaded_files=[source_input],
        output_mode="text",
        aspect_ratio=DEFAULT_ASPECT_RATIO,
    )
    payload = _extract_strict_json_object(
        str(response.get("text") or ""),
        "手机端适配没有识别到电脑端元素清单。",
    )
    normalized_elements: list[dict[str, Any]] = []
    for index, raw_element in enumerate(list(payload.get("elements") or []), start=1):
        if not isinstance(raw_element, dict):
            continue
        name = str(raw_element.get("name") or "").strip()[:160]
        if not name:
            continue
        try:
            count = max(int(raw_element.get("count") or 1), 1)
        except Exception:
            count = 1
        raw_regions = raw_element.get("regions") or raw_element.get("bboxes") or raw_element.get("bbox") or []
        if isinstance(raw_regions, dict) or (
            isinstance(raw_regions, (list, tuple))
            and len(raw_regions) >= 4
            and not isinstance(raw_regions[0], (list, tuple, dict))
        ):
            raw_regions = [raw_regions]
        regions = [
            bbox
            for bbox in (
                normalize_main_image_a_plus_element_bbox(raw_bbox, source_size)
                for raw_bbox in list(raw_regions or [])
            )
            if bbox is not None
        ]
        count = max(count, len(regions) or 1)
        try:
            reading_order = max(int(raw_element.get("reading_order") or index), 1)
        except Exception:
            reading_order = index
        retention_priority = str(raw_element.get("retention_priority") or "critical").strip().lower()
        if retention_priority not in {"critical", "flexible_background"}:
            retention_priority = "critical"
        crop_policy = str(raw_element.get("crop_policy") or "full_element").strip().lower()
        if crop_policy not in {
            "full_element",
            "photo_recrop_allowed",
            "background_crop_allowed",
        }:
            crop_policy = "full_element"
        normalized_elements.append(
            {
                "name": name,
                "type": str(raw_element.get("type") or "other").strip()[:48],
                "count": count,
                "description": str(raw_element.get("description") or "").strip()[:240],
                "verbatim_text": str(
                    raw_element.get("verbatim_text") or raw_element.get("text") or ""
                ).strip()[:800],
                "retention_priority": retention_priority,
                "crop_policy": crop_policy,
                "reading_order": reading_order,
                "regions": regions,
            }
        )
        if index >= 80:
            break
    if not normalized_elements:
        raise RuntimeError("手机端适配没有识别到电脑端元素清单，请重试。")
    return normalized_elements


def format_main_image_a_plus_mobile_element_inventory(
    elements,
    *,
    json,
) -> str:
    lines = []
    for index, element in enumerate(list(elements or []), start=1):
        name = str(element.get("name") or f"元素 {index}").strip()
        description = str(element.get("description") or "").strip()
        verbatim_text = str(element.get("verbatim_text") or "").strip()
        retention_priority = str(element.get("retention_priority") or "critical").strip()
        crop_policy = str(element.get("crop_policy") or "full_element").strip()
        try:
            reading_order = max(int(element.get("reading_order") or index), 1)
        except Exception:
            reading_order = index
        try:
            element_count = max(int(element.get("count") or len(list(element.get("regions") or [])) or 1), 1)
        except Exception:
            element_count = 1
        line = (
            f"{index}. {name}（阅读顺序 {reading_order}，出现 {element_count} 处，"
            f"保留级别 {retention_priority}，裁切策略 {crop_policy}）"
        )
        regions = list(element.get("regions") or [])
        if regions:
            line += "；电脑端完整外接框=" + json.dumps(regions, ensure_ascii=False, separators=(",", ":"))
        if description:
            line += f"：{description}"
        if verbatim_text:
            line += "；逐字锁定原文=" + json.dumps(verbatim_text, ensure_ascii=False)
        lines.append(line)
    if not lines:
        return ""
    return "电脑端元素清单（这是最低保留清单，不代表可以忽略清单外的可见元素）：\n" + "\n".join(lines)


def analyze_main_image_a_plus_source_integrity(
    source_inputs,
    *,
    DEFAULT_ASPECT_RATIO,
    MAIN_IMAGE_A_PLUS_MAX_FILES,
    MAIN_IMAGE_A_PLUS_SOURCE_INTEGRITY_MODEL,
    _extract_strict_json_object,
    call_openrouter,
) -> list[dict[str, Any]]:
    """Detect source crops before they are propagated into an A+ composition."""
    normalized_inputs = list(source_inputs or [])[:MAIN_IMAGE_A_PLUS_MAX_FILES]
    default_reports = [
        {
            "image_index": index,
            "status": "unknown",
            "asset_role": "unknown",
            "intentional_crop": False,
            "cropped_sides": [],
            "content_types": [],
            "repairability": "unknown",
            "reference_image_indices": [],
            "confidence": 0.0,
            "reason": "",
        }
        for index in range(1, len(normalized_inputs) + 1)
    ]
    if not normalized_inputs:
        return default_reports
    try:
        response = call_openrouter(
            model=MAIN_IMAGE_A_PLUS_SOURCE_INTEGRITY_MODEL,
            prompt=(
                "你是电商 A+ 生成前的源图完整性检查器。按输入顺序逐张判断图片中的有效主体是否在原始拍摄边界之外已经缺失。"
                "先判断 asset_role：raw_asset 是单纯人像、商品、包装或素材照；designed_module 是已包含标题、卖点、参数、卡片、对比或复合排版的完成广告模块。"
                "只有当人物、头发、肢体、服装、商品、包装、Logo、文字、参数或有语义装饰明显在画布边缘被切断，且结构应继续延伸到画外时，才标记 cropped；"
                "正常的近景构图、纯背景满版、完整主体贴近边缘但轮廓未缺失，不得误判为 cropped。"
                "对 designed_module，图片窗口内的人像特写、肩臂或头发出血、商品纹理特写通常是故意裁切，intentional_crop=true 且应判定 complete；"
                "只有整个模块画布把半个字、未完结的卡片、被斩断的 Logo/包装/参数组直接切在外边界上，才标记 cropped。"
                "cropped_sides 只能使用 top、bottom、left、right。content_types 只能使用 background、person、face、hair、clothing、product、package、logo、text、parameter、decoration。"
                "repairability 只能使用 safe_auto、reference_required、unrecoverable：纯背景、环境、头发或服装外缘通常可 safe_auto；"
                "商品结构、人脸、包装、Logo、文字和参数缺失时至少需要其他完整参考图，使用 reference_required；若没有任何可见依据且不能真实恢复则使用 unrecoverable。"
                "reference_image_indices 只能列出确实属于同一人物身份或同一商品 SKU，并清晰显示缺失区域的其他输入图编号；不能因为品类相同、风格相似或都是模特就当成补齐参考。"
                "confidence 使用 0 到 1。只返回严格 JSON，不要 Markdown。格式："
                '{"images":[{"image_index":1,"asset_role":"raw_asset|designed_module","status":"complete|cropped","intentional_crop":false,"cropped_sides":["top"],'
                '"content_types":["person"],"repairability":"safe_auto|reference_required|unrecoverable",'
                '"reference_image_indices":[2],"confidence":0.92,"reason":"头发轮廓在顶部被画布切断"}]}'
            ),
            uploaded_files=normalized_inputs,
            output_mode="text",
            aspect_ratio=DEFAULT_ASPECT_RATIO,
        )
        payload = _extract_strict_json_object(
            str(response.get("text") or ""),
            "A+ 源图完整性检查没有返回有效结果。",
        )
    except Exception as exc:
        error_text = str(exc).strip()[:240]
        for report in default_reports:
            report["analysis_error"] = error_text
        return default_reports

    valid_sides = {"top", "bottom", "left", "right"}
    valid_types = {
        "background",
        "person",
        "face",
        "hair",
        "clothing",
        "product",
        "package",
        "logo",
        "text",
        "parameter",
        "decoration",
    }
    reports_by_index = {int(item["image_index"]): item for item in default_reports}
    for raw_report in list(payload.get("images") or []):
        if not isinstance(raw_report, dict):
            continue
        try:
            image_index = int(raw_report.get("image_index") or 0)
        except Exception:
            continue
        if image_index not in reports_by_index:
            continue
        status = str(raw_report.get("status") or "unknown").strip().lower()
        if status not in {"complete", "cropped"}:
            status = "unknown"
        asset_role = str(raw_report.get("asset_role") or "unknown").strip().lower()
        if asset_role not in {"raw_asset", "designed_module"}:
            asset_role = "unknown"
        cropped_sides = [
            str(side).strip().lower()
            for side in list(raw_report.get("cropped_sides") or [])
            if str(side).strip().lower() in valid_sides
        ]
        content_types = [
            str(content_type).strip().lower()
            for content_type in list(raw_report.get("content_types") or [])
            if str(content_type).strip().lower() in valid_types
        ]
        repairability = str(raw_report.get("repairability") or "unknown").strip().lower()
        if repairability not in {"safe_auto", "reference_required", "unrecoverable"}:
            repairability = "unknown"
        try:
            confidence = max(0.0, min(float(raw_report.get("confidence") or 0.0), 1.0))
        except Exception:
            confidence = 0.0
        reference_image_indices: list[int] = []
        for raw_index in list(raw_report.get("reference_image_indices") or []):
            try:
                reference_index = int(raw_index)
            except Exception:
                continue
            if reference_index in reports_by_index and reference_index != image_index:
                reference_image_indices.append(reference_index)
        reports_by_index[image_index].update(
            {
                "status": status,
                "asset_role": asset_role,
                "intentional_crop": bool(raw_report.get("intentional_crop")),
                "cropped_sides": list(dict.fromkeys(cropped_sides)),
                "content_types": list(dict.fromkeys(content_types)),
                "repairability": repairability,
                "reference_image_indices": list(dict.fromkeys(reference_image_indices)),
                "confidence": confidence,
                "reason": str(raw_report.get("reason") or "").strip()[:300],
            }
        )
    return [reports_by_index[index] for index in sorted(reports_by_index)]


def repair_main_image_a_plus_source_crop(
    source_input,
    report,
    *,
    model,
    supporting_references,
    AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
    MAIN_IMAGE_A_PLUS_SOURCE_REPAIR_EDGE_RATIO,
    NANO_BANANA_MODEL,
    Path,
    build_outpaint_source_canvas,
    build_outpaint_source_framing_instruction,
    call_openrouter_images_api,
    crop_outpaint_result_to_selected_region,
    get_outpaint_target_aspect_ratio,
    get_outpaint_target_canvas_size,
    get_uploaded_input_dimensions,
    get_uploaded_input_name,
    load_image_bytes_from_url,
    normalize_uploaded_input,
    prepare_main_image_a_plus_reference_input,
    sanitize_file_name,
) -> dict[str, Any]:
    """Outpaint only the source edges confirmed as truncated by the integrity pass."""
    source_width, source_height = get_uploaded_input_dimensions(source_input)
    cropped_sides = set(str(side).strip().lower() for side in list(report.get("cropped_sides") or []))
    horizontal_extension = max(24, int(round(source_width * MAIN_IMAGE_A_PLUS_SOURCE_REPAIR_EDGE_RATIO)))
    vertical_extension = max(24, int(round(source_height * MAIN_IMAGE_A_PLUS_SOURCE_REPAIR_EDGE_RATIO)))
    top_px = vertical_extension if "top" in cropped_sides else 0
    bottom_px = vertical_extension if "bottom" in cropped_sides else 0
    left_px = horizontal_extension if "left" in cropped_sides else 0
    right_px = horizontal_extension if "right" in cropped_sides else 0
    if top_px + bottom_px + left_px + right_px <= 0:
        return normalize_uploaded_input(source_input)

    transition_canvas = build_outpaint_source_canvas(
        source_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    reference_inputs = [
        prepare_main_image_a_plus_reference_input(item)
        for item in list(supporting_references or [])[:3]
    ]
    target_width, target_height = get_outpaint_target_canvas_size(
        source_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    content_types = "、".join(str(value) for value in list(report.get("content_types") or [])) or "主体边缘"
    support_note = (
        f"第 2 张起共 {len(reference_inputs)} 张图片只用于核对同一人物或商品在缺失区域的真实结构、颜色、材质与细节；"
        "不得复制这些参考图的背景、构图、文字或无关内容。"
        if reference_inputs
        else "没有额外结构参考，只允许补齐从现有边缘能够自然连续推断的背景、头发、服装或环境，不得臆造 Logo、文字、参数或商品结构。"
    )
    repair_prompt = (
        "这是 A+ 素材进入排版前的源图边缘补齐任务。第 1 张是已经放入扩展画布的唯一原始素材，原图内部全部像素是事实依据。"
        f"经检查，原图的 {content_types} 在 {','.join(sorted(cropped_sides))} 边缘被截断。"
        f"请只补齐这些缺失方向，最终形成完整的 {target_width}×{target_height}px 连续画面。"
        "保持原图内部的人物身份、脸部、商品 SKU、包装、Logo、文字、颜色、材质、比例、角度、透视和光线不变；"
        "不得移动、缩放、重绘或替换原图中已经完整可见的内容。补齐区域必须与原边缘自然连续，不得出现边框、模糊带、拉伸纹理、镜像、重复主体或矩形接缝。"
        f"{support_note}"
        + build_outpaint_source_framing_instruction(
            source_input,
            top_px,
            bottom_px,
            left_px,
            right_px,
        )
        + "只返回一张补齐后的完整素材，不返回说明、对比图或多个版本。"
    )
    repair_result = call_openrouter_images_api(
        model=str(model or NANO_BANANA_MODEL),
        prompt=repair_prompt,
        uploaded_files=[transition_canvas, *reference_inputs],
        aspect_ratio=get_outpaint_target_aspect_ratio(
            source_input,
            top_px,
            bottom_px,
            left_px,
            right_px,
        ),
        resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        max_attempts=1,
    )
    repaired_images = list(repair_result.get("images") or [])
    if not repaired_images:
        raise RuntimeError("源图智能补齐没有返回图片。")
    normalized_url = crop_outpaint_result_to_selected_region(
        str(repaired_images[0]),
        source_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    repaired_bytes, repaired_mime_type = load_image_bytes_from_url(normalized_url)
    source_name = Path(get_uploaded_input_name(source_input) or "a_plus_source").stem
    return {
        "data": repaired_bytes,
        "name": f"{sanitize_file_name(source_name)}_a_plus_completed.png",
        "type": repaired_mime_type or "image/png",
    }


def prepare_main_image_a_plus_sources_with_repair(
    source_inputs,
    *,
    model,
    Any,
    MAIN_IMAGE_A_PLUS_MAX_FILES,
    MAIN_IMAGE_A_PLUS_MAX_SOURCE_REPAIRS,
    MAIN_IMAGE_A_PLUS_SOURCE_REPAIR_MIN_CONFIDENCE,
    analyze_main_image_a_plus_source_integrity,
    prepare_main_image_a_plus_reference_input,
    repair_main_image_a_plus_source_crop,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, list[str]]:
    """Prepare A+ references, repairing confident source-edge truncation when truthful."""
    raw_inputs = list(source_inputs or [])[:MAIN_IMAGE_A_PLUS_MAX_FILES]
    analysis_inputs = [prepare_main_image_a_plus_reference_input(item) for item in raw_inputs]
    reports = analyze_main_image_a_plus_source_integrity(analysis_inputs)
    repaired_inputs: list[Any] = []
    warnings: list[str] = []
    repair_count = 0
    sensitive_types = {"face", "product", "package", "logo", "text", "parameter"}
    for source_index, source_input in enumerate(raw_inputs):
        report = reports[source_index] if source_index < len(reports) else {}
        status = str(report.get("status") or "unknown")
        confidence = float(report.get("confidence") or 0.0)
        if status != "cropped" or confidence < MAIN_IMAGE_A_PLUS_SOURCE_REPAIR_MIN_CONFIDENCE:
            repaired_inputs.append(source_input)
            continue
        content_types = set(str(value) for value in list(report.get("content_types") or []))
        repairability = str(report.get("repairability") or "unknown")
        asset_role = str(report.get("asset_role") or "unknown")
        matched_reference_indices = {
            int(value)
            for value in list(report.get("reference_image_indices") or [])
            if str(value).strip().isdigit()
        }
        supporting_references = [
            raw_inputs[reference_index - 1]
            for reference_index in sorted(matched_reference_indices)
            if 1 <= reference_index <= len(raw_inputs)
            and reference_index != source_index + 1
        ]
        needs_reference = bool(content_types & sensitive_types) or repairability == "reference_required"
        designed_text_or_brand_crop = asset_role == "designed_module" and bool(
            content_types & {"logo", "text", "parameter"}
        )
        cannot_truthfully_repair = (
            repairability == "unrecoverable"
            or designed_text_or_brand_crop
            or (needs_reference and not supporting_references)
        )
        if cannot_truthfully_repair:
            reason = str(report.get("reason") or "主体关键结构已在源图中缺失")
            if source_index == 0 and asset_role != "designed_module":
                raise RuntimeError(
                    f"检测到第 1 张核心素材本身已截断（{reason}），且没有其他完整参考图可以真实补齐。"
                    "请补充同一商品/人物的完整图片后再生成，系统不会猜造商品结构、Logo 或文字。"
                )
            report["repair_status"] = "preserved_unrepaired"
            warnings.append(
                f"第 {source_index + 1} 张素材存在无法可靠补齐的截断，已保留原图并仅使用其完整可见内容：{reason}"
            )
            repaired_inputs.append(source_input)
            continue
        if repair_count >= MAIN_IMAGE_A_PLUS_MAX_SOURCE_REPAIRS:
            warnings.append(f"第 {source_index + 1} 张素材检测到截断，但已达到单次自动补齐上限。")
            repaired_inputs.append(source_input)
            continue
        try:
            repaired_input = repair_main_image_a_plus_source_crop(
                source_input,
                report,
                model=model,
                supporting_references=supporting_references if needs_reference else [],
            )
        except Exception as exc:
            if source_index == 0 and needs_reference and asset_role != "designed_module":
                raise RuntimeError(f"第 1 张核心素材智能补齐失败：{exc}") from exc
            report["repair_status"] = "preserved_unrepaired"
            warnings.append(f"第 {source_index + 1} 张素材补齐失败，已保留原图并限制使用完整可见区域：{exc}")
            repaired_inputs.append(source_input)
        else:
            report["repair_status"] = "repaired"
            repair_count += 1
            repaired_inputs.append(repaired_input)
    return (
        [prepare_main_image_a_plus_reference_input(item) for item in repaired_inputs],
        reports,
        repair_count,
        warnings,
    )


def build_main_image_a_plus_source_integrity_instruction(reports) -> str:
    designed_modules = [
        report
        for report in list(reports or [])
        if str(report.get("asset_role") or "") == "designed_module"
    ]
    repaired = [
        report
        for report in list(reports or [])
        if str(report.get("repair_status") or "") == "repaired"
    ]
    preserved_unrepaired = [
        report
        for report in list(reports or [])
        if str(report.get("repair_status") or "") == "preserved_unrepaired"
    ]
    if not designed_modules and not repaired and not preserved_unrepaired:
        return ""
    instructions = ["源图完整性预处理（含素材角色分类）："]
    if designed_modules:
        designed_indices = "、".join(
            str(int(report.get("image_index") or 0)) for report in designed_modules
        )
        instructions.append(
            f"第 {designed_indices} 张是已排版的广告/A+ 模块，不是待扣图的单一商品素材。"
            "应学习其品牌色、字体气质、主次比例和已经完整可见的内容组，再统一重组；"
            "不得把模块中的人像特写、头发/肩臂出血或商品微距特写误当成必须补出完整全身/全物。"
            "内容预算是硬上限：第 1 张优先只提取 1 个首屏主视觉组；第 2 张最多提取 2 个最强产品证据组；第 3 张及之后每张最多提取 1 个完整证据组，全图支撑证据组总数不得超过 3 个。"
            "禁止把任何一张方形/矩形已设计稿连同其整片背景、边框和全部文字当成一个大矩形直接搬进长图；必须拆成完整语义组后重新建立尺度、留白和对齐。"
            "全图最多保留 5 个主文字组（含首屏标题和底部品牌收尾）；重复口号、环绕装饰字、次要标签和低优先级说明必须主动取舍，不得为了‘全部用上’而牺牲设计层级。"
        )
    if repaired:
        repaired_summary = "；".join(
            f"第 {int(report.get('image_index') or 0)} 张已补齐 {','.join(list(report.get('cropped_sides') or []))} 边缘"
            for report in repaired
        )
        instructions.append(
            f"{repaired_summary}。补齐图只恢复原始画面之外的缺失上下文；"
            "原图内部以及其他完整参考图仍是商品、人物、Logo、文字与参数的最高事实依据。"
        )
    if preserved_unrepaired:
        preserved_indices = "、".join(
            str(int(report.get("image_index") or 0)) for report in preserved_unrepaired
        )
        instructions.append(
            f"第 {preserved_indices} 张存在无法安全猜补的外边界截断，原图仍保留作为参考；"
            "只能采用其完整可见的人物、商品、文字或参数组，不得复制原图边界上的半个字、半个卡片或猜造缺失结构。"
        )
    instructions.append(
        "不得把补齐区域或截断边界中无法由参考图验证的猜测当成新的商品卖点或结构细节。"
    )
    return "".join(instructions)
