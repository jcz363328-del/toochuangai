import concurrent.futures
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, '/app')
from 图片 import openrouter_image_site as site
from 图片.omnia_key_pool import load_omnia_api_keys, credential_fingerprint
from 图片.omnia_service import get_cost_ledger

keys = load_omnia_api_keys(site.load_omnia_api_key())
by_fingerprint = {credential_fingerprint(key): key for key in keys}
channels = {credential_fingerprint(key): index + 1 for index, key in enumerate(keys)}
ledger = get_cost_ledger()
db = sqlite3.connect(ledger.db_path)
db.row_factory = sqlite3.Row
saved = {row['fingerprint']: dict(row) for row in db.execute('SELECT * FROM key_usage')}
calls = [dict(row) for row in db.execute('SELECT * FROM calls ORDER BY rowid DESC LIMIT 10')]
db.close()

def usage(key):
    fingerprint = credential_fingerprint(key)
    started = time.monotonic()
    result = {'channel': channels[fingerprint], 'recorded_error': bool(saved[fingerprint]['error']),
              'updated_at': saved[fingerprint]['updated_at']}
    try:
        response = site.requests.get(site.OMNIAKEY_API_BASE + '/v1/dashboard/billing/usage',
            headers={'Authorization': 'Bearer ' + key}, timeout=(5, 12), allow_redirects=False)
        result['http'] = response.status_code
        if response.status_code == 200:
            value = Decimal(str(response.json()['total_usage'])) / 100
            result['difference_percent'] = str(value - Decimal(saved[fingerprint]['current_usd']))
    except Exception as exc:
        result['error_type'] = type(exc).__name__
    result['seconds'] = round(time.monotonic() - started, 2)
    return result

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    print(json.dumps({'usage': list(executor.map(usage, keys))}, ensure_ascii=False))

for call in calls:
    summary = {'task': call['task_id'][:16], 'channel': channels.get(call['key_fingerprint']),
               'outcome': call['outcome'], 'billing': call['billing_status'],
               'created_at': call['created_at'], 'finished_at': call['finished_at']}
    if call['task_id'] and call['outcome'] == 'uncertain':
        try:
            response = site.requests.get(site.OMNIAKEY_MEDIA_TASKS_URL + '/' + call['task_id'],
                headers={'Authorization': 'Bearer ' + by_fingerprint[call['key_fingerprint']]},
                timeout=(5, 12), allow_redirects=False)
            summary['task_http'] = response.status_code
            if response.status_code == 200:
                data = response.json()
                summary['provider_status'] = data.get('status')
                summary['asset_count'] = len(data.get('assets') or [])
                error = data.get('error')
                if isinstance(error, dict):
                    summary['provider_error_code'] = str(error.get('code') or '')[:80]
        except Exception as exc:
            summary['task_error_type'] = type(exc).__name__
    print(json.dumps(summary, ensure_ascii=False))
print(json.dumps({'snapshot': ledger.snapshot()}, ensure_ascii=False))
