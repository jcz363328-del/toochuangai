from __future__ import annotations

import os
import tempfile
import hashlib
import copy
import re
import shutil
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from flask import Blueprint, current_app, g, has_request_context, jsonify, render_template, request, send_file, session
from openpyxl import load_workbook
from openpyxl.comments import Comment

import daily_replenishment as base
from integrations.sellfox import sellfox_purchase
from department_permissions import require_permission, is_local_superadmin
from bjc import dui_db
from tools import escape_sql_literal


daily_replenishment_operation_bp = Blueprint("daily_replenishment_operation", __name__)

PERMISSION_NAME = "daily_replenishment_operation"
SHEET_ORDER = ("库存明细", "在途", "日常补货", "FBA发货", "每日库存", "海运即将到货", "低毛利率")
_refresh_lock = Lock()
_snapshot_cache_lock = Lock()
_snapshot_cache: dict[str, tuple[int, dict[str, Any]]] = {}
_refresh_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="daily-replenishment-refresh")
_refresh_jobs_lock = Lock()
_refresh_jobs: dict[str, dict[str, Any]] = {}
SEA_SHIPPING_RECOMMENDATION_DAYS = 30
SEA_SHIPPING_RECOMMENDATION_MIN_AVG = 20.0
SEA_RECOMMENDATION_SHEET = "推荐海运"
SALES_TREND_SHEET = "近15天销量"
SNAPSHOT_SHEET_ORDER = (*SHEET_ORDER, SEA_RECOMMENDATION_SHEET, SALES_TREND_SHEET)


def _normalized_store(value: Any) -> str:
    return str(value or "").strip()


def get_store_permissions(user_name: str, *, query_executor=base.sf_db) -> dict[str, Any]:
    """按飞书用户名读取 DianQuanXian：2=阅读，1=增删改。"""
    if has_request_context() and is_local_superadmin() and session.get('feishu_user_id') and not getattr(g, 'permission_debug_state', None) and not session.get('permission_debug_user_open_id'):
        rows = query_executor("SELECT DISTINCT Dian FROM dbo.DianQuanXian WHERE Dian IS NOT NULL") or []
        stores = {_normalized_store(row[0] if isinstance(row, (list, tuple)) else row) for row in rows}
        stores.discard('')
        return {"read_stores": stores, "write_stores": stores, "can_write": True}
    normalized_name = str(user_name or "").split("（", 1)[0].strip()
    if not normalized_name:
        return {"read_stores": set(), "write_stores": set(), "can_write": False}
    safe_name = escape_sql_literal(normalized_name)
    rows = query_executor(
        "/* daily_replenishment_operation:store_permissions */\n"
        "SELECT DISTINCT Dian,LeiXing FROM dbo.DianQuanXian "
        f"WHERE LTRIM(RTRIM(YunYing))=N'{safe_name}' AND Dian IS NOT NULL AND LeiXing IN (1,2)"
    ) or []
    read_stores: set[str] = set()
    write_stores: set[str] = set()
    for row in rows:
        values = list(row) if isinstance(row, (list, tuple)) else [row]
        store = _normalized_store(values[0] if values else "")
        try:
            permission_type = int(values[1]) if len(values) > 1 else 0
        except (TypeError, ValueError):
            permission_type = 0
        if not store:
            continue
        if permission_type == 2:
            read_stores.add(store)
        elif permission_type == 1:
            write_stores.add(store)
            read_stores.add(store)
    return {
        "read_stores": read_stores,
        "write_stores": write_stores,
        "can_write": bool(write_stores),
    }


def get_operator_stores(user_name: str, *, query_executor=base.sf_db) -> set[str]:
    return set(get_store_permissions(user_name, query_executor=query_executor)["read_stores"])


def _visible_skus(stores: set[str], *, query_executor=base.sf_db) -> set[str]:
    if not stores:
        return set()
    literals = ",".join(f"N'{escape_sql_literal(store)}'" for store in sorted(stores))
    rows = query_executor(
        "/* daily_replenishment_operation:visible_skus */\n"
        "SELECT DISTINCT sd.SKU FROM dbo.SKUDian sd "
        f"WHERE LTRIM(RTRIM(CONVERT(NVARCHAR(100),sd.Dian))) IN ({literals}) "
        "AND sd.SKU IS NOT NULL"
    ) or []
    return {
        str(row[0] if isinstance(row, (list, tuple)) else row or "").lstrip("@").strip()
        for row in rows
        if str(row[0] if isinstance(row, (list, tuple)) else row or "").strip()
    }


def scoped_query_executor(user_name: str, *, query_executor=base.sf_db):
    """为当前运营人员构建仅返回其店铺数据的查询执行器。"""
    access = get_store_permissions(user_name, query_executor=query_executor)
    stores = set(access["read_stores"])
    visible_skus = _visible_skus(stores, query_executor=query_executor)
    access["visible_skus"] = visible_skus

    def execute(sql: str):
        # 运营部门用户均可进入功能；没有店铺映射时返回空数据，不放行全量数据。
        if not stores:
            return []
        rows = list(query_executor(sql) or [])
        marker = str(sql or "")
        if "daily_replenishment:core" in marker:
            return [row for row in rows if len(row) > 1 and _normalized_store(row[1]) in stores]
        if "daily_replenishment:sites" in marker:
            return [row for row in rows if row and str(row[0] or "").strip() in visible_skus]
        if "daily_replenishment:sheet_fba_shipping" in marker:
            return [row for row in rows if len(row) > 3 and _normalized_store(row[3]) in stores]
        if "daily_replenishment:sheet_ocean_arrivals" in marker:
            return [row for row in rows if len(row) > 2 and _normalized_store(row[2]) in stores]
        if "daily_replenishment:sheet_inventory_detail" in marker:
            return [row for row in rows if len(row) > 1 and str(row[1] or "").strip() in visible_skus]
        if "daily_replenishment:sheet_transit" in marker:
            return [
                row for row in rows
                if row and any(str(value or "").lstrip("@").strip() in visible_skus for value in row[:2])
            ]
        if "daily_replenishment:sheet_daily_inventory" in marker or "daily_replenishment:sheet_low_margin" in marker:
            return [row for row in rows if row and str(row[0] or "").strip() in visible_skus]
        if "daily_replenishment:smart_sales_history" in marker or "daily_replenishment:smart_sites" in marker:
            return [row for row in rows if row and str(row[0] or "").strip() in visible_skus]
        if "daily_replenishment:smart_margins" in marker:
            return [row for row in rows if row and str(row[0] or "").strip() in visible_skus]
        if "daily_replenishment:sea_shipping" in marker:
            return [row for row in rows if row and str(row[0] or "").lstrip("@").strip() in visible_skus]
        if "daily_replenishment:smart_status" in marker:
            return [
                row for row in rows
                if len(row) > 1 and str(row[1] or "").strip() in visible_skus
            ]
        return rows

    return execute, access


def _current_user_name(*, query_executor=base.sf_db) -> str:
    request_state = getattr(g, "permission_debug_state", None) if has_request_context() else None
    request_debug_name = (
        str(request_state.get("user_name") or "").strip()
        if isinstance(request_state, dict)
        else ""
    )
    name = str(
        request_debug_name
        or session.get("permission_debug_user_name")
        or session.get("feishu_user_name")
        or ""
    ).split("（", 1)[0].strip()
    if name and name not in {"用户", "飞书用户"}:
        return name

    request_debug_open_id = (
        str(request_state.get("user_open_id") or "").strip()
        if isinstance(request_state, dict)
        else ""
    )
    open_id = str(
        request_debug_open_id
        or session.get("permission_debug_user_open_id")
        or session.get("feishu_open_id")
        or session.get("feishu_user_id")
        or ""
    ).strip()
    if not open_id:
        return ""
    safe_open_id = escape_sql_literal(open_id)
    rows = query_executor(
        "/* daily_replenishment_operation:resolve_user_name */\n"
        "IF OBJECT_ID(N'dbo.feishu_id_tc', N'U') IS NOT NULL "
        f"SELECT TOP 1 YONGHU FROM dbo.feishu_id_tc WHERE FeiShu_ID=N'{safe_open_id}' "
        "ELSE IF OBJECT_ID(N'dbo.feishu_id', N'U') IS NOT NULL "
        f"SELECT TOP 1 YONGHU FROM dbo.feishu_id WHERE FeiShu_ID=N'{safe_open_id}'"
    ) or []
    if rows:
        first = rows[0] if isinstance(rows, list) else rows
        resolved = first[0] if isinstance(first, (list, tuple)) else first
        name = str(resolved or "").split("（", 1)[0].strip()
        if name:
            session["feishu_user_name"] = name
            return name
    return ""


def _snapshot_owner_key(user_name: str) -> str:
    normalized_name = str(user_name or "").split("（", 1)[0].strip()
    return hashlib.sha256((normalized_name + "|dianquanxian-v1").encode("utf-8")).hexdigest()[:20]


def get_output_dir(*, create: bool = False) -> Path:
    configured = current_app.config.get("DAILY_REPLENISHMENT_OPERATION_OUTPUT_DIR")
    raw = configured or os.environ.get("DAILY_REPLENISHMENT_OPERATION_OUTPUT_DIR")
    output_dir = Path(str(raw)).expanduser() if raw else base.get_output_dir() / "_日常补货运营"
    if create:
        output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_snapshot_path(snapshot_date: date | None = None, *, user_name: str = "") -> Path:
    target = snapshot_date or date.today()
    owner = _snapshot_owner_key(user_name)
    return get_output_dir() / "_每日快照" / owner / f"{target:%Y%m%d}日常补货运营.xlsx"


def get_today_snapshot(*, user_name: str = "") -> Path | None:
    path = get_snapshot_path(user_name=user_name)
    return path if path.is_file() else None


def get_shared_today_snapshot() -> Path | None:
    """仅使用明确标记的全量共享快照，不从个人快照猜测全量数据。"""
    path = get_output_dir() / '_每日快照' / '_shared_full_v1' / f'{date.today():%Y%m%d}日常补货运营.xlsx'
    return path if path.is_file() else None


def get_shared_snapshot_path() -> Path:
    return get_output_dir() / '_每日快照' / '_shared_full_v1' / f'{date.today():%Y%m%d}日常补货运营.xlsx'


