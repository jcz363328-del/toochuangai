import unittest
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BusinessAnalysisIntegrationTests(unittest.TestCase):
    def test_main_dashboard_has_business_analysis_card(self):
        page = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
        ai_page = (ROOT / "templates" / "ai_modules.html").read_text(encoding="utf-8")

        self.assertIn("<h3>经营分析</h3>", page)
        self.assertIn("url_for('business_analysis')", page)
        self.assertNotIn("<h3>经营分析</h3>", ai_page)

    def test_flask_bundle_and_protected_routes_are_wired(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        package = (ROOT / "business_analysis" / "package.json").read_text(encoding="utf-8")
        flask_entry = (ROOT / "business_analysis" / "flask" / "index.html").read_text(encoding="utf-8")

        self.assertIn("@app.route('/ai/business-analysis')", app_source)
        self.assertIn("@app.route('/ai/business-analysis/assets/<path:filename>')", app_source)
        self.assertIn("@app.route('/api/ai/business-analysis/dashboard')", app_source)
        self.assertIn("@app.route('/api/ai/business-analysis/scope')", app_source)
        self.assertIn("'/api/ai/business-analysis/fiscal-overview'", app_source)
        self.assertIn("@app.route('/api/ai/business-analysis/key-tasks'", app_source)
        self.assertGreaterEqual(app_source.count("@_require_business_analysis_access"), 4)
        self.assertIn("force_business_analysis_query_params", app_source)
        self.assertIn("prepare_business_analysis_payload", app_source)
        self.assertIn("X-Business-Analysis-Source", app_source)
        self.assertIn("_BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH", app_source)
        self.assertIn("'daily-snapshot'", app_source)
        self.assertIn("'business_owner':", app_source)
        self.assertIn('"build:flask"', package)
        self.assertIn('data-dashboard-api="/api/ai/business-analysis/dashboard"', flask_entry)
        self.assertIn('data-scope-api="/api/ai/business-analysis/scope"', flask_entry)
        self.assertIn('data-key-tasks-api="/api/ai/business-analysis/key-tasks"', flask_entry)

        flask_main = (ROOT / "business_analysis" / "flask" / "main.tsx").read_text(encoding="utf-8")
        self.assertIn("emptyWorkbookData", flask_main)
        self.assertNotIn("workbook-data.json", flask_main)

    def test_daily_dashboard_snapshot_caches_current_and_previous_month(self):
        refresh_script = (
            ROOT / "business_analysis" / "scripts" / "refresh-dashboard-snapshot.mjs"
        ).read_text(encoding="utf-8")

        self.assertIn("const cachedPeriods = [period, previousPeriod];", refresh_script)
        self.assertIn("schemaVersion: 2", refresh_script)
        self.assertIn("periods[selectedPeriod]", refresh_script)

    def test_key_tasks_use_json_without_node_date(self):
        dashboard = (ROOT / "business_analysis" / "app" / "components" / "KeyTasksBoard.tsx").read_text(
            encoding="utf-8"
        )
        storage = json.loads(
            (ROOT / "business_analysis" / "data" / "key-tasks.json").read_text(encoding="utf-8")
        )

        self.assertIn("风险或阻塞 <small>选填</small>", dashboard)
        self.assertNotIn("节点日期", dashboard)
        self.assertEqual(storage, {"version": 1, "updatedAt": None, "tasks": []})

    def test_key_task_matrix_avoids_nested_desktop_scrollbars(self):
        dashboard = (ROOT / "business_analysis" / "app" / "components" / "KeyTasksBoard.tsx").read_text(
            encoding="utf-8"
        )
        styles = (ROOT / "business_analysis" / "app" / "globals.css").read_text(encoding="utf-8")

        self.assertIn("150px repeat(${data.meta.projects.length}, minmax(0, 1fr))", dashboard)
        self.assertIn("overflow: clip;", styles)
        self.assertNotIn("max-height: min(66vh, 760px);", styles)
        self.assertNotIn("min-width: 1436px;", styles)
        self.assertIn(".key-task-matrix { min-width: 1080px; }", styles)

    def test_fiscal_home_prioritizes_annual_goal_and_progress_comparison(self):
        overview = (
            ROOT / "business_analysis" / "app" / "components" / "FiscalOverview.tsx"
        ).read_text(encoding="utf-8")

        self.assertNotIn("整体达成率", overview)
        self.assertIn('className="fiscal-kpi fiscal-kpi-main"', overview)
        self.assertIn('"财年总目标"', overview)
        self.assertIn('data.scope.role === "member" && data.scope.operator', overview)
        self.assertIn("buildPeriodTimeline", overview)
        self.assertIn("<h2>{periodName}时间与目标完成对比</h2>", overview)
        self.assertNotIn('data.filters.periodType === "annual" ? buildFiscalTimeline', overview)
        self.assertIn("整季指标", overview)
        self.assertIn("整月指标", overview)
        self.assertIn("整体指标与完成", overview)
        self.assertIn("整月总指标", overview)
        self.assertIn("当月已完成", overview)
        self.assertIn("完成占比 = 当月实绩 ÷ 整月指标，不按数据日折算", overview)
        self.assertIn("cumulativeActual / cumulativeTarget", overview)
        self.assertIn('`完成占比<span style="float:right', overview)
        self.assertIn('const rankingRateLabel = isMonthView ? "完成率"', overview)
        self.assertIn('className="fiscal-progress-row is-time"', overview)
        self.assertIn('className="fiscal-progress-row is-target"', overview)
        self.assertIn("两条进度线采用相同的 0–100% 刻度", overview)
        self.assertIn("店铺完整明细表", overview)
        self.assertIn("const storeRows = data.stores ?? [];", overview)
        self.assertIn("<StoreRankingGrid rows={storeRows}", overview)
        self.assertNotIn("个人完整明细表", overview)

    def test_category_yoy_displays_last_year_same_month_baseline(self):
        dashboard = (
            ROOT / "business_analysis" / "app" / "DashboardClient.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("yearAgoLabel={yearAgoPeriod?.label", dashboard)
        self.assertIn("{yearAgoLabel}</td>", dashboard)
        self.assertIn("同比基期", dashboard)
        self.assertIn("row.yearAgoShare", dashboard)
        self.assertIn("去年同月日均销售", dashboard)
        self.assertIn("总体销售额", dashboard)
        self.assertIn("日均销售额", dashboard)
        self.assertIn("{currentLabel}总体销售额", dashboard)
        self.assertIn("{currentLabel}日均销售额", dashboard)

    def test_all_dashboard_tabs_are_visible_for_restricted_users(self):
        dashboard = (
            ROOT / "business_analysis" / "app" / "DashboardClient.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("const visibleTab: DashboardTab = activeTab;", dashboard)
        self.assertNotIn('accessScope?.role === "ratio_viewer" ? [', dashboard)
        for label in ("业绩分析", "品类阵营", "运营风险", "店铺明细"):
            self.assertIn(label, dashboard)
        self.assertIn("公司均值", dashboard)
        self.assertIn("部门均值", dashboard)
        self.assertIn("averageComparisonLabel", dashboard)
        self.assertIn("risk-average-comparison", dashboard)
        self.assertIn("平均滞销", dashboard)
        self.assertIn("panel-title-metric", dashboard)
        store_section = dashboard.split('id="stores"', 1)[1].split('id="tasks"', 1)[0]
        self.assertNotIn("<th>未发货</th>", store_section)
        self.assertNotIn('value="unshipped"', store_section)

    def test_category_snapshot_contains_paired_and_cluster_segments(self):
        snapshot = json.loads(
            (ROOT / "business_analysis" / "app" / "data" / "workbook-data.json").read_text(
                encoding="utf-8"
            )
        )

        categories = snapshot["categorySegments"]["categories"]
        self.assertEqual([item["key"] for item in categories], ["paired", "cluster"])
        self.assertEqual(snapshot["meta"]["rowCounts"]["categorySegments"], 2)
        self.assertTrue(all(len(item["departments"]) == 5 for item in categories))
        self.assertEqual(
            list(snapshot["categorySegmentsByPeriod"]),
            ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"],
        )
        expected_departments = ["运营一部", "运营二部", "运营三部", "运营六部", "运营七部"]
        for period in snapshot["categorySegmentsByPeriod"].values():
            self.assertTrue(
                all(
                    [row["department"] for row in category["departments"]]
                    == expected_departments
                    for category in period["categories"]
                )
            )
            self.assertTrue(
                all(
                    category["company"]["yearAgo"]["sales"] > 0
                    and all("yearAgoSales" in row for row in category["departments"])
                    for category in period["categories"]
                )
            )

    def test_fiscal_company_rate_supports_older_api_payloads(self):
        fiscal_overview = (
            ROOT / "business_analysis" / "app" / "components" / "FiscalOverview.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "data.overall.companyFiscalAchievementRate ?? data.overall.annualProgressRate",
            fiscal_overview,
        )


if __name__ == "__main__":
    unittest.main()
