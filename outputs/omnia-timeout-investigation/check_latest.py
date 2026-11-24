import requests,json,sys,sqlite3,re
from pathlib import Path
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
p=s.HISTORY_DIR/'qa_conversations'/'conversations.sqlite3';c=sqlite3.connect(p)
rows=c.execute("SELECT error,created FROM turns WHERE error LIKE '%provider_submit_uncertain%' ORDER BY rowid DESC LIMIT 2").fetchall();c.close()
for error,created in rows:
 id=re.search(r'task_[A-Za-z0-9]+',error).group()
 r=requests.get(s.OMNIAKEY_MEDIA_TASKS_URL+'/'+id,headers={'Authorization':'Bearer '+s.load_omnia_api_key()},timeout=30);v=r.json()
 print(json.dumps({'http':r.status_code,'local_created':created,**{k:v.get(k) for k in ['id','status','error','created_at','updated_at','billing','retryable']},'keys':list(v),'asset_count':len(v.get('assets') or [])},ensure_ascii=True,default=str))
