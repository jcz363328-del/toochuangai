"""A+ image guide, element analysis, slice download and PSD assembly."""

from __future__ import annotations

from typing import Any


def get_main_image_a_plus_native_safe_zones(
    layout,
    request_aspect_ratio,
    *,
    math,
    re,
    select_main_image_a_plus_safe_aspect_ratio,
) -> dict[str, Any]:
    """Map final-canvas safety margins into the model's native aspect-ratio canvas."""
    target_width, target_height = (int(value) for value in layout["target_size"])
    normalized_ratio = str(
        request_aspect_ratio
        or select_main_image_a_plus_safe_aspect_ratio((target_width, target_height))
    ).strip()
    ratio_match = re.fullmatch(r"(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)", normalized_ratio)
    if not ratio_match:
        raise ValueError(f"Unsupported A+ native aspect ratio: {normalized_ratio}")
    native_width = float(ratio_match.group(1))
    native_height = float(ratio_match.group(2))
    if native_width <= 0 or native_height <= 0:
        raise ValueError(f"Unsupported A+ native aspect ratio: {normalized_ratio}")

    foreground_margin_x = max(0.025, 18.0 / float(target_width))
    foreground_margin_y = max(0.02, 36.0 / float(target_height))
    text_margin_x = max(
        0.08,
        float(layout.get("text_margin_x") or 0) / float(target_width),
    )
    text_margin_y = max(
        0.04,
        float(layout.get("text_margin_y") or 0) / float(target_height),
    )

    def native_box(margin_x: float, margin_y: float) -> list[int]:
        return [
            math.ceil(margin_x * 1000),
            math.ceil(margin_y * 1000),
            math.floor((1.0 - margin_x) * 1000),
            math.floor((1.0 - margin_y) * 1000),
        ]

    return {
        "request_aspect_ratio": normalized_ratio,
        "crop_x_percent": 0.0,
        "crop_y_percent": 0.0,
        "extension_x_percent": 0.0,
        "extension_y_percent": 0.0,
        "foreground_box": native_box(foreground_margin_x, foreground_margin_y),
        "text_box": native_box(text_margin_x, text_margin_y),
        "final_text_margin_x": round(text_margin_x * target_width),
        "final_text_margin_y": round(text_margin_y * target_height),
    }


def get_main_image_a_plus_template_layout(
    template_input,
    *,
    AMAZON_A_PLUS_MAX_EDGE,
    AMAZON_A_PLUS_MAX_PIXELS,
    Image,
    ImageOps,
    MAIN_IMAGE_A_PLUS_SECTION_COUNT,
    get_uploaded_file_bytes,
    io,
) -> dict[str, Any]:
    if template_input is None:
        raise RuntimeError("套版替换需要先上传 1 张成品 A+ 模板。")
    template_bytes = get_uploaded_file_bytes(template_input)
    try:
        with Image.open(io.BytesIO(template_bytes)) as image:
            normalized = ImageOps.exif_transpose(image)
            target_width, target_height = normalized.size
    except Exception as exc:
        raise RuntimeError(f"无法读取成品 A+ 模板尺寸：{exc}") from exc
    if (
        target_width <= 0
        or target_height < MAIN_IMAGE_A_PLUS_SECTION_COUNT
        or target_width > AMAZON_A_PLUS_MAX_EDGE
        or target_height > AMAZON_A_PLUS_MAX_EDGE
        or target_width * target_height > AMAZON_A_PLUS_MAX_PIXELS
    ):
        raise RuntimeError(
            "成品 A+ 模板尺寸不受支持：最长边不能超过 10000px，画布不能超过 4000 万像素。"
        )
    base_section_height, remainder = divmod(target_height, MAIN_IMAGE_A_PLUS_SECTION_COUNT)
    section_heights = [base_section_height] * MAIN_IMAGE_A_PLUS_SECTION_COUNT
    section_heights[-1] += remainder
    return {
        "key": "template_original_size",
        "label": f"跟随模板原尺寸｜{target_width}×{target_height}",
        "target_size": (target_width, target_height),
        "section_heights": tuple(section_heights),
        "text_margin_x": max(24, round(target_width * 0.08)),
        "text_margin_y": max(20, round(min(section_heights) * 0.1)),
    }


