"""Canvas geometry and quality checks for image outpainting."""

import io
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat


def get_outpaint_extension_limits(
    original_input: Any,
    *,
    OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
    OUTPAINT_MAX_CANVAS_MULTIPLIER,
    get_uploaded_input_dimensions,
) -> dict[str, int]:
    source_w, source_h = get_uploaded_input_dimensions(original_input)
    per_side_factor = max((float(OUTPAINT_MAX_CANVAS_MULTIPLIER) - 1.0) / 2.0, 0.0)
    horizontal_limit = min(
        OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
        max(int(round(source_w * per_side_factor)), 0),
    )
    vertical_limit = min(
        OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
        max(int(round(source_h * per_side_factor)), 0),
    )
    return {
        "top": vertical_limit,
        "bottom": vertical_limit,
        "left": horizontal_limit,
        "right": horizontal_limit,
    }


def clamp_outpaint_extensions(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    *,
    get_outpaint_extension_limits,
) -> tuple[int, int, int, int]:
    limits = get_outpaint_extension_limits(original_input)
    return (
        max(0, min(limits["top"], int(top_px))),
        max(0, min(limits["bottom"], int(bottom_px))),
        max(0, min(limits["left"], int(left_px))),
        max(0, min(limits["right"], int(right_px))),
    )


def get_outpaint_default_extension(direction_limit: int) -> int:
    limit = max(int(direction_limit), 0)
    if limit <= 0:
        return 0
    target = limit * 0.5
    if limit < 50:
        return max(1, int(round(target)))
    return max(50, min(limit, int(round(target / 50.0) * 50)))


def get_outpaint_target_canvas_size(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    *,
    clamp_outpaint_extensions,
    get_uploaded_input_dimensions,
) -> tuple[int, int]:
    try:
        source_w, source_h = get_uploaded_input_dimensions(original_input)
        top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
            original_input,
            top_px,
            bottom_px,
            left_px,
            right_px,
        )
        return (
            max(1, source_w + left_px + right_px),
            max(1, source_h + top_px + bottom_px),
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"模特扩图失败：无法读取原图尺寸。{exc}") from exc


def get_outpaint_target_aspect_ratio(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    fallback: str,
    *,
    DEFAULT_ASPECT_RATIO,
    get_outpaint_target_canvas_size,
    select_closest_aspect_ratio,
) -> str:
    try:
        return select_closest_aspect_ratio(
            get_outpaint_target_canvas_size(
                original_input,
                top_px,
                bottom_px,
                left_px,
                right_px,
            )
        )
    except Exception:
        return str(fallback or DEFAULT_ASPECT_RATIO)


def build_outpaint_source_framing_instruction(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    *,
    clamp_outpaint_extensions,
    get_uploaded_input_dimensions,
) -> str:
    source_w, source_h = get_uploaded_input_dimensions(original_input)
    top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    target_w = source_w + left_px + right_px
    target_h = source_h + top_px + bottom_px
    width_share = (source_w / target_w) * 100.0
    height_share = (source_h / target_h) * 100.0
    left_share = (left_px / target_w) * 100.0
    right_share = (right_px / target_w) * 100.0
    top_share = (top_px / target_h) * 100.0
    bottom_share = (bottom_px / target_h) * 100.0
    source_area_share = ((source_w * source_h) / float(target_w * target_h)) * 100.0
    new_area_share = max(0.0, 100.0 - source_area_share)
    return (
        f"Use an exact conceptual target canvas of {target_w}x{target_h}px. "
        f"The uploaded source field begins at target-canvas coordinate x={left_px}px, y={top_px}px and occupies the rectangle "
        f"[{left_px}, {top_px}] to [{left_px + source_w}, {top_px + source_h}]. "
        "MANDATORY OUTPAINT FRAMING GEOMETRY — this overrides any instruction to keep the old crop or old subject size. "
        f"The uploaded source field of view must occupy only about {width_share:.1f}% of the final frame width and {height_share:.1f}% of the final frame height. "
        f"Place that conceptual source field with about {left_share:.1f}% new visual space on the left, {right_share:.1f}% on the right, {top_share:.1f}% above, and {bottom_share:.1f}% below. "
        f"Approximately {new_area_share:.1f}% of the final frame area must show genuinely new, naturally continued scene content that was outside the uploaded crop. "
        "These percentages describe field-of-view geometry only; do not draw a box, border, inset, or pasted source rectangle. "
        "The requested percentages and offsets are strict. Do not symmetrize unequal sides, do not center the source unless the selected margins are equal, and keep every zero-expansion side flush with the final output edge. "
        "The final result must show an unmistakably wider/taller camera view and visibly more surroundings. "
        "Returning the same crop, the same subject frame occupancy, a merely retouched copy, or an image with no clearly visible new outer scene is a failed result."
    )


