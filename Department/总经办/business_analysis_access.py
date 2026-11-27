import calendar
import copy
import re


BUSINESS_ANALYSIS_DEPARTMENTS = (
    "运营一部",
    "运营二部",
    "运营三部",
    "运营六部",
    "运营七部",
)

BUSINESS_ANALYSIS_DEPARTMENT_LEADERS = {
    "运营一部": {"周雪", "郭婷"},
    "运营二部": {"王钰媛"},
    "运营三部": {"大张雯"},
    "运营六部": {"郭鑫"},
    "运营七部": {"侯瑞昕", "侯瑞欣"},
}

BUSINESS_ANALYSIS_ROTATION_LEADERS = {
    "郭婷": "运营一部",
    "王淑雯": "运营二部",
    "柳琳": "运营三部",
    "刘星辰": "运营六部",
    "张彦微": "运营七部",
}

_DISPLAY_DEPARTMENTS = {
    "周雪": "运营一部",
    "王钰媛": "运营二部",
    "大张雯": "运营三部",
    "郭鑫": "运营六部",
    "侯瑞昕": "运营七部",
    "侯瑞欣": "运营七部",
    **{name: name for name in BUSINESS_ANALYSIS_DEPARTMENTS},
}


def _text(value):
    return str(value or "").strip()


def normalize_person_name(value):
    name = _text(value)
    name = re.sub(r"\s*[（(][^（）()]{1,40}[）)]\s*$", "", name).strip()
    return re.sub(r"\s+", "", name)


def normalize_department_name(value):
    name = _text(value)
    return _DISPLAY_DEPARTMENTS.get(name, name)


def _business_analysis_tier_rank(value):
    match = re.fullmatch(r"([铜银金钻])(\d+)", _text(value))
    if not match:
        return None
    level = int(match.group(2))
    if level <= 0:
        return None
    return {"铜": 0, "银": 3, "金": 7, "钻": 16}[match.group(1)] + level


def merge_business_analysis_store_tier_snapshot(data, snapshot, warning=None):
    """Merge the separately maintained tier snapshot into a dashboard snapshot."""
    result = copy.deepcopy(data if isinstance(data, dict) else {})
    raw_rows = snapshot.get("rows") if isinstance(snapshot, dict) else None
    if not isinstance(raw_rows, list):
        return result

    snapshot_date = _text(snapshot.get("effectiveDate"))
    rows = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        row = copy.deepcopy(raw)
        department = normalize_department_name(row.get("department") or row.get("leader"))
        if department:
            row["department"] = department
        if snapshot_date and not _text(row.get("effectiveDate")):
            row["effectiveDate"] = snapshot_date
        if row.get("tierRank") is None:
            row["tierRank"] = _business_analysis_tier_rank(row.get("tier"))
        rows.append(row)

    result["storeTiers"] = rows
    by_store = {}
    for row in rows:
        try:
            by_store[int(row.get("store"))] = row
        except (TypeError, ValueError):
            continue
    performance = result.get("performance")
    if isinstance(performance, dict):
        for store in performance.get("stores") or []:
            if not isinstance(store, dict):
                continue
            try:
                tier = by_store.get(int(store.get("store")))
            except (TypeError, ValueError):
                tier = None
            if tier:
                store["tier"] = tier.get("tier")
                store["tierRank"] = tier.get("tierRank")

    effective_date = max(
        (_text(row.get("effectiveDate")) for row in rows),
        default=snapshot_date,
    ) or snapshot_date
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    row_counts = meta.get("rowCounts") if isinstance(meta.get("rowCounts"), dict) else {}
    row_counts["storeTiers"] = len(rows)
    meta["rowCounts"] = row_counts
    meta["storeTier"] = {
        "effectiveDate": effective_date or None,
        "updatedAt": _text(snapshot.get("updatedAt"))
        or (f"{effective_date}T00:00:00+08:00" if effective_date else None),
        "source": "workbook-snapshot",
        "stale": True,
        "warning": warning,
    }
    result["meta"] = meta
    return result


