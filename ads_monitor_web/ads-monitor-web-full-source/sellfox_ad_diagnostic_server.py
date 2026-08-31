#!/usr/bin/env python3
"""Local Sellfox SP diagnostics with hourly snapshots for authorized shops."""

from __future__ import annotations

import argparse
import copy
import json
import logging
import re
import secrets
import shutil
import sqlite3
import statistics
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlsplit
from zoneinfo import ZoneInfo

from sellfox_ads_monitor import (
    DEFAULT_CONFIG_PATH as DEFAULT_MONITOR_CONFIG_PATH,
    MonitorFailure,
    ONLINE_PRODUCT_PATH,
    SP_AD_PRODUCT_PATH,
    SP_CAMPAIGN_PATH,
    SP_HOUR_CAMPAIGN_PATH,
    SP_HOUR_TARGET_PATH,
    SP_KEYWORD_PATH,
    SP_PRODUCT_TARGET_PATH,
    SellfoxAdsClient,
    ShopConfig,
    discover_authorized_shops,
    fetch_cursor_items,
    fetch_page_items,
    listing_stage_for,
    load_api_credentials,
    load_monitor_config,
)
from sellfox_ads_realtime import MARKETPLACE_REPORT_TIMEZONES, RealtimeAdsClient
from sellfox_ads_bulk_report import (
    BulkReportError,
    excel_date_to_iso,
    parse_first_sheet_xlsx,
)
from sellfox_import import as_text
from sellfox_sp_control import SpControlError, SpControlService


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 4174
PILOT_SHOP_ID = "475394"
PILOT_SHOP_NAME = "21号站-李娜-US"
PILOT_MARKETPLACE_ID = "ATVPDKIKX0DER"
PILOT_CURRENCY = "USD"
PILOT_TIMEZONE = "America/Los_Angeles"
SECONDARY_SHOP_ID = "476221"
SECONDARY_SHOP_NAME = "23号店-侯梁-US"
BUSINESS_TIMEZONE = "Asia/Shanghai"
LIST_TTL_SECONDS = 180
DETAIL_TTL_SECONDS = 60
REFRESH_COOLDOWN_SECONDS = 30
SNAPSHOT_TTL_SECONDS = 60 * 60
REQUEST_DEADLINE_SECONDS = 55
MAX_HTTP_ATTEMPTS = 60
NEW_LISTING_DAYS = 90
PERFORMANCE_WINDOW_DAYS = 7
PERFORMANCE_MIN_CLICKS = 10
PERFORMANCE_CTR_THRESHOLD = Decimal("0.01")
PERFORMANCE_CVR_THRESHOLD = Decimal("0.10")
BUDGET_FULL_THRESHOLD = Decimal("0.98")
DEFAULT_MATURE_PAYLOAD = ROOT / "ads-monitor-web" / "public" / "data" / "ads-monitor.json"
DEFAULT_REALTIME_PAYLOAD = ROOT / "ads-monitor-web" / "public" / "data" / "ads-realtime.json"
DEFAULT_METRICS_DB = ROOT / "data" / "sellfox_ads.sqlite3"
DEFAULT_SNAPSHOT_DIR = ROOT / "data" / "ad_diagnostic_snapshots"
SNAPSHOT_SCHEMA_VERSION = "sellfox-ad-diagnostic-snapshot-v2"
SNAPSHOT_RUN_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
ALLOWED_ORIGINS = frozenset(
    {"http://127.0.0.1:4173", "http://localhost:4173"}
)
CAMPAIGN_ID_RE = re.compile(r"^[0-9]{1,32}$")
PROVISIONAL_COUNTER_ANOMALY = "PROVISIONAL_CLICKS_EXCEED_IMPRESSIONS"

SP_GROUP_PATH = "/api/cpc/manageData/spGroup.json"
SP_NEGATIVE_KEYWORD_PATH = "/api/cpc/manageData/spNeKeyword.json"
SP_NEGATIVE_TARGET_PATH = "/api/cpc/manageData/spNeTarget.json"
SP_HOUR_GROUP_PATH = "/api/cpc/hourData/spGroup.json"
SP_HOUR_AD_PRODUCT_PATH = "/api/cpc/hourData/spAdProduct.json"
SP_HOUR_PLACEMENT_PATH = "/api/cpc/hourData/spPlacement.json"
PRODUCT_ANALYSIS_PATH = "/api/productAnalyze/new/pageList.json"
PRODUCT_PROFIT_PATH = "/api/sale/profit/product/pageList.json"
FBA_RETURN_PATH = "/api/order/api/report/fbaReturn/pageList.json"
PRODUCT_SALES_PATH = "/api/productSale/page.json"
DEEP_REPORT_DIR = ROOT / "data" / "ad_diagnostic_reports"


@dataclass(frozen=True)
class DiagnosticShop:
    shop_id: str
    shop_name: str
    marketplace_id: str = PILOT_MARKETPLACE_ID
    currency: str = PILOT_CURRENCY
    timezone: str = PILOT_TIMEZONE


DIAGNOSTIC_SHOPS = {
    PILOT_SHOP_ID: DiagnosticShop(PILOT_SHOP_ID, PILOT_SHOP_NAME),
    SECONDARY_SHOP_ID: DiagnosticShop(SECONDARY_SHOP_ID, SECONDARY_SHOP_NAME),
}
DEFAULT_DIAGNOSTIC_SHOP = DIAGNOSTIC_SHOPS[PILOT_SHOP_ID]


def diagnostic_shop_from_config(shop: ShopConfig) -> DiagnosticShop:
    """Convert a validated monitor shop into the diagnostic shop shape."""
    report_timezone = MARKETPLACE_REPORT_TIMEZONES.get(shop.marketplace_id)
    if not report_timezone:
        raise MonitorFailure(
            f"店铺 {shop.shop_id} 的站点缺少广告报表时区配置。"
        )
    return DiagnosticShop(
        shop_id=shop.shop_id,
        shop_name=shop.shop_name,
        marketplace_id=shop.marketplace_id,
        currency=shop.currency,
        timezone=report_timezone,
    )


def resolve_diagnostic_shops(
    client: SellfoxAdsClient,
    config_path: Path = DEFAULT_MONITOR_CONFIG_PATH,
) -> dict[str, DiagnosticShop]:
    """Return every configured or dynamically discovered authorized shop."""
    config = load_monitor_config(config_path)
    shops = (
        discover_authorized_shops(client, config)
        if config.discover_shops
        else config.shops
    )
    if not shops:
        raise MonitorFailure("诊断刷新没有可用店铺。")
    return {
        shop.shop_id: diagnostic_shop_from_config(shop)
        for shop in shops
    }


def _campaign_lifecycle(rows: Sequence[Mapping[str, Any]], fallback: Any = "") -> str:
    fallback_text = as_text(fallback)
    if fallback_text in {"new", "established", "mixed", "unknown"}:
        return fallback_text
    stages = {as_text(row.get("listing_stage")) for row in rows}
    if not stages or "unknown" in stages:
        return "unknown"
    if stages == {"new"}:
        return "new"
    if "new" in stages:
        return "mixed"
    return "established"


def _campaign_performance_status(metrics: Mapping[str, Any], lifecycle: str) -> str:
    if lifecycle in {"new", "mixed"}:
        return "new_observation"
    if lifecycle != "established":
        return "unknown"
    if int(_decimal(metrics.get("data_days"))) < PERFORMANCE_WINDOW_DAYS:
        return "insufficient_sample"
    if _decimal(metrics.get("clicks")) < PERFORMANCE_MIN_CLICKS:
        return "insufficient_sample"
    ctr = metrics.get("ctr")
    cvr = metrics.get("cvr")
    if ctr is None or cvr is None:
        return "insufficient_sample"
    return (
        "normal"
        if _decimal(ctr) >= PERFORMANCE_CTR_THRESHOLD
        and _decimal(cvr) >= PERFORMANCE_CVR_THRESHOLD
        else "poor"
    )


def _campaign_ad_type(
    campaign: Mapping[str, Any],
    keywords: Sequence[Mapping[str, Any]],
    product_targets: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    if as_text(campaign.get("targetingType")).casefold() == "auto":
        return "auto", []
    match_types = sorted({
        as_text(row.get("matchType")).casefold()
        for row in keywords
        if as_text(row.get("matchType"))
    })
    if product_targets and not match_types:
        return "product_target", match_types
    if len(match_types) == 1 and not product_targets:
        return match_types[0], match_types
    if match_types or product_targets:
        return "manual_mixed", match_types
    return "manual", match_types


def shop_data_dir(root: Path, shop_id: str) -> Path:
    return root if shop_id == PILOT_SHOP_ID else root / shop_id
SEARCH_TERM_INDEX_NAME = "search-term-index.json"
DETAIL_SECTIONS = frozenset({"overview", "full"})
SEARCH_TERM_KINDS = frozenset({"waste", "conversion"})

READ_ENDPOINTS = frozenset(
    {
        SP_CAMPAIGN_PATH,
        SP_GROUP_PATH,
        SP_AD_PRODUCT_PATH,
        SP_KEYWORD_PATH,
        SP_PRODUCT_TARGET_PATH,
        SP_NEGATIVE_KEYWORD_PATH,
        SP_NEGATIVE_TARGET_PATH,
        ONLINE_PRODUCT_PATH,
        PRODUCT_ANALYSIS_PATH,
        PRODUCT_PROFIT_PATH,
        FBA_RETURN_PATH,
        PRODUCT_SALES_PATH,
        SP_HOUR_CAMPAIGN_PATH,
        SP_HOUR_GROUP_PATH,
        SP_HOUR_AD_PRODUCT_PATH,
        SP_HOUR_TARGET_PATH,
        SP_HOUR_PLACEMENT_PATH,
    }
)
ACTIONABLE_CODES = frozenset(
    {"DECREASE_BID", "INCREASE_BID", "INCREASE_BUDGET"}
)
CORE_SOURCE_IDS = frozenset(
    {"sp_campaign", "sp_ad_product", "online_product", "mature_14d"}
)
METRIC_FIELDS = (
    "costs",
    "clicks",
    "impressions",
    "orders",
    "sales",
    "units",
    "sameOrders",
    "sameSales",
    "sameUnits",
)
PRODUCT_CONTEXT_FIELDS = (
    "id",
    "shopId",
    "marketplaceId",
    "asin",
    "parentAsin",
    "sku",
    "msku",
    "fnsku",
    "title",
    "mainImage",
    "openDate",
    "onlineStatus",
    "switchFulfillmentTo",
    "standardPrice",
    "listingPrice",
    "salePrices",
    "quantity",
    "warehousing",
    "unsellable",
    "totalInventory",
    "saleNum",
    "day7SaleNum",
    "day14SaleNum",
    "day30SaleNum",
    "day7SalePrice",
    "day14SalePrice",
    "day30SalePrice",
    "profitPrice",
    "profitRate",
    "fbaFees",
    "referralFee",
    "rating",
    "reviewNum",
    "bsrRank",
    "inventoryManage",
    "lastSyncTime",
    "firstOrderDate",
    "firstSaleDate",
)
ANALYSIS_CONTEXT_FIELDS = (
    "shopIdList",
    "marketplaceIdList",
    "skuList",
    "mskuList",
    "asinList",
    "parentAsinList",
    "productIdList",
    "salePriceThis",
    "orderNumThis",
    "productTotalNumThis",
    "refundRateThis",
    "returnSaleRateThis",
    "profitPriceThis",
    "profitRateThis",
    "adCostThis",
    "adTotalSalesThis",
    "adOrderNumThis",
    "adImpressionsThis",
    "adClicksThis",
    "acosThis",
    "acoasThis",
    "asoasThis",
    "adOrderRateThis",
    "adCostSp",
    "adTotalSalesSp",
    "adOrderNumSp",
    "adImpressionsSp",
    "adClicksSp",
    "acosSp",
    "availableDays",
    "totalInventory",
)
FINANCE_CONTEXT_FIELDS = (
    "shopIdList",
    "skuList",
    "mskuList",
    "asinList",
    "profit",
    "profitRate",
    "profitRateNet",
    "salePrice",
    "saleNum",
    "orderNum",
    "refundPercent",
    "refundPrice",
    "adTotalOrderNum",
    "adTotalSale",
    "adOrderNum",
    "adTotalSales",
    "adTotalCost",
    "adTotalCostPercent",
    "adSpOrderNum",
    "adSpSalePrice",
    "adSpCost",
    "adSpCostPercent",
    "adOrderNumSp",
    "adTotalSalesSp",
    "adTotalCostSp",
    "adSbOrderNum",
    "adSbSalePrice",
    "adSbCost",
    "adSbCostPercent",
    "adOrderNumSb",
    "adTotalSalesSb",
    "adTotalCostSb",
    "adSbvOrderNum",
    "adSbvSalePrice",
    "adSbvCost",
    "adSbvCostPercent",
    "adOrderNumSbv",
    "adTotalSalesSbv",
    "adTotalCostSbv",
    "adSbsOrderNum",
    "adSbsSalePrice",
    "adSbsCost",
    "adSbsCostPercent",
    "adSdOrderNum",
    "adSdSalePrice",
    "adSdCost",
    "adSdCostPercent",
    "adOrderNumSd",
    "adTotalSalesSd",
    "adTotalCostSd",
    "adCostRate",
    "purchasePrice",
    "headTripPrice",
    "salesCommission",
    "fbaDeliveryFee",
    "fbaStorageFee",
    "referralFee",
)
DEEP_REPORT_TYPES = {
    "campaigns": ("adCampaignReport", ("广告活动",)),
    "groups": ("adGroupReport", ("广告组ID", "广告组")),
    "products": ("adProductReport", ("广告产品ID", "asin", "sku")),
    "placements": ("adSpaceReport", ("广告位",)),
    "targets": ("adTargeringReport", ("广告投放ID", "投放", "匹配类型")),
    "search_terms": ("adSearchTermReport", ("用户搜索词", "广告投放ID", "投放", "匹配类型")),
    "purchased_items": ("adPurchasedItemReport", ("其他ASIN", "ASIN", "SKU", "投放")),
    "business_placements": ("amazonBusinessReport", ("广告位",)),
}


class DiagnosticError(RuntimeError):
    status_code = 500
    error_code = "INTERNAL_ERROR"
    public_message = "诊断服务暂时不可用。"


class BadRequest(DiagnosticError):
    status_code = 400
    error_code = "BAD_REQUEST"
    public_message = "请求参数无效。"


class Forbidden(DiagnosticError):
    status_code = 403
    error_code = "FORBIDDEN"
    public_message = "只允许访问已启用的诊断店铺。"


class NotFound(DiagnosticError):
    status_code = 404
    error_code = "NOT_FOUND"
    public_message = "该广告活动不属于固定试点店铺或不存在。"


class RefreshLimited(DiagnosticError):
    status_code = 429
    error_code = "REFRESH_COOLDOWN"
    public_message = "刷新过于频繁，请稍后再试。"


class UpstreamUnavailable(DiagnosticError):
    status_code = 502
    error_code = "SELLFOX_UNAVAILABLE"
    public_message = "赛狐核心只读接口暂时不可用。"


class ReportScopeError(ValueError):
    pass


class ReportDateWindowError(ValueError):
    pass


@dataclass
class CacheEntry:
    value: dict[str, Any]
    created_at: float
    expires_at: float


@dataclass(frozen=True)
class SnapshotEntry:
    value: dict[str, Any]
    generated_at: datetime
    source: str


def snapshot_refresh_errors(value: Mapping[str, Any]) -> list[str]:
    """Return report sections that are unsafe to publish as a fresh snapshot."""
    performance = value.get("performance", {})
    if not isinstance(performance, Mapping):
        return sorted(DEEP_REPORT_TYPES)
    mature = performance.get("mature_14d", {})
    deep = mature.get("deep_reports", {}) if isinstance(mature, Mapping) else {}
    if not isinstance(deep, Mapping):
        return sorted(DEEP_REPORT_TYPES)
    return sorted(
        key
        for key in DEEP_REPORT_TYPES
        if not isinstance(deep.get(key), Mapping)
        or as_text(deep[key].get("status")) != "available"
    )


class SnapshotStore:
    """Versioned, atomic diagnostic snapshots with small per-campaign files."""

    def __init__(self, root: Path, shop_id: str = PILOT_SHOP_ID) -> None:
        self.root = root.resolve()
        self.shop_id = shop_id
        self.runs = self.root / "runs"
        self.hot = self.root / "hot"
        self.pointer = self.root / "current.json"
        self._write_lock = threading.Lock()

    @staticmethod
    def _relative_path(kind: str, campaign_id: str = "") -> Path:
        if kind == "campaigns":
            return Path("campaigns.json")
        if kind not in DETAIL_SECTIONS or not CAMPAIGN_ID_RE.fullmatch(campaign_id):
            raise ValueError("invalid snapshot key")
        return Path("details") / kind / f"{campaign_id}.json"

    @staticmethod
    def _key(kind: str, campaign_id: str = "") -> str:
        return "campaigns" if kind == "campaigns" else f"detail:{kind}:{campaign_id}"

    @staticmethod
    def _timestamp(value: datetime) -> str:
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _write_json(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(_json_safe(value), ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _envelope(
        self,
        kind: str,
        campaign_id: str,
        value: Mapping[str, Any],
        generated_at: datetime,
    ) -> dict[str, Any]:
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "key": self._key(kind, campaign_id),
            "shop_id": self.shop_id,
            "campaign_id": campaign_id,
            "generated_at": self._timestamp(generated_at),
            "payload": dict(value),
        }

    def _current_run(self) -> Path | None:
        pointer = self._read_json(self.pointer)
        run_id = as_text(pointer.get("run_id")) if pointer else ""
        if not SNAPSHOT_RUN_RE.fullmatch(run_id):
            return None
        candidate = (self.runs / run_id).resolve()
        return candidate if candidate.parent == self.runs.resolve() else None

    def _read_envelope(
        self,
        path: Path,
        accepted_keys: set[str],
        campaign_id: str,
    ) -> SnapshotEntry | None:
        envelope = self._read_json(path)
        if not envelope or envelope.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
            return None
        if as_text(envelope.get("shop_id")) != self.shop_id:
            return None
        if as_text(envelope.get("key")) not in accepted_keys:
            return None
        if campaign_id and as_text(envelope.get("campaign_id")) != campaign_id:
            return None
        generated_at = self._parse_timestamp(envelope.get("generated_at"))
        payload = envelope.get("payload")
        if generated_at is None or not isinstance(payload, dict):
            return None
        return SnapshotEntry(copy.deepcopy(payload), generated_at, str(path))

    def read(self, kind: str, campaign_id: str = "") -> SnapshotEntry | None:
        relative = self._relative_path(kind, campaign_id)
        accepted = {self._key(kind, campaign_id)}
        relatives = [relative]
        if kind == "overview":
            relatives.append(self._relative_path("full", campaign_id))
            accepted.add(self._key("full", campaign_id))
        roots = [self.hot]
        current = self._current_run()
        if current:
            roots.append(current)
        entries = [
            entry
            for root in roots
            for item in relatives
            if (entry := self._read_envelope(root / item, accepted, campaign_id))
        ]
        return max(entries, key=lambda item: item.generated_at) if entries else None

    def write_hot(
        self,
        kind: str,
        value: Mapping[str, Any],
        generated_at: datetime,
        campaign_id: str = "",
    ) -> None:
        relative = self._relative_path(kind, campaign_id)
        with self._write_lock:
            self._write_json(
                self.hot / relative,
                self._envelope(kind, campaign_id, value, generated_at),
            )

    def publish(
        self,
        campaigns: Mapping[str, Any],
        details: Mapping[str, Mapping[str, Any]],
        generated_at: datetime,
        *,
        retention: int = 4,
    ) -> dict[str, Any]:
        rows = campaigns.get("campaigns")
        if not isinstance(rows, list):
            raise ValueError("campaign snapshot is missing rows")
        campaign_ids = [as_text(row.get("campaignId") or row.get("campaign_id")) for row in rows]
        if any(not CAMPAIGN_ID_RE.fullmatch(item) for item in campaign_ids):
            raise ValueError("campaign snapshot contains an invalid id")
        if len(campaign_ids) != len(set(campaign_ids)) or set(details) != set(campaign_ids):
            raise ValueError("detail snapshot coverage is incomplete")
        utc = generated_at if generated_at.tzinfo else generated_at.replace(tzinfo=timezone.utc)
        run_id = f"{utc.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        run_root = self.runs / run_id
        with self._write_lock:
            if run_root.exists():
                raise ValueError("snapshot run already exists")
            self._write_json(
                run_root / self._relative_path("campaigns"),
                self._envelope("campaigns", "", campaigns, utc),
            )
            for campaign_id, detail in details.items():
                self._write_json(
                    run_root / self._relative_path("full", campaign_id),
                    self._envelope("full", campaign_id, detail, utc),
                )
                overview = compact_overview_snapshot(detail)
                self._write_json(
                    run_root / self._relative_path("overview", campaign_id),
                    self._envelope("overview", campaign_id, overview, utc),
                )
            manifest = {
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "run_id": run_id,
                "shop_id": self.shop_id,
                "generated_at": self._timestamp(utc),
                "campaign_count": len(campaign_ids),
                "complete": True,
            }
            self._write_json(run_root / "manifest.json", manifest)
            self._write_json(self.pointer, manifest)
            self._prune(max(1, retention), keep=run_id)
        return manifest

    def _prune(self, retention: int, *, keep: str) -> None:
        try:
            candidates = sorted(
                (
                    item
                    for item in self.runs.iterdir()
                    if item.is_dir() and SNAPSHOT_RUN_RE.fullmatch(item.name)
                ),
                key=lambda item: item.name,
                reverse=True,
            )
        except OSError:
            return
        retained = {item.name for item in candidates[:retention]}
        retained.add(keep)
        runs_root = self.runs.resolve()
        for item in candidates:
            resolved = item.resolve()
            if item.name not in retained and resolved.parent == runs_root:
                shutil.rmtree(resolved, ignore_errors=True)


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value)) if value not in (None, "") else Decimal("0")
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return result if result.is_finite() else Decimal("0")


