def ensure_history_storage(
    DB_IMAGE_DIR,
    UPLOAD_CACHE_DIR,
):
    UPLOAD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DB_IMAGE_DIR.mkdir(parents=True, exist_ok=True)



def convert_history_path_to_public_url(
    image_path_text,
    Path,
    ensure_db_image_dir,
    get_history_public_base_url,
    relocate_storage_path,
    urllib,
):
    normalized = relocate_storage_path(image_path_text)
    if not normalized:
        return ""
    if normalized.startswith(("http://", "https://", "data:", "file://")):
        return normalized
    candidate = Path(normalized)
    if not candidate.exists() or not candidate.is_file():
        return normalized
    try:
        relative_path = candidate.resolve().relative_to(ensure_db_image_dir().resolve())
    except Exception:
        return normalized
    encoded_relative_path = "/".join(urllib.parse.quote(part) for part in relative_path.parts)
    return f"{get_history_public_base_url()}/{encoded_relative_path}"



def build_history_download_public_url(
    image_source,
    DB_IMAGE_DIR,
    Image,
    Path,
    convert_history_path_to_public_url,
    decode_data_url,
    ensure_jimeng_upload_dir,
    get_history_public_base_url,
    get_image_extension_from_mime,
    get_jimeng_public_upload_base_url,
    hashlib,
    image_bytes_to_data_url,
    io,
    is_managed_static_image_url,
    load_image_bytes_from_url,
    urllib,
    uuid4,
):
    normalized_source = str(image_source or "").strip()
    if not normalized_source:
        return ""
    if normalized_source.startswith(("http://", "https://")):
        if is_managed_static_image_url(
            normalized_source, (get_history_public_base_url(), get_jimeng_public_upload_base_url())
        ):
            return normalized_source
        # A provider URL may reject browser CORS or expire. Publish the exact
        # original through our own asset server, without altering signed URLs.
        original_bytes, original_mime = load_image_bytes_from_url(normalized_source)
        with Image.open(io.BytesIO(original_bytes)) as original_image:
            original_mime = Image.MIME.get(original_image.format or "", original_mime)
        normalized_source = image_bytes_to_data_url(original_bytes, original_mime or "image/png")
    upload_base_url = get_jimeng_public_upload_base_url()
    if not upload_base_url:
        return normalized_source
    upload_dir = ensure_jimeng_upload_dir() / "history_downloads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Decode data URLs before touching the filesystem: an original's base64
    # payload is much longer than the OS filename limit.
    decoded = decode_data_url(normalized_source)
    source_path = Path(normalized_source) if decoded is None else None
    if source_path is not None and source_path.exists() and source_path.is_file():
        # History files already have a public route that preserves directories.
        # Flattening them into a basename-only cache can serve another original.
        try:
            source_path.resolve().relative_to(DB_IMAGE_DIR.resolve())
            public_url = convert_history_path_to_public_url(str(source_path))
            if public_url.startswith(("http://", "https://")):
                source_stat = source_path.stat()
                separator = "&" if "?" in public_url else "?"
                return f"{public_url}{separator}v={source_stat.st_mtime_ns}-{source_stat.st_size}"
        except (OSError, ValueError):
            pass
        image_bytes = source_path.read_bytes()
        target_name = f"history_download_{hashlib.sha256(image_bytes).hexdigest()}{source_path.suffix.lower()}"
        target_path = upload_dir / target_name
        temporary_path = target_path.with_name(f".{target_name}.{uuid4().hex}.tmp")
        try:
            if not target_path.exists():
                temporary_path.write_bytes(image_bytes)
                temporary_path.replace(target_path)
        except Exception:
            return normalized_source
        finally:
            temporary_path.unlink(missing_ok=True)
        encoded_parts = "/".join(urllib.parse.quote(part) for part in ("history_downloads", target_name))
        return f"{upload_base_url}/{encoded_parts}"
    if decoded is None:
        return normalized_source
    image_bytes, mime_type = decoded
    extension = get_image_extension_from_mime(mime_type or "image/png")
    file_name = f"history_download_{hashlib.sha256(image_bytes).hexdigest()}{extension}"
    target_path = upload_dir / file_name
    temporary_path = target_path.with_name(f".{file_name}.{uuid4().hex}.tmp")
    try:
        if not target_path.exists():
            temporary_path.write_bytes(image_bytes)
            temporary_path.replace(target_path)
    except Exception:
        return normalized_source
    finally:
        temporary_path.unlink(missing_ok=True)
    encoded_parts = "/".join(urllib.parse.quote(part) for part in ("history_downloads", file_name))
    return f"{upload_base_url}/{encoded_parts}"



def save_history_thumbnail(
    image_bytes,
    original_path,
    DB_HISTORY_THUMB_MAX_EDGE,
    DB_HISTORY_THUMB_TARGET_BYTES,
    Image,
    build_history_thumbnail_path,
    io,
):
    thumbnail_path = build_history_thumbnail_path(original_path)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = image.convert("RGB")
            converted.thumbnail((DB_HISTORY_THUMB_MAX_EDGE, DB_HISTORY_THUMB_MAX_EDGE), Image.Resampling.LANCZOS)
            quality_candidates = (82, 76, 70, 64, 58, 52)
            output_bytes = b""
            for quality in quality_candidates:
                output = io.BytesIO()
                converted.save(output, format="JPEG", quality=quality, optimize=True)
                output_bytes = output.getvalue()
                if len(output_bytes) <= DB_HISTORY_THUMB_TARGET_BYTES or quality == quality_candidates[-1]:
                    break
    except Exception:
        return str(original_path)
    thumbnail_path.write_bytes(output_bytes)
    return str(thumbnail_path)



