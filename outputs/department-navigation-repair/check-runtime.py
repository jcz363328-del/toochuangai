from pathlib import Path
import hashlib, json
p=Path('/app')
print(json.dumps({n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in ('app.py','templates/operation_dept.html','图片/openrouter_image_site.py')},ensure_ascii=False))
