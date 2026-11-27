"""TikTok invite monitoring and influencer registration routes."""

from __future__ import annotations


def tk_invite_monitor(
    *,
    render_template,
    session,
):
    """邀请ID实时监控上传页面"""
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('内容生产工厂/tk_invite_monitor.html', user_name=user_name, user_id=user_id)


def upload_invite_ids(
    *,
    dui_db,
    jsonify,
    request,
    session,
    sf_db,
):
    """上传Excel并批量写入 tk_yaoqingma(邀请码, 日期, BD, 店铺)"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未发现文件，请选择Excel文件后重试'})

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'})

        # 读取Excel（兼容xlsx/xls），优先使用pandas
        import pandas as pd
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return jsonify({'success': False, 'message': f'读取Excel失败: {str(e)}'})

        # 标准化列名：兼容“邀请id/邀请码”和“截止日期/日期/店铺”
        normalized_cols = {str(c).strip(): c for c in df.columns}
        id_col = None
        date_col = None
        store_col = None
        for cand in ['邀请id', '邀请码', '邀请ID', '邀请码ID']:
            if cand in normalized_cols:
                id_col = normalized_cols[cand]
                break
        for cand in ['截止日期', '日期', '到期日期', '截止时间']:
            if cand in normalized_cols:
                date_col = normalized_cols[cand]
                break
        for cand in ['店铺', '店铺编号', '店号']:
            if cand in normalized_cols:
                store_col = normalized_cols[cand]
                break

        if not id_col or not date_col or not store_col:
            return jsonify({'success': False, 'message': 'Excel缺少必要列：需要包含“邀请id/邀请码”、“截止日期/日期”和“店铺”列（店铺示例：80、81、82）'})

        bd_name = session.get('feishu_user_name', '')
        bd_name_safe = str(bd_name).replace("'", "''")

        store_in_db = True
        try:
            tb_cols = sf_db("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'tk_yaoqingma' ORDER BY ORDINAL_POSITION") or []
            col_names = []
            for c in tb_cols:
                if isinstance(c, (list, tuple)):
                    col_names.append(str(c[0]))
                elif isinstance(c, dict):
                    col_names.append(str(c.get('COLUMN_NAME') or c.get('column_name') or ''))
                else:
                    col_names.append(str(c))
            col_names = [name for name in col_names if name]
            store_in_db = ('店铺' in col_names)
        except Exception:
            store_in_db = True

        inserted = 0
        errors = []
        warnings = []
        warned_no_store_col = False
        for idx, row in df.iterrows():
            invite_val = row.get(id_col)
            date_val = row.get(date_col)
            store_val = row.get(store_col)
            if pd.isna(invite_val) or str(invite_val).strip() == '':
                errors.append(f'第{idx+1}行邀请码为空，跳过')
                continue

            invite_safe = str(invite_val).strip().replace("'", "''")

            try:
                if pd.isna(date_val) or str(date_val).strip() == '':
                    raise ValueError('日期为空')
                if hasattr(date_val, 'strftime'):
                    date_safe = date_val.strftime('%Y-%m-%d')
                else:
                    from datetime import datetime
                    date_safe = datetime.strptime(str(date_val).strip(), '%Y-%m-%d').strftime('%Y-%m-%d')
            except Exception:
                errors.append(f'第{idx+1}行日期格式不正确，需YYYY-MM-DD，当前值: {date_val}')
                continue

            try:
                store_code = None
                if pd.isna(store_val) or str(store_val).strip() == '':
                    raise ValueError('店铺为空')
                store_str = str(store_val).strip()
                if isinstance(store_val, (int, float)):
                    store_code = str(int(float(store_val)))
                else:
                    import re
                    if re.fullmatch(r'\d+', store_str):
                        store_code = store_str
                    else:
                        raise ValueError('店铺需为数字')
                store_safe = store_code.replace("'", "''")
            except Exception:
                errors.append(f'第{idx+1}行店铺格式错误：{store_val}（需为数字，如80、81、82）')
                continue

            if store_in_db:
                sql = f"""
                INSERT INTO tk_yaoqingma (邀请码, 日期, BD, 店铺)
                VALUES ('{invite_safe}', '{date_safe}', '{bd_name_safe}', '{store_safe}')
                """
            else:
                sql = f"""
                INSERT INTO tk_yaoqingma (邀请码, 日期, BD)
                VALUES ('{invite_safe}', '{date_safe}', '{bd_name_safe}')
                """
                if not warned_no_store_col:
                    warnings.append('数据库未检测到“店铺”列，已忽略写入该字段')
                    warned_no_store_col = True
            try:
                expire_sql = f"""
                UPDATE tk_yaoqingma
                SET 日期 = '2000-01-01'
                WHERE 邀请码 = '{invite_safe}'
                """
                dui_db(expire_sql)

                dui_db(sql)
                inserted += 1
            except Exception as e:
                errors.append(f'第{idx+1}行插入失败: {str(e)}')

        return jsonify({
            'success': True,
            'inserted': inserted,
            'errors': errors,
            'warnings': warnings,
            'message': f'上传完成，成功插入 {inserted} 条记录，{len(errors)} 条失败'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'上传处理异常: {str(e)}'})


def upload_wanghong_register(
    *,
    datetime,
    dui_db,
    jsonify,
    request,
    session,
    sf_db,
):
    """上传Excel并写入 TK_wanghongming_dengji(BD, WangHongMing, Dian, DaoRuShiJian)"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未发现文件，请选择Excel文件后重试'})

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'})

        import pandas as pd
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return jsonify({'success': False, 'message': f'读取Excel失败: {str(e)}'})

        normalized_cols = {str(c).strip(): c for c in df.columns}
        name_col = None
        store_col = None
        for cand in ['网红名', '红人名', '达人名', '网红', '红人', '达人', 'WangHongMing']:
            if cand in normalized_cols:
                name_col = normalized_cols[cand]
                break
        for cand in ['店', '店铺', '店铺编号', '店号', 'Dian']:
            if cand in normalized_cols:
                store_col = normalized_cols[cand]
                break

        if not name_col or not store_col:
            return jsonify({'success': False, 'message': 'Excel缺少必要列：需要包含“网红名”和“店/店铺”列'})

        bd_name = session.get('feishu_user_name', '')
        bd_name_safe = str(bd_name).replace("'", "''")

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        inserted = 0
        updated = 0
        errors = []

        for idx, row in df.iterrows():
            name_val = row.get(name_col)
            store_val = row.get(store_col)

            if pd.isna(name_val) or str(name_val).strip() == '':
                errors.append(f'第{idx+1}行网红名为空，跳过')
                continue
            if pd.isna(store_val) or str(store_val).strip() == '':
                errors.append(f'第{idx+1}行店铺为空，跳过')
                continue

            name_safe = str(name_val).strip().replace("'", "''")
            store_safe = ''
            try:
                if isinstance(store_val, (int, float)) and str(store_val).strip() != '':
                    store_safe = str(int(float(store_val))).strip()
                else:
                    store_safe = str(store_val).strip()
            except Exception:
                store_safe = str(store_val).strip()
            store_safe = store_safe.replace("'", "''")
            if store_safe == '':
                errors.append(f'第{idx+1}行店铺格式错误：{store_val}')
                continue

            try:
                exists_sql = f"SELECT COUNT(1) FROM TK_wanghongming_dengji WHERE WangHongMing = '{name_safe}' AND Dian = '{store_safe}'"
                exists = sf_db(exists_sql, single=True)
                exists = int(exists or 0)
            except Exception as e:
                errors.append(f'第{idx+1}行查询失败: {str(e)}')
                continue

            try:
                if exists > 0:
                    sql = f"""
                        UPDATE TK_wanghongming_dengji
                        SET DaoRuShiJian = '{now_str}', BD = '{bd_name_safe}', TongZhiShiJian = NULL
                        WHERE WangHongMing = '{name_safe}' AND Dian = '{store_safe}'
                    """
                    dui_db(sql)
                    updated += 1
                else:
                    sql = f"""
                        INSERT INTO TK_wanghongming_dengji (BD, WangHongMing, Dian, DaoRuShiJian)
                        VALUES ('{bd_name_safe}', '{name_safe}', '{store_safe}', '{now_str}')
                    """
                    dui_db(sql)
                    inserted += 1
            except Exception as e:
                errors.append(f'第{idx+1}行写入失败: {str(e)}')

        return jsonify({
            'success': True,
            'inserted': inserted,
            'updated': updated,
            'errors': errors,
            'message': f'导入完成：新增 {inserted} 条，更新 {updated} 条，失败 {len(errors)} 条'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'上传处理异常: {str(e)}'})


