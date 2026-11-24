from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'qa-browser-deps'))
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch();pg=b.new_page(viewport={'width':1586,'height':1000})
 pg.goto('http://127.0.0.1:8000/lashforge/?feature=ai_qa_image')
 pg.wait_for_timeout(3000)
 print('chat available:',pg.locator('.qa-page-title').count(),'exception:',pg.locator('[data-testid="stException"]').count())
 if pg.locator('.qa-page-title').count():
  pg.screenshot(path=str(Path(__file__).parent/'production-expanded.png'),full_page=True)
  main=pg.locator('.st-key-qa_chat_main').bounding_box()
  composer=pg.locator('.st-key-qa_chat_composer').bounding_box()
  assert composer['x'] >= main['x'], (main,composer)
  collapse=pg.locator('[data-testid=stSidebarCollapseButton]')
  if collapse.count():
   collapse.click()
   pg.wait_for_timeout(500)
  pg.screenshot(path=str(Path(__file__).parent/'production.png'),full_page=True)
 b.close()

