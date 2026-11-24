from pathlib import Path
import sys, os, base64, io
sys.path.insert(0,str(Path('outputs/qa-browser-deps').resolve()))
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(Path('outputs/qa-browser-binaries').resolve())
from playwright.sync_api import sync_playwright
from PIL import Image
out=Path('outputs/poster-fusion-drop')
def png(color):
    b=io.BytesIO();Image.new('RGB',(160,240),color).save(b,format='PNG');return base64.b64encode(b.getvalue()).decode()
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1600,'height':1000})
    page.goto('http://127.0.0.1:18609')
    zones=page.locator('[data-testid="stFileUploaderDropzone"]')
    zones.first.wait_for()
    page.wait_for_function('document.querySelectorAll("[data-testid=stFileUploaderDropzone]").length===4')
    assert all(zones.nth(i).bounding_box()['height']>=300 for i in range(4))
    page.screenshot(path=str(out/'empty.png'),full_page=True)
    # Actual DOM drag/drop events exercise Streamlit's native uploader listeners.
    for i,color in enumerate(['red','green','blue','yellow']):
        transfer=page.evaluate_handle('''({data,name})=>{const dt=new DataTransfer();const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));dt.items.add(new File([bytes],name,{type:'image/png'}));return dt;}''',{'data':png(color),'name':f'{i}.png'})
        zones.nth(i).dispatch_event('drop',{'dataTransfer':transfer})
        page.wait_for_function('(i)=>getComputedStyle(document.querySelectorAll("[data-testid=stFileUploaderDropzone]")[i]).backgroundImage.startsWith("url(")',arg=i)
    button=page.get_by_role('button',name='生成融合海报',exact=True)
    assert button.is_enabled()
    old=zones.nth(2).evaluate('(e)=>getComputedStyle(e).backgroundImage')
    zones.nth(2).hover()
    page.evaluate('''data=>{const dt=new DataTransfer();const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));dt.items.add(new File([bytes],'pasted.png',{type:'image/png'}));document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));}''',png('purple'))
    page.wait_for_function('(old)=>getComputedStyle(document.querySelectorAll("[data-testid=stFileUploaderDropzone]")[2]).backgroundImage!==old',arg=old)
    assert button.is_enabled()
    page.wait_for_timeout(600)
    assert page.locator('[data-testid=stFileChip]:visible').count() == 0
    assert page.locator('[data-testid=stFileChips]:visible').count() == 0
    page.screenshot(path=str(out/'filled.png'),full_page=True)
    for width in (1920,1600,1366,1024,768):
        page.set_viewport_size({'width':width,'height':1000})
        page.wait_for_timeout(100)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'overflow at {width}'
        for index in range(4):
            rect = zones.nth(index).bounding_box()
            assert rect['x'] >= 0 and rect['x'] + rect['width'] <= width, (width,index,rect)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(out/'mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('[data-testid="stException"]').count()==0
    print('PASS: 4 image frames, native drop upload, correct-slot clipboard replacement, mobile overflow, no page exceptions')
    browser.close()
