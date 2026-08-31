import json
import logging
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from unittest import mock
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sellfox_ads_monitor import (
    DataQualityFailure,
    MonitorConfig,
    MonitorFailure,
    ONLINE_PRODUCT_PATH,
    RunCoverage,
    RuleSet,
    SellfoxAdsClient,
    ShopConfig,
    SP_AD_PRODUCT_PATH,
    aggregate_campaigns,
    aggregate_targets,
    bulk_row_to_fact,
    build_payload,
    build_advertised_products,
    campaign_budget_matrix_status,
    campaign_listing_stage,
    campaign_performance_status,
    complete_bulk_report_calendar,
    connect_store,
    demo_config,
    discover_authorized_shops,
    fetch_cursor_items,
    fetch_online_products_for_shops,
    fetch_page_items,
    finalize_output_swap,
    generate_recommendations,
    insert_campaigns,
    insert_ad_products,
    insert_hourly,
    insert_online_products,
    load_base_endpoint_cache,
    load_monitor_config,
    listing_stage_for,
    normalize_hourly_row,
    parse_rules,
    promote_run,
    publish_live_payload,
    report_reconciliation_blocks,
    rollback_output_swap,
    seed_demo_data,
    select_campaigns,
    swap_generated_outputs,
    write_base_endpoint_cache,
)


class AdsMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config_path = self.root / "config.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "shops": [],
                    "collection": {
                        "lookback_days": 14,
                        "maturity_lag_days": 2,
                        "max_campaigns_per_shop": 20,
                        "pull_targets": True,
                    },
                    "rules": {"target_acos": 0.3},
                    "storage": {
                        "database_path": str(self.root / "ads.sqlite3"),
                        "output_dir": str(self.root / "outputs"),
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def demo(self) -> MonitorConfig:
        return demo_config(load_monitor_config(self.config_path))

    def test_demo_generates_expected_bid_recommendations(self):
        config = self.demo()
        run_id = "demo-run"
        with connect_store(config.database_path) as connection:
            coverage = seed_demo_data(
                connection,
                config,
                run_id=run_id,
                as_of=date(2026, 8, 19),
            )
            campaigns, targets, recommendations = generate_recommendations(
                connection, config, run_id, set()
            )
            products, listing_coverage, listing_blocks = build_advertised_products(
                connection,
                config,
                run_id=run_id,
                as_of=date(2026, 8, 19),
            )

        self.assertEqual(coverage.status, "complete")
        self.assertEqual(len(campaigns), 2)
        self.assertEqual(len(targets), 3)
        by_target = {
            item["target_id"]: item
            for item in recommendations
            if item["target_id"]
        }
        self.assertEqual(by_target["KW-GOOD"]["action_code"], "INCREASE_BID")
        self.assertEqual(by_target["KW-GOOD"]["proposed_value"], "1.05")
        self.assertEqual(by_target["KW-HIGH"]["action_code"], "OBSERVE")
        self.assertEqual(by_target["KW-HIGH"]["rule_id"], "new_listing_90d_protection")
        self.assertEqual(by_target["KW-ZERO"]["action_code"], "OBSERVE")
        self.assertEqual(by_target["KW-ZERO"]["rule_id"], "new_listing_90d_protection")
        self.assertEqual(len(products), 2)
        self.assertEqual(
            {item["listing_stage"] for item in products},
            {"new", "established"},
        )
        self.assertEqual(listing_coverage["status"], "complete")
        self.assertFalse(listing_blocks)

    def test_quality_failure_marks_coverage_partial_without_changing_call_counts(self):
        coverage = RunCoverage(
            requested_calls=3,
            successful_calls=3,
            quality_failures=1,
        )

        self.assertEqual(coverage.status, "partial")
        self.assertEqual(coverage.requested_calls, 3)
        self.assertEqual(coverage.successful_calls + coverage.failed_calls, 3)

    def test_failed_campaign_blocks_all_suggestions(self):
        config = self.demo()
        run_id = "blocked-run"
        with connect_store(config.database_path) as connection:
            seed_demo_data(
                connection,
                config,
                run_id=run_id,
                as_of=date(2026, 8, 19),
            )
            _, _, recommendations = generate_recommendations(
                connection,
                config,
                run_id,
                {("DEMO-SHOP", "CAMP-CUT")},
            )
        blocked = [
            item
            for item in recommendations
            if item["campaign_id"] == "CAMP-CUT"
        ]
        self.assertTrue(blocked)
        self.assertTrue(all(item["action_code"] == "BLOCKED" for item in blocked))
        self.assertTrue(all(item["data_status"] == "partial" for item in blocked))

    def test_hourly_history_isolated_by_run(self):
        config = self.demo()
        raw = {
            "shopId": "DEMO-SHOP",
            "date": "2026-08-10",
            "hour": "12",
            "campaignId": "C1",
            "costs": "1.25",
            "clicks": "1",
            "impressions": "10",
            "orders": "0",
            "sales": "0",
            "units": "0",
        }
        first = normalize_hourly_row(
            raw,
            aggregation_type="campaign",
            shop_id="DEMO-SHOP",
            report_date=date(2026, 8, 10),
            campaign_id="C1",
            run_id="run-1",
            ingested_at=datetime.now().isoformat(),
        )
        second = {**first, "run_id": "run-2", "spend": "2.50"}
        second_refresh = {**second, "spend": "3.00"}
        with connect_store(config.database_path) as connection:
            insert_hourly(connection, [first])
            insert_hourly(connection, [second])
            insert_hourly(connection, [second_refresh])
            rows = list(
                connection.execute(
                    "SELECT run_id, spend FROM hourly_fact_history ORDER BY run_id"
                )
            )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["run_id"], "run-1")
        self.assertEqual(rows[1]["run_id"], "run-2")
        self.assertEqual(rows[1]["spend"], "3.00")

    def test_attempt_replaces_previous_run_only_when_promoted(self):
        config = self.demo()
        with connect_store(config.database_path) as connection:
            for run_id, message in (("stable", "old"), ("attempt", "new")):
                connection.execute(
                    """
                    INSERT INTO sync_log (run_id, logged_at, endpoint, status, message)
                    VALUES (?, '2026-08-19T09:00:00+08:00', '/test', 'ok', ?)
                    """,
                    (run_id, message),
                )
            connection.commit()
            before = connection.execute(
                "SELECT message FROM sync_log WHERE run_id = 'stable'"
            ).fetchone()[0]
            promote_run(connection, "attempt", "stable")
            rows = list(
                connection.execute(
                    "SELECT run_id, message FROM sync_log ORDER BY id"
                )
            )
        self.assertEqual(before, "old")
        self.assertEqual([tuple(row) for row in rows], [("stable", "new")])

    def test_generated_output_swap_rolls_back_without_touching_unknown_files(self):
        final_dir = self.root / "outputs" / "scope"
        staging_dir = self.root / "outputs" / ".scope.staging-test"
        backup_dir = self.root / "outputs" / ".scope.backup-test"
        final_dir.mkdir(parents=True)
        staging_dir.mkdir(parents=True)
        (final_dir / "keep.txt").write_text("user", encoding="utf-8")
        (final_dir / "sellfox_ads_monitor_payload.json").write_text(
            "old", encoding="utf-8"
        )
        (final_dir / "赛狐广告监控与调控建议.xlsx").write_text(
            "old workbook", encoding="utf-8"
        )
        (staging_dir / "sellfox_ads_monitor_payload.json").write_text(
            "new", encoding="utf-8"
        )
        (staging_dir / "sellfox_ads_recommendations.csv").write_text(
            "new csv", encoding="utf-8"
        )

        state = swap_generated_outputs(staging_dir, final_dir, backup_dir)
        self.assertEqual((final_dir / "keep.txt").read_text(encoding="utf-8"), "user")
        self.assertEqual(
            (final_dir / "sellfox_ads_monitor_payload.json").read_text(
                encoding="utf-8"
            ),
            "new",
        )
        self.assertEqual(
            (final_dir / "赛狐广告监控与调控建议.xlsx").read_text(
                encoding="utf-8"
            ),
            "old workbook",
        )
        rollback_output_swap(state)
        self.assertEqual(
            (final_dir / "sellfox_ads_monitor_payload.json").read_text(
                encoding="utf-8"
            ),
            "old",
        )
        self.assertTrue((final_dir / "赛狐广告监控与调控建议.xlsx").exists())

        second_backup = self.root / "outputs" / ".scope.backup-final"
        second = swap_generated_outputs(staging_dir, final_dir, second_backup)
        finalize_output_swap(second, logging.getLogger("test-output-swap"))
        self.assertFalse(staging_dir.exists())
        self.assertFalse(second_backup.exists())
        self.assertEqual((final_dir / "keep.txt").read_text(encoding="utf-8"), "user")

    def test_output_swap_rolls_back_on_keyboard_interrupt(self):
        final_dir = self.root / "outputs" / "scope"
        staging_dir = self.root / "outputs" / ".scope.staging-interrupt"
        backup_dir = self.root / "outputs" / ".scope.backup-interrupt"
        final_dir.mkdir(parents=True)
        staging_dir.mkdir(parents=True)
        old_path = final_dir / "sellfox_ads_monitor_payload.json"
        new_path = staging_dir / "sellfox_ads_monitor_payload.json"
        csv_path = staging_dir / "sellfox_ads_recommendations.csv"
        old_path.write_text("old", encoding="utf-8")
        new_path.write_text("new", encoding="utf-8")
        csv_path.write_text("csv", encoding="utf-8")
        original_replace = os.replace
        calls = 0

        def interrupt_once(source, target):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise KeyboardInterrupt
            return original_replace(source, target)

        with mock.patch("sellfox_ads_monitor.os.replace", side_effect=interrupt_once):
            with self.assertRaises(KeyboardInterrupt):
                swap_generated_outputs(staging_dir, final_dir, backup_dir)
        self.assertEqual(old_path.read_text(encoding="utf-8"), "old")
        self.assertEqual(new_path.read_text(encoding="utf-8"), "new")
        self.assertEqual(csv_path.read_text(encoding="utf-8"), "csv")
        self.assertFalse(backup_dir.exists())

    def test_negative_metric_is_rejected(self):
        with self.assertRaises(DataQualityFailure):
            normalize_hourly_row(
                {
                    "date": "2026-08-10",
                    "hour": "1",
                    "costs": "-1",
                    "clicks": "0",
                    "impressions": "0",
                    "orders": "0",
                    "sales": "0",
                    "units": "0",
                },
                aggregation_type="campaign",
                shop_id="S1",
                report_date=date(2026, 8, 10),
                campaign_id="C1",
                run_id="run",
                ingested_at="now",
            )

    def test_invalid_metric_and_fractional_hour_are_rejected(self):
        base = {
            "date": "2026-08-10",
            "hour": "1",
            "costs": "1",
            "clicks": "0",
            "impressions": "0",
            "orders": "0",
            "sales": "0",
            "units": "0",
        }
        for raw in ({**base, "orders": "bad"}, {**base, "hour": "1.5"}):
            with self.assertRaises(DataQualityFailure):
                normalize_hourly_row(
                    raw,
                    aggregation_type="campaign",
                    shop_id="S1",
                    report_date=date(2026, 8, 10),
                    campaign_id="C1",
                    run_id="run",
                    ingested_at="now",
                )

    def test_target_without_id_uses_non_colliding_fallback(self):
        base = {
            "date": "2026-08-10",
            "hour": "1",
            "campaignId": "C1",
            "costs": "1",
            "clicks": "1",
            "impressions": "10",
            "orders": "0",
            "sales": "0",
            "units": "0",
            "matchType": "exact",
        }
        rows = [
            normalize_hourly_row(
                {**base, "targeting": text},
                aggregation_type="target",
                shop_id="S1",
                report_date=date(2026, 8, 10),
                campaign_id="C1",
                run_id="run",
                ingested_at="now",
            )
            for text in ("alpha", "beta")
        ]
        self.assertNotEqual(rows[0]["targeting_id"], rows[1]["targeting_id"])
        config = self.demo()
        with connect_store(config.database_path) as connection:
            insert_hourly(connection, rows)
            count = connection.execute(
                "SELECT COUNT(*) FROM hourly_fact_history"
            ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_cursor_pagination_keeps_shop_scope_with_next_token(self):
        class FakeClient:
            def __init__(self):
                self.bodies = []

            def post_data(self, path, body, purpose):
                self.bodies.append(body)
                if len(self.bodies) == 1:
                    return {"itemList": [{"campaignId": "1"}], "nextToken": "N1"}
                return {"itemList": [{"campaignId": "2"}], "nextToken": ""}

        client = FakeClient()
        items, pages = fetch_cursor_items(
            client,
            "/test",
            {"shopId": "S1", "pageSize": "1000"},
            "test",
        )
        self.assertEqual(pages, 2)
        self.assertEqual([item["campaignId"] for item in items], ["1", "2"])
        self.assertEqual(
            client.bodies[1],
            {"shopId": "S1", "pageSize": "1000", "nextToken": "N1"},
        )

    def test_page_pagination_keeps_account_filters(self):
        class FakeClient:
            def __init__(self):
                self.bodies = []

            def post_data(self, path, body, purpose):
                self.bodies.append(body)
                return {
                    "rows": [{"shopId": "S1", "sku": f"SKU-{len(self.bodies)}"}],
                    "totalPage": 2,
                    "totalSize": 2,
                }

        client = FakeClient()
        items, pages = fetch_page_items(
            client,
            ONLINE_PRODUCT_PATH,
            {"shopIdList": ["S1"], "pageSize": "200"},
            "test",
        )
        self.assertEqual((len(items), pages), (2, 2))
        self.assertEqual(
            client.bodies[1],
            {"shopIdList": ["S1"], "pageSize": "200", "pageNo": "2"},
        )

    def test_online_products_use_single_scoped_page_stream(self):
        shops = self.demo().shops
        fake_client = mock.Mock()
        with mock.patch(
            "sellfox_ads_monitor.SellfoxAdsClient", return_value=fake_client
        ), mock.patch(
            "sellfox_ads_monitor.fetch_page_items", return_value=([], 1)
        ) as fetch:
            results = fetch_online_products_for_shops(
                shops,
                client_id="id",
                client_secret="secret",
                logger=logging.getLogger("test-online-products"),
            )

        body = fetch.call_args.args[2]
        self.assertEqual(body["pageSize"], "200")
        self.assertNotIn("shopIdList", body)
        self.assertEqual(body["onlineStatusList"], ["active", "inActive"])
        self.assertEqual(len(results), 1)
        fake_client.close.assert_called_once()

    def test_advertised_products_join_is_unique_and_fail_closed(self):
        config = self.demo()
        run_id = "listing-map"
        snapshot_at = "2026-08-20T09:00:00+08:00"
        with connect_store(config.database_path) as connection:
            insert_campaigns(
                connection,
                run_id,
                snapshot_at,
                [{"campaignId": "C1", "state": "enabled"}],
                "DEMO-SHOP",
            )
            insert_ad_products(
                connection,
                run_id,
                snapshot_at,
                [
                    {
                        "campaignId": "C1",
                        "groupId": "G1",
                        "adId": "A1",
                        "asin": "b000new001",
                        "sku": "SKU-New",
                        "state": "enabled",
                    },
                    {
                        "campaignId": "C1",
                        "groupId": "G1",
                        "adId": "A2",
                        "asin": "B000OLD001",
                        "sku": "SKU-Old",
                        "state": "enabled",
                    },
                    {
                        "campaignId": "C-PAUSED",
                        "groupId": "G2",
                        "adId": "A-HISTORY",
                        "asin": "B000OLD999",
                        "sku": "SKU-History",
                        "state": "enabled",
                    },
                ],
                "DEMO-SHOP",
            )
            insert_online_products(
                connection,
                run_id,
                snapshot_at,
                [
                    {
                        "id": "P1",
                        "asin": "B000NEW001",
                        "sku": "SKU-New",
                        "openDate": "2026-08-01 00:00:00",
                        "onlineStatus": "Active",
                    },
                    {
                        "id": "P2",
                        "asin": "B000OLD001",
                        "sku": "SKU-Old",
                        "openDate": "2026-01-01 00:00:00",
                    },
                    {
                        "id": "P3",
                        "asin": "B000OLD001",
                        "sku": "SKU-Old",
                        "openDate": "2026-01-01 00:00:00",
                    },
                ],
                "DEMO-SHOP",
            )
            for endpoint in (SP_AD_PRODUCT_PATH, ONLINE_PRODUCT_PATH):
                connection.execute(
                    """
                    INSERT INTO sync_log
                    (run_id, logged_at, shop_id, endpoint, status)
                    VALUES (?, ?, ?, ?, 'ok')
                    """,
                    (run_id, snapshot_at, "DEMO-SHOP", endpoint),
                )
            products, coverage, blocked = build_advertised_products(
                connection,
                config,
                run_id=run_id,
                as_of=date(2026, 8, 20),
            )

        by_ad = {row["ad_id"]: row for row in products}
        self.assertNotIn("A-HISTORY", by_ad)
        self.assertEqual(by_ad["A1"]["listing_stage"], "new")
        self.assertEqual(by_ad["A1"]["listing_age_days"], 19)
        self.assertEqual(by_ad["A1"]["mapping_status"], "matched")
        self.assertEqual(by_ad["A2"]["mapping_status"], "ambiguous")
        self.assertEqual(by_ad["A2"]["listing_stage"], "unknown")
        self.assertEqual(coverage["status"], "partial")
        self.assertEqual(coverage["source_advertised_products"], 3)
        self.assertEqual(coverage["excluded_non_enabled_campaign_positions"], 1)
        self.assertIn(("DEMO-SHOP", "C1"), blocked)

    def test_listing_stage_uses_open_date_and_rejects_future_date(self):
        self.assertEqual(
            listing_stage_for("2026-05-22", as_of=date(2026, 8, 20), new_days=90),
            (90, "new"),
        )
        self.assertEqual(
            listing_stage_for("2026-05-21", as_of=date(2026, 8, 20), new_days=90),
            (91, "established"),
        )
        self.assertEqual(
            listing_stage_for("2026-08-21", as_of=date(2026, 8, 20), new_days=90),
            (None, "unknown"),
        )

    def test_campaign_performance_uses_inclusive_ctr_and_purchase_rate_thresholds(self):
        rules = self.demo().default_rules
        metrics = {
            "data_days": 7,
            "clicks": Decimal("10"),
            "ctr": Decimal("0.01"),
            "cvr": Decimal("0.10"),
        }
        self.assertEqual(campaign_performance_status(metrics, "established", rules), "normal")
        self.assertEqual(campaign_performance_status({**metrics, "ctr": Decimal("0.009")}, "established", rules), "poor")
        self.assertEqual(campaign_performance_status(metrics, "new", rules), "new_observation")
        self.assertEqual(campaign_budget_matrix_status("poor", True), "poor_full")
        self.assertEqual(campaign_listing_stage([{"listing_stage": "new"}, {"listing_stage": "established"}]), "mixed")

    def test_cursor_loop_is_stopped(self):
        class FakeClient:
            def post_data(self, path, body, purpose):
                return {"itemList": [], "nextToken": "LOOP"}

        with self.assertRaises(MonitorFailure):
            fetch_cursor_items(FakeClient(), "/test", {"shopId": "S1"}, "test")

    def test_missing_item_list_is_rejected(self):
        class FakeClient:
            def post_data(self, path, body, purpose):
                return {"totalCount": "0", "nextToken": ""}

        with self.assertRaises(MonitorFailure):
            fetch_cursor_items(FakeClient(), "/test", {"shopId": "S1"}, "test")

    def test_shop_discovery_paginates_filters_and_maps_currency(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def post_data(self, path, body, purpose):
                self.calls.append((path, body))
                if body["pageNo"] == "1":
                    return {
                        "rows": [
                            {
                                "id": "US-1",
                                "name": "美国店",
                                "adStatus": "auth",
                                "status": 0,
                                "marketplaceId": "ATVPDKIKX0DER",
                                "region": "NA",
                            },
                            {
                                "id": "SKIP-AUTH",
                                "name": "未授权店",
                                "adStatus": "unauth",
                                "status": 0,
                                "marketplaceId": "ATVPDKIKX0DER",
                            },
                        ],
                        "totalPage": 2,
                    }
                return {
                    "rows": [
                        {
                            "id": "UK-1",
                            "name": "英国店",
                            "adStatus": "已授权",
                            "status": "0",
                            "marketplaceId": "A1F83G8C2ARO7P",
                            "region": "EU",
                        },
                        {
                            "id": "SKIP-STATUS",
                            "name": "停用店",
                            "adStatus": "auth",
                            "status": "1",
                            "marketplaceId": "A1F83G8C2ARO7P",
                        },
                    ],
                    "totalPage": "2",
                }

        client = FakeClient()
        shops = discover_authorized_shops(
            client,
            load_monitor_config(self.config_path),
        )
        by_id = {shop.shop_id: shop for shop in shops}

        self.assertEqual(
            client.calls,
            [
                ("/api/shop/pageList.json", {"pageNo": "1", "pageSize": "100"}),
                ("/api/shop/pageList.json", {"pageNo": "2", "pageSize": "100"}),
            ],
        )
        self.assertEqual(set(by_id), {"US-1", "UK-1"})
        self.assertEqual((by_id["US-1"].currency, by_id["US-1"].region), ("USD", "NA"))
        self.assertEqual((by_id["UK-1"].currency, by_id["UK-1"].region), ("GBP", "EU"))

    def test_shop_discovery_blocks_unknown_marketplace_currency(self):
        class FakeClient:
            def post_data(self, path, body, purpose):
                return {
                    "rows": [
                        {
                            "id": "UNKNOWN-1",
                            "name": "未知站点店铺",
                            "adStatus": "auth",
                            "status": "0",
                            "marketplaceId": "UNKNOWN-MARKETPLACE",
                        }
                    ],
                    "totalPage": 1,
                }

        with self.assertRaisesRegex(MonitorFailure, "无法确定币种"):
            discover_authorized_shops(FakeClient(), load_monitor_config(self.config_path))

    def test_zero_campaign_limit_does_not_truncate(self):
        config = load_monitor_config(self.config_path, max_campaigns_override=0)
        shop = self.demo().shops[0]
        campaigns = [
            {"campaignId": "C1", "state": "enabled", "budget": "10"},
            {"campaignId": "C2", "state": "enabled", "budget": "30"},
            {"campaignId": "C3", "state": "enabled", "budget": "20"},
            {"campaignId": "C4", "state": "paused", "budget": "99"},
        ]

        selected, skipped = select_campaigns(campaigns, shop, config.max_campaigns_per_shop)

        self.assertEqual(config.max_campaigns_per_shop, 0)
        self.assertEqual([item["campaignId"] for item in selected], ["C2", "C3", "C1"])
        self.assertEqual(skipped, 0)

    def test_bulk_row_to_fact_normalizes_daily_target_metrics(self):
        fact = bulk_row_to_fact(
            {
                "shop_id": "S1",
                "report_date": "2026-08-17",
                "campaign_id": "C1",
                "ad_group_id": "G1",
                "target_id": "T1",
                "target_text": "running shoes",
                "match_type": "exact",
                "spend": Decimal("12.34"),
                "clicks": Decimal("7"),
                "impressions": Decimal("100"),
                "orders": Decimal("2"),
                "sales": Decimal("40.00"),
                "units": Decimal("2"),
            },
            aggregation_type="target",
            run_id="bulk-run",
            ingested_at="2026-08-19T09:00:00+08:00",
        )

        self.assertEqual(
            {
                key: fact[key]
                for key in (
                    "run_id",
                    "aggregation_type",
                    "shop_id",
                    "report_date",
                    "report_hour",
                    "campaign_id",
                    "ad_group_id",
                    "targeting_id",
                    "targeting",
                    "match_type",
                    "spend",
                    "sales",
                    "orders",
                )
            },
            {
                "run_id": "bulk-run",
                "aggregation_type": "target",
                "shop_id": "S1",
                "report_date": "2026-08-17",
                "report_hour": 0,
                "campaign_id": "C1",
                "ad_group_id": "G1",
                "targeting_id": "T1",
                "targeting": "running shoes",
                "match_type": "exact",
                "spend": "12.34",
                "sales": "40.00",
                "orders": "2",
            },
        )

    def test_bulk_calendar_fills_enabled_campaigns_and_seen_targets_for_14_days(self):
        config = self.demo()
        run_id = "bulk-calendar"
        window = [date(2026, 8, 4 + offset) for offset in range(14)]
        metric_values = {
            "spend": Decimal("5"),
            "clicks": Decimal("2"),
            "impressions": Decimal("20"),
            "orders": Decimal("1"),
            "sales": Decimal("10"),
            "units": Decimal("1"),
        }
        campaign_rows = [
            {
                "shop_id": "DEMO-SHOP",
                "shop_name": "演示店铺",
                "report_date": "2026-08-10",
                "campaign_id": "C-ENABLED",
                "campaign_name": "Enabled",
                **metric_values,
            }
        ]
        targeting_rows = [
            {
                "shop_id": "DEMO-SHOP",
                "shop_name": "演示店铺",
                "report_date": "2026-08-12",
                "campaign_id": "C-ENABLED",
                "campaign_name": "Enabled",
                "ad_group_id": "G1",
                "target_id": "T1",
                "target_text": "keyword",
                "match_type": "exact",
                **metric_values,
            }
        ]

        with connect_store(config.database_path) as connection:
            insert_campaigns(
                connection,
                run_id,
                "2026-08-19T09:00:00+08:00",
                [
                    {
                        "shopId": "DEMO-SHOP",
                        "campaignId": "C-ENABLED",
                        "name": "Enabled",
                        "state": "enabled",
                    },
                    {
                        "shopId": "DEMO-SHOP",
                        "campaignId": "C-PAUSED",
                        "name": "Paused",
                        "state": "paused",
                    },
                ],
            )
            completed_campaigns, completed_targets = complete_bulk_report_calendar(
                connection,
                run_id,
                window,
                campaign_rows,
                targeting_rows,
            )

        expected_dates = {day.isoformat() for day in window}
        enabled_rows = [
            row for row in completed_campaigns if row["campaign_id"] == "C-ENABLED"
        ]
        self.assertEqual(len(enabled_rows), 14)
        self.assertEqual({row["report_date"] for row in enabled_rows}, expected_dates)
        self.assertFalse(any(row["campaign_id"] == "C-PAUSED" for row in completed_campaigns))
        self.assertEqual(
            next(row for row in enabled_rows if row["report_date"] == "2026-08-10")["spend"],
            Decimal("5"),
        )
        self.assertTrue(
            all(
                row["spend"] == Decimal("0")
                for row in enabled_rows
                if row["report_date"] != "2026-08-10"
            )
        )
        self.assertEqual(len(completed_targets), 14)
        self.assertEqual({row["report_date"] for row in completed_targets}, expected_dates)
        self.assertTrue(all(row["target_id"] == "T1" for row in completed_targets))
        self.assertEqual(
            next(row for row in completed_targets if row["report_date"] == "2026-08-12")["spend"],
            Decimal("5"),
        )
        self.assertTrue(
            all(
                row["spend"] == Decimal("0")
                for row in completed_targets
                if row["report_date"] != "2026-08-12"
            )
        )

    def test_report_reconciliation_blocks_only_affected_campaign(self):
        campaign_rows = [
            {
                "shop_id": "S1",
                "report_date": "2026-08-17",
                "campaign_id": "C-MATCH",
                "spend": "10",
                "sales": "30",
                "orders": "2",
            },
            {
                "shop_id": "S1",
                "report_date": "2026-08-17",
                "campaign_id": "C-MISMATCH",
                "spend": "20",
                "sales": "50",
                "orders": "3",
            },
        ]
        targeting_rows = [
            {
                "shop_id": "S1",
                "report_date": "2026-08-17",
                "campaign_id": "C-MATCH",
                "spend": "4",
                "sales": "10",
                "orders": "1",
            },
            {
                "shop_id": "S1",
                "report_date": "2026-08-17",
                "campaign_id": "C-MATCH",
                "spend": "6",
                "sales": "20",
                "orders": "1",
            },
            {
                "shop_id": "S1",
                "report_date": "2026-08-17",
                "campaign_id": "C-MISMATCH",
                "spend": "19",
                "sales": "50",
                "orders": "3",
            },
        ]

        blocked, mismatch_by_shop = report_reconciliation_blocks(
            campaign_rows,
            targeting_rows,
        )

        self.assertEqual(blocked, {("S1", "C-MISMATCH")})
        self.assertEqual(mismatch_by_shop, {"S1": 1})

    def test_campaign_and_target_blocks_are_applied_independently(self):
        config = self.demo()
        run_id = "separate-blocks"
        with connect_store(config.database_path) as connection:
            seed_demo_data(
                connection,
                config,
                run_id=run_id,
                as_of=date(2026, 8, 19),
            )
            _, _, recommendations = generate_recommendations(
                connection,
                config,
                run_id,
                {("DEMO-SHOP", "CAMP-GROWTH")},
                {("DEMO-SHOP", "CAMP-CUT")},
                as_of=date(2026, 8, 19),
            )

        campaigns = {
            item["campaign_id"]: item
            for item in recommendations
            if item["entity_type"] == "campaign"
        }
        targets = [item for item in recommendations if item["entity_type"] != "campaign"]
        self.assertEqual(campaigns["CAMP-GROWTH"]["rule_id"], "data_incomplete")
        self.assertNotEqual(campaigns["CAMP-CUT"]["rule_id"], "data_incomplete")
        self.assertTrue(
            all(
                item["rule_id"] == "data_incomplete"
                for item in targets
                if item["campaign_id"] == "CAMP-CUT"
            )
        )
        self.assertTrue(
            all(
                item["rule_id"] != "data_incomplete"
                for item in targets
                if item["campaign_id"] == "CAMP-GROWTH"
            )
        )

    def test_base_endpoint_cache_round_trip_validates_shop_scope(self):
        base = self.demo()
        shops = (
            replace(base.shops[0], shop_id="S1", shop_name="店铺一"),
            replace(base.shops[0], shop_id="S2", shop_name="店铺二"),
        )
        endpoint = "/api/cpc/manageData/spCampaign.json"
        cache_path = self.root / "cache" / "campaigns.json"
        results = [
            {
                "shop": shop,
                "items": [{"shopId": shop.shop_id, "campaignId": f"C-{shop.shop_id}"}],
                "pages": 1,
                "error": "",
            }
            for shop in shops
        ]

        write_base_endpoint_cache(cache_path, endpoint, results)
        loaded = load_base_endpoint_cache(cache_path, shops, endpoint)

        self.assertIsNotNone(loaded)
        self.assertEqual([item["shop"].shop_id for item in loaded], ["S1", "S2"])
        self.assertEqual([item["items"][0]["campaignId"] for item in loaded], ["C-S1", "C-S2"])
        self.assertIsNone(load_base_endpoint_cache(cache_path, shops[:1], endpoint))
        other_scope = (shops[0], replace(shops[1], shop_id="S3", shop_name="店铺三"))
        self.assertIsNone(load_base_endpoint_cache(cache_path, other_scope, endpoint))
        self.assertIsNone(load_base_endpoint_cache(cache_path, shops, "/other-endpoint"))

    def test_payload_keeps_shop_currency_trends_and_recommendation_context(self):
        base = self.demo()
        shops = (
            ShopConfig(
                shop_id="S-US",
                shop_name="美国店",
                currency="USD",
                campaign_ids=(),
                rules=base.default_rules,
                marketplace_id="ATVPDKIKX0DER",
                region="NA",
            ),
            ShopConfig(
                shop_id="S-UK",
                shop_name="英国店",
                currency="GBP",
                campaign_ids=(),
                rules=base.default_rules,
                marketplace_id="A1F83G8C2ARO7P",
                region="EU",
            ),
        )
        config = replace(base, shops=shops)
        run_id = "multi-shop-live"
        report_day = date(2026, 8, 17)
        campaign_rows = [
            {
                "shopId": "S-US",
                "campaignId": "C-SHARED",
                "name": "US Campaign",
                "state": "enabled",
                "budget": "50",
            },
            {
                "shopId": "S-UK",
                "campaignId": "C-SHARED",
                "name": "UK Campaign",
                "state": "enabled",
                "budget": "40",
            },
        ]
        metric_rows = []
        for shop_id, spend, sales, orders in (
            ("S-US", "10", "50", "2"),
            ("S-UK", "20", "40", "1"),
        ):
            metric_rows.append(
                normalize_hourly_row(
                    {
                        "shopId": shop_id,
                        "date": report_day.isoformat(),
                        "hour": "12",
                        "campaignId": "C-SHARED",
                        "costs": spend,
                        "clicks": "5",
                        "impressions": "100",
                        "orders": orders,
                        "sales": sales,
                        "units": orders,
                    },
                    aggregation_type="campaign",
                    shop_id=shop_id,
                    report_date=report_day,
                    campaign_id="C-SHARED",
                    run_id=run_id,
                    ingested_at="2026-08-19T09:00:00+08:00",
                )
            )

        with connect_store(config.database_path) as connection:
            insert_campaigns(
                connection,
                run_id,
                "2026-08-19T09:00:00+08:00",
                campaign_rows,
            )
            insert_hourly(connection, metric_rows)
            campaigns, targets, recommendations = generate_recommendations(
                connection,
                config,
                run_id,
                set(),
                as_of=date(2026, 8, 19),
            )
            payload = build_payload(
                connection,
                config,
                run_id=run_id,
                as_of=date(2026, 8, 19),
                mode="live",
                coverage=RunCoverage(
                    requested_calls=2,
                    successful_calls=2,
                    selected_campaigns=2,
                ),
                campaigns=campaigns,
                targets=targets,
                recommendations=recommendations,
            )

        daily = {(item["shop_id"], item["date"]): item for item in payload["daily_trend"]}
        campaign_daily = {
            (item["shop_id"], item["campaign_id"], item["date"]): item
            for item in payload["campaign_daily_trend"]
        }
        recommendations_by_shop = {
            item["shop_id"]: item for item in payload["recommendations"]
        }

        self.assertEqual(payload["meta"]["currencies"], ["GBP", "USD"])
        self.assertEqual((daily[("S-US", "2026-08-17")]["currency"], daily[("S-US", "2026-08-17")]["spend"]), ("USD", 10.0))
        self.assertEqual((daily[("S-UK", "2026-08-17")]["currency"], daily[("S-UK", "2026-08-17")]["spend"]), ("GBP", 20.0))
        self.assertEqual(campaign_daily[("S-US", "C-SHARED", "2026-08-17")]["campaign_name"], "US Campaign")
        self.assertEqual(campaign_daily[("S-UK", "C-SHARED", "2026-08-17")]["campaign_name"], "UK Campaign")
        self.assertEqual((recommendations_by_shop["S-US"]["shop_name"], recommendations_by_shop["S-US"]["currency"]), ("美国店", "USD"))
        self.assertEqual((recommendations_by_shop["S-UK"]["shop_name"], recommendations_by_shop["S-UK"]["currency"]), ("英国店", "GBP"))

    def test_live_payload_publish_rejects_demo_and_replaces_atomically(self):
        source = self.root / "live.json"
        demo_source = self.root / "demo.json"
        destination = self.root / "dashboard" / "ads-monitor.json"
        destination.parent.mkdir(parents=True)
        destination.write_text(
            json.dumps({"meta": {"mode": "live"}, "version": "old"}),
            encoding="utf-8",
        )
        demo_source.write_text(
            json.dumps({"meta": {"mode": "demo"}, "version": "demo"}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(MonitorFailure, "演示数据"):
            publish_live_payload(demo_source, destination)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8"))["version"], "old")

        live_payload = {"meta": {"mode": "live"}, "version": "new"}
        source.write_text(json.dumps(live_payload), encoding="utf-8")
        original_replace = os.replace
        observed = {}

        def inspect_then_replace(temporary, target):
            temporary = Path(temporary)
            target = Path(target)
            observed["temporary"] = temporary
            self.assertEqual(target, destination)
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8"))["version"], "old")
            self.assertEqual(json.loads(temporary.read_text(encoding="utf-8")), live_payload)
            return original_replace(temporary, target)

        with mock.patch("sellfox_ads_monitor.os.replace", side_effect=inspect_then_replace):
            published = publish_live_payload(source, destination)

        self.assertEqual(published, destination)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), live_payload)
        self.assertTrue(observed["temporary"].name.startswith(".ads-monitor.json.tmp-"))
        self.assertFalse(observed["temporary"].exists())

    def test_invalid_rule_direction_is_rejected(self):
        with self.assertRaises(MonitorFailure):
            parse_rules({"target_acos": 0.3, "max_change_pct": -0.1})

    def test_same_target_across_products_aggregates_once(self):
        config = self.demo()
        run_id = "target-grain"
        with connect_store(config.database_path) as connection:
            seed_demo_data(
                connection,
                config,
                run_id=run_id,
                as_of=date(2026, 8, 19),
            )
            extra = normalize_hourly_row(
                {
                    "date": "2026-08-04",
                    "hour": "12",
                    "campaignId": "CAMP-GROWTH",
                    "groupId": "GROUP-1",
                    "targetingId": "KW-GOOD",
                    "targeting": "good keyword",
                    "matchType": "exact",
                    "adId": "AD-2",
                    "msku": "SKU-2",
                    "costs": "1",
                    "clicks": "1",
                    "impressions": "10",
                    "orders": "0",
                    "sales": "0",
                    "units": "0",
                },
                aggregation_type="target",
                shop_id="DEMO-SHOP",
                report_date=date(2026, 8, 4),
                campaign_id="CAMP-GROWTH",
                run_id=run_id,
                ingested_at="now",
            )
            insert_hourly(connection, [extra])
            shops = {shop.shop_id: shop for shop in config.shops}
            campaigns = aggregate_campaigns(connection, run_id, shops)
            targets = aggregate_targets(connection, run_id, campaigns, shops)
        matching = [item for item in targets if item["target_id"] == "KW-GOOD"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["spend"], Decimal("141.00"))

    def test_budget_rule_uses_recent_natural_days(self):
        config = self.demo()
        run_id = "natural-days"
        with connect_store(config.database_path) as connection:
            seed_demo_data(
                connection,
                config,
                run_id=run_id,
                as_of=date(2026, 8, 19),
            )
            connection.execute(
                """
                UPDATE hourly_fact_history SET spend = '50'
                WHERE run_id = ? AND aggregation_type = 'campaign'
                  AND campaign_id = 'CAMP-GROWTH' AND report_date <= '2026-08-10'
                """,
                (run_id,),
            )
            connection.execute(
                """
                DELETE FROM hourly_fact_history
                WHERE run_id = ? AND aggregation_type = 'campaign'
                  AND campaign_id = 'CAMP-GROWTH' AND report_date > '2026-08-10'
                """,
                (run_id,),
            )
            shops = {shop.shop_id: shop for shop in config.shops}
            campaigns = aggregate_campaigns(
                connection, run_id, shops, date(2026, 8, 17)
            )
        growth = next(item for item in campaigns if item["campaign_id"] == "CAMP-GROWTH")
        self.assertEqual(growth["budget_utilization_days_7d"], 0)
        self.assertFalse(growth["latest_complete_budget_full"])

    def test_budget_full_uses_98_percent_on_latest_complete_day(self):
        config = self.demo()
        run_id = "budget-full-boundary"
        with connect_store(config.database_path) as connection:
            seed_demo_data(connection, config, run_id=run_id, as_of=date(2026, 8, 19))
            connection.execute(
                """
                UPDATE hourly_fact_history SET spend = '49'
                WHERE run_id = ? AND aggregation_type = 'campaign'
                  AND campaign_id = 'CAMP-GROWTH' AND report_date = '2026-08-17'
                """,
                (run_id,),
            )
            shops = {shop.shop_id: shop for shop in config.shops}
            campaigns = aggregate_campaigns(connection, run_id, shops, date(2026, 8, 17))
        growth = next(item for item in campaigns if item["campaign_id"] == "CAMP-GROWTH")
        self.assertTrue(growth["latest_complete_budget_full"])
        self.assertEqual(growth["budget_utilization_days_7d"], 1)

    def test_stale_latest_day_blocks_suggestion(self):
        config = self.demo()
        run_id = "stale-day"
        with connect_store(config.database_path) as connection:
            seed_demo_data(
                connection,
                config,
                run_id=run_id,
                as_of=date(2026, 8, 19),
            )
            connection.execute(
                """
                DELETE FROM hourly_fact_history
                WHERE run_id = ? AND report_date = '2026-08-17'
                  AND campaign_id = 'CAMP-GROWTH'
                """,
                (run_id,),
            )
            _, _, recommendations = generate_recommendations(
                connection,
                config,
                run_id,
                set(),
                as_of=date(2026, 8, 19),
            )
        growth = [
            item
            for item in recommendations
            if item["campaign_id"] == "CAMP-GROWTH"
        ]
        self.assertTrue(growth)
        self.assertTrue(all(item["action_code"] == "BLOCKED" for item in growth))
        self.assertTrue(all(item["rule_id"] == "stale_data" for item in growth))

    def test_transport_failure_is_wrapped_for_partial_run_handling(self):
        client = object.__new__(SellfoxAdsClient)
        client.logger = logging.getLogger("test")
        client._last_order_call = 0.0
        client._throttle = lambda: None
        client._signed_params = lambda path: {}

        def fail(*args, **kwargs):
            from sellfox_import import ImportFailure

            raise ImportFailure("network failed")

        client._request_json = fail
        with self.assertRaisesRegex(MonitorFailure, "network failed"):
            client.post_data("/test", {}, "test")


if __name__ == "__main__":
    unittest.main()
