import hashlib,json
from pathlib import Path
from 图片.request_limits import get_request_limiter
source=Path('/app/图片/openrouter_image_site.py')
print(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'requests':get_request_limiter().snapshot()},ensure_ascii=False))
