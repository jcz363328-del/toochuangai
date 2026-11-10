from datetime import datetime, timedelta
import os
from pathlib import Path
import subprocess
from threading import Event, Lock, Thread
from zoneinfo import ZoneInfo


ROOT = Path("/app/ads_monitor_web/ads-monitor-web-full-source")
PYTHON = "/usr/local/bin/python"
CONFIG = "/ads-state/ads_monitor_config.json"
RUN_LOCK = Lock()
JOBS = {
    "hourly": [
        [PYTHON, "sellfox_ad_diagnostic_refresh.py", "--config", CONFIG, "--snapshot-dir", "data/ad_diagnostic_snapshots", "--batch-size", "1", "--deep-shop-batch-size", "8", "--catalog-workers", "3", "--catalog-ttl-minutes", "45", "--overview-workers", "2"],
        [PYTHON, "sellfox_ad_diagnostic_refresh.py", "--config", CONFIG, "--snapshot-dir", "data/ad_diagnostic_snapshots", "--status-file", "data/ad_diagnostic_priority_refresh_status.json", "--shop-id", "475394", "--campaign-id", "70540977760495", "--batch-size", "1", "--deep-shop-batch-size", "1", "--catalog-workers", "1", "--overview-workers", "1"],
    ],
    "daily": [[PYTHON, "sellfox_ads_monitor.py", "--config", CONFIG, "--output-dir", "outputs/ads_monitor_scheduled", "--once", "--no-workbook", "--lock-wait-minutes", "90"]],
}


def next_trigger(name, now):
    if name == "hourly":
        trigger = now.replace(minute=55, second=0, microsecond=0)
        return trigger if trigger > now else trigger + timedelta(hours=1)
    trigger = now.replace(hour=9, minute=0, second=0, microsecond=0)
    return trigger if trigger > now else trigger + timedelta(days=1)


def run_job(name):
    with RUN_LOCK:
        for command in JOBS[name]:
            result = subprocess.run(command, cwd=ROOT, check=False)
            print(f"scheduled job {name}: exit={result.returncode}", flush=True)


if __name__ == "__main__":
    if os.environ.get("TC_SCHEDULED_JOBS", "0") != "1":
        print("Scheduled jobs disabled", flush=True)
        Event().wait()
    timezone = ZoneInfo("Asia/Shanghai")
    now = datetime.now(timezone)
    triggers = {name: next_trigger(name, now) for name in JOBS}
    active = {}
    while True:
        now = datetime.now(timezone)
        for name in JOBS:
            if now < triggers[name]:
                continue
            triggers[name] = next_trigger(name, now)
            if name in active and active[name].is_alive():
                continue
            active[name] = Thread(target=run_job, args=(name,), daemon=True)
            active[name].start()
        Event().wait(5)
