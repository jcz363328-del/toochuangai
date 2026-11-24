import sys,json,time,uuid,requests,concurrent.futures
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
key=s.load_omnia_api_key();url=s.OMNIAKEY_MEDIA_TASKS_URL

def run(model):
 h={'Authorization':'Bearer '+key,'Idempotency-Key':'diagnostic-'+uuid.uuid4().hex}
 payload={'model':model,'type':'image','operation':'generate','input':{'prompt':'A small red paper boat on a plain white background.'},'parameters':{}}
 start=time.monotonic()
 try:
  r=requests.post(url,headers=h,json=payload,timeout=(15,60));v=r.json();tid=v.get('id')
  print(json.dumps({'event':'submitted','model':model,'http':r.status_code,'id':tid,'status':v.get('status'),'error':v.get('error')},ensure_ascii=True),flush=True)
  if not tid:return
  while time.monotonic()-start<420:
   if v.get('status') in ['succeeded','failed','cancelled','canceled']:break
   time.sleep(8)
   r=requests.get(url+'/'+tid,headers={'Authorization':'Bearer '+key},timeout=(15,35));v=r.json()
  result={'model':model,'elapsed_seconds':round(time.monotonic()-start,1),**{k:v.get(k) for k in ['id','status','error','created_at','started_at','finished_at','retry_count']},'asset_count':len(v.get('assets') or [])}
  print(json.dumps({'event':'result',**result},ensure_ascii=True),flush=True)
 except Exception as e:print(json.dumps({'event':'exception','model':model,'type':type(e).__name__},ensure_ascii=True),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,['gemini-nano-banana-2.1','gpt-image-2.5-flare']))
