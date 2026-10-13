"""AI 部组别月度经营查询。"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any

from flask import Blueprint, jsonify, render_template, request

from bjc import sf_db
from department_permissions import require_permission


ai_group_performance_bp = Blueprint("ai_group_performance", __name__)
PERMISSION_KEY = "ai_group_performance"


def _month_bounds(value: str) -> tuple[date, date, date]:
    try:
        current = date.fromisoformat(f"{value}-01")
    except (TypeError, ValueError):
        raise ValueError("月份格式无效，请使用 YYYY-MM")
    if current > date.today().replace(day=1):
        raise ValueError("不能查询未来月份")
    previous = date(current.year - (current.month == 1), 12 if current.month == 1 else current.month - 1, 1)
    following = date(current.year + (current.month == 12), 1 if current.month == 12 else current.month + 1, 1)
    return previous, current, following


def _sql_text(value: str) -> str:
    return "N'" + value.replace("'", "''") + "'"


def load_groups() -> list[str]:
    rows = sf_db(
        "SELECT DISTINCT LTRIM(RTRIM(ZuZhang)) FROM dbo.v_PinPaiDianPu "
        "WHERE NULLIF(LTRIM(RTRIM(ZuZhang)), N'') IS NOT NULL ORDER BY 1"
    ) or []
    return [str(row[0] if isinstance(row, (tuple, list)) else row).strip() for row in rows]


def build_query(month: str, group: str, detail: bool = False) -> str:
    previous, current, following = _month_bounds(month)
    group_literal = _sql_text(group)
    prev_label, curr_label = f"{previous.month}月", f"{current.month}月"
    ctes = f"""
