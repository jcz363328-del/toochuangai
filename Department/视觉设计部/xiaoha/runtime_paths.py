"""Resolve storage directories and escape legacy SQL string values."""

from __future__ import annotations

from pathlib import Path


def ensure_jimeng_upload_dir(
    *,
    DB_IMAGE_DIR,
    JIMENG_UPLOAD_SUBDIR,
    ensure_history_storage,
) -> Path:
    ensure_history_storage()
    upload_dir = DB_IMAGE_DIR / JIMENG_UPLOAD_SUBDIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def escape_sql_text(value) -> str:
    return str(value or "").replace("'", "''")


def ensure_db_image_dir(*, DB_IMAGE_DIR) -> Path:
    DB_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    return DB_IMAGE_DIR


def ensure_feature_output_dir(
    feature_key,
    *,
    CUTOUT_OUTPUT_DIR,
    DB_IMAGE_DIR,
) -> Path:
    output_dir = CUTOUT_OUTPUT_DIR if str(feature_key or "").strip() == "background_cutout" else DB_IMAGE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
