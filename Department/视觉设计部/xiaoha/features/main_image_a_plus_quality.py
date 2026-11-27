"""Evaluate A+ candidate quality and build repair instructions."""

from __future__ import annotations

from typing import Any


def review_main_image_a_plus_candidate(
    candidate_image,
    layout,
    mode,
    source_inputs,
    expected_element_inventory,
    designed_module_pipeline,
    expected_section_count,
    strict_visual_quality,
    multi_visual_centers,
    *,
    DEFAULT_ASPECT_RATIO,
    MAIN_IMAGE_A_PLUS_MAX_FILES,
    MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT,
    MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT,
    MAIN_IMAGE_A_PLUS_QUALITY_REVIEW_MODEL,
    _extract_strict_json_object,
    call_openrouter,
    detect_main_image_a_plus_outer_blank_borders,
    is_main_image_a_plus_permitted_photographic_bleed_issue,
    load_image_bytes_from_url,
    prepare_main_image_a_plus_reference_input,
    re,
) -> dict[str, Any]:
    """Use a lightweight vision pass to reject clipped, incomplete, or weak A+ results."""
    target_width, target_height = (int(value) for value in layout["target_size"])
    mobile_screen_count = int(
        layout.get("mobile_screen_count")
        or max(round(target_height / MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT), 1)
    )
    text_margin_x = int(layout.get("text_margin_x") or round(target_width * 0.08))
    text_margin_y = int(layout.get("text_margin_y") or round(target_height * 0.04))
    is_mobile = str(mode or "").strip() == MAIN_IMAGE_A_PLUS_MODE_MOBILE_ADAPT
    try:
        candidate_bytes, candidate_mime_type = load_image_bytes_from_url(candidate_image)
        candidate_reference = prepare_main_image_a_plus_reference_input(
            {
                "data": candidate_bytes,
                "name": "a_plus_candidate.png",
                "type": candidate_mime_type,
            }
        )
        detected_outer_border_issues = detect_main_image_a_plus_outer_blank_borders(
            candidate_bytes
        )
        comparison_inputs = list(source_inputs or [])[: max(MAIN_IMAGE_A_PLUS_MAX_FILES - 1, 1)]
        comparison_inputs.append(candidate_reference)
        source_reference_count = max(len(comparison_inputs) - 1, 0)
        source_note = (
            f"前 {len(comparison_inputs) - 1} 张图是电脑端原稿，最后 1 张图是待验收的手机端成品。"
            if is_mobile and len(comparison_inputs) > 1
            else (
                f"前 {len(comparison_inputs) - 1} 张图是真实商品与品牌参考，最后 1 张图是待验收的 A+ 成品；需要同时检查商品与品牌一致性。"
                if len(comparison_inputs) > 1
                else "唯一输入图是待验收的 A+ 成品。"
            )
        )
        source_truth_note = (
            "逐一对照前面的全部真实源图：候选里每一个可识别的人物、五官、商品、包装、配件、工具、花朵、徽章、图标、认证、Logo、参数和文案都必须能在源图中找到明确依据。"
            "纯背景、抽象色块、渐变、无语义纹理、光影和投影可以新增；除此之外，任何源图中不存在、由不同源图拼成、或把残缺对象猜测补全的可识别内容都必须写入 invented_elements 并判定不通过。"
            if strict_visual_quality and len(comparison_inputs) > 1
            else ""
        )
        inventory_note = str(expected_element_inventory or "").strip()
        designed_module_note = (
            f"当前候选是由 {max(int(expected_section_count or 0), 1)} 张完成广告模块一对一分区重构后的长图。"
            "允许存在多个连续内容区，但每个源图只能贡献一个区，不能在不同区重复；不要仅因存在分区就判为拼贴。"
            "只有候选明显保留了源图的旧画布外框、整张矩形截图、全部原模块内容，或同一源模块被重复搬运时，才写入‘整块搬运’。"
            "候选中的每一处可读文案都必须能在源图中找到清晰完整的逐字依据；新增口号、改写句子、近似品牌字或臆造参数必须写入 text_mismatches。"
            "同时在 affected_section_indices 返回所有需要重做的区段编号，编号从上到下由 1 开始；局部问题只返回对应区段，全局问题才返回全部区段。"
            if designed_module_pipeline
            else ""
        )
        visual_center_review_note = (
            "视觉上必须沿长图纵向形成一个略占优势的首屏主中心，以及分布在中段、下段的两到四个次视觉中心；"
            "每个次中心都要有足够面积、清晰主体、独立明暗或色彩反差和不同构图动作，不能只是首屏旁边的小缩略图或普通说明卡。"
            "不得把全部高价值素材集中在顶部；如果中段或下段只剩大片空背景、同尺寸文字卡或弱小信息点，content_richness_score 和 commercial_design_score 都不得高于 6。"
            if multi_visual_centers
            else "视觉上必须清楚形成背景氛围层、中景信息层和前景商品或人物层，主视觉与辅助内容要有显著尺度差，且至少有一处有目的的叠压、景深或光影连接。"
        )
        strict_visual_note = (
            "当前是 A+测试 的严格验收：背景、场景、色块、光影或纹理必须连续触达四边；任何白边、黑边、页边距、相框、空白边带、"
            "安全框、尺寸文字、坐标、标尺、辅助线、箭头或制作批注都必须一票否决。"
            f"{visual_center_review_note}"
            "如果整图主要由同尺寸、同底色、同圆角的浅色卡片机械堆叠，或各区域明暗、尺度、空间关系几乎一致，depth_score 不得高于 6，并判定不通过。"
            "内容丰富度必须来自真实素材的分级编排：应有多个纵向分布、大小错落且角色不同的视觉中心，以及贯穿全图的背景或图形关系；"
            "合理使用满版视觉、局部特写、错位图片窗口、横向信息带、前后遮挡、跨区色块、投影或景深，但不能要求不存在的内容。"
            "如果可用源图足够却只剩一张主图加大片无目的空背景，或全图只有一到两个弱小信息点，content_richness_score 不得高于 6；"
            "如果依靠重复素材、堆满小卡片或虚构图标配件来制造丰富感，同样判定不通过。"
            "另外单独评估 commercial_design_score：成品需要有连续的品牌色关系、统一版式语汇、明确主次、多样但一致的图片容器、有目的的叠压与景深，并形成首屏引导、中段证据和底部收束的完整广告节奏。"
            "如果仅把内容放在米白底上、所有区域视觉重量相近、连续使用同一白色卡片，或没有一个稳定的品牌图形母题，commercial_design_score 不得高于 6 并判定不通过。"
            + (
                f"本轮有 {source_reference_count} 张真实源图；如果其中至少四张含有清晰、完整且不重复的可用内容，候选图应该组织出至少四组真实证据；若明显只使用一到两组且留下无目的空洞，必须降低 content_richness_score 并判定不通过。"
                if source_reference_count >= 4
                else "源素材较少时不得虚构新对象补量，应依靠真实素材的尺度、裁切窗口、明暗、叠压和背景材质建立丰富度。"
            )
            if strict_visual_quality
            else ""
        )
        review_prompt = (
            "你是资深电商视觉总监和 A+ 成品质检员。"
            f"{source_note}只检查最后一张候选图，目标尺寸为 {target_width}×{target_height}px。"
            f"{source_truth_note}"
            f"所有新增标题、正文、参数、品牌名和可读 Logo 的完整外接框必须距最终画布左右至少 {text_margin_x}px、上下至少 {text_margin_y}px；"
            "逐项检查是否存在半个字、断笔、末行被切、文字描边或阴影碰边、主体/包装/人物肢体/装饰被画布切断。"
            "尤其检查右对齐长标题、步骤正文和底部品牌行：如果一行在画布边缘突然终止、尾字只剩部分笔画、英文单词或句子明显未结束、"
            "文本框看起来仍向画布外延伸，即使没有看到完整的缺失字符，也必须视为文字被截断并写入 cropped_or_edge_touching_text。"
            "必须区分‘专业摄影出血’与‘意外截断’：时尚人像的发梢、肩臂、躯干或环境在摄影窗口/最终画布边缘自然出血是允许的，"
            "只要眼睛、鼻子、嘴部、主要头部轮廓、人物身份和动作语义仍完整，就不得因为发梢、肩臂或躯干出画而写入 clipped_foreground。"
            "只有脸部关键五官、商品结构、包装边缘、Logo、文字、参数或必要动作被无意切掉时，才属于严重截断。"
            "clipped_foreground 中的每一项必须明确写出被切元素、所在方向和实际缺失部位，禁止只返回元素名称；仅出现‘模特头发、发梢、肩臂或躯干自然出画’不得判错。"
            "任何白色或彩色卡片、参数表、对比框、图片窗口、徽章或带有语义的容器只要被最终画布顶部、底部、左右边缘或内部拼接边界切开，"
            "即使其中部分文字仍可见，也必须写入 clipped_foreground；其中被切文字同时写入 cropped_or_edge_touching_text。"
            "画面不得出现系统安全区、像素尺寸、边距、坐标、辅助线、标尺、双向箭头或诸如 96px、132px 的制作标注；"
            "这类内容若不属于源图真实商品参数，必须写入 technical_artifacts 并判定不通过。"
            "画布四边不得存在白边、黑边、页边距、相框或连续空白带；发现后必须写入 outer_border_issues 并判定不通过。"
            "设计质量检查必须严格：画面要有明确主焦点、专业网格、尺度对比、疏密节奏、连续品牌视觉语言和清晰文字层级；"
            "普通素材堆叠、机械等分卡片、连续相同模块、拥挤小字、大片无目的空洞或廉价贴纸感都要降分。"
            f"{strict_visual_note}"
            + (
                f"手机端应形成 {mobile_screen_count} 个约 600×450 的清晰阅读屏，并与电脑端逐项对照 critical 元素数量、出现次数、文字原文和阅读顺序；"
                "missing_elements 只填写清单中 retention_priority=critical 的缺失项，flexible_background 的合理裁切不能判缺失。"
                "不得把桌面版直接缩窄或机械竖排；横向复合模块应像批准样本一样按语义拆解重排，同时保留 Before/After、双眼型和步骤图等天然内容组。"
                "最终适配必须是一张从顶部到底部连续设计的完整长图。只要出现横向接缝、逐屏风格变化、重复小画面、画中画边框、两侧补片、虚化边、模糊带、毛玻璃、纯色边框、镜像或拉伸像素，"
                "就必须写入 layout_issues 并判定不通过。"
                "但只要顶部标题、底部文案、人物、商品或任何 critical 元素被最终画布切掉，就必须判定为 clipped_foreground 或 cropped_or_edge_touching_text。"
                if is_mobile
                else (
                    "不要因为参考素材没有全部出现而判缺失；自由创作允许主动取舍素材，只评估候选成品自身的完整性、文字安全和商业设计质量。"
                    f"如果候选图将多张已设计方形/矩形广告整块上下堆叠，或同时使用超过 1 个首屏主视觉、{4 if strict_visual_quality else 3} 个支撑证据模块、5 个主文字组，"
                    "必须在 layout_issues 写明‘整块搬运/信息超载’并判定不通过。"
                )
            )
            + (
                f"\n\n必须核对的电脑端最低元素清单：\n{inventory_note}"
                if is_mobile and inventory_note
                else ""
            )
            + designed_module_note
            + "\n\n只返回严格 JSON，不要 Markdown，不要解释。格式："
            '{"composition_score":8,"depth_score":8,"content_richness_score":8,"commercial_design_score":8,"mobile_layout_score":8,'
            '"cropped_or_edge_touching_text":[],"clipped_foreground":[],'
            '"missing_elements":[],"duplicated_elements":[],"invented_elements":[],"text_mismatches":[],'
            '"technical_artifacts":[],"outer_border_issues":[],"layout_issues":[],'
            '"affected_section_indices":[],"passed":true,'
            '"retry_instruction":"若不通过，用一句可直接交给生成模型的中文指令说明如何修复"}'
        )
        response = call_openrouter(
            model=MAIN_IMAGE_A_PLUS_QUALITY_REVIEW_MODEL,
            prompt=review_prompt,
            uploaded_files=comparison_inputs,
            output_mode="text",
            aspect_ratio=DEFAULT_ASPECT_RATIO,
        )
        payload = _extract_strict_json_object(
            str(response.get("text") or ""),
            "A+ 成品质检没有返回有效结果。",
        )

        def normalize_issue_list(key: str) -> list[str]:
            raw_value = payload.get(key) or []
            if isinstance(raw_value, str):
                raw_value = [raw_value]
            normalized_issues = [
                str(item).strip()[:240]
                for item in list(raw_value or [])
                if str(item).strip()
            ][:20]
            if not designed_module_pipeline or int(expected_section_count or 0) <= 0:
                return normalized_issues
            max_section_index = max(int(expected_section_count or 0), 1)

            def references_nonexistent_section(issue: str) -> bool:
                section_numbers: list[int] = []
                for pattern in (
                    r"(?i)section[_\s-]*(\d+)",
                    r"第\s*(\d+)\s*(?:区|段|模块)",
                ):
                    section_numbers.extend(
                        int(match)
                        for match in re.findall(pattern, issue)
                    )
                return any(number > max_section_index for number in section_numbers)

            return [
                issue
                for issue in normalized_issues
                if not references_nonexistent_section(issue)
            ]

        def normalize_section_indices() -> list[int]:
            raw_value = payload.get("affected_section_indices") or []
            if isinstance(raw_value, (str, int, float)):
                raw_value = [raw_value]
            max_section_index = max(int(expected_section_count or 0), 1)
            normalized: list[int] = []
            for value in list(raw_value or []):
                try:
                    section_index = int(value)
                except (TypeError, ValueError):
                    continue
                if 1 <= section_index <= max_section_index and section_index not in normalized:
                    normalized.append(section_index)
            return normalized[:max_section_index]

        try:
            composition_score = max(0.0, min(float(payload.get("composition_score") or 0), 10.0))
        except Exception:
            composition_score = 0.0
        try:
            mobile_layout_score = max(
                0.0,
                min(float(payload.get("mobile_layout_score") or composition_score), 10.0),
            )
        except Exception:
            mobile_layout_score = composition_score
        try:
            depth_score = max(
                0.0,
                min(float(payload.get("depth_score") or composition_score), 10.0),
            )
        except Exception:
            depth_score = composition_score
        try:
            content_richness_score = max(
                0.0,
                min(
                    float(payload.get("content_richness_score") or composition_score),
                    10.0,
                ),
            )
        except Exception:
            content_richness_score = composition_score
        try:
            commercial_design_score = max(
                0.0,
                min(
                    float(payload.get("commercial_design_score") or composition_score),
                    10.0,
                ),
            )
        except Exception:
            commercial_design_score = composition_score
        outer_border_issues = normalize_issue_list("outer_border_issues")
        for issue in detected_outer_border_issues:
            if issue not in outer_border_issues:
                outer_border_issues.append(issue)
        raw_clipped_foreground = normalize_issue_list("clipped_foreground")
        clipped_foreground = [
            issue
            for issue in raw_clipped_foreground
            if not is_main_image_a_plus_permitted_photographic_bleed_issue(issue)
        ]
        review = {
            "reviewed": True,
            "composition_score": composition_score,
            "depth_score": depth_score,
            "content_richness_score": content_richness_score,
            "commercial_design_score": commercial_design_score,
            "mobile_layout_score": mobile_layout_score,
            "cropped_or_edge_touching_text": normalize_issue_list(
                "cropped_or_edge_touching_text"
            ),
            "clipped_foreground": clipped_foreground,
            "missing_elements": normalize_issue_list("missing_elements"),
            "duplicated_elements": normalize_issue_list("duplicated_elements"),
            "invented_elements": normalize_issue_list("invented_elements"),
            "text_mismatches": normalize_issue_list("text_mismatches"),
            "technical_artifacts": normalize_issue_list("technical_artifacts"),
            "outer_border_issues": outer_border_issues[:20],
            "layout_issues": normalize_issue_list("layout_issues"),
            "affected_section_indices": normalize_section_indices(),
            "retry_instruction": str(payload.get("retry_instruction") or "").strip()[:1200],
        }
        critical_issues = (
            list(review["cropped_or_edge_touching_text"])
            + list(review["clipped_foreground"])
            + list(review["technical_artifacts"])
            + list(review["outer_border_issues"])
            + list(review["invented_elements"])
        )
        if is_mobile or designed_module_pipeline:
            critical_issues.extend(review["missing_elements"])
            critical_issues.extend(review["duplicated_elements"])
            critical_issues.extend(review["text_mismatches"])
        if strict_visual_quality:
            critical_issues.extend(review["layout_issues"])
        quality_dimensions = [composition_score, depth_score]
        if is_mobile:
            quality_dimensions.append(mobile_layout_score)
        if strict_visual_quality:
            quality_dimensions.append(content_richness_score)
            quality_dimensions.append(commercial_design_score)
        quality_score = min(quality_dimensions)
        raw_passed = payload.get("passed", True)
        if isinstance(raw_passed, str):
            review_passed = raw_passed.strip().lower() in {"true", "1", "yes", "pass", "passed"}
        else:
            review_passed = bool(raw_passed)
        permitted_bleed_was_only_reported_problem = (
            bool(raw_clipped_foreground)
            and not clipped_foreground
            and not review["cropped_or_edge_touching_text"]
            and not review["missing_elements"]
            and not review["duplicated_elements"]
            and not review["invented_elements"]
            and not review["text_mismatches"]
            and not review["technical_artifacts"]
            and not review["outer_border_issues"]
            and not review["layout_issues"]
        )
        if permitted_bleed_was_only_reported_problem:
            review_passed = True
        review["quality_score"] = quality_score
        review["critical_issue_count"] = len(critical_issues)
        minimum_quality_score = 8.0 if strict_visual_quality else 7.0
        review["passed"] = (
            review_passed
            and not critical_issues
            and quality_score >= minimum_quality_score
        )
        return review
    except Exception as exc:
        return {
            "reviewed": False,
            "passed": False,
            "quality_score": 0.0,
            "critical_issue_count": 1,
            "layout_issues": ["成品质检未完成"],
            "retry_instruction": "",
            "review_error": str(exc)[:300],
        }


