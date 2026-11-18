"""User-authorized, idempotent backfill of store 33's historical promotion."""
import json
import uuid
from pathlib import Path

import pytds
import requests

from secret_settings import sql_server_config
from innovation.message_service import MessageService
from business_analysis_store_tier_promotion import DEFAULT_RECIPIENTS

KEY = '33:8:2026-11-04'
REPORT = Path(__file__).with_suffix('.json')
MESSAGE = '''【🎉 店铺晋级喜报（历史补发）🎉】
店铺：33号店
店铺负责人：赵羽姝
🏆 晋级层级：金1
📅 晋级确认日期：2026-11-04
⏱ 30天保持：2026-10-06 至 2026-11-04（连续保持金1及以上）

本条补发此前已达成的晋级成绩。店铺此后曾达到金2，截至2026-11-16最新层级已回落至金1；金2尚未连续保持满30天。本次补发不代表当前晋级金2。'''


def main():
    state = json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {'event': KEY, 'message': MESSAGE, 'results': {}}
    service = MessageService('company1')
    # Authenticate before creating a notification record; no message is sent here.
    token = service._get_access_token()
    if not token:
        raise RuntimeError('Failed to obtain Feishu token')
    with pytds.connect(**sql_server_config(), timeout=60) as conn:
        c = conn.cursor()
        c.execute('SELECT XuHao,FaSongZhuangTai FROM dbo.DianPuJinJi WHERE XiaoXiBiaoShi=%s', (KEY,))
        existing = c.fetchone()
        if existing and existing[1] == '已发送':
            print(json.dumps({'status': 'already-sent', 'event': KEY}, ensure_ascii=False))
            return
        if existing:
            record_id = existing[0]
        else:
            c.execute('''INSERT INTO dbo.DianPuJinJi
                (DianPu,RiQi,YuanDengJi,XinDengJi,YunYing,FaSongDuiXiang,FaSongZhuangTai,XiaoXiBiaoShi,FaSongBeiZhu)
                OUTPUT INSERTED.XuHao VALUES (33,%s,%s,%s,%s,%s,%s,%s,%s)''',
                ('2026-11-04','银4','金1','赵羽姝','；'.join(DEFAULT_RECIPIENTS),'发送中',KEY,'用户确认补发历史金1晋级；最新已从金2回落金1'))
            record_id = c.fetchone()[0]
            conn.commit()
        for name in DEFAULT_RECIPIENTS:
            if state['results'].get(name, {}).get('success'):
                continue
            c.execute('SELECT FeiShu_ID FROM feishu_id WHERE YONGHU=%s', (name,))
            ids = [str(r[0]) for r in c.fetchall() if r[0]]
            if len(set(ids)) != 1:
                raise RuntimeError(f'Ambiguous recipient: {name}')
            fid = ids[0]
            response = requests.post('https://open.feishu.cn/open-apis/im/v1/messages',
                params={'receive_id_type': service.detect_type(fid)},
                headers={'Authorization': f'Bearer {token}'},
                json={'receive_id': fid, 'msg_type': 'text',
                      'content': json.dumps({'text': MESSAGE}, ensure_ascii=False),
                      'uuid': str(uuid.uuid5(uuid.NAMESPACE_URL, KEY + ':' + name))}, timeout=30)
            payload = response.json()
            state['results'][name] = {'success': payload.get('code') == 0,
                'message_id': payload.get('data', {}).get('message_id'),
                'code': payload.get('code'), 'msg': payload.get('msg')}
            REPORT.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'recipient': name, **state['results'][name]}, ensure_ascii=False), flush=True)
        failed = [n for n in DEFAULT_RECIPIENTS if not state['results'].get(n, {}).get('success')]
        status = '已发送' if not failed else ('发送失败' if len(failed) == len(DEFAULT_RECIPIENTS) else '部分失败')
        note = '用户确认补发历史金1晋级；最新已从金2回落金1。' + ('失败：' + '；'.join(failed) if failed else '6位接收人全部发送成功。')
        c.execute('UPDATE dbo.DianPuJinJi SET FaSongZhuangTai=%s,FaSongShiJian=SYSDATETIME(),FaSongBeiZhu=%s WHERE XuHao=%s', (status,note,record_id))
        conn.commit()
        print(json.dumps({'status': status, 'event': KEY, 'record_id': record_id, 'failed': failed}, ensure_ascii=False))


if __name__ == '__main__':
    main()
