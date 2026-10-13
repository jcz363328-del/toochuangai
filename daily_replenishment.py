from __future__ import annotations

import os
import posixpath
import re
import tempfile
import time
import warnings
from collections import defaultdict
from copy import copy
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from bjc import sf_db
from department_permissions import require_permission


daily_replenishment_bp = Blueprint("daily_replenishment", __name__)

SHEET_NAME = "日常补货"
DEFAULT_OUTPUT_DIR = Path(r"D:\tuchuangai\捕获表文件")
ALLOWED_SUFFIXES = {".xlsx", ".xlsm"}
SESSION_SOURCE_KEY = "daily_replenishment_source"
MAX_REMARK_LENGTH = 5000
DEFAULT_HEADERS = (
    "运营",
    "店铺",
    "分类",
    "SKU",
    "总库存",
    "FBA可售量",
    "待到货",
    "销量",
    "日均销量",
    "K值",
    "可售量对应的可售天数",
    "不含待到货量的可售天数",
    "含待到货量的可售天数",
    "订货量",
    "订货后可售天数",
    "到FBA仓日期",
    "工厂",
    "备注",
    "类别",
    "AB品",
    "站点",
)

_cache_lock = Lock()
_sheet_cache: dict[tuple[str, int, int], dict[str, Any]] = {}
_source_comment_cache: dict[tuple[str, int, int], dict[str, Any]] = {}
_snapshot_lock = Lock()
SNAPSHOT_DIR_NAME = "_每日快照"
SNAPSHOT_GENERATOR_VERSION = "Python快照"
DEFAULT_RECENT_DAYS = 15
DEFAULT_SALES_SOURCE = "付款"
COMMENT_SHEET_NAME = "_单元格批注"
STYLE_SHEET_NAME = "_单元格样式"
COMMENT_AUTHOR = "图创AI"
COMMENT_PARAMETER_DEFAULTS = {
    "前两次库存天数": 100,
    "最近的采购计划": 3,
    "最近找运营下单": 60,
    "最近找运营下单_减量": 3,
    "新品标黄色": 30,
    "最近开售": 15,
    "最近开售_销售天数": 3,
    "起量倍数_系数": 2,
    "起量倍数_可售天数": 30,
    "持续下滑": 10,
    "到货时效天数": 60,
    "到货时效比例": 0.8,
    "可售天数标红": 30,
    "超过N天未到货": 10,
    "变异系数": 0.08,
}


class DailyReplenishmentError(RuntimeError):
    pass


class DailySnapshotRefreshInProgress(DailyReplenishmentError):
    pass


def get_output_dir(*, create: bool = False) -> Path:
    configured = current_app.config.get("DAILY_REPLENISHMENT_OUTPUT_DIR")
    raw = configured or os.environ.get("DAILY_REPLENISHMENT_OUTPUT_DIR")
    output_dir = Path(str(raw)).expanduser() if raw else DEFAULT_OUTPUT_DIR
    if create:
        output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_snapshot_path(snapshot_date: date | None = None) -> Path:
    target_date = snapshot_date or date.today()
    return (
        get_output_dir()
        / SNAPSHOT_DIR_NAME
        / f"{target_date:%Y%m%d}日常补货_{SNAPSHOT_GENERATOR_VERSION}.xlsx"
    )


def get_today_snapshot() -> Path | None:
    path = get_snapshot_path()
    return path if _is_supported_workbook(path) else None


def _safe_filename(filename: str) -> str:
    name = Path(str(filename or "").replace("\\", "/")).name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.rstrip(". ")
    return name[:120] or "日常补货.xlsx"


def _is_supported_workbook(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES


def _is_path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _configured_source_path() -> Path | None:
    raw = current_app.config.get("DAILY_REPLENISHMENT_SOURCE_PATH")
    raw = raw or os.environ.get("DAILY_REPLENISHMENT_SOURCE_PATH")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    return path if _is_supported_workbook(path) else None


def _allowed_session_source(path: Path) -> bool:
    if _is_path_within(path, get_output_dir()):
        return True
    configured = _configured_source_path()
    if configured and path.resolve() == configured.resolve():
        return True
    desktop = Path.home() / "Desktop"
    return desktop.is_dir() and _is_path_within(path, desktop)


def resolve_source_path() -> Path | None:
    session_path = str(session.get(SESSION_SOURCE_KEY) or "").strip()
    if session_path:
        candidate = Path(session_path)
        if _is_supported_workbook(candidate) and _allowed_session_source(candidate):
            return candidate
        session.pop(SESSION_SOURCE_KEY, None)

    configured = _configured_source_path()
    if configured:
        return configured

    candidates: list[Path] = []
    output_dir = get_output_dir()
    if output_dir.is_dir():
        for pattern in ("*日常补货*.xls*", "*日常捕获*.xls*"):
            candidates.extend(path for path in output_dir.glob(pattern) if _is_supported_workbook(path))

    desktop = Path.home() / "Desktop"
    if desktop.is_dir():
        for pattern in ("*日常补货*.xls*", "*日常捕获*.xls*"):
            candidates.extend(path for path in desktop.glob(pattern) if _is_supported_workbook(path))

    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def _validate_uploaded_workbook(path: Path) -> None:
    max_bytes = int(current_app.config.get("DAILY_REPLENISHMENT_MAX_UPLOAD_BYTES", 80 * 1024 * 1024))
    if path.stat().st_size > max_bytes:
        raise DailyReplenishmentError("表格文件过大，请上传80MB以内的 .xlsx 或 .xlsm 文件")
    try:
        with ZipFile(path) as archive:
            names = set(archive.namelist())
            if "xl/workbook.xml" not in names:
                raise DailyReplenishmentError("上传的文件不是有效的 Excel 工作簿")
            expanded_size = sum(info.file_size for info in archive.infolist())
            if expanded_size > 512 * 1024 * 1024:
                raise DailyReplenishmentError("表格解压后过大，无法安全读取")
    except BadZipFile as exc:
        raise DailyReplenishmentError("上传的文件不是有效的 Excel 工作簿") from exc


def save_uploaded_workbook(storage) -> Path:
    filename = _safe_filename(getattr(storage, "filename", ""))
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise DailyReplenishmentError("仅支持 .xlsx 和 .xlsm 文件")

    working_dir = get_output_dir(create=True) / "_工作文件"
    working_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=working_dir, suffix=suffix, delete=False) as tmp:
        temp_path = Path(tmp.name)
    try:
        storage.save(temp_path)
        _validate_uploaded_workbook(temp_path)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = working_dir / f"{stamp}_{uuid4().hex[:6]}_{filename}"
        os.replace(temp_path, destination)
        return destination
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _clone_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "columns": list(dataset["columns"]),
        "header_comments": dict(dataset.get("header_comments") or {}),
        "order_notes": dict(dataset.get("order_notes") or {}),
        "generation": dict(dataset.get("generation") or {}),
        "rows": [
            {
                "row_number": row["row_number"],
                "values": list(row["values"]),
                "comments": dict(row.get("comments") or {}),
                "styles": {
                    str(index): list(tokens)
                    for index, tokens in dict(row.get("styles") or {}).items()
                },
            }
            for row in dataset["rows"]
        ],
    }


def load_daily_replenishment(path: Path) -> dict[str, Any]:
    if not _is_supported_workbook(path):
        raise DailyReplenishmentError("找不到可读取的日常补货工作簿")

    stat = path.stat()
    cache_key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        cached = _sheet_cache.get(cache_key)
    if cached is not None:
        return _clone_dataset(cached)

    max_rows = int(current_app.config.get("DAILY_REPLENISHMENT_MAX_ROWS", 20000))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    except Exception as exc:
        raise DailyReplenishmentError(f"表格读取失败：{exc}") from exc

    try:
        if SHEET_NAME not in workbook.sheetnames:
            raise DailyReplenishmentError(f"工作簿中找不到“{SHEET_NAME}”工作表")
        sheet = workbook[SHEET_NAME]
        iterator = sheet.iter_rows(min_row=1, max_col=len(DEFAULT_HEADERS), values_only=True)
        first_row = next(iterator, None)
        columns = list(first_row or DEFAULT_HEADERS)
        columns.extend([None] * (len(DEFAULT_HEADERS) - len(columns)))
        columns = [str(value).strip() if value not in (None, "") else DEFAULT_HEADERS[index] for index, value in enumerate(columns[: len(DEFAULT_HEADERS)])]

        rows: list[dict[str, Any]] = []
        blank_streak = 0
        for row_number, raw_values in enumerate(iterator, start=2):
            values = list(raw_values[: len(DEFAULT_HEADERS)])
            values.extend([None] * (len(DEFAULT_HEADERS) - len(values)))
            sku = values[3]
            if sku in (None, ""):
                blank_streak += 1
                if rows and blank_streak >= 100:
                    break
                continue
            blank_streak = 0
            rows.append(
                {
                    "row_number": row_number,
                    "values": values,
                    "comments": {},
                    "styles": {},
                }
            )
            if len(rows) >= max_rows:
                break

        header_comments: dict[str, str] = {}
        rows_by_number = {row["row_number"]: row for row in rows}
        if COMMENT_SHEET_NAME in workbook.sheetnames:
            comment_sheet = workbook[COMMENT_SHEET_NAME]
            for raw_row, raw_column, raw_comment in comment_sheet.iter_rows(
                min_row=2,
                max_col=3,
                values_only=True,
            ):
                if raw_comment in (None, ""):
                    continue
                try:
                    row_number = int(raw_row)
                    column_index = int(raw_column)
                except (TypeError, ValueError):
                    continue
                if not 0 <= column_index < len(DEFAULT_HEADERS):
                    continue
                comment = str(raw_comment).strip()
                if row_number == 1:
                    header_comments[str(column_index)] = comment
                elif row_number in rows_by_number:
                    rows_by_number[row_number]["comments"][str(column_index)] = comment

        if STYLE_SHEET_NAME in workbook.sheetnames:
            style_sheet = workbook[STYLE_SHEET_NAME]
            for raw_row, raw_column, raw_styles in style_sheet.iter_rows(
                min_row=2,
                max_col=3,
                values_only=True,
            ):
                try:
                    row_number = int(raw_row)
                    column_index = int(raw_column)
                except (TypeError, ValueError):
                    continue
                if row_number not in rows_by_number or not 0 <= column_index < len(DEFAULT_HEADERS):
                    continue
                tokens = [
                    token.strip()
                    for token in str(raw_styles or "").split(" ")
                    if token.strip()
                ]
                if tokens:
                    rows_by_number[row_number]["styles"][str(column_index)] = tokens

        order_notes: dict[str, str] = {}
        if "下单备注" in workbook.sheetnames:
            notes_sheet = workbook["下单备注"]
            blank_notes = 0
            for sku, note in notes_sheet.iter_rows(min_row=2, max_col=2, values_only=True):
                if sku in (None, ""):
                    blank_notes += 1
                    if order_notes and blank_notes >= 100:
                        break
                    continue
                blank_notes = 0
                if note not in (None, ""):
                    order_notes[str(sku).strip()] = str(note).strip()

        generation: dict[str, Any] = {}
        if "_生成信息" in workbook.sheetnames:
            generation_sheet = workbook["_生成信息"]
            for key, value in generation_sheet.iter_rows(min_row=1, max_col=2, values_only=True):
                if key not in (None, ""):
                    generation[str(key).strip()] = _json_value(value)

    finally:
        workbook.close()

    dataset = {
        "columns": columns,
        "rows": rows,
        "header_comments": header_comments,
        "order_notes": order_notes,
        "generation": generation,
    }
    with _cache_lock:
        _sheet_cache.clear()
        _sheet_cache[cache_key] = _clone_dataset(dataset)
    return dataset


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return value


