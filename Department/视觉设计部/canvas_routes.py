"""Provide authenticated infinite canvas bootstrap configuration."""

from __future__ import annotations


def api_infinite_canvas_bootstrap_config(
    *,
    _INFINITE_CANVAS_LEGACY_IMAGE_MODELS,
    _INFINITE_CANVAS_OMNIAKEY_IMAGE_MODELS,
    _INFINITE_CANVAS_OMNIAKEY_MODEL,
    _INFINITE_CANVAS_OPENROUTER_IMAGE_MODELS,
    _INFINITE_CANVAS_OPENROUTER_TEXT_MODELS,
    env,
    jsonify,
):
    api_key = str(env('OPENROUTER_API_KEY') or '').strip()
    omnia_api_key = str(env('OMNIAKEY_API_KEY') or '').strip()
    omnia_base_url = str(env('OMNIAKEY_BASE_URL') or 'https://api.omniakey.com').strip().rstrip('/')
    if omnia_base_url.lower().endswith('/v1'):
        omnia_base_url = omnia_base_url[:-3]
    if not api_key and not omnia_api_key:
        return jsonify({
            'success': False,
            'message': 'OPENROUTER_API_KEY 与 OMNIAKEY_API_KEY 均未配置',
        }), 503

    legacy_nano_model = 'google/gemini-nano-banana-2.1'
    legacy_image_models = [legacy_nano_model, *_INFINITE_CANVAS_LEGACY_IMAGE_MODELS]
    omnia_image_models = list(_INFINITE_CANVAS_OMNIAKEY_IMAGE_MODELS)
    openrouter_image_models = list(_INFINITE_CANVAS_OPENROUTER_IMAGE_MODELS)
    text_models = list(_INFINITE_CANVAS_OPENROUTER_TEXT_MODELS)
    legacy_channel = {
        'id': 'xiaoha-openrouter',
        'name': '小哈 OpenRouter',
        'baseUrl': 'https://openrouter.ai/api/v1',
        'apiKey': api_key,
        'apiFormat': 'openai',
        'models': [*legacy_image_models, *text_models],
    }
    channels = [
        {
            'id': 'xiaoha-omnia',
            'name': '小哈 OmniaKey',
            'baseUrl': f'{omnia_base_url}/v1',
            'apiKey': omnia_api_key,
            'apiFormat': 'openai',
            'models': omnia_image_models,
        },
        {
            'id': 'xiaoha-openrouter',
            'name': '小哈 OpenRouter',
            'baseUrl': 'https://openrouter.ai/api/v1',
            'apiKey': api_key,
            'apiFormat': 'openai',
            'models': openrouter_image_models + text_models,
        },
    ]
    image_models = omnia_image_models + (openrouter_image_models if api_key else [])
    available_text_models = text_models if api_key else []
    return jsonify({
        'success': True,
        'config': {
            'configVersion': '2026-11-06-omnia-no-qwen',
            'channel': legacy_channel,
            'channels': channels,
            'imageModel': legacy_nano_model,
            'imageModelNext': _INFINITE_CANVAS_OMNIAKEY_MODEL,
            'textModel': available_text_models[0] if available_text_models else '',
            'videoModel': '',
            'audioModel': '',
            'imageModels': legacy_image_models if api_key else [],
            'imageModelsNext': image_models,
            'textModels': available_text_models,
            'videoModels': [],
            'audioModels': [],
        },
    })
