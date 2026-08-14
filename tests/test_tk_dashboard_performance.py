from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TkDashboardPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = (ROOT / "tk_total_dashboard.py").read_text(encoding="utf-8")
        cls.template = (
            ROOT / "templates" / "tk_total_dashboard.html"
        ).read_text(encoding="utf-8")

    def test_metric_computation_no_longer_calls_monolithic_procedure(self):
        compute_block = self.backend.split(
            "def _compute_metrics_payload(", 1
        )[1].split("def _get_cached_metrics_payload(", 1)[0]

        self.assertIn("_fetch_dashboard_metrics_fast(", compute_block)
        self.assertNotIn("EXEC sp_TK_Dashboard_GetMetrics", compute_block)

    def test_cold_query_returns_shell_and_refreshes_in_background(self):
        cache_block = self.backend.split(
            "def _get_cached_metrics_payload(", 1
        )[1].split("def _merge_numeric_dicts(", 1)[0]

        self.assertIn("refresh_in_background()", cache_block)
        self.assertIn("_build_dashboard_shell_payload(", cache_block)
        self.assertIn("sales_source=sales_source", cache_block)
        self.assertIn("'refreshing': True", self.backend)
        self.assertIn("pollMetricsUntilReady", self.template)

    def test_page_open_schedules_refresh_instead_of_waiting_for_it(self):
        page_block = self.backend.split(
            "def tk_dashboard_page():", 1
        )[1].split("def tk_dashboard_project_page():", 1)[0]

        self.assertIn("_schedule_default_cache_refresh()", page_block)
        self.assertNotIn("_refresh_default_cache_once()", page_block)

    def test_default_refresh_does_not_precompute_every_shop(self):
        refresh_block = self.backend.split(
            "def _refresh_default_cache_once():", 1
        )[1].split("def _run_default_cache_refresh(", 1)[0]

        self.assertNotIn("for s in shops:", refresh_block)
        self.assertIn("new_map['ALL']", refresh_block)
        self.assertIn("_default_cache_refresh_lock", self.backend)


if __name__ == "__main__":
    unittest.main()
