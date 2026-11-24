import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from 图片 import canvas_a_plus as node_api
from 图片 import openrouter_image_site as site


class CanvasAPlusNodeTests(unittest.TestCase):
    def test_every_a_plus_node_reuses_its_job_and_preserves_input_order(self):
        for key in node_api.FEATURE_KEYS:
            feature = site.get_feature_by_key(key)
            files = [{'name': str(i), 'data': b'test'} for i in range(max(1, feature['min_images']))]
            with self.subTest(key=key), patch.object(site, 'run_feature_job', return_value={'images': ['one', 'two']}) as run, \
                 patch.object(site, 'get_uploaded_input_dimensions', return_value=(1464, 2400)), \
                 patch.object(site, 'analyze_hero_style_reverse_reference', return_value={'prompt': 'analyzed'}):
                result = node_api.run_node(site, feature, files, 'design notes', 'tester')
                context = run.call_args.args[0]
                self.assertEqual(context['uploaded_files'], files)
                self.assertEqual(context['account_name'], 'tester')
                self.assertEqual(result['images'], ['one', 'two'])
                self.assertEqual(context['max_output_images'], 1)
                if key == 'a_plus_hero_style_reverse':
                    self.assertEqual(context['prompt'], 'analyzed')

    def test_invalid_reference_counts_do_not_submit_billable_work(self):
        for key, count in [('amazon_to_walmart_a_plus', 2), ('main_image_a_plus', 0),
                           ('a_plus_style_model_replace', 1), ('a_plus_first_screen_selling_points', 1)]:
            with self.subTest(key=key), patch.object(site, 'run_feature_job') as run:
                with self.assertRaises(ValueError):
                    node_api.run_node(site, site.get_feature_by_key(key), [{}] * count, '', 'tester')
                run.assert_not_called()

    def test_authenticated_handler_returns_every_output_image(self):
        payload = {'feature': 'amazon_to_walmart_a_plus', 'images': ['data:image/png;base64,eA==']}
        raw = json.dumps(payload).encode()
        handler = SimpleNamespace(headers={'Content-Length': str(len(raw))}, rfile=io.BytesIO(raw), send_json=Mock())
        query = 'auth_user=tester&auth_token=' + site.build_auth_token('tester')
        with patch.object(node_api, 'run_node', return_value={'images': ['one', 'two', 'three', 'four']}), \
             patch.object(site, 'load_image_bytes_from_url', side_effect=lambda url: (url.encode(), 'image/png')):
            site.JimengStaticRequestHandler.serve_infinite_canvas_image_feature(handler, query)
        response = handler.send_json.call_args.args[0]
        self.assertTrue(response['success'])
        self.assertEqual(len(response['images']), 4)

    def test_psd_download_rejects_path_traversal_or_invalid_token(self):
        handler = SimpleNamespace(send_json=Mock())
        for query in ['file=../../secret.psd', 'auth_user=tester&file=' + 'a' * 32 + '.psd']:
            node_api.serve_psd(handler, site, query)
            self.assertEqual(handler.send_json.call_args.kwargs['status'], 403)

    def test_psd_download_checks_owner_and_serves_saved_file(self):
        import tempfile
        from pathlib import Path
        from urllib.parse import urlsplit
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / 'original.psd'
            original.write_bytes(b'8BPS-test')
            with patch.object(site, 'ensure_feature_output_dir', return_value=Path(folder)):
                url = node_api.prepare_psd_download(site, {'psd_path': str(original)}, 'tester')
                handler = SimpleNamespace(send_json=Mock(), send_response=Mock(), send_header=Mock(), end_headers=Mock(), wfile=io.BytesIO())
                node_api.serve_psd(handler, site, urlsplit(url).query)
                self.assertEqual(handler.wfile.getvalue(), b'8BPS-test')
                handler.send_response.assert_called_once_with(200)
                node_api.serve_psd(handler, site, urlsplit(url).query.replace('auth_user=tester', 'auth_user=other'))
                self.assertEqual(handler.send_json.call_args.kwargs['status'], 403)

    def test_workspace_url_is_scoped_without_changing_normal_canvas(self):
        self.assertIn('workspace=a_plus', site.build_infinite_canvas_url('http://localhost:8000', 8502, 'tester', 'a_plus'))
        self.assertNotIn('workspace=', site.build_infinite_canvas_url('http://localhost:8000', 8502, 'tester'))


if __name__ == '__main__':
    unittest.main()
