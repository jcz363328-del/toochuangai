from pathlib import Path
import ast
import shutil

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
source = (out / 'before-app.py').read_text(encoding='utf-8-sig')
marker = "@app.route('/finance_modules')"
registration = '''from finance_tk_expenses import register_tk_expenses
register_tk_expenses(app, require_permission)
from finance_tk_payments import register_tk_payments
register_tk_payments(app, require_permission)


'''
assert source.count(marker) == 1
assert 'register_tk_payments' not in source
source = source.replace(marker, registration + marker, 1)
ast.parse(source)
(out / 'app.py').write_text(source, encoding='utf-8')
template = (out / 'before-finance_modules.html').read_text(encoding='utf-8-sig')
local = (root / 'templates/finance_modules.html').read_text(encoding='utf-8-sig')
cards = local.split('<div class="modules-grid">', 1)[1].split('<!--', 1)[0]
assert template.count('<div class="modules-grid">') == 1
template = template.replace('<div class="modules-grid">', '<div class="modules-grid">' + cards, 1)
(out / 'templates/finance_modules.html').write_text(template, encoding='utf-8')
for rel in ['finance_tk_expenses.py', 'finance_tk_payments.py', 'templates/finance_tk_expenses.html', 'templates/finance_tk_payments.html']:
    shutil.copy2(root / rel, out / rel)
(out / 'Dockerfile').write_text('''FROM toochuangai-single:latest
COPY app.py finance_tk_expenses.py finance_tk_payments.py /app/
COPY templates/ /app/templates/
''', encoding='utf-8')
