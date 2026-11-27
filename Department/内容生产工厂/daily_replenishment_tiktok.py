from __future__ import annotations

import copy
import hashlib
import os
import shutil
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request, send_file, session
from openpyxl import Workbook, load_workbook

import daily_replenishment as base
from daily_replenishment_operation import (
    _current_user_name,
    _normalized_store,
    _snapshot_owner_key,
    get_store_permissions,
)
from department_permissions import require_permission
from tools import escape_sql_literal


daily_replenishment_tiktok_bp = Blueprint("daily_replenishment_tiktok", __name__)

PERMISSION_NAME = "daily_replenishment_tiktok"
SHEET_ORDER = (base.SHEET_NAME, "SKU销量", "数据源", "站点销量库存")
MAIN_SHEET = base.SHEET_NAME
DEFAULT_RECENT_DAYS = 7
DEFAULT_SAMPLE_DAYS = 30
_refresh_lock = Lock()
_snapshot_cache_lock = Lock()
_snapshot_cache: dict[str, tuple[int, dict[str, Any]]] = {}
_refresh_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="daily-replenishment-tiktok")
_refresh_jobs_lock = Lock()
_refresh_jobs: dict[str, dict[str, Any]] = {}


def get_output_dir(*, create: bool = False) -> Path:
    configured = current_app.config.get("DAILY_REPLENISHMENT_TIKTOK_OUTPUT_DIR")
    raw = configured or os.environ.get("DAILY_REPLENISHMENT_TIKTOK_OUTPUT_DIR")
    output_dir = Path(str(raw)).expanduser() if raw else base.get_output_dir() / "_日常补货TikTok"
    if create:
        output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_snapshot_path(snapshot_date: date | None = None, *, user_name: str = "") -> Path:
    target = snapshot_date or date.today()
    owner = _snapshot_owner_key(user_name)
    return get_output_dir() / "_每日快照" / owner / f"{target:%Y%m%d}智能补货中心-Tiktok.xlsx"


def get_today_snapshot(*, user_name: str = "") -> Path | None:
    path = get_snapshot_path(user_name=user_name)
    return path if path.is_file() else None


def get_shared_today_snapshot() -> Path | None:
    root = get_output_dir() / "_每日快照"
    if not root.is_dir():
        return None
    filename = f"{date.today():%Y%m%d}智能补货中心-Tiktok.xlsx"
    candidates = [path for path in root.rglob(filename) if path.is_file()]
    return max(candidates, key=lambda path: (path.stat().st_size, path.stat().st_mtime_ns)) if candidates else None


def _resolve_snapshot_for_user(user_name: str) -> tuple[Path | None, bool]:
    own = get_today_snapshot(user_name=user_name)
    if own is not None:
        return own, False
    return get_shared_today_snapshot(), True


def resolve_source_path() -> Path | None:
    configured = current_app.config.get("DAILY_REPLENISHMENT_TIKTOK_SOURCE_PATH")
    raw = configured or os.environ.get("DAILY_REPLENISHMENT_TIKTOK_SOURCE_PATH")
    if raw:
        candidate = Path(str(raw)).expanduser()
        if candidate.is_file() and candidate.suffix.lower() in {".xlsx", ".xlsm"}:
            return candidate
    roots = [Path.home() / "Downloads", Path.home() / "Desktop"]
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        candidates.extend(
            path
            for path in root.glob("*日常补货*TK*.xls*")
            if path.is_file() and not path.name.startswith("~$")
        )
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(str(value or "").replace(",", "").strip())
    except (TypeError, ValueError):
        return default
    return number if number == number and abs(number) != float("inf") else default


def _compact(value: Any) -> int | float:
    number = _number(value)
    rounded = round(number)
    return int(rounded) if abs(number - rounded) < 1e-9 else round(number, 4)


def _date(value: Any) -> date | None:
    return base._coerce_date(value)


def _days(stock: Any, daily: Any) -> int:
    inventory = _number(stock)
    sales = _number(daily)
    if sales <= 0:
        return 999
    return int(round(inventory / sales))


