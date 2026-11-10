"""智能补货（“亚马逊补货系统”可迁移包）算法的本地移植。

来源：`下单系统逻辑说明.md` + `test_rules_1_2.py`（可迁移包 2026-10-30）。
移植目标：把「建议下单量」接进日常补货主表的「订货量」列。

与源实现的差异（均为数据源或默认参数上的差异，逐条记录）：
1. 输入不再是 Excel 工作簿，而是已经生成好的主表行 + 数据库查询；
2. 规则 3（近 7 天找运营减单拦截）默认关闭，且当前没有可解析的批注来源；
3. 规则 4（店铺高存销比压低目标天数）需要存销比数据，当前数据库未提供，按 0 差值处理；
4. 规则 13（毛利骤降减 1 件）依赖逐月毛利历史，默认不启用；
5. 规则 9 / 规则 10 的调整量沿用源实现默认 0，只记录原因、不改数量；
6. 规则 A（自适应日均销量）默认关闭。

因此默认参数下真正影响数量的只有：
主盘面 A/B/C 目标天数缺口、百件档位取整、最小起补缺口、分站点缺口（规则 8）、
以及规则 5/6/7/14 的硬性不下单拦截。
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from typing import Any

import daily_replenishment as base


# 源实现默认参数（见《下单系统逻辑说明》第 5 节）
DEFAULT_PARAMS: dict[str, Any] = {
    "target_a": 80.0,
    "target_b": 65.0,
    "target_c": 55.0,
    "sea_target_a": 90.0,
    "sea_target_b": 75.0,
    "sea_target_c": 65.0,
    "trigger_offset": 7.0,
    "min_gap": 70.0,
    "ab_sufficient_days": 30.0,
    "rule11_min_sales": 5.0,
    "rule11_low_days": 30.0,
    "high_margin_threshold": 25.0,
    "rule9_multiplier": 5.0,
    "rule9_threshold": 10.0,
    "rule9_adjust": 0.0,
    "rule10_k_divisor": 2.0,
    "rule10_adjust": 0.0,
    "rule13_drop_threshold": 10.0,
    "rule13_adjust": 1,
    "rule14_min_sales": 5.0,
    "rule3_enabled": False,
    "rule_a_enabled": False,
    "rule_a_falling": 0.85,
    "rule_a_rising": 1.15,
    "rule_a_max_multiplier": 1.5,
    "cxb_diff_threshold": 0.4,
    "cxb_reduction": 10.0,
}

# 销量来源对应的表与列（与 base._generation_sql 保持一致）
_SALES_SOURCES = {
    "付款": ("v_XiaoShouLiang", "HeSuanXiaoLiang"),
    "下单": ("GuangGao", "ShuLiang"),
}

# 主表列下标（与 DEFAULT_HEADERS 对齐）
_COL_STORE = 1
_COL_CATEGORY = 2
_COL_SKU = 3
_COL_TOTAL = 4
_COL_FBA = 5
_COL_PENDING = 6
_COL_DAILY = 8
_COL_K = 9
_COL_DAYS_WITH_PENDING = 12
_COL_ORDER = 13
_COL_DAYS_AFTER_ORDER = 14
_COL_REMARK = 17
_COL_AB = 19

_SKU_INDEX = 0
_COUNTRY_INDEX = 1
_LOCAL_INDEX = 2
_SITE_SALES_INDEX = 3
_SITE_DAILY_INDEX = 4
_SITE_DAYS_INDEX = 5

_AB_PATTERN = re.compile(r"(\d+)-([12])")


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value or "").strip().replace(",", "")
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    if not math.isfinite(number):
        return None
    return number


def _normalized_store(value: Any) -> str:
    store = str(value or "").strip()
    if store.endswith(".0") and store[:-2].replace("-", "").isdigit():
        store = store[:-2]
    if store in {"nan", "未知店铺", "0", ""}:
        return ""
    return store


def _normalized_category(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    if not text or text.lower() == "nan":
        return "C"
    return text[0].upper()


def _tier_round(quantity: float) -> int:
    """源实现的百件档位取整。"""
    if quantity <= 100:
        return 100
    if quantity <= 150:
        return 150
    if quantity <= 200:
        return 200
    if quantity <= 6000:
        return int(math.ceil(quantity / 100.0) * 100)
    return int(math.ceil(quantity / 500.0) * 500)


def _trigger_days(target_days: dict[str, float], offset: float) -> dict[str, float]:
    return {key: max(0.0, float(target) - offset) for key, target in target_days.items()}


def _window_average(history: list[tuple[Any, float]], window: int) -> tuple[float | None, int, list[tuple[Any, float]]]:
    """取最近 window 条历史，返回（均值，实际条数，选中区间）。"""
    selected = list(history)[-window:] if window > 0 else []
    if not selected:
        return None, 0, []
    return sum(item[1] for item in selected) / len(selected), len(selected), selected


def _adaptive_sales(history: list[tuple[Any, float]], original: float, params: dict[str, Any], window: int) -> tuple[float, str]:
    """规则 A：自适应日均销量（默认关闭）。"""
    values = [item[1] for item in list(history)[-window:]]
    values.reverse()
    if len(values) < 3:
        return original, "数据不足,使用原值"
    avg_3 = sum(values[:3]) / 3.0
    avg_period = sum(values) / len(values)
    bias = avg_3 / avg_period if avg_period > 0 else 0.0
    if bias < float(params["rule_a_falling"]):
        return avg_3, f"下降(3d均值:{avg_3:.1f})"
    if bias > float(params["rule_a_rising"]):
        avg_7 = sum(values[:7]) / min(7, len(values))
        limit = original * float(params["rule_a_max_multiplier"])
        if avg_7 > limit:
            return limit, f"上升(7d追涨-触发1.5倍上限:{limit:.1f})"
        return avg_7, f"上升(7d均值:{avg_7:.1f})"
    return avg_period, f"平稳({len(values)}d均值:{avg_period:.1f})"


def build_context(
    settings: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    query_executor=base.sf_db,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从数据库准备算法所需上下文；任何一项取数失败都降级为空，不影响主表生成。"""
    options = dict(DEFAULT_PARAMS)
    if params:
        options.update(params)
    window = int(settings.get("recent_days") or 15)

    skus = {
        str(row["values"][_COL_SKU] or "").strip()
        for row in rows
        if str(row["values"][_COL_SKU] or "").strip()
    }
    context: dict[str, Any] = {
        "history": {},
        "sites": {},
        "margins": {},
        "clearance": set(),
        "ocean": set(),
        "store_cxb": {},
        "company_cxb": 0.0,
        "latest_sales": {},
        "window_days": window,
        "params": options,
    }
    if not skus:
        return context

    start = settings["sales_start"].isoformat()
    end = settings["sales_end"].isoformat()

    # 逐日销量（近 window+2 天），用于规则 14 的细节与站点销量系数
    table, column = _SALES_SOURCES.get(str(settings.get("sales_source") or "付款"), _SALES_SOURCES["付款"])
    try:
        sales_rows = query_executor(
            "/* daily_replenishment:smart_sales_history */\n"
            f"SELECT SKU,RiQi,SUM(CAST(ISNULL({column},0) AS FLOAT)) Qty\n"
            f"  FROM {table}\n"
            f" WHERE RiQi BETWEEN '{start}' AND '{end}' AND SKU IS NOT NULL\n"
            " GROUP BY SKU,RiQi\n"
            " ORDER BY SKU,RiQi"
        ) or []
    except Exception:
        sales_rows = []
    for raw in sales_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 3:
            continue
        sku = str(raw[0] or "").strip()
        quantity = _num(raw[2])
        if not sku or quantity is None:
            continue
        context["history"].setdefault(sku, []).append((base._coerce_date(raw[1]), quantity))

    for sku, history in context["history"].items():
        history.sort(key=lambda item: (item[0] or date.min))
        context["history"][sku] = history[-15:]
        context["latest_sales"][sku] = history[-1][1]

    # 分站点：国、本地库存、站点日均、站点 FBA 可售天数
    try:
        site_rows = query_executor(
            "/* daily_replenishment:smart_sites */\n"
            "WITH Base AS (\n"
            " SELECT Cang,SKU,\n"
            "        CAST(ISNULL(KeShou,0)+ISNULL(DaiTiaoCang,0)+ISNULL(TiaoCangZhong,0) AS FLOAT) FbaStock,\n"
            "        CAST(ISNULL(ZaiTu,0)+ISNULL(RuCangZhong,0) AS FLOAT) FbaTransit\n"
            "   FROM v_KuCun2 WHERE SKU<>'0'\n"
            "), Sales AS (\n"
            f" SELECT Guo,SKU,SUM(CAST(ISNULL({column},0) AS FLOAT)) Qty\n"
            f"   FROM {table} WHERE RiQi BETWEEN '{start}' AND '{end}' GROUP BY Guo,SKU\n"
            "), LocalStock AS (\n"
            " SELECT SKU,SUM(CAST(ISNULL(ShuLiang,0) AS FLOAT)) Qty FROM v_KuCun1 GROUP BY SKU\n"
            ")\n"
            "SELECT b.SKU,\n"
            "       CASE b.Cang WHEN '欧洲仓' THEN '英国' WHEN '英国仓' THEN '英国'\n"
            "            WHEN '美国仓' THEN '美国' WHEN '加拿大仓' THEN '加拿大'\n"
            "            WHEN '澳洲仓' THEN '澳洲' ELSE b.Cang END Country,\n"
            "       ISNULL(ls.Qty,0) LocalQty, ISNULL(s.Qty,0) SalesQty,\n"
            f"       ROUND(ISNULL(s.Qty,0)/{float(window)},4) DailySales,\n"
            "       CASE WHEN ISNULL(s.Qty,0)=0 THEN 999\n"
            "            ELSE ROUND((b.FbaStock+b.FbaTransit)/(ISNULL(s.Qty,0)"
            f"/{float(window)}),2) END FbaDays\n"
            "  FROM Base b\n"
            "  LEFT JOIN Sales s ON s.SKU=b.SKU AND s.Guo=CASE b.Cang WHEN '欧洲仓' THEN '英国'\n"
            "       WHEN '英国仓' THEN '英国' WHEN '美国仓' THEN '美国'\n"
            "       WHEN '加拿大仓' THEN '加拿大' WHEN '澳洲仓' THEN '澳洲' ELSE b.Cang END\n"
            "  LEFT JOIN LocalStock ls ON ls.SKU=b.SKU\n"
            " ORDER BY b.SKU"
        ) or []
    except Exception:
        site_rows = []
    for raw in site_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 6:
            continue
        sku = str(raw[0] or "").strip()
        country = str(raw[1] or "").strip()
        if not sku or not country:
            continue
        sites = context["sites"].setdefault(sku, [])
        if any(site["country"] == country for site in sites):
            continue  # 源实现：同 SKU 同国只取第一条
        sites.append(
            {
                "country": country,
                "local_inv": _num(raw[2]) or 0.0,
                "fba_sales": _num(raw[4]),
                "fba_days": _num(raw[5]),
            }
        )

    # 当前毛利率（百分比），用于规则 11
    margin_days = 30
    try:
        margin_rows = query_executor(
            "/* daily_replenishment:smart_margins */\n"
            "SELECT SKU, SUM(MaoLiRun)/(SUM(MaoLiLvFenMu)+0.0001) Ratio\n"
            "  FROM v_MaoLiLv\n"
            f" WHERE RiQi>='{(settings['as_of_date'] - timedelta(days=margin_days)).isoformat()}'\n"
            "   AND XiaoShouE<>0 AND SKU IS NOT NULL\n"
            " GROUP BY SKU"
        ) or []
    except Exception:
        margin_rows = []
    for raw in margin_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        sku = str(raw[0] or "").strip()
        ratio = _num(raw[1])
        if sku and ratio is not None:
            context["margins"][sku] = round(ratio * 100.0, 2)

    # 清货（规则 7）与海运（蓝字，目标天数改用海运口径）
    try:
        status_rows = query_executor(
            "/* daily_replenishment:smart_status */\n"
            "SELECT 'clearance' Kind,SKU FROM QingHuo\n"
            "UNION ALL\n"
            "SELECT 'ocean',SKU FROM HaiYunSKU WHERE ZhengChang='Y'"
        ) or []
    except Exception:
        status_rows = []
    for raw in status_rows:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        kind = str(raw[0] or "").strip()
        sku = str(raw[1] or "").strip()
        if not sku:
            continue
        if kind == "clearance":
            context["clearance"].add(sku)
        elif kind == "ocean":
            context["ocean"].add(sku)
    return context