def resolve_business_analysis_scope(
    user_id,
    user_name,
    department_rows,
    leader_id_getter=None,
    full_access=False,
):
    uid = _text(user_id)
    normalized_user_name = normalize_person_name(user_name)
    if not uid:
        return None
    if full_access:
        return {
            "role": "business_owner",
            "department": None,
            "departmentId": "",
            "operator": None,
            "userName": _text(user_name),
            "canViewAmounts": True,
            "categoryRatioVisible": True,
        }
    selected = None
    delegated_department = BUSINESS_ANALYSIS_ROTATION_LEADERS.get(normalized_user_name)
    if delegated_department:
        delegated_row = next((
            row for row in (department_rows or [])
            if isinstance(row, dict)
            and normalize_department_name(row.get("name")) == delegated_department
        ), {})
        selected = {
            "department": delegated_department,
            "departmentId": _text(
                delegated_row.get("department_id")
                or delegated_row.get("open_department_id")
            ),
        }
    for row in department_rows or []:
        if selected:
            break
        if not isinstance(row, dict):
            continue
        if _text(row.get("status")).lower() in {"invalid", "unmapped"}:
            continue
        department = normalize_department_name(row.get("name"))
        if department in BUSINESS_ANALYSIS_DEPARTMENTS:
            selected = {
                "department": department,
                "departmentId": _text(row.get("department_id") or row.get("open_department_id")),
            }
            break
    if not selected:
        return {
            "role": "ratio_viewer",
            "department": None,
            "departmentId": "",
            "operator": None,
            "userName": _text(user_name),
            "canViewAmounts": False,
            "categoryRatioVisible": True,
        }

    leader_names = {
        normalize_person_name(name)
        for name in BUSINESS_ANALYSIS_DEPARTMENT_LEADERS[selected["department"]]
    }
    is_leader = bool(delegated_department) or normalized_user_name in leader_names
    if not is_leader and leader_id_getter and selected["departmentId"]:
        is_leader = _text(leader_id_getter(selected["departmentId"])) == uid

    return {
        "role": "department_leader" if is_leader else "member",
        "department": selected["department"],
        "departmentId": selected["departmentId"],
        "operator": None if is_leader else _text(user_name),
        "userName": _text(user_name),
        # 普通成员的查询和返回行都会按本人运营姓名裁剪，因此可以查看
        # 自己负责店铺的具体金额；部门负责人仍查看本部门完整金额。
        "canViewAmounts": True,
        "categoryRatioVisible": True,
    }


def force_business_analysis_query_params(query_items, scope):
    params = [
        (key, value)
        for key, value in (query_items or [])
        if key not in {"department", "operator"}
    ]
    if scope.get("role") == "business_owner":
        return params
    params.append(("department", scope.get("department") or "__ratio_only__"))
    if scope.get("operator"):
        params.append(("operator", scope["operator"]))
    return params


def _ratio(value, base):
    try:
        numerator = float(value or 0)
        denominator = float(base or 0)
    except (TypeError, ValueError):
        return None
    return numerator / denominator if denominator else None


def _daily_growth(current, previous, current_days, previous_days):
    try:
        current_value = float(current or 0)
        previous_value = float(previous or 0)
    except (TypeError, ValueError):
        return None
    if not previous_value:
        return None
    return (current_value / current_days) / (previous_value / previous_days) - 1


def _month_days(period):
    try:
        year, month = [int(value) for value in _text(period).split("-", 1)]
        return calendar.monthrange(year, month)[1]
    except (TypeError, ValueError):
        return 30


def _row_is_visible(row, scope, allowed_store_ids):
    if not isinstance(row, dict):
        return False
    if scope.get("role") == "business_owner":
        return True
    if scope.get("role") == "ratio_viewer":
        return False
    operator = normalize_person_name(row.get("operator"))
    if scope.get("operator"):
        return operator == normalize_person_name(scope["operator"])
    department = normalize_department_name(row.get("department") or row.get("leader"))
    if department:
        return department == scope["department"]
    try:
        return int(row.get("store")) in allowed_store_ids
    except (TypeError, ValueError):
        return False


def _hydrate_category_year_ago(category_root, fallback_root):
    """Fill a legacy live payload's missing year-ago fields from the same-period snapshot."""
    if not isinstance(category_root, dict) or not isinstance(fallback_root, dict):
        return
    fallback_categories = {
        _text(category.get("key") or category.get("label")): category
        for category in (fallback_root.get("categories") or [])
        if isinstance(category, dict)
    }
    for category in category_root.get("categories") or []:
        if not isinstance(category, dict):
            continue
        fallback = fallback_categories.get(_text(category.get("key") or category.get("label")))
        if not isinstance(fallback, dict):
            continue
        company = category.get("company") if isinstance(category.get("company"), dict) else {}
        fallback_company = fallback.get("company") if isinstance(fallback.get("company"), dict) else {}
        if "yearAgo" not in company and isinstance(fallback_company.get("yearAgo"), dict):
            company["yearAgo"] = copy.deepcopy(fallback_company["yearAgo"])
            category["company"] = company

        fallback_rows = {
            normalize_department_name(row.get("department")): row
            for row in (fallback.get("departments") or [])
            if isinstance(row, dict)
        }
        for row in category.get("departments") or []:
            if not isinstance(row, dict):
                continue
            fallback_row = fallback_rows.get(normalize_department_name(row.get("department")))
            if not fallback_row:
                continue
            for key in ("yearAgoSales", "yearAgoUsSales"):
                if key not in row and key in fallback_row:
                    row[key] = copy.deepcopy(fallback_row[key])


