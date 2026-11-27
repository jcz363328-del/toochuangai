"""Resize, crop, split and stitch images without changing output geometry."""

from __future__ import annotations

from PIL import Image
from typing import Any


def split_main_image_a_plus_template(
    template_input,
    target_width,
    section_heights,
    *,
    Any,
    Image,
    ImageOps,
    fit_image_to_canvas_without_distortion,
    get_uploaded_file_bytes,
    io,
) -> list[dict[str, Any]]:
    if template_input is None:
        raise RuntimeError("套版替换需要先上传 1 张成品 A+ 模板。")
    template_bytes = get_uploaded_file_bytes(template_input)
    try:
        with Image.open(io.BytesIO(template_bytes)) as image:
            template = ImageOps.exif_transpose(image).convert("RGB")
            target_height = sum(section_heights)
            if template.size != (target_width, target_height):
                template = fit_image_to_canvas_without_distortion(
                    template,
                    target_width,
                    target_height,
                )
            sections: list[dict[str, Any]] = []
            start_y = 0
            for index, section_height in enumerate(section_heights, start=1):
                section = template.crop((0, start_y, target_width, start_y + section_height))
                output = io.BytesIO()
                section.save(output, format="PNG")
                sections.append(
                    {
                        "data": output.getvalue(),
                        "name": f"a_plus_layout_template_section_{index}.png",
                        "type": "image/png",
                    }
                )
                start_y += section_height
            return sections
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"成品 A+ 模板读取或拆分失败：{exc}") from exc


def stitch_main_image_a_plus_sections(
    section_image_urls,
    target_width,
    section_heights,
    *,
    Image,
    ImageOps,
    cover_image_to_canvas_without_distortion,
    image_bytes_to_data_url,
    io,
    load_image_bytes_from_url,
) -> str:
    if len(section_image_urls) != len(section_heights):
        raise RuntimeError("主图生A+分段数量不完整，无法合成长图。")
    target_height = sum(section_heights)
    canvas = Image.new("RGB", (target_width, target_height), "white")
    current_y = 0
    for section_image_url, section_height in zip(section_image_urls, section_heights):
        image_bytes, _mime_type = load_image_bytes_from_url(section_image_url)
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                section = ImageOps.exif_transpose(image).convert("RGB")
                if section.size != (target_width, section_height):
                    section = cover_image_to_canvas_without_distortion(
                        section,
                        target_width,
                        section_height,
                    )
                canvas.paste(section, (0, current_y))
        except Exception as exc:
            raise RuntimeError(f"主图生A+分段图片读取失败：{exc}") from exc
        current_y += section_height
    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return image_bytes_to_data_url(output.getvalue(), "image/png")


def resize_main_image_a_plus_mobile_single_layer(
    candidate_image_url,
    target_width,
    target_height,
    *,
    Image,
    ImageOps,
    cover_image_to_canvas_without_distortion,
    image_bytes_to_data_url,
    io,
    load_image_bytes_from_url,
) -> str:
    """Normalize the generated mobile canvas proportionally, cropping only its safe side fields."""
    candidate_bytes, _mime_type = load_image_bytes_from_url(candidate_image_url)
    try:
        with Image.open(io.BytesIO(candidate_bytes)) as candidate_image:
            candidate = ImageOps.exif_transpose(candidate_image).convert("RGB")
        if candidate.width <= 0 or candidate.height <= 0:
            raise ValueError("Candidate image dimensions are invalid.")
        exact_width = max(int(target_width), 1)
        exact_height = max(int(target_height), 1)
        fitted = cover_image_to_canvas_without_distortion(
            candidate,
            exact_width,
            exact_height,
        )
        output = io.BytesIO()
        fitted.save(output, format="PNG")
        return image_bytes_to_data_url(output.getvalue(), "image/png")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"手机端单层成品尺寸归一失败：{exc}") from exc


