"""Read-only deployment smoke checks; never submits a paid model request."""
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, '/app')
from 图片 import openrouter_image_site as site
from 图片.request_limits import get_request_limiter

report = {}
with urllib.request.urlopen('http://127.0.0.1:8501/lashforge/_stcore/health', timeout=10) as response:
    report['web_health'] = response.read().decode()
with urllib.request.urlopen('http://127.0.0.1:8502/_xiaoha_static_health', timeout=10) as response:
    report['static_health'] = json.load(response)

query = urllib.parse.urlencode({site.AUTH_QUERY_USER_KEY: 'admin', site.AUTH_QUERY_TOKEN_KEY: site.build_auth_token('admin')})
base = 'http://127.0.0.1:8502'
with urllib.request.urlopen(base + '/infinite-canvas/api/bootstrap-config?' + query, timeout=10) as response:
    config = json.load(response)['config']
channel = config['channel']
assert channel['baseUrl'] == '/infinite-canvas/api/omnia/v1'
assert channel['apiKey'].startswith('xh1.')
assert channel['apiKey'] != site.load_omnia_api_key()
report['canvas_uses_backend_proxy'] = True
headers = {'Authorization': 'Bearer ' + channel['apiKey'], 'Content-Type': 'application/json'}
with urllib.request.urlopen(urllib.request.Request(base + channel['baseUrl'] + '/models', headers=headers), timeout=10) as response:
    report['model_count'] = len(json.load(response)['data'])

# Intentionally unsupported model: local validation must reject before any API call.
request = urllib.request.Request(base + channel['baseUrl'] + '/images/generations',
    data=json.dumps({'model': '__invalid_smoke_check__', 'prompt': 'validation only'}).encode(), headers=headers)
try:
    urllib.request.urlopen(request, timeout=10)
    raise AssertionError('unsupported model was accepted')
except urllib.error.HTTPError as error:
    assert error.code == 400, error.code
    report['invalid_model_rejected'] = error.code
report['limiter'] = get_request_limiter().snapshot()
assert report['limiter']['active'] == 0 and report['limiter']['waiting'] == 0
assert not report['limiter']['draining']
report['hashes'] = {name: hashlib.sha256((Path('/app/图片') / name).read_bytes()).hexdigest()
    for name in ('openrouter_image_site.py', 'qa_chat.py', 'request_limits.py', 'canvas_api_proxy.py')}
print(json.dumps(report, ensure_ascii=False, indent=2))
