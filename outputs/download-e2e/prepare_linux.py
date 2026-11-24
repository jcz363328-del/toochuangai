from pathlib import Path
import shutil
p=Path(__file__).parent
q=p/'linux-fixture'
q.mkdir(exist_ok=True)
shutil.copy(p/'fixture_app.py',q/'fixture_app.py')
(q/'serve.py').write_text((p/'serve.py').read_text().replace("sys.path[:0] = [str(ROOT), str(FOLDER/'deps')]","sys.path[:0] = [str(ROOT)]").replace("host='127.0.0.1',port=18580","host='0.0.0.0',port=18580"))
shutil.copytree(p/'history',q/'history',dirs_exist_ok=True)
(q/'uploads').mkdir(exist_ok=True)