def normalize_main_image_a_plus_element_bbox(raw_bbox, image_size) -> list[int] | None:
    if isinstance(raw_bbox, dict):
        left = raw_bbox.get("left", raw_bbox.get("x", 0))
        top = raw_bbox.get("top", raw_bbox.get("y", 0))
        if "right" in raw_bbox or "bottom" in raw_bbox:
            right = raw_bbox.get("right", left)
            bottom = raw_bbox.get("bottom", top)
        else:
            right = float(left or 0) + float(raw_bbox.get("width", raw_bbox.get("w", 0)) or 0)
            bottom = float(top or 0) + float(raw_bbox.get("height", raw_bbox.get("h", 0)) or 0)
        values = [left, top, right, bottom]
    elif isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
        values = list(raw_bbox[:4])
    else:
        return None
    try:
        left, top, right, bottom = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    max_value = max(abs(left), abs(top), abs(right), abs(bottom))
    if max_value <= 1.01:
        left, top, right, bottom = [value * 1000 for value in (left, top, right, bottom)]
    elif max_value > 1000:
        image_width, image_height = image_size
        if image_width <= 0 or image_height <= 0:
            return None
        left = left / image_width * 1000
        right = right / image_width * 1000
        top = top / image_height * 1000
        bottom = bottom / image_height * 1000
    left, right = sorted((max(0, min(1000, left)), max(0, min(1000, right))))
    top, bottom = sorted((max(0, min(1000, top)), max(0, min(1000, bottom))))
    if right - left < 5 or bottom - top < 5:
        return None
    return [round(left), round(top), round(right), round(bottom)]


def analyze_main_image_a_plus_elements(
    template_input,
    *,
    DEFAULT_ASPECT_RATIO,
    MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
    MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS,
    call_openrouter,
    get_uploaded_input_dimensions,
    parse_main_image_a_plus_element_analysis,
) -> list[dict[str, Any]]:
    if template_input is None:
        raise RuntimeError("请先上传 1 张完整的成品 A+ 示例图。")
    image_size = get_uploaded_input_dimensions(template_input)
    analysis_prompt = (
        "你是电商 A+ 视觉模板元素分析器。请完整识别这张成品 A+ 长图中所有可以用另一张图片替换的前景内容，"
        "包括模特或人物、商品、包装、Logo/品牌、独立文案块、参数标签、徽章图标、使用效果、局部特写和带有商品语义的装饰。"
        "不要把纯背景、底层色块、结构边框、留白、分区和整体版式列为可替换元素。"
        "语义相同且应该使用同一份替换素材的重复内容合并成一个元素组，并在 regions 中列出它的全部出现位置；"
        "语义不同的产品、人物、文字块或细节必须拆成不同元素组。请覆盖整张长图，不要只分析首屏。"
        f"最多输出 {MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS} 个最完整的元素组。所有坐标都使用 0 到 1000 的归一化整数，"
        "格式为 [left, top, right, bottom]。只返回严格 JSON，不要 Markdown，不要解释。"
        "JSON 格式：{\"elements\":[{\"name\":\"主模特\",\"type\":\"model\","
        "\"description\":\"模板中人物主体\",\"replacement_hint\":\"上传要替换进去的新模特图\","
        "\"regions\":[[100,50,700,420]]}]}"
    )
    response = call_openrouter(
        model=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        prompt=analysis_prompt,
        uploaded_files=[template_input],
        output_mode="text",
        aspect_ratio=DEFAULT_ASPECT_RATIO,
    )
    return parse_main_image_a_plus_element_analysis(
        str(response.get("text") or ""),
        image_size,
    )


