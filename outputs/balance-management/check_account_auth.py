import sys,json
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as site
key=site.load_omnia_api_key()
for path in ('/api/me','/api/dashboard/session'):
 try:
  r=site.requests.get('https://omniakey.com'+path,headers={'Authorization':'Bearer '+key},timeout=(5,12),allow_redirects=False)
  print(path,'status',r.status_code)
  if r.status_code==200:
   def schema(obj,depth=0):
    if depth>3:return type(obj).__name__
    if isinstance(obj,dict):return {k:schema(v,depth+1) for k,v in obj.items()}
    return type(obj).__name__
   print('schema',json.dumps(schema(r.json())))
 except Exception:print(path,'request_failed')
