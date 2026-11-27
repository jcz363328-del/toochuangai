"""Compose and format report history, analysis and export views."""

from __future__ import annotations


def _xiaotu_normalize_report_html_body(
    raw_html,
    image_paths_text,
    *,
    _xiaotu_report_image_url,
    html_escape,
    html_unescape,
    os,
    re,
):
    html = str(raw_html or "").strip()
    paths = [
        str(x or "").strip()
        for x in re.split(r"[|;\n]+", str(image_paths_text or ""))
        if str(x or "").strip()
    ]
    if html:
        def repl_img_src(match):
            quote_char = match.group(1) or '"'
            src = html_unescape(str(match.group(2) or "").strip())
            if not src or src.startswith("data:") or src.startswith("http://") or src.startswith("https://") or src.startswith("/api/xiaotu/report_image"):
                return match.group(0)
            return f"src={quote_char}{html_escape(_xiaotu_report_image_url(src), quote=True)}{quote_char}"

        html = re.sub(r"src\s*=\s*([\"'])([^\"']+)\1", repl_img_src, html, flags=re.IGNORECASE)
    else:
        html = "<p>（无正文）</p>"
    existing = set()
    for m in re.finditer(r"<img\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE):
        existing.add(html_unescape(str(m.group(1) or "").strip()))
    extra_imgs = []
    for path in paths:
        img_url = _xiaotu_report_image_url(path)
        if not img_url or img_url in existing or path in existing:
            continue
        extra_imgs.append(
            f'<figure><img src="{html_escape(img_url, quote=True)}" alt="日报图片"><figcaption>{html_escape(os.path.basename(path))}</figcaption></figure>'
        )
    if extra_imgs:
        html += "\n" + "\n".join(extra_imgs)
    return html


def _xiaotu_build_history_analysis_html(
    user_name,
    start_date,
    end_date,
    analysis_text,
    rows,
    *,
    _xiaotu_markdownish_to_html,
    _xiaotu_normalize_report_html_body,
    datetime,
    html_escape,
):
    range_text = f"{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    analysis_html = _xiaotu_markdownish_to_html(analysis_text)
    item_html = []
    for idx, one in enumerate(rows, start=1):
        riqi = html_escape(str((one or {}).get("riqi") or "").strip())
        title = html_escape(str((one or {}).get("biaoti") or "未命名日报").strip())
        body_html = _xiaotu_normalize_report_html_body(
            (one or {}).get("zhengwen") or "",
            (one or {}).get("tupianlujin") or ""
        )
        ocr_text = str((one or {}).get("tupianneirong") or "").strip()
        ocr_html = f"<details><summary>图片识别内容</summary><pre>{html_escape(ocr_text)}</pre></details>" if ocr_text else ""
        item_html.append(f"""
        <article class="daily-item">
            <div class="daily-index">#{idx}</div>
            <h2>{title}</h2>
            <div class="daily-meta">{riqi}</div>
            <div class="daily-body">{body_html}</div>
            {ocr_html}
        </article>
        """)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_escape(user_name)} 日报历史分析 {html_escape(range_text)}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; color: #172033; background: #f6f7fb; }}
    .wrap {{ max-width: 1080px; margin: 0 auto; padding: 28px 18px 56px; }}
    .hero {{ background: #ffffff; border: 1px solid #e7eaf0; border-radius: 8px; padding: 22px; margin-bottom: 16px; }}
    h1 {{ font-size: 24px; margin: 0 0 8px; }}
    .meta {{ color: #64748b; font-size: 13px; line-height: 1.7; }}
    .analysis, .daily-item {{ background: #ffffff; border: 1px solid #e7eaf0; border-radius: 8px; padding: 20px; margin-top: 14px; }}
    .analysis h2, .daily-item h2 {{ margin: 0 0 10px; font-size: 18px; }}
    .analysis p, .analysis li {{ line-height: 1.75; }}
    .daily-index {{ display: inline-block; color: #2563eb; font-weight: 700; margin-bottom: 8px; }}
    .daily-meta {{ color: #64748b; font-size: 13px; margin-bottom: 12px; }}
    .daily-body {{ line-height: 1.75; overflow-wrap: anywhere; }}
    .daily-body img, figure img {{ max-width: 100%; height: auto; border: 1px solid #e5e7eb; border-radius: 6px; margin: 8px 0; }}
    figure {{ margin: 12px 0; }}
    figcaption {{ color: #64748b; font-size: 12px; }}
    pre {{ white-space: pre-wrap; background: #f8fafc; padding: 12px; border-radius: 6px; color: #334155; }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>{html_escape(user_name)} 日报历史分析</h1>
      <div class="meta">日期范围：{html_escape(range_text)} | 日报数量：{len(rows)} | 生成时间：{html_escape(generated_at)}</div>
    </section>
    <section class="analysis">
      <h2>整合分析</h2>
      {analysis_html}
    </section>
    {''.join(item_html)}
  </main>
</body>
</html>"""


def _xiaotu_history_export_body_html(
    raw_body,
    image_paths_text,
    image_cache,
    *,
    _xiaotu_history_export_image_data_uri,
    _xiaotu_normalize_report_html_body,
    html_escape,
    html_unescape,
    re,
):
    body_text = str(raw_body or "").strip()
    if body_text and not re.search(r"<[A-Za-z][^>]*>", body_text):
        body_text = "<p>" + html_escape(body_text).replace("\n", "<br>") + "</p>"
    html = _xiaotu_normalize_report_html_body(body_text, image_paths_text)
    html = re.sub(
        r"<\s*(script|style|iframe|object|embed|form|meta|link|base)\b[^>]*>[\s\S]*?<\s*/\s*\1\s*>",
        "",
        html,
        flags=re.IGNORECASE,
    )
    html = re.sub(r"<\s*(?:script|style|iframe|object|embed|form|meta|link|base)\b[^>]*?/?>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\s+on[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html, flags=re.IGNORECASE)
    # 保留原富文本排版，仅移除可执行代码或发起外部请求的危险 CSS。
    def sanitize_style(match):
        quote_char = match.group(1)
        style_value = str(match.group(2) or "")
        safe_declarations = []
        for declaration in style_value.split(";"):
            if ":" not in declaration:
                continue
            property_name, property_value = declaration.split(":", 1)
            property_name = property_name.strip().lower()
            property_value = property_value.strip()
            if not re.fullmatch(r"(?:color|background-color|font-(?:size|weight|style|family)|text-(?:align|decoration|indent)|line-height|letter-spacing|white-space|margin(?:-(?:top|right|bottom|left))?|padding(?:-(?:top|right|bottom|left))?|list-style-type|border(?:-(?:top|right|bottom|left))?(?:-(?:color|style|width))?|width|max-width|height|max-height)", property_name):
                continue
            if re.search(r"(?:url\s*\(|expression\s*\(|javascript:|@import|behavior\s*:|-moz-binding)", property_value, flags=re.IGNORECASE):
                continue
            safe_declarations.append(f"{property_name}: {property_value}")
        return (f" style={quote_char}{'; '.join(safe_declarations)}{quote_char}" if safe_declarations else "")

    html = re.sub(r"\s+style\s*=\s*([\"'])(.*?)\1", sanitize_style, html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"\s+href\s*=\s*([\"'])\s*javascript:[^\"']*\1", "", html, flags=re.IGNORECASE)

    embedded_count = 0
    missing_count = 0

    def replace_image_tag(match):
        nonlocal embedded_count, missing_count
        tag = str(match.group(0) or "")
        src_match = re.search(r"\bsrc\s*=\s*([\"'])([^\"']+)\1", tag, flags=re.IGNORECASE)
        src = html_unescape(str(src_match.group(2) if src_match else "").strip())
        data_uri = _xiaotu_history_export_image_data_uri(src, image_cache=image_cache)
        alt_match = re.search(r"\balt\s*=\s*([\"'])([^\"']*)\1", tag, flags=re.IGNORECASE)
        alt_text = html_unescape(str(alt_match.group(2) if alt_match else "日报图片").strip()) or "日报图片"
        if not data_uri:
            missing_count += 1
            return f'<span class="image-missing">[{html_escape(alt_text)}暂不可用]</span>'
        embedded_count += 1
        preserved_attributes = []
        for attribute_name in ("class", "style", "width", "height"):
            attribute_match = re.search(
                rf"\b{attribute_name}\s*=\s*([\"'])(.*?)\1",
                tag,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if attribute_match:
                preserved_attributes.append(
                    f'{attribute_name}="{html_escape(attribute_match.group(2), quote=True)}"'
                )
        extra = (" " + " ".join(preserved_attributes)) if preserved_attributes else ""
        return f'<img src="{html_escape(data_uri, quote=True)}" alt="{html_escape(alt_text, quote=True)}"{extra}>'

    html = re.sub(r"<img\b[^>]*>", replace_image_tag, html, flags=re.IGNORECASE)
    return html, embedded_count, missing_count


def _xiaotu_build_history_export_html(
    session_user_name,
    ctx,
    rows_uploaded,
    rows_received,
    *,
    _xiaotu_history_export_body_html,
    export_html,
):
    return export_html._xiaotu_build_history_export_html(
        session_user_name, ctx, rows_uploaded, rows_received,
        render_body=_xiaotu_history_export_body_html,
    )
