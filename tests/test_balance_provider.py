from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from 图片.balance_provider import BalanceProvider
from 图片.omnia_cost_ledger import CostLedger
from 图片.omnia_key_pool import OmniaKeyPool, credential_fingerprint


KEYS = ("test-credential-one", "test-credential-two", "test-credential-three",
        "test-credential-four", "test-credential-five")
IDS = tuple(credential_fingerprint(key) for key in KEYS)


class BalanceProviderTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.ledger = CostLedger(Path(folder.name) / "ledger.sqlite3")
        self.ledger.initialize_balance("42.86", {key: 0 for key in IDS}, baseline_id="test-start")
        self.time = 0
        self.usage = {key: "0" for key in KEYS}
        self.fetch = Mock(side_effect=lambda key: self.usage[key])
        self.fetch_status = Mock(return_value=None)
        self.load_keys = Mock(return_value=KEYS)
        self.pool = OmniaKeyPool(Path(folder.name) / "leases.sqlite3")
        self.provider = BalanceProvider(ledger_loader=lambda: self.ledger,
                                        keys_loader=self.load_keys, usage_fetcher=self.fetch,
                                        pool_loader=lambda: self.pool,
                                        clock=lambda: self.time, task_status_fetcher=self.fetch_status)

    def test_initial_refresh_queries_each_key_once_and_returns_verified_percentage(self):
        result = self.provider.snapshot()
        self.assertEqual(result["percent"], 42.86)
        self.assertFalse(result["error"])
        self.assertEqual(self.fetch.call_count, 5)
        self.assertEqual(result["calls"], [])

    def test_remote_usage_is_cached_but_local_new_calls_are_immediately_visible(self):
        self.provider.snapshot()
        self.ledger.begin_call("call", "", IDS[0], "model", "2K", 0)
        self.ledger.finish_call("call", "success", ".029")
        self.time = 299
        result = self.provider.snapshot()
        self.assertEqual(result["percent"], 42.831)
        self.assertEqual(len(result["calls"]), 1)
        self.assertEqual(result["calls"][0]["channel"], 1)
        self.assertEqual(result["calls"][0]["cost_percent"], .029)
        self.assertEqual(self.fetch.call_count, 5)
        self.usage[KEYS[0]] = ".029"
        self.time = 300
        self.provider.snapshot()
        self.assertEqual(self.fetch.call_count, 10)

    def test_forced_refresh_deducts_only_new_cumulative_usage(self):
        self.provider.snapshot()
        self.usage[KEYS[2]] = "1.25"
        result = self.provider.snapshot(force=True)
        self.assertEqual(result["percent"], 41.61)
        self.assertEqual(self.fetch.call_count, 10)
        self.provider.snapshot(force=True)
        self.assertEqual(self.ledger.snapshot()["percent"], 41.61)

    def test_failed_query_retains_verified_balance_and_uses_short_failure_ttl(self):
        self.provider.snapshot()
        self.fetch.side_effect = RuntimeError("private amount USD 999 and secret")
        result = self.provider.snapshot(force=True)
        self.assertEqual(result["percent"], 42.86)
        self.assertTrue(result["error"])
        self.assertNotIn("private", repr(result))
        self.time = 29
        self.provider.snapshot()
        self.assertEqual(self.fetch.call_count, 10)
        self.fetch.side_effect = lambda key: self.usage[key]
        self.time = 30
        result = self.provider.snapshot()
        self.assertFalse(result["error"])
        self.assertEqual(self.fetch.call_count, 15)

    def test_counter_regression_never_increases_displayed_balance(self):
        self.usage[KEYS[0]] = "1"
        self.provider.snapshot()
        self.usage[KEYS[0]] = "0"
        result = self.provider.snapshot(force=True)
        self.assertEqual(result["percent"], 41.86)
        self.assertTrue(result["error"])

    def test_concurrent_forced_refreshes_share_one_read_per_key(self):
        entered, release = threading.Event(), threading.Event()
        def fetch(key):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("wait timeout")
            return 0
        self.fetch.side_effect = fetch
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.provider.snapshot, True)
            self.assertTrue(entered.wait(1))
            second = pool.submit(self.provider.snapshot, True)
            try:
                with self.assertRaises(TimeoutError):
                    second.result(timeout=.05)
            finally:
                release.set()
            self.assertEqual(first.result()["percent"], second.result()["percent"])
        self.assertEqual(self.fetch.call_count, 5)

    def test_missing_ledger_or_keys_never_fabricates_a_balance(self):
        provider = BalanceProvider(ledger_loader=lambda: None)
        self.assertIsNone(provider.snapshot()["percent"])
        self.load_keys.return_value = ()
        self.assertIsNone(self.provider.snapshot()["percent"])
        self.assertEqual(self.fetch.call_count, 0)

    def test_primary_loader_is_forwarded_without_displaying_credentials(self):
        loader = Mock(return_value=KEYS[0])
        result = self.provider.snapshot(primary_loader=loader)
        loader.assert_called_once_with()
        self.load_keys.assert_called_once_with(KEYS[0])
        for secret in (*KEYS, *IDS):
            self.assertNotIn(secret, repr(result))
        self.assertNotIn("usd", repr(result).lower())

    def test_pending_call_is_visible_and_does_not_appear_free(self):
        self.ledger.begin_call("call", "", IDS[0], "model", "2K", 0)
        self.ledger.finish_call("call", "uncertain")
        result = self.provider.snapshot()
        self.assertEqual(result["pending_calls"], 1)
        self.assertEqual(result["calls"][0]["status"], "pending")
        self.assertIsNone(result["calls"][0]["cost_percent"])

    def test_delayed_charge_is_settled_only_under_the_idle_key_lease(self):
        self.ledger.begin_call("call", "", IDS[0], "model", "2K", 0)
        self.ledger.finish_call("call", "success", 0)
        self.usage[KEYS[0]] = ".029"
        result = self.provider.snapshot()
        self.assertEqual(result["calls"][0]["status"], "settled")
        self.assertEqual(result["calls"][0]["cost_percent"], .029)
        self.assertEqual(result["pending_calls"], 0)
        self.assertEqual(result["percent"], 42.831)

    def test_active_key_is_skipped_without_reading_or_settling_its_window(self):
        with self.pool.hold(KEYS, preferred_fingerprint=IDS[0]):
            self.ledger.begin_call("call", "", IDS[0], "model", "2K", 0)
            self.usage[KEYS[0]] = ".029"
            result = self.provider.snapshot()
            self.assertEqual(result["calls"][0]["status"], "submitted")
            self.assertEqual(result["active_calls"], 1)
            self.assertEqual(result["percent"], 42.86)
            self.assertEqual(self.fetch.call_count, 4)
        result = self.provider.snapshot(force=True)
        self.assertEqual(result["calls"][0]["outcome"], "uncertain")
        self.assertEqual(result["calls"][0]["cost_percent"], .029)
        self.assertEqual(result["percent"], 42.831)

    def failed_charge(self):
        self.ledger.begin_call("failed-4k", "remote-task-4k", IDS[0], "model", "4K", 0)
        self.ledger.finish_call("failed-4k", "uncertain", ".039")

    def test_confirmed_failed_task_refund_returns_balance_once(self):
        self.failed_charge()
        self.fetch_status.return_value = "failed"
        result = self.provider.snapshot()
        self.assertEqual(result["percent"], 42.86)
        self.assertFalse(result["error"])
        row = result["calls"][0]
        self.assertEqual(row["outcome"], "failed")
        self.assertEqual(row["cost_percent"], 0)
        self.assertTrue(row["refunded"])
        self.assertEqual(row["refund_percent"], .039)
        self.fetch_status.assert_called_with(KEYS[0], "remote-task-4k")
        repeated = self.provider.snapshot(force=True)
        self.assertEqual(repeated["percent"], 42.86)
        self.assertEqual(len(repeated["calls"]), 1)
        self.assertEqual(repeated["calls"][0]["refund_percent"], .039)

    def test_unknown_but_paid_task_can_be_confirmed_successful(self):
        self.failed_charge()
        self.usage[KEYS[0]] = ".039"
        self.fetch_status.return_value = "success"
        result = self.provider.snapshot()
        row = result["calls"][0]
        self.assertEqual((row["outcome"], row["cost_percent"]), ("success", .039))
        self.assertFalse(row["refunded"])
        self.assertEqual(result["percent"], 42.821)

    def test_busy_key_does_not_query_task_status(self):
        self.failed_charge()
        with self.pool.hold(KEYS, preferred_fingerprint=IDS[0]):
            result = self.provider.snapshot()
        self.fetch_status.assert_not_called()
        self.assertEqual(result["percent"], 42.821)
        self.assertEqual(result["calls"][0]["outcome"], "uncertain")

    def test_task_status_failure_cannot_confirm_refund(self):
        self.failed_charge()
        self.fetch_status.side_effect = RuntimeError("private provider response")
        result = self.provider.snapshot()
        self.assertTrue(result["error"])
        self.assertEqual(result["failed_channels"], 1)
        self.assertEqual(result["percent"], 42.821)
        self.assertFalse(result["calls"][0]["refunded"])
        self.assertNotIn("private", repr(result))

    def test_usage_failure_cannot_confirm_refund(self):
        self.failed_charge()
        self.fetch_status.return_value = "failed"

        def fetch(key):
            if key == KEYS[0]:
                raise RuntimeError("usage unavailable")
            return 0

        self.fetch.side_effect = fetch
        result = self.provider.snapshot()
        self.assertTrue(result["error"])
        self.assertEqual(result["percent"], 42.821)
        self.assertFalse(result["calls"][0]["refunded"])

    def test_task_status_failure_does_not_mark_valid_balance_refresh_failed(self):
        self.failed_charge()
        self.usage[KEYS[0]] = ".039"
        self.fetch_status.side_effect = RuntimeError("task status unavailable")
        result = self.provider.snapshot()
        self.assertFalse(result["error"])
        self.assertEqual(result["failed_channels"], 0)
        self.assertEqual(result["percent"], 42.821)
        self.assertEqual(result["calls"][0]["outcome"], "uncertain")

    def test_cache_does_not_reintroduce_key_error_already_healed_by_worker(self):
        def fetch(key):
            if key == KEYS[0]:
                raise RuntimeError("usage unavailable")
            return 0

        self.fetch.side_effect = fetch
        failed = self.provider.snapshot()
        self.assertTrue(failed["error"])
        self.assertEqual(failed["failed_channels"], 1)
        self.ledger.reconcile_key(IDS[0], 0)
        self.time = 1
        healed = self.provider.snapshot()
        self.assertFalse(healed["error"])
        self.assertEqual(healed["failed_channels"], 0)
        self.assertEqual(self.fetch.call_count, 5)


if __name__ == "__main__":
    unittest.main()
