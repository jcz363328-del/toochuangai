import sys, os, io, base64, json
from pathlib import Path
sys.path.insert(0, str(Path('outputs/qa-browser-deps').resolve()))
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(Path('outputs/qa-browser-binaries').resolve())
from PIL import Image
from playwright.sync_api import sync_playwright

buffer = io.BytesIO()
Image.new('RGB', (100, 140), 'purple').save(buffer, format='PNG')
data = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
READ = '''async () => {
const db=await new Promise(r=>{const q=indexedDB.open('infinite-canvas');q.onsuccess=()=>r(q.result)});
const value=await new Promise(r=>{const q=db.transaction('app_state').objectStore('app_state').get('infinite-canvas:a_plus_canvas_store');q.onsuccess=()=>r(q.result)});db.close();return JSON.parse(value);
}'''
WRITE = '''async (value) => {
const db=await new Promise(r=>{const q=indexedDB.open('infinite-canvas');q.onsuccess=()=>r(q.result)});
await new Promise(r=>{const t=db.transaction('app_state','readwrite');t.objectStore('app_state').put(JSON.stringify(value),'infinite-canvas:a_plus_canvas_store');t.oncomplete=r});db.close();
}'''
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width':1800, 'height':1200})
    errors, calls = [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.route('**/api/bootstrap-config*', lambda r: r.fulfill(status=200,json={'success':False}))
    def request(route):
        payload = route.request.post_data_json
        calls.append(payload)
        if payload['action'] == 'analyze':
            name = 'A' if len(calls) == 1 else 'B'
            analysis = {key: name+'-'+key for key in ['prompt','background','subject','supporting_elements','decoration','typography','texture']}
            route.fulfill(status=200,json={'success':True,'text':analysis['prompt'],'analysis':analysis})
        else:
            route.fulfill(status=200,json={'success':True,'images':[data]})
    page.route('**/api/reference-node*', request)
    page.goto('http://127.0.0.1:18614/infinite-canvas/canvas?workspace=a_plus')
    page.get_by_role('button',name='新建画布',exact=True).first.click()
    page.get_by_role('button',name='功能模块',exact=True).click()
    page.get_by_role('button',name='参考图反推',exact=True).click()
    page.wait_for_timeout(1000)
    value=page.evaluate(READ)
    project=value['state']['projects'][0]
    project['nodes']=[{'id':name,'type':'image','title':'参考图'+name,'position':{'x':100,'y':y},'width':260,'height':200,'metadata':{'content':data,'mimeType':'image/png','imageFunction':'reference_reverse','status':'idle'}} for name,y in [('a',120),('b',540)]]
    project['connections']=[]; project['viewport']={'x':0,'y':0,'k':1}
    page.evaluate(WRITE,value);page.reload()
    for name in ['a','b']:
        page.locator(f'[data-node-id="{name}"]').click(position={'x':120,'y':100})
        button=page.get_by_role('button',name='反推文案',exact=True)
        button.wait_for(timeout=5000)
        button.click()
        page.wait_for_timeout(1300)
    assert len(calls)==2,calls
    assert all(len(call['images'])==1 for call in calls)
    value=page.evaluate(READ);project=value['state']['projects'][0]
    texts=[node for node in project['nodes'] if node['metadata'].get('referenceAnalysis')]
    assert len(texts)==2,project['nodes']
    print('Two separate image analyses passed',flush=True)
    for node,field in zip(texts,['background','subject']):
        page.mouse.click(1650,1000)
        page.locator(f'[data-node-id="{node["id"]}"]').click(position={'x':80,'y':80})
        page.wait_for_timeout(200)
        # Open the node prompt panel with its existing composer action.
        if not page.get_by_role('checkbox',name='完整文案',exact=True).count():
            page.get_by_role("button",name="编辑",exact=True).click()
        page.get_by_role('checkbox',name='背景' if field=='background' else '主体',exact=True).check()
        page.wait_for_timeout(350)
    page.wait_for_timeout(900)
    value=page.evaluate(READ);project=value['state']['projects'][0]
    texts=[node for node in project['nodes'] if node['metadata'].get('referenceAnalysis')]
    assert texts[0]['metadata']['content']=='背景：A-background',texts[0]
    assert texts[1]['metadata']['content']=='主体：B-subject',texts[1]
    project['nodes'].append({'id':'compose','type':'image','title':'文案组合生图','position':{'x':1000,'y':200},'width':300,'height':220,'metadata':{'imageFunction':'reference_compose','status':'idle'}})
    project['connections'] += [{'id':'join'+str(i),'fromNodeId':node['id'],'toNodeId':'compose'} for i,node in enumerate(texts)]
    page.evaluate(WRITE,value);page.reload()
    page.locator('[data-node-id="compose"]').click(position={'x':100,'y':100})
    button=page.get_by_role('button',name='组合生图',exact=True);button.wait_for();assert button.is_enabled();button.click();page.wait_for_timeout(1400)
    assert calls[-1]['action']=='generate' and calls[-1]['images']==[],calls[-1]
    assert 'A-background' in calls[-1]['prompt'] and 'B-subject' in calls[-1]['prompt']
    assert 'A-subject' not in calls[-1]['prompt'] and 'B-background' not in calls[-1]['prompt']
    value=page.evaluate(READ);nodes=value['state']['projects'][0]['nodes'];assert len(nodes)==6,nodes
    page.screenshot(path='outputs/reference-canvas/connected-workflow.png',full_page=True)
    page.reload();page.wait_for_timeout(1200);assert len(page.evaluate(READ)['state']['projects'][0]['nodes'])==6
    assert not errors,errors
    print('Selected content + text-only generation + output + reload persistence passed; all model calls mocked',flush=True)
    browser.close()
