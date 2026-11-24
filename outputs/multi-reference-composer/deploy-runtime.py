import hashlib,json,subprocess,sys,time,urllib.request
from pathlib import Path
from 图片.request_limits import get_request_limiter
limiter=get_request_limiter()
main=Path('/app/图片/openrouter_image_site.py')
module=Path('/app/图片/multi_reference_composer.py')
original=main.read_bytes()
original_module=module.read_bytes() if module.exists() else None
changed=False
try:
    assert hashlib.sha256(original).hexdigest()=='287904bb4b4c3ab883bbc3409bd335afcab2692e2a51998261e034a95c1f0d14', 'Runtime source changed'
    state=limiter.snapshot()
    assert state['draining'] and not state['active'] and not state['waiting'], 'Requests still active'
    staged_main=Path('/tmp/multi-reference-new-main.py').read_bytes()
    staged_module=Path('/tmp/multi-reference-new-module.py').read_bytes()
    compile(staged_main,str(main),'exec')
    compile(staged_module,str(module),'exec')
    module.write_bytes(staged_module)
    main.write_bytes(staged_main)
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
    print(json.dumps({'deployed':True,'sha256':hashlib.sha256(main.read_bytes()).hexdigest(),'module_sha256':hashlib.sha256(module.read_bytes()).hexdigest()}))
except Exception:
    if changed:
        main.write_bytes(original)
        if original_module is None:
            module.unlink(missing_ok=True)
        else:
            module.write_bytes(original_module)
        subprocess.run(['supervisorctl','restart','xiaoha'],check=False)
    raise
finally:
    limiter.drain(False)
    print('New requests enabled.')
