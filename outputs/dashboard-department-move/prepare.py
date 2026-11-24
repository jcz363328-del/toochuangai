from pathlib import Path
import ast
root=Path.cwd();out=root/'outputs/dashboard-department-move'
source=(out/'before-app.py').read_text(encoding='utf-8')
start=source.index("    for key, name, endpoint, icon in [\n        ('tk_overall_dashboard'")
end=source.index("    operations = next(group for group in groups",start)
source=source[:start]+source[end:]
old="                           dept_id='shenzhen_dept')"
assert source.count(old)==1
source=source.replace(old,"                           dept_id='shenzhen_dept',\n                           can_sz_dashboard=_current_user_has_permission('tk_total_dashboard', user_id))",1)
ast.parse(source);(out/'app.py').write_text(source,encoding='utf-8')
(out/'templates').mkdir(exist_ok=True)
for name in ['tk_project.html','operation_dept.html','finance_sz_dashboard.html']:
 (out/'templates'/name).write_bytes((root/'templates'/name).read_bytes())
(out/'Dockerfile').write_text('FROM toochuangai-single:latest\nCOPY app.py /app/app.py\nCOPY templates/ /app/templates/\n',encoding='utf-8')
