import sys
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Department.视觉设计部.xiaoha.openrouter_image_site import ensure_jimeng_static_server


if __name__ == "__main__":
    status = ensure_jimeng_static_server(owner=True)
    if not status.get("started"):
        raise RuntimeError("Xiaoha asset server could not bind its internal port")
    Event().wait()
