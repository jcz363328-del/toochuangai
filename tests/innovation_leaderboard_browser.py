import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright


render = """
import sys
sys.path.insert(0, '/app/tests')
from test_innovation_sidebar import InnovationSidebarTests
from innovation.leaderboard import load_points_leaderboard
from flask import render_template
test = InnovationSidebarTests()
test.setUp()
leaders = load_points_leaderboard(lambda sql: [('测试成员' + str(number), 1000 - number * 35) for number in range(1, 21)])
with test.app.test_request_context('/innovation/leaderboard'):
    print(render_template('leaderboard.html', leaders=leaders, leaderboard_error=False))
"""
html = subprocess.check_output(['/opt/web/bin/python', '-c', render]).decode()
with sync_playwright() as runtime:
    browser = runtime.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1584, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))

    def respond(route):
        path = route.request.url.split('preview.local', 1)[1].split('?', 1)[0]
        if path.startswith('/innovation/static/'):
            route.fulfill(path=str(Path('/app/innovation/static') / path.removeprefix('/innovation/static/')))
        else:
            route.fulfill(content_type='text/html', body=html)

    page.route('http://preview.local/**', respond)
    page.goto('http://preview.local/innovation/leaderboard', wait_until='networkidle', timeout=90000)
    assert page.locator('.leaderboard-row').count() == 20
    assert page.locator('.leaderboard-tier').count() == 0
    assert page.locator('.leaderboard-honor').count() == 3
    for index, name in enumerate(('first', 'second', 'third')):
        icon = page.locator('.leaderboard-rank-icon').nth(index)
        assert icon.get_attribute('src').endswith('/' + name + '.png')
        assert icon.evaluate('(image) => image.complete && image.naturalWidth > 0')
        assert icon.evaluate('(image) => getComputedStyle(image).objectFit') == 'contain'
    assert page.locator('.innovation-nav-item[aria-current="page"]').inner_text() == '创新星榜'
    assert page.locator('.innovation-nav-group h2').all_text_contents() == ['工作台', '提案协作', '创新星主场', '积分与激励']
    for link in page.locator('.innovation-star-link').all():
        assert link.is_visible()
    assert page.locator('.innovation-nav-group').last.locator('a').all_text_contents()[-1].strip() == '奖品管理'
    assert page.locator('.innovation-shell').evaluate('(element) => getComputedStyle(element).paddingTop') == '8px'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path='/qa/innovation-leaderboard-desktop.png', full_page=True)
    page.emulate_media(reduced_motion='reduce')
    assert page.locator('.leaderboard-honor').first.evaluate('(element) => getComputedStyle(element, "::after").animationName') == 'none'
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path='/qa/innovation-leaderboard-mobile.png', full_page=True)
    assert not errors, errors
    browser.close()
    print('Leaderboard browser checks passed: twenty rows, podium, sidebar grouping, compact margins, responsive layout and reduced motion.')
