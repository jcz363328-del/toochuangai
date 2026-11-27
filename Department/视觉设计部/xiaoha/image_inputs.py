"""Load images, normalize provider inputs and maintain upload caches."""

from __future__ import annotations

from typing import Any


def prepare_openrouter_uploaded_input(
    uploaded_file,
    max_bytes,
    *,
    Image,
    ImageOps,
    OPENROUTER_INPUT_MIN_BUDGET_BYTES,
    OPENROUTER_MAX_INPUT_IMAGE_EDGE,
    Path,
    io,
    normalize_uploaded_input,
    sanitize_file_name,
) -> dict[str, Any]:
    normalized = normalize_uploaded_input(uploaded_file)
    image_bytes = bytes(normalized.get("data") or b"")
    limit = max(OPENROUTER_INPUT_MIN_BUDGET_BYTES, int(max_bytes or 0))
    if not image_bytes or len(image_bytes) <= limit:
        return normalized

    original_name = sanitize_file_name(str(normalized.get("name") or "openrouter_input.png"))
    stem = Path(original_name).stem or "openrouter_input"
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = ImageOps.exif_transpose(image)
            has_alpha = working.mode in {"RGBA", "LA"} or "transparency" in working.info
            working = working.convert("RGBA") if has_alpha else working.convert("RGB")
            if max(working.size) > OPENROUTER_MAX_INPUT_IMAGE_EDGE:
                ratio = OPENROUTER_MAX_INPUT_IMAGE_EDGE / float(max(working.size))
                resized_size = (
                    max(1, int(round(working.size[0] * ratio))),
                    max(1, int(round(working.size[1] * ratio))),
                )
                working = working.resize(resized_size, Image.Resampling.LANCZOS)
            if has_alpha:
                background = Image.new("RGB", working.size, (255, 255, 255))
                background.paste(working, mask=working.getchannel("A"))
                working = background
            else:
                working = working.convert("RGB")

            quality_candidates = (94, 92, 90, 88, 86, 84, 82, 80, 76, 72, 68, 64, 60, 56, 52)
            output_bytes = b""
            for _attempt in range(8):
                for quality in quality_candidates:
                    output = io.BytesIO()
                    working.save(output, format="JPEG", quality=quality, optimize=True)
                    output_bytes = output.getvalue()
                    if len(output_bytes) <= limit:
                        return {
                            "data": output_bytes,
                            "name": f"{sanitize_file_name(stem)}_openrouter.jpg",
                            "type": "image/jpeg",
                        }
                if len(output_bytes) <= limit:
                    return {
                        "data": output_bytes,
                        "name": f"{sanitize_file_name(stem)}_openrouter.jpg",
                        "type": "image/jpeg",
                    }
                next_size = (
                    max(1, int(round(working.size[0] * 0.86))),
                    max(1, int(round(working.size[1] * 0.86))),
                )
                if next_size == working.size:
                    break
                working = working.resize(next_size, Image.Resampling.LANCZOS)
    except Exception as exc:
        raise RuntimeError(
            "OpenRouter 输入图片超过 30MB，自动压缩失败，请换一张更小的图片或降低上一步输出尺寸。"
        ) from exc

    raise RuntimeError("OpenRouter 输入图片过大，自动压缩后仍然超过请求体上限，请降低图片尺寸后重试。")


