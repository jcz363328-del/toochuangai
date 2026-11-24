import sys, json, concurrent.futures
sys.path.insert(0, '/app')
from 图片 import openrouter_image_site as site
ns = site.load_config_namespace()
print('relevant_config_names', [k for k in ns if any(s in k.lower() for s in ['omnia','balance','account','token'])])
paths = ['/api/user/self', '/v1/balance', '/v1/me', '/v1/credits', '/api/usage/token/', '/v1/dashboard/billing/balance', '/api/token/self', '/dashboard/billing/credit_grants']
def check(path):
 try:
  r=site.requests.get(site.OMNIAKEY_API_BASE+path,timeout=(4,8),allow_redirects=False)
  return {'path':path,'status':r.status_code,'type':r.headers.get('Content-Type','')}
 except Exception:return {'path':path,'failed':True}
for result in concurrent.futures.ThreadPoolExecutor(max_workers=4).map(check,paths):print(json.dumps(result))
