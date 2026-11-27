"""Background segmentation, green-screen removal and lash tray postprocessing."""

from __future__ import annotations

from PIL import Image
from typing import Any


def parse_hex_rgb(
    hex_color,
    *,
    re,
) -> tuple[int, int, int]:
    normalized = str(hex_color or "").strip().lstrip("#")
    if len(normalized) == 3:
        normalized = "".join(part * 2 for part in normalized)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", normalized):
        return (255, 255, 255)
    return (
        int(normalized[0:2], 16),
        int(normalized[2:4], 16),
        int(normalized[4:6], 16),
    )


def estimate_cutout_background_color(
    image,
    sample_mode,
    *,
    ImageStat,
) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    if width <= 0 or height <= 0:
        return (255, 255, 255)
    sample_mode = str(sample_mode or "").strip()
    if sample_mode == "自动边缘取样":
        band = max(2, min(width, height, 80) // 10)
        band = min(band, width, height)
        boxes = [
            (0, 0, width, band),
            (0, height - band, width, height),
            (0, 0, band, height),
            (width - band, 0, width, height),
        ]
    else:
        corner = max(2, min(width, height, 96) // 4)
        corner = min(corner, width, height)
        boxes = [
            (0, 0, corner, corner),
            (width - corner, 0, width, corner),
            (0, height - corner, corner, height),
            (width - corner, height - corner, width, height),
        ]

    totals = [0.0, 0.0, 0.0]
    total_weight = 0
    for box in boxes:
        left, top, right, bottom = box
        crop_width = max(right - left, 1)
        crop_height = max(bottom - top, 1)
        weight = crop_width * crop_height
        stat = ImageStat.Stat(rgb.crop(box))
        for channel_index, mean_value in enumerate(stat.mean[:3]):
            totals[channel_index] += float(mean_value) * weight
        total_weight += weight
    if total_weight <= 0:
        return (255, 255, 255)
    return tuple(max(0, min(255, int(round(value / total_weight)))) for value in totals)


def extract_edge_connected_mask(
    candidate_mask,
    *,
    Image,
    ImageDraw,
) -> Image.Image:
    try:
        import numpy as np
        from scipy import ndimage

        mask = np.asarray(candidate_mask.convert("L")) >= 128
        if mask.size == 0:
            return candidate_mask.convert("L")
        seeds = np.zeros_like(mask, dtype=bool)
        seeds[0, :] = mask[0, :]
        seeds[-1, :] = mask[-1, :]
        seeds[:, 0] = mask[:, 0]
        seeds[:, -1] = mask[:, -1]
        connected = ndimage.binary_propagation(seeds, mask=mask)
        connected_image = (connected.astype(np.uint8) * 255)
        return Image.fromarray(connected_image, mode="L")
    except Exception:
        pass

    working = candidate_mask.convert("L").point(lambda value: 255 if value >= 128 else 0)
    width, height = working.size
    if width <= 0 or height <= 0:
        return working
    pixels = working.load()
    for x in range(width):
        if pixels[x, 0] == 255:
            ImageDraw.floodfill(working, (x, 0), 128, thresh=0)
        if pixels[x, height - 1] == 255:
            ImageDraw.floodfill(working, (x, height - 1), 128, thresh=0)
    for y in range(height):
        if pixels[0, y] == 255:
            ImageDraw.floodfill(working, (0, y), 128, thresh=0)
        if pixels[width - 1, y] == 255:
            ImageDraw.floodfill(working, (width - 1, y), 128, thresh=0)
    return working.point(lambda value: 255 if value == 128 else 0)


def build_subject_protection_mask(
    distance,
    threshold,
    *,
    Image,
    ImageDraw,
) -> Image.Image:
    try:
        import numpy as np

        arr = np.asarray(distance.convert("L")) > max(0, min(255, int(threshold)))
        if arr.size == 0:
            return Image.new("L", distance.size, 0)
        height, width = arr.shape
        row_threshold = max(12, int(round(width * 0.008)))
        col_threshold = max(12, int(round(height * 0.008)))
        rows = np.where(arr.sum(axis=1) >= row_threshold)[0]
        cols = np.where(arr.sum(axis=0) >= col_threshold)[0]
        if rows.size == 0 or cols.size == 0:
            return Image.new("L", distance.size, 0)

        left = int(cols[0])
        right = int(cols[-1])
        top = int(rows[0])
        bottom = int(rows[-1])
        pad_x = max(8, int(round(width * 0.018)))
        pad_y = max(8, int(round(height * 0.018)))
        left = max(0, left - pad_x)
        right = min(width - 1, right + pad_x)
        top = max(0, top - pad_y)
        bottom = min(height - 1, bottom + pad_y)

        area_ratio = ((right - left + 1) * (bottom - top + 1)) / float(max(width * height, 1))
        if area_ratio <= 0 or area_ratio >= 0.92:
            return Image.new("L", distance.size, 0)

        mask = Image.new("L", distance.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((left, top, right, bottom), fill=255)
        return mask
    except Exception:
        return Image.new("L", distance.size, 0)


def build_lash_rectangle_protection_mask(
    image,
    *,
    Image,
    ImageDraw,
) -> Image.Image:
    try:
        import numpy as np

        rgb = np.asarray(image.convert("RGB"))
        if rgb.size == 0:
            return Image.new("L", image.size, 0)
        height, width = rgb.shape[:2]
        luminance = (
            0.299 * rgb[:, :, 0].astype("float32")
            + 0.587 * rgb[:, :, 1].astype("float32")
            + 0.114 * rgb[:, :, 2].astype("float32")
        )
        dark_mask = luminance < 95
        if not bool(dark_mask.any()):
            return Image.new("L", image.size, 0)

        min_col_count = max(10, int(round(height * 0.006)))
        min_row_count = max(10, int(round(width * 0.006)))
        cols = np.where(dark_mask.sum(axis=0) >= min_col_count)[0]
        rows = np.where(dark_mask.sum(axis=1) >= min_row_count)[0]
        if cols.size == 0 or rows.size == 0:
            return Image.new("L", image.size, 0)

        lash_left = int(cols[0])
        lash_right = int(cols[-1])
        lash_top = int(rows[0])
        lash_bottom = int(rows[-1])

        dense_mask = dark_mask.copy()
        dense_mask[:, :lash_left] = False
        dense_mask[:, lash_right + 1 :] = False
        dense_mask[:lash_top, :] = False
        dense_mask[lash_bottom + 1 :, :] = False
        ys, xs = np.where(dense_mask)
        if xs.size < 200:
            return Image.new("L", image.size, 0)

        points = np.column_stack((xs.astype("float32"), ys.astype("float32")))
        center = points.mean(axis=0)
        centered = points - center
        covariance = np.cov(centered, rowvar=False)
        values, vectors = np.linalg.eigh(covariance)
        ordered = vectors[:, np.argsort(values)[::-1]]
        axis_a = ordered[:, 0]
        axis_b = ordered[:, 1]
        if abs(axis_a[0]) >= abs(axis_b[0]):
            x_axis = axis_a
            y_axis = axis_b
        else:
            x_axis = axis_b
            y_axis = axis_a
        if x_axis[0] < 0:
            x_axis = -x_axis
        if y_axis[1] < 0:
            y_axis = -y_axis

        projected_x = points @ x_axis
        projected_y = points @ y_axis
        left = float(projected_x.min())
        right = float(projected_x.max())
        top = float(projected_y.min())
        bottom = float(projected_y.max())
        lash_width = max(right - left, 1.0)
        lash_height = max(bottom - top, 1.0)

        left -= lash_width * 0.12
        right += lash_width * 0.04
        top -= lash_height * 0.30
        bottom += lash_height * 0.16

        corners = [
            x_axis * left + y_axis * top,
            x_axis * right + y_axis * top,
            x_axis * right + y_axis * bottom,
            x_axis * left + y_axis * bottom,
        ]
        polygon = [(float(point[0]), float(point[1])) for point in corners]
        min_x = max(0.0, min(point[0] for point in polygon))
        max_x = min(float(width - 1), max(point[0] for point in polygon))
        min_y = max(0.0, min(point[1] for point in polygon))
        max_y = min(float(height - 1), max(point[1] for point in polygon))
        area_ratio = ((max_x - min_x + 1) * (max_y - min_y + 1)) / float(max(width * height, 1))
        if area_ratio <= 0.04 or area_ratio >= 0.88:
            return Image.new("L", image.size, 0)

        mask = Image.new("L", image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.polygon(polygon, fill=255)
        return mask
    except Exception:
        return Image.new("L", image.size, 0)


def remove_background_by_color(
    image,
    background_color,
    tolerance,
    softness,
    edge_blur,
    invert_mask,
    connected_only,
    protect_subject_region,
    subject_region_mode,
    *,
    Image,
    ImageChops,
    ImageFilter,
    ImageOps,
    build_lash_rectangle_protection_mask,
    build_subject_protection_mask,
    extract_edge_connected_mask,
) -> Image.Image:
    source = ImageOps.exif_transpose(image).convert("RGBA")
    tolerance = max(0, min(255, int(tolerance)))
    softness = max(0, min(255, int(softness)))
    edge_blur = max(0.0, min(8.0, float(edge_blur)))
    background = Image.new("RGB", source.size, background_color)
    diff = ImageChops.difference(source.convert("RGB"), background)
    red, green, blue = diff.split()
    distance = ImageChops.lighter(ImageChops.lighter(red, green), blue)

    high = tolerance if softness <= 0 else max(tolerance + 1, min(255, tolerance + softness))
    if softness <= 0:
        background_strength = distance.point(lambda value: 255 if value <= tolerance else 0)
    else:

        def background_from_distance(value: int) -> int:
            if value <= tolerance:
                return 255
            if value >= high:
                return 0
            return int(round((high - value) * 255 / (high - tolerance)))

        background_strength = distance.point(background_from_distance)

    protection_mask = None
    if connected_only:
        candidate_mask = distance.point(lambda value: 255 if value <= high else 0)
        connected_mask = extract_edge_connected_mask(candidate_mask)
        background_strength = ImageChops.multiply(background_strength, connected_mask)
    if protect_subject_region:
        if str(subject_region_mode or "").strip() == "lash_rectangle":
            candidate_protection_mask = build_lash_rectangle_protection_mask(source)
        else:
            candidate_protection_mask = build_subject_protection_mask(distance, high)
        if candidate_protection_mask.getbbox() is not None:
            protection_mask = candidate_protection_mask
            background_strength = ImageChops.multiply(background_strength, ImageOps.invert(protection_mask))

    alpha = ImageOps.invert(background_strength)
    if protection_mask is not None:
        alpha = ImageChops.multiply(alpha, protection_mask)
    if invert_mask:
        alpha = ImageOps.invert(alpha)
    alpha = ImageChops.multiply(alpha, source.getchannel("A"))
    if edge_blur > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(edge_blur))

    result = source.copy()
    result.putalpha(alpha)
    return result


def image_to_png_bytes(
    image,
    *,
    io,
) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def crop_to_visible_alpha(
    image,
    padding,
    *,
    ImageOps,
) -> Image.Image:
    source = ImageOps.exif_transpose(image).convert("RGBA")
    alpha_bbox = source.getchannel("A").getbbox()
    if not alpha_bbox:
        return source
    left, top, right, bottom = alpha_bbox
    safe_padding = max(0, int(padding))
    left = max(0, left - safe_padding)
    top = max(0, top - safe_padding)
    right = min(source.width, right + safe_padding)
    bottom = min(source.height, bottom + safe_padding)
    if left <= 0 and top <= 0 and right >= source.width and bottom >= source.height:
        return source
    return source.crop((left, top, right, bottom))


def regularize_lash_tray_alpha(
    alpha_image,
    *,
    Image,
) -> tuple[Image.Image, bool]:
    """Fit a clean perspective quadrilateral to the rectangular lash tray mask."""
    alpha = alpha_image.convert("L")
    try:
        import cv2
        import numpy as np

        alpha_array = np.asarray(alpha, dtype=np.uint8)
        height, width = alpha_array.shape[:2]
        if width < 64 or height < 64:
            return alpha, False

        binary = (alpha_array >= 96).astype(np.uint8) * 255
        contours, _hierarchy = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return alpha, False
        contour = max(contours, key=cv2.contourArea)
        contour_area = float(cv2.contourArea(contour))
        canvas_area = float(max(width * height, 1))
        if contour_area / canvas_area < 0.06:
            return alpha, False

        hull = cv2.convexHull(contour)
        perimeter = float(cv2.arcLength(hull, True))
        if perimeter <= 0:
            return alpha, False

        quadrilateral = None
        for epsilon_ratio in (0.003, 0.004, 0.005, 0.006, 0.008, 0.01, 0.012, 0.015, 0.02):
            candidate = cv2.approxPolyDP(hull, epsilon_ratio * perimeter, True)
            if len(candidate) == 4 and cv2.isContourConvex(candidate):
                candidate_area = float(cv2.contourArea(candidate))
                area_ratio = candidate_area / max(contour_area, 1.0)
                if 0.96 <= area_ratio <= 1.10:
                    quadrilateral = candidate
                    break
        if quadrilateral is None:
            return alpha, False

        points = quadrilateral.reshape(4, 2).astype(np.int32)
        edge_lengths = [
            float(np.linalg.norm(points[(index + 1) % 4] - points[index]))
            for index in range(4)
        ]
        if min(edge_lengths) < min(width, height) * 0.10:
            return alpha, False

        smooth_alpha = np.zeros((height, width), dtype=np.uint8)
        cv2.fillConvexPoly(smooth_alpha, points, 255, lineType=cv2.LINE_AA)
        return Image.fromarray(smooth_alpha, mode="L"), True
    except Exception:
        return alpha, False


def regularize_lash_tray_cutout(
    image,
    *,
    Image,
    ImageOps,
    regularize_lash_tray_alpha,
) -> tuple[Image.Image, bool]:
    """Straighten the tray outline and extend nearby edge pixels into tiny mask gaps."""
    source = ImageOps.exif_transpose(image).convert("RGBA")
    smooth_alpha, regularized = regularize_lash_tray_alpha(source.getchannel("A"))
    if not regularized:
        return source, False
    try:
        import cv2
        import numpy as np

        array = np.array(source)
        original_alpha = array[:, :, 3]
        smooth_alpha_array = np.asarray(smooth_alpha, dtype=np.uint8)
        reliable_subject = original_alpha >= 96
        added_area = (smooth_alpha_array > 2) & ~reliable_subject
        added_ratio = float(added_area.mean())
        if added_ratio > 0.035 or not reliable_subject.any():
            return source, False

        if added_area.any():
            distance_source = (~reliable_subject).astype(np.uint8)
            _distance, labels = cv2.distanceTransformWithLabels(
                distance_source,
                cv2.DIST_L2,
                5,
                labelType=cv2.DIST_LABEL_PIXEL,
            )
            subject_coordinates = np.argwhere(distance_source == 0)
            added_y, added_x = np.where(added_area)
            nearest_indexes = labels[added_y, added_x].astype(np.int64) - 1
            valid = (nearest_indexes >= 0) & (nearest_indexes < len(subject_coordinates))
            if valid.any():
                nearest_y = subject_coordinates[nearest_indexes[valid], 0]
                nearest_x = subject_coordinates[nearest_indexes[valid], 1]
                array[added_y[valid], added_x[valid], :3] = array[nearest_y, nearest_x, :3]

        array[:, :, 3] = smooth_alpha_array
        return Image.fromarray(array, mode="RGBA"), True
    except Exception:
        return source, False


def finalize_lash_tray_cutout_edges(
    image,
    *,
    clean_cutout_edge_fringe,
    crop_to_visible_alpha,
    regularize_lash_tray_cutout,
) -> Image.Image:
    regularized_image, has_regularized_edge = regularize_lash_tray_cutout(image)
    return crop_to_visible_alpha(
        clean_cutout_edge_fringe(
            regularized_image,
            contract_edge=False,
            preserve_alpha_edge=has_regularized_edge,
        ),
        padding=1,
    )


def preserve_source_pixels_with_ai_alpha(
    source_image,
    ai_cutout_image,
    *,
    Image,
    ImageOps,
    finalize_lash_tray_cutout_edges,
) -> Image.Image:
    """Use AI as the cutout mask while keeping original product color and scale."""
    source = ImageOps.exif_transpose(source_image).convert("RGBA")
    ai_cutout = ImageOps.exif_transpose(ai_cutout_image).convert("RGBA")
    if source.width <= 0 or source.height <= 0 or ai_cutout.width <= 0 or ai_cutout.height <= 0:
        return finalize_lash_tray_cutout_edges(ai_cutout)

    source_ratio = source.width / float(source.height)
    cutout_ratio = ai_cutout.width / float(ai_cutout.height)
    if abs(source_ratio - cutout_ratio) / max(source_ratio, 0.01) > 0.045:
        return finalize_lash_tray_cutout_edges(ai_cutout)

    alpha = ai_cutout.getchannel("A")
    if alpha.size != source.size:
        alpha = alpha.resize(source.size, Image.Resampling.LANCZOS)
    visible_bbox = alpha.getbbox()
    if not visible_bbox:
        return finalize_lash_tray_cutout_edges(ai_cutout)
    visible_area = (visible_bbox[2] - visible_bbox[0]) * (visible_bbox[3] - visible_bbox[1])
    canvas_area = max(source.width * source.height, 1)
    if visible_area / canvas_area < 0.04:
        return finalize_lash_tray_cutout_edges(ai_cutout)

    result = source.copy()
    result.putalpha(alpha)
    return finalize_lash_tray_cutout_edges(result)


def remove_simple_green_screen_background(
    image,
    *,
    Image,
    ImageOps,
) -> Image.Image:
    try:
        import numpy as np

        source = ImageOps.exif_transpose(image).convert("RGBA")
        array = np.array(source)
        rgb = array[:, :, :3].astype(np.int32)
        red = rgb[:, :, 0]
        green = rgb[:, :, 1]
        blue = rgb[:, :, 2]
        green_mask = (green > 120) & (green - red > 45) & (green - blue > 45)
        array[:, :, 3] = np.where(green_mask, 0, array[:, :, 3]).astype(np.uint8)
        return Image.fromarray(array, mode="RGBA")
    except Exception:
        return image.convert("RGBA")


def clean_cutout_edge_fringe(
    image,
    contract_edge,
    preserve_alpha_edge,
    *,
    Image,
    ImageOps,
) -> Image.Image:
    """Create a narrow, smooth inner antialias and remove green-screen spill."""
    source = ImageOps.exif_transpose(image).convert("RGBA")
    try:
        import cv2
        import numpy as np

        array = np.array(source)
        alpha = array[:, :, 3].astype(np.uint8)
        if alpha.size == 0 or int(alpha.max()) == 0:
            return source
        if float((alpha == 0).mean()) < 0.01:
            return source

        rgb = array[:, :, :3].astype(np.int32)
        red = rgb[:, :, 0]
        green = rgb[:, :, 1]
        blue = rgb[:, :, 2]

        if preserve_alpha_edge:
            alpha = np.where(alpha <= 2, 0, alpha).astype(np.uint8)
        else:
            # Low-alpha pixels are the wide halo seen after zooming. Build a fresh
            # contour from the reliable part of the mask, then antialias inward only.
            reliable_mask = (alpha >= 96).astype(np.uint8)
            if int(reliable_mask.sum()) <= 0:
                return source

            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            contracted_mask = (
                cv2.erode(reliable_mask, kernel, iterations=1)
                if contract_edge
                else reliable_mask
            )
            reliable_area = int(reliable_mask.sum())
            contracted_area = int(contracted_mask.sum())
            if contracted_area <= 0 or contracted_area < reliable_area * 0.86:
                contracted_mask = reliable_mask

            # The distance ramp is fully inside the contour: no outward blur or halo.
            distance = cv2.distanceTransform(contracted_mask, cv2.DIST_L2, 5)
            alpha = np.clip((distance - 0.22) * (255.0 / 0.92), 0, 255).astype(np.uint8)
            alpha[contracted_mask == 0] = 0

        partial_edge = (alpha > 0) & (alpha < 255)
        green_dominant = (green > 82) & (green > red + 12) & (green > blue + 12)
        fringe_mask = partial_edge & green_dominant
        if fringe_mask.any():
            neutral_green = np.maximum(red, blue)
            array[:, :, 1] = np.where(
                fringe_mask,
                np.minimum(green, neutral_green),
                array[:, :, 1],
            ).astype(np.uint8)

        transparent_mask = alpha <= 2
        if transparent_mask.any():
            array[:, :, :3] = np.where(transparent_mask[:, :, None], 0, array[:, :, :3]).astype(np.uint8)
        array[:, :, 3] = alpha
        return Image.fromarray(array, mode="RGBA")
    except Exception:
        return source


def remove_ai_green_screen_background(
    image,
    *,
    Image,
    ImageFilter,
    ImageOps,
    build_lash_rectangle_protection_mask,
    clean_cutout_edge_fringe,
    remove_background_by_color,
    remove_simple_green_screen_background,
) -> Image.Image:
    """Remove the AI-generated outer background while preserving inner product details."""
    source = ImageOps.exif_transpose(image).convert("RGBA")
    try:
        import cv2
        import numpy as np

        array = np.array(source)
        height, width = array.shape[:2]
        if width <= 0 or height <= 0:
            return source

        rgb = array[:, :, :3].astype(np.int32)
        alpha = array[:, :, 3]
        red = rgb[:, :, 0]
        green = rgb[:, :, 1]
        blue = rgb[:, :, 2]

        if float((alpha == 0).mean()) > 0.08 and float((alpha[0, :] == 0).mean()) > 0.45:
            return clean_cutout_edge_fringe(source)

        border_mask = np.zeros((height, width), dtype=bool)
        border_mask[0, :] = True
        border_mask[-1, :] = True
        border_mask[:, 0] = True
        border_mask[:, -1] = True
        ring = max(2, min(36, int(round(min(width, height) * 0.025))))
        edge_ring_mask = np.zeros((height, width), dtype=bool)
        edge_ring_mask[:ring, :] = True
        edge_ring_mask[-ring:, :] = True
        edge_ring_mask[:, :ring] = True
        edge_ring_mask[:, -ring:] = True

        border_pixels = rgb[edge_ring_mask & (alpha > 0)]
        if border_pixels.size:
            border_key = np.median(border_pixels, axis=0).astype(np.int32)
        else:
            border_key = np.array([0, 255, 0], dtype=np.int32)

        green_key = np.array([0, 255, 0], dtype=np.int32)
        green_distance = np.sqrt(((rgb - green_key) ** 2).sum(axis=2))
        border_distance = np.sqrt(((rgb - border_key) ** 2).sum(axis=2))
        edge_distances = border_distance[edge_ring_mask & (alpha > 0)]
        if edge_distances.size:
            adaptive_border_threshold = int(round(float(np.percentile(edge_distances, 92)) + 38))
            adaptive_border_threshold = max(52, min(145, adaptive_border_threshold))
        else:
            adaptive_border_threshold = 72
        brightness = (red + green + blue) / 3.0
        max_channel = np.maximum(np.maximum(red, green), blue)
        min_channel = np.minimum(np.minimum(red, green), blue)
        low_saturation = (max_channel - min_channel) <= 42
        edge_brightness_values = brightness[edge_ring_mask & (alpha > 0)]
        edge_is_light = bool(edge_brightness_values.size and float(np.median(edge_brightness_values)) >= 170)
        light_background_like = edge_is_light & low_saturation & (brightness >= 145) & (border_distance <= max(72, adaptive_border_threshold + 22))
        green_like = (green > 115) & (green - red > 35) & (green - blue > 35)
        candidate_mask = (
            ((green_distance <= 175) & (green > 85))
            | green_like
            | (border_distance <= adaptive_border_threshold)
            | light_background_like
        )
        candidate_mask &= alpha > 0
        if float(candidate_mask[border_mask].mean()) < 0.15:
            candidate_mask |= ((green_distance <= 215) & (green > 70) & (green > red + 18) & (green > blue + 18))
            candidate_mask |= (border_distance <= max(adaptive_border_threshold, 110))
            candidate_mask &= alpha > 0

        component_count, labels = cv2.connectedComponents(candidate_mask.astype(np.uint8), 8)
        if component_count <= 1:
            return clean_cutout_edge_fringe(remove_background_by_color(
                source,
                tuple(int(value) for value in border_key[:3]),
                tolerance=max(adaptive_border_threshold, 90),
                softness=48,
                edge_blur=0.45,
                invert_mask=False,
                connected_only=True,
                protect_subject_region=True,
                subject_region_mode="lash_rectangle",
            ))

        edge_labels = np.unique(labels[border_mask & candidate_mask])
        edge_labels = edge_labels[edge_labels > 0]
        if edge_labels.size == 0:
            return clean_cutout_edge_fringe(remove_background_by_color(
                source,
                tuple(int(value) for value in border_key[:3]),
                tolerance=max(adaptive_border_threshold, 90),
                softness=48,
                edge_blur=0.45,
                invert_mask=False,
                connected_only=True,
                protect_subject_region=True,
                subject_region_mode="lash_rectangle",
            ))

        background_mask = np.isin(labels, edge_labels)
        protection_mask_image = build_lash_rectangle_protection_mask(source)
        protection_mask = np.asarray(protection_mask_image.convert("L")) >= 128
        if protection_mask.any():
            background_mask &= ~protection_mask
        removed_ratio = float(background_mask.mean())
        if removed_ratio < 0.015:
            return clean_cutout_edge_fringe(remove_background_by_color(
                source,
                tuple(int(value) for value in border_key[:3]),
                tolerance=max(adaptive_border_threshold, 100),
                softness=56,
                edge_blur=0.45,
                invert_mask=False,
                connected_only=True,
                protect_subject_region=True,
                subject_region_mode="lash_rectangle",
            ))
        subject_alpha = np.where(background_mask, 0, 255).astype(np.uint8)
        subject_alpha_image = Image.fromarray(subject_alpha, mode="L").filter(ImageFilter.GaussianBlur(0.55))
        final_alpha = np.minimum(np.array(subject_alpha_image), alpha).astype(np.uint8)

        edge_mask = (final_alpha > 0) & (final_alpha < 252) & (green > red + 25) & (green > blue + 25)
        if edge_mask.any():
            neutral_green = np.maximum(red, blue) + 8
            array[:, :, 1] = np.where(edge_mask, np.minimum(green, neutral_green), array[:, :, 1]).astype(np.uint8)

        array[:, :, 3] = final_alpha
        return clean_cutout_edge_fringe(Image.fromarray(array, mode="RGBA"))
    except Exception:
        return clean_cutout_edge_fringe(remove_simple_green_screen_background(source))


def call_ai_lash_tray_cutout(
    uploaded_input,
    prompt,
    *,
    DEFAULT_ASPECT_RATIO,
    NANO_BANANA_MODEL,
    build_ai_lash_tray_cutout_prompt,
    call_openrouter_images_api,
    uploaded_input_to_pil_image,
) -> dict[str, Any]:
    source_size: tuple[int, int] | None = None
    try:
        source_size = uploaded_input_to_pil_image(uploaded_input).size
    except Exception:
        source_size = None
    ai_prompt = build_ai_lash_tray_cutout_prompt(prompt, source_size=source_size)
    try:
        result = call_openrouter_images_api(
            model=NANO_BANANA_MODEL,
            prompt=ai_prompt,
            aspect_ratio=DEFAULT_ASPECT_RATIO,
            uploaded_files=[uploaded_input],
            resolution="4K",
        )
        result["channel"] = "Images API 原生 4K"
        return result
    except Exception as exc:
        raise RuntimeError(
            "OmniaKey 原生 4K 调用失败。为避免画质降级，本次未使用聊天兼容通道。"
            f"原因：{exc}"
        ) from exc


def trim_transparent_image(
    image,
    padding,
    alpha_threshold,
) -> Image.Image:
    source = image.convert("RGBA")
    alpha = source.getchannel("A").point(lambda value: 255 if value > alpha_threshold else 0)
    bbox = alpha.getbbox()
    if bbox is None:
        return source
    left, top, right, bottom = bbox
    padding = max(0, int(padding))
    crop_box = (
        max(0, left - padding),
        max(0, top - padding),
        min(source.size[0], right + padding),
        min(source.size[1], bottom + padding),
    )
    return source.crop(crop_box)


def find_lash_product_region_polygon(
    image,
    *,
    Any,
    Image,
    ImageOps,
) -> list[tuple[float, float]] | None:
    try:
        import cv2
        import numpy as np

        source = ImageOps.exif_transpose(image).convert("RGB")
        width, height = source.size
        if width <= 0 or height <= 0:
            return None

        max_detection_edge = 1400
        scale = min(max_detection_edge / float(max(width, height)), 1.0)
        small_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        small = source.resize(small_size, Image.Resampling.LANCZOS) if scale < 1.0 else source
        rgb = np.asarray(small)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        dark_mask = (gray < 95).astype(np.uint8) * 255
        if int(dark_mask.sum()) <= 0:
            return None

        close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 5))
        grouped = cv2.morphologyEx(dark_mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
        grouped = cv2.dilate(grouped, cv2.getStructuringElement(cv2.MORPH_RECT, (17, 9)), iterations=2)
        component_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(grouped, 8)
        components: list[dict[str, Any]] = []
        image_area = max(small_size[0] * small_size[1], 1)
        for component_index in range(1, component_count):
            x, y, w, h, area = [int(value) for value in stats[component_index]]
            if area < max(250, int(round(image_area * 0.0012))):
                continue
            aspect = w / float(max(h, 1))
            if area < image_area * 0.006 and aspect < 1.8:
                continue
            components.append(
                {
                    "index": component_index,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "area": area,
                    "right": x + w,
                    "bottom": y + h,
                }
            )
        if not components:
            return None

        primary = max(components, key=lambda item: int(item["area"]))
        primary_left = int(primary["x"])
        primary_right = int(primary["right"])
        primary_width = max(primary_right - primary_left, 1)
        selected_indexes: set[int] = {int(primary["index"])}
        for component in components:
            overlap_left = max(primary_left, int(component["x"]))
            overlap_right = min(primary_right, int(component["right"]))
            overlap_ratio = max(overlap_right - overlap_left, 0) / float(max(min(primary_width, int(component["w"])), 1))
            close_enough = abs((int(component["x"]) + int(component["right"])) / 2 - (primary_left + primary_right) / 2) <= primary_width * 0.34
            if overlap_ratio >= 0.45 or close_enough:
                selected_indexes.add(int(component["index"]))

        selected_mask = np.isin(labels, list(selected_indexes))
        ys, xs = np.where(selected_mask)
        if xs.size < 200:
            return None

        points = np.column_stack((xs.astype("float32"), ys.astype("float32")))
        center = points.mean(axis=0)
        centered = points - center
        covariance = np.cov(centered, rowvar=False)
        values, vectors = np.linalg.eigh(covariance)
        ordered = vectors[:, np.argsort(values)[::-1]]
        axis_a = ordered[:, 0]
        axis_b = ordered[:, 1]
        if abs(axis_a[0]) >= abs(axis_b[0]):
            x_axis = axis_a
            y_axis = axis_b
        else:
            x_axis = axis_b
            y_axis = axis_a
        if x_axis[0] < 0:
            x_axis = -x_axis
        if y_axis[1] < 0:
            y_axis = -y_axis

        projected_x = points @ x_axis
        projected_y = points @ y_axis
        left = float(projected_x.min())
        right = float(projected_x.max())
        top = float(projected_y.min())
        bottom = float(projected_y.max())
        region_width = max(right - left, 1.0)
        region_height = max(bottom - top, 1.0)

        left -= region_width * 0.08
        right += region_width * 0.035
        top -= region_height * 0.28
        bottom += region_height * 0.075

        small_corners = [
            x_axis * left + y_axis * top,
            x_axis * right + y_axis * top,
            x_axis * right + y_axis * bottom,
            x_axis * left + y_axis * bottom,
        ]
        inverse_scale = 1.0 / max(scale, 1e-6)
        polygon = [
            (
                max(0.0, min(float(width - 1), float(point[0]) * inverse_scale)),
                max(0.0, min(float(height - 1), float(point[1]) * inverse_scale)),
            )
            for point in small_corners
        ]
        min_x = min(point[0] for point in polygon)
        max_x = max(point[0] for point in polygon)
        min_y = min(point[1] for point in polygon)
        max_y = max(point[1] for point in polygon)
        area_ratio = ((max_x - min_x + 1) * (max_y - min_y + 1)) / float(max(width * height, 1))
        if area_ratio <= 0.08 or area_ratio >= 0.78:
            return None
        return polygon
    except Exception:
        return None


def cut_to_lash_product_region(
    original_image,
    fallback_image,
    *,
    Image,
    ImageChops,
    ImageDraw,
    ImageFilter,
    ImageOps,
    find_lash_product_region_polygon,
    trim_transparent_image,
) -> Image.Image:
    source = ImageOps.exif_transpose(original_image).convert("RGBA")
    polygon = find_lash_product_region_polygon(source)
    if not polygon:
        return trim_transparent_image(fallback_image)
    mask = Image.new("L", source.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon(polygon, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.35))
    result = source.copy()
    result.putalpha(ImageChops.multiply(mask, source.getchannel("A")))
    return trim_transparent_image(result, padding=2, alpha_threshold=2)


def uploaded_input_to_pil_image(
    uploaded_input,
    *,
    Image,
    ImageOps,
    get_uploaded_file_bytes,
    io,
) -> Image.Image:
    image_bytes = get_uploaded_file_bytes(uploaded_input)
    if not image_bytes:
        raise RuntimeError("上传图片为空，请重新上传。")
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return ImageOps.exif_transpose(image).convert("RGBA")
    except Exception as exc:
        raise RuntimeError(f"无法读取上传图片：{exc}") from exc


def run_ai_background_cutout_job(
    job_context,
    *,
    Image,
    call_ai_lash_tray_cutout,
    get_uploaded_input_name,
    image_bytes_to_data_url,
    image_to_png_bytes,
    io,
    load_image_bytes_from_url,
    math,
    prepare_uploaded_input,
    preserve_source_pixels_with_ai_alpha,
    remove_ai_green_screen_background,
    set_task_progress,
    uploaded_input_to_data_url,
    uploaded_input_to_pil_image,
) -> dict[str, Any]:
    job_id = str(job_context.get("job_id") or "")
    uploaded_files = [prepare_uploaded_input(item) for item in list(job_context.get("uploaded_files") or [])]
    if not uploaded_files:
        raise RuntimeError("请先上传 1 张需要抠图的图片。")
    max_output_images = int(job_context.get("max_output_images") or 0)
    if max_output_images > 0:
        uploaded_files = uploaded_files[:max_output_images]

    result_images: list[str] = []
    source_images: list[str] = []
    captions: list[str] = []
    text_parts: list[str] = []
    total_files = max(len(uploaded_files), 1)
    base_prompt = str(job_context.get("prompt") or "")

    for image_index, uploaded_input in enumerate(uploaded_files, start=1):
        if job_id:
            progress = 12 + math.floor(((image_index - 1) / total_files) * 58)
            set_task_progress(job_id, progress, f"正在调用 AI 抠出睫毛托盘 {image_index}/{total_files}")
        source_name = get_uploaded_input_name(uploaded_input) or f"原图 {image_index}"
        source_images.append(uploaded_input_to_data_url(uploaded_input))
        source_image = uploaded_input_to_pil_image(uploaded_input)

        ai_result = call_ai_lash_tray_cutout(uploaded_input, base_prompt)
        ai_images = list(ai_result.get("images") or [])
        if not ai_images:
            raise RuntimeError("AI 没有返回可用的抠图预处理图片，请重试。")

        if job_id:
            progress = 68 + math.floor((image_index / total_files) * 12)
            set_task_progress(job_id, min(progress, 82), f"正在把 AI 绿幕图转成透明 PNG {image_index}/{total_files}")
        ai_image_bytes, _mime_type = load_image_bytes_from_url(str(ai_images[0]))
        try:
            with Image.open(io.BytesIO(ai_image_bytes)) as ai_image:
                ai_transparent_image = remove_ai_green_screen_background(ai_image)
                transparent_image = preserve_source_pixels_with_ai_alpha(source_image, ai_transparent_image)
        except Exception as exc:
            raise RuntimeError(f"AI 抠图结果转透明 PNG 失败：{exc}") from exc

        result_images.append(image_bytes_to_data_url(image_to_png_bytes(transparent_image), "image/png"))
        captions.append(f"{source_name} - AI 抠图后透明 PNG")
        ai_text = str(ai_result.get("text") or "").strip()
        if ai_text:
            text_parts.append(ai_text)

    if job_id:
        set_task_progress(job_id, 84, "正在生成透明 PNG 预览")
    return {
        "images": result_images,
        "source_images": source_images[: len(result_images)],
        "captions": captions,
        "text": "\n\n".join(
            part
            for part in [
                "已由 AI 先定位带睫毛的托盘区域并去除杂质背景，再由代码优先使用原图像素生成透明 PNG，保持商品颜色和主体高度一致。",
                *text_parts,
            ]
            if str(part or "").strip()
        ).strip(),
    }


def build_checkerboard_preview(
    image,
    max_edge,
    *,
    Image,
    ImageDraw,
) -> Image.Image:
    preview = image.convert("RGBA")
    max_edge = max(320, int(max_edge))
    if max(preview.size) > max_edge:
        ratio = max_edge / float(max(preview.size))
        next_size = (
            max(1, int(round(preview.size[0] * ratio))),
            max(1, int(round(preview.size[1] * ratio))),
        )
        preview = preview.resize(next_size, Image.Resampling.LANCZOS)

    block = max(10, min(preview.size) // 24)
    checker = Image.new("RGBA", preview.size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(checker)
    for y in range(0, preview.size[1], block):
        for x in range(0, preview.size[0], block):
            if ((x // block) + (y // block)) % 2:
                draw.rectangle(
                    (x, y, min(x + block, preview.size[0]), min(y + block, preview.size[1])),
                    fill=(230, 236, 245, 255),
                )
    checker.alpha_composite(preview)
    return checker
