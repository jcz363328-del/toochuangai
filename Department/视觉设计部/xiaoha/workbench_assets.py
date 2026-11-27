"""Inject styles and browser interactions for the Xiaoha workbench."""

from __future__ import annotations


def inject_processing_transition(
    *,
    APP_DIR,
    build_running_job_spinner_html,
    components,
    json,
) -> None:
    script = (APP_DIR / "processing_transition.js").read_text(encoding="utf-8-sig")
    script = script.replace("__XIAOHA_LOADING_HTML__", json.dumps(build_running_job_spinner_html(0, "正在提交处理，请稍候")))
    components.html(
        '<script>const s=window.parent.document.createElement("script");s.textContent='
        + json.dumps(script).replace("</", r"<\/")
        + ';window.parent.document.head.appendChild(s);s.remove();</script>', height=0,
    )


def inject_app_styles(
    *,
    inject_processing_transition,
    st,
) -> None:
    from Department.视觉设计部.xiaoha.action_dock import inject_action_dock_styles
    inject_action_dock_styles(st)
    inject_processing_transition()
    st.markdown(
        """
        <style>
        .xiaoha-task-spinner-card {
            display: flex;
            align-items: center;
            gap: 14px;
            width: 100%;
            box-sizing: border-box;
            padding: 14px 16px;
            margin: 4px 0 10px;
            border: 1px solid rgba(126, 96, 255, 0.22);
            border-radius: 14px;
            background: linear-gradient(135deg, rgba(126, 96, 255, 0.10), rgba(18, 31, 55, 0.44));
        }
        .xiaoha-task-spinner-circle {
            position: relative;
            width: 48px;
            height: 48px;
            flex: 0 0 48px;
            display: grid;
            place-items: center;
        }
        .xiaoha-task-spinner-orbit {
            position: absolute;
            inset: 0;
            box-sizing: border-box;
            border: 4px solid rgba(126, 96, 255, 0.18);
            border-top-color: #8d78ff;
            border-right-color: #39d7c5;
            border-radius: 50%;
            animation: xiaoha-task-spinner-rotate 0.9s linear infinite;
        }
        .xiaoha-task-spinner-value {
            color: #f5f7ff;
            font-size: 11px;
            font-weight: 800;
        }
        .xiaoha-task-spinner-stage {
            color: #f5f7ff;
            font-size: 14px;
            line-height: 1.45;
            font-weight: 750;
        }
        .xiaoha-task-spinner-subtitle {
            margin-top: 3px;
            color: rgba(214, 219, 255, 0.68);
            font-size: 12px;
        }
        .xiaoha-queue-overview {
            margin: 8px 0 12px;
            padding: 12px 14px;
            border: 1px solid rgba(126, 96, 255, 0.18);
            border-radius: 12px;
            background: rgba(7, 19, 41, 0.52);
        }
        .xiaoha-queue-title {
            margin-bottom: 7px;
            color: rgba(245, 247, 255, 0.72);
            font-size: 12px;
            font-weight: 750;
        }
        .xiaoha-queue-row {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 6px 8px;
            color: rgba(225, 230, 255, 0.76);
            font-size: 12px;
            border-radius: 8px;
        }
        .xiaoha-queue-row.current { background: rgba(126, 96, 255, 0.12); }
        .xiaoha-queue-row strong { color: #a99bff; font-weight: 750; }
        @keyframes xiaoha-task-spinner-rotate { to { transform: rotate(360deg); } }
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            background:
                radial-gradient(circle at top right, rgba(88, 64, 255, 0.20), transparent 28%),
                radial-gradient(circle at bottom right, rgba(88, 64, 255, 0.14), transparent 18%),
                linear-gradient(90deg, #030816 0%, #071329 45%, #08152d 100%);
            color: #f5f7ff;
        }
        [data-testid="stHeader"], .stAppHeader {
            background: transparent;
            pointer-events: none;
        }
        [data-testid="stHeader"] button {
            pointer-events: auto;
        }
        [data-testid="stToolbar"]:not(:has([data-testid="stExpandSidebarButton"])),
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu,
        button[title="View fullscreen"],
        button[title="Deploy"],
        div:has(> button[title="Deploy"]) {
            display: none !important;
            visibility: hidden !important;
        }
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"] {
            display: flex !important;
            visibility: visible !important;
            color: #e1e5f5;
        }
        [data-testid="stSidebarCollapseButton"] {
            visibility: visible !important;
        }
        [data-testid="stSidebarCollapseButton"] button {
            color: #f5f7ff !important;
        }
        /* Streamlit 1.67 mounts the sidebar opener inside the app toolbar. */
        [data-testid="stToolbar"]:has([data-testid="stExpandSidebarButton"]) {
            display: flex !important;
            visibility: visible !important;
            pointer-events: none;
        }
        [data-testid="stExpandSidebarButton"] {
            position: fixed;
            top: 12px;
            left: 16px;
            z-index: 1000000;
            display: flex !important;
            align-items: center;
            justify-content: center;
            visibility: visible !important;
            pointer-events: auto;
            width: 40px;
            min-width: 40px;
            height: 40px;
            min-height: 40px;
            padding: 10px;
            color: #aeb9d1 !important;
            background: transparent !important;
            border: none !important;
            border-radius: 10px;
            box-shadow: none !important;
            transition: background 0.15s ease;
        }
        [data-testid="stExpandSidebarButton"] > * {
            display: none !important;
        }
        [data-testid="stExpandSidebarButton"]::before {
            content: "";
            width: 20px;
            height: 20px;
            background: currentColor;
            mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cg fill='none' stroke='black' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='4' width='18' height='16' rx='3'/%3E%3Cpath d='M9 4v16m4-11 3 3-3 3'/%3E%3C/g%3E%3C/svg%3E") center / contain no-repeat;
        }
        [data-testid="stExpandSidebarButton"]:hover {
            background: rgba(169, 155, 255, 0.10) !important;
            color: #f5f7ff !important;
        }
        [data-testid="stExpandSidebarButton"]:focus-visible {
            outline: 2px solid #8c75ff;
            outline-offset: 2px;
        }
        [data-testid="stExpandSidebarButton"]::after {
            content: "展开侧栏";
            position: absolute;
            top: 46px;
            left: 0;
            white-space: nowrap;
            padding: 6px 9px;
            border-radius: 6px;
            background: #20283c;
            color: #e1e5f5;
            font-size: 12px;
            font-weight: 400;
            opacity: 0;
            pointer-events: none;
        }
        [data-testid="stExpandSidebarButton"]:hover::after,
        [data-testid="stExpandSidebarButton"]:focus-visible::after {
            opacity: 1;
        }
        [data-testid="stAppViewContainer"] {
            padding-top: 0 !important;
        }
        [data-testid="stAppViewContainer"] > .main {
            padding-top: 0 !important;
            margin-top: 0 !important;
        }
        .main .block-container,
        [data-testid="stMainBlockContainer"] {
            box-sizing: border-box;
            width: 100% !important;
            max-width: none !important;
            padding-top: 0.72rem !important;
            margin: 0 !important;
            padding-left: 1rem;
            padding-right: 1rem;
            padding-bottom: 1.35rem;
        }
        [data-testid="stMainBlockContainer"] {
            padding-top: 0 !important;
            margin-top: 0 !important;
        }
        /* Let the workspace shrink inside both standalone and embedded views. */
        :is(div[data-testid="column"], div[data-testid="stColumn"]) {
            min-width: 0;
        }
        div[data-testid="stHorizontalBlock"]:has(> :is(div[data-testid="column"], div[data-testid="stColumn"]) .side-menu-shell) {
            flex-wrap: nowrap;
            align-items: flex-start;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) {
            flex: 0 0 176px !important;
            width: 176px !important;
            min-width: 0 !important;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell)
            + :is(div[data-testid="column"], div[data-testid="stColumn"]) {
            flex: 1 1 0 !important;
            width: 0 !important;
            min-width: 0 !important;
        }
        [data-testid="stSidebar"] {
            background: #080f23;
            border-right: 1px solid rgba(169, 155, 255, 0.18);
        }
        [data-testid="stSidebarContent"] {
            padding: 0 14px 16px;
        }
        [data-testid="stSidebarHeader"] {
            position: absolute;
            top: 12px;
            right: 12px;
            height: 32px;
            min-height: 0;
            padding: 0;
            z-index: 20;
        }
        [data-testid="stSidebarUserContent"] {
            padding-top: 0;
        }
        .st-key-xiaoha_sidebar_brand {
            position: sticky;
            top: 0;
            z-index: 10;
            background: #080f23;
            padding: 18px 8px 16px;
            border-bottom: 1px solid rgba(169, 155, 255, 0.14);
            margin-bottom: 8px;
        }
        .xiaoha-sidebar-brand strong {
            display: block;
            font-size: 22px;
            line-height: 30px;
            color: #f5f7ff;
        }
        .xiaoha-sidebar-brand span {
            display: block;
            margin-top: 4px;
            font-size: 11px;
            color: #929bb5;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            border: none;
            border-radius: 8px;
            background: transparent;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary {
            min-height: 44px;
            padding: 10px 8px;
            color: #c4cce0;
            font-weight: 600;
        }
        [data-testid="stSidebar"] [data-testid="stExpanderDetails"] {
            padding: 2px 0 6px 10px;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button {
            min-height: 36px;
            padding: 7px 12px;
            justify-content: flex-start;
            border: none;
            border-radius: 7px;
            background: transparent;
            box-shadow: none;
            color: #aeb8d0;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button:hover {
            background: #151e35;
            color: #f5f7ff;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button[kind="primary"] {
            background: rgba(117, 91, 255, 0.20);
            color: #d9d1ff;
            box-shadow: inset 3px 0 #8c75ff;
        }
        [data-testid="stSidebar"] .stButton {
            margin-bottom: 0;
        }
        [data-testid="stSidebar"] .stButton > button {
            width: 100%;
            min-height: 46px;
            justify-content: center;
            align-items: center;
            padding: 0.38rem 0.65rem;
            border-radius: 0;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-bottom: none;
            background: rgba(6, 14, 30, 0.72);
            box-shadow: none;
            transition: all 0.18s ease;
        }
        [data-testid="stSidebar"] .stButton:first-of-type > button {
            border-top-left-radius: 14px;
            border-top-right-radius: 14px;
        }
        [data-testid="stSidebar"] .stButton:last-of-type > button {
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            border-bottom-left-radius: 14px;
            border-bottom-right-radius: 14px;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background: rgba(21, 32, 58, 0.9);
            border-color: rgba(146, 166, 255, 0.18);
            transform: none;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, rgba(118, 87, 255, 0.96), rgba(85, 62, 230, 0.94));
            border-color: rgba(169, 149, 255, 0.58);
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
        }
        [data-testid="stSidebar"] .stButton > button p {
            white-space: pre-line;
            text-align: center;
            font-size: 1rem;
            line-height: 1.2;
            font-weight: 700;
            color: rgba(255, 255, 255, 0.92);
            margin: 0;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] p {
            color: #ffffff;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, rgba(118, 87, 255, 0.96), rgba(85, 62, 230, 0.94));
            border-color: rgba(169, 149, 255, 0.58);
        }
        .brand-wrap {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            margin-bottom: 0.45rem;
        }
        .sidebar-card {
            display: block;
            text-decoration: none;
            padding: 0.9rem 1rem 0.82rem;
            margin-bottom: 0.85rem;
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            background: rgba(8, 15, 31, 0.88);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.22);
            transition: all 0.18s ease;
        }
        .sidebar-card:hover {
            border-color: rgba(144, 122, 255, 0.42);
            transform: translateY(-1px);
        }
        .sidebar-card.active {
            background: linear-gradient(135deg, rgba(106, 76, 255, 0.95), rgba(92, 65, 239, 0.92));
            border-color: rgba(144, 122, 255, 0.7);
            box-shadow: 0 14px 34px rgba(93, 68, 246, 0.28);
        }
        .sidebar-card-title {
            color: #ffffff;
            font-size: 1.02rem;
            font-weight: 700;
            line-height: 1.35;
            margin-bottom: 0.28rem;
        }
        .sidebar-card-sub {
            color: rgba(222, 226, 255, 0.78);
            font-size: 0.79rem;
            line-height: 1.45;
        }
        .brand-logo {
            width: 28px;
            height: 28px;
            border-radius: 7px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 0.85rem;
            color: #ffffff;
            background: linear-gradient(135deg, #8c7bff, #5f4bff);
            box-shadow: 0 10px 24px rgba(95, 75, 255, 0.35);
        }
        .brand-title {
            color: #ffffff;
            font-size: 1.06rem;
            font-weight: 700;
            margin: 0;
            line-height: 1.15;
        }
        .brand-subtitle {
            color: rgba(214, 219, 255, 0.72);
            font-size: 0.66rem;
            margin-top: 0.08rem;
        }
        .side-menu-shell {
            background:
                radial-gradient(circle at top right, rgba(88, 64, 255, 0.10), transparent 28%),
                linear-gradient(135deg, rgba(9, 17, 35, 0.88), rgba(7, 15, 31, 0.88));
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
            box-shadow: 0 16px 34px rgba(0, 0, 0, 0.20);
            padding: 0.46rem 0.44rem 0.42rem;
            margin-bottom: 0.24rem;
        }
        .side-menu-note {
            color: rgba(214, 219, 255, 0.7);
            font-size: 0.64rem;
            margin: 0.1rem 0 0;
        }
        div[data-testid="stElementContainer"]:has(.collapsed-side-menu-marker) {
            display: block !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
        }
        div[data-testid="stElementContainer"]:has(.collapsed-side-menu-marker)
        + div[data-testid="stElementContainer"] {
            position: fixed !important;
            left: 5px !important;
            top: 66px !important;
            width: 34px !important;
            z-index: 9999 !important;
            margin: 0 !important;
        }
        div[data-testid="stElementContainer"]:has(.collapsed-side-menu-marker)
        + div[data-testid="stElementContainer"] .stButton > button {
            width: 34px !important;
            min-width: 34px !important;
            min-height: 38px !important;
            padding: 0 !important;
            border-radius: 0 10px 10px 0 !important;
            border-color: rgba(138, 117, 255, 0.42) !important;
            background: rgba(10, 19, 39, 0.96) !important;
            box-shadow: 0 8px 22px rgba(0, 0, 0, 0.3) !important;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) .stButton > button {
            min-height: 31px !important;
            padding: 0.12rem 0.36rem !important;
            border-radius: 10px !important;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) .stButton > button p {
            font-size: 0.72rem !important;
            line-height: 1.08 !important;
            font-weight: 700 !important;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpander"] {
            margin-top: 0.38rem;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 11px;
            background: rgba(6, 14, 30, 0.56);
            overflow: hidden;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpander"] details {
            border: 0 !important;
            border-radius: inherit;
            background: transparent;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpander"] details > summary {
            min-height: 34px;
            padding: 0.28rem 0.5rem;
            color: rgba(229, 233, 255, 0.92) !important;
            font-size: 0.72rem;
            font-weight: 750;
            background: rgba(12, 22, 43, 0.96) !important;
            border: 0 !important;
            box-shadow: none !important;
            outline: none !important;
            -webkit-tap-highlight-color: transparent !important;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpander"] details > summary:hover,
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpander"] details > summary:focus,
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpander"] details > summary:focus-visible,
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpander"] details > summary:active {
            color: #ffffff !important;
            background: rgba(24, 33, 58, 0.98) !important;
            border: 0 !important;
            box-shadow: none !important;
            outline: none !important;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpander"] details[open] > summary {
            color: #ffffff !important;
            background: rgba(28, 35, 57, 0.98) !important;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpander"] summary:focus-visible {
            outline: 2px solid #9b85ff !important;
            outline-offset: -2px;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpanderDetails"] {
            border-color: rgba(255, 255, 255, 0.08) !important;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpander"] details > summary * {
            color: inherit !important;
            fill: currentColor !important;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) [data-testid="stExpander"] details > div {
            padding: 0.12rem 0.3rem 0.35rem;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell) .side-history-shell {
            margin-top: 0.45rem;
            padding-top: 0.45rem;
        }
        .side-history-shell {
            margin-top: 0.7rem;
            padding-top: 0.65rem;
            border-top: 1px solid rgba(255, 255, 255, 0.07);
        }
        .side-history-title {
            color: #f5f7ff;
            font-size: 0.9rem;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }
        .side-history-caption {
            color: rgba(214, 219, 255, 0.66);
            font-size: 0.7rem;
            margin: 0.2rem 0 0.32rem;
        }
        .history-card-time {
            color: #f5f7ff;
            font-size: 0.78rem;
            font-weight: 700;
            line-height: 1.25;
            margin-bottom: 0.12rem;
        }
        .history-card-model {
            color: rgba(214, 219, 255, 0.72);
            font-size: 0.68rem;
            line-height: 1.28;
            margin-bottom: 0.12rem;
            word-break: break-word;
        }
        .history-card-meta {
            min-height: 54px;
            margin-bottom: 0.34rem;
        }
        .workspace-panel {
            background:
                radial-gradient(circle at top right, rgba(88, 64, 255, 0.12), transparent 26%),
                linear-gradient(135deg, rgba(9, 17, 35, 0.92), rgba(7, 15, 31, 0.92));
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
            box-shadow: 0 18px 44px rgba(0, 0, 0, 0.24);
            padding: 0.86rem 0.94rem 0.92rem;
            margin-top: 0;
        }
        .workspace-panel:empty {
            display: none;
        }
        .login-shell {
            min-height: calc(100vh - 2rem);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-card {
            width: min(430px, 100%);
            background:
                radial-gradient(circle at top right, rgba(88, 64, 255, 0.16), transparent 30%),
                linear-gradient(135deg, rgba(9, 17, 35, 0.96), rgba(7, 15, 31, 0.96));
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 22px;
            box-shadow: 0 28px 70px rgba(0, 0, 0, 0.34);
            padding: 1.5rem 1.35rem 1.2rem;
        }
        .login-brand {
            color: #ffffff;
            font-size: 1.8rem;
            font-weight: 800;
            margin-bottom: 0.3rem;
            text-align: center;
        }
        .login-subtitle {
            color: rgba(214, 219, 255, 0.76);
            font-size: 0.95rem;
            text-align: center;
            margin-bottom: 1.2rem;
        }
        .login-tips {
            color: rgba(214, 219, 255, 0.7);
            font-size: 0.82rem;
            text-align: center;
            margin-top: 0.7rem;
        }
        .feature-head-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 0.55rem;
        }
        /* Streamlit marks the previous render tree as stale during every widget
           rerun. Keep it fully visible so ordinary clicks do not look like a
           full-page breathing/fade animation. */
        div[data-testid="stAppViewContainer"] [data-stale="true"] {
            opacity: 1 !important;
            filter: none !important;
            transition: none !important;
        }
        div[data-testid="stAppViewContainer"] [data-stale="true"] img {
            opacity: 1 !important;
            transition: none !important;
        }
        .feature-left-box {
            flex: 1;
        }
        .feature-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.22rem 0.52rem;
            margin-left: 0.55rem;
            border-radius: 999px;
            font-size: 0.74rem;
            color: #dcd5ff;
            background: rgba(120, 92, 255, 0.14);
            border: 1px solid rgba(130, 103, 255, 0.28);
            vertical-align: middle;
        }
        .feature-title {
            color: #ffffff;
            font-size: 1.55rem;
            font-weight: 700;
            margin-bottom: 0.24rem;
        }
        .feature-desc {
            color: rgba(214, 219, 255, 0.78);
            font-size: 0.88rem;
            margin-bottom: 0.55rem;
            max-width: 780px;
        }
        .meta-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.38rem;
            margin-bottom: 0.65rem;
        }
        .feature-desc,
        .meta-row {
            display: none !important;
        }
        .meta-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.28rem 0.56rem;
            border-radius: 999px;
            font-size: 0.74rem;
            color: #dbe0ff;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.06);
        }
        .workflow-strip {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.38rem;
            margin: 0.1rem 0 0.78rem;
            padding: 0.48rem;
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 13px;
            background: rgba(5, 12, 27, 0.42);
        }
        .workflow-step {
            display: flex;
            align-items: center;
            min-width: 0;
            gap: 0.42rem;
            color: rgba(230, 233, 255, 0.78);
            font-size: 0.74rem;
            line-height: 1.25;
            white-space: nowrap;
            position: relative;
        }
        .workflow-step:not(:last-child)::after {
            content: "";
            height: 1px;
            flex: 1 1 auto;
            min-width: 12px;
            margin-left: 0.18rem;
            background: linear-gradient(90deg, rgba(139, 117, 255, 0.46), rgba(139, 117, 255, 0.08));
        }
        .workflow-step-number {
            display: grid;
            place-items: center;
            width: 22px;
            height: 22px;
            flex: 0 0 22px;
            border-radius: 50%;
            color: #f7f6ff;
            font-size: 0.68rem;
            font-weight: 800;
            background: rgba(126, 96, 255, 0.2);
            border: 1px solid rgba(145, 122, 255, 0.34);
        }
        .a-plus-lab-page-marker,
        .a-plus-lab-left-marker,
        .a-plus-lab-right-marker,
        .feature-workbench-left-marker,
        .feature-workbench-right-marker {
            display: none;
        }
        .a-plus-lab-empty-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.72rem;
            min-height: 700px;
        }
        .a-plus-lab-empty-item {
            min-height: 338px;
            padding: 0.85rem;
            border: 1px dashed rgba(132, 111, 255, 0.48);
            border-radius: 12px;
            background: rgba(7, 15, 31, 0.42);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            color: rgba(214, 219, 255, 0.6);
        }
        .a-plus-lab-empty-index {
            align-self: flex-start;
            margin-bottom: auto;
            padding: 0.25rem 0.5rem;
            border-radius: 7px;
            color: rgba(224, 228, 255, 0.78);
            background: rgba(255, 255, 255, 0.035);
            font-size: 0.74rem;
        }
        .a-plus-lab-empty-copy {
            margin: auto 0;
        }
        .a-plus-lab-empty-title {
            color: rgba(241, 243, 255, 0.88);
            font-size: 0.9rem;
            font-weight: 650;
            margin-bottom: 0.38rem;
        }
        .a-plus-lab-empty-subtitle {
            max-width: 170px;
            font-size: 0.74rem;
            line-height: 1.55;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-lab-page-marker)
            > div[data-testid="stHorizontalBlock"]:has(.a-plus-lab-left-marker):has(.a-plus-lab-right-marker) {
            align-items: stretch;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-lab-page-marker)
            > div[data-testid="stHorizontalBlock"]:has(.a-plus-lab-left-marker):has(.a-plus-lab-right-marker)
            > :is(div[data-testid="column"], div[data-testid="stColumn"]) {
            min-width: 0;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-lab-left-marker),
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-lab-right-marker) {
            min-height: 760px;
            padding: 0.72rem 0.8rem 0.8rem;
            border: 1px solid rgba(132, 111, 255, 0.22);
            border-radius: 14px;
            background: rgba(7, 15, 31, 0.38);
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .feature-workbench-left-marker),
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .feature-workbench-right-marker) {
            box-sizing: border-box;
            min-width: 0;
            min-height: 620px;
            padding: 0.7rem 0.78rem 0.82rem;
            border: 1px solid rgba(132, 111, 255, 0.18);
            border-radius: 14px;
            background: rgba(7, 15, 31, 0.32);
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .feature-workbench-right-marker)
            .result-empty {
            min-height: 420px;
            margin-top: 0.25rem;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .feature-workbench-left-marker)
            div[data-testid="stAlert"],
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .feature-workbench-right-marker)
            div[data-testid="stAlert"] {
            margin-top: 0.35rem;
            margin-bottom: 0.35rem;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-lab-left-marker)
            div[data-testid="stFileUploader"] {
            margin-bottom: 0.1rem;
        }
        @media (max-width: 1050px) {
            .a-plus-lab-empty-grid {
                min-height: 560px;
            }
            .a-plus-lab-empty-item {
                min-height: 268px;
            }
        }
        .fixed-model-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.7rem;
            margin: 0.08rem 0 0.42rem;
            padding: 0.58rem 0.72rem;
            border-radius: 11px;
            border: 1px solid rgba(255, 255, 255, 0.07);
            background: rgba(255, 255, 255, 0.035);
            color: rgba(214, 219, 255, 0.68);
            font-size: 0.74rem;
        }
        .fixed-model-card strong {
            color: #f3f5ff;
            font-size: 0.82rem;
            font-weight: 750;
        }
        .a-plus-inline-model-card {
            min-height: 2.4rem;
            display: flex;
            align-items: center;
            padding: 0.5rem 0.65rem;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.035);
            color: #f3f5ff;
            font-size: 0.78rem;
            font-weight: 700;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .guide-wrap {
            min-width: 140px;
        }
        .section-kicker {
            color: rgba(214, 219, 255, 0.72);
            font-size: 0.78rem;
            margin: 0.15rem 0 0.45rem;
        }
        .panel-subtitle {
            color: rgba(214, 219, 255, 0.82);
            font-size: 0.82rem;
            font-weight: 600;
            margin: 0.2rem 0 0.26rem;
        }
        /* Streamlit compensates Markdown paragraphs with a negative bottom
           margin. These HTML headings need their full height in normal flow. */
        [data-testid="stMarkdownContainer"]:has(> :is(.panel-subtitle, .result-block-title, .section-kicker)) {
            margin-bottom: 0 !important;
        }
        .upload-main-empty, .result-empty {
            min-height: 188px;
            border-radius: 14px;
            border: 1px dashed rgba(132, 111, 255, 0.58);
            background: rgba(7, 15, 31, 0.52);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            gap: 0.55rem;
            text-align: center;
            color: rgba(214, 219, 255, 0.72);
            margin-bottom: 0.24rem;
        }
        .empty-icon {
            font-size: 1.9rem;
            color: #8b75ff;
            line-height: 1;
        }
        .empty-title {
            color: #eef1ff;
            font-size: 0.95rem;
            font-weight: 600;
        }
        .empty-subtitle {
            color: rgba(214, 219, 255, 0.62);
            font-size: 0.78rem;
        }
        .slot-empty {
            height: 88px;
            border-radius: 14px;
            border: 1px dashed rgba(132, 111, 255, 0.54);
            background: rgba(7, 15, 31, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #8b75ff;
            font-size: 1.6rem;
            margin-bottom: 0.35rem;
        }
        .slot-helper {
            color: rgba(214, 219, 255, 0.55);
            font-size: 0.72rem;
            text-align: left;
            margin: 0.12rem 0 0.32rem;
        }
        .a-plus-skill-summary {
            margin: 0.5rem 0 0.44rem;
            padding: 0.78rem 0.82rem;
            border: 1px solid rgba(132, 111, 255, 0.22);
            border-radius: 14px;
            background:
                radial-gradient(circle at top right, rgba(132, 111, 255, 0.12), transparent 42%),
                rgba(8, 16, 34, 0.76);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
        }
        .a-plus-skill-summary-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.7rem;
        }
        .a-plus-skill-summary-title {
            min-width: 0;
            color: #f6f7ff;
            font-size: 0.9rem;
            font-weight: 750;
            line-height: 1.35;
        }
        .a-plus-skill-status {
            flex: 0 0 auto;
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            padding: 0.2rem 0.46rem;
            border: 1px solid rgba(104, 226, 170, 0.24);
            border-radius: 999px;
            background: rgba(58, 193, 129, 0.1);
            color: #8be6ba;
            font-size: 0.68rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .a-plus-skill-status::before {
            content: "";
            width: 0.34rem;
            height: 0.34rem;
            border-radius: 999px;
            background: #71dda8;
            box-shadow: 0 0 0 3px rgba(113, 221, 168, 0.1);
        }
        .a-plus-skill-summary-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.34rem;
            margin-top: 0.52rem;
        }
        .a-plus-skill-summary-meta span {
            padding: 0.2rem 0.42rem;
            border: 1px solid rgba(255, 255, 255, 0.075);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.035);
            color: rgba(224, 228, 255, 0.72);
            font-size: 0.68rem;
            line-height: 1.2;
        }
        .a-plus-skill-summary-desc {
            display: -webkit-box;
            margin-top: 0.5rem;
            overflow: hidden;
            color: rgba(214, 219, 255, 0.68);
            font-size: 0.73rem;
            line-height: 1.55;
            -webkit-box-orient: vertical;
            -webkit-line-clamp: 2;
        }
        .a-plus-skill-summary-note {
            margin-top: 0.48rem;
            padding-top: 0.46rem;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            color: rgba(168, 182, 232, 0.62);
            font-size: 0.68rem;
            line-height: 1.45;
        }
        .a-plus-skill-detail-copy {
            color: rgba(214, 219, 255, 0.72);
            font-size: 0.74rem;
            line-height: 1.62;
        }
        .a-plus-skill-detail-copy strong {
            color: #f2f4ff;
            font-weight: 700;
        }
        .inline-action-row {
            margin-top: 0.42rem;
            padding-top: 0.48rem;
            border-top: 1px solid rgba(255, 255, 255, 0.07);
        }
        .main-action-dock-marker,
        .a-plus-mode-selector-marker,
        .a-plus-template-card-marker,
        .a-plus-analysis-card-marker,
        .a-plus-auto-fill-card-marker,
        .image-smart-analysis-report-marker,
        .batch-left-column-marker,
        .batch-right-column-marker,
        .upload-add-marker,
        .upload-more-marker {
            display: none !important;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .batch-left-column-marker),
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .batch-right-column-marker) {
            align-self: stretch !important;
            min-width: 0 !important;
            padding: 0.78rem 0.82rem 0.82rem !important;
            border: 1px solid rgba(255, 255, 255, 0.075);
            border-radius: 15px;
            background:
                radial-gradient(circle at top right, rgba(132, 111, 255, 0.075), transparent 31%),
                rgba(5, 13, 29, 0.58);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .batch-right-column-marker) .result-empty {
            min-height: 390px;
            margin-bottom: 0;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .batch-left-column-marker) .result-block-title,
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .batch-right-column-marker) .result-block-title {
            margin-bottom: 0.62rem;
        }
        .upload-summary-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            min-height: 34px;
            margin: 0 0 0.5rem;
            padding: 0.42rem 0.58rem;
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.035);
            color: rgba(214, 219, 255, 0.72);
            font-size: 0.74rem;
        }
        .upload-summary-row strong {
            color: #f3f5ff;
            font-size: 0.78rem;
            font-weight: 750;
        }
        .upload-summary-row span:last-child {
            color: rgba(214, 219, 255, 0.56);
        }
        .upload-sortable-item {
            position: relative;
        }
        .upload-sort-grip {
            position: absolute;
            z-index: 24;
            top: 6px;
            left: 6px;
            display: inline-flex;
            align-items: center;
            gap: 0.28rem;
            min-height: 28px;
            padding: 0.18rem 0.48rem;
            border: 1px solid rgba(255, 255, 255, 0.46);
            border-radius: 999px;
            background: rgba(16, 24, 47, 0.9);
            color: #ffffff;
            font-size: 0.68rem;
            font-weight: 700;
            line-height: 1;
            cursor: grab;
            user-select: none;
            box-shadow: 0 5px 14px rgba(0, 0, 0, 0.3);
        }
        .upload-sort-grip:active {
            cursor: grabbing;
        }
        .upload-sort-grip-icon {
            color: #b9adff;
            font-size: 0.8rem;
            letter-spacing: -0.16rem;
        }
        .upload-sortable-item.upload-sort-dragging {
            opacity: 0.56;
        }
        .upload-sort-drop-zone {
            position: fixed;
            z-index: 999997;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 2px dashed rgba(174, 158, 255, 0.88);
            border-radius: 14px;
            background: rgba(30, 24, 64, 0.58);
            color: #ffffff;
            font-size: 0.76rem;
            font-weight: 750;
            pointer-events: auto;
            backdrop-filter: blur(2px);
            transition: border-color 0.12s ease, background 0.12s ease, transform 0.12s ease;
        }
        .upload-sort-drop-zone.is-source {
            border-color: rgba(255, 255, 255, 0.2);
            background: rgba(8, 15, 31, 0.35);
            color: rgba(255, 255, 255, 0.56);
        }
        .upload-sort-drop-zone.is-target {
            border-color: #c9beff;
            background: rgba(99, 72, 222, 0.72);
            transform: scale(1.025);
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker),
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker) {
            position: sticky;
            top: 0.55rem;
            z-index: 42;
            margin: 0 0 0.72rem !important;
            padding: 0.58rem 0.62rem 0.48rem !important;
            border: 1px solid rgba(132, 111, 255, 0.34) !important;
            border-radius: 14px !important;
            border-color: rgba(132, 111, 255, 0.34) !important;
            background:
                linear-gradient(180deg, rgba(13, 23, 48, 0.98), rgba(8, 16, 34, 0.96)) !important;
            box-shadow:
                0 14px 32px rgba(0, 0, 0, 0.3),
                inset 0 1px 0 rgba(255, 255, 255, 0.055);
            backdrop-filter: blur(16px);
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker) .fixed-model-card,
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker) .fixed-model-card {
            margin-top: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker) .inline-action-row,
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker) .inline-action-row {
            display: none !important;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-mode-selector-marker) > .stElementContainer:has(.stRadio) {
            width: 100% !important;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-mode-selector-marker) .stRadio {
            width: 100% !important;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-mode-selector-marker) .stRadio [role="radiogroup"] {
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.34rem !important;
            width: 100% !important;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-mode-selector-marker) .stRadio [role="radiogroup"] label {
            min-width: 0 !important;
            min-height: 34px !important;
            padding: 0.18rem 0.36rem !important;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            background: rgba(8, 16, 34, 0.72);
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-template-card-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-template-card-marker),
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-template-card-marker) {
            min-height: 272px;
            padding: 0.62rem 0.68rem 0.52rem !important;
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            border-radius: 14px !important;
            background: rgba(7, 15, 31, 0.52) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-analysis-card-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-analysis-card-marker),
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-analysis-card-marker) {
            min-height: 178px;
            padding: 0.62rem 0.68rem 0.52rem !important;
            border: 1px solid rgba(132, 111, 255, 0.18) !important;
            border-radius: 14px !important;
            border-color: rgba(132, 111, 255, 0.18) !important;
            background: rgba(10, 18, 38, 0.68) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-auto-fill-card-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-auto-fill-card-marker),
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-auto-fill-card-marker) {
            min-height: 210px;
            padding: 0.62rem 0.68rem 0.52rem !important;
            border: 1px solid rgba(132, 111, 255, 0.18) !important;
            border-radius: 14px !important;
            border-color: rgba(132, 111, 255, 0.18) !important;
            background: rgba(10, 18, 38, 0.68) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-analysis-card-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-analysis-card-marker) .stButton,
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-analysis-card-marker) .stButton,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-auto-fill-card-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-auto-fill-card-marker) .stButton,
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-auto-fill-card-marker) .stButton {
            min-height: 34px;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .image-smart-analysis-report-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .image-smart-analysis-report-marker),
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .image-smart-analysis-report-marker) {
            min-height: 520px;
            padding: 0.9rem 1rem 0.8rem !important;
            border: 1px solid rgba(132, 111, 255, 0.2) !important;
            border-radius: 15px !important;
            background:
                radial-gradient(circle at top right, rgba(132, 111, 255, 0.09), transparent 28%),
                rgba(7, 15, 31, 0.64) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .image-smart-analysis-report-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .image-smart-analysis-report-marker) h1,
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .image-smart-analysis-report-marker) h1 {
            font-size: 1.32rem !important;
            margin: 0 0 0.72rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .image-smart-analysis-report-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .image-smart-analysis-report-marker) h2,
        div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .image-smart-analysis-report-marker) h2 {
            color: #f2efff !important;
            font-size: 1rem !important;
            margin: 1rem 0 0.38rem !important;
            padding-bottom: 0.28rem;
            border-bottom: 1px solid rgba(132, 111, 255, 0.16);
        }
        :is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.skin-reference-grid-marker)
            + :is(div[data-testid="stHorizontalBlock"], div[data-testid="stLayoutWrapper"]) {
            align-items: start !important;
        }
        :is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.skin-reference-grid-marker)
            + :is(div[data-testid="stHorizontalBlock"], div[data-testid="stLayoutWrapper"]) :is(div[data-testid="column"], div[data-testid="stColumn"]) {
            min-width: 0 !important;
        }
        :is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.skin-reference-grid-marker)
            + :is(div[data-testid="stHorizontalBlock"], div[data-testid="stLayoutWrapper"])
            :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.upload-preview-root) {
            min-height: 154px !important;
        }
        :is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.skin-reference-grid-marker)
            + :is(div[data-testid="stHorizontalBlock"], div[data-testid="stLayoutWrapper"])
            :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.upload-preview-root) div[data-testid="stVerticalBlock"]:has(.upload-preview-root) {
            width: min(136px, 100%) !important;
        }
        :is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.skin-reference-grid-marker)
            + :is(div[data-testid="stHorizontalBlock"], div[data-testid="stLayoutWrapper"])
            :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.upload-preview-root) iframe {
            max-height: 122px !important;
        }
        :is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.skin-reference-grid-marker)
            + :is(div[data-testid="stHorizontalBlock"], div[data-testid="stLayoutWrapper"])
            div[data-testid="stCaptionContainer"] {
            display: none !important;
        }
        :is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.skin-reference-grid-marker)
            + :is(div[data-testid="stHorizontalBlock"], div[data-testid="stLayoutWrapper"])
            .stSelectbox {
            margin-top: 0 !important;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .inline-action-row)
            div[data-testid="stHorizontalBlock"]:has(.stButton) {
            align-items: end !important;
            display: grid !important;
            grid-template-columns: minmax(0, 1.35fr) minmax(0, 0.95fr) !important;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .inline-action-row)
            div[data-testid="stHorizontalBlock"]:has(.stNumberInput) {
            grid-template-columns: minmax(160px, 0.68fr) minmax(0, 1.42fr) minmax(120px, 0.82fr) !important;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .inline-action-row)
            div[data-testid="stHorizontalBlock"]:has(.stButton)
            > :is(div[data-testid="column"], div[data-testid="stColumn"]) {
            width: 100% !important;
            min-width: 0 !important;
        }
        /* Streamlit compensates Markdown paragraph margins by -16px. These
           authored HTML labels/cards have no paragraph margin to compensate. */
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .inline-action-row)
            [data-testid="stMarkdown"] [data-testid="stMarkdownContainer"] {
            margin-bottom: 0 !important;
        }
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker) {
            border-color: rgba(132, 111, 255, 0.18) !important;
        }
        .stRadio [role="radiogroup"] {
            gap: 0.18rem !important;
        }
        .stRadio [role="radiogroup"] label {
            min-height: 28px !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        .compact-thumb img {
            border-radius: 12px !important;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .clickable-image-grid {
            display: grid;
            gap: 0.5rem;
            margin-bottom: 0.5rem;
        }
        .clickable-image-card {
            display: block;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.08);
            background: rgba(7, 15, 31, 0.52);
            text-decoration: none;
            transition: transform 0.16s ease, border-color 0.16s ease;
        }
        .clickable-image-card:hover {
            transform: translateY(-1px);
            border-color: rgba(140, 124, 255, 0.55);
        }
        .clickable-image-card img {
            width: 100%;
            display: block;
        }
        .clickable-image-tip {
            color: rgba(214, 219, 255, 0.62);
            font-size: 0.76rem;
            margin: -0.15rem 0 0.65rem;
        }
        [data-testid="stFileUploader"] {
            margin: 0 !important;
            padding: 0 !important;
        }
        [data-testid="stFileUploader"] > section {
            margin: 0 !important;
            padding: 0 !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            background: rgba(10, 19, 38, 0.92) !important;
            color: rgba(243, 246, 255, 0.92) !important;
            border: 1px solid rgba(255, 255, 255, 0.10) !important;
            border-radius: 12px !important;
            min-height: 34px !important;
            height: 34px !important;
            padding: 0 !important;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            width: 100% !important;
            position: relative !important;
        }
        [data-testid="stFileUploaderDropzone"]:hover {
            background: rgba(18, 30, 56, 0.96) !important;
            border-color: rgba(138, 158, 255, 0.24) !important;
            color: #ffffff !important;
        }
        [data-testid="stFileUploaderDropzoneInstructions"] {
            display: none !important;
        }
        [data-testid="stFileUploaderDropzone"]::after {
            content: "选择图片";
            font-size: 0.76rem;
            font-weight: 600;
            color: inherit;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 100%;
            position: absolute;
            left: 0;
            top: 0;
        }
        div[data-testid="stFileUploader"]:has([aria-label="继续上传"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "继续上传";
        }
        div[data-testid="stFileUploader"]:has([aria-label="重新上传"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "重新上传";
        }
        div[data-testid="stFileUploader"]:has([aria-label="上传图片"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "上传图片";
        }
        div[data-testid="stFileUploader"]:has([aria-label="上传参考图"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "上传参考图";
        }
        [data-testid="stFileUploaderFile"] {
            display: none !important;
        }
        [data-testid="stFileUploaderDropzone"] button {
            display: none !important;
        }
        .image-placeholder {
            color: rgba(214, 219, 255, 0.68);
            font-size: 0.9rem;
            line-height: 1.8;
            text-align: center;
            padding: 2.75rem 0.8rem;
        }
        .stTextArea textarea, .stTextInput input {
            background: rgba(7, 15, 31, 0.92) !important;
            color: #f4f6ff !important;
            border-radius: 14px !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
        }
        /* Streamlit uses BaseWeb in older releases and React Aria in newer
           ones. Style each control shell as well as its text input. */
        :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) [data-baseweb="select"] > div {
            background: rgba(7, 15, 31, 0.92) !important;
            color: #f4f6ff !important;
            border-radius: 10px !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
        }
        :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) [role="group"]:has(input[role="combobox"]) {
            background: #0a1326 !important;
            color: #f4f6ff !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            border-radius: 10px !important;
            min-width: 0;
            max-width: 100%;
        }
        :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) input[role="combobox"] {
            background: transparent !important;
        }
        :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) input::placeholder {
            color: #cbd3ec !important;
            -webkit-text-fill-color: #cbd3ec !important;
            opacity: 1;
        }
        :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) [role="group"]:has(input[role="combobox"]) button {
            background: transparent !important;
            color: #d6dbff !important;
            border: 0 !important;
        }
        :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) [data-baseweb="select"] {
            min-width: 0;
            max-width: 100%;
        }
        :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) [data-baseweb="select"] :is(div, span) {
            color: #f4f6ff !important;
        }
        :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) :is([role="combobox"], input),
        [data-testid="stNumberInput"] input {
            color: #f4f6ff !important;
            -webkit-text-fill-color: #f4f6ff !important;
            caret-color: #b9adff;
        }
        :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) svg {
            color: #d6dbff !important;
            fill: currentColor;
        }
        [data-testid="stNumberInputContainer"] {
            background: #0a1326 !important;
            color: #f4f6ff !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            border-radius: 10px !important;
            overflow: hidden;
        }
        [data-testid="stNumberInput"] input {
            min-width: 0;
            background: transparent !important;
        }
        [data-testid="stNumberInput"] [data-baseweb="input"],
        [data-testid="stNumberInput"] [data-baseweb="base-input"] {
            background: transparent !important;
            color: #f4f6ff !important;
            border: 0 !important;
        }
        [data-testid="stNumberInput"] button {
            flex-shrink: 0;
            color: #f4f6ff !important;
            background: #111c33 !important;
            border: 0 !important;
        }
        [data-testid="stNumberInput"] button:hover:not(:disabled) {
            background: #282448 !important;
        }
        [data-testid="stNumberInput"] button:disabled {
            color: #8790aa !important;
        }
        [data-testid="stNumberInput"] button svg {
            color: inherit !important;
            fill: currentColor;
        }
        :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) [data-baseweb="select"]:focus-within > div,
        :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) [role="group"]:has(input[role="combobox"]):focus-within,
        [data-testid="stNumberInputContainer"]:focus-within {
            border-color: #9b85ff !important;
            box-shadow: 0 0 0 2px rgba(132, 111, 255, 0.22) !important;
        }
        /* Select menus are mounted in a portal outside the widget itself. */
        [data-baseweb="popover"]:has([data-testid="stSelectboxVirtualDropdown"]) {
            background: #0d172d !important;
            border-color: rgba(132, 111, 255, 0.34) !important;
        }
        [data-baseweb="popover"] [role="listbox"],
        [data-baseweb="popover"]:has([data-testid="stSelectboxVirtualDropdown"]) > div,
        [data-testid="stSelectboxVirtualDropdown"],
        [data-testid="stMultiSelectDropdown"],
        [data-testid="stSelectboxVirtualDropdown"] > div {
            background: #0d172d !important;
            color: #f4f6ff !important;
        }
        :is([data-testid="stSelectboxVirtualDropdown"], [data-testid="stMultiSelectDropdown"]) {
            border-color: rgba(132, 111, 255, 0.34) !important;
        }
        [role="listbox"] [role="option"],
        :is([data-testid="stSelectboxVirtualDropdown"], [data-testid="stMultiSelectDropdown"]) [role="option"] {
            background: #0d172d !important;
            color: #f4f6ff !important;
        }
        [role="listbox"] [role="option"]:is(:hover, [aria-selected="true"], [data-focused], [data-hovered]),
        :is([data-testid="stSelectboxVirtualDropdown"], [data-testid="stMultiSelectDropdown"]) [role="option"]:is(:hover, [aria-selected="true"], [data-focused], [data-hovered]) {
            background: #302653 !important;
        }
        :is([data-testid="stSelectboxVirtualDropdown"], [data-testid="stMultiSelectDropdown"]) [data-item-hl] {
            background: inherit !important;
            color: inherit !important;
        }
        .stForm {
            border: none !important;
            background: transparent !important;
            padding: 0 !important;
        }
        .stButton {
            margin: 0 !important;
            padding: 0 !important;
        }
        .stButton > button[kind="primary"], .stFormSubmitButton > button {
            background: linear-gradient(135deg, #7a5cff, #5d44f6);
            color: #ffffff;
            border: none;
            border-radius: 12px;
            box-shadow: 0 12px 30px rgba(93, 68, 246, 0.25);
        }
        .stButton > button[kind="secondary"] {
            background: rgba(10, 19, 38, 0.92) !important;
            color: rgba(243, 246, 255, 0.92) !important;
            border: 1px solid rgba(255, 255, 255, 0.10) !important;
            border-radius: 12px;
            box-shadow: none;
            min-height: 34px;
            padding: 0.18rem 0.55rem;
        }
        .stButton > button[kind="secondary"]:hover {
            background: rgba(18, 30, 56, 0.96) !important;
            border-color: rgba(138, 158, 255, 0.24) !important;
            color: #ffffff !important;
        }
        .stButton > button[kind="secondary"] p {
            color: rgba(243, 246, 255, 0.92) !important;
            font-size: 0.76rem !important;
            font-weight: 600 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }
        .stButton > button,
        [data-testid="stFileUploaderDropzone"] {
            min-width: 0 !important;
        }
        [data-testid="stFileUploaderDropzone"]::after {
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            padding: 0 0.35rem;
            box-sizing: border-box;
        }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stFileUploader"]):has(.stButton) > :is(div[data-testid="column"], div[data-testid="stColumn"]) {
            width: 100% !important;
            min-width: 0 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root) {
            position: relative;
            margin-bottom: 0.35rem;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root) .upload-preview-root {
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
        }
        div[data-testid="element-container"]:has(.upload-replace-uploader-marker) {
            display: none !important;
        }
        div[data-testid="element-container"]:has(.upload-replace-uploader-marker) + div[data-testid="element-container"] {
            position: static !important;
            display: block !important;
            width: 100% !important;
            height: auto !important;
            margin: 0.34rem 0 0 !important;
            padding: 0 !important;
            opacity: 1 !important;
            pointer-events: auto !important;
        }
        div[data-testid="element-container"]:has(.upload-replace-uploader-marker) + div[data-testid="element-container"] [data-testid="stFileUploaderDropzone"] {
            min-height: 30px !important;
            height: 30px !important;
            border-radius: 10px !important;
            background: rgba(10, 19, 38, 0.9) !important;
        }
        div[data-testid="element-container"]:has(.upload-replace-uploader-marker) + div[data-testid="element-container"] [data-testid="stFileUploaderDropzone"]::after {
            content: "替换图片" !important;
        }
        div[data-testid="element-container"]:has(.upload-add-marker) + div[data-testid="element-container"] [data-testid="stFileUploaderDropzone"]::after {
            content: "添加图片" !important;
        }
        div[data-testid="element-container"]:has(.upload-more-marker) + div[data-testid="element-container"] [data-testid="stFileUploaderDropzone"]::after {
            content: "继续添加" !important;
        }
        div[data-testid="stFileUploader"]:has([aria-label="替换图片"]) [data-testid="stFileUploaderDropzone"]::after {
            content: "替换图片";
        }
        .upload-replace-hotspot {
            position: fixed !important;
            z-index: 999998 !important;
            margin: 0 !important;
            padding: 0 !important;
            opacity: 0;
            pointer-events: none;
            display: block !important;
            transition: opacity 0.14s ease;
        }
        body.upload-file-dragging .upload-replace-hotspot {
            opacity: 1;
            pointer-events: auto;
        }
        .upload-replace-hotspot {
            border: 2px solid rgba(126, 96, 255, 0.94) !important;
            border-radius: 14px !important;
            background: rgba(8, 15, 31, 0.72) !important;
            box-shadow: 0 0 0 9999px rgba(3, 8, 22, 0.14);
            backdrop-filter: blur(2px);
        }
        .upload-replace-hotspot::after {
            content: "松开替换图片" !important;
            color: #ffffff;
            font-size: 0.82rem;
            font-weight: 700;
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        div[data-testid="element-container"].upload-replace-overlay {
            position: fixed !important;
            z-index: 999999 !important;
            display: block !important;
            margin: 0 !important;
            padding: 0 !important;
            opacity: 0.01;
            pointer-events: none;
        }
        body.upload-file-dragging div[data-testid="element-container"].upload-replace-overlay {
            pointer-events: auto;
        }
        div[data-testid="element-container"].upload-replace-overlay [data-testid="stFileUploader"],
        div[data-testid="element-container"].upload-replace-overlay [data-testid="stFileUploader"] > section,
        div[data-testid="element-container"].upload-replace-overlay [data-testid="stFileUploaderDropzone"] {
            width: 100% !important;
            height: 100% !important;
            min-height: 100% !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker) {
            display: none !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) {
            position: absolute !important;
            z-index: 20;
            top: 6px !important;
            right: 6px !important;
            width: 28px !important;
            height: 28px !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
            display: block !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) [data-testid="stButton"],
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) [data-testid="stTooltipIcon"],
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) [data-testid="stTooltipHoverTarget"] {
            width: 28px !important;
            height: 28px !important;
            min-width: 28px !important;
            min-height: 28px !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) button {
            min-height: 28px !important;
            height: 28px !important;
            min-width: 28px !important;
            width: 28px !important;
            padding: 0 !important;
            border-radius: 50% !important;
            background: rgba(255, 77, 90, 0.96) !important;
            border: 1px solid rgba(255, 255, 255, 0.92) !important;
            color: #ffffff !important;
            display: flex;
            align-items: center;
            justify-content: center;
            line-height: 1;
            box-shadow: 0 6px 14px rgba(0, 0, 0, 0.34) !important;
            opacity: 1 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) button:hover {
            background: rgba(255, 36, 74, 1) !important;
            border-color: rgba(255, 255, 255, 1) !important;
            color: #ffffff !important;
        }
        div[data-testid="stVerticalBlock"]:has(.upload-preview-root)
            > div:is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.delete-marker)
            + div:is([data-testid="stElementContainer"], [data-testid="element-container"]) button p {
            color: inherit !important;
            font-size: 15px !important;
            font-weight: 800 !important;
            line-height: 1 !important;
            margin: 0 !important;
            padding: 0 !important;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .stButton > button[kind="secondary"].small-icon-button,
        .stButton > button[kind="secondary"]:has(p:only-child) {
            box-shadow: none;
        }
        [data-testid="stPopoverButton"] > button {
            background: rgba(255, 255, 255, 0.06);
            color: #f8f9ff;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(8, 15, 31, 0.55);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 18px;
        }
        .result-block-title {
            color: #ffffff;
            font-size: 0.92rem;
            font-weight: 700;
            margin-bottom: 0.48rem;
        }
        .canvas-flow-summary {
            display: flex;
            flex-wrap: wrap;
            gap: 0.36rem;
            margin: 0 0 0.58rem;
        }
        .canvas-flow-chip {
            display: inline-flex;
            align-items: center;
            padding: 0.22rem 0.52rem;
            border-radius: 999px;
            color: #e8eaff;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.08);
            font-size: 0.72rem;
            line-height: 1.3;
        }
        :is(div[data-testid="column"], div[data-testid="stColumn"]):has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .canvas-right-column-marker) {
            align-self: flex-start !important;
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            background:
                radial-gradient(circle at top right, rgba(132, 111, 255, 0.12), transparent 30%),
                rgba(6, 14, 29, 0.72);
            padding: 0.72rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
        }
        div[data-testid="stVerticalBlock"] {
            gap: 0.42rem !important;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.62rem !important;
        }
        div[data-testid="element-container"] {
            margin-bottom: 0.18rem !important;
        }
        .stSlider {
            padding-top: 0 !important;
            padding-bottom: 0.12rem !important;
        }
        [data-testid="stWidgetLabel"],
        [data-testid="stWidgetLabel"] :is(p, span),
        [data-testid="stWidgetLabel"] [data-testid="stTooltipIcon"] button {
            color: rgba(225, 229, 255, 0.82) !important;
        }
        [data-testid="stAlertContainer"] {
            background: #10213b !important;
            color: #c8ddff !important;
            border: 1px solid rgba(118, 162, 255, 0.24);
        }
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {
            background: #102d29 !important;
            color: #b6ebce !important;
        }
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {
            background: #302719 !important;
            color: #ffe2a3 !important;
        }
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {
            background: #331d2b !important;
            color: #ffc5ce !important;
        }
        [data-testid="stAlertContainer"] [data-testid^="stAlertContent"] {
            color: inherit !important;
        }
        .stSlider label p,
        .stTextArea label p,
        .stSelectbox label p,
        [data-testid="stNumberInput"] label p,
        [data-testid="stTextInput"] label p,
        [data-testid="stMultiSelect"] label p,
        .stRadio label p {
            color: rgba(225, 229, 255, 0.82) !important;
            font-size: 0.76rem !important;
            font-weight: 600 !important;
        }
        .stSlider [data-baseweb="slider"] {
            padding-top: 0.15rem !important;
            padding-bottom: 0.15rem !important;
        }
        [data-testid="stCaptionContainer"] {
            font-size: 0.72rem !important;
            line-height: 1.35 !important;
        }
        /* Use the available workspace width, including when the app is framed. */
        div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .workspace-panel) {
            container-type: inline-size;
            container-name: xiaoha-workspace;
            min-width: 0;
        }
        @container xiaoha-workspace (max-width: 960px) {
            div[data-testid="stHorizontalBlock"]:is(:has(.feature-workbench-left-marker), :has(.a-plus-lab-left-marker)) {
                flex-direction: column;
                align-items: stretch;
            }
            div[data-testid="stHorizontalBlock"]:is(:has(.feature-workbench-left-marker), :has(.a-plus-lab-left-marker))
                > :is(div[data-testid="column"], div[data-testid="stColumn"]) {
                flex: 1 1 auto !important;
                width: 100% !important;
                min-width: 0 !important;
            }
            div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .feature-workbench-left-marker),
            div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .feature-workbench-right-marker) {
                min-height: 0;
            }
        }
        @container xiaoha-workspace (max-width: 560px) {
            :is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.skin-reference-grid-marker)
                + div[data-testid="stHorizontalBlock"],
            :is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.skin-reference-grid-marker)
                + div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
                flex-direction: column;
                align-items: stretch;
            }
            :is([data-testid="stElementContainer"], [data-testid="element-container"]):has(.skin-reference-grid-marker)
                + :is(div[data-testid="stHorizontalBlock"], div[data-testid="stLayoutWrapper"])
                :is(div[data-testid="column"], div[data-testid="stColumn"]) {
                flex: 1 1 auto !important;
                width: 100% !important;
            }
            div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .inline-action-row)
                div[data-testid="stHorizontalBlock"]:has(.stNumberInput) {
                grid-template-columns: minmax(160px, 0.68fr) minmax(0, 1.42fr) !important;
            }
            div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .inline-action-row)
                div[data-testid="stHorizontalBlock"]:has(.stNumberInput)
                > :is(div[data-testid="column"], div[data-testid="stColumn"]):last-child {
                grid-column: 1 / -1;
            }
            div[data-testid="stHorizontalBlock"]:has(> :is(div[data-testid="column"], div[data-testid="stColumn"]) [data-testid="stSelectbox"]):not(:has(.stNumberInput)) {
                flex-wrap: wrap;
            }
            .workflow-step {
                white-space: normal;
                overflow-wrap: anywhere;
            }
        }
        @container xiaoha-workspace (max-width: 380px) {
            div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .inline-action-row)
                div[data-testid="stHorizontalBlock"]:has(.stButton) {
                grid-template-columns: minmax(0, 1fr) !important;
            }
        }
        @media (max-width: 768px) {
            div[data-testid="stHorizontalBlock"]:has(> :is(div[data-testid="column"], div[data-testid="stColumn"]) .side-menu-shell) {
                flex-wrap: wrap;
            }
            :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell),
            :is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell)
                + :is(div[data-testid="column"], div[data-testid="stColumn"]) {
                flex: 1 1 100% !important;
                width: 100% !important;
            }
        }
        @media (max-width: 900px) {
            .main .block-container,
            [data-testid="stMainBlockContainer"] {
                padding-left: 0.55rem;
                padding-right: 0.55rem;
            }
            .feature-title {
                font-size: 1.28rem;
            }
            .workspace-panel {
                padding: 0.62rem;
            }
            .workflow-strip {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .workflow-step:last-child {
                grid-column: span 2;
            }
            .workflow-step::after {
                display: none !important;
            }
            :is(div[data-testid="column"], div[data-testid="stColumn"]):has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .batch-right-column-marker) .result-empty {
                min-height: 250px;
            }
            div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker),
            div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .main-action-dock-marker) {
                position: relative;
                top: auto;
            }
            div[data-testid="stVerticalBlock"]:has(> :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-mode-selector-marker) .stRadio [role="radiogroup"] {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-template-card-marker, > div > div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-template-card-marker),
            div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stVerticalBlock"] > :is([data-testid="stElementContainer"], [data-testid="element-container"]) .a-plus-template-card-marker) {
                min-height: 224px;
            }
        }

        /* Sidebar overrides follow shared workbench styles. */
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 6px !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpanderDetails"] {
            border: none !important;
        }
        [data-testid="stSidebar"] .stButton [data-testid="stMarkdownContainer"] {
            width: 100%;
            text-align: left !important;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"],
        [data-testid="stSidebar"] [data-testid="stExpander"] details {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary,
        [data-testid="stSidebar"] [data-testid="stExpander"] details[open] > summary {
            background: transparent !important;
            color: #c4cce0 !important;
            border: none !important;
            border-radius: 8px !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
            background: #141d33 !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button {
            min-height: 36px !important;
            justify-content: flex-start !important;
            padding: 6px 12px !important;
            border: none !important;
            border-radius: 6px !important;
            background: transparent !important;
            box-shadow: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button p {
            width: 100%;
            text-align: left !important;
            font-size: 13px !important;
            font-weight: 400 !important;
            color: #aeb9d1 !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button > div,
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button [data-testid="stMarkdownContainer"] {
            width: 100% !important;
            text-align: left !important;
            justify-content: flex-start !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button:hover {
            background: #141d33 !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button[kind="primary"] {
            background: rgba(117, 91, 255, 0.18) !important;
            box-shadow: inset 3px 0 #8c75ff !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button[kind="primary"] p {
            color: #ded7ff !important;
            font-weight: 600 !important;
        }
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="stSidebarCollapseButton"] button * {
            color: #b8abff !important;
        }

        @media (min-width: 768px) {
            [data-testid="stAppViewContainer"]:has([data-testid="stExpandSidebarButton"]) [data-testid="stMainBlockContainer"] {
                padding-left: 72px !important;
            }
        }
        @media (max-width: 767px) {
            [data-testid="stAppViewContainer"]:has([data-testid="stExpandSidebarButton"]) [data-testid="stMainBlockContainer"] {
                padding-top: 56px !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_clipboard_paste_support(*, components) -> None:
    components.html(
        """
        <script>
        (function () {
          const hostWindow = window.parent;
          const hostDocument = hostWindow && hostWindow.document;
          if (!hostWindow || !hostDocument || hostWindow.__lashforgePasteSupportInstalled) {
            return;
          }
          hostWindow.__lashforgePasteSupportInstalled = true;
          hostWindow.__lashforgeLastUploaderInput = null;

          function isVisible(element) {
            if (!element || !(element instanceof hostWindow.HTMLElement)) {
              return false;
            }
            const style = hostWindow.getComputedStyle(element);
            if (!style || style.display === "none" || style.visibility === "hidden") {
              return false;
            }
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          }

          function findUploaderInputFromNode(node) {
            let current = node;
            while (current && current !== hostDocument.body) {
              if (typeof current.querySelector === "function") {
                const input = current.querySelector('input[type="file"]');
                if (input && input.isConnected && !input.disabled) {
                  return input;
                }
              }
              current = current.parentElement;
            }
            return null;
          }

          function getVisibleFileInputs() {
            return Array.from(hostDocument.querySelectorAll('input[type="file"]')).filter(function (input) {
              // Streamlit keeps the native file input visually hidden.  It is
              // still the real upload target, so visibility must not be used
              // to decide whether paste can target it.
              return input && !input.disabled;
            });
          }

          function resolveTargetInput() {
            const active = hostDocument.activeElement;
            if (active && active.tagName === "INPUT" && active.type === "file" && isVisible(active) && !active.disabled) {
              return active;
            }
            const remembered = hostWindow.__lashforgeLastUploaderInput;
            if (remembered && remembered.isConnected && !remembered.disabled) {
              return remembered;
            }
            const visibleInputs = getVisibleFileInputs();
            if (visibleInputs.length) {
              return visibleInputs[0];
            }
            // Some Streamlit versions render the input without the type
            // attribute until the uploader receives focus. Find it by the
            // uploader test id as a final fallback.
            const zones = Array.from(hostDocument.querySelectorAll('[data-testid*="fileUploader"], [data-testid*="FileUploader"]'));
            for (const zone of zones) {
              const input = zone.querySelector('input');
              if (input && !input.disabled) return input;
            }
            return null;
          }

          function showToast(message) {
            let toast = hostDocument.getElementById("lashforge-paste-toast");
            if (!toast) {
              toast = hostDocument.createElement("div");
              toast.id = "lashforge-paste-toast";
              toast.style.cssText = [
                "position:fixed",
                "right:18px",
                "bottom:18px",
                "z-index:999999",
                "padding:10px 14px",
                "border-radius:12px",
                "background:rgba(10,18,36,0.92)",
                "border:1px solid rgba(126,166,255,0.28)",
                "color:#eef4ff",
                "font-size:12px",
                "box-shadow:0 12px 34px rgba(0,0,0,0.28)",
                "opacity:0",
                "transition:opacity .18s ease"
              ].join(";");
              hostDocument.body.appendChild(toast);
            }
            toast.textContent = message;
            toast.style.opacity = "1";
            hostWindow.clearTimeout(hostWindow.__lashforgePasteToastTimer);
            hostWindow.__lashforgePasteToastTimer = hostWindow.setTimeout(function () {
              toast.style.opacity = "0";
            }, 1800);
          }

          hostDocument.addEventListener("pointerdown", function (event) {
            const input = findUploaderInputFromNode(event.target);
            if (input) {
              hostWindow.__lashforgeLastUploaderInput = input;
            }
          }, true);

          hostDocument.addEventListener("mouseover", function (event) {
            const input = findUploaderInputFromNode(event.target);
            if (input) {
              hostWindow.__lashforgeLastUploaderInput = input;
            }
          }, true);

          hostDocument.addEventListener("paste", async function (event) {
            const clipboard = event.clipboardData;
            if (!clipboard || !clipboard.items || !clipboard.items.length) {
              return;
            }
            const imageFiles = Array.from(clipboard.items)
              .filter(function (item) { return item.kind === "file" && /^image\\//i.test(item.type || ""); })
              .map(function (item) { return item.getAsFile(); })
              .filter(Boolean);
            if (!imageFiles.length) {
              return;
            }
            const targetInput = resolveTargetInput();
            if (!targetInput) {
              showToast("未找到可粘贴的图片上传区域");
              return;
            }
            try {
              const transfer = new hostWindow.DataTransfer();
              imageFiles.forEach(function (file) {
                transfer.items.add(file);
              });
              targetInput.files = transfer.files;
              targetInput.dispatchEvent(new hostWindow.Event("change", { bubbles: true }));
              targetInput.dispatchEvent(new hostWindow.Event("input", { bubbles: true }));
              event.preventDefault();
              showToast(imageFiles.length > 1 ? "已粘贴图片到上传区域" : "已粘贴图片到当前上传区域");
            } catch (error) {
              showToast("粘贴图片失败，请改用上传按钮");
            }
          }, true);
        })();
        </script>
        """,
        height=0,
    )


def inject_upload_drag_replace_support(*, components) -> None:
    components.html(
        """
        <script>
        (function () {
          const hostWindow = window.parent;
          const hostDocument = hostWindow && hostWindow.document;
          const installVersion = "native-overlay-uploader-v5";
          if (!hostWindow || !hostDocument || hostWindow.__lashforgeUploadReplaceInstalled === installVersion) {
            return;
          }
          hostWindow.__lashforgeUploadReplaceInstalled = installVersion;

          function hasImageFile(event) {
            const items = Array.from((event.dataTransfer && event.dataTransfer.items) || []);
            if (items.some((item) => item.kind === "file" && /^image\\//i.test(item.type || ""))) {
              return true;
            }
            return Array.from((event.dataTransfer && event.dataTransfer.files) || [])
              .some((file) => /^image\\//i.test(file.type || ""));
          }

          function getElementContainer(node) {
            return node && node.closest('div[data-testid="element-container"]');
          }

          function getPreviewContainer(marker) {
            let current = getElementContainer(marker);
            while (current && current.nextElementSibling) {
              current = current.nextElementSibling;
              if (current.querySelector && current.querySelector(".upload-replace-uploader-marker")) {
                return null;
              }
              const rect = current.getBoundingClientRect();
              if (rect.width > 24 && rect.height > 24) {
                return current;
              }
            }
            return null;
          }

          function getReplacementUploaderContainer(marker) {
            let current = getElementContainer(marker);
            while (current && current.nextElementSibling) {
              current = current.nextElementSibling;
              if (current.querySelector && current.querySelector(".upload-replace-uploader-marker")) {
                return current.nextElementSibling || null;
              }
            }
            return null;
          }

          function clearHotspots() {
            hostDocument.querySelectorAll(".upload-replace-hotspot").forEach((node) => node.remove());
            hostDocument.querySelectorAll(".upload-replace-overlay").forEach((node) => {
              node.classList.remove("upload-replace-overlay");
              node.style.left = "";
              node.style.top = "";
              node.style.width = "";
              node.style.height = "";
            });
          }

          function createReplaceHotspots() {
            clearHotspots();
            hostDocument.querySelectorAll(".upload-preview-root").forEach((marker) => {
              const preview = getPreviewContainer(marker);
              const uploader = getReplacementUploaderContainer(marker);
              if (!preview || !uploader) return;
              const rect = preview.getBoundingClientRect();
              if (rect.width < 24 || rect.height < 24) return;
              uploader.classList.add("upload-replace-overlay");
              uploader.style.left = `${rect.left}px`;
              uploader.style.top = `${rect.top}px`;
              uploader.style.width = `${rect.width}px`;
              uploader.style.height = `${rect.height}px`;
              const hotspot = hostDocument.createElement("div");
              hotspot.className = "upload-replace-hotspot";
              hotspot.style.left = `${rect.left}px`;
              hotspot.style.top = `${rect.top}px`;
              hotspot.style.width = `${rect.width}px`;
              hotspot.style.height = `${rect.height}px`;
              hostDocument.body.appendChild(hotspot);
            });
          }

          function enableReplaceLayer(event) {
            if (!hasImageFile(event)) return;
            createReplaceHotspots();
            hostDocument.body.classList.add("upload-file-dragging");
          }

          function disableReplaceLayer() {
            hostWindow.setTimeout(function () {
              hostDocument.body.classList.remove("upload-file-dragging");
              clearHotspots();
            }, 180);
          }

          hostDocument.addEventListener("dragenter", enableReplaceLayer, true);
          hostDocument.addEventListener("dragover", enableReplaceLayer, true);
          hostDocument.addEventListener("drop", disableReplaceLayer, true);
          hostDocument.addEventListener("dragend", disableReplaceLayer, true);
          hostDocument.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
              hostDocument.body.classList.remove("upload-file-dragging");
            }
          }, true);
          hostWindow.addEventListener("scroll", disableReplaceLayer, true);
          hostWindow.addEventListener("resize", disableReplaceLayer, true);
        })();
        </script>
        """,
        height=0,
    )


def inject_upload_reorder_support(
    *,
    APP_DIR,
    UPLOAD_REORDER_QUERY_KEY,
    components,
) -> None:
    script = (APP_DIR / "upload_priority_sort.js").read_text(encoding="utf-8")
    script = script.replace("__UPLOAD_REORDER_QUERY_KEY__", UPLOAD_REORDER_QUERY_KEY)
    components.html("<script>" + script + "</script>", height=0)