def build_outpaint_region_guide(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    *,
    OUTPAINT_GUIDE_MAX_EDGE,
    clamp_outpaint_extensions,
    get_uploaded_input_dimensions,
) -> dict[str, Any]:
    source_w, source_h = get_uploaded_input_dimensions(original_input)
    top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    target_w = source_w + left_px + right_px
    target_h = source_h + top_px + bottom_px
    scale = min(OUTPAINT_GUIDE_MAX_EDGE / float(max(target_w, target_h)), 1.0)
    guide_w = max(32, int(round(target_w * scale)))
    guide_h = max(32, int(round(target_h * scale)))
    guide = Image.new("RGB", (guide_w, guide_h), (0, 0, 0))
    draw = ImageDraw.Draw(guide)
    source_box = (
        int(round(left_px / target_w * guide_w)),
        int(round(top_px / target_h * guide_h)),
        int(round((left_px + source_w) / target_w * guide_w)) - 1,
        int(round((top_px + source_h) / target_h * guide_h)) - 1,
    )
    draw.rectangle(source_box, fill=(255, 255, 255))
    output = io.BytesIO()
    guide.save(output, format="PNG", optimize=True)
    return {
        "data": output.getvalue(),
        "name": "outpaint_region_layout_mask.png",
        "type": "image/png",
    }


