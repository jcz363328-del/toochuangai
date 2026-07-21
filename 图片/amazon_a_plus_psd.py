from __future__ import annotations

import io
import math
import struct
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageOps


PSD_MAX_DIMENSION = 30_000
MAX_LAYER_COUNT = 128
AMAZON_A_PLUS_ASPECT_RATIOS = {
    "1:1": 1.0,
    "1:4": 1 / 4,
    "1:8": 1 / 8,
    "2:3": 2 / 3,
    "3:2": 3 / 2,
    "3:4": 3 / 4,
    "4:3": 4 / 3,
    "4:1": 4.0,
    "4:5": 4 / 5,
    "5:4": 5 / 4,
    "8:1": 8.0,
    "9:16": 9 / 16,
    "16:9": 16 / 9,
    "21:9": 21 / 9,
}


@dataclass(frozen=True)
class LayerAsset:
    name: str
    image: Image.Image
    left: int
    top: int

    @property
    def right(self) -> int:
        return self.left + self.image.width

    @property
    def bottom(self) -> int:
        return self.top + self.image.height


def select_closest_aspect_ratio(canvas_size: tuple[int, int]) -> str:
    width, height = int(canvas_size[0]), int(canvas_size[1])
    if width <= 0 or height <= 0:
        raise ValueError("Canvas dimensions must be positive.")
    target_ratio = width / height
    return min(
        AMAZON_A_PLUS_ASPECT_RATIOS,
        key=lambda label: abs(math.log(target_ratio / AMAZON_A_PLUS_ASPECT_RATIOS[label])),
    )


def fit_background_to_canvas_without_distortion(
    image: Image.Image,
    canvas_size: tuple[int, int],
) -> Image.Image:
    """Fit a background to the PSD canvas without stretching its geometry."""
    target_width, target_height = int(canvas_size[0]), int(canvas_size[1])
    if target_width <= 0 or target_height <= 0:
        raise ValueError("Canvas dimensions must be positive.")
    source = ImageOps.exif_transpose(image).convert("RGBA")
    scale = min(target_width / source.width, target_height / source.height)
    resized_size = (
        max(1, min(target_width, int(round(source.width * scale)))),
        max(1, min(target_height, int(round(source.height * scale)))),
    )
    resized = source.resize(resized_size, Image.Resampling.LANCZOS)
    if resized.size == (target_width, target_height):
        return resized

    average_color = source.convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    canvas = Image.new("RGBA", (target_width, target_height), (*average_color, 255))
    offset = (
        (target_width - resized.width) // 2,
        (target_height - resized.height) // 2,
    )
    canvas.alpha_composite(resized, dest=offset)
    return canvas


def fit_green_screen_to_canvas(image: Image.Image, canvas_size: tuple[int, int]) -> Image.Image:
    target_width, target_height = int(canvas_size[0]), int(canvas_size[1])
    if target_width <= 0 or target_height <= 0:
        raise ValueError("Canvas dimensions must be positive.")
    source = ImageOps.exif_transpose(image).convert("RGB")
    if source.width <= 0 or source.height <= 0:
        raise ValueError("Source image dimensions are invalid.")

    scale = min(target_width / source.width, target_height / source.height)
    resized_width = max(1, min(target_width, int(round(source.width * scale))))
    resized_height = max(1, min(target_height, int(round(source.height * scale))))
    resized = source.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    if scale < 0.98:
        resized = resized.filter(ImageFilter.UnsharpMask(radius=0.7, percent=90, threshold=3))
    elif scale > 1.02:
        resized = resized.filter(ImageFilter.UnsharpMask(radius=0.9, percent=110, threshold=3))

    canvas = Image.new("RGB", (target_width, target_height), (0, 255, 0))
    offset = (
        (target_width - resized_width) // 2,
        (target_height - resized_height) // 2,
    )
    canvas.paste(resized, offset)
    return canvas


