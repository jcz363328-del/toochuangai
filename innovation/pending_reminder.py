# -*- coding: utf-8 -*-

import os
import re
import time
import json
from collections import defaultdict
from datetime import datetime, timedelta
from threading import Lock, Thread

import requests

from bjc import sf_db

from .config import DEPARTMENT_FEISHU_MAPPING


MANAGE_URL = "http://223.78.73.100:8000/innovation/manage"
DEPARTMENT_ALIASES = {
    "TK项目": "TK部门",
    "TK": "TK部门",
    "数据": "AI部",
    "人力": "人力行政部",
    "美工": "视觉设计部",
    "摄影": "摄影部",
}


class FeishuReminderMessageService:
    """使用同一个飞书应用读取通讯录并发送消息，避免 open_id 跨应用失效。"""

    def __init__(self, query_fn=sf_db):
        self.query_fn = query_fn
        self.recipient_names = {}
        self.last_send_result = {}
        self._http = requests.Session()
        self._http.trust_env = False

    def _get_access_token(self):
        from department_permissions import permission_manager

        return permission_manager.get_access_token()

    @staticmethod
    def _escape_sql(value):
        return str(value or "").replace("'", "''")

    def _department_ids(self, assignee):
        original_name = str(assignee or "").strip()
        names = [original_name]
        alias = DEPARTMENT_ALIASES.get(original_name)
        if alias and alias not in names:
            names.append(alias)
        name_sql = ",".join(f"N'{self._escape_sql(name)}'" for name in names if name)
        if not name_sql:
            return []
        rows = self.query_fn(f"""
            SELECT DISTINCT FeiShu_ID
            FROM feishu_id
            WHERE YongHu IN ({name_sql})
              AND (FeiShu_ID LIKE 'od-%%' OR FeiShu_ID LIKE 'od[_]%%')
        """) or []
        department_ids = []
        for row in rows:
            value = row[0] if isinstance(row, (list, tuple)) and row else row
            department_id = str(value or "").strip()
            if department_id and department_id not in department_ids:
                department_ids.append(department_id)
        return department_ids

    def _department_members(self, department_id):
        token = self._get_access_token()
        if not token:
            self.last_send_result = {"error": "获取飞书访问令牌失败"}
            return []
        url = "https://open.feishu.cn/open-apis/contact/v3/users"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        params = {
            "user_id_type": "open_id",
            "department_id_type": "open_department_id",
            "department_id": department_id,
            "page_size": 100,
        }
        members = []
        page_token = ""
        while True:
            if page_token:
                params["page_token"] = page_token
            response = self._http.get(url, headers=headers, params=params, timeout=15)
            payload = response.json() or {}
            if payload.get("code") != 0:
                self.last_send_result = payload
                break
            data = payload.get("data") or {}
            for user in data.get("items") or []:
                open_id = str(user.get("open_id") or "").strip()
                if not open_id:
                    continue
                if open_id not in members:
                    members.append(open_id)
                name = str(user.get("name") or "").strip()
                if name:
                    self.recipient_names[open_id] = name
            page_token = str(data.get("page_token") or "").strip()
            if not page_token:
                break
        return members

    def _department_children(self, department_id):
        token = self._get_access_token()
        if not token:
            self.last_send_result = {"error": "获取飞书访问令牌失败"}
            return []
        url = f"https://open.feishu.cn/open-apis/contact/v3/departments/{department_id}/children"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        params = {
            "department_id_type": "open_department_id",
            "fetch_child": False,
            "page_size": 50,
        }
        children = []
        page_token = ""
        while True:
            if page_token:
                params["page_token"] = page_token
            response = self._http.get(url, headers=headers, params=params, timeout=15)
            payload = response.json() or {}
            if payload.get("code") != 0:
                self.last_send_result = payload
                break
            data = payload.get("data") or {}
            for item in data.get("items") or []:
                child_id = str(
                    item.get("open_department_id")
                    or item.get("department_id")
                    or item.get("id")
                    or ""
                ).strip()
                if child_id and child_id not in children:
                    children.append(child_id)
            page_token = str(data.get("page_token") or "").strip()
            if not page_token:
                break
        return children

    def _department_tree_ids(self, department_id):
        department_ids = []
        seen = set()
        stack = [department_id]
        while stack:
            current = stack.pop()
            if not current or current in seen:
                continue
            seen.add(current)
            department_ids.append(current)
            for child_id in self._department_children(current):
                if child_id not in seen:
                    stack.append(child_id)
        return department_ids

    def _lookup_user_by_user_id(self, user_id):
        token = self._get_access_token()
        if not token:
            self.last_send_result = {"error": "获取飞书访问令牌失败"}
            return ""
        clean_user_id = str(user_id or "").strip()
        if not clean_user_id:
            return ""
        url = f"https://open.feishu.cn/open-apis/contact/v3/users/{clean_user_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        params = {"user_id_type": "user_id", "department_id_type": "open_department_id"}
        response = self._http.get(url, headers=headers, params=params, timeout=15)
        payload = response.json() or {}
        if payload.get("code") != 0:
            self.last_send_result = payload
            return ""
        user = (payload.get("data") or {}).get("user") or {}
        open_id = str(user.get("open_id") or "").strip()
        name = str(user.get("name") or "").strip()
        if open_id and name:
            self.recipient_names[open_id] = name
        return open_id

    def _mapped_contacts(self, assignee):
        original_name = str(assignee or "").strip()
        mapping_name = original_name
        if mapping_name not in DEPARTMENT_FEISHU_MAPPING:
            mapping_name = DEPARTMENT_ALIASES.get(original_name) or original_name
        raw_targets = DEPARTMENT_FEISHU_MAPPING.get(mapping_name)
        targets = raw_targets if isinstance(raw_targets, (list, tuple, set)) else [raw_targets]
        contacts = []
        for target in targets:
            target_id = str(target or "").strip()
            if not target_id:
                continue
            if target_id.startswith("ou_"):
                open_id = target_id
            elif "@" in target_id:
                open_id = target_id
            else:
                open_id = self._lookup_user_by_user_id(target_id)
            if open_id and open_id not in contacts:
                contacts.append(open_id)
        return contacts

    def get_department_contacts(self, assignee):
        contacts = []
        self.last_send_result = {}
        try:
            for department_id in self._department_ids(assignee):
                for tree_department_id in self._department_tree_ids(department_id):
                    for member in self._department_members(tree_department_id):
                        if member not in contacts:
                            contacts.append(member)
            if not contacts:
                contacts.extend(self._mapped_contacts(assignee))
        except Exception as exc:
            self.last_send_result = {"error": str(exc)}
        return contacts

    def _resolve_personal_receive_id(self, recipient):
        value = str(recipient or "").strip()
        if value.startswith("ou_") or value.startswith("oc_") or "@" in value:
            return value
        rows = self.query_fn(f"""
            SELECT TOP 1 FeiShu_ID, YongHu
            FROM feishu_id
            WHERE YongHu = N'{self._escape_sql(value)}'
              AND (FeiShu_ID LIKE 'ou[_]%%' OR FeiShu_ID LIKE 'oc[_]%%' OR FeiShu_ID LIKE '%%@%%')
            ORDER BY CASE WHEN FeiShu_ID LIKE 'ou[_]%%' THEN 0 ELSE 1 END, ID
        """) or []
        if not rows:
            return ""
        row = rows[0]
        receive_id = str(row[0] or "").strip()
        name = str(row[1] or "").strip() if len(row) > 1 else value
        if receive_id and name:
            self.recipient_names[receive_id] = name
        return receive_id

    def send_message(self, recipient, message):
        self.last_send_result = {}
        receive_id = self._resolve_personal_receive_id(recipient)
        if not receive_id:
            self.last_send_result = {"error": "未找到该承接人的可用飞书接收人"}
            return False
        token = self._get_access_token()
        if not token:
            self.last_send_result = {"error": "获取飞书访问令牌失败"}
            return False
        if receive_id.startswith("oc_"):
            receive_id_type = "chat_id"
        elif "@" in receive_id:
            receive_id_type = "email"
        else:
            receive_id_type = "open_id"
        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": str(message or "")}, ensure_ascii=False),
        }
        try:
            response = self._http.post(url, headers=headers, json=payload, timeout=20)
            result = response.json() or {}
            self.last_send_result = result
            return result.get("code") == 0
        except Exception as exc:
            self.last_send_result = {"error": str(exc)}
            return False


