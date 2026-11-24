import sys,json,requests,concurrent.futures
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
checks=[('openrouter_key','https://openrouter.ai/api/v1/auth/key',s.load_api_key()),('openrouter_models','https://openrouter.ai/api/v1/models',s.load_api_key())]
def run(entry):
 name,url,key=entry
 try:
  r=requests.get(url,headers={'Authorization':'Bearer '+key},timeout=(10,30));v=r.json()
  if name.endswith('models'):
   data=[{'id':m.get('id'),'output':m.get('architecture',{}).get('output_modalities'),'pricing':m.get('pricing')} for m in v.get('data',[]) if 'image' in m.get('architecture',{}).get('output_modalities',[])]
  else:
   d=v.get('data',{});data={k:d.get(k) for k in ['limit_remaining','limit','usage','is_free_tier']}
  print(json.dumps({'name':name,'http':r.status_code,'data':data,'error':s.redact_background_error_text(v.get('error'))},ensure_ascii=True))
 except Exception as e:print(name,type(e).__name__)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,checks))
