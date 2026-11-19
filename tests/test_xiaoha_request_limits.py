import inspect
import multiprocessing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "图片"))
import request_limits as limits


def _process_request(path, running, maximum, lock, start, ready):
    limiter = limits.RequestLimiter(path, group_limits={"ark": 2}, poll_interval=0.01)
    ready.put(True)
    start.wait(10)
    with limiter.slot("ark"):
        with lock:
            running.value += 1
            maximum.value = max(maximum.value, running.value)
        time.sleep(0.12)
        with lock:
            running.value -= 1


def _crashed_request(path, ready):
    limiter = limits.RequestLimiter(path, lease_seconds=0.5, poll_interval=0.01)
    with limiter.slot("omnia_image"):
        ready.set()
        os._exit(0)


class RequestLimiterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "requests.sqlite3"
        self.limiter = self.make_limiter()

    def make_limiter(self, **kwargs):
        return limits.RequestLimiter(self.path, poll_interval=0.01, **kwargs)

    def wait_for(self, predicate, timeout=3):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for concurrency state")

    def test_separate_processes_share_capacity(self):
        ctx = multiprocessing.get_context("spawn")
        running, maximum = ctx.Value("i", 0), ctx.Value("i", 0)
        lock, start = ctx.Lock(), ctx.Event()
        ready = ctx.Queue()
        processes = [ctx.Process(target=_process_request,
                                 args=(str(self.path), running, maximum, lock, start, ready))
                     for _ in range(6)]
        for process in processes:
            process.start()
        for _ in processes:
            self.assertTrue(ready.get(timeout=15))
        start.set()
        for process in processes:
            process.join(15)
            if process.is_alive():
                process.terminate()
                process.join()
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(maximum.value, 2)
        self.assertEqual(self.limiter.snapshot()["active"], 0)

    def test_fifo_between_threads_and_separate_manager_instances(self):
        order, failures = [], []

        def request(number):
            try:
                with self.make_limiter().slot("omnia_image"):
                    order.append(number)
                    time.sleep(0.03)
            except BaseException as exc:
                failures.append(exc)

        with self.limiter.slot("omnia_image"):
            threads = []
            for index in range(4):
                thread = threading.Thread(target=request, args=(index,))
                thread.start()
                threads.append(thread)
                self.wait_for(lambda: self.limiter.snapshot()["waiting"] == index + 1)
        for thread in threads:
            thread.join(3)
        self.assertEqual(failures, [])
        self.assertEqual(order, [0, 1, 2, 3])

    def test_provider_limit_and_download_isolation(self):
        limiter = self.make_limiter(model_limit=2, queue_timeout=0.06)
        with limiter.slot("omnia_text"), limiter.slot("omnia_text"):
            with self.assertRaises(limits.RequestQueueTimeout):
                with limiter.slot("omnia_image"):
                    self.fail("Omnia provider cap was bypassed")
            with self.assertRaises(limits.RequestQueueTimeout):
                with limiter.slot("ark"):
                    self.fail("Global model cap was bypassed")
            with limiter.slot("download"):
                state = limiter.snapshot()
                self.assertEqual(state["active"], 3)
                self.assertEqual(state["groups"]["download"]["active"], 1)

    def test_omnia_provider_limit_is_configurable_and_bounded(self):
        for value, expected in (("4", 4), ("99", 16), ("0", 1), ("invalid", 2)):
            with self.subTest(value=value), patch.dict(os.environ, {"XIAOHA_OMNIA_CONCURRENCY": value}):
                self.assertEqual(self.make_limiter().provider_limit, expected)
                self.assertEqual(self.make_limiter(provider_limit=3).provider_limit, 3)

    def test_blocked_provider_does_not_stall_other_provider(self):
        order = []

        def wait_for_image():
            with self.limiter.slot("omnia_image"):
                order.append("image")

        with self.limiter.slot("omnia_image"):
            thread = threading.Thread(target=wait_for_image)
            thread.start()
            self.wait_for(lambda: self.limiter.snapshot()["waiting"] == 1)
            with self.limiter.slot("ark"):
                order.append("ark")
        thread.join(3)
        self.assertEqual(order, ["ark", "image"])

    def test_queue_limit_and_timeout_do_not_submit(self):
        limiter = self.make_limiter(max_waiting=1, queue_timeout=0.08)
        failure = []

        def waiting_request():
            try:
                with limiter.slot("omnia_image"):
                    failure.append("unexpected admission")
            except limits.RequestQueueTimeout as exc:
                failure.append(str(exc))

        with limiter.slot("omnia_image"):
            thread = threading.Thread(target=waiting_request)
            thread.start()
            self.wait_for(lambda: limiter.snapshot()["waiting"] == 1)
            with self.assertRaisesRegex(limits.RequestQueueFull, "尚未提交"):
                with limiter.slot("omnia_image"):
                    self.fail("Full queue admitted a request")
            thread.join(2)
            self.assertEqual(limiter.snapshot()["waiting"], 0)
        self.assertEqual(len(failure), 1)
        self.assertIn("尚未提交", failure[0])

    def test_normal_exception_releases_slot(self):
        with self.assertRaisesRegex(ValueError, "bad request"):
            with self.limiter.slot("omnia_image"):
                raise ValueError("bad request")
        self.assertEqual(self.limiter.snapshot()["active"], 0)
        with self.limiter.slot("omnia_image"):
            self.assertEqual(self.limiter.snapshot()["active"], 1)

    def test_cleanup_failure_preserves_success_and_lease_expires(self):
        limiter = self.make_limiter(lease_seconds=0.4)

        @limits.limited_request("omnia_image")
        def request():
            return "completed image"

        with patch.object(limits, "get_request_limiter", return_value=limiter), \
                patch.object(limiter, "_release", side_effect=sqlite3.OperationalError("unavailable")):
            with self.assertLogs(limits.__name__, level="WARNING") as logs:
                self.assertEqual(request(), "completed image")
        self.assertTrue(any("cleanup failed" in line for line in logs.output))
        self.wait_for(lambda: limiter.snapshot()["active"] == 0)

    def test_cleanup_failure_preserves_original_provider_error(self):
        with patch.object(self.limiter, "_release", side_effect=sqlite3.OperationalError("unavailable")):
            with self.assertLogs(limits.__name__, level="WARNING"):
                with self.assertRaisesRegex(ValueError, "original provider error"):
                    with self.limiter.slot("omnia_image"):
                        raise ValueError("original provider error")

    def test_unknown_outcome_retains_capacity_temporarily(self):
        limiter = self.make_limiter(uncertain_cooldown=1.0, queue_timeout=0.05)
        with self.assertRaises(RuntimeError):
            with limiter.slot("omnia_image"):
                raise RuntimeError("provider_submit_uncertain: 未自动重新提交")
        self.assertEqual(limiter.snapshot()["retained"], 1)
        with self.assertRaises(limits.RequestQueueTimeout):
            with limiter.slot("omnia_image"):
                self.fail("Uncertain task released capacity early")
        self.wait_for(lambda: limiter.snapshot()["retained"] == 0)
        with limiter.slot("omnia_image"):
            self.assertEqual(limiter.snapshot()["retained"], 0)

    def test_429_cooldown_is_shared_across_omnia_groups(self):
        limiter = self.make_limiter(rate_limit_cooldown=1.0, queue_timeout=0.04)
        with self.assertRaises(RuntimeError):
            with limiter.slot("omnia_text"):
                raise RuntimeError("HTTP 429 Too Many Requests")
        self.assertEqual(limiter.snapshot()["active"], 0)
        with self.assertRaises(limits.RequestQueueTimeout):
            with limiter.slot("omnia_image"):
                self.fail("Provider cooldown was bypassed")
        with limiter.slot("ark"):
            pass
        self.wait_for(lambda: not limiter.snapshot()["cooldowns"])
        with limiter.slot("omnia_image"):
            pass

    def test_drain_persists_but_existing_waiter_finishes(self):
        finished = threading.Event()

        def existing_request():
            with self.limiter.slot("omnia_image"):
                finished.set()

        with self.limiter.slot("omnia_image"):
            thread = threading.Thread(target=existing_request)
            thread.start()
            self.wait_for(lambda: self.limiter.snapshot()["waiting"] == 1)
            self.limiter.drain(True)
            other = self.make_limiter()
            with self.assertRaisesRegex(limits.RequestQueueFull, "尚未提交"):
                other.ensure_accepting()
        thread.join(3)
        self.assertTrue(finished.is_set())
        with self.assertRaisesRegex(limits.RequestQueueFull, "维护"):
            with other.slot("download"):
                self.fail("Draining admitted a new request")
        other.drain(False)
        self.limiter.ensure_accepting()

    def test_drain_allows_admitted_task_nested_download(self):
        with self.limiter.slot("omnia_image"):
            self.limiter.drain(True)
            with self.limiter.slot("download"):
                self.assertEqual(self.limiter.snapshot()["active"], 2)
        with self.assertRaisesRegex(limits.RequestQueueFull, "尚未提交"):
            with self.limiter.slot("omnia_image"):
                self.fail("A new outer task bypassed drain")

    def test_nested_same_group_still_consumes_capacity(self):
        limiter = self.make_limiter(queue_timeout=0.05)
        with limiter.slot("omnia_image"):
            with self.assertRaises(limits.RequestQueueTimeout):
                with limiter.slot("omnia_image"):
                    self.fail("Nested request bypassed group capacity")

    def test_accepted_job_completes_later_stages_after_drain(self):
        with patch.object(limits, "get_request_limiter", return_value=self.limiter):
            with limits.admitted_job():
                with self.limiter.slot("omnia_image"):
                    pass
                self.limiter.drain(True)
                # The first provider stage has finished, but the accepted job
                # must be able to start its next provider/download stages.
                with self.limiter.slot("omnia_text"), self.limiter.slot("download"):
                    self.assertEqual(self.limiter.snapshot()["active"], 2)
            with self.assertRaisesRegex(limits.RequestQueueFull, "尚未提交"):
                with limits.admitted_job():
                    self.fail("A new job bypassed drain")
        with self.assertRaises(limits.RequestQueueFull):
            with self.limiter.slot("download"):
                self.fail("Accepted job context leaked")

    def test_already_queued_job_can_enter_after_drain(self):
        self.limiter.ensure_accepting()  # Admission at enqueue time.
        self.limiter.drain(True)
        with patch.object(limits, "get_request_limiter", return_value=self.limiter):
            with limits.admitted_job(existing=True):
                with self.limiter.slot("omnia_image"):
                    self.assertEqual(self.limiter.snapshot()["active"], 1)
                with self.limiter.slot("download"):
                    pass
            with self.assertRaises(limits.RequestQueueFull):
                with limits.admitted_job():
                    self.fail("A new job bypassed drain")

    def test_public_cooldown_blocks_other_managers_and_does_not_shorten(self):
        self.limiter.cooldown("ark", seconds=1)
        initial = self.limiter.snapshot()["cooldowns"]["group:ark"]
        self.limiter.cooldown("ark", seconds=0)
        self.assertEqual(self.limiter.snapshot()["cooldowns"]["group:ark"], initial)
        other = self.make_limiter(queue_timeout=0.05)
        with self.assertRaises(limits.RequestQueueTimeout):
            with other.slot("ark"):
                self.fail("A separate manager bypassed shared cooldown")
        with other.slot("jimeng"):
            pass

    def test_crashed_process_lease_is_reclaimed(self):
        ctx = multiprocessing.get_context("spawn")
        ready = ctx.Event()
        process = ctx.Process(target=_crashed_request, args=(str(self.path), ready))
        process.start()
        self.assertTrue(ready.wait(10))
        process.join(3)
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(self.limiter.snapshot()["active"], 1)
        with self.limiter.slot("omnia_image"):
            self.assertEqual(self.limiter.snapshot()["active"], 1)
        self.assertEqual(self.limiter.snapshot()["active"], 0)

    def test_heartbeat_keeps_long_task_alive(self):
        limiter = self.make_limiter(lease_seconds=0.18, heartbeat_interval=0.04,
                                    queue_timeout=0.04)
        with limiter.slot("omnia_image"):
            time.sleep(0.4)
            self.assertEqual(self.make_limiter().snapshot()["active"], 1)
            with self.assertRaises(limits.RequestQueueTimeout):
                with limiter.slot("omnia_image"):
                    self.fail("Healthy long-running lease expired")

    def test_heartbeat_logs_transient_database_failure_and_retries(self):
        stop = Mock()
        stop.wait.side_effect = [False, False, True]
        connection = self.limiter._connect()
        with patch.object(self.limiter, "_connect", side_effect=[
                sqlite3.OperationalError("busy"), connection]) as connect:
            with self.assertLogs(limits.__name__, level="WARNING") as logs:
                self.limiter._heartbeat("test-missing-ticket", stop)
        self.assertEqual(connect.call_count, 2)
        self.assertTrue(any("heartbeat failed" in line for line in logs.output))

    def test_context_callback_and_decorator_preserve_signature(self):
        callbacks = []

        @limits.limited_request("omnia_image")
        def request(prompt, *, size="1K"):
            return prompt, size

        with patch.object(limits, "get_request_limiter", return_value=self.limiter):
            with limits.request_wait_callback(lambda group, ahead: callbacks.append((group, ahead))):
                self.assertEqual(request("hello", size="2K"), ("hello", "2K"))
            request("second")
        self.assertEqual(callbacks, [("omnia_image", 0)])
        self.assertEqual(str(inspect.signature(request)), "(prompt, *, size='1K')")
        self.assertEqual(request.__name__, "request")

    def test_wait_callback_reports_queue_and_admission(self):
        callbacks = []

        def waiter():
            with self.limiter.slot("omnia_image", on_wait=lambda group, ahead:
                                   callbacks.append((group, ahead))):
                pass

        with self.limiter.slot("omnia_image"):
            thread = threading.Thread(target=waiter)
            thread.start()
            self.wait_for(lambda: bool(callbacks))
            self.assertEqual(callbacks, [("omnia_image", 1)])
        thread.join(3)
        self.assertEqual(callbacks, [("omnia_image", 1), ("omnia_image", 0)])


if __name__ == "__main__":
    unittest.main()