def build_main_image_a_plus_quality_retry_instruction(review, multi_visual_centers) -> str:
    issue_keys = (
        "cropped_or_edge_touching_text",
        "clipped_foreground",
        "missing_elements",
        "duplicated_elements",
        "invented_elements",
        "text_mismatches",
        "technical_artifacts",
        "outer_border_issues",
        "layout_issues",
    )
    issues = [
        str(issue).strip()
        for key in issue_keys
        for issue in list(review.get(key) or [])
        if str(issue).strip()
    ]
    model_instruction = str(review.get("retry_instruction") or "").strip()
    issue_summary = "；".join(issues[:12]) or "设计层级或安全区未达到商业成品标准"
    same_side_recovery = ""
    for side_name in ("左侧", "右侧", "顶部", "底部", "左边", "右边"):
        if sum(side_name in issue for issue in issues) >= 2:
            same_side_recovery = (
                "同一侧已有多个元素被切，不要逐个补边；必须把该侧人物、商品、包装和配件作为一个完整视觉组显著缩小并整体向内移动，重新分配周围空间。"
            )
            break
    text_logo_recovery = (
        "品牌字标、Logo、标题或正文被切时，禁止只重画缺失字母；必须重新计算整组文本框，先把字号降低一个或多个层级，"
        "长句在自然语义停顿处换行，再把整个文字组向画面内部移动，四周保留清楚的纯背景缓冲。"
        "右对齐文字必须改为对齐内部栏线，不能继续把画布右边缘当作对齐线；所有同侧文字组都要一起复查并统一内移。"
        if any(
            term in issue
            for issue in issues
            for term in ("字母", "文字", "标题", "品牌", "Logo", "logo", "NEWCALLY")
        )
        else ""
    )
    commercial_richness_recovery = ""
    try:
        commercial_design_score = float(
            review.get("commercial_design_score")
            or review.get("composition_score")
            or review.get("quality_score")
            or 0
        )
        content_richness_score = float(
            review.get("content_richness_score")
            or review.get("composition_score")
            or review.get("quality_score")
            or 0
        )
    except (TypeError, ValueError):
        commercial_design_score = 0.0
        content_richness_score = 0.0
    if min(commercial_design_score, content_richness_score) < 8.0:
        commercial_richness_recovery = (
            "商业设计感和内容丰富度不足时，保留源图中更多清晰、完整且不重复的真实证据，"
            + (
                "将它们改排为一个首屏主中心和分布在中段、下段的两到四个大中型次视觉中心；每个中心使用不同真实语义组、不同尺度与明暗落点，不能把所有视觉重量堆在顶部；"
                if multi_visual_centers
                else "将它们改排为一处强主视觉、大小错落的支撑场景和有明暗反差的商品落点；"
            )
            + "用统一的渐变、裁切窗口、半透明材质面、投影、高光反射和跨区色块中的三至五种建立前中后景，"
            "但不得增加新人物、商品、配件、图标、徽章、箭头、标签或文案。"
        )
    return (
        "上一候选已被成品质检拦截，请从原始参考图重新构图，不要沿用上一候选的错误坐标。"
        f"必须修复：{issue_summary}。"
        + (f"质检修复建议：{model_instruction}。" if model_instruction else "")
        + same_side_recovery
        + text_logo_recovery
        + commercial_richness_recovery
        + "修复后先逐字检查四边文字，再逐项检查主体与元素数量，最后检查移动端/整图的视觉焦点和疏密节奏；只有全部通过才输出。"
    )


