from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'qa-browser-deps'))
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1000})
 page.goto('http://127.0.0.1:8000/lashforge/?feature=ai_qa_image')
 sidebar=page.locator('[data-testid=stSidebar]');sidebar.wait_for()
 group=sidebar.locator('[data-testid=stExpander]').filter(has=page.locator('summary',has_text='图片处理'))
 group.locator('summary').click()
 group.locator('button').first.wait_for(state='visible')
 positions=group.locator('button p').evaluate_all('''es=>es.map(e=>{let r=document.createRange();r.selectNodeContents(e);return {text:e.textContent,x:r.getBoundingClientRect().x,align:getComputedStyle(e).textAlign}})''')
 assert len(positions)>3,positions
 assert max(i['x'] for i in positions)-min(i['x'] for i in positions)<2,positions
 assert all(i['align']=='left' for i in positions),positions
 sidebar.screenshot(path=str(Path(__file__).parent/'sidebar-left-aligned.png'))
 print(json.dumps(positions,ensure_ascii=False));b.close()
