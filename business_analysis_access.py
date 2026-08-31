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
    "运营一部": {"周雪"},
    "运营二部": {"王钰媛"},
    "运营三部": {"大张雯"},
    "运营六部": {"郭鑫"},
    "运营七部": {"侯瑞昕", "侯瑞欣"},
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


def resolve_business_analysis_scope(user_id, user_name, department_rows, leader_id_getter=None):
    uid = _text(user_id)
    normalized_user_name = normalize_person_name(user_name)
    selected = None
    for row in department_rows or []:
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
    if not uid:
        return None
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
    is_leader = normalized_user_name in leader_names
    if not is_leader and leader_id_getter and selected["departmentId"]:
        is_leader = _text(leader_id_getter(selected["departmentId"])) == uid

    return {
        "role": "department_leader" if is_leader else "member",
        "department": selected["department"],
        "departmentId": selected["departmentId"],
        "operator": None if is_leader else _text(user_name),
        "userName": _text(user_name),
        "canViewAmounts": bool(is_leader),
        "categoryRatioVisible": True,
    }


def force_business_analysis_query_params(query_items, scope):
    params = [
        (key, value)
        for key, value in (query_items or [])
        if key not in {"department", "operator"}
    ]
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
    if scope.get("role") == "ratio_viewer":
        return False
    operator = normalize_person_name(row.get("operator"))
    if scope.get("operator"):
        return operator == normalize_person_name(scope["operator"])
    department = normalize_department_name(row.get("department"))
    if department:
        return department == scope["department"]
    try:
        return int(row.get("store")) in allowed_store_ids
    except (TypeError, ValueError):
        return False


def _sanitize_category_segments(data, period):
    previous_period = ""
    try:
        year, month = [int(value) for value in period.split("-", 1)]
        previous_month = month - 1
        previous_year = year
        if previous_month == 0:
            previous_month = 12
            previous_year -= 1
        previous_period = f"{previous_year:04d}-{previous_month:02d}"
    except (TypeError, ValueError):
        pass
    current_days = _month_days(period)
    previous_days = _month_days(previous_period)

    category_root = data.get("categorySegments") or {}
    for category in category_root.get("categories") or []:
        company = category.get("company") or {}
        company_current = company.get("current") or {}
        company_previous = company.get("previous") or {}
        rows = [row for row in (category.get("departments") or []) if isinstance(row, dict)]
        current_total = sum(float(row.get("currentSales") or 0) for row in rows)
        previous_total = sum(float(row.get("previousSales") or 0) for row in rows)
        category["ratios"] = {
            "company": {
                "dailyMom": _daily_growth(
                    company_current.get("sales"),
                    company_previous.get("sales"),
                    current_days,
                    previous_days,
                ),
                "usDailyMom": _daily_growth(
                    company_current.get("usSales"),
                    company_previous.get("usSales"),
                    current_days,
                    previous_days,
                ),
                "currentUsShare": _ratio(company_current.get("usSales"), company_current.get("sales")),
                "previousUsShare": _ratio(company_previous.get("usSales"), company_previous.get("sales")),
            },
            "departments": [
                {
                    "department": normalize_department_name(row.get("department")),
                    "currentShare": _ratio(row.get("currentSales"), current_total),
                    "previousShare": _ratio(row.get("previousSales"), previous_total),
                    "dailyMom": _daily_growth(
                        row.get("currentSales"),
                        row.get("previousSales"),
                        current_days,
                        previous_days,
                    ),
                    "currentUsShare": _ratio(row.get("currentUsSales"), row.get("currentSales")),
                    "previousUsShare": _ratio(row.get("previousUsSales"), row.get("previousSales")),
                }
                for row in rows
            ],
        }
        for bucket in (company_current, company_previous):
            bucket["sales"] = 0
            bucket["usSales"] = 0
        for row in rows:
            for key in (
                "currentSales",
                "previousSales",
                "currentUsSales",
                "previousUsSales",
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


def prepare_business_analysis_payload(payload, scope, period):
    result = copy.deepcopy(payload if isinstance(payload, dict) else {})
    data = result.get("data")
    if not isinstance(data, dict):
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
    performance["departments"] = [] if scope.get("role") == "ratio_viewer" else [
        row for row in (performance.get("departments") or [])
        if isinstance(row, dict)
        and (row.get("isTotal") or normalize_department_name(row.get("name")) == scope["department"])
    ]

    for key in ("slowMoving", "shipping", "newProductOrders", "unshipped"):
        data[key] = [
            row for row in (data.get(key) or [])
            if _row_is_visible(row, scope, allowed_store_ids)
        ]
    data["magnetDaily"] = []
    data.pop("categorySegmentsByPeriod", None)
    _sanitize_category_segments(data, period)

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
