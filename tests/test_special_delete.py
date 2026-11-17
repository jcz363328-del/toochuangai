import unittest
from unittest.mock import patch
from flask import Flask, session
from pathlib import Path
import ast
import logging
from types import SimpleNamespace
from flask import jsonify
from innovation.special_support import _same_department, permission_manager, special_permission_subject, special_subject_in_departments

# 单独加载权限和删除函数，避免页面模块依赖生产环境的消息服务。
source = Path(__file__).resolve().parents[1] / 'innovation' / 'specials.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {'_can_delete_special', 'delete_special'}]
specials = SimpleNamespace()
specials.__dict__.update(session=session, jsonify=jsonify, permission_manager=permission_manager,
    special_permission_subject=special_permission_subject, special_subject_in_departments=special_subject_in_departments, _same_department=_same_department, logger=logging.getLogger(__name__),
    _get_current_feishu_user_name=lambda: str(session.get('feishu_user_name') or ''),
    ensure_special_storage=lambda: None, _load_special=lambda special_id: None, dui_db=lambda sql: None)
exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), specials.__dict__)


class SpecialDeleteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test'

    def test_named_users_and_ai_members_only(self):
        cases = [('韩雅俊', '', True), ('蔡晶', '', True), ('普通员工', '流程与AI部', True), ('管理员', '人力资源与行政部', False), ('普通员工', '销售部', False)]
        for name, department, expected in cases:
            with self.subTest(name=name, department=department), self.app.test_request_context('/'), patch.object(specials.permission_manager, 'get_user_departments', return_value=[]), patch.object(specials.permission_manager, '_user_in_department_tree', return_value=False):
                session.update(feishu_user_name=name, feishu_user_id='user', user_department=department)
                self.assertEqual(specials._can_delete_special(), expected)

    def test_ai_child_department(self):
        with self.app.test_request_context('/'), patch.object(specials.permission_manager, 'get_user_departments', return_value=[{'name': '子部门', 'department_id': 'child'}]), patch.object(specials.permission_manager, '_user_in_department_tree', return_value=True):
            session['feishu_user_id'] = 'user'
            self.assertTrue(specials._can_delete_special())

    def test_unauthorized_request_never_writes(self):
        with self.app.test_request_context('/'), patch.object(specials, 'ensure_special_storage'), patch.object(specials, '_can_delete_special', return_value=False), patch.object(specials, 'dui_db') as execute:
            self.assertEqual(specials.delete_special(1)[1], 403)
            execute.assert_not_called()

    def test_deletion_preserves_ideas_and_points(self):
        with self.app.test_request_context('/'), patch.object(specials, 'ensure_special_storage'), patch.object(specials, '_can_delete_special', return_value=True), patch.object(specials, '_load_special', return_value={'zhuanxiang_id': 1}), patch.object(specials, 'dui_db') as execute:
            self.assertTrue(specials.delete_special(1).get_json()['success'])
            sql = execute.call_args.args[0]
            self.assertIn("zhuangtai = 'yishanchu'", sql)
            self.assertNotIn('chuangxin_tibao1', sql)

    def test_missing_special_returns_404(self):
        with self.app.test_request_context('/'), patch.object(specials, 'ensure_special_storage'), patch.object(specials, '_can_delete_special', return_value=True), patch.object(specials, '_load_special', return_value=None), patch.object(specials, 'dui_db') as execute:
            self.assertEqual(specials.delete_special(1)[1], 404)
            execute.assert_not_called()

    def test_request_department_override_removes_real_named_user_grant(self):
        from flask import g
        with self.app.test_request_context('/'):
            session.update(feishu_user_name='韩雅俊', feishu_user_id='real', user_department='流程与AI部')
            g.permission_debug_state = {'departments': ['销售部'], 'user_name': '', 'user_open_id': ''}
            self.assertFalse(specials._can_delete_special())

    def test_request_simulated_named_user_can_delete(self):
        from flask import g
        with self.app.test_request_context('/'):
            g.permission_debug_state = {'departments': ['销售部'], 'user_name': '蔡晶', 'user_open_id': ''}
            self.assertTrue(specials._can_delete_special())
