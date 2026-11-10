from datetime import date

import historical_sales as module


def test_parse_range_rejects_invalid_order():
    try:
        module._parse_range("2026-03-02", "2026-03-01")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_previous_year_handles_leap_day():
    assert module._previous_year(date(2024, 2, 29)) == date(2023, 2, 28)


def test_historical_sales_uses_dedicated_permission_key():
    assert module.PERMISSION_KEY == "historical_sales"


def test_build_comparison_aligns_current_and_previous(monkeypatch):
    values = {
        date(2026, 3, 1): 10,
        date(2026, 3, 2): 20,
        date(2025, 3, 1): 5,
        date(2025, 3, 2): 10,
    }
    monkeypatch.setattr(module, "_query_daily_sales", lambda start, end: {d: v for d, v in values.items() if start <= d <= end})
    result = module.build_comparison(date(2026, 3, 1), date(2026, 3, 2))
    assert result["current_total"] == 30
    assert result["previous_total"] == 15
    assert result["growth"] == 1
    assert result["points"][0] == {"date": "2026-03-01", "previous_date": "2025-03-01", "current": 10, "previous": 5}
