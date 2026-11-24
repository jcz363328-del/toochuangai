import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'outputs/qa-browser-deps'))
from playwright.sync_api import sync_playwright
from jinja2 import Template

html = Template((root / 'templates/operation_fba_shipping_methods.html').read_text(encoding='utf-8')).render(
    back_url='/', source_name='运营部门', user_name='预览',
    url_for=lambda *args, **kwargs: '/static/js/fba_shipping.js?v=' + kwargs['v'])
record = dict(key='1', id='FBA-DEMO-001', shop='4', ship='海运-1', log='LOG-001',
    tracking='', ien='', codes=[], filled=False, status='', issues=['海运追踪码缺失'],
    n=None, parsed_count=0, check='', date='2026-11-19 09:20:31', package='')
payload = dict(success=True, data=dict(records=[record, dict(record, key='2', id='FBA-DEMO-002')],
    page=1, total_pages=1, total=2, loaded_at='2026-11-19 19:08:04',
    stats=dict(total=2, filled=0, issues=2, checked=0, unchecked=2)))

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=str(next((root / 'outputs/qa-browser-binaries/chromium-1255').rglob('chrome.exe'))), headless=True)
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def respond(route):
        path = urlsplit(route.request.url).path
        if path.endswith('/shops'):
            route.fulfill(json=dict(success=True, data=dict(shops=['4'], shipping_methods=['海运-1'])))
        elif path.startswith('/api/'):
            route.fulfill(json=payload)
        elif path.endswith('.js'):
            route.fulfill(content_type='application/javascript', body=(root / 'static/js/fba_shipping.js').read_text(encoding='utf-8'))
        else:
            route.fulfill(content_type='text/html', body=html)
    page.route('**/*', respond)
    for width in (2373, 1440, 390):
        page.set_viewport_size(dict(width=width, height=1000))
        page.goto('http://fba.test/')
        page.locator('tr[data-row-detail]').first.wait_for()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'page overflow: {width}'
        bounds = page.locator('.panel').bounding_box()
        assert bounds['x'] <= 40 and width - bounds['x'] - bounds['width'] <= 41, bounds
        row = page.locator('tr[data-row-detail]').first
        row.locator('td').nth(1).click()
        assert page.locator('#overlay').get_attribute('aria-hidden') == 'false'
        assert page.locator('#drawer h2').inner_text() == record['id']
        page.locator('#close').click()
        row.locator('.rowcheck').check()
        assert page.locator('#overlay').get_attribute('aria-hidden') == 'true'
        assert '1 条' in page.locator('#selection').inner_text()
        row.focus()
        page.keyboard.press('Enter')
        assert page.locator('#overlay').get_attribute('aria-hidden') == 'false'
        page.keyboard.press('Escape')
        assert row.evaluate('(el) => el === document.activeElement')
        page.locator('.table-wrap').evaluate('(el) => { el.scrollLeft = 0; }')
        page.screenshot(path=str(Path(__file__).parent / f'preview-{width}.png'), full_page=True)
        print(f'{width}px: layout, row detail, checkbox, keyboard and focus passed')
    assert not errors, errors
    browser.close()
