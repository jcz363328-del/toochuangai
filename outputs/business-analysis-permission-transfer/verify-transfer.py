from pathlib import Path
import json
import pytds
from department_permissions import permission_manager as manager
from secret_settings import sql_server_config
before=json.loads(Path('/tmp/business-analysis-permission-before.json').read_text(encoding='utf8'))
records=manager.get_permission_records(force_refresh=True)
verified={}
for key, original in before['permissions'].items():
    current=records[key]
    old_users=set(manager._split_permission_values(original['yonghu']))
    new_users=set(manager._split_permission_values(current['yonghu']))
    assert new_users == (old_users-{'任真民'})|{'杨悦'}, key
    for field in original:
        if field != 'yonghu': assert current[field] == original[field], (key,field)
    decisions={}
    for name in ('任真民','杨悦'):
        allowed,reason=manager._check_direct_permission_row(current,{'user_id':'audit-only','identities':{name},'valid_departments':[],'user_departments':[]})
        assert allowed == (name=='杨悦'), (key,name,allowed,reason)
        decisions[name]={'personal_grant':allowed,'reason':reason}
    verified[key]={'users':current['yonghu'],'verified':decisions}
print(json.dumps(verified,ensure_ascii=False))
Path('/tmp/business-analysis-permission-after.json').write_text(json.dumps(verified,ensure_ascii=False,indent=2),encoding='utf8')