def _settings(source: Path | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = base._read_generation_parameters(source)
    raw_days = (overrides or {}).get("recent_days")
    if raw_days in (None, ""):
        raw_days = parameters.get("最近天数", DEFAULT_RECENT_DAYS)
    try:
        recent_days = int(raw_days)
    except (TypeError, ValueError) as exc:
        raise base.DailyReplenishmentError("TikTok 最近天数必须是整数") from exc
    if not 1 <= recent_days <= 365:
        raise base.DailyReplenishmentError("TikTok 最近天数必须在 1 到 365 之间")
    raw_sample_days = parameters.get("近期发样品_天数", DEFAULT_SAMPLE_DAYS)
    if (overrides or {}).get("sample_days") not in (None, ""):
        raw_sample_days = (overrides or {}).get("sample_days")
    try:
        sample_days = int(raw_sample_days)
    except (TypeError, ValueError):
        sample_days = DEFAULT_SAMPLE_DAYS
    sample_days = max(1, min(sample_days, 365))
    raw_listing_days = (overrides or {}).get("listing_days", parameters.get("新品标黄色", 30))
    try:
        listing_days = int(raw_listing_days)
    except (TypeError, ValueError) as exc:
        raise base.DailyReplenishmentError("新品标黄色天数必须是整数") from exc
    if not 1 <= listing_days <= 365:
        raise base.DailyReplenishmentError("新品标黄色天数必须在 1 到 365 之间")
    today = date.today()
    settings = {
        "as_of_date": today,
        "recent_days": recent_days,
        "sales_start": today - timedelta(days=recent_days),
        "sales_end": today - timedelta(days=1),
        "sales_header": f"{(today - timedelta(days=recent_days)).month}.{(today - timedelta(days=recent_days)).day}到{(today - timedelta(days=1)).month}.{(today - timedelta(days=1)).day}销量",
        "sample_days": sample_days,
        "site_days": max(1, min(int(parameters.get("最近在各站点的销量和库存", 15) or 15), 365)),
        "recent_launch_days": max(1, min(int(parameters.get("最近开售", 10) or 10), 365)),
        "recent_launch_sales_days": max(1, min(int(parameters.get("最近开售_销售天数", 3) or 3), 365)),
        "new_product_days": listing_days,
        "variation_threshold": float(parameters.get("变异系数", 0.08) or 0.08),
        "low_days": int(parameters.get("可售天数标红", 30) or 30),
        "surge_multiplier": float(parameters.get("起量倍数_系数", 1.5) or 1.5),
        "parameters": parameters,
        "overdue_days": int(parameters.get("超过N天未到货", 10) or 10),
    }
    return settings


def _visible_tiktok_skus(stores: set[str], *, query_executor=base.sf_db) -> set[str]:
    if not stores:
        return set()
    literals = ",".join(f"N'{escape_sql_literal(store)}'" for store in sorted(stores))
    try:
        rows = query_executor(
            "/* daily_replenishment_tiktok:visible_skus */\n"
            "SELECT DISTINCT ZhuSKU FROM v_TK_KuCun "
            f"WHERE CONVERT(NVARCHAR(100),Dian) IN ({literals}) AND ZhuSKU IS NOT NULL"
        ) or []
    except Exception:
        rows = []
    return {str(row[0] if isinstance(row, (list, tuple)) else row or "").strip() for row in rows if str(row[0] if isinstance(row, (list, tuple)) else row or "").strip()}


def scoped_query_executor(user_name: str, *, query_executor=base.sf_db):
    access = get_store_permissions(user_name, query_executor=query_executor)
    stores = set(access["read_stores"])
    visible_skus = _visible_tiktok_skus(stores, query_executor=query_executor)
    access["visible_skus"] = visible_skus

    def execute(sql: str):
        if not stores:
            return []
        rows = list(query_executor(sql) or [])
        marker = str(sql or "")
        if "daily_replenishment_tiktok:core" in marker:
            return [row for row in rows if len(row) > 1 and _normalized_store(row[1]) in stores]
        if "daily_replenishment_tiktok:visible_skus" in marker:
            return rows
        if any(token in marker for token in (
            "daily_replenishment_tiktok:sales",
            "daily_replenishment_tiktok:sales_detail",
            "daily_replenishment_tiktok:sample",
            "daily_replenishment_tiktok:purchase_plan",
            "daily_replenishment_tiktok:aux_consumption",
            "daily_replenishment_tiktok:new_sales",
            "daily_replenishment_tiktok:site_sales_inventory",
            "daily_replenishment_tiktok:yesterday_orders",
            "daily_replenishment_tiktok:video",
            "daily_replenishment_tiktok:first_sale",
            "daily_replenishment_tiktok:notes",
            "daily_replenishment_tiktok:surge",
            "daily_replenishment_tiktok:in_transit",
            "daily_replenishment_tiktok:delivery_time",
            "daily_replenishment_tiktok:new_local",
            "daily_replenishment_tiktok:pending",
            "daily_replenishment_tiktok:clearance",
            "daily_replenishment_tiktok:ocean",
        )):
            return [row for row in rows if row and str(row[0] or "").strip() in visible_skus]
        return rows

    return execute, access


def _main_sql(settings: dict[str, Any]) -> str:
    start = settings["sales_start"].isoformat()
    end = settings["sales_end"].isoformat()
    days = float(settings["recent_days"])
    return f"""/* daily_replenishment_tiktok:core */
WITH Inventory AS (
    SELECT YunYing,Dian,ZhuSKU,
           SUM(CASE WHEN Cang='本地仓' THEN ISNULL(ShuLiang,0) ELSE 0 END) LocalStock,
           SUM(CASE WHEN Cang='美东' THEN ISNULL(ShuLiang,0)+ISNULL(ZaiTu,0) ELSE 0 END) EastStock,
           SUM(CASE WHEN Cang='美西' THEN ISNULL(ShuLiang,0)+ISNULL(ZaiTu,0) ELSE 0 END) WestStock,
           SUM(CASE WHEN Cang='FBT-US' THEN ISNULL(ShuLiang,0)+ISNULL(ZaiTu,0) ELSE 0 END) FbtUsStock,
           SUM(CASE WHEN Cang='FBT-UK' THEN ISNULL(ShuLiang,0)+ISNULL(ZaiTu,0) ELSE 0 END) FbtUkStock,
           SUM(CASE WHEN Cang='本地仓' THEN ISNULL(ZaiTu,0) ELSE 0 END) PurchaseTransit
      FROM v_TK_KuCun
     WHERE ZhuSKU IS NOT NULL AND LTRIM(RTRIM(ZhuSKU))<>''
     GROUP BY YunYing,Dian,ZhuSKU
), Sales AS (
    SELECT SKU,SUM(ISNULL(XiaoLiang,0)) SalesQty
      FROM TK_DingDan
     WHERE DingGoushijian BETWEEN '{start}' AND '{end}'
     GROUP BY SKU
), KLatest AS (
    SELECT SKU,MAX(K) KValue
      FROM TK_K
     WHERE RiQi=(SELECT MAX(RiQi) FROM TK_K)
     GROUP BY SKU
), Category AS (
    SELECT SKU,Dian,MAX(FenLei) FenLei
      FROM v_FenLei
     WHERE Dian>=80
     GROUP BY SKU,Dian
)
SELECT i.YunYing,i.Dian,ISNULL(c.FenLei,'D'),i.ZhuSKU,
       i.LocalStock,i.EastStock,i.WestStock,i.FbtUsStock,i.FbtUkStock,
       i.PurchaseTransit,ISNULL(s.SalesQty,0),ISNULL(k.KValue,0)
  FROM Inventory i
  LEFT JOIN Sales s ON s.SKU=i.ZhuSKU
  LEFT JOIN KLatest k ON k.SKU=i.ZhuSKU
  LEFT JOIN Category c ON c.SKU=i.ZhuSKU AND c.Dian=i.Dian
 ORDER BY i.Dian,i.ZhuSKU"""


def _optional(query_executor, sql: str) -> list[Any]:
    try:
        return list(query_executor(sql) or [])
    except Exception:
        return []


def generate_tiktok_dataset(source: Path | None = None, *, query_executor=base.sf_db, overrides: dict[str, Any] | None = None, user_name: str = "") -> dict[str, Any]:
    settings = _settings(source, overrides)
    try:
        core_rows = list(query_executor(_main_sql(settings)) or [])
    except Exception as exc:
        raise base.DailyReplenishmentError(f"生成 TikTok 补货表失败：{exc}") from exc

    sample_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:sample */
SELECT SKU,COUNT(*)
  FROM TK_WangHong_HeZuo
 WHERE COALESCE(FaHuoRiQi,ShouHuoRiQi) BETWEEN '{(settings['as_of_date'] - timedelta(days=settings['sample_days'])).isoformat()}' AND '{settings['as_of_date'].isoformat()}'
 GROUP BY SKU""",
    )
    purchase_plan_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:purchase_plan */
SELECT ZhuSKU,RiQi,ShuLiang,JiHuaBianHao,GongYingShang,FuZeRen,BeiZhu
  FROM CaiGouJiHua jh
  LEFT JOIN GongYingShang gys ON jh.GongYingShang=gys.ID AND gys.YorN='Y'
 WHERE ZhuangTai IN ('待审批','已完成','待采购')
   AND RiQi>='{(settings['as_of_date'] - timedelta(days=int(settings['parameters'].get('最近的采购计划', 3) or 3))).isoformat()}'
 ORDER BY RiQi""",
    )
    aux_consumption_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:aux_consumption */
SELECT FuLiao,SUM(XiaoHaoLiang)
  FROM v_FuLiaoXiaoHaoLiang_XiaoShou
 WHERE RiQi>='{(settings['as_of_date'] - timedelta(days=settings['recent_days'])).isoformat()}'
 GROUP BY FuLiao""",
    )
    new_sales_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:new_sales */
SELECT SKU,SUM(ISNULL(XiaoLiang,0))
  FROM TK_DingDan
 WHERE DingGouRiQi BETWEEN '{(settings['as_of_date'] - timedelta(days=settings['recent_launch_sales_days'] + 1)).isoformat()}' AND '{(settings['as_of_date'] - timedelta(days=2)).isoformat()}'
 GROUP BY SKU""",
    )
    site_sales_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:site_sales_inventory */
