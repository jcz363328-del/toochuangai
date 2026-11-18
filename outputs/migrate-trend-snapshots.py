import sys, shutil
from pathlib import Path
from datetime import date
sys.path.insert(0,'/app')
from flask import Flask
from openpyxl import load_workbook
import daily_replenishment_operation as operation
app=Flask(__name__)
with app.app_context():
 paths=list((operation.get_output_dir()/'_每日快照').rglob(f'{date.today():%Y%m%d}日常补货运营.xlsx'))
 updated=0
 for i,path in enumerate(paths):
  book=load_workbook(path,read_only=True)
  try:exists=operation.SALES_TREND_SHEET in book.sheetnames
  finally:book.close()
  if exists:continue
  payload=operation.load_snapshot_cached(path)
  main=payload['sheets'][operation.base.SHEET_NAME]
  index=main['columns'].index('SKU')
  skus={str(row[index] or '').strip() for row in main['rows']}
  settings=payload.get('generation') or {}
  print('computing_snapshot_trends',len(skus),flush=True)
  sheet=operation._sales_trend_snapshot_sheet(settings,skus)
  backup=Path('/tmp/trend-snapshot-backup');backup.mkdir(exist_ok=True)
  shutil.copy2(path,backup/f'{i}.xlsx')
  with operation._refresh_lock:
   operation._write_snapshot_sheet(path,sheet_name=operation.SALES_TREND_SHEET,columns=sheet['columns'],rows=sheet['rows'])
  updated+=1
  print('trend_rows',len(sheet['rows']),'start',sheet['columns'][1],'end',sheet['columns'][-1],flush=True)
 print('snapshots_updated',updated,flush=True)
