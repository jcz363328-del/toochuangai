"""Prepare gallery items and A+ image slice downloads."""

from __future__ import annotations

from typing import Any


def build_main_image_a_plus_crop_archive(
    image_bytes,
    preset_key,
    base_name,
    *,
    AMAZON_A_PLUS_MAX_PIXELS,
    Image,
    ImageOps,
    MAIN_IMAGE_A_PLUS_CROP_PRESETS,
    MAIN_IMAGE_A_PLUS_MAX_MOBILE_SCREENS,
    MAIN_IMAGE_A_PLUS_MIN_MOBILE_SCREENS,
    Path,
    infer_main_image_a_plus_screen_count,
    io,
    sanitize_file_name,
    zipfile,
) -> dict[str, Any]:
    preset = MAIN_IMAGE_A_PLUS_CROP_PRESETS.get(str(preset_key or "").strip())
    if preset is None:
        raise ValueError(f"未知的 A+ 裁切规格：{preset_key}")
    segment_height = int(preset["segment_height"])
    segment_count = int(preset["segment_count"])
    target_height = segment_height * segment_count
    if not image_bytes:
        raise ValueError("没有可裁切的图片内容。")

    try:
        with Image.open(io.BytesIO(image_bytes)) as opened_image:
            transposed = ImageOps.exif_transpose(opened_image)
            has_alpha = transposed.mode in {"RGBA", "LA"} or "transparency" in transposed.info
            prepared = transposed.convert("RGBA" if has_alpha else "RGB")
            source_width, source_height = prepared.size
            if source_width <= 0 or source_height <= 0:
                raise ValueError("图片尺寸无效。")
            exact_segment_count = (
                source_height // segment_height
                if source_height % segment_height == 0
                else 0
            )
            if (
                MAIN_IMAGE_A_PLUS_MIN_MOBILE_SCREENS
                <= exact_segment_count
                <= MAIN_IMAGE_A_PLUS_MAX_MOBILE_SCREENS
            ):
                segment_count = exact_segment_count
            else:
                segment_count = infer_main_image_a_plus_screen_count(
                    (source_width, source_height)
                )
            target_height = segment_height * segment_count
            if source_height != target_height:
                scale = target_height / source_height
                target_width = max(1, round(source_width * scale))
                if target_width * target_height > AMAZON_A_PLUS_MAX_PIXELS:
                    raise ValueError("图片比例过宽，等比适配后的像素数量超过处理上限。")
                resized = prepared.resize(
                    (target_width, target_height),
                    Image.Resampling.LANCZOS,
                )
                prepared.close()
                prepared = resized

            safe_stem = sanitize_file_name(Path(str(base_name or "a_plus_result")).stem)
            if not safe_stem or safe_stem == "upload.bin":
                safe_stem = "a_plus_result"
            archive_output = io.BytesIO()
            segment_sizes: list[tuple[int, int]] = []
            with zipfile.ZipFile(archive_output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                for segment_index in range(segment_count):
                    top = segment_index * segment_height
                    segment = prepared.crop((0, top, prepared.width, top + segment_height))
                    segment_output = io.BytesIO()
                    segment.save(segment_output, format="PNG", optimize=True)
                    segment.close()
                    segment_name = (
                        f"{safe_stem}_{preset['suffix']}_{segment_index + 1:02d}.png"
                    )
                    archive.writestr(segment_name, segment_output.getvalue())
                    segment_sizes.append((prepared.width, segment_height))
            prepared.close()
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"A+ 图片裁切失败：{exc}") from exc

    return {
        "data": archive_output.getvalue(),
        "file_name": f"{safe_stem}_{preset['suffix']}_{segment_count}_segments.zip",
        "mime": "application/zip",
        "label": str(preset["label"]),
        "segment_height": segment_height,
        "segment_count": segment_count,
        "segment_sizes": segment_sizes,
        "source_size": (source_width, source_height),
        "normalized_size": (segment_sizes[0][0], target_height),
    }


def build_main_image_a_plus_crop_archive_from_source(
    image_source,
    preset_key,
    base_name,
    *,
    build_main_image_a_plus_crop_archive,
    load_image_bytes_from_url,
) -> dict[str, Any]:
    image_bytes, _mime_type = load_image_bytes_from_url(image_source)
    return build_main_image_a_plus_crop_archive(image_bytes, preset_key, base_name)


