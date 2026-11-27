"""Resolve stored image paths and construct history preview and download links."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_jimeng_static_base_url(
    public_app_url,
    static_port,
    *,
    DEFAULT_PUBLIC_APP_URL,
    JIMENG_UPLOAD_ROUTE_PREFIX,
    os,
    urllib,
) -> str:
    static_port = int(os.getenv("JIMENG_PUBLIC_PORT") or static_port)
    raw_url = str(public_app_url or "").strip() or DEFAULT_PUBLIC_APP_URL
    parsed = urllib.parse.urlsplit(raw_url)
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname or "www.toochuangai.com"
    netloc = hostname
    default_port = 443 if scheme == "https" else 80
    if os.getenv("TC_SINGLE_PORT") == "1":
        netloc = parsed.netloc
    elif static_port and static_port != default_port:
        netloc = f"{hostname}:{static_port}"
    return urllib.parse.urlunsplit((scheme, netloc, JIMENG_UPLOAD_ROUTE_PREFIX, "", ""))


def build_history_static_base_url(
    public_app_url,
    static_port,
    *,
    DEFAULT_PUBLIC_APP_URL,
    HISTORY_STATIC_ROUTE_PREFIX,
    os,
    urllib,
) -> str:
    static_port = int(os.getenv("JIMENG_PUBLIC_PORT") or static_port)
    raw_url = str(public_app_url or "").strip() or DEFAULT_PUBLIC_APP_URL
    parsed = urllib.parse.urlsplit(raw_url)
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname or "www.toochuangai.com"
    netloc = hostname
    default_port = 443 if scheme == "https" else 80
    if os.getenv("TC_SINGLE_PORT") == "1":
        netloc = parsed.netloc
    elif static_port and static_port != default_port:
        netloc = f"{hostname}:{static_port}"
    return urllib.parse.urlunsplit((scheme, netloc, HISTORY_STATIC_ROUTE_PREFIX, "", ""))


def get_jimeng_public_upload_base_url(*, load_runtime_settings) -> str:
    runtime_settings = load_runtime_settings()
    return str(runtime_settings.get("jimeng_public_upload_base_url") or "").strip().rstrip("/")


def get_history_public_base_url(
    *,
    DEFAULT_JIMENG_STATIC_PORT,
    DEFAULT_PUBLIC_APP_URL,
    build_history_static_base_url,
    load_runtime_settings,
) -> str:
    runtime_settings = load_runtime_settings()
    public_app_url = str(runtime_settings.get("public_app_url") or DEFAULT_PUBLIC_APP_URL).strip() or DEFAULT_PUBLIC_APP_URL
    try:
        static_port = int(runtime_settings.get("jimeng_static_port") or DEFAULT_JIMENG_STATIC_PORT)
    except Exception:
        static_port = DEFAULT_JIMENG_STATIC_PORT
    return build_history_static_base_url(public_app_url, static_port).rstrip("/")


def build_direct_image_download_url(
    image_source,
    *,
    build_history_download_public_url,
    urllib,
) -> str:
    download_source = build_history_download_public_url(image_source)
    if not download_source.startswith(("http://", "https://")):
        return download_source
    parsed = urllib.parse.urlsplit(download_source)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["download"] = ["1"]
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(query, doseq=True),
            parsed.fragment,
        )
    )


def build_history_thumbnail_path(
    image_path,
    *,
    DB_HISTORY_THUMB_DIR_NAME,
) -> Path:
    return image_path.parent / DB_HISTORY_THUMB_DIR_NAME / f"{image_path.stem}_thumb.jpg"


def build_db_history_image_value(
    image_path,
    *,
    DB_HISTORY_PATH_MAX_LENGTH,
) -> str:
    full_path_text = str(image_path)
    if len(full_path_text) <= DB_HISTORY_PATH_MAX_LENGTH:
        return full_path_text
    file_name = image_path.name
    if len(file_name) <= DB_HISTORY_PATH_MAX_LENGTH:
        return file_name
    suffix = image_path.suffix or ".png"
    stem_limit = max(DB_HISTORY_PATH_MAX_LENGTH - len(suffix), 1)
    return f"{image_path.stem[:stem_limit]}{suffix}"


def build_saved_history_file_name(
    created_at,
    index,
    extension,
) -> str:
    return f"{created_at.strftime('%Y%m%d_%H%M%S_%f')}_{index:02d}{extension}"


def resolve_db_history_image_path(
    image_path_text,
    account_name,
    feature_name,
    created_at_text,
    *,
    Path,
    _xiaoha_history_storage,
    ensure_db_image_dir,
    relocate_storage_path,
    try_find_history_image_by_metadata,
) -> str:
    return _xiaoha_history_storage.resolve_db_history_image_path(
        image_path_text,
        account_name,
        feature_name,
        created_at_text,
        Path=Path,
        ensure_db_image_dir=ensure_db_image_dir,
        relocate_storage_path=relocate_storage_path,
        try_find_history_image_by_metadata=try_find_history_image_by_metadata,
    )


def normalize_history_image_source(
    image_source,
    *,
    image_bytes_to_data_url,
    load_image_bytes_from_url,
) -> str:
    image_bytes, mime_type = load_image_bytes_from_url(image_source)
    return image_bytes_to_data_url(image_bytes, mime_type or "image/png")


def build_history_thumbnail_source(
    image_source,
    *,
    build_gallery_preview_data_url,
    image_bytes_to_data_url,
    load_image_bytes_from_url,
) -> str:
    image_bytes, mime_type = load_image_bytes_from_url(image_source)
    preview_item = build_gallery_preview_data_url(image_bytes, mime_type or "image/png")
    if preview_item is not None:
        return preview_item[0]
    return image_bytes_to_data_url(image_bytes, mime_type or "image/png")


def prepare_result_for_frontend(
    result,
    *,
    Any,
    FRONTEND_PRIVATE_RESULT_FIELDS,
) -> dict[str, Any]:
    """Return a UI-safe result without internal prompts or provider payloads."""
    safe_result = dict(result or {})
    for field_name in FRONTEND_PRIVATE_RESULT_FIELDS:
        safe_result.pop(field_name, None)
    history_records: list[dict[str, Any]] = []
    for record in list(safe_result.get("history_records") or []):
        if not isinstance(record, dict):
            continue
        safe_record = dict(record)
        for field_name in FRONTEND_PRIVATE_RESULT_FIELDS:
            safe_record.pop(field_name, None)
        history_records.append(safe_record)
    if "history_records" in safe_result:
        safe_result["history_records"] = history_records
    return safe_result
