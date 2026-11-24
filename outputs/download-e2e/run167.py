import sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'outputs/xiaoha-responsive/runtime-1.67'))
import streamlit
print('EXACT FRONTEND RUNTIME',streamlit.__version__,streamlit.__file__,flush=True)
from streamlit.web import cli
sys.argv=['streamlit','run',str(root/'outputs/download-e2e/fixture_app.py'),'--global.developmentMode=false','--server.port=18581','--server.address=127.0.0.1','--server.headless=true','--server.fileWatcherType=none','--server.enableCORS=false','--server.enableXsrfProtection=false','--browser.gatherUsageStats=false']
cli.main()
