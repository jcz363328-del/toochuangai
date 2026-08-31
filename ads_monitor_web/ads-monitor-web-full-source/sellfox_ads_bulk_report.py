#!/usr/bin/env python3
"""Download and parse Sellfox SP daily advertising reports."""

from __future__ import annotations

import io
import os
import posixpath
import re
import tempfile
import time
import unicodedata
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator, Mapping, Protocol, Sequence
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET


CREATE_TASK_PATH = "/api/cpc/download/createTask.json"
PAGE_LIST_PATH = "/api/cpc/download/pageList.json"
CAMPAIGN_REPORT = "adCampaignReport"
TARGETING_REPORT = "adTargeringReport"

MAX_ZIP_ENTRIES = 10_000
MAX_ZIP_MEMBER_BYTES = 512 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 768 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024


class BulkReportError(RuntimeError):
    """Raised when a report cannot be obtained or trusted."""


class AdsClient(Protocol):
    session: Any

    def post_data(
        self,
        path: str,
        body: dict[str, Any],
        purpose: str,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ReportTask:
    task_id: str
    shop_ids: tuple[str, ...]
    report_type_code: str


@dataclass(frozen=True)
class ReadyReport:
    task_id: str
    shop_ids: tuple[str, ...]
    report_type_code: str
    download_urls: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True)
class DownloadedReport:
    task_id: str
    shop_ids: tuple[str, ...]
    report_type_code: str
    path: Path


@dataclass
class ParsedReportBundle:
    files: tuple[Path, ...]
    campaign_rows: list[dict[str, Any]]
    targeting_rows: list[dict[str, Any]]
    campaign_rows_by_shop: dict[str, list[dict[str, Any]]]
    targeting_rows_by_shop: dict[str, list[dict[str, Any]]]


CAMPAIGN_HEADERS = {
    "店铺": "shop_name",
    "日期": "report_date",
    "广告活动": "campaign_name",
    "定位类型": "targeting_type",
    "广告花费": "spend",
    "广告曝光量": "impressions",
    "广告点击量": "clicks",
    "CPC": "cpc",
    "广告点击率": "ctr",
    "广告转化率": "cvr",
    "ACoS": "acos",
    "ROAS": "roas",
    "广告订单量": "orders",
    "本广告产品订单量": "advertised_product_orders",
    "其他产品广告订单量": "other_product_orders",
    "广告销售额": "sales",
    "本广告产品销售额": "advertised_product_sales",
    "其他产品广告销售额": "other_product_sales",
    "广告销量": "units",
    "本广告产品销量": "advertised_product_units",
    "其他产品广告销量": "other_product_units",
    "广告活动开始时间": "campaign_start_date",
    "广告活动结束时间": "campaign_end_date",
    "广告活动运行状态": "campaign_status",
    "广告组合ID": "portfolio_id",
    "广告活动ID": "campaign_id",
}

TARGETING_HEADERS = {
    "店铺": "shop_name",
    "日期": "report_date",
    "投放": "target_text",
    "匹配类型": "match_type",
    "广告组": "ad_group_name",
    "广告活动": "campaign_name",
    "定位类型": "targeting_type",
    "广告花费": "spend",
    "广告曝光量": "impressions",
    "广告点击量": "clicks",
    "CPC": "cpc",
    "广告点击率": "ctr",
    "广告转化率": "cvr",
    "ACoS": "acos",
    "ROAS": "roas",
    "广告订单量": "orders",
    "本广告产品订单量": "advertised_product_orders",
    "其他产品广告订单量": "other_product_orders",
    "广告销售额": "sales",
    "本广告产品销售额": "advertised_product_sales",
    "其他产品广告销售额": "other_product_sales",
    "广告销量": "units",
    "本广告产品销量": "advertised_product_units",
    "其他产品广告销量": "other_product_units",
    "广告活动开始时间": "campaign_start_date",
    "广告活动结束时间": "campaign_end_date",
    "投放运行状态": "target_status",
    "广告活动ID": "campaign_id",
    "广告组ID": "ad_group_id",
    "广告投放ID": "target_id",
}

