from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'qa-browser-deps'))
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch();pg=b.new_page(viewport={'width':1586,'height':1000});pg.goto('http://127.0.0.1:18603?sample=1');pg.locator('.qa-page-title').wait_for();pg.wait_for_timeout(500)
 print(json.dumps(pg.evaluate('''() => {let e=document.querySelector('.st-key-qa_chat_nav');let out=[];for(let ss of document.styleSheets){try{for(let r of ss.cssRules){if(r.selectorText && e.matches(r.selectorText) && (r.style.height || r.style.minHeight))out.push(r.cssText)}}catch{}}return {innerHeight, rules:out,chat:document.querySelector('[data-testid=stChatMessage]')?.outerHTML.slice(0,5000),iframes:[...document.querySelectorAll('iframe')].map(e=>e.outerHTML.slice(0,400))}}'''),ensure_ascii=False))
 b.close()

