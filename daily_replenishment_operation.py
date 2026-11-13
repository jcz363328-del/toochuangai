from __future__ import annotations

import os
import tempfile
import hashlib
import copy
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from flask import Blueprint, current_app, g, has_request_context, jsonify, render_template, request, send_file, session
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

import daily_replenishment as base
from department_permissions import require_permission
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
        if "daily_replenishment:smart_sales_history" in marker or "daily_replenishment:smart_sites" in marker:
            return [row for row in rows if row and str(row[0] or "").strip() in visible_skus]
        if "daily_replenishment:smart_margins" in marker:
            return [row for row in rows if row and str(row[0] or "").strip() in visible_skus]
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
    """Return the shared full-scope snapshot for today.

    Per-operator snapshots are stored beside the shared snapshot.  Falling back
    to the newest file can select another operator's small, already-filtered
    workbook and leave the current operator with zero rows after authorization
    filtering.  The full-scope workbook is the largest same-day snapshot in
    this store, so use size as the stable full-scope signal and mtime only as a
    tie-breaker.
    """
    snapshot_root = get_output_dir() / "_每日快照"
    if not snapshot_root.is_dir():
        return None
    filename = f"{date.today():%Y%m%d}日常补货运营.xlsx"
    candidates = [path for path in snapshot_root.rglob(filename) if path.is_file()]
    return max(candidates, key=lambda path: (path.stat().st_size, path.stat().st_mtime_ns)) if candidates else None


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
        styles = sheet.get("styles") or {}
        sheet["styles"] = {
            str(new_index): styles[str(old_index)]
            for new_index, old_index in enumerate(kept_indexes)
            if str(old_index) in styles
        }
    return scoped


