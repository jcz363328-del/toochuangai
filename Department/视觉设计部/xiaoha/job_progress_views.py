"""Render task progress and usage status in Xiaoha."""

from __future__ import annotations


def calculate_smooth_running_progress(
    current_percent,
    reported_percent,
    *,
    waiting,
) -> int:
    """Advance visible progress in small steps while a background task is running."""
    current = max(1, min(int(current_percent or 1), 99))
    if waiting:
        return current
    reported = max(1, min(int(reported_percent or 1), 100))
    reported_target = min(reported, 97)
    if reported_target > current:
        return min(reported_target, current + 2)

    if reported <= 5:
        waiting_cap = 10
    elif reported < 72:
        waiting_cap = 70
    elif reported < 88:
        waiting_cap = 86
    else:
        waiting_cap = 97
    return min(waiting_cap, current + 1)


def build_running_job_spinner_html(
    progress_value,
    progress_stage,
    *,
    html,
) -> str:
    safe_stage = html.escape(str(progress_stage or "正在处理中").strip() or "正在处理中")
    return f"""
    <style>
    .result-empty.xiaoha-result-loading {{min-height:350px;display:flex;flex-direction:column;
      align-items:center;justify-content:center;gap:16px;box-sizing:border-box;text-align:center;
      border:1px dashed #7165ac;border-radius:12px;background:#0a1326;padding:28px;}}
    .xiaoha-result-orbit {{width:46px;height:46px;flex-shrink:0;border:3px solid #30284e;
      border-top-color:#a18aff;border-right-color:#58cbbf;border-radius:50%;
      animation:xiaoha-result-turn .9s linear infinite;}}
    .xiaoha-result-loading .empty-title {{color:#e9e6ff;overflow-wrap:anywhere;}}
    .xiaoha-result-loading .empty-subtitle {{color:#aab5d1;}}
    @keyframes xiaoha-result-turn {{to {{transform:rotate(360deg);}}}}
    @media(prefers-reduced-motion:reduce) {{.xiaoha-result-orbit {{animation:none;}}}}
    </style>
    <div class="result-empty xiaoha-result-loading" role="status" aria-live="polite">
      <div class="xiaoha-result-orbit" aria-hidden="true"></div>
      <div class="empty-title">{safe_stage}</div>
      <div class="empty-subtitle">完成后将在这里显示结果，可切换到其他功能</div>
    </div>
    """


def build_queued_job_card_html(
    job_info,
    *,
    html,
) -> str:
    ahead_count = max(int(job_info.get("queue_ahead") or 0), 0)
    feature_name = html.escape(str(job_info.get("feature_name") or "生成任务"))
    submitted_at = html.escape(str(job_info.get("submitted_at") or ""))
    queue_text = (
        f"前面还有 {ahead_count} 个任务，完成后会自动开始"
        if ahead_count
        else "前序任务即将结束，马上开始"
    )
    return f"""
    <div class="xiaoha-task-spinner-card" role="status" aria-live="polite">
      <div class="xiaoha-task-spinner-circle" aria-hidden="true">
        <div class="xiaoha-task-spinner-orbit"></div>
        <span class="xiaoha-task-spinner-value">排队</span>
      </div>
      <div>
        <div class="xiaoha-task-spinner-stage">{feature_name} · 已加入任务队列</div>
        <div class="xiaoha-task-spinner-subtitle">{queue_text}{f' · {submitted_at}' if submitted_at else ''}</div>
      </div>
    </div>
    """


def build_job_queue_overview_html(
    active_jobs,
    current_job_id,
    *,
    html,
) -> str:
    if len(active_jobs) <= 1:
        return ""
    items: list[str] = []
    for job_info in active_jobs:
        job_id = str(job_info.get("job_id") or "")
        status = str(job_info.get("status") or "").strip().lower()
        feature_name = html.escape(str(job_info.get("feature_name") or "生成任务"))
        if status == "running":
            state_label = f"执行中 · {max(1, min(int(job_info.get('progress') or 1), 99))}%"
        else:
            ahead_count = max(int(job_info.get("queue_ahead") or 0), 0)
            state_label = f"等待中 · 前面 {ahead_count} 个"
        current_class = " current" if job_id and job_id == current_job_id else ""
        items.append(
            f'<div class="xiaoha-queue-row{current_class}"><span>{feature_name}</span>'
            f'<strong>{html.escape(state_label)}</strong></div>'
        )
    return (
        '<div class="xiaoha-queue-overview"><div class="xiaoha-queue-title">任务队列</div>'
        + "".join(items)
        + "</div>"
    )


def render_xiaoha_usage_dashboard(
    *,
    build_xiaoha_usage_dashboard_data,
    build_xiaoha_usage_dashboard_html,
    components,
    datetime,
    format_user_facing_error_message,
    load_xiaoha_usage_dashboard_rows,
    st,
) -> None:
    title_col, refresh_col = st.columns([5.6, 0.8], vertical_alignment="bottom")
    with title_col:
        st.markdown("## 今日数据看板")
        st.caption("查看当天各功能使用情况，以及最近 7 天与昨日的时间线对比。")
    with refresh_col:
        if st.button("刷新数据", key="refresh_xiaoha_usage_dashboard", use_container_width=True):
            load_xiaoha_usage_dashboard_rows.clear()
            st.rerun()

    today = datetime.now().date()
    try:
        rows = load_xiaoha_usage_dashboard_rows(today.isoformat())
    except Exception as exc:
        st.error("数据看板暂时无法连接统计数据库，请稍后刷新。")
        st.caption(f"统计查询错误：{format_user_facing_error_message(exc)}")
        return
    dashboard_data = build_xiaoha_usage_dashboard_data(rows, today)
    components.html(
        build_xiaoha_usage_dashboard_html(dashboard_data),
        height=1050,
        scrolling=False,
    )
