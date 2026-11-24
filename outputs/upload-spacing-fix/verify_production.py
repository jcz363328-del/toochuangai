from pathlib import Path
import base64,io,json
from PIL import Image
from playwright.sync_api import sync_playwright
out=Path('/tmp/upload-spacing-fix')
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':2151,'height':1055},device_scale_factor=1)
 page.goto('http://127.0.0.1:18612/?kind=actual&feature=hd_batch')
 page.locator('[data-testid=stFileUploaderDropzone]').first.wait_for()
 b=io.BytesIO();Image.new('RGB',(160,240),'#46769a').save(b,format='PNG')
 data=base64.b64encode(b.getvalue()).decode()
 dt=page.evaluate_handle("data=>{const dt=new DataTransfer();dt.items.add(new File([Uint8Array.from(atob(data),c=>c.charCodeAt(0))],'spacing-sample.png',{type:'image/png'}));return dt;}",data)
 page.locator('[data-testid=stFileUploaderDropzone]').first.dispatch_event('drop',{'dataTransfer':dt})
 page.wait_for_function('document.querySelectorAll("[data-testid=stFileUploaderDropzone]").length>=2')
 page.wait_for_timeout(300)
 metrics=page.locator('.panel-subtitle').first.evaluate('''el=>{let nodes=[],p=el;while(p&&nodes.length<7){const r=p.getBoundingClientRect(),s=getComputedStyle(p);nodes.push({tag:p.tagName,classes:p.className,testid:p.dataset.testid,x:r.x,y:r.y,w:r.width,h:r.height,gap:s.gap,margin:s.margin,padding:s.padding,height:s.height,overflow:s.overflow});p=p.parentElement}const z=document.querySelector('[data-testid="stFileUploaderDropzone"]').getBoundingClientRect();return {nodes,zone:{x:z.x,y:z.y,h:z.height}}}''')
 assert metrics['zone']['y']-(metrics['nodes'][0]['y']+metrics['nodes'][0]['h'])>=8,metrics
 print('Desktop subtitle-to-frame gap:',round(metrics['zone']['y']-(metrics['nodes'][0]['y']+metrics['nodes'][0]['h']),2))
 page.screenshot(path=str(out/'production-after.png'),full_page=True)
 (out/'after-dom.html').write_text(page.content(),encoding='utf-8')
 for feature in ['hd_batch','background_texture','product_retouch_local']:
  if feature!='hd_batch':
   page.goto('http://127.0.0.1:18612/?kind=actual&feature='+feature)
   page.locator('.panel-subtitle').first.wait_for()
  for width in [1440,1024,390]:
   page.set_viewport_size({'width':width,'height':1055})
   page.wait_for_timeout(150)
   assert page.locator('[data-testid=stException]').count()==0
   result=page.locator('.panel-subtitle,.result-block-title,.section-kicker').evaluate_all("""nodes=>nodes.filter(el=>el.getBoundingClientRect().height).map(el=>{const r=el.getBoundingClientRect(),p=el.closest('[data-testid=stElementContainer]');return {label:el.textContent,reserved:p.getBoundingClientRect().bottom-r.bottom}})""")
   assert all(r['reserved']>=-1 for r in result),(feature,width,result)
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(feature,width)
   print('PASS',feature,width,'headings:',len(result))
 browser.close()

