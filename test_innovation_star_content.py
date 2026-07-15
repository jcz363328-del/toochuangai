import atexit
import io
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


BOOTSTRAP_DIR = tempfile.mkdtemp(prefix='innovation_star_bootstrap_')
atexit.register(shutil.rmtree, BOOTSTRAP_DIR, True)
os.environ['INNOVATION_UPLOAD_FOLDER'] = os.path.join(BOOTSTRAP_DIR, 'uploads')
os.environ['INNOVATION_STAR_MEDIA_FOLDER'] = os.path.join(BOOTSTRAP_DIR, 'star-media')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'innovation'))

import web_app as innovation_web_app


class InnovationStarContentTests(unittest.TestCase):
    def setUp(self):
        self.media_dir = tempfile.mkdtemp(prefix='innovation_star_media_')
        self.addCleanup(shutil.rmtree, self.media_dir, True)
        self.original_media_dir = innovation_web_app.INNOVATION_STAR_MEDIA_FOLDER
        innovation_web_app.INNOVATION_STAR_MEDIA_FOLDER = self.media_dir
        self.addCleanup(
            setattr,
            innovation_web_app,
            'INNOVATION_STAR_MEDIA_FOLDER',
            self.original_media_dir,
        )
        innovation_web_app.app.config.update(TESTING=True, SECRET_KEY='test-secret')
        self.client = innovation_web_app.app.test_client()

    def login(self, name, user_id='ou_test'):
        with self.client.session_transaction() as user_session:
            user_session['feishu_user_id'] = user_id
            user_session['feishu_user_name'] = name

    def test_non_editor_is_rejected(self):
        self.login('普通同事')
        with patch.object(
            innovation_web_app.permission_manager,
            'get_user_departments',
            return_value=[{'name': '运营一部', 'status': 'active'}],
        ), patch.object(innovation_web_app, 'dui_db') as write_db:
            response = self.client.post(
                '/api/innovation_star_content',
                data={'content_type': 'share', 'copy': '不应写入'},
            )

        self.assertEqual(response.status_code, 403)
        write_db.assert_not_called()

    def test_ai_department_can_add_image_and_copy(self):
        self.login('AI同事')
        statements = []
        with patch.object(
            innovation_web_app.permission_manager,
            'get_user_departments',
            return_value=[{'name': 'AI部', 'status': 'active'}],
        ), patch.object(innovation_web_app, 'dui_db', side_effect=statements.append):
            response = self.client.post(
                '/api/innovation_star_content',
                data={
                    'content_type': 'share',
                    'copy': "案例's 进度 100%",
                    'images': (io.BytesIO(b'image-content'), 'case.png'),
                },
                content_type='multipart/form-data',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['section'], 'share')
        self.assertEqual(len(os.listdir(self.media_dir)), 1)
        self.assertIn('创新新享', statements[0])
        self.assertIn("案例''s 进度 100%%", statements[0])
        self.assertIn(self.media_dir, statements[0])

    def test_named_hr_editor_can_submit_with_all_optional_fields_empty(self):
        self.login('韩雅俊（人力行政部）')
        statements = []
        with patch.object(
            innovation_web_app.permission_manager,
            'get_user_departments',
            side_effect=AssertionError('named editor should not need department lookup'),
        ), patch.object(innovation_web_app, 'dui_db', side_effect=statements.append):
            response = self.client.post(
                '/api/innovation_star_content',
                data={'content_type': 'talk'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('创新新说', statements[0])
        self.assertGreaterEqual(statements[0].count('NULL'), 3)

    def test_invalid_video_removes_image_saved_earlier(self):
        self.login('AI同事')
        with patch.object(
            innovation_web_app.permission_manager,
            'get_user_departments',
            return_value=[{'name': 'AI部', 'status': 'active'}],
        ), patch.object(innovation_web_app, 'dui_db') as write_db:
            response = self.client.post(
                '/api/innovation_star_content',
                data={
                    'content_type': 'talk',
                    'images': (io.BytesIO(b'image-content'), 'case.jpg'),
                    'videos': (io.BytesIO(b'bad-video'), 'case.exe'),
                },
                content_type='multipart/form-data',
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(os.listdir(self.media_dir), [])
        write_db.assert_not_called()

    def test_database_failure_removes_uploaded_files(self):
        self.login('AI同事')
        with patch.object(
            innovation_web_app.permission_manager,
            'get_user_departments',
            return_value=[{'name': 'AI部', 'status': 'active'}],
        ), patch.object(innovation_web_app, 'dui_db', side_effect=RuntimeError('db unavailable')):
            response = self.client.post(
                '/api/innovation_star_content',
                data={
                    'content_type': 'share',
                    'videos': (io.BytesIO(b'video-content'), 'case.mp4'),
                },
                content_type='multipart/form-data',
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(os.listdir(self.media_dir), [])

    def test_rows_are_grouped_and_media_paths_are_normalized(self):
        rows = [
            (
                7,
                r'D:\tuchuangai\创新星主场\one.jpg;D:\tuchuangai\创新星主场\two.png',
                r'D:\tuchuangai\创新星主场\clip.mp4',
                datetime(2026, 7, 14, 10, 30),
                '创新新说',
                '复盘文案',
                '韩雅俊',
            )
        ]
        with patch.object(innovation_web_app, 'sf_db', return_value=rows):
            grouped = innovation_web_app._innovation_star_items()

        self.assertEqual(grouped['share'], [])
        self.assertEqual(grouped['talk'][0]['images'], ['one.jpg', 'two.png'])
        self.assertEqual(grouped['talk'][0]['videos'], ['clip.mp4'])
        self.assertEqual(grouped['talk'][0]['created_at'], '2026-07-14 10:30')

    def test_non_editor_cannot_delete_content(self):
        self.login('普通同事')
        with patch.object(
            innovation_web_app.permission_manager,
            'get_user_departments',
            return_value=[{'name': '运营一部', 'status': 'active'}],
        ), patch.object(innovation_web_app, 'sf_db') as read_db, patch.object(
            innovation_web_app,
            'dui_db',
        ) as write_db:
            response = self.client.delete('/api/innovation_star_content/7')

        self.assertEqual(response.status_code, 403)
        read_db.assert_not_called()
        write_db.assert_not_called()

    def test_ai_department_can_delete_record_and_its_media(self):
        self.login('AI同事')
        image_path = Path(self.media_dir, 'delete-me.jpg')
        video_path = Path(self.media_dir, 'delete-me.mp4')
        image_path.write_bytes(b'image')
        video_path.write_bytes(b'video')
        statements = []
        with patch.object(
            innovation_web_app.permission_manager,
            'get_user_departments',
            return_value=[{'name': 'AI部', 'status': 'active'}],
        ), patch.object(
            innovation_web_app,
            'sf_db',
            return_value=[(str(image_path), str(video_path), '创新新说')],
        ), patch.object(innovation_web_app, 'dui_db', side_effect=statements.append):
            response = self.client.delete('/api/innovation_star_content/7')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['section'], 'talk')
        self.assertTrue(response.get_json()['file_cleanup_complete'])
        self.assertFalse(image_path.exists())
        self.assertFalse(video_path.exists())
        self.assertIn('DELETE FROM chuangxinxing WHERE ID = 7', statements[0])

    def test_database_delete_failure_keeps_media(self):
        self.login('AI同事')
        image_path = Path(self.media_dir, 'keep-me.jpg')
        image_path.write_bytes(b'image')
        with patch.object(
            innovation_web_app.permission_manager,
            'get_user_departments',
            return_value=[{'name': 'AI部', 'status': 'active'}],
        ), patch.object(
            innovation_web_app,
            'sf_db',
            return_value=[(str(image_path), None, '创新新享')],
        ), patch.object(innovation_web_app, 'dui_db', side_effect=RuntimeError('db unavailable')):
            response = self.client.delete('/api/innovation_star_content/8')

        self.assertEqual(response.status_code, 500)
        self.assertTrue(image_path.exists())

    def test_delete_never_removes_file_outside_media_folder(self):
        self.login('AI同事')
        outside_dir = tempfile.mkdtemp(prefix='innovation_star_outside_')
        self.addCleanup(shutil.rmtree, outside_dir, True)
        outside_path = Path(outside_dir, 'outside.jpg')
        outside_path.write_bytes(b'outside')
        with patch.object(
            innovation_web_app.permission_manager,
            'get_user_departments',
            return_value=[{'name': 'AI部', 'status': 'active'}],
        ), patch.object(
            innovation_web_app,
            'sf_db',
            return_value=[(str(outside_path), None, '创新新享')],
        ), patch.object(innovation_web_app, 'dui_db'):
            response = self.client.delete('/api/innovation_star_content/9')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(outside_path.exists())

    def test_delete_returns_not_found_for_missing_record(self):
        self.login('AI同事')
        with patch.object(
            innovation_web_app.permission_manager,
            'get_user_departments',
            return_value=[{'name': 'AI部', 'status': 'active'}],
        ), patch.object(innovation_web_app, 'sf_db', return_value=[]), patch.object(
            innovation_web_app,
            'dui_db',
        ) as write_db:
            response = self.client.delete('/api/innovation_star_content/404')

        self.assertEqual(response.status_code, 404)
        write_db.assert_not_called()


if __name__ == '__main__':
    unittest.main()
