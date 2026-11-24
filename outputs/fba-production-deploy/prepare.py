from pathlib import Path
import ast
root=Path.cwd();out=root/'outputs/fba-production-deploy'
source=(root/'app.py').read_text(encoding='utf-8-sig');runtime=(out/'before-app.py').read_text(encoding='utf-8-sig')
names={'api_operation_fba_shipping_methods','api_operation_fba_shipping_method_shops'}
tree=ast.parse(source);source_lines=source.splitlines(keepends=True)
replacements={n.name:''.join(source_lines[n.lineno-1:n.end_lineno])+'\n' for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names}
lines=runtime.splitlines(keepends=True)
for n in sorted([n for n in ast.parse(runtime).body if isinstance(n,ast.FunctionDef) and n.name in names],key=lambda n:n.lineno,reverse=True):lines[n.lineno-1:n.end_lineno]=[replacements[n.name]]
runtime=''.join(lines)
n=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='export_operation_fba_shipping_methods')
export=''.join(source_lines[min(d.lineno for d in n.decorator_list)-1:n.end_lineno])+'\n\n\n'
marker="@app.route('/operation/fba_shipping_methods')";assert runtime.count(marker)==1
runtime=runtime.replace(marker,export+marker,1);ast.parse(runtime)
(out/'app.py').write_text(runtime,encoding='utf-8')
# Keep the production template reviewable rather than minified.
p=root/'templates/operation_fba_shipping_methods.html';s=p.read_text(encoding='utf-8')
a,b=s.split('<style>',1);css,html=b.split('</style>',1)
p.write_text(a.replace('><','>\n<')+'<style>\n'+css.replace(';',';\n').replace('}','}\n')+'</style>'+html.replace('><','>\n<'),encoding='utf-8')
(out/'templates').mkdir(exist_ok=True);(out/'static/js').mkdir(parents=True,exist_ok=True)
for rel in ['fba_shipping_service.py','templates/operation_fba_shipping_methods.html','static/js/fba_shipping.js']:
 (out/rel).write_bytes((root/rel).read_bytes())
(out/'Dockerfile').write_text('FROM toochuangai-single:latest\nCOPY app.py fba_shipping_service.py /app/\nCOPY templates/operation_fba_shipping_methods.html /app/templates/operation_fba_shipping_methods.html\nCOPY static/js/fba_shipping.js /app/static/js/fba_shipping.js\n',encoding='utf-8')
