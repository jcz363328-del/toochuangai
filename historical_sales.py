"""AI 部历史销售额同期曲线。"""

from datetime import date, timedelta
from typing import Any

from flask import Blueprint, jsonify, render_template, request

from bjc import sf_db
from department_permissions import require_permission


historical_sales_bp = Blueprint("historical_sales", __name__)
PERMISSION_KEY = "historical_sales"
MAX_RANGE_DAYS = 366


def _parse_range(start_text: str, end_text: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except (TypeError, ValueError):
        raise ValueError("日期格式无效，请使用 YYYY-MM-DD")
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    if end > date.today():
        raise ValueError("结束日期不能晚于今天")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError("单次查询最多支持 366 天")
    return start, end


def _previous_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:  # 2 月 29 日在非闰年对齐到 2 月 28 日
        return value.replace(year=value.year - 1, day=28)


def _query_daily_sales(start: date, end: date) -> dict[date, float]:
    sql = f"""
SELECT RiQi, SUM(ISNULL(CONVERT(decimal(28, 4), JinE), 0)) AS XiaoShouE
FROM dbo.GuangGao
WHERE RiQi >= '{start.isoformat()}' AND RiQi < '{(end + timedelta(days=1)).isoformat()}'
GROUP BY RiQi
ORDER BY RiQi
"""
    rows = sf_db(sql) or []
    result: dict[date, float] = {}
    for row in rows:
        raw_date, raw_value = row
        day = raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date)[:10])
        result[day] = float(raw_value or 0)
    return result


def build_comparison(start: date, end: date) -> dict[str, Any]:
    previous_start, previous_end = _previous_year(start), _previous_year(end)
    current = _query_daily_sales(start, end)
    previous = _query_daily_sales(previous_start, previous_end)
    points = []
    current_total = previous_total = 0.0
    for offset in range((end - start).days + 1):
        current_day = start + timedelta(days=offset)
        previous_day = previous_start + timedelta(days=offset)
        current_value = current.get(current_day, 0.0)
        previous_value = previous.get(previous_day, 0.0)
        current_total += current_value
        previous_total += previous_value
        points.append({
            "date": current_day.isoformat(),
            "previous_date": previous_day.isoformat(),
            "current": round(current_value, 2),
            "previous": round(previous_value, 2),
        })
    growth = None if previous_total == 0 else (current_total / previous_total - 1)
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "previous_start": previous_start.isoformat(), "previous_end": previous_end.isoformat(),
        "current_total": round(current_total, 2), "previous_total": round(previous_total, 2),
        "growth": growth, "points": points,
    }


@historical_sales_bp.get("/ai/historical-sales")
@require_permission(PERMISSION_KEY)
def page():
    today = date.today()
    return render_template(
        "historical_sales.html",
        default_start=(today - timedelta(days=29)).isoformat(),
        default_end=today.isoformat(),
    )


@historical_sales_bp.get("/api/ai/historical-sales")
@require_permission(PERMISSION_KEY)
def query():
    try:
        start, end = _parse_range(request.args.get("start", ""), request.args.get("end", ""))
        return jsonify({"success": True, "data": build_comparison(start, end)})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "销售数据查询失败，请稍后重试"}), 503
