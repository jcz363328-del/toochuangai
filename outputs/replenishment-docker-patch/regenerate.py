import os
import uuid
from flask import Flask
import daily_replenishment_operation as op
app = Flask(__name__)
app.secret_key = 'maintenance'
with app.test_request_context('/'):
    target = op.get_shared_snapshot_path()
    print('Generating full shared snapshot', flush=True)
    dataset = op.generate_operation_dataset(op.base.resolve_source_path(), query_executor=op.base.sf_db)
    staging = target.with_name('.' + uuid.uuid4().hex + '.xlsx')
    try:
        op.save_operation_workbook(dataset, staging)
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)
    rows = dataset['main']['rows']
    operators = {str(row['values'][0] or '').strip() for row in rows}
    stores = {str(row['values'][1] or '').strip() for row in rows}
    print('Full snapshot ready: rows=%s operators=%s stores=%s' % (len(rows), len(operators), len(stores)), flush=True)