SELECT SKU,FaHuoCang,SUM(销量),SUM(库存量),SUM(在途)
  FROM (
        SELECT SKU,FaHuoCang,SUM(XiaoLiang) 销量,0 库存量,0 在途
          FROM v_TK_DingDan
         WHERE DingGouRiQi BETWEEN '{(settings['as_of_date'] - timedelta(days=settings['site_days'] + 1)).isoformat()}' AND '{(settings['as_of_date'] - timedelta(days=2)).isoformat()}'
         GROUP BY SKU,FaHuoCang
        UNION ALL
        SELECT ZhuSKU,Cang,0,SUM(ShuLiang),SUM(ZaiTu)
          FROM v_TK_KuCun
         GROUP BY ZhuSKU,Cang
  ) t
 GROUP BY SKU,FaHuoCang
 ORDER BY SKU,FaHuoCang""",
    )
    yesterday_order_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:yesterday_orders */
SELECT SKU,FaHuoCang,SUM(XiaoLiang),ROUND(SUM(DanJia*XiaoLiang)/NULLIF(SUM(XiaoLiang),0),2),COUNT(DISTINCT DanHao)
  FROM v_TK_DingDan
 WHERE DingGouRiQi='{(settings['as_of_date'] - timedelta(days=1)).isoformat()}'
 GROUP BY SKU,FaHuoCang
 ORDER BY SKU,SUM(XiaoLiang) DESC""",
    )
    daily_sales_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:sales_detail */
SELECT SKU,DingGouRiQi,SUM(ISNULL(XiaoLiang,0))
  FROM TK_DingDan
 WHERE DingGouRiQi BETWEEN '{settings['sales_start'].isoformat()}' AND '{settings['sales_end'].isoformat()}'
 GROUP BY SKU,DingGouRiQi ORDER BY SKU,DingGouRiQi""",
    )
    video_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:video */
SELECT sp.SKU,COUNT(DISTINCT zx.ShiPinID),SUM(ISNULL(zx.BoFangShu,0))
  FROM v_TK_WangHong_ShiPinShangXin_ZuiXin zx
  LEFT JOIN v_TK_HeZuoShiPin sp ON zx.ShiPinID=sp.ShiPinID
 WHERE zx.ShiPinID IN (SELECT DISTINCT ShiPinID FROM v_TK_HeZuoShiPin WHERE FaBuRiQi>='{(settings['as_of_date'] - timedelta(days=settings['sample_days'])).isoformat()}')
 GROUP BY sp.SKU""",
    )
    first_sale_rows = _optional(
        query_executor,
        "/* daily_replenishment_tiktok:first_sale */ SELECT SKU,MIN(DingGouRiQi) FROM TK_DingDan GROUP BY SKU",
    )
    note_filter = ""
    if user_name:
        note_filter = f" AND TianJiaRen LIKE N'%@{escape_sql_literal(user_name)}'"
    note_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:notes */
SELECT SKU,RiQi,BeiZhu FROM ChanPinBeiZhu WHERE YorN='Y'{note_filter} ORDER BY SKU,RiQi""",
    )
    surge_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:surge */
SELECT SKU,RiQi,XiaoLiang,ZhiQian3TianRiJun,BeiShu
  FROM QiLiang
 WHERE RiQi>='{(settings['as_of_date'] - timedelta(days=4)).isoformat()}'
   AND XiaoLiang>2 AND BeiShu>={settings['surge_multiplier']}
 ORDER BY RiQi,SKU""",
    )
    clearance_rows = _optional(query_executor, "/* daily_replenishment_tiktok:clearance */ SELECT SKU FROM QingHuo")
    ocean_rows = _optional(query_executor, "/* daily_replenishment_tiktok:ocean */ SELECT SKU FROM HaiYunSKU WHERE ZhengChang='Y'")
    pending_rows = _optional(
        query_executor,
        """/* daily_replenishment_tiktok:pending */
SELECT zd.ZhuSKU,cgd.XiaDanRiQi,cgd.DanHao,cgd.GongYingShang,
       cgd.CaiGouLiang,cgd.DaoHuoLiang,cgd.DaiDaoHuoLiang,ISNULL(gys.FuZeRen,'未定义')
  FROM CaiGouDan cgd
  LEFT JOIN ZiDian zd ON cgd.SKU=zd.SKU
  LEFT JOIN GongYingShang gys ON cgd.GongYingShang=gys.ID AND gys.YorN='Y'
 WHERE cgd.CaiGouZhuangTai='待到货' AND cgd.DaiDaoHuoLiang>0
 ORDER BY zd.ZhuSKU,cgd.XiaDanRiQi,cgd.DanHao""",
    )
    in_transit_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:in_transit */
SELECT SKU,CASE ShouHuoCang WHEN 'FBT虚拟仓-UK' THEN 'FBT-UK' WHEN 'FBT虚拟仓-US' THEN 'FBT-US'
       WHEN '万邑通-USKY3 Warehouse' THEN '美东' WHEN '万邑通-USWC2 Warehouse' THEN '美西' END,
       FaHuoRiQi,BeiHuoLiang,ShouHuoLiang
  FROM TK_BeiHuoDan
 WHERE FaHuoRiQi>='{(settings['as_of_date'] - timedelta(days=int(settings['parameters'].get('最近在途', 120) or 120))).isoformat()}'
   AND BeiHuoLiang-ShouHuoLiang>0
 ORDER BY SKU,ShouHuoCang,FaHuoRiQi""",
    )
    delivery_rows = _optional(
        query_executor,
        f"""/* daily_replenishment_tiktok:delivery_time */
