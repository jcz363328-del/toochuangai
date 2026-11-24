import sys,json,time,requests,uuid,base64,io
from pathlib import Path
from PIL import Image,ImageDraw
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
im=Image.new('RGB',(256,256),'white');ImageDraw.Draw(im).rectangle((64,64,192,192),fill='red');b=io.BytesIO();im.save(b,format='PNG')
payload={'model':s.NANO_BANANA_MODEL,'prompt':'Change the red square to a blue square. Keep its position, shape, and the white background unchanged.','image':'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode(),'n':1,'response_format':'b64_json','aspect_ratio':'1:1','image_size':'1K'}
start=time.monotonic()
r=requests.post(s.OMNIAKEY_API_BASE+'/v1/images/edits',headers={'Authorization':'Bearer '+s.load_omnia_api_key(),'Content-Type':'application/json','Idempotency-Key':'xiaoha-edit-check-'+uuid.uuid4().hex},json=payload,timeout=(15,240))
try:v=r.json()
except:v={}
for i,item in enumerate(v.get('data') or []):
 if item.get('b64_json'):
  decoded=base64.b64decode(item['b64_json']);Path('/tmp/omnia-edit-proof.image').write_bytes(decoded)
  out=Image.open(io.BytesIO(decoded));print(json.dumps({'image_size':out.size,'center_pixel':out.convert('RGB').getpixel((out.width//2,out.height//2))}),flush=True)
print(json.dumps({'http':r.status_code,'seconds':round(time.monotonic()-start,1),'keys':list(v),'images':len(v.get('data') or []),'error':s.redact_background_error_text(v.get('error')),'request_id':r.headers.get('x-request-id')},ensure_ascii=True),flush=True)