def build_main_image_a_plus_free_quality_repair_prompt(
    full_prompt,
    layout,
    review,
    source_reference_count,
    source_pool_only,
    *,
    A_PLUS_PRODUCT_LOCK_RULES,
    A_PLUS_UPLOAD_POOL_LOCK_RULES,
    build_main_image_a_plus_canvas_safety_instruction,
    build_main_image_a_plus_quality_retry_instruction,
    select_main_image_a_plus_safe_aspect_ratio,
) -> str:
    """Turn quality-review findings into an image-edit pass over the best candidate."""
    target_width, target_height = (int(value) for value in layout["target_size"])
    request_aspect_ratio = select_main_image_a_plus_safe_aspect_ratio(
        (target_width, target_height)
    )
    canvas_safety = build_main_image_a_plus_canvas_safety_instruction(
        layout,
        request_aspect_ratio,
    )
    source_count = max(int(source_reference_count or 0), 0)
    support_area_target = 2 if source_count <= 1 else 3 if source_count <= 3 else 4
    source_role = (
        f"第 2 至第 {source_count + 1} 张是真实商品、人物、包装、Logo 与文字事实来源；"
        if source_count > 1
        else (
            "第 2 张是真实商品、人物、包装、Logo 与文字事实来源；"
            if source_count == 1
            else "本轮没有额外事实源图；"
        )
    )
    repair_instruction = build_main_image_a_plus_quality_retry_instruction(
        review,
        multi_visual_centers=source_pool_only,
    )
    source_lock_rules = (
        A_PLUS_UPLOAD_POOL_LOCK_RULES if source_pool_only else A_PLUS_PRODUCT_LOCK_RULES
    )
    return (
        f"{str(full_prompt or '').strip()}\n\n"
        "这是 A+ 成品质检后的定向修复任务，不是再随机生成一套新稿。"
        f"输入图片共 {source_count + 1} 张：第 1 张是上一轮质检未通过的 A+ 候选图，是本轮必须直接编辑的底图；{source_role}"
        "真实事实一律以第 2 张起的源图为准；候选图中与源图不一致的文字、商品细节或虚构元素不得保留。"
        f"必须在候选图现有构图上完成精确编辑，直接输出 1 张完整 A+ 成品；"
        f"{target_width}×{target_height}px 只是宽度和构图高度节奏参考，后端只锁定宽度 {target_width}px，最终高度按返回图比例自适应。"
        "已经正确的区域、品牌风格、配色和背景连续性必须保持，只修改质检指出的问题及必要的邻近区域。"
        "修复优先级固定为：第一，把贴边或被误截的人脸关键五官、主要头部轮廓、商品、包装、Logo 和文字整组向内移动或等比缩小；不要把专业的发梢、肩臂或躯干出血误修成拘谨的证件照构图；"
        + (
            "第二，保留一个略占优势的首屏主中心，同时保住中段和下段的次视觉中心；次中心可以略低一档，但不能全部降成小卡片或无视觉重量的说明区；"
            if source_pool_only
            else "第二，只保留一个最强主焦点，降低其他模块的尺度和对比；"
        )
        + "第三，用统一的列线、边距、对齐线和间距重排问题模块，不得继续使用多块平均并列的拼贴式网格；"
        "第四，完整保留所有标题和 Before/After 等有语义组合，通过换行、缩小字号或扩大底区解决可读性，不得删字或裁字。"
        "如果质检出现信息拥挤、元素堆叠、阅读流程不清或拼贴感，必须主动删除候选图中低优先级的重复口号、环绕装饰字、次要标签和重复产品图；"
        + (
            f"修复后沿长图纵向组织 1 个首屏主中心、2 至 4 个中下段次视觉中心、约 {support_area_target} 个有明显尺度变化的内容场景和 1 个品牌收尾；"
            "可以增加连续背景、抽象色块、统一轮廓的局部特写窗口、错位排版、半透明材质面、投影、高光反射、光晕与景深来丰富层次，"
            "并确保相邻场景不连续使用相同白色底、相同尺寸和相同卡片结构，但不得增加任何源图中不存在的语义对象。"
            if source_pool_only
            else "修复后只允许 1 个首屏主视觉、最多 3 个支撑证据模块和 1 个品牌收尾；"
        )
        + "不得保留任何整张方形广告模块的大矩形搬运痕迹。"
        "文字修复硬规则：任何标题、正文、品牌名和 Logo 都不得与人物、商品、图片、其他文字或装饰重叠；"
        "品牌字标和 Logo 必须作为不可拆分的完整图形组整体缩小、移动或重新排版；禁止只补一个字母、把尾字贴在画布边缘，或继续沿用源图中的贴边坐标。"
        "底部收尾必须使用独立的低干扰背景区，先留足安全边距再放 Logo 和原图确实存在的文字。"
        "禁止新增 Thank you、Shop now、Choose us、品牌口号或任何源图中不存在的收尾文案；候选图已经虚构的这类文字必须删除。"
        f"{repair_instruction}"
        f"{canvas_safety}"
        "背景、场景、渐变、光影与连续纹理仍必须满版覆盖四边；禁止加白边、黑边、模糊带、相框或边缘生成式背景延展来换取安全距离。"
        f"{source_lock_rules}"
        "只返回修复后的单张成品，不返回说明、对比图、标注框或多个版本。"
    )


