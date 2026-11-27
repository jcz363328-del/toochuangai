"""Normalize image inputs and encode provider-safe data."""

from __future__ import annotations

from typing import Any


def sanitize_file_name(
    file_name,
    *,
    hashlib,
    re,
) -> str:
    original_name = str(file_name or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", original_name).strip("._")
    if cleaned:
        return cleaned[:96]
    if original_name:
        return f"file_{hashlib.sha1(original_name.encode('utf-8')).hexdigest()[:12]}"
    return "upload.bin"


def get_uploaded_file_bytes(
    uploaded_file,
    *,
    Path,
) -> bytes:
    if isinstance(uploaded_file, Path):
        return uploaded_file.read_bytes()
    if isinstance(uploaded_file, dict):
        return bytes(uploaded_file.get("data") or b"")
    return uploaded_file.getvalue()


def get_uploaded_file_name(
    uploaded_file,
    *,
    Path,
) -> str:
    if isinstance(uploaded_file, Path):
        return uploaded_file.name
    if isinstance(uploaded_file, dict):
        return str(uploaded_file.get("name") or "").strip()
    return str(getattr(uploaded_file, "name", "") or "").strip()


def get_uploaded_file_type(
    uploaded_file,
    *,
    Path,
    mimetypes,
) -> str:
    if isinstance(uploaded_file, Path):
        return mimetypes.guess_type(uploaded_file.name)[0] or "application/octet-stream"
    if isinstance(uploaded_file, dict):
        return str(uploaded_file.get("type") or "").strip() or "application/octet-stream"
    return str(getattr(uploaded_file, "type", "") or "").strip() or "application/octet-stream"


def normalize_uploaded_input(
    uploaded_file,
    *,
    get_uploaded_file_bytes,
    get_uploaded_file_name,
    get_uploaded_file_type,
) -> dict[str, Any]:
    return {
        "data": get_uploaded_file_bytes(uploaded_file),
        "name": get_uploaded_file_name(uploaded_file),
        "type": get_uploaded_file_type(uploaded_file),
    }


def prepare_openrouter_request_inputs(
    uploaded_files,
    *,
    OPENROUTER_INPUT_MIN_BUDGET_BYTES,
    OPENROUTER_REQUEST_IMAGE_BUDGET_BYTES,
    prepare_openrouter_uploaded_input,
) -> list[dict[str, Any]]:
    """按请求体总预算分摊压缩所有输入图，避免多张图叠加后触发 413。"""
    files = list(uploaded_files or [])
    if not files:
        return []
    per_image_budget = max(
        OPENROUTER_INPUT_MIN_BUDGET_BYTES,
        OPENROUTER_REQUEST_IMAGE_BUDGET_BYTES // len(files),
    )
    return [
        prepare_openrouter_uploaded_input(uploaded_file, max_bytes=per_image_budget)
        for uploaded_file in files
    ]


def get_uploaded_input_closest_aspect_ratio(
    uploaded_input,
    fallback,
    *,
    DEFAULT_ASPECT_RATIO,
    Image,
    ImageOps,
    get_uploaded_file_bytes,
    io,
    select_closest_aspect_ratio,
) -> str:
    try:
        image_bytes = get_uploaded_file_bytes(uploaded_input)
        with Image.open(io.BytesIO(image_bytes)) as image:
            normalized = ImageOps.exif_transpose(image)
            if normalized.width > 0 and normalized.height > 0:
                return select_closest_aspect_ratio((normalized.width, normalized.height))
    except Exception:
        pass
    return str(fallback or DEFAULT_ASPECT_RATIO)


def get_uploaded_input_dimensions(
    uploaded_input,
    *,
    Image,
    ImageOps,
    get_uploaded_file_bytes,
    io,
) -> tuple[int, int]:
    image_bytes = get_uploaded_file_bytes(uploaded_input)
    if not image_bytes:
        raise RuntimeError("上传图片为空，请重新上传。")
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            source = ImageOps.exif_transpose(image)
            return max(int(source.width), 1), max(int(source.height), 1)
    except Exception as exc:
        raise RuntimeError(f"无法读取上传图片尺寸：{exc}") from exc


def get_image_extension_from_mime(
    mime_type,
    *,
    mimetypes,
) -> str:
    normalized_mime = str(mime_type or "").strip().lower()
    extension = mimetypes.guess_extension(normalized_mime) or ".png"
    if extension == ".jpe":
        return ".jpg"
    return extension


def decode_data_url(
    data_url,
    *,
    base64,
    urllib,
) -> tuple[bytes, str] | None:
    if not data_url.startswith("data:"):
        return None
    try:
        meta, encoded = data_url.split(",", 1)
    except ValueError:
        return None
    mime_type = meta.split(":", 1)[1].split(";", 1)[0] or "image/png"
    try:
        if ";base64" in meta:
            return base64.b64decode(encoded), mime_type
        return urllib.parse.unquote_to_bytes(encoded), mime_type
    except Exception:
        return None


def image_bytes_to_data_url(
    image_bytes,
    mime_type,
    *,
    Image,
    base64,
    io,
) -> str:
    if not str(mime_type or "").lower().startswith("image/"):
        with Image.open(io.BytesIO(image_bytes)) as image:
            mime_type = Image.MIME.get(image.format or "", "image/png")
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"
