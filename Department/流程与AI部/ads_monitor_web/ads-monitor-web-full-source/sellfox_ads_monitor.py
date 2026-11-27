#!/usr/bin/env python3
"""Read Sellfox SP advertising data and generate review-only recommendations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

# Keep scheduled runs self-contained even when the project virtualenv is absent.
_SCRIPT_ROOT = Path(__file__).resolve().parent
_BUNDLED_DEPENDENCY_PATH = _SCRIPT_ROOT / ".python_deps"
if _BUNDLED_DEPENDENCY_PATH.is_dir():
    sys.path.insert(0, str(_BUNDLED_DEPENDENCY_PATH))

from sellfox_import import (
    API_BASE_URL,
    Config,
    ImportFailure,
    SellfoxClient,
    as_text,
    load_encrypted_config,
)
from sellfox_ads_bulk_report import (
    BulkReportError,
    CAMPAIGN_REPORT,
    TARGETING_REPORT,
    collect_bulk_reports,
    parse_report_directory,
)


ROOT = _SCRIPT_ROOT
DEFAULT_CONFIG_PATH = ROOT / "ads_monitor_config.json"
SHOP_LIST_PATH = "/api/shop/pageList.json"
SP_CAMPAIGN_PATH = "/api/cpc/manageData/spCampaign.json"
SP_KEYWORD_PATH = "/api/cpc/manageData/spKeyword.json"
SP_PRODUCT_TARGET_PATH = "/api/cpc/manageData/spTarget.json"
SP_AD_PRODUCT_PATH = "/api/cpc/manageData/spAdProduct.json"
ONLINE_PRODUCT_PATH = "/api/order/api/product/v2/pageList.json"
SP_HOUR_CAMPAIGN_PATH = "/api/cpc/hourData/spCampaign.json"
SP_HOUR_TARGET_PATH = "/api/cpc/hourData/spTarget.json"
RULE_VERSION = "sellfox-sp-v1.1"
MONEY_QUANTUM = Decimal("0.01")
RATE_QUANTUM = Decimal("0.0001")

MARKETPLACE_CURRENCIES = {
    "ATVPDKIKX0DER": "USD",
    "A2EUQ1WTGCTBG2": "CAD",
    "A1AM78C64UM0Y8": "MXN",
    "A2Q3Y263D00KWC": "BRL",
    "A1RKKUPIHCS9HS": "EUR",
    "A1F83G8C2ARO7P": "GBP",
    "A13V1IB3VIYZZH": "EUR",
    "A1PA6795UKMFR9": "EUR",
    "APJ6JRA9NG5V4": "EUR",
    "A1805IZSGTT6HS": "EUR",
    "A2NODRKZP88ZB9": "SEK",
    "A1C3SOZRARQ6R3": "PLN",
    "AMEN7PMS3EDWL": "EUR",
    "A28R8C7NBKEWEA": "EUR",
    "A33AVAJ2PDY3EV": "TRY",
    "A39IBJ37TRP1C6": "AUD",
}

LOCAL_APPDATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
LOG_DIR = LOCAL_APPDATA / "SellfoxTK" / "logs"
LOG_PATH = LOG_DIR / "sellfox_ads_monitor.log"
WORKBOOK_NAME = "赛狐广告监控与调控建议.xlsx"
GENERATED_OUTPUT_NAMES = frozenset(
    {
        "sellfox_ads_monitor_payload.json",
        "sellfox_ads_recommendations.csv",
        WORKBOOK_NAME,
        f"{WORKBOOK_NAME}.inspect.ndjson",
        "previews",
    }
)


class MonitorFailure(ImportFailure):
    """A sanitized failure safe for logs and command output."""


class DataQualityFailure(MonitorFailure):
    """Raised when a report row cannot safely drive a recommendation."""


class OutputRollbackFailure(MonitorFailure):
    """Raised when old generated outputs require manual restoration."""


@dataclass(frozen=True)
class RuleSet:
    target_acos: Decimal
    min_orders: int
    scale_min_orders: int
    min_clicks: int
    min_spend: Decimal
    max_zero_order_spend: Decimal
    high_acos_multiplier: Decimal
    low_acos_multiplier: Decimal
    bid_decrease_pct: Decimal
    bid_increase_pct: Decimal
    budget_increase_pct: Decimal
    budget_utilization_threshold: Decimal
    budget_utilization_days: int
    min_bid: Decimal
    max_bid: Decimal
    max_change_pct: Decimal
    min_mature_days: int
    performance_ctr_threshold: Decimal
    performance_cvr_threshold: Decimal
    protected_campaign_ids: frozenset[str]
    protected_target_ids: frozenset[str]


@dataclass(frozen=True)
class ShopConfig:
    shop_id: str
    shop_name: str
    currency: str
    campaign_ids: tuple[str, ...]
    rules: RuleSet
    marketplace_id: str = ""
    region: str = ""


@dataclass(frozen=True)
class MonitorConfig:
    shops: tuple[ShopConfig, ...]
    discover_shops: bool
    default_rules: RuleSet
    lookback_days: int
    maturity_lag_days: int
    max_campaigns_per_shop: int
    pull_targets: bool
    listing_new_days: int
    main_product_window_days: int
    main_product_min_orders: int
    main_product_max_daily_cv: Decimal
    main_product_sudden_drop_ratio: Decimal
    report_shop_batch_size: int
    report_poll_seconds: int
    report_timeout_seconds: int
    database_path: Path
    output_dir: Path
    raw_report_dir: Path
    dashboard_payload_path: Path | None
    node_path: str


@dataclass
class RunCoverage:
    requested_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    quality_failures: int = 0
    selected_campaigns: int = 0
    skipped_campaigns: int = 0

    @property
    def status(self) -> str:
        if self.failed_calls or self.quality_failures or self.skipped_campaigns:
            return "partial"
        return "complete"


@dataclass(frozen=True)
class OutputSwapState:
    staging_dir: Path
    final_dir: Path
    backup_dir: Path
    moved_old: tuple[str, ...]
    moved_new: tuple[str, ...]


def decimal_value(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def report_decimal(value: Any, field: str) -> Decimal:
    if value is None or value == "":
        raise DataQualityFailure(f"小时报告缺少 {field}。")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DataQualityFailure(f"小时报告 {field} 不是有效数字。") from exc
    if not result.is_finite():
        raise DataQualityFailure(f"小时报告 {field} 不是有限数字。")
    return result


def config_decimal(value: Any, default: str, field: str) -> Decimal:
    source = default if value is None or value == "" else value
    try:
        result = Decimal(str(source))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MonitorFailure(f"规则 {field} 不是有效数字。") from exc
    if not result.is_finite():
        raise MonitorFailure(f"规则 {field} 不是有限数字。")
    return result


def decimal_text(value: Any) -> str:
    return format(decimal_value(value), "f")


def ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator).quantize(RATE_QUANTUM, ROUND_HALF_UP)


def rounded_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, ROUND_HALF_UP)


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def merged_mapping(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    return {**base, **{key: val for key, val in override.items() if val is not None}}


def parse_rules(value: dict[str, Any]) -> RuleSet:
    rules = RuleSet(
        target_acos=config_decimal(value.get("target_acos"), "-1", "target_acos"),
        min_orders=int(value.get("min_orders", 3)),
        scale_min_orders=int(value.get("scale_min_orders", 5)),
        min_clicks=int(value.get("min_clicks", 10)),
        min_spend=config_decimal(value.get("min_spend"), "5", "min_spend"),
        max_zero_order_spend=config_decimal(
            value.get("max_zero_order_spend"), "20", "max_zero_order_spend"
        ),
        high_acos_multiplier=config_decimal(
            value.get("high_acos_multiplier"), "1.2", "high_acos_multiplier"
        ),
        low_acos_multiplier=config_decimal(
            value.get("low_acos_multiplier"), "0.8", "low_acos_multiplier"
        ),
        bid_decrease_pct=config_decimal(
            value.get("bid_decrease_pct"), "0.1", "bid_decrease_pct"
        ),
        bid_increase_pct=config_decimal(
            value.get("bid_increase_pct"), "0.05", "bid_increase_pct"
        ),
        budget_increase_pct=config_decimal(
            value.get("budget_increase_pct"), "0.1", "budget_increase_pct"
        ),
        budget_utilization_threshold=config_decimal(
            value.get("budget_utilization_threshold"),
            "0.98",
            "budget_utilization_threshold",
        ),
        budget_utilization_days=int(value.get("budget_utilization_days", 3)),
        min_bid=config_decimal(value.get("min_bid"), "0.02", "min_bid"),
        max_bid=config_decimal(value.get("max_bid"), "10", "max_bid"),
        max_change_pct=config_decimal(
            value.get("max_change_pct"), "0.1", "max_change_pct"
        ),
        min_mature_days=int(value.get("min_mature_days", 7)),
        performance_ctr_threshold=config_decimal(
            value.get("performance_ctr_threshold"), "0.01", "performance_ctr_threshold"
        ),
        performance_cvr_threshold=config_decimal(
            value.get("performance_cvr_threshold"), "0.1", "performance_cvr_threshold"
        ),
        protected_campaign_ids=frozenset(
            str(item) for item in value.get("protected_campaign_ids", [])
        ),
        protected_target_ids=frozenset(
            str(item) for item in value.get("protected_target_ids", [])
        ),
    )
    if not Decimal("0") < rules.target_acos <= Decimal("10"):
        raise MonitorFailure("target_acos 必须大于 0 且不超过 10。")
    if min(rules.min_orders, rules.scale_min_orders, rules.min_clicks) < 0:
        raise MonitorFailure("订单和点击门槛不能为负数。")
    if min(rules.min_spend, rules.max_zero_order_spend, rules.min_bid) < 0:
        raise MonitorFailure("花费和最低竞价门槛不能为负数。")
    if rules.max_bid < rules.min_bid:
        raise MonitorFailure("max_bid 不能小于 min_bid。")
    if rules.high_acos_multiplier < 1:
        raise MonitorFailure("high_acos_multiplier 必须不小于 1。")
    if not Decimal("0") < rules.low_acos_multiplier <= 1:
        raise MonitorFailure("low_acos_multiplier 必须大于 0 且不超过 1。")
    changes = (
        rules.bid_decrease_pct,
        rules.bid_increase_pct,
        rules.budget_increase_pct,
        rules.max_change_pct,
    )
    if any(change < 0 or change > 1 for change in changes):
        raise MonitorFailure("调控比例必须在 0 到 1 之间。")
    if not Decimal("0") < rules.budget_utilization_threshold <= 1:
        raise MonitorFailure("budget_utilization_threshold 必须在 0 到 1 之间。")
    if not 1 <= rules.budget_utilization_days <= 7:
        raise MonitorFailure("budget_utilization_days 必须在 1 到 7 之间。")
    if not 1 <= rules.min_mature_days <= 60:
        raise MonitorFailure("min_mature_days 必须在 1 到 60 之间。")
    if not Decimal("0") <= rules.performance_ctr_threshold <= 1:
        raise MonitorFailure("performance_ctr_threshold 必须在 0 到 1 之间。")
    if not Decimal("0") <= rules.performance_cvr_threshold <= 1:
        raise MonitorFailure("performance_cvr_threshold 必须在 0 到 1 之间。")
    return rules


def load_monitor_config(
    path: Path,
    *,
    shop_overrides: Sequence[str] = (),
    currency_override: str | None = None,
    database_override: str | None = None,
    output_override: str | None = None,
    lookback_override: int | None = None,
    max_campaigns_override: int | None = None,
) -> MonitorConfig:
    if not path.exists():
        raise MonitorFailure(f"广告监控配置不存在：{path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise MonitorFailure("广告监控配置不是有效的 UTF-8 JSON。") from exc
    if not isinstance(raw, dict):
        raise MonitorFailure("广告监控配置顶层必须是对象。")

    collection = raw.get("collection") or {}
    storage = raw.get("storage") or {}
    default_rule_values = raw.get("rules") or {}
    default_rules = parse_rules(default_rule_values)
    raw_shops = list(raw.get("shops") or [])
    discover_shops = bool(collection.get("discover_shops", not raw_shops))
    if shop_overrides:
        discover_shops = False
        raw_shops = [
            {
                "shop_id": shop_id,
                "shop_name": shop_id,
                "currency": (currency_override or "UNKNOWN").upper(),
            }
            for shop_id in shop_overrides
        ]

    shops: list[ShopConfig] = []
    seen_shop_ids: set[str] = set()
    for raw_shop in raw_shops:
        if not isinstance(raw_shop, dict):
            raise MonitorFailure("shops 中的每一项都必须是对象。")
        shop_id = as_text(raw_shop.get("shop_id"))
        if not shop_id:
            raise MonitorFailure("shops 中存在空 shop_id。")
        if shop_id in seen_shop_ids:
            raise MonitorFailure(f"shop_id 重复：{shop_id}")
        seen_shop_ids.add(shop_id)
        shop_rules = parse_rules(
            merged_mapping(default_rule_values, raw_shop.get("rules") or {})
        )
        shops.append(
            ShopConfig(
                shop_id=shop_id,
                shop_name=as_text(raw_shop.get("shop_name")) or shop_id,
                currency=(as_text(raw_shop.get("currency")) or "UNKNOWN").upper(),
                campaign_ids=tuple(
                    str(item) for item in raw_shop.get("campaign_ids", [])
                ),
                rules=shop_rules,
                marketplace_id=as_text(raw_shop.get("marketplace_id")),
                region=as_text(raw_shop.get("region")),
            )
        )

    currencies = {shop.currency.upper() for shop in shops}
    if "UNKNOWN" in currencies:
        raise MonitorFailure("每个店铺都必须配置真实 currency，不能使用 UNKNOWN。")

    lookback_days = int(
        lookback_override
        if lookback_override is not None
        else collection.get("lookback_days", 14)
    )
    maturity_lag_days = int(collection.get("maturity_lag_days", 2))
    max_campaigns = int(
        max_campaigns_override
        if max_campaigns_override is not None
        else collection.get("max_campaigns_per_shop", 20)
    )
    if lookback_days < 1 or lookback_days > 60:
        raise MonitorFailure("lookback_days 必须在 1 到 60 之间。")
    if maturity_lag_days < 0 or maturity_lag_days > 14:
        raise MonitorFailure("maturity_lag_days 必须在 0 到 14 之间。")
    if max_campaigns < 0:
        raise MonitorFailure("max_campaigns_per_shop 不能小于 0；0 表示不限制。")
    listing_new_days = int(collection.get("listing_new_days", 90))
    if not 1 <= listing_new_days <= 365:
        raise MonitorFailure("listing_new_days 必须在 1 到 365 之间。")
    main_product = collection.get("main_product") or {}
    main_product_window_days = int(main_product.get("window_days", 7))
    main_product_min_orders = int(main_product.get("min_orders", 50))
    main_product_max_daily_cv = config_decimal(
        main_product.get("max_daily_cv"), "0.35", "main_product.max_daily_cv"
    )
    main_product_sudden_drop_ratio = config_decimal(
        main_product.get("sudden_drop_ratio"), "0.6", "main_product.sudden_drop_ratio"
    )
    if not 3 <= main_product_window_days <= 30:
        raise MonitorFailure("main_product.window_days 必须在 3 到 30 之间。")
    if main_product_min_orders < 1:
        raise MonitorFailure("main_product.min_orders 必须大于 0。")
    if not Decimal("0") <= main_product_max_daily_cv <= 3:
        raise MonitorFailure("main_product.max_daily_cv 必须在 0 到 3 之间。")
    if not Decimal("0") < main_product_sudden_drop_ratio <= 1:
        raise MonitorFailure("main_product.sudden_drop_ratio 必须在 0 到 1 之间。")
    report_batch_size = int(collection.get("report_shop_batch_size", 50))
    report_poll_seconds = int(collection.get("report_poll_seconds", 10))
    report_timeout_seconds = int(collection.get("report_timeout_seconds", 900))
    if not 1 <= report_batch_size <= 100:
        raise MonitorFailure("report_shop_batch_size 必须在 1 到 100 之间。")
    if not 5 <= report_poll_seconds <= 60:
        raise MonitorFailure("report_poll_seconds 必须在 5 到 60 之间。")
    if not 60 <= report_timeout_seconds <= 3600:
        raise MonitorFailure("report_timeout_seconds 必须在 60 到 3600 之间。")

    dashboard_value = as_text(storage.get("dashboard_payload_path"))

    return MonitorConfig(
        shops=tuple(shops),
        discover_shops=discover_shops,
        default_rules=default_rules,
        lookback_days=lookback_days,
        maturity_lag_days=maturity_lag_days,
        max_campaigns_per_shop=max_campaigns,
        pull_targets=bool(collection.get("pull_targets", True)),
        listing_new_days=listing_new_days,
        main_product_window_days=main_product_window_days,
        main_product_min_orders=main_product_min_orders,
        main_product_max_daily_cv=main_product_max_daily_cv,
        main_product_sudden_drop_ratio=main_product_sudden_drop_ratio,
        report_shop_batch_size=report_batch_size,
        report_poll_seconds=report_poll_seconds,
        report_timeout_seconds=report_timeout_seconds,
        database_path=resolve_path(
            database_override
            or storage.get("database_path", "data/sellfox_ads.sqlite3")
        ),
        output_dir=resolve_path(
            output_override or storage.get("output_dir", "outputs/ads_monitor")
        ),
        raw_report_dir=resolve_path(
            storage.get("raw_report_dir", "data/ads_report_cache")
        ),
        dashboard_payload_path=(
            resolve_path(dashboard_value) if dashboard_value else None
        ),
        node_path=as_text(storage.get("node_path")),
    )


def setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("SellfoxAdsMonitor")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)
    for log_path in (LOG_PATH, ROOT / "logs" / LOG_PATH.name):
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            rotating = RotatingFileHandler(
                log_path,
                maxBytes=2_000_000,
                backupCount=10,
                encoding="utf-8",
            )
        except OSError:
            continue
        rotating.setFormatter(formatter)
        logger.addHandler(rotating)
        break
    return logger


@contextmanager
def single_instance(wait_seconds: int = 0) -> Iterator[None]:
    if wait_seconds < 0:
        raise ValueError("广告监控锁等待秒数不能小于 0。")
    if os.name != "nt":
        yield
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    mutex = kernel32.CreateMutexW(None, True, r"Global\SellfoxAdsMonitor")
    if not mutex:
        raise ctypes.WinError()
    already_exists = kernel32.GetLastError() == 183
    owns_mutex = not already_exists
    if already_exists:
        if wait_seconds <= 0:
            kernel32.CloseHandle(mutex)
            raise MonitorFailure("已有广告监控任务正在运行，本次安全退出。")
        wait_milliseconds = min(wait_seconds * 1000, 0xFFFFFFFE)
        wait_result = kernel32.WaitForSingleObject(mutex, wait_milliseconds)
        if wait_result in (0x00000000, 0x00000080):
            owns_mutex = True
        elif wait_result == 0x00000102:
            kernel32.CloseHandle(mutex)
            raise MonitorFailure(
                f"等待现有广告监控任务 {wait_seconds} 秒后仍未释放，本次安全退出。"
            )
        else:
            kernel32.CloseHandle(mutex)
            raise ctypes.WinError()
    try:
        yield
    finally:
        if owns_mutex:
            kernel32.ReleaseMutex(mutex)
        kernel32.CloseHandle(mutex)


class SellfoxAdsClient(SellfoxClient):
    """Thin ad-specific wrapper over the existing OAuth and signature client."""

    _shared_token_lock = threading.Lock()
    _shared_access_tokens: dict[str, str] = {}

    def __init__(self, client_id: str, client_secret: str, logger: logging.Logger):
        config = Config(client_id, client_secret, "", "", "", "")
        super().__init__(config, logger)
        self.session.headers["User-Agent"] = "SellfoxAdsMonitor/1.0"

    def get_token(self) -> str:
        if self._access_token:
            return self._access_token
        cache_key = self.config.client_id
        with self._shared_token_lock:
            shared_token = self._shared_access_tokens.get(cache_key, "")
            if not shared_token:
                shared_token = super().get_token()
                self._shared_access_tokens[cache_key] = shared_token
            self._access_token = shared_token
        return self._access_token

    def post_data(
        self,
        path: str,
        body: dict[str, Any],
        purpose: str,
    ) -> dict[str, Any]:
        for attempt in range(1, 9):
            self._throttle()
            try:
                try:
                    payload = self._request_json(
                        "POST",
                        API_BASE_URL + path,
                        params=self._signed_params(path),
                        body=body,
                        purpose=purpose,
                    )
                except ImportFailure as exc:
                    raise MonitorFailure(str(exc)) from exc
            finally:
                self._last_order_call = time.monotonic()
            code = payload.get("code")
            if str(code) == "0":
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise MonitorFailure(f"{purpose}的 data 格式异常。")
                return data
            if str(code) == "40019" and attempt < 8:
                delay = min(60, 5 * (2 ** (attempt - 1)))
                self.logger.warning("赛狐接口限流，%s 秒后重试。", delay)
                time.sleep(delay)
                continue
            raise MonitorFailure(
                f"{purpose}失败：code={code}，{as_text(payload.get('msg'))}"
            )
        raise MonitorFailure(f"{purpose}多次触发限流。")


def load_api_credentials() -> tuple[str, str]:
    try:
        stored = load_encrypted_config(required=False)
    except ImportFailure as exc:
        stored = {}
        stored_error = str(exc)
    else:
        stored_error = ""
    client_id = os.environ.get("SELLFOX_CLIENT_ID") or stored.get("client_id", "")
    client_secret = os.environ.get("SELLFOX_CLIENT_SECRET") or stored.get(
        "client_secret", ""
    )
    if not client_id or not client_secret:
        suffix = f"（本机加密配置读取失败：{stored_error}）" if stored_error else ""
        raise MonitorFailure(
            "缺少赛狐 API 凭据。请先运行 sellfox_import.py --configure，"
            "或设置 SELLFOX_CLIENT_ID/SELLFOX_CLIENT_SECRET。" + suffix
        )
    return str(client_id), str(client_secret)


def fetch_cursor_items(
    client: SellfoxAdsClient,
    path: str,
    body: dict[str, Any],
    purpose: str,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    next_token = ""
    seen_tokens: set[str] = set()
    pages = 0
    while True:
        request_body = dict(body)
        if next_token:
            request_body["nextToken"] = next_token
        data = client.post_data(path, request_body, purpose)
        pages += 1
        page_items = data.get("itemList")
        if not isinstance(page_items, list):
            raise MonitorFailure(f"{purpose}的 itemList 格式异常。")
        if any(not isinstance(item, dict) for item in page_items):
            raise MonitorFailure(f"{purpose}的 itemList 包含非对象记录。")
        items.extend(page_items)
        next_token = as_text(data.get("nextToken"))
        if not next_token:
            return items, pages
        if next_token in seen_tokens:
            raise MonitorFailure(f"{purpose}出现重复 nextToken，已中止分页。")
        seen_tokens.add(next_token)


def fetch_page_items(
    client: SellfoxAdsClient,
    path: str,
    body: dict[str, Any],
    purpose: str,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    page_no = 1
    while True:
        request_body = {**body, "pageNo": str(page_no)}
        data = client.post_data(path, request_body, f"{purpose}第 {page_no} 页")
        page_items = data.get("rows")
        if not isinstance(page_items, list):
            raise MonitorFailure(f"{purpose}的 rows 格式异常。")
        if any(not isinstance(item, dict) for item in page_items):
            raise MonitorFailure(f"{purpose}的 rows 包含非对象记录。")
        items.extend(page_items)
        try:
            total_page = int(data.get("totalPage") or 1)
            total_size = int(data.get("totalSize") or len(items))
        except (TypeError, ValueError) as exc:
            raise MonitorFailure(f"{purpose}的分页字段格式异常。") from exc
        if total_page < page_no or total_page > 10000 or total_size < len(items):
            raise MonitorFailure(f"{purpose}的分页边界异常。")
        if page_no >= total_page:
            return items, page_no
        if not page_items:
            raise MonitorFailure(f"{purpose}在未到末页时返回空 rows。")
        page_no += 1


def discover_authorized_shops(
    client: SellfoxAdsClient,
    config: MonitorConfig,
) -> tuple[ShopConfig, ...]:
    rows: list[dict[str, Any]] = []
    page_no = 1
    while True:
        data = client.post_data(
            SHOP_LIST_PATH,
            {"pageNo": str(page_no), "pageSize": "100"},
            f"读取店铺列表第 {page_no} 页",
        )
        page_rows = data.get("rows")
        if not isinstance(page_rows, list) or any(
            not isinstance(item, dict) for item in page_rows
        ):
            raise MonitorFailure("店铺列表 rows 格式异常。")
        rows.extend(page_rows)
        try:
            total_pages = int(data.get("totalPage") or page_no)
        except (TypeError, ValueError) as exc:
            raise MonitorFailure("店铺列表 totalPage 格式异常。") from exc
        if total_pages < page_no or total_pages > 10000:
            raise MonitorFailure("店铺列表 totalPage 超出安全范围。")
        if page_no >= total_pages:
            break
        page_no += 1

    overrides = {shop.shop_id: shop for shop in config.shops}
    discovered: list[ShopConfig] = []
    seen_ids: set[str] = set()
    unknown_marketplaces: set[str] = set()
    for row in rows:
        if as_text(row.get("adStatus")).lower() not in {"auth", "已授权"}:
            continue
        if as_text(row.get("status")) != "0":
            continue
        shop_id = as_text(row.get("id"))
        marketplace_id = as_text(row.get("marketplaceId"))
        if not shop_id:
            raise MonitorFailure("已授权店铺缺少 id。")
        if shop_id in seen_ids:
            raise MonitorFailure(f"店铺列表返回重复 id：{shop_id}")
        seen_ids.add(shop_id)
        currency = MARKETPLACE_CURRENCIES.get(marketplace_id)
        if not currency:
            unknown_marketplaces.add(marketplace_id or "<empty>")
            continue
        override = overrides.get(shop_id)
        if override and override.currency != currency:
            raise MonitorFailure(
                f"店铺 {shop_id} 配置币种 {override.currency} 与站点币种 {currency} 不一致。"
            )
        discovered.append(
            ShopConfig(
                shop_id=shop_id,
                shop_name=(
                    override.shop_name
                    if override and override.shop_name != shop_id
                    else as_text(row.get("name")) or shop_id
                ),
                currency=currency,
                campaign_ids=override.campaign_ids if override else (),
                rules=override.rules if override else config.default_rules,
                marketplace_id=marketplace_id,
                region=as_text(row.get("region")),
            )
        )
    if unknown_marketplaces:
        raise MonitorFailure(
            "发现无法确定币种的已授权 Amazon 站点："
            + ", ".join(sorted(unknown_marketplaces))
        )
    if not discovered:
        raise MonitorFailure("没有找到广告已授权且状态正常的 Amazon 店铺。")
    normalized_names = [shop.shop_name.strip().casefold() for shop in discovered]
    if len(normalized_names) != len(set(normalized_names)):
        raise MonitorFailure("已授权店铺存在重名，无法安全归属批量广告报表。")
    return tuple(sorted(discovered, key=lambda item: (item.shop_name, item.shop_id)))


def resolve_discovered_shops(
    config: MonitorConfig,
    logger: logging.Logger,
) -> MonitorConfig:
    if not config.discover_shops:
        return config
    client_id, client_secret = load_api_credentials()
    client = SellfoxAdsClient(client_id, client_secret, logger)
    try:
        shops = discover_authorized_shops(client, config)
    finally:
        client.close()
    logger.info("已发现 %s 个广告授权正常店铺。", len(shops))
    return replace(config, shops=shops)


def normalize_hourly_row(
    row: dict[str, Any],
    *,
    aggregation_type: str,
    shop_id: str,
    report_date: date,
    campaign_id: str,
    run_id: str,
    ingested_at: str,
) -> dict[str, Any]:
    if aggregation_type not in {"campaign", "target"}:
        raise DataQualityFailure(f"未知小时报告聚合类型：{aggregation_type}")
    actual_date = as_text(row.get("date")) or report_date.isoformat()
    try:
        date.fromisoformat(actual_date)
        hour_value = report_decimal(row.get("hour"), "hour")
    except (ValueError, TypeError) as exc:
        raise DataQualityFailure("小时报告日期或小时格式异常。") from exc
    if actual_date != report_date.isoformat():
        raise DataQualityFailure("小时报告日期与请求日期不一致。")
    if hour_value != hour_value.to_integral_value():
        raise DataQualityFailure("小时报告 hour 不是整数。")
    hour = int(hour_value)
    if hour < 0 or hour > 23:
        raise DataQualityFailure(f"小时报告 hour 超出 0-23：{hour}")

    metrics = {
        "spend": report_decimal(row.get("costs"), "costs"),
        "clicks": report_decimal(row.get("clicks"), "clicks"),
        "impressions": report_decimal(row.get("impressions"), "impressions"),
        "orders": report_decimal(row.get("orders"), "orders"),
        "sales": report_decimal(row.get("sales"), "sales"),
        "units": report_decimal(row.get("units"), "units"),
    }
    if any(value < 0 for value in metrics.values()):
        raise DataQualityFailure("小时报告出现负数核心指标。")
    if metrics["clicks"] > metrics["impressions"]:
        raise DataQualityFailure("小时报告 clicks 大于 impressions。")

    actual_shop_id = as_text(row.get("shopId")) or shop_id
    actual_campaign_id = as_text(row.get("campaignId")) or campaign_id
    if actual_shop_id != shop_id or actual_campaign_id != campaign_id:
        raise DataQualityFailure("小时报告店铺或活动与请求范围不一致。")
    targeting = as_text(row.get("targeting"))
    match_type = as_text(row.get("matchType"))
    ad_id = as_text(row.get("adId"))
    ad_group_id = as_text(row.get("groupId"))
    targeting_id = as_text(row.get("targetingId"))
    if aggregation_type == "target" and not targeting_id:
        if not any((targeting, match_type, ad_id)):
            raise DataQualityFailure("投放小时报告缺少可识别的投放对象。")
        targeting_id = f"text:{ad_group_id}:{targeting}:{match_type}:{ad_id}"

    return {
        "run_id": run_id,
        "aggregation_type": aggregation_type,
        "shop_id": actual_shop_id,
        "report_date": actual_date,
        "report_hour": hour,
        "campaign_id": actual_campaign_id,
        "ad_group_id": ad_group_id,
        "ad_id": ad_id,
        "targeting_id": targeting_id,
        "targeting": targeting,
        "match_type": match_type,
        "placement": as_text(row.get("placement")),
        "msku": as_text(row.get("msku")),
        "asin": as_text(row.get("asin")),
        **{key: decimal_text(value) for key, value in metrics.items()},
        "ingested_at": ingested_at,
        "raw_json": json.dumps(row, ensure_ascii=False, separators=(",", ":")),
    }


SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_snapshot (
  run_id TEXT NOT NULL,
  snapshot_at TEXT NOT NULL,
  shop_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL,
  portfolio_id TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT '',
  serving_status TEXT NOT NULL DEFAULT '',
  targeting_type TEXT NOT NULL DEFAULT '',
  budget TEXT NOT NULL DEFAULT '0',
  strategy TEXT NOT NULL DEFAULT '',
  adjustments TEXT NOT NULL DEFAULT '',
  start_date TEXT NOT NULL DEFAULT '',
  end_date TEXT NOT NULL DEFAULT '',
  creation_date TEXT NOT NULL DEFAULT '',
  last_updated_date TEXT NOT NULL DEFAULT '',
  raw_json TEXT NOT NULL,
  PRIMARY KEY (run_id, shop_id, campaign_id)
);
CREATE INDEX IF NOT EXISTS ix_campaign_snapshot_lookup
ON campaign_snapshot (shop_id, campaign_id, snapshot_at);

CREATE TABLE IF NOT EXISTS keyword_snapshot (
  run_id TEXT NOT NULL,
  snapshot_at TEXT NOT NULL,
  shop_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL DEFAULT '',
  ad_group_id TEXT NOT NULL DEFAULT '',
  keyword_id TEXT NOT NULL,
  keyword_text TEXT NOT NULL DEFAULT '',
  bid TEXT NOT NULL DEFAULT '0',
  match_type TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT '',
  serving_status TEXT NOT NULL DEFAULT '',
  raw_json TEXT NOT NULL,
  PRIMARY KEY (run_id, shop_id, keyword_id)
);
CREATE INDEX IF NOT EXISTS ix_keyword_snapshot_lookup
ON keyword_snapshot (shop_id, keyword_id, snapshot_at);

CREATE TABLE IF NOT EXISTS target_snapshot (
  run_id TEXT NOT NULL,
  snapshot_at TEXT NOT NULL,
  shop_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL DEFAULT '',
  ad_group_id TEXT NOT NULL DEFAULT '',
  target_id TEXT NOT NULL,
  bid TEXT NOT NULL DEFAULT '0',
  state TEXT NOT NULL DEFAULT '',
  serving_status TEXT NOT NULL DEFAULT '',
  expression_type TEXT NOT NULL DEFAULT '',
  expression TEXT NOT NULL DEFAULT '',
  resolved_expression TEXT NOT NULL DEFAULT '',
  raw_json TEXT NOT NULL,
  PRIMARY KEY (run_id, shop_id, campaign_id, ad_group_id, target_id)
);
CREATE INDEX IF NOT EXISTS ix_target_snapshot_lookup
ON target_snapshot (shop_id, target_id, snapshot_at);

CREATE TABLE IF NOT EXISTS ad_product_snapshot (
  run_id TEXT NOT NULL,
  snapshot_at TEXT NOT NULL,
  source_row INTEGER NOT NULL,
  shop_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL DEFAULT '',
  group_id TEXT NOT NULL DEFAULT '',
  ad_id TEXT NOT NULL DEFAULT '',
  asin TEXT NOT NULL DEFAULT '',
  sku TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT '',
  serving_status TEXT NOT NULL DEFAULT '',
  raw_json TEXT NOT NULL,
  PRIMARY KEY (run_id, shop_id, source_row)
);
CREATE INDEX IF NOT EXISTS ix_ad_product_snapshot_lookup
ON ad_product_snapshot (run_id, shop_id, campaign_id, asin, sku);

CREATE TABLE IF NOT EXISTS online_product_snapshot (
  run_id TEXT NOT NULL,
  snapshot_at TEXT NOT NULL,
  source_row INTEGER NOT NULL,
  shop_id TEXT NOT NULL,
  marketplace_id TEXT NOT NULL DEFAULT '',
  product_id TEXT NOT NULL DEFAULT '',
  asin TEXT NOT NULL DEFAULT '',
  sku TEXT NOT NULL DEFAULT '',
  open_date TEXT NOT NULL DEFAULT '',
  online_status TEXT NOT NULL DEFAULT '',
  last_sync_time TEXT NOT NULL DEFAULT '',
  first_order_date TEXT NOT NULL DEFAULT '',
  first_sale_date TEXT NOT NULL DEFAULT '',
  raw_json TEXT NOT NULL,
  PRIMARY KEY (run_id, shop_id, source_row)
);
CREATE INDEX IF NOT EXISTS ix_online_product_snapshot_lookup
ON online_product_snapshot (run_id, shop_id, asin, sku);

CREATE TABLE IF NOT EXISTS hourly_fact_history (
  run_id TEXT NOT NULL,
  aggregation_type TEXT NOT NULL,
  shop_id TEXT NOT NULL,
  report_date TEXT NOT NULL,
  report_hour INTEGER NOT NULL,
  campaign_id TEXT NOT NULL,
  ad_group_id TEXT NOT NULL DEFAULT '',
  ad_id TEXT NOT NULL DEFAULT '',
  targeting_id TEXT NOT NULL DEFAULT '',
  targeting TEXT NOT NULL DEFAULT '',
  match_type TEXT NOT NULL DEFAULT '',
  placement TEXT NOT NULL DEFAULT '',
  msku TEXT NOT NULL DEFAULT '',
  asin TEXT NOT NULL DEFAULT '',
  spend TEXT NOT NULL DEFAULT '0',
  clicks TEXT NOT NULL DEFAULT '0',
  impressions TEXT NOT NULL DEFAULT '0',
  orders TEXT NOT NULL DEFAULT '0',
  sales TEXT NOT NULL DEFAULT '0',
  units TEXT NOT NULL DEFAULT '0',
  ingested_at TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  PRIMARY KEY (
    run_id, aggregation_type, shop_id, report_date, report_hour,
    campaign_id, ad_group_id, ad_id, targeting_id, placement
  )
);
CREATE INDEX IF NOT EXISTS ix_hourly_fact_window
ON hourly_fact_history (run_id, aggregation_type, report_date, shop_id, campaign_id);

CREATE TABLE IF NOT EXISTS recommendation (
  run_id TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  shop_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_key TEXT NOT NULL,
  campaign_id TEXT NOT NULL DEFAULT '',
  campaign_name TEXT NOT NULL DEFAULT '',
  target_id TEXT NOT NULL DEFAULT '',
  target_text TEXT NOT NULL DEFAULT '',
  match_type TEXT NOT NULL DEFAULT '',
  action_code TEXT NOT NULL,
  priority TEXT NOT NULL,
  current_value TEXT NOT NULL DEFAULT '',
  proposed_value TEXT NOT NULL DEFAULT '',
  change_pct TEXT NOT NULL DEFAULT '',
  spend TEXT NOT NULL DEFAULT '0',
  sales TEXT NOT NULL DEFAULT '0',
  orders TEXT NOT NULL DEFAULT '0',
  clicks TEXT NOT NULL DEFAULT '0',
  acos TEXT NOT NULL DEFAULT '',
  target_acos TEXT NOT NULL DEFAULT '',
  rule_id TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  reason TEXT NOT NULL,
  data_status TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT '待审核',
  PRIMARY KEY (run_id, entity_key, rule_id)
);

CREATE TABLE IF NOT EXISTS sync_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  logged_at TEXT NOT NULL,
  shop_id TEXT NOT NULL DEFAULT '',
  endpoint TEXT NOT NULL,
  report_date TEXT NOT NULL DEFAULT '',
  campaign_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  message TEXT NOT NULL DEFAULT ''
);
"""


