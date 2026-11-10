import concurrent.futures
import sys
import subprocess
import urllib.request


CHECKS = {
    "gateway": "http://127.0.0.1:8000/_container/health",
    "web": "http://127.0.0.1:8100/_container/health",
    "sales-api": "http://127.0.0.1:4311/api/health",
    "xiaoha": "http://127.0.0.1:8501/lashforge/_stcore/health",
    "xiaoha-static": "http://127.0.0.1:8502/infinite-canvas/",
    "videoclaw-backend": "http://127.0.0.1:18000/api/health",
    "videoclaw-frontend": "http://127.0.0.1:3000/ai/video-claw",
    "ads-api": "http://127.0.0.1:4174/api/diagnostic/health",
}


def check_service(item):
    name, url = item
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return name if response.status != 200 else ""
    except Exception:
        return name


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(CHECKS)) as executor:
        failed = [name for name in executor.map(check_service, CHECKS.items()) if name]
    try:
        status = subprocess.run(["/usr/bin/supervisorctl", "status"], capture_output=True, timeout=5, check=False)
        if status.returncode:
            failed.append("process-manager")
    except Exception:
        failed.append("process-manager")
    print("unhealthy: " + ", ".join(failed) if failed else "all services healthy")
    sys.exit(1 if failed else 0)
