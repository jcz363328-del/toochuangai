import sys,json
from collections import deque
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as site
path=site.OMNIAKEY_TASK_RECEIPTS_FILE
if not path.exists():
 print('no_existing_task_receipt')
 raise SystemExit(0)
with path.open(encoding='utf-8') as f: recent=deque(f,maxlen=10)
receipt=next((json.loads(line) for line in reversed(recent) if line.strip()),None)
if not receipt:
 print('no_existing_task_receipt')
 raise SystemExit(0)
key=site.load_omnia_api_key()
r=site.requests.get(site.OMNIAKEY_MEDIA_TASKS_URL+'/'+site.urllib.parse.quote(receipt['task_id'],safe=''),headers={'Authorization':'Bearer '+key},allow_redirects=False,**site.get_external_request_kwargs(timeout=(5,12),use_proxy=False))
print('existing_task_http_status',r.status_code)
if r.status_code==200:
 data=r.json()
 def schema(value,depth=0):
  if depth>5:return type(value).__name__
  if isinstance(value,dict):return {k:schema(v,depth+1) for k,v in value.items()}
  if isinstance(value,list):return [schema(value[0],depth+1)] if value else []
  return type(value).__name__
 print('task_status',data.get('status'))
 print('response_field_types',json.dumps(schema(data)))
