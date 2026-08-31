#!/usr/bin/env python3
"""Refresh mature reports and publish only validated diagnostic snapshots."""

from __future__ import annotations

import argparse
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from sellfox_ad_diagnostic_reports import OUTPUT_DIR, refresh_reports
from sellfox_ad_diagnostic_server import (
    CAMPAIGN_ID_RE,
    DEFAULT_MONITOR_CONFIG_PATH,
    DEFAULT_MATURE_PAYLOAD,
    DEFAULT_SNAPSHOT_DIR,
    DEEP_REPORT_DIR,
    DiagnosticShop,
    DiagnosticService,
    SnapshotStore,
    compact_overview_snapshot,
    resolve_diagnostic_shops,
    shop_data_dir,
)
from sellfox_ad_diagnostic_snapshot import refresh_snapshot_batch
from sellfox_ads_monitor import SellfoxAdsClient, load_api_credentials, single_instance


ROOT = Path(__file__).resolve().parent
DEFAULT_STATUS_FILE = ROOT / "data" / "ad_diagnostic_refresh_status.json"
DEFAULT_ROTATION_FILE = ROOT / "data" / "ad_diagnostic_shop_rotation.json"
DEFAULT_OVERVIEW_CAMPAIGN_ID = "70540977760495"
ACTIONABLE_CODES = {
    "DECREASE_BID",
    "INCREASE_BID",
    "PAUSE_TARGET",
    "NEGATE_SEARCH_TERM",
    "REVIEW_TARGET",
}


def select_diagnostic_shops(
    shops: Mapping[str, DiagnosticShop],
    requested_shop_ids: Sequence[str],
) -> list[DiagnosticShop]:
    if len(requested_shop_ids) != len(set(requested_shop_ids)):
        raise ValueError("指定店铺包含重复 ID。")
    unknown = sorted(set(requested_shop_ids).difference(shops))
    if unknown:
        raise ValueError(f"指定店铺不在已授权清单：{','.join(unknown)}")
    selected_ids = list(requested_shop_ids) or list(shops)
    return [shops[shop_id] for shop_id in selected_ids]


def select_rotating_shops(
    shops: Sequence[DiagnosticShop],
    last_attempts: Mapping[str, str],
    limit: int,
) -> list[DiagnosticShop]:
    if limit < 1:
        raise ValueError("深度刷新店铺数必须大于 0。")
    return sorted(
        shops,
        key=lambda shop: (str(last_attempts.get(shop.shop_id) or ""), shop.shop_id),
    )[:limit]


def select_overview_campaign_id(catalog: Mapping[str, Any]) -> str:
    rows = catalog.get("campaigns")
    if not isinstance(rows, list):
        return ""

    def number(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def priority(row: Mapping[str, Any]) -> int:
        text = str(row.get("priority") or "").strip().casefold()
        action = str(row.get("action") or row.get("action_code") or "").upper()
        blockers = row.get("blockers")
        blocker_count = len(blockers) if isinstance(blockers, list) else 0
        if text in {"high", "p0", "p1", "高"}:
            return 400 + blocker_count
        if action in ACTIONABLE_CODES or number(row.get("actionable_count")) > 0:
            return 300 + blocker_count
        if text in {"medium", "p2", "中"}:
            return 200 + blocker_count
        return 100 + blocker_count if blocker_count else 0

    valid = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and CAMPAIGN_ID_RE.fullmatch(
            str(row.get("campaignId") or row.get("campaign_id") or "")
        )
    ]
    if not valid:
        return ""

    def key(row: Mapping[str, Any]) -> tuple[Any, ...]:
        campaign_id = str(row.get("campaignId") or row.get("campaign_id") or "")
        windows = row.get("performance_windows")
        window = windows.get("14d") if isinstance(windows, Mapping) else None
        mature = window if isinstance(window, Mapping) else row.get("mature_14d")
        spend = number(mature.get("spend")) if isinstance(mature, Mapping) else 0.0
        name = str(
            row.get("name")
            or row.get("campaignName")
            or row.get("campaign_name")
            or campaign_id
        )
        return (
            0 if campaign_id == DEFAULT_OVERVIEW_CAMPAIGN_ID else 1,
            -priority(row),
            -spend,
            name.casefold(),
            campaign_id,
        )

    selected = min(valid, key=key)
    return str(selected.get("campaignId") or selected.get("campaign_id") or "")


