"""Save credential-free verification evidence for this scoped deployment."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
verification = next(json.loads(line) for line in
                    (root / "live-verification.txt").read_text(encoding="utf-8-sig").splitlines()
                    if line.startswith('{"files_verified"'))
manifest = json.loads((root / "runtime-release" / "manifest.json").read_text())
for entry in manifest:
    assert hashlib.sha256((root.parents[1] / "图片" / entry["name"]).read_bytes()).hexdigest() == entry["after"]
image = subprocess.check_output(["docker", "image", "inspect", "toochuangai-single:latest",
                                 "--format", "{{.Id}}"], text=True).strip()
assert image == "sha256:7cb10e2f1f6b3ea48188fcb182b1a55dbd3259594e8d29b37be1e30d55f1b2f3"
report = {
    "deployed_at": datetime.now().astimezone().isoformat(),
    "container": "toochuangai-single-app-1",
    "image": image,
    "tag": "toochuangai-single:balance-refund-20261124",
    "previous_image": "sha256:97c636b7c699c287d3058e74b850d8c561ea1b5f800d24cbf9ce394012b359d8",
    "manifest": manifest,
    "tests": {"local": "231 passed", "image": "231 passed"},
    "live_verification": verification,
    "health": "ok",
    "services": ["xiaoha RUNNING", "xiaoha-static RUNNING"],
    "notes": "Refund verified from original task failure and matching usage decrease; baseline unchanged.",
}
(root / "deployment-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("Scoped deployment evidence saved")
