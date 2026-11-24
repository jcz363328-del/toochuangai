from pathlib import Path
import sys,ast
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from flask import Flask,jsonify,request,render_template
from bjc import sf_db
app=Flask(__name__,template_folder=str(root/'templates'),static_folder=str(root/'static'))
scope=dict(app=app,jsonify=jsonify,request=request,sf_db=sf_db,_operation_dept_has_access=lambda:True)
source=ast.parse((root/'app.py').read_text(encoding='utf-8-sig'))
names={'api_operation_fba_shipping_methods':'/api/operation/fba_shipping_methods','api_operation_fba_shipping_method_shops':'/api/operation/fba_shipping_methods/shops','export_operation_fba_shipping_methods':'/api/operation/fba_shipping_methods/export'}
funcs=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in names]
for f in funcs:f.decorator_list=[]
exec(compile(ast.Module(body=funcs,type_ignores=[]),'<preview-api>','exec'),scope)
for name,path in names.items():app.add_url_rule(path,view_func=scope[name])
@app.route('/')
def index():return render_template('operation_fba_shipping_methods.html',back_url='/',source_name='首页',user_name='页面验收')
app.run(host='127.0.0.1',port=18604,debug=False)
