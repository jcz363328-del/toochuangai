from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from bjc import sf_db
for name,sql in [('填写状态',"SELECT TOP 12 ShiFouTianXie,COUNT(*) FROM FBAHuoJian_YunShuFangShi GROUP BY ShiFouTianXie ORDER BY COUNT(*) DESC"),('运输方式',"SELECT TOP 12 YunShuFangShi,COUNT(*) FROM FBAHuoJian_YunShuFangShi GROUP BY YunShuFangShi ORDER BY COUNT(*) DESC"),('检查日期',"SELECT MAX(JianChaRiQi),COUNT(JianChaRiQi),MIN(ZhuiZongMaGeShu),MAX(ZhuiZongMaGeShu) FROM FBAHuoJian_YunShuFangShi")]:
 print(name,json.dumps(sf_db(sql),ensure_ascii=False,default=str))
