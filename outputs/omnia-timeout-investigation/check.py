import requests,json,sys,sqlite3
from pathlib import Path
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
id='task_iaUJHhl6EdaXLVYNf97BoDcqEp5phH0q'
r=requests.get(s.OMNIAKEY_MEDIA_TASKS_URL+'/'+id,headers={'Authorization':'Bearer '+s.load_omnia_api_key()},timeout=30)
v=r.json()
print(json.dumps({'http':r.status_code,'keys':list(v),'id':v.get('id'),'status':v.get('status'),'error':v.get('error'),'created_at':v.get('created_at'),'updated_at':v.get('updated_at'),'asset_count':len(v.get('assets') or [])},ensure_ascii=True,default=str))
p=s.HISTORY_DIR/'qa_conversations'/'conversations.sqlite3'
if p.exists():
 con=sqlite3.connect(p)
 rows=con.execute('SELECT id,status,job,created,error FROM turns WHERE error LIKE ? ORDER BY rowid DESC LIMIT 6',('%'+id+'%',)).fetchall()
 print(json.dumps({'matching_turns':rows},ensure_ascii=True));con.close()
