from __future__ import annotations

import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from 图片 import openrouter_image_site as site


class TaskRuntimeConcurrencyTests(unittest.TestCase):
    def runtime(self, **settings):
        values = {"XIAOHA_JOB_WORKERS": "2", "XIAOHA_JOB_QUEUE_LIMIT": "64", "XIAOHA_ACCOUNT_QUEUE_LIMIT": "8"}
        values.update({k: str(v) for k, v in settings.items()})
        with patch.dict(os.environ, values):
            runtime = site.TaskRuntime()
        self.addCleanup(runtime.shutdown)
        return runtime

    def test_global_workers_are_bounded_across_many_accounts(self):
        runtime = self.runtime()
        gate = threading.Event()
        started = threading.Event()
        guard = threading.Lock()
        counts = {"active": 0, "peak": 0, "started": 0}

        def work():
            with guard:
                counts["active"] += 1
                counts["started"] += 1
                counts["peak"] = max(counts["peak"], counts["active"])
                if counts["started"] == 2:
                    started.set()
            gate.wait(3)
            with guard:
                counts["active"] -= 1

        try:
            futures = [runtime.submit_generation_job(str(i), str(i), work) for i in range(12)]
            self.assertTrue(started.wait(1))
            self.assertEqual(counts["started"], 2)
            self.assertEqual(runtime.get_generation_queue_state("2")["state"], "queued")
        finally:
            gate.set()
        for future in futures:
            future.result(3)
        self.assertEqual(counts["peak"], 2)

    def test_fifo_accounts_are_fair_and_duplicates_and_canceled_jobs_never_run(self):
        runtime = self.runtime(XIAOHA_JOB_WORKERS=1)
        gate = threading.Event()
        started = threading.Event()
        order = []

        def work(name):
            order.append(name)
            if name == "a1":
                started.set()
                gate.wait(3)
            return name

        try:
            first = runtime.submit_generation_job("a", "a1", work, "a1")
            self.assertTrue(started.wait(1))
            second = runtime.submit_generation_job("a", "a2", work, "a2")
            cancel = runtime.submit_generation_job("a", "cancel", work, "cancel")
            self.assertTrue(cancel.cancel())
            third = runtime.submit_generation_job("a", "a3", work, "a3")
            other = runtime.submit_generation_job("b", "b1", work, "b1")
            duplicate = runtime.submit_generation_job("b", "a2", work, "bad-duplicate")
            self.assertIs(duplicate, second)
        finally:
            gate.set()
        for future in (first, second, third, other):
            future.result(3)
        self.assertEqual(order, ["a1", "b1", "a2", "a3"])
        self.assertEqual(runtime.get_generation_queue_state("cancel")["state"], "canceled")

    def test_concurrent_duplicate_job_id_executes_once(self):
        runtime = self.runtime()
        barrier = threading.Barrier(12)
        calls = []

        def submit(_):
            barrier.wait()
            return runtime.submit_generation_job("a", "same-id", lambda: calls.append("called"))

        with ThreadPoolExecutor(max_workers=12) as clients:
            futures = list(clients.map(submit, range(12)))
        futures[0].result(2)
        self.assertTrue(all(future is futures[0] for future in futures))
        self.assertEqual(calls, ["called"])

    def test_capacity_rejection_leaves_no_future_or_pending_job(self):
        runtime = self.runtime(XIAOHA_JOB_WORKERS=1, XIAOHA_JOB_QUEUE_LIMIT=3, XIAOHA_ACCOUNT_QUEUE_LIMIT=2)
        gate = threading.Event()
        try:
            runtime.submit_generation_job("a", "a1", gate.wait, 3)
            runtime.submit_generation_job("a", "a2", lambda: None)
            with self.assertRaisesRegex(RuntimeError, "当前账号任务队列已满"):
                runtime.submit_generation_job("a", "a3", lambda: None)
            runtime.submit_generation_job("b", "b1", lambda: None)
            with self.assertRaisesRegex(RuntimeError, "小哈任务队列已满"):
                runtime.submit_generation_job("c", "c1", lambda: None)
            for job in ("a3", "c1"):
                self.assertNotIn(job, runtime.futures)
                self.assertNotIn(job, runtime._pending)
                self.assertNotIn(job, runtime.job_queue_keys)
        finally:
            gate.set()

    def test_parallel_submissions_cannot_overfill_one_account(self):
        runtime = self.runtime(XIAOHA_ACCOUNT_QUEUE_LIMIT=3)
        gate = threading.Event()
        barrier = threading.Barrier(12)

        def submit(i):
            barrier.wait()
            try:
                return runtime.submit_generation_job("same-account", str(i), gate.wait, 3)
            except RuntimeError:
                return None

        try:
            with ThreadPoolExecutor(max_workers=12) as clients:
                results = list(clients.map(submit, range(12)))
            self.assertEqual(sum(result is not None for result in results), 3)
            self.assertEqual(len(runtime.futures), 3)
        finally:
            gate.set()

    def test_failure_releases_account_and_nonwaiting_shutdown_cancels_pending(self):
        runtime = self.runtime(XIAOHA_JOB_WORKERS=1)
        gate = threading.Event()
        started = threading.Event()
        calls = []

        def failing():
            started.set()
            gate.wait(3)
            raise ValueError("expected")

        first = runtime.submit_generation_job("a", "a1", failing)
        self.assertTrue(started.wait(1))
        queued = runtime.submit_generation_job("a", "a2", calls.append, "must-not-run")
        runtime.shutdown(wait=False)
        gate.set()
        with self.assertRaisesRegex(ValueError, "expected"):
            first.result(3)
        self.assertTrue(queued.cancelled())
        self.assertEqual(calls, [])

    def test_done_retention_is_bounded_without_pruning_running_jobs(self):
        runtime = self.runtime(XIAOHA_COMPLETED_JOB_LIMIT=2)
        gate = threading.Event()
        active = runtime.submit_generation_job("busy", "active", gate.wait, 3)
        try:
            for i in range(6):
                runtime.submit_generation_job("other", f"done-{i}", lambda: None).result(2)
            deadline = time.monotonic() + 2
            while (len(runtime._completed) > 2 or "other" in runtime.generation_orders) and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertIn("active", runtime.futures)
            self.assertFalse(active.done())
            self.assertLessEqual(len(runtime._completed), 2)
            self.assertLessEqual(len(runtime.futures), 3)
            self.assertNotIn("other", runtime.generation_orders)
        finally:
            gate.set()

    def test_cancel_release_frees_capacity_and_shutdown_drains_fifo(self):
        runtime = self.runtime(XIAOHA_JOB_WORKERS=1, XIAOHA_ACCOUNT_QUEUE_LIMIT=2)
        gate = threading.Event()
        calls = []
        first = runtime.submit_generation_job("a", "a1", gate.wait, 3)
        canceled = runtime.submit_generation_job("a", "a2", calls.append, "canceled")
        runtime.release_generation_job("a2")
        self.assertTrue(canceled.cancelled())
        last = runtime.submit_generation_job("a", "a3", calls.append, "last")
        gate.set()
        runtime.shutdown(wait=True)
        self.assertTrue(first.done())
        self.assertTrue(last.done())
        self.assertEqual(calls, ["last"])
        self.assertEqual(runtime.generation_orders, {})
        with self.assertRaisesRegex(RuntimeError, "维护"):
            runtime.submit_generation_job("a", "after-close", lambda: None)


if __name__ == "__main__":
    unittest.main()
