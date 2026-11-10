"""Prepress inspection workflow used by the Feishu XiaoHa bot."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
import zlib
from pathlib import Path
from threading import Lock


SOURCE_EXTENSIONS = {".ai", ".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PACKAGE_EXTENSIONS = {".zip"}
ALLOWED_EXTENSIONS = SOURCE_EXTENSIONS | IMAGE_EXTENSIONS | PACKAGE_EXTENSIONS
TRIGGER_WORDS = ("检查印前合规", "印前检查", "核对设计稿", "检查设计稿", "能否交付印刷")
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_ZIP_BYTES = 500 * 1024 * 1024
SESSION_TTL_SECONDS = 2 * 60 * 60
PT_TO_MM = 25.4 / 72.0

STANDARDS = {
    "bleed_mm": 2.0,
    "min_dpi": 300,
    "text_to_trim_mm": "1–2mm",
    "hot_stamp_min_mm": 0.3,
    "window_edge_mm": 6.0,
    "window_paste_mm": 15.0,
    "code_label_mm": "50×30mm",
    "date_label_mm": "25×15mm",
    "bottom_card_margin_mm": 2.0,
    "info_tag_margin_mm": 2.0,
}

_sessions: dict[str, dict] = {}
_sessions_lock = Lock()


def is_trigger(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    return any(word.lower() in normalized for word in TRIGGER_WORDS)


def accepts_filename(filename: str) -> bool:
    return Path(str(filename or "")).suffix.lower() in ALLOWED_EXTENSIONS


def has_active_session(chat_id: str) -> bool:
    with _sessions_lock:
        _prune_locked()
        return bool(_sessions.get(str(chat_id or "")))


def activate_session(chat_id: str) -> None:
    """Mark a chat as collecting files before asynchronous downloads finish."""
    key = str(chat_id or "").strip()
    if not key:
        return
    with _sessions_lock:
        _prune_locked()
        if key not in _sessions:
            _sessions[key] = {
                "root": tempfile.mkdtemp(prefix="xiaoha_prepress_"),
                "files": [],
                "updated_at": time.time(),
            }


def _prune_locked() -> None:
    cutoff = time.time() - SESSION_TTL_SECONDS
    expired = [key for key, value in _sessions.items() if value.get("updated_at", 0) < cutoff]
    for key in expired:
        session = _sessions.pop(key, None) or {}
        shutil.rmtree(session.get("root", ""), ignore_errors=True)


def _safe_filename(filename: str, fallback: str) -> str:
    name = os.path.basename(str(filename or "")).strip() or fallback
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name[:180]


def stage_file(chat_id: str, blob: bytes, filename: str) -> dict:
    if not blob:
        raise ValueError("文件内容为空")
    if len(blob) > MAX_FILE_BYTES:
        raise ValueError("单个文件不能超过 200MB")
    ext = Path(str(filename or "")).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("仅支持 AI、PDF、ZIP 和常见图片格式")
    key = str(chat_id or "").strip()
    if not key:
        raise ValueError("缺少会话标识")
    with _sessions_lock:
        _prune_locked()
        session = _sessions.get(key)
        if not session:
            root = tempfile.mkdtemp(prefix="xiaoha_prepress_")
            session = {"root": root, "files": [], "updated_at": time.time()}
            _sessions[key] = session
        safe_name = _safe_filename(filename, f"upload{ext}")
        target = os.path.join(session["root"], f"{uuid.uuid4().hex[:8]}_{safe_name}")
        with open(target, "wb") as handle:
            handle.write(blob)
        entry = {"path": target, "name": safe_name, "size": len(blob), "extension": ext}
        session["files"].append(entry)
        session["updated_at"] = time.time()
        return {"count": len(session["files"]), "name": safe_name, "extension": ext}


def pending_files(chat_id: str) -> list[dict]:
    with _sessions_lock:
        _prune_locked()
        session = _sessions.get(str(chat_id or "")) or {}
        return [dict(item) for item in session.get("files", [])]


def _safe_extract_zip(zip_path: str, destination: str) -> list[str]:
    extracted = []
    total = 0
    dest_real = os.path.realpath(destination)
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            total += int(info.file_size or 0)
            if total > MAX_ZIP_BYTES:
                raise ValueError("ZIP 解压后不能超过 500MB")
            suffix = Path(info.filename).suffix.lower()
            if suffix not in SOURCE_EXTENSIONS | IMAGE_EXTENSIONS:
                continue
            target = os.path.realpath(os.path.join(destination, info.filename))
            if os.path.commonpath([dest_real, target]) != dest_real:
                raise ValueError("ZIP 中包含不安全路径")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(target)
    return extracted


def _filename_check(path: str) -> tuple[bool, str]:
    name = Path(path).stem
    sku = bool(re.search(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", name))
    size = bool(re.search(r"\d+(?:\.\d+)?\s*[xX×*]\s*\d+(?:\.\d+)?\s*(?:mm|cm|厘米)?", name))
    process = any(word in name for word in ("烫银", "烫金", "UV", "覆膜", "哑膜", "亮膜", "击凸", "压纹", "模切", "丝印"))
    missing = [label for ok, label in ((sku, "SKU"), (size, "尺寸"), (process, "工艺")) if not ok]
    return not missing, "字段齐全" if not missing else "缺少" + "、".join(missing)


def _bleed_result(page) -> tuple[str, str]:
    media, trim, bleed = page.mediabox, page.trimbox, page.bleedbox
    same = all(abs(a - b) < 0.05 for a, b in zip(media, trim))
    if same:
        return "⚠️ 需人工确认", "未定义独立 TrimBox，无法自动计算出血"
    values = [
        abs((bleed.x0 - trim.x0) * PT_TO_MM),
        abs((trim.x1 - bleed.x1) * PT_TO_MM),
        abs((trim.y1 - bleed.y1) * PT_TO_MM),
        abs((bleed.y0 - trim.y0) * PT_TO_MM),
    ]
    minimum = min(values)
    if minimum + 0.02 >= STANDARDS["bleed_mm"]:
        return "✅ 通过", f"最小出血 {minimum:.2f}mm"
    return "❌ 不通过", f"最小出血 {minimum:.2f}mm，标准为 2mm"


AI_ZSTD_HEADER = b"%AI24_ZStandard_Data"
AI_ZLIB_HEADER = b"%AI12_CompressedData"
AI_NATIVE_CHUNK_BYTES = 8 * 1024 * 1024
AI_NATIVE_MAX_LINE_BYTES = 64 * 1024


def _ai_private_data(doc) -> bytes | None:
    """Concatenate Illustrator's native AIPrivateData streams from a PDF-compatible AI file."""
    if doc.page_count < 1:
        return None
    private = doc.xref_get_key(doc.page_xref(0), "PieceInfo/Illustrator/Private")
    if private[0] == "xref":
        private_source = doc.xref_object(int(private[1].split()[0]))
    elif private[0] == "dict":
        private_source = private[1]
    else:
        return None
    parts = sorted(
        (int(index), int(xref))
        for index, xref in re.findall(r"/AIPrivateData(\d+)\s+(\d+)\s+0\s+R", private_source)
    )
    if not parts:
        return None
    return b"".join(doc.xref_stream(xref) or b"" for _index, xref in parts)