def _sanitize_category_segments(data, period, scope, redact_amounts=True):
    # 品类模块包含公司及跨部门汇总，普通成员即使可查看本人店铺金额，
    # 也不能由此获得公司或其他部门的绝对金额。
    can_view_category_amounts = bool(scope.get("canViewAmounts")) and scope.get("role") != "member"
    previous_period = ""
    year_ago_period = ""
    try:
        year, month = [int(value) for value in period.split("-", 1)]
        previous_month = month - 1
        previous_year = year
        if previous_month == 0:
            previous_month = 12
            previous_year -= 1
        previous_period = f"{previous_year:04d}-{previous_month:02d}"
        year_ago_period = f"{year - 1:04d}-{month:02d}"
    except (TypeError, ValueError):
        pass
    current_days = _month_days(period)
    previous_days = _month_days(previous_period)
    year_ago_days = _month_days(year_ago_period)

    category_root = data.get("categorySegments") or {}

    for category in category_root.get("categories") or []:
        rows = [row for row in (category.get("departments") or []) if isinstance(row, dict)]
        company = category.get("company") or {}
        company_current = company.get("current") or {}
        company_previous = company.get("previous") or {}
        company_year_ago = company.get("yearAgo") or {}
        current_total = sum(float(row.get("currentSales") or 0) for row in rows)
        previous_total = sum(float(row.get("previousSales") or 0) for row in rows)
        year_ago_total = sum(float(row.get("yearAgoSales") or 0) for row in rows)
        category["ratios"] = {
            "company": {
                "currentSales": float(company_current.get("sales") or 0) if can_view_category_amounts else None,
                "previousSales": float(company_previous.get("sales") or 0) if can_view_category_amounts else None,
                "yearAgoSales": float(company_year_ago.get("sales") or 0) if can_view_category_amounts else None,
                "currentDailySales": _ratio(company_current.get("sales"), current_days) if can_view_category_amounts else None,
                "previousDailySales": _ratio(company_previous.get("sales"), previous_days) if can_view_category_amounts else None,
                "yearAgoDailySales": _ratio(company_year_ago.get("sales"), year_ago_days) if can_view_category_amounts else None,
                "dailyMom": _daily_growth(
                    company_current.get("sales"),
                    company_previous.get("sales"),
                    current_days,
                    previous_days,
                ),
                "dailyYoy": _daily_growth(
                    company_current.get("sales"),
                    company_year_ago.get("sales"),
                    current_days,
                    year_ago_days,
                ),
                "usDailyMom": _daily_growth(
                    company_current.get("usSales"),
                    company_previous.get("usSales"),
                    current_days,
                    previous_days,
                ),
                "usDailyYoy": _daily_growth(
                    company_current.get("usSales"),
                    company_year_ago.get("usSales"),
                    current_days,
                    year_ago_days,
                ),
                "currentUsShare": _ratio(company_current.get("usSales"), company_current.get("sales")),
                "previousUsShare": _ratio(company_previous.get("usSales"), company_previous.get("sales")),
                "yearAgoUsShare": _ratio(company_year_ago.get("usSales"), company_year_ago.get("sales")),
            },
            "departments": [
                {
                    "department": normalize_department_name(row.get("department")),
                    "currentSales": (
                        float(row.get("currentSales") or 0)
                        if can_view_category_amounts and (
                            scope.get("role") == "business_owner"
                            or normalize_department_name(row.get("department")) == normalize_department_name(scope.get("department"))
                        )
                        else None
                    ),
                    "currentDailySales": (
                        _ratio(row.get("currentSales"), current_days)
                        if can_view_category_amounts and (
                            scope.get("role") == "business_owner"
                            or normalize_department_name(row.get("department")) == normalize_department_name(scope.get("department"))
                        )
                        else None
                    ),
                    "currentShare": _ratio(row.get("currentSales"), current_total),
                    "previousShare": _ratio(row.get("previousSales"), previous_total),
                    "yearAgoShare": _ratio(row.get("yearAgoSales"), year_ago_total),
                    "dailyMom": _daily_growth(
                        row.get("currentSales"),
                        row.get("previousSales"),
                        current_days,
                        previous_days,
                    ),
                    "dailyYoy": _daily_growth(
                        row.get("currentSales"),
                        row.get("yearAgoSales"),
                        current_days,
                        year_ago_days,
                    ),
                    "currentUsShare": _ratio(row.get("currentUsSales"), row.get("currentSales")),
                    "previousUsShare": _ratio(row.get("previousUsSales"), row.get("previousSales")),
                    "yearAgoUsShare": _ratio(row.get("yearAgoUsSales"), row.get("yearAgoSales")),
                }
                for row in rows
            ],
        }
        if not redact_amounts:
            continue
        for bucket in (company_current, company_previous, company_year_ago):
            bucket["sales"] = 0
            bucket["usSales"] = 0
        for row in rows:
            for key in (
                "currentSales",
                "previousSales",
                "yearAgoSales",
                "currentUsSales",
                "previousUsSales",
                "yearAgoUsSales",
            ):
                row[key] = 0
        for bucket in (category.get("industry") or {}).values():
            if isinstance(bucket, dict):
                bucket["sales"] = 0
                bucket["dailySales"] = None
        for row in category.get("shareDaily") or []:
            if isinstance(row, dict):
                row["marketSales"] = 0
                row["companySales"] = 0