def build_outpaint_source_canvas(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    *,
    OUTPAINT_GUIDE_MAX_EDGE,
    OUTPAINT_SCAFFOLD_BLUR_RATIO,
    OUTPAINT_TRANSITION_CLEAR_RATIO,
    OUTPAINT_TRANSITION_FEATHER_RATIO,
    clamp_outpaint_extensions,
    get_uploaded_file_bytes,
    get_uploaded_input_dimensions,
) -> dict[str, Any]:
    """Build an opaque edge-color scaffold so the source is not perceived as an inset photo."""
    source_w, source_h = get_uploaded_input_dimensions(original_input)
    top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    target_w = source_w + left_px + right_px
    target_h = source_h + top_px + bottom_px
    scale = min(OUTPAINT_GUIDE_MAX_EDGE / float(max(target_w, target_h)), 1.0)
    canvas_w = max(32, int(round(target_w * scale)))
    canvas_h = max(32, int(round(target_h * scale)))
    source_left = int(round((left_px / target_w) * canvas_w))
    source_top = int(round((top_px / target_h) * canvas_h))
    source_right = int(round(((left_px + source_w) / target_w) * canvas_w))
    source_bottom = int(round(((top_px + source_h) / target_h) * canvas_h))
    source_right = max(source_right, source_left + 1)
    source_bottom = max(source_bottom, source_top + 1)

    image_bytes = get_uploaded_file_bytes(original_input)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            source = ImageOps.exif_transpose(image).convert("RGBA")
            source = source.resize(
                (source_right - source_left, source_bottom - source_top),
                Image.Resampling.LANCZOS,
            )
            source_width, source_height = source.size
            horizontal_clear = max(
                4,
                min(128, int(round(source_width * OUTPAINT_TRANSITION_CLEAR_RATIO))),
            )
            vertical_clear = max(
                4,
                min(128, int(round(source_height * OUTPAINT_TRANSITION_CLEAR_RATIO))),
            )
            horizontal_feather = max(
                8,
                min(256, int(round(source_width * OUTPAINT_TRANSITION_FEATHER_RATIO))),
            )
            vertical_feather = max(
                8,
                min(256, int(round(source_height * OUTPAINT_TRANSITION_FEATHER_RATIO))),
            )
            x_alpha = [255] * source_width
            y_alpha = [255] * source_height
            if left_px > 0:
                for x in range(min(horizontal_clear, source_width)):
                    x_alpha[x] = 0
                feather_start = min(horizontal_clear, source_width)
                feather_end = min(feather_start + horizontal_feather, source_width)
                feather_span = max(feather_end - feather_start, 1)
                for x in range(feather_start, feather_end):
                    progress = (x - feather_start + 1) / float(feather_span + 1)
                    smooth_progress = progress * progress * (3.0 - (2.0 * progress))
                    x_alpha[x] = min(x_alpha[x], int(round(255 * smooth_progress)))
            if right_px > 0:
                for offset in range(min(horizontal_clear, source_width)):
                    x = source_width - 1 - offset
                    x_alpha[x] = 0
                feather_start = min(horizontal_clear, source_width)
                feather_end = min(feather_start + horizontal_feather, source_width)
                feather_span = max(feather_end - feather_start, 1)
                for offset in range(feather_start, feather_end):
                    x = source_width - 1 - offset
                    progress = (offset - feather_start + 1) / float(feather_span + 1)
                    smooth_progress = progress * progress * (3.0 - (2.0 * progress))
                    x_alpha[x] = min(x_alpha[x], int(round(255 * smooth_progress)))
            if top_px > 0:
                for y in range(min(vertical_clear, source_height)):
                    y_alpha[y] = 0
                feather_start = min(vertical_clear, source_height)
                feather_end = min(feather_start + vertical_feather, source_height)
                feather_span = max(feather_end - feather_start, 1)
                for y in range(feather_start, feather_end):
                    progress = (y - feather_start + 1) / float(feather_span + 1)
                    smooth_progress = progress * progress * (3.0 - (2.0 * progress))
                    y_alpha[y] = min(y_alpha[y], int(round(255 * smooth_progress)))
            if bottom_px > 0:
                for offset in range(min(vertical_clear, source_height)):
                    y = source_height - 1 - offset
                    y_alpha[y] = 0
                feather_start = min(vertical_clear, source_height)
                feather_end = min(feather_start + vertical_feather, source_height)
                feather_span = max(feather_end - feather_start, 1)
                for offset in range(feather_start, feather_end):
                    y = source_height - 1 - offset
                    progress = (offset - feather_start + 1) / float(feather_span + 1)
                    smooth_progress = progress * progress * (3.0 - (2.0 * progress))
                    y_alpha[y] = min(y_alpha[y], int(round(255 * smooth_progress)))
            transition_alpha = Image.new("L", (source_width, source_height), 255)
            transition_alpha.putdata(
                [
                    min(x_alpha[x], y_alpha[y])
                    for y in range(source_height)
                    for x in range(source_width)
                ]
            )
            # Image-generation chat APIs do not reliably interpret PNG transparency as
            # an edit mask. A transparent canvas can therefore make the opaque source
            # look like a pasted picture, prompting the model to draw a second subject
            # around it. Fill the whole target with edge colors first, blur that
            # disposable scaffold, then blend the trusted source through a broad mask.
            canvas = Image.new(
                "RGBA",
                (canvas_w, canvas_h),
                source.getpixel((0, 0)),
            )
            canvas.alpha_composite(source, (source_left, source_top))
            if source_left > 0:
                left_strip = source.crop((0, 0, 1, source_height)).resize(
                    (source_left, source_height),
                    Image.Resampling.BICUBIC,
                )
                canvas.alpha_composite(left_strip, (0, source_top))
            if source_right < canvas_w:
                right_strip = source.crop(
                    (source_width - 1, 0, source_width, source_height)
                ).resize(
                    (canvas_w - source_right, source_height),
                    Image.Resampling.BICUBIC,
                )
                canvas.alpha_composite(right_strip, (source_right, source_top))
            if source_top > 0:
                top_strip = canvas.crop((0, source_top, canvas_w, source_top + 1)).resize(
                    (canvas_w, source_top),
                    Image.Resampling.BICUBIC,
                )
                canvas.alpha_composite(top_strip, (0, 0))
            if source_bottom < canvas_h:
                bottom_strip = canvas.crop(
                    (0, source_bottom - 1, canvas_w, source_bottom)
                ).resize(
                    (canvas_w, canvas_h - source_bottom),
                    Image.Resampling.BICUBIC,
                )
                canvas.alpha_composite(bottom_strip, (0, source_bottom))

            blur_radius = max(
                4,
                min(
                    64,
                    int(
                        round(
                            min(source_width, source_height)
                            * OUTPAINT_SCAFFOLD_BLUR_RATIO
                        )
                    ),
                ),
            )
            canvas = canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            source.putalpha(255)
            canvas.paste(source, (source_left, source_top), transition_alpha)
            canvas.putalpha(255)
            output = io.BytesIO()
            canvas.save(output, format="PNG", optimize=True)
    except Exception as exc:
        raise RuntimeError(f"扩图定位画布生成失败：{exc}") from exc
    return {
        "data": output.getvalue(),
        "name": "outpaint_transition_canvas.png",
        "type": "image/png",
    }


