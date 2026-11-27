#!/usr/bin/env python3
"""Import Sellfox TikTok and approved custom-shop orders into a test table.

The production table dbo.TK_DingDan is intentionally hard-coded as read-only.
Credentials are read from environment variables or a Windows-DPAPI encrypted
configuration file. They are never stored in this source file.
"""

from __future__ import annotations

import argparse
import ctypes
import getpass
import hashlib
import hmac
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import secrets
import sys
import time
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import requests

try:
    import pyodbc
except ImportError:  # Allows --help and unit tests before dependencies are installed.
    pyodbc = None


APP_NAME = "SellfoxTK"
API_BASE_URL = "https://openapi.sellfox.com"
TOKEN_PATH = "/api/oauth/v2/token.json"
ORDER_PATH = "/api/multiplatform/order/list.json"
SOURCE_TABLE = "dbo.TK_DingDan"
TARGET_TABLE = "dbo.TK_dingdan_ceshi"
PLATFORM_TIKTOK = 6
PLATFORM_SHOPIFY = 3
REQUEST_PLATFORM_IDS = (PLATFORM_TIKTOK, PLATFORM_SHOPIFY)
CUSTOM_SHOP_IDS = frozenset({"483494", "553350"})
CUSTOM_SHOP_NAMES = frozenset({"okaylove", "geeneiya"})
MONEY_QUANTUM = Decimal("0.01")
UK_TO_USD_FACTOR = Decimal("7.5") / Decimal("6.5")
EMPTY_DATETIME = datetime(1900, 1, 1)

LOCAL_APPDATA = Path(
    os.environ.get(
        "LOCALAPPDATA",
        str(Path.home() / "AppData" / "Local"),
    )
)
APP_DIR = LOCAL_APPDATA / APP_NAME
CONFIG_PATH = APP_DIR / "config.dpapi"
LOG_DIR = APP_DIR / "logs"
LOG_PATH = LOG_DIR / "sellfox_import.log"

DB_COLUMNS = [
    "Dian",
    "Guo",
    "DanHao",
    "ZhuangTai",
    "FaHuoFangShi",
    "DingGouShiJian",
    "FuKuanShiJian",
    "FaHuoShiJian",
    "JieSuanZhuangTai",
    "ChanPinID",
    "MSKU",
    "SKU",
    "XiaoLiang",
    "ChanPinJinE",
    "CuXiaoZheKou",
    "MaiJiaShangPinZheKou",
    "PingTaiShangPinZheKou",
    "MaiJiaYunFeiZheKou",
    "PingTaiYunFeiZheKou",
    "MaiJiaYunFei",
    "ShuiFei",
    "ShangPinJiaGeShui",
    "YunFeiShui",
    "QiTaShouRu",
    "XiaoShouShouYi",
    "PingTaiPeiSongFei",
    "XiaoShouYongJin",
    "DingDanQiTaFeiYong",
    "YunFei",
    "CaiGouChengBen",
    "TouChengFeiYong",
    "PingTaiFaKuan",
    "TuiKuan",
    "DingDanLiRun",
    "DingDanLiRunLv",
    "BeiZhu",
    "WuLiuShang",
    "YunDanHao",
    "MaiJiaYouXiang",
    "ShouJianRen",
    "DianHua",
    "YouBian",
    "ZhouDiQu",
    "ChengShi",
    "XiangXiDiZhi",
    "ShiFouCuXiao",
    "ShiFouYangPin",
    "ShiFouLianMeng",
    "DaoRuShiJian",
    "DingGouRiQi",
]

STRING_LIMITS = {
    "Guo": 5,
    "DanHao": 25,
    "ZhuangTai": 5,
    "FaHuoFangShi": 6,
    "JieSuanZhuangTai": 5,
    "ChanPinID": 25,
    "MSKU": 50,
    "SKU": 25,
    "BeiZhu": 500,
    "WuLiuShang": 100,
    "YunDanHao": 100,
    "MaiJiaYouXiang": 100,
    "ShouJianRen": 200,
    "DianHua": 100,
    "YouBian": 100,
    "ZhouDiQu": 1000,
    "ChengShi": 100,
    "XiangXiDiZhi": 1000,
    "ShiFouCuXiao": 1,
    "ShiFouYangPin": 1,
    "ShiFouLianMeng": 1,
}

ORDER_MONEY_FIELDS = {
    "CuXiaoZheKou": "discountAmount",
    "MaiJiaShangPinZheKou": "sellerProductDiscount",
    "PingTaiShangPinZheKou": "platformProductDiscount",
    "MaiJiaYunFeiZheKou": "sellerShippingDiscount",
    "PingTaiYunFeiZheKou": "platformShippingDiscount",
    "MaiJiaYunFei": "shippingChargeAmount",
    "QiTaShouRu": "otherIncome",
    "XiaoShouShouYi": "totalAmount",
    "PingTaiPeiSongFei": "platformDeliveryFee",
    "XiaoShouYongJin": "salesCommission",
    "DingDanQiTaFeiYong": "orderOtherFee",
    "YunFei": "shippingCost",
    "CaiGouChengBen": "purchaseCost",
    "TouChengFeiYong": "headTripPrice",
    "PingTaiFaKuan": "platformPenalty",
    "TuiKuan": "refundTotalAmount",
    "DingDanLiRun": "orderProfit",
}

MONETARY_COLUMNS = {
    "ChanPinJinE",
    "CuXiaoZheKou",
    "MaiJiaShangPinZheKou",
    "PingTaiShangPinZheKou",
    "MaiJiaYunFeiZheKou",
    "PingTaiYunFeiZheKou",
    "MaiJiaYunFei",
    "ShuiFei",
    "ShangPinJiaGeShui",
    "YunFeiShui",
    "QiTaShouRu",
    "XiaoShouShouYi",
    "PingTaiPeiSongFei",
    "XiaoShouYongJin",
    "DingDanQiTaFeiYong",
    "YunFei",
    "CaiGouChengBen",
    "TouChengFeiYong",
    "PingTaiFaKuan",
    "TuiKuan",
    "DingDanLiRun",
}

