"""Install a checked source overlay after existing outbound jobs finish."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, "/app")
from 图片.request_limits import get_request_limiter

root = Path("/tmp/xiaoha-balance-refund/runtime-release")
manifest = json.loads((root / "manifest.json").read_text())
for entry in manifest:
    staged = root / entry["name"]
    assert hashlib.sha256(staged.read_bytes()).hexdigest() == entry["after"]
    compile(staged.read_text(encoding="utf-8-sig"), entry["name"], "exec")

limiter = get_request_limiter()
previous = {}
changed = False
try:
    limiter.drain(True)
    deadline, stable_since = time.monotonic() + 300, None
    while True:
        state = limiter.snapshot()
        print(json.dumps({key: state.get(key) for key in ["active", "waiting", "retained", "draining"]}), flush=True)
        if state["active"] == 0 and state["waiting"] == 0:
            stable_since = stable_since or time.monotonic()
            if time.monotonic() - stable_since >= 10:
                break
        else:
            stable_since = None
        if time.monotonic() >= deadline:
            raise RuntimeError("Existing work is still active; no source files were changed")
        time.sleep(5)
    for entry in manifest:
        target = Path("/app/图片") / entry["name"]
        original = target.read_bytes() if target.exists() else None
        actual = hashlib.sha256(original).hexdigest() if original is not None else None
        assert actual == entry["before"], "Concurrent production change: " + entry["name"]
        previous[target] = original
    for entry in manifest:
        target = Path("/app/图片") / entry["name"]
        staged = target.with_suffix(".py.five-key-staged")
        staged.write_bytes((root / entry["name"]).read_bytes())
        os.replace(staged, target)
        changed = True
    subprocess.run(["supervisorctl", "restart", "xiaoha", "xiaoha-static"], check=True)
    import requests
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            response = requests.get("http://127.0.0.1:8501/lashforge/_stcore/health", timeout=3)
            if response.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(2)
    else:
        raise RuntimeError("Xiaoha did not become healthy")
    print("Balance refund release active and healthy", flush=True)
except BaseException:
    if changed:
        for target, original in previous.items():
            if original is None:
                target.unlink(missing_ok=True)
            else:
                staged = target.with_suffix(".py.five-key-rollback")
                staged.write_bytes(original)
                os.replace(staged, target)
        subprocess.run(["supervisorctl", "restart", "xiaoha", "xiaoha-static"], check=True)
        print("Previous source files restored", flush=True)
    raise
finally:
    limiter.drain(False)
    print("Request admission restored", flush=True)
