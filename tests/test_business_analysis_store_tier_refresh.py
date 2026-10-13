import unittest
from datetime import date

from business_analysis_store_tier_refresh import _missing_tier_dates


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


if __name__ == "__main__":
    unittest.main()
