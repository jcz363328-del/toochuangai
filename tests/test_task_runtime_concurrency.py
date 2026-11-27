from __future__ import annotations

import ast
import os
import threading
import time
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

def load_runtime_class():
    # Exercise the actual scheduler without importing Streamlit or credentials.
    # A replacement source can be checked before it is applied to main.
    path = Path(os.environ.get("XIAOHA_TASK_RUNTIME_SOURCE") or
                Path(__file__).resolve().parents[1] / "Department" / "视觉设计部" / "xiaoha" / "task_runtime.py")
    module = ast.parse(path.read_text(encoding="utf-8-sig"))
    runtime = next(node for node in module.body
                   if isinstance(node, ast.ClassDef) and node.name == "TaskRuntime")
    namespace = {"os": os, "time": time, "Lock": threading.Lock,
                 "ThreadPoolExecutor": ThreadPoolExecutor, "Future": Future, "Any": Any,
                 "JIMENG_HD_GLOBAL_QUEUE_KEY": "__jimeng_hd_global_queue__"}
    exec(compile(ast.Module(body=[runtime], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["TaskRuntime"]


site = SimpleNamespace(TaskRuntime=load_runtime_class())


class TaskRuntimeConcurrencyTests(unittest.TestCase):
    def runtime(self, **settings):
        values = {"XIAOHA_JOB_WORKERS": "2", "XIAOHA_ACCOUNT_CONCURRENCY": "5",
                  "XIAOHA_JOB_QUEUE_LIMIT": "64", "XIAOHA_ACCOUNT_QUEUE_LIMIT": "8"}
        values.update({k: str(v) for k, v in settings.items()})
        with patch.dict(os.environ, values):
            runtime = site.TaskRuntime()
        self.addCleanup(runtime.shutdown)
        return runtime

    def test_default_five_jobs_from_one_account_run_and_sixth_queues(self):
        with patch.dict(os.environ, {}, clear=True):
            runtime = site.TaskRuntime()
        self.addCleanup(runtime.shutdown)
        self.assertEqual(runtime.max_workers, 5)
        gates = [threading.Event() for _ in range(6)]
        started = [threading.Event() for _ in range(6)]

        def work(index):
            started[index].set()
            gates[index].wait(3)
            return index

        try:
            futures = [runtime.submit_generation_job("same", str(i), work, i) for i in range(6)]
            for index in range(5):
                self.assertTrue(started[index].wait(1))
                self.assertEqual(runtime.get_generation_queue_state(str(index))["state"], "running")
            self.assertFalse(started[5].is_set())
            self.assertEqual(runtime.get_generation_queue_state("5"),
                             {"state": "queued", "ahead_count": 5, "queue_position": 6})
            gates[0].set()
            self.assertTrue(started[5].wait(1))
        finally:
            for gate in gates:
                gate.set()
        self.assertEqual([future.result(3) for future in futures], list(range(6)))

    def test_other_account_gets_released_slot_before_busy_account_backlog(self):
        runtime = self.runtime(XIAOHA_JOB_WORKERS=5, XIAOHA_ACCOUNT_QUEUE_LIMIT=16)
        gates = [threading.Event() for _ in range(5)]
        started = [threading.Event() for _ in range(5)]
        other_gate = threading.Event()
        other_started = threading.Event()
        order = []
        guard = threading.Lock()

        def work(name):
            with guard:
                order.append(name)
            if name.startswith("a") and int(name[1:]) < 5:
                index = int(name[1:])
                started[index].set()
                gates[index].wait(3)
            if name == "b0":
                other_started.set()
                other_gate.wait(3)

        try:
            futures = [runtime.submit_generation_job("a", f"a{i}", work, f"a{i}") for i in range(8)]
            self.assertTrue(all(event.wait(1) for event in started))
            other = runtime.submit_generation_job("b", "b0", work, "b0")
            self.assertEqual(runtime.get_generation_queue_state("b0")["state"], "queued")
            gates[0].set()
            self.assertTrue(other_started.wait(2))
            self.assertNotIn("a5", order)
            for gate in gates:
                gate.set()
            other_gate.set()
            other.result(2)
            for future in futures:
                future.result(2)
            self.assertLess(order.index("b0"), order.index("a5"))
        finally:
            for gate in gates:
                gate.set()
            other_gate.set()

    def test_account_limit_and_jimeng_single_slot_are_respected(self):
        runtime = self.runtime(XIAOHA_JOB_WORKERS=5, XIAOHA_ACCOUNT_CONCURRENCY=2)
        gate = threading.Event()
        try:
            futures = [runtime.submit_generation_job("a", f"a{i}", gate.wait, 3) for i in range(3)]
            special = [runtime.submit_generation_job("__jimeng_hd_global_queue__", f"j{i}", gate.wait, 3)
                       for i in range(2)]
            self.assertEqual(runtime.get_generation_queue_state("a1")["state"], "running")
            self.assertEqual(runtime.get_generation_queue_state("a2")["state"], "queued")
            self.assertEqual(runtime.get_generation_queue_state("j0")["state"], "running")
            self.assertEqual(runtime.get_generation_queue_state("j1")["state"], "queued")
            other = runtime.submit_generation_job("b", "b0", gate.wait, 3)
            self.assertEqual(runtime.get_generation_queue_state("b0")["state"], "running")
        finally:
            gate.set()
        for future in futures + special + [other]:
            future.result(3)

    def test_failed_job_releases_one_of_five_slots_and_keeps_other_progress(self):
        runtime = self.runtime(XIAOHA_JOB_WORKERS=5)
        gate = threading.Event()
        fail_gate = threading.Event()
        queued_started = threading.Event()

        def failing():
            fail_gate.wait(3)
            raise ValueError("expected")

        try:
            failed = runtime.submit_generation_job("same", "fail", failing)
            peers = [runtime.submit_generation_job("same", f"peer{i}", gate.wait, 3) for i in range(4)]
            runtime.progress.update({f"peer{i}": {"percent": 42} for i in range(4)})
            queued = runtime.submit_generation_job("same", "queued", queued_started.set)
            self.assertEqual(runtime.get_generation_queue_state("queued")["state"], "queued")
            fail_gate.set()
            with self.assertRaisesRegex(ValueError, "expected"):
                failed.result(2)
            self.assertTrue(queued_started.wait(2))
            queued.result(2)
            self.assertEqual(runtime.get_generation_queue_state("fail")["state"], "completed")
            self.assertEqual(runtime.get_generation_queue_state("unknown")["state"], "missing")
            self.assertTrue(all(runtime.progress[f"peer{i}"]["percent"] == 42 for i in range(4)))
            runtime.release_generation_job("peer0")
            self.assertIn("peer0", runtime.futures)
            self.assertEqual(runtime.progress["peer0"]["percent"], 42)
        finally:
            fail_gate.set()
            gate.set()
        for future in peers:
            future.result(3)

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
