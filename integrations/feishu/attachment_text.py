"""Extract text from document attachments in Feishu chat."""

import io
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile


def extract_attachment_text(file_bytes, filename):
    b = file_bytes or b""
    name = (filename or "").strip()
    ext = ""
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower().strip()

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
