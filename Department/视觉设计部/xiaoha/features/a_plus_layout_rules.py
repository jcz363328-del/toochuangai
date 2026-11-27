"""Resolve A+ layout, element and image continuity rules."""

from __future__ import annotations

from typing import Any


def infer_main_image_a_plus_screen_count(
    canvas_size,
    *,
    MAIN_IMAGE_A_PLUS_DESKTOP_SCREEN_HEIGHT,
    MAIN_IMAGE_A_PLUS_MAX_MOBILE_SCREENS,
    MAIN_IMAGE_A_PLUS_MIN_MOBILE_SCREENS,
    math,
) -> int:
    """Infer how many logical A+ screens a desktop or mobile long image contains."""
    width, height = (max(int(value), 1) for value in canvas_size)
    canvas_ratio = width / float(height)
    if canvas_ratio <= 0.38:
        raw_count = height / float(width * 0.75)
    else:
        normalized_desktop_height = height * (1464.0 / float(width))
        raw_count = normalized_desktop_height / float(MAIN_IMAGE_A_PLUS_DESKTOP_SCREEN_HEIGHT)
    rounded_count = int(math.floor(raw_count + 0.5))
    return max(
        MAIN_IMAGE_A_PLUS_MIN_MOBILE_SCREENS,
        min(rounded_count, MAIN_IMAGE_A_PLUS_MAX_MOBILE_SCREENS),
    )


def get_main_image_a_plus_mobile_layout_for_source(
    source_size,
    *,
    MAIN_IMAGE_A_PLUS_LAYOUTS,
    MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT,
    get_main_image_a_plus_layout,
    infer_main_image_a_plus_screen_count,
) -> dict[str, Any]:
    screen_count = infer_main_image_a_plus_screen_count(source_size)
    target_width = int(MAIN_IMAGE_A_PLUS_LAYOUTS["mobile_equal"]["target_size"][0])
    target_height = screen_count * MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT
    layout = get_main_image_a_plus_layout("mobile_equal")
    layout.update(
        {
            "label": f"手机端｜{target_width}×{target_height}｜{screen_count} 屏自然重排",
            "target_size": (target_width, target_height),
            "section_heights": (MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT,) * screen_count,
            "mobile_screen_count": screen_count,
            "source_size": tuple(max(int(value), 1) for value in source_size),
        }
    )
    return layout


def select_main_image_a_plus_safe_aspect_ratio(
    canvas_size,
    *,
    GEMINI_IMAGE_ASPECT_RATIOS,
    re,
) -> str:
    """Prefer a native ratio that preserves the full left and right edges after cover fitting."""
    width, height = (int(value) for value in canvas_size)
    if width <= 0 or height <= 0:
        raise ValueError("A+ canvas dimensions must be positive.")
    target_ratio = width / float(height)
    parsed_ratios: list[tuple[float, str]] = []
    for ratio_text in GEMINI_IMAGE_ASPECT_RATIOS:
        ratio_match = re.fullmatch(r"(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)", ratio_text)
        if not ratio_match:
            continue
        ratio_value = float(ratio_match.group(1)) / float(ratio_match.group(2))
        if ratio_value <= target_ratio + 1e-9:
            parsed_ratios.append((ratio_value, ratio_text))
    if not parsed_ratios:
        raise ValueError("No native A+ aspect ratio can preserve the complete horizontal canvas.")
    return max(parsed_ratios, key=lambda item: (item[0], item[1]))[1]


