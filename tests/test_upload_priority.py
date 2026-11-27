import contextlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from Department.视觉设计部.xiaoha import openrouter_image_site as site


class UploadPriorityTests(unittest.TestCase):
    def test_reordered_files_survive_reload_without_losing_content(self):
        files = [{'name': f'{i}.png', 'type': 'image/png', 'data': bytes([i])} for i in range(3)]
        with tempfile.TemporaryDirectory() as folder, patch.object(site, 'UPLOAD_CACHE_DIR', Path(folder)), patch.object(site, 'ensure_history_storage'):
            site.save_upload_cache('priority', files, account_name='tester')
            site.reorder_upload_cache_item('priority', 0, 2, account_name='tester')
            self.assertEqual(site.load_upload_cache('priority', account_name='tester'), files[1:] + files[:1])

    def test_move_button_saves_and_refreshes(self):
        controls = [contextlib.nullcontext() for _ in range(3)]
        with (
            patch.object(site, 'render_frame_uploader', return_value=None),
            patch.object(site.st, 'columns', return_value=controls),
            patch.object(site.st, 'button', side_effect=[False, True, False]),
            patch.object(site, 'reorder_upload_cache_item') as reorder,
            patch.object(site, 'reset_upload_widget') as reset,
            patch.object(site.st, 'rerun') as rerun,
        ):
            site.render_uploaded_preview_card({}, 'priority', 1, 'preview', preview_renderer=lambda *args: None, allow_reorder=True, item_count=3)
        reorder.assert_called_once_with('priority', 1, 0)
        reset.assert_called_once_with('priority')
        rerun.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
