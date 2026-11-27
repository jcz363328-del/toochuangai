"""财务查询、审批导出与费用导入路由。"""
from datetime import datetime
import requests
from flask import jsonify, render_template, request, send_file, session
from bjc import sf_db, dui_db
from department_permissions import permission_manager
from .shenzhen_total import compute_shenzhen_expenses


def register_finance_routes(app, require_permission):
    @app.route('/finance_sz_dashboard')
    @require_permission('tk_total_dashboard')
    def finance_sz_dashboard():
        return render_template('财务部/finance_sz_dashboard.html')


    @app.route('/api/finance/sz_expenses')
    @require_permission('tk_total_dashboard')
    def api_finance_sz_expenses():
        try:
            base_month = request.args.get('base_month', '')
            months, data = compute_shenzhen_expenses(base_month)
            return jsonify({'success': True, 'months': months, 'data': data})
        except Exception as e:
            return jsonify({'success': False, 'message': f'查询失败: {str(e)}'}), 500


    def _export_approval_amounts_core(start_date, end_date, approval_code, source):
        import requests, time, json
        if source != 'feishu':
            return jsonify({'success': False, 'message': '仅支持从飞书审批中心拉取'}), 400
        token = permission_manager.get_access_token()
        if not token:
            return jsonify({'success': False, 'message': '获取飞书访问令牌失败'}), 500
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        def to_ts(s):
            if not s:
                return None
            try:
                from datetime import datetime
                dt = datetime.strptime(s.strip(), '%Y-%m-%d')
                return int(time.mktime(dt.timetuple()))
            except Exception:
                return None
        start_ts = to_ts(start_date)
        end_ts = to_ts(end_date)
        if not start_ts or not end_ts:
            end_ts = int(time.time())
            start_ts = end_ts - 30 * 24 * 3600
        approvals = []
        code_name_map = {}
        if approval_code:
            approvals = [approval_code]
            code_name_map[approval_code] = ''
        else:
            url_list = 'https://open.feishu.cn/open-apis/approval/v4/approvals'
            page_token = None
            while True:
                params = {'page_size': 100}
                if page_token:
                    params['page_token'] = page_token
                r = requests.get(url_list, headers=headers, params=params).json()
                if r.get('code') != 0:
                    break
                items = r.get('data', {}).get('items') or r.get('data', {}).get('approval_list') or []
                for it in items:
                    code = it.get('approval_code') or it.get('code') or ''
                    name = it.get('name') or it.get('approval_name') or ''
                    if code:
                        approvals.append(code)
                        code_name_map[code] = name
                page_token = r.get('data', {}).get('page_token') or r.get('data', {}).get('next_page_token')
                if not page_token:
                    break
        results = []
        url_instances = 'https://open.feishu.cn/open-apis/approval/v4/instances'
        def extract_amounts(form_obj):
            amounts = []
            fields = []
            try:
                if isinstance(form_obj, str):
                    form_obj = json.loads(form_obj)
            except Exception:
                form_obj = {}
            def scan(v, kpath=''):
                try:
                    if isinstance(v, dict):
                        for k, val in v.items():
                            kp = f"{kpath}.{k}" if kpath else str(k)
                            scan(val, kp)
                    elif isinstance(v, list):
                        for i, val in enumerate(v):
                            scan(val, f"{kpath}[{i}]")
                    else:
                        if isinstance(v, (int, float)):
                            amounts.append(float(v))
                            fields.append(f"{kpath}={v}")
                        else:
                            s = str(v)
                            if any(w in (kpath or '') for w in ['金额', '费用', '金额(元)']):
                                try:
                                    num = float(s.replace(',', ''))
                                    amounts.append(num)
                                    fields.append(f"{kpath}={num}")
                                except Exception:
                                    pass
                except Exception:
                    pass
            scan(form_obj)
            total = amounts[0] if amounts else 0
            return total, ';'.join(fields[:6])
        for code in approvals:
            page_token = None
            while True:
                params = {
                    'approval_code': code,
                    'start_time': start_ts,
                    'end_time': end_ts,
                    'page_size': 100
                }
                if page_token:
                    params['page_token'] = page_token
                r = requests.get(url_instances, headers=headers, params=params).json()
                if r.get('code') != 0:
                    try:
                        params['start_time'] = start_ts * 1000
                        params['end_time'] = end_ts * 1000
                        r = requests.get(url_instances, headers=headers, params=params).json()
                    except Exception:
                        pass
                    if r.get('code') != 0:
                        break
                items = r.get('data', {}).get('items') or r.get('data', {}).get('instance_list') or []
                for it in items:
                    form = it.get('form') or it.get('form_value') or it.get('form_values') or {}
                    amt, detail = extract_amounts(form)
                    st = it.get('start_time') or it.get('create_time') or 0
                    ft = it.get('end_time') or it.get('finish_time') or 0
                    def fmt(ts):
                        try:
                            from datetime import datetime
                            return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S') if ts else ''
                        except Exception:
                            return ''
                    title = it.get('title') or it.get('approval_name') or ''
                    status = it.get('status') or it.get('instance_status') or ''
                    originator = it.get('user_id') or it.get('originator_user_id') or ''
                    instance_code = it.get('instance_code') or ''
                    results.append([
                        instance_code,
                        title,
                        code_name_map.get(code, ''),
                        originator,
                        '',
                        amt,
                        status,
                        fmt(st),
                        fmt(ft),
                        detail
                    ])
                page_token = r.get('data', {}).get('page_token') or r.get('data', {}).get('next_page_token')
                if not page_token:
                    break
        preview = request.args.get('preview')
        if not results:
            if preview:
                return jsonify({'success': True, 'message': '无记录', 'approvals': approvals, 'count': 0})
            return jsonify({'success': False, 'message': '没有数据可导出'}), 404
        import pandas as pd
        from io import BytesIO
        buf = BytesIO()
        cols = ['实例编码', '审批标题', '审批类型', '申请人', '部门', '金额', '状态', '发起时间', '完成时间', '金额字段明细']
        df = pd.DataFrame(results, columns=cols)
        df.sort_values(by=['发起时间'], inplace=True, ascending=False)
        df.to_excel(buf, index=False, engine='openpyxl')
        buf.seek(0)
        filename_suffix = f"_{start_date}_to_{end_date}" if start_date and end_date else ""
        filename = f"飞书审批金额明细{filename_suffix}.xlsx"
        return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=filename)

    @app.route('/api/export_approval_amounts', methods=['GET'])
    @require_permission('admin_functions')
    def export_approval_amounts():
        try:
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            approval_code = request.args.get('approval_code')
            source = request.args.get('source', 'feishu')
            return _export_approval_amounts_core(start_date, end_date, approval_code, source)
        except Exception as e:
            return jsonify({'success': False, 'message': f'导出失败: {str(e)}'}), 500

    @app.route('/api/export_approval_amounts_finance', methods=['GET'])
    @require_permission('finance_dept')
    def export_approval_amounts_finance():
        try:
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            approval_code = request.args.get('approval_code')
            source = request.args.get('source', 'feishu')
            return _export_approval_amounts_core(start_date, end_date, approval_code, source)
        except Exception as e:
            return jsonify({'success': False, 'message': f'导出失败: {str(e)}'}), 500

    @app.route('/api/feishu/approvals', methods=['GET'])
    @require_permission('admin_functions')
    def list_feishu_approvals():
        try:
            token = permission_manager.get_access_token()
            if not token:
                return jsonify({'success': False, 'message': '获取飞书访问令牌失败'}), 500
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json; charset=utf-8'
            }
            url_list = 'https://open.feishu.cn/open-apis/approval/v4/approvals'
            page_token = None
            items_all = []
            while True:
                params = {'page_size': 100}
                if page_token:
                    params['page_token'] = page_token
                r = requests.get(url_list, headers=headers, params=params).json()
                if r.get('code') != 0:
                    break
                items = r.get('data', {}).get('items') or r.get('data', {}).get('approval_list') or []
                for it in items:
                    items_all.append({
                        'code': it.get('approval_code') or it.get('code') or '',
                        'name': it.get('name') or it.get('approval_name') or ''
                    })
                page_token = r.get('data', {}).get('page_token') or r.get('data', {}).get('next_page_token')
                if not page_token:
                    break
            return jsonify({'success': True, 'data': items_all})
        except Exception as e:
            return jsonify({'success': False, 'message': f'拉取失败: {str(e)}'}), 500

    @app.route('/api/feishu/approvals_finance', methods=['GET'])
    @require_permission('finance_dept')
    def list_feishu_approvals_finance():
        try:
            token = permission_manager.get_access_token()
            if not token:
                return jsonify({'success': False, 'message': '获取飞书访问令牌失败'}), 500
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json; charset=utf-8'
            }
            url_list = 'https://open.feishu.cn/open-apis/approval/v4/approvals'
            page_token = None
            items_all = []
            while True:
                params = {'page_size': 100}
                if page_token:
                    params['page_token'] = page_token
                r = requests.get(url_list, headers=headers, params=params).json()
                if r.get('code') != 0:
                    break
                items = r.get('data', {}).get('items') or r.get('data', {}).get('approval_list') or []
                for it in items:
                    items_all.append({
                        'code': it.get('approval_code') or it.get('code') or '',
                        'name': it.get('name') or it.get('approval_name') or ''
                    })
                page_token = r.get('data', {}).get('page_token') or r.get('data', {}).get('next_page_token')
                if not page_token:
                    break
            return jsonify({'success': True, 'data': items_all})
        except Exception as e:
            return jsonify({'success': False, 'message': f'拉取失败: {str(e)}'}), 500

    @app.route('/api/finance/import_expense_sheet', methods=['POST'])
    @require_permission('finance_dept')
    def import_expense_sheet():
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'message': '未发现文件'}), 400
            file = request.files['file']
            if not file or file.filename == '':
                return jsonify({'success': False, 'message': '未选择文件'}), 400
            import pandas as pd
            try:
                df = pd.read_excel(file)
            except Exception as e:
                return jsonify({'success': False, 'message': f'读取Excel失败: {str(e)}'}), 400
            cols_map = {str(c).strip(): c for c in df.columns}
            required = ['日期','费用类别','摘要','借方','贷方','报销人','项目','银行类别','部门']
            missing = [c for c in required if c not in cols_map]
            if missing:
                return jsonify({'success': False, 'message': f'缺少列: {"、".join(missing)}'}), 400
            def esc(v):
                return '' if v is None else str(v).strip().replace("'","''")
            def parse_date(v):
                import pandas as pd
                from datetime import datetime
                if pd.isna(v):
                    return None
                if hasattr(v,'strftime'):
                    return v.strftime('%Y-%m-%d')
                s = str(v).strip()
                if not s:
                    return None
                for fmt in ['%Y-%m-%d','%Y-%m-%d %H:%M:%S','%Y/%m/%d','%Y-%m-%dT%H:%M:%S']:
                    try:
                        return datetime.strptime(s,fmt).strftime('%Y-%m-%d')
                    except Exception:
                        pass
                try:
                    parts = s.replace('/','-').split('-')
                    if len(parts)==3:
                        y = int(parts[0]); m = int(parts[1]); d = int(parts[2])
                        return f"{y:04d}-{m:02d}-{d:02d}"
                except Exception:
                    pass
                return None
            def parse_num(v):
                import pandas as pd
                if pd.isna(v):
                    return None
                s = str(v).strip().replace(',','')
                if s=='':
                    return None
                try:
                    return round(float(s),2)
                except Exception:
                    return None
            inserted = 0
            updated = 0
            errors = []
            for idx, row in df.iterrows():
                d = parse_date(row.get(cols_map['日期']))
                lei = esc(row.get(cols_map['费用类别']))
                zhai = esc(row.get(cols_map['摘要']))
                jiefang = parse_num(row.get(cols_map['借方']))
                daifang = parse_num(row.get(cols_map['贷方']))
                baoxiaoren = esc(row.get(cols_map['报销人']))
                xiangmu = esc(row.get(cols_map['项目']))
                yinhang = esc(row.get(cols_map['银行类别']))
                bumen = esc(row.get(cols_map['部门']))
                if not d:
                    errors.append(f'第{idx+1}行日期无效')
                    continue
                conds = [
                    f"日期 = '{d}'",
                    f"费用类别 = '{lei}'",
                    f"摘要 = '{zhai}'",
                    ("借方 IS NULL" if jiefang is None else f"借方 = {jiefang}"),
                    ("贷方 IS NULL" if daifang is None else f"贷方 = {daifang}"),
                    f"报销人 = '{baoxiaoren}'",
                    f"项目 = '{xiangmu}'",
                    f"银行类别 = '{yinhang}'",
                    f"部门 = '{bumen}'"
                ]
                dup_sql = f"SELECT COUNT(*) FROM 财务_费用明细 WHERE {' AND '.join(conds)}"
                try:
                    cnt = sf_db(dup_sql, single=True)
                    cnt = int(cnt or 0)
                except Exception:
                    cnt = 0
                if cnt > 0:
                    errors.append(
                        f"重复记录，已跳过: 日期={d}, 费用类别={lei}, 摘要={zhai}, 借方={'' if jiefang is None else jiefang}, 贷方={'' if daifang is None else daifang}, 报销人={baoxiaoren}, 项目={xiangmu}, 银行类别={yinhang}, 部门={bumen}"
                    )
                    continue
                vals = [
                    f"'{d}'",
                    f"'{lei}'",
                    f"'{zhai}'",
                    'NULL' if jiefang is None else str(jiefang),
                    'NULL' if daifang is None else str(daifang),
                    f"'{baoxiaoren}'",
                    f"'{xiangmu}'",
                    f"'{yinhang}'",
                    f"'{bumen}'"
                ]
                sql = f"INSERT INTO 财务_费用明细 (日期, 费用类别, 摘要, 借方, 贷方, 报销人, 项目, 银行类别, 部门) VALUES ({', '.join(vals)})"
                try:
                    dui_db(sql)
                    inserted += 1
                except Exception as e:
                    errors.append(f"第{idx+1}行插入失败: {str(e)}")
            return jsonify({'success': True, 'inserted': inserted, 'errors': errors, 'message': f'成功 {inserted} 条，失败 {len(errors)} 条'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'导入失败: {str(e)}'})


    @app.route('/api/finance/export_expense_sheet', methods=['GET'])
    @require_permission('finance_dept')
    def export_expense_sheet():
        try:
            sql = "SELECT 日期, 费用类别, 摘要, 借方, 贷方, 报销人, 项目, 银行类别, 部门 FROM 财务_费用明细 ORDER BY 日期, 费用类别, 摘要"
            rows = sf_db(sql) or []
            if not rows:
                return jsonify({'success': False, 'message': '没有数据可导出'}), 404
            import pandas as pd
            from io import BytesIO
            buf = BytesIO()
            cols = ['日期', '费用类别', '摘要', '借方', '贷方', '报销人', '项目', '银行类别', '部门']
            df = pd.DataFrame(rows, columns=cols)
            df.to_excel(buf, index=False, engine='openpyxl')
            buf.seek(0)
            filename = '费用明细.xlsx'
            return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=filename)
        except Exception as e:
            return jsonify({'success': False, 'message': f'导出失败: {str(e)}'}), 500


    @app.route('/api/finance/export_freight', methods=['GET'])
    @require_permission('finance_dept')
    def export_freight():
        try:
            start_date = request.args.get('start_date', '').strip()
            end_date = request.args.get('end_date', '').strip()
            stores_raw = request.args.get('stores', '').strip()
            if not start_date or not end_date:
                return jsonify({'success': False, 'message': '开始日期和结束日期不能为空'}), 400
            where = [
                f"结算日期 >= '{start_date}'",
                f"结算日期 <= '{end_date}'"
            ]
            shops = []
            if stores_raw:
                parts = [p.strip() for p in stores_raw.replace('，', ',').split(',') if p.strip()]
                if parts:
                    shop_list = []
                    for s in parts:
                        s2 = s.replace("'", "''")
                        shop_list.append(f"'{s2}'")
                        shops.append(s2)
                    where.append(f"店 IN ({', '.join(shop_list)})")
            where_sql = ' AND '.join(where)
            sql = f"""
    SELECT 
      物流运费, 
      平台实际运费, 
      运费折扣, 
      退货运费, 
      单号, 
      sku, 
      结算日期,
      店
    FROM v_TK_JieSuan js 
    LEFT JOIN tk_dingdan dd ON dd.danhao = js.单号 
    WHERE {where_sql}
    ORDER BY 结算日期, 店, 单号, sku
    """
            rows = sf_db(sql) or []
            if not rows:
                return jsonify({'success': False, 'message': '没有数据可导出'}), 404
            import pandas as pd
            from io import BytesIO
            buf = BytesIO()
            cols = ['物流运费', '平台实际运费', '运费折扣', '退货运费', '单号', 'sku', '结算日期', '店']
            df = pd.DataFrame(rows, columns=cols)
            df.to_excel(buf, index=False, engine='openpyxl')
            buf.seek(0)
            if shops:
                shop_str = '_'.join(shops)
                filename = f'物流运费结算明细_{start_date}_{end_date}_{shop_str}.xlsx'
            else:
                filename = f'物流运费结算明细_{start_date}_{end_date}.xlsx'
            return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=filename)
        except Exception as e:
            return jsonify({'success': False, 'message': f'导出失败: {str(e)}'}), 500

    @app.route('/api/finance/import_allocation_ratio', methods=['POST'])
    @require_permission('finance_dept')
    def import_allocation_ratio():
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'message': '未发现文件'}), 400
            file = request.files['file']
            if not file or file.filename == '':
                return jsonify({'success': False, 'message': '未选择文件'}), 400
            import pandas as pd
            try:
                df = pd.read_excel(file)
            except Exception as e:
                return jsonify({'success': False, 'message': f'读取Excel失败: {str(e)}'}), 400
            cols = {str(c).strip(): c for c in df.columns}
            required = ['年','月','国','地区','项目','店铺','比例']
            missing = [c for c in required if c not in cols]
            if missing:
                return jsonify({'success': False, 'message': f'缺少列: {"、".join(missing)}'}), 400
            def esc(v):
                return '' if v is None else str(v).strip().replace("'", "''")
            def parse_int(v):
                import pandas as pd
                if pd.isna(v):
                    return None
                s = str(v).strip()
                if s == '':
                    return None
                try:
                    return int(float(s))
                except Exception:
                    return None
            def parse_num(v):
                import pandas as pd
                if pd.isna(v):
                    return None
                s = str(v).strip().replace(',', '')
                if s == '':
                    return None
                try:
                    return float(s)
                except Exception:
                    return None
            inserted = 0
            updated = 0
            errors = []
            for idx, row in df.iterrows():
                nian = parse_int(row.get(cols['年']))
                yue = parse_int(row.get(cols['月']))
                guo = esc(row.get(cols['国']))
                diqu = esc(row.get(cols['地区']))
                xiangmu = esc(row.get(cols['项目']))
                dianpu = esc(row.get(cols['店铺']))
                bili = parse_num(row.get(cols['比例']))
                if nian is None:
                    errors.append(f'第{idx+1}行年份无效')
                    continue
                # 月份允许为空（NULL）
                if not guo:
                    errors.append(f'第{idx+1}行国为空')
                    continue
                if not diqu:
                    errors.append(f'第{idx+1}行地区为空')
                    continue
                if not xiangmu:
                    errors.append(f'第{idx+1}行项目为空')
                    continue
                if not dianpu:
                    errors.append(f'第{idx+1}行店铺为空')
                    continue
                if bili is None:
                    errors.append(f'第{idx+1}行比例无效')
                    continue
                yue_val = 'NULL' if yue is None else str(yue)
                base_conds = [
                    f"年 = {nian}",
                    (f"月 IS NULL" if yue is None else f"月 = {yue}"),
                    f"地区 = '{diqu}'",
                    f"项目 = '{xiangmu}'",
                    f"店铺 = '{dianpu}'"
                ]
                conds = [*base_conds, f"国 = '{guo}'"]
                where_clause = " AND ".join(conds)
                dup_sql = f"SELECT COUNT(*) FROM tk_费用分摊比例 WHERE {where_clause}"
                try:
                    cnt = sf_db(dup_sql, single=True)
                    cnt = int(cnt or 0)
                except Exception:
                    cnt = 0
                if cnt > 0:
                    sql = (
                        "UPDATE tk_费用分摊比例 "
                        f"SET 比例 = {bili} "
                        f"WHERE {where_clause}"
                    )
                    try:
                        dui_db(sql)
                        updated += 1
                    except Exception as e:
                        errors.append(f"第{idx+1}行更新失败: {str(e)}")
                    continue
                # 旧数据没有国家。首次按国家重新导入同一条分摊记录时，
                # 直接为旧记录补上国家，避免新旧记录同时参与看板汇总。
                legacy_where_clause = " AND ".join([
                    *base_conds,
                    "(国 IS NULL OR LTRIM(RTRIM(国)) = '')"
                ])
                legacy_sql = (
                    "SELECT COUNT(*) FROM tk_费用分摊比例 "
                    f"WHERE {legacy_where_clause}"
                )
                try:
                    legacy_count = int(sf_db(legacy_sql, single=True) or 0)
                except Exception:
                    legacy_count = 0
                if legacy_count > 0:
                    sql = (
                        "UPDATE tk_费用分摊比例 "
                        f"SET 国 = '{guo}', 比例 = {bili} "
                        f"WHERE {legacy_where_clause}"
                    )
                    try:
                        dui_db(sql)
                        updated += 1
                    except Exception as e:
                        errors.append(f"第{idx+1}行更新旧数据失败: {str(e)}")
                    continue
                sql = (
                    "INSERT INTO tk_费用分摊比例 (年, 月, 国, 地区, 项目, 店铺, 比例) VALUES "
                    f"({nian}, {yue_val}, '{guo}', '{diqu}', '{xiangmu}', '{dianpu}', {bili})"
                )
                try:
                    dui_db(sql)
                    inserted += 1
                except Exception as e:
                    errors.append(f"第{idx+1}行插入失败: {str(e)}")
            return jsonify({
                'success': True,
                'inserted': inserted,
                'updated': updated,
                'errors': errors,
                'message': f'新增 {inserted} 条，更新 {updated} 条，失败 {len(errors)} 条'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'导入失败: {str(e)}'})

    @app.route('/api/finance/import_wage_rent', methods=['POST'])
    @require_permission('finance_dept')
    def import_wage_rent():
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'message': '未发现文件'}), 400
            file = request.files['file']
            if not file or file.filename == '':
                return jsonify({'success': False, 'message': '未选择文件'}), 400
            import pandas as pd
            try:
                df = pd.read_excel(file)
            except Exception as e:
                return jsonify({'success': False, 'message': f'读取Excel失败: {str(e)}'}), 400
            cols = {str(c).strip().lower(): c for c in df.columns}
            required = ['nian','yue','tuandui','xiangmu','feiyonge']
            missing = [c for c in required if c not in cols]
            if missing:
                return jsonify({'success': False, 'message': f'缺少列: {"、".join(missing)}'}), 400
            def esc(v):
                return '' if v is None else str(v).strip().replace("'", "''")
            def parse_int(v):
                import pandas as pd
                if pd.isna(v):
                    return None
                s = str(v).strip()
                if s == '':
                    return None
                try:
                    return int(float(s))
                except Exception:
                    return None
            def parse_num(v):
                import pandas as pd
                if pd.isna(v):
                    return None
                s = str(v).strip().replace(',', '')
                if s == '':
                    return None
                try:
                    return float(s)
                except Exception:
                    return None
            user_name = session.get('feishu_user_name', '')
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            inserted = 0
            updated = 0
            errors = []
            for idx, row in df.iterrows():
                nian = parse_int(row.get(cols['nian']))
                yue = parse_int(row.get(cols['yue']))
                tuandui = esc(row.get(cols['tuandui']))
                xiangmu = esc(row.get(cols['xiangmu']))
                feiyonge = parse_num(row.get(cols['feiyonge']))
                if nian is None:
                    errors.append(f'第{idx+1}行年份无效')
                    continue
                if yue is None or yue < 1 or yue > 12:
                    errors.append(f'第{idx+1}行月份无效')
                    continue
                if not tuandui:
                    errors.append(f'第{idx+1}行团队为空')
                    continue
                if not xiangmu:
                    errors.append(f'第{idx+1}行项目为空')
                    continue
                if feiyonge is None:
                    errors.append(f'第{idx+1}行费用额无效')
                    continue
                dup_sql = (
                    f"SELECT COUNT(*) FROM tk_feiyong2 WHERE "
                    f"Nian = {nian} AND Yue = {yue} AND TuanDui = '{tuandui}' AND XiangMu = '{xiangmu}'"
                )
                try:
                    cnt = sf_db(dup_sql, single=True)
                    cnt = int(cnt or 0)
                except Exception:
                    cnt = 0
                if cnt > 0:
                    sql = (
                        f"UPDATE tk_feiyong2 SET FeiYongE = {feiyonge}, "
                        f"DaoRuRen = '{esc(user_name)}', DaoRuShiJian = '{now_str}' "
                        f"WHERE Nian = {nian} AND Yue = {yue} AND TuanDui = '{tuandui}' AND XiangMu = '{xiangmu}'"
                    )
                    try:
                        dui_db(sql)
                        updated += 1
                    except Exception as e:
                        errors.append(f"第{idx+1}行更新失败: {str(e)}")
                else:
                    sql = (
                        "INSERT INTO tk_feiyong2 (Nian, Yue, TuanDui, XiangMu, FeiYongE, DaoRuRen, DaoRuShiJian) VALUES "
                        f"({nian}, {yue}, '{tuandui}', '{xiangmu}', {feiyonge}, '{esc(user_name)}', '{now_str}')"
                    )
                    try:
                        dui_db(sql)
                        inserted += 1
                    except Exception as e:
                        errors.append(f"第{idx+1}行插入失败: {str(e)}")
            return jsonify({
                'success': True,
                'inserted': inserted,
                'updated': updated,
                'errors': errors,
                'message': f'新增 {inserted} 条，更新 {updated} 条，失败 {len(errors)} 条'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'导入失败: {str(e)}'})

