from pathlib import Path
import shutil


def prepare_runtime(root):
    video = root / "VideoClaw/video-claw/video-claw/backend"
    files = [
        (video / "config.yaml" if (video / "config.yaml").exists() else video / "config.yaml.example", root / "docker-data/videoclaw/config.yaml"),
        (root / "ads_monitor_web/ads-monitor-web-full-source/ads_monitor_config.json", root / "docker-data/ads/ads_monitor_config.json"),
    ]
    for source, target in files:
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        print("Prepared " + str(target.relative_to(root)))


if __name__ == "__main__":
    prepare_runtime(Path(__file__).resolve().parents[1])