def serialize_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "columns": list(dataset["columns"]),
        "header_comments": dict(dataset.get("header_comments") or {}),
        "generation": dict(dataset.get("generation") or {}),
        "rows": [
            {
                "row_number": row["row_number"],
                "values": [_json_value(value) for value in row["values"]],
                "comments": dict(row.get("comments") or {}),
                "styles": {
                    str(index): list(tokens)
                    for index, tokens in dict(row.get("styles") or {}).items()
                },
            }
            for row in dataset["rows"]
        ],
    }


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    rows = dataset["rows"]
    operators = sorted({str(row["values"][0]).strip() for row in rows if row["values"][0] not in (None, "")})
    morning = 0
    afternoon = 0
    remarks = 0
    for row in rows:
        quantity = _as_number(row["values"][13])
        if quantity is not None and quantity >= 10:
            morning += 1
        if quantity is not None and quantity < -10:
            afternoon += 1
        if str(row["values"][17] or "").strip():
            remarks += 1
    return {
        "total": len(rows),
        "morning": morning,
        "afternoon": afternoon,
        "remarks": remarks,
        "operators": operators,
    }


def _read_generation_parameters(source: Path | None) -> dict[str, Any]:
    if source is None or not _is_supported_workbook(source):
        return {}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            workbook = load_workbook(source, read_only=True, data_only=True, keep_links=False)
    except Exception:
        return {}
    try:
        values: dict[str, Any] = {}
        if "参数" not in workbook.sheetnames:
            return {}
        for key, value in workbook["参数"].iter_rows(min_row=2, max_col=2, values_only=True):
            if key not in (None, ""):
                values[str(key).strip()] = value
        return values
    finally:
        workbook.close()


def get_generation_settings(
    source: Path | None = None,
    *,
    as_of_date: date | None = None,
    recent_days: Any = None,
    sales_source: Any = None,
) -> dict[str, Any]:
    parameters = _read_generation_parameters(source)
    comment_parameters = dict(COMMENT_PARAMETER_DEFAULTS)
    for key, default_value in COMMENT_PARAMETER_DEFAULTS.items():
        raw_value = parameters.get(key, default_value)
        try:
            comment_parameters[key] = (
                float(raw_value) if isinstance(default_value, float) else int(raw_value)
            )
        except (TypeError, ValueError):
            comment_parameters[key] = default_value
    raw_days = recent_days
    if raw_days in (None, ""):
        raw_days = current_app.config.get("DAILY_REPLENISHMENT_RECENT_DAYS")
    if raw_days in (None, ""):
        raw_days = parameters.get("最近天数", DEFAULT_RECENT_DAYS)
    try:
        days = int(raw_days)
    except (TypeError, ValueError) as exc:
        raise DailyReplenishmentError("最近天数必须是整数") from exc
    if not 1 <= days <= 365:
        raise DailyReplenishmentError("最近天数必须在 1 到 365 之间")

    raw_source = sales_source
    if raw_source in (None, ""):
        raw_source = current_app.config.get("DAILY_REPLENISHMENT_SALES_SOURCE")
    if raw_source in (None, ""):
        raw_source = parameters.get("销售来源", DEFAULT_SALES_SOURCE)
    normalized_source = str(raw_source).strip() or DEFAULT_SALES_SOURCE
    if normalized_source not in {"付款", "下单"}:
        raise DailyReplenishmentError("销量来源只能是“付款”或“下单”")

    today = as_of_date or date.today()
    sales_end = today - timedelta(days=2)
    sales_start = today - timedelta(days=days + 1)
    sales_header = (
        f"{sales_start.month}.{sales_start.day}-"
        f"{sales_end.month}.{sales_end.day}销量"
    )
    return {
        "as_of_date": today,
        "sales_start": sales_start,
        "sales_end": sales_end,
        "recent_days": days,
        "sales_source": normalized_source,
        "sales_header": sales_header,
        "comment_parameters": comment_parameters,
    }


def _generation_sql(settings: dict[str, Any]) -> str:
    start = settings["sales_start"].isoformat()
    end = settings["sales_end"].isoformat()
    ship_start = (settings["as_of_date"] - timedelta(days=60)).isoformat()
    if settings["sales_source"] == "下单":
        sales_sql = (
            "SELECT SKU,SUM(ShuLiang) SalesQty\n"
            "  FROM GuangGao\n"
            f" WHERE RiQi BETWEEN '{start}' AND '{end}'\n"
            " GROUP BY SKU"
        )
    else:
        sales_sql = (
            "SELECT SKU,SUM(HeSuanXiaoLiang) SalesQty\n"
            "  FROM v_XiaoShouLiang\n"
            f" WHERE RiQi BETWEEN '{start}' AND '{end}'\n"
            " GROUP BY SKU"
        )

    return f"""/* daily_replenishment:core */
WITH InventoryDetail AS (
    SELECT SKU,
           SUM(CAST(ISNULL(ShuLiang,0) AS FLOAT)) Qty,
           CAST(0 AS FLOAT) FbaSellable
      FROM v_KuCun1
     WHERE SKU IN (SELECT SKU FROM ZiDian WHERE BaoHan<>'')
     GROUP BY SKU
    UNION ALL
    SELECT SKU,
           SUM(CAST(ISNULL(KeShou,0)+ISNULL(DaiTiaoCang,0)+ISNULL(TiaoCangZhong,0)+ISNULL(ZaiTu,0) AS FLOAT)) Qty,
           SUM(CAST(ISNULL(KeShou,0) AS FLOAT)) FbaSellable
      FROM v_KuCun2
     GROUP BY SKU
), Inventory AS (
    SELECT SKU,SUM(Qty) TotalInventory,SUM(FbaSellable) FbaSellable
      FROM InventoryDetail
     GROUP BY SKU
), SemiFinishedDetail AS (
    SELECT zd.ZhuSKU,
           kc.SKU ComponentSKU,
           SUM(CAST(ISNULL(kc.ShuLiang,0) AS FLOAT)) ComponentQty
      FROM v_KuCun1 kc
      LEFT JOIN ZiDian zd ON kc.SKU=zd.SKU
     WHERE kc.SKU NOT LIKE '%盒%'
       AND kc.SKU NOT LIKE '%半毛%'
       AND kc.SKU NOT LIKE '%不干胶%'
       AND kc.SKU IN (SELECT SKU FROM ZiDian WHERE BaoHan='')
       AND kc.ShuLiang>0
     GROUP BY zd.ZhuSKU,kc.SKU
), SemiFinishedTotal AS (
    SELECT ZhuSKU,SUM(ComponentQty) ComponentQty
      FROM SemiFinishedDetail
     GROUP BY ZhuSKU
), OrphanSemiFinished AS (
    SELECT zd.ZhuSKU,
           kc.SKU ComponentSKU,
           SUM(CAST(ISNULL(kc.ShuLiang,0) AS FLOAT)) ComponentQty
      FROM v_KuCun1 kc
      LEFT JOIN ZiDian zd ON kc.SKU=zd.SKU
     WHERE kc.SKU<>zd.ZhuSKU
       AND kc.ShuLiang>0
       AND zd.Dian<>99
     GROUP BY zd.ZhuSKU,kc.SKU
), InventoryRows AS (
    SELECT i.SKU,
           i.TotalInventory+ISNULL(sf.ComponentQty,0) TotalInventory,
           i.FbaSellable
      FROM Inventory i
      LEFT JOIN SemiFinishedTotal sf ON sf.ZhuSKU=i.SKU
    UNION ALL
    SELECT sf.ComponentSKU SKU,sf.ComponentQty TotalInventory,CAST(0 AS FLOAT) FbaSellable
      FROM OrphanSemiFinished sf
     WHERE NOT EXISTS (SELECT 1 FROM Inventory i WHERE i.SKU=sf.ZhuSKU)
), Transit AS (
    SELECT ZhuSKU SKU,SUM(CAST(ISNULL(ZaiTu,0) AS FLOAT)) PendingQty
      FROM v_ZaiTu
     GROUP BY ZhuSKU
), Sales AS (
{sales_sql}
), FbaDate AS (
    SELECT SKU,MIN(RiQi) FirstFbaDate
      FROM XinPin
     WHERE Cang='FBA'
     GROUP BY SKU
), LocDate AS (
    SELECT SKU,MIN(RiQi) FirstLocDate
      FROM XinPin
     WHERE Cang='LOC'
     GROUP BY SKU
), ShipDate AS (
    SELECT ZhuSKU SKU,MIN(RiQi) FirstShipDate
      FROM ChuKu
     WHERE LeiXing='FBA出库' AND RiQi>='{ship_start}'
     GROUP BY ZhuSKU
), StoreCategory AS (
    SELECT SKU,Dian,MAX(FenLei) FenLei
      FROM v_FenLei
     GROUP BY SKU,Dian
), ProductType AS (
    SELECT ZhuSKU,
           MAX(CASE
               WHEN FenLei1 IN ('簇毛','自研发簇毛','研发部簇毛') THEN '簇毛'
               WHEN FenLei1 IN ('研发部改良磁铁睫毛','研发部软磁假睫毛','磁铁睫毛') OR FenLei3='软磁假睫毛' THEN '磁铁'
               WHEN FenLei1='甲片' THEN '甲片'
               ELSE NULL
           END) ProductType
      FROM ZiDian
     GROUP BY ZhuSKU
), ABProduct AS (
    SELECT SKU,
           MIN(CONVERT(NVARCHAR(10),FenZu)+'-'+CONVERT(NVARCHAR(10),XuHao)) ABValue
      FROM ABPin
     GROUP BY SKU
)
SELECT dp.YunYing,sd.Dian,COALESCE(sc.FenLei,'D'),i.SKU,
       i.TotalInventory,i.FbaSellable,ISNULL(t.PendingQty,0),ISNULL(s.SalesQty,0),
       vk.K_SKU,fd.FirstFbaDate,sh.FirstShipDate,ld.FirstLocDate,
       zd.GongYingShang,zd.ZhuSKU,pt.ProductType,ab.ABValue
  FROM InventoryRows i
  LEFT JOIN Transit t ON t.SKU=i.SKU
  LEFT JOIN Sales s ON s.SKU=i.SKU
  LEFT JOIN SKUDian sd ON sd.SKU=i.SKU
  LEFT JOIN v_PinPaiDianPu dp ON dp.Dian=sd.Dian
  LEFT JOIN StoreCategory sc ON sc.SKU=i.SKU AND sc.Dian=sd.Dian
  LEFT JOIN v_K vk ON vk.SKU=i.SKU
  LEFT JOIN FbaDate fd ON fd.SKU=i.SKU
  LEFT JOIN ShipDate sh ON sh.SKU=i.SKU
  LEFT JOIN LocDate ld ON ld.SKU=i.SKU
  LEFT JOIN ZiDian zd ON zd.SKU=i.SKU
  LEFT JOIN ProductType pt ON pt.ZhuSKU=COALESCE(zd.ZhuSKU,i.SKU)
  LEFT JOIN ABProduct ab ON ab.SKU=i.SKU
 WHERE ISNULL(i.TotalInventory,0)+ISNULL(t.PendingQty,0)<>0
 ORDER BY sd.Dian,i.SKU"""


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    match = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _compact_number(value: Any, *, default: int | float = 0) -> int | float:
    number = _as_number(value)
    if number is None:
        return default
    rounded = round(number)
    return int(rounded) if abs(number - rounded) < 1e-9 else round(number, 4)


