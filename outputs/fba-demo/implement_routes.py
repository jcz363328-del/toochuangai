from pathlib import Path
import ast
p=Path('app.py');s=p.read_text(encoding='utf-8-sig');tree=ast.parse(s);lines=s.splitlines(keepends=True)
replacements={
'api_operation_fba_shipping_methods':'''def api_operation_fba_shipping_methods():
    if not _operation_dept_has_access():
        return jsonify({'success': False, 'message': '无权限访问运营部门数据'}), 403
    try:
        from fba_shipping_service import load_snapshot, payload
        return jsonify({'success': True, 'data': payload(load_snapshot(sf_db), request.args)})
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': '分页参数无效'}), 400
    except Exception:
        app.logger.exception('FBA shipping query failed')
        return jsonify({'success': False, 'message': '货件数据读取失败，请稍后重试'}), 503
''',
'api_operation_fba_shipping_method_shops':'''def api_operation_fba_shipping_method_shops():
    if not _operation_dept_has_access():
        return jsonify({'success': False, 'message': '无权限访问运营部门数据'}), 403
    try:
        from fba_shipping_service import load_snapshot
        snapshot = load_snapshot(sf_db)
        return jsonify({'success': True, 'data': {'shops': snapshot['shops'],
                       'shipping_methods': snapshot['shipping_methods']}})
    except Exception:
        app.logger.exception('FBA shipping options failed')
        return jsonify({'success': False, 'message': '筛选选项读取失败，请稍后重试'}), 503
'''}
for node in sorted((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in replacements),key=lambda n:n.lineno,reverse=True):
 lines[node.lineno-1:node.end_lineno]=[replacements[node.name]]
s=''.join(lines)
marker="@app.route('/operation/fba_shipping_methods')"
new='''@app.route('/api/operation/fba_shipping_methods/export')
@require_permission('operation_fba_shipping')
def export_operation_fba_shipping_methods():
    if not _operation_dept_has_access():
        return jsonify({'success': False, 'message': '无权限访问运营部门数据'}), 403
    try:
        from flask import Response
        from fba_shipping_service import load_snapshot, csv_rows
        snapshot = load_snapshot(sf_db)
        response = Response(csv_rows(snapshot, dict(request.args)), content_type='text/csv; charset=utf-8')
        response.headers['Content-Disposition'] = 'attachment; filename="fba_shipping.csv"'
        response.headers['Cache-Control'] = 'no-store'
        return response
    except Exception:
        app.logger.exception('FBA shipping export failed')
        return jsonify({'success': False, 'message': '导出失败，请稍后重试'}), 503


'''
assert s.count(marker)==1;s=s.replace(marker,new+marker,1);ast.parse(s);p.write_text(s,encoding='utf-8')
