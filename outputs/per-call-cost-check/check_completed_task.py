import sys,json
from datetime import datetime,timezone,timedelta
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as site
now=datetime.now(timezone.utc)
candidates=[]
with site.OMNIAKEY_TASK_RECEIPTS_FILE.open(encoding='utf-8') as f:
 for line in f:
  try:
   row=json.loads(line)
   stamp=datetime.fromisoformat(row['timestamp'])
   if timedelta(minutes=10)<now-stamp<timedelta(hours=23):candidates.append(row)
  except (ValueError,KeyError):pass
key=site.load_omnia_api_key()
for receipt in candidates[-3:][::-1]:
 r=site.requests.get(site.OMNIAKEY_MEDIA_TASKS_URL+'/'+site.urllib.parse.quote(receipt['task_id'],safe=''),headers={'Authorization':'Bearer '+key},allow_redirects=False,**site.get_external_request_kwargs(timeout=(5,12),use_proxy=False))
 print('existing_task_http_status',r.status_code)
 if r.status_code!=200:continue
 data=r.json()
 print('task_status',data.get('status'))
 if data.get('status')!='succeeded':continue
 def schema(value,depth=0):
  if depth>5:return type(value).__name__
  if isinstance(value,dict):return {k:schema(v,depth+1) for k,v in value.items()}
  if isinstance(value,list):return [schema(value[0],depth+1)] if value else []
  return type(value).__name__
 print('response_field_types',json.dumps(schema(data)))
 break
else:print('no_completed_task_sample')