def is_outpaint_result_effectively_unchanged(
    image_url: str,
    original_input: Any,
    *,
    get_uploaded_file_bytes,
    load_image_bytes_from_url,
) -> bool:
    """Detect an unchanged or merely re-encoded source crop before accepting it."""
    try:
        original_bytes = get_uploaded_file_bytes(original_input)
        result_bytes, _mime_type = load_image_bytes_from_url(image_url)
        with Image.open(io.BytesIO(original_bytes)) as original_image:
            original = ImageOps.exif_transpose(original_image).convert("RGB")
        with Image.open(io.BytesIO(result_bytes)) as result_image:
            result = ImageOps.exif_transpose(result_image).convert("RGB")
        comparison_size = (64, 64)
        original_thumb = original.resize(comparison_size, Image.Resampling.LANCZOS)
        result_thumb = result.resize(comparison_size, Image.Resampling.LANCZOS)
        color_difference = ImageStat.Stat(
            ImageChops.difference(original_thumb, result_thumb)
        ).mean
        original_edges = original_thumb.filter(ImageFilter.FIND_EDGES)
        result_edges = result_thumb.filter(ImageFilter.FIND_EDGES)
        edge_difference = ImageStat.Stat(
            ImageChops.difference(original_edges, result_edges)
        ).mean
        normalized_color_difference = sum(color_difference[:3]) / (3.0 * 255.0)
        normalized_edge_difference = sum(edge_difference[:3]) / (3.0 * 255.0)
        return normalized_color_difference < 0.035 and normalized_edge_difference < 0.025
    except Exception:
        return False


