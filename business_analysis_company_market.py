"""手动导入的美国站市场与大盘对比数据（类目 / 公司订单 / 结算口径）。

数据来自运营同学每月维护的 Excel，页面按月份查看与导入。
存储为本地 JSON 文件，写入使用临时文件 + 原子替换，避免读到半截内容。
"""

from __future__ import annotations

import io
import json
import os
import re
import tempfile
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any

DATA_PATH = Path(__file__).resolve().parent / "business_analysis" / "data" / "company-market-data.json"

COMPANY_MARKET_METRICS = (
    {
        "key": "categorySalesVolume",
        "label": "类目销量",
        "unit": "件",
        "format": "integer",
        "source": "类目销量",
    },
    {
        "key": "categorySalesAmount",
        "label": "类目销售额",
        "unit": "元",
        "format": "money",
        "source": "类目销售额",
    },
    {
        "key": "companyOrderVolume",
        "label": "公司订单销量",
        "unit": "件",
        "format": "integer",
        "source": "公司订单销量",
    },
    {
        "key": "companyOrderAmount",
        "label": "公司订单销售额",
        "unit": "元",
        "format": "money",
        "source": "公司订单销售额",
    },
    {
        "key": "companySettlementVolume",
        "label": "结算销量",
        "unit": "件",
        "format": "integer",
        "source": "公司结算销量",
    },
    {
        "key": "companySettlementAmount",
        "label": "结算销售额",
        "unit": "元",
        "format": "money",
        "source": "公司结算销售额",
    },
)

# 同义表头，容忍运营同学换过列名
_HEADER_ALIASES = {
    "类目销量": ("类目销量", "类目销售量", "类目销量（件）"),
    "类目销售额": ("类目销售额", "类目销售额（元）", "类目gmv"),
    "公司订单销量": ("公司订单销量", "公司订单销售量", "订单销量", "销售量"),
    "公司订单销售额": ("公司订单销售额", "订单销售额"),
    "公司结算销量": ("公司结算销量", "公司结算销售量", "结算销量", "结算销售量"),
    "公司结算销售额": ("公司结算销售额", "结算销售额", "结算金额"),
    "客单价": ("大盘客单价", "客单价"),
    "类别环比": ("类目环比上月增长率", "类别环比上月增长率"),
    "结算环比": ("公司结算环比上月增长率", "结算环比上月增长率"),
    "销量环比": ("公司销量环比上月增长率", "销量环比上月增长率"),
    "大盘占比": ("假睫毛大盘占比", "大盘占比"),
}

EXTRA_FIELDS = {
    "客单价": "averageOrderValue",
    "类别环比": "categoryMonthOverMonth",
    "结算环比": "settlementMonthOverMonth",
    "销量环比": "volumeMonthOverMonth",
    "大盘占比": "marketShare",
}

# 这些列由系统根据原始列自动计算，不需要手工填写
US_MARKET_DAILY_GROWTH_LABEL = "美国市场日均环比增长率"
DERIVED_COLUMNS = (
    "类目环比上月增长率",
    US_MARKET_DAILY_GROWTH_LABEL,
    "大盘客单价",
    "公司结算环比上月增长率",
    "公司销量环比上月增长率",
    "假睫毛大盘占比",
    "公司客单价",
)

_STORE_LOCK = RLock()
_SCHEMA_VERSION = 2
_DATE_HEADERS = {"日期", "月份", "统计月份", "月度"}


def _infer_column_format(label):
    """根据表头文字推断展示格式。"""
    text = str(label or "").strip()
    normalized = _normalize_header(text)
    if normalized in _DATE_HEADERS or "日期" in normalized or "月份" in normalized:
        return "date"
    if "增长率" in normalized or "占比" in normalized or normalized.endswith("率"):
        return "ratio"
    if "客单价" in normalized or "单价" in normalized or "均价" in normalized:
        return "decimal"
    if "销售额" in normalized or "金额" in normalized or "gmv" in normalized:
        return "money"
    if "销量" in normalized or "数量" in normalized or "件数" in normalized:
        return "integer"
    return "decimal"


def _parse_date_value(value, month):
    """把日期列转成 YYYY-MM-DD；拿不到具体日期时回落到月末。"""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        serial = float(value)
        if 20000 <= serial <= 80000:
            return (date(1899, 12, 30) + timedelta(days=int(serial))).isoformat()
    text = str(value or "").strip()
    match = re.match(r"^(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
        except ValueError:
            pass
    if month:
        return _month_end_date(month)
    return None


class CompanyMarketError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = int(status)
        self.code = str(code)
        self.message = str(message)


def _problem(status, code, message):
    raise CompanyMarketError(status, code, message)


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_header(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s\u3000]+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\([^)]*\)$", "", text)
    return text


