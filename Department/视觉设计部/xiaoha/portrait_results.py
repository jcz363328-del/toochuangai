"""Prepare portrait enhancement outputs and download sources."""

from __future__ import annotations

from typing import Any


def restore_portrait_hd_source_size(
    image_url,
    source_input,
    *,
    Image,
    ImageOps,
    cover_image_to_canvas_without_distortion,
    get_uploaded_input_dimensions,
    image_bytes_to_data_url,
    io,
    load_image_bytes_from_url,
) -> str:
    """Return an exact source-sized HD frame without stretching or letterbox borders."""
    target_width, target_height = get_uploaded_input_dimensions(source_input)
    image_bytes, _mime_type = load_image_bytes_from_url(image_url)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = ImageOps.exif_transpose(image).convert("RGB")
            if converted.size == (target_width, target_height):
                return image_url
            resized = cover_image_to_canvas_without_distortion(
                converted,
                target_width,
                target_height,
            )
            output = io.BytesIO()
            resized.save(output, format="PNG")
        return image_bytes_to_data_url(output.getvalue(), "image/png")
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc).startswith("图片下载失败："):
            raise
        raise RuntimeError(f"高清结果尺寸恢复失败：{exc}") from exc


def finalize_portrait_upscale_result(
    result,
    target_size,
    *,
    Image,
    ImageOps,
    image_bytes_to_data_url,
    io,
    load_image_bytes_from_url,
) -> dict[str, Any]:
    images = []
    for image_url in list(result.get("images") or []):
        data, _mime = load_image_bytes_from_url(str(image_url))
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
            target_width, target_height = target_size
            # 只容许接口输出尺寸取整带来的约 1px 比例误差，拒绝裁剪主体。
            if (abs(round(width * target_height / height) - target_width) > 1
                    and abs(round(height * target_width / width) - target_height) > 1):
                raise RuntimeError("专用超清返回的画幅与原图不一致，本次未裁剪或拉伸，请联系管理员核查原任务。")
            image = image.convert("RGB")
            if image.size != target_size:
                image = image.resize(target_size, Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="PNG")
        images.append(image_bytes_to_data_url(output.getvalue(), "image/png"))
    if not images:
        raise RuntimeError("专用超清未返回图片。")
    result.update(images=images[:1], target_size=target_size, channel="即梦专用超清 · 原图尺寸输出")
    return result


def call_jimeng_portrait_hd(
    prompt,
    aspect_ratio,
    uploaded_files,
    feature_key,
    *,
    build_portrait_hd_prompt,
    build_portrait_hd_size_instruction,
    call_jimeng_v40,
    finalize_portrait_hd_result,
    get_portrait_hd_inputs,
    get_uploaded_input_closest_aspect_ratio,
) -> dict[str, Any]:
    portrait_inputs = get_portrait_hd_inputs(uploaded_files)
    source_input = portrait_inputs[0]
    source_aspect_ratio = get_uploaded_input_closest_aspect_ratio(source_input, fallback=aspect_ratio)
    result = call_jimeng_v40(
        prompt=(
            build_portrait_hd_prompt(prompt)
            + "\n\n"
            + build_portrait_hd_size_instruction(source_input)
        ),
        aspect_ratio=source_aspect_ratio,
        uploaded_files=portrait_inputs,
        feature_key=feature_key,
    )
    return finalize_portrait_hd_result(result, source_input)


def call_jimeng_v40(
    prompt,
    aspect_ratio,
    uploaded_files,
    feature_key,
    *,
    JIMENG_REQ_KEY,
    JIMENG_SUBMIT_ACTION,
    _JIMENG_TASK_LOCK,
    build_jimeng_request_payload,
    jimeng_signed_post,
    poll_jimeng_task_result,
    save_uploaded_inputs_for_jimeng,
) -> dict[str, Any]:
    image_urls = save_uploaded_inputs_for_jimeng(list(uploaded_files or []))
    submit_body = build_jimeng_request_payload(
        prompt,
        aspect_ratio,
        image_urls=image_urls,
        feature_key=feature_key,
    )
    with _JIMENG_TASK_LOCK:
        submit_data = jimeng_signed_post(JIMENG_SUBMIT_ACTION, submit_body, timeout=120)
        if int(submit_data.get("code") or 0) != 10000:
            raise RuntimeError(f"Agent 提交任务失败：{submit_data.get('message') or submit_data}")
        task_id = str(((submit_data.get("data") or {}).get("task_id")) or "").strip()
        if not task_id:
            raise RuntimeError("Agent 提交任务失败：返回结果里没有 task_id。")
        return poll_jimeng_task_result(JIMENG_REQ_KEY, task_id, timeout=120)


def resize_uploaded_image_locally(
    uploaded_input,
    target_width,
    target_height,
    *,
    Image,
    ImageOps,
    fit_image_to_canvas_without_distortion,
    get_uploaded_file_bytes,
    image_bytes_to_data_url,
    io,
) -> str:
    safe_width = max(1, min(int(target_width), 12000))
    safe_height = max(1, min(int(target_height), 12000))
    if safe_width * safe_height > 64_000_000:
        raise RuntimeError("目标图片不能超过 6400 万像素，请调小宽度或高度。")
    try:
        image_bytes = get_uploaded_file_bytes(uploaded_input)
        with Image.open(io.BytesIO(image_bytes)) as image:
            source = ImageOps.exif_transpose(image).convert("RGBA")
            resized = fit_image_to_canvas_without_distortion(source, safe_width, safe_height)
            output = io.BytesIO()
            resized.save(output, format="PNG", optimize=True)
        return image_bytes_to_data_url(output.getvalue(), "image/png")
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"图片尺寸处理失败：{exc}") from exc


def build_result_download_sources(
    images,
    history_records,
    *,
    build_history_download_public_url,
    flatten_history_items,
) -> list[str]:
    """Use the same persisted original-image URLs as the history gallery."""
    history_items = flatten_history_items(list(history_records or []))
    download_sources: list[str] = []
    for index, image_source in enumerate(images):
        history_source = ""
        if index < len(history_items):
            history_item = history_items[index]
            history_source = str(
                history_item.get("download_source")
                or history_item.get("original_image")
                or ""
            ).strip()
        preferred_source = history_source or str(image_source or "").strip()
        try:
            public_source = build_history_download_public_url(preferred_source)
        except Exception:
            public_source = preferred_source
        download_sources.append(public_source or str(image_source or "").strip())
    return download_sources
