import sys,json
from pathlib import Path
FOLDER=Path(__file__).resolve().parent
ROOT=FOLDER.parents[1]
sys.path.insert(0,str(ROOT/'outputs/qa-browser-deps'))
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=str(next((ROOT/'outputs/qa-browser-binaries/chromium-1255').rglob('chrome.exe'))),headless=True)
    page=browser.new_page(viewport={'width':1500,'height':1100},accept_downloads=True)
    page.set_default_timeout(5000)
    page.on('pageerror',lambda e:print('PAGE ERROR',e,flush=True))
    page.on('console',lambda msg:print('CONSOLE',msg.type,msg.text[:250],flush=True))
    page.goto('http://127.0.0.1:18580/',wait_until='networkidle')
    page.get_by_role('button',name='打开历史记录',exact=True).click()
    dialog=page.locator('[role="dialog"]').first
    dialog.wait_for(state='attached')
    print('DIALOG META',page.evaluate('()=>[...document.querySelectorAll("dialog,[role=dialog]")].map(d=>({tag:d.tagName,html:d.outerHTML.slice(0,800),rect:d.getBoundingClientRect().toJSON(),inert:d.inert,iframes:[...d.querySelectorAll("iframe")].map(f=>({rect:f.getBoundingClientRect().toJSON(),title:f.title}))}))'),flush=True)
    try:
        dialog.locator('iframe').first.content_frame.locator('.zoom-thumb').click()
        print('CLICKED',flush=True)
        print('OVERLAY',page.evaluate('()=>{let d=document.querySelector("#lashforge-fullscreen-viewer");return {parent:d.parentElement.outerHTML.slice(0,500),html:d.outerHTML.slice(0,500),rect:d.getBoundingClientRect().toJSON(),ancestors:[...function*(n){while(n){yield {tag:n.tagName,id:n.id,inert:n.inert,aria:n.getAttribute("aria-hidden")};n=n.parentElement;}}(d)],dialogs:[...document.querySelectorAll("dialog")].map(n=>({open:n.open,html:n.outerHTML.slice(0,400)}))}}'),flush=True)
        page.locator('#lashforge-fullscreen-download').click()
        print('DOWNLOAD CLICKED',flush=True)
    finally:
        page.screenshot(path=str(FOLDER/'inspect167.png'))
        print('SAVED',flush=True)
        browser.close()
