"""Keep recent report reminder results and recipient lookups."""

from __future__ import annotations


def _xiaotu_remember_user_open_id(
    user_name,
    open_id,
    *,
    _xiaotu_user_open_id_cache,
    re,
):
    name = str(user_name or "").strip()
    oid = str(open_id or "").strip()
    if not name or not oid.startswith("ou_"):
        return
    _xiaotu_user_open_id_cache[name] = oid
    compact_name = re.sub(r"\s+", "", name)
    if compact_name:
        _xiaotu_user_open_id_cache[compact_name] = oid


def _xiaotu_get_cached_open_id_by_name(
    user_name,
    *,
    _xiaotu_user_open_id_cache,
    re,
):
    name = str(user_name or "").strip()
    if not name:
        return ""
    oid = str(_xiaotu_user_open_id_cache.get(name) or "").strip()
    if oid.startswith("ou_"):
        return oid
    compact_name = re.sub(r"\s+", "", name)
    oid = str(_xiaotu_user_open_id_cache.get(compact_name) or "").strip()
    return oid if oid.startswith("ou_") else ""


def _xiaotu_append_report_reminder_log(
    stage,
    kwargs,
    *,
    _safe_debug_print,
    _xiaotu_report_reminder_lock,
    _xiaotu_report_reminder_logs,
    _xiaotu_report_reminder_logs_limit,
    datetime,
    json,
):
    item = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "stage": str(stage or "").strip() or "unknown",
    }
    for key, value in (kwargs or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            item[key] = value
        else:
            try:
                item[key] = json.loads(json.dumps(value, ensure_ascii=False))
            except Exception:
                item[key] = str(value)
    with _xiaotu_report_reminder_lock:
        _xiaotu_report_reminder_logs.append(item)
        if len(_xiaotu_report_reminder_logs) > _xiaotu_report_reminder_logs_limit:
            del _xiaotu_report_reminder_logs[:len(_xiaotu_report_reminder_logs) - _xiaotu_report_reminder_logs_limit]
    try:
        _safe_debug_print(f"[xiaotu_report_reminder][{item['stage']}] {item}")
    except Exception:
        pass
