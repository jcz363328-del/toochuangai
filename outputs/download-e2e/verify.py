import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]
sys.path.insert(0,str(ROOT/'outputs/qa-browser-deps'))
from playwright.sync_api import sync_playwright

ORIGINALS = [FOLDER/'history/a/result.png', FOLDER/'history/b/result.png', FOLDER/'history/c/photo.jpg']
checks=[]
failures=[]
requests=[]
errors=[]

def record_download(page, click, expected, label):
    with page.expect_download(timeout=20000) as event:
        click()
    download=event.value
    assert download.failure() is None, download.failure()
    data=Path(download.path()).read_bytes()
    assert data == expected.read_bytes(), f'{label}: bytes differ from {expected}'
    if label.startswith(('data original','remote original')):
        assert download.url.startswith('blob:'),download.url
    else:
        assert download.url.startswith('http://127.0.0.1:18580/'),download.url
    checks.append({'case':label,'filename':download.suggested_filename,'url':download.url,'sha256':hashlib.sha256(data).hexdigest()})
    print('PASS',label,download.suggested_filename,flush=True)

with sync_playwright() as playwright:
    browser=playwright.chromium.launch(executable_path=str(next((ROOT/'outputs/qa-browser-binaries/chromium-1255').rglob('chrome.exe'))),headless=True)
    context=browser.new_context(accept_downloads=True,viewport={'width':1500,'height':1100})
    # Verify the ordinary download fallback used on HTTP and unsupported browsers.
    context.add_init_script('window.showSaveFilePicker = undefined;')
    page=context.new_page()
    page.set_default_timeout(15000)
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:requests.append(r.url))
    page.on('requestfailed',lambda r:print('REQUEST FAILED',r.url,r.failure,flush=True))
    page.on('dialog',lambda dialog:(errors.append('DIALOG: '+dialog.message),dialog.dismiss()))
    page.goto('http://127.0.0.1:18580/',wait_until='networkidle')
    page.get_by_role('button',name='打开历史记录',exact=True).wait_for()
    for index,expected in enumerate(ORIGINALS):
        record_download(page,lambda index=index:page.get_by_role('button',name=f'问答下载原图 {index+1}',exact=True).click(),expected,f'QA initial download button {index+1}')
    print('Fixture loaded. Iframes:',page.locator('iframe').count(),flush=True)
    print('SANDBOX',page.locator('iframe').first.get_attribute('sandbox'),flush=True)
    page.get_by_role('button',name='打开历史记录',exact=True).click()
    dialog=page.get_by_role('dialog')
    dialog.wait_for()
    page.wait_for_function("document.querySelectorAll('[role=dialog] iframe').length >= 3")
    for index,expected in enumerate(ORIGINALS):
        # Each card is a genuine st.iframe srcdoc in a genuine st.dialog.
        thumbnail=dialog.locator('iframe').nth(index).content_frame.locator('.zoom-thumb')
        thumbnail.click()
        page.locator('#lashforge-fullscreen-image').wait_for(state='visible')
        full_url=page.locator('#lashforge-fullscreen-image').get_attribute('src')
        assert full_url.startswith('http://127.0.0.1:18580/'),full_url
        for method in ['button','context','save_as']:
            def click(method=method):
                if method=='button': page.locator('#lashforge-fullscreen-download').click()
                else:
                    page.locator('#lashforge-fullscreen-image').click(button='right')
                    page.locator('#lashforge-save-as-image' if method=='save_as' else '#lashforge-download-image').click()
            record_download(page,click,expected,f'history image {index+1} {method}')
            assert checks[-1]['filename']==f'原图_{index+1}{expected.suffix}',checks[-1]
        page.locator('#lashforge-fullscreen-close').click()
    # Thumbnail right-click can have different coordinates and modal menu host.
    thumbnail=dialog.locator('iframe').nth(0).content_frame.locator('.zoom-thumb')
    thumbnail.click(button='right')
    record_download(page,lambda:page.locator('#lashforge-download-image').click(),ORIGINALS[0],'history thumbnail context')
    dialog.get_by_role('button',name='全选当前图片').click()
    print('SELECT ALL CLICKED',flush=True)
    page.screenshot(path=str(FOLDER/'after-select-all.png'))
    print('SCREENSHOT',flush=True)
    archive_button=dialog.get_by_role('button',name='批量下载已选图片（3 张）')
    print('ZIP ENABLED',archive_button.is_enabled(),flush=True)
    with page.expect_download(timeout=20000) as event:
        print('ZIP CLICK',flush=True)
        archive_button.click()
        print('ZIP CLICK DONE',flush=True)
    zip_download=event.value
    print('ZIP EVENT',zip_download.suggested_filename,zip_download.url,flush=True)
    assert zip_download.failure() is None,zip_download.failure()
    zip_data=Path(zip_download.path()).read_bytes()
    with zipfile.ZipFile(io.BytesIO(zip_data)) as archive:
        actual=[archive.read(name) for name in archive.namelist()]
        assert len(actual)==3,archive.namelist()
        assert sorted(hashlib.sha256(v).hexdigest() for v in actual)==sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in ORIGINALS)
    checks.append({'case':'history ZIP all 3 originals','filename':zip_download.suggested_filename})
    print('PASS history ZIP all 3 originals',flush=True)
    # Dismiss and re-open to exercise old viewer/menu DOM and new iframe handlers.
    page.get_by_role('dialog').get_by_role('button',name='Close',exact=True).click()
    page.get_by_role('button',name='打开历史记录',exact=True).click()
    thumbnail=page.get_by_role('dialog').locator('iframe').nth(1).content_frame.locator('.zoom-thumb')
    thumbnail.click()
    record_download(page,lambda:page.locator('#lashforge-fullscreen-download').click(),ORIGINALS[1],'history reopened second image')
    page.locator('#lashforge-fullscreen-close').click()
    page.get_by_role('dialog').get_by_role('button',name='Close',exact=True).click()
    for index,expected in enumerate(ORIGINALS):
        record_download(page,lambda index=index:page.get_by_role('button',name=f'问答下载原图 {index+1}',exact=True).click(),expected,f'QA download button {index+1}')
    result_iframe=page.locator('iframe').first.content_frame
    for index,expected in enumerate(ORIGINALS[:2]):
        result_iframe.locator('.zoom-thumb').nth(index).click()
        record_download(page,lambda:page.locator('#lashforge-fullscreen-download').click(),expected,f'result enlarged {index+1}')
        page.locator('#lashforge-fullscreen-close').click()
    for frame_index,expected,label in [(1,ORIGINALS[2],'data original'),(2,ORIGINALS[0],'remote original without CORS')]:
        page.locator('iframe').nth(frame_index).content_frame.locator('.zoom-thumb').click()
        record_download(page,lambda:page.locator('#lashforge-fullscreen-download').click(),expected,label)
        assert page.locator('#lashforge-fullscreen-image').evaluate('(img)=>img.naturalWidth')==2400
        page.locator('#lashforge-fullscreen-close').click()
    compare_iframe=page.locator('iframe').last.content_frame
    compare_image=compare_iframe.locator('.compare-native-result')
    compare_box=compare_image.bounding_box()
    compare_image.click(position={'x':compare_box['width']*.75,'y':compare_box['height']*.5})
    record_download(page,lambda:page.locator('#lashforge-fullscreen-download').click(),ORIGINALS[1],'compare enlarged after regular gallery')
    assert page.locator('#lashforge-fullscreen-image').evaluate('(img)=>img.oncontextmenu===null')
    assert page.locator('#lashforge-fullscreen-image').evaluate('(img)=>img.naturalWidth')==2400
    assert page.locator('#lashforge-fullscreen-image').evaluate('(img)=>img.naturalHeight')==1600
    page.locator('#lashforge-fullscreen-close').click()
    print('ERRORS',errors,flush=True)
    assert not errors,errors
    assert not any('public-config.invalid' in r or ':8000/history_images/' in r for r in requests),[r for r in requests if 'history_images' in r]
    (FOLDER/'report.json').write_text(json.dumps({'checks':checks,'requests':requests,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS',len(checks),'real HTTP/Streamlit download checks, including ZIP containing 3 originals',flush=True)
    page.goto('about:blank')
    context.close()
    browser.close()
