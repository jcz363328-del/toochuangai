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
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:18611/?kind=actual&feature=hd_batch')
 zone=page.locator('[data-testid=stFileUploaderDropzone]:visible').first
 zone.dispatch_event('drop',{'dataTransfer':transfer(page,[('batch-source.png','red')])})
 page.wait_for_function('document.querySelectorAll("[data-testid=stFileUploaderDropzone]").length>=2')
 page.wait_for_function('getComputedStyle(document.querySelector("[data-testid=stFileUploaderDropzone]")).backgroundImage.startsWith("url(")')
 assert page.get_by_role('button',name='图片操作',exact=True).count()==0
 first=page.locator('[data-testid=stFileUploaderDropzone]:visible').first
 assert first.bounding_box()['height']>=290
 first.hover()
 page.evaluate('dt=>document.dispatchEvent(new ClipboardEvent("paste",{clipboardData:dt,bubbles:true,cancelable:true}))',transfer(page,[('replaced.png','blue')]))
 page.wait_for_timeout(300)
 assert page.locator('[data-testid=stException]').count()==0,page.locator('body').inner_text()[-1500:]
 page.screenshot(path=str(out/'batch-hd-frames.png'),full_page=True)
 for width in [1440,1024,390]:
  page.set_viewport_size({'width':width,'height':1080})
  page.wait_for_timeout(100)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
 assert not errors,errors
 print('PASS actual batch HD: existing image is a direct paste/replace frame, no image-actions menu, desktop/mobile no overflow')
 browser.close()
