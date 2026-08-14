from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TkDashboardMultiShopTests(unittest.TestCase):
    def test_procedure_source_aggregates_all_selected_shop_ratios(self):
        source = (ROOT / "create_sps.py").read_text(encoding="utf-8")

        self.assertNotIn(
            "(SELECT 比例 FROM tk_费用分摊比例",
            source,
        )
        self.assertEqual(
            source.count(
                "(SELECT SUM(CASE WHEN ISNUMERIC(比例) = 1 "
                "THEN CONVERT(DECIMAL(18,6), 比例) ELSE 0 END) "
                "FROM tk_费用分摊比例"
            ),
            6,
        )

    def test_migration_rewrites_existing_procedure_without_dropping_it(self):
        migration = (
            ROOT
            / "migrations"
            / "20260728_fix_tk_dashboard_multi_shop_allocation.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("ALTER PROCEDURE", migration)
        self.assertIn("@ScalarRatioLookup", migration)
        self.assertIn("@AggregatedRatioLookup", migration)
        self.assertNotIn("DROP PROCEDURE", migration)


if __name__ == "__main__":
    unittest.main()