def prepare_ark_seedream_uploaded_input(
    uploaded_file,
    *,
    ARK_MAX_INPUT_IMAGE_BYTES,
    ARK_MAX_INPUT_IMAGE_EDGE,
    ARK_MAX_INPUT_IMAGE_PIXELS,
    Image,
    ImageOps,
    Path,
    io,
    math,
    normalize_uploaded_input,
    sanitize_file_name,
) -> dict[str, Any]:
    normalized = normalize_uploaded_input(uploaded_file)
    image_bytes = bytes(normalized.get("data") or b"")
    if not image_bytes:
        raise RuntimeError("即梦 5 Pro 输入图片为空，请重新上传。")

    original_name = sanitize_file_name(str(normalized.get("name") or "seedream_input.png"))
    stem = Path(original_name).stem or "seedream_input"
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = ImageOps.exif_transpose(image)
            width, height = working.size
            needs_resize = (
                max(width, height) > ARK_MAX_INPUT_IMAGE_EDGE
                or width * height > ARK_MAX_INPUT_IMAGE_PIXELS
            )
            if (
                not needs_resize
                and len(image_bytes) <= ARK_MAX_INPUT_IMAGE_BYTES
            ):
                return normalized

            scale = min(
                1.0,
                ARK_MAX_INPUT_IMAGE_EDGE / float(max(width, height)),
                math.sqrt(ARK_MAX_INPUT_IMAGE_PIXELS / float(max(width * height, 1))),
            )
            resized_size = (
                max(1, int(math.floor(width * scale))),
                max(1, int(math.floor(height * scale))),
            )
            has_alpha = working.mode in {"RGBA", "LA"} or "transparency" in working.info
            working = working.convert("RGBA") if has_alpha else working.convert("RGB")
            if resized_size != working.size:
                working = working.resize(resized_size, Image.Resampling.LANCZOS)
            if has_alpha:
                background = Image.new("RGB", working.size, (255, 255, 255))
                background.paste(working, mask=working.getchannel("A"))
                working = background
            else:
                working = working.convert("RGB")

            output_bytes = b""
            for quality in (94, 90, 86, 82, 78, 72, 66, 60, 54):
                output = io.BytesIO()
                working.save(output, format="JPEG", quality=quality, optimize=True)
                output_bytes = output.getvalue()
                if len(output_bytes) <= ARK_MAX_INPUT_IMAGE_BYTES:
                    return {
                        "data": output_bytes,
                        "name": f"{sanitize_file_name(stem)}_seedream.jpg",
                        "type": "image/jpeg",
                    }
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"即梦 5 Pro 输入图片预处理失败：{exc}") from exc

    raise RuntimeError("即梦 5 Pro 输入图片压缩后仍超过 30MB，请降低图片尺寸后重试。")


def save_upload_cache(
    widget_key,
    uploaded_files,
    account_name,
    *,
    Any,
    Path,
    get_current_account_name,
    get_upload_cache_dir,
    json,
    load_upload_cache,
    mimetypes,
    normalize_uploaded_input,
    sanitize_file_name,
) -> list[dict[str, Any]]:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    cache_dir = get_upload_cache_dir(normalized_account, widget_key)
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cache_dir / "manifest.json"
    entries: list[dict[str, Any]] = []
    for child in cache_dir.glob("*"):
        if child.name != "manifest.json" and child.is_file():
            try:
                child.unlink()
            except Exception:
                pass
    for index, uploaded_file in enumerate(uploaded_files, start=1):
        normalized = normalize_uploaded_input(uploaded_file)
        file_name = normalized["name"] or f"upload_{index}.bin"
        extension = Path(file_name).suffix or mimetypes.guess_extension(normalized["type"]) or ".bin"
        cached_name = f"{index:02d}_{sanitize_file_name(Path(file_name).stem)}{extension}"
        cached_path = cache_dir / cached_name
        cached_path.write_bytes(bytes(normalized["data"]))
        entries.append(
            {
                "file_name": file_name,
                "mime_type": normalized["type"],
                "cached_name": cached_name,
            }
        )
    manifest_path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return load_upload_cache(widget_key, account_name=normalized_account)


def load_upload_cache(
    widget_key,
    account_name,
    max_files,
    *,
    Any,
    get_current_account_name,
    get_upload_cache_dir,
    json,
    mimetypes,
) -> list[dict[str, Any]]:
    normalized_account = str(account_name or get_current_account_name()).strip() or "admin"
    cache_dir = get_upload_cache_dir(normalized_account, widget_key)
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    results: list[dict[str, Any]] = []
    for entry in list(entries or []):
        cached_name = str(entry.get("cached_name") or "").strip()
        if not cached_name:
            continue
        cached_path = cache_dir / cached_name
        if not cached_path.exists() or not cached_path.is_file():
            continue
        results.append(
            {
                "data": cached_path.read_bytes(),
                "name": str(entry.get("file_name") or cached_path.name),
                "type": str(entry.get("mime_type") or mimetypes.guess_type(cached_path.name)[0] or "application/octet-stream"),
            }
        )
        if max_files is not None and len(results) >= max_files:
            break
    return results


