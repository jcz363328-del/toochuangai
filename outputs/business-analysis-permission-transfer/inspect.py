import json
from pathlib import Path
import pytds
from department_permissions import permission_manager as manager
from secret_settings import sql_server_config
records=manager.get_permission_records(force_refresh=True)
permissions={k:v for k,v in records.items() if k.startswith('business_analysis')}
conn=pytds.connect(**sql_server_config())
try:
    cur=conn.cursor()
    cur.execute('SELECT FeiShu_ID, YONGHU FROM dbo.feishu_id WHERE LTRIM(RTRIM(YONGHU)) IN (%s,%s)', ('任真民','杨悦'))
    people=[{'user_id':str(r[0] or '').strip(),'name':str(r[1] or '').strip()} for r in cur.fetchall()]
    cur.execute("SELECT UserID,UserName,FunctionName,IsAllowed,UpdatedBy,UpdatedAt FROM dbo.UserPermissionOverrides WHERE FunctionName LIKE %s AND (LTRIM(RTRIM(UserName)) IN (%s,%s) OR UserID IN (SELECT FeiShu_ID FROM dbo.feishu_id WHERE LTRIM(RTRIM(YONGHU)) IN (%s,%s)))",('business_analysis%','任真民','杨悦','任真民','杨悦'))
    overrides=[list(r) for r in cur.fetchall()]
finally:
    conn.close()
result={'permissions':permissions,'people':people,'overrides':overrides}
Path('/tmp/business-analysis-permission-before.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,default=str))
