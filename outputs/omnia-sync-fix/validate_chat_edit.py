import ast
import io
import json
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, '/app')
from 图片 import openrouter_image_site as site
from 图片 import qa_chat

# Exercise the public image adapter and chat persistence without replacing
# the running service until the new transport has been verified.
source = Path('/tmp/omnia-patched-site.py').read_text(encoding='utf-8-sig')
namespace = vars(site)
namespace['OMNIAKEY_SYNC_IMAGE_TIMEOUT_SECONDS'] = 300
for node in ast.parse(source).body:
    if getattr(node, 'name', '') in {'OmniaImageOutcomeUnknown', 'call_omnia_sync_image_api', 'call_omnia_image_api'}:
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<patched-sync>', 'exec'), namespace)

references = []
for color in ('red', 'blue'):
    image = Image.new('RGB', (256, 256), 'white')
    ImageDraw.Draw(image).rectangle((64, 64, 192, 192), fill=color)
    output = io.BytesIO()
    image.save(output, format='PNG')
    references.append({'data': output.getvalue(), 'name': color + '.png', 'type': 'image/png'})

started = time.monotonic()
with tempfile.TemporaryDirectory(prefix='omnia-chat-check-') as folder:
    store = qa_chat.ChatStore(Path(folder))
    chat = store.create('transport-check')
    prompt = 'Change the red square in the first image to the blue color shown in the second image. Keep its layout and the white background.'
    turn = store.add('transport-check', chat, prompt, [], site.NANO_BANANA_MODEL)
    context = {'qa_chat_root': folder, 'account_name': 'transport-check', 'qa_turn_id': turn}
    try:
        result = qa_chat.run_chat_job(site, context, lambda _: site.call_openrouter_images_api(
            model=site.NANO_BANANA_MODEL, prompt=prompt, uploaded_files=references,
            aspect_ratio=site.DEFAULT_ASPECT_RATIO, max_attempts=1))
        saved = store.turns('transport-check', chat)[0]
        raw, mime = site.load_image_bytes_from_url(saved['images'][0])
        image = Image.open(io.BytesIO(raw))
        pixel = image.convert('RGB').getpixel((image.width // 2, image.height // 2))
        Path('/tmp/omnia-chat-edit-proof.image').write_bytes(raw)
        print(json.dumps({'success': True, 'seconds': round(time.monotonic() - started, 1),
            'status': saved['status'], 'saved_images': len(saved['images']), 'size': image.size,
            'center_pixel': pixel, 'mime': mime, 'channel': result['channel']}), flush=True)
    except Exception as exc:
        print(json.dumps({'success': False, 'seconds': round(time.monotonic() - started, 1),
            'error': site.redact_background_error_text(exc)}, ensure_ascii=True), flush=True)