SELECT zhuSKU,平均到货天数,单数
  FROM get_daohuoshixiao('{(settings['as_of_date'] - timedelta(days=int(settings['parameters'].get('到货时效天数', 60) or 60))).isoformat()}', '{(settings['as_of_date'] - timedelta(days=1)).isoformat()}', {float(settings['parameters'].get('到货时效比例', 0.8) or 0.8)})""",
    )
    new_local_rows = _optional(query_executor, "/* daily_replenishment_tiktok:new_local */ SELECT ZhuSKU,MinRiQi FROM v_到本地仓日期")

    samples = {str(row[0] or "").strip(): _compact(row[1]) for row in sample_rows if isinstance(row, (list, tuple)) and len(row) >= 2}
    purchase_plans: dict[str, list[str]] = defaultdict(list)
    for row in purchase_plan_rows:
        if isinstance(row, (list, tuple)) and len(row) >= 7:
            sku = str(row[0] or "").strip()
            if sku:
                detail = "，".join(str(value or "") for value in row[1:])
                purchase_plans[sku].append(detail)
    aux_consumption = {str(row[0] or "").strip(): _compact(row[1]) for row in aux_consumption_rows if isinstance(row, (list, tuple)) and len(row) >= 2}
    new_sales = {str(row[0] or "").strip(): _compact(row[1]) for row in new_sales_rows if isinstance(row, (list, tuple)) and len(row) >= 2}
    site_sales_inventory = [
        [str(row[0] or "").strip(), str(row[1] or "").strip(), _compact(row[2]), _compact(row[3]), _compact(row[4])]
        for row in site_sales_rows
        if isinstance(row, (list, tuple)) and len(row) >= 5 and str(row[0] or "").strip()
    ]
    yesterday_orders: dict[str, list[str]] = defaultdict(list)
    for row in yesterday_order_rows:
        if isinstance(row, (list, tuple)) and len(row) >= 5:
            sku = str(row[0] or "").strip()
            if sku:
                yesterday_orders[sku].append(f"{row[1] or '未知仓'}：销量{_compact(row[2])}，均价{_compact(row[3])}，订单数{_compact(row[4])}")
    daily_sales: dict[tuple[str, date], int | float] = {}
    for row in daily_sales_rows:
        if isinstance(row, (list, tuple)) and len(row) >= 3:
            sku = str(row[0] or "").strip()
            day = _date(row[1])
            if sku and day:
                daily_sales[(sku, day)] = _compact(row[2])
    videos = {str(row[0] or "").strip(): (_compact(row[1]), _compact(row[2])) for row in video_rows if isinstance(row, (list, tuple)) and len(row) >= 3}
    first_sales = {str(row[0] or "").strip(): _date(row[1]) for row in first_sale_rows if isinstance(row, (list, tuple)) and len(row) >= 2}
    notes: dict[str, list[str]] = defaultdict(list)
    for row in note_rows:
        if isinstance(row, (list, tuple)) and len(row) >= 3:
            sku = str(row[0] or "").strip()
            if sku:
                stamp = _date(row[1])
                stamp_text = stamp.strftime("%y-%m-%d") if stamp else str(row[1] or "")
                notes[sku].append(f"[{stamp_text}]{str(row[2] or '').strip()}")
    pending: dict[str, list[str]] = defaultdict(list)
    for row in pending_rows:
        if isinstance(row, (list, tuple)) and len(row) >= 8:
            sku = str(row[0] or "").strip()
            if sku:
                pending[sku].append(
                    f"{row[1] or ''}，{row[2] or ''}，{row[3] or ''}，{_compact(row[4])}-{_compact(row[5])}={_compact(row[6])}，{row[7] or ''}"
                )
    in_transit: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in in_transit_rows:
        if isinstance(row, (list, tuple)) and len(row) >= 5:
            sku = str(row[0] or "").strip()
            warehouse = str(row[1] or "").strip()
            if sku and warehouse:
                in_transit[sku].append((warehouse, f"{row[2] or ''} 备货{_compact(row[3])}-签收{_compact(row[4])}=" + str(_compact(_number(row[3]) - _number(row[4])))))
    delivery = {str(row[0] or "").strip(): f"到货时效：{_compact(row[1])}天，{_compact(row[2])}次" for row in delivery_rows if isinstance(row, (list, tuple)) and len(row) >= 3}
    new_local = {str(row[0] or "").strip(): _date(row[1]) for row in new_local_rows if isinstance(row, (list, tuple)) and len(row) >= 2}
    surge: dict[str, list[str]] = defaultdict(list)
    for row in surge_rows:
        if isinstance(row, (list, tuple)) and len(row) >= 5:
            sku = str(row[0] or "").strip()
            if sku:
                surge[sku].append(f"{row[1] or ''}，{_compact(row[2])}/{_compact(row[3])}={_compact(row[4])}")
    clearance = {str(row[0] if isinstance(row, (list, tuple)) else row or "").strip() for row in clearance_rows}
    ocean = {str(row[0] if isinstance(row, (list, tuple)) else row or "").strip() for row in ocean_rows}

    columns = ["运营", "店铺", "分类", "SKU", "本地库存", "美东库存", "美西库存", "FBT-US库存", "FBT-UK库存", "总库存", "采购在途", settings["sales_header"], "日均销量", "K值", "不含待到货量的可售天数", "含待到货量的可售天数", "订货量", "订货后可售天数", "备注", "近期发样品数", "近期发布视频个数", "近期发布视频播放量"]
    rows: list[dict[str, Any]] = []
    for raw in core_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 12:
            continue
        operator, store, category, sku = raw[:4]
        sku_text = str(sku or "").strip()
        if not sku_text:
            continue
        local, east, west, fbt_us, fbt_uk = (_compact(value) for value in raw[4:9])
        transit, sales, k_value = (_compact(value) for value in raw[9:12])
        launch_sale_override = (
            first_sales.get(sku_text)
            and first_sales[sku_text] >= settings["as_of_date"] - timedelta(days=settings["recent_launch_days"])
            and sku_text in new_sales
        )
        if launch_sale_override:
            sales = new_sales[sku_text]
        if sku_text in aux_consumption:
            sales = aux_consumption[sku_text]
        total = _compact(local + east + west + fbt_us + fbt_uk)
        daily = round(_number(sales) / settings["recent_days"], 1)
        no_pending_days = _days(total, daily) if total else 0
        with_pending_days = _days(total + transit, daily) if total + transit else 0
        remark_parts = list(notes.get(sku_text, []))
        if pending.get(sku_text):
            remark_parts.append("待到货：" + "\n".join(pending[sku_text]))
        if first_sales.get(sku_text):
            remark_parts.append(f"首次销售日期：{first_sales[sku_text].isoformat()}")
        if surge.get(sku_text):
            remark_parts.append("可能起量：" + "\n".join(surge[sku_text]))
        if launch_sale_override:
            remark_parts.append(f"最近开售销量：{new_sales[sku_text]}")
        if purchase_plans.get(sku_text):
            remark_parts.append("最近采购计划：" + "\n".join(purchase_plans[sku_text]))
        remark = "\n".join(remark_parts)
        rows.append({
            "row_number": len(rows) + 2,
            "values": [operator, store, str(category or "D"), sku_text, local, east, west, fbt_us, fbt_uk, total, transit, sales, daily, k_value, no_pending_days, with_pending_days, 0, with_pending_days, remark, samples.get(sku_text, 0), videos.get(sku_text, (0, 0))[0], videos.get(sku_text, (0, 0))[1]],
            "comments": {},
            "styles": {},
        })

    for row in rows:
        sku = str(row["values"][3])
        comments = row["comments"]

        def add_comment(column_index: int, text: str) -> None:
            existing = str(comments.get(column_index) or "").strip()
            comments[column_index] = f"{existing}\n{text}".strip() if existing else text

        if pending.get(sku):
            add_comment(10, "\n".join(pending[sku]))
        if first_sales.get(sku):
            add_comment(18, f"首次销售日期：{first_sales[sku].isoformat()}")
        if surge.get(sku):
            add_comment(11, "可能起量：\n" + "\n".join(surge[sku]))
        if first_sales.get(sku) and first_sales[sku] >= settings["as_of_date"] - timedelta(days=settings["recent_launch_days"]) and sku in new_sales:
            add_comment(11, f"最近 {settings['recent_launch_sales_days']} 天销量：{new_sales[sku]}")
            style_map = row["styles"]
            style_map.setdefault("11", []).append("mark-recent-sales")
        if purchase_plans.get(sku):
            add_comment(16, "最近采购计划：\n" + "\n".join(purchase_plans[sku]))
        if sku in aux_consumption:
            add_comment(11, "辅料消耗量：" + str(aux_consumption[sku]))
        if notes.get(sku):
            add_comment(18, "\n".join(notes[sku]))
        if delivery.get(sku):
            add_comment(16, delivery[sku])
        for warehouse, detail in in_transit.get(sku, []):
            warehouse_index = {"美东": 5, "美西": 6, "FBT-US": 7, "FBT-UK": 8}.get(warehouse)
            if warehouse_index is not None:
                add_comment(warehouse_index, detail)
        style_map = row["styles"]
        if sku in clearance:
            for index in range(0, 20):
                style_map.setdefault(str(index), []).append("mark-clearance")
        if sku in ocean:
            for index in range(0, 19):
                style_map.setdefault(str(index), []).append("mark-ocean")
        first_sale = first_sales.get(sku)
        if first_sale and first_sale >= settings["as_of_date"] - timedelta(days=settings["new_product_days"]):
            style_map.setdefault("18", []).append("mark-new-product")
        daily = _number(row["values"][12])
        k_value = _number(row["values"][13])
        if daily > 0 and k_value / daily >= settings["variation_threshold"]:
            style_map.setdefault("13", []).append("mark-variation")
        if _number(row["values"][15]) <= settings["low_days"] and daily > 0:
            for index in (14, 15, 17):
                style_map.setdefault(str(index), []).append("mark-low-stock")
        if surge.get(sku):
            style_map.setdefault("11", []).append("mark-surge")
        if new_local.get(sku) and new_local[sku] >= settings["as_of_date"] - timedelta(days=90):
            for index in (0, 1, 2):
                style_map.setdefault(str(index), []).append("mark-new-local")
        for line in pending.get(sku, []):
            pending_date = _date(line.split("，", 1)[0])
            quantity_text = line.split("=")[-1].split("，", 1)[0] if "=" in line else "0"
            if pending_date and pending_date <= settings["as_of_date"] - timedelta(days=int(settings.get("overdue_days", 10))) and _number(quantity_text) > 10:
                style_map.setdefault("10", []).append("mark-overdue")

    main = {
        "columns": columns,
        "header_comments": {},
        "order_notes": {},
        "generation": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "as_of_date": settings["as_of_date"].isoformat(),
            "sales_start": settings["sales_start"].isoformat(),
            "sales_end": settings["sales_end"].isoformat(),
            "recent_days": settings["recent_days"],
            "sales_source": "TK_DingDan.XiaoLiang",
            "platform": "TikTok",
        },
        "rows": rows,
    }
    daily_rows = [
        [row["values"][3], day, daily_sales.get((str(row["values"][3]), day), 0)]
        for row in rows
        for day in (settings["sales_start"] + timedelta(days=index) for index in range(settings["recent_days"]))
    ]
    return {
        "main": main,
        "sheets": {
            "SKU销量": {"columns": ["SKU", "日期", "销量"], "rows": daily_rows, "purpose": "TikTok 最近 N 天销量明细"},
            "数据源": {"columns": ["SKU", "样品数", "视频数", "视频播放量", "昨日下单付款明细"], "rows": [[sku, samples.get(sku, 0), videos.get(sku, (0, 0))[0], videos.get(sku, (0, 0))[1], "\n".join(yesterday_orders.get(sku, []))] for sku in sorted({str(row["values"][3]) for row in rows})], "purpose": "TikTok 生成按钮使用的样品、视频和昨日订单统计"},
            "站点销量库存": {"columns": ["SKU", "发货仓", "销量", "库存量", "在途"], "rows": site_sales_inventory, "purpose": "TikTok 最近站点销量、库存与在途明细"},
        },
        "generation": main["generation"],
    }


def save_tiktok_workbook(dataset: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    base._save_dataset_workbook(dataset["main"], destination)
    workbook = load_workbook(destination)
    try:
        for name in SHEET_ORDER[1:]:
            sheet_data = dataset["sheets"].get(name) or {}
            sheet = workbook.create_sheet(name)
            columns = list(sheet_data.get("columns") or [])
            for column, value in enumerate(columns, 1):
                base._write_literal(sheet.cell(1, column), value)
            for row_index, values in enumerate(sheet_data.get("rows") or [], 2):
                for column, value in enumerate(values, 1):
                    base._write_literal(sheet.cell(row_index, column), value)
            base._style_worksheet(sheet, len(sheet_data.get("rows") or []) + 1, len(columns))
        ordered = [workbook[name] for name in SHEET_ORDER if name in workbook.sheetnames]
        remaining = [sheet for sheet in workbook.worksheets if sheet.title not in SHEET_ORDER]
        workbook._sheets = ordered + remaining
        temp_path = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        workbook.save(temp_path)
        os.replace(temp_path, destination)
    finally:
        workbook.close()
        if 'temp_path' in locals():
            Path(temp_path).unlink(missing_ok=True)
    return destination


def _sheet_payload(dataset: dict[str, Any]) -> dict[str, Any]:
    main = base.serialize_dataset(dataset["main"])
    sheets = {
        name: {"columns": list(sheet.get("columns") or []), "rows": [[base._json_value(value) for value in row] for row in sheet.get("rows") or []], "purpose": str(sheet.get("purpose") or "")}
        for name, sheet in dataset["sheets"].items()
    }
    sheets[MAIN_SHEET] = {
        "columns": main["columns"], "rows": [row["values"] for row in main["rows"]],
        "header_comments": dict(main.get("header_comments") or {}),
        "comments": {str(index): dict(row.get("comments") or {}) for index, row in enumerate(main["rows"]) if row.get("comments")},
        "styles": {str(index): dict(row.get("styles") or {}) for index, row in enumerate(main["rows"]) if row.get("styles")},
        "purpose": "TikTok 生成日常补货表按钮的主表",
    }
    return {"sheets": sheets, "generation": main.get("generation") or {}}


def _load_tiktok_main(path: Path) -> dict[str, Any]:
    """Read the TikTok main sheet without the Amazon loader's 21-column limit."""
    if not base._is_supported_workbook(path):
        raise base.DailyReplenishmentError("找不到可读取的 TikTok 日常补货工作簿")
    max_rows = int(current_app.config.get("DAILY_REPLENISHMENT_MAX_ROWS", 20000))
    workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        if MAIN_SHEET not in workbook.sheetnames:
            raise base.DailyReplenishmentError(f"工作簿中找不到“{MAIN_SHEET}”工作表")
        sheet = workbook[MAIN_SHEET]
        first_row = next(sheet.iter_rows(min_row=1, max_col=sheet.max_column, values_only=True), None)
        raw_columns = list(first_row or [])
        columns = [
            str(value).strip() if value not in (None, "") else f"列{index + 1}"
            for index, value in enumerate(raw_columns)
        ]
        if not columns:
            columns = list(base.DEFAULT_HEADERS)
        sku_index = columns.index("SKU") if "SKU" in columns else 3
        rows: list[dict[str, Any]] = []
        blank_streak = 0
        for row_number, raw_values in enumerate(
            sheet.iter_rows(min_row=2, max_col=len(columns), values_only=True),
            start=2,
        ):
            values = list(raw_values[: len(columns)])
            values.extend([None] * (len(columns) - len(values)))
            if values[sku_index] in (None, ""):
                blank_streak += 1
                if rows and blank_streak >= 100:
                    break
                continue
            blank_streak = 0
            rows.append({"row_number": row_number, "values": values, "comments": {}, "styles": {}})
            if len(rows) >= max_rows:
                break

        rows_by_number = {row["row_number"]: row for row in rows}
        header_comments: dict[str, str] = {}
        if base.COMMENT_SHEET_NAME in workbook.sheetnames:
            for raw_row, raw_column, raw_comment in workbook[base.COMMENT_SHEET_NAME].iter_rows(
                min_row=2, max_col=3, values_only=True
            ):
                if raw_comment in (None, ""):
                    continue
                try:
                    row_number = int(raw_row)
                    column_index = int(raw_column)
                except (TypeError, ValueError):
                    continue
                if not 0 <= column_index < len(columns):
                    continue
                comment = str(raw_comment).strip()
                if row_number == 1:
                    header_comments[str(column_index)] = comment
                elif row_number in rows_by_number:
                    rows_by_number[row_number]["comments"][str(column_index)] = comment

        if base.STYLE_SHEET_NAME in workbook.sheetnames:
            for raw_row, raw_column, raw_styles in workbook[base.STYLE_SHEET_NAME].iter_rows(
                min_row=2, max_col=3, values_only=True
            ):
                try:
                    row_number = int(raw_row)
                    column_index = int(raw_column)
                except (TypeError, ValueError):
                    continue
                if row_number not in rows_by_number or not 0 <= column_index < len(columns):
                    continue
                tokens = [token.strip() for token in str(raw_styles or "").split(" ") if token.strip()]
                if tokens:
                    rows_by_number[row_number]["styles"][str(column_index)] = tokens

        order_notes: dict[str, str] = {}
        if "下单备注" in workbook.sheetnames:
            for sku, note in workbook["下单备注"].iter_rows(min_row=2, max_col=2, values_only=True):
                if sku not in (None, "") and note not in (None, ""):
                    order_notes[str(sku).strip()] = str(note).strip()

        generation: dict[str, Any] = {}
        if "_生成信息" in workbook.sheetnames:
            for key, value in workbook["_生成信息"].iter_rows(min_row=1, max_col=2, values_only=True):
                if key not in (None, ""):
                    generation[str(key).strip()] = base._json_value(value)
        return {
            "columns": columns,
            "rows": rows,
            "header_comments": header_comments,
            "order_notes": order_notes,
            "generation": generation,
        }
    finally:
        workbook.close()


