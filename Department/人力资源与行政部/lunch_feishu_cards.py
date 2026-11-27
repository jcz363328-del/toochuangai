"""Preview lunch cards; --send sends the four cards to 周俊成 only."""
import argparse
from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
import uuid
from zoneinfo import ZoneInfo

import pytds
import requests
from PIL import Image, ImageDraw, ImageFont

from secret_settings import get_feishu_message_config, sql_server_config


SQL = """
SELECT
 CASE
 WHEN cn.bumen=N'周雪' THEN N'运营一部'
 WHEN cn.bumen=N'王钰媛' THEN N'运营二部'
 WHEN cn.bumen=N'大张雯' THEN N'运营三部'
 WHEN cn.bumen=N'郭鑫' THEN N'运营六部'
 WHEN cn.bumen=N'侯瑞昕' THEN N'运营七部'
 WHEN cn.uname IN (N'侯梁',N'孙洁') THEN N'运营部'
 WHEN cn.bumen=N'宋亚倩' THEN N'TK'
 WHEN cn.bumen=N'刘蓉蓉' THEN N'运营三部'
 WHEN cn.bumen=N'美工' THEN N'设计'
 ELSE cn.bumen END AS department,
 lc.yonghu, lc.xingshi, cn.bumen
FROM Lunch lc
LEFT JOIN (SELECT uname, MAX(bumen) AS bumen FROM computername GROUP BY uname) cn
 ON cn.uname=lc.yonghu
WHERE lc.yorn='Y' AND lc.riqi >= %s AND lc.riqi < DATEADD(day,1,%s)
 AND cn.bumen<>N'教师' AND lc.XingShi IN (N'堂食',N'盒饭')
ORDER BY department,lc.yonghu
"""


