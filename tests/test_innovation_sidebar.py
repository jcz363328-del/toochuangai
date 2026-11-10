import unittest
from pathlib import Path

from flask import Flask, render_template
from jinja2 import FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]


class InnovationSidebarTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-only'
        self.app.jinja_loader = FileSystemLoader(ROOT / 'innovation/templates')
        for endpoint, path in (
            ('index', '/'), ('reauth', '/reauth'), ('api_menu_click', '/api/menu_click'),
            ('innovation.innovation_index', '/innovation/'),
            ('innovation.innovation_submit', '/innovation/submit'),
            ('innovation.innovation_manage', '/innovation/manage'),
            ('innovation.innovation_points', '/innovation/points'),
            ('innovation.innovation_leaderboard', '/innovation/leaderboard'),
            ('innovation.innovation_excellent_cases', '/innovation/excellent_cases'),
            ('innovation.static', '/innovation/static/<path:filename>'),
            ('innovation.innovation_uploaded_file', '/innovation/uploads/<path:filename>'),
            ('innovation.innovation_add_star_content', '/innovation/api/innovation_star_content'),
            ('innovation.innovation_save_chuangxinxing_proposal_note', '/innovation/api/chuangxinxing/proposal-note'),
            ('innovation.innovation_star_media', '/innovation/innovation_star_media/<path:filename>'),
        ):
            self.app.add_url_rule(path, endpoint, lambda **kwargs: '')

    def test_home_renders_existing_routes_and_real_dashboard(self):
        with self.app.test_request_context('/innovation/'):
            rendered = render_template('index.html')
        self.assertIn('aria-current="page"', rendered)
        self.assertIn('innovation-sidebar', rendered)
        self.assertEqual(rendered.count('id="recentProposalsBody"'), 1)
        self.assertNotIn('class="hero-section bg-light', rendered)
        self.assertNotIn('class="innovation-page-heading"', rendered)
        for chart in ('top-department', 'top-person', 'monthly-trend', 'category-distribution', 'top-proposal-counts', 'top-highest-scores'):
            self.assertIn(f'id="{chart}"', rendered)

    def test_navigation_retains_tracking_and_identity_rebind(self):
        with self.app.test_request_context('/innovation/submit'):
            rendered = render_template('base.html')
        self.assertIn('href="/reauth"', rendered)
        self.assertIn('aria-controls="innovationSidebar"', rendered)
        self.assertIn("logMenuClickAndGo('发起创新'", rendered)
        self.assertIn('aria-current="page"', rendered)

    def test_points_has_no_title_gap_and_uses_uncropped_reward_images(self):
        with self.app.test_request_context('/innovation/points'):
            rendered = render_template('points.html', feishu_user_name='测试人员')
        self.assertNotIn('积分中心</h3>', rendered)
        self.assertIn('object-fit: contain;', rendered)
        self.assertNotIn('object-fit: cover;', rendered)
        self.assertIn('个人积分与奖励', rendered)
        self.assertIn('loadUserPoints(); loadRewards();', rendered)

    def test_proposal_content_is_inserted_as_text(self):
        source = (ROOT / 'innovation/templates/index.html').read_text(encoding='utf-8')
        self.assertIn('cell.textContent = value', source)
        self.assertNotIn('body.innerHTML', source)

    def test_management_sections_have_one_active_panel(self):
        for section in ('innovations', 'rewards', 'meeting-draw', 'invalid'):
            with self.app.test_request_context('/innovation/manage?section=' + section):
                rendered = render_template('manage.html', is_committee_member=False, feishu_user_name='测试人员', feishu_user_id='test-user')
            expected = section if section != 'invalid' else 'innovations'
            self.assertIn(f'class="tab-pane fade show active" id="{expected}"', rendered)
            self.assertEqual(rendered.count('class="tab-pane fade show active"'), 1)
            self.assertEqual(rendered.count('aria-current="page"'), 1)
            self.assertNotIn('id="manageTabs"', rendered)
            self.assertNotIn('id="rewards-tab"', rendered)

    def test_star_sections_are_nested_and_select_one_panel(self):
        for tab in ('excellent', 'rank', 'share', 'talk', 'invalid'):
            with self.app.test_request_context('/innovation/excellent_cases?tab=' + tab):
                rendered = render_template('excellent_cases.html', cases=[], total_count=0, leaderboard=[], star_share_items=[], star_talk_items=[], can_add_star_content=False, can_manage_proposal_notes=False)
            expected = tab if tab != 'invalid' else 'excellent'
            self.assertIn(f'id="tab-{expected}" class="tab-panel active"', rendered)
            self.assertEqual(rendered.count('class="tab-panel active"'), 1)
            self.assertEqual(rendered.count('aria-current="page"'), 1)
            self.assertEqual(rendered.count('data-star-section='), 4)
            self.assertNotIn('class="innovation-tabs"', rendered)
            self.assertIn('class="innovation-star-navigation"', rendered)
            self.assertNotIn('<details class="innovation-star-navigation"', rendered)
