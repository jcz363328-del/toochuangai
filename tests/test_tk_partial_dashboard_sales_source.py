import unittest
from pathlib import Path


class TkPartialDashboardSalesSourceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.backend = (self.root / "tk_total_dashboard.py").read_text(encoding="utf-8")
        self.template = (self.root / "templates" / "tk_total_dashboard.html").read_text(encoding="utf-8")

    def test_partial_dashboard_uses_bd_order_settlement_gmv(self):
        self.assertIn("FROM TK_DingDan AS dd WITH (NOLOCK)", self.backend)
        self.assertIn("FROM TK_BDDingDan AS bd WITH (NOLOCK)", self.backend)
        self.assertIn("DingDanYingJieSuanGMV", self.backend)
        self.assertIn("sales_source=PARTIAL_DASHBOARD_SALES_SOURCE", self.backend)

    def test_partial_dashboard_refreshes_daily_at_0930(self):
        self.assertIn("PARTIAL_CACHE_REFRESH_HOUR = 9", self.backend)
        self.assertIn("PARTIAL_CACHE_REFRESH_MINUTE = 30", self.backend)
        self.assertIn("time.sleep(_seconds_until_next_partial_cache_refresh())", self.backend)

    def test_partial_dashboard_uses_its_own_persistent_precomputed_cache(self):
        self.assertIn("precomputed_shop_payloads=_partial_precomputed_shop_payloads", self.backend)
        self.assertIn("precomputed_week_shop_payloads=_partial_precomputed_week_shop_payloads", self.backend)
        self.assertIn("partial-dashboard:month:86", self.backend)
        self.assertIn("dbo.TK_KanBan_HuanCun", self.backend)
        self.assertIn("sales_source: RESTRICT_LIKE_82 ? 'bd_order_settlement_gmv' : ''", self.template)

    def test_every_tk_dashboard_metric_has_hover_calculation(self):
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
        self.assertIn("const SALES_CALCULATION = RESTRICT_LIKE_82", self.template)
        self.assertIn("attachCalculationTooltips();", self.template)
        self.assertNotIn("if (!RESTRICT_LIKE_82 || document.getElementById('calculationTooltip'))", self.template)
        self.assertIn("row.querySelectorAll('td').forEach", self.template)
        self.assertIn("className = 'calculation-tooltip'", self.template)

    def test_every_tk_dashboard_summary_and_chart_has_hover_calculation(self):
        visible_data_ids = {
            "salesHeader", "salesValue", "progressHeader", "progressBar",
            "progressText", "progressFooter", "salesProgressHeader",
            "salesProgressBar", "salesProgressText", "salesProgressDetail",
            "influencerProgressHeader", "influencerProgressBar",
            "influencerProgressText", "influencerProgressDetail",
            "videoProgressHeader", "videoProgressBar", "videoProgressText",
            "videoProgressDetail", "chartPeriodLabel", "periodMonth",
            "chartActualSales", "chartGrossProfit", "chartNetProfit",
            "businessTrendChart", "costCompositionChart", "achRatioChart",
        }
        for element_id in visible_data_ids:
            with self.subTest(element_id=element_id):
                self.assertIn(f"['{element_id}',", self.template)
        self.assertIn("'.ratio-header'", self.template)
        self.assertIn("'.target-header'", self.template)
        self.assertIn("'.achieved-header'", self.template)
        self.assertIn("'.achratio-header'", self.template)

    def test_dashboard_has_force_refresh_cache_button(self):
        self.assertIn('id="refreshCacheBtn"', self.template)
        self.assertIn('onclick="refreshDashboardCache()"', self.template)
        self.assertIn('async function queryMetrics(forceRefresh = false)', self.template)
        self.assertIn('force_refresh: forceRefresh', self.template)
        self.assertIn("force_refresh = data.get('force_refresh') is True", self.backend)
        self.assertIn('if not force_refresh and cached', self.backend)
        self.assertIn('force_refresh=force_refresh', self.backend)
        self.assertIn('def _promote_manual_refresh_to_standard_cache', self.backend)


if __name__ == "__main__":
    unittest.main()