def build_main_image_a_plus_quality_recovery_advice(review) -> str:
    advice: list[str] = []
    if list(review.get("clipped_foreground") or []):
        advice.append("优先换用人物头顶、商品和包装四边完整的源图")
    if list(review.get("cropped_or_edge_touching_text") or []):
        advice.append("上传标题四周留白完整的参考图，或减少同一张图中的大段文字")
    if list(review.get("layout_issues") or []):
        advice.append("选择与目标端一致的版式 Skill，或减少同时参与首屏的素材数量")
    if list(review.get("text_mismatches") or []):
        advice.append("使用文字清晰、没有透视变形的原始文案图")
    if list(review.get("invented_elements") or []):
        advice.append("删除源图中不存在的对象，只保留上传素材池中可核实的元素")
    if list(review.get("technical_artifacts") or []):
        advice.append("删除全部标尺、箭头和制作批注后再输出纯成品")
    if list(review.get("outer_border_issues") or []):
        advice.append("让连续背景满版延伸到画布四边，不要用补白凑尺寸")
    if not advice:
        advice.append("减少一次上传的复合成品图，优先使用主体完整的原始素材")
    return "建议处理：" + "；".join(advice[:3]) + "。"


def collect_main_image_a_plus_quality_issues(review) -> list[str]:
    issue_keys = (
        "cropped_or_edge_touching_text",
        "clipped_foreground",
        "missing_elements",
        "duplicated_elements",
        "invented_elements",
        "text_mismatches",
        "technical_artifacts",
        "outer_border_issues",
        "layout_issues",
    )
    return [
        str(issue).strip()
        for key in issue_keys
        for issue in list(review.get(key) or [])
        if str(issue).strip()
    ][:40]


