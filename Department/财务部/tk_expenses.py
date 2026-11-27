"""TK工作簿费用导入页面。工作簿宏仅作为业务规则来源，不执行宏。"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import jsonify, render_template, request, session
from openpyxl import load_workbook

from .database import connect


def parse_rows(stream, kind):
    if kind not in ('advertising', 'other'):
        raise ValueError('请选择广告费用或其他费用')
    book = load_workbook(stream, read_only=True, data_only=True)
    try:
        sheet = book['费用导入'] if '费用导入' in book.sheetnames else book.active
        original = sheet.title == '费用导入'
        rows = []
        for number, values in enumerate(sheet.iter_rows(values_only=True), 1):
            if number < (4 if original else 2):
                continue
            start, width = (7, 6) if original and kind == 'other' else (0, 5 if kind == 'advertising' else 6)
            cells = list(values[start:start + width])
            cells += [None] * (width - len(cells))
            if all(v is None or v == '' for v in cells):
                continue
            try:
                raw_date, raw_store = cells[:2]
                day = raw_date.date() if isinstance(raw_date, datetime) else raw_date
                if not isinstance(day, date):
                    day = date.fromisoformat(str(day).strip().replace('/', '-'))
                store = Decimal(str(raw_store))
                if not store.is_finite() or store != int(store) or store < 0:
                    raise ValueError('店铺应为非负整数')
                project, country, amount, note = ('广告', cells[2], cells[3], cells[4]) if kind == 'advertising' else cells[2:6]
                amount = Decimal(str(amount).replace(',', ''))
                if not amount.is_finite() or amount != amount.quantize(Decimal('.01')):
                    raise ValueError('费用应为最多两位小数的有限数字')
                if not str(project or '').strip() or (kind == 'advertising' and not str(country or '').strip()):
                    raise ValueError('项目不能为空，广告费用的国不能为空')
                rows.append((day, int(store), str(country or '').strip(), str(project).strip(), amount, str(note or '')))
            except (ValueError, TypeError, InvalidOperation, OverflowError) as exc:
                raise ValueError(f'第{number}行数据无效：{exc}') from exc
        if not rows:
            raise ValueError('没有可导入的费用记录')
        return rows
    finally:
        book.close()


def save_rows(rows, kind, actor, connect):
    """整批事务；广告检查与写入使用同一连接，失败时不留下部分导入。"""
    conn = connect()
    try:
        cursor = conn.cursor()
        if kind == 'advertising':
            seen = set()
            for row in rows:
                day, store, country, project, amount, note = row
                key = row[:5]
                if amount > 0:
                    if key in seen:
                        raise ValueError('文件中存在重复广告费用')
                    seen.add(key)
                    cursor.execute('SELECT COUNT(*) FROM TK_FeiYong WITH (UPDLOCK,HOLDLOCK) WHERE RiQi=%s AND Dian=%s AND Guo=%s AND XiangMu=%s AND FeiYongE=%s AND FeiYongE>0', (day, store, country, project, amount))
                    if cursor.fetchone()[0]:
                        raise ValueError(f'{day} 店{store}的该笔广告费用已经导入')
            cursor.execute("SELECT Dian FROM v_PinPaiDianPu WHERE bumen=%s", ('TT',))
            stores = {int(r[0]) for r in cursor.fetchall()}
            if any(r[1] not in stores for r in rows):
                raise ValueError('广告费用中存在非TT部门店铺')
        for row in rows:
            cursor.execute('INSERT INTO TK_FeiYong (RiQi,Dian,Guo,XiangMu,FeiYongE,BeiZhu,DaoRuRen,DaoRuShiJian) VALUES (%s,%s,%s,%s,%s,%s,%s,GETDATE())', (*row, actor))
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def register_tk_expenses(app, require_permission):
    @app.route('/finance/tk_expenses')
    @require_permission('finance_dept')
    def finance_tk_expenses():
        return render_template('财务部/finance_tk_expenses.html')

    @app.route('/api/finance/tk_expenses', methods=['GET', 'POST'])
    @require_permission('finance_dept')
    def api_finance_tk_expenses():
        try:
            if request.method == 'POST':
                upload = request.files.get('file')
                if not upload or not upload.filename.lower().endswith(('.xlsx', '.xlsm')):
                    raise ValueError('请选择xlsx或xlsm文件')
                kind = request.form.get('kind')
                rows = parse_rows(upload, kind)
                actor = str(session.get('feishu_user_name') or session.get('feishu_open_id') or '').strip()
                if not actor:
                    return jsonify(success=False, message='请重新登录后导入'), 401
                count = save_rows(rows, kind, actor, connect)
                return jsonify(success=True, message=f'成功导入 {count} 条', inserted=count)
            start = date.fromisoformat(request.args.get('start_date', ''))
            end = date.fromisoformat(request.args.get('end_date', ''))
            if start > end:
                raise ValueError('开始日期不能晚于结束日期')
            conn = connect()
            try:
                cursor = conn.cursor()
                cursor.execute(EXPENSE_QUERY, (start, end + timedelta(days=1)) * 3)
                data = [[v.isoformat(sep=' ') if isinstance(v, datetime) else v.isoformat() if isinstance(v, date) else str(v) if isinstance(v, Decimal) else v for v in row] for row in cursor.fetchall()]
                return jsonify(success=True, data=data)
            finally:
                conn.close()
        except ValueError as exc:
            return jsonify(success=False, message=str(exc)), 400
        except Exception:
            app.logger.exception('TK费用操作失败')
            return jsonify(success=False, message='费用操作失败，请检查文件格式或联系管理员查看日志'), 500


# 与新版工作簿一致：订单佣金汇总 + 手工费用明细 + 产品金额8%的平台佣金。
ORDER_FILTER = """
dd.DingGouShiJian >= %s AND dd.DingGouShiJian < %s
AND dd.ZhuangTai IN (N'待发货',N'已发货',N'平台发货',N'仓库已出库',N'待仓库出库',N'未知')
AND NOT EXISTS (SELECT 1 FROM dbo.TK_TuiHuo th WHERE th.DanHao_ShangPinID=dd.DanHao+dd.ChanPinID)
"""
EXPENSE_QUERY = f"""
SELECT * FROM (
SELECT CAST(dd.DingGouShiJian AS date) RiQi,dd.Dian,dd.Guo,N'网红佣金' XiangMu,
SUM(wh.YongJin) FeiYongE,N'网红佣金，来自TK_WangHongYongJin' BeiZhu,
N'系统' DengJiRen,MAX(dd.DingGouShiJian) DengJiShiJian
FROM dbo.TK_DingDan dd INNER JOIN dbo.TK_WangHongYongJin wh ON wh.DanHao=dd.DanHao
WHERE {ORDER_FILTER} AND wh.YongJin>0
GROUP BY CAST(dd.DingGouShiJian AS date),dd.Dian,dd.Guo
UNION ALL
SELECT RiQi,Dian,Guo,XiangMu,FeiYongE,BeiZhu,DaoRuRen,DaoRuShiJian
FROM dbo.TK_FeiYong WHERE RiQi >= %s AND RiQi < %s AND FeiYongE<>0
UNION ALL
SELECT CAST(dd.DingGouShiJian AS date),dd.Dian,dd.Guo,N'平台佣金',
SUM(ROUND(dd.ChanPinJinE*0.08,4)),N'平台佣金=产品金额*8%%，来自TK_DingDan',N'系统',MAX(dd.DingGouShiJian)
FROM dbo.TK_DingDan dd WHERE {ORDER_FILTER} AND ROUND(dd.ChanPinJinE*0.08,4)>0
GROUP BY CAST(dd.DingGouShiJian AS date),dd.Dian,dd.Guo
) result ORDER BY Dian,RiQi,Guo,XiangMu,DengJiShiJian
"""
