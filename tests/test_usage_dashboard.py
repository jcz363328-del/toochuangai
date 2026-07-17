from __future__ import annotations

import unittest
from datetime import date

from 图片 import openrouter_image_site as site


class UsageDashboardTests(unittest.TestCase):
    def test_dashboard_aggregates_feature_hour_and_day_usage(self) -> None:
        rows = [
            (date(2026, 7, 17), 9, "智能抠图", 3, 2),
            (date(2026, 7, 17), 10, "模特图批量高清", 2, 2),
            (date(2026, 7, 17), 10, "智能抠图", 1, 2),
            (date(2026, 7, 16), 9, "智能抠图", 4, 2),
            (date(2026, 7, 11), 14, "主图生A+", 5, 2),
        ]

        data = site.build_xiaoha_usage_dashboard_data(rows, date(2026, 7, 17))

        self.assertEqual(data["today_total"], 6)
        self.assertEqual(data["yesterday_total"], 4)
        self.assertEqual(data["active_accounts"], 2)
        self.assertEqual(data["active_features"], 2)
        self.assertEqual(data["peak_hour"], "09:00")
        self.assertEqual(data["peak_count"], 3)
        self.assertEqual(data["feature_names"], ["智能抠图", "模特图批量高清"])
        self.assertEqual(data["feature_counts"], [4, 2])
        self.assertEqual(data["day_labels"], ["07-11", "07-12", "07-13", "07-14", "07-15", "07-16", "07-17"])
        self.assertEqual(data["day_totals"], [5, 0, 0, 0, 0, 4, 6])
        self.assertEqual(data["today_hour_totals"][9:11], [3, 3])
        self.assertEqual(data["yesterday_hour_totals"][9], 4)
        self.assertTrue(data["has_today_data"])

    def test_dashboard_handles_empty_summary_row(self) -> None:
        data = site.build_xiaoha_usage_dashboard_data(
            [(None, None, None, None, 0)],
            "2026-07-17",
        )

        self.assertEqual(data["today_total"], 0)
        self.assertEqual(data["active_features"], 0)
        self.assertEqual(data["peak_hour"], "—")
        self.assertEqual(data["top_feature_name"], "暂无")
        self.assertFalse(data["has_today_data"])

    def test_dashboard_html_uses_echarts_and_all_required_charts(self) -> None:
        data = site.build_xiaoha_usage_dashboard_data([], date(2026, 7, 17))

        dashboard_html = site.build_xiaoha_usage_dashboard_html(data)

        self.assertIn("echarts@5.5.1", dashboard_html)
        self.assertIn('id="featureRanking"', dashboard_html)
        self.assertIn('id="dailyTrend"', dashboard_html)
        self.assertIn('id="hourlyTrend"', dashboard_html)
        self.assertIn("AI_TuPian", dashboard_html)
        self.assertIn("GongNeng", dashboard_html)
        self.assertIn("昨日总量", dashboard_html)


if __name__ == "__main__":
    unittest.main()
