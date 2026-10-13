from datetime import date, timedelta

from business_analysis_store_tier_promotion import detect_promotions


START = date(2026, 1, 1)


def rows_for(ranks, store=4):
    return [
        (START + timedelta(days=index), store, f"等级{rank}", rank)
        for index, rank in enumerate(ranks)
    ]


def test_promotes_after_30_uninterrupted_days_above_historical_high():
    events = detect_promotions(rows_for([1] * 5 + [2] * 30), {START + timedelta(days=34)})
    assert len(events) == 1
    assert events[0].tier_rank == 2
    assert events[0].streak_started_on == START + timedelta(days=5)
    assert events[0].consecutive is False


def test_drop_during_window_prevents_promotion():
    ranks = [1] * 5 + [2] * 15 + [1] + [2] * 14
    events = detect_promotions(rows_for(ranks), {START + timedelta(days=len(ranks) - 1)})
    assert events == []


def test_return_to_historical_high_is_not_a_promotion():
    ranks = [3] + [1] * 5 + [3] * 30
    events = detect_promotions(rows_for(ranks), {START + timedelta(days=len(ranks) - 1)})
    assert events == []


def test_missing_calendar_day_breaks_streak():
    rows = rows_for([2] * 30)
    del rows[10]
    assert detect_promotions(rows, {START + timedelta(days=29)}) == []


def test_second_new_high_is_marked_as_consecutive_promotion():
    ranks = [1] * 5 + [2] * 30 + [3] * 30
    events = detect_promotions(rows_for(ranks), {START + timedelta(days=64)})
    assert len(events) == 1
    assert events[0].tier_rank == 3
    assert events[0].consecutive is True


def test_higher_days_inside_window_still_qualify_at_window_floor():
    ranks = [1] * 5 + [2] * 10 + [3] * 10 + [2] * 10
    events = detect_promotions(rows_for(ranks), {START + timedelta(days=34)})
    assert len(events) == 1
    assert events[0].tier_rank == 2
