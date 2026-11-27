"""Report editor templates, drafting and assistant interactions."""

from __future__ import annotations


def api_xiaotu_moban_list(
    *,
    jsonify,
    session,
    sf_db,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    try:
        sql_text = f"""
            SELECT XingMing, Moban, NeiRong, RiQi
            FROM baogao_moban
            ORDER BY RiQi DESC, XingMing ASC, Moban ASC
        """
        rows = sf_db(sql_text) or []
        out = []
        for row in rows:
            if isinstance(row, dict):
                one = {
                    'xingming': str(row.get('XingMing') or row.get('xingming') or '').strip(),
                    'moban': str(row.get('Moban') or row.get('moban') or '').strip(),
                    'neirong': str(row.get('NeiRong') or row.get('neirong') or '').strip(),
                    'riqi': str(row.get('RiQi') or row.get('riqi') or '').strip(),
                }
            else:
                values = list(row) if isinstance(row, (list, tuple)) else []
                one = {
                    'xingming': str(values[0] if len(values) > 0 else '').strip(),
                    'moban': str(values[1] if len(values) > 1 else '').strip(),
                    'neirong': str(values[2] if len(values) > 2 else '').strip(),
                    'riqi': str(values[3] if len(values) > 3 else '').strip(),
                }
            if one['moban']:
                one['moban_key'] = f"{one['xingming']}||{one['moban']}"
                out.append(one)
        return jsonify({'success': True, 'data': out})
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取模板失败: {str(e)}'}), 500


def api_xiaotu_moban_save(
    *,
    _xiaotu_sql_escape,
    datetime,
    dui_db,
    jsonify,
    request,
    session,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    user_name = str(session.get('feishu_user_name') or '').strip()
    if not user_name:
        return jsonify({'success': False, 'message': '未获取到当前用户名'}), 400

    data = request.get_json(silent=True) or {}
    moban = str(data.get('moban') or '').strip()
    neirong = str(data.get('neirong') or '').strip()
    source_moban = str(data.get('source_moban') or moban).strip()
    if not moban:
        return jsonify({'success': False, 'message': '模板名不能为空'}), 400
    if not neirong:
        return jsonify({'success': False, 'message': '模板内容不能为空'}), 400

    riqi = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    esc_name = _xiaotu_sql_escape(user_name)
    esc_moban = _xiaotu_sql_escape(moban)
    esc_source_moban = _xiaotu_sql_escape(source_moban)
    esc_neirong = _xiaotu_sql_escape(neirong)
    try:
        sql_text = f"""
            IF EXISTS (
                SELECT 1 FROM baogao_moban
                WHERE XingMing = N'{esc_name}' AND Moban = N'{esc_source_moban}'
            )
            BEGIN
                UPDATE baogao_moban
                SET Moban = N'{esc_moban}', NeiRong = N'{esc_neirong}', RiQi = '{riqi}'
                WHERE XingMing = N'{esc_name}' AND Moban = N'{esc_source_moban}'
            END
            ELSE IF EXISTS (
                SELECT 1 FROM baogao_moban
                WHERE XingMing = N'{esc_name}' AND Moban = N'{esc_moban}'
            )
            BEGIN
                UPDATE baogao_moban
                SET NeiRong = N'{esc_neirong}', RiQi = '{riqi}'
                WHERE XingMing = N'{esc_name}' AND Moban = N'{esc_moban}'
            END
            ELSE
            BEGIN
                INSERT INTO baogao_moban (XingMing, Moban, NeiRong, RiQi)
                VALUES (N'{esc_name}', N'{esc_moban}', N'{esc_neirong}', '{riqi}')
            END
        """
        dui_db(sql_text)
        return jsonify({
            'success': True,
            'message': '模板已保存',
            'data': {
                'xingming': user_name,
                'moban': moban,
                'neirong': neirong,
                'riqi': riqi
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存模板失败: {str(e)}'}), 500


def api_xiaotu_moban_delete(
    *,
    _xiaotu_sql_escape,
    dui_db,
    jsonify,
    request,
    session,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    user_name = str(session.get('feishu_user_name') or '').strip()
    if not user_name:
        return jsonify({'success': False, 'message': '未获取到当前用户名'}), 400

    moban = str(request.args.get('moban') or '').strip()
    if not moban:
        return jsonify({'success': False, 'message': '缺少模板名'}), 400
    esc_name = _xiaotu_sql_escape(user_name)
    esc_moban = _xiaotu_sql_escape(moban)
    try:
        sql_text = f"""
            DELETE FROM baogao_moban
            WHERE XingMing = N'{esc_name}' AND Moban = N'{esc_moban}'
        """
        dui_db(sql_text)
        return jsonify({'success': True, 'message': '模板已删除'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除模板失败: {str(e)}'}), 500


def api_xiaotu_chat(
    *,
    _feishu_append_chat_history,
    _feishu_build_cloud_doc_url,
    _feishu_find_cloud_doc_url_any,
    _generate_ai_answer_with_cloud_doc_url,
    _generate_cloud_doc_analysis,
    _get_feishu_user_access_token,
    _xiaotu_extract_doc_token,
    _xiaotu_get_doc_candidates_for_user,
    datetime,
    jsonify,
    request,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    user_access_token = _get_feishu_user_access_token()
    if not user_access_token:
        session['post_auth_redirect'] = url_for('dashboard_xiaotu')
        return jsonify({
            'success': False,
            'message': '登录状态缺少云文档访问凭证，正在跳转重新登录',
            'auth_url': url_for('feishu_auth')
        }), 401
    data = request.get_json(silent=True) or {}
    mode = str(data.get('mode') or 'qa').strip().lower()
    question = str(data.get('question') or '').strip()
    doc_id = str(data.get('doc_id') or '').strip()
    manual_url = str(data.get('doc_url') or '').strip()
    conv = str(data.get('conversation_id') or '').strip()
    if not conv:
        conv = f"xiaotu:{user_id}:{int(datetime.now().timestamp())}"
    docs, _ = _xiaotu_get_doc_candidates_for_user(
        user_id,
        force_refresh=False,
        user_access_token=user_access_token
    )
    selected = None
    if doc_id:
        for one in docs:
            if str(one.get('id') or '').strip() == doc_id:
                selected = one
                break
    if selected is None:
        url = _feishu_find_cloud_doc_url_any(manual_url) or manual_url
        if not url:
            url = _feishu_find_cloud_doc_url_any(question) or ""
        if not url:
            token_only = _xiaotu_extract_doc_token(question)
            if token_only.startswith("doxcn"):
                url = _feishu_build_cloud_doc_url("docx", token_only)
            elif token_only.startswith("doccn"):
                url = _feishu_build_cloud_doc_url("doc", token_only)
            elif token_only.startswith("wiki"):
                url = _feishu_build_cloud_doc_url("wiki", token_only)
        if not url:
            return jsonify({'success': False, 'message': '请通过输入框中的+号选择云文档，或直接粘贴飞书云文档链接后再发送'}), 400
        token = _xiaotu_extract_doc_token(url)
        if not token:
            return jsonify({'success': False, 'message': '链接不是可识别的飞书云文档地址'}), 400
        selected = {
            'id': f'adhoc_{token}',
            'name': f'临时文档-{token[:8]}',
            'url': url
        }
    doc_url = str(selected.get('url') or '').strip()
    if not doc_url:
        return jsonify({'success': False, 'message': '文档链接无效'}), 400
    if mode == 'analysis':
        ask = question or '请按周报/月报分析方式，输出评分、亮点、不足、原因证据和可执行改进建议。'
        answer = _generate_cloud_doc_analysis(ask, doc_url, chat_id=conv)
    else:
        ask = question or '请先总结文档核心信息，再给出关键结论。'
        answer = _generate_ai_answer_with_cloud_doc_url(ask, doc_url, chat_id=conv)
    _feishu_append_chat_history(conv, "user", ask)
    _feishu_append_chat_history(conv, "assistant", answer or "")
    return jsonify({
        'success': True,
        'data': {
            'conversation_id': conv,
            'doc': {
                'id': str(selected.get('id') or ''),
                'name': str(selected.get('name') or ''),
                'url': doc_url
            },
            'answer': answer or ''
        }
    })


def api_xiaotu_report_cache(
    *,
    _xiaotu_get_report_cache,
    jsonify,
    session,
):
    try:
        user_name = str(session.get('feishu_user_name') or '').strip()
        if not user_name:
            return jsonify({'success': False, 'message': '未登录'}), 401
        return jsonify({
            'success': True,
            'data': _xiaotu_get_report_cache(user_name)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取缓存失败: {str(e)}'}), 500


def api_xiaotu_report_draft(
    *,
    _get_cloud_documents_agent,
    _xiaotu_compact_report_body_for_storage,
    _xiaotu_extract_report_image_paths_from_html,
    _xiaotu_get_report_cache,
    _xiaotu_normalize_notify_time,
    _xiaotu_parse_notify_open_ids,
    _xiaotu_parse_notify_targets,
    _xiaotu_replace_html_img_src_with_paths,
    _xiaotu_resolve_notify_names,
    _xiaotu_resolve_notify_open_ids,
    _xiaotu_save_inline_html_images_and_ocr_safe,
    _xiaotu_save_remote_html_images_and_ocr_safe,
    _xiaotu_save_uploaded_images_and_ocr_safe,
    _xiaotu_upsert_report_cache_draft,
    _xiaotu_upsert_report_cache_notify,
    datetime,
    jsonify,
    relocate_storage_path,
    request,
    session,
):
    try:
        is_multipart = str(request.content_type or "").lower().startswith("multipart/form-data")
        if is_multipart:
            data = request.form.to_dict() if request.form else {}
        else:
            data = request.get_json(silent=True) or {}
        user_id = str(session.get('feishu_user_id') or '').strip()
        user_name = str(session.get('feishu_user_name') or '').strip()
        if not user_id or not user_name:
            return jsonify({'success': False, 'message': '未登录'}), 401

        rich_content_html = str(data.get('rich_content_html') or data.get('rich_content') or '').strip()
        selected_notify_targets = _xiaotu_parse_notify_targets(data)
        selected_notify_open_ids = _xiaotu_resolve_notify_open_ids(
            _xiaotu_parse_notify_open_ids(data),
            selected_notify_targets
        )
        notify_time = _xiaotu_normalize_notify_time(data.get('notify_time') or '')
        selected_notify_names = _xiaotu_resolve_notify_names(selected_notify_open_ids, selected_notify_targets)

        uploaded_files = request.files.getlist('images') if is_multipart else []
        draft_token = f"draft_{user_id}_{int(datetime.now().timestamp())}"
        draft_root_dir = relocate_storage_path(r"D:\tuchuangai\报告缓存图片")
        draft_html = rich_content_html
        image_paths = _xiaotu_extract_report_image_paths_from_html(draft_html)
        if uploaded_files:
            saved_paths, _, _ = _xiaotu_save_uploaded_images_and_ocr_safe(
                uploaded_files,
                report_token=draft_token,
                root_base_dir=draft_root_dir
            )
            for one_path in (saved_paths or []):
                if one_path and one_path not in image_paths:
                    image_paths.append(one_path)
            draft_html = _xiaotu_replace_html_img_src_with_paths(draft_html, saved_paths or [])
        if draft_html:
            draft_html, inline_paths, _, _ = _xiaotu_save_inline_html_images_and_ocr_safe(
                draft_html,
                report_token=draft_token,
                root_base_dir=draft_root_dir
            )
            for one_path in (inline_paths or []):
                if one_path and one_path not in image_paths:
                    image_paths.append(one_path)
            draft_html, remote_paths, _, _ = _xiaotu_save_remote_html_images_and_ocr_safe(
                draft_html,
                report_token=draft_token,
                agent=_get_cloud_documents_agent(),
                root_base_dir=draft_root_dir
            )
            for one_path in (remote_paths or []):
                if one_path and one_path not in image_paths:
                    image_paths.append(one_path)

        if not draft_html and image_paths:
            draft_html = "".join(
                f'<p><img src="{str(p or "").replace("\\", "/")}" alt="draft-image"></p>'
                for p in image_paths if str(p or "").strip()
            )
        draft_html = _xiaotu_compact_report_body_for_storage(draft_html)

        _xiaotu_upsert_report_cache_notify(
            user_name,
            selected_notify_open_ids,
            selected_notify_targets,
            notify_time
        )
        _xiaotu_upsert_report_cache_draft(user_name, draft_html, image_paths)

        return jsonify({
            'success': True,
            'message': '草稿已保存',
            'data': _xiaotu_get_report_cache(user_name)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存草稿失败: {str(e)}'}), 500
