"""日报导出的取值、图片嵌入和可选明细工具。"""
import base64
import mimetypes
import os
import re
from html import escape as html_escape, unescape as html_unescape
from urllib.parse import parse_qs, unquote, urlparse
from secret_settings import relocate_storage_path
from .formatting import _xiaotu_html_to_plain_text_preserve_blocks

def _xiaotu_history_export_value(row, key, index):
    if isinstance(row, dict):
        if key in row:
            return row.get(key)
        return row.get(key.lower())
    values = list(row) if isinstance(row, (list, tuple)) else []
    return values[index] if index < len(values) else ""

def _xiaotu_history_export_image_data_uri(source, image_cache=None):
    raw = html_unescape(str(source or "").strip()).strip().strip('"').strip("'")
    if not raw:
        return ""
    if re.match(r"^data:image/(?:png|jpe?g|gif|webp|bmp);base64,", raw, flags=re.IGNORECASE):
        return raw

    parsed = urlparse(raw)
    if parsed.path == "/api/xiaotu/report_image":
        nested_paths = parse_qs(parsed.query or "").get("path") or []
        raw = str(nested_paths[0] if nested_paths else "").strip()
    elif parsed.scheme in {"http", "https"}:
        return ""
    raw = unquote(raw).strip().strip('"').strip("'")
    if not raw:
        return ""

    allowed_base_dirs = [
        os.path.abspath(relocate_storage_path(r"D:\tuchuangai\报告图片")),
        os.path.abspath(relocate_storage_path(r"D:\tuchuangai\报告缓存图片")),
    ]
    normalized = str(relocate_storage_path(raw) or "").replace("/", os.sep)
    if not normalized:
        return ""
    if not os.path.isabs(normalized):
        normalized = os.path.join(allowed_base_dirs[0], normalized.lstrip("\\/"))
    abs_path = os.path.abspath(normalized)
    allowed = False
    for base_dir in allowed_base_dirs:
        try:
            if os.path.commonpath([base_dir, abs_path]) == base_dir:
                allowed = True
                break
        except Exception:
            continue
    if not allowed or not os.path.isfile(abs_path):
        return ""
    if os.path.splitext(abs_path)[1].lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return ""

    cache = image_cache if isinstance(image_cache, dict) else {}
    if abs_path in cache:
        return cache[abs_path]
    mime = mimetypes.guess_type(abs_path)[0] or ""
    if not mime.startswith("image/"):
        return ""
    with open(abs_path, "rb") as image_file:
        image_bytes = image_file.read()
    if not image_bytes:
        return ""
    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    cache[abs_path] = data_uri
    return data_uri

def _xiaotu_history_export_optional_detail(label, value):
    text = _xiaotu_html_to_plain_text_preserve_blocks(value)
    if not text:
        return ""
    return (
        '<details class="record-detail">'
        f'<summary>{html_escape(label)}</summary>'
        f'<pre>{html_escape(text)}</pre>'
        '</details>'
    )
