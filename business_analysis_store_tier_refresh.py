"""Refresh CengJi with the same rules as the Excel `刷新等级` button."""

from __future__ import annotations

import calendar
import json
import os
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl
import pytds

from secret_settings import sql_server_config


warnings.filterwarnings(
    "ignore",
    message="Conditional Formatting extension is not supported and will be removed",
    module="openpyxl.worksheet._reader",
)

DEFAULT_TEMPLATE = Path(r"C:\Users\admin\Desktop\每日数据模板-8.xlsm")


@dataclass(frozen=True)
class TierRule:
    name: str
    minimum: float
    maximum: float
    margin: float
    tier_id: int


def _template_path() -> Path:
    return Path(os.environ.get("BUSINESS_ANALYSIS_TIER_TEMPLATE", str(DEFAULT_TEMPLATE)))


def _load_template() -> tuple[list[TierRule], set[int]]:
    path = _template_path()
    if not path.is_file():
        raise FileNotFoundError(f"店铺等级模板不存在: {path}")

    # The workbook is read-only; its Excel-only formatting extensions stay untouched.
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_vba=True)
    try:
        settings = workbook["设置"]
        rules: list[TierRule] = []
        for values in settings.iter_rows(min_row=2, min_col=1, max_col=5, values_only=True):
            name, minimum, maximum, margin, tier_id = values
            if not name:
                break
            rules.append(
                TierRule(
                    name=str(name).strip(),
                    minimum=float(minimum or 0),
                    maximum=float(maximum),
                    margin=float(margin),
                    tier_id=int(tier_id),
                )
            )

        level_sheet = workbook["店铺等级"]
        stores = {
            int(value)
            for (value,) in level_sheet.iter_rows(min_row=2, min_col=2, max_col=2, values_only=True)
            if isinstance(value, (int, float))
        }
    finally:
        workbook.close()

    if not rules:
        raise RuntimeError("模板“设置”页没有层级规则")
    if not stores:
        raise RuntimeError("模板“店铺等级”页没有店铺")
    return rules, stores


def _fee_map(cursor, start: date, end: date) -> dict[int, float]:
    y1, m1 = start.year, start.month
    y2, m2 = end.year, end.month
    if m1 == m2 and y1 == y2:
        cursor.execute(
            "SELECT Dian, ROUND(CangChuFei, 0) FROM CangChuFei WHERE Nian=%s AND Yue=%s",
            (y1, m1),
        )
        return {int(store): float(fee or 0) for store, fee in cursor.fetchall()}

    cursor.execute("SELECT COUNT(*) FROM CangChuFei WHERE Nian=%s AND Yue=%s", (y2, m2))
    if int(cursor.fetchone()[0]) == 0:
        cursor.execute(
            "SELECT Dian, ROUND(CangChuFei, 0) FROM CangChuFei WHERE Nian=%s AND Yue=%s",
            (y1, m1),
        )
        return {int(store): float(fee or 0) for store, fee in cursor.fetchall()}

    first_days = calendar.monthrange(y1, m1)[1] - start.day + 1
    second_days = end.day
    cursor.execute(
        """
        SELECT first_fee.Dian,
               ROUND(first_fee.CangChuFei / 30.0 * %s + second_fee.CangChuFei / 30.0 * %s, 0)
          FROM (SELECT Dian, CangChuFei FROM CangChuFei WHERE Nian=%s AND Yue=%s) first_fee
          LEFT JOIN (SELECT Dian, CangChuFei FROM CangChuFei WHERE Nian=%s AND Yue=%s) second_fee
            ON first_fee.Dian=second_fee.Dian
        """,
        (first_days, second_days, y1, m1, y2, m2),
    )
    return {int(store): float(fee or 0) for store, fee in cursor.fetchall() if fee is not None}


def _level_for(rules: list[TierRule], sales: float, margin: float) -> tuple[TierRule, str]:
    candidate_index = next(
        (index for index, rule in enumerate(rules) if rule.minimum <= sales < rule.maximum),
        len(rules) - 1,
    )
    candidate = rules[candidate_index]
    if margin >= candidate.margin:
        return candidate, "销售额达标且毛利率达标"
    if candidate_index == 0:
        return candidate, "销售额达标但毛利率不达标，最低层级"
    final_rule = rules[candidate_index - 1]
    decision = (
        f"销售额达到【{candidate.name}，[{candidate.minimum:g}，{candidate.maximum:g})，"
        f"{candidate.margin:.0%}】，但毛利率不达标，降一级"
    )
    return final_rule, decision


