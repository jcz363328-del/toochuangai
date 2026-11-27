"""Prepare feature-specific images and output constraints."""

from __future__ import annotations

from PIL import Image
from typing import Any


def build_uploaded_input_from_image_url_raw(
    image_url,
    base_name,
    *,
    load_image_bytes_from_url,
    sanitize_file_name,
) -> dict[str, Any]:
    image_bytes, mime_type = load_image_bytes_from_url(image_url)
    return {
        "data": image_bytes,
        "name": sanitize_file_name(base_name),
        "type": mime_type or "image/png",
    }


def build_portrait_hd_prompt(
    prompt,
    *,
    PORTRAIT_HD_COLOR_LOCK_RULES,
    PORTRAIT_HD_SKIN_LOCK_RULES,
) -> str:
    base_prompt = str(prompt or "").strip()
    rules = (
        f"最高优先级硬性规则：{PORTRAIT_HD_SKIN_LOCK_RULES}{PORTRAIT_HD_COLOR_LOCK_RULES}\n"
        "图片使用规则：\n"
        "- 第一张图片是需要高清增强的主图，必须以第一张图片的人物身份、五官、脸型、表情、发型、构图和背景为准。\n"
        "- 如果提供了第二张图片，第二张图片仍作为高清参考图，但只允许参考其清晰度、分辨率和细节解析水平。\n"
        "- 严禁从第二张图片借用或迁移肤色、肤质、毛孔状态、皮肤光泽、颗粒感、斑点、妆容、脸型、五官、眼睛、表情、发型、服饰、背景、色温、色调、白平衡、曝光、对比度或任何色彩风格。\n"
        "- 最终皮肤必须逐项保持第1张原图状态，不得磨皮、祛斑、去痣、去痘印、去细纹、提亮或调色。\n"
        "- 最终整张画面的色温、色调、白平衡和全部颜色关系必须逐项保持第1张原图状态，只能增加清晰度，禁止任何自动校色或风格化调色。\n"
        "- 最终结果必须仍然是第一张图片中的同一个人。\n"
        "- 最终画布的像素宽度和像素高度必须分别与第1张原图完全一致，只提升清晰度。\n"
        "- 禁止裁剪、扩图、补边、旋转、拉伸、改变宽高比或重新取景；必须完整保留原图上下左右四边的所有内容。"
    )
    if base_prompt:
        return f"{base_prompt}\n\n{rules}"
    return rules


def build_portrait_hd_size_instruction(
    source_input,
    *,
    get_uploaded_input_dimensions,
) -> str:
    source_width, source_height = get_uploaded_input_dimensions(source_input)
    return (
        f"尺寸锁定：第1张原图是 {source_width}×{source_height}px。"
        f"最终结果必须严格为 {source_width}×{source_height}px，宽度和高度都不能改变。"
        "仅增强原图已有像素内容的清晰度；禁止裁剪、扩图、补边、旋转、拉伸、改变宽高比或重新取景，"
        "原图顶部、底部、左侧和右侧的全部内容必须完整保留。"
    )


def finalize_portrait_hd_result(
    result,
    source_input,
    *,
    get_uploaded_input_dimensions,
    restore_portrait_hd_source_size,
) -> dict[str, Any]:
    processed_result = dict(result)
    target_width, target_height = get_uploaded_input_dimensions(source_input)
    processed_result["images"] = [
        restore_portrait_hd_source_size(str(image_url), source_input)
        for image_url in list(result.get("images") or [])
    ]
    processed_result["target_size"] = (target_width, target_height)
    return processed_result


def get_portrait_hd_inputs(
    uploaded_files,
    *,
    get_model_reference_files,
) -> list[Any]:
    normalized_files = list(uploaded_files or [])
    if not normalized_files:
        raise RuntimeError("高清失败：请先上传 1 张主图。")
    portrait_inputs = [normalized_files[0]]
    if len(normalized_files) >= 2:
        portrait_inputs.append(normalized_files[1])
        return portrait_inputs
    reference_files = get_model_reference_files()
    if reference_files:
        portrait_inputs.append(reference_files[0])
    return portrait_inputs


def get_latest_feature_result(feature_key) -> dict[str, Any] | None:
    return None


def prepare_uploaded_input(
    uploaded_file,
    *,
    Path,
    normalize_uploaded_input,
) -> Any:
    if isinstance(uploaded_file, Path):
        return uploaded_file
    if isinstance(uploaded_file, dict):
        return normalize_uploaded_input(uploaded_file)
    return normalize_uploaded_input(uploaded_file)


def get_uploaded_input_name(
    uploaded_input,
    *,
    Path,
) -> str:
    if isinstance(uploaded_input, Path):
        return uploaded_input.name
    if isinstance(uploaded_input, dict):
        return str(uploaded_input.get("name") or "").strip()
    return str(getattr(uploaded_input, "name", "") or "").strip()


