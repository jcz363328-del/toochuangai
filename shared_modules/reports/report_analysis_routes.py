"""Daily report document slicing, knowledge lookup and periodic analysis."""

from __future__ import annotations


def _xiaotu_slice_daily_doc_content(
    agent,
    doc_url,
    doc_text,
    *,
    _xiaotu_build_block_debug_sample,
    _xiaotu_extract_block_plain_text,
    _xiaotu_extract_image_tokens_from_block,
    _xiaotu_fetch_docx_blocks,
    _xiaotu_find_preferred_daily_block_index,
    _xiaotu_find_preferred_daily_date_start,
    _xiaotu_is_image_like_block,
    _xiaotu_order_doc_blocks,
):
    result = {
        "used": False,
        "matched_date": "",
        "match_mode": "",
        "text_sliced": False,
        "image_token_count": 0,
        "block_error": "",
        "text_source": "raw_content",
        "block_total": 0,
        "matched_block_index": -1,
        "trailing_block_count": 0,
        "trailing_image_like_block_count": 0,
        "trailing_block_samples": []
    }
    text_raw = str(doc_text or "").strip()
    if agent is None or not str(doc_url or "").strip() or not text_raw:
        return text_raw, [], result

    sliced_text = text_raw
    start_pos, matched_line, match_mode = _xiaotu_find_preferred_daily_date_start(text_raw)
    if start_pos >= 0:
        tail = text_raw[start_pos:].strip()
        if tail:
            sliced_text = tail
            result["used"] = True
            result["matched_date"] = matched_line
            result["match_mode"] = match_mode
            result["text_sliced"] = True

    resolver = getattr(agent, "resolve_url_to_doc", None)
    if not callable(resolver):
        return sliced_text, [], result
    try:
        resolved_token, resolved_type, resolved_err = resolver(doc_url)
    except Exception as e:
        resolved_token, resolved_type, resolved_err = "", "", str(e)
    if resolved_err or not resolved_token or str(resolved_type or "").strip().lower() not in {"docx", "docs", ""}:
        if resolved_err:
            result["block_error"] = str(resolved_err)
        return sliced_text, [], result

    blocks, block_err = _xiaotu_fetch_docx_blocks(agent, resolved_token)
    if block_err:
        result["block_error"] = block_err
        return sliced_text, [], result
    if not blocks:
        return sliced_text, [], result
    ordered_blocks = _xiaotu_order_doc_blocks(blocks)
    scan_blocks = ordered_blocks or blocks
    result["block_total"] = len(scan_blocks)

    last_date_block_idx, block_match_mode = _xiaotu_find_preferred_daily_block_index(
        scan_blocks,
        result.get("matched_date") or matched_line
    )
    if last_date_block_idx >= 0 and not result.get("matched_date"):
        result["matched_date"] = str(matched_line or "").strip()
    if block_match_mode:
        result["match_mode"] = block_match_mode
    result["matched_block_index"] = last_date_block_idx

    if last_date_block_idx < 0:
        result["trailing_block_samples"] = [
            _xiaotu_build_block_debug_sample(b)
            for b in scan_blocks[:8]
        ]
        return sliced_text, [], result

    trailing_blocks = scan_blocks[last_date_block_idx:]
    result["trailing_block_count"] = len(trailing_blocks)
    result["trailing_image_like_block_count"] = sum(1 for b in trailing_blocks if _xiaotu_is_image_like_block(b))
    result["trailing_block_samples"] = [
        _xiaotu_build_block_debug_sample(b)
        for b in trailing_blocks[:8]
    ]

    block_text_lines = []
    for block in trailing_blocks:
        one_text = _xiaotu_extract_block_plain_text(block)
        one_text = str(one_text or "").strip()
        if not one_text:
            continue
        block_text_lines.append(one_text)
    block_sliced_text = "\n".join(block_text_lines).strip()
    if block_sliced_text:
        sliced_text = block_sliced_text
        result["used"] = True
        result["text_sliced"] = True
        result["text_source"] = "doc_blocks"

    tokens = []
    seen = set()
    for block in trailing_blocks:
        for token in _xiaotu_extract_image_tokens_from_block(block):
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    result["used"] = True
    result["image_token_count"] = len(tokens)
    return sliced_text, tokens, result


