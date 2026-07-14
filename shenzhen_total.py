from datetime import datetime
from calendar import monthrange
from bjc import sf_db


def compute_shenzhen_expenses(base_month):
    base_month = (base_month or "").strip()
    if base_month:
        try:
            base_dt = datetime.strptime(base_month + "-01", "%Y-%m-%d")
        except Exception:
            today = datetime.today()
            base_dt = today.replace(day=1)
    else:
        today = datetime.today()
        base_dt = today.replace(day=1)
    months = []
    periods = []
    for i in range(6):
        y = base_dt.year + (base_dt.month - 1 + i) // 12
        m = (base_dt.month - 1 + i) % 12 + 1
        start = datetime(y, m, 1)
        last_day = monthrange(y, m)[1]
        end = datetime(y, m, last_day)
        months.append(f"{y:04d}-{m:02d}")
        periods.append((start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
    if not periods:
        return [], {}
    all_start = periods[0][0]
    all_end = periods[-1][1]
    categories = [
        "营运费",
        "办公费",
        "差旅费",
        "交通费",
        "培训费",
        "员工福利",
        "物业水电",
        "税金",
        "商标专利费",
        "房屋租金",
        "人力成本",
        "产品成本",
        "头程",
        "尾程",
        "广告费",
        "平台费",
        "推广费",
        "所得税",
    ]
    safe_cats = [c.replace("'", "''") for c in categories]
    cat_clause = ",".join([f"'{c}'" for c in safe_cats])
    sql = f"""
SELECT
    CONVERT(varchar(7), 日期, 120) AS ym,
    费用类别,
    SUM(贷方) AS amount
FROM 财务_费用明细
WHERE 日期 >= '{all_start}' AND 日期 <= '{all_end}'
  AND 费用类别 IN ({cat_clause})
GROUP BY CONVERT(varchar(7), 日期, 120), 费用类别
"""
    rows = sf_db(sql) or []
    month_index = {m: idx for idx, m in enumerate(months)}
    data = {c: [0.0] * len(months) for c in categories}
    for row in rows:
        if isinstance(row, dict):
            ym = str(row.get("ym") or row.get("YM") or "").strip()
            cat = str(row.get("费用类别") or row.get("FeiYongLeiBie") or "").strip()
            amt_raw = row.get("amount")
        else:
            if len(row) < 3:
                continue
            ym = str(row[0]).strip()
            cat = str(row[1]).strip()
            amt_raw = row[2]
        if not ym or not cat:
            continue
        if ym not in month_index:
            continue
        if cat not in data:
            continue
        try:
            amt = float(amt_raw or 0)
        except Exception:
            amt = 0.0
        idx = month_index[ym]
        data[cat][idx] = amt
    op_cats = [
        "营运费",
        "办公费",
        "差旅费",
        "交通费",
        "培训费",
        "员工福利",
        "物业水电",
        "税金",
        "商标专利费",
    ]
    op_vals = [0.0] * len(months)
    for i in range(len(months)):
        total = 0.0
        for c in op_cats:
            vals = data.get(c)
            if not vals:
                continue
            try:
                v = float(vals[i] or 0)
            except Exception:
                v = 0.0
            total += v
        op_vals[i] = total
    data["经营成本"] = op_vals
    var_cats = [
        "产品成本",
        "头程",
        "尾程",
        "广告费",
        "平台费",
        "推广费",
    ]
    var_vals = [0.0] * len(months)
    for i in range(len(months)):
        total = 0.0
        for c in var_cats:
            vals = data.get(c)
            if not vals:
                continue
            try:
                v = float(vals[i] or 0)
            except Exception:
                v = 0.0
            total += v
        var_vals[i] = total
    data["变动成本"] = var_vals
    fixed_cats = [
        "房屋租金",
        "人力成本",
    ]
    fixed_vals = [0.0] * len(months)
    for i in range(len(months)):
        total = 0.0
        for c in fixed_cats:
            vals = data.get(c)
            if not vals:
                continue
            try:
                v = float(vals[i] or 0)
            except Exception:
                v = 0.0
            total += v
        fixed_vals[i] = total
    data["固定成本"] = fixed_vals
    total_out = [0.0] * len(months)
    for i in range(len(months)):
        try:
            op_v = float(op_vals[i] or 0)
        except Exception:
            op_v = 0.0
        try:
            fixed_v = float(fixed_vals[i] or 0)
        except Exception:
            fixed_v = 0.0
        try:
            var_v = float(var_vals[i] or 0)
        except Exception:
            var_v = 0.0
        total_out[i] = op_v + fixed_v + var_v
    data["支出"] = total_out
    income_vals = data.get("收入") or [0.0] * len(months)
    gross_vals = [0.0] * len(months)
    pre_tax_vals = [0.0] * len(months)
    for i in range(len(months)):
        try:
            inc = float(income_vals[i] or 0)
        except Exception:
            inc = 0.0
        try:
            var_cost = float(var_vals[i] or 0)
        except Exception:
            var_cost = 0.0
        try:
            out_cost = float(total_out[i] or 0)
        except Exception:
            out_cost = 0.0
        gross_vals[i] = inc - var_cost
        pre_tax_vals[i] = inc - out_cost
    data["毛利"] = gross_vals
    data["除所得税前利润"] = pre_tax_vals
    tax_vals = data.get("所得税") or [0.0] * len(months)
    monthly_net = [0.0] * len(months)
    for i in range(len(months)):
        try:
            pre_tax = float(pre_tax_vals[i] or 0)
        except Exception:
            pre_tax = 0.0
        try:
            tax = float(tax_vals[i] or 0)
        except Exception:
            tax = 0.0
        monthly_net[i] = pre_tax - tax
    data["月度税后净利润"] = monthly_net
    year_sum = {}
    for i in range(len(months)):
        ym = months[i]
        year = ym[:4]
        try:
            v = float(monthly_net[i] or 0)
        except Exception:
            v = 0.0
        year_sum[year] = year_sum.get(year, 0.0) + v
    annual_net = [0.0] * len(months)
    for i in range(len(months)):
        year = months[i][:4]
        annual_net[i] = year_sum.get(year, 0.0)
    data["年度税后净利润"] = annual_net
    return months, data