def select_main_image_a_plus_crop_anchors(
    review,
    *,
    collect_main_image_a_plus_quality_issues,
) -> tuple[str, str]:
    issues = collect_main_image_a_plus_quality_issues(dict(review or {}))

    def count_terms(terms: tuple[str, ...]) -> int:
        return sum(
            1
            for issue in issues
            if any(term in issue for term in terms)
        )

    left_count = count_terms(("左侧", "左边", "左端"))
    right_count = count_terms(("右侧", "右边", "右端"))
    top_count = count_terms(("顶部", "上侧", "上边", "上端"))
    bottom_count = count_terms(("底部", "下侧", "下边", "下端"))
    horizontal_anchor = (
        "right"
        if right_count > left_count
        else "left"
        if left_count > right_count
        else "center"
    )
    vertical_anchor = (
        "bottom"
        if bottom_count > top_count
        else "top"
        if top_count > bottom_count
        else "center"
    )
    return horizontal_anchor, vertical_anchor


def collect_main_image_a_plus_severe_subject_clips(
    review,
    *,
    is_main_image_a_plus_permitted_photographic_bleed_issue,
) -> list[str]:
    severe_subject_keywords = (
        "人脸",
        "脸部",
        "五官",
        "眼睛",
        "鼻子",
        "嘴部",
        "头顶",
        "头部轮廓",
        "商品",
        "产品",
        "包装",
        "配件",
        "胶水瓶",
        "镜子",
    )
    return [
        str(value).strip()
        for value in list(review.get("clipped_foreground") or [])
        if str(value).strip()
        and not is_main_image_a_plus_permitted_photographic_bleed_issue(value)
        and any(keyword in str(value) for keyword in severe_subject_keywords)
    ]


