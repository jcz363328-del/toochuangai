"""Xiaoha application and navigation rendering."""


def render_login_page(
    authenticate_requested_user,
    st,
):
    authenticate_requested_user()
    st.rerun()


def render_side_menu(
    current_feature,
    SIDE_MENU_FEATURE_GROUPS,
    XIAOHA_BALANCE_KEY,
    XIAOHA_DASHBOARD_KEY,
    get_visible_features,
    select_feature,
    st,
):
    with st.container(key="xiaoha_sidebar_brand"):
        st.markdown(
            '<div class="xiaoha-sidebar-brand"><strong>小哈</strong></div>',
            unsafe_allow_html=True,
        )

    visible_features = get_visible_features()
    features_by_key = {str(feature["key"]): feature for feature in visible_features}
    grouped_keys: set[str] = set()
    groups = []
    for group_name, feature_keys in SIDE_MENU_FEATURE_GROUPS:
        group_features = [features_by_key[key] for key in feature_keys if key in features_by_key]
        if group_features:
            groups.append((group_name, group_features))
            grouped_keys.update(str(feature["key"]) for feature in group_features)
    ungrouped_features = [feature for feature in visible_features if str(feature["key"]) not in grouped_keys]
    if ungrouped_features:
        groups.append(("其他功能", ungrouped_features))
    groups.append(("状态与数据", [
        {"key": XIAOHA_DASHBOARD_KEY, "name": "数据看板"},
        {"key": XIAOHA_BALANCE_KEY, "name": "余额管理"},
    ]))
    selected_key = str(st.session_state.selected_feature_key or "")
    for group_name, group_features in groups:
        with st.expander(
            group_name,
            expanded=any(str(feature["key"]) == selected_key for feature in group_features),
        ):
            for feature in group_features:
                st.button(
                    str(feature["name"]),
                    key=f"side_menu_feature_{feature['key']}",
                    use_container_width=True,
                    type="primary" if str(feature["key"]) == selected_key else "secondary",
                    on_click=select_feature,
                    args=(feature["key"],),
                )


def main(
    DEFAULT_ASPECT_RATIO,
    DEFAULT_MODEL,
    FEATURE_QUERY_KEY,
    XIAOHA_BALANCE_KEY,
    XIAOHA_DASHBOARD_KEY,
    XIAOHA_DEFAULT_FEATURE_KEY,
    authenticate_requested_user,
    consume_pending_outpaint_drag,
    consume_pending_upload_delete,
    consume_pending_upload_reorder,
    ensure_history_storage,
    ensure_jimeng_static_server,
    ensure_state,
    get_visible_features,
    inject_app_styles,
    inject_clipboard_paste_support,
    inject_upload_reorder_support,
    render_openrouter_feature,
    render_side_menu,
    render_xiaoha_balance_management,
    render_xiaoha_usage_dashboard,
    restore_auth_session,
    st,
    sync_background_jobs,
):
    st.set_page_config(page_title="小哈", layout="wide", initial_sidebar_state="expanded")
    ensure_state()
    restore_auth_session()
    sync_background_jobs()
    ensure_history_storage()
    jimeng_static_server = ensure_jimeng_static_server()
    if consume_pending_upload_delete():
        st.rerun()
    if consume_pending_upload_reorder():
        st.rerun()
    if consume_pending_outpaint_drag():
        st.rerun()
    inject_app_styles()
    inject_clipboard_paste_support()
    inject_upload_reorder_support()
    if not st.session_state.is_authenticated:
        authenticate_requested_user()
    visible_features = get_visible_features()
    feature_keys = {feature["key"] for feature in visible_features}
    allowed_page_keys = feature_keys | {XIAOHA_DASHBOARD_KEY, XIAOHA_BALANCE_KEY}
    if st.session_state.selected_feature_key not in allowed_page_keys:
        st.session_state.selected_feature_key = (
            XIAOHA_DEFAULT_FEATURE_KEY
            if XIAOHA_DEFAULT_FEATURE_KEY in feature_keys
            else (visible_features[0]["key"] if visible_features else XIAOHA_DASHBOARD_KEY)
        )
        if st.session_state.selected_feature_key:
            st.query_params[FEATURE_QUERY_KEY] = st.session_state.selected_feature_key

    current_feature = next(
        (
            feature
            for feature in visible_features
            if feature["key"] == st.session_state.selected_feature_key
        ),
        None,
    )
    if not bool(jimeng_static_server.get("started")):
        st.warning(
            "Agent 参考图静态服务启动失败，当前图片上传到 Agent 可能无法使用。"
            f"{str(jimeng_static_server.get('error') or '').strip()}"
        )
    with st.sidebar:
        render_side_menu(current_feature)
    with st.container():
        if st.session_state.selected_feature_key == XIAOHA_DASHBOARD_KEY:
            render_xiaoha_usage_dashboard()
        elif st.session_state.selected_feature_key == XIAOHA_BALANCE_KEY:
            render_xiaoha_balance_management()
        elif current_feature is not None:
            render_openrouter_feature(current_feature, model=DEFAULT_MODEL, aspect_ratio=DEFAULT_ASPECT_RATIO)
