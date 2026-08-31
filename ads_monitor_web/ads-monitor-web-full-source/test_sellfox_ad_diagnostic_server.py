from __future__ import annotations

import http.client
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import sellfox_ad_diagnostic_server as diagnostic


CAMPAIGN_ID = "70540977760495"
GROUP_ID = "189415784985387"
AD_ID = "459104320731581"
KEYWORD_ID = "123456789"
SKU = "21-180B"
ASIN = "B0CQKVFVHH"
NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def post_data(self, path, body, purpose):
        self.calls.append((path, dict(body)))
        if path == diagnostic.SP_CAMPAIGN_PATH:
            return {
                "itemList": [
                    {
                        "shopId": diagnostic.PILOT_SHOP_ID,
                        "campaignId": CAMPAIGN_ID,
                        "name": "21-180B lash clusters up-4.22",
                        "state": "enabled",
                        "budget": "50",
                        "targetingType": "manual",
                        "servingStatus": "CAMPAIGN_STATUS_ENABLED",
                    }
                ],
                "nextToken": "",
            }
        if path == diagnostic.SP_GROUP_PATH:
            return {
                "itemList": [
                    {
                        "shopId": diagnostic.PILOT_SHOP_ID,
                        "campaignId": CAMPAIGN_ID,
                        "groupId": GROUP_ID,
                        "name": "lash clusters",
                        "defaultBid": "0.8",
                        "state": "enabled",
                        "servingStatus": "AD_GROUP_STATUS_ENABLED",
                    }
                ],
                "nextToken": "",
            }
        if path == diagnostic.SP_AD_PRODUCT_PATH:
            return {
                "itemList": [
                    {
                        "shopId": diagnostic.PILOT_SHOP_ID,
                        "campaignId": CAMPAIGN_ID,
                        "groupId": GROUP_ID,
                        "adId": AD_ID,
                        "asin": ASIN,
                        "sku": SKU,
                        "state": "enabled",
                        "servingStatus": "CAMPAIGN_OUT_OF_BUDGET",
                    }
                ],
                "nextToken": "",
            }
        if path == diagnostic.SP_KEYWORD_PATH:
            return {
                "itemList": [
                    {
                        "shopId": diagnostic.PILOT_SHOP_ID,
                        "campaignId": CAMPAIGN_ID,
                        "groupId": GROUP_ID,
                        "keywordId": KEYWORD_ID,
                        "keywordText": "lash clusters",
                        "matchType": "exact",
                        "bid": "0.8",
                        "state": "enabled",
                    }
                ],
                "nextToken": "",
            }
        if path in {
            diagnostic.SP_PRODUCT_TARGET_PATH,
            diagnostic.SP_NEGATIVE_KEYWORD_PATH,
            diagnostic.SP_NEGATIVE_TARGET_PATH,
        }:
            return {"itemList": [], "nextToken": ""}
        if path == diagnostic.ONLINE_PRODUCT_PATH:
            return {
                "rows": [
                    {
                        "shopId": diagnostic.PILOT_SHOP_ID,
                        "marketplaceId": diagnostic.PILOT_MARKETPLACE_ID,
                        "asin": ASIN,
                        "sku": SKU,
                        "openDate": "2023-12-18 00:00:00",
                        "onlineStatus": "Active",
                        "title": "Lash Clusters",
                        "totalInventory": "200",
                        "profitRate": "21.5",
                    },
                    {"shopId": "OTHER", "asin": ASIN, "sku": SKU},
                ],
                "totalPage": 1,
                "totalSize": 2,
            }
        if path == diagnostic.PRODUCT_ANALYSIS_PATH:
            return {
                "rows": [
                    {
                        "shopIdList": [diagnostic.PILOT_SHOP_ID],
                        "marketplaceIdList": [diagnostic.PILOT_MARKETPLACE_ID],
                        "skuList": [SKU],
                        "asinList": [ASIN],
                        "salePriceThis": "500",
                        "profitRateThis": "20.5",
                        "adCostThis": "100",
                        "acosThis": "36.78",
                    },
                    {"shopIdList": [diagnostic.PILOT_SHOP_ID], "skuList": ["OTHER"]},
                ],
                "totalPage": 1,
                "totalSize": 2,
            }
        if path == diagnostic.PRODUCT_PROFIT_PATH:
            return {
                "rows": [
                    {
                        "shopIdList": [diagnostic.PILOT_SHOP_ID],
                        "skuList": [{"sku": SKU, "name": SKU}],
                        "mskuList": [SKU],
                        "asinList": [{"asin": ASIN, "url": "https://example.test"}],
                        "profit": "100",
                        "profitRate": "20",
                        "adTotalCost": "-90",
                        "adTotalCostSp": "-80",
                        "adSpCost": "-80",
                        "adSbCost": "-4",
                        "adSbvCost": "-3",
                        "adSbsCost": "0",
                        "adSdCost": "-3",
                    }
                ],
                "totalPage": 1,
                "totalSize": 1,
            }
        if path == diagnostic.FBA_RETURN_PATH:
            return {
                "rows": [
                    {
                        "shopId": diagnostic.PILOT_SHOP_ID,
                        "msku": SKU,
                        "asin": ASIN,
                        "quantity": "2",
                        "reason": "DAMAGED",
                        "reasonStr": "商品损坏",
                        "status": "Unit returned to inventory",
                        "customerComments": "sensitive",
                        "orderId": "secret-order",
                    }
                ],
                "totalPage": 1,
                "totalSize": 1,
            }
        if path == diagnostic.PRODUCT_SALES_PATH:
            metric = body["type"]
            return {
                "rows": [
                    {
                        "shopIds": [diagnostic.PILOT_SHOP_ID],
                        "skus": [SKU],
                        "mskus": [SKU],
                        "asins": [ASIN],
                        "productSaleDayOpenVo": [
                            {"day": "2026-08-20", metric: "10", "currency": "USD"}
                        ],
                    }
                ],
                "totalPage": 1,
                "totalSize": 1,
            }
        if path in {
            diagnostic.SP_HOUR_CAMPAIGN_PATH,
            diagnostic.SP_HOUR_GROUP_PATH,
            diagnostic.SP_HOUR_AD_PRODUCT_PATH,
            diagnostic.SP_HOUR_TARGET_PATH,
            diagnostic.SP_HOUR_PLACEMENT_PATH,
        }:
            row = {
                "shopId": diagnostic.PILOT_SHOP_ID,
                "campaignId": CAMPAIGN_ID,
                "date": body["date"],
                "hour": "3",
                "costs": "20",
                "clicks": "20",
                "impressions": "1000",
                "orders": "2",
                "sales": "20",
                "units": "2",
                "sameOrders": "2",
                "sameSales": "20",
                "sameUnits": "2",
                "groupId": GROUP_ID,
                "adId": AD_ID,
                "targetingId": KEYWORD_ID,
                "targeting": "lash clusters",
                "matchType": "exact",
                "placement": "Top of search",
                "msku": SKU,
                "asin": ASIN,
            }
            return {"itemList": [row], "totalCount": "1"}
        raise AssertionError(f"unexpected path {path}")


