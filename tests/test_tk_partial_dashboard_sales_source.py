import unittest
from pathlib import Path


class TkPartialDashboardSalesSourceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.backend = (self.root / "tk_total_dashboard.py").read_text(encoding="utf-8")
        self.template = (self.root / "templates" / "tk_total_dashboard.html").read_text(encoding="utf-8")

    def test_partial_dashboard_uses_tk_dingdan_gmv(self):
        sales_query = self.backend.split(
            "def _get_tk_order_gmv_sales(", 1
        )[1].split("def _fetch_dashboard_metrics_fast(", 1)[0]
        self.assertIn("FROM TK_DingDan AS dd WITH (NOLOCK)", sales_query)
        self.assertIn("AND dd.Dian IN ({in_clause})", sales_query)
        self.assertIn(
            "AND dd.ZhuangTai IN (N'已发货', N'已完成')",
            sales_query,
        )
        self.assertNotIn("AND dd.ZhuangTai <> N'已取消'", sales_query)
        self.assertIn(
            "THEN dd.ChanPinJinE + dd.MaiJiaShangPinZheKou + dd.TuiKuan",
            sales_query,
        )
        self.assertIn(
            "ELSE dd.XiaoShouShouYi - dd.ShuiFei - dd.PingTaiShangPinZheKou",
            sales_query,
        )
        self.assertNotIn("TK_BDDingDan", sales_query)
        self.assertNotIn("TK_TuiHuo", sales_query)
        self.assertNotIn("dd.Guo", sales_query)
        self.assertIn("sales_source=PARTIAL_DASHBOARD_SALES_SOURCE", self.backend)

    def test_partial_dashboard_refreshes_daily_at_0930(self):
        self.assertIn("PARTIAL_CACHE_REFRESH_HOUR = 9", self.backend)
        self.assertIn("PARTIAL_CACHE_REFRESH_MINUTE = 30", self.backend)
        self.assertIn("time.sleep(_seconds_until_next_partial_cache_refresh())", self.backend)

    def test_joint_dashboard_does_not_embed_shared_precomputed_shop_data(self):
        project_page = self.backend.split(
            "def tk_dashboard_project_page():", 1
        )[1].split("def tk_dashboard_sz_page():", 1)[0]
        self.assertIn("precomputed_shop_payloads={}", project_page)
        self.assertIn("precomputed_week_shop_payloads={}", project_page)
        self.assertNotIn("_partial_precomputed_shop_payloads", project_page)
        self.assertNotIn("_partial_precomputed_week_shop_payloads", project_page)
        self.assertIn("partial-dashboard:month:86", self.backend)
        self.assertIn("dbo.TK_KanBan_HuanCun", self.backend)
        self.assertIn("sales_source: RESTRICT_LIKE_82 ? 'tk_dingdan_gmv' : ''", self.template)

    def test_partial_dashboard_cold_query_refreshes_in_background(self):
        cache_block = self.backend.split(
            "def _get_cached_metrics_payload(", 1
        )[1].split("def _merge_numeric_dicts(", 1)[0]
        self.assertIn("refresh_in_background()", cache_block)
        self.assertNotIn("payload = compute_and_store()\n    return payload", cache_block)
        self.assertIn("sales_source=sales_source", cache_block)

    def test_joint_dashboard_cold_shell_immediately_queries_tk_dingdan_sales(self):
        shell_block = self.backend.split(
            "def _build_dashboard_shell_payload(", 1
        )[1].split("def _compute_metrics_payload(", 1)[0]
        self.assertIn("sales_source == PARTIAL_DASHBOARD_SALES_SOURCE", shell_block)
        self.assertIn("tk_order_sales = _get_tk_order_gmv_sales(", shell_block)
        self.assertIn("yesterday_sales = tk_order_sales['yesterday']", shell_block)
        self.assertIn("selected_sales = tk_order_sales['selected']", shell_block)

    def test_joint_dashboard_queries_after_authorized_shops_load(self):
        self.assertIn("window.addEventListener('DOMContentLoaded', async () =>", self.template)
        self.assertIn("await loadShops();", self.template)
        self.assertIn(
            "if (DEFAULT_SELECT_ALL && getSelectedShops().length > 0)",
            self.template,
        )

    def test_overall_and_joint_dashboards_default_to_all_available_shops(self):
        overall_page = self.backend.split(
            "def tk_dashboard_page():", 1
        )[1].split("def tk_dashboard_project_page():", 1)[0]
        project_page = self.backend.split(
            "def tk_dashboard_project_page():", 1
        )[1].split("def tk_dashboard_sz_page():", 1)[0]
        self.assertIn("default_select_all=True", overall_page)
        self.assertIn("default_select_all=True", project_page)
        self.assertEqual(self.backend.count("default_select_all=True"), 2)
        self.assertIn("page_payload = (_precomputed_shop_payloads or {}).get('ALL')", overall_page)
        self.assertIn("const DEFAULT_SELECT_ALL", self.template)
        self.assertIn("DEFAULT_SELECT_ALL ||", self.template)
        self.assertIn("selectAll.checked = DEFAULT_SELECT_ALL", self.template)
        self.assertIn("PRECOMPUTED_SHOP_PAYLOADS.ALL", self.template)

    def test_overall_and_joint_dashboards_use_distinct_sales_cards(self):
        overall_page = self.backend.split(
            "def tk_dashboard_page():", 1
        )[1].split("def tk_dashboard_project_page():", 1)[0]
        project_page = self.backend.split(
            "def tk_dashboard_project_page():", 1
        )[1].split("def tk_dashboard_sz_page():", 1)[0]
        self.assertIn("show_order_sales_card=True", overall_page)
        self.assertNotIn("show_order_sales_card=True", project_page)
        self.assertEqual(self.backend.count("show_order_sales_card=True"), 1)
        self.assertIn("昨日实时结算销售额（USD）", overall_page)
        self.assertIn("昨日订单实时销售额（USD）", self.template)
        self.assertIn("昨日订单实时结算销售额（USD）", self.template)
        self.assertIn("primary_sales_title='昨日实时结算销售额（USD）'", overall_page)
        self.assertIn("primary_sales_title='昨日订单实时销售额（USD）'", project_page)
        self.assertIn("const SETTLEMENT_SALES_CALCULATION", self.template)
        self.assertIn("const ORDER_SALES_CALCULATION", self.template)

    def test_overall_order_sales_card_uses_dedicated_tk_dingdan_endpoint(self):
        endpoint = self.backend.split(
            "def tk_yesterday_order_sales():", 1
        )[1].split("def tk_metrics():", 1)[0]
        self.assertIn("_get_tk_order_gmv_sales(", endpoint)
        self.assertIn("'total_order_sales': order_sales['yesterday']", endpoint)
        self.assertIn("'previous_order_sales': order_sales['previous']", endpoint)
        self.assertIn("'selected_order_sales': order_sales['selected']", endpoint)
        self.assertIn("fetch('/tk/yesterday_order_sales'", self.template)
        self.assertIn("data.total_order_sales", self.template)
        self.assertIn("data.previous_order_sales", self.template)
        self.assertIn("data.selected_order_sales", self.template)

    def test_overall_order_dimension_sales_row_is_display_only(self):
        order_row = self.template.split(
            '<td>订单维度销售额</td>', 1
        )[1].split('<td>销售额</td>', 1)[0]
        self.assertIn('id="orderDimensionSales"', order_row)
        self.assertIn('id="orderDimensionSalesActual"', order_row)
        self.assertIn('id="orderDimensionSalesRatio">—</td>', order_row)
        self.assertIn('id="orderDimensionSalesTarget">—</td>', order_row)
        self.assertIn('id="orderDimensionSalesAchRatio">—</td>', order_row)
        self.assertIn("仅作独立展示，不参与占比、目标、毛利润、净利润或其他指标计算", self.template)
        self.assertIn("{% if show_order_sales_card|default(false) %}", self.template)

    def test_every_tk_dashboard_metric_has_hover_calculation(self):
        metric_ids = {
            "breakEvenRevenue", "orderCount", "profitTargetRevenue",
            "orderDimensionSales", "monthlySalesPrev",
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
            "salesHeader", "salesValue", "orderSalesHeader", "orderSalesValue",
            "progressHeader", "progressBar",
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

    def test_statistics_table_header_is_visible_on_joint_dashboard(self):
        statistics_block = self.template.split(
            '<div class="module-label period">统计期</div>', 1
        )[1].split('<div class="module-label business">经营成果</div>', 1)[0]
        self.assertIn('<td class="value col-value" id="periodMonth"></td>', statistics_block)
        self.assertIn('class="col-ratio ratio-header">上个月占比</td>', statistics_block)
        self.assertIn('class="col-target target-header">本月目标</td>', statistics_block)
        self.assertIn('class="col-achieved achieved-header">实际达成</td>', statistics_block)
        self.assertNotIn('style="display:none;"', statistics_block)

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
