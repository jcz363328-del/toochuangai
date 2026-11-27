"""Create Sellfox purchase drafts with persistent duplicate-request protection."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import logging
import sqlite3
import requests
import sys
from datetime import date
from pathlib import Path

CREATE_PATH = "/api/purchasePlan/create.json"


class PurchaseRejected(RuntimeError):
    pass


class PurchaseUncertain(RuntimeError):
    pass


def get_client():
    # Reuse the deployed Sellfox token, credential loading and signature implementation.
    root = Path(__file__).resolve().parents[2]
    module_path = Path("ads_monitor_web") / "ads-monitor-web-full-source"
    module_dir = root / module_path
    if not (module_dir / "sellfox_ads_monitor.py").is_file():
        module_dir = root / "Department" / "流程与AI部" / module_path
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))
    from sellfox_ads_monitor import SellfoxAdsClient, load_api_credentials
    client_id, secret = load_api_credentials()
    return SellfoxAdsClient(client_id, secret, logging.getLogger(__name__))


def send_purchase(payload):
    try:
        client = get_client()
    except Exception as exc:
        raise PurchaseRejected("赛狐连接配置不可用，请联系管理员检查 API 凭据。") from exc
    try:
        # Creation is deliberately sent ONCE; read-client retry helpers are not used.
        from sellfox_import import API_BASE_URL
        try:
            params = client._signed_params(CREATE_PATH)
        except Exception as exc:
            raise PurchaseRejected("获取赛狐授权失败，尚未创建采购计划。") from exc
        try:
            response = client.session.request("POST", API_BASE_URL + CREATE_PATH,
                                              params=params, json=payload, timeout=(15, 90))
        except requests.RequestException as exc:
            raise PurchaseUncertain("赛狐网络请求超时或中断，未收到创建回执；请先核对，勿重复创建。") from exc
        try:
            result = response.json()
        except ValueError as exc:
            if response.status_code in (400, 401, 403, 404, 405, 413, 415, 422, 429):
                raise PurchaseRejected(f"赛狐接口拒绝请求（HTTP {response.status_code}），未创建采购计划。") from exc
            raise PurchaseUncertain(f"赛狐接口未返回有效回执（HTTP {response.status_code}），创建结果未确认。") from exc
        if not isinstance(result, dict):
            raise PurchaseUncertain("赛狐回执格式异常，创建结果未确认。")
        if str(result.get("code")) != "0":
            raise PurchaseRejected(f"赛狐拒绝创建：{result.get('msg') or result.get('message') or '请检查商品及操作人信息'}（{result.get('code')}）")
        return result.get("data")
    finally:
        client.close()


@contextmanager
def _database(path):
    db = sqlite3.connect(path, timeout=15)
    try:
        with db:
            yield db
    finally:
        db.close()


def create_once(payload, ledger_path, *, sender=send_purchase):
    """Same user and same draft on the same day return the original result."""
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256((date.today().isoformat() + serialized).encode()).hexdigest()
    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with _database(ledger_path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS requests (key TEXT PRIMARY KEY, status TEXT NOT NULL, result TEXT)")
        fields = {row[1] for row in db.execute("PRAGMA table_info(requests)")}
        for column in ("error", "payload", "updated_at"):
            if column not in fields:
                db.execute(f"ALTER TABLE requests ADD COLUMN {column} TEXT")
        db.commit()
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute("SELECT status,result,error FROM requests WHERE key=?", (key,)).fetchone()
        if prior and prior[0] == "success":
            return json.loads(prior[1]), True
        if prior and prior[0] in ("pending", "uncertain"):
            raise PurchaseUncertain(prior[2] or "原请求未保存成功回执，不能确认已创建；请先到赛狐核对，勿重复创建。")
        db.execute("INSERT OR REPLACE INTO requests (key,status,result,payload,updated_at) VALUES (?, 'pending', NULL, ?, datetime('now'))", (key, serialized))
    try:
        result = sender(payload)
    except PurchaseRejected as exc:
        with _database(ledger_path) as db:
            db.execute("UPDATE requests SET status='rejected',error=?,updated_at=datetime('now') WHERE key=?", (str(exc),key))
        raise
    except Exception as exc:
        with _database(ledger_path) as db:
            message = str(exc) if isinstance(exc, PurchaseUncertain) else "创建过程发生异常，未收到成功回执，请先到赛狐核对。"
            db.execute("UPDATE requests SET status='uncertain',error=?,updated_at=datetime('now') WHERE key=?", (message,key))
        raise PurchaseUncertain(message) from exc
    with _database(ledger_path) as db:
        db.execute("UPDATE requests SET status='success',result=? WHERE key=?",
                   (json.dumps(result, ensure_ascii=False), key))
    return result, False
