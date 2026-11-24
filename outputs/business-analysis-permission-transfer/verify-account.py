import json
from department_permissions import permission_manager as manager
uid='ou_f6ab7ffde7bde7a9af75db4e8c19bb10'
info=manager.get_user_info_by_user_id(uid)
print(json.dumps({'user_id':uid,'name':(info or {}).get('name'),'lookup_found':bool(info),'departments':manager.get_user_departments(uid)},ensure_ascii=False))