def _available_days(stock: Any, daily_sales: Any, *, zero_stock_is_zero: bool = False) -> int:
    stock_number = _as_number(stock) or 0
    daily_number = _as_number(daily_sales) or 0
    if zero_stock_is_zero and stock_number == 0:
        return 0
    if daily_number <= 0:
        return 999
    return int(round(stock_number / daily_number))


def _comment_number(value: Any) -> str:
    number = _as_number(value)
    if number is None:
        return str(value or "").strip()
    compact = _compact_number(number)
    return str(compact)


def _comment_date(value: Any, *, short: bool = False) -> str:
    parsed = _coerce_date(value)
    if parsed is None:
        return str(value or "").strip()
    return parsed.strftime("%m.%d") if short else parsed.isoformat()


def _append_cell_comment(
    comments: dict[str, dict[str, str]],
    sku: Any,
    column_index: int,
    text: Any,
) -> None:
    sku_text = str(sku or "").strip()
    comment_text = str(text or "").replace("_x000D_\n", "\n").strip()
    if not sku_text or not comment_text:
        return
    row_comments = comments.setdefault(sku_text, {})
    key = str(column_index)
    existing = row_comments.get(key, "")
    if comment_text not in existing.split("\n\n"):
        row_comments[key] = f"{existing}\n\n{comment_text}".strip() if existing else comment_text


def _append_cell_style(
    styles: dict[str, dict[str, list[str]]],
    sku: Any,
    column_index: int,
    *tokens: str,
) -> None:
    sku_text = str(sku or "").strip()
    if not sku_text or not 0 <= column_index < len(DEFAULT_HEADERS):
        return
    cell_styles = styles.setdefault(sku_text, {}).setdefault(str(column_index), [])
    for token in tokens:
        normalized = str(token or "").strip()
        if normalized and normalized not in cell_styles:
            cell_styles.append(normalized)


def _recent_month_day(value: str, today: date) -> date | None:
    match = re.match(r"\s*(\d{1,2})\.(\d{1,2})", value)
    if not match:
        return None
    try:
        parsed = date(today.year, int(match.group(1)), int(match.group(2)))
    except ValueError:
        return None
    if parsed > today:
        try:
            parsed = parsed.replace(year=today.year - 1)
        except ValueError:
            return None
    return parsed


def _optional_comment_query(query_executor, sql: str) -> list[Any]:
    try:
        return list(query_executor(sql) or [])
    except Exception as exc:
        try:
            current_app.logger.warning("日常补货批注查询失败：%s", exc)
        except RuntimeError:
            pass
        return []


