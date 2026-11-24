import sys,ast,time,json,io
from pathlib import Path
from PIL import Image
sys.path.insert(0,'/app')
from 图片 import openrouter_image_site as site
source=Path('/tmp/omnia-patched-site.py').read_text(encoding='utf-8-sig')
namespace=vars(site);namespace['OMNIAKEY_SYNC_IMAGE_TIMEOUT_SECONDS']=300
for node in ast.parse(source).body:
 if getattr(node,'name','') in {'OmniaImageOutcomeUnknown','call_omnia_sync_image_api'}:
  exec(compile(ast.Module(body=[node],type_ignores=[]),'<patched-sync>','exec'),namespace)
start=time.monotonic()
try:
 result=site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL,'a paper boat on a quiet lake at sunset',aspect_ratio='1:1')
 raw,mime=site.decode_data_url(result['images'][0]);im=Image.open(io.BytesIO(raw));im.verify();Path('/tmp/omnia-integrated-proof.image').write_bytes(raw)
 print(json.dumps({'success':True,'seconds':round(time.monotonic()-start,1),'mime':mime,'size':im.size,'bytes':len(raw),'channel':result['channel']}),flush=True)
except Exception as exc:print(json.dumps({'success':False,'seconds':round(time.monotonic()-start,1),'error':site.redact_background_error_text(exc)},ensure_ascii=True),flush=True)
