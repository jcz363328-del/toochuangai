from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'qa-browser-deps'))
from playwright.sync_api import sync_playwright
root=Path(__file__).parent
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':1680,'height':1080},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto((root/'index.html').resolve().as_uri())
 assert page.locator('#rows tr').count()==8
 page.screenshot(path=str(root/'preview.png'),full_page=True)
 page.locator('[data-tab="issue"]').click();assert page.locator('#rows tr').count()==3
 page.locator('[data-detail="FBA18DEMO004"]').click();assert page.locator('#overlay.open').count()==1
 assert '数据库记录' in page.locator('#drawer').inner_text()
 page.screenshot(path=str(root/'detail-preview.png'),full_page=True)
 page.keyboard.press('Escape');page.locator('#reset').click();page.locator('#search').fill('80621');assert page.locator('#rows tr').count()==1
 page.locator('#reset').click();page.locator('#status').select_option('unmarked');assert page.locator('#rows tr').count()==3
 page.locator('#reset').click();page.locator('#allCheck').check();assert '8' in page.locator('#selection').inner_text()
 with page.expect_download() as d:page.locator('#export').click()
 assert d.value.suggested_filename.endswith('.csv')
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 assert not errors,errors
 print('PASS: filters, counts, details, escape, search, status, selection, CSV export, mobile containment, no JS errors')
 b.close()