def load_snapshot(path: Path) -> dict[str, Any]:
    main = _load_tiktok_main(path)
    workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        serialized = base.serialize_dataset(main)
        sheets: dict[str, Any] = {
            MAIN_SHEET: {
                "columns": serialized["columns"], "rows": [row["values"] for row in serialized["rows"]],
                "header_comments": serialized.get("header_comments") or {},
                "comments": {str(i): dict(row.get("comments") or {}) for i, row in enumerate(serialized["rows"]) if row.get("comments")},
                "styles": {str(i): dict(row.get("styles") or {}) for i, row in enumerate(serialized["rows"]) if row.get("styles")},
                "purpose": "TikTok 智能补货中心快照",
            }
        }
        for name in SHEET_ORDER[1:]:
            if name not in workbook.sheetnames:
                continue
            values = list(workbook[name].iter_rows(values_only=True))
            sheets[name] = {"columns": [str(value or "") for value in (values[0] if values else [])], "rows": [[base._json_value(value) for value in row] for row in values[1:] if any(value not in (None, "") for value in row)], "comments": {}, "styles": {}, "purpose": "TikTok 智能补货中心快照"}
        generation = {}
        if "_生成信息" in workbook.sheetnames:
            generation = {str(key): base._json_value(value) for key, value in workbook["_生成信息"].iter_rows(max_col=2, values_only=True) if key not in (None, "")}
        return {"sheets": sheets, "generation": generation}
    finally:
        workbook.close()