def build_commercial_a_plus_background(image: Image.Image) -> Image.Image:
    """Create a restrained brand-tinted background for editable A+ PSD output."""
    source = ImageOps.exif_transpose(image).convert("RGB")
    width, height = source.size
    if width <= 0 or height <= 0:
        raise ValueError("Source image dimensions are invalid.")

    sample = source.copy()
    sample.thumbnail((96, 96), Image.Resampling.BILINEAR)
    foreground_colors: list[tuple[int, int, int]] = []
    sample_pixels = (
        sample.get_flattened_data()
        if hasattr(sample, "get_flattened_data")
        else sample.getdata()
    )
    for red, green, blue in sample_pixels:
        is_green_screen = green >= 120 and green - max(red, blue) >= 36
        if not is_green_screen:
            foreground_colors.append((red, green, blue))
    if foreground_colors:
        count = len(foreground_colors)
        accent = tuple(sum(color[channel] for color in foreground_colors) // count for channel in range(3))
    else:
        accent = (196, 172, 184)

    def blend_with_white(color: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
        return tuple(
            max(0, min(255, int(round(255 * (1.0 - amount) + channel * amount))))
            for channel in color
        )

    top_color = blend_with_white(accent, 0.07)
    bottom_color = blend_with_white(accent, 0.16)
    gradient_strip = Image.new("RGB", (1, max(height, 1)), top_color)
    strip_pixels = gradient_strip.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        softened_ratio = ratio * ratio * (3.0 - 2.0 * ratio)
        strip_pixels[0, y] = tuple(
            int(round(top_color[channel] * (1.0 - softened_ratio) + bottom_color[channel] * softened_ratio))
            for channel in range(3)
        )
    background = gradient_strip.resize((width, height), Image.Resampling.BILINEAR).convert("RGBA")

    glow_scale = min(1.0, 900.0 / max(width, height))
    glow_size = (max(1, int(round(width * glow_scale))), max(1, int(round(height * glow_scale))))
    glow = Image.new("RGBA", glow_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    glow_accent = (*blend_with_white(accent, 0.56), 36)
    secondary_accent = (*blend_with_white((accent[2], accent[0], accent[1]), 0.34), 24)
    glow_width, glow_height = glow.size
    draw.ellipse(
        (-glow_width * 0.25, -glow_height * 0.04, glow_width * 0.78, glow_height * 0.42),
        fill=glow_accent,
    )
    draw.ellipse(
        (glow_width * 0.44, glow_height * 0.56, glow_width * 1.18, glow_height * 1.04),
        fill=secondary_accent,
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=max(18, int(min(glow.size) * 0.07))))
    if glow.size != background.size:
        glow = glow.resize(background.size, Image.Resampling.BILINEAR)
    background.alpha_composite(glow)
    return background


def _u16(value: int) -> bytes:
    return struct.pack(">H", int(value))


def _i16(value: int) -> bytes:
    return struct.pack(">h", int(value))


def _u32(value: int) -> bytes:
    return struct.pack(">I", int(value))


def _i32(value: int) -> bytes:
    return struct.pack(">i", int(value))


def _pascal_string(value: str, padding: int = 4) -> bytes:
    encoded = str(value or "Layer").encode("mac_roman", errors="replace")[:255]
    payload = bytes([len(encoded)]) + encoded
    payload += b"\x00" * ((-len(payload)) % max(int(padding), 1))
    return payload


def _channel_payload(image: Image.Image, channel_name: str) -> bytes:
    channel = image.getchannel(channel_name)
    return _u16(0) + channel.tobytes()


def build_layered_psd(
    canvas_size: tuple[int, int],
    layers: list[LayerAsset],
    composite: Image.Image | None = None,
) -> bytes:
    width, height = (int(canvas_size[0]), int(canvas_size[1]))
    if width <= 0 or height <= 0 or width > PSD_MAX_DIMENSION or height > PSD_MAX_DIMENSION:
        raise ValueError("PSD canvas dimensions are invalid.")
    if not layers:
        raise ValueError("At least one PSD layer is required.")
    if len(layers) > MAX_LAYER_COUNT:
        raise ValueError(f"PSD layer count exceeds {MAX_LAYER_COUNT}.")

    normalized_layers: list[LayerAsset] = []
    for index, layer in enumerate(layers, start=1):
        layer_image = ImageOps.exif_transpose(layer.image).convert("RGBA")
        if layer_image.width <= 0 or layer_image.height <= 0:
            continue
        if layer.left < 0 or layer.top < 0 or layer.right > width or layer.bottom > height:
            raise ValueError(f"Layer {index} is outside the PSD canvas.")
        normalized_layers.append(
            LayerAsset(
                name=str(layer.name or f"A+ Element {index:02d}"),
                image=layer_image,
                left=int(layer.left),
                top=int(layer.top),
            )
        )
    if not normalized_layers:
        raise ValueError("No visible PSD layers were provided.")

    layer_records: list[bytes] = []
    layer_channel_data: list[bytes] = []
    channel_specs = ((0, "R"), (1, "G"), (2, "B"), (-1, "A"))
    for layer in normalized_layers:
        channel_payloads = [
            (channel_id, _channel_payload(layer.image, channel_name))
            for channel_id, channel_name in channel_specs
        ]
        record = bytearray()
        record.extend(_i32(layer.top))
        record.extend(_i32(layer.left))
        record.extend(_i32(layer.bottom))
        record.extend(_i32(layer.right))
        record.extend(_u16(len(channel_payloads)))
        for channel_id, payload in channel_payloads:
            record.extend(_i16(channel_id))
            record.extend(_u32(len(payload)))
        record.extend(b"8BIM")
        record.extend(b"norm")
        record.extend(bytes((255, 0, 0, 0)))
        extra_data = _u32(0) + _u32(0) + _pascal_string(layer.name)
        record.extend(_u32(len(extra_data)))
        record.extend(extra_data)
        layer_records.append(bytes(record))
        layer_channel_data.extend(payload for _channel_id, payload in channel_payloads)

    layer_info = _i16(len(normalized_layers)) + b"".join(layer_records) + b"".join(layer_channel_data)
    if len(layer_info) % 2:
        layer_info += b"\x00"
    layer_and_mask_data = _u32(len(layer_info)) + layer_info + _u32(0)

    if composite is None:
        composite_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for layer in reversed(normalized_layers):
            composite_image.alpha_composite(layer.image, dest=(layer.left, layer.top))
    else:
        composite_image = ImageOps.exif_transpose(composite).convert("RGBA")
        if composite_image.size != (width, height):
            raise ValueError("PSD composite size does not match the canvas.")

    header = (
        b"8BPS"
        + _u16(1)
        + b"\x00" * 6
        + _u16(4)
        + _u32(height)
        + _u32(width)
        + _u16(8)
        + _u16(3)
    )
    merged_image_data = _u16(0) + b"".join(
        composite_image.getchannel(channel_name).tobytes()
        for channel_name in ("R", "G", "B", "A")
    )
    return (
        header
        + _u32(0)
        + _u32(0)
        + _u32(len(layer_and_mask_data))
        + layer_and_mask_data
        + merged_image_data
    )


def clean_green_edge_spill(image: Image.Image) -> Image.Image:
    """Recover foreground color and alpha from opaque green-screen edge pixels."""
    source = ImageOps.exif_transpose(image).convert("RGBA")
    try:
        import cv2
        import numpy as np

        array = np.array(source)
        alpha = array[:, :, 3].astype(np.uint8)
        visible = alpha >= 8
        if not visible.any() or not (alpha < 8).any():
            return source

        rgb = array[:, :, :3].astype(np.float32)
        red = rgb[:, :, 0]
        green = rgb[:, :, 1]
        blue = rgb[:, :, 2]
        distance_inside = cv2.distanceTransform(visible.astype(np.uint8), cv2.DIST_L2, 5)
        edge_width = max(2.5, min(6.0, min(source.size) * 0.008))

        # A green-screen blend can be approximated as foreground color plus a
        # [0, 255, 0] background contribution. Estimate the foreground green
        # channel from red/blue, then solve that contribution back out.
        expected_foreground_green = red * 0.58 + blue * 0.42
        green_spill = np.clip(green - expected_foreground_green, 0.0, 255.0)
        green_dominance = green - np.maximum(red, blue)
        contaminated = (
            visible
            & (distance_inside <= edge_width)
            & (green_spill >= 10.0)
            & (green_dominance >= 3.0)
        )
        if not contaminated.any():
            return source

        recovered_alpha = np.clip(255.0 - green_spill, 0.0, 255.0)
        new_alpha = alpha.astype(np.float32)
        new_alpha[contaminated] = np.minimum(new_alpha[contaminated], recovered_alpha[contaminated])
        new_alpha[new_alpha < 10.0] = 0.0

        color_alpha_fraction = np.maximum(recovered_alpha / 255.0, 0.04)
        background_fraction = 1.0 - color_alpha_fraction
        recovered_red = np.clip(red / color_alpha_fraction, 0.0, 255.0)
        recovered_blue = np.clip(blue / color_alpha_fraction, 0.0, 255.0)
        recovered_green = np.clip(
            (green - background_fraction * 255.0) / color_alpha_fraction,
            0.0,
            255.0,
        )
        array[:, :, 0] = np.where(contaminated, recovered_red, red).astype(np.uint8)
        array[:, :, 1] = np.where(contaminated, recovered_green, green).astype(np.uint8)
        array[:, :, 2] = np.where(contaminated, recovered_blue, blue).astype(np.uint8)
        array[:, :, 3] = new_alpha.astype(np.uint8)

        transparent = array[:, :, 3] == 0
        array[:, :, :3] = np.where(transparent[:, :, None], 0, array[:, :, :3]).astype(np.uint8)
        return Image.fromarray(array, mode="RGBA")
    except Exception:
        return source


def remove_green_screen(image: Image.Image) -> Image.Image:
    source = ImageOps.exif_transpose(image).convert("RGBA")
    try:
        import cv2
        import numpy as np

        array = np.array(source)
        height, width = array.shape[:2]
        rgb = array[:, :, :3].astype(np.int32)
        original_alpha = array[:, :, 3].astype(np.uint8)
        red = rgb[:, :, 0]
        green = rgb[:, :, 1]
        blue = rgb[:, :, 2]

        ring = max(2, min(24, int(round(min(width, height) * 0.02))))
        edge_ring = np.zeros((height, width), dtype=bool)
        edge_ring[:ring, :] = True
        edge_ring[-ring:, :] = True
        edge_ring[:, :ring] = True
        edge_ring[:, -ring:] = True
        border_pixels = rgb[edge_ring & (original_alpha > 0)]
        border_key = (
            np.median(border_pixels, axis=0).astype(np.int32)
            if border_pixels.size
            else np.array([0, 255, 0], dtype=np.int32)
        )
        pure_green = np.array([0, 255, 0], dtype=np.int32)
        border_distance = np.sqrt(((rgb - border_key) ** 2).sum(axis=2))
        pure_green_distance = np.sqrt(((rgb - pure_green) ** 2).sum(axis=2))
        green_dominance = green - np.maximum(red, blue)

        green_candidate = (
            (green > 75)
            & (green_dominance > 18)
            & ((border_distance < 170) | (pure_green_distance < 190))
            & (original_alpha > 0)
        )
        component_count, labels = cv2.connectedComponents(green_candidate.astype(np.uint8), 8)
        border_mask = np.zeros((height, width), dtype=bool)
        border_mask[0, :] = True
        border_mask[-1, :] = True
        border_mask[:, 0] = True
        border_mask[:, -1] = True
        edge_labels = np.unique(labels[border_mask & green_candidate]) if component_count > 1 else np.array([])
        edge_labels = edge_labels[edge_labels > 0]
        background = np.isin(labels, edge_labels) if edge_labels.size else green_candidate
        exact_green = (
            (pure_green_distance < 52)
            & (green > 150)
            & (green_dominance > 65)
            & (original_alpha > 0)
        )
        exact_count, exact_labels, exact_stats, _exact_centroids = cv2.connectedComponentsWithStats(
            exact_green.astype(np.uint8),
            8,
        )
        enclosed_hole_limit = max(64, int(round(width * height * 0.0015)))
        for exact_index in range(1, exact_count):
            exact_area = int(exact_stats[exact_index, cv2.CC_STAT_AREA])
            component = exact_labels == exact_index
            if (component & border_mask).any() or exact_area <= enclosed_hole_limit:
                background |= component

        alpha = original_alpha.copy()
        alpha[background] = 0
        soft_zone = cv2.dilate(background.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1).astype(bool)
        soft_zone &= ~background
        soft_zone &= (green > 70) & (green_dominance > 8)
        if soft_zone.any():
            key_distance = np.minimum(border_distance, pure_green_distance)
            soft_alpha = np.clip((key_distance - 28.0) * (255.0 / 128.0), 0, 255).astype(np.uint8)
            alpha[soft_zone] = np.minimum(alpha[soft_zone], soft_alpha[soft_zone])

        spill = (alpha > 0) & (alpha < 255) & (green_dominance > 8)
        if spill.any():
            neutral_green = np.maximum(red, blue) + 8
            array[:, :, 1] = np.where(spill, np.minimum(green, neutral_green), array[:, :, 1]).astype(np.uint8)
        array[:, :, 3] = alpha
        transparent = alpha == 0
        array[:, :, :3] = np.where(transparent[:, :, None], 0, array[:, :, :3]).astype(np.uint8)
        return clean_green_edge_spill(Image.fromarray(array, mode="RGBA"))
    except Exception:
        return source


def _extract_layers_with_gap(image: Image.Image, grouping_gap: int) -> list[LayerAsset]:
    import cv2
    import numpy as np

    source = image.convert("RGBA")
    array = np.array(source)
    alpha = array[:, :, 3]
    foreground = alpha >= 24
    if not foreground.any():
        return []

    gap = max(int(grouping_gap), 1)
    kernel_size = gap * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    grouped_mask = cv2.dilate(foreground.astype(np.uint8), kernel, iterations=1)
    component_count, labels, _stats, _centroids = cv2.connectedComponentsWithStats(grouped_mask, 8)
    canvas_area = source.width * source.height
    min_visible_area = max(10, int(round(canvas_area * 0.00001)))
    layer_candidates: list[tuple[int, int, Image.Image]] = []

    for label_index in range(1, component_count):
        selected = foreground & (labels == label_index)
        visible_area = int(selected.sum())
        if visible_area < min_visible_area:
            continue
        ys, xs = np.where(selected)
        if xs.size == 0 or ys.size == 0:
            continue
        padding = 2
        left = max(int(xs.min()) - padding, 0)
        top = max(int(ys.min()) - padding, 0)
        right = min(int(xs.max()) + padding + 1, source.width)
        bottom = min(int(ys.max()) + padding + 1, source.height)
        crop_array = array[top:bottom, left:right].copy()
        selected_crop = selected[top:bottom, left:right]
        crop_array[:, :, 3] = np.where(selected_crop, crop_array[:, :, 3], 0).astype(np.uint8)
        crop_array[:, :, :3] = np.where(
            (crop_array[:, :, 3] > 0)[:, :, None],
            crop_array[:, :, :3],
            0,
        ).astype(np.uint8)
        layer_candidates.append((top, left, Image.fromarray(crop_array, mode="RGBA")))

    layer_candidates.sort(key=lambda item: (item[0], item[1]))
    return [
        LayerAsset(name=f"A+ Element {index:02d}", image=layer_image, left=left, top=top)
        for index, (top, left, layer_image) in enumerate(layer_candidates, start=1)
    ]


def extract_element_layers(image: Image.Image) -> list[LayerAsset]:
    source = ImageOps.exif_transpose(image).convert("RGBA")
    base_gap = max(4, min(18, int(round(min(source.size) * 0.012))))
    layers: list[LayerAsset] = []
    for multiplier in (1, 2, 3):
        layers = _extract_layers_with_gap(source, base_gap * multiplier)
        if len(layers) <= MAX_LAYER_COUNT:
            break
    if not layers:
        raise RuntimeError("No visible elements were found after green-screen removal.")
    if len(layers) > MAX_LAYER_COUNT:
        raise RuntimeError(f"Too many isolated elements were found (maximum {MAX_LAYER_COUNT}).")
    return layers


def build_layered_a_plus(
    image: Image.Image,
    background: Image.Image | None = None,
) -> dict[str, Any]:
    green_screen = ImageOps.exif_transpose(image).convert("RGBA")
    transparent = remove_green_screen(green_screen)
    alpha = transparent.getchannel("A")
    histogram = alpha.histogram()
    pixel_count = max(transparent.width * transparent.height, 1)
    transparent_ratio = sum(histogram[:8]) / pixel_count
    visible_ratio = sum(histogram[24:]) / pixel_count
    if transparent_ratio < 0.05:
        raise RuntimeError("The generated image does not contain a recognizable green-screen background.")
    if visible_ratio < 0.0001:
        raise RuntimeError("The generated green-screen image does not contain visible elements.")
    element_layers = extract_element_layers(transparent)
    background_layer: LayerAsset | None = None
    if background is not None:
        normalized_background = ImageOps.exif_transpose(background).convert("RGBA")
        if normalized_background.size != transparent.size:
            normalized_background = fit_background_to_canvas_without_distortion(
                normalized_background,
                transparent.size,
            )
        background_layer = LayerAsset(
            name="A+ Background",
            image=normalized_background,
            left=0,
            top=0,
        )
        if len(element_layers) + 1 > MAX_LAYER_COUNT:
            raise RuntimeError(f"Too many isolated elements were found (maximum {MAX_LAYER_COUNT - 1} with background).")
    layers = [*element_layers, *([background_layer] if background_layer is not None else [])]
    composite = (
        background_layer.image.copy()
        if background_layer is not None
        else Image.new("RGBA", transparent.size, (0, 0, 0, 0))
    )
    for layer in reversed(element_layers):
        composite.alpha_composite(layer.image, dest=(layer.left, layer.top))
    psd_bytes = build_layered_psd(transparent.size, layers, composite=composite)
    manifest = [
        {
            "name": layer.name,
            "left": layer.left,
            "top": layer.top,
            "width": layer.image.width,
            "height": layer.image.height,
        }
        for layer in layers
    ]
    preview_buffer = io.BytesIO()
    composite.save(preview_buffer, format="PNG")
    return {
        "composite": composite,
        "composite_png": preview_buffer.getvalue(),
        "layers": layers,
        "layer_manifest": manifest,
        "layer_count": len(layers),
        "psd_bytes": psd_bytes,
    }