def mature_payload() -> dict:
    return {
        "meta": {
            "mode": "live",
            "generated_at": "2026-08-21T10:48:58+08:00",
            "source_start_date": "2026-08-06",
            "source_end_date": "2026-08-19",
            "maturity_lag_days": 2,
            "lookback_days": 14,
        },
        "campaigns": [
            {
                "shop_id": diagnostic.PILOT_SHOP_ID,
                "campaign_id": CAMPAIGN_ID,
                "campaign_name": "21-180B lash clusters up-4.22",
                "state": "enabled",
                "spend": 700.84,
                "sales": 1656.39,
                "orders": 153,
                "clicks": 1000,
                "impressions": 100000,
                "acos": 0.4231,
                "data_days": 14,
                "latest_date": "2026-08-19",
            }
        ],
        "targets": [
            {
                "shop_id": diagnostic.PILOT_SHOP_ID,
                "campaign_id": CAMPAIGN_ID,
                "target_id": KEYWORD_ID,
                "targeting": "lash clusters",
                "spend": 700.84,
                "sales": 1656.39,
                "orders": 153,
                "acos": 0.4231,
            }
        ],
        "recommendations": [
            {
                "shop_id": diagnostic.PILOT_SHOP_ID,
                "campaign_id": CAMPAIGN_ID,
                "entity_type": "keyword",
                "target_id": KEYWORD_ID,
                "target_text": "lash clusters",
                "action_code": "DECREASE_BID",
                "priority": "高",
                "current_value": "0.80",
                "proposed_value": "0.72",
                "spend": "700.84",
                "target_acos": "0.3",
                "rule_id": "high_acos",
                "reason": "成熟层高ACoS。",
            }
        ],
        "campaign_daily_trend": [
            {
                "shop_id": diagnostic.PILOT_SHOP_ID,
                "campaign_id": CAMPAIGN_ID,
                "date": "2026-08-19",
                "spend": 50,
                "sales": 100,
            }
        ],
    }


class DiagnosticServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.payload_path = self.root / "ads-monitor.json"
        self.payload_path.write_text(
            json.dumps(mature_payload(), ensure_ascii=False), encoding="utf-8"
        )
        self.fake_clock = FakeClock()
        self.clients: list[FakeClient] = []

        def factory():
            client = FakeClient()
            self.clients.append(client)
            return client

        self.service = diagnostic.DiagnosticService(
            client_factory=factory,
            mature_payload_path=self.payload_path,
            realtime_payload_path=self.root / "missing-realtime.json",
            metrics_db_path=self.root / "missing.sqlite3",
            clock=lambda: NOW,
            monotonic=self.fake_clock,
        )
        self.deep_patch = mock.patch.object(diagnostic, "DEEP_REPORT_DIR", self.root / "missing")
        self.deep_patch.start()

    def tearDown(self) -> None:
        self.deep_patch.stop()
        self.temp.cleanup()

    def test_campaign_list_is_fixed_shop_and_uses_live_sources(self):
        payload = self.service.campaigns()
        self.assertEqual(payload["shop"]["shop_id"], diagnostic.PILOT_SHOP_ID)
        self.assertEqual(payload["campaigns"][0]["campaignId"], CAMPAIGN_ID)
        self.assertEqual(payload["campaigns"][0]["action_codes"], ["DECREASE_BID"])
        self.assertEqual(payload["campaigns"][0]["spend"], 700.84)
        self.assertEqual(payload["campaigns"][0]["priority"], "高")
        self.assertEqual(payload["campaigns"][0]["action"], "DECREASE_BID")
        self.assertEqual(payload["campaigns"][0]["default_bid"], 0.8)
        self.assertEqual(payload["campaigns"][0]["total_target_count"], 1)
        self.assertEqual(payload["campaigns"][0]["advertised_product_count"], 1)

    def test_campaign_list_uses_only_fresh_same_day_budget_progress(self):
        realtime_path = self.root / "ads-realtime.json"
        realtime_path.write_text(json.dumps({
            "campaigns": [{
                "shop_id": diagnostic.PILOT_SHOP_ID,
                "campaign_id": CAMPAIGN_ID,
                "freshness": {"status": "fresh"},
                "today": {"report_date": "2026-08-21", "latest_hour": 4, "spend": 49},
            }],
        }), encoding="utf-8")
        self.service.realtime_payload_path = realtime_path
        campaign = self.service.campaigns()["campaigns"][0]
        self.assertEqual(campaign["today_budget_progress"], 0.98)
        self.assertEqual(campaign["today_budget_status"], "fresh")
        self.assertTrue(self.clients[0].closed)
        for path, body in self.clients[0].calls:
            self.assertEqual(body.get("shopId"), diagnostic.PILOT_SHOP_ID)
            self.assertIn(path, {
                diagnostic.SP_CAMPAIGN_PATH,
                diagnostic.SP_GROUP_PATH,
                diagnostic.SP_AD_PRODUCT_PATH,
                diagnostic.SP_KEYWORD_PATH,
                diagnostic.SP_PRODUCT_TARGET_PATH,
            })

    def test_campaign_windows_include_purchase_rate(self):
        metrics_path = self.root / "metrics.sqlite3"
        connection = sqlite3.connect(metrics_path)
        connection.execute(
            """
            CREATE TABLE hourly_fact_history (
                aggregation_type TEXT,
                shop_id TEXT,
                campaign_id TEXT,
                report_date TEXT,
                report_hour INTEGER,
                spend REAL,
                clicks INTEGER,
                impressions INTEGER,
                orders INTEGER,
                sales REAL,
                ingested_at TEXT,
                run_id TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO hourly_fact_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("campaign", diagnostic.PILOT_SHOP_ID, CAMPAIGN_ID, "2026-08-19", 3, 20, 20, 1000, 2, 40, "2026-08-20T00:00:00Z", "run-1"),
        )
        connection.commit()
        connection.close()
        service = diagnostic.DiagnosticService(
            client_factory=FakeClient,
            mature_payload_path=self.payload_path,
            metrics_db_path=metrics_path,
            clock=lambda: NOW,
            monotonic=self.fake_clock,
        )

        windows, source = service._campaign_windows()

        self.assertEqual(source["status"], "ok")
        self.assertEqual(windows[CAMPAIGN_ID]["14d"]["cvr"], 0.1)
        self.assertEqual(
            windows[CAMPAIGN_ID]["14d"]["daily_trend"],
            [{
                "date": "2026-08-19",
                "spend": 20,
                "clicks": 20,
                "impressions": 1000,
                "orders": 2,
                "sales": 40,
            }],
        )

    def test_campaign_windows_fall_back_to_current_campaign_report(self):
        report_dir = self.root / "reports"
        report_dir.mkdir()
        report_path = report_dir / "adCampaignReport-1-1.xlsx"
        report_path.touch()
        start = date(2026, 8, 6)
        rows = [
            {
                "店铺": diagnostic.PILOT_SHOP_NAME,
                "日期": (start + timedelta(days=offset)).isoformat(),
                "广告活动ID": CAMPAIGN_ID,
                "广告花费": "10",
                "广告点击量": "2",
                "广告曝光量": "100",
                "广告订单量": "1",
                "广告销售额": "20",
            }
            for offset in range(14)
        ]
        service = diagnostic.DiagnosticService(
            client_factory=FakeClient,
            mature_payload_path=self.payload_path,
            metrics_db_path=self.root / "missing.sqlite3",
            deep_report_dir=report_dir,
            clock=lambda: NOW,
            monotonic=self.fake_clock,
        )

        with mock.patch.object(service, "_read_report", return_value=(list(rows[0]), rows)):
            windows, source = service._campaign_windows()

        self.assertEqual(source["status"], "partial")
        self.assertEqual(source["error"], "30D_WINDOW_UNAVAILABLE")
        self.assertEqual(source["supported_windows"], ["7d", "14d"])
        self.assertEqual(windows[CAMPAIGN_ID]["7d"]["spend"], 70)
        self.assertEqual(windows[CAMPAIGN_ID]["14d"]["spend"], 140)
        self.assertEqual(windows[CAMPAIGN_ID]["14d"]["cvr"], 0.5)
        self.assertEqual(len(windows[CAMPAIGN_ID]["14d"]["daily_trend"]), 14)
        self.assertNotIn("30d", windows[CAMPAIGN_ID])

    def test_detail_joins_sku_aggregates_today_and_explains_conflict(self):
        payload = self.service.campaign_detail(CAMPAIGN_ID)
        listing = payload["listing_context"][0]
        decision = payload["decision"]
        self.assertEqual(listing["mapping_status"], "matched")
        self.assertEqual(listing["listing_stage"], "established")
        self.assertEqual(listing["finance"]["adTotalCost"], 90)
        self.assertEqual(listing["finance"]["adSpCost"], 80)
        self.assertEqual(listing["finance"]["adSbvCost"], 3)
        self.assertEqual(set(listing["operating_windows"]), {"7d", "14d", "30d"})
        self.assertTrue(all(
            item["finance_mapping_status"] == "matched"
            for item in listing["operating_windows"].values()
        ))
        profit_calls = [
            body
            for client in self.clients
            for path, body in client.calls
            if path == diagnostic.PRODUCT_PROFIT_PATH
        ]
        self.assertEqual(
            sorted(
                (date.fromisoformat(body["endDate"]) - date.fromisoformat(body["startDate"])).days + 1
                for body in profit_calls
            ),
            [7, 14, 30],
        )
        self.assertEqual(listing["returns"]["total_quantity"], 2)
        self.assertEqual(listing["returns"]["top_reasons"][0]["rate"], 1.0)
        self.assertEqual(listing["sales_trend"]["salePrice"][0]["salePrice"], "10")
        self.assertEqual(listing["sales_trend"]["orderNum"][0]["orderNum"], "10")
        self.assertEqual(listing["sales_trend"]["productNum"][0]["productNum"], "10")
        self.assertNotIn("customerComments", json.dumps(listing, ensure_ascii=False))
        self.assertNotIn("secret-order", json.dumps(listing, ensure_ascii=False))
        self.assertEqual(decision["primary_action"]["action_code"], "DECREASE_BID")
        self.assertEqual(decision["action"], "DECREASE_BID")
        self.assertIsInstance(decision["confidence"], float)
        self.assertTrue(decision["evidence"])
        self.assertEqual(decision["blockers"], [])
        self.assertIsInstance(decision["mature_evidence"], list)
        self.assertEqual(decision["today_confirmation"]["status"], "confirmed")
        self.assertEqual(decision["execution_gate"], "REVIEW")
        self.assertIn(
            "OUT_OF_BUDGET_NOT_PROOF_TO_INCREASE",
            {item["code"] for item in decision["conflicts"]},
        )
        self.assertNotEqual(decision["action"], "INCREASE_BUDGET")
        self.assertFalse(decision["budget_guardrail_passed"])
        self.assertFalse(payload["performance"]["mature_14d"]["is_realtime"])
        self.assertEqual(payload["performance"]["mature_14d"]["source_end_date"], "2026-08-19")
        pacing = payload["performance"]["today"]["pacing"]
        self.assertEqual(pacing["report_timezone"], "America/Los_Angeles")
        self.assertEqual(pacing["latest_complete_hour"], 3)
        self.assertTrue(pacing["comparison_ready"])
        self.assertEqual(pacing["today"]["spend"], 20)
        self.assertEqual(pacing["yesterday_same_hour"]["spend"], 20)
        self.assertEqual(pacing["yesterday_same_hour"]["change"], 0)
        self.assertEqual(pacing["prior_7d_same_hour"]["available_days"], 7)
        self.assertEqual(pacing["prior_7d_same_hour"]["median_spend"], 20)
        self.assertEqual(pacing["yesterday_full_day"]["spend"], 20)
        self.assertEqual(len(pacing["history"]), 7)
        required = {"endpoint", "fetched_at", "effective_date", "row_count", "pages", "status", "error", "cache_status"}
        self.assertTrue(all(required <= set(source) for source in payload["sources"]))

    def test_overview_skips_full_context_and_search_term_xlsx(self):
        report_dir = self.root / "overview-reports"
        report_dir.mkdir()
        index = {
            "meta": {
                "shop_id": diagnostic.PILOT_SHOP_ID,
                "shop_name": diagnostic.PILOT_SHOP_NAME,
                "report_start_date": "2026-08-06",
                "report_end_date": "2026-08-19",
            },
            "campaigns": {
                CAMPAIGN_ID: {
                    "entity_count": 12,
                    "waste_count": 11,
                    "conversion_count": 1,
                    "summary": {"spend": 25, "sales": 20},
                    "waste_summary": {"spend": 5, "effective_sample_count": 1},
                    "conversion_summary": {"orders": 1, "sales": 20},
                    "waste": [
                        {"identity": {"用户搜索词": f"waste-{index}"}, "spend": 1}
                        for index in range(11)
                    ],
                    "conversion": [
                        {"identity": {"用户搜索词": "winner"}, "orders": 1, "sales": 20}
                    ],
                }
            },
        }
        (report_dir / diagnostic.SEARCH_TERM_INDEX_NAME).write_text(
            json.dumps(index, ensure_ascii=False), encoding="utf-8"
        )
        with mock.patch.object(diagnostic, "DEEP_REPORT_DIR", report_dir), mock.patch.object(
            self.service, "_read_report", side_effect=AssertionError("overview parsed xlsx")
        ):
            payload = self.service.campaign_detail(CAMPAIGN_ID, section="overview")

        paths = {path for client in self.clients for path, _ in client.calls}
        self.assertNotIn(diagnostic.SP_GROUP_PATH, paths)
        self.assertNotIn(diagnostic.SP_KEYWORD_PATH, paths)
        self.assertNotIn(diagnostic.PRODUCT_ANALYSIS_PATH, paths)
        self.assertNotIn(diagnostic.PRODUCT_PROFIT_PATH, paths)
        self.assertNotIn(diagnostic.FBA_RETURN_PATH, paths)
        self.assertNotIn(diagnostic.PRODUCT_SALES_PATH, paths)
        search = payload["performance"]["mature_14d"]["deep_reports"]["search_terms"]
        self.assertEqual(len(search["top_waste"]), 10)
        self.assertEqual(search["waste_count"], 11)
        self.assertEqual(search["conversion_count"], 1)
        self.assertEqual(search["waste_summary"]["spend"], 5)
        self.assertEqual(search["conversion_summary"]["orders"], 1)

    def test_search_term_index_pages_lazily_and_caps_page_size(self):
        report_dir = self.root / "paged-reports"
        report_dir.mkdir()
        rows = [
            {
                "identity": {
                    "用户搜索词": f"term-{index}",
                    "广告投放ID": f"T{index}",
                    "投放": "close-match",
                    "匹配类型": "自动",
                },
                "spend": 20 - index,
                "units": index,
                "same_orders": index,
                "same_sales": index * 2,
            }
            for index in range(13)
        ]
        payload = {
            "meta": {
                "shop_id": diagnostic.PILOT_SHOP_ID,
                "shop_name": diagnostic.PILOT_SHOP_NAME,
                "report_start_date": "2026-08-06",
                "report_end_date": "2026-08-19",
            },
            "campaigns": {
                CAMPAIGN_ID: {
                    "entity_count": 13,
                    "waste_count": 13,
                    "conversion_count": 0,
                    "summary": {"units": 78},
                    "waste_summary": {"spend": 91},
                    "conversion_summary": {},
                    "waste": rows,
                    "conversion": [],
                }
            },
        }
        (report_dir / diagnostic.SEARCH_TERM_INDEX_NAME).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        with mock.patch.object(diagnostic, "DEEP_REPORT_DIR", report_dir):
            page = self.service.search_term_page(
                CAMPAIGN_ID, "waste", page=2, page_size=10
            )
            with self.assertRaises(diagnostic.BadRequest):
                self.service.search_term_page(
                    CAMPAIGN_ID, "waste", page=1, page_size=11
                )

        self.assertEqual(page["total"], 13)
        self.assertEqual(page["total_pages"], 2)
        self.assertEqual(len(page["rows"]), 3)
        self.assertEqual(page["kind_summary"]["spend"], 91)
        self.assertEqual(page["rows"][0]["identity"]["广告投放ID"], "T10")
        self.assertEqual(page["rows"][0]["same_sales"], 20)

    def test_auto_campaign_bid_action_becomes_manual_target_review(self):
        decision = self.service._build_decision(
            {"targetingType": "auto"},
            {"ad_products": [{"servingStatus": "AD_STATUS_LIVE"}]},
            [{"listing_stage": "established"}],
            mature_payload(),
            {"targets": {"rows": []}, "campaign": {"rows": []}},
            [{"source_id": "mature_14d", "status": "ok"}],
        )

        self.assertEqual(decision["action"], "REVIEW_TARGET")
        self.assertEqual(decision["primary_action"]["original_action_code"], "DECREASE_BID")
        self.assertFalse(decision["primary_action"]["can_adjust_keyword_cpc"])
        self.assertEqual(
            decision["primary_action"]["recommended_match_types"], ["exact", "broad"]
        )
        self.assertEqual(decision["today_confirmation"]["status"], "review")
        self.assertIn(
            "AUTO_CAMPAIGN_NO_KEYWORD_CPC",
            {item["code"] for item in decision["protections"]},
        )

    def test_normal_cache_force_refresh_and_cooldown(self):
        first = self.service.campaigns()
        second = self.service.campaigns()
        self.assertEqual(len(self.clients), 1)
        self.assertEqual(first["meta"]["cache_status"], "miss")
        self.assertEqual(second["meta"]["cache_status"], "hit")
        self.service.campaigns(refresh=True)
        self.assertEqual(len(self.clients), 2)
        with self.assertRaises(diagnostic.RefreshLimited):
            self.service.campaigns(refresh=True)

    def test_invalid_or_foreign_campaign_is_rejected(self):
        with self.assertRaises(diagnostic.BadRequest):
            self.service.campaign_detail("../../secret")

        class EmptyClient(FakeClient):
            def post_data(self, path, body, purpose):
                if path == diagnostic.SP_CAMPAIGN_PATH:
                    return {"itemList": [], "nextToken": ""}
                return super().post_data(path, body, purpose)

        service = diagnostic.DiagnosticService(
            client_factory=EmptyClient,
            mature_payload_path=self.payload_path,
            clock=lambda: NOW,
        )
        with self.assertRaises(diagnostic.NotFound):
            service.campaign_detail("999999")

    def test_listing_unknown_blocks_and_new_listing_is_protected(self):
        mature = mature_payload()
        base = self.clients[0] if self.clients else FakeClient()
        structure = {
            "ad_products": [
                {"campaignId": CAMPAIGN_ID, "servingStatus": "AD_STATUS_LIVE"}
            ]
        }
        today = {"targets": {"rows": []}, "campaign": {"rows": []}}
        sources = [{"source_id": "mature_14d", "status": "ok"}]
        unknown = self.service._build_decision(
            {}, structure, [{"listing_stage": "unknown"}], mature, today, sources
        )
        new = self.service._build_decision(
            {}, structure, [{"listing_stage": "new"}], mature, today, sources
        )
        self.assertEqual(unknown["execution_gate"], "BLOCK")
        self.assertIn("LISTING_UNKNOWN_BLOCK", {item["code"] for item in unknown["protections"]})
        self.assertEqual(new["execution_gate"], "REVIEW")
        self.assertIn("NEW_LISTING_PROTECTION", {item["code"] for item in new["protections"]})

    def test_out_of_budget_never_overrides_keyword_decrease_with_budget_increase(self):
        mature = mature_payload()
        mature["recommendations"].insert(
            0,
            {
                "shop_id": diagnostic.PILOT_SHOP_ID,
                "campaign_id": CAMPAIGN_ID,
                "entity_type": "campaign",
                "action_code": "INCREASE_BUDGET",
                "priority": "高",
                "spend": "9999",
                "reason": "预算耗尽。",
            },
        )
        decision = self.service._build_decision(
            {"servingStatus": "CAMPAIGN_OUT_OF_BUDGET"},
            {"ad_products": [{"servingStatus": "CAMPAIGN_OUT_OF_BUDGET"}]},
            [{"listing_stage": "established"}],
            mature,
            {"targets": {"rows": []}, "campaign": {"rows": []}},
            [{"source_id": "mature_14d", "status": "ok"}],
        )
        self.assertEqual(decision["action"], "DECREASE_BID")
        self.assertEqual(decision["primary_action"]["action_code"], "DECREASE_BID")
        self.assertFalse(decision["budget_guardrail_passed"])

    def test_deep_report_aggregation_marks_waste_and_recomputes_ratios(self):
        rows = [
            {
                "日期": "2026-08-19",
                "用户搜索词": "waste",
                "广告投放ID": "1",
                "投放": "lash",
                "匹配类型": "广泛",
                "广告花费": "10",
                "广告曝光量": "100",
                "广告点击量": "10",
                "广告订单量": "0",
                "广告销售额": "0",
            },
            {
                "日期": "2026-08-19",
                "用户搜索词": "winner",
                "广告投放ID": "1",
                "投放": "lash",
                "匹配类型": "广泛",
                "广告花费": "5",
                "广告曝光量": "100",
                "广告点击量": "5",
                "广告订单量": "2",
                "广告销售额": "20",
            },
        ]
        result = diagnostic.DiagnosticService._aggregate_deep_rows(
            rows,
            ("用户搜索词", "广告投放ID", "投放", "匹配类型"),
            "search_terms",
        )
        self.assertEqual(result["summary"]["spend"], 15)
        self.assertEqual(result["summary"]["sales"], 20)
        self.assertEqual(result["summary"]["acos"], 0.75)
        self.assertEqual(result["top_waste"][0]["identity"]["用户搜索词"], "waste")
        self.assertEqual(result["top_converting"][0]["identity"]["用户搜索词"], "winner")

    def test_read_endpoint_registry_contains_no_write_paths(self):
        joined = " ".join(diagnostic.READ_ENDPOINTS).lower()
        for token in ("edit", "create", "close", "archive", "delete"):
            self.assertNotIn(token, joined)

    def test_cursor_requires_explicit_shop_and_campaign_scope(self):
        class ScopeClient:
            def post_data(self, path, body, purpose):
                base = {"shopId": diagnostic.PILOT_SHOP_ID, "campaignId": CAMPAIGN_ID}
                return {
                    "itemList": [
                        base,
                        {"campaignId": CAMPAIGN_ID},
                        {"shopId": diagnostic.PILOT_SHOP_ID},
                        {"shopId": "OTHER", "campaignId": CAMPAIGN_ID},
                    ],
                    "nextToken": "",
                }

        rows, trace, dropped = self.service._cursor(
            ScopeClient(),
            "scope_probe",
            diagnostic.SP_GROUP_PATH,
            {"shopId": diagnostic.PILOT_SHOP_ID, "campaignId": CAMPAIGN_ID},
            campaign_id=CAMPAIGN_ID,
        )
        self.assertEqual(rows, [{"shopId": diagnostic.PILOT_SHOP_ID, "campaignId": CAMPAIGN_ID}])
        self.assertEqual(dropped, 3)
        self.assertEqual(trace["scope_dropped"], 3)

    def test_sales_trend_rejects_empty_shop_id(self):
        class EmptyShopClient:
            def post_data(self, path, body, purpose):
                return {
                    "rows": [
                        {
                            "shopId": "",
                            "shopIdList": [diagnostic.PILOT_SHOP_ID],
                            "sku": SKU,
                            "productSaleDayOpenVo": [],
                        }
                    ],
                    "totalPage": 1,
                    "totalSize": 1,
                }

        output, traces = self.service._fetch_product_sales_trends(
            EmptyShopClient(), {(ASIN, SKU)}, date(2026, 8, 21)
        )
        self.assertEqual(output, {SKU: {}})
        self.assertTrue(all(trace["row_count"] == 0 for trace in traces))
        self.assertTrue(all(trace["scope_dropped"] == 1 for trace in traces))

    def test_hour_preserves_provisional_counter_anomaly_but_never_confirms_it(self):
        class HourClient:
            def post_data(self, path, body, purpose):
                exact = {
                    "shopId": diagnostic.PILOT_SHOP_ID,
                    "campaignId": CAMPAIGN_ID,
                    "date": body["date"],
                    "hour": "12",
                    "clicks": "1",
                    "impressions": "0",
                    "costs": "0.96",
                    "orders": "0",
                    "sales": "0",
                    "targetingId": KEYWORD_ID,
                }
                return {
                    "itemList": [
                        exact,
                        {**exact, "shopId": ""},
                        {**exact, "campaignId": ""},
                        {**exact, "date": ""},
                    ]
                }

        rows, trace = self.service._hour(
            HourClient(),
            "hour_target",
            diagnostic.SP_HOUR_TARGET_PATH,
            "target",
            CAMPAIGN_ID,
            date(2026, 8, 20),
            120,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["shopId"], diagnostic.PILOT_SHOP_ID)
        self.assertEqual(trace["status"], "partial")
        self.assertEqual(trace["anomaly_rows"], 1)
        self.assertEqual(trace["scope_dropped"], 3)
        self.assertIn(diagnostic.PROVISIONAL_COUNTER_ANOMALY, trace["quality_issues"])

        mature = mature_payload()
        decision = self.service._build_decision(
            {},
            {"ad_products": [{"shopId": diagnostic.PILOT_SHOP_ID}]},
            [{"listing_stage": "established"}],
            mature,
            {
                "targets": {
                    "rows": rows,
                    "quality_status": "partial",
                    "quality_issues": [diagnostic.PROVISIONAL_COUNTER_ANOMALY],
                }
            },
            [{"source_id": "hour_target", "status": "partial"}],
        )
        self.assertEqual(decision["today_confirmation"]["status"], "watch")
        self.assertIn(
            diagnostic.PROVISIONAL_COUNTER_ANOMALY,
            {item["code"] for item in decision["conflicts"]},
        )

    def test_mature_snapshot_wrong_d2_window_fails_closed(self):
        payload = mature_payload()
        payload["meta"]["source_end_date"] = "2026-08-20"
        self.payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        service = diagnostic.DiagnosticService(
            client_factory=FakeClient,
            mature_payload_path=self.payload_path,
            clock=lambda: NOW,
        )
        context, trace = service._mature_context(CAMPAIGN_ID)
        self.assertEqual(context["status"], "unavailable")
        self.assertEqual(context["campaigns"], [])
        self.assertEqual(trace["status"], "error")
        self.assertEqual(trace["error"], "MATURE_SNAPSHOT_DATE_WINDOW_INVALID")
        self.assertEqual(trace["expected_end_date"], "2026-08-19")

    def test_deep_report_requires_exact_shop_and_d2_window(self):
        report_dir = self.root / "reports"
        report_dir.mkdir()
        report_path = report_dir / "adCampaignReport-1-1.xlsx"
        report_path.touch()
        start = date(2026, 8, 6)
        rows = [
            {
                "店铺": diagnostic.PILOT_SHOP_NAME,
                "日期": (start + timedelta(days=offset)).isoformat(),
                "广告活动ID": CAMPAIGN_ID,
                "广告活动": "sample",
            }
            for offset in range(14)
        ]
        with mock.patch.object(diagnostic, "DEEP_REPORT_DIR", report_dir), mock.patch.object(
            diagnostic, "DEEP_REPORT_TYPES", {"campaigns": ("adCampaignReport", ("广告活动",))}
        ), mock.patch.object(self.service, "_read_report", return_value=(list(rows[0]), rows)):
            reports, sources = self.service._deep_reports(CAMPAIGN_ID)
            self.assertEqual(reports["campaigns"]["status"], "available")
            self.assertEqual(sources[0]["effective_date"], "2026-08-06..2026-08-19")

            foreign = [dict(row) for row in rows]
            foreign[0]["店铺"] = "OTHER"
            with mock.patch.object(self.service, "_read_report", return_value=(list(rows[0]), foreign)):
                reports, sources = self.service._deep_reports(CAMPAIGN_ID)
            self.assertEqual(reports["campaigns"]["status"], "error")
            self.assertEqual(sources[0]["error"], "REPORT_SCOPE_INVALID")

            stale = [dict(row) for row in rows[:-1]]
            with mock.patch.object(self.service, "_read_report", return_value=(list(rows[0]), stale)):
                reports, sources = self.service._deep_reports(CAMPAIGN_ID)
            self.assertEqual(reports["campaigns"]["status"], "error")
            self.assertEqual(sources[0]["error"], "REPORT_DATE_WINDOW_INVALID")


class SnapshotStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = diagnostic.SnapshotStore(self.root / "snapshots")
        self.catalog = {
            "meta": {"shop_id": diagnostic.PILOT_SHOP_ID},
            "campaigns": [{"campaignId": CAMPAIGN_ID, "name": "snapshot"}],
        }
        self.detail = {
            "meta": {"shop_id": diagnostic.PILOT_SHOP_ID},
            "campaign": {"campaignId": CAMPAIGN_ID, "name": "snapshot"},
            "structure": {
                "ad_products": [{"campaignId": CAMPAIGN_ID, "sku": SKU}],
                "keywords": [{"keywordId": KEYWORD_ID}],
            },
            "performance": {
                "today": {"campaign": {}, "ad_groups": {}},
                "mature_14d": {
                    "deep_reports": {
                        "placements": {"status": "available", "report_type": "adSpaceReport"},
                        "business_placements": {"status": "available", "report_type": "amazonBusinessReport"},
                        "search_terms": {"status": "available"},
                        "targets": {"status": "available"},
                    }
                },
            },
            "sources": [],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_published_snapshot_is_atomic_compact_and_api_free(self):
        manifest = self.store.publish(
            self.catalog, {CAMPAIGN_ID: self.detail}, NOW, retention=2
        )

        def forbidden_client():
            raise AssertionError("snapshot hit reached Sellfox API")

        service = diagnostic.DiagnosticService(
            client_factory=forbidden_client,
            mature_payload_path=self.root / "unused.json",
            clock=lambda: NOW,
            snapshot_dir=self.store.root,
        )
        catalog = service.campaigns()
        overview = service.campaign_detail(CAMPAIGN_ID, section="overview")
        full = service.campaign_detail(CAMPAIGN_ID)

        self.assertEqual(manifest["campaign_count"], 1)
        self.assertEqual(catalog["meta"]["cache_status"], "persistent_snapshot")
        self.assertEqual(overview["meta"]["cache_status"], "persistent_snapshot")
        self.assertEqual(set(overview["structure"]), {"ad_products"})
        self.assertNotIn("ad_groups", overview["performance"]["today"])
        self.assertEqual(
            set(overview["performance"]["mature_14d"]["deep_reports"]),
            {"placements", "search_terms"},
        )
        self.assertIn("keywords", full["structure"])

    def test_missing_overview_snapshot_fetches_overview_before_full_detail(self):
        service = diagnostic.DiagnosticService(
            client_factory=lambda: (_ for _ in ()).throw(
                AssertionError("patched detail loader should be used")
            ),
            mature_payload_path=self.root / "unused.json",
            clock=lambda: NOW,
            snapshot_dir=self.store.root,
        )
        overview_payload = diagnostic.compact_overview_snapshot(self.detail)
        calls = []

        def fetch_detail(campaign_id, *, section="full"):
            calls.append((campaign_id, section))
            return overview_payload if section == "overview" else self.detail

        with mock.patch.object(
            service, "_fetch_campaign_detail", side_effect=fetch_detail
        ):
            overview = service.campaign_detail(CAMPAIGN_ID, section="overview")

        self.assertEqual(calls, [(CAMPAIGN_ID, "overview")])
        self.assertEqual(overview["meta"]["kind"], "campaign_detail_overview")
        self.assertIsNotNone(self.store.read("overview", CAMPAIGN_ID))
        self.assertIsNone(self.store.read("full", CAMPAIGN_ID))
        saved = self.store.read("overview", CAMPAIGN_ID)
        self.assertFalse(saved.value["meta"]["snapshot_compacted_from_full"])

    def test_stale_overview_and_full_share_one_background_refresh(self):
        self.store.publish(
            self.catalog,
            {CAMPAIGN_ID: self.detail},
            NOW - timedelta(hours=2),
        )
        clients: list[FakeClient] = []

        def factory():
            client = FakeClient()
            clients.append(client)
            return client

        mature = self.root / "ads-monitor.json"
        mature.write_text(json.dumps(mature_payload()), encoding="utf-8")
        service = diagnostic.DiagnosticService(
            client_factory=factory,
            mature_payload_path=mature,
            clock=lambda: NOW,
            snapshot_dir=self.store.root,
            snapshot_ttl=60,
        )
        with mock.patch.object(diagnostic, "DEEP_REPORT_DIR", self.root / "missing"):
            overview = service.campaign_detail(
                CAMPAIGN_ID, refresh=True, section="overview"
            )
            full = service.campaign_detail(CAMPAIGN_ID, refresh=True)
            for _ in range(200):
                if not service.health()["snapshot"]["background_refreshes"]:
                    break
                time.sleep(0.01)

        self.assertEqual(overview["meta"]["cache_status"], "stale_snapshot")
        self.assertTrue(overview["meta"]["refresh_pending"])
        self.assertIn(full["meta"]["cache_status"], {"persistent_snapshot", "stale_snapshot"})
        self.assertEqual(len(clients), 1)
        refreshed = self.store.read("full", CAMPAIGN_ID)
        self.assertEqual(refreshed.value["campaign"]["campaignId"], CAMPAIGN_ID)
        self.assertEqual(refreshed.generated_at, NOW - timedelta(hours=2))


class StubService:
    def health(self):
        return {"status": "ok", "read_only": True}

    def campaigns(self, refresh=False):
        return {"campaigns": [], "refresh": refresh}

    def campaign_detail(self, campaign_id, refresh=False, section="full"):
        if campaign_id == "404":
            raise diagnostic.NotFound()
        return {"campaign_id": campaign_id, "refresh": refresh, "section": section}

    def search_term_page(self, campaign_id, kind, page=1, page_size=10):
        return {
            "campaign_id": campaign_id,
            "kind": kind,
            "page": page,
            "page_size": page_size,
            "rows": [],
        }


class LeakingStub(StubService):
    def campaigns(self, refresh=False):
        raise RuntimeError("client_secret=TOPSECRET")


class StubControlService:
    def __init__(self):
        self.previews = []
        self.executions = []

    def capabilities(self, refresh=False):
        return {"status": "ok", "mcp_status": "available", "refresh": refresh, "operations": []}

    def preview(self, payload, *, context=None):
        self.previews.append((payload, context))
        return {"plan_id": "SPC-1234567890abcdef1234", "confirmation": f"确认执行 {payload['campaign_id']}"}

    def execute(self, payload):
        self.executions.append(payload)
        return {"status": "succeeded", "plan_id": payload["plan_id"]}


class HttpHandlerTests(unittest.TestCase):
    def _request(self, service, method, path, *, headers=None, body=None, control_service=None, control_token="", services=None, control_services=None):
        server = diagnostic.LocalDiagnosticServer(
            (diagnostic.HOST, 0), diagnostic.make_handler(
                service,
                control_service,
                control_token,
                services=services,
                control_services=control_services,
            )
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection(
                diagnostic.HOST, server.server_address[1], timeout=5
            )
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            raw = response.read()
            payload = json.loads(raw.decode("utf-8")) if raw else None
            return response.status, dict(response.getheaders()), payload, raw
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_health_route_and_allowed_cors(self):
        status, headers, payload, _ = self._request(
            StubService(),
            "GET",
            "/api/diagnostic/health",
            headers={"Origin": "http://127.0.0.1:4173"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["read_only"])
        self.assertEqual(headers["Access-Control-Allow-Origin"], "http://127.0.0.1:4173")
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_post_is_405_and_foreign_shop_is_403(self):
        status, _, payload, _ = self._request(
            StubService(), "POST", "/api/diagnostic/campaigns"
        )
        self.assertEqual(status, 405)
        self.assertEqual(payload["error"]["code"], "METHOD_NOT_ALLOWED")
        status, _, payload, _ = self._request(
            StubService(), "GET", "/api/diagnostic/campaigns?shop_id=999"
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "FORBIDDEN")

    def test_routes_each_enabled_shop_to_its_own_service(self):
        class ShopStub(StubService):
            def __init__(self, shop):
                self.shop = shop

            def campaigns(self, refresh=False):
                return {"shop": {"shop_id": self.shop.shop_id}, "campaigns": []}

        primary = ShopStub(diagnostic.DIAGNOSTIC_SHOPS[diagnostic.PILOT_SHOP_ID])
        secondary = ShopStub(diagnostic.DIAGNOSTIC_SHOPS[diagnostic.SECONDARY_SHOP_ID])
        status, _, payload, _ = self._request(
            primary,
            "GET",
            f"/api/diagnostic/campaigns?shop_id={diagnostic.SECONDARY_SHOP_ID}",
            services={primary.shop.shop_id: primary, secondary.shop.shop_id: secondary},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["shop"]["shop_id"], diagnostic.SECONDARY_SHOP_ID)

    def test_shops_route_lists_every_enabled_shop(self):
        class ShopStub(StubService):
            def __init__(self, shop):
                self.shop = shop

        primary = ShopStub(diagnostic.DIAGNOSTIC_SHOPS[diagnostic.PILOT_SHOP_ID])
        secondary = ShopStub(diagnostic.DIAGNOSTIC_SHOPS[diagnostic.SECONDARY_SHOP_ID])
        status, _, payload, _ = self._request(
            primary,
            "GET",
            "/api/diagnostic/shops",
            services={primary.shop.shop_id: primary, secondary.shop.shop_id: secondary},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["default_shop_id"], diagnostic.PILOT_SHOP_ID)
        self.assertEqual(payload["refresh_interval_minutes"], 60)
        self.assertEqual(
            {shop["id"] for shop in payload["shops"]},
            {diagnostic.PILOT_SHOP_ID, diagnostic.SECONDARY_SHOP_ID},
        )

    def test_detail_404_and_disallowed_origin(self):
        status, _, payload, _ = self._request(
            StubService(), "GET", "/api/diagnostic/campaigns/404"
        )
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "NOT_FOUND")
        status, _, payload, _ = self._request(
            StubService(),
            "GET",
            "/api/diagnostic/health",
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "FORBIDDEN")

    def test_unexpected_error_does_not_leak_secret(self):
        status, _, payload, raw = self._request(
            LeakingStub(), "GET", "/api/diagnostic/campaigns"
        )
        self.assertEqual(status, 500)
        self.assertEqual(payload["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn(b"TOPSECRET", raw)
        self.assertNotIn(b"client_secret", raw)

    def test_options_allows_control_post(self):
        status, headers, _, _ = self._request(
            StubService(),
            "OPTIONS",
            "/api/diagnostic/campaigns",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Methods"], "GET, POST, OPTIONS")
        self.assertIn("X-SP-Control-Token", headers["Access-Control-Allow-Headers"])

    def test_sp_control_capabilities_preview_and_execute(self):
        control = StubControlService()
        token = "local-control-token"
        status, _, payload, _ = self._request(
            StubService(),
            "GET",
            f"/api/diagnostic/sp-controls/capabilities?campaign_id={CAMPAIGN_ID}",
            control_service=control,
            control_token=token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["control_token"], token)

        headers = {
            "Origin": "http://127.0.0.1:4173",
            "Content-Type": "application/json",
            "X-SP-Control-Token": token,
        }
        preview_body = json.dumps({"operation": "campaign_budget", "campaign_id": CAMPAIGN_ID, "values": {"budget": 65}})
        status, _, payload, _ = self._request(
            StubService(),
            "POST",
            "/api/diagnostic/sp-controls/preview",
            headers=headers,
            body=preview_body,
            control_service=control,
            control_token=token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["confirmation"], f"确认执行 {CAMPAIGN_ID}")
        self.assertEqual(control.previews[0][1]["campaign_id"], CAMPAIGN_ID)

        execute_body = json.dumps({"plan_id": payload["plan_id"], "confirmation": payload["confirmation"]})
        status, _, payload, _ = self._request(
            StubService(),
            "POST",
            "/api/diagnostic/sp-controls/execute",
            headers=headers,
            body=execute_body,
            control_service=control,
            control_token=token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "succeeded")

    def test_sp_control_rejects_invalid_token(self):
        body = json.dumps({"operation": "campaign_budget", "campaign_id": CAMPAIGN_ID, "values": {"budget": 65}})
        status, _, payload, _ = self._request(
            StubService(),
            "POST",
            "/api/diagnostic/sp-controls/preview",
            headers={"Origin": "http://localhost:4173", "Content-Type": "application/json", "X-SP-Control-Token": "wrong"},
            body=body,
            control_service=StubControlService(),
            control_token="right",
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "CONTROL_TOKEN_INVALID")

    def test_compatibility_route_returns_list_and_selected_detail(self):
        status, _, payload, _ = self._request(
            StubService(),
            "GET",
            f"/api/diagnostic?shop_id={diagnostic.PILOT_SHOP_ID}&campaign_id={CAMPAIGN_ID}",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["campaign_id"], CAMPAIGN_ID)
        self.assertEqual(payload["campaigns"], [])

    def test_overview_and_search_term_paging_routes(self):
        status, _, payload, _ = self._request(
            StubService(),
            "GET",
            f"/api/diagnostic?campaign_id={CAMPAIGN_ID}&section=overview",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["section"], "overview")
        self.assertNotIn("campaigns", payload)

        status, _, payload, _ = self._request(
            StubService(),
            "GET",
            f"/api/diagnostic/search-terms?campaign_id={CAMPAIGN_ID}&kind=waste&page=2&page_size=10",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["kind"], "waste")
        self.assertEqual(payload["page"], 2)


if __name__ == "__main__":
    unittest.main()