DECLARE @PrevStart date = '{previous.isoformat()}';
DECLARE @CurrStart date = '{current.isoformat()}';
DECLARE @NextStart date = '{following.isoformat()}';
WITH Stores AS (
 SELECT LTRIM(RTRIM(Dian)) Dian, MAX(DianMing) DianMing, MAX(YunYing) YunYing
 FROM dbo.v_PinPaiDianPu WHERE LTRIM(RTRIM(ZuZhang)) = {group_literal}
 GROUP BY LTRIM(RTRIM(Dian))
), SiteSales AS (
 SELECT LTRIM(RTRIM(g.Dian)) Dian, ISNULL(NULLIF(LTRIM(RTRIM(g.Guo)),N''),N'未标注站点') ZhanDian,
 SUM(CASE WHEN g.RiQi>=@PrevStart AND g.RiQi<@CurrStart THEN ISNULL(CONVERT(decimal(28,4),g.JinE),0) ELSE 0 END) PrevSales,
 SUM(CASE WHEN g.RiQi>=@CurrStart AND g.RiQi<@NextStart THEN ISNULL(CONVERT(decimal(28,4),g.JinE),0) ELSE 0 END) CurrSales
 FROM dbo.v_All_GuangGao g INNER JOIN Stores s ON s.Dian=LTRIM(RTRIM(g.Dian))
 WHERE g.RiQi>=@PrevStart AND g.RiQi<@NextStart
 GROUP BY LTRIM(RTRIM(g.Dian)),ISNULL(NULLIF(LTRIM(RTRIM(g.Guo)),N''),N'未标注站点')
), SiteProfit AS (
 SELECT LTRIM(RTRIM(l.Dian)) Dian, ISNULL(NULLIF(LTRIM(RTRIM(l.Guo)),N''),N'未标注站点') ZhanDian,
 SUM(CASE WHEN l.RiQi>=@PrevStart AND l.RiQi<@CurrStart THEN ISNULL(CONVERT(decimal(28,4),l.MaoLiRun),0) ELSE 0 END) PrevProfit,
 SUM(CASE WHEN l.RiQi>=@CurrStart AND l.RiQi<@NextStart THEN ISNULL(CONVERT(decimal(28,4),l.MaoLiRun),0) ELSE 0 END) CurrProfit,
 SUM(CASE WHEN l.RiQi>=@CurrStart AND l.RiQi<@NextStart THEN ISNULL(CONVERT(decimal(28,4),l.XiaoShouE),0)+ISNULL(CONVERT(decimal(28,4),l.MaiJiaYunFei),0)+ISNULL(CONVERT(decimal(28,4),l.KuCunPeiChang),0)+ISNULL(CONVERT(decimal(28,4),l.CuXiaoFei),0) ELSE 0 END) CurrMarginBase
 FROM dbo.v_All_LiRun l INNER JOIN Stores s ON s.Dian=LTRIM(RTRIM(l.Dian))
 WHERE l.RiQi>=@PrevStart AND l.RiQi<@NextStart
 GROUP BY LTRIM(RTRIM(l.Dian)),ISNULL(NULLIF(LTRIM(RTRIM(l.Guo)),N''),N'未标注站点')
), SiteData AS (
 SELECT COALESCE(a.Dian,p.Dian) Dian,COALESCE(a.ZhanDian,p.ZhanDian) ZhanDian,
 ISNULL(a.PrevSales,0) PrevSales,ISNULL(a.CurrSales,0) CurrSales,
 ISNULL(p.PrevProfit,0) PrevProfit,ISNULL(p.CurrProfit,0) CurrProfit,ISNULL(p.CurrMarginBase,0) CurrMarginBase
 FROM SiteSales a FULL OUTER JOIN SiteProfit p ON p.Dian=a.Dian AND p.ZhanDian=a.ZhanDian
), StoreData AS (
 SELECT Dian,SUM(PrevSales) PrevSales,SUM(CurrSales) CurrSales,SUM(PrevProfit) PrevProfit,SUM(CurrProfit) CurrProfit,SUM(CurrMarginBase) CurrMarginBase
 FROM SiteData GROUP BY Dian
), Targets AS (
 SELECT LTRIM(RTRIM(z.Dian)) Dian,SUM(ISNULL(CONVERT(decimal(28,4),z.ZhiBiao),0)) CurrTarget
 FROM dbo.v_ZhiBiao z INNER JOIN Stores s ON s.Dian=LTRIM(RTRIM(z.Dian))
 WHERE z.Nian={current.year} AND z.Yue={current.month} GROUP BY LTRIM(RTRIM(z.Dian))
)
"""
    if detail:
        return ctes + f"""SELECT s.Dian AS [店铺],s.DianMing AS [店铺名称],s.YunYing AS [运营],x.ZhanDian AS [站点],
 ROUND(x.PrevSales,2) AS [{prev_label}销售额],ROUND(x.CurrSales,2) AS [{curr_label}销售额],
 CASE WHEN x.PrevSales<>0 THEN ROUND(x.CurrSales/x.PrevSales-1,4) END AS [环比增长率],
 CASE WHEN x.CurrMarginBase<>0 THEN ROUND(x.CurrProfit/x.CurrMarginBase,4) END AS [{curr_label}毛利率],
 ROUND(ISNULL(t.CurrTarget,0),2) AS [店铺{curr_label}目标],
 CASE WHEN ISNULL(t.CurrTarget,0)<>0 THEN ROUND(d.CurrSales/t.CurrTarget,4) END AS [店铺达成率],
 CASE WHEN ISNULL(d.CurrSales,0)<>0 THEN ROUND(x.CurrSales/d.CurrSales,4) END AS [{curr_label}销售占店铺比重],
 ROUND(x.CurrProfit,2) AS [{curr_label}毛利润]
 FROM SiteData x INNER JOIN Stores s ON s.Dian=x.Dian LEFT JOIN StoreData d ON d.Dian=x.Dian LEFT JOIN Targets t ON t.Dian=x.Dian
 WHERE x.PrevSales<>0 OR x.CurrSales<>0 OR x.PrevProfit<>0 OR x.CurrProfit<>0 ORDER BY s.Dian,x.CurrSales DESC,x.ZhanDian"""
    return ctes + f"""SELECT s.Dian AS [店铺],s.DianMing AS [店铺名称],s.YunYing AS [运营],
 ROUND(ISNULL(d.PrevSales,0),2) AS [{prev_label}销售额],ROUND(ISNULL(d.CurrSales,0),2) AS [{curr_label}销售额],
 CASE WHEN ISNULL(d.PrevSales,0)<>0 THEN ROUND(d.CurrSales/d.PrevSales-1,4) END AS [环比增长率],
 ROUND(ISNULL(t.CurrTarget,0),2) AS [{curr_label}目标],CASE WHEN ISNULL(t.CurrTarget,0)<>0 THEN ROUND(d.CurrSales/t.CurrTarget,4) END AS [达成率],
 CASE WHEN ISNULL(d.CurrMarginBase,0)<>0 THEN ROUND(d.CurrProfit/d.CurrMarginBase,4) END AS [{curr_label}毛利率],ROUND(ISNULL(d.CurrProfit,0),2) AS [{curr_label}毛利润]
 FROM Stores s LEFT JOIN StoreData d ON d.Dian=s.Dian LEFT JOIN Targets t ON t.Dian=s.Dian ORDER BY ISNULL(d.CurrSales,0) DESC,s.Dian"""


def _rows(sql: str) -> dict[str, Any]:
    # sf_db 不返回游标描述，因此列名由查询的稳定输出顺序提供给前端。
    values = sf_db(sql) or []
    return {"rows": [list(row) if isinstance(row, (tuple, list)) else [row] for row in values]}


@ai_group_performance_bp.get("/ai/group-performance")
@require_permission(PERMISSION_KEY)
def page():
    return render_template("ai_group_performance.html", default_month=date.today().strftime("%Y-%m"))


@ai_group_performance_bp.get("/api/ai/group-performance/groups")
@require_permission(PERMISSION_KEY)
def groups():
    try:
        return jsonify({"success": True, "groups": load_groups()})
    except Exception:
        return jsonify({"success": False, "message": "组别加载失败，请稍后重试"}), 503


@ai_group_performance_bp.get("/api/ai/group-performance/query")
@require_permission(PERMISSION_KEY)
def query():
    month, group = request.args.get("month", "").strip(), request.args.get("group", "").strip()
    if not group or len(group) > 80:
        return jsonify({"success": False, "message": "请选择有效组别"}), 400
    try:
        previous, current, _ = _month_bounds(month)
        summary = _rows(build_query(month, group))
        detail = _rows(build_query(month, group, detail=True))
        summary["columns"] = ["店铺", "店铺名称", "运营", f"{previous.month}月销售额", f"{current.month}月销售额", "环比增长率", f"{current.month}月目标", "达成率", f"{current.month}月毛利率", f"{current.month}月毛利润"]
        detail["columns"] = ["店铺", "店铺名称", "运营", "站点", f"{previous.month}月销售额", f"{current.month}月销售额", "环比增长率", f"{current.month}月毛利率", f"店铺{current.month}月目标", "店铺达成率", f"{current.month}月销售占店铺比重", f"{current.month}月毛利润"]
        return jsonify({"success": True, "month": month, "group": group, "summary": summary, "detail": detail})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "查询失败，请稍后重试或联系管理员"}), 503
