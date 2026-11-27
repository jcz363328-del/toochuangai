"""Resolve Xiaoha login, selected feature and account state."""

from __future__ import annotations


def load_login_accounts(
    *,
    DEFAULT_LOGIN_ACCOUNTS,
    load_config_namespace,
) -> dict[str, str]:
    namespace = load_config_namespace()
    configured_accounts = namespace.get("login_accounts")
    if isinstance(configured_accounts, dict):
        accounts = {
            str(username).strip(): str(password)
            for username, password in configured_accounts.items()
            if str(username).strip()
        }
        if accounts:
            return accounts
    return dict(DEFAULT_LOGIN_ACCOUNTS)


def build_auth_token(
    username,
    *,
    AUTH_TOKEN_SALT,
    hashlib,
) -> str:
    normalized_username = str(username or "").strip().lower()
    raw = f"{AUTH_TOKEN_SALT}:{normalized_username}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def persist_auth_session(
    username,
    *,
    AUTH_QUERY_TOKEN_KEY,
    AUTH_QUERY_USER_KEY,
    build_auth_token,
    st,
) -> None:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        return
    st.query_params[AUTH_QUERY_USER_KEY] = normalized_username
    st.query_params[AUTH_QUERY_TOKEN_KEY] = build_auth_token(normalized_username)


def clear_persisted_auth_session(
    *,
    AUTH_QUERY_TOKEN_KEY,
    AUTH_QUERY_USER_KEY,
    st,
) -> None:
    try:
        del st.query_params[AUTH_QUERY_USER_KEY]
    except Exception:
        pass
    try:
        del st.query_params[AUTH_QUERY_TOKEN_KEY]
    except Exception:
        pass


def get_requested_feature_key(
    *,
    FEATURE_QUERY_KEY,
    st,
) -> str:
    return str(st.query_params.get(FEATURE_QUERY_KEY, "")).strip()


def select_feature(
    feature_key,
    *,
    FEATURE_QUERY_KEY,
    get_requested_feature_key,
    st,
) -> None:
    normalized_key = str(feature_key or "").strip()
    if not normalized_key:
        return
    st.session_state.selected_feature_key = normalized_key
    if get_requested_feature_key() != normalized_key:
        st.query_params[FEATURE_QUERY_KEY] = normalized_key


def set_side_menu_visible(
    visible,
    *,
    st,
) -> None:
    st.session_state.side_menu_visible = bool(visible)


def clear_query_param(
    param_key,
    *,
    st,
) -> None:
    try:
        del st.query_params[param_key]
    except Exception:
        pass


def get_requested_auth_username(
    *,
    AUTH_QUERY_USER_KEY,
    st,
) -> str:
    candidate_keys = (
        AUTH_QUERY_USER_KEY,
        "feishu_user_name",
        "user_name",
        "name",
    )
    for key in candidate_keys:
        value = str(st.query_params.get(key, "")).strip()
        if value:
            return value
    return ""


def authenticate_requested_user(
    *,
    AUTH_QUERY_TOKEN_KEY,
    build_auth_token,
    clear_query_param,
    get_requested_auth_username,
    persist_auth_session,
    st,
) -> None:
    requested_username = get_requested_auth_username()
    if requested_username:
        normalized_username = requested_username
        query_token = str(st.query_params.get(AUTH_QUERY_TOKEN_KEY, "")).strip()
        if query_token and query_token != build_auth_token(normalized_username):
            clear_query_param(AUTH_QUERY_TOKEN_KEY)
        st.session_state.is_authenticated = True
        st.session_state.auth_username = normalized_username
        st.session_state.login_username = normalized_username
        st.session_state.login_error = ""
        persist_auth_session(normalized_username)
        return
    st.session_state.is_authenticated = True
    st.session_state.auth_username = "访客"
    st.session_state.login_username = "访客"
    st.session_state.login_error = ""


def restore_auth_session(
    *,
    authenticate_requested_user,
    st,
) -> None:
    if st.session_state.get("is_authenticated"):
        return
    authenticate_requested_user()


def get_current_account_name(*, st) -> str:
    return str(st.session_state.get("auth_username") or "admin").strip() or "admin"