def crop_outpaint_result_to_selected_region(
    image_url: str,
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    *,
    clamp_outpaint_extensions,
    get_outpaint_target_canvas_size,
    image_bytes_to_data_url,
    load_image_bytes_from_url,
) -> str:
    """Crop to the selected ratio, then return the exact selected pixel dimensions."""
    target_w, target_h = get_outpaint_target_canvas_size(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = ImageOps.exif_transpose(image).convert("RGB")
            source_w, source_h = working.size
            target_ratio = target_w / float(target_h)
            source_ratio = source_w / float(source_h)
            crop_left = 0
            crop_top = 0
            crop_right = source_w
            crop_bottom = source_h
            if source_ratio > target_ratio:
                crop_width = max(1, min(source_w, int(round(source_h * target_ratio))))
                surplus = max(source_w - crop_width, 0)
                horizontal_total = left_px + right_px
                left_share = (left_px / horizontal_total) if horizontal_total > 0 else 0.5
                crop_left = max(0, min(surplus, int(round(surplus * left_share))))
                crop_right = crop_left + crop_width
            elif source_ratio < target_ratio:
                crop_height = max(1, min(source_h, int(round(source_w / target_ratio))))
                surplus = max(source_h - crop_height, 0)
                vertical_total = top_px + bottom_px
                top_share = (top_px / vertical_total) if vertical_total > 0 else 0.5
                crop_top = max(0, min(surplus, int(round(surplus * top_share))))
                crop_bottom = crop_top + crop_height
            unchanged_crop = (crop_left, crop_top, crop_right, crop_bottom) == (
                0,
                0,
                source_w,
                source_h,
            )
            if unchanged_crop and working.size == (target_w, target_h):
                return image_url
            cropped = (
                working
                if unchanged_crop
                else working.crop((crop_left, crop_top, crop_right, crop_bottom))
            )
            if cropped.size != (target_w, target_h):
                cropped = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            cropped.save(output, format="PNG", optimize=True)
        return image_bytes_to_data_url(output.getvalue(), "image/png")
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc).startswith("图片下载失败："):
            raise
        raise RuntimeError(f"扩图结果范围校正失败：{exc}") from exc


