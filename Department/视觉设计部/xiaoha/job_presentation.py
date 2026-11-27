"""Display live jobs, billing and persisted history in the workbench."""

from __future__ import annotations

from datetime import date
from typing import Any


def calculate_finishing_progress(
    start_percent,
    elapsed_seconds,
    duration_seconds,
    *,
    math,
) -> int:
    """Animate a completed backend task to 100 instead of jumping instantly."""
    start = max(1, min(int(start_percent or 1), 99))
    duration = max(float(duration_seconds), 0.1)
    fraction = max(0.0, min(float(elapsed_seconds) / duration, 1.0))
    return min(100, max(start, int(math.floor(start + ((100 - start) * fraction)))))


def render_running_job_status(
    feature_key,
    in_result,
    *,
    build_running_job_spinner_html,
    st,
    sync_background_jobs,
) -> None:
    # A scheduled fragment from the previous page may arrive during navigation.
    # It must not synchronize jobs or request a full-app rerun on the new page.
    if st.session_state.get("selected_feature_key") != feature_key:
        return
    sync_background_jobs()
    current_job = st.session_state.get("background_jobs", {}).get(feature_key) or {}
    status = str(current_job.get("status") or "").strip().lower()
    if status not in {"queued", "running"}:
        st.rerun()
        return
    # Existing header calls retain background polling without adding a status banner.
    if in_result:
        stage = "任务排队中，等待开始" if status == "queued" else str(current_job.get("stage") or "正在生成，请稍候")
        st.markdown(build_running_job_spinner_html(0, stage), unsafe_allow_html=True)


def render_result_loading(
    feature_key,
    *,
    render_running_job_status,
    st,
) -> bool:
    key = feature_key or str(st.session_state.get("selected_feature_key") or "")
    job = st.session_state.get("background_jobs", {}).get(key) or {}
    if str(job.get("status") or "").lower() not in {"queued", "running"}:
        return False
    render_running_job_status(key, in_result=True)
    return True


def normalize_dashboard_date(
    value,
    *,
    date,
    datetime,
) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text_value = str(value or "").strip()
    if not text_value:
        return None
    try:
        return date.fromisoformat(text_value[:10])
    except ValueError:
        return None


def render_xiaoha_balance_management(
    *,
    SimpleNamespace,
    load_omnia_api_key,
    st,
) -> None:
    from Department.视觉设计部.xiaoha.balance_view import render_balance_management
    from Department.视觉设计部.xiaoha.balance_provider import load_balance_snapshot

    render_balance_management(
        SimpleNamespace(st=st),
        lambda force=False: load_balance_snapshot(force=force, primary_loader=load_omnia_api_key),
    )


def format_history_datetime(
    value,
    *,
    datetime,
) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "").strip()


def get_history_cache_key(account_name, feature_key) -> str:
    normalized_account = str(account_name or "admin").strip() or "admin"
    normalized_feature = str(feature_key or "").strip() or "all"
    return f"history:{normalized_account}:{normalized_feature}"


def get_history_visible_limit(
    cache_key,
    *,
    HISTORY_PAGE_SIZE,
    st,
) -> int:
    current = st.session_state.history_visible_counts.get(cache_key, HISTORY_PAGE_SIZE)
    return max(int(current), HISTORY_PAGE_SIZE)


def set_history_visible_limit(
    cache_key,
    limit,
    *,
    HISTORY_PAGE_SIZE,
    st,
) -> None:
    st.session_state.history_visible_counts[cache_key] = max(int(limit), HISTORY_PAGE_SIZE)


def ensure_history_records_loaded(
    feature_key,
    account_name,
    cache_key,
    limit,
    *,
    HISTORY_PAGE_SIZE,
    get_feature_history_records,
    st,
) -> list[dict[str, Any]]:
    safe_limit = max(int(limit), HISTORY_PAGE_SIZE)
    cached_records = st.session_state.history_records_cache.get(cache_key)
    if cached_records is not None and len(cached_records) >= safe_limit:
        return list(cached_records)
    records = get_feature_history_records(feature_key, account_name, limit=safe_limit)
    st.session_state.history_records_cache[cache_key] = records
    return records


def get_history_columns_per_row(item_count) -> int:
    if item_count <= 2:
        return max(item_count, 1)
    if item_count <= 6:
        return 3
    return 4
