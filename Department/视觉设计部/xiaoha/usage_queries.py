"""Read Xiaoha usage dashboard data."""

from __future__ import annotations

from typing import Any


def load_xiaoha_usage_dashboard_rows(
    reference_date_text,
    *,
    DB_HISTORY_TABLE,
    XIAOHA_DASHBOARD_HISTORY_DAYS,
    datetime,
    execute_db_query,
    normalize_dashboard_date,
    timedelta,
) -> list[tuple[Any, ...]]:
    today = normalize_dashboard_date(reference_date_text) or datetime.now().date()
    range_start = datetime.combine(
        today - timedelta(days=XIAOHA_DASHBOARD_HISTORY_DAYS - 1),
        datetime.min.time(),
    )
    today_start = datetime.combine(today, datetime.min.time())
    range_end = today_start + timedelta(days=1)
    query = f"""
        WITH UsageByHour AS (
            SELECT
                CAST(RiQi AS date) AS UsageDate,
                DATEPART(hour, RiQi) AS UsageHour,
                CASE
                    WHEN NULLIF(LTRIM(RTRIM(GongNeng)), '') IS NULL THEN N'未分类功能'
                    ELSE LTRIM(RTRIM(GongNeng))
                END AS FeatureName,
                COUNT_BIG(*) AS UsageCount
            FROM {DB_HISTORY_TABLE}
            WHERE RiQi >= %s AND RiQi < %s
            GROUP BY
                CAST(RiQi AS date),
                DATEPART(hour, RiQi),
                CASE
                    WHEN NULLIF(LTRIM(RTRIM(GongNeng)), '') IS NULL THEN N'未分类功能'
                    ELSE LTRIM(RTRIM(GongNeng))
                END
        ),
        TodayAccounts AS (
            SELECT COUNT(DISTINCT NULLIF(LTRIM(RTRIM(ZhangHao)), '')) AS ActiveAccounts
            FROM {DB_HISTORY_TABLE}
            WHERE RiQi >= %s AND RiQi < %s
        )
        SELECT
            UsageByHour.UsageDate,
            UsageByHour.UsageHour,
            UsageByHour.FeatureName,
            UsageByHour.UsageCount,
            TodayAccounts.ActiveAccounts
        FROM TodayAccounts
        LEFT JOIN UsageByHour ON 1 = 1
        ORDER BY UsageByHour.UsageDate, UsageByHour.UsageHour, UsageByHour.UsageCount DESC
    """
    return execute_db_query(
        query,
        (range_start, range_end, today_start, range_end),
    )
