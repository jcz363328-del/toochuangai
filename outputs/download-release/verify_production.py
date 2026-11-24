from pathlib import Path
from urllib.parse import urlsplit, urlencode, parse_qs, unquote
from urllib.request import urlopen
from urllib.error import HTTPError
import hashlib
import io
from PIL import Image
from 图片 import openrouter_image_site as site

for health in ('http://127.0.0.1:8501/lashforge/_stcore/health', 'http://127.0.0.1:8502/_xiaoha_static_health'):
    assert urlopen(health,timeout=10).status == 200
source = next(p for p in site.DB_IMAGE_DIR.rglob('*') if p.is_file() and p.suffix.lower() in ('.png','.jpg','.jpeg','.webp') and p.stat().st_size < 10_000_000)
parsed = urlsplit(site.build_history_download_public_url(str(source)))
query = parse_qs(parsed.query)
query.update(download=['1'], filename=['下载验证_原图'+source.suffix.lower()])
route = parsed.path + '?' + urlencode(query,doseq=True)
with urlopen('http://127.0.0.1:8000'+route,timeout=20) as response:
    downloaded = response.read()
    disposition = response.headers.get('Content-Disposition','')
    assert 'attachment;' in disposition
    assert unquote(disposition.split("filename*=UTF-8''",1)[1]) == query['filename'][0]
assert hashlib.sha256(downloaded).digest() == hashlib.sha256(source.read_bytes()).digest()
with Image.open(io.BytesIO(downloaded)) as image:
    size = image.size
local_bytes,_ = site.load_image_bytes_from_url(site.build_history_download_public_url(str(source)))
assert local_bytes == downloaded
try:
    urlopen('http://127.0.0.1:8000/history_images/__download_regression_missing__.png?download=1',timeout=10)
    raise AssertionError('missing original unexpectedly served')
except HTTPError as error:
    assert error.code == 404
    assert not error.headers.get('Content-Disposition')
print('PASS: production Nginx original download, UTF-8 filename, exact hash, dimensions',size)
print('PASS: server-side original read and missing-file error response')
