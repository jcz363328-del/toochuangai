"""Text representation of stored report interactions."""
import re
import json
from datetime import datetime

def _xiaotu_feedback_entry_line(entry_type, actor_name, content_text, target_name=""):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    entry = {
        "type": str(entry_type or "").strip() or "comment",
        "ts": ts,
        "actor": str(actor_name or "匿名用户").strip() or "匿名用户",
        "content": str(content_text or "").strip(),
    }
    target = str(target_name or "").strip()
    if target:
        entry["target"] = target
    return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))


def _xiaotu_parse_feedback_entries(raw_text, entry_type="comment"):
    out = []
    text = str(raw_text or "").strip()
    if not text:
        return out
    for line in text.splitlines():
        line = str(line or "").strip()
        if not line:
            continue
        item = None
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    item = {
                        "type": str(obj.get("type") or entry_type or "comment").strip() or "comment",
                        "ts": str(obj.get("ts") or "").strip(),
                        "actor": str(obj.get("actor") or "").strip(),
                        "target": str(obj.get("target") or "").strip(),
                        "content": str(obj.get("content") or "").strip(),
                    }
            except Exception:
                item = None
        if not item:
            if str(entry_type or "").strip() == "reply":
                m = re.match(
                    r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+(?P<actor>.+?)\s+回复(?P<target>[^：:]*)[：:](?P<content>.+)$",
                    line
                )
                if m:
                    item = {
                        "type": "reply",
                        "ts": str(m.group("ts") or "").strip(),
                        "actor": str(m.group("actor") or "").strip(),
                        "target": str(m.group("target") or "").strip(),
                        "content": str(m.group("content") or "").strip(),
                    }
            else:
                m = re.match(
                    r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+(?P<actor>[^：:]+)[：:](?P<content>.+)$",
                    line
                )
                if m:
                    item = {
                        "type": "comment",
                        "ts": str(m.group("ts") or "").strip(),
                        "actor": str(m.group("actor") or "").strip(),
                        "target": "",
                        "content": str(m.group("content") or "").strip(),
                    }
        if not item:
            item = {
                "type": str(entry_type or "").strip() or "comment",
                "ts": "",
                "actor": "",
                "target": "",
                "content": line,
            }
        out.append(item)
    return out


def _xiaotu_parse_like_user_names(raw_text):
    raw = str(raw_text or "").strip()
    if not raw:
        return []
    parts = re.split(r"[|\n,，;；]+", raw)
    out = []
    seen = set()
    for one in parts:
        name = str(one or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _xiaotu_build_like_user_text(names):
    out = []
    seen = set()
    for one in list(names or []):
        name = str(one or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return "|".join(out)


def _xiaotu_feedback_entries_to_text(items, entry_type="comment"):
    lines = []
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        entry = {
            "type": str(item.get("type") or entry_type or "comment").strip() or "comment",
            "ts": str(item.get("ts") or "").strip(),
            "actor": str(item.get("actor") or "").strip(),
            "content": content,
        }
        target = str(item.get("target") or "").strip()
        if target:
            entry["target"] = target
        lines.append(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines)
