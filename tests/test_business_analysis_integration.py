import unittest
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BusinessAnalysisIntegrationTests(unittest.TestCase):
    def test_ai_department_has_business_analysis_card(self):
        page = (ROOT / "templates" / "ai_modules.html").read_text(encoding="utf-8")

        self.assertIn("<h3>经营分析</h3>", page)
        self.assertIn("url_for('business_analysis')", page)

    def test_flask_bundle_and_protected_routes_are_wired(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        package = (ROOT / "business_analysis" / "package.json").read_text(encoding="utf-8")
        flask_entry = (ROOT / "business_analysis" / "flask" / "index.html").read_text(encoding="utf-8")

        self.assertIn("@app.route('/ai/business-analysis')", app_source)
        self.assertIn("@app.route('/ai/business-analysis/assets/<path:filename>')", app_source)
        self.assertIn("@app.route('/api/ai/business-analysis/dashboard')", app_source)
        self.assertGreaterEqual(app_source.count("@_require_business_analysis_access"), 4)
        self.assertIn("force_business_analysis_query_params", app_source)
        self.assertIn("prepare_business_analysis_payload", app_source)
        self.assertIn('"build:flask"', package)
        self.assertIn('data-dashboard-api="/api/ai/business-analysis/dashboard"', flask_entry)

        flask_main = (ROOT / "business_analysis" / "flask" / "main.tsx").read_text(encoding="utf-8")
        self.assertIn("emptyWorkbookData", flask_main)
        self.assertNotIn("workbook-data.json", flask_main)

    def test_dashboard_tab_state_is_initialized_before_it_is_read(self):
        dashboard = (
            ROOT / "business_analysis" / "app" / "DashboardClient.tsx"
        ).read_text(encoding="utf-8")

        state_declaration = dashboard.index(
            'const [activeTab, setActiveTab] = useState<DashboardTab>("performance");'
        )
        visible_tab_declaration = dashboard.index(
            'const visibleTab: DashboardTab = accessScope?.role === "ratio_viewer"'
        )
        self.assertLess(state_declaration, visible_tab_declaration)

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


if __name__ == "__main__":
    unittest.main()