def load_snapshot_cached(path: Path) -> dict[str, Any]:
    key = str(path.resolve())
    modified = path.stat().st_mtime_ns
    with _snapshot_cache_lock:
        cached = _snapshot_cache.get(key)
        if cached and cached[0] == modified:
            return copy.deepcopy(cached[1])
    payload = load_snapshot(path)
    with _snapshot_cache_lock:
        _snapshot_cache[key] = (modified, copy.deepcopy(payload))
    return payload


def cache_snapshot_payload(path: Path, payload: dict[str, Any]) -> None:
    with _snapshot_cache_lock:
        _snapshot_cache[str(path.resolve())] = (path.stat().st_mtime_ns, copy.deepcopy(payload))


def _scope_payload(payload: dict[str, Any], access: dict[str, Any]) -> dict[str, Any]:
    scoped = copy.deepcopy(payload)
    stores = {_normalized_store(value) for value in access.get("read_stores") or set()}
    visible = {str(value or "").strip() for value in access.get("visible_skus") or set()}
    for name, sheet in (scoped.get("sheets") or {}).items():
        columns = [str(value or "").strip() for value in sheet.get("columns") or []]
        rows = sheet.get("rows") or []
        if name == MAIN_SHEET:
            try:
                index = columns.index("店铺")
            except ValueError:
                index = 1
            keep = [i for i, row in enumerate(rows) if len(row) > index and _normalized_store(row[index]) in stores]
        else:
            try:
                index = columns.index("SKU")
            except ValueError:
                index = 0
            keep = [i for i, row in enumerate(rows) if len(row) > index and str(row[index] or "").strip() in visible]
        sheet["rows"] = [rows[i] for i in keep]
        sheet["comments"] = {str(new): sheet.get("comments", {}).get(str(old), {}) for new, old in enumerate(keep) if str(old) in sheet.get("comments", {})}
        sheet["styles"] = {str(new): sheet.get("styles", {}).get(str(old), {}) for new, old in enumerate(keep) if str(old) in sheet.get("styles", {})}
    return scoped


def _snapshot_meta(path: Path | None, *, user_name: str = "", access: dict[str, Any] | None = None, shared: bool = False) -> dict[str, Any]:
    if path is None:
        return {"available": False, "date": date.today().isoformat(), "download_available": False}
    stat = path.stat()
    meta = {"available": True, "date": date.today().isoformat(), "name": path.name, "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"), "size_mb": round(stat.st_size / 1024 / 1024, 2), "download_available": not shared}
    stores = "\x1f".join(sorted(_normalized_store(value) for value in (access or {}).get("read_stores") or set()))
    skus = "\x1f".join(sorted(str(value or "").strip() for value in (access or {}).get("visible_skus") or set()))
    prefix = f"daily-replenishment-tiktok:v1:{_snapshot_owner_key(user_name)}:"
    meta["client_cache_prefix"] = prefix
    meta["client_cache_key"] = f"{prefix}{stat.st_mtime_ns}:{hashlib.sha256(f'{stores}|{skus}'.encode()).hexdigest()[:16]}"
    return meta


