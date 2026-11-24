import sys,hashlib,json
from pathlib import Path
FOLDER=Path(__file__).resolve().parent
ROOT=FOLDER.parents[1]
sys.path.insert(0,str(ROOT/'outputs/qa-browser-deps'))
from playwright.sync_api import sync_playwright
checks=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=str(next((ROOT/'outputs/qa-browser-binaries/chromium-1255').rglob('chrome.exe'))),headless=True)
    context=browser.new_context(accept_downloads=True,viewport={'width':1500,'height':1100})
    context.add_init_script('window.showSaveFilePicker = undefined;')
    page=context.new_page()
    page.on('pageerror',lambda e:print('PAGE ERROR',e,flush=True))
    page.on('dialog',lambda d:(print('DIALOG',d.message,flush=True),d.dismiss()))
    page.set_default_timeout(10000)
    page.goto('http://127.0.0.1:18580/',wait_until='networkidle')
    for frame_index,thumb_index,expected,label in [(0,1,'history/b/result.png','result second'),(1,0,'history/c/photo.jpg','data original'),(2,0,'history/a/result.png','remote original without CORS'),(3,0,'history/b/result.png','compare enlarged')]:
        print('START',label,flush=True)
        frame=page.locator('iframe').nth(frame_index).content_frame
        if frame_index==3:
            element=frame.locator('.compare-native-result')
            box=element.bounding_box()
            element.click(position={'x':box['width']*.75,'y':box['height']*.5})
        else: frame.locator('.zoom-thumb').nth(thumb_index).click()
        page.locator('#lashforge-fullscreen-image').wait_for(state='visible')
        assert page.locator('#lashforge-fullscreen-image').evaluate('(img)=>img.naturalWidth')==2400
        with page.expect_download() as info:
            page.locator('#lashforge-fullscreen-download').click()
        download=info.value
        data=Path(download.path()).read_bytes()
        assert data==(FOLDER/expected).read_bytes(),label
        if frame_index in (1,2): assert download.url.startswith('blob:'),download.url
        else: assert download.url.startswith('http://127.0.0.1:18580/'),download.url
        checks.append(dict(case=label,url=download.url,sha256=hashlib.sha256(data).hexdigest()))
        print('PASS',label,download.suggested_filename,flush=True)
        page.locator('#lashforge-fullscreen-close').click()
    (FOLDER/'report-extra.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print('PASS extra 4 actual HTTP downloads with exact original bytes',flush=True)
    page.goto('about:blank')
    browser.close()
