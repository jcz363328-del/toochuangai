import hashlib,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,'/app')
from 图片.request_limits import get_request_limiter
root=Path('/tmp/a-plus-blank-fusion/runtime-release')
manifest=json.loads((root/'manifest.json').read_text())
for file in manifest:
 assert hashlib.sha256((root/file['name']).read_bytes()).hexdigest()==file['after']
 compile((root/file['name']).read_text(encoding='utf-8-sig'),file['name'],'exec')
limiter=get_request_limiter()
try:
 limiter.drain(True)
 deadline=time.monotonic()+300
 stable_since=None
 while True:
  state=limiter.snapshot()
  print(json.dumps({k:state.get(k) for k in ['active','waiting','retained','draining']}),flush=True)
  if state['active']==0 and state['waiting']==0:
   if stable_since is None:stable_since=time.monotonic()
   if time.monotonic()-stable_since>=10:break
  else:stable_since=None
  if time.monotonic()>deadline:raise RuntimeError('Existing work is still running; service unchanged')
  time.sleep(5)
 for file in manifest:
  target=Path('/app/图片')/file['name']
  assert hashlib.sha256(target.read_bytes()).hexdigest()==file['before'],'Production changed concurrently: '+file['name']
 for file in manifest:
  target=Path('/app/图片')/file['name']
  staged=target.with_suffix(target.suffix+'.poster-history-new')
  staged.write_bytes((root/file['name']).read_bytes())
  os.replace(staged,target)
 subprocess.run(['supervisorctl','restart','xiaoha'],check=True)
 print('A+ blank-space fusion release active',flush=True)
finally:
 limiter.drain(False)
 print('Request admission restored',flush=True)
