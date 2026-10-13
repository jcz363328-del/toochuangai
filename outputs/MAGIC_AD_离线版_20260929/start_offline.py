from __future__ import annotations

import http.server
import os
import socket
import threading
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "app"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    os.chdir(ROOT)
    port = free_port()
    port_file = ROOT.parent / ".magic_ad_port"
    port_file.write_text(str(port), encoding="ascii")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), QuietHandler)
    url = f"http://127.0.0.1:{port}/"
    print(f"MAGIC AD 离线版已启动：{url}")
    print("关闭此窗口即可退出。")
    threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        port_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
