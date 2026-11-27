"""Apply image upload edits and decode browser upload actions."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_upload_delete_token(
    raw_token,
    *,
    base64,
    json,
) -> tuple[str, int] | None:
    normalized = str(raw_token or "").strip()
    if not normalized:
        return None
    padding = "=" * (-len(normalized) % 4)
    try:
        payload = base64.urlsafe_b64decode((normalized + padding).encode("ascii")).decode("utf-8")
        parsed = json.loads(payload)
    except Exception:
        return None
    widget_key = str(parsed.get("widget_key") or "").strip()
    if not widget_key:
        return None
    try:
        item_index = int(parsed.get("item_index"))
    except Exception:
        return None
    if item_index < 0:
        return None
    return widget_key, item_index


def parse_upload_reorder_token(
    raw_token,
    *,
    base64,
    json,
) -> tuple[str, int, int] | None:
    normalized = str(raw_token or "").strip()
    if not normalized:
        return None
    padding = "=" * (-len(normalized) % 4)
    try:
        payload = base64.urlsafe_b64decode((normalized + padding).encode("ascii")).decode("utf-8")
        parsed = json.loads(payload)
        widget_key = str(parsed.get("widget_key") or "").strip()
        source_index = int(parsed.get("source_index"))
        target_index = int(parsed.get("target_index"))
    except Exception:
        return None
    if not widget_key or source_index < 0 or target_index < 0:
        return None
    return widget_key, source_index, target_index


def file_to_data_url(
    uploaded_file,
    *,
    Path,
    base64,
    mimetypes,
) -> str:
    if isinstance(uploaded_file, Path):
        raw = uploaded_file.read_bytes()
        file_name = uploaded_file.name
        mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    elif isinstance(uploaded_file, dict):
        raw = bytes(uploaded_file.get("data") or b"")
        file_name = str(uploaded_file.get("name") or "")
        mime_type = str(uploaded_file.get("type") or "") or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    else:
        raw = uploaded_file.getvalue()
        file_name = getattr(uploaded_file, "name", "")
        mime_type = getattr(uploaded_file, "type", "") or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    encoded = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def get_model_reference_files(
    *,
    APP_DIR,
    HD_MODEL_REFERENCE_FILE,
    OUTPUTS_HD_DEFAULT_REFERENCE_FILE,
    OUTPUTS_HD_REFERENCE_DIR,
    Path,
    REFERENCE_IMAGE_EXTENSIONS,
) -> list[Path]:
    if OUTPUTS_HD_DEFAULT_REFERENCE_FILE.exists() and OUTPUTS_HD_DEFAULT_REFERENCE_FILE.is_file():
        return [OUTPUTS_HD_DEFAULT_REFERENCE_FILE]
    if HD_MODEL_REFERENCE_FILE.exists() and HD_MODEL_REFERENCE_FILE.is_file():
        return [HD_MODEL_REFERENCE_FILE]
    candidate_dirs = [
        OUTPUTS_HD_REFERENCE_DIR,
        APP_DIR / "model_reference",
        APP_DIR / "__pycache__" / "model_reference",
    ]
    results: list[Path] = []
    seen: set[Path] = set()
    for folder in candidate_dirs:
        if not folder.exists() or not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in REFERENCE_IMAGE_EXTENSIONS:
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    results.append(path)
    return results


def clear_upload_cache(
    widget_key,
    account_name,
    *,
    get_current_account_name,
    get_upload_cache_dir,
) -> None:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    cache_dir = get_upload_cache_dir(normalized_account, widget_key)
    if cache_dir.exists():
        for child in cache_dir.glob("*"):
            try:
                if child.is_file():
                    child.unlink()
            except Exception:
                pass
        try:
            cache_dir.rmdir()
        except Exception:
            pass


def reorder_upload_cache_item(
    widget_key,
    source_index,
    target_index,
    account_name,
    *,
    get_current_account_name,
    load_upload_cache,
    replace_upload_cache,
) -> list[dict[str, Any]]:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    current_files = load_upload_cache(widget_key, account_name=normalized_account, max_files=None)
    if (
        source_index < 0
        or target_index < 0
        or source_index >= len(current_files)
        or target_index >= len(current_files)
        or source_index == target_index
    ):
        return current_files
    reordered_files = list(current_files)
    moved_file = reordered_files.pop(source_index)
    reordered_files.insert(target_index, moved_file)
    return replace_upload_cache(widget_key, reordered_files, account_name=normalized_account)


def replace_upload_cache_item(
    widget_key,
    item_index,
    uploaded_file,
    account_name,
    *,
    get_current_account_name,
    load_upload_cache,
    replace_upload_cache,
) -> list[dict[str, Any]]:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    current_files = load_upload_cache(widget_key, account_name=normalized_account, max_files=None)
    if item_index < 0:
        return current_files
    if item_index < len(current_files):
        current_files[item_index] = uploaded_file
    else:
        current_files.append(uploaded_file)
    return replace_upload_cache(widget_key, current_files, account_name=normalized_account)


def build_uploaded_input_from_replace_payload(
    payload_text,
    *,
    decode_data_url,
    json,
    mimetypes,
) -> dict[str, Any] | None:
    try:
        payload = json.loads(str(payload_text or ""))
    except Exception:
        return None
    data_url = str(payload.get("data_url") or "").strip()
    decoded = decode_data_url(data_url)
    if decoded is None:
        return None
    image_bytes, mime_type = decoded
    file_name = str(payload.get("name") or "").strip() or f"replacement{mimetypes.guess_extension(mime_type) or '.png'}"
    return {
        "data": image_bytes,
        "name": file_name,
        "type": str(payload.get("type") or mime_type or "image/png"),
    }


def normalize_image_bytes_for_jimeng(
    image_bytes,
    extension,
    *,
    Image,
    io,
) -> tuple[bytes, str]:
    normalized_extension = str(extension or "").strip().lower()
    if normalized_extension in {".png", ".jpg", ".jpeg"}:
        return image_bytes, ".jpg" if normalized_extension == ".jpeg" else normalized_extension
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")
            output = io.BytesIO()
            if "A" in converted.getbands():
                converted.save(output, format="PNG")
                return output.getvalue(), ".png"
            converted.save(output, format="JPEG", quality=95, subsampling=0)
            return output.getvalue(), ".jpg"
    except Exception:
        return image_bytes, ".png"


def uploaded_input_to_data_url(
    uploaded_input,
    *,
    Path,
    build_gallery_preview_data_url,
    get_uploaded_file_bytes,
    image_bytes_to_data_url,
    mimetypes,
) -> str:
    image_bytes = get_uploaded_file_bytes(uploaded_input)
    mime_type = ""
    if isinstance(uploaded_input, Path):
        file_name = uploaded_input.name
        mime_type = mimetypes.guess_type(file_name)[0] or ""
    elif isinstance(uploaded_input, dict):
        mime_type = str(uploaded_input.get("type") or "").strip()
        file_name = str(uploaded_input.get("name") or "").strip()
    else:
        mime_type = str(getattr(uploaded_input, "type", "") or "").strip()
        file_name = str(getattr(uploaded_input, "name", "") or "").strip()
    if not mime_type:
        mime_type = mimetypes.guess_type(file_name)[0] or "image/png"
    preview_item = build_gallery_preview_data_url(image_bytes, mime_type)
    if preview_item is not None:
        return preview_item[0]
    return image_bytes_to_data_url(image_bytes, mime_type)
