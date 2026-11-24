import base64
import io
import sys
from pathlib import Path
from unittest.mock import patch
from PIL import Image

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from 图片 import openrouter_image_site as site

folder = Path(__file__).parent
previews = {}
for name, color in [('a', 'red'), ('b', 'blue'), ('c', 'green')]:
    out = io.BytesIO()
    Image.new('RGB', (2400, 1600), color).save(out, 'PNG')
    (folder / f'{name}.png').write_bytes(out.getvalue())
    previews[name] = 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()
for gallery, names in [('first', ['a', 'c']), ('second', ['b'])]:
    with patch.object(site.st, 'iframe') as render:
        site.render_zoomable_image_gallery([previews[n] for n in names], columns=2,
            thumb_height=100, component_key=gallery, include_full_src=True,
            full_images=[f'http://history.test/original/{n}.png' for n in names],
            download_names=[f'{n}-original.png' for n in names])
    (folder / f'{gallery}.html').write_text(render.call_args.args[0], encoding='utf-8')
