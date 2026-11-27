"""Read-only shipping suggestions using the fixed 2026-11-27 P90 reference."""
from datetime import date, timedelta
import json
import math
from pathlib import Path

REFERENCE = json.loads(Path(__file__).with_name('shipping_p90_reference.json').read_text(encoding='utf-8'))
MIN_SAMPLES = 5
HANDOFF_DAYS = 1  # A visible minimum handoff margin, not a guarantee of FBA availability.


def recommend(country, sellable, daily, *, today=None):
    today = today or date.today()
    sellable, daily = max(0, float(sellable)), max(0, float(daily))
    all_routes = [r for r in REFERENCE['routes'] if r['country'] == country]
    routes = [r for r in all_routes if r['samples'] >= MIN_SAMPLES]
    monday_wait = (0 - today.weekday()) % 7
    monday = today + timedelta(days=monday_wait)
    result = {'country': country, 'sellable': sellable, 'daily': daily,
              'coverage_days': round(sellable / daily, 1) if daily else None,
              'monday': monday.isoformat(), 'monday_wait': monday_wait,
              'routes': routes, 'all_routes': all_routes, 'handoff_days': HANDOFF_DAYS,
              'bridge_qty': 0, 'tone': 'neutral', 'kind': 'unavailable'}
    if daily <= 0:
        result['message'] = '近期无销量，暂不推荐发货'
        return result
    coverage = sellable / daily
    sea = next((r for r in routes if r['method'] == '海运'), None)
    fast = sorted([r for r in routes if '海运' not in r['method']], key=lambda r: (r['p90_days'], -r['samples']))
    viable = [r for r in fast if r['p90_days'] + HANDOFF_DAYS <= coverage]
    if not sea:
        result['message'] = '暂无足够海运样本'
        if viable:
            result.update(kind='express_only', method=viable[0], message='可参考快线，海运样本不足')
        elif fast:
            result.update(kind='risk', method=fast[0], tone='danger', message='最快参考线路也可能接不上库存')
        return result
    sea_days = monday_wait + sea['p90_days']
    result.update(sea=sea, sea_arrival=(today + timedelta(days=sea_days)).isoformat(), sea_total_days=sea_days)
    if coverage >= sea_days + HANDOFF_DAYS:
        deadline = today + timedelta(days=math.floor(coverage - sea['p90_days'] - HANDOFF_DAYS))
        latest_monday = deadline - timedelta(days=deadline.weekday())
        result.update(kind='sea', tone='ok', message='优先海运', latest_monday=latest_monday.isoformat())
    elif viable:
        bridge_qty = math.ceil(max(0, daily * (sea_days + HANDOFF_DAYS) - sellable))
        result.update(kind='bridge', tone='warn', method=viable[0], bridge_qty=bridge_qty,
                      message='少量快线衔接，其余海运')
    else:
        result.update(kind='risk', tone='danger', method=fast[0] if fast else None,
                      message='当前库存可能接不上，需人工加急')
    return result
