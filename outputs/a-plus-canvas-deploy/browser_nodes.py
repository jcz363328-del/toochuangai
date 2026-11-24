from pathlib import Path
import sys, os, io, base64, json
sys.path.insert(0,str(Path('outputs/qa-browser-deps').resolve()))
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(Path('outputs/qa-browser-binaries').resolve())
from PIL import Image
from playwright.sync_api import sync_playwright
out=Path('outputs/a-plus-canvas-deploy')
b=io.BytesIO();Image.new('RGB',(160,100),'#9e89bb').save(b,format='PNG');data='data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1700,'height':1100})
 errors=[];requests=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('**/api/bootstrap-config*',lambda r:r.fulfill(status=200,json={'success':False}))
 page.route('**/api/detect-public-figures*',lambda r:r.fulfill(status=200,json={'success':True,'detected':False,'names':[]}))
 def respond(route):
    requests.append(route.request.post_data_json)
    route.fulfill(status=200,json={'success':True,'images':[data]*4,'image':data})
 page.route('**/api/image-feature*',respond)
 page.goto('http://127.0.0.1:18610/infinite-canvas/canvas?workspace=a_plus')
 page.get_by_role('button',name='新建画布',exact=True).first.click()
 page.get_by_role('button',name='功能模块',exact=True).click()
 page.get_by_role('button',name='亚马逊A+改沃尔玛A+',exact=True).click()
 page.wait_for_timeout(600)
 print('databases',page.evaluate('indexedDB.databases()'),flush=True)
 project_id=page.url.split('/canvas/')[1].split('?')[0]
 # Use the actual persisted schema to load a connected-input workflow.
 page.evaluate('''async ({data,id})=>{
  const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('infinite-canvas');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)});
  await new Promise((resolve,reject)=>{const t=db.transaction('app_state','readwrite');const store=t.objectStore('app_state');const r=store.get('infinite-canvas:a_plus_canvas_store');r.onsuccess=()=>{
    const v=JSON.parse(r.result);const p=v.state.projects.find(p=>p.id===id);
    p.nodes=[{id:'source',type:'image',title:'原始A+',position:{x:200,y:220},width:260,height:200,metadata:{content:data,mimeType:'image/png'}},
      {id:'module',type:'image',title:'沃尔玛转换节点',position:{x:620,y:220},width:300,height:220,metadata:{imageFunction:'amazon_to_walmart_a_plus',status:'idle'}}];
    p.connections=[{id:'edge',fromNodeId:'source',toNodeId:'module'}];p.viewport={x:0,y:0,k:1};
    store.put(JSON.stringify(v),'infinite-canvas:a_plus_canvas_store');};t.oncomplete=resolve;t.onerror=()=>reject(t.error);});db.close();
 }''',{'data':data,'id':project_id})
 page.reload()
 module=page.locator('[data-node-id="module"]')
 module.click(position={'x':130,'y':90})
 generate=page.get_by_role('button',name='生成',exact=True)
 generate.wait_for(timeout=5000)
 assert generate.is_enabled(),page.locator('body').inner_text()[-2000:]
 generate.click()
 page.wait_for_timeout(2000)
 print('request count',len(requests),'page errors',errors,flush=True)
 page.screenshot(path=str(out/'debug-nodes.png'),full_page=True)
 page.wait_for_function("""async () => {
 const db=await new Promise(r=>{const q=indexedDB.open('infinite-canvas');q.onsuccess=()=>r(q.result)});
 const v=await new Promise(r=>{const q=db.transaction('app_state').objectStore('app_state').get('infinite-canvas:a_plus_canvas_store');q.onsuccess=()=>r(q.result)});db.close();
 return JSON.parse(v).state.projects[0].nodes.length===6;
 }""",timeout=5000)
 assert len(requests)==1 and requests[0]['feature']=='amazon_to_walmart_a_plus'
 assert requests[0]['images']==[data]
 page.wait_for_timeout(600)
 page.screenshot(path=str(out/'connected-nodes.png'),full_page=True)
 page.reload()
 page.wait_for_function("""async () => {
 const db=await new Promise(r=>{const q=indexedDB.open('infinite-canvas');q.onsuccess=()=>r(q.result)});
 const v=await new Promise(r=>{const q=db.transaction('app_state').objectStore('app_state').get('infinite-canvas:a_plus_canvas_store');q.onsuccess=()=>r(q.result)});db.close();
 return JSON.parse(v).state.projects[0].nodes.length===6;
 }""",timeout=5000)
 # Normal library is distinct.
 page.goto('http://127.0.0.1:18610/infinite-canvas/canvas')
 page.get_by_role('heading',name='无限画布',exact=True).wait_for()
 assert page.locator('text=还没有画布').count()==1
 assert not errors,errors
 print('PASS: A+ module menu, connected-input generation, four output nodes, reload persistence, isolated normal library; mocked model response only',flush=True)
 browser.close()
