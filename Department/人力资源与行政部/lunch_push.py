"""Daily lunch cards, persisted delivery receipts and an in-process scheduler."""
import argparse
from copy import deepcopy
from contextlib import closing
from datetime import datetime, time, timedelta
import json
import logging
import os
from pathlib import Path
import sqlite3
from threading import Event, Lock, Thread
import uuid
from zoneinfo import ZoneInfo

import pytds
import requests

from lunch_feishu_cards import SQL, build_card
from secret_settings import get_feishu_message_config, sql_server_config

TZ = ZoneInfo('Asia/Shanghai')
ROOT = Path(__file__).resolve().parents[2]
GROUPS = {
    'all': ('图创星链（青岛）创新科技有限公司', 'oc_3674213c39e3ab537603d69e09307b91'),
    'tk': ('图创——内容生产工厂', 'oc_ad7ea614fe87f4e74b1ee3283c3d801d'),
}
LOG = logging.getLogger(__name__)


def now_local():
    return datetime.now(TZ)


def next_trigger(now=None):
    now = (now or now_local()).astimezone(TZ)
    trigger = now.replace(hour=9, minute=25, second=0, microsecond=0)
    return trigger if now < trigger else trigger + timedelta(days=1)


def is_due(now):
    local = now.astimezone(TZ)
    # A bounded retry window prevents a late restart from sending lunch notices at night.
    return time(9, 25) <= local.time() < time(10)


