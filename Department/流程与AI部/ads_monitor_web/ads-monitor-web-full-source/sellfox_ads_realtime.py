#!/usr/bin/env python3
"""Collect provisional Sellfox SP hourly data without touching mature facts."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from sellfox_ads_monitor import (
    DataQualityFailure,
    MonitorFailure,
    SP_HOUR_CAMPAIGN_PATH,
    SellfoxAdsClient,
    load_api_credentials,
    normalize_hourly_row,
    single_instance,
)
from sellfox_import import API_BASE_URL, ImportFailure, as_text


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "ads_monitor_config.json"
DEFAULT_MATURE_PAYLOAD = ROOT / "ads-monitor-web" / "public" / "data" / "ads-monitor.json"
SCHEMA_VERSION = "sellfox-ads-realtime-v1"
ACTIONABLE_CODES = frozenset({"DECREASE_BID", "INCREASE_BID", "INCREASE_BUDGET"})
SCALE_CODES = frozenset({"INCREASE_BID", "INCREASE_BUDGET"})
TIER_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Sellfox does not return an ad-profile timezone. These defaults are explicit,
# inspectable marketplace assumptions and can be overridden per shop in config.
MARKETPLACE_REPORT_TIMEZONES = {
    "ATVPDKIKX0DER": "America/Los_Angeles",
    "A2EUQ1WTGCTBG2": "America/Los_Angeles",
    "A1AM78C64UM0Y8": "America/Los_Angeles",
    "A2Q3Y263D00KWC": "America/Sao_Paulo",
    "A1RKKUPIHCS9HS": "Europe/Madrid",
    "A1F83G8C2ARO7P": "Europe/London",
    "A13V1IB3VIYZZH": "Europe/Paris",
    "A1PA6795UKMFR9": "Europe/Berlin",
    "APJ6JRA9NG5V4": "Europe/Rome",
    "A1805IZSGTT6HS": "Europe/Amsterdam",
    "A2NODRKZP88ZB9": "Europe/Stockholm",
    "A1C3SOZRARQ6R3": "Europe/Warsaw",
    "AMEN7PMS3EDWL": "Europe/Brussels",
    "A28R8C7NBKEWEA": "Europe/Dublin",
    "A33AVAJ2PDY3EV": "Europe/Istanbul",
    "A39IBJ37TRP1C6": "Australia/Sydney",
}


class RealtimeFailure(MonitorFailure):
    """A sanitized realtime-layer failure."""


class RealtimeBudgetExhausted(RealtimeFailure):
    """Raised before exceeding the per-run HTTP or elapsed-time budget."""


class RealtimeAdsClient(SellfoxAdsClient):
    """Sellfox client with a bounded HTTP-attempt budget and shorter timeouts."""

    def __init__(self, client_id: str, client_secret: str, logger: logging.Logger):
        super().__init__(client_id, client_secret, logger)
        self.http_attempts = 0
        self._run_http_limit = 0
        self._run_deadline = float("inf")

    def configure_run(self, *, deadline: float, max_http_attempts: int) -> None:
        self.http_attempts = 0
        self._run_deadline = deadline
        self._run_http_limit = max_http_attempts

    @property
    def remaining_http_attempts(self) -> int:
        return max(0, self._run_http_limit - self.http_attempts)

    def _remaining_seconds(self) -> float:
        return self._run_deadline - time.monotonic()

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        purpose: str,
    ) -> dict[str, Any]:
        if self.remaining_http_attempts <= 0:
            raise RealtimeBudgetExhausted("本轮 HTTP 请求额度已用完。")
        remaining = self._remaining_seconds()
        if remaining <= 2:
            raise RealtimeBudgetExhausted("本轮运行时间额度已用完。")
        self.http_attempts += 1
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                json=body,
                timeout=(min(10, max(1, remaining - 1)), min(30, max(1, remaining - 1))),
            )
        except requests.RequestException as exc:
            raise ImportFailure(f"{purpose}网络请求失败。") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise ImportFailure(
                f"{purpose}返回了非 JSON 响应（HTTP {response.status_code}）。"
            ) from exc
        if not isinstance(payload, dict):
            raise ImportFailure(f"{purpose}返回格式异常。")
        if response.status_code >= 400 and str(payload.get("code")) != "40019":
            code = payload.get("code", response.status_code)
            message = as_text(payload.get("msg")) or "HTTP 请求失败"
            raise ImportFailure(f"{purpose}失败：code={code}，{message}")
        return payload

    def post_data(
        self,
        path: str,
        body: dict[str, Any],
        purpose: str,
    ) -> dict[str, Any]:
        for attempt in range(1, 4):
            if self.remaining_http_attempts <= 0 or self._remaining_seconds() <= 2:
                raise RealtimeBudgetExhausted("本轮实时采集额度已用完。")
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
            if str(code) == "40019" and attempt < 3:
                delay = min(10, 5 * attempt)
                if self._remaining_seconds() <= delay + 2:
                    raise RealtimeBudgetExhausted("限流退避会超过本轮时间额度。")
                self.logger.warning("赛狐小时接口限流，%s 秒后重试。", delay)
                time.sleep(delay)
                continue
            raise MonitorFailure(
                f"{purpose}失败：code={code}，{as_text(payload.get('msg'))}"
            )
        raise MonitorFailure(f"{purpose}多次触发限流。")


@dataclass(frozen=True)
class RealtimeConfig:
    enabled: bool
    mature_payload_path: Path
    state_path: Path
    dashboard_payload_path: Path
    max_calls_per_run: int
    max_runtime_seconds: int
    stale_grace_minutes: int
    tier_intervals_minutes: Mapping[str, int]
    new_campaign_days: int
    min_alert_clicks: Decimal
    min_alert_spend: Decimal
    cpc_spike_multiplier: Decimal
    spend_pace_multiplier: Decimal
    budget_alert_threshold: Decimal
    timezone_by_shop: Mapping[str, str]
    timezone_by_marketplace: Mapping[str, str]
    watch_campaign_ids: frozenset[str]


@dataclass(frozen=True)
class CatalogItem:
    shop_id: str
    shop_name: str
    currency: str
    marketplace_id: str
    campaign_id: str
    campaign_name: str
    budget: Decimal
    creation_date: str
    mature_spend: Decimal
    mature_sales: Decimal
    mature_clicks: Decimal
    mature_orders: Decimal
    mature_data_days: int
    mature_cpc: Decimal
    mature_cvr: Decimal
    mature_acos: Decimal
    mature_action_codes: tuple[str, ...]
    mature_priority: str
    tier: str
    lifecycle: str
    timezone_name: str
    timezone_source: str
    listing_stage: str = "unknown"
    listing_total_skus: int = 0
    listing_new_skus: int = 0
    listing_unknown_skus: int = 0

    @property
    def key(self) -> str:
        return f"{self.shop_id}:{self.campaign_id}"

    @property
    def campaign_lifecycle(self) -> str:
        return self.lifecycle


def decimal_value(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        result = Decimal(str(value)) if value not in (None, "") else default
    except (InvalidOperation, TypeError, ValueError):
        return default
    return result if result.is_finite() else default


def number(value: Decimal | int | float | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def resolve_path(value: Any, default: Path) -> Path:
    text = as_text(value)
    path = Path(text) if text else default
    return path if path.is_absolute() else ROOT / path


def config_decimal(raw: Mapping[str, Any], key: str, default: str) -> Decimal:
    value = decimal_value(raw.get(key), Decimal(default))
    if value < 0:
        raise RealtimeFailure(f"realtime.{key} 不能为负数。")
    return value


def load_realtime_config(path: Path) -> RealtimeConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RealtimeFailure("实时监控配置不是有效的 UTF-8 JSON。") from exc
    if not isinstance(raw, dict):
        raise RealtimeFailure("实时监控配置顶层必须是对象。")
    realtime = raw.get("realtime") or {}
    storage = raw.get("storage") or {}
    if not isinstance(realtime, dict) or not isinstance(storage, dict):
        raise RealtimeFailure("realtime 和 storage 必须是对象。")
    intervals_raw = realtime.get("tier_intervals_minutes") or {}
    if not isinstance(intervals_raw, dict):
        raise RealtimeFailure("tier_intervals_minutes 必须是对象。")
    intervals = {
        tier: int(intervals_raw.get(tier, default))
        for tier, default in {"P0": 30, "P1": 120, "P2": 240, "P3": 720}.items()
    }
    if any(value < 15 or value > 1440 for value in intervals.values()):
        raise RealtimeFailure("实时层级间隔必须在 15 到 1440 分钟之间。")
    max_calls = int(realtime.get("max_calls_per_run", 350))
    max_runtime = int(realtime.get("max_runtime_seconds", 480))
    stale_grace = int(realtime.get("stale_grace_minutes", 30))
    new_days = int(realtime.get("new_campaign_days", 14))
    if not 1 <= max_calls <= 1000:
        raise RealtimeFailure("max_calls_per_run 必须在 1 到 1000 之间。")
    if not 60 <= max_runtime <= 1800:
        raise RealtimeFailure("max_runtime_seconds 必须在 60 到 1800 之间。")
    if not 0 <= stale_grace <= 240:
        raise RealtimeFailure("stale_grace_minutes 必须在 0 到 240 之间。")
    if not 1 <= new_days <= 90:
        raise RealtimeFailure("new_campaign_days 必须在 1 到 90 之间。")
    timezone_by_shop = realtime.get("timezone_by_shop") or {}
    timezone_by_marketplace = realtime.get("timezone_by_marketplace") or {}
    if not isinstance(timezone_by_shop, dict) or not isinstance(
        timezone_by_marketplace, dict
    ):
        raise RealtimeFailure("时区映射必须是对象。")
    merged_marketplaces = dict(MARKETPLACE_REPORT_TIMEZONES)
    merged_marketplaces.update(
        {as_text(key): as_text(value) for key, value in timezone_by_marketplace.items()}
    )
    parsed = RealtimeConfig(
        enabled=bool(realtime.get("enabled", True)),
        mature_payload_path=resolve_path(
            storage.get("dashboard_payload_path"), DEFAULT_MATURE_PAYLOAD
        ),
        state_path=resolve_path(
            storage.get("realtime_state_path"), ROOT / "data" / "ads_realtime_state.json"
        ),
        dashboard_payload_path=resolve_path(
            storage.get("realtime_dashboard_payload_path"),
            ROOT / "ads-monitor-web" / "public" / "data" / "ads-realtime.json",
        ),
        max_calls_per_run=max_calls,
        max_runtime_seconds=max_runtime,
        stale_grace_minutes=stale_grace,
        tier_intervals_minutes=intervals,
        new_campaign_days=new_days,
        min_alert_clicks=config_decimal(realtime, "min_alert_clicks", "10"),
        min_alert_spend=config_decimal(realtime, "min_alert_spend", "5"),
        cpc_spike_multiplier=config_decimal(realtime, "cpc_spike_multiplier", "1.5"),
        spend_pace_multiplier=config_decimal(
            realtime, "spend_pace_multiplier", "1.6"
        ),
        budget_alert_threshold=config_decimal(
            realtime, "budget_alert_threshold", "0.85"
        ),
        timezone_by_shop={
            as_text(key): as_text(value) for key, value in timezone_by_shop.items()
        },
        timezone_by_marketplace=merged_marketplaces,
        watch_campaign_ids=frozenset(
            as_text(value) for value in realtime.get("watch_campaign_ids", [])
        ),
    )
    if parsed.cpc_spike_multiplier < 1 or parsed.spend_pace_multiplier < 1:
        raise RealtimeFailure("CPC 与花费速度异常倍数必须不小于 1。")
    if not Decimal("0") < parsed.budget_alert_threshold <= Decimal("1"):
        raise RealtimeFailure("budget_alert_threshold 必须大于 0 且不超过 1。")
    validate_output_paths(parsed)
    return parsed


def normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def validate_output_paths(config: RealtimeConfig) -> None:
    paths = {
        "成熟层": normalized_path(config.mature_payload_path),
        "实时状态": normalized_path(config.state_path),
        "实时发布": normalized_path(config.dashboard_payload_path),
    }
    if len(set(paths.values())) != len(paths):
        raise RealtimeFailure("成熟层、实时状态和实时发布路径必须互不相同。")


def load_mature_payload(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise RealtimeFailure("成熟层 ads-monitor.json 缺失或无效。") from exc
    if not isinstance(payload, dict) or payload.get("meta", {}).get("mode") != "live":
        raise RealtimeFailure("实时层只接受 mode=live 的成熟层数据。")
    if not isinstance(payload.get("campaigns"), list) or not isinstance(
        payload.get("shops"), list
    ):
        raise RealtimeFailure("成熟层缺少 campaigns 或 shops。")
    return payload, hashlib.sha256(raw).hexdigest()


def parse_creation_date(value: str) -> date | None:
    text = as_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace(" ", "T")).date()
    except ValueError:
        return None


def lifecycle_for(value: str, as_of: date, new_days: int) -> str:
    created = parse_creation_date(value)
    if created is None:
        return "unknown"
    age = max(0, (as_of - created).days)
    if age <= new_days:
        return "launch"
    if age <= 30:
        return "growth"
    return "mature"


def priority_rank(value: str) -> int:
    return {"高": 0, "中": 1, "低": 2}.get(as_text(value), 3)


def timezone_for_shop(
    shop_id: str,
    marketplace_id: str,
    config: RealtimeConfig,
) -> tuple[str, str]:
    if config.timezone_by_shop.get(shop_id):
        return config.timezone_by_shop[shop_id], "shop_override"
    if config.timezone_by_marketplace.get(marketplace_id):
        return config.timezone_by_marketplace[marketplace_id], "marketplace_default"
    return "", "unknown"


def campaign_listing_summary(
    payload: Mapping[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in payload.get("advertised_products", []):
        if not isinstance(row, Mapping):
            continue
        key = (as_text(row.get("shop_id")), as_text(row.get("campaign_id")))
        if all(key):
            grouped[key].append(row)
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for key, rows in grouped.items():
        stages = {as_text(row.get("listing_stage")).lower() for row in rows}
        mappings = {as_text(row.get("mapping_status")).lower() for row in rows}
        unknown = sum(
            as_text(row.get("listing_stage")).lower() == "unknown"
            or as_text(row.get("mapping_status")).lower() != "matched"
            for row in rows
        )
        if unknown:
            stage = "unknown"
        elif stages == {"new"}:
            stage = "new"
        elif stages == {"established"}:
            stage = "established"
        elif stages == {"new", "established"}:
            stage = "mixed"
        else:
            stage = "unknown"
        result[key] = {
            "stage": stage,
            "total_skus": len(rows),
            "new_skus": sum(
                as_text(row.get("listing_stage")).lower() == "new" for row in rows
            ),
            "unknown_skus": unknown,
            "mapping_statuses": tuple(sorted(mappings)),
        }
    return result


def build_catalog(
    payload: Mapping[str, Any],
    config: RealtimeConfig,
    *,
    as_of: date,
) -> list[CatalogItem]:
    shops = {
        as_text(item.get("shop_id")): item
        for item in payload.get("shops", [])
        if isinstance(item, dict) and as_text(item.get("shop_id"))
    }
    actions: dict[tuple[str, str], set[str]] = defaultdict(set)
    priorities: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in payload.get("recommendations", []):
        if not isinstance(row, dict):
            continue
        code = as_text(row.get("action_code"))
        if code not in ACTIONABLE_CODES:
            continue
        key = (as_text(row.get("shop_id")), as_text(row.get("campaign_id")))
        if all(key):
            actions[key].add(code)
            priorities[key].append(as_text(row.get("priority")))
    listing_by_campaign = campaign_listing_summary(payload)

    enabled = [
        item
        for item in payload.get("campaigns", [])
        if isinstance(item, dict)
        and as_text(item.get("shop_id")) in shops
        and as_text(item.get("campaign_id"))
        and as_text(item.get("state")).lower() == "enabled"
    ]
    top_by_shop: dict[str, tuple[Decimal, str]] = {}
    for row in enabled:
        shop_id = as_text(row.get("shop_id"))
        candidate = (decimal_value(row.get("spend")), as_text(row.get("campaign_id")))
        if shop_id not in top_by_shop or candidate > top_by_shop[shop_id]:
            top_by_shop[shop_id] = candidate

    result: list[CatalogItem] = []
    for row in enabled:
        shop_id = as_text(row.get("shop_id"))
        campaign_id = as_text(row.get("campaign_id"))
        shop = shops[shop_id]
        key = (shop_id, campaign_id)
        lifecycle = lifecycle_for(
            as_text(row.get("creation_date")), as_of, config.new_campaign_days
        )
        listing = listing_by_campaign.get(
            key,
            {
                "stage": "unknown",
                "total_skus": 0,
                "new_skus": 0,
                "unknown_skus": 1,
            },
        )
        watch_key = f"{shop_id}:{campaign_id}"
        if watch_key in config.watch_campaign_ids or campaign_id in config.watch_campaign_ids:
            tier = "P0"
        elif (
            actions.get(key)
            or lifecycle == "launch"
            or listing["stage"] in {"new", "mixed"}
            or top_by_shop[shop_id][1] == campaign_id
        ):
            tier = "P1"
        elif decimal_value(row.get("spend")) > 0:
            tier = "P2"
        else:
            tier = "P3"
        timezone_name, timezone_source = timezone_for_shop(
            shop_id, as_text(shop.get("marketplace_id")), config
        )
        priority = min(priorities.get(key, [""]), key=priority_rank)
        result.append(
            CatalogItem(
                shop_id=shop_id,
                shop_name=as_text(shop.get("shop_name")) or shop_id,
                currency=as_text(shop.get("currency")),
                marketplace_id=as_text(shop.get("marketplace_id")),
                campaign_id=campaign_id,
                campaign_name=as_text(row.get("campaign_name")) or campaign_id,
                budget=decimal_value(row.get("budget")),
                creation_date=as_text(row.get("creation_date")),
                mature_spend=decimal_value(row.get("spend")),
                mature_sales=decimal_value(row.get("sales")),
                mature_clicks=decimal_value(row.get("clicks")),
                mature_orders=decimal_value(row.get("orders")),
                mature_data_days=max(0, int(decimal_value(row.get("data_days")))),
                mature_cpc=decimal_value(row.get("cpc")),
                mature_cvr=decimal_value(row.get("cvr")),
                mature_acos=decimal_value(row.get("acos")),
                mature_action_codes=tuple(sorted(actions.get(key, set()))),
                mature_priority=priority,
                tier=tier,
                lifecycle=lifecycle,
                timezone_name=timezone_name,
                timezone_source=timezone_source,
                listing_stage=as_text(listing["stage"]) or "unknown",
                listing_total_skus=int(listing["total_skus"]),
                listing_new_skus=int(listing["new_skus"]),
                listing_unknown_skus=int(listing["unknown_skus"]),
            )
        )
    return sorted(result, key=lambda item: (item.shop_id, item.campaign_id))


def parse_timestamp(value: Any) -> datetime | None:
    text = as_text(value)
    if not text:
        return None
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def local_clock(
    item: CatalogItem,
    now_utc: datetime,
    loader: Callable[[str], Any] = ZoneInfo,
) -> datetime | None:
    if not item.timezone_name:
        return None
    try:
        zone = loader(item.timezone_name)
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return None
    return now_utc.astimezone(zone)


def empty_campaign_state(item: CatalogItem) -> dict[str, Any]:
    return {
        "shop_id": item.shop_id,
        "campaign_id": item.campaign_id,
        "last_attempt_at": "",
        "last_success_at": "",
        "last_empty_at": "",
        "next_due_at": "",
        "consecutive_failures": 0,
        "last_error_code": "",
        "last_error": "",
        "report_date": "",
        "latest_hour": None,
        "elapsed_hours_at_fetch": None,
        "rows_count": 0,
        "empty_success": False,
        "metrics": {},
    }


def normalize_saved_state(item: CatalogItem, value: Mapping[str, Any]) -> dict[str, Any]:
    state = dict(value or empty_campaign_state(item))
    if (
        state.get("empty_success")
        and int(state.get("rows_count") or 0) == 0
        and not state.get("last_empty_at")
    ):
        empty_at = as_text(state.get("last_attempt_at")) or as_text(
            state.get("last_success_at")
        )
        state.update(
            {
                "last_empty_at": empty_at,
                "last_success_at": "",
                "next_due_at": empty_at,
                "last_error_code": "EMPTY_RESPONSE",
                "last_error": "接口成功但尚未返回当日活动小时行。",
                "metrics": {},
            }
        )
    return state


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "campaigns": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RealtimeFailure("实时状态文件无效；为保护旧状态，已停止运行。") from exc
    if not isinstance(state, dict) or not isinstance(state.get("campaigns"), dict):
        raise RealtimeFailure("实时状态文件结构无效；为保护旧状态，已停止运行。")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise RealtimeFailure("实时状态文件版本不兼容。")
    return state


def campaign_is_fresh(
    item: CatalogItem,
    state: Mapping[str, Any],
    config: RealtimeConfig,
    now_utc: datetime,
) -> bool:
    success = parse_timestamp(state.get("last_success_at"))
    if success is None:
        return False
    max_age = config.tier_intervals_minutes[item.tier] + config.stale_grace_minutes
    if (now_utc - success).total_seconds() > max_age * 60:
        return False
    clock = local_clock(item, now_utc)
    return clock is not None and as_text(state.get("report_date")) == clock.date().isoformat()


def campaign_is_due(
    item: CatalogItem,
    state: Mapping[str, Any],
    now_utc: datetime,
) -> bool:
    clock = local_clock(item, now_utc)
    if clock is None:
        return False
    if as_text(state.get("report_date")) != clock.date().isoformat():
        return True
    next_due = parse_timestamp(state.get("next_due_at"))
    return next_due is None or next_due <= now_utc


def due_rank(
    item: CatalogItem,
    state: Mapping[str, Any],
    config: RealtimeConfig,
    now_utc: datetime,
) -> tuple[Any, ...]:
    next_due = parse_timestamp(state.get("next_due_at"))
    interval = config.tier_intervals_minutes[item.tier]
    overdue = 10**9 if next_due is None else (now_utc - next_due).total_seconds() / 60
    return (
        -overdue / max(1, interval),
        TIER_ORDER[item.tier],
        priority_rank(item.mature_priority),
        -item.mature_spend,
        item.campaign_id,
    )


def select_due_campaigns(
    catalog: Sequence[CatalogItem],
    states: Mapping[str, Mapping[str, Any]],
    config: RealtimeConfig,
    now_utc: datetime,
    limit: int,
) -> tuple[list[CatalogItem], int, int]:
    grouped: dict[str, list[CatalogItem]] = defaultdict(list)
    for item in catalog:
        state = states.get(item.key, {})
        if campaign_is_due(item, state, now_utc):
            grouped[item.shop_id].append(item)
    for shop_items in grouped.values():
        shop_items.sort(key=lambda item: due_rank(item, states.get(item.key, {}), config, now_utc))
    selected: list[CatalogItem] = []
    shop_ids = sorted(
        grouped,
        key=lambda shop_id: (
            0
            if not any(
                campaign_is_fresh(item, states.get(item.key, {}), config, now_utc)
                for item in catalog
                if item.shop_id == shop_id
            )
            else 1,
            due_rank(grouped[shop_id][0], states.get(grouped[shop_id][0].key, {}), config, now_utc),
            shop_id,
        ),
    )
    while shop_ids and len(selected) < limit:
        next_round: list[str] = []
        for shop_id in shop_ids:
            if len(selected) >= limit:
                next_round.append(shop_id)
                continue
            selected.append(grouped[shop_id].pop(0))
            if grouped[shop_id]:
                next_round.append(shop_id)
        shop_ids = next_round
    due_total = sum(len(items) for items in grouped.values()) + len(selected)
    overdue = sum(
        1
        for item in catalog
        if campaign_is_due(item, states.get(item.key, {}), now_utc)
        and parse_timestamp(states.get(item.key, {}).get("last_success_at")) is not None
    )
    return selected, max(0, due_total - len(selected)), overdue


def normalize_campaign_response(
    raw_items: Any,
    *,
    item: CatalogItem,
    report_date: date,
    run_id: str,
    ingested_at: str,
) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list) or any(not isinstance(row, dict) for row in raw_items):
        raise RealtimeFailure("小时活动报告 itemList 格式异常。")
    rows = [
        normalize_hourly_row(
            row,
            aggregation_type="campaign",
            shop_id=item.shop_id,
            report_date=report_date,
            campaign_id=item.campaign_id,
            run_id=run_id,
            ingested_at=ingested_at,
        )
        for row in raw_items
    ]
    keys = [(row["report_date"], row["report_hour"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise DataQualityFailure("小时活动报告包含重复小时。")
    return sorted(rows, key=lambda row: (row["report_date"], row["report_hour"]))


def aggregate_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    totals = {
        key: sum((decimal_value(row.get(key)) for row in rows), Decimal("0"))
        for key in ("spend", "clicks", "impressions", "orders", "sales", "units")
    }
    totals["cpc"] = totals["spend"] / totals["clicks"] if totals["clicks"] else None
    totals["cvr"] = totals["orders"] / totals["clicks"] if totals["clicks"] else None
    totals["acos"] = totals["spend"] / totals["sales"] if totals["sales"] else None
    return {key: number(value) for key, value in totals.items()}


def update_success_state(
    state: dict[str, Any],
    item: CatalogItem,
    rows: Sequence[Mapping[str, Any]],
    report_date: date,
    now_utc: datetime,
    config: RealtimeConfig,
) -> None:
    timestamp = iso_utc(now_utc)
    report_clock = local_clock(item, now_utc)
    if report_clock is None:
        raise RealtimeFailure("成功响应无法关联有效广告报表时区。")
    state.update(
        {
            "shop_id": item.shop_id,
            "campaign_id": item.campaign_id,
            "last_attempt_at": timestamp,
            "last_success_at": timestamp,
            "last_empty_at": "",
            "next_due_at": iso_utc(
                now_utc + timedelta(minutes=config.tier_intervals_minutes[item.tier])
            ),
            "consecutive_failures": 0,
            "last_error_code": "",
            "last_error": "",
            "report_date": report_date.isoformat(),
            "latest_hour": max((int(row["report_hour"]) for row in rows), default=None),
            "elapsed_hours_at_fetch": max(1, min(24, report_clock.hour)),
            "rows_count": len(rows),
            "empty_success": not rows,
            "metrics": aggregate_rows(rows),
        }
    )


def update_empty_state(
    state: dict[str, Any],
    item: CatalogItem,
    report_date: date,
    now_utc: datetime,
) -> None:
    had_current_rows = (
        as_text(state.get("report_date")) == report_date.isoformat()
        and int(state.get("rows_count") or 0) > 0
    )
    state.update(
        {
            "shop_id": item.shop_id,
            "campaign_id": item.campaign_id,
            "last_attempt_at": iso_utc(now_utc),
            "last_empty_at": iso_utc(now_utc),
            "next_due_at": iso_utc(now_utc + timedelta(minutes=15)),
            "consecutive_failures": 0,
            "last_error_code": (
                "EMPTY_RESPONSE_AFTER_DATA" if had_current_rows else "EMPTY_RESPONSE"
            ),
            "last_error": (
                "同一站点日此前已有小时数据，本次却返回空结果；已保留旧指标。"
                if had_current_rows
                else "接口成功但尚未返回当日活动小时行。"
            ),
            "pending_report_date": report_date.isoformat(),
            "empty_success": True,
        }
    )


def update_failure_state(
    state: dict[str, Any],
    item: CatalogItem,
    now_utc: datetime,
    code: str,
    message: str,
) -> None:
    failures = int(state.get("consecutive_failures") or 0) + 1
    backoff = min(60, 15 * (2 ** min(failures - 1, 2)))
    state.update(
        {
            "shop_id": item.shop_id,
            "campaign_id": item.campaign_id,
            "last_attempt_at": iso_utc(now_utc),
            "next_due_at": iso_utc(now_utc + timedelta(minutes=backoff)),
            "consecutive_failures": failures,
            "last_error_code": code,
            "last_error": message[:300],
        }
    )


def freshness_status(
    item: CatalogItem,
    state: Mapping[str, Any],
    config: RealtimeConfig,
    now_utc: datetime,
) -> tuple[str, float | None]:
    success = parse_timestamp(state.get("last_success_at"))
    if success is None:
        if state.get("last_empty_at"):
            return "empty", None
        return ("error" if state.get("last_error") else "never"), None
    age = max(0.0, (now_utc - success).total_seconds() / 60)
    attempt = parse_timestamp(state.get("last_attempt_at"))
    if state.get("last_error") and attempt is not None and attempt > success:
        return "error", age
    return (
        "fresh" if campaign_is_fresh(item, state, config, now_utc) else "stale",
        age,
    )


def baseline(item: CatalogItem) -> dict[str, Any]:
    days = Decimal(item.mature_data_days or 1)
    return {
        "data_days": item.mature_data_days,
        "daily_spend": number(item.mature_spend / days),
        "daily_sales": number(item.mature_sales / days),
        "daily_clicks": number(item.mature_clicks / days),
        "daily_orders": number(item.mature_orders / days),
        "cpc": number(item.mature_cpc),
        "cvr": number(item.mature_cvr),
        "acos": number(item.mature_acos),
    }


def alert_id(item: CatalogItem, code: str, report_date: str) -> str:
    raw = f"{item.shop_id}|{item.campaign_id}|{code}|{report_date}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def make_alert(
    item: CatalogItem,
    state: Mapping[str, Any],
    *,
    code: str,
    severity: str,
    metric: str,
    current: Any,
    baseline_value: Any,
    deviation_pct: Any,
    handling: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "alert_id": alert_id(item, code, as_text(state.get("report_date"))),
        "shop_id": item.shop_id,
        "shop_name": item.shop_name,
        "currency": item.currency,
        "campaign_id": item.campaign_id,
        "campaign_name": item.campaign_name,
        "campaign_lifecycle": item.campaign_lifecycle,
        "listing_stage": item.listing_stage,
        "severity": severity,
        "alert_code": code,
        "metric": metric,
        "current_value": current,
        "baseline_value": baseline_value,
        "deviation_pct": deviation_pct,
        "observed_at": as_text(state.get("last_success_at")),
        "handling": handling,
        "reason": reason,
    }


def handling_for_anomaly(item: CatalogItem) -> str:
    if item.listing_stage == "unknown":
        return "BLOCK"
    if item.lifecycle == "launch" or item.listing_stage in {"new", "mixed"}:
        return "WATCH"
    return "BLOCK" if set(item.mature_action_codes) & SCALE_CODES else "WARN"


def campaign_snapshot(
    item: CatalogItem,
    state: Mapping[str, Any],
    config: RealtimeConfig,
    now_utc: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    status, age = freshness_status(item, state, config, now_utc)
    metrics = dict(state.get("metrics") or {})
    base = baseline(item)
    alerts: list[dict[str, Any]] = []
    report_date = as_text(state.get("report_date"))
    latest_hour = state.get("latest_hour")
    signals: list[str] = []
    actionable = bool(item.mature_action_codes)
    if actionable and item.listing_stage == "unknown":
        alerts.append(
            make_alert(
                item,
                state,
                code="PRODUCT_LIFECYCLE_UNKNOWN",
                severity="critical",
                metric="listing_stage",
                current="unknown",
                baseline_value="openDate",
                deviation_pct=None,
                handling="BLOCK",
                reason="广告 SKU 未能通过 shopId+ASIN+SKU 唯一关联上架时间，阻断自动缩量。",
            )
        )
        signals.append("PRODUCT_LIFECYCLE_UNKNOWN")
    if actionable and status != "fresh":
        alerts.append(
            make_alert(
                item,
                state,
                code="REALTIME_NOT_FRESH",
                severity="critical",
                metric="freshness",
                current=status,
                baseline_value=f"{config.tier_intervals_minutes[item.tier]}m",
                deviation_pct=None,
                handling="BLOCK",
                reason="实时层未达到新鲜度要求，阻断进入执行确认。",
            )
        )
        signals.append("REALTIME_NOT_FRESH")
    if status == "fresh" and state.get("rows_count", 0) and latest_hour is not None:
        clicks = decimal_value(metrics.get("clicks"))
        spend = decimal_value(metrics.get("spend"))
        orders = decimal_value(metrics.get("orders"))
        cpc = decimal_value(metrics.get("cpc"))
        elapsed_hours = int(state.get("elapsed_hours_at_fetch") or int(latest_hour) + 1)
        elapsed_ratio = Decimal(max(1, min(24, elapsed_hours))) / Decimal(24)
        projected_spend = spend / elapsed_ratio if elapsed_ratio else Decimal("0")
        daily_spend = decimal_value(base.get("daily_spend"))
        if (
            clicks >= config.min_alert_clicks
            and item.mature_cpc > 0
            and cpc >= item.mature_cpc * config.cpc_spike_multiplier
        ):
            deviation = (cpc / item.mature_cpc - 1) * 100
            alerts.append(
                make_alert(
                    item,
                    state,
                    code="CPC_SPIKE",
                    severity="high",
                    metric="cpc",
                    current=number(cpc),
                    baseline_value=number(item.mature_cpc),
                    deviation_pct=number(deviation),
                    handling=handling_for_anomaly(item),
                    reason="当日暂定 CPC 明显高于成熟期基线；新品只观察，不直接降价。",
                )
            )
            signals.append("CPC_SPIKE")
        if (
            spend >= config.min_alert_spend
            and daily_spend > 0
            and projected_spend >= daily_spend * config.spend_pace_multiplier
        ):
            deviation = (projected_spend / daily_spend - 1) * 100
            alerts.append(
                make_alert(
                    item,
                    state,
                    code="SPEND_PACE_HIGH",
                    severity="high",
                    metric="projected_spend",
                    current=number(projected_spend),
                    baseline_value=number(daily_spend),
                    deviation_pct=number(deviation),
                    handling=handling_for_anomaly(item),
                    reason="按已完成小时外推的花费速度高于成熟期日均基线。",
                )
            )
            signals.append("SPEND_PACE_HIGH")
        if item.budget > 0 and spend / item.budget >= config.budget_alert_threshold:
            utilization = spend / item.budget
            alerts.append(
                make_alert(
                    item,
                    state,
                    code="BUDGET_NEAR_LIMIT",
                    severity="medium",
                    metric="budget_utilization",
                    current=number(utilization),
                    baseline_value=number(config.budget_alert_threshold),
                    deviation_pct=number((utilization - config.budget_alert_threshold) * 100),
                    handling=handling_for_anomaly(item),
                    reason="当日暂定花费已接近活动预算上限，需结合盈利与生命周期复核。",
                )
            )
            signals.append("BUDGET_NEAR_LIMIT")
        if clicks >= config.min_alert_clicks and spend >= config.min_alert_spend and orders == 0:
            alerts.append(
                make_alert(
                    item,
                    state,
                    code="ORDERS_NOT_ATTRIBUTED_YET",
                    severity="medium",
                    metric="orders",
                    current=0,
                    baseline_value=number(decimal_value(base.get("daily_orders"))),
                    deviation_pct=None,
                    handling="WATCH",
                    reason="当日订单仍可能延迟归因，只预警，不据此直接降价。",
                )
            )
            signals.append("ORDERS_NOT_ATTRIBUTED_YET")
    empty_success = bool(state.get("empty_success"))
    if empty_success:
        signals.append("NO_ACTIVITY_ROWS")
    if any(alert["handling"] == "BLOCK" for alert in alerts):
        gate = "BLOCK"
    elif actionable and (
        alerts
        or item.lifecycle == "launch"
        or item.listing_stage in {"new", "mixed"}
        or empty_success
    ):
        gate = "REVIEW"
    elif actionable and status == "fresh":
        gate = "NO_OBJECTION"
    elif actionable:
        gate = "BLOCK"
    else:
        gate = "MONITOR_ONLY"
    snapshot = {
        "shop_id": item.shop_id,
        "shop_name": item.shop_name,
        "currency": item.currency,
        "marketplace_id": item.marketplace_id,
        "campaign_id": item.campaign_id,
        "campaign_name": item.campaign_name,
        "tier": item.tier,
        "lifecycle": item.lifecycle,
        "campaign_lifecycle": item.campaign_lifecycle,
        "listing_stage": item.listing_stage,
        "product_lifecycle": {
            "listing_stage": item.listing_stage,
            "total_skus": item.listing_total_skus,
            "new_skus": item.listing_new_skus,
            "unknown_skus": item.listing_unknown_skus,
        },
        "timezone": item.timezone_name,
        "timezone_source": item.timezone_source,
        "mature_action_codes": list(item.mature_action_codes),
        "mature_priority": item.mature_priority,
        "freshness": {
            "status": status,
            "last_success_at": as_text(state.get("last_success_at")),
            "age_minutes": round(age, 1) if age is not None else None,
            "expected_interval_minutes": config.tier_intervals_minutes[item.tier],
            "last_error_code": as_text(state.get("last_error_code")),
        },
        "today": {
            "report_date": report_date,
            "latest_hour": latest_hour,
            "elapsed_hours_at_fetch": state.get("elapsed_hours_at_fetch"),
            "rows_count": int(state.get("rows_count") or 0),
            "empty_success": bool(state.get("empty_success")),
            **metrics,
        },
        "mature_baseline": base,
        "signals": signals,
        "execution_gate": gate,
    }
    return snapshot, alerts


def build_payload(
    catalog: Sequence[CatalogItem],
    states: Mapping[str, Mapping[str, Any]],
    mature_payload: Mapping[str, Any],
    mature_hash: str,
    config: RealtimeConfig,
    now_utc: datetime,
    run_stats: Mapping[str, Any],
) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    for item in catalog:
        snapshot, item_alerts = campaign_snapshot(
            item, states.get(item.key, {}), config, now_utc
        )
        snapshots.append(snapshot)
        alerts.extend(item_alerts)
    fresh = [item for item in snapshots if item["freshness"]["status"] == "fresh"]
    stale = [item for item in snapshots if item["freshness"]["status"] == "stale"]
    never = [item for item in snapshots if item["freshness"]["status"] == "never"]
    errors = [item for item in snapshots if item["freshness"]["status"] == "error"]
    empty = [item for item in snapshots if item["freshness"]["status"] == "empty"]
    shops: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in snapshots:
        shops[item["shop_id"]].append(item)
    mature_shops = {
        as_text(row.get("shop_id")): row
        for row in mature_payload.get("shops", [])
        if isinstance(row, dict) and as_text(row.get("shop_id"))
    }
    mature_coverage = {
        as_text(row.get("shop_id")): row
        for row in mature_payload.get("shop_coverage", [])
        if isinstance(row, dict) and as_text(row.get("shop_id"))
    }
    shop_coverage = []
    for shop_id, mature_shop in sorted(mature_shops.items()):
        rows = shops.get(shop_id, [])
        covered = sum(row["freshness"]["status"] == "fresh" for row in rows)
        observed = max(
            (row["freshness"]["last_success_at"] for row in rows), default=""
        )
        if rows and covered == len(rows):
            shop_status = "complete"
            message = "本店全部启用活动已达到各自实时层新鲜度目标。"
        elif rows and covered:
            shop_status = "partial"
            message = "本店仅部分活动达到实时层新鲜度目标。"
        elif rows:
            shop_status = "unavailable"
            message = "本店没有可用于实时判断的新鲜活动数据。"
        elif int(mature_coverage.get(shop_id, {}).get("failed_calls") or 0) > 0:
            shop_status = "unavailable"
            message = "成熟层读取失败，无法确认本店是否存在启用 SP 活动。"
        else:
            shop_status = "not_applicable"
            message = "本店当前没有启用 SP 活动，不纳入实时采集分母。"
        shop_coverage.append(
            {
                "shop_id": shop_id,
                "shop_name": as_text(mature_shop.get("shop_name")) or shop_id,
                "currency": as_text(mature_shop.get("currency")),
                "status": shop_status,
                "observed_at": observed,
                "covered_campaigns": covered,
                "eligible_campaigns": len(rows),
                "message": message,
            }
        )
    covered_shops = sum(
        row["covered_campaigns"] > 0
        for row in shop_coverage
        if row["eligible_campaigns"] > 0
    )
    not_applicable_shops = sum(
        row["status"] == "not_applicable" for row in shop_coverage
    )
    unavailable_shops = sum(row["status"] == "unavailable" for row in shop_coverage)
    latest_success = max(
        (row["freshness"]["last_success_at"] for row in snapshots), default=""
    )
    unknown_timezones = sum(not item.timezone_name for item in catalog)
    if not fresh:
        status = "unavailable"
    elif (
        len(fresh) == len(snapshots)
        and not run_stats.get("failed")
        and not unavailable_shops
    ):
        status = "complete"
    else:
        status = "partial"
    mature_meta = mature_payload.get("meta") or {}
    calls = {
        "budget": config.max_calls_per_run,
        "attempted": int(run_stats.get("attempted") or 0),
        "succeeded": int(run_stats.get("succeeded") or 0),
        "failed": int(run_stats.get("failed") or 0),
        "quality_failures": int(run_stats.get("quality_failures") or 0),
        "empty_responses": int(run_stats.get("empty_responses") or 0),
        "http_attempts": int(run_stats.get("http_attempts") or 0),
    }
    coverage = {
        "catalog_campaigns": len(catalog),
        "fresh": len(fresh),
        "stale": len(stale),
        "never_seen": len(never),
        "errors": len(errors),
        "empty_responses": len(empty),
        "backlog": int(run_stats.get("backlog") or 0),
        "overdue": int(run_stats.get("overdue") or 0),
        "unknown_timezones": unknown_timezones,
        "capacity_required_calls_per_run": round(
            sum(
                15 / config.tier_intervals_minutes[item.tier]
                for item in catalog
            ),
            1,
        ),
    }
    alerts.sort(
        key=lambda row: (
            SEVERITY_ORDER.get(row["severity"], 9),
            0 if row["handling"] == "BLOCK" else 1,
            -(float(row["deviation_pct"]) if row["deviation_pct"] is not None else 0),
            row["shop_name"],
            row["campaign_name"],
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "title": "赛狐 SP 广告实时监控层",
            "mode": "live",
            "layer": "realtime",
            "run_id": as_text(run_stats.get("run_id")),
            "generated_at": iso_utc(now_utc),
            "observed_at": latest_success,
            "window_start": min(
                (row["today"]["report_date"] for row in snapshots if row["today"]["report_date"]),
                default="",
            ),
            "report_date": max(
                (row["today"]["report_date"] for row in snapshots if row["today"]["report_date"]),
                default="",
            ),
            "status": status,
            "layer_role": "warning_blocking_confirmation_only",
            "execution_policy": "read_only",
            "schedule_minutes": 15,
            "stale_after_minutes": 45,
            "expires_at": iso_utc(now_utc + timedelta(minutes=45)),
            "covered_shops": covered_shops,
            "eligible_shops": len(shops),
            "total_shops": len(mature_shops),
            "not_applicable_shops": not_applicable_shops,
            "unavailable_shops": unavailable_shops,
            "covered_campaigns": len(fresh),
            "eligible_campaigns": len(catalog),
            "requested_calls": calls["attempted"],
            "successful_calls": calls["succeeded"],
            "failed_calls": calls["failed"],
            "quality_failures": calls["quality_failures"],
            "calls": calls,
            "coverage": coverage,
            "mature_ref": {
                "run_id": as_text(mature_meta.get("run_id")),
                "generated_at": as_text(mature_meta.get("generated_at")),
                "source_end_date": as_text(mature_meta.get("source_end_date")),
                "sha256": mature_hash,
            },
            "source_note": (
                "Sellfox SP campaign hourly data is provisional. It can warn, block, or "
                "confirm review, but it never directly changes ads."
            ),
        },
        "alerts": alerts,
        "campaign_snapshots": snapshots,
        "campaigns": snapshots,
        "listing_coverage": mature_payload.get("listing_coverage") or {},
        "policy": mature_payload.get("policy") or {},
        "shop_coverage": shop_coverage,
        "sources": [
            {
                "name": "SP活动小时数据",
                "url": "https://sellfoxapi.apifox.cn/",
                "endpoint": SP_HOUR_CAMPAIGN_PATH,
            }
        ],
    }


def validate_realtime_payload(payload: Mapping[str, Any]) -> None:
    meta = payload.get("meta") if isinstance(payload, dict) else None
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or not isinstance(meta, dict)
        or meta.get("mode") != "live"
        or meta.get("layer") != "realtime"
        or not isinstance(payload.get("alerts"), list)
        or not isinstance(payload.get("shop_coverage"), list)
    ):
        raise RealtimeFailure("实时层待发布 JSON 未通过安全校验。")


def atomic_write_json(payload: Mapping[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise RealtimeFailure(f"原子发布失败：{path.name}") from exc
    return path


def setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("SellfoxAdsRealtime")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)
    log_dir = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "SellfoxTK" / "logs"
    for path in (log_dir / "sellfox_ads_realtime.log", ROOT / "logs" / "sellfox_ads_realtime.log"):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=10, encoding="utf-8")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            break
        except OSError:
            continue
    return logger


def collect_once(
    config: RealtimeConfig,
    *,
    client: Any,
    mature_payload: Mapping[str, Any],
    mature_hash: str,
    state: dict[str, Any],
    now_utc: datetime,
    logger: logging.Logger,
    shop_ids: frozenset[str] = frozenset(),
    campaign_ids: frozenset[str] = frozenset(),
    clock: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current_time = clock or (lambda: datetime.now(timezone.utc))
    catalog = build_catalog(mature_payload, config, as_of=now_utc.date())
    if shop_ids:
        catalog = [item for item in catalog if item.shop_id in shop_ids]
    if campaign_ids:
        catalog = [item for item in catalog if item.campaign_id in campaign_ids]
    if not catalog:
        raise RealtimeFailure("筛选后没有可采集的启用 SP 活动。")
    old_states = state.get("campaigns") or {}
    states = {
        item.key: normalize_saved_state(item, old_states.get(item.key) or {})
        for item in catalog
    }
    run_id = now_utc.strftime("%Y%m%dT%H%M%SZ")
    timezone_failures = 0
    for item in catalog:
        if local_clock(item, now_utc) is not None:
            continue
        update_failure_state(
            states[item.key],
            item,
            now_utc,
            "TIMEZONE_UNKNOWN",
            "未配置有效广告报表时区。",
        )
        timezone_failures += 1
    selected, backlog, overdue = select_due_campaigns(
        catalog, states, config, now_utc, config.max_calls_per_run
    )
    stats = {
        "run_id": run_id,
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "quality_failures": 0,
        "timezone_failures": timezone_failures,
        "empty_responses": 0,
        "http_attempts": 0,
        "backlog": backlog,
        "overdue": overdue,
    }
    started = time.monotonic()
    if hasattr(client, "configure_run"):
        client.configure_run(
            deadline=started + config.max_runtime_seconds,
            max_http_attempts=config.max_calls_per_run + 1,
        )
    for index, item in enumerate(selected):
        if time.monotonic() - started >= config.max_runtime_seconds:
            stats["backlog"] += len(selected) - index
            logger.warning("已达到单轮运行时限，剩余活动保留到下一轮。")
            break
        if getattr(client, "remaining_http_attempts", 1) <= 0:
            stats["backlog"] += len(selected) - index
            logger.warning("已达到单轮 HTTP 请求上限，剩余活动保留到下一轮。")
            break
        attempt_at = current_time().astimezone(timezone.utc)
        report_clock = local_clock(item, attempt_at)
        if report_clock is None:
            stats["backlog"] += 1
            continue
        stats["attempted"] += 1
        try:
            data = client.post_data(
                SP_HOUR_CAMPAIGN_PATH,
                {
                    "aggregationType": "campaign",
                    "shopId": item.shop_id,
                    "date": report_clock.date().isoformat(),
                    "campaignId": item.campaign_id,
                },
                f"读取店铺 {item.shop_id} 活动 {item.campaign_id} 当日小时数据",
            )
            rows = normalize_campaign_response(
                data.get("itemList"),
                item=item,
                report_date=report_clock.date(),
                run_id=run_id,
                ingested_at=iso_utc(attempt_at),
            )
            if rows:
                update_success_state(
                    states[item.key], item, rows, report_clock.date(), attempt_at, config
                )
            else:
                update_empty_state(
                    states[item.key], item, report_clock.date(), attempt_at
                )
                stats["empty_responses"] += 1
            stats["succeeded"] += 1
        except RealtimeBudgetExhausted:
            stats["attempted"] -= 1
            stats["backlog"] += len(selected) - index
            logger.warning("已达到单轮实时采集额度，剩余活动保留到下一轮。")
            break
        except DataQualityFailure as exc:
            update_failure_state(states[item.key], item, attempt_at, "DATA_QUALITY", str(exc))
            stats["quality_failures"] += 1
            stats["failed"] += 1
            logger.warning("%s/%s 小时数据校验失败：%s", item.shop_id, item.campaign_id, exc)
        except MonitorFailure as exc:
            update_failure_state(states[item.key], item, attempt_at, "API_ERROR", str(exc))
            stats["failed"] += 1
            logger.warning("%s/%s 小时数据读取失败：%s", item.shop_id, item.campaign_id, exc)
    completed_at = current_time().astimezone(timezone.utc)
    stats["http_attempts"] = int(getattr(client, "http_attempts", stats["attempted"]))
    new_state = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": iso_utc(completed_at),
        "mature_ref": {
            "run_id": as_text(mature_payload.get("meta", {}).get("run_id")),
            "sha256": mature_hash,
        },
        "campaigns": states,
    }
    payload = build_payload(
        catalog, states, mature_payload, mature_hash, config, completed_at, stats
    )
    return new_state, payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="赛狐 SP 广告独立实时监控层（只读）")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--mature-payload", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-calls", type=int)
    parser.add_argument("--shop-id", action="append", default=[])
    parser.add_argument("--campaign-id", action="append", default=[])
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logger = setup_logging(args.verbose)
    try:
        config = load_realtime_config(args.config.resolve())
        if not config.enabled:
            raise RealtimeFailure("realtime.enabled=false，实时采集已由配置关闭。")
        official_state_path = normalized_path(config.state_path)
        official_output_path = normalized_path(config.dashboard_payload_path)
        if args.mature_payload:
            config = replace(config, mature_payload_path=args.mature_payload.resolve())
        if args.state:
            config = replace(config, state_path=args.state.resolve())
        if args.output:
            config = replace(config, dashboard_payload_path=args.output.resolve())
        if args.max_calls is not None:
            if not 1 <= args.max_calls <= 1000:
                raise RealtimeFailure("--max-calls 必须在 1 到 1000 之间。")
            config = replace(config, max_calls_per_run=args.max_calls)
        validate_output_paths(config)
        scoped = bool(args.shop_id or args.campaign_id)
        if scoped and not args.plan_only and not (args.state and args.output):
            raise RealtimeFailure(
                "限定店铺或活动运行时必须同时指定独立 --state 和 --output，"
                "避免覆盖全店铺实时状态。"
            )
        if scoped and not args.plan_only and (
            normalized_path(config.state_path) == official_state_path
            or normalized_path(config.dashboard_payload_path) == official_output_path
        ):
            raise RealtimeFailure("限定范围运行必须使用与正式全量路径不同的输出文件。")
        mature_payload, mature_hash = load_mature_payload(config.mature_payload_path)
        now_utc = datetime.now(timezone.utc)
        catalog = build_catalog(mature_payload, config, as_of=now_utc.date())
        if args.shop_id:
            catalog = [item for item in catalog if item.shop_id in set(args.shop_id)]
        if args.campaign_id:
            catalog = [item for item in catalog if item.campaign_id in set(args.campaign_id)]
        state = load_state(config.state_path)
        if args.plan_only:
            selected, backlog, overdue = select_due_campaigns(
                catalog,
                state.get("campaigns") or {},
                config,
                now_utc,
                config.max_calls_per_run,
            )
            required_calls = round(
                sum(
                    15 / config.tier_intervals_minutes[item.tier]
                    for item in catalog
                ),
                1,
            )
            print(
                json.dumps(
                    {
                        "mode": "plan_only",
                        "eligible_campaigns": len(catalog),
                        "selected_calls": len(selected),
                        "backlog": backlog,
                        "overdue": overdue,
                        "steady_state_calls_per_run": required_calls,
                        "capacity_headroom": round(
                            config.max_calls_per_run - required_calls, 1
                        ),
                        "tiers": dict(
                            sorted(
                                (
                                    tier,
                                    sum(item.tier == tier for item in catalog),
                                )
                                for tier in TIER_ORDER
                            )
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        client_id, client_secret = load_api_credentials()
        client = RealtimeAdsClient(client_id, client_secret, logger)
        try:
            with single_instance():
                new_state, payload = collect_once(
                    config,
                    client=client,
                    mature_payload=mature_payload,
                    mature_hash=mature_hash,
                    state=state,
                    now_utc=now_utc,
                    logger=logger,
                    shop_ids=frozenset(args.shop_id),
                    campaign_ids=frozenset(args.campaign_id),
                )
                validate_realtime_payload(payload)
                atomic_write_json(payload, config.dashboard_payload_path)
                atomic_write_json(new_state, config.state_path)
        finally:
            client.close()
        meta = payload["meta"]
        logger.info(
            "实时层完成：状态=%s，活动覆盖=%s/%s，请求=%s，失败=%s。",
            meta["status"],
            meta["covered_campaigns"],
            meta["eligible_campaigns"],
            meta["requested_calls"],
            meta["failed_calls"],
        )
        return 0
    except (RealtimeFailure, MonitorFailure) as exc:
        logger.error("实时层失败：%s", exc)
        return 2
    except KeyboardInterrupt:
        logger.warning("实时层已由用户中止；旧发布文件保持不变。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