DATE_FIELDS = frozenset(
    {"report_date", "campaign_start_date", "campaign_end_date"}
)
ID_FIELDS = frozenset(
    {"portfolio_id", "campaign_id", "ad_group_id", "target_id"}
)
DECIMAL_FIELDS = frozenset(
    {
        "spend",
        "impressions",
        "clicks",
        "cpc",
        "ctr",
        "cvr",
        "acos",
        "roas",
        "orders",
        "advertised_product_orders",
        "other_product_orders",
        "sales",
        "advertised_product_sales",
        "other_product_sales",
        "units",
        "advertised_product_units",
        "other_product_units",
    }
)

_REPORT_ALIASES = {
    "activity": CAMPAIGN_REPORT,
    "campaign": CAMPAIGN_REPORT,
    "campaignreport": CAMPAIGN_REPORT,
    "adcampaignreport": CAMPAIGN_REPORT,
    "活动": CAMPAIGN_REPORT,
    "活动日报": CAMPAIGN_REPORT,
    "target": TARGETING_REPORT,
    "targeting": TARGETING_REPORT,
    "adtargeringreport": TARGETING_REPORT,
    "投放": TARGETING_REPORT,
    "投放日报": TARGETING_REPORT,
}
_CELL_REF_RE = re.compile(r"^([A-Za-z]+)")
_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")


def normalize_report_type(value: str) -> str:
    key = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    code = _REPORT_ALIASES.get(key)
    if not code:
        raise BulkReportError("不支持的广告报表类型。")
    return code


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalized_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _text(value))
    return " ".join(text.split()).casefold()


def _validated_date(value: Any, label: str) -> str:
    text = _text(value)
    if not text:
        raise BulkReportError(f"{label}不能为空。")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise BulkReportError(f"{label}必须是 YYYY-MM-DD。") from exc
    return parsed.isoformat()


def create_report_tasks(
    client: AdsClient,
    shop_ids: Sequence[str],
    report_type: str,
    report_start_date: str,
    report_end_date: str,
    *,
    batch_size: int = 50,
) -> list[ReportTask]:
    """Create one asynchronous task per shop batch."""

    code = normalize_report_type(report_type)
    start = _validated_date(report_start_date, "报表开始日期")
    end = _validated_date(report_end_date, "报表结束日期")
    if start > end:
        raise BulkReportError("报表开始日期不能晚于结束日期。")
    if not 1 <= batch_size <= 100:
        raise BulkReportError("batch_size 必须在 1 到 100 之间。")
    clean_ids = tuple(dict.fromkeys(_text(item) for item in shop_ids if _text(item)))
    if not clean_ids:
        raise BulkReportError("至少需要一个店铺 ID。")

    tasks: list[ReportTask] = []
    for offset in range(0, len(clean_ids), batch_size):
        batch = clean_ids[offset : offset + batch_size]
        body = {
            "shopIds": list(batch),
            "adTypeCode": "sp",
            "reportTypeCode": code,
            "timeUnit": "daily",
            "reportStartDate": start,
            "reportEndDate": end,
        }
        data = client.post_data(CREATE_TASK_PATH, body, "创建广告报表下载任务")
        task_id = _text(data.get("id")) if isinstance(data, dict) else ""
        if not task_id:
            raise BulkReportError("创建广告报表任务返回格式异常。")
        tasks.append(ReportTask(task_id, batch, code))
    return tasks


def _page_rows(data: Any) -> list[dict[str, Any]]:
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise BulkReportError("广告报表任务列表返回格式异常。")
    return rows


def _task_rows(
    client: AdsClient,
    task_ids: Sequence[str],
    *,
    page_size: int = 100,
) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    wanted = set(task_ids)
    for offset in range(0, len(task_ids), page_size):
        batch = list(task_ids[offset : offset + page_size])
        page_no = 1
        while True:
            body = {
                "pageNo": str(page_no),
                "pageSize": str(page_size),
                "taskIds": batch,
            }
            data = client.post_data(PAGE_LIST_PATH, body, "查询广告报表下载任务")
            rows = _page_rows(data)
            for row in rows:
                task_id = _text(row.get("id"))
                if task_id not in wanted:
                    continue
                if task_id in found:
                    raise BulkReportError("广告报表任务列表包含重复任务。")
                found[task_id] = row
            if len(rows) < page_size:
                break
            page_no += 1
            if page_no > 1_000:
                raise BulkReportError("广告报表任务列表分页异常。")
    return found