def list_invite_codes(
    *,
    jsonify,
    session,
    sf_db,
):
    try:
        user_name = session.get('feishu_user_name', '')
        if not user_name:
            return jsonify({'success': False, 'message': '未登录'}), 401

        bd_name_safe = str(user_name).replace("'", "''")
        sql = f"""
            SELECT 邀请码, 日期
            FROM tk_yaoqingma
            WHERE BD = '{bd_name_safe}'
            ORDER BY 日期 DESC
        """
        rows = sf_db(sql) or []
        data = []
        from datetime import datetime, date
        for r in rows:
            invite = r[0] if len(r) > 0 else ''
            raw_date = r[1] if len(r) > 1 else ''
            formatted = ''
            try:
                if isinstance(raw_date, datetime):
                    formatted = raw_date.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                elif isinstance(raw_date, date):
                    formatted = datetime(raw_date.year, raw_date.month, raw_date.day).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                else:
                    # 尝试解析字符串
                    s = str(raw_date)
                    try:
                        # 兼容 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM:SS'
                        fmt = '%Y-%m-%d %H:%M:%S' if ' ' in s else '%Y-%m-%d'
                        dt = datetime.strptime(s[:19], fmt)
                        formatted = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    except Exception:
                        formatted = s
            except Exception:
                formatted = str(raw_date)

            data.append({
                'invite_code': invite,
                'date': formatted
            })
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'查询失败: {str(e)}'}), 500


