"""Read and normalize report images and their OCR text."""

from __future__ import annotations


def _xiaotu_classify_image_debug(
    err_text,
    image_block_count,
    saved_count,
):
    t = str(err_text or "").strip()
    tl = t.lower()
    if int(saved_count or 0) > 0:
        return {"reason_code": "ok", "reason_text": "图片下载与落盘成功"}
    if ("可见" in t and "不可见" in t) or ("not visible" in tl) or ("invisible" in tl):
        return {"reason_code": "visibility_denied", "reason_text": t or "可见性不足：应用对文档或图片资源不可见"}
    if (
        ("权限" in t) or ("scope" in tl) or ("access denied" in tl) or ("forbidden" in tl) or
        ("401" in tl) or ("403" in tl) or ("permission" in tl)
    ):
        return {"reason_code": "permission_denied", "reason_text": t or "权限不足：应用缺少图片读取/下载权限"}
    if int(image_block_count or 0) <= 0:
        return {"reason_code": "no_image_block", "reason_text": t or "未识别到图片块：文档可能无图片或图片非可下载资源"}
    if t:
        return {"reason_code": "download_failed", "reason_text": t}
    return {"reason_code": "unknown", "reason_text": "未知原因：未获取到可落盘图片"}


def _xiaotu_save_doc_images_and_ocr(
    agent,
    doc_token,
    doc_url,
    specific_tokens,
    *,
    _ocr_images_bytes_with_ai,
    _xiaotu_classify_image_debug,
    os,
    relocate_storage_path,
):
    token = str(doc_token or "").strip()
    debug = {
        "reason_code": "unknown",
        "reason_text": "",
        "doc_token": token,
        "doc_type": "",
        "image_block_count": 0,
        "saved_image_count": 0,
        "block_total": 0,
        "image_like_block_total": 0,
        "token_candidate_total": 0
    }
    if agent is None:
        debug.update({"reason_code": "agent_missing", "reason_text": "云文档代理未初始化"})
        return [], "", debug
    doc_type = ""
    resolver = getattr(agent, "resolve_url_to_doc", None)
    if callable(resolver) and str(doc_url or "").strip():
        try:
            resolved_token, resolved_type, resolved_err = resolver(doc_url)
        except Exception:
            resolved_token, resolved_type, resolved_err = "", "", ""
        if resolved_err and not token:
            info = _xiaotu_classify_image_debug(resolved_err, 0, 0)
            debug.update(info)
            debug["doc_type"] = str(resolved_type or "").strip().lower()
            return [], f"图片读取失败：{resolved_err}", debug
        if resolved_token:
            token = str(resolved_token or "").strip()
            debug["doc_token"] = token
        doc_type = str(resolved_type or "").strip().lower()
        debug["doc_type"] = doc_type
    if not token:
        info = _xiaotu_classify_image_debug("未能解析到文档token", 0, 0)
        debug.update(info)
        return [], "图片读取失败：未能解析到文档token", debug
    if doc_type and doc_type not in {"docx", "docs", "doc", ""}:
        info = _xiaotu_classify_image_debug(f"当前文档类型 {doc_type} 暂不支持图片提取", 0, 0)
        debug.update(info)
        return [], f"图片读取失败：当前文档类型 {doc_type} 暂不支持图片提取", debug

    preferred_tokens = specific_tokens if isinstance(specific_tokens, list) else None
    if preferred_tokens is not None:
        tokens = []
        seen_tokens = set()
        for one in preferred_tokens:
            t = str(one or "").strip()
            if not t or t in seen_tokens:
                continue
            seen_tokens.add(t)
            tokens.append(t)
        err = ""
        debug["block_total"] = 0
        debug["image_like_block_total"] = len(tokens)
        debug["token_candidate_total"] = len(tokens)
        if len(tokens) <= 0:
            debug.update({
                "reason_code": "daily_slice_no_image",
                "reason_text": "日报切片后未匹配到日期后的图片"
            })
    else:
        fetch_debug = getattr(agent, "fetch_docx_image_tokens_debug", None)
        if callable(fetch_debug):
            tokens, err, token_stats = fetch_debug(token, max_tokens=80, max_pages=80)
            if isinstance(token_stats, dict):
                debug["block_total"] = int(token_stats.get("block_total") or 0)
                debug["image_like_block_total"] = int(token_stats.get("image_like_block_total") or 0)
                debug["token_candidate_total"] = int(token_stats.get("token_candidate_total") or 0)
        else:
            tokens, err = agent.fetch_docx_image_tokens(token, max_tokens=80, max_pages=80)
    debug["image_block_count"] = len(tokens or [])
    if err and not tokens:
        info = _xiaotu_classify_image_debug(err, len(tokens or []), 0)
        debug.update(info)
        return [], f"图片读取失败：{err}", debug
    if not tokens:
        msg = "未识别到可下载图片（更可能是无图片块）"
        if preferred_tokens is not None:
            msg = "日报切片后未匹配到日期后的图片"
        info = _xiaotu_classify_image_debug(msg, 0, 0)
        debug.update(info)
        return [], msg, debug
    root_dir = os.path.join(relocate_storage_path(r"D:\tuchuangai\报告图片"), token)
    os.makedirs(root_dir, exist_ok=True)
    image_paths = []
    ocr_inputs = []
    download_errs = []
    for idx, file_token in enumerate(tokens, start=1):
        blob, mime, dl_err = agent.download_media_bytes(file_token)
        if not blob:
            if dl_err:
                download_errs.append(str(dl_err))
            continue
        mm = str(mime or "").lower()
        ext = ".jpg"
        if "png" in mm:
            ext = ".png"
        elif "webp" in mm:
            ext = ".webp"
        elif "gif" in mm:
            ext = ".gif"
        file_path = os.path.join(root_dir, f"{idx}{ext}")
        with open(file_path, "wb") as f:
            f.write(blob)
        image_paths.append(file_path)
        ocr_inputs.append((blob, mime))
    debug["saved_image_count"] = len(image_paths)
    image_ocr_text = ""
    if ocr_inputs:
        try:
            image_ocr_text = _ocr_images_bytes_with_ai(ocr_inputs) or ""
        except Exception:
            image_ocr_text = ""
    err_for_debug = ""
    if download_errs:
        err_for_debug = "；".join(download_errs[:3])
    elif err:
        err_for_debug = str(err)
    info = _xiaotu_classify_image_debug(err_for_debug, len(tokens or []), len(image_paths))
    debug.update(info)
    if err and not image_ocr_text:
        image_ocr_text = f"图片OCR提示：{err}"
    if (not image_paths) and (not image_ocr_text) and debug.get("reason_text"):
        image_ocr_text = f"图片调试：{debug.get('reason_text')}"
    return image_paths, image_ocr_text, debug


