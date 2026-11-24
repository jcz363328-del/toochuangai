import sys,requests,time,json,base64,io
from PIL import Image
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
start=time.monotonic()
r=requests.post(s.OMNIAKEY_API_BASE+'/v1/images/generations',headers={'Authorization':'Bearer '+s.load_omnia_api_key()},json={'model':s.NANO_BANANA_MODEL,'prompt':'a paper boat on a quiet lake at sunset','n':1,'response_format':'b64_json','size':'1024x1024'},timeout=(15,150))
try:v=r.json()
except:v={}
sizes=[]
for item in v.get('data') or []:
 if item.get('b64_json'):
  with Image.open(io.BytesIO(base64.b64decode(item['b64_json']))) as im:sizes.append(im.size)
print(json.dumps({'http':r.status_code,'seconds':round(time.monotonic()-start,1),'sizes':sizes,'error':s.redact_background_error_text(v.get('error'))},ensure_ascii=True),flush=True)
