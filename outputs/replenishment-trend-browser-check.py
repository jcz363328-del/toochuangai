from pathlib import Path
from playwright.sync_api import sync_playwright
html=Path('/tmp/replenishment-ui-check.html').read_text()
with sync_playwright() as p:
 browser=p.chromium.launch(args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1920,'height':1080})
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('**/*',lambda r:r.fulfill(body=html,content_type='text/html'))
 page.goto('http://replenishment.test/')
 page.locator('.sales-spark').first.wait_for()
 assert page.locator('.sales-spark').count()==8
 assert page.locator('.sales-spark circle').count()==120
 assert page.locator('#grid thead th').count()==page.locator('#grid col').count()==22
 assert page.locator('#grid tbody tr').first.locator('td').count()==22
 assert '2026-11-16' in page.locator('.sales-spark > title').first.text_content()
 page.locator('#grid tbody tr').first.click()
 page.locator('[data-trend] svg').wait_for()
 assert '2026-11-02' in page.locator('[data-trend]').inner_html()
 page.screenshot(path='/tmp/replenishment-trend-check.png')
 assert not errors,errors
 print('PASS: 8 row charts, 15 points each, aligned columns, dates and snapshot-backed drawer')
 browser.close()
