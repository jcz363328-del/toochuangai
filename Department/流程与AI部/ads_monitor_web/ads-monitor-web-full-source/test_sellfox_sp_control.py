import json
import tempfile
import unittest
from pathlib import Path

from sellfox_sp_control import SpControlError, SpControlService


CAMPAIGN_ID = "437874027293037"
TARGET_ID = "310616146035497"
GROUP_ID = "288236452768823"

TARGETING_SCHEMA = {
    "type": "object",
    "properties": {
        "shop_id": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "targetId": {"type": "string"},
                    "targetingType": {"type": "string"},
                    "bid": {"type": "number"},
                },
                "required": ["targetId", "targetingType", "bid"],
            },
        },
    },
    "required": ["shop_id", "items"],
}


def campaign_context(target_id=TARGET_ID):
    return {
        "campaign": {"campaignId": CAMPAIGN_ID},
        "structure": {
            "ad_groups": [{"groupId": GROUP_ID}],
            "keywords": [{"keywordId": target_id}],
            "product_targets": [],
            "ad_products": [],
            "negative_keywords": [],
            "negative_product_targets": [],
        },
    }


class FakeMcpClient:
    def __init__(self, schemas, calls):
        self.schemas = schemas
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def list_tools(self):
        return self.schemas

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"structuredContent": {"code": 0, "data": {"successIds": [TARGET_ID]}}}


class SpControlServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.calls = []
        self.schemas = {"edit_sp_targeting": TARGETING_SCHEMA}
        self.service = SpControlService(
            plan_dir=self.root / "plans",
            audit_dir=self.root / "audit",
            credentials_loader=lambda: ("client", "secret"),
            client_factory=lambda *_args: FakeMcpClient(self.schemas, self.calls),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def preview_keyword_bid(self):
        return self.service.preview(
            {
                "operation": "keyword_bid",
                "campaign_id": CAMPAIGN_ID,
                "values": {"target_id": TARGET_ID, "targeting_type": "keyword", "bid": 0.55},
            },
            context=campaign_context(),
        )

    def test_capability_preview_execute_and_single_use(self):
        capabilities = self.service.capabilities(refresh=True)
        keyword_bid = next(item for item in capabilities["operations"] if item["id"] == "keyword_bid")
        self.assertTrue(keyword_bid["available"])
        self.assertEqual(keyword_bid["availability"], "live")

        plan = self.preview_keyword_bid()
        saved = json.loads((self.root / "plans" / f"{plan['plan_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["arguments"]["items"][0]["targetId"], TARGET_ID)
        self.assertEqual(saved["arguments"]["items"][0]["bid"], 0.55)
        self.assertEqual(saved["after"], {"targeting_type": "keyword", "bid": 0.55})

        result = self.service.execute({"plan_id": plan["plan_id"], "confirmation": plan["confirmation"]})
        self.assertEqual(result["status"], "succeeded")
        audit = json.loads(next((self.root / "audit").glob("execution-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(audit["after"], {"targeting_type": "keyword", "bid": 0.55})
        self.assertEqual(audit["operation_label"], "关键词竞价")
        self.assertEqual(self.calls[-1][0], "edit_sp_targeting")
        with self.assertRaises(SpControlError) as raised:
            self.service.execute({"plan_id": plan["plan_id"], "confirmation": plan["confirmation"]})
        self.assertEqual(raised.exception.error_code, "PLAN_ALREADY_USED")

    def test_preview_rejects_entity_outside_current_campaign(self):
        with self.assertRaises(SpControlError) as raised:
            self.service.preview(
                {
                    "operation": "keyword_bid",
                    "campaign_id": CAMPAIGN_ID,
                    "values": {"target_id": "999999999", "targeting_type": "keyword", "bid": 0.55},
                },
                context=campaign_context(),
            )
        self.assertEqual(raised.exception.error_code, "CONTROL_ENTITY_MISMATCH")
        self.assertFalse(self.calls)

    def test_preview_rejects_unavailable_operation_without_calling_tool(self):
        with self.assertRaises(SpControlError) as raised:
            self.service.preview(
                {
                    "operation": "campaign_budget",
                    "campaign_id": CAMPAIGN_ID,
                    "values": {"budget": 65},
                },
                context=campaign_context(),
            )
        self.assertEqual(raised.exception.error_code, "CAPABILITY_UNAVAILABLE")
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