def _header_lookup():
    lookup = {}
    for canonical, aliases in _HEADER_ALIASES.items():
        for alias in aliases:
            lookup[_normalize_header(alias)] = canonical
    return lookup


def _parse_number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("，", "").replace(" ", "")
    percent = text.endswith("%")
    text = text.rstrip("%")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        number = float(match.group(0))
    except ValueError:
        return None
    if percent:
        number = number / 100.0
    return number


def _parse_month(value):
    """把 Excel 日期（序列号 / 文本 / datetime）统一成 YYYY-MM。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m")
    if isinstance(value, date):
        return value.strftime("%Y-%m")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        serial = float(value)
        if 20000 <= serial <= 80000:
            base = date(1899, 12, 30)
            parsed = base + timedelta(days=int(serial))
            return parsed.strftime("%Y-%m")
        if 1900 <= serial <= 2100:
            return f"{int(serial):04d}-01"
        return None
    text = str(value).strip()
    match = re.match(r"^(\d{4})[-/年.](\d{1,2})", text)
    if match:
        month = int(match.group(2))
        if 1 <= month <= 12:
            return f"{int(match.group(1)):04d}-{month:02d}"
    match = re.match(r"^(\d{4})(\d{2})$", text)
    if match:
        month = int(match.group(2))
        if 1 <= month <= 12:
            return f"{match.group(1)}-{month:02d}"
    return None


def _month_end_date(month):
    year, month_number = (int(part) for part in month.split("-"))
    if month_number == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month_number + 1, 1)
    return (next_month - timedelta(days=1)).isoformat()


def _days_in_month(month):
    try:
        year, month_number = (int(part) for part in str(month).split("-")[:2])
    except (TypeError, ValueError):
        return None
    if not 1 <= month_number <= 12:
        return None
    return monthrange(year, month_number)[1]


def _ensure_derived_columns(columns):
    """补齐系统派生列，保证旧数据文件也能显示新增指标。"""
    labels = [str(item.get("label") or "") for item in columns]
    for label in DERIVED_COLUMNS:
        if label in labels:
            continue
        item = {"label": label, "format": _infer_column_format(label)}
        if label == US_MARKET_DAILY_GROWTH_LABEL and "类目环比上月增长率" in labels:
            position = labels.index("类目环比上月增长率") + 1
            columns.insert(position, item)
            labels.insert(position, label)
        else:
            columns.append(item)
            labels.append(label)
    return columns


def _empty_store():
    return {"schemaVersion": _SCHEMA_VERSION, "updatedAt": None, "columns": [], "months": {}}


def load_company_market_store(path=DATA_PATH):
    path = Path(path)
    if not path.exists():
        return _empty_store()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _problem(503, "COMPANY_MARKET_STORE_UNREADABLE", f"公司大盘数据文件读取失败：{exc}")
    if not isinstance(raw, dict):
        return _empty_store()
    months = raw.get("months") if isinstance(raw.get("months"), dict) else {}
    normalized = {}
    for month_key, payload in months.items():
        month = _parse_month(month_key)
        if not month or not isinstance(payload, dict):
            continue
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        values = payload.get("values") if isinstance(payload.get("values"), dict) else {}
        normalized[month] = {
            "month": month,
            "date": str(payload.get("date") or _month_end_date(month)),
            "metrics": {key: _parse_number(value) for key, value in metrics.items() if key in {m["key"] for m in COMPANY_MARKET_METRICS}},
            "extras": payload.get("extras") if isinstance(payload.get("extras"), dict) else {},
            "values": values,
            "importedAt": payload.get("importedAt"),
            "sourceFile": payload.get("sourceFile"),
        }
    columns = raw.get("columns") if isinstance(raw.get("columns"), list) else []
    normalized_columns = []
    seen = set()
    for item in columns:
        if isinstance(item, dict):
            label = str(item.get("label") or "").strip()
            column_format = str(item.get("format") or "").strip()
        else:
            label = str(item or "").strip()
            column_format = ""
        if not label or label in seen:
            continue
        seen.add(label)
        normalized_columns.append(
            {"label": label, "format": column_format or _infer_column_format(label)}
        )
    _ensure_derived_columns(normalized_columns)
    return {
        "schemaVersion": int(raw.get("schemaVersion") or _SCHEMA_VERSION),
        "updatedAt": raw.get("updatedAt"),
        "columns": normalized_columns,
        "months": normalized,
    }


def save_company_market_store(store, path=DATA_PATH):
    payload = {
        "schemaVersion": _SCHEMA_VERSION,
        "updatedAt": _now_iso(),
        "columns": [
            {"label": str(item.get("label") or ""), "format": str(item.get("format") or "")}
            for item in (store.get("columns") or [])
            if str(item.get("label") or "").strip()
        ],
        "months": {
            month: {
                "month": item.get("month") or month,
                "date": item.get("date"),
                "metrics": item.get("metrics") or {},
                "extras": item.get("extras") or {},
                "values": item.get("values") or {},
                "importedAt": item.get("importedAt"),
                "sourceFile": item.get("sourceFile"),
            }
            for month, item in sorted((store.get("months") or {}).items())
        },
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return payload


def parse_company_market_workbook(file_bytes, file_name="上传文件.xlsx"):
    """解析 Excel，返回 {month: {date, metrics, extras}}（不落盘）。"""
    import openpyxl

    if not file_bytes:
        _problem(400, "COMPANY_MARKET_EMPTY_FILE", "请选择要导入的 Excel 文件")
    if len(file_bytes) > 20 * 1024 * 1024:
        _problem(400, "COMPANY_MARKET_FILE_TOO_LARGE", "Excel 文件超过 20MB，请拆分后再导入")
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:
        _problem(400, "COMPANY_MARKET_UNREADABLE_FILE", f"Excel 无法解析（需要 .xlsx）：{exc}")

    lookup = _header_lookup()
    parsed_months = {}
    ordered_columns: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    try:
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            header_row = None
            for row in rows:
                normalized_cells = [_normalize_header(cell) for cell in row]
                matched = sum(1 for cell in normalized_cells if cell in lookup)
                if matched >= 3:
                    header_row = row
                    break
            if header_row is None:
                continue
            column_map = {}
            for index, cell in enumerate(header_row):
                canonical = lookup.get(_normalize_header(cell))
                if canonical and canonical not in column_map:
                    column_map[canonical] = index
            if "类目销量" not in column_map and "类目销售额" not in column_map:
                continue
            date_index = None
            for index, cell in enumerate(header_row):
                if _normalize_header(cell) in _DATE_HEADERS:
                    date_index = index
                    break
            if date_index is None:
                date_index = 0
            sheet_columns: list[dict[str, Any]] = []
            for index, cell in enumerate(header_row):
                label = str(cell or "").strip()
                if not label:
                    continue
                sheet_columns.append(
                    {
                        "label": label,
                        "index": index,
                        "format": _infer_column_format(label),
                    }
                )
            for column in sheet_columns:
                if column["label"] not in seen_labels:
                    seen_labels.add(column["label"])
                    ordered_columns.append(
                        {"label": column["label"], "format": column["format"]}
                    )
            for row in rows:
                if row is None:
                    continue
                cells = list(row)
                month = _parse_month(cells[date_index] if date_index < len(cells) else None)
                if not month:
                    continue
                metrics = {}
                for metric in COMPANY_MARKET_METRICS:
                    index = column_map.get(metric["source"])
                    if index is None or index >= len(cells):
                        continue
                    value = _parse_number(cells[index])
                    if value is not None:
                        metrics[metric["key"]] = value
                if not metrics:
                    continue
                extras = {}
                for canonical, field_name in EXTRA_FIELDS.items():
                    index = column_map.get(canonical)
                    if index is None or index >= len(cells):
                        continue
                    value = _parse_number(cells[index])
                    if value is not None:
                        extras[field_name] = value
                values = {}
                source_date = None
                for column in sheet_columns:
                    index = column["index"]
                    if index >= len(cells):
                        continue
                    raw_value = cells[index]
                    if column["format"] == "date":
                        parsed_date = _parse_date_value(raw_value, month)
                        source_date = source_date or parsed_date
                        if parsed_date:
                            values[column["label"]] = parsed_date
                        continue
                    number = _parse_number(raw_value)
                    if number is not None:
                        values[column["label"]] = number
                existing = parsed_months.get(month) or {
                    "month": month,
                    "metrics": {},
                    "extras": {},
                    "values": {},
                }
                existing["metrics"].update(metrics)
                existing["extras"].update(extras)
                existing["values"].update(values)
                existing["date"] = source_date or existing.get("date") or _month_end_date(month)
                parsed_months[month] = existing
    finally:
        try:
            workbook.close()
        except Exception:
            pass

    if not parsed_months:
        _problem(
            400,
            "COMPANY_MARKET_NO_ROWS",
            "没有在文件里识别到可用数据，请确认表头包含「日期 / 类目销量 / 类目销售额 / 公司订单销售额」等列",
        )
    return {
        "columns": ordered_columns,
        "months": {
            month: {
                "month": month,
                "date": item.get("date") or _month_end_date(month),
                "metrics": item["metrics"],
                "extras": item.get("extras") or {},
                "values": item.get("values") or {},
                "sourceFile": file_name,
            }
            for month, item in sorted(parsed_months.items())
        },
    }


def import_company_market_months(file_bytes, file_name, months=None, path=DATA_PATH):
    parsed_result = parse_company_market_workbook(file_bytes, file_name)
    parsed = parsed_result["months"]
    parsed_columns = parsed_result.get("columns") or []
    available = sorted(parsed)
    requested = [str(value).strip() for value in (months or []) if str(value or "").strip()]
    normalized_requested = []
    for value in requested:
        month = _parse_month(value)
        if month and month not in normalized_requested:
            normalized_requested.append(month)
    selected = normalized_requested or available
    missing = [month for month in selected if month not in parsed]
    if missing:
        _problem(
            400,
            "COMPANY_MARKET_MONTH_NOT_FOUND",
            f"文件里没有这些月份的数据：{'、'.join(missing)}",
        )

    imported_at = _now_iso()
    with _STORE_LOCK:
        store = load_company_market_store(path)
        merged_columns = list(store.get("columns") or [])
        existing_labels = {str(item.get("label") or "") for item in merged_columns}
        for column in parsed_columns:
            label = str(column.get("label") or "")
            if label and label not in existing_labels:
                existing_labels.add(label)
                merged_columns.append(
                    {"label": label, "format": column.get("format") or _infer_column_format(label)}
                )
        store["columns"] = merged_columns
        for month in selected:
            payload = parsed[month]
            store["months"][month] = {
                "month": month,
                "date": payload["date"],
                "metrics": payload["metrics"],
                "extras": payload.get("extras") or {},
                "values": payload.get("values") or {},
                "importedAt": imported_at,
                "sourceFile": file_name,
            }
        saved = save_company_market_store(store, path)

    return {
        "importedMonths": selected,
        "availableMonths": available,
        "updatedAt": saved.get("updatedAt"),
        "months": build_company_market_months(saved),
        "columns": saved.get("columns") or [],
    }


def _previous_month_label(month):
    try:
        year, month_number = (int(part) for part in str(month).split("-")[:2])
    except (TypeError, ValueError):
        return None
    if month_number == 1:
        return f"{year - 1}-12"
    return f"{year}-{month_number - 1:02d}"


def _compute_derived_values(values, previous_entry, month=None):
    """根据原始列自动计算增长率、客单价等派生列。"""
    computed: dict[str, float] = {}
    previous_values = (previous_entry or {}).get("values") or {}

    def number(source):
        raw = values.get(source)
        if raw is None or raw == "":
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    category_sales = number("类目销售额")
    category_volume = number("类目销量")
    order_sales = number("公司订单销售额")
    order_volume = number("公司订单销量")
    settlement_sales = number("公司结算销售额")
    previous_category_sales = _to_number(previous_values.get("类目销售额"))

    if category_sales and category_volume:
        computed["大盘客单价"] = round(category_sales / category_volume, 4)
    if order_sales and order_volume:
        computed["公司客单价"] = round(order_sales / order_volume, 4)
    if order_sales and category_sales:
        # 假睫毛大盘占比 = 公司订单销售额 / 类目销售额
        computed["假睫毛大盘占比"] = round(order_sales / category_sales, 6)

    growth = _growth(category_sales, previous_category_sales)
    if growth is not None:
        computed["类目环比上月增长率"] = round(growth, 6)

    # 美国市场日均环比：先按当月自然日折算日均销售额，再与上月日均比较。
    month_key = _parse_month(month or values.get("日期") or "")
    previous_month = (previous_entry or {}).get("month") or (
        _previous_month_label(month_key) if month_key else None
    )
    current_days = _days_in_month(month_key) if month_key else None
    previous_days = _days_in_month(previous_month) if previous_month else None
    if current_days and previous_days and category_sales is not None and previous_category_sales is not None:
        daily_growth = _growth(category_sales / current_days, previous_category_sales / previous_days)
        if daily_growth is not None:
            computed[US_MARKET_DAILY_GROWTH_LABEL] = round(daily_growth, 6)

    growth = _growth(settlement_sales, _to_number(previous_values.get("公司结算销售额")))
    if growth is not None:
        computed["公司结算环比上月增长率"] = round(growth, 6)
    growth = _growth(order_volume, _to_number(previous_values.get("公司订单销量")))
    if growth is not None:
        computed["公司销量环比上月增长率"] = round(growth, 6)
    return computed


def _to_number(raw):
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def upsert_company_market_month(month, values, entry_date=None, path=DATA_PATH):
    """按月写入/覆盖一条公司大盘数据（手动录入）。"""
    parsed_month = _parse_month(month)
    if not parsed_month:
        _problem(400, "COMPANY_MARKET_INVALID_MONTH", "月份格式不正确，应为 YYYY-MM（例如 2026-09）")
    if not isinstance(values, dict):
        _problem(400, "COMPANY_MARKET_INVALID_VALUES", "提交的数据格式不正确")

    with _STORE_LOCK:
        store = load_company_market_store(path)
        columns = store.get("columns") or []
        if not columns:
            _problem(400, "COMPANY_MARKET_NO_COLUMNS", "数据列尚未初始化，请先联系管理员导入一次基础数据")
        labels = [str(item.get("label") or "") for item in columns]
        formats = {str(item.get("label") or ""): str(item.get("format") or "") for item in columns}
        unknown = [str(key) for key in values if str(key) not in labels]
        if unknown:
            _problem(400, "COMPANY_MARKET_UNKNOWN_COLUMN", f"未知列：{'、'.join(unknown)}")

        normalized_values: dict[str, Any] = {}
        for label, raw_value in values.items():
            label = str(label)
            if formats.get(label) == "date":
                text = str(raw_value or "").strip()
                if not text:
                    continue
                parsed_date = _parse_date_value(text, parsed_month)
                if not parsed_date:
                    _problem(400, "COMPANY_MARKET_INVALID_VALUE", f"{label} 不是有效日期：{raw_value}")
                normalized_values[label] = parsed_date
                continue
            text = "" if raw_value is None else str(raw_value).strip()
            if text in {"", "—", "-"}:
                continue
            number = _parse_number(raw_value)
            if number is None:
                _problem(400, "COMPANY_MARKET_INVALID_VALUE", f"{label} 不是有效数字：{raw_value}")
            normalized_values[label] = number

        if not any(label != "日期" for label in normalized_values):
            _problem(400, "COMPANY_MARKET_EMPTY_ENTRY", "请至少填写一个数值后再保存")

        date_value = normalized_values.get("日期") or (
            _parse_date_value(entry_date, parsed_month) if entry_date else None
        ) or f"{parsed_month}-01"
        if "日期" in labels:
            normalized_values["日期"] = date_value

        previous_entry = store["months"].get(_previous_month_label(parsed_month)) or {}
        for label, computed in _compute_derived_values(normalized_values, previous_entry, parsed_month).items():
            if label in labels:
                normalized_values[label] = computed

        metrics = {}
        for metric in COMPANY_MARKET_METRICS:
            value = normalized_values.get(metric["source"])
            if value is not None:
                metrics[metric["key"]] = value
        extras = {
            field_name: normalized_values[source]
            for source, field_name in EXTRA_FIELDS.items()
            if normalized_values.get(source) is not None
        }
        store["months"][parsed_month] = {
            "month": parsed_month,
            "date": date_value,
            "metrics": metrics,
            "extras": extras,
            "values": normalized_values,
            "importedAt": _now_iso(),
            "sourceFile": "手动录入",
        }
        save_company_market_store(store, path)

    return get_company_market_overview(parsed_month, path)


def recalculate_derived_columns(path=DATA_PATH):
    """按原始列重算历史月份的派生列（增长率、客单价）。"""
    with _STORE_LOCK:
        store = load_company_market_store(path)
        months = store.get("months") or {}
        labels = {str(item.get("label") or "") for item in store.get("columns") or []}
        for month in sorted(months):
            entry = months[month]
            values = entry.get("values") or {}
            previous_entry = months.get(_previous_month_label(month)) or {}
            computed = {
                label: value
                for label, value in _compute_derived_values(values, previous_entry, month).items()
                if label in labels
            }
            for label in DERIVED_COLUMNS:
                if not label in labels:
                    continue
                if label in computed:
                    values[label] = computed[label]
                else:
                    values.pop(label, None)
            entry["values"] = values
            extras = entry.get("extras") or {}
            for source, field_name in EXTRA_FIELDS.items():
                if source in values:
                    extras[field_name] = values[source]
                else:
                    extras.pop(field_name, None)
            entry["extras"] = extras
        store["updatedAt"] = _now_iso()
        save_company_market_store(store, path)
        return {"months": len(months), "columns": sorted(labels)}


def build_company_market_months(store):
    months = store.get("months") or {}
    result = []
    for month in sorted(months.keys(), reverse=True):
        item = months[month]
        result.append(
            {
                "month": month,
                "date": item.get("date") or _month_end_date(month),
                "importedAt": item.get("importedAt"),
                "sourceFile": item.get("sourceFile"),
            }
        )
    return result


def _growth(current, previous):
    if current is None or previous in (None, 0):
        return None
    try:
        return float(current) / float(previous) - 1.0
    except (TypeError, ZeroDivisionError):
        return None


def get_market_overview_rows(path=DATA_PATH):
    """把美国站市场的类目销量/销售额整理成「大盘趋势」表格行。

    该接口只暴露大盘趋势原本就公开展示的类目口径，不包含公司订单数据。
    """
    store = load_company_market_store(path)
    months = store.get("months") or {}
    rows = []
    previous_sales = None
    for month in sorted(months):
        values = (months.get(month) or {}).get("values") or {}
        volume = _to_number(values.get("类目销量"))
        amount = _to_number(values.get("类目销售额"))
        if volume is None and amount is None:
            continue
        growth = _to_number(values.get("类目环比上月增长率"))
        if growth is None and amount is not None and previous_sales:
            growth = _growth(amount, previous_sales)
        price = _to_number(values.get("大盘客单价"))
        if price is None and amount is not None and volume:
            price = amount / volume
        rows.append(
            {
                "period": month,
                "salesVolume": volume,
                "salesAmount": amount if amount is not None else 0,
                "monthOverMonthGrowth": growth,
                "averageOrderValue": price,
                "partial": volume is None or amount is None,
            }
        )
        if amount is not None:
            previous_sales = amount
    return rows


def get_company_market_overview(month=None, path=DATA_PATH):
    store = load_company_market_store(path)
    months = build_company_market_months(store)
    columns = list(store.get("columns") or [])
    if not months:
        return {
            "updatedAt": store.get("updatedAt"),
            "months": [],
            "selected": None,
            "previous": None,
            "metrics": list(COMPANY_MARKET_METRICS),
            "columns": columns,
            "history": [],
        }
    requested_month = _parse_month(month) if month else None
    selected_month = requested_month if requested_month in store["months"] else months[0]["month"]
    ordered = sorted(store["months"].keys())
    previous_month = None
    if selected_month in ordered:
        index = ordered.index(selected_month)
        if index > 0:
            previous_month = ordered[index - 1]

    def build_entry(month_key):
        item = store["months"].get(month_key) or {}
        metrics = item.get("metrics") or {}
        extras = item.get("extras") or {}
        values = item.get("values") or {}
        return {
            "month": month_key,
            "date": item.get("date") or _month_end_date(month_key),
            "metrics": metrics,
            "extras": extras,
            "values": values,
            "importedAt": item.get("importedAt"),
            "sourceFile": item.get("sourceFile"),
        }

    selected = build_entry(selected_month)
    previous = build_entry(previous_month) if previous_month else None
    history = [build_entry(month_key) for month_key in sorted(store["months"].keys(), reverse=True)]
    return {
        "updatedAt": store.get("updatedAt"),
        "months": months,
        "selected": selected,
        "previous": previous,
        "metrics": list(COMPANY_MARKET_METRICS),
        "columns": columns,
        "history": history,
        "growth": {
            metric["key"]: _growth(
                (selected.get("metrics") or {}).get(metric["key"]),
                (previous.get("metrics") or {}).get(metric["key"]) if previous else None,
            )
            for metric in COMPANY_MARKET_METRICS
        },
    }