def _xiaotu_save_uploaded_images_and_ocr(
    files,
    report_token,
    root_base_dir,
    *,
    _ocr_images_bytes_with_ai,
    datetime,
    os,
    relocate_storage_path,
    secure_filename,
):
    items = files if isinstance(files, list) else []
    if not items:
        return [], "", {"reason_code": "no_upload", "reason_text": "未上传图片", "saved_image_count": 0}
    token = str(report_token or datetime.now().strftime("%Y%m%d%H%M%S")).strip() or datetime.now().strftime("%Y%m%d%H%M%S")
    base_dir = os.path.abspath(str(root_base_dir or relocate_storage_path(r"D:\tuchuangai\报告图片")))
    root_dir = os.path.join(base_dir, f"upload_{token}")
    os.makedirs(root_dir, exist_ok=True)

    image_paths = []
    ocr_inputs = []
    idx = 0
    for one in items:
        if one is None:
            continue
        raw = one.read()
        if not raw:
            continue
        idx += 1
        filename = secure_filename(str(getattr(one, "filename", "") or f"img_{idx}.jpg"))
        ext = os.path.splitext(filename)[1].lower()
        if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
            ext = ".jpg"
        save_name = f"{idx}{ext}"
        save_path = os.path.join(root_dir, save_name)
        with open(save_path, "wb") as f:
            f.write(raw)
        image_paths.append(save_path)
        mime = str(getattr(one, "mimetype", "") or "image/jpeg")
        ocr_inputs.append((raw, mime))

    image_ocr_text = ""
    if ocr_inputs:
        try:
            image_ocr_text = _ocr_images_bytes_with_ai(ocr_inputs) or ""
        except Exception:
            image_ocr_text = ""
    debug = {
        "reason_code": "ok" if image_paths else "upload_empty",
        "reason_text": "上传图片处理完成" if image_paths else "上传图片为空",
        "saved_image_count": len(image_paths)
    }
    return image_paths, str(image_ocr_text or "").strip(), debug


