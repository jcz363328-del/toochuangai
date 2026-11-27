"""Persistent mapping from report recipients to Feishu card messages."""

import json
import os
from datetime import datetime
from threading import Lock


class ReportCardMessageStore:
    def __init__(self, path):
        self.path = path
        self._messages = {}
        self._lock = Lock()
        self._loaded = False


    def remember(self, wendangid, receive_id, message_id):
        self._ensure_loaded()
        wid = str(wendangid or "").strip()
        rid = str(receive_id or "").strip()
        mid = str(message_id or "").strip()
        if not wid or not rid or not mid:
            return
        with self._lock:
            bucket = self._messages.get(wid) or {}
            if not isinstance(bucket, dict):
                bucket = {}
            now_ts = datetime.now().timestamp()
            old_item = bucket.get(rid) or {}
            message_ids = []
            if isinstance(old_item, dict):
                old_ids = old_item.get("message_ids") or []
                if isinstance(old_ids, list):
                    for old in old_ids:
                        if isinstance(old, dict):
                            old_mid = str(old.get("message_id") or "").strip()
                            if old_mid:
                                message_ids.append({
                                    "message_id": old_mid,
                                    "ts": float(old.get("ts") or 0) if str(old.get("ts") or "").strip() else 0
                                })
                        else:
                            old_mid = str(old or "").strip()
                            if old_mid:
                                message_ids.append({"message_id": old_mid, "ts": 0})
                old_mid = str(old_item.get("message_id") or "").strip()
                if old_mid and not any(str(x.get("message_id") or "").strip() == old_mid for x in message_ids):
                    message_ids.append({
                        "message_id": old_mid,
                        "ts": float(old_item.get("ts") or 0) if str(old_item.get("ts") or "").strip() else 0
                    })
            deduped = []
            seen = set()
            for item in sorted(message_ids, key=lambda x: float(x.get("ts") or 0)):
                item_mid = str(item.get("message_id") or "").strip()
                if not item_mid or item_mid in seen or item_mid == mid:
                    continue
                seen.add(item_mid)
                deduped.append({
                    "message_id": item_mid,
                    "ts": float(item.get("ts") or 0)
                })
            deduped.append({
                "message_id": mid,
                "ts": now_ts
            })
            bucket[rid] = {
                "message_id": mid,
                "ts": now_ts,
                "message_ids": deduped[-8:]
            }
            self._messages[wid] = bucket
            self._save_locked()

    def _ensure_loaded(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            loaded_map = {}
            try:
                if os.path.exists(self.path):
                    with open(self.path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    if isinstance(raw, dict):
                        for wid, bucket in raw.items():
                            wid_key = str(wid or "").strip()
                            if not wid_key or not isinstance(bucket, dict):
                                continue
                            normalized_bucket = {}
                            for rid, item in bucket.items():
                                rid_key = str(rid or "").strip()
                                if not rid_key or not isinstance(item, dict):
                                    continue
                                latest_mid = str(item.get("message_id") or "").strip()
                                latest_ts = float(item.get("ts") or 0)
                                message_ids = []
                                for raw_item in (item.get("message_ids") or []):
                                    if isinstance(raw_item, dict):
                                        raw_mid = str(raw_item.get("message_id") or "").strip()
                                        raw_ts = float(raw_item.get("ts") or 0)
                                    else:
                                        raw_mid = str(raw_item or "").strip()
                                        raw_ts = 0
                                    if raw_mid:
                                        message_ids.append({
                                            "message_id": raw_mid,
                                            "ts": raw_ts
                                        })
                                if latest_mid and not any(str(x.get("message_id") or "").strip() == latest_mid for x in message_ids):
                                    message_ids.append({
                                        "message_id": latest_mid,
                                        "ts": latest_ts
                                    })
                                if latest_mid or message_ids:
                                    normalized_bucket[rid_key] = {
                                        "message_id": latest_mid or str((message_ids[-1] or {}).get("message_id") or "").strip(),
                                        "ts": latest_ts,
                                        "message_ids": message_ids[-8:]
                                    }
                            if normalized_bucket:
                                loaded_map[wid_key] = normalized_bucket
            except Exception:
                loaded_map = {}
            self._messages.clear()
            self._messages.update(loaded_map)
            self._loaded = True

    def _save_locked(self):
        try:
            payload = {}
            for wid, bucket in (self._messages or {}).items():
                wid_key = str(wid or "").strip()
                if not wid_key or not isinstance(bucket, dict):
                    continue
                normalized_bucket = {}
                for rid, item in bucket.items():
                    rid_key = str(rid or "").strip()
                    if not rid_key or not isinstance(item, dict):
                        continue
                    latest_mid = str(item.get("message_id") or "").strip()
                    latest_ts = float(item.get("ts") or 0)
                    message_ids = []
                    seen = set()
                    for raw_item in (item.get("message_ids") or []):
                        if not isinstance(raw_item, dict):
                            raw_mid = str(raw_item or "").strip()
                            raw_ts = 0
                        else:
                            raw_mid = str(raw_item.get("message_id") or "").strip()
                            raw_ts = float(raw_item.get("ts") or 0)
                        if not raw_mid or raw_mid in seen:
                            continue
                        seen.add(raw_mid)
                        message_ids.append({
                            "message_id": raw_mid,
                            "ts": raw_ts
                        })
                    if latest_mid and latest_mid not in seen:
                        message_ids.append({
                            "message_id": latest_mid,
                            "ts": latest_ts
                        })
                    if latest_mid or message_ids:
                        normalized_bucket[rid_key] = {
                            "message_id": latest_mid or str((message_ids[-1] or {}).get("message_id") or "").strip(),
                            "ts": latest_ts,
                            "message_ids": message_ids[-8:]
                        }
                if normalized_bucket:
                    payload[wid_key] = normalized_bucket
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            pass

    def message_ids(self, wendangid, receive_id=''):
        self._ensure_loaded()
        wid = str(wendangid or "").strip()
        rid = str(receive_id or "").strip()
        if not wid:
            return []
        with self._lock:
            bucket = self._messages.get(wid) or {}
            if not isinstance(bucket, dict):
                return []
            items = []
            if rid:
                items = [bucket.get(rid) or {}]
            else:
                items = list(bucket.values())
        message_ids = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            candidates = []
            raw_ids = item.get("message_ids") or []
            if isinstance(raw_ids, list):
                for raw in raw_ids:
                    if isinstance(raw, dict):
                        candidate_mid = str(raw.get("message_id") or "").strip()
                    else:
                        candidate_mid = str(raw or "").strip()
                    if candidate_mid:
                        candidates.append(candidate_mid)
            latest_mid = str(item.get("message_id") or "").strip()
            if latest_mid:
                candidates.append(latest_mid)
            for candidate_mid in candidates:
                if candidate_mid and candidate_mid not in seen:
                    seen.add(candidate_mid)
                    message_ids.append(candidate_mid)
        return message_ids

    def message_id(self, wendangid, receive_id=''):
        message_ids = self.message_ids(wendangid, receive_id)
        return message_ids[-1] if message_ids else ""

    def receive_ids(self, wendangid):
        self._ensure_loaded()
        wid = str(wendangid or "").strip()
        if not wid:
            return []
        with self._lock:
            bucket = self._messages.get(wid) or {}
            if not isinstance(bucket, dict):
                return []
            return [
                str(receive_id or "").strip()
                for receive_id in bucket.keys()
                if str(receive_id or "").strip()
            ]

    def forget(self, wendangid):
        self._ensure_loaded()
        wid = str(wendangid or "").strip()
        if not wid:
            return
        with self._lock:
            if wid in self._messages:
                self._messages.pop(wid, None)
                self._save_locked()

    def entries(self, wendangid, latest_only=False):
        wid = str(wendangid or "").strip()
        if not wid:
            return []
        out = []
        seen = set()
        for receive_id in self.receive_ids(wid):
            rid = str(receive_id or "").strip()
            message_ids = (
                [self.message_id(wid, rid)]
                if latest_only else
                self.message_ids(wid, rid)
            )
            for message_id in message_ids:
                mid = str(message_id or "").strip()
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                out.append({
                    "receive_id": rid,
                    "message_id": mid,
                })
        return out
