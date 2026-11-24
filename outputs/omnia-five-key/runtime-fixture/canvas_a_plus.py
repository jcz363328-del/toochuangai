"""A+ canvas nodes reuse the existing A+ job implementations and history storage."""
FEATURE_KEYS = {
    'main_image_a_plus', 'a_plus_reference_lab', 'a_plus_style_model_replace',
    'a_plus_first_screen_selling_points', 'amazon_to_walmart_a_plus',
    'a_plus_hero_style_reverse', 'amazon_a_plus',
}


def build_context(site, feature, files, prompt, username):
    key = feature['key']
    minimum = int(feature.get('min_images') or 1)
    maximum = int(feature.get('max_input_images') or 10)
    if key == 'amazon_to_walmart_a_plus':
        maximum = 1
    if not minimum <= len(files) <= maximum:
        raise ValueError(f"{feature['name']}需要连接{minimum}到{maximum}张图片，按连接顺序确定主体和参考。")
    layout = site.get_main_image_a_plus_layout()
    context = {
        'feature': dict(feature), 'model': site.NANO_BANANA_MODEL,
        'prompt': site.build_prompt(feature, prompt, site.DEFAULT_ASPECT_RATIO, ''),
        'custom_prompt': prompt, 'uploaded_files': files,
        'output_mode': 'image', 'max_output_images': 1,
        'target_size': tuple(feature.get('target_size') or layout['target_size']),
        'aspect_ratio': site.DEFAULT_ASPECT_RATIO, 'account_name': username,
        'main_image_a_plus_mode': site.MAIN_IMAGE_A_PLUS_MODE_FREE,
        'hero_reverse_count': 1, 'hero_reverse_size': [0, 0],
        'a_plus_first_screen_requirements': prompt,
        'a_plus_first_screen_keep_height': 0,
    }
    if key == 'a_plus_reference_lab':
        style = site.resolve_a_plus_reference_style('auto', prompt)
        context['a_plus_reference_lab_style_key'] = style
        context['a_plus_source_repair_enabled'] = False
        context['prompt'] += "\n" + site.build_a_plus_reference_lab_instruction(
            style, layout['key'], len(files), 0, prompt, auto_repair_crops=False)
    if key == 'a_plus_first_screen_selling_points':
        context['target_size'] = site.get_uploaded_input_dimensions(files[0])
    return context


def run_node(site, feature, files, prompt, username):
    if feature['key'] not in FEATURE_KEYS:
        raise ValueError('不支持的A+画布功能')
    context = build_context(site, feature, files, prompt, username)
    if feature['key'] == 'a_plus_hero_style_reverse':
        analysis = site.analyze_hero_style_reverse_reference(files[0], prompt)
        context['prompt'] = str(analysis.get('prompt') or '').strip()
        if not context['prompt']:
            raise RuntimeError('首屏风格逆向未返回可用提示词')
    result = site.run_feature_job(context)
    images = list(result.get('images') or [])
    if not images:
        raise RuntimeError('A+功能未返回图片，请查看任务错误后重试。')
    return result


def prepare_psd_download(site, result, username):
    import uuid
    from pathlib import Path
    from urllib.parse import urlencode
    original = result.get('psd_path')
    if not original:
        return ''
    name = uuid.uuid4().hex + '.psd'
    directory = site.ensure_feature_output_dir('a_plus_canvas')
    (directory / name).write_bytes(Path(original).read_bytes())
    return '/infinite-canvas/api/a-plus-psd?' + urlencode({
        site.AUTH_QUERY_USER_KEY: username, site.AUTH_QUERY_TOKEN_KEY: site.build_auth_token(username),
        'file': name, 'asset_token': site.build_auth_token(username + ':a_plus_canvas:' + name),
    })


def serve_psd(handler, site, query_text):
    import hmac
    import re
    from urllib.parse import parse_qs
    query = parse_qs(query_text)
    username = (query.get(site.AUTH_QUERY_USER_KEY) or [''])[0]
    token = (query.get(site.AUTH_QUERY_TOKEN_KEY) or [''])[0]
    name = (query.get('file') or [''])[0]
    asset_token = (query.get('asset_token') or [''])[0]
    if (not username or not re.fullmatch(r'[0-9a-f]{32}\.psd', name)
            or not hmac.compare_digest(token, site.build_auth_token(username))
            or not hmac.compare_digest(asset_token, site.build_auth_token(username + ':a_plus_canvas:' + name))):
        handler.send_json({'success': False, 'message': '无效的PSD下载凭证'}, status=403)
        return
    path = site.ensure_feature_output_dir('a_plus_canvas') / name
    if not path.is_file():
        handler.send_json({'success': False, 'message': 'PSD文件不存在'}, status=404)
        return
    handler.send_response(200)
    handler.send_header('Content-Type', 'image/vnd.adobe.photoshop')
    handler.send_header('Content-Length', str(path.stat().st_size))
    handler.send_header('Content-Disposition', 'attachment; filename="A-plus.psd"')
    handler.send_header('Cache-Control', 'private, no-store')
    handler.end_headers()
    with path.open('rb') as stream:
        import shutil
        shutil.copyfileobj(stream, handler.wfile)
