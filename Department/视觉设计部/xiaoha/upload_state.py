"""Manage signed upload actions and user-scoped upload state."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_upload_delete_token(
    widget_key,
    item_index,
    *,
    base64,
    json,
) -> str:
    payload = json.dumps(
        {
            "widget_key": str(widget_key or "").strip(),
            "item_index": int(item_index),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def consume_pending_upload_delete(
    *,
    UPLOAD_DELETE_QUERY_KEY,
    clear_query_param,
    parse_upload_delete_token,
    remove_upload_cache_item,
    reset_upload_widget,
    st,
) -> bool:
    delete_token = str(st.query_params.get(UPLOAD_DELETE_QUERY_KEY, "")).strip()
    if not delete_token:
        return False
    clear_query_param(UPLOAD_DELETE_QUERY_KEY)
    parsed = parse_upload_delete_token(delete_token)
    if parsed is None:
        return False
    widget_key, item_index = parsed
    remove_upload_cache_item(widget_key, item_index)
    reset_upload_widget(widget_key)
    return True


def build_upload_reorder_token(
    widget_key,
    source_index,
    target_index,
    *,
    base64,
    json,
) -> str:
    payload = json.dumps(
        {
            "widget_key": str(widget_key or "").strip(),
            "source_index": int(source_index),
            "target_index": int(target_index),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def consume_pending_upload_reorder(
    *,
    UPLOAD_REORDER_QUERY_KEY,
    clear_query_param,
    parse_upload_reorder_token,
    reorder_upload_cache_item,
    reset_upload_widget,
    st,
) -> bool:
    reorder_token = str(st.query_params.get(UPLOAD_REORDER_QUERY_KEY, "")).strip()
    if not reorder_token:
        return False
    clear_query_param(UPLOAD_REORDER_QUERY_KEY)
    parsed = parse_upload_reorder_token(reorder_token)
    if parsed is None:
        return False
    widget_key, source_index, target_index = parsed
    reorder_upload_cache_item(widget_key, source_index, target_index)
    reset_upload_widget(widget_key)
    return True


def consume_pending_upload_replacement(
    widget_key,
    *,
    UPLOAD_REPLACE_INDEX_QUERY_KEY,
    UPLOAD_REPLACE_WIDGET_QUERY_KEY,
    clear_query_param,
    st,
) -> int | None:
    replace_widget = str(st.query_params.get(UPLOAD_REPLACE_WIDGET_QUERY_KEY, "")).strip()
    if replace_widget != str(widget_key or "").strip():
        return None
    raw_index = str(st.query_params.get(UPLOAD_REPLACE_INDEX_QUERY_KEY, "")).strip()
    clear_query_param(UPLOAD_REPLACE_WIDGET_QUERY_KEY)
    clear_query_param(UPLOAD_REPLACE_INDEX_QUERY_KEY)
    try:
        return max(int(raw_index), 0)
    except Exception:
        return 0


def get_uploader_nonce_state_key(widget_key) -> str:
    return f"uploader_nonce_{widget_key}"


def get_uploader_widget_key(
    widget_key,
    *,
    get_uploader_nonce_state_key,
    st,
) -> str:
    nonce_key = get_uploader_nonce_state_key(widget_key)
    nonce_value = int(st.session_state.get(nonce_key, 0) or 0)
    return f"{widget_key}__uploader__{nonce_value}"


def get_replace_uploader_widget_key(
    widget_key,
    item_index,
    *,
    get_uploader_nonce_state_key,
    st,
) -> str:
    nonce_key = get_uploader_nonce_state_key(widget_key)
    nonce_value = int(st.session_state.get(nonce_key, 0) or 0)
    return f"{widget_key}__replace__{item_index}__{nonce_value}"


def get_replace_payload_widget_key(
    widget_key,
    item_index,
    *,
    get_uploader_nonce_state_key,
    st,
) -> str:
    nonce_key = get_uploader_nonce_state_key(widget_key)
    nonce_value = int(st.session_state.get(nonce_key, 0) or 0)
    return f"{widget_key}__replace_payload__{item_index}__{nonce_value}"


def reset_upload_widget(
    widget_key,
    *,
    get_uploader_nonce_state_key,
    get_uploader_widget_key,
    st,
) -> None:
    current_widget_key = get_uploader_widget_key(widget_key)
    st.session_state.pop(widget_key, None)
    st.session_state.pop(current_widget_key, None)
    nonce_key = get_uploader_nonce_state_key(widget_key)
    st.session_state[nonce_key] = int(st.session_state.get(nonce_key, 0) or 0) + 1


def get_skin_texture_reference_files(
    *,
    Path,
    REFERENCE_IMAGE_EXTENSIONS,
    SKIN_TEXTURE_REFERENCE_DIR,
) -> list[Path]:
    if not SKIN_TEXTURE_REFERENCE_DIR.exists() or not SKIN_TEXTURE_REFERENCE_DIR.is_dir():
        return []
    results: list[Path] = []
    for path in sorted(SKIN_TEXTURE_REFERENCE_DIR.iterdir()):
        if path.is_file() and path.suffix.lower() in REFERENCE_IMAGE_EXTENSIONS:
            results.append(path)
    return results


def build_upload_cache_token(
    account_name,
    widget_key,
    *,
    hashlib,
) -> str:
    raw = f"{account_name}:{widget_key}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def get_upload_cache_dir(
    account_name,
    widget_key,
    *,
    UPLOAD_CACHE_DIR,
    build_upload_cache_token,
    ensure_history_storage,
    sanitize_file_name,
) -> Path:
    ensure_history_storage()
    safe_account = sanitize_file_name(account_name)
    cache_token = build_upload_cache_token(account_name, widget_key)
    return UPLOAD_CACHE_DIR / safe_account / cache_token


def replace_upload_cache(
    widget_key,
    uploaded_files,
    account_name,
    *,
    clear_upload_cache,
    get_current_account_name,
    save_upload_cache,
) -> list[dict[str, Any]]:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    if not uploaded_files:
        clear_upload_cache(widget_key, account_name=normalized_account)
        return []
    return save_upload_cache(widget_key, uploaded_files, account_name=normalized_account)


def remove_upload_cache_item(
    widget_key,
    item_index,
    account_name,
    *,
    get_current_account_name,
    load_upload_cache,
    replace_upload_cache,
) -> list[dict[str, Any]]:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    current_files = load_upload_cache(widget_key, account_name=normalized_account, max_files=None)
    remaining_files = [item for index, item in enumerate(current_files) if index != item_index]
    return replace_upload_cache(widget_key, remaining_files, account_name=normalized_account)