def _send_error_text(service):
    detail = getattr(service, "last_send_result", None)
    if not isinstance(detail, dict):
        return ""
    return str(detail.get("msg") or detail.get("message") or detail.get("error") or "").strip()


def _clip_text(value, limit=220):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return "（无内容）"
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _coerce_datetime(value):
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_elapsed(start_time, now_dt):
    start = _coerce_datetime(start_time)
    if not start:
        return "超过2天"
    total_hours = max(0, int((now_dt - start).total_seconds() // 3600))
    days, hours = divmod(total_hours, 24)
    if hours:
        return f"{days}天{hours}小时"
    return f"{days}天"


def load_overdue_pending_projects(now_dt=None, query_fn=sf_db):
    """只返回同一项目全部流转状态为“待承接”且已超过2天的记录。"""
    now = now_dt if isinstance(now_dt, datetime) else datetime.now()
    cutoff = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        WITH pending_projects AS (
            SELECT [项目编号]
            FROM chuangxin_liuzhuan1
            GROUP BY [项目编号]
            HAVING COUNT(*) > 0
               AND SUM(
                    CASE
                        WHEN LTRIM(RTRIM(ISNULL([状态], ''))) = N'待承接' THEN 0
                        ELSE 1
                    END
               ) = 0
        ), overdue_assignees AS (
            SELECT
                flow.[项目编号],
                LTRIM(RTRIM(flow.[承接人])) AS [承接人],
                MIN(flow.[流转时间]) AS earliest_flow_time
            FROM chuangxin_liuzhuan1 flow
            INNER JOIN pending_projects pending
                    ON pending.[项目编号] = flow.[项目编号]
            WHERE LTRIM(RTRIM(ISNULL(flow.[状态], ''))) = N'待承接'
              AND flow.[流转时间] IS NOT NULL
              AND LTRIM(RTRIM(ISNULL(flow.[承接人], ''))) <> ''
            GROUP BY flow.[项目编号], LTRIM(RTRIM(flow.[承接人]))
            HAVING MIN(flow.[流转时间]) < '{cutoff}'
        )
        SELECT
            overdue.[项目编号],
            overdue.[承接人],
            overdue.earliest_flow_time,
            ISNULL(CAST(project.[标题] AS NVARCHAR(MAX)), ''),
            ISNULL(CAST(project.[内容] AS NVARCHAR(MAX)), '')
        FROM overdue_assignees overdue
        INNER JOIN chuangxin_tibao1 project
                ON project.[编号] = overdue.[项目编号]
        ORDER BY overdue.[承接人], overdue.earliest_flow_time, overdue.[项目编号]
    """
    rows = query_fn(sql) or []
    projects = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        assignee = str(row[1] or "").strip()
        if not assignee:
            continue
        projects.append({
            "project_id": str(row[0] or "").strip(),
            "assignee": assignee,
            "flow_time": _coerce_datetime(row[2]),
            "title": str(row[3] or "").strip(),
            "content": str(row[4] or "").strip(),
        })
    return projects


def group_projects_by_assignee(projects):
    grouped = defaultdict(list)
    for project in projects or []:
        assignee = str(project.get("assignee") or "").strip()
        if assignee:
            grouped[assignee].append(project)
    return dict(grouped)


def build_pending_reminder_message(assignee, projects, now_dt=None):
    now = now_dt if isinstance(now_dt, datetime) else datetime.now()
    items = list(projects or [])
    lines = [
        f"【创新提案待处理提醒｜{now.strftime('%Y-%m-%d')}｜{assignee}】",
        "",
        f"以下 {len(items)} 条提案已超过2天未处理，请尽快承接处理：",
        "",
    ]
    for index, project in enumerate(items, start=1):
        project_id = str(project.get("project_id") or "-").strip()
        title = _clip_text(project.get("title"), limit=100)
        content = _clip_text(project.get("content"), limit=220)
        elapsed = _format_elapsed(project.get("flow_time"), now)
        lines.extend([
            f"{index}. 提案编号：#{project_id}",
            f"   提案标题：{title}",
            f"   提案内容：{content}",
            f"   未处理时长：{elapsed}",
            "",
        ])
    lines.extend([
        "请尽快进入创新管理处理：",
        MANAGE_URL,
    ])
    return "\n".join(lines).strip()


class InnovationPendingReminder:
    def __init__(self, query_fn=sf_db, service_factory=None, enabled=None):
        self.query_fn = query_fn
        self.service_factory = service_factory or FeishuReminderMessageService
        if enabled is None:
            raw = str(os.environ.get("INNOVATION_PENDING_REMINDER_ENABLED", "1")).strip().lower()
            enabled = raw not in {"0", "false", "no", "off"}
        self.enabled = bool(enabled)
        self._lock = Lock()
        self._thread_started = False
        self._last_attempt_date = ""
        self.last_result = None

    @property
    def thread_started(self):
        with self._lock:
            return self._thread_started

    def run_once(self, now_dt=None, send_messages=True, include_message_details=False):
        now = now_dt if isinstance(now_dt, datetime) else datetime.now()
        projects = load_overdue_pending_projects(now_dt=now, query_fn=self.query_fn)
        grouped = group_projects_by_assignee(projects)
        result = {
            "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "overdue_count": len(projects),
            "assignee_count": len(grouped),
            "recipient_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "dry_run": not send_messages,
            "assignees": {},
        }
        if not send_messages:
            result["assignees"] = {name: len(items) for name, items in grouped.items()}
            self.last_result = result
            return result

        message_service = self.service_factory()
        for assignee, items in grouped.items():
            message = build_pending_reminder_message(assignee, items, now_dt=now)
            contacts = []
            try:
                contacts = message_service.get_department_contacts(assignee) or []
            except Exception:
                contacts = []
            contacts = list(dict.fromkeys(str(contact or "").strip() for contact in contacts if str(contact or "").strip()))

            assignee_result = {"project_count": len(items), "recipient_count": 0, "success": 0, "failed": 0}
            if include_message_details:
                assignee_result["message"] = message
                assignee_result["recipients"] = []
            if contacts:
                for contact in contacts:
                    assignee_result["recipient_count"] += 1
                    try:
                        sent = bool(message_service.send_message(contact, message))
                    except Exception:
                        sent = False
                    if sent:
                        assignee_result["success"] += 1
                    else:
                        assignee_result["failed"] += 1
                    if include_message_details:
                        recipient_result = {
                            "id": contact,
                            "name": str(getattr(message_service, "recipient_names", {}).get(contact) or "").strip(),
                            "success": sent,
                        }
                        if not sent:
                            recipient_result["error"] = _send_error_text(message_service)
                        assignee_result["recipients"].append(recipient_result)
            else:
                assignee_result["recipient_count"] = 1
                try:
                    sent = bool(message_service.send_message(assignee, message))
                except Exception:
                    sent = False
                if sent:
                    assignee_result["success"] = 1
                else:
                    assignee_result["failed"] = 1
                if include_message_details:
                    recipient_result = {
                        "id": assignee,
                        "name": str(getattr(message_service, "recipient_names", {}).get(assignee) or assignee).strip(),
                        "success": sent,
                    }
                    if not sent:
                        recipient_result["error"] = _send_error_text(message_service)
                    assignee_result["recipients"].append(recipient_result)

            result["recipient_count"] += assignee_result["recipient_count"]
            result["success_count"] += assignee_result["success"]
            result["failed_count"] += assignee_result["failed"]
            result["assignees"][assignee] = assignee_result

        self.last_result = result
        return result

    def _loop(self):
        while True:
            now = datetime.now()
            day_key = now.strftime("%Y-%m-%d")
            should_run = False
            if now.hour == 9:
                with self._lock:
                    if self._last_attempt_date != day_key:
                        self._last_attempt_date = day_key
                        should_run = True
            if should_run:
                try:
                    self.run_once(now_dt=now, send_messages=True)
                except Exception as exc:
                    self.last_result = {
                        "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "error": str(exc),
                    }
                    with self._lock:
                        self._last_attempt_date = ""
            time.sleep(30)

    def start(self):
        if not self.enabled:
            return False
        with self._lock:
            if self._thread_started:
                return True
            thread = Thread(target=self._loop, name="innovation_pending_reminder", daemon=True)
            thread.start()
            self._thread_started = True
        return True


innovation_pending_reminder = InnovationPendingReminder()
