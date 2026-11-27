"""Text and block parsing for report source documents."""
import re
import json
from datetime import datetime, date, timedelta
from html import escape as html_escape, unescape as html_unescape

def _xiaotu_extract_doc_token(url):
    u = str(url or "").strip()
    if not u:
        return ""
    pats = [
        r"/docx/([a-zA-Z0-9]+)",
        r"/docs/([a-zA-Z0-9]+)",
        r"/wiki/([a-zA-Z0-9]+)",
        r"/doc/([a-zA-Z0-9]+)",
        r"(doxcn[a-zA-Z0-9]+)"
    ]
    for p in pats:
        m = re.search(p, u)
        if m:
            return str(m.group(1) or "").strip()
    return ""


def _xiaotu_extract_source_doc_token(report_id):
    rid = str(report_id or "").strip()
    if not rid:
        return ""
    if "__" in rid:
        prefix = str(rid.split("__", 1)[0] or "").strip()
        if prefix and prefix.lower() != "manual":
            return prefix
        return ""
    if rid.lower().startswith("manual_"):
        return ""
    if re.fullmatch(r"[A-Za-z0-9]{6,120}", rid):
        return rid
    return ""


def _xiaotu_guess_title(doc_name, doc_text, doc_token):
    name = str(doc_name or "").strip()
    if name and not name.startswith("云文档-") and not name.startswith("临时文档-"):
        return name[:200]
    text = str(doc_text or "").strip()
    for line in text.splitlines():
        t = str(line or "").strip().lstrip("#").strip()
        if len(t) >= 2:
            return t[:200]
    if name:
        return name[:200]
    tok = str(doc_token or "").strip()
    return (f"云文档-{tok[:10]}" if tok else "未命名云文档")[:200]


def _xiaotu_detect_report_kind(question_text, title_text, body_text):
    s = f"{str(question_text or '')}\n{str(title_text or '')}\n{str(body_text or '')}".lower()
    if "月报" in s:
        return "月报"
    if "日报" in s:
        return "日报"
    if "周报" in s:
        return "周报"
    return "周报"


def _xiaotu_is_daily_date_heading(text_line):
    line = str(text_line or "").strip()
    if not line:
        return False
    line = re.sub(r"^[#>*\-\s]+", "", line).strip()
    if not line or len(line) > 48:
        return False
    patterns = [
        r"^(20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?)(?:\s*[（(]?[^\n（）()]{0,12}[)）]?)?(?:\s*(日报|工作日报|工作总结|总结))?$",
        r"^(\d{1,2}[月]\d{1,2}日)(?:\s*[（(]?[^\n（）()]{0,12}[)）]?)?(?:\s*(日报|工作日报|工作总结|总结))?$",
        r"^(\d{1,2}[./-]\d{1,2})(?:\s*[（(]?[^\n（）()]{0,12}[)）]?)?(?:\s*(日报|工作日报|工作总结|总结))?$",
    ]
    return any(re.match(pat, line, flags=re.I) for pat in patterns)


def _xiaotu_find_daily_date_matches(text):
    raw = str(text or "")
    if not raw:
        return []
    patterns = [
        r"(^|[\r\n])[\t >#*\-]*"
        r"(20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?(?:\s*[（(]?[^\r\n（）()]{0,12}[)）]?)?(?:\s*(?:日报|工作日报|工作总结|总结))?)"
        r"(?=\s*(?:[\r\n]|$))",
        r"(^|[\r\n])[\t >#*\-]*"
        r"(\d{1,2}月\d{1,2}日(?:\s*[（(]?[^\r\n（）()]{0,12}[)）]?)?(?:\s*(?:日报|工作日报|工作总结|总结))?)"
        r"(?=\s*(?:[\r\n]|$))",
        r"(^|[\r\n])[\t >#*\-]*"
        r"(\d{1,2}[./-]\d{1,2}(?:\s*[（(]?[^\r\n（）()]{0,12}[)）]?)?(?:\s*(?:日报|工作日报|工作总结|总结))?)"
        r"(?=\s*(?:[\r\n]|$))",
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, raw, flags=re.I):
            found.append({
                "start": int(m.start(2)),
                "text": str(m.group(2) or "").strip()
            })
    found.sort(key=lambda x: int(x.get("start") or 0))
    dedup = []
    seen = set()
    for one in found:
        key = (int(one.get("start") or 0), str(one.get("text") or ""))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(one)
    return dedup


