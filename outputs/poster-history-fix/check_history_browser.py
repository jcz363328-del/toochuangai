from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1080})
 page.goto('http://127.0.0.1:18613/')
 page.get_by_text('历史记录',exact=True).first.click()
 page.get_by_role('button',name='打开历史记录',exact=True).click()
 gallery=page.frame_locator('iframe').locator('.zoom-thumb')
 # Find the gallery iframe among helper frames inside the modal.
 page.wait_for_function("Array.from(document.querySelectorAll('iframe')).some(f=>f.contentDocument?.querySelector('.zoom-thumb'))")
 frame=next(f for f in page.frames if f.locator('.zoom-thumb').count())
 frame.locator('.zoom-thumb').click()
 image=page.locator('#lashforge-fullscreen-image')
 image.wait_for()
 page.wait_for_function("document.querySelector('#lashforge-fullscreen-image').naturalWidth===600")
 result=image.evaluate("el=>{const ev=new MouseEvent('contextmenu',{button:2,bubbles:true,cancelable:true});return {allowed:el.dispatchEvent(ev),width:el.naturalWidth,height:el.naturalHeight,original:el.src.startsWith('data:image/png')}}")
 assert result=={'allowed':True,'width':600,'height':400,'original':True},result
 assert page.locator('#lashforge-eagle-menu:visible').count()==0
 # Exercise a real right click as well; it must not create the custom menu.
 image.click(button='right')
 assert page.locator('#lashforge-eagle-menu:visible').count()==0
 page.keyboard.press('Escape')
 assert page.locator('[data-testid=stException]').count()==0
 print('PASS: history modal original 600x400; native context menu permitted over HTTP; custom menu does not intercept')
 browser.close()