def _xiaotu_save_inline_html_images_and_ocr(
    html_text,
    report_token,
    root_base_dir,
    *,
    _ocr_images_bytes_with_ai,
    base64,
    datetime,
    os,
    re,
    relocate_storage_path,
):
    src = str(html_text or "")
    if not src:
        return src, [], "", {"reason_code": "no_inline_image", "reason_text": "富文本中无内嵌图片", "saved_image_count": 0}

    token = str(report_token or datetime.now().strftime("%Y%m%d%H%M%S")).strip() or datetime.now().strftime("%Y%m%d%H%M%S")
    base_dir = os.path.abspath(str(root_base_dir or relocate_storage_path(r"D:\tuchuangai\报告图片")))
    root_dir = os.path.join(base_dir, f"upload_{token}_inline")
    os.makedirs(root_dir, exist_ok=True)

    image_paths = []
    ocr_inputs = []
    seen_data_urls = {}
    idx = 0

    def _ext_from_mime(mime_text):
        mt = str(mime_text or "").lower()
        if "png" in mt:
            return ".png"
        if "webp" in mt:
            return ".webp"
        if "gif" in mt:
            return ".gif"
        if "bmp" in mt:
            return ".bmp"
        return ".jpg"

    def _replace(match):
        nonlocal idx
        prefix = match.group(1)
        data_url = str(match.group(2) or "").strip()
        mime_text = str(match.group(3) or "").strip()
        payload = re.sub(r"\s+", "", str(match.group(4) or ""))
        suffix = match.group(5)
        if not data_url or not payload:
            return match.group(0)
        existing = seen_data_urls.get(data_url)
        if existing:
            return f"{prefix}{existing.replace(os.sep, '/')}{suffix}"
        try:
            image_bytes = base64.b64decode(payload, validate=False)
        except Exception:
            return match.group(0)
        if not image_bytes:
            return match.group(0)
        idx += 1
        save_path = os.path.join(root_dir, f"inline_{idx}{_ext_from_mime(mime_text)}")
        with open(save_path, "wb") as f:
            f.write(image_bytes)
        image_paths.append(save_path)
        ocr_inputs.append((image_bytes, mime_text or "image/jpeg"))
        seen_data_urls[data_url] = save_path
        return f"{prefix}{save_path.replace(os.sep, '/')}{suffix}"

    updated_html = re.sub(
        r'(<img\b[^>]*\bsrc\s*=\s*["\'])(data:(image/[^;,"\']+);base64,([^"\']+))(["\'][^>]*>)',
        _replace,
        src,
        flags=re.IGNORECASE
    )

    image_ocr_text = ""
    if ocr_inputs:
        try:
            image_ocr_text = _ocr_images_bytes_with_ai(ocr_inputs) or ""
        except Exception:
            image_ocr_text = ""
    debug = {
        "reason_code": "ok" if image_paths else "no_inline_image",
        "reason_text": "富文本内嵌图片处理完成" if image_paths else "富文本中无可保存的内嵌图片",
        "saved_image_count": len(image_paths)
    }
    return updated_html, image_paths, str(image_ocr_text or "").strip(), debug


