"""Developer-owned product sales for store 37, based on the legacy Excel button."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytds
from flask import Blueprint, g, has_request_context, jsonify, render_template, request, session

from department_permissions import require_permission
from secret_settings import sql_server_config


developer_product_sales_bp = Blueprint("developer_product_sales", __name__)
PERMISSION_KEY = "ai_dept"
CUMULATIVE_START = date(2024, 6, 1)
PROGRESS_TARGET = 500_000
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


def _developer_name() -> str:
    request_state = getattr(g, "permission_debug_state", None) if has_request_context() else None
    switched_name = (
        str(request_state.get("user_name") or "").strip()
        if isinstance(request_state, dict)
        else ""
    )
    return str(
        switched_name
        or session.get("permission_debug_user_name")
        or session.get("feishu_user_name")
        or ""
    ).strip()


def _parse_store(value: str) -> int:
    try:
        store = int(str(value or "").strip())
    except (TypeError, ValueError):
        raise ValueError("店铺号必须为正整数")
    if store <= 0 or store > 999999:
        raise ValueError("店铺号必须为正整数")
    return store


def _query_sales(developer: str, store: int, start: date, end: date) -> dict[str, Any]:
    next_day = end + timedelta(days=1)
    params = {
        "developer": developer,
        "store": store,
        "start": start,
        "next_day": next_day,
        "cumulative_start": CUMULATIVE_START,
    }
    filter_sql = """
FROM dbo.v_MaoLiLv AS ml
WHERE ml.RiQi >= %(start)s AND ml.RiQi < %(next_day)s
  AND ml.Dian = %(store)s
  AND EXISTS (
      SELECT 1 FROM dbo.ZiDian AS zd
      WHERE zd.SKU = ml.SKU AND LTRIM(RTRIM(zd.KaiFaRen)) = %(developer)s
  )
"""
    summary_sql = """
SELECT
    ISNULL(SUM(CONVERT(decimal(28, 4), ml.XiaoShouE)), 0),
    ISNULL(SUM(CONVERT(decimal(28, 4), ml.MaoLiRun)), 0),
    CASE WHEN ISNULL(SUM(CONVERT(decimal(28, 4), ml.MaoLiLvFenMu)), 0) = 0 THEN NULL
         ELSE SUM(CONVERT(decimal(28, 4), ml.MaoLiRun)) /
              SUM(CONVERT(decimal(28, 4), ml.MaoLiLvFenMu)) END
""" + filter_sql
    daily_sql = """
SELECT
    CONVERT(date, ml.RiQi),
    ISNULL(SUM(CONVERT(decimal(28, 4), ml.XiaoShouE)), 0),
    ISNULL(SUM(CONVERT(decimal(28, 4), ml.MaoLiRun)), 0),
    CASE WHEN ISNULL(SUM(CONVERT(decimal(28, 4), ml.MaoLiLvFenMu)), 0) = 0 THEN NULL
         ELSE SUM(CONVERT(decimal(28, 4), ml.MaoLiRun)) /
              SUM(CONVERT(decimal(28, 4), ml.MaoLiLvFenMu)) END
""" + filter_sql + " GROUP BY CONVERT(date, ml.RiQi) ORDER BY CONVERT(date, ml.RiQi)"
    cumulative_sql = """
SELECT ISNULL(SUM(CONVERT(decimal(28, 4), lr.XiaoShouE)), 0)
FROM dbo.LiRun AS lr
WHERE lr.RiQi >= %(cumulative_start)s
  AND lr.Dian = %(store)s
  AND EXISTS (
      SELECT 1 FROM dbo.ZiDian AS zd
      WHERE zd.SKU = lr.SKU AND LTRIM(RTRIM(zd.KaiFaRen)) = %(developer)s
  )
"""

    with pytds.connect(**sql_server_config()) as connection:
        cursor = connection.cursor()
        cursor.execute(summary_sql, params)
        summary = cursor.fetchone() or (0, 0, None)
        cursor.execute(daily_sql, params)
        daily_rows = cursor.fetchall() or []
        cursor.execute(cumulative_sql, params)
        cumulative_row = cursor.fetchone() or (0,)

    cumulative_sales = float(cumulative_row[0] or 0)
    return {
        "developer": developer,
        "store": store,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "sales": round(float(summary[0] or 0), 2),
        "profit": round(float(summary[1] or 0), 2),
        "margin": None if summary[2] is None else float(summary[2]),
        "cumulative_start": CUMULATIVE_START.isoformat(),
        "cumulative_sales": round(cumulative_sales, 2),
        "progress_target": PROGRESS_TARGET,
        "progress": cumulative_sales / PROGRESS_TARGET,
        "daily": [
            {
                "date": (row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0])[:10])).isoformat(),
                "sales": round(float(row[1] or 0), 2),
                "profit": round(float(row[2] or 0), 2),
                "margin": None if row[3] is None else float(row[3]),
            }
            for row in daily_rows
        ],
    }


@developer_product_sales_bp.get("/ai/developer-product-sales")
@require_permission(PERMISSION_KEY)
def page():
    today = date.today()
    return render_template(
        "developer_product_sales.html",
        developer=_developer_name(),
        default_start=(today - timedelta(days=29)).isoformat(),
        default_end=today.isoformat(),
    )


@developer_product_sales_bp.get("/api/ai/developer-product-sales")
@require_permission(PERMISSION_KEY)
def query():
    developer = _developer_name()
    if not developer:
        return jsonify({"success": False, "message": "未获取到当前飞书用户名，请重新登录"}), 401
    try:
        start, end = _parse_range(request.args.get("start", ""), request.args.get("end", ""))
        store = _parse_store(request.args.get("store", ""))
        return jsonify({"success": True, "data": _query_sales(developer, store, start, end)})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "产品销售数据查询失败，请稍后重试"}), 503