def list_unchecked_invite_codes_12h(
    *,
    jsonify,
    sf_db,
):
    """
    查询“12小时之内还未检查的邀请码”：
    使用提供的 SQL 条件：
        SELECT ID, 邀请码, BD, 日期
        FROM tk_yaoqingma
        WHERE 日期 >= GETDATE()
          AND 导入时间 <= DATEADD(HOUR, -12, GETDATE());
    """
    try:
        sql = """
            SELECT ID, 邀请码, BD, 日期, 店铺
            FROM tk_yaoqingma
            WHERE 日期 >= GETDATE()
              AND 导入时间 <= DATEADD(HOUR, -12, GETDATE())
            ORDER BY 日期 ASC, ID ASC
        """
        rows = sf_db(sql) or []
        from datetime import datetime, date
        data = []
        store_counts = {}
        for r in rows:
            row_id = r[0] if len(r) > 0 else None
            invite = r[1] if len(r) > 1 else ''
            bd_name = r[2] if len(r) > 2 else ''
            raw_date = r[3] if len(r) > 3 else None
            store = r[4] if len(r) > 4 else ''
            store_str = '' if store is None else str(store).strip()
            if store_str:
                store_counts[store_str] = store_counts.get(store_str, 0) + 1
            formatted_date = ''
            try:
                if isinstance(raw_date, datetime):
                    formatted_date = raw_date.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(raw_date, date):
                    formatted_date = datetime(raw_date.year, raw_date.month, raw_date.day).strftime('%Y-%m-%d')
                else:
                    formatted_date = str(raw_date) if raw_date is not None else ''
            except Exception:
                formatted_date = str(raw_date) if raw_date is not None else ''
            data.append({
                'id': row_id,
                'invite_code': invite,
                'bd': bd_name,
                'date': formatted_date,
                'store': store_str
            })
        total_count = len(data)
        store_list = [{'store': k, 'count': v} for k, v in store_counts.items()]
        store_list.sort(key=lambda x: x['store'])
        return jsonify({'success': True, 'data': data, 'total': total_count, 'store_counts': store_list})
    except Exception as e:
        return jsonify({'success': False, 'message': f'查询失败: {str(e)}'}), 500


