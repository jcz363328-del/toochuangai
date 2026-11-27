from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from Department.视觉设计部.xiaoha import omnia_service as service
from Department.视觉设计部.xiaoha.omnia_key_pool import OmniaKeyPool, credential_fingerprint, current_omnia_credential


KEYS = tuple("test-service-credential-" + str(index) for index in range(5))
OMNIAKEY_API_BASE = "https://api.omniakey.com"


def load_omnia_api_key():
    current = current_omnia_credential()
    return current.api_key if current else KEYS[0]


class OmniaImageOutcomeUnknown(RuntimeError):
    pass


class OmniaServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        baseline = self.root / "baseline.json"
        baseline.write_text(json.dumps({
            "baseline_id": "verified-test-baseline", "balance_usd": "42.86",
            "usage_by_key": {credential_fingerprint(key): "0" for key in KEYS},
        }), encoding="utf-8")
        keys = self.root / "credentials.json"
        keys.write_text(json.dumps(KEYS), encoding="utf-8")
        env = patch.dict(os.environ, {
            "OMNIAKEY_API_KEYS_FILE": str(keys),
            "XIAOHA_OMNIA_BASELINE_FILE": str(baseline),
            "XIAOHA_OMNIA_COST_DB": str(self.root / "costs.sqlite3"),
            "XIAOHA_OMNIA_TRACKING_ENABLED": "1",
        })
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(service._cached_ledger.cache_clear)
        self.pool = OmniaKeyPool(self.root / "pool.sqlite3", poll_interval=0.005)
        pool_patch = patch.object(service, "get_omnia_key_pool", return_value=self.pool)
        pool_patch.start()
        self.addCleanup(pool_patch.stop)
        self.ledger = service.get_cost_ledger()

    def test_usage_endpoint_converts_cents_and_disables_redirects(self):
        response = Mock(status_code=200)
        response.json.return_value = {"object": "list", "total_usage": "123.456"}
        with patch.object(service.requests, "get", return_value=response) as get:
            self.assertEqual(service.fetch_usage(KEYS[0], OMNIAKEY_API_BASE + "/v1"), Decimal("1.23456"))
        self.assertEqual(get.call_args.args[0], OMNIAKEY_API_BASE + "/v1/dashboard/billing/usage")
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer " + KEYS[0])
        self.assertEqual(get.call_args.kwargs["timeout"], (5, 12))

    def test_usage_failure_never_exposes_response_or_credential(self):
        for body in ({"total_usage": True}, {"total_usage": "NaN"}, {"total_usage": -1}, {"error": KEYS[0]}):
            response = Mock(status_code=200)
            response.json.return_value = body
            with patch.object(service.requests, "get", return_value=response):
                with self.assertRaises(service.OmniaUsageUnavailable) as raised:
                    service.fetch_usage(KEYS[0])
            self.assertNotIn(KEYS[0], str(raised.exception))
        with patch.object(service.requests, "get", side_effect=RuntimeError(KEYS[0])):
            with self.assertRaises(service.OmniaUsageUnavailable) as raised:
                service.fetch_usage(KEYS[0])
        self.assertNotIn(KEYS[0], str(raised.exception))

    def test_usage_redirect_or_plain_http_is_not_followed(self):
        with patch.object(service.requests, "get", return_value=Mock(status_code=302)) as get:
            with self.assertRaises(service.OmniaUsageUnavailable):
                service.fetch_usage(KEYS[0])
            self.assertEqual(get.call_count, 1)
        with patch.object(service.requests, "get") as get:
            with self.assertRaises(service.OmniaUsageUnavailable):
                service.fetch_usage(KEYS[0], "http://api.omniakey.com")
            get.assert_not_called()

    def test_success_records_one_confirmed_cost_and_preserves_result(self):
        sentinel = object()

        @service.managed_omnia_call("image")
        def generate(model="nano-banana-2.1", resolution="2K"):
            self.assertIsNotNone(current_omnia_credential())
            self.assertEqual(self.pool.snapshot()["active"], 1)
            self.assertEqual(len(service.current_omnia_call_metadata()["key_fingerprint"]), 64)
            return sentinel

        with patch.object(service, "fetch_usage", side_effect=[Decimal(0), Decimal(".029")]):
            self.assertIs(generate(), sentinel)
        row = self.ledger.list_calls()[0]
        self.assertEqual((row["cost_percent"], row["model"], row["resolution"]), (.029, "nano-banana-2.1", "2K"))
        self.assertEqual((row["status"], row["outcome"]), ("settled", "success"))
        self.assertEqual(self.ledger.snapshot()["percent"], 42.831)
        self.assertEqual(service.current_omnia_call_metadata(), {})

    def test_five_concurrent_calls_have_distinct_keys_and_individual_costs(self):
        barrier = threading.Barrier(5)
        lock = threading.Lock()
        usage = {key: Decimal(0) for key in KEYS}
        selected = []

        def fetch(key, base):
            with lock:
                return usage[key]

        @service.managed_omnia_call("image")
        def generate(model="nano-banana-2.1", resolution="2K"):
            key = load_omnia_api_key()
            with lock:
                selected.append(key)
            barrier.wait(5)
            with lock:
                usage[key] += Decimal(".029")
            return "result"

        with patch.object(service, "fetch_usage", side_effect=fetch):
            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(lambda _: generate(), range(5)))
        self.assertEqual(len(set(selected)), 5)
        self.assertEqual(results, ["result"] * 5)
        rows = self.ledger.list_calls()
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["cost_percent"] == .029 for row in rows))
        self.assertEqual(self.ledger.snapshot()["percent"], 42.715)

    def test_after_usage_failure_keeps_successful_result_and_pending_cost(self):
        @service.managed_omnia_call("image")
        def generate(model="nano-banana-2.1"):
            return {"image": "completed"}

        with patch.object(service, "fetch_usage", side_effect=[Decimal(0), RuntimeError("private")]):
            self.assertEqual(generate(), {"image": "completed"})
        row = self.ledger.list_calls()[0]
        self.assertEqual((row["status"], row["outcome"], row["cost_percent"]), ("pending", "success", None))
        self.assertTrue(self.ledger.snapshot()["error"])

    def test_before_usage_failure_does_not_guess_individual_cost(self):
        @service.managed_omnia_call("text")
        def generate(model="text-model"):
            return "finished"

        with patch.object(service, "fetch_usage", side_effect=[RuntimeError("private"), Decimal(".01")]):
            self.assertEqual(generate(), "finished")
        row = self.ledger.list_calls()[0]
        self.assertEqual((row["status"], row["cost_percent"]), ("pending", None))
        self.assertEqual(self.ledger.snapshot()["percent"], 42.85)

    def test_unknown_call_and_resume_reuse_original_key_and_single_entry(self):
        original = []

        @service.managed_omnia_call("image")
        def generate(model="nano-banana-2.1"):
            original.append(load_omnia_api_key())
            service.record_omnia_task("task-original")
            raise OmniaImageOutcomeUnknown("远端结果尚未确认，未自动重新提交")

        @service.managed_omnia_call("image", resume=True)
        def resume_task(task_id, model="nano-banana-2.1"):
            self.assertEqual(load_omnia_api_key(), original[0])
            service.record_omnia_provider_status("success")
            return "recovered"

        with patch.object(service, "fetch_usage", side_effect=[Decimal(0), Decimal(0), Decimal(".029")]):
            with self.assertRaises(OmniaImageOutcomeUnknown):
                generate()
            before_id = self.ledger.list_calls()[0]["call_id"]
            self.assertEqual(self.pool.snapshot()["retained"], 1)
            self.assertEqual(resume_task("task-original"), "recovered")
        rows = self.ledger.list_calls()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["call_id"], before_id)
        self.assertEqual((rows[0]["cost_percent"], rows[0]["outcome"]), (.029, "success"))

    def test_legacy_resume_uses_original_key_without_creating_a_new_charge(self):
        @service.managed_omnia_call("image", resume=True)
        def resume_task(task_id, model="nano-banana-2.1"):
            self.assertEqual(load_omnia_api_key(), KEYS[0])
            return "recovered"

        with patch.object(service, "fetch_usage", return_value=Decimal(".029")):
            self.assertEqual(resume_task("legacy-task"), "recovered")
        self.assertEqual(self.ledger.list_calls(), [])
        self.assertEqual(self.ledger.snapshot()["percent"], 42.831)

    def test_provider_success_is_retained_when_asset_download_fails(self):
        @service.managed_omnia_call("image")
        def generate(model="nano-banana-2.1"):
            service.record_omnia_provider_status("success")
            raise RuntimeError("download unavailable")

        with patch.object(service, "fetch_usage", side_effect=[Decimal(0), Decimal(".029")]):
            with self.assertRaisesRegex(RuntimeError, "download unavailable"):
                generate()
        row = self.ledger.list_calls()[0]
        self.assertEqual((row["outcome"], row["cost_percent"]), ("success", .029))

    def test_failure_with_no_billing_confirmation_remains_pending(self):
        @service.managed_omnia_call("image")
        def generate(model="nano-banana-2.1"):
            raise RuntimeError("provider rejected")

        with patch.object(service, "fetch_usage", return_value=Decimal(0)):
            with self.assertRaisesRegex(RuntimeError, "provider rejected"):
                generate()
        row = self.ledger.list_calls()[0]
        self.assertEqual((row["status"], row["outcome"], row["cost_percent"]), ("pending", "failed", None))

    def test_internal_retry_and_nested_wrapper_create_one_entry(self):
        attempts = []

        @service.managed_omnia_call("text")
        def transport(model="text-model"):
            for index in range(3):
                attempts.append(index)
            return "ok"

        @service.managed_omnia_call("text")
        def generate(model="text-model"):
            return transport(model)

        with patch.object(service, "fetch_usage", side_effect=[Decimal(0), Decimal(".01")]) as fetch:
            self.assertEqual(generate(), "ok")
        self.assertEqual(attempts, [0, 1, 2])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(self.ledger.list_calls()), 1)

    def test_stream_context_uses_same_accounting_hooks(self):
        with patch.object(service, "fetch_usage", side_effect=[Decimal(0), Decimal(".01")]):
            with service.managed_omnia_context(primary_key=KEYS[0], model="stream-model"):
                self.assertIsNotNone(current_omnia_credential())
                service.record_omnia_provider_status("success")
        self.assertEqual(self.ledger.list_calls()[0]["cost_percent"], .01)

    def test_disabled_tracking_leaves_legacy_function_untouched(self):
        @service.managed_omnia_call("image")
        def generate(model="legacy"):
            self.assertIsNone(current_omnia_credential())
            return "legacy-result"

        with patch.dict(os.environ, {"XIAOHA_OMNIA_TRACKING_ENABLED": "0"}), \
                patch.object(service, "fetch_usage") as fetch:
            self.assertEqual(generate(), "legacy-result")
            fetch.assert_not_called()
        self.assertEqual(self.ledger.list_calls(), [])

    def test_ledger_restart_keeps_original_baseline(self):
        self.ledger.reconcile_key(credential_fingerprint(KEYS[0]), Decimal(".029"))
        service._cached_ledger.cache_clear()
        self.assertEqual(service.get_cost_ledger().snapshot()["percent"], 42.831)

    def test_task_binding_failure_is_unknown_and_never_submits_again(self):
        generated = []

        @service.managed_omnia_call("image")
        def generate(model="nano-banana-2.1"):
            generated.append(True)
            service.record_omnia_task("task-accepted")

        with patch.object(service, "fetch_usage", return_value=Decimal(0)), \
                patch.object(self.ledger, "attach_task", side_effect=RuntimeError("database unavailable")):
            with self.assertRaises(service.OmniaAccountingOutcomeUnknown):
                generate()
        self.assertEqual(generated, [True])
        self.assertEqual(self.ledger.list_calls()[0]["outcome"], "uncertain")
        self.assertEqual(self.pool.snapshot()["retained"], 1)

    def test_delayed_billing_settles_before_next_same_key_call(self):
        one_key = self.root / "one-key.json"
        one_key.write_text(json.dumps([KEYS[0]]), encoding="utf-8")

        @service.managed_omnia_call("image")
        def generate(model="nano-banana-2.1"):
            return "done"

        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": str(one_key)}), \
                patch.object(service, "fetch_usage", side_effect=[Decimal(0), Decimal(0),
                                                                  Decimal(".029"), Decimal(".058")]):
            generate()
            self.assertEqual(self.ledger.list_calls()[0]["status"], "pending")
            generate()
        rows = self.ledger.list_calls()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["status"] == "settled" and row["cost_percent"] == .029 for row in rows))
        self.assertEqual(self.ledger.snapshot()["percent"], 42.802)

    def test_confirmed_rejection_can_record_final_zero(self):
        @service.managed_omnia_call("image")
        def generate(model="nano-banana-2.1"):
            service.record_omnia_provider_status("rejected")
            raise RuntimeError("invalid provider request")

        with patch.object(service, "fetch_usage", return_value=Decimal(0)):
            with self.assertRaisesRegex(RuntimeError, "invalid provider request"):
                generate()
        row = self.ledger.list_calls()[0]
        self.assertEqual((row["outcome"], row["status"], row["cost_percent"]), ("failed", "settled", 0.0))

    def test_fallback_model_updates_existing_row(self):
        @service.managed_omnia_call("text")
        def generate(model="preferred-model"):
            service.record_omnia_model("actual-fallback-model")
            return "finished"

        with patch.object(service, "fetch_usage", side_effect=[Decimal(0), Decimal(".01")]):
            generate()
        rows = self.ledger.list_calls()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["model"], "actual-fallback-model")

    def test_successful_retry_overrides_prior_attempt_rejection(self):
        @service.managed_omnia_call("text")
        def generate(model="text-model"):
            service.record_omnia_provider_status("rejected")
            return "retry succeeded"

        with patch.object(service, "fetch_usage", side_effect=[Decimal(0), Decimal(".01")]):
            generate()
        row = self.ledger.list_calls()[0]
        self.assertEqual((row["outcome"], row["cost_percent"]), ("success", .01))

    def test_unknown_retry_cannot_inherit_prior_rejection_zero_charge(self):
        @service.managed_omnia_call("text")
        def generate(model="text-model"):
            service.record_omnia_provider_status("rejected")
            raise OmniaImageOutcomeUnknown("provider_submit_uncertain")

        with patch.object(service, "fetch_usage", return_value=Decimal(0)):
            with self.assertRaises(OmniaImageOutcomeUnknown):
                generate()
        row = self.ledger.list_calls()[0]
        self.assertEqual((row["outcome"], row["cost_percent"]), ("uncertain", None))

    def test_receipt_restores_original_nonprimary_key_after_crash_before_binding(self):
        fingerprint = credential_fingerprint(KEYS[3])
        self.ledger.begin_call("call-before-crash", "", fingerprint, "nano-banana-2.1", "2K", Decimal(0))
        receipt = self.root / "receipts.jsonl"
        receipt.write_text(json.dumps({"task_id": "accepted-before-crash", "call_id": "call-before-crash",
                                       "key_fingerprint": fingerprint}) + "\n", encoding="utf-8")
        self.assertIsNone(self.ledger.find_call_by_task("accepted-before-crash"))
        self.assertEqual(self.pool.task_fingerprint("accepted-before-crash"), "")

        @service.managed_omnia_call("image", resume=True)
        def resume_task(task_id, model="nano-banana-2.1"):
            self.assertEqual(load_omnia_api_key(), KEYS[3])
            return "original task recovered"

        with patch.dict(globals(), {"OMNIAKEY_TASK_RECEIPTS_FILE": receipt}), \
                patch.object(service, "fetch_usage", return_value=Decimal(".029")) as fetch:
            self.assertEqual(resume_task("accepted-before-crash"), "original task recovered")
            self.assertEqual(fetch.call_args.args[0], KEYS[3])
        rows = self.ledger.list_calls()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["call_id"], rows[0]["task_id"], rows[0]["cost_percent"]),
                         ("call-before-crash", "accepted-before-crash", .029))
        self.assertEqual(self.pool.task_fingerprint("accepted-before-crash"), fingerprint)

    def test_receipt_recovers_ledger_binding_when_pool_binding_was_already_saved(self):
        fingerprint = credential_fingerprint(KEYS[4])
        self.ledger.begin_call("call-pool-bound", "", fingerprint, "nano-banana-2.1", "2K", Decimal(0))
        with self.pool.hold(KEYS, preferred_fingerprint=fingerprint) as credential:
            credential.bind_task("pool-bound-task")
        receipt = self.root / "receipts.jsonl"
        receipt.write_text(json.dumps({"task_id": "pool-bound-task", "call_id": "call-pool-bound",
                                       "key_fingerprint": fingerprint}) + "\n", encoding="utf-8")
        with patch.object(service, "fetch_usage", return_value=Decimal(".029")):
            with service.managed_omnia_context(primary_key=KEYS[0], model="nano-banana-2.1",
                                               task_id="pool-bound-task", resume=True, receipt_path=receipt):
                self.assertEqual(load_omnia_api_key(), KEYS[4])
        self.assertEqual(self.ledger.find_call_by_task("pool-bound-task")["call_id"], "call-pool-bound")
        self.assertEqual(len(self.ledger.list_calls()), 1)

    def test_new_receipt_without_matching_ledger_never_falls_back_to_primary(self):
        receipt = self.root / "receipts.jsonl"
        receipt.write_text(json.dumps({"task_id": "lost-ledger-task", "call_id": "missing-call",
                                       "key_fingerprint": credential_fingerprint(KEYS[2])}) + "\n", encoding="utf-8")
        with patch.object(service, "fetch_usage") as fetch:
            with self.assertRaisesRegex(RuntimeError, "回执与调用记录不一致"):
                with service.managed_omnia_context(primary_key=KEYS[0], model="nano-banana-2.1",
                                                   task_id="lost-ledger-task", resume=True, receipt_path=receipt):
                    self.fail("Must not query a receipt task using an unrelated key")
            fetch.assert_not_called()

    def test_partial_new_receipt_never_falls_back_to_primary(self):
        receipt = self.root / "receipts.jsonl"
        receipt.write_text(json.dumps({"task_id": "partial-receipt-task", "call_id": "partial-call"}) + "\n",
                           encoding="utf-8")
        with patch.object(service, "fetch_usage") as fetch:
            with self.assertRaisesRegex(RuntimeError, "回执不完整"):
                with service.managed_omnia_context(primary_key=KEYS[0], model="nano-banana-2.1",
                                                   task_id="partial-receipt-task", resume=True, receipt_path=receipt):
                    self.fail("Partial new receipt must not use the primary fallback")
            fetch.assert_not_called()

    def test_original_single_key_receipt_retains_legacy_recovery(self):
        receipt = self.root / "receipts.jsonl"
        receipt.write_text(json.dumps({"task_id": "old-receipt-task", "model": "nano-banana-2.1"}) + "\n",
                           encoding="utf-8")
        with patch.object(service, "fetch_usage", return_value=Decimal(".029")):
            with service.managed_omnia_context(primary_key=KEYS[0], model="nano-banana-2.1",
                                               task_id="old-receipt-task", resume=True, receipt_path=receipt):
                self.assertEqual(load_omnia_api_key(), KEYS[0])
        self.assertEqual(self.ledger.list_calls(), [])

    def test_cold_ledger_getter_initializes_only_once_across_threads(self):
        service._cached_ledger.cache_clear()
        barrier = threading.Barrier(8)
        constructor = service.CostLedger

        def get_ledger(_):
            barrier.wait(5)
            return service.get_cost_ledger()

        with patch.object(service, "CostLedger", wraps=constructor) as construct:
            with ThreadPoolExecutor(max_workers=8) as executor:
                instances = list(executor.map(get_ledger, range(8)))
        self.assertEqual(len({id(instance) for instance in instances}), 1)
        self.assertEqual(construct.call_count, 1)

    def test_task_status_lookup_uses_original_key_get_only(self):
        response = Mock(status_code=200)
        response.json.return_value = {"id": "original-task", "status": "failed",
                                      "error": {"code": "provider_submit_uncertain"}}
        with patch.object(service.requests, "get", return_value=response) as get, \
                patch.object(service.requests, "post") as post:
            self.assertEqual(service.fetch_task_status(KEYS[3], "original-task"), "failed")
        post.assert_not_called()
        self.assertEqual(get.call_args.args[0], OMNIAKEY_API_BASE + "/v1/media/tasks/original-task")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer " + KEYS[3])
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_task_status_failure_exposes_no_private_body(self):
        response = Mock(status_code=200)
        response.json.return_value = {"error": KEYS[0]}
        with patch.object(service.requests, "get", return_value=response):
            with self.assertRaises(service.OmniaUsageUnavailable) as raised:
                service.fetch_task_status(KEYS[0], "task")
        self.assertNotIn(KEYS[0], str(raised.exception))

    def test_terminal_provider_failure_overrides_uncertain_error_code(self):
        @service.managed_omnia_call("image")
        def generate(model="model"):
            service.record_omnia_provider_status("failed")
            raise RuntimeError("provider_submit_uncertain")

        with patch.object(service, "fetch_usage", side_effect=[Decimal(0), Decimal(".039")]):
            with self.assertRaisesRegex(RuntimeError, "provider_submit_uncertain"):
                generate()
        self.assertEqual(self.ledger.list_calls()[0]["outcome"], "failed")

    def test_refund_is_reconciled_before_next_same_key_generation(self):
        fingerprint = credential_fingerprint(KEYS[0])
        self.ledger.begin_call("previous-failure", "original-failed-task", fingerprint, "model", "4K", 0)
        self.ledger.finish_call("previous-failure", "uncertain", Decimal(".039"))
        one_key = self.root / "one-key.json"
        one_key.write_text(json.dumps([KEYS[0]]), encoding="utf-8")

        @service.managed_omnia_call("image")
        def generate(model="model", resolution="2K"):
            self.assertEqual(self.ledger.snapshot()["percent"], 42.86)
            return "generated"

        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": str(one_key)}), \
                patch.object(service, "fetch_task_status", return_value="failed") as status, \
                patch.object(service, "fetch_usage", side_effect=[Decimal(0), Decimal(".029")]):
            self.assertEqual(generate(), "generated")
        rows = self.ledger.list_calls()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["cost_percent"], .029)
        self.assertEqual(rows[1]["cost_percent"], 0)
        self.assertTrue(rows[1]["refunded"])
        self.assertEqual(self.ledger.snapshot()["percent"], 42.831)
        status.assert_called_once_with(KEYS[0], "original-failed-task", OMNIAKEY_API_BASE)

    def test_unconfirmed_counter_drop_blocks_new_paid_call_until_refund_can_be_verified(self):
        fingerprint = credential_fingerprint(KEYS[0])
        self.ledger.begin_call("previous-failure", "failed-task", fingerprint, "model", "4K", 0)
        self.ledger.finish_call("previous-failure", "uncertain", Decimal(".039"))
        one_key = self.root / "one-key.json"
        one_key.write_text(json.dumps([KEYS[0]]), encoding="utf-8")
        submitted = []

        @service.managed_omnia_call("image")
        def generate(model="model"):
            submitted.append(True)
            return "must not submit"

        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": str(one_key)}), \
                patch.object(service, "fetch_task_status", side_effect=RuntimeError("temporary status failure")), \
                patch.object(service, "fetch_usage", return_value=Decimal(0)):
            with self.assertRaisesRegex(RuntimeError, "本次尚未提交"):
                generate()
        self.assertEqual(submitted, [])
        self.assertEqual(len(self.ledger.list_calls()), 1)
        self.assertEqual(self.ledger.snapshot()["percent"], 42.821)
        self.assertEqual(self.pool.snapshot(), {"active": 0, "retained": 0})
        with self.pool.hold(KEYS, preferred_fingerprint=fingerprint) as credential:
            repaired = service.reconcile_omnia_key(
                self.ledger, credential, usage_fetcher=lambda key: Decimal(0),
                task_status_fetcher=lambda key, task: "failed",
            )
        self.assertTrue(repaired["reconciled"])
        self.assertEqual(len(self.ledger.list_calls()), 1)
        self.assertEqual(self.ledger.snapshot()["percent"], 42.86)
        self.assertTrue(self.ledger.list_calls()[0]["refunded"])

    def test_known_failure_waits_for_refund_before_reusing_key(self):
        fingerprint = credential_fingerprint(KEYS[0])
        self.ledger.begin_call("previous-failure", "failed-task", fingerprint, "model", "4K", 0)
        self.ledger.finish_call("previous-failure", "uncertain", Decimal(".039"))
        one_key = self.root / "one-key.json"
        one_key.write_text(json.dumps([KEYS[0]]), encoding="utf-8")
        submitted = []

        @service.managed_omnia_call("image")
        def generate(model="model"):
            submitted.append(True)

        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": str(one_key)}), \
                patch.object(service, "fetch_task_status", return_value="failed"), \
                patch.object(service, "fetch_usage", return_value=Decimal(".039")):
            with self.assertRaisesRegex(RuntimeError, "本次尚未提交"):
                generate()
        self.assertEqual(submitted, [])
        self.assertEqual(len(self.ledger.list_calls()), 1)
        self.assertEqual(self.ledger.list_calls()[0]["outcome"], "failed")
        self.assertFalse(self.ledger.list_calls()[0]["refunded"])
        with self.pool.hold(KEYS, preferred_fingerprint=fingerprint) as credential:
            repaired = service.reconcile_omnia_key(
                self.ledger, credential, usage_fetcher=lambda key: Decimal(0),
                task_status_fetcher=lambda key, task: "failed",
            )
        self.assertFalse(repaired["blocked"])
        self.assertTrue(self.ledger.list_calls()[0]["refunded"])

    def test_remote_task_still_running_does_not_overlap_new_generation(self):
        fingerprint = credential_fingerprint(KEYS[0])
        self.ledger.begin_call("previous-unknown", "running-task", fingerprint, "model", "4K", 0)
        self.ledger.finish_call("previous-unknown", "uncertain", Decimal(".039"))
        one_key = self.root / "one-key.json"
        one_key.write_text(json.dumps([KEYS[0]]), encoding="utf-8")

        @service.managed_omnia_call("image")
        def generate(model="model"):
            self.fail("An existing remote task must not overlap a new paid request")

        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": str(one_key)}), \
                patch.object(service, "fetch_task_status", return_value=None), \
                patch.object(service, "fetch_usage", return_value=Decimal(".039")):
            with self.assertRaisesRegex(RuntimeError, "本次尚未提交"):
                generate()
        self.assertEqual(len(self.ledger.list_calls()), 1)
        self.assertEqual(self.ledger.list_calls()[0]["outcome"], "uncertain")


if __name__ == "__main__":
    unittest.main()