def generate_database_comments(
    settings: dict[str, Any],
    generated_rows: list[dict[str, Any]],
    *,
    query_executor=sf_db,
) -> dict[str, dict[str, str]]:
    """按原 VBA 的【批注】表规则生成页面和快照共用的单元格批注。"""
    today: date = settings["as_of_date"]
    parameters = dict(COMMENT_PARAMETER_DEFAULTS)
    parameters.update(settings.get("comment_parameters") or {})
    comments: dict[str, dict[str, str]] = {}
    rows_by_sku = {
        str(row["values"][3] or "").strip(): row
        for row in generated_rows
        if str(row["values"][3] or "").strip()
    }

    inventory_rows = _optional_comment_query(
        query_executor,
        """/* daily_replenishment:comments_inventory */
SELECT '库存' Kind,SKU,'本地' Detail,SUM(CAST(ISNULL(ShuLiang,0) AS FLOAT)) Qty
  FROM v_KuCun1
 WHERE SKU IN (SELECT SKU FROM ZiDian WHERE BaoHan<>'')
 GROUP BY SKU
UNION ALL
SELECT '库存',SKU,'FBA',SUM(CAST(ISNULL(KeShou,0)+ISNULL(DaiTiaoCang,0)+ISNULL(TiaoCangZhong,0)+ISNULL(ZaiTu,0) AS FLOAT))
  FROM v_KuCun2
 GROUP BY SKU
UNION ALL
SELECT '半成品',zd.ZhuSKU,kc.SKU,SUM(CAST(ISNULL(kc.ShuLiang,0) AS FLOAT))
  FROM v_KuCun1 kc
  LEFT JOIN ZiDian zd ON kc.SKU=zd.SKU
 WHERE kc.SKU NOT LIKE '%盒%'
   AND kc.SKU NOT LIKE '%半毛%'
   AND kc.SKU NOT LIKE '%不干胶%'
   AND kc.SKU IN (SELECT SKU FROM ZiDian WHERE BaoHan='')
   AND kc.ShuLiang>0
 GROUP BY zd.ZhuSKU,kc.SKU
 ORDER BY SKU,Kind,Detail""",
    )
    for raw in inventory_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 4:
            continue
        kind, sku, detail, quantity = raw[:4]
        if str(kind or "").strip() == "半成品":
            text = f"半成品：{detail}，数量：{_comment_number(quantity)}"
        else:
            text = f"{detail}：{_comment_number(quantity)}"
        _append_cell_comment(comments, sku, 4, text)

    fba_rows = _optional_comment_query(
        query_executor,
        """/* daily_replenishment:comments_fba */
SELECT SKU,SUM(KeShou),SUM(DaiTiaoCang),SUM(TiaoCangZhong),SUM(ZaiTu)
  FROM v_KuCun2
 GROUP BY SKU
 ORDER BY SKU""",
    )
    for raw in fba_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 5:
            continue
        sku, sellable, pending_transfer, transferring, in_transit = raw[:5]
        text = (
            f"可售量：{_comment_number(sellable)}\n"
            f"待调仓：{_comment_number(pending_transfer)}\n"
            f"调仓中：{_comment_number(transferring)}\n"
            f"在途量：{_comment_number(in_transit)}"
        )
        _append_cell_comment(comments, sku, 5, text)

    transit_start = (today - timedelta(days=122)).isoformat()
    transit_rows = _optional_comment_query(
        query_executor,
        f"""/* daily_replenishment:comments_shipping_transit */
SELECT SKU,Guo,ChuangJianShiJian,FaHuoLiang,QianShouLiang,
       FaHuoLiang-QianShouLiang,datediff(DAY,ChuangJianShiJian,GETDATE())
  FROM v_FBAHuoJian
 WHERE ChuangJianShiJian>='{transit_start}'
   AND YunShuFangShi2 IN ('海运','空派')
   AND FaHuoLiang-QianShouLiang>=30
 ORDER BY SKU,ChuangJianShiJian""",
    )
    transit_by_sku: dict[str, list[str]] = defaultdict(list)
    for raw in transit_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 7:
            continue
        sku, country, created, sent, received, difference, elapsed = raw[:7]
        transit_by_sku[str(sku or "").strip()].append(
            f"{country}，{_comment_date(created)}，{_comment_number(sent)}-"
            f"{_comment_number(received)}={_comment_number(difference)}，{_comment_number(elapsed)}天"
        )
    for sku, details in transit_by_sku.items():
        _append_cell_comment(comments, sku, 5, "近120天海运在途信息：\n" + "\n".join(details))

    pending_rows = _optional_comment_query(
        query_executor,
        """/* daily_replenishment:comments_pending */
SELECT zd.ZhuSKU,cgd.XiaDanRiQi,cgd.DanHao,cgd.GongYingShang,
       cgd.CaiGouLiang,cgd.DaoHuoLiang,cgd.DaiDaoHuoLiang,
       ISNULL(gys.FuZeRen,'未定义')
  FROM CaiGouDan cgd
  LEFT JOIN ZiDian zd ON cgd.SKU=zd.SKU
  LEFT JOIN GongYingShang gys ON cgd.GongYingShang=gys.ID AND gys.YorN='Y'
 WHERE cgd.CaiGouZhuangTai='待到货' AND cgd.DaiDaoHuoLiang>0
 ORDER BY zd.ZhuSKU,cgd.XiaDanRiQi,cgd.DanHao""",
    )
    for raw in pending_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 8:
            continue
        sku, ordered, number, supplier, ordered_qty, arrived_qty, pending_qty, owner = raw[:8]
        supplier_text = str(supplier or "").strip()
        supplier_text = supplier_text.zfill(2) if supplier_text.isdigit() else supplier_text
        text = (
            f"{_comment_date(ordered)}，{number}，{supplier_text}，"
            f"{_comment_number(ordered_qty)}-{_comment_number(arrived_qty)}="
            f"{_comment_number(pending_qty)}，{owner}"
        )
        _append_cell_comment(comments, sku, 6, text)

    seven_start = (today - timedelta(days=8)).isoformat()
    three_start = (today - timedelta(days=4)).isoformat()
    sales_end = (today - timedelta(days=2)).isoformat()
    recent_sales_rows = _optional_comment_query(
        query_executor,
        f"""/* daily_replenishment:comments_recent_sales */
SELECT SKU,
       ROUND(SUM(CASE WHEN RiQi BETWEEN '{seven_start}' AND '{sales_end}' THEN HeSuanXiaoLiang ELSE 0 END)/7.0,1),
       ROUND(SUM(CASE WHEN RiQi BETWEEN '{three_start}' AND '{sales_end}' THEN HeSuanXiaoLiang ELSE 0 END)/3.0,1),
       SUM(CASE WHEN RiQi BETWEEN '{three_start}' AND '{sales_end}' THEN HeSuanXiaoLiang ELSE 0 END)
  FROM v_XiaoShouLiang
 WHERE RiQi BETWEEN '{seven_start}' AND '{sales_end}'
 GROUP BY SKU
 ORDER BY SKU""",
    )
    recent_sales: dict[str, tuple[Any, Any, Any]] = {}
    for raw in recent_sales_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 4:
            continue
        sku = str(raw[0] or "").strip()
        recent_sales[sku] = (raw[1], raw[2], raw[3])
        _append_cell_comment(
            comments,
            sku,
            8,
            f"近3天日均：{_comment_number(raw[2])}\n近7天日均：{_comment_number(raw[1])}",
        )

    previous_days = int(parameters["前两次库存天数"])
    previous_rows = _optional_comment_query(
        query_executor,
        f"""/* daily_replenishment:comments_previous_inventory */
WITH RunTimes AS (
    SELECT TOP 2 DaoRuShiJian
      FROM (SELECT DISTINCT DaoRuShiJian
              FROM BuHuoBiaoLiuCun
             WHERE DaoRuShiJian<'{today.isoformat()}') d
     ORDER BY DaoRuShiJian DESC
)
SELECT b.SKU,b.DaoRuShiJian,b.ZongKuCun,b.DaiDaoHuo,b.RiJunLiang,b.K,b.ZongKeShouTianShu
  FROM BuHuoBiaoLiuCun b
 WHERE b.DaoRuShiJian IN (SELECT DaoRuShiJian FROM RunTimes)
 ORDER BY b.SKU,b.DaoRuShiJian""",
    )
    previous_by_sku: dict[str, list[str]] = defaultdict(list)
    for raw in previous_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 7:
            continue
        sku, imported, inventory, pending, daily, k_value, days = raw[:7]
        previous_by_sku[str(sku or "").strip()].append(
            f"{_comment_date(imported, short=True)}：{_comment_number(inventory)} + "
            f"{_comment_number(pending)}，{_comment_number(daily)}，"
            f"{_comment_number(k_value)}，{_comment_number(days)}"
        )
    for sku, details in previous_by_sku.items():
        row = rows_by_sku.get(sku)
        if row and (_as_number(row["values"][12]) or 999) <= previous_days:
            _append_cell_comment(comments, sku, 12, "\n".join(details[-2:]))

    plan_days = int(parameters["最近的采购计划"])
    plan_start = (today - timedelta(days=plan_days)).isoformat()
    plan_rows = _optional_comment_query(
        query_executor,
        f"""/* daily_replenishment:comments_purchase_plan */
SELECT jh.ZhuSKU,jh.RiQi,jh.ShuLiang,jh.JiHuaBianHao,jh.GongYingShang,
       gys.FuZeRen,jh.BeiZhu
  FROM CaiGouJiHua jh
  LEFT JOIN GongYingShang gys ON jh.GongYingShang=gys.ID AND gys.YorN='Y'
 WHERE jh.ZhuangTai IN ('待审批','已完成','待采购')
   AND jh.RiQi>='{plan_start}'
 ORDER BY jh.ZhuSKU,jh.RiQi""",
    )
    plan_by_sku: dict[str, list[str]] = defaultdict(list)
    for raw in plan_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 7:
            continue
        sku, plan_date, quantity, number, supplier, owner, note = raw[:7]
        detail = (
            f"{_comment_date(plan_date)}，{_comment_number(quantity)}，{number}，"
            f"{supplier or ''}，{owner or ''}"
        )
        if str(note or "").strip():
            detail += f"，{str(note).strip()}"
        plan_by_sku[str(sku or "").strip()].append(detail)
    for sku, details in plan_by_sku.items():
        _append_cell_comment(
            comments,
            sku,
            13,
            f"最近 {plan_days} 天的采购计划：\n" + "\n".join(details),
        )

    delivery_days = int(parameters["到货时效天数"])
    delivery_end = today - timedelta(days=1)
    delivery_start = delivery_end - timedelta(days=delivery_days)
    delivery_ratio = float(parameters["到货时效比例"])
    delivery_rows = _optional_comment_query(
        query_executor,
        f"""/* daily_replenishment:comments_delivery_time */
SELECT ZhuSKU,平均到货天数,单数
  FROM get_daohuoshixiao('{delivery_start.isoformat()}','{delivery_end.isoformat()}',{delivery_ratio})
 ORDER BY ZhuSKU""",
    )
    for raw in delivery_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 3:
            continue
        _append_cell_comment(
            comments,
            raw[0],
            13,
            f"到货时效：{_comment_number(raw[1])}天，{_comment_number(raw[2])}次",
        )

    falling_threshold = int(parameters["持续下滑"])
    falling_start = (today - timedelta(days=16)).isoformat()
    falling_rows = _optional_comment_query(
        query_executor,
        f"""/* daily_replenishment:comments_falling */
SELECT SKU,COUNT(*)
  FROM K
 WHERE RiQi BETWEEN '{falling_start}' AND '{sales_end}'
   AND K_SKU<=-0.01
   AND SKU NOT IN (SELECT SKU FROM QingHuo)
 GROUP BY SKU
HAVING COUNT(*)>={falling_threshold}
 ORDER BY SKU""",
    )
    for raw in falling_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        sku = str(raw[0] or "").strip()
        row = rows_by_sku.get(sku)
        if row and (_as_number(row["values"][8]) or 0) > 3 and (_as_number(row["values"][9]) or 0) < 0:
            _append_cell_comment(comments, sku, 13, f"过去15天，有 {_comment_number(raw[1])} 天K值<=0，谨慎下单")

    order_days = int(parameters["最近找运营下单"])
    order_start = (today - timedelta(days=order_days)).isoformat()
    order_rows = _optional_comment_query(
        query_executor,
        f"""/* daily_replenishment:comments_operator_orders */
SELECT SKU,RiQi,DingHuoLiang,XiaDanLiang,BeiZhu
  FROM MeiTianXiaDan
 WHERE RiQi>='{order_start}'
 ORDER BY SKU,RiQi""",
    )
    orders_by_sku: dict[str, list[str]] = defaultdict(list)
    for raw in order_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 5:
            continue
        sku, ordered, requested, placed, note = raw[:5]
        detail = (
            f"{_comment_date(ordered, short=True)}，{_comment_number(requested)}"
            f"->{_comment_number(placed)}"
        )
        if str(note or "").strip():
            detail += f"，{str(note).strip()}"
        orders_by_sku[str(sku or "").strip()].append(detail)
    for sku, details in orders_by_sku.items():
        _append_cell_comment(
            comments,
            sku,
            14,
            f"最近 {order_days} 天找运营下单：\n" + "\n".join(details),
        )

    first_payment_rows = _optional_comment_query(
        query_executor,
        """/* daily_replenishment:comments_first_payment */
SELECT SKU,MIN(RiQi)
  FROM LiRun
 WHERE XiaoShouLiang>0
 GROUP BY SKU
 ORDER BY SKU""",
    )
    recent_product_days = int(parameters["最近开售"])
    short_sales_days = int(parameters["最近开售_销售天数"])
    for raw in first_payment_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        sku = str(raw[0] or "").strip()
        first_payment = _coerce_date(raw[1])
        _append_cell_comment(comments, sku, 15, f"首次付款日期：{_comment_date(raw[1])}")
        if first_payment and first_payment >= today - timedelta(days=recent_product_days):
            recent = recent_sales.get(sku)
            row = rows_by_sku.get(sku)
            if recent and row:
                short_start = today - timedelta(days=short_sales_days + 1)
                _append_cell_comment(
                    comments,
                    sku,
                    7,
                    f"此为最近 {short_sales_days} 天(从{short_start.month}.{short_start.day}到"
                    f"{settings['sales_end'].month}.{settings['sales_end'].day})的销量，\n"
                    f"最近 {recent_product_days} 天总销量："
                    f"{_comment_number(row['values'][7])}",
                )

    return comments


