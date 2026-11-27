"""Initialize local workbench state and apply pending crop interactions."""

from __future__ import annotations


def consume_pending_outpaint_drag(
    *,
    OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX,
    OUTPAINT_DRAG_QUERY_KEY,
    OUTPAINT_DRAG_STEP_PX,
    OUTPAINT_FALLBACK_MAX_EXTENSION_PX,
    clear_query_param,
    json,
    st,
) -> bool:
    raw_payload = str(st.query_params.get(OUTPAINT_DRAG_QUERY_KEY, "")).strip()
    if not raw_payload:
        return False
    clear_query_param(OUTPAINT_DRAG_QUERY_KEY)
    try:
        payload = json.loads(raw_payload)
    except Exception:
        return False
    keys = dict(payload.get("keys") or {})
    limits = dict(payload.get("limits") or {})
    try:
        drag_step = max(1, int(payload.get("step") or OUTPAINT_DRAG_STEP_PX))
    except Exception:
        drag_step = OUTPAINT_DRAG_STEP_PX
    changed = False
    for direction in ("top", "bottom", "left", "right"):
        state_key = str(keys.get(direction) or "").strip()
        if not state_key.startswith(("outpaint_", "infinite_canvas_")):
            continue
        try:
            value = int(payload.get(direction) or 0)
        except Exception:
            value = 0
        try:
            direction_limit = int(limits.get(direction) or OUTPAINT_FALLBACK_MAX_EXTENSION_PX)
        except Exception:
            direction_limit = OUTPAINT_FALLBACK_MAX_EXTENSION_PX
        direction_limit = max(0, min(OUTPAINT_ABSOLUTE_MAX_EXTENSION_PX, direction_limit))
        if direction_limit > 0 and value >= direction_limit - max(drag_step / 2, 1):
            value = direction_limit
        else:
            value = max(0, min(direction_limit, int(round(value / drag_step) * drag_step)))
        st.session_state[state_key] = value
        changed = True
    mode_state_key = str(keys.get("mode") or "").strip()
    drag_mode = str(payload.get("mode") or "").strip().lower()
    if mode_state_key.startswith(("outpaint_", "infinite_canvas_")) and drag_mode in {
        "position",
        "resize",
    }:
        st.session_state[mode_state_key] = drag_mode
        changed = True
    return changed


def ensure_state(
    *,
    Any,
    XIAOHA_DEFAULT_FEATURE_KEY,
    get_requested_feature_key,
    st,
) -> None:
    if "feature_results" not in st.session_state:
        st.session_state.feature_results = {}
    if "selected_feature_key" not in st.session_state:
        st.session_state.selected_feature_key = (
            get_requested_feature_key() or XIAOHA_DEFAULT_FEATURE_KEY
        )
    if "side_menu_visible" not in st.session_state:
        st.session_state.side_menu_visible = True
    if "is_authenticated" not in st.session_state:
        st.session_state.is_authenticated = False
    if "auth_username" not in st.session_state:
        st.session_state.auth_username = ""
    if "history_panel_expanded" not in st.session_state:
        st.session_state.history_panel_expanded = {}
    if "history_records_cache" not in st.session_state:
        st.session_state.history_records_cache = {}
    if "history_visible_counts" not in st.session_state:
        st.session_state.history_visible_counts = {}
    if "local_history_records" not in st.session_state:
        st.session_state.local_history_records = {}
    if "background_jobs" not in st.session_state:
        st.session_state.background_jobs = {}
    if "a_plus_first_screen_hero_results" not in st.session_state:
        st.session_state.a_plus_first_screen_hero_results = {}
    if "background_job_queue" not in st.session_state:
        migrated_jobs: list[dict[str, Any]] = []
        for feature_key, job_info in dict(st.session_state.background_jobs).items():
            if not isinstance(job_info, dict):
                continue
            migrated_job = job_info
            migrated_job.setdefault("feature_key", str(feature_key or ""))
            migrated_jobs.append(migrated_job)
        st.session_state.background_job_queue = migrated_jobs
