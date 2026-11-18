import sys,shutil
from pathlib import Path
from datetime import date
from flask import Flask
sys.path.insert(0,'/app')
import daily_replenishment_operation as operation
from openpyxl import load_workbook
app=Flask(__name__)
with app.app_context():
 root=operation.get_output_dir() / '_每日快照'
 paths=list(root.rglob(f'{date.today():%Y%m%d}日常补货运营.xlsx'))
 pending=[]
 for path in paths:
  book=load_workbook(path,read_only=True)
  try:
   if operation.SEA_RECOMMENDATION_SHEET not in book.sheetnames: pending.append(path)
  finally:book.close()
 print('snapshots_to_migrate',len(pending),flush=True)
 if pending:
  items=operation._normalize_sea_shipping_rows(operation.base.sf_db(operation._sea_shipping_recommendation_sql()) or [])
  rows=[[item['sku'],item['avg_daily_sales']] for item in items]
  backup=Path('/tmp/sea-snapshot-backup');backup.mkdir(exist_ok=True)
  for index,path in enumerate(pending):
   shutil.copy2(path,backup/f'{index}.xlsx')
   with operation._refresh_lock: operation._write_sea_recommendation_snapshot(path,rows=rows)
  print('migrated',len(pending),'recommendations',len(items),flush=True)
