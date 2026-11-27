"""Daily report history queries, downloads and analysis attachments."""

from __future__ import annotations


def api_xiaotu_report_history(
    *,
    _current_user_has_permission,
    _xiaotu_build_name_match_clause,
    _xiaotu_build_report_history_url,
    _xiaotu_collect_notify_user_names_by_department_names,
    _xiaotu_enrich_feedback_data,
    _xiaotu_extract_source_doc_token,
    _xiaotu_get_report_history_scope,
    _xiaotu_list_notify_departments,
    _xiaotu_list_notify_users_current_app_cached,
    _xiaotu_sql_escape,
    datetime,
    jsonify,
    request,
    session,
    sf_db,
):
    try:
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401

        session_user_name = str(session.get('feishu_user_name') or '').strip()
        request_debug_mode = str(request.args.get('debug_scope_mode') or '').strip().lower()
        history_debug_enabled = _current_user_has_permission('xiaotu_report_history_debug', user_id)
        if request_debug_mode not in {"", "current", "self_only", "all_uploads", "operation_only"}:
            request_debug_mode = ""
        effective_debug_mode = request_debug_mode if history_debug_enabled else ""
        history_scope = _xiaotu_get_report_history_scope(session_user_name, debug_mode=effective_debug_mode)
        can_view_all_uploads = bool(history_scope.get('can_view_all_uploads'))
        restricted_to_allowed_departments = bool(history_scope.get('restricted_to_allowed_departments'))
        allowed_department_names = list(history_scope.get('allowed_department_names') or [])
        request_name = str(request.args.get('name') or '').strip()
        department_id = str(request.args.get('department_id') or '').strip()
        filter_name = str(request_name or session_user_name or '').strip()
        date_start = str(request.args.get('date_start') or '').strip()
        date_end = str(request.args.get('date_end') or '').strip()
        keyword = str(request.args.get('keyword') or '').strip()
        focus_wid = str(request.args.get('wendangid') or '').strip()
        page_size = 10
        try:
            uploaded_page = max(1, int(request.args.get('uploaded_page') or 1))
        except Exception:
            uploaded_page = 1
        try:
            received_page = max(1, int(request.args.get('received_page') or 1))
        except Exception:
            received_page = 1
        if department_id and not (department_id.startswith("od_") or department_id.startswith("od-")):
            return jsonify({'success': False, 'message': 'department_id格式无效'}), 400

        allowed_department_ids = set()
        if allowed_department_names:
            for one in (_xiaotu_list_notify_departments() or []):
                if not isinstance(one, dict):
                    continue
                dept_name = str(one.get("department_name") or "").strip()
                dept_id = str(one.get("department_id") or "").strip()
                if dept_name in allowed_department_names and dept_id:
                    allowed_department_ids.add(dept_id)
            if department_id and department_id not in allowed_department_ids:
                return jsonify({'success': True, 'data': {
                    'filters': {
                        'name': '',
                        'department_id': department_id,
                        'date_start': date_start,
                        'date_end': date_end,
                        'keyword': keyword,
                        'wendangid': focus_wid,
                    },
                    'permissions': {
                        'can_view_all_uploads': can_view_all_uploads,
                        'restricted_to_allowed_departments': restricted_to_allowed_departments,
                        'allowed_department_names': allowed_department_names,
                    },
                    'pagination': {
                        'uploaded': {'page': 1, 'page_size': page_size, 'total': 0, 'total_pages': 1},
                        'received': {'page': 1, 'page_size': page_size, 'total': 0, 'total_pages': 1},
                    },
                    'stats': {
                        'uploaded_total': 0,
                        'received_total': 0,
                        'uploaded_today': 0,
                        'received_today': 0,
                        'received_unique_senders': 0,
                    },
                    'uploaded': [],
                    'received': [],
                }})

        where_uploaded = ["1=1"]
        where_received = ["1=1"]
        uploaded_filter_name = filter_name
        if (can_view_all_uploads or restricted_to_allowed_departments) and not request_name:
            uploaded_filter_name = ''
        if uploaded_filter_name:
            esc_name = _xiaotu_sql_escape(uploaded_filter_name)
            where_uploaded.append(f"b.XingMing LIKE N'%%{esc_name}%%'")
        if filter_name:
            esc_name = _xiaotu_sql_escape(filter_name)
            where_received.append(f"b.JieShouRen LIKE N'%%{esc_name}%%'")
        if allowed_department_names:
            allowed_user_names = _xiaotu_collect_notify_user_names_by_department_names(allowed_department_names)
            own_name = str(session_user_name or "").strip()
            if own_name and own_name not in allowed_user_names:
                allowed_user_names.append(own_name)
            allowed_name_clause = _xiaotu_build_name_match_clause("b.XingMing", allowed_user_names)
            if allowed_name_clause:
                where_uploaded.append(allowed_name_clause)
                where_received.append(allowed_name_clause)
            else:
                where_uploaded.append("1=0")
                where_received.append("1=0")
        if department_id:
            department_users = _xiaotu_list_notify_users_current_app_cached(department_id)
            department_user_names = [str((one or {}).get("name") or "").strip() for one in department_users if isinstance(one, dict)]
            department_name_clause = _xiaotu_build_name_match_clause("b.XingMing", department_user_names)
            if department_name_clause:
                where_uploaded.append(department_name_clause)
                where_received.append(department_name_clause)
            else:
                where_uploaded.append("1=0")
                where_received.append("1=0")
        if focus_wid:
            esc_wid = _xiaotu_sql_escape(focus_wid)
            where_uploaded.append(f"b.WenDangID = '{esc_wid}'")
            where_received.append(f"b.WenDangID = '{esc_wid}'")
        if date_start:
            where_uploaded.append(f"b.RiQi >= '{_xiaotu_sql_escape(date_start)} 00:00:00'")
            where_received.append(f"b.RiQi >= '{_xiaotu_sql_escape(date_start)} 00:00:00'")
        if date_end:
            where_uploaded.append(f"b.RiQi <= '{_xiaotu_sql_escape(date_end)} 23:59:59'")
            where_received.append(f"b.RiQi <= '{_xiaotu_sql_escape(date_end)} 23:59:59'")
        if keyword:
            esc_kw = _xiaotu_sql_escape(keyword)
            keyword_clause = (
                "("
                f"b.BiaoTi LIKE N'%%{esc_kw}%%' OR "
                f"b.ZhengWen LIKE N'%%{esc_kw}%%' OR "
                f"b.TuPianNeiRong LIKE N'%%{esc_kw}%%' OR "
                f"b.PingJia LIKE N'%%{esc_kw}%%' OR "
                f"b.LeiXing LIKE N'%%{esc_kw}%%' OR "
                f"b.RenYuanLeiXing LIKE N'%%{esc_kw}%%'"
                ")"
            )
            where_uploaded.append(keyword_clause)
            where_received.append(keyword_clause)

        uploaded_where_sql = " AND ".join(where_uploaded)
        received_where_sql = " AND ".join(where_received)
        uploaded_offset = max(0, (uploaded_page - 1) * page_size)
        received_offset = max(0, (received_page - 1) * page_size)

        def _query_scalar_int(sql_text):
            raw = sf_db(sql_text)
            if isinstance(raw, list):
                raw = raw[0] if raw else {}
            if isinstance(raw, dict):
                for value in raw.values():
                    try:
                        return int(value or 0)
                    except Exception:
                        continue
                return 0
            if isinstance(raw, (list, tuple)):
                try:
                    return int(raw[0] if len(raw) > 0 else 0)
                except Exception:
                    return 0
            try:
                return int(raw or 0)
            except Exception:
                return 0

        uploaded_total = _query_scalar_int(
            f"SELECT COUNT(1) AS total_count FROM baogao b WHERE {uploaded_where_sql}"
        )
        received_total = _query_scalar_int(
            f"SELECT COUNT(1) AS total_count FROM baogao b WHERE {received_where_sql}"
        )
        uploaded_total_pages = max(1, (uploaded_total + page_size - 1) // page_size) if uploaded_total else 1
        received_total_pages = max(1, (received_total + page_size - 1) // page_size) if received_total else 1
        uploaded_page = min(uploaded_page, uploaded_total_pages)
        received_page = min(received_page, received_total_pages)
        uploaded_offset = max(0, (uploaded_page - 1) * page_size)
        received_offset = max(0, (received_page - 1) * page_size)

        sql_uploaded = f"""
            SELECT
                b.WenDangID,
                b.RiQi,
                b.XingMing,
                b.BiaoTi,
                b.ZhengWen,
                b.TuPianLujin,
                b.LeiXing,
                b.RenYuanLeiXing,
                b.JieShouRen,
                ISNULL(d.DianZan, '') AS DianZan,
                ISNULL(d.PingJia, '') AS PingLun,
                ISNULL(d.HuiFu, '') AS HuiFu,
                ISNULL(d.YongHu, '') AS YongHu
            FROM baogao b
            LEFT JOIN BaoGao_dianzan d ON d.WenDangID = b.WenDangID
            WHERE {uploaded_where_sql}
            ORDER BY b.RiQi DESC
            OFFSET {uploaded_offset} ROWS FETCH NEXT {page_size} ROWS ONLY
        """
        sql_received = f"""
            SELECT
                b.WenDangID,
                b.RiQi,
                b.XingMing,
                b.BiaoTi,
                b.ZhengWen,
                b.TuPianLujin,
                b.LeiXing,
                b.RenYuanLeiXing,
                b.JieShouRen,
                ISNULL(d.DianZan, '') AS DianZan,
                ISNULL(d.PingJia, '') AS PingLun,
                ISNULL(d.HuiFu, '') AS HuiFu,
                ISNULL(d.YongHu, '') AS YongHu
            FROM baogao b
            LEFT JOIN BaoGao_dianzan d ON d.WenDangID = b.WenDangID
            WHERE {received_where_sql}
            ORDER BY b.RiQi DESC
            OFFSET {received_offset} ROWS FETCH NEXT {page_size} ROWS ONLY
        """
        rows_uploaded = sf_db(sql_uploaded) or []
        rows_received = sf_db(sql_received) or []

        def _norm_rows(rows):
            out = []
            if not isinstance(rows, list):
                rows = [rows]
            for row in rows:
                if isinstance(row, dict):
                    wid = str(row.get('WenDangID') or '').strip()
                    one = {
                        'wendangid': wid,
                        'source_doc_token': _xiaotu_extract_source_doc_token(wid),
                        'riqi': str(row.get('RiQi') or '').strip(),
                        'xingming': str(row.get('XingMing') or '').strip(),
                        'biaoti': str(row.get('BiaoTi') or '').strip(),
                        'zhengwen': str(row.get('ZhengWen') or '').strip(),
                        'tupianlujin': str(row.get('TuPianLujin') or '').strip(),
                        'leixing': str(row.get('LeiXing') or '').strip(),
                        'renyuanleixing': str(row.get('RenYuanLeiXing') or '').strip(),
                        'jieshouren': str(row.get('JieShouRen') or '').strip(),
                        'dianzan': str(row.get('DianZan') or row.get('dianzan') or '').strip(),
                        'pinglun': str(row.get('PingLun') or row.get('pinglun') or '').strip(),
                        'huifu': str(row.get('HuiFu') or row.get('huifu') or '').strip(),
                        'yonghu': str(row.get('YongHu') or row.get('yonghu') or '').strip(),
                        'report_url': _xiaotu_build_report_history_url(wid),
                    }
                else:
                    values = list(row) if isinstance(row, (list, tuple)) else []
                    wid = str(values[0] if len(values) > 0 else '').strip()
                    one = {
                        'wendangid': wid,
                        'source_doc_token': _xiaotu_extract_source_doc_token(wid),
                        'riqi': str(values[1] if len(values) > 1 else '').strip(),
                        'xingming': str(values[2] if len(values) > 2 else '').strip(),
                        'biaoti': str(values[3] if len(values) > 3 else '').strip(),
                        'zhengwen': str(values[4] if len(values) > 4 else '').strip(),
                        'tupianlujin': str(values[5] if len(values) > 5 else '').strip(),
                        'leixing': str(values[6] if len(values) > 6 else '').strip(),
                        'renyuanleixing': str(values[7] if len(values) > 7 else '').strip(),
                        'jieshouren': str(values[8] if len(values) > 8 else '').strip(),
                        'dianzan': str(values[9] if len(values) > 9 else '').strip(),
                        'pinglun': str(values[10] if len(values) > 10 else '').strip(),
                        'huifu': str(values[11] if len(values) > 11 else '').strip(),
                        'yonghu': str(values[12] if len(values) > 12 else '').strip(),
                        'report_url': _xiaotu_build_report_history_url(wid),
                    }
                one.update(_xiaotu_enrich_feedback_data(one, owner_name=one.get('xingming')))
                out.append(one)
            return out

        uploaded = _norm_rows(rows_uploaded)
        received = _norm_rows(rows_received)

        today_s = datetime.now().strftime('%Y-%m-%d')
        stats = {
            'uploaded_total': uploaded_total,
            'received_total': received_total,
            'uploaded_today': _query_scalar_int(
                f"SELECT COUNT(1) AS total_count FROM baogao b WHERE {uploaded_where_sql} AND CONVERT(varchar(10), b.RiQi, 23) = '{today_s}'"
            ),
            'received_today': _query_scalar_int(
                f"SELECT COUNT(1) AS total_count FROM baogao b WHERE {received_where_sql} AND CONVERT(varchar(10), b.RiQi, 23) = '{today_s}'"
            ),
            'received_unique_senders': _query_scalar_int(
                f"SELECT COUNT(DISTINCT ISNULL(NULLIF(LTRIM(RTRIM(b.XingMing)), ''), '')) AS total_count FROM baogao b WHERE {received_where_sql}"
            ),
        }
        return jsonify({
            'success': True,
            'data': {
                'filters': {
                    'name': uploaded_filter_name if can_view_all_uploads else filter_name,
                    'department_id': department_id,
                    'date_start': date_start,
                    'date_end': date_end,
                    'keyword': keyword,
                    'wendangid': focus_wid,
                },
                'permissions': {
                    'can_view_all_uploads': can_view_all_uploads,
                    'restricted_to_allowed_departments': restricted_to_allowed_departments,
                    'allowed_department_names': allowed_department_names,
                    'debug_scope_mode': str(history_scope.get('debug_mode') or 'current'),
                    'debug_enabled': history_debug_enabled,
                },
                'pagination': {
                    'uploaded': {
                        'page': min(uploaded_page, uploaded_total_pages),
                        'page_size': page_size,
                        'total': uploaded_total,
                        'total_pages': uploaded_total_pages,
                    },
                    'received': {
                        'page': min(received_page, received_total_pages),
                        'page_size': page_size,
                        'total': received_total,
                        'total_pages': received_total_pages,
                    }
                },
                'stats': stats,
                'uploaded': uploaded,
                'received': received,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取历史失败: {str(e)}'}), 500


def api_xiaotu_report_history_download(
    *,
    _xiaotu_build_history_export_html,
    _xiaotu_build_report_history_export_context,
    datetime,
    jsonify,
    re,
    request,
    send_file,
    session,
    sf_db,
):
    try:
        user_id = session.get('feishu_user_id')
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        session_user_name = str(session.get('feishu_user_name') or '').strip()
        ctx = _xiaotu_build_report_history_export_context(request.args, session_user_name)
        export_limit = 20000
        select_columns = """
            b.WenDangID,
            b.RiQi,
            b.XingMing,
            b.BiaoTi,
            b.ZhengWen,
            b.TuPianLujin,
            b.TuPianNeiRong,
            b.LeiXing,
            b.RenYuanLeiXing,
            b.JieShouRen,
            b.PingJia,
            ISNULL(d.DianZan, '') AS DianZan,
            ISNULL(d.PingJia, '') AS PingLun,
            ISNULL(d.HuiFu, '') AS HuiFu,
            ISNULL(d.YongHu, '') AS YongHu
        """
        sql_uploaded = f"""
            SELECT TOP {export_limit}
                {select_columns}
            FROM baogao b
            LEFT JOIN BaoGao_dianzan d ON d.WenDangID = b.WenDangID
            WHERE {ctx['uploaded_where_sql']}
            ORDER BY b.RiQi DESC
        """
        sql_received = f"""
            SELECT TOP {export_limit}
                {select_columns}
            FROM baogao b
            LEFT JOIN BaoGao_dianzan d ON d.WenDangID = b.WenDangID
            WHERE {ctx['received_where_sql']}
            ORDER BY b.RiQi DESC
        """
        rows_uploaded = sf_db(sql_uploaded) or []
        rows_received = sf_db(sql_received) or []
        from io import BytesIO
        html_text = _xiaotu_build_history_export_html(
            session_user_name,
            ctx,
            rows_uploaded,
            rows_received,
        )
        output = BytesIO(html_text.encode("utf-8"))
        output.seek(0)
        start_label = re.sub(r"[^0-9]", "", str(ctx.get("date_start") or "")) or "全部"
        end_label = re.sub(r"[^0-9]", "", str(ctx.get("date_end") or "")) or "全部"
        now_label = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"报告历史记录_{start_label}_to_{end_label}_{now_label}.html"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='text/html; charset=utf-8'
        )
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'下载历史记录失败: {str(e)}'}), 500


def api_xiaotu_report_history_analysis_file(
    *,
    _XIAOTU_REPORT_HISTORY_ANALYSIS_DIR,
    _xiaotu_build_name_scope_clause,
    _xiaotu_get_history_analysis_visible_user_names,
    _xiaotu_sql_escape,
    jsonify,
    os,
    relocate_storage_path,
    request,
    send_file,
    session,
    sf_db,
    unquote,
):
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        user_name = str(session.get('feishu_user_name') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        if not user_name:
            return jsonify({'success': False, 'message': '未获取到当前飞书用户名'}), 400
        raw_path = str(request.args.get('path') or '').strip()
        if not raw_path:
            return jsonify({'success': False, 'message': '缺少文件路径'}), 400
        normalized = relocate_storage_path(unquote(raw_path).strip().strip('"').strip("'"))
        abs_path = os.path.abspath(normalized)
        base = os.path.abspath(_XIAOTU_REPORT_HISTORY_ANALYSIS_DIR)
        if os.path.commonpath([base, abs_path]) != base:
            return jsonify({'success': False, 'message': '文件路径不在允许目录内'}), 403
        if not os.path.isfile(abs_path):
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        if os.path.splitext(abs_path)[1].lower() != ".html":
            return jsonify({'success': False, 'message': '只支持HTML文件'}), 400
        visible_scope = _xiaotu_get_history_analysis_visible_user_names(user_id, user_name)
        visible_name_clause = _xiaotu_build_name_scope_clause(
            "YongHu",
            list(visible_scope.get("user_names") or [user_name])
        )
        if not visible_name_clause:
            visible_name_clause = f"YongHu = N'{_xiaotu_sql_escape(user_name)}'"
        esc_path = _xiaotu_sql_escape(abs_path)
        matched_rows = sf_db(f"""
            SELECT TOP 1 ID
            FROM baogao_lishi
            WHERE WeiZhi = N'{esc_path}'
              AND {visible_name_clause}
        """) or []
        if not matched_rows:
            return jsonify({'success': False, 'message': '无权查看该报告历史文件'}), 403
        return send_file(abs_path, as_attachment=False, conditional=True)
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取历史分析文件失败: {str(e)}'}), 500


def api_xiaotu_report_history_analysis_list(
    *,
    _xiaotu_build_name_scope_clause,
    _xiaotu_get_history_analysis_visible_user_names,
    _xiaotu_sql_escape,
    jsonify,
    os,
    relocate_storage_path,
    session,
    sf_db,
    url_for,
):
    try:
        user_id = str(session.get('feishu_user_id') or '').strip()
        user_name = str(session.get('feishu_user_name') or '').strip()
        if not user_id:
            return jsonify({'success': False, 'message': '未登录'}), 401
        if not user_name:
            return jsonify({'success': False, 'message': '未获取到当前飞书用户名'}), 400
        visible_scope = _xiaotu_get_history_analysis_visible_user_names(user_id, user_name)
        visible_name_clause = _xiaotu_build_name_scope_clause(
            "YongHu",
            list(visible_scope.get("user_names") or [user_name])
        )
        if not visible_name_clause:
            visible_name_clause = f"YongHu = N'{_xiaotu_sql_escape(user_name)}'"
        rows = sf_db(f"""
            SELECT TOP 100 ID, YongHu, KaiShiRiQi, JieShuRIQi, WeiZhi
            FROM baogao_lishi
            WHERE {visible_name_clause}
            ORDER BY ID DESC
        """) or []
        items = []
        for row in rows:
            if isinstance(row, dict):
                rid = row.get("ID") or row.get("id")
                yonghu = row.get("YongHu") or row.get("yonghu")
                start_date = row.get("KaiShiRiQi") or row.get("kaishiriqi")
                end_date = row.get("JieShuRIQi") or row.get("jieshuriqi")
                path = row.get("WeiZhi") or row.get("weizhi")
            else:
                values = list(row) if isinstance(row, (list, tuple)) else []
                rid = values[0] if len(values) > 0 else ""
                yonghu = values[1] if len(values) > 1 else ""
                start_date = values[2] if len(values) > 2 else ""
                end_date = values[3] if len(values) > 3 else ""
                path = values[4] if len(values) > 4 else ""
            path_text = relocate_storage_path(path)
            exists = bool(path_text and os.path.isfile(path_text))
            items.append({
                "id": str(rid or "").strip(),
                "user_name": str(yonghu or "").strip(),
                "start_date": str(start_date or "").strip()[:10],
                "end_date": str(end_date or "").strip()[:10],
                "file_path": path_text,
                "file_url": url_for('api_xiaotu_report_history_analysis_file', path=path_text) if exists else "",
                "exists": exists,
            })
        return jsonify({
            'success': True,
            'data': {
                'user_name': user_name,
                'permissions': {
                    'is_department_leader': bool(visible_scope.get('is_department_leader')),
                    'department_names': list(visible_scope.get('department_names') or []),
                },
                'items': items,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取报告历史记录失败: {str(e)}'}), 500
