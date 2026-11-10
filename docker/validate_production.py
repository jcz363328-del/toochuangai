import json
from pathlib import Path
import sys


if __name__ == "__main__":
    root = Path("/source")
    required = [
        "knowledge_base",
        "listing_agent/data",
        "business_analysis/data",
        "static/exports",
        "VideoClaw/video-claw/video-claw/backend/code/data",
        "VideoClaw/video-claw/video-claw/backend/code/result",
        "ads_monitor_web/ads-monitor-web-full-source/data",
        "docker-data/production-videoclaw/config.yaml",
        "docker-data/production-ads/ads_monitor_config.json",
    ]
    missing = [name for name in required if not (root / name).exists()]
    result = {"missing_required_paths": missing, "storage_root_exists": Path("/storage").is_dir()}
    print(json.dumps(result))
    sys.exit(1 if missing or not result["storage_root_exists"] else 0)
