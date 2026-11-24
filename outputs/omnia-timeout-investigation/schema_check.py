import requests,sys,json,re,concurrent.futures
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
for path in ['src/contracts.mjs','src/client.mjs']:
 r=requests.get('https://raw.githubusercontent.com/weareomnia/omniakey-devtools/main/'+path,timeout=25)
 print('OFFICIAL',path,r.status_code,r.text[:24000])
ids=[]
for line in s.OPENROUTER_ERROR_LOG_FILE.read_text().splitlines():
 try:v=json.loads(line)
 except:continue
 if v.get('feature_key')=='omnia_image' and v.get('job_id','').startswith('task_'):ids.append(v['job_id'])
def check(tid):
 r=requests.get(s.OMNIAKEY_MEDIA_TASKS_URL+'/'+tid,headers={'Authorization':'Bearer '+s.load_omnia_api_key()},timeout=25)
 v=r.json();return {'http':r.status_code,**{k:v.get(k) for k in ['id','model','status','operation','error','created_at','finished_at']}}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for v in pool.map(check,ids[-8:]):print('EXISTING',json.dumps(v,ensure_ascii=True))
