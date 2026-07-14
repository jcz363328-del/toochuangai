import os
import json
import re
import uuid
import zipfile
import io
import xml.etree.ElementTree as ET
from threading import Lock
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, send_from_directory, session
from department_permissions import require_permission


class KnowledgeBaseService:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.index_path = os.path.join(self.base_dir, "index.json")
        self.files_dir = os.path.join(self.base_dir, "files")
        self._lock = Lock()
        self._ocr_image_func = None
        self._cache = {
            "index_mtime": None,
            "file_mtimes": {},
            "docs": [],
            "loaded_at": None,
        }

    def set_ocr_image_func(self, func):
        self._ocr_image_func = func

    def _guess_image_mime(self, filename):
        name = (filename or "").strip().lower()
        if name.endswith(".png"):
            return "image/png"
        if name.endswith(".jpg") or name.endswith(".jpeg"):
            return "image/jpeg"
        if name.endswith(".webp"):
            return "image/webp"
        if name.endswith(".gif"):
            return "image/gif"
        if name.endswith(".bmp"):
            return "image/bmp"
        if name.endswith(".tif") or name.endswith(".tiff"):
            return "image/tiff"
        return "image/png"

    def ensure_dirs(self):
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.files_dir, exist_ok=True)
        if not os.path.exists(self.index_path):
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def _safe_read_text(self, file_path, max_chars=200000):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return (f.read(max_chars) or "").strip()
        except Exception:
            try:
                with open(file_path, "r", encoding="gbk", errors="ignore") as f:
                    return (f.read(max_chars) or "").strip()
            except Exception:
                return ""

    def extract_text_from_bytes(self, file_bytes, filename):
        b = file_bytes or b""
        name = (filename or "").strip()
        ext = ""
        if "." in name:
            ext = name.rsplit(".", 1)[-1].lower().strip()

        if ext in {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"}:
            if callable(self._ocr_image_func) and b:
                try:
                    return (self._ocr_image_func([{"bytes": b, "mime": self._guess_image_mime(name)}]) or "").strip()
                except Exception:
                    return ""
            return ""

        if ext in {"txt", "md", "csv", "log"}:
            try:
                return b.decode("utf-8", errors="ignore").strip()
            except Exception:
                try:
                    return b.decode("gbk", errors="ignore").strip()
                except Exception:
                    return ""

        if ext == "json":
            try:
                raw = b.decode("utf-8", errors="ignore").strip()
            except Exception:
                raw = ""
            if not raw:
                return ""
            try:
                obj = json.loads(raw)
                return json.dumps(obj, ensure_ascii=False, indent=2)[:200000].strip()
            except Exception:
                return raw[:200000].strip()

        if ext == "docx":
            try:
                with zipfile.ZipFile(io.BytesIO(b), "r") as z:
                    xml_bytes = z.read("word/document.xml")
                root = ET.fromstring(xml_bytes)
                parts = []
                for el in root.iter():
                    if el.tag.endswith("}t") and el.text:
                        parts.append(el.text)
                        if sum(len(p) for p in parts) >= 300000:
                            break
                return "\n".join([p.strip() for p in parts if str(p).strip()])[:300000].strip()
            except Exception:
                return ""

        if ext == "xlsx":
            try:
                with zipfile.ZipFile(io.BytesIO(b), "r") as z:
                    shared_strings = []
                    try:
                        ss_xml = z.read("xl/sharedStrings.xml")
                        ss_root = ET.fromstring(ss_xml)
                        for si in ss_root.iter():
                            if si.tag.endswith("}t") and si.text is not None:
                                shared_strings.append(si.text)
                    except Exception:
                        shared_strings = []

                    sheet_names = []
                    try:
                        wb_xml = z.read("xl/workbook.xml")
                        wb_root = ET.fromstring(wb_xml)
                        for sheet in wb_root.iter():
                            if sheet.tag.endswith("}sheet"):
                                sn = sheet.attrib.get("name")
                                if sn:
                                    sheet_names.append(sn)
                    except Exception:
                        sheet_names = []

                    sheet_files = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
                    sheet_files.sort()

                    out_lines = []
                    total_rows = 0
                    for idx, sheet_file in enumerate(sheet_files):
                        title = sheet_names[idx] if idx < len(sheet_names) else os.path.basename(sheet_file)
                        out_lines.append(f"[{title}]")
                        xml_bytes = z.read(sheet_file)
                        root = ET.fromstring(xml_bytes)
                        for row in root.iter():
                            if not row.tag.endswith("}row"):
                                continue
                            total_rows += 1
                            if total_rows > 3000:
                                break
                            row_values = []
                            for c in row:
                                if not isinstance(c.tag, str) or (not c.tag.endswith("}c")):
                                    continue
                                t = c.attrib.get("t")
                                v = None
                                for child in c:
                                    if isinstance(child.tag, str) and child.tag.endswith("}v"):
                                        v = child.text
                                        break
                                if v is None:
                                    row_values.append("")
                                    continue
                                if t == "s":
                                    try:
                                        s_idx = int(v)
                                        row_values.append(shared_strings[s_idx] if 0 <= s_idx < len(shared_strings) else "")
                                    except Exception:
                                        row_values.append("")
                                else:
                                    row_values.append(str(v))
                            line = "\t".join([str(x).strip() for x in row_values]).strip()
                            if line:
                                out_lines.append(line)
                            if sum(len(x) for x in out_lines) >= 500000:
                                break
                        if total_rows > 3000 or sum(len(x) for x in out_lines) >= 500000:
                            break
                    return "\n".join(out_lines)[:500000].strip()
            except Exception:
                return ""

        if ext == "pdf":
            try:
                import fitz  # type: ignore
                doc = fitz.open(stream=b, filetype="pdf")
                parts = []
                for i in range(min(doc.page_count, 20)):
                    parts.append(doc.load_page(i).get_text("text"))
                    if sum(len(p) for p in parts) >= 300000:
                        break
                return "\n".join([p.strip() for p in parts if str(p).strip()])[:300000].strip()
            except Exception:
                try:
                    txt = b.decode("latin-1", errors="ignore")
                except Exception:
                    return ""
                candidates = re.findall(r"\((.{1,200})\)", txt)
                cleaned = []
                for c in candidates:
                    c2 = re.sub(r"\\[nrtbf\\()]", " ", c)
                    c2 = re.sub(r"[^\x20-\x7E\u4e00-\u9fff]", " ", c2)
                    c2 = re.sub(r"\s+", " ", c2).strip()
                    if len(c2) >= 6:
                        cleaned.append(c2)
                    if sum(len(x) for x in cleaned) >= 120000:
                        break
                return "\n".join(cleaned)[:120000].strip()

        return ""

    def _extract_docx_text(self, file_path, max_chars=300000):
        try:
            with zipfile.ZipFile(file_path, "r") as z:
                xml_bytes = z.read("word/document.xml")
            root = ET.fromstring(xml_bytes)
            parts = []
            for el in root.iter():
                if el.tag.endswith("}t") and el.text:
                    parts.append(el.text)
                    if sum(len(p) for p in parts) >= max_chars:
                        break
            return "\n".join([p.strip() for p in parts if str(p).strip()])[:max_chars].strip()
        except Exception:
            return ""

    def _extract_xlsx_text(self, file_path, max_chars=500000, max_rows=3000):
        try:
            with zipfile.ZipFile(file_path, "r") as z:
                shared_strings = []
                try:
                    ss_xml = z.read("xl/sharedStrings.xml")
                    ss_root = ET.fromstring(ss_xml)
                    for si in ss_root.iter():
                        if si.tag.endswith("}t") and si.text is not None:
                            shared_strings.append(si.text)
                except Exception:
                    shared_strings = []

                sheet_names = []
                try:
                    wb_xml = z.read("xl/workbook.xml")
                    wb_root = ET.fromstring(wb_xml)
                    for sheet in wb_root.iter():
                        if sheet.tag.endswith("}sheet"):
                            name = sheet.attrib.get("name")
                            if name:
                                sheet_names.append(name)
                except Exception:
                    sheet_names = []

                sheet_files = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
                sheet_files.sort()

                out_lines = []
                total_rows = 0
                for idx, sheet_file in enumerate(sheet_files):
                    title = sheet_names[idx] if idx < len(sheet_names) else os.path.basename(sheet_file)
                    out_lines.append(f"[{title}]")
                    xml_bytes = z.read(sheet_file)
                    root = ET.fromstring(xml_bytes)
                    for row in root.iter():
                        if not row.tag.endswith("}row"):
                            continue
                        total_rows += 1
                        if total_rows > max_rows:
                            break
                        row_values = []
                        for c in row:
                            if not isinstance(c.tag, str) or (not c.tag.endswith("}c")):
                                continue
                            t = c.attrib.get("t")
                            v = None
                            for child in c:
                                if isinstance(child.tag, str) and child.tag.endswith("}v"):
                                    v = child.text
                                    break
                            if v is None:
                                row_values.append("")
                                continue
                            if t == "s":
                                try:
                                    s_idx = int(v)
                                    row_values.append(shared_strings[s_idx] if 0 <= s_idx < len(shared_strings) else "")
                                except Exception:
                                    row_values.append("")
                            else:
                                row_values.append(str(v))
                        line = "\t".join([str(x).strip() for x in row_values]).strip()
                        if line:
                            out_lines.append(line)
                        if sum(len(x) for x in out_lines) >= max_chars:
                            break
                    if total_rows > max_rows or sum(len(x) for x in out_lines) >= max_chars:
                        break
                return "\n".join(out_lines)[:max_chars].strip()
        except Exception:
            return ""

    def _extract_text_by_entry(self, entry):
        if not isinstance(entry, dict):
            return ""
        name = str(entry.get("name") or "").strip()
        stored_name = str(entry.get("stored_name") or "").strip()
        if not stored_name:
            return ""
        file_path = os.path.join(self.files_dir, stored_name)
        if not os.path.exists(file_path):
            return ""
        ext = ""
        if "." in name:
            ext = name.rsplit(".", 1)[-1].lower().strip()
        if ext in {"txt", "md", "csv", "log"}:
            return self._safe_read_text(file_path)
        if ext in {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"}:
            if not callable(self._ocr_image_func):
                return ""
            try:
                with open(file_path, "rb") as f:
                    blob = f.read()
            except Exception:
                blob = b""
            if not blob:
                return ""
            try:
                return (self._ocr_image_func([{"bytes": blob, "mime": self._guess_image_mime(name)}]) or "").strip()
            except Exception:
                return ""
        if ext in {"json"}:
            raw = self._safe_read_text(file_path)
            if not raw:
                return ""
            try:
                obj = json.loads(raw)
                return json.dumps(obj, ensure_ascii=False, indent=2)[:200000].strip()
            except Exception:
                return raw[:200000].strip()
        if ext in {"docx"}:
            return self._extract_docx_text(file_path)
        if ext in {"xlsx"}:
            return self._extract_xlsx_text(file_path)
        return ""

    def _tokenize(self, text, max_tokens=5000):
        s = (text or "").strip()
        if not s:
            return set()
        tokens = set()
        lower = s.lower()
        for w in re.findall(r"[a-z0-9_]{2,}", lower):
            tokens.add(w)
            if len(tokens) >= max_tokens:
                return tokens
        for seq in re.findall(r"[\u4e00-\u9fff]{2,}", s):
            seq = seq.strip()
            if not seq:
                continue
            if len(seq) <= 6:
                tokens.add(seq)
            for i in range(len(seq) - 1):
                tokens.add(seq[i:i + 2])
                if len(tokens) >= max_tokens:
                    return tokens
        return tokens

    def _make_chunks(self, text, max_chunk_chars=700):
        t = (text or "").strip()
        if not t:
            return []
        lines = [ln.strip() for ln in t.splitlines()]
        lines = [ln for ln in lines if ln]
        chunks = []
        buf = ""
        for ln in lines:
            if not buf:
                buf = ln
            elif (len(buf) + 1 + len(ln)) <= max_chunk_chars:
                buf = buf + "\n" + ln
            else:
                chunks.append(buf)
                buf = ln
            if len(chunks) >= 200:
                break
        if buf and len(chunks) < 200:
            chunks.append(buf)
        return chunks

    def _read_index(self):
        self.ensure_dirs()
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def list_entries(self):
        with self._lock:
            return self._read_index()

    def upload_file(self, file_storage, uploader=""):
        if not file_storage or not getattr(file_storage, "filename", ""):
            return None, "缺少文件"
        self.ensure_dirs()

        original = secure_filename(file_storage.filename)
        if not original:
            return None, "文件名无效"

        file_storage.stream.seek(0, os.SEEK_END)
        size = int(file_storage.stream.tell() or 0)
        file_storage.stream.seek(0)
        if size <= 0:
            return None, "文件为空"
        if size > 50 * 1024 * 1024:
            return None, "文件过大，最大50MB"

        stored_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex}"
        full_path = os.path.join(self.files_dir, stored_name)
        try:
            file_storage.save(full_path)
        except Exception as e:
            return None, f"保存失败: {e}"

        entry = {
            "id": uuid.uuid4().hex,
            "name": original,
            "stored_name": stored_name,
            "size": size,
            "mime": getattr(file_storage, "mimetype", "") or "application/octet-stream",
            "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "uploader": uploader or "",
        }

        with self._lock:
            index_data = self._read_index()
            index_data.append(entry)
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)

        self.refresh_cache(force=True)
        return entry, ""

    def delete_entry(self, entry_id):
        entry_id = str(entry_id or "").strip()
        if not entry_id:
            return False, "缺少id"
        with self._lock:
            index_data = self._read_index()
            kept = []
            removed = None
            for e in index_data:
                if isinstance(e, dict) and str(e.get("id") or "") == entry_id:
                    removed = e
                else:
                    kept.append(e)
            if removed is None:
                return False, "未找到记录"
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(kept, f, ensure_ascii=False, indent=2)

        stored_name = str((removed or {}).get("stored_name") or "").strip()
        if stored_name:
            try:
                os.remove(os.path.join(self.files_dir, stored_name))
            except Exception:
                pass

        self.refresh_cache(force=True)
        return True, ""

    def refresh_cache(self, force=False):
        self.ensure_dirs()
        try:
            index_mtime = os.path.getmtime(self.index_path) if os.path.exists(self.index_path) else None
        except Exception:
            index_mtime = None

        with self._lock:
            if not force and self._cache.get("index_mtime") == index_mtime:
                last_file_mtimes = self._cache.get("file_mtimes") or {}
                changed = False
                for stored_name, last_mtime in last_file_mtimes.items():
                    file_path = os.path.join(self.files_dir, stored_name)
                    try:
                        now_mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else None
                    except Exception:
                        now_mtime = None
                    if now_mtime != last_mtime:
                        changed = True
                        break
                if not changed:
                    return

            index_data = self._read_index()
            docs = []
            file_mtimes = {}
            for entry in index_data:
                if not isinstance(entry, dict):
                    continue
                stored_name = str(entry.get("stored_name") or "").strip()
                if not stored_name:
                    continue
                file_path = os.path.join(self.files_dir, stored_name)
                try:
                    file_mtimes[stored_name] = os.path.getmtime(file_path) if os.path.exists(file_path) else None
                except Exception:
                    file_mtimes[stored_name] = None

                text = self._extract_text_by_entry(entry)
                title = str(entry.get("name") or stored_name).strip()
                chunks = self._make_chunks(text)
                tokens = self._tokenize(title + "\n" + text)
                docs.append({
                    "id": entry.get("id"),
                    "name": title,
                    "stored_name": stored_name,
                    "text": text,
                    "chunks": chunks,
                    "tokens": tokens,
                })

            self._cache["index_mtime"] = index_mtime
            self._cache["file_mtimes"] = file_mtimes
            self._cache["docs"] = docs
            self._cache["loaded_at"] = datetime.now().isoformat(timespec="seconds")

    def search(self, question, top_snippets=5):
        q = (question or "").strip()
        if not q:
            return []
        try:
            self.refresh_cache(force=False)
        except Exception:
            pass

        q_tokens = self._tokenize(q, max_tokens=1200)
        if not q_tokens:
            return []

        with self._lock:
            docs = list(self._cache.get("docs") or [])
        if not docs:
            return []

        ranked_docs = []
        for doc in docs:
            doc_tokens = doc.get("tokens") or set()
            overlap = len(q_tokens & doc_tokens) if doc_tokens else 0
            if overlap <= 0:
                continue
            score = (overlap / (len(q_tokens) + 6.0)) + (overlap / (len(doc_tokens) + 80.0))
            ranked_docs.append((score, doc))
        ranked_docs.sort(key=lambda x: x[0], reverse=True)
        ranked_docs = ranked_docs[:3]

        snippets = []
        for doc_score, doc in ranked_docs:
            name = doc.get("name") or "未知文档"
            for chunk in (doc.get("chunks") or [])[:200]:
                ct = self._tokenize(chunk, max_tokens=1500)
                overlap = len(q_tokens & ct) if ct else 0
                if overlap <= 0:
                    continue
                score = (overlap / (len(q_tokens) + 6.0)) + (overlap / (len(ct) + 80.0)) + (0.15 * doc_score)
                snippets.append({"doc": name, "text": chunk, "score": score, "overlap": overlap})
        snippets.sort(key=lambda x: x["score"], reverse=True)
        return snippets[:top_snippets]


