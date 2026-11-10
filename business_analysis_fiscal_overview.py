"""Source-backed fiscal target progress for the business-analysis home page."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytds

from secret_settings import sql_server_config


logger = logging.getLogger(__name__)


FISCAL_YEAR_PATTERN = re.compile(r"^(?P<start>\d{4})-(?P<end>\d{4})$")
MONTH_PATTERN = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
PERIOD_TYPES = {"annual", "quarter", "month"}
CACHE_VERSION = 1
CACHE_DIRECTORY = Path(
    os.environ.get("BUSINESS_ANALYSIS_FISCAL_CACHE_DIR")
    or Path(__file__).resolve().parent / "business_analysis" / "data"
)

SOURCE_TO_DISPLAY_DEPARTMENT = {
    "周雪": "运营一部",
    "王钰媛": "运营二部",
    "大张雯": "运营三部",
    "郭鑫": "运营六部",
    "侯瑞昕": "运营七部",
    "侯瑞欣": "运营七部",
}
DISPLAY_TO_SOURCE_DEPARTMENT = {
    display: source
    for source, display in SOURCE_TO_DISPLAY_DEPARTMENT.items()
    if source != "侯瑞欣"
}
DEPARTMENT_DISPLAY_ORDER = ["运营一部", "运营二部", "运营三部", "运营六部", "运营七部"]

FISCAL_OVERVIEW_SQL = """
WITH TargetRows AS (
    SELECT
        CAST(RiQi AS date) AS PeriodStart,
        Dian AS Store,
        MAX(YunYing) AS Operator,
        MAX(BuMen) AS Department,
        SUM(CAST(ZhiBiao AS decimal(28,4))) AS Target
    FROM dbo.v_ZhiBiao
    WHERE CaiNian=%s
    GROUP BY CAST(RiQi AS date), Dian
), Bounds AS (
    SELECT MIN(PeriodStart) AS StartDate, DATEADD(month, 1, MAX(PeriodStart)) AS EndDate
    FROM TargetRows
), ActualRows AS (
    SELECT
        DATEFROMPARTS(YEAR(ml.RiQi), MONTH(ml.RiQi), 1) AS PeriodStart,
        ml.Dian AS Store,
        SUM(CAST(ml.XiaoShouE AS decimal(28,4))) AS Actual
    FROM dbo.LiRun ml
    CROSS JOIN Bounds b
    WHERE ml.RiQi >= b.StartDate AND ml.RiQi < b.EndDate
      AND EXISTS (SELECT 1 FROM TargetRows t WHERE t.Store=ml.Dian)
    GROUP BY DATEFROMPARTS(YEAR(ml.RiQi), MONTH(ml.RiQi), 1), ml.Dian
), LatestActual AS (
    SELECT MAX(CAST(ml.RiQi AS date)) AS LatestActualDate
    FROM dbo.LiRun ml
    CROSS JOIN Bounds b
    WHERE ml.RiQi >= b.StartDate AND ml.RiQi < b.EndDate
      AND EXISTS (SELECT 1 FROM TargetRows t WHERE t.Store=ml.Dian)
), ActualStoreUniverse AS (
    SELECT DISTINCT ml.Dian AS Store
    FROM dbo.LiRun ml
    CROSS JOIN Bounds b
    WHERE ml.RiQi >= b.StartDate AND ml.RiQi < b.EndDate
), TargetStores AS (
    SELECT DISTINCT Store FROM TargetRows
)
SELECT
    t.PeriodStart,
    t.Store,
    t.Operator,
    t.Department,
    t.Target,
    COALESCE(a.Actual, 0) AS Actual,
    l.LatestActualDate,
    CASE WHEN EXISTS (SELECT 1 FROM ActualStoreUniverse au WHERE au.Store=t.Store) THEN 1 ELSE 0 END AS IsMetricStore,
    (SELECT COUNT(*) FROM TargetStores) AS TargetStoreCount,
    (SELECT COUNT(*) FROM TargetStores ts WHERE EXISTS (SELECT 1 FROM ActualStoreUniverse au WHERE au.Store=ts.Store)) AS MatchedStoreCount,
    (SELECT COUNT(*) FROM ActualStoreUniverse au WHERE NOT EXISTS (SELECT 1 FROM TargetStores ts WHERE ts.Store=au.Store)) AS ExcludedActualStoreCount
