import json
import logging
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sellfox_ads_monitor import MonitorFailure
from sellfox_ads_realtime import (
    CatalogItem,
    RealtimeConfig,
    RealtimeFailure,
    aggregate_rows,
    atomic_write_json,
    build_catalog,
    campaign_snapshot,
    collect_once,
    empty_campaign_state,
    load_realtime_config,
    local_clock,
    normalize_campaign_response,
    select_due_campaigns,
)


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def sample_payload(campaign_count=1, shop_count=1, actionable=True):
    shops = [
        {
            "shop_id": f"S{index}",
            "shop_name": f"Shop {index}",
            "currency": "USD",
            "marketplace_id": "ATVPDKIKX0DER",
        }
        for index in range(shop_count)
    ]
    campaigns = []
    recommendations = []
    advertised_products = []
    for shop_index in range(shop_count):
        for campaign_index in range(campaign_count):
            campaign_id = f"C{shop_index}-{campaign_index}"
            campaigns.append(
                {
                    "shop_id": f"S{shop_index}",
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_id,
                    "state": "enabled",
                    "budget": 20,
                    "creation_date": "2026-01-01 00:00:00",
                    "spend": 140 - campaign_index,
                    "sales": 560,
                    "clicks": 140,
                    "orders": 28,
                    "data_days": 14,
                    "cpc": 1,
                    "cvr": 0.2,
                    "acos": 0.25,
                }
            )
            advertised_products.append(
                {
                    "shop_id": f"S{shop_index}",
                    "campaign_id": campaign_id,
                    "group_id": f"G{campaign_index}",
                    "ad_id": f"A{campaign_index}",
                    "asin": f"B000{shop_index:02d}{campaign_index:03d}",
                    "sku": f"SKU-{shop_index}-{campaign_index}",
                    "open_date": "2026-01-01",
                    "listing_age_days": 231,
                    "listing_stage": "established",
                    "mapping_status": "matched",
                }
            )
            if actionable and campaign_index == 0:
                recommendations.append(
                    {
                        "shop_id": f"S{shop_index}",
                        "campaign_id": campaign_id,
                        "action_code": "INCREASE_BID",
                        "priority": "高",
                    }
                )
    return {
        "meta": {
            "mode": "live",
            "run_id": "mature-1",
            "generated_at": "2026-08-20T01:00:00+08:00",
            "source_end_date": "2026-08-18",
        },
        "shops": shops,
        "campaigns": campaigns,
        "advertised_products": advertised_products,
        "recommendations": recommendations,
    }


def config(root: Path) -> RealtimeConfig:
    return RealtimeConfig(
        enabled=True,
        mature_payload_path=root / "mature.json",
        state_path=root / "state.json",
        dashboard_payload_path=root / "realtime.json",
        max_calls_per_run=350,
        max_runtime_seconds=480,
        stale_grace_minutes=30,
        tier_intervals_minutes={"P0": 30, "P1": 120, "P2": 240, "P3": 720},
        new_campaign_days=14,
        min_alert_clicks=Decimal("10"),
        min_alert_spend=Decimal("5"),
        cpc_spike_multiplier=Decimal("1.5"),
        spend_pace_multiplier=Decimal("1.6"),
        budget_alert_threshold=Decimal("0.85"),
        timezone_by_shop={},
        timezone_by_marketplace={"ATVPDKIKX0DER": "America/Los_Angeles"},
        watch_campaign_ids=frozenset(),
    )


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response or {"itemList": []}
        self.error = error
        self.calls = []

    def post_data(self, path, body, purpose):
        self.calls.append((path, body, purpose))
        if self.error:
            raise self.error
        return self.response


class AdsRealtimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = config(self.root)
        self.logger = logging.getLogger("test-realtime")

    def tearDown(self):
        self.temp.cleanup()

    def test_catalog_prioritizes_actionable_and_top_spend(self):
        payload = sample_payload(campaign_count=3, actionable=True)
        payload["campaigns"][2]["spend"] = 0
        catalog = build_catalog(payload, self.config, as_of=date(2026, 8, 20))
        by_id = {item.campaign_id: item for item in catalog}
        self.assertEqual(by_id["C0-0"].tier, "P1")
        self.assertEqual(by_id["C0-1"].tier, "P2")
        self.assertEqual(by_id["C0-2"].tier, "P3")
        self.assertEqual(by_id["C0-0"].mature_action_codes, ("INCREASE_BID",))

    def test_scheduler_hard_cap_and_shop_fairness(self):
        payload = sample_payload(campaign_count=4, shop_count=4, actionable=False)
        catalog = build_catalog(payload, self.config, as_of=date(2026, 8, 20))
        states = {item.key: empty_campaign_state(item) for item in catalog}
        selected, backlog, _ = select_due_campaigns(
            catalog, states, self.config, NOW, limit=4
        )
        self.assertEqual(len(selected), 4)
        self.assertEqual(len({item.shop_id for item in selected}), 4)
        self.assertEqual(backlog, 12)

    def test_overdue_ratio_can_promote_lower_tier(self):
        catalog = build_catalog(
            sample_payload(campaign_count=2, shop_count=1, actionable=False),
            self.config,
            as_of=date(2026, 8, 20),
        )
        p1 = replace(catalog[0], tier="P1")
        p2 = replace(catalog[1], tier="P2")
        states = {
            p1.key: {
                **empty_campaign_state(p1),
                "last_success_at": "2026-08-20T10:00:00+00:00",
                "next_due_at": "2026-08-20T11:59:00+00:00",
                "report_date": "2026-08-20",
            },
            p2.key: {
                **empty_campaign_state(p2),
                "last_success_at": "2026-08-20T01:00:00+00:00",
                "next_due_at": "2026-08-20T07:00:00+00:00",
                "report_date": "2026-08-20",
            },
        }
        selected, _, _ = select_due_campaigns(
            [p1, p2], states, self.config, NOW, limit=1
        )
        self.assertEqual(selected[0].campaign_id, p2.campaign_id)

    def test_report_date_uses_marketplace_timezone(self):
        item = build_catalog(
            sample_payload(), self.config, as_of=date(2026, 8, 20)
        )[0]
        clock = local_clock(item, datetime(2026, 8, 20, 6, 30, tzinfo=timezone.utc))
        self.assertEqual(clock.date().isoformat(), "2026-08-19")
        self.assertEqual(clock.hour, 23)

    def test_hour_rows_are_sorted_and_duplicate_hour_rejected(self):
        item = build_catalog(
            sample_payload(), self.config, as_of=date(2026, 8, 20)
        )[0]

        def row(hour):
            return {
                "shopId": "S0",
                "campaignId": "C0-0",
                "date": "2026-08-20",
                "hour": str(hour),
                "costs": "1",
                "clicks": "1",
                "impressions": "10",
                "orders": "0",
                "sales": "0",
                "units": "0",
            }

        rows = normalize_campaign_response(
            [row(2), row(0), row(1)],
            item=item,
            report_date=date(2026, 8, 20),
            run_id="test",
            ingested_at=NOW.isoformat(),
        )
        self.assertEqual([item["report_hour"] for item in rows], [0, 1, 2])
        with self.assertRaises(MonitorFailure):
            normalize_campaign_response(
                [row(1), row(1)],
                item=item,
                report_date=date(2026, 8, 20),
                run_id="test",
                ingested_at=NOW.isoformat(),
            )

    def test_aggregate_zero_denominators_return_null(self):
        metrics = aggregate_rows(
            [{"spend": "5", "clicks": "0", "impressions": "0", "orders": "0", "sales": "0", "units": "0"}]
        )
        self.assertIsNone(metrics["cpc"])
        self.assertIsNone(metrics["cvr"])
        self.assertIsNone(metrics["acos"])

    def test_failed_refresh_preserves_previous_metrics_and_blocks_scale(self):
        payload = sample_payload()
        item = build_catalog(payload, self.config, as_of=date(2026, 8, 20))[0]
        old = empty_campaign_state(item)
        old.update(
            {
                "last_success_at": "2026-08-20T10:00:00+00:00",
                "next_due_at": "2026-08-20T11:00:00+00:00",
                "report_date": "2026-08-20",
                "latest_hour": 3,
                "rows_count": 4,
                "metrics": {"spend": 8, "clicks": 8, "orders": 1, "sales": 20},
            }
        )
        state = {"schema_version": "sellfox-ads-realtime-v1", "campaigns": {item.key: old}}
        new_state, output = collect_once(
            replace(self.config, max_calls_per_run=1),
            client=FakeClient(error=MonitorFailure("read failed")),
            mature_payload=payload,
            mature_hash="hash",
            state=state,
            now_utc=NOW,
            logger=self.logger,
            clock=lambda: NOW,
        )
        current = new_state["campaigns"][item.key]
        self.assertEqual(current["metrics"]["spend"], 8)
        self.assertEqual(current["last_success_at"], "2026-08-20T10:00:00+00:00")
        self.assertEqual(output["campaign_snapshots"][0]["execution_gate"], "BLOCK")

    def test_empty_success_is_not_api_failure(self):
        payload = sample_payload(actionable=False)
        state, output = collect_once(
            replace(self.config, max_calls_per_run=1),
            client=FakeClient({"itemList": []}),
            mature_payload=payload,
            mature_hash="hash",
            state={"schema_version": "sellfox-ads-realtime-v1", "campaigns": {}},
            now_utc=NOW,
            logger=self.logger,
            clock=lambda: NOW,
        )
        campaign = next(iter(state["campaigns"].values()))
        self.assertTrue(campaign["empty_success"])
        self.assertEqual(output["meta"]["successful_calls"], 1)
        self.assertEqual(output["meta"]["failed_calls"], 0)
        self.assertEqual(output["meta"]["covered_campaigns"], 0)
        self.assertEqual(output["campaign_snapshots"][0]["freshness"]["status"], "empty")

    def test_empty_after_nonempty_preserves_same_day_metrics(self):
        payload = sample_payload()
        item = build_catalog(payload, self.config, as_of=date(2026, 8, 20))[0]
        old = empty_campaign_state(item)
        old.update(
            {
                "last_success_at": "2026-08-20T10:00:00+00:00",
                "next_due_at": "2026-08-20T11:00:00+00:00",
                "report_date": "2026-08-20",
                "latest_hour": 2,
                "rows_count": 3,
                "metrics": {"spend": 12, "clicks": 6, "orders": 1, "sales": 20},
            }
        )
        state, output = collect_once(
            replace(self.config, max_calls_per_run=1),
            client=FakeClient({"itemList": []}),
            mature_payload=payload,
            mature_hash="hash",
            state={"schema_version": "sellfox-ads-realtime-v1", "campaigns": {item.key: old}},
            now_utc=NOW,
            logger=self.logger,
            clock=lambda: NOW,
        )
        current = state["campaigns"][item.key]
        self.assertEqual(current["metrics"]["spend"], 12)
        self.assertEqual(current["last_error_code"], "EMPTY_RESPONSE_AFTER_DATA")
        self.assertEqual(output["campaign_snapshots"][0]["freshness"]["status"], "error")

    def test_zero_order_is_watch_but_cpc_spike_blocks_scale(self):
        payload = sample_payload()
        item = build_catalog(payload, self.config, as_of=date(2026, 8, 20))[0]
        state = empty_campaign_state(item)
        state.update(
            {
                "last_success_at": NOW.isoformat(),
                "last_attempt_at": NOW.isoformat(),
                "next_due_at": "2026-08-20T13:30:00+00:00",
                "report_date": "2026-08-20",
                "latest_hour": 4,
                "rows_count": 5,
                "metrics": {
                    "spend": 30,
                    "clicks": 15,
                    "impressions": 200,
                    "orders": 0,
                    "sales": 0,
                    "units": 0,
                    "cpc": 2,
                    "cvr": 0,
                    "acos": None,
                },
            }
        )
        snapshot, alerts = campaign_snapshot(item, state, self.config, NOW)
        by_code = {alert["alert_code"]: alert for alert in alerts}
        self.assertEqual(by_code["ORDERS_NOT_ATTRIBUTED_YET"]["handling"], "WATCH")
        self.assertEqual(by_code["CPC_SPIKE"]["handling"], "BLOCK")
        self.assertEqual(snapshot["execution_gate"], "BLOCK")

    def test_mixed_listing_campaign_only_watches_realtime_anomaly(self):
        payload = sample_payload()
        payload["advertised_products"].append(
            {
                "shop_id": "S0",
                "campaign_id": "C0-0",
                "group_id": "G-NEW",
                "ad_id": "A-NEW",
                "asin": "B000NEW001",
                "sku": "SKU-NEW",
                "open_date": "2026-08-10",
                "listing_age_days": 10,
                "listing_stage": "new",
                "mapping_status": "matched",
            }
        )
        item = build_catalog(payload, self.config, as_of=date(2026, 8, 20))[0]
        self.assertEqual(item.listing_stage, "mixed")
        state = empty_campaign_state(item)
        state.update(
            {
                "last_success_at": NOW.isoformat(),
                "last_attempt_at": NOW.isoformat(),
                "report_date": "2026-08-20",
                "latest_hour": 4,
                "rows_count": 5,
                "metrics": {
                    "spend": 30,
                    "clicks": 15,
                    "impressions": 200,
                    "orders": 1,
                    "sales": 10,
                    "units": 1,
                    "cpc": 2,
                    "cvr": 0.0667,
                    "acos": 3,
                },
            }
        )
        snapshot, alerts = campaign_snapshot(item, state, self.config, NOW)
        self.assertEqual(
            next(alert for alert in alerts if alert["alert_code"] == "CPC_SPIKE")[
                "handling"
            ],
            "WATCH",
        )
        self.assertEqual(snapshot["execution_gate"], "REVIEW")

    def test_unknown_listing_mapping_blocks_actionable_campaign(self):
        payload = sample_payload()
        payload["advertised_products"][0]["mapping_status"] = "ambiguous"
        payload["advertised_products"][0]["listing_stage"] = "unknown"
        item = build_catalog(payload, self.config, as_of=date(2026, 8, 20))[0]
        snapshot, alerts = campaign_snapshot(
            item,
            {
                **empty_campaign_state(item),
                "last_success_at": NOW.isoformat(),
                "last_attempt_at": NOW.isoformat(),
                "report_date": "2026-08-20",
                "rows_count": 0,
                "metrics": {},
            },
            self.config,
            NOW,
        )
        self.assertEqual(item.listing_stage, "unknown")
        self.assertEqual(snapshot["execution_gate"], "BLOCK")
        self.assertIn(
            "PRODUCT_LIFECYCLE_UNKNOWN",
            {alert["alert_code"] for alert in alerts},
        )

    def test_atomic_write_leaves_valid_json(self):
        path = self.root / "nested" / "payload.json"
        atomic_write_json({"value": "ok"}, path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"value": "ok"})
        self.assertFalse(list(path.parent.glob(".payload.json.tmp-*")))

    def test_config_rejects_excessive_call_budget(self):
        path = self.root / "config.json"
        path.write_text(
            json.dumps(
                {
                    "realtime": {"max_calls_per_run": 1001},
                    "storage": {"dashboard_payload_path": "mature.json"},
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(RealtimeFailure):
            load_realtime_config(path)

    def test_config_rejects_path_collision(self):
        path = self.root / "config-collision.json"
        path.write_text(
            json.dumps(
                {
                    "storage": {
                        "dashboard_payload_path": "same.json",
                        "realtime_state_path": "state.json",
                        "realtime_dashboard_payload_path": "same.json",
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(RealtimeFailure):
            load_realtime_config(path)


if __name__ == "__main__":
    unittest.main()
