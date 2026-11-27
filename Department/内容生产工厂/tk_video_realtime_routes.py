"""TikTok real-time video reporting and account link management."""

from __future__ import annotations


def tk_video_realtime(
    *,
    render_template,
    session,
):
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('内容生产工厂/tk_video_realtime.html', user_name=user_name, user_id=user_id)


def tk_video_realtime_account_links(
    *,
    render_template,
    session,
):
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('内容生产工厂/tk_video_realtime_account_links.html', user_name=user_name, user_id=user_id)


def _tk_video_realtime_sql_text(value):
    return str(value or '').strip().replace("'", "''")


def _tk_video_realtime_pick(row, key):
    if isinstance(row, dict):
        return row.get(key) if key in row else row.get(key.upper())
    return None


def api_tk_video_realtime_account_links(
    *,
    _tk_video_realtime_pick,
    jsonify,
    sf_db,
):
    try:
        rows = sf_db(
            "SELECT DISTINCT dian, daren, fuzeren "
            "FROM TK_ZiYouZhangHao "
            "WHERE ISNULL(LTRIM(RTRIM(daren)), '') <> '' "
            "ORDER BY dian, fuzeren, daren"
        ) or []
        items = []
        for row in rows:
            if isinstance(row, dict):
                item = {
                    'dian': str(_tk_video_realtime_pick(row, 'dian') or '').strip(),
                    'daren': str(_tk_video_realtime_pick(row, 'daren') or '').strip(),
                    'fuzeren': str(_tk_video_realtime_pick(row, 'fuzeren') or '').strip(),
                }
            elif isinstance(row, (list, tuple)):
                item = {
                    'dian': str(row[0] if len(row) > 0 and row[0] is not None else '').strip(),
                    'daren': str(row[1] if len(row) > 1 and row[1] is not None else '').strip(),
                    'fuzeren': str(row[2] if len(row) > 2 and row[2] is not None else '').strip(),
                }
            else:
                item = {'dian': '', 'daren': '', 'fuzeren': ''}
            if not item['daren']:
                continue
            items.append(item)
        return jsonify({'success': True, 'data': {'items': items}})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取店铺负责人列表失败: {str(e)}'}), 500


def api_tk_video_realtime_account_links_save(
    *,
    _tk_video_realtime_sql_text,
    dui_db,
    jsonify,
    request,
    sf_db,
):
    try:
        data = request.get_json(silent=True) or {}
        dian = str(data.get('dian') or '').strip()
        daren = str(data.get('daren') or '').strip()
        fuzeren = str(data.get('fuzeren') or '').strip()
        original_dian = str(data.get('original_dian') or '').strip()
        original_daren = str(data.get('original_daren') or '').strip()
        original_fuzeren = str(data.get('original_fuzeren') or '').strip()

        if not dian:
            return jsonify({'success': False, 'message': '店铺不能为空'}), 400
        if not daren:
            return jsonify({'success': False, 'message': '账号不能为空'}), 400
        if not fuzeren:
            return jsonify({'success': False, 'message': '负责人不能为空'}), 400

        esc_dian = _tk_video_realtime_sql_text(dian)
        esc_daren = _tk_video_realtime_sql_text(daren)
        esc_fuzeren = _tk_video_realtime_sql_text(fuzeren)
        esc_original_dian = _tk_video_realtime_sql_text(original_dian)
        esc_original_daren = _tk_video_realtime_sql_text(original_daren)
        esc_original_fuzeren = _tk_video_realtime_sql_text(original_fuzeren)

        exists_sql = (
            "SELECT COUNT(1) AS total "
            "FROM TK_ZiYouZhangHao "
            f"WHERE dian = N'{esc_dian}' AND daren = N'{esc_daren}' AND fuzeren = N'{esc_fuzeren}'"
        )
        exists_count = int(sf_db(exists_sql, single=True) or 0)

        if original_daren:
            update_sql = f"""
            UPDATE TK_ZiYouZhangHao
            SET dian = N'{esc_dian}',
                daren = N'{esc_daren}',
                fuzeren = N'{esc_fuzeren}'
            WHERE ISNULL(dian, '') = N'{esc_original_dian}'
              AND ISNULL(daren, '') = N'{esc_original_daren}'
              AND ISNULL(fuzeren, '') = N'{esc_original_fuzeren}'
            """
            dui_db(update_sql)
            action = 'updated'
        else:
            if exists_count > 0:
                return jsonify({'success': False, 'message': '相同的店铺、账号、负责人记录已存在'}), 400
            insert_sql = (
                "INSERT INTO TK_ZiYouZhangHao (dian, daren, fuzeren) "
                f"VALUES (N'{esc_dian}', N'{esc_daren}', N'{esc_fuzeren}')"
            )
            dui_db(insert_sql)
            action = 'inserted'

        return jsonify({'success': True, 'message': '保存成功', 'data': {'action': action}})
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存店铺负责人失败: {str(e)}'}), 500


