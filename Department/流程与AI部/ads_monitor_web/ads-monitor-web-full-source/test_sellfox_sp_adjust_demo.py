import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import sellfox_sp_adjust_demo as demo


NOW = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)


def recommendation(**overrides):
    row = {
        "shop_id": "101",
        "shop_name": "demo-US",
        "currency": "USD",
        "entity_type": "keyword",
        "campaign_id": "201",
        "target_id": "301",
        "target_text": "lash clusters",
        "action_code": "DECREASE_BID",
        "current_value": "1.00",
        "spend": "80",
        "orders": "8",
        "clicks": "60",
        "acos": "0.50",
        "target_acos": "0.30",
        "rule_id": "high_acos",
        "reason": "ACoS above threshold",
        "data_status": "complete",
    }
    row.update(overrides)
    return row


class FakeMcp:
    def __init__(self, current="1.00", fail_write=False):
        self.current = current
        self.fail_write = fail_write
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def list_tools(self):
        return {
            "get_sp_keyword_list": {
                "type": "object",
                "properties": {"shop_id": {"type": "string"}},
                "required": ["shop_id"],
            },
            "edit_sp_targeting": {
                "type": "object",
                "properties": {
                    "shop_id": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["shop_id", "items"],
            },
        }

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "get_sp_keyword_list":
            return {"structuredContent": {"data": {"itemList": [{
                "keywordId": "301", "bid": self.current, "state": "enabled"
            }]}}}
        if name == "edit_sp_targeting":
            if self.fail_write:
                return {"structuredContent": {"data": {
                    "successIds": [], "failList": [{"id": "301", "errorMsg": "failed"}]
                }}}
            self.current = str(arguments["items"][0]["bid"])
            return {"structuredContent": {"data": {"successIds": ["301"], "failList": []}}}
        raise AssertionError(name)


class SpAdjustDemoTests(unittest.TestCase):
    def write_source(self, directory, rows, age=timedelta(hours=1), now=NOW):
        path = Path(directory) / "source.json"
        path.write_text(json.dumps({
            "meta": {
                "mode": "live",
                "run_id": "20260820-live-test",
                "generated_at": (now - age).isoformat(),
                "coverage": "complete",
            },
            "recommendations": rows,
        }), encoding="utf-8")
        return path

    def write_realtime(self, directory, source, now, gate="NO_OBJECTION"):
        path = Path(directory) / "realtime.json"
        path.write_text(json.dumps({
            "meta": {
                "mode": "live",
                "layer": "realtime",
                "run_id": "realtime-test",
                "generated_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=30)).isoformat(),
                "mature_ref": {"sha256": demo.file_sha256(source)},
            },
            "campaign_snapshots": [{
                "shop_id": "101",
                "campaign_id": "201",
                "execution_gate": gate,
                "freshness": {"status": "fresh"},
            }],
        }), encoding="utf-8")
        return path

    def executable_plan(self, directory, client, now):
        source = self.write_source(directory, [recommendation()], now=now)
        realtime = self.write_realtime(directory, source, now)
        plan_path = Path(directory) / "decision-plan.json"
        plan = demo.build_plan(source, realtime_source=realtime, now=now)
        required = demo.required_tools_for(plan["items"][0])
        schemas = client.list_tools()
        plan["mcp_preflight"] = "CURRENT_VALUE_VERIFIED"
        plan["mcp_preflight_at"] = now.isoformat()
        plan["mcp_tools_verified"] = sorted(required)
        plan["mcp_schema_sha256"] = demo.schema_digest(schemas, required)
        plan["approval_signature"] = demo.plan_signature(plan, "secret")
        demo.atomic_json(plan_path, plan)
        return source, plan_path, plan

    def test_builds_one_dry_run_with_smaller_safe_step(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_source(directory, [recommendation()])
            plan = demo.build_plan(source, now=NOW)
        self.assertEqual("DRY_RUN", plan["mode"])
        self.assertFalse(plan["execution"]["sent"])
        self.assertEqual(1, len(plan["items"]))
        self.assertEqual("0.95", plan["items"][0]["proposed_value"])
        self.assertEqual("edit_sp_targeting", plan["items"][0]["mcp_call"]["tool"])

    def test_rejects_demo_and_stale_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_source(directory, [recommendation()], age=timedelta(days=4))
            with self.assertRaises(demo.DemoError):
                demo.build_plan(source, now=NOW)
            payload = json.loads(source.read_text(encoding="utf-8"))
            payload["meta"]["mode"] = "demo"
            source.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(demo.DemoError):
                demo.build_plan(source, now=NOW)

    def test_rejects_synthetic_target_id_and_bad_metrics(self):
        self.assertIsNone(demo.candidate_from(recommendation(target_id="text:abc")))
        self.assertIsNone(demo.candidate_from(recommendation(orders="1")))
        self.assertIsNone(demo.candidate_from(recommendation(currency="CAD")))

    def test_product_target_and_increase_bid_mapping(self):
        item = demo.candidate_from(recommendation(
            entity_type="target",
            action_code="INCREASE_BID",
            rule_id="low_acos_scale",
            acos="0.20",
        ))
        self.assertEqual("product", item["targeting_type"])
        self.assertEqual("1.03", item["proposed_value"])
        self.assertEqual("edit_sp_targeting", item["mcp_call"]["tool"])

    def test_current_value_check_blocks_drift(self):
        client = FakeMcp(current="1.10")
        item = demo.candidate_from(recommendation())
        with self.assertRaises(demo.DemoError):
            demo.verify_current(client, item, "current_value")
        self.assertEqual(["get_sp_keyword_list"], [call[0] for call in client.calls])

    def test_realtime_gate_blocks_execution_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_source(directory, [recommendation()])
            realtime = self.write_realtime(directory, source, NOW, gate="BLOCK")
            plan = demo.build_plan(source, realtime_source=realtime, now=NOW)
            with patch.object(demo, "DEFAULT_REALTIME_SOURCE", realtime):
                with self.assertRaises(demo.DemoError):
                    demo.verify_realtime_evidence(plan, plan["items"][0], NOW)

    def test_execution_needs_exact_confirm_and_environment_gate(self):
        item = demo.candidate_from(recommendation())
        plan = {
            "version": 1,
            "mode": "DRY_RUN",
            "created_at": NOW.isoformat(),
            "expires_at": (NOW + demo.PLAN_TTL).isoformat(),
            "source": {
                "run_id": "run-1",
                "generated_at": (NOW - timedelta(hours=1)).isoformat(),
                "sha256": "a" * 64,
            },
            "items": [item],
            "mcp_preflight": "CURRENT_VALUE_VERIFIED",
            "approval_signature": "test-only",
            "execution": {"sent": False},
        }
        plan["plan_id"] = demo.plan_id_for(
            plan["source"]["run_id"],
            plan["source"]["generated_at"],
            plan["source"]["sha256"],
            plan["created_at"],
            item,
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(demo.DemoError):
                demo.validate_execution(plan, plan["plan_id"], NOW)
        with patch.dict(os.environ, {"SELLFOX_SP_WRITE_ENABLED": demo.WRITE_GATE}):
            with self.assertRaises(demo.DemoError):
                demo.validate_execution(plan, "wrong", NOW)
            self.assertEqual(
                "301", demo.validate_execution(plan, plan["plan_id"], NOW)["object_id"]
            )
            plan["items"][0]["proposed_value"] = "0.90"
            with self.assertRaises(demo.DemoError):
                demo.validate_execution(plan, plan["plan_id"], NOW)

    def test_fake_execution_writes_once_and_verifies(self):
        runtime = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            client = FakeMcp()
            source, plan_path, plan = self.executable_plan(directory, client, runtime)
            with (
                patch.object(demo, "DEFAULT_SOURCE", source),
                patch.object(demo, "DEFAULT_REALTIME_SOURCE", Path(plan["realtime"]["path"])),
                patch.object(demo, "DEFAULT_PLAN", plan_path),
                patch.object(demo, "load_api_credentials", return_value=("id", "secret")),
                patch.object(demo, "McpClient", side_effect=lambda *_: client),
                patch.dict(os.environ, {"SELLFOX_SP_WRITE_ENABLED": demo.WRITE_GATE}),
            ):
                result = demo.execute_plan(plan_path, plan["plan_id"], demo.DEFAULT_MCP_URL)
            self.assertTrue(result["verified"])
            self.assertEqual(
                ["get_sp_keyword_list", "edit_sp_targeting", "get_sp_keyword_list"],
                [name for name, _ in client.calls],
            )
            audit = json.loads(Path(result["audit"]).read_text(encoding="utf-8"))
            self.assertEqual("VERIFIED", audit["status"])

    def test_partial_write_is_unknown_and_cannot_retry(self):
        runtime = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            client = FakeMcp(fail_write=True)
            source, plan_path, plan = self.executable_plan(directory, client, runtime)
            with (
                patch.object(demo, "DEFAULT_SOURCE", source),
                patch.object(demo, "DEFAULT_REALTIME_SOURCE", Path(plan["realtime"]["path"])),
                patch.object(demo, "DEFAULT_PLAN", plan_path),
                patch.object(demo, "load_api_credentials", return_value=("id", "secret")),
                patch.object(demo, "McpClient", side_effect=lambda *_: client),
                patch.dict(os.environ, {"SELLFOX_SP_WRITE_ENABLED": demo.WRITE_GATE}),
            ):
                with self.assertRaises(demo.DemoError):
                    demo.execute_plan(plan_path, plan["plan_id"], demo.DEFAULT_MCP_URL)
                with self.assertRaises(demo.DemoError):
                    demo.execute_plan(plan_path, plan["plan_id"], demo.DEFAULT_MCP_URL)
            audit_path = plan_path.parent / f"execution-{plan['plan_id']}.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual("UNKNOWN", audit["status"])
            self.assertEqual(1, sum(name == "edit_sp_targeting" for name, _ in client.calls))

    def test_execution_lock_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            with demo.execution_lock(Path(directory)):
                with self.assertRaises(demo.DemoError):
                    with demo.execution_lock(Path(directory)):
                        pass


if __name__ == "__main__":
    unittest.main()
