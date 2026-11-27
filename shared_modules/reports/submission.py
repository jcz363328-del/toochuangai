"""Report submission and evaluation generation."""


def _xiaotu_generate_org_perf_contribution(
    user_name,
    report_kind,
    report_material,
    org_perf_context,
    chat_id,
    _generate_ai_answer_with_doc,
    _safe_debug_print,
):
    context = str(org_perf_context or "").strip()
    material = str(report_material or "").strip()
    if not context or not material:
        return ""
    prompt = (
        "请严格对照“组织绩效配置(ai_neirong)”分析该员工今日日报对组织绩效产生了什么贡献。\n"
        "ai_neirong 是唯一评价口径，必须优先匹配其中的KPI指标、任务、定义、数据来源、达标/挑战口径；"
        "只能基于日报材料里的事实说明贡献，不要编造没有写出的结果、数据或影响。\n"
        "输出要求：\n"
        "1. 只输出一段，标题固定为“组织绩效贡献：”。\n"
        "2. 100字以内，必须点明命中的组织绩效指标/任务名称，并说明日报事实如何贡献该指标。\n"
        "3. 如果日报内容无法对应ai_neirong里的任何指标或任务，写“组织绩效贡献：当前日报信息未能对应组织绩效配置中的明确指标，暂无法判断具体贡献。”\n"
        "4. 不要打分，不要写空泛表扬，不要只写“提升效率/促进绩效”等泛化结论。"
    )
    doc_text = (
        f"提交人：{user_name}\n"
        f"报告类型：{report_kind}\n\n"
        f"组织绩效配置(ai_neirong)：\n{context}\n\n"
        f"今日日报材料：\n{material}"
    )
    try:
        text = _generate_ai_answer_with_doc(
            prompt_text=prompt,
            doc_text=doc_text,
            doc_name=f"{user_name} 组织绩效贡献分析",
            chat_id=chat_id or None
        )
        return str(text or "").strip()
    except Exception as e:
        _safe_debug_print(f"组织绩效贡献分析失败: {user_name} -> {e}")
        return ""


def _xiaotu_generate_report_memory_json(
    prompt_text,
    doc_text,
    doc_name,
    chat_id,
    _OPENAI_TEXT_MODEL_CANDIDATES,
    _ai_chat_complete,
):
    prompt = str(prompt_text or "").strip()
    content = str(doc_text or "").strip()
    if not content:
        raise ValueError("日报长期记忆材料为空")
    messages = [
        {
            "role": "system",
            "content": (
                "你是公司内部的日报长期记忆维护器。"
                "只能依据提供的日报和旧快照生成严格合法的JSON，不得编造事实，不得输出JSON以外的内容。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"任务要求：\n{prompt}\n\n"
                f"材料《{str(doc_name or '日报长期记忆材料').strip()}》：\n{content[:80000]}"
            ),
        },
    ]
    return _ai_chat_complete(
        messages,
        max_tokens=4000,
        temperature=0.1,
        model_candidates=_OPENAI_TEXT_MODEL_CANDIDATES,
    )


