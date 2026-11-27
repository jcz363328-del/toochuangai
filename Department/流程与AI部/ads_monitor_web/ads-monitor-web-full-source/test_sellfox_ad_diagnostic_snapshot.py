from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sellfox_ad_diagnostic_server import SnapshotStore
from sellfox_ad_diagnostic_snapshot import refresh_snapshot_batch


class StubService:
    def __init__(self) -> None:
        self.details: list[str] = []

    def campaigns(self, refresh=False):
        return {
            "meta": {},
            "campaigns": [
                {"campaignId": "100", "name": "first"},
                {"campaignId": "200", "name": "second"},
            ],
        }

    def campaign_detail(self, campaign_id, refresh=False, section="full"):
        self.details.append(campaign_id)
        return {
            "meta": {},
            "campaign": {"campaignId": campaign_id},
            "structure": {"ad_products": [], "keywords": []},
            "performance": {
                "today": {},
                "mature_14d": {
                    "deep_reports": {
                        key: {"status": "available"}
                        for key in (
                            "campaigns",
                            "groups",
                            "products",
                            "placements",
                            "targets",
                            "search_terms",
                            "purchased_items",
                            "business_placements",
                        )
                    }
                },
            },
        }


class SnapshotBuilderTests(unittest.TestCase):
    def test_refreshes_one_bounded_batch_without_hiding_other_campaigns(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = StubService()
            store = SnapshotStore(Path(temporary))
            manifest = refresh_snapshot_batch(
                service,
                store,
                batch_size=1,
                delay_seconds=0,
            )

            self.assertEqual(manifest["campaign_count"], 2)
            self.assertEqual(manifest["known_snapshot_count"], 1)
            self.assertEqual(service.details, ["100"])
            self.assertIsNotNone(store.read("campaigns"))
            self.assertIsNotNone(store.read("overview", "100"))
            self.assertIsNotNone(store.read("full", "100"))
            self.assertIsNone(store.read("full", "200"))

            next_manifest = refresh_snapshot_batch(
                service, store, batch_size=1, delay_seconds=0
            )
            self.assertEqual(service.details, ["100", "200"])
            self.assertEqual(next_manifest["known_snapshot_count"], 2)
            self.assertIsNotNone(store.read("full", "200"))

    def test_requested_campaign_is_refreshed_first(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = StubService()
            manifest = refresh_snapshot_batch(
                service,
                SnapshotStore(Path(temporary)),
                batch_size=1,
                delay_seconds=0,
                requested_campaign_ids=["200"],
            )

            self.assertEqual(manifest["selected"], ["200"])
            self.assertEqual(service.details, ["200"])

    def test_invalid_refresh_preserves_last_successful_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = StubService()
            store = SnapshotStore(Path(temporary))
            old_time = datetime(2026, 8, 25, tzinfo=timezone.utc)
            old_detail = service.campaign_detail("100")
            old_detail["campaign"]["name"] = "historical"
            store.write_hot("full", old_detail, old_time, "100")
            service.details.clear()

            original = service.campaign_detail

            def invalid_detail(campaign_id, refresh=False, section="full"):
                detail = original(campaign_id, refresh=refresh, section=section)
                detail["performance"]["mature_14d"]["deep_reports"]["placements"] = {
                    "status": "error"
                }
                return detail

            service.campaign_detail = invalid_detail
            manifest = refresh_snapshot_batch(
                service,
                store,
                batch_size=1,
                delay_seconds=0,
                requested_campaign_ids=["100"],
            )

            current = store.read("full", "100")
            self.assertEqual(manifest["failures"], ["100"])
            self.assertEqual(current.generated_at, old_time)
            self.assertEqual(current.value["campaign"]["name"], "historical")


if __name__ == "__main__":
    unittest.main()