ENV_CONFIG_KEYS = {
    "client_id": "SELLFOX_CLIENT_ID",
    "client_secret": "SELLFOX_CLIENT_SECRET",
    "db_server": "TK_SQL_SERVER",
    "db_database": "TK_SQL_DATABASE",
    "db_user": "TK_SQL_USER",
    "db_password": "TK_SQL_PASSWORD",
}


class ImportFailure(RuntimeError):
    """A sanitized failure safe to show in logs and automation output."""


class MappingFailure(ImportFailure):
    """Raised when an API order cannot be safely mapped."""


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str
    db_server: str
    db_database: str
    db_user: str
    db_password: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "Config":
        missing = [
            key
            for key in ENV_CONFIG_KEYS
            if not str(value.get(key, "")).strip()
        ]
        if missing:
            raise ImportFailure(
                "配置缺少字段：" + ", ".join(missing) + "。请先运行 --configure。"
            )
        return cls(**{key: str(value[key]).strip() for key in ENV_CONFIG_KEYS})


@dataclass
class RunStats:
    orders_fetched: int = 0
    tiktok_orders: int = 0
    custom_orders: int = 0
    out_of_scope_orders_dropped: int = 0
    rows_mapped: int = 0
    multi_item_orders: int = 0
    rows_written: int = 0
    target_rows_for_orders: int = 0
    api_pages: int = 0
    duplicate_orders_dropped: int = 0


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _windows_crypto_apis() -> tuple[Any, Any]:
    _require_windows()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    return crypt32, kernel32


def _require_windows() -> None:
    if os.name != "nt":
        raise ImportFailure("加密配置当前仅支持 Windows。")


def _blob_from_bytes(data: bytes) -> tuple[_DataBlob, Any]:
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    blob = _DataBlob(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return blob, buffer


def dpapi_protect(data: bytes) -> bytes:
    in_blob, in_buffer = _blob_from_bytes(data)
    out_blob = _DataBlob()
    crypt32, kernel32 = _windows_crypto_apis()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "Sellfox TikTok importer",
        None,
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(out_blob),
    )
    del in_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def dpapi_unprotect(data: bytes) -> bytes:
    in_blob, in_buffer = _blob_from_bytes(data)
    out_blob = _DataBlob()
    crypt32, kernel32 = _windows_crypto_apis()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0x1,
        ctypes.byref(out_blob),
    )
    del in_buffer
    if not ok:
        raise ImportFailure(
            "无法解密本机配置；请在创建配置的 Windows 用户下运行，"
            "或重新执行 --configure。"
        )
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def load_encrypted_config(required: bool = True) -> dict[str, str]:
    config: dict[str, str] = {}
    if CONFIG_PATH.exists():
        try:
            clear = dpapi_unprotect(CONFIG_PATH.read_bytes())
            config = json.loads(clear.decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ImportFailure("加密配置文件损坏或不可读。") from exc

    for key, env_name in ENV_CONFIG_KEYS.items():
        env_value = os.environ.get(env_name)
        if env_value:
            config[key] = env_value

    if required:
        Config.from_mapping(config)
    return config


def save_encrypted_config(config: Config) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "db_server": config.db_server,
            "db_database": config.db_database,
            "db_user": config.db_user,
            "db_password": config.db_password,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    protected = dpapi_protect(payload)
    temporary = CONFIG_PATH.with_suffix(".tmp")
    temporary.write_bytes(protected)
    os.replace(temporary, CONFIG_PATH)


def configure(from_env: bool) -> None:
    current = load_encrypted_config(required=False)

    def value(key: str, prompt: str, *, secret: bool = False) -> str:
        env_name = ENV_CONFIG_KEYS[key]
        env_value = os.environ.get(env_name)
        if env_value:
            return env_value.strip()
        if from_env:
            raise ImportFailure(f"环境变量 {env_name} 未设置。")
        old = str(current.get(key, "")).strip()
        suffix = "（直接回车保留现值）" if old else ""
        entered = (
            getpass.getpass(f"{prompt}{suffix}: ")
            if secret
            else input(f"{prompt}{suffix}: ")
        ).strip()
        return entered or old

    config = Config.from_mapping(
        {
            "client_id": value("client_id", "Sellfox client_id"),
            "client_secret": value(
                "client_secret",
                "Sellfox client_secret",
                secret=True,
            ),
            "db_server": value("db_server", "SQL Server 地址"),
            "db_database": value("db_database", "数据库名"),
            "db_user": value("db_user", "数据库用户名"),
            "db_password": value(
                "db_password",
                "数据库密码",
                secret=True,
            ),
        }
    )
    save_encrypted_config(config)
    print(f"配置已使用 Windows DPAPI 加密保存：{CONFIG_PATH}")


def setup_logging(verbose: bool = False) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)
    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=2_000_000,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


@contextmanager
def single_instance() -> Iterator[None]:
    """Use a Windows named mutex so manual and scheduled runs cannot overlap."""
    _require_windows()
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    mutex = kernel32.CreateMutexW(
        None,
        False,
        r"Local\SellfoxTK_dingdan_ceshi_import",
    )
    if not mutex:
        raise ctypes.WinError()
    ERROR_ALREADY_EXISTS = 183
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(mutex)
        raise ImportFailure("已有一个赛狐订单导入正在运行，本次已安全退出。")
    try:
        yield
    finally:
        kernel32.ReleaseMutex(mutex)
        kernel32.CloseHandle(mutex)


