import json
import tempfile
import unittest
from pathlib import Path

import business_analysis_company_market as company_market


class DailyMarketGrowthTests(unittest.TestCase):
    def test_daily_growth_normalizes_month_length(self):
        values = {"类目销售额": 3_100_000, "日期": "2026-03-01"}
        previous = {"month": "2026-02", "values": {"类目销售额": 2_800_000}}

        computed = company_market._compute_derived_values(values, previous, "2026-03")

        # 2026-03 有 31 天、2026-02 有 28 天：总销售额增长 10.71%，日均持平。
        self.assertAlmostEqual(computed["类目环比上月增长率"], 3_100_000 / 2_800_000 - 1, places=6)
        self.assertAlmostEqual(computed["美国市场日均环比增长率"], 0.0, places=6)

    def test_legacy_store_gets_new_derived_column_after_category_growth(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "market.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "columns": [
                            {"label": "日期", "format": "date"},
                            {"label": "类目销量", "format": "integer"},
                            {"label": "类目销售额", "format": "money"},
                            {"label": "类目环比上月增长率", "format": "ratio"},
                            {"label": "大盘客单价", "format": "decimal"},
                        ],
                        "months": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            store = company_market.load_company_market_store(path)
            labels = [column["label"] for column in store["columns"]]

            self.assertIn("美国市场日均环比增长率", labels)
            self.assertEqual(
                labels.index("美国市场日均环比增长率"),
                labels.index("类目环比上月增长率") + 1,
            )

    def test_manual_entry_persists_daily_growth(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "market.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "columns": [
                            {"label": "日期", "format": "date"},
                            {"label": "类目销量", "format": "integer"},
                            {"label": "类目销售额", "format": "money"},
                        ],
                        "months": {
                            "2026-02": {
                                "month": "2026-02",
                                "date": "2026-02-01",
                                "values": {"类目销量": 100_000, "类目销售额": 2_800_000},
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            company_market.upsert_company_market_month(
                "2026-03",
                {"类目销量": 100_000, "类目销售额": 3_100_000},
                "2026-03-01",
                path=path,
            )
            stored = company_market.load_company_market_store(path)

            self.assertAlmostEqual(
                stored["months"]["2026-03"]["values"]["美国市场日均环比增长率"],
                0.0,
                places=6,
            )

    def test_market_overview_rows_reuse_category_sales_and_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "market.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "columns": [
                            {"label": "类目销量", "format": "integer"},
                            {"label": "类目销售额", "format": "money"},
                        ],
                        "months": {
                            "2026-09": {
                                "month": "2026-09",
                                "values": {"类目销量": 100, "类目销售额": 1000},
                            },
                            "2026-10": {
                                "month": "2026-10",
                                "values": {"类目销量": 120, "类目销售额": 1320},
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            rows = company_market.get_market_overview_rows(path)

            self.assertEqual([row["period"] for row in rows], ["2026-09", "2026-10"])
            self.assertEqual(rows[-1]["salesVolume"], 120)
            self.assertEqual(rows[-1]["salesAmount"], 1320)
            self.assertAlmostEqual(rows[-1]["monthOverMonthGrowth"], 0.32, places=6)


if __name__ == "__main__":
    unittest.main()
