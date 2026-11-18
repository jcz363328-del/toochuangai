from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 browser=p.chromium.launch(args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1920,'height':1080})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  if r.request.url.endswith('echarts.min.js'):r.fulfill(path='/tmp/echarts.min.js',content_type='text/javascript')
  else:r.fulfill(path='/tmp/replenishment-ui-check.html',content_type='text/html')
 page.route('**/*',route);page.goto('http://replenishment.test/')
 page.locator('.sku-status').first.wait_for()
 rows=page.locator('#grid tbody tr')
 assert '低库存' in rows.nth(0).locator('.sku-statuses').inner_text()
 assert rows.nth(0).locator('.sku-status:not(.more)').count()==2
 assert rows.nth(0).locator('.sku-status.more').count()==1
 assert '清货' in rows.nth(1).locator('.sku-statuses').inner_text()
 assert '待下单' in rows.nth(2).locator('.sku-statuses').inner_text()
 assert '断货' in rows.nth(3).locator('.sku-statuses').inner_text()
 assert page.locator('td.mark-low-stock').first.evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)'
 assert page.locator('td.mark-falling').first.evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)'
 field=page.locator('[data-qty-row="0"]');field.fill('15');field.press('Tab')
 assert '待下单' in rows.nth(0).locator('.sku-statuses').inner_text()
 assert 'dirty' in field.get_attribute('class')
 page.mouse.move(1900,50)
 page.screenshot(path='/tmp/replenishment-labels-check.png')
 assert not errors,errors
 print('PASS: risk/clearance/order labels, two-label cap, neutral cell colors, live edited quantity label')
 browser.close()