def detect_amazon_a_plus_section_boundaries(
    source,
    *,
    AMAZON_TO_WALMART_PAGE_COUNT,
    _amazon_a_plus_row_profile,
) -> list[int]:
    """Find the four content-section cuts instead of slicing the canvas into equal quarters."""
    count = AMAZON_TO_WALMART_PAGE_COUNT
    nominal = [round(source.height * index / count) for index in range(count + 1)]
    try:
        means, stds, sample_height = _amazon_a_plus_row_profile(source)
    except Exception:
        return nominal
    if len(means) < count * 2:
        return nominal
    max_std = max(stds) or 1.0
    jumps = [0.0]
    for index in range(1, len(means)):
        jumps.append(abs(means[index] - means[index - 1]))
    max_jump = max(jumps) or 1.0
    scores = [
        0.55 * (1.0 - stds[index] / max_std) + 0.45 * (jumps[index] / max_jump)
        for index in range(len(means))
    ]
    section = source.height / count
    boundaries = [0]
    for index in range(1, count):
        center = nominal[index]
        window = section * 0.08
        low = max(int(boundaries[-1] + section * 0.45), int(center - window))
        high = min(int(source.height - section * 0.45 * (count - index)), int(center + window))
        if low >= high:
            boundaries.append(center)
            continue
        sample_low = max(1, int(low * sample_height / source.height))
        sample_high = min(len(scores) - 1, int(high * sample_height / source.height))
        if sample_high <= sample_low:
            boundaries.append(center)
            continue
        best_index = max(range(sample_low, sample_high), key=lambda row: scores[row])
        if scores[best_index] < 0.5:
            boundaries.append(center)
            continue
        boundaries.append(int(round(best_index * source.height / sample_height)))
    boundaries.append(source.height)
    return boundaries


def split_amazon_a_plus_source(
    uploaded_input,
    *,
    AMAZON_TO_WALMART_PAGE_COUNT,
    Any,
    Image,
    ImageOps,
    detect_amazon_a_plus_section_boundaries,
    get_uploaded_file_bytes,
    io,
    prepare_openrouter_uploaded_input,
) -> tuple[list[dict[str, Any]], bool]:
    """Return four ordered source sections when the upload is a long A+ canvas."""
    image_bytes = get_uploaded_file_bytes(uploaded_input)
    if not image_bytes:
        raise RuntimeError("上传的亚马逊 A+ 图片为空，请重新上传。")
    try:
        with Image.open(io.BytesIO(image_bytes)) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGB")
            is_long_canvas = source.height >= source.width * 1.2
            if not is_long_canvas:
                normalized = prepare_openrouter_uploaded_input(uploaded_input)
                return [normalized for _index in range(AMAZON_TO_WALMART_PAGE_COUNT)], False
            boundaries = detect_amazon_a_plus_section_boundaries(source)
            sections: list[dict[str, Any]] = []
            for index in range(AMAZON_TO_WALMART_PAGE_COUNT):
                crop = source.crop((0, boundaries[index], source.width, boundaries[index + 1]))
                output = io.BytesIO()
                crop.save(output, format="PNG", optimize=True)
                sections.append(
                    prepare_openrouter_uploaded_input(
                        {
                            "data": output.getvalue(),
                            "name": f"amazon_a_plus_section_{index + 1}.png",
                            "type": "image/png",
                        }
                    )
                )
            return sections, True
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"无法读取亚马逊 A+ 图片：{exc}") from exc


