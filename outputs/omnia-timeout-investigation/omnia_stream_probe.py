import sys,json,time,requests,base64,io
from pathlib import Path
from PIL import Image,ImageDraw
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
im=Image.new('RGB',(256,256),'white');ImageDraw.Draw(im).rectangle((32,48,128,160),fill='red');ImageDraw.Draw(im).ellipse((168,180,220,232),fill='green');b=io.BytesIO();im.save(b,format='PNG')
url='data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
payload={'model':s.NANO_BANANA_MODEL,'messages':[{'role':'user','content':[{'type':'text','text':'Change only the red rectangle to blue. Keep the green circle, white background and positions unchanged.'},{'type':'image_url','image_url':{'url':url}}]}],'modalities':['image','text'],'stream':True}
start=time.monotonic();chunks=[];images=[]
with requests.post(s.OMNIAKEY_CHAT_COMPLETIONS_URL,headers={'Authorization':'Bearer '+s.load_omnia_api_key(),'Content-Type':'application/json'},json=payload,stream=True,timeout=(15,150)) as r:
 print(json.dumps({'event':'headers','http':r.status_code,'seconds':round(time.monotonic()-start,1),'content_type':r.headers.get('content-type')}),flush=True)
 if r.status_code>=400:
  print(s.redact_background_error_text(r.text[:1600]),flush=True)
 else:
  for line in r.iter_lines():
   if not line.startswith(b'data:'):continue
   text=line[5:].strip()
   if text==b'[DONE]':break
   try:v=json.loads(text)
   except:continue
   chunks.append(v)
   if v.get('error'):print('ERROR',json.dumps(v['error']),flush=True)
   for choice in v.get('choices') or []:
    delta=choice.get('delta') or choice.get('message') or {}
    for image in delta.get('images') or []:
     source=(image.get('image_url') or {}).get('url');images.append(source)
   if time.monotonic()-start>240:break
  Path('/tmp/omnia-stream-probe.json').write_text(json.dumps(chunks))
  for i,source in enumerate(images):
   decoded=s.decode_data_url(source)
   if decoded:Path('/tmp/omnia-stream-proof-'+str(i)+'.image').write_bytes(decoded[0])
 print(json.dumps({'event':'result','seconds':round(time.monotonic()-start,1),'chunks':len(chunks),'images':len(images)}),flush=True)
