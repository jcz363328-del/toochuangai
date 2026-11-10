from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "innovation" / "templates" / "index.html").read_text(encoding="utf-8")
BACKEND = (ROOT / "innovation" / "web_app.py").read_text(encoding="utf-8")


class InnovationDashboardEchartsTests(unittest.TestCase):
    def test_dashboard_uses_echarts_for_every_visual_section(self) -> None:
        self.assertIn("echarts@5.5.1", TEMPLATE)
        self.assertNotIn("new Chart(", TEMPLATE)
        for chart_id in (
            "top-department",
            "top-person",
            "top-proposal-counts",
            "top-highest-scores",
            "category-distribution",
            "monthly-trend",
        ):
            self.assertIn(f'id="{chart_id}" class="dashboard-chart', TEMPLATE)

    def test_dashboard_uses_three_equal_chart_columns(self) -> None:
        self.assertIn("grid-template-columns: repeat(12, minmax(0, 1fr))", TEMPLATE)
        self.assertIn('dashboard-chart-card main', TEMPLATE)
        self.assertIn('dashboard-chart-card side', TEMPLATE)
        self.assertIn(".dashboard-chart-card.main {", TEMPLATE)
        main_style = TEMPLATE.split('.innovation-dashboard .dashboard-chart-card.main {', 1)[1].split('}', 1)[0]
        self.assertIn("grid-column: span 4;", main_style)
        self.assertLess(TEMPLATE.index('id="top-person"'), TEMPLATE.index('id="monthly-trend"'))
        self.assertLess(TEMPLATE.index('id="monthly-trend"'), TEMPLATE.index('id="top-proposal-counts"'))
        self.assertEqual(TEMPLATE.count('id="monthly-trend"'), 1)

    def test_dashboard_has_chart_lifecycle_and_empty_state_handling(self) -> None:
        self.assertIn("const dashboardCharts = new Map()", TEMPLATE)
        self.assertIn("chart.showLoading", TEMPLATE)
        self.assertIn("chart.hideLoading", TEMPLATE)
        self.assertIn("dashboardEmptyOption", TEMPLATE)
        self.assertIn("dashboardCharts.forEach(chart => chart.resize())", TEMPLATE)
        self.assertIn("dashboardRequestId", TEMPLATE)

    def test_dashboard_renders_expected_chart_types(self) -> None:
        self.assertIn("type: 'bar'", TEMPLATE)
        self.assertIn("type: 'pie'", TEMPLATE)
        self.assertIn("markLine:", TEMPLATE)
        self.assertIn("new echarts.graphic.LinearGradient", TEMPLATE)

    def test_date_filter_uses_local_dates_and_validates_the_range(self) -> None:
        self.assertIn("function formatLocalDate(date)", TEMPLATE)
        self.assertIn("开始日期不能晚于结束日期", TEMPLATE)
        self.assertNotIn("firstDay.toISOString()", TEMPLATE)

    def test_category_api_returns_enough_slices_for_the_pie_chart(self) -> None:
        category_section = BACKEND.split("# 4. 创新类别分布", 1)[1].split("# 5. 月度趋势", 1)[0]
        self.assertIn("SELECT TOP 8", category_section)

    def test_dashboard_month_buckets_avoid_clr_format_function(self) -> None:
        dashboard_section = BACKEND.split("def get_dashboard_data", 1)[1].split(
            "@app.route('/api/get_innovation_compare'", 1
        )[0]
        self.assertNotIn("FORMAT(", dashboard_section)
        self.assertIn("CONVERT(VARCHAR(7)", dashboard_section)

    def test_person_ranking_allows_third_place_ties(self) -> None:
        person_section = BACKEND.split("# 3. 个人积分前三名", 1)[1].split("# 4.", 1)[0]
        self.assertIn("top 3 with ties", person_section)


if __name__ == "__main__":
    unittest.main()
