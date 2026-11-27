"""Persist generated images and update usage records."""

from __future__ import annotations

from typing import Any


def save_generated_images_and_record_db(
    feature,
    model,
    prompt,
    result,
    account_name,
    *,
    Any,
    build_db_history_image_value,
    build_saved_history_file_name,
    datetime,
    ensure_feature_output_dir,
    ensure_history_thumbnail,
    get_image_extension_from_mime,
    insert_history_db_record,
    load_image_bytes_from_url,
) -> list[dict[str, Any]]:
    normalized_account = str(account_name or "admin").strip() or "admin"
    feature_key = str(feature.get("key") or "").strip()
    feature_name = str(feature.get("name") or feature_key).strip()
    created_at = datetime.now()
    created_at_text = created_at.strftime("%Y-%m-%d %H:%M:%S")
    records: list[dict[str, Any]] = []
    image_sources = list(result.get("images") or [])
    image_count = len(image_sources)
    if not image_sources:
        insert_history_db_record(
            account_name=normalized_account,
            feature_name=feature_name,
            model=str(model or ""),
            image_path="",
            created_at_text=created_at_text,
            image_count=image_count,
        )
        records.append(
            {
                "account_name": normalized_account,
                "feature_key": feature_key,
                "feature_name": feature_name,
                "model": str(model or ""),
                "images": [],
                "created_at": created_at_text,
                "image_index": 1,
            }
        )
        return records
    storage_dir = ensure_feature_output_dir(feature_key)
    for index, image_source in enumerate(image_sources, start=1):
        image_bytes, mime_type = load_image_bytes_from_url(str(image_source))
        extension = get_image_extension_from_mime(mime_type)
        file_name = build_saved_history_file_name(created_at, index, extension)
        saved_path = storage_dir / file_name
        saved_path.write_bytes(image_bytes)
        image_path_text = str(saved_path)
        db_image_path_text = build_db_history_image_value(saved_path)
        thumbnail_path_text = ensure_history_thumbnail(image_path_text)
        insert_history_db_record(
            account_name=normalized_account,
            feature_name=feature_name,
            model=str(model or ""),
            image_path=db_image_path_text,
            created_at_text=created_at_text,
            image_count=image_count,
        )
        records.append(
            {
                "account_name": normalized_account,
                "feature_key": feature_key,
                "feature_name": feature_name,
                "model": str(model or ""),
                "images": [thumbnail_path_text],
                "original_images": [image_path_text],
                "thumbnail_images": [thumbnail_path_text],
                "created_at": created_at_text,
                "image_index": index,
            }
        )
    return records


def persist_generated_images_in_background(
    feature,
    model,
    prompt,
    result,
    account_name,
    *,
    Thread,
    save_generated_images_and_record_db,
    sys,
) -> None:
    safe_feature = dict(feature)
    safe_result = {"images": list(result.get("images") or [])}
    safe_model = str(model or "")
    safe_prompt = str(prompt or "")
    safe_account_name = str(account_name or "admin")

    def worker() -> None:
        try:
            save_generated_images_and_record_db(
                feature=safe_feature,
                model=safe_model,
                prompt=safe_prompt,
                result=safe_result,
                account_name=safe_account_name,
            )
        except Exception as exc:
            print(f"[history-save] 后台保存失败：{exc}", file=sys.stderr)

    Thread(target=worker, daemon=True).start()
