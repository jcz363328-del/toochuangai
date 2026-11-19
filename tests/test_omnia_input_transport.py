import base64
import io
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from 图片 import openrouter_image_site as site

class OmniaInputTests(unittest.TestCase):
    def setUp(self):
        limiter = self.enterContext(patch.object(site, 'get_request_limiter')).return_value
        self.enterContext(patch('图片.request_limits.get_request_limiter', return_value=limiter))

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
            with patch.object(site, 'load_omnia_api_key', return_value='test-key'), patch.object(site.requests, 'post', return_value=response) as post, patch.object(site, 'record_background_job_error') as log_error:
                with self.assertRaisesRegex(RuntimeError, 'test-stop'):
                    site.call_omnia_media_image_api(site.NANO_BANANA_MODEL, 'test', [self.image()] * count)
                self.assertEqual(log_error.call_args.args[:3], ('test', 'omnia_image', 'failed'))
                value = post.call_args.kwargs['json']['input']
                refs = [value['image']] if count == 1 else value['images']
                self.assertEqual(len(refs), count)
                for ref in refs:
                    self.assertEqual(ref['mime_type'], 'image/png')
                    Image.open(io.BytesIO(base64.b64decode(ref['data'], validate=True))).verify()

    def test_long_safety_response_keeps_actionable_reason(self):
        message = 'provider_submit_rejected: The generated result was blocked by the content safety review. ' + 'x' * 900
        result = site.format_omnia_error_message(message)
        self.assertIn('审核', result)
        self.assertNotIn('详细信息已记录', result)

    def test_poll_connection_failure_retries_same_task(self):
        created = Mock(status_code=200)
        created.json.return_value = {'id': 'existing-task', 'status': 'pending'}
        completed = Mock(status_code=200)
        completed.json.return_value = {'status': 'succeeded', 'assets': [{'url': 'https://example.test/image.png', 'mime_type': 'image/png'}]}
        asset = Mock(content=b'png', headers={'Content-Type': 'image/png'})
        with patch.object(site, 'load_omnia_api_key', return_value='test-key'), \
                patch.object(site.requests, 'post', return_value=created) as post, \
                patch.object(site.requests, 'get', side_effect=[site.requests.ConnectionError('DNS unavailable'), completed, asset]) as get, \
                patch.object(site.time, 'sleep'):
            result = site.call_omnia_media_image_api(site.NANO_BANANA_MODEL, 'test')
        self.assertTrue(result['images'])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(get.call_args_list[0].args[0], get.call_args_list[1].args[0])
        self.assertTrue(get.call_args_list[0].args[0].endswith('/existing-task'))

    def test_error_log_is_persistent_and_redacted(self):
        import tempfile
        from pathlib import Path
        import json
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'errors.jsonl'
            with patch.object(site, 'OPENROUTER_ERROR_LOG_FILE', path), patch.object(site.sys, 'stderr', io.StringIO()) as stderr:
                site.record_background_job_error('task-123', 'omnia_image', 'failed', RuntimeError('Authorization: Bearer private-secret'))
            record = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(record['job_id'], 'task-123')
            self.assertNotIn('private-secret', record['error'])
            self.assertNotIn('private-secret', stderr.getvalue())
        self.assertEqual(site.OPENROUTER_ERROR_LOG_FILE.parent, site.PROJECT_ROOT / 'logs')

if __name__ == '__main__':
    unittest.main()