def _read_rotation(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    attempts = payload.get("last_attempts") if isinstance(payload, Mapping) else None
    return {
        str(shop_id): str(attempted_at)
        for shop_id, attempted_at in attempts.items()
        if str(shop_id) and str(attempted_at)
    } if isinstance(attempts, Mapping) else {}


def _write_rotation(path: Path, attempts: Mapping[str, str]) -> None:
    payload = {
        "schema_version": "sellfox-ad-diagnostic-shop-rotation-v1",
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "last_attempts": dict(attempts),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--as-of 必须是 YYYY-MM-DD。") from exc


def _write_status(path: Path, attempt: Mapping[str, Any], *, success: bool) -> None:
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        previous = {}
    payload = {
        "schema_version": "sellfox-ad-diagnostic-refresh-status-v1",
        "last_attempt": dict(attempt),
        "last_success": dict(attempt) if success else previous.get("last_success"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="每小时刷新诊断店铺只读广告数据")
    parser.add_argument("--config", type=Path, default=DEFAULT_MONITOR_CONFIG_PATH)
    parser.add_argument("--as-of", type=_parse_date)
    parser.add_argument("--mature-payload", type=Path, default=DEFAULT_MATURE_PAYLOAD)
    parser.add_argument("--report-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--status-file", type=Path, default=DEFAULT_STATUS_FILE)
    parser.add_argument("--rotation-file", type=Path, default=DEFAULT_ROTATION_FILE)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--deep-shop-batch-size", type=int, default=8)
    parser.add_argument("--catalog-workers", type=int, default=3)
    parser.add_argument("--overview-workers", type=int, default=4)
    parser.add_argument("--overview-ttl-minutes", type=int, default=60)
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    parser.add_argument("--campaign-id", action="append", default=[])
    parser.add_argument("--shop-id", action="append", default=[])
    parser.add_argument("--check-config", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (
        args.batch_size < 1
        or args.batch_size > 25
        or args.deep_shop_batch_size < 1
        or args.deep_shop_batch_size > 25
        or args.catalog_workers < 1
        or args.catalog_workers > 16
        or args.overview_workers < 1
        or args.overview_workers > 16
        or args.overview_ttl_minutes < 1
        or args.overview_ttl_minutes > 1440
        or args.delay_seconds < 0
        or len(args.campaign_id) > 25
        or any(not CAMPAIGN_ID_RE.fullmatch(item) for item in args.campaign_id)
        or (args.campaign_id and len(args.shop_id) != 1)
    ):
        raise SystemExit("刷新参数无效。")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        client_id, client_secret = load_api_credentials()
        with single_instance():
            client = SellfoxAdsClient(
                client_id,
                client_secret,
                logging.getLogger("sellfox-ad-diagnostic-refresh"),
            )
            try:
                client.get_token()
                runtime_shops = resolve_diagnostic_shops(
                    client,
                    args.config.resolve(),
                )
                selected_shops = select_diagnostic_shops(
                    runtime_shops,
                    args.shop_id,
                )
                if args.check_config:
                    print(json.dumps({
                        "status": "ok",
                        "read_only": True,
                        "shop_count": len(selected_shops),
                        "selected_shop_ids": [shop.shop_id for shop in selected_shops]
                        if args.shop_id else [],
                    }, ensure_ascii=False, indent=2))
                    return 0

                rotation_path = args.rotation_file.resolve()
                rotation_attempts = _read_rotation(rotation_path)
                deep_shops: list[DiagnosticShop] = []
                deep_shop_ids: set[str] = set()
                shop_results_by_id: dict[str, dict[str, Any]] = {}
                catalog_payloads: dict[str, dict[str, Any]] = {}

                def refresh_catalog(shop: DiagnosticShop) -> tuple[dict[str, Any], int]:
                    store = SnapshotStore(
                        shop_data_dir(args.snapshot_dir.resolve(), shop.shop_id),
                        shop.shop_id,
                    )
                    existing = store.read("campaigns")
                    if existing is not None:
                        age_seconds = (
                            datetime.now(timezone.utc) - existing.generated_at
                        ).total_seconds()
                        rows = existing.value.get("campaigns")
                        if 0 <= age_seconds < 45 * 60 and isinstance(rows, list):
                            return existing.value, len(rows)
                    service = DiagnosticService(
                        shop=shop,
                        mature_payload_path=args.mature_payload.resolve(),
                        snapshot_dir=None,
                        deep_report_dir=shop_data_dir(DEEP_REPORT_DIR, shop.shop_id),
                    )
                    catalog = None
                    for attempt in range(1, 6):
                        try:
                            catalog = service.campaigns(refresh=attempt == 1)
                            break
                        except Exception as exc:
                            if (
                                type(exc).__name__ != "UpstreamUnavailable"
                                or attempt == 5
                            ):
                                raise
                            logging.warning(
                                "店铺 %s 遇到上游限流，%s 秒后重试（%s/5）。",
                                shop.shop_id,
                                attempt * 3,
                                attempt,
                            )
                            time.sleep(attempt * 3)
                    if catalog is None:
                        raise RuntimeError("活动列表刷新未返回结果。")
                    rows = catalog.get("campaigns")
                    if not isinstance(rows, list):
                        raise ValueError("活动列表响应格式异常。")
                    store.write_hot("campaigns", catalog, datetime.now(timezone.utc))
                    return catalog, len(rows)

                with ThreadPoolExecutor(
                    max_workers=min(args.catalog_workers, len(selected_shops)),
                    thread_name_prefix="diagnostic-catalog",
                ) as executor:
                    futures = {
                        executor.submit(refresh_catalog, shop): shop
                        for shop in selected_shops
                    }
                    for future in as_completed(futures):
                        shop = futures[future]
                        shop_result: dict[str, Any] = {
                            "shop": {
                                "shop_id": shop.shop_id,
                                "shop_name": shop.shop_name,
                                "currency": shop.currency,
                            },
                            "refresh_tier": "catalog",
                        }
                        try:
                            catalog, campaign_count = future.result()
                            shop_result.update({
                                "status": "ok",
                                "catalog": {
                                    "status": "ok",
                                    "campaign_count": campaign_count,
                                },
                            })
                            catalog_payloads[shop.shop_id] = catalog
                        except Exception as exc:
                            logging.error(
                                "店铺 %s 活动清单刷新失败：%s。",
                                shop.shop_id,
                                type(exc).__name__,
                            )
                            shop_result.update({
                                "status": "error",
                                "catalog": {
                                    "status": "error",
                                    "error_type": type(exc).__name__,
                                },
                            })
                        shop_results_by_id[shop.shop_id] = shop_result

                overview_shops = [
                    shop
                    for shop in selected_shops
                    if shop.shop_id in catalog_payloads
                    and select_overview_campaign_id(catalog_payloads[shop.shop_id])
                ]
                overview_shop_ids = {shop.shop_id for shop in overview_shops}
                for shop in selected_shops:
                    result = shop_results_by_id[shop.shop_id]
                    if result.get("catalog", {}).get("status") == "ok" and shop.shop_id not in overview_shop_ids:
                        result["overview_snapshot"] = {
                            "status": "not_applicable",
                            "reason": "no_campaigns",
                        }

                deep_shops = (
                    overview_shops
                    if args.shop_id
                    else select_rotating_shops(
                        overview_shops,
                        rotation_attempts,
                        min(args.deep_shop_batch_size, len(overview_shops)),
                    )
                    if overview_shops
                    else []
                )
                deep_shop_ids = {shop.shop_id for shop in deep_shops}
                for shop in overview_shops:
                    shop_results_by_id[shop.shop_id]["refresh_tier"] = (
                        "catalog_overview_and_detail"
                        if shop.shop_id in deep_shop_ids
                        else "catalog_and_overview"
                    )

                def refresh_overview(shop: DiagnosticShop) -> dict[str, Any]:
                    catalog = catalog_payloads[shop.shop_id]
                    campaign_id = select_overview_campaign_id(catalog)
                    store = SnapshotStore(
                        shop_data_dir(args.snapshot_dir.resolve(), shop.shop_id),
                        shop.shop_id,
                    )
                    existing = store.read("overview", campaign_id)
                    if existing is not None:
                        age_seconds = (
                            datetime.now(timezone.utc) - existing.generated_at
                        ).total_seconds()
                        if 0 <= age_seconds < args.overview_ttl_minutes * 60:
                            return {
                                "status": "ok",
                                "campaign_id": campaign_id,
                                "source": "snapshot",
                                "age_seconds": round(age_seconds, 1),
                            }
                    service = DiagnosticService(
                        shop=shop,
                        mature_payload_path=args.mature_payload.resolve(),
                        snapshot_dir=None,
                        deep_report_dir=shop_data_dir(DEEP_REPORT_DIR, shop.shop_id),
                    )
                    detail = service.campaign_detail(
                        campaign_id,
                        refresh=True,
                        section="overview",
                    )
                    overview = compact_overview_snapshot(detail)
                    overview.setdefault("meta", {})["snapshot_compacted_from_full"] = False
                    generated_at = datetime.now(timezone.utc)
                    store.write_hot("overview", overview, generated_at, campaign_id)
                    return {
                        "status": "ok",
                        "campaign_id": campaign_id,
                        "source": "sellfox_api",
                        "generated_at": generated_at.isoformat(timespec="seconds"),
                    }

                if overview_shops:
                    with ThreadPoolExecutor(
                        max_workers=min(args.overview_workers, len(overview_shops)),
                        thread_name_prefix="diagnostic-overview",
                    ) as executor:
                        futures = {
                            executor.submit(refresh_overview, shop): shop
                            for shop in overview_shops
                        }
                        for future in as_completed(futures):
                            shop = futures[future]
                            shop_result = shop_results_by_id[shop.shop_id]
                            try:
                                shop_result["overview_snapshot"] = future.result()
                            except Exception as exc:
                                logging.error(
                                    "店铺 %s 首屏快照刷新失败：%s。",
                                    shop.shop_id,
                                    type(exc).__name__,
                                )
                                shop_result["status"] = "partial"
                                shop_result["overview_snapshot"] = {
                                    "status": "error",
                                    "error": "overview_refresh_failed",
                                    "error_type": type(exc).__name__,
                                }

                deep_attempted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                for shop in deep_shops:
                    shop_result = shop_results_by_id[shop.shop_id]
                    if shop_result.get("status") != "ok":
                        rotation_attempts[shop.shop_id] = deep_attempted_at
                        continue
                    try:
                        reports = refresh_reports(
                            client,
                            shop_data_dir(args.report_dir.resolve(), shop.shop_id),
                            shop_id=shop.shop_id,
                            shop_name=shop.shop_name,
                            as_of=args.as_of,
                        )
                        snapshots = refresh_snapshot_batch(
                            DiagnosticService(
                                shop=shop,
                                mature_payload_path=args.mature_payload.resolve(),
                                snapshot_dir=None,
                                deep_report_dir=shop_data_dir(
                                    DEEP_REPORT_DIR,
                                    shop.shop_id,
                                ),
                            ),
                            SnapshotStore(
                                shop_data_dir(
                                    args.snapshot_dir.resolve(),
                                    shop.shop_id,
                                ),
                                shop.shop_id,
                            ),
                            batch_size=args.batch_size,
                            delay_seconds=args.delay_seconds,
                            requested_campaign_ids=args.campaign_id,
                            catalog_payload=catalog_payloads[shop.shop_id],
                        )
                        shop_result.update({
                            "status": (
                                "ok" if snapshots["status"] == "ok" else "partial"
                            ),
                            "reports": reports,
                            "snapshots": snapshots,
                        })
                    except Exception as exc:
                        logging.error(
                            "店铺 %s 深度快照刷新失败：%s。",
                            shop.shop_id,
                            type(exc).__name__,
                        )
                        shop_result.update({
                            "status": "partial",
                            "detail": {
                                "status": "error",
                                "error": "shop_refresh_failed",
                                "error_type": type(exc).__name__,
                            },
                        })
                    rotation_attempts[shop.shop_id] = deep_attempted_at
                if not args.shop_id:
                    _write_rotation(rotation_path, rotation_attempts)
            finally:
                client.close()

        shop_results = [
            shop_results_by_id[shop.shop_id]
            for shop in selected_shops
        ]
        failures = [item for item in shop_results if item.get("status") != "ok"]
        successes = [item for item in shop_results if item.get("status") == "ok"]
        catalog_successes = [
            item
            for item in shop_results
            if item.get("catalog", {}).get("status") == "ok"
        ]
        overview_successes = [
            item
            for item in shop_results
            if item.get("overview_snapshot", {}).get("status") == "ok"
        ]
        overview_failures = [
            item
            for item in shop_results
            if item.get("overview_snapshot", {}).get("status") == "error"
        ]
        summary = {
            "status": "partial" if failures and successes else "error" if failures else "ok",
            "started_at": started_at,
            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "shop_count": len(shop_results),
            "catalog_success_count": len(catalog_successes),
            "catalog_failure_count": len(shop_results) - len(catalog_successes),
            "overview_eligible_count": len(overview_shops),
            "overview_success_count": len(overview_successes),
            "overview_failure_count": len(overview_failures),
            "deep_shop_count": len(deep_shops),
            "deep_shop_ids": [shop.shop_id for shop in deep_shops],
            "shops": shop_results,
        }
        success = len(catalog_successes) == len(shop_results)
        _write_status(args.status_file.resolve(), summary, success=success)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if success else 1
    except Exception as exc:
        summary = {
            "status": "error",
            "started_at": started_at,
            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "error": "refresh_failed",
            "error_type": type(exc).__name__,
        }
        _write_status(args.status_file.resolve(), summary, success=False)
        logging.error("诊断刷新失败：%s：%s", type(exc).__name__, exc)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
