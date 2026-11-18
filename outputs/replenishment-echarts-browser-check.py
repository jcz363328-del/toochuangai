from pathlib import Path
from playwright.sync_api import sync_playwright
html=Path('/tmp/replenishment-ui-check.html').read_text()
with sync_playwright() as p:
 browser=p.chromium.launch(args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1920,'height':1080})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  if r.request.url.endswith('echarts.min.js'):r.fulfill(path='/tmp/echarts.min.js',content_type='text/javascript')
  else:
   assert '/mock/' not in r.request.url,'No data fetch expected'
   r.fulfill(body=html,content_type='text/html')
 page.route('**/*',route)
 page.goto('http://replenishment.test/')
 page.locator('.sales-spark canvas').first.wait_for()
 assert page.locator('.sales-spark').count()==8
 page.locator('.sales-spark').first.hover(position={'x':80,'y':20})
 tip=page.locator('.sales-echarts-tooltip').filter(visible=True)
 tip.wait_for()
 assert 'TEST-5' in tip.inner_text() and '2026-11-' in tip.inner_text() and '销量' in tip.inner_text(),tip.inner_text()
 page.screenshot(path='/tmp/echarts-inline-check.png')
 page.locator('.sales-spark').first.focus()
 page.keyboard.press('ArrowLeft')
 assert '2026-11-15' in tip.inner_text()
 page.locator('#grid tbody tr').first.click()
 page.locator('.trend-large canvas').wait_for()
 page.locator('.trend-large').hover(position={'x':100,'y':70})
 assert page.locator('.sales-echarts-tooltip').filter(visible=True).count()>=1
 page.locator('#dClose').click()
 page.locator('[data-filter="1"]').click()
 page.locator('#pop input[value="5"]').check()
 page.locator('#pop [data-apply]').click()
 page.locator('.sales-spark canvas').wait_for()
 assert page.locator('.sales-spark').count()==1
 assert not errors,errors
 print('PASS: ECharts hover date/value, keyboard point selection, expanded chart and filter rerender')
 browser.close()
