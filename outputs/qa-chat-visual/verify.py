from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'qa-browser-deps'))
from playwright.sync_api import sync_playwright
root=Path(__file__).parent
with sync_playwright() as p:
 b=p.chromium.launch()
 page=b.new_page(viewport={'width':1586,'height':1000},device_scale_factor=1)
 page.goto('http://127.0.0.1:18603?sample=1')
 page.locator('.qa-page-title').wait_for()
 page.locator('[data-testid="stChatMessage"]').first.wait_for()
 page.wait_for_timeout(1200)
 assert page.locator('[data-testid="stException"]').count()==0
 page.screenshot(path=str(root/'conversation.png'),full_page=True)
 frame=page.frame_locator('iframe').first
 frame.locator('img.zoom-thumb').click()
 assert page.locator('#lashforge-fullscreen-viewer').is_visible()
 page.locator('#lashforge-fullscreen-close').click()
 assert not page.locator('#lashforge-fullscreen-viewer').is_visible()
 page.locator('[data-testid="stChatInputFileUploadButton"] input').set_input_files(str(root/'sample.png'))
 page.locator('textarea').fill('边缘再淡一点，整体更简洁。')
 page.screenshot(path=str(root/'with-attachment.png'),full_page=True)
 for width,height in [(2012,1248),(1440,900),(390,844)]:
  page.set_viewport_size({'width':width,'height':height})
  page.wait_for_timeout(300)
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(width,'horizontal overflow')
  assert page.locator('textarea').bounding_box()['height'] < 100
  if width>800:
   nav=page.locator('.st-key-qa_chat_nav').bounding_box()
   assert 230 < nav['width'] < 250,nav
   assert nav['height'] > height*0.75,nav
   composer=page.locator('.st-key-qa_chat_composer').bounding_box()
   assert composer['y']+composer['height'] <=height+20,composer
  page.screenshot(path=str(root/f'viewport-{width}.png'),full_page=True)
 print('PASS: conversation, preview open/close, reference attachment, 2012/1440/390 layout, compact input, no overflow')
 b.close()
