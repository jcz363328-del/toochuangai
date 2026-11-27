"""Single-image reference analysis and text-only composition for A+ canvas."""
import json
from urllib.parse import parse_qs

from Department.视觉设计部.xiaoha.multi_reference_composer import build_analysis_prompt, parse_analysis


def run_node(site, payload, username):
    action = payload.get('action')
    prompt = str(payload.get('prompt') or '').strip()
    if len(prompt) > 30000:
        raise ValueError('组合文案过长，请缩短到30000字以内。')
    images = payload.get('images') or []
    if not isinstance(images, list):
        raise ValueError('图片参数无效。')
    if action == 'analyze':
        if len(images) != 1:
            raise ValueError('每个反推节点只能提交一张参考图。')
        decoded = site.decode_data_url(str(images[0]))
        if not decoded or not decoded[1].startswith('image/'):
            raise ValueError('请上传可读取的参考图片。')
        data, mime = decoded
        response = site.call_openrouter(
            model=site.IMAGE_SMART_ANALYSIS_MODEL,
            prompt=build_analysis_prompt(prompt),
            uploaded_files=[{'data': data, 'name': 'reference.png', 'type': mime}],
            output_mode='text', aspect_ratio=site.DEFAULT_ASPECT_RATIO,
        )
        analysis = parse_analysis(response.get('text'))
        return {'success': True, 'analysis': analysis, 'text': analysis['prompt']}
    if action != 'generate':
        raise ValueError('不支持的参考节点操作。')
    if images:
        raise ValueError('组合生图只接收已选择的逆向文案，不接收参考图。')
    if not prompt:
        raise ValueError('请连接至少一份逆向文案。')
    feature = site.get_feature_by_key(site.MULTI_REFERENCE_COMPOSER_FEATURE_KEY)
    result = site.run_feature_job({
        'feature': feature, 'composer_action': 'generate', 'model': site.NANO_BANANA_MODEL,
        'prompt': '根据以下选定文案生成一张完整的商业画面，统一光影、透视、尺度和材质；'
                  '只采用选定内容，不添加未选元素，不做拼贴或分栏。\n\n' + prompt,
        'uploaded_files': [], 'output_mode': 'image', 'max_output_images': 1,
        'aspect_ratio': '4:3', 'account_name': username,
    })
    originals = []
    for url in result.get('images') or []:
        data, mime = site.load_image_bytes_from_url(str(url))
        originals.append(site.image_bytes_to_data_url(data, mime or 'image/png'))
    if not originals:
        raise RuntimeError('没有返回生成图片，请检查任务后重试。')
    return {'success': True, 'images': originals}


def serve(handler, site, query_text):
    # Authentication and the shared request limit are enforced by the route wrapper.
    username = (parse_qs(query_text).get(site.AUTH_QUERY_USER_KEY) or [''])[0].strip()
    length = int(handler.headers.get('Content-Length') or 0)
    if not 0 < length <= site.INFINITE_CANVAS_IMAGE_FEATURE_MAX_REQUEST_BYTES:
        handler.send_json({'success': False, 'message': '请求为空或图片超过80MB'}, status=413)
        return
    payload = json.loads(handler.rfile.read(length).decode('utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('节点参数无效。')
    handler.send_json(run_node(site, payload, username))