def _save_quantity_changes(snapshot: Path, access: dict[str, Any], changes: list[dict[str, Any]]) -> int:
    if not changes:
        return 0
    payload = load_snapshot(snapshot)
    main = payload["sheets"][MAIN_SHEET]
    columns = [str(value or "").strip() for value in main.get("columns") or []]
    indexes = {name: columns.index(name) for name in ("SKU", "店铺", "运营", "订货量")}
    rows = main.get("rows") or []
    stores = {_normalized_store(value) for value in access.get("read_stores") or set()}
    scoped = [index for index, row in enumerate(rows) if len(row) > indexes["店铺"] and _normalized_store(row[indexes["店铺"]]) in stores]
    resolved: dict[int, int] = {}
    for raw in changes:
        if not isinstance(raw, dict):
            raise base.DailyReplenishmentError("订货量修改明细格式不正确")
        try:
            scoped_index = int(raw.get("index"))
            quantity = _number(raw.get("quantity"))
        except (TypeError, ValueError) as exc:
            raise base.DailyReplenishmentError("订货量修改格式不正确") from exc
        if scoped_index < 0 or scoped_index >= len(scoped) or quantity < 0 or abs(quantity - round(quantity)) > 1e-9:
            raise base.DailyReplenishmentError("订货量必须是大于等于 0 的整数")
        full_index = scoped[scoped_index]
        row = rows[full_index]
        for key in ("SKU", "店铺", "运营"):
            if key in raw and str(raw.get(key) or "").strip() != str(row[indexes[key]] or "").strip():
                raise base.DailyReplenishmentError("快照内容已变化，请刷新后再保存订货量")
        resolved[full_index] = int(round(quantity))
    workbook = load_workbook(snapshot)
    temp_path = snapshot.with_name(f".{snapshot.name}.{uuid.uuid4().hex}.tmp")
    try:
        sheet = workbook[MAIN_SHEET]
        for index, quantity in resolved.items():
            sheet.cell(row=index + 2, column=indexes["订货量"] + 1).value = quantity
        workbook.save(temp_path)
        os.replace(temp_path, snapshot)
    finally:
        workbook.close()
        temp_path.unlink(missing_ok=True)
    return len(resolved)


@daily_replenishment_tiktok_bp.get("/ai/daily-replenishment-tiktok")
@require_permission(PERMISSION_NAME)
def page():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    snapshot, shared = _resolve_snapshot_for_user(user_name)
    return render_template("内容生产工厂/daily_replenishment_tiktok.html", snapshot=_snapshot_meta(snapshot, user_name=user_name, access=access, shared=shared), initial_data=None, operator_stores=sorted(access["read_stores"]), can_write=bool(access["can_write"]))


@daily_replenishment_tiktok_bp.post("/api/ai/daily-replenishment-tiktok/refresh")
@require_permission(PERMISSION_NAME)
def refresh():
    user_name = _current_user_name()
    executor, access = scoped_query_executor(user_name)
    if not access["can_write"]:
        return jsonify({"success": False, "message": "当前用户在 DianQuanXian 中只有阅读权限，不能生成或刷新"}), 403
    uploaded = request.files.get("file")
    source = base.save_uploaded_workbook(uploaded) if uploaded and getattr(uploaded, "filename", "") else resolve_source_path()
    overrides: dict[str, Any] = {}
    raw_days = (request.form.get("recentDays") or "").strip()
    if raw_days:
        try:
            overrides["recent_days"] = int(raw_days)
        except ValueError:
            return jsonify({"success": False, "message": "最近天数必须是整数"}), 400
    raw_listing_days = (request.form.get("listingDays") or "").strip()
    if raw_listing_days:
        try:
            overrides["listing_days"] = int(raw_listing_days)
        except ValueError:
            return jsonify({"success": False, "message": "新品标黄色天数必须是整数"}), 400
    raw_sample_days = (request.form.get("sampleDays") or "").strip()
    if raw_sample_days:
        try:
            overrides["sample_days"] = int(raw_sample_days)
        except ValueError:
            return jsonify({"success": False, "message": "样品与视频统计天数必须是整数"}), 400
    job_id = uuid.uuid4().hex
    app = current_app._get_current_object()
    with _refresh_jobs_lock:
        _refresh_jobs[job_id] = {"status": "queued", "user": user_name}

    def run_job():
        try:
            with app.app_context():
                with _refresh_jobs_lock:
                    _refresh_jobs[job_id]["status"] = "running"
                with _refresh_lock:
                    dataset = generate_tiktok_dataset(source, query_executor=executor, overrides=overrides, user_name=user_name)
                    snapshot = get_snapshot_path(user_name=user_name)
                    save_tiktok_workbook(dataset, snapshot)
                payload = _sheet_payload(dataset)
                payload.update(success=True, stores=sorted(access["read_stores"]), snapshot=_snapshot_meta(snapshot, user_name=user_name, access=access))
                cache_snapshot_payload(snapshot, payload)
            with _refresh_jobs_lock:
                _refresh_jobs[job_id].update(status="completed", payload=payload)
        except Exception as exc:
            app.logger.exception("Failed to refresh TikTok replenishment")
            with _refresh_jobs_lock:
                _refresh_jobs[job_id].update(status="failed", message=str(exc))

    _refresh_executor.submit(run_job)
    return jsonify({"success": True, "jobId": job_id, "status": "queued", "message": "TikTok 补货表生成任务已开始"}), 202


@daily_replenishment_tiktok_bp.get("/api/ai/daily-replenishment-tiktok/refresh/<job_id>")
@require_permission(PERMISSION_NAME)
def refresh_status(job_id):
    with _refresh_jobs_lock:
        job = _refresh_jobs.get(job_id)
        if not job or job.get("user") != _current_user_name():
            return jsonify({"success": False, "message": "生成任务不存在"}), 404
        result = dict(job)
    if result.get("status") == "completed":
        return jsonify(result["payload"])
    return jsonify({"success": result.get("status") != "failed", "status": result.get("status"), "message": result.get("message", "")})


@daily_replenishment_tiktok_bp.get("/api/ai/daily-replenishment-tiktok/data")
@require_permission(PERMISSION_NAME)
def data():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    snapshot, shared = _resolve_snapshot_for_user(user_name)
    if snapshot is None:
        return jsonify({"success": False, "message": "今日的 TikTok 智能补货快照尚未生成"}), 404
    payload = _scope_payload(load_snapshot_cached(snapshot), access)
    payload.update(success=True, stores=sorted(access["read_stores"]), snapshot=_snapshot_meta(snapshot, user_name=user_name, access=access, shared=shared))
    return jsonify(payload)


