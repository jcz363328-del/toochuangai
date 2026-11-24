import sys,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from bjc import sf_db
from fba_shipping_service import load_snapshot,payload
start=time.monotonic();s=load_snapshot(sf_db);p=payload(s,{})
print(json.dumps({'seconds':round(time.monotonic()-start,2),'total':p['total'],'stats':p['stats'],'page_size':p['page_size'],'available_fields':p['available_fields']},ensure_ascii=True))
