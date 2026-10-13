"""Detect qualified store-tier promotions and notify the configured recipient."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Iterable

import pytds

from secret_settings import sql_server_config


PROMOTION_DAYS = 30
DEFAULT_RECIPIENTS = ("蔡晶", "王晓菁", "韩雅俊", "陈子烨", "周俊成")
EXCLUDED_STORES = {55}


@dataclass(frozen=True)
class PromotionEvent:
    store: int
    tier: str
    tier_rank: int
    qualified_on: date
    streak_started_on: date
    previous_highest_rank: int | None
    consecutive: bool

    @property
    def event_id(self) -> str:
        return f"{self.store}:{self.tier_rank}:{self.qualified_on.isoformat()}"


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def detect_promotions(rows: Iterable[tuple], target_dates: set[date] | None = None) -> list[PromotionEvent]:
    """Return first-time highs held for 30 uninterrupted calendar days.

    Each input row is ``(date, store, tier label, tier rank)``. A day qualifies
    at the lowest rank seen in its trailing 30-day window. The window must have
    every calendar day, and that lowest rank must exceed every rank observed
    before the window began.
    """
    histories: dict[int, dict[date, tuple[str, int]]] = defaultdict(dict)
    for raw_day, raw_store, raw_tier, raw_rank in rows:
        day = _as_date(raw_day)
        store = int(raw_store)
        rank = int(raw_rank)
        existing = histories[store].get(day)
        if existing is None or rank > existing[1]:
            histories[store][day] = (str(raw_tier), rank)

    events: list[PromotionEvent] = []
    for store, by_day in histories.items():
        if store in EXCLUDED_STORES:
            continue
        days = sorted(by_day)
        prior_events = 0
        for index, day in enumerate(days):
            start = day - timedelta(days=PROMOTION_DAYS - 1)
            window_days = [start + timedelta(days=offset) for offset in range(PROMOTION_DAYS)]
            if any(window_day not in by_day for window_day in window_days):
                continue
            floor_day = min(window_days, key=lambda item: by_day[item][1])
            tier, floor_rank = by_day[floor_day]
            prior_ranks = [by_day[old_day][1] for old_day in days[:index] if old_day < start]
            previous_highest = max(prior_ranks) if prior_ranks else None
            # Establishing the first observed level is a baseline, not an
            # upgrade. A promotion needs a real historical level to exceed.
            if previous_highest is None or floor_rank <= previous_highest:
                continue
            event = PromotionEvent(
                store=store,
                tier=tier,
                tier_rank=floor_rank,
                qualified_on=day,
                streak_started_on=start,
                previous_highest_rank=previous_highest,
                consecutive=prior_events > 0,
            )
            prior_events += 1
            if target_dates is None or day in target_dates:
                events.append(event)
    return sorted(events, key=lambda item: (item.qualified_on, item.store, item.tier_rank))


def _message(event: PromotionEvent, operator: str = "") -> str:
    heading = "🎉 店铺连续晋级喜报 🎉" if event.consecutive else "🎉 店铺晋级喜报 🎉"
    operator_line = f"店铺负责人：{operator}\n" if operator else ""
    return (
        f"【{heading}】\n"
        f"店铺：{event.store}号店\n"
        f"{operator_line}"
        f"🏆 晋级层级：{event.tier}\n"
        f"📅 连续达标：{PROMOTION_DAYS}天（{event.streak_started_on.isoformat()} 至 {event.qualified_on.isoformat()}）"
    )


def _default_sender(recipient: str, message: str) -> bool:
    from innovation.message_service import MessageService

    return bool(MessageService("company1").send_message(recipient, message))


def _ensure_notification_columns(cursor) -> None:
    columns = (
        ("FaSongDuiXiang", "nvarchar(50)"),
        ("FaSongShiJian", "datetime2"),
        ("FaSongZhuangTai", "nvarchar(20)"),
        ("XiaoXiBiaoShi", "nvarchar(100)"),
        ("FaSongBeiZhu", "nvarchar(500)"),
    )
    for name, data_type in columns:
        cursor.execute(
            f"IF COL_LENGTH('dbo.DianPuJinJi', '{name}') IS NULL "
            f"ALTER TABLE dbo.DianPuJinJi ADD {name} {data_type} NULL"
        )
    cursor.execute(
        """IF NOT EXISTS (
                 SELECT 1 FROM sys.indexes
                  WHERE object_id = OBJECT_ID('dbo.DianPuJinJi')
                    AND name = 'UX_DianPuJinJi_XiaoXiBiaoShi'
             )
             CREATE UNIQUE INDEX UX_DianPuJinJi_XiaoXiBiaoShi
                 ON dbo.DianPuJinJi(XiaoXiBiaoShi)
                 WHERE XiaoXiBiaoShi IS NOT NULL"""
    )


def _tier_label_for_rank(rows: Iterable[tuple], rank: int | None) -> str:
    if rank is None:
        return ""
    for _, _, tier, tier_rank in rows:
        if int(tier_rank) == rank:
            return str(tier)
    return str(rank)


def notify_store_tier_promotions(
    from_date: date,
    through_date: date,
    *,
    sender: Callable[[str, str], bool] | None = None,
    recipient: str | None = None,
) -> dict:
    connection = pytds.connect(**sql_server_config(), timeout=180)
    try:
        cursor = connection.cursor()
        _ensure_notification_columns(cursor)
        connection.commit()
        cursor.execute(
            """
            SELECT RiQi, Dian,
                   CONCAT(CONVERT(nvarchar(20), CengJi1), CONVERT(nvarchar(10), CengJi2)),
                   CengJiID
              FROM CengJi
             WHERE RiQi <= %s
             ORDER BY Dian, RiQi
            """,
            (through_date,),
        )
        rows = cursor.fetchall()
        cursor.execute("SELECT Dian, YunYing FROM v_PinPaiDianPu")
        operators = {int(store): str(operator or "") for store, operator in cursor.fetchall()}

        target_dates = {
            from_date + timedelta(days=offset)
            for offset in range((through_date - from_date).days + 1)
        }
        events = detect_promotions(rows, target_dates)
        send = sender or _default_sender
        sent = []
        failed = []
        skipped = []
        recipients = (recipient,) if recipient else DEFAULT_RECIPIENTS
        recipient_text = "；".join(recipients)
        for event in events:
            message_key = event.event_id
            cursor.execute(
                "SELECT XuHao FROM dbo.DianPuJinJi WHERE XiaoXiBiaoShi = %s",
                (message_key,),
            )
            existing = cursor.fetchone()
            if existing:
                skipped.append(message_key)
                continue
            cursor.execute(
                """INSERT INTO dbo.DianPuJinJi
                       (DianPu, RiQi, YuanDengJi, XinDengJi, YunYing, DianPuJiShu,
                        FaSongDuiXiang, FaSongZhuangTai, XiaoXiBiaoShi)
                     OUTPUT INSERTED.XuHao
                     VALUES (%s, %s, %s, %s, %s, NULL, %s, N'发送中', %s)""",
                (
                    event.store,
                    event.qualified_on,
                    _tier_label_for_rank(rows, event.previous_highest_rank),
                    event.tier,
                    operators.get(event.store, ""),
                    recipient_text,
                    message_key,
                ),
            )
            record_id = int(cursor.fetchone()[0])
            connection.commit()
            event_failures = []
            for target_recipient in recipients:
                cursor.execute(
                    "UPDATE dbo.DianPuJinJi SET FaSongDuiXiang=%s WHERE XuHao=%s",
                    (recipient_text, record_id),
                )
                try:
                    success = send(target_recipient, _message(event, operators.get(event.store, "")))
                    error = "" if success else "飞书消息发送失败"
                except Exception as exc:
                    success = False
                    error = str(exc)
                if success:
                    sent.append(f"{target_recipient}:{event.event_id}")
                else:
                    event_failures.append(f"{target_recipient}：{error}")
                    failed.append({"eventId": event.event_id, "recipient": target_recipient, "error": error})
            final_status = "已发送" if not event_failures else ("发送失败" if len(event_failures) == len(recipients) else "部分失败")
            cursor.execute(
                """UPDATE dbo.DianPuJinJi
                      SET FaSongShiJian=SYSDATETIME(), FaSongZhuangTai=%s, FaSongBeiZhu=%s
                    WHERE XuHao=%s""",
                (final_status, "；".join(event_failures)[:500] or None, record_id),
            )
            connection.commit()
        return {
            "status": "failed" if failed else "completed",
            "detected": len(events),
            "sent": len(sent),
            "skipped": len(skipped),
            "failed": failed,
            "recipients": list(recipients),
        }
    finally:
        connection.close()