def _scope_snapshot_payload(payload: dict[str, Any], access: dict[str, Any]) -> dict[str, Any]:
    """Filter a shared snapshot to the current user's DianQuanXian store scope."""
    scoped = copy.deepcopy(payload)
    stores = {_normalized_store(value) for value in access.get("read_stores") or set()}
    visible_skus = {str(value or "").lstrip("@").strip() for value in access.get("visible_skus") or set()}
    sheets = scoped.get("sheets") or {}

    def keep_store(row: list[Any], index: int) -> bool:
        return len(row) > index and _normalized_store(row[index]) in stores

    def keep_sku(row: list[Any], indexes: tuple[int, ...]) -> bool:
        return any(
            len(row) > index and str(row[index] or "").lstrip("@").strip() in visible_skus
            for index in indexes
        )

    rules = {
        "库存明细": lambda row: keep_sku(row, (1,)),
        "在途": lambda row: keep_sku(row, (0, 1)),
        base.SHEET_NAME: lambda row: keep_store(row, 1),
        "FBA发货": lambda row: keep_store(row, 3),
        "每日库存": lambda row: keep_sku(row, (0,)),
        "海运即将到货": lambda row: keep_store(row, 2),
        "低毛利率": lambda row: keep_sku(row, (0,)),
        SEA_RECOMMENDATION_SHEET: lambda row: keep_sku(row, (0,)),
        SALES_TREND_SHEET: lambda row: keep_sku(row, (0,)),
    }
    for name, sheet in sheets.items():
        rule = rules.get(name)
        if rule is None:
            continue
        old_rows = list(sheet.get("rows") or [])
        kept_indexes = [index for index, row in enumerate(old_rows) if rule(row)]
        sheet["rows"] = [old_rows[index] for index in kept_indexes]
        comments = sheet.get("comments") or {}
        sheet["comments"] = {
            str(new_index): comments[str(old_index)]
            for new_index, old_index in enumerate(kept_indexes)
            if str(old_index) in comments
        }
        styles = sheet.get("styles") or {}
        sheet["styles"] = {
            str(new_index): styles[str(old_index)]
            for new_index, old_index in enumerate(kept_indexes)
            if str(old_index) in styles
        }
    return scoped


def _scoped_main_row_indexes(payload: dict[str, Any], access: dict[str, Any]) -> list[int]:
    """Return full-snapshot row indexes for the authorized 日常补货 rows."""
    sheet = (payload.get("sheets") or {}).get(base.SHEET_NAME) or {}
    columns = [str(value or "").strip() for value in sheet.get("columns") or []]
    try:
        store_index = columns.index("店铺")
    except ValueError as exc:
        raise base.DailyReplenishmentError("快照缺少“店铺”列，无法保存订货量") from exc
    stores = {_normalized_store(value) for value in access.get("read_stores") or set()}
    return [
        index
        for index, row in enumerate(sheet.get("rows") or [])
        if len(row) > store_index and _normalized_store(row[store_index]) in stores
    ]


def _coerce_order_quantity(value: Any, *, allow_zero: bool = True) -> int:
    number = base._as_number(value)
    if number is None or number < 0 or (not allow_zero and number <= 0):
        raise base.DailyReplenishmentError("订货量必须是大于 0 的整数" if not allow_zero else "订货量必须是大于等于 0 的整数")
    rounded = int(round(number))
    if abs(number - rounded) > 1e-9:
        raise base.DailyReplenishmentError("订货量必须是整数")
    return rounded


def _save_snapshot_quantity_changes(
    snapshot: Path,
    access: dict[str, Any],
    changes: list[dict[str, Any]],
) -> tuple[Path, int]:
    """Persist authorized quantity edits into the user's current snapshot."""
    if not changes:
        return snapshot, 0
    payload = load_snapshot(snapshot)
    main = (payload.get("sheets") or {}).get(base.SHEET_NAME) or {}
    columns = [str(value or "").strip() for value in main.get("columns") or []]
    try:
        sku_index = columns.index("SKU")
        store_index = columns.index("店铺")
        operator_index = columns.index("运营")
        quantity_index = columns.index("订货量")
    except ValueError as exc:
        raise base.DailyReplenishmentError("快照缺少保存订货量所需的列") from exc
    rows = main.get("rows") or []
    scoped_indexes = _scoped_main_row_indexes(payload, access)
    resolved: dict[int, int] = {}
    for raw in changes:
        if not isinstance(raw, dict):
            raise base.DailyReplenishmentError("订货量修改明细格式不正确")
        try:
            scoped_index = int(raw.get("index"))
        except (TypeError, ValueError) as exc:
            raise base.DailyReplenishmentError("订货量修改缺少有效行号") from exc
        if scoped_index < 0 or scoped_index >= len(scoped_indexes):
            raise base.DailyReplenishmentError("订货量修改的行已失效，请刷新后重试")
        full_index = scoped_indexes[scoped_index]
        row = rows[full_index]
        expected = {
            "sku": str(row[sku_index] or "").strip(),
            "store": _normalized_store(row[store_index]),
            "operator": str(row[operator_index] or "").strip(),
        }
        for key in ("sku", "store", "operator"):
            if key in raw and str(raw.get(key) or "").strip() != expected[key]:
                raise base.DailyReplenishmentError("快照内容已变化，请刷新后再保存订货量")
        resolved[full_index] = _coerce_order_quantity(raw.get("quantity"), allow_zero=True)
    if not resolved:
        return snapshot, 0

    snapshot.parent.mkdir(parents=True, exist_ok=True)
    quantity_column = quantity_index + 1
    workbook = load_workbook(snapshot)
    temp_path: Path | None = None
    try:
        if base.SHEET_NAME not in workbook.sheetnames:
            raise base.DailyReplenishmentError("快照缺少日常补货工作表")
        sheet = workbook[base.SHEET_NAME]
        for full_index, quantity in resolved.items():
            sheet.cell(row=full_index + 2, column=quantity_column).value = quantity
        with tempfile.NamedTemporaryFile(dir=snapshot.parent, suffix=".xlsx", delete=False) as tmp:
            temp_path = Path(tmp.name)
        workbook.save(temp_path)
        os.replace(temp_path, snapshot)
        temp_path = None
    finally:
        workbook.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    for full_index, quantity in resolved.items():
        rows[full_index][quantity_index] = quantity
    cache_snapshot_payload(snapshot, payload)
    return snapshot, len(resolved)


def _resolve_snapshot_for_user(user_name: str) -> tuple[Path | None, bool]:
    shared = get_shared_today_snapshot()
    if shared is None:
        return None, True
    own = get_today_snapshot(user_name=user_name)
    # 只保留基于本轮全量快照之后的个人订货量修改。
    if own is not None and own.stat().st_mtime_ns > shared.stat().st_mtime_ns:
        return own, False
    return shared, True


