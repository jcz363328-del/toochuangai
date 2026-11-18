"""Preview and safely retry recorded promotion notifications, including historical awards."""
import json
import uuid

import pytds
import requests

from business_analysis_store_tier_promotion import DEFAULT_RECIPIENTS
from secret_settings import sql_server_config


def _connect():
    return pytds.connect(**sql_server_config(), timeout=60)


def _records(cursor, start, end, store=None):
    sql = '''SELECT XuHao,DianPu,RiQi,YuanDengJi,XinDengJi,YunYing,
                    FaSongZhuangTai,FaSongShiJian,FaSongBeiZhu
               FROM dbo.DianPuJinJi WHERE RiQi >= %s AND RiQi <= %s AND DianPu <> 55'''
    params = [start, end]
    if store is not None:
        sql += ' AND DianPu=%s'
        params.append(store)
    cursor.execute(sql + ' ORDER BY RiQi DESC,XuHao DESC', tuple(params))
    keys = ('id', 'store', 'date', 'previousTier', 'tier', 'operator', 'status', 'sentAt', 'note')
    return [dict(zip(keys, row)) for row in cursor.fetchall()]


def message_for(record):
    return (
        '【🎉 店铺晋级喜报（历史补发）🎉】\n'
        f"店铺：{record['store']}号店\n店铺负责人：{record['operator'] or '—'}\n"
        f"🏆 晋级层级：{record['previousTier']} → {record['tier']}\n"
        f"📅 晋级记录日期：{str(record['date'])[:10]}\n\n"
        '本条按历史晋级台账补发，记录的是此前已达成的成绩；'
        '店铺之后可能发生等级变化，本条不代表当前等级。'
    )


def preview_backfill(start, end, store=None):
    with _connect() as conn:
        rows = _records(conn.cursor(), start, end, store)
    for row in rows:
        row['date'] = str(row['date'])[:10]
        row['sentAt'] = str(row['sentAt']) if row['sentAt'] else None
        row['status'] = row['status'] or '未发送'
        row['message'] = message_for(row)
        row['canSend'] = row['status'] in {'未发送', '发送失败', '部分失败'}
    return {'rows': rows, 'recipients': list(DEFAULT_RECIPIENTS)}


def pending_recipients(status, note, attempts):
    """Never infer success after an interrupted send or a truncated legacy error."""
    if status == '已发送':
        return []
    if status == '发送中' or any(v['status'] in {'发送中', '待核实'} for v in attempts.values()):
        raise ValueError('有发送结果待核实，请先核对飞书消息，避免重复发送')
    if status == '部分失败' and not attempts:
        raise ValueError('旧记录缺少逐人发送结果，请先核实接收人，避免重复发送')
    if status not in {None, '', '未发送', '发送失败', '部分失败'}:
        raise ValueError('当前通知状态不可补发，请先核实发送记录')
    return [name for name in DEFAULT_RECIPIENTS if attempts.get(name, {}).get('status') != '已发送']