knowledge_base_bp = Blueprint("knowledge_base", __name__)
kb_service = KnowledgeBaseService(base_dir=os.path.join(os.path.dirname(__file__), "knowledge_base"))

def _h(s):
    s = "" if s is None else str(s)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&#x27;"))


@knowledge_base_bp.route("/knowledge_base", methods=["GET", "POST"])
@require_permission("admin_functions")
def knowledge_base_page():
    uploader = (session.get("feishu_user_name") or "").strip()
    msg = ""
    if request.method == "POST":
        f = request.files.get("file")
        entry, err = kb_service.upload_file(f, uploader=uploader)
        if entry:
            msg = "上传成功"
        else:
            msg = err or "上传失败"

    rows = kb_service.list_entries()
    items_html = []
    for e in reversed(rows or []):
        if not isinstance(e, dict):
            continue
        eid = _h(e.get("id"))
        name = _h(e.get("name"))
        stored_name = _h(e.get("stored_name"))
        size = _h(e.get("size"))
        upload_time = _h(e.get("upload_time"))
        up = _h(e.get("uploader"))
        file_url = f"/api/knowledge_base/file/{stored_name}"
        items_html.append(
            "<tr>"
            f"<td style='padding:6px 8px;'>{name}</td>"
            f"<td style='padding:6px 8px;'>{size}</td>"
            f"<td style='padding:6px 8px;'>{upload_time}</td>"
            f"<td style='padding:6px 8px;'>{up}</td>"
            f"<td style='padding:6px 8px;'><a href='{file_url}'>下载</a></td>"
            f"<td style='padding:6px 8px;'><button type='button' onclick=\"kbDel('{eid}')\">删除</button></td>"
            "</tr>"
        )

    table = (
        "<table border='1' cellspacing='0' cellpadding='0' style='border-collapse:collapse; width:100%;'>"
        "<thead><tr>"
        "<th style='padding:6px 8px;'>文件</th>"
        "<th style='padding:6px 8px;'>大小</th>"
        "<th style='padding:6px 8px;'>上传时间</th>"
        "<th style='padding:6px 8px;'>上传人</th>"
        "<th style='padding:6px 8px;'>下载</th>"
        "<th style='padding:6px 8px;'>删除</th>"
        "</tr></thead>"
        f"<tbody>{''.join(items_html) if items_html else ''}</tbody>"
        "</table>"
    )

    html = f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>知识库管理</title>
