"""Build Xiaoha links through the portal gateway."""

from __future__ import annotations


def _build_lashforge_auth_token(
    user_name,
    *,
    _LASHFORGE_AUTH_TOKEN_SALT,
    hashlib,
):
    normalized_name = str(user_name or '').strip().lower()
    if not normalized_name:
        return ''
    raw = f"{_LASHFORGE_AUTH_TOKEN_SALT}:{normalized_name}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _get_lashforge_public_base_url(
    *,
    _LASHFORGE_PUBLIC_URL,
    env,
    os,
    request,
    urlparse,
):
    if env("TC_SINGLE_PORT") == "1":
        return '/lashforge'
    env_url = str(os.environ.get("LASHFORGE_PUBLIC_URL") or "").strip().rstrip('/')
    if env_url:
        return env_url

    fallback_url = (_LASHFORGE_PUBLIC_URL or "http://www.toochuangai.com:8501/lashforge").rstrip('/')
    fallback_parts = urlparse(fallback_url)
    scheme = fallback_parts.scheme or "http"
    port = fallback_parts.port or 8501
    host_text = str(
        request.headers.get('X-Forwarded-Host')
        or request.headers.get('Host')
        or request.host
        or ""
    ).split(',')[0].strip()

    if not host_text:
        return fallback_url

    parsed_host = urlparse('//' + host_text)
    hostname = parsed_host.hostname or host_text.split(':')[0].strip()
    if not hostname:
        return fallback_url
    if ':' in hostname and not hostname.startswith('['):
        hostname = f'[{hostname}]'
    return f"{scheme}://{hostname}:{port}/lashforge"


def _build_lashforge_entry_url(
    user_name,
    *,
    _build_lashforge_auth_token,
    _get_lashforge_public_base_url,
    _normalize_feishu_user_name,
    quote,
):
    base_url = _get_lashforge_public_base_url().rstrip('/')
    normalized_name = _normalize_feishu_user_name(user_name, fallback='')
    if not normalized_name:
        return f"{base_url}/?embed=true"
    auth_token = _build_lashforge_auth_token(normalized_name)
    return f"{base_url}/?auth_user={quote(normalized_name)}&auth_token={auth_token}&embed=true"


def visual_design_image_tool(
    *,
    _build_lashforge_entry_url,
    _ensure_lashforge_watchdog_started,
    _is_feishu_request,
    _is_lashforge_reachable,
    _normalize_feishu_user_name,
    redirect,
    render_template,
    request,
    session,
):
    user_name = _normalize_feishu_user_name(session.get('feishu_user_name', ''), fallback='访客')
    _ensure_lashforge_watchdog_started()
    lashforge_url = _build_lashforge_entry_url(user_name)
    if _is_feishu_request() and request.args.get('embed') != '1':
        if _is_lashforge_reachable(timeout=0.8):
            return redirect(lashforge_url)
        return render_template(
            '视觉设计部/lashforge_launch.html',
            user_name=user_name,
            lashforge_url=lashforge_url,
        )
    return render_template(
        '视觉设计部/lashforge_embed.html',
        user_name=user_name,
        lashforge_url=lashforge_url,
    )


def visual_design_image_tool_status(
    *,
    _ensure_lashforge_watchdog_started,
    _is_lashforge_reachable,
    jsonify,
):
    ready = _is_lashforge_reachable(timeout=1)
    if not ready:
        _ensure_lashforge_watchdog_started()
    return jsonify({'ready': ready})