def ensure_history_thumbnail(
    image_path_text,
    Path,
    build_history_thumbnail_path,
    relocate_storage_path,
    save_history_thumbnail,
):
    image_path = Path(relocate_storage_path(image_path_text))
    if not image_path.exists() or not image_path.is_file():
        return str(image_path_text or "")
    thumbnail_path = build_history_thumbnail_path(image_path)
    if thumbnail_path.exists() and thumbnail_path.is_file():
        return str(thumbnail_path)
    try:
        return save_history_thumbnail(image_path.read_bytes(), image_path)
    except Exception:
        return str(image_path)



def try_find_history_image_by_metadata(
    account_name,
    feature_name,
    created_at_text,
    datetime,
    ensure_db_image_dir,
    sanitize_file_name,
):
    normalized_created_at = str(created_at_text or "").strip()
    if not normalized_created_at:
        return ""
    try:
        created_at = datetime.strptime(normalized_created_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""
    prefix = created_at.strftime("%Y%m%d_%H%M%S")
    storage_dir = ensure_db_image_dir()
    candidates = sorted(storage_dir.glob(f"{prefix}_*"), key=lambda path: path.name)
    if not candidates:
        return ""
    safe_account = sanitize_file_name(account_name or "")
    narrowed_candidates = [
        path
        for path in candidates
        if safe_account and safe_account.lower() in path.name.lower()
    ]
    if narrowed_candidates:
        return str(narrowed_candidates[0])
    return str(candidates[0])



def resolve_db_history_image_path(
    image_path_text,
    account_name,
    feature_name,
    created_at_text,
    Path,
    ensure_db_image_dir,
    relocate_storage_path,
    try_find_history_image_by_metadata,
):
    normalized = relocate_storage_path(image_path_text)
    if not normalized:
        return try_find_history_image_by_metadata(account_name, feature_name, created_at_text)
    candidate = Path(normalized)
    if candidate.is_absolute():
        return str(candidate)
    resolved_path = ensure_db_image_dir() / candidate.name
    if resolved_path.exists() and resolved_path.is_file():
        return str(resolved_path)
    same_prefix_candidates = sorted(
        ensure_db_image_dir().glob(f"{candidate.stem}*{candidate.suffix}"),
        key=lambda path: path.name,
    )
    if same_prefix_candidates:
        return str(same_prefix_candidates[0])
    return try_find_history_image_by_metadata(account_name, feature_name, created_at_text)



def insert_history_db_record(
    account_name,
    feature_name,
    model,
    image_path,
    created_at_text,
    image_count,
    DB_HISTORY_TABLE,
    execute_db_non_query,
):
    insert_query = (
        f"INSERT INTO {DB_HISTORY_TABLE} (ZhangHao, GongNeng, MoXing, TuPian, RiQi, ZhangShu) "
        f"VALUES (%s, %s, %s, %s, %s, %s)"
    )
    execute_db_non_query(
        insert_query,
        (
            str(account_name or ""),
            str(feature_name or ""),
            str(model or ""),
            str(image_path or ""),
            str(created_at_text or ""),
            max(int(image_count), 0),
        ),
    )



def build_local_history_records(
    feature,
    model,
    prompt,
    result,
    account_name,
    Any,
    build_history_thumbnail_source,
    datetime,
    normalize_history_image_source,
):
    normalized_account = str(account_name or "admin").strip() or "admin"
    created_at = datetime.now()
    created_at_text = created_at.strftime("%Y-%m-%d %H:%M:%S")
    records: list[dict[str, Any]] = []
    for index, image_source in enumerate(result.get("images") or [], start=1):
        try:
            local_image_source = normalize_history_image_source(image_source)
            local_thumbnail_source = build_history_thumbnail_source(image_source)
        except Exception:
            continue
        records.append(
            {
                "account_name": normalized_account,
                "feature_key": str(feature.get("key") or ""),
                "feature_name": str(feature.get("name") or ""),
                "model": str(model or ""),
                "images": [local_thumbnail_source],
                "original_images": [local_image_source],
                "thumbnail_images": [local_thumbnail_source],
                "local_images": [local_thumbnail_source],
                "local_original_images": [local_image_source],
                "created_at": created_at_text,
                "image_index": index,
            }
        )
    return records



def store_local_history_records(
    account_name,
    feature_key,
    records,
    MAX_HISTORY_RECORDS,
    st,
):
    normalized_account = str(account_name or "admin").strip() or "admin"
    user_store = dict(st.session_state.local_history_records.get(normalized_account) or {})
    existing_records = list(user_store.get(feature_key) or [])
    merged_records = list(records) + existing_records
    user_store[feature_key] = merged_records[:MAX_HISTORY_RECORDS]
    st.session_state.local_history_records[normalized_account] = user_store

