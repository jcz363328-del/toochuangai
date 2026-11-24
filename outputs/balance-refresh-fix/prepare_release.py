import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
project = root.parents[1]
names = ['omnia_cost_ledger.py', 'omnia_service.py', 'balance_provider.py', 'balance_view.py']
for baseline in ['runtime', 'image']:
    dest = root / (baseline + '-release')
    dest.mkdir(exist_ok=True)
    manifest = []
    for name in names:
        compile((project / '图片' / name).read_text(encoding='utf-8-sig'), name, 'exec')
        shutil.copy2(project / '图片' / name, dest / name)
        manifest.append({'name': name,
                         'before': hashlib.sha256((root / ('before-' + baseline) / name).read_bytes()).hexdigest(),
                         'after': hashlib.sha256((dest / name).read_bytes()).hexdigest()})
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

script = (root.parent / 'omnia-five-key' / 'deploy_when_idle.py').read_text(encoding='utf-8')
script = script.replace('/tmp/xiaoha-five-key/', '/tmp/xiaoha-balance-refund/')
script = script.replace('Five-key release active and healthy', 'Balance refund release active and healthy')
(root / 'deploy_when_idle.py').write_text(script, encoding='utf-8')
print('Scoped source overlays prepared')
