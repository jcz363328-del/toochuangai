import sys,json,time,uuid,requests
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
url=s.OMNIAKEY_MEDIA_TASKS_URL
headers={'Authorization':'Bearer '+s.load_omnia_api_key(),'Content-Type':'application/json','Idempotency-Key':'xiaoha-check-'+uuid.uuid4().hex}
payload={'model':'gemini-nano-banana-2.1','type':'image','operation':'generate','input':{'prompt':'a paper boat on a quiet lake at sunset'},'parameters':{'aspect_ratio':'1:1'}}
start=time.monotonic()
r=requests.post(url,headers=headers,json=payload,timeout=(15,60));v=r.json();tid=v.get('id')
print(json.dumps({'event':'submitted','http':r.status_code,'id':tid,'status':v.get('status'),'error':v.get('error')},ensure_ascii=True),flush=True)
if tid:
 while time.monotonic()-start<600:
  if v.get('status') in ('succeeded','failed','canceled','cancelled'):break
  time.sleep(5)
  r=requests.get(url+'/'+tid,headers={'Authorization':headers['Authorization']},timeout=(15,35));r.raise_for_status();v=r.json()
 print(json.dumps({'event':'result','elapsed_seconds':round(time.monotonic()-start,1),**{k:v.get(k) for k in ['id','status','error','created_at','finished_at']},'asset_count':len(v.get('assets') or [])},ensure_ascii=True),flush=True)
 if v.get('status')=='succeeded' and v.get('assets'):
  from pathlib import Path
  a=v['assets'][0];r=requests.get(a['url'],timeout=(15,60));r.raise_for_status();Path('/tmp/omnia-latest-proof.image').write_bytes(r.content)
  print(json.dumps({'event':'downloaded','bytes':len(r.content),'mime_type':a.get('mime_type')},ensure_ascii=True),flush=True)
