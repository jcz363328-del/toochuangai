import unittest
from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from openpyxl import load_workbook

import review_analysis as review_module


ROOT = Path(__file__).resolve().parents[1]
REVIEW_TEMPLATE_SOURCE = (ROOT / "templates" / "review_analysis.html").read_text(
    encoding="utf-8"
)


class ReviewAnalysisQueryTests(unittest.TestCase):
    def test_query_uses_charindex_without_percent_format_tokens(self):
        sql = review_module._build_review_query(
            "SKU-123",
            datetime(2026, 7, 1),
            5,
        )

        self.assertIn("CHARINDEX", sql)
        self.assertIn("COALESCE(ASIN, '') + COALESCE(SKU, '')", sql)
        self.assertNotIn("%", sql)
        self.assertNotIn("XingJi <=", sql)

    def test_query_adds_rating_limit_and_escapes_identifier(self):
        sql = review_module._build_review_query(
            "SKU'123",
            datetime(2026, 7, 1),
            3,
        )

        self.assertIn("N'SKU''123'", sql)
        self.assertIn("XingJi <= 3", sql)

    def test_attribute_queries_join_zidian_with_whitelisted_columns(self):
        expected_columns = {
            "category": "fenlei1",
            "factory": "gongyingshang",
            "remark": "maoxing",
        }

        for filter_type, column in expected_columns.items():
            with self.subTest(filter_type=filter_type):
                sql = review_module._build_review_query(
                    "值'一",
                    datetime(2026, 7, 1),
                    3,
                    filter_type,
                )

                self.assertIn("FROM zidian AS zd WITH (NOLOCK)", sql)
                self.assertIn("zd.sku = pj.SKU", sql)
                self.assertIn(f"zd.[{column}]", sql)
                self.assertIn("CHARINDEX", sql)
                self.assertIn("N'值''一'", sql)
                self.assertIn(
                    f"COALESCE(CAST(zd.[{column}] AS NVARCHAR(500)), N'')",
                    sql,
                )
                self.assertNotIn(") = N'值''一'", sql)
                self.assertNotIn("%", sql)

    def test_attribute_filters_are_text_inputs_without_option_loading(self):
        self.assertNotIn('id="attribute_filter_value"', REVIEW_TEMPLATE_SOURCE)
        self.assertNotIn("loadReviewFilterOptions", REVIEW_TEMPLATE_SOURCE)
        self.assertNotIn("/api/review_analysis/filter_options", REVIEW_TEMPLATE_SOURCE)
        self.assertIn("请输入分类关键词", REVIEW_TEMPLATE_SOURCE)
        self.assertIn("请输入生产工厂关键词", REVIEW_TEMPLATE_SOURCE)
        self.assertIn("请输入毛型或备注关键词", REVIEW_TEMPLATE_SOURCE)

    def test_filter_option_queries_use_distinct_zidian_values(self):
        expected_columns = {
            "category": "fenlei1",
            "factory": "gongyingshang",
            "remark": "maoxing",
        }

        for filter_type, column in expected_columns.items():
            with self.subTest(filter_type=filter_type):
                sql = review_module._build_review_filter_options_query(filter_type)
                self.assertIn("SELECT DISTINCT", sql)
                self.assertIn(f"CAST([{column}] AS NVARCHAR(500))", sql)
                self.assertIn("FROM zidian WITH (NOLOCK)", sql)

        with self.assertRaises(ValueError):
            review_module._build_review_filter_options_query("sku")
        with self.assertRaises(ValueError):
            review_module._build_review_filter_options_query("unsafe_column")

    def test_filter_options_api_returns_trimmed_unique_values(self):
        app = Flask(__name__)
        captured = {}

        def fake_sf_db(sql):
            captured["sql"] = sql
            return [" 工厂A ", "工厂A", "工厂B", None, ""]

        with app.test_request_context(
            "/api/review_analysis/filter_options?filter_type=factory"
        ):
            with patch.object(review_module.bjc, "sf_db", side_effect=fake_sf_db):
                response = review_module.review_filter_options.__wrapped__()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["options"], ["工厂A", "工厂B"])
        self.assertIn("[gongyingshang]", captured["sql"])

    def test_review_chart_data_uses_all_rows_for_summary_and_charts(self):
        def review_row(review_date, shop, rating):
            row = [None] * 21
            row[1] = review_date
            row[2] = shop
            row[5] = rating
            return tuple(row)

        reviews = [
            review_row(datetime(2026, 7, 2), "店铺A", 1),
            review_row(datetime(2026, 7, 8), "店铺A", 3),
            review_row(datetime(2026, 8, 1), "店铺B", 5),
            review_row("2026-08-20", "店铺B", 5),
        ]

        chart_data = review_module._build_review_chart_data(reviews)

        self.assertEqual(chart_data["summary"]["review_count"], 4)
        self.assertEqual(chart_data["summary"]["average_rating"], 3.5)
        self.assertEqual(chart_data["summary"]["negative_count"], 2)
        self.assertEqual(chart_data["summary"]["negative_rate"], 50.0)
        self.assertEqual(chart_data["summary"]["shop_count"], 2)
        self.assertEqual(
            chart_data["rating_distribution"],
            [
                {"rating": 1, "count": 1},
                {"rating": 2, "count": 0},
                {"rating": 3, "count": 1},
                {"rating": 4, "count": 0},
                {"rating": 5, "count": 2},
            ],
        )
        self.assertEqual(
            chart_data["monthly_trend"],
            [
                {"month": "2026-07", "count": 2, "average_rating": 2.0},
                {"month": "2026-08", "count": 2, "average_rating": 5.0},
            ],
        )
        self.assertEqual(
            chart_data["shop_distribution"],
            [
                {"shop": "店铺A", "count": 2},
                {"shop": "店铺B", "count": 2},
            ],
        )

    def test_successful_analysis_returns_chart_data(self):
        row = [None] * 21
        row[1] = datetime(2026, 8, 20)
        row[2] = "店铺A"
        row[5] = 2
        row[7] = "Poor quality"
        row[8] = "质量较差"

        with patch.object(review_module.bjc, "sf_db", return_value=[tuple(row)]):
            with patch.object(review_module, "local_analysis", return_value="分析结果"):
                with patch.object(review_module, "save_analysis_record"):
                    result = review_module.analyze_negative_reviews(
                        "SKU-123",
                        months_limit=3,
                        max_rating=3,
                        use_local=True,
                    )

        self.assertTrue(result["success"])
        self.assertEqual(result["chart_data"]["summary"]["review_count"], 1)
        self.assertEqual(result["chart_data"]["summary"]["negative_count"], 1)

    def test_negative_review_analysis_passes_safe_query_to_database(self):
        captured = {}

        def fake_sf_db(sql):
            captured["sql"] = sql
            return []

        with patch.object(review_module.bjc, "sf_db", side_effect=fake_sf_db):
            result = review_module.analyze_negative_reviews(
                "B0TEST123",
                months_limit=3,
                max_rating=3,
                use_local=True,
            )

        self.assertFalse(result["success"])
        self.assertIn("CHARINDEX", captured["sql"])
        self.assertNotIn("%", captured["sql"])

    def test_analyze_reviews_passes_selected_filter_to_analysis(self):
        app = Flask(__name__)
        with app.test_request_context(
            "/analyze_reviews",
            method="POST",
            json={
                "filter_type": "factory",
                "filter_value": "生产工厂A",
                "months_limit": 6,
                "max_rating": 2,
                "use_local": True,
            },
        ):
            with patch.object(
                review_module,
                "analyze_negative_reviews",
                return_value={"success": True},
            ) as analyze_mock:
                response = review_module.analyze_reviews.__wrapped__()

        self.assertTrue(response.get_json()["success"])
        analyze_mock.assert_called_once_with("生产工厂A", 6, 2, True, "factory")

    def test_analyze_reviews_keeps_legacy_product_identifier_payload(self):
        app = Flask(__name__)
        with app.test_request_context(
            "/analyze_reviews",
            method="POST",
            json={"product_identifier": "SKU-123"},
        ):
            with patch.object(
                review_module,
                "analyze_negative_reviews",
                return_value={"success": True},
            ) as analyze_mock:
                response = review_module.analyze_reviews.__wrapped__()

        self.assertTrue(response.get_json()["success"])
        analyze_mock.assert_called_once_with("SKU-123", 3, 3, False, "sku")

    def test_word_frequency_analysis_passes_safe_query_to_database(self):
        app = Flask(__name__)
        captured = {}

        def fake_sf_db(sql):
            captured["sql"] = sql
            return []

        with app.test_request_context(
            "/analyze_word_freq",
            method="POST",
            json={
                "product_identifier": "B0TEST123",
                "months_limit": 3,
                "max_rating": 3,
            },
        ):
            with patch.object(review_module.bjc, "sf_db", side_effect=fake_sf_db):
                response = review_module.analyze_word_freq.__wrapped__()

        self.assertTrue(response.get_json()["success"])
        self.assertIn("CHARINDEX", captured["sql"])
        self.assertNotIn("%", captured["sql"])

    def test_word_frequency_analysis_supports_category_filter(self):
        app = Flask(__name__)
        captured = {}

        def fake_sf_db(sql):
            captured["sql"] = sql
            return []

        with app.test_request_context(
            "/analyze_word_freq",
            method="POST",
            json={
                "filter_type": "category",
                "filter_value": "假睫毛",
                "months_limit": 3,
                "max_rating": 3,
            },
        ):
            with patch.object(review_module.bjc, "sf_db", side_effect=fake_sf_db):
                response = review_module.analyze_word_freq.__wrapped__()

        self.assertTrue(response.get_json()["success"])
        self.assertIn("zd.[fenlei1]", captured["sql"])
        self.assertIn("N'假睫毛'", captured["sql"])

    def test_all_review_export_query_filters_exact_product_without_date_filter(self):
        sql = review_module._build_all_review_export_query("SKU'123")

        for column in review_module._REVIEW_EXPORT_SOURCE_COLUMNS:
            self.assertIn(f"[{column}]", sql)
        self.assertIn("COALESCE(SKU, '') = N'SKU''123'", sql)
        self.assertIn("COALESCE(ASIN, '') = N'SKU''123'", sql)
        self.assertNotIn("RiQi >=", sql)
        self.assertIn("ORDER BY RiQi DESC, ID DESC", sql)

    def test_export_all_review_history_returns_excel_with_all_fields(self):
        app = Flask(__name__)
        review = (
            "=潜在公式",
            "产品很好",
            datetime(2026, 8, 24, 10, 30),
            "https://example.com/review/1",
            "SKU-123",
            "B0TEST123",
            "Buyer",
            "buyer@example.com",
        )

        captured = {}

        def fake_sf_db(sql):
            captured["sql"] = sql
            return [review]

        with app.test_request_context(
            "/api/review_analysis/export_all_history?product_identifier=SKU-123"
        ):
            with patch.object(review_module.bjc, "sf_db", side_effect=fake_sf_db):
                response = review_module.export_all_review_history.__wrapped__()

        self.assertEqual(response.status_code, 200)
        self.assertIn(".xlsx", response.headers["Content-Disposition"])
        self.assertIn("COALESCE(SKU, '') = N'SKU-123'", captured["sql"])

        response.direct_passthrough = False
        workbook = load_workbook(BytesIO(response.get_data()), read_only=True, data_only=False)
        worksheet = workbook["历史评论"]
        rows = list(worksheet.iter_rows(values_only=True))
        self.assertEqual(rows[0], tuple(review_module._REVIEW_EXPORT_HEADERS))
        self.assertEqual(len(rows[1]), len(review_module._REVIEW_EXPORT_HEADERS))
        self.assertEqual(rows[1][0], "产品很好\n=潜在公式")
        self.assertEqual(rows[1][3:7], ("SKU-123", "B0TEST123", "Buyer", "buyer@example.com"))

    def test_export_all_review_history_returns_404_when_empty(self):
        app = Flask(__name__)

        with app.test_request_context(
            "/api/review_analysis/export_all_history?product_identifier=SKU-404"
        ):
            with patch.object(review_module.bjc, "sf_db", return_value=[]):
                response, status = review_module.export_all_review_history.__wrapped__()

        self.assertEqual(status, 404)
        self.assertIn("SKU-404", response.get_json()["message"])

    def test_export_all_review_history_requires_product_identifier(self):
        app = Flask(__name__)

        with app.test_request_context("/api/review_analysis/export_all_history"):
            response, status = review_module.export_all_review_history.__wrapped__()

        self.assertEqual(status, 400)
        self.assertEqual(response.get_json()["message"], "请先输入要导出的 SKU 或 ASIN")


if __name__ == "__main__":
    unittest.main()
