import unittest
from pathlib import Path


class TkPartialDashboardSalesSourceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.backend = (self.root / "tk_total_dashboard.py").read_text(encoding="utf-8")
        self.template = (self.root / "templates" / "tk_total_dashboard.html").read_text(encoding="utf-8")

    def test_partial_dashboard_uses_bd_order_settlement_gmv(self):
        self.assertIn("FROM v_tk_bddingdan WITH (NOLOCK)", self.backend)
        self.assertIn("DingDanYingJieSuanGMV", self.backend)
        self.assertIn("sales_source=PARTIAL_DASHBOARD_SALES_SOURCE", self.backend)

    def test_partial_dashboard_does_not_reuse_default_sales_cache(self):
        self.assertIn("precomputed_shop_payloads={}", self.backend)
        self.assertIn("precomputed_week_shop_payloads={}", self.backend)
        self.assertIn("sales_source: RESTRICT_LIKE_82 ? 'bd_order_settlement_gmv' : ''", self.template)

    def test_every_partial_dashboard_metric_has_hover_calculation(self):
        metric_ids = {
            "breakEvenRevenue", "orderCount", "profitTargetRevenue", "monthlySalesPrev",
            "netProfit", "grossProfit", "influencerCommission",
            "influencerCommissionCreator", "influencerCommissionPartner",
            "influencerCommissionAdOrder", "influencerCommissionChannel",
            "influencerCount", "influencerVideoFee", "influencerVideoFeeShuaDan",
            "influencerVideoFeeShouHou", "influencerVideoFeeKengWei",
            "influencerVideoFeeBuyProduct", "influencerVideoFeeGift", "videoCount",
            "activityServiceFee", "adFee", "platformCommission", "vatFee",
            "adjustmentFee", "otherPlatformFee", "opMgmtQD", "opMgmtSZ",
            "prodCost", "prodCostPlatform", "prodCostSample", "prodCostSelfSample",
            "prodCostAfterSales", "touChengCost", "weiChengCost", "storageReturnCost",
            "storageReturnInbound", "storageReturnStorage", "storageReturnReturn",
            "qdWage", "szWage", "qdRent", "szRent",
        }
        for metric_id in metric_ids:
            with self.subTest(metric_id=metric_id):
                self.assertIn(f"'{metric_id}':", self.template)
        self.assertIn("attachPartialCalculationTooltips();", self.template)
        self.assertIn("className = 'calculation-tooltip'", self.template)


if __name__ == "__main__":
    unittest.main()