def render_table(groups, path):
    width, header, cell = 1200, 72, 66
    left, middle, right = 0, 230, 360
    height = header + sum(max(1, (len(names) + 3) // 4) * cell for names in groups.values()) + 1
    image = Image.new('RGB', (width + 1, height), '#ffffff')
    draw = ImageDraw.Draw(image)
    def load_font(bold=False):
        candidates = [os.environ.get('LUNCH_FONT_BOLD' if bold else 'LUNCH_FONT', ''),
                      'C:/Windows/Fonts/msyhbd.ttc' if bold else 'C:/Windows/Fonts/msyh.ttc',
                      '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc' if bold else
                      '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                # Noto CJK collections default to Japanese; select Simplified Chinese.
                font_index = 2 if Path(candidate).name in {
                    'NotoSansCJK-Bold.ttc', 'NotoSansCJK-Regular.ttc'} else 0
                return ImageFont.truetype(candidate, 27 if bold else 26, index=font_index)
        raise RuntimeError('未找到中文字体，请配置 LUNCH_FONT / LUNCH_FONT_BOLD')
    font, bold = load_font(), load_font(True)
    border = '#cbd5e1'
    def label(box, text, strong=False):
        x0, y0, x1, y1 = box
        draw.text(((x0+x1)/2, (y0+y1)/2), text, font=bold if strong else font,
                  fill='#1e293b', anchor='mm')
    draw.rectangle((0, 0, width, header), fill='#e9eef5')
    label((left, 0, middle, header), '部门', True)
    label((middle, 0, right, header), '人数', True)
    label((right, 0, width, header), '人员明细', True)
    y = header
    department_edges = [header]
    for group_index, (department, names) in enumerate(groups.items()):
        row_count = max(1, (len(names)+3)//4)
        end = y + row_count * cell
        draw.rectangle((0, y, width, end), fill='#ffffff' if group_index % 2 == 0 else '#dbeafe')
        label((left, y, middle, end), department)
        label((middle, y, right, end), f'{len(names)} 人')
        for row_index in range(row_count):
            for col in range(4):
                index = row_index*4+col
                x0 = right + col*210
                label((x0, y+row_index*cell, x0+210, y+(row_index+1)*cell),
                      names[index] if index < len(names) else '')
            draw.line((right, y+row_index*cell, width, y+row_index*cell), fill=border, width=2)
        for col in range(1, 4):
            x = right+col*210
            draw.line((x, y, x, end), fill=border, width=2)
        draw.line((0, end, width, end), fill=border, width=2)
        department_edges.append(end)
        y = end
    for x in (0, middle, right, width):
        draw.line((x, 0, x, height), fill=border, width=2)
    draw.line((0, 0, width, 0), fill=border, width=2)
    draw.line((0, header, width, header), fill=border, width=2)
    for edge in department_edges:
        draw.line((0, edge, width, edge), fill='#94a3b8', width=3)
    temporary = path.with_name(path.stem + '-' + uuid.uuid4().hex + '.png')
    image.save(temporary)
    temporary.replace(path)


def build_card(rows, day, meal, tk, test=True, output_dir=None):
    groups = defaultdict(list)
    for department, name, form, original in rows:
        if form == meal and (not tk or original == '内容生产工厂'):
            groups[department].append(name)
    total = sum(map(len, groups.values()))
    elements = [{'tag': 'div', 'text': {'tag': 'lark_md', 'content':
        f'日期：{day}\n**订餐总人数：{total} 人**'}}]
    if groups:
        image_dir = Path(output_dir) if output_dir else Path(__file__).resolve().parents[2] / 'outputs' / 'lunch_cards' / day
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / f'{"tk" if tk else "all"}_{meal}_grid.png'
        render_table(groups, image_path)
        elements.append({'tag': 'img', 'img_key': str(image_path),
                        'alt': {'tag': 'plain_text', 'content': '部门、人数与人员分格名单'}})
    if not groups:
        elements.append({'tag': 'div', 'text': {'tag': 'plain_text', 'content': '今日暂无订餐人员'}})
    body_elements = []
    for element in elements:
        if element['tag'] == 'div':
            body_elements.append({'tag': 'markdown', 'content': element['text']['content']})
        else:
            body_elements.append(element)
    return {'schema': '2.0', 'config': {'wide_screen_mode': True},
            'header': {'template': 'orange' if tk else 'blue', 'title': {
                'tag': 'plain_text', 'content': f'今日{"TK" if tk else "整体"}{meal}订餐名单' + ('（测试）' if test else '')}},
            'body': {'elements': body_elements}}, total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send', action='store_true')
    args = parser.parse_args()
    day = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    with pytds.connect(**sql_server_config(), login_timeout=10, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT FeiShu_ID FROM feishu_id WHERE YONGHU=%s', ('周俊成',))
        recipients = [r[0] for r in cursor.fetchall() if r[0] and r[0].startswith('ou_')]
        if len(recipients) != 1:
            raise RuntimeError('周俊成接收账号不唯一或未找到，停止发送')
        cursor.execute(SQL, (day, day))
        rows = cursor.fetchall()
    cards = []
    for tk in (False, True):
        for meal in ('堂食', '盒饭'):
            card, count = build_card(rows, day.isoformat(), meal, tk)
            cards.append({'title': card['header']['title']['content'], 'count': count, 'card': card})
    out = Path(__file__).resolve().parents[2] / 'outputs' / 'lunch_cards' / day.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'table_preview.json').write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'recipient': '周俊成', 'cards': [{'title': c['title'], 'count': c['count']} for c in cards]}, ensure_ascii=False))
    if not args.send:
        return
    cfg = get_feishu_message_config()
    response = requests.post('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                             json=cfg, timeout=30)
    response.raise_for_status()
    auth = response.json()
    if auth.get('code') != 0 or not auth.get('tenant_access_token'):
        raise RuntimeError(f"飞书认证失败：{auth.get('code')} {auth.get('msg')}")
    headers = {'Authorization': 'Bearer ' + auth['tenant_access_token']}
    receipts = []
    for entry in cards:
        for element in entry['card']['body']['elements']:
            if element['tag'] == 'img':
                with open(element['img_key'], 'rb') as image_file:
                    upload = requests.post('https://open.feishu.cn/open-apis/im/v1/images',
                        headers=headers, data={'image_type': 'message'},
                        files={'image': image_file}, timeout=30)
                uploaded = upload.json()
                if uploaded.get('code') != 0:
                    raise RuntimeError(f"表格图片上传失败：{uploaded.get('msg')}")
                element['img_key'] = uploaded['data']['image_key']
        response = requests.post('https://open.feishu.cn/open-apis/im/v1/messages',
            params={'receive_id_type': 'open_id'}, headers=headers, timeout=30,
            json={'receive_id': recipients[0], 'msg_type': 'interactive',
                  'content': json.dumps(entry['card'], ensure_ascii=False), 'uuid': str(uuid.uuid4())})
        result = response.json()
        if result.get('code') != 0:
            raise RuntimeError(f"发送失败：{result.get('code')} {result.get('msg')}")
        response.raise_for_status()
        receipts.append({'title': entry['title'], 'message_id': result['data']['message_id']})
        (out / 'table_receipts.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(receipts[-1], ensure_ascii=False))


if __name__ == '__main__':
    main()
