"""Resolve report card links, owners and edit sessions."""

from __future__ import annotations


def _xiaotu_get_report_owner_open_id_resolved(
    wendangid,
    report_row,
    *,
    _xiaotu_get_report_owner_open_id,
    _xiaotu_get_report_row,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_remember_report_owner_open_id,
):
    wid = str(wendangid or "").strip()
    if not wid:
        return ""
    remembered = str(_xiaotu_get_report_owner_open_id(wid) or "").strip()
    if remembered.startswith("ou_"):
        return remembered
    row = report_row if isinstance(report_row, dict) else _xiaotu_get_report_row(wid)
    owner_name = str((row or {}).get("xingming") or "").strip()
    owner_open_id = str(_xiaotu_lookup_open_id_by_name(owner_name) or "").strip()
    if owner_open_id.startswith("ou_"):
        _xiaotu_remember_report_owner_open_id(wid, owner_open_id)
        return owner_open_id
    return ""


def _xiaotu_set_report_edit_ready_session(
    wendangid,
    notify_open_ids,
    notify_targets,
    *,
    _XIAOTU_REPORT_EDIT_READY_SESSION_KEY,
    datetime,
    session,
):
    wid = str(wendangid or "").strip()
    if not wid:
        return
    session[_XIAOTU_REPORT_EDIT_READY_SESSION_KEY] = {
        "wendangid": wid,
        "ts": int(datetime.now().timestamp()),
        "notify_open_ids": [str(x or "").strip() for x in (notify_open_ids or []) if str(x or "").strip()],
        "notify_targets": [
            {
                "open_id": str((one or {}).get("open_id") or "").strip(),
                "name": str((one or {}).get("name") or "").strip(),
            }
            for one in (notify_targets or [])
            if isinstance(one, dict) and str((one or {}).get("open_id") or "").strip()
        ],
    }
    session.modified = True


def _xiaotu_clear_report_edit_ready_session(
    wendangid,
    *,
    _XIAOTU_REPORT_EDIT_READY_SESSION_KEY,
    session,
):
    wid = str(wendangid or "").strip()
    current = session.get(_XIAOTU_REPORT_EDIT_READY_SESSION_KEY)
    if wid and isinstance(current, dict) and str(current.get("wendangid") or "").strip() != wid:
        return
    if _XIAOTU_REPORT_EDIT_READY_SESSION_KEY in session:
        session.pop(_XIAOTU_REPORT_EDIT_READY_SESSION_KEY, None)
        session.modified = True


def _xiaotu_get_report_edit_ready_session(
    wendangid,
    *,
    _XIAOTU_REPORT_EDIT_READY_SESSION_KEY,
    _XIAOTU_REPORT_EDIT_READY_TTL_SECONDS,
    _xiaotu_clear_report_edit_ready_session,
    datetime,
    session,
):
    wid = str(wendangid or "").strip()
    raw = session.get(_XIAOTU_REPORT_EDIT_READY_SESSION_KEY)
    if not isinstance(raw, dict):
        return {}
    stored_wid = str(raw.get("wendangid") or "").strip()
    ts = int(raw.get("ts") or 0)
    now_ts = int(datetime.now().timestamp())
    if (not stored_wid) or (ts <= 0) or (now_ts - ts > _XIAOTU_REPORT_EDIT_READY_TTL_SECONDS):
        _xiaotu_clear_report_edit_ready_session()
        return {}
    if wid and stored_wid != wid:
        return {}
    return raw


def _xiaotu_build_reply_target_options(
    feedback,
    owner_name,
    *,
    _xiaotu_enrich_feedback_data,
):
    fb = _xiaotu_enrich_feedback_data(feedback or {}, owner_name=owner_name)
    out = []
    for name in fb.get("reply_targets") or []:
        name = str(name or "").strip()
        if not name:
            continue
        out.append({
            "text": {
                "tag": "plain_text",
                "content": name
            },
            "value": name
        })
    return out


def _xiaotu_build_report_history_url(
    wendangid,
    *,
    _XIAOTU_REPORT_CENTER_PUBLIC_URL,
    quote,
    re,
    url_for,
    urlparse,
):
    wid = str(wendangid or "").strip()
    if not wid:
        return ""
    try:
        return url_for('dashboard_xiaotu_report_history', wendangid=wid, _external=True)
    except Exception:
        base_url = str(_XIAOTU_REPORT_CENTER_PUBLIC_URL or "").strip()
        if not base_url:
            return ""
        parsed = urlparse(base_url)
        if parsed.scheme and parsed.netloc:
            base_url = f"{parsed.scheme}://{parsed.netloc}/dashboard/xiaotu-report-history"
        else:
            base_url = base_url.split("?", 1)[0].rstrip("/")
            base_url = re.sub(r"/dashboard/xiaotu-report-center/?$", "/dashboard/xiaotu-report-history", base_url)
            if not base_url.endswith("/dashboard/xiaotu-report-history"):
                base_url = base_url.rstrip("/") + "/dashboard/xiaotu-report-history"
        return f"{base_url}?wendangid={quote(wid)}"


def _xiaotu_split_org_perf_from_pingjia(
    pingjia_text,
    *,
    re,
):
    text = str(pingjia_text or "").strip()
    if not text:
        return "", ""
    marker_match = re.search(r"(?:^|\n)\s*(?:组织绩效贡献|对组织绩效影响)\s*[:：]", text)
    if not marker_match:
        return text, ""
    start = marker_match.start()
    marker_start = marker_match.start()
    if text[marker_start:marker_start + 1] == "\n":
        marker_start += 1
    summary = text[:start].strip()
    org_impact = text[marker_start:].strip()
    org_impact = re.sub(r"^\s*组织绩效贡献\s*[:：]\s*", "", org_impact).strip()
    org_impact = re.sub(r"^\s*对组织绩效影响\s*[:：]\s*", "", org_impact).strip()
    return summary, org_impact


def _xiaotu_find_first_key(
    obj,
    target_keys,
    *,
    _xiaotu_find_first_key,
):
    keys = {str(k).strip().lower() for k in (target_keys or []) if str(k or "").strip()}
    if not keys:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k or "").strip().lower()
            if lk in keys:
                return v
            nested = _xiaotu_find_first_key(v, keys)
            if nested is not None:
                return nested
    elif isinstance(obj, list):
        for item in obj:
            nested = _xiaotu_find_first_key(item, keys)
            if nested is not None:
                return nested
    return None
