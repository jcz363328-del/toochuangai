"""Run interaction and responsive checks in an isolated headless Edge instance."""
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cdp_transport', ROOT.parents[1] / 'tmp/cdp_shot.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
port = 9446
edge = subprocess.Popen([transport.EDGE, '--headless=new', '--disable-gpu', '--no-first-run',
    f'--remote-debugging-port={port}', f'--user-data-dir={ROOT / "qa-profile"}', 'about:blank'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(50):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list') as response:
                targets = json.load(response)
            page = next(t for t in targets if t['type'] == 'page')
            break
        except Exception:
            time.sleep(.2)
    ws = transport.WebSocket(page['webSocketDebuggerUrl'])
    counter = 0
    def call(method, params=None):
        global counter
        counter += 1
        ws.send(json.dumps({'id':counter, 'method':method, 'params':params or {}}))
        while True:
            message = json.loads(ws.recv())
            if message.get('id') == counter:
                assert 'error' not in message, message
                return message.get('result', {})
    def js(expression):
        result = call('Runtime.evaluate', {'expression':expression, 'returnByValue':True})
        assert 'exceptionDetails' not in result, result
        return result.get('result', {}).get('value')
    call('Page.enable')
    call('Page.navigate', {'url':'http://127.0.0.1:8767/'})
    for _ in range(50):
        if js("document.querySelector('#total')?.textContent") == '12':
            break
        time.sleep(.1)
    assert js("document.querySelector('#total').textContent") == '12'
    assert js("document.querySelector('#rate').textContent") == '16.67%'
    assert js("document.querySelector('.proposal-section') === null") is True
    shots = ROOT / 'previews'
    shots.mkdir(exist_ok=True)
    for theme in ['blue', 'navy', 'green']:
        js(f"document.querySelector('[data-theme-choice={theme}]').click()")
        for width, height in [(1503,1046),(1440,1000),(390,844),(2340,1300)]:
            call('Emulation.setDeviceMetricsOverride', {'width':width,'height':height,'deviceScaleFactor':1,'mobile':False})
            js('window.scrollTo(0,0)')
            time.sleep(.1)
            if not js('document.documentElement.scrollWidth <= innerWidth'):
                raise AssertionError((theme,width,'overflow'))
            image = call('Page.captureScreenshot', {'format':'png','captureBeyondViewport':False})
            (shots / f'{theme}-{width}.png').write_bytes(base64.b64decode(image['data']))
    js("document.querySelector('[data-period=month]').click();document.querySelector('#start').value='2026-11-20';document.querySelector('#end').value='2026-11-01';document.querySelector('#filters').requestSubmit()")
    assert js("document.querySelector('#dateError').textContent.length > 0")
    js("document.querySelector('[data-period=month]').click();document.querySelector('[data-create]').click()")
    assert js("document.querySelector('#createDialog').open") is True
    js("document.querySelector('[name=title]').value='<script>演示</script>';document.querySelector('[name=description]').value='测试内容';document.querySelector('#createForm').requestSubmit()")
    assert js("document.querySelector('#total').textContent") == '13'
    assert js("document.querySelector('.proposal-section') === null") is True
    js("document.querySelector('nav [data-view=points]').click()")
    assert js("document.querySelector('.points-content').hidden") is False
    js("document.querySelector('nav [data-view=stars]').click()")
    assert js("document.querySelector('.stars-content').hidden") is False
    print('PASS: 3 themes x 4 widths; metrics; no proposal detail section; invalid dates; submit; points; stars.')
    ws.close()
finally:
    edge.terminate()

