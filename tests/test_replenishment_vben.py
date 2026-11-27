import unittest
from unittest.mock import patch

import app as site
import daily_replenishment_operation as operation
from department_permissions import PERMISSION_CONFIG
from core.permissions.permission_seed_data import build_permission_seed_rows


class ReplenishmentVbenTests(unittest.TestCase):
    def setUp(self):
        self.client = site.app.test_client()
        with self.client.session_transaction() as session:
            session['feishu_user_id'] = 'dev_vben_test'
            session['feishu_user_name'] = '测试运营'

    def test_new_page_requires_ai_membership_even_with_permission(self):
        with patch.object(site.permission_manager, 'check_user_permission', return_value=(True, 'test')), patch.object(site, '_can_access_ai_workspace', return_value=False):
            self.assertEqual(403, self.client.get('/ai/replenishment-vben').status_code)
            self.assertEqual(403, self.client.get('/api/ai/replenishment-vben/config').status_code)

    def test_config_preserves_scoped_write_permissions_and_existing_api(self):
        access = {'can_write': True, 'read_stores': {'1', '2'}, 'write_stores': {'2'}}
        with patch.object(site.permission_manager, 'check_user_permission', return_value=(True, 'test')), patch.object(site, '_can_access_ai_workspace', return_value=True), patch.object(operation, 'scoped_query_executor', return_value=(None, access)):
            response = self.client.get('/api/ai/replenishment-vben/config')
            self.assertEqual(200, response.status_code)
            body = response.get_json()
            self.assertEqual(['2'], body['write_stores'])
            self.assertIn('/daily-replenishment-operation/data', body['data_url'])
            self.assertIn('/daily-replenishment-operation/sales-trend', body['trend_url'])

    def test_read_only_scope_stays_read_only(self):
        with patch.object(site.permission_manager, 'check_user_permission', return_value=(True, 'test')), patch.object(site, '_can_access_ai_workspace', return_value=True), patch.object(operation, 'scoped_query_executor', return_value=(None, {'can_write': False})):
            self.assertFalse(self.client.get('/api/ai/replenishment-vben/config').get_json()['can_write'])

    def test_separate_entry_serves_built_vue_app(self):
        with patch.object(site.permission_manager, 'check_user_permission', return_value=(True, 'test')), patch.object(site, '_can_access_ai_workspace', return_value=True):
            response = self.client.get('/ai/replenishment-vben')
            self.assertEqual(200, response.status_code)
            self.assertIn('/static/replenishment-vben/assets/', response.get_data(as_text=True))
        self.assertIn('daily_replenishment_operation.page', site.app.view_functions)

    def test_permission_seed_is_ai_only_and_separate(self):
        row = next(r for r in build_permission_seed_rows(PERMISSION_CONFIG) if r['gongneng'] == 'replenishment_vben')
        self.assertEqual('AI部；流程与AI部', row['bumen'])
        self.assertEqual('ai_dept', row['fujigongneng'])

if __name__ == '__main__':
    unittest.main()