def generate_database_styles(
    settings: dict[str, Any],
    generated_rows: list[dict[str, Any]],
    comments_by_sku: dict[str, dict[str, str]],
    *,
    query_executor=sf_db,
) -> dict[str, dict[str, list[str]]]:
    """迁移原表“生成”宏中的主要字体、底色和斜体标记规则。"""
    today: date = settings["as_of_date"]
    parameters = dict(COMMENT_PARAMETER_DEFAULTS)
    parameters.update(settings.get("comment_parameters") or {})
    styles: dict[str, dict[str, list[str]]] = {}
    rows_by_sku = {
        str(row["values"][3] or "").strip(): row
        for row in generated_rows
        if str(row["values"][3] or "").strip()
    }

    # 不需要再查库的规则：批注内容与 VBA 的判断条件来自同一数据源。
    for sku, row in rows_by_sku.items():
        values = row["values"]
        comments = comments_by_sku.get(sku, {})
        inventory_comment = str(comments.get("4") or "")
        if "半成品：" in inventory_comment:
            _append_cell_style(styles, sku, 4, "mark-half-finished")
        if "本地：" in inventory_comment and "FBA：" not in inventory_comment:
            _append_cell_style(styles, sku, 3, "mark-only-local")

        fba_comment = str(comments.get("5") or "")
        if "近120天海运在途信息" in fba_comment:
            _append_cell_style(styles, sku, 5, "mark-shipping-transit")

        pending_comment = str(comments.get("6") or "")
        overdue_days = int(parameters["超过N天未到货"])
        for line in pending_comment.splitlines():
            ordered = _coerce_date(line)
            quantity_match = re.search(r"=\s*(-?\d+(?:\.\d+)?)，", line)
            pending_quantity = _as_number(quantity_match.group(1)) if quantity_match else None
            if ordered and ordered <= today - timedelta(days=overdue_days) and (pending_quantity or 0) > 10:
                _append_cell_style(styles, sku, 6, "mark-overdue")
                break

        sales_comment = str(comments.get("8") or "")
        three_match = re.search(r"近3天日均：\s*(-?\d+(?:\.\d+)?)", sales_comment)
        seven_match = re.search(r"近7天日均：\s*(-?\d+(?:\.\d+)?)", sales_comment)
        if three_match and seven_match:
            three_day = float(three_match.group(1))
            seven_day = float(seven_match.group(1))
            if three_day > seven_day * 1.1:
                _append_cell_style(styles, sku, 8, "mark-sales-rise")

        if str(comments.get("7") or "").strip():
            _append_cell_style(styles, sku, 7, "mark-recent-sales")

        first_payment_match = re.search(
            r"首次付款日期：\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            str(comments.get("15") or ""),
        )
        first_payment = _coerce_date(first_payment_match.group(1)) if first_payment_match else None
        if first_payment and first_payment > today - timedelta(days=int(parameters["新品标黄色"])):
            _append_cell_style(styles, sku, 15, "mark-new-product")

        plan_comment = str(comments.get("13") or "")
        if "谨慎下单" in plan_comment:
            _append_cell_style(styles, sku, 13, "mark-falling")
        if any(
            (parsed := _coerce_date(line)) is not None
            and parsed >= today - timedelta(days=1)
            for line in plan_comment.splitlines()
        ):
            _append_cell_style(styles, sku, 13, "mark-recent-plan")

        reduction_days = int(parameters["最近找运营下单_减量"])
        for line in str(comments.get("14") or "").splitlines():
            order_date = _recent_month_day(line, today)
            quantities = re.search(r"，\s*(-?\d+(?:\.\d+)?)\s*->\s*(-?\d+(?:\.\d+)?)", line)
            if not order_date or not quantities:
                continue
            requested = float(quantities.group(1))
            placed = float(quantities.group(2))
            if order_date >= today - timedelta(days=reduction_days) and placed < requested:
                _append_cell_style(styles, sku, 14, "mark-reduced-order")
                break

        daily_sales = _as_number(values[8]) or 0
        k_value = _as_number(values[9])
        if daily_sales > 0 and k_value is not None and k_value / daily_sales >= float(parameters["变异系数"]):
            _append_cell_style(styles, sku, 9, "mark-variation")

        sellable_days = _as_number(values[10])
        if sellable_days is not None and sellable_days <= int(parameters["可售天数标红"]):
            for column_index in range(10, 13):
                _append_cell_style(styles, sku, column_index, "mark-low-stock")

    status_rows = _optional_comment_query(
        query_executor,
        f"""/* daily_replenishment:comments_style_status */
SELECT 'clearance' Kind,SKU FROM QingHuo
UNION ALL
SELECT 'ocean',SKU FROM HaiYunSKU WHERE ZhengChang='Y'
UNION ALL
SELECT 'expedite',SKU FROM CuiHuo_SKU
 WHERE ShenPi='Y' AND ShenPiShiJian>='{(today - timedelta(days=20)).isoformat()}'
UNION ALL
SELECT 'low_inventory_fee',SKU FROM v_DiKuCunFei
ORDER BY Kind,SKU""",
    )
    for raw in status_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        kind, sku = str(raw[0] or "").strip(), raw[1]
        if kind == "clearance":
            for column_index in range(0, 17):
                _append_cell_style(styles, sku, column_index, "mark-clearance")
        elif kind == "ocean":
            for column_index in range(0, 19):
                _append_cell_style(styles, sku, column_index, "mark-ocean")
        elif kind == "expedite":
            _append_cell_style(styles, sku, 3, "mark-expedite")
        elif kind == "low_inventory_fee":
            _append_cell_style(styles, sku, 0, "mark-low-inventory-fee")

    new_local_rows = _optional_comment_query(
        query_executor,
        """/* daily_replenishment:comments_style_new_local */
SELECT ZhuSKU,MinRiQi FROM v_到本地仓日期 ORDER BY ZhuSKU""",
    )
    for raw in new_local_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        local_date = _coerce_date(raw[1])
        if local_date and local_date >= today - timedelta(days=90):
            for column_index in range(0, 3):
                _append_cell_style(styles, raw[0], column_index, "mark-new-local")

    surge_start = (today - timedelta(days=4)).isoformat()
    surge_rows = _optional_comment_query(
        query_executor,
        f"""/* daily_replenishment:comments_style_surge */
SELECT SKU,RiQi,XiaoLiang,ZhiQian3TianRiJun,BeiShu
  FROM QiLiang
 WHERE RiQi>='{surge_start}' AND XiaoLiang>2
   AND BeiShu>={float(parameters['起量倍数_系数'])}
 ORDER BY RiQi,SKU""",
    )
    surge_details: dict[str, list[str]] = defaultdict(list)
    for raw in surge_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 5:
            continue
        sku = str(raw[0] or "").strip()
        surge_details[sku].append(
            f"{_comment_date(raw[1], short=True)}，{_comment_number(raw[2])}/"
            f"{_comment_number(raw[3])}={_comment_number(raw[4])}"
        )
    for sku, details in surge_details.items():
        row = rows_by_sku.get(sku)
        if row and (_as_number(row["values"][12]) or 999) <= int(parameters["起量倍数_可售天数"]):
            _append_cell_style(styles, sku, 8, "mark-surge")
            _append_cell_comment(comments_by_sku, sku, 8, "\n".join(details))

    return styles


def generate_button_sheets(
    settings: dict[str, Any],
    *,
    query_executor=sf_db,
) -> dict[str, dict[str, Any]]:
    """同步原 VBA“生成日常补货表”按钮会重建的配套工作表。"""
    start = settings["sales_start"].isoformat()
    end = settings["sales_end"].isoformat()
    today: date = settings["as_of_date"]
    listing_days = int(settings.get("low_margin_listing_days") or 60)
    margin_days = int(settings.get("low_margin_recent_days") or 30)
    margin_threshold = float(settings.get("low_margin_threshold") or 0.1)

    definitions = {
        "库存明细": (
            ["位置", "SKU", "数量"],
            f"""/* daily_replenishment:sheet_inventory_detail */
SELECT CASE WHEN WeiZhi='LOC' THEN '本地' ELSE 'FBA' END,SKU,
       SUM(CAST(ISNULL(ShuLiang,0) AS FLOAT))
  FROM get_KuCun('{(today - timedelta(days=1)).isoformat()}')
 WHERE ShuLiang<>0
 GROUP BY CASE WHEN WeiZhi='LOC' THEN '本地' ELSE 'FBA' END,SKU
 ORDER BY 1 DESC,SKU""",
            "汇总本地与 FBA 库存，为日常补货生成 SKU 基础清单",
        ),
        "在途": (
            ["SKU", "主SKU", "在途"],
            """/* daily_replenishment:sheet_transit */
SELECT SKU,'@'+ZhuSKU,ZaiTu FROM v_ZaiTu ORDER BY ZhuSKU,SKU""",
            "同步待到货量，为日常补货的待到货量与批注提供数据",
        ),
        "FBA发货": (
            ["国", "分类", "仓", "店", "ASIN", "SKU", "FBA库存", "FBA在途", "本地库存", f"{settings['recent_days']}天销量", "有库存的天数", "日均销量", "FBA可售天数", "发货量", "发货后FBA可售天数", "K值", "均价($)", "MSKU", "待到货", "产品备注"],
            f"""/* daily_replenishment:sheet_fba_shipping */
WITH Base AS (
 SELECT Cang,Dian,ASIN,SKU,
        CAST(ISNULL(KeShou,0)+ISNULL(DaiTiaoCang,0)+ISNULL(TiaoCangZhong,0) AS FLOAT) FbaStock,
        CAST(ISNULL(ZaiTu,0)+ISNULL(RuCangZhong,0) AS FLOAT) FbaTransit
   FROM v_KuCun2 WHERE SKU<>'0'
), Sales AS (
 SELECT Guo,SKU,SUM(HeSuanXiaoLiang) Qty
   FROM v_XiaoShouLiang WHERE RiQi BETWEEN '{start}' AND '{end}' GROUP BY Guo,SKU
), LocalStock AS (
 SELECT SKU,SUM(CAST(ISNULL(ShuLiang,0) AS FLOAT)) Qty FROM v_KuCun1 GROUP BY SKU
), Pending AS (
 SELECT ZhuSKU SKU,SUM(CAST(ISNULL(ZaiTu,0) AS FLOAT)) Qty FROM v_ZaiTu GROUP BY ZhuSKU
)
SELECT CASE b.Cang WHEN '欧洲仓' THEN '英国' WHEN '英国仓' THEN '英国'
            WHEN '美国仓' THEN '美国' WHEN '加拿大仓' THEN '加拿大'
            WHEN '澳洲仓' THEN '澳洲' ELSE b.Cang END,
       ISNULL(fc.FenLei,'D'),b.Cang,b.Dian,b.ASIN,b.SKU,b.FbaStock,b.FbaTransit,
       ISNULL(ls.Qty,0),ISNULL(s.Qty,0),{settings['recent_days']},
       ROUND(ISNULL(s.Qty,0)/{float(settings['recent_days'])},1),
       CASE WHEN ISNULL(s.Qty,0)=0 THEN 999 ELSE ROUND((b.FbaStock+b.FbaTransit)/(s.Qty/{float(settings['recent_days'])}),0) END,
       0,
       CASE WHEN ISNULL(s.Qty,0)=0 THEN 999 ELSE ROUND((b.FbaStock+b.FbaTransit)/(s.Qty/{float(settings['recent_days'])}),0) END,
       ISNULL(kg.K,0),NULL,ms.MSKU,ISNULL(p.Qty,0),NULL
  FROM Base b
  LEFT JOIN Sales s ON s.SKU=b.SKU AND s.Guo=CASE b.Cang WHEN '欧洲仓' THEN '英国' WHEN '英国仓' THEN '英国' WHEN '美国仓' THEN '美国' WHEN '加拿大仓' THEN '加拿大' WHEN '澳洲仓' THEN '澳洲' ELSE b.Cang END
  LEFT JOIN LocalStock ls ON ls.SKU=b.SKU
  LEFT JOIN Pending p ON p.SKU=b.SKU
  LEFT JOIN v_FenLei fc ON fc.SKU=b.SKU AND fc.Dian=b.Dian
  LEFT JOIN v_k_Guo kg ON kg.SKU=b.SKU AND kg.Guo=s.Guo
  LEFT JOIN MSKU ms ON ms.SKU=b.SKU AND ms.ASIN=b.ASIN AND ms.Guo=s.Guo AND ms.MSKU NOT LIKE '%Amazon%'
 ORDER BY b.Dian,b.SKU,ISNULL(s.Qty,0) DESC""",
            "按站点同步 FBA 库存、在途、销量、可售天数与发货量",
        ),
        "每日库存": (
            ["SKU", "仓", "日期", "可售量", "可售+待调仓+调仓中"],
            f"""/* daily_replenishment:sheet_daily_inventory */
SELECT SKU,Cang,RiQi,SUM(KeShou),SUM(KeShou+DaiTiaoCang+TiaoCangZhong)
  FROM KuCun2
 WHERE RiQi BETWEEN '{start}' AND '{end}'
 GROUP BY SKU,Cang,RiQi
HAVING SUM(KeShou+DaiTiaoCang+TiaoCangZhong)>0
 ORDER BY SKU,Cang,RiQi""",
            "保留近期逐日 FBA 库存，供 FBA 发货的有库存天数计算",
        ),
        "海运即将到货": (
            ["创建时间", "单号", "店", "国", "SKU", "发货量", "签收量", "开船日期", "到港日期", "配送地址", "区域", "州", "城市"],
            f"""/* daily_replenishment:sheet_ocean_arrivals */
SELECT ChuangJianShiJian,DanHao,Dian,Guo,SKU,FaHuoLiang,QianShouLiang,
       KaiChuanRiQi,DaoGangRiQi,PeiSongDiZhi,QuYu,Zhou,ChengShi
  FROM v_FBAHuoJian
 WHERE ChuangJianShiJian>='{(today - timedelta(days=90)).isoformat()}'
   AND SKU IN (SELECT SKU FROM v_HaiYunSKU)
   AND Guo='美国' AND YunShuFangShi='海运-5'
   AND FaHuoLiang-QianShouLiang>50
   AND DaoGangRiQi>='{(today - timedelta(days=20)).isoformat()}'
 ORDER BY ChuangJianShiJian""",
            "同步近 90 天发货且近 20 天到港的未签收海运 SKU",
        ),
        "低毛利率": (
            ["SKU", "近期销售额", "近期毛利", "毛利率", "筛选规则"],
            f"""/* daily_replenishment:sheet_low_margin */
SELECT SKU,SUM(XiaoShouE),SUM(MaoLiRun),
       SUM(MaoLiRun)/(SUM(MaoLiLvFenMu)+0.0001),
       '上架>{listing_days}天，近{margin_days}天毛利率<={margin_threshold}'
  FROM v_MaoLiLv
 WHERE SKU IN (SELECT SKU FROM GuangGao WHERE ShuLiang>0 GROUP BY SKU
                HAVING MIN(RiQi)<=DATEADD(day,-{listing_days},GETDATE()))
   AND RiQi>='{(today - timedelta(days=margin_days)).isoformat()}' AND XiaoShouE<>0
 GROUP BY SKU
HAVING SUM(MaoLiRun)/(SUM(MaoLiLvFenMu)+0.0001)<={margin_threshold}
 ORDER BY SKU""",
            "同步原按钮完成后自动执行的低毛利率筛选",
        ),
    }

    sheets: dict[str, dict[str, Any]] = {}
    for name, (columns, sql, purpose) in definitions.items():
        try:
            rows = list(query_executor(sql) or [])
        except Exception as exc:
            raise DailyReplenishmentError(f"同步“{name}”工作表失败：{exc}") from exc
        sheets[name] = {
            "columns": list(columns),
            "rows": [list(row[: len(columns)]) for row in rows if isinstance(row, (list, tuple))],
            "purpose": purpose,
        }
    return sheets


