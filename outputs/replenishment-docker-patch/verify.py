from flask import Flask
import daily_replenishment_operation as op
app = Flask(__name__)
with app.app_context():
    path = op.get_shared_today_snapshot()
    assert path is not None
    payload = op.load_snapshot_cached(path)
    rows = payload['sheets'][op.base.SHEET_NAME]['rows']
    names = list(dict.fromkeys(str(row[0] or '').strip() for row in rows if row[0]))
    checked = 0
    for name in names:
        access = op.get_store_permissions(name)
        if not access['read_stores']:
            continue
        scoped = op._scope_snapshot_payload(payload, access)
        visible = scoped['sheets'][op.base.SHEET_NAME]['rows']
        assert all(op._normalized_store(row[1]) in access['read_stores'] for row in visible)
        print('Permission scope %s: authorized_stores=%s visible_rows=%s' % (checked + 1, len(access['read_stores']), len(visible)), flush=True)
        checked += 1
        if checked == 2:
            break
    assert checked == 2
    print('Shared full snapshot and two real permission scopes verified', flush=True)
