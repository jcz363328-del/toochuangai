from datetime import datetime
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
lines = (root / "live-verification-output.txt").read_text(encoding="utf-8-sig").splitlines()
live = next(json.loads(line) for line in reversed(lines) if line.startswith("{"))
assert live["usage_refresh_ok"] and live["channels"] == live["concurrency"] == 5
test_output = (root / "runtime-test-output.txt").read_text(encoding="utf-8-sig")
assert "Ran 235 tests" in test_output and test_output.rstrip().endswith("OK")
image_id = subprocess.check_output(["docker", "image", "inspect", "toochuangai-single:latest", "--format", "{{.Id}}"], text=True).strip()
report = {
    "completed_at": datetime.now().astimezone().isoformat(),
    "deployed": True,
    "container": "toochuangai-single-app-1",
    "processes_restarted_after_idle": ["xiaoha", "xiaoha-static"],
    "image_tag": "toochuangai-single:fivekeys-20261124",
    "latest_image_id": image_id,
    "latest_tag_updated": True,
    "channels": 5,
    "shared_account_balance": True,
    "starting_percent": 42.86,
    "post_deploy_percent": round(live["balance_percent"], 6),
    "live_verification": live,
    "validation": {
        "production_runtime_tests_passed": 235,
        "image_tests_passed": 233,
        "image_existing_spinner_failures": 2,
        "same_spinner_failures_verified_on_before_image": True,
        "paid_requests_from_validation": 0,
        "service_health": "ok",
        "release_credentials_absent": True,
    },
    "runtime_manifest": json.loads((root / "runtime-release" / "manifest.json").read_text()),
    "image_manifest": json.loads((root / "image-release" / "manifest.json").read_text()),
    "limits": [
        "Balance uses the user-confirmed baseline and bound-key usage, not a web-session account balance API",
        "Recharge, usage on other keys, counter resets and unexpected refunds require recalibration",
        "Individual call records begin at deployment; usage since baseline capture is included in aggregate balance",
        "Ambiguous or delayed per-call fees remain pending until attribution can be verified",
    ],
}
(root / "deployment-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("Deployment report saved")
