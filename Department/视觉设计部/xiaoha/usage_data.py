"""Aggregate Xiaoha usage and account statistics."""

from __future__ import annotations

from typing import Any


def build_xiaoha_usage_dashboard_data(
    rows,
    reference_date,
    *,
    XIAOHA_DASHBOARD_HISTORY_DAYS,
    XIAOHA_DASHBOARD_MAX_FEATURE_LINES,
    date,
    datetime,
    normalize_dashboard_date,
    timedelta,
) -> dict[str, Any]:
    today = normalize_dashboard_date(reference_date) or datetime.now().date()
    yesterday = today - timedelta(days=1)
    first_day = today - timedelta(days=XIAOHA_DASHBOARD_HISTORY_DAYS - 1)
    usage_counts: dict[tuple[date, int, str], int] = {}
    today_active_accounts = 0

    for row in rows:
        if len(row) > 4:
            try:
                today_active_accounts = max(today_active_accounts, int(row[4] or 0))
            except (TypeError, ValueError):
                pass
        usage_day = normalize_dashboard_date(row[0] if len(row) > 0 else None)
        if usage_day is None or usage_day < first_day or usage_day > today:
            continue
        try:
            usage_hour = int(row[1] if len(row) > 1 else 0)
        except (TypeError, ValueError):
            usage_hour = 0
        usage_hour = max(0, min(usage_hour, 23))
        feature_name = str(row[2] if len(row) > 2 else "").strip() or "未分类功能"
        try:
            usage_count = max(int(row[3] if len(row) > 3 else 0), 0)
        except (TypeError, ValueError):
            usage_count = 0
        key = (usage_day, usage_hour, feature_name)
        usage_counts[key] = usage_counts.get(key, 0) + usage_count

    day_sequence = [first_day + timedelta(days=offset) for offset in range(XIAOHA_DASHBOARD_HISTORY_DAYS)]
    hour_labels = [f"{hour:02d}:00" for hour in range(24)]
    today_feature_totals: dict[str, int] = {}
    recent_feature_totals: dict[str, int] = {}
    today_hour_totals = [0] * 24
    yesterday_hour_totals = [0] * 24
    daily_totals = {usage_day: 0 for usage_day in day_sequence}

    for (usage_day, usage_hour, feature_name), usage_count in usage_counts.items():
        recent_feature_totals[feature_name] = recent_feature_totals.get(feature_name, 0) + usage_count
        daily_totals[usage_day] = daily_totals.get(usage_day, 0) + usage_count
        if usage_day == today:
            today_feature_totals[feature_name] = today_feature_totals.get(feature_name, 0) + usage_count
            today_hour_totals[usage_hour] += usage_count
        elif usage_day == yesterday:
            yesterday_hour_totals[usage_hour] += usage_count

    sorted_today_features = sorted(
        today_feature_totals.items(),
        key=lambda item: (-item[1], item[0]),
    )
    line_feature_source = sorted_today_features or sorted(
        recent_feature_totals.items(),
        key=lambda item: (-item[1], item[0]),
    )
    line_feature_names = [
        feature_name
        for feature_name, _count in line_feature_source[:XIAOHA_DASHBOARD_MAX_FEATURE_LINES]
    ]
    feature_hour_series = []
    for feature_name in line_feature_names:
        feature_hour_series.append(
            {
                "name": feature_name,
                "data": [
                    usage_counts.get((today, hour, feature_name), 0)
                    for hour in range(24)
                ],
            }
        )

    today_total = sum(today_hour_totals)
    yesterday_total = sum(yesterday_hour_totals)
    delta_count = today_total - yesterday_total
    if yesterday_total > 0:
        delta_percent = round((delta_count / yesterday_total) * 100, 1)
        delta_label = f"{delta_percent:+g}% 较昨日"
    elif today_total > 0:
        delta_label = "今日新增记录"
    else:
        delta_label = "今日暂无记录"

    peak_count = max(today_hour_totals) if today_hour_totals else 0
    peak_hour = today_hour_totals.index(peak_count) if peak_count > 0 else None
    top_feature_name = sorted_today_features[0][0] if sorted_today_features else "暂无"
    top_feature_count = sorted_today_features[0][1] if sorted_today_features else 0

    return {
        "date": today.isoformat(),
        "date_label": today.strftime("%Y年%m月%d日"),
        "updated_at": datetime.now().strftime("%H:%M:%S"),
        "today_total": today_total,
        "yesterday_total": yesterday_total,
        "delta_count": delta_count,
        "delta_label": delta_label,
        "active_accounts": today_active_accounts,
        "active_features": len([count for count in today_feature_totals.values() if count > 0]),
        "peak_hour": f"{peak_hour:02d}:00" if peak_hour is not None else "—",
        "peak_count": peak_count,
        "top_feature_name": top_feature_name,
        "top_feature_count": top_feature_count,
        "feature_names": [feature_name for feature_name, _count in sorted_today_features],
        "feature_counts": [count for _feature_name, count in sorted_today_features],
        "hour_labels": hour_labels,
        "today_hour_totals": today_hour_totals,
        "yesterday_hour_totals": yesterday_hour_totals,
        "day_labels": [usage_day.strftime("%m-%d") for usage_day in day_sequence],
        "day_totals": [daily_totals.get(usage_day, 0) for usage_day in day_sequence],
        "feature_hour_series": feature_hour_series,
        "has_today_data": today_total > 0,
    }
