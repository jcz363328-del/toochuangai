from __future__ import annotations

import http.server
import json
import os
import socket
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
DATA = ROOT / "offline-data"
SNAPSHOTS = DATA / "snapshots"
DEFAULT_SHOP = "475394"
DEFAULT_CAMPAIGN = "70540977760495"


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def snapshot_payload(path: Path):
    value = read_json(path)
    return value.get("payload", value)


class OfflineHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP), **kwargs)

    def log_message(self, format: str, *args: object) -> None:
        pass

    def send_json(self, value, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def fail(self, message: str, status: int = 404) -> None:
        self.send_json({"error": {"message": message}, "offline": True}, status)

    def do_POST(self) -> None:
        self.fail("离线版不支持广告调控或任何写入操作。", 405)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/diagnostic"):
            return super().do_GET()
        query = parse_qs(parsed.query)
        if parsed.path == "/api/diagnostic/health":
            return self.send_json({"status": "ok", "service": "magic-ad-offline", "read_only": True, "snapshot": {"enabled": True}})
        if parsed.path == "/api/diagnostic/shops":
            value = read_json(DATA / "shops.json")
            available = {item.name for item in SNAPSHOTS.iterdir() if item.is_dir() and (item / "hot" / "campaigns.json").is_file()}
            available.add(DEFAULT_SHOP)
            value["shops"] = [shop for shop in value.get("shops", []) if str(shop.get("id", shop.get("shop_id", ""))) in available]
            value["default_shop_id"] = DEFAULT_SHOP
            value["offline"] = True
            return self.send_json(value)
        if parsed.path == "/api/diagnostic/search-terms":
            return self.search_terms(query)
        if parsed.path.startswith("/api/diagnostic/sp-controls"):
            return self.fail("离线版已禁用广告调控。", 403)
        if parsed.path != "/api/diagnostic":
            return self.fail("未知的离线诊断接口。")
        shop = query.get("shop_id", [DEFAULT_SHOP])[0]
        campaign = query.get("campaign_id", [""])[0]
        section = query.get("section", ["full"])[0]
        if not campaign:
            path = DATA / "475394-catalog.json" if shop == DEFAULT_SHOP else SNAPSHOTS / shop / "hot" / "campaigns.json"
            if path.is_file():
                return self.send_json(read_json(path) if shop == DEFAULT_SHOP else snapshot_payload(path))
            return self.fail("该店铺没有可用的离线活动目录。")
        if shop == DEFAULT_SHOP and campaign == DEFAULT_CAMPAIGN:
            path = DATA / f"{shop}-{campaign}-{'overview' if section == 'overview' else 'full'}.json"
        else:
            bucket = "overview" if section == "overview" else "full"
            path = SNAPSHOTS / shop / "hot" / "details" / bucket / f"{campaign}.json"
        if path.is_file():
            return self.send_json(read_json(path) if shop == DEFAULT_SHOP else snapshot_payload(path))
        return self.fail("该活动没有可用的离线详情快照。")

    def search_terms(self, query) -> None:
        shop = query.get("shop_id", [DEFAULT_SHOP])[0]
        campaign = query.get("campaign_id", [""])[0]
        kind = query.get("kind", ["waste"])[0]
        page = max(1, int(query.get("page", ["1"])[0]))
        size = max(1, min(100, int(query.get("page_size", ["10"])[0])))
        rows = []
        if shop == DEFAULT_SHOP:
            record = read_json(DATA / "search-term-index.json").get("campaigns", {}).get(campaign, {})
            rows = record.get(kind, [])
        start = (page - 1) * size
        self.send_json({"rows": rows[start:start + size], "total": len(rows), "page": page, "page_size": size, "offline": True})


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    port = free_port()
    port_file = ROOT / ".magic_ad_port"
    port_file.write_text(str(port), encoding="ascii")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), OfflineHandler)
    url = f"http://127.0.0.1:{port}/"
    print(f"MAGIC AD 完整离线版已启动：{url}")
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
