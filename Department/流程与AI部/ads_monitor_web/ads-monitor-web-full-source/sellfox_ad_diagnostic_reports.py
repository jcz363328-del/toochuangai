#!/usr/bin/env python3
"""Refresh the mature SP report layer for the 21-US diagnostic pilot."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from sellfox_ads_bulk_report import (
    BulkReportError,
    CREATE_TASK_PATH,
    DownloadedReport,
    ReportTask,
    download_report_files_to_directory,
    excel_date_to_iso,
    parse_first_sheet_xlsx,
    wait_for_report_tasks,
)
from sellfox_ads_monitor import SellfoxAdsClient, load_api_credentials


ROOT = Path(__file__).resolve().parent
SHOP_ID = "475394"
SHOP_NAME = "21号站-李娜-US"
OUTPUT_DIR = ROOT / "data" / "ad_diagnostic_reports"
SEARCH_TERM_INDEX_NAME = "search-term-index.json"
REPORT_TYPES = (
    "adCampaignReport",
    "adGroupReport",
    "adProductReport",
    "adSpaceReport",
    "adTargeringReport",
    "adSearchTermReport",
    "adPurchasedItemReport",
    "amazonBusinessReport",
)
REQUIRED_HEADERS = frozenset({"店铺", "日期", "广告活动ID"})
SEARCH_TERM_DIMENSIONS = ("用户搜索词", "广告投放ID", "投放", "匹配类型")
SEARCH_TERM_METRICS = {
    "spend": "广告花费",
    "impressions": "广告曝光量",
    "clicks": "广告点击量",
    "orders": "广告订单量",
    "sales": "广告销售额",
    "units": "广告销量",
    "same_orders": "本广告产品订单量",
    "other_orders": "其他产品广告订单量",
    "same_sales": "本广告产品销售额",
    "other_sales": "其他产品广告销售额",
    "same_units": "本广告产品销量",
    "other_units": "其他产品广告销量",
}


class DiagnosticReportError(RuntimeError):
    """Raised when the refreshed report set is incomplete or untrusted."""


def report_window(as_of: date | None = None) -> tuple[date, date]:
    analysis_date = as_of or date.today()
    end = analysis_date - timedelta(days=2)
    return end - timedelta(days=13), end


def create_deep_report_tasks(
    client: Any,
    start: date,
    end: date,
    *,
    shop_id: str = SHOP_ID,
) -> list[ReportTask]:
    if start > end:
        raise DiagnosticReportError("报表开始日期不能晚于结束日期。")
    tasks: list[ReportTask] = []
    task_ids: set[str] = set()
    for report_type in REPORT_TYPES:
        body = {
            "shopIds": [shop_id],
            "adTypeCode": "sp",
            "reportTypeCode": report_type,
            "timeUnit": "daily",
            "reportStartDate": start.isoformat(),
            "reportEndDate": end.isoformat(),
        }
        data = client.post_data(CREATE_TASK_PATH, body, f"创建{report_type}任务")
        task_id = str(data.get("id", "")).strip() if isinstance(data, dict) else ""
        if not task_id or task_id in task_ids:
            raise DiagnosticReportError("广告报表任务 ID 缺失或重复。")
        task_ids.add(task_id)
        tasks.append(ReportTask(task_id, (shop_id,), report_type))
    return tasks


def validate_report_files(
    files: Sequence[DownloadedReport],
    *,
    shop_id: str = SHOP_ID,
    expected_shop_name: str = SHOP_NAME,
) -> dict[str, dict[str, int]]:
    expected = set(REPORT_TYPES)
    file_counts = {code: 0 for code in REPORT_TYPES}
    row_counts = {code: 0 for code in REPORT_TYPES}
    for downloaded in files:
        code = downloaded.report_type_code
        if code not in expected or set(downloaded.shop_ids) != {shop_id}:
            raise DiagnosticReportError("下载文件的报表类型或店铺范围异常。")
        if not downloaded.path.is_file() or downloaded.path.suffix.lower() != ".xlsx":
            raise DiagnosticReportError("广告报表文件缺失或格式异常。")
        headers, rows = parse_first_sheet_xlsx(downloaded.path)
        missing = REQUIRED_HEADERS.difference(headers)
        if missing:
            raise DiagnosticReportError(
                f"{code} 首表缺少必要字段：{','.join(sorted(missing))}。"
            )
        for row in rows:
            shop_name = str(row.get("店铺", "")).strip()
            if shop_name and shop_name != expected_shop_name:
                raise DiagnosticReportError(f"{code} 包含非试点店铺数据。")
        file_counts[code] += 1
        row_counts[code] += len(rows)
    missing_types = [code for code, count in file_counts.items() if not count]
    if missing_types:
        raise DiagnosticReportError(
            f"报表集合不完整：{','.join(missing_types)}。"
        )
    return {
        code: {"files": file_counts[code], "rows": row_counts[code]}
        for code in REPORT_TYPES
    }


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _ratio(numerator: Decimal, denominator: Decimal) -> float | None:
    return float(numerator / denominator) if denominator else None


def build_search_term_index(
    files: Sequence[DownloadedReport],
    destination: Path,
    *,
    start: date,
    end: date,
    shop_id: str = SHOP_ID,
    shop_name: str = SHOP_NAME,
) -> Path:
    if start > end:
        raise DiagnosticReportError("搜索词索引开始日期不能晚于结束日期。")
    reports = sorted(
        (item for item in files if item.report_type_code == "adSearchTermReport"),
        key=lambda item: item.path.name,
    )
    if not reports:
        raise DiagnosticReportError("搜索词报表缺失，无法生成分页索引。")
    grouped: dict[str, dict[tuple[str, ...], dict[str, Any]]] = {}
    observed_dates: set[date] = set()
    for report in reports:
        _, rows = parse_first_sheet_xlsx(report.path)
        pilot_rows = [
            row for row in rows
            if str(row.get("店铺", "")).strip() == shop_name
        ]
        if not pilot_rows:
            raise DiagnosticReportError(
                f"{report.path.name} 没有试点店铺的搜索词日期覆盖。"
            )
        file_dates: set[date] = set()
        for row_number, row in enumerate(pilot_rows, start=2):
            try:
                report_date_iso = excel_date_to_iso(row.get("日期"), "日期")
            except BulkReportError as exc:
                raise DiagnosticReportError(
                    f"{report.path.name} 第 {row_number} 行日期无效。"
                ) from exc
            if not report_date_iso:
                raise DiagnosticReportError(
                    f"{report.path.name} 第 {row_number} 行缺少日期。"
                )
            report_date = date.fromisoformat(report_date_iso)
            if not start <= report_date <= end:
                raise DiagnosticReportError(
                    f"{report.path.name} 第 {row_number} 行日期 {report_date_iso} "
                    f"超出请求窗口 {start.isoformat()}..{end.isoformat()}。"
                )
            file_dates.add(report_date)
            observed_dates.add(report_date)
            campaign_id = str(row.get("广告活动ID", "")).strip()
            if not campaign_id:
                continue
            identity = tuple(str(row.get(field, "")).strip() for field in SEARCH_TERM_DIMENSIONS)
            current = grouped.setdefault(campaign_id, {}).setdefault(
                identity,
                {
                    "identity": dict(zip(SEARCH_TERM_DIMENSIONS, identity)),
                    **{field: Decimal("0") for field in SEARCH_TERM_METRICS},
                    "dates": set(),
                },
            )
            current["dates"].add(report_date_iso)
            for field, header in SEARCH_TERM_METRICS.items():
                current[field] += _decimal(row.get(header))
        if not file_dates:
            raise DiagnosticReportError(
                f"{report.path.name} 的搜索词日期覆盖为空。"
            )
    if not observed_dates:
        raise DiagnosticReportError("搜索词报表日期覆盖为空，拒绝生成索引。")

    campaigns: dict[str, dict[str, Any]] = {}
    for campaign_id, values in grouped.items():
        entities = []
        for value in values.values():
            spend = value["spend"]
            clicks = value["clicks"]
            impressions = value["impressions"]
            orders = value["orders"]
            sales = value["sales"]
            entities.append(
                {
                    "identity": value["identity"],
                    **{
                        field: _number(value[field])
                        for field in SEARCH_TERM_METRICS
                    },
                    "acos": _ratio(spend, sales),
                    "roas": _ratio(sales, spend),
                    "cpc": _ratio(spend, clicks),
                    "ctr": _ratio(clicks, impressions),
                    "cvr": _ratio(orders, clicks),
                    "data_days": len(value["dates"]),
                    "latest_date": max(value["dates"], default=""),
                }
            )
        waste = sorted(
            (item for item in entities if not item["orders"] and item["spend"]),
            key=lambda item: (-float(item["spend"]), json.dumps(item["identity"], ensure_ascii=False, sort_keys=True)),
        )
        conversion = sorted(
            (item for item in entities if item["orders"]),
            key=lambda item: (-float(item["sales"]), -float(item["orders"]), -float(item["spend"])),
        )
        totals = {
            field: sum((_decimal(item[field]) for item in entities), Decimal("0"))
            for field in SEARCH_TERM_METRICS
        }
        summary = {
            field: _number(value)
            for field, value in totals.items()
        }
        summary.update(
            acos=_ratio(totals["spend"], totals["sales"]),
            roas=_ratio(totals["sales"], totals["spend"]),
            cpc=_ratio(totals["spend"], totals["clicks"]),
            ctr=_ratio(totals["clicks"], totals["impressions"]),
            cvr=_ratio(totals["orders"], totals["clicks"]),
            data_days=len({day for value in values.values() for day in value["dates"]}),
        )

        def summarize_subset(items: list[dict[str, Any]]) -> dict[str, Any]:
            subset = {
                field: sum((_decimal(item[field]) for item in items), Decimal("0"))
                for field in SEARCH_TERM_METRICS
            }
            max_clicks = max(items, key=lambda item: float(item["clicks"] or 0), default=None)
            result = {field: _number(value) for field, value in subset.items()}
            result.update(
                acos=_ratio(subset["spend"], subset["sales"]),
                roas=_ratio(subset["sales"], subset["spend"]),
                cpc=_ratio(subset["spend"], subset["clicks"]),
                ctr=_ratio(subset["clicks"], subset["impressions"]),
                cvr=_ratio(subset["orders"], subset["clicks"]),
                effective_sample_count=sum(1 for item in items if _decimal(item["clicks"]) >= 10),
                attention_count=sum(1 for item in items if _decimal(item["orders"]) >= 2 or _decimal(item["clicks"]) >= 10),
                sample_insufficient_count=sum(1 for item in items if _decimal(item["clicks"]) < 10),
                max_clicks_term=(
                    {"identity": max_clicks["identity"], "clicks": max_clicks["clicks"]}
                    if max_clicks else None
                ),
            )
            return result

        campaigns[campaign_id] = {
            "entity_count": len(entities),
            "waste_count": len(waste),
            "conversion_count": len(conversion),
            "summary": summary,
            "waste_summary": summarize_subset(waste),
            "conversion_summary": summarize_subset(conversion),
            "waste": waste,
            "conversion": conversion,
        }

    payload = {
        "meta": {
            "shop_id": shop_id,
            "shop_name": shop_name,
            "report_start_date": start.isoformat(),
            "report_end_date": end.isoformat(),
            "data_start_date": min(observed_dates).isoformat(),
            "data_end_date": max(observed_dates).isoformat(),
            "data_days": len(observed_dates),
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "campaigns": campaigns,
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return destination


def _remove_generated_directory(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _replace_directory(staging: Path, destination: Path) -> None:
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise DiagnosticReportError("报表输出路径必须是普通目录。")
    backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}"
    moved_old = False
    try:
        if destination.exists():
            destination.replace(backup)
            moved_old = True
        staging.replace(destination)
    except Exception as exc:
        if moved_old and backup.exists() and not destination.exists():
            backup.replace(destination)
        raise DiagnosticReportError("无法安全替换成熟报表目录。") from exc
    finally:
        if backup.exists() and destination.exists():
            _remove_generated_directory(backup)


def refresh_reports(
    client: Any,
    destination: str | Path = OUTPUT_DIR,
    *,
    shop_id: str = SHOP_ID,
    shop_name: str = SHOP_NAME,
    as_of: date | None = None,
    timeout_seconds: float = 900,
    poll_interval_seconds: float = 5,
) -> dict[str, Any]:
    analysis_date = as_of or date.today()
    start, end = report_window(analysis_date)
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = (target.parent / f".{target.name}.staging-{uuid.uuid4().hex}").resolve()
    staging.mkdir()
    try:
        tasks = create_deep_report_tasks(client, start, end, shop_id=shop_id)
        ready = wait_for_report_tasks(
            client,
            tasks,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        downloaded = download_report_files_to_directory(client, ready, staging)
        coverage = validate_report_files(
            downloaded,
            shop_id=shop_id,
            expected_shop_name=shop_name,
        )
        index_path = build_search_term_index(
            downloaded,
            staging / SEARCH_TERM_INDEX_NAME,
            start=start,
            end=end,
            shop_id=shop_id,
            shop_name=shop_name,
        )
        file_names = sorted([*(item.path.name for item in downloaded), index_path.name])
        _replace_directory(staging, target)
    finally:
        if staging.exists():
            _remove_generated_directory(staging)
    return {
        "status": "ok",
        "shop_id": shop_id,
        "shop_name": shop_name,
        "as_of": analysis_date.isoformat(),
        "report_start_date": start.isoformat(),
        "report_end_date": end.isoformat(),
        "report_types": list(REPORT_TYPES),
        "task_count": len(tasks),
        "file_count": len(downloaded),
        "files": file_names,
        "coverage": coverage,
        "output_directory": str(target),
        "refreshed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--as-of 必须是 YYYY-MM-DD。") from exc


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="刷新21号店成熟 SP 广告诊断报表（只读）")
    parser.add_argument("--as-of", type=_parse_date, help="分析日，默认今天")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logger = logging.getLogger("sellfox-ad-diagnostic-reports")
    client: SellfoxAdsClient | None = None
    try:
        client_id, client_secret = load_api_credentials()
        client = SellfoxAdsClient(client_id, client_secret, logger)
        client.get_token()
        summary = refresh_reports(client, as_of=args.as_of)
    except Exception as exc:
        summary = {
            "status": "error",
            "shop_id": SHOP_ID,
            "shop_name": SHOP_NAME,
            "error": "refresh_failed",
            "error_type": type(exc).__name__,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1
    finally:
        if client is not None:
            client.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