def send_backfill(record_id):
    from innovation.message_service import MessageService

    with _connect() as conn:
        c = conn.cursor()
        # A session lock also protects against concurrent clicks across workers.
        resource = f'promotion-backfill:{record_id}'
        c.execute("DECLARE @r int; EXEC @r=sys.sp_getapplock @Resource=%s,@LockMode='Exclusive',@LockOwner='Session',@LockTimeout=0; SELECT @r", (resource,))
        if c.fetchone()[0] < 0:
            raise ValueError('该通知正在补发，请稍后刷新')
        try:
            c.execute('''IF OBJECT_ID('dbo.DianPuJinJiRecipientSend','U') IS NULL
                CREATE TABLE dbo.DianPuJinJiRecipientSend (
                    RecordID int NOT NULL, Recipient nvarchar(50) NOT NULL,
                    Status nvarchar(20) NOT NULL, MessageID nvarchar(100) NULL,
                    Detail nvarchar(500) NULL, UpdatedAt datetime2 NOT NULL DEFAULT SYSDATETIME(),
                    PRIMARY KEY (RecordID,Recipient))''')
            conn.commit()
            c.execute('SELECT RiQi,DianPu FROM dbo.DianPuJinJi WHERE XuHao=%s', (record_id,))
            key = c.fetchone()
            if not key or int(key[1]) == 55:
                raise ValueError('晋级记录不存在或不可补发')
            record = next(r for r in _records(c, key[0], key[0], key[1]) if r['id'] == record_id)
            c.execute('SELECT Recipient,Status,MessageID FROM dbo.DianPuJinJiRecipientSend WHERE RecordID=%s', (record_id,))
            attempts = {n: {'status': s, 'messageId': mid} for n, s, mid in c.fetchall()}
            targets = pending_recipients(record['status'], record['note'], attempts)
            if not targets:
                return {'sent': 0, 'failed': 0, 'status': '已发送', 'message': '已发送，已跳过重复补发'}
            service = MessageService('company1')
            token = service._get_access_token()
            if not token:
                raise RuntimeError('获取飞书访问凭证失败')
            # Resolve every target before performing any send.
            ids = {}
            for name in targets:
                c.execute('SELECT FeiShu_ID FROM feishu_id WHERE YONGHU=%s', (name,))
                matches = {str(r[0]) for r in c.fetchall() if r[0]}
                if len(matches) != 1:
                    raise ValueError(f'{name}的飞书接收人不唯一或不存在')
                ids[name] = matches.pop()
            sent = failed = 0
            for name in targets:
                c.execute('DELETE FROM dbo.DianPuJinJiRecipientSend WHERE RecordID=%s AND Recipient=%s', (record_id, name))
                c.execute("INSERT INTO dbo.DianPuJinJiRecipientSend (RecordID,Recipient,Status) VALUES (%s,%s,N'发送中')", (record_id, name))
                conn.commit()
                mid = None
                try:
                    response = requests.post('https://open.feishu.cn/open-apis/im/v1/messages',
                        params={'receive_id_type': service.detect_type(ids[name])},
                        headers={'Authorization': f'Bearer {token}'},
                        json={'receive_id': ids[name], 'msg_type': 'text',
                              'content': json.dumps({'text': message_for(record)}, ensure_ascii=False),
                              'uuid': str(uuid.uuid5(uuid.NAMESPACE_URL, resource + ':' + name))}, timeout=30)
                    data = response.json()
                    mid = (data.get('data') or {}).get('message_id')
                    status = '已发送' if data.get('code') == 0 and mid else '发送失败'
                    detail = str(data.get('msg') or '')[:500]
                except Exception:
                    status, detail = '待核实', '请求中断，可能已送达，请核实飞书消息后处理'
                attempts[name] = {'status': status, 'messageId': mid}
                sent += status == '已发送'
                failed += status != '已发送'
                c.execute('UPDATE dbo.DianPuJinJiRecipientSend SET Status=%s,MessageID=%s,Detail=%s,UpdatedAt=SYSDATETIME() WHERE RecordID=%s AND Recipient=%s', (status, mid, detail, record_id, name))
                outstanding = [n for n in DEFAULT_RECIPIENTS if attempts.get(n, {}).get('status') != '已发送']
                overall = '已发送' if not outstanding else '部分失败'
                c.execute('UPDATE dbo.DianPuJinJi SET FaSongDuiXiang=%s,FaSongZhuangTai=%s,FaSongShiJian=SYSDATETIME(),FaSongBeiZhu=%s WHERE XuHao=%s',
                    ('；'.join(DEFAULT_RECIPIENTS), overall, '历史补发；未成功：' + '；'.join(outstanding) if outstanding else '历史补发：全部成功', record_id))
                conn.commit()
            return {'sent': sent, 'failed': failed, 'status': overall}
        finally:
            c.execute("EXEC sys.sp_releaseapplock @Resource=%s,@LockOwner='Session'", (resource,))
            conn.commit()