def crop_main_image_a_plus_replacement_input(
    replacement_input,
    crop_box,
    element_id,
    element_name,
    *,
    Image,
    ImageOps,
    get_uploaded_file_bytes,
    io,
    math,
    normalize_main_image_a_plus_element_bbox,
    sanitize_file_name,
) -> dict[str, Any] | None:
    """Return only the matched replacement element, never the full source artwork."""
    try:
        source_bytes = get_uploaded_file_bytes(replacement_input)
        with Image.open(io.BytesIO(source_bytes)) as source_image:
            source_image = ImageOps.exif_transpose(source_image)
            source_width, source_height = source_image.size
            normalized_box = normalize_main_image_a_plus_element_bbox(
                crop_box,
                (source_width, source_height),
            )
            if normalized_box is None:
                return None
            left_n, top_n, right_n, bottom_n = normalized_box
            left = math.floor(left_n / 1000 * source_width)
            top = math.floor(top_n / 1000 * source_height)
            right = math.ceil(right_n / 1000 * source_width)
            bottom = math.ceil(bottom_n / 1000 * source_height)
            crop_width = max(right - left, 1)
            crop_height = max(bottom - top, 1)
            padding = max(2, round(max(crop_width, crop_height) * 0.035))
            left = max(0, left - padding)
            top = max(0, top - padding)
            right = min(source_width, right + padding)
            bottom = min(source_height, bottom + padding)
            if right - left < 4 or bottom - top < 4:
                return None
            cropped = source_image.crop((left, top, right, bottom))
            if cropped.size == source_image.size:
                return None
            if cropped.mode not in {"RGB", "RGBA"}:
                cropped = cropped.convert("RGBA" if "A" in cropped.getbands() else "RGB")
            output = io.BytesIO()
            cropped.save(output, format="PNG", optimize=True)
    except Exception:
        return None
    safe_name = sanitize_file_name(str(element_name or f"element_{element_id}"))
    return {
        "data": output.getvalue(),
        "name": f"recommended_{int(element_id)}_{safe_name}_crop.png",
        "type": "image/png",
    }


def analyze_main_image_a_plus_element_at_point(
    template_input,
    point,
    existing_elements,
    *,
    DEFAULT_ASPECT_RATIO,
    MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
    MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS,
    call_openrouter,
    get_uploaded_input_dimensions,
    parse_main_image_a_plus_element_analysis,
) -> dict[str, Any]:
    if template_input is None:
        raise RuntimeError("请先上传完整 A+ 模板。")
    if len(existing_elements) >= MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS:
        raise RuntimeError(f"当前最多支持 {MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS} 个元素组。")
    point_x, point_y = point
    existing_summary = "；".join(
        f"#{int(element.get('id') or index + 1)} {str(element.get('name') or '元素')}"
        for index, element in enumerate(existing_elements)
    )
    prompt = (
        "你是电商 A+ 模板补漏识别器。用户点击了完整模板中的一个漏识别元素，点击坐标使用 0 到 1000 "
        f"归一化坐标，位置为 ({point_x}, {point_y})。请识别点击位置正下方或距离最近的完整前景元素，"
        "判断它是人物、产品、包装、品牌 Logo、独立文字块、参数、徽章、效果图还是细节特写，"
        "并返回该语义元素的完整边界；如果同一元素在模板中重复出现，请在 regions 中返回全部出现位置。"
        "不要把背景、底层色块、结构边框或整个分区识别成元素。只返回 1 个元素的严格 JSON，不要 Markdown。"
        f"已经识别的元素为：{existing_summary or '无'}。避免重复返回已经识别的元素。"
        "JSON 格式：{\"elements\":[{\"name\":\"产品包装\",\"type\":\"package\","
        "\"description\":\"点击位置的商品包装\",\"replacement_hint\":\"上传新产品包装图\","
        "\"regions\":[[100,100,450,380]]}]}"
    )
    response = call_openrouter(
        model=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        prompt=prompt,
        uploaded_files=[template_input],
        output_mode="text",
        aspect_ratio=DEFAULT_ASPECT_RATIO,
    )
    detected = parse_main_image_a_plus_element_analysis(
        str(response.get("text") or ""),
        get_uploaded_input_dimensions(template_input),
    )
    if not detected:
        raise RuntimeError("点击位置没有识别到可替换元素，请点击元素主体后重试。")
    new_element = dict(detected[0])
    new_element["id"] = max(
        [int(element.get("id") or 0) for element in existing_elements] or [0]
    ) + 1
    return new_element


