# -*- coding: utf-8 -*-

import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from threading import Lock, Thread

from bjc import sf_db
from innovation.message_service import MessageService


DEFAULT_RUN_HOUR = 11
DEFAULT_RUN_MINUTE = 30
DEFAULT_BATCH_SIZE = 40


def _normalize_importer_name(value):
    name = str(value or "").strip()
    if "@" in name:
        tail = name.split("@")[-1].strip()
        if tail:
            name = tail
    return name


def _clip_text(value, limit=140):
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, int(limit) - 1)].rstrip() + "…"


def load_yesterday_tracking_records(now_dt=None, query_fn=sf_db):
    now = now_dt if isinstance(now_dt, datetime) else datetime.now()
    target_date = (now - timedelta(days=1)).date()
    next_date = target_date + timedelta(days=1)
    start_text = target_date.strftime("%Y-%m-%d")
    end_text = next_date.strftime("%Y-%m-%d")
    rows = query_fn(f"""
        SELECT DISTINCT
            hz.SKU,
            zd.dian,
            hz.ID,
            hz.DaoRuRen,
            hz.DaoRuShiJian,
            hz.FaYangDingDanHao,
            COALESCE(NULLIF(dd_exact.GenZongHao, ''), dd_order.GenZongHao, '') AS GenZongHao,
            CASE
                WHEN NULLIF(dd_exact.GenZongHao, '') IS NOT NULL THEN dd_exact.fahuoshijian
                ELSE dd_order.fahuoshijian
            END AS fahuoshijian,
            dd_exact.kefubeizhu
        FROM TK_WangHong_HeZuo hz
        LEFT JOIN ZiDian zd
            ON hz.SKU = zd.SKU
        LEFT JOIN (
            SELECT
                UPPER(LTRIM(RTRIM(ISNULL(CAST(DanHao AS NVARCHAR(100)), '')))) AS join_danhao,
                UPPER(LTRIM(RTRIM(ISNULL(CAST(SKU AS NVARCHAR(100)), '')))) AS join_sku,
                MAX(ISNULL(GenZongHao, '')) AS GenZongHao,
                MAX(fahuoshijian) AS fahuoshijian,
                MAX(ISNULL(kefubeizhu, '')) AS kefubeizhu
            FROM TK_DingDan_shouhou
            GROUP BY
                UPPER(LTRIM(RTRIM(ISNULL(CAST(DanHao AS NVARCHAR(100)), '')))),
                UPPER(LTRIM(RTRIM(ISNULL(CAST(SKU AS NVARCHAR(100)), ''))))
        ) dd_exact
            ON UPPER(LTRIM(RTRIM(ISNULL(CAST(hz.FaYangDingDanHao AS NVARCHAR(100)), '')))) = dd_exact.join_danhao
           AND UPPER(LTRIM(RTRIM(ISNULL(CAST(hz.SKU AS NVARCHAR(100)), '')))) = dd_exact.join_sku
        LEFT JOIN (
            SELECT
                UPPER(LTRIM(RTRIM(ISNULL(CAST(DanHao AS NVARCHAR(100)), '')))) AS join_danhao,
                MAX(LTRIM(RTRIM(ISNULL(CAST(GenZongHao AS NVARCHAR(500)), '')))) AS GenZongHao,
                MAX(fahuoshijian) AS fahuoshijian
            FROM TK_DingDan_shouhou
            WHERE LTRIM(RTRIM(ISNULL(CAST(GenZongHao AS NVARCHAR(500)), ''))) <> ''
            GROUP BY
                UPPER(LTRIM(RTRIM(ISNULL(CAST(DanHao AS NVARCHAR(100)), ''))))
            HAVING COUNT(DISTINCT UPPER(LTRIM(RTRIM(CAST(GenZongHao AS NVARCHAR(500)))))) = 1
        ) dd_order
            ON UPPER(LTRIM(RTRIM(ISNULL(CAST(hz.FaYangDingDanHao AS NVARCHAR(100)), '')))) = dd_order.join_danhao
        WHERE hz.DaoRuShiJian >= CONVERT(date, '{start_text}', 23)
          AND hz.DaoRuShiJian < CONVERT(date, '{end_text}', 23)
          AND LTRIM(RTRIM(ISNULL(CAST(hz.DaoRuRen AS NVARCHAR(200)), ''))) <> ''
          AND ISNULL(hz.FaYangDingDanHao, '') <> ''
          AND CHARINDEX('57', ISNULL(CAST(hz.FaYangDingDanHao AS NVARCHAR(100)), '')) = 0
          AND CHARINDEX('TKWS', UPPER(ISNULL(CAST(hz.SKU AS NVARCHAR(100)), ''))) = 0
          AND COALESCE(NULLIF(dd_exact.GenZongHao, ''), dd_order.GenZongHao, '') <> ''
        ORDER BY hz.DaoRuRen ASC, hz.ID DESC
    """) or []
    columns = [
        "SKU",
        "dian",
        "ID",
        "DaoRuRen",
        "DaoRuShiJian",
        "FaYangDingDanHao",
        "GenZongHao",
        "fahuoshijian",
        "kefubeizhu",
    ]
    records = []
    for row in rows:
        if isinstance(row, dict):
            item = {
                key: row.get(key) if key in row else row.get(key.lower())
                for key in columns
            }
        elif isinstance(row, (list, tuple)):
            item = {
                key: row[index] if index < len(row) else None
                for index, key in enumerate(columns)
            }
        else:
            continue
        importer = _normalize_importer_name(item.get("DaoRuRen"))
        tracking_no = str(item.get("GenZongHao") or "").strip()
        if not importer or not tracking_no:
            continue
        item["DaoRuRen"] = importer
        for key in ("SKU", "dian", "FaYangDingDanHao", "GenZongHao", "kefubeizhu"):
            item[key] = str(item.get(key) or "").strip()
        for key in ("DaoRuShiJian", "fahuoshijian"):
            value = item.get(key)
            if isinstance(value, datetime):
                item[key] = value.strftime("%Y-%m-%d %H:%M:%S")
            else:
                item[key] = str(value or "").strip()
        records.append(item)
    return records