def api_xiaotu_report_submit(
    RequestEntityTooLarge,
    Thread,
    _XIAOTU_REPORT_ESCALATION_USER,
    _feishu_upload_image_by_path_safe,
    _generate_ai_answer_with_doc,
    _get_cloud_documents_agent,
    _get_feishu_user_access_token,
    _safe_debug_print,
    _xiaotu_build_report_history_url,
    _xiaotu_build_report_instance_id,
    _xiaotu_build_report_title,
    _xiaotu_clear_report_cache_draft,
    _xiaotu_clear_report_edit_ready_session,
    _xiaotu_compact_report_body_for_storage,
    _xiaotu_count_daily_date_headings,
    _xiaotu_detect_report_kind,
    _xiaotu_extract_doc_token,
    _xiaotu_extract_source_doc_token,
    _xiaotu_find_last_daily_date_start,
    _xiaotu_generate_org_perf_contribution,
    _xiaotu_get_department_leader_user_id,
    _xiaotu_get_report_edit_ready_session,
    _xiaotu_get_report_row,
    _xiaotu_guess_title,
    _xiaotu_html_to_plain_text_preserve_blocks,
    _xiaotu_lookup_open_id_by_name,
    _xiaotu_lookup_org_perf_context,
    _xiaotu_normalize_notify_time,
    _xiaotu_parse_notify_open_ids,
    _xiaotu_parse_notify_targets,
    _xiaotu_person_focus_text,
    _xiaotu_person_type_from_value,
    _xiaotu_pick_doc_for_request,
    _xiaotu_pick_primary_department,
    _xiaotu_query_user_names_by_open_ids,
    _xiaotu_read_report_memory_context,
    _xiaotu_remember_report_owner_open_id,
    _xiaotu_replace_html_img_src_with_paths,
    _xiaotu_report_kind_from_type,
    _xiaotu_resolve_notify_names,
    _xiaotu_resolve_notify_open_ids,
    _xiaotu_resolve_redirect_url,
    _xiaotu_save_doc_images_and_ocr_safe,
    _xiaotu_save_inline_html_images_and_ocr_safe,
    _xiaotu_save_remote_html_images_and_ocr_safe,
    _xiaotu_save_uploaded_images_and_ocr_safe,
    _xiaotu_send_report_notification,
    _xiaotu_slice_daily_doc_content,
    _xiaotu_sql_escape,
    _xiaotu_update_report_memory,
    _xiaotu_upsert_report_cache_notify,
    app,
    datetime,
    dui_db,
    jsonify,
    request,
    session,
    url_for,
):
    stage = "start"
    try:
        stage = "parse_request"
        is_multipart = str(request.content_type or "").lower().startswith("multipart/form-data")
        if is_multipart:
            data = request.form.to_dict() if request.form else {}
        else:
            data = request.get_json(silent=True) or {}
        doc_id = str(data.get('doc_id') or '').strip()
        manual_url = str(data.get('doc_url') or '').strip()
        question = str(data.get('question') or '').strip()
        rich_content_html = str(data.get('rich_content_html') or data.get('rich_content') or '').strip()
        notify_time = _xiaotu_normalize_notify_time(data.get('notify_time') or '')
        report_type = str(data.get('report_type') or 'week').strip()
        person_type_raw = str(data.get('renyuanleixing') or data.get('person_type') or 'formal_staff').strip()
        notify_mode = str(data.get('notify_mode') or '').strip().lower()
        edit_wendangid = str(data.get('edit_wendangid') or '').strip()
        selected_notify_targets = _xiaotu_parse_notify_targets(data)
        selected_notify_open_ids = _xiaotu_resolve_notify_open_ids(
            _xiaotu_parse_notify_open_ids(data),
            selected_notify_targets
        )
        selected_notify_names = _xiaotu_resolve_notify_names(selected_notify_open_ids, selected_notify_targets)
        selected_notify_name_map = {}
        for item in (selected_notify_targets or []):
            if not isinstance(item, dict):
                continue
            oid = str(item.get("open_id") or "").strip()
            nm = str(item.get("name") or "").strip()
            if oid and nm and oid not in selected_notify_name_map:
                selected_notify_name_map[oid] = nm
        try:
            selected_notify_name_map.update(_xiaotu_query_user_names_by_open_ids(selected_notify_open_ids) or {})
        except Exception:
            pass
        person_type = _xiaotu_person_type_from_value(person_type_raw)
        selected_report_kind = _xiaotu_report_kind_from_type(report_type)
        redirect_endpoint = str(data.get('redirect_endpoint') or 'dashboard_xiaotu').strip()
        uploaded_files = request.files.getlist('images') if is_multipart else []

        stage = "auth"
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        user_access_token = _get_feishu_user_access_token()
        if not user_access_token:
            session['post_auth_redirect'] = _xiaotu_resolve_redirect_url(redirect_endpoint, fallback='dashboard_xiaotu')
            return jsonify({
                'success': False,
                'message': '登录状态缺少云文档访问凭证，正在跳转重新登录',
                'auth_url': url_for('feishu_auth')
            }), 401
        uploader_name = str(session.get('feishu_user_name') or '未知用户').strip()
        existing_report_row = {}
        existing_report_time_text = ""
        existing_source_doc_token = ""
        if edit_wendangid:
            edit_ready = _xiaotu_get_report_edit_ready_session(edit_wendangid)
            if not edit_ready:
                return jsonify({'success': False, 'message': '当前日报未进入可编辑状态，请先从历史页执行“撤回并修改”'}), 400
            existing_report_row = _xiaotu_get_report_row(edit_wendangid)
            if not existing_report_row:
                return jsonify({'success': False, 'message': '未找到需要修改的原日报'}), 404
            if uploader_name != str(existing_report_row.get('xingming') or '').strip():
                return jsonify({'success': False, 'message': '只能修改自己提报的日报'}), 403
            existing_report_time_text = str(existing_report_row.get('riqi') or '').strip()
            existing_source_doc_token = _xiaotu_extract_source_doc_token(edit_wendangid)

        stage = "pick_doc"
        selected = None
        doc_url = ""
        doc_token = ""
        if manual_url or doc_id or question:
            selected = _xiaotu_pick_doc_for_request(
                user_id=user_id,
                user_access_token=user_access_token,
                doc_id=doc_id,
                manual_url=manual_url,
                question=question
            )
            if selected is not None:
                doc_url = str((selected or {}).get('url') or '').strip()
                doc_token = _xiaotu_extract_doc_token(doc_url)
        if (not doc_url) and (not rich_content_html) and (not uploaded_files):
            return jsonify({'success': False, 'message': '请先选择云文档，或填写富文本内容/上传图片后再提交'}), 400
        if doc_url and not doc_token:
            return jsonify({'success': False, 'message': '未能解析云文档ID'}), 400

        stage = "load_agent"
        agent = _get_cloud_documents_agent()
        if agent is None:
            return jsonify({'success': False, 'message': '云文档模块未加载成功'}), 500

        stage = "fetch_doc_text"
        doc_text = ""
        daily_slice_debug = {"used": False, "matched_date": "", "text_sliced": False, "image_token_count": 0, "block_error": ""}
        daily_slice_image_tokens = []
        should_slice_daily = False
        auto_daily_structured = False
        if doc_url:
            doc_text, err = agent.fetch_document_text(doc_url, include_images_ocr=False)
            if err:
                return jsonify({'success': False, 'message': err}), 400
            daily_heading_count = _xiaotu_count_daily_date_headings(doc_text)
            last_daily_pos, _ = _xiaotu_find_last_daily_date_start(doc_text)
            auto_daily_structured = last_daily_pos >= 0
            initial_report_kind = selected_report_kind or _xiaotu_detect_report_kind(
                question,
                str((selected or {}).get('name') or ''),
                doc_text
            )
            should_slice_daily = (initial_report_kind == "日报") or auto_daily_structured
            if should_slice_daily:
                doc_text, daily_slice_image_tokens, daily_slice_debug = _xiaotu_slice_daily_doc_content(agent, doc_url, doc_text)
        rich_text_plain = _xiaotu_html_to_plain_text_preserve_blocks(rich_content_html or "")
        body_text = str(doc_text or '').strip()
        if rich_content_html:
            body_text = rich_content_html.strip()
        source_doc_token = str(doc_token or "").strip()
        if not source_doc_token and edit_wendangid:
            source_doc_token = existing_source_doc_token
        report_wendangid_raw = edit_wendangid or _xiaotu_build_report_instance_id(source_doc_token)
        upload_image_paths, upload_image_ocr_text, upload_debug = _xiaotu_save_uploaded_images_and_ocr_safe(
            uploaded_files,
            report_token=report_wendangid_raw
        )
        inline_image_paths, inline_image_ocr_text, inline_image_debug = ([], "", {"reason_code": "no_inline_image", "reason_text": "未检测到富文本内嵌图片", "saved_image_count": 0})
        remote_image_paths, remote_image_ocr_text, remote_image_debug = ([], "", {"reason_code": "no_remote_image", "reason_text": "未检测到富文本远程图片", "saved_image_count": 0})
        if rich_content_html:
            body_text = _xiaotu_replace_html_img_src_with_paths(rich_content_html, upload_image_paths)
            body_text, inline_image_paths, inline_image_ocr_text, inline_image_debug = _xiaotu_save_inline_html_images_and_ocr_safe(
                body_text,
                report_token=report_wendangid_raw
            )
            body_text, remote_image_paths, remote_image_ocr_text, remote_image_debug = _xiaotu_save_remote_html_images_and_ocr_safe(
                body_text,
                report_token=report_wendangid_raw,
                agent=agent
            )
        upload_image_paths = (upload_image_paths or []) + (inline_image_paths or []) + (remote_image_paths or [])
        upload_image_ocr_text = "\n\n".join([
            x for x in [
                str(upload_image_ocr_text or "").strip(),
                str(inline_image_ocr_text or "").strip(),
                str(remote_image_ocr_text or "").strip()
            ] if x
        ]).strip()
        guessed_title_text = _xiaotu_guess_title(
            (selected or {}).get('name'),
            rich_text_plain or body_text,
            source_doc_token or report_wendangid_raw
        )
        report_kind = ("日报" if should_slice_daily else (selected_report_kind or _xiaotu_detect_report_kind(question, guessed_title_text, body_text)))
        report_date_text = datetime.now().strftime('%Y-%m-%d')
        if edit_wendangid and existing_report_time_text:
            report_date_text = str(existing_report_time_text).strip()[:10] or report_date_text
        title_text = _xiaotu_build_report_title(uploader_name, report_kind, report_date_text)
        person_focus_text = _xiaotu_person_focus_text(person_type)

        stage = "image_extract"
        doc_image_paths, doc_image_ocr_text, image_debug = ([], "", {"reason_code": "skip", "reason_text": "未使用云文档图片", "saved_image_count": 0})
        if doc_url and doc_token:
            doc_image_paths, doc_image_ocr_text, image_debug = _xiaotu_save_doc_images_and_ocr_safe(
                agent,
                doc_token,
                doc_url=doc_url,
                specific_tokens=(daily_slice_image_tokens if should_slice_daily else None)
            )
        image_paths = (doc_image_paths or []) + (upload_image_paths or [])
        image_paths_text = "|".join(image_paths)
        image_ocr_text = "\n\n".join([x for x in [str(doc_image_ocr_text or "").strip(), str(upload_image_ocr_text or "").strip()] if x]).strip()
        body_text = _xiaotu_compact_report_body_for_storage(body_text)
        # Preserve the original structured body for card rendering; plain text is only a last fallback.
        notify_source_text = str(body_text or rich_content_html or doc_text or rich_text_plain or "").strip()
        notify_image_key = _feishu_upload_image_by_path_safe(image_paths[0]) if image_paths else ""
        today_text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        stage = "build_sql_fast"
        pingjia_text = "AI分析中，完成后将自动更新评价结果并推送互动卡片。"
        org_perf_context = ""
        org_perf_contribution_text = ""
        wen_dang_id = _xiaotu_sql_escape(report_wendangid_raw)
        biao_ti = _xiaotu_sql_escape(title_text)
        zheng_wen = _xiaotu_sql_escape(body_text)
        tu_pian_lu_jin = _xiaotu_sql_escape(image_paths_text)
        xing_ming = _xiaotu_sql_escape(uploader_name)
        ping_jia = _xiaotu_sql_escape(pingjia_text)
        tu_pian_nei_rong = _xiaotu_sql_escape(image_ocr_text)
        lei_xing = _xiaotu_sql_escape(report_kind)
        renyuan_lei_xing = _xiaotu_sql_escape(person_type)
        jie_shou_ren = _xiaotu_sql_escape("|".join(selected_notify_names))
        report_time_text = existing_report_time_text or today_text
        report_time_esc = _xiaotu_sql_escape(report_time_text)

        if edit_wendangid:
            sql_insert = f"""
                UPDATE baogao
                SET BiaoTi = N'{biao_ti}',
                    ZhengWen = N'{zheng_wen}',
                    TuPianLujin = N'{tu_pian_lu_jin}',
                    XingMing = N'{xing_ming}',
                    RiQi = '{report_time_esc}',
                    PingJia = N'{ping_jia}',
                    TuPianNeiRong = N'{tu_pian_nei_rong}',
                    LeiXing = N'{lei_xing}',
                    RenYuanLeiXing = N'{renyuan_lei_xing}',
                    JieShouRen = N'{jie_shou_ren}'
                WHERE WenDangID = '{wen_dang_id}'
                  AND XingMing = N'{xing_ming}'
            """
        else:
            sql_insert = f"""
                IF EXISTS (
                    SELECT 1
                    FROM baogao WITH (UPDLOCK, HOLDLOCK)
                    WHERE WenDangID = '{wen_dang_id}'
                      AND XingMing = N'{xing_ming}'
                )
                BEGIN
                    UPDATE baogao
                    SET BiaoTi = N'{biao_ti}',
                        ZhengWen = N'{zheng_wen}',
                        TuPianLujin = N'{tu_pian_lu_jin}',
                        XingMing = N'{xing_ming}',
                        RiQi = '{report_time_esc}',
                        PingJia = N'{ping_jia}',
                        TuPianNeiRong = N'{tu_pian_nei_rong}',
                        LeiXing = N'{lei_xing}',
                        RenYuanLeiXing = N'{renyuan_lei_xing}',
                        JieShouRen = N'{jie_shou_ren}'
                    WHERE WenDangID = '{wen_dang_id}'
                      AND XingMing = N'{xing_ming}'
                END
                ELSE
                BEGIN
                    INSERT INTO baogao (WenDangID, BiaoTi, ZhengWen, TuPianLujin, XingMing, RiQi, PingJia, TuPianNeiRong, LeiXing, RenYuanLeiXing, JieShouRen)
                    VALUES (
                        '{wen_dang_id}',
                        N'{biao_ti}',
                        N'{zheng_wen}',
                        N'{tu_pian_lu_jin}',
                        N'{xing_ming}',
                        '{report_time_esc}',
                        N'{ping_jia}',
                        N'{tu_pian_nei_rong}',
                        N'{lei_xing}',
                        N'{renyuan_lei_xing}',
                        N'{jie_shou_ren}'
                    )
                END
            """

        stage = "db_insert_fast"
        try:
            dui_db(sql_insert)
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'写入baogao失败: {str(e)}',
                'stage': stage
            }), 500

        comment_url = url_for('xiaotu_report_comment_page', wendangid=report_wendangid_raw, _external=True) if report_wendangid_raw else ""
        report_url = _xiaotu_build_report_history_url(report_wendangid_raw)
        _xiaotu_remember_report_owner_open_id(report_wendangid_raw, user_id)

        bg_payload = {
            "report_wendangid_raw": report_wendangid_raw,
            "uploader_name": uploader_name,
            "user_id": user_id,
            "title_text": title_text,
            "person_type": person_type,
            "person_focus_text": person_focus_text,
            "report_kind": report_kind,
            "report_type": report_type,
            "report_date_text": report_date_text,
            "rich_text_plain": rich_text_plain,
            "body_text": body_text,
            "image_ocr_text": image_ocr_text,
            "guessed_title_text": guessed_title_text,
            "doc_url": doc_url,
            "notify_source_text": notify_source_text,
            "notify_image_key": notify_image_key,
            "image_paths_text": image_paths_text,
            "comment_url": comment_url,
            "report_url": report_url,
            "selected_notify_open_ids": list(selected_notify_open_ids or []),
            "selected_notify_name_map": dict(selected_notify_name_map or {}),
            "notify_mode": notify_mode,
            "edit_wendangid": edit_wendangid,
        }

        def _xiaotu_report_ai_background_worker(payload):
            with app.app_context():
                try:
                    uid = str(payload.get("user_id") or "").strip()
                    wid = str(payload.get("report_wendangid_raw") or "").strip()
                    uname = str(payload.get("uploader_name") or "").strip()
                    kind = str(payload.get("report_kind") or "").strip()
                    ptype = str(payload.get("person_type") or "").strip()
                    focus = str(payload.get("person_focus_text") or "").strip()
                    rich_plain = str(payload.get("rich_text_plain") or "").strip()
                    body = str(payload.get("body_text") or "").strip()
                    img_ocr = str(payload.get("image_ocr_text") or "").strip()
                    is_daily = (str(payload.get("report_type") or "").strip().lower() in {"day", "daily"}) or ("日报" in kind)
                    history_context = _xiaotu_read_report_memory_context(uname) if is_daily else ""
                    prompt = (
                        f"请按{kind}要求对该日报进行简短评价，并结合人员类型侧重点输出。\n"
                        f"{focus}\n"
                        "请把正文和图片识别内容作为同一份材料统一分析。"
                        "如果提供了历史长期记忆，可以用它判断本次工作的延续、变化和作用，但评价中的事实必须来自当前日报，"
                        "不得把历史事项说成今天完成。输出要短、准、具体，控制在120字以内。"
                    )
                    source = f"正文：\n{rich_plain or _xiaotu_html_to_plain_text_preserve_blocks(body)}\n\n图片识别内容：\n{img_ocr or '（无）'}"
                    analysis_source = source
                    if history_context:
                        analysis_source = (
                            "【历史长期记忆，仅作背景】\n"
                            f"{history_context}\n\n"
                            "【当前日报，作为本次评价的事实来源】\n"
                            f"{source}"
                        )
                    ai_text = _generate_ai_answer_with_doc(
                        prompt_text=prompt,
                        doc_text=analysis_source,
                        doc_name=str(payload.get("guessed_title_text") or payload.get("title_text") or "日报内容"),
                        chat_id=f"xiaotu_report_bg:{uid}:{int(datetime.now().timestamp())}"
                    )
                    final_pingjia = str(ai_text or "").strip()
                    org_text = ""
                    if is_daily:
                        org_ctx = _xiaotu_lookup_org_perf_context(uname)
                        if org_ctx:
                            org_text = _xiaotu_generate_org_perf_contribution(
                                uname,
                                kind,
                                source,
                                org_ctx,
                                chat_id=f"xiaotu_org_perf_bg:{uid}:{int(datetime.now().timestamp())}"
                            )
                            if org_text:
                                if "组织绩效贡献" not in org_text and "对组织绩效影响" not in org_text:
                                    org_text = f"组织绩效贡献：{org_text}"
                                final_pingjia = "\n\n".join([x for x in [final_pingjia, org_text] if x]).strip()
                    if not final_pingjia:
                        final_pingjia = "AI分析暂未生成有效评价。"
                    dui_db(f"""
                        UPDATE baogao
                        SET PingJia = N'{_xiaotu_sql_escape(final_pingjia)}'
                        WHERE WenDangID = '{_xiaotu_sql_escape(wid)}'
                          AND XingMing = N'{_xiaotu_sql_escape(uname)}'
                    """)

                    targets = [uid]
                    selected_ids = [str(x or "").strip() for x in (payload.get("selected_notify_open_ids") or []) if str(x or "").strip()]
                    targets.extend([x for x in selected_ids if x != uid])
                    should_add_default_target = (not selected_ids) or (str(payload.get("notify_mode") or "").strip().lower() == "selected_plus_default")
                    if should_add_default_target:
                        try:
                            primary_dept_id, _ = _xiaotu_pick_primary_department(uid)
                            leader_id = _xiaotu_get_department_leader_user_id(primary_dept_id)
                            if leader_id and leader_id != uid:
                                targets.append(leader_id)
                        except Exception:
                            pass
                    sent = set()
                    for target in targets:
                        target = str(target or "").strip()
                        if not target or target in sent:
                            continue
                        sent.add(target)
                        _xiaotu_send_report_notification(
                            target,
                            "open_id",
                            str(payload.get("title_text") or "").strip(),
                            ptype,
                            final_pingjia,
                            doc_url=str(payload.get("doc_url") or "").strip(),
                            source_text=str(payload.get("notify_source_text") or "").strip(),
                            image_key=str(payload.get("notify_image_key") or "").strip(),
                            image_paths_text=str(payload.get("image_paths_text") or "").strip(),
                            wendangid=wid,
                            comment_url=str(payload.get("comment_url") or "").strip(),
                            report_url=str(payload.get("report_url") or "").strip(),
                            org_impact_text=org_text
                        )
                except Exception as bg_err:
                    _safe_debug_print(f"后台日报AI分析失败: {payload.get('report_wendangid_raw')} -> {bg_err}")

        def _xiaotu_report_memory_background_worker(payload):
            with app.app_context():
                try:
                    kind = str(payload.get("report_kind") or "").strip()
                    is_daily = (
                        str(payload.get("report_type") or "").strip().lower() in {"day", "daily"}
                    ) or ("日报" in kind)
                    if not is_daily:
                        return
                    rich_plain = str(payload.get("rich_text_plain") or "").strip()
                    body = str(payload.get("body_text") or "").strip()
                    img_ocr = str(payload.get("image_ocr_text") or "").strip()
                    current_material = (
                        f"正文：\n{rich_plain or _xiaotu_html_to_plain_text_preserve_blocks(body)}\n\n"
                        f"图片识别内容：\n{img_ocr or '（无）'}"
                    )
                    _xiaotu_update_report_memory(
                        user_name=str(payload.get("uploader_name") or "").strip(),
                        user_open_id=str(payload.get("user_id") or "").strip(),
                        report_id=str(payload.get("report_wendangid_raw") or "").strip(),
                        report_date=str(payload.get("report_date_text") or "").strip(),
                        report_material=current_material,
                        is_edit=bool(payload.get("edit_wendangid")),
                    )
                except Exception as memory_err:
                    _safe_debug_print(
                        f"后台日报长期记忆更新失败: "
                        f"{payload.get('report_wendangid_raw')} -> {memory_err}"
                    )

        Thread(target=_xiaotu_report_ai_background_worker, args=(bg_payload,), daemon=True).start()
        Thread(target=_xiaotu_report_memory_background_worker, args=(bg_payload,), daemon=True).start()

        cache_warning = ""
        try:
            _xiaotu_upsert_report_cache_notify(
                uploader_name,
                selected_notify_open_ids,
                selected_notify_targets,
                notify_time
            )
            _xiaotu_clear_report_cache_draft(uploader_name)
            if edit_wendangid:
                _xiaotu_clear_report_edit_ready_session(edit_wendangid)
        except Exception as cache_err:
            cache_warning = str(cache_err)

        return jsonify({
            'success': True,
            'message': '提交成功，AI分析将在后台进行，完成后会自动更新评价并推送互动卡片。',
            'data': {
                'doc_id': doc_token or "",
                'report_id': report_wendangid_raw,
                'source_doc_token': source_doc_token,
                'doc_url': doc_url or "",
                'edit_wendangid': edit_wendangid,
                'title': title_text,
                'submitter_name': uploader_name,
                'report_kind': report_kind,
                'renyuanleixing': person_type,
                'image_count': len(image_paths),
                'image_paths': image_paths,
                'image_debug': image_debug,
                'daily_slice_debug': daily_slice_debug,
                'upload_image_debug': upload_debug,
                'inline_image_debug': inline_image_debug,
                'remote_image_debug': remote_image_debug,
                'pushed': False,
                'ai_background': True,
                'notify_policy': '后台AI分析完成后推送',
                'notify_time': notify_time,
                'notify_detail': {},
                'jieshouren': selected_notify_names,
                'pingjia': pingjia_text,
                'org_perf_matched': False,
                'org_perf_contribution': '',
                'cache_cleared': (cache_warning == ""),
                'cache_warning': cache_warning
            }
        })

        stage = "ai_analysis"
        eval_prompt = (
            f"请按{report_kind}要求对该文档进行总结，并结合“{person_type}”身份侧重点输出精简评价。\n"
            f"{person_focus_text}\n"
            "请把正文内容和图片识别内容视为同一份素材统一分析，不要分开写两套结论；若图片内容与正文互补，请合并后再判断。\n"
            f"{'若人员类型为管培生/实习，请按“当日工作内容 -> 遇到的问题、解决方案与思路扩展 -> 明日计划 -> 好用的工作方法与素材积累”的顺序判断，其中“当日工作内容”最重要，必须优先写清楚。\\n' if person_type == '管培生/实习' else ''}"
            "先判断素材是否足够支撑分析：如果正文和图片内容总量很少，只有几个字，或主要是“测试、试试、123、111、abc”等无实际业务信息的内容，"
            "说明信息不足，不能根据人员类型去脑补SOP执行、流程优化、协作效率、结果稳定性等表现。\n"
            "输出要短、准、易读，目标是让人一眼看懂，不要写成长篇分析。\n"
            "输出结构要求为：\n"
            "1. 重点总结：2-3句，优先写最重要进展、结果或问题，必须贴合该人员类型的侧重点。\n"
            "2. 亮点：仅在正文或图片内容里存在明确、可落地、可说明的亮点时才写1-2条；如果没有明显亮点，就不要输出“亮点”这个标题，也不要凑内容。\n"
            "3. 待改进：最多写1条；如果没有明确问题，可写“暂无明显问题”或直接不写。\n"
            "要求：\n"
            "- 如果素材明显不足，请只输出“重点总结：当前内容过少或仅为测试信息，无法据此做有效业务分析。”；不要输出亮点，不要输出待改进，不要补充推测；\n"
            "- 总体尽量控制在220字以内；\n"
            "- 不要复述过多原文，不要铺陈背景，不要写空话；\n"
            "- 不要把小问题拆成很多条，不足只保留最关键的一条或不写；\n"
            "- 只能根据素材里明确写出的事实来分析，不能把“测试”类内容扩写成真实工作表现；\n"
            "- 语言直接、具体、简短，每条尽量一句话；没有亮点时不要为了凑格式硬写亮点。"
        )
        source_for_eval = (
            f"正文：\n{rich_text_plain or body_text}\n\n"
            f"图片识别内容：\n{image_ocr_text or '（无）'}\n"
        )
        pingjia = _generate_ai_answer_with_doc(
            prompt_text=eval_prompt,
            doc_text=source_for_eval,
            doc_name=guessed_title_text or title_text or "上传内容",
            chat_id=f"xiaotu_report:{user_id}:{int(datetime.now().timestamp())}"
        )
        pingjia_text = str(pingjia or '').strip()
        org_perf_context = ""
        org_perf_contribution_text = ""
        try:
            is_daily_report = (str(report_type or "").strip().lower() in {"day", "daily"}) or ("日报" in str(report_kind or ""))
            if is_daily_report:
                org_perf_context = _xiaotu_lookup_org_perf_context(uploader_name)
                if org_perf_context:
                    org_perf_material = (
                        f"正文：\n{rich_text_plain or _xiaotu_html_to_plain_text_preserve_blocks(body_text)}\n\n"
                        f"图片识别内容：\n{image_ocr_text or '（无）'}"
                    )
                    org_perf_contribution_text = _xiaotu_generate_org_perf_contribution(
                        uploader_name,
                        report_kind,
                        org_perf_material,
                        org_perf_context,
                        chat_id=f"xiaotu_org_perf:{user_id}:{int(datetime.now().timestamp())}"
                    )
                    if org_perf_contribution_text:
                        if "组织绩效贡献" not in org_perf_contribution_text:
                            org_perf_contribution_text = f"组织绩效贡献：{org_perf_contribution_text}"
                        pingjia_text = "\n\n".join([x for x in [pingjia_text, org_perf_contribution_text] if x]).strip()
        except Exception as org_perf_err:
            _safe_debug_print(f"组织绩效贡献分析跳过: {uploader_name} -> {org_perf_err}")

        stage = "build_sql"
        wen_dang_id = _xiaotu_sql_escape(report_wendangid_raw)
        biao_ti = _xiaotu_sql_escape(title_text)
        zheng_wen = _xiaotu_sql_escape(body_text)
        tu_pian_lu_jin = _xiaotu_sql_escape(image_paths_text)
        xing_ming = _xiaotu_sql_escape(uploader_name)
        ping_jia = _xiaotu_sql_escape(pingjia_text)
        tu_pian_nei_rong = _xiaotu_sql_escape(image_ocr_text)
        lei_xing = _xiaotu_sql_escape(report_kind)
        renyuan_lei_xing = _xiaotu_sql_escape(person_type)
        jie_shou_ren = _xiaotu_sql_escape("|".join(selected_notify_names))
        report_time_text = existing_report_time_text or today_text
        report_time_esc = _xiaotu_sql_escape(report_time_text)

        if edit_wendangid:
            sql_insert = f"""
                UPDATE baogao
                SET BiaoTi = N'{biao_ti}',
                    ZhengWen = N'{zheng_wen}',
                    TuPianLujin = N'{tu_pian_lu_jin}',
                    XingMing = N'{xing_ming}',
                    RiQi = '{report_time_esc}',
                    PingJia = N'{ping_jia}',
                    TuPianNeiRong = N'{tu_pian_nei_rong}',
                    LeiXing = N'{lei_xing}',
                    RenYuanLeiXing = N'{renyuan_lei_xing}',
                    JieShouRen = N'{jie_shou_ren}'
                WHERE WenDangID = '{wen_dang_id}'
                  AND XingMing = N'{xing_ming}'
            """
        else:
            sql_insert = f"""
                IF EXISTS (
                    SELECT 1
                    FROM baogao WITH (UPDLOCK, HOLDLOCK)
                    WHERE WenDangID = '{wen_dang_id}'
                      AND XingMing = N'{xing_ming}'
                )
                BEGIN
                    UPDATE baogao
                    SET BiaoTi = N'{biao_ti}',
                        ZhengWen = N'{zheng_wen}',
                        TuPianLujin = N'{tu_pian_lu_jin}',
                        XingMing = N'{xing_ming}',
                        RiQi = '{report_time_esc}',
                        PingJia = N'{ping_jia}',
                        TuPianNeiRong = N'{tu_pian_nei_rong}',
                        LeiXing = N'{lei_xing}',
                        RenYuanLeiXing = N'{renyuan_lei_xing}',
                        JieShouRen = N'{jie_shou_ren}'
                    WHERE WenDangID = '{wen_dang_id}'
                      AND XingMing = N'{xing_ming}'
                END
                ELSE
                BEGIN
                    INSERT INTO baogao (WenDangID, BiaoTi, ZhengWen, TuPianLujin, XingMing, RiQi, PingJia, TuPianNeiRong, LeiXing, RenYuanLeiXing, JieShouRen)
                    VALUES (
                        '{wen_dang_id}',
                        N'{biao_ti}',
                        N'{zheng_wen}',
                        N'{tu_pian_lu_jin}',
                        N'{xing_ming}',
                        '{report_time_esc}',
                        N'{ping_jia}',
                        N'{tu_pian_nei_rong}',
                        N'{lei_xing}',
                        N'{renyuan_lei_xing}',
                        N'{jie_shou_ren}'
                    )
                END
            """

        stage = "db_insert"
        try:
            dui_db(sql_insert)
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'写入baogao失败: {str(e)}',
                'stage': stage
            }), 500

        comment_url = url_for('xiaotu_report_comment_page', wendangid=report_wendangid_raw, _external=True) if report_wendangid_raw else ""
        report_url = _xiaotu_build_report_history_url(report_wendangid_raw)
        _xiaotu_remember_report_owner_open_id(report_wendangid_raw, user_id)

        stage = "feishu_push"
        pushed = _xiaotu_send_report_notification(
            user_id,
            "open_id",
            title_text,
            person_type,
            pingjia_text,
            doc_url=doc_url,
            source_text=notify_source_text,
            image_key=notify_image_key,
            image_paths_text=image_paths_text,
            wendangid=report_wendangid_raw,
            comment_url=comment_url,
            report_url=report_url,
            org_impact_text=org_perf_contribution_text
        )
        notify_policy = "成员提交->部门leader_user_id+自己；负责人提交->陶晓飞+自己"
        if selected_notify_open_ids:
            notify_policy = "按指定人员通知+自己"
            if notify_mode == "selected_plus_default":
                notify_policy = "按指定人员通知+默认上级策略+自己"
        notify_detail = {
            'self_notify': bool(pushed),
            'primary_department_id': '',
            'primary_department_name': '',
            'department_leader_user_id': '',
            'is_uploader_department_leader': False,
            'selected_mode': ('selected_plus_default' if notify_mode == 'selected_plus_default' else 'selected_only'),
            'selected_targets': [],
            'extra_targets': [],
            'extra_success_count': 0,
            'extra_failed_count': 0
        }

        try:
            primary_dept_id, primary_dept_name = _xiaotu_pick_primary_department(user_id)
            dept_leader_user_id = _xiaotu_get_department_leader_user_id(primary_dept_id)
            uploader_uid = str(user_id or "").strip()
            is_uploader_leader = bool(dept_leader_user_id) and (uploader_uid == dept_leader_user_id)
            notify_detail['primary_department_id'] = primary_dept_id
            notify_detail['primary_department_name'] = primary_dept_name
            notify_detail['department_leader_user_id'] = dept_leader_user_id
            notify_detail['is_uploader_department_leader'] = is_uploader_leader

            extra_targets = []
            if selected_notify_open_ids:
                for oid in selected_notify_open_ids:
                    if oid and oid != uploader_uid:
                        extra_targets.append(oid)
                    notify_detail['selected_targets'].append({
                        'open_id': oid,
                        'name': selected_notify_name_map.get(oid, ''),
                        'is_self': bool(oid == uploader_uid)
                    })
                if notify_mode == "selected_plus_default":
                    if is_uploader_leader:
                        target_name = str(_XIAOTU_REPORT_ESCALATION_USER or '').strip()
                        if target_name and target_name != uploader_name:
                            escalation_open_id = _xiaotu_lookup_open_id_by_name(target_name)
                            if escalation_open_id:
                                extra_targets.append(escalation_open_id)
                            else:
                                notify_detail['extra_targets'].append({
                                    'name': target_name,
                                    'success': False,
                                    'message': '未找到升级通知人对应的open_id'
                                })
                                notify_detail['extra_failed_count'] += 1
                    else:
                        if dept_leader_user_id and dept_leader_user_id != uploader_uid:
                            extra_targets.append(dept_leader_user_id)
                        elif not dept_leader_user_id:
                            notify_detail['extra_targets'].append({
                                'name': 'missing_department_leader_user_id',
                                'success': False,
                                'message': '当前用户部门未获取到leader_user_id'
                            })
                            notify_detail['extra_failed_count'] += 1
            elif is_uploader_leader:
                target_name = str(_XIAOTU_REPORT_ESCALATION_USER or '').strip()
                if target_name and target_name != uploader_name:
                    escalation_open_id = _xiaotu_lookup_open_id_by_name(target_name)
                    if escalation_open_id:
                        extra_targets.append(escalation_open_id)
                    else:
                        notify_detail['extra_targets'].append({
                            'name': target_name,
                            'success': False,
                            'message': '未找到升级通知人对应的open_id'
                        })
                        notify_detail['extra_failed_count'] += 1
            else:
                if dept_leader_user_id and dept_leader_user_id != uploader_uid:
                    extra_targets.append(dept_leader_user_id)
                elif not dept_leader_user_id:
                    notify_detail['extra_targets'].append({
                        'name': 'missing_department_leader_user_id',
                        'success': False,
                        'message': '当前用户部门未获取到leader_user_id'
                    })
                    notify_detail['extra_failed_count'] += 1

            sent_seen = set()
            for target in extra_targets:
                target = str(target or "").strip()
                if not target or target in sent_seen:
                    continue
                sent_seen.add(target)
                ok = bool(_xiaotu_send_report_notification(
                    target,
                    "open_id",
                    title_text,
                    person_type,
                    pingjia_text,
                    doc_url=doc_url,
                    source_text=notify_source_text,
                    image_key=notify_image_key,
                    image_paths_text=image_paths_text,
                    wendangid=report_wendangid_raw,
                    comment_url=comment_url,
                    report_url=report_url,
                    org_impact_text=org_perf_contribution_text
                ))
                notify_detail['extra_targets'].append({'name': target, 'success': ok})
                if ok:
                    notify_detail['extra_success_count'] += 1
                else:
                    notify_detail['extra_failed_count'] += 1
        except Exception as notify_err:
            notify_detail['extra_targets'].append({'name': 'notify_error', 'success': False, 'message': str(notify_err)})
            notify_detail['extra_failed_count'] += 1

        cache_warning = ""
        try:
            _xiaotu_upsert_report_cache_notify(
                uploader_name,
                selected_notify_open_ids,
                selected_notify_targets,
                notify_time
            )
            _xiaotu_clear_report_cache_draft(uploader_name)
            if edit_wendangid:
                _xiaotu_clear_report_edit_ready_session(edit_wendangid)
        except Exception as cache_err:
            cache_warning = str(cache_err)

        return jsonify({
            'success': True,
            'message': ('已更新原日报记录并完成飞书推送' if edit_wendangid else '已提交到baogao并完成飞书推送'),
            'data': {
                'doc_id': doc_token or "",
                'report_id': report_wendangid_raw,
                'source_doc_token': source_doc_token,
                'doc_url': doc_url or "",
                'edit_wendangid': edit_wendangid,
                'title': title_text,
                'submitter_name': uploader_name,
                'report_kind': report_kind,
                'renyuanleixing': person_type,
                'image_count': len(image_paths),
                'image_paths': image_paths,
                'image_debug': image_debug,
                'daily_slice_debug': daily_slice_debug,
                'upload_image_debug': upload_debug,
                'inline_image_debug': inline_image_debug,
                'remote_image_debug': remote_image_debug,
                'pushed': bool(pushed),
                'notify_policy': notify_policy,
                'notify_time': notify_time,
                'notify_detail': notify_detail,
                'jieshouren': selected_notify_names,
                'pingjia': pingjia_text,
                'org_perf_matched': bool(org_perf_context),
                'org_perf_contribution': org_perf_contribution_text,
                'cache_cleared': (cache_warning == ""),
                'cache_warning': cache_warning
            }
        })
    except RequestEntityTooLarge:
        return jsonify({
            'success': False,
            'message': '提交内容过大，请压缩图片、减少粘贴图片数量，或分次提交后再试',
            'stage': stage
        }), 413
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'提交处理失败（阶段:{stage}）: {str(e)}',
            'stage': stage
        }), 500
