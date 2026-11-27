"""财务付款记录查询，沿用工作簿的青岛BD范围。"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

from flask import jsonify, render_template, request, send_file, session

from .database import connect as default_connect


PAYMENT_SCOPE = "ShenQingRen IN (SELECT BD FROM v_TK_BD_FenQu WHERE 位置=%s)"


def payment_query(args, actor):
    start = date.fromisoformat(args.get('start_date', ''))
    end = date.fromisoformat(args.get('end_date', ''))
    if start > end or end == date.max:
        raise ValueError('日期范围无效')
    conditions = ['ShenQingShiJian >= %s', 'ShenQingShiJian < %s', PAYMENT_SCOPE]
    params = [start, end + timedelta(days=1), '青岛']
    if args.get('unpaid') == '1':
        conditions.append("(FuKuanRen='' OR FuKuanRen IS NULL)")
    if args.get('mine') == '1':
        if not actor:
            raise ValueError('无法识别当前申请人，请重新登录')
        conditions.append('ShenQingRen=%s')
        params.append(actor)
    query = '''SELECT ID,HeZuoID,ShenQingRen,ShenQingShiJian,WangHongMing,ShouKuanZhangHao,
    FuFeiJinE,Dian,BeiZhu,XuHao,FuKuanDanHao,FuKuanRen,FuKuanShiJian,FuKuanBeiZhu,
    CASE WHEN DATALENGTH(FuKuanJieTu)>0 THEN 1 ELSE 0 END
    FROM TK_WangHong_HeZuo_FuKuan WHERE ''' + ' AND '.join(conditions) + ' ORDER BY ID DESC'
    return query, tuple(params)


def register_tk_payments(app, require_permission, connect=None):
    if connect is None:
        connect = default_connect

    @app.route('/finance/tk_payments')
    @require_permission('finance_dept')
    def finance_tk_payments():
        return render_template('财务部/finance_tk_payments.html')

    @app.route('/api/finance/tk_payments')
    @require_permission('finance_dept')
    def api_finance_tk_payments():
        try:
            query, params = payment_query(request.args, str(session.get('feishu_user_name') or '').strip())
            conn = connect()
            try:
                cursor = conn.cursor()
                cursor.execute(query, params)
                data = [[v.isoformat(sep=' ') if isinstance(v, datetime) else v.isoformat() if isinstance(v, date) else str(v) if isinstance(v, Decimal) else v for v in row] for row in cursor.fetchall()]
                return jsonify(success=True, data=data)
            finally:
                conn.close()
        except ValueError as exc:
            return jsonify(success=False, message=str(exc)), 400
        except Exception:
            app.logger.exception('付款查询失败')
            return jsonify(success=False, message='付款查询失败，请联系管理员查看日志'), 500

    @app.route('/api/finance/tk_payments/<int:payment_id>/screenshot')
    @require_permission('finance_dept')
    def finance_tk_payment_screenshot(payment_id):
        try:
            conn = connect()
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT FuKuanJieTu FROM TK_WangHong_HeZuo_FuKuan WHERE ID=%s AND ' + PAYMENT_SCOPE, (payment_id, '青岛'))
                row = cursor.fetchone()
                if not row or not row[0]:
                    return jsonify(success=False, message='没有付款截图'), 404
                content = bytes(row[0])
            finally:
                conn.close()
            from PIL import Image
            with Image.open(BytesIO(content)) as img:
                fmt = img.format
                if fmt not in ('JPEG', 'PNG', 'GIF', 'WEBP', 'BMP'):
                    return jsonify(success=False, message='截图格式暂不支持'), 415
            response = send_file(BytesIO(content), mimetype=Image.MIME[fmt], download_name=f'payment-{payment_id}.{fmt.lower()}')
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            return response
        except Exception:
            app.logger.exception('读取付款截图失败')
            return jsonify(success=False, message='读取付款截图失败'), 500