def suggest(
    rows: list[dict[str, Any]],
    context: dict[str, Any],
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """对每一行执行源实现第 6 节的决策顺序，返回 {SKU: 结果}。"""
    options = dict(context.get("params") or DEFAULT_PARAMS)
    if params:
        options.update(params)

    window = int(context.get("window_days") or 15)
    history_map: dict[str, list[tuple[Any, float]]] = context.get("history") or {}
    site_map: dict[str, list[dict[str, Any]]] = context.get("sites") or {}
    margin_map: dict[str, float] = context.get("margins") or {}
    latest_sales: dict[str, float] = context.get("latest_sales") or {}
    clearance: set[str] = context.get("clearance") or set()
    ocean: set[str] = context.get("ocean") or set()
    store_cxb: dict[str, float] = context.get("store_cxb") or {}
    company_cxb = float(context.get("company_cxb") or 0.0)

    target_days = {
        "A": float(options["target_a"]),
        "B": float(options["target_b"]),
        "C": float(options["target_c"]),
    }
    sea_target_days = {
        "A": float(options["sea_target_a"]),
        "B": float(options["sea_target_b"]),
        "C": float(options["sea_target_c"]),
    }
    trigger_days = _trigger_days(target_days, float(options["trigger_offset"]))
    sea_trigger_days = _trigger_days(sea_target_days, float(options["trigger_offset"]))
    min_gap = float(options["min_gap"])
    ab_sufficient_groups = _ab_groups(rows, float(options["ab_sufficient_days"]))

    results: dict[str, dict[str, Any]] = {}

    for row in rows:
        values = row["values"]
        sku = str(values[_COL_SKU] or "").strip()
        if not sku:
            continue
        store = _normalized_store(values[_COL_STORE])
        category = _normalized_category(values[_COL_CATEGORY])
        is_sea_freight = sku in ocean
        remark = str(values[_COL_REMARK] or "")

        no_order_reasons: list[str] = []
        order_reasons: list[str] = []
        calc_process = ""

        if "【【【不用下单】】】" in remark:
            no_order_reasons.append("使用公共库存，不用下单 (规则6)")
        if sku in clearance:
            no_order_reasons.append("清货产品，Q列灰色标记 (规则7)")

        available_days = _num(values[_COL_DAYS_WITH_PENDING])
        k_value = _num(values[_COL_K])
        margin_value = float(margin_map.get(sku, 0) or 0)
        today_sales = float(latest_sales.get(sku, 0) or 0)
        daily_sales_raw = _num(values[_COL_DAILY])
        history = list(history_map.get(sku) or [])
        daily_sales, actual_days, selected_history = _window_average(history, window)

        if daily_sales is None:
            daily_sales = daily_sales_raw
        if actual_days > 0 and daily_sales is not None:
            order_reasons.append(f"销量口径:近{window}天(实际{actual_days}天)均值{daily_sales:.1f}")
        elif daily_sales is not None:
            order_reasons.append(f"销量口径:近{window}天无历史,使用表格原值{daily_sales:.1f}")

        if options.get("rule_a_enabled") and daily_sales is not None and daily_sales_raw is not None:
            daily_sales, trend_desc = _adaptive_sales(history, daily_sales, options, window)
            if "数据不足" not in trend_desc:
                order_reasons.append(f"规则A:{trend_desc}")

        # 规则 14：绝对低销拦截
        if daily_sales is not None and daily_sales < float(options["rule14_min_sales"]):
            if selected_history:
                zero_days = sum(1 for item in selected_history if item[1] == 0)
                top_3 = sorted(selected_history, key=lambda item: item[1], reverse=True)[:3]
                top_3_sorted = sorted(top_3, key=lambda item: (item[0] or date.min))
                details = []
                for item in top_3_sorted:
                    stamp = item[0].strftime("%Y-%m-%d") if isinstance(item[0], (date, datetime)) else str(item[0])[:10]
                    details.append(f"{stamp}({item[1]:.0f}件)")
                no_order_reasons.append(
                    f"规则14:日均销量过低({daily_sales:.2f}<{options['rule14_min_sales']})，"
                    f"历史{len(selected_history)}天中包含{zero_days}天是0交易，"
                    f"成交最高三天为：{'、'.join(details) if details else '无'}"
                )
            else:
                no_order_reasons.append(
                    f"规则14:日均销量过低({daily_sales:.2f}<{options['rule14_min_sales']}，无历史交易数据)"
                )

        global_transit = _num(values[_COL_PENDING]) or 0.0
        if available_days is None:
            no_order_reasons.append("可售天数缺失")
        if daily_sales is None:
            no_order_reasons.append("日均销量缺失")

        # 规则 5：同组 A 款本地+在途充足时 B 款不下单（只看 -2 款）
        ab_mark = str(values[_COL_AB] or "").strip()
        if ab_mark and ab_mark.lower() != "nan":
            for match in _AB_PATTERN.finditer(ab_mark):
                if match.group(2) != "2":
                    continue
                group_id = int(match.group(1))
                if group_id in ab_sufficient_groups:
                    no_order_reasons.append(
                        f"AB品关联(规则5):同组A产品(序号{group_id})的本地库存+在途已充足"
                        f"(>={options['ab_sufficient_days']}天)"
                    )

        final_order = 0
        main_gap: float | None = None
        if daily_sales is not None and available_days is not None:
            if daily_sales < float(options["rule11_min_sales"]):
                if margin_value > float(options["high_margin_threshold"]) and available_days < float(options["rule11_low_days"]):
                    final_order = 100
                    calc_process = "100"
                    order_reasons.append(
                        f"规则11: 销量({daily_sales:.1f})<{options['rule11_min_sales']},"
                        f"但毛利({margin_value:.1f}%)>{options['high_margin_threshold']} "
                        f"并且天数({available_days:.1f})<{options['rule11_low_days']} -> 破格下100"
                    )
                else:
                    no_order_reasons.append(f"日均销量({daily_sales:.1f}) < 5且非高毛利缺货特例 (规则11)")

        if category not in target_days:
            no_order_reasons.append(f"未定义补货规则的分类: '{values[_COL_CATEGORY]}'")

        main_target: float | None = None
        main_trigger: float | None = None
        freight_label = "海运" if is_sea_freight else "基础"
        if category in target_days:
            main_target = sea_target_days[category] if is_sea_freight else target_days[category]
            main_trigger = sea_trigger_days[category] if is_sea_freight else trigger_days[category]

        if final_order == 0 and not no_order_reasons:
            if available_days is not None and daily_sales is not None and main_trigger is not None and main_target is not None:
                if available_days >= main_trigger:
                    no_order_reasons.append(
                        f"综合可售天数充足 ({available_days:.1f} >= {category}类{freight_label}起补线{main_trigger:.1f})"
                    )
                else:
                    target = main_target
                    cxb_diff = float(store_cxb.get(store, 0) or 0) - company_cxb
                    if cxb_diff > float(options["cxb_diff_threshold"]):
                        target -= float(options["cxb_reduction"])
                        order_reasons.append(f"规则4(目标天数-{options['cxb_reduction']})")
                    shortage_days = target - available_days
                    raw_order = 100.0 if shortage_days <= 0 else shortage_days * daily_sales
                    final_order = _tier_round(raw_order)
                    order_reasons.append(
                        f"规则1:[{category}类{freight_label}天数{available_days:.1f}<起补线{main_trigger:.1f},目标{main_target}]"
                    )
                    order_reasons.append(f"规则2:计算{raw_order:.0f}->规范{final_order}")
                    calc_process = str(final_order)
                    main_gap = raw_order

        # 规则 8：分站点缺口
        rule8_added = 0
        blocked = [reason for reason in no_order_reasons if any(key in reason for key in ("规则11", "规则14", "缺失", "定义"))]
        if (
            category in target_days
            and available_days is not None
            and main_trigger is not None
            and available_days < main_trigger
            and not blocked
        ):
            sites = list(site_map.get(sku) or [])
            short_sites: list[dict[str, Any]] = []
            sales_factor = 1.0
            if daily_sales_raw is not None and daily_sales_raw > 0 and daily_sales is not None:
                sales_factor = daily_sales / daily_sales_raw
            for site in sites:
                site_days = site.get("fba_days")
                site_sales_raw = site.get("fba_sales")
                site_target = target_days[category]
                if is_sea_freight and str(site.get("country")) in {"美国", "US"}:
                    site_target = sea_target_days[category]
                site_sales = (site_sales_raw or 0.0) * sales_factor if site_sales_raw is not None else None
                if site_days is not None and site_sales is not None and site_days < site_target and site_sales > 0:
                    short_sites.append(
                        {
                            "country": site.get("country"),
                            "days": site_days,
                            "req_qty": (site_target - site_days) * site_sales,
                            "site_target": site_target,
                            "local_inv": float(site.get("local_inv") or 0.0),
                        }
                    )
            short_sites.sort(key=lambda item: item["req_qty"], reverse=True)
            shared_local = max((site["local_inv"] for site in sites), default=0.0) if sites else 0.0
            remaining_local = shared_local
            rule8_total = 0
            rule8_reasons: list[str] = []
            calc_parts: list[str] = []
            small_total = 0.0
            small_details: list[dict[str, Any]] = []

            for site in short_sites:
                req_orig = site["req_qty"]
                current = req_orig
                deducted_local = 0.0
                if remaining_local > 0:
                    deducted_local = min(remaining_local, current)
                    remaining_local -= deducted_local
                    current -= deducted_local
                deducted_transit = 0.0
                if global_transit > 0 and current > 0:
                    deducted_transit = min(global_transit, current)
                    global_transit -= deducted_transit
                    current -= deducted_transit
                if current <= 0:
                    continue
                if current >= min_gap:
                    site_final = _tier_round(current)
                    rule8_total += site_final
                    label = site["country"]
                    if is_sea_freight and str(site["country"]) in {"美国", "US"}:
                        label = f"{label}(海运特供-{category})"
                    reason = f"规则8:为[{label}]加单{site_final}(天数{site['days']:.0f}<目标{site['site_target']},原缺口{req_orig:.0f}"
                    if deducted_local > 0:
                        reason += f",抵扣本地{deducted_local:.0f}"
                    if deducted_transit > 0:
                        reason += f",抵扣在途{deducted_transit:.0f}"
                    reason += ")"
                    rule8_reasons.append(reason)
                    calc_parts.append(f"{site_final}({label})")
                else:
                    small_total += current
                    small_details.append({"country": site["country"], "net": current})

            if small_total >= min_gap:
                site_final = _tier_round(small_total)
                rule8_total += site_final
                countries = ",".join(str(item["country"]) for item in small_details)
                rule8_reasons.append(
                    f"规则8:为[{countries}]合计加单{site_final}(小站点合计缺口{small_total:.0f}>={min_gap:.0f})"
                )
                calc_parts.append(f"{site_final}({countries}合计)")
            elif small_total > 0:
                countries = ",".join(str(item["country"]) for item in small_details)
                no_order_reasons.append(f"规则8:[{countries}]合计缺口{small_total:.0f}不足起补缺口{min_gap:.0f}")

            rule8_added = rule8_total
            rule8_process = " + ".join(calc_parts)

        if rule8_added > 0:
            if final_order > 0:
                order_reasons = [
                    f"{reason}(辅助)" if any(key in reason for key in ("规则1:", "规则2:", "规则4", "规则11")) else reason
                    for reason in order_reasons
                ]
                order_reasons.extend(rule8_reasons)
                calc_process = rule8_process
                final_order = rule8_added
            else:
                order_reasons.extend(rule8_reasons)
                calc_process = rule8_process
                final_order += rule8_added
            no_order_reasons = [reason for reason in no_order_reasons if "综合可售天数充足" not in reason]

        # 规则 8 未起效时，主盘面基础缺口也必须达到最小起补缺口
        if rule8_added == 0 and main_gap is not None and main_gap < min_gap:
            final_order = 0
            no_order_reasons.append(f"规则2:主盘面基础缺口{main_gap:.0f}不足起补缺口{min_gap:.0f}")
            order_reasons = []
            calc_process = ""

        if final_order > 0:
            # 规则 10：K 值趋势修正（默认调整量 0）
            if k_value is not None and k_value != 0:
                divisor = float(options["rule10_k_divisor"])
                strength = int(abs(k_value) // divisor) if divisor > 0 else 0
                if strength > 0:
                    adjust = float(options["rule10_adjust"])
                    if k_value > 0:
                        final_order += adjust
                        order_reasons.append(f"规则10:上升趋势强度{strength}(预留+{adjust:g})")
                        if adjust:
                            calc_process += f" + {adjust:g}(规则10上升)"
                    else:
                        final_order = max(0, final_order - adjust)
                        order_reasons.append(f"规则10:下降趋势强度{strength}(预留-{adjust:g})")
                        if adjust:
                            calc_process += f" - {adjust:g}(规则10下降)"
                        if final_order == 0:
                            no_order_reasons.append("规则10:下降趋势导致基础数量被清空修正为0")

            # 规则 9：最新一天突然起量（默认调整量 0）
            multiplier = float(options["rule9_multiplier"])
            if final_order > 0 and daily_sales and daily_sales > 0 and today_sales >= daily_sales * multiplier:
                adjust = float(options["rule9_adjust"])
                final_order -= adjust
                threshold = float(options["rule9_threshold"])
                if daily_sales > threshold:
                    order_reasons.append(f"规则9(突然起量):日均>{threshold:g}(预留-{adjust:g})")
                else:
                    order_reasons.append(f"规则9(突然起量):日均<={threshold:g}(预留-{adjust:g})观察")
                if adjust:
                    calc_process += f" - {adjust:g}(规则9调整)"

        total = max(0, int(round(final_order)))
        if no_order_reasons:
            results[sku] = {
                "qty": 0,
                "calc_process": "",
                "order_reason": "",
                "no_order_reason": "\n".join(no_order_reasons),
                "daily_sales": daily_sales,
            }
        else:
            if total > 0:
                calc_process += f" = {total}"
            results[sku] = {
                "qty": total,
                "calc_process": calc_process if total > 0 else "",
                "order_reason": "\n".join(order_reasons) if total > 0 else "",
                "no_order_reason": "",
                "daily_sales": daily_sales,
            }
    return results


def _ab_groups(rows: list[dict[str, Any]], sufficient_days: float) -> set[int]:
    """规则 5：找出本地库存+待到货可覆盖足够天数的 A 款（序号-1）组。"""
    groups: set[int] = set()
    for row in rows:
        values = row["values"]
        mark = str(values[_COL_AB] or "").strip()
        if not mark or mark.lower() == "nan":
            continue
        total = _num(values[_COL_TOTAL]) or 0.0
        fba = _num(values[_COL_FBA]) or 0.0
        pending = _num(values[_COL_PENDING]) or 0.0
        daily = _num(values[_COL_DAILY]) or 0.0
        if daily <= 0:
            continue
        local = max(0.0, total - fba)
        if (local + pending) / daily < sufficient_days:
            continue
        for match in _AB_PATTERN.finditer(mark):
            if match.group(2) == "1":
                groups.add(int(match.group(1)))
    return groups


def attach_suggestions(
    settings: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    query_executor=base.sf_db,
    params: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """把建议下单量写进主表「订货量」，并重算「订货后可售天数」。"""
    context = build_context(settings, rows, query_executor=query_executor, params=params)
    results = suggest(rows, context, params=params)

    for row in rows:
        values = row["values"]
        sku = str(values[_COL_SKU] or "").strip()
        item = results.get(sku)
        if not item:
            continue
        quantity = max(0, int(item.get("qty") or 0))
        values[_COL_ORDER] = quantity
        stock_with_pending = (_num(values[_COL_TOTAL]) or 0.0) + (_num(values[_COL_PENDING]) or 0.0)
        values[_COL_DAYS_AFTER_ORDER] = base._available_days(
            stock_with_pending + quantity,
            _num(values[_COL_DAILY]),
        )
    return results


def order_comment(result: dict[str, Any]) -> str:
    """订货量单元格的悬浮说明：为什么是这么多 / 为什么是 0。"""
    quantity = int(result.get("qty") or 0)
    if quantity > 0:
        lines = [f"智能补货建议：{quantity} 件"]
        process = str(result.get("calc_process") or "").strip()
        if process:
            lines.append(f"计算过程：{process}")
        reason = str(result.get("order_reason") or "").strip()
        if reason:
            lines.append(reason)
        return "\n".join(lines)
    reason = str(result.get("no_order_reason") or "").strip()
    if not reason:
        return "智能补货建议：0 件"
    return f"智能补货建议：0 件（不下单原因）\n{reason}"
