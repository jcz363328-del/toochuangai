import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit, unquote
from unittest.mock import patch

from Department.视觉设计部.xiaoha import openrouter_image_site as site


class HistoryDownloadIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.upload = self.root / 'uploads'
        self.upload.mkdir()
        self.enterContext(patch.object(site, 'ensure_jimeng_upload_dir', return_value=self.upload))
        self.enterContext(patch.object(site, 'get_jimeng_public_upload_base_url', return_value='https://test/uploads'))
        self.enterContext(patch.object(site, 'DB_IMAGE_DIR', self.root / 'history'))

    def test_same_name_and_size_never_reuse_another_original(self):
        first, second = self.root / 'a/result.png', self.root / 'b/result.png'
        first.parent.mkdir(); second.parent.mkdir()
        first.write_bytes(b'first-original')
        second.write_bytes(b'other-original')
        self.assertEqual(first.stat().st_size, second.stat().st_size)
        urls = [site.build_history_download_public_url(str(p)) for p in (first, second, first)]
        self.assertNotEqual(urls[0], urls[1])
        self.assertEqual(urls[0], urls[2])
        for url, source in zip(urls, (first, second, first)):
            published = self.upload / 'history_downloads' / unquote(urlsplit(url).path.split('/')[-1])
            self.assertEqual(published.read_bytes(), source.read_bytes())

    def test_same_size_replacement_gets_a_new_url(self):
        source = self.root / 'result.png'
        source.write_bytes(b'first-original')
        before = site.build_history_download_public_url(str(source))
        source.write_bytes(b'other-original')
        after = site.build_history_download_public_url(str(source))
        self.assertNotEqual(before, after)

    def test_history_original_keeps_directory_and_bypasses_stale_cache(self):
        source = self.root / 'history/account-a/result.png'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'correct-original')
        cached = self.upload / 'history_downloads/result.png'
        cached.parent.mkdir(); cached.write_bytes(b'wrong-original!!')
        with patch.object(site, 'get_history_public_base_url', return_value='https://test/history'):
            url = site.build_history_download_public_url(str(source))
        self.assertEqual(urlsplit(url).path, '/history/account-a/result.png')
        self.assertIn('v=', urlsplit(url).query)
        self.assertEqual(source.read_bytes(), b'correct-original')

    def test_large_data_url_is_published_without_treating_it_as_a_filename(self):
        original = b'original-image-bytes' * 5000
        source = site.image_bytes_to_data_url(original, 'image/png')
        url = site.build_history_download_public_url(source)
        self.assertTrue(url.startswith('https://test/uploads/history_downloads/'))
        published = self.upload / 'history_downloads' / unquote(urlsplit(url).path.split('/')[-1])
        self.assertEqual(published.read_bytes(), original)
        self.assertEqual(site.build_history_download_public_url(source), url)

    def test_signed_provider_original_is_served_locally_without_changing_its_query(self):
        import io
        from PIL import Image

        output = io.BytesIO()
        Image.new('RGB', (1200, 800), '#409080').save(output, 'PNG')
        original = output.getvalue()
        signed_url = 'https://provider.test/history_images/original.png?signature=keep-exact'
        with patch.object(site, 'load_image_bytes_from_url', return_value=(original, 'application/octet-stream')) as load:
            url = site.build_direct_image_download_url(signed_url)
        load.assert_called_once_with(signed_url)
        self.assertTrue(url.startswith('https://test/uploads/history_downloads/'))
        self.assertIn('download=1', url)
        published = self.upload / 'history_downloads' / unquote(urlsplit(url).path.split('/')[-1])
        self.assertEqual(published.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