class LunchPush:
    def __init__(self, storage=None):
        base = Path(os.environ.get('TUCHUANGAI_STORAGE_ROOT') or ROOT / 'outputs')
        self.storage = Path(storage) if storage else base / 'lunch_push'
        self._start_lock = Lock()
        self._thread = None
        self.last_error = ''

    def connect(self):
        self.storage.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.storage / 'delivery.sqlite3', timeout=300)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS delivery (
            day TEXT NOT NULL, scope TEXT NOT NULL, meal TEXT NOT NULL,
            recipient TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL,
            count INTEGER NOT NULL, message_id TEXT, error TEXT, updated_at TEXT NOT NULL,
            PRIMARY KEY(day,scope,meal,recipient))''')
        conn.commit()
        return conn

    def preview(self, day=None, test=False):
        day = day or now_local().date()
        with pytds.connect(**sql_server_config(), login_timeout=10, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute(SQL, (day, day))
            rows = cursor.fetchall()
        entries = []
        for scope in ('all', 'tk'):
            for meal in ('堂食', '盒饭'):
                directory = self.storage / 'images' / day.isoformat()
                card, count = build_card(rows, day.isoformat(), meal, scope == 'tk',
                                         test=test, output_dir=directory)
                entries.append({'scope': scope, 'meal': meal, 'count': count,
                                'group': GROUPS[scope][0], 'recipient': GROUPS[scope][1],
                                'image': f'{scope}_{meal}_grid.png' if count else None,
                                'card': card})
        return entries

    def token(self):
        response = requests.post('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                                 json=get_feishu_message_config(), timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get('code') != 0 or not data.get('tenant_access_token'):
            raise RuntimeError(f"飞书认证失败：{data.get('code')} {data.get('msg')}")
        return data['tenant_access_token']

    def validate_groups(self):
        headers = {'Authorization': 'Bearer ' + self.token()}
        names = []
        for expected, chat_id in GROUPS.values():
            response = requests.get('https://open.feishu.cn/open-apis/im/v1/chats/' + chat_id,
                                    headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            if data.get('code') != 0 or data.get('data', {}).get('name') != expected:
                raise RuntimeError(f'无法核对目标群：{expected}')
            names.append(expected)
        return names

    def send_card(self, entry, recipient, token, dedupe_key):
        card = deepcopy(entry['card'])
        headers = {'Authorization': 'Bearer ' + token}
        for element in card['body']['elements']:
            if element['tag'] == 'img':
                with open(element['img_key'], 'rb') as image_file:
                    response = requests.post('https://open.feishu.cn/open-apis/im/v1/images',
                        headers=headers, data={'image_type': 'message'},
                        files={'image': image_file}, timeout=30)
                response.raise_for_status()
                data = response.json()
                if data.get('code') != 0:
                    raise RuntimeError(f"表格图片上传失败：{data.get('msg')}")
                element['img_key'] = data['data']['image_key']
        response = requests.post('https://open.feishu.cn/open-apis/im/v1/messages',
            params={'receive_id_type': 'chat_id' if recipient.startswith('oc_') else 'open_id'},
            headers=headers, timeout=30, json={'receive_id': recipient, 'msg_type': 'interactive',
                'content': json.dumps(card, ensure_ascii=False),
                'uuid': str(uuid.uuid5(uuid.NAMESPACE_URL, dedupe_key))})
        data = response.json()
        if data.get('code') != 0:
            raise RuntimeError(f"飞书发送失败：{data.get('code')} {data.get('msg')}")
        response.raise_for_status()
        return data['data']['message_id']

    def run_once(self, test=False, preview_to_zhou=False):
        day = now_local().date()
        recipient_override = None
        if test or preview_to_zhou:
            with pytds.connect(**sql_server_config(), login_timeout=10, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT DISTINCT FeiShu_ID FROM feishu_id WHERE YONGHU=%s', ('周俊成',))
                ids = [r[0] for r in cursor.fetchall() if r[0] and r[0].startswith('ou_')]
            if len(ids) != 1:
                raise RuntimeError('周俊成的接收账号不唯一')
            recipient_override = ids[0]
        entries = self.preview(day, test=test)
        token = None
        results = []
        with closing(self.connect()) as conn:
            for entry in entries:
                recipient = recipient_override or entry['recipient']
                key = (day.isoformat(), entry['scope'], entry['meal'], recipient)
                conn.execute('BEGIN IMMEDIATE')
                prior = conn.execute('SELECT * FROM delivery WHERE day=? AND scope=? AND meal=? AND recipient=?', key).fetchone()
                if prior and (prior['status'] == 'sent' or prior['attempts'] >= 5):
                    conn.commit()
                    results.append({'scope': entry['scope'], 'meal': entry['meal'], 'status': 'skipped'})
                    continue
                attempts = (prior['attempts'] if prior else 0) + 1
                message_id, error, status = '', '', 'sent'
                try:
                    token = token or self.token()
                    message_id = self.send_card(entry, recipient, token, 'lunch:' + ':'.join(key))
                except Exception as exc:
                    error, status = str(exc), 'failed'
                    LOG.exception('Lunch push failed: %s %s', entry['scope'], entry['meal'])
                conn.execute('INSERT OR REPLACE INTO delivery VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (*key, status, attempts, entry['count'], message_id, error, now_local().isoformat()))
                conn.commit()
                results.append({'scope': entry['scope'], 'meal': entry['meal'], 'status': status,
                                'message_id': message_id, 'error': error})
        return results

    def records(self):
        with closing(self.connect()) as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM delivery ORDER BY updated_at DESC LIMIT 40')]

    def _loop(self):
        while True:
            try:
                if is_due(now_local()):
                    self.run_once()
                self.last_error = ''
            except Exception as exc:
                self.last_error = str(exc)
                LOG.exception('Lunch scheduler failed')
            Event().wait(30)

    def start(self):
        if os.environ.get('LUNCH_PUSH_ENABLED', '1') != '1':
            return False
        with self._start_lock:
            if not self._thread or not self._thread.is_alive():
                self._thread = Thread(target=self._loop, name='lunch-push', daemon=True)
                self._thread.start()
        return True


lunch_push = LunchPush()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--preview-to-zhou', action='store_true',
                        help='Send unmodified production cards to 周俊成 instead of the groups')
    parser.add_argument('--validate-groups', action='store_true')
    args = parser.parse_args()
    if args.serve:
        lunch_push.start()
        Event().wait()
    elif args.validate_groups:
        print(json.dumps(lunch_push.validate_groups(), ensure_ascii=False))
    elif args.send:
        print(json.dumps(lunch_push.run_once(test=args.test, preview_to_zhou=args.preview_to_zhou), ensure_ascii=False))
    else:
        print(json.dumps([{k: v for k, v in entry.items() if k != 'card'}
                          for entry in lunch_push.preview(test=args.test)], ensure_ascii=False))
