import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from dashboard_workspace import extract_features, template_catalog_context, feature_anchor

from flask import Flask, jsonify, session
from jinja2 import Environment, FileSystemLoader


class WorkspaceCatalogTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        source = Path(__file__).resolve().parents[1].joinpath('app.py').read_text(encoding='utf-8-sig')
        function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == 'dashboard_workspace_catalog')
        function.decorator_list = []
        self.rendered = []

        def render(template, **context):
            self.rendered.append(context['dept_id'])
            return '<div></div>'

        namespace = {'app': self.app, 'session': session, 'jsonify': jsonify,
                     '_can_access_ai_workspace': lambda: True,
                     'permission_manager': SimpleNamespace(get_user_accessible_functions=lambda user: [{'function_name': 'tk_dashboard_88'}], get_permission_records=lambda: {'tk_dashboard_88': {}}),
                     '_permission_debug_effective_state': lambda: {},
                     '_current_user_has_permission': lambda key, user: key == 'tk_dashboard_88',
                     '_OPERATION_DEPT_FUNCTIONS': {'operation_dept_1', 'operation_dept_6'},
                     '_normalize_dashboard_functions': lambda items: [], 'render_template': render,
                     'url_for': lambda endpoint, **values: '/' + endpoint}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<catalog>', 'exec'), namespace)
        self.catalog = namespace['dashboard_workspace_catalog']
        self.namespace = namespace

    def test_login_required(self):
        with self.app.test_request_context():
            self.assertEqual(self.catalog()[1], 401)

    def test_operations_include_newcomer_without_department_permission(self):
        with self.app.test_request_context():
            session['feishu_user_id'] = 'member'
            body = self.catalog().get_json()
            self.assertTrue(body['success'])
            self.assertIn('newcomer_group', self.rendered)
            self.assertEqual(len(self.rendered), 3)
            self.assertIn('items', body['groups'][0])
            self.assertNotIn('pages', body['groups'][0])
            self.assertEqual(body['groups'][0]['key'], 'operations')

    def test_extracts_all_links(self):
        html = '<div class="module-card"><h3>Listing</h3><a href="/listing">Open</a><a href="/rank">Rank</a></div>'
        self.assertEqual([item['href'] for item in extract_features(html, '/ai')], ['/listing', '/rank'])

    def test_distinct_features_with_same_address_are_preserved(self):
        html = '<div class="module-card"><h3>Analysis</h3><a href="/tool">Open</a></div><div class="module-card"><h3>Ranking</h3><a href="/tool">Open</a></div>'
        self.assertEqual([item['menu'] for item in extract_features(html, '/ai')], ['Analysis', 'Ranking'])

    def test_permission_scope_and_inline_actions(self):
        denied = '<div data-permission="admin_functions" data-allowed="false"><div class="module-card"><h3>Delete</h3><button onclick="remove()">Remove</button></div></div>'
        self.assertEqual(extract_features(denied, '/ai'), [])
        permitted = denied.replace('data-allowed="false"', 'data-allowed="true"')
        item = extract_features(permitted, '/ai')[0]
        self.assertEqual(item['scopePermission'], 'admin_functions')
        self.assertEqual(item['href'], '/ai#' + feature_anchor('Delete'))

    def test_full_ai_template_retains_tools_and_inline_actions(self):
        environment = Environment(loader=FileSystemLoader(Path(__file__).resolve().parents[1] / 'templates'))
        environment.globals['url_for'] = lambda endpoint, **values: '/' + endpoint
        flags = {name: True for name in ['can_ai_dept', 'can_ai_full', 'can_daily_replenishment', 'can_daily_replenishment_operation', 'can_group_performance', 'can_business_analysis', 'can_ads_monitor', 'can_video_claw', 'can_value_evaluation', 'can_value_evaluation_admin', 'can_historical_sales']}
        html = environment.get_template('ai_modules.html').render(**flags)
        names = {item['menu'] for item in extract_features(html, '/ai_modules')}
        self.assertTrue({'日常补货', '组别经营数据', '版本更新通知', '创新项目删除', '权限身份切换（测试）', 'Listing 生成工作台 V2', 'ABA 排名导入与分析'}.issubset(names))

    def test_button_features_and_deduplication(self):
        html = '''<div class="module-card"><h3>Import</h3><input type="file"><button onclick="upload()">Upload</button></div>
        <div class="quick-card" data-menu="Shipping" data-href="/shipping?source=one"><h3>Shipping</h3></div>
        <div class="quick-card" data-menu="Shipping" data-href="/shipping?source=two"><h3>Shipping</h3></div>'''
        items = extract_features(html, '/finance')
        self.assertEqual([item['href'] for item in items], ['/finance#' + feature_anchor('Import'), '/shipping'])
        self.assertEqual(items[1]['menu'], 'Shipping')

    def configure_full_catalog(self):
        self.app.jinja_loader = FileSystemLoader(Path(__file__).resolve().parents[1] / 'templates')
        self.app.jinja_env.globals['url_for'] = self.namespace['url_for']
        self.namespace['render_template'] = lambda template, **context: self.app.jinja_env.get_template(template).render(**context)
        groups = ['tk_project_group', 'ai_dept', 'finance_dept', 'hr_admin_dept', 'warehouse_group', 'tech_dept', 'visual_design_dept', 'photography_dept', 'procurement_dept', 'general_office', 'rd_dept', 'shenzhen_dept']
        self.namespace['_normalize_dashboard_functions'] = lambda items: [{'function_name': key, 'name': key} for key in groups]

    def test_all_department_templates_render_without_errors(self):
        self.configure_full_catalog()
        with self.app.test_request_context():
            session['feishu_user_id'] = 'member'
            body = self.catalog().get_json()
        for group in body['groups']:
            self.assertEqual(group['errors'], [], group['key'])
            if group['key'] != 'warehouse_group':
                self.assertTrue(group['items'], group['key'])

    def test_complete_catalog_independent_of_user_permissions(self):
        self.configure_full_catalog()
        with self.app.test_request_context():
            session['feishu_user_id'] = 'member'
            denied = self.catalog([]).get_json()
            full_permissions = [{'function_name': key} for key in ['admin_functions', 'historical_sales', 'daily_replenishment', 'daily_replenishment_operation', 'ai_dept', 'tk_joint_dashboard_all']]
            permitted = self.catalog(full_permissions).get_json()
        for first, second in zip(denied['groups'], permitted['groups']):
            self.assertEqual([item['id'] for item in first['items']], [item['id'] for item in second['items']])
        ai = next(group for group in denied['groups'] if group['key'] == 'ai_dept')
        self.assertTrue(any(item['menu'] == '日常补货' and not item['allowed'] for item in ai['items']))
        ai = next(group for group in permitted['groups'] if group['key'] == 'ai_dept')
        self.assertTrue(any(item['menu'] == '日常补货' and item['allowed'] for item in ai['items']))

    def test_template_memberships_and_flags_are_discovered(self):
        source = "{% set has_tool = 'future_tool' in ns.fnames %}{% if can_future_tool %}Future{% endif %}"
        flags, permissions = template_catalog_context(source)
        self.assertTrue(flags['can_future_tool'])
        self.assertIn('future_tool', permissions)

    def test_action_anchor_does_not_change_when_other_cards_are_hidden(self):
        first = '<div class="module-card"><h3>First</h3><a href="/first">Open</a></div>'
        action = '<div class="module-card"><h3>版本通知</h3><button onclick="notify()">Send</button></div>'
        self.assertEqual(extract_features(first + action, '/ai')[-1]['href'], extract_features(action, '/ai')[0]['href'])

    def test_explicit_feature_permission_is_separate_from_group_permission(self):
        html = '<div data-permission="admin_functions"><div class="module-card"><h3>Monitor</h3><a href="/monitor">Open</a></div></div>'
        item = extract_features(html, '/ai')[0]
        self.assertEqual(item['permission'], '')
        self.assertEqual(item['scopePermission'], 'admin_functions')

    def test_child_permission_does_not_require_department_permission(self):
        self.configure_full_catalog()

        function_name = 'daily_replenishment'

        def protected_page():
            return function_name

        self.app.add_url_rule('/daily_replenishment.page', endpoint='test_daily', view_func=protected_page)
        with self.app.test_request_context():
            session['feishu_user_id'] = 'member'
            body = self.catalog([{'function_name': 'daily_replenishment'}]).get_json()
        ai = next(group for group in body['groups'] if group['key'] == 'ai_dept')
        replenishment = next(item for item in ai['items'] if item['menu'] == '日常补货')
        self.assertTrue(replenishment['allowed'])
        self.assertEqual(replenishment['required_permissions'], ['daily_replenishment'])


if __name__ == '__main__':
    unittest.main()