def generate_database_dataset(
    settings: dict[str, Any],
    *,
    query_executor=sf_db,
) -> dict[str, Any]:
    try:
        core_rows = query_executor(_generation_sql(settings)) or []
        site_rows = query_executor(
            "/* daily_replenishment:sites */\n"
            "SELECT DISTINCT SKU,Guo\n"
            "  FROM v_Listing\n"
            " WHERE SKU IS NOT NULL AND Guo IS NOT NULL\n"
            "   AND LTRIM(RTRIM(SKU))<>'' AND LTRIM(RTRIM(Guo))<>''\n"
            " ORDER BY SKU,Guo"
        ) or []
    except Exception as exc:
        raise DailyReplenishmentError(f"从数据库生成日常补货表失败：{exc}") from exc

    countries_by_sku: dict[str, list[str]] = defaultdict(list)
    for raw in site_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        sku = str(raw[0] or "").strip()
        country = str(raw[1] or "").strip()
        if sku and country and country not in countries_by_sku[sku]:
            countries_by_sku[sku].append(country)

    columns = list(DEFAULT_HEADERS)
    columns[7] = str(settings["sales_header"])
    generated_rows: list[dict[str, Any]] = []
    for raw in core_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 16:
            continue
        (
            operator,
            store,
            classification,
            sku,
            total_inventory,
            fba_sellable,
            pending,
            sales,
            k_value,
            first_fba,
            first_ship,
            first_loc,
            factory,
            _main_sku,
            product_type,
            ab_value,
        ) = raw[:16]
        sku_text = str(sku or "").strip()
        if not sku_text:
            continue

        total_value = _compact_number(total_inventory)
        fba_value = _compact_number(fba_sellable)
        pending_value = _compact_number(pending)
        sales_value = _compact_number(sales)
        first_fba_date = _coerce_date(first_fba)
        elapsed_days = (
            (settings["as_of_date"] - first_fba_date).days
            if first_fba_date is not None
            else settings["recent_days"]
        )
        denominator = min(settings["recent_days"], max(elapsed_days, 1))
        daily_sales = round((_as_number(sales_value) or 0) / denominator, 1)

        if first_fba_date is not None:
            arrival_value: Any = first_fba_date
        elif _coerce_date(first_ship) is not None:
            arrival_value = f"发FBA：{_coerce_date(first_ship).isoformat()}"
        elif _coerce_date(first_loc) is not None:
            arrival_value = f"到本地：{_coerce_date(first_loc).isoformat()}"
        else:
            arrival_value = None

        countries = countries_by_sku.get(sku_text, [])
        site_value = f"{len(countries)}：{'、'.join(countries)}" if countries else None
        stock_with_pending = (_as_number(total_value) or 0) + (_as_number(pending_value) or 0)
        values = [
            str(operator).strip() if operator not in (None, "") else ("图创" if sku_text == "0" else None),
            store,
            str(classification or "D").strip() or "D",
            sku_text,
            total_value,
            fba_value,
            pending_value,
            sales_value,
            daily_sales,
            round(_as_number(k_value), 2) if _as_number(k_value) is not None else None,
            _available_days(fba_value, daily_sales, zero_stock_is_zero=True),
            _available_days(total_value, daily_sales),
            _available_days(stock_with_pending, daily_sales),
            0,
            _available_days(stock_with_pending, daily_sales),
            arrival_value,
            str(factory).strip() if factory not in (None, "") else None,
            None,
            str(product_type).strip() if product_type not in (None, "") else None,
            str(ab_value).strip() if ab_value not in (None, "") else None,
            site_value,
        ]
        generated_rows.append({"row_number": 0, "values": values})

    def sort_key(row: dict[str, Any]):
        values = row["values"]
        store_number = _as_number(values[1])
        return (
            store_number is None,
            store_number if store_number is not None else 0,
            str(values[19] or ""),
            str(values[3] or ""),
        )

    generated_rows.sort(key=sort_key)
    for row_number, row in enumerate(generated_rows, start=2):
        row["row_number"] = row_number

    comments_by_sku = generate_database_comments(
        settings,
        generated_rows,
        query_executor=query_executor,
    )
    styles_by_sku = generate_database_styles(
        settings,
        generated_rows,
        comments_by_sku,
        query_executor=query_executor,
    )
    for row in generated_rows:
        sku = str(row["values"][3] or "").strip()
        row["comments"] = dict(comments_by_sku.get(sku) or {})
        row["styles"] = {
            str(index): list(tokens)
            for index, tokens in dict(styles_by_sku.get(sku) or {}).items()
        }

    generation = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "as_of_date": settings["as_of_date"].isoformat(),
        "sales_start": settings["sales_start"].isoformat(),
        "sales_end": settings["sales_end"].isoformat(),
        "sales_header": settings["sales_header"],
        "recent_days": settings["recent_days"],
        "sales_source": settings["sales_source"],
        "generator": SNAPSHOT_GENERATOR_VERSION,
    }
    return {
        "columns": columns,
        "rows": generated_rows,
        "header_comments": {
            "2": "黑底白字：90天内到本地仓的新品",
            "3": "红色加粗字体：只在本地仓有库存",
            "4": "黄色底色：本地仓有半成品库存",
            "6": "数据来自本地库存，不是CaiGouDan",
            "7": "从2024-10-09开始，销量数据从v_XiaoShouLiang中取数",
        },
        "order_notes": {},
        "generation": generation,
    }


