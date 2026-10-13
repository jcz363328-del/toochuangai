import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "ads_monitor_web" / "ads-monitor-web-full-source" / "ads-monitor-web"
ADS_MONITOR_ROOT = WEB_ROOT.parent


class AdsMonitorIntegrationTests(unittest.TestCase):
    def test_ai_department_has_ads_monitor_card(self):
        page = (ROOT / "templates" / "ai_modules.html").read_text(encoding="utf-8")
        self.assertIn("MAGIC AD 广告监控", page)
        self.assertIn("url_for('ads_monitor')", page)

    def test_main_app_protects_page_and_api_with_magic_ad_permission(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("@app.route('/ai/ads-monitor')", app_source)
        self.assertIn("@app.route('/api/ads-monitor/diagnostic'", app_source)
        self.assertGreaterEqual(app_source.count("@require_permission('ads_monitor')"), 3)

    def test_frontend_has_a_dedicated_flask_build_and_proxy_endpoint(self):
        package = (WEB_ROOT / "package.json").read_text(encoding="utf-8")
        diagnostic_api = (WEB_ROOT / "src" / "adDiagnosticApi.js").read_text(encoding="utf-8")
        self.assertIn('"build:flask"', package)
        self.assertIn("/ai/ads-monitor/", package)
        self.assertIn("/api/ads-monitor/diagnostic", diagnostic_api)

    def test_diagnostic_first_paint_loads_hourly_catalog_before_campaign_detail(self):
        view = (WEB_ROOT / "src" / "AdDiagnosticView.jsx").read_text(encoding="utf-8")
        component = view.split("export function AdDiagnosticView", 1)[1]

        self.assertIn(
            'const [selectedCampaignId, setSelectedCampaignId] = useState("");',
            component,
        )
        self.assertNotIn('useState(shop.defaultCampaignId || "")', component)
        self.assertLess(
            component.index("if (!selectedCampaignId)"),
            component.index('section: "overview"'),
        )

    def test_hourly_snapshot_runner_prioritizes_default_shop_campaign(self):
        for script_name in (
            "run_ads_diagnostic_hourly_refresh.ps1",
            "运行广告诊断每小时刷新.ps1",
        ):
            runner = (ADS_MONITOR_ROOT / script_name).read_text(encoding="utf-8-sig")
            with self.subTest(script=script_name):
                self.assertIn('$PriorityShopId = "475394"', runner)
                self.assertIn('$PriorityCampaignId = "70540977760495"', runner)
                self.assertIn('"--status-file", $priorityStatusFile', runner)
                self.assertIn('"--shop-id", $PriorityShopId', runner)
                self.assertIn('"--campaign-id", $PriorityCampaignId', runner)


if __name__ == "__main__":
    unittest.main()