def api_tk_video_realtime_account_links_delete(
    *,
    _tk_video_realtime_sql_text,
    dui_db,
    jsonify,
    request,
):
    try:
        data = request.get_json(silent=True) or {}
        dian = str(data.get('dian') or '').strip()
        daren = str(data.get('daren') or '').strip()
        fuzeren = str(data.get('fuzeren') or '').strip()
        if not daren:
            return jsonify({'success': False, 'message': '缺少账号，无法删除'}), 400
        esc_dian = _tk_video_realtime_sql_text(dian)
        esc_daren = _tk_video_realtime_sql_text(daren)
        esc_fuzeren = _tk_video_realtime_sql_text(fuzeren)
        delete_sql = f"""
        DELETE FROM TK_ZiYouZhangHao
        WHERE ISNULL(dian, '') = N'{esc_dian}'
          AND ISNULL(daren, '') = N'{esc_daren}'
          AND ISNULL(fuzeren, '') = N'{esc_fuzeren}'
        """
        dui_db(delete_sql)
        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除店铺负责人失败: {str(e)}'}), 500


def api_tk_video_realtime_shops(
    *,
    jsonify,
    sf_db,
):
    try:
        rows = sf_db(
            "SELECT DISTINCT dian FROM TK_ZiYouZhangHao "
            "WHERE dian IS NOT NULL AND LTRIM(RTRIM(dian)) <> '' "
            "ORDER BY dian"
        ) or []
        shops = []
        for r in rows:
            if isinstance(r, dict):
                v = r.get('dian') or r.get('DIAN') or ''
            elif isinstance(r, (list, tuple)) and r:
                v = r[0]
            else:
                v = r
            v = str(v).strip()
            if v:
                shops.append(v)
        return jsonify({'success': True, 'data': {'shops': shops}})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取店铺列表失败: {str(e)}'}), 500


def api_tk_video_realtime_daren(
    *,
    jsonify,
    request,
    sf_db,
):
    try:
        def _parse_list_param(name, max_items=200):
            vals = request.args.getlist(name) or []
            parts = []
            for v in vals:
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                for p in s.replace('，', ',').split(','):
                    p = (p or '').strip()
                    if not p or p.upper() == 'ALL':
                        continue
                    parts.append(p)
            out = []
            seen = set()
            for p in parts:
                if p in seen:
                    continue
                seen.add(p)
                out.append(p)
                if len(out) >= max_items:
                    break
            return out

        dian_list = _parse_list_param('dian')
        fuzeren_list = _parse_list_param('fuzeren')
        where = "WHERE daren IS NOT NULL AND LTRIM(RTRIM(daren)) <> ''"
        if dian_list:
            dian_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in dian_list])
            where += f" AND dian IN ({dian_in})"
        if fuzeren_list:
            fuzeren_in = ", ".join([("'" + str(x).replace("'", "''") + "'") for x in fuzeren_list])
            where += f" AND fuzeren IN ({fuzeren_in})"
        rows = sf_db(
            "SELECT DISTINCT daren FROM TK_ZiYouZhangHao "
            f"{where} "
            "ORDER BY daren"
        ) or []
        daren_list = []
        for r in rows:
            if isinstance(r, dict):
                v = r.get('daren') or r.get('DAREN') or ''
            elif isinstance(r, (list, tuple)) and r:
                v = r[0]
            else:
                v = r
            v = str(v).strip()
            if v:
                daren_list.append(v)
        return jsonify({'success': True, 'data': {'daren': daren_list}})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取达人列表失败: {str(e)}'}), 500