def tk_invite_monitor_wanghong_register_overview(
    *,
    datetime,
    jsonify,
    sf_db,
):
    """达人资料/合作记录登记展示"""
    try:
        latest_sql = """
            SELECT MAX(shijian) AS latest_time
            FROM (
                SELECT MAX(DaoRuShiJian) AS shijian
                FROM TK_WangHong_ZiLiao
                WHERE CHARINDEX(N'影刀', ISNULL(CAST(BeiZhu1 AS NVARCHAR(200)), '')) > 0
                UNION ALL
                SELECT MAX(DaoRuShiJian) AS shijian
                FROM TK_WangHong_HeZuo
                WHERE CHARINDEX(N'影刀', ISNULL(CAST(DaoRuRen AS NVARCHAR(200)), '')) > 0
            ) t
        """
        latest_raw = sf_db(latest_sql, single=True)

        count_sql = """
            SELECT COUNT(1)
            FROM TK_WangHongMing_DengJi
            WHERE TongZhiShiJian IS NULL
        """
        remaining_raw = sf_db(count_sql, single=True)
        if isinstance(remaining_raw, dict):
            remaining_count = int(
                remaining_raw.get('COUNT(1)')
                or remaining_raw.get('count')
                or remaining_raw.get('cnt')
                or 0
            )
        elif isinstance(remaining_raw, (list, tuple)):
            remaining_count = int(remaining_raw[0] if remaining_raw else 0)
        else:
            remaining_count = int(remaining_raw or 0)

        list_sql = """
            SELECT TOP 300
                ROW_NUMBER() OVER (ORDER BY DaoRuShiJian DESC) AS XH,
                BD,
                WangHongMing,
                Dian,
                DaoRuShiJian,
                TongZhiShiJian
            FROM TK_WangHongMing_DengJi
            WHERE TongZhiShiJian IS NULL
            ORDER BY DaoRuShiJian DESC
        """
        rows = sf_db(list_sql) or []

        items = []
        for r in rows:
            if isinstance(r, dict):
                row_id = (
                    r.get('XH')
                    if 'XH' in r else
                    r.get('xh')
                    if 'xh' in r else
                    r.get('ID')
                    if 'ID' in r else
                    r.get('id')
                )
                bd = r.get('BD') if 'BD' in r else r.get('bd')
                wanghongming = r.get('WangHongMing') if 'WangHongMing' in r else r.get('wanghongming')
                dian = r.get('Dian') if 'Dian' in r else r.get('dian')
                daoru = r.get('DaoRuShiJian') if 'DaoRuShiJian' in r else r.get('daorushijian')
                tongzhi = r.get('TongZhiShiJian') if 'TongZhiShiJian' in r else r.get('tongzhishijian')
            elif isinstance(r, (list, tuple)):
                row_id = r[0] if len(r) > 0 else None
                bd = r[1] if len(r) > 1 else ''
                wanghongming = r[2] if len(r) > 2 else ''
                dian = r[3] if len(r) > 3 else ''
                daoru = r[4] if len(r) > 4 else None
                tongzhi = r[5] if len(r) > 5 else None
            else:
                row_id = None
                bd = ''
                wanghongming = ''
                dian = ''
                daoru = None
                tongzhi = None
            if isinstance(daoru, datetime):
                daoru_text = daoru.strftime('%Y-%m-%d %H:%M:%S')
            else:
                daoru_text = '' if daoru is None else str(daoru)
            if isinstance(tongzhi, datetime):
                tongzhi_text = tongzhi.strftime('%Y-%m-%d %H:%M:%S')
            else:
                tongzhi_text = '' if tongzhi is None else str(tongzhi)
            items.append({
                'id': row_id,
                'bd': '' if bd is None else str(bd),
                'wanghongming': '' if wanghongming is None else str(wanghongming),
                'dian': '' if dian is None else str(dian),
                'daorushijian': daoru_text,
                'tongzhishijian': tongzhi_text
            })

        if isinstance(latest_raw, datetime):
            latest_time = latest_raw.strftime('%Y-%m-%d %H:%M:%S')
        else:
            latest_time = '' if latest_raw is None else str(latest_raw)

        return jsonify({
            'success': True,
            'data': {
                'latest_time': latest_time,
                'remaining_count': remaining_count,
                'preview_count': len(items),
                'items': items
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'查询失败: {str(e)}'}), 500
