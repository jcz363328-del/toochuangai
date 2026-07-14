from flask import Blueprint, render_template, request, jsonify, session
from datetime import datetime
from department_permissions import require_permission
from bjc import sf_db, dui_db
import re


bd_metrics_bp = Blueprint('bd_metrics', __name__)


@bd_metrics_bp.route('/tk_bd_metrics')
@require_permission('tk_project_group')
def tk_bd_metrics_page():
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    current_day = now.day
    return render_template(
        'tk_bd_metrics.html',
        user_name=user_name,
        user_id=user_id,
        current_year=current_year,
        current_month=current_month,
        current_day=current_day
    )


@bd_metrics_bp.route('/api/tk_bd_metrics', methods=['GET'])
@require_permission('tk_project_group')
def get_tk_bd_metrics():
    try:
        year = request.args.get('year', type=int)
        month = request.args.get('month', type=int)
        shop_raw = request.args.get('shop', '', type=str)
        shop = shop_raw.strip() if shop_raw else ''

        if not year or not month:
            return jsonify({'success': False, 'message': '年份和月份不能为空'}), 400
        if month < 1 or month > 12:
            return jsonify({'success': False, 'message': '月份必须在1-12之间'}), 400

        conditions = [f"t.Nian = {year}", f"t.Yue = {month}"]
        if shop:
            parts = [p.strip() for p in re.split(r'[,\s，]+', shop) if p.strip()]
            if len(parts) == 1:
                safe_shop = parts[0].replace("'", "''")
                conditions.append(f"t.Dian = '{safe_shop}'")
            elif parts:
                safe_list = [p.replace("'", "''") for p in parts]
                in_values = ",".join(f"'{s}'" for s in safe_list)
                conditions.append(f"t.Dian IN ({in_values})")
        where_sql = " AND ".join(conditions)

        sql = f"""
SELECT 
    t.Nian, 
    t.Yue, 
    t.Dian, 
    t.BD, 
    t.ShiPinMuBiao, 
    t.JiYangMuBiao, 
    ISNULL(sp.实际视频数, 0) AS 实际视频数, 
    ISNULL(jy.实际寄养数量, 0) AS 实际寄样 
FROM tk_bd_shipin_jiyang t 
LEFT JOIN ( 
    SELECT 
        t2.Nian, 
        t2.Yue, 
        h.dian, 
        h.fuzeren, 
        COUNT(DISTINCT h.shipinid) AS 实际视频数 
    FROM tk_bd_shipin_jiyang t2 
    JOIN v_TK_HeZuoShiPin h WITH (NOLOCK) 
        ON h.dian = t2.Dian 
       AND h.fuzeren = t2.BD 
       AND h.faburiqi >= DATEFROMPARTS(t2.Nian, t2.Yue, 1) 
       AND h.faburiqi <  DATEADD(MONTH, 1, DATEFROMPARTS(t2.Nian, t2.Yue, 1)) 
    GROUP BY 
        t2.Nian, 
        t2.Yue, 
        h.dian, 
        h.fuzeren 
) sp 
    ON  sp.Nian = t.Nian 
    AND sp.Yue  = t.Yue 
    AND sp.dian = t.Dian 
    AND sp.fuzeren = t.BD 
LEFT JOIN ( 
    SELECT 
        t3.Nian, 
        t3.Yue, 
        zl.fuzeren, 
        zd.dian, 
        COUNT(*) AS 实际寄养数量 
    FROM tk_bd_shipin_jiyang t3 
    JOIN tk_wanghong_hezuo hz WITH (NOLOCK) 
        ON hz.fahuoriqi >= DATEFROMPARTS(t3.Nian, t3.Yue, 1) 
       AND hz.fahuoriqi <  DATEADD(MONTH, 1, DATEFROMPARTS(t3.Nian, t3.Yue, 1)) 
       AND CHARINDEX('TKWS', UPPER(ISNULL(CAST(hz.sku AS NVARCHAR(100)), ''))) = 0
    JOIN tk_wanghong_ziliao zl WITH (NOLOCK) 
        ON zl.bianhao = hz.bianhao 
       AND zl.fuzeren = t3.BD 
    JOIN zidian zd WITH (NOLOCK) 
        ON zd.sku = hz.sku 
       AND zd.dian = t3.Dian 
    GROUP BY 
        t3.Nian, 
        t3.Yue, 
        zl.fuzeren, 
        zd.dian 
) jy 
    ON  jy.Nian = t.Nian 
    AND jy.Yue  = t.Yue 
    AND jy.fuzeren = t.BD 
    AND jy.dian = t.Dian
WHERE {where_sql}
ORDER BY t.Dian, t.BD
"""
        rows = sf_db(sql) or []
        data = []
        for r in rows:
            try:
                year_val = r[0]
                month_val = r[1]
                shop_val = r[2]
                bd_val = r[3]
                shipin_target = r[4]
                jiyang_target = r[5]
                actual_videos = r[6]
                actual_reach = r[7]
            except Exception:
                continue
            data.append({
                'year': year_val,
                'month': month_val,
                'shop': shop_val,
                'bd': bd_val,
                'video_target': shipin_target,
                'sample_target': jiyang_target,
                'actual_video_count': actual_videos,
                'actual_reach_count': actual_reach
            })
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取BD指标失败: {str(e)}'}), 500