def api_tk_video_realtime_fuzeren(
    *,
    jsonify,
    request,
    sf_db,
):
    try:
        def _parse_list_param(name, max_items=200):
            vals = request.args.getlist(name) or []
            parts = []
            for v in vals:
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                for p in s.replace('，', ',').split(','):
                    p = (p or '').strip()
                    if not p or p.upper() == 'ALL':
                        continue
                    parts.append(p)
            out = []
            seen = set()
            for p in parts:
                if p in seen:
                    continue
                seen.add(p)
                out.append(p)
                if len(out) >= max_items:
                    break
            return out

        dian_list = _parse_list_param('dian')
        daren_list = _parse_list_param('daren')
        where = "WHERE fuzeren IS NOT NULL AND LTRIM(RTRIM(fuzeren)) <> ''"
        if dian_list:
            dian_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in dian_list])
            where += f" AND dian IN ({dian_in})"
        if daren_list:
            daren_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in daren_list])
            where += f" AND daren IN ({daren_in})"
        rows = sf_db(
            "SELECT DISTINCT fuzeren FROM TK_ZiYouZhangHao "
            f"{where} "
            "ORDER BY fuzeren"
        ) or []
        fuzeren_list = []
        for r in rows:
            if isinstance(r, dict):
                v = r.get('fuzeren') or r.get('FUZEREN') or ''
            elif isinstance(r, (list, tuple)) and r:
                v = r[0]
            else:
                v = r
            v = str(v).strip()
            if v:
                fuzeren_list.append(v)
        return jsonify({'success': True, 'data': {'fuzeren': fuzeren_list}})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取负责人列表失败: {str(e)}'}), 500