def as_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def decimal_field(
    source: dict[str, Any],
    field: str,
    order_no: str,
) -> Decimal:
    value = source.get(field)
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise MappingFailure(
            f"订单 {order_no} 的 {field} 不是有效金额。"
        ) from exc


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return default


def as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def clip(value: Any, limit: int) -> str:
    return as_text(value)[:limit]


def first_value(source: dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None and value != "":
            return value
    return ""


def classify_order_source(order: dict[str, Any]) -> str | None:
    """Map an OpenAPI order to the two sources selected in the Sellfox UI."""
    platform_type = as_text(
        first_value(order, ("platformType", "platformId"))
    )
    platform_name = as_text(order.get("platformName")).casefold()
    if platform_type == str(PLATFORM_TIKTOK) or platform_name == "tiktok":
        return "TikTok"

    # Sellfox exposes this account's UI "自定义" orders as Shopify (platform 3).
    # Keep a local shop whitelist so future real Shopify stores are not imported.
    if platform_type != str(PLATFORM_SHOPIFY):
        return None
    shop_id = as_text(order.get("shopId"))
    shop_name = as_text(order.get("shopName")).casefold()
    if shop_id in CUSTOM_SHOP_IDS or shop_name in CUSTOM_SHOP_NAMES:
        return "自定义"
    return None


def parse_datetime(
    value: Any,
    default: datetime = EMPTY_DATETIME,
    *,
    strict: bool = False,
    field: str = "datetime",
    order_no: str = "",
) -> datetime:
    text = as_text(value)
    if not text:
        if strict:
            raise MappingFailure(f"订单 {order_no} 缺少 {field}。")
        return default
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except ValueError:
        pass
    text = text.replace("T", " ")
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    if strict:
        raise MappingFailure(f"订单 {order_no} 的 {field} 日期格式无效。")
    return default


def yes_no(value: Any, default: bool = False) -> str:
    if value is None or value == "":
        return "是" if default else "否"
    normalized = as_text(value).lower()
    return "是" if normalized in {"1", "true", "yes", "是", "y"} else "否"


def normalize_store(shop_name: Any) -> int:
    original = as_text(shop_name)
    if not original:
        raise MappingFailure("API 返回了空店铺名称。")

    special = {
        "tk83-uk": 80,
        "okaylove": 202,
        "geeneiya": 201,
    }
    lowered = original.casefold()
    if lowered in special:
        return special[lowered]

    cleaned = re.sub(r"（.*$", "", original).strip()
    cleaned = re.sub("tk", "", cleaned, flags=re.IGNORECASE).strip()
    for suffix_store in (86, 90, 82):
        if cleaned.casefold() == f"{suffix_store}-uk":
            return suffix_store
    if re.fullmatch(r"\d+", cleaned):
        return int(cleaned)
    raise MappingFailure(f"无法把店铺名称“{original}”转换成数字店铺编号。")


def map_fulfillment(value: Any) -> str:
    text = as_text(value)
    return {
        "SellerFulfilled": "卖家发货",
        "WFSFulfilled": "平台发货",
        "3PLFulfilled": "第三方发货",
    }.get(text, text or "")


def map_settlement(value: Any) -> str:
    text = as_text(value)
    return {
        "0": "未结算",
        "1": "已结算",
        "2": "未知",
    }.get(text, text or "未知")


def parse_extra_info(order: dict[str, Any]) -> dict[str, Any]:
    value = order.get("extraInfo")
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def allocate_total(
    total: Decimal,
    weights: Sequence[Decimal],
    quantum: Decimal = MONEY_QUANTUM,
) -> list[Decimal]:
    """Allocate a total without losing a cent; the final row receives residual."""
    count = len(weights)
    if count == 0:
        return []
    if count == 1:
        return [total]
    positive = [max(weight, Decimal("0")) for weight in weights]
    weight_sum = sum(positive, Decimal("0"))
    if weight_sum == 0:
        positive = [Decimal("1")] * count
        weight_sum = Decimal(count)
    result: list[Decimal] = []
    assigned = Decimal("0")
    for index, weight in enumerate(positive):
        if index == count - 1:
            value = total - assigned
        else:
            value = (total * weight / weight_sum).quantize(
                quantum,
                rounding=ROUND_HALF_UP,
            )
            assigned += value
        result.append(value)
    return result


def _item_weights(
    items: Sequence[dict[str, Any]],
    order_no: str,
) -> list[Decimal]:
    gross = [
        max(decimal_field(item, "originalPrice", order_no), Decimal("0"))
        for item in items
    ]
    if sum(gross, Decimal("0")) > 0:
        return gross
    quantities = [
        max(as_decimal(item.get("saleNum"), Decimal("1")), Decimal("0"))
        for item in items
    ]
    if sum(quantities, Decimal("0")) > 0:
        return quantities
    return [Decimal("1")] * len(items)


def _tax_components(
    tax_total: Decimal,
    line_values: Sequence[dict[str, Decimal]],
) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    bases: list[Decimal] = []
    for values in line_values:
        net_product = max(
            values["ChanPinJinE"]
            + values["MaiJiaShangPinZheKou"]
            + values["PingTaiShangPinZheKou"],
            Decimal("0"),
        )
        net_shipping = max(
            values["MaiJiaYunFei"]
            + values["MaiJiaYunFeiZheKou"]
            + values["PingTaiYunFeiZheKou"],
            Decimal("0"),
        )
        bases.extend((net_product, net_shipping))
    components = allocate_total(tax_total, bases)
    product_tax = components[0::2]
    shipping_tax = components[1::2]
    line_tax = [
        product_tax[index] + shipping_tax[index]
        for index in range(len(line_values))
    ]
    return line_tax, product_tax, shipping_tax


def map_order(order: dict[str, Any], imported_at: datetime) -> list[dict[str, Any]]:
    order_no = as_text(order.get("orderNo"))
    if not order_no:
        raise MappingFailure("API 返回了没有 orderNo 的订单。")

    raw_items = order.get("skuInfoVo")
    items = raw_items if isinstance(raw_items, list) else []
    items = [item for item in items if isinstance(item, dict)]
    if not items:
        items = [{}]

    weights = _item_weights(items, order_no)
    line_count = len(items)
    allocated: dict[str, list[Decimal]] = {}
    for column, api_field in ORDER_MONEY_FIELDS.items():
        allocated[column] = allocate_total(
            decimal_field(order, api_field, order_no),
            weights,
        )

    product_total = decimal_field(order, "productAmount", order_no)
    product_values = [
        decimal_field(item, "originalPrice", order_no) for item in items
    ]
    if sum(product_values, Decimal("0")) == 0 and product_total != 0:
        product_values = allocate_total(product_total, weights)

    line_money: list[dict[str, Decimal]] = []
    for index in range(line_count):
        values = {
            column: allocated[column][index]
            for column in ORDER_MONEY_FIELDS
        }
        values["ChanPinJinE"] = product_values[index]
        line_money.append(values)

    tax_lines, product_taxes, shipping_taxes = _tax_components(
        decimal_field(order, "taxAmount", order_no),
        line_money,
    )

    extra = parse_extra_info(order)
    purchase_time = parse_datetime(
        order.get("purchaseDate"),
        strict=True,
        field="purchaseDate",
        order_no=order_no,
    )
    pay_time = parse_datetime(
        first_value(order, ("payTime",)) or extra.get("paidTime"),
        strict=bool(first_value(order, ("payTime",)) or extra.get("paidTime")),
        field="payTime",
        order_no=order_no,
    )
    country = as_text(
        first_value(order, ("marketplaceName", "marketplaceCode"))
    )
    shop = normalize_store(order.get("shopName"))
    multi_item_note = (
        "[API测试：多商品订单的订单级财务按商品金额比例分摊]"
        if line_count > 1
        else ""
    )

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        values = line_money[index]
        values["ShuiFei"] = tax_lines[index]
        values["ShangPinJiaGeShui"] = product_taxes[index]
        values["YunFeiShui"] = shipping_taxes[index]

        denominator = values["ChanPinJinE"] + values["CuXiaoZheKou"]
        if denominator != 0:
            profit_rate = values["DingDanLiRun"] / denominator
        else:
            profit_rate = (
                decimal_field(order, "orderProfitRate", order_no)
                / Decimal("100")
            )

        if country == "英国":
            values = {
                key: (
                    amount * UK_TO_USD_FACTOR
                    if key in MONETARY_COLUMNS
                    else amount
                )
                for key, amount in values.items()
            }

        notes = " ".join(
            part
            for part in (as_text(order.get("notes")), multi_item_note)
            if part
        )
        recipient_source = order.get("recipientInfo")
        recipient = recipient_source if isinstance(recipient_source, dict) else {}

        row: dict[str, Any] = {
            "Dian": shop,
            "Guo": country,
            "DanHao": order_no,
            "ZhuangTai": as_text(order.get("orderStatus")),
            "FaHuoFangShi": map_fulfillment(order.get("shipNodeType")),
            "DingGouShiJian": purchase_time,
            "FuKuanShiJian": pay_time,
            "FaHuoShiJian": parse_datetime(
                item.get("shipDateTime"),
                strict=bool(item.get("shipDateTime")),
                field="shipDateTime",
                order_no=order_no,
            ),
            "JieSuanZhuangTai": map_settlement(
                order.get("settlementStatus")
            ),
            "ChanPinID": as_text(
                first_value(item, ("productId", "orderItemId"))
            ),
            "MSKU": as_text(item.get("msku")),
            "SKU": as_text(first_value(item, ("localSku", "sku"))),
            "XiaoLiang": as_int(item.get("saleNum"), 1),
            **{column: float(values.get(column, Decimal("0"))) for column in MONETARY_COLUMNS},
            "DingDanLiRunLv": float(profit_rate),
            "BeiZhu": notes,
            "WuLiuShang": as_text(
                first_value(item, ("carrier", "logisticsProvider"))
            ),
            "YunDanHao": as_text(
                first_value(
                    item,
                    (
                        "trackingNo",
                        "trackingNumber",
                        "waybillNo",
                        "logisticsTrackingNumber",
                    ),
                )
                or first_value(
                    order,
                    ("trackingNo", "trackingNumber", "waybillNo"),
                )
            ),
            "MaiJiaYouXiang": as_text(order.get("buyerEmail")),
            "ShouJianRen": as_text(
                first_value(
                    recipient,
                    ("name", "recipientName", "fullName"),
                )
            ),
            "DianHua": as_text(
                first_value(recipient, ("phone", "phoneNumber"))
            ),
            "YouBian": as_text(
                first_value(recipient, ("postalCode", "zipCode"))
            ),
            "ZhouDiQu": as_text(
                first_value(recipient, ("state", "region", "province"))
            ),
            "ChengShi": as_text(first_value(recipient, ("city",))),
            "XiangXiDiZhi": as_text(
                first_value(
                    recipient,
                    ("address", "addressLine1", "detailedAddress"),
                )
            ),
            "ShiFouCuXiao": yes_no(order.get("isPromotion")),
            "ShiFouYangPin": yes_no(
                order.get("isSample"),
                default=bool(as_int(extra.get("isSampleOrder"))),
            ),
            "ShiFouLianMeng": yes_no(
                first_value(order, ("isAffiliate", "isAlliance"))
            ),
            "DaoRuShiJian": imported_at,
            "DingGouRiQi": purchase_time.date(),
        }
        for column, limit in STRING_LIMITS.items():
            row[column] = clip(row.get(column), limit)
        rows.append(row)
    return rows


class SellfoxClient:
    def __init__(self, config: Config, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "SellfoxTK-TestImporter/1.0",
            }
        )
        self._access_token = ""
        self._last_order_call = 0.0

    def close(self) -> None:
        self.session.close()

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        purpose: str,
    ) -> dict[str, Any]:
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                json=body,
                timeout=(15, 90),
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
        if (
            response.status_code >= 400
            and str(payload.get("code")) != "40019"
        ):
            code = payload.get("code", response.status_code)
            message = as_text(payload.get("msg")) or "HTTP 请求失败"
            raise ImportFailure(f"{purpose}失败：code={code}，{message}")
        return payload

    def get_token(self) -> str:
        if self._access_token:
            return self._access_token
        payload = self._request_json(
            "GET",
            API_BASE_URL + TOKEN_PATH,
            params={
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "grant_type": "client_credentials",
            },
            purpose="获取 Access Token",
        )
        if payload.get("code") not in (0, "0", None):
            raise ImportFailure(
                f"获取 Access Token 失败：code={payload.get('code')}，"
                f"{as_text(payload.get('msg'))}"
            )
        data = payload.get("data")
        token = data.get("access_token") if isinstance(data, dict) else ""
        if not token:
            raise ImportFailure("Access Token 响应中没有 access_token。")
        self._access_token = str(token)
        return self._access_token

    def _signed_params(self, path: str) -> dict[str, str]:
        token = self.get_token()
        timestamp = str(int(time.time() * 1000))
        nonce = str(secrets.randbelow(900_000) + 100_000)
        sign_values = {
            "access_token": token,
            "client_id": self.config.client_id,
            "method": "post",
            "nonce": nonce,
            "timestamp": timestamp,
            "url": path,
        }
        canonical = "&".join(
            f"{key}={sign_values[key]}" for key in sorted(sign_values)
        )
        signature = hmac.new(
            self.config.client_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "access_token": token,
            "client_id": self.config.client_id,
            "timestamp": timestamp,
            "nonce": nonce,
            "sign": signature,
        }

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_order_call
        if elapsed < 1.05:
            time.sleep(1.05 - elapsed)

    def post_orders(self, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(1, 9):
            self._throttle()
            try:
                payload = self._request_json(
                    "POST",
                    API_BASE_URL + ORDER_PATH,
                    params=self._signed_params(ORDER_PATH),
                    body=body,
                    purpose="读取多平台订单",
                )
            finally:
                self._last_order_call = time.monotonic()
            code = payload.get("code")
            if str(code) == "0":
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise ImportFailure("订单接口 data 格式异常。")
                return data
            if str(code) == "40019" and attempt < 8:
                delay = min(60, 5 * (2 ** (attempt - 1)))
                self.logger.warning(
                    "赛狐接口限流，%s 秒后进行第 %s 次重试",
                    delay,
                    attempt + 1,
                )
                time.sleep(delay)
                continue
            raise ImportFailure(
                f"读取多平台订单失败：code={code}，"
                f"{as_text(payload.get('msg'))}"
            )
        raise ImportFailure("订单接口多次触发限流。")

    def fetch_orders(
        self,
        *,
        start_date: date,
        end_date: date,
        date_type: str,
        page_size: int,
        max_orders: int | None,
        stats: RunStats,
    ) -> list[dict[str, Any]]:
        page_no = 1
        result_by_order: dict[str, dict[str, Any]] = {}
        missing_order_counter = 0
        while True:
            data = self.post_orders(
                {
                    "pageNo": str(page_no),
                    "pageSize": str(page_size),
                    "platformIdList": list(REQUEST_PLATFORM_IDS),
                    "dateType": date_type,
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "orderBy": date_type,
                    "desc": True,
                }
            )
            stats.api_pages += 1
            page_rows = data.get("rows")
            rows = page_rows if isinstance(page_rows, list) else []
            rows = [row for row in rows if isinstance(row, dict)]
            for row in rows:
                if classify_order_source(row) is None:
                    stats.out_of_scope_orders_dropped += 1
                    continue
                order_no = as_text(row.get("orderNo"))
                if not order_no:
                    missing_order_counter += 1
                    order_no = f"__missing_order_{missing_order_counter}"
                existing = result_by_order.get(order_no)
                if existing is not None:
                    stats.duplicate_orders_dropped += 1
                    if as_text(row.get("updateTime")) >= as_text(
                        existing.get("updateTime")
                    ):
                        result_by_order[order_no] = row
                    continue
                if max_orders is not None and len(result_by_order) >= max_orders:
                    continue
                result_by_order[order_no] = row

            total_page = as_int(data.get("totalPage"), 1)
            self.logger.info(
                "API 第 %s/%s 页，当前累计 %s 个订单",
                page_no,
                total_page,
                len(result_by_order),
            )
            if (
                not rows
                or page_no >= total_page
                or (
                    max_orders is not None
                    and len(result_by_order) >= max_orders
                )
            ):
                break
            page_no += 1
        result = list(result_by_order.values())
        stats.orders_fetched = len(result)
        stats.tiktok_orders = sum(
            classify_order_source(order) == "TikTok" for order in result
        )
        stats.custom_orders = sum(
            classify_order_source(order) == "自定义" for order in result
        )
        self.logger.info(
            "API 筛选完成：TikTok=%s，自定义=%s，范围外丢弃=%s",
            stats.tiktok_orders,
            stats.custom_orders,
            stats.out_of_scope_orders_dropped,
        )
        if stats.duplicate_orders_dropped:
            self.logger.warning(
                "分页期间发现 %s 个重复订单，已按 orderNo 保留最新 updateTime。",
                stats.duplicate_orders_dropped,
            )
        return result


def require_pyodbc() -> Any:
    if pyodbc is None:
        raise ImportFailure(
            "缺少 pyodbc。请先运行："
            r".\.venv\Scripts\python.exe -m pip install -r requirements.txt"
        )
    return pyodbc


def connect_database(config: Config) -> Any:
    module = require_pyodbc()
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={config.db_server};"
        f"DATABASE={config.db_database};"
        f"UID={config.db_user};"
        f"PWD={config.db_password};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
        "APP=SellfoxTK-TestImporter;"
    )
    try:
        return module.connect(
            connection_string,
            autocommit=False,
            timeout=20,
        )
    except module.Error as exc:
        raise ImportFailure("连接 SQL Server 失败。") from exc