def _xiaotu_extract_feishu_file_token_from_fragment(
    fragment_text,
    *,
    base64,
    html_unescape,
    json,
    re,
):
    raw = html_unescape(str(fragment_text or ""))
    if not raw:
        return ""
    patterns = [
        r'data-lark-image-uri\s*=\s*["\']\s*drivetoken://([A-Za-z0-9_-]{10,})',
        r'file_token["\']?\s*[:=]\s*["\']?([A-Za-z0-9_-]{10,})',
        r'"file_token"\s*:\s*"([A-Za-z0-9_-]{10,})"',
        r'"token"\s*:\s*"([A-Za-z0-9_-]{10,})"',
        r'drivetoken://([A-Za-z0-9_-]{10,})'
    ]
    for pat in patterns:
        m = re.search(pat, raw, flags=re.IGNORECASE)
        if m:
            return str(m.group(1) or "").strip()
    suite_match = re.search(r'data-suite\s*=\s*["\']([^"\']+)["\']', raw, flags=re.IGNORECASE)
    if suite_match:
        encoded = html_unescape(str(suite_match.group(1) or "")).strip()
        try:
            padding = "=" * ((4 - len(encoded) % 4) % 4)
            suite_text = base64.b64decode(encoded + padding).decode("utf-8", errors="ignore")
            suite_obj = json.loads(suite_text or "{}")
            token = str(suite_obj.get("fileToken") or "").strip()
            if token:
                return token
        except Exception:
            pass
    return ""