def find_main_image_a_plus_element_at_point(
    elements,
    point,
    *,
    Any,
) -> dict[str, Any] | None:
    point_x, point_y = point
    candidates: list[tuple[float, dict[str, Any]]] = []
    for element in elements:
        for region in list(element.get("regions") or []):
            if not isinstance(region, (list, tuple)) or len(region) < 4:
                continue
            left, top, right, bottom = [float(value) for value in region[:4]]
            if left <= point_x <= right and top <= point_y <= bottom:
                candidates.append((max(1.0, (right - left) * (bottom - top)), element))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def consume_main_image_a_plus_manual_point(
    template_signature,
    *,
    MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY,
    clear_query_param,
    json,
    st,
) -> tuple[int, int] | None:
    raw_payload = str(
        st.query_params.get(MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY, "")
    ).strip()
    if not raw_payload:
        return None
    clear_query_param(MAIN_IMAGE_A_PLUS_MANUAL_POINT_QUERY_KEY)
    try:
        payload = json.loads(raw_payload)
        if str(payload.get("template_signature") or "") != str(template_signature or ""):
            return None
        point_x = max(0, min(1000, int(round(float(payload.get("x") or 0)))))
        point_y = max(0, min(1000, int(round(float(payload.get("y") or 0)))))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return point_x, point_y


def consume_main_image_a_plus_text_edit_point(
    source_signature,
    *,
    MAIN_IMAGE_A_PLUS_TEXT_POINT_QUERY_KEY,
    clear_query_param,
    json,
    st,
) -> tuple[int, int] | None:
    raw_payload = str(
        st.query_params.get(MAIN_IMAGE_A_PLUS_TEXT_POINT_QUERY_KEY, "")
    ).strip()
    if not raw_payload:
        return None
    try:
        payload = json.loads(raw_payload)
        if str(payload.get("source_signature") or "") != str(source_signature or ""):
            return None
        point_x = max(0, min(1000, int(round(float(payload.get("x") or 0)))))
        point_y = max(0, min(1000, int(round(float(payload.get("y") or 0)))))
    except (TypeError, ValueError, json.JSONDecodeError):
        clear_query_param(MAIN_IMAGE_A_PLUS_TEXT_POINT_QUERY_KEY)
        return None
    clear_query_param(MAIN_IMAGE_A_PLUS_TEXT_POINT_QUERY_KEY)
    return point_x, point_y


