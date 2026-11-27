"""Amazon message assistant configuration and routes."""

from __future__ import annotations


def _build_amazon_reply_service(
    *,
    AI_RUNTIME_CONFIG,
    API_BASE_URL,
    OPENAI_API_KEY,
    _OPENAI_TEXT_MODEL,
    _get_env_float,
    _get_env_int,
    _normalize_chat_completions_url,
    os,
    sql_server_config,
):
    from Department.运营部.amazon_reply_service import AmazonReplyService, SiliconFlowConfig, SqlServerConfig, normalize_model

    db_defaults = sql_server_config(include_port=True)
    db_config = SqlServerConfig(
        server=str(db_defaults.get('server') or ''),
        port=int(db_defaults.get('port') or 1433),
        database=str(db_defaults.get('database') or ''),
        user=str(db_defaults.get('user') or ''),
        password=str(db_defaults.get('password') or ''),
    )
    shared_api_key = (
        os.environ.get('SILICONFLOW_API_KEY')
        or os.environ.get('OPENAI_API_KEY')
        or OPENAI_API_KEY
        or AI_RUNTIME_CONFIG.get('api_key')
        or ''
    )
    shared_base_url = (
        os.environ.get('SILICONFLOW_BASE_URL')
        or os.environ.get('OPENAI_BASE_URL')
        or API_BASE_URL
        or AI_RUNTIME_CONFIG.get('base_url')
        or 'https://api.siliconflow.cn/v1'
    )
    ai_config = SiliconFlowConfig(
        api_key=str(shared_api_key or '').strip(),
        model=normalize_model(os.environ.get('SILICONFLOW_MODEL') or os.environ.get('OPENAI_TEXT_MODEL') or _OPENAI_TEXT_MODEL),
        base_url=_normalize_chat_completions_url(shared_base_url),
        temperature=_get_env_float('SILICONFLOW_TEMPERATURE', 0.2),
        max_tokens=_get_env_int('AMAZON_REPLY_MAX_TOKENS', _get_env_int('SILICONFLOW_MAX_TOKENS', 450)),
        timeout_seconds=_get_env_int('AMAZON_REPLY_TIMEOUT_SECONDS', _get_env_int('SILICONFLOW_TIMEOUT_SECONDS', 35)),
        retry_count=_get_env_int('AMAZON_REPLY_RETRY_COUNT', _get_env_int('SILICONFLOW_RETRY_COUNT', 0)),
    )
    return AmazonReplyService(db_config, ai_config)


def amazon_reply_agent(
    *,
    render_template,
    request,
    session,
    url_for,
):
    user_name = session.get('feishu_user_name', '用户')
    source = str(request.args.get('source') or '').strip()
    return_url_map = {
        'operation_dept_1': url_for('operation_dept_1'),
        'operation_dept_2': url_for('operation_dept_2'),
        'operation_dept_3': url_for('operation_dept_3'),
        'operation_dept_6': url_for('operation_dept_6'),
        'operation_dept_7': url_for('operation_dept_7'),
    }
    return render_template(
        '运营部/amazon_reply_agent.html',
        user_name=user_name,
        return_url=return_url_map.get(source) or url_for('ai_modules'),
        return_label=('返回运营功能' if source in return_url_map else '返回AI功能')
    )


def api_ai_amazon_reply_generate(
    *,
    _get_amazon_reply_service,
    jsonify,
    request,
):
    try:
        data = request.get_json(silent=True) or {}
        buyer_question = str(data.get('buyerQuestion') or data.get('buyer_question') or '').strip()
        extra_context = str(data.get('extraContext') or data.get('extra_context') or '').strip()
        if not buyer_question:
            return jsonify({'success': False, 'message': '请先填写买家站内信内容'}), 400
        if len(buyer_question) > 5000 or len(extra_context) > 5000:
            return jsonify({'success': False, 'message': '输入内容过长，请精简后再生成'}), 400
        result = _get_amazon_reply_service().generate_reply(
            buyer_question=buyer_question,
            extra_context=extra_context,
        )
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500


def _amazon_reply_text_list(
    value,
    *,
    re,
):
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r'[\n,，;；]+', str(value or ''))
    result = []
    seen = set()
    for item in raw_items:
        text = str(item or '').strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _amazon_reply_rule_type(raw_type):
    normalized = str(raw_type or '').strip().lower()
    from Department.运营部.amazon_reply_service import RULE_TYPE_PROHIBITED, RULE_TYPE_SENSITIVE

    if normalized in {'prohibited', 'forbidden', 'ban', '禁用词'}:
        return RULE_TYPE_PROHIBITED
    if normalized in {'sensitive', 'sensitive_phrase', '敏感词', '敏感短语'}:
        return RULE_TYPE_SENSITIVE
    raise ValueError('规则类型只能是禁用词或敏感词')


def api_ai_amazon_reply_rules(
    *,
    _get_amazon_reply_service,
    jsonify,
):
    try:
        data = _get_amazon_reply_service().list_management_items()
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500


def api_ai_amazon_reply_add_rule(
    *,
    _amazon_reply_rule_type,
    _get_amazon_reply_service,
    jsonify,
    request,
):
    try:
        data = request.get_json(silent=True) or {}
        rule_type = _amazon_reply_rule_type(data.get('ruleType') or data.get('type'))
        content = str(data.get('content') or '').strip()
        safe_hint = str(data.get('safeHint') or data.get('safe_hint') or '').strip()
        item = _get_amazon_reply_service().add_rule(rule_type, content, safe_hint)
        return jsonify({'success': True, 'data': item})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400


def api_ai_amazon_reply_delete_rule(
    rule_id,
    *,
    _get_amazon_reply_service,
    jsonify,
):
    try:
        _get_amazon_reply_service().disable_rule(rule_id)
        return jsonify({'success': True, 'message': '已删除'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500


def api_ai_amazon_reply_add_scenario(
    *,
    _amazon_reply_text_list,
    _get_amazon_reply_service,
    jsonify,
    request,
):
    try:
        data = request.get_json(silent=True) or {}
        item = _get_amazon_reply_service().add_scenario(
            title=str(data.get('title') or '').strip(),
            keywords=_amazon_reply_text_list(data.get('keywords')),
            buyer_examples=_amazon_reply_text_list(data.get('buyerExamples') or data.get('buyer_examples')),
            seller_reply_en=str(data.get('sellerReplyEn') or data.get('seller_reply_en') or '').strip(),
            seller_reply_zh=str(data.get('sellerReplyZh') or data.get('seller_reply_zh') or '').strip(),
            internal_notes=str(data.get('internalNotes') or data.get('internal_notes') or '').strip(),
        )
        return jsonify({'success': True, 'data': item})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400


def api_ai_amazon_reply_delete_scenario(
    scenario_id,
    *,
    _get_amazon_reply_service,
    jsonify,
):
    try:
        _get_amazon_reply_service().disable_scenario(scenario_id)
        return jsonify({'success': True, 'message': '已删除'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500
