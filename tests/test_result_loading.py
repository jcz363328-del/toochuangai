import unittest
from unittest.mock import patch
from 图片 import openrouter_image_site as site


class ResultLoadingTests(unittest.TestCase):
    def test_active_job_replaces_old_result_in_preview(self):
        for status in ('queued', 'running'):
            with self.subTest(status=status), patch.object(site.st, 'session_state', {
                'background_jobs': {'poster_fusion': {'status': status}},
            }), patch.object(site, 'render_running_job_status') as loading, \
                 patch.object(site, 'render_zoomable_image_gallery') as gallery:
                site.render_result_preview(['old-result'], show_title=False, feature_key='poster_fusion')
                loading.assert_called_once_with('poster_fusion', in_result=True)
                gallery.assert_not_called()

    def test_completion_displays_result_in_same_preview(self):
        with patch.object(site.st, 'session_state', {
            'background_jobs': {'poster_fusion': {'status': 'completed'}},
        }), patch.object(site, 'render_running_job_status') as loading, \
             patch.object(site, 'build_result_download_sources', return_value=['new-result']), \
             patch.object(site, 'render_zoomable_image_gallery') as gallery:
            site.render_result_preview(['new-result'], show_title=False, feature_key='poster_fusion')
            loading.assert_not_called()
            self.assertEqual(gallery.call_args.args[0], ['new-result'])

    def test_other_feature_job_does_not_block_current_result(self):
        with patch.object(site.st, 'session_state', {
            'selected_feature_key': 'hd_batch',
            'background_jobs': {'poster_fusion': {'status': 'running'}},
        }):
            self.assertFalse(site.render_result_loading())

    def test_header_polling_has_no_visible_banner(self):
        with patch.object(site.st, 'session_state', {
            'background_jobs': {'hd_batch': {'status': 'running'}},
        }), patch.object(site, 'sync_background_jobs'), patch.object(site.st, 'markdown') as markup:
            site.render_running_job_status.__wrapped__('hd_batch')
            markup.assert_not_called()

