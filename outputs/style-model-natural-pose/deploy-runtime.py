import hashlib,json,subprocess,sys,time,urllib.request
from pathlib import Path
from 图片.request_limits import get_request_limiter
limiter=get_request_limiter()
main=Path('/app/图片/openrouter_image_site.py')
original=main.read_bytes()
changed=False
try:
    assert hashlib.sha256(original).hexdigest()=='e5173f37f671bb8e1cf00fe4f162a4b08919caa4a6e6c6ad379b2802b6b9071c', 'Runtime source changed'
    limiter.drain(True)
    quiet=0
    for attempt in range(16):
        state=limiter.snapshot()
        quiet=quiet+1 if not state['active'] and not state['waiting'] else 0
        if quiet>=5: break
        time.sleep(3)
    else:
        raise RuntimeError('Tasks still running; update deferred')
    staged=Path('/tmp/style-model-natural-pose-new-main.py').read_bytes()
    compile(staged,str(main),'exec')
    main.write_bytes(staged)
    changed=True
    subprocess.run(['supervisorctl','restart','xiaoha'],check=True)
    for attempt in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8501/lashforge/_stcore/health',timeout=2) as response:
                if response.status==200: break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError('Xiaoha did not become healthy')
    subprocess.run([sys.executable,'/app/docker/healthcheck.py'],check=True)
    print(json.dumps({'deployed':True,'sha256':hashlib.sha256(main.read_bytes()).hexdigest()}))
except Exception:
    if changed:
        main.write_bytes(original)
        subprocess.run(['supervisorctl','restart','xiaoha'],check=False)
    raise
finally:
    limiter.drain(False)
    print('New requests enabled.')
