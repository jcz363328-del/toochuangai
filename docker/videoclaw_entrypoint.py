import os
from pathlib import Path
import shutil
import sys


backend = Path("/app/backend")
state = Path("/video-state")
state.mkdir(parents=True, exist_ok=True)
config = state / "config.yaml"
if not config.exists():
    shutil.copyfile(backend / "config.yaml.example", config)
config_link = backend / "config.yaml"
if not config_link.is_symlink():
    config_link.symlink_to(config)
sys.path.insert(0, str(backend))
os.chdir(backend)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.app:app", host="127.0.0.1", port=18000, access_log=False)
