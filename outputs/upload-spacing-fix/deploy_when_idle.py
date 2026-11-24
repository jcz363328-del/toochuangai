import hashlib, subprocess, sys, time
from pathlib import Path
sys.path.insert(0,'/app')
from 图片.request_limits import get_request_limiter
limiter=get_request_limiter()
try:
 limiter.drain(True)
 deadline=time.monotonic()+300
 stable_since=None
 while True:
  s=limiter.snapshot()
  idle=s['active']==0 and s['waiting']==0
  if idle:
   if stable_since is None:stable_since=time.monotonic()
   if time.monotonic()-stable_since>=10:break
  else:stable_since=None
  if time.monotonic()>deadline:raise RuntimeError('Existing requests have not drained; service kept running')
  time.sleep(5)
 path=Path('/app/图片/openrouter_image_site.py')
 assert hashlib.sha256(path.read_bytes()).hexdigest()=='2adfe207b48e10941d437823718f9dbb16d2b8b175a222f570a5541a0cdc150c','Production changed concurrently'
 path.write_bytes(Path('/tmp/upload-spacing-fix/production-patched.py').read_bytes())
 subprocess.run(['supervisorctl','restart','xiaoha'],check=True)
 print('Production spacing patch active',flush=True)
finally:
 limiter.drain(False)
 print('Request admission restored',flush=True)