def _resolve_snapshot_for_user(user_name: str) -> tuple[Path | None, bool]:
    own = get_today_snapshot(user_name=user_name)
    if own is not None:
        return own, False
    return get_shared_today_snapshot(), True


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
                    "styles": {
                        str(index): dict(row.get("styles") or {})
                        for index, row in enumerate(serialized.get("rows") or [])
                        if row.get("styles")
                    },
                    "purpose": "智能补货中心-运营快照",
                }
            else:
                sheets[name] = {
                    "columns": [str(value or "") for value in (values[0] if values else [])],
                    "rows": [[base._json_value(value) for value in row] for row in values[1:] if any(value not in (None, "") for value in row)],
                    "header_comments": {},
                    "comments": {},
                    "styles": {},
                    "purpose": "智能补货中心-运营快照",
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
    snapshot_meta["download_available"] = not is_shared
    _attach_client_cache_meta(snapshot_meta, snapshot_path, user_name, access)
    response = current_app.make_response(
        render_template(
            "daily_replenishment_operation.html",
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
        scoped_executor, access = scoped_query_executor(user_name)
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
                        dataset = generate_operation_dataset(source, query_executor=scoped_executor, overrides=overrides)
                        snapshot = save_operation_workbook(dataset, get_snapshot_path(user_name=user_name))
                    payload = _sheet_payload(dataset)
                    snapshot_meta = _snapshot_payload(snapshot, user_name=user_name)
                    _attach_client_cache_meta(snapshot_meta, snapshot, user_name, access)
                    payload.update(success=True, stores=sorted(stores), snapshot=snapshot_meta)
                    cache_snapshot_payload(snapshot, payload)
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
        return jsonify({"success": False, "message": f"智能补货中心-运营刷新失败：{exc}"}), 500


@daily_replenishment_operation_bp.get("/api/ai/daily-replenishment-operation/refresh/<job_id>")
@require_permission(PERMISSION_NAME)
def refresh_status(job_id):
    with _refresh_jobs_lock:
        job = _refresh_jobs.get(job_id)
        if not job or job.get("user") != _current_user_name():
            return jsonify({"success": False, "message": "刷新任务不存在"}), 404
        result = dict(job)
    if result.get("status") == "completed":
        return jsonify(result["payload"])
    return jsonify({"success": result.get("status") != "failed", "status": result.get("status"), "message": result.get("message", "")})


@daily_replenishment_operation_bp.get("/api/ai/daily-replenishment-operation/data")
@require_permission(PERMISSION_NAME)
def data():
    user_name = _current_user_name()
    _, access = scoped_query_executor(user_name)
    stores = set(access["read_stores"])
    snapshot, is_shared = _resolve_snapshot_for_user(user_name)
    if snapshot is None:
        return jsonify({"success": False, "message": "今日的智能补货中心-运营快照尚未生成"}), 404
    payload = load_snapshot_cached(snapshot)
    # Apply authorization on every response, including a user's own snapshot.
    # File ownership only selects a cache candidate; it must not grant data scope.
    payload = _scope_snapshot_payload(payload, access)
    snapshot_meta = _snapshot_payload(snapshot, user_name=user_name)
    snapshot_meta["download_available"] = not is_shared
    _attach_client_cache_meta(snapshot_meta, snapshot, user_name, access)
    payload.update(success=True, stores=sorted(stores), snapshot=snapshot_meta)
    return jsonify(payload)


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


@daily_replenishment_operation_bp.get("/api/ai/daily-replenishment-operation/download")
@require_permission(PERMISSION_NAME)
def download():
    user_name = _current_user_name()
    scoped_query_executor(user_name)
    snapshot = get_today_snapshot(user_name=user_name)
    if snapshot is None:
        return jsonify({"success": False, "message": "今日快照尚未生成"}), 404
    return send_file(snapshot, as_attachment=True, download_name=snapshot.name)


# ---------------------------------------------------------------- 采购计划导入模板
# 复刻 Excel【日常补货】页「生成采购计划」按钮的口径：
#   订货量 > 10 的行 -> *SKU（有【下单SKU】就用它，否则原 SKU）
#   *计划采购量 = 订货量；备注 = "成品SKU：原SKU" +（需下单里该 SKU 的备注）
PURCHASE_PLAN_HEADERS = ("*SKU", "店铺", "FNSKU", "专属类型", "仓库", "MSKU", "供应商", "*计划采购量", "备注")
PURCHASE_PLAN_MIN_QTY = 10


def _purchase_plan_items(sheet_payload: dict[str, Any]) -> list[tuple[str, int]]:
    """从日常补货快照中挑出”订货量 > 10”的 (原 SKU, 订货量)。"""
    columns = [str(value or "").strip() for value in sheet_payload.get("columns") or []]
    try:
        sku_index = columns.index("SKU")
        qty_index = columns.index("订货量")
    except ValueError as exc:
        raise base.DailyReplenishmentError("快照缺少“SKU”或“订货量”列，无法生成采购计划") from exc
    items: list[tuple[str, int]] = []
    for row in sheet_payload.get("rows") or []:
        if not isinstance(row, (list, tuple)) or len(row) <= max(sku_index, qty_index):
            continue
        source_sku = str(row[sku_index] or "").strip()
        quantity = base._as_number(row[qty_index])
        if not source_sku or quantity is None or quantity <= PURCHASE_PLAN_MIN_QTY:
            continue
        items.append((source_sku, int(round(quantity))))
    return items


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


def _purchase_plan_rows(sheet_payload: dict[str, Any]) -> list[list[Any]]:
    """拼出采购导入模板的数据行：*SKU / 店铺 / FNSKU / 专属类型 / 仓库 / MSKU / 供应商 / *计划采购量 / 备注。"""
    items = _purchase_plan_items(sheet_payload)
    if not items:
        return []
    source_skus = {sku for sku, _ in items}
    sku_map = _purchase_plan_sku_map(source_skus)
    chosen_skus = {(sku_map.get(sku) or sku) for sku in source_skus}
    notes = _purchase_plan_notes(chosen_skus)
    rows: list[list[Any]] = []
    for source_sku, quantity in items:
        sku = sku_map.get(source_sku) or source_sku
        remark = f"成品SKU：{source_sku}"
        note = notes.get(sku)
        if note:
            remark = f"{remark} {note}"
        # 店铺/FNSKU/专属类型/仓库/MSKU/供应商 与原 Excel 一致，留空由采购填写
        rows.append([sku, "", "", "", "", "", "", quantity, remark])
    return rows


@daily_replenishment_operation_bp.get("/api/ai/daily-replenishment-operation/purchase-plan")
@require_permission(PERMISSION_NAME)
def purchase_plan():
    """按 Excel【日常补货】页「生成采购计划」的逻辑，导出采购导入模板（下单导入.xlsx）。"""
    try:
        user_name = _current_user_name()
        _, access = scoped_query_executor(user_name)
        snapshot, _is_shared = _resolve_snapshot_for_user(user_name)
        if snapshot is None:
            return jsonify({"success": False, "message": "今日的智能补货中心-运营快照尚未生成，请先点“生成 / 刷新”"}), 404
        payload = _scope_snapshot_payload(load_snapshot_cached(snapshot), access)
        sheet_payload = (payload.get("sheets") or {}).get(base.SHEET_NAME) or {}
        rows = _purchase_plan_rows(sheet_payload)

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "下单导入"
        worksheet.append(list(PURCHASE_PLAN_HEADERS))
        for values in rows:
            worksheet.append(values)
        for cell in worksheet[1]:
            cell.font = Font(bold=True)
        worksheet.freeze_panes = "A2"
        for column, width in (("A", 20), ("B", 12), ("C", 16), ("H", 14), ("I", 56)):
            worksheet.column_dimensions[column].width = width

        today = date.today()
        download_name = f"{today.month}.{today.day}下单导入.xlsx"
        output_dir = get_output_dir(create=True) / "_采购计划"
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / f"{today.isoformat()}_{uuid.uuid4().hex[:8]}下单导入.xlsx"
        try:
            workbook.save(destination)
        finally:
            workbook.close()

        response = send_file(destination, as_attachment=True, download_name=download_name, max_age=0)
        response.headers["X-Purchase-Plan-Rows"] = str(len(rows))
        response.headers["X-Purchase-Plan-Min-Qty"] = str(PURCHASE_PLAN_MIN_QTY)
        return response
    except base.DailyReplenishmentError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Failed to build daily replenishment purchase plan")
        return jsonify({"success": False, "message": f"生成采购计划失败：{exc}"}), 500
