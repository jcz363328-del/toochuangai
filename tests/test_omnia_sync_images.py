import base64
import io
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from Department.视觉设计部.xiaoha import openrouter_image_site as site

class OmniaSyncImageTests(unittest.TestCase):
    def setUp(self):
        limiter = self.enterContext(patch.object(site, 'get_request_limiter')).return_value
        self.enterContext(patch('Department.视觉设计部.xiaoha.request_limits.get_request_limiter', return_value=limiter))
        out = io.BytesIO()
        Image.new('RGB', (12, 12), 'blue').save(out, format='JPEG')
        self.bytes = out.getvalue()
        self.response = Mock(status_code=200, headers={})
        self.response.json.return_value = {'data': [{'b64_json': base64.b64encode(self.bytes).decode()}]}

    def test_legacy_sync_adapter_keeps_actual_mime(self):
        with patch.object(site, 'load_omnia_api_key', return_value='test'), patch.object(site.requests, 'post', return_value=self.response) as post:
            result = site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, 'draw a boat', aspect_ratio='16:9', resolution='2K')
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], site.OMNIAKEY_API_BASE + '/v1/images/generations')
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['model'], site.NANO_BANANA_MODEL)
        self.assertNotIn('aspect_ratio', payload)
        self.assertNotIn('image_size', payload)
        width, height = map(int, payload['size'].split('x'))
        self.assertAlmostEqual(width / height, 16 / 9, places=2)
        self.assertLess(abs(width * height - 2048 ** 2), 2048 * 8)
        self.assertTrue(result['images'][0].startswith('data:image/jpeg;base64,'))
        self.assertEqual(site.decode_data_url(result['images'][0])[0], self.bytes)

    def test_references_use_edit_endpoint_and_keep_all_images(self):
        upload = {'data': self.bytes, 'name': 'wrong.png', 'type': 'image/png'}
        for count in (1, 2, 3):
            with self.subTest(count=count), patch.object(site, 'load_omnia_api_key', return_value='test'), patch.object(site.requests, 'post', return_value=self.response) as post:
                site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, 'edit', [upload] * count)
                self.assertTrue(post.call_args.args[0].endswith('/images/edits'))
                self.assertNotIn('Content-Type', post.call_args.kwargs['headers'])
                self.assertNotIn('json', post.call_args.kwargs)
                self.assertEqual(post.call_args.kwargs['data']['size'], '1024x1024')
                refs = post.call_args.kwargs['files']
                self.assertEqual(len(refs), count)
                for field, (name, data, mime) in refs:
                    self.assertEqual(field, 'image' if count == 1 else 'image[]')
                    self.assertEqual(mime, 'image/png')
                    Image.open(io.BytesIO(data)).verify()

    def test_auto_size_follows_reference_orientation_and_defaults_to_square(self):
        output = io.BytesIO()
        Image.new('RGB', (240, 160)).save(output, format='PNG')
        upload = {'data': output.getvalue(), 'name': 'landscape.png', 'type': 'image/png'}
        with patch.object(site, 'load_omnia_api_key', return_value='test'), patch.object(site.requests, 'post', return_value=self.response) as post:
            site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, 'edit', [upload])
            width, height = map(int, post.call_args.kwargs['data']['size'].split('x'))
            self.assertAlmostEqual(width / height, 1.5, places=2)
            site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, 'draw')
            self.assertEqual(post.call_args.kwargs['json']['size'], '1024x1024')

    def test_uncertain_submission_is_not_resubmitted_by_hd_retry(self):
        for failure in (site.requests.Timeout(), site.requests.ConnectionError()):
            with self.subTest(failure=type(failure)), patch.object(site, 'load_omnia_api_key', return_value='test'), patch.object(site.requests, 'post', side_effect=failure) as post:
                with self.assertRaises(site.OmniaImageOutcomeUnknown) as caught:
                    site.run_hd_batch_generate_with_retry(lambda prompt: site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, prompt), 'test')
                self.assertEqual(post.call_count, 1)
                self.assertIn('未自动重新提交', site.format_omnia_error_message(str(caught.exception)))

    def test_upstream_failure_does_not_fall_back_to_another_provider(self):
        self.response.status_code = 403
        self.response.json.return_value = {'error': {'code': 'upstream_unavailable', 'message': 'unavailable'}}
        with patch.object(site, 'load_omnia_api_key', return_value='test'), patch.object(site.requests, 'post', return_value=self.response) as post:
            with self.assertRaisesRegex(RuntimeError, 'upstream_unavailable'):
                site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, 'test')
            self.assertEqual(post.call_count, 1)

    def test_server_error_is_not_retried_as_new_generation(self):
        self.response.status_code = 504
        with patch.object(site, 'load_omnia_api_key', return_value='test'), patch.object(site.requests, 'post', return_value=self.response) as post:
            with self.assertRaises(site.OmniaImageOutcomeUnknown):
                site.run_hd_batch_generate_with_retry(lambda prompt: site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, prompt), 'test')
            self.assertEqual(post.call_count, 1)

    def test_rejects_bad_or_missing_output(self):
        for value in ({'data': []}, {'data': [{'b64_json': 'not-an-image'}]}):
            with self.subTest(value=value), patch.object(site, 'load_omnia_api_key', return_value='test'), patch.object(site.requests, 'post', return_value=self.response):
                self.response.json.return_value = value
                with self.assertRaises(RuntimeError):
                    site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, 'test')

    def test_other_models_keep_media_transport(self):
        with patch.object(site, 'call_omnia_media_image_api', return_value={'images': ['ok']}) as media, patch.object(site, 'call_omnia_sync_image_api') as sync:
            site.call_omnia_image_api('Dola-Seedream-5.0-pro', 'test')
            media.assert_called_once()
            sync.assert_not_called()

    def test_explicit_canvas_size_is_preserved(self):
        with patch.object(site, 'load_omnia_api_key', return_value='test'), patch.object(site.requests, 'post', return_value=self.response) as post:
            site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, 'draw', size='1536x1024')
            self.assertEqual(post.call_args.kwargs['json']['size'], '1536x1024')

if __name__ == '__main__':
    unittest.main()