def build_gallery_item(
    image_source,
    compress_preview,
    include_full_src,
    full_image_source,
    direct_src,
    embed_full_src,
    *,
    Any,
    Image,
    build_gallery_preview_data_url,
    decode_data_url,
    get_history_public_base_url,
    get_jimeng_public_upload_base_url,
    image_bytes_to_data_url,
    io,
    is_managed_static_image_url,
    load_image_bytes_from_url,
    urllib,
    build_history_download_public_url=None,
) -> dict[str, Any] | None:
    normalized_image_source = str(image_source or "").strip()
    normalized_full_src = str(full_image_source or "").strip()
    if direct_src:
        if not normalized_image_source:
            return None
        item: dict[str, Any] = {
            "src": normalized_image_source,
            "width": 1,
            "height": 1,
        }
        if include_full_src:
            item["full_src"] = normalized_full_src or normalized_image_source
        return item
    original_full_src = ""
    decoded_data_url = decode_data_url(normalized_image_source)
    if decoded_data_url is not None:
        image_bytes, mime_type = decoded_data_url
        original_full_src = normalized_image_source
    else:
        original_full_src = normalized_image_source
        try:
            image_bytes, mime_type = load_image_bytes_from_url(normalized_image_source)
            if not normalized_image_source.startswith(("http://", "https://")):
                original_full_src = image_bytes_to_data_url(image_bytes, mime_type or "image/png")
        except Exception:
            fallback_item: dict[str, Any] = {
                "src": normalized_image_source,
                "width": 1,
                "height": 1,
            }
            if include_full_src and (normalized_full_src or original_full_src):
                fallback_item["full_src"] = normalized_full_src
                if not fallback_item["full_src"]:
                    fallback_item["full_src"] = original_full_src
            return fallback_item
    if compress_preview:
        preview_item = build_gallery_preview_data_url(image_bytes, mime_type or "image/png")
        if preview_item is None:
            return None
        preview_src, width, height = preview_item
    else:
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                width, height = image.size
        except Exception:
            width, height = 0, 0
        preview_src = image_bytes_to_data_url(image_bytes, mime_type or "image/png")
    item = {
        "src": preview_src,
        "width": width,
        "height": height,
    }
    if include_full_src:
        normalized_full_src = str(full_image_source or "").strip()
        if normalized_full_src:
            if embed_full_src and not normalized_full_src.startswith("data:"):
                try:
                    if normalized_full_src == normalized_image_source:
                        full_image_bytes, full_mime_type = image_bytes, mime_type
                    else:
                        full_image_bytes, full_mime_type = load_image_bytes_from_url(normalized_full_src)
                    item["full_src"] = image_bytes_to_data_url(full_image_bytes, full_mime_type or "image/png")
                except Exception:
                    item["full_src"] = normalized_full_src
            else:
                item["full_src"] = normalized_full_src
        elif original_full_src:
            # Provider asset URLs can display in <img> yet reject browser fetch
            # through CORS. We already have their untouched original bytes.
            source_url = urllib.parse.urlsplit(normalized_image_source)
            is_remote_original = source_url.scheme in {"http", "https"} and not is_managed_static_image_url(
                normalized_image_source, (get_history_public_base_url(), get_jimeng_public_upload_base_url())
            )
            item["full_src"] = (
                image_bytes_to_data_url(image_bytes, mime_type or "image/png")
                if embed_full_src and is_remote_original else original_full_src
            )
        elif not compress_preview:
            item["full_src"] = preview_src
    if include_full_src and not embed_full_src and build_history_download_public_url:
        # Publish exact original bytes separately. Only the small preview and
        # a URL travel in the page; the viewer requests the original on click.
        original_source = item.get("full_src") or normalized_image_source
        if original_source == normalized_image_source and normalized_image_source.startswith(("http://", "https://")):
            if not is_managed_static_image_url(
                normalized_image_source, (get_history_public_base_url(), get_jimeng_public_upload_base_url())
            ):
                original_source = image_bytes_to_data_url(image_bytes, mime_type or "image/png")
        item["full_src"] = build_history_download_public_url(original_source)
    return item