def _ready_report(task: ReportTask, row: Mapping[str, Any]) -> ReadyReport | None:
    state = _text(row.get("reportState"))
    if state == "生成中":
        return None
    if state == "失败":
        raise BulkReportError(f"广告报表任务 {task.task_id} 生成失败。")
    if state != "已生成":
        raise BulkReportError("广告报表任务状态格式异常。")

    row_code = _text(row.get("reportTypeCode"))
    row_shops = row.get("shopId")
    if row_code != task.report_type_code:
        raise BulkReportError("广告报表任务类型与创建请求不一致。")
    if not isinstance(row_shops, list):
        raise BulkReportError("广告报表任务店铺字段格式异常。")
    clean_shops = tuple(_text(item) for item in row_shops)
    if any(not item for item in clean_shops) or set(clean_shops) != set(task.shop_ids):
        raise BulkReportError("广告报表任务店铺范围与创建请求不一致。")

    urls = row.get("downloadUrl")
    if not isinstance(urls, list) or not urls:
        raise BulkReportError("已生成的广告报表没有下载地址。")
    clean_urls = tuple(_validated_download_url(item) for item in urls)
    return ReadyReport(task.task_id, task.shop_ids, task.report_type_code, clean_urls)


def wait_for_report_tasks(
    client: AdsClient,
    tasks: Sequence[ReportTask],
    *,
    timeout_seconds: float = 900,
    poll_interval_seconds: float = 5,
    _clock: Callable[[], float] = time.monotonic,
    _sleep: Callable[[float], None] = time.sleep,
) -> list[ReadyReport]:
    """Poll until every task is generated or a task fails."""

    if timeout_seconds <= 0 or poll_interval_seconds < 0:
        raise BulkReportError("轮询时间参数无效。")
    task_map = {task.task_id: task for task in tasks}
    if len(task_map) != len(tasks) or any(not key for key in task_map):
        raise BulkReportError("广告报表任务 ID 无效或重复。")
    if not task_map:
        return []

    ready: dict[str, ReadyReport] = {}
    deadline = _clock() + timeout_seconds
    while len(ready) < len(task_map):
        pending = [task_id for task_id in task_map if task_id not in ready]
        for task_id, row in _task_rows(client, pending).items():
            report = _ready_report(task_map[task_id], row)
            if report:
                ready[task_id] = report
        if len(ready) == len(task_map):
            break
        if _clock() >= deadline:
            raise BulkReportError("等待广告报表生成超时。")
        _sleep(poll_interval_seconds)
    return [ready[task.task_id] for task in tasks]


def _validated_download_url(value: Any) -> str:
    url = _text(value)
    parts = urlsplit(url)
    if not url or parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise BulkReportError("广告报表下载地址格式异常。")
    if parts.username or parts.password:
        raise BulkReportError("广告报表下载地址格式异常。")
    return url


