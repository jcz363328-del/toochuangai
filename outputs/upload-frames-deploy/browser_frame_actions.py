from pathlib import Path
import sys,os,base64,io,json
sys.path.insert(0,str(Path('outputs/qa-browser-deps').resolve()))
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(Path('outputs/qa-browser-binaries').resolve())
from PIL import Image
from playwright.sync_api import sync_playwright
out=Path('outputs/upload-frames-deploy')
def data(color):
 b=io.BytesIO();Image.new('RGB',(1800,2400),color).save(b,format='PNG');return base64.b64encode(b.getvalue()).decode()
def transfer(page,names):
 return page.evaluate_handle('''files=>{const dt=new DataTransfer();for(const f of files)dt.items.add(new File([Uint8Array.from(atob(f.data),c=>c.charCodeAt(0))],f.name,{type:'image/png'}));return dt;}''',[{'name':n,'data':data(c)} for n,c in names])

with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1080},accept_downloads=True)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:18611/?kind=actual&feature=product_retouch')
 first=page.locator('[data-testid=stFileUploaderDropzone]:visible').first
 with page.expect_file_chooser() as chooser:first.click()
 chooser.value.set_files([])
 first.dispatch_event('drop',{'dataTransfer':transfer(page,[('original.png','red')])})
 page.locator('.upload-frame-meta').first.wait_for(state='attached',timeout=5000)
 page.wait_for_function('window.__xiaohaFrameActionsV2===true')
 assert page.get_by_role('button',name='放大查看',exact=True).count()==0
 choosers=[];page.on('filechooser',lambda c:choosers.append(c))
 first=page.locator('[data-testid=stFileUploaderDropzone]:visible').first
 page.wait_for_timeout(400)
 first.click()
 dialog=page.get_by_role('dialog',name='图片放大预览')
 dialog.wait_for(timeout=5000)
 page.wait_for_function('document.querySelector(".xiaoha-image-dialog img").naturalWidth===1800')
 assert not choosers,'clicking uploaded image must not open chooser'
 assert dialog.locator('img').get_attribute('src') == 'data:image/png;base64,'+data('red')
 page.screenshot(path=str(out/'click-enlarged.png'),full_page=True)
 page.keyboard.press('Escape')
 assert dialog.count()==0
 first.click(button='right')
 menu=page.locator('.xiaoha-image-menu');menu.wait_for()
 assert menu.get_by_role('button').count()==4
 with page.expect_download() as download:
  menu.get_by_role('button',name='下载原图',exact=True).click()
 download.value.save_as(str(out/'download-original.png'))
 assert (out/'download-original.png').read_bytes()==base64.b64decode(data('red'))
 first.click(button='right')
 with page.expect_file_chooser() as replacement_chooser:
  page.locator('.xiaoha-image-menu').get_by_role('button',name='更换图片',exact=True).click()
 replacement_chooser.value.set_files([])
 # Native drag/drop and clipboard still replace the selected frame.
 first.hover()
 page.evaluate('dt=>document.dispatchEvent(new ClipboardEvent("paste",{clipboardData:dt,bubbles:true,cancelable:true}))',transfer(page,[('new.png','blue')]))
 page.wait_for_function('(src)=>document.querySelector(".upload-frame-meta").dataset.source===src',arg='data:image/png;base64,'+data('blue'))
 first.click()
 page.get_by_role('dialog').wait_for()
 assert page.get_by_role('dialog').locator('img').get_attribute('src')=='data:image/png;base64,'+data('blue')
 page.get_by_role('dialog').get_by_role('button',name='关闭',exact=True).click()
 first.click(button='right')
 page.locator('.xiaoha-image-menu').get_by_role('button',name='移除图片',exact=True).click()
 page.wait_for_function('document.querySelectorAll(".upload-frame-meta").length===0')
 assert not errors,errors
 print('PASS product retouch: empty click selects; uploaded click enlarges; right-click menu downloads original bytes and opens replacement chooser; Ctrl+V replacement and zoom use new image; ESC/close work')
 browser.close()
