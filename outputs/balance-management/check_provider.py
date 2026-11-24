import sys,json
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as site
key=site.load_omnia_api_key()
assert key, 'Missing configured provider credential'
for suffix in ('subscription','usage'):
 response=site.requests.get(site.OMNIAKEY_API_BASE+'/v1/dashboard/billing/'+suffix,headers={'Authorization':'Bearer '+key},allow_redirects=False,**site.get_external_request_kwargs(timeout=(5,12),use_proxy=False))
 print(suffix,'status',response.status_code)
 if response.status_code==200:
  body=response.json()
  print('field_types',json.dumps({name:type(value).__name__ for name,value in body.items()}))
  print('object',body.get('object'))
  if suffix=='subscription':print('limits_equal',body.get('hard_limit_usd')==body.get('soft_limit_usd')==body.get('system_hard_limit_usd'))
 else:
  print('request_failed_without_disclosing_body')
