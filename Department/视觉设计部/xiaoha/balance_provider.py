"""Reconcile configured-key usage with the verified local balance baseline.

This is not an account-balance API: recharges and activity on other keys need a
new verified baseline. Only percentage snapshots leave this module for the UI.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
import time

from .omnia_key_pool import credential_fingerprint, get_omnia_key_pool, load_omnia_api_keys


def _load_ledger():
    from .omnia_service import get_cost_ledger
    return get_cost_ledger()


def _fetch_usage(api_key):
    from .omnia_service import fetch_usage
    return fetch_usage(api_key)


def _fetch_task_status(api_key, task_id):
    from .omnia_service import fetch_task_status
    return fetch_task_status(api_key, task_id)


class BalanceProvider:
    def __init__(self, *, ledger_loader=_load_ledger, keys_loader=load_omnia_api_keys,
                 usage_fetcher=_fetch_usage, pool_loader=get_omnia_key_pool, clock=time.monotonic,
                 ttl_seconds=300, failure_ttl_seconds=30, task_status_fetcher=_fetch_task_status):
        self._ledger_loader = ledger_loader
        self._keys_loader = keys_loader
        self._usage_fetcher = usage_fetcher
        self._task_status_fetcher = task_status_fetcher
        self._pool_loader = pool_loader
        self._clock = clock
        self._ttl = ttl_seconds
        self._failure_ttl = failure_ttl_seconds
        self._lock = threading.Lock()
        self._scope = None
        self._expires_at = 0
        self._refresh_failed = False
        self._running = None

    @staticmethod
    def _unavailable():
        return {"percent": None, "updated_at": "", "error": True,
                "pending_calls": 0, "active_calls": 0, "calls": []}

    def snapshot(self, force=False, *, primary_loader=None):
        try:
            ledger = self._ledger_loader()
            if ledger is None:
                return self._unavailable()
            primary = primary_loader() if primary_loader is not None else ""
            keys = tuple(self._keys_loader(primary))
            if not keys:
                return self._unavailable()
            fingerprints = tuple(credential_fingerprint(key) for key in keys)
            scope = (ledger.db_path, fingerprints)
        except Exception:
            return self._unavailable()

        while True:
            with self._lock:
                running = self._running
                fresh = self._scope == scope and self._clock() < self._expires_at
                if running is None and fresh and not force:
                    break
                if running is None:
                    running = threading.Event()
                    self._running = running
                    owner = True
                else:
                    owner = False
            if not owner:
                running.wait()
                # A concurrent refresh satisfies a forced request as well.
                force = False
                continue
            failed = True
            global_failure = False
            try:
                def reconcile(item):
                    key, fingerprint = item
                    try:
                        with self._pool_loader().try_hold_nonblocking(
                                keys, preferred_fingerprint=fingerprint) as credential:
                            if credential is None:
                                # The owning generation worker will reconcile
                                # this channel; never read its temporary window
                                # as a final cost or queue a balance-page lease.
                                return True
                            from .omnia_service import reconcile_omnia_key
                            result = reconcile_omnia_key(
                                ledger, credential, usage_fetcher=self._usage_fetcher,
                                task_status_fetcher=self._task_status_fetcher,
                            )
                            return not result["error"]
                    except Exception:
                        try:
                            ledger.mark_key_error(fingerprint)
                        except Exception:
                            pass
                        return False

                with ThreadPoolExecutor(max_workers=min(5, len(keys))) as pool:
                    results = list(pool.map(reconcile, zip(keys, fingerprints)))
                failed = not all(results)
            except Exception:
                failed = True
                global_failure = True
            finally:
                with self._lock:
                    self._scope = scope
                    # Per-key failures already live in the ledger and may be
                    # healed by a generation worker before the cache expires.
                    # Keep only failures of the refresh machinery itself here.
                    self._refresh_failed = global_failure
                    self._expires_at = self._clock() + (self._failure_ttl if failed else self._ttl)
                    self._running = None
                    running.set()
            break

        try:
            result = dict(ledger.snapshot())
            with self._lock:
                result["error"] = bool(result.get("error") or self._refresh_failed)
            result["failed_channels"] = len(ledger.failed_key_fingerprints())
            # Stable, friendly channel numbering; no fingerprint is sent to UI.
            channels = {fingerprint[:8]: index + 1 for index, fingerprint in enumerate(fingerprints)}
            calls = []
            for item in ledger.list_calls(limit=100):
                calls.append({
                    "call_id": item["call_id"], "task_id": item["task_id"],
                    "model": item["model"], "resolution": item["resolution"],
                    "channel": channels.get(item["channel"]),
                    "cost_percent": item["cost_percent"], "status": item["status"],
                    "outcome": item["outcome"], "created_at": item["created_at"],
                    "finished_at": item["finished_at"],
                    "refunded": bool(item.get("refunded")),
                    "refund_percent": item.get("refund_percent", 0),
                })
            result["calls"] = calls
            return result
        except Exception:
            return self._unavailable()


_provider = BalanceProvider()


def load_balance_snapshot(force=False, *, primary_loader=None):
    return _provider.snapshot(force=force, primary_loader=primary_loader)
