import base64
import json
import os
from pathlib import Path
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, 'Playwright browser runtime required')
class PriorityDragBrowserTests(unittest.TestCase):
    def test_real_pointer_drag_and_refreshed_indices(self):
        script = Path(os.environ.get('UPLOAD_SORT_JS', str(Path(__file__).resolve().parents[1] / 'Department/视觉设计部/xiaoha' / 'upload_priority_sort.js'))).read_text(encoding='utf-8').replace('__UPLOAD_REORDER_QUERY_KEY__', 'reorder_upload')
        html = '''<style>.card{position:relative;display:inline-block;width:180px;height:200px;margin:10px;background:pink}.upload-sort-grip{position:absolute;top:5px;left:5px;padding:10px;cursor:grab}.upload-sort-drop-zone{position:fixed}</style>'''
        for i in range(3):
            html += f'<div class="card" data-testid="stVerticalBlock"><div class="upload-preview-root" data-upload-sortable="true" data-upload-widget="test" data-upload-index="{i}"></div><p>image {i}</p></div>'
        html += '<iframe srcdoc=""></iframe>'
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()
            page.route('http://sort.test/**', lambda route: route.fulfill(body=html, content_type='text/html'))
            page.goto('http://sort.test/')
            frame = page.frames[1]
            frame.evaluate(script)
            frame.evaluate(script)  # Streamlit reruns must not duplicate handlers.
            self.assertEqual(page.locator('.upload-sort-grip').count(), 3)
            source = page.locator('.upload-sort-grip').nth(0).bounding_box()
            target = page.locator('.card').nth(2).bounding_box()
            x, y = source['x'] + 10, source['y'] + 10
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 1, y + 1)
            page.mouse.up()
            self.assertNotIn('reorder_upload', page.url)
            # A DOM update must refresh the source index on an existing grip.
            page.locator('.upload-preview-root').nth(0).evaluate("el => el.dataset.uploadIndex = '1'")
            page.wait_for_function("document.querySelector('.upload-sort-grip').dataset.index === '1'")
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(target['x'] + 80, target['y'] + 90, steps=12)
            page.mouse.up()
            page.wait_for_url('**/*reorder_upload=*')
            from urllib.parse import urlparse, parse_qs
            token = parse_qs(urlparse(page.url).query)['reorder_upload'][0]
            payload = json.loads(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)))
            self.assertEqual(payload, {'widget_key': 'test', 'source_index': 1, 'target_index': 2})
            browser.close()


if __name__ == '__main__':
    unittest.main()
