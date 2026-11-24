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
 for kind in ['single','multi','refs','compact','hero','materials','poster','actual']:
  page.goto('http://127.0.0.1:18611/?kind='+kind)
  zones=page.locator('[data-testid=stFileUploaderDropzone]:visible')
  zones.first.wait_for()
  assert all(zones.nth(i).bounding_box()['height']>=190 for i in range(zones.count())),kind
  if kind in ['single','compact','hero','refs']:
   zones.first.dispatch_event('drop',{'dataTransfer':transfer(page,[('first.png','red')])})
   page.get_by_text('first.png',exact=False).first.wait_for(state='attached')
   page.wait_for_function('getComputedStyle(document.querySelector("[data-testid=stFileUploaderDropzone]")).backgroundImage.startsWith("url(")')
   zones.first.hover()
   clip=transfer(page,[('replacement.png','blue')])
   page.evaluate('dt=>document.dispatchEvent(new ClipboardEvent("paste",{clipboardData:dt,bubbles:true,cancelable:true}))',clip)
   page.get_by_text('replacement.png',exact=False).first.wait_for(state='attached')
  elif kind in ['multi','materials']:
   zones.first.dispatch_event('drop',{'dataTransfer':transfer(page,[('one.png','red'),('two.png','green')])})
   page.get_by_text('two.png',exact=False).first.wait_for(state='attached')
   page.wait_for_timeout(200)
   assert page.locator('[data-testid=stException]').count()==0,page.locator('body').inner_text()[-1200:]
   zones=page.locator('[data-testid=stFileUploaderDropzone]:visible')
   zones.last.dispatch_event('drop',{'dataTransfer':transfer(page,[('three.png','blue'),('four.png','yellow')])})
   page.get_by_text('three.png',exact=False).first.wait_for(state='attached')
   if kind=='multi':
    page.wait_for_timeout(250)
    text=page.locator('[data-testid=stJson]').inner_text()
    assert 'four.png' not in text,text
  page.wait_for_timeout(250)
  assert page.locator('[data-testid=stFileChip]:visible').count()==0,kind
  assert page.locator('[data-testid=stException]').count()==0,page.locator('body').inner_text()[-1200:]
  for width in [1440,1024,390]:
   page.set_viewport_size({'width':width,'height':1080})
   page.wait_for_timeout(100)
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(kind,width)
  page.set_viewport_size({'width':1440,'height':1080})
  page.screenshot(path=str(out/(kind+'.png')),full_page=True)
  print('PASS',kind,flush=True)
 assert not errors,errors
 browser.close()
