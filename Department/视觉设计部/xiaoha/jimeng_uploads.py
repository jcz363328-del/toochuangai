"""Publish normalized Jimeng input images for processing."""

from __future__ import annotations


def save_uploaded_inputs_for_jimeng(
    uploaded_files,
    *,
    Path,
    REFERENCE_IMAGE_EXTENSIONS,
    datetime,
    ensure_jimeng_upload_dir,
    get_image_extension_from_mime,
    get_jimeng_public_upload_base_url,
    normalize_image_bytes_for_jimeng,
    prepare_jimeng_i2i_uploaded_input,
    sanitize_file_name,
    urllib,
    uuid4,
) -> list[str]:
    if not uploaded_files:
        return []
    base_url = get_jimeng_public_upload_base_url()
    if not base_url:
        raise RuntimeError("未配置 Agent 上传公网地址。请先在 config.py 中配置 `jimeng_public_upload_base_url`。")
    upload_dir = ensure_jimeng_upload_dir()
    public_urls: list[str] = []
    for index, uploaded_file in enumerate(uploaded_files, start=1):
        normalized = prepare_jimeng_i2i_uploaded_input(uploaded_file)
        image_bytes = bytes(normalized.get("data") or b"")
        if not image_bytes:
            continue
        original_name = sanitize_file_name(str(normalized.get("name") or f"jimeng_input_{index}.png"))
        extension = Path(original_name).suffix.lower()
        if extension not in REFERENCE_IMAGE_EXTENSIONS:
            extension = get_image_extension_from_mime(str(normalized.get("type") or "image/png"))
        image_bytes, extension = normalize_image_bytes_for_jimeng(image_bytes, extension)
        file_name = (
            f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{index:02d}_{uuid4().hex[:10]}{extension}"
        )
        saved_path = upload_dir / file_name
        saved_path.write_bytes(image_bytes)
        public_urls.append(f"{base_url}/{urllib.parse.quote(file_name)}")
    return public_urls
