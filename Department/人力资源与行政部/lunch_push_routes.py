"""Expose lunch push preview, send and image endpoints."""

from __future__ import annotations


def lunch_push_page(
    *,
    _can_access_ai_workspace,
    env,
    render_template,
):
    if not _can_access_ai_workspace():
        return '仅AI部成员可访问AI部功能。', 403
    from Department.人力资源与行政部.lunch_push import GROUPS, next_trigger
    return render_template('人力资源与行政部/lunch_push.html', groups=GROUPS,
        next_run=next_trigger().strftime('%Y-%m-%d %H:%M'),
        enabled=env('TC_BACKGROUND_JOBS', '1') == '1' and env('LUNCH_PUSH_ENABLED', '1') == '1')


def lunch_push_api(
    *,
    _can_access_ai_workspace,
    app,
    jsonify,
    lunch_push,
    request,
    url_for,
):
    if not _can_access_ai_workspace():
        return jsonify(success=False, message='仅AI部成员可访问AI部功能。'), 403
    try:
        if request.method == 'POST':
            payload = request.get_json(silent=True) or {}
            if payload.get('action') not in ('test', 'send'):
                return jsonify(success=False, message='不支持的操作'), 400
            result = lunch_push.run_once(test=payload['action'] == 'test')
            success = all(item['status'] != 'failed' for item in result)
            return jsonify(success=success, results=result), 200 if success else 502
        entries = lunch_push.preview()
        for entry in entries:
            entry.pop('card', None)
            if entry['image']:
                entry['image'] = url_for('lunch_push_image', filename=entry['image'])
        return jsonify(success=True, entries=entries, records=lunch_push.records(),
                       scheduler_error=lunch_push.last_error)
    except Exception:
        app.logger.exception('订餐推送操作失败')
        return jsonify(success=False, message='订餐推送操作失败，请查看服务日志。'), 500


def lunch_push_image(
    filename,
    *,
    _can_access_ai_workspace,
    abort,
    lunch_push,
    send_file,
):
    if not _can_access_ai_workspace():
        return '无权访问', 403
    from Department.人力资源与行政部.lunch_push import now_local
    if filename not in {f'{scope}_{meal}_grid.png' for scope in ('all', 'tk') for meal in ('堂食', '盒饭')}:
        abort(404)
    path = lunch_push.storage / 'images' / now_local().date().isoformat() / filename
    if not path.is_file():
        abort(404)
    response = send_file(path, mimetype='image/png', max_age=0)
    response.headers['Cache-Control'] = 'no-store'
    return response