@contextmanager
def connect_store(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA)
    try:
        yield connection
    finally:
        connection.close()


RUN_TABLES = (
    "campaign_snapshot",
    "keyword_snapshot",
    "target_snapshot",
    "ad_product_snapshot",
    "online_product_snapshot",
    "hourly_fact_history",
    "recommendation",
    "sync_log",
)


def reset_run(connection: sqlite3.Connection, run_id: str) -> None:
    for table in RUN_TABLES:
        connection.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))
    connection.commit()


def promote_run(
    connection: sqlite3.Connection,
    attempt_run_id: str,
    run_id: str,
) -> None:
    if attempt_run_id == run_id:
        return
    with connection:                                                   # Atomic swap.
        for table in RUN_TABLES:
            connection.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))
            connection.execute(
                f"UPDATE {table} SET run_id = ? WHERE run_id = ?",
                (run_id, attempt_run_id),
            )


def insert_campaigns(
    connection: sqlite3.Connection,
    run_id: str,
    snapshot_at: str,
    records: Iterable[dict[str, Any]],
    default_shop_id: str = "",
) -> int:
    rows = []
    for item in records:
        source_shop_id = as_text(item.get("shopId"))
        if source_shop_id and default_shop_id and source_shop_id != default_shop_id:
            raise DataQualityFailure("广告活动返回了请求范围外的店铺。")
        shop_id = source_shop_id or default_shop_id
        campaign_id = as_text(item.get("campaignId"))
        if not shop_id or not campaign_id:
            raise DataQualityFailure("广告活动缺少 shopId 或 campaignId。")
        rows.append(
            (
                run_id,
                snapshot_at,
                shop_id,
                campaign_id,
                as_text(item.get("portfolioId")),
                as_text(item.get("name")),
                as_text(item.get("state")).lower(),
                as_text(item.get("servingStatus")),
                as_text(item.get("targetingType")),
                decimal_text(item.get("budget")),
                as_text(item.get("strategy")),
                as_text(item.get("adjustments")),
                as_text(item.get("startDate")),
                as_text(item.get("endDate")),
                as_text(item.get("creationDate")),
                as_text(item.get("lastUpdatedDate")),
                json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            )
        )
    connection.executemany(
        """
        INSERT OR REPLACE INTO campaign_snapshot VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def insert_keywords(
    connection: sqlite3.Connection,
    run_id: str,
    snapshot_at: str,
    records: Iterable[dict[str, Any]],
    default_shop_id: str = "",
) -> int:
    rows = []
    for item in records:
        source_shop_id = as_text(item.get("shopId"))
        if source_shop_id and default_shop_id and source_shop_id != default_shop_id:
            raise DataQualityFailure("SP 关键词返回了请求范围外的店铺。")
        shop_id = source_shop_id or default_shop_id
        campaign_id = as_text(item.get("campaignId"))
        keyword_id = as_text(item.get("keywordId"))
        if not shop_id or not campaign_id or not keyword_id:
            raise DataQualityFailure("SP 关键词缺少 shopId、campaignId 或 keywordId。")
        rows.append(
            (
                run_id,
                snapshot_at,
                shop_id,
                campaign_id,
                as_text(item.get("groupId")),
                keyword_id,
                as_text(item.get("keywordText")),
                decimal_text(item.get("bid")),
                as_text(item.get("matchType")),
                as_text(item.get("state")).lower(),
                as_text(item.get("servingStatus")),
                json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            )
        )
    connection.executemany(
        """
        INSERT OR REPLACE INTO keyword_snapshot VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def insert_product_targets(
    connection: sqlite3.Connection,
    run_id: str,
    snapshot_at: str,
    records: Iterable[dict[str, Any]],
    default_shop_id: str = "",
) -> int:
    rows = []
    for item in records:
        source_shop_id = as_text(item.get("shopId"))
        if source_shop_id and default_shop_id and source_shop_id != default_shop_id:
            raise DataQualityFailure("SP 商品投放返回了请求范围外的店铺。")
        shop_id = source_shop_id or default_shop_id
        campaign_id = as_text(item.get("campaignId"))
        target_id = as_text(item.get("targetId"))
        if not shop_id or not campaign_id or not target_id:
            raise DataQualityFailure("SP 商品投放缺少 shopId、campaignId 或 targetId。")
        rows.append(
            (
                run_id,
                snapshot_at,
                shop_id,
                campaign_id,
                as_text(item.get("groupId")),
                target_id,
                decimal_text(item.get("bid")),
                as_text(item.get("state")).lower(),
                as_text(item.get("servingStatus")),
                as_text(item.get("expressionType")),
                as_text(item.get("expression")),
                as_text(item.get("resolvedExpression")),
                json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            )
        )
    connection.executemany(
        """
        INSERT OR REPLACE INTO target_snapshot VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def insert_ad_products(
    connection: sqlite3.Connection,
    run_id: str,
    snapshot_at: str,
    records: Iterable[dict[str, Any]],
    default_shop_id: str = "",
) -> int:
    materialized = sorted(
        records,
        key=lambda item: (
            as_text(item.get("campaignId")),
            as_text(item.get("groupId")),
            as_text(item.get("adId")),
            as_text(item.get("asin")).upper(),
            as_text(item.get("sku")),
            json.dumps(item, ensure_ascii=False, sort_keys=True),
        ),
    )
    rows = []
    for source_row, item in enumerate(materialized):
        source_shop_id = as_text(item.get("shopId"))
        if source_shop_id and default_shop_id and source_shop_id != default_shop_id:
            raise DataQualityFailure("SP 广告商品返回了请求范围外的店铺。")
        shop_id = source_shop_id or default_shop_id
        if not shop_id:
            raise DataQualityFailure("SP 广告商品缺少 shopId。")
        rows.append(
            (
                run_id,
                snapshot_at,
                source_row,
                shop_id,
                as_text(item.get("campaignId")),
                as_text(item.get("groupId")),
                as_text(item.get("adId")),
                as_text(item.get("asin")).upper(),
                as_text(item.get("sku")),
                as_text(item.get("state")).lower(),
                as_text(item.get("servingStatus")),
                json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            )
        )
    connection.executemany(
        """
        INSERT OR REPLACE INTO ad_product_snapshot VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def insert_online_products(
    connection: sqlite3.Connection,
    run_id: str,
    snapshot_at: str,
    records: Iterable[dict[str, Any]],
    default_shop_id: str = "",
    expected_marketplace_id: str = "",
) -> int:
    materialized = sorted(
        records,
        key=lambda item: (
            as_text(item.get("asin")).upper(),
            as_text(item.get("sku")),
            as_text(item.get("id")),
            json.dumps(item, ensure_ascii=False, sort_keys=True),
        ),
    )
    rows = []
    for source_row, item in enumerate(materialized):
        source_shop_id = as_text(item.get("shopId"))
        if source_shop_id and default_shop_id and source_shop_id != default_shop_id:
            raise DataQualityFailure("在线产品 V2 返回了请求范围外的店铺。")
        shop_id = source_shop_id or default_shop_id
        if not shop_id:
            raise DataQualityFailure("在线产品 V2 缺少 shopId。")
        marketplace_id = as_text(item.get("marketplaceId"))
        if (
            marketplace_id
            and expected_marketplace_id
            and marketplace_id != expected_marketplace_id
        ):
            raise DataQualityFailure("在线产品 V2 的 marketplaceId 与店铺不一致。")
        rows.append(
            (
                run_id,
                snapshot_at,
                source_row,
                shop_id,
                marketplace_id or expected_marketplace_id,
                as_text(item.get("id")),
                as_text(item.get("asin")).upper(),
                as_text(item.get("sku")),
                as_text(item.get("openDate")),
                as_text(item.get("onlineStatus")),
                as_text(item.get("lastSyncTime")),
                as_text(item.get("firstOrderDate")),
                as_text(item.get("firstSaleDate")),
                json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            )
        )
    connection.executemany(
        """
        INSERT OR REPLACE INTO online_product_snapshot VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


HOURLY_COLUMNS = (
    "run_id",
    "aggregation_type",
    "shop_id",
    "report_date",
    "report_hour",
    "campaign_id",
    "ad_group_id",
    "ad_id",
    "targeting_id",
    "targeting",
    "match_type",
    "placement",
    "msku",
    "asin",
    "spend",
    "clicks",
    "impressions",
    "orders",
    "sales",
    "units",
    "ingested_at",
    "raw_json",
)


def insert_hourly(
    connection: sqlite3.Connection,
    rows: Iterable[dict[str, Any]],
) -> int:
    materialized = list(rows)
    placeholders = ",".join("?" for _ in HOURLY_COLUMNS)
    connection.executemany(
        f"INSERT OR REPLACE INTO hourly_fact_history VALUES ({placeholders})",
        [tuple(row[column] for column in HOURLY_COLUMNS) for row in materialized],
    )
    return len(materialized)


def log_sync(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    shop_id: str,
    endpoint: str,
    status: str,
    row_count: int = 0,
    report_date: str = "",
    campaign_id: str = "",
    message: str = "",
) -> None:
    connection.execute(
        """
        INSERT INTO sync_log
        (run_id, logged_at, shop_id, endpoint, report_date, campaign_id,
         status, row_count, message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            datetime.now().astimezone().isoformat(timespec="seconds"),
            shop_id,
            endpoint,
            report_date,
            campaign_id,
            status,
            row_count,
            message[:500],
        ),
    )


def date_window(as_of: date, config: MonitorConfig) -> list[date]:
    end = as_of - timedelta(days=config.maturity_lag_days)
    start = end - timedelta(days=config.lookback_days - 1)
    return [start + timedelta(days=offset) for offset in range(config.lookback_days)]


def campaign_sort_key(item: dict[str, Any]) -> tuple[int, Decimal, str]:
    enabled_rank = 0 if as_text(item.get("state")) == "enabled" else 1
    return enabled_rank, -decimal_value(item.get("budget")), as_text(
        item.get("campaignId")
    )


def select_campaigns(
    campaigns: Sequence[dict[str, Any]],
    shop: ShopConfig,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    selected = [
        item
        for item in campaigns
        if as_text(item.get("state")) == "enabled"
    ]
    if shop.campaign_ids:
        wanted = set(shop.campaign_ids)
        selected = [
            item
            for item in selected
            if as_text(item.get("campaignId")) in wanted
        ]
    selected.sort(key=campaign_sort_key)
    if limit == 0:
        return selected, 0
    return selected[:limit], max(0, len(selected) - limit)


def serving_status_blocks(value: Any) -> bool:
    status = as_text(value).lower()
    blocked_tokens = (
        "paused",
        "archived",
        "disabled",
        "ended",
        "terminated",
        "ineligible",
        "suspended",
        "rejected",
    )
    return bool(status) and any(token in status for token in blocked_tokens)


def load_base_endpoint_cache(
    path: Path,
    shops: Sequence[ShopConfig],
    endpoint: str,
) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    shop_map = {shop.shop_id: shop for shop in shops}
    if payload.get("endpoint") != endpoint:
        return None
    if set(payload.get("shop_ids") or []) != set(shop_map):
        return None
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return None
    results = []
    for raw in raw_results:
        shop = shop_map.get(as_text(raw.get("shop_id"))) if isinstance(raw, dict) else None
        items = raw.get("items") if isinstance(raw, dict) else None
        if not shop or not isinstance(items, list):
            return None
        results.append(
            {
                "shop": shop,
                "items": items,
                "pages": int(raw.get("pages") or 0),
                "error": as_text(raw.get("error")),
            }
        )
    return results if len(results) == len(shops) else None


def write_base_endpoint_cache(
    path: Path,
    endpoint: str,
    results: Sequence[dict[str, Any]],
) -> None:
    payload = {
        "version": 1,
        "endpoint": endpoint,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "shop_ids": [result["shop"].shop_id for result in results],
        "results": [
            {
                "shop_id": result["shop"].shop_id,
                "pages": result["pages"],
                "items": result["items"],
                "error": result["error"],
            }
            for result in results
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def fetch_online_products_for_shops(
    shops: Sequence[ShopConfig],
    *,
    client_id: str,
    client_secret: str,
    logger: logging.Logger,
    cache_path: Path | None = None,
) -> list[dict[str, Any]]:
    cached = (
        load_base_endpoint_cache(cache_path, shops, ONLINE_PRODUCT_PATH)
        if cache_path
        else None
    )
    if cached is not None and not any(result["error"] for result in cached):
        logger.info("使用当日在线产品 V2 基础数据缓存。")
        return cached
    client = SellfoxAdsClient(client_id, client_secret, logger)
    try:
        try:
            items, pages = fetch_page_items(
                client,
                ONLINE_PRODUCT_PATH,
                {
                    "onlineStatusList": ["active", "inActive"],
                    "pageSize": "200",
                },
                "读取在线产品 V2",
            )
        except MonitorFailure as exc:
            results = [
                {"shop": shop, "items": [], "pages": 0, "error": str(exc)}
                for shop in shops
            ]
        else:
            shops_by_id = {shop.shop_id: shop for shop in shops}
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            ignored = 0
            for item in items:
                shop_id = as_text(item.get("shopId"))
                if shop_id not in shops_by_id:
                    ignored += 1
                    continue
                grouped[shop_id].append(item)
            if ignored:
                logger.warning("在线产品 V2 忽略了 %s 条非目标店铺记录。", ignored)
            results = [
                {
                    "shop": shop,
                    "items": grouped.get(shop.shop_id, []),
                    "pages": pages,
                    "error": "",
                }
                for shop in shops
            ]
    finally:
        client.close()
    if cache_path:
        try:
            write_base_endpoint_cache(cache_path, ONLINE_PRODUCT_PATH, results)
        except OSError:
            logger.warning("无法写入在线产品 V2 基础数据缓存。")
    return results


def fetch_base_endpoint(
    shops: Sequence[ShopConfig],
    *,
    client_id: str,
    client_secret: str,
    path: str,
    label: str,
    logger: logging.Logger,
    cache_path: Path | None = None,
    pagination: str = "cursor",
) -> list[dict[str, Any]]:
    if pagination not in {"cursor", "page"}:
        raise MonitorFailure(f"未知基础数据分页方式：{pagination}")
    if pagination == "page":
        if path != ONLINE_PRODUCT_PATH:
            raise MonitorFailure(f"分页基础数据端点未登记：{path}")
        return fetch_online_products_for_shops(
            shops,
            client_id=client_id,
            client_secret=client_secret,
            logger=logger,
            cache_path=cache_path,
        )
    cached = (
        load_base_endpoint_cache(cache_path, shops, path)
        if cache_path
        else None
    )
    if cached is not None and not any(result["error"] for result in cached):
        logger.info("使用当日 %s 基础数据缓存。", label)
        return cached
    cached_by_shop = {
        result["shop"].shop_id: result
        for result in (cached or [])
        if not result["error"]
    }
    pending_shops = [shop for shop in shops if shop.shop_id not in cached_by_shop]
    if cached_by_shop:
        logger.info(
            "使用 %s 的 %s 个缓存店铺，仅重试 %s 个失败店铺。",
            label,
            len(cached_by_shop),
            len(pending_shops),
        )
    client = SellfoxAdsClient(client_id, client_secret, logger)
    refreshed: dict[str, dict[str, Any]] = {}
    try:
        for shop in pending_shops:
            try:
                if pagination == "page":
                    items, pages = fetch_page_items(
                        client,
                        path,
                        {
                            "shopIdList": [shop.shop_id],
                            "onlineStatusList": ["active"],
                            "pageSize": "100",
                        },
                        f"读取 {shop.shop_name} 的 {label}",
                    )
                else:
                    items, pages = fetch_cursor_items(
                        client,
                        path,
                        {
                            "shopId": shop.shop_id,
                            "state": "enabled",
                            "pageSize": "1000",
                        },
                        f"读取 {shop.shop_name} 的 {label}",
                    )
                refreshed[shop.shop_id] = {
                    "shop": shop,
                    "items": items,
                    "pages": pages,
                    "error": "",
                }
            except MonitorFailure as exc:
                refreshed[shop.shop_id] = {
                    "shop": shop,
                    "items": [],
                    "pages": 0,
                    "error": str(exc),
                }
    finally:
        client.close()
    results = [
        cached_by_shop.get(shop.shop_id) or refreshed[shop.shop_id]
        for shop in shops
    ]
    if cache_path:
        try:
            write_base_endpoint_cache(cache_path, path, results)
        except OSError:
            logger.warning("无法写入 %s 基础数据缓存。", label)
    return results


def parse_listing_date(value: Any) -> date | None:
    text = as_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00").replace(" ", "T")).date()
    except ValueError:
        return None


def listing_stage_for(
    open_date: Any,
    *,
    as_of: date,
    new_days: int,
) -> tuple[int | None, str]:
    opened = parse_listing_date(open_date)
    if opened is None:
        return None, "unknown"
    age = (as_of - opened).days
    if age < 0:
        return None, "unknown"
    return age, "new" if age <= new_days else "established"


def campaign_listing_stage(products: Sequence[Mapping[str, Any]]) -> str:
    stages = {as_text(row.get("listing_stage")) for row in products}
    if not stages or "unknown" in stages:
        return "unknown"
    if stages == {"new"}:
        return "new"
    if "new" in stages:
        return "mixed"
    return "established"


def campaign_performance_status(
    metrics: Mapping[str, Any],
    lifecycle: str,
    rules: RuleSet,
) -> str:
    if lifecycle in {"new", "mixed"}:
        return "new_observation"
    if lifecycle != "established":
        return "unknown"
    if int(metrics.get("data_days") or 0) < rules.min_mature_days:
        return "insufficient_sample"
    clicks = decimal_value(metrics.get("clicks"))
    if clicks < rules.min_clicks:
        return "insufficient_sample"
    ctr = metrics.get("ctr")
    cvr = metrics.get("cvr")
    if ctr is None or cvr is None:
        return "insufficient_sample"
    return (
        "normal"
        if decimal_value(ctr) >= rules.performance_ctr_threshold
        and decimal_value(cvr) >= rules.performance_cvr_threshold
        else "poor"
    )


def campaign_budget_matrix_status(performance_status: str, budget_full: bool) -> str:
    if performance_status == "normal":
        return "normal_full" if budget_full else "normal_not_full"
    if performance_status == "poor":
        return "poor_full" if budget_full else "poor_not_full"
    return performance_status


def listing_policy_metadata(config: MonitorConfig, as_of: date) -> dict[str, Any]:
    return {
        "new_listing_days": config.listing_new_days,
        "age_basis": "openDate",
        "age_as_of": as_of.isoformat(),
        "new_rule": f"0 <= listing_age_days <= {config.listing_new_days}",
        "join_key": ["shop_id", "asin", "sku"],
        "asin_normalization": "trim_upper",
        "sku_normalization": "trim_exact",
        "ambiguity_policy": "fail_closed_unknown",
        "online_status_scope": ["active", "inActive"],
        "deleted_policy": "excluded_and_not_found",
        "source_endpoints": [SP_AD_PRODUCT_PATH, ONLINE_PRODUCT_PATH],
        "read_only": True,
    }


def build_advertised_products(
    connection: sqlite3.Connection,
    config: MonitorConfig,
    *,
    run_id: str,
    as_of: date,
) -> tuple[list[dict[str, Any]], dict[str, Any], set[tuple[str, str]]]:
    shops = {shop.shop_id: shop for shop in config.shops}
    ad_rows = [
        dict(row)
        for row in sqlite_rows(
            connection,
            """
            SELECT ad.* FROM ad_product_snapshot AS ad
            INNER JOIN campaign_snapshot AS campaign
              ON campaign.run_id = ad.run_id
             AND campaign.shop_id = ad.shop_id
             AND campaign.campaign_id = ad.campaign_id
             AND campaign.state = 'enabled'
            WHERE ad.run_id = ?
            ORDER BY ad.shop_id, ad.campaign_id, ad.group_id, ad.ad_id,
                     ad.asin, ad.sku, ad.source_row
            """,
            (run_id,),
        )
    ]
    source_ad_product_count = connection.execute(
        "SELECT COUNT(*) FROM ad_product_snapshot WHERE run_id = ?",
        (run_id,),
    ).fetchone()[0]
    online_rows = [
        dict(row)
        for row in sqlite_rows(
            connection,
            """
            SELECT * FROM online_product_snapshot
            WHERE run_id = ?
            ORDER BY shop_id, asin, sku, source_row
            """,
            (run_id,),
        )
    ]
    logs = sqlite_rows(
        connection,
        """
        SELECT shop_id, endpoint, status FROM sync_log
        WHERE run_id = ? AND endpoint IN (?, ?)
        """,
        (run_id, SP_AD_PRODUCT_PATH, ONLINE_PRODUCT_PATH),
    )
    source_status: dict[tuple[str, str], str] = {}
    for row in logs:
        key = (row["shop_id"], row["endpoint"])
        previous = source_status.get(key)
        source_status[key] = "error" if previous == "error" or row["status"] != "ok" else "ok"

    online_index: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in online_rows:
        key = (row["shop_id"], as_text(row["asin"]).upper(), as_text(row["sku"]))
        online_index[key].append(row)
    ad_identity_counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for row in ad_rows:
        ad_identity_counts[
            (row["shop_id"], row["campaign_id"], row["group_id"], row["ad_id"])
        ] += 1

    products: list[dict[str, Any]] = []
    for row in ad_rows:
        shop_id = row["shop_id"]
        shop = shops.get(shop_id)
        campaign_id = as_text(row["campaign_id"])
        group_id = as_text(row["group_id"])
        ad_id = as_text(row["ad_id"])
        asin = as_text(row["asin"]).upper()
        sku = as_text(row["sku"])
        identity = (shop_id, campaign_id, group_id, ad_id)
        key = (shop_id, asin, sku)
        matches = online_index.get(key, [])
        mapping_status = "matched"
        match: dict[str, Any] | None = None
        if source_status.get((shop_id, SP_AD_PRODUCT_PATH)) != "ok" or source_status.get(
            (shop_id, ONLINE_PRODUCT_PATH)
        ) != "ok":
            mapping_status = "source_unavailable"
        elif not all((campaign_id, group_id, ad_id, asin, sku)):
            mapping_status = "invalid_ad_key"
        elif ad_identity_counts[identity] != 1:
            mapping_status = "duplicate_ad"
        elif not matches:
            mapping_status = "not_found"
        elif len(matches) != 1:
            mapping_status = "ambiguous"
        else:
            match = matches[0]
            if (
                shop
                and shop.marketplace_id
                and match["marketplace_id"]
                and match["marketplace_id"] != shop.marketplace_id
            ):
                mapping_status = "marketplace_mismatch"
        open_date = as_text(match.get("open_date")) if match else ""
        listing_age_days, listing_stage = listing_stage_for(
            open_date,
            as_of=as_of,
            new_days=config.listing_new_days,
        )
        if mapping_status == "matched" and listing_stage == "unknown":
            mapping_status = "invalid_open_date"
        if mapping_status != "matched":
            listing_age_days = None
            listing_stage = "unknown"
        products.append(
            {
                "shop_id": shop_id,
                "shop_name": shop.shop_name if shop else shop_id,
                "marketplace_id": shop.marketplace_id if shop else "",
                "campaign_id": campaign_id,
                "group_id": group_id,
                "ad_id": ad_id,
                "asin": asin,
                "sku": sku,
                "ad_state": as_text(row["state"]),
                "ad_serving_status": as_text(row["serving_status"]),
                "open_date": (
                    parse_listing_date(open_date).isoformat()
                    if mapping_status == "matched" and parse_listing_date(open_date)
                    else open_date
                ),
                "online_status": as_text(match.get("online_status")) if match else "",
                "listing_age_days": listing_age_days,
                "listing_stage": listing_stage,
                "mapping_status": mapping_status,
                "mapping_count": len(matches),
            }
        )

    campaigns = sqlite_rows(
        connection,
        """
        SELECT shop_id, campaign_id FROM campaign_snapshot
        WHERE run_id = ? AND state = 'enabled'
        """,
        (run_id,),
    )
    campaign_keys = {(row["shop_id"], row["campaign_id"]) for row in campaigns}
    by_campaign: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in products:
        by_campaign[(row["shop_id"], row["campaign_id"])].append(row)
    blocked_campaigns = {
        key
        for key in campaign_keys
        if not by_campaign.get(key)
        or any(
            row["mapping_status"] != "matched" or row["listing_stage"] == "unknown"
            for row in by_campaign[key]
        )
    }

    shop_coverage = []
    for shop in config.shops:
        rows = [row for row in products if row["shop_id"] == shop.shop_id]
        matched = sum(row["mapping_status"] == "matched" for row in rows)
        known = sum(row["listing_stage"] != "unknown" for row in rows)
        sources_ok = all(
            source_status.get((shop.shop_id, endpoint)) == "ok"
            for endpoint in (SP_AD_PRODUCT_PATH, ONLINE_PRODUCT_PATH)
        )
        if not sources_ok:
            status = "unavailable"
        elif not rows:
            status = "not_applicable"
        elif known == len(rows):
            status = "complete"
        else:
            status = "partial"
        shop_coverage.append(
            {
                "shop_id": shop.shop_id,
                "shop_name": shop.shop_name,
                "status": status,
                "advertised_products": len(rows),
                "matched": matched,
                "unknown": len(rows) - known,
            }
        )
    matched_total = sum(row["mapping_status"] == "matched" for row in products)
    unknown_total = sum(row["listing_stage"] == "unknown" for row in products)
    if any(row["status"] == "unavailable" for row in shop_coverage):
        coverage_status = "partial" if matched_total else "unavailable"
    elif unknown_total:
        coverage_status = "partial"
    elif products:
        coverage_status = "complete"
    else:
        coverage_status = "not_applicable"
    listing_coverage = {
        "status": coverage_status,
        "advertised_products": len(products),
        "source_advertised_products": source_ad_product_count,
        "excluded_non_enabled_campaign_positions": max(
            0, source_ad_product_count - len(ad_rows)
        ),
        "matched": matched_total,
        "unmatched": len(products) - matched_total,
        "new": sum(row["listing_stage"] == "new" for row in products),
        "established": sum(row["listing_stage"] == "established" for row in products),
        "unknown": unknown_total,
        "mapping_rate": round(matched_total / len(products), 4) if products else None,
        "blocked_campaigns": len(blocked_campaigns),
        "shop_coverage": shop_coverage,
    }
    return products, listing_coverage, blocked_campaigns


def collect_live_base_data(
    connection: sqlite3.Connection,
    config: MonitorConfig,
    *,
    as_of: date,
    run_id: str,
    logger: logging.Logger,
    coverage: RunCoverage,
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    client_id, client_secret = load_api_credentials()
    snapshot_at = datetime.now().astimezone().isoformat(timespec="seconds")
    endpoints = (
        (SP_CAMPAIGN_PATH, "SP 广告活动", "campaigns.json", insert_campaigns, "cursor"),
        (SP_KEYWORD_PATH, "SP 关键词", "keywords.json", insert_keywords, "cursor"),
        (
            SP_PRODUCT_TARGET_PATH,
            "SP 商品投放",
            "product_targets.json",
            insert_product_targets,
            "cursor",
        ),
        (
            SP_AD_PRODUCT_PATH,
            "SP 广告商品",
            "ad_products.json",
            insert_ad_products,
            "cursor",
        ),
        (
            ONLINE_PRODUCT_PATH,
            "在线产品 V2",
            "online_products.json",
            insert_online_products,
            "page",
        ),
    )
    endpoint_results: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=len(endpoints)) as executor:
        cache_root = config.raw_report_dir / f"base-{date.today():%Y%m%d}"
        futures = {
            executor.submit(
                fetch_base_endpoint,
                config.shops,
                client_id=client_id,
                client_secret=client_secret,
                path=path,
                label=label,
                logger=logger,
                cache_path=cache_root / cache_name,
                pagination=pagination,
            ): (path, label, inserter)
            for path, label, cache_name, inserter, pagination in endpoints
        }
        for future in as_completed(futures):
            path, label, inserter = futures[future]
            try:
                endpoint_results[path] = future.result()
            except Exception as exc:
                raise MonitorFailure(f"读取 {label} 失败。") from exc
            for result in endpoint_results[path]:
                shop = result["shop"]
                coverage.requested_calls += 1
                if result["error"]:
                    coverage.failed_calls += 1
                    log_sync(
                        connection,
                        run_id=run_id,
                        shop_id=shop.shop_id,
                        endpoint=path,
                        status="error",
                        message=result["error"],
                    )
                    logger.warning("店铺 %s %s 读取失败。", shop.shop_name, label)
                    continue
                try:
                    row_count = inserter(
                        connection,
                        run_id,
                        snapshot_at,
                        result["items"],
                        shop.shop_id,
                    )
                except DataQualityFailure as exc:
                    result["error"] = str(exc)
                    coverage.failed_calls += 1
                    log_sync(
                        connection,
                        run_id=run_id,
                        shop_id=shop.shop_id,
                        endpoint=path,
                        status="error",
                        message=str(exc),
                    )
                    continue
                coverage.successful_calls += 1
                log_sync(
                    connection,
                    run_id=run_id,
                    shop_id=shop.shop_id,
                    endpoint=path,
                    status="ok",
                    row_count=row_count,
                    message=f"pages={result['pages']}",
                )
    connection.commit()
    campaigns = sqlite_rows(
        connection,
        "SELECT shop_id, campaign_id FROM campaign_snapshot WHERE run_id = ? AND state = 'enabled'",
        (run_id,),
    )
    campaign_keys = {(row["shop_id"], row["campaign_id"]) for row in campaigns}
    coverage.selected_campaigns = len(campaign_keys)
    failed_campaign_shops = {
        result["shop"].shop_id
        for result in endpoint_results.get(SP_CAMPAIGN_PATH, [])
        if result["error"]
    }
    failed_target_shops = {
        result["shop"].shop_id
        for path in (SP_KEYWORD_PATH, SP_PRODUCT_TARGET_PATH)
        for result in endpoint_results.get(path, [])
        if result["error"]
    }
    failed_listing_shops = {
        result["shop"].shop_id
        for path in (SP_AD_PRODUCT_PATH, ONLINE_PRODUCT_PATH)
        for result in endpoint_results.get(path, [])
        if result["error"]
    }
    blocked_campaigns = {
        key
        for key in campaign_keys
        if key[0] in failed_campaign_shops | failed_listing_shops
    }
    blocked_targets = {
        key
        for key in campaign_keys
        if key[0] in failed_campaign_shops | failed_target_shops | failed_listing_shops
    }
    _, _, listing_blocks = build_advertised_products(
        connection,
        config,
        run_id=run_id,
        as_of=as_of,
    )
    mapping_blocks = {
        key for key in listing_blocks if key[0] not in failed_listing_shops
    }
    coverage.quality_failures += len(mapping_blocks)
    blocked_campaigns.update(listing_blocks)
    blocked_targets.update(listing_blocks)
    return blocked_campaigns, blocked_targets


def collect_hourly_live_data(
    connection: sqlite3.Connection,
    config: MonitorConfig,
    *,
    as_of: date,
    run_id: str,
    logger: logging.Logger,
) -> tuple[RunCoverage, set[tuple[str, str]]]:
    if not config.shops:
        raise MonitorFailure(
            "ads_monitor_config.json 的 shops 为空；请填写赛狐 Amazon 店铺 shop_id，"
            "或同时用 --shop-id 和 --currency 临时指定。"
        )
    client_id, client_secret = load_api_credentials()
    client = SellfoxAdsClient(client_id, client_secret, logger)
    snapshot_at = datetime.now().astimezone().isoformat(timespec="seconds")
    coverage = RunCoverage()
    blocked: set[tuple[str, str]] = set()
    try:
        for shop in config.shops:
            try:
                campaigns, pages = fetch_cursor_items(
                    client,
                    SP_CAMPAIGN_PATH,
                    {"shopId": shop.shop_id, "pageSize": "1000"},
                    f"读取店铺 {shop.shop_name} 的 SP 广告活动",
                )
                insert_campaigns(
                    connection, run_id, snapshot_at, campaigns, shop.shop_id
                )
                log_sync(
                    connection,
                    run_id=run_id,
                    shop_id=shop.shop_id,
                    endpoint=SP_CAMPAIGN_PATH,
                    status="ok",
                    row_count=len(campaigns),
                    message=f"pages={pages}",
                )
            except MonitorFailure as exc:
                log_sync(
                    connection,
                    run_id=run_id,
                    shop_id=shop.shop_id,
                    endpoint=SP_CAMPAIGN_PATH,
                    status="error",
                    message=str(exc),
                )
                coverage.failed_calls += 1
                logger.error("店铺 %s 基础活动读取失败：%s", shop.shop_name, exc)
                continue

            keyword_data_complete = True
            try:
                keywords, pages = fetch_cursor_items(
                    client,
                    SP_KEYWORD_PATH,
                    {"shopId": shop.shop_id, "pageSize": "1000"},
                    f"读取店铺 {shop.shop_name} 的 SP 关键词",
                )
                insert_keywords(
                    connection, run_id, snapshot_at, keywords, shop.shop_id
                )
                log_sync(
                    connection,
                    run_id=run_id,
                    shop_id=shop.shop_id,
                    endpoint=SP_KEYWORD_PATH,
                    status="ok",
                    row_count=len(keywords),
                    message=f"pages={pages}",
                )
            except MonitorFailure as exc:
                keywords = []
                keyword_data_complete = False
                log_sync(
                    connection,
                    run_id=run_id,
                    shop_id=shop.shop_id,
                    endpoint=SP_KEYWORD_PATH,
                    status="error",
                    message=str(exc),
                )
                coverage.failed_calls += 1
                logger.warning("店铺 %s 关键词读取失败：%s", shop.shop_name, exc)

            selected, skipped = select_campaigns(
                campaigns, shop, config.max_campaigns_per_shop
            )
            if not keyword_data_complete:
                blocked.update(
                    (shop.shop_id, as_text(item.get("campaignId")))
                    for item in selected
                )
            coverage.selected_campaigns += len(selected)
            coverage.skipped_campaigns += skipped
            for campaign in selected:
                campaign_id = as_text(campaign.get("campaignId"))
                for report_day in date_window(as_of, config):
                    requests_to_make = [(SP_HOUR_CAMPAIGN_PATH, "campaign")]
                    if config.pull_targets:
                        requests_to_make.append((SP_HOUR_TARGET_PATH, "target"))
                    for endpoint, aggregation_type in requests_to_make:
                        coverage.requested_calls += 1
                        body = {
                            "aggregationType": aggregation_type,
                            "shopId": shop.shop_id,
                            "date": report_day.isoformat(),
                            "campaignId": campaign_id,
                        }
                        try:
                            data = client.post_data(
                                endpoint,
                                body,
                                (
                                    f"读取 {shop.shop_name}/{campaign_id}/"
                                    f"{report_day} {aggregation_type} 小时报告"
                                ),
                            )
                            raw_items = data.get("itemList")
                            if not isinstance(raw_items, list):
                                raise MonitorFailure("小时报告 itemList 格式异常。")
                            if any(not isinstance(item, dict) for item in raw_items):
                                raise MonitorFailure("小时报告 itemList 包含非对象记录。")
                            normalized = [
                                normalize_hourly_row(
                                    item,
                                    aggregation_type=aggregation_type,
                                    shop_id=shop.shop_id,
                                    report_date=report_day,
                                    campaign_id=campaign_id,
                                    run_id=run_id,
                                    ingested_at=snapshot_at,
                                )
                                for item in raw_items
                            ]
                            insert_hourly(connection, normalized)
                            log_sync(
                                connection,
                                run_id=run_id,
                                shop_id=shop.shop_id,
                                endpoint=endpoint,
                                status="ok",
                                row_count=len(normalized),
                                report_date=report_day.isoformat(),
                                campaign_id=campaign_id,
                            )
                            coverage.successful_calls += 1
                        except MonitorFailure as exc:
                            blocked.add((shop.shop_id, campaign_id))
                            coverage.failed_calls += 1
                            log_sync(
                                connection,
                                run_id=run_id,
                                shop_id=shop.shop_id,
                                endpoint=endpoint,
                                status="error",
                                report_date=report_day.isoformat(),
                                campaign_id=campaign_id,
                                message=str(exc),
                            )
                            logger.warning(
                                "%s/%s/%s 读取失败：%s",
                                shop.shop_name,
                                campaign_id,
                                report_day,
                                exc,
                            )
            connection.commit()
    finally:
        client.close()
    return coverage, blocked


def bulk_row_to_fact(
    row: dict[str, Any],
    *,
    aggregation_type: str,
    run_id: str,
    ingested_at: str,
) -> dict[str, Any]:
    try:
        report_day = date.fromisoformat(as_text(row.get("report_date")))
    except ValueError as exc:
        raise DataQualityFailure("天维度报表日期格式异常。") from exc
    shop_id = as_text(row.get("shop_id"))
    campaign_id = as_text(row.get("campaign_id"))
    raw = {
        "shopId": shop_id,
        "date": report_day.isoformat(),
        "hour": "0",
        "campaignId": campaign_id,
        "groupId": as_text(row.get("ad_group_id")),
        "targetingId": as_text(row.get("target_id")),
        "targeting": as_text(row.get("target_text")),
        "matchType": as_text(row.get("match_type")),
        "costs": decimal_text(row.get("spend")),
        "clicks": decimal_text(row.get("clicks")),
        "impressions": decimal_text(row.get("impressions")),
        "orders": decimal_text(row.get("orders")),
        "sales": decimal_text(row.get("sales")),
        "units": decimal_text(row.get("units")),
    }
    return normalize_hourly_row(
        raw,
        aggregation_type=aggregation_type,
        shop_id=shop_id,
        report_date=report_day,
        campaign_id=campaign_id,
        run_id=run_id,
        ingested_at=ingested_at,
    )


def report_reconciliation_blocks(
    campaign_rows: Sequence[dict[str, Any]],
    targeting_rows: Sequence[dict[str, Any]],
) -> tuple[set[tuple[str, str]], dict[str, int]]:
    def totals(rows: Sequence[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Decimal]]:
        grouped: dict[tuple[str, str, str], dict[str, Decimal]] = defaultdict(
            lambda: defaultdict(Decimal)
        )
        for row in rows:
            key = (row["shop_id"], row["report_date"], row["campaign_id"])
            for metric in ("spend", "sales", "orders"):
                grouped[key][metric] += decimal_value(row.get(metric))
        return grouped

    campaign_totals = totals(campaign_rows)
    targeting_totals = totals(targeting_rows)
    blocked: set[tuple[str, str]] = set()
    mismatch_by_shop: dict[str, int] = defaultdict(int)
    for key in set(campaign_totals) | set(targeting_totals):
        left = campaign_totals.get(key, {})
        right = targeting_totals.get(key, {})
        if any(
            abs(decimal_value(left.get(metric)) - decimal_value(right.get(metric)))
            > Decimal("0.01")
            for metric in ("spend", "sales", "orders")
        ):
            blocked.add((key[0], key[2]))
            mismatch_by_shop[key[0]] += 1
    return blocked, dict(mismatch_by_shop)


def complete_bulk_report_calendar(
    connection: sqlite3.Connection,
    run_id: str,
    window: Sequence[date],
    campaign_rows: Sequence[dict[str, Any]],
    targeting_rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dates = [day.isoformat() for day in window]
    completed_campaigns = [dict(row) for row in campaign_rows]
    campaign_seen = {
        (row["shop_id"], row["campaign_id"], row["report_date"])
        for row in completed_campaigns
    }
    snapshots = sqlite_rows(
        connection,
        "SELECT shop_id, campaign_id, name FROM campaign_snapshot WHERE run_id = ? AND state = 'enabled'",
        (run_id,),
    )
    zero_metrics = {
        "spend": Decimal("0"),
        "clicks": Decimal("0"),
        "impressions": Decimal("0"),
        "orders": Decimal("0"),
        "sales": Decimal("0"),
        "units": Decimal("0"),
    }
    for snapshot in snapshots:
        for report_date in dates:
            key = (snapshot["shop_id"], snapshot["campaign_id"], report_date)
            if key in campaign_seen:
                continue
            completed_campaigns.append(
                {
                    "shop_id": snapshot["shop_id"],
                    "shop_name": "",
                    "report_date": report_date,
                    "campaign_id": snapshot["campaign_id"],
                    "campaign_name": snapshot["name"],
                    **zero_metrics,
                }
            )

    completed_targets = [dict(row) for row in targeting_rows]
    target_templates: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    target_seen = set()
    for row in completed_targets:
        entity = (
            row["shop_id"],
            row["campaign_id"],
            row["ad_group_id"],
            row["target_id"],
        )
        target_templates.setdefault(entity, row)
        target_seen.add((*entity, row["report_date"]))
    for entity, template in target_templates.items():
        for report_date in dates:
            if (*entity, report_date) in target_seen:
                continue
            completed_targets.append(
                {**template, "report_date": report_date, **zero_metrics}
            )
    return completed_campaigns, completed_targets


def collect_live_data(
    connection: sqlite3.Connection,
    config: MonitorConfig,
    *,
    as_of: date,
    run_id: str,
    logger: logging.Logger,
    report_source_dir: Path | None = None,
) -> tuple[RunCoverage, set[tuple[str, str]], set[tuple[str, str]]]:
    if not config.shops:
        raise MonitorFailure("没有可采集的广告授权店铺。")
    coverage = RunCoverage()
    blocked_campaigns, blocked_targets = collect_live_base_data(
        connection,
        config,
        as_of=as_of,
        run_id=run_id,
        logger=logger,
        coverage=coverage,
    )
    window = date_window(as_of, config)
    start_date, end_date = window[0].isoformat(), window[-1].isoformat()
    shop_id_to_name = {shop.shop_id: shop.shop_name for shop in config.shops}
    try:
        if report_source_dir:
            bundle = parse_report_directory(
                report_source_dir,
                {shop.shop_name: shop.shop_id for shop in config.shops},
            )
            campaign_rows = bundle.campaign_rows
            targeting_rows = bundle.targeting_rows if config.pull_targets else []
        else:
            client_id, client_secret = load_api_credentials()
            client = SellfoxAdsClient(client_id, client_secret, logger)
            try:
                report_dir = config.raw_report_dir / f"reports-{run_id}"
                bundle = collect_bulk_reports(
                    client,
                    {name: shop_id for shop_id, name in shop_id_to_name.items()},
                    start_date,
                    end_date,
                    report_dir,
                    report_types=(
                        (CAMPAIGN_REPORT, TARGETING_REPORT)
                        if config.pull_targets
                        else (CAMPAIGN_REPORT,)
                    ),
                    batch_size=config.report_shop_batch_size,
                    timeout_seconds=config.report_timeout_seconds,
                    poll_interval_seconds=config.report_poll_seconds,
                )
            finally:
                client.close()
            campaign_rows = bundle.campaign_rows
            targeting_rows = bundle.targeting_rows if config.pull_targets else []
    except BulkReportError as exc:
        raise MonitorFailure(str(exc)) from exc

    expected_dates = {day.isoformat() for day in window}
    for row in [*campaign_rows, *targeting_rows]:
        if row.get("report_date") not in expected_dates:
            raise DataQualityFailure("天维度报表返回了请求窗口外的日期。")
        if row.get("shop_id") not in shop_id_to_name:
            raise DataQualityFailure("天维度报表返回了请求范围外的店铺。")
    campaign_rows, targeting_rows = complete_bulk_report_calendar(
        connection,
        run_id,
        window,
        campaign_rows,
        targeting_rows,
    )
    ingested_at = datetime.now().astimezone().isoformat(timespec="seconds")
    campaign_facts = [
        bulk_row_to_fact(
            row,
            aggregation_type="campaign",
            run_id=run_id,
            ingested_at=ingested_at,
        )
        for row in campaign_rows
    ]
    targeting_facts = [
        bulk_row_to_fact(
            row,
            aggregation_type="target",
            run_id=run_id,
            ingested_at=ingested_at,
        )
        for row in targeting_rows
    ]
    insert_hourly(connection, [*campaign_facts, *targeting_facts])
    campaign_by_shop_count: dict[str, int] = defaultdict(int)
    targeting_by_shop_count: dict[str, int] = defaultdict(int)
    for row in campaign_rows:
        campaign_by_shop_count[row["shop_id"]] += 1
    for row in targeting_rows:
        targeting_by_shop_count[row["shop_id"]] += 1
    for shop in config.shops:
        log_sync(
            connection,
            run_id=run_id,
            shop_id=shop.shop_id,
            endpoint=f"bulk:{CAMPAIGN_REPORT}",
            status="ok",
            row_count=campaign_by_shop_count[shop.shop_id],
            message=f"window={start_date}..{end_date}",
        )
        if config.pull_targets:
            log_sync(
                connection,
                run_id=run_id,
                shop_id=shop.shop_id,
                endpoint=f"bulk:{TARGETING_REPORT}",
                status="ok",
                row_count=targeting_by_shop_count[shop.shop_id],
                message=f"window={start_date}..{end_date}",
            )
    batch_count = (len(config.shops) + config.report_shop_batch_size - 1) // config.report_shop_batch_size
    report_calls = (
        0
        if report_source_dir
        else batch_count * (2 if config.pull_targets else 1)
    )
    coverage.requested_calls += report_calls
    coverage.successful_calls += report_calls
    if config.pull_targets:
        reconciliation_blocks, mismatch_by_shop = report_reconciliation_blocks(
            campaign_rows,
            targeting_rows,
        )
        blocked_targets.update(reconciliation_blocks)
        for shop_id, mismatch_days in mismatch_by_shop.items():
            coverage.quality_failures += 1
            log_sync(
                connection,
                run_id=run_id,
                shop_id=shop_id,
                endpoint="bulk:campaign-target-reconciliation",
                status="error",
                row_count=mismatch_days,
                message="活动日报与投放日报核心指标不一致；投放级建议已阻断。",
            )
    connection.commit()
    return coverage, blocked_campaigns, blocked_targets


def sum_metric(rows: Iterable[sqlite3.Row], name: str) -> Decimal:
    return sum((decimal_value(row[name]) for row in rows), Decimal("0"))


def metric_bundle(rows: Sequence[sqlite3.Row]) -> dict[str, Any]:
    spend = sum_metric(rows, "spend")
    sales = sum_metric(rows, "sales")
    clicks = sum_metric(rows, "clicks")
    impressions = sum_metric(rows, "impressions")
    orders = sum_metric(rows, "orders")
    units = sum_metric(rows, "units")
    return {
        "spend": rounded_money(spend),
        "sales": rounded_money(sales),
        "clicks": clicks,
        "impressions": impressions,
        "orders": orders,
        "units": units,
        "acos": ratio(spend, sales),
        "roas": ratio(sales, spend),
        "ctr": ratio(clicks, impressions),
        "cvr": ratio(orders, clicks),
        "cpc": ratio(spend, clicks),
        "data_days": len({row["report_date"] for row in rows}),
        "latest_date": max((row["report_date"] for row in rows), default=""),
    }


def sqlite_rows(
    connection: sqlite3.Connection,
    query: str,
    params: Sequence[Any],
) -> list[sqlite3.Row]:
    return list(connection.execute(query, params))


def aggregate_campaigns(
    connection: sqlite3.Connection,
    run_id: str,
    shops: dict[str, ShopConfig],
    window_end: date | None = None,
) -> list[dict[str, Any]]:
    campaigns = sqlite_rows(
        connection,
        "SELECT * FROM campaign_snapshot WHERE run_id = ? AND state = 'enabled'",
        (run_id,),
    )
    facts = sqlite_rows(
        connection,
        "SELECT * FROM hourly_fact_history WHERE run_id = ? AND aggregation_type = 'campaign'",
        (run_id,),
    )
    grouped: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in facts:
        grouped[(row["shop_id"], row["campaign_id"])].append(row)

    result: list[dict[str, Any]] = []
    for campaign in campaigns:
        key = (campaign["shop_id"], campaign["campaign_id"])
        rows = grouped.get(key, [])
        metrics = metric_bundle(rows)
        budget = decimal_value(campaign["budget"])
        daily_spend: dict[str, Decimal] = defaultdict(Decimal)
        for row in rows:
            daily_spend[row["report_date"]] += decimal_value(row["spend"])
        latest_day = window_end or (
            date.fromisoformat(metrics["latest_date"])
            if metrics["latest_date"]
            else None
        )
        recent_dates = (
            [
                (latest_day - timedelta(days=offset)).isoformat()
                for offset in range(6, -1, -1)
            ]
            if latest_day
            else []
        )
        recent_set = set(recent_dates)
        performance_7d = metric_bundle(
            [row for row in rows if row["report_date"] in recent_set]
        )
        latest_complete_budget_full = bool(
            budget > 0
            and latest_day
            and daily_spend.get(latest_day.isoformat(), Decimal("0"))
            >= budget * shops[key[0]].rules.budget_utilization_threshold
        )
        utilization_days = sum(
            1
            for day in recent_dates
            if budget > 0
            and daily_spend.get(day, Decimal("0"))
            >= budget * shops[key[0]].rules.budget_utilization_threshold
        )
        result.append(
            {
                "shop_id": key[0],
                "shop_name": shops[key[0]].shop_name,
                "currency": shops[key[0]].currency,
                "campaign_id": key[1],
                "campaign_name": campaign["name"],
                "state": campaign["state"],
                "serving_status": campaign["serving_status"],
                "budget": rounded_money(budget),
                "strategy": campaign["strategy"],
                "creation_date": campaign["creation_date"],
                "last_updated_date": campaign["last_updated_date"],
                "budget_utilization_days_7d": utilization_days,
                "latest_complete_budget_full": latest_complete_budget_full,
                "performance_7d": performance_7d,
                "expected_latest_date": window_end.isoformat() if window_end else "",
                **metrics,
            }
        )
    return result


def aggregate_targets(
    connection: sqlite3.Connection,
    run_id: str,
    campaigns: Sequence[dict[str, Any]],
    shops: dict[str, ShopConfig],
) -> list[dict[str, Any]]:
    facts = sqlite_rows(
        connection,
        "SELECT * FROM hourly_fact_history WHERE run_id = ? AND aggregation_type = 'target'",
        (run_id,),
    )
    keywords = sqlite_rows(
        connection,
        "SELECT * FROM keyword_snapshot WHERE run_id = ?",
        (run_id,),
    )
    product_targets = sqlite_rows(
        connection,
        "SELECT * FROM target_snapshot WHERE run_id = ?",
        (run_id,),
    )
    keyword_map = {
        (
            row["shop_id"],
            row["campaign_id"],
            row["ad_group_id"],
            row["keyword_id"],
        ): row
        for row in keywords
    }
    product_target_map = {
        (
            row["shop_id"],
            row["campaign_id"],
            row["ad_group_id"],
            row["target_id"],
        ): row
        for row in product_targets
    }
    campaign_map = {
        (item["shop_id"], item["campaign_id"]): item for item in campaigns
    }
    grouped: dict[tuple[str, str, str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in facts:
        target_id = row["targeting_id"] or (
            f"text:{row['targeting']}:{row['match_type']}:{row['ad_id']}"
        )
        grouped[
            (row["shop_id"], row["campaign_id"], row["ad_group_id"], target_id)
        ].append(row)

    result: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        shop_id, campaign_id, ad_group_id, target_id = key
        keyword = keyword_map.get((shop_id, campaign_id, ad_group_id, target_id))
        product_target = product_target_map.get(
            (shop_id, campaign_id, ad_group_id, target_id)
        )
        campaign = campaign_map.get((shop_id, campaign_id), {})
        if not campaign:
            continue
        targeting = next((row["targeting"] for row in rows if row["targeting"]), "")
        match_type = next((row["match_type"] for row in rows if row["match_type"]), "")
        ad_id = ",".join(sorted({row["ad_id"] for row in rows if row["ad_id"]}))
        msku = ",".join(sorted({row["msku"] for row in rows if row["msku"]}))
        asin = ",".join(sorted({row["asin"] for row in rows if row["asin"]}))
        result.append(
            {
                "shop_id": shop_id,
                "shop_name": shops[shop_id].shop_name,
                "currency": shops[shop_id].currency,
                "campaign_id": campaign_id,
                "campaign_name": campaign.get("campaign_name", ""),
                "campaign_state": campaign.get("state", ""),
                "campaign_serving_status": campaign.get("serving_status", ""),
                "entity_type": "keyword" if keyword else "target",
                "target_key": f"{'keyword' if keyword else 'target'}:{target_id}",
                "target_id": target_id,
                "ad_group_id": ad_group_id,
                "targeting": (
                    keyword["keyword_text"]
                    if keyword
                    else product_target["resolved_expression"]
                    if product_target and product_target["resolved_expression"]
                    else product_target["expression"]
                    if product_target
                    else targeting
                ),
                "match_type": keyword["match_type"] if keyword else match_type,
                "ad_id": ad_id,
                "msku": msku,
                "asin": asin,
                "state": (
                    keyword["state"]
                    if keyword
                    else product_target["state"]
                    if product_target
                    else campaign.get("state", "")
                ),
                "serving_status": (
                    keyword["serving_status"]
                    if keyword
                    else product_target["serving_status"]
                    if product_target
                    else ""
                ),
                "current_bid": (
                    rounded_money(decimal_value(keyword["bid"]))
                    if keyword
                    else rounded_money(decimal_value(product_target["bid"]))
                    if product_target
                    else None
                ),
                "expected_latest_date": campaign.get("expected_latest_date", ""),
                **metric_bundle(rows),
            }
        )
    return result


def clamp_change(
    current: Decimal,
    requested_pct: Decimal,
    rules: RuleSet,
    *,
    lower: Decimal,
    upper: Decimal,
) -> tuple[Decimal, Decimal]:
    pct = max(-rules.max_change_pct, min(rules.max_change_pct, requested_pct))
    proposed = rounded_money(current * (Decimal("1") + pct))
    proposed = max(lower, min(upper, proposed))
    actual = ratio(proposed - current, current) or Decimal("0")
    return proposed, actual


def recommendation_base(
    *,
    run_id: str,
    generated_at: str,
    entity_type: str,
    entity_key: str,
    shop_id: str,
    campaign_id: str,
    target_id: str,
    metrics: dict[str, Any],
    rules: RuleSet,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "shop_id": shop_id,
        "shop_name": as_text(metrics.get("shop_name")) or shop_id,
        "currency": as_text(metrics.get("currency")) or "UNKNOWN",
        "entity_type": entity_type,
        "entity_key": entity_key,
        "campaign_id": campaign_id,
        "campaign_name": "",
        "target_id": target_id,
        "target_text": "",
        "match_type": "",
        "action_code": "HOLD",
        "priority": "低",
        "current_value": "",
        "proposed_value": "",
        "change_pct": "",
        "spend": decimal_text(metrics.get("spend")),
        "sales": decimal_text(metrics.get("sales")),
        "orders": decimal_text(metrics.get("orders")),
        "clicks": decimal_text(metrics.get("clicks")),
        "acos": (
            decimal_text(metrics["acos"]) if metrics.get("acos") is not None else ""
        ),
        "target_acos": decimal_text(rules.target_acos),
        "rule_id": "within_target",
        "rule_version": RULE_VERSION,
        "reason": "当前指标未触发调控阈值。",
        "data_status": "complete",
        "review_status": "待审核",
    }


def target_recommendation(
    target: dict[str, Any],
    *,
    run_id: str,
    generated_at: str,
    rules: RuleSet,
    blocked: bool,
) -> dict[str, Any]:
    entity_key = (
        f"{target['entity_type']}:{target['shop_id']}:"
        f"{target['campaign_id']}:{target.get('ad_group_id', '')}:"
        f"{target.get('target_key', target['target_id'])}"
    )
    result = recommendation_base(
        run_id=run_id,
        generated_at=generated_at,
        entity_type=target["entity_type"],
        entity_key=entity_key,
        shop_id=target["shop_id"],
        campaign_id=target["campaign_id"],
        target_id=target["target_id"],
        metrics=target,
        rules=rules,
    )
    current_bid = target.get("current_bid")
    result["campaign_name"] = target.get("campaign_name", "")
    result["target_text"] = target.get("targeting", "")
    result["match_type"] = target.get("match_type", "")
    result["current_value"] = decimal_text(current_bid) if current_bid else ""

    if blocked:
        result.update(
            action_code="BLOCKED",
            priority="高",
            rule_id="data_incomplete",
            reason="该活动本次存在接口或数据质量失败，禁止生成调价建议。",
            data_status="partial",
        )
        return result
    if target.get("currency") == "UNKNOWN":
        result.update(
            action_code="BLOCKED",
            priority="高",
            rule_id="missing_currency",
            reason="店铺币种未配置，禁止生成调价建议。",
            data_status="partial",
        )
        return result
    if target["campaign_id"] in rules.protected_campaign_ids or target[
        "target_id"
    ] in rules.protected_target_ids:
        result.update(
            action_code="PROTECTED",
            rule_id="protected_entity",
            reason="对象在保护名单中，不生成调价建议。",
        )
        return result
    if target.get("state") != "enabled":
        result.update(
            action_code="BLOCKED",
            rule_id="entity_not_enabled",
            reason="活动或投放对象不是 enabled，禁止生成建议。",
        )
        return result
    if serving_status_blocks(target.get("serving_status")) or serving_status_blocks(
        target.get("campaign_serving_status")
    ):
        result.update(
            action_code="BLOCKED",
            rule_id="entity_not_serving",
            reason="活动或投放对象处于明确的非投放状态，禁止生成建议。",
        )
        return result
    if target["data_days"] < rules.min_mature_days:
        result.update(
            action_code="OBSERVE",
            rule_id="insufficient_days",
            reason=f"成熟数据仅 {target['data_days']} 天，低于 {rules.min_mature_days} 天。",
        )
        return result
    if target.get("expected_latest_date") and target.get("latest_date") != target.get(
        "expected_latest_date"
    ):
        result.update(
            action_code="BLOCKED",
            priority="高",
            rule_id="stale_data",
            reason="投放数据没有更新到预期成熟日，禁止生成建议。",
            data_status="partial",
        )
        return result
    lifecycle = as_text(target.get("listing_stage"))
    if lifecycle == "unknown":
        result.update(
            action_code="BLOCKED",
            priority="高",
            rule_id="listing_lifecycle_unknown",
            reason="广告商品上架时间未知，禁止生成自动调价建议。",
            data_status="partial",
        )
        return result
    if lifecycle in {"new", "mixed"}:
        result.update(
            action_code="OBSERVE",
            rule_id="new_listing_90d_protection",
            reason="活动包含开售90天内新品，只进入新品诊断和人工复核。",
        )
        return result

    spend = target["spend"]
    orders = target["orders"]
    clicks = target["clicks"]
    acos = target["acos"]
    if orders == 0 and clicks >= rules.min_clicks and spend >= rules.max_zero_order_spend:
        if current_bid:
            proposed, actual_pct = clamp_change(
                current_bid,
                -rules.bid_decrease_pct,
                rules,
                lower=rules.min_bid,
                upper=rules.max_bid,
            )
            result.update(
                action_code="DECREASE_BID",
                priority="高",
                proposed_value=decimal_text(proposed),
                change_pct=decimal_text(actual_pct),
                rule_id="zero_order_spend",
                reason=(
                    f"{target['data_days']} 天点击 {decimal_text(clicks)}、花费 "
                    f"{decimal_text(spend)} 但 0 单；先降价，连续两期仍无单再考虑暂停。"
                ),
            )
        else:
            result.update(
                action_code="REVIEW_TARGET",
                priority="高",
                rule_id="zero_order_missing_bid",
                reason="0 单花费超限，但基础接口没有可关联竞价；需人工检查商品投放。",
            )
        return result

    if (
        orders >= rules.min_orders
        and spend >= rules.min_spend
        and acos is not None
        and acos > rules.target_acos * rules.high_acos_multiplier
    ):
        if current_bid:
            proposed, actual_pct = clamp_change(
                current_bid,
                -rules.bid_decrease_pct,
                rules,
                lower=rules.min_bid,
                upper=rules.max_bid,
            )
            result.update(
                action_code="DECREASE_BID",
                priority="高",
                proposed_value=decimal_text(proposed),
                change_pct=decimal_text(actual_pct),
                rule_id="high_acos",
                reason=(
                    f"ACoS {decimal_text(acos)} 高于目标的 "
                    f"{decimal_text(rules.high_acos_multiplier)} 倍阈值。"
                ),
            )
        else:
            result.update(
                action_code="REVIEW_TARGET",
                priority="中",
                rule_id="high_acos_missing_bid",
                reason="ACoS 超标，但基础接口没有可关联竞价。",
            )
        return result

    if (
        orders >= rules.scale_min_orders
        and spend >= rules.min_spend
        and acos is not None
        and acos < rules.target_acos * rules.low_acos_multiplier
    ):
        if current_bid:
            proposed, actual_pct = clamp_change(
                current_bid,
                rules.bid_increase_pct,
                rules,
                lower=rules.min_bid,
                upper=rules.max_bid,
            )
            result.update(
                action_code="INCREASE_BID",
                priority="中",
                proposed_value=decimal_text(proposed),
                change_pct=decimal_text(actual_pct),
                rule_id="low_acos_scale",
                reason=(
                    f"订单达到 {decimal_text(orders)}，且 ACoS {decimal_text(acos)} "
                    "明显低于目标，可小幅扩量。"
                ),
            )
        return result

    if clicks < rules.min_clicks and orders < rules.min_orders:
        result.update(
            action_code="OBSERVE",
            rule_id="insufficient_sample",
            reason="点击和订单样本不足，继续观察。",
        )
    return result


def campaign_recommendation(
    campaign: dict[str, Any],
    *,
    run_id: str,
    generated_at: str,
    rules: RuleSet,
    blocked: bool,
) -> dict[str, Any]:
    entity_key = f"campaign:{campaign['shop_id']}:{campaign['campaign_id']}"
    result = recommendation_base(
        run_id=run_id,
        generated_at=generated_at,
        entity_type="campaign",
        entity_key=entity_key,
        shop_id=campaign["shop_id"],
        campaign_id=campaign["campaign_id"],
        target_id="",
        metrics=campaign,
        rules=rules,
    )
    budget = campaign["budget"]
    result["campaign_name"] = campaign.get("campaign_name", "")
    result["current_value"] = decimal_text(budget) if budget else ""
    if blocked:
        result.update(
            action_code="BLOCKED",
            priority="高",
            rule_id="data_incomplete",
            reason="该活动本次存在接口或数据质量失败，禁止生成预算建议。",
            data_status="partial",
        )
        return result
    if campaign.get("currency") == "UNKNOWN":
        result.update(
            action_code="BLOCKED",
            priority="高",
            rule_id="missing_currency",
            reason="店铺币种未配置，禁止生成预算建议。",
            data_status="partial",
        )
        return result
    if campaign["campaign_id"] in rules.protected_campaign_ids:
        result.update(
            action_code="PROTECTED",
            rule_id="protected_campaign",
            reason="活动在保护名单中，不生成预算建议。",
        )
        return result
    if campaign.get("state") != "enabled":
        result.update(
            action_code="BLOCKED",
            rule_id="campaign_not_enabled",
            reason="活动不是 enabled，禁止生成建议。",
        )
        return result
    if serving_status_blocks(campaign.get("serving_status")):
        result.update(
            action_code="BLOCKED",
            rule_id="campaign_not_serving",
            reason="活动处于明确的非投放状态，禁止生成建议。",
        )
        return result
    if campaign["data_days"] < rules.min_mature_days:
        result.update(
            action_code="OBSERVE",
            rule_id="insufficient_days",
            reason=f"成熟数据仅 {campaign['data_days']} 天，继续观察。",
        )
        return result
    if campaign.get("expected_latest_date") and campaign.get(
        "latest_date"
    ) != campaign.get("expected_latest_date"):
        result.update(
            action_code="BLOCKED",
            priority="高",
            rule_id="stale_data",
            reason="活动数据没有更新到预期成熟日，禁止生成建议。",
            data_status="partial",
        )
        return result
    performance_status = as_text(campaign.get("performance_status"))
    performance_7d = campaign.get("performance_7d") or {}
    budget_full = bool(campaign.get("budget_full"))
    if performance_status == "unknown":
        result.update(
            action_code="BLOCKED",
            priority="高",
            rule_id="listing_lifecycle_unknown",
            reason="广告商品上架时间未知，禁止生成预算建议。",
            data_status="partial",
        )
        return result
    if performance_status == "new_observation":
        result.update(
            action_code="OBSERVE",
            rule_id="new_listing_90d_protection",
            reason="活动包含开售90天内新品，不按老品CTR和购买率判定好坏。",
        )
        return result
    if performance_status == "insufficient_sample":
        result.update(
            action_code="OBSERVE",
            rule_id="performance_sample_insufficient",
            reason="近7个成熟日或点击样本不足，暂不判定广告表现。",
        )
        return result
    if performance_status == "poor":
        result.update(
            action_code="REVIEW_TARGET" if budget_full else "HOLD",
            priority="高" if budget_full else "中",
            rule_id="poor_performance_budget_full" if budget_full else "poor_performance_budget_available",
            reason=(
                "老品近7日CTR或购买率未达标且预算已跑满；禁止加预算，优先清理低效投放。"
                if budget_full
                else "老品近7日CTR或购买率未达标且预算未跑满；保持预算约束并继续优化。"
            ),
        )
        return result
    if (
        budget > 0
        and performance_status == "normal"
        and decimal_value(performance_7d.get("orders")) >= rules.scale_min_orders
        and performance_7d.get("acos") is not None
        and decimal_value(performance_7d.get("acos")) <= rules.target_acos
        and campaign["budget_utilization_days_7d"]
        >= rules.budget_utilization_days
    ):
        proposed, actual_pct = clamp_change(
            budget,
            rules.budget_increase_pct,
            rules,
            lower=Decimal("0.01"),
            upper=Decimal("9999999"),
        )
        result.update(
            action_code="INCREASE_BUDGET",
            priority="中",
            proposed_value=decimal_text(proposed),
            change_pct=decimal_text(actual_pct),
            rule_id="profitable_budget_limited",
            reason=(
                f"最近 7 个成熟日有 {campaign['budget_utilization_days_7d']} 天"
                "花费达到预算 98%，且 ACoS 达标。"
            ),
        )
    elif performance_status == "normal":
        result.update(
            rule_id="normal_performance_budget_available",
            reason=(
                "老品近7日CTR和购买率达标，但预算尚未形成稳定跑满；"
                "不加预算，先检查竞价、广告位和关键词覆盖。"
            ),
        )
    return result


RECOMMENDATION_COLUMNS = (
    "run_id",
    "generated_at",
    "shop_id",
    "entity_type",
    "entity_key",
    "campaign_id",
    "campaign_name",
    "target_id",
    "target_text",
    "match_type",
    "action_code",
    "priority",
    "current_value",
    "proposed_value",
    "change_pct",
    "spend",
    "sales",
    "orders",
    "clicks",
    "acos",
    "target_acos",
    "rule_id",
    "rule_version",
    "reason",
    "data_status",
    "review_status",
)

RECOMMENDATION_EXPORT_COLUMNS = (
    "run_id",
    "generated_at",
    "shop_id",
    "shop_name",
    "currency",
    *RECOMMENDATION_COLUMNS[3:],
)


def insert_recommendations(
    connection: sqlite3.Connection,
    recommendations: Iterable[dict[str, Any]],
) -> int:
    rows = list(recommendations)
    placeholders = ",".join("?" for _ in RECOMMENDATION_COLUMNS)
    connection.executemany(
        f"INSERT OR REPLACE INTO recommendation VALUES ({placeholders})",
        [tuple(item[column] for column in RECOMMENDATION_COLUMNS) for item in rows],
    )
    return len(rows)


def generate_recommendations(
    connection: sqlite3.Connection,
    config: MonitorConfig,
    run_id: str,
    blocked_campaigns: set[tuple[str, str]],
    blocked_targets: set[tuple[str, str]] | None = None,
    *,
    as_of: date | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    target_blocks = blocked_campaigns if blocked_targets is None else blocked_targets
    shops = {shop.shop_id: shop for shop in config.shops}
    window_end = as_of - timedelta(days=config.maturity_lag_days) if as_of else None
    campaigns = aggregate_campaigns(connection, run_id, shops, window_end)
    targets = aggregate_targets(connection, run_id, campaigns, shops)
    advertised_products, _, _ = build_advertised_products(
        connection,
        config,
        run_id=run_id,
        as_of=as_of or date.today(),
    )
    products_by_campaign: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for product in advertised_products:
        products_by_campaign[(product["shop_id"], product["campaign_id"])].append(product)
    campaigns_by_key = {
        (campaign["shop_id"], campaign["campaign_id"]): campaign
        for campaign in campaigns
    }
    for key, campaign in campaigns_by_key.items():
        rules = shops[key[0]].rules
        lifecycle = campaign_listing_stage(products_by_campaign.get(key, []))
        performance_status = campaign_performance_status(
            campaign.get("performance_7d", {}), lifecycle, rules
        )
        out_of_budget = "OUT_OF_BUDGET" in as_text(campaign.get("serving_status")).upper()
        budget_full = out_of_budget or bool(campaign.get("latest_complete_budget_full"))
        campaign.update(
            listing_stage=lifecycle,
            performance_status=performance_status,
            budget_status="full" if budget_full else "not_full",
            budget_full=budget_full,
            budget_matrix_status=campaign_budget_matrix_status(
                performance_status, budget_full
            ),
            performance_thresholds={
                "ctr": rules.performance_ctr_threshold,
                "cvr": rules.performance_cvr_threshold,
                "min_clicks": rules.min_clicks,
                "min_mature_days": rules.min_mature_days,
                "window_days": 7,
            },
        )
    for target in targets:
        campaign = campaigns_by_key.get((target["shop_id"], target["campaign_id"]), {})
        target["listing_stage"] = campaign.get("listing_stage", "unknown")
        target["campaign_performance_status"] = campaign.get("performance_status", "unknown")
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    recommendations: list[dict[str, Any]] = []
    for campaign in campaigns:
        shop = shops[campaign["shop_id"]]
        key = (campaign["shop_id"], campaign["campaign_id"])
        recommendations.append(
            campaign_recommendation(
                campaign,
                run_id=run_id,
                generated_at=generated_at,
                rules=shop.rules,
                blocked=key in blocked_campaigns,
            )
        )
    for target in targets:
        shop = shops[target["shop_id"]]
        key = (target["shop_id"], target["campaign_id"])
        recommendations.append(
            target_recommendation(
                target,
                run_id=run_id,
                generated_at=generated_at,
                rules=shop.rules,
                blocked=key in target_blocks,
            )
        )
    insert_recommendations(connection, recommendations)
    connection.commit()
    return campaigns, targets, recommendations


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(json_safe(item) for item in value)
    return value


def build_payload(
    connection: sqlite3.Connection,
    config: MonitorConfig,
    *,
    run_id: str,
    as_of: date,
    mode: str,
    coverage: RunCoverage,
    campaigns: Sequence[dict[str, Any]],
    targets: Sequence[dict[str, Any]],
    recommendations: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    advertised_products, listing_coverage, _ = build_advertised_products(
        connection,
        config,
        run_id=run_id,
        as_of=as_of,
    )
    campaign_facts = sqlite_rows(
        connection,
        """
        SELECT * FROM hourly_fact_history
        WHERE run_id = ? AND aggregation_type = 'campaign'
        ORDER BY report_date, report_hour, shop_id, campaign_id
        """,
        (run_id,),
    )
    shops_by_id = {shop.shop_id: shop for shop in config.shops}
    daily: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(
        lambda: {"spend": Decimal("0"), "sales": Decimal("0"), "orders": Decimal("0")}
    )
    campaign_daily: dict[tuple[str, str, str], dict[str, Decimal]] = defaultdict(
        lambda: {"spend": Decimal("0"), "sales": Decimal("0"), "orders": Decimal("0")}
    )
    for row in campaign_facts:
        day_key = (row["shop_id"], row["report_date"])
        campaign_key = (row["shop_id"], row["campaign_id"], row["report_date"])
        for metric in ("spend", "sales", "orders"):
            value = decimal_value(row[metric])
            daily[day_key][metric] += value
            campaign_daily[campaign_key][metric] += value

    action_counts: dict[str, int] = defaultdict(int)
    for item in recommendations:
        action_counts[item["action_code"]] += 1
    sync_logs = [
        dict(row)
        for row in sqlite_rows(
            connection,
            "SELECT * FROM sync_log WHERE run_id = ? ORDER BY id",
            (run_id,),
        )
    ]
    source_rows = []
    for row in campaign_facts[:5000]:
        shop = shops_by_id.get(row["shop_id"])
        source_rows.append(
            {
                **dict(row),
                "shop_name": shop.shop_name if shop else row["shop_id"],
                "currency": shop.currency if shop else "UNKNOWN",
            }
        )
    report_dates = [key[-1] for key in campaign_daily]
    start_date = min(report_dates, default="")
    end_date = max(report_dates, default="")
    campaign_names = {
        (item["shop_id"], item["campaign_id"]): item.get("campaign_name", "")
        for item in campaigns
    }
    rules = [
        {
            "shop_id": shop.shop_id,
            "shop_name": shop.shop_name,
            "currency": shop.currency,
            "marketplace_id": shop.marketplace_id,
            "region": shop.region,
            **asdict(shop.rules),
        }
        for shop in config.shops
    ]
    log_rows_by_shop: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sync_logs:
        log_rows_by_shop[row["shop_id"]].append(row)
    fact_dates_by_shop: dict[str, list[str]] = defaultdict(list)
    report_campaigns_by_shop: dict[str, set[str]] = defaultdict(set)
    for row in campaign_facts:
        fact_dates_by_shop[row["shop_id"]].append(row["report_date"])
        report_campaigns_by_shop[row["shop_id"]].add(row["campaign_id"])
    campaign_counts: dict[str, int] = defaultdict(int)
    for item in campaigns:
        campaign_counts[item["shop_id"]] += 1
    shop_coverage = []
    for shop in config.shops:
        logs = log_rows_by_shop.get(shop.shop_id, [])
        failed = sum(item["status"] != "ok" for item in logs)
        dates = fact_dates_by_shop.get(shop.shop_id, [])
        shop_coverage.append(
            {
                "shop_id": shop.shop_id,
                "shop_name": shop.shop_name,
                "currency": shop.currency,
                "marketplace_id": shop.marketplace_id,
                "region": shop.region,
                "status": "partial" if failed else "complete",
                "failed_calls": failed,
                "successful_calls": sum(item["status"] == "ok" for item in logs),
                "campaigns": campaign_counts[shop.shop_id],
                "campaigns_with_report_rows": len(
                    report_campaigns_by_shop.get(shop.shop_id, set())
                ),
                "source_start_date": min(dates, default=""),
                "source_end_date": max(dates, default=""),
            }
        )
    return json_safe(
        {
            "meta": {
                "title": "赛狐广告监控与调控建议",
                "run_id": run_id,
                "generated_at": datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
                "as_of": as_of.isoformat(),
                "mode": mode,
                "status": coverage.status,
                "source_start_date": start_date,
                "source_end_date": end_date,
                "lookback_days": config.lookback_days,
                "maturity_lag_days": config.maturity_lag_days,
                "rule_version": RULE_VERSION,
                "requested_calls": coverage.requested_calls,
                "successful_calls": coverage.successful_calls,
                "failed_calls": coverage.failed_calls,
                "quality_failures": coverage.quality_failures,
                "selected_campaigns": coverage.selected_campaigns,
                "skipped_campaigns": coverage.skipped_campaigns,
                "shop_count": len(config.shops),
                "currencies": sorted({shop.currency for shop in config.shops}),
                "source_rows_total": len(campaign_facts),
                "source_rows_published": len(source_rows),
                "source_rows_truncated": len(source_rows) < len(campaign_facts),
                "source_note": (
                    "Sellfox Open API; authorized shops, SP base data, and SP daily reports. "
                    "Recommendations are review-only and do not modify ads."
                ),
            },
            "daily_trend": [
                {
                    "shop_id": shop_id,
                    "shop_name": shops_by_id[shop_id].shop_name,
                    "currency": shops_by_id[shop_id].currency,
                    "date": day,
                    **values,
                }
                for (shop_id, day), values in sorted(daily.items())
            ],
            "campaign_daily_trend": [
                {
                    "shop_id": shop_id,
                    "shop_name": shops_by_id[shop_id].shop_name,
                    "currency": shops_by_id[shop_id].currency,
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_names.get((shop_id, campaign_id), ""),
                    "date": day,
                    **values,
                }
                for (shop_id, campaign_id, day), values in sorted(
                    campaign_daily.items()
                )
            ],
            "action_counts": [
                {"action_code": code, "count": count}
                for code, count in sorted(action_counts.items())
            ],
            "campaigns": list(campaigns),
            "targets": list(targets),
            "advertised_products": advertised_products,
            "listing_coverage": listing_coverage,
            "policy": {
                "listing_lifecycle": listing_policy_metadata(config, as_of),
                "main_product": {
                    "window_days": config.main_product_window_days,
                    "min_orders": config.main_product_min_orders,
                    "max_daily_cv": config.main_product_max_daily_cv,
                    "sudden_drop_ratio": config.main_product_sudden_drop_ratio,
                    "sales_stability_basis": "daily_order_count_coefficient_of_variation",
                },
            },
            "recommendations": list(recommendations),
            "sync_logs": sync_logs,
            "shops": [
                {
                    "shop_id": shop.shop_id,
                    "shop_name": shop.shop_name,
                    "currency": shop.currency,
                    "marketplace_id": shop.marketplace_id,
                    "region": shop.region,
                }
                for shop in config.shops
            ],
            "shop_coverage": shop_coverage,
            "rules": rules,
            "source_data": source_rows,
            "sources": [
                {
                    "name": "获取店铺列表",
                    "url": "https://sellfoxapi.apifox.cn/api-51516635",
                },
                {
                    "name": "SP广告活动",
                    "url": "https://sellfoxapi.apifox.cn/api-367482273",
                },
                {
                    "name": "SP关键词投放",
                    "url": "https://sellfoxapi.apifox.cn/api-367482278",
                },
                {
                    "name": "SP商品投放",
                    "url": "https://sellfoxapi.apifox.cn/api-367482279",
                },
                {
                    "name": "SP广告商品",
                    "url": "https://sellfoxapi.apifox.cn/",
                    "endpoint": SP_AD_PRODUCT_PATH,
                },
                {
                    "name": "在线产品 V2",
                    "url": "https://sellfoxapi.apifox.cn/",
                    "endpoint": ONLINE_PRODUCT_PATH,
                },
                {
                    "name": "创建广告日报下载任务",
                    "url": "https://sellfoxapi.apifox.cn/api-52365899",
                },
                {
                    "name": "查询广告日报下载任务",
                    "url": "https://sellfoxapi.apifox.cn/api-52365898",
                },
            ],
        }
    )


def write_payload(payload: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "sellfox_ads_monitor_payload.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def publish_live_payload(source: Path, destination: Path) -> Path:
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise MonitorFailure("待发布的广告监控 JSON 无效。") from exc
    if payload.get("meta", {}).get("mode") != "live":
        raise MonitorFailure("拒绝把演示数据发布到真实广告看板。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == destination.resolve():
        return destination
    temporary = destination.with_name(
        f".{destination.name}.tmp-{os.getpid()}-{time.time_ns()}"
    )
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    except OSError as exc:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise MonitorFailure("发布广告监控网页数据失败。") from exc
    return destination


def write_recommendation_csv(
    recommendations: Sequence[dict[str, Any]],
    output_dir: Path,
) -> Path:
    path = output_dir / "sellfox_ads_recommendations.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(RECOMMENDATION_EXPORT_COLUMNS),
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(recommendations)
    return path


def normalize_payload_run_id(payload: dict[str, Any], run_id: str) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "run_id":
                    value[key] = run_id
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)


def validate_staged_outputs(staging_dir: Path, workbook_expected: bool) -> None:
    required = {
        "sellfox_ads_monitor_payload.json",
        "sellfox_ads_recommendations.csv",
    }
    if workbook_expected:
        required.add(WORKBOOK_NAME)
    invalid = [
        name
        for name in sorted(required)
        if not (staging_dir / name).is_file() or (staging_dir / name).stat().st_size <= 0
    ]
    if invalid:
        raise MonitorFailure("广告监控临时产物缺失或为空：" + ", ".join(invalid))


def rollback_output_swap(state: OutputSwapState) -> None:
    failures: list[str] = []
    for name in reversed(state.moved_new):
        source = state.final_dir / name
        if not source.exists():
            continue
        try:
            os.replace(source, state.staging_dir / name)
        except OSError:
            failures.append(name)
    for name in reversed(state.moved_old):
        source = state.backup_dir / name
        if not source.exists():
            continue
        try:
            os.replace(source, state.final_dir / name)
        except OSError:
            failures.append(name)
    if failures:
        raise OutputRollbackFailure(
            "输出文件回滚失败，请保留 backup 目录并人工恢复："
            + ", ".join(sorted(set(failures)))
        )


def swap_generated_outputs(
    staging_dir: Path,
    final_dir: Path,
    backup_dir: Path,
) -> OutputSwapState:
    if not staging_dir.is_dir():
        raise MonitorFailure("广告监控临时输出目录不存在。")
    staged_names = {item.name for item in staging_dir.iterdir()}
    unexpected = staged_names - GENERATED_OUTPUT_NAMES
    if unexpected:
        raise MonitorFailure(
            "广告监控临时目录出现未知文件：" + ", ".join(sorted(unexpected))
        )
    final_dir.mkdir(parents=True, exist_ok=True)
    if backup_dir.exists():
        raise MonitorFailure("广告监控备份目录已存在，本次安全退出。")
    backup_dir.mkdir(parents=True)
    moved_old: list[str] = []
    moved_new: list[str] = []
    try:
        for name in sorted(staged_names):
            source = final_dir / name
            if source.exists():
                os.replace(source, backup_dir / name)
                moved_old.append(name)
        for name in sorted(staged_names):
            os.replace(staging_dir / name, final_dir / name)
            moved_new.append(name)
    except BaseException as exc:
        state = OutputSwapState(
            staging_dir,
            final_dir,
            backup_dir,
            tuple(moved_old),
            tuple(moved_new),
        )
        try:
            rollback_output_swap(state)
        except MonitorFailure as rollback_exc:
            raise rollback_exc from exc
        try:
            backup_dir.rmdir()
        except OSError:
            pass
        if isinstance(exc, OSError):
            raise MonitorFailure("替换广告监控输出文件失败，旧版已恢复。") from exc
        raise
    return OutputSwapState(
        staging_dir,
        final_dir,
        backup_dir,
        tuple(moved_old),
        tuple(moved_new),
    )


def discard_output_directory(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_dir() or not any(
        marker in path.name for marker in (".staging-", ".backup-")
    ):
        raise MonitorFailure("拒绝清理非广告监控临时目录。")
    shutil.rmtree(path)


def finalize_output_swap(state: OutputSwapState, logger: logging.Logger) -> None:
    for path in (state.backup_dir, state.staging_dir):
        try:
            discard_output_directory(path)
        except OSError:
            logger.warning("无法清理广告监控临时目录：%s", path)


def find_node(configured: str = "") -> Path | None:
    candidates = [
        configured,
        os.environ.get("ADS_MONITOR_NODE", ""),
        shutil.which("node") or "",
        str(
            Path.home()
            / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
        ),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def build_workbook(
    payload_path: Path,
    output_dir: Path,
    configured_node: str,
    *,
    preview: bool = False,
) -> Path:
    node = find_node(configured_node)
    if not node:
        raise MonitorFailure(
            "未找到 Node.js，无法生成 xlsx；JSON 和 CSV 已生成。"
        )
    builder = ROOT / "build_ads_monitor_workbook.mjs"
    if not builder.exists():
        raise MonitorFailure(f"工作簿生成器不存在：{builder}")
    workbook_path = output_dir / WORKBOOK_NAME
    command = [str(node), str(builder), str(payload_path), str(workbook_path)]
    if preview:
        command.append(str(output_dir / "previews"))
    try:
        subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            timeout=240,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MonitorFailure("生成广告监控工作簿失败。") from exc
    return workbook_path


def validate_preflight(
    config: MonitorConfig,
    *,
    require_workbook: bool = True,
) -> dict[str, Any]:
    if not config.shops and not config.discover_shops:
        raise MonitorFailure("shops 为空，无法创建可运行的每日监控任务。")
    client_id, client_secret = load_api_credentials()
    client = SellfoxAdsClient(
        client_id,
        client_secret,
        logging.getLogger("sellfox-ads-preflight"),
    )
    try:
        client.get_token()  # Verify credentials now.
        checked_config = (
            replace(config, shops=discover_authorized_shops(client, config))
            if config.discover_shops
            else config
        )
    except ImportFailure as exc:
        raise MonitorFailure(str(exc)) from exc
    finally:
        client.close()
    node = find_node(config.node_path) if require_workbook else None
    if require_workbook:
        if not node:
            raise MonitorFailure("未找到 Node.js，无法生成广告监控工作簿。")
        if not (ROOT / "build_ads_monitor_workbook.mjs").is_file():
            raise MonitorFailure("广告监控工作簿生成器不存在。")
        if not (ROOT / "node_modules" / "@oai" / "artifact-tool").exists():
            raise MonitorFailure("缺少工作簿依赖 @oai/artifact-tool。")
    return {
        "status": "ok",
        "shops": len(checked_config.shops),
        "currencies": sorted({shop.currency for shop in checked_config.shops}),
        "shop_source": "api" if config.discover_shops else "config",
        "authentication": "ok",
        "workbook": "enabled" if require_workbook else "disabled",
        "node": str(node) if node else "",
    }


def seed_demo_data(
    connection: sqlite3.Connection,
    config: MonitorConfig,
    *,
    run_id: str,
    as_of: date,
) -> RunCoverage:
    snapshot_at = datetime.now().astimezone().isoformat(timespec="seconds")
    shop = config.shops[0]
    campaigns = [
        {
            "shopId": shop.shop_id,
            "campaignId": "CAMP-GROWTH",
            "name": "SP-成熟产品-扩量",
            "state": "enabled",
            "servingStatus": "CAMPAIGN_STATUS_ENABLED",
            "targetingType": "manual",
            "budget": "50",
            "strategy": "legacyForSales",
            "creationDate": "2026-01-01",
            "lastUpdatedDate": "2026-07-01",
        },
        {
            "shopId": shop.shop_id,
            "campaignId": "CAMP-CUT",
            "name": "SP-高ACoS-降价",
            "state": "enabled",
            "servingStatus": "CAMPAIGN_STATUS_ENABLED",
            "targetingType": "manual",
            "budget": "35",
            "strategy": "legacyForSales",
            "creationDate": "2026-01-01",
            "lastUpdatedDate": "2026-07-01",
        },
    ]
    keywords = [
        {
            "shopId": shop.shop_id,
            "campaignId": "CAMP-GROWTH",
            "groupId": "GROUP-1",
            "keywordId": "KW-GOOD",
            "keywordText": "good keyword",
            "bid": "1.00",
            "matchType": "exact",
            "state": "enabled",
            "servingStatus": "AD_STATUS_LIVE",
        },
        {
            "shopId": shop.shop_id,
            "campaignId": "CAMP-CUT",
            "groupId": "GROUP-2",
            "keywordId": "KW-HIGH",
            "keywordText": "high acos keyword",
            "bid": "1.20",
            "matchType": "phrase",
            "state": "enabled",
            "servingStatus": "AD_STATUS_LIVE",
        },
        {
            "shopId": shop.shop_id,
            "campaignId": "CAMP-CUT",
            "groupId": "GROUP-2",
            "keywordId": "KW-ZERO",
            "keywordText": "zero order keyword",
            "bid": "0.80",
            "matchType": "broad",
            "state": "enabled",
            "servingStatus": "AD_STATUS_LIVE",
        },
    ]
    insert_campaigns(connection, run_id, snapshot_at, campaigns)
    insert_keywords(connection, run_id, snapshot_at, keywords)
    ad_products = [
        {
            "shopId": shop.shop_id,
            "campaignId": "CAMP-GROWTH",
            "groupId": "GROUP-1",
            "adId": "AD-GROWTH",
            "asin": "B0DEMO0001",
            "sku": "SKU-DEMO-ESTABLISHED",
            "state": "enabled",
            "servingStatus": "AD_STATUS_LIVE",
        },
        {
            "shopId": shop.shop_id,
            "campaignId": "CAMP-CUT",
            "groupId": "GROUP-2",
            "adId": "AD-CUT",
            "asin": "B0DEMO0002",
            "sku": "SKU-DEMO-NEW",
            "state": "enabled",
            "servingStatus": "AD_STATUS_LIVE",
        },
    ]
    online_products = [
        {
            "id": "PRODUCT-DEMO-1",
            "shopId": shop.shop_id,
            "asin": "B0DEMO0001",
            "sku": "SKU-DEMO-ESTABLISHED",
            "openDate": (as_of - timedelta(days=120)).isoformat(),
            "onlineStatus": "Active",
        },
        {
            "id": "PRODUCT-DEMO-2",
            "shopId": shop.shop_id,
            "asin": "B0DEMO0002",
            "sku": "SKU-DEMO-NEW",
            "openDate": (as_of - timedelta(days=10)).isoformat(),
            "onlineStatus": "Active",
        },
    ]
    insert_ad_products(connection, run_id, snapshot_at, ad_products, shop.shop_id)
    insert_online_products(connection, run_id, snapshot_at, online_products, shop.shop_id)
    rows: list[dict[str, Any]] = []
    days = date_window(as_of, config)
    target_specs = [
        ("CAMP-GROWTH", "KW-GOOD", "good keyword", "exact", "10", "50", "1", "10", "1000"),
        ("CAMP-CUT", "KW-HIGH", "high acos keyword", "phrase", "15", "30", "0.5", "12", "800"),
        ("CAMP-CUT", "KW-ZERO", "zero order keyword", "broad", "5", "0", "0", "3", "300"),
    ]
    for report_day in days:
        campaign_totals: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: defaultdict(Decimal)
        )
        for campaign_id, target_id, targeting, match_type, spend, sales, orders, clicks, impressions in target_specs:
            raw = {
                "shopId": shop.shop_id,
                "date": report_day.isoformat(),
                "hour": "12",
                "campaignId": campaign_id,
                "groupId": "GROUP-1" if campaign_id == "CAMP-GROWTH" else "GROUP-2",
                "targetingId": target_id,
                "targeting": targeting,
                "matchType": match_type,
                "costs": spend,
                "sales": sales,
                "orders": orders,
                "clicks": clicks,
                "impressions": impressions,
                "units": orders,
            }
            rows.append(
                normalize_hourly_row(
                    raw,
                    aggregation_type="target",
                    shop_id=shop.shop_id,
                    report_date=report_day,
                    campaign_id=campaign_id,
                    run_id=run_id,
                    ingested_at=snapshot_at,
                )
            )
            for key in ("costs", "sales", "orders", "clicks", "impressions", "units"):
                campaign_totals[campaign_id][key] += decimal_value(raw[key])
        for campaign_id, totals in campaign_totals.items():
            raw = {
                "shopId": shop.shop_id,
                "date": report_day.isoformat(),
                "hour": "12",
                "campaignId": campaign_id,
                **{key: decimal_text(value) for key, value in totals.items()},
            }
            rows.append(
                normalize_hourly_row(
                    raw,
                    aggregation_type="campaign",
                    shop_id=shop.shop_id,
                    report_date=report_day,
                    campaign_id=campaign_id,
                    run_id=run_id,
                    ingested_at=snapshot_at,
                )
            )
    insert_hourly(connection, rows)
    log_sync(
        connection,
        run_id=run_id,
        shop_id=shop.shop_id,
        endpoint="demo-fixture",
        status="ok",
        row_count=len(rows),
        message="synthetic demo data",
    )
    for endpoint, count in (
        (SP_AD_PRODUCT_PATH, len(ad_products)),
        (ONLINE_PRODUCT_PATH, len(online_products)),
    ):
        log_sync(
            connection,
            run_id=run_id,
            shop_id=shop.shop_id,
            endpoint=endpoint,
            status="ok",
            row_count=count,
            message="synthetic demo listing data",
        )
    connection.commit()
    return RunCoverage(
        requested_calls=1,
        successful_calls=1,
        selected_campaigns=len(campaigns),
    )


def demo_config(base: MonitorConfig) -> MonitorConfig:
    default_rules = parse_rules(
        {
            "target_acos": 0.3,
            "min_orders": 3,
            "scale_min_orders": 5,
            "min_clicks": 10,
            "min_spend": 5,
            "max_zero_order_spend": 20,
            "high_acos_multiplier": 1.2,
            "low_acos_multiplier": 0.8,
            "bid_decrease_pct": 0.1,
            "bid_increase_pct": 0.05,
            "budget_increase_pct": 0.1,
            "budget_utilization_threshold": 0.98,
            "budget_utilization_days": 3,
            "min_bid": 0.02,
            "max_bid": 10,
            "max_change_pct": 0.1,
            "min_mature_days": 7,
            "performance_ctr_threshold": 0.01,
            "performance_cvr_threshold": 0.1,
        }
    )
    return MonitorConfig(
        shops=(
            ShopConfig(
                shop_id="DEMO-SHOP",
                shop_name="演示店铺",
                currency="USD",
                campaign_ids=(),
                rules=default_rules,
            ),
        ),
        discover_shops=False,
        default_rules=default_rules,
        lookback_days=base.lookback_days,
        maturity_lag_days=base.maturity_lag_days,
        max_campaigns_per_shop=base.max_campaigns_per_shop,
        pull_targets=True,
        listing_new_days=base.listing_new_days,
        main_product_window_days=base.main_product_window_days,
        main_product_min_orders=base.main_product_min_orders,
        main_product_max_daily_cv=base.main_product_max_daily_cv,
        main_product_sudden_drop_ratio=base.main_product_sudden_drop_ratio,
        report_shop_batch_size=base.report_shop_batch_size,
        report_poll_seconds=base.report_poll_seconds,
        report_timeout_seconds=base.report_timeout_seconds,
        database_path=base.database_path,
        output_dir=base.output_dir,
        raw_report_dir=base.raw_report_dir,
        dashboard_payload_path=base.dashboard_payload_path,
        node_path=base.node_path,
    )


def config_scope_id(config: MonitorConfig) -> str:
    parts = [
        f"{shop.shop_id}:{shop.currency}:{','.join(sorted(shop.campaign_ids))}"
        for shop in sorted(config.shops, key=lambda item: item.shop_id)
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:10]
    currencies = sorted({shop.currency.lower() for shop in config.shops})
    prefix = currencies[0] if len(currencies) == 1 else "multi"
    return f"{prefix}-{digest}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="读取赛狐 SP 广告数据，生成监控工作簿和调控建议（不会修改广告）。"
    )
    parser.add_argument("--once", action="store_true", help="执行一次监控")
    parser.add_argument("--demo", action="store_true", help="使用合成数据生成演示结果")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--shop-id", action="append", default=[])
    parser.add_argument("--currency", help="与 --shop-id 一起使用，例如 USD")
    parser.add_argument("--lookback-days", type=int)
    parser.add_argument("--max-campaigns", type=int)
    parser.add_argument("--database")
    parser.add_argument("--output-dir")
    parser.add_argument(
        "--report-source-dir",
        help="复用已下载的 adCampaignReport/adTargeringReport XLSX 目录",
    )
    parser.add_argument("--as-of", help="分析日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--no-workbook", action="store_true")
    parser.add_argument("--check-config", action="store_true", help="仅做定时任务预检")
    parser.add_argument(
        "--lock-wait-minutes",
        type=int,
        default=0,
        help="已有广告采集任务运行时最多等待多少分钟；默认立即退出",
    )
    parser.add_argument("--preview", action="store_true", help="同时渲染工作簿预览图")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger = setup_logging(args.verbose)
    try:
        if args.lock_wait_minutes < 0:
            raise ValueError("--lock-wait-minutes 不能小于 0。")
        as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
        config = load_monitor_config(
            resolve_path(args.config),
            shop_overrides=args.shop_id,
            currency_override=args.currency,
            database_override=args.database,
            output_override=args.output_dir,
            lookback_override=args.lookback_days,
            max_campaigns_override=args.max_campaigns,
        )
        if args.check_config:
            print(
                json.dumps(
                    validate_preflight(
                        config,
                        require_workbook=not args.no_workbook,
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        if args.demo:
            config = demo_config(config)
        else:
            config = resolve_discovered_shops(config, logger)
        mode = "demo" if args.demo else "live"
        scope_id = config_scope_id(config)
        config = replace(config, output_dir=config.output_dir / scope_id)
        run_id = f"{as_of:%Y%m%d}-{mode}-{scope_id}"
        attempt_run_id = f"{run_id}-attempt-{os.getpid()}-{time.time_ns()}"
        attempt_suffix = hashlib.sha256(attempt_run_id.encode("utf-8")).hexdigest()[:12]
        staging_output_dir = (
            config.output_dir.parent
            / f".{config.output_dir.name}.staging-{attempt_suffix}"
        )
        backup_output_dir = (
            config.output_dir.parent
            / f".{config.output_dir.name}.backup-{attempt_suffix}"
        )
        swap_state: OutputSwapState | None = None
        with single_instance(
            wait_seconds=args.lock_wait_minutes * 60
        ), connect_store(config.database_path) as connection:
            try:
                if args.demo:
                    coverage = seed_demo_data(
                        connection, config, run_id=attempt_run_id, as_of=as_of
                    )
                    blocked_campaigns: set[tuple[str, str]] = set()
                    blocked_targets: set[tuple[str, str]] = set()
                else:
                    coverage, blocked_campaigns, blocked_targets = collect_live_data(
                        connection,
                        config,
                        as_of=as_of,
                        run_id=attempt_run_id,
                        logger=logger,
                        report_source_dir=(
                            resolve_path(args.report_source_dir)
                            if args.report_source_dir
                            else None
                        ),
                    )
                campaigns, targets, recommendations = generate_recommendations(
                    connection,
                    config,
                    attempt_run_id,
                    blocked_campaigns,
                    blocked_targets,
                    as_of=as_of,
                )
                payload = build_payload(
                    connection,
                    config,
                    as_of=as_of,
                    run_id=attempt_run_id,
                    mode=mode,
                    coverage=coverage,
                    campaigns=campaigns,
                    targets=targets,
                    recommendations=recommendations,
                )
                normalize_payload_run_id(payload, run_id)
                published_recommendations = list(payload["recommendations"])
                staged_payload_path = write_payload(payload, staging_output_dir)
                staged_csv_path = write_recommendation_csv(
                    published_recommendations,
                    staging_output_dir,
                )
                staged_workbook_path = None
                if not args.no_workbook:
                    staged_workbook_path = build_workbook(
                        staged_payload_path,
                        staging_output_dir,
                        config.node_path,
                        preview=args.preview,
                    )
                validate_staged_outputs(
                    staging_output_dir,
                    workbook_expected=not args.no_workbook,
                )
                swap_state = swap_generated_outputs(
                    staging_output_dir,
                    config.output_dir,
                    backup_output_dir,
                )
                try:
                    promote_run(connection, attempt_run_id, run_id)
                except BaseException:
                    rollback_output_swap(swap_state)
                    swap_state = None
                    raise
            except BaseException as exc:
                reset_run(connection, attempt_run_id)
                if swap_state is None and not isinstance(exc, OutputRollbackFailure):
                    try:
                        discard_output_directory(staging_output_dir)
                        backup_output_dir.rmdir()
                    except FileNotFoundError:
                        pass
                    except OSError:
                        logger.warning(
                            "无法清理广告监控临时目录：%s",
                            staging_output_dir,
                        )
                raise
        if swap_state is None:
            raise MonitorFailure("广告监控输出未完成安全替换。")
        finalize_output_swap(swap_state, logger)
        payload_path = config.output_dir / staged_payload_path.name
        csv_path = config.output_dir / staged_csv_path.name
        workbook_path = (
            config.output_dir / staged_workbook_path.name
            if staged_workbook_path
            else None
        )
        dashboard_path = None
        if mode == "live" and config.dashboard_payload_path:
            dashboard_path = publish_live_payload(
                payload_path,
                config.dashboard_payload_path,
            )
        actionable = sum(
            1
            for item in recommendations
            if item["action_code"]
            in {"DECREASE_BID", "INCREASE_BID", "INCREASE_BUDGET", "REVIEW_TARGET"}
        )
        result = {
            "status": "ok",
            "mode": mode,
            "run_id": run_id,
            "coverage": coverage.status,
            "campaigns": len(campaigns),
            "targets": len(targets),
            "recommendations": len(recommendations),
            "actionable": actionable,
            "payload": str(payload_path),
            "recommendation_csv": str(csv_path),
            "workbook": str(workbook_path) if workbook_path else "",
            "dashboard": str(dashboard_path) if dashboard_path else "",
        }
        logger.info(
            "广告监控完成：模式=%s，覆盖=%s，活动=%s，投放=%s，待复核=%s。",
            mode,
            coverage.status,
            len(campaigns),
            len(targets),
            actionable,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (MonitorFailure, ValueError) as exc:
        logger.error("%s", exc)
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 2
    except KeyboardInterrupt:
        logger.warning("用户取消了广告监控。")
        return 130
    except Exception as exc:
        logger.error("未预期错误：%s", type(exc).__name__)
        print(
            json.dumps(
                {"status": "error", "message": f"未预期错误：{type(exc).__name__}"},
                ensure_ascii=False,
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