def prepare_main_image_a_plus_reference_input(
    uploaded_input,
    *,
    Image,
    ImageOps,
    MAIN_IMAGE_A_PLUS_REFERENCE_MAX_EDGE,
    MAIN_IMAGE_A_PLUS_REFERENCE_TARGET_BYTES,
    Path,
    io,
    normalize_uploaded_input,
    sanitize_file_name,
) -> dict[str, Any]:
    normalized = normalize_uploaded_input(uploaded_input)
    image_bytes = bytes(normalized.get("data") or b"")
    if not image_bytes:
        return normalized
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = ImageOps.exif_transpose(image).convert("RGB")
            if max(working.size) > MAIN_IMAGE_A_PLUS_REFERENCE_MAX_EDGE:
                scale = MAIN_IMAGE_A_PLUS_REFERENCE_MAX_EDGE / float(max(working.size))
                working = working.resize(
                    (
                        max(1, int(round(working.width * scale))),
                        max(1, int(round(working.height * scale))),
                    ),
                    Image.Resampling.LANCZOS,
                )
            output_bytes = b""
            for quality in (92, 88, 84, 80, 76, 72):
                output = io.BytesIO()
                working.save(output, format="JPEG", quality=quality, optimize=True)
                output_bytes = output.getvalue()
                if len(output_bytes) <= MAIN_IMAGE_A_PLUS_REFERENCE_TARGET_BYTES:
                    break
            stem = Path(str(normalized.get("name") or "a_plus_reference")).stem or "a_plus_reference"
            return {
                "data": output_bytes,
                "name": f"{sanitize_file_name(stem)}_a_plus_ref.jpg",
                "type": "image/jpeg",
            }
    except Exception:
        return normalized


def prepare_omnia_media_uploaded_input(
    uploaded_file,
    max_bytes,
    *,
    Image,
    ImageOps,
    OMNIAKEY_INPUT_MIN_BUDGET_BYTES,
    OMNIAKEY_MAX_INPUT_IMAGE_EDGE,
    Path,
    io,
    normalize_uploaded_input,
    sanitize_file_name,
) -> dict[str, Any]:
    normalized = normalize_uploaded_input(uploaded_file)
    image_bytes = bytes(normalized.get("data") or b"")
    if not image_bytes:
        raise RuntimeError("OmniaKey 输入图片为空，请重新上传。")
    limit = max(OMNIAKEY_INPUT_MIN_BUDGET_BYTES, int(max_bytes or 0))
    original_name = sanitize_file_name(str(normalized.get("name") or "omnia_input.png"))
    stem = Path(original_name).stem or "omnia_input"
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            working = ImageOps.exif_transpose(image)
            has_alpha = working.mode in {"RGBA", "LA"} or "transparency" in working.info
            working = working.convert("RGBA") if has_alpha else working.convert("RGB")
            # Decode even small uploads: filenames and browser MIME types may
            # disagree with the actual bytes. Emit a clean, explicit PNG first.
            if max(working.size) <= OMNIAKEY_MAX_INPUT_IMAGE_EDGE:
                canonical = io.BytesIO()
                working.save(canonical, format="PNG")
                if len(canonical.getvalue()) <= limit:
                    return {"data": canonical.getvalue(), "name": f"{stem}_omnia.png", "type": "image/png"}
            if has_alpha:
                background = Image.new("RGB", working.size, (255, 255, 255))
                background.paste(working, mask=working.getchannel("A"))
                working = background
            else:
                working = working.convert("RGB")
            if max(working.size) > OMNIAKEY_MAX_INPUT_IMAGE_EDGE:
                ratio = OMNIAKEY_MAX_INPUT_IMAGE_EDGE / float(max(working.size))
                working = working.resize(
                    (
                        max(1, int(round(working.size[0] * ratio))),
                        max(1, int(round(working.size[1] * ratio))),
                    ),
                    Image.Resampling.LANCZOS,
                )

            for _attempt in range(10):
                for quality in (92, 88, 84, 80, 76, 72, 68, 64, 60, 56, 52):
                    output = io.BytesIO()
                    working.save(output, format="JPEG", quality=quality, optimize=True)
                    output_bytes = output.getvalue()
                    if len(output_bytes) <= limit:
                        return {
                            "data": output_bytes,
                            "name": f"{sanitize_file_name(stem)}_omnia.jpg",
                            "type": "image/jpeg",
                        }
                next_size = (
                    max(1, int(round(working.size[0] * 0.85))),
                    max(1, int(round(working.size[1] * 0.85))),
                )
                if next_size == working.size:
                    break
                working = working.resize(next_size, Image.Resampling.LANCZOS)
    except Exception as exc:
        raise RuntimeError("OmniaKey 输入图片无法解码或转换，请重新导出为 PNG/JPEG 后上传。") from exc

    raise RuntimeError("OmniaKey 输入图片压缩后仍然超过 1MB 请求体上限，请降低图片尺寸后重试。")