def _parse_order_quantity(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise DailyReplenishmentError(f"订货量“{value}”不是有效数字") from exc
    return int(number) if number.is_integer() else number


def apply_edits(dataset: dict[str, Any], edits: Any) -> int:
    if edits in (None, ""):
        return 0
    if not isinstance(edits, list):
        raise DailyReplenishmentError("编辑内容格式不正确")
    if len(edits) > len(dataset["rows"]):
        raise DailyReplenishmentError("编辑行数超出表格范围")

    row_map = {int(row["row_number"]): row for row in dataset["rows"]}
    changed = 0
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        try:
            row_number = int(edit.get("row_number"))
        except (TypeError, ValueError) as exc:
            raise DailyReplenishmentError("编辑行号无效") from exc
        row = row_map.get(row_number)
        if row is None:
            raise DailyReplenishmentError(f"表格中找不到第 {row_number} 行")

        expected_sku = str(edit.get("sku") or "").strip()
        actual_sku = str(row["values"][3] or "").strip()
        if expected_sku and expected_sku != actual_sku:
            raise DailyReplenishmentError(f"SKU {expected_sku} 已变更位置，请重新生成后再保存")

        if "order_quantity" in edit:
            new_quantity = _parse_order_quantity(edit.get("order_quantity"))
            if row["values"][13] != new_quantity:
                row["values"][13] = new_quantity
                changed += 1
        if "remark" in edit:
            new_remark = str(edit.get("remark") or "").strip()
            if len(new_remark) > MAX_REMARK_LENGTH:
                raise DailyReplenishmentError(f"SKU {actual_sku} 的备注超过 {MAX_REMARK_LENGTH} 字")
            if str(row["values"][17] or "") != new_remark:
                row["values"][17] = new_remark or None
                changed += 1
    return changed


def _format_remark_date(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime("%y-%m-%d")
    text = str(value or "").strip()
    match = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if match:
        return f"{int(match.group(1)) % 100:02d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return text[:10]


def fetch_database_remarks() -> dict[str, str]:
    remarks: dict[str, list[str]] = defaultdict(list)
    base_rows = sf_db(
        "SELECT SKU,RiQi,BeiZhu\n"
        "  FROM ChanPinBeiZhu\n"
        " WHERE YorN='Y' and TianJiaRen like '%@毕景春'\n"
        " ORDER BY SKU,RiQi"
    ) or []
    for row in base_rows:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        sku = str(row[0] or "").strip()
        text = str(row[2] or "").strip()
        if sku and text:
            remarks[sku].append(f"[{_format_remark_date(row[1])}]{text}")

    priority_rows = sf_db(
        "SELECT SKU,TianJiaShiJian,BeiZhu\n"
        "  FROM ZhongDianPin\n"
        " WHERE YOrN='Y'\n"
        " ORDER BY TianJiaShiJian desc"
    ) or []
    for row in priority_rows:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        sku = str(row[0] or "").strip()
        text = str(row[2] or "").strip()
        if sku:
            remarks[sku].append(f"[{_format_remark_date(row[1])}]重点品：{text}")
    return {sku: "\n".join(parts) for sku, parts in remarks.items()}


def apply_database_remarks(dataset: dict[str, Any], remarks: dict[str, str]) -> int:
    changed = 0
    for row in dataset["rows"]:
        sku = str(row["values"][3] or "").strip()
        value = remarks.get(sku) or None
        if row["values"][17] != value:
            row["values"][17] = value
            changed += 1
    return changed


def _write_literal(cell, value: Any) -> None:
    cell.value = value
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        cell.data_type = "s"


def _style_worksheet(sheet, row_count: int, column_count: int) -> None:
    header_fill = PatternFill("solid", fgColor="4F46E5")
    header_font = Font(name="Microsoft YaHei", size=10, bold=True, color="FFFFFF")
    body_font = Font(name="Microsoft YaHei", size=10, color="111827")
    thin_gray = Side(style="thin", color="D8DEE9")
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    sheet.auto_filter.ref = f"A1:{get_column_letter(column_count)}{max(row_count, 1)}"
    sheet.row_dimensions[1].height = 34
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=thin_gray)

    widths = [12, 8, 8, 18, 11, 11, 11, 13, 11, 9, 13, 14, 14, 10, 13, 16, 10, 42, 12, 10, 13]
    for index in range(1, column_count + 1):
        sheet.column_dimensions[get_column_letter(index)].width = widths[index - 1] if index <= len(widths) else 16

    for row in sheet.iter_rows(min_row=2, max_row=row_count, max_col=column_count):
        for index, cell in enumerate(row, start=1):
            cell.font = body_font
            cell.alignment = Alignment(
                horizontal="left" if index in (1, 4, 18) else "center",
                vertical="center",
                wrap_text=index == 18,
            )
            cell.border = Border(bottom=Side(style="hair", color="E5E7EB"))
        if len(row) >= 14 and _as_number(row[13].value) not in (None, 0):
            row[13].fill = PatternFill("solid", fgColor="FEF3C7")
            row[13].font = Font(name="Microsoft YaHei", size=10, bold=True, color="92400E")
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0


def _add_dataset_sheet(workbook: Workbook, name: str, columns: list[str], rows: list[list[Any]]):
    sheet = workbook.create_sheet(title=name)
    for column_index, value in enumerate(columns, start=1):
        _write_literal(sheet.cell(row=1, column=column_index), value)
    for row_index, values in enumerate(rows, start=2):
        for column_index, value in enumerate(values, start=1):
            _write_literal(sheet.cell(row=row_index, column=column_index), value)
    _style_worksheet(sheet, len(rows) + 1, len(columns))
    return sheet


def _new_export_workbook() -> Workbook:
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.creator = "图创AI系统"
    workbook.properties.lastModifiedBy = "图创AI系统"
    return workbook


def _apply_cell_business_styles(cell, raw_tokens: Any) -> None:
    tokens = {str(token).strip() for token in (raw_tokens or []) if str(token).strip()}
    if not tokens:
        return

    fill_color: str | None = None
    if "mark-clearance" in tokens:
        fill_color = "A6A6A6"
    if "mark-variation" in tokens:
        fill_color = "00B0F0"
    if "mark-surge" in tokens:
        fill_color = "D9EAF7"
    if tokens.intersection(
        {
            "mark-half-finished",
            "mark-shipping-transit",
            "mark-overdue",
            "mark-new-product",
            "mark-reduced-order",
            "mark-low-inventory-fee",
        }
    ):
        fill_color = "FFFF00"
    if "mark-recent-sales" in tokens:
        fill_color = "00B050"
    if "mark-low-stock" in tokens:
        fill_color = "FF0000"
    if tokens.intersection({"mark-falling", "mark-new-local"}):
        fill_color = "000000"
    if fill_color:
        cell.fill = PatternFill("solid", fgColor=fill_color)

    font = copy(cell.font)
    if tokens.intersection(
        {"mark-only-local", "mark-expedite", "mark-shipping-transit"}
    ):
        font.color = "FF0000"
        font.bold = True
    if "mark-ocean" in tokens:
        font.color = "0070C0"
        font.bold = True
    if tokens.intersection({"mark-sales-rise", "mark-low-inventory-fee"}):
        font.color = "FF0000"
        font.bold = True
    if tokens.intersection({"mark-falling", "mark-new-local"}):
        font.color = "FFFFFF"
    if "mark-recent-plan" in tokens:
        font.italic = True
    cell.font = font


def _save_dataset_workbook(dataset: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook = _new_export_workbook()
    data_sheet = _add_dataset_sheet(
        workbook,
        SHEET_NAME,
        list(dataset["columns"]),
        [list(row["values"]) for row in dataset["rows"]],
    )
    header_comments = dict(dataset.get("header_comments") or {})
    comment_records: list[list[Any]] = []
    for raw_index, raw_comment in header_comments.items():
        try:
            column_index = int(raw_index)
        except (TypeError, ValueError):
            continue
        comment_text = str(raw_comment or "").strip()
        if not comment_text or not 0 <= column_index < len(DEFAULT_HEADERS):
            continue
        data_sheet.cell(row=1, column=column_index + 1).comment = Comment(
            comment_text[:32767],
            COMMENT_AUTHOR,
        )
        comment_records.append([1, column_index, comment_text])
    for row in dataset["rows"]:
        row_number = int(row["row_number"])
        for raw_index, raw_comment in dict(row.get("comments") or {}).items():
            try:
                column_index = int(raw_index)
            except (TypeError, ValueError):
                continue
            comment_text = str(raw_comment or "").strip()
            if not comment_text or not 0 <= column_index < len(DEFAULT_HEADERS):
                continue
            data_sheet.cell(row=row_number, column=column_index + 1).comment = Comment(
                comment_text[:32767],
                COMMENT_AUTHOR,
            )
            comment_records.append([row_number, column_index, comment_text])
    style_records: list[list[Any]] = []
    for row in dataset["rows"]:
        row_number = int(row["row_number"])
        for raw_index, raw_tokens in dict(row.get("styles") or {}).items():
            try:
                column_index = int(raw_index)
            except (TypeError, ValueError):
                continue
            tokens = [
                str(token).strip()
                for token in (raw_tokens or [])
                if str(token).strip()
            ]
            if not tokens or not 0 <= column_index < len(DEFAULT_HEADERS):
                continue
            _apply_cell_business_styles(
                data_sheet.cell(row=row_number, column=column_index + 1),
                tokens,
            )
            style_records.append([row_number, column_index, " ".join(tokens)])
    if comment_records:
        comment_sheet = _add_dataset_sheet(
            workbook,
            COMMENT_SHEET_NAME,
            ["行号", "列序号", "批注"],
            comment_records,
        )
        comment_sheet.sheet_state = "hidden"
    if style_records:
        style_sheet = _add_dataset_sheet(
            workbook,
            STYLE_SHEET_NAME,
            ["行号", "列序号", "样式"],
            style_records,
        )
        style_sheet.sheet_state = "hidden"
    order_notes = dict(dataset.get("order_notes") or {})
    if order_notes:
        _add_dataset_sheet(
            workbook,
            "下单备注",
            ["SKU", "下单备注"],
            [[sku, note] for sku, note in order_notes.items()],
        )
    generation = dict(dataset.get("generation") or {})
    if generation:
        info_sheet = workbook.create_sheet(title="_生成信息")
        for row_index, (key, value) in enumerate(generation.items(), start=1):
            _write_literal(info_sheet.cell(row=row_index, column=1), key)
            _write_literal(info_sheet.cell(row=row_index, column=2), _json_value(value))
        info_sheet.sheet_state = "hidden"
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".xlsx", delete=False) as tmp:
        temp_path = Path(tmp.name)
    try:
        workbook.save(temp_path)
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)
        workbook.close()
    with _cache_lock:
        _sheet_cache.clear()
    return destination


def save_remark_capture(dataset: dict[str, Any]) -> Path:
    output_dir = get_output_dir(create=True)
    stamp = datetime.now().strftime("%y%m%d_%H%M%S")
    destination = output_dir / f"{stamp}日常补货_备注.xlsx"
    return _save_dataset_workbook(dataset, destination)


def update_today_snapshot(dataset: dict[str, Any]) -> Path:
    snapshot = get_today_snapshot()
    if snapshot is None:
        raise DailyReplenishmentError("今日快照尚未生成，请先点击“刷新今日快照”")
    return _save_dataset_workbook(dataset, snapshot)