def _download_file(client: AdsClient, url: str, path: Path, max_bytes: int) -> None:
    try:
        response = client.session.get(
            url,
            stream=True,
            timeout=(15, 120),
            allow_redirects=True,
        )
    except Exception:
        raise BulkReportError("下载广告报表时发生网络错误。") from None
    try:
        status = int(getattr(response, "status_code", 0))
        if status < 200 or status >= 300:
            raise BulkReportError(f"下载广告报表失败（HTTP {status}）。")
        length = _text(getattr(response, "headers", {}).get("Content-Length"))
        if length:
            try:
                declared = int(length)
            except ValueError as exc:
                raise BulkReportError("广告报表下载响应长度格式异常。") from exc
            if declared < 0 or declared > max_bytes:
                raise BulkReportError("广告报表下载文件超过安全大小限制。")
        written = 0
        with path.open("xb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not isinstance(chunk, (bytes, bytearray)):
                    raise BulkReportError("广告报表下载响应格式异常。")
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    raise BulkReportError("广告报表下载文件超过安全大小限制。")
                output.write(chunk)
        if written == 0:
            raise BulkReportError("广告报表下载文件为空。")
    except BulkReportError:
        raise
    except Exception:
        raise BulkReportError("下载广告报表时发生网络错误。") from None
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


@contextmanager
def downloaded_report_files(
    client: AdsClient,
    reports: Sequence[ReadyReport],
    *,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> Iterator[list[DownloadedReport]]:
    """Download reports into a private temporary directory."""

    if max_bytes <= 0:
        raise BulkReportError("下载文件大小限制无效。")
    with tempfile.TemporaryDirectory(prefix="sellfox_ads_") as temporary:
        root = Path(temporary).resolve()
        try:
            os.chmod(root, 0o700)
        except OSError:
            pass
        downloaded: list[DownloadedReport] = []
        index = 0
        for report in reports:
            for url in report.download_urls:
                index += 1
                path = (root / f"report_{index:04d}.xlsx").resolve()
                if root not in path.parents:
                    raise BulkReportError("临时报表路径不安全。")
                _download_file(client, _validated_download_url(url), path, max_bytes)
                downloaded.append(
                    DownloadedReport(
                        report.task_id,
                        report.shop_ids,
                        report.report_type_code,
                        path,
                    )
                )
        yield downloaded


def download_report_files_to_directory(
    client: AdsClient,
    reports: Sequence[ReadyReport],
    destination: str | os.PathLike[str],
    *,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> list[DownloadedReport]:
    """Persist generated XLSX files without using remote file names."""

    if max_bytes <= 0:
        raise BulkReportError("下载文件大小限制无效。")
    root = Path(destination).resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BulkReportError("无法创建广告报表保存目录。") from exc
    if not root.is_dir():
        raise BulkReportError("广告报表保存路径不是目录。")

    downloaded: list[DownloadedReport] = []
    index = 0
    for report in reports:
        safe_task = re.sub(r"[^A-Za-z0-9_-]", "_", report.task_id)[:64] or "task"
        for url in report.download_urls:
            index += 1
            name = f"{report.report_type_code}-{safe_task}-{index:04d}.xlsx"
            path = (root / name).resolve()
            if root not in path.parents:
                raise BulkReportError("广告报表保存路径不安全。")
            try:
                _download_file(client, _validated_download_url(url), path, max_bytes)
            except Exception:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise
            downloaded.append(
                DownloadedReport(
                    report.task_id,
                    report.shop_ids,
                    report.report_type_code,
                    path,
                )
            )
    return downloaded


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _zip_info(archive: zipfile.ZipFile, name: str) -> zipfile.ZipInfo:
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise BulkReportError("XLSX 缺少必要的工作簿文件。") from exc
    if info.file_size > MAX_ZIP_MEMBER_BYTES:
        raise BulkReportError("XLSX 内部文件超过安全大小限制。")
    return info


def _xml_root(archive: zipfile.ZipFile, name: str) -> ET.Element:
    info = _zip_info(archive, name)
    try:
        with archive.open(info) as source:
            return ET.parse(source).getroot()
    except (ET.ParseError, OSError, RuntimeError) as exc:
        raise BulkReportError("XLSX XML 格式异常。") from exc


def _first_sheet_path(archive: zipfile.ZipFile) -> str:
    workbook = _xml_root(archive, "xl/workbook.xml")
    relationship_id = ""
    for element in workbook.iter():
        if _local_name(element.tag) == "sheet":
            relationship_id = next(
                (
                    value
                    for key, value in element.attrib.items()
                    if _local_name(key) == "id"
                ),
                "",
            )
            break
    if not relationship_id:
        raise BulkReportError("XLSX 没有可读取的首个工作表。")

    relationships = _xml_root(archive, "xl/_rels/workbook.xml.rels")
    target = ""
    for element in relationships.iter():
        if _local_name(element.tag) != "Relationship":
            continue
        if element.attrib.get("Id") == relationship_id:
            target = _text(element.attrib.get("Target"))
            break
    if not target:
        raise BulkReportError("XLSX 首个工作表关系缺失。")
    path = target.lstrip("/")
    if not path.startswith("xl/"):
        path = posixpath.normpath(posixpath.join("xl", path))
    if path.startswith("../") or not path.startswith("xl/"):
        raise BulkReportError("XLSX 首个工作表路径不安全。")
    _zip_info(archive, path)
    return path


def _all_text(element: ET.Element) -> str:
    return "".join(
        node.text or ""
        for node in element.iter()
        if _local_name(node.tag) == "t"
    )


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        info = archive.getinfo("xl/sharedStrings.xml")
    except KeyError:
        return []
    if info.file_size > MAX_ZIP_MEMBER_BYTES:
        raise BulkReportError("XLSX 共享字符串超过安全大小限制。")
    values: list[str] = []
    try:
        with archive.open(info) as source:
            for _, element in ET.iterparse(source, events=("end",)):
                if _local_name(element.tag) == "si":
                    values.append(_all_text(element))
                    element.clear()
    except (ET.ParseError, OSError, RuntimeError) as exc:
        raise BulkReportError("XLSX 共享字符串格式异常。") from exc
    return values


def _column_index(reference: str, fallback: int) -> int:
    match = _CELL_REF_RE.match(reference)
    if not match:
        return fallback
    index = 0
    for char in match.group(1).upper():
        index = index * 26 + ord(char) - 64
    return index - 1


def _cell_value(cell: ET.Element, shared_strings: Sequence[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return _all_text(cell)
    value = next(
        (
            child.text or ""
            for child in cell
            if _local_name(child.tag) == "v"
        ),
        "",
    )
    if cell_type == "s":
        try:
            index = int(value)
            return shared_strings[index]
        except (ValueError, IndexError) as exc:
            raise BulkReportError("XLSX 共享字符串索引无效。") from exc
    if cell_type == "b":
        return "TRUE" if value == "1" else "FALSE"
    return value


def _sheet_rows(
    archive: zipfile.ZipFile,
    path: str,
    shared_strings: Sequence[str],
) -> Iterator[list[str]]:
    info = _zip_info(archive, path)
    try:
        with archive.open(info) as source:
            for _, element in ET.iterparse(source, events=("end",)):
                if _local_name(element.tag) != "row":
                    continue
                values: list[str] = []
                fallback = 0
                for cell in element:
                    if _local_name(cell.tag) != "c":
                        continue
                    index = _column_index(cell.attrib.get("r", ""), fallback)
                    if index < fallback or index > 100_000:
                        raise BulkReportError("XLSX 单元格引用格式异常。")
                    values.extend("" for _ in range(index - len(values)))
                    values.append(_cell_value(cell, shared_strings))
                    fallback = index + 1
                element.clear()
                yield values
    except BulkReportError:
        raise
    except (ET.ParseError, OSError, RuntimeError) as exc:
        raise BulkReportError("XLSX 首个工作表格式异常。") from exc


def parse_first_sheet_xlsx(
    source: str | os.PathLike[str] | bytes | bytearray | BinaryIO,
) -> tuple[list[str], list[dict[str, str]]]:
    """Return the first worksheet as headers and string-valued rows."""

    archive_source: Any = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
    try:
        with zipfile.ZipFile(archive_source) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise BulkReportError("XLSX 内部文件数量超过安全限制。")
            if sum(info.file_size for info in infos) > MAX_ZIP_TOTAL_BYTES:
                raise BulkReportError("XLSX 解压后超过安全大小限制。")
            sheet_path = _first_sheet_path(archive)
            shared = _shared_strings(archive)
            headers: list[str] = []
            rows: list[dict[str, str]] = []
            for values in _sheet_rows(archive, sheet_path, shared):
                while values and not _text(values[-1]):
                    values.pop()
                if not values:
                    continue
                if not headers:
                    headers = [_text(value) for value in values]
                    if any(not header for header in headers):
                        raise BulkReportError("XLSX 表头包含空列名。")
                    if len(set(headers)) != len(headers):
                        raise BulkReportError("XLSX 表头包含重复列名。")
                    continue
                if len(values) > len(headers):
                    raise BulkReportError("XLSX 数据列数超过表头列数。")
                values.extend("" for _ in range(len(headers) - len(values)))
                if any(_text(value) for value in values):
                    rows.append(dict(zip(headers, values)))
            if not headers:
                raise BulkReportError("XLSX 首个工作表为空。")
            return headers, rows
    except BulkReportError:
        raise
    except (zipfile.BadZipFile, OSError, TypeError, ValueError) as exc:
        raise BulkReportError("文件不是有效的 XLSX。") from exc


def _normalized_header(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _text(value))
    return re.sub(r"\s+", "", text).casefold()


def _header_mapping(report_type: str) -> dict[str, str]:
    code = normalize_report_type(report_type)
    return CAMPAIGN_HEADERS if code == CAMPAIGN_REPORT else TARGETING_HEADERS


def _decimal_value(value: Any, field_name: str) -> Decimal:
    text = unicodedata.normalize("NFKC", _text(value))
    if text.casefold() in {"", "-", "--", "n/a", "null"}:
        return Decimal("0")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    percent = text.endswith("%")
    if percent:
        text = text[:-1].strip()
    text = text.replace(",", "")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise BulkReportError(f"字段 {field_name} 不是有效数字。") from exc
    if not number.is_finite():
        raise BulkReportError(f"字段 {field_name} 不是有限数字。")
    if negative:
        number = -number
    return number / 100 if percent else number


def excel_date_to_iso(value: Any, field_name: str = "日期") -> str:
    """Convert an Excel serial or a common date string to YYYY-MM-DD."""

    text = unicodedata.normalize("NFKC", _text(value))
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if fmt != "%Y%m%d" else text, fmt).date().isoformat()
        except ValueError:
            continue
    if "T" in text or " " in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    if _NUMERIC_RE.fullmatch(text):
        try:
            serial = Decimal(text)
            whole_days = int(serial.to_integral_value(rounding=ROUND_FLOOR))
            converted = date(1899, 12, 30) + timedelta(days=whole_days)
        except (InvalidOperation, ValueError, OverflowError) as exc:
            raise BulkReportError(f"字段 {field_name} 的 Excel 日期序列无效。") from exc
        if whole_days < 1:
            raise BulkReportError(f"字段 {field_name} 的 Excel 日期序列无效。")
        return converted.isoformat()
    raise BulkReportError(f"字段 {field_name} 不是有效日期。")


def normalize_report_rows(
    headers: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    report_type: str,
) -> list[dict[str, Any]]:
    """Map the official Chinese export columns to stable field names."""

    code = normalize_report_type(report_type)
    mapping = _header_mapping(code)
    aliases = {_normalized_header(source): target for source, target in mapping.items()}
    resolved: dict[str, str] = {}
    for source in headers:
        target = aliases.get(_normalized_header(source))
        if not target:
            continue
        if target in resolved.values():
            raise BulkReportError(f"报表列 {target} 重复。")
        resolved[source] = target
    missing = [target for target in mapping.values() if target not in resolved.values()]
    if missing:
        raise BulkReportError("报表缺少必需列：" + ", ".join(missing))

    normalized: list[dict[str, Any]] = []
    for row_number, source_row in enumerate(rows, start=2):
        target_row: dict[str, Any] = {}
        for source, target in resolved.items():
            value = source_row.get(source, "")
            if target in DECIMAL_FIELDS:
                target_row[target] = _decimal_value(value, target)
            elif target in DATE_FIELDS:
                text = _text(value)
                if target == "campaign_end_date" and text == "无结束日期":
                    target_row[target] = text
                else:
                    target_row[target] = excel_date_to_iso(text, target)
            elif target in ID_FIELDS:
                target_row[target] = _text(value)
            else:
                target_row[target] = _text(value)
        required_values = ["shop_name", "report_date", "campaign_name", "campaign_id"]
        if code == TARGETING_REPORT:
            required_values.extend(("target_text", "ad_group_id", "target_id"))
        empty = [field for field in required_values if not target_row.get(field)]
        if empty:
            raise BulkReportError(
                f"报表第 {row_number} 行缺少必需值：" + ", ".join(empty)
            )
        normalized.append(target_row)
    return normalized


def _report_type_from_filename(path: Path) -> str:
    name = path.name.casefold()
    if CAMPAIGN_REPORT.casefold() in name:
        return CAMPAIGN_REPORT
    if TARGETING_REPORT.casefold() in name:
        return TARGETING_REPORT
    raise BulkReportError("XLSX 文件名不含受支持的广告报表类型。")


def _row_identity(row: Mapping[str, Any], report_type: str) -> tuple[str, ...]:
    fields = ["shop_id", "report_date", "campaign_id"]
    if report_type == TARGETING_REPORT:
        fields.extend(("ad_group_id", "target_id"))
    return tuple(_text(row.get(field)) for field in fields)


def parse_report_directory(
    path: str | os.PathLike[str],
    shop_name_to_id: Mapping[str, str],
) -> ParsedReportBundle:
    """Parse and merge saved campaign and targeting XLSX files."""

    root = Path(path).resolve()
    if not root.is_dir():
        raise BulkReportError("广告报表目录不存在。")
    explicit = {_text(name): _text(shop_id) for name, shop_id in shop_name_to_id.items()}
    if any(not name or not shop_id for name, shop_id in explicit.items()):
        raise BulkReportError("店铺名称到 ID 的映射不能为空。")
    id_to_name: dict[str, str] = {}
    for name, shop_id in explicit.items():
        if shop_id in id_to_name and _normalized_name(id_to_name[shop_id]) != _normalized_name(name):
            raise BulkReportError("同一店铺 ID 对应多个不同名称。")
        id_to_name[shop_id] = name

    candidates = sorted(root.glob("*.xlsx"), key=lambda item: item.name.casefold())
    unsupported = [
        item
        for item in candidates
        if CAMPAIGN_REPORT.casefold() not in item.name.casefold()
        and TARGETING_REPORT.casefold() not in item.name.casefold()
    ]
    if unsupported:
        raise BulkReportError("目录中包含无法识别类型的 XLSX。")
    files = [
        item
        for item in candidates
        if CAMPAIGN_REPORT.casefold() in item.name.casefold()
        or TARGETING_REPORT.casefold() in item.name.casefold()
    ]
    if not files:
        raise BulkReportError("目录中没有受支持的广告报表 XLSX。")

    grouped = {
        CAMPAIGN_REPORT: {shop_id: [] for shop_id in id_to_name},
        TARGETING_REPORT: {shop_id: [] for shop_id in id_to_name},
    }
    flat = {CAMPAIGN_REPORT: [], TARGETING_REPORT: []}
    seen = {CAMPAIGN_REPORT: set(), TARGETING_REPORT: set()}
    for report_path in files:
        code = _report_type_from_filename(report_path)
        headers, raw_rows = parse_first_sheet_xlsx(report_path)
        rows = normalize_report_rows(headers, raw_rows, code)
        attributed = attribute_rows_to_shops(
            rows,
            id_to_name,
            explicit_name_to_id=explicit,
        )
        for shop_id, shop_rows in attributed.items():
            for row in shop_rows:
                identity = _row_identity(row, code)
                if identity in seen[code]:
                    raise BulkReportError("广告报表目录包含重复数据行。")
                seen[code].add(identity)
                grouped[code][shop_id].append(row)
                flat[code].append(row)
    return ParsedReportBundle(
        files=tuple(files),
        campaign_rows=flat[CAMPAIGN_REPORT],
        targeting_rows=flat[TARGETING_REPORT],
        campaign_rows_by_shop=grouped[CAMPAIGN_REPORT],
        targeting_rows_by_shop=grouped[TARGETING_REPORT],
    )


def collect_bulk_reports(
    client: AdsClient,
    shop_name_to_id: Mapping[str, str],
    report_start_date: str,
    report_end_date: str,
    destination: str | os.PathLike[str],
    *,
    report_types: Sequence[str] = (CAMPAIGN_REPORT, TARGETING_REPORT),
    batch_size: int = 50,
    timeout_seconds: float = 900,
    poll_interval_seconds: float = 5,
) -> ParsedReportBundle:
    """Collect selected report types, keep XLSX files, and return parsed rows."""

    clean_mapping = {
        _text(name): _text(shop_id) for name, shop_id in shop_name_to_id.items()
    }
    if not clean_mapping:
        raise BulkReportError("至少需要一个店铺名称到 ID 的映射。")
    destination_path = Path(destination).resolve()
    if destination_path.is_dir() and any(destination_path.glob("*.xlsx")):
        raise BulkReportError("广告报表保存目录已包含 XLSX，请使用空目录。")
    codes = tuple(dict.fromkeys(normalize_report_type(item) for item in report_types))
    if not codes:
        raise BulkReportError("至少需要一种广告报表类型。")
    shop_ids = list(clean_mapping.values())
    tasks: list[ReportTask] = []
    for code in codes:
        tasks.extend(
            create_report_tasks(
                client,
                shop_ids,
                code,
                report_start_date,
                report_end_date,
                batch_size=batch_size,
            )
        )
    ready = wait_for_report_tasks(
        client,
        tasks,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    download_report_files_to_directory(client, ready, destination_path)
    return parse_report_directory(destination_path, clean_mapping)


def attribute_rows_to_shops(
    rows: Sequence[Mapping[str, Any]],
    shop_id_to_name: Mapping[str, str],
    *,
    explicit_name_to_id: Mapping[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Assign report rows by shop name without guessing duplicate names."""

    shops = {_text(shop_id): _text(name) for shop_id, name in shop_id_to_name.items()}
    if any(not shop_id or not name for shop_id, name in shops.items()):
        raise BulkReportError("店铺 ID 与名称映射不能为空。")
    by_name: dict[str, list[str]] = {}
    for shop_id, name in shops.items():
        by_name.setdefault(_normalized_name(name), []).append(shop_id)

    explicit: dict[str, str] = {}
    for name, shop_id in (explicit_name_to_id or {}).items():
        key, clean_id = _normalized_name(name), _text(shop_id)
        if not key or clean_id not in shops:
            raise BulkReportError("显式店铺名称映射无效。")
        if key in explicit and explicit[key] != clean_id:
            raise BulkReportError("显式店铺名称映射存在冲突。")
        explicit[key] = clean_id
    duplicates = {name: ids for name, ids in by_name.items() if len(ids) > 1}
    unresolved = [name for name, ids in duplicates.items() if explicit.get(name) not in ids]
    if unresolved:
        raise BulkReportError("存在重复店铺名称；需要提供显式唯一映射。")

    attributed = {shop_id: [] for shop_id in shops}
    for row_number, row in enumerate(rows, start=2):
        report_name = _normalized_name(row.get("shop_name"))
        if not report_name:
            raise BulkReportError(f"报表第 {row_number} 行缺少店铺名称。")
        shop_id = explicit.get(report_name)
        if not shop_id:
            candidates = by_name.get(report_name, [])
            if len(candidates) != 1:
                raise BulkReportError(f"报表第 {row_number} 行店铺名称无法唯一归属。")
            shop_id = candidates[0]
        target = dict(row)
        target["shop_id"] = shop_id
        attributed[shop_id].append(target)
    return attributed


def collect_bulk_report_rows(
    client: AdsClient,
    shop_id_to_name: Mapping[str, str],
    report_type: str,
    report_start_date: str,
    report_end_date: str,
    *,
    batch_size: int = 50,
    timeout_seconds: float = 900,
    poll_interval_seconds: float = 5,
    explicit_name_to_id: Mapping[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Create, wait, download, parse, and attribute a complete report."""

    shops = {_text(shop_id): _text(name) for shop_id, name in shop_id_to_name.items()}
    attribute_rows_to_shops([], shops, explicit_name_to_id=explicit_name_to_id)
    tasks = create_report_tasks(
        client,
        list(shops),
        report_type,
        report_start_date,
        report_end_date,
        batch_size=batch_size,
    )
    ready = wait_for_report_tasks(
        client,
        tasks,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    result = {shop_id: [] for shop_id in shops}
    with downloaded_report_files(client, ready) as files:
        for downloaded in files:
            headers, raw_rows = parse_first_sheet_xlsx(downloaded.path)
            rows = normalize_report_rows(headers, raw_rows, downloaded.report_type_code)
            task_shops = {shop_id: shops[shop_id] for shop_id in downloaded.shop_ids}
            task_explicit = {
                name: shop_id
                for name, shop_id in (explicit_name_to_id or {}).items()
                if _text(shop_id) in task_shops
            }
            attributed = attribute_rows_to_shops(
                rows,
                task_shops,
                explicit_name_to_id=task_explicit,
            )
            for shop_id, shop_rows in attributed.items():
                result[shop_id].extend(shop_rows)
    return result


__all__ = [
    "BulkReportError",
    "CAMPAIGN_HEADERS",
    "CAMPAIGN_REPORT",
    "CREATE_TASK_PATH",
    "DownloadedReport",
    "PAGE_LIST_PATH",
    "ParsedReportBundle",
    "ReadyReport",
    "ReportTask",
    "TARGETING_HEADERS",
    "TARGETING_REPORT",
    "attribute_rows_to_shops",
    "collect_bulk_reports",
    "collect_bulk_report_rows",
    "create_report_tasks",
    "downloaded_report_files",
    "download_report_files_to_directory",
    "excel_date_to_iso",
    "normalize_report_rows",
    "normalize_report_type",
    "parse_first_sheet_xlsx",
    "parse_report_directory",
    "wait_for_report_tasks",
]
