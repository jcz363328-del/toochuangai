from __future__ import annotations

import os
import tempfile
import hashlib
import copy
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from flask import Blueprint, current_app, g, has_request_context, jsonify, render_template, request, send_file, session
from openpyxl import load_workbook

import daily_replenishment as base
from department_permissions import require_permission
from tools import escape_sql_literal


daily_replenishment_operation_bp = Blueprint("daily_replenishment_operation", __name__)

PERMISSION_NAME = "daily_replenishment_operation"
SHEET_ORDER = ("库存明细", "在途", "日常补货", "FBA发货", "每日库存", "海运即将到货", "低毛利率")
_refresh_lock = Lock()
_snapshot_cache_lock = Lock()
_snapshot_cache: dict[str, tuple[int, dict[str, Any]]] = {}


def _normalized_store(value: Any) -> str:
    return str(value or "").strip()


def get_store_permissions(user_name: str, *, query_executor=base.sf_db) -> dict[str, Any]:
    """按飞书用户名读取 DianQuanXian：2=阅读，1=增删改。"""
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
    """Return the newest existing snapshot for today when the current user has none."""
    snapshot_root = get_output_dir() / "_每日快照"
    if not snapshot_root.is_dir():
        return None
    filename = f"{date.today():%Y%m%d}日常补货运营.xlsx"
    candidates = [path for path in snapshot_root.rglob(filename) if path.is_file()]
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None


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
    return scoped


def _resolve_snapshot_for_user(user_name: str) -> tuple[Path | None, bool]:
    own = get_today_snapshot(user_name=user_name)
    if own is not None:
        return own, False
    return get_shared_today_snapshot(), True


def _settings(source: Path | None = None) -> dict[str, Any]:
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
    return settings


def generate_operation_dataset(source: Path | None = None, *, query_executor=base.sf_db) -> dict[str, Any]:
    settings = _settings(source)
    main = base.generate_database_dataset(settings, query_executor=query_executor)
    related = base.generate_button_sheets(settings, query_executor=query_executor)
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
        for name in SHEET_ORDER:
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

        ordered = [workbook[name] for name in SHEET_ORDER if name in workbook.sheetnames]
        remaining = [sheet for sheet in workbook.worksheets if sheet.title not in SHEET_ORDER]
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
        "purpose": "原运营版按钮生成的日常补货主表",
    }
    return {"sheets": sheets, "generation": main.get("generation") or {}}


def load_snapshot(path: Path) -> dict[str, Any]:
    main_dataset = base.load_daily_replenishment(path)
    workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        sheets: dict[str, Any] = {}
        for name in SHEET_ORDER:
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
                    "purpose": "日常补货运营快照",
                }
            else:
                sheets[name] = {
                    "columns": [str(value or "") for value in (values[0] if values else [])],
                    "rows": [[base._json_value(value) for value in row] for row in values[1:] if any(value not in (None, "") for value in row)],
                    "header_comments": {},
                    "comments": {},
                    "purpose": "日常补货运营快照",
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
    snapshot = path or get_today_snapshot(user_name=user_name)
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


@daily_replenishment_operation_bp.get("/ai/daily-replenishment-operation")
@require_permission(PERMISSION_NAME)
def page():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    stores = set(access["read_stores"])
    snapshot_path, is_shared = _resolve_snapshot_for_user(user_name)
    snapshot_meta = _snapshot_payload(snapshot_path, user_name=user_name)
    snapshot_meta["download_available"] = not is_shared
    initial_data = None
    if snapshot_path is not None:
        initial_data = load_snapshot_cached(snapshot_path)
        # Never trust the snapshot's owner directory as an authorization boundary.
        # A snapshot may have been generated before permissions changed (or while an
        # administrator was impersonating this user), so every read must be scoped
        # again using the effective identity of the current request.
        initial_data = _scope_snapshot_payload(initial_data, access)
        initial_data.update(
            success=True,
            stores=sorted(stores),
            snapshot=snapshot_meta,
            message="今日快照已直接加载",
        )
    return render_template(
        "daily_replenishment_operation.html",
        snapshot=snapshot_meta,
        initial_data=initial_data,
        operator_stores=sorted(stores),
        can_write=bool(access["can_write"]),
    )


@daily_replenishment_operation_bp.post("/api/ai/daily-replenishment-operation/refresh")
@require_permission(PERMISSION_NAME)
def refresh():
    try:
        user_name = _current_user_name()
        scoped_executor, access = scoped_query_executor(user_name)
        if not access["can_write"]:
            return jsonify({"success": False, "message": "当前用户在 DianQuanXian 中只有阅读权限，不能生成或刷新"}), 403
        stores = set(access["read_stores"])
        uploaded = request.files.get("file")
        source = None
        if uploaded and getattr(uploaded, "filename", ""):
            source = base.save_uploaded_workbook(uploaded)
        else:
            source = base.resolve_source_path()
        with _refresh_lock:
            dataset = generate_operation_dataset(source, query_executor=scoped_executor)
            snapshot = save_operation_workbook(dataset, get_snapshot_path(user_name=user_name))
        payload = _sheet_payload(dataset)
        payload.update(success=True, stores=sorted(stores), snapshot=_snapshot_payload(snapshot, user_name=user_name), message="日常补货运营的 7 个工作表已按店铺权限同步刷新")
        cache_snapshot_payload(snapshot, payload)
        return jsonify(payload)
    except base.DailyReplenishmentError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Failed to refresh daily replenishment operation")
        return jsonify({"success": False, "message": f"日常补货运营刷新失败：{exc}"}), 500


@daily_replenishment_operation_bp.get("/api/ai/daily-replenishment-operation/data")
@require_permission(PERMISSION_NAME)
def data():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    stores = set(access["read_stores"])
    snapshot, is_shared = _resolve_snapshot_for_user(user_name)
    if snapshot is None:
        return jsonify({"success": False, "message": "今日的日常补货运营快照尚未生成"}), 404
    payload = load_snapshot_cached(snapshot)
    # Apply authorization on every response, including a user's own snapshot.
    # File ownership only selects a cache candidate; it must not grant data scope.
    payload = _scope_snapshot_payload(payload, access)
    snapshot_meta = _snapshot_payload(snapshot, user_name=user_name)
    snapshot_meta["download_available"] = not is_shared
    payload.update(success=True, stores=sorted(stores), snapshot=snapshot_meta)
    return jsonify(payload)


@daily_replenishment_operation_bp.get("/api/ai/daily-replenishment-operation/download")
@require_permission(PERMISSION_NAME)
def download():
    user_name = _current_user_name()
    scoped_query_executor(user_name)
    snapshot = get_today_snapshot(user_name=user_name)
    if snapshot is None:
        return jsonify({"success": False, "message": "今日快照尚未生成"}), 404
    return send_file(snapshot, as_attachment=True, download_name=snapshot.name)
