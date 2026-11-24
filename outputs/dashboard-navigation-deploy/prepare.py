from pathlib import Path
import ast
root=Path.cwd()
out=root/'outputs/dashboard-navigation-deploy'
before=(out/'before-app.py').read_text(encoding='utf-8')
source=(root/'app.py').read_text(encoding='utf-8-sig')
start=source.index("    for key, name, endpoint, icon in [\n        ('tk_overall_dashboard'")
end=source.index("    operations = next(group for group in groups",start)
needle="    operations = next(group for group in groups if group['key'] == 'operations')"
assert before.count(needle)==1
result=before.replace(needle,source[start:end]+needle,1)
old="                           dept_id='general_office')"
new="                           dept_id='general_office',\n                           can_business_analysis=_current_user_has_permission('business_analysis', user_id))"
assert result.count(old)==1
result=result.replace(old,new,1)
ast.parse(result)
(out/'app.py').write_text(result,encoding='utf-8')
(out/'templates').mkdir(exist_ok=True)
for name in ['dashboard.html','operation_dept.html','finance_sz_dashboard.html']:
 (out/'templates'/name).write_bytes((root/'templates'/name).read_bytes())
(out/'Dockerfile').write_text('FROM toochuangai-single:latest\nCOPY app.py /app/app.py\nCOPY templates/ /app/templates/\n',encoding='utf-8')
