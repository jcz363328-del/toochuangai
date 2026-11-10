import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import business_analysis_fiscal_overview as fiscal_module
from business_analysis_fiscal_overview import shape_fiscal_overview


ROWS = [
    {"PeriodStart": "2026-06-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 100, "Actual": 80, "LatestActualDate": "2026-07-31", "MatchedStoreCount": 2, "ExcludedActualStoreCount": 1},
    {"PeriodStart": "2026-07-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 100, "Actual": 120, "LatestActualDate": "2026-07-31", "MatchedStoreCount": 2, "ExcludedActualStoreCount": 1},
    {"PeriodStart": "2026-08-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 100, "Actual": 0, "LatestActualDate": "2026-07-31", "MatchedStoreCount": 2, "ExcludedActualStoreCount": 1},
    {"PeriodStart": "2026-06-01", "Store": 2, "Operator": "乙", "Department": "王钰媛", "Target": 200, "Actual": 100, "LatestActualDate": "2026-07-31", "MatchedStoreCount": 2, "ExcludedActualStoreCount": 1},
    {"PeriodStart": "2026-07-01", "Store": 2, "Operator": "乙", "Department": "王钰媛", "Target": 200, "Actual": 300, "LatestActualDate": "2026-07-31", "MatchedStoreCount": 2, "ExcludedActualStoreCount": 1},
    {"PeriodStart": "2026-08-01", "Store": 2, "Operator": "乙", "Department": "王钰媛", "Target": 200, "Actual": 0, "LatestActualDate": "2026-07-31", "MatchedStoreCount": 2, "ExcludedActualStoreCount": 1},
]


class FiscalOverviewTests(unittest.TestCase):
    def test_fiscal_actual_uses_lirun_sales(self):
        self.assertIn("FROM dbo.LiRun ml", fiscal_module.FISCAL_OVERVIEW_SQL)
        self.assertNotIn("FROM dbo.v_MaoLiLv ml", fiscal_module.FISCAL_OVERVIEW_SQL)

    def test_owner_reconciles_ytd_target_actual_rate_and_gap(self):
        result = shape_fiscal_overview(ROWS, "2026-2027", {"role": "business_owner", "canViewAmounts": True})

        self.assertEqual(result["overall"]["fullYearTarget"], 900)
        self.assertEqual(result["overall"]["periodTarget"], 900)
        self.assertEqual(result["overall"]["ytdTarget"], 600)
        self.assertEqual(result["overall"]["actual"], 600)
        self.assertEqual(result["overall"]["achievementRate"], 1)
        self.assertAlmostEqual(result["overall"]["periodCompletionRate"], 2 / 3)
        self.assertEqual(result["overall"]["gap"], 0)
        self.assertEqual(result["departments"][0]["name"], "运营二部")
        self.assertEqual(result["people"][0]["name"], "乙")
        self.assertEqual(result["people"][0]["storeNames"], ["2号店"])
        self.assertEqual([row["name"] for row in result["stores"]], ["2号店", "1号店"])
        self.assertEqual(result["stores"][0]["operator"], "乙")
        self.assertEqual(result["stores"][0]["department"], "运营二部")
        self.assertIsNone(result["monthly"][2]["actual"])

    def test_store_labels_only_show_stores_in_the_metric_universe(self):
        rows = [
            {"PeriodStart": "2026-06-01", "Store": 28, "Operator": "甲", "Department": "周雪", "Target": 340000, "Actual": 0, "LatestActualDate": "2026-06-30", "IsMetricStore": 1},
            {"PeriodStart": "2026-06-01", "Store": 502, "Operator": "甲", "Department": "周雪", "Target": 1, "Actual": 0, "LatestActualDate": "2026-06-30", "IsMetricStore": 0},
        ]

        result = shape_fiscal_overview(rows, "2026-2027", {"role": "business_owner", "canViewAmounts": True})

        self.assertEqual(result["people"][0]["storeNames"], ["28号店"])
        self.assertEqual(result["people"][0]["stores"], 1)
        self.assertEqual(result["departments"][0]["storeNames"], ["28号店"])
        self.assertEqual(result["departments"][0]["stores"], 1)
        self.assertEqual([row["name"] for row in result["stores"]], ["28号店"])

    def test_legacy_cache_infers_metric_stores_from_actual_rows(self):
        rows = ROWS + [
            {"PeriodStart": "2026-06-01", "Store": 502, "Operator": "甲", "Department": "周雪", "Target": 1, "Actual": 0, "LatestActualDate": "2026-07-31"},
        ]

        result = shape_fiscal_overview(rows, "2026-2027", {"role": "business_owner", "canViewAmounts": True})
        person = next(row for row in result["people"] if row["name"] == "甲")

        self.assertEqual(person["storeNames"], ["1号店"])
        self.assertEqual(person["stores"], 1)

    def test_one_operator_with_multiple_stores_is_split_into_store_rows(self):
        rows = [
            {"PeriodStart": "2026-06-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 100, "Actual": 80, "LatestActualDate": "2026-06-30", "IsMetricStore": 1},
            {"PeriodStart": "2026-06-01", "Store": 2, "Operator": "甲", "Department": "周雪", "Target": 200, "Actual": 100, "LatestActualDate": "2026-06-30", "IsMetricStore": 1},
        ]

        result = shape_fiscal_overview(rows, "2026-2027", {"role": "business_owner", "canViewAmounts": True})

        self.assertEqual(len(result["people"]), 1)
        self.assertEqual([row["name"] for row in result["stores"]], ["1号店", "2号店"])
        self.assertTrue(all(row["operator"] == "甲" for row in result["stores"]))

    def test_store_owner_uses_latest_month_in_selected_period(self):
        rows = [
            {"PeriodStart": "2026-06-01", "Store": 1.0, "Operator": "旧负责人", "Department": "周雪", "Target": 100, "Actual": 80, "LatestActualDate": "2026-07-31", "IsMetricStore": 1},
            {"PeriodStart": "2026-07-01", "Store": 1.0, "Operator": "新负责人", "Department": "王钰媛", "Target": 100, "Actual": 120, "LatestActualDate": "2026-07-31", "IsMetricStore": 1},
        ]

        annual = shape_fiscal_overview(rows, "2026-2027", {"role": "business_owner", "canViewAmounts": True})
        june = shape_fiscal_overview(
            rows,
            "2026-2027",
            {"role": "business_owner", "canViewAmounts": True},
            filters={"periodType": "month", "period": "2026-06"},
        )

        self.assertEqual(annual["stores"][0]["name"], "1号店")
        self.assertEqual(annual["stores"][0]["operator"], "新负责人")
        self.assertEqual(annual["stores"][0]["department"], "运营二部")
        self.assertEqual(june["stores"][0]["operator"], "旧负责人")
        self.assertEqual(june["stores"][0]["department"], "运营一部")

    def test_department_leader_only_sees_department(self):
        result = shape_fiscal_overview(ROWS, "2026-2027", {
            "role": "department_leader",
            "department": "运营一部",
            "canViewAmounts": True,
        })

        self.assertEqual(result["overall"]["fullYearTarget"], 300)
        self.assertEqual([row["name"] for row in result["people"]], ["甲"])
        self.assertEqual(result["people"][0]["storeNames"], ["1号店"])
        self.assertEqual([row["name"] for row in result["stores"]], ["1号店"])

    def test_member_only_sees_self_and_amounts_are_redacted(self):
        result = shape_fiscal_overview(ROWS, "2026-2027", {
            "role": "member",
            "department": "运营一部",
            "operator": "甲",
            "canViewAmounts": False,
        })

        self.assertIsNone(result["overall"]["actual"])
        self.assertEqual(result["overall"]["achievementRate"], 1)
        self.assertEqual(result["overall"]["gapRate"], 0)
        self.assertAlmostEqual(result["overall"]["remainingRate"], 1 / 3)
        self.assertEqual([row["name"] for row in result["people"]], ["甲"])
        self.assertIsNone(result["people"][0]["gap"])
        self.assertEqual(result["people"][0]["gapRate"], 0)
        self.assertEqual([row["name"] for row in result["stores"]], ["1号店"])
        self.assertIsNone(result["stores"][0]["gap"])
        self.assertEqual(result["stores"][0]["operator"], "甲")

    def test_ratio_viewer_keeps_rates_but_redacts_company_amounts(self):
        result = shape_fiscal_overview(ROWS, "2026-2027", {
            "role": "ratio_viewer",
            "canViewAmounts": False,
        })

        self.assertEqual(len(result["departments"]), 2)
        self.assertEqual(result["overall"]["achievementRate"], 1)
        self.assertIsNone(result["overall"]["fullYearTarget"])
        self.assertIsNone(result["overall"]["periodTarget"])
        self.assertAlmostEqual(result["overall"]["periodCompletionRate"], 2 / 3)

    def test_owner_can_filter_department_and_single_month(self):
        result = shape_fiscal_overview(
            ROWS,
            "2026-2027",
            {"role": "business_owner", "canViewAmounts": True},
            filters={"department": "运营一部", "periodType": "month", "period": "2026-07"},
        )

        self.assertEqual(result["filters"]["department"], "运营一部")
        self.assertEqual(result["filters"]["periodLabel"], "2026年7月")
        self.assertEqual(result["overall"]["ytdTarget"], 100)
        self.assertEqual(result["overall"]["periodTarget"], 100)
        self.assertEqual(result["overall"]["actual"], 120)
        self.assertEqual(result["overall"]["achievementRate"], 1.2)
        self.assertEqual(result["overall"]["periodCompletionRate"], 1.2)
        self.assertEqual([row["name"] for row in result["departments"]], ["运营一部"])
        self.assertEqual([row["name"] for row in result["people"]], ["甲"])
        self.assertEqual([row["name"] for row in result["stores"]], ["1号店"])

    def test_quarter_filter_uses_elapsed_months_in_fiscal_quarter(self):
        result = shape_fiscal_overview(
            ROWS,
            "2026-2027",
            {"role": "business_owner", "canViewAmounts": True},
            filters={"periodType": "quarter", "period": "Q1"},
        )

        self.assertEqual(result["overall"]["ytdTarget"], 600)
        self.assertEqual(result["overall"]["periodTarget"], 900)
        self.assertEqual(result["overall"]["actual"], 600)
        self.assertAlmostEqual(result["overall"]["periodCompletionRate"], 2 / 3)
        self.assertEqual(result["period"]["elapsedMonths"], 2)
        self.assertEqual(result["period"]["totalMonths"], 3)
        self.assertIsNone(result["monthly"][2]["actual"])

    def test_current_month_target_is_prorated_to_latest_actual_day(self):
        rows = [
            {"PeriodStart": "2026-08-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 100, "Actual": 100, "LatestActualDate": "2026-09-03", "IsMetricStore": 1},
            {"PeriodStart": "2026-09-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 300, "Actual": 30, "LatestActualDate": "2026-09-03", "IsMetricStore": 1},
            {"PeriodStart": "2026-10-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 200, "Actual": 0, "LatestActualDate": "2026-09-03", "IsMetricStore": 1},
        ]

        result = shape_fiscal_overview(
            rows,
            "2026-2027",
            {"role": "business_owner", "canViewAmounts": True},
        )

        self.assertEqual(result["overall"]["fullYearTarget"], 600)
        self.assertEqual(result["overall"]["ytdTarget"], 130)
        self.assertEqual(result["overall"]["periodTarget"], 600)
        self.assertEqual(result["overall"]["actual"], 130)
        self.assertEqual(result["overall"]["achievementRate"], 1)
        self.assertAlmostEqual(result["overall"]["periodCompletionRate"], 130 / 600)
        self.assertEqual(result["overall"]["periodRemaining"], 470)
        self.assertEqual(result["overall"]["gap"], 0)
        self.assertTrue(result["period"]["targetProrated"])
        self.assertEqual(result["period"]["targetElapsedDays"], 3)
        self.assertEqual(result["period"]["targetMonthDays"], 30)
        self.assertEqual(result["monthly"][1]["target"], 300)
        self.assertEqual(result["monthly"][1]["targetToDate"], 30)
        self.assertEqual(result["monthly"][1]["cumulativeTarget"], 400)
        self.assertEqual(result["monthly"][1]["cumulativeTargetToDate"], 130)
        self.assertEqual(result["monthly"][1]["achievementRate"], 1)
        self.assertIsNone(result["monthly"][2]["cumulativeTargetToDate"])
        self.assertEqual(result["departments"][0]["ytdTarget"], 130)
        self.assertEqual(result["people"][0]["achievementRate"], 1)
        self.assertEqual(result["stores"][0]["achievementRate"], 1)

    def test_current_month_view_uses_full_month_target_without_daily_proration(self):
        rows = [
            {"PeriodStart": "2026-08-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 100, "Actual": 100, "LatestActualDate": "2026-09-03", "IsMetricStore": 1},
            {"PeriodStart": "2026-09-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 300, "Actual": 30, "LatestActualDate": "2026-09-03", "IsMetricStore": 1},
        ]

        result = shape_fiscal_overview(
            rows,
            "2026-2027",
            {"role": "business_owner", "canViewAmounts": True},
            filters={"periodType": "month", "period": "2026-09"},
        )

        self.assertEqual(result["overall"]["periodTarget"], 300)
        self.assertEqual(result["overall"]["ytdTarget"], 300)
        self.assertEqual(result["overall"]["actual"], 30)
        self.assertEqual(result["overall"]["achievementRate"], 0.1)
        self.assertEqual(result["overall"]["periodCompletionRate"], 0.1)
        self.assertEqual(result["overall"]["gap"], 270)
        self.assertFalse(result["period"]["targetProrated"])
        self.assertIsNone(result["period"]["targetElapsedDays"])
        self.assertEqual(result["monthly"][0]["targetToDate"], 300)
        self.assertEqual(result["monthly"][0]["achievementRate"], 0.1)
        self.assertEqual(result["departments"][0]["ytdTarget"], 300)
        self.assertEqual(result["departments"][0]["achievementRate"], 0.1)
        self.assertEqual(result["stores"][0]["achievementRate"], 0.1)

        redacted = shape_fiscal_overview(
            rows,
            "2026-2027",
            {"role": "ratio_viewer", "canViewAmounts": False},
            filters={"periodType": "month", "period": "2026-09"},
        )
        self.assertIsNone(redacted["overall"]["periodTarget"])
        self.assertIsNone(redacted["overall"]["actual"])
        self.assertEqual(redacted["overall"]["achievementRate"], 0.1)
        self.assertEqual(redacted["overall"]["companyFiscalAchievementRate"], 0.325)
        self.assertIsNone(redacted["monthly"][0]["target"])
        self.assertEqual(redacted["monthly"][0]["achievementRate"], 0.1)
        self.assertIsNone(redacted["departments"][0]["ytdTarget"])
        self.assertEqual(redacted["departments"][0]["achievementRate"], 0.1)

    def test_company_fiscal_achievement_ignores_department_filter_and_daily_proration(self):
        rows = [
            {"PeriodStart": "2026-06-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 100, "Actual": 40, "LatestActualDate": "2026-09-05", "IsMetricStore": 1},
            {"PeriodStart": "2026-09-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 100, "Actual": 10, "LatestActualDate": "2026-09-05", "IsMetricStore": 1},
            {"PeriodStart": "2026-06-01", "Store": 2, "Operator": "乙", "Department": "王钰婷", "Target": 200, "Actual": 100, "LatestActualDate": "2026-09-05", "IsMetricStore": 1},
            {"PeriodStart": "2026-09-01", "Store": 2, "Operator": "乙", "Department": "王钰婷", "Target": 200, "Actual": 20, "LatestActualDate": "2026-09-05", "IsMetricStore": 1},
        ]

        result = shape_fiscal_overview(
            rows,
            "2026-2027",
            {"role": "ratio_viewer", "canViewAmounts": False},
            filters={"periodType": "annual", "department": "运营一部"},
        )

        self.assertAlmostEqual(result["overall"]["companyFiscalAchievementRate"], 170 / 600)
        self.assertNotEqual(
            result["overall"]["companyFiscalAchievementRate"],
            result["overall"]["achievementRate"],
        )

    def test_current_quarter_keeps_latest_month_daily_proration(self):
        rows = [
            {"PeriodStart": f"2026-{month:02d}-01", "Store": 1, "Operator": "甲", "Department": "周雪", "Target": 100, "Actual": actual, "LatestActualDate": "2026-09-03", "IsMetricStore": 1}
            for month, actual in ((6, 100), (7, 100), (8, 100), (9, 10), (10, 0), (11, 0))
        ]

        result = shape_fiscal_overview(
            rows,
            "2026-2027",
            {"role": "business_owner", "canViewAmounts": True},
            filters={"periodType": "quarter", "period": "Q2"},
        )

        self.assertEqual(result["overall"]["periodTarget"], 300)
        self.assertEqual(result["overall"]["ytdTarget"], 10)
        self.assertEqual(result["overall"]["actual"], 10)
        self.assertEqual(result["overall"]["achievementRate"], 1)
        self.assertAlmostEqual(result["overall"]["periodCompletionRate"], 1 / 30)
        self.assertTrue(result["period"]["targetProrated"])
        self.assertEqual(result["monthly"][0]["targetToDate"], 10)

    def test_department_filter_cannot_escape_leader_scope(self):
        with self.assertRaisesRegex(ValueError, "权限范围"):
            shape_fiscal_overview(
                ROWS,
                "2026-2027",
                {"role": "department_leader", "department": "运营一部", "canViewAmounts": True},
                filters={"department": "运营二部"},
            )


class FiscalOverviewMonthlyCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cache_directory_patch = patch.object(
            fiscal_module,
            "CACHE_DIRECTORY",
            Path(self.temporary.name),
        )
        self.cache_directory_patch.start()
        fiscal_module._raw_cache.clear()
        fiscal_module._refreshing_years.clear()

    def tearDown(self):
        fiscal_module._raw_cache.clear()
        fiscal_module._refreshing_years.clear()
        self.cache_directory_patch.stop()
        self.temporary.cleanup()

    def test_current_month_disk_cache_skips_database_query(self):
        rows = [{"PeriodStart": "2026-06-01", "Store": 1, "Target": 100, "Actual": 80}]
        fiscal_module._write_disk_cache("2026-2027", "2026-09", rows)

        with patch.object(fiscal_module, "_cache_month", return_value="2026-09"), patch.object(
            fiscal_module,
            "_query_raw_rows",
            side_effect=AssertionError("当月缓存命中时不应查询数据库"),
        ):
            result = fiscal_module._fetch_raw_rows("2026-2027")

        self.assertEqual(result, rows)

    def test_stale_disk_cache_returns_immediately_and_starts_background_refresh(self):
        rows = [{"PeriodStart": "2026-06-01", "Store": 1, "Target": 100, "Actual": 80}]
        fiscal_module._write_disk_cache("2026-2027", "2026-08", rows)

        with patch.object(fiscal_module, "_cache_month", return_value="2026-09"), patch.object(
            fiscal_module,
            "_start_background_refresh",
        ) as refresh:
            result = fiscal_module._fetch_raw_rows("2026-2027")

        self.assertEqual(result, rows)
        refresh.assert_called_once_with("2026-2027", "2026-09")


if __name__ == "__main__":
    unittest.main()
