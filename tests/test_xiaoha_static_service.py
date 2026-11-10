import unittest
from unittest.mock import Mock, patch

from 图片 import openrouter_image_site as site


class XiaohaStaticServiceTests(unittest.TestCase):
    def test_managed_ui_reuses_service_and_recovers(self):
        response = Mock()
        response.json.return_value = {"service": "xiaoha-static", "canvas_ready": True}
        with patch.dict(site.os.environ, {"TC_SINGLE_PORT": "1"}), patch.object(site, "load_runtime_settings", return_value={}), patch.object(site.requests, "get", side_effect=[site.requests.ConnectionError("offline"), response]), patch.object(site, "start_jimeng_static_server") as start:
            self.assertFalse(site.ensure_jimeng_static_server()["started"])
            self.assertTrue(site.ensure_jimeng_static_server()["started"])
        start.assert_not_called()

    def test_unrelated_service_is_rejected(self):
        response = Mock()
        response.json.return_value = {"service": "other"}
        with patch.dict(site.os.environ, {"TC_SINGLE_PORT": "1"}), patch.object(site, "load_runtime_settings", return_value={}), patch.object(site.requests, "get", return_value=response):
            self.assertFalse(site.ensure_jimeng_static_server()["started"])

    def test_owner_starts_server(self):
        with patch.dict(site.os.environ, {"TC_SINGLE_PORT": "1"}), patch.object(site, "start_jimeng_static_server", return_value={"started": True}) as start:
            self.assertTrue(site.ensure_jimeng_static_server(owner=True)["started"])
        start.assert_called_once()
