import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from bjc import sf_db
rows=sf_db("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=N'FBAHuoJian_YunShuFangShi' ORDER BY ORDINAL_POSITION")
print(json.dumps(rows,ensure_ascii=False,default=str))
Path(__file__).with_name('schema.json').write_text(json.dumps(rows,ensure_ascii=False,default=str),encoding='utf-8')
