import os
import runpy
import subprocess
import shutil
import sys
from pathlib import Path

folder=Path('/app/outputs/download-e2e')
folder.parent.mkdir(parents=True,exist_ok=True)
shutil.copytree('/tmp/e2e-fixture',folder,dirs_exist_ok=True)
if not Path('/tmp/e2e-deps/aiohttp').exists():
    subprocess.run([sys.executable,'-m','ensurepip'],check=True)
    subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-cache-dir','--target','/tmp/e2e-deps','aiohttp'],check=True)
os.environ['PYTHONPATH']='/tmp/e2e-deps:/app'
os.environ['TC_SINGLE_PORT']='1'
sys.path.insert(0,'/tmp/e2e-deps')
server=subprocess.Popen([sys.executable,'-m','streamlit','run',str(folder/'fixture_app.py'),'--server.port=18581','--server.address=127.0.0.1','--server.headless=true','--server.fileWatcherType=none','--server.enableCORS=false','--server.enableXsrfProtection=false','--browser.gatherUsageStats=false'])
try:
    runpy.run_path(str(folder/'serve.py'),run_name='__main__')
finally:
    server.terminate()
    server.wait(timeout=10)
