"""Report document lists, history pages and source indexing."""

from __future__ import annotations


def _xiaotu_lookup_org_perf_context(
    user_name,
    *,
    _safe_debug_print,
    _xiaotu_sql_escape,
    re,
    sf_db,
):
    name = str(user_name or "").strip()
    if not name:
        return ""
    esc_name = _xiaotu_sql_escape(name)
    compact_name = re.sub(r"\s+", "", name)
    esc_compact_name = _xiaotu_sql_escape(compact_name)
    try:
        rows = sf_db(f"""
            IF OBJECT_ID(N'dbo.zuzhi_jixiao', N'U') IS NOT NULL
                SELECT TOP 1 ai_neirong
                FROM dbo.zuzhi_jixiao
                WHERE yonghu LIKE N'%%{esc_name}%%'
                   OR REPLACE(ISNULL(yonghu, N''), N' ', N'') LIKE N'%%{esc_compact_name}%%'
                ORDER BY yonghu
        """) or []
    except Exception as e:
        _safe_debug_print(f"查询组织绩效配置失败: {name} -> {e}")
        return ""
    if not rows:
        return ""
    first = rows[0]
    if isinstance(first, dict):
        return str(first.get("ai_neirong") or first.get("AI_NEIRONG") or "").strip()
    if isinstance(first, (list, tuple)):
        return str(first[0] if first else "").strip()
    return str(first or "").strip()


def _xiaotu_person_focus_text(person_type):
    pt = str(person_type or "").strip()
    if pt == "管理层":
        return (
            "侧重点：经营洞察、管理动作复盘、团队带教、资源配置与风险预警。"
            "请适当指出优点与不足，建议要可执行。"
        )
    if pt == "改进人员":
        return (
            "侧重点：绩效差距、改进动作闭环、指标变化、问题根因与纠偏。"
            "请适当指出优点与不足，建议要量化、可跟踪。"
        )
    if pt == "管培生/实习":
        return (
            "侧重点要求（第1点最重要，优先围绕这一点判断内容是否完整、清楚、具体）：\n"
            "1. 当日工作内容：必须重点关注今日学习内容、今日工作内容、各事项用时情况，以及学习知识点是否有梳理总结。\n"
            "2. 遇到的问题、解决方案与思路扩展：说明遇到的学习难点或不理解内容、如何解决、思考路径，以及以后应对类似问题的思路总结或扩展。\n"
            "3. 明日计划：是否写清明日需继续跟进的事项与下一步动作。\n"
            "4. 好用的工作方法与素材积累：是否沉淀了可复用的方法、资料、模板或经验。\n"
            "请在总结、优点、不足、改进建议中优先体现第1点，再依次覆盖后面几点；建议要明确、具体、易执行，适合管培生/实习生快速成长。"
        )
    return (
        "侧重点：SOP执行质量、流程优化、协作效率、结果稳定性。"
        "请适当指出优点与不足，建议要具体可落地。"
    )


def _xiaotu_extract_knowledge_terms(
    question,
    *,
    re,
):
    raw = str(question or "").strip().lower()
    if not raw:
        return []
    parts = re.split(r"[\s,，。；;：:、\?\!！？\(\)（）\[\]【】\"'“”‘’/\\\-\+]+", raw)
    terms = []
    seen = set()
    for part in parts:
        token = str(part or "").strip()
        if len(token) < 2:
            continue
        if token not in seen:
            seen.add(token)
            terms.append(token)
        chinese_only = re.sub(r"[^\u4e00-\u9fff]", "", token)
        if len(chinese_only) >= 4:
            for size in (2, 3):
                for i in range(0, len(chinese_only) - size + 1):
                    piece = chinese_only[i:i + size]
                    if piece not in seen:
                        seen.add(piece)
                        terms.append(piece)
                    if len(terms) >= 18:
                        return terms[:18]
    return terms[:18]


