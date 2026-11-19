import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from 图片 import openrouter_image_site as site
from 图片.request_limits import RequestLimiter


class ManualElementQueueTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.limiter = RequestLimiter(Path(folder) / "limits.sqlite3", poll_interval=.01)
        self.enterContext(patch("图片.request_limits.get_request_limiter", return_value=self.limiter))
        self.enterContext(patch.object(site, "get_request_limiter", return_value=self.limiter))
        with patch.dict(os.environ, {"XIAOHA_JOB_WORKERS": "2", "XIAOHA_ACCOUNT_QUEUE_LIMIT": "8"}):
            self.runtime = site.TaskRuntime()
        self.addCleanup(self.runtime.shutdown)
        self.state = {"auth_username": "alice", "analysis": {"template_signature": "template", "elements": []}}
        self.enterContext(patch.object(site.st, "session_state", self.state))
        self.enterContext(patch.object(site, "get_task_runtime", return_value=self.runtime))
        self.enterContext(patch.object(site, "prepare_uploaded_input", side_effect=lambda value: value))
        self.gate = threading.Event()
        self.addCleanup(self.gate.set)
        self.started = threading.Event()
        self.detected = {"name": "product", "regions": [[0, 0, 10, 10]]}

    def block_account(self):
        def block():
            self.started.set()
            self.gate.wait(3)
        self.runtime.submit_generation_job("alice", "existing", block)
        self.assertTrue(self.started.wait(1))

    def submit(self):
        return site.submit_main_image_a_plus_manual_element_job(
            "manual", {"data": b"image"}, "template", (5, 5), [])

    def test_manual_job_shares_account_fifo_and_completes_through_maintenance(self):
        self.block_account()

        def recognize(*args):
            with self.limiter.slot("omnia_text"):
                return self.detected

        with patch.object(site, "analyze_main_image_a_plus_element_at_point", side_effect=recognize) as analyze:
            state = self.submit()
            self.assertEqual(state["status"], "queued")
            self.assertEqual(self.runtime.job_queue_keys[state["job_id"]], "alice")
            synced = site.sync_main_image_a_plus_manual_element_job("manual", "analysis", "template")
            self.assertEqual(synced["status"], "queued")
            self.assertEqual(synced["progress"], 1)
            self.assertIn("1 个任务", synced["stage"])
            self.assertEqual(self.submit()["job_id"], state["job_id"])
            self.assertEqual(len(self.runtime.futures), 2)
            analyze.assert_not_called()
            self.limiter.drain(True)
            self.gate.set()
            self.runtime.futures[state["job_id"]].result(3)
            synced = site.sync_main_image_a_plus_manual_element_job("manual", "analysis", "template")
        self.assertEqual(synced["status"], "completed")
        self.assertEqual(self.state["analysis"]["elements"][0]["name"], "product")
        analyze.assert_called_once()

    def test_full_account_queue_returns_error_without_orphan_future_or_progress(self):
        self.runtime.max_account_jobs = 1
        self.block_account()
        state = self.submit()
        self.assertEqual(state["status"], "error")
        self.assertIn("队列已满", state["error"])
        self.assertNotIn(state["job_id"], self.runtime.futures)
        self.assertNotIn(state["job_id"], self.runtime.progress)
        self.assertEqual(len(self.runtime.futures), 1)

    def test_canceling_a_queued_manual_job_never_runs_recognition(self):
        self.block_account()
        with patch.object(site, "analyze_main_image_a_plus_element_at_point", return_value=self.detected) as analyze:
            state = self.submit()
            self.assertTrue(self.runtime.futures[state["job_id"]].cancel())
            synced = site.sync_main_image_a_plus_manual_element_job("manual", "analysis", "template")
            self.assertEqual(synced["status"], "error")
            self.assertIn("未向模型提交", synced["error"])
            self.gate.set()
            self.runtime.shutdown()
        analyze.assert_not_called()
        self.assertEqual(self.state["analysis"]["elements"], [])

    def test_maintenance_rejects_new_manual_work_before_enqueuing(self):
        self.limiter.drain(True)
        state = self.submit()
        self.assertEqual(state["status"], "error")
        self.assertIn("维护", state["error"])
        self.assertEqual(self.runtime.futures, {})
        self.assertEqual(self.runtime.progress, {})


if __name__ == "__main__":
    unittest.main()
