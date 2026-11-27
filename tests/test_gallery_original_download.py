import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from Department.视觉设计部.xiaoha import openrouter_image_site as site


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

    def test_explicit_embedded_gallery_keeps_original_before_preview_compression(self):
        self.assert_original(site.build_gallery_item(self.source, embed_full_src=True))

    def test_default_gallery_publishes_original_and_sends_only_thumbnail(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            site, 'get_jimeng_public_upload_base_url', return_value='https://assets.test/uploads'
        ), patch.object(site, 'ensure_jimeng_upload_dir', return_value=Path(folder)):
            item = site.build_gallery_item(self.source)
            self.assertTrue(item['full_src'].startswith('https://assets.test/uploads/history_downloads/'))
            originals = list((Path(folder) / 'history_downloads').iterdir())
            self.assertEqual(len(originals), 1)
            self.assertEqual(originals[0].read_bytes(), self.original)
            preview, _ = site.decode_data_url(item['src'])
            with Image.open(io.BytesIO(preview)) as image:
                self.assertLessEqual(max(image.size), 640)
            self.assertNotIn(self.source, str(item))

    def test_local_original_is_browser_downloadable_without_resizing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'original.png'
            path.write_bytes(self.original)
            self.assert_original(site.build_gallery_item(str(path), embed_full_src=True))

    def test_thumbnail_does_not_fetch_separate_managed_original(self):
        original_url = 'https://assets.test/uploads/full.png'
        with patch.object(site, 'build_history_download_public_url', return_value=original_url) as publish, patch.object(
            site, 'load_image_bytes_from_url', side_effect=AssertionError('Original must stay unloaded')
        ):
            item = site.build_gallery_item(self.source, full_image_source=original_url)
        self.assertEqual(item['full_src'], original_url)
        publish.assert_called_once_with(original_url)

    def test_provider_original_is_published_without_a_second_download(self):
        source = 'https://provider.test/signed-original.png'
        with patch.object(site, 'load_image_bytes_from_url', return_value=(self.original, 'image/png')) as load, patch.object(
            site, 'build_history_download_public_url', return_value='https://assets.test/original.png'
        ) as publish:
            item = site.build_gallery_item(source, full_image_source=source)
        self.assertEqual(item['full_src'], 'https://assets.test/original.png')
        load.assert_called_once_with(source)
        publish.assert_called_once_with(self.source)

    def test_separate_history_thumbnail_never_replaces_original(self):
        preview = io.BytesIO()
        Image.new('RGB', (120, 80), '#3167af').save(preview, 'JPEG')
        item = site.build_gallery_item(
            site.image_bytes_to_data_url(preview.getvalue(), 'image/jpeg'),
            full_image_source=self.source,
            embed_full_src=True,
        )
        self.assert_original(item)

    def test_provider_image_does_not_require_browser_cors_to_download(self):
        source = 'https://provider.test/signed-original.png'
        for content_type in ('image/png', 'application/octet-stream'):
            with self.subTest(content_type=content_type):
                with patch.object(site, 'load_image_bytes_from_url', return_value=(self.original, content_type)) as load:
                    item = site.build_gallery_item(source, full_image_source=source, embed_full_src=True)
                self.assert_original(item)
                self.assertTrue(item['full_src'].startswith('data:image/png;'))
                load.assert_called_once_with(source)

    def test_jpeg_original_download_keeps_jpeg_extension(self):
        output = io.BytesIO()
        Image.new('RGB', (1200, 800), '#3167af').save(output, 'JPEG')
        source = site.image_bytes_to_data_url(output.getvalue(), 'image/jpeg')
        with patch.object(site.st, 'iframe') as render:
            site.render_zoomable_image_gallery([source], 1, 120, 'jpeg_original', embed_full_src=True)
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
