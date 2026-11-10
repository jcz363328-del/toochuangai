import html
import re
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch

import app as site
from dashboard_workspace import template_catalog_context
from department_permissions import PERMISSION_CONFIG


class WorkspaceIntegrationTests(unittest.TestCase):
    def catalog(self, permissions, ai_member=True):
        with site.app.test_request_context('/dashboard'):
            site.session['feishu_user_id'] = 'dev_workspace_audit'
            site.session['feishu_user_name'] = 'Workspace audit'
            with patch.object(site.permission_manager, 'get_permission_records', return_value=PERMISSION_CONFIG), patch.object(site, '_can_access_ai_workspace', return_value=ai_member):
                return site.dashboard_workspace_catalog([{'function_name': permission} for permission in permissions]).get_json()

    def test_every_ai_source_card_has_a_catalog_entry(self):
        body = self.catalog([])
        group = next(group for group in body['groups'] if group['key'] == 'ai_dept')
        self.assertEqual(group['errors'], [])
        with site.app.test_request_context():
            source = site.app.jinja_env.loader.get_source(site.app.jinja_env, 'ai_modules.html')[0]
            flags, _ = template_catalog_context(source)
            rendered = site.render_template('ai_modules.html', **flags)
        titles = re.findall(r'<div\b[^>]*class="module-card"[^>]*>.*?<h3[^>]*>(.*?)</h3>', rendered, re.S)
        expected = {html.unescape(re.sub('<[^>]+>', '', title)).strip() for title in titles}
        self.assertGreaterEqual(len(expected), 20)
        self.assertEqual(expected, {item['menu'] for item in group['items']})

    def test_every_content_factory_source_card_has_a_catalog_entry(self):
        body = self.catalog([])
        group = next(group for group in body['groups'] if group['key'] == 'tk_project_group')
        with site.app.test_request_context():
            source = site.app.jinja_env.loader.get_source(site.app.jinja_env, 'tk_project.html')[0]
            flags, names = template_catalog_context(source)
            rendered = site.render_template('tk_project.html', accessible_functions=[{'function_name': name} for name in names], **flags)
        expected = {html.unescape(title) for title in re.findall(r'data-menu="([^"]+)"', rendered)}
        self.assertEqual(group['errors'], [])
        self.assertEqual(expected, {item['menu'] for item in group['items']})

    def test_every_catalog_target_is_registered_and_all_departments_render(self):
        body = self.catalog([])
        adapter = site.app.url_map.bind('localhost')
        self.assertEqual(len(body['groups']), 13)
        for group in body['groups']:
            self.assertEqual(group['errors'], [], group['key'])
            for item in group['items']:
                with self.subTest(group=group['key'], feature=item['menu']):
                    adapter.match(urlsplit(item['href']).path, method='GET')

    def test_single_feature_grant_does_not_hide_other_features(self):
        denied = self.catalog([])
        scoped = self.catalog(['daily_replenishment'])
        for first, second in zip(denied['groups'], scoped['groups']):
            self.assertEqual([item['id'] for item in first['items']], [item['id'] for item in second['items']])
        ai = next(group for group in scoped['groups'] if group['key'] == 'ai_dept')
        self.assertTrue(next(item for item in ai['items'] if item['menu'] == '日常补货')['allowed'])
        self.assertFalse(next(item for item in ai['items'] if item['menu'] == '历史销售数据曲线')['allowed'])

    def test_public_links_are_not_blocked_by_administration_scope(self):
        body = self.catalog([])
        ai = next(group for group in body['groups'] if group['key'] == 'ai_dept')
        listing = next(item for item in ai['items'] if item['menu'] == 'Listing 生成工作台 V2')
        self.assertTrue(listing['allowed'])
        inline = next(item for item in ai['items'] if item['menu'] == '创新项目删除')
        self.assertFalse(inline['allowed'])
        self.assertEqual(inline['required_permissions'], ['admin_functions'])

    def test_aba_import_and_ranking_view_have_separate_permissions(self):
        body = self.catalog([])
        ai = next(group for group in body['groups'] if group['key'] == 'ai_dept')
        entries = [item for item in ai['items'] if item['menu'] == 'ABA 排名导入与分析']
        self.assertEqual(len(entries), 2)
        imported = next(item for item in entries if '#abaRankingImport' in item['href'])
        self.assertFalse(imported['allowed'])
        self.assertEqual(imported['required_permissions'], ['listing_agent_aba_import'])

    def test_non_ai_member_catalog_does_not_contain_ai_features(self):
        body = self.catalog(['ai_dept', 'admin_functions'], ai_member=False)
        self.assertFalse(body['can_access_ai_workspace'])
        self.assertNotIn('ai_dept', {group['key'] for group in body['groups']})
        self.assertNotIn('历史销售数据曲线', {item['menu'] for group in body['groups'] for item in group['items']})
        operations = next(group for group in body['groups'] if group['key'] == 'operations')
        self.assertIn('智能补货中心-运营', {item['menu'] for item in operations['items']})

    def test_ai_page_denies_non_members_despite_individual_ai_permission(self):
        with site.app.test_request_context('/ai_modules'):
            site.session['feishu_user_id'] = 'test_non_ai'
            with patch.object(site.permission_manager, 'get_user_departments', return_value=[{'name': '总经办'}]), patch.object(site.permission_manager, 'check_user_permission', return_value=(True, '个人授权')):
                self.assertEqual(site.ai_modules()[1], 403)

    def test_department_lookup_failure_fails_closed(self):
        with site.app.test_request_context('/ai_modules'):
            site.session['feishu_user_id'] = 'test_non_ai'
            with patch.object(site.permission_manager, 'get_user_departments', side_effect=RuntimeError('offline')):
                self.assertFalse(site._can_access_ai_workspace())

    def test_ai_member_can_enter_ai_page(self):
        with site.app.test_request_context('/ai_modules'):
            site.session['feishu_user_id'] = 'test_ai'
            with patch.object(site.permission_manager, 'get_user_departments', return_value=[{'name': 'AI部'}]), patch.object(site.permission_manager, 'check_user_permission', return_value=(True, 'AI部')):
                self.assertIn('AI部功能', site.ai_modules())

    def test_signed_non_ai_simulation_hides_ai_workspace(self):
        with site.app.test_request_context('/ai_modules'):
            site.session['feishu_user_id'] = 'test_ai'
            site.g.permission_debug_state = {'departments': ['运营一部']}
            with patch.object(site.permission_manager, 'get_user_departments', return_value=[{'name': 'AI部'}]):
                self.assertFalse(site._can_access_ai_workspace())


if __name__ == '__main__':
    unittest.main()