def _iter_ai_native_chunks(blob: bytes):
    if blob.startswith(AI_ZSTD_HEADER):
        from compression import zstd

        data = blob[len(AI_ZSTD_HEADER):]
        while data:
            decompressor = zstd.ZstdDecompressor()
            chunk = decompressor.decompress(data, max_length=AI_NATIVE_CHUNK_BYTES)
            while True:
                if chunk:
                    yield chunk
                if decompressor.eof or decompressor.needs_input:
                    break
                chunk = decompressor.decompress(b"", max_length=AI_NATIVE_CHUNK_BYTES)
            if not decompressor.eof:
                raise ValueError("AI 原生数据不完整")
            data = decompressor.unused_data
    elif blob.startswith(AI_ZLIB_HEADER):
        decompressor = zlib.decompressobj()
        chunk = decompressor.decompress(blob[len(AI_ZLIB_HEADER):], AI_NATIVE_CHUNK_BYTES)
        while True:
            if chunk:
                yield chunk
            if not decompressor.unconsumed_tail:
                break
            chunk = decompressor.decompress(decompressor.unconsumed_tail, AI_NATIVE_CHUNK_BYTES)
        tail = decompressor.flush()
        if tail:
            yield tail
    else:
        yield blob


def _decode_ai_path(raw: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1").strip()


def _scan_ai_native_lines(chunks) -> dict:
    """Count placed (linked) files and embedded rasters in Illustrator's native art stream.

    Embedding an image in Illustrator turns it into raster art carrying its own pixel data
    (%AI5_BeginRaster), while a linked file stays a %AI5_BeginPlace block that only records
    the external path (%%IncludeFile) unless the block itself carries %%BeginData.
    """
    linked: list[str] = []
    embedded_placed = 0
    raster_count = 0
    in_place = False
    place_path = ""
    place_has_data = False
    leftover = b""
    for chunk in chunks:
        buffer = leftover + chunk
        lines = buffer.split(b"\n")
        leftover = lines.pop()
        if len(leftover) > AI_NATIVE_MAX_LINE_BYTES:
            leftover = leftover[-AI_NATIVE_MAX_LINE_BYTES:]
        for line in lines:
            if not line.startswith(b"%"):
                continue
            line = line.rstrip(b"\r")
            if line.startswith(b"%AI5_BeginPlace"):
                in_place, place_path, place_has_data = True, "", False
            elif in_place and line.startswith(b"%%IncludeFile:"):
                place_path = _decode_ai_path(line[len(b"%%IncludeFile:"):])
            elif in_place and line.startswith(b"%%BeginData"):
                place_has_data = True
            elif in_place and line.startswith(b"%AI5_EndPlace"):
                if place_has_data:
                    embedded_placed += 1
                else:
                    linked.append(place_path or "（未记录路径）")
                in_place = False
            elif line.startswith(b"%AI5_BeginRaster"):
                raster_count += 1
    return {"linked": linked, "embedded_placed": embedded_placed, "raster_count": raster_count}


def _scan_ai_links(doc) -> dict:
    try:
        blob = _ai_private_data(doc)
        if not blob:
            return {"readable": False, "reason": "文件中没有 Illustrator 原生数据（可能是由其他软件另存的 AI）"}
        result = _scan_ai_native_lines(_iter_ai_native_chunks(blob))
    except ImportError:
        return {"readable": False, "reason": "当前 Python 不支持 Zstandard 解压（需要 Python 3.14+）"}
    except Exception as exc:
        return {"readable": False, "reason": f"Illustrator 原生数据解析失败：{exc}"}
    result["readable"] = True
    return result


def _scan_source(path: str, render_dir: str, display_name: str | None = None) -> dict:
    try:
        import pymupdf as fitz
    except ImportError as exc:
        raise RuntimeError("缺少 PyMuPDF，请先安装 requirements.txt 依赖") from exc
    record = {"path": path, "name": display_name or os.path.basename(path), "pages": [], "errors": []}
    try:
        doc = fitz.open(path)
    except Exception as exc:
        record["errors"].append(f"无法打开：{exc}")
        return record
    record["metadata"] = dict(doc.metadata or {})
    for index, page in enumerate(doc):
        width_mm = page.rect.width * PT_TO_MM
        height_mm = page.rect.height * PT_TO_MM
        bleed_status, bleed_evidence = _bleed_result(page)
        fonts = page.get_fonts(full=True)
        images = []
        for image in page.get_images(full=True):
            xref, _smask, width, height, _bpc, colorspace = image[:6]
            dpi = None
            try:
                rects = page.get_image_rects(xref)
                if rects and rects[0].width > 0 and rects[0].height > 0:
                    dpi = min(width / (rects[0].width / 72), height / (rects[0].height / 72))
            except Exception:
                pass
            images.append({"colorspace": str(colorspace), "dpi": dpi})
        render_path = os.path.join(render_dir, f"{uuid.uuid4().hex[:8]}_p{index + 1}.png")
        page.get_pixmap(dpi=200, alpha=False).save(render_path)
        record["pages"].append({
            "number": index + 1,
            "size_mm": [round(width_mm, 2), round(height_mm, 2)],
            "bleed_status": bleed_status,
            "bleed_evidence": bleed_evidence,
            "font_count": len(fonts),
            "outlined": len(fonts) == 0,
            "images": images,
            "rgb_detected": any("RGB" in item["colorspace"].upper() for item in images),
            "low_dpi": [round(item["dpi"], 1) for item in images if item["dpi"] is not None and item["dpi"] < STANDARDS["min_dpi"]],
            "render_path": render_path,
        })
    if Path(path).suffix.lower() == ".ai":
        record["ai_links"] = _scan_ai_links(doc)
    doc.close()
    return record


def _status_for_all(values: list[bool], unknown_when_empty: bool = False) -> str:
    if not values and unknown_when_empty:
        return "⚠️ 需人工确认"
    return "✅ 通过" if all(values) else "❌ 不通过"


def _ai_embedding_result(scan: dict) -> tuple[str, str]:
    name = scan.get("name") or os.path.basename(scan.get("path", ""))
    links = scan.get("ai_links") or {}
    if not links.get("readable"):
        reason = links.get("reason") or "未能读取 Illustrator 原生数据"
        return "⚠️ 需人工确认", f"{name}：{reason}；请在 Illustrator“链接”面板中确认每个资源均已嵌入。"
    linked = links.get("linked") or []
    embedded_count = int(links.get("raster_count") or 0) + int(links.get("embedded_placed") or 0)
    if linked:
        counts: dict[str, int] = {}
        for linked_path in linked:
            counts[linked_path] = counts.get(linked_path, 0) + 1
        details = "；".join(
            f"{linked_path}" + (f" ×{count}" if count > 1 else "")
            for linked_path, count in counts.items()
        )
        return (
            "❌ 不通过",
            f"{name}：检测到 {len(linked)} 处外链置入（{len(counts)} 个文件）：{details}。"
            "请在 Illustrator“链接”面板中选中这些项目并“嵌入图像”后重新保存。",
        )
    return "✅ 通过", f"{name}：未发现外链置入文件，已嵌入图像 {embedded_count} 个。"


def _embedding_check(scans: list[dict]) -> tuple[str, str]:
    """Only report embedding facts the uploaded file can actually prove."""
    ai_scans = [scan for scan in scans if Path(scan.get("path", "")).suffix.lower() == ".ai" and not scan.get("errors")]
    if ai_scans:
        results = [_ai_embedding_result(scan) for scan in ai_scans]
        statuses = [status for status, _evidence in results]
        if any(status.startswith("❌") for status in statuses):
            status = "❌ 不通过"
        elif any(status.startswith("⚠") for status in statuses):
            status = "⚠️ 需人工确认"
        else:
            status = "✅ 通过"
        return status, "；".join(evidence for _status, evidence in results)

    pages = [page for scan in scans for page in scan.get("pages", [])]
    raster_count = sum(len(page.get("images", [])) for page in pages)
    if raster_count:
        return "✅ 通过", f"PDF 中检测到 {raster_count} 个自包含图像对象。"
    return "⚠️ 需人工确认", "未检测到可核验的栅格图像对象；纯矢量内容无需嵌入，其他置入资源请人工确认。"


def _build_report(scans: list[dict], images: list[str], visual_notes: list[str]) -> str:
    pages = [page for scan in scans for page in scan.get("pages", [])]
    openable = [not scan.get("errors") for scan in scans]
    filename_results = [_filename_check(scan["name"]) for scan in scans]
    bleed_fail = any(page["bleed_status"].startswith("❌") for page in pages)
    bleed_unknown = any(page["bleed_status"].startswith("⚠") for page in pages)
    bleed_status = "❌ 不通过" if bleed_fail else ("⚠️ 需人工确认" if bleed_unknown else "✅ 通过")
    outlined = _status_for_all([page["outlined"] for page in pages], unknown_when_empty=True)
    color = _status_for_all([not page["rgb_detected"] for page in pages], unknown_when_empty=True)
    dpi = _status_for_all([not page["low_dpi"] for page in pages], unknown_when_empty=True)
    filename_status = _status_for_all([item[0] for item in filename_results], unknown_when_empty=True)
    embedding_status, embedding_evidence = _embedding_check(scans)
    source_types = {Path(scan["path"]).suffix.lower() for scan in scans}
    three_files = "✅ 通过" if {".ai", ".pdf"}.issubset(source_types) and images else "❌ 不通过"
    visual = "\n".join(visual_notes).strip() or "未执行视觉模型复核；以下设计意图项均需人工确认。"
    automatic_fail = any(status.startswith("❌") for status in (bleed_status, outlined, color, dpi, embedding_status, filename_status, three_files)) or not all(openable)
    overall = "不通过" if automatic_fail else "有条件通过（仍有视觉项需确认）"
    rows = [
        ("1", "文件可解析", _status_for_all(openable), "；".join(err for scan in scans for err in scan.get("errors", [])) or "AI/PDF 可正常打开"),
        ("2", "色彩模式 CMYK", color, "检测嵌入图片色彩空间；矢量对象仍需人工确认"),
        ("3", "出血 2mm", bleed_status, "；".join(page["bleed_evidence"] for page in pages)),
        ("4", "图片分辨率 ≥300dpi", dpi, "低于标准：" + str([v for page in pages for v in page["low_dpi"]]) if any(page["low_dpi"] for page in pages) else "未发现低分辨率嵌入图"),
        ("5", "字体转曲", outlined, "字体对象数：" + str(sum(page["font_count"] for page in pages))),
        ("6", "图片嵌入", embedding_status, embedding_evidence),
        ("7", "文件名规范", filename_status, "；".join(f"{scan['name']}：{result[1]}" for scan, result in zip(scans, filename_results))),
        ("8", "AI + PDF + 截图一致", three_files, "已收集 AI、PDF、截图" if three_files.startswith("✅") else "必须同时提供 AI、PDF 和截图"),
        ("9", "AI 版本 CS5+", "⚠️ 需人工确认", "PDF 元数据只能提供提示，需 Illustrator 复核保存版本"),
        ("10", "叠加效果背景", "⚠️ 需人工确认", "查看高清渲染图"),
        ("11", "烫银最细 >0.3mm", "⚠️ 需人工确认", "查看工艺图层/高清渲染图"),
        ("12", "文字距裁切线 1–2mm", "⚠️ 需人工确认", "查看高清渲染图"),
        ("13", "包装盒开盖方向统一", "⚠️ 需人工确认", "TK 产品例外"),
        ("14", "封口贴/糊边接口在背面", "⚠️ 需人工确认", "查看刀模与成品方向"),
        ("15", "开窗距边/粘贴区", "⚠️ 需人工确认", "标准：距边 6mm、粘贴区 15mm"),
        ("16", "信息贴位预留", "⚠️ 需人工确认", "编码 50×30mm；日期 25×15mm"),
        ("17", "底卡规范", "⚠️ 需人工确认", "重要信息距边 2mm、正反 180°、圆角、四面翻盖"),
        ("18", "信息贴白边", "⚠️ 需人工确认", "边框外侧 2mm"),
        ("19", "页面尺寸与截图备注", "⚠️ 需人工确认", "页面尺寸：" + str([page["size_mm"] for page in pages])),
    ]
    lines = [
        "# 印前检查报告",
        "",
        f"**总体结论：{overall}**",
        "",
        f"检查文件：{', '.join(scan['name'] for scan in scans)}；截图 {len(images)} 张。",
        "",
        "| # | 检查项 | 结论 | 证据/说明 |",
        "|---|---|---|---|",
    ]
    lines.extend(f"| {number} | {name} | {status} | {str(evidence).replace('|', '／')} |" for number, name, status, evidence in rows)
    lines.extend(["", "## 视觉复核记录", "", visual, "", "## 修改建议", ""])
    failures = [name for _number, name, status, _evidence in rows if status.startswith("❌")]
    lines.append("请先修正：" + "、".join(failures) + "。修正后重新上传完整文件包复检。" if failures else "自动项未发现硬性失败；请由设计/印前人员确认所有标记为“需人工确认”的项目。")
    return "\n".join(lines)


def run_check(chat_id: str, vision_reviewer=None) -> dict:
    key = str(chat_id or "").strip()
    with _sessions_lock:
        _prune_locked()
        session = _sessions.pop(key, None)
    if not session:
        raise ValueError("还没有收到设计文件，请先发送 AI、PDF、截图或 ZIP")
    root = session["root"]
    try:
        expanded = []
        display_names: dict[str, str] = {}
        extract_dir = os.path.join(root, "extracted")
        for item in session["files"]:
            if item["extension"] == ".zip":
                os.makedirs(extract_dir, exist_ok=True)
                expanded.extend(_safe_extract_zip(item["path"], extract_dir))
            else:
                expanded.append(item["path"])
                display_names[item["path"]] = item["name"]
        sources = [path for path in expanded if Path(path).suffix.lower() in SOURCE_EXTENSIONS]
        images = [path for path in expanded if Path(path).suffix.lower() in IMAGE_EXTENSIONS]
        if not sources:
            raise ValueError("未找到 AI 或 PDF 文件")
        render_dir = os.path.join(root, "renders")
        os.makedirs(render_dir, exist_ok=True)
        scans = [_scan_source(path, render_dir, display_names.get(path)) for path in sources]
        renders = [page["render_path"] for scan in scans for page in scan.get("pages", [])]
        visual_notes = []
        if callable(vision_reviewer):
            for render in renders[:8]:
                try:
                    note = str(vision_reviewer(render) or "").strip()
                    if note:
                        visual_notes.append(f"- {os.path.basename(render)}：{note}")
                except Exception as exc:
                    visual_notes.append(f"- {os.path.basename(render)}：视觉复核失败（{exc}）")
        report = _build_report(scans, images, visual_notes)
        return {"report": report, "scan_count": len(scans), "image_count": len(images)}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def reset_session(chat_id: str) -> None:
    with _sessions_lock:
        session = _sessions.pop(str(chat_id or ""), None) or {}
    shutil.rmtree(session.get("root", ""), ignore_errors=True)