def api_xiaotu_knowledge_search(
    *,
    _generate_ai_answer_with_doc,
    _xiaotu_extract_knowledge_terms,
    _xiaotu_render_knowledge_source_text,
    _xiaotu_sql_escape,
    datetime,
    jsonify,
    re,
    request,
    session,
    sf_db,
):
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        user_name = str(session.get('feishu_user_name') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        if not user_name:
            return jsonify({'success': False, 'message': '未获取到当前飞书用户名'}), 400

        data = request.get_json(silent=True) or {}
        question = str(data.get('question') or '').strip()
        if not question:
            return jsonify({'success': False, 'message': '请输入要搜索的问题'}), 400

        esc_user_name = _xiaotu_sql_escape(user_name)
        sql_text = f"""
            SELECT TOP 400 RiQi, BiaoTi, ZhengWen, TuPianNeiRong
            FROM baogao
            WHERE XingMing = N'{esc_user_name}'
            ORDER BY RiQi DESC
        """
        rows = sf_db(sql_text) or []
        if not rows:
            return jsonify({'success': False, 'message': '你还没有提交过可供搜索的日志'}), 404

        norm_rows = []
        for idx, row in enumerate(rows):
            if isinstance(row, dict):
                riqi = row.get('RiQi')
                biaoti = row.get('BiaoTi')
                zhengwen = row.get('ZhengWen')
                tupianneirong = row.get('TuPianNeiRong')
            else:
                values = list(row) if isinstance(row, (list, tuple)) else []
                riqi = values[0] if len(values) > 0 else ""
                biaoti = values[1] if len(values) > 1 else ""
                zhengwen = values[2] if len(values) > 2 else ""
                tupianneirong = values[3] if len(values) > 3 else ""
            norm_rows.append({
                'order_index': idx,
                'riqi': str(riqi or '').strip(),
                'biaoti': str(biaoti or '').strip(),
                'zhengwen': str(zhengwen or '').strip(),
                'tupianneirong': str(tupianneirong or '').strip(),
            })

        q_lower = question.lower()
        q_joined = re.sub(r"\s+", "", q_lower)
        terms = _xiaotu_extract_knowledge_terms(question)
        matched_rows = []
        for one in norm_rows:
            haystack = "\n".join([
                str(one.get('biaoti') or ''),
                str(one.get('zhengwen') or ''),
                str(one.get('tupianneirong') or '')
            ]).lower()
            haystack_joined = re.sub(r"\s+", "", haystack)
            score = 0
            if q_joined and q_joined in haystack_joined:
                score += 12
            for term in terms:
                if term and term in haystack:
                    score += min(6, max(2, len(term)))
            if score > 0:
                copied = dict(one)
                copied['score'] = score
                matched_rows.append(copied)

        matched_rows.sort(key=lambda x: (-int(x.get('score') or 0), int(x.get('order_index') or 0)))
        matched_rows = matched_rows[:30]
        if not matched_rows:
            return jsonify({
                'success': False,
                'message': '未在你已提交日志的正文和图片内容中检索到相关信息'
            }), 404

        source_text = _xiaotu_render_knowledge_source_text(matched_rows)
        prompt = (
            f"你是日志知识搜索助手。请仅基于以下“{user_name}本人已提交日志”的检索结果回答问题。\n"
            f"用户问题：{question}\n"
            "回答要求：\n"
            "1) 只能依据提供的日志正文和图片内容回答，不得补充素材之外的信息；\n"
            "2) 先给出直接答案，再概括依据；\n"
            "3) 若有多条记录，合并总结共同结论并点出关键时间或标题；\n"
            "4) 若证据不足，请明确说明“未在我已提交日志中检索到足够依据”；\n"
            "5) 输出简洁清晰，适合直接阅读。"
        )
        answer = _generate_ai_answer_with_doc(
            prompt_text=prompt,
            doc_text=source_text[:50000],
            doc_name=f"{user_name}-日志知识搜索",
            chat_id=f"xiaotu_knowledge:{user_id}:{int(datetime.now().timestamp())}"
        )

        return jsonify({
            'success': True,
            'data': {
                'user_name': user_name,
                'question': question,
                'row_count': len(matched_rows),
                'searched_total': len(norm_rows),
                'answer': str(answer or '').strip(),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'知识搜索失败: {str(e)}'}), 500


def api_xiaotu_period_report(
    *,
    Thread,
    _generate_ai_answer_with_doc,
    _safe_debug_print,
    _xiaotu_build_history_analysis_html,
    _xiaotu_build_name_match_clause,
    _xiaotu_build_name_scope_clause,
    _xiaotu_get_history_analysis_visible_user_names,
    _xiaotu_get_period_range,
    _xiaotu_parse_date_value,
    _xiaotu_render_period_source_text,
    _xiaotu_save_history_analysis_file,
    _xiaotu_sql_escape,
    app,
    datetime,
    dui_db,
    hashlib,
    jsonify,
    request,
    session,
    sf_db,
    time,
):
    try:
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401

        data = request.get_json(silent=True) or {}
        session_user_name = str(session.get('feishu_user_name') or '').strip()
        user_name = str(data.get('user_name') or session.get('feishu_user_name') or '').strip()
        if not user_name:
            return jsonify({'success': False, 'message': '请提供飞书用户名'}), 400

        visible_scope = _xiaotu_get_history_analysis_visible_user_names(user_id, session_user_name)
        visible_name_clause = _xiaotu_build_name_scope_clause(
            "XingMing",
            list(visible_scope.get("user_names") or [session_user_name])
        )
        if not visible_name_clause:
            visible_name_clause = f"XingMing = N'{_xiaotu_sql_escape(session_user_name)}'"
        target_name_clause = _xiaotu_build_name_match_clause("XingMing", [user_name])
        if not target_name_clause:
            target_name_clause = f"XingMing = N'{_xiaotu_sql_escape(user_name)}'"
        auth_rows = sf_db(f"""
            SELECT TOP 1 XingMing
            FROM baogao
            WHERE ({target_name_clause})
              AND ({visible_name_clause})
        """) or []
        if not auth_rows:
            return jsonify({'success': False, 'message': '无权为该用户生成报告HTML'}), 403

        today = datetime.now()
        default_start = datetime(today.year, today.month, today.day)
        start_day = _xiaotu_parse_date_value(data.get('start_date'), fallback=None)
        end_day = _xiaotu_parse_date_value(data.get('end_date'), fallback=None)
        if start_day is None or end_day is None:
            legacy_start, legacy_end, _, _ = _xiaotu_get_period_range(data.get('report_type') or 'week')
            start_day = start_day or datetime(legacy_start.year, legacy_start.month, legacy_start.day)
            end_day = end_day or datetime(legacy_end.year, legacy_end.month, legacy_end.day)
        start_day = datetime(start_day.year, start_day.month, start_day.day)
        end_day = datetime(end_day.year, end_day.month, end_day.day)
        if end_day < start_day:
            return jsonify({'success': False, 'message': '结束日期不能早于开始日期'}), 400
        if (end_day - start_day).days > 120:
            return jsonify({'success': False, 'message': '一次最多分析120天日报'}), 400
        start_s = start_day.strftime('%Y-%m-%d 00:00:00')
        end_s = end_day.strftime('%Y-%m-%d 23:59:59')
        sql_text = f"""
            SELECT RiQi, BiaoTi, ZhengWen, TuPianLujin, TuPianNeiRong
            FROM baogao
            WHERE ({target_name_clause})
              AND RiQi >= '{start_s}'
              AND RiQi <= '{end_s}'
            ORDER BY RiQi ASC
        """
        rows = sf_db(sql_text) or []
        if not rows:
            return jsonify({
                'success': False,
                'message': f'未查询到 {user_name} 在所选日期范围内的日报数据'
            }), 404

        norm_rows = []
        for row in rows:
            if isinstance(row, dict):
                riqi = row.get('RiQi')
                biaoti = row.get('BiaoTi')
                zhengwen = row.get('ZhengWen')
                tupianlujin = row.get('TuPianLujin')
                tupianneirong = row.get('TuPianNeiRong')
            else:
                values = list(row) if isinstance(row, (list, tuple)) else []
                riqi = values[0] if len(values) > 0 else ""
                biaoti = values[1] if len(values) > 1 else ""
                zhengwen = values[2] if len(values) > 2 else ""
                tupianlujin = values[3] if len(values) > 3 else ""
                tupianneirong = values[4] if len(values) > 4 else ""
            norm_rows.append({
                'riqi': str(riqi or '').strip(),
                'biaoti': str(biaoti or '').strip(),
                'zhengwen': str(zhengwen or '').strip(),
                'tupianlujin': str(tupianlujin or '').strip(),
                'tupianneirong': str(tupianneirong or '').strip(),
            })

        source_text = _xiaotu_render_period_source_text(norm_rows)
        if not source_text:
            return jsonify({'success': False, 'message': '所选日期范围内数据为空（正文和图片内容均为空）'}), 400

        prompt = (
            f"请基于以下按日报顺序整合的素材，为飞书用户“{user_name}”生成一份阶段性日报历史分析。\n"
            f"时间范围：{start_s} ~ {end_s}。\n"
            "输出要求：\n"
            "1) 不要重排日报原文顺序；分析时基于所有日报的正文和图片识别内容统一观察；\n"
            "2) 重点总结这段时间日报里体现出的思考性内容，包括关键判断、问题意识、方法沉淀、复盘反思、跨日变化；\n"
            "3) 必须基于素材事实，不要编造素材中没有出现的工作、结果或数据；\n"
            "4) 不要写成流水账，不要简单罗列每日事项；\n"
            "5) 建议输出结构：阶段概览、关键思考、方法沉淀、问题与反思、后续关注；\n"
            "6) 语言清晰、克制，适合放入HTML报告的“整合分析”部分。"
        )
        task_id = hashlib.md5(
            f"{user_name}|{start_day.strftime('%Y-%m-%d')}|{end_day.strftime('%Y-%m-%d')}|{time.time()}".encode("utf-8")
        ).hexdigest()[:16]

        def _xiaotu_period_report_background_worker(payload):
            with app.app_context():
                try:
                    p_user_name = str(payload.get("user_name") or "").strip()
                    p_user_id = str(payload.get("user_id") or "").strip()
                    p_start_day = payload.get("start_day")
                    p_end_day = payload.get("end_day")
                    p_rows = list(payload.get("rows") or [])
                    p_source_text = str(payload.get("source_text") or "")
                    p_prompt = str(payload.get("prompt") or "")
                    p_task_id = str(payload.get("task_id") or "").strip()
                    report_text = _generate_ai_answer_with_doc(
                        prompt_text=p_prompt,
                        doc_text=p_source_text,
                        doc_name=f"{p_user_name}-日报历史分析",
                        chat_id=f"xiaotu_history_report:{p_user_id}:{p_task_id}"
                    )
                    report_text = str(report_text or '').strip()
                    html_text = _xiaotu_build_history_analysis_html(p_user_name, p_start_day, p_end_day, report_text, p_rows)
                    file_path = _xiaotu_save_history_analysis_file(p_user_name, p_start_day, p_end_day, html_text)
                    dui_db(f"""
                        INSERT INTO baogao_lishi (YongHu, KaiShiRiQi, JieShuRIQi, WeiZhi)
                        VALUES (
                            N'{_xiaotu_sql_escape(p_user_name)}',
                            '{p_start_day.strftime('%Y-%m-%d')}',
                            '{p_end_day.strftime('%Y-%m-%d')}',
                            N'{_xiaotu_sql_escape(file_path)}'
                        )
                    """)
                except Exception as bg_err:
                    _safe_debug_print(f"日报历史分析后台生成失败: {payload.get('user_name')} {payload.get('task_id')} -> {bg_err}")

        Thread(target=_xiaotu_period_report_background_worker, args=({
            "task_id": task_id,
            "user_id": str(user_id or ""),
            "user_name": user_name,
            "start_day": start_day,
            "end_day": end_day,
            "rows": norm_rows,
            "source_text": source_text,
            "prompt": prompt,
        },), daemon=True).start()

        return jsonify({
            'success': True,
            'message': '已提交后台生成任务，完成后会出现在报告历史记录中',
            'data': {
                'user_name': user_name,
                'report_kind': '报告',
                'report_type': 'custom',
                'date_range': f"{start_s} ~ {end_s}",
                'row_count': len(norm_rows),
                'task_id': task_id,
                'ai_background': True,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'生成失败: {str(e)}'}), 500