</head>
<body style="font-family: Arial, sans-serif; padding: 18px;">
  <h2 style="margin: 0 0 12px 0;">知识库管理</h2>
  <div style="margin: 0 0 12px 0; color: #555;">当前用户：{_h(uploader) or '未知'}</div>
  <form method="post" enctype="multipart/form-data" style="margin: 0 0 16px 0;">
    <input type="file" name="file" required />
    <button type="submit">上传</button>
    <span style="margin-left: 10px; color: #d00;">{_h(msg)}</span>
  </form>
  <div style="margin: 0 0 10px 0;">
    <a href="/api/knowledge_base/list" target="_blank">查看JSON列表</a>
  </div>
  {table}
  <script>
    async function kbDel(id) {{
      if (!confirm('确认删除？')) return;
      const resp = await fetch('/api/knowledge_base/delete/' + encodeURIComponent(id), {{ method: 'DELETE' }});
      const data = await resp.json().catch(() => null);
      if (!resp.ok || !data || data.success !== true) {{
        alert((data && data.message) ? data.message : '删除失败');
        return;
      }}
      location.reload();
    }}
  </script>
</body>
</html>
""".strip()
    return html


@knowledge_base_bp.route("/api/knowledge_base/upload", methods=["POST"])
@require_permission("admin_functions")
def api_knowledge_base_upload():
    uploader = (session.get("feishu_user_name") or "").strip()
    f = request.files.get("file")
    entry, err = kb_service.upload_file(f, uploader=uploader)
    if not entry:
        return jsonify({"success": False, "message": err or "上传失败"}), 400
    return jsonify({"success": True, "data": entry})


@knowledge_base_bp.route("/api/knowledge_base/list", methods=["GET"])
@require_permission("admin_functions")
def api_knowledge_base_list():
    data = kb_service.list_entries()
    return jsonify({"success": True, "data": data})


@knowledge_base_bp.route("/api/knowledge_base/delete/<entry_id>", methods=["DELETE"])
@require_permission("admin_functions")
def api_knowledge_base_delete(entry_id):
    ok, err = kb_service.delete_entry(entry_id)
    if not ok:
        return jsonify({"success": False, "message": err or "删除失败"}), 400
    return jsonify({"success": True})


@knowledge_base_bp.route("/api/knowledge_base/file/<stored_name>", methods=["GET"])
@require_permission("admin_functions")
def api_knowledge_base_get_file(stored_name):
    stored_name = str(stored_name or "").strip()
    if not stored_name or ".." in stored_name or "/" in stored_name or "\\" in stored_name:
        return jsonify({"success": False, "message": "文件名无效"}), 400
    if not os.path.exists(os.path.join(kb_service.files_dir, stored_name)):
        return jsonify({"success": False, "message": "文件不存在"}), 404
    return send_from_directory(kb_service.files_dir, stored_name, as_attachment=True)
