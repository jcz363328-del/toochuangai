from pathlib import Path
import json
from playwright.sync_api import sync_playwright
html=Path('/tmp/replenishment-ui-check.html').read_text()
with sync_playwright() as p:
 browser=p.chromium.launch(args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':900})
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  if '/mock/' in r.request.url:
   assert r.request.method != 'GET', 'Page must not fetch recommendations separately'
   r.fulfill(json={'success':True,'added':1,'skipped':0})
  else:r.fulfill(body=html,content_type='text/html')
 page.route('**/*',route)
 page.goto('http://replenishment.test/')
 sea=page.locator('#seaRecommendation')
 page.locator('#seaRecommendationCount').filter(has_text='1').wait_for()
 assert sea.evaluate('(e)=>e.tagName')=='BUTTON'
 assert not page.locator('#seaRecommendationView').is_visible()
 assert not page.locator('#seaRecommendationList').is_visible()
 assert page.locator('#seaRecommendationList').evaluate('(e)=>!e.closest("aside")')
 sea.click()
 assert page.locator('#seaRecommendationView').is_visible()
 assert not page.locator('#replenishmentView').is_visible()
 assert not page.locator('#stats').is_visible()
 page.locator('#seaRecommendationList input').check()
 assert page.locator('#seaRecommendationAdd').is_enabled()
 page.locator('[data-quick="all"]').click()
 assert not page.locator('#seaRecommendationView').is_visible()
 assert page.locator('#replenishmentView').is_visible()
 sea.click()
 assert page.locator('#seaRecommendationList input').is_checked()
 page.locator('[data-name="日常补货"]').click()
 assert page.locator('#replenishmentView').is_visible()
 grid=page.locator('#grid tbody tr')
 assert grid.count()==8,grid.count()
 page.locator('[data-filter="1"]').click()
 page.locator('#pop input[value="5"]').check()
 assert grid.count()==8
 page.locator('#pop [data-apply]').click()
 assert grid.count()==1,grid.count()
 page.locator('[data-filter="1"]').click()
 page.locator('#pop .filter-all').check()
 assert grid.count()==1
 page.locator('#pop [data-apply]').click()
 assert grid.count()==8
 page.locator('[data-filter="1"]').click()
 page.locator('#pop input[value="6"]').check()
 page.keyboard.press('Escape')
 assert grid.count()==8
 page.set_viewport_size({'width':900,'height':500})
 page.locator('[data-filter="1"]').click()
 pop=page.locator('#pop').bounding_box()
 foot=page.locator('#pop .pop-foot').bounding_box()
 assert pop['y']>=0 and pop['y']+pop['height']<=500,pop
 assert foot['y']+foot['height']<=500,foot
 page.screenshot(path='/tmp/replenishment-ui-check.png')
 assert not errors,errors
 print('PASS: sea directory opens main-panel details and navigation restores table, draft selection, apply/reset, cancel, viewport and footer; no JS errors')
 browser.close()