def build_main_image_a_plus_mobile_repair_prompt(
    layout,
    element_inventory,
    safe_margin_instruction,
    review,
    *,
    MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT,
    build_main_image_a_plus_quality_retry_instruction,
) -> str:
    target_width, target_height = (int(value) for value in layout["target_size"])
    screen_count = int(
        layout.get("mobile_screen_count")
        or max(round(target_height / MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT), 1)
    )
    repair_instruction = build_main_image_a_plus_quality_retry_instruction(review)
    return (
        "这是手机端 A+ 的定向修复任务。输入图片只有两张：第 1 张是电脑版原稿，也是人物、商品、包装、Logo、文字、参数和图片内容的唯一事实来源；"
        "第 2 张是上一轮生成的手机版候选，只用于继承已经完成的手机端构图、品牌风格、配色、层级和纵向节奏。"
        "严禁把第 2 张中与第 1 张不一致的文字、商品细节或虚构元素继续保留，也不得交换两张图的角色。"
        f"请在第 2 张版式基础上做局部重排和精确修复，直接输出一张完整的 {target_width}×{target_height}px、共 {screen_count} 个约 600×450 阅读屏的手机版 A+。"
        "优先保持第 2 张中已经正确且美观的区域不变；只对质检指出的问题及其必要邻近区域进行修改，避免整张图重新随机生成。"
        "逐项对照第 1 张恢复缺失元素、纠正重复元素和错误文字；所有文字必须逐字沿用第 1 张原文，不能凭语义改写。"
        "任何被裁切、贴边或遮挡的文字、Logo、人物、商品、包装、步骤图和效果图，都必须整组向内移动、重新换行或等比缩小，不能用遮罩、补边、拉伸或删除解决。"
        "摄影背景可以重新取景，但人脸、眼睛、动作和商品语义必须完整；背景、渐变与纹理必须继续满版铺满四边。"
        f"{repair_instruction}"
        + (
            f"\n\n必须逐项核对的电脑版内容清单：\n{str(element_inventory).strip()}"
            if str(element_inventory or "").strip()
            else ""
        )
        + (
            f"\n\n手机端安全边距硬规则：{str(safe_margin_instruction).strip()}"
            if str(safe_margin_instruction or "").strip()
            else ""
        )
        + "\n\n只返回修复后的单张手机端成品，不返回说明、对比图、标记框或多个版本。"
    )


def rank_main_image_a_plus_quality_review(review) -> tuple[int, int, float]:
    return (
        2 if bool(review.get("passed")) and bool(review.get("reviewed")) else 1,
        -int(review.get("critical_issue_count") or 0),
        float(review.get("quality_score") or 0.0),
    )
