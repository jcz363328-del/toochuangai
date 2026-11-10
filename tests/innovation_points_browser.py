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
with test.app.test_request_context('/innovation/points'):
    print(render_template('points.html', feishu_user_name='测试人员'))
"""
html = subprocess.check_output(['/opt/web/bin/python', '-c', render]).decode()
rewards = [{'id': number, 'name': label, 'image_path': f'/test-reward-{number}.svg', 'points_required': 10, 'stock': 1} for number, label in [(1, '横向图片'), (2, '竖向图片')]]
with sync_playwright() as runtime:
    browser = runtime.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1584, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.dismiss())

    def respond(route):
        path = route.request.url.split('preview.local', 1)[1].split('?', 1)[0]
        if path.startswith('/innovation/api/'):
            payload = {'success': True, 'data': {'records': [], 'current_points': 100, 'annual_points': 100, 'total_earned_points': 100}}
            if path.endswith('get_rewards'):
                payload['data'] = {'rewards': rewards}
            route.fulfill(content_type='application/json', body=json.dumps(payload))
        elif path.startswith('/test-reward-'):
            width, height = (800, 200) if path.endswith('1.svg') else (200, 800)
            route.fulfill(content_type='image/svg+xml', body=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="#dce7ff"/><rect x="2" y="2" width="{width-4}" height="{height-4}" fill="none" stroke="#4664df" stroke-width="4"/></svg>')
        elif path.startswith('/innovation/static/'):
            route.fulfill(path=str(Path('/app/innovation/static') / path.removeprefix('/innovation/static/')))
        else:
            route.fulfill(content_type='text/html', body=html)

    page.route('http://preview.local/**', respond)
    page.goto('http://preview.local/innovation/points', wait_until='networkidle', timeout=90000)
    page.wait_for_function("document.querySelectorAll('.reward-image-container img').length === 2")
    for image in page.locator('.reward-image-container img').all():
        assert image.evaluate('(image) => image.complete && image.naturalWidth > 0')
        assert image.evaluate('(image) => getComputedStyle(image).objectFit') == 'contain'
        assert image.bounding_box()['height'] >= 180
    assert page.locator('h3').filter(has_text='积分中心').count() == 0
    assert page.locator('#current-points').bounding_box()['y'] < 200
    page.screenshot(path='/qa/innovation-points-desktop.png', full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path='/qa/innovation-points-mobile.png', full_page=True)
    assert not errors, errors
    browser.close()
    print('Points browser checks passed: content moves up, landscape/portrait images use contain, mobile has no overflow; no exchange executed.')