def group_tracking_records_by_importer(records):
    grouped = defaultdict(list)
    for record in records or []:
        importer = _normalize_importer_name(record.get("DaoRuRen"))
        if importer:
            grouped[importer].append(record)
    return dict(grouped)


def build_tracking_messages(importer, records, target_date, batch_size=DEFAULT_BATCH_SIZE):
    items = list(records or [])
    safe_batch_size = max(int(batch_size or DEFAULT_BATCH_SIZE), 1)
    batch_count = max(1, (len(items) + safe_batch_size - 1) // safe_batch_size)
    date_text = (
        target_date.strftime("%Y-%m-%d")
        if hasattr(target_date, "strftime")
        else str(target_date or "").strip()
    )
    messages = []
    for batch_index in range(batch_count):
        batch = items[
            batch_index * safe_batch_size : (batch_index + 1) * safe_batch_size
        ]
        batch_tip = f"（第 {batch_index + 1}/{batch_count} 批）" if batch_count > 1 else ""
        lines = [
            f"【客服跟踪号通知｜{date_text}】{batch_tip}",
            "",
            f"{importer}，你前一天导入的 {len(items)} 条记录已有跟踪号：",
            "",
        ]
        for index, item in enumerate(batch, start=batch_index * safe_batch_size + 1):
            lines.extend(
                [
                    f"{index}. 订单号：{_clip_text(item.get('FaYangDingDanHao')) or '-'}",
                    f"   SKU：{_clip_text(item.get('SKU')) or '-'}"
                    f"｜店铺：{_clip_text(item.get('dian')) or '-'}",
                    f"   跟踪号：{_clip_text(item.get('GenZongHao'), limit=240) or '-'}",
                ]
            )
            ship_time = _clip_text(item.get("fahuoshijian"))
            if ship_time:
                lines.append(f"   发货时间：{ship_time}")
            note = _clip_text(item.get("kefubeizhu"), limit=180)
            if note:
                lines.append(f"   客服备注：{note}")
            lines.append("")
        lines.append("请及时核对以上订单的物流信息。")
        messages.append("\n".join(lines).strip())
    return messages


class TkCustomerServiceTrackingReminder:
    def __init__(
        self,
        query_fn=sf_db,
        service_factory=None,
        enabled=None,
        run_hour=DEFAULT_RUN_HOUR,
        run_minute=DEFAULT_RUN_MINUTE,
    ):
        self.query_fn = query_fn
        self.service_factory = service_factory or (lambda: MessageService("company1"))
        if enabled is None:
            raw = str(
                os.environ.get("TK_CUSTOMER_SERVICE_REMINDER_ENABLED", "1")
            ).strip().lower()
            enabled = raw not in {"0", "false", "no", "off"}
        self.enabled = bool(enabled)
        self.run_hour = int(run_hour)
        self.run_minute = int(run_minute)
        self._lock = Lock()
        self._thread_started = False
        self._last_attempt_date = ""
        self._sent_batches = set()
        self.last_result = None

    @property
    def thread_started(self):
        with self._lock:
            return self._thread_started

    def is_due(self, now_dt=None):
        now = now_dt if isinstance(now_dt, datetime) else datetime.now()
        return (now.hour, now.minute) >= (self.run_hour, self.run_minute)

    def run_once(self, now_dt=None, send_messages=True, include_message_details=False):
        now = now_dt if isinstance(now_dt, datetime) else datetime.now()
        target_date = (now - timedelta(days=1)).date()
        records = load_yesterday_tracking_records(now_dt=now, query_fn=self.query_fn)
        grouped = group_tracking_records_by_importer(records)
        result = {
            "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "target_date": target_date.strftime("%Y-%m-%d"),
            "record_count": len(records),
            "importer_count": len(grouped),
            "message_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "dry_run": not send_messages,
            "importers": {},
        }
        if not send_messages:
            result["importers"] = {
                importer: len(items) for importer, items in grouped.items()
            }
            self.last_result = result
            return result

        message_service = self.service_factory()
        for importer, items in grouped.items():
            messages = build_tracking_messages(importer, items, target_date)
            importer_result = {
                "record_count": len(items),
                "message_count": len(messages),
                "success": 0,
                "failed": 0,
                "skipped": 0,
            }
            if include_message_details:
                importer_result["messages"] = []
            for batch_index, message in enumerate(messages, start=1):
                dedupe_key = (
                    target_date.strftime("%Y-%m-%d"),
                    importer,
                    batch_index,
                )
                with self._lock:
                    already_sent = dedupe_key in self._sent_batches
                if already_sent:
                    importer_result["skipped"] += 1
                    result["skipped_count"] += 1
                    if include_message_details:
                        importer_result["messages"].append(
                            {
                                "batch": batch_index,
                                "success": True,
                                "skipped": True,
                                "message": message,
                            }
                        )
                    continue
                result["message_count"] += 1
                try:
                    sent = bool(message_service.send_message(importer, message))
                except Exception:
                    sent = False
                if sent:
                    with self._lock:
                        self._sent_batches.add(dedupe_key)
                    importer_result["success"] += 1
                    result["success_count"] += 1
                else:
                    importer_result["failed"] += 1
                    result["failed_count"] += 1
                if include_message_details:
                    detail = {
                        "batch": batch_index,
                        "success": sent,
                        "skipped": False,
                        "message": message,
                    }
                    if not sent:
                        last_result = getattr(message_service, "last_send_result", None)
                        if isinstance(last_result, dict):
                            detail["error"] = str(
                                last_result.get("msg")
                                or last_result.get("message")
                                or last_result.get("error")
                                or ""
                            ).strip()
                    importer_result["messages"].append(detail)
            result["importers"][importer] = importer_result
        self.last_result = result
        return result

    def _loop(self):
        while True:
            now = datetime.now()
            day_key = now.strftime("%Y-%m-%d")
            should_run = False
            if self.is_due(now):
                with self._lock:
                    if self._last_attempt_date != day_key:
                        self._last_attempt_date = day_key
                        should_run = True
            if should_run:
                try:
                    self.run_once(now_dt=now, send_messages=True)
                except Exception as exc:
                    self.last_result = {
                        "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "error": str(exc),
                    }
                    with self._lock:
                        self._last_attempt_date = ""
            time.sleep(30)

    def start(self):
        if not self.enabled:
            return False
        with self._lock:
            if self._thread_started:
                return True
            thread = Thread(
                target=self._loop,
                name="tk_customer_service_tracking_reminder",
                daemon=True,
            )
            thread.start()
            self._thread_started = True
        return True


tk_customer_service_tracking_reminder = TkCustomerServiceTrackingReminder()
