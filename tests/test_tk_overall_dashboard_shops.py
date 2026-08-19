import unittest
from pathlib import Path


class TkOverallDashboardShopTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.backend = (root / "tk_total_dashboard.py").read_text(encoding="utf-8")

    def test_shop_source_unions_settlement_and_order_data(self):
        helper = self.backend.split(
            "def _get_overall_dashboard_shops():", 1
        )[1].split("METRICS_CACHE_TTL", 1)[0]
        self.assertIn("FROM v_TK_JieSuan WITH (NOLOCK)", helper)
        self.assertIn("FROM TK_DingDan WITH (NOLOCK)", helper)
        self.assertIn("UNION", helper)

    def test_shop_endpoint_and_all_shop_queries_share_complete_source(self):
        endpoint = self.backend.split(
            "def tk_shops():", 1
        )[1].split("def tk_joint_shops():", 1)[0]
        self.assertIn("shops = _get_overall_dashboard_shops()", endpoint)

        default_refresh = self.backend.split(
            "def _refresh_default_cache_once():", 1
        )[1].split("def _run_default_cache_refresh", 1)[0]
        self.assertIn("shops = _get_overall_dashboard_shops()", default_refresh)

        metrics = self.backend.split(
            "def tk_metrics():", 1
        )[1]
        self.assertIn("shops = _get_overall_dashboard_shops()", metrics)


if __name__ == "__main__":
    unittest.main()
