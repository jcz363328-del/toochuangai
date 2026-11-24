import sys,requests,time,json,base64
from pathlib import Path
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
start=time.monotonic()
r=requests.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':'Bearer '+s.load_api_key(),'Content-Type':'application/json'},json={'model':'google/gemini-nano-banana-2.1','messages':[{'role':'user','content':'a paper boat on a quiet lake at sunset'}],'modalities':['image','text'],'image_config':{'aspect_ratio':'1:1','image_size':'1K'},'stream':False},timeout=(15,240))
v=r.json()
images=[]
if v.get('choices'):images=s.extract_response_payload(v)['images']
for i,img in enumerate(images):
 decoded=s.decode_data_url(img)
 if decoded:Path('/tmp/openrouter-proof-'+str(i)+'.image').write_bytes(decoded[0])
print(json.dumps({'http':r.status_code,'seconds':round(time.monotonic()-start,1),'images':len(images),'error':s.redact_background_error_text(v.get('error')),'model':v.get('model'),'id':v.get('id')},ensure_ascii=True),flush=True)
