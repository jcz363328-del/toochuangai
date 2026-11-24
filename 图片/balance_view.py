"""Percentage-only account balance view."""
from __future__ import annotations

import math


def render_balance_management(api, load_snapshot):
    st = api.st
    title, refresh = st.columns([5, 1], vertical_alignment="bottom")
    with title:
        st.markdown("## 余额管理")
    with refresh:
        force = st.button("刷新余额", key="balance_management_refresh", use_container_width=True)

    try:
        snapshot = load_snapshot(force=force)
        value = snapshot.get("percent")
        percent = float(value) if value is not None else None
        if percent is not None and not math.isfinite(percent):
            percent = None
    except Exception:
        snapshot, percent = {}, None

    if percent is None:
        st.error("暂时无法获取余额，请稍后刷新")
        return

    if snapshot.get("error"):
        st.warning("部分用量暂未核对，当前显示已核对余额，请稍后刷新。")

    st.markdown("""<style>
    .st-key-balance_management_card {padding:24px!important;border-radius:18px!important;}
    .st-key-balance_management_card [data-testid="stMetricValue"] {font-size:3.4rem!important;}
    .st-key-balance_management_status [data-testid="stMetricValue"] {font-size:1.65rem!important;}
    .st-key-balance_management_card [data-baseweb="progress-bar"] > div,
    .st-key-balance_management_card [role="progressbar"] {height:18px!important;border-radius:999px!important;}
    </style>""", unsafe_allow_html=True)
    with st.container(key="balance_management_card", border=True):
        remaining, status = st.columns([3, 1], vertical_alignment="center")
        with remaining:
            st.metric("剩余额度", f"{percent:.3f}".rstrip("0").rstrip(".") + "%")
        with status, st.container(key="balance_management_status"):
            st.metric("额度状态", "偏低" if percent <= 10 else "留意" if percent <= 20 else "充足")
        st.progress(min(1.0, max(0.0, percent / 100)))
        updated_at = str(snapshot.get("updated_at") or "").strip()
        if updated_at:
            st.caption(f"上次更新：{updated_at}")
    st.caption("根据已核对的起始余额和已绑定密钥的新增用量统计；充值或使用其他密钥后，需要重新校准。")
    pending = max(0, int(snapshot.get("pending_calls") or 0))
    active = max(0, int(snapshot.get("active_calls") or 0))
    if pending:
        st.info(f"{pending} 次调用费用待核对，尚未确认的费用不会显示为零。")
    if active:
        st.caption(f"当前有 {active} 次调用正在处理，完成后核对费用。")
    st.markdown("### 每次调用")
    rows = []
    for call in snapshot.get("calls") or []:
        status = call.get("status")
        outcome = call.get("outcome")
        value = call.get("cost_percent")
        if status == "submitted":
            label, cost = "处理中", "待核对"
        elif status != "settled" or value is None:
            label, cost = "待核对", "待核对"
        else:
            label = ("失败·已退款" if call.get("refunded") else
                     "已核对" if outcome == "success" else
                     "失败·未扣费" if outcome == "failed" and float(value) == 0 else
                     "失败·费用已核对" if outcome == "failed" else "结果待确认·费用已核对")
            cost_value = float(value)
            cost = ("<0.000001%" if 0 < cost_value < 0.000001 else
                    f"{cost_value:.6f}".rstrip("0").rstrip(".") + "%")
        refund = float(call.get("refund_percent") or 0)
        returned = ("<0.000001%" if 0 < refund < 0.000001 else
                    f"{refund:.6f}".rstrip("0").rstrip(".") + "%" if refund > 0 else "—")
        task = str(call.get("task_id") or call.get("call_id") or "")
        channel = call.get("channel")
        rows.append({
            "时间": str(call.get("created_at") or ""),
            "模型": str(call.get("model") or ""),
            "分辨率": str(call.get("resolution") or ""),
            "任务": task[:12] + ("…" if len(task) > 12 else ""),
            "通道": f"通道 {channel}" if isinstance(channel, int) and 1 <= channel <= 5 else "—",
            "消耗比例": cost, "退回比例": returned, "状态": label,
        })
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.caption("暂无调用记录")