def quote_identifier(value: str) -> str:
    return "[" + value.replace("]", "]]") + "]"


def quote_table(value: str) -> str:
    parts = value.split(".")
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_]+", p) for p in parts):
        raise ImportFailure(f"不安全的表名：{value}")
    return ".".join(quote_identifier(part) for part in parts)


def table_object_id(cursor: Any, table: str) -> int | None:
    cursor.execute("SELECT OBJECT_ID(?, N'U')", table)
    row = cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else None


def table_columns(cursor: Any, table: str) -> list[tuple[Any, ...]]:
    cursor.execute(
        """
        SELECT
            c.column_id,
            c.name,
            TYPE_NAME(c.user_type_id) AS type_name,
            c.max_length,
            c.precision,
            c.scale,
            c.is_nullable,
            c.is_identity
        FROM sys.columns AS c
        WHERE c.object_id = OBJECT_ID(?, N'U')
        ORDER BY c.column_id
        """,
        table,
    )
    return [tuple(row) for row in cursor.fetchall()]


def _default_signatures(
    cursor: Any,
    table: str,
) -> list[tuple[str, str]]:
    cursor.execute(
        """
        SELECT c.name, dc.definition
        FROM sys.default_constraints AS dc
        JOIN sys.columns AS c
          ON c.object_id = dc.parent_object_id
         AND c.column_id = dc.parent_column_id
        WHERE dc.parent_object_id = OBJECT_ID(?, N'U')
        ORDER BY c.column_id
        """,
        table,
    )
    return [(str(row[0]), str(row[1])) for row in cursor.fetchall()]


