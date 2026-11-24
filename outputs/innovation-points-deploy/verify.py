import ast
import json
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify
from innovation.bjc import sf_db

source = Path('/app/innovation/web_app.py').read_text(encoding='utf-8')
tree = ast.parse(source)
ns = dict(request=request, jsonify=jsonify, sf_db=sf_db, datetime=datetime,
          ensure_special_storage=lambda: None, _safe_print=lambda *args: None)
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_PROJECT_POINTS_SQL' for t in node.targets):
        ns['_PROJECT_POINTS_SQL'] = ast.literal_eval(node.value)
    if isinstance(node, ast.FunctionDef) and node.name in ('get_point_records', 'get_user_points'):
        node.decorator_list = []
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<deployed-api>', 'exec'), ns)
app = Flask(__name__)
user = '叶雨菲'
raw = sf_db("SELECT COUNT(*), COUNT(DISTINCT 编号) FROM v_quanyuanchuangxin WHERE 发起人 = N'叶雨菲' AND 最高分 > 0")
print(json.dumps({'raw_rows_and_unique_projects': raw}, ensure_ascii=True))
with app.test_request_context('/innovation/api/get_point_records', query_string={'user_name': user, 'per_page': 10000}):
    response = ns['get_point_records']()
    assert not isinstance(response, tuple), str(response)
    payload = response.get_json()
    assert payload['success'], payload
    data = payload['data']
    projects = [r['description'] for r in data['records'] if r['source'] == '创新项目']
    assert len(projects) == len(set(projects)), 'duplicate project rewards remain'
    print(json.dumps({'records_success': True, 'project_records': len(projects), 'stats': data['stats']}, ensure_ascii=True))
with app.test_request_context('/innovation/api/get_user_points', query_string={'user_name': user}):
    response = ns['get_user_points']()
    assert not isinstance(response, tuple), str(response)
    payload = response.get_json()
    assert payload['success'], payload
    assert payload['data']['total_earned_points'] == data['stats']['total_earned']
    print(json.dumps({'balance_success': True, 'totals_match': True}, ensure_ascii=True))
