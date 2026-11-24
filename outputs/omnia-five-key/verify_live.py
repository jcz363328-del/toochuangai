import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, "/app")
from 图片 import openrouter_image_site as site
from 图片.omnia_key_pool import load_omnia_api_keys
from 图片.omnia_service import get_cost_ledger
from 图片.balance_provider import load_balance_snapshot
from 图片.request_limits import get_request_limiter

manifest = json.loads(Path("/tmp/xiaoha-five-key/runtime-release/manifest.json").read_text())
for entry in manifest:
    assert hashlib.sha256((Path("/app/图片") / entry["name"]).read_bytes()).hexdigest() == entry["after"]
keys = load_omnia_api_keys(site.load_omnia_api_key())
assert len(keys) == len(set(keys)) == 5
limiter = get_request_limiter()
assert limiter.provider_limit == limiter.group_limits["omnia_image"] == 5
runtime = site.TaskRuntime()
assert runtime.max_workers == runtime.max_account_workers == 5
runtime.shutdown()
snapshot = load_balance_snapshot(force=True, primary_loader=site.load_omnia_api_key)
assert snapshot["percent"] is not None and not snapshot["error"], "Read-only usage verification failed"
assert all("usd" not in key.lower() for key in snapshot)
assert site.XIAOHA_BALANCE_KEY == "__balance__"
print(json.dumps({"files_verified": len(manifest), "channels": len(keys),
                  "concurrency": limiter.provider_limit, "balance_percent": snapshot["percent"],
                  "pending_calls": snapshot["pending_calls"], "active_calls": snapshot["active_calls"],
                  "call_records": len(snapshot["calls"]), "usage_refresh_ok": not snapshot["error"],
                  "generation_requests_sent_by_verification": 0}, ensure_ascii=False))
