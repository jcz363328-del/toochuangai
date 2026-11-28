"""Daily snapshots for the shared innovation homepage statistics."""

from calendar import monthrange
from datetime import datetime, timedelta, timezone
from threading import Event, Thread

from flask import current_app, request

SHANGHAI = timezone(timedelta(hours=8))
EXTENSION = 'innovation_home_snapshots'


def monthly_query(now):
    start = now.date().replace(day=1)
    end = start.replace(day=monthrange(start.year, start.month)[1])
    return {'start_date': start.isoformat(), 'end_date': end.isoformat()}


def read_snapshot(endpoint):
    if request.args.get('refresh') == '1':
        return None
    query = {'homepage': '1'}
    if endpoint == 'dashboard':
        query = monthly_query(datetime.now(SHANGHAI))
    if request.args.to_dict(flat=False) != {key: [value] for key, value in query.items()}:
        return None
    return current_app.extensions.get(EXTENSION, {}).get((endpoint, tuple(query.items())))


def warm_snapshots(app, now):
    from innovation.web_app import get_dashboard_data, get_statistics

    snapshots = {}
    previous = app.extensions.get(EXTENSION, {})
    for endpoint, query, handler in (
        ('statistics', {'homepage': '1'}, get_statistics),
        ('dashboard', monthly_query(now), get_dashboard_data),
    ):
        key = (endpoint, tuple(query.items()))
        try:
            with app.test_request_context(query_string={**query, 'refresh': '1'}):
                response = app.make_response(handler())
                payload = response.get_json()
                if response.status_code != 200 or not payload or payload.get('success') is not True:
                    raise RuntimeError(f'Invalid snapshot response (HTTP {response.status_code})')
                snapshots[key] = payload
        except Exception:
            app.logger.exception('Could not warm innovation homepage %s snapshot', endpoint)
            if key in previous:
                snapshots[key] = previous[key]
    app.extensions[EXTENSION] = snapshots


def start_home_snapshot_worker(app):
    def run():
        while True:
            now = datetime.now(SHANGHAI)
            next_run = now.replace(hour=7, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            warm_snapshots(app, now)
            Event().wait(max(0, (next_run - datetime.now(SHANGHAI)).total_seconds()))

    Thread(target=run, name='innovation-home-snapshots', daemon=True).start()
