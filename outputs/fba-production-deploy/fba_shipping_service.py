"""Read-only FBA query snapshot, compatible with SQL Server compatibility 100."""
import csv
import io
import re
import time
from datetime import datetime
from threading import Lock

TABLE = 'FBAHuoJian_YunShuFangShi'
FIELDS = {
    'ID': ('key', '序号'), 'Dian': ('shop', '店铺'), 'DanHao': ('id', '货件单号'),
    'YunShuFangShi': ('ship', '运输方式'), 'XiaoBaoGuo': ('package', '小包裹'),
    'WuLiuDanHao': ('log', '物流单号'), 'DaoRuShiJian': ('date', '导入时间'),
    'Ien': ('ien', 'IEN'), 'HuoJianDanHao': ('tracking', '亚马逊追踪码'),
    'ShiFouTianXie': ('status', '填写状态'), 'ZhuiZongMaGeShu': ('n', '追踪码个数（记录）'),
    'JianChaRiQi': ('check', '检查日期'),
}
_lock = Lock()
_snapshot = None
_expires = 0
SCI = re.compile(r'[+-]?\d+(?:\.\d+)?[eE][+-]?\d+')


def text(value):
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return str(value).strip()


def prepare(values):
    lower = {k.lower(): v for k, v in values.items()}
    row = {alias: text(lower.get(field.lower())) for field, (alias, _) in FIELDS.items()}
    row['n'] = int(row['n']) if row['n'] else None
    row['codes'] = [s for s in re.split(r'[;,，；\s]+', row['tracking']) if s]
    row['parsed_count'] = len(row['codes'])
    row['filled'] = row['status'].upper() == 'Y'
    row['issues'] = []
    if '海运' in row['ship'] and not row['codes']:
        row['issues'].append('海运追踪码缺失')
    if any(SCI.fullmatch(code) for code in row['codes']):
        row['issues'].append('追踪码格式异常')
    if row['n'] is not None and row['n'] != row['parsed_count']:
        row['issues'].append('数量待核对')
    return row


def load_snapshot(query, force=False):
    global _snapshot, _expires
    with _lock:
        if _snapshot is not None and time.monotonic() < _expires and not force:
            return _snapshot
        columns = query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME=N'FBAHuoJian_YunShuFangShi' ORDER BY ORDINAL_POSITION") or []
        columns = [r[0] if isinstance(r, (tuple, list)) else r for r in columns]
        actual = {str(c).lower(): str(c) for c in columns}
        used = [actual[k.lower()] for k in FIELDS if k.lower() in actual]
        if not used or 'danhao' not in actual:
            raise RuntimeError('未找到FBA货件表或货件单号字段')
        quoted = ','.join('[' + c.replace(']', ']]') + ']' for c in used)
        # Fixed table and schema-discovered columns only; no request text in SQL.
        raw = query(f"SELECT {quoted} FROM [{TABLE}]") or []
        records = []
        for item in raw:
            record = prepare(item if isinstance(item, dict) else dict(zip(used, item)))
            if not record['id'].upper().startswith(('IBR', 'OWS')):
                records.append(record)
        _snapshot = {
            'records': records, 'loaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'columns': [{'key': c, 'label': next(label for field, (_, label) in FIELDS.items() if field.lower() == c.lower())} for c in used],
            'available_fields': [alias for field, (alias, _) in FIELDS.items() if field.lower() in actual],
            'shops': sorted({r['shop'] for r in records if r['shop']}),
            'shipping_methods': sorted({r['ship'] for r in records if r['ship']}),
        }
        _expires = time.monotonic() + 30
        return _snapshot


def query_records(snapshot, args):
    search = text(args.get('q') or args.get('danhao')).lower()
    shop = text(args.get('dian'))
    shipping = text(args.get('shipping'))
    status = text(args.get('status'))
    tab = text(args.get('tab') or ('issue' if args.get('issue') in ('1', 'true', 'yes', 'on') else 'all'))
    base = [r for r in snapshot['records']
            if (not shop or r['shop'] == shop)
            and (not shipping or r['ship'] == shipping)
            and (not status or (r['filled'] if status == 'Y' else not r['status'] if status == 'unmarked' else r['status'] == status))
            and (not search or search in '\n'.join((r['id'], r['log'], r['tracking'], r['ien'])).lower())]
    stats = {'total': len(base), 'filled': sum(r['filled'] for r in base),
             'issues': sum(bool(r['issues']) for r in base), 'checked': sum(bool(r['check']) for r in base),
             'unchecked': sum(not r['check'] for r in base)}
    records = [r for r in base if tab == 'all'
               or tab == 'issue' and r['issues'] or tab == 'filled' and r['filled']
               or tab == 'unchecked' and not r['check']]
    sort = text(args.get('sort') or 'import_desc')
    sort_field = 'check' if sort == 'check_desc' else 'key' if sort == 'seq_desc' else 'date'
    def order(row):
        key = int(row['key']) if row['key'].isdigit() else 0
        return (key, row['id']) if sort_field == 'key' else (row[sort_field], key)
    records.sort(key=order, reverse=sort != 'import_asc')
    return records, stats


def payload(snapshot, args):
    records, stats = query_records(snapshot, args)
    page_size = max(1, min(int(args.get('page_size') or 20), 100))
    pages = max(1, (len(records) + page_size - 1) // page_size)
    page = min(max(int(args.get('page') or 1), 1), pages)
    visible = records[(page - 1) * page_size:page * page_size]
    # Preserve the original response shape for department inline tables.
    items = []
    for row in visible:
        values = {col['key']: row[next(alias for field, (alias, _) in FIELDS.items() if field.lower() == col['key'].lower())] for col in snapshot['columns']}
        values['__cargo_count__'] = row['parsed_count']
        items.append({'values': values, 'warning': bool(row['issues']),
                      'warning_fields': {'HuoJianDanHao': '；'.join(row['issues'])} if row['issues'] else {}})
    return {'records': visible, 'items': items, 'columns': snapshot['columns'], 'stats': stats,
            'page': page, 'page_size': page_size, 'total': len(records), 'total_pages': pages,
            'loaded_at': snapshot['loaded_at'], 'available_fields': snapshot['available_fields'],
            'has_import_sort': 'date' in snapshot['available_fields'],
            'has_dian_filter': 'shop' in snapshot['available_fields'],
            'has_danhao_filter': 'id' in snapshot['available_fields']}


def csv_rows(snapshot, args):
    records, _ = query_records(snapshot, args)
    selected = {s for s in text(args.get('selected')).split(',') if s}
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    fields = list(FIELDS.values())
    writer.writerow([label for _, label in fields] + ['追踪码个数（识别）', '关注事项'])
    yield '\ufeff' + buffer.getvalue()
    for record in records:
        if selected and record['key'] not in selected:
            continue
        buffer.seek(0)
        buffer.truncate(0)
        values = [record[key] if record[key] is not None else '' for key, _ in fields]
        # Prevent spreadsheet formulas in exported database text cells.
        values = ["'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v for v in values]
        writer.writerow(values + [record['parsed_count'], '；'.join(record['issues'])])
        yield buffer.getvalue()
