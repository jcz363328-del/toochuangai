import unittest
from datetime import datetime
from unittest.mock import patch

from flask import Flask

import review_analysis as review_module


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


if __name__ == "__main__":
    unittest.main()
