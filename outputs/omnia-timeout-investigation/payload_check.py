import sys,sqlite3,json
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as s
from 图片.qa_chat import ChatStore,build_context
from unittest.mock import patch
store=ChatStore(s.HISTORY_DIR)
with store.connect() as db:rows=db.execute('SELECT chat,id FROM turns WHERE error LIKE ? ORDER BY rowid DESC LIMIT 2',('%provider_submit_uncertain%',)).fetchall()
for row in rows:
 with store.connect() as db:account=db.execute('SELECT account FROM chats WHERE id=?',(row['chat'],)).fetchone()[0]
 turns=store.turns(account,row['chat']);t=next(t for t in turns if t['id']==row['id']);prior=turns[:turns.index(t)]
 refs,prompt=build_context(prior,t['prompt'],t['refs'])
 feature=dict(s.get_feature_by_key('ai_qa_image'))
 prompt=s.build_prompt(feature,prompt,t['ratio'],'只生成图片，严格执行本轮要求。')
 files=[s.image_url_as_uploaded_input(src,'ref.png') for src in refs]
 class Captured(Exception):pass
 def capture(*args,**kwargs):
  payload=kwargs['json'];images=payload['input'].get('images') or ([payload['input']['image']] if 'image' in payload['input'] else [])
  print(json.dumps({'turn':t['id'],'model':payload['model'],'operation':payload['operation'],'parameters':payload['parameters'],'json_bytes':len(json.dumps(payload).encode()),'prompt_chars':len(payload['input']['prompt']),'refs_count':len(images),'mime_types':[i.get('mime_type') for i in images]},ensure_ascii=True))
  raise Captured()
 with patch.object(s.requests,'post',side_effect=capture):
  try:s.call_omnia_image_api(t['model'],prompt,files,t['ratio'],max_attempts=1)
  except Captured:pass
