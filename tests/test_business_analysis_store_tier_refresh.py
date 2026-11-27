import unittest
from datetime import date
from unittest.mock import Mock, patch

from business_analysis_store_tier_refresh import (
    ELIGIBLE_STORES,
    TIER_RULES,
    _level_for,
    _missing_tier_dates,
    _rows_for_date,
    refresh_store_tiers,
)


class StoreTierRefreshGapTests(unittest.TestCase):
    def test_historical_gap_is_backfilled_even_when_latest_date_exists(self):
        existing = {
            date(2026, 9, 23),
            date(2026, 9, 25),
            date(2026, 9, 26),
        }

        self.assertEqual(
            [date(2026, 9, 24), date(2026, 9, 27)],
            _missing_tier_dates(existing, date(2026, 9, 27)),
        )

    def test_complete_history_has_no_pending_dates(self):
        existing = {date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25)}

        self.assertEqual([], _missing_tier_dates(existing, date(2026, 9, 25)))

    def test_empty_history_starts_at_target_end(self):
        self.assertEqual(
            [date(2026, 9, 25)],
            _missing_tier_dates(set(), date(2026, 9, 25)),
        )


class BuiltInTierRulesTests(unittest.TestCase):
    def test_margin_thresholds_and_single_level_downgrade(self):
        for sales, margin, expected in (
            (15000, 0.10, "铜2"),
            (15000, 0.099, "铜1"),
            (45000, 0.20, "银1"),
            (45000, 0.199, "铜3"),
            (150000, 0.24, "金1"),
            (150000, 0.239, "银4"),
            (670000, 0.24, "钻5"),
            (670000, 0, "钻4"),
            (100, 0, "铜1"),
        ):
            with self.subTest(sales=sales, margin=margin):
                self.assertEqual(expected, _level_for(list(TIER_RULES), sales, margin)[0].name)

    def test_rows_keep_30_day_window_fee_deduction_and_store_scope(self):
        cursor = Mock()
        cursor.fetchall.return_value = [(26, 350000, 100000, 25000), (999, 350000, 100000, 25000)]
        with patch("business_analysis_store_tier_refresh._fee_map", return_value={26: 2000}):
            rows = _rows_for_date(cursor, date(2026, 11, 25), list(TIER_RULES), set(ELIGIBLE_STORES))
        self.assertEqual(1, len(rows))
        self.assertEqual((26, "金", 5, 12), rows[0][1:5])
        self.assertEqual((date(2026, 10, 27), date(2026, 11, 25)), rows[0][5:7])
        self.assertEqual(23, rows[0][8])

    def _connection(self):
        connection = Mock()
        connection.cursor.return_value.fetchall.return_value = [(date(2026, 11, 25),)]
        return connection

    def test_refresh_needs_no_workbook_even_with_obsolete_template_setting(self):
        connection = self._connection()
        with patch.dict("os.environ", {"BUSINESS_ANALYSIS_TIER_TEMPLATE": "/missing/template.xlsm"}), patch(
            "business_analysis_store_tier_refresh.pytds.connect", return_value=connection
        ), patch("business_analysis_store_tier_refresh.sql_server_config", return_value={}), patch(
            "builtins.open", side_effect=AssertionError("Refresh must not read a workbook")
        ):
            result = refresh_store_tiers(today=date(2026, 11, 27))
        self.assertEqual("up-to-date", result["status"])
        self.assertEqual("2026-11-25", result["throughDate"])
        self.assertEqual("built-in", result["ruleSource"])
        self.assertEqual(21, result["ruleCount"])
        self.assertEqual(37, result["storeCount"])
        self.assertNotIn("templatePath", result)
        connection.commit.assert_not_called()
        connection.close.assert_called_once()

    def test_dry_run_does_not_write_calculated_rows(self):
        connection = self._connection()
        connection.cursor.return_value.fetchall.return_value = [(date(2026, 11, 24),)]
        with patch("business_analysis_store_tier_refresh.pytds.connect", return_value=connection), patch(
            "business_analysis_store_tier_refresh.sql_server_config", return_value={}
        ), patch("business_analysis_store_tier_refresh._rows_for_date", return_value=[("calculated",)]):
            result = refresh_store_tiers(today=date(2026, 11, 27), dry_run=True)
        self.assertEqual("dry-run", result["status"])
        self.assertEqual("2026-11-25", result["throughDate"])
        connection.cursor.return_value.executemany.assert_not_called()
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once()

    def test_query_failure_rolls_back_without_deleting_existing_rows(self):
        connection = self._connection()
        connection.cursor.return_value.fetchall.return_value = [(date(2026, 11, 24),)]
        with patch("business_analysis_store_tier_refresh.pytds.connect", return_value=connection), patch(
            "business_analysis_store_tier_refresh.sql_server_config", return_value={}
        ), patch("business_analysis_store_tier_refresh._rows_for_date", side_effect=RuntimeError("query failed")):
            with self.assertRaisesRegex(RuntimeError, "query failed"):
                refresh_store_tiers(today=date(2026, 11, 27))
        self.assertEqual(1, connection.cursor.return_value.execute.call_count)
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
