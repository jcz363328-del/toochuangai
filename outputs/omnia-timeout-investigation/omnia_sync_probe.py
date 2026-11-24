import sys,json,time,requests,uuid
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
start=time.monotonic()
r=requests.post(s.OMNIAKEY_API_BASE+'/v1/images/generations',headers={'Authorization':'Bearer '+s.load_omnia_api_key(),'Content-Type':'application/json','Idempotency-Key':'xiaoha-sync-check-'+uuid.uuid4().hex},json={'model':s.NANO_BANANA_MODEL,'prompt':'a paper boat on a quiet lake at sunset','n':1,'response_format':'b64_json'},timeout=(15,240))
try:v=r.json()
except:v={}
print(json.dumps({'http':r.status_code,'seconds':round(time.monotonic()-start,1),'keys':list(v),'images':len(v.get('data') or []),'error':s.redact_background_error_text(v.get('error')),'request_id':r.headers.get('x-request-id')},ensure_ascii=True),flush=True)