def prepare_business_analysis_payload(payload, scope, period, category_fallback=None):
    result = copy.deepcopy(payload if isinstance(payload, dict) else {})
    data = result.get("data")
    if not isinstance(data, dict):
        return result

    category_history = data.pop("categorySegmentsByPeriod", None)
    if isinstance(category_history, dict) and isinstance(category_history.get(period), dict):
        data["categorySegments"] = copy.deepcopy(category_history[period])
    _hydrate_category_year_ago(data.get("categorySegments"), category_fallback)

    if scope.get("role") == "business_owner":
        _sanitize_category_segments(data, period, scope, redact_amounts=False)
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        meta["accessScope"] = {
            "role": scope["role"],
            "department": None,
            "operator": None,
            "userName": scope.get("userName"),
            "canViewAmounts": True,
            "categoryRatioVisible": True,
        }
        data["meta"] = meta
        return result

    performance = data.get("performance") if isinstance(data.get("performance"), dict) else {}
    stores = [
        row for row in (performance.get("stores") or [])
        if _row_is_visible(row, scope, set())
    ]
    period_rows = [
        row for row in (performance.get("periodRows") or [])
        if _row_is_visible(row, scope, set())
    ]
    allowed_store_ids = {
        int(row.get("store"))
        for row in stores + period_rows
        if isinstance(row, dict) and str(row.get("store") or "").isdigit()
    }
    performance["stores"] = stores
    performance["periodRows"] = period_rows
    performance["departments"] = [
        row for row in (performance.get("departments") or [])
        if isinstance(row, dict)
        and scope.get("role") == "department_leader"
        and not row.get("isTotal")
        and normalize_department_name(row.get("name")) == scope["department"]
    ]

    for key in ("slowMoving", "shipping", "newProductOrders", "unshipped"):
        data[key] = [
            row for row in (data.get(key) or [])
            if _row_is_visible(row, scope, allowed_store_ids)
        ]
    data["storeTiers"] = [
        row for row in (data.get("storeTiers") or [])
        if _row_is_visible(row, scope, allowed_store_ids)
    ]
    data["magnetDaily"] = []
    _sanitize_category_segments(data, period, scope)

    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    for key in ("sourceTotals", "curatedTotals", "reconciliation", "auditNotes"):
        meta.pop(key, None)
    meta["accessScope"] = {
        "role": scope["role"],
        "department": scope["department"],
        "operator": scope.get("operator"),
        "userName": scope.get("userName"),
        "canViewAmounts": bool(scope.get("canViewAmounts")),
        "categoryRatioVisible": True,
    }
    data["meta"] = meta

    if not scope.get("canViewAmounts"):
        for formula in result.get("formulas") or []:
            if not isinstance(formula, dict):
                continue
            if formula.get("unit") == "CNY":
                formula["value"] = None
            for item in formula.get("inputs") or []:
                if isinstance(item, dict) and not str(item.get("key") or "").startswith("days"):
                    item["value"] = None
    return result
