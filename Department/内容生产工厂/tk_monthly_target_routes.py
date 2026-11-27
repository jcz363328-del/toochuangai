"""TikTok monthly target import, validation and template export."""

from __future__ import annotations


def tk_monthly_target_import(
    *,
    render_template,
    session,
):
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('内容生产工厂/tk_monthly_target_import.html', user_name=user_name, user_id=user_id)


def upload_monthly_target(
    *,
    dui_db,
    jsonify,
    request,
    sf_db,
):
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

        if df is None or df.empty:
            return jsonify({'success': False, 'message': 'Excel内容为空'})

        def normalize_col(name):
            s = str(name).strip()
            s = s.replace('\u3000', '').replace(' ', '').replace('\t', '')
            s = s.replace('（', '(').replace('）', ')')
            s = s.replace('(', '').replace(')', '')
            s = s.replace('_', '').replace('-', '').replace('—', '')
            s = s.lower()
            if s in ('年份', '年度', 'year'):
                return '年'
            if s in ('月份', '月度', 'month'):
                return '月'
            if s in ('店', '店铺', '门店', '店名', '门市', 'shop', '门店号', '店号'):
                return '店'
            return s

        cols_rs = sf_db(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = 'tk_yuedumubiao' ORDER BY ORDINAL_POSITION"
        ) or []
        db_cols = []
        db_types = {}
        for r in cols_rs:
            if isinstance(r, (list, tuple)) and len(r) >= 2:
                col_name = str(r[0])
                col_type = str(r[1])
            elif isinstance(r, dict):
                col_name = str(r.get('COLUMN_NAME') or r.get('column_name') or '')
                col_type = str(r.get('DATA_TYPE') or r.get('data_type') or '')
            else:
                continue
            if col_name:
                db_cols.append(col_name)
                db_types[col_name] = col_type.lower()

        if not db_cols:
            return jsonify({'success': False, 'message': '未获取到数据库表 tk_yuedumubiao 的字段信息'})

        excel_cols = list(df.columns)
        excel_norm_map = {}
        for c in excel_cols:
            n = normalize_col(c)
            if n and n not in excel_norm_map:
                excel_norm_map[n] = c

        db_norm_map = {}
        for c in db_cols:
            n = normalize_col(c)
            if n and n not in db_norm_map:
                db_norm_map[n] = c

        year_db_col = db_norm_map.get('年')
        month_db_col = db_norm_map.get('月')
        shop_db_col = db_norm_map.get('店')
        import_time_db_col = db_norm_map.get('导入时间')
        year_excel_col = excel_norm_map.get('年')
        month_excel_col = excel_norm_map.get('月')
        shop_excel_col = excel_norm_map.get('店')
        if not (year_db_col and month_db_col and year_excel_col and month_excel_col and shop_db_col and shop_excel_col):
            return jsonify({'success': False, 'message': 'Excel必须包含“年”“月”“店”三列'})

        numeric_types = {
            'int', 'bigint', 'smallint', 'tinyint',
            'decimal', 'numeric', 'float', 'real',
            'money', 'smallmoney', 'bit'
        }

        def to_sql_identifier(name):
            return '[' + str(name).replace(']', ']]') + ']'

        def parse_numeric(v, default=0):
            try:
                if pd.isna(v) or str(v).strip() == '':
                    return default
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return int(v)
                s = str(v).strip().replace(',', '')
                return int(float(s))
            except Exception:
                return default

        def to_sql_value(db_col, v, warnings):
            norm_name = normalize_col(db_col)
            if norm_name == '店':
                if v is None or (hasattr(pd, 'isna') and pd.isna(v)) or str(v).strip() == '':
                    return 'NULL', None
                num = None
                try:
                    num = parse_numeric(v, default=None)
                except Exception:
                    num = None
                if num is not None:
                    num_int = int(num)
                    return str(num_int), num_int
                s = str(v).strip()
                s = s.replace("'", "''")
                return "'" + s + "'", s
            if norm_name in ('年', '月', '导入时间'):
                if v is None or (hasattr(pd, 'isna') and pd.isna(v)):
                    return 'NULL', None
                s = str(v)
                s = s.replace("'", "''")
                return "'" + s + "'", s
            num = None
            try:
                num = parse_numeric(v, default=None)
            except Exception:
                num = None
            if num is not None:
                num_int = int(num)
                return str(num_int), num_int
            if v is None or (hasattr(pd, 'isna') and pd.isna(v)):
                return 'NULL', None
            s = str(v)
            s = s.replace("'", "''")
            return "'" + s + "'", s

        warnings = []

        mapped = []
        for excel_norm, excel_col in excel_norm_map.items():
            db_col = db_norm_map.get(excel_norm)
            if db_col:
                mapped.append((db_col, excel_col))

        if len(mapped) == 0:
            return jsonify({'success': False, 'message': 'Excel表头与数据库字段无法匹配'})

        year_ident = to_sql_identifier(year_db_col)
        month_ident = to_sql_identifier(month_db_col)
        shop_ident = to_sql_identifier(shop_db_col)
        import_time_ident = to_sql_identifier(import_time_db_col) if import_time_db_col else None

        total_rows = len(df)
        processed_rows = 0
        inserted_rows = 0
        updated_rows = 0
        detail_msgs = []

        for idx, row in df.iterrows():
            year_val = row.get(year_excel_col)
            month_val = row.get(month_excel_col)
            shop_val = row.get(shop_excel_col)
            year_num = int(parse_numeric(year_val, default=0))
            month_num = int(parse_numeric(month_val, default=0))
            if year_num <= 0 or month_num <= 0:
                warnings.append(f'第{idx + 2}行年/月不合法：年={year_val}，月={month_val}')
                continue

            shop_sql_val, shop_raw = to_sql_value(shop_db_col, shop_val, warnings)
            shop_raw_str = str(shop_raw or '').strip()
            if not shop_raw_str:
                warnings.append(f'第{idx + 2}行“店”列为空，已跳过')
                continue

            set_parts = []
            insert_cols = []
            insert_vals = []
            for db_col, excel_col in mapped:
                norm_name = normalize_col(db_col)
                if norm_name in ('年', '月', '店'):
                    continue
                sql_val, _ = to_sql_value(db_col, row.get(excel_col), warnings)
                col_ident = to_sql_identifier(db_col)
                set_parts.append(f"{col_ident} = {sql_val}")
                insert_cols.append(col_ident)
                insert_vals.append(sql_val)

            if import_time_ident:
                set_parts.append(f"{import_time_ident} = GETDATE()")

            exist_cnt = sf_db(
                f"SELECT COUNT(*) FROM tk_yuedumubiao WHERE {year_ident} = {year_num} AND {month_ident} = {month_num} AND {shop_ident} = {shop_sql_val}",
                single=True
            )
            exist_cnt = int(exist_cnt) if exist_cnt is not None else 0

            if exist_cnt > 0 and set_parts:
                sql = (
                    f"UPDATE tk_yuedumubiao SET {', '.join(set_parts)} "
                    f"WHERE {year_ident} = {year_num} AND {month_ident} = {month_num} AND {shop_ident} = {shop_sql_val}"
                )
                dui_db(sql)
                action = '更新'
                updated_rows += 1
            else:
                if import_time_ident:
                    insert_cols_full = [year_ident, month_ident, shop_ident, import_time_ident] + insert_cols
                    insert_vals_full = [str(year_num), str(month_num), shop_sql_val, 'GETDATE()'] + insert_vals
                else:
                    insert_cols_full = [year_ident, month_ident, shop_ident] + insert_cols
                    insert_vals_full = [str(year_num), str(month_num), shop_sql_val] + insert_vals
                sql = (
                    f"INSERT INTO tk_yuedumubiao ({', '.join(insert_cols_full)}) "
                    f"VALUES ({', '.join(insert_vals_full)})"
                )
                dui_db(sql)
                action = '新增'
                inserted_rows += 1

            processed_rows += 1
            detail_msgs.append(f'{action} {year_num}年{month_num}月 店={shop_raw_str} 月度目标')
            if exist_cnt > 1:
                warnings.append(f'检测到数据库中 {year_num}年{month_num}月 店={shop_raw_str} 存在多条记录，本次将全部更新')

        if processed_rows == 0:
            return jsonify({
                'success': False,
                'message': '未找到任何有效行，导入失败',
                'warnings': warnings
            })

        msg = f'导入完成：共{total_rows}行，成功{processed_rows}行，新增{inserted_rows}行，更新{updated_rows}行'

        return jsonify({'success': True,
            'action': '批量导入',
            'total_rows': total_rows,
            'processed_rows': processed_rows,
            'inserted_rows': inserted_rows,
            'updated_rows': updated_rows,
            'warnings': warnings + detail_msgs,
            'message': msg
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'导入失败: {str(e)}'})


