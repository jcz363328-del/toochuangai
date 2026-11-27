"""Image analysis, palettes, report rendering and layout comparison."""

from __future__ import annotations

from PIL import Image
from PIL import ImageFont
from typing import Any


def _image_smart_text(
    value,
    max_length,
    *,
    re,
) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:max_length]


def _image_smart_string_list(
    value,
    max_items,
    max_length,
    *,
    _image_smart_text,
    re,
) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\n,，；;、]+", value)
    elif isinstance(value, (list, tuple)):
        raw_items = list(value)
    else:
        raw_items = []
    items: list[str] = []
    for raw_item in raw_items:
        item = _image_smart_text(raw_item, max_length)
        if item and item not in items:
            items.append(item)
        if len(items) >= max_items:
            break
    return items


def describe_image_smart_color(
    rgb,
    *,
    colorsys,
) -> str:
    red, green, blue = [max(0, min(255, int(value))) for value in rgb]
    hue, saturation, value = colorsys.rgb_to_hsv(red / 255.0, green / 255.0, blue / 255.0)
    if saturation < 0.08:
        if value >= 0.92:
            return "近白色"
        if value <= 0.16:
            return "近黑色"
        if value >= 0.68:
            return "浅灰色"
        if value <= 0.36:
            return "深灰色"
        return "中灰色"
    degrees = hue * 360.0
    if degrees < 15 or degrees >= 345:
        base_name = "红色"
    elif degrees < 42:
        base_name = "橙色"
    elif degrees < 68:
        base_name = "黄色"
    elif degrees < 155:
        base_name = "绿色"
    elif degrees < 190:
        base_name = "青色"
    elif degrees < 255:
        base_name = "蓝色"
    elif degrees < 292:
        base_name = "紫色"
    elif degrees < 345:
        base_name = "洋红色"
    else:
        base_name = "红色"
    if value >= 0.86 and saturation <= 0.42:
        prefix = "浅"
    elif value <= 0.38:
        prefix = "深"
    elif saturation <= 0.28:
        prefix = "灰"
    else:
        prefix = ""
    return f"{prefix}{base_name}"


