import json, os, re, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from secret_settings import env
import getpass
new_keys=json.loads(getpass.getpass('Credential input (hidden): '))
primary=env('OMNIAKEY_API_KEY')
assert primary and isinstance(new_keys,list) and len(new_keys)==4, 'Expected existing credential plus four new credentials'
keys=list(dict.fromkeys([primary]+new_keys))
assert len(keys)==5 and all(isinstance(k,str) and re.fullmatch(r'sk-[A-Za-z0-9]{30,100}',k) for k in keys), 'Credential validation failed'
target=Path('图片/history/.credentials/omnia_api_keys.json').resolve()
assert not target.exists(),'Credential file already exists; inspect before changing'
target.parent.mkdir(parents=True,exist_ok=True)
staged=target.with_suffix('.new')
fd=os.open(staged,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(keys,f)
os.replace(staged,target)
print('Configured credential count:',len(keys),flush=True)