def render_main_image_a_plus_manual_element_picker(
    annotated_preview,
    template_signature,
    component_key,
    *,
    MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY,
    json,
    re,
    st,
) -> None:
    safe_component_key = re.sub(r"[^A-Za-z0-9_-]+", "_", str(component_key or "picker"))
    preview_json = json.dumps(str(annotated_preview or ""), ensure_ascii=False)
    signature_json = json.dumps(str(template_signature or ""), ensure_ascii=False)
    query_key_json = json.dumps(MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY)
    html_content = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        html, body {{ margin: 0; padding: 0; background: transparent; color: #eef3ff; font-family: Arial, sans-serif; }}
        .picker-shell {{ position: relative; height: 720px; overflow: auto; border-radius: 14px; border: 1px solid rgba(139, 156, 255, .26); background: rgba(5, 12, 27, .72); }}
        .picker-tip {{ position: sticky; top: 0; z-index: 3; padding: 10px 12px; background: rgba(9, 18, 39, .94); color: #dfe6ff; font-size: 13px; line-height: 1.5; border-bottom: 1px solid rgba(139, 156, 255, .18); }}
        .picker-image-wrap {{ display: flex; justify-content: center; padding: 12px; }}
        .picker-image {{ display: block; width: min(100%, 760px); height: auto; cursor: crosshair; border-radius: 8px; user-select: none; -webkit-user-drag: none; }}
        .picker-image:hover {{ box-shadow: 0 0 0 2px rgba(126, 96, 255, .85); }}
        .picker-loading {{ position: fixed; inset: 0; display: none; align-items: center; justify-content: center; background: rgba(3, 8, 22, .72); z-index: 5; font-weight: 700; }}
      </style>
    </head>
    <body>
      <div class="picker-shell" id="picker-shell-{safe_component_key}">
        <div class="picker-tip" id="picker-tip-{safe_component_key}">点击机器漏掉的元素主体，系统会按点击位置补充识别并生成一个新编号。已带彩色编号的区域无需重复点击。</div>
        <div class="picker-image-wrap"><img class="picker-image" id="picker-image-{safe_component_key}" alt="点击补漏" /></div>
      </div>
      <div class="picker-loading" id="picker-loading-{safe_component_key}">正在定位元素，请稍候…</div>
      <script>
        (() => {{
          const image = document.getElementById("picker-image-{safe_component_key}");
          const loading = document.getElementById("picker-loading-{safe_component_key}");
          const tip = document.getElementById("picker-tip-{safe_component_key}");
          const hostWindow = window.parent;
          image.src = {preview_json};
          image.addEventListener("click", (event) => {{
            const rect = image.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            const x = Math.max(0, Math.min(1000, Math.round((event.clientX - rect.left) / rect.width * 1000)));
            const y = Math.max(0, Math.min(1000, Math.round((event.clientY - rect.top) / rect.height * 1000)));
            const payload = JSON.stringify({{
              template_signature: {signature_json},
              x,
              y
            }});
            const nextUrl = new URL(hostWindow.location.href);
            nextUrl.searchParams.set({query_key_json}, payload);
            loading.style.display = "flex";
            hostWindow.location.replace(nextUrl.toString());
            window.setTimeout(() => {{
              loading.style.display = "none";
              if (tip) tip.textContent = "点击已提交；如果页面没有更新，请再点击一次元素主体。";
            }}, 6000);
          }});
        }})();
      </script>
    </body>
    </html>
    """
    st.iframe(html_content, height=740, width="stretch")


def is_main_image_a_plus_permitted_photographic_bleed_issue(issue) -> bool:
    normalized = str(issue or "").strip().lower()
    if not normalized:
        return False
    permitted_terms = (
        "头发",
        "发梢",
        "发丝",
        "肩臂",
        "肩部",
        "手臂",
        "躯干",
        "衣服",
        "服装",
        "环境",
        "背景",
    )
    protected_terms = (
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
        "logo",
        "文字",
        "参数",
    )
    return any(term in normalized for term in permitted_terms) and not any(
        term in normalized for term in protected_terms
    )


def get_main_image_a_plus_mobile_reference_inputs(
    *,
    Any,
    MAIN_IMAGE_A_PLUS_MOBILE_REFERENCE_PAIRS,
    MAIN_IMAGE_A_PLUS_MOBILE_REFERENCE_ROOT,
    prepare_main_image_a_plus_reference_input,
) -> list[dict[str, Any]]:
    """Load the approved PC→mobile pairs as few-shot layout references."""
    references: list[dict[str, Any]] = []
    for pair_index, (desktop_name, mobile_name) in enumerate(
        MAIN_IMAGE_A_PLUS_MOBILE_REFERENCE_PAIRS,
        start=1,
    ):
        pair_paths = (
            ("desktop", MAIN_IMAGE_A_PLUS_MOBILE_REFERENCE_ROOT / desktop_name),
            ("mobile", MAIN_IMAGE_A_PLUS_MOBILE_REFERENCE_ROOT / mobile_name),
        )
        if not all(path.exists() and path.is_file() for _role, path in pair_paths):
            continue
        prepared_pair: list[dict[str, Any]] = []
        for role, reference_path in pair_paths:
            prepared = prepare_main_image_a_plus_reference_input(
                {
                    "data": reference_path.read_bytes(),
                    "name": f"layout_example_{pair_index}_{role}.jpg",
                    "type": "image/jpeg",
                }
            )
            if bytes(prepared.get("data") or b""):
                prepared_pair.append(prepared)
        if len(prepared_pair) == 2:
            references.extend(prepared_pair)
    return references


def render_main_image_a_plus_crop_downloads(
    image_sources,
    key_prefix,
    base_names,
    *,
    MAIN_IMAGE_A_PLUS_CROP_PRESETS,
    build_main_image_a_plus_crop_archive_from_source,
    infer_main_image_a_plus_crop_base_name,
    sanitize_file_name,
    st,
) -> None:
    normalized_sources = [str(source or "").strip() for source in image_sources if str(source or "").strip()]
    if not normalized_sources:
        return
    normalized_key_prefix = sanitize_file_name(key_prefix or "main_image_a_plus_crop")
    for image_index, image_source in enumerate(normalized_sources):
        item_key = f"{normalized_key_prefix}_{image_index}"
        visibility_key = f"{item_key}_options_visible"
        is_visible = bool(st.session_state.get(visibility_key, False))
        entry_label = "收起裁切选项" if is_visible else "裁切下载"
        if len(normalized_sources) > 1:
            entry_label = f"图片 {image_index + 1} · {entry_label}"
        if st.button(
            entry_label,
            key=f"{item_key}_toggle",
            type="secondary",
            use_container_width=True,
            icon=":material/content_cut:",
        ):
            is_visible = not is_visible
            st.session_state[visibility_key] = is_visible
        if not is_visible:
            continue

        supplied_name = ""
        if base_names and image_index < len(base_names):
            supplied_name = str(base_names[image_index] or "").strip()
        base_name = supplied_name or infer_main_image_a_plus_crop_base_name(image_source, image_index)
        st.caption("完整长图会按实际 4 屏或 5 屏高度等比适配后横向切段；不拉伸、不压缩、不漏掉首尾内容。")
        option_columns = st.columns(2, gap="small")
        for option_column, preset_key in zip(option_columns, ("mobile", "desktop")):
            preset = MAIN_IMAGE_A_PLUS_CROP_PRESETS[preset_key]
            with option_column:
                try:
                    with st.spinner(f"正在准备{preset['label']}文件…"):
                        archive = build_main_image_a_plus_crop_archive_from_source(
                            image_source,
                            preset_key,
                            base_name,
                        )
                except Exception as exc:
                    st.error(str(exc))
                    continue
                segment_width = int(archive["segment_sizes"][0][0])
                st.download_button(
                    f"{preset['label']} · {segment_width}×{preset['segment_height']} × {archive['segment_count']}",
                    data=archive["data"],
                    file_name=archive["file_name"],
                    mime=archive["mime"],
                    key=f"{item_key}_download_{preset_key}",
                    icon=":material/download:",
                    type="primary",
                    use_container_width=True,
                )


def build_amazon_a_plus_layered_result(
    result,
    target_size,
    *,
    Image,
    ImageOps,
    build_commercial_a_plus_background,
    build_layered_a_plus,
    datetime,
    fit_green_screen_to_canvas,
    image_bytes_to_data_url,
    io,
    load_image_bytes_from_url,
    uuid4,
) -> dict[str, Any]:
    image_sources = list(result.get("images") or [])
    if not image_sources:
        raise RuntimeError("模型没有返回可用于分层的绿幕 A+ 底稿。")

    image_bytes, _mime_type = load_image_bytes_from_url(str(image_sources[0]))
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            green_screen = ImageOps.exif_transpose(image).convert("RGBA")
    except Exception as exc:
        raise RuntimeError(f"无法读取模型返回的绿幕 A+ 底稿：{exc}") from exc

    source_generation_size = green_screen.size
    if target_size:
        green_screen = fit_green_screen_to_canvas(
            green_screen,
            (int(target_size[0]), int(target_size[1])),
        ).convert("RGBA")

    try:
        commercial_background = build_commercial_a_plus_background(green_screen)
        layered = build_layered_a_plus(green_screen, background=commercial_background)
    except Exception as exc:
        raise RuntimeError(f"绿幕元素自动裁切失败：{exc}") from exc

    green_buffer = io.BytesIO()
    green_screen.save(green_buffer, format="PNG")
    layer_count = int(layered.get("layer_count") or 0)
    psd_file_name = f"amazon_a_plus_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.psd"
    processed_result = dict(result)
    processed_result["images"] = [
        image_bytes_to_data_url(bytes(layered["composite_png"]), "image/png")
    ]
    processed_result["green_screen_images"] = [
        image_bytes_to_data_url(green_buffer.getvalue(), "image/png")
    ]
    background_buffer = io.BytesIO()
    commercial_background.save(background_buffer, format="PNG")
    processed_result["background_images"] = [
        image_bytes_to_data_url(background_buffer.getvalue(), "image/png")
    ]
    processed_result["layer_count"] = layer_count
    processed_result["layer_manifest"] = list(layered.get("layer_manifest") or [])
    processed_result["source_generation_size"] = source_generation_size
    processed_result["psd_bytes"] = bytes(layered["psd_bytes"])
    processed_result["psd_file_name"] = psd_file_name
    original_text = str(result.get("text") or "").strip()
    processed_result["text"] = "\n\n".join(
        part
        for part in (
            original_text,
            f"高清底稿尺寸为 {source_generation_size[0]}*{source_generation_size[1]}px，已按比例适配到目标画布。",
            f"已生成 1 个独立商业背景层，并从绿幕底稿中识别元素，共得到 {layer_count} 个 Photoshop 可编辑图层。",
        )
        if part
    )
    return processed_result