def _extract_image_smart_palette_from_image(
    source_image,
    max_colors,
    *,
    Any,
    Image,
    describe_image_smart_color,
    math,
) -> list[dict[str, Any]]:
    working = source_image.convert("RGBA")
    working.thumbnail((240, 240), Image.Resampling.LANCZOS)
    pixel_data = (
        working.get_flattened_data()
        if hasattr(working, "get_flattened_data")
        else working.getdata()
    )
    pixels = [
        (int(red), int(green), int(blue))
        for red, green, blue, alpha in pixel_data
        if int(alpha) >= 48
    ]
    if not pixels:
        pixels = [(255, 255, 255)]
    sample = Image.new("RGB", (len(pixels), 1))
    sample.putdata(pixels)
    quantized = sample.quantize(
        colors=max(12, min(24, max(int(max_colors), 1) * 4)),
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    raw_palette = quantized.getpalette() or []
    color_counts = sorted(
        list(quantized.getcolors(maxcolors=256) or []),
        reverse=True,
    )
    clusters: list[dict[str, Any]] = []
    merge_distance = 34.0
    for count, palette_index in color_counts:
        offset = int(palette_index) * 3
        if offset + 2 >= len(raw_palette):
            continue
        color = tuple(int(value) for value in raw_palette[offset : offset + 3])
        matching_cluster = next(
            (
                cluster
                for cluster in clusters
                if math.dist(tuple(cluster["center"]), color) <= merge_distance
            ),
            None,
        )
        if matching_cluster is None:
            clusters.append(
                {
                    "count": int(count),
                    "sum": [color[channel] * int(count) for channel in range(3)],
                    "center": list(color),
                }
            )
            continue
        matching_cluster["count"] += int(count)
        for channel in range(3):
            matching_cluster["sum"][channel] += color[channel] * int(count)
            matching_cluster["center"][channel] = (
                matching_cluster["sum"][channel] / matching_cluster["count"]
            )
    clusters.sort(key=lambda item: int(item["count"]), reverse=True)
    total_pixels = max(len(pixels), 1)
    palette: list[dict[str, Any]] = []
    for cluster in clusters[: max(int(max_colors), 1)]:
        center = tuple(float(value) for value in cluster["center"])
        representative = min(pixels, key=lambda pixel: math.dist(pixel, center))
        hex_color = "#{:02X}{:02X}{:02X}".format(*representative)
        palette.append(
            {
                "hex": hex_color,
                "rgb": list(representative),
                "ratio": round(int(cluster["count"]) / total_pixels * 100.0, 1),
                "name": describe_image_smart_color(representative),
            }
        )
    return palette


def extract_image_smart_palette(
    uploaded_input,
    max_colors,
    *,
    Image,
    ImageOps,
    _extract_image_smart_palette_from_image,
    get_uploaded_file_bytes,
    io,
) -> list[dict[str, Any]]:
    image_bytes = get_uploaded_file_bytes(uploaded_input)
    if not image_bytes:
        raise RuntimeError("图片智能分析失败：上传图片为空。")
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            source = ImageOps.exif_transpose(image)
            return _extract_image_smart_palette_from_image(source, max_colors=max_colors)
    except Exception as exc:
        raise RuntimeError(f"图片智能分析失败：无法读取原图颜色。{exc}") from exc


def build_image_smart_analysis_model_prompt(base_prompt, palette) -> str:
    palette_lines = [
        f"- {str(item.get('hex') or '').upper()}：原图像素占比约 {float(item.get('ratio') or 0):.1f}%"
        for item in list(palette or [])
        if str(item.get("hex") or "").strip()
    ]
    return (
        f"{str(base_prompt or '').strip()}\n\n"
        "以下色号由系统直接从原图像素取样，是真实色卡数据，不是模型估算。"
        "color_notes 只能逐项使用这些 HEX，不得改写或新增色号：\n"
        + "\n".join(palette_lines)
    ).strip()


def parse_image_smart_analysis_payload(
    response_text,
    image_size,
    palette,
    *,
    Any,
    _image_smart_string_list,
    _image_smart_text,
    json,
    normalize_main_image_a_plus_element_bbox,
    re,
) -> dict[str, Any]:
    raw_text = str(response_text or "").strip()
    payload: dict[str, Any] = {}
    if raw_text:
        candidates = [raw_text]
        fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text, re.IGNORECASE)
        if fenced_match:
            candidates.insert(0, fenced_match.group(1).strip())
        object_start, object_end = raw_text.find("{"), raw_text.rfind("}")
        if object_start >= 0 and object_end > object_start:
            candidates.append(raw_text[object_start : object_end + 1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                payload = parsed
                break

    summary = _image_smart_text(payload.get("summary"), 180)
    if not summary:
        summary = _image_smart_text(raw_text, 180) or "已完成主图视觉拆解。"
    regions: list[dict[str, Any]] = []
    for region_index, raw_region in enumerate(list(payload.get("regions") or []), start=1):
        if not isinstance(raw_region, dict):
            continue
        bbox = normalize_main_image_a_plus_element_bbox(
            raw_region.get("bbox") or raw_region.get("box") or raw_region.get("region"),
            image_size,
        )
        if bbox is None:
            continue
        regions.append(
            {
                "id": len(regions) + 1,
                "name": _image_smart_text(raw_region.get("name"), 18) or f"区域 {region_index}",
                "bbox": bbox,
                "content": _image_smart_text(raw_region.get("content"), 90) or "可见画面内容",
                "style": _image_smart_text(raw_region.get("style"), 90) or "区域视觉关系",
            }
        )
        if len(regions) >= 6:
            break
    if not regions:
        regions = [
            {
                "id": 1,
                "name": "整体画面",
                "bbox": [0, 0, 1000, 1000],
                "content": summary,
                "style": "模型未返回可靠的局部坐标，当前按全图展示。",
            }
        ]

    allowed_hex = {
        str(item.get("hex") or "").strip().upper(): dict(item)
        for item in list(palette or [])
        if str(item.get("hex") or "").strip()
    }
    notes_by_hex: dict[str, dict[str, str]] = {}
    for raw_note in list(payload.get("color_notes") or []):
        if not isinstance(raw_note, dict):
            continue
        hex_color = str(raw_note.get("hex") or "").strip().upper()
        if hex_color not in allowed_hex:
            continue
        notes_by_hex[hex_color] = {
            "role": _image_smart_text(raw_note.get("role"), 16),
            "description": _image_smart_text(raw_note.get("description"), 54),
        }
    enriched_palette: list[dict[str, Any]] = []
    default_roles = ("主色", "辅色", "辅色", "中性色", "强调色", "点缀色")
    for color_index, palette_item in enumerate(list(palette or [])):
        color_item = dict(palette_item)
        hex_color = str(color_item.get("hex") or "").strip().upper()
        note = notes_by_hex.get(hex_color) or {}
        color_item["role"] = note.get("role") or default_roles[min(color_index, len(default_roles) - 1)]
        color_item["description"] = (
            note.get("description")
            or f"{str(color_item.get('name') or '取样色')}，约占画面 {float(color_item.get('ratio') or 0):.1f}%"
        )
        enriched_palette.append(color_item)

    return {
        "summary": summary,
        "composition": _image_smart_text(payload.get("composition"), 120) or "以主视觉为中心组织画面层级。",
        "lighting": _image_smart_text(payload.get("lighting"), 100) or "以原图可见光影和材质关系为准。",
        "typography": _image_smart_text(payload.get("typography"), 100) or "未发现可确认的文字排版信息。",
        "decorations": _image_smart_string_list(payload.get("decorations"), 5, 60),
        "style_tags": _image_smart_string_list(payload.get("style_tags"), 8, 24),
        "regions": regions,
        "palette": enriched_palette,
    }


def _load_image_smart_font(
    size,
    bold,
    *,
    ImageFont,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    file_names = (
        ("msyhbd.ttc", "simhei.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf")
        if bold
        else ("msyh.ttc", "simsun.ttc", "arial.ttf", "DejaVuSans.ttf")
    )
    for file_name in file_names:
        font_path = f"C:/Windows/Fonts/{file_name}" if ":" not in file_name else file_name
        try:
            return ImageFont.truetype(font_path, max(int(size), 8))
        except (OSError, ValueError):
            try:
                return ImageFont.truetype(file_name, max(int(size), 8))
            except (OSError, ValueError):
                continue
    return ImageFont.load_default()


def _wrap_image_smart_text(
    draw,
    value,
    font,
    max_width,
    max_lines,
    *,
    _image_smart_text,
) -> list[str]:
    normalized = _image_smart_text(value, 500)
    if not normalized:
        return []
    lines: list[str] = []
    current = ""
    for character in normalized:
        candidate = f"{current}{character}"
        text_box = draw.textbbox((0, 0), candidate, font=font)
        if current and text_box[2] - text_box[0] > max_width:
            lines.append(current)
            current = character
            if len(lines) >= max_lines:
                break
        else:
            current = candidate
    if len(lines) < max_lines and current:
        lines.append(current)
    if len(lines) >= max_lines and "".join(lines) != normalized:
        last_line = lines[-1].rstrip("。；，,. ") + "…"
        while last_line:
            text_box = draw.textbbox((0, 0), last_line, font=font)
            if text_box[2] - text_box[0] <= max_width:
                break
            last_line = last_line[:-2] + "…"
        lines[-1] = last_line
    return lines[:max_lines]


def _draw_image_smart_text_block(
    draw,
    value,
    position,
    font,
    fill,
    max_width,
    max_lines,
    line_gap,
    *,
    _wrap_image_smart_text,
) -> int:
    lines = _wrap_image_smart_text(draw, value, font, max_width, max_lines)
    x, y = position
    text_box = draw.textbbox((0, 0), "国Ag", font=font)
    line_height = max(text_box[3] - text_box[1], 1)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height + line_gap
    return y


def build_image_smart_analysis_board(
    uploaded_input,
    analysis,
    *,
    Image,
    ImageDraw,
    ImageOps,
    _draw_image_smart_text_block,
    _load_image_smart_font,
    build_image_smart_layout_comparison,
    get_uploaded_file_bytes,
    io,
    math,
) -> bytes:
    image_bytes = get_uploaded_file_bytes(uploaded_input)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            source = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        raise RuntimeError(f"无法生成视觉拆解图：原图读取失败。{exc}") from exc

    regions = list(analysis.get("regions") or [])[:6]
    palette = list(analysis.get("palette") or [])[:6]
    layout_comparison = build_image_smart_layout_comparison(uploaded_input, analysis)
    region_rows = max(1, math.ceil(len(regions) / 2))
    canvas_width = 1400
    layout_title_top = 1050
    layout_panel_top = 1102
    layout_panel_padding = 24
    layout_panel_bottom = (
        layout_panel_top + layout_panel_padding * 2 + layout_comparison.height
    )
    region_top = layout_panel_bottom + 62
    region_card_height = 188
    region_gap = 18
    canvas_height = region_top + region_rows * (region_card_height + region_gap) + 70
    board = Image.new("RGB", (canvas_width, canvas_height), (244, 242, 237))
    draw = ImageDraw.Draw(board)

    ink = (29, 31, 37)
    muted = (98, 101, 109)
    line_color = (218, 214, 206)
    card_color = (252, 251, 248)
    accent_colors = (
        (101, 83, 219),
        (27, 156, 133),
        (232, 133, 45),
        (214, 72, 123),
        (52, 125, 210),
        (119, 145, 48),
    )
    title_font = _load_image_smart_font(42, bold=True)
    subtitle_font = _load_image_smart_font(20)
    section_font = _load_image_smart_font(27, bold=True)
    heading_font = _load_image_smart_font(23, bold=True)
    body_font = _load_image_smart_font(18)
    small_font = _load_image_smart_font(16)
    tiny_font = _load_image_smart_font(14)

    draw.text((56, 44), "图片视觉拆解", font=title_font, fill=ink)
    source_width, source_height = source.size
    draw.text(
        (56, 101),
        f"分区域内容 · 真实取色 · HEX 色号    原图 {source_width}×{source_height}px",
        font=subtitle_font,
        fill=muted,
    )

    preview_panel = (56, 150, 646, 706)
    summary_panel = (670, 150, 1344, 706)
    draw.rounded_rectangle(preview_panel, radius=24, fill=card_color, outline=line_color, width=2)
    draw.rounded_rectangle(summary_panel, radius=24, fill=card_color, outline=line_color, width=2)
    draw.text((82, 174), "区域定位", font=section_font, fill=ink)

    preview_box = (82, 224, 620, 680)
    contained = ImageOps.contain(
        source,
        (preview_box[2] - preview_box[0], preview_box[3] - preview_box[1]),
        Image.Resampling.LANCZOS,
    )
    source_left = preview_box[0] + (preview_box[2] - preview_box[0] - contained.width) // 2
    source_top = preview_box[1] + (preview_box[3] - preview_box[1] - contained.height) // 2
    board.paste(contained, (source_left, source_top))
    overlay = Image.new("RGBA", board.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    badge_font = _load_image_smart_font(18, bold=True)
    for region_index, region in enumerate(regions):
        bbox = list(region.get("bbox") or [])
        if len(bbox) < 4:
            continue
        left = source_left + round(float(bbox[0]) / 1000 * contained.width)
        top = source_top + round(float(bbox[1]) / 1000 * contained.height)
        right = source_left + round(float(bbox[2]) / 1000 * contained.width)
        bottom = source_top + round(float(bbox[3]) / 1000 * contained.height)
        accent = accent_colors[region_index % len(accent_colors)]
        overlay_draw.rectangle(
            (left, top, right, bottom),
            fill=(*accent, 30),
            outline=(*accent, 255),
            width=4,
        )
        badge_left = max(source_left, min(right - 34, left + 8))
        badge_top = max(source_top, min(bottom - 34, top + 8))
        overlay_draw.ellipse(
            (badge_left, badge_top, badge_left + 34, badge_top + 34),
            fill=(*accent, 255),
        )
        label = str(region_index + 1)
        label_box = overlay_draw.textbbox((0, 0), label, font=badge_font)
        overlay_draw.text(
            (
                badge_left + (34 - (label_box[2] - label_box[0])) / 2,
                badge_top + (34 - (label_box[3] - label_box[1])) / 2 - label_box[1],
            ),
            label,
            font=badge_font,
            fill=(255, 255, 255, 255),
        )
    board = Image.alpha_composite(board.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(board)

    draw.text((700, 174), "视觉摘要", font=section_font, fill=ink)
    summary_y = _draw_image_smart_text_block(
        draw,
        analysis.get("summary"),
        (700, 224),
        body_font,
        ink,
        614,
        4,
        line_gap=9,
    )
    summary_y += 12
    summary_lines = (
        ("构图", analysis.get("composition")),
        ("光影", analysis.get("lighting")),
        ("文字", analysis.get("typography")),
        ("装饰", "；".join(list(analysis.get("decorations") or [])) or "未发现明显独立装饰元素"),
        ("风格", " · ".join(list(analysis.get("style_tags") or [])) or "根据原图内容判断"),
    )
    for label, value in summary_lines:
        draw.text((700, summary_y), f"{label}：", font=heading_font, fill=ink)
        summary_y = _draw_image_smart_text_block(
            draw,
            value,
            (772, summary_y + 2),
            small_font,
            muted,
            535,
            2,
            line_gap=6,
        )
        summary_y += 8

    draw.text((56, 752), "真实配色", font=section_font, fill=ink)
    draw.text(
        (184, 758),
        "色块和 HEX 均直接从原图像素取样，非 AI 猜色",
        font=small_font,
        fill=muted,
    )
    palette_y = 804
    palette_gap = 14
    palette_width = (1288 - palette_gap * 5) // 6
    for color_index, color_item in enumerate(palette):
        card_left = 56 + color_index * (palette_width + palette_gap)
        card_right = card_left + palette_width
        draw.rounded_rectangle(
            (card_left, palette_y, card_right, 1006),
            radius=18,
            fill=card_color,
            outline=line_color,
            width=2,
        )
        rgb = tuple(int(value) for value in list(color_item.get("rgb") or (255, 255, 255))[:3])
        draw.rounded_rectangle(
            (card_left + 12, palette_y + 12, card_right - 12, palette_y + 82),
            radius=12,
            fill=rgb,
        )
        draw.text(
            (card_left + 14, palette_y + 95),
            str(color_item.get("hex") or ""),
            font=heading_font,
            fill=ink,
        )
        draw.text(
            (card_left + 14, palette_y + 128),
            f"{str(color_item.get('role') or '')} · {float(color_item.get('ratio') or 0):.1f}%",
            font=tiny_font,
            fill=muted,
        )
        _draw_image_smart_text_block(
            draw,
            color_item.get("description"),
            (card_left + 14, palette_y + 154),
            tiny_font,
            ink,
            palette_width - 28,
            2,
            line_gap=4,
        )

    draw.text((56, layout_title_top), "原图与纯排版对照", font=section_font, fill=ink)
    draw.text(
        (292, layout_title_top + 7),
        "左右画幅、比例和区域坐标完全对应；右侧仅保留版式骨架",
        font=small_font,
        fill=muted,
    )
    draw.rounded_rectangle(
        (56, layout_panel_top, 1344, layout_panel_bottom),
        radius=24,
        fill=card_color,
        outline=line_color,
        width=2,
    )
    layout_left = 56 + (1288 - layout_comparison.width) // 2
    board.paste(
        layout_comparison,
        (layout_left, layout_panel_top + layout_panel_padding),
    )

    draw.text((56, region_top - 48), "分区域简析", font=section_font, fill=ink)
    region_card_width = 635
    for region_index, region in enumerate(regions):
        row_index, column_index = divmod(region_index, 2)
        card_left = 56 + column_index * (region_card_width + 18)
        card_top = region_top + row_index * (region_card_height + region_gap)
        card_right = card_left + region_card_width
        card_bottom = card_top + region_card_height
        accent = accent_colors[region_index % len(accent_colors)]
        draw.rounded_rectangle(
            (card_left, card_top, card_right, card_bottom),
            radius=20,
            fill=card_color,
            outline=line_color,
            width=2,
        )
        draw.rounded_rectangle(
            (card_left, card_top, card_left + 10, card_bottom),
            radius=5,
            fill=accent,
        )
        draw.ellipse(
            (card_left + 26, card_top + 24, card_left + 66, card_top + 64),
            fill=accent,
        )
        number_text = str(region_index + 1)
        number_box = draw.textbbox((0, 0), number_text, font=heading_font)
        draw.text(
            (
                card_left + 46 - (number_box[2] - number_box[0]) / 2,
                card_top + 44 - (number_box[3] - number_box[1]) / 2 - number_box[1],
            ),
            number_text,
            font=heading_font,
            fill=(255, 255, 255),
        )
        draw.text(
            (card_left + 82, card_top + 26),
            str(region.get("name") or f"区域 {region_index + 1}"),
            font=heading_font,
            fill=ink,
        )
        content_y = _draw_image_smart_text_block(
            draw,
            region.get("content"),
            (card_left + 82, card_top + 66),
            small_font,
            ink,
            region_card_width - 110,
            2,
            line_gap=5,
        )
        _draw_image_smart_text_block(
            draw,
            region.get("style"),
            (card_left + 82, content_y + 6),
            tiny_font,
            muted,
            region_card_width - 110,
            2,
            line_gap=4,
        )
        local_palette = list(region.get("palette") or [])[:3]
        for local_index, local_color in enumerate(local_palette):
            local_hex = str(local_color.get("hex") or "")
            local_rgb = tuple(int(value) for value in list(local_color.get("rgb") or (255, 255, 255))[:3])
            chip_left = card_right - 200 + local_index * 58
            draw.rounded_rectangle(
                (chip_left, card_bottom - 34, chip_left + 48, card_bottom - 18),
                radius=8,
                fill=local_rgb,
                outline=(205, 201, 194),
                width=1,
            )
            if local_index == 0:
                draw.text(
                    (card_left + 26, card_bottom - 39),
                    f"区域取色 {local_hex}",
                    font=tiny_font,
                    fill=muted,
                )

    output = io.BytesIO()
    board.save(output, format="PNG", optimize=True)
    return output.getvalue()


def build_image_smart_layout_comparison(
    uploaded_input,
    analysis,
    *,
    Any,
    Image,
    ImageDraw,
    ImageOps,
    get_uploaded_file_bytes,
    io,
) -> Image.Image:
    image_bytes = get_uploaded_file_bytes(uploaded_input)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            source = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        raise RuntimeError(f"无法生成纯排版对照：原图读取失败。{exc}") from exc

    max_panel_width = 600
    max_panel_height = 560
    uniform_scale = min(
        max_panel_width / float(max(source.width, 1)),
        max_panel_height / float(max(source.height, 1)),
    )
    panel_width = max(1, int(round(source.width * uniform_scale)))
    panel_height = max(1, int(round(source.height * uniform_scale)))
    source_panel = source.resize(
        (panel_width, panel_height),
        Image.Resampling.LANCZOS,
    )
    wireframe = Image.new("RGB", (panel_width, panel_height), (247, 247, 247))
    draw = ImageDraw.Draw(wireframe)

    def region_area(region: dict[str, Any]) -> float:
        bbox = list(region.get("bbox") or [])
        if len(bbox) < 4:
            return 0.0
        try:
            return max(0.0, float(bbox[2]) - float(bbox[0])) * max(
                0.0,
                float(bbox[3]) - float(bbox[1]),
            )
        except (TypeError, ValueError):
            return 0.0

    regions = list(analysis.get("regions") or [])[:6]
    regions.sort(key=region_area, reverse=True)
    region_shades = (214, 204, 194, 184, 174, 164)
    for region_index, region in enumerate(regions):
        bbox = list(region.get("bbox") or [])
        if len(bbox) < 4:
            continue
        left = max(0, min(panel_width - 1, round(float(bbox[0]) / 1000 * panel_width)))
        top = max(0, min(panel_height - 1, round(float(bbox[1]) / 1000 * panel_height)))
        right = max(left + 1, min(panel_width, round(float(bbox[2]) / 1000 * panel_width)))
        bottom = max(top + 1, min(panel_height, round(float(bbox[3]) / 1000 * panel_height)))
        shade = region_shades[region_index % len(region_shades)]
        radius = max(2, min(18, round(min(right - left, bottom - top) * 0.08)))
        draw.rounded_rectangle(
            (left, top, right - 1, bottom - 1),
            radius=radius,
            fill=(shade, shade, shade),
            outline=(151, 151, 151),
            width=max(1, round(min(panel_width, panel_height) * 0.003)),
        )

    border_width = max(2, round(min(panel_width, panel_height) * 0.008))
    draw.rectangle(
        (0, 0, panel_width - 1, panel_height - 1),
        outline=(126, 126, 126),
        width=border_width,
    )

    gap = 28
    comparison = Image.new(
        "RGB",
        (panel_width * 2 + gap, panel_height),
        (252, 252, 252),
    )
    comparison.paste(source_panel, (0, 0))
    comparison.paste(wireframe, (panel_width + gap, 0))
    comparison_draw = ImageDraw.Draw(comparison)
    comparison_draw.rectangle(
        (0, 0, panel_width - 1, panel_height - 1),
        outline=(208, 208, 208),
        width=max(1, border_width // 2),
    )
    return comparison


def build_image_smart_analysis_result(
    model_result,
    uploaded_input,
    palette,
    *,
    Image,
    ImageOps,
    Path,
    _extract_image_smart_palette_from_image,
    build_image_smart_analysis_board,
    extract_image_smart_palette,
    get_uploaded_file_bytes,
    get_uploaded_input_dimensions,
    get_uploaded_input_name,
    image_bytes_to_data_url,
    io,
    parse_image_smart_analysis_payload,
    sanitize_file_name,
) -> dict[str, Any]:
    source_size = get_uploaded_input_dimensions(uploaded_input)
    extracted_palette = list(palette or extract_image_smart_palette(uploaded_input))
    analysis = parse_image_smart_analysis_payload(
        str(model_result.get("text") or ""),
        source_size,
        extracted_palette,
    )
    image_bytes = get_uploaded_file_bytes(uploaded_input)
    with Image.open(io.BytesIO(image_bytes)) as image:
        source = ImageOps.exif_transpose(image).convert("RGBA")
        for region in list(analysis.get("regions") or []):
            bbox = list(region.get("bbox") or [])
            if len(bbox) < 4:
                region["palette"] = []
                continue
            crop_box = (
                max(0, min(source.width - 1, round(float(bbox[0]) / 1000 * source.width))),
                max(0, min(source.height - 1, round(float(bbox[1]) / 1000 * source.height))),
                max(1, min(source.width, round(float(bbox[2]) / 1000 * source.width))),
                max(1, min(source.height, round(float(bbox[3]) / 1000 * source.height))),
            )
            if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
                region["palette"] = []
                continue
            region["palette"] = _extract_image_smart_palette_from_image(
                source.crop(crop_box),
                max_colors=3,
            )
    board_bytes = build_image_smart_analysis_board(uploaded_input, analysis)
    source_stem = sanitize_file_name(
        Path(get_uploaded_input_name(uploaded_input) or "image").stem
    )
    result = dict(model_result)
    result["images"] = []
    result["text"] = str(analysis.get("summary") or "").strip()
    result["visual_analysis"] = {
        **analysis,
        "source_size": source_size,
        "board_image": image_bytes_to_data_url(board_bytes, "image/png"),
        "board_file_name": f"{source_stem}_视觉与排版拆解.png",
    }
    return result


def render_image_smart_analysis_report(
    result,
    job_status,
    result_key,
    *,
    datetime,
    decode_data_url,
    html,
    re,
    render_zoomable_image_gallery,
    st,
) -> None:
    normalized_report = str(result.get("text") or "").strip()
    visual_analysis = (
        dict(result.get("visual_analysis") or {})
        if isinstance(result.get("visual_analysis"), dict)
        else {}
    )
    normalized_status = str(job_status or "").strip().lower()
    board_image = str(visual_analysis.get("board_image") or "").strip()
    if not normalized_report and not board_image:
        empty_title = "正在理解图片内容" if normalized_status in {"queued", "running"} else "等待分析主图"
        empty_subtitle = (
            "AI 正在识别画面区域，并从原图像素提取真实色卡"
            if normalized_status in {"queued", "running"}
            else "拖入 1 张主图并点击“开始智能分析”，这里会显示分区域视觉拆解图"
        )
        st.markdown(
            '<div class="result-empty">'
            '<div class="empty-icon">◫</div>'
            f'<div class="empty-title">{html.escape(empty_title)}</div>'
            f'<div class="empty-subtitle">{html.escape(empty_subtitle)}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        return

    safe_result_key = re.sub(r"[^0-9A-Za-z_-]+", "_", str(result_key or "latest"))
    if board_image:
        render_zoomable_image_gallery(
            [board_image],
            columns=1,
            thumb_height=None,
            component_key=f"image_smart_analysis_board_{safe_result_key}",
            fit_mode="contain",
            max_width_percent=100,
            compress_preview=True,
            include_full_src=True,
            full_images=[board_image],
            embed_full_src=True,
        )
        decoded_board = decode_data_url(board_image)
        if decoded_board is not None:
            board_bytes, _mime_type = decoded_board
            st.download_button(
                "下载完整视觉拆解图（PNG）",
                data=board_bytes,
                file_name=str(
                    visual_analysis.get("board_file_name")
                    or "图片视觉与排版拆解.png"
                ),
                mime="image/png",
                key=f"download_image_smart_analysis_board_{safe_result_key}",
                icon=":material/download:",
                type="primary",
                use_container_width=True,
            )
        st.caption(
            "原图与灰度纯排版已按相同画幅并排合入拆解图；色卡与 HEX 色号由系统直接读取原图像素生成。"
        )
        return

    with st.container(border=True):
        st.markdown(
            '<div class="image-smart-analysis-report-marker"></div>',
            unsafe_allow_html=True,
        )
        st.markdown(normalized_report)
    st.download_button(
        "下载分析报告（Markdown）",
        data=normalized_report,
        file_name=f"图片智能分析报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
        mime="text/markdown; charset=utf-8",
        key=f"download_image_smart_analysis_{safe_result_key}",
        icon=":material/download:",
        use_container_width=True,
    )
