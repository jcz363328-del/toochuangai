import os
import unittest
from unittest.mock import patch

from flask import Flask
from department_permissions import FeishuPermissionManager, is_local_superadmin


class LocalSuperadminTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['LOCAL_SUPERADMIN_LOOPBACK_BOUND'] = True

    def test_local_permission_does_not_query_or_write_database(self):
        manager = FeishuPermissionManager()
        with patch.dict(os.environ, TC_LOCAL_SUPERADMIN='1'), \
                self.app.test_request_context('/', base_url='http://localhost',
                                              environ_base={'REMOTE_ADDR': '127.0.0.1'}), \
                patch.object(manager, 'get_permission_records', side_effect=AssertionError('DB accessed')):
            self.assertTrue(manager.check_user_permission('dev_user', 'any_feature')[0])

    def test_all_navigation_entries_are_visible(self):
        manager = FeishuPermissionManager()
        with patch.dict(os.environ, TC_LOCAL_SUPERADMIN='1'), \
                self.app.test_request_context('/', environ_base={'REMOTE_ADDR': '127.0.0.1'}), \
                patch.object(manager, 'get_permission_records', return_value={'*': {}, 'a': {}, 'b': {}}):
            self.assertEqual([r['function_name'] for r in manager.get_user_accessible_functions('dev')], ['a', 'b'])

    def test_rejects_disabled_remote_proxy_and_unbound_contexts(self):
        cases = [
            ('0', True, '127.0.0.1', 'localhost', {}),
            ('1', False, '127.0.0.1', 'localhost', {}),
            ('1', True, '192.168.1.2', 'localhost', {}),
            ('1', True, '127.0.0.1', 'localhost.attacker.com', {}),
            ('1', True, '127.0.0.1', 'localhost', {'X-Forwarded-For': '1.2.3.4'}),
        ]
        for enabled, bound, addr, host, headers in cases:
            with self.subTest(enabled=enabled, bound=bound, addr=addr, host=host, headers=headers):
                self.app.config['LOCAL_SUPERADMIN_LOOPBACK_BOUND'] = bound
                with patch.dict(os.environ, TC_LOCAL_SUPERADMIN=enabled), \
                        self.app.test_request_context('/', base_url='http://' + host,
                                                      environ_base={'REMOTE_ADDR': addr}, headers=headers):
                    self.assertFalse(is_local_superadmin())

    def test_no_request_context_cannot_grant_permission(self):
        with patch.dict(os.environ, TC_LOCAL_SUPERADMIN='1'):
            self.assertFalse(is_local_superadmin())


if __name__ == '__main__':
    unittest.main()
