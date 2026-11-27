"""Select and normalize A+ layouts and canvas dimensions."""

from __future__ import annotations

from typing import Any


def get_main_image_a_plus_layout(
    layout_key,
    *,
    MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY,
    MAIN_IMAGE_A_PLUS_LAYOUTS,
) -> dict[str, Any]:
    normalized_key = str(layout_key or "").strip()
    if normalized_key not in MAIN_IMAGE_A_PLUS_LAYOUTS:
        normalized_key = MAIN_IMAGE_A_PLUS_DEFAULT_LAYOUT_KEY
    layout = dict(MAIN_IMAGE_A_PLUS_LAYOUTS[normalized_key])
    layout["key"] = normalized_key
    layout["target_size"] = tuple(int(value) for value in layout["target_size"])
    layout["section_heights"] = tuple(int(value) for value in layout["section_heights"])
    return layout


def is_main_image_a_plus_mobile_size(
    canvas_size,
    *,
    infer_main_image_a_plus_screen_count,
) -> bool:
    try:
        width, height = (int(value) for value in canvas_size)
    except Exception:
        return False
    if width <= 0 or height <= width:
        return False
    screen_count = infer_main_image_a_plus_screen_count((width, height))
    expected_height = width * 0.75 * screen_count
    return abs(height - expected_height) <= max(4.0, expected_height * 0.015)


def select_main_image_a_plus_vertical_preserving_aspect_ratio(
    canvas_size,
    *,
    select_main_image_a_plus_safe_aspect_ratio,
) -> str:
    """Backward-compatible alias for the A+ text-safe native ratio selector."""
    return select_main_image_a_plus_safe_aspect_ratio(canvas_size)


def normalize_main_image_a_plus_mode(
    mode,
    *,
    MAIN_IMAGE_A_PLUS_MODE_FREE,
    MAIN_IMAGE_A_PLUS_MODE_LABELS,
) -> str:
    normalized_mode = str(mode or "").strip()
    if normalized_mode not in MAIN_IMAGE_A_PLUS_MODE_LABELS:
        return MAIN_IMAGE_A_PLUS_MODE_FREE
    return normalized_mode


def get_main_image_a_plus_template_signature(
    template_input,
    *,
    get_uploaded_file_bytes,
    hashlib,
) -> str:
    template_bytes = get_uploaded_file_bytes(template_input)
    return hashlib.sha1(template_bytes).hexdigest()[:16] if template_bytes else ""


def get_main_image_a_plus_text_edit_signature(
    source_image,
    *,
    hashlib,
) -> str:
    normalized_source = str(source_image or "").strip()
    return hashlib.sha1(normalized_source.encode("utf-8")).hexdigest()[:20]


def _layout_skill_text(
    value,
    max_length,
    *,
    re,
) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:max_length]


def _layout_skill_ratio(value, default) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if number > 1.0 and number <= 100.0:
        number /= 100.0
    return round(max(0.0, min(1.0, number)), 4)


def _layout_skill_int(
    value,
    default,
    minimum,
    maximum,
) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _layout_skill_bbox(
    value,
    *,
    normalize_main_image_a_plus_element_bbox,
) -> list[int]:
    normalized = normalize_main_image_a_plus_element_bbox(value, (1000, 1000))
    return normalized or []


def build_main_image_a_plus_designed_module_section_heights(target_height, section_count) -> tuple[int, ...]:
    safe_count = max(int(section_count), 1)
    base_height, remainder = divmod(max(int(target_height), safe_count), safe_count)
    return tuple(
        base_height + (1 if section_index < remainder else 0)
        for section_index in range(safe_count)
    )


def is_main_image_a_plus_mobile_canvas(
    image_source,
    *,
    Image,
    ImageOps,
    io,
    is_main_image_a_plus_mobile_size,
    load_image_bytes_from_url,
) -> bool:
    """Identify existing mobile A+ results by their canvas ratio without mutating them."""
    normalized_source = str(image_source or "").strip()
    if not normalized_source:
        return False
    try:
        image_bytes, _mime_type = load_image_bytes_from_url(normalized_source)
        with Image.open(io.BytesIO(image_bytes)) as image:
            normalized = ImageOps.exif_transpose(image)
            width, height = normalized.size
    except Exception:
        return False
    return is_main_image_a_plus_mobile_size((width, height))