FROM TargetRows t
LEFT JOIN ActualRows a ON a.PeriodStart=t.PeriodStart AND a.Store=t.Store
CROSS JOIN LatestActual l
ORDER BY t.PeriodStart, t.Department, t.Operator, t.Store
"""

_cache_lock = threading.Lock()
_raw_cache: dict[str, tuple[str, list[dict]]] = {}
_refreshing_years: set[str] = set()


def validate_fiscal_year(value):
    fiscal_year = str(value or "").strip()
    match = FISCAL_YEAR_PATTERN.fullmatch(fiscal_year)
    if not match or int(match.group("end")) != int(match.group("start")) + 1:
        raise ValueError("财年格式必须为连续年份，例如 2026-2027")
    return fiscal_year


def _number(value):
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _iso_date(value):
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value or "")[:10]


def _month_key(value):
    return _iso_date(value)[:7]


def _month_end(month):
    year, month_number = (int(value) for value in month.split("-"))
    return f"{month}-{monthrange(year, month_number)[1]:02d}"


def _display_department(value):
    source = str(value or "").strip()
    return SOURCE_TO_DISPLAY_DEPARTMENT.get(source, source)


def _quarter_options(months):
    options = []
    for index in range(0, len(months), 3):
        quarter_months = months[index:index + 3]
        if not quarter_months:
            continue
        options.append({
            "value": f"Q{(index // 3) + 1}",
            "label": f"财年Q{(index // 3) + 1} · {quarter_months[0]} 至 {quarter_months[-1]}",
            "months": quarter_months,
        })
    return options


def _cache_month():
    return datetime.now().strftime("%Y-%m")


def _cache_path(fiscal_year):
    safe_year = validate_fiscal_year(fiscal_year)
    return CACHE_DIRECTORY / f"fiscal-overview-{safe_year}.json"


def _json_ready_row(row):
    normalized = {}
    for key, value in dict(row).items():
        if isinstance(value, Decimal):
            normalized[key] = float(value)
        elif isinstance(value, (date, datetime)):
            normalized[key] = value.strftime("%Y-%m-%d")
        else:
            normalized[key] = value
    return normalized


def _read_disk_cache(fiscal_year):
    try:
        with _cache_path(fiscal_year).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("version") != CACHE_VERSION
        or payload.get("fiscalYear") != fiscal_year
        or not isinstance(payload.get("rows"), list)
    ):
        return None
    return str(payload.get("cacheMonth") or ""), [dict(row) for row in payload["rows"] if isinstance(row, dict)]


def _write_disk_cache(fiscal_year, cache_month, rows):
    path = _cache_path(fiscal_year)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "version": CACHE_VERSION,
        "fiscalYear": fiscal_year,
        "cacheMonth": cache_month,
        "refreshedAt": datetime.now().isoformat(timespec="seconds"),
        "rows": [_json_ready_row(row) for row in rows],
    }
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary_path, path)


def _query_raw_rows(fiscal_year):
    # This runs only in the daily snapshot job. Allow the heavier fiscal query
    # to finish without affecting page-load latency, which now reads JSON only.
    connection = pytds.connect(**sql_server_config(), timeout=180)
    try:
        cursor = connection.cursor()
        cursor.execute(FISCAL_OVERVIEW_SQL, (fiscal_year,))
        columns = [column[0] for column in cursor.description]
        return [_json_ready_row(dict(zip(columns, row))) for row in (cursor.fetchall() or [])]
    finally:
        connection.close()


def _refresh_month_cache(fiscal_year, cache_month):
    try:
        rows = _query_raw_rows(fiscal_year)
        _write_disk_cache(fiscal_year, cache_month, rows)
        with _cache_lock:
            _raw_cache[fiscal_year] = (cache_month, rows)
    except Exception:
        logger.exception("Failed to refresh fiscal overview monthly cache for %s", fiscal_year)
    finally:
        with _cache_lock:
            _refreshing_years.discard(fiscal_year)


def _start_background_refresh(fiscal_year, cache_month):
    with _cache_lock:
        if fiscal_year in _refreshing_years:
            return
        _refreshing_years.add(fiscal_year)
    worker = threading.Thread(
        target=_refresh_month_cache,
        args=(fiscal_year, cache_month),
        name=f"fiscal-overview-{fiscal_year}",
        daemon=True,
    )
    worker.start()


def _fetch_raw_rows(fiscal_year, force=False):
    current_month = _cache_month()
    if not force:
        with _cache_lock:
            cached = _raw_cache.get(fiscal_year)
        if cached and cached[0] == current_month:
            return [dict(row) for row in cached[1]]

        disk_cache = _read_disk_cache(fiscal_year)
        if disk_cache:
            cached_month, rows = disk_cache
            with _cache_lock:
                _raw_cache[fiscal_year] = (cached_month, rows)
            if cached_month != current_month:
                _start_background_refresh(fiscal_year, current_month)
            return [dict(row) for row in rows]

    rows = _query_raw_rows(fiscal_year)
    _write_disk_cache(fiscal_year, current_month, rows)
    with _cache_lock:
        _raw_cache[fiscal_year] = (current_month, rows)
    return [dict(row) for row in rows]


def _store_sort_key(value):
    text = str(value or "").strip()
    try:
        return (0, int(text))
    except (TypeError, ValueError):
        return (1, text)


def _display_store(value):
    text = str(value or "").strip() or "未分配"
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text if text == "未分配" else f"{text}号店"


def _metric_store_keys(rows):
    """Return stores represented by the performance data used for the metrics."""
    has_explicit_membership = any("IsMetricStore" in row for row in rows)
    if has_explicit_membership:
        return {
            str(row.get("Store") or "").strip()
            for row in rows
            if _number(row.get("IsMetricStore")) > 0 and str(row.get("Store") or "").strip()
        }
    return {
        str(row.get("Store") or "").strip()
        for row in rows
        if _number(row.get("Actual")) != 0 and str(row.get("Store") or "").strip()
    }


def _target_progress_factor(month, latest_date):
    if not month or not latest_date or month != latest_date[:7]:
        return 1.0
    try:
        year, month_number = [int(value) for value in month.split("-", 1)]
        elapsed_days = int(latest_date[8:10])
        total_days = monthrange(year, month_number)[1]
    except (TypeError, ValueError):
        return 1.0
    return min(max(elapsed_days / total_days, 0.0), 1.0)


def _summarize(rows, key_name, label_getter, selected_months, target_weights, amounts_visible, metric_stores):
    selected_months = set(selected_months)
    groups = defaultdict(lambda: {"full_target": 0.0, "ytd_target": 0.0, "actual": 0.0, "stores": set()})
    for row in rows:
        key = str(row.get(key_name) or "未分配").strip() or "未分配"
        group = groups[key]
        target = _number(row.get("Target"))
        actual = _number(row.get("Actual"))
        group["full_target"] += target
        row_month = _month_key(row.get("PeriodStart"))
        if row_month in selected_months:
            group["ytd_target"] += target * target_weights.get(row_month, 1.0)
            group["actual"] += actual
        store = str(row.get("Store") or "").strip()
        if store and store in metric_stores:
            group["stores"].add(store)

    ranked = []
    for key, values in groups.items():
        store_names = sorted(values["stores"], key=_store_sort_key)
        achievement = values["actual"] / values["ytd_target"] if values["ytd_target"] else None
        gap_rate = (
            (values["ytd_target"] - values["actual"]) / values["ytd_target"]
            if values["ytd_target"] else None
        )
        ranked.append({
            "key": key,
            "name": label_getter(key),
            "stores": len(store_names),
            "storeNames": [f"{store}号店" for store in store_names],
            "fullYearTarget": values["full_target"] if amounts_visible else None,
            "ytdTarget": values["ytd_target"] if amounts_visible else None,
            "actual": values["actual"] if amounts_visible else None,
            "achievementRate": achievement,
            "gap": (values["ytd_target"] - values["actual"]) if amounts_visible else None,
            "gapRate": gap_rate,
        })
    ranked.sort(
        key=lambda row: (
            row["achievementRate"] is not None,
            row["achievementRate"] or 0,
            groups[row["key"]]["actual"],
        ),
        reverse=True,
    )
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
    return ranked


def shape_fiscal_overview(rows, fiscal_year, scope, filters=None):
    fiscal_year = validate_fiscal_year(fiscal_year)
    filters = filters or {}
    source_rows = list(rows or [])
    role = str((scope or {}).get("role") or "ratio_viewer").strip()
    scope_department = str((scope or {}).get("department") or "").strip()
    source_department = DISPLAY_TO_SOURCE_DEPARTMENT.get(scope_department, scope_department)
    scope_operator = str((scope or {}).get("operator") or "").strip()
    amounts_visible = bool((scope or {}).get("canViewAmounts"))

    permitted_rows = []
    for row in source_rows:
        department = str(row.get("Department") or "").strip()
        operator = str(row.get("Operator") or "").strip()
        if role in {"department_leader", "member"} and source_department and department != source_department:
            continue
        if role == "member" and scope_operator and operator != scope_operator:
            continue
        permitted_rows.append(row)

    department_order = {name: index for index, name in enumerate(DEPARTMENT_DISPLAY_ORDER)}
    available_departments = sorted(
        {_display_department(row.get("Department")) for row in permitted_rows if row.get("Department")},
        key=lambda name: (department_order.get(name, len(department_order)), name),
    )
    requested_department = str(filters.get("department") or "").strip()
    if requested_department and requested_department not in available_departments:
        raise ValueError("部门筛选超出当前用户的权限范围")
    filtered_rows = [
        row for row in permitted_rows
        if not requested_department or _display_department(row.get("Department")) == requested_department
    ]

    latest_date = max((_iso_date(row.get("LatestActualDate")) for row in permitted_rows), default="")
    latest_month = latest_date[:7] if latest_date else "0000-00"
    company_latest_date = max((_iso_date(row.get("LatestActualDate")) for row in source_rows), default="")
    company_latest_month = company_latest_date[:7] if company_latest_date else "0000-00"
    company_full_target = sum(_number(row.get("Target")) for row in source_rows)
    company_annual_actual = sum(
        _number(row.get("Actual"))
        for row in source_rows
        if _month_key(row.get("PeriodStart")) <= company_latest_month
    )
    company_fiscal_achievement = (
        company_annual_actual / company_full_target if company_full_target else None
    )
    all_months = sorted({_month_key(row.get("PeriodStart")) for row in permitted_rows if row.get("PeriodStart")})
    elapsed_months = [month for month in all_months if month <= latest_month]
    quarter_options = [
        option for option in _quarter_options(all_months)
        if any(month in elapsed_months for month in option["months"])
    ]

    period_type = str(filters.get("periodType") or "annual").strip().lower()
    if period_type not in PERIOD_TYPES:
        raise ValueError("period_type 仅支持 annual、quarter 或 month")
    requested_period = str(filters.get("period") or "").strip()
    period_options = []
    if period_type == "annual":
        period_key = fiscal_year
        period_label = f"{fiscal_year} 财年累计"
        display_months = all_months
        selected_months = elapsed_months
    elif period_type == "quarter":
        period_options = [{"value": option["value"], "label": option["label"]} for option in quarter_options]
        default_quarter = next(
            (option["value"] for option in reversed(quarter_options) if latest_month in option["months"]),
            quarter_options[-1]["value"] if quarter_options else "",
        )
        period_key = requested_period or default_quarter
        selected_option = next((option for option in quarter_options if option["value"] == period_key), None)
        if not selected_option:
            raise ValueError("季度筛选不在当前财年的可用范围内")
        period_label = selected_option["label"]
        display_months = selected_option["months"]
        selected_months = [month for month in display_months if month <= latest_month]
    else:
        period_options = [
            {"value": month, "label": f"{month[:4]}年{int(month[5:7])}月"}
            for month in elapsed_months
        ]
        period_key = requested_period or (elapsed_months[-1] if elapsed_months else "")
        if not MONTH_PATTERN.fullmatch(period_key) or period_key not in elapsed_months:
            raise ValueError("月度筛选不在当前财年的可用范围内")
        period_label = f"{period_key[:4]}年{int(period_key[5:7])}月"
        display_months = [period_key]
        selected_months = [period_key]

    selected_month_set = set(selected_months)
    display_month_set = set(display_months)
    annual_month_set = set(elapsed_months)
    target_weights = {
        month: 1.0 if period_type == "month" else _target_progress_factor(month, latest_date)
        for month in selected_months
    }
    month_groups = defaultdict(lambda: {"target": 0.0, "actual": 0.0})
    full_target = period_target = selected_target = selected_actual = annual_actual = 0.0
    elapsed_stores = set()
    active_stores = set()
    for row in filtered_rows:
        month = _month_key(row.get("PeriodStart"))
        target = _number(row.get("Target"))
        row_actual = _number(row.get("Actual"))
        full_target += target
        month_groups[month]["target"] += target
        month_groups[month]["actual"] += row_actual
        if month in display_month_set:
            period_target += target
        if month in annual_month_set:
            annual_actual += row_actual
        if month in selected_month_set:
            selected_target += target * target_weights.get(month, 1.0)
            selected_actual += row_actual
            store = int(row.get("Store") or 0)
            if store:
                elapsed_stores.add(store)
                if row_actual:
                    active_stores.add(store)

    running_target = running_target_to_date = running_actual = 0.0
    monthly = []
    for month in display_months:
        target = month_groups[month]["target"]
        month_actual = month_groups[month]["actual"] if month <= latest_month else None
        target_to_date = (
            target * target_weights.get(month, _target_progress_factor(month, latest_date))
            if month_actual is not None else None
        )
        running_target += target
        if month_actual is not None:
            running_actual += month_actual
            running_target_to_date += target_to_date or 0.0
        monthly.append({
            "period": month,
            "target": target if amounts_visible else None,
            "targetToDate": target_to_date if amounts_visible else None,
            "actual": month_actual if amounts_visible else None,
            "cumulativeTarget": running_target if amounts_visible else None,
            "cumulativeTargetToDate": (
                running_target_to_date if amounts_visible and month_actual is not None else None
            ),
            "cumulativeActual": running_actual if amounts_visible and month_actual is not None else None,
            "achievementRate": (
                month_actual / target_to_date
                if month_actual is not None and target_to_date else None
            ),
        })

    metric_stores = _metric_store_keys(filtered_rows)
    departments = _summarize(
        filtered_rows,
        "Department",
        _display_department,
        selected_months,
        target_weights,
        amounts_visible,
        metric_stores,
    )
    people = _summarize(
        filtered_rows,
        "Operator",
        lambda value: value,
        selected_months,
        target_weights,
        amounts_visible,
        metric_stores,
    )
    store_source_rows = [
        row for row in filtered_rows
        if str(row.get("Store") or "").strip() in metric_stores
    ]
    stores = _summarize(
        store_source_rows,
        "Store",
        _display_store,
        selected_months,
        target_weights,
        amounts_visible,
        metric_stores,
    )
    department_by_source = {
        str(row.get("Department") or "").strip(): _display_department(row.get("Department"))
        for row in filtered_rows
    }
    operator_department = {}
    for row in filtered_rows:
        operator = str(row.get("Operator") or "未分配").strip() or "未分配"
        source = str(row.get("Department") or "").strip()
        operator_department.setdefault(operator, department_by_source.get(source, source))
    for row in people:
        row["department"] = operator_department.get(row["key"], "")

    store_ownership = {}
    selected_store_rows = [
        row for row in store_source_rows
        if _month_key(row.get("PeriodStart")) in selected_month_set
    ]
    ownership_source_rows = selected_store_rows or store_source_rows
    for source_row in sorted(ownership_source_rows, key=lambda row: _month_key(row.get("PeriodStart"))):
        store_key = str(source_row.get("Store") or "").strip()
        store_ownership[store_key] = {
            "operator": str(source_row.get("Operator") or "未分配").strip() or "未分配",
            "department": _display_department(source_row.get("Department")),
        }
    for row in stores:
        ownership = store_ownership.get(row["key"], {})
        row["operator"] = ownership.get("operator", "未分配")
        row["department"] = ownership.get("department", "")

    achievement = selected_actual / selected_target if selected_target else None
    period_completion = selected_actual / period_target if period_target else None
    annual_progress = annual_actual / full_target if full_target else None
    gap_rate = (selected_target - selected_actual) / selected_target if selected_target else None
    period_remaining_rate = (
        (period_target - selected_actual) / period_target if period_target else None
    )
    remaining_rate = (full_target - annual_actual) / full_target if full_target else None
    first_row = filtered_rows[0] if filtered_rows else {}
    selected_latest_month = selected_months[-1] if selected_months else ""
    selected_latest_date = (
        latest_date if selected_latest_month == latest_month
        else _month_end(selected_latest_month) if selected_latest_month
        else ""
    )
    selected_target_factor = target_weights.get(selected_latest_month, 1.0)
    target_prorated = bool(
        selected_latest_month
        and selected_latest_month == latest_month
        and selected_target_factor < 1.0
    )
    target_elapsed_days = int(selected_latest_date[8:10]) if target_prorated else None
    target_month_days = (
        monthrange(int(selected_latest_month[:4]), int(selected_latest_month[5:7]))[1]
        if target_prorated else None
    )
    return {
        "fiscalYear": fiscal_year,
        "scope": {
            "role": role,
            "department": scope_department or None,
            "operator": scope_operator or None,
            "canViewAmounts": amounts_visible,
        },
        "filters": {
            "department": requested_department or None,
            "departments": available_departments,
            "periodType": period_type,
            "period": period_key,
            "periodLabel": period_label,
            "periodOptions": period_options,
        },
        "period": {
            "start": f"{display_months[0]}-01" if display_months else None,
            "end": f"{display_months[-1]}-01" if display_months else None,
            "latestActualDate": selected_latest_date or None,
            "sourceLatestActualDate": latest_date or None,
            "elapsedMonths": len(selected_months),
            "totalMonths": len(display_months),
            "targetProrated": target_prorated,
            "targetElapsedDays": target_elapsed_days,
            "targetMonthDays": target_month_days,
        },
        "overall": {
            "fullYearTarget": full_target if amounts_visible else None,
            "periodTarget": period_target if amounts_visible else None,
            "ytdTarget": selected_target if amounts_visible else None,
            "actual": selected_actual if amounts_visible else None,
            "achievementRate": achievement,
            "periodCompletionRate": period_completion,
            "annualProgressRate": annual_progress,
            "companyFiscalAchievementRate": company_fiscal_achievement,
            "gap": (selected_target - selected_actual) if amounts_visible else None,
            "gapRate": gap_rate,
            "periodRemaining": (period_target - selected_actual) if amounts_visible else None,
            "periodRemainingRate": period_remaining_rate,
            "remainingToAnnual": (full_target - annual_actual) if amounts_visible else None,
            "remainingRate": remaining_rate,
        },
        "monthly": monthly,
        "departments": departments,
        "stores": stores,
        "people": people,
        "quality": {
            "targetRows": len(filtered_rows),
            "targetStores": len({int(row.get("Store") or 0) for row in filtered_rows if row.get("Store")}),
            "storesWithActual": len(active_stores),
            "storesWithoutActual": len(elapsed_stores - active_stores),
            "matchedStoreCount": int(first_row.get("MatchedStoreCount") or 0),
            "excludedActualStoreCount": int(first_row.get("ExcludedActualStoreCount") or 0),
        },
        "source": {
            "target": "dbo.v_ZhiBiao.ZhiBiao",
            "actual": "dbo.LiRun.XiaoShouE",
            "join": "Dian + calendar month",
            "fetchedAt": datetime.now().isoformat(timespec="seconds"),
        },
    }


def load_fiscal_overview(fiscal_year, scope, force=False, filters=None):
    fiscal_year = validate_fiscal_year(fiscal_year)
    return shape_fiscal_overview(
        _fetch_raw_rows(fiscal_year, force=force),
        fiscal_year,
        scope,
        filters=filters,
    )


def refresh_fiscal_overview_snapshot(fiscal_year="2026-2027"):
    """Refresh the durable monthly snapshot and return lightweight run metadata."""
    fiscal_year = validate_fiscal_year(fiscal_year)
    rows = _fetch_raw_rows(fiscal_year, force=True)
    return {
        "fiscalYear": fiscal_year,
        "rowCount": len(rows),
        "cachePath": str(_cache_path(fiscal_year)),
        "refreshedAt": datetime.now().isoformat(timespec="seconds"),
    }
