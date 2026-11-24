import sys,json,hashlib,concurrent.futures,os
from decimal import Decimal
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as site
root=Path('/app/图片/history/.credentials')
keys=json.loads((root/'omnia_api_keys.json').read_text())
assert len(set(keys))==5
print('primary_matches_production',keys[0]==site.load_omnia_api_key())
def check(pair):
 i,key=pair
 try:
  r=site.requests.get(site.OMNIAKEY_API_BASE+'/v1/dashboard/billing/usage',headers={'Authorization':'Bearer '+key},allow_redirects=False,**site.get_external_request_kwargs(timeout=(5,12),use_proxy=False))
  if r.status_code!=200:return i,None,r.status_code
  data=r.json()
  value=data.get('total_usage')
  if isinstance(value,bool):return i,None,'invalid'
  amount=Decimal(str(value))/100
  if not amount.is_finite() or amount<0:return i,None,'invalid'
  return i,str(amount),200
 except Exception:return i,None,'unavailable'
results=list(concurrent.futures.ThreadPoolExecutor(max_workers=3).map(check,enumerate(keys)))
for i,amount,status in results: print(json.dumps({'channel':i+1,'usage_http_status':status,'numeric_usage':amount is not None,'zero_usage':amount=='0' or (amount is not None and Decimal(amount)==0)}))
assert all(amount is not None for i,amount,status in results),'Unable to establish all key usage baselines'
assert Decimal(results[0][1])>0 and all(Decimal(v)==0 for i,v,status in results[1:]),'Cannot verify key-scoped usage; baseline not recorded'
baseline={'baseline_id':'user-confirmed-20261124-42.86','balance_usd':'42.86','created_at':datetime.now(timezone.utc).isoformat(),'usage_by_key':{hashlib.sha256(keys[i].encode()).hexdigest():v for i,v,status in results}}
target=root/'balance_baseline.json'
assert not target.exists(),'Baseline already exists'
fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as f:json.dump(baseline,f)
os.chmod(root/'omnia_api_keys.json',0o600)
print('baseline_recorded',True)
