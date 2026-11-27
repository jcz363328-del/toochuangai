"""Background job queues and lifecycle for Xiaoha."""
from __future__ import annotations

import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any

JIMENG_HD_GLOBAL_QUEUE_KEY = "__jimeng_hd_global_queue__"


class TaskRuntime:
    """Bounded concurrent jobs with FIFO per account and fair shared capacity."""

    def __init__(self) -> None:
        def setting(name: str, default: int, maximum: int) -> int:
            try:
                return min(max(int(os.environ.get(name, default)), 1), maximum)
            except (TypeError, ValueError):
                return default

        self.max_workers = setting("XIAOHA_JOB_WORKERS", 5, 16)
        self.max_account_workers = min(
            self.max_workers, setting("XIAOHA_ACCOUNT_CONCURRENCY", 5, 5)
        )
        self.max_outstanding_jobs = setting("XIAOHA_JOB_QUEUE_LIMIT", 64, 4096)
        self.max_account_jobs = setting("XIAOHA_ACCOUNT_QUEUE_LIMIT", 8, 256)
        self.completed_limit = setting("XIAOHA_COMPLETED_JOB_LIMIT", 256, 4096)
        self.completed_ttl = setting("XIAOHA_COMPLETED_JOB_TTL_SECONDS", 86400, 604800)
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="xiaoha-local")
        self.generation_executor = ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix="xiaoha-generation"
        )
        self.generation_orders: dict[str, list[str]] = {}
        self.job_queue_keys: dict[str, str] = {}
        self.futures: dict[str, Future] = {}
        self.progress: dict[str, dict[str, Any]] = {}
        self.lock = Lock()
        self._pending: dict[str, tuple[Any, tuple[Any, ...]]] = {}
        self._ready_accounts: list[str] = []
        self._running_accounts: dict[str, int] = {}
        self._running_jobs: set[str] = set()
        self._completed: dict[str, float] = {}
        self._closed = False

    def _forget_completed_locked(self, job_id: str) -> None:
        future = self.futures.get(job_id)
        if future is not None and not future.done():
            return
        self.futures.pop(job_id, None)
        self.progress.pop(job_id, None)
        self.job_queue_keys.pop(job_id, None)
        self._completed.pop(job_id, None)

    def _prune_completed_locked(self) -> None:
        now = time.monotonic()
        ordered_ids = {item for order in self.generation_orders.values() for item in order}
        # Local helper futures share this registry and also need bounded
        # retention if their browser session is closed before collecting them.
        for job_id, future in self.futures.items():
            if future.done() and job_id not in ordered_ids and job_id not in self._completed:
                self._completed[job_id] = now
        for job_id, completed_at in list(self._completed.items()):
            if now - completed_at >= self.completed_ttl or len(self._completed) > self.completed_limit:
                self._forget_completed_locked(job_id)

    def _clean_canceled_locked(self) -> None:
        for job_id in list(self._pending):
            if not self.futures[job_id].cancelled():
                continue
            self._pending.pop(job_id, None)
            account = self.job_queue_keys[job_id]
            order = self.generation_orders.get(account, [])
            if job_id in order:
                order.remove(job_id)
            if not order:
                self.generation_orders.pop(account, None)
                if account in self._ready_accounts:
                    self._ready_accounts.remove(account)
            self._completed[job_id] = time.monotonic()

    def _dispatch_locked(self) -> None:
        self._clean_canceled_locked()
        while self._ready_accounts and len(self._running_jobs) < self.max_workers:
            candidate = next((
                index for index, account in enumerate(self._ready_accounts)
                if self._running_accounts.get(account, 0) < (
                    1 if account == JIMENG_HD_GLOBAL_QUEUE_KEY else self.max_account_workers
                )
            ), None)
            if candidate is None:
                break
            account = self._ready_accounts.pop(candidate)
            order = self.generation_orders.get(account, [])
            # Running jobs stay in generation_orders for quota/progress lookup;
            # only the first still-pending job is eligible for dispatch.
            job_id = next((item for item in order if item in self._pending), None)
            if job_id is None:
                continue
            callback, args = self._pending.pop(job_id)
            self._running_jobs.add(job_id)
            self._running_accounts[account] = self._running_accounts.get(account, 0) + 1
            if any(item in self._pending for item in order):
                self._ready_accounts.append(account)
            self.generation_executor.submit(
                self._run_generation_job, account, job_id, self.futures[job_id], callback, args
            )
        self._prune_completed_locked()

    def _run_generation_job(self, account: str, job_id: str, future: Future, callback: Any, args: tuple) -> None:
        try:
            if future.set_running_or_notify_cancel():
                try:
                    result = callback(*args)
                except BaseException as exc:
                    future.set_exception(exc)
                else:
                    future.set_result(result)
        finally:
            with self.lock:
                order = self.generation_orders.get(account, [])
                if job_id in order:
                    order.remove(job_id)
                self._running_jobs.discard(job_id)
                remaining = self._running_accounts.get(account, 1) - 1
                if remaining:
                    self._running_accounts[account] = remaining
                else:
                    self._running_accounts.pop(account, None)
                # Give accounts that waited during this job the next turn.
                # A busy account can still fill every otherwise-idle slot.
                if account in self._ready_accounts:
                    self._ready_accounts.remove(account)
                if any(item in self._pending for item in order):
                    self._ready_accounts.append(account)
                if not order:
                    self.generation_orders.pop(account, None)
                self._completed[job_id] = time.monotonic()
                self._dispatch_locked()

    def submit_generation_job(
        self,
        queue_key: str,
        job_id: str,
        callback: Any,
        *args: Any,
        max_outstanding_jobs: int | None = None,
    ) -> Future:
        account = str(queue_key or "admin").strip() or "admin"
        with self.lock:
            existing = self.futures.get(job_id)
            if existing is not None:
                return existing
            if self._closed:
                raise RuntimeError("小哈正在维护，暂时不能提交新任务。")
            self._clean_canceled_locked()
            self._prune_completed_locked()
            outstanding = sum(not future.done() for future in self.futures.values())
            if outstanding >= self.max_outstanding_jobs:
                raise RuntimeError(f"小哈任务队列已满（最多 {self.max_outstanding_jobs} 个），请等待已有任务完成。")
            capacity = self.max_outstanding_jobs if account == JIMENG_HD_GLOBAL_QUEUE_KEY else self.max_account_jobs
            if max_outstanding_jobs is not None:
                capacity = min(capacity, max(int(max_outstanding_jobs), 1))
            account_count = sum(
                not self.futures[item].done() for item in self.generation_orders.get(account, [])
            )
            if account_count >= capacity:
                raise RuntimeError(f"当前账号任务队列已满（最多 {capacity} 个），请等待已有任务完成。")
            future = Future()
            self.futures[job_id] = future
            self.job_queue_keys[job_id] = account
            self._pending[job_id] = (callback, args)
            self.generation_orders.setdefault(account, []).append(job_id)
            if account not in self._ready_accounts:
                self._ready_accounts.append(account)
            self._dispatch_locked()
            return future

    def get_generation_queue_state(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            future = self.futures.get(job_id)
            if future is None:
                return {"state": "missing", "ahead_count": 0, "queue_position": 0}
            if future.done():
                state = "canceled" if future.cancelled() else "completed"
                return {"state": state, "ahead_count": 0, "queue_position": 0}
            if future.running() or job_id in self._running_jobs:
                return {"state": "running", "ahead_count": 0, "queue_position": 0}
            account = self.job_queue_keys.get(job_id, "")
            before = 0
            for item in self.generation_orders.get(account, []):
                if item == job_id:
                    break
                if not self.futures[item].done():
                    before += 1
            return {"state": "queued", "ahead_count": before, "queue_position": before + 1}

    def release_generation_job(self, job_id: str) -> None:
        with self.lock:
            future = self.futures.get(job_id)
            # An active Future can still be referenced by the scheduler. Only
            # reclaim it after its account slot and order entry are released.
            if job_id in self._pending or any(job_id in order for order in self.generation_orders.values()):
                if future is not None and not future.done():
                    future.cancel()
                self._dispatch_locked()
                return
            self._forget_completed_locked(job_id)

    def shutdown(self, wait: bool = True) -> None:
        with self.lock:
            self._closed = True
            futures = list(self.futures.values())
            if not wait:
                for job_id in self._pending:
                    self.futures[job_id].cancel()
        if wait:
            # Drain application queues before closing the underlying executor;
            # completed jobs still need to dispatch the next account job.
            for future in futures:
                try:
                    future.result()
                except BaseException:
                    pass
        self.executor.shutdown(wait=wait)
        self.generation_executor.shutdown(wait=wait)
