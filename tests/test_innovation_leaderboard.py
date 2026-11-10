import ast
import unittest
from pathlib import Path
from unittest.mock import Mock

from flask import Flask, redirect, render_template, session, url_for
from jinja2 import FileSystemLoader

from innovation.leaderboard import load_points_leaderboard


ROOT = Path(__file__).resolve().parents[1]


class InnovationLeaderboardTests(unittest.TestCase):
    def test_all_time_earned_points_and_deterministic_top_twenty(self):
        query = Mock(return_value=[('甲', 100), ('乙', 100), ('丙', 50), ('丁', 20)])
        leaders = load_points_leaderboard(query)
        sql = query.call_args.args[0]
        self.assertIn('TOP 20', sql)
        self.assertIn('SUM(COALESCE(最高分, 0))', sql)
        self.assertNotIn('创新_消费', sql)
        self.assertNotIn('YEAR(', sql)
        self.assertIn('姓名 ASC', sql)
        self.assertEqual([leader['rank'] for leader in leaders], [1, 1, 3, 4])
        self.assertEqual(leaders[0]['tier'], 'gold')
        self.assertEqual(leaders[2]['tier'], 'bronze')

    def test_empty_and_maximum_size(self):
        self.assertEqual(load_points_leaderboard(lambda sql: []), [])
        rows = [('用户' + str(index), 100 - index) for index in range(30)]
        self.assertEqual(len(load_points_leaderboard(lambda sql: rows)), 20)

    def test_route_requires_login_and_reports_failure(self):
        application = Flask(__name__)
        application.secret_key = 'test-only'
        application.jinja_loader = FileSystemLoader(ROOT / 'innovation/templates')
        application.add_url_rule('/auth', 'feishu_auth', lambda: '')
        source = ast.parse((ROOT / 'innovation/web_app.py').read_text(encoding='utf-8-sig'))
        function = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'points_leaderboard')
        function.decorator_list = []
        loader = Mock(return_value=[])
        renderer = Mock(return_value='rendered')
        namespace = dict(session=session, redirect=redirect, url_for=url_for, render_template=renderer, load_points_leaderboard=loader, sf_db=Mock())
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<route>', 'exec'), namespace)
        with application.test_request_context('/leaderboard'):
            self.assertEqual(namespace['points_leaderboard']().status_code, 302)
            loader.assert_not_called()
            session['feishu_user_id'] = 'test-user'
            self.assertEqual(namespace['points_leaderboard'](), 'rendered')
            loader.side_effect = RuntimeError('database unavailable')
            self.assertEqual(namespace['points_leaderboard'](), ('rendered', 503))

    def test_template_escapes_names_and_renders_tiers(self):
        from test_innovation_sidebar import InnovationSidebarTests
        setup = InnovationSidebarTests()
        setup.setUp()
        leaders = load_points_leaderboard(lambda sql: [('<script>alert(1)</script>', 100), ('乙', 90), ('丙', 80)])
        with setup.app.test_request_context('/innovation/leaderboard'):
            rendered = render_template('leaderboard.html', leaders=leaders, leaderboard_error=False)
        self.assertNotIn('<script>alert(1)</script>', rendered)
        for tier in ('gold', 'silver', 'bronze'):
            self.assertIn('tier-' + tier, rendered)
        self.assertEqual(rendered.count('class="leaderboard-row '), 3)
        self.assertNotIn('class="leaderboard-tier"', rendered)
        for label in ('创新领航者', '创新先锋', '创新能手', '创新精英', '创新新锐'):
            self.assertNotIn(label, rendered)
        self.assertEqual(rendered.count('class="leaderboard-rank-icon"'), 3)
        for name in ('first', 'second', 'third'):
            self.assertIn('images/rank-icons/' + name + '.png', rendered)
            asset = ROOT / 'innovation/static/images/rank-icons' / (name + '.png')
            self.assertTrue(asset.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
