"""Proxy VideoClaw and advertising diagnostics through the portal."""

from __future__ import annotations


def video_claw(
    subpath,
    *,
    _VIDEOCLAW_FRONTEND_URL,
    _can_access_ai_workspace,
    _ensure_videoclaw_started,
    app,
    render_template,
    request,
    requests,
):
    """进入受 AI 部权限保护的 VideoClaw 部署。"""
    if not _can_access_ai_workspace():
        return '仅AI部成员可访问AI部功能。', 403
    _ensure_videoclaw_started()
    upstream_path = '/ai/video-claw' + (('/' + str(subpath).lstrip('/')) if subpath else '')
    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in {'host', 'content-length', 'connection'}
    }
    try:
        upstream = requests.request(
            method=request.method,
            url=_VIDEOCLAW_FRONTEND_URL + upstream_path,
            params=list(request.args.items(multi=True)),
            data=request.get_data() or None,
            headers=headers,
            timeout=30,
        )
    except requests.RequestException:
        return render_template(
            '流程与AI部/videoclaw_unavailable.html',
            frontend_url=_VIDEOCLAW_FRONTEND_URL,
            message='VideoClaw 正在启动，请刷新页面重试。',
        ), 503
    excluded = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
    response = app.response_class(
        upstream.content,
        status=upstream.status_code,
        content_type=upstream.headers.get('Content-Type'),
    )
    for key, value in upstream.headers.items():
        if key.lower() not in excluded and key.lower() != 'content-type':
            response.headers[key] = value
    return response


def video_claw_backend(
    subpath,
    *,
    _VIDEOCLAW_BACKEND_URL,
    _can_access_ai_workspace,
    app,
    jsonify,
    request,
    requests,
    stream_with_context,
):
    if not _can_access_ai_workspace():
        return jsonify({'error': '仅AI部成员可访问AI部功能。'}), 403
    headers = {key: value for key, value in request.headers.items() if key.lower() not in {'host', 'content-length', 'connection'}}
    try:
        upstream = requests.request(
            request.method,
            _VIDEOCLAW_BACKEND_URL + '/' + subpath,
            params=list(request.args.items(multi=True)),
            data=request.get_data() or None,
            headers=headers,
            stream=True,
            timeout=(5, 300),
        )
    except requests.RequestException:
        return jsonify({'error': 'VideoClaw 后端暂不可用。'}), 503

    def chunks():
        try:
            yield from upstream.iter_content(chunk_size=1024)
        finally:
            upstream.close()

    response = app.response_class(stream_with_context(chunks()), status=upstream.status_code)
    excluded = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
    for key, value in upstream.headers.items():
        if key.lower() not in excluded:
            response.headers[key] = value
    response.call_on_close(upstream.close)
    response.headers['X-Accel-Buffering'] = 'no'
    return response


def ads_monitor_diagnostic_api(
    subpath,
    *,
    _ADS_MONITOR_API_PORT,
    _ensure_ads_monitor_api_started,
    _is_ads_monitor_api_reachable,
    app,
    jsonify,
    request,
    requests,
    time,
):
    if not _is_ads_monitor_api_reachable(timeout=0.8):
        _ensure_ads_monitor_api_started()
        for _ in range(24):
            time.sleep(0.25)
            if _is_ads_monitor_api_reachable(timeout=0.5):
                break
        else:
            return jsonify({
                'error': {
                    'code': 'ADS_MONITOR_SERVICE_STARTING',
                    'message': '广告诊断服务正在启动，请稍后刷新。',
                }
            }), 503

    upstream_path = '/api/diagnostic'
    if subpath:
        upstream_path += '/' + str(subpath).lstrip('/')
    upstream_headers = {
        'Accept': request.headers.get('Accept') or 'application/json',
    }
    if request.method == 'POST':
        upstream_headers['Content-Type'] = request.headers.get('Content-Type') or 'application/json'
        upstream_headers['Origin'] = 'http://127.0.0.1:4173'
        control_token = str(request.headers.get('X-SP-Control-Token') or '').strip()
        if control_token:
            upstream_headers['X-SP-Control-Token'] = control_token

    try:
        upstream = requests.request(
            method=request.method,
            url=f'http://127.0.0.1:{_ADS_MONITOR_API_PORT}{upstream_path}',
            params=list(request.args.items(multi=True)),
            data=request.get_data() if request.method == 'POST' else None,
            headers=upstream_headers,
            timeout=70,
        )
    except requests.RequestException:
        return jsonify({
            'error': {
                'code': 'ADS_MONITOR_SERVICE_UNAVAILABLE',
                'message': '广告诊断服务暂时不可用，请稍后刷新。',
            }
        }), 503

    response = app.response_class(
        upstream.content,
        status=upstream.status_code,
        content_type=upstream.headers.get('Content-Type', 'application/json; charset=utf-8'),
    )
    response.headers['Cache-Control'] = 'no-store'
    return response
