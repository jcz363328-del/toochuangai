from pathlib import Path
import sys,os,base64,io,json
sys.path.insert(0,str(Path('outputs/qa-browser-deps').resolve()))
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(Path('outputs/qa-browser-binaries').resolve())
from PIL import Image
from playwright.sync_api import sync_playwright
out=Path('outputs/upload-frames-deploy')
def data(color):
 b=io.BytesIO();Image.new('RGB',(160,240),color).save(b,format='PNG');return base64.b64encode(b.getvalue()).decode()
def transfer(page,names):
 return page.evaluate_handle('''files=>{const dt=new DataTransfer();for(const f of files)dt.items.add(new File([Uint8Array.from(atob(f.data),c=>c.charCodeAt(0))],f.name,{type:'image/png'}));return dt;}''',[{'name':n,'data':data(c)} for n,c in names])

with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1080})
 page.goto('http://127.0.0.1:18611/?kind=multi')
 page.locator('[data-testid=stFileUploaderDropzone]:visible').first.dispatch_event('drop',{'dataTransfer':transfer(page,[('one.png','red'),('two.png','green'),('three.png','blue')])})
 page.wait_for_function('document.querySelectorAll("[data-testid=stFileUploaderDropzone]").length>=4')
 assert page.get_by_role('button',name='图片操作',exact=True).count()==0
 page.locator('[data-testid=stFileUploaderDropzone]:visible').first.dispatch_event('drop',{'dataTransfer':transfer(page,[('replacement.png','purple')])})
 page.wait_for_function('document.querySelector("[data-testid=stJson]").textContent.includes("replacement.png")')
 page.get_by_role('button',name='后移 →',exact=True).first.click()
 page.wait_for_function('document.querySelector("[data-testid=stJson]").textContent.indexOf("two.png") < document.querySelector("[data-testid=stJson]").textContent.indexOf("replacement.png")')
 page.get_by_role('button',name='移除',exact=True).first.click()
 page.wait_for_function('!document.querySelector("[data-testid=stJson]").textContent.includes("two.png")')
 page.get_by_role('button',name='清空上传',exact=True).click()
 page.wait_for_function('!document.querySelector("[data-testid=stJson]").textContent.includes("replacement.png")')
 assert page.locator('[data-testid=stFileUploaderDropzone]:visible').count()==1
 print('PASS multi reorder, per-image removal and clear; image frame remains ready for new uploads')
 browser.close()
