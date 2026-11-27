"""日报文本格式与预览工具，无数据库或请求上下文依赖。"""
import re
from datetime import datetime
from html import unescape as html_unescape

def _xiaotu_sql_escape(value):
    return str(value or "").replace("%", "%%").replace("'", "''")

def _xiaotu_normalize_notify_time(raw_text):
    txt = str(raw_text or "").strip()
    if not txt:
        return ""
    m = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?$", txt)
    if not m:
        return ""
    return f"{int(m.group(1)):02d}:{m.group(2)}"

def _xiaotu_format_message_time(create_time_raw):
    raw = str(create_time_raw or "").strip()
    if not raw:
        return ""
    try:
        ts = int(float(raw))
        if ts > 10 ** 12:
            ts = int(ts / 1000)
        return datetime.fromtimestamp(ts).strftime('%H:%M')
    except Exception:
        return raw[:5]

def _xiaotu_clip_card_text(text, limit=900):
    raw = str(text or "").replace("\r\n", "\n").strip()
    if not raw:
        return ""
    if len(raw) <= limit:
        return raw
    return raw[: max(0, int(limit) - 1)].rstrip() + "…"

def _xiaotu_html_to_plain_text_preserve_blocks(raw_text):
    text = str(raw_text or "")
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)
    text = re.sub(r"<span\b[^>]*data-lark-record-data=[\s\S]*?</span\s*>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]*class=['\"][^'\"]*lark-record-clipboard[^'\"]*['\"][^>]*>[\s\S]*?</[^>]+>", " ", text, flags=re.I)
    text = re.sub(r"<(script|style|svg)[^>]*>[\s\S]*?</\1\s*>", " ", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<img\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(
        r"<li\b([^>]*)data-index=['\"]([^'\"]+)['\"]([^>]*)>",
        lambda m: "\n" + str(m.group(2) or "").strip() + " ",
        text,
        flags=re.I
    )
    text = re.sub(r"<li\b[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"</li\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</?(?:ol|ul)\b[^>]*>", "\n", text, flags=re.I)
    for lvl in range(6, 0, -1):
        text = re.sub(rf"<h{lvl}\b[^>]*>", "\n" + ("#" * lvl) + " ", text, flags=re.I)
        text = re.sub(rf"</h{lvl}\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<(?:strong|b)\b[^>]*>", "**", text, flags=re.I)
    text = re.sub(r"</(?:strong|b)\s*>", "**", text, flags=re.I)
    text = re.sub(r"<(?:em|i)\b[^>]*>", "*", text, flags=re.I)
    text = re.sub(r"</(?:em|i)\s*>", "*", text, flags=re.I)
    text = re.sub(r"</?(?:div|p|section|article|header|footer|blockquote|pre)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"</?(?:table|thead|tbody|tr)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"</?(?:td|th)\b[^>]*>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\*{3,}", "**", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    cleaned_lines = []
    for line in text.splitlines():
        one = str(line or "").strip()
        one = re.sub(r"^(?:[A-Za-z0-9_-]{12,}\s+)+", "", one).strip()
        if not one:
            continue
        if re.fullmatch(r"[A-Za-z0-9_-]{12,}", one):
            continue
        cleaned_lines.append(one)
    return "\n".join(cleaned_lines).strip()

def _xiaotu_extract_plain_preview_text(raw_text, limit=500):
    text = _xiaotu_html_to_plain_text_preserve_blocks(raw_text)
    return _xiaotu_clip_card_text(text, limit=limit)

def _xiaotu_normalize_compare_path(raw_path):
    txt = str(raw_path or "").strip().replace("\\", "/")
    txt = re.sub(r"^https?://[^/]+", "", txt, flags=re.I)
    return txt
