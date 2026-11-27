"""HTTP attachment headers for the original images served by Xiaoha."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit


IMAGE_STATIC_PREFIXES = ("/history_images/", "/jimeng_uploads/")


def is_managed_static_image_url(source: str, public_base_urls: Iterable[str]) -> bool:
    """Recognize our routes without confusing an external host's same path."""
    try:
        parsed = urlsplit(str(source or "").strip())
        if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
            return False
        if not unquote(parsed.path).startswith(IMAGE_STATIC_PREFIXES):
            return False
        if not parsed.netloc:
            return not parsed.scheme and parsed.path.startswith("/")
        hosts = {urlsplit(str(base or "")).hostname for base in public_base_urls}
        return parsed.hostname is not None and parsed.hostname in hosts
    except ValueError:
        return False


def resolve_local_static_image_source(
    source: str,
    *,
    history_directory: str | Path,
    upload_directory: str | Path,
    public_base_urls: Iterable[str],
) -> Path | None:
    """Resolve our own static URLs to their saved file without an HTTP round trip.

    Only a configured public hostname (or a relative static route) is accepted.
    Ports may differ when an external reverse proxy exposes the same service.
    Query parameters never select another file or alter its image bytes.
    """
    try:
        parsed = urlsplit(str(source or "").strip())
        if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
            return None
        if parsed.netloc:
            allowed_hosts = {
                urlsplit(str(base or "").strip()).hostname
                for base in public_base_urls
                if str(base or "").strip()
            }
            if not parsed.hostname or parsed.hostname not in allowed_hosts:
                return None
        elif parsed.scheme:
            return None

        route = unquote(parsed.path)
        if "\x00" in route or "\\" in route:
            return None
        if route.startswith(IMAGE_STATIC_PREFIXES[0]):
            root = Path(history_directory).resolve()
            relative_path = route[len(IMAGE_STATIC_PREFIXES[0]) :]
        elif route.startswith(IMAGE_STATIC_PREFIXES[1]):
            root = Path(upload_directory).resolve()
            relative_path = route[len(IMAGE_STATIC_PREFIXES[1]) :]
        else:
            return None
        if any(part in {".", ".."} for part in relative_path.split("/")):
            return None
        candidate = (root / relative_path).resolve()
        candidate.relative_to(root)
        return candidate if candidate.is_file() else None
    except (OSError, ValueError):
        return None


def _safe_download_name(value: str, fallback: str) -> str:
    # A suggested filename is a leaf name, even when a caller supplied a
    # Windows path. Strip controls before building either header parameter.
    name = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(character for character in name if not unicodedata.category(character).startswith("C"))
    name = re.sub(r'[<>:"|?*]', "_", name).strip(" .")
    if not name or name in (".", ".."):
        name = fallback
    # Keep the extension when shortening a large, user supplied name.
    if len(name) > 180:
        stem, dot, suffix = name.rpartition(".")
        extension = dot + suffix if dot and len(suffix) <= 16 else ""
        name = name[: 180 - len(extension)].rstrip(" .") + extension
    return name or "image.png"


def build_image_attachment_header(
    request_target: str,
    *,
    status_code: int,
    content_type: str,
    method: str = "GET",
) -> str | None:
    """Return a safe Content-Disposition only for a successful image download.

    ``request_target`` is the handler's path (including its query string).
    The optional ``filename`` query parameter controls the suggested leaf name.
    Error responses, API JSON and ordinary inline image requests stay inline.
    """
    if method.upper() != "GET" or status_code not in (200, 206):
        return None
    if not str(content_type or "").split(";", 1)[0].strip().lower().startswith("image/"):
        return None

    try:
        request_url = urlsplit(str(request_target or ""))
        path = unquote(request_url.path)
        query = parse_qs(request_url.query, keep_blank_values=True)
    except ValueError:
        return None
    if not path.startswith(IMAGE_STATIC_PREFIXES):
        return None
    if str((query.get("download") or [""])[0]).strip() != "1":
        return None

    fallback = _safe_download_name(path.rsplit("/", 1)[-1], "image.png")
    requested = str((query.get("filename") or [""])[0]).strip()
    name = _safe_download_name(requested, fallback)
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip(" .")
    ascii_stem, dot, ascii_suffix = ascii_name.rpartition(".")
    if dot and not re.search(r"[A-Za-z0-9]", ascii_stem):
        ascii_name = "image." + ascii_suffix
    elif not re.search(r"[A-Za-z0-9]", ascii_name):
        ascii_name = "image"
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name, safe="")}'