def load_image_bytes_from_url(
    image_url,
    *,
    DB_IMAGE_DIR,
    HISTORY_STATIC_ROUTE_PREFIX,
    JIMENG_UPLOAD_ROUTE_PREFIX,
    Path,
    REQUEST_PROXIES,
    decode_data_url,
    ensure_jimeng_upload_dir,
    get_external_request_kwargs,
    get_history_public_base_url,
    get_jimeng_public_upload_base_url,
    get_request_limiter,
    mimetypes,
    requests,
    resolve_local_static_image_source,
    urllib,
) -> tuple[bytes, str]:
    decoded = decode_data_url(image_url)
    if decoded:
        return decoded
    normalized_url = str(image_url or "").strip()
    if urllib.parse.urlsplit(normalized_url).path.startswith(
        (f"{HISTORY_STATIC_ROUTE_PREFIX}/", f"{JIMENG_UPLOAD_ROUTE_PREFIX}/")
    ):
        saved_original = resolve_local_static_image_source(
            normalized_url,
            history_directory=DB_IMAGE_DIR,
            upload_directory=ensure_jimeng_upload_dir(),
            public_base_urls=(get_history_public_base_url(), get_jimeng_public_upload_base_url()),
        )
        if saved_original is not None:
            return saved_original.read_bytes(), mimetypes.guess_type(saved_original.name)[0] or "image/png"
    local_path = Path(image_url)
    if not image_url.startswith(("http://", "https://")) and local_path.exists() and local_path.is_file():
        mime_type = mimetypes.guess_type(local_path.name)[0] or "image/png"
        return local_path.read_bytes(), mime_type
    try:
        normalized_url = str(image_url or "").strip().lower()
        use_proxy = not (
            "volcengine" in normalized_url
            or "tos-cn-" in normalized_url
            or "imagex" in normalized_url
            or ":8502/" in normalized_url
            or "toochuangai.com/jimeng_uploads" in normalized_url
            or "omniakey" in normalized_url
            or "cloudflarestorage.com" in normalized_url
            or "r2.dev" in normalized_url
        )
        with get_request_limiter().slot("download"):
            try:
                response = requests.get(image_url, **get_external_request_kwargs(timeout=(15, 120), use_proxy=False))
            except requests.RequestException:
                if not use_proxy or not REQUEST_PROXIES:
                    raise
                # Asset GETs are safe to retry. The legacy desktop SOCKS proxy
                # may be unavailable inside Docker, so never require it first.
                response = requests.get(image_url, **get_external_request_kwargs(timeout=(15, 120), use_proxy=True))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"图片下载失败：无法下载模型返回的图片地址。{exc}") from exc
    mime_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip() or "image/png"
    return response.content, mime_type
