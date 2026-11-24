from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'qa-browser-deps'))
from playwright.sync_api import sync_playwright
root=Path(__file__).parent
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1586,'height':1000},device_scale_factor=1)
    page.goto('http://127.0.0.1:18603')
    page.locator('.qa-page-title').wait_for()
    page.wait_for_timeout(1500)
    page.screenshot(path=str(root/'empty.png'),full_page=True)
    print(json.dumps(page.evaluate('''() => Object.fromEntries(['.st-key-qa_chat_layout','.st-key-qa_chat_nav','.st-key-qa_chat_main','.st-key-qa_chat_messages','.st-key-qa_chat_composer','textarea'].map(s=>{const e=document.querySelector(s);return [s,e?{rect:e.getBoundingClientRect().toJSON(),css: {height:getComputedStyle(e).height,minHeight:getComputedStyle(e).minHeight},parent:e.parentElement.outerHTML.slice(0,700)}:null]}))'''),ensure_ascii=False))
    print('errors',page.locator('[data-testid="stException"]').all_text_contents())
    browser.close()