def _clone_defaults(cursor: Any) -> int:
    defaults = _default_signatures(cursor, SOURCE_TABLE)
    created = 0
    for column, definition in defaults:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM sys.default_constraints AS dc
            JOIN sys.columns AS c
              ON c.object_id = dc.parent_object_id
             AND c.column_id = dc.parent_column_id
            WHERE dc.parent_object_id = OBJECT_ID(?, N'U')
              AND c.name = ?
            """,
            TARGET_TABLE,
            column,
        )
        if int(cursor.fetchone()[0]) > 0:
            continue
        constraint = f"DF_TK_dingdan_ceshi_{column}"[:128]
        cursor.execute(
            f"ALTER TABLE {quote_table(TARGET_TABLE)} "
            f"ADD CONSTRAINT {quote_identifier(constraint)} "
            f"DEFAULT {definition} FOR {quote_identifier(column)}"
        )
        created += 1
    return created


def _indexes(cursor: Any, table: str) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            i.index_id,
            i.name,
            i.is_unique,
            i.type_desc,
            i.has_filter,
            i.filter_definition,
            i.fill_factor,
            i.is_padded,
            i.ignore_dup_key,
            i.allow_row_locks,
            i.allow_page_locks,
            ic.key_ordinal,
            ic.index_column_id,
            ic.is_included_column,
            ic.is_descending_key,
            c.name AS column_name
        FROM sys.indexes AS i
        JOIN sys.index_columns AS ic
          ON ic.object_id = i.object_id
         AND ic.index_id = i.index_id
        JOIN sys.columns AS c
          ON c.object_id = ic.object_id
         AND c.column_id = ic.column_id
        WHERE i.object_id = OBJECT_ID(?, N'U')
          AND i.index_id > 0
          AND i.is_hypothetical = 0
          AND i.is_primary_key = 0
          AND i.is_unique_constraint = 0
        ORDER BY i.index_id, ic.is_included_column, ic.key_ordinal,
                 ic.index_column_id
        """,
        table,
    )
    groups: dict[int, dict[str, Any]] = {}
    for row in cursor.fetchall():
        index_id = int(row[0])
        group = groups.setdefault(
            index_id,
            {
                "name": str(row[1]),
                "unique": bool(row[2]),
                "type_desc": str(row[3]),
                "has_filter": bool(row[4]),
                "filter": row[5],
                "fill_factor": int(row[6]),
                "is_padded": bool(row[7]),
                "ignore_dup_key": bool(row[8]),
                "allow_row_locks": bool(row[9]),
                "allow_page_locks": bool(row[10]),
                "keys": [],
                "includes": [],
            },
        )
        column = str(row[15])
        if bool(row[13]):
            group["includes"].append(column)
        else:
            direction = "DESC" if bool(row[14]) else "ASC"
            group["keys"].append((int(row[11]), column, direction))
    result = list(groups.values())
    for index in result:
        index["keys"].sort(key=lambda item: item[0])
    return result