def _extract_strict_json_object(
    response_text,
    empty_message,
    *,
    json,
    re,
) -> dict[str, Any]:
    raw_text = str(response_text or "").strip()
    if not raw_text:
        raise RuntimeError(empty_message)
    candidates = [raw_text]
    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text, re.IGNORECASE)
    if fenced_match:
        candidates.insert(0, fenced_match.group(1).strip())
    object_start, object_end = raw_text.find("{"), raw_text.rfind("}")
    if object_start >= 0 and object_end > object_start:
        candidates.append(raw_text[object_start : object_end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    raise RuntimeError("A+ 版式解析结果不是有效 JSON，请重新解析。")


def _layout_skill_string_list(
    value,
    max_items,
    *,
    _layout_skill_text,
    re,
) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\n；;]+", value)
    elif isinstance(value, (list, tuple)):
        raw_items = list(value)
    else:
        raw_items = []
    items: list[str] = []
    for raw_item in raw_items:
        item = _layout_skill_text(raw_item)
        if item and item not in items:
            items.append(item)
        if len(items) >= max_items:
            break
    return items


def _normalize_layout_skill_elements(
    value,
    max_items,
    *,
    Any,
    _layout_skill_bbox,
    _layout_skill_text,
) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for raw_element in list(value or []) if isinstance(value, (list, tuple)) else []:
        if not isinstance(raw_element, dict):
            continue
        bbox = _layout_skill_bbox(raw_element.get("bbox") or raw_element.get("region"))
        if not bbox:
            continue
        element_type = _layout_skill_text(raw_element.get("type") or "other", 32).lower()
        elements.append(
            {
                "type": element_type or "other",
                "bbox": bbox,
                "alignment": _layout_skill_text(raw_element.get("alignment"), 48),
                "overlap": _layout_skill_text(
                    raw_element.get("overlap") or raw_element.get("occlusion"),
                    96,
                ),
            }
        )
        if len(elements) >= max_items:
            break
    return elements


def _normalize_layout_skill_hero(
    value,
    *,
    _layout_skill_int,
    _layout_skill_ratio,
    _layout_skill_text,
    _normalize_layout_skill_elements,
) -> dict[str, Any]:
    raw_hero = dict(value or {}) if isinstance(value, dict) else {}
    visual_center = raw_hero.get("visual_center") or [500, 250]
    if not isinstance(visual_center, (list, tuple)) or len(visual_center) < 2:
        visual_center = [500, 250]
    try:
        center = [
            round(max(0, min(1000, float(visual_center[0])))),
            round(max(0, min(1000, float(visual_center[1])))),
        ]
    except (TypeError, ValueError):
        center = [500, 250]
    return {
        "height_ratio": _layout_skill_ratio(raw_hero.get("height_ratio"), 0.3),
        "visual_center": center,
        "product_position": _layout_skill_text(raw_hero.get("product_position"), 64),
        "model_position": _layout_skill_text(raw_hero.get("model_position"), 64),
        "text_blocks": _layout_skill_int(raw_hero.get("text_blocks"), maximum=12),
        "text_area_ratio": _layout_skill_ratio(raw_hero.get("text_area_ratio")),
        "elements": _normalize_layout_skill_elements(raw_hero.get("elements")),
    }


def analyze_a_plus_layout_cases(
    case_inputs,
    previous_common,
    *,
    A_PLUS_SKILL_MAX_CASES,
    DEFAULT_ASPECT_RATIO,
    MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
    _extract_strict_json_object,
    build_a_plus_layout_analysis_prompt,
    call_openrouter,
    normalize_a_plus_layout_skill_analysis,
) -> dict[str, Any]:
    normalized_inputs = list(case_inputs or [])[:A_PLUS_SKILL_MAX_CASES]
    if not normalized_inputs:
        raise RuntimeError("请至少上传 1 张优秀 A+ 完整案例。")
    response = call_openrouter(
        model=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        prompt=build_a_plus_layout_analysis_prompt(normalized_inputs, previous_common),
        uploaded_files=normalized_inputs,
        output_mode="text",
        aspect_ratio=DEFAULT_ASPECT_RATIO,
    )
    payload = _extract_strict_json_object(
        str(response.get("text") or ""),
        "A+ 版式解析没有返回结果，请重新解析。",
    )
    return normalize_a_plus_layout_skill_analysis(payload, normalized_inputs)


def get_main_image_a_plus_layout_device(layout) -> str:
    if isinstance(layout, dict):
        layout_key = str(layout.get("key") or "")
        target_size = tuple(layout.get("target_size") or ())
    else:
        layout_key = str(layout or "")
        target_size = ()
    if layout_key.startswith("mobile"):
        return "mobile"
    if layout_key.startswith("desktop"):
        return "desktop"
    if len(target_size) == 2:
        return "mobile" if int(target_size[0]) <= 600 else "desktop"
    return ""


def build_main_image_a_plus_continuity_reference(
    image_url,
    target_width,
    target_height,
    base_name,
    *,
    Image,
    ImageOps,
    Path,
    cover_image_to_canvas_without_distortion,
    io,
    load_image_bytes_from_url,
    sanitize_file_name,
) -> dict[str, Any]:
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = ImageOps.exif_transpose(image).convert("RGB")
            expected_size = (max(int(target_width), 1), max(int(target_height), 1))
            if working.size != expected_size:
                working = cover_image_to_canvas_without_distortion(working, *expected_size)
            output = io.BytesIO()
            working.save(output, format="JPEG", quality=88, optimize=True, subsampling=0)
    except Exception as exc:
        raise RuntimeError(f"A+ 连续片段参考图压缩失败：{exc}") from exc
    safe_stem = Path(sanitize_file_name(base_name or "a_plus_continuity")).stem
    return {
        "data": output.getvalue(),
        "name": f"{safe_stem}.jpg",
        "type": "image/jpeg",
    }
