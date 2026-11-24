from pathlib import Path
p=Path('outputs/xiaoha-main-namespace-fix');s=(p/'before.py').read_text(encoding='utf-8-sig')
assert s.count('from threading import Lock, Thread')==1
assert s.count('sys.modules[__name__]')==2
s=s.replace('from threading import Lock, Thread','from threading import Lock, Thread\nfrom types import SimpleNamespace',1)
s=s.replace('sys.modules[__name__]','SimpleNamespace(**globals())')
(p/'openrouter_image_site.py').write_text(s,encoding='utf-8')
(p/'Dockerfile').write_text('FROM toochuangai-single:latest\nCOPY openrouter_image_site.py /app/图片/openrouter_image_site.py\n',encoding='utf-8')
