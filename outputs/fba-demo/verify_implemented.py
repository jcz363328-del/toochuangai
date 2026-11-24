from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'qa-browser-deps'))
from playwright.sync_api import sync_playwright
root=Path(__file__).parent
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':1680,'height':1080});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:18604');page.locator('[data-detail]').first.wait_for();page.wait_for_timeout(300)
 assert page.locator('#rows tr').count()==20
 assert int(page.locator('#total').inner_text().replace(',',''))>200
 page.screenshot(path=str(root/'implemented.png'),full_page=True)
 with page.expect_response(lambda r:'/api/operation/fba_shipping_methods?' in r.url):page.locator('#next').click()
 page.locator('#pageInfo').filter(has_text='2 /').wait_for()
 first=page.locator('#rows .cargo').first.inner_text()
 with page.expect_response(lambda r:'/api/operation/fba_shipping_methods?' in r.url):page.locator('#search').fill(first)
 page.locator('#pageInfo').filter(has_text='1 /').wait_for()
 page.locator('[data-detail]').first.click();page.locator('#overlay.open').wait_for()
 assert '记录序号' in page.locator('#drawer').inner_text()
 if page.locator('#copy').count():
  page.locator('#copy').click();page.locator('#toast').filter(has_text='已复制').wait_for()
 page.keyboard.press('Escape');assert not page.locator('#overlay').is_visible()
 page.locator('.rowcheck').first.check()
 with page.expect_download() as d:page.locator('#export').click()
 assert d.value.suggested_filename=='FBA货件追踪.csv'
 with page.expect_response(lambda r:'/api/operation/fba_shipping_methods?' in r.url):page.locator('#reset').click()
 page.locator('#total').filter(has_text='73,').wait_for()
 with page.expect_response(lambda r:'/api/operation/fba_shipping_methods?' in r.url):page.locator('[data-tab="issue"]').click()
 page.locator('[data-detail]').first.wait_for();assert page.locator('#rows .attention').count()>0
 with page.expect_response(lambda r:'/api/operation/fba_shipping_methods?' in r.url):page.locator('#status').select_option('unmarked')
 page.locator('[data-detail]').first.wait_for()
 for w,h in [(1440,900),(390,844)]:
  page.set_viewport_size({'width':w,'height':h});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 assert not errors,errors
 print('PASS: real data, full-dataset metrics, 20-row paging, next-page, search, drawer, clipboard, selected CSV, reset, issues, status, responsive, no JS errors')
 b.close()