def upscale_image_to_min_edge(
    image_url,
    min_edge,
    enhance_detail,
    *,
    Image,
    ImageEnhance,
    ImageFilter,
    MIN_OUTPUT_EDGE,
    image_bytes_to_data_url,
    io,
    load_image_bytes_from_url,
    math,
) -> str:
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = image.convert("RGB")
            width, height = converted.size
            if width <= 0 or height <= 0:
                raise RuntimeError("返回的图片尺寸无效。")
            adaptive_min_edge = max(int(min_edge or 0), MIN_OUTPUT_EDGE)
            scale = max(adaptive_min_edge / width, adaptive_min_edge / height, 1.0)
            if scale > 1.001:
                target_width = max(math.ceil(width * scale), adaptive_min_edge)
                target_height = max(math.ceil(height * scale), adaptive_min_edge)
                resized = converted.resize(
                    (target_width, target_height),
                    Image.Resampling.LANCZOS,
                )
            else:
                resized = converted.copy()
            if enhance_detail:
                # Preserve zoomed detail while keeping skin texture natural and less harsh.
                resized = resized.filter(ImageFilter.DETAIL)
                resized = ImageEnhance.Contrast(resized).enhance(1.05)
                resized = resized.filter(ImageFilter.UnsharpMask(radius=1.2, percent=172, threshold=3))
                resized = resized.filter(ImageFilter.UnsharpMask(radius=0.55, percent=96, threshold=2))
                resized = ImageEnhance.Sharpness(resized).enhance(1.22)
            output = io.BytesIO()
            resized.save(output, format="PNG")
        return image_bytes_to_data_url(output.getvalue(), "image/png")
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc).startswith("图片下载失败："):
            raise
        raise RuntimeError(f"本地处理失败：返回图片已收到，但在本地放大处理时出错。{exc}") from exc


