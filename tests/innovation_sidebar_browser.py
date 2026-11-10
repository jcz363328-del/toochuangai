import json
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright


render = """
import sys
sys.path.insert(0, '/app/tests')
from test_innovation_sidebar import InnovationSidebarTests
from flask import render_template
test = InnovationSidebarTests()
test.setUp()
with test.app.test_request_context('/innovation/'):
    print(render_template('index.html'))
"""
html = subprocess.check_output(['/opt/web/bin/python', '-c', render]).decode()
with sync_playwright() as runtime:
    browser = runtime.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1584, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))

    def respond(route):
        path = route.request.url.split('preview.local', 1)[1].split('?', 1)[0]
        if path.startswith('/innovation/api/'):
            payload = {'success': True, 'data': {}}
            if path.endswith('get_statistics'):
                payload['data'] = {'pending_count': 0}
            if path.endswith('get_rewards'):
                payload['data'] = []
            if path.endswith('meeting_draw/state'):
                payload['meetings'] = {key: {'label': label, 'round': 1, 'candidates': [], 'selected': [], 'selected_details': [], 'latest_result': [], 'latest_group_excluded': [], 'can_draw': False, 'can_cancel': False} for key, label in [('review', '创新评审会'), ('group', '创新小组会')]}
            if path.endswith('get_innovations'):
                payload['data'] = [{'title': '<script>提案标题</script>', 'initiator': '测试人员', 'initiation_time': '2026-11-10'}]
            route.fulfill(content_type='application/json', body=json.dumps(payload))
        elif path.startswith('/innovation/static/'):
            target = Path('/app/innovation/static') / path.removeprefix('/innovation/static/')
            route.fulfill(path=str(target))
        else:
            route.fulfill(content_type='text/html', body=html)

    page.route('http://preview.local/**', respond)
    page.goto('http://preview.local/innovation/', wait_until='networkidle', timeout=90000)
    page.wait_for_function("document.getElementById('recentProposalsBody').textContent.includes('测试人员')")
    assert page.locator('#recentProposalsBody tr').count() == 1
    assert page.locator('#recentProposalsBody script').count() == 0
    assert page.locator('.innovation-global-search').get_attribute('action') == '/innovation/manage'
    assert page.locator('.innovation-nav-item[aria-current="page"]').count() == 1
    assert page.locator('.dashboard-chart canvas').count() == 6
    brand = page.locator('.innovation-brand').bounding_box()
    header = page.locator('.innovation-topbar').bounding_box()
    assert abs(brand['height'] - header['height']) < 1
    assert page.locator('.dashboard-heading').count() == 0
    assert page.locator('.dashboard-filterbar #dashboardDataStatus').count() == 1
    filters = page.locator('.dashboard-filterbar').bounding_box()
    assert page.locator('.innovation-page-heading').count() == 0
    assert filters['y'] <= header['y'] + header['height'] + 24
    recent = page.locator('.innovation-recent').bounding_box()
    assert abs(filters['x'] - recent['x']) < 1
    assert abs(filters['width'] - recent['width']) < 1
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path='/qa/innovation-sidebar-desktop.png', full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_timeout(300)
    page.locator('.innovation-menu-toggle').click()
    assert page.locator('.innovation-menu-toggle').get_attribute('aria-expanded') == 'true'
    page.keyboard.press('Escape')
    assert page.locator('.innovation-menu-toggle').get_attribute('aria-expanded') == 'false'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path='/qa/innovation-sidebar-mobile.png', full_page=True)
    assert not errors, errors
    page.set_viewport_size({'width': 1584, 'height': 1000})
    for section in ('innovations', 'rewards', 'meeting-draw'):
        management_render = render.replace("'/innovation/'", repr('/innovation/manage?desktop=1&section=' + section)).replace("render_template('index.html')", "render_template('manage.html', is_committee_member=False, feishu_user_name='测试人员', feishu_user_id='test-user')")
        html = subprocess.check_output(['/opt/web/bin/python', '-c', management_render]).decode()
        page.goto('http://preview.local/innovation/manage?desktop=1&section=' + section, wait_until='networkidle', timeout=90000)
        assert page.locator('#' + section).is_visible()
        assert page.locator('.tab-pane.active').count() == 1
        assert page.locator('#manageTabs').count() == 0
        assert page.locator('.innovation-nav-item[aria-current="page"]').count() == 1
        if section == 'meeting-draw':
            assert page.locator('.meeting-draw-card').count() == 2
            assert page.locator('#meeting-draw .alert-danger').count() == 0
            page.screenshot(path='/qa/innovation-meeting-sidebar.png', full_page=True)
    assert not errors, errors
    print('Browser checks passed: charts, real API response structure, text escaping, active navigation, mobile menu, no overflow or JS errors.')
    for tab in ('excellent', 'share', 'talk'):
        star_render = render.replace("'/innovation/'", repr('/innovation/excellent_cases?tab=' + tab)).replace("render_template('index.html')", "render_template('excellent_cases.html', cases=[], total_count=0, leaderboard=[], star_share_items=[], star_talk_items=[], can_add_star_content=False, can_manage_proposal_notes=False)")
        html = subprocess.check_output(['/opt/web/bin/python', '-c', star_render]).decode()
        page.goto('http://preview.local/innovation/excellent_cases?tab=' + tab, wait_until='networkidle', timeout=90000)
        assert page.locator('#tab-' + tab).is_visible()
        assert page.locator('.tab-panel.active').count() == 1
        assert page.locator('.innovation-tabs').count() == 0
        assert page.locator('.innovation-star-link[aria-current="page"]').get_attribute('data-star-section') == tab
        for link in page.locator('.innovation-star-link').all():
            assert link.is_visible()
    page.screenshot(path='/qa/innovation-star-sidebar.png', full_page=True)
    assert not errors, errors
    print('Star submenu checks passed for all four sections.')
    browser.close()