def _number(value: Decimal | int | float | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _ratio(numerator: Decimal, denominator: Decimal) -> float | None:
    return _number(numerator / denominator) if denominator else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _number(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def compact_overview_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["structure"] = {
        "ad_products": list(result.get("structure", {}).get("ad_products", []))
    }
    today = result.get("performance", {}).get("today")
    if isinstance(today, dict):
        today.pop("ad_groups", None)
    mature = result.get("performance", {}).get("mature_14d")
    if isinstance(mature, dict) and isinstance(mature.get("deep_reports"), dict):
        reports = mature["deep_reports"]
        mature["deep_reports"] = {
            key: reports[key]
            for key in ("placements", "search_terms")
            if key in reports
        }
    meta = result.setdefault("meta", {})
    meta["kind"] = "campaign_detail_overview"
    meta["snapshot_compacted_from_full"] = True
    return result


def _pick(source: Mapping[str, Any] | None, fields: Sequence[str]) -> dict[str, Any]:
    if not source:
        return {}
    return {field: _json_safe(source.get(field)) for field in fields if field in source}


def _contains(value: Any, expected: str, *, upper: bool = False) -> bool:
    expected_value = expected.upper() if upper else expected
    values = value if isinstance(value, list) else [value]
    for item in values:
        candidates = item.values() if isinstance(item, Mapping) else (item,)
        for candidate in candidates:
            text = as_text(candidate)
            if (text.upper() if upper else text) == expected_value:
                return True
    return False


def _report_decimal(value: Any) -> Decimal:
    text = as_text(value).strip().replace(",", "")
    if text.casefold() in {"", "-", "--", "n/a", "null"}:
        return Decimal("0")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    percent = text.endswith("%")
    if percent:
        text = text[:-1]
    result = _decimal(text)
    if negative:
        result = -result
    return result / 100 if percent else result


def _aggregate_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    totals = {field: sum((_decimal(row.get(field)) for row in rows), Decimal("0")) for field in METRIC_FIELDS}
    spend = totals["costs"]
    clicks = totals["clicks"]
    impressions = totals["impressions"]
    orders = totals["orders"]
    sales = totals["sales"]
    latest_hour = max((int(_decimal(row.get("hour"))) for row in rows), default=None)
    return {
        "spend": _number(spend),
        "clicks": _number(clicks),
        "impressions": _number(impressions),
        "orders": _number(orders),
        "sales": _number(sales),
        "units": _number(totals["units"]),
        "same_orders": _number(totals["sameOrders"]),
        "same_sales": _number(totals["sameSales"]),
        "same_units": _number(totals["sameUnits"]),
        "acos": _ratio(spend, sales),
        "roas": _ratio(sales, spend),
        "cpc": _ratio(spend, clicks),
        "ctr": _ratio(clicks, impressions),
        "cvr": _ratio(orders, clicks),
        "latest_hour": latest_hour,
        "rows_count": len(rows),
    }


def _source(
    source_id: str,
    endpoint: str,
    fetched_at: str,
    *,
    effective_date: str = "",
    row_count: int = 0,
    pages: int = 0,
    status: str = "ok",
    error: str = "",
    cache_status: str = "miss",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "endpoint": endpoint,
        "fetched_at": fetched_at,
        "effective_date": effective_date,
        "row_count": row_count,
        "pages": pages,
        "status": status,
        "error": error,
        "cache_status": cache_status,
        **_json_safe(extra),
    }


def _safe_campaign_action(
    campaign: Mapping[str, Any],
    recommendation: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if recommendation is None:
        return None
    action = dict(recommendation)
    targeting_type = as_text(campaign.get("targetingType")).casefold()
    action_code = as_text(action.get("action_code"))
    if targeting_type == "auto" and action_code in {"DECREASE_BID", "INCREASE_BID"}:
        action.update(
            original_action_code=action_code,
            action_code="REVIEW_TARGET",
            action_label="优质搜索词转手动广告",
            can_adjust_keyword_cpc=False,
            recommended_match_types=["exact", "broad"],
            reason=(
                "自动广告中的用户搜索词不能直接调整关键词CPC；"
                "请人工复核后新建手动精准和广泛广告。"
            ),
        )
    return action


class DiagnosticService:
    def __init__(
        self,
        *,
        shop: DiagnosticShop = DEFAULT_DIAGNOSTIC_SHOP,
        client_factory: Callable[[], Any] | None = None,
        mature_payload_path: Path = DEFAULT_MATURE_PAYLOAD,
        realtime_payload_path: Path = DEFAULT_REALTIME_PAYLOAD,
        metrics_db_path: Path = DEFAULT_METRICS_DB,
        deep_report_dir: Path | None = None,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        list_ttl: int = LIST_TTL_SECONDS,
        detail_ttl: int = DETAIL_TTL_SECONDS,
        refresh_cooldown: int = REFRESH_COOLDOWN_SECONDS,
        snapshot_dir: Path | None = None,
        snapshot_ttl: int = SNAPSHOT_TTL_SECONDS,
        control_audit_dir: Path | None = None,
    ) -> None:
        self.shop = shop
        self.client_factory = client_factory or self._default_client
        self.mature_payload_path = mature_payload_path
        self.realtime_payload_path = realtime_payload_path
        self.metrics_db_path = metrics_db_path
        self.deep_report_dir = deep_report_dir
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.list_ttl = list_ttl
        self.detail_ttl = detail_ttl
        self.refresh_cooldown = refresh_cooldown
        self.snapshot_ttl = snapshot_ttl
        self.snapshot_store = SnapshotStore(snapshot_dir, shop.shop_id) if snapshot_dir else None
        self.control_audit_dir = (control_audit_dir or ROOT / "outputs" / "sp_control" / "audit").resolve()
        self._cache: dict[str, CacheEntry] = {}
        self._forced_at: dict[str, float] = {}
        self._attempted_at: dict[str, float] = {}
        self._cache_lock = threading.RLock()
        self._fetch_locks: dict[str, threading.Lock] = {}
        self._refreshing: set[str] = set()
        self._mature_lock = threading.Lock()
        self._mature_mtime_ns = -1
        self._mature_payload: dict[str, Any] | None = None
        self._report_cache: dict[Path, tuple[int, list[str], list[dict[str, str]]]] = {}
        self._search_term_index_cache: tuple[int, dict[str, Any]] | None = None

    def _realtime_campaign_context(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.realtime_payload_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            return {}
        expected_date = self._now().astimezone(ZoneInfo(self.shop.timezone)).date().isoformat()
        output: dict[str, dict[str, Any]] = {}
        for row in payload.get("campaigns", []):
            if as_text(row.get("shop_id")) != self.shop.shop_id:
                continue
            campaign_id = as_text(row.get("campaign_id"))
            freshness = row.get("freshness") if isinstance(row.get("freshness"), Mapping) else {}
            today = row.get("today") if isinstance(row.get("today"), Mapping) else {}
            status = as_text(freshness.get("status")) or "unknown"
            usable = status == "fresh" and as_text(today.get("report_date")) == expected_date
            output[campaign_id] = {
                "status": "fresh" if usable else status,
                "today": dict(today) if usable else {},
            }
        return output

    def _campaign_windows(self) -> tuple[dict[str, Any], dict[str, Any]]:
        fetched_at = self._timestamp()
        endpoint = str(self.metrics_db_path)
        try:
            resolved = self.metrics_db_path.resolve()
            connection = sqlite3.connect(
                f"file:{resolved.as_posix()}?mode=ro",
                uri=True,
                timeout=10,
            )
            _, _, mature_end = self._mature_window()
            row = connection.execute(
                """
                SELECT MAX(report_date)
                FROM hourly_fact_history
                WHERE aggregation_type = 'campaign'
                  AND shop_id = ?
                  AND report_date <= ?
                """,
                (self.shop.shop_id, mature_end.isoformat()),
            ).fetchone()
            latest = date.fromisoformat(as_text(row[0])) if row and row[0] else mature_end
            start = latest - timedelta(days=29)
            rows = connection.execute(
                """
                WITH ranked AS (
                    SELECT
                        campaign_id,
                        report_date,
                        report_hour,
                        spend,
                        clicks,
                        impressions,
                        orders,
                        sales,
                        ROW_NUMBER() OVER (
                            PARTITION BY campaign_id, report_date, report_hour
                            ORDER BY ingested_at DESC, run_id DESC
                        ) AS row_rank
                    FROM hourly_fact_history
                    WHERE aggregation_type = 'campaign'
                      AND shop_id = ?
                      AND report_date BETWEEN ? AND ?
                )
                SELECT campaign_id, report_date, spend, clicks, impressions, orders, sales
                FROM ranked
                WHERE row_rank = 1
                """,
                (self.shop.shop_id, start.isoformat(), latest.isoformat()),
            ).fetchall()
            connection.close()
        except (OSError, sqlite3.Error, ValueError) as error:
            return self._campaign_windows_from_report(
                fetched_at=fetched_at,
                primary_endpoint=endpoint,
                primary_error=type(error).__name__.upper(),
            )

        daily: dict[str, dict[date, list[Decimal]]] = {}
        for campaign_id, report_date, spend, clicks, impressions, orders, sales in rows:
            key = as_text(campaign_id)
            day = date.fromisoformat(as_text(report_date))
            values = daily.setdefault(key, {}).setdefault(day, [Decimal("0")] * 5)
            for index, value in enumerate((spend, clicks, impressions, orders, sales)):
                values[index] += _decimal(value)
        windows = self._build_campaign_windows(daily, latest, (7, 14, 30))
        return windows, _source(
            "campaign_windows",
            endpoint,
            fetched_at,
            effective_date=latest.isoformat(),
            row_count=len(rows),
            pages=1,
            cache_status="local",
        )

    @staticmethod
    def _build_campaign_windows(
        daily: Mapping[str, Mapping[date, Sequence[Decimal]]],
        latest: date,
        supported_days: Sequence[int],
    ) -> dict[str, Any]:
        windows: dict[str, Any] = {}
        for campaign_id, days in daily.items():
            campaign_windows: dict[str, Any] = {}
            for window_days in supported_days:
                window_start = latest - timedelta(days=window_days - 1)
                selected = sorted(
                    ((day, values) for day, values in days.items() if day >= window_start),
                    key=lambda item: item[0],
                )
                spend = sum((values[0] for _, values in selected), Decimal("0"))
                clicks = sum((values[1] for _, values in selected), Decimal("0"))
                impressions = sum((values[2] for _, values in selected), Decimal("0"))
                orders = sum((values[3] for _, values in selected), Decimal("0"))
                sales = sum((values[4] for _, values in selected), Decimal("0"))
                campaign_windows[f"{window_days}d"] = {
                    "spend": _number(spend),
                    "clicks": _number(clicks),
                    "impressions": _number(impressions),
                    "orders": _number(orders),
                    "sales": _number(sales),
                    "ctr": _ratio(clicks, impressions),
                    "cpc": _ratio(spend, clicks),
                    "cvr": _ratio(orders, clicks),
                    "acos": _ratio(spend, sales),
                    "roas": _ratio(sales, spend),
                    "data_days": len(selected),
                    "window_days": window_days,
                    "start_date": window_start.isoformat(),
                    "latest_date": latest.isoformat(),
                    "daily_trend": [
                        {
                            "date": day.isoformat(),
                            "spend": _number(values[0]),
                            "clicks": _number(values[1]),
                            "impressions": _number(values[2]),
                            "orders": _number(values[3]),
                            "sales": _number(values[4]),
                        }
                        for day, values in selected
                    ],
                }
            windows[campaign_id] = campaign_windows
        return windows

    def _campaign_windows_from_report(
        self,
        *,
        fetched_at: str,
        primary_endpoint: str,
        primary_error: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        report_dir = self.deep_report_dir or DEEP_REPORT_DIR
        candidates = sorted(
            report_dir.glob("adCampaignReport-*.xlsx"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        ) if report_dir.is_dir() else []
        if not candidates:
            return {}, _source(
                "campaign_windows",
                primary_endpoint,
                fetched_at,
                status="error",
                error=primary_error,
            )

        path = candidates[0]
        try:
            headers, rows = self._read_report(path)
            required_headers = {"店铺", "日期", "广告活动ID"}
            if not required_headers.issubset(headers):
                raise ReportScopeError("required scope headers missing")
            shops = {as_text(row.get("店铺")) for row in rows}
            if shops != {self.shop.shop_name}:
                raise ReportScopeError("report contains foreign or missing shop")
            as_of, expected_start, expected_end = self._mature_window()
            expected_dates = {
                (expected_start + timedelta(days=offset)).isoformat()
                for offset in range(14)
            }
            report_dates = [excel_date_to_iso(row.get("日期"), "日期") for row in rows]
            if set(report_dates) != expected_dates:
                raise ReportDateWindowError("report date window is not current D-2 14d")

            daily: dict[str, dict[date, list[Decimal]]] = {}
            metric_headers = (
                "广告花费",
                "广告点击量",
                "广告曝光量",
                "广告订单量",
                "广告销售额",
            )
            for row, report_date in zip(rows, report_dates):
                campaign_id = as_text(row.get("广告活动ID"))
                if not campaign_id or not report_date:
                    continue
                day = date.fromisoformat(report_date)
                values = daily.setdefault(campaign_id, {}).setdefault(
                    day, [Decimal("0")] * 5
                )
                for index, header in enumerate(metric_headers):
                    values[index] += _report_decimal(row.get(header))
            windows = self._build_campaign_windows(daily, expected_end, (7, 14))
            stat = path.stat()
            modified = datetime.fromtimestamp(
                stat.st_mtime, timezone.utc
            ).isoformat(timespec="seconds")
            return windows, _source(
                "campaign_windows",
                str(path),
                modified,
                effective_date=expected_end.isoformat(),
                row_count=len(rows),
                pages=0,
                status="partial",
                error="30D_WINDOW_UNAVAILABLE",
                cache_status="file_cache",
                supported_windows=["7d", "14d"],
                fallback_from=primary_endpoint,
                fallback_error=primary_error,
                expected_start_date=expected_start.isoformat(),
                expected_end_date=expected_end.isoformat(),
                business_as_of=as_of.isoformat(),
                scope_verified=True,
            )
        except (OSError, BulkReportError, ValueError) as error:
            if isinstance(error, ReportScopeError):
                fallback_error = "REPORT_SCOPE_INVALID"
            elif isinstance(error, ReportDateWindowError):
                fallback_error = "REPORT_DATE_WINDOW_INVALID"
            else:
                fallback_error = "REPORT_FILE_INVALID"
            return {}, _source(
                "campaign_windows",
                primary_endpoint,
                fetched_at,
                status="error",
                error=primary_error,
                fallback_endpoint=str(path),
                fallback_error=fallback_error,
            )

    def _adjustment_reviews(self, campaign_id: str) -> list[dict[str, Any]]:
        audits: list[dict[str, Any]] = []
        try:
            paths = sorted(
                self.control_audit_dir.glob("execution-*.json"),
                key=lambda path: path.stat().st_mtime_ns,
                reverse=True,
            )
        except OSError:
            return []
        for path in paths:
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if (
                as_text(item.get("status")) == "succeeded"
                and as_text(item.get("shop_id")) == self.shop.shop_id
                and as_text(item.get("campaign_id")) == campaign_id
            ):
                audits.append(item)
            if len(audits) >= 20:
                break
        if not audits:
            return []

        dated: list[tuple[dict[str, Any], date]] = []
        for audit in audits:
            try:
                changed = datetime.fromisoformat(as_text(audit.get("finished_at")))
                if changed.tzinfo is None:
                    changed = changed.replace(tzinfo=timezone.utc)
                changed_date = changed.astimezone(ZoneInfo(self.shop.timezone)).date()
            except (ValueError, KeyError):
                continue
            dated.append((audit, changed_date))
        if not dated:
            return []

        first = min(day - timedelta(days=7) for _, day in dated)
        last = max(day + timedelta(days=7) for _, day in dated)
        _, _, mature_end = self._mature_window()
        last = min(last, mature_end)
        try:
            resolved = self.metrics_db_path.resolve()
            connection = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True, timeout=10)
            rows = connection.execute(
                """
                WITH ranked AS (
                    SELECT report_date, report_hour, spend, clicks, impressions, orders, sales,
                           ROW_NUMBER() OVER (
                               PARTITION BY report_date, report_hour
                               ORDER BY ingested_at DESC, run_id DESC
                           ) AS row_rank
                    FROM hourly_fact_history
                    WHERE aggregation_type = 'campaign'
                      AND shop_id = ?
                      AND campaign_id = ?
                      AND report_date BETWEEN ? AND ?
                )
                SELECT report_date, spend, clicks, impressions, orders, sales
                FROM ranked WHERE row_rank = 1
                """,
                (self.shop.shop_id, campaign_id, first.isoformat(), last.isoformat()),
            ).fetchall()
            connection.close()
        except (OSError, sqlite3.Error):
            return []

        daily: dict[date, list[Decimal]] = {}
        for report_date, spend, clicks, impressions, orders, sales in rows:
            day = date.fromisoformat(as_text(report_date))
            values = daily.setdefault(day, [Decimal("0")] * 5)
            for index, value in enumerate((spend, clicks, impressions, orders, sales)):
                values[index] += _decimal(value)

        def summarize(start: date, end: date, budget: Any) -> dict[str, Any]:
            selected = sorted(
                ((day, values) for day, values in daily.items() if start <= day <= min(end, mature_end)),
                key=lambda item: item[0],
            )
            spend = sum((values[0] for _, values in selected), Decimal("0"))
            clicks = sum((values[1] for _, values in selected), Decimal("0"))
            impressions = sum((values[2] for _, values in selected), Decimal("0"))
            orders = sum((values[3] for _, values in selected), Decimal("0"))
            sales = sum((values[4] for _, values in selected), Decimal("0"))
            budget_value = _decimal(budget)
            return {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "mature_days": len(selected),
                "required_days": 7,
                "spend": _number(spend),
                "clicks": _number(clicks),
                "impressions": _number(impressions),
                "orders": _number(orders),
                "sales": _number(sales),
                "ctr": _ratio(clicks, impressions),
                "cpc": _ratio(spend, clicks),
                "cvr": _ratio(orders, clicks),
                "acos": _ratio(spend, sales),
                "roas": _ratio(sales, spend),
                "top_placement_click_share": None,
                "budget_full_days": (
                    sum(values[0] >= budget_value * BUDGET_FULL_THRESHOLD for _, values in selected)
                    if budget_value > 0 else None
                ),
            }

        reviews = []
        for audit, changed_date in dated:
            context = audit.get("context") if isinstance(audit.get("context"), Mapping) else {}
            before_values = audit.get("before") if isinstance(audit.get("before"), Mapping) else {}
            after_values = audit.get("after") if isinstance(audit.get("after"), Mapping) else {}
            base_budget = context.get("budget")
            before_budget = before_values.get("budget", base_budget)
            after_budget = after_values.get("budget", base_budget)
            before = summarize(changed_date - timedelta(days=7), changed_date - timedelta(days=1), before_budget)
            after = summarize(changed_date + timedelta(days=1), changed_date + timedelta(days=7), after_budget)
            reviews.append({
                "plan_id": as_text(audit.get("plan_id")),
                "operation": as_text(audit.get("operation")),
                "operation_label": as_text(audit.get("operation_label")) or as_text(audit.get("operation")),
                "changed_at": as_text(audit.get("finished_at")),
                "changed_business_date": changed_date.isoformat(),
                "before_value": before_values,
                "after_value": after_values,
                "before": before,
                "after": after,
                "status": "complete" if after["mature_days"] == 7 else "collecting",
                "post_progress": after["mature_days"] / 7,
                "limitations": ["广告位历史占比尚无逐日持久化数据，当前显示缺失且不推断排名。"],
            })
        return reviews

    def _cache_value(self, key: str) -> CacheEntry | None:
        with self._cache_lock:
            entry = self._cache.get(key)
            return entry if entry and entry.expires_at > self.monotonic() else None

    def _save_memory(self, key: str, value: Mapping[str, Any], ttl: int) -> None:
        created = self.monotonic()
        with self._cache_lock:
            self._cache[key] = CacheEntry(
                copy.deepcopy(dict(value)), created, created + ttl
            )

    def _mark_snapshot(
        self,
        entry: SnapshotEntry,
        *,
        stale: bool,
        refresh_pending: bool,
    ) -> dict[str, Any]:
        age = max(0.0, (self._now() - entry.generated_at).total_seconds())
        status = "stale_snapshot" if stale else "persistent_snapshot"
        result = copy.deepcopy(entry.value)
        meta = result.setdefault("meta", {})
        meta.update(
            {
                "cache_status": status,
                "cache_age_seconds": round(age, 1),
                "snapshot_generated_at": entry.generated_at.isoformat(timespec="seconds"),
                "snapshot_age_seconds": round(age, 1),
                "snapshot_stale": stale,
                "refresh_pending": refresh_pending,
                "refresh_retry_after_seconds": 2 if refresh_pending else 0,
            }
        )
        for source in result.get("sources", []):
            if source.get("cache_status") in {"miss", "hit"}:
                source["cache_status"] = status
        return result

    def _schedule_background(
        self,
        key: str,
        loader: Callable[[], dict[str, Any]],
        on_success: Callable[[dict[str, Any], datetime], None],
        *,
        forced: bool,
    ) -> bool:
        now = self.monotonic()
        with self._cache_lock:
            if key in self._refreshing:
                return True
            last_attempt = self._attempted_at.get(key)
            if not forced and last_attempt is not None and now - last_attempt < self.refresh_cooldown:
                return False
            if forced:
                last_forced = self._forced_at.get(key)
                if last_forced is not None and now - last_forced < self.refresh_cooldown:
                    return False
                self._forced_at[key] = now
            self._attempted_at[key] = now
            self._refreshing.add(key)

        def run() -> None:
            try:
                value = loader()
                on_success(value, self._now())
            except Exception:
                logging.getLogger("SellfoxAdDiagnostic.snapshot").warning(
                    "后台快照刷新失败：%s", key
                )
            finally:
                with self._cache_lock:
                    self._refreshing.discard(key)

        threading.Thread(
            target=run,
            name=f"sellfox-snapshot-{key[:48]}",
            daemon=True,
        ).start()
        return True

    def _snapshot_first(
        self,
        key: str,
        kind: str,
        ttl: int,
        refresh: bool,
        loader: Callable[[], dict[str, Any]],
        on_success: Callable[[dict[str, Any], datetime], None],
        *,
        campaign_id: str = "",
        refresh_key: str | None = None,
        cold_loader: Callable[[], dict[str, Any]] | None = None,
        cold_on_success: Callable[[dict[str, Any], datetime], None] | None = None,
    ) -> dict[str, Any]:
        if self.snapshot_store is None:
            return self._cached(key, ttl, refresh, loader)
        memory = self._cache_value(key)
        if memory and not refresh:
            return self._mark_cache(memory.value, "hit", memory.created_at)
        snapshot = self.snapshot_store.read(kind, campaign_id)
        if snapshot:
            age = (self._now() - snapshot.generated_at).total_seconds()
            if age >= -300:
                stale = age > self.snapshot_ttl
                pending = False
                if refresh or stale:
                    pending = self._schedule_background(
                        refresh_key or key, loader, on_success, forced=refresh
                    )
                return self._mark_snapshot(
                    snapshot, stale=stale, refresh_pending=pending
                )
        value = self._cached(key, ttl, refresh, cold_loader or loader)
        if value.get("meta", {}).get("cache_status") == "miss":
            (cold_on_success or on_success)(value, self._now())
        return value

    @staticmethod
    def _default_client() -> RealtimeAdsClient:
        client_id, client_secret = load_api_credentials()
        logger = logging.getLogger("SellfoxAdDiagnostic.upstream")
        client = RealtimeAdsClient(client_id, client_secret, logger)
        client.configure_run(
            deadline=time.monotonic() + REQUEST_DEADLINE_SECONDS,
            max_http_attempts=MAX_HTTP_ATTEMPTS,
        )
        return client

    def _now(self) -> datetime:
        value = self.clock()
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _timestamp(self) -> str:
        return self._now().astimezone(timezone.utc).isoformat(timespec="seconds")

    def _mature_window(self) -> tuple[date, date, date]:
        as_of = self._now().astimezone(ZoneInfo(BUSINESS_TIMEZONE)).date()
        end = as_of - timedelta(days=2)
        return as_of, end - timedelta(days=13), end

    def _cached(
        self,
        key: str,
        ttl: int,
        refresh: bool,
        loader: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        now = self.monotonic()
        stale: CacheEntry | None
        with self._cache_lock:
            stale = self._cache.get(key)
            if refresh:
                last = self._forced_at.get(key)
                if last is not None and now - last < self.refresh_cooldown:
                    raise RefreshLimited()
                self._forced_at[key] = now
            elif stale and stale.expires_at > now:
                return self._mark_cache(stale.value, "hit", stale.created_at)

        with self._cache_lock:
            fetch_lock = self._fetch_locks.setdefault(key, threading.Lock())

        with fetch_lock:
            now = self.monotonic()
            with self._cache_lock:
                current = self._cache.get(key)
                if not refresh and current and current.expires_at > now:
                    return self._mark_cache(current.value, "hit", current.created_at)
            try:
                value = loader()
            except DiagnosticError:
                if stale:
                    value = self._mark_cache(stale.value, "stale_if_error", stale.created_at)
                    value.setdefault("data_quality", {})["status"] = "partial"
                    value["data_quality"].setdefault("issues", []).append(
                        "LIVE_REFRESH_FAILED_USING_STALE_CACHE"
                    )
                    return value
                raise
            created = self.monotonic()
            with self._cache_lock:
                self._cache[key] = CacheEntry(copy.deepcopy(value), created, created + ttl)
            return self._mark_cache(value, "miss", created)

    def _mark_cache(
        self, value: Mapping[str, Any], status: str, created_at: float
    ) -> dict[str, Any]:
        result = copy.deepcopy(dict(value))
        result.setdefault("meta", {})["cache_status"] = status
        result["meta"]["cache_age_seconds"] = round(
            max(0, self.monotonic() - created_at), 1
        )
        for item in result.get("sources", []):
            if item.get("cache_status") == "miss":
                item["cache_status"] = status
        return result

    def _load_mature_payload(self) -> dict[str, Any]:
        try:
            mtime = self.mature_payload_path.stat().st_mtime_ns
        except OSError as exc:
            raise UpstreamUnavailable() from exc
        with self._mature_lock:
            if self._mature_payload is not None and mtime == self._mature_mtime_ns:
                return self._mature_payload
            try:
                payload = json.loads(self.mature_payload_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                raise UpstreamUnavailable() from exc
            if not isinstance(payload, dict) or payload.get("meta", {}).get("mode") != "live":
                raise UpstreamUnavailable()
            self._mature_payload = payload
            self._mature_mtime_ns = mtime
            return payload

    @staticmethod
    def _close(client: Any) -> None:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    def _cursor(
        self,
        client: Any,
        source_id: str,
        path: str,
        body: dict[str, Any],
        *,
        campaign_id: str = "",
        required: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
        fetched_at = self._timestamp()
        try:
            rows, pages = fetch_cursor_items(client, path, body, source_id)
        except Exception as exc:
            if required:
                raise UpstreamUnavailable() from exc
            return [], _source(
                source_id,
                path,
                fetched_at,
                status="error",
                error="UPSTREAM_ERROR",
            ), 0
        kept: list[dict[str, Any]] = []
        dropped = 0
        for row in rows:
            shop_id = as_text(row.get("shopId"))
            row_campaign = as_text(row.get("campaignId"))
            if shop_id != self.shop.shop_id:
                dropped += 1
                continue
            if campaign_id and row_campaign != campaign_id:
                dropped += 1
                continue
            kept.append(row)
        trace = _source(
            source_id,
            path,
            fetched_at,
            row_count=len(kept),
            pages=pages,
            raw_row_count=len(rows),
            scope_dropped=dropped,
            scope_verified=True,
        )
        return kept, trace, dropped

    def _page(
        self,
        client: Any,
        source_id: str,
        path: str,
        body: dict[str, Any],
        *,
        effective_date: str = "",
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        fetched_at = self._timestamp()
        try:
            rows, pages = fetch_page_items(client, path, body, source_id)
        except Exception:
            return [], _source(
                source_id,
                path,
                fetched_at,
                effective_date=effective_date,
                status="error",
                error="UPSTREAM_ERROR",
            )
        return rows, _source(
            source_id,
            path,
            fetched_at,
            effective_date=effective_date,
            row_count=len(rows),
            pages=pages,
            raw_row_count=len(rows),
        )

    def campaigns(self, *, refresh: bool = False) -> dict[str, Any]:
        def save(value: dict[str, Any], generated_at: datetime) -> None:
            self._save_memory("campaigns", value, self.list_ttl)
            if self.snapshot_store:
                self.snapshot_store.write_hot("campaigns", value, generated_at)

        return self._snapshot_first(
            "campaigns",
            "campaigns",
            self.list_ttl,
            refresh,
            self._fetch_campaigns,
            save,
        )

    def _fetch_campaigns(self) -> dict[str, Any]:
        client = self.client_factory()
        sources: list[dict[str, Any]] = []
        leaks_by_source: list[int] = []
        try:
            campaigns, trace, leaks = self._cursor(
                client,
                "sp_campaign",
                SP_CAMPAIGN_PATH,
                {"shopId": self.shop.shop_id, "pageSize": "1000"},
                required=True,
            )
            sources.append(trace)
            leaks_by_source.append(leaks)
            structures: dict[str, list[dict[str, Any]]] = {}
            for key, source_id, path in (
                ("groups", "sp_group", SP_GROUP_PATH),
                ("products", "sp_ad_product", SP_AD_PRODUCT_PATH),
                ("keywords", "sp_keyword", SP_KEYWORD_PATH),
                ("targets", "sp_target", SP_PRODUCT_TARGET_PATH),
            ):
                rows, trace, dropped = self._cursor(
                    client,
                    source_id,
                    path,
                    {"shopId": self.shop.shop_id, "pageSize": "1000"},
                )
                structures[key] = rows
                sources.append(trace)
                leaks_by_source.append(dropped)
        finally:
            self._close(client)
        groups = structures.get("groups", [])
        products = structures.get("products", [])
        keywords = structures.get("keywords", [])
        targets = structures.get("targets", [])
        mature, mature_source = self._mature_context("")
        sources.append(mature_source)
        performance_windows, windows_source = self._campaign_windows()
        sources.append(windows_source)
        realtime_by_campaign = self._realtime_campaign_context()
        mature_campaigns = {
            as_text(item.get("campaign_id")): item
            for item in mature.get("campaigns", [])
            if as_text(item.get("shop_id")) == self.shop.shop_id
        }
        mature_actions: dict[str, list[dict[str, Any]]] = {}
        for item in mature.get("recommendations", []):
            if as_text(item.get("shop_id")) != self.shop.shop_id:
                continue
            campaign_id = as_text(item.get("campaign_id"))
            mature_actions.setdefault(campaign_id, []).append(item)
        mature_products_by_campaign: dict[str, list[dict[str, Any]]] = {}
        for item in mature.get("advertised_products", []):
            mature_products_by_campaign.setdefault(
                as_text(item.get("campaign_id")), []
            ).append(item)
        products_by_campaign: dict[str, list[dict[str, Any]]] = {}
        for item in products:
            products_by_campaign.setdefault(as_text(item.get("campaignId")), []).append(item)
        groups_by_campaign: dict[str, list[dict[str, Any]]] = {}
        for item in groups:
            groups_by_campaign.setdefault(as_text(item.get("campaignId")), []).append(item)
        keywords_by_campaign: dict[str, list[dict[str, Any]]] = {}
        for item in keywords:
            keywords_by_campaign.setdefault(as_text(item.get("campaignId")), []).append(item)
        targets_by_campaign: dict[str, list[dict[str, Any]]] = {}
        for item in targets:
            targets_by_campaign.setdefault(as_text(item.get("campaignId")), []).append(item)
        output = []
        priority_order = {"高": 0, "中": 1, "低": 2}
        for item in campaigns:
            campaign_id = as_text(item.get("campaignId"))
            ad_rows = products_by_campaign.get(campaign_id, [])
            group_rows = groups_by_campaign.get(campaign_id, [])
            keyword_rows = keywords_by_campaign.get(campaign_id, [])
            target_rows = targets_by_campaign.get(campaign_id, [])
            snapshot = mature_campaigns.get(campaign_id, {})
            windows = performance_windows.get(campaign_id, {})
            default_bids = sorted(
                {_decimal(row.get("defaultBid")) for row in group_rows if as_text(row.get("defaultBid"))}
            )
            raw_actions = [
                value
                for value in mature_actions.get(campaign_id, [])
                if as_text(value.get("action_code")) in ACTIONABLE_CODES
            ]
            raw_actions.sort(
                key=lambda row: (
                    priority_order.get(as_text(row.get("priority")), 9),
                    -float(_decimal(row.get("spend"))),
                )
            )
            out_of_budget = "OUT_OF_BUDGET" in " ".join(
                as_text(row.get("servingStatus")) for row in (item, *ad_rows)
            ).upper()
            decreases = [row for row in raw_actions if as_text(row.get("action_code")) == "DECREASE_BID"]
            raw_primary = decreases[0] if out_of_budget and decreases else (raw_actions[0] if raw_actions else None)
            actions = [
                safe
                for row in raw_actions
                if (safe := _safe_campaign_action(item, row)) is not None
            ]
            primary = _safe_campaign_action(item, raw_primary)
            mature_spend = float(_decimal(snapshot.get("spend")))
            lifecycle = _campaign_lifecycle(
                mature_products_by_campaign.get(campaign_id, []),
                snapshot.get("listing_stage"),
            )
            performance_7d = windows.get("7d", {})
            performance_status = as_text(snapshot.get("performance_status")) or (
                _campaign_performance_status(performance_7d, lifecycle)
            )
            budget = _decimal(item.get("budget") or snapshot.get("budget"))
            realtime = realtime_by_campaign.get(campaign_id, {})
            realtime_today = realtime.get("today", {})
            today_spend = _decimal(realtime_today.get("spend"))
            today_budget_progress = _ratio(today_spend, budget) if budget > 0 and realtime_today else None
            budget_full_days = int(_decimal(snapshot.get("budget_utilization_days_7d")))
            if not budget_full_days and budget > 0:
                budget_full_days = sum(
                    _decimal(row.get("spend")) >= budget * BUDGET_FULL_THRESHOLD
                    for row in performance_7d.get("daily_trend", [])
                )
            daily_rows = sorted(
                performance_7d.get("daily_trend", []),
                key=lambda row: as_text(row.get("report_date") or row.get("date")),
            )
            latest_complete_budget_full = bool(snapshot.get("latest_complete_budget_full"))
            if budget > 0 and daily_rows:
                latest_complete_budget_full = (
                    _decimal(daily_rows[-1].get("spend"))
                    >= budget * BUDGET_FULL_THRESHOLD
                )
            budget_full = out_of_budget or latest_complete_budget_full
            ad_type, match_types = _campaign_ad_type(item, keyword_rows, target_rows)
            budget_matrix = (
                f"{performance_status}_{'full' if budget_full else 'not_full'}"
                if performance_status in {"normal", "poor"}
                else performance_status
            )
            output.append(
                {
                    **_json_safe(item),
                    "advertised_product_count": len(ad_rows),
                    "ad_group_count": len(group_rows),
                    "keyword_count": len(keyword_rows),
                    "product_target_count": len(target_rows),
                    "total_target_count": len(keyword_rows) + len(target_rows),
                    "default_bid": _number(default_bids[0]) if len(default_bids) == 1 else None,
                    "default_bid_min": _number(default_bids[0]) if default_bids else None,
                    "default_bid_max": _number(default_bids[-1]) if default_bids else None,
                    "skus": sorted({as_text(row.get("sku")) for row in ad_rows if as_text(row.get("sku"))}),
                    "asins": sorted({as_text(row.get("asin")).upper() for row in ad_rows if as_text(row.get("asin"))}),
                    "listing_stage": lifecycle,
                    "performance_status": performance_status,
                    "performance_window": "7d",
                    "budget_status": "full" if budget_full else "not_full",
                    "budget_full": budget_full,
                    "latest_complete_budget_full": latest_complete_budget_full,
                    "budget_utilization_days_7d": budget_full_days,
                    "today_budget_progress": today_budget_progress,
                    "today_budget_spend": _number(today_spend) if realtime_today else None,
                    "today_budget_latest_hour": realtime_today.get("latest_hour"),
                    "today_budget_status": realtime.get("status", "unavailable"),
                    "budget_matrix_status": budget_matrix,
                    "ad_type": ad_type,
                    "match_types": match_types,
                    "performance_windows": windows,
                    "mature_14d": _pick(
                        snapshot,
                        (
                            "spend",
                            "sales",
                            "orders",
                            "clicks",
                            "impressions",
                            "acos",
                            "roas",
                            "cpc",
                            "cvr",
                            "data_days",
                            "latest_date",
                        ),
                    ),
                    "actionable_count": len(actions),
                    "action_codes": sorted({as_text(row.get("action_code")) for row in actions}),
                    "spend": mature_spend,
                    "priority": as_text(primary.get("priority")) if primary else "观察",
                    "action": as_text(primary.get("action_code")) if primary else "MONITOR_ONLY",
                }
            )
        output.sort(
            key=lambda row: (
                0 if row["actionable_count"] else 1,
                -float(row.get("mature_14d", {}).get("spend") or 0),
                as_text(row.get("campaignId")),
            )
        )
        return {
            "meta": self._meta("campaign_list"),
            "shop": self._shop(),
            "campaigns": output,
            "data_quality": {
                "status": "partial" if any(source["status"] != "ok" for source in sources) else "complete",
                "issues": ["SCOPE_ROWS_DROPPED"] if sum(leaks_by_source) else [],
                "scope_dropped": sum(leaks_by_source),
            },
            "sources": sources,
        }

    def campaign_detail(
        self,
        campaign_id: str,
        *,
        refresh: bool = False,
        section: str = "full",
    ) -> dict[str, Any]:
        if not CAMPAIGN_ID_RE.fullmatch(campaign_id):
            raise BadRequest()
        if section not in DETAIL_SECTIONS:
            raise BadRequest()
        key = f"detail:{section}:{campaign_id}"
        full_key = f"detail:full:{campaign_id}"

        def load_full() -> dict[str, Any]:
            return self._fetch_campaign_detail(campaign_id, section="full")

        def load_overview() -> dict[str, Any]:
            return self._fetch_campaign_detail(campaign_id, section="overview")

        def save_full(value: dict[str, Any], generated_at: datetime) -> None:
            invalid = snapshot_refresh_errors(value)
            if invalid:
                logging.getLogger("SellfoxAdDiagnostic.snapshot").warning(
                    "快照验证失败，继续使用历史快照：%s", ",".join(invalid)
                )
                return
            overview = compact_overview_snapshot(value)
            self._save_memory(full_key, value, self.detail_ttl)
            self._save_memory(
                f"detail:overview:{campaign_id}", overview, self.detail_ttl
            )
            if self.snapshot_store:
                self.snapshot_store.write_hot(
                    "full", value, generated_at, campaign_id
                )
                self.snapshot_store.write_hot(
                    "overview", overview, generated_at, campaign_id
                )

        def save_overview(value: dict[str, Any], generated_at: datetime) -> None:
            overview = compact_overview_snapshot(value)
            overview.setdefault("meta", {})["snapshot_compacted_from_full"] = False
            self._save_memory(
                f"detail:overview:{campaign_id}", overview, self.detail_ttl
            )
            if self.snapshot_store:
                self.snapshot_store.write_hot(
                    "overview", overview, generated_at, campaign_id
                )

        return self._snapshot_first(
            key,
            section,
            self.detail_ttl,
            refresh,
            load_full if self.snapshot_store else lambda: self._fetch_campaign_detail(
                campaign_id, section=section
            ),
            save_full,
            campaign_id=campaign_id,
            refresh_key=full_key,
            cold_loader=load_overview if section == "overview" else None,
            cold_on_success=save_overview if section == "overview" else None,
        )

    def _fetch_campaign_detail(
        self,
        campaign_id: str,
        *,
        section: str = "full",
    ) -> dict[str, Any]:
        overview_only = section == "overview"
        client = self.client_factory()
        sources: list[dict[str, Any]] = []
        issues: list[str] = []
        body = {"shopId": self.shop.shop_id, "campaignId": campaign_id, "pageSize": "1000"}
        try:
            campaigns, trace, leaks = self._cursor(
                client,
                "sp_campaign",
                SP_CAMPAIGN_PATH,
                body,
                campaign_id=campaign_id,
                required=True,
            )
            sources.append(trace)
            if not campaigns:
                raise NotFound()
            if len(campaigns) != 1:
                raise UpstreamUnavailable()
            campaign = campaigns[0]
            structures: dict[str, list[dict[str, Any]]] = {}
            full_specs = (
                ("ad_groups", "sp_group", SP_GROUP_PATH),
                ("ad_products", "sp_ad_product", SP_AD_PRODUCT_PATH),
                ("keywords", "sp_keyword", SP_KEYWORD_PATH),
                ("product_targets", "sp_target", SP_PRODUCT_TARGET_PATH),
                ("negative_keywords", "sp_negative_keyword", SP_NEGATIVE_KEYWORD_PATH),
                ("negative_product_targets", "sp_negative_target", SP_NEGATIVE_TARGET_PATH),
            )
            specs = (
                (("ad_products", "sp_ad_product", SP_AD_PRODUCT_PATH),)
                if overview_only
                else full_specs
            )
            scope_dropped = leaks
            for key, source_id, path in specs:
                rows, trace, dropped = self._cursor(
                    client,
                    source_id,
                    path,
                    body,
                    campaign_id=campaign_id,
                )
                structures[key] = rows
                sources.append(trace)
                scope_dropped += dropped
                if trace["status"] != "ok":
                    issues.append(f"{source_id.upper()}_UNAVAILABLE")

            products = structures["ad_products"]
            product_keys = {
                (as_text(row.get("asin")).upper(), as_text(row.get("sku")))
                for row in products
                if as_text(row.get("asin")) and as_text(row.get("sku"))
            }
            local_date = self._now().astimezone(ZoneInfo(self.shop.timezone)).date()
            online_rows, online_source = self._fetch_online_products(
                client, product_keys
            )
            sources.append(online_source)
            analysis_rows: list[dict[str, Any]] = []
            finance_rows: list[dict[str, Any]] = []
            finance_windows: dict[str, list[dict[str, Any]]] = {}
            return_rows: list[dict[str, Any]] = []
            sales_trends: dict[str, dict[str, list[dict[str, Any]]]] = {}
            context_sources: list[dict[str, Any]] = []
            if not overview_only:
                analysis_rows, analysis_source = self._fetch_product_analysis(
                    client, product_keys, local_date
                )
                finance_sources: list[dict[str, Any]] = []
                for window_days in (7, 14, 30):
                    window_key = f"{window_days}d"
                    window_rows, window_source = self._fetch_product_profit(
                        client, product_keys, local_date, window_days=window_days
                    )
                    finance_windows[window_key] = window_rows
                    finance_sources.append(window_source)
                finance_rows = finance_windows["14d"]
                return_rows, return_source = self._fetch_fba_returns(
                    client, product_keys, local_date
                )
                sales_trends, trend_sources = self._fetch_product_sales_trends(
                    client, product_keys, local_date
                )
                context_sources = [
                    analysis_source,
                    *finance_sources,
                    return_source,
                    *trend_sources,
                ]
                sources.extend(context_sources)
            listing_context, listing_quality = self._build_listing_context(
                products,
                online_rows,
                analysis_rows,
                finance_rows,
                return_rows,
                sales_trends,
                local_date,
                finance_windows=finance_windows,
            )
            for trace in (online_source, *context_sources):
                scope_dropped += int(trace.get("scope_dropped") or 0)
            if listing_quality["unknown"]:
                issues.append("LISTING_MAPPING_UNKNOWN")

            today: dict[str, Any] = {}
            full_hour_specs = (
                ("campaign", "hour_campaign", SP_HOUR_CAMPAIGN_PATH, "campaign", 15),
                ("ad_groups", "hour_group", SP_HOUR_GROUP_PATH, "adGroup", 15),
                ("ad_products", "hour_ad_product", SP_HOUR_AD_PRODUCT_PATH, "adProduct", 15),
                ("targets", "hour_target", SP_HOUR_TARGET_PATH, "target", 120),
                ("placements", "hour_placement", SP_HOUR_PLACEMENT_PATH, "placement", 15),
            )
            hour_specs = (
                tuple(item for item in full_hour_specs if item[0] != "ad_groups")
                if overview_only
                else full_hour_specs
            )

            def fetch_hour(spec: tuple[str, str, str, str, int]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
                _, source_id, path, aggregation, expected_lag = spec
                if not overview_only:
                    return self._hour(
                        client, source_id, path, aggregation, campaign_id, local_date, expected_lag
                    )
                worker = self.client_factory()
                token = getattr(client, "_access_token", "")
                if token and hasattr(worker, "_access_token"):
                    worker._access_token = token
                try:
                    return self._hour(
                        worker, source_id, path, aggregation, campaign_id, local_date, expected_lag
                    )
                finally:
                    self._close(worker)

            if overview_only:
                with ThreadPoolExecutor(max_workers=len(hour_specs)) as executor:
                    hour_results = list(executor.map(fetch_hour, hour_specs))
            else:
                hour_results = [fetch_hour(spec) for spec in hour_specs]

            for (key, source_id, _, aggregation, _), (rows, trace) in zip(hour_specs, hour_results):
                sources.append(trace)
                today[key] = {
                    "metric_level": aggregation,
                    "summary": _aggregate_metrics(rows),
                    "rows": [_json_safe(row) for row in rows],
                    "quality_status": trace["status"],
                    "quality_issues": trace.get("quality_issues", []),
                    "anomaly_rows": int(trace.get("anomaly_rows") or 0),
                }
                scope_dropped += int(trace.get("scope_dropped") or 0)
                if trace["status"] == "error":
                    issues.append(f"{source_id.upper()}_UNAVAILABLE")
                elif trace["status"] == "partial":
                    issues.extend(trace.get("quality_issues", []))

            pacing, pacing_source = self._campaign_pacing(
                client,
                campaign_id,
                local_date,
                today.get("campaign", {}).get("rows", []),
                parallel=overview_only,
            )
            today["pacing"] = pacing
            sources.append(pacing_source)
            if pacing_source["status"] == "error":
                issues.append("HOUR_CAMPAIGN_PACING_UNAVAILABLE")
        finally:
            self._close(client)

        mature, mature_source = self._mature_context(campaign_id)
        sources.append(mature_source)
        report_keys = (
            {"placements"}
            if overview_only
            else set(DEEP_REPORT_TYPES).difference({"search_terms"})
        )
        deep_reports, deep_sources = self._deep_reports(
            campaign_id,
            report_keys=report_keys,
        )
        waste_page, index_source = self._search_term_page(
            campaign_id, "waste", page=1, page_size=10
        )
        conversion_page, _ = self._search_term_page(
            campaign_id, "conversion", page=1, page_size=10
        )
        deep_reports["search_terms"] = {
            "status": waste_page["status"],
            "report_type": "adSearchTermReport",
            "effective_date": waste_page["effective_date"],
            "metric_level": "search_terms",
            "entity_count": waste_page["entity_count"],
            "summary": waste_page["summary"],
            "waste_summary": waste_page["kind_summary"],
            "conversion_summary": conversion_page["kind_summary"],
            "top_waste": waste_page["rows"],
            "top_converting": conversion_page["rows"],
            "waste_count": waste_page["total"],
            "conversion_count": conversion_page["total"],
        }
        deep_sources.append(index_source)
        mature["deep_reports"] = deep_reports
        mature["source_priority"] = "downloaded_sellfox_report_files_then_verified_rule_snapshot"
        mature["preferred_campaign_summary"] = deep_reports.get("campaigns", {}).get("summary", {})
        sources.extend(deep_sources)
        if mature_source["status"] != "ok":
            issues.append("MATURE_14D_UNAVAILABLE")
        decision = self._build_decision(
            campaign,
            structures,
            listing_context,
            mature,
            today,
            sources,
        )
        adjustment_reviews = self._adjustment_reviews(campaign_id)
        source_errors = [source["source_id"] for source in sources if source["status"] == "error"]
        partial_sources = [source["source_id"] for source in sources if source["status"] == "partial"]
        if any(source_id in CORE_SOURCE_IDS for source_id in source_errors):
            quality_status = "partial"
        elif source_errors or partial_sources or listing_quality["unknown"] or scope_dropped:
            quality_status = "partial"
        else:
            quality_status = "complete"
        return {
            "meta": self._meta(f"campaign_detail_{section}", campaign_id),
            "shop": self._shop(),
            "campaign": _json_safe(campaign),
            "structure": _json_safe(structures),
            "listing_context": listing_context,
            "performance": {
                "mature_14d": mature,
                "today": {
                    "is_provisional": True,
                    "report_timezone": self.shop.timezone,
                    "report_date": local_date.isoformat(),
                    "attribution_warning": "当日订单和销售额可能延迟归因，只用于确认、冲突和阻断。",
                    **today,
                },
            },
            "decision": decision,
            "adjustment_reviews": adjustment_reviews,
            "data_quality": {
                "status": quality_status,
                "issues": sorted(set(issues)),
                "source_errors": source_errors,
                "partial_sources": partial_sources,
                "scope_dropped": scope_dropped,
                "scope_verified": True,
                "listing_mapping": listing_quality,
            },
            "sources": sources,
        }

    def _fetch_online_products(
        self,
        client: Any,
        product_keys: set[tuple[str, str]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not product_keys:
            return [], _source(
                "online_product",
                ONLINE_PRODUCT_PATH,
                self._timestamp(),
                status="skipped",
                error="NO_ADVERTISED_PRODUCT_KEYS",
            )
        body: dict[str, Any] = {
            "shopIdList": [self.shop.shop_id],
            "marketplaceIdList": [self.shop.marketplace_id],
            "onlineStatusList": ["active", "inActive"],
            "pageSize": "200",
        }
        if len(product_keys) == 1:
            _, sku = next(iter(product_keys))
            body.update({"searchType": "sku", "searchContent": sku})
        rows, trace = self._page(client, "online_product", ONLINE_PRODUCT_PATH, body)
        kept = [
            row
            for row in rows
            if as_text(row.get("shopId")) == self.shop.shop_id
            and (as_text(row.get("asin")).upper(), as_text(row.get("sku"))) in product_keys
        ]
        trace["row_count"] = len(kept)
        trace["scope_dropped"] = len(rows) - len(kept)
        trace["scope_verified"] = True
        return kept, trace

    def _fetch_product_analysis(
        self,
        client: Any,
        product_keys: set[tuple[str, str]],
        local_date: date,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not product_keys:
            return [], _source(
                "product_analysis",
                PRODUCT_ANALYSIS_PATH,
                self._timestamp(),
                status="skipped",
                error="NO_ADVERTISED_PRODUCT_KEYS",
            )
        end = local_date - timedelta(days=1)
        start = end - timedelta(days=13)
        skus = sorted({sku for _, sku in product_keys})
        body = {
            "pageSize": "100",
            "shopIdList": [self.shop.shop_id],
            "marketplaceIdList": [self.shop.marketplace_id],
            "currency": self.shop.currency,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "searchType": "sku",
            "searchMode": "exact",
            "asinType": "4",
            "searchContents": skus,
            "adTypeList": ["sp"],
            "compareType": "0",
        }
        rows, trace = self._page(
            client,
            "product_analysis",
            PRODUCT_ANALYSIS_PATH,
            body,
            effective_date=f"{start.isoformat()}..{end.isoformat()}",
        )
        kept = []
        for row in rows:
            shop_ok = _contains(row.get("shopIdList"), self.shop.shop_id)
            sku_ok = any(_contains(row.get("skuList"), sku) for sku in skus)
            if shop_ok and sku_ok:
                kept.append(row)
        trace["row_count"] = len(kept)
        trace["scope_dropped"] = len(rows) - len(kept)
        trace["scope_verified"] = True
        trace["server_filter_trusted"] = False
        trace["percentage_unit"] = "percentage_points"
        return kept, trace

    def _fetch_product_profit(
        self,
        client: Any,
        product_keys: set[tuple[str, str]],
        local_date: date,
        *,
        window_days: int = 14,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if window_days not in {7, 14, 30}:
            raise ValueError("window_days must be 7, 14, or 30")
        source_id = f"product_profit_{window_days}d"
        if not product_keys:
            return [], _source(
                source_id,
                PRODUCT_PROFIT_PATH,
                self._timestamp(),
                status="skipped",
                error="NO_ADVERTISED_PRODUCT_KEYS",
            )
        end = local_date - timedelta(days=1)
        start = end - timedelta(days=window_days - 1)
        skus = sorted({sku for _, sku in product_keys})
        rows, trace = self._page(
            client,
            source_id,
            PRODUCT_PROFIT_PATH,
            {
                "pageSize": "100",
                "shopIdList": [self.shop.shop_id],
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "currency": self.shop.currency,
                "searchType": "sku",
                "searchContentList": skus,
                "type": "sku",
                "mergeAsin": "false",
                "onlySettle": "false",
            },
            effective_date=f"{start.isoformat()}..{end.isoformat()}",
        )
        kept = [
            row
            for row in rows
            if _contains(row.get("shopIdList"), self.shop.shop_id)
            and any(
                _contains(row.get("skuList"), sku)
                or _contains(row.get("mskuList"), sku)
                for sku in skus
            )
        ]
        trace["row_count"] = len(kept)
        trace["scope_dropped"] = len(rows) - len(kept)
        trace["scope_verified"] = True
        trace["percentage_unit"] = "percentage_points"
        trace["negative_cost_policy"] = "absolute_value_for_display"
        return kept, trace

    def _fetch_fba_returns(
        self,
        client: Any,
        product_keys: set[tuple[str, str]],
        local_date: date,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not product_keys:
            return [], _source(
                "fba_returns",
                FBA_RETURN_PATH,
                self._timestamp(),
                status="skipped",
                error="NO_ADVERTISED_PRODUCT_KEYS",
            )
        start = local_date - timedelta(days=29)
        skus = sorted({sku for _, sku in product_keys})
        rows, trace = self._page(
            client,
            "fba_returns",
            FBA_RETURN_PATH,
            {
                "pageSize": "100",
                "shopIdList": [self.shop.shop_id],
                "searchType": "sku",
                "searchContent": skus,
                "returnStartDate": start.isoformat(),
                "returnEndDate": local_date.isoformat(),
            },
            effective_date=f"{start.isoformat()}..{local_date.isoformat()}",
        )
        kept = [
            row
            for row in rows
            if as_text(row.get("shopId")) == self.shop.shop_id
            and (as_text(row.get("asin")).upper(), as_text(row.get("msku"))) in product_keys
        ]
        trace["row_count"] = len(kept)
        trace["scope_dropped"] = len(rows) - len(kept)
        trace["scope_verified"] = True
        trace["pii_policy"] = "order_ids_and_customer_comments_excluded"
        return kept, trace

    def _fetch_product_sales_trends(
        self,
        client: Any,
        product_keys: set[tuple[str, str]],
        local_date: date,
    ) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], list[dict[str, Any]]]:
        if not product_keys:
            trace = _source(
                "product_sales_salePrice",
                PRODUCT_SALES_PATH,
                self._timestamp(),
                status="skipped",
                error="NO_ADVERTISED_PRODUCT_KEYS",
            )
            return {}, [trace]
        end = local_date - timedelta(days=1)
        start = end - timedelta(days=29)
        skus = sorted({sku for _, sku in product_keys})
        output: dict[str, dict[str, list[dict[str, Any]]]] = {sku: {} for sku in skus}
        traces: list[dict[str, Any]] = []
        for metric in ("salePrice", "orderNum", "productNum"):
            rows, trace = self._page(
                client,
                f"product_sales_{metric}",
                PRODUCT_SALES_PATH,
                {
                    "pageSize": "100",
                    "type": metric,
                    "groupType": "sku",
                    "shopIdList": [self.shop.shop_id],
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "searchType": "sku",
                    "searchContentList": skus,
                    "statTimeType": "1",
                    "currency": self.shop.currency,
                    "mergeAsin": "false",
                },
                effective_date=f"{start.isoformat()}..{end.isoformat()}",
            )
            kept = []
            for row in rows:
                shop_ok = (
                    as_text(row.get("shopId")) == self.shop.shop_id
                    if "shopId" in row
                    else _contains(row.get("shopIds"), self.shop.shop_id)
                    or _contains(row.get("shopIdList"), self.shop.shop_id)
                )
                matched_skus = [
                    sku
                    for sku in skus
                    if _contains(row.get("skuList"), sku)
                    or _contains(row.get("mskuList"), sku)
                    or _contains(row.get("skus"), sku)
                    or _contains(row.get("mskus"), sku)
                    or as_text(row.get("sku")) == sku
                    or as_text(row.get("msku")) == sku
                ]
                if not shop_ok or not matched_skus:
                    continue
                kept.append(row)
                series = row.get("productSaleDayOpenVo")
                clean_series = series if isinstance(series, list) else []
                for sku in matched_skus:
                    output[sku][metric] = [_json_safe(item) for item in clean_series if isinstance(item, dict)]
            trace["row_count"] = len(kept)
            trace["scope_dropped"] = len(rows) - len(kept)
            trace["scope_verified"] = True
            traces.append(trace)
        return output, traces

    def _hour(
        self,
        client: Any,
        source_id: str,
        path: str,
        aggregation: str,
        campaign_id: str,
        local_date: date,
        expected_lag_minutes: int,
        provisional: bool = True,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        fetched_at = self._timestamp()
        try:
            data = client.post_data(
                path,
                {
                    "aggregationType": aggregation,
                    "shopId": self.shop.shop_id,
                    "date": local_date.isoformat(),
                    "campaignId": campaign_id,
                },
                source_id,
            )
            raw_rows = data.get("itemList")
            if not isinstance(raw_rows, list) or any(not isinstance(row, dict) for row in raw_rows):
                raise MonitorFailure("invalid itemList")
            rows = []
            dropped = 0
            anomaly_rows = 0
            for row in raw_rows:
                if as_text(row.get("shopId")) != self.shop.shop_id:
                    dropped += 1
                    continue
                if as_text(row.get("campaignId")) != campaign_id:
                    dropped += 1
                    continue
                actual_date = as_text(row.get("date"))
                if actual_date != local_date.isoformat():
                    dropped += 1
                    continue
                if not as_text(row.get("hour")):
                    dropped += 1
                    continue
                hour = _decimal(row.get("hour"))
                metrics = [_decimal(row.get(field)) for field in METRIC_FIELDS]
                if hour != hour.to_integral_value() or not 0 <= int(hour) <= 23:
                    raise MonitorFailure("invalid report clock")
                if any(value < 0 for value in metrics):
                    raise MonitorFailure("negative metric")
                if _decimal(row.get("clicks")) > _decimal(row.get("impressions")):
                    anomaly_rows += 1
                rows.append({**row, "hour": int(hour)})
            latest_hour = max((int(row["hour"]) for row in rows), default=None)
            quality_issues = []
            if dropped:
                quality_issues.append("SCOPE_ROWS_DROPPED")
            if anomaly_rows:
                quality_issues.append(PROVISIONAL_COUNTER_ANOMALY)
            return rows, _source(
                source_id,
                path,
                fetched_at,
                effective_date=local_date.isoformat(),
                row_count=len(rows),
                pages=1,
                raw_row_count=len(raw_rows),
                scope_dropped=dropped,
                scope_verified=True,
                latest_hour=latest_hour,
                provisional=provisional,
                expected_lag_minutes=expected_lag_minutes,
                status="partial" if quality_issues else "ok",
                error=";".join(quality_issues),
                quality_issues=quality_issues,
                anomaly_rows=anomaly_rows,
            )
        except Exception:
            return [], _source(
                source_id,
                path,
                fetched_at,
                effective_date=local_date.isoformat(),
                status="error",
                error="UPSTREAM_ERROR",
                provisional=provisional,
                expected_lag_minutes=expected_lag_minutes,
            )

    def _campaign_pacing(
        self,
        client: Any,
        campaign_id: str,
        local_date: date,
        today_rows: Sequence[Mapping[str, Any]],
        *,
        parallel: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        fetched_at = self._timestamp()
        today_summary = _aggregate_metrics(today_rows)
        latest_hour = today_summary.get("latest_hour")
        dates = [local_date - timedelta(days=offset) for offset in range(1, 8)]
        if latest_hour is None:
            return {
                "report_timezone": self.shop.timezone,
                "report_date": local_date.isoformat(),
                "latest_complete_hour": None,
                "minimum_comparison_hours": 4,
                "comparison_ready": False,
                "today": {"spend": today_summary.get("spend")},
                "history": [],
            }, _source(
                "hour_campaign_pacing_history",
                SP_HOUR_CAMPAIGN_PATH,
                fetched_at,
                status="skipped",
                error="TODAY_HOUR_NOT_AVAILABLE",
            )

        def fetch_day(history_date: date) -> tuple[date, list[dict[str, Any]], dict[str, Any]]:
            if not parallel:
                rows, trace = self._hour(
                    client,
                    f"hour_campaign_history_{history_date.isoformat()}",
                    SP_HOUR_CAMPAIGN_PATH,
                    "campaign",
                    campaign_id,
                    history_date,
                    15,
                    provisional=False,
                )
                return history_date, rows, trace
            worker = self.client_factory()
            token = getattr(client, "_access_token", "")
            if token and hasattr(worker, "_access_token"):
                worker._access_token = token
            try:
                rows, trace = self._hour(
                    worker,
                    f"hour_campaign_history_{history_date.isoformat()}",
                    SP_HOUR_CAMPAIGN_PATH,
                    "campaign",
                    campaign_id,
                    history_date,
                    15,
                    provisional=False,
                )
                return history_date, rows, trace
            finally:
                self._close(worker)

        if parallel:
            with ThreadPoolExecutor(max_workers=len(dates)) as executor:
                results = list(executor.map(fetch_day, dates))
        else:
            results = [fetch_day(history_date) for history_date in dates]

        history = []
        same_hour_spends: list[Decimal] = []
        comparable_metrics: list[dict[str, Any]] = []
        traces = []
        for history_date, rows, trace in results:
            traces.append(trace)
            full_summary = _aggregate_metrics(rows)
            comparable_rows = [row for row in rows if int(_decimal(row.get("hour"))) <= latest_hour]
            comparable_summary = _aggregate_metrics(comparable_rows)
            available = trace["status"] != "error" and (
                full_summary.get("latest_hour") is not None
                and int(full_summary["latest_hour"]) >= latest_hour
            )
            same_hour_spend = comparable_summary.get("spend") if available else None
            if same_hour_spend is not None:
                same_hour_spends.append(_decimal(same_hour_spend))
                comparable_metrics.append(comparable_summary)
            history.append({
                "date": history_date.isoformat(),
                "status": trace["status"],
                "latest_hour": full_summary.get("latest_hour"),
                "same_hour_spend": same_hour_spend,
                "same_hour_metrics": comparable_summary if available else {},
                "full_day_spend": full_summary.get("spend") if trace["status"] != "error" else None,
            })

        yesterday = history[0]
        yesterday_same = yesterday.get("same_hour_spend")
        yesterday_full = yesterday.get("full_day_spend")
        median_spend = statistics.median(same_hour_spends) if same_hour_spends else None
        today_spend = _decimal(today_summary.get("spend"))

        median_metrics = {
            metric: _number(statistics.median(values))
            for metric in ("spend", "impressions", "clicks", "orders", "sales", "cpc")
            if (values := [
                _decimal(summary.get(metric))
                for summary in comparable_metrics
                if summary.get(metric) is not None
            ])
        }

        def relative_change(baseline: Any) -> float | int | None:
            baseline_value = _decimal(baseline)
            return _number((today_spend - baseline_value) / baseline_value) if baseline_value > 0 else None

        def metric_changes(baselines: Mapping[str, Any]) -> dict[str, Any]:
            changes = {}
            for metric, baseline in baselines.items():
                baseline_value = _decimal(baseline)
                current = _decimal(today_summary.get(metric))
                changes[metric] = _number((current - baseline_value) / baseline_value) if baseline_value > 0 else None
            return changes

        statuses = [trace["status"] for trace in traces]
        available_days = len(same_hour_spends)
        source_status = "error" if not any(status != "error" for status in statuses) else (
            "ok" if all(status == "ok" for status in statuses) else "partial"
        )
        quality_issues = sorted({
            issue
            for trace in traces
            for issue in trace.get("quality_issues", [])
        })
        pacing = {
            "report_timezone": self.shop.timezone,
            "report_date": local_date.isoformat(),
            "latest_complete_hour": latest_hour,
            "complete_hours": latest_hour + 1,
            "minimum_comparison_hours": 4,
            "comparison_ready": latest_hour >= 3 and available_days >= 3,
            "today": {
                "spend": today_summary.get("spend"),
                "metrics": today_summary,
                "through_hour": latest_hour,
            },
            "yesterday_same_hour": {
                "date": yesterday["date"],
                "spend": yesterday_same,
                "change": relative_change(yesterday_same),
                "metrics": yesterday.get("same_hour_metrics", {}),
                "changes": metric_changes(yesterday.get("same_hour_metrics", {})),
            },
            "prior_7d_same_hour": {
                "available_days": available_days,
                "required_days": 3,
                "median_spend": _number(median_spend) if median_spend is not None else None,
                "change": relative_change(median_spend),
                "medians": median_metrics,
                "changes": metric_changes(median_metrics),
            },
            "yesterday_full_day": {
                "date": yesterday["date"],
                "spend": yesterday_full,
            },
            "history": history,
        }
        return pacing, _source(
            "hour_campaign_pacing_history",
            SP_HOUR_CAMPAIGN_PATH,
            fetched_at,
            effective_date=f"{dates[-1].isoformat()}..{dates[0].isoformat()}",
            row_count=sum(int(trace.get("row_count") or 0) for trace in traces),
            pages=sum(int(trace.get("pages") or 0) for trace in traces),
            status=source_status,
            error=";".join(quality_issues) if quality_issues else ("UPSTREAM_ERROR" if source_status == "error" else ""),
            provisional=False,
            report_timezone=self.shop.timezone,
            comparison_hour=latest_hour,
            available_days=available_days,
            quality_issues=quality_issues,
        )

    def _build_listing_context(
        self,
        ad_products: Sequence[Mapping[str, Any]],
        online_rows: Sequence[Mapping[str, Any]],
        analysis_rows: Sequence[Mapping[str, Any]],
        finance_rows: Sequence[Mapping[str, Any]],
        return_rows: Sequence[Mapping[str, Any]],
        sales_trends: Mapping[str, Mapping[str, list[dict[str, Any]]]],
        as_of: date,
        *,
        finance_windows: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        finance_windows = finance_windows or {}
        output = []
        for ad in ad_products:
            asin = as_text(ad.get("asin")).upper()
            sku = as_text(ad.get("sku"))
            online = [
                row
                for row in online_rows
                if as_text(row.get("shopId")) == self.shop.shop_id
                and as_text(row.get("asin")).upper() == asin
                and as_text(row.get("sku")) == sku
            ]
            analysis = [
                row
                for row in analysis_rows
                if _contains(row.get("shopIdList"), self.shop.shop_id)
                and _contains(row.get("skuList"), sku)
                and (
                    not row.get("asinList")
                    or _contains(row.get("asinList"), asin, upper=True)
                )
            ]
            finance = [
                row
                for row in finance_rows
                if _contains(row.get("shopIdList"), self.shop.shop_id)
                and (
                    _contains(row.get("skuList"), sku)
                    or _contains(row.get("mskuList"), sku)
                )
                and (
                    not row.get("asinList")
                    or _contains(row.get("asinList"), asin, upper=True)
                )
            ]
            window_finance: dict[str, Any] = {}
            for window_key, window_rows in finance_windows.items():
                matches = [
                    row
                    for row in window_rows
                    if _contains(row.get("shopIdList"), self.shop.shop_id)
                    and (
                        _contains(row.get("skuList"), sku)
                        or _contains(row.get("mskuList"), sku)
                    )
                    and (
                        not row.get("asinList")
                        or _contains(row.get("asinList"), asin, upper=True)
                    )
                ]
                window_finance[window_key] = {
                    "window_days": int(window_key.removesuffix("d")),
                    "finance_mapping_status": "matched" if len(matches) == 1 else "not_found" if not matches else "ambiguous",
                    "finance": self._finance_context(matches[0] if len(matches) == 1 else None),
                }
            returns = [
                row
                for row in return_rows
                if as_text(row.get("shopId")) == self.shop.shop_id
                and as_text(row.get("asin")).upper() == asin
                and as_text(row.get("msku")) == sku
            ]
            mapping = "matched" if len(online) == 1 else "not_found" if not online else "ambiguous"
            opened = as_text(online[0].get("openDate")) if len(online) == 1 else ""
            age, stage = listing_stage_for(opened, as_of=as_of, new_days=NEW_LISTING_DAYS)
            if mapping != "matched" or stage == "unknown":
                stage = "unknown"
                age = None
            analysis_mapping = "matched" if len(analysis) == 1 else "not_found" if not analysis else "ambiguous"
            finance_mapping = "matched" if len(finance) == 1 else "not_found" if not finance else "ambiguous"
            output.append(
                {
                    "shop_id": self.shop.shop_id,
                    "campaign_id": as_text(ad.get("campaignId")),
                    "group_id": as_text(ad.get("groupId")),
                    "ad_id": as_text(ad.get("adId")),
                    "asin": asin,
                    "sku": sku,
                    "ad_state": as_text(ad.get("state")),
                    "ad_serving_status": as_text(ad.get("servingStatus")),
                    "mapping_status": mapping,
                    "analysis_mapping_status": analysis_mapping,
                    "finance_mapping_status": finance_mapping,
                    "open_date": opened,
                    "listing_age_days": age,
                    "listing_stage": stage,
                    "online_product": _pick(online[0] if len(online) == 1 else None, PRODUCT_CONTEXT_FIELDS),
                    "product_analysis": _pick(analysis[0] if len(analysis) == 1 else None, ANALYSIS_CONTEXT_FIELDS),
                    "finance": self._finance_context(finance[0] if len(finance) == 1 else None),
                    "operating_windows": window_finance,
                    "returns": self._return_context(returns),
                    "sales_trend": {
                        "metric_level": "sku_all_business",
                        "is_ad_campaign_attribution": False,
                        **_json_safe(sales_trends.get(sku, {})),
                    },
                    "profit_inventory_policy": "context_only_not_an_automatic_bid_rule",
                }
            )
        return output, {
            "total": len(output),
            "matched": sum(row["mapping_status"] == "matched" for row in output),
            "new": sum(row["listing_stage"] == "new" for row in output),
            "established": sum(row["listing_stage"] == "established" for row in output),
            "unknown": sum(row["listing_stage"] == "unknown" for row in output),
            "analysis_matched": sum(row["analysis_mapping_status"] == "matched" for row in output),
            "finance_matched": sum(row["finance_mapping_status"] == "matched" for row in output),
        }

    @staticmethod
    def _finance_context(row: Mapping[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {
                "status": "unavailable",
                "metric_level": "sku_all_business",
                "context_only": True,
            }
        values = _pick(row, FINANCE_CONTEXT_FIELDS)
        for key in tuple(values):
            if key.casefold().startswith("ad") and "cost" in key.casefold():
                values[key] = _number(abs(_decimal(values[key])))
        return {
            "status": "available",
            "metric_level": "sku_all_business",
            "is_ad_campaign_attribution": False,
            "context_only": True,
            "percentage_unit": "percentage_points",
            "negative_ad_cost_display": "absolute_value",
            **values,
        }

    @staticmethod
    def _return_context(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        reasons: dict[str, Decimal] = {}
        statuses: dict[str, Decimal] = {}
        total = Decimal("0")
        for row in rows:
            quantity = _decimal(row.get("quantity"))
            total += quantity
            reason = as_text(row.get("reasonStr")) or as_text(row.get("reason")) or "未知原因"
            status = as_text(row.get("status")) or "未知状态"
            reasons[reason] = reasons.get(reason, Decimal("0")) + quantity
            statuses[status] = statuses.get(status, Decimal("0")) + quantity
        ranked = lambda values: [
            {"name": key, "quantity": _number(value), "rate": _ratio(value, total)}
            for key, value in sorted(values.items(), key=lambda item: (-item[1], item[0]))[:10]
        ]
        return {
            "metric_level": "sku_all_business",
            "is_ad_campaign_attribution": False,
            "context_only": True,
            "window_days": 30,
            "total_quantity": _number(total),
            "top_reasons": ranked(reasons),
            "top_statuses": ranked(statuses),
            "customer_comments_included": False,
            "order_ids_included": False,
        }

    def _mature_context(self, campaign_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        fetched_at = self._timestamp()
        try:
            payload = self._load_mature_payload()
        except UpstreamUnavailable:
            return {
                "is_realtime": False,
                "status": "unavailable",
                "campaigns": [],
                "targets": [],
                "advertised_products": [],
                "recommendations": [],
                "daily_trend": [],
            }, _source(
                "mature_14d",
                "snapshot://ads-monitor.json",
                fetched_at,
                status="error",
                error="MATURE_SNAPSHOT_UNAVAILABLE",
                cache_status="local_snapshot",
            )
        meta = payload.get("meta") or {}
        as_of, expected_start, expected_end = self._mature_window()
        source_start_text = as_text(meta.get("source_start_date"))
        source_end_text = as_text(meta.get("source_end_date"))
        try:
            source_start = date.fromisoformat(source_start_text)
            source_end = date.fromisoformat(source_end_text)
            lag_days = int(meta.get("maturity_lag_days") or 0)
            lookback_days = int(meta.get("lookback_days") or 0)
        except (TypeError, ValueError):
            source_start = source_end = date.min
            lag_days = lookback_days = 0
        as_of_text = as_text(meta.get("as_of"))
        window_valid = (
            source_start == expected_start
            and source_end == expected_end
            and lag_days == 2
            and lookback_days == 14
            and (not as_of_text or as_of_text == as_of.isoformat())
        )
        if not window_valid:
            return {
                "is_realtime": False,
                "status": "unavailable",
                "source_start_date": source_start_text,
                "source_end_date": source_end_text,
                "expected_start_date": expected_start.isoformat(),
                "expected_end_date": expected_end.isoformat(),
                "campaigns": [],
                "targets": [],
                "advertised_products": [],
                "recommendations": [],
                "daily_trend": [],
            }, _source(
                "mature_14d",
                "snapshot://ads-monitor.json",
                fetched_at,
                effective_date=source_end_text,
                status="error",
                error="MATURE_SNAPSHOT_DATE_WINDOW_INVALID",
                cache_status="local_snapshot",
                expected_start_date=expected_start.isoformat(),
                expected_end_date=expected_end.isoformat(),
                business_as_of=as_of.isoformat(),
            )
        matcher = lambda row: (
            isinstance(row, dict)
            and as_text(row.get("shop_id")) == self.shop.shop_id
            and (not campaign_id or as_text(row.get("campaign_id")) == campaign_id)
        )
        context = {
            "is_realtime": False,
            "status": "mature_d2_snapshot",
            "generated_at": as_text(meta.get("generated_at")),
            "source_start_date": source_start_text,
            "source_end_date": source_end_text,
            "maturity_lag_days": lag_days,
            "lookback_days": lookback_days,
            "policy": payload.get("policy") or {},
            "campaigns": [row for row in payload.get("campaigns", []) if matcher(row)],
            "targets": [row for row in payload.get("targets", []) if matcher(row)],
            "advertised_products": [
                row for row in payload.get("advertised_products", []) if matcher(row)
            ],
            "recommendations": [row for row in payload.get("recommendations", []) if matcher(row)],
            "daily_trend": [
                row
                for row in payload.get("campaign_daily_trend", [])
                if matcher(row)
            ],
            "warning": "成熟归因层来自最近成功的赛狐API快照，默认截止D-2，不是实时数据。",
        }
        trace = _source(
            "mature_14d",
            "snapshot://ads-monitor.json",
            fetched_at,
            effective_date=context["source_end_date"],
            row_count=(
                len(context["campaigns"])
                + len(context["targets"])
                + len(context["advertised_products"])
            ),
            pages=0,
            cache_status="local_snapshot",
            upstream="Sellfox Open API bulk advertising reports",
            generated_at=context["generated_at"],
            maturity_lag_days=context["maturity_lag_days"],
            realtime=False,
        )
        return context, trace

    def _load_search_term_index(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        report_dir = self.deep_report_dir or DEEP_REPORT_DIR
        path = report_dir / SEARCH_TERM_INDEX_NAME
        fetched_at = self._timestamp()
        if not path.is_file():
            return {}, _source(
                "deep_search_terms_index",
                f"file://{SEARCH_TERM_INDEX_NAME}",
                fetched_at,
                status="missing",
                error="SEARCH_TERM_INDEX_MISSING",
                cache_status="file_cache",
                realtime=False,
            )
        try:
            stat = path.stat()
            cached = self._search_term_index_cache
            if cached and cached[0] == stat.st_mtime_ns:
                payload = cached[1]
            else:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("index payload must be an object")
                self._search_term_index_cache = (stat.st_mtime_ns, payload)
            meta = payload.get("meta")
            campaigns = payload.get("campaigns")
            if not isinstance(meta, Mapping) or not isinstance(campaigns, Mapping):
                raise ValueError("index metadata or campaigns missing")
            as_of, expected_start, expected_end = self._mature_window()
            if (
                as_text(meta.get("shop_id")) != self.shop.shop_id
                or as_text(meta.get("shop_name")) != self.shop.shop_name
                or as_text(meta.get("report_start_date")) != expected_start.isoformat()
                or as_text(meta.get("report_end_date")) != expected_end.isoformat()
            ):
                raise ReportDateWindowError("search term index scope or window invalid")
            modified = datetime.fromtimestamp(
                stat.st_mtime, timezone.utc
            ).isoformat(timespec="seconds")
            effective = f"{expected_start.isoformat()}..{expected_end.isoformat()}"
            return payload, _source(
                "deep_search_terms_index",
                f"file://{SEARCH_TERM_INDEX_NAME}",
                modified,
                effective_date=effective,
                row_count=sum(
                    int(value.get("entity_count") or 0)
                    for value in campaigns.values()
                    if isinstance(value, Mapping)
                ),
                cache_status="file_cache",
                report_type="adSearchTermReport",
                file_name=path.name,
                realtime=False,
                scope_verified=True,
                expected_start_date=expected_start.isoformat(),
                expected_end_date=expected_end.isoformat(),
                business_as_of=as_of.isoformat(),
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}, _source(
                "deep_search_terms_index",
                f"file://{SEARCH_TERM_INDEX_NAME}",
                fetched_at,
                status="error",
                error="SEARCH_TERM_INDEX_INVALID",
                cache_status="file_cache",
                realtime=False,
            )

    def _search_term_page(
        self,
        campaign_id: str,
        kind: str,
        *,
        page: int,
        page_size: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload, source = self._load_search_term_index()
        meta = payload.get("meta", {}) if payload else {}
        campaign = payload.get("campaigns", {}).get(campaign_id, {}) if payload else {}
        if not isinstance(campaign, Mapping):
            campaign = {}
        rows = campaign.get(kind, [])
        rows = rows if isinstance(rows, list) else []
        total = int(campaign.get(f"{kind}_count") or len(rows))
        start = (page - 1) * page_size
        return {
            "status": "available" if source["status"] == "ok" else source["status"],
            "campaign_id": campaign_id,
            "kind": kind,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
            "entity_count": int(campaign.get("entity_count") or 0),
            "summary": _json_safe(campaign.get("summary", {})),
            "kind_summary": _json_safe(campaign.get(f"{kind}_summary", {})),
            "rows": _json_safe(rows[start : start + page_size]),
            "effective_date": (
                f"{as_text(meta.get('report_start_date'))}..{as_text(meta.get('report_end_date'))}"
                if meta else ""
            ),
        }, source

    def search_term_page(
        self,
        campaign_id: str,
        kind: str,
        *,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        if (
            not CAMPAIGN_ID_RE.fullmatch(campaign_id)
            or kind not in SEARCH_TERM_KINDS
            or page < 1
            or page_size < 1
            or page_size > 10
        ):
            raise BadRequest()
        result, source = self._search_term_page(
            campaign_id, kind, page=page, page_size=page_size
        )
        return {
            "meta": self._meta("search_term_page", campaign_id),
            "shop": self._shop(),
            **result,
            "source": source,
        }

    def _deep_reports(
        self,
        campaign_id: str,
        *,
        report_keys: set[str] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        output: dict[str, Any] = {}
        sources: list[dict[str, Any]] = []
        as_of, expected_start, expected_end = self._mature_window()
        expected_dates = {
            (expected_start + timedelta(days=offset)).isoformat()
            for offset in range(14)
        }
        report_dir = self.deep_report_dir or DEEP_REPORT_DIR
        for key, (prefix, dimensions) in DEEP_REPORT_TYPES.items():
            if report_keys is not None and key not in report_keys:
                continue
            candidates = sorted(
                report_dir.glob(f"{prefix}-*.xlsx"),
                key=lambda path: (path.stat().st_mtime_ns, path.name),
                reverse=True,
            ) if report_dir.is_dir() else []
            if not candidates:
                output[key] = {"status": "missing", "summary": {}, "top": []}
                sources.append(
                    _source(
                        f"deep_{key}",
                        "/api/cpc/download/pageList.json",
                        self._timestamp(),
                        status="missing",
                        error="REPORT_FILE_MISSING",
                        cache_status="file_cache",
                        report_type=prefix,
                    )
                )
                continue
            path = candidates[0]
            try:
                headers, rows = self._read_report(path)
                required_headers = {"店铺", "日期", "广告活动ID"}
                if not required_headers.issubset(headers):
                    raise ReportScopeError("required scope headers missing")
                shops = {as_text(row.get("店铺")) for row in rows}
                if shops != {self.shop.shop_name}:
                    raise ReportScopeError("report contains foreign or missing shop")
                all_dates = [
                    excel_date_to_iso(row.get("日期"), "日期") for row in rows
                ]
                if set(all_dates) != expected_dates:
                    raise ReportDateWindowError("report date window is not current D-2 14d")
                filtered = [
                    row
                    for row in rows
                    if as_text(row.get("广告活动ID")) == campaign_id
                ]
                report = self._aggregate_deep_rows(filtered, dimensions, key)
                dates = sorted(set(all_dates))
                effective = f"{dates[0]}..{dates[-1]}" if dates else ""
                stat = path.stat()
                modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds")
                task_match = re.search(r"-(\d+)-", path.name)
                output[key] = {
                    "status": "available",
                    "report_type": prefix,
                    "effective_date": effective,
                    "file_generated_at": modified,
                    **report,
                }
                sources.append(
                    _source(
                        f"deep_{key}",
                        "/api/cpc/download/pageList.json",
                        modified,
                        effective_date=effective,
                        row_count=len(filtered),
                        pages=0,
                        cache_status="file_cache",
                        report_type=prefix,
                        report_task_id=task_match.group(1) if task_match else "",
                        create_endpoint="/api/cpc/download/createTask.json",
                        file_name=path.name,
                        raw_row_count=len(rows),
                        headers_count=len(headers),
                        realtime=False,
                        scope_verified=True,
                        expected_start_date=expected_start.isoformat(),
                        expected_end_date=expected_end.isoformat(),
                        business_as_of=as_of.isoformat(),
                    )
                )
            except (OSError, BulkReportError, ValueError) as exc:
                if isinstance(exc, ReportScopeError):
                    error_code = "REPORT_SCOPE_INVALID"
                elif isinstance(exc, ReportDateWindowError):
                    error_code = "REPORT_DATE_WINDOW_INVALID"
                else:
                    error_code = "REPORT_FILE_INVALID"
                output[key] = {"status": "error", "summary": {}, "top": []}
                sources.append(
                    _source(
                        f"deep_{key}",
                        "/api/cpc/download/pageList.json",
                        self._timestamp(),
                        status="error",
                        error=error_code,
                        cache_status="file_cache",
                        report_type=prefix,
                        file_name=path.name,
                        expected_start_date=expected_start.isoformat(),
                        expected_end_date=expected_end.isoformat(),
                        business_as_of=as_of.isoformat(),
                    )
                )
        return output, sources

    def _read_report(self, path: Path) -> tuple[list[str], list[dict[str, str]]]:
        stat = path.stat()
        cached = self._report_cache.get(path)
        if cached and cached[0] == stat.st_mtime_ns:
            return cached[1], cached[2]
        headers, rows = parse_first_sheet_xlsx(path)
        self._report_cache[path] = (stat.st_mtime_ns, headers, rows)
        return headers, rows

    @staticmethod
    def _aggregate_deep_rows(
        rows: Sequence[Mapping[str, Any]],
        dimensions: Sequence[str],
        report_key: str,
    ) -> dict[str, Any]:
        grouped: dict[tuple[str, ...], dict[str, Any]] = {}
        dates: set[str] = set()
        for row in rows:
            report_date = excel_date_to_iso(row.get("日期"), "日期")
            if report_date:
                dates.add(report_date)
            identity = tuple(as_text(row.get(field)) for field in dimensions)
            current = grouped.setdefault(
                identity,
                {
                    "identity": {field: value for field, value in zip(dimensions, identity)},
                    "spend": Decimal("0"),
                    "impressions": Decimal("0"),
                    "clicks": Decimal("0"),
                    "orders": Decimal("0"),
                    "sales": Decimal("0"),
                    "units": Decimal("0"),
                    "same_orders": Decimal("0"),
                    "other_orders": Decimal("0"),
                    "same_sales": Decimal("0"),
                    "other_sales": Decimal("0"),
                    "same_units": Decimal("0"),
                    "other_units": Decimal("0"),
                    "dates": set(),
                },
            )
            if report_date:
                current["dates"].add(report_date)
            if report_key == "purchased_items":
                current["other_sales"] += _report_decimal(row.get("其他SKU销售额"))
                current["other_units"] += _report_decimal(row.get("其他SKU销量"))
                current["sales"] += _report_decimal(row.get("其他SKU销售额"))
                current["units"] += _report_decimal(row.get("其他SKU销量"))
                continue
            mapping = {
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
            for field, header in mapping.items():
                current[field] += _report_decimal(row.get(header))

        def finalize(value: Mapping[str, Any]) -> dict[str, Any]:
            spend = value["spend"]
            clicks = value["clicks"]
            impressions = value["impressions"]
            orders = value["orders"]
            sales = value["sales"]
            return {
                "identity": value["identity"],
                "spend": _number(spend),
                "impressions": _number(impressions),
                "clicks": _number(clicks),
                "orders": _number(orders),
                "sales": _number(sales),
                "units": _number(value["units"]),
                "same_orders": _number(value["same_orders"]),
                "other_orders": _number(value["other_orders"]),
                "same_sales": _number(value["same_sales"]),
                "other_sales": _number(value["other_sales"]),
                "same_units": _number(value["same_units"]),
                "other_units": _number(value["other_units"]),
                "acos": _ratio(spend, sales),
                "roas": _ratio(sales, spend),
                "cpc": _ratio(spend, clicks),
                "ctr": _ratio(clicks, impressions),
                "cvr": _ratio(orders, clicks),
                "data_days": len(value["dates"]),
            }

        entities = [finalize(value) for value in grouped.values()]
        entities.sort(key=lambda value: (-float(value["spend"] or 0), -float(value["sales"] or 0), json.dumps(value["identity"], ensure_ascii=False, sort_keys=True)))
        summary = finalize(
            {
                "identity": {},
                "spend": sum((_decimal(value["spend"]) for value in entities), Decimal("0")),
                "impressions": sum((_decimal(value["impressions"]) for value in entities), Decimal("0")),
                "clicks": sum((_decimal(value["clicks"]) for value in entities), Decimal("0")),
                "orders": sum((_decimal(value["orders"]) for value in entities), Decimal("0")),
                "sales": sum((_decimal(value["sales"]) for value in entities), Decimal("0")),
                "units": sum((_decimal(value["units"]) for value in entities), Decimal("0")),
                "same_orders": sum((_decimal(value["same_orders"]) for value in entities), Decimal("0")),
                "other_orders": sum((_decimal(value["other_orders"]) for value in entities), Decimal("0")),
                "same_sales": sum((_decimal(value["same_sales"]) for value in entities), Decimal("0")),
                "other_sales": sum((_decimal(value["other_sales"]) for value in entities), Decimal("0")),
                "same_units": sum((_decimal(value["same_units"]) for value in entities), Decimal("0")),
                "other_units": sum((_decimal(value["other_units"]) for value in entities), Decimal("0")),
                "dates": dates,
            }
        )
        result = {
            "metric_level": report_key,
            "row_count": len(rows),
            "entity_count": len(entities),
            "summary": summary,
            "top": entities[:10],
        }
        if report_key == "search_terms":
            result["top_waste"] = sorted(
                [value for value in entities if not value["orders"] and value["spend"]],
                key=lambda value: -float(value["spend"]),
            )[:10]
            result["top_converting"] = sorted(
                [value for value in entities if value["orders"]],
                key=lambda value: (-float(value["sales"]), -float(value["orders"])),
            )[:10]
        return result

    def _build_decision(
        self,
        campaign: Mapping[str, Any],
        structure: Mapping[str, Sequence[Mapping[str, Any]]],
        listings: Sequence[Mapping[str, Any]],
        mature: Mapping[str, Any],
        today: Mapping[str, Any],
        sources: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        raw_recommendations = [
            row
            for row in mature.get("recommendations", [])
            if as_text(row.get("action_code")) in ACTIONABLE_CODES
        ]
        priority_order = {"高": 0, "中": 1, "低": 2}
        raw_recommendations.sort(
            key=lambda row: (
                priority_order.get(as_text(row.get("priority")), 9),
                -float(_decimal(row.get("spend"))),
            )
        )
        stages = {as_text(row.get("listing_stage")) for row in listings}
        if not listings or "unknown" in stages:
            lifecycle = "unknown"
        elif stages == {"new"}:
            lifecycle = "new"
        elif "new" in stages:
            lifecycle = "mixed"
        else:
            lifecycle = "established"
        serving = " ".join(
            [as_text(campaign.get("servingStatus"))]
            + [as_text(row.get("servingStatus")) for rows in structure.values() for row in rows]
        ).upper()
        out_of_budget = "OUT_OF_BUDGET" in serving
        decreases = [row for row in raw_recommendations if as_text(row.get("action_code")) == "DECREASE_BID"]
        raw_primary = decreases[0] if out_of_budget and decreases else (raw_recommendations[0] if raw_recommendations else None)
        recommendations = [
            safe
            for row in raw_recommendations
            if (safe := _safe_campaign_action(campaign, row)) is not None
        ]
        primary = _safe_campaign_action(campaign, raw_primary)
        automatic_targeting = as_text(campaign.get("targetingType")).casefold() == "auto"
        conflicts: list[dict[str, str]] = []
        protections: list[dict[str, str]] = []
        if out_of_budget:
            conflicts.append(
                {
                    "code": "OUT_OF_BUDGET_NOT_PROOF_TO_INCREASE",
                    "message": "预算不足只说明流量受限，不证明应该加预算；必须先验证成熟盈利和当日走势。",
                }
            )
        if lifecycle == "unknown":
            protections.append(
                {
                    "code": "LISTING_UNKNOWN_BLOCK",
                    "message": "广告商品未能唯一关联上架时间，阻断任何可执行调控。",
                }
            )
        elif lifecycle in {"new", "mixed"}:
            protections.append(
                {
                    "code": "NEW_LISTING_PROTECTION",
                    "message": "存在开售90天内SKU，不按老品表现规则机械调价，只进入新品诊断和人工复核。",
                }
            )
        if automatic_targeting:
            protections.append(
                {
                    "code": "AUTO_CAMPAIGN_NO_KEYWORD_CPC",
                    "message": "自动广告搜索词没有可直接修改的关键词CPC；优质词只建议人工新建手动精准和广泛广告。",
                }
            )

        confirmation = {
            "status": "no_mature_action" if not primary else "pending",
            "metric_level": "target" if primary and primary.get("target_id") else "campaign",
            "matched_rows": 0,
            "summary": {},
            "message": "当前没有成熟层可执行建议。" if not primary else "等待当日层确认。",
        }
        if primary:
            target_id = as_text(primary.get("target_id"))
            layer = today.get("targets", {}) if target_id else today.get("campaign", {})
            rows = list(layer.get("rows", []))
            layer_issues = {
                as_text(value) for value in layer.get("quality_issues", [])
            }
            if target_id:
                rows = [row for row in rows if as_text(row.get("targetingId")) == target_id]
            summary = _aggregate_metrics(rows)
            confirmation.update(
                matched_rows=len(rows),
                summary=summary,
                quality_status=as_text(layer.get("quality_status")) or "unknown",
                quality_issues=sorted(layer_issues),
            )
            action = as_text(primary.get("action_code"))
            target_acos = _decimal(primary.get("target_acos"))
            current_acos = summary.get("acos")
            if as_text(primary.get("action_code")) == "REVIEW_TARGET":
                confirmation.update(
                    status="review",
                    message="自动广告搜索词不能直接调关键词CPC；建议人工复核后新建手动精准和广泛广告。",
                )
            elif PROVISIONAL_COUNTER_ANOMALY in layer_issues:
                confirmation.update(
                    status="watch",
                    message="当日小时层存在点击数暂时大于曝光数的归因回填异常，只保留审计数据，不作强确认。",
                )
                conflicts.append(
                    {
                        "code": PROVISIONAL_COUNTER_ANOMALY,
                        "message": "赛狐当日小时指标尚在异步回填，当前层不能确认成熟建议。",
                    }
                )
            elif not rows:
                confirmation.update(status="pending", message="当日小时层尚无同粒度记录，不能确认成熟建议。")
            elif action == "DECREASE_BID" and current_acos is not None and Decimal(str(current_acos)) > target_acos * Decimal("1.2"):
                confirmation.update(status="confirmed", message="当日同粒度ACoS仍高于成熟规则阈值，方向一致。")
            elif action == "DECREASE_BID" and summary.get("sales"):
                confirmation.update(status="conflict", message="当日同粒度ACoS未继续超阈值，应保留成熟建议但暂停调整。")
                conflicts.append(
                    {
                        "code": "TODAY_CONFLICTS_WITH_MATURE_DECREASE",
                        "message": "当日暂定数据与成熟层降价方向不一致。",
                    }
                )
            else:
                confirmation.update(status="watch", message="当日归因尚不充分，只观察，不据此直接改变竞价。")

        source_errors = {as_text(source.get("source_id")) for source in sources if source.get("status") == "error"}
        if lifecycle == "unknown" or "mature_14d" in source_errors or "sp_ad_product" in source_errors or "online_product" in source_errors:
            gate = "BLOCK"
        elif lifecycle in {"new", "mixed"} or primary or confirmation["status"] in {"pending", "conflict", "watch"}:
            gate = "REVIEW"
        else:
            gate = "MONITOR_ONLY"
        product_count = len(structure.get("ad_products", []))
        granularity = {
            "campaign": "campaign_level",
            "targets": "target_or_keyword_level_when_targetingId_matches",
            "sku": (
                "single_product_context_only"
                if product_count == 1
                else "not_allocated_when_campaign_has_multiple_products"
            ),
            "product_count": product_count,
            "allocation_policy": "never_proportionally_split_campaign_metrics_across_skus",
        }
        action = as_text(primary.get("action_code")) if primary else "MONITOR_ONLY"
        mature_evidence = []
        if primary:
            mature_evidence.append(
                {
                    "code": f"MATURE_RULE_{as_text(primary.get('rule_id')).upper() or 'ACTION'}",
                    "label": "D-2成熟规则",
                    "message": as_text(primary.get("reason")) or "成熟窗口触发调控建议。",
                    "grain": as_text(primary.get("entity_type")) or "campaign",
                    "freshness": "mature_14d",
                    "status": "supports",
                    "metrics": _pick(primary, ("spend", "sales", "orders", "clicks", "acos", "target_acos")),
                }
            )
        else:
            mature_evidence.append(
                {
                    "code": "NO_MATURE_ACTION",
                    "label": "D-2成熟规则",
                    "message": "当前成熟窗口未触发可调整动作。",
                    "grain": "campaign",
                    "freshness": "mature_14d",
                    "status": "monitor",
                }
            )
        evidence = [
            *mature_evidence,
            {
                "code": "LISTING_LIFECYCLE",
                "label": "SKU上架阶段",
                "message": f"广告商品生命周期为 {lifecycle}。",
                "grain": "sku",
                "freshness": "live",
                "status": "unknown" if lifecycle == "unknown" else "verified",
            },
            {
                "code": "TODAY_CONFIRMATION",
                "label": "当日小时层确认",
                "message": as_text(confirmation.get("message")),
                "grain": as_text(confirmation.get("metric_level")),
                "freshness": "current_hour",
                "status": as_text(confirmation.get("status")),
                "summary": confirmation.get("summary", {}),
            },
        ]
        if out_of_budget:
            evidence.append(
                {
                    "code": "CAMPAIGN_OUT_OF_BUDGET",
                    "label": "预算状态",
                    "message": "活动流量受预算限制，但该信号不支持直接加预算。",
                    "grain": "campaign",
                    "freshness": "live",
                    "status": "context_only",
                }
            )
        blockers = []
        if gate == "BLOCK":
            blockers = [
                {
                    "code": "CORE_EVIDENCE_BLOCKED",
                    "message": "上架映射或核心证据不完整，只允许观察。",
                    "grain": "campaign",
                    "status": "blocked",
                    "blocking": True,
                }
            ]
        confidence = Decimal("0.2") if not primary else Decimal("0.65")
        if primary and lifecycle == "established":
            confidence += Decimal("0.10")
        if primary:
            confidence += {
                "confirmed": Decimal("0.15"),
                "pending": Decimal("-0.15"),
                "conflict": Decimal("-0.25"),
                "watch": Decimal("-0.10"),
            }.get(as_text(confirmation.get("status")), Decimal("0"))
        if source_errors:
            confidence -= Decimal("0.10")
        if lifecycle in {"new", "mixed"}:
            confidence -= Decimal("0.15")
        if lifecycle == "unknown":
            confidence = min(confidence, Decimal("0.10"))
        confidence = max(Decimal("0"), min(confidence, Decimal("0.95")))
        return {
            "mode": "review_only",
            "can_execute": False,
            "execution_gate": gate,
            "product_lifecycle": lifecycle,
            "action": action,
            "confidence": float(confidence),
            "evidence": _json_safe(evidence),
            "blockers": blockers,
            "primary_action": _json_safe(primary) if primary else None,
            "mature_evidence": _json_safe(mature_evidence),
            "mature_evidence_meta": {
                "is_realtime": False,
                "source_end_date": mature.get("source_end_date", ""),
                "generated_at": mature.get("generated_at", ""),
                "actions": _json_safe(recommendations),
            },
            "today_confirmation": confirmation,
            "conflicts": conflicts,
            "protections": protections,
            "metric_granularity": granularity,
            "profit_inventory_policy": "SKU利润和库存只作上下文，不直接触发竞价或预算修改。",
            "budget_policy": "预算不足不等于应该加预算；先看成熟ACoS、利润、库存、生命周期和当日确认。",
            "budget_guardrail_passed": False,
        }

    def _meta(self, kind: str, campaign_id: str = "") -> dict[str, Any]:
        return {
            "schema_version": "sellfox-ad-diagnostic-v1",
            "kind": kind,
            "request_id": uuid.uuid4().hex,
            "generated_at": self._timestamp(),
            "shop_id": self.shop.shop_id,
            "campaign_id": campaign_id,
            "mode": "live_read_only",
            "execution_policy": "review_only",
            "write_operations_available": False,
            "cache_status": "miss",
            "cache_age_seconds": 0,
        }

    def _shop(self) -> dict[str, str]:
        return {
            "shop_id": self.shop.shop_id,
            "shop_name": self.shop.shop_name,
            "marketplace_id": self.shop.marketplace_id,
            "currency": self.shop.currency,
            "timezone": self.shop.timezone,
        }

    def health(self) -> dict[str, Any]:
        current = self.snapshot_store._current_run() if self.snapshot_store else None
        with self._cache_lock:
            refreshing = sorted(self._refreshing)
        return {
            "status": "ok",
            "service": "sellfox-ad-diagnostic",
            "bind": f"{HOST}:{PORT}",
            "shop": self._shop(),
            "read_only": False,
            "diagnostic_data_read_only": True,
            "allowed_methods": ["GET", "POST", "OPTIONS"],
            "write_operations_available": True,
            "write_policy": "preview_then_explicit_confirmation",
            "snapshot": {
                "enabled": self.snapshot_store is not None,
                "ttl_seconds": self.snapshot_ttl,
                "current_run": current.name if current else "",
                "background_refreshes": refreshing,
            },
        }


class DiagnosticRequestHandler(BaseHTTPRequestHandler):
    service: DiagnosticService
    services: Mapping[str, DiagnosticService]
    control_service: SpControlService | None = None
    control_services: Mapping[str, SpControlService]
    default_shop_id = PILOT_SHOP_ID
    control_token = ""
    server_version = "SellfoxDiagnostic/1.0"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        logging.getLogger("SellfoxAdDiagnostic.http").info(
            "%s %s", self.command, urlsplit(self.path).path[:160]
        )

    def _origin(self) -> str:
        return self.headers.get("Origin", "")

    def _security_check(self) -> None:
        host = self.headers.get("Host", "")
        hostname = host.rsplit(":", 1)[0].strip("[]").lower() if host else ""
        if hostname and hostname not in {"127.0.0.1", "localhost"}:
            raise Forbidden()
        origin = self._origin()
        if origin and origin not in ALLOWED_ORIGINS:
            raise Forbidden()

    def _service_for_shop(self, shop_id: str) -> tuple[DiagnosticService, SpControlService | None]:
        service = self.services.get(shop_id)
        if service is None:
            raise Forbidden()
        return service, self.control_services.get(shop_id)

    def _service_for_query(self, query: Mapping[str, list[str]]) -> tuple[DiagnosticService, SpControlService | None]:
        values = [
            value
            for key, items in query.items()
            if key.lower() in {"shop", "shopid", "shop_id"}
            for value in items
        ]
        if len(set(values)) > 1:
            raise BadRequest()
        shop_id = values[0] if values else self.default_shop_id
        return self._service_for_shop(shop_id)

    def _send(self, status: int, payload: Mapping[str, Any] | None = None) -> None:
        raw = b"" if payload is None else json.dumps(_json_safe(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        origin = self._origin()
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def _error(self, exc: DiagnosticError) -> None:
        self._send(
            exc.status_code,
            {
                "error": {
                    "code": exc.error_code,
                    "message": exc.public_message,
                    "request_id": uuid.uuid4().hex,
                }
            },
        )

    def _control_error(self, exc: SpControlError) -> None:
        self._send(
            exc.status_code,
            {"error": {"code": exc.error_code, "message": str(exc), "request_id": uuid.uuid4().hex}},
        )

    def do_OPTIONS(self) -> None:
        try:
            self._security_check()
            requested = self.headers.get("Access-Control-Request-Method", "GET")
            if requested not in {"GET", "POST"}:
                raise BadRequest()
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            origin = self._origin()
            if origin in ALLOWED_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-SP-Control-Token")
                self.send_header("Access-Control-Max-Age", "600")
                self.send_header("Vary", "Origin")
            self.end_headers()
        except DiagnosticError as exc:
            self._error(exc)

    def do_GET(self) -> None:
        try:
            self._security_check()
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            service, control_service = self._service_for_query(query)
            refresh_values = query.get("refresh", ["0"])
            if len(refresh_values) != 1 or refresh_values[0] not in {"0", "1", "false", "true"}:
                raise BadRequest()
            refresh = refresh_values[0] in {"1", "true"}
            path = unquote(parsed.path)
            if path == "/api/diagnostic/shops":
                shops = sorted(
                    (
                        {
                            "id": item.shop.shop_id,
                            "name": item.shop.shop_name,
                            "currency": item.shop.currency,
                            "marketplace_id": item.shop.marketplace_id,
                            "timezone": item.shop.timezone,
                        }
                        for item in self.services.values()
                    ),
                    key=lambda item: (item["name"], item["id"]),
                )
                self._send(
                    200,
                    {
                        "default_shop_id": self.default_shop_id,
                        "refresh_interval_minutes": 60,
                        "shops": shops,
                    },
                )
                return
            if path == "/api/diagnostic/sp-controls/capabilities":
                campaign_values = query.get("campaign_id", [])
                if len(campaign_values) != 1 or not CAMPAIGN_ID_RE.fullmatch(campaign_values[0]):
                    raise BadRequest()
                if control_service is None:
                    raise NotFound()
                payload = control_service.capabilities(refresh=refresh)
                payload["campaign_id"] = campaign_values[0]
                payload["control_token"] = self.control_token
                self._send(200, payload)
                return
            if path == "/api/diagnostic/search-terms":
                campaign_values = query.get("campaign_id", [])
                kind_values = query.get("kind", [])
                page_values = query.get("page", ["1"])
                size_values = query.get("page_size", ["10"])
                if not (
                    len(campaign_values) == len(kind_values) == 1
                    and len(page_values) == len(size_values) == 1
                ):
                    raise BadRequest()
                try:
                    page = int(page_values[0])
                    page_size = int(size_values[0])
                except ValueError as exc:
                    raise BadRequest() from exc
                self._send(
                    200,
                    service.search_term_page(
                        campaign_values[0],
                        kind_values[0],
                        page=page,
                        page_size=page_size,
                    ),
                )
                return
            if path == "/api/diagnostic":
                campaign_values = query.get("campaign_id", [])
                if len(campaign_values) > 1:
                    raise BadRequest()
                if not campaign_values or not campaign_values[0]:
                    self._send(200, service.campaigns(refresh=refresh))
                    return
                section_values = query.get("section", ["full"])
                if len(section_values) != 1 or section_values[0] not in DETAIL_SECTIONS:
                    raise BadRequest()
                section = section_values[0]
                detail = (
                    service.campaign_detail(
                        campaign_values[0], refresh=refresh, section=section
                    )
                    if section != "full"
                    else service.campaign_detail(campaign_values[0], refresh=refresh)
                )
                if section == "full":
                    listing = service.campaigns(refresh=False)
                    detail["campaigns"] = listing.get("campaigns", [])
                    detail["campaign_list_meta"] = listing.get("meta", {})
                self._send(200, detail)
                return
            if path == "/api/diagnostic/health":
                self._send(200, service.health())
                return
            if path == "/api/diagnostic/campaigns":
                self._send(200, service.campaigns(refresh=refresh))
                return
            match = re.fullmatch(r"/api/diagnostic/campaigns/([^/]+)", path)
            if match:
                section_values = query.get("section", ["full"])
                if len(section_values) != 1 or section_values[0] not in DETAIL_SECTIONS:
                    raise BadRequest()
                section = section_values[0]
                self._send(
                    200,
                    (
                        service.campaign_detail(
                            match.group(1), refresh=refresh, section=section
                        )
                        if section != "full"
                        else service.campaign_detail(match.group(1), refresh=refresh)
                    ),
                )
                return
            raise NotFound()
        except DiagnosticError as exc:
            self._error(exc)
        except Exception:
            self._error(DiagnosticError())

    def _read_json_body(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise SpControlError("请求必须使用 application/json。")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise SpControlError("Content-Length 无效。") from exc
        if length < 2 or length > 65536:
            raise SpControlError("请求体大小无效。")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise SpControlError("请求体不是有效 JSON。") from exc
        if not isinstance(payload, dict):
            raise SpControlError("请求体必须是 JSON 对象。")
        return payload

    def do_POST(self) -> None:
        try:
            self._security_check()
            path = unquote(urlsplit(self.path).path)
            if path not in {"/api/diagnostic/sp-controls/preview", "/api/diagnostic/sp-controls/execute"}:
                self._method_not_allowed()
                return
            if self._origin() not in ALLOWED_ORIGINS:
                raise SpControlError("调控请求来源无效。", status_code=403, error_code="CONTROL_ORIGIN_INVALID")
            token = self.headers.get("X-SP-Control-Token", "")
            if not token or not secrets.compare_digest(token, self.control_token):
                raise SpControlError("调控令牌无效，请重新打开调控面板。", status_code=403, error_code="CONTROL_TOKEN_INVALID")
            payload = self._read_json_body()
            shop_id = as_text(payload.get("shop_id")) or self.default_shop_id
            service, control_service = self._service_for_shop(shop_id)
            if control_service is None:
                raise SpControlError("SP 调控服务未启用。", status_code=503, error_code="CONTROL_DISABLED")
            result = (
                control_service.preview(
                    payload,
                    context=service.campaign_detail(str(payload.get("campaign_id") or "")),
                )
                if path.endswith("/preview")
                else control_service.execute(payload)
            )
            self._send(200, result)
        except SpControlError as exc:
            self._control_error(exc)
        except DiagnosticError as exc:
            self._error(exc)
        except Exception:
            self._control_error(SpControlError("SP 调控服务暂时不可用。", status_code=500, error_code="CONTROL_INTERNAL_ERROR"))

    def _method_not_allowed(self) -> None:
        try:
            self._security_check()
        except DiagnosticError as exc:
            self._error(exc)
            return
        self._send(
            405,
            {
                "error": {
                    "code": "METHOD_NOT_ALLOWED",
                    "message": "该路径不支持此请求方法。SP 调控只允许通过预览与人工确认接口提交。",
                    "request_id": uuid.uuid4().hex,
                }
            },
        )

    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_HEAD = _method_not_allowed


class LocalDiagnosticServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(
    service: DiagnosticService,
    control_service: SpControlService | None = None,
    control_token: str = "",
    *,
    services: Mapping[str, DiagnosticService] | None = None,
    control_services: Mapping[str, SpControlService] | None = None,
) -> type[DiagnosticRequestHandler]:
    class BoundHandler(DiagnosticRequestHandler):
        pass

    BoundHandler.service = service
    BoundHandler.control_service = control_service
    default_shop_id = getattr(getattr(service, "shop", None), "shop_id", PILOT_SHOP_ID)
    BoundHandler.default_shop_id = default_shop_id
    BoundHandler.services = dict(services or {default_shop_id: service})
    BoundHandler.control_services = dict(
        control_services
        or ({default_shop_id: control_service} if control_service else {})
    )
    BoundHandler.control_token = control_token
    return BoundHandler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="赛狐SP广告诊断与人工确认调控服务")
    parser.add_argument("--config", type=Path, default=DEFAULT_MONITOR_CONFIG_PATH)
    parser.add_argument("--mature-payload", type=Path, default=DEFAULT_MATURE_PAYLOAD)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--snapshot-ttl-minutes", type=int, default=60)
    parser.add_argument("--no-snapshot", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.snapshot_ttl_minutes < 1:
        raise SystemExit("--snapshot-ttl-minutes 必须大于 0。")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    runtime_shops = DIAGNOSTIC_SHOPS
    discovery_client = None
    try:
        client_id, client_secret = load_api_credentials()
        discovery_client = SellfoxAdsClient(
            client_id,
            client_secret,
            logging.getLogger("sellfox-ad-diagnostic-shops"),
        )
        runtime_shops = resolve_diagnostic_shops(
            discovery_client,
            args.config.resolve(),
        )
        logging.info("广告诊断已加载 %s 个授权店铺。", len(runtime_shops))
    except Exception as exc:
        logging.warning(
            "动态店铺发现失败，暂用本地店铺清单：%s。",
            type(exc).__name__,
        )
    finally:
        if discovery_client is not None:
            discovery_client.close()
    services = {
        shop_id: DiagnosticService(
            shop=shop,
            mature_payload_path=args.mature_payload.resolve(),
            snapshot_dir=(
                None
                if args.no_snapshot
                else shop_data_dir(args.snapshot_dir.resolve(), shop_id)
            ),
            deep_report_dir=shop_data_dir(DEEP_REPORT_DIR, shop_id),
            snapshot_ttl=args.snapshot_ttl_minutes * 60,
        )
        for shop_id, shop in runtime_shops.items()
    }
    control_services = {
        shop_id: SpControlService(shop_id=shop_id)
        for shop_id in runtime_shops
    }
    default_shop_id = (
        PILOT_SHOP_ID if PILOT_SHOP_ID in services else next(iter(services))
    )
    service = services[default_shop_id]
    control_token = secrets.token_urlsafe(32)
    try:
        server = LocalDiagnosticServer(
            (HOST, PORT),
            make_handler(
                service,
                control_services[default_shop_id],
                control_token,
                services=services,
                control_services=control_services,
            ),
        )
    except OSError:
        logging.error("无法绑定 %s:%s；端口可能已被占用。", HOST, PORT)
        return 1
    logging.info("单店广告诊断与人工确认调控服务已启动：http://%s:%s", HOST, PORT)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