def _index_signatures(cursor: Any, table: str) -> list[tuple[Any, ...]]:
    signatures: list[tuple[Any, ...]] = []
    for index in _indexes(cursor, table):
        signatures.append(
            (
                index["unique"],
                index["type_desc"].upper(),
                index["has_filter"],
                as_text(index["filter"]),
                index["fill_factor"],
                index["is_padded"],
                index["ignore_dup_key"],
                index["allow_row_locks"],
                index["allow_page_locks"],
                tuple(index["keys"]),
                tuple(index["includes"]),
            )
        )
    return sorted(signatures, key=repr)


def _clone_indexes(cursor: Any) -> int:
    created = 0
    for source in _indexes(cursor, SOURCE_TABLE):
        name = (source["name"] + "_ceshi")[:128]
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM sys.indexes
            WHERE object_id = OBJECT_ID(?, N'U')
              AND name = ?
            """,
            TARGET_TABLE,
            name,
        )
        if int(cursor.fetchone()[0]) > 0:
            continue
        keys = ", ".join(
            f"{quote_identifier(column)} {direction}"
            for _, column, direction in source["keys"]
        )
        includes = ""
        if source["includes"]:
            includes = " INCLUDE (" + ", ".join(
                quote_identifier(column) for column in source["includes"]
            ) + ")"
        filtered = (
            f" WHERE {source['filter']}"
            if source["has_filter"] and source["filter"]
            else ""
        )
        options = [
            f"PAD_INDEX = {'ON' if source['is_padded'] else 'OFF'}",
            f"IGNORE_DUP_KEY = {'ON' if source['ignore_dup_key'] else 'OFF'}",
            f"ALLOW_ROW_LOCKS = {'ON' if source['allow_row_locks'] else 'OFF'}",
            f"ALLOW_PAGE_LOCKS = {'ON' if source['allow_page_locks'] else 'OFF'}",
        ]
        if source["fill_factor"]:
            options.append(f"FILLFACTOR = {source['fill_factor']}")
        unique = "UNIQUE " if source["unique"] else ""
        index_type = (
            "CLUSTERED"
            if source["type_desc"].upper() == "CLUSTERED"
            else "NONCLUSTERED"
        )
        cursor.execute(
            f"CREATE {unique}{index_type} INDEX {quote_identifier(name)} "
            f"ON {quote_table(TARGET_TABLE)} ({keys})"
            f"{includes}{filtered} WITH ({', '.join(options)})"
        )
        created += 1
    return created


def ensure_test_table(connection: Any, logger: logging.Logger) -> None:
    cursor = connection.cursor()
    if table_object_id(cursor, SOURCE_TABLE) is None:
        raise ImportFailure(f"源表 {SOURCE_TABLE} 不存在。")
    created_table = False
    if table_object_id(cursor, TARGET_TABLE) is None:
        cursor.execute(
            f"SELECT TOP (0) * INTO {quote_table(TARGET_TABLE)} "
            f"FROM {quote_table(SOURCE_TABLE)}"
        )
        created_table = True

    defaults_created = _clone_defaults(cursor)
    indexes_created = _clone_indexes(cursor)

    source_columns = table_columns(cursor, SOURCE_TABLE)
    target_columns = table_columns(cursor, TARGET_TABLE)
    if source_columns != target_columns:
        connection.rollback()
        raise ImportFailure(
            f"{TARGET_TABLE} 与 {SOURCE_TABLE} 的列结构不一致，已停止写入。"
        )
    expected_non_identity = [row[1] for row in source_columns if not row[7]]
    if expected_non_identity != DB_COLUMNS:
        connection.rollback()
        raise ImportFailure(
            "正式表物理列顺序已变化，与脚本映射不一致，已停止写入。"
        )
    if _default_signatures(cursor, SOURCE_TABLE) != _default_signatures(
        cursor,
        TARGET_TABLE,
    ):
        connection.rollback()
        raise ImportFailure(
            f"{TARGET_TABLE} 与 {SOURCE_TABLE} 的默认值定义不一致，"
            "已停止写入。"
        )
    if _index_signatures(cursor, SOURCE_TABLE) != _index_signatures(
        cursor,
        TARGET_TABLE,
    ):
        connection.rollback()
        raise ImportFailure(
            f"{TARGET_TABLE} 与 {SOURCE_TABLE} 的索引定义不一致，"
            "已停止写入。"
        )
    connection.commit()
    logger.info(
        "测试表检查完成：created=%s，新增默认值=%s，新增索引=%s",
        created_table,
        defaults_created,
        indexes_created,
    )


def _row_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(column, "") for column in DB_COLUMNS)


def _chunks(values: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def write_rows(
    connection: Any,
    orders: Sequence[dict[str, Any]],
    rows: Sequence[dict[str, Any]],
    logger: logging.Logger,
) -> tuple[int, int]:
    order_numbers = sorted(
        {as_text(order.get("orderNo")) for order in orders if order.get("orderNo")}
    )
    if not order_numbers:
        return 0, 0
    cursor = connection.cursor()
    try:
        for batch in _chunks(order_numbers, 500):
            placeholders = ",".join("?" for _ in batch)
            cursor.execute(
                f"DELETE FROM {quote_table(TARGET_TABLE)} "
                f"WHERE {quote_identifier('DanHao')} IN ({placeholders})",
                *batch,
            )

        if rows:
            columns_sql = ", ".join(quote_identifier(c) for c in DB_COLUMNS)
            placeholders = ", ".join("?" for _ in DB_COLUMNS)
            insert_sql = (
                f"INSERT INTO {quote_table(TARGET_TABLE)} ({columns_sql}) "
                f"VALUES ({placeholders})"
            )
            try:
                cursor.fast_executemany = True
            except AttributeError:
                pass
            cursor.executemany(insert_sql, [_row_tuple(row) for row in rows])
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    verified = 0
    for batch in _chunks(order_numbers, 500):
        placeholders = ",".join("?" for _ in batch)
        cursor.execute(
            f"SELECT COUNT_BIG(*) FROM {quote_table(TARGET_TABLE)} "
            f"WHERE {quote_identifier('DanHao')} IN ({placeholders})",
            *batch,
        )
        verified += int(cursor.fetchone()[0])
    logger.info(
        "事务写入完成：%s 个订单，%s 行；数据库复核 %s 行",
        len(order_numbers),
        len(rows),
        verified,
    )
    return len(rows), verified


def resolve_dates(args: argparse.Namespace) -> tuple[date, date]:
    if bool(args.start_date) != bool(args.end_date):
        raise ImportFailure("--start-date 与 --end-date 必须同时提供。")
    if args.start_date:
        try:
            start = date.fromisoformat(args.start_date)
            end = date.fromisoformat(args.end_date)
        except ValueError as exc:
            raise ImportFailure("日期格式必须为 YYYY-MM-DD。") from exc
    else:
        end = date.today()
        start = end - timedelta(days=args.lookback_days - 1)
    if start > end:
        raise ImportFailure("开始日期不能晚于结束日期。")
    if (end - start).days > 89:
        raise ImportFailure("单次 API 日期范围不能超过 90 天。")
    return start, end


def run_import(
    args: argparse.Namespace,
    config: Config,
    logger: logging.Logger,
) -> RunStats:
    start, end = resolve_dates(args)
    stats = RunStats()
    logger.info(
        "开始导入 TikTok + 自定义订单：%s 至 %s，dateType=%s，目标=%s",
        start,
        end,
        args.date_type,
        TARGET_TABLE,
    )

    connection = connect_database(config)
    try:
        ensure_test_table(connection, logger)
        if args.ensure_table_only:
            return stats

        client = SellfoxClient(config, logger)
        try:
            orders = client.fetch_orders(
                start_date=start,
                end_date=end,
                date_type=args.date_type,
                page_size=args.page_size,
                max_orders=args.max_orders,
                stats=stats,
            )
        finally:
            client.close()

        imported_at = datetime.now().replace(microsecond=0)
        mapped_rows: list[dict[str, Any]] = []
        for order in orders:
            order_rows = map_order(order, imported_at)
            if len(order_rows) > 1:
                stats.multi_item_orders += 1
            mapped_rows.extend(order_rows)
        stats.rows_mapped = len(mapped_rows)

        if stats.multi_item_orders:
            logger.warning(
                "%s 个多商品订单使用订单级财务按商品金额比例分摊；"
                "测试表备注列已标识这些行。",
                stats.multi_item_orders,
            )
        if args.dry_run:
            logger.info("dry-run：已取数和映射，未写数据库。")
            return stats

        written, verified = write_rows(
            connection,
            orders,
            mapped_rows,
            logger,
        )
        stats.rows_written = written
        stats.target_rows_for_orders = verified
        if verified != written:
            raise ImportFailure(
                f"写入后复核行数不一致：预计 {written}，实际 {verified}。"
            )
        return stats
    finally:
        connection.close()


def show_config() -> None:
    config = Config.from_mapping(load_encrypted_config())
    masked_id = (
        config.client_id[:2] + "***" + config.client_id[-2:]
        if len(config.client_id) > 4
        else "***"
    )
    print(
        json.dumps(
            {
                "config_path": str(CONFIG_PATH),
                "client_id": masked_id,
                "db_server": config.db_server,
                "db_database": config.db_database,
                "db_user": config.db_user,
                "target_table": TARGET_TABLE,
                "secrets": "hidden",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "从赛狐多平台订单 API 导入 TikTok + 指定自定义店铺订单到 "
            "dbo.TK_dingdan_ceshi（不会写正式表）。"
        )
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--configure",
        action="store_true",
        help="交互式创建 Windows DPAPI 加密配置",
    )
    action.add_argument(
        "--show-config",
        action="store_true",
        help="显示不含密码的配置摘要",
    )
    action.add_argument(
        "--ensure-table-only",
        action="store_true",
        help="只创建/检查测试表，不调用 API",
    )
    action.add_argument(
        "--once",
        action="store_true",
        help="执行一次导入（无参数时也是此模式）",
    )
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="配合 --configure，从环境变量创建加密配置",
    )
    parser.add_argument("--start-date", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--date-type",
        choices=("updateTime", "purchase", "payTime"),
        default="purchase",
        help="API 时间筛选类型，默认 purchase（订购时间）",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="未指定日期时回看自然日数，默认 7",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        help="API 每页订单数，1-1000，默认 1000",
    )
    parser.add_argument(
        "--max-orders",
        type=int,
        help="最多读取多少个订单；用于小批量测试",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="调用 API 并完成映射，但不写数据库",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出更详细的本地日志（不会记录密码或 Token）",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.lookback_days < 1 or args.lookback_days > 90:
        raise ImportFailure("--lookback-days 必须在 1 到 90 之间。")
    if args.page_size < 1 or args.page_size > 1000:
        raise ImportFailure("--page-size 必须在 1 到 1000 之间。")
    if args.max_orders is not None and args.max_orders < 1:
        raise ImportFailure("--max-orders 必须大于 0。")
    if args.from_env and not args.configure:
        raise ImportFailure("--from-env 只能与 --configure 一起使用。")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logger = setup_logging(args.verbose)
    try:
        validate_args(args)
        if args.configure:
            configure(args.from_env)
            return 0
        if args.show_config:
            show_config()
            return 0

        config = Config.from_mapping(load_encrypted_config())
        with single_instance():
            stats = run_import(args, config, logger)
        summary = {
            "status": "ok",
            "target": TARGET_TABLE,
            "orders": stats.orders_fetched,
            "tiktok_orders": stats.tiktok_orders,
            "custom_orders": stats.custom_orders,
            "out_of_scope_orders_dropped": stats.out_of_scope_orders_dropped,
            "rows_mapped": stats.rows_mapped,
            "rows_written": stats.rows_written,
            "multi_item_orders": stats.multi_item_orders,
            "api_pages": stats.api_pages,
            "duplicate_orders_dropped": stats.duplicate_orders_dropped,
        }
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except ImportFailure as exc:
        logger.error("%s", exc)
        print(
            json.dumps(
                {"status": "error", "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2
    except KeyboardInterrupt:
        logger.warning("用户取消了导入。")
        return 130
    except Exception as exc:
        # Do not emit a traceback: request URLs contain signed credentials.
        logger.error("未预期错误：%s: %s", type(exc).__name__, exc)
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"未预期错误：{type(exc).__name__}",
                },
                ensure_ascii=False,
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