def _detect_solid_first_screen_fill_start(
    source,
    *,
    ImageStat,
) -> int:
    """Find a continuous, solid-color bottom canvas; fail closed without one."""
    rgb = source.convert("RGB")
    width, height = rgb.size
    sample = rgb.crop((0, height - 1, width, height))
    background = tuple(int(v) for v in ImageStat.Stat(sample).median)
    pixels = rgb.load()
    # Inspect original pixels so narrow details are never discarded by downsampling.
    for y in range(height - 1, -1, -1):
        if any(max(abs(pixels[x, y][c] - background[c]) for c in range(3)) > 12
               for x in range(width)):
            start = y + 1
            if height - start < max(16, round(height * .1)):
                raise RuntimeError("首屏底稿下方未检测到足够的纯色留白，请上传带下方留白的底稿。")
            return start
    raise RuntimeError("首屏底稿没有可识别的首屏内容，请检查上传图片。")


def detect_first_screen_fill_start(
    source,
    *,
    detect_first_screen_fill_bounds,
) -> int:
    return detect_first_screen_fill_bounds(source)[0]


def fit_selling_points_region(
    image,
    size,
    background,
    *,
    Image,
    ImageOps,
) -> Image.Image:
    """Contain the entire generated design; keep the original background in any padding."""
    image = ImageOps.exif_transpose(image).convert('RGBA')
    fitted = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    if isinstance(background, Image.Image):
        canvas = background.convert('RGBA').copy()
        if canvas.size != size:
            raise ValueError("卖点背景尺寸必须与安全区域一致。")
    else:
        canvas = Image.new('RGBA', size, tuple(background) + (255,))
    canvas.alpha_composite(fitted, ((size[0]-fitted.width)//2, (size[1]-fitted.height)//2))
    return canvas


def preserve_first_screen_pixels(
    image_url,
    uploaded_input,
    *,
    Image,
    ImageOps,
    build_first_screen_fill_mask,
    find_first_screen_safe_region,
    fit_selling_points_region,
    get_uploaded_file_bytes,
    image_bytes_to_data_url,
    io,
    load_image_bytes_from_url,
) -> str:
    """Keep the same original-content lock for legacy callers."""
    with Image.open(io.BytesIO(get_uploaded_file_bytes(uploaded_input))) as image:
        source = ImageOps.exif_transpose(image).convert('RGBA')
    bounds = find_first_screen_safe_region(build_first_screen_fill_mask(source))
    data, _mime = load_image_bytes_from_url(image_url)
    with Image.open(io.BytesIO(data)) as image:
        # Legacy input is an entire design, so contain it instead of cropping it.
        designed = fit_selling_points_region(image, (bounds[2]-bounds[0], bounds[3]-bounds[1]), source.crop(bounds))
    canvas = source.copy()
    canvas.paste(designed, bounds[:2])
    output = io.BytesIO()
    canvas.save(output, format='PNG')
    return image_bytes_to_data_url(output.getvalue(), 'image/png')


def selling_points_bottom_blank_fraction(
    image,
    *,
    ImageStat,
) -> float:
    """Measure a large empty tail using the center, ignoring decorative side borders."""
    rgb = image.convert('RGB')
    margin = max(1,rgb.width//10)
    small = rgb.crop((margin,0,rgb.width-margin,rgb.height)).resize((160,400))
    blank = 0
    for y in range(small.height-1,-1,-1):
        if max(ImageStat.Stat(small.crop((0,y,small.width,y+1))).stddev) > 6:
            break
        blank += 1
    return blank / small.height


def request_selling_points_layout(
    model,
    prompt,
    inputs,
    size,
    background,
    *,
    AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
    call_openrouter_images_api,
    select_closest_aspect_ratio,
):
    result = call_openrouter_images_api(
        model=model, prompt=prompt, uploaded_files=inputs,
        aspect_ratio=select_closest_aspect_ratio(size),
        resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
    )
    if not result.get('images'):
        raise RuntimeError("卖点区域未返回图片。")
    return result


def _amazon_a_plus_row_profile(
    source,
    *,
    Image,
    math,
) -> tuple[list[float], list[float], int]:
    """Return per-row brightness mean/std profiles for section boundary detection."""
    sample_width = 320
    sample_height = max(120, min(1200, int(source.height * sample_width / max(source.width, 1))))
    sample = source.convert("L").resize((sample_width, sample_height), Image.Resampling.BILINEAR)
    pixels = list(sample.getdata())
    means: list[float] = []
    stds: list[float] = []
    for row_index in range(sample_height):
        row = pixels[row_index * sample_width : (row_index + 1) * sample_width]
        mean = sum(row) / sample_width
        variance = sum((value - mean) ** 2 for value in row) / sample_width
        means.append(mean)
        stds.append(math.sqrt(variance))
    return means, stds, sample_height


def image_url_as_uploaded_input(
    image_url,
    name,
    *,
    load_image_bytes_from_url,
    prepare_openrouter_uploaded_input,
) -> dict[str, Any]:
    image_bytes, mime_type = load_image_bytes_from_url(image_url)
    return prepare_openrouter_uploaded_input(
        {"data": image_bytes, "name": name, "type": mime_type or "image/png"}
    )


def submit_main_image_a_plus_mobile_adaptation(
    source_image,
    *,
    MAIN_IMAGE_A_PLUS_FEATURE_KEY,
    NANO_BANANA_MODEL,
    get_feature_by_key,
    st,
    submit_feature_job,
) -> dict[str, Any]:
    normalized_source = str(source_image or "").strip()
    if not normalized_source:
        raise RuntimeError("没有可用于手机端适配的 A+ 成品图。")
    feature = get_feature_by_key(MAIN_IMAGE_A_PLUS_FEATURE_KEY)
    if feature is None:
        raise RuntimeError("主图生A+功能不存在。")
    return submit_feature_job(
        feature,
        {
            "feature": dict(feature),
            "model": NANO_BANANA_MODEL,
            "prompt": "",
            "uploaded_files": [],
            "output_mode": "image",
            "main_image_a_plus_adapt_mobile": True,
            "main_image_a_plus_desktop_source": normalized_source,
            "account_name": str(st.session_state.get("auth_username") or "admin"),
        },
    )


def redact_background_error_text(
    value,
    *,
    re,
) -> str:
    """Keep diagnostics useful without persisting API keys or embedded source images."""
    text = str(value or "")
    text = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+",
        r"\1[redacted]",
        text,
    )
    text = re.sub(r"(?i)\bsk-(?:or-v1-)?[a-z0-9._-]{12,}\b", "sk-[redacted]", text)
    text = re.sub(
        r"(?i)data:image/[^;\s]+;base64,[a-z0-9+/=_-]+",
        "data:image/[redacted]",
        text,
    )
    return text[:6000]


def build_a_plus_first_screen_user_override(custom_prompt) -> str:
    """Scope optional instructions to new material while retaining the immutable base."""
    normalized = str(custom_prompt or '').strip()
    if not normalized:
        return ''
    return '\n'.join([
        '【新增卖点补充要求】以下要求仅适用于空白区域中新加入的素材及布局：',
        normalized,
        '【底稿保护优先】补充要求不得修改、删除、重绘或遮挡第1张底稿任何已有元素；去文字、改色、重排等要求只能作用于新增卖点素材。无法满足时省略对应新增元素，不能突破完整保留、禁止裁切和空间限制。',
    ])


def _compact_prompt_text(
    value,
    *,
    re,
) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def enforce_global_no_distortion_rules(
    prompt,
    *,
    prepend,
    GLOBAL_NO_DISTORTION_RULES,
) -> str:
    """Attach the geometry lock once, including for specialized generation paths."""
    normalized_prompt = str(prompt or "").strip()
    if "GLOBAL GEOMETRY LOCK" in normalized_prompt:
        return normalized_prompt
    if not normalized_prompt:
        return GLOBAL_NO_DISTORTION_RULES
    if prepend:
        return f"{GLOBAL_NO_DISTORTION_RULES}\n\n{normalized_prompt}"
    return f"{normalized_prompt}\n\n{GLOBAL_NO_DISTORTION_RULES}"


def infer_main_image_a_plus_crop_base_name(
    image_source,
    index,
    *,
    Path,
    urllib,
) -> str:
    normalized_source = str(image_source or "").strip()
    if normalized_source and not normalized_source.startswith("data:"):
        if normalized_source.startswith(("http://", "https://")):
            candidate = Path(urllib.parse.unquote(urllib.parse.urlsplit(normalized_source).path)).stem
        else:
            candidate = Path(normalized_source).stem
        if candidate:
            return candidate
    return f"a_plus_result_{index + 1:02d}"


def resize_image_to_exact_size(
    image_url,
    target_width,
    target_height,
    *,
    Image,
    fit_image_to_canvas_without_distortion,
    image_bytes_to_data_url,
    io,
    load_image_bytes_from_url,
) -> str:
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            resized = fit_image_to_canvas_without_distortion(image, target_width, target_height)
            output = io.BytesIO()
            resized.save(output, format="PNG")
        return image_bytes_to_data_url(output.getvalue(), "image/png")
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc).startswith("图片下载失败："):
            raise
        raise RuntimeError(f"本地处理失败：返回图片已收到，但在尺寸处理时出错。{exc}") from exc


def parse_size_text(
    size_text,
    *,
    AMAZON_A_PLUS_MAX_EDGE,
    AMAZON_A_PLUS_MAX_PIXELS,
    re,
) -> tuple[int, int] | None:
    normalized = size_text.strip().lower().replace("x", "*").replace("×", "*")
    match = re.fullmatch(r"(\d{2,5})\*(\d{2,5})", normalized)
    if not match:
        return None
    width = int(match.group(1))
    height = int(match.group(2))
    if (
        width <= 0
        or height <= 0
        or width > AMAZON_A_PLUS_MAX_EDGE
        or height > AMAZON_A_PLUS_MAX_EDGE
        or width * height > AMAZON_A_PLUS_MAX_PIXELS
    ):
        return None
    return width, height
