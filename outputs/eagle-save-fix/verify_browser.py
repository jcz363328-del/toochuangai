import ast, json, os, sys, urllib.parse
from pathlib import Path
from types import SimpleNamespace
from typing import Any
sys.path.insert(0,str(Path('outputs/qa-browser-deps').resolve()))
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(Path('outputs/qa-browser-binaries').resolve())
from playwright.sync_api import sync_playwright

root=Path('outputs/eagle-save-fix')
source=Path(sys.argv[1] if len(sys.argv)>1 else '图片/openrouter_image_site.py').read_text(encoding='utf-8')
module=ast.parse(source)
fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='render_zoomable_image_gallery')
original='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aB1sAAAAASUVORK5CYII='
rendered=[]
ns=dict(Any=Any,json=json,os=os,urllib=urllib,st=SimpleNamespace(iframe=lambda html,**kw:rendered.append(html)),
 build_gallery_item=lambda *a,**kw:dict(src=original,full_src='/original.png',width=1,height=1,download_name='eagle-original.png'),
 get_history_public_base_url=lambda:'https://xiaoha.test/history_images',get_jimeng_public_upload_base_url=lambda:'https://xiaoha.test/jimeng_uploads',
 HISTORY_STATIC_ROUTE_PREFIX='/history_images',JIMENG_UPLOAD_ROUTE_PREFIX='/jimeng_uploads',UPLOAD_DELETE_QUERY_KEY='delete')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<gallery>','exec'),ns)
ns['render_zoomable_image_gallery'](['fixture'],1,160,'eagle_test')
html=rendered[0]
(root/'gallery.html').write_text(html,encoding='utf-8')
import base64
image_bytes=base64.b64decode(original.split(',',1)[1])
passed=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 for scenario in ['success','login','offline','rejected','invalid_response','http','old_menu']:
  page=browser.new_page()
  errors=[]; posts=[]; calls=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  def route(req):
   url=req.request.url;calls.append(url)
   if '/api/application/info' in url:
    if scenario=='offline':return req.abort('connectionrefused')
    return req.fulfill(json={'status':'success','data':{'version':'4.0'}})
   if '/api/item/addFromURL' in url:
    posts.append(req.request.post_data_json)
    if scenario=='invalid_response':return req.fulfill(body='{}',content_type='application/json')
    return req.fulfill(json={'status':'error' if scenario=='rejected' else 'success','message':'Library unavailable'})
   if url.endswith('/original.png'):
    return req.fulfill(body=b'<html>login</html>' if scenario=='login' else image_bytes,content_type='text/html' if scenario=='login' else 'image/png')
   body=html
   if scenario=='old_menu':body='<div id="lashforge-eagle-menu"><button id="lashforge-save-to-eagle">old</button></div>'+body
   return req.fulfill(body=body,content_type='text/html; charset=utf-8')
  page.route('**/*',route)
  page.goto(('http' if scenario=='http' else 'https')+'://xiaoha.test/')
  page.locator('.zoom-thumb').click(button='right')
  page.locator('#lashforge-save-to-eagle').click()
  page.wait_for_function("document.querySelector('#lashforge-eagle-toast').textContent !== '正在保存到 Eagle…'")
  message=page.locator('#lashforge-eagle-toast').inner_text()
  assert not errors,errors
  assert not page.locator('#lashforge-save-to-eagle').is_disabled()
  if scenario in ('success','old_menu'):
   assert message=='已保存到 Eagle',message
   assert len(posts)==1
   assert posts[0]['url']==original
   assert posts[0]['name']=='eagle-original.png'
   assert page.locator('#lashforge-eagle-menu').get_attribute('data-version')=='20261124-2'
  elif scenario=='http':
   assert 'HTTP' in message and 'Alt' in message,message
   assert not any('/api/' in c for c in calls),calls
  elif scenario=='login':assert '登录已过期' in message and not posts,message
  elif scenario=='offline':assert '本机 Eagle' in message and not posts,message
  elif scenario=='rejected':assert 'Library unavailable' in message,message
  else:assert '失败' in message,message
  page.locator('.zoom-thumb').click()
  allowed=page.locator('#lashforge-fullscreen-image').evaluate("el => el.dispatchEvent(new MouseEvent('contextmenu', {altKey:true,bubbles:true,cancelable:true}))")
  assert allowed,'Alt + context menu prevented'
  passed.append(scenario)
  page.close()
 browser.close()
(root/'browser-report.json').write_text(json.dumps({'passed':passed,'count':len(passed)},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: '+', '.join(passed))