def api_tk_video_realtime_videos(
    *,
    jsonify,
    re,
    request,
    sf_db,
):
    try:
        def _parse_list_param(name, max_items=200):
            vals = request.args.getlist(name) or []
            parts = []
            for v in vals:
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                for p in s.replace('，', ',').split(','):
                    p = (p or '').strip()
                    if not p or p.upper() == 'ALL':
                        continue
                    parts.append(p)
            out = []
            seen = set()
            for p in parts:
                if p in seen:
                    continue
                seen.add(p)
                out.append(p)
                if len(out) >= max_items:
                    break
            return out

        dian_list = _parse_list_param('dian')
        daren_list = _parse_list_param('daren')
        fuzeren_list = _parse_list_param('fuzeren')
        created_start = (request.args.get('created_start') or '').strip()
        created_end = (request.args.get('created_end') or '').strip()
        view_range = (request.args.get('view_range') or '').strip()
        if created_start and (not re.match(r'^\d{4}-\d{2}-\d{2}$', created_start)):
            return jsonify({'success': False, 'message': '创建日期开始格式无效，应为YYYY-MM-DD'}), 400
        if created_end and (not re.match(r'^\d{4}-\d{2}-\d{2}$', created_end)):
            return jsonify({'success': False, 'message': '创建日期结束格式无效，应为YYYY-MM-DD'}), 400
        if created_start and created_end and created_start > created_end:
            return jsonify({'success': False, 'message': '创建日期开始不能晚于结束日期'}), 400
        valid_view_ranges = {'0_20000', '20000_100000', '100000_1000000', '1000000_plus'}
        if view_range and view_range not in valid_view_ranges:
            return jsonify({'success': False, 'message': '播放量区间参数无效'}), 400
        page = int(request.args.get('page') or 1)
        page_size = int(request.args.get('page_size') or 50)
        page = max(1, page)
        page_size = max(1, min(200, page_size))
        offset = (page - 1) * page_size

        def _parse_int_from_rows(rows, key):
            if not rows:
                return 0
            r0 = rows[0]
            if isinstance(r0, dict):
                return int(r0.get(key) or r0.get(key.upper()) or 0)
            if isinstance(r0, (list, tuple)) and r0:
                return int(r0[0] or 0)
            return int(r0 or 0)

        where_parts = ["l.rn = 1"]
        join_account_all_sql = "LEFT JOIN (SELECT daren, MAX(dian) AS dian, MAX(fuzeren) AS fuzeren FROM TK_ZiYouZhangHao GROUP BY daren) a ON a.daren = l.daren"
        join_account_filtered_sql = join_account_all_sql
        join_account_raw_filtered_sql = ""
        account_filters = []
        if dian_list:
            dian_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in dian_list])
            account_filters.append(f"dian IN ({dian_in})")
        if fuzeren_list:
            fuzeren_in = ", ".join([("'" + str(x).replace("'", "''") + "'") for x in fuzeren_list])
            account_filters.append(f"fuzeren IN ({fuzeren_in})")
        if account_filters:
            account_where_sql = " WHERE " + " AND ".join(account_filters)
            join_account_filtered_sql = (
                "INNER JOIN ("
                "  SELECT daren, MAX(dian) AS dian, MAX(fuzeren) AS fuzeren "
                "  FROM TK_ZiYouZhangHao "
                f"  {account_where_sql} "
                "  GROUP BY daren"
                ") a ON a.daren = l.daren"
            )
            join_account_raw_filtered_sql = (
                "INNER JOIN ("
                "  SELECT daren "
                "  FROM TK_ZiYouZhangHao "
                f"  {account_where_sql} "
                "  GROUP BY daren"
                ") a ON a.daren = v.daren"
            )
        if daren_list:
            daren_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in daren_list])
            where_parts.append(f"l.daren IN ({daren_in})")
        if created_start:
            where_parts.append(
                f"ISDATE(l.chuangjianshijian) = 1 AND CONVERT(datetime, l.chuangjianshijian) >= '{created_start} 00:00:00'"
            )
        if created_end:
            where_parts.append(
                f"ISDATE(l.chuangjianshijian) = 1 AND CONVERT(datetime, l.chuangjianshijian) <= '{created_end} 23:59:59'"
            )
        if view_range:
            view_num_l = "CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.bofangshu)), ',', '')) = 1 THEN CAST(REPLACE(LTRIM(RTRIM(l.bofangshu)), ',', '') AS float) ELSE -1 END"
            if view_range == '0_20000':
                where_parts.append(f"{view_num_l} >= 0 AND {view_num_l} < 20000")
            elif view_range == '20000_100000':
                where_parts.append(f"{view_num_l} >= 20000 AND {view_num_l} < 100000")
            elif view_range == '100000_1000000':
                where_parts.append(f"{view_num_l} >= 100000 AND {view_num_l} < 1000000")
            elif view_range == '1000000_plus':
                where_parts.append(f"{view_num_l} >= 1000000")
        where_sql = " AND ".join(where_parts)

        raw_where_parts = []
        if daren_list:
            daren_in = ", ".join([("'" + str(d).replace("'", "''") + "'") for d in daren_list])
            raw_where_parts.append(f"v.daren IN ({daren_in})")
        if created_start:
            raw_where_parts.append(
                f"ISDATE(v.chuangjianshijian) = 1 AND CONVERT(datetime, v.chuangjianshijian) >= '{created_start} 00:00:00'"
            )
        if created_end:
            raw_where_parts.append(
                f"ISDATE(v.chuangjianshijian) = 1 AND CONVERT(datetime, v.chuangjianshijian) <= '{created_end} 23:59:59'"
            )
        if view_range:
            view_num_v = "CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(v.bofangshu)), ',', '')) = 1 THEN CAST(REPLACE(LTRIM(RTRIM(v.bofangshu)), ',', '') AS float) ELSE -1 END"
            if view_range == '0_20000':
                raw_where_parts.append(f"{view_num_v} >= 0 AND {view_num_v} < 20000")
            elif view_range == '20000_100000':
                raw_where_parts.append(f"{view_num_v} >= 20000 AND {view_num_v} < 100000")
            elif view_range == '100000_1000000':
                raw_where_parts.append(f"{view_num_v} >= 100000 AND {view_num_v} < 1000000")
            elif view_range == '1000000_plus':
                raw_where_parts.append(f"{view_num_v} >= 1000000")
        raw_where_sql = " AND ".join(raw_where_parts) if raw_where_parts else "1=1"
        order_where_parts = []
        if created_start:
            order_where_parts.append(
                f"ISDATE(o.chuangjianshijian) = 1 AND CONVERT(datetime, o.chuangjianshijian) >= '{created_start} 00:00:00'"
            )
        if created_end:
            order_where_parts.append(
                f"ISDATE(o.chuangjianshijian) = 1 AND CONVERT(datetime, o.chuangjianshijian) <= '{created_end} 23:59:59'"
            )
        order_where_sql = " AND ".join(order_where_parts) if order_where_parts else "1=1"
        total_raw_all = _parse_int_from_rows(
            sf_db("SELECT COUNT(1) AS total_raw_all FROM TK_ZiYouZhangHao_ShiPinShuJu") or [],
            "total_raw_all"
        )
        total_raw_filtered = _parse_int_from_rows(
            sf_db(
                "SELECT COUNT(1) AS total_raw_filtered "
                "FROM TK_ZiYouZhangHao_ShiPinShuJu v "
                f"{join_account_raw_filtered_sql} "
                f"WHERE {raw_where_sql}"
            ) or [],
            "total_raw_filtered"
        )

        count_rows = sf_db(
            "WITH latest AS ("
            "  SELECT v.*, ROW_NUMBER() OVER ("
            "    PARTITION BY v.daren, v.shipinid "
            "    ORDER BY "
            "      CASE "
            "        WHEN v.xuhao IS NULL THEN 0 "
            "        WHEN PATINDEX('%%[^0-9]%%', LTRIM(RTRIM(CAST(v.xuhao AS varchar(50))))) = 0 "
            "          THEN CAST(LTRIM(RTRIM(CAST(v.xuhao AS varchar(50)))) AS bigint) "
            "        ELSE 0 "
            "      END DESC, "
            "      v.zhuaqushijian DESC"
            "  ) AS rn "
            "  FROM TK_ZiYouZhangHao_ShiPinShuJu v"
            ") "
            "SELECT COUNT(1) AS total "
            "FROM latest l "
            f"{join_account_filtered_sql} "
            f"WHERE {where_sql}"
        ) or []
        total = _parse_int_from_rows(count_rows, 'total')

        def _parse_agg_row(row):
            if not row:
                return {
                    'video_count': 0,
                    'sum_duration_seconds': 0.0,
                    'sum_likes': 0.0,
                    'sum_views': 0.0,
                    'sum_jine': 0.0,
                    'sum_purchase_count': 0,
                    'sum_comments': 0.0,
                    'sum_favorites': 0.0,
                    'sum_shares': 0.0,
                }
            if isinstance(row, dict):
                getv = lambda k: row.get(k) if k in row else row.get(k.upper())
                return {
                    'video_count': int(getv('video_count') or 0),
                    'sum_duration_seconds': float(getv('sum_duration_seconds') or 0),
                    'sum_likes': float(getv('sum_likes') or 0),
                    'sum_views': float(getv('sum_views') or 0),
                    'sum_jine': float(getv('sum_jine') or 0),
                    'sum_purchase_count': int(getv('sum_purchase_count') or 0),
                    'sum_comments': float(getv('sum_comments') or 0),
                    'sum_favorites': float(getv('sum_favorites') or 0),
                    'sum_shares': float(getv('sum_shares') or 0),
                }
            if isinstance(row, (list, tuple)):
                vals = list(row) + [0] * 9
                return {
                    'video_count': int(vals[0] or 0),
                    'sum_duration_seconds': float(vals[1] or 0),
                    'sum_likes': float(vals[2] or 0),
                    'sum_views': float(vals[3] or 0),
                    'sum_jine': float(vals[4] or 0),
                    'sum_purchase_count': int(vals[5] or 0),
                    'sum_comments': float(vals[6] or 0),
                    'sum_favorites': float(vals[7] or 0),
                    'sum_shares': float(vals[8] or 0),
                }
            return {
                'video_count': 0,
                'sum_duration_seconds': 0.0,
                'sum_likes': 0.0,
                'sum_views': 0.0,
                'sum_jine': 0.0,
                'sum_purchase_count': 0,
                'sum_comments': 0.0,
                'sum_favorites': 0.0,
                'sum_shares': 0.0,
            }

        agg_sql_base = (
            "WITH latest AS ("
            "  SELECT v.*, ROW_NUMBER() OVER ("
            "    PARTITION BY v.daren, v.shipinid "
            "    ORDER BY "
            "      CASE "
            "        WHEN v.xuhao IS NULL THEN 0 "
            "        WHEN PATINDEX('%%[^0-9]%%', LTRIM(RTRIM(CAST(v.xuhao AS varchar(50))))) = 0 "
            "          THEN CAST(LTRIM(RTRIM(CAST(v.xuhao AS varchar(50)))) AS bigint) "
            "        ELSE 0 "
            "      END DESC, "
            "      v.zhuaqushijian DESC"
            "  ) AS rn "
            "  FROM TK_ZiYouZhangHao_ShiPinShuJu v"
            "), order_sum AS ("
            "  SELECT "
            "    LTRIM(RTRIM(CAST(o.shipinid AS varchar(100)))) AS shipinid_key, "
            "    COUNT(1) AS purchase_count, "
            "    SUM(CASE "
            "      WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(CAST(o.jine AS varchar(100)))), ',', '')) = 1 "
            "        THEN CAST(REPLACE(LTRIM(RTRIM(CAST(o.jine AS varchar(100)))), ',', '') AS float) "
            "      ELSE 0 END) AS jine_sum "
            "  FROM tk_bddingdan o "
            f"  WHERE {order_where_sql} "
            "  GROUP BY LTRIM(RTRIM(CAST(o.shipinid AS varchar(100))))"
            ") "
            "SELECT "
            "  COUNT(1) AS video_count, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.shichang)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.shichang)), ',', '') AS float) ELSE 0 END) AS sum_duration_seconds, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.dianzanshu)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.dianzanshu)), ',', '') AS float) ELSE 0 END) AS sum_likes, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.bofangshu)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.bofangshu)), ',', '') AS float) ELSE 0 END) AS sum_views, "
            "  SUM(ISNULL(os.jine_sum, 0)) AS sum_jine, "
            "  SUM(ISNULL(os.purchase_count, 0)) AS sum_purchase_count, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.pinglunshu)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.pinglunshu)), ',', '') AS float) ELSE 0 END) AS sum_comments, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.shoucangshu)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.shoucangshu)), ',', '') AS float) ELSE 0 END) AS sum_favorites, "
            "  SUM(CASE WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(l.fenxiangshu)), ',', '')) = 1 "
            "      THEN CAST(REPLACE(LTRIM(RTRIM(l.fenxiangshu)), ',', '') AS float) ELSE 0 END) AS sum_shares "
            "FROM latest l "
            "LEFT JOIN order_sum os ON os.shipinid_key = LTRIM(RTRIM(CAST(l.shipinid AS varchar(100)))) "
        )
        agg_all_sql = f"{agg_sql_base} {join_account_all_sql} "
        agg_filtered_sql = f"{agg_sql_base} {join_account_filtered_sql} "

        agg_all_rows = sf_db(
            f"{agg_all_sql} WHERE l.rn = 1"
        ) or []
        agg_filtered_rows = sf_db(
            f"{agg_filtered_sql} WHERE {where_sql}"
        ) or []
        aggregate_all = _parse_agg_row(agg_all_rows[0] if agg_all_rows else None)
        aggregate_filtered = _parse_agg_row(agg_filtered_rows[0] if agg_filtered_rows else None)

        start_row = offset + 1
        end_row = offset + page_size
        list_sql = (
            "WITH latest AS ("
            "  SELECT v.*, ROW_NUMBER() OVER ("
            "    PARTITION BY v.daren, v.shipinid "
            "    ORDER BY "
            "      CASE "
            "        WHEN v.xuhao IS NULL THEN 0 "
            "        WHEN PATINDEX('%%[^0-9]%%', LTRIM(RTRIM(CAST(v.xuhao AS varchar(50))))) = 0 "
            "          THEN CAST(LTRIM(RTRIM(CAST(v.xuhao AS varchar(50)))) AS bigint) "
            "        ELSE 0 "
            "      END DESC, "
            "      v.zhuaqushijian DESC"
            "  ) AS rn "
            "  FROM TK_ZiYouZhangHao_ShiPinShuJu v"
            "), order_sum AS ("
            "  SELECT "
            "    LTRIM(RTRIM(CAST(o.shipinid AS varchar(100)))) AS shipinid_key, "
            "    COUNT(1) AS purchase_count, "
            "    SUM(CASE "
            "      WHEN ISNUMERIC(REPLACE(LTRIM(RTRIM(CAST(o.jine AS varchar(100)))), ',', '')) = 1 "
            "        THEN CAST(REPLACE(LTRIM(RTRIM(CAST(o.jine AS varchar(100)))), ',', '') AS float) "
            "      ELSE 0 END) AS jine_sum "
            "  FROM tk_bddingdan o "
            f"  WHERE {order_where_sql} "
            "  GROUP BY LTRIM(RTRIM(CAST(o.shipinid AS varchar(100))))"
            "), filtered AS ("
            "  SELECT "
            "    a.dian AS dian, l.daren AS daren, a.fuzeren AS fuzeren, l.shipinid AS shipinid, "
            "    l.chuangjianshijian AS chuangjianshijian, l.biaoti AS biaoti, l.tag AS tag, "
            "    l.shichang AS shichang, l.dianzanshu AS dianzanshu, l.bofangshu AS bofangshu, "
            "    l.pinglunshu AS pinglunshu, l.shoucangshu AS shoucangshu, l.fenxiangshu AS fenxiangshu, "
            "    ISNULL(os.jine_sum, 0) AS jine_sum, "
            "    ISNULL(os.purchase_count, 0) AS purchase_count, "
            "    l.zhuaqushijian AS zhuaqushijian, "
            "    ROW_NUMBER() OVER (ORDER BY l.zhuaqushijian DESC) AS _rownum "
            "  FROM latest l "
            f"  {join_account_filtered_sql} "
            "  LEFT JOIN order_sum os ON os.shipinid_key = LTRIM(RTRIM(CAST(l.shipinid AS varchar(100)))) "
            f"  WHERE {where_sql}"
            ") "
            "SELECT dian, daren, fuzeren, shipinid, chuangjianshijian, biaoti, tag, shichang, "
            "       dianzanshu, bofangshu, pinglunshu, shoucangshu, fenxiangshu, jine_sum, purchase_count, zhuaqushijian "
            "FROM filtered "
            f"WHERE _rownum BETWEEN {start_row} AND {end_row} "
            "ORDER BY _rownum"
        )
        rows = sf_db(
            list_sql
        ) or []

        cols = [
            'dian', 'daren', 'fuzeren', 'shipinid', 'chuangjianshijian', 'biaoti', 'tag', 'shichang',
            'dianzanshu', 'bofangshu', 'pinglunshu', 'shoucangshu', 'fenxiangshu', 'jine_sum', 'purchase_count', 'zhuaqushijian'
        ]
        items = []
        for r in rows:
            if isinstance(r, dict):
                item = {k: (r.get(k) if k in r else r.get(k.upper())) for k in cols}
            elif isinstance(r, (list, tuple)):
                item = {cols[i]: (r[i] if i < len(r) else None) for i in range(len(cols))}
            else:
                item = {}
            shipinid = (item.get('shipinid') or '').strip() if isinstance(item.get('shipinid'), str) else str(item.get('shipinid') or '').strip()
            item['video_url'] = f"https://www.tiktok.com/@lunavale0128/video/{shipinid}" if shipinid else ''
            items.append(item)

        return jsonify({
            'success': True,
            'data': {
                'items': items,
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_raw_all': total_raw_all,
                'total_raw_filtered': total_raw_filtered,
                'aggregate_all': aggregate_all,
                'aggregate_filtered': aggregate_filtered
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取视频数据失败: {str(e)}'}), 500
