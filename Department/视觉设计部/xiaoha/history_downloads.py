def sanitize_history_download_name_part(
    value,
    fallback,
    re,
):
    normalized = str(value or "").strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", normalized)
    cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")
    return (cleaned or fallback)[:48]



def format_history_download_timestamp(
    created_at,
    datetime,
    re,
):
    normalized = str(created_at or "").strip()
    if normalized:
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            return parsed.strftime("%Y%m%d_%H%M%S")
        except ValueError:
            pass
    digits = re.sub(r"\D+", "", normalized)
    if len(digits) >= 14:
        return f"{digits[:8]}_{digits[8:14]}"
    if len(digits) >= 8:
        return f"{digits[:8]}_000000"
    return "time_unknown"



def build_history_download_file_name(
    feature_name,
    created_at,
    image_index,
    image_source,
    original_name,
    uniqueness_seed,
    Path,
    format_history_download_timestamp,
    hashlib,
    infer_history_download_extension,
    sanitize_history_download_name_part,
    urllib,
):
    source_path = urllib.parse.urlparse(str(image_source or "")).path
    source_name = Path(urllib.parse.unquote(source_path)).name
    candidate_name = str(original_name or source_name or "").strip()
    extension = infer_history_download_extension(candidate_name, image_source, "")
    feature_part = sanitize_history_download_name_part(feature_name, "历史图片")
    timestamp_part = format_history_download_timestamp(created_at)
    normalized_index = max(int(image_index), 1)
    unique_source = "|".join(
        [
            str(uniqueness_seed or ""),
            str(feature_name or ""),
            str(created_at or ""),
            str(normalized_index),
            str(image_source or ""),
            str(original_name or ""),
        ]
    )
    unique_code = hashlib.sha1(unique_source.encode("utf-8")).hexdigest()[:8]
    return f"{feature_part}_{timestamp_part}_{normalized_index:02d}_{unique_code}{extension}"



def flatten_history_items(
    records,
    Any,
    Path,
    build_history_download_file_name,
    hashlib,
    urllib,
):
    items: list[dict[str, Any]] = []
    for record_index, record in enumerate(records):
        display_images = list(record.get("images") or [])
        original_images = list(record.get("original_images") or display_images)
        local_display_images = list(record.get("local_images") or display_images)
        local_original_images = list(record.get("local_original_images") or original_images)
        created_at = str(record.get("created_at") or "").strip()
        model_name = str(record.get("model") or "").strip()
        feature_name = str(record.get("feature_name") or "").strip()
        for image_index, display_image in enumerate(display_images):
            original_image = original_images[image_index] if image_index < len(original_images) else display_image
            render_display_image = (
                local_display_images[image_index] if image_index < len(local_display_images) else display_image
            )
            download_source = (
                local_original_images[image_index] if image_index < len(local_original_images) else original_image
            )
            selection_seed = "|".join(
                [
                    str(record.get("id") or record.get("result_id") or ""),
                    created_at,
                    model_name,
                    feature_name,
                    str(original_image or ""),
                    str(download_source or ""),
                    str(record_index),
                    str(image_index),
                ]
            )
            selection_id = hashlib.sha1(selection_seed.encode("utf-8")).hexdigest()
            source_name = Path(
                urllib.parse.unquote(
                    urllib.parse.urlparse(
                        str(download_source or original_image or render_display_image or display_image)
                    ).path
                )
            ).name
            download_name = build_history_download_file_name(
                feature_name,
                created_at,
                image_index + 1,
                str(download_source or original_image or render_display_image or display_image),
                original_name=source_name,
                uniqueness_seed=selection_id,
            )
            items.append(
                {
                    "display_image": render_display_image,
                    "original_image": original_image,
                    "download_source": download_source,
                    "created_at": created_at,
                    "model": model_name,
                    "feature_name": feature_name,
                    "download_name": download_name,
                    "selection_id": selection_id,
                }
            )
    return items



def get_history_item_selection_key(
    key_prefix,
    item,
    item_index,
    hashlib,
):
    selection_id = str(item.get("selection_id") or "").strip()
    if not selection_id:
        selection_seed = "|".join(
            [
                str(item.get("download_source") or ""),
                str(item.get("original_image") or ""),
                str(item.get("created_at") or ""),
                str(item_index),
            ]
        )
        selection_id = hashlib.sha1(selection_seed.encode("utf-8")).hexdigest()
    return f"{key_prefix}_select_{selection_id[:24]}"



def infer_history_download_extension(
    file_name,
    image_source,
    mime_type,
    Path,
    urllib,
):
    supported_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
    supplied_extension = Path(str(file_name or "")).suffix.lower()
    if supplied_extension in supported_extensions:
        return ".jpg" if supplied_extension == ".jpeg" else supplied_extension
    source_path = urllib.parse.urlparse(str(image_source or "")).path
    source_extension = Path(source_path).suffix.lower()
    if source_extension in supported_extensions:
        return ".jpg" if source_extension == ".jpeg" else source_extension
    normalized_mime_type = str(mime_type or "").split(";", 1)[0].strip().lower()
    mime_extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
        "image/avif": ".avif",
    }.get(normalized_mime_type)
    return mime_extension or ".png"



def build_history_download_archive_bytes(
    items,
    Path,
    infer_history_download_extension,
    io,
    load_image_bytes_from_url,
    sanitize_history_download_name_part,
    zipfile,
):
    selected_items = [dict(item) for item in list(items or []) if isinstance(item, dict)]
    if not selected_items:
        raise RuntimeError("请至少选择 1 张历史图片。")

    archive_output = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(archive_output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item_index, item in enumerate(selected_items, start=1):
            image_source = str(
                item.get("download_source")
                or item.get("original_image")
                or item.get("display_image")
                or ""
            ).strip()
            if not image_source:
                raise RuntimeError(f"第 {item_index} 张历史图片缺少原图地址，无法打包。")
            try:
                image_bytes, mime_type = load_image_bytes_from_url(image_source)
            except Exception as exc:
                raise RuntimeError(f"第 {item_index} 张历史图片读取失败：{exc}") from exc

            supplied_name = str(item.get("download_name") or "").strip()
            supplied_stem = Path(supplied_name).stem or f"history_{item_index:02d}"
            safe_stem = sanitize_history_download_name_part(
                supplied_stem,
                f"history_{item_index:02d}",
            )
            extension = infer_history_download_extension(supplied_name, image_source, mime_type)
            archive_name = f"{safe_stem}{extension}"
            duplicate_index = 2
            while archive_name.lower() in used_names:
                archive_name = f"{safe_stem}_{duplicate_index}{extension}"
                duplicate_index += 1
            used_names.add(archive_name.lower())
            archive.writestr(archive_name, image_bytes)
    return archive_output.getvalue()

