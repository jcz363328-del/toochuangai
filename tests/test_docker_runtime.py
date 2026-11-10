import ast
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


class DockerRuntimeTests(unittest.TestCase):
    def test_consolidated_and_legacy_paths_use_configured_root(self):
        namespace = {"__file__": str(ROOT / "secret_settings.py")}
        with patch.dict(os.environ, {"TUCHUANGAI_STORAGE_ROOT": "/container-data"}):
            exec(compile((ROOT / "secret_settings.py").read_text(encoding="utf-8"), "secret_settings.py", "exec"), namespace)
        relocate = namespace["relocate_storage_path"]
        expected = str(Path("/container-data") / "模特视频" / "sample.mp4")
        self.assertEqual(relocate(r"D:\tuchuangai\模特视频\sample.mp4"), expected)
        self.assertEqual(relocate(r"D:\模特视频\sample.mp4"), expected)
        self.assertEqual(relocate("https://example.com/video.mp4"), "https://example.com/video.mp4")
        self.assertEqual(relocate(r"D:\tuchuangai-other\sample.mp4"), r"D:\tuchuangai-other\sample.mp4")

    def test_health_check_does_not_call_application_or_auth(self):
        tree = ast.parse((ROOT / "docker_entrypoint.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "application")
        app = Mock(return_value=[b"application"])
        namespace = {"app": app}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "docker_entrypoint.py", "exec"), namespace)
        response = Mock()
        self.assertEqual(namespace["application"]({"PATH_INFO": "/_container/health"}, response), [b"ok"])
        app.assert_not_called()
        self.assertEqual(namespace["application"]({"PATH_INFO": "/"}, response), [b"application"])
        app.assert_called_once()

    def test_docker_disables_background_jobs_and_uses_separate_port(self):
        compose = (ROOT / "compose.multi.yaml").read_text(encoding="utf-8")
        self.assertIn('TC_BACKGROUND_JOBS: "${TC_BACKGROUND_JOBS:-0}"', compose)
        self.assertIn("${DOCKER_WEB_PORT:-18080}:8000", compose)
        self.assertIn("network_mode: service:web", compose)
        self.assertNotIn("8000:8000", compose)

    def test_container_never_launches_windows_service_scripts(self):
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        checks = {
            "_ensure_business_analysis_api_started": "_is_business_analysis_api_reachable",
            "_ensure_lashforge_watchdog_started": "_is_lashforge_reachable",
            "_ensure_videoclaw_started": "_is_videoclaw_frontend_reachable",
            "_ensure_ads_monitor_api_started": "_is_ads_monitor_api_reachable",
        }
        for function_name, health_name in checks.items():
            with self.subTest(service=function_name):
                function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function_name)
                health = Mock(return_value=False)
                namespace = {"env": Mock(return_value="1"), health_name: health}
                exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
                self.assertFalse(namespace[function_name]())
                health.assert_called_once()

    def test_all_compose_services_have_health_checks_and_internal_video_ports(self):
        import yaml

        services = yaml.safe_load((ROOT / "compose.multi.yaml").read_text(encoding="utf-8"))["services"]
        expected = {"web", "sales-api", "xiaoha", "xiaoha-static", "videoclaw-backend", "videoclaw-frontend", "ads-api"}
        self.assertEqual(expected, set(services))
        for name, service in services.items():
            with self.subTest(service=name):
                self.assertEqual("unless-stopped", service["restart"])
                if name != "web":
                    self.assertIn("healthcheck", service)
                    self.assertNotIn("ports", service)
        self.assertNotIn("18000:", str(services["web"].get("ports")))

    def test_video_backend_proxy_streams_and_denies_non_ai_members(self):
        from flask import Flask, jsonify, request, stream_with_context

        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "video_claw_backend")
        function.decorator_list = []
        app = Flask(__name__)
        upstream = Mock(status_code=200, headers={"Content-Type": "text/event-stream"})
        upstream.iter_content.return_value = iter([b"data: first\n\n", b"data: second\n\n"])
        requests = Mock()
        requests.request.return_value = upstream
        namespace = {"app": app, "request": request, "jsonify": jsonify, "stream_with_context": stream_with_context, "requests": requests, "_VIDEOCLAW_BACKEND_URL": "http://127.0.0.1:18000", "_can_access_ai_workspace": Mock(return_value=True)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
        with app.test_request_context("/ai/video-claw/backend/api/health"):
            response = namespace["video_claw_backend"]("api/health")
            self.assertEqual("no", response.headers["X-Accel-Buffering"])
            self.assertEqual(b"data: first\n\ndata: second\n\n", response.get_data())
            self.assertTrue(requests.request.call_args.kwargs["stream"])
            namespace["_can_access_ai_workspace"].return_value = False
            requests.request.reset_mock()
            denied = namespace["video_claw_backend"]("api/health")
            self.assertEqual(403, denied[1])
            requests.request.assert_not_called()

    def test_single_container_has_only_one_published_port(self):
        import configparser
        import yaml

        compose = yaml.safe_load((ROOT / "compose.single.yaml").read_text(encoding="utf-8"))
        primary = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
        self.assertEqual(compose, primary)
        self.assertEqual(["app"], list(compose["services"]))
        service = compose["services"]["app"]
        self.assertEqual(1, len(service["ports"]))
        config = configparser.ConfigParser()
        config.read(ROOT / "docker/supervisord.conf", encoding="utf-8")
        programs = [name for name in config.sections() if name.startswith("program:")]
        self.assertEqual(9, len(programs))
        for program in programs:
            self.assertTrue(config.getboolean(program, "autorestart"))
            self.assertTrue(config.getboolean(program, "stopasgroup"))
        self.assertIn("/opt/web/bin/python", config.get("program:web", "command"))
        self.assertIn("/opt/xiaoha/bin/python", config.get("program:xiaoha", "command"))
        self.assertIn("/opt/video/bin/python", config.get("program:videoclaw-backend", "command"))

    def test_single_port_xiaoha_urls_keep_gateway_port(self):
        import urllib.parse

        tree = ast.parse((ROOT / "图片/openrouter_image_site.py").read_text(encoding="utf-8"))
        names = {"build_jimeng_static_base_url", "build_history_static_base_url"}
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        namespace = {"os": os, "urllib": urllib, "DEFAULT_PUBLIC_APP_URL": "http://localhost:8000/lashforge", "JIMENG_UPLOAD_ROUTE_PREFIX": "/jimeng_uploads", "HISTORY_STATIC_ROUTE_PREFIX": "/history_images"}
        exec(compile(ast.Module(body=functions, type_ignores=[]), "xiaoha", "exec"), namespace)
        with patch.dict(os.environ, {"TC_SINGLE_PORT": "1", "JIMENG_PUBLIC_PORT": ""}):
            upload = namespace["build_jimeng_static_base_url"]("http://example.com:8000/lashforge", 8502)
            history = namespace["build_history_static_base_url"]("http://example.com:8000/lashforge", 8502)
        self.assertEqual("http://example.com:8000/jimeng_uploads", upload)
        self.assertEqual("http://example.com:8000/history_images", history)

    def test_scheduled_jobs_keep_original_windows_schedule(self):
        from datetime import datetime

        namespace = {"__name__": "scheduler_test"}
        exec(compile((ROOT / "docker/scheduled_jobs.py").read_text(encoding="utf-8"), "scheduler", "exec"), namespace)
        trigger = namespace["next_trigger"]
        self.assertEqual(datetime(2026, 11, 10, 10, 55), trigger("hourly", datetime(2026, 11, 10, 10, 54)))
        self.assertEqual(datetime(2026, 11, 10, 11, 55), trigger("hourly", datetime(2026, 11, 10, 10, 55)))
        self.assertEqual(datetime(2026, 11, 11, 9, 0), trigger("daily", datetime(2026, 11, 10, 9, 1)))
        tree = ast.parse((ROOT / "docker/scheduled_jobs.py").read_text(encoding="utf-8"))
        runner = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_job")
        self.assertIsInstance(runner.body[0], ast.With)


if __name__ == "__main__":
    unittest.main()