def dashboard_xiaotu_report_history(
    *,
    _get_feishu_user_access_token,
    _xiaotu_get_history_analysis_visible_user_names,
    _xiaotu_get_report_history_debug_options,
    _xiaotu_get_report_history_scope,
    redirect,
    render_template,
    request,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        session['post_auth_redirect'] = request.full_path.rstrip('?')
        return redirect(url_for('feishu_auth'))
    user_access_token = _get_feishu_user_access_token()
    if not user_access_token:
        session['post_auth_redirect'] = request.full_path.rstrip('?')
        return redirect(url_for('feishu_auth'))
    user_name = str(session.get('feishu_user_name') or '用户').strip()
    history_debug_options = _xiaotu_get_report_history_debug_options(user_name)
    history_scope = _xiaotu_get_report_history_scope(user_name)
    history_analysis_scope = _xiaotu_get_history_analysis_visible_user_names(user_id, user_name)
    can_view_all_uploads = bool(history_scope.get('can_view_all_uploads'))
    restricted_to_allowed_departments = bool(history_scope.get('restricted_to_allowed_departments'))
    return render_template(
        '日报与报告/xiaotu_report_history.html',
        user_name=user_name,
        history_filter_name=('' if (can_view_all_uploads or restricted_to_allowed_departments) else user_name),
        history_can_view_all_uploads=can_view_all_uploads,
        history_restricted_to_allowed_departments=restricted_to_allowed_departments,
        history_allowed_department_names=list(history_scope.get('allowed_department_names') or []),
        history_analysis_is_department_leader=bool(history_analysis_scope.get('is_department_leader')),
        history_analysis_department_names=list(history_analysis_scope.get('department_names') or []),
        history_debug_enabled=bool(history_debug_options),
        history_debug_options=history_debug_options,
        history_debug_default_mode='current',
    )


def api_xiaotu_docs(
    *,
    _clear_feishu_user_access_token,
    _get_feishu_user_access_token,
    _xiaotu_extract_url_from_text,
    _xiaotu_get_doc_candidates_for_user,
    _xiaotu_need_reauth,
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
    force_refresh = str(request.args.get('refresh') or '').strip().lower() in {'1', 'true', 'yes'}
    docs, sync_err = _xiaotu_get_doc_candidates_for_user(
        user_id,
        force_refresh=force_refresh,
        user_access_token=user_access_token
    )
    if _xiaotu_need_reauth(sync_err):
        _clear_feishu_user_access_token()
        session['feishu_user_access_token_expire_at'] = ''
        session['post_auth_redirect'] = url_for('dashboard_xiaotu')
        return jsonify({
            'success': False,
            'message': '飞书登录已过期，正在跳转重新登录',
            'auth_url': url_for('feishu_auth')
        }), 401
    sync_apply_url = _xiaotu_extract_url_from_text(sync_err)
    return jsonify({'success': True, 'data': docs, 'sync_error': sync_err, 'sync_apply_url': sync_apply_url})


def api_xiaotu_add_doc(
    *,
    _feishu_find_cloud_doc_url_any,
    _get_cloud_documents_agent,
    _xiaotu_extract_doc_token,
    _xiaotu_get_user_saved_docs,
    _xiaotu_set_user_saved_docs,
    datetime,
    jsonify,
    request,
    session,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    data = request.get_json(silent=True) or {}
    url_raw = str(data.get('url') or '').strip()
    name = str(data.get('name') or '').strip()
    url = _feishu_find_cloud_doc_url_any(url_raw) or url_raw
    if not url:
        return jsonify({'success': False, 'message': '请填写云文档链接'}), 400
    token = _xiaotu_extract_doc_token(url)
    if not token:
        return jsonify({'success': False, 'message': '链接不是可识别的飞书云文档地址'}), 400
    agent = _get_cloud_documents_agent()
    if agent is None:
        return jsonify({'success': False, 'message': '云文档模块未加载成功'}), 500
    _, err = agent.fetch_document_text(url, include_images_ocr=False)
    if err:
        return jsonify({'success': False, 'message': err}), 400
    rows = _xiaotu_get_user_saved_docs(user_id)
    for one in rows:
        if str(one.get('url') or '').strip() == url:
            return jsonify({'success': True, 'data': one})
    now_s = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    doc_id = f"p_{token}_{int(datetime.now().timestamp() * 1000)}"
    new_item = {
        'id': doc_id,
        'name': name or f'云文档-{token[:8]}',
        'url': url,
        'source': 'personal',
        'created_at': now_s
    }
    rows.insert(0, new_item)
    if len(rows) > 50:
        rows = rows[:50]
    _xiaotu_set_user_saved_docs(user_id, rows)
    return jsonify({'success': True, 'data': new_item})