def _settings(source: Path | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = base.get_generation_settings(source)
    listing_days, recent_days, threshold = 60, 30, 0.1
    if source and source.is_file():
        try:
            workbook = load_workbook(source, read_only=True, data_only=True, keep_links=False)
            try:
                if "低毛利率" in workbook.sheetnames:
                    sheet = workbook["低毛利率"]
                    listing_days = int(sheet["B1"].value or listing_days)
                    recent_days = int(sheet["B2"].value or recent_days)
                    threshold = float(sheet["B3"].value or threshold)
            finally:
                workbook.close()
        except Exception:
            pass
    settings.update(
        low_margin_listing_days=listing_days,
        low_margin_recent_days=recent_days,
        low_margin_threshold=threshold,
    )
    if overrides:
        for key in ("low_margin_listing_days", "low_margin_recent_days", "low_margin_threshold"):
            if key in overrides and overrides[key] is not None:
                settings[key] = overrides[key]
    return settings


# 销量来源 -> (逐日明细表, 销量列)，与 generate_database_dataset 的口径保持一致
_SALES_SOURCE_TABLES: dict[str, tuple[str, str]] = {
    "下单": ("GuangGao", "ShuLiang"),
    "付款": ("v_XiaoShouLiang", "HeSuanXiaoLiang"),
}


def _trend_window(settings: dict[str, Any]) -> tuple[date, date]:
    """走势区间：优先用前端传来的快照区间，缺省回退到当前生成参数。"""
    start = settings["sales_start"]
    end = settings["sales_end"]
    raw_start = str(request.args.get("start") or "").strip()
    raw_end = str(request.args.get("end") or "").strip()
    if raw_start and raw_end:
        try:
            start = date.fromisoformat(raw_start)
            end = date.fromisoformat(raw_end)
        except ValueError as exc:
            raise base.DailyReplenishmentError("日期参数应形如 YYYY-MM-DD") from exc
        if start > end:
            start, end = end, start
    span = (end - start).days + 1
    if span < 1 or span > 45:
        raise base.DailyReplenishmentError("走势区间需在 1 到 45 天之间")
    if end > date.today():
        raise base.DailyReplenishmentError("走势区间的结束日期不能晚于今天")
    return start, end


def generate_operation_dataset(source: Path | None = None, *, query_executor=base.sf_db, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = _settings(source, overrides)
    main = base.generate_database_dataset(settings, query_executor=query_executor)
    notes = query_executor(
        "/* daily_replenishment:clearance_notes */\n"
        "SELECT SKU,BeiZhu FROM dbo.ChanPinBeiZhu "
        "WHERE YorN='Y' AND (BeiZhu LIKE N'清货登记：%' OR BeiZhu LIKE N'运营备注：%') ORDER BY RiQi"
    ) or []
    by_sku: dict[str, list[str]] = {}
    for sku, note in notes:
        by_sku.setdefault(str(sku).strip(), []).append(str(note))
    for row in main.get("rows") or []:
        values = row["values"]
        for note in by_sku.get(str(values[3]).strip(), []):
            if note not in str(values[17] or ""):
                values[17] = "\n".join(filter(None, [values[17], note]))
    related = base.generate_button_sheets(settings, query_executor=query_executor)
    skus = {str(row["values"][3] or "").strip() for row in main.get("rows") or [] if len(row.get("values") or []) > 3}
    related[SALES_TREND_SHEET] = _sales_trend_snapshot_sheet(settings, skus, query_executor=query_executor)
    recommendations = _normalize_sea_shipping_rows(query_executor(_sea_shipping_recommendation_sql()) or [])
    related[SEA_RECOMMENDATION_SHEET] = {
        "columns": ["SKU", "日均销量"],
        "rows": [[item["sku"], item["avg_daily_sales"]] for item in recommendations],
        "purpose": "每日快照生成时计算的推荐海运",
    }
    return {
        "main": main,
        "sheets": related,
        "generation": dict(main.get("generation") or {}),
    }


def save_operation_workbook(dataset: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    base._save_dataset_workbook(dataset["main"], destination)
    workbook = load_workbook(destination)
    try:
        for name in SNAPSHOT_SHEET_ORDER:
            if name == base.SHEET_NAME:
                continue
            if name in workbook.sheetnames:
                del workbook[name]
            sheet_data = dataset["sheets"].get(name)
            if not sheet_data:
                continue
            sheet = workbook.create_sheet(name)
            columns = list(sheet_data.get("columns") or [])
            rows = [list(row) for row in sheet_data.get("rows") or []]
            for column_index, value in enumerate(columns, 1):
                base._write_literal(sheet.cell(1, column_index), value)
            for row_index, values in enumerate(rows, 2):
                for column_index, value in enumerate(values, 1):
                    base._write_literal(sheet.cell(row_index, column_index), value)
            base._style_worksheet(sheet, len(rows) + 1, len(columns))
            if name in (SEA_RECOMMENDATION_SHEET, SALES_TREND_SHEET):
                sheet.sheet_state = "hidden"

        ordered = [workbook[name] for name in SNAPSHOT_SHEET_ORDER if name in workbook.sheetnames]
        remaining = [sheet for sheet in workbook.worksheets if sheet.title not in SNAPSHOT_SHEET_ORDER]
        workbook._sheets = ordered + remaining
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".xlsx", delete=False) as tmp:
            temp_path = Path(tmp.name)
        try:
            workbook.save(temp_path)
            os.replace(temp_path, destination)
        finally:
            temp_path.unlink(missing_ok=True)
    finally:
        workbook.close()
    return destination


def _sheet_payload(dataset: dict[str, Any]) -> dict[str, Any]:
    main = base.serialize_dataset(dataset["main"])
    sheets = {
        name: {
            "columns": list(sheet.get("columns") or []),
            "rows": [[base._json_value(value) for value in row] for row in sheet.get("rows") or []],
            "purpose": str(sheet.get("purpose") or ""),
        }
        for name, sheet in dataset["sheets"].items()
    }
    sheets[base.SHEET_NAME] = {
        "columns": main["columns"],
        "rows": [row["values"] for row in main["rows"]],
        "header_comments": dict(main.get("header_comments") or {}),
        "comments": {
            str(index): dict(row.get("comments") or {})
            for index, row in enumerate(main["rows"])
            if row.get("comments")
        },
        "styles": {
            str(index): dict(row.get("styles") or {})
            for index, row in enumerate(main["rows"])
            if row.get("styles")
        },
        "purpose": "原运营版按钮生成的日常补货主表",
    }
    return {"sheets": sheets, "generation": main.get("generation") or {}}


def load_snapshot(path: Path) -> dict[str, Any]:
    main_dataset = base.load_daily_replenishment(path)
    workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        sheets: dict[str, Any] = {}
        for name in SNAPSHOT_SHEET_ORDER:
            if name not in workbook.sheetnames:
                continue
            sheet = workbook[name]
            values = list(sheet.iter_rows(values_only=True))
            if name == base.SHEET_NAME:
                serialized = base.serialize_dataset(main_dataset)
                sheets[name] = {
                    "columns": list(serialized.get("columns") or []),
                    "rows": [list(row.get("values") or []) for row in serialized.get("rows") or []],
                    "header_comments": dict(serialized.get("header_comments") or {}),
                    "comments": {
                        str(index): dict(row.get("comments") or {})
                        for index, row in enumerate(serialized.get("rows") or [])
                        if row.get("comments")
                    },
                    "styles": {
                        str(index): dict(row.get("styles") or {})
                        for index, row in enumerate(serialized.get("rows") or [])
                        if row.get("styles")
                    },
                    "purpose": "智能补货中心-亚马逊快照",
                }
            else:
                sheets[name] = {
                    "columns": [str(value or "") for value in (values[0] if values else [])],
                    "rows": [[base._json_value(value) for value in row] for row in values[1:] if any(value not in (None, "") for value in row)],
                    "header_comments": {},
                    "comments": {},
                    "styles": {},
                    "purpose": "智能补货中心-亚马逊快照",
                }
        generation: dict[str, Any] = {}
        if "_生成信息" in workbook.sheetnames:
            for key, value in workbook["_生成信息"].iter_rows(max_col=2, values_only=True):
                if key not in (None, ""):
                    generation[str(key)] = base._json_value(value)
        return {"sheets": sheets, "generation": generation}
    finally:
        workbook.close()


def load_snapshot_cached(path: Path) -> dict[str, Any]:
    """按文件修改时间缓存解析后的快照，避免每次进入页面重读 Excel。"""
    cache_key = str(path.resolve())
    modified = path.stat().st_mtime_ns
    with _snapshot_cache_lock:
        cached = _snapshot_cache.get(cache_key)
        if cached and cached[0] == modified:
            return copy.deepcopy(cached[1])
    payload = load_snapshot(path)
    with _snapshot_cache_lock:
        _snapshot_cache[cache_key] = (modified, copy.deepcopy(payload))
    return payload


def cache_snapshot_payload(path: Path, payload: dict[str, Any]) -> None:
    cache_key = str(path.resolve())
    modified = path.stat().st_mtime_ns
    cache_value = {
        "sheets": copy.deepcopy(payload.get("sheets") or {}),
        "generation": copy.deepcopy(payload.get("generation") or {}),
    }
    with _snapshot_cache_lock:
        _snapshot_cache[cache_key] = (modified, cache_value)


def _snapshot_payload(path: Path | None = None, *, user_name: str = "") -> dict[str, Any]:
    snapshot = path or _resolve_snapshot_for_user(user_name)[0]
    if snapshot is None:
        return {"available": False, "date": date.today().isoformat()}
    stat = snapshot.stat()
    return {
        "available": True,
        "date": date.today().isoformat(),
        "name": snapshot.name,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "size_mb": round(stat.st_size / 1024 / 1024, 2),
    }


def _attach_client_cache_meta(
    meta: dict[str, Any],
    path: Path | None,
    user_name: str,
    access: dict[str, Any],
) -> dict[str, Any]:
    """Bind browser cache data to the user, permission scope, and snapshot version."""
    if path is None or not path.is_file():
        return meta
    stores = "\x1f".join(sorted(_normalized_store(value) for value in access.get("read_stores") or set()))
    skus = "\x1f".join(sorted(str(value or "").strip() for value in access.get("visible_skus") or set()))
    scope_hash = hashlib.sha256(f"{stores}|{skus}".encode("utf-8")).hexdigest()[:16]
    prefix = f"daily-replenishment-operation:v2:{_snapshot_owner_key(user_name)}:"
    meta["client_cache_prefix"] = prefix
    meta["client_cache_key"] = f"{prefix}{path.stat().st_mtime_ns}:{scope_hash}"
    return meta


@daily_replenishment_operation_bp.get("/ai/daily-replenishment-operation")
@require_permission(PERMISSION_NAME)
def page():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    stores = set(access["read_stores"])
    snapshot_path, is_shared = _resolve_snapshot_for_user(user_name)
    snapshot_meta = _snapshot_payload(snapshot_path, user_name=user_name)
    snapshot_meta["download_available"] = snapshot_path is not None
    _attach_client_cache_meta(snapshot_meta, snapshot_path, user_name, access)
    response = current_app.make_response(
        render_template(
            "运营部/daily_replenishment_operation.html",
            snapshot=snapshot_meta,
            # Keep the first response small; the browser loads the scoped snapshot
            # asynchronously from /data instead of parsing thousands of embedded rows.
            initial_data=None,
            operator_stores=sorted(stores),
            can_write=bool(access["can_write"]),
        )
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@daily_replenishment_operation_bp.post("/api/ai/daily-replenishment-operation/refresh")
@require_permission(PERMISSION_NAME)
def refresh():
    try:
        user_name = _current_user_name()
        _, access = scoped_query_executor(user_name)
        if not access["can_write"]:
            return jsonify({"success": False, "message": "当前用户在 DianQuanXian 中只有阅读权限，不能生成或刷新"}), 403
        stores = set(access["read_stores"])
        uploaded = request.files.get("file")
        overrides = {}
        for form_key, setting_key, caster in (
            ("listingDays", "low_margin_listing_days", int),
            ("recentDays", "low_margin_recent_days", int),
            ("marginThreshold", "low_margin_threshold", float),
        ):
            raw = (request.form.get(form_key) or "").strip()
            if raw:
                try:
                    overrides[setting_key] = caster(raw)
                except ValueError:
                    return jsonify({"success": False, "message": "参数格式不正确"}), 400
        source = None
        if uploaded and getattr(uploaded, "filename", ""):
            source = base.save_uploaded_workbook(uploaded)
        else:
            source = base.resolve_source_path()
        job_id = uuid.uuid4().hex
        app = current_app._get_current_object()
        with _refresh_jobs_lock:
            _refresh_jobs[job_id] = {"status": "queued", "user": user_name}

        def run_job():
            try:
                # 后台线程没有请求上下文，必须自己压入应用上下文，
                # 否则 get_generation_settings 等读取 current_app.config 的调用会抛
                # “Working outside of application context”。
                with app.app_context():
                    with _refresh_jobs_lock:
                        _refresh_jobs[job_id]["status"] = "running"
                    with _refresh_lock:
                        dataset = generate_operation_dataset(source, query_executor=base.sf_db, overrides=overrides)
                        snapshot = get_shared_snapshot_path()
                        staging = snapshot.with_name(f'.{uuid.uuid4().hex}.xlsx')
                        try:
                            save_operation_workbook(dataset, staging)
                            os.replace(staging, snapshot)
                        finally:
                            staging.unlink(missing_ok=True)
                        payload = _sheet_payload(dataset)
                        cache_snapshot_payload(snapshot, payload)
                    snapshot_meta = _snapshot_payload(snapshot, user_name=user_name)
                    payload = _scope_snapshot_payload(payload, access)
                    snapshot_meta['download_available'] = True
                    _attach_client_cache_meta(snapshot_meta, snapshot, user_name, access)
                    payload.update(success=True, stores=sorted(stores), snapshot=snapshot_meta)
                with _refresh_jobs_lock:
                    _refresh_jobs[job_id].update(status="completed", payload=payload)
            except Exception as exc:
                app.logger.exception("Failed to refresh daily replenishment operation")
                with _refresh_jobs_lock:
                    _refresh_jobs[job_id].update(status="failed", message=str(exc))

        _refresh_executor.submit(run_job)
        return jsonify({"success": True, "jobId": job_id, "status": "queued", "message": "刷新任务已在后台开始，切换页面不会中断"}), 202
    except base.DailyReplenishmentError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Failed to refresh daily replenishment operation")
        return jsonify({"success": False, "message": f"智能补货中心-亚马逊刷新失败：{exc}"}), 500


@daily_replenishment_operation_bp.get("/api/ai/daily-replenishment-operation/refresh/<job_id>")
@require_permission(PERMISSION_NAME)
def refresh_status(job_id):
    with _refresh_jobs_lock:
        job = _refresh_jobs.get(job_id)
        if not job or job.get("user") != _current_user_name():
            return jsonify({"success": False, "message": "刷新任务不存在"}), 404
        result = dict(job)
    if result.get("status") == "completed":
        _, access = scoped_query_executor(_current_user_name())
        payload = _scope_snapshot_payload(result["payload"], access)
        payload['stores'] = sorted(access['read_stores'])
        return jsonify(payload)
    return jsonify({"success": result.get("status") != "failed", "status": result.get("status"), "message": result.get("message", "")})


@daily_replenishment_operation_bp.get("/api/ai/daily-replenishment-operation/data")
@require_permission(PERMISSION_NAME)
def data():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    stores = set(access["read_stores"])
    snapshot, is_shared = _resolve_snapshot_for_user(user_name)
    if snapshot is None:
        return jsonify({"success": False, "message": "今日的智能补货中心-亚马逊快照尚未生成"}), 404
    payload = load_snapshot_cached(snapshot)
    # Apply authorization on every response, including a user's own snapshot.
    # File ownership only selects a cache candidate; it must not grant data scope.
    payload = _scope_snapshot_payload(payload, access)
    snapshot_meta = _snapshot_payload(snapshot, user_name=user_name)
    snapshot_meta["download_available"] = True
    _attach_client_cache_meta(snapshot_meta, snapshot, user_name, access)
    payload.update(success=True, stores=sorted(stores), snapshot=snapshot_meta)
    return jsonify(payload)


def _sea_shipping_recommendation_sql() -> str:
    """返回近 30 个完整销售日的海运推荐查询。"""
    return f"""/* daily_replenishment:sea_shipping_recommendations */
SELECT sales.SKU,
       ROUND(SUM(ISNULL(sales.HeSuanXiaoLiang,0))/{SEA_SHIPPING_RECOMMENDATION_DAYS}.0,1) AS AvgDailySales
  FROM v_XiaoShouLiang sales
  LEFT JOIN HaiYunSKU ocean
    ON LTRIM(RTRIM(ocean.SKU))=LTRIM(RTRIM(sales.SKU))
   AND ocean.ZhengChang=N'Y'
 WHERE sales.RiQi>=CONVERT(date,DATEADD(day,-31,GETDATE()))
   AND sales.RiQi<CONVERT(date,DATEADD(day,-1,GETDATE()))
   AND ocean.SKU IS NULL
 GROUP BY sales.SKU
HAVING SUM(ISNULL(sales.HeSuanXiaoLiang,0))>{SEA_SHIPPING_RECOMMENDATION_DAYS * SEA_SHIPPING_RECOMMENDATION_MIN_AVG:g}
 ORDER BY AvgDailySales DESC,sales.SKU"""


def _normalize_sea_shipping_rows(rows: list[Any]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for raw in rows or []:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        sku = str(raw[0] or "").lstrip("@").strip()
        try:
            average = float(raw[1])
        except (TypeError, ValueError):
            continue
        if not sku or average <= SEA_SHIPPING_RECOMMENDATION_MIN_AVG:
            continue
        recommendations.append({"sku": sku, "avg_daily_sales": round(average, 1)})
    return recommendations


def _sales_trend_snapshot_sheet(settings: dict[str, Any], skus: set[str], *, query_executor=base.sf_db) -> dict[str, Any]:
    """One grouped query per refresh, with a complete zero-filled 15-day series."""
    end = base._coerce_date(settings.get("sales_end")) or date.today() - timedelta(days=2)
    start = end - timedelta(days=14)
    dates = [(start + timedelta(days=index)).isoformat() for index in range(15)]
    wanted = sorted(sku for sku in skus if sku)
    table, column = _SALES_SOURCE_TABLES.get(settings.get("sales_source"), _SALES_SOURCE_TABLES["付款"])
    totals: dict[str, dict[str, float]] = {}
    if wanted:
        literals = ",".join(f"N'{escape_sql_literal(sku, escape_percent=False)}'" for sku in wanted)
        sql = f"""/* daily_replenishment:snapshot_sales_trend */
SELECT SKU,CONVERT(date,RiQi),SUM(CAST(ISNULL({column},0) AS FLOAT))
  FROM {table}
 WHERE SKU IN ({literals}) AND RiQi>='{start.isoformat()}' AND RiQi<DATEADD(day,1,'{end.isoformat()}')
 GROUP BY SKU,CONVERT(date,RiQi)"""
        for raw in query_executor(sql) or []:
            if not isinstance(raw, (list, tuple)) or len(raw) < 3:
                continue
            sku = str(raw[0] or "").strip()
            day = base._coerce_date(raw[1])
            if sku not in skus or day is None or not start <= day <= end:
                continue
            key = day.isoformat()
            values = totals.setdefault(sku, {})
            values[key] = values.get(key, 0) + (base._as_number(raw[2]) or 0)
    return {
        "columns": ["SKU", *dates],
        "rows": [[sku, *[int(round(totals.get(sku, {}).get(day, 0))) for day in dates]] for sku in wanted],
        "purpose": "截至快照销量截止日的近15天逐日销量",
    }


def _write_snapshot_sheet(path: Path, *, rows: list[list[Any]] | None = None, removed_skus: set[str] | None = None, sheet_name: str = SEA_RECOMMENDATION_SHEET, columns: list[str] | None = None) -> bool:
    """Update one hidden data sheet, preserving every other snapshot sheet.

    The caller holds _refresh_lock so a refresh cannot replace this update.
    """
    workbook = load_workbook(path)
    temp_path = None
    try:
        if rows is None:
            if sheet_name not in workbook.sheetnames:
                return False
            existing = list(workbook[sheet_name].iter_rows(min_row=2, values_only=True))
            rows = [list(row) for row in existing if row and str(row[0] or "").lstrip("@").strip() not in (removed_skus or set())]
            if len(rows) == len(existing):
                return False
        if sheet_name in workbook.sheetnames:
            del workbook[sheet_name]
        sheet = workbook.create_sheet(sheet_name)
        for index, values in enumerate([columns or ["SKU", "日均销量"], *rows], 1):
            for column, value in enumerate(values, 1):
                base._write_literal(sheet.cell(index, column), value)
        sheet.sheet_state = "hidden"
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".xlsx", delete=False) as tmp:
            temp_path = Path(tmp.name)
        workbook.save(temp_path)
        os.replace(temp_path, path)
        with _snapshot_cache_lock:
            _snapshot_cache.pop(str(path.resolve()), None)
        return True
    finally:
        workbook.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def populate_sea_recommendation_snapshot(path: Path, *, query_executor=base.sf_db) -> bool:
    """One-time migration for an existing daily snapshot; never called on page reads."""
    with _refresh_lock:
        workbook = load_workbook(path, read_only=True)
        try:
            if SEA_RECOMMENDATION_SHEET in workbook.sheetnames:
                return False
        finally:
            workbook.close()
        items = _normalize_sea_shipping_rows(query_executor(_sea_shipping_recommendation_sql()) or [])
        return _write_snapshot_sheet(path, rows=[[item["sku"], item["avg_daily_sales"]] for item in items])


def _sea_shipping_insert_sql(skus: list[str]) -> str:
    values = ",".join(
        f"(N'{escape_sql_literal(sku, escape_percent=False)}')"
        for sku in skus
    )
    return f"""INSERT INTO dbo.HaiYunSKU ([SKU],[ZhengChang],[TianJiaShiJian],[ShanChuShiJian])
SELECT candidates.SKU,N'Y',GETDATE(),NULL
  FROM (VALUES {values}) candidates(SKU)
 WHERE NOT EXISTS (
       SELECT 1
         FROM dbo.HaiYunSKU existing
        WHERE LTRIM(RTRIM(existing.SKU))=candidates.SKU
          AND existing.ZhengChang=N'Y'
 )"""


@daily_replenishment_operation_bp.route(
    "/api/ai/daily-replenishment-operation/sea-shipping-recommendations",
    methods=("GET", "POST"),
)
@require_permission(PERMISSION_NAME)
def sea_shipping_recommendations():
    user_name = _current_user_name()
    execute, access = scoped_query_executor(user_name)
    visible_skus = {
        str(value or "").lstrip("@").strip()
        for value in access.get("visible_skus") or set()
        if str(value or "").strip()
    }
    if request.method == "GET":
        try:
            snapshot, _ = _resolve_snapshot_for_user(user_name)
            payload = load_snapshot_cached(snapshot) if snapshot is not None else {}
            sheet = (payload.get("sheets") or {}).get(SEA_RECOMMENDATION_SHEET)
            recommendations = [
                item for item in _normalize_sea_shipping_rows((sheet or {}).get("rows") or [])
                if item["sku"] in visible_skus
            ]
            return jsonify(
                success=True,
                items=recommendations,
                snapshot_ready=sheet is not None,
                days=SEA_SHIPPING_RECOMMENDATION_DAYS,
                threshold=SEA_SHIPPING_RECOMMENDATION_MIN_AVG,
            )
        except Exception as exc:
            current_app.logger.exception("Failed to load sea shipping recommendations")
            return jsonify({"success": False, "message": f"读取海运推荐失败：{exc}"}), 500

    if not access.get("can_write"):
        return jsonify({"success": False, "message": "当前用户没有写入海运计划的权限"}), 403
    body = request.get_json(silent=True) or {}
    raw_skus = body.get("skus") if isinstance(body, dict) else None
    if not isinstance(raw_skus, list):
        return jsonify({"success": False, "message": "请选择要加入海运计划的 SKU"}), 400
    selected: list[str] = []
    seen: set[str] = set()
    for raw in raw_skus:
        sku = str(raw or "").lstrip("@").strip()
        if sku and sku not in seen:
            selected.append(sku)
            seen.add(sku)
    if not selected:
        return jsonify({"success": False, "message": "请选择要加入海运计划的 SKU"}), 400
    if len(selected) > 500:
        return jsonify({"success": False, "message": "一次最多加入 500 个 SKU"}), 400
    if any(sku not in visible_skus for sku in selected):
        return jsonify({"success": False, "message": "所选 SKU 不在当前店铺权限范围内"}), 403
    try:
        with _refresh_lock:
            active_rows = execute(
                "/* daily_replenishment:sea_shipping_active */\n"
                "SELECT SKU FROM dbo.HaiYunSKU WHERE ZhengChang=N'Y'"
            )
            active = {
                str(row[0] if isinstance(row, (list, tuple)) else row or "").lstrip("@").strip()
                for row in active_rows or []
            }
            to_insert = [sku for sku in selected if sku not in active]
            if to_insert:
                dui_db(_sea_shipping_insert_sql(to_insert))
            paths = {get_shared_today_snapshot(), get_today_snapshot(user_name=user_name)}
            for snapshot in paths:
                if snapshot is not None:
                    _write_snapshot_sheet(snapshot, removed_skus=set(selected))
        return jsonify(
            success=True,
            added=len(to_insert),
            skipped=len(selected) - len(to_insert),
            skus=to_insert,
        )
    except Exception as exc:
        current_app.logger.exception("Failed to add sea shipping recommendations")
        return jsonify({"success": False, "message": f"加入海运计划失败：{exc}"}), 500


@daily_replenishment_operation_bp.get("/api/ai/daily-replenishment-operation/sales-trend")
@require_permission(PERMISSION_NAME)
def sales_trend():
    """返回 SKU 在快照销量区间内的逐日销量：单 SKU 供抽屉，多 SKU 供行内迷你走势。"""
    raw_skus = str(request.args.get("skus") or "").strip()
    raw_sku = str(request.args.get("sku") or "").strip()
    if raw_skus:
        wanted = [item.strip() for item in raw_skus.split(",") if item.strip()]
    elif raw_sku:
        wanted = [raw_sku]
    else:
        return jsonify({"success": False, "message": "缺少 SKU 参数"}), 400
    if len(wanted) > 200:
        return jsonify({"success": False, "message": "一次最多查询 200 个 SKU"}), 400
    user_name = _current_user_name()
    execute, access = scoped_query_executor(user_name)
    visible = access.get("visible_skus") or set()
    allowed = [sku for sku in wanted if sku in visible]
    if not allowed:
        return jsonify({"success": False, "message": "该 SKU 不在当前账号的店铺权限范围内"}), 403
    try:
        settings = _settings()
        start, end = _trend_window(settings)
    except base.DailyReplenishmentError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    table, column = _SALES_SOURCE_TABLES[settings["sales_source"]]
    in_list = ",".join(f"'{escape_sql_literal(sku, escape_percent=False)}'" for sku in allowed)
    sql = f"""/* daily_replenishment:sales_trend */
SELECT SKU,RiQi,SUM(CAST(ISNULL({column},0) AS FLOAT))
  FROM {table}
 WHERE SKU IN ({in_list})
   AND RiQi BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
 GROUP BY SKU,RiQi
 ORDER BY SKU,RiQi"""
    try:
        rows = execute(sql) or []
    except Exception as exc:
        return jsonify({"success": False, "message": f"读取逐日销量失败：{exc}"}), 500

    by_sku: dict[str, dict[str, int]] = {}
    for raw in rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 3:
            continue
        sku = str(raw[0] or "").strip()
        day = base._coerce_date(raw[1])
        if not sku or day is None:
            continue
        by_sku.setdefault(sku, {})[day.isoformat()] = int(round(base._as_number(raw[2]) or 0))

    dates = []
    cursor = start
    while cursor <= end:
        dates.append(cursor.isoformat())
        cursor += timedelta(days=1)

    def series_for(sku: str) -> list[dict[str, Any]]:
        day_map = by_sku.get(sku, {})
        return [{"date": key, "qty": day_map.get(key, 0)} for key in dates]

    if raw_skus:
        series = {sku: series_for(sku) for sku in wanted}
        return jsonify(
            {
                "success": True,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "series": series,
                "source": settings["sales_source"],
            }
        )

    sku = wanted[0]
    days = series_for(sku)
    total = sum(item["qty"] for item in days)
    return jsonify(
        {
            "success": True,
            "sku": sku,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": days,
            "sum": total,
            "avg": round(total / len(days), 1) if days else 0,
            "source": settings["sales_source"],
        }
    )


@daily_replenishment_operation_bp.post("/api/ai/daily-replenishment-operation/clearance")
@require_permission(PERMISSION_NAME)
def register_clearance():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    body = request.get_json(silent=True)
    sku = str(body.get("sku") or "").strip() if isinstance(body, dict) else ""
    if not sku:
        return jsonify(success=False, message="请选择要标记清货的 SKU"), 400
    if not user_name or not access.get("can_write"):
        return jsonify(success=False, message="当前用户没有登记清货的权限"), 403
    try:
        with _refresh_lock:
            snapshot, is_shared = _resolve_snapshot_for_user(user_name)
            if snapshot is None:
                return jsonify(success=False, message="请先生成今日快照"), 404
            payload = load_snapshot(snapshot)
            main = payload["sheets"][base.SHEET_NAME]
            columns = main["columns"]
            sku_col, store_col = columns.index("SKU"), columns.index("店铺")
            matching = [row for row in main["rows"] if str(row[sku_col] or "").strip() == sku]
            if not any(_normalized_store(row[store_col]) in access.get("write_stores", set()) for row in matching):
                return jsonify(success=False, message="该 SKU 不在当前可写店铺范围内"), 403
            stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
            note = f"清货登记：{stamp}，登记人：{user_name}"
            # 清货状态和审计备注在同一事务内保存；重复点击保留首次登记记录。
            dui_db("""SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF NOT EXISTS (SELECT 1 FROM dbo.QingHuo WITH (UPDLOCK,HOLDLOCK) WHERE SKU=%s)
BEGIN
    INSERT INTO dbo.QingHuo (SKU,BeiZhu,TianJiaRiQi) VALUES (%s,%s,%s);
END;
IF NOT EXISTS (SELECT 1 FROM dbo.ChanPinBeiZhu WITH (UPDLOCK,HOLDLOCK)
               WHERE SKU=%s AND YorN='Y' AND BeiZhu LIKE N'清货登记：%%')
BEGIN
    INSERT INTO dbo.ChanPinBeiZhu (SKU,RiQi,BeiZhu,TianJiaRen,YorN)
    VALUES (%s,%s,%s,%s,'Y');
END;
COMMIT TRANSACTION;""", params=(sku, sku, note, stamp, sku, sku, stamp, note, user_name))
            # 读取数据库中的首次登记，避免重复请求改写登记时间。
            records = base.sf_db(
                "SELECT TOP 1 BeiZhu FROM dbo.ChanPinBeiZhu WHERE SKU=N'"
                + escape_sql_literal(sku) + "' AND YorN='Y' AND BeiZhu LIKE N'清货登记：%' ORDER BY RiQi"
            ) or []
            if records:
                note = str(records[0][0])
            if is_shared:
                own = get_snapshot_path(user_name=user_name)
                own.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snapshot, own)
                snapshot = own
            workbook = load_workbook(snapshot)
            temp_path = None
            try:
                ws = workbook[base.SHEET_NAME]
                if base.STYLE_SHEET_NAME not in workbook.sheetnames:
                    metadata = workbook.create_sheet(base.STYLE_SHEET_NAME)
                    metadata.append(["行号", "列序号", "样式"])
                    metadata.sheet_state = "hidden"
                metadata = workbook[base.STYLE_SHEET_NAME]
                if base.COMMENT_SHEET_NAME not in workbook.sheetnames:
                    comments = workbook.create_sheet(base.COMMENT_SHEET_NAME)
                    comments.append(["行号", "列序号", "批注"])
                    comments.sheet_state = "hidden"
                comments = workbook[base.COMMENT_SHEET_NAME]
                for index, row in enumerate(main["rows"]):
                    if str(row[sku_col] or "").strip() != sku:
                        continue
                    remark_col = columns.index("备注")
                    previous = str(row[remark_col] or "")
                    if note not in previous:
                        base._write_literal(ws.cell(index + 2, remark_col + 1), "\n".join(filter(None, [previous, note])))
                    order_cell = ws.cell(index + 2, columns.index("订货量") + 1)
                    order_cell.value = 0
                    order_cell.comment = Comment("智能补货建议：0 件（清货产品，不下单）\n" + note, "智能补货")
                    comments.append([index + 2, columns.index("订货量"), order_cell.comment.text])
                    for column in range(1, 18):
                        tokens = list((main.get("styles", {}).get(str(index), {})).get(str(column - 1), []))
                        if "mark-clearance" not in tokens:
                            tokens.append("mark-clearance")
                        metadata.append([index + 2, column - 1, " ".join(tokens)])
                        base._apply_cell_business_styles(ws.cell(index + 2, column), ["mark-clearance"])
                with tempfile.NamedTemporaryFile(dir=snapshot.parent, suffix=".xlsx", delete=False) as tmp:
                    temp_path = Path(tmp.name)
                workbook.save(temp_path)
                os.replace(temp_path, snapshot)
            finally:
                workbook.close()
                if temp_path:
                    temp_path.unlink(missing_ok=True)
            updated = load_snapshot(snapshot)
            result = _scope_snapshot_payload(updated, access)
            cache_snapshot_payload(snapshot, updated)
            meta = _snapshot_payload(snapshot, user_name=user_name)
            _attach_client_cache_meta(meta, snapshot, user_name, access)
            result.update(snapshot=meta, stores=sorted(access["read_stores"]))
        result.update(success=True, message="已标记清货", note=note)
        return jsonify(result)
    except Exception as exc:
        current_app.logger.exception("Failed to register clearance")
        return jsonify(success=False, message=f"登记清货失败：{exc}"), 500


@daily_replenishment_operation_bp.post("/api/ai/daily-replenishment-operation/notes")
@require_permission(PERMISSION_NAME)
def add_note():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    if not user_name or not access.get("can_write"):
        return jsonify(success=False, message="当前用户没有添加备注的权限"), 403
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(success=False, message="请输入 SKU 和备注"), 400
    sku, note = str(body.get("sku") or "").strip(), str(body.get("note") or "").strip()
    if not sku or not note or len(note) > 1000:
        return jsonify(success=False, message="请选择 SKU 并输入 1–1000 字的备注"), 400
    try:
        with _refresh_lock:
            snapshot, is_shared = _resolve_snapshot_for_user(user_name)
            if snapshot is None:
                return jsonify(success=False, message="请先生成今日快照"), 404
            payload = load_snapshot(snapshot)
            main = payload["sheets"][base.SHEET_NAME]
            columns = main["columns"]
            sku_col, store_col, remark_col = (columns.index(name) for name in ("SKU", "店铺", "备注"))
            matching = [i for i, row in enumerate(main["rows"])
                        if str(row[sku_col] or "").strip() == sku]
            if not any(_normalized_store(main["rows"][i][store_col]) in access.get("write_stores", set()) for i in matching):
                return jsonify(success=False, message="该 SKU 不在当前可写店铺范围内"), 403
            stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
            dui_db("INSERT INTO dbo.ChanPinBeiZhu (SKU,RiQi,BeiZhu,TianJiaRen,YorN) VALUES (%s,%s,%s,%s,'Y')",
                   params=(sku, stamp, f"运营备注：{note}（{user_name} · {stamp}）", user_name))
            if is_shared:
                own = get_snapshot_path(user_name=user_name)
                own.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snapshot, own)
                snapshot = own
            workbook = load_workbook(snapshot)
            temp_path = None
            try:
                ws = workbook[base.SHEET_NAME]
                for index in matching:
                    previous = str(main["rows"][index][remark_col] or "")
                    entry = f"运营备注：{note}（{user_name} · {stamp}）"
                    base._write_literal(ws.cell(index + 2, remark_col + 1), "\n".join(filter(None, [previous, entry])))
                with tempfile.NamedTemporaryFile(dir=snapshot.parent, suffix=".xlsx", delete=False) as tmp:
                    temp_path = Path(tmp.name)
                workbook.save(temp_path)
                os.replace(temp_path, snapshot)
            finally:
                workbook.close()
                if temp_path:
                    temp_path.unlink(missing_ok=True)
            updated = load_snapshot(snapshot)
            cache_snapshot_payload(snapshot, updated)
            result = _scope_snapshot_payload(updated, access)
            meta = _snapshot_payload(snapshot, user_name=user_name)
            _attach_client_cache_meta(meta, snapshot, user_name, access)
            result.update(snapshot=meta, stores=sorted(access["read_stores"]), success=True, message="备注已保存")
        return jsonify(result)
    except Exception:
        current_app.logger.exception("Failed to add replenishment note")
        return jsonify(success=False, message="保存备注失败，请稍后重试"), 500


@daily_replenishment_operation_bp.post("/api/ai/daily-replenishment-operation/ab-product")
@require_permission(PERMISSION_NAME)
def set_ab_product():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    if not user_name or not access.get("can_write"):
        return jsonify(success=False, message="当前用户没有设置 AB 品的权限"), 403
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(success=False, message="请输入 SKU、分组号和款号"), 400
    sku = str(body.get("sku") or "").strip()
    group, kind = body.get("group"), body.get("type")
    if (not sku or type(group) is not int or not 1 <= group <= 2147483647
            or type(kind) is not int or kind not in (1, 2)):
        return jsonify(success=False, message="分组号必须为正整数，款号须为 A 品（1）或 B 品（2）"), 400
    try:
        with _refresh_lock:
            snapshot, is_shared = _resolve_snapshot_for_user(user_name)
            if snapshot is None:
                return jsonify(success=False, message="请先生成今日快照"), 404
            payload = load_snapshot(snapshot)
            main = payload["sheets"][base.SHEET_NAME]
            columns = main["columns"]
            sku_col, store_col, ab_col = (columns.index(name) for name in ("SKU", "店铺", "AB品"))
            matching = [i for i, row in enumerate(main["rows"])
                        if str(row[sku_col] or "").strip() == sku]
            if not any(_normalized_store(main["rows"][i][store_col]) in access.get("write_stores", set()) for i in matching):
                return jsonify(success=False, message="该 SKU 不在当前可写店铺范围内"), 403
            dui_db("""SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF EXISTS (SELECT 1 FROM dbo.ABPin WITH (UPDLOCK,HOLDLOCK) WHERE SKU=%s AND FenZu=%s)
    UPDATE dbo.ABPin SET XuHao=%s WHERE SKU=%s AND FenZu=%s;
ELSE
    INSERT INTO dbo.ABPin (SKU,FenZu,XuHao) VALUES (%s,%s,%s);
COMMIT TRANSACTION;""", params=(sku, group, kind, sku, group, sku, group, kind))
            records = base.sf_db(
                "SELECT MIN(CONVERT(NVARCHAR(10),FenZu)+'-'+CONVERT(NVARCHAR(10),XuHao)) FROM dbo.ABPin WHERE SKU=N'"
                + escape_sql_literal(sku) + "'"
            ) or []
            ab_value = str(records[0][0]) if records and records[0][0] else f"{group}-{kind}"
            if is_shared:
                own = get_snapshot_path(user_name=user_name)
                own.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snapshot, own)
                snapshot = own
            workbook = load_workbook(snapshot)
            temp_path = None
            try:
                ws = workbook[base.SHEET_NAME]
                for index in matching:
                    base._write_literal(ws.cell(index + 2, ab_col + 1), ab_value)
                with tempfile.NamedTemporaryFile(dir=snapshot.parent, suffix=".xlsx", delete=False) as tmp:
                    temp_path = Path(tmp.name)
                workbook.save(temp_path)
                os.replace(temp_path, snapshot)
            finally:
                workbook.close()
                if temp_path:
                    temp_path.unlink(missing_ok=True)
            updated = load_snapshot(snapshot)
            cache_snapshot_payload(snapshot, updated)
            result = _scope_snapshot_payload(updated, access)
            meta = _snapshot_payload(snapshot, user_name=user_name)
            _attach_client_cache_meta(meta, snapshot, user_name, access)
            result.update(snapshot=meta, stores=sorted(access["read_stores"]), success=True, message="AB 品已保存；请生成 / 刷新快照以应用补货规则")
        return jsonify(result)
    except Exception:
        current_app.logger.exception("Failed to set replenishment AB product")
        return jsonify(success=False, message="保存 AB 品失败，请稍后重试"), 500


