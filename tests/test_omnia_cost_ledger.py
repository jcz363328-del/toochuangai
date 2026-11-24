from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from 图片.omnia_cost_ledger import CostLedger, KeyBusyError


KEYS = [str(index) * 64 for index in range(1, 6)]


class CostLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "costs.sqlite3"
        self.now = datetime(2026, 11, 24, 7, 0, 0, tzinfo=timezone.utc)
        self.ledger = CostLedger(self.path, now=lambda: self.now)
        self.baselines = {key: ("12.3" if index == 0 else "0") for index, key in enumerate(KEYS)}
        self.ledger.initialize_balance("42.86", self.baselines, baseline_id="verified-20261124")

    def begin(self, call="call-1", key=KEYS[0], before="12.3", task="task-1"):
        return self.ledger.begin_call(call, task, key, "nano-banana-2.1", "2K", before)

    def test_user_verified_baseline_only_exposes_percentage(self):
        self.assertEqual(self.ledger.snapshot(), {
            "percent": 42.86, "updated_at": "2026-11-24 15:00:00", "error": False,
            "pending_calls": 0, "active_calls": 0,
        })

    def test_restart_never_resets_existing_usage_baseline(self):
        self.ledger.reconcile_key(KEYS[0], "12.8")
        restarted = CostLedger(self.path)
        self.assertFalse(restarted.initialize_balance("42.86", {k: "99" for k in KEYS},
                                                     baseline_id="verified-20261124"))
        self.assertEqual(restarted.snapshot()["percent"], 42.36)
        with self.assertRaises(ValueError):
            restarted.initialize_balance("100", self.baselines, baseline_id="replacement")
        with self.assertRaises(ValueError):
            restarted.initialize_balance("100", {KEYS[0]: "0"}, baseline_id="verified-20261124")

    def test_uninitialized_ledger_is_unknown(self):
        empty = CostLedger(Path(self.temp.name) / "empty.sqlite3")
        self.assertIsNone(empty.snapshot()["percent"])
        self.assertTrue(empty.snapshot()["error"])

    def test_positive_per_call_charge_settles_once_and_survives_restart(self):
        self.begin()
        result = self.ledger.finish_call("call-1", "success", "12.329")
        self.assertEqual(result["cost_percent"], .029)
        self.assertEqual(result["status"], "settled")
        self.assertEqual(result["outcome"], "success")
        self.assertEqual(self.ledger.snapshot()["percent"], 42.831)
        for _ in range(3):
            self.ledger.finish_call("call-1", "success", "12.329")
            self.ledger.settle_call("call-1", "12.329")
            self.ledger.reconcile_key(KEYS[0], "12.329")
        self.assertEqual(CostLedger(self.path).snapshot()["percent"], 42.831)
        self.assertEqual(len(self.ledger.list_calls()), 1)

    def test_zero_success_is_pending_until_provider_finalization(self):
        self.begin()
        result = self.ledger.finish_call("call-1", "success", "12.3")
        self.assertEqual(result["status"], "pending")
        self.assertIsNone(result["cost_percent"])
        self.assertEqual(self.ledger.snapshot()["pending_calls"], 1)
        settled = self.ledger.settle_call("call-1", "12.329")
        self.assertEqual(settled["cost_percent"], .029)
        self.assertEqual(self.ledger.snapshot()["pending_calls"], 0)

    def test_confirmed_no_charge_failure_does_not_deduct(self):
        self.begin()
        row = self.ledger.finish_call("call-1", "failed", "12.3", final_zero=True)
        self.assertEqual((row["status"], row["outcome"], row["cost_percent"]),
                         ("settled", "failed", 0.0))
        self.assertEqual(self.ledger.snapshot()["percent"], 42.86)

    def test_failed_response_does_not_invent_a_refund(self):
        self.begin()
        row = self.ledger.finish_call("call-1", "failed", "12.339")
        self.assertEqual(row["cost_percent"], .039)
        self.assertEqual(row["outcome"], "failed")
        self.assertEqual(self.ledger.snapshot()["percent"], 42.821)

    def test_unknown_network_outcome_is_not_reported_as_free(self):
        self.begin()
        row = self.ledger.finish_call("call-1", "uncertain")
        self.assertEqual((row["status"], row["outcome"]), ("pending", "uncertain"))
        self.assertIsNone(row["cost_percent"])
        self.assertTrue(self.ledger.snapshot()["error"])
        row = self.ledger.finish_call("call-1", "success", "12.329")
        self.assertEqual((row["status"], row["outcome"]), ("settled", "success"))

    def test_five_concurrent_channels_are_accounted_without_lost_updates(self):
        def work(index):
            key = KEYS[index]
            before = Decimal(self.baselines[key])
            self.begin(f"call-{index}", key, before)
            return self.ledger.finish_call(f"call-{index}", "success", before + Decimal("0.029"))
        with ThreadPoolExecutor(max_workers=5) as pool:
            rows = list(pool.map(work, range(5)))
        self.assertTrue(all(row["cost_percent"] == .029 for row in rows))
        self.assertEqual(self.ledger.snapshot()["percent"], 42.715)
        self.assertEqual(self.ledger.snapshot()["active_calls"], 0)

    def test_same_key_cannot_have_two_active_accounting_windows(self):
        self.begin()
        with self.assertRaises(KeyBusyError):
            self.begin("call-2")
        self.assertEqual(self.ledger.snapshot()["active_calls"], 1)

    def test_duplicate_id_is_idempotent_but_different_identity_rejected(self):
        first = self.begin()
        self.assertEqual(self.begin(), first)
        self.assertEqual(len(self.ledger.list_calls()), 1)
        with self.assertRaises(ValueError):
            self.begin(task="different-task")

    def test_prior_pending_makes_later_call_attribution_unsafe(self):
        self.begin()
        self.ledger.finish_call("call-1", "uncertain", "12.3")
        self.begin("call-2")
        second = self.ledger.finish_call("call-2", "success", "12.358")
        self.assertIsNone(second["cost_percent"])
        self.assertEqual(second["status"], "pending")
        first = self.ledger.settle_call("call-1", "12.358")
        self.assertIsNone(first["cost_percent"])
        self.assertEqual(self.ledger.snapshot()["percent"], 42.802)
        self.assertEqual(self.ledger.snapshot()["pending_calls"], 2)

    def test_unconfirmed_attribution_still_updates_total_balance(self):
        self.begin()
        row = self.ledger.finish_call("call-1", "success", "12.329", attribution_confirmed=False)
        self.assertEqual(row["status"], "pending")
        self.assertIsNone(row["cost_percent"])
        self.assertEqual(self.ledger.snapshot()["percent"], 42.831)

    def test_counter_regression_preserves_last_balance_and_flags_error(self):
        self.ledger.reconcile_key(KEYS[0], "12.8")
        self.assertFalse(self.ledger.reconcile_key(KEYS[0], "0"))
        self.assertEqual(self.ledger.snapshot()["percent"], 42.36)
        self.assertTrue(self.ledger.snapshot()["error"])
        self.assertTrue(self.ledger.reconcile_key(KEYS[0], "12.8"))
        self.assertFalse(self.ledger.snapshot()["error"])

    def test_usage_before_a_call_updates_balance_but_is_not_billed_to_it(self):
        self.begin(before="12.8")
        row = self.ledger.finish_call("call-1", "success", "12.829")
        self.assertEqual(row["cost_percent"], .029)
        self.assertEqual(self.ledger.snapshot()["percent"], 42.331)

    def test_missing_or_stale_before_counter_does_not_guess_cost(self):
        self.begin(before=None)
        row = self.ledger.finish_call("call-1", "success", "12.329")
        self.assertIsNone(row["cost_percent"])
        self.assertEqual(self.ledger.snapshot()["percent"], 42.831)
        self.begin("call-2", key=KEYS[1], before="0")
        self.ledger.finish_call("call-2", "success", ".029")
        self.begin("call-3", key=KEYS[1], before="0")
        row = self.ledger.finish_call("call-3", "success", ".058")
        self.assertIsNone(row["cost_percent"])

    def test_reconcile_does_not_assign_external_usage_to_pending_calls(self):
        self.begin()
        self.ledger.finish_call("call-1", "uncertain")
        self.ledger.reconcile_key(KEYS[0], "13")
        row = self.ledger.list_calls()[0]
        self.assertIsNone(row["cost_percent"])
        self.assertEqual(self.ledger.snapshot()["percent"], 42.16)

    def test_recovery_preserves_interrupted_call_without_retry_or_zero_cost(self):
        self.begin()
        self.assertEqual(self.ledger.recover_interrupted_calls(), 1)
        self.assertEqual(self.ledger.recover_interrupted_calls(), 0)
        row = self.ledger.list_calls()[0]
        self.assertEqual(row["outcome"], "uncertain")
        self.assertIsNone(row["cost_percent"])
        self.assertEqual(self.ledger.snapshot()["pending_calls"], 1)
        self.assertEqual(self.ledger.snapshot()["active_calls"], 0)

    def test_public_records_never_include_raw_amounts_or_key_fingerprints(self):
        self.begin()
        self.ledger.finish_call("call-1", "success", "12.329")
        snapshot, rows = self.ledger.snapshot(), self.ledger.list_calls()
        public = repr((snapshot, rows))
        self.assertNotIn("usd", public.lower())
        self.assertNotIn(KEYS[0], public)
        self.assertNotIn("12.329", public)
        self.assertEqual(rows[0]["channel"], KEYS[0][:8])

    def test_invalid_counters_and_credentials_are_rejected_without_state_changes(self):
        for value in (True, None, "NaN", "Infinity", "-1", {}, "1e10000"):
            with self.subTest(value=str(value)):
                with self.assertRaises(ValueError):
                    self.ledger.reconcile_key(KEYS[0], value)
        with self.assertRaises(ValueError):
            self.begin(key="sk-do-not-store-credentials")
        with self.assertRaises(ValueError):
            self.begin(key="f" * 64)
        self.assertEqual(self.ledger.snapshot()["percent"], 42.86)

    def test_filter_limit_and_negative_remaining(self):
        self.begin(task="task-a")
        self.ledger.finish_call("call-1", "success", "100")
        self.begin("call-2", key=KEYS[1], before="0", task="task-b")
        self.ledger.finish_call("call-2", "failed", "0", final_zero=True)
        self.assertEqual(len(self.ledger.list_calls(limit=1)), 1)
        self.assertEqual(self.ledger.list_calls(task_id="task-a")[0]["call_id"], "call-1")
        self.assertEqual(self.ledger.snapshot()["percent"], 0)

    def test_settled_cost_is_immutable_and_outcome_cannot_regress(self):
        self.begin()
        first = self.ledger.finish_call("call-1", "success", "12.329")
        duplicate = self.ledger.finish_call("call-1", "uncertain", "12.9")
        self.assertEqual(first, duplicate)
        self.assertEqual(self.ledger.snapshot()["percent"], 42.26)

    def test_async_task_binding_and_recovery_reuse_the_existing_call(self):
        self.begin(task="")
        self.assertIsNone(self.ledger.find_call_by_task("provider-task-1"))
        self.ledger.attach_task("call-1", "provider-task-1")
        self.ledger.attach_task("call-1", "provider-task-1")
        self.ledger.finish_call("call-1", "uncertain")
        recovered = CostLedger(self.path).find_call_by_task("provider-task-1")
        self.assertEqual(recovered["call_id"], "call-1")
        self.assertEqual(recovered["key_fingerprint"], KEYS[0])
        self.assertEqual(recovered["before_usage_usd"], "12.3")
        self.assertEqual(recovered["status"], "uncertain")
        self.ledger.finish_call(recovered["call_id"], "success", "12.329")
        self.assertEqual(len(self.ledger.list_calls()), 1)
        self.assertEqual(self.ledger.snapshot()["percent"], 42.831)

    def test_task_binding_cannot_reassign_or_duplicate_provider_requests(self):
        self.begin(task="call-1")
        self.ledger.attach_task("call-1", "provider-task-1")
        with self.assertRaises(ValueError):
            self.ledger.attach_task("call-1", "provider-task-2")
        self.begin("call-2", key=KEYS[1], before="0", task="")
        with self.assertRaises(ValueError):
            self.ledger.attach_task("call-2", "provider-task-1")
        self.assertEqual(self.ledger.find_call_by_task("provider-task-1")["call_id"], "call-1")

    def test_resolved_model_can_change_only_before_call_finishes(self):
        self.begin()
        self.assertEqual(self.ledger.update_call_model("call-1", "resolved-model")["model"], "resolved-model")
        self.ledger.finish_call("call-1", "success", "12.329")
        self.assertEqual(self.ledger.update_call_model("call-1", "late-model")["model"], "resolved-model")
        self.assertEqual(len(self.ledger.list_calls()), 1)

    def test_delayed_charge_can_be_reconciled_before_next_call(self):
        self.begin()
        self.ledger.finish_call("call-1", "success", "12.3")
        pending = self.ledger.latest_pending_call(KEYS[0])
        self.assertEqual(pending["call_id"], "call-1")
        self.assertTrue(pending["attribution_confirmed"])
        self.ledger.settle_call(pending["call_id"], "12.329")
        self.assertIsNone(self.ledger.latest_pending_call(KEYS[0]))
        self.begin("call-2", before="12.329")
        second = self.ledger.finish_call("call-2", "success", "12.358")
        self.assertEqual(second["cost_percent"], .029)
        self.assertEqual(self.ledger.snapshot()["pending_calls"], 0)

    def test_active_window_suppresses_old_pending_lookup(self):
        self.begin()
        self.assertIsNone(self.ledger.latest_pending_call(KEYS[0]))
        self.ledger.finish_call("call-1", "uncertain")
        self.begin("call-2")
        self.assertIsNone(self.ledger.latest_pending_call(KEYS[0]))

    def test_key_specific_crash_recovery_leaves_other_active_channels_alone(self):
        self.begin()
        self.begin("call-2", key=KEYS[1], before="0")
        self.assertEqual(self.ledger.recover_interrupted_key_calls(KEYS[0]), 1)
        self.assertEqual(self.ledger.recover_interrupted_key_calls(KEYS[0]), 0)
        calls = {row["call_id"]: row for row in self.ledger.list_calls()}
        self.assertEqual(calls["call-1"]["outcome"], "uncertain")
        self.assertEqual(calls["call-2"]["outcome"], "submitted")
        self.begin("call-3")
        self.assertEqual(self.ledger.snapshot()["active_calls"], 2)

    def test_saved_receipt_can_find_original_call_before_task_binding(self):
        self.assertIsNone(self.ledger.find_call_by_id("unknown"))
        self.begin(task="")
        record = CostLedger(self.path).find_call_by_id("call-1")
        self.assertEqual(record["task_id"], "")
        self.assertEqual(record["key_fingerprint"], KEYS[0])
        self.assertEqual(record["before_usage_usd"], "12.3")
        self.ledger.attach_task(record["call_id"], "saved-task")
        self.assertEqual(self.ledger.find_call_by_id("call-1"), self.ledger.find_call_by_task("saved-task"))
        self.assertEqual(len(self.ledger.list_calls()), 1)

    def test_cold_start_five_instances_initialize_one_shared_baseline(self):
        path = Path(self.temp.name) / "cold-start.sqlite3"
        gate = threading.Barrier(5)
        def initialize(_):
            gate.wait(timeout=3)
            ledger = CostLedger(path)
            return ledger.initialize_balance("42.86", self.baselines, baseline_id="cold-start")
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(initialize, range(5)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 4)
        self.assertEqual(CostLedger(path).snapshot()["percent"], 42.86)

    def test_first_open_retries_database_locked_by_another_connection(self):
        path = Path(self.temp.name) / "locked-start.sqlite3"
        blocker = sqlite3.connect(path, isolation_level=None)
        self.addCleanup(blocker.close)
        blocker.execute("CREATE TABLE existing (value INTEGER)")
        blocker.execute("BEGIN EXCLUSIVE")
        started = threading.Event()
        def initialize():
            started.set()
            return CostLedger(path)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(initialize)
            self.assertTrue(started.wait(1))
            time.sleep(.25)
            blocker.rollback()
            ledger = future.result(timeout=3)
        self.assertIsNone(ledger.snapshot()["percent"])

    def test_wal_lock_retry_budget_is_bounded(self):
        path = Path(self.temp.name) / "bounded-start.sqlite3"
        with closing(sqlite3.connect(path, isolation_level=None)) as blocker:
            blocker.execute("CREATE TABLE existing (value INTEGER)")
            blocker.execute("BEGIN EXCLUSIVE")
            with closing(sqlite3.connect(path, timeout=30, isolation_level=None)) as contender:
                started = time.monotonic()
                with self.assertRaises(sqlite3.OperationalError):
                    CostLedger._enable_wal(contender, timeout=.15)
                self.assertLess(time.monotonic() - started, .75)
            blocker.rollback()

    def test_failed_task_matching_counter_refund_restores_balance_exactly_once(self):
        self.begin(task="provider-task")
        self.ledger.finish_call("call-1", "uncertain", "12.339")
        self.assertEqual(self.ledger.snapshot()["percent"], 42.821)
        candidates = self.ledger.get_task_reconciliation_candidates(KEYS[0])
        self.assertEqual(candidates[0]["task_id"], "provider-task")
        self.assertEqual(candidates[0]["cost_usd"], "0.039")
        for _ in range(3):
            self.assertTrue(self.ledger.reconcile_task_outcomes(KEYS[0], {"provider-task": "failed"}, "12.3"))
        call = self.ledger.list_calls()[0]
        self.assertEqual(call["cost_percent"], 0)
        self.assertEqual(call["refund_percent"], .039)
        self.assertTrue(call["refunded"])
        self.assertEqual(call["outcome"], "failed")
        self.assertEqual(self.ledger.snapshot()["percent"], 42.86)
        self.assertFalse(self.ledger.snapshot()["error"])
        self.assertEqual(self.ledger.get_task_reconciliation_candidates(KEYS[0]), [])

    def test_canceled_task_can_receive_the_same_verified_refund(self):
        self.begin(task="provider-task")
        self.ledger.finish_call("call-1", "uncertain", "12.339")
        self.assertTrue(self.ledger.reconcile_task_outcomes(KEYS[0], {"provider-task": "canceled"}, "12.3"))
        self.assertTrue(self.ledger.list_calls()[0]["refunded"])

    def test_failure_without_counter_drop_does_not_fabricate_refund(self):
        self.begin(task="provider-task")
        self.ledger.finish_call("call-1", "uncertain", "12.339")
        self.assertTrue(self.ledger.reconcile_task_outcomes(KEYS[0], {"provider-task": "failed"}, "12.339"))
        call = self.ledger.list_calls()[0]
        self.assertEqual(call["outcome"], "failed")
        self.assertFalse(call["refunded"])
        self.assertEqual(call["cost_percent"], .039)

    def test_unconfirmed_or_successful_task_cannot_authorize_counter_drop(self):
        self.begin(task="provider-task")
        self.ledger.finish_call("call-1", "uncertain", "12.339")
        for outcomes in ({}, {"different-task": "failed"}, {"provider-task": "success"}):
            self.assertFalse(self.ledger.reconcile_task_outcomes(KEYS[0], outcomes, "12.3"))
            self.assertEqual(self.ledger.snapshot()["percent"], 42.821)
            self.assertFalse(self.ledger.list_calls()[0]["refunded"])
            self.assertTrue(self.ledger.snapshot()["error"])

    def test_partial_or_excess_counter_drop_stays_unreconciled(self):
        self.begin(task="provider-task")
        self.ledger.finish_call("call-1", "uncertain", "12.339")
        for after in ("12.329", "12.299"):
            self.assertFalse(self.ledger.reconcile_task_outcomes(KEYS[0], {"provider-task": "failed"}, after))
            self.assertEqual(self.ledger.snapshot()["percent"], 42.821)
            self.assertFalse(self.ledger.list_calls()[0]["refunded"])

    def test_later_call_makes_prior_task_refund_ambiguous(self):
        self.begin(task="provider-task-1")
        self.ledger.finish_call("call-1", "uncertain", "12.339")
        self.begin("call-2", task="provider-task-2", before="12.339")
        self.ledger.finish_call("call-2", "success", "12.368")
        self.assertFalse(self.ledger.reconcile_task_outcomes(
            KEYS[0], {"provider-task-1": "failed"}, "12.329"))
        self.assertEqual(self.ledger.snapshot()["percent"], 42.792)
        self.assertFalse(any(call["refunded"] for call in self.ledger.list_calls()))

    def test_external_usage_after_call_prevents_refund_attribution(self):
        self.begin(task="provider-task")
        self.ledger.finish_call("call-1", "uncertain", "12.339")
        self.ledger.reconcile_key(KEYS[0], "12.35")
        self.assertFalse(self.ledger.reconcile_task_outcomes(KEYS[0], {"provider-task": "failed"}, "12.311"))
        self.assertFalse(self.ledger.list_calls()[0]["refunded"])

    def test_refund_is_not_applied_to_another_key(self):
        self.begin(task="provider-task-1")
        self.ledger.finish_call("call-1", "uncertain", "12.339")
        self.begin("call-2", key=KEYS[1], before="0", task="provider-task-2")
        self.ledger.finish_call("call-2", "uncertain", ".039")
        self.assertFalse(self.ledger.reconcile_task_outcomes(KEYS[1], {"provider-task-1": "failed"}, "0"))
        self.assertFalse(any(call["refunded"] for call in self.ledger.list_calls()))

    def test_successful_status_lookup_confirms_older_unknown_outcome_without_rebilling(self):
        self.begin(task="provider-task-1")
        self.ledger.finish_call("call-1", "uncertain", "12.339")
        self.begin("call-2", task="provider-task-2", before="12.339")
        self.ledger.finish_call("call-2", "success", "12.368")
        self.assertIn("provider-task-1", [row["task_id"] for row in self.ledger.get_task_reconciliation_candidates(KEYS[0])])
        self.assertTrue(self.ledger.reconcile_task_outcomes(KEYS[0], {"provider-task-1": "success"}, "12.368"))
        first = self.ledger.list_calls(task_id="provider-task-1")[0]
        self.assertEqual(first["outcome"], "success")
        self.assertEqual(first["cost_percent"], .039)
        self.assertEqual(self.ledger.snapshot()["percent"], 42.792)

    def test_float_noise_does_not_raise_false_warning_or_refund(self):
        self.begin(task="provider-task")
        self.ledger.finish_call("call-1", "uncertain", "12.339000000000001")
        self.assertTrue(self.ledger.reconcile_key(KEYS[0], "12.339"))
        self.assertFalse(self.ledger.snapshot()["error"])
        self.assertFalse(self.ledger.list_calls()[0]["refunded"])
        self.assertFalse(self.ledger.reconcile_key(KEYS[0], "12.338999"))
        self.assertTrue(self.ledger.snapshot()["error"])

    def test_settled_call_refresh_clears_old_error_without_rebilling(self):
        self.begin(task="provider-task")
        first = self.ledger.finish_call("call-1", "uncertain", "12.339")
        self.ledger.mark_key_error(KEYS[0])
        self.assertEqual(self.ledger.failed_key_fingerprints(), (KEYS[0],))
        self.ledger.finish_call("call-1", "success", "12.339")
        self.assertFalse(self.ledger.snapshot()["error"])
        self.assertEqual(self.ledger.failed_key_fingerprints(), ())
        self.assertEqual(self.ledger.list_calls()[0]["cost_percent"], first["cost_percent"])

    def test_old_database_additive_refund_migration_preserves_existing_calls(self):
        self.begin(task="provider-task")
        self.ledger.finish_call("call-1", "uncertain", "12.339")
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute("ALTER TABLE calls DROP COLUMN refund_usd")
        migrated = CostLedger(self.path)
        self.assertEqual(migrated.snapshot()["percent"], 42.821)
        self.assertEqual(migrated.list_calls()[0]["cost_percent"], .039)
        self.assertEqual(migrated.list_calls()[0]["refund_percent"], 0)
        self.assertTrue(migrated.reconcile_task_outcomes(KEYS[0], {"provider-task": "failed"}, "12.3"))
        self.assertEqual(migrated.snapshot()["percent"], 42.86)

    def test_reconciliation_candidates_distinguish_latest_and_older_unknown_calls(self):
        self.begin(task="provider-task-1")
        self.ledger.finish_call("call-1", "uncertain", "12.339")
        self.begin("call-2", task="provider-task-2", before="12.339")
        self.ledger.finish_call("call-2", "uncertain", "12.368")
        candidates = {row["call_id"]: row for row in self.ledger.get_task_reconciliation_candidates(KEYS[0])}
        self.assertFalse(candidates["call-1"]["is_latest"])
        self.assertTrue(candidates["call-2"]["is_latest"])


if __name__ == "__main__":
    unittest.main()