def fit_image_to_canvas_without_distortion(
    image,
    target_width,
    target_height,
    *,
    Image,
    ImageOps,
    ImageStat,
) -> Image.Image:
    """Fit the complete image on an exact canvas without changing its aspect ratio."""
    safe_target_width = max(int(target_width), 1)
    safe_target_height = max(int(target_height), 1)
    source = ImageOps.exif_transpose(image).convert("RGB")
    if source.width <= 0 or source.height <= 0:
        raise ValueError("Source image dimensions are invalid.")

    scale = min(
        safe_target_width / float(source.width),
        safe_target_height / float(source.height),
    )
    resized_width = max(1, min(safe_target_width, int(round(source.width * scale))))
    resized_height = max(1, min(safe_target_height, int(round(source.height * scale))))
    resized = source.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    if resized.size == (safe_target_width, safe_target_height):
        return resized

    edge_depth = max(1, min(24, source.width // 20 or 1, source.height // 20 or 1))
    edge_regions = (
        source.crop((0, 0, source.width, edge_depth)),
        source.crop((0, source.height - edge_depth, source.width, source.height)),
        source.crop((0, 0, edge_depth, source.height)),
        source.crop((source.width - edge_depth, 0, source.width, source.height)),
    )
    edge_means = [ImageStat.Stat(region).mean[:3] for region in edge_regions]
    background_color = tuple(
        max(0, min(255, int(round(sum(mean[channel] for mean in edge_means) / len(edge_means)))))
        for channel in range(3)
    )
    canvas = Image.new("RGB", (safe_target_width, safe_target_height), background_color)
    offset = (
        (safe_target_width - resized_width) // 2,
        (safe_target_height - resized_height) // 2,
    )
    canvas.paste(resized, offset)
    return canvas


def cover_image_to_canvas_without_distortion(
    image,
    target_width,
    target_height,
    horizontal_anchor,
    vertical_anchor,
    *,
    Image,
    ImageOps,
    math,
) -> Image.Image:
    """Fill an exact canvas without stretching or adding letterbox borders."""
    safe_target_width = max(int(target_width), 1)
    safe_target_height = max(int(target_height), 1)
    source = ImageOps.exif_transpose(image).convert("RGB")
    if source.width <= 0 or source.height <= 0:
        raise ValueError("Source image dimensions are invalid.")

    scale = max(
        safe_target_width / float(source.width),
        safe_target_height / float(source.height),
    )
    resized_width = max(safe_target_width, int(math.ceil(source.width * scale)))
    resized_height = max(safe_target_height, int(math.ceil(source.height * scale)))
    resized = source.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    extra_width = max(resized_width - safe_target_width, 0)
    extra_height = max(resized_height - safe_target_height, 0)
    normalized_horizontal_anchor = str(horizontal_anchor or "center").strip().lower()
    normalized_vertical_anchor = str(vertical_anchor or "center").strip().lower()
    crop_left = (
        0
        if normalized_horizontal_anchor == "left"
        else extra_width
        if normalized_horizontal_anchor == "right"
        else extra_width // 2
    )
    crop_top = (
        0
        if normalized_vertical_anchor == "top"
        else extra_height
        if normalized_vertical_anchor == "bottom"
        else extra_height // 2
    )
    return resized.crop(
        (
            crop_left,
            crop_top,
            crop_left + safe_target_width,
            crop_top + safe_target_height,
        )
    )


def fit_image_to_canvas_with_continuous_background(
    image,
    target_width,
    target_height,
    *,
    Image,
    ImageEnhance,
    ImageFilter,
    ImageOps,
    cover_image_to_canvas_without_distortion,
) -> Image.Image:
    """Preserve the complete image and fill ratio gaps with a soft edge-derived background."""
    safe_target_width = max(int(target_width), 1)
    safe_target_height = max(int(target_height), 1)
    source = ImageOps.exif_transpose(image).convert("RGB")
    if source.width <= 0 or source.height <= 0:
        raise ValueError("Source image dimensions are invalid.")

    scale = min(
        safe_target_width / float(source.width),
        safe_target_height / float(source.height),
    )
    resized_width = max(1, min(safe_target_width, int(round(source.width * scale))))
    resized_height = max(1, min(safe_target_height, int(round(source.height * scale))))
    foreground = source.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    if foreground.size == (safe_target_width, safe_target_height):
        return foreground

    background = cover_image_to_canvas_without_distortion(
        source,
        safe_target_width,
        safe_target_height,
    )
    blur_radius = max(4.0, min(safe_target_width, safe_target_height) * 0.025)
    background = background.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    background = ImageEnhance.Contrast(background).enhance(0.72)
    background = ImageEnhance.Brightness(background).enhance(0.94)
    offset = (
        (safe_target_width - resized_width) // 2,
        (safe_target_height - resized_height) // 2,
    )
    background.paste(foreground, offset)
    return background


def resize_image_to_target_width(
    image_url,
    target_width,
    *,
    Image,
    ImageOps,
    image_bytes_to_data_url,
    io,
    load_image_bytes_from_url,
) -> tuple[str, tuple[int, int]]:
    """Scale a complete image to one fixed width and keep its natural proportional height."""
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            source = ImageOps.exif_transpose(image).convert("RGB")
            safe_target_width = max(int(target_width), 1)
            if source.width <= 0 or source.height <= 0:
                raise ValueError("Source image dimensions are invalid.")
            target_height = max(
                1,
                int(round(source.height * safe_target_width / float(source.width))),
            )
            resized = source.resize(
                (safe_target_width, target_height),
                Image.Resampling.LANCZOS,
            )
            output = io.BytesIO()
            resized.save(output, format="PNG")
        return (
            image_bytes_to_data_url(output.getvalue(), "image/png"),
            (safe_target_width, target_height),
        )
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc).startswith("图片下载失败："):
            raise
        raise RuntimeError(
            f"本地处理失败：完整 A+ 已返回，但在按宽度等比缩放时出错。{exc}"
        ) from exc


def cover_image_to_exact_size(
    image_url,
    target_width,
    target_height,
    horizontal_anchor,
    vertical_anchor,
    *,
    Image,
    fit_image_to_canvas_with_continuous_background,
    image_bytes_to_data_url,
    io,
    load_image_bytes_from_url,
) -> str:
    """Fit a complete A+ result on the exact canvas without cropping any source pixel."""
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            safe_target_width = max(int(target_width), 1)
            safe_target_height = max(int(target_height), 1)
            fitted = fit_image_to_canvas_with_continuous_background(
                image,
                safe_target_width,
                safe_target_height,
            )
            output = io.BytesIO()
            fitted.save(output, format="PNG")
        return image_bytes_to_data_url(output.getvalue(), "image/png")
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc).startswith("图片下载失败："):
            raise
        raise RuntimeError(f"本地处理失败：完整 A+ 已返回，但在保留四边画面的规格适配时出错。{exc}") from exc
