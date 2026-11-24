import sys,requests,time,json,base64
from pathlib import Path
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
start=time.monotonic()
url=s.OMNIAKEY_API_BASE+'/v1beta/models/'+s.NANO_BANANA_MODEL+':generateContent'
r=requests.post(url,headers={'Authorization':'Bearer '+s.load_omnia_api_key(),'Content-Type':'application/json'},json={'contents':[{'role':'user','parts':[{'text':'A small red paper boat on a plain white background.'}]}],'generationConfig':{'responseModalities':['TEXT','IMAGE']}},timeout=(15,240))
try:v=r.json()
except: v={}
parts=[p for c in v.get('candidates',[]) for p in c.get('content',{}).get('parts',[])]
images=[p.get('inlineData') or p.get('inline_data') for p in parts if p.get('inlineData') or p.get('inline_data')]
for i,img in enumerate(images):Path('/tmp/omnia-native-proof-'+str(i)+'.png').write_bytes(base64.b64decode(img['data']))
print(json.dumps({'http':r.status_code,'seconds':round(time.monotonic()-start,1),'images':len(images),'image_chars':[len(i.get('data','')) for i in images],'finish_reasons':[c.get('finishReason') for c in v.get('candidates',[])],'error':s.redact_background_error_text(v.get('error')),'keys':list(v)},ensure_ascii=True),flush=True)