def _rows_for_date(cursor, target: date, rules: list[TierRule], stores: set[int]) -> list[tuple]:
    start = target - timedelta(days=29)
    cursor.execute(
        """
        SELECT Dian, SUM(XiaoShouE), SUM(MaoLiLvFenMu), SUM(MaoLiRun)
          FROM v_MaoLiLv
         WHERE RiQi BETWEEN %s AND %s
         GROUP BY Dian
         ORDER BY Dian
        """,
        (start, target),
    )
    aggregates = cursor.fetchall()
    fees = _fee_map(cursor, start, target)
    rows: list[tuple] = []
    for store, sales, denominator, profit in aggregates:
        store = int(store)
        if store not in stores:
            continue
        sales = float(sales or 0)
        denominator = float(denominator or 0)
        margin = ((float(profit or 0) - fees.get(store, 0.0)) / denominator) if denominator else 0.0
        rule, decision = _level_for(rules, sales, margin)
        standard = f"销售额 [{rule.minimum:g},{rule.maximum:g})，毛利率 {rule.margin:.0%}"
        rows.append(
            (
                target,
                store,
                rule.name[0],
                int(rule.name[1:]),
                rule.tier_id,
                start,
                target,
                sales,
                round(margin * 100, 2),
                standard,
                decision,
                datetime.now(),
            )
        )
    if not rows:
        raise RuntimeError(f"{target.isoformat()} 未查询到可用的店铺层级数据")
    return rows


def _missing_tier_dates(existing_dates: set[date], target_end: date) -> list[date]:
    """Return historical gaps plus dates not yet appended, in date order."""
    if not existing_dates:
        return [target_end]
    first_observed = min(existing_dates)
    if first_observed > target_end:
        return []
    pending: list[date] = []
    target = first_observed
    while target <= target_end:
        if target not in existing_dates:
            pending.append(target)
        target += timedelta(days=1)
    return pending


def refresh_store_tiers(today: date | None = None, dry_run: bool = False) -> dict:
    """Backfill through today-2; replace each date only after all rows are calculated."""
    rules, stores = _load_template()
    target_end = (today or date.today()) - timedelta(days=2)
    connection = pytds.connect(**sql_server_config(), timeout=180)
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT DISTINCT CAST(RiQi AS date) FROM CengJi WHERE RiQi <= %s", (target_end,))
        existing_dates = {
            value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
            for (value,) in cursor.fetchall()
            if value is not None
        }
        pending_dates = _missing_tier_dates(existing_dates, target_end)
        latest = max(existing_dates) if existing_dates else None
        if not pending_dates:
            connection.rollback()
            return {
                "status": "up-to-date",
                "throughDate": latest.isoformat() if latest else None,
                "rowCount": 0,
                "templatePath": str(_template_path()),
            }

        pending: list[tuple[date, list[tuple]]] = []
        for target in pending_dates:
            pending.append((target, _rows_for_date(cursor, target, rules, stores)))

        if dry_run:
            connection.rollback()
        else:
            for target, rows in pending:
                cursor.execute("DELETE FROM CengJi WHERE RiQi=%s", (target,))
                cursor.executemany(
                    """
                    INSERT INTO CengJi
                      (RiQi,Dian,CengJi1,CengJi2,CengJiID,SD,ED,JinE,MaoLiLv,BiaoZhun,PanDuanGuoCheng,DaoRuShiJian)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    rows,
                )
            connection.commit()

        return {
            "status": "dry-run" if dry_run else "refreshed",
            "fromDate": pending[0][0].isoformat(),
            "throughDate": pending[-1][0].isoformat(),
            "dateCount": len(pending),
            "rowCount": sum(len(rows) for _, rows in pending),
            "templatePath": str(_template_path()),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(refresh_store_tiers(), ensure_ascii=False))
