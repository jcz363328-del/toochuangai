from __future__ import annotations

import unittest

from sellfox_ad_diagnostic_refresh import (
    is_monitor_busy_error,
    select_diagnostic_shops,
    select_overview_campaign_id,
    select_rotating_shops,
)
from sellfox_ad_diagnostic_server import DiagnosticShop
from sellfox_ads_monitor import MonitorFailure


class ShopSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shops = {
            "1": DiagnosticShop("1", "一号店"),
            "2": DiagnosticShop("2", "二号店"),
            "3": DiagnosticShop("3", "三号店"),
        }

    def test_empty_selection_refreshes_all_discovered_shops(self):
        selected = select_diagnostic_shops(self.shops, [])
        self.assertEqual([shop.shop_id for shop in selected], ["1", "2", "3"])

    def test_monitor_busy_is_an_expected_hourly_skip(self):
        self.assertTrue(
            is_monitor_busy_error(
                MonitorFailure("已有广告监控任务正在运行，本次安全退出。")
            )
        )
        self.assertFalse(is_monitor_busy_error(MonitorFailure("其他错误")))

    def test_explicit_selection_is_validated(self):
        self.assertEqual(
            [shop.shop_id for shop in select_diagnostic_shops(self.shops, ["2"])],
            ["2"],
        )
        with self.assertRaisesRegex(ValueError, "不在已授权清单"):
            select_diagnostic_shops(self.shops, ["9"])
        with self.assertRaisesRegex(ValueError, "重复"):
            select_diagnostic_shops(self.shops, ["2", "2"])

    def test_deep_refresh_rotates_oldest_shops(self):
        selected = select_rotating_shops(
            list(self.shops.values()),
            {"1": "2026-08-28T03:00:00+00:00", "2": "2026-08-28T01:00:00+00:00"},
            2,
        )
        self.assertEqual([shop.shop_id for shop in selected], ["3", "2"])

    def test_overview_campaign_matches_default_frontend_priority(self):
        catalog = {
            "campaigns": [
                {"campaignId": "101", "name": "0k-清仓广告", "actionable_count": 0},
                {"campaignId": "280", "name": "01R-christmas lashes-广泛", "actionable_count": 0},
                {"campaignId": "300", "name": "z-low", "actionable_count": 1},
            ]
        }
        self.assertEqual(select_overview_campaign_id(catalog), "300")
        catalog["campaigns"][2]["actionable_count"] = 0
        self.assertEqual(select_overview_campaign_id(catalog), "280")

    def test_overview_campaign_prefers_pilot_campaign(self):
        catalog = {
            "campaigns": [
                {"campaignId": "300", "name": "actionable", "actionable_count": 1},
                {"campaignId": "70540977760495", "name": "pilot", "actionable_count": 0},
            ]
        }
        self.assertEqual(
            select_overview_campaign_id(catalog),
            "70540977760495",
        )

    def test_overview_campaign_prefers_secondary_shop_campaign(self):
        catalog = {
            "shop": {"shop_id": "476221"},
            "campaigns": [
                {"campaignId": "300", "name": "actionable", "state": "enabled", "actionable_count": 1},
                {"campaignId": "390041487563225", "name": "23-default", "state": "enabled"},
            ],
        }
        self.assertEqual(select_overview_campaign_id(catalog), "390041487563225")

    def test_overview_campaign_prefers_enabled_over_archived(self):
        catalog = {
            "campaigns": [
                {"campaignId": "100", "name": "archived", "state": "archived", "mature_14d": {"spend": 999}},
                {"campaignId": "200", "name": "enabled", "state": "enabled", "mature_14d": {"spend": 1}},
            ]
        }
        self.assertEqual(select_overview_campaign_id(catalog), "200")


if __name__ == "__main__":
    unittest.main()
