from pathlib import Path
import sys, os
sys.path.insert(0,str(Path('outputs/qa-browser-deps').resolve()))
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(Path('outputs/qa-browser-binaries').resolve())
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1700,'height':1000})
 page.route('**/api/bootstrap-config*',lambda r:r.fulfill(status=200,json={'success':False}))
 page.on('pageerror',lambda e: print(str(e),flush=True))
 page.goto('http://127.0.0.1:18610/infinite-canvas/canvas?workspace=a_plus')
 page.wait_for_timeout(2000)
 page.screenshot(path='outputs/a-plus-canvas-deploy/probe.png')
 print(page.locator('body').inner_text()[:1400],flush=True)
 page.get_by_role('button',name='新建画布',exact=True).first.wait_for(timeout=5000)
 print(page.locator('body').inner_text()[:1400])
 page.get_by_role('button',name='新建画布',exact=True).first.click()
 page.get_by_role('button',name='功能模块',exact=True).click()
 page.screenshot(path='outputs/a-plus-canvas-deploy/nodes-menu.png')
 print(page.locator('body').inner_text()[-1500:])
 browser.close()