def _xiaotu_save_remote_html_images_and_ocr(
    html_text,
    report_token,
    agent,
    root_base_dir,
    *,
    _ocr_images_bytes_with_ai,
    _xiaotu_extract_feishu_file_token_from_fragment,
    datetime,
    html_unescape,
    mimetypes,
    os,
    re,
    relocate_storage_path,
    requests,
    unquote,
    urlparse,
):
    src = str(html_text or "")
    if not src:
        return src, [], "", {"reason_code": "no_remote_image", "reason_text": "富文本中无远程图片", "saved_image_count": 0}

    token = str(report_token or datetime.now().strftime("%Y%m%d%H%M%S")).strip() or datetime.now().strftime("%Y%m%d%H%M%S")
    base_dir = os.path.abspath(str(root_base_dir or relocate_storage_path(r"D:\tuchuangai\报告图片")))
    root_dir = os.path.join(base_dir, f"upload_{token}_remote")
    os.makedirs(root_dir, exist_ok=True)

    image_paths = []
    ocr_inputs = []
    download_errors = []
    seen_urls = {}
    seen_tokens = {}
    idx = 0

    def _normalize_remote_url(raw):
        u = html_unescape(str(raw or "")).strip()
        u = u.strip("`").strip().strip('"').strip("'").strip()
        if not u:
            return ""
        if u.startswith("https%3A") or u.startswith("http%3A"):
            try:
                u = unquote(u)
            except Exception:
                pass
        u = u.replace("&amp;", "&")
        u = u.strip("`").strip().strip('"').strip("'").strip()
        return u

    def _save_bytes(image_bytes, mime_text, source_key):
        nonlocal idx
        if not image_bytes:
            return ""
        idx += 1
        ext = _guess_ext(source_key, mime_text)
        save_path = os.path.join(root_dir, f"remote_{idx}{ext}")
        with open(save_path, "wb") as f:
            f.write(image_bytes)
        image_paths.append(save_path)
        ocr_inputs.append((image_bytes, mime_text or "image/jpeg"))
        return save_path

    def _guess_ext(url_text, content_type):
        ct = str(content_type or "").lower()
        if "png" in ct:
            return ".png"
        if "webp" in ct:
            return ".webp"
        if "gif" in ct:
            return ".gif"
        if "bmp" in ct:
            return ".bmp"
        if "jpeg" in ct or "jpg" in ct:
            return ".jpg"
        parsed = urlparse(str(url_text or "").strip())
        ext = os.path.splitext(parsed.path or "")[1].lower()
        if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
            return ext
        guessed = mimetypes.guess_extension(ct.split(";")[0].strip()) if ct else None
        if guessed in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
            return guessed
        return ".jpg"

    def _replace(match):
        nonlocal idx
        tag = str(match.group(0) or "")
        src_match = re.search(r'(\bsrc\s*=\s*["\'])([^"\']+)(["\'])', tag, flags=re.IGNORECASE)
        if not src_match:
            return tag
        prefix = str(src_match.group(1) or "")
        raw_url = _normalize_remote_url(src_match.group(2))
        suffix = str(src_match.group(3) or "")
        file_token = _xiaotu_extract_feishu_file_token_from_fragment(tag)
        if file_token:
            existing_by_token = seen_tokens.get(file_token)
            if existing_by_token:
                return re.sub(r'(\bsrc\s*=\s*["\'])[^"\']*(["\'])', rf'\1{existing_by_token.replace(os.sep, "/")}\2', tag, count=1, flags=re.IGNORECASE)
            if agent is not None and hasattr(agent, "download_media_bytes"):
                try:
                    blob, mime, dl_err = agent.download_media_bytes(file_token)
                except Exception as e:
                    blob, mime, dl_err = b"", "", str(e)
                if blob:
                    save_path = _save_bytes(blob, mime, f"feishu_token:{file_token}")
                    if save_path:
                        seen_tokens[file_token] = save_path
                        return re.sub(r'(\bsrc\s*=\s*["\'])[^"\']*(["\'])', rf'\1{save_path.replace(os.sep, "/")}\2', tag, count=1, flags=re.IGNORECASE)
                if dl_err:
                    download_errors.append(f"token:{file_token[:40]} -> {str(dl_err)}")
        if not raw_url:
            return tag
        lower_url = raw_url.lower()
        if (
            lower_url.startswith('/api/xiaotu/report_image')
            or lower_url.startswith('data:')
            or lower_url.startswith('blob:')
            or lower_url.startswith('file://')
        ):
            return tag
        if not re.match(r"^https?://", raw_url, flags=re.IGNORECASE):
            return tag
        existing = seen_urls.get(raw_url)
        if existing:
            return re.sub(r'(\bsrc\s*=\s*["\'])[^"\']*(["\'])', rf'\1{existing.replace(os.sep, "/")}\2', tag, count=1, flags=re.IGNORECASE)
        try:
            resp = requests.get(
                raw_url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": raw_url
                },
                timeout=20
            )
            if not resp.ok or not resp.content:
                download_errors.append(f"{raw_url[:120]} -> HTTP {getattr(resp, 'status_code', 'ERR')}")
                return tag
            content_type = str(resp.headers.get("Content-Type") or "").lower()
            if content_type and ("image/" not in content_type):
                download_errors.append(f"{raw_url[:120]} -> 非图片类型 {content_type}")
                return tag
            save_path = _save_bytes(resp.content, content_type, raw_url)
            seen_urls[raw_url] = save_path
            return re.sub(r'(\bsrc\s*=\s*["\'])[^"\']*(["\'])', rf'\1{save_path.replace(os.sep, "/")}\2', tag, count=1, flags=re.IGNORECASE)
        except Exception as e:
            download_errors.append(f"{raw_url[:120]} -> {str(e)}")
            return tag

    updated_html = re.sub(
        r'<img\b[^>]*>',
        _replace,
        src,
        flags=re.IGNORECASE
    )

    image_ocr_text = ""
    if ocr_inputs:
        try:
            image_ocr_text = _ocr_images_bytes_with_ai(ocr_inputs) or ""
        except Exception:
            image_ocr_text = ""
    debug = {
        "reason_code": "ok" if image_paths else "no_remote_image",
        "reason_text": ("富文本远程图片处理完成" if image_paths else ("富文本远程图片未下载成功" if download_errors else "富文本中无远程图片")),
        "saved_image_count": len(image_paths),
        "download_error": "；".join(download_errors[:3])
    }
    return updated_html, image_paths, str(image_ocr_text or "").strip(), debug


def _xiaotu_replace_html_img_src_with_paths(
    html_text,
    image_paths,
    *,
    re,
):
    src = str(html_text or "")
    paths = image_paths if isinstance(image_paths, list) else []
    if not src or not paths:
        return src
    idx = 0

    def _replace(match):
        nonlocal idx
        tag = str(match.group(0) or "")
        if 'data-local-image=' not in tag.lower():
            return tag
        if idx >= len(paths):
            return tag
        safe_path = paths[idx].replace("\\", "/")
        idx += 1
        return re.sub(r'(\bsrc\s*=\s*["\'])[^"\']*(["\'])', rf'\1{safe_path}\2', tag, count=1, flags=re.IGNORECASE)

    return re.sub(r"<img\b[^>]*>", _replace, src, flags=re.IGNORECASE)


def _xiaotu_image_debug(
    reason_code,
    reason_text,
    saved_count,
):
    return {
        "reason_code": str(reason_code or "failed"),
        "reason_text": str(reason_text or "").strip(),
        "saved_image_count": int(saved_count or 0),
    }
