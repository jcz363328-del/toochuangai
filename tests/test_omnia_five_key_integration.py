"""Real application adapters, scheduling, key context and accounting together."""
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from Department.视觉设计部.xiaoha import openrouter_image_site as site
from Department.视觉设计部.xiaoha import omnia_service as service
from Department.视觉设计部.xiaoha.omnia_key_pool import credential_fingerprint


class FiveKeyApplicationIntegrationTests(unittest.TestCase):
    def test_six_real_adapter_calls_use_five_keys_and_deduct_each_once(self):
        keys = [f"integration-channel-{i}" for i in range(5)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            keyfile, baseline = root / "keys.json", root / "baseline.json"
            keyfile.write_text(json.dumps(keys), encoding="utf-8")
            baseline.write_text(json.dumps({"baseline_id": "integration", "balance_usd": "42.86",
                "usage_by_key": {credential_fingerprint(key): "0" for key in keys}}), encoding="utf-8")
            env = {"OMNIAKEY_API_KEY": keys[0], "OMNIAKEY_API_KEYS_FILE": str(keyfile),
                   "XIAOHA_OMNIA_BASELINE_FILE": str(baseline),
                   "XIAOHA_OMNIA_COST_DB": str(root / "costs.sqlite3"),
                   "XIAOHA_OMNIA_KEY_DB": str(root / "keys.sqlite3"),
                   "XIAOHA_REQUEST_DB": str(root / "requests.sqlite3"),
                   "XIAOHA_OMNIA_TRACKING_ENABLED": "1"}
            output = io.BytesIO()
            Image.new("RGB", (8, 8), "blue").save(output, format="PNG")
            encoded = base64.b64encode(output.getvalue()).decode()
            lock = threading.Lock()
            five_running, release = threading.Event(), threading.Event()
            running, peaks, seen, usage = set(), [], [], dict.fromkeys(keys, 0)

            def read_usage(_url, *, headers, **_kwargs):
                key = headers["Authorization"][7:]
                with lock:
                    total = usage[key]
                return Mock(status_code=200, json=lambda: {"total_usage": total})

            def generate(_url, *, headers, **_kwargs):
                key = headers["Authorization"][7:]
                with lock:
                    self.assertNotIn(key, running, "Two requests shared one active key")
                    running.add(key)
                    peaks.append(len(running))
                    seen.append(key)
                    if len(running) == 5:
                        five_running.set()
                if not release.wait(10):
                    raise AssertionError("Five concurrent calls were not admitted")
                with lock:
                    usage[key] += 3  # Provider counter uses cents: each call costs 0.03%.
                    running.remove(key)
                return Mock(status_code=200, headers={}, json=lambda: {"data": [{"b64_json": encoded}]})

            with patch.dict(os.environ, env), patch.object(service.requests, "get", side_effect=read_usage), \
                    patch.object(site.requests, "post", side_effect=generate) as post:
                # Do not reuse an application limiter cached before the isolated environment.
                from Department.视觉设计部.xiaoha.request_limits import _cached_limiter
                from Department.视觉设计部.xiaoha.omnia_key_pool import _cached_pool
                _cached_limiter.cache_clear()
                _cached_pool.cache_clear()
                try:
                    with ThreadPoolExecutor(max_workers=6) as executor:
                        jobs = [executor.submit(site.call_omnia_sync_image_api,
                                                site.NANO_BANANA_MODEL, "integration") for _ in range(6)]
                        try:
                            self.assertTrue(five_running.wait(10))
                            self.assertEqual(len(seen), 5)
                        finally:
                            release.set()
                        results = [job.result(15) for job in jobs]
                    self.assertTrue(all(item["images"] for item in results))
                    self.assertEqual(post.call_count, 6)
                    self.assertEqual(max(peaks), 5)
                    self.assertEqual(set(seen), set(keys))
                    ledger = service.get_cost_ledger()
                    self.assertEqual(len(ledger.list_calls()), 6)
                    self.assertTrue(all(row["cost_percent"] == 0.03 for row in ledger.list_calls()))
                    self.assertAlmostEqual(ledger.snapshot()["percent"], 42.68)
                    self.assertEqual(ledger.snapshot()["pending_calls"], 0)
                    with self.assertRaises(ValueError):
                        site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, "validation", size="invalid")
                    self.assertEqual(post.call_count, 6)
                    self.assertEqual(ledger.list_calls()[0]["cost_percent"], 0)
                    site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, "after validation")
                    self.assertEqual(ledger.list_calls()[0]["cost_percent"], 0.03)
                    rejection = Mock(status_code=400, headers={}, json=lambda: {"error": {"message": "rejected"}})
                    with patch.object(site.requests, "post", return_value=rejection), self.assertRaises(RuntimeError):
                        site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, "rejection")
                    self.assertEqual(ledger.list_calls()[0]["cost_percent"], 0)
                    site.call_omnia_sync_image_api(site.NANO_BANANA_MODEL, "after rejection")
                    self.assertEqual(ledger.list_calls()[0]["cost_percent"], 0.03)
                    self.assertAlmostEqual(ledger.snapshot()["percent"], 42.62)
                    self.assertEqual(ledger.snapshot()["pending_calls"], 0)
                finally:
                    _cached_limiter.cache_clear()
                    _cached_pool.cache_clear()
                    service._cached_ledger.cache_clear()


if __name__ == "__main__":
    unittest.main()