@daily_replenishment_operation_bp.post("/api/ai/daily-replenishment-operation/order-quantities")
@require_permission(PERMISSION_NAME)
def update_order_quantities():
    """Save edited 订货量 values back to the current operator snapshot."""
    try:
        user_name = _current_user_name()
        _, access = scoped_query_executor(user_name)
        if not access["can_write"]:
            return jsonify({"success": False, "message": "当前用户只有阅读权限，不能修改订货量"}), 403
        body = request.get_json(silent=True) or {}
        changes = body.get("changes") if isinstance(body, dict) else None
        if not isinstance(changes, list):
            return jsonify({"success": False, "message": "订货量修改明细格式不正确"}), 400
        snapshot, is_shared = _resolve_snapshot_for_user(user_name)
        if snapshot is None:
            return jsonify({"success": False, "message": "今日快照尚未生成，请先生成 / 刷新"}), 404
        with _refresh_lock:
            if is_shared:
                own_snapshot = get_snapshot_path(user_name=user_name)
                own_snapshot.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snapshot, own_snapshot)
                snapshot = own_snapshot
            _save_snapshot_quantity_changes(snapshot, access, changes)
            payload = _scope_snapshot_payload(load_snapshot_cached(snapshot), access)
        snapshot_meta = _snapshot_payload(snapshot, user_name=user_name)
        _attach_client_cache_meta(snapshot_meta, snapshot, user_name, access)
        payload.update(success=True, stores=sorted(access["read_stores"]), snapshot=snapshot_meta)
        return jsonify(payload)
    except base.DailyReplenishmentError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Failed to update daily replenishment order quantities")
        return jsonify({"success": False, "message": f"保存订货量失败：{exc}"}), 500


