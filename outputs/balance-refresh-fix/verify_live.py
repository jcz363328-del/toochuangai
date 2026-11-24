"""Read-only provider verification of the already refunded 4K task."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, "/app")
from 图片 import openrouter_image_site as site
from 图片.omnia_key_pool import load_omnia_api_keys
from 图片.omnia_service import get_cost_ledger
from 图片.balance_provider import load_balance_snapshot

manifest = json.loads(Path("/tmp/xiaoha-balance-refund/runtime-release/manifest.json").read_text())
for entry in manifest:
    assert hashlib.sha256((Path("/app/图片") / entry["name"]).read_bytes()).hexdigest() == entry["after"]
assert len(set(load_omnia_api_keys(site.load_omnia_api_key()))) == 5
ledger = get_cost_ledger()

snapshots = []
for _ in range(2):
    snapshot = load_balance_snapshot(force=True, primary_loader=site.load_omnia_api_key)
    assert snapshot["percent"] is not None and not snapshot["error"], "Usage refresh did not reconcile"
    calls = [row for row in snapshot["calls"] if row["task_id"].startswith("task_Iyv5eEbt2M7")]
    assert len(calls) == 1, "Expected original 4K task record"
    call = calls[0]
    assert call["outcome"] == "failed" and call["status"] == "settled"
    assert call["refunded"] and call["cost_percent"] == 0
    assert abs(call["refund_percent"] - 0.039) < 1e-10
    snapshots.append({"percent": snapshot["percent"], "error": snapshot["error"],
                      "pending_calls": snapshot["pending_calls"],
                      "active_calls": snapshot["active_calls"],
                      "call_records": len(snapshot["calls"]),
                      "refunded_call": {key: call[key] for key in
                          ("resolution", "channel", "outcome", "cost_percent", "refund_percent")}})

assert snapshots[0]["refunded_call"] == snapshots[1]["refunded_call"]
print(json.dumps({"files_verified": len(manifest), "channels": 5,
                  "snapshots": snapshots, "refund_idempotent": True,
                  "generation_requests_sent_by_verification": 0}, ensure_ascii=False))
