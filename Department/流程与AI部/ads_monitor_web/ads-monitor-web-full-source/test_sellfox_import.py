import unittest
import logging
from datetime import date, datetime
from decimal import Decimal

from sellfox_import import (
    DB_COLUMNS,
    REQUEST_PLATFORM_IDS,
    RunStats,
    SellfoxClient,
    UK_TO_USD_FACTOR,
    allocate_total,
    classify_order_source,
    map_order,
    normalize_store,
    parse_datetime,
)


class MappingTests(unittest.TestCase):
    def test_store_mapping_matches_vba_rules(self):
        self.assertEqual(normalize_store("TK83-UK"), 80)
        self.assertEqual(normalize_store("TK86-UK"), 86)
        self.assertEqual(normalize_store("TK85"), 85)
        self.assertEqual(normalize_store("okaylove"), 202)
        self.assertEqual(normalize_store("Geeneiya"), 201)

    def test_single_uk_order_matches_vba_currency_factor(self):
        order = {
            "shopName": "TK86-UK",
            "marketplaceName": "英国",
            "orderNo": "576928757726157480",
            "shipNodeType": "WFSFulfilled",
            "purchaseDate": "2026-07-27 01:53:10",
            "payTime": "2026-07-27 01:53:13",
            "orderStatus": "待发货",
            "settlementStatus": "0",
            "totalAmount": "25.98",
            "productAmount": "36.99",
            "discountAmount": "-15",
            "sellerProductDiscount": "-15",
            "shippingChargeAmount": "3.99",
            "taxAmount": "4.34",
            "salesCommission": "-2.08",
            "purchaseCost": "-4.09",
            "headTripPrice": "-0.55",
            "orderProfit": "23.60",
            "orderProfitRate": "107.32",
            "skuInfoVo": [
                {
                    "productId": "1729852727862598129",
                    "msku": "86-18A-UK",
                    "localSku": "86-18A-UK",
                    "saleNum": "1",
                    "originalPrice": "36.99",
                    "carrier": "Royal Mail UK",
                }
            ],
        }
        row = map_order(order, datetime(2026, 7, 27, 9, 0))[0]
        self.assertEqual(row["DanHao"], "576928757726157480")
        self.assertAlmostEqual(
            row["ChanPinJinE"],
            float(Decimal("36.99") * UK_TO_USD_FACTOR),
        )
        self.assertAlmostEqual(
            row["DingDanLiRun"],
            float(Decimal("23.60") * UK_TO_USD_FACTOR),
        )
        self.assertAlmostEqual(row["DingDanLiRunLv"], 1.0732, places=4)

    def test_multi_item_allocation_preserves_totals(self):
        order = {
            "shopName": "TK85",
            "marketplaceName": "美国",
            "orderNo": "577495837582201567",
            "purchaseDate": "2026-07-26 19:01:58",
            "payTime": "2026-07-26 19:02:02",
            "orderStatus": "待发货",
            "settlementStatus": "0",
            "productAmount": "90.00",
            "totalAmount": "57.42",
            "discountAmount": "-48.03",
            "sellerProductDiscount": "-48.03",
            "shippingChargeAmount": "11.37",
            "taxAmount": "4.08",
            "salesCommission": "-4.59",
            "purchaseCost": "-5.13",
            "headTripPrice": "-3.12",
            "orderProfit": "44.58",
            "skuInfoVo": [
                {"productId": "1", "localSku": "A", "originalPrice": "30"},
                {"productId": "2", "localSku": "B", "originalPrice": "30"},
                {"productId": "3", "localSku": "C", "originalPrice": "30"},
            ],
        }
        rows = map_order(order, datetime(2026, 7, 27, 9, 0))
        self.assertEqual(len(rows), 3)
        self.assertAlmostEqual(sum(row["XiaoShouShouYi"] for row in rows), 57.42)
        self.assertAlmostEqual(sum(row["DingDanLiRun"] for row in rows), 44.58)
        self.assertTrue(all("按商品金额比例分摊" in row["BeiZhu"] for row in rows))
        self.assertTrue(all(set(DB_COLUMNS) >= set(row) for row in rows))

    def test_allocation_keeps_exact_residual(self):
        values = allocate_total(
            Decimal("1.00"),
            [Decimal("1"), Decimal("1"), Decimal("1")],
        )
        self.assertEqual(sum(values), Decimal("1.00"))
        self.assertEqual(values, [Decimal("0.33"), Decimal("0.33"), Decimal("0.34")])

    def test_api_iso_minute_datetime(self):
        self.assertEqual(
            parse_datetime("2026-07-26T18:54", strict=True),
            datetime(2026, 7, 26, 18, 54),
        )

    def test_tiktok_and_custom_shop_scope(self):
        self.assertEqual(
            classify_order_source(
                {"platformType": "6", "platformName": "TikTok"}
            ),
            "TikTok",
        )
        self.assertEqual(
            classify_order_source(
                {
                    "platformType": "3",
                    "shopId": "483494",
                    "shopName": "okaylove",
                }
            ),
            "自定义",
        )
        self.assertEqual(
            classify_order_source(
                {
                    "platformType": 3,
                    "shopId": 553350,
                    "shopName": "Geeneiya",
                }
            ),
            "自定义",
        )
        self.assertIsNone(
            classify_order_source(
                {
                    "platformType": "3",
                    "shopId": "999999",
                    "shopName": "unrelated-shopify-store",
                }
            )
        )

    def test_fetch_requests_both_platforms_and_filters_shopify(self):
        class FakeClient:
            def __init__(self):
                self.logger = logging.getLogger("test-fetch")
                self.bodies = []

            def post_orders(self, body):
                self.bodies.append(body)
                return {
                    "rows": [
                        {
                            "orderNo": "T1",
                            "platformType": "6",
                            "platformName": "TikTok",
                            "updateTime": "2026-07-28 09:00:00",
                        },
                        {
                            "orderNo": "C1",
                            "platformType": "3",
                            "shopId": "483494",
                            "shopName": "okaylove",
                            "updateTime": "2026-07-28 09:00:00",
                        },
                        {
                            "orderNo": "S1",
                            "platformType": "3",
                            "shopId": "999999",
                            "shopName": "other-shopify",
                            "updateTime": "2026-07-28 09:00:00",
                        },
                    ],
                    "totalPage": 1,
                }

        client = FakeClient()
        stats = RunStats()
        orders = SellfoxClient.fetch_orders(
            client,
            start_date=date(2026, 7, 22),
            end_date=date(2026, 7, 28),
            date_type="purchase",
            page_size=1000,
            max_orders=None,
            stats=stats,
        )

        self.assertEqual(client.bodies[0]["platformIdList"], list(REQUEST_PLATFORM_IDS))
        self.assertEqual(client.bodies[0]["dateType"], "purchase")
        self.assertEqual({order["orderNo"] for order in orders}, {"T1", "C1"})
        self.assertEqual(stats.tiktok_orders, 1)
        self.assertEqual(stats.custom_orders, 1)
        self.assertEqual(stats.out_of_scope_orders_dropped, 1)


if __name__ == "__main__":
    unittest.main()
