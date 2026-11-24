import sys,json,sqlite3,re,requests,time
from pathlib import Path
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
headers={'Authorization':'Bearer '+s.load_omnia_api_key()}
db=sqlite3.connect(s.HISTORY_DIR/'qa_conversations'/'conversations.sqlite3');db.row_factory=sqlite3.Row
rows=db.execute('SELECT model,status,refs,prompt,error,created FROM turns ORDER BY rowid DESC LIMIT 12').fetchall()
for row in rows:
 d=dict(row); refs=json.loads(d.pop('refs'));prompt=d.pop('prompt');d['prompt_chars']=len(prompt);d['refs_meta']=[]
 for ref in refs:
  p=Path(ref);meta={'exists':p.exists()}
  if p.exists():
   from PIL import Image
   with Image.open(p) as im:meta.update(bytes=p.stat().st_size,size=im.size,format=im.format)
  d['refs_meta'].append(meta)
 print('TURN',json.dumps(d,ensure_ascii=True))
for row in rows[:4]:
 m=re.search(r'task_[A-Za-z0-9]+',row['error'] or '')
 if not m:continue
 r=requests.get(s.OMNIAKEY_MEDIA_TASKS_URL+'/'+m.group(),headers=headers,timeout=30)
 v=r.json();print('TASK',json.dumps({k:v.get(k) for k in ['id','status','model','operation','error','created_at','started_at','updated_at','finished_at','retry_count']},ensure_ascii=True))
r=requests.get(s.OMNIAKEY_API_BASE+'/v1/models',headers=headers,timeout=30)
v=r.json(); models=v.get('data',[]) if isinstance(v,dict) else []
print('MODELS',r.status_code,json.dumps([m for m in models if any(w in str(m.get('id','')).lower() for w in ['banana','image-2','seedream'])],ensure_ascii=True)[:20000])
p=s.OPENROUTER_ERROR_LOG_FILE
if p.exists():
 lines=p.read_text().splitlines()
 for line in lines[-120:]:
  try:v=json.loads(line)
  except:continue
  if 'omnia' in v.get('feature_key','') or 'provider_submit' in v.get('error',''): print('LOG',json.dumps(v,ensure_ascii=True))