@daily_replenishment_tiktok_bp.get("/api/ai/daily-replenishment-tiktok/sales-trend")
@require_permission(PERMISSION_NAME)
def sales_trend():
    wanted = [item.strip() for item in str(request.args.get("skus") or request.args.get("sku") or "").split(",") if item.strip()]
    if not wanted:
        return jsonify({"success": False, "message": "缺少 SKU 参数"}), 400
    if len(wanted) > 200:
        return jsonify({"success": False, "message": "一次最多查询 200 个 SKU"}), 400
    user_name = _current_user_name()
    execute, access = scoped_query_executor(user_name)
    allowed = [sku for sku in wanted if sku in access.get("visible_skus", set())]
    if not allowed:
        return jsonify({"success": False, "message": "该 SKU 不在当前账号的店铺权限范围内"}), 403
    snapshot, _ = _resolve_snapshot_for_user(user_name)
    generation = load_snapshot_cached(snapshot).get("generation") if snapshot else {}
    try:
        start = date.fromisoformat(str(request.args.get("start") or generation.get("sales_start")))
        end = date.fromisoformat(str(request.args.get("end") or generation.get("sales_end")))
    except ValueError:
        return jsonify({"success": False, "message": "日期参数应形如 YYYY-MM-DD"}), 400
    if start > end or (end - start).days > 45 or end > date.today():
        return jsonify({"success": False, "message": "走势区间需在 1 到 45 天之间且不能晚于今天"}), 400
    literals = ",".join(f"N'{escape_sql_literal(sku, escape_percent=False)}'" for sku in allowed)
    rows = execute(f"""/* daily_replenishment_tiktok:sales */
SELECT SKU,DingGouRiQi,SUM(ISNULL(XiaoLiang,0)) FROM TK_DingDan
 WHERE SKU IN ({literals}) AND DingGouRiQi BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
 GROUP BY SKU,DingGouRiQi ORDER BY SKU,DingGouRiQi""") or []
    by_sku: dict[str, dict[str, int]] = defaultdict(dict)
    for row in rows:
        if isinstance(row, (list, tuple)) and len(row) >= 3 and _date(row[1]):
            by_sku[str(row[0] or "").strip()][_date(row[1]).isoformat()] = int(round(_number(row[2])))
    dates = [(start + timedelta(days=index)).isoformat() for index in range((end - start).days + 1)]
    series = {sku: [{"date": stamp, "qty": by_sku.get(sku, {}).get(stamp, 0)} for stamp in dates] for sku in wanted}
    if request.args.get("skus"):
        return jsonify({"success": True, "start": start.isoformat(), "end": end.isoformat(), "series": series, "source": "TK_DingDan"})
    days = series[wanted[0]]
    total = sum(item["qty"] for item in days)
    return jsonify({"success": True, "sku": wanted[0], "start": start.isoformat(), "end": end.isoformat(), "days": days, "sum": total, "avg": round(total / len(days), 1) if days else 0, "source": "TK_DingDan"})


@daily_replenishment_tiktok_bp.post("/api/ai/daily-replenishment-tiktok/order-quantities")
@require_permission(PERMISSION_NAME)
def update_order_quantities():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    if not access["can_write"]:
        return jsonify({"success": False, "message": "当前用户只有阅读权限，不能修改订货量"}), 403
    body = request.get_json(silent=True) or {}
    changes = body.get("changes") if isinstance(body, dict) else None
    if not isinstance(changes, list):
        return jsonify({"success": False, "message": "订货量修改明细格式不正确"}), 400
    snapshot, shared = _resolve_snapshot_for_user(user_name)
    if snapshot is None:
        return jsonify({"success": False, "message": "今日快照尚未生成，请先生成"}), 404
    with _refresh_lock:
        if shared:
            own = get_snapshot_path(user_name=user_name)
            own.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot, own)
            snapshot = own
        _save_quantity_changes(snapshot, access, changes)
    payload = _scope_payload(load_snapshot_cached(snapshot), access)
    payload.update(success=True, stores=sorted(access["read_stores"]), snapshot=_snapshot_meta(snapshot, user_name=user_name, access=access))
    return jsonify(payload)


@daily_replenishment_tiktok_bp.get("/api/ai/daily-replenishment-tiktok/download")
@require_permission(PERMISSION_NAME)
def download():
    snapshot = get_today_snapshot(user_name=_current_user_name())
    if snapshot is None:
        return jsonify({"success": False, "message": "今日快照尚未生成"}), 404
    return send_file(snapshot, as_attachment=True, download_name=snapshot.name)


@daily_replenishment_tiktok_bp.route("/api/ai/daily-replenishment-tiktok/purchase-plan", methods=("GET", "POST"))
@require_permission(PERMISSION_NAME)
def purchase_plan():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    snapshot, _ = _resolve_snapshot_for_user(user_name)
    if snapshot is None:
        return jsonify({"success": False, "message": "今日快照尚未生成"}), 404
    payload = _scope_payload(load_snapshot_cached(snapshot), access)
    sheet = payload["sheets"].get(MAIN_SHEET) or {}
    columns = [str(value or "").strip() for value in sheet.get("columns") or []]
    indexes = {name: columns.index(name) for name in ("SKU", "店铺", "订货量")}
    items = []
    for index, row in enumerate(sheet.get("rows") or []):
        qty = _number(row[indexes["订货量"]])
        if qty > 10:
            items.append({"index": index, "sku": str(row[indexes["SKU"]] or ""), "store": str(row[indexes["店铺"]] or ""), "quantity": int(round(qty))})
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        confirmed = body.get("items") if isinstance(body, dict) else None
        if not isinstance(confirmed, list) or not confirmed:
            return jsonify({"success": False, "message": "请至少选择一条采购明细"}), 400
        by_index = {item["index"]: item for item in items}
        items = []
        for raw in confirmed:
            try:
                item = by_index[int(raw.get("index"))]
                quantity = int(round(_number(raw.get("quantity"))))
            except (TypeError, ValueError, KeyError):
                return jsonify({"success": False, "message": "采购明细已变化，请刷新后重试"}), 400
            if quantity <= 0:
                return jsonify({"success": False, "message": "采购数量必须大于 0"}), 400
            items.append({**item, "quantity": quantity})
    workbook = Workbook()
    sheet_out = workbook.active
    sheet_out.title = "Sheet1"
    headers = ["*SKU", "店铺", "FNSKU", "专属类型", "MSKU", "供应商", "*计划采购量", "备注"]
    sheet_out.append(headers)
    for item in items:
        sheet_out.append([item["sku"], item["store"], "", "", "", "", item["quantity"], f"成品SKU：{item['sku']}"])
    output_dir = get_output_dir(create=True) / "_采购计划"
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{date.today().isoformat()}_{uuid.uuid4().hex[:8]}下单导入.xlsx"
    workbook.save(destination)
    response = send_file(destination, as_attachment=True, download_name=f"{date.today().month}.{date.today().day}下单导入.xlsx", max_age=0)
    response.headers["X-Purchase-Plan-Rows"] = str(len(items))
    return response
