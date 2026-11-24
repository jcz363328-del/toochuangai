import sys,json
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as site
headers={'Authorization':'Bearer '+site.load_omnia_api_key()}
s=site.requests.get(site.OMNIAKEY_API_BASE+'/v1/dashboard/billing/subscription',headers=headers,timeout=(5,12),allow_redirects=False).json()
u=site.requests.get(site.OMNIAKEY_API_BASE+'/v1/dashboard/billing/usage',headers=headers,timeout=(5,12),allow_redirects=False).json()
limit=s.get('hard_limit_usd');used=u.get('total_usage')
print(json.dumps({'numeric':isinstance(limit,(int,float)) and isinstance(used,(int,float)),'unlimited_sentinel':limit==100000000,'positive_remaining':isinstance(limit,(int,float)) and isinstance(used,(int,float)) and limit-used/100>0,'reference_matches_configured_total':limit==100}))
