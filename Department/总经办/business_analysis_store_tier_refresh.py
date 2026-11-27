"""Refresh CengJi using the built-in store scope and tier rules."""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pytds

from secret_settings import sql_server_config


@dataclass(frozen=True)
class TierRule:
    name: str
    minimum: float
    maximum: float
    margin: float
    tier_id: int


# Migrated from the verified production workbook on 2026-11-27. Preserve its
# exact bounds and the existing half-open comparison in _level_for, so removing
# the workbook dependency does not change historical classification behavior.
TIER_RULES = (
    TierRule("铜1", 0, 14999.99, 0.10, 1),
    TierRule("铜2", 15000, 29999.99, 0.10, 2),
    TierRule("铜3", 30000, 44999.99, 0.10, 3),
    TierRule("银1", 45000, 59999.99, 0.20, 4),
    TierRule("银2", 60000, 89999.99, 0.20, 5),
    TierRule("银3", 90000, 119999.99, 0.20, 6),
    TierRule("银4", 120000, 149999.99, 0.20, 7),
    TierRule("金1", 150000, 189999.99, 0.24, 8),
    TierRule("金2", 190000, 229999.99, 0.24, 9),
    TierRule("金3", 230000, 269999.99, 0.24, 10),
    TierRule("金4", 270000, 309999.99, 0.24, 11),
    TierRule("金5", 310000, 349999.99, 0.24, 12),
    TierRule("金6", 350000, 389999.99, 0.24, 13),
    TierRule("金7", 390000, 429999.99, 0.24, 14),
    TierRule("金8", 430000, 469999.99, 0.24, 15),
    TierRule("金9", 470000, 509999.99, 0.24, 16),
    TierRule("钻1", 510000, 549999.99, 0.24, 17),
    TierRule("钻2", 550000, 589999.99, 0.24, 18),
    TierRule("钻3", 590000, 629999.99, 0.24, 19),
    TierRule("钻4", 630000, 669999.99, 0.24, 20),
    TierRule("钻5", 670000, 9999999.99, 0.24, 21),
)
ELIGIBLE_STORES = frozenset({
    2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 15, 16, 17, 18, 20, 21, 22,
    23, 25, 26, 28, 31, 32, 33, 35, 36, 37, 38, 39, 40, 41, 42, 43,
    50, 51, 52, 55,
})


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
    rules, stores = list(TIER_RULES), set(ELIGIBLE_STORES)
    rule_metadata = {
        "ruleSource": "built-in",
        "ruleCount": len(rules),
        "storeCount": len(stores),
    }
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
                **rule_metadata,
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
            **rule_metadata,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(refresh_store_tiers(), ensure_ascii=False))
