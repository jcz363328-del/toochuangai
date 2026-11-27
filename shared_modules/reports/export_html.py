from datetime import datetime
from html import escape as html_escape
from .formatting import _xiaotu_html_to_plain_text_preserve_blocks
from .export_media import _xiaotu_history_export_value, _xiaotu_history_export_optional_detail

def _xiaotu_history_export_section_html(rows, source_label, image_cache=None, *, render_body):
    normalized_rows = rows if isinstance(rows, list) else [rows]
    cards = []
    embedded_total = 0
    missing_total = 0
    for index, row in enumerate(normalized_rows, start=1):
        value = lambda key, position: _xiaotu_history_export_value(row, key, position)
        body_html, embedded_count, missing_count = render_body(
            value("ZhengWen", 4),
            value("TuPianLujin", 5),
            image_cache=image_cache,
        )
        embedded_total += embedded_count
        missing_total += missing_count
        title = _xiaotu_html_to_plain_text_preserve_blocks(value("BiaoTi", 3)) or "未命名日报"
        wid = str(value("WenDangID", 0) or "").strip()
        report_type = str(value("LeiXing", 7) or "-").strip() or "-"
        person_type = str(value("RenYuanLeiXing", 8) or "-").strip() or "-"
        cards.append(f"""
        <article class="report-record">
          <div class="record-topline">
            <span class="record-index">#{index}</span>
            <time>{html_escape(str(value("RiQi", 1) or "").strip())}</time>
            <span class="tag">{html_escape(report_type)}</span>
            <span class="tag">{html_escape(person_type)}</span>
          </div>
          <h2>{html_escape(title)}</h2>
          <dl class="record-meta">
            <div><dt>提报人</dt><dd>{html_escape(str(value("XingMing", 2) or "-").strip() or "-")}</dd></div>
            <div><dt>接收人</dt><dd>{html_escape(str(value("JieShouRen", 9) or "-").strip() or "-")}</dd></div>
            <div><dt>日报 ID</dt><dd>{html_escape(wid or "-")}</dd></div>
            <div><dt>点赞状态</dt><dd>{html_escape(str(value("DianZan", 11) or "未点赞").strip() or "未点赞")}</dd></div>
          </dl>
          <div class="record-body">{body_html}</div>
          <div class="record-details">
            {_xiaotu_history_export_optional_detail("图片识别内容", value("TuPianNeiRong", 6))}
            {_xiaotu_history_export_optional_detail("AI 评价", value("PingJia", 10))}
            {_xiaotu_history_export_optional_detail("评论", value("PingLun", 12))}
            {_xiaotu_history_export_optional_detail("回复", value("HuiFu", 13))}
          </div>
        </article>
        """)
    empty_html = '<div class="empty-state">暂无记录</div>'
    section_html = f"""
    <section class="report-section">
      <div class="section-heading"><h1>{html_escape(source_label)}</h1><span>{len(normalized_rows)} 条</span></div>
      {''.join(cards) if cards else empty_html}
    </section>
    """
    return section_html, embedded_total, missing_total

def _xiaotu_build_history_export_html(session_user_name, ctx, rows_uploaded, rows_received, *, render_body):
    image_cache = {}
    uploaded_html, uploaded_images, uploaded_missing = _xiaotu_history_export_section_html(
        rows_uploaded, "提报记录", image_cache=image_cache, render_body=render_body
    )
    received_html, received_images, received_missing = _xiaotu_history_export_section_html(
        rows_received, "收到记录", image_cache=image_cache, render_body=render_body
    )
    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    start_date = str(ctx.get("date_start") or "未限制")
    end_date = str(ctx.get("date_end") or "未限制")
    filter_name = str(ctx.get("name") or "未限制")
    keyword = str(ctx.get("keyword") or "未限制")
    embedded_total = uploaded_images + received_images
    missing_total = uploaded_missing + received_missing
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
  <title>报告历史记录 {html_escape(start_date)} 至 {html_escape(end_date)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f4f6f8; color: #172033; font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif; }}
    .page {{ width: min(1120px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 56px; }}
    .export-header {{ padding: 22px; border: 1px solid #dfe4ea; background: #fff; }}
    .export-header h1 {{ margin: 0 0 14px; font-size: 24px; }}
    .export-meta {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 18px; color: #5e6878; font-size: 13px; line-height: 1.6; }}
    .export-meta strong {{ color: #273244; }}
    .report-section {{ margin-top: 22px; }}
    .section-heading {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 10px; }}
    .section-heading h1 {{ margin: 0; font-size: 20px; }}
    .section-heading span {{ color: #687386; font-size: 13px; }}
    .report-record {{ margin-top: 10px; padding: 20px; border: 1px solid #dfe4ea; background: #fff; break-inside: avoid; }}
    .record-topline {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; color: #687386; font-size: 12px; }}
    .record-index {{ color: #2563eb; font-weight: 800; }}
    .tag {{ padding: 3px 7px; border: 1px solid #d9e0e8; background: #f7f9fb; color: #465267; }}
    .report-record h2 {{ margin: 12px 0; font-size: 19px; overflow-wrap: anywhere; }}
    .record-meta {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 0 0 16px; padding: 12px; background: #f7f9fb; }}
    .record-meta div {{ min-width: 0; }}
    .record-meta dt {{ color: #758094; font-size: 11px; }}
    .record-meta dd {{ margin: 4px 0 0; color: #303b4d; font-size: 12px; overflow-wrap: anywhere; }}
    .record-body {{ font-size: 14px; line-height: 1.8; overflow-wrap: anywhere; }}
    .record-body img {{ display: block; max-width: 100%; height: auto; margin: 14px 0; border: 1px solid #e1e6ec; }}
    .record-body figure {{ margin: 14px 0; }}
    .record-body figcaption {{ color: #758094; font-size: 12px; }}
    .image-missing {{ display: inline-block; margin: 8px 0; color: #a13d45; font-size: 12px; }}
    .record-details {{ display: grid; gap: 8px; margin-top: 14px; }}
    .record-detail {{ border-top: 1px solid #e6eaf0; padding-top: 8px; }}
    .record-detail summary {{ cursor: pointer; color: #465267; font-size: 13px; font-weight: 700; }}
    .record-detail pre {{ margin: 8px 0 0; padding: 12px; background: #f7f9fb; color: #364154; font: inherit; font-size: 12px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .empty-state {{ padding: 32px; border: 1px solid #dfe4ea; background: #fff; color: #758094; text-align: center; }}
    @media (max-width: 760px) {{ .export-meta, .record-meta {{ grid-template-columns: 1fr 1fr; }} }}
    @media print {{ body {{ background: #fff; }} .page {{ width: 100%; padding: 0; }} .report-record, .export-header {{ border-color: #bbb; }} }}
  </style>
</head>
<body>
  <main class="page">
    <header class="export-header">
      <h1>报告历史记录</h1>
      <div class="export-meta">
        <span><strong>导出人：</strong>{html_escape(session_user_name or "-")}</span>
        <span><strong>导出时间：</strong>{html_escape(generated_at)}</span>
        <span><strong>日期范围：</strong>{html_escape(start_date)} 至 {html_escape(end_date)}</span>
        <span><strong>姓名筛选：</strong>{html_escape(filter_name)}</span>
        <span><strong>关键词：</strong>{html_escape(keyword)}</span>
        <span><strong>内嵌图片：</strong>{embedded_total} 张{f'，{missing_total} 张不可用' if missing_total else ''}</span>
      </div>
    </header>
    {uploaded_html}
    {received_html}
  </main>
</body>
</html>"""

