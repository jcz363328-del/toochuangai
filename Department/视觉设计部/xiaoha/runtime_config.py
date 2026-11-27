"""Resolve Xiaoha model, storage and gateway settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_infinite_canvas_url(
    public_app_url,
    static_port,
    username,
    workspace,
    *,
    AUTH_QUERY_TOKEN_KEY,
    AUTH_QUERY_USER_KEY,
    DEFAULT_PUBLIC_APP_URL,
    INFINITE_CANVAS_BUILD_DIR,
    INFINITE_CANVAS_STATIC_ROUTE_PREFIX,
    build_auth_token,
    os,
    urllib,
) -> str:
    static_port = int(os.getenv("JIMENG_PUBLIC_PORT") or static_port)
    raw_url = str(public_app_url or "").strip() or DEFAULT_PUBLIC_APP_URL
    parsed = urllib.parse.urlsplit(raw_url)
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname or "www.toochuangai.com"
    netloc = hostname
    default_port = 443 if scheme == "https" else 80
    if os.getenv("TC_SINGLE_PORT") == "1":
        netloc = parsed.netloc
    elif static_port and static_port != default_port:
        netloc = f"{hostname}:{static_port}"
    normalized_username = str(username or "访客").strip() or "访客"
    try:
        canvas_version = str((INFINITE_CANVAS_BUILD_DIR / "index.html").stat().st_mtime_ns)
    except OSError:
        canvas_version = "unbuilt"
    query = urllib.parse.urlencode(
        {
            AUTH_QUERY_USER_KEY: normalized_username,
            AUTH_QUERY_TOKEN_KEY: build_auth_token(normalized_username),
            "embed": "true",
            "build": canvas_version,
            **({"workspace": "a_plus"} if workspace == "a_plus" else {}),
        }
    )
    return urllib.parse.urlunsplit(
        (scheme, netloc, f"{INFINITE_CANVAS_STATIC_ROUTE_PREFIX}/canvas", query, "")
    )


def load_config_namespace(
    *,
    APP_DIR,
    Any,
    image_site_config_namespace,
    os,
) -> dict[str, Any]:
    if os.getenv("TC_CONTAINER_MODE") == "1":
        return image_site_config_namespace()
    config_path = APP_DIR / "config.py"
    if not config_path.exists():
        return {}

    namespace: dict[str, Any] = {}
    try:
        exec(config_path.read_text(encoding="utf-8"), namespace)
    except Exception:
        return {}
    return namespace


def load_api_key(
    *,
    load_config_namespace,
    os,
) -> str:
    env_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key

    namespace = load_config_namespace()
    if not namespace:
        return ""

    for key_name in ("open_routher_api_key", "openrouter_api_key", "OPENROUTER_API_KEY"):
        value = str(namespace.get(key_name, "")).strip()
        if value:
            return value

    return ""


def load_omnia_api_key(
    *,
    current_omnia_credential,
    load_config_namespace,
    os,
) -> str:
    credential = current_omnia_credential()
    if credential is not None:
        return credential.api_key
    env_key = os.getenv("OMNIAKEY_API_KEY", "").strip()
    if env_key:
        return env_key

    namespace = load_config_namespace()
    for key_name in ("omnia_api_key", "omnia_key_api_key", "OMNIAKEY_API_KEY"):
        value = str(namespace.get(key_name, "")).strip()
        if value:
            return value
    return ""


def load_ark_api_key(
    *,
    load_config_namespace,
    os,
) -> str:
    env_key = os.getenv("ARK_API_KEY", "").strip()
    if env_key:
        return env_key

    namespace = load_config_namespace()
    if not namespace:
        return ""

    for key_name in ("ark_api_key", "ARK_API_KEY"):
        value = str(namespace.get(key_name, "")).strip()
        if value:
            return value
    return ""


def load_runtime_settings(
    *,
    DEFAULT_JIMENG_STATIC_PORT,
    DEFAULT_SERVER_ADDRESS,
    DEFAULT_SERVER_PORT,
    build_jimeng_static_base_url,
    load_config_namespace,
) -> dict[str, Any]:
    namespace = load_config_namespace()
    server_address = str(namespace.get("server_address") or DEFAULT_SERVER_ADDRESS).strip() or DEFAULT_SERVER_ADDRESS
    try:
        server_port = int(namespace.get("server_port") or DEFAULT_SERVER_PORT)
    except Exception:
        server_port = DEFAULT_SERVER_PORT
    try:
        jimeng_static_port = int(namespace.get("jimeng_static_port") or DEFAULT_JIMENG_STATIC_PORT)
    except Exception:
        jimeng_static_port = DEFAULT_JIMENG_STATIC_PORT
    public_app_url = str(namespace.get("public_app_url") or "").strip().rstrip("/")
    if not public_app_url:
        public_app_url = f"http://www.toochuangai.com:{server_port}/lashforge"
    jimeng_public_upload_base_url = str(namespace.get("jimeng_public_upload_base_url") or "").strip().rstrip("/")
    if not jimeng_public_upload_base_url:
        jimeng_public_upload_base_url = build_jimeng_static_base_url(public_app_url, jimeng_static_port)
    return {
        "server_address": server_address,
        "server_port": server_port,
        "jimeng_static_port": jimeng_static_port,
        "public_app_url": public_app_url,
        "jimeng_public_upload_base_url": jimeng_public_upload_base_url,
    }


def get_external_request_kwargs(
    timeout,
    use_proxy,
    *,
    Any,
    REQUEST_PROXIES,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"timeout": timeout}
    if use_proxy:
        kwargs["proxies"] = REQUEST_PROXIES
    return kwargs


def get_image_matting_model_path(
    *,
    IMAGE_MATTING_DEFAULT_MODEL_PATH,
    Path,
    load_runtime_settings,
    os,
) -> Path:
    configured_path = str(os.environ.get("IMAGE_MATTING_MODEL_PATH") or "").strip()
    if not configured_path:
        try:
            configured_path = str(load_runtime_settings().get("image_matting_model_path") or "").strip()
        except Exception:
            configured_path = ""
    if configured_path:
        return Path(configured_path).expanduser()
    return IMAGE_MATTING_DEFAULT_MODEL_PATH