def _xiaotu_extract_block_plain_text(block_obj):
    ignore_keys = {
        "token", "file_token", "image_token", "media_token", "resource_token", "object_token",
        "block_id", "id", "parent_id", "parentid", "url", "href", "block_type", "type"
    }
    table_like_keys = {
        "table", "cells", "cell", "table_cells", "table_cell", "rows", "row", "table_rows",
        "table_row", "header_row", "body_rows", "columns", "column", "grid", "matrix"
    }
    row_like_keys = {"rows", "row", "table_rows", "table_row", "header_row", "body_rows"}
    cell_like_keys = {"cells", "cell", "table_cells", "table_cell", "columns", "column"}

    def clean_fragment(raw):
        s = html_unescape(str(raw or "")).strip()
        if not s:
            return ""
        s = re.sub(r"\s+", " ", s).strip()
        # 去掉飞书 block 里常见的对象 id 前缀，避免出现在正文里。
        s = re.sub(r"^(?:[A-Za-z0-9_-]{12,}\s+)+", "", s).strip()
        if not s:
            return ""
        if re.fullmatch(r"[A-Za-z0-9_-]{12,}", s):
            return ""
        if re.fullmatch(r"\d{1,3}", s):
            return ""
        return s

    def merge_fragments(parts, separator=" "):
        rows = []
        for one in (parts or []):
            txt = str(one or "").strip()
            if not txt:
                continue
            rows.append(txt)
        if not rows:
            return ""
        text = separator.join(rows)
        text = re.sub(r"[ \t\f\v]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def walk(obj, parent_key=""):
        if obj is None:
            return ""
        if isinstance(obj, str):
            return clean_fragment(obj)
        if isinstance(obj, dict):
            grouped_parts = []
            cell_parts = []
            has_table_hint = False
            for k, v in obj.items():
                lk = str(k or "").strip().lower()
                if lk in ignore_keys:
                    continue
                if lk in table_like_keys:
                    has_table_hint = True
                child_text = walk(v, lk)
                if not child_text:
                    continue
                if lk in row_like_keys:
                    grouped_parts.append(child_text)
                elif lk in cell_like_keys:
                    cell_parts.append(child_text)
                else:
                    grouped_parts.append(child_text)
            if cell_parts:
                cell_line = merge_fragments(cell_parts, " | ")
                if cell_line:
                    grouped_parts.append(cell_line)
            if has_table_hint:
                return merge_fragments(grouped_parts, "\n")
            return merge_fragments(grouped_parts, " ")
        elif isinstance(obj, list):
            child_parts = []
            for item in obj:
                child_text = walk(item, parent_key)
                if child_text:
                    child_parts.append(child_text)
            if parent_key in row_like_keys:
                return merge_fragments(child_parts, "\n")
            if parent_key in cell_like_keys:
                return merge_fragments(child_parts, " | ")
            return merge_fragments(child_parts, "\n" if parent_key in table_like_keys else " ")
        return ""

    text = walk(block_obj)
    text = re.sub(r"[ \t\f\v]+", " ", str(text or ""))
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _xiaotu_order_doc_blocks(blocks):
    rows = [x for x in (blocks or []) if isinstance(x, dict)]
    if not rows:
        return []
    id_map = {}
    child_ids = set()
    for block in rows:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        if block_id and block_id not in id_map:
            id_map[block_id] = block
        children = block.get("children")
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    cid = str(child.get("block_id") or child.get("id") or child.get("child_id") or child.get("blockId") or "").strip()
                else:
                    cid = str(child or "").strip()
                if cid:
                    child_ids.add(cid)

    roots = []
    for block in rows:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        parent_id = str(block.get("parent_id") or block.get("parentId") or "").strip()
        if (not parent_id or parent_id not in id_map) and (not block_id or block_id not in child_ids):
            roots.append(block)
    if not roots:
        roots = rows[:]

    ordered = []
    seen = set()

    def visit(block):
        if not isinstance(block, dict):
            return
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        key = block_id or f"obj:{id(block)}"
        if key in seen:
            return
        seen.add(key)
        ordered.append(block)
        children = block.get("children")
        if not isinstance(children, list):
            return
        for child in children:
            if isinstance(child, dict):
                cid = str(child.get("block_id") or child.get("id") or child.get("child_id") or child.get("blockId") or "").strip()
            else:
                cid = str(child or "").strip()
            if cid and cid in id_map:
                visit(id_map[cid])

    for root in roots:
        visit(root)
    for block in rows:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        key = block_id or f"obj:{id(block)}"
        if key not in seen:
            seen.add(key)
            ordered.append(block)
    return ordered


def _xiaotu_is_image_like_block(block_obj):
    if not isinstance(block_obj, dict):
        return False
    block_type = str(block_obj.get("block_type") or block_obj.get("type") or "").lower()
    if any(k in block_type for k in ["image", "media", "file", "attachment", "gallery", "figure", "picture"]):
        return True
    keys = {str(k).lower() for k in block_obj.keys()}
    return bool({"image", "media", "file", "attachment", "gallery", "figure", "picture"} & keys)


def _xiaotu_build_date_search_keys(text):
    raw = str(text or "").strip()
    if not raw:
        return []
    nums = re.findall(r"\d+", raw)
    joined = "".join(nums)
    keys = []
    if len(joined) >= 8:
        keys.append(joined[:8])
        keys.append(joined[-4:])
    elif len(joined) >= 4:
        keys.append(joined[-4:])
    seen = set()
    out = []
    for one in keys:
        one = str(one or "").strip()
        if not one or one in seen:
            continue
        seen.add(one)
        out.append(one)
    return out


def _xiaotu_markdownish_to_html(text):
    raw = str(text or "").strip()
    if not raw:
        return "<p>暂无分析内容。</p>"
    lines = raw.splitlines()
    parts = []
    in_ul = False
    for line in lines:
        s = str(line or "").strip()
        if not s:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", s)
        if heading:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            level = min(4, max(2, len(heading.group(1)) + 1))
            parts.append(f"<h{level}>{html_escape(heading.group(2).strip())}</h{level}>")
            continue
        if re.match(r"^[-*]\s+", s):
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{html_escape(re.sub(r'^[-*]\\s+', '', s))}</li>")
            continue
        if in_ul:
            parts.append("</ul>")
            in_ul = False
        parts.append(f"<p>{html_escape(s)}</p>")
    if in_ul:
        parts.append("</ul>")
    return "\n".join(parts)


def _xiaotu_compact_report_body_for_storage(html_text, max_chars=300000):
    text = str(html_text or "")
    if not text:
        return text

    def _replace_data_img(match):
        tag = str(match.group(0) or "")
        if re.search(r'\bsrc\s*=\s*["\']data:image/', tag, flags=re.IGNORECASE):
            return '<p>[图片已作为附件保存，正文中省略内嵌图片数据]</p>'
        if re.search(r'\bsrc\s*=\s*["\']blob:', tag, flags=re.IGNORECASE):
            return '<p>[图片已作为附件保存，正文中省略临时图片数据]</p>'
        return tag

    text = re.sub(r"<img\b[^>]*>", _replace_data_img, text, flags=re.IGNORECASE)
    text = re.sub(
        r"data:image/[^;\"'\s>]+;base64,[A-Za-z0-9+/=\r\n]+",
        "[图片数据已省略]",
        text,
        flags=re.IGNORECASE
    )
    if len(text) > max_chars:
        text = text[:max_chars] + "\n<p>[正文过长，后续内容已自动截断，原图片请查看附件]</p>"
    return text