def download_monthly_target_template(
    *,
    datetime,
    jsonify,
    send_file,
    sf_db,
):
    try:
        import pandas as pd
        from io import BytesIO
        desired_headers = [
            '实时保本额',
            '销售量',
            '销售额',
            '净利润',
            '毛利润',
            '达人佣金',
            '达人数',
            '达人视频费',
            '视频数',
            '活动服务费',
            '广告费',
            '平台佣金',
            'VAT',
            '调整费',
            '其他',
            '经营管理费青岛',
            '经营管理费深圳',
            '产品成本',
            '头程费用',
            '尾程项目',
            '项目尾程仓储费入库费',
            '工资青岛',
            '工资深圳',
            '房租青岛',
            '房租深圳',
            '年',
            '月',
            '店',
            '创作者佣金',
            '联盟伙伴佣金',
            '广告订单佣金',
            '达人渠道号佣金',
            '刷单费',
            '售后',
            '网红坑位费',
            '给网红购买产品费',
            '达人礼品费',
            '入库费',
            '仓储费',
            '退货费'
        ]
        cols_rs = sf_db(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = 'tk_yuedumubiao'"
        ) or []
        db_cols = set()
        for r in cols_rs:
            if isinstance(r, (list, tuple)) and len(r) >= 1:
                col_name = str(r[0])
            elif isinstance(r, dict):
                col_name = str(r.get('COLUMN_NAME') or r.get('column_name') or '')
            else:
                col_name = ''
            if col_name:
                db_cols.add(col_name)
        headers = [h for h in desired_headers if (not db_cols or h in db_cols)]
        if not headers:
            headers = desired_headers
        df = pd.DataFrame(columns=headers)
        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        filename = f"tk_yuedumubiao_import_template_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'生成模板失败: {str(e)}'})
