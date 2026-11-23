import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from 图片 import openrouter_image_site as site


class GalleryOriginalDownloadTests(unittest.TestCase):
    def setUp(self):
        buffer = io.BytesIO()
        Image.new('RGB', (2400, 1600), '#3167af').save(buffer, 'PNG')
        self.original = buffer.getvalue()
        self.source = site.image_bytes_to_data_url(self.original, 'image/png')

    def assert_original(self, item):
        original, _ = site.decode_data_url(item['full_src'])
        preview, _ = site.decode_data_url(item['src'])
        self.assertEqual(original, self.original)
        self.assertNotEqual(preview, original)
        with Image.open(io.BytesIO(original)) as image:
            self.assertEqual(image.size, (2400, 1600))

    def test_default_gallery_keeps_original_before_preview_compression(self):
        self.assert_original(site.build_gallery_item(self.source))

    def test_local_original_is_browser_downloadable_without_resizing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'original.png'
            path.write_bytes(self.original)
            self.assert_original(site.build_gallery_item(str(path)))

    def test_separate_history_thumbnail_never_replaces_original(self):
        preview = io.BytesIO()
        Image.new('RGB', (120, 80), '#3167af').save(preview, 'JPEG')
        item = site.build_gallery_item(
            site.image_bytes_to_data_url(preview.getvalue(), 'image/jpeg'),
            full_image_source=self.source,
        )
        self.assert_original(item)

    def test_provider_image_does_not_require_browser_cors_to_download(self):
        source = 'https://provider.test/signed-original.png'
        for content_type in ('image/png', 'application/octet-stream'):
            with self.subTest(content_type=content_type):
                with patch.object(site, 'load_image_bytes_from_url', return_value=(self.original, content_type)) as load:
                    item = site.build_gallery_item(source, full_image_source=source)
                self.assert_original(item)
                self.assertTrue(item['full_src'].startswith('data:image/png;'))
                load.assert_called_once_with(source)

    def test_jpeg_original_download_keeps_jpeg_extension(self):
        output = io.BytesIO()
        Image.new('RGB', (1200, 800), '#3167af').save(output, 'JPEG')
        source = site.image_bytes_to_data_url(output.getvalue(), 'image/jpeg')
        with patch.object(site.st, 'iframe') as render:
            site.render_zoomable_image_gallery([source], 1, 120, 'jpeg_original')
        self.assertIn('"download_name": "jpeg_original_1.jpg"', render.call_args.args[0])

    def test_asset_download_does_not_require_the_desktop_socks_proxy(self):
        from contextlib import nullcontext
        from unittest.mock import Mock

        response = Mock(content=self.original, headers={'Content-Type': 'image/png'})
        limiter = Mock()
        limiter.slot.return_value = nullcontext()
        def fetch(_url, **kwargs):
            if kwargs.get('proxies'):
                raise site.requests.exceptions.InvalidSchema('Missing dependencies for SOCKS support.')
            return response
        with patch.object(site, 'get_request_limiter', return_value=limiter), patch.object(
            site.requests, 'get', side_effect=fetch
        ):
            downloaded, _ = site.load_image_bytes_from_url('https://provider.test/original.png')
        self.assertEqual(downloaded, self.original)


if __name__ == '__main__':
    unittest.main()
