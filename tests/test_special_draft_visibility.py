import unittest
from unittest.mock import patch
from flask import Flask, session
from innovation import special_support as support


class SpecialDraftVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test'

    def test_only_designated_departments_see_drafts(self):
        for department, expected in [('流程与AI部', True), ('人力资源与行政部', True), ('销售部', False), ('AI部', False)]:
            with self.subTest(department=department), self.app.test_request_context('/'):
                session['user_department'] = department
                self.assertEqual(support.user_can_view_special_drafts(), expected)

    def test_nested_department_uses_organization_tree(self):
        with self.app.test_request_context('/'), patch.object(support.permission_manager, 'get_user_departments', return_value=[{'name': '新子部门', 'department_id': 'child'}]), patch.object(support.permission_manager, '_user_in_department_tree', side_effect=lambda rows, root: root == '人力资源与行政部') as tree:
            session['feishu_user_id'] = 'user'
            self.assertTrue(support.user_can_view_special_drafts())
            self.assertTrue(tree.called)

    def test_debug_department_does_not_inherit_real_session_access(self):
        with self.app.test_request_context('/'):
            session['user_department'] = '流程与AI部'
            session['permission_debug_departments'] = ['销售部']
            self.assertFalse(support.user_can_view_special_drafts())

    def test_department_fallback_ignores_invalid_and_duplicate_names(self):
        with patch.object(support.permission_manager, 'get_user_departments', return_value=[{'name': '流程与AI部'}, {'name': '流程与AI部'}, {'name': '旧部门', 'status': 'invalid'}]):
            self.assertEqual(support.get_special_user_department('user'), '流程与AI部')

    def test_lookup_failure_does_not_grant_access(self):
        with self.app.test_request_context('/'), patch.object(support.permission_manager, 'get_user_departments', side_effect=RuntimeError):
            session['feishu_user_id'] = 'user'
            self.assertFalse(support.user_can_view_special_drafts())

    def test_request_state_overrides_real_and_stale_session_departments(self):
        from flask import g
        with self.app.test_request_context('/'):
            session.update(user_department='流程与AI部', permission_debug_departments=['人力资源与行政部'])
            g.permission_debug_state = {'departments': ['销售部'], 'user_name': '', 'user_open_id': ''}
            self.assertFalse(support.user_can_view_special_drafts())

    def test_request_state_reset_ignores_stale_session_debug(self):
        from flask import g
        with self.app.test_request_context('/'):
            session.update(user_department='销售部', permission_debug_departments=['流程与AI部'])
            g.permission_debug_state = {'departments': [], 'user_name': '', 'user_open_id': ''}
            self.assertFalse(support.user_can_view_special_drafts())