def measure_outpaint_boundary_seams(
    image_url: str,
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    *,
    OUTPAINT_MULTISCALE_SEAM_RATIO_THRESHOLD,
    OUTPAINT_MULTISCALE_SEAM_STRENGTH_THRESHOLD,
    OUTPAINT_SEAM_RATIO_THRESHOLD,
    OUTPAINT_SEAM_STRENGTH_THRESHOLD,
    clamp_outpaint_extensions,
    get_outpaint_target_canvas_size,
    get_uploaded_input_dimensions,
    load_image_bytes_from_url,
) -> list[dict[str, Any]]:
    """Measure narrow and broad discontinuities at former source boundaries."""
    target_w, target_h = get_outpaint_target_canvas_size(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    source_w, source_h = get_uploaded_input_dimensions(original_input)
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)

    def median(values: list[float]) -> float:
        ordered = sorted(values)
        if not ordered:
            return 0.0
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / 2.0

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = ImageOps.exif_transpose(image).convert("RGB")
            width, height = working.size
            scale_x = width / float(max(target_w, 1))
            scale_y = height / float(max(target_h, 1))
            minimum_edge = min(width, height)
            search_radius = max(2, min(24, int(round(minimum_edge * 0.004))))
            maximum_gap = max(16, min(24, int(round(minimum_edge * 0.008))))
            gap_candidates = sorted(
                {
                    gap
                    for gap in (1, 2, 4, 8, 12, 16, 24, maximum_gap)
                    if gap <= maximum_gap
                }
            )
            baseline_span = max(32, min(128, int(round(minimum_edge * 0.05))))

            def boundary_strength(
                axis: str,
                position: int,
                sample_gap: int,
                span_start: int,
                span_end: int,
            ) -> float:
                if axis == "vertical":
                    first_x = max(0, min(width - 1, int(position) - sample_gap))
                    second_x = max(0, min(width - 1, int(position) + sample_gap - 1))
                    first = working.crop((first_x, span_start, first_x + 1, span_end))
                    second = working.crop((second_x, span_start, second_x + 1, span_end))
                else:
                    first_y = max(0, min(height - 1, int(position) - sample_gap))
                    second_y = max(0, min(height - 1, int(position) + sample_gap - 1))
                    first = working.crop((span_start, first_y, span_end, first_y + 1))
                    second = working.crop((span_start, second_y, span_end, second_y + 1))
                channel_means = ImageStat.Stat(ImageChops.difference(first, second)).mean
                return sum(channel_means[:3]) / 3.0

            vertical_span = (
                int(round(top_px * scale_y)),
                int(round((top_px + source_h) * scale_y)),
            )
            horizontal_span = (
                int(round(left_px * scale_x)),
                int(round((left_px + source_w) * scale_x)),
            )
            candidates: list[tuple[str, str, int, tuple[int, int]]] = []
            if left_px > 0:
                candidates.append(
                    ("left", "vertical", int(round(left_px * scale_x)), vertical_span)
                )
            if right_px > 0:
                candidates.append(
                    (
                        "right",
                        "vertical",
                        int(round((left_px + source_w) * scale_x)),
                        vertical_span,
                    )
                )
            if top_px > 0:
                candidates.append(
                    ("top", "horizontal", int(round(top_px * scale_y)), horizontal_span)
                )
            if bottom_px > 0:
                candidates.append(
                    (
                        "bottom",
                        "horizontal",
                        int(round((top_px + source_h) * scale_y)),
                        horizontal_span,
                    )
                )

            measurements: list[dict[str, Any]] = []
            for side, axis, position, raw_span in candidates:
                axis_limit = width - 1 if axis == "vertical" else height - 1
                span_limit = height if axis == "vertical" else width
                span_start = max(0, min(span_limit - 1, int(raw_span[0])))
                span_end = max(span_start + 1, min(span_limit, int(raw_span[1])))
                span_trim = min(
                    max(0, int(round((span_end - span_start) * 0.025))),
                    max((span_end - span_start - 2) // 2, 0),
                )
                span_start += span_trim
                span_end -= span_trim

                scale_measurements: list[dict[str, Any]] = []
                for sample_gap in gap_candidates:
                    search_start = max(sample_gap, position - search_radius)
                    search_end = min(axis_limit - sample_gap + 1, position + search_radius)
                    nearby = [
                        (
                            candidate_position,
                            boundary_strength(
                                axis,
                                candidate_position,
                                sample_gap,
                                span_start,
                                span_end,
                            ),
                        )
                        for candidate_position in range(search_start, search_end + 1)
                    ]
                    peak_position, peak_strength = max(
                        nearby or [(position, 0.0)],
                        key=lambda item: item[1],
                    )
                    baseline_step = max(2, sample_gap // 2)
                    baseline_exclusion = search_radius + (sample_gap * 2) + 2
                    baseline_positions = [
                        position + offset
                        for offset in range(
                            -baseline_span,
                            baseline_span + 1,
                            baseline_step,
                        )
                        if abs(offset) >= baseline_exclusion
                        and sample_gap <= position + offset <= axis_limit - sample_gap + 1
                    ]
                    baseline_strengths = [
                        boundary_strength(
                            axis,
                            candidate_position,
                            sample_gap,
                            span_start,
                            span_end,
                        )
                        for candidate_position in baseline_positions
                    ]
                    baseline_strength = max(median(baseline_strengths), 0.1)
                    strength_ratio = peak_strength / baseline_strength
                    if sample_gap <= 2:
                        detected = (
                            peak_strength >= OUTPAINT_SEAM_STRENGTH_THRESHOLD
                            and strength_ratio >= OUTPAINT_SEAM_RATIO_THRESHOLD
                        )
                    else:
                        detected = (
                            peak_strength >= OUTPAINT_MULTISCALE_SEAM_STRENGTH_THRESHOLD
                            and strength_ratio >= OUTPAINT_MULTISCALE_SEAM_RATIO_THRESHOLD
                        )
                    scale_measurements.append(
                        {
                            "position": peak_position,
                            "gap": sample_gap,
                            "strength": peak_strength,
                            "baseline": baseline_strength,
                            "ratio": strength_ratio,
                            "detected": detected,
                        }
                    )
                best_measurement = max(
                    scale_measurements,
                    key=lambda item: (
                        bool(item.get("detected")),
                        float(item.get("ratio") or 0.0),
                        float(item.get("strength") or 0.0),
                    ),
                    default={
                        "position": position,
                        "gap": 1,
                        "strength": 0.0,
                        "baseline": 0.1,
                        "ratio": 0.0,
                        "detected": False,
                    },
                )
                measurements.append(
                    {
                        "side": side,
                        "axis": axis,
                        **best_measurement,
                    }
                )
            return measurements
    except Exception:
        return []


def has_outpaint_rectangular_join(measurements: list[dict[str, Any]]) -> bool:
    """Require rectangle-like evidence so natural single scene edges are not over-rejected."""
    detected = [item for item in measurements if bool(item.get("detected"))]
    if len(detected) >= 2:
        return True
    return any(
        float(item.get("strength") or 0.0) >= 16.0
        and float(item.get("ratio") or 0.0) >= 3.25
        for item in detected
    )


def build_outpaint_seam_repair_reference(
    image_url: str,
    *,
    OUTPAINT_GUIDE_MAX_EDGE,
    load_image_bytes_from_url,
) -> dict[str, Any]:
    """Build a compact full-frame reference for a second-pass seamless redraw."""
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = ImageOps.exif_transpose(image).convert("RGB")
            if max(working.size) > OUTPAINT_GUIDE_MAX_EDGE:
                scale = OUTPAINT_GUIDE_MAX_EDGE / float(max(working.size))
                working = working.resize(
                    (
                        max(1, int(round(working.size[0] * scale))),
                        max(1, int(round(working.size[1] * scale))),
                    ),
                    Image.Resampling.LANCZOS,
                )
            output = io.BytesIO()
            working.save(output, format="JPEG", quality=95, optimize=True)
    except Exception as exc:
        raise RuntimeError(f"扩图接缝修复参考图生成失败：{exc}") from exc
    return {
        "data": output.getvalue(),
        "name": "outpaint_seam_repair_reference.jpg",
        "type": "image/jpeg",
    }


def build_outpaint_seam_repair_prompt(
    original_input: Any,
    top_px: int,
    bottom_px: int,
    left_px: int,
    right_px: int,
    measurements: list[dict[str, Any]],
    *,
    clamp_outpaint_extensions,
    get_outpaint_target_canvas_size,
    get_uploaded_input_dimensions,
) -> str:
    target_w, target_h = get_outpaint_target_canvas_size(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    top_px, bottom_px, left_px, right_px = clamp_outpaint_extensions(
        original_input,
        top_px,
        bottom_px,
        left_px,
        right_px,
    )
    source_w, source_h = get_uploaded_input_dimensions(original_input)
    detected_sides = ", ".join(
        str(item.get("side") or "")
        for item in measurements
        if item.get("detected")
    )
    return (
        "MANDATORY FULL-FRAME SEAM REPAIR PASS. "
        "There is exactly one input image: a failed but otherwise useful expanded photograph. "
        "It contains a visible pasted or inset source rectangle. That rectangle is an artifact, not protected content. "
        f"The intended final geometry is {target_w}x{target_h}px. The former source rectangle runs from "
        f"x={left_px} to x={left_px + source_w} and y={top_px} to y={top_px + source_h}; "
        f"the strongest detected joins are on: {detected_sides or 'the former source boundaries'}. "
        "Re-render the complete photograph as one unified camera exposure and fully reconstruct broad corridors on both sides of every former rectangle boundary. "
        "Seam removal has higher priority than exact pixel preservation near those boundaries. "
        "Do not preserve, paste back, trace, frame, or outline the old center rectangle. "
        "Remove every straight tonal step, hard vertical or horizontal edge, texture-frequency change, duplicated object, broken line, and body or clothing discontinuity caused by the old join. "
        "Make walls, ceiling lines, furniture, floor, rug, hair, skin, clothing, limbs, lighting, perspective, sharpness, grain, and noise flow continuously across the whole frame. "
        "Keep the same single person, identity, face, expression, pose, clothing, room, camera viewpoint, and final composition, but allow natural resynthesis wherever required to make the image seamless. "
        "Return exactly one finished full-frame photograph with no inset image, collage, border, frame, split panel, or rectangular stitching trace."
    )
