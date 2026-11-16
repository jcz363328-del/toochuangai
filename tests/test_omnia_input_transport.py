import base64
import io
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from 图片 import openrouter_image_site as site

class OmniaInputTests(unittest.TestCase):
    def image(self):
        out = io.BytesIO()
        Image.new('RGBA', (32, 32), (20, 40, 60, 128)).save(out, format='PNG')
        return {'data': out.getvalue(), 'name': 'wrong.jpg', 'type': 'image/jpeg'}

    def test_corrects_mime_and_preserves_alpha(self):
        result = site.prepare_omnia_media_uploaded_input(self.image())
        self.assertEqual(result['type'], 'image/png')
        with Image.open(io.BytesIO(result['data'])) as image:
            self.assertEqual(image.getpixel((0, 0)), (20, 40, 60, 128))

    def test_rejects_corrupt_small_file_before_submit(self):
        with self.assertRaises(RuntimeError):
            site.prepare_omnia_media_uploaded_input({'data': b'not an image', 'name': 'a.png', 'type': 'image/png'})

    def test_single_and_multiple_reference_payloads(self):
        for count in (1, 3):
            response = Mock(status_code=200)
            response.json.return_value = {'id': 'test', 'status': 'failed', 'error': 'test-stop'}
            with patch.object(site, 'load_omnia_api_key', return_value='test-key'), patch.object(site.requests, 'post', return_value=response) as post:
                with self.assertRaisesRegex(RuntimeError, 'test-stop'):
                    site.call_omnia_image_api(site.NANO_BANANA_MODEL, 'test', [self.image()] * count)
                value = post.call_args.kwargs['json']['input']
                refs = [value['image']] if count == 1 else value['images']
                self.assertEqual(len(refs), count)
                for ref in refs:
                    self.assertEqual(ref['mime_type'], 'image/png')
                    Image.open(io.BytesIO(base64.b64decode(ref['data'], validate=True))).verify()

if __name__ == '__main__':
    unittest.main()