@bd_metrics_bp.route('/tk_bd_metrics_import')
@require_permission('tk_project_group')
def tk_bd_metrics_import_page():
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    return render_template('tk_bd_metrics_import.html', user_name=user_name, user_id=user_id)


@bd_metrics_bp.route('/api/tk_bd_metrics_import/template', methods=['GET'])
@require_permission('tk_project_group')
def download_bd_metrics_template():
    try:
        import pandas as pd
        from io import BytesIO
        headers = ['Nian', 'Yue', 'Dian', 'BD', 'ShiPinMuBiao', 'JiYangMuBiao']
        df = pd.DataFrame(columns=headers)
        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        from flask import send_file
        filename = f"tk_bd_shipin_jiyang_template_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'生成模板失败: {str(e)}'}), 500


@bd_metrics_bp.route('/api/tk_bd_metrics_import/upload', methods=['POST'])
@require_permission('tk_project_group')
def upload_bd_metrics():
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

        required_cols = ['Nian', 'Yue', 'Dian', 'BD', 'ShiPinMuBiao', 'JiYangMuBiao']
        for col in required_cols:
            if col not in df.columns:
                return jsonify({'success': False, 'message': f'缺少必要列: {col}'})

        inserted = 0
        warnings = []
        for _, row in df.iterrows():
            try:
                nian_raw = row['Nian']
                yue_raw = row['Yue']
                dian_raw = row['Dian']
                bd_raw = row['BD']
                shipin_raw = row['ShiPinMuBiao']
                jiyang_raw = row['JiYangMuBiao']

                nian = int(nian_raw)
                yue = int(yue_raw)

                if pd.isna(dian_raw):
                    raise ValueError('店铺为空')
                if isinstance(dian_raw, (int, float)):
                    dian_int = int(dian_raw)
                else:
                    dian_str = str(dian_raw).strip()
                    if not dian_str:
                        raise ValueError('店铺为空')
                    try:
                        dian_int = int(float(dian_str))
                    except Exception:
                        if dian_str.isdigit():
                            dian_int = int(dian_str)
                        else:
                            raise ValueError('店铺格式错误')
                dian = str(dian_int)

                bd = str(bd_raw).strip()
                shipin = int(shipin_raw)
                jiyang = int(jiyang_raw)
            except Exception:
                warnings.append('有行数据格式不正确，已跳过一行')
                continue
            if not dian or not bd:
                warnings.append(f'店或BD为空，已跳过: 年={nian}, 月={yue}')
                continue
            safe_dian = dian.replace("'", "''")
            safe_bd = bd.replace("'", "''")
            delete_sql = f"""
DELETE FROM tk_bd_shipin_jiyang
WHERE Nian = {nian} AND Yue = {yue} AND Dian = '{safe_dian}' AND BD = '{safe_bd}'
"""
            dui_db(delete_sql)
            insert_sql = f"""
INSERT INTO tk_bd_shipin_jiyang (Nian, Yue, Dian, BD, ShiPinMuBiao, JiYangMuBiao)
VALUES ({nian}, {yue}, '{safe_dian}', '{safe_bd}', {shipin}, {jiyang})
"""
            dui_db(insert_sql)
            inserted += 1

        try:
            cleanup_sql = """
UPDATE tk_bd_shipin_jiyang
SET Dian = CONVERT(varchar(10), CONVERT(int, CONVERT(float, Dian)))
WHERE ISNUMERIC(Dian) = 1 AND CHARINDEX('.', Dian) > 0
"""
            dui_db(cleanup_sql)
        except Exception:
            pass

        msg = f'导入完成，共写入 {inserted} 行'
        return jsonify({'success': True, 'message': msg, 'warnings': warnings})
    except Exception as e:
        return jsonify({'success': False, 'message': f'导入失败: {str(e)}'}), 500