@daily_replenishment_operation_bp.get("/api/ai/daily-replenishment-operation/download")
@require_permission(PERMISSION_NAME)
def download():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    snapshot, _ = _resolve_snapshot_for_user(user_name)
    if snapshot is None:
        return jsonify({"success": False, "message": "今日快照尚未生成"}), 404
    from io import BytesIO
    from openpyxl import Workbook
    payload = _scope_snapshot_payload(load_snapshot_cached(snapshot), access)
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, sheet in (payload.get('sheets') or {}).items():
        ws = workbook.create_sheet(name)
        for column, value in enumerate(sheet.get('columns') or [], 1):
            base._write_literal(ws.cell(1, column), value)
        for index, row in enumerate(sheet.get('rows') or [], 2):
            for column, value in enumerate(row, 1):
                base._write_literal(ws.cell(index, column), value)
        base._style_worksheet(ws, len(sheet.get('rows') or []) + 1, len(sheet.get('columns') or []))
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    stream.seek(0)
    return send_file(stream, as_attachment=True, download_name=snapshot.name,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', max_age=0)


# ---------------------------------------------------------------- 采购计划导入模板
# 复刻 Excel【日常补货】页「生成采购计划」按钮的口径：
#   订货量 > 10 的行 -> *SKU（有【下单SKU】就用它，否则原 SKU）
#   *计划采购量 = 订货量；商品备注 = "成品SKU：原 SKU" +（需下单里该 SKU 的备注）
#   店铺与采购方分别取快照里的店铺和运营负责人，采购仓库固定为青岛仓。
PURCHASE_PLAN_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "templates" / "import_purchase_plan_template.xlsx"
PURCHASE_PLAN_HEADERS = (
    "临时单号",
    "*SKU",
    "店铺",
    "FNSKU",
    "专属类型",
    "*采购仓库",
    "供应商",
    "采购方",
    "*计划采购量",
    "采购员",
    "预计到货时间",
    "商品备注",
    "创建时间",
    "单据备注",
)
PURCHASE_PLAN_WAREHOUSE = "青岛仓"
PURCHASE_PLAN_MIN_QTY = 10


def _purchase_plan_item_details(sheet_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """从快照中挑出订货量大于阈值的行，并保留店铺及负责人。"""
    columns = [str(value or "").strip() for value in sheet_payload.get("columns") or []]
    try:
        sku_index = columns.index("SKU")
        qty_index = columns.index("订货量")
    except ValueError as exc:
        raise base.DailyReplenishmentError("快照缺少“SKU”或“订货量”列，无法生成采购计划") from exc
    operator_index = columns.index("运营") if "运营" in columns else None
    store_index = columns.index("店铺") if "店铺" in columns else None
    items: list[dict[str, Any]] = []
    for row_index, row in enumerate(sheet_payload.get("rows") or []):
        if not isinstance(row, (list, tuple)) or len(row) <= max(sku_index, qty_index):
            continue
        source_sku = str(row[sku_index] or "").strip()
        quantity = base._as_number(row[qty_index])
        if not source_sku or quantity is None or quantity <= PURCHASE_PLAN_MIN_QTY:
            continue
        operator = ""
        if operator_index is not None and operator_index < len(row):
            operator = str(row[operator_index] or "").strip()
        store = ""
        if store_index is not None and store_index < len(row):
            store = str(row[store_index] or "").strip()
        items.append({
            "row_index": row_index,
            "source_sku": source_sku,
            "quantity": int(round(quantity)),
            "store": store,
            "purchaser": operator,
        })
    return items


def _purchase_plan_items(sheet_payload: dict[str, Any]) -> list[tuple[str, int]]:
    """从日常补货快照中挑出”订货量 > 10”的 (原 SKU, 订货量)。"""
    return [
        (item["source_sku"], item["quantity"])
        for item in _purchase_plan_item_details(sheet_payload)
    ]


def _purchase_plan_sku_map(skus: set[str]) -> dict[str, str]:
    """读取 XiaDanSKU 的「SKU -> 下单SKU」映射，等价于 Excel 手工修正过的【下单SKU】列。"""
    if not skus:
        return {}
    literals = ",".join(f"N'{escape_sql_literal(sku, escape_percent=False)}'" for sku in sorted(skus))
    try:
        rows = base.sf_db(
            "/* daily_replenishment_operation:purchase_plan_sku_map */\n"
            "SELECT SKU,XiaDanSKU FROM dbo.XiaDanSKU "
            f"WHERE SKU IN ({literals})"
        ) or []
    except Exception:
        current_app.logger.warning("读取 XiaDanSKU 映射失败，采购计划将直接使用原 SKU", exc_info=True)
        return {}
    mapping: dict[str, str] = {}
    for raw in rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        sku = str(raw[0] or "").strip()
        target = str(raw[1] or "").strip()
        if sku and target:
            mapping[sku] = target
    return mapping


def _purchase_plan_notes(skus: set[str]) -> dict[str, str]:
    """读取今天【需下单】的备注（MeiTianXiaDan.BeiZhu），等价于 Excel 的 VLOOKUP(需下单!E:J,6)。"""
    if not skus:
        return {}
    literals = ",".join(f"N'{escape_sql_literal(sku, escape_percent=False)}'" for sku in sorted(skus))
    today = date.today().isoformat()
    try:
        rows = base.sf_db(
            "/* daily_replenishment_operation:purchase_plan_notes */\n"
            "SELECT SKU,BeiZhu FROM dbo.MeiTianXiaDan "
            f"WHERE RiQi='{today}' AND SKU IN ({literals})"
        ) or []
    except Exception:
        current_app.logger.warning("读取需下单备注失败，采购计划备注只保留成品SKU", exc_info=True)
        return {}
    notes: dict[str, str] = {}
    for raw in rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        sku = str(raw[0] or "").strip()
        note = str(raw[1] or "").strip()
        if sku and note:
            notes.setdefault(sku, note)
    return notes


def _purchase_plan_rows_from_items(items: list[dict[str, Any]]) -> list[list[Any]]:
    """根据确认后的采购明细拼出模板 Sheet1 的 14 列数据行。"""
    if not items:
        return []
    source_skus = {item["source_sku"] for item in items}
    sku_map = _purchase_plan_sku_map(source_skus)
    chosen_skus = {(sku_map.get(sku) or sku) for sku in source_skus}
    notes = _purchase_plan_notes(chosen_skus)
    rows: list[list[Any]] = []
    for item in items:
        source_sku = item["source_sku"]
        quantity = item["quantity"]
        sku = sku_map.get(source_sku) or source_sku
        remark = f"成品SKU：{source_sku}"
        note = notes.get(sku)
        if note:
            remark = f"{remark} {note}"
        rows.append([
            "",                       # 临时单号
            sku,                      # *SKU
            item["store"],           # 店铺
            "",                       # FNSKU
            "",                       # 专属类型
            PURCHASE_PLAN_WAREHOUSE,  # *采购仓库
            "",                       # 供应商
            item["purchaser"],       # 采购方
            quantity,                 # *计划采购量
            "",                       # 采购员
            "",                       # 预计到货时间
            remark,                   # 商品备注
            "",                       # 创建时间
            "",                       # 单据备注
        ])
    return rows


def _purchase_plan_rows(sheet_payload: dict[str, Any]) -> list[list[Any]]:
    """拼出模板 Sheet1 的 14 列数据行。"""
    return _purchase_plan_rows_from_items(_purchase_plan_item_details(sheet_payload))


def _purchase_plan_confirmed_rows(
    sheet_payload: dict[str, Any], confirmations: list[dict[str, Any]]
) -> list[list[Any]]:
    """根据明细确认弹窗里的行号和数量生成最终导出行。"""
    candidates = {
        item["row_index"]: item
        for item in _purchase_plan_item_details(sheet_payload)
    }
    if not confirmations:
        raise base.DailyReplenishmentError("请至少选择一条采购明细")
    items: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw in confirmations:
        if not isinstance(raw, dict):
            raise base.DailyReplenishmentError("采购明细格式不正确")
        try:
            row_index = int(raw.get("index"))
        except (TypeError, ValueError) as exc:
            raise base.DailyReplenishmentError("采购明细缺少有效行号") from exc
        if row_index in seen or row_index not in candidates:
            raise base.DailyReplenishmentError("采购明细已变化，请刷新后重新确认")
        item = dict(candidates[row_index])
        item["quantity"] = _coerce_order_quantity(raw.get("quantity"), allow_zero=False)
        items.append(item)
        seen.add(row_index)
    return _purchase_plan_rows_from_items(items)


def _purchase_plan_inline_string_cell(reference: str, value: Any, style: str = "") -> str:
    text = xml_escape(str(value or ""))
    style_attr = f' s="{style}"' if style else ""
    return f'<c r="{reference}"{style_attr} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _purchase_plan_template_row(row_number: int, values: list[Any]) -> str:
    columns = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    cells: list[str] = []
    for index, value in enumerate(values, start=1):
        if value in (None, ""):
            continue
        reference = f"{columns[index - 1]}{row_number}"
        if index == 2:
            cells.append(_purchase_plan_inline_string_cell(reference, value, "6"))
        elif index == 6:
            cells.append(_purchase_plan_inline_string_cell(reference, value, "7"))
        elif index == 9:
            cells.append(f'<c r="{reference}"><v>{int(value)}</v></c>')
        else:
            cells.append(_purchase_plan_inline_string_cell(reference, value))
    # Keep the template's yyyy-mm-dd formatting on the creation-time column.
    cells.append(f'<c r="M{row_number}" s="2"/>')
    return (
        f'<row r="{row_number}" spans="1:14" ht="18.75" customHeight="1">'
        + "".join(cells)
        + "</row>"
    )


def _write_purchase_plan_template(rows: list[list[Any]], destination: Path) -> None:
    """Fill the provided XLSX template while preserving its hidden lists and formatting."""
    if not PURCHASE_PLAN_TEMPLATE_PATH.is_file():
        raise base.DailyReplenishmentError(
            f"采购计划模板不存在：{PURCHASE_PLAN_TEMPLATE_PATH.name}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_destination = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    row_count = max(67, len(rows) + 1)
    if not rows:
        body_rows = "".join(
            _purchase_plan_template_row(row_number, [""] * len(PURCHASE_PLAN_HEADERS))
            for row_number in range(2, row_count + 1)
        )
    else:
        body_rows = "".join(
            _purchase_plan_template_row(row_number, values)
            for row_number, values in enumerate(rows, start=2)
        )
    try:
        with zipfile.ZipFile(PURCHASE_PLAN_TEMPLATE_PATH, "r") as source_zip, zipfile.ZipFile(
            temp_destination, "w", compression=zipfile.ZIP_DEFLATED
        ) as target_zip:
            for entry in source_zip.infolist():
                data = source_zip.read(entry.filename)
                if entry.filename == "xl/worksheets/sheet1.xml":
                    xml = data.decode("utf-8")
                    header_match = re.search(r'<row r="1".*?</row>', xml, flags=re.DOTALL)
                    if header_match is None:
                        raise base.DailyReplenishmentError("采购计划模板缺少表头行")
                    sheet_data = f"<sheetData>{header_match.group(0)}{body_rows}</sheetData>"
                    xml = re.sub(r'<dimension ref="A1:N\d+"/>', f'<dimension ref="A1:N{row_count}"/>', xml, count=1)
                    xml = re.sub(r"<sheetData>.*?</sheetData>", sheet_data, xml, count=1, flags=re.DOTALL)
                    data = xml.encode("utf-8")
                target_zip.writestr(entry, data)
        os.replace(temp_destination, destination)
    finally:
        temp_destination.unlink(missing_ok=True)


def _sellfox_purchase_payload(rows: list[list[Any]], user_name: str) -> dict[str, Any]:
    items = []
    for row in rows:
        quantity = _coerce_order_quantity(row[8], allow_zero=False)
        if quantity > 2147483647:
            raise base.DailyReplenishmentError("采购数量超过赛狐接口允许的范围")
        # Local store numbers identify several marketplaces, not a unique Sellfox shop.
        # Keep the source store in the remark rather than sending an invalid shopName.
        note = "；".join(filter(None, [str(row[11] or ""), f"店铺编号：{row[2]}" if row[2] else "", f"运营：{row[7]}" if row[7] else ""]))
        item = {"sku": str(row[1]), "planNum": quantity, "note": note}
        items.append(item)
    items.sort(key=lambda item: (item["sku"], item["note"], item.get("partyAName", ""), item["planNum"]))
    return {"warehouseName": PURCHASE_PLAN_WAREHOUSE, "userName": user_name,
            "operationType": 0, "isExpediting": 0, "items": items,
            "note": f"智能补货中心 · {user_name}"}


@daily_replenishment_operation_bp.post("/api/ai/daily-replenishment-operation/purchase-plan/create")
@require_permission(PERMISSION_NAME)
def create_sellfox_purchase_plan():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    if not user_name or not access.get("can_write"):
        return jsonify(success=False, message="当前用户没有创建采购计划的权限"), 403
    body = request.get_json(silent=True)
    confirmations = body.get("items") if isinstance(body, dict) else None
    if not isinstance(confirmations, list) or not confirmations:
        return jsonify(success=False, message="请先选择采购明细"), 400
    try:
        with _refresh_lock:
            snapshot, is_shared = _resolve_snapshot_for_user(user_name)
            if snapshot is None:
                return jsonify(success=False, message="请先生成今日快照"), 404
            payload = _scope_snapshot_payload(load_snapshot_cached(snapshot), access)
            main = (payload.get("sheets") or {}).get(base.SHEET_NAME) or {}
            rows = _purchase_plan_confirmed_rows(main, confirmations)
            store_col = main["columns"].index("店铺")
            for raw in confirmations:
                row = main["rows"][int(raw["index"])]
                if _normalized_store(row[store_col]) not in access.get("write_stores", set()):
                    return jsonify(success=False, message="所选商品含无写入权限的店铺"), 403
            api_payload = _sellfox_purchase_payload(rows, user_name)
            if is_shared:
                own = get_snapshot_path(user_name=user_name)
                own.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snapshot, own)
                snapshot = own
            _save_snapshot_quantity_changes(snapshot, access, confirmations)
        ledger = get_output_dir(create=True) / "_采购计划" / "sellfox_requests.sqlite"
        result, reused = sellfox_purchase.create_once(api_payload, ledger)
        return jsonify(success=True, message="该采购计划已创建，请到赛狐查看" if reused else "已在赛狐保存采购计划",
                       data=result, reused=reused, item_count=len(rows), creator=user_name,
                       warehouse=PURCHASE_PLAN_WAREHOUSE)
    except base.DailyReplenishmentError as exc:
        return jsonify(success=False, message=str(exc)), 400
    except sellfox_purchase.PurchaseRejected as exc:
        return jsonify(success=False, message=str(exc)), 400
    except sellfox_purchase.PurchaseUncertain as exc:
        return jsonify(success=False, message=str(exc), uncertain=True), 409
    except Exception:
        current_app.logger.exception("Failed to create Sellfox purchase plan")
        return jsonify(success=False, message="创建采购计划失败，请联系管理员检查赛狐连接"), 500


@daily_replenishment_operation_bp.route("/api/ai/daily-replenishment-operation/purchase-plan", methods=("GET", "POST"))
@require_permission(PERMISSION_NAME)
def purchase_plan():
    """确认采购明细后导出采购导入模板（下单导入.xlsx）。"""
    try:
        user_name = _current_user_name()
        _, access = scoped_query_executor(user_name)
        snapshot, is_shared = _resolve_snapshot_for_user(user_name)
        if snapshot is None:
            return jsonify({"success": False, "message": "今日的智能补货中心-亚马逊快照尚未生成，请先点“生成 / 刷新”"}), 404
        payload = _scope_snapshot_payload(load_snapshot_cached(snapshot), access)
        sheet_payload = (payload.get("sheets") or {}).get(base.SHEET_NAME) or {}
        confirmed_items: list[dict[str, Any]] | None = None
        if request.method == "POST":
            body = request.get_json(silent=True) or {}
            confirmed_items = body.get("items") if isinstance(body, dict) else None
            if not isinstance(confirmed_items, list):
                return jsonify({"success": False, "message": "采购明细格式不正确"}), 400
            rows = _purchase_plan_confirmed_rows(sheet_payload, confirmed_items)
            with _refresh_lock:
                if is_shared:
                    own_snapshot = get_snapshot_path(user_name=user_name)
                    own_snapshot.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(snapshot, own_snapshot)
                    snapshot = own_snapshot
                _save_snapshot_quantity_changes(snapshot, access, confirmed_items)
        else:
            rows = _purchase_plan_rows(sheet_payload)

        today = date.today()
        download_name = f"{today.month}.{today.day}下单导入.xlsx"
        output_dir = get_output_dir(create=True) / "_采购计划"
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / f"{today.isoformat()}_{uuid.uuid4().hex[:8]}下单导入.xlsx"
        _write_purchase_plan_template(rows, destination)

        response = send_file(destination, as_attachment=True, download_name=download_name, max_age=0)
        response.headers["X-Purchase-Plan-Rows"] = str(len(rows))
        response.headers["X-Purchase-Plan-Min-Qty"] = str(PURCHASE_PLAN_MIN_QTY)
        return response
    except base.DailyReplenishmentError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Failed to build daily replenishment purchase plan")
        return jsonify({"success": False, "message": f"生成采购计划失败：{exc}"}), 500


@daily_replenishment_operation_bp.route("/api/ai/daily-replenishment-operation/preferences", methods=("GET", "PUT"))
@require_permission(PERMISSION_NAME)
def table_preferences():
    """User preferences live beside persistent snapshots, never in image/code layers."""
    import json
    import sqlite3
    from contextlib import closing
    owner = str(session.get("feishu_user_id") or _current_user_name()).strip()
    if not owner:
        return jsonify(success=False, message="请先登录"), 401
    path = get_output_dir(create=True) / "table_preferences.sqlite3"
    with closing(sqlite3.connect(path, timeout=15)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS table_preferences (owner TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        if request.method == "PUT":
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict) or payload.get("version") != 1:
                return jsonify(success=False, message="表格设置格式无效"), 400
            encoded = json.dumps(payload, ensure_ascii=False)
            if len(encoded.encode("utf-8")) > 262144:
                return jsonify(success=False, message="表格设置过大"), 400
            db.execute("INSERT INTO table_preferences(owner,payload) VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET payload=excluded.payload", (owner, encoded))
            db.commit()
        else:
            row = db.execute("SELECT payload FROM table_preferences WHERE owner=?", (owner,)).fetchone()
            payload = json.loads(row[0]) if row else None
    response = jsonify(success=True, preferences=payload)
    response.headers["Cache-Control"] = "no-store"
    return response


@daily_replenishment_operation_bp.get("/api/ai/daily-replenishment-operation/shipping-reference")
@require_permission(PERMISSION_NAME)
def shipping_reference():
    """Read current stock and per-country sales; never create shipping plans."""
    from .shipping_reference import REFERENCE, recommend
    sku = str(request.args.get("sku") or "").strip()
    if not sku or len(sku) > 150:
        return jsonify(success=False, message="请提供有效 SKU"), 400
    execute, access = scoped_query_executor(_current_user_name())
    if sku not in (access.get("visible_skus") or set()):
        return jsonify(success=False, message="该 SKU 不在当前账号的店铺权限范围内"), 403
    safe_sku = escape_sql_literal(sku, escape_percent=False)
    try:
        settings = _settings()
        start, end = settings['sales_start'], settings['sales_end']
        period = (end - start).days + 1
        rows = execute(f"""/* daily_replenishment:shipping_reference */
WITH Stock AS (
 SELECT CASE Cang WHEN N'美国仓' THEN N'美国' WHEN N'加拿大仓' THEN N'加拿大'
        WHEN N'英国仓' THEN N'英国' WHEN N'日本仓' THEN N'日本'
        WHEN N'澳洲仓' THEN N'澳大利亚' WHEN N'澳洲' THEN N'澳大利亚' ELSE Cang END Country,
        SUM(CAST(ISNULL(KeShou,0) AS FLOAT)) Sellable
 FROM v_KuCun2 WHERE SKU=N'{safe_sku}' GROUP BY Cang
), Sales AS (
 SELECT CASE Guo WHEN N'澳洲' THEN N'澳大利亚' ELSE Guo END Country,
        SUM(CAST(ISNULL(HeSuanXiaoLiang,0) AS FLOAT)) Sales
 FROM v_XiaoShouLiang WHERE SKU=N'{safe_sku}' AND RiQi BETWEEN '{start.isoformat()}' AND '{end.isoformat()}' GROUP BY Guo
), Countries AS (SELECT Country FROM Stock UNION SELECT Country FROM Sales)
SELECT c.Country,ISNULL((SELECT SUM(s.Sellable) FROM Stock s WHERE s.Country=c.Country),0),
 ISNULL((SELECT SUM(s.Sales) FROM Sales s WHERE s.Country=c.Country),0)/{float(period)}
FROM Countries c WHERE c.Country IS NOT NULL ORDER BY c.Country""") or []
        local_rows = execute(f"""/* daily_replenishment:shipping_reference_local */
SELECT SUM(CAST(ISNULL(ShuLiang,0) AS FLOAT)) FROM v_KuCun1 WHERE SKU=N'{safe_sku}'""") or []
        raw_local = local_rows[0] if local_rows else None
        raw_local = raw_local[0] if isinstance(raw_local, (tuple, list)) else raw_local
        local_stock = max(0, float(raw_local)) if raw_local is not None else None
        countries = [recommend(str(r[0]).strip(), r[1] or 0, r[2] or 0) for r in rows]
        response = jsonify(success=True, sku=sku, countries=countries, local_stock=local_stock,
                           bridge_total=sum(r['bridge_qty'] for r in countries),
                           reference_date=REFERENCE['as_of'], sales_start=start.isoformat(), sales_end=end.isoformat())
        response.headers['Cache-Control'] = 'no-store'
        return response
    except Exception:
        current_app.logger.exception("Failed to load shipping reference")
        return jsonify(success=False, message="发货参考暂时无法读取，请稍后重试"), 500