def _source_static_comments(source: Path | None) -> dict[str, Any]:
    """读取模板中不会被 Workbook_BeforeClose 清除的人工批注（主要是 T 列）。"""
    empty = {"header_comments": {}, "comments_by_sku": {}}
    if source is None or not _is_supported_workbook(source):
        return empty
    stat = source.stat()
    cache_key = (str(source.resolve()), stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        cached = _source_comment_cache.get(cache_key)
    if cached is not None:
        return {
            "header_comments": dict(cached["header_comments"]),
            "comments_by_sku": {
                sku: dict(values) for sku, values in cached["comments_by_sku"].items()
            },
        }

    try:
        with ZipFile(source) as archive:
            main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            document_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            workbook_root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relation_id = None
            for node in workbook_root.findall(f".//{{{main_ns}}}sheet"):
                if node.get("name") == SHEET_NAME:
                    relation_id = node.get(f"{{{document_rel_ns}}}id")
                    break
            if not relation_id:
                return empty

            workbook_rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            worksheet_target = None
            for relation in workbook_rels.findall(f"{{{package_rel_ns}}}Relationship"):
                if relation.get("Id") == relation_id:
                    worksheet_target = relation.get("Target")
                    break
            if not worksheet_target:
                return empty
            worksheet_part = worksheet_target.lstrip("/")
            if not worksheet_part.startswith("xl/"):
                worksheet_part = posixpath.normpath(posixpath.join("xl", worksheet_part))
            worksheet_rels_part = posixpath.join(
                posixpath.dirname(worksheet_part),
                "_rels",
                posixpath.basename(worksheet_part) + ".rels",
            )
            if worksheet_rels_part not in archive.namelist():
                return empty
            worksheet_rels = ElementTree.fromstring(archive.read(worksheet_rels_part))
            comments_target = None
            for relation in worksheet_rels.findall(f"{{{package_rel_ns}}}Relationship"):
                if str(relation.get("Type") or "").endswith("/comments"):
                    comments_target = relation.get("Target")
                    break
            if not comments_target:
                return empty
            comments_part = posixpath.normpath(
                posixpath.join(posixpath.dirname(worksheet_part), comments_target)
            )
            comments_root = ElementTree.fromstring(archive.read(comments_part))
            comments_by_ref: dict[str, str] = {}
            for node in comments_root.findall(f".//{{{main_ns}}}comment"):
                cell_ref = str(node.get("ref") or "").upper()
                text = "".join(
                    value.text or ""
                    for value in node.findall(f".//{{{main_ns}}}t")
                ).replace("_x000D_\n", "\n").strip()
                if cell_ref and text:
                    comments_by_ref[cell_ref] = text
    except (BadZipFile, KeyError, OSError, ElementTree.ParseError):
        return empty

    row_skus: dict[int, str] = {}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            workbook = load_workbook(source, read_only=True, data_only=True, keep_links=False)
        try:
            if SHEET_NAME not in workbook.sheetnames:
                return empty
            blank_streak = 0
            for row_number, (sku,) in enumerate(
                workbook[SHEET_NAME].iter_rows(
                    min_row=2,
                    min_col=4,
                    max_col=4,
                    values_only=True,
                ),
                start=2,
            ):
                sku_text = str(sku or "").strip()
                if not sku_text:
                    blank_streak += 1
                    if row_skus and blank_streak >= 100:
                        break
                    continue
                blank_streak = 0
                row_skus[row_number] = sku_text
        finally:
            workbook.close()
    except Exception:
        return empty

    header_comments: dict[str, str] = {}
    comments_by_sku: dict[str, dict[str, str]] = {}
    for cell_ref, comment in comments_by_ref.items():
        match = re.fullmatch(r"([A-Z]+)(\d+)", cell_ref)
        if not match:
            continue
        letters, raw_row = match.groups()
        column_number = 0
        for character in letters:
            column_number = column_number * 26 + (ord(character) - 64)
        column_index = column_number - 1
        row_number = int(raw_row)
        if not 0 <= column_index < len(DEFAULT_HEADERS):
            continue
        if row_number == 1:
            header_comments[str(column_index)] = comment
        elif column_index >= 17 and row_number in row_skus:
            comments_by_sku.setdefault(row_skus[row_number], {})[str(column_index)] = comment

    result = {
        "header_comments": header_comments,
        "comments_by_sku": comments_by_sku,
    }
    with _cache_lock:
        _source_comment_cache.clear()
        _source_comment_cache[cache_key] = {
            "header_comments": dict(header_comments),
            "comments_by_sku": {
                sku: dict(values) for sku, values in comments_by_sku.items()
            },
        }
    return result


def _merge_source_static_comments(dataset: dict[str, Any], source: Path | None) -> None:
    source_comments = _source_static_comments(source)
    dataset.setdefault("header_comments", {}).update(source_comments["header_comments"])
    comments_by_sku = source_comments["comments_by_sku"]
    for row in dataset["rows"]:
        sku = str(row["values"][3] or "").strip()
        for column_index, comment in comments_by_sku.get(sku, {}).items():
            existing = str(row.setdefault("comments", {}).get(column_index) or "").strip()
            row["comments"][column_index] = (
                f"{existing}\n\n{comment}" if existing and comment not in existing else comment
            )


def refresh_today_snapshot(
    source: Path | None = None,
    *,
    recent_days: Any = None,
    sales_source: Any = None,
) -> tuple[Path, dict[str, Any], int]:
    snapshot = get_snapshot_path()
    reservation = snapshot.with_suffix(snapshot.suffix + ".lock")
    with _snapshot_lock:
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        reservation_fd = None
        try:
            try:
                reservation_fd = os.open(
                    reservation,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError as exc:
                try:
                    stale_reservation = time.time() - reservation.stat().st_mtime > 1800
                except OSError:
                    stale_reservation = False
                if not stale_reservation:
                    raise DailySnapshotRefreshInProgress("今日快照正在刷新，请稍后重试") from exc
                reservation.unlink(missing_ok=True)
                try:
                    reservation_fd = os.open(
                        reservation,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    )
                except FileExistsError as retry_exc:
                    raise DailySnapshotRefreshInProgress("今日快照正在刷新，请稍后重试") from retry_exc

            settings = get_generation_settings(
                source,
                recent_days=recent_days,
                sales_source=sales_source,
            )
            dataset = generate_database_dataset(settings)
            _merge_source_static_comments(dataset, source)
            database_remarks = fetch_database_remarks()
            apply_database_remarks(dataset, database_remarks)
            _save_dataset_workbook(dataset, snapshot)
            return snapshot, dataset, len(database_remarks)
        finally:
            if reservation_fd is not None:
                os.close(reservation_fd)
                reservation.unlink(missing_ok=True)


def _safe_sheet_name(raw_name: Any, used: set[str]) -> str:
    name = re.sub(r"[\\/*?:\[\]]", "_", str(raw_name or "未分配").strip())[:31] or "未分配"
    candidate = name
    suffix = 2
    while candidate.casefold() in used:
        marker = f"_{suffix}"
        candidate = f"{name[: 31 - len(marker)]}{marker}"
        suffix += 1
    used.add(candidate.casefold())
    return candidate


def build_split_workbook(dataset: dict[str, Any], batch: int) -> tuple[BytesIO, int]:
    if batch not in (1, 2):
        raise DailyReplenishmentError("批次只能选择 1（上午）或 2（下午）")
    selected: list[dict[str, Any]] = []
    for row in dataset["rows"]:
        quantity = _as_number(row["values"][13])
        if quantity is None:
            continue
        if (batch == 1 and quantity >= 10) or (batch == 2 and quantity < -10):
            selected.append(row)
    if not selected:
        rule = "订货量 >= 10" if batch == 1 else "订货量 < -10"
        raise DailyReplenishmentError(f"当前表格中没有符合“{rule}”的行")

    explanation = "上午批次：订货量 >= 10" if batch == 1 else "下午批次：订货量 < -10"
    columns = list(dataset["columns"][:16]) + ["下单备注", "说明"]

    def export_values(row: dict[str, Any]) -> list[Any]:
        values = row["values"]
        sku = str(values[3] or "").strip()
        order_note = (dataset.get("order_notes") or {}).get(sku) or values[17]
        return list(values[:16]) + [order_note, explanation]

    workbook = _new_export_workbook()
    _add_dataset_sheet(workbook, "拆分汇总", columns, [export_values(row) for row in selected])
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        groups[str(row["values"][0] or "未分配").strip() or "未分配"].append(row)
    used = {"拆分汇总".casefold()}
    for operator, rows in sorted(groups.items(), key=lambda item: item[0]):
        _add_dataset_sheet(
            workbook,
            _safe_sheet_name(operator, used),
            columns,
            [export_values(row) for row in rows],
        )

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    output.seek(0)
    return output, len(selected)


def _source_payload(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "size_mb": round(stat.st_size / 1024 / 1024, 2),
    }


def _snapshot_payload(path: Path | None = None) -> dict[str, Any]:
    snapshot = path or get_today_snapshot()
    if snapshot is None:
        return {
            "available": False,
            "can_refresh": True,
            "date": date.today().isoformat(),
        }
    payload = _source_payload(snapshot)
    payload.update(
        {
            "available": True,
            "can_refresh": True,
            "date": date.today().isoformat(),
        }
    )
    return payload


def _dataset_response(snapshot: Path, dataset: dict[str, Any], **extra: Any):
    payload = serialize_dataset(dataset)
    payload.update(
        {
            "success": True,
            "source": _source_payload(snapshot),
            "snapshot": _snapshot_payload(snapshot),
            "summary": summarize_dataset(dataset),
        }
    )
    payload.update(extra)
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _load_request_dataset() -> tuple[Path, dict[str, Any]]:
    snapshot = get_today_snapshot()
    if snapshot is None:
        raise DailyReplenishmentError("今日快照尚未生成，请先点击“刷新今日快照”")
    return snapshot, load_daily_replenishment(snapshot)


@daily_replenishment_bp.get("/ai/daily-replenishment")
@require_permission("daily_replenishment")
def page():
    source = resolve_source_path()
    snapshot = get_today_snapshot()
    generation_settings = get_generation_settings(source)
    response = current_app.make_response(
        render_template(
            "daily_replenishment.html",
            source_available=bool(source),
            source_name=source.name if source else "",
            snapshot=_snapshot_payload(snapshot),
            generation_settings={
                key: _json_value(value)
                for key, value in generation_settings.items()
            },
            output_dir=str(get_output_dir()),
        )
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@daily_replenishment_bp.post("/api/ai/daily-replenishment/snapshot/refresh")
@require_permission("daily_replenishment")
def refresh_snapshot():
    try:
        had_snapshot = get_today_snapshot() is not None
        uploaded = request.files.get("file")
        if uploaded and getattr(uploaded, "filename", ""):
            source = save_uploaded_workbook(uploaded)
            session[SESSION_SOURCE_KEY] = str(source)
        else:
            source = resolve_source_path()
        snapshot, dataset, database_count = refresh_today_snapshot(
            source,
            recent_days=request.form.get("recent_days"),
            sales_source=request.form.get("sales_source"),
        )
        generation = dataset.get("generation") or {}
        return _dataset_response(
            snapshot,
            dataset,
            message=(
                f"今日补货表{'已重新刷新' if had_snapshot else '已生成'}，"
                f"共 {len(dataset['rows'])} 行，"
                f"销量截止 {generation.get('sales_end', '')}"
            ),
            database_sku_count=database_count,
        )
    except DailySnapshotRefreshInProgress as exc:
        return jsonify({"success": False, "message": str(exc)}), 409
    except DailyReplenishmentError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Failed to refresh daily replenishment snapshot")
        return jsonify({"success": False, "message": f"快照刷新失败：{exc}"}), 500


@daily_replenishment_bp.post("/api/ai/daily-replenishment/generate")
@require_permission("daily_replenishment")
def generate():
    try:
        snapshot, dataset = _load_request_dataset()
        return _dataset_response(snapshot, dataset)
    except DailyReplenishmentError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Failed to generate daily replenishment preview")
        return jsonify({"success": False, "message": f"生成失败：{exc}"}), 500


@daily_replenishment_bp.post("/api/ai/daily-replenishment/remarks")
@require_permission("daily_replenishment")
def remarks():
    try:
        snapshot, dataset = _load_request_dataset()
        payload = request.get_json(silent=True) or {}
        changed = apply_edits(dataset, payload.get("edits") or [])
        destination = save_remark_capture(dataset)
        update_today_snapshot(dataset)
        return jsonify(
            {
                "success": True,
                "message": f"备注文件已保存，本次应用 {changed} 处手工修改",
                "filename": destination.name,
                "saved_path": str(destination),
                "snapshot": _snapshot_payload(snapshot),
                "download_url": url_for("daily_replenishment.download_capture", filename=destination.name),
            }
        )
    except DailyReplenishmentError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Failed to refresh and save daily replenishment remarks")
        return jsonify({"success": False, "message": f"备注刷新或保存失败：{exc}"}), 500


@daily_replenishment_bp.post("/api/ai/daily-replenishment/split")
@require_permission("daily_replenishment")
def split():
    try:
        _, dataset = _load_request_dataset()
        payload = request.get_json(silent=True) or {}
        apply_edits(dataset, payload.get("edits") or [])
        try:
            batch = int(payload.get("batch", 1))
        except (TypeError, ValueError) as exc:
            raise DailyReplenishmentError("批次格式不正确") from exc
        output, selected_count = build_split_workbook(dataset, batch)
        stamp = datetime.now().strftime("%y%m%d_%H%M%S")
        filename = f"{stamp}日常补货_批次{batch}_按运营拆分.xlsx"
        response = send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
        response.headers["X-Daily-Replenishment-Rows"] = str(selected_count)
        return response
    except DailyReplenishmentError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Failed to split daily replenishment workbook")
        return jsonify({"success": False, "message": f"拆分失败：{exc}"}), 500


@daily_replenishment_bp.get("/api/ai/daily-replenishment/download/<path:filename>")
@require_permission("daily_replenishment")
def download_capture(filename: str):
    safe_name = _safe_filename(filename)
    if safe_name != filename or Path(safe_name).suffix.lower() not in ALLOWED_SUFFIXES:
        return jsonify({"success": False, "message": "文件名无效"}), 400
    output_dir = get_output_dir()
    path = output_dir / safe_name
    if not _is_supported_workbook(path) or not _is_path_within(path, output_dir):
        return jsonify({"success": False, "message": "文件不存在"}), 404
    return send_file(path, as_attachment=True, download_name=path.name)

